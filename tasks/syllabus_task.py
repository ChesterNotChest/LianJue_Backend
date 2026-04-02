from datetime import datetime
import re
from pathlib import Path
import os
import json
import time
from repositories.file_repo import create_file
from repositories.jobs_repo import create_job, get_job_by_id, get_status_by_job_id, get_graphId_by_job_id
from repositories.syllabus_repo import create_syllabus, get_syllabus_by_id, set_syllabus_draft_path, set_syllabus_path, set_syllabus_day_one, set_syllabus_title, list_all_syllabuses
from repositories.syllabus_graph_repo import create_syllabus_graph
from schemas.syllabus import Syllabus
from utils.markdown_utils import preprocess_markdown_content, clean_llm_response
from utils.llm_utils import get_model_instance
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential
from extensions import db


def upload_calendar(file_path, upload_time: str = None) -> Syllabus:
    # 上传一份新的教学日历，生成一个新的syllabus记录
    if not upload_time:
        upload_time = datetime.utcnow().isoformat()
    file = create_file(file_path=file_path, upload_time=upload_time)
    file_id = file.file_id if file else None
    syllabus = create_syllabus(edu_calendar_path=file_path, file_id=file_id)
    
    return syllabus


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

    # 1. 解析教学日历，提取关键信息
    file_id = syllabus.file_id
    job = create_job(file_id=file_id, end_stage="pdf_to_md", graph_id=graph_id)

    while get_status_by_job_id(job.job_id) != "completed":
        print(f"   ⏳ [POST] 等待 pdf_to_md 任务完成... 当前状态: {get_status_by_job_id(job.job_id)}")
        time.sleep(5)  # 每5秒检查一次状态，直到pdf_to_md阶段完成

    # 2. 读取解析出来的markdown内容
    md_path = job.markdown_path
    if not md_path:
        print(f"   ❌ [POST] Job {job.job_id} 没有 markdown_path，无法进行 md_to_triples")
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
    if hasattr(syllabus, 'edu_calendar_path') and syllabus.edu_calendar_path:
        title = os.path.basename(syllabus.edu_calendar_path)
    else:
        title = f"syllabus_{syllabus.syllabus_id}"

    graphId = get_graphId_by_job_id(job.job_id)
    graph_name = graphId
    draft_obj["title"] = title
    draft_obj["graph_name"] = graph_name

    # persist draft to schedule/syllabus_draft with timestamped filename and update syllabus record
    try:
        drafts_dir = Path("./schedule/syllabus_draft")
        drafts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        if getattr(syllabus, 'edu_calendar_path', None):
            base_name = Path(syllabus.edu_calendar_path).stem
        else:
            base_name = f"syllabus_{syllabus.syllabus_id}"
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

    return syllabus


