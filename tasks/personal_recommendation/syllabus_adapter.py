"""Adapt syllabus JSON into the graph shape used by route recommendation."""

import re
from typing import Any, Callable, Dict, List, Optional

from tasks.personal_recommendation.concept_decomposer import (
    DECOMPOSITION_METHOD_PERIOD_ANCHOR,
    DECOMPOSITION_METHOD_RULE_FALLBACK,
    FALLBACK_TAG_PERIOD_TITLE,
    FALLBACK_TAG_RULE_CONCEPT,
    FALLBACK_TAG_RULE_IMPLIED_CONCEPT,
    RELIABILITY_PERIOD_ANCHOR_DEFAULT,
    decompose_periods_to_concepts,
)


SYLLABUS_CHILD_KEYS = ("children", "sections", "topics", "subtopics", "items", "modules")
SYLLABUS_ID_KEYS = ("id", "node_id", "nid", "uid", "key")
SYLLABUS_TITLE_KEYS = ("title", "name", "label")
SYLLABUS_OUTCOME_KEYS = ("outcomes", "skills", "learning_outcomes", "objectives")
SYLLABUS_PREREQUISITE_KEYS = ("prerequisites", "prereq", "parents", "depends_on")
DEFAULT_DIRECTORY_DIFFICULTY = 1.0
DEFAULT_DIRECTORY_LEARNING_TIME = 1.0
PERIOD_SOURCE = "syllabus_period"
PERIOD_FALLBACK_SOURCE = "syllabus_period_fallback"
PERIOD_CONCEPT_SOURCE = "syllabus_period_concept"
IMPORTANCE_DIFFICULTY = {
    "low": 1.0,
    "medium": 2.0,
    "high": 3.0,
}
PERIOD_CONCEPT_TERMS = (
    ("HDFS", ("HDFS", "分布式文件系统")),
    ("MapReduce", ("MapReduce",)),
    ("Hadoop", ("Hadoop",)),
    ("HBase", ("HBase",)),
    ("Hive", ("Hive",)),
    ("NoSQL", ("NoSQL", "非关系型数据库")),
    ("RowKey", ("RowKey", "行键")),
    ("Region", ("Region", "分区")),
    ("预分区", ("预分区", "预先分区", "Pre-splitting")),
    ("热点规避", ("热点", "热点规避", "热点问题")),
    ("列族", ("列族", "Column Family")),
    ("稀疏数据", ("稀疏数据",)),
    ("图数据库", ("图数据库",)),
    ("Apriori", ("Apriori",)),
    ("关联规则", ("关联规则",)),
    ("特征提取", ("特征提取",)),
    ("特征选择", ("特征选择",)),
    ("数据可视化", ("数据可视化", "可视化")),
    ("Spark", ("Spark",)),
    ("GPU", ("GPU",)),
    ("TPU", ("TPU",)),
    ("FPGA", ("FPGA",)),
    ("隐私保护", ("隐私保护",)),
)
PERIOD_IMPLIED_CONCEPTS = {
    "HBase": ("RowKey", "Region", "预分区", "热点规避", "列族", "稀疏数据"),
}
CONCEPT_PREREQUISITE_TITLES = {
    "RowKey": ("HBase",),
    "Region": ("HBase",),
    "预分区": ("Region",),
    "热点规避": ("RowKey", "Region"),
    "列族": ("HBase",),
    "稀疏数据": ("HBase",),
}
MIN_RULE_FALLBACK_CONCEPTS_PER_PERIOD = 2
MAX_RULE_FALLBACK_CONCEPTS_PER_PERIOD = 3


def _pick_id(item: dict) -> Optional[str]:
    for key in SYLLABUS_ID_KEYS:
        if key in item:
            return str(item[key])
    for key in SYLLABUS_TITLE_KEYS:
        if key in item:
            return str(item[key])
    return None


