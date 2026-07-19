"""Resource planning Agent internals.

Atomic tool responsibilities in this stage:

- read generation plan
- write generation plan
- retrieve materials
- read generation draft
- write generation draft
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


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


def _clip_text_items(value: Any, *, limit: int = 4, max_chars: int = 160) -> List[str]:
    items = value if isinstance(value, list) else ([] if value is None else [value])
    clipped: List[str] = []
    for item in items:
        text = _safe_text(item)
        if not text:
            continue
        if len(text) > max_chars:
            text = text[: max(0, max_chars - 3)].rstrip() + "..."
        if text not in clipped:
            clipped.append(text)
        if len(clipped) >= limit:
            break
    return clipped


def _tool_read_generation_plan(state: dict, resource_type: str) -> dict:
    state["tool_trace"].append("read_generation_plan")
    return dict(state["plans"].get(resource_type) or {})


def _tool_write_generation_plan(state: dict, resource_type: str, plan: dict) -> dict:
    state["tool_trace"].append("write_generation_plan")
    state["plans"][resource_type] = dict(plan or {})
    return dict(state["plans"][resource_type])


def _tool_retrieve_generation_materials(
    state: dict,
    resource_type: str,
    search_fn: Optional[Callable[..., Dict[str, Any]]],
    *,
    query_override: str = "",
) -> dict:
    state["tool_trace"].append("retrieve_generation_materials")
    existing = state["request"].get("retrieval_context")
    if isinstance(existing, dict) and (
        existing.get("paragraphs")
        or existing.get("results")
        or existing.get("success") is False
    ):
        return existing

    graph_name = _safe_text(state["request"].get("graph_name"))
    if not search_fn or not graph_name:
        return {"success": False, "paragraphs": [], "reasoning_paths": [], "error": ""}

    if query_override:
        query = query_override
    else:
        query_parts = [
            state["request"].get("question"),
            state["request"].get("topic"),
            " ".join(_normalize_str_list(state["request"].get("knowledge_items"))),
            " ".join(_normalize_str_list(state["request"].get("weak_points"))),
            resource_type,
        ]
        query = " ".join(_safe_text(item) for item in query_parts if _safe_text(item))
    if not query:
        return {"success": False, "paragraphs": [], "reasoning_paths": [], "error": ""}
    return search_fn(query, graph_name=graph_name, top_k=8)


def _tool_read_generation_draft(state: dict, resource_type: str) -> dict:
    state["tool_trace"].append("read_generation_draft")
    return dict(state["drafts"].get(resource_type) or {})


def _tool_write_generation_draft(state: dict, resource_type: str, draft: dict) -> dict:
    state["tool_trace"].append("write_generation_draft")
    state["drafts"][resource_type] = dict(draft or {})
    return dict(state["drafts"][resource_type])


def _build_default_plan(request_payload: dict, resource_type: str) -> dict:
    return {
        "resource_type": resource_type,
        "topic": request_payload.get("topic"),
        "student_question": request_payload.get("question"),
        "selected_weeks": request_payload.get("selected_weeks") or [],
        "knowledge_items": request_payload.get("knowledge_items") or [],
        "weak_points": request_payload.get("weak_points") or [],
        "learning_goal": request_payload.get("learning_goal"),
        "objective": f"生成一份围绕“{request_payload.get('question')}”的 {resource_type} 资源",
    }


def _build_default_draft(request_payload: dict, resource_type: str, plan: dict, retrieval_context: dict) -> dict:
    paragraphs = retrieval_context.get("paragraphs") if isinstance(retrieval_context, dict) else []
    paragraphs = paragraphs if isinstance(paragraphs, list) else []
    evidence = [str(item).strip() for item in paragraphs[:8] if str(item).strip()]
    key_concepts = _normalize_str_list(request_payload.get("knowledge_items")) + _normalize_str_list(request_payload.get("weak_points"))
    if not key_concepts:
        key_concepts = [_safe_text(request_payload.get("topic"))]
    outline = [
        "问题背景",
        "核心知识点",
        "重点难点",
        "针对性练习或结构梳理",
    ]
    learning_brief = {
        "topic": request_payload.get("topic"),
        "student_question": request_payload.get("question"),
        "learning_goal": request_payload.get("learning_goal") or plan.get("objective"),
        "resource_type": resource_type,
        "key_concepts": _clip_text_items(key_concepts, limit=8, max_chars=80),
        "weak_points": _clip_text_items(request_payload.get("weak_points"), limit=5, max_chars=80),
        "outline": outline,
        "evidence_summaries": _clip_text_items(evidence, limit=8, max_chars=500),
        "generation_constraints": {
            "max_slides": (request_payload.get("generation_requirements") or {}).get("max_slides", 6)
            if isinstance(request_payload.get("generation_requirements"), dict)
            else 6,
            "quiz_count": (request_payload.get("generation_requirements") or {}).get("quiz_count", 5)
            if isinstance(request_payload.get("generation_requirements"), dict)
            else 5,
        },
    }
    return {
        "resource_type": resource_type,
        "title": f"{request_payload.get('topic')} {resource_type}",
        "summary": f"围绕学生问题“{request_payload.get('question')}”的草稿。",
        "outline": outline,
        "evidence": evidence,
        "plan_objective": plan.get("objective"),
        "learning_brief": learning_brief,
    }


class ResourcePlanningAgent:
    def __init__(self, search_fn: Optional[Callable[..., Dict[str, Any]]] = None) -> None:
        self.search_fn = search_fn
        self._sessions: Dict[str, dict] = {}

    def _get_search_fn(self) -> Optional[Callable[..., Dict[str, Any]]]:
        if self.search_fn is not None:
            return self.search_fn
        try:
            from tasks.common.search_tool import search_tool
        except Exception:
            return None
        self.search_fn = search_tool
        return self.search_fn

    def _get_session(self, request_payload: dict) -> dict:
        session_key = f"{request_payload.get('user_id')}::{request_payload.get('question')}::{request_payload.get('topic')}"
        if session_key not in self._sessions:
            self._sessions[session_key] = {
                "request": request_payload,
                "plans": {},
                "drafts": {},
                "tool_trace": [],
            }
        else:
            self._sessions[session_key]["request"] = request_payload
            self._sessions[session_key]["tool_trace"] = []
        return self._sessions[session_key]

    def run(self, request_payload: dict, resource_type: str) -> dict:
        state = self._get_session(request_payload)

        plan = _tool_read_generation_plan(state, resource_type)
        if not plan:
            plan = _build_default_plan(request_payload, resource_type)
            plan = _tool_write_generation_plan(state, resource_type, plan)

        retrieval_context = _tool_retrieve_generation_materials(
            state,
            resource_type,
            self._get_search_fn(),
        )

        draft = _tool_read_generation_draft(state, resource_type)
        if not draft:
            draft = _build_default_draft(request_payload, resource_type, plan, retrieval_context)
            draft = _tool_write_generation_draft(state, resource_type, draft)

        return {
            "success": True,
            "resource_type": resource_type,
            "plan": plan,
            "retrieval_context": retrieval_context if isinstance(retrieval_context, dict) else {},
            "draft": draft,
            "learning_brief": draft.get("learning_brief") if isinstance(draft, dict) else {},
            "tool_trace": state["tool_trace"][:],
        }


def get_resource_planning_agent() -> ResourcePlanningAgent:
    return ResourcePlanningAgent()


def run_resource_planning_agent(
    request_payload: dict,
    resource_type: str,
    *,
    planning_agent: Any = None,
) -> dict:
    agent = planning_agent or get_resource_planning_agent()
    return agent.run(request_payload, resource_type)
