import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from constant import BasePath
from tasks.generative.contracts import GENERATIVE_MANIFEST_VERSION, GENERATIVE_RESOURCE_TYPES


_MANIFEST_FILE_LOCK = threading.RLock()


def _get_backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_generative_root() -> Path:
    return _get_backend_root() / BasePath.GENERATIVE_ROOT.value.lstrip("/")


def _use_file_backend() -> bool:
    return bool(os.getenv("GENERATIVE_FILE_BACKEND") == "1" or os.getenv("GENERATOR_FILE_BACKEND") == "1")


def _db_available() -> bool:
    try:
        from flask import has_app_context

        return bool(has_app_context())
    except Exception:
        return False


def _require_db_backend() -> None:
    if not _db_available():
        raise RuntimeError("generated resource metadata requires a database app context; set GENERATIVE_FILE_BACKEND=1 only for tests or offline artifacts")


def normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer") from None
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def normalize_resource_type(resource_type: str) -> str:
    normalized = str(resource_type or "").strip()
    if normalized not in GENERATIVE_RESOURCE_TYPES:
        raise ValueError("resource_type must be one of " + "/".join(GENERATIVE_RESOURCE_TYPES))
    return normalized


def utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def new_resource_id(resource_type: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{resource_type}-{timestamp}-{uuid4().hex[:6]}"


def repo_relative_path(path_value: Path) -> str:
    return path_value.resolve().relative_to(_get_backend_root().resolve()).as_posix()


def read_json(path_value: Path, default: Any = None) -> Any:
    if not path_value.exists():
        return default
    try:
        return json.loads(path_value.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json file: {path_value}") from exc


def write_json(path_value: Path, payload: Dict[str, Any]) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path_value: Path, content: str) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    path_value.write_text(content, encoding="utf-8")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def get_generative_user_root(user_id: int) -> Path:
    normalized_user_id = normalize_positive_int(user_id, "user_id")
    return _get_generative_root() / f"user_{normalized_user_id}"


def ensure_generative_workspace(user_id: int) -> dict:
    user_root = get_generative_user_root(user_id)
    user_root.mkdir(parents=True, exist_ok=True)

    directories = {
        "documents_dir": user_root / "documents",
        "mindmap_dir": user_root / "mindmap",
        "quiz_dir": user_root / "quiz",
        "coding_practice_dir": user_root / "coding_practice",
        "ppt_dir": user_root / "ppt",
    }
    for path_value in directories.values():
        path_value.mkdir(parents=True, exist_ok=True)

    manifest_path = user_root / "manifest.json"
    if _use_file_backend() and not manifest_path.exists():
        now_ts = utc_timestamp()
        write_json(
            manifest_path,
            {
                "version": GENERATIVE_MANIFEST_VERSION,
                "user_id": normalize_positive_int(user_id, "user_id"),
                "resource_count": 0,
                "updated_at": now_ts,
                "resources": [],
            },
        )

    return {
        "user_root": repo_relative_path(user_root),
        "documents_dir": repo_relative_path(directories["documents_dir"]),
        "mindmap_dir": repo_relative_path(directories["mindmap_dir"]),
        "quiz_dir": repo_relative_path(directories["quiz_dir"]),
        "coding_practice_dir": repo_relative_path(directories["coding_practice_dir"]),
        "ppt_dir": repo_relative_path(directories["ppt_dir"]),
        "manifest_path": repo_relative_path(manifest_path),
    }


def load_manifest(user_id: int) -> dict:
    if not _use_file_backend():
        _require_db_backend()
        return _load_manifest_db(user_id)
    ensure_generative_workspace(user_id)
    manifest_path = get_generative_user_root(user_id) / "manifest.json"
    manifest = read_json(manifest_path, default=None)
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain a JSON object")
    manifest.setdefault("user_id", normalize_positive_int(user_id, "user_id"))
    manifest.setdefault("resources", [])
    if not isinstance(manifest["resources"], list):
        raise ValueError("manifest.json resources must be a list")
    manifest.setdefault("version", GENERATIVE_MANIFEST_VERSION)
    manifest["resource_count"] = len(manifest["resources"])
    manifest.setdefault("updated_at", utc_timestamp())
    return manifest


def save_manifest(user_id: int, manifest: dict) -> None:
    if not _use_file_backend():
        _require_db_backend()
        _save_manifest_db(user_id, manifest)
        return
    manifest["version"] = GENERATIVE_MANIFEST_VERSION
    manifest["user_id"] = normalize_positive_int(user_id, "user_id")
    manifest["resource_count"] = len(manifest.get("resources") or [])
    manifest["updated_at"] = utc_timestamp()
    manifest_path = get_generative_user_root(user_id) / "manifest.json"
    write_json(manifest_path, manifest)


def append_manifest_entry(user_id: int, entry: dict) -> dict:
    if not _use_file_backend():
        _require_db_backend()
        _append_manifest_entry_db(user_id, entry)
        return entry
    with _MANIFEST_FILE_LOCK:
        manifest = load_manifest(user_id)
        manifest["resources"].append(entry)
        save_manifest(user_id, manifest)
    return entry


def _resource_row_to_entry(row: Any, files: list[Any] | None = None) -> dict:
    main_files = _json_loads(getattr(row, "main_files_json", None), {})
    if not isinstance(main_files, dict):
        main_files = {}
    for item in files or []:
        if getattr(item, "file_role", None) and getattr(item, "path_or_url", None):
            main_files.setdefault(item.file_role, item.path_or_url)
    return {
        "resource_id": row.resource_id,
        "resource_type": row.resource_type,
        "title": row.title,
        "topic": row.topic,
        "user_id": row.user_id,
        "syllabus_id": row.syllabus_id,
        "status": row.status,
        "resource_dir": row.resource_dir,
        "main_files": main_files,
        "validation": _json_loads(row.validation_json, {}) or {},
        "metadata": _json_loads(row.metadata_json, {}) or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _load_manifest_db(user_id: int) -> dict:
    from schemas.agent_runtime_state import GeneratedResource, GeneratedResourceFile

    normalized_user_id = normalize_positive_int(user_id, "user_id")
    rows = GeneratedResource.query.filter_by(user_id=normalized_user_id).order_by(GeneratedResource.created_at.asc()).all()
    resources = []
    for row in rows:
        files = GeneratedResourceFile.query.filter_by(resource_id=row.resource_id).all()
        resources.append(_resource_row_to_entry(row, files))
    now_ts = utc_timestamp()
    updated_at = max([int(item.get("updated_at") or 0) for item in resources] or [now_ts])
    return {
        "version": GENERATIVE_MANIFEST_VERSION,
        "user_id": normalized_user_id,
        "resource_count": len(resources),
        "updated_at": updated_at,
        "resources": resources,
    }


def _save_manifest_db(user_id: int, manifest: dict) -> None:
    for entry in list((manifest or {}).get("resources") or []):
        if isinstance(entry, dict):
            _append_manifest_entry_db(user_id, entry)


def _append_manifest_entry_db(user_id: int, entry: dict) -> None:
    from extensions import db
    from schemas.agent_runtime_state import GeneratedResource, GeneratedResourceFile

    normalized_user_id = normalize_positive_int(user_id, "user_id")
    payload = dict(entry or {})
    resource_id = str(payload.get("resource_id") or "").strip()
    if not resource_id:
        return
    now_ts = utc_timestamp()
    row = db.session.get(GeneratedResource, resource_id)
    if row is None:
        row = GeneratedResource(resource_id=resource_id)
        db.session.add(row)
    row.user_id = normalized_user_id
    row.syllabus_id = payload.get("syllabus_id")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    row.step_id = metadata.get("step_id") or metadata.get("current_step_id")
    row.resource_type = str(payload.get("resource_type") or "")
    row.title = str(payload.get("title") or "")
    row.topic = str(payload.get("topic") or "")
    row.status = str(payload.get("status") or "ready")
    row.resource_dir = str(payload.get("resource_dir") or "")
    row.validation_json = _json_dumps(payload.get("validation") if isinstance(payload.get("validation"), dict) else {})
    row.metadata_json = _json_dumps(metadata)
    main_files = payload.get("main_files") if isinstance(payload.get("main_files"), dict) else {}
    row.main_files_json = _json_dumps(main_files)
    row.created_at = int(payload.get("created_at") or row.created_at or now_ts)
    row.updated_at = int(payload.get("updated_at") or now_ts)
    db.session.flush()  # 确保 resource 先入库，避免子表 FK 约束失败
    for role, path_or_url in main_files.items():
        if not path_or_url:
            continue
        file_row = GeneratedResourceFile.query.filter_by(resource_id=resource_id, file_role=str(role)).first()
        if file_row is None:
            file_row = GeneratedResourceFile(resource_id=resource_id, file_role=str(role))
            db.session.add(file_row)
        file_row.path_or_url = str(path_or_url)
        file_row.mime_type = ""
        file_row.created_at = file_row.created_at or now_ts
    db.session.commit()
