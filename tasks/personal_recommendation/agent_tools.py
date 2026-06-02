import os
from typing import Any, Dict

from tasks.common.search_tool import search_tool
from tasks.personal_recommendation.concept_decomposer import (
    CONCEPT_DECOMPOSITION_SCHEMA_VERSION,
    DECOMPOSE_PERIOD_CONCEPTS_TOOL,
    READ_PERIOD_CONTEXT_TOOL,
    RETRIEVE_PERIOD_EVIDENCE_TOOL,
    VALIDATE_CONCEPT_GRAPH_TOOL,
    decompose_periods_to_concepts,
    normalize_decomposition_rag_context,
)


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def _short_text(value: Any, limit: int = 700) -> str:
    text = safe_text(value)
    return text[:limit] if len(text) > limit else text


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


def tool_read_period_context(state: Dict[str, Any]) -> Dict[str, Any]:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    periods = payload.get("periods") if isinstance(payload.get("periods"), list) else []
    normalized_periods = [item for item in periods if isinstance(item, dict)]
    state["periods"] = normalized_periods
    state.setdefault("tool_trace", []).append(READ_PERIOD_CONTEXT_TOOL)
    return {
        "tool": READ_PERIOD_CONTEXT_TOOL,
        "period_count": len(normalized_periods),
        "has_syllabus_id": bool(payload.get("syllabus_id")),
        "periods": [
            {
                "week_index": safe_text(period.get("week_index")),
                "content": _short_text(period.get("content"), 500),
                "enhanced_content": _short_text(period.get("enhanced_content"), 900),
                "importance": safe_text(period.get("importance")),
            }
            for period in normalized_periods[:6]
        ],
    }


def tool_retrieve_period_evidence(state: Dict[str, Any]) -> Dict[str, Any]:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    if isinstance(payload.get("rag_context"), dict):
        rag_context = payload["rag_context"]
    else:
        periods = state.get("periods") if isinstance(state.get("periods"), list) else []
        query_parts = []
        for period in periods[:3]:
            query_parts.append(safe_text(period.get("content")))
            query_parts.append(safe_text(period.get("enhanced_content")))
        query = " ".join(part for part in query_parts if part).strip() or "course concept decomposition"
        graph_name = payload.get("graph_name") or os.getenv("PERSONAL_RECOMMENDATION_DECOMPOSER_RAG_GRAPH_NAME") or os.getenv("SEARCH_TOOL_GRAPH_NAME")
        try:
            top_k = int(payload.get("rag_top_k") or os.getenv("PERSONAL_RECOMMENDATION_DECOMPOSER_TOP_K") or 5)
        except Exception:
            top_k = 5
        rag_context = search_tool(query, graph_name=graph_name, top_k=top_k)
    normalized = normalize_decomposition_rag_context(rag_context)
    state["rag_context"] = rag_context
    state["normalized_rag_context"] = normalized
    state.setdefault("tool_trace", []).append(RETRIEVE_PERIOD_EVIDENCE_TOOL)
    evidence_items = normalized.get("evidence_items") if isinstance(normalized.get("evidence_items"), list) else []
    return {
        "tool": RETRIEVE_PERIOD_EVIDENCE_TOOL,
        "success": bool(normalized.get("success")),
        "query": normalized.get("query") or "",
        "graph_name": normalized.get("graph_name") or "",
        "evidence_count": len(evidence_items),
        "evidence_items": [
            {
                "id": item.get("id"),
                "rank": item.get("rank"),
                "content": _short_text(item.get("content"), 900),
                "source": item.get("source"),
                "relevance_score": item.get("relevance_score"),
            }
            for item in evidence_items[:5]
            if isinstance(item, dict)
        ],
        "reasoning_edges": (normalized.get("reasoning_edges") or [])[:10],
        "warning_count": len(normalized.get("warnings") or []),
    }


def tool_decompose_period_concepts(state: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Store the Agent's concept graph proposal.

    Expected proposal shape:
    {
      "concepts": [
        {
          "title": "RowKey",
          "source_period": {"week_index": "6", "title": "HBase"},
          "prerequisite_titles": ["HBase"],
          "confidence": 0.86,
          "matched_by": ["period.enhanced_content", "rag.evidence"],
          "reason": "RowKey is central to HBase row access."
        }
      ],
      "edges": [
        {"source_title": "HBase", "target_title": "RowKey", "confidence": 0.8}
      ]
    }
    """
    state["concept_proposal"] = proposal if isinstance(proposal, dict) else {}
    state.setdefault("tool_trace", []).append(DECOMPOSE_PERIOD_CONCEPTS_TOOL)
    return {
        "tool": DECOMPOSE_PERIOD_CONCEPTS_TOOL,
        "concept_count": len((state["concept_proposal"].get("concepts") or []) if isinstance(state["concept_proposal"], dict) else []),
        "edge_count": len((state["concept_proposal"].get("edges") or []) if isinstance(state["concept_proposal"], dict) else []),
    }


def tool_validate_concept_graph(state: Dict[str, Any]) -> Dict[str, Any]:
    from tasks.personal_recommendation.syllabus_adapter import _extract_period_concepts

    periods = state.get("periods") if isinstance(state.get("periods"), list) else []
    proposal = state.get("concept_proposal") if isinstance(state.get("concept_proposal"), dict) else {}
    result = decompose_periods_to_concepts(
        periods,
        rag_context=state.get("rag_context") if isinstance(state.get("rag_context"), dict) else None,
        decomposer=lambda _payload: proposal,
        rule_decomposer=_extract_period_concepts,
    )
    state["decomposition_result"] = result
    state.setdefault("tool_trace", []).append(VALIDATE_CONCEPT_GRAPH_TOOL)
    return {
        "tool": VALIDATE_CONCEPT_GRAPH_TOOL,
        "success": bool(result.get("success")),
        "schema_version": CONCEPT_DECOMPOSITION_SCHEMA_VERSION,
        "concept_count": len(result.get("concepts") or []),
        "edge_count": len(result.get("edges") or []),
        "fallback_used": bool(result.get("fallback_used")),
        "error_code": result.get("error_code") or "",
    }
