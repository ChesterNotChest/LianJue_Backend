import os
from typing import Any, Dict

from tasks.search_tool import search_tool


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def build_recommendation_search_query(payload: Dict[str, Any]) -> str:
    parts = []
    for goal in payload.get("goals") or []:
        text = safe_text(goal)
        if text:
            parts.append(text)
    for key in ("question", "learning_goal", "topic"):
        text = safe_text(payload.get(key))
        if text:
            parts.append(text)
    if not parts:
        parts.append("learning path recommendation")
    return " ".join(parts)


def tool_load_request_context(state: Dict[str, Any]) -> Dict[str, Any]:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    state["request_context"] = {
        "user_id": payload.get("user_id"),
        "syllabus_id": payload.get("syllabus_id"),
        "goals": payload.get("goals") or [],
        "question": payload.get("question") or "",
        "graph_name": payload.get("graph_name") or payload.get("rag_graph_name") or "",
    }
    state["request_context_loaded"] = True
    return {
        "tool": "load_request_context",
        "has_user_id": bool(payload.get("user_id")),
        "has_syllabus_id": bool(payload.get("syllabus_id")),
        "goal_count": len(payload.get("goals") or []),
    }


def tool_search_recommendation_context(state: Dict[str, Any]) -> Dict[str, Any]:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    query = build_recommendation_search_query(payload)
    graph_name = payload.get("graph_name") or payload.get("rag_graph_name") or os.getenv("SEARCH_TOOL_GRAPH_NAME")
    try:
        top_k = int(payload.get("rag_top_k") or payload.get("top_k") or 5)
    except Exception:
        top_k = 5
    result = search_tool(query, graph_name=graph_name, top_k=top_k)
    state["rag_context"] = result
    return {
        "tool": "search_recommendation_context",
        "query": query,
        "success": bool(result.get("success")),
        "result_count": int(result.get("result_count") or 0),
        "reasoning_paths": result.get("reasoning_paths") or [],
        "error": result.get("error") or "",
    }


def tool_run_recommendation_route(state: Dict[str, Any]) -> Dict[str, Any]:
    from tasks import personal_recommendation_task as recommendation_task

    payload = dict(state.get("payload") or {})
    if state.get("rag_context") is not None:
        payload["rag_context"] = state.get("rag_context")
    result = recommendation_task.run_recommendation_route_from_payload(payload)
    state["recommendation_result"] = result
    return {
        "tool": "run_recommendation_route",
        "success": bool(result.get("success")),
        "candidate_count": len(result.get("candidates") or []),
        "selected_count": len(result.get("selected") or []),
        "has_graph": bool((result.get("graph") or {}).get("nodes")),
        "error_code": result.get("error_code") or "",
    }
