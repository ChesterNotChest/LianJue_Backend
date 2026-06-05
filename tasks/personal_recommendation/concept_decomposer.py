"""Concept decomposition helpers for period-based recommendation syllabi."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


CONCEPT_DECOMPOSITION_SCHEMA_VERSION = "personal_recommendation.concept_decomposition.v1"

DECOMPOSITION_METHOD_AGENT = "agent"
DECOMPOSITION_METHOD_RULE_FALLBACK = "rule_fallback"
DECOMPOSITION_METHOD_PERIOD_ANCHOR = "period_anchor"

FALLBACK_TAG_RULE_CONCEPT = "period_concept_rule_fallback"
FALLBACK_TAG_RULE_IMPLIED_CONCEPT = "period_concept_rule_implied_fallback"
FALLBACK_TAG_PERIOD_TITLE = "period_title_fallback"
FALLBACK_TAG_AGENT_INVALID = "agent_invalid_fallback"
FALLBACK_TAG_AGENT_UNAVAILABLE = "agent_unavailable_fallback"

READ_PERIOD_CONTEXT_TOOL = "read_period_context"
RETRIEVE_PERIOD_EVIDENCE_TOOL = "retrieve_period_evidence"
DECOMPOSE_PERIOD_CONCEPTS_TOOL = "decompose_period_concepts"
VALIDATE_CONCEPT_GRAPH_TOOL = "validate_concept_graph"

CONCEPT_DECOMPOSITION_TOOL_ORDER = [
    READ_PERIOD_CONTEXT_TOOL,
    RETRIEVE_PERIOD_EVIDENCE_TOOL,
    DECOMPOSE_PERIOD_CONCEPTS_TOOL,
    VALIDATE_CONCEPT_GRAPH_TOOL,
]

REVIEW_ACTION_ACCEPT_WITH_LOW_CONFIDENCE = "accept_with_low_confidence"
REVIEW_ACTION_RERETRIEVE_AND_RETRY = "reretrieve_and_retry"
REVIEW_ACTION_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"
REVIEW_ACTION_REQUIRE_TEACHER_REVIEW = "require_teacher_review"

FALLBACK_REVIEW_ACTIONS = (
    REVIEW_ACTION_ACCEPT_WITH_LOW_CONFIDENCE,
    REVIEW_ACTION_RERETRIEVE_AND_RETRY,
    REVIEW_ACTION_ASK_GOAL_CLARIFICATION,
    REVIEW_ACTION_REQUIRE_TEACHER_REVIEW,
)

RELIABILITY_AGENT_DEFAULT = 0.85
RELIABILITY_PERIOD_ANCHOR_DEFAULT = 0.8
RELIABILITY_RULE_FALLBACK_DEFAULT = 0.55
RELIABILITY_RULE_IMPLIED_DEFAULT = 0.35


class ConceptItem(BaseModel):
    title: str
    source_period: Dict[str, Any] = Field(default_factory=dict)
    prerequisite_titles: List[str] = Field(default_factory=list)
    outcomes: List[str] = Field(default_factory=list)
    confidence: float = RELIABILITY_AGENT_DEFAULT
    reliability: Optional[float] = None
    matched_by: List[str] = Field(default_factory=list)
    reason: str = ""
    decomposition_method: str = DECOMPOSITION_METHOD_AGENT
    fallback_tag: str = ""
    implied: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: Any) -> float:
        return _clamp_float(value, RELIABILITY_AGENT_DEFAULT)

    @field_validator("reliability", mode="before")
    @classmethod
    def _normalize_reliability(cls, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        return _clamp_float(value, RELIABILITY_AGENT_DEFAULT)


class ConceptEdge(BaseModel):
    source_title: str
    target_title: str
    confidence: float = RELIABILITY_AGENT_DEFAULT
    reason: str = ""

    @field_validator("source_title", "target_title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: Any) -> float:
        return _clamp_float(value, RELIABILITY_AGENT_DEFAULT)


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        normalized = float(value)
    except Exception:
        normalized = float(default)
    if normalized < 0:
        return 0.0
    if normalized > 1:
        return 1.0
    return normalized


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_string_list(value: Any) -> List[str]:
    items = []
    for item in _as_list(value):
        text = _safe_text(item)
        if text and text not in items:
            items.append(text)
    return items


def _normalize_concept_input(item: Dict[str, Any]) -> Dict[str, Any]:
    concept = dict(item)
    if "matched_by" in concept and not isinstance(concept.get("matched_by"), list):
        concept["matched_by"] = _normalize_string_list(concept.get("matched_by"))
    if "prerequisite_titles" in concept and not isinstance(concept.get("prerequisite_titles"), list):
        concept["prerequisite_titles"] = _normalize_string_list(concept.get("prerequisite_titles"))
    if "outcomes" in concept and not isinstance(concept.get("outcomes"), list):
        concept["outcomes"] = _normalize_string_list(concept.get("outcomes"))
    return concept


def _normalize_edge_input(item: Dict[str, Any]) -> Dict[str, Any]:
    edge = dict(item)
    if not edge.get("source_title"):
        edge["source_title"] = edge.get("source") or edge.get("from")
    if not edge.get("target_title"):
        edge["target_title"] = edge.get("target") or edge.get("to")
    if not edge.get("reason") and edge.get("relation"):
        edge["reason"] = _safe_text(edge.get("relation"))
    return edge


def _source_period_key(concept: Dict[str, Any]) -> str:
    source_period = concept.get("source_period") if isinstance(concept.get("source_period"), dict) else {}
    return _safe_text(source_period.get("week_index"))


def _concept_key(concept: Dict[str, Any]) -> tuple[str, str]:
    return (_source_period_key(concept), _safe_text(concept.get("title")).lower())


def reliability_for_concept(concept: Dict[str, Any], method: str = "") -> float:
    if concept.get("reliability") not in (None, ""):
        return _clamp_float(concept.get("reliability"), RELIABILITY_AGENT_DEFAULT)
    if concept.get("fallback_tag") == FALLBACK_TAG_RULE_IMPLIED_CONCEPT or concept.get("implied"):
        return RELIABILITY_RULE_IMPLIED_DEFAULT
    if (concept.get("decomposition_method") or method) == DECOMPOSITION_METHOD_RULE_FALLBACK:
        return RELIABILITY_RULE_FALLBACK_DEFAULT
    if (concept.get("decomposition_method") or method) == DECOMPOSITION_METHOD_PERIOD_ANCHOR:
        return RELIABILITY_PERIOD_ANCHOR_DEFAULT
    return _clamp_float(concept.get("confidence"), RELIABILITY_AGENT_DEFAULT)


def normalize_decomposition_rag_context(rag_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(rag_context, dict):
        return {
            "success": False,
            "query": "",
            "graph_name": "",
            "evidence_items": [],
            "reasoning_edges": [],
            "entity_details": [],
            "path_scores": {},
            "context_text": "",
            "warnings": ["rag_context missing or not dict"],
        }

    warnings: List[str] = []
    results = rag_context.get("results") if isinstance(rag_context.get("results"), list) else []
    evidence_items: List[Dict[str, Any]] = []
    if results:
        for idx, item in enumerate(results, start=1):
            if not isinstance(item, dict):
                continue
            content = _safe_text(item.get("content") or item.get("summary") or item)
            if not content:
                continue
            try:
                rank = int(item.get("rank") or idx)
            except Exception:
                rank = idx
            relevance = item.get("relevance_score")
            if relevance in (None, ""):
                relevance = item.get("score")
            if relevance in (None, ""):
                relevance = 1.0 / max(rank, 1)
            evidence_items.append(
                {
                    "id": _safe_text(item.get("id")) or f"evidence_{len(evidence_items) + 1}",
                    "rank": rank,
                    "content": content,
                    "source": _safe_text(item.get("source")) or "results",
                    "relevance_score": _clamp_float(relevance, 1.0 / max(rank, 1)),
                    "metadata": _dict_or_empty(item.get("metadata")),
                }
            )

    if not evidence_items:
        paragraphs = rag_context.get("paragraphs") if isinstance(rag_context.get("paragraphs"), list) else []
        for idx, paragraph in enumerate(paragraphs, start=1):
            content = _safe_text(paragraph)
            if not content:
                continue
            evidence_items.append(
                {
                    "id": f"evidence_{idx}",
                    "rank": idx,
                    "content": content,
                    "source": "paragraphs",
                    "relevance_score": 1.0 / idx,
                    "metadata": {
                        "query": rag_context.get("query") or "",
                        "graph_name": rag_context.get("graph_name") or "",
                    },
                }
            )

    reasoning_paths = rag_context.get("reasoning_paths")
    reasoning_edges: List[str] = []
    entity_details: List[Any] = []
    if isinstance(reasoning_paths, dict):
        reasoning_edges = _normalize_string_list(reasoning_paths.get("edges"))
        entity_details = _as_list(reasoning_paths.get("entity_in_para_details"))
    elif isinstance(reasoning_paths, list):
        for item in reasoning_paths:
            if isinstance(item, dict) and item.get("reason"):
                reasoning_edges.append(_safe_text(item.get("reason")))
            else:
                reasoning_edges.append(_safe_text(item))
        reasoning_edges = [item for item in reasoning_edges if item]
    elif reasoning_paths:
        reasoning_edges = [_safe_text(reasoning_paths)]

    if not evidence_items:
        warnings.append("no evidence items")

    return {
        "success": bool(rag_context.get("success")),
        "query": _safe_text(rag_context.get("query")),
        "graph_name": _safe_text(rag_context.get("graph_name")),
        "evidence_items": evidence_items,
        "reasoning_edges": reasoning_edges,
        "entity_details": entity_details,
        "path_scores": _dict_or_empty(rag_context.get("path_scores")),
        "context_text": _safe_text(rag_context.get("context_text")),
        "warnings": warnings,
    }


def _normalize_agent_result(raw_result: Any, periods: List[Dict[str, Any]]) -> Dict[str, Any]:
    if hasattr(raw_result, "model_dump"):
        raw_result = raw_result.model_dump()
    if not isinstance(raw_result, dict):
        return _structured_failure("agent_invalid_output", "agent returned non-dict output")

    concepts_in = raw_result.get("concepts") if isinstance(raw_result.get("concepts"), list) else []
    edges_in = raw_result.get("edges") if isinstance(raw_result.get("edges"), list) else []
    concepts: List[Dict[str, Any]] = []
    seen = set()
    period_by_week = {
        _safe_text(period.get("week_index")): period
        for period in periods
        if isinstance(period, dict)
    }

    for item in concepts_in:
        if not isinstance(item, dict):
            continue
        try:
            concept = ConceptItem.model_validate(_normalize_concept_input(item)).model_dump()
        except Exception:
            continue
        if not concept["title"]:
            continue
        source_period = concept.get("source_period") if isinstance(concept.get("source_period"), dict) else {}
        week_index = _safe_text(source_period.get("week_index"))
        if not week_index and len(periods) == 1:
            week_index = _safe_text(periods[0].get("week_index") or "1")
            source_period["week_index"] = week_index
        if not source_period.get("title") and week_index in period_by_week:
            source_period["title"] = _safe_text(period_by_week[week_index].get("title") or period_by_week[week_index].get("content"))
        concept["source_period"] = source_period
        concept["decomposition_method"] = DECOMPOSITION_METHOD_AGENT
        concept["fallback_tag"] = ""
        concept["implied"] = False
        concept["outcomes"] = _normalize_string_list(concept.get("outcomes")) or [concept["title"]]
        concept["matched_by"] = _normalize_string_list(concept.get("matched_by"))
        concept["prerequisite_titles"] = _normalize_string_list(concept.get("prerequisite_titles"))
        concept["confidence"] = _clamp_float(concept.get("confidence"), RELIABILITY_AGENT_DEFAULT)
        concept["reliability"] = reliability_for_concept(concept, DECOMPOSITION_METHOD_AGENT)
        key = _concept_key(concept)
        if key in seen:
            continue
        seen.add(key)
        concepts.append(concept)

    if not concepts:
        return _structured_failure("agent_invalid_output", "agent returned no valid concepts")

    titles = {concept["title"] for concept in concepts}
    edges: List[Dict[str, Any]] = []
    for item in edges_in:
        if not isinstance(item, dict):
            continue
        try:
            edge = ConceptEdge.model_validate(_normalize_edge_input(item)).model_dump()
        except Exception:
            continue
        if edge["source_title"] not in titles or edge["target_title"] not in titles:
            continue
        edges.append(edge)

    return {
        "schema_version": CONCEPT_DECOMPOSITION_SCHEMA_VERSION,
        "success": True,
        "method": DECOMPOSITION_METHOD_AGENT,
        "fallback_used": False,
        "concepts": concepts,
        "edges": edges,
        "fallback_summary": {},
        "warnings": [],
        "error_code": "",
        "error_message": "",
    }


def _structured_failure(error_code: str, error_message: str) -> Dict[str, Any]:
    return {
        "schema_version": CONCEPT_DECOMPOSITION_SCHEMA_VERSION,
        "success": False,
        "method": "",
        "fallback_used": False,
        "concepts": [],
        "edges": [],
        "fallback_summary": {},
        "warnings": [],
        "error_code": error_code,
        "error_message": error_message,
    }


def _fallback_summary(reason: str, concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
    implied_count = sum(1 for concept in concepts if concept.get("fallback_tag") == FALLBACK_TAG_RULE_IMPLIED_CONCEPT or concept.get("implied"))
    return {
        "reason": reason,
        "fallback_node_count": len(concepts),
        "implied_fallback_count": implied_count,
        "review_action": REVIEW_ACTION_RERETRIEVE_AND_RETRY if implied_count else REVIEW_ACTION_ACCEPT_WITH_LOW_CONFIDENCE,
        "needs_review": bool(concepts),
    }


def _rule_fallback(periods: List[Dict[str, Any]], rule_decomposer: Optional[Callable[[dict], List[dict]]], reason: str) -> Dict[str, Any]:
    concepts: List[Dict[str, Any]] = []
    if callable(rule_decomposer):
        for period in periods:
            if not isinstance(period, dict):
                continue
            week_index = _safe_text(period.get("week_index"))
            period_title = _safe_text(period.get("title") or period.get("content"))
            for raw_concept in rule_decomposer(period) or []:
                if not isinstance(raw_concept, dict):
                    continue
                concept = dict(raw_concept)
                concept["source_period"] = {
                    "week_index": week_index,
                    "title": period_title,
                }
                concept["decomposition_method"] = DECOMPOSITION_METHOD_RULE_FALLBACK
                concept.setdefault("fallback_tag", FALLBACK_TAG_RULE_CONCEPT)
                concept["confidence"] = _clamp_float(concept.get("confidence"), RELIABILITY_RULE_FALLBACK_DEFAULT)
                concept["reliability"] = reliability_for_concept(concept, DECOMPOSITION_METHOD_RULE_FALLBACK)
                concept["outcomes"] = _normalize_string_list(concept.get("outcomes")) or [_safe_text(concept.get("title"))]
                concept["matched_by"] = _normalize_string_list(concept.get("matched_by"))
                concept["prerequisite_titles"] = _normalize_string_list(concept.get("prerequisite_titles"))
                concepts.append(concept)

    return {
        "schema_version": CONCEPT_DECOMPOSITION_SCHEMA_VERSION,
        "success": True,
        "method": DECOMPOSITION_METHOD_RULE_FALLBACK,
        "fallback_used": True,
        "concepts": concepts,
        "edges": [],
        "fallback_summary": _fallback_summary(reason, concepts),
        "warnings": [],
        "error_code": "",
        "error_message": "",
    }


def decompose_periods_to_concepts(
    periods: List[Dict[str, Any]],
    *,
    rag_context: Optional[Dict[str, Any]] = None,
    decomposer: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    rule_decomposer: Optional[Callable[[dict], List[dict]]] = None,
) -> Dict[str, Any]:
    period_copy = deepcopy(periods or [])
    normalized_rag = normalize_decomposition_rag_context(rag_context)
    payload = {
        "schema_version": CONCEPT_DECOMPOSITION_SCHEMA_VERSION,
        "periods": period_copy,
        "rag_context": normalized_rag,
    }

    if callable(decomposer):
        try:
            agent_result = _normalize_agent_result(decomposer(payload), period_copy)
        except Exception as exc:
            return _rule_fallback(period_copy, rule_decomposer, f"agent_unavailable:{exc}")
        if agent_result.get("success"):
            return agent_result
        return _rule_fallback(period_copy, rule_decomposer, agent_result.get("error_code") or "agent_invalid_output")

    return _rule_fallback(period_copy, rule_decomposer, "agent_unavailable")


def summarize_fallback_dependency(path: List[str], learning_tree: Dict[str, Any]) -> Dict[str, Any]:
    fallback_nodes = []
    implied_nodes = []
    reliabilities = []
    for node_id in path or []:
        node = learning_tree.get(str(node_id), {}) if isinstance(learning_tree, dict) else {}
        if not isinstance(node, dict):
            continue
        if node.get("decomposition_method") == DECOMPOSITION_METHOD_RULE_FALLBACK or node.get("fallback_tag"):
            fallback_nodes.append(str(node_id))
            if node.get("fallback_tag") == FALLBACK_TAG_RULE_IMPLIED_CONCEPT or node.get("implied"):
                implied_nodes.append(str(node_id))
        if node.get("reliability") not in (None, ""):
            reliabilities.append(_clamp_float(node.get("reliability"), 1.0))

    has_fallback = bool(fallback_nodes)
    if implied_nodes:
        action = REVIEW_ACTION_RERETRIEVE_AND_RETRY
    elif fallback_nodes:
        action = REVIEW_ACTION_ACCEPT_WITH_LOW_CONFIDENCE
    else:
        action = ""
    return {
        "has_fallback": has_fallback,
        "fallback_node_count": len(fallback_nodes),
        "implied_fallback_node_count": len(implied_nodes),
        "fallback_nodes": fallback_nodes,
        "lowest_reliability": min(reliabilities) if reliabilities else None,
        "suggested_agent_action": action,
    }
