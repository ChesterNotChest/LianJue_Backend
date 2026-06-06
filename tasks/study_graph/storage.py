import json
import os
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


def _use_file_backend() -> bool:
    return bool(os.getenv("STUDY_GRAPH_FILE_BACKEND") == "1")


def _db_available() -> bool:
    try:
        from flask import has_app_context

        return bool(has_app_context())
    except Exception:
        return False


def _require_db_backend() -> None:
    if not _db_available():
        raise RuntimeError("study graph persistence requires a database app context; set STUDY_GRAPH_FILE_BACKEND=1 only for tests or offline artifacts")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


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
    if not _use_file_backend():
        _require_db_backend()
        return _ensure_tree_db(user_id, syllabus_id, title, now_ts, subject_title)
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
    if not _use_file_backend():
        _require_db_backend()
        return _load_tree_manifest_db(user_id, syllabus_id)
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
    if not _use_file_backend():
        _require_db_backend()
        return _save_tree_manifest_db(user_id, syllabus_id, manifest)
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
    if not _use_file_backend():
        _require_db_backend()
        try:
            return _load_tree_manifest_db(user_id, syllabus_id)
        except Exception:
            return None
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
    if not _use_file_backend():
        _require_db_backend()
        return _list_nodes_db(tree_id)
    try:
        _, user_id, syllabus_id = tree_id.split(":", 2)
        manifest = load_tree_manifest(int(user_id), int(syllabus_id))
    except Exception:
        return []
    nodes = manifest.get("nodes") if isinstance(manifest.get("nodes"), list) else []
    return sorted([node for node in nodes if isinstance(node, dict)], key=lambda node: int(node.get("first_seen_at") or 0))


def list_edges(tree_id: str) -> list[dict]:
    if not _use_file_backend():
        _require_db_backend()
        return _list_edges_db(tree_id)
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
    wall_clock_ts = int(time())
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
    first_seen_at = payload.get("first_seen_at")
    try:
        payload["first_seen_at"] = int(first_seen_at)
    except Exception:
        payload["first_seen_at"] = wall_clock_ts
    last_updated_at = node.get("last_updated_at", payload.get("last_updated_at"))
    try:
        payload["last_updated_at"] = int(last_updated_at)
    except Exception:
        payload["last_updated_at"] = wall_clock_ts
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
    if not _use_file_backend():
        _require_db_backend()
        return _append_change_log_db(tree_id, entry)
    _, user_id, syllabus_id = tree_id.split(":", 2)
    change_log_path = _change_log_path(int(user_id), int(syllabus_id))
    change_log_path.parent.mkdir(parents=True, exist_ok=True)
    change_log_path.touch(exist_ok=True)
    payload = dict(entry)
    client_change_id = str(payload.get("client_change_id") or "").strip()
    payload.setdefault("tree_id", tree_id)
    payload.setdefault("created_at", int(time()))
    if not client_change_id:
        payload["ignored"] = True
        return payload
    existing = get_change_log(tree_id, client_change_id)
    if existing is not None:
        result = dict(existing)
        result["duplicate"] = True
        return result
    _atomic_append_jsonl(change_log_path, payload)
    return payload


def get_change_log(tree_id: str, client_change_id: str) -> Optional[dict]:
    if not _use_file_backend():
        _require_db_backend()
        return _get_change_log_db(tree_id, client_change_id)
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


def _ensure_tree_db(user_id: int, syllabus_id: int, title: str | None = None, now_ts: Optional[int] = None, subject_title: str | None = None) -> dict:
    if now_ts is None:
        now_ts = int(time())
    manifest = get_tree(user_id, syllabus_id)
    if manifest is None:
        manifest = make_empty_tree(user_id, syllabus_id, title, int(now_ts), subject_title=subject_title)
        _save_tree_manifest_db(user_id, syllabus_id, manifest)
    return {
        "tree_dir": "",
        "manifest_path": f"db://study_graph_tree/{build_tree_id(user_id, syllabus_id)}",
        "change_log_path": f"db://study_graph_change_log/{build_tree_id(user_id, syllabus_id)}",
    }


