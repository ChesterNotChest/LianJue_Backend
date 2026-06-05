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


_TOKEN_STOPWORDS = {
    "的",
    "是",
    "和",
    "与",
    "及",
    "中",
    "在",
    "为",
    "了",
    "有",
    "this",
    "that",
    "with",
    "from",
    "the",
    "and",
    "for",
}


def _is_quality_token(token: str) -> bool:
    token = _safe_text(token).lower()
    if not token or token in _TOKEN_STOPWORDS:
        return False
    if re.fullmatch(r"[a-z0-9]+", token):
        return len(token) >= 3
    if re.fullmatch(r"[\u4e00-\u9fff]+", token):
        return len(token) >= 2
    return len(token) >= 3


def _tokenize(value: Any) -> set[str]:
    text = _safe_text(value).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text, flags=re.UNICODE)
        if _is_quality_token(token)
    }


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _edge_text(value: Any) -> str:
    parsed = _parse_jsonish(value)
    if isinstance(parsed, dict):
        parts = [
            parsed.get("source"),
            parsed.get("target"),
            parsed.get("relation"),
            parsed.get("reason"),
            parsed.get("title"),
        ]
        return " ".join(_safe_text(item) for item in parts if _safe_text(item))
    return _safe_text(parsed)


def _is_quality_edge_text(value: Any) -> bool:
    text = _safe_text(value)
    if not text:
        return False
    relation_text = text.split(":", 1)[1] if ":" in text else text
    quality_tokens = _tokenize(relation_text)
    single_char_items = re.findall(r"(?:^|[,，\s])([a-zA-Z\u4e00-\u9fff])(?:$|[,，\s])", relation_text)
    if ":" in text and len(quality_tokens) < 2:
        return False
    if single_char_items and len(single_char_items) > max(3, len(quality_tokens) * 2):
        return False
    return True


def _collect_rag_evidence(rag_context: Dict[str, Any]) -> Dict[str, Any]:
    reasoning_paths = rag_context.get("reasoning_paths") if isinstance(rag_context, dict) else None
    evidence_texts: List[str] = []
    entities: List[str] = []
    edges: List[str] = []

    if isinstance(reasoning_paths, dict):
        for edge in reasoning_paths.get("edges") or []:
            text = _edge_text(edge)
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
            text = _edge_text(item)
            if text:
                evidence_texts.append(text)
                edges.append(text)
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
                if overlap >= 0.5 or len(alias_tokens & evidence_tokens) >= 2:
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
        if not _is_quality_edge_text(edge):
            continue
        source = None
        target = None
        edge_norm = _normalize_text(edge)
        edge_tokens = _tokenize(edge)
        for matched in matched_nodes:
            title_norm = _normalize_text(matched["title"])
            title_tokens = _tokenize(matched["title"])
            strong_title_match = bool(title_norm and title_norm in edge_norm)
            strong_token_match = bool(title_tokens and (len(title_tokens & edge_tokens) >= max(1, min(2, len(title_tokens)))))
            if strong_title_match or strong_token_match:
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
