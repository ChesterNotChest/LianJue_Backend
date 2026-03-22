from datetime import datetime
from pathlib import Path
import os
import json
import time
from repositories.file_repo import create_file
from repositories.jobs_repo import create_job, get_job_by_id, get_status_by_job_id, get_graphId_by_job_id
from repositories.syllabus_repo import create_syllabus, get_syllabus_by_id, set_syllabus_draft_path
from schemas.syllabus import Syllabus
from utils.markdown_utils import preprocess_markdown_content, clean_llm_response
from utils.llm_utils import get_model_instance
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
    except Exception as e:
        print(f"   ❌ 保存 syllabus 草稿失败: {e}")

    return syllabus


def update_syllabus_draft(syllabus_id: int, week_index: str, new_content: str = None, new_importance: str = None) -> Syllabus:
    """Update an existing syllabus draft JSON for a given `syllabus_id`.

    - Only updates fields that already exist in the matched week entry.
    - `week_index` is used for matching and will not be modified.
    - `new_importance` must be one of: 'low', 'medium', 'high' (case-insensitive accepted).
    - `new_content` must be a string.

    Returns the `Syllabus` object on success, or None on failure.
    """
    # validate inputs
    if new_content is None and new_importance is None:
        print("   ⚠️ [POST] 没有要更新的字段（content 或 importance）。")
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

    if not updated:
        print("   ⚠️ [POST] 未执行任何更新（没有匹配到可修改的字段）。")
        return None

    # write back
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"   💾 [POST] 草稿已更新并保存: {draft_path}")
    except Exception as e:
        print(f"   ❌ [POST] 保存更新失败: {e}")
        return None

    return syllabus

# build_syllabus()

# get_syllabus()