def _load_tree_manifest_db(user_id: int, syllabus_id: int) -> dict:
    from extensions import db
    from schemas.agent_runtime_state import StudyGraphTree

    tree_id = build_tree_id(user_id, syllabus_id)
    row = db.session.get(StudyGraphTree, tree_id)
    if row is None:
        raise ValueError("tree manifest does not exist")
    data = _json_loads(row.manifest_json, None)
    if not isinstance(data, dict):
        data = {
            "schema_version": STUDY_GRAPH_MANIFEST_VERSION,
            "tree_id": tree_id,
            "user_id": int(user_id),
            "syllabus_id": int(syllabus_id),
            "subject_title": row.subject_title or "",
            "title": row.title or "",
            "virtual_root": build_virtual_root_node(user_id, syllabus_id, row.subject_title or row.title or "", int(row.updated_at or time())),
            "nodes": _list_nodes_db(tree_id),
            "edges": _list_edges_db(tree_id),
            "summary": _json_loads(row.summary_json, {}) or {},
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    data.setdefault("schema_version", STUDY_GRAPH_MANIFEST_VERSION)
    data.setdefault("tree_id", tree_id)
    data.setdefault("user_id", int(user_id))
    data.setdefault("syllabus_id", int(syllabus_id))
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    data.setdefault("summary", {})
    return data


def _save_tree_manifest_db(user_id: int, syllabus_id: int, manifest: dict) -> dict:
    from extensions import db
    from schemas.agent_runtime_state import StudyGraphEdge, StudyGraphNode, StudyGraphTree

    manifest = dict(manifest or {})
    tree_id = build_tree_id(user_id, syllabus_id)
    now_ts = int(time())
    manifest["schema_version"] = STUDY_GRAPH_MANIFEST_VERSION
    manifest["tree_id"] = tree_id
    manifest["user_id"] = int(user_id)
    manifest["syllabus_id"] = int(syllabus_id)
    manifest.setdefault("nodes", [])
    manifest.setdefault("edges", [])
    manifest.setdefault("summary", {})
    manifest["updated_at"] = int(manifest.get("updated_at") or now_ts)
    row = db.session.get(StudyGraphTree, tree_id)
    if row is None:
        row = StudyGraphTree(tree_id=tree_id)
        db.session.add(row)
    row.user_id = int(user_id)
    row.syllabus_id = int(syllabus_id)
    row.subject_title = str(manifest.get("subject_title") or "")
    row.title = str(manifest.get("title") or "")
    row.summary_json = _json_dumps(manifest.get("summary") or {})
    row.manifest_json = _json_dumps(manifest)
    row.created_at = int(manifest.get("created_at") or row.created_at or now_ts)
    row.updated_at = int(manifest.get("updated_at") or now_ts)

    for node in manifest.get("nodes") or []:
        if not isinstance(node, dict) or not node.get("node_id"):
            continue
        node_row = db.session.get(StudyGraphNode, str(node.get("node_id")))
        if node_row is None:
            node_row = StudyGraphNode(node_id=str(node.get("node_id")))
            db.session.add(node_row)
        node_row.tree_id = tree_id
        node_row.type = str(node.get("type") or "knowledge")
        node_row.title = str(node.get("title") or "")
        node_row.normalized_title = str(node.get("normalized_title") or node.get("title") or "")
        node_row.aliases_json = _json_dumps(node.get("aliases") or [])
        node_row.summary = str(node.get("summary") or "")
        node_row.parent_node_id = node.get("parent_node_id")
        mastery = node.get("mastery") if isinstance(node.get("mastery"), dict) else {}
        node_row.mastery_json = _json_dumps(mastery)
        node_row.mastery_label = mastery.get("label")
        try:
            node_row.mastery_score = float(mastery.get("score")) if mastery.get("score") is not None else None
        except Exception:
            node_row.mastery_score = None
        node_row.display_json = _json_dumps(node.get("display") if isinstance(node.get("display"), dict) else {})
        node_row.source_json = _json_dumps(node.get("source") if isinstance(node.get("source"), dict) else {})
        node_row.first_seen_at = int(node.get("first_seen_at") or now_ts)
        node_row.last_updated_at = int(node.get("last_updated_at") or now_ts)

    for edge in manifest.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source") or edge.get("source_node_id")
        target = edge.get("target") or edge.get("target_node_id")
        edge_type = edge.get("edge_type") or "parent_of"
        edge_id = edge.get("edge_id") or f"{tree_id}:{edge_type}:{source}:{target}"
        if not source or not target:
            continue
        edge_row = db.session.get(StudyGraphEdge, str(edge_id))
        if edge_row is None:
            edge_row = StudyGraphEdge(edge_id=str(edge_id))
            db.session.add(edge_row)
        edge_row.tree_id = tree_id
        edge_row.source_node_id = str(source)
        edge_row.target_node_id = str(target)
        edge_row.edge_type = str(edge_type)
        edge_row.created_at = int(edge.get("created_at") or edge_row.created_at or now_ts)
        edge_row.updated_at = int(edge.get("updated_at") or now_ts)
    db.session.commit()
    return manifest


def _list_nodes_db(tree_id: str) -> list[dict]:
    from schemas.agent_runtime_state import StudyGraphNode

    rows = StudyGraphNode.query.filter_by(tree_id=tree_id).order_by(StudyGraphNode.first_seen_at.asc()).all()
    result = []
    for row in rows:
        mastery = _json_loads(row.mastery_json, {}) or {}
        result.append(
            {
                "node_id": row.node_id,
                "tree_id": row.tree_id,
                "type": row.type,
                "title": row.title,
                "normalized_title": row.normalized_title,
                "aliases": _json_loads(row.aliases_json, []) or [],
                "summary": row.summary or "",
                "parent_node_id": row.parent_node_id,
                "mastery": mastery,
                "display": _json_loads(row.display_json, {}) or {},
                "source": _json_loads(row.source_json, {}) or {},
                "first_seen_at": row.first_seen_at,
                "last_updated_at": row.last_updated_at,
            }
        )
    return result


def _list_edges_db(tree_id: str) -> list[dict]:
    from schemas.agent_runtime_state import StudyGraphEdge

    rows = StudyGraphEdge.query.filter_by(tree_id=tree_id).order_by(StudyGraphEdge.created_at.asc()).all()
    return [
        {
            "edge_id": row.edge_id,
            "tree_id": row.tree_id,
            "source": row.source_node_id,
            "target": row.target_node_id,
            "edge_type": row.edge_type,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def _append_change_log_db(tree_id: str, entry: dict) -> dict:
    from extensions import db
    from schemas.agent_runtime_state import StudyGraphChangeLog

    payload = dict(entry)
    client_change_id = str(payload.get("client_change_id") or "").strip()
    payload.setdefault("tree_id", tree_id)
    payload.setdefault("created_at", int(time()))
    if not client_change_id:
        payload["ignored"] = True
        return payload
    existing = _get_change_log_db(tree_id, client_change_id)
    if existing is not None:
        result = dict(existing)
        result["duplicate"] = True
        return result
    row = StudyGraphChangeLog(tree_id=tree_id, client_change_id=client_change_id)
    row.status = str(payload.get("status") or "")
    row.request_json = _json_dumps(payload.get("request") if isinstance(payload.get("request"), dict) else {})
    row.result_json = _json_dumps(payload.get("result") if isinstance(payload.get("result"), dict) else {})
    row.reason = str(payload.get("reason") or "")
    row.entry_json = _json_dumps(payload)
    row.created_at = int(payload.get("created_at") or time())
    db.session.add(row)
    db.session.commit()
    return payload


def _get_change_log_db(tree_id: str, client_change_id: str) -> Optional[dict]:
    from schemas.agent_runtime_state import StudyGraphChangeLog

    if not client_change_id:
        return None
    row = StudyGraphChangeLog.query.filter_by(tree_id=tree_id, client_change_id=str(client_change_id)).first()
    if row is None:
        return None
    payload = _json_loads(row.entry_json, None)
    if isinstance(payload, dict):
        return payload
    return {
        "tree_id": row.tree_id,
        "client_change_id": row.client_change_id,
        "status": row.status,
        "request": _json_loads(row.request_json, {}) or {},
        "result": _json_loads(row.result_json, {}) or {},
        "reason": row.reason,
        "created_at": row.created_at,
    }