def update_syllabus_draft(syllabus_id: int, week_index: str, day_one: str = None, new_content: str = None, new_importance: str = None, new_title: str = None) -> Syllabus:
    """Update an existing syllabus draft JSON for a given `syllabus_id`.

    - Only updates fields that already exist in the matched week entry.
    - `week_index` is used for matching and will not be modified.
    - `new_importance` must be one of: 'low', 'medium', 'high' (case-insensitive accepted).
    - `new_content` must be a string.
    - `day_one` is mandatory and is used for positioning the begin of semester, it will not be updated but is required for locating the correct week entry in the draft.

    Returns the `Syllabus` object on success, or None on failure.
    """
    # validate inputs (allow updating title or day_one even if content/importance absent)
    if new_content is None and new_importance is None and new_title is None and (day_one is None or (isinstance(day_one, str) and day_one.strip() == "")):
        print("   ⚠️ [POST] 没有要更新的字段（content/importances/title/day_one）。")
        return None

    if new_importance is not None:
        ni = new_importance.lower()
        if ni not in ("low", "medium", "high"):
            print("   ❌ [POST] importance 必须是 'low'/'medium'/'high'。")
            return None
        new_importance = ni

    if new_content is not None and not isinstance(new_content, str):
        print("   ❌ [POST] new_content 必须是字符串。")
        return None

    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [POST] 无效的 syllabus_id: {syllabus_id}")
        return None

    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    if not draft_path:
        print(f"   ❌ [POST] syllabus {syllabus_id} 未配置 draft 路径。")
        return None

    p = Path(draft_path)
    if not p.exists():
        print(f"   ❌ [POST] 草稿文件不存在: {draft_path}")
        return None

    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"   ❌ [POST] 读取或解析草稿文件失败: {e}")
        return None

    period = data.get('period')
    if not isinstance(period, list):
        print("   ❌ [POST] 草稿中不包含有效的 'period' 列表，无法更新。")
        return None

    # find matching week entry (match as string)
    matched = None
    for entry in period:
        if str(entry.get('week_index')) == str(week_index):
            matched = entry
            break

    if not matched:
        print(f"   ❌ [POST] 未找到 week_index={week_index} 的条目。")
        return None

    # Only update fields that already exist in the entry
    updated = False
    if new_content is not None and 'content' in matched:
        matched['content'] = new_content
        updated = True
    elif new_content is not None:
        print("   ⚠️ [POST] 条目中不存在 'content' 字段，已跳过 content 更新。")

    if new_importance is not None and 'importance' in matched:
        matched['importance'] = new_importance
        updated = True
    elif new_importance is not None:
        print("   ⚠️ [POST] 条目中不存在 'importance' 字段，已跳过 importance 更新。")

    # allow updates that only change title or day_one even if content/importance weren't updated
    if not updated and new_title is None and (day_one is None or (isinstance(day_one, str) and day_one.strip() == "")):
        print("   ⚠️ [POST] 未执行任何更新（没有匹配到可修改的字段）。")
        return None
    elif not updated:
        print("   ⚠️ [POST] 未执行 content/importance 更新，但将处理 title/day_one 提交。")

    # If new_title provided, update the draft JSON title only (do NOT modify DB)
    if new_title is not None:
        try:
            data['title'] = new_title
            updated = True
        except Exception as e:
            print(f"   ⚠️ [POST] 更新 JSON 中的 title 失败: {e}")

    # Determine and persist day_one handling per rules:
    # - if day_one param is empty/None: read DB value; if DB missing -> default to '3-2' and save to DB
    # - if day_one param provided (non-empty), set JSON and attempt to persist parsed date to DB
    desired_day_one = None
    if day_one is None or (isinstance(day_one, str) and day_one.strip() == ""):
        # use DB value if present
        db_day = getattr(syllabus, 'day_one_time', None)
        if db_day:
            desired_day_one = db_day.strftime('%Y-%m-%d')
        else:
            desired_day_one = '3-2'
            # try to parse '3-2' into a date (current year)
            try:
                parts = desired_day_one.split('-')
                month = int(parts[0])
                day = int(parts[1])
                year = datetime.utcnow().year
                set_syllabus_day_one(syllabus_id, datetime(year, month, day))
            except Exception:
                pass
    else:
        # user provided a value -> set JSON and attempt to persist parsed date to DB
        desired_day_one = day_one
        parsed_dt = None
        try:
            if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', day_one):
                parsed_dt = datetime.strptime(day_one, '%Y-%m-%d')
            elif re.match(r'^\d{1,2}-\d{1,2}$', day_one):
                parts = day_one.split('-')
                month = int(parts[0])
                d = int(parts[1])
                year = datetime.utcnow().year
                parsed_dt = datetime(year, month, d)
            else:
                try:
                    parsed_dt = datetime.fromisoformat(day_one)
                except Exception:
                    parsed_dt = None
        except Exception:
            parsed_dt = None

        if parsed_dt is not None:
            try:
                set_syllabus_day_one(syllabus_id, parsed_dt)
            except Exception:
                pass

    # write desired_day_one into matched entry
    if desired_day_one is not None:
        matched['day_one'] = desired_day_one

    # write back
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"   💾 [POST] 草稿已更新并保存: {draft_path}")
    except Exception as e:
        print(f"   ❌ [POST] 保存更新失败: {e}")
        return None

    return syllabus

def get_syllabus_draft_detail_info(syllabus_id: int) -> dict:
    """Get syllabus draft detail info for a given syllabus_id, including parsed period entries and raw model text if available."""
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [GET] 无效的 syllabus_id: {syllabus_id}")
        return None

    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    if not draft_path:
        print(f"   ❌ [GET] syllabus {syllabus_id} 未配置 draft 路径。")
        return None

    p = Path(draft_path)
    if not p.exists():
        print(f"   ❌ [GET] 草稿文件不存在: {draft_path}")
        return None

    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        period = data.get('period', [])
        raw_model_text = data.get('raw_model_text', None)
        return {
            "period": period,
            "raw_model_text": raw_model_text
        }
    except Exception as e:
        print(f"   ❌ [GET] 读取或解析草稿文件失败: {e}")
        return None
    
def list_all_syllabuses_brief_info():
    """List all syllabuses with brief info (id, title, draft_path)."""
    syllabuses = list_all_syllabuses()
    result = []
    for s in syllabuses:
        result.append({
            "syllabus_id": s.syllabus_id,
            "title": s.title,
            "draft_path": s.syllabus_draft_path
        })
    return result

