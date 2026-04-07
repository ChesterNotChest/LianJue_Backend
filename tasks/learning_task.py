# TODO 这里计划构建学生端的学习任务系统，负责管理学生的学习任务状态，提供方法供学生提问、获取学习资源等。

'''
模糊需求：
1. 学生提问的当前时间的时间戳，以匹配的形式来定位当前应该处在的进度。

2. 随后，将学生的提问做RAG检索，用检索结果来与教学大纲的描述性内容做语义比对，以锚定学生问的是第几周的内容。

3. 将1和2的内容，来确认学生学习进度与提问进度（已学，在学，未学）来完成不同程度指导，
再通过提问的质量来评判学生的掌握度是否薄弱。
如果薄弱，则标记薄弱
（每个学生有一个独立的拓展后的教学大纲
    （带有额外“competance”和"updated_at"的教学大纲json文件）
）。

如果提问质量比较一般，则标记为正常。如果询问特别有深度，则标记为掌握。
改完就把"updated_at"改成当前时间戳。一段时间后，自动降级一等。
'''


import os
import json
import re
from time import time
from datetime import datetime, timezone
from constant import PersonalSyllabus

from utils.llm_utils import get_model_instance
from utils.markdown_utils import clean_llm_response
from knowlion.abution_knowlion_driver import KnowLion
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_syllabus_repo import get_user_syllabus, set_personal_syllabus_path
from schemas.file import File
from extensions import db

'''
如下的描述都是相对于sylllabus json文件 来做拓展的。

personal_sylllabus外部多了如下字段：
review_count # 这个不是复习次数，而是llm的审查次数。
reviewed_at: 时间戳

personal_sylllabus的*每个周*都多包括如下字段：
    competance: weak/normal/master/none
    competance_progress: -5 to +5, 每次提问根据质量提升或降低，达到+5则升级，-5则降级
    suggested_competance_list: 由大模型产生的建议若干，用于后续得到最终suggested_competance。review_count每达到5次，清空一次。
    updated_at: 时间戳

'''

