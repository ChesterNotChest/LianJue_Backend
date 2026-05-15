import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from repositories.material_repo import (
    get_material_by_id,
    list_materials_by_syllabus,
    set_material_path,
    set_material_title,
)
from repositories.syllabusmaterial_repo import (
    create_syllabus_material,
    get_syllabusmaterials_by_material,
    remove_syllabusmaterial,
)
from tasks import generative_task


def _normalize_involved_weeks(involved_weeks: Any) -> List[int]:
    weeks = []
    if not isinstance(involved_weeks, list):
        return weeks
    for value in involved_weeks:
        try:
            week_index = int(value)
        except (TypeError, ValueError):
            continue
        if week_index not in weeks:
            weeks.append(week_index)
    return weeks


def _read_json_file(path_value: str) -> Optional[dict]:
    if not isinstance(path_value, str) or not path_value.strip() or not os.path.exists(path_value):
        return None
    try:
        with open(path_value, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_file(path_value: str, payload: dict) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    try:
        os.makedirs(os.path.dirname(path_value) or ".", exist_ok=True)
        with open(path_value, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _get_backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_repo_path(path_value: Any) -> Optional[Path]:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return path_obj
    return _get_backend_root() / path_obj


def _read_text_file(path_value: Any) -> Optional[str]:
    resolved = _resolve_repo_path(path_value)
    if resolved is None or not resolved.exists():
        return None
    try:
        return resolved.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_resource_json(path_value: Any) -> Optional[dict]:
    resolved = _resolve_repo_path(path_value)
    if resolved is None or not resolved.exists():
        return None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_material_title(payload: dict) -> Optional[str]:
    for key in ("material_title", "title", "resource_title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sync_material_week_bindings(
    material_id: int,
    syllabus_id: int,
    involved_weeks: Any,
    default_ok_to_recommend: bool = False,
) -> None:
    if material_id is None or syllabus_id is None:
        return

    target_weeks = set(_normalize_involved_weeks(involved_weeks))
    existing_rows = [
        row
        for row in get_syllabusmaterials_by_material(material_id)
        if getattr(row, "syllabus_id", None) == syllabus_id
    ]
    existing_by_week = {
        int(getattr(row, "week_index")): row
        for row in existing_rows
        if getattr(row, "week_index", None) is not None
    }

    for week_index in existing_by_week:
        if week_index not in target_weeks:
            remove_syllabusmaterial(material_id, syllabus_id, week_index)

    for week_index in target_weeks:
        existing = existing_by_week.get(week_index)
        ok_to_recommend = (
            getattr(existing, "ok_to_recommend", default_ok_to_recommend)
            if existing
            else default_ok_to_recommend
        )
        create_syllabus_material(
            material_id,
            syllabus_id,
            week_index,
            ok_to_recommend=ok_to_recommend,
        )


def _is_missing_path(path_value) -> bool:
    return not isinstance(path_value, str) or not path_value.strip()


def get_material_status(material_id: int) -> dict:
    """Return material status flags for draft/final readiness."""
    material = get_material_by_id(material_id)
    if not material:
        return None

    draft_path = getattr(material, 'draft_material_path', None)
    final_path = getattr(material, 'material_path', None)

    return {
        'is_material_draft_path_null': _is_missing_path(draft_path),
        'is_material_path_null': _is_missing_path(final_path),
    }


def update_material_draft_json(material_id: int, material_draft_json: dict):
    """Deprecated draft mutation entry."""
    return None


def update_final_material_json(material_id: int, material_json: dict):
    """Replace the stored final/display JSON for a material."""
    if not isinstance(material_json, dict):
        return None

    material = get_material_by_id(material_id)
    if not material:
        return None

    final_path = getattr(material, "material_path", None)
    if not final_path or not os.path.exists(final_path):
        return None

    if not _write_json_file(final_path, material_json):
        return None

    set_material_path(material_id, final_path)
    _sync_material_week_bindings(
        material_id,
        int(getattr(material, "syllabus_id", None)),
        material_json.get("involved_weeks") or material_json.get("weeks"),
        default_ok_to_recommend=False,
    )

    title = _extract_material_title(material_json)
    if title:
        set_material_title(material_id, title)

    return get_material_by_id(material_id)


def get_material_draft_detail_info(material_id: int) -> Optional[dict]:
    """Deprecated draft detail entry."""
    return None


def get_material_detail_info(material_id: int) -> Optional[dict]:
    """Return a wrapper around the stored final/display JSON."""
    material = get_material_by_id(material_id)
    if not material:
        return None
    material_path = getattr(material, "material_path", None)
    content = _read_json_file(material_path)
    if content is None:
        return None
    resource_type = content.get("resource_type") or content.get("type")
    return {
        "material_id": getattr(material, "material_id", None),
        "resource_id": content.get("resource_id"),
        "resource_type": resource_type,
        "title": _extract_material_title(content) or getattr(material, "title", None),
        "syllabus_id": getattr(material, "syllabus_id", None),
        "status": content.get("status") or "ready",
        "main_files": {
            "json_path": material_path,
        },
        "content": content,
        "create_time": getattr(material, "create_time", None),
    }


def _resource_summary_from_entry(entry: dict) -> dict:
    return {
        "resource_id": entry.get("resource_id"),
        "resource_type": entry.get("resource_type"),
        "title": entry.get("title"),
        "topic": entry.get("topic"),
        "syllabus_id": entry.get("syllabus_id"),
        "status": entry.get("status"),
        "resource_dir": entry.get("resource_dir"),
        "main_files": entry.get("main_files") if isinstance(entry.get("main_files"), dict) else {},
        "validation": entry.get("validation") if isinstance(entry.get("validation"), dict) else {},
        "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
    }


def _entry_matches(entry: dict, syllabus_id: Optional[int], resource_type: Optional[str]) -> bool:
    if syllabus_id is not None:
        try:
            if int(entry.get("syllabus_id")) != int(syllabus_id):
                return False
        except (TypeError, ValueError):
            return False
    if resource_type and str(entry.get("resource_type") or "") != str(resource_type):
        return False
    return True


def list_generated_resources(
    user_id: int,
    syllabus_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[dict]:
    """List generated resource summaries from the per-user manifest."""
    manifest = generative_task.load_manifest(int(user_id))
    entries = [
        _resource_summary_from_entry(entry)
        for entry in manifest.get("resources", [])
        if isinstance(entry, dict) and _entry_matches(entry, syllabus_id, resource_type)
    ]
    entries.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    if limit is not None:
        try:
            limit_value = max(0, int(limit))
        except (TypeError, ValueError):
            limit_value = 0
        entries = entries[:limit_value]
    return entries


def list_generated_resources_by_type(
    user_id: int,
    syllabus_id: Optional[int] = None,
    limit_per_type: Optional[int] = None,
) -> Dict[str, List[dict]]:
    """Group generated resource summaries by resource_type."""
    resources = list_generated_resources(user_id=user_id, syllabus_id=syllabus_id)
    grouped: Dict[str, List[dict]] = {}
    for item in resources:
        key = str(item.get("resource_type") or "unknown")
        grouped.setdefault(key, []).append(item)
    if limit_per_type is not None:
        try:
            limit_value = max(0, int(limit_per_type))
        except (TypeError, ValueError):
            limit_value = 0
        grouped = {key: value[:limit_value] for key, value in grouped.items()}
    return grouped


def get_generated_resource_detail(user_id: int, resource_id: str) -> Optional[dict]:
    """Return a render-ready detail wrapper for a generated resource."""
    if not resource_id:
        return None
    manifest = generative_task.load_manifest(int(user_id))
    entry = None
    for item in manifest.get("resources", []):
        if isinstance(item, dict) and str(item.get("resource_id") or "") == str(resource_id):
            entry = item
            break
    if not entry:
        return None

    summary = _resource_summary_from_entry(entry)
    main_files = summary["main_files"]
    content = _read_resource_json(main_files.get("json_path"))
    if content is None:
        return None

    render = {}
    if main_files.get("md_path"):
        render["markdown"] = _read_text_file(main_files.get("md_path"))
    if main_files.get("mermaid_path"):
        render["mermaid"] = _read_text_file(main_files.get("mermaid_path"))

    return {
        **summary,
        "content": content,
        "render": render,
    }


def list_materials_brief_info(syllabus_id: int):
    """List material records for a syllabus."""
    items = []
    for material in list_materials_by_syllabus(syllabus_id):
        items.append({
            "material_id": getattr(material, "material_id", None),
            "file_id": getattr(material, "file_id", None),
            "title": getattr(material, "title", None),
            "final_path": getattr(material, "material_path", None),
            "pdf_path": getattr(material, "pdf_path", None),
            "create_time": getattr(material, "create_time", None),
        })
    return items


def list_materials_draft_brief_info(syllabus_id: int):
    """Deprecated draft list alias."""
    return list_materials_brief_info(syllabus_id)


def publish_material(material_id: int, new_pdf: bool = False, do_publish: bool = False):
    """Deprecated legacy publish entry.

    Generated resources should be rendered directly by their resource renderer.
    """
    return None
