import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from constant import BasePath
from tasks.generative.contracts import GENERATIVE_MANIFEST_VERSION, GENERATIVE_RESOURCE_TYPES


def _get_backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_generative_root() -> Path:
    return _get_backend_root() / BasePath.GENERATIVE_ROOT.value.lstrip("/")


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
    if not manifest_path.exists():
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
    manifest["version"] = GENERATIVE_MANIFEST_VERSION
    manifest["user_id"] = normalize_positive_int(user_id, "user_id")
    manifest["resource_count"] = len(manifest.get("resources") or [])
    manifest["updated_at"] = utc_timestamp()
    manifest_path = get_generative_user_root(user_id) / "manifest.json"
    write_json(manifest_path, manifest)


def append_manifest_entry(user_id: int, entry: dict) -> dict:
    manifest = load_manifest(user_id)
    manifest["resources"].append(entry)
    save_manifest(user_id, manifest)
    return entry
