"""Tools used by the pydantic-ai resource generation agent."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

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


def tool_read_generation_request(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "read_generation_request")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    if not request:
        return {
            "tool": "read_generation_request",
            "success": False,
            "error_code": RESOURCE_AGENT_ERROR_MISSING_REQUEST,
            "error_message": "missing generation request",
        }
    return {
        "tool": "read_generation_request",
        "success": True,
        "user_id": request.get("user_id"),
        "syllabus_id": request.get("syllabus_id"),
        "resource_type": resource_type,
        "topic": request.get("topic") or "",
        "question": request.get("question") or "",
    }


def tool_read_generation_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "read_generation_plan")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    if not plan:
        plan = planning_task._build_default_plan(request, resource_type)
        state["plan"] = plan
    return {
        "tool": "read_generation_plan",
        "success": True,
        "resource_type": resource_type,
        "plan": plan,
    }


def tool_retrieve_generation_materials(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "retrieve_generation_materials")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    search_fn = _get_search_fn(state.get("planning_agent"))
    retrieval_context = planning_task._tool_retrieve_generation_materials(
        {"request": request, "tool_trace": []},
        resource_type,
        search_fn,
    )
    if not isinstance(retrieval_context, dict):
        retrieval_context = {"success": False, "paragraphs": [], "reasoning_paths": [], "error": ""}
    state["retrieval_context"] = retrieval_context
    return {
        "tool": "retrieve_generation_materials",
        "success": bool(retrieval_context.get("success")),
        "result_count": int(retrieval_context.get("result_count") or len(retrieval_context.get("paragraphs") or [])),
        "retrieval_context": retrieval_context,
        "error": retrieval_context.get("error") or "",
    }


def tool_write_generation_draft(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "write_generation_draft")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    retrieval_context = state.get("retrieval_context") if isinstance(state.get("retrieval_context"), dict) else {}
    draft = planning_task._build_default_draft(request, resource_type, plan, retrieval_context)
    state["draft"] = draft
    state["planning_bundle"] = {
        "success": True,
        "resource_type": resource_type,
        "plan": plan,
        "retrieval_context": retrieval_context,
        "draft": draft,
        "tool_trace": [
            "read_generation_plan",
            "retrieve_generation_materials",
            "write_generation_draft",
        ],
    }
    return {
        "tool": "write_generation_draft",
        "success": True,
        "resource_type": resource_type,
        "draft": draft,
        "planning_bundle": state["planning_bundle"],
    }


class LegacyResourcePayloadGenerator:
    """Compatibility adapter around the old LiteLLM resource payload generator."""

    def __init__(self, legacy_agent: Any = None) -> None:
        self.legacy_agent = legacy_agent

    def generate(self, request_payload: dict, resource_type: str, planning_bundle: dict) -> dict:
        agent = self.legacy_agent
        if agent is None:
            from tasks.generative.resource_generation_agent import LLMResourceGenerationAgent

            agent = LLMResourceGenerationAgent()
            self.legacy_agent = agent
        return agent.generate_resource_content(request_payload, resource_type, planning_bundle)


def tool_generate_resource_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "generate_resource_payload")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    planning_bundle = state.get("planning_bundle") if isinstance(state.get("planning_bundle"), dict) else {}
    generator = state.get("generation_tool")
    try:
        if hasattr(generator, "generate"):
            generated_content = generator.generate(request, resource_type, planning_bundle)
        elif hasattr(generator, "generate_resource_content"):
            generated_content = generator.generate_resource_content(request, resource_type, planning_bundle)
        else:
            generated_content = LegacyResourcePayloadGenerator().generate(request, resource_type, planning_bundle)
    except Exception as exc:
        state["generation_error"] = str(exc)
        return {
            "tool": "generate_resource_payload",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_GENERATION_FAILED,
            "error_message": str(exc),
        }
    if not isinstance(generated_content, dict):
        error_message = "generated resource payload must be a dict"
        state["generation_error"] = error_message
        return {
            "tool": "generate_resource_payload",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_GENERATION_FAILED,
            "error_message": error_message,
        }
    state["generated_content"] = generated_content
    return {
        "tool": "generate_resource_payload",
        "success": True,
        "resource_type": resource_type,
        "content": generated_content,
    }


def tool_persist_generated_resource(state: Dict[str, Any]) -> Dict[str, Any]:
    _append_trace(state, "persist_generated_resource")
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    resource_type = _safe_text(state.get("resource_type") or request.get("resource_type"))
    generated_content = state.get("generated_content")
    if not isinstance(generated_content, dict):
        return {
            "tool": "persist_generated_resource",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_PERSIST_FAILED,
            "error_message": "missing generated_content",
        }
    try:
        from tasks.generative.resource_generation_agent import build_single_resource_payload
        from tasks.generative.resource_persistence import persist_generated_resource

        persisted = persist_generated_resource(
            build_single_resource_payload(request, resource_type),
            generated_content,
        )
    except Exception as exc:
        state["persist_error"] = str(exc)
        return {
            "tool": "persist_generated_resource",
            "success": False,
            "resource_type": resource_type,
            "error_code": RESOURCE_AGENT_ERROR_PERSIST_FAILED,
            "error_message": str(exc),
        }
    state["persisted_resource"] = persisted
    return {
        "tool": "persist_generated_resource",
        "success": bool(persisted.get("success")),
        "resource_type": resource_type,
        "resource": persisted,
        "error_code": persisted.get("error_code") or "",
        "error_message": persisted.get("error_message") or "",
    }
