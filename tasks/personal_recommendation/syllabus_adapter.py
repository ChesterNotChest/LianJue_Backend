"""Adapt syllabus JSON into the graph shape used by route recommendation."""
from typing import Any, Dict, List, Optional


def _pick_id(item: dict) -> Optional[str]:
    for key in ("id", "node_id", "nid", "uid", "key"):
        if key in item:
            return str(item[key])
    if "title" in item:
        return str(item["title"])
    return None


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


def _normalize_node(node: dict, include_depends_on: bool = False) -> Dict[str, Any]:
    prerequisites = node.get("prerequisites") or node.get("prereq") or node.get("parents")
    if include_depends_on and not prerequisites:
        prerequisites = node.get("depends_on")
    outcomes = node.get("outcomes") or node.get("skills") or node.get("learning_outcomes") or []
    return {
        "prerequisites": _normalize_links(prerequisites),
        "outcomes": _normalize_links(outcomes),
        "learning_time_est": _normalize_number(
            node.get("learning_time_est") or node.get("duration") or node.get("learning_time") or 1
        ),
        "difficulty": _normalize_number(node.get("difficulty") or node.get("level") or 1),
        "title": node.get("title") or node.get("name") or None,
    }


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
                result[str(node_id)] = _normalize_node(node)
        return result

    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            node_id = _pick_id(item)
            if node_id:
                result[str(node_id)] = _normalize_node(item, include_depends_on=True)
        return result

    if isinstance(syllabus_json, dict) and all(isinstance(value, dict) for value in syllabus_json.values()):
        for node_id, node in syllabus_json.items():
            result[str(node_id)] = _normalize_node(node)
        return result

    return {}
