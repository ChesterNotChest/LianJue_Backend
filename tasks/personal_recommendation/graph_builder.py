"""Build the runtime graph used by recommendation search."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Optional



NODE_SOURCE_SYLLABUS = "syllabus"
NODE_SOURCE_RAG = "rag"
EDGE_SOURCE_SYLLABUS = "syllabus"
EDGE_SOURCE_RAG = "rag"
EDGE_SOURCE_PROFILE = "profile"
EDGE_CONFIDENCE_SYLLABUS = 1.0
EDGE_CONFIDENCE_RAG_DEFAULT = 0.6

PROFILE_STATE_KNOWN = "known"
PROFILE_STATE_WEAK = "weak"
PROFILE_STATE_UNKNOWN = "unknown"

STUDY_GRAPH_STATE_COMPLETED = "completed"
STUDY_GRAPH_STATE_BLOCKED = "blocked"
STUDY_GRAPH_STATE_WEAK = "weak"
STUDY_GRAPH_STATE_CURRENT = "current"
STUDY_GRAPH_STATE_UNKNOWN = "unknown"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _knowledge_levels(profile: Optional[dict]) -> dict:
    if not isinstance(profile, dict):
        return {}
    knowledge = profile.get("knowledge_levels")
    return knowledge if isinstance(knowledge, dict) else {}


def _match_score(candidates: list[str], knowledge: Dict[str, float]) -> tuple[list[float], list[str]]:
    """Return (scores, matched_keys) for the best-matching knowledge_point entries.

    Tries exact match first, then substring containment (either direction),
    then token-set overlap as a final fallback.  This bridges the gap between
    short profile knowledge-point keys (e.g. "HDFS 基础") and long syllabus
    outcome / title strings (e.g. "分布式文件系统及主流技术HDFS").
    """
    if not candidates or not knowledge:
        return [], []
    scores: list[float] = []
    matched: list[str] = []
    for candidate in candidates:
        # 1) exact match
        if candidate in knowledge:
            scores.append(_safe_float(knowledge[candidate], 0.0))
            matched.append(candidate)
            continue
        # 2) substring containment
        best = 0.0
        best_key = ""
        candidate_lower = candidate.lower()
        for key, value in knowledge.items():
            key_lower = key.lower()
            if key_lower in candidate_lower or candidate_lower in key_lower:
                v = _safe_float(value, 0.0)
                if v > best:
                    best = v
                    best_key = key
        if best > 0:
            scores.append(best)
            matched.append(best_key)
            continue
        # 3) token-overlap fallback
        candidate_tokens = _tokenize(candidate)
        if not candidate_tokens:
            continue
        best = 0.0
        best_key = ""
        for key, value in knowledge.items():
            key_tokens = _tokenize(key)
            overlap = candidate_tokens & key_tokens
            if overlap:
                v = _safe_float(value, 0.0)
                if v > best:
                    best = v
                    best_key = key
        if best > 0:
            scores.append(best)
            matched.append(best_key)
    return scores, matched


def _tokenize(text: str) -> set[str]:
    """Lightweight token set for Chinese + English mixed text."""
    tokens: set[str] = set()
    # English alphabet tokens
    for m in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*", text):
        if len(m) >= 2:
            tokens.add(m.lower())
    # Chinese character bigrams + single-keyword tokens
    chinese = re.findall(r"[一-鿿]+", text)
    for chunk in chinese:
        # bigrams
        for i in range(len(chunk) - 1):
            tokens.add(chunk[i:i+2])
        # also keep the whole chunk (up to a reasonable length)
        if len(chunk) <= 8:
            tokens.add(chunk)
    return tokens


def _annotate_profile_state(node: dict, profile: Optional[dict]) -> str:
    outcomes = [str(item) for item in node.get("outcomes") or [] if item not in (None, "")]
    title = str(node.get("title") or "")
    knowledge = _knowledge_levels(profile)
    if not knowledge:
        return PROFILE_STATE_UNKNOWN

    # Try outcomes first, then title as fallback
    candidates = list(outcomes)
    if title and title not in candidates:
        candidates.append(title)

    scores, _ = _match_score(candidates, knowledge)
    if scores and all(s >= 0.8 for s in scores):
        return PROFILE_STATE_KNOWN
    if any(s > 0 for s in scores):
        return PROFILE_STATE_WEAK
    return PROFILE_STATE_UNKNOWN


def _as_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        text = value.strip()
        return {text} if text else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if item not in (None, "")}
    return {str(value)}


def _annotate_study_graph_state(node_id: str, study_graph_state: Optional[dict]) -> str:
    if not isinstance(study_graph_state, dict):
        return STUDY_GRAPH_STATE_UNKNOWN
    normalized = str(node_id)
    if normalized and normalized == str(study_graph_state.get("current_node_id") or ""):
        return STUDY_GRAPH_STATE_CURRENT
    if normalized in _as_set(study_graph_state.get("completed_node_ids")):
        return STUDY_GRAPH_STATE_COMPLETED
    if normalized in _as_set(study_graph_state.get("blocked_node_ids")):
        return STUDY_GRAPH_STATE_BLOCKED
    if normalized in _as_set(study_graph_state.get("weak_node_ids")):
        return STUDY_GRAPH_STATE_WEAK
    return STUDY_GRAPH_STATE_UNKNOWN


def _normalize_prerequisites(node: dict) -> list[str]:
    return [str(item) for item in node.get("prerequisites") or [] if item not in (None, "")]


def build_recommendation_graph_tree(
    learning_tree: Dict[str, Any],
    rag_overlay: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    study_graph_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    graph = deepcopy(learning_tree or {})
    for node_id, raw_node in list(graph.items()):
        node = raw_node if isinstance(raw_node, dict) else {}
        if node is not raw_node:
            graph[node_id] = node
        node.setdefault("title", str(node_id))
        node.setdefault("outcomes", [])
        node["prerequisites"] = _normalize_prerequisites(node)
        node.setdefault("node_source", NODE_SOURCE_SYLLABUS)

        edge_sources = node.get("edge_sources") if isinstance(node.get("edge_sources"), dict) else {}
        edge_confidence = node.get("edge_confidence") if isinstance(node.get("edge_confidence"), dict) else {}
        for prerequisite in node["prerequisites"]:
            edge_sources.setdefault(str(prerequisite), EDGE_SOURCE_SYLLABUS)
            edge_confidence.setdefault(str(prerequisite), EDGE_CONFIDENCE_SYLLABUS)
        node["edge_sources"] = edge_sources
        node["edge_confidence"] = edge_confidence
        try:
            node["reliability"] = float(node.get("reliability", 1.0))
        except Exception:
            node["reliability"] = 1.0
        node["profile_state"] = _annotate_profile_state(node, profile)
        node["study_graph_state"] = _annotate_study_graph_state(str(node_id), study_graph_state)

    if isinstance(rag_overlay, dict):
        for edge in rag_overlay.get("temporary_edges") or []:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if not source or not target or source not in graph or target not in graph:
                continue
            target_node = graph[target]
            prerequisites = target_node.setdefault("prerequisites", [])
            if source not in prerequisites:
                prerequisites.append(source)
            target_node.setdefault("edge_sources", {})[source] = EDGE_SOURCE_RAG
            target_node.setdefault("edge_confidence", {})[source] = EDGE_CONFIDENCE_RAG_DEFAULT
    return graph
