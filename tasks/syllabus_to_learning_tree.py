"""Helpers to convert a syllabus JSON into the `learning_tree` shape
expected by the recommendation route.

This implements a best-effort mapping supporting several common syllabus shapes.
"""
from typing import Any, Dict, List, Optional


def _pick_id(item: dict) -> Optional[str]:
    for k in ('id', 'node_id', 'nid', 'uid', 'key'):
        if k in item:
            return str(item[k])
    # try title-based fallback (not ideal)
    if 'title' in item:
        return str(item['title'])
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
    prereq = node.get('prerequisites') or node.get('prereq') or node.get('parents')
    if include_depends_on and not prereq:
        prereq = node.get('depends_on')
    outcomes = node.get('outcomes') or node.get('skills') or node.get('learning_outcomes') or []
    return {
        'prerequisites': _normalize_links(prereq),
        'outcomes': _normalize_links(outcomes),
        'learning_time_est': _normalize_number(node.get('learning_time_est') or node.get('duration') or node.get('learning_time') or 1),
        'difficulty': _normalize_number(node.get('difficulty') or node.get('level') or 1),
        'title': node.get('title') or node.get('name') or None,
    }


def syllabus_json_to_learning_tree(syllabus_json: Any) -> Dict[str, Dict]:
    if not syllabus_json:
        return {}

    # find nodes container
    nodes = None
    if isinstance(syllabus_json, dict):
        for k in ('nodes', 'items', 'modules', 'chapters', 'sections'):
            if k in syllabus_json and isinstance(syllabus_json[k], (list, dict)):
                nodes = syllabus_json[k]
                break
    if nodes is None and isinstance(syllabus_json, list):
        nodes = syllabus_json

    result: Dict[str, Dict] = {}

    # If nodes is a dict mapping id->node
    if isinstance(nodes, dict):
        for nid, node in nodes.items():
            if not isinstance(node, dict):
                continue
            result[str(nid)] = _normalize_node(node)
        return result

    # If nodes is a list
    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            nid = _pick_id(item)
            if not nid:
                # skip items without id/title
                continue
            result[str(nid)] = _normalize_node(item, include_depends_on=True)
        return result

    # Fallback: if syllabus_json itself looks like mapping id->node
    if isinstance(syllabus_json, dict):
        ok = True
        for k, v in syllabus_json.items():
            if not isinstance(v, dict):
                ok = False
                break
        if ok:
            for nid, node in syllabus_json.items():
                result[str(nid)] = _normalize_node(node)
            return result

    return {}