def _pick_title(item: dict) -> Optional[str]:
    for key in SYLLABUS_TITLE_KEYS:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _stable_id_from_title(title: str, parent_id: Optional[str] = None) -> str:
    text = str(title or "").strip()
    base = re.sub(r"\s+", "_", text)
    base = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", base, flags=re.UNICODE).strip("_")
    if not base:
        base = "node"
    if parent_id:
        return f"{parent_id}.{base}"
    return base


def _stable_period_id(title: str, week_index: Any = None) -> str:
    node_id = _stable_id_from_title(title)
    if node_id and node_id != "node":
        return node_id
    suffix = str(week_index or "").strip() or "unknown"
    return f"period_{suffix}"


def _normalize_links(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _normalize_number(value: Any, default: float = 1.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _difficulty_from_importance(value: Any) -> float:
    key = str(value or "").strip().lower()
    return IMPORTANCE_DIFFICULTY.get(key, DEFAULT_DIRECTORY_DIFFICULTY)


def _first_present(node: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = node.get(key)
        if value not in (None, ""):
            return value
    return None


def _iter_child_items(node: dict) -> List[dict]:
    children: List[dict] = []
    for key in SYLLABUS_CHILD_KEYS:
        value = node.get(key)
        if isinstance(value, dict):
            for child_id, child in value.items():
                if not isinstance(child, dict):
                    continue
                payload = dict(child)
                payload.setdefault("id", child_id)
                children.append(payload)
        elif isinstance(value, list):
            children.extend([item for item in value if isinstance(item, dict)])
    return children


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _period_title(period: dict) -> str:
    explicit_title = _pick_title(period)
    if explicit_title:
        return explicit_title
    content = _clean_text(period.get("content") or period.get("original_content"))
    if content:
        # "大数据存储与管理：分布式数据库中典型技术HBase" → take the
        # topic-name part (before the first colon), not the description.
        # Syllabus content follows a consistent "topic：description" pattern.
        for separator in ("：", ":", "；", ";"):
            if separator in content:
                parts = [part.strip() for part in content.split(separator) if part.strip()]
                if len(parts) >= 2:
                    return parts[-1][:40]
        return content[:40]
    enhanced = _clean_text(period.get("enhanced_content"))
    if enhanced:
        sentence = re.split(r"[。.!！？?]", enhanced, maxsplit=1)[0].strip()
        return sentence[:40] if sentence else enhanced[:40]
    week_index = _clean_text(period.get("week_index"))
    return f"period_{week_index}" if week_index else ""


def _period_outcomes(title: str, period: dict, node_id: str) -> List[str]:
    outcomes = _normalize_links(_first_present(period, SYLLABUS_OUTCOME_KEYS))
    candidates = list(outcomes)
    if title:
        candidates.append(title)
    if node_id and not node_id.startswith("period_"):
        candidates.append(node_id)

    # Add a few stable lexical hints from the original text. This is deliberately
    # light-weight; the adapter's concept decomposition is only a diagnosable
    # rule fallback. The primary decomposer should be an Agent/RAG stage.
    text = " ".join(
        _clean_text(period.get(key))
        for key in ("content", "enhanced_content", "original_content")
        if period.get(key)
    )
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]*", text):
        if len(token) >= 2:
            candidates.append(token)
    # Chinese token extraction removed: it produced nonsensical sentence
    # fragments from syllabus body text that looked broken in the frontend.

    seen = set()
    result = []
    for item in candidates:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result or ([title] if title else [])


def _concept_outcomes(title: str, concept_id: str) -> List[str]:
    candidates = [title, concept_id]
    if re.search(r"[A-Za-z]", title):
        candidates.append(title.lower())
    seen = set()
    result = []
    for item in candidates:
        normalized = str(item).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _normalize_concept_title(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip(" -_，,。.;；:：、")
    if not text or len(text) < 2:
        return ""
    if len(text) > 24:
        sentence = re.split(r"[。.!！?？]", text, maxsplit=1)[0].strip()
        if 2 <= len(sentence) <= 24:
            text = sentence
        else:
            return ""
    return text


def _fallback_concept_titles_from_period(period: dict) -> List[str]:
    candidates: List[str] = []
    for key in ("knowledge_points", "knowledge_point", "objectives", "outcomes", "skills", "keywords"):
        for item in _normalize_links(period.get(key)):
            title = _normalize_concept_title(item)
            if title:
                candidates.append(title)

    period_title = _normalize_concept_title(_period_title(period))
    if period_title:
        candidates.append(period_title)

    text = " ".join(
        _clean_text(period.get(key))
        for key in ("content", "enhanced_content", "original_content")
        if period.get(key)
    )
    for separator in ("：", ":", "；", ";"):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) >= 2:
                text = "；".join(parts[1:])
                break
    for phrase in re.split(r"[、,，;；/／|｜\n]+", text):
        title = _normalize_concept_title(phrase)
        if title:
            candidates.append(title)

    seen = set()
    result = []
    for title in candidates:
        if title in seen:
            continue
        seen.add(title)
        result.append(title)
        if len(result) >= MAX_RULE_FALLBACK_CONCEPTS_PER_PERIOD:
            break
    return result


def _extract_period_concepts(period: dict) -> List[dict]:
    text = " ".join(
        _clean_text(period.get(key))
        for key in ("content", "enhanced_content", "original_content")
        if period.get(key)
    )
    if not text:
        return []
    concepts = []
    seen = set()
    for title, aliases in PERIOD_CONCEPT_TERMS:
        matched_by = [alias for alias in aliases if alias and alias.lower() in text.lower()]
        if not matched_by or title in seen:
            continue
        seen.add(title)
        concepts.append(
            {
                "title": title,
                "matched_by": matched_by,
                "confidence": 0.75 if len(matched_by) == 1 else 0.85,
                "implied": False,
                "decomposition_method": DECOMPOSITION_METHOD_RULE_FALLBACK,
                "fallback_tag": FALLBACK_TAG_RULE_CONCEPT,
            }
        )
    for concept in list(concepts):
        for implied_title in PERIOD_IMPLIED_CONCEPTS.get(concept["title"], ()):
            if implied_title in seen:
                continue
            seen.add(implied_title)
            concepts.append(
                {
                    "title": implied_title,
                    "matched_by": [f"implied_by:{concept['title']}"],
                    "confidence": 0.55,
                    "implied": True,
                    "decomposition_method": DECOMPOSITION_METHOD_RULE_FALLBACK,
                    "fallback_tag": FALLBACK_TAG_RULE_IMPLIED_CONCEPT,
                }
            )
    if len(concepts) < MIN_RULE_FALLBACK_CONCEPTS_PER_PERIOD:
        for title in _fallback_concept_titles_from_period(period):
            if title in seen:
                continue
            seen.add(title)
            concepts.append(
                {
                    "title": title,
                    "matched_by": ["period.text_phrase"],
                    "confidence": 0.5,
                    "implied": False,
                    "decomposition_method": DECOMPOSITION_METHOD_RULE_FALLBACK,
                    "fallback_tag": FALLBACK_TAG_RULE_CONCEPT,
                }
            )
            if len(concepts) >= MAX_RULE_FALLBACK_CONCEPTS_PER_PERIOD:
                break
    return concepts


def _concept_prerequisites_from_titles(
    concept_title: str,
    prerequisite_titles: List[str],
    current_concept_by_title: Dict[str, str],
    previous_concept_by_title: Dict[str, str],
) -> List[str]:
    titles = list(prerequisite_titles or []) or list(CONCEPT_PREREQUISITE_TITLES.get(concept_title, ()))
    prerequisites = []
    for prerequisite_title in titles:
        prerequisite_id = current_concept_by_title.get(prerequisite_title) or previous_concept_by_title.get(prerequisite_title)
        if prerequisite_id and prerequisite_id not in prerequisites:
            prerequisites.append(prerequisite_id)
    previous_same_concept = previous_concept_by_title.get(concept_title)
    if previous_same_concept and previous_same_concept not in prerequisites:
        prerequisites.append(previous_same_concept)
    return prerequisites


def _period_description(period: dict) -> str:
    return _clean_text(period.get("enhanced_content") or period.get("content") or period.get("original_content"))


def _expand_period_nodes(
    periods: Any,
    *,
    concept_decomposer: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    rag_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict]:
    result: Dict[str, Dict] = {}
    if not isinstance(periods, list):
        return result
    decomposition = decompose_periods_to_concepts(
        periods,
        rag_context=rag_context,
        decomposer=concept_decomposer,
        rule_decomposer=_extract_period_concepts,
    )
    concepts_by_week: Dict[str, List[dict]] = {}
    for concept in decomposition.get("concepts") or []:
        if not isinstance(concept, dict):
            continue
        source_period = concept.get("source_period") if isinstance(concept.get("source_period"), dict) else {}
        week_index = str(source_period.get("week_index") or "")
        if week_index:
            concepts_by_week.setdefault(week_index, []).append(concept)
    edge_titles_by_target = {}
    for edge in decomposition.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        target = str(edge.get("target_title") or "").strip()
        source = str(edge.get("source_title") or "").strip()
        if target and source:
            edge_titles_by_target.setdefault(target, []).append(source)

    previous_anchor_id: Optional[str] = None
    previous_concept_by_title: Dict[str, str] = {}
    for index, item in enumerate(periods, start=1):
        if not isinstance(item, dict):
            continue
        title = _period_title(item)
        if not title:
            continue
        week_index = item.get("week_index") or index
        node_id = _stable_period_id(title, week_index=week_index)
        node_source = PERIOD_FALLBACK_SOURCE if node_id.startswith("period_") else PERIOD_SOURCE
        prerequisites = _normalize_links(_first_present(item, SYLLABUS_PREREQUISITE_KEYS))
        if previous_anchor_id and not prerequisites:
            prerequisites = [previous_anchor_id]
        anchor_node = {
            "title": title,
            "prerequisites": prerequisites,
            "outcomes": _period_outcomes(title, item, node_id),
            "learning_time_est": _normalize_number(
                item.get("learning_time_est") or item.get("duration") or item.get("learning_time") or DEFAULT_DIRECTORY_LEARNING_TIME
            ),
            "difficulty": _normalize_number(item.get("difficulty") or item.get("level"), _difficulty_from_importance(item.get("importance"))),
            "node_source": node_source,
            "decomposition_method": DECOMPOSITION_METHOD_PERIOD_ANCHOR,
            "reliability": RELIABILITY_PERIOD_ANCHOR_DEFAULT,
            "week_index": str(week_index),
            "day_one": _clean_text(item.get("day_one")),
            "importance": _clean_text(item.get("importance")),
            "description": _period_description(item),
            "original_content": _clean_text(item.get("original_content") or item.get("content")),
        }
        if node_source == PERIOD_FALLBACK_SOURCE:
            anchor_node["fallback_tag"] = FALLBACK_TAG_PERIOD_TITLE
        result[node_id] = anchor_node

        concepts = concepts_by_week.get(str(week_index), [])
        current_concept_by_title: Dict[str, str] = {}
        for concept in concepts:
            concept_title = concept["title"]
            concept_id = f"{node_id}.{_stable_id_from_title(concept_title)}"
            concept_prerequisites = [node_id]
            title_prerequisites = list(concept.get("prerequisite_titles") or [])
            title_prerequisites.extend(edge_titles_by_target.get(concept_title) or [])
            for prerequisite_id in _concept_prerequisites_from_titles(
                concept_title,
                title_prerequisites,
                current_concept_by_title,
                previous_concept_by_title,
            ):
                if prerequisite_id not in concept_prerequisites:
                    concept_prerequisites.append(prerequisite_id)
            result[concept_id] = {
                "title": concept_title,
                "prerequisites": concept_prerequisites,
                "outcomes": list(concept.get("outcomes") or []) or _concept_outcomes(concept_title, concept_id),
                "learning_time_est": 1.0,
                "difficulty": anchor_node["difficulty"],
                "node_source": PERIOD_CONCEPT_SOURCE,
                "decomposition_method": concept["decomposition_method"],
                "fallback_tag": concept.get("fallback_tag") or "",
                "week_index": str(week_index),
                "source_period": {
                    "week_index": str(week_index),
                    "title": title,
                    "node_id": node_id,
                },
                "confidence": concept["confidence"],
                "reliability": concept.get("reliability", concept.get("confidence")),
                "matched_by": concept["matched_by"],
                "implied": bool(concept.get("implied")),
                "reason": concept.get("reason") or "",
                "description": anchor_node["description"],
            }
            result[concept_id]["edge_sources"] = {
                prerequisite: result[concept_id]["decomposition_method"]
                for prerequisite in concept_prerequisites
            }
            result[concept_id]["edge_confidence"] = {
                prerequisite: min(float(anchor_node.get("reliability", 1.0)), float(result[concept_id].get("reliability", 1.0)))
                if prerequisite == node_id
                else float(result[concept_id].get("reliability", 1.0))
                for prerequisite in concept_prerequisites
            }
            current_concept_by_title[concept_title] = concept_id
        previous_concept_by_title.update(current_concept_by_title)
        previous_anchor_id = node_id
    return result


def _normalize_node(node: dict, include_depends_on: bool = False) -> Dict[str, Any]:
    prerequisites = _first_present(node, SYLLABUS_PREREQUISITE_KEYS if include_depends_on else SYLLABUS_PREREQUISITE_KEYS[:-1])
    outcomes = _first_present(node, SYLLABUS_OUTCOME_KEYS)
    title = _pick_title(node)
    return {
        "prerequisites": _normalize_links(prerequisites),
        "outcomes": _normalize_links(outcomes) or ([title] if title else []),
        "learning_time_est": _normalize_number(
            node.get("learning_time_est") or node.get("duration") or node.get("learning_time") or DEFAULT_DIRECTORY_LEARNING_TIME
        ),
        "difficulty": _normalize_number(node.get("difficulty") or node.get("level") or DEFAULT_DIRECTORY_DIFFICULTY),
        "title": title,
        "node_source": "syllabus",
    }


def _expand_syllabus_node(node: dict, parent_id: Optional[str], result: Dict[str, Dict]) -> Optional[str]:
    if not isinstance(node, dict):
        return None
    node_id = _pick_id(node)
    title = _pick_title(node)
    if not node_id and title:
        node_id = _stable_id_from_title(title, parent_id)
    if not node_id:
        return None

    normalized = _normalize_node(node, include_depends_on=True)
    if parent_id and not normalized["prerequisites"]:
        normalized["prerequisites"] = [str(parent_id)]
    result[str(node_id)] = normalized

    for child in _iter_child_items(node):
        _expand_syllabus_node(child, str(node_id), result)
    return str(node_id)


def syllabus_json_to_learning_tree(
    syllabus_json: Any,
    *,
    concept_decomposer: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    rag_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict]:
    if not syllabus_json:
        return {}

    if isinstance(syllabus_json, dict) and isinstance(syllabus_json.get("period"), list):
        return _expand_period_nodes(
            syllabus_json.get("period"),
            concept_decomposer=concept_decomposer,
            rag_context=rag_context,
        )

    nodes = None
    if isinstance(syllabus_json, dict):
        for key in ("nodes", "items", "modules", "chapters", "sections"):
            if key in syllabus_json and isinstance(syllabus_json[key], (list, dict)):
                nodes = syllabus_json[key]
                break
    if nodes is None and isinstance(syllabus_json, list):
        nodes = syllabus_json

    result: Dict[str, Dict] = {}

    if isinstance(nodes, dict):
        for node_id, node in nodes.items():
            if isinstance(node, dict):
                payload = dict(node)
                payload.setdefault("id", node_id)
                _expand_syllabus_node(payload, None, result)
        return result

    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            _expand_syllabus_node(item, None, result)
        return result

    if isinstance(syllabus_json, dict) and all(isinstance(value, dict) for value in syllabus_json.values()):
        for node_id, node in syllabus_json.items():
            payload = dict(node)
            payload.setdefault("id", node_id)
            _expand_syllabus_node(payload, None, result)
        return result

    return {}
