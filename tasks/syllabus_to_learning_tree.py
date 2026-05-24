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
            result[str(nid)] = {
                'prerequisites': list(node.get('prerequisites') or node.get('prereq') or node.get('parents') or []),
                'outcomes': list(node.get('outcomes') or node.get('skills') or []),
                'learning_time_est': float(node.get('learning_time_est') or node.get('duration') or node.get('learning_time') or 1),
                'difficulty': float(node.get('difficulty') or node.get('level') or 1),
                'title': node.get('title') or node.get('name') or None,
            }
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
            prereq = item.get('prerequisites') or item.get('prereq') or item.get('parents') or item.get('depends_on') or []
            if isinstance(prereq, str):
                prereq = [prereq]
            outcomes = item.get('outcomes') or item.get('skills') or item.get('learning_outcomes') or []
            if isinstance(outcomes, str):
                outcomes = [outcomes]
            try:
                time_est = float(item.get('learning_time_est') or item.get('duration') or item.get('learning_time') or 1)
            except Exception:
                time_est = 1.0
            try:
                diff = float(item.get('difficulty') or item.get('level') or 1)
            except Exception:
                diff = 1.0
            result[str(nid)] = {
                'prerequisites': list(prereq),
                'outcomes': list(outcomes),
                'learning_time_est': time_est,
                'difficulty': diff,
                'title': item.get('title') or item.get('name') or None,
            }
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
                result[str(nid)] = {
                    'prerequisites': list(node.get('prerequisites') or node.get('prereq') or []),
                    'outcomes': list(node.get('outcomes') or node.get('skills') or []),
                    'learning_time_est': float(node.get('learning_time_est') or node.get('duration') or 1),
                    'difficulty': float(node.get('difficulty') or node.get('level') or 1),
                    'title': node.get('title') or node.get('name') or None,
                }
            return result

    return {}


