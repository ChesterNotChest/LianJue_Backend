from datetime import datetime
import re
from pathlib import Path
import os
import json
import time
import uuid
import shutil
from repositories.jobs_repo import create_job, get_job_by_id, get_status_by_job_id, get_graphId_by_job_id
from repositories.file_repo import create_file, delete_file, get_file_by_id
from repositories.syllabus_repo import create_syllabus, get_syllabus_by_id, set_syllabus_draft_path, set_syllabus_path, set_syllabus_day_one, set_syllabus_title, list_all_syllabuses
from repositories.syllabus_graph_repo import create_syllabus_graph, list_graphs_by_syllabus
from repositories.graph_repo import get_graph_by_id, get_graph_by_graphId
from repositories.user_syllabus_repo import create_user_syllabus, list_user_syllabuses, list_user_syllabuses_by_syllabus
from schemas.syllabus import Syllabus
from schemas.user_syllabus import UserSyllabus
from schemas.file import File
from constant import SyllabusPermission
from utils.markdown_utils import preprocess_markdown_content, clean_llm_response
from utils.llm_utils import get_model_instance
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential
from extensions import db
from tasks.syllabus.storage import (
    is_missing_path,
    parse_day_one_string,
    read_json_from_path,
    resolve_repo_path,
    validate_syllabus_period,
    write_json_to_path,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _reset_db_session():
    # Force the next ORM read to use a brand-new Session/transaction so it can
    # observe commits made by the background JobChecker thread.
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass


def _get_latest_job_status(job_id: int):
    _reset_db_session()
    return get_status_by_job_id(job_id)


def _get_latest_job(job_id: int):
    _reset_db_session()
    return get_job_by_id(job_id)


def _has_file_references(file_id: int) -> bool:
    if file_id is None:
        return False
    if Syllabus.query.filter_by(file_id=file_id).first() is not None:
        return True
    try:
        from repositories.filegraph_repo import get_bindings_by_file_id
        return bool(get_bindings_by_file_id(file_id))
    except Exception:
        return True


def _calendar_path_exists(path: str) -> bool:
    abs_path = os.path.abspath(path)
    return (
        os.path.exists(abs_path)
        or File.query.filter_by(path=abs_path).first() is not None
        or Syllabus.query.filter_by(edu_calendar_path=abs_path).first() is not None
    )


def _unique_calendar_path(save_dir: str, file_name: str) -> str:
    safe_name = os.path.basename(file_name or 'calendar.pdf')
    if save_dir:
        base_path = os.path.abspath(os.path.join(save_dir, safe_name))
    else:
        base_path = os.path.abspath(safe_name)

    if not _calendar_path_exists(base_path):
        return base_path

    stem, ext = os.path.splitext(safe_name)
    parent = os.path.dirname(base_path)
    for _ in range(10):
        suffix = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        candidate_name = f"{stem}_{suffix}{ext}"
        candidate_path = os.path.abspath(os.path.join(parent, candidate_name))
        if not _calendar_path_exists(candidate_path):
            return candidate_path

    raise RuntimeError("failed to allocate unique calendar file path")


def _add_calendar_file(file_path: str, file_name: str, file_bytes: bytes = None, upload_time: str = None) -> dict:
    save_dir = os.path.dirname(file_path)
    actual_path = _unique_calendar_path(save_dir, file_name)
    existed_before_create = File.query.filter_by(path=actual_path).first() is not None
    wrote_file = False
    source_path = os.path.abspath(file_path)

    try:
        if file_bytes is not None:
            parent = os.path.dirname(actual_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            content = file_bytes if isinstance(file_bytes, (bytes, bytearray)) else str(file_bytes).encode('utf-8')
            with open(actual_path, 'wb') as wf:
                wf.write(content)
            wrote_file = True
        else:
            if not os.path.isfile(source_path):
                raise FileNotFoundError(f"calendar source file does not exist: {source_path}")
            if os.path.abspath(actual_path) != source_path:
                parent = os.path.dirname(actual_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                shutil.copy2(source_path, actual_path)
                wrote_file = True

        file_record = create_file(actual_path, upload_time=upload_time)
        file_id = getattr(file_record, 'file_id', None)
    except Exception:
        if wrote_file and os.path.isfile(actual_path):
            try:
                os.remove(actual_path)
            except Exception:
                pass
        raise

    return {
        'file_id': file_id,
        'path': actual_path,
        'created': not existed_before_create,
    }


def _delete_calendar_file_if_created(uploaded_file: dict) -> None:
    if not uploaded_file or not uploaded_file.get('created'):
        return

    file_id = uploaded_file.get('file_id')
    actual_path = uploaded_file.get('path')
    if file_id is None or not actual_path:
        return

    file_record = get_file_by_id(file_id)
    if file_record is None:
        return

    file_path_to_remove = getattr(file_record, 'path', None)
    if os.path.abspath(file_path_to_remove or '') != os.path.abspath(actual_path):
        return
    if _has_file_references(file_id):
        return

    delete_file(file_id)
    if file_path_to_remove and os.path.isfile(file_path_to_remove):
        os.remove(file_path_to_remove)


def upload_calendar(file_path, file_name, file_bytes: bytes = None, upload_time: str = None, user_id: int = None) -> Syllabus:
    # 上传一份新的教学日历，生成一个新的syllabus记录
    if not upload_time:
        upload_time = datetime.utcnow().isoformat()
    uploaded_file = None
    syllabus = None

    try:
        uploaded_file = _add_calendar_file(file_path, file_name, file_bytes=file_bytes, upload_time=upload_time)
        syllabus = create_syllabus(
            edu_calendar_path=uploaded_file['path'],
            file_id=uploaded_file['file_id'],
        )
        if syllabus is not None and user_id is not None:
            create_user_syllabus(
                user_id=int(user_id),
                syllabus_id=int(getattr(syllabus, 'syllabus_id', None)),
                syllabus_permission=SyllabusPermission.OWNER.value,
            )

        return syllabus
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

        try:
            if syllabus is not None and getattr(syllabus, 'syllabus_id', None) is not None:
                UserSyllabus.query.filter_by(syllabus_id=syllabus.syllabus_id).delete()
                db.session.delete(syllabus)
                db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass

        try:
            _delete_calendar_file_if_created(uploaded_file)
        except Exception:
            pass

        raise


def build_syllabus_draft(syllabus_id: int, graph_id: int, initial_prompt: str) -> Syllabus:
    '''
    {
    title: "",  
    related_graph: [  # 用于图数据库向量检索
    {
    "graph_name": "", 
    }, 
    ],  
 
    }
    '''
    # 构建syllabus草稿，生成一个新的syllabus记录
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        raise RuntimeError(f"Syllabus {syllabus_id} not found")

    syllabus_pk = int(getattr(syllabus, 'syllabus_id'))
    syllabus_file_id = getattr(syllabus, 'file_id', None)
    syllabus_calendar_path = getattr(syllabus, 'edu_calendar_path', None)


    # 1. 解析教学日历，提取关键信息
    file_id = syllabus.file_id
    job = create_job(file_id=syllabus_file_id, end_stage="pdf_to_md", graph_id=graph_id)
    job_id = int(getattr(job, 'job_id'))

    while True:
        job_status = _get_latest_job_status(job_id)
        if job_status == "completed":
            break
        if job_status == "failed":
            fresh_job = _get_latest_job(job_id)
            error_message = getattr(fresh_job, 'error_message', '') if fresh_job else ''
            raise RuntimeError(f"Job {job_id} 执行失败: {error_message or 'unknown error'}")

        print(f"   ⏳ [POST] 等待 pdf_to_md 任务完成... 当前状态: {job_status}")
        time.sleep(5)  # 每5秒检查一次状态，直到pdf_to_md阶段完成

    # 2. 读取解析出来的markdown内容
    job = _get_latest_job(job_id)
    md_path = job.markdown_path if job else None
    if not md_path:
        print(f"   ❌ [POST] Job {job_id} 没有 markdown_path，无法进行 md_to_triples")
        return []
    
    # 读取md文件
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
    except Exception as e:
        print(f"   ❌ [POST] 读取 Markdown 文件失败: {e}")
        return []
    
    # 3. 基于initial_prompt和md_content，构建syllabus草稿内容
    system_prompt = """
你是一个教学设计专家，负责根据教学日历内容生成结构化的课程大纲草稿。

【任务说明】
请根据以下教学日历内容，结合你的专业知识，提取关键教学主题并按周次构建课程大纲。

【输出格式要求】
必须严格遵守以下JSON格式：
{
    "period": [
        {
            "week_index": "1",
            "content": "大数据课程导论与基本概念：介绍学科背景、课程目标、考核方式，以及核心概念框架",
            "importance": "low",
        },
        {
            "week_index": "2",
            "content": "大数据的定义、特点，以及大数据的具体应用",
            "importance": "high", 
        }
    ]
}

【字段说明】
- week_index: 教学周次（如"1"、"2"）
- content: 详细教学内容描述（50-100字）
- importance: 重要性等级（high/medium/low）

【重要性评估标准】
- high: 核心概念、基础理论、必须掌握的知识点
- medium: 重要但非核心的扩展知识、应用案例  
- low: 补充阅读、拓展内容、非考核重点

【处理步骤】
1. 分析教学日历中的主题分布
2. 按时间顺序组织教学周次
3. 为每个教学周提炼核心内容
4. 评估每个周次的教学重要性
5. 提取关键概念术语
"""
    
    # 4. 调取大模型
    model_instance = get_model_instance()
    # clean md content a bit before sending
    md_content = preprocess_markdown_content(md_content)

    user_prompt = f"""
用户要求：
{initial_prompt}
教学日历内容如下：
{md_content}
"""

    # call the text model (system prompt + user prompt)
    try:
        raw_response = model_instance.call_text_model(system_prompt, user_prompt)
    except Exception as e:
        print(f"   ❌ 调用大模型失败: {e}")
        return None

    # clean potential fences and try to parse JSON
    cleaned = clean_llm_response(raw_response)
    parsed = None
    try:
        parsed = json.loads(cleaned)
    except Exception:
        # try to extract the first JSON block in the response
        import re
        m = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', cleaned)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None

    if parsed is None:
        print("   ❌ 无法解析模型返回的 JSON 草稿。返回原始文本供人工查看。")
        draft_obj = {
            "period": [],
            "raw_model_text": cleaned
        }
    else:
        # ensure result is a dict with 'period' key
        if isinstance(parsed, list):
            draft_obj = {"period": parsed}
        elif isinstance(parsed, dict):
            draft_obj = parsed
        else:
            draft_obj = {"period": []}

    # 补充 title 与 graph_name 字段
    title = None
    if syllabus_calendar_path:
        title = os.path.basename(syllabus_calendar_path)
    else:
        title = f"syllabus_{syllabus_pk}"

    graphId = get_graphId_by_job_id(job_id)
    graph_name = graphId
    draft_obj["title"] = title
    draft_obj["graph_name"] = graph_name

    # persist draft to schedule/syllabus_draft with timestamped filename and update syllabus record
    try:
        drafts_dir = Path("./schedule/syllabus_draft")
        drafts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        if syllabus_calendar_path:
            base_name = Path(syllabus_calendar_path).stem
        else:
            base_name = f"syllabus_{syllabus_pk}"
        draft_fname = f"{base_name}_{ts}.json"
        draft_path = drafts_dir / draft_fname
        with draft_path.open('w', encoding='utf-8') as f:
            json.dump(draft_obj, f, ensure_ascii=False, indent=2)
        # save path to syllabus and commit
        set_syllabus_draft_path(syllabus_id, str(draft_path))
        print(f"   💾 [POST] Syllabus 草稿已保存: {draft_path}")
        # establish syllabus <-> graph association (many-to-many) via repo
        try:
            create_syllabus_graph(syllabus_id=syllabus_id, graph_id=graph_id)
            print(f"   🔗 [POST] Syllabus 与 graph_id={graph_id} 的关联已保存。")
        except Exception as e:
            print(f"   ⚠️ [POST] 保存 Syllabus-Graph 关联失败: {e}")
    except Exception as e:
        print(f"   ❌ 保存 syllabus 草稿失败: {e}")

    return get_syllabus_by_id(syllabus_pk)


def _validate_syllabus_period(period: list) -> bool:
    return validate_syllabus_period(period)


def _read_json_from_path(path_value: str):
    return read_json_from_path(path_value, BACKEND_ROOT)


def _write_json_to_path(path_value: str, payload: dict) -> bool:
    return write_json_to_path(path_value, payload, BACKEND_ROOT)


def _parse_day_one_string(day_one: str):
    return parse_day_one_string(day_one)


def _is_missing_path(path_value) -> bool:
    return is_missing_path(path_value)


def _resolve_repo_path(path_value):
    return resolve_repo_path(path_value, BACKEND_ROOT)


def _extract_graph_name_from_syllabus_payload(syllabus) -> str:
    for path_attr in ('syllabus_path', 'syllabus_draft_path'):
        payload = _read_json_from_path(getattr(syllabus, path_attr, None))
        if not isinstance(payload, dict):
            continue
        graph_name = payload.get('graph_name')
        if isinstance(graph_name, str) and graph_name.strip():
            return graph_name.strip()
    return None


def _get_graph_info_from_legacy_payload(syllabus_id: int):
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        return None, None

    legacy_graph_name = _extract_graph_name_from_syllabus_payload(syllabus)
    if not legacy_graph_name:
        return None, None

    graph = get_graph_by_graphId(legacy_graph_name)
    if not graph:
        return None, legacy_graph_name

    try:
        create_syllabus_graph(syllabus_id=syllabus_id, graph_id=graph.graph_id)
    except Exception as e:
        print(f"   [LIST] failed to backfill syllabus_graph for syllabus_id={syllabus_id}: {e}")

    return getattr(graph, 'graph_id', None), getattr(graph, 'graphId', legacy_graph_name)


def _sync_personal_syllabuses_from_syllabus_json(syllabus_id: int, syllabus_json: dict) -> int:
    if not isinstance(syllabus_json, dict):
        return 0

    period = syllabus_json.get('period')
    if not isinstance(period, list):
        return 0

    try:
        bindings = list_user_syllabuses_by_syllabus(syllabus_id)
    except Exception as e:
        print(f"   [UPDATE] failed to list related personal_syllabus bindings: {e}")
        return 0

    synced_count = 0

    for binding in bindings:
        personal_path = getattr(binding, 'personal_syllabus_path', None)
        resolved_personal_path = _resolve_repo_path(personal_path)
        if resolved_personal_path is None or not resolved_personal_path.exists():
            continue

        existing_json = _read_json_from_path(personal_path)
        if not isinstance(existing_json, dict):
            continue

        existing_period = existing_json.get('period')
        if not isinstance(existing_period, list):
            existing_period = []

        existing_by_week = {
            str(entry.get('week_index')): entry
            for entry in existing_period
            if isinstance(entry, dict) and entry.get('week_index') is not None
        }

        synced_period = []
        for syllabus_entry in period:
            if not isinstance(syllabus_entry, dict):
                continue

            week_key = str(syllabus_entry.get('week_index'))
            existing_entry = existing_by_week.get(week_key, {})
            synced_period.append({
                'week_index': syllabus_entry.get('week_index'),
                'content': syllabus_entry.get('content'),
                'enhanced_content': syllabus_entry.get('enhanced_content'),
                'importance': syllabus_entry.get('importance'),
                'competance': existing_entry.get('competance', 'none'),
                'competance_progress': existing_entry.get('competance_progress', 0),
                'suggested_competance_list': existing_entry.get('suggested_competance_list', []),
                'updated_at': existing_entry.get('updated_at', 0),
            })

        existing_json['syllabus_id'] = syllabus_id
        existing_json['user_id'] = getattr(binding, 'user_id', existing_json.get('user_id'))
        existing_json['period'] = synced_period

        if _write_json_to_path(personal_path, existing_json):
            synced_count += 1

    return synced_count


def update_syllabus_draft_json(syllabus_id: int, syllabus_draft_json: dict) -> Syllabus:
    """Replace the whole syllabus draft JSON with the submitted raw json."""
    if not isinstance(syllabus_draft_json, dict):
        print("   [UPDATE] `syllabus_draft_json` must be a dict.")
        return None

    required_fields = ('title', 'graph_name', 'period')
    if any(field not in syllabus_draft_json for field in required_fields):
        print(f"   [UPDATE] syllabus_draft_json must contain: {required_fields}")
        return None

    if not _validate_syllabus_period(syllabus_draft_json.get('period')):
        return None

    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   [UPDATE] invalid syllabus_id: {syllabus_id}")
        return None

    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    resolved_draft_path = _resolve_repo_path(draft_path)
    if not draft_path or resolved_draft_path is None or not resolved_draft_path.exists():
        print(f"   [UPDATE] draft file does not exist: {draft_path}")
        return None

    if not _write_json_to_path(draft_path, syllabus_draft_json):
        return None

    title = syllabus_draft_json.get('title')
    if isinstance(title, str) and title.strip():
        try:
            set_syllabus_title(syllabus_id, title)
        except Exception as e:
            print(f"   [UPDATE] failed to persist draft title to DB: {e}")

    print(f"   [UPDATE] syllabus draft updated and saved: {draft_path}")
    return get_syllabus_by_id(syllabus_id)


def get_syllabus_draft_detail_info(syllabus_id: int) -> dict:
    """Return the full syllabus draft JSON for the given syllabus_id."""
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [GET] 无效的 syllabus_id: {syllabus_id}")
        return None

    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    if not draft_path:
        print(f"   ❌ [GET] syllabus {syllabus_id} 未配置 draft 路径。")
        return None

    p = _resolve_repo_path(draft_path)
    if p is None or not p.exists():
        print(f"   ❌ [GET] 草稿文件不存在: {draft_path}")
        return None

    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"   ❌ [GET] 读取或解析草稿文件失败: {e}")
        return None


def get_syllabus_status(syllabus_id: int) -> dict:
    """Return syllabus status flags for upload/draft/final readiness."""
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        return None

    edu_calendar_path = getattr(syllabus, 'edu_calendar_path', None)
    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    final_path = getattr(syllabus, 'syllabus_path', None)

    return {
        'is_edu_calendar_path_null': _is_missing_path(edu_calendar_path),
        'is_syllabus_draft_path_null': _is_missing_path(draft_path),
        'is_syllabus_path_null': _is_missing_path(final_path),
    }
    
def _serialize_day_one_time(value):
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _get_primary_graph_info(syllabus_id: int):
    graph_ids = list_graphs_by_syllabus(syllabus_id)
    for graph_id in graph_ids:
        graph = get_graph_by_id(graph_id)
        if graph:
            return getattr(graph, 'graph_id', graph_id), getattr(graph, 'graphId', None)
    return _get_graph_info_from_legacy_payload(syllabus_id)


def _serialize_teacher_syllabus(syllabus, user_binding=None):
    graph_id, graph_name = _get_primary_graph_info(getattr(syllabus, 'syllabus_id', None))
    permission = getattr(user_binding, 'syllabus_permission', None)

    return {
        'syllabus_id': getattr(syllabus, 'syllabus_id', None),
        'title': getattr(syllabus, 'title', None),
        'edu_calendar_path': getattr(syllabus, 'edu_calendar_path', None),
        'syllabus_draft_path': getattr(syllabus, 'syllabus_draft_path', None),
        'syllabus_path': getattr(syllabus, 'syllabus_path', None),
        'day_one_time': _serialize_day_one_time(getattr(syllabus, 'day_one_time', None)),
        'syllabus_permission': permission,
        'graph_id': graph_id,
        'graph_name': graph_name,
    }


def _serialize_student_syllabus(syllabus, user_binding):
    personal_path = getattr(user_binding, 'personal_syllabus_path', None)
    return {
        'syllabus_id': getattr(syllabus, 'syllabus_id', None),
        'title': getattr(syllabus, 'title', None),
        'personal_syllabus_path': personal_path,
        'day_one_time': _serialize_day_one_time(getattr(syllabus, 'day_one_time', None)),
        'isLearning': bool(personal_path),
    }


def _list_manageable_syllabuses(user_id: int):
    bindings = list_user_syllabuses(user_id, syllabus_permission=SyllabusPermission.OWNER.value)
    result = []

    for binding in bindings:
        syllabus = get_syllabus_by_id(getattr(binding, 'syllabus_id', None))
        if not syllabus:
            continue
        result.append(_serialize_teacher_syllabus(syllabus, binding))

    return result


def _list_learning_syllabuses(user_id: int):
    bindings = list_user_syllabuses(user_id)
    result = []

    for binding in bindings:
        syllabus = get_syllabus_by_id(getattr(binding, 'syllabus_id', None))
        if not syllabus:
            continue
        result.append(_serialize_student_syllabus(syllabus, binding))

    return result


def list_all_syllabuses_brief_info(user_id: int = None, manage: bool = False):
    """List syllabus brief info for teacher manage view or student learning view.

    - user_id is None: return all syllabuses in teacher-style shape.
    - manage=True: return only syllabuses the user can manage (owner).
    - manage=False: return all syllabuses bound to the user in student-style shape.
    """
    if user_id is None:
        syllabuses = list_all_syllabuses()
        return [_serialize_teacher_syllabus(s) for s in syllabuses]

    if manage:
        return _list_manageable_syllabuses(user_id)

    return _list_learning_syllabuses(user_id)

def build_syllabus(syllabus_id: int) -> Syllabus:
    """Build final syllabus by enriching each `period` entry.

    Steps:
    - Load existing syllabus draft (must contain 'period' list).
    - For each week entry: keep `original_content`, run `KnowLion.search()` to retrieve context,
      then call the text model to produce `enhanced_content`.
    - Save final syllabus JSON (set `syllabus_path`) and return the Syllabus record.

    Arguments:
    - syllabus_id: id of the syllabus record to process.
    """
    # load syllabus record and draft
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [BUILD] 无效的 syllabus_id: {syllabus_id}")
        return None

    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    if not draft_path:
        print(f"   ❌ [BUILD] syllabus {syllabus_id} 未配置 draft 路径。")
        return None

    p = _resolve_repo_path(draft_path)
    if p is None or not p.exists():
        print(f"   ❌ [BUILD] 草稿文件不存在: {draft_path}")
        return None

    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"   ❌ [BUILD] 读取或解析草稿文件失败: {e}")
        return None

    period = data.get('period')
    if not isinstance(period, list) or len(period) == 0:
        print("   ❌ [BUILD] 草稿中不包含有效的 'period' 列表，无法构建最终 syllabus。")
        return None

    # determine graph_name through syllabus -> graph relation
    graph_name = None
    try:
        _, graph_name = _get_primary_graph_info(syllabus_id)
    except Exception as e:
        print(f"   [BUILD] failed to resolve graph by syllabus relation: {e}")
        graph_name = None

    # Prepare model instance
    model_instance = get_model_instance()

    # Try to initialize KnowLion for retrieval; if it fails, proceed with LLM-only enrichment
    kl = None
    try:
        from config import LITELLM_MODEL_CONFIGS
        from knowlion.abution_knowlion_driver import KnowLion
        if graph_name:
            kl = KnowLion(LITELLM_MODEL_CONFIGS, graph_name=str(graph_name))
        else:
            # instantiate with a dummy graph id to allow model-only fallback
            kl = None
    except Exception as e:
        print(f"   ⚠️ [BUILD] 无法初始化 KnowLion 检索器（将使用 LLM-only 模式）: {e}")
        kl = None

    # prompts
    system_prompt = (
        "你是教学设计专家。请基于原始教学周内容与检索到的相关参考资料，生成一段100-200字的增强描述（enhanced_content）用于后续知识匹配，" 
        "只返回增强后的纯文本描述，不要包含JSON或额外说明。"
    )

    # iterate and enrich concurrently using a thread pool and retry on LLM failures
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def call_model_with_retry(sys_prompt: str, usr_prompt: str) -> str:
        return model_instance.call_text_model(sys_prompt, usr_prompt)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=6))
    def search_with_retry(text: str, top_k: int = 6):
        if kl is None:
            raise RuntimeError("KnowLion not initialized")
        return kl.search(text, top_k=top_k)


    # First: perform retrievals sequentially to avoid overloading the retrieval service
    retrieval_texts = [""] * len(period)
    for idx, entry in enumerate(period):
        try:
            orig = entry.get('content') or entry.get('original_content') or ""
            entry['original_content'] = orig
            retrieval_text = ''
            if kl is not None:
                try:
                    try:
                        retrieval_results = search_with_retry(orig, top_k=6)
                    except Exception:
                        # fallback attempt with smaller top_k before giving up
                        retrieval_results = None
                        try:
                            retrieval_results = search_with_retry(orig, top_k=3)
                        except Exception as e:
                            print(f"   ⚠️ [BUILD] 第 {idx+1} 条检索连续失败，跳过检索: {e}")
                            retrieval_results = None

                    if retrieval_results:
                        retrieval_text = json.dumps(retrieval_results.get('reasoning_paths', []) or retrieval_results.get('paragraphs', []), ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"   ⚠️ [BUILD] 第 {idx+1} 条检索失败，跳过检索: {e}")

            retrieval_texts[idx] = retrieval_text
            # small pause between retrievals to be polite to the service
            time.sleep(0.2)
        except Exception as e:
            print(f"   ⚠️ [BUILD] 检索阶段第 {idx+1} 条发生异常: {e}")

    # Then: call the LLM concurrently using prepared retrieval_texts
    def call_for_idx(i: int, entry: dict, retrieval_text: str) -> tuple:
        try:
            orig = entry.get('original_content', '')
            user_prompt = f"原始周内容:\n{orig}\n\n检索到的参考资料（如有）:\n{retrieval_text}\n\n请根据上述内容生成增强描述："
            raw = call_model_with_retry(system_prompt, user_prompt)
            enhanced = clean_llm_response(raw)
            return i, enhanced or ""
        except Exception as e:
            print(f"   ⚠️ [BUILD] 第 {i+1} 条调用大模型失败: {e}")
            return i, ""

    max_workers = min(4, max(1, len(period)))
    with ThreadPoolExecutor(max_workers=max_workers) as exc:
        futures = {exc.submit(call_for_idx, idx, entry, retrieval_texts[idx]): idx for idx, entry in enumerate(period)}
        for fut in as_completed(futures):
            try:
                _idx, enhanced_text = fut.result()
                if 0 <= _idx < len(period):
                    period[_idx]['enhanced_content'] = enhanced_text
                    if 'importance' not in period[_idx]:
                        period[_idx]['importance'] = period[_idx].get('importance', 'medium')
            except Exception as e:
                print(f"   ⚠️ [BUILD] 并发任务处理失败: {e}")

    # finalize metadata
    # Determine day_one for final JSON (do not modify DB here)
    db_day = getattr(syllabus, 'day_one_time', None)
    if data.get('day_one'):
        final_day_one = data.get('day_one')
    elif db_day:
        try:
            final_day_one = db_day.strftime('%Y-%m-%d')
        except Exception:
            final_day_one = str(db_day)
    else:
        final_day_one = '3-2'

    # Title MUST come from the draft JSON; do not fallback to external names
    title_in_json = data.get('title')
    if not title_in_json or not isinstance(title_in_json, str) or title_in_json.strip() == "":
        print("   ❌ [BUILD] 草稿 JSON 中缺少有效的 'title' 字段，无法构建最终 syllabus。（要求：title 必须来自草稿）")
        return None

    final_obj = {
        'title': title_in_json,
        'day_one': final_day_one,
        'graph_name': graph_name,
        'period': period
    }

    # persist final syllabus
    try:
        finals_dir = Path('./schedule/syllabus')
        finals_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        # sanitize title for filename: remove problematic chars, replace spaces with underscore
        safe_title = re.sub(r'[^A-Za-z0-9\u4e00-\u9fff\-_ ]', '', title_in_json).strip()
        safe_title = safe_title.replace(' ', '_') or f"syllabus_{syllabus.syllabus_id}"
        fname = f"{safe_title}_{ts}.json"
        final_path = finals_dir / fname
        with final_path.open('w', encoding='utf-8') as f:
            json.dump(final_obj, f, ensure_ascii=False, indent=2)

        # update syllabus record
        try:
            set_syllabus_path(syllabus_id, str(final_path))
        except Exception:
            # best-effort: ignore DB write failures but inform
            print(f"   ⚠️ [BUILD] 无法保存 syllabus_path 到 DB（请检查 DB 连接）")

        # also persist the title into DB (final title comes from draft JSON)
        try:
            set_syllabus_title(syllabus_id, title_in_json)
        except Exception:
            print(f"   ⚠️ [BUILD] 无法保存 title 到 DB（非致命）")

        print(f"   💾 [BUILD] 最终 syllabus 已保存: {final_path}")
    except Exception as e:
        print(f"   ❌ [BUILD] 保存最终 syllabus 失败: {e}")
        return None

    return syllabus

