"""Adapt syllabus JSON into the graph shape used by route recommendation."""

import re
from typing import Any, Dict, List, Optional


SYLLABUS_CHILD_KEYS = ("children", "sections", "topics", "subtopics", "items", "modules")
SYLLABUS_ID_KEYS = ("id", "node_id", "nid", "uid", "key")
SYLLABUS_TITLE_KEYS = ("title", "name", "label")
SYLLABUS_OUTCOME_KEYS = ("outcomes", "skills", "learning_outcomes", "objectives")
SYLLABUS_PREREQUISITE_KEYS = ("prerequisites", "prereq", "parents", "depends_on")
DEFAULT_DIRECTORY_DIFFICULTY = 1.0
DEFAULT_DIRECTORY_LEARNING_TIME = 1.0


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


def syllabus_json_to_learning_tree(syllabus_json: Any) -> Dict[str, Dict]:
    if not syllabus_json:
        return {}

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
