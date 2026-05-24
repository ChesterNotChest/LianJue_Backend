import json
import math
import re
from difflib import SequenceMatcher
from typing import Any, Iterable, List

from tasks.study_graph.contracts import STUDY_GRAPH_TITLE_STOP_SUFFIXES, score_to_mastery_label

try:
    from pypinyin import Style, lazy_pinyin
except Exception:  # pragma: no cover - optional dependency
    Style = None
    lazy_pinyin = None


def _unicode_normalize_text(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .replace("　", " ")
        .replace("：", ":")
        .replace("，", ",")
        .replace("。", ".")
        .replace("；", ";")
        .replace("？", "?")
        .replace("！", "!")
    )


def _romanize_cjk_text(text: str) -> str:
    text = str(text or "")
    if not text:
        return ""
    if lazy_pinyin is not None and Style is not None:
        try:
            romanized = "".join(lazy_pinyin(text, style=Style.NORMAL, strict=False))
        except Exception:
            romanized = ""
        if romanized:
            return romanized
    return "".join(f"u{ord(ch):x}" for ch in text)


def normalize_knowledge_title(title: str) -> str:
    text = _unicode_normalize_text(title).lower()
    for suffix in STUDY_GRAPH_TITLE_STOP_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff _-]+", " ", text)
    tokens: list[str] = []
    for part in re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]+", text):
        if re.fullmatch(r"[0-9a-zA-Z]+", part):
            cleaned = part.lower()
        else:
            cleaned = _romanize_cjk_text(part).lower()
        cleaned = re.sub(r"[^0-9a-z]+", "", cleaned)
        if cleaned:
            tokens.append(cleaned)
    return "_".join(tokens)


def normalize_aliases(aliases: Any) -> list[str]:
    if not isinstance(aliases, list):
        return []
    normalized: list[str] = []
    for alias in aliases:
        text = str(alias or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized[:8]


def _tokenize(value: str) -> list[str]:
    cleaned = normalize_knowledge_title(value)
    if not cleaned:
        return []
    return [token for token in cleaned.split("_") if token]


def _common_prefix_len(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    for index in range(limit):
        if a[index] != b[index]:
            return index
    return limit


def _normalized_edit_distance(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    matcher = SequenceMatcher(a=a, b=b)
    return 1.0 - matcher.ratio()


def rank_tree_candidates(nodes: list[dict], query: str, max_candidates: int) -> list[dict]:
    normalized_query = normalize_knowledge_title(query)
    if not normalized_query:
        return []

    ranked: list[dict] = []
    query_tokens = set(_tokenize(normalized_query))
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        normalized_title = normalize_knowledge_title(node.get("normalized_title") or node.get("title") or "")
        if not normalized_title:
            continue
        aliases = normalize_aliases(node.get("aliases") or [])
        alias_norm_hit = any(normalize_knowledge_title(alias) == normalized_query for alias in aliases)
        exact_title = 1.0 if normalized_title == normalized_query else 0.0
        alias_exact = 1.0 if alias_norm_hit else 0.0
        substring = 1.0 if (normalized_query in normalized_title or normalized_title in normalized_query) else 0.0
        candidate_tokens = set(_tokenize(normalized_title))
        token_union = query_tokens | candidate_tokens
        token_jaccard = (len(query_tokens & candidate_tokens) / len(token_union)) if token_union else 0.0
        prefix = _common_prefix_len(normalized_query, normalized_title) / max(len(normalized_query), len(normalized_title), 1)
        levenshtein = 1 - _normalized_edit_distance(normalized_query, normalized_title)
        score = max(
            0.0,
            min(
                1.0,
                0.42 * exact_title
                + 0.24 * alias_exact
                + 0.16 * substring
                + 0.10 * token_jaccard
                + 0.05 * prefix
                + 0.03 * levenshtein,
            ),
        )
        ranked.append(
            {
                "node_id": node.get("node_id"),
                "title": node.get("title"),
                "normalized_title": normalized_title,
                "mastery": node.get("mastery") if isinstance(node.get("mastery"), dict) else {"label": score_to_mastery_label(0.0), "score": 0.0},
                "score": score,
                "matched_by": "normalized_title" if exact_title else "alias" if alias_exact else "substring" if substring else "overlap",
                "candidate_roles": ["existing_node", "possible_parent"] if score >= 0.6 else ["existing_node"],
            }
        )

    ranked.sort(key=lambda item: (item["score"], len(str(item.get("title") or ""))), reverse=True)
    return ranked[: max(0, int(max_candidates or 0))]


def evidence_key_from_payload(payload: dict) -> str:
    question = normalize_knowledge_title(payload.get("question") or "")
    detected_topics = sorted(
        normalize_knowledge_title(item.get("title") or "")
        for item in (payload.get("detected_topics") or [])
        if isinstance(item, dict) and item.get("title")
    )
    event_signatures = sorted(
        json.dumps(item, ensure_ascii=False, sort_keys=True)
        for item in (payload.get("events") or [])
        if isinstance(item, dict)
    )
    rag_titles = sorted(
        normalize_knowledge_title(item.get("title") or "")
        for item in (payload.get("rag_context") or [])
        if isinstance(item, dict) and item.get("title")
    )
    parent_candidates = sorted(
        normalize_knowledge_title(item.get("child_title") or "")
        for item in (payload.get("parent_candidates") or [])
        if isinstance(item, dict) and item.get("child_title")
    )
    raw = "|".join([question, ",".join(detected_topics), ",".join(event_signatures), ",".join(rag_titles), ",".join(parent_candidates)])
    return raw.strip("|")
