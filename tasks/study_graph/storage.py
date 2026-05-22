import json
from pathlib import Path
from time import time
from typing import Any, Optional

from tasks.study_graph.contracts import STUDY_GRAPH_MANIFEST_VERSION, build_tree_id, build_virtual_root_node, make_empty_tree, study_graph_root


def _tree_dir(user_id: int, syllabus_id: int) -> Path:
    return study_graph_root() / f"user_{int(user_id)}" / f"syllabus_{int(syllabus_id)}"


def _manifest_path(user_id: int, syllabus_id: int) -> Path:
    return _tree_dir(user_id, syllabus_id) / "manifest.json"


def _change_log_path(user_id: int, syllabus_id: int) -> Path:
    return _tree_dir(user_id, syllabus_id) / "change_log.jsonl"


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _atomic_append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False))
        f.write("\n")


def ensure_tree_workspace(user_id: int, syllabus_id: int, title: str | None = None, now_ts: Optional[int] = None, subject_title: str | None = None) -> dict:
    tree_dir = _tree_dir(user_id, syllabus_id)
    tree_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _manifest_path(user_id, syllabus_id)
    change_log_path = _change_log_path(user_id, syllabus_id)
    if not manifest_path.exists():
        if now_ts is None:
            now_ts = int(time())
        manifest = make_empty_tree(user_id, syllabus_id, title, int(now_ts), subject_title=subject_title)
        _atomic_write_json(manifest_path, manifest)
        change_log_path.touch(exist_ok=True)
    return {
        "tree_dir": str(tree_dir),
        "manifest_path": str(manifest_path),
        "change_log_path": str(change_log_path),
    }


def load_tree_manifest(user_id: int, syllabus_id: int) -> dict:
    manifest_path = _manifest_path(user_id, syllabus_id)
    if not manifest_path.exists():
        raise ValueError("tree manifest does not exist")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    data.setdefault("schema_version", STUDY_GRAPH_MANIFEST_VERSION)
    data.setdefault("tree_id", build_tree_id(user_id, syllabus_id))
    data.setdefault("user_id", int(user_id))
    data.setdefault("syllabus_id", int(syllabus_id))
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    data.setdefault("summary", {})
    return data


def save_tree_manifest(user_id: int, syllabus_id: int, manifest: dict) -> dict:
    manifest = dict(manifest or {})
    manifest["schema_version"] = STUDY_GRAPH_MANIFEST_VERSION
    manifest["tree_id"] = build_tree_id(user_id, syllabus_id)
    manifest["user_id"] = int(user_id)
    manifest["syllabus_id"] = int(syllabus_id)
    manifest.setdefault("nodes", [])
    manifest.setdefault("edges", [])
    manifest.setdefault("summary", {})
    manifest["updated_at"] = int(time())
    _atomic_write_json(_manifest_path(user_id, syllabus_id), manifest)
    return manifest


def get_tree(user_id: int, syllabus_id: int) -> Optional[dict]:
    manifest_path = _manifest_path(user_id, syllabus_id)
    if not manifest_path.exists():
        return None
    try:
        return load_tree_manifest(user_id, syllabus_id)
    except Exception:
        return None


def create_tree_if_missing(user_id: int, syllabus_id: int, title: str | None, now_ts: int, subject_title: str | None = None) -> dict:
    ensure_tree_workspace(user_id, syllabus_id, title=title, now_ts=now_ts, subject_title=subject_title)
    manifest = get_tree(user_id, syllabus_id)
    if manifest is None:
        manifest = make_empty_tree(user_id, syllabus_id, title, now_ts, subject_title=subject_title)
        save_tree_manifest(user_id, syllabus_id, manifest)
    elif subject_title:
        resolved_subject = str(subject_title or "").strip()
        if resolved_subject and (not manifest.get("subject_title") or manifest.get("subject_title") == manifest.get("title")):
            manifest["subject_title"] = resolved_subject
            manifest["title"] = f"{resolved_subject}学习成长树"
            manifest["virtual_root"] = build_virtual_root_node(user_id, syllabus_id, resolved_subject, now_ts)
            save_tree_manifest(user_id, syllabus_id, manifest)
    return manifest