def ask_question(user_id: int, syllabus_id: int, question: str):
    '''
    里面的大部分是伪代码。主要用于描述流程逻辑。
    1. 获取当前时间戳


    2. 获取personal_syllabus_path（从user_syllabus表中获取），并获取json文件内容，来定位应该在 第几周。
        _get_current_week(syllabus_id, current_time)

    3. 让大模型用 学生的提问 来与 教学大纲中每周的描述性内容 做语义比对，来判断学生提问对应的是 哪几周。
        relevant_week_list = _get_relevant_week_by_semantic(question, syllabus_id)
        RAG_list = []
        for week_index in relevant_week_list:
            enhanced_content = 取自personal_syllabus_path -> 的json里对应week_index的"enhanced_content"字段，来增强学生的提问内容，以提供给大模型更丰富的上下文信息。
            RAG_list.append({
                "week_index": week_index,
                "rag_content": _search_method(enhanced_content)
            })
        
    4. history_window = 由一个 syllabus_id_student_id.json 维护，最大长度为5，来存储学生的提问历史和大模型的回答历史（仅包含timestamp, question, answer这3个字段）。
    5. user_prompt: question + 应处周次 + 实际周次-RAG结果 + 掌握度（如果有的话）
    6. system_prompt: 要求产出 {answer + document_names[...] + competance_list（掌握度） [{week_index: weak_far/weak/normal/master/master_far}, ...]}
        根据进度差异和掌握度来给出不同的指导建议。
        根据进度差异来给出不同的掌握度评判。
         - 计划提供检索结果的结构，来指明 文档名称 的位置

        _调用json解析方法()
        _存储历史对话() - 请存到/history/syllabus_id_student_id.json里，来维护一个历史对话窗口，最大长度为5，来存储学生的提问历史和大模型的回答历史（仅包含timestamp, question, answer这3个字段）。

    7. documents用来和mysql的file表中的material_path模糊匹配，来找到对应的file_id。匹配不到的直接展示llm给的document名字
        _match_documents(document_names)

    8. 如果competance比json里的高/低 n 级，则向对应的competance_progress加 n / -n。(far表是距离normal有2级远，weak和master则距离normal有1级远）
        如果刚好处在同一个competance等级，对于normal自然+1，其余的(weak/master)则不变。
        如果初始json的competance是none，则设为llm给出的competance等级。（出现far 则设为对应的非far等级）
        if not _update_review_count(personal_syllabus_path):
            for week_index, suggested_competance in competance_list:
                _toggle_competance(personal_syllabus_path, week_index, suggested_competance)
        else:
            for week_index, suggested_competance in competance_list:
                _update_competance(personal_syllabus_path, week_index)

    '''

    now_ts = int(time())

    # 1. 获取 personal syllabus path
    ps = get_user_syllabus(user_id, syllabus_id)
    personal_path = getattr(ps, 'personal_syllabus_path', None) if ps else None
    if not personal_path or not os.path.exists(personal_path):
        init_personal_syllabus(user_id, syllabus_id)
        ps = get_user_syllabus(user_id, syllabus_id)
        personal_path = getattr(ps, 'personal_syllabus_path', None) if ps else None

    # 2. 当前处在第几周
    current_week = _get_current_week(syllabus_id, now_ts)

    # 3. 语义比对定位相关周次
    relevant_week_list = _get_relevant_week_by_semantic(question, syllabus_id)

    # 3.b RAG for each relevant week (use enhanced_content from personal or syllabus)
    rag_list = []
    syllabus = get_syllabus_by_id(syllabus_id)
    syllabus_json = None
    if syllabus and getattr(syllabus, 'syllabus_path', None) and os.path.exists(syllabus.syllabus_path):
        try:
            with open(syllabus.syllabus_path, 'r', encoding='utf-8') as f:
                syllabus_json = json.load(f)
        except Exception:
            syllabus_json = None

    graph_name = None
    if syllabus_json:
        graph_name = syllabus_json.get('graph_name')

    kl = None
    try:
        kl = KnowLion({}, graph_name or '')
    except Exception:
        kl = None

    for wi in relevant_week_list:
        enhanced = None
        # try personal syllabus
        if personal_path and os.path.exists(personal_path):
            try:
                with open(personal_path, 'r', encoding='utf-8') as f:
                    pjson = json.load(f)
                    period = pjson.get('period', [])
                    for entry in period:
                        if str(entry.get('week_index')) == str(wi):
                            enhanced = entry.get('enhanced_content') or entry.get('content')
                            break
            except Exception:
                enhanced = None
        # fallback to syllabus json
        if enhanced is None and syllabus_json:
            for entry in syllabus_json.get('period', []):
                if str(entry.get('week_index')) == str(wi):
                    enhanced = entry.get('enhanced_content') or entry.get('content')
                    break

        rag_content = None
        if kl and enhanced:
            try:
                res = kl.search(enhanced, top_k=6)
                # prefer paragraphs or reasoning_paths
                rag_content = res.get('paragraphs') or res.get('reasoning_paths') or res
            except Exception:
                rag_content = None

        rag_list.append({"week_index": wi, "rag_content": rag_content})

    # 4. history window file
    hist_dir = os.path.join(os.getcwd(), 'history')
    os.makedirs(hist_dir, exist_ok=True)
    hist_path = os.path.join(hist_dir, f"{syllabus_id}_{user_id}.json")
    history = []
    if os.path.exists(hist_path):
        try:
            with open(hist_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = []

    # get current competence for current_week if present
    current_competance = None
    if personal_path and os.path.exists(personal_path):
        try:
            with open(personal_path, 'r', encoding='utf-8') as f:
                pjson = json.load(f)
                for entry in pjson.get('period', []):
                    if str(entry.get('week_index')) == str(current_week):
                        current_competance = entry.get('competance')
                        break
        except Exception:
            current_competance = None

    # 5/6 build prompts — strict JSON output, follow schema similar to syllabus/material tasks
    system_prompt = '''
你是一个学习指导专家，负责根据学生提问、教学进度（周次）与检索到的上下文（RAG）来判断学生当前掌握情况并给出指导建议。

严格输出要求（仅输出纯 JSON，不要包含任何自然语言说明或注释）：
{
  "answer": "<string: 对学生问题的直接答案或指导>",
  "document_names": ["<string: 推荐或引用的文档名称/路径>", ...],
  "competance_list": [
    {"week_index": "<string|int>", "level": "weak_far|weak|normal|master|master_far"},
    ...
  ]
}

输出策略：
- `answer` 应基于提供的 RAG 检索内容与教学周片段，优先引用高置信度检索结果；若检索不足，可基于通用教学知识给出简洁答案。
- `document_names` 列出用于回答的主要文档名称（若无可匹配文档，则可留空列表）。
- `competance_list` 针对 `relevant_weeks` 中的周次按本次提问质量评估建议的掌握度，取值必须是 weak_far|weak|normal|master|master_far。
- 只在匹配度明确时才标注 weak_far 或 master_far；不要输出其他未在此枚举中的等级字符串。

行为约束：
- 严格只返回 JSON；不输出额外文字。
- 若无法判断，则在 `answer` 中说明不可判断，并返回空的 `document_names` 与一个对当前周（expected_week）的 `competance_list` 条目，等级可设为 "normal"。
'''

    # user prompt contains structured inputs — include RAG and context explicitly
    user_prompt = json.dumps({
        "question": question,
        "expected_week": current_week,
        "relevant_weeks": relevant_week_list,
        "rag": rag_list,
        "current_competance": current_competance
    }, ensure_ascii=False)

    model = get_model_instance()
    try:
        raw = model.call_text_model(system_prompt, user_prompt, stream=False, history=history)
    except Exception as e:
        raw = f"LLM call failed: {e}"

    # normalize model output and parse JSON
    cleaned_raw = clean_llm_response(raw)
    parsed = None
    if cleaned_raw:
        try:
            parsed = json.loads(cleaned_raw)
        except Exception:
            # attempt to extract JSON substring from cleaned text
            m = re.search(r"\{.*\}", cleaned_raw, flags=re.S)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    parsed = {"answer": cleaned_raw}
            else:
                parsed = {"answer": cleaned_raw}
    else:
        parsed = {"answer": cleaned_raw}

    # 7. match documents
    doc_names = parsed.get('document_names') if isinstance(parsed, dict) else None
    matched = _match_documents(doc_names or [])

    # 8. competence handling
    competance_list = parsed.get('competance_list') if isinstance(parsed, dict) else []
    # update review count and apply suggested competance
    if personal_path:
        reached = False
        try:
            reached = _update_review_count(personal_path)
        except Exception:
            reached = False

        if not reached:
            for item in competance_list or []:
                wi = item.get('week_index')
                lvl = item.get('level') or item.get('competance')
                try:
                    _toggle_competance(personal_path, wi, lvl)
                except Exception:
                    pass
        else:
            for item in competance_list or []:
                wi = item.get('week_index')
                try:
                    _update_competance(personal_path, wi)
                except Exception:
                    pass

    # store history (keep last 5)
    entry = {"timestamp": now_ts, "question": question, "answer": parsed.get('answer') if isinstance(parsed, dict) else str(parsed)}
    history.append(entry)
    history = history[-5:]
    try:
        with open(hist_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # return structured result
    out = {
        'answer': parsed.get('answer') if isinstance(parsed, dict) else str(parsed),
        'matched_files': matched,
        'competance_list': competance_list,
        'raw': parsed
    }
    return out

def init_personal_syllabus(user_id: int, syllabus_id: int):
    # Initialize a personal syllabus for a user based on the main syllabus structure, with default competance and progress.
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        return False
    syllabus_json = None
    if getattr(syllabus, 'syllabus_path', None) and os.path.exists(syllabus.syllabus_path):
        try:
            with open(syllabus.syllabus_path, 'r', encoding='utf-8') as f:
                syllabus_json = json.load(f)
        except Exception:
            syllabus_json = None
    if not syllabus_json:
        return False
    personal_json = {
        "syllabus_id": syllabus_id,
        "user_id": user_id,
        "review_count": 0,
        "reviewed_at": 0,
        "period": []
    }
    for entry in syllabus_json.get('period', []):
        personal_entry = {
            "week_index": entry.get('week_index'),
            "content": entry.get('content'),
            "enhanced_content": entry.get('enhanced_content'),
            "competance": "none",
            "competance_progress": 0,
            "suggested_competance_list": [],
            "updated_at": 0
        }
        personal_json['period'].append(personal_entry)
    # build a cross-platform directory path and ensure it exists
    personal_base_path = os.path.join(os.getcwd(), 'schedule', 'student_alt', f'user_{user_id}')
    try:
        os.makedirs(personal_base_path, exist_ok=True)
    except Exception:
        return False

    personal_path = os.path.join(personal_base_path, f'{syllabus_id}_personal.json')
    try:
        with open(personal_path, 'w', encoding='utf-8') as f:
            json.dump(personal_json, f, ensure_ascii=False, indent=2)
    except Exception:
        return False

    # store absolute path in UserSyllabus table (create or update record)
    abs_path = os.path.abspath(personal_path)
    ps = set_personal_syllabus_path(user_id, syllabus_id, abs_path)
    if not ps:
        return False
    return abs_path

def _manage_forgetting_curve():
    '''
    定时任务，每天执行一次，来管理遗忘曲线。
    1. 遍历所有personal_syllabus_json文件，检查每个周次的updated_at字段。
    2. 如果updated_at距离当前时间超过一定阈值，则将competance降低一级，并将competance_progress重置为0。
    3. 更新personal_syllabus_json文件。
    '''
    base_dir = os.path.join(os.getcwd(), 'schedule', 'student_alt')
    if not os.path.exists(base_dir):
        return 0

    now_ts = int(time())
    try:
        forget_days = int(PersonalSyllabus.FORGET_DAYS.value)
    except Exception:
        forget_days = 7
    threshold = forget_days * 24 * 3600

    modified_count = 0

    for user_folder in os.listdir(base_dir):
        user_path = os.path.join(base_dir, user_folder)
        if not os.path.isdir(user_path):
            continue

        for fname in os.listdir(user_path):
            if not fname.endswith('_personal.json'):
                continue
            personal_path = os.path.join(user_path, fname)
            try:
                with open(personal_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue

            changed = False
            period = data.get('period', [])
            for entry in period:
                try:
                    updated_at = int(entry.get('updated_at') or 0)
                except Exception:
                    updated_at = 0

                if updated_at <= 0:
                    continue

                if now_ts - updated_at > threshold:
                    cur = entry.get('competance')
                    # downgrade one level: master -> normal, normal -> weak, weak stays weak
                    new_level = cur
                    if cur == 'master':
                        new_level = 'normal'
                    elif cur == 'normal':
                        new_level = 'weak'

                    if new_level != cur:
                        entry['competance'] = new_level
                        entry['competance_progress'] = 0
                        entry['updated_at'] = now_ts
                        changed = True

            if changed:
                try:
                    with open(personal_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    modified_count += 1
                except Exception:
                    pass

    return modified_count

def _get_current_week(syllabus_id: int, current_time: int):
    '''
    1. 获取从数据库，获取day_one_time，与current_time对比，来定位应该在 第几周。
    2. 返回当前周次
    '''
    syllabus = get_syllabus_by_id(syllabus_id)
    day_one_dt = None
    if syllabus and getattr(syllabus, 'day_one_time', None):
        day_one_dt = syllabus.day_one_time
    else:
        # try reading syllabus json
        if syllabus and getattr(syllabus, 'syllabus_path', None) and os.path.exists(syllabus.syllabus_path):
            try:
                with open(syllabus.syllabus_path, 'r', encoding='utf-8') as f:
                    sj = json.load(f)
                    d = sj.get('day_one')
                    if isinstance(d, str) and re.match(r"\d{4}-\d{2}-\d{2}", d):
                        day_one_dt = datetime.fromisoformat(d)
            except Exception:
                day_one_dt = None

    if not day_one_dt:
        return 1

    # ensure timezone-naive comparison
    if isinstance(day_one_dt, datetime):
        day_one_dt = day_one_dt.replace(tzinfo=None)
        now_dt = datetime.fromtimestamp(current_time, timezone.utc).replace(tzinfo=None)
        delta_days = (now_dt - day_one_dt).days
    else:
        delta_days = 0

    if delta_days < 0:
        return 1
    week = delta_days // 7 + 1
    return week

def _get_relevant_week_by_semantic(question: str, syllabus_id: int):
    '''
    1. 获取syllabus_path（从syllabus表中获取），并获取json文件内容，来获取每周的描述性内容。
    2. 让大模型用 学生的提问 来与 教学大纲中每周的描述性内容 做语义比对，来判断学生提问对应的是 哪几周。
    3. 返回对应的周次列表
    system_prompt: 你是一个问题定位助手，负责根据学生的提问来判断学生提问对应的是教学大纲中的哪几周的内容。教学大纲的每周内容都有一个描述性文本。请根据学生的提问来与每周的描述性文本做语义比对，来判断学生提问对应的是哪几周的内容。只在匹配程度较为明确的情况下，才判断为相关。请返回一个列表，包含所有相关的周次。至少返回一个周次。
    '''
    syllabus = get_syllabus_by_id(syllabus_id)
    syllabus_json = None
    if syllabus and getattr(syllabus, 'syllabus_path', None) and os.path.exists(syllabus.syllabus_path):
        try:
            with open(syllabus.syllabus_path, 'r', encoding='utf-8') as f:
                syllabus_json = json.load(f)
        except Exception:
            syllabus_json = None

    period = syllabus_json.get('period', []) if syllabus_json else []
    fragments = []
    for entry in period:
        idx = entry.get('week_index')
        txt = entry.get('enhanced_content') or entry.get('content') or ''
        fragments.append({'week_index': idx, 'text': txt})

    system_prompt = "你是一个问题定位助手，负责根据学生的提问来判断学生提问对应的是教学大纲中的哪几周的内容。教学大纲的每周内容都有一个描述性文本。请根据学生的提问来与每周的描述性文本做语义比对，来判断学生提问对应的是哪几周的内容。只在匹配程度较为明确的情况下，才判断为相关。请返回一个列表，包含所有相关的周次。至少返回一个周次。返回json，格式如下：{week_indices: [1, 2, ...]}"

    user_frag = question + "\n\n"
    for f in fragments:
        user_frag += f"week_index: {f['week_index']}\ncontent: {f['text']}\n---\n"

    model = get_model_instance()
    try:
        resp = model.call_text_model(system_prompt, user_frag, stream=False)
    except Exception:
        resp = None

    cleaned = clean_llm_response(resp)
    if not cleaned:
        return [1]

    # Prefer strict JSON output: try parse and extract 'week_indices'
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            wi = parsed.get('week_indices') or parsed.get('week_indices'.replace('_', ' ')) or parsed.get('week_indices'.replace('_', '-'))
            # also accept keys like 'week_indexes' or 'week_indices'
            if not wi:
                for k in parsed.keys():
                    if 'week' in k and ('index' in k or 'indices' in k or 'indexes' in k):
                        wi = parsed.get(k)
                        break
            if isinstance(wi, list) and wi:
                # normalize to ints and unique-preserve order
                out = []
                for v in wi:
                    try:
                        iv = int(v)
                    except Exception:
                        continue
                    if iv not in out:
                        out.append(iv)
                if out:
                    return out
    except Exception:
        # not valid json — fall back to regex extraction
        pass

    # fallback: regex number extraction from cleaned text
    nums = re.findall(r"\d+", cleaned)
    if nums:
        seen = []
        for n in nums:
            if n not in seen:
                seen.append(n)
        return [int(x) for x in seen]

    return [1]

def _match_documents(document_names: list[str]):
    '''
    1. 对于每个document_name，在file表中模糊匹配material_path，来找到对应的file_id。匹配不到的直接展示llm给的document名字
    2. 返回一个列表，包含每个document_name对应的file_id（如果有的话）
    '''
    results = []
    if not document_names:
        return results
    for name in document_names:
        if not name:
            results.append(None)
            continue
        # fuzzy match against File.path
        try:
            q = File.query.filter(File.path.ilike(f"%{name}%"))
            fobj = q.first()
            if fobj:
                results.append(fobj.file_id)
            else:
                results.append(name)
        except Exception:
            results.append(name)
    return results

def _update_review_count(personal_syllabus_path: str) -> bool:
    '''
    1. 读取personal_syllabus_json文件，获取当前review_count
    2. review_count加1。reviewed_at 更新为当前时间戳。
    3. 返回是否达到了需要推动教学进度的条件（例如review_count达到5次）（超时的更新由其他方法处理）。
    '''
    if not personal_syllabus_path or not os.path.exists(personal_syllabus_path):
        return False
    try:
        with open(personal_syllabus_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return False

    rc = data.get('review_count', 0) or 0
    rc += 1
    data['review_count'] = rc
    data['reviewed_at'] = int(time())
    try:
        with open(personal_syllabus_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # return whether reached LLM review threshold
    try:
        return rc >= int(PersonalSyllabus.LLM_REVIEW_THREDHOLD.value)
    except Exception:
        return rc >= 5

def _toggle_competance(personal_syllabus_path: str, week_index: int, suggested_competance: str):
    '''
    对对应的周的suggested_competance_list进行更新，来提供给后续的复习建议。
    '''
    if not personal_syllabus_path or not os.path.exists(personal_syllabus_path):
        return
    try:
        with open(personal_syllabus_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return

    period = data.get('period', [])
    for entry in period:
        if str(entry.get('week_index')) == str(week_index):
            lst = entry.get('suggested_competance_list') or []
            lst.append(suggested_competance)
            entry['suggested_competance_list'] = lst
            entry['updated_at'] = int(time())
            break

    try:
        with open(personal_syllabus_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _update_competance(personal_syllabus_path: str, week_index: int):
    '''
    1. 定义:
    suggested_competance等级顺序：weak_far < weak < normal < master < master_far
    competance等级顺序：weak < normal < master < none
    2. 读取json里的suggested_competance_list，以如下规则加减后得到最终suggested_competance如下————
        weak_far=-2, weak=-1, normal=0, master=1, master_far=2
        计算方式：total_score = sum(分数列表)
        avg_score = total_score / len(分数列表)
        平均值 → 最终等级：
        avg_score <= -1.5 → weak_far
        -1.5 < avg_score <= -0.5 → weak
        -0.5 < avg_score < 0.5 → normal
        0.5 <= avg_score < 1.5 → master
        avg_score >= 1.5 → master_far
由此得到suggested_competance。并清空suggested_competance_list。
    3. 读取personal_syllabus_json文件，获取当前competance等级和competance_progress。
    4. 根据suggested_competance与当前competance的差异，来调整competance_progress。
        如果suggested_competance比当前competance高/低 n 级，则向对应的competance_progress加 n / -n。(far表是距离normal有2级远，weak和master则距离normal有1级远）
        如果刚好处在同一个competance等级，对于normal自然+1，其余的(weak/master)则不变。
        如果初始json的competance是none，则设为llm给出的competance等级。（出现far 则设为对应的非far等级）
    5. 如果competance_progress达到+5，则升级competance等级；如果达到-5，则降级competance等级。
    6. 更新personal_syllabus_json文件中的competance和competance_progress字段，更新updated_at。
    '''
    if not personal_syllabus_path or not os.path.exists(personal_syllabus_path):
        return

    try:
        with open(personal_syllabus_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return

    period = data.get('period', [])
    target = None
    for entry in period:
        if str(entry.get('week_index')) == str(week_index):
            target = entry
            break
    if not target:
        return

    # map suggested strings to numeric scores
    score_map = {'weak_far': -2, 'weak': -1, 'normal': 0, 'master': 1, 'master_far': 2}

    sugg_list = target.get('suggested_competance_list') or []
    if not isinstance(sugg_list, list) or len(sugg_list) == 0:
        return

    # compute average score
    scores = [score_map.get(s, 0) for s in sugg_list]
    avg = sum(scores) / len(scores)

    if avg <= -1.5:
        suggested = 'weak_far'
    elif -1.5 < avg <= -0.5:
        suggested = 'weak'
    elif -0.5 < avg < 0.5:
        suggested = 'normal'
    elif 0.5 <= avg < 1.5:
        suggested = 'master'
    else:
        suggested = 'master_far'

    # clear suggested list
    target['suggested_competance_list'] = []

    # current values
    cur = target.get('competance')
    cur_prog = int(target.get('competance_progress') or 0)

    # if current is none or missing, set to suggested base (non-far)
    if cur is None or cur == 'none':
        base = suggested.replace('_far', '') if suggested.endswith('_far') else suggested
        target['competance'] = base
        target['competance_progress'] = 0
        target['updated_at'] = int(time())
        try:
            with open(personal_syllabus_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return

    # numeric mapping for base levels (centered at normal)
    base_map = {'weak': -1, 'normal': 0, 'master': 1}
    suggested_val = score_map.get(suggested, 0)
    # use base value for current (None handled above)
    cur_val = base_map.get(cur, 0)

    # compute diff (suggested - current)
    diff = suggested_val - cur_val

    # if diff is zero and current is normal, reward small positive progress
    if diff == 0:
        if cur == 'normal':
            cur_prog += 1
    else:
        cur_prog += diff

    # promotion/demotion thresholds (use constants)
    new_level = cur
    try:
        prog_max = int(PersonalSyllabus.PROGRESS_MAX.value)
    except Exception:
        prog_max = 5
    try:
        prog_min = int(PersonalSyllabus.PROGRESS_MIN.value)
    except Exception:
        prog_min = -5

    if cur_prog >= prog_max:
        if cur == 'weak':
            new_level = 'normal'
        elif cur == 'normal':
            new_level = 'master'
        cur_prog = 0
    elif cur_prog <= prog_min:
        if cur == 'master':
            new_level = 'normal'
        elif cur == 'normal':
            new_level = 'weak'
        cur_prog = 0

    target['competance'] = new_level
    target['competance_progress'] = cur_prog
    target['updated_at'] = int(time())

    try:
        with open(personal_syllabus_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 这个是为API设计的，后续可以根据需要来调整参数和返回值。它不是工具函数，而是一个完整的业务流程函数。
def update_personal_syllabus(user_id: int, syllabus_id: int, week_index: int, study_time_spent: int = -1, competance: str = None, competance_progress: int = None):
    """
    Update a user's personal syllabus entry for a given week.

    Rules (strict):
    - If `study_time_spent` != -1, interpret as hours and map to progress increments:
        1h -> +2, 2h -> +4, 3h -> +5, >3h -> +5.
      DO NOT use `review_count` as a study counter (its meaning is LLM audit).
      Update only `competance_progress`, `competance` if thresholds hit, and `reviewed_at`/`updated_at` timestamps.
    - If `study_time_spent` == -1, then apply direct overrides from `competance` and/or `competance_progress` if provided.
    - Persist changes to the personal syllabus JSON file. Return parsed dict on success, None on failure.
    """
    if user_id is None or syllabus_id is None or week_index is None:
        return None

    ps = get_user_syllabus(user_id, syllabus_id)
    personal_path = getattr(ps, 'personal_syllabus_path', None) if ps else None
    if not personal_path or not os.path.exists(personal_path):
        try:
            init_personal_syllabus(user_id, syllabus_id)
        except Exception:
            pass
        ps = get_user_syllabus(user_id, syllabus_id)
        personal_path = getattr(ps, 'personal_syllabus_path', None) if ps else None

    if not personal_path or not os.path.exists(personal_path):
        return None

    try:
        with open(personal_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    period = data.get('period', [])
    target = None
    for entry in period:
        if str(entry.get('week_index')) == str(week_index):
            target = entry
            break
    if not target:
        return None

    now_ts = int(time())

    # Study time mode
    if study_time_spent is not None and int(study_time_spent) != -1:
        hrs = int(study_time_spent)
        if hrs <= 0:
            inc = 0
        elif hrs == 1:
            inc = 2
        elif hrs == 2:
            inc = 4
        else:
            inc = 5

        # update timestamps only; do NOT touch review_count
        data['reviewed_at'] = now_ts

        # apply progress
        cur_prog = int(target.get('competance_progress') or 0)
        cur_prog += inc
        cur = target.get('competance') or 'normal'

        # promotion/demotion using constants
        new_level = cur
        if cur_prog >= PersonalSyllabus.PROGRESS_MAX.value:
            if cur == 'weak':
                new_level = 'normal'
            elif cur == 'normal':
                new_level = 'master'
            cur_prog = 0
        elif cur_prog <= PersonalSyllabus.PROGRESS_MIN.value:
            if cur == 'master':
                new_level = 'normal'
            elif cur == 'normal':
                new_level = 'weak'
            cur_prog = 0

        target['competance'] = new_level
        target['competance_progress'] = cur_prog
        target['updated_at'] = now_ts

    else:
        # direct override mode
        changed = False
        if competance is not None:
            target['competance'] = competance
            changed = True
        if competance_progress is not None:
            try:
                target['competance_progress'] = int(competance_progress)
                changed = True
            except Exception:
                pass
        if changed:
            target['updated_at'] = now_ts

    try:
        with open(personal_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return None

    return data


def get_personal_syllabus_detail_info(user_id: int, syllabus_id: int) -> dict:
    """
    Return parsed personal syllabus JSON for a user and syllabus.
    Mirrors `get_material_detail_info` style: reads JSON file and returns parsed dict or None.
    """
    if user_id is None or syllabus_id is None:
        return None

    ps = get_user_syllabus(user_id, syllabus_id)
    personal_path = getattr(ps, 'personal_syllabus_path', None) if ps else None
    if not personal_path or not os.path.exists(personal_path):
        try:
            init_personal_syllabus(user_id, syllabus_id)
        except Exception:
            pass
        ps = get_user_syllabus(user_id, syllabus_id)
        personal_path = getattr(ps, 'personal_syllabus_path', None) if ps else None

    if not personal_path or not os.path.exists(personal_path):
        return None

    try:
        with open(personal_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None