# update_syllabus()
def update_syllabus_json(syllabus_id: int, syllabus_json: dict) -> Syllabus:
    """Replace the whole final syllabus JSON with the submitted raw json."""
    if not isinstance(syllabus_json, dict):
        print("   [UPDATE] `syllabus_json` must be a dict.")
        return None

    required_fields = ('title', 'day_one', 'graph_name', 'period')
    if any(field not in syllabus_json for field in required_fields):
        print(f"   [UPDATE] syllabus_json must contain: {required_fields}")
        return None

    if not _validate_syllabus_period(syllabus_json.get('period')):
        return None

    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   [UPDATE] invalid syllabus_id: {syllabus_id}")
        return None

    final_path = getattr(syllabus, 'syllabus_path', None)
    resolved_final_path = _resolve_repo_path(final_path)
    if not final_path or resolved_final_path is None or not resolved_final_path.exists():
        print(f"   [UPDATE] final syllabus file does not exist: {final_path}")
        return None

    if not _write_json_to_path(final_path, syllabus_json):
        return None

    title = syllabus_json.get('title')
    if isinstance(title, str) and title.strip():
        try:
            set_syllabus_title(syllabus_id, title)
        except Exception as e:
            print(f"   [UPDATE] failed to persist final title to DB: {e}")

    parsed_day_one = _parse_day_one_string(syllabus_json.get('day_one'))
    if parsed_day_one is not None:
        try:
            set_syllabus_day_one(syllabus_id, parsed_day_one)
        except Exception as e:
            print(f"   [UPDATE] failed to persist final day_one to DB: {e}")

    synced_personal_count = _sync_personal_syllabuses_from_syllabus_json(syllabus_id, syllabus_json)
    if synced_personal_count:
        print(f"   [UPDATE] synced {synced_personal_count} related personal_syllabus file(s).")

    print(f"   [UPDATE] final syllabus updated and saved: {final_path}")
    return get_syllabus_by_id(syllabus_id)


