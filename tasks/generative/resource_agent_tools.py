"""Tools used by the pydantic-ai resource generation agent."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from tasks.common.status_events import STATUS_RUNNING, emit_status_event
from tasks.generative import resource_planning_agent as planning_task
from tasks.generative.resource_agent_contracts import (
    RESOURCE_AGENT_ERROR_GENERATION_FAILED,
    RESOURCE_AGENT_ERROR_MISSING_REQUEST,
    RESOURCE_AGENT_ERROR_PERSIST_FAILED,
)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _append_trace(state: Dict[str, Any], tool_name: str) -> None:
    trace = state.setdefault("tool_trace", [])
    if isinstance(trace, list):
        trace.append(tool_name)
    emit_status_event(
        state,
        agent="resource_agent",
        stage=tool_name,
        status=STATUS_RUNNING,
        payload={"resource_type": state.get("resource_type") or ""},
    )


def _with_status(state: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = _safe_text(result.get("tool"))
    if tool_name:
        emit_status_event(
            state,
            agent="resource_agent",
            stage=tool_name,
            status="succeeded" if result.get("success") is not False else "failed",
            message=result.get("error_message") or result.get("error") or "",
            payload={"resource_type": result.get("resource_type") or state.get("resource_type") or ""},
        )
    return result


def _get_search_fn(planning_agent: Any) -> Optional[Callable[..., Dict[str, Any]]]:
    if planning_agent is None:
        return None
    if hasattr(planning_agent, "_get_search_fn"):
        try:
            return planning_agent._get_search_fn()
        except Exception:
            return None
    search_fn = getattr(planning_agent, "search_fn", None)
    return search_fn if callable(search_fn) else None


def _normalize_list(value: Any, *, limit: int = 6, max_chars: int = 160) -> List[str]:
    items = value if isinstance(value, list) else ([] if value is None else [value])
    normalized: List[str] = []
    for item in items:
        text = _safe_text(item)
        if not text:
            continue
        if len(text) > max_chars:
            text = text[: max(0, max_chars - 3)].rstrip() + "..."
        if text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _summarize_retrieval_context(retrieval_context: Dict[str, Any], *, resource_type: str) -> Dict[str, Any]:
    evidence_chars_by_type = {
        "documents": 180,
        "coding_practice": 140,
        "ppt": 48,
        "quiz": 48,
        "mindmap": 48,
    }
    evidence_max_chars = evidence_chars_by_type.get(resource_type, 120)
    paragraphs = _normalize_list(retrieval_context.get("paragraphs"), limit=4, max_chars=evidence_max_chars)
    results = retrieval_context.get("results") if isinstance(retrieval_context.get("results"), list) else []
    result_summaries: List[str] = []
    for result in results[:3]:
        if isinstance(result, dict):
            text = _safe_text(result.get("summary") or result.get("content") or result.get("text") or result.get("title"))
        else:
            text = _safe_text(result)
        if text:
            result_summaries.extend(_normalize_list([text], limit=1, max_chars=evidence_max_chars))
    reasoning_paths = _normalize_list(retrieval_context.get("reasoning_paths"), limit=3, max_chars=140)
    top_k_by_type = {
        "documents": 4,
        "coding_practice": 3,
        "ppt": 2,
        "quiz": 2,
        "mindmap": 2,
    }
    keep = top_k_by_type.get(resource_type, 3)
    evidence = (paragraphs + result_summaries)[:keep]
    return {
        "success": bool(retrieval_context.get("success")),
        "result_count": int(retrieval_context.get("result_count") or len(evidence)),
        "evidence_summaries": evidence,
        "reasoning_paths": reasoning_paths[:2],
        "error": retrieval_context.get("error") or "",
    }


def _build_learning_brief(
    request: Dict[str, Any],
    resource_type: str,
    plan: Dict[str, Any],
    retrieval_context: Dict[str, Any],
    draft: Dict[str, Any],
) -> Dict[str, Any]:
    requirements = request.get("generation_requirements") if isinstance(request.get("generation_requirements"), dict) else {}
    max_slides = requirements.get("max_slides") or requirements.get("ppt_max_slides") or 6
    try:
        max_slides = max(3, min(int(max_slides), 8))
    except Exception:
        max_slides = 6
    retrieval_summary = _summarize_retrieval_context(retrieval_context, resource_type=resource_type)
    key_concepts = _normalize_list(
        (request.get("knowledge_items") or []) + (request.get("weak_points") or []),
        limit=8,
        max_chars=80,
    )
    if not key_concepts:
        key_concepts = _normalize_list([request.get("topic")], limit=1, max_chars=80)
    return {
        "topic": request.get("topic") or "",
        "student_question": request.get("question") or "",
        "learning_goal": request.get("learning_goal") or plan.get("objective") or "",
        "resource_type": resource_type,
        "key_concepts": key_concepts,
        "weak_points": _normalize_list(request.get("weak_points"), limit=5, max_chars=80),
        "selected_weeks": request.get("selected_weeks") if isinstance(request.get("selected_weeks"), list) else [],
        "outline": _normalize_list(draft.get("outline"), limit=6, max_chars=80),
        "evidence_summaries": retrieval_summary["evidence_summaries"],
        "reasoning_paths": retrieval_summary["reasoning_paths"],
        "generation_constraints": {
            "max_slides": max_slides,
            "quiz_count": requirements.get("quiz_count") or 5,
            "coding_scope": requirements.get("coding_scope") or "single-file runnable practice",
        },
    }


def _compact_planning_bundle_for_generation(planning_bundle: Dict[str, Any], resource_type: str) -> Dict[str, Any]:
    learning_brief = planning_bundle.get("learning_brief") if isinstance(planning_bundle.get("learning_brief"), dict) else {}
    plan = planning_bundle.get("plan") if isinstance(planning_bundle.get("plan"), dict) else {}
    draft = planning_bundle.get("draft") if isinstance(planning_bundle.get("draft"), dict) else {}
    retrieval_context = planning_bundle.get("retrieval_context") if isinstance(planning_bundle.get("retrieval_context"), dict) else {}
    retrieval_summary = _summarize_retrieval_context(retrieval_context, resource_type=resource_type)
    brief_evidence_max_chars = 180 if resource_type == "documents" else 48
    compact_learning_brief = {
        "topic": learning_brief.get("topic") or plan.get("topic") or "",
        "student_question": learning_brief.get("student_question") or plan.get("student_question") or "",
        "learning_goal": learning_brief.get("learning_goal") or plan.get("learning_goal") or plan.get("objective") or "",
        "resource_type": learning_brief.get("resource_type") or resource_type,
        "key_concepts": _normalize_list(learning_brief.get("key_concepts"), limit=8, max_chars=80),
        "weak_points": _normalize_list(learning_brief.get("weak_points"), limit=5, max_chars=80),
        "selected_weeks": learning_brief.get("selected_weeks") if isinstance(learning_brief.get("selected_weeks"), list) else [],
        "outline": _normalize_list(learning_brief.get("outline"), limit=6, max_chars=80),
        "evidence_summaries": _normalize_list(
            learning_brief.get("evidence_summaries") or retrieval_summary["evidence_summaries"],
            limit=3 if resource_type == "documents" else 1,
            max_chars=brief_evidence_max_chars,
        ),
        "reasoning_paths": _normalize_list(learning_brief.get("reasoning_paths"), limit=2, max_chars=140),
        "generation_constraints": learning_brief.get("generation_constraints")
        if isinstance(learning_brief.get("generation_constraints"), dict)
        else {},
    }
    compact = {
        "success": planning_bundle.get("success", True),
        "resource_type": resource_type,
        "plan": {
            "resource_type": plan.get("resource_type") or resource_type,
            "topic": plan.get("topic"),
            "student_question": plan.get("student_question"),
            "learning_goal": plan.get("learning_goal"),
            "objective": plan.get("objective"),
            "knowledge_items": _normalize_list(plan.get("knowledge_items"), limit=8, max_chars=80),
            "weak_points": _normalize_list(plan.get("weak_points"), limit=5, max_chars=80),
        },
        "draft": {
            "resource_type": draft.get("resource_type") or resource_type,
            "title": draft.get("title"),
            "summary": draft.get("summary"),
            "outline": _normalize_list(draft.get("outline"), limit=6, max_chars=80),
            "evidence": _normalize_list(
                draft.get("evidence"),
                limit=3 if resource_type == "documents" else 1,
                max_chars=180 if resource_type == "documents" else 48,
            ),
        },
        "retrieval_context": retrieval_summary,
        "learning_brief": compact_learning_brief,
        "tool_trace": planning_bundle.get("tool_trace") if isinstance(planning_bundle.get("tool_trace"), list) else [],
    }
    return compact


def tool_read_generation_request(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "read_generation_request")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    if not request:
        return _with_status(state, {
            "tool": "read_generation_request",
            "success": False,
            "error_code": RESOURCE_AGENT_ERROR_MISSING_REQUEST,
            "error_message": "missing generation request",
        })
    return _with_status(state, {
        "tool": "read_generation_request",
        "success": True,
        "user_id": request.get("user_id"),
        "syllabus_id": request.get("syllabus_id"),
        "resource_type": resource_type,
        "topic": request.get("topic") or "",
        "question": request.get("question") or "",
    })


def tool_read_generation_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "read_generation_plan")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    if not plan:
        plan = planning_task._build_default_plan(request, resource_type)
        state["plan"] = plan
    return _with_status(state, {
        "tool": "read_generation_plan",
        "success": True,
        "resource_type": resource_type,
        "plan": plan,
    })


def tool_retrieve_generation_materials(state: Dict[str, Any], *, search_query: str = "") -> Dict[str, Any]:
    _append_trace(state, "retrieve_generation_materials")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    search_fn = _get_search_fn(state.get("planning_agent"))
    retrieval_context = planning_task._tool_retrieve_generation_materials(
        {"request": request, "tool_trace": []},
        resource_type,
        search_fn,
        query_override=_safe_text(search_query),
    )
    if not isinstance(retrieval_context, dict):
        retrieval_context = {"success": False, "paragraphs": [], "reasoning_paths": [], "error": ""}
    state["retrieval_context"] = retrieval_context
    return _with_status(state, {
        "tool": "retrieve_generation_materials",
        "success": bool(retrieval_context.get("success")),
        "result_count": int(retrieval_context.get("result_count") or len(retrieval_context.get("paragraphs") or [])),
        "retrieval_context": retrieval_context,
        "error": retrieval_context.get("error") or "",
    })


def tool_write_generation_draft(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "write_generation_draft")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    retrieval_context = state.get("retrieval_context") if isinstance(state.get("retrieval_context"), dict) else {}
    draft = planning_task._build_default_draft(request, resource_type, plan, retrieval_context)
    learning_brief = _build_learning_brief(request, resource_type, plan, retrieval_context, draft)
    draft["learning_brief"] = learning_brief
    state["draft"] = draft
    state["planning_bundle"] = {
        "success": True,
        "resource_type": resource_type,
        "plan": plan,
        "retrieval_context": retrieval_context,
        "draft": draft,
        "learning_brief": learning_brief,
        "tool_trace": [
            "read_generation_plan",
            "retrieve_generation_materials",
            "write_generation_draft",
        ],
    }
    return _with_status(state, {
        "tool": "write_generation_draft",
        "success": True,
        "resource_type": resource_type,
        "draft": draft,
        "learning_brief": learning_brief,
        "planning_bundle": state["planning_bundle"],
    })


def tool_generate_resource_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "generate_resource_payload")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    planning_bundle = state.get("planning_bundle") if isinstance(state.get("planning_bundle"), dict) else {}
    generation_bundle = _compact_planning_bundle_for_generation(planning_bundle, resource_type)
    state["generation_planning_bundle"] = generation_bundle
    generator = state.get("generation_tool")
    try:
        if hasattr(generator, "generate"):
            generated_content = generator.generate(request, resource_type, generation_bundle)
        elif hasattr(generator, "generate_resource_content"):
            generated_content = generator.generate_resource_content(request, resource_type, generation_bundle)
        else:
            error_message = "resource content generation tool is required"
            state["generation_error"] = error_message
            return _with_status(state, {
                "tool": "generate_resource_payload",
                "success": False,
                "resource_type": resource_type,
                "error_code": RESOURCE_AGENT_ERROR_GENERATION_FAILED,
                "error_message": error_message,
            })
    except Exception as exc:
        state["generation_error"] = str(exc)
        return _with_status(state, {
            "tool": "generate_resource_payload",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_GENERATION_FAILED,
            "error_message": str(exc),
        })
    if not isinstance(generated_content, dict):
        error_message = "generated resource payload must be a dict"
        state["generation_error"] = error_message
        return _with_status(state, {
            "tool": "generate_resource_payload",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_GENERATION_FAILED,
            "error_message": error_message,
        })
    state["generated_content"] = generated_content
    return _with_status(state, {
        "tool": "generate_resource_payload",
        "success": True,
        "resource_type": resource_type,
        "content": generated_content,
    })


def tool_persist_generated_resource(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "persist_generated_resource")
    existing_resource = state.get("persisted_resource")
    if isinstance(existing_resource, dict) and existing_resource.get("success") is True:
        return _with_status(state, {
            "tool": "persist_generated_resource",
            "success": bool(existing_resource.get("success")),
            "resource_type": existing_resource.get("resource_type") or state.get("resource_type") or "",
            "resource": existing_resource,
            "idempotent": True,
            "error_code": existing_resource.get("error_code") or "",
            "error_message": existing_resource.get("error_message") or "",
        })
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    generated_content = state.get("generated_content")
    if not isinstance(generated_content, dict):
        return _with_status(state, {
            "tool": "persist_generated_resource",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_PERSIST_FAILED,
            "error_message": "missing generated_content",
        })
    try:
        from tasks.generative.resource_generation_agent import build_single_resource_payload
        from tasks.generative.resource_persistence import persist_generated_resource

        persisted = persist_generated_resource(
            build_single_resource_payload(request, resource_type),
            generated_content,
        )
    except Exception as exc:
        state["persist_error"] = str(exc)
        return _with_status(state, {
            "tool": "persist_generated_resource",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_PERSIST_FAILED,
            "error_message": str(exc),
        })
    state["persisted_resource"] = persisted
    return _with_status(state, {
        "tool": "persist_generated_resource",
        "success": bool(persisted.get("success")),
        "resource_type": resource_type,
        "resource": persisted,
        "error_code": persisted.get("error_code") or "",
        "error_message": persisted.get("error_message") or "",
    })
