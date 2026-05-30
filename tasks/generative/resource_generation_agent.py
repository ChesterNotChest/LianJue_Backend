"""Resource generation Agent internals.

Architecture in the current stage:

resource_generation_agent
    -> resource_planning_agent (as a callable tool)
    -> file persistence tool set in ``tasks.generative.resource_persistence``

The total agent is intentionally excluded here. The fixed input payload for
this stage is a user-centric request describing:

- student question
- requested resource types
- optional syllabus / graph / retrieval context
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from config import LITELLM_MODEL_CONFIGS
from . import resource_planning_agent as planning_task
from tasks.generative.contracts import (
    GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
    GENERATIVE_DOCUMENT_SCHEMA_VERSION,
    GENERATIVE_PPT_SCHEMA_VERSION,
    GENERATIVE_QUIZ_SCHEMA_VERSION,
)
from tasks.generative.resource_persistence import persist_generated_resource
from tasks.generative.storage import (
    normalize_positive_int as _normalize_positive_int,
    normalize_resource_type as _normalize_resource_type,
)


DEFAULT_RESOURCE_TYPES = ("documents", "mindmap", "quiz")
MODEL_TIERS = ("cheap", "standard", "strong")
GENERAL_MODEL_KEYS_BY_TIER = {
    "cheap": ("text_cheap", "deepseek_text", "text_deepseek", "deepseek_chat", "text"),
    "standard": ("text_standard", "text", "text_cheap", "deepseek_text", "text_strong"),
    "strong": ("text_strong", "text", "text_standard", "text_cheap"),
}
PPT_MODEL_KEYS_BY_TIER = {
    "cheap": (
        "ppt_text_cheap",
        "ppt_text",
        "text_cheap",
        "deepseek_text",
        "text_deepseek",
        "deepseek_chat",
        "text",
    ),
    "standard": (
        "ppt_text",
        "text_standard",
        "text",
        "text_cheap",
        "deepseek_text",
    ),
    "strong": (
        "ppt_text_strong",
        "ppt_text",
        "text_strong",
        "text",
        "text_standard",
    ),
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: List[str] = []
    for item in items:
        text = _safe_text(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _clip_words(text: str, max_chars: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max(0, max_chars - 1)].rstrip() + "…"


def _compact_ppt_body(text: str, max_chars: int = 100) -> str:
    compact = " ".join(str(text or "").split())
    if not compact:
        return ""
    sentence_parts = []
    current = []
    for char in compact:
        current.append(char)
        if char in "。！？!?":
            sentence = "".join(current).strip()
            if sentence:
                sentence_parts.append(sentence)
            current = []
        if len(sentence_parts) >= 2:
            break
    if sentence_parts:
        compact = "".join(sentence_parts)
    return _clip_words(compact, max_chars)


def _normalize_ppt_bullets(bullets: List[str], topic: str) -> List[str]:
    normalized = [_clip_words(item, 96) for item in bullets if _safe_text(item)]
    fallback_items = [
        f"围绕 {topic} 提炼核心判断",
        "保留可复习的原因、方法或例子",
        "避免只记结论，关注适用条件",
    ]
    for item in fallback_items:
        if len(normalized) >= 3:
            break
        if item not in normalized:
            normalized.append(item)
    return normalized[:5]


def _ppt_placeholder_visual_hint(index: int, title: str) -> str:
    if index == 1:
        return "标题区 + 主题区 + 学习目标区"
    if any(keyword in title for keyword in ("总结", "回顾", "自测", "检查")):
        return "标题区 + 要点区 + 复习提示区"
    return "标题区 + 导语区 + 要点区"


def _build_ppt_cover_slide(request_payload: dict, generated: dict) -> dict:
    title = _safe_text(generated.get("title")) or f"{request_payload['topic']} 复习课件"
    learning_goal = _safe_text(request_payload.get("learning_goal"))
    topic = _safe_text(request_payload.get("topic")) or title
    return {
        "slide_index": 1,
        "title": title,
        "body": f"本课件围绕 {topic} 展开，帮助你快速定位问题、理解原因并完成复习。",
        "bullets": _normalize_ppt_bullets(
            [
                topic,
                learning_goal or "围绕学生问题展开定向复习",
                "按问题、机制、策略和自测顺序阅读",
            ],
            topic,
        ),
        "speaker_notes": "",
        "visual_hint": "标题区 + 主题区 + 学习目标区",
        "slide_role": "cover",
        "key_takeaway": "先让学生知道这份课件要解决什么问题。",
    }


def _normalize_ppt_speaker_notes(value: Any) -> str:
    notes = _safe_text(value)
    if not notes:
        return ""
    useful_markers = ("易错", "注意", "误区", "避免", "不要", "提醒", "区分", "常见错误")
    if not any(marker in notes for marker in useful_markers):
        return ""
    return _clip_words(notes, 100)


def _normalize_int_list(value: Any) -> List[int]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: List[int] = []
    for item in items:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in normalized:
            normalized.append(number)
    return normalized


def _extract_json_object(raw_text: Any) -> Dict[str, Any]:
    text = _safe_text(raw_text)
    if not text:
        raise ValueError("empty LLM response")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response does not contain a valid JSON object")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must decode to a JSON object")
    return parsed


def _derive_topic_from_question(question: str) -> str:
    compact = " ".join(_safe_text(question).split())
    if not compact:
        return "generated_resource"
    return compact[:48]


def normalize_generation_request(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    user_id = _normalize_positive_int(payload.get("user_id"), "user_id")
    question = _safe_text(payload.get("question") or payload.get("student_question"))
    if not question:
        raise ValueError("question is required")

    resource_types_raw = payload.get("resource_types")
    if resource_types_raw is None:
        resource_types_raw = payload.get("resource_type") or list(DEFAULT_RESOURCE_TYPES)
    resource_types = []
    for item in (resource_types_raw if isinstance(resource_types_raw, list) else [resource_types_raw]):
        resource_type = _normalize_resource_type(item)
        if resource_type not in resource_types:
            resource_types.append(resource_type)
    if not resource_types:
        raise ValueError("resource_types is required")

    syllabus_id = payload.get("syllabus_id")
    if syllabus_id not in (None, ""):
        syllabus_id = _normalize_positive_int(syllabus_id, "syllabus_id")
    else:
        syllabus_id = None

    retrieval_context = payload.get("retrieval_context")
    if not isinstance(retrieval_context, dict):
        retrieval_context = {}

    topic = _safe_text(payload.get("topic")) or _derive_topic_from_question(question)
    normalized = {
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "question": question,
        "topic": topic,
        "subject": _safe_text(payload.get("subject")),
        "graph_name": _safe_text(payload.get("graph_name")),
        "resource_types": resource_types,
        "selected_weeks": _normalize_int_list(payload.get("selected_weeks") or payload.get("week_indices")),
        "knowledge_items": _normalize_str_list(payload.get("knowledge_items")),
        "weak_points": _normalize_str_list(payload.get("weak_points")),
        "learning_goal": _safe_text(payload.get("learning_goal")),
        "profile_snapshot": payload.get("profile_snapshot") if isinstance(payload.get("profile_snapshot"), dict) else {},
        "retrieval_context": retrieval_context,
        "generation_requirements": payload.get("generation_requirements") if isinstance(payload.get("generation_requirements"), dict) else {},
    }
    if not normalized["knowledge_items"]:
        normalized["knowledge_items"] = normalized["weak_points"][:]
    return normalized


def build_single_resource_payload(request_payload: dict, resource_type: str) -> dict:
    normalized_type = _normalize_resource_type(resource_type)
    payload = dict(request_payload)
    payload["resource_type"] = normalized_type
    if normalized_type == "mindmap" and not payload.get("knowledge_items"):
        payload["knowledge_items"] = payload.get("weak_points") or [payload["topic"]]
    return payload


class LLMResourceGenerationAgent:
    """Default generation agent that turns planning output into typed resource JSON."""

    def __init__(self, model: Any = None) -> None:
        self.model = model or self._load_default_model()
        self._model_cache: Dict[str, Any] = {"text": self.model}

    @staticmethod
    def _load_default_model() -> Any:
        from utils.llm_utils import get_model_instance

        return get_model_instance()

    @staticmethod
    def _build_text_only_model(model_key: str) -> Any:
        from knowlion.multi_model_litellm import LitellmMultiModel

        model_config = LITELLM_MODEL_CONFIGS.get(model_key)
        if not isinstance(model_config, dict):
            raise ValueError(f"model config {model_key} is unavailable")
        return LitellmMultiModel({"text": model_config})

    def _resolve_model_tier(self, resource_type: str, request_payload: dict) -> str:
        requirements = request_payload.get("generation_requirements") if isinstance(request_payload, dict) else {}
        requirements = requirements if isinstance(requirements, dict) else {}

        explicit_tier = _safe_text(
            requirements.get("model_tier")
            or requirements.get("llm_tier")
            or (requirements.get("ppt_model_tier") if resource_type == "ppt" else None)
        ).lower()
        if explicit_tier in MODEL_TIERS:
            return explicit_tier

        # Default to the cheapest tier first so resource generation can prefer low-cost DeepSeek-like models.
        return "cheap"

    def _candidate_model_keys(self, resource_type: str, tier: str) -> tuple[str, ...]:
        normalized_tier = tier if tier in MODEL_TIERS else "cheap"
        if resource_type == "ppt":
            return PPT_MODEL_KEYS_BY_TIER[normalized_tier]
        return GENERAL_MODEL_KEYS_BY_TIER[normalized_tier]

    def _resolve_model_key(self, resource_type: str, request_payload: dict) -> str:
        requirements = request_payload.get("generation_requirements") if isinstance(request_payload, dict) else {}
        requirements = requirements if isinstance(requirements, dict) else {}

        explicit_model_key = _safe_text(requirements.get("model_key") or requirements.get("llm_model_key"))
        if explicit_model_key and explicit_model_key in LITELLM_MODEL_CONFIGS:
            return explicit_model_key

        if resource_type == "ppt":
            ppt_model_key = _safe_text(requirements.get("ppt_model_key"))
            if ppt_model_key and ppt_model_key in LITELLM_MODEL_CONFIGS:
                return ppt_model_key
        tier = self._resolve_model_tier(resource_type, request_payload)
        for candidate in self._candidate_model_keys(resource_type, tier):
            if candidate in LITELLM_MODEL_CONFIGS:
                return candidate
        return "text"

    def _get_model_for_resource_type(self, resource_type: str, request_payload: dict) -> Any:
        model_key = self._resolve_model_key(resource_type, request_payload)
        if model_key in self._model_cache:
            return self._model_cache[model_key]
        self._model_cache[model_key] = self._build_text_only_model(model_key)
        return self._model_cache[model_key]

    def _call_json(
        self,
        task_name: str,
        request_payload: dict,
        planning_bundle: dict,
        required_keys: List[str],
        *,
        system_prompt_override: Optional[str] = None,
    ) -> dict:
        system_prompt = system_prompt_override or (
            "你是联觉系统的资源生成agent。"
            "你会收到学生问题、资源类型、规划结果、检索资料和草稿。"
            "你只返回一个合法 JSON 对象，不要输出 Markdown 代码块，不要输出解释。"
        )
        user_prompt = json.dumps(
            {
                "task": task_name,
                "student_question": request_payload.get("question"),
                "topic": request_payload.get("topic"),
                "resource_type": request_payload.get("resource_type"),
                "learning_goal": request_payload.get("learning_goal"),
                "weak_points": request_payload.get("weak_points") or [],
                "knowledge_items": request_payload.get("knowledge_items") or [],
                "selected_weeks": request_payload.get("selected_weeks") or [],
                "generation_requirements": request_payload.get("generation_requirements") if isinstance(request_payload.get("generation_requirements"), dict) else {},
                "required_keys": required_keys,
                "planning_bundle": {
                    "plan": planning_bundle.get("plan") if isinstance(planning_bundle.get("plan"), dict) else {},
                    "draft": planning_bundle.get("draft") if isinstance(planning_bundle.get("draft"), dict) else {},
                    "retrieval_context": planning_bundle.get("retrieval_context") if isinstance(planning_bundle.get("retrieval_context"), dict) else {},
                },
            },
            ensure_ascii=False,
        )
        model = self._get_model_for_resource_type(
            _safe_text(request_payload.get("resource_type")) or task_name,
            request_payload,
        )
        raw = model.call_text_model(system_prompt, user_prompt, stream=False)
        return _extract_json_object(raw)

    def _generate_document_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        document_system_prompt = (
            "你是联觉系统里的学生学习文档生成 agent。"
            "documents 资源可以比 PPT 更完整、更复杂，但复杂度必须体现在学习结构上，而不是堆砌长段落。"
            "请生成一份适合学生独立阅读和复习的 Markdown 文档 JSON。"
            "sections 必须使用清晰且不重复的 heading，避免连续使用“知识点说明”。"
            "优先覆盖这些章节：学习目标、问题背景、核心概念、机制原理、方法步骤、例子/案例、常见误区、自测清单、复习总结。"
            "每个 section 的 body 可以比 PPT 更充分，建议 1 到 3 段，必须包含具体解释、判断依据或操作建议。"
            "section 可选包含 key_points、examples、pitfalls、checklist、evidence 字段；这些字段应为字符串列表。"
            "如果检索结果里有证据，要转写进 body 或 evidence，不要只泛泛引用。"
            "你只返回一个合法 JSON 对象，不要输出 Markdown，不要解释。"
        )
        generated = self._call_json(
            "generate_document",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "summary", "sections", "extension_reading"],
            system_prompt_override=document_system_prompt,
        )
        generated["schema_version"] = GENERATIVE_DOCUMENT_SCHEMA_VERSION
        generated["title"] = _safe_text(generated.get("title")) or f"{request_payload['topic']} 讲解文档"
        generated["topic"] = _safe_text(generated.get("topic")) or request_payload["topic"]
        generated["summary"] = _safe_text(generated.get("summary")) or f"围绕“{request_payload['question']}”的讲解资源。"

        preferred_headings = [
            "学习目标",
            "问题背景",
            "核心概念",
            "机制原理",
            "方法步骤",
            "例子/案例",
            "常见误区",
            "自测清单",
            "复习总结",
        ]
        sections = generated.get("sections") if isinstance(generated.get("sections"), list) else []
        normalized_sections = []
        used_headings = set()
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            heading = _safe_text(section.get("heading") or section.get("title"))
            if not heading or heading in used_headings or heading == "知识点说明":
                heading = preferred_headings[min(index - 1, len(preferred_headings) - 1)]
                suffix = 2
                while heading in used_headings:
                    heading = f"{preferred_headings[min(index - 1, len(preferred_headings) - 1)]} {suffix}"
                    suffix += 1
            used_headings.add(heading)
            body = _safe_text(section.get("body") or section.get("content")) or f"围绕 {request_payload['topic']} 展开说明。"
            normalized_sections.append(
                {
                    "heading": heading,
                    "body": body,
                    "key_points": _normalize_str_list(section.get("key_points") or section.get("points")),
                    "examples": _normalize_str_list(section.get("examples") or section.get("cases")),
                    "pitfalls": _normalize_str_list(section.get("pitfalls") or section.get("misconceptions")),
                    "checklist": _normalize_str_list(section.get("checklist") or section.get("self_check")),
                    "evidence": _normalize_str_list(section.get("evidence") or section.get("references")),
                }
            )
        if not normalized_sections:
            normalized_sections = [
                {
                    "heading": "问题背景",
                    "body": request_payload["question"],
                    "key_points": [f"当前问题聚焦 {request_payload['topic']}"],
                    "examples": [],
                    "pitfalls": [],
                    "checklist": [],
                    "evidence": [],
                },
                {
                    "heading": "核心说明",
                    "body": f"围绕 {request_payload['topic']} 展开说明。",
                    "key_points": [f"先理解 {request_payload['topic']} 的概念、原因和判断方法"],
                    "examples": [],
                    "pitfalls": [],
                    "checklist": [],
                    "evidence": [],
                },
            ]
        generated["sections"] = normalized_sections
        generated["extension_reading"] = generated.get("extension_reading") if isinstance(generated.get("extension_reading"), list) else []
        return generated

    def _generate_mindmap_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        mindmap_system_prompt = (
            "你是联觉系统里的思维导图资源生成 agent。"
            "你的职责是把学生问题、学习目标、薄弱点和检索证据转成 Mermaid mindmap JSON。"
            "mindmap 必须突出层级关系：中心主题 -> 核心概念/机制/方法/误区/练习方向。"
            "不要生成长段落，不要写成文档；每个节点应短、具体、可扫描。"
            "mermaid 必须以 mindmap 开头，root 必须对应当前 topic。"
            "nodes 可返回结构化节点列表，但 mermaid 是必填主产物。"
            "如果检索材料里有关键实体或路径，应转成分支或子节点。"
            "你只返回一个合法 JSON 对象，不要输出 Markdown，不要解释。"
        )
        generated = self._call_json(
            "generate_mindmap",
            request_payload,
            planning_bundle,
            ["title", "root", "nodes", "mermaid"],
            system_prompt_override=mindmap_system_prompt,
        )
        mermaid = _safe_text(generated.get("mermaid"))
        if not mermaid.startswith("mindmap"):
            lines = ["mindmap", f"  root(({request_payload['topic']}))"]
            for item in request_payload.get("knowledge_items") or request_payload.get("weak_points") or ["核心概念"]:
                lines.append(f"    {item}")
            mermaid = "\n".join(lines)
        return {
            "title": _safe_text(generated.get("title")) or f"{request_payload['topic']} 思维导图",
            "root": _safe_text(generated.get("root")) or request_payload["topic"],
            "nodes": generated.get("nodes") if isinstance(generated.get("nodes"), list) else [],
            "mermaid": mermaid,
        }

    def _generate_quiz_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        quiz_system_prompt = (
            "你是联觉系统里的练习题资源生成 agent。"
            "你的职责是根据学生问题、薄弱点、知识点和检索证据生成诊断型 quiz JSON。"
            "题目要检查理解和应用，不要只考术语记忆。"
            "questions 必须围绕当前 topic 和 weak_points，优先覆盖概念辨析、原因判断、策略选择和易错点。"
            "每道题必须包含 id、type、difficulty、stem、options、answer、explanation、knowledge_points。"
            "第一版统一使用 single_choice，options 必须恰好 4 个；answer 使用 A/B/C/D 中的一个。"
            "explanation 必须解释为什么正确选项成立，以及至少指出一个干扰项为什么不对。"
            "你只返回一个合法 JSON 对象，不要输出 Markdown，不要解释。"
        )
        generated = self._call_json(
            "generate_quiz",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "questions"],
            system_prompt_override=quiz_system_prompt,
        )
        generated["schema_version"] = GENERATIVE_QUIZ_SCHEMA_VERSION
        generated["title"] = _safe_text(generated.get("title")) or f"{request_payload['topic']} 习题"
        generated["topic"] = _safe_text(generated.get("topic")) or request_payload["topic"]

        questions = generated.get("questions") if isinstance(generated.get("questions"), list) else []
        normalized_questions = []
        for index, question in enumerate(questions, start=1):
            if not isinstance(question, dict):
                continue
            options = question.get("options") if isinstance(question.get("options"), list) else []
            if len(options) < 4:
                options = ["避免热点并保证可区分", "扩大端口规模", "删除现有图谱", "关闭检索功能"]
            normalized_questions.append(
                {
                    "id": _safe_text(question.get("id")) or f"q{index}",
                    "type": "single_choice",
                    "difficulty": _safe_text(question.get("difficulty")) or "medium",
                    "stem": _safe_text(question.get("stem") or question.get("question")) or f"围绕“{request_payload['question']}”最关键的理解是什么？",
                    "options": options[:4],
                    "answer": _safe_text(question.get("answer")) or "A",
                    "explanation": _safe_text(question.get("explanation")) or "依据规划草稿中的核心说明。",
                    "knowledge_points": _normalize_str_list(question.get("knowledge_points")) or request_payload.get("knowledge_items") or [request_payload["topic"]],
                }
            )
        if not normalized_questions:
            normalized_questions = [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "difficulty": "medium",
                    "stem": f"围绕“{request_payload['question']}”最关键的理解是什么？",
                    "options": ["避免热点并保证可区分", "扩大端口规模", "删除现有图谱", "关闭检索功能"],
                    "answer": "A",
                    "explanation": "依据规划草稿中的核心说明。",
                    "knowledge_points": request_payload.get("knowledge_items") or [request_payload["topic"]],
                }
            ]
        generated["questions"] = normalized_questions
        return generated

    def _generate_coding_practice_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        coding_system_prompt = (
            "你是联觉系统里的代码练习资源生成 agent。"
            "你的职责是把学生问题和检索证据转成一个最小可运行的 coding_practice JSON。"
            "练习必须服务于当前 topic，不要生成与知识点无关的通用代码。"
            "优先生成 python；如果确实需要其他语言，必须保证 code_files 和 run_guide 一致。"
            "steps 要按学生操作顺序描述：理解目标、阅读/补全代码、运行、观察输出、反思知识点。"
            "code_files 必须包含 path、purpose、content；run_guide 必须包含 entry_file、command、expected_output。"
            "代码应尽量短小、可读、可直接运行，避免依赖外部服务或大型包。"
            "expected_output 应能体现练习目标，不要只写 success。"
            "你只返回一个合法 JSON 对象，不要输出 Markdown，不要解释。"
        )
        generated = self._call_json(
            "generate_coding_practice",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "language", "summary", "learning_objectives", "steps", "code_files", "run_guide"],
            system_prompt_override=coding_system_prompt,
        )
        generated["schema_version"] = GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION
        generated["title"] = _safe_text(generated.get("title")) or f"{request_payload['topic']} 实操案例"
        generated["topic"] = _safe_text(generated.get("topic")) or request_payload["topic"]
        generated["language"] = _safe_text(generated.get("language")) or "python"
        generated["summary"] = _safe_text(generated.get("summary")) or f"围绕 {request_payload['topic']} 的最小可运行案例。"
        generated["learning_objectives"] = _normalize_str_list(generated.get("learning_objectives")) or [f"理解 {request_payload['topic']}"]
        generated["steps"] = generated.get("steps") if isinstance(generated.get("steps"), list) else [
            {"step_index": 1, "title": "阅读目标", "instruction": f"先理解问题：{request_payload['question']}"},
            {"step_index": 2, "title": "运行案例", "instruction": "执行示例代码并观察输出。"},
        ]
        generated["code_files"] = generated.get("code_files") if isinstance(generated.get("code_files"), list) else [
            {
                "path": "code/main.py",
                "purpose": "entry",
                "content": f"def explain():\n    return 'resource for {request_payload['topic']}'\n\nprint(explain())\n",
            }
        ]
        generated["run_guide"] = generated.get("run_guide") if isinstance(generated.get("run_guide"), dict) else {
            "entry_file": "code/main.py",
            "command": "python code/main.py",
            "expected_output": request_payload["topic"],
        }
        return generated

    def _generate_ppt_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        requirements = request_payload.get("generation_requirements") if isinstance(request_payload.get("generation_requirements"), dict) else {}
        slide_target = int(requirements.get("slide_count_target") or requirements.get("slide_count_limit") or 8)
        slide_target = min(max(slide_target, 6), 12)
        ppt_system_prompt = (
            "你是联觉系统里的学生自学复习 PPT 设计 agent。"
            "你的职责是把学生问题、检索证据、知识点和学习目标，转成一份内容扎实、层次分明、适合学生独立学习和复习的 PPT JSON。"
            "不要写空泛口号，不要只写标题。"
            "第一页必须是标题页/封面页，slide_role 必须为 cover；标题页只放课件标题、主题、学习目标和阅读导向，不讲具体知识点。"
            "每页都要有实质内容，每条 bullet 尽量具体，体现概念、原因、方法、例子或结论。"
            "body 必须是页面导语或核心判断，不是报告段落，也不是 speaker_notes。"
            "body 建议 35 到 80 个中文字符，最多 1 到 2 句，用来提示本页看什么。"
            "每页 bullets 必须有 3 到 5 条结构化要点，每条尽量具体，承载原因、方法、例子、条件或结论。"
            "优先生成以下结构中的大部分页面：学习目标、问题导入、概念澄清、机制/原理、对比分析、步骤/策略、例子/案例、自测提示、复习总结。"
            "不要生成 Q&A、答疑页或致谢页。"
            "slides 中每页必须包含 slide_index、title、body、bullets、visual_hint；speaker_notes 可为空或省略。"
            "speaker_notes 只在必要时添加，用于补充易错点或注意事项；不能承载正文重点，宁可不写。"
            "不要主动设计表格、复杂图表、时间线、流程箭头、复杂卡片或新增视觉组件。"
            "visual_hint 只能描述页面已有占位元素，例如“标题区 + 导语区 + 要点区”或“标题区 + 要点区 + 复习提示区”。"
            "复杂元素和长文本不可以共存；如果页面信息较多，必须通过 bullets 拆分，而不是拉长 body。"
            "如果检索结果里有证据，要把证据转写成课件内容，而不是忽略。"
            "你只返回一个合法 JSON 对象，不要输出 Markdown，不要解释。"
        )
        generated = self._call_json(
            "generate_ppt",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "summary", "theme", "slide_style", "slides"],
            system_prompt_override=ppt_system_prompt,
        )
        generated["schema_version"] = GENERATIVE_PPT_SCHEMA_VERSION
        generated["title"] = _safe_text(generated.get("title")) or f"{request_payload['topic']} 复习课件"
        generated["topic"] = _safe_text(generated.get("topic")) or request_payload["topic"]
        generated["summary"] = _safe_text(generated.get("summary")) or f"围绕“{request_payload['question']}”的结构化课件。"
        generated["theme"] = _safe_text(generated.get("theme")) or _safe_text(requirements.get("theme")) or "academic-rich"
        generated["slide_style"] = _safe_text(generated.get("slide_style")) or _safe_text(requirements.get("style")) or "study-review"
        raw_slides = generated.get("slides") if isinstance(generated.get("slides"), list) else []
        normalized_slides = []
        cover_slide = _build_ppt_cover_slide(request_payload, generated)
        for index, slide in enumerate(raw_slides, start=1):
            if not isinstance(slide, dict):
                continue
            title = _safe_text(slide.get("title") or slide.get("heading") or slide.get("name") or slide.get("type"))
            raw_bullets = slide.get("bullets")
            bullets = _normalize_str_list(raw_bullets) if isinstance(raw_bullets, list) else []
            if not bullets:
                content = slide.get("content")
                if isinstance(content, list):
                    bullets = _normalize_str_list(content)
                elif _safe_text(content):
                    bullets = [_safe_text(content)]
            if not title and bullets:
                title = f"要点 {index}"
            body = _safe_text(
                slide.get("body")
                or slide.get("paragraph")
                or slide.get("narrative")
                or slide.get("main_text")
                or slide.get("description")
            )
            if not body:
                content = slide.get("content")
                if _safe_text(content) and _safe_text(content) not in bullets:
                    body = _safe_text(content)
            role = _safe_text(slide.get("slide_role") or slide.get("role"))
            visual_hint = _safe_text(slide.get("visual_hint") or slide.get("type"))
            if not visual_hint:
                visual_hint = _ppt_placeholder_visual_hint(index, title)
            else:
                visual_hint = _ppt_placeholder_visual_hint(index, title)
            speaker_notes = _normalize_ppt_speaker_notes(slide.get("speaker_notes") or slide.get("notes"))
            if not body:
                if index == 1:
                    body = f"本页先定位学习问题，把它放回 {request_payload['topic']} 的知识框架中。"
                else:
                    body = f"本页给出“{title or request_payload['topic']}”的核心判断，再用要点补齐原因和方法。"
            normalized_slides.append(
                {
                    "slide_index": int(slide.get("slide_index") or index),
                    "title": title or f"第{index}页",
                    "body": _compact_ppt_body(body),
                    "bullets": _normalize_ppt_bullets(bullets, request_payload["topic"]),
                    "speaker_notes": speaker_notes,
                    "visual_hint": visual_hint,
                    "slide_role": role or ("cover" if index == 1 else "content"),
                    "key_takeaway": _safe_text(slide.get("key_takeaway") or slide.get("takeaway")),
                }
            )
        if len(normalized_slides) < 4:
            normalized_slides = [
                cover_slide,
                {
                    "slide_index": 2,
                    "title": "问题导入",
                    "body": "先从原始疑问切入，确认当前卡点来自概念、机制和应用场景的连接不足。",
                    "bullets": [
                        request_payload["question"],
                        "结合学习目标定位当前薄弱点。",
                        "明确为什么这个知识点容易出错。",
                    ],
                    "speaker_notes": "注意先用自己的话解释原始问题，再对照后续页面补齐理解。",
                    "visual_hint": "标题区 + 导语区 + 要点区",
                    "slide_role": "intro",
                    "key_takeaway": "先聚焦问题，再进入知识讲解。",
                },
                {
                    "slide_index": 3,
                    "title": "核心讲解",
                    "body": f"理解 {request_payload['topic']} 时，要同时回答概念、原因和判断方法三个问题。",
                    "bullets": [
                        f"围绕 {request_payload['topic']} 解释核心概念和机制。",
                        "结合检索资料说明常见误区与判断依据。",
                        "给出一条可复用的分析思路或设计原则。",
                    ],
                    "speaker_notes": "注意区分概念定义、机制原因和判断方法，不要混成一个结论。",
                    "visual_hint": "标题区 + 导语区 + 要点区",
                    "slide_role": "concept",
                    "key_takeaway": "不仅给结论，还要解释为什么。",
                },
                {
                    "slide_index": 4,
                    "title": "总结",
                    "body": "最后把关键结论收束为可复用的判断路径，方便后续练习时主动识别问题。",
                    "bullets": [
                        "回顾本资源的关键结论。",
                        "指出后续练习或复习方向。",
                        "把知识点与学生原问题闭环。",
                    ],
                    "speaker_notes": "",
                    "visual_hint": "标题区 + 要点区 + 复习提示区",
                    "slide_role": "summary",
                    "key_takeaway": "让学生带着清晰结论离开。",
                },
            ]

        normalized_slides = sorted(normalized_slides, key=lambda item: int(item.get("slide_index") or 0))
        if normalized_slides:
            first = normalized_slides[0]
            first_role = _safe_text(first.get("slide_role") or first.get("role")).lower()
            first_title = _safe_text(first.get("title"))
            is_cover = first_role == "cover" or any(keyword in first_title for keyword in ("封面", "标题页", "导入页"))
            if is_cover:
                first.update(
                    {
                        "slide_role": "cover",
                        "visual_hint": "标题区 + 主题区 + 学习目标区",
                    }
                )
                if not _safe_text(first.get("title")):
                    first["title"] = cover_slide["title"]
            else:
                normalized_slides.insert(0, cover_slide)
        else:
            normalized_slides = [cover_slide]
        for next_index, slide in enumerate(normalized_slides, start=1):
            slide["slide_index"] = next_index
        if len(normalized_slides) < slide_target:
            supplement_titles = [
                ("概念拆解", "标题区 + 导语区 + 要点区"),
                ("机制原理", "标题区 + 导语区 + 要点区"),
                ("对比分析", "标题区 + 导语区 + 要点区"),
                ("案例分析", "标题区 + 导语区 + 要点区"),
                ("复习总结", "标题区 + 要点区 + 复习提示区"),
            ]
            for title, visual_hint in supplement_titles:
                if len(normalized_slides) >= slide_target:
                    break
                normalized_slides.append(
                    {
                        "slide_index": len(normalized_slides) + 1,
                        "title": title,
                        "body": f"本页补充 {title} 视角，帮助把 {request_payload['topic']} 从结论变成可复习的方法。",
                        "bullets": _normalize_ppt_bullets([f"围绕 {request_payload['topic']} 补充 {title} 视角。", "结合当前薄弱点给出可回看的复习要点。"], request_payload["topic"]),
                        "speaker_notes": "",
                        "visual_hint": visual_hint,
                        "slide_role": "content",
                        "key_takeaway": "",
                    }
                )
        generated["slides"] = normalized_slides[:12]
        return generated

    def generate_resource_content(self, request_payload: dict, resource_type: str, planning_bundle: dict) -> dict:
        normalized_type = _normalize_resource_type(resource_type)
        if normalized_type == "documents":
            return self._generate_document_content(request_payload, planning_bundle)
        if normalized_type == "mindmap":
            return self._generate_mindmap_content(request_payload, planning_bundle)
        if normalized_type == "quiz":
            return self._generate_quiz_content(request_payload, planning_bundle)
        if normalized_type == "coding_practice":
            return self._generate_coding_practice_content(request_payload, planning_bundle)
        if normalized_type == "ppt":
            return self._generate_ppt_content(request_payload, planning_bundle)
        raise ValueError(f"resource_type {normalized_type} is not supported")


def _build_failed_resource_result(resource_type: str, topic: str, error_message: str, planning_trace: Optional[List[str]] = None) -> dict:
    return {
        "success": False,
        "resource_id": None,
        "resource_type": resource_type,
        "title": f"{topic} {resource_type} generation failed",
        "topic": topic,
        "status": "failed",
        "resource_dir": None,
        "validation": {
            "valid": False,
            "errors": [error_message],
            "warnings": [],
        },
        "planning_trace": planning_trace or [],
        "error_message": error_message,
        "error_code": "generation_failed",
    }


def _tool_invoke_resource_planning_agent(state: dict, resource_type: str, planning_agent: Any) -> dict:
    bundle = planning_task.run_resource_planning_agent(state["request"], resource_type, planning_agent=planning_agent)
    state["tool_trace"].append("invoke_resource_planning_agent")
    state["planning_results"][resource_type] = bundle
    return bundle


def _tool_persist_generated_resource(state: dict, resource_type: str, generated_content: dict) -> dict:
    payload = build_single_resource_payload(state["request"], resource_type)
    result = persist_generated_resource(payload, generated_content)
    state["tool_trace"].append("persist_generated_resource")
    return result


def generate_single_resource_from_request(
    request_payload: dict,
    resource_type: str,
    *,
    generation_agent: Any = None,
    planning_agent: Any = None,
) -> dict:
    normalized_request = normalize_generation_request(request_payload)
    if generation_agent is None:
        from tasks.generative.resource_agent_runtime import run_single_resource_generation_agent

        planner = planning_agent or planning_task.get_resource_planning_agent()
        agent_result = run_single_resource_generation_agent(
            normalized_request,
            resource_type,
            planning_agent=planner,
        )
        if agent_result.resource:
            persisted = dict(agent_result.resource)
            planning_bundle = agent_result.planning_bundle if isinstance(agent_result.planning_bundle, dict) else {}
            persisted["planning_trace"] = planning_bundle.get("tool_trace") or []
            persisted["tool_trace"] = agent_result.tool_trace[:]
            return persisted
        failed = _build_failed_resource_result(
            resource_type,
            normalized_request["topic"],
            agent_result.error_message or "resource generation agent did not persist a resource",
            planning_trace=[],
        )
        failed["tool_trace"] = agent_result.tool_trace[:]
        return failed

    agent = generation_agent or LLMResourceGenerationAgent()
    planner = planning_agent or planning_task.get_resource_planning_agent()

    state = {"request": normalized_request, "tool_trace": [], "planning_results": {}}
    planning_bundle = _tool_invoke_resource_planning_agent(state, resource_type, planner)
    generated_content = agent.generate_resource_content(
        build_single_resource_payload(normalized_request, resource_type),
        resource_type,
        planning_bundle,
    )
    persisted = _tool_persist_generated_resource(state, resource_type, generated_content)
    persisted["planning_trace"] = planning_bundle.get("tool_trace") or []
    persisted["tool_trace"] = state["tool_trace"][:]
    return persisted


def run_resource_generation_agent(
    request_payload: dict,
    *,
    generation_agent: Any = None,
    planning_agent: Any = None,
) -> dict:
    normalized_request = normalize_generation_request(request_payload)
    planner = planning_agent or planning_task.get_resource_planning_agent()

    state = {"request": normalized_request, "tool_trace": [], "planning_results": {}}
    resources = []
    for resource_type in normalized_request["resource_types"]:
        planning_trace: List[str] = []
        try:
            if generation_agent is None:
                from tasks.generative.resource_agent_runtime import run_single_resource_generation_agent

                agent_result = run_single_resource_generation_agent(
                    normalized_request,
                    resource_type,
                    planning_agent=planner,
                )
                planning_bundle = agent_result.planning_bundle if isinstance(agent_result.planning_bundle, dict) else {}
                planning_trace = planning_bundle.get("tool_trace") or []
                if not agent_result.resource:
                    raise RuntimeError(agent_result.error_message or "resource generation agent did not persist a resource")
                persisted = dict(agent_result.resource)
                persisted["tool_trace"] = agent_result.tool_trace[:]
                state["tool_trace"].extend(agent_result.tool_trace)
            else:
                planning_bundle = _tool_invoke_resource_planning_agent(state, resource_type, planner)
                planning_trace = planning_bundle.get("tool_trace") or []
                generated_content = generation_agent.generate_resource_content(
                    build_single_resource_payload(normalized_request, resource_type),
                    resource_type,
                    planning_bundle,
                )
                persisted = _tool_persist_generated_resource(state, resource_type, generated_content)
                persisted["tool_trace"] = state["tool_trace"][:]
            persisted["planning_trace"] = planning_trace
            resources.append(persisted)
        except Exception as exc:
            resources.append(
                _build_failed_resource_result(
                    resource_type,
                    normalized_request["topic"],
                    str(exc),
                    planning_trace=planning_trace,
                )
            )

    success_count = sum(1 for item in resources if item.get("success") is True)
    failed_count = len(resources) - success_count
    return {
        "success": failed_count == 0,
        "request": normalized_request,
        "resources": resources,
        "resource_count": len(resources),
        "success_count": success_count,
        "failed_count": failed_count,
        "tool_trace": state["tool_trace"],
        "error_message": "" if failed_count == 0 else f"{failed_count} resource(s) failed",
        "error_code": "" if failed_count == 0 else "partial_failure",
    }


def generate_resources_from_request(
    request_payload: dict,
    generation_agent: Any = None,
    planning_agent: Any = None,
) -> dict:
    return run_resource_generation_agent(
        request_payload,
        generation_agent=generation_agent,
        planning_agent=planning_agent,
    )