def list_nodes(tree_id: str) -> list[dict]:
    try:
        _, user_id, syllabus_id = tree_id.split(":", 2)
        manifest = load_tree_manifest(int(user_id), int(syllabus_id))
    except Exception:
        return []
    nodes = manifest.get("nodes") if isinstance(manifest.get("nodes"), list) else []
    return sorted([node for node in nodes if isinstance(node, dict)], key=lambda node: int(node.get("first_seen_at") or 0))


def list_edges(tree_id: str) -> list[dict]:
    try:
        _, user_id, syllabus_id = tree_id.split(":", 2)
        manifest = load_tree_manifest(int(user_id), int(syllabus_id))
    except Exception:
        return []
    edges = manifest.get("edges") if isinstance(manifest.get("edges"), list) else []
    return [edge for edge in edges if isinstance(edge, dict)]


def upsert_node(tree_id: str, node: dict) -> dict:
    if not isinstance(node, dict):
        raise ValueError("node must be a dict")
    _, user_id, syllabus_id = tree_id.split(":", 2)
    manifest = load_tree_manifest(int(user_id), int(syllabus_id))
    nodes = manifest.setdefault("nodes", [])
    now_ts = int(time())
    normalized_title = node.get("normalized_title")
    node_id = node.get("node_id")
    existing = None
    if node_id:
        for item in nodes:
            if isinstance(item, dict) and item.get("node_id") == node_id:
                existing = item
                break
    if existing is None and normalized_title:
        for item in nodes:
            if isinstance(item, dict) and item.get("normalized_title") == normalized_title:
                existing = item
                break
    payload = dict(existing or {})
    payload.update(node)
    payload.setdefault("tree_id", tree_id)
    payload.setdefault("first_seen_at", now_ts)
    payload["last_updated_at"] = now_ts
    if existing is None:
        nodes.append(payload)
    else:
        existing.update(payload)
        payload = existing
    save_tree_manifest(int(user_id), int(syllabus_id), manifest)
    return payload


def upsert_edge(tree_id: str, source: str, target: str, edge_type: str, now_ts: int) -> dict:
    _, user_id, syllabus_id = tree_id.split(":", 2)
    manifest = load_tree_manifest(int(user_id), int(syllabus_id))
    edges = manifest.setdefault("edges", [])
    edge_id = f"{tree_id}:{edge_type}:{source}:{target}"
    existing = None
    for item in edges:
        if isinstance(item, dict) and item.get("edge_id") == edge_id:
            existing = item
            break
    payload = existing or {"edge_id": edge_id, "created_at": now_ts}
    payload.update(
        {
            "tree_id": tree_id,
            "source": source,
            "target": target,
            "edge_type": edge_type,
            "updated_at": now_ts,
        }
    )
    if existing is None:
        edges.append(payload)
    else:
        existing.update(payload)
        payload = existing
    save_tree_manifest(int(user_id), int(syllabus_id), manifest)
    return payload


def append_change_log(tree_id: str, entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValueError("entry must be a dict")
    _, user_id, syllabus_id = tree_id.split(":", 2)
    change_log_path = _change_log_path(int(user_id), int(syllabus_id))
    change_log_path.parent.mkdir(parents=True, exist_ok=True)
    change_log_path.touch(exist_ok=True)
    existing = get_change_log(tree_id, str(entry.get("client_change_id") or ""))
    if existing is not None:
        result = dict(existing)
        result["duplicate"] = True
        return result
    payload = dict(entry)
    payload.setdefault("tree_id", tree_id)
    payload.setdefault("created_at", int(time()))
    _atomic_append_jsonl(change_log_path, payload)
    return payload


def get_change_log(tree_id: str, client_change_id: str) -> Optional[dict]:
    try:
        _, user_id, syllabus_id = tree_id.split(":", 2)
        change_log_path = _change_log_path(int(user_id), int(syllabus_id))
    except Exception:
        return None
    if not change_log_path.exists():
        return None
    if not client_change_id:
        return None
    for line in change_log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and str(item.get("client_change_id") or "") == str(client_change_id):
            return item
    return None


def update_summary(tree_id: str, summary: dict, now_ts: int) -> dict:
    _, user_id, syllabus_id = tree_id.split(":", 2)
    manifest = load_tree_manifest(int(user_id), int(syllabus_id))
    manifest["summary"] = dict(summary or {})
    manifest["updated_at"] = int(now_ts)
    save_tree_manifest(int(user_id), int(syllabus_id), manifest)
    return manifest["summary"]