def build_syllabus(syllabus_id: int, graph_name: str = None) -> Syllabus:
    """Build final syllabus by enriching each `period` entry.

    Steps:
    - Load existing syllabus draft (must contain 'period' list).
    - For each week entry: keep `original_content`, run `KnowLion.search()` to retrieve context,
      then call the text model to produce `enhanced_content`.
    - Save final syllabus JSON (set `syllabus_path`) and return the Syllabus record.

    Arguments:
    - syllabus_id: id of the syllabus record to process.
    - graph_name: optional graph override (falls back to draft's graph_name).
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

    p = Path(draft_path)
    if not p.exists():
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

    # determine graph_name
    draft_graph = data.get('graph_name')
    graph_name = graph_name or draft_graph

    # Prepare model instance
    model_instance = get_model_instance()

    # Try to initialize KnowLion for retrieval; if it fails, proceed with LLM-only enrichment
    kl = None
    try:
        from config import MODEL_CONFIGS
        from knowlion.abution_knowlion_driver import KnowLion
        if graph_name:
            kl = KnowLion(MODEL_CONFIGS, graph_name=str(graph_name))
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
def update_syllabus(syllabus_id: int, *, title: str = None, day_one: str = None, syllabus_path: str = None) -> Syllabus:
    """Update syllabus record fields (title/day_one/syllabus_path).

    - `title`: will update the DB title field if provided (best-effort).
    - `day_one`: attempts to parse and persist a datetime to DB using `set_syllabus_day_one`.
    - `syllabus_path`: set the final syllabus JSON path in DB via `set_syllabus_path`.

    Returns the updated `Syllabus` object or None on failure.
    """
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [UPDATE] 无效的 syllabus_id: {syllabus_id}")
        return None

    # update day_one if provided
    if day_one:
        parsed_dt = None
        try:
            if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', day_one):
                parsed_dt = datetime.strptime(day_one, '%Y-%m-%d')
            elif re.match(r'^\d{1,2}-\d{1,2}$', day_one):
                parts = day_one.split('-')
                month = int(parts[0]); d = int(parts[1])
                year = datetime.utcnow().year
                parsed_dt = datetime(year, month, d)
            else:
                try:
                    parsed_dt = datetime.fromisoformat(day_one)
                except Exception:
                    parsed_dt = None
        except Exception:
            parsed_dt = None

        if parsed_dt is not None:
            try:
                set_syllabus_day_one(syllabus_id, parsed_dt)
                print(f"   💾 [UPDATE] 已更新 syllabus.day_one: {parsed_dt}")
            except Exception as e:
                print(f"   ⚠️ [UPDATE] 保存 day_one 到 DB 失败: {e}")
        else:
            print("   ⚠️ [UPDATE] 无法解析 day_one 字符串，已跳过 DB 保存。")

    # update syllabus_path if provided
    if syllabus_path:
        try:
            set_syllabus_path(syllabus_id, str(syllabus_path))
            print(f"   💾 [UPDATE] 已更新 syllabus_path: {syllabus_path}")
        except Exception as e:
            print(f"   ⚠️ [UPDATE] 保存 syllabus_path 到 DB 失败: {e}")

    # update title in draft JSON only is handled elsewhere; attempt DB title if provided
    if title:
        try:
            set_syllabus_title(syllabus_id, title)
            print(f"   💾 [UPDATE] 已更新 DB 中的 title: {title}")
        except Exception as e:
            print(f"   ⚠️ [UPDATE] 保存 title 到 DB 失败: {e}")

    # return fresh object
    try:
        return get_syllabus_by_id(syllabus_id)
    except Exception:
        return syllabus


def get_syllabus_detail_info(syllabus_id: int) -> dict:
    """Return detailed syllabus info including draft and final JSON contents.

    Returns a dict with keys: `syllabus` (DB object), `draft` (parsed JSON or None),
    `final` (parsed JSON or None). None returned on invalid id.
    """
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        print(f"   ❌ [GET] 无效的 syllabus_id: {syllabus_id}")
        return None

    result = {'syllabus': syllabus, 'draft': None, 'final': None}

    draft_path = getattr(syllabus, 'syllabus_draft_path', None)
    if draft_path:
        p = Path(draft_path)
        if p.exists():
            try:
                result['draft'] = json.loads(p.read_text(encoding='utf-8'))
            except Exception as e:
                print(f"   ⚠️ [GET] 读取 draft JSON 失败: {e}")

    final_path = getattr(syllabus, 'syllabus_path', None)
    if final_path:
        p2 = Path(final_path)
        if p2.exists():
            try:
                result['final'] = json.loads(p2.read_text(encoding='utf-8'))
            except Exception as e:
                print(f"   ⚠️ [GET] 读取 final JSON 失败: {e}")

    return result


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
