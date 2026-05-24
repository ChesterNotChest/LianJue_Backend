import json
import re
from typing import Any, Dict, List


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value).strip()


def _normalize_text(value: Any) -> str:
    text = _safe_text(value).lower()
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE))


def _tokenize(value: Any) -> set[str]:
    text = _safe_text(value).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text, flags=re.UNICODE)
        if len(token) > 1
    }


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _collect_rag_evidence(rag_context: Dict[str, Any]) -> Dict[str, Any]:
    reasoning_paths = rag_context.get("reasoning_paths") if isinstance(rag_context, dict) else None
    evidence_texts: List[str] = []
    entities: List[str] = []
    edges: List[str] = []

    if isinstance(reasoning_paths, dict):
        for edge in reasoning_paths.get("edges") or []:
            text = _safe_text(edge)
            if text:
                edges.append(text)
                evidence_texts.append(text)
        for item in reasoning_paths.get("entity_in_para_details") or []:
            parsed = _parse_jsonish(item)
            evidence_texts.append(_safe_text(parsed))
            if isinstance(parsed, dict):
                entities.extend(str(key) for key in parsed.keys())
    elif isinstance(reasoning_paths, list):
        for item in reasoning_paths:
            evidence_texts.append(_safe_text(item))
            if isinstance(item, dict):
                entities.extend(str(key) for key in item.keys() if key in ("title", "entity", "topic"))
    elif reasoning_paths:
        evidence_texts.append(_safe_text(reasoning_paths))

    for key in ("paragraphs", "results"):
        values = rag_context.get(key) if isinstance(rag_context, dict) else None
        if isinstance(values, list):
            evidence_texts.extend(_safe_text(item) for item in values)

    context_text = rag_context.get("context_text") if isinstance(rag_context, dict) else ""
    if context_text:
        evidence_texts.append(_safe_text(context_text))

    evidence_text = "\n".join(text for text in evidence_texts if text)
    return {
        "entities": sorted({item for item in entities if item}),
        "edges": edges,
        "text": evidence_text,
        "normalized_text": _normalize_text(evidence_text),
        "tokens": _tokenize(evidence_text),
    }


def build_rag_overlay(rag_context: Any, learning_tree: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(rag_context, dict) or not rag_context.get("success"):
        return {
            "enabled": False,
            "matched_nodes": [],
            "candidate_hints": [],
            "temporary_edges": [],
            "warnings": ["rag_context missing or unsuccessful"],
        }

    evidence = _collect_rag_evidence(rag_context)
    matched_nodes = []
    node_relevance: Dict[str, float] = {}
    normalized_evidence = evidence["normalized_text"]
    evidence_tokens = evidence["tokens"]

    for node_id, node in (learning_tree or {}).items():
        if not isinstance(node, dict):
            continue
        aliases = [node_id, node.get("title")]
        aliases.extend(node.get("outcomes") or [])
        aliases.extend(node.get("aliases") or [])

        best_score = 0.0
        matched_by = []
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if not normalized_alias:
                continue
            if normalized_alias in normalized_evidence:
                best_score = max(best_score, 1.0)
                matched_by.append(str(alias))
                continue
            alias_tokens = _tokenize(alias)
            if alias_tokens:
                overlap = len(alias_tokens & evidence_tokens) / max(len(alias_tokens), 1)
                if overlap > 0:
                    best_score = max(best_score, min(0.85, overlap))
                    matched_by.append(str(alias))

        if best_score > 0:
            relevance = round(best_score, 4)
            node_relevance[str(node_id)] = relevance
            matched_nodes.append(
                {
                    "node_id": str(node_id),
                    "title": node.get("title") or str(node_id),
                    "relevance": relevance,
                    "matched_by": sorted(set(matched_by)),
                    "evidence_entities": evidence["entities"][:8],
                }
            )

    temporary_edges = []
    for edge in evidence["edges"]:
        source = None
        target = None
        edge_norm = _normalize_text(edge)
        for matched in matched_nodes:
            title_norm = _normalize_text(matched["title"])
            if title_norm and title_norm in edge_norm:
                if source is None:
                    source = matched["node_id"]
                elif target is None and matched["node_id"] != source:
                    target = matched["node_id"]
        if source and target:
            temporary_edges.append(
                {
                    "source": source,
                    "target": target,
                    "type": "rag_evidence",
                    "reason": edge,
                    "persistent": False,
                }
            )

    return {
        "enabled": True,
        "matched_nodes": matched_nodes,
        "candidate_hints": [],
        "temporary_edges": temporary_edges,
        "warnings": [],
        "node_relevance": node_relevance,
    }


def score_candidate_with_overlay(candidate: Dict[str, Any], overlay: Dict[str, Any]) -> float:
    if not isinstance(overlay, dict):
        return 0.0
    node_relevance = overlay.get("node_relevance") if isinstance(overlay.get("node_relevance"), dict) else {}
    path = [str(item) for item in candidate.get("path") or []]
    if not path:
        return 0.0
    return round(sum(float(node_relevance.get(node_id) or 0.0) for node_id in path) / len(path), 4)