def get_syllabus_detail_info(syllabus_id: int) -> dict:
    """Return the full final syllabus JSON for the given syllabus_id."""
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [GET] 无效的 syllabus_id: {syllabus_id}")
        return None

    final_path = getattr(syllabus, 'syllabus_path', None)
    if not final_path:
        print(f"   ❌ [GET] syllabus {syllabus_id} 未配置 final 路径。")
        return None

    p = _resolve_repo_path(final_path)
    if p is None or not p.exists():
        print(f"   ❌ [GET] final 文件不存在: {final_path}")
        return None

    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"   ❌ [GET] 读取或解析 final 文件失败: {e}")
        return None


def list_all_syllabus_brief_info() -> list:
    """Return a brief list of existing syllabus records.

    Each item contains: syllabus_id, edu_calendar_path, syllabus_draft_path, syllabus_path, day_one_time
    """
    items = []
    try:
        rows = list_all_syllabuses()
        for s in rows:
            items.append({
                'syllabus_id': getattr(s, 'syllabus_id', None),
                'title': getattr(s, 'title', None),
                'edu_calendar_path': getattr(s, 'edu_calendar_path', None),
                'syllabus_draft_path': getattr(s, 'syllabus_draft_path', None),
                'syllabus_path': getattr(s, 'syllabus_path', None),
                'day_one_time': getattr(s, 'day_one_time', None)
            })
        return items
    except Exception as e:
        print(f"   ⚠️ [LIST] 无法通过 repo 列出 syllabus 列表: {e}")
        return []
