import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from repositories.file_repo import get_file_by_id
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_repo import get_user_by_id
from repositories.user_syllabus_repo import get_user_syllabus
from tasks.file_task import add_file as add_file_task
from tasks.learning_task import init_personal_syllabus
from utils.llm_utils import get_model_instance
from utils.markdown_utils import clean_llm_response


RESOURCE_TYPE_DEFS = {
    "document": {
        "label": "文档",
        "file_ext": "md",
        "prompt_kind": "study_note",
    },
    "question_bank": {
        "label": "题库",
        "file_ext": "md",
        "prompt_kind": "question_bank",
    },
    "mindmap": {
        "label": "思维导图",
        "file_ext": "md",
        "prompt_kind": "mindmap",
    },
    "code_case": {
        "label": "代码案例",
        "file_ext": "md",
        "prompt_kind": "code_case",
    },
    "video": {
        "label": "视频",
        "file_ext": "md",
        "prompt_kind": "video_script",
    },
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_int_list(values: Any) -> List[int]:
    if not isinstance(values, list):
        return []
    out: List[int] = []
    for value in values:
        try:
            iv = int(value)
        except Exception:
            continue
        if iv not in out:
            out.append(iv)
    return out


def _extract_json_object(text: Any) -> Optional[Dict[str, Any]]:
    cleaned = clean_llm_response(text)
    if not cleaned:
        return None

    try:
        payload = json.loads(cleaned)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None

    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _resource_root(user_id: int, syllabus_id: int) -> str:
    return os.path.join(
        os.getcwd(),
        "material",
        "student_generated_resources",
        f"user_{user_id}",
        f"syllabus_{syllabus_id}",
    )


def _manifest_path(user_id: int, syllabus_id: int) -> str:
    return os.path.join(_resource_root(user_id, syllabus_id), "manifest.json")


def _load_json_file(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_manifest(user_id: int, syllabus_id: int) -> List[Dict[str, Any]]:
    data = _load_json_file(_manifest_path(user_id, syllabus_id))
    return data if isinstance(data, list) else []


def _save_manifest(user_id: int, syllabus_id: int, items: List[Dict[str, Any]]) -> None:
    root = _resource_root(user_id, syllabus_id)
    os.makedirs(root, exist_ok=True)
    with open(_manifest_path(user_id, syllabus_id), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _ensure_personal_syllabus(user_id: int, syllabus_id: int) -> Optional[dict]:
    relation = get_user_syllabus(user_id, syllabus_id)
    personal_path = getattr(relation, "personal_syllabus_path", None) if relation else None
    if not personal_path or not os.path.exists(personal_path):
        personal_path = init_personal_syllabus(user_id, syllabus_id)
    if not personal_path or not os.path.exists(personal_path):
        return None
    data = _load_json_file(personal_path)
    return data if isinstance(data, dict) else None


def _load_syllabus_json(syllabus_id: int) -> Optional[dict]:
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        return None
    path = getattr(syllabus, "syllabus_path", None)
    data = _load_json_file(path)
    return data if isinstance(data, dict) else None


def _competance_focus(level: str) -> str:
    normalized = _safe_text(level) or "none"
    if normalized in {"weak_far", "weak"}:
        return "基础讲解要更细、步骤要更明确、要加入纠错提醒和低门槛练习。"
    if normalized == "normal":
        return "保持标准教学节奏，兼顾巩固与小幅提升。"
    if normalized in {"master", "master_far"}:
        return "压缩基础解释，增加迁移、对比、进阶挑战和开放性延伸。"
    return "按尚未开始学习的状态设计，先建立概念框架与入门路径。"


def _build_week_context(
    personal_syllabus: dict,
    syllabus_json: dict,
    week_indices: List[int],
) -> List[Dict[str, Any]]:
    personal_period = personal_syllabus.get("period", []) if isinstance(personal_syllabus, dict) else []
    syllabus_period = syllabus_json.get("period", []) if isinstance(syllabus_json, dict) else []
    personal_by_week = {
        int(entry.get("week_index")): entry
        for entry in personal_period
        if isinstance(entry, dict) and entry.get("week_index") is not None
    }
    syllabus_by_week = {
        int(entry.get("week_index")): entry
        for entry in syllabus_period
        if isinstance(entry, dict) and entry.get("week_index") is not None
    }

    result: List[Dict[str, Any]] = []
    for week_index in week_indices:
        personal_entry = personal_by_week.get(week_index, {})
        syllabus_entry = syllabus_by_week.get(week_index, {})
        content = _safe_text(
            personal_entry.get("enhanced_content")
            or personal_entry.get("content")
            or syllabus_entry.get("enhanced_content")
            or syllabus_entry.get("content")
        )
        competance = _safe_text(personal_entry.get("competance") or "none")
        result.append({
            "week_index": week_index,
            "importance": _safe_text(personal_entry.get("importance") or syllabus_entry.get("importance") or "medium"),
            "competance": competance,
            "competance_progress": int(personal_entry.get("competance_progress") or 0),
            "content": content,
            "focus_hint": _competance_focus(competance),
        })
    return result


def _build_personalization_summary(profile: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return {
            "learning_goal": "未提供",
            "learning_style": "balanced",
            "resource_preference": [],
            "difficulty_tolerance": "medium",
            "bottleneck_topics": [],
            "dropout_risk": "unknown",
        }
    return {
        "learning_goal": profile.get("learning_goal") or "未提供",
        "learning_style": profile.get("learning_style") or "balanced",
        "resource_preference": profile.get("resource_preference") or [],
        "difficulty_tolerance": profile.get("difficulty_tolerance") or "medium",
        "bottleneck_topics": profile.get("bottleneck_topics") or [],
        "dropout_risk": profile.get("dropout_risk") or "unknown",
    }


def _build_resource_prompt(resource_type: str, week_contexts: List[Dict[str, Any]], profile_summary: Dict[str, Any]) -> tuple[str, str]:
    type_def = RESOURCE_TYPE_DEFS[resource_type]
    prompt_kind = type_def["prompt_kind"]
    style = _safe_text(profile_summary.get("learning_style") or "balanced")
    preference = profile_summary.get("resource_preference") or []
    preference_text = "、".join([_safe_text(item) for item in preference if _safe_text(item)]) or "通用"
    bottlenecks = "、".join([_safe_text(item) for item in (profile_summary.get("bottleneck_topics") or []) if _safe_text(item)]) or "暂无明显瓶颈"

    week_lines = []
    for item in week_contexts:
        week_lines.append(
            "\n".join(
                [
                    f"第{item['week_index']}周",
                    f"- 掌握度: {item['competance']}",
                    f"- 难度: {item['importance']}",
                    f"- 进度值: {item['competance_progress']}",
                    f"- 内容: {item['content']}",
                    f"- 个性化策略: {item['focus_hint']}",
                ]
            )
        )

    base_system_prompt = """
你是联觉学习平台的学生端统一个性化资源生成器。

你必须依据学生当前周次知识掌握度、课程内容、学习风格和薄弱点，生成个性化学习资源。

严格只返回 JSON，不要返回 Markdown 代码块，不要返回解释文字。
返回格式必须是：
{
  "title": "资源标题",
  "summary": "80字以内摘要",
  "highlights": ["亮点1", "亮点2", "亮点3"],
  "content_markdown": "完整 Markdown 内容"
}

通用要求：
- 所有内容必须围绕用户选中的周次。
- 对掌握度 weak/weak_far 的周次，需要补足基础解释、误区提醒、分步骤练习。
- 对掌握度 master/master_far 的周次，需要减少重复基础内容，增加迁移和进阶挑战。
- 语言风格要贴合学生学习风格。
- 若同一次请求包含多个周次，要先给共性主线，再分别处理各周差异。
- content_markdown 必须是可直接展示或下载的完整内容。
""".strip()

    specialized_prompt_map = {
        "study_note": """
资源类型：学习文档
- 输出结构建议：学习目标、关键概念、按周梳理、常见误区、阶段性建议。
- 文档要有明确标题和分节。
- 对薄弱周次给出更细的解释和例子。
""".strip(),
        "question_bank": """
资源类型：题库
- 输出结构建议：题库说明、分层练习题、参考答案、简短解析。
- 总题量控制在 6 到 10 题之间。
- 题型可混合单选、判断、简答，但以 Markdown 呈现即可。
- 对薄弱周次增加基础巩固题，对掌握较好的周次加入迁移题。
""".strip(),
        "mindmap": """
资源类型：思维导图
- content_markdown 中必须包含 mermaid 思维导图代码块。
- 图后还要补一段如何阅读该图的说明。
- 节点结构必须体现周次之间的先后关系与重点差异。
""".strip(),
        "code_case": """
资源类型：代码案例
- content_markdown 必须包含至少一个可运行代码块。
- 结构建议：案例背景、代码、逐段讲解、变式练习、调试提醒。
- 若课程内容偏理论，也要给出一个最小可执行示例或伪代码案例。
""".strip(),
        "video_script": """
资源类型：视频
- 当前输出为“教学视频脚本包”，不是二进制视频文件。
- content_markdown 结构建议：视频标题、目标受众、推荐时长、分镜表、旁白脚本、画面提示、结尾练习。
- 分镜表需要包含镜头序号、时长、画面、旁白四列。
""".strip(),
    }

    user_prompt = json.dumps(
        {
            "learning_goal": profile_summary.get("learning_goal"),
            "learning_style": style,
            "resource_preference": preference_text,
            "difficulty_tolerance": profile_summary.get("difficulty_tolerance"),
            "dropout_risk": profile_summary.get("dropout_risk"),
            "bottleneck_topics": bottlenecks,
            "selected_weeks": week_lines,
            "resource_type": type_def["label"],
        },
        ensure_ascii=False,
        indent=2,
    )
    system_prompt = f"{base_system_prompt}\n\n{specialized_prompt_map[prompt_kind]}"
    return system_prompt, user_prompt


def _generate_single_resource(resource_type: str, week_contexts: List[Dict[str, Any]], profile_summary: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt, user_prompt = _build_resource_prompt(resource_type, week_contexts, profile_summary)
    model = get_model_instance()
    raw = model.call_text_model(system_prompt, user_prompt, stream=False)
    payload = _extract_json_object(raw)
    if not payload:
        raise ValueError(f"{resource_type} generation returned invalid JSON")

    title = _safe_text(payload.get("title")) or f"{RESOURCE_TYPE_DEFS[resource_type]['label']}资源"
    summary = _safe_text(payload.get("summary")) or f"{RESOURCE_TYPE_DEFS[resource_type]['label']}已生成"
    content_markdown = _safe_text(payload.get("content_markdown"))
    if not content_markdown:
        raise ValueError(f"{resource_type} generation returned empty content_markdown")

    highlights = payload.get("highlights")
    if not isinstance(highlights, list):
        highlights = []
    highlights = [_safe_text(item) for item in highlights if _safe_text(item)]

    return {
        "title": title,
        "summary": summary,
        "highlights": highlights[:6],
        "content_markdown": content_markdown,
    }


def _save_generated_resource(
    user_id: int,
    syllabus_id: int,
    resource_type: str,
    week_indices: List[int],
    resource_payload: Dict[str, Any],
) -> Dict[str, Any]:
    root = _resource_root(user_id, syllabus_id)
    os.makedirs(root, exist_ok=True)
    timestamp = int(time.time())
    type_def = RESOURCE_TYPE_DEFS[resource_type]
    week_label = "-".join(str(item) for item in week_indices)
    file_name = f"{resource_type}_weeks_{week_label}_{timestamp}.{type_def['file_ext']}"
    file_id = add_file_task(
        root,
        file_name,
        file_bytes=resource_payload["content_markdown"].encode("utf-8"),
        upload_time=datetime.utcnow().isoformat(),
    )
    file_row = get_file_by_id(file_id)
    stored_path = getattr(file_row, "path", None) if file_row else os.path.join(root, file_name)
    filename = os.path.basename(stored_path) if stored_path else file_name

    entry = {
        "resource_id": f"{resource_type}_{timestamp}",
        "resource_type": resource_type,
        "resource_label": type_def["label"],
        "title": resource_payload["title"],
        "summary": resource_payload["summary"],
        "highlights": resource_payload["highlights"],
        "status": "completed",
        "week_indices": week_indices,
        "generated_at": datetime.utcnow().isoformat(),
        "file_id": file_id,
        "filename": filename,
        "path": stored_path,
    }
    return entry


def _build_resource_response_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    path = entry.get("path")
    content = ""
    if isinstance(path, str) and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            content = ""
    return {
        "resource_id": entry.get("resource_id"),
        "resource_type": entry.get("resource_type"),
        "resource_label": entry.get("resource_label"),
        "title": entry.get("title"),
        "summary": entry.get("summary"),
        "highlights": entry.get("highlights") or [],
        "status": entry.get("status") or "completed",
        "week_indices": entry.get("week_indices") or [],
        "generated_at": entry.get("generated_at"),
        "file_id": entry.get("file_id"),
        "filename": entry.get("filename"),
        "preview": content[:800],
        "content": content,
    }


def list_generated_resources(user_id: int, syllabus_id: int) -> List[Dict[str, Any]]:
    items = _load_manifest(user_id, syllabus_id)
    items.sort(key=lambda item: _safe_text(item.get("generated_at")), reverse=True)
    return [_build_resource_response_entry(item) for item in items]


def generate_learning_resources(
    user_id: int,
    syllabus_id: int,
    week_indices: List[int],
    resource_types: List[str],
) -> Dict[str, Any]:
    user = get_user_by_id(user_id)
    syllabus = get_syllabus_by_id(syllabus_id)
    if not user or not syllabus:
        raise ValueError("invalid user_id or syllabus_id")

    selected_types = [item for item in resource_types if item in RESOURCE_TYPE_DEFS]
    selected_weeks = _normalize_int_list(week_indices)
    if not selected_types:
        raise ValueError("missing resource_types")
    if not selected_weeks:
        raise ValueError("missing week_indices")

    personal_syllabus = _ensure_personal_syllabus(user_id, syllabus_id)
    syllabus_json = _load_syllabus_json(syllabus_id)
    if not isinstance(personal_syllabus, dict) or not isinstance(syllabus_json, dict):
        raise ValueError("personal syllabus or syllabus content not ready")

    week_contexts = _build_week_context(personal_syllabus, syllabus_json, selected_weeks)
    if not week_contexts:
        raise ValueError("no valid week context found")

    from tasks.learning_profile_task import build_learning_profile

    profile = None
    try:
        profile = build_learning_profile(user_id, syllabus_id)
    except Exception:
        profile = None
    profile_summary = _build_personalization_summary(profile)

    manifest_items = _load_manifest(user_id, syllabus_id)
    generated_entries: List[Dict[str, Any]] = []

    for resource_type in selected_types:
        try:
            resource_payload = _generate_single_resource(resource_type, week_contexts, profile_summary)
            entry = _save_generated_resource(user_id, syllabus_id, resource_type, selected_weeks, resource_payload)
            manifest_items.insert(0, entry)
            generated_entries.append(_build_resource_response_entry(entry))
        except Exception as exc:
            generated_entries.append({
                "resource_id": f"{resource_type}_failed_{int(time.time())}",
                "resource_type": resource_type,
                "resource_label": RESOURCE_TYPE_DEFS[resource_type]["label"],
                "title": f"{RESOURCE_TYPE_DEFS[resource_type]['label']}生成失败",
                "summary": _safe_text(exc) or "generation failed",
                "highlights": [],
                "status": "failed",
                "week_indices": selected_weeks,
                "generated_at": datetime.utcnow().isoformat(),
                "file_id": None,
                "filename": None,
                "preview": "",
                "content": "",
            })

    _save_manifest(user_id, syllabus_id, manifest_items[:60])
    return {
        "resources": generated_entries,
        "profile_summary": profile_summary,
    }
