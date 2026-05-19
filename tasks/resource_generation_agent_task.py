"""Resource generation agent task.

Architecture in the current stage:

resource_generation_agent
    -> resource_planning_agent (as a callable tool)
    -> file persistence tool set in ``tasks.generative_task``

The total agent is intentionally excluded here. The fixed input payload for
this stage is a user-centric request describing:

- student question
- requested resource types
- optional syllabus / graph / retrieval context
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tasks import generative_task
from tasks import resource_planning_agent_task as planning_task
from tasks.generative.storage import (
    normalize_positive_int as _normalize_positive_int,
    normalize_resource_type as _normalize_resource_type,
)


DEFAULT_RESOURCE_TYPES = ("documents", "mindmap", "quiz")


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

    @staticmethod
    def _load_default_model() -> Any:
        from utils.llm_utils import get_model_instance

        return get_model_instance()

    def _call_json(
        self,
        task_name: str,
        request_payload: dict,
        planning_bundle: dict,
        required_keys: List[str],
    ) -> dict:
        system_prompt = (
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
                "required_keys": required_keys,
                "planning_bundle": {
                    "plan": planning_bundle.get("plan") if isinstance(planning_bundle.get("plan"), dict) else {},
                    "draft": planning_bundle.get("draft") if isinstance(planning_bundle.get("draft"), dict) else {},
                    "retrieval_context": planning_bundle.get("retrieval_context") if isinstance(planning_bundle.get("retrieval_context"), dict) else {},
                },
            },
            ensure_ascii=False,
        )
        raw = self.model.call_text_model(system_prompt, user_prompt, stream=False)
        return _extract_json_object(raw)

    def _generate_document_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        generated = self._call_json(
            "generate_document",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "summary", "sections", "extension_reading"],
        )
        generated["schema_version"] = generative_task.GENERATIVE_DOCUMENT_SCHEMA_VERSION
        generated["title"] = _safe_text(generated.get("title")) or f"{request_payload['topic']} 讲解文档"
        generated["topic"] = _safe_text(generated.get("topic")) or request_payload["topic"]
        generated["summary"] = _safe_text(generated.get("summary")) or f"围绕“{request_payload['question']}”的讲解资源。"

        sections = generated.get("sections") if isinstance(generated.get("sections"), list) else []
        normalized_sections = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = _safe_text(section.get("heading") or section.get("title")) or "知识点说明"
            body = _safe_text(section.get("body") or section.get("content")) or f"围绕 {request_payload['topic']} 展开说明。"
            normalized_sections.append({"heading": heading, "body": body})
        if not normalized_sections:
            normalized_sections = [
                {"heading": "问题背景", "body": request_payload["question"]},
                {"heading": "核心说明", "body": f"围绕 {request_payload['topic']} 展开说明。"},
            ]
        generated["sections"] = normalized_sections
        generated["extension_reading"] = generated.get("extension_reading") if isinstance(generated.get("extension_reading"), list) else []
        return generated

    def _generate_mindmap_content(self, request_payload: dict, planning_bundle: dict) -> dict:
        generated = self._call_json(
            "generate_mindmap",
            request_payload,
            planning_bundle,
            ["title", "root", "nodes", "mermaid"],
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
        generated = self._call_json(
            "generate_quiz",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "questions"],
        )
        generated["schema_version"] = generative_task.GENERATIVE_QUIZ_SCHEMA_VERSION
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
        generated = self._call_json(
            "generate_coding_practice",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "language", "summary", "learning_objectives", "steps", "code_files", "run_guide"],
        )
        generated["schema_version"] = generative_task.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION
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
        generated = self._call_json(
            "generate_ppt",
            request_payload,
            planning_bundle,
            ["schema_version", "title", "topic", "summary", "theme", "slide_style", "slides"],
        )
        generated["schema_version"] = generative_task.GENERATIVE_PPT_SCHEMA_VERSION
        generated["title"] = _safe_text(generated.get("title")) or f"{request_payload['topic']} 教学课件"
        generated["topic"] = _safe_text(generated.get("topic")) or request_payload["topic"]
        generated["summary"] = _safe_text(generated.get("summary")) or f"围绕“{request_payload['question']}”的结构化课件。"
        generated["theme"] = _safe_text(generated.get("theme")) or "academic-clean"
        generated["slide_style"] = _safe_text(generated.get("slide_style")) or "teaching-outline"
        raw_slides = generated.get("slides") if isinstance(generated.get("slides"), list) else []
        normalized_slides = []
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
            normalized_slides.append(
                {
                    "slide_index": int(slide.get("slide_index") or index),
                    "title": title or f"第{index}页",
                    "bullets": bullets or [request_payload["topic"]],
                    "speaker_notes": _safe_text(slide.get("speaker_notes") or slide.get("notes") or slide.get("content"))
                    or "围绕当前页要点进行讲解。",
                    "visual_hint": _safe_text(slide.get("visual_hint") or slide.get("type"))
                    or "标题 + 要点列表",
                }
            )
        generated["slides"] = normalized_slides or [
            {
                "slide_index": 1,
                "title": "学习目标",
                "bullets": [request_payload["question"], request_payload["topic"]],
                "speaker_notes": "先说明本次资源围绕的问题。",
                "visual_hint": "标题 + 目标列表",
            }
        ]
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
    result = generative_task.persist_generated_resource(payload, generated_content)
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
    agent = generation_agent or LLMResourceGenerationAgent()
    planner = planning_agent or planning_task.get_resource_planning_agent()

    state = {"request": normalized_request, "tool_trace": [], "planning_results": {}}
    resources = []
    for resource_type in normalized_request["resource_types"]:
        planning_trace: List[str] = []
        try:
            planning_bundle = _tool_invoke_resource_planning_agent(state, resource_type, planner)
            planning_trace = planning_bundle.get("tool_trace") or []
            generated_content = agent.generate_resource_content(
                build_single_resource_payload(normalized_request, resource_type),
                resource_type,
                planning_bundle,
            )
            persisted = _tool_persist_generated_resource(state, resource_type, generated_content)
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
