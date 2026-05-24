import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from tasks import generative_task
from tasks.generative.storage import _get_backend_root


bp = Blueprint("generative_api", __name__, url_prefix="/api")


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


def _entry_matches(entry: dict, syllabus_id=None, resource_type=None) -> bool:
    if syllabus_id is not None:
        try:
            if int(entry.get("syllabus_id")) != int(syllabus_id):
                return False
        except (TypeError, ValueError):
            return False
    if resource_type and str(entry.get("resource_type") or "") != str(resource_type):
        return False
    return True


def _resolve_repo_path(path_value):
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path_obj = Path(path_value)
    if path_obj.is_absolute():
        return path_obj
    return _get_backend_root() / path_obj


def _read_text_file(path_value):
    resolved = _resolve_repo_path(path_value)
    if resolved is None or not resolved.exists():
        return None
    try:
        return resolved.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_resource_json(path_value):
    resolved = _resolve_repo_path(path_value)
    if resolved is None or not resolved.exists():
        return None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


@bp.route("/generative_generate", methods=["POST"])
def generative_generate_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    question = data.get("question") or data.get("student_question")
    resource_types = data.get("resource_types") or data.get("resource_type")

    if not user_id or not question or not resource_types:
        return jsonify(
            {
                "success": False,
                "resources": [],
                "error_message": "missing user_id/question/resource_types",
                "error_code": "missing_fields",
            }
        ), 400

    try:
        result = generative_task.run_resource_generation_agent(data)
        return jsonify(
            {
                "success": bool(result.get("success")),
                "request": result.get("request"),
                "resources": result.get("resources") or [],
                "resource_count": int(result.get("resource_count") or 0),
                "success_count": int(result.get("success_count") or 0),
                "failed_count": int(result.get("failed_count") or 0),
                "tool_trace": result.get("tool_trace") or [],
                "error_message": result.get("error_message") or "",
                "error_code": result.get("error_code") or "",
            }
        ), 200
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "resources": [],
                "error_message": str(e),
                "error_code": "exception",
            }
        ), 500


@bp.route("/generative_list", methods=["POST"])
def generative_list_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify(
            {
                "success": False,
                "materials": [],
                "error_message": "missing user_id",
                "error_code": "missing_fields",
            }
        ), 400

    syllabus_id = data.get("syllabus_id")
    resource_type = data.get("resource_type")
    limit = data.get("limit")
    try:
        manifest = generative_task.load_manifest(int(user_id))
        rows = [
            _resource_summary_from_entry(entry)
            for entry in manifest.get("resources", [])
            if isinstance(entry, dict)
            and _entry_matches(
                entry,
                syllabus_id=int(syllabus_id) if syllabus_id not in (None, "") else None,
                resource_type=str(resource_type) if resource_type not in (None, "") else None,
            )
        ]
        rows.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
        if limit is not None:
            try:
                rows = rows[: max(0, int(limit))]
            except (TypeError, ValueError):
                rows = []
        return jsonify(
            {
                "success": True,
                "materials": rows,
                "error_message": "",
                "error_code": "",
            }
        ), 200
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "materials": [],
                "error_message": str(e),
                "error_code": "exception",
            }
        ), 500


@bp.route("/generative_detail", methods=["POST"])
def generative_detail_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    resource_id = data.get("resource_id")
    if not user_id or not resource_id:
        return jsonify(
            {
                "success": False,
                "material": None,
                "error_message": "missing user_id/resource_id",
                "error_code": "missing_fields",
            }
        ), 400

    try:
        manifest = generative_task.load_manifest(int(user_id))
        entry = None
        for item in manifest.get("resources", []):
            if isinstance(item, dict) and str(item.get("resource_id") or "") == str(resource_id):
                entry = item
                break
        if not entry:
            material = None
        else:
            summary = _resource_summary_from_entry(entry)
            main_files = summary["main_files"]
            content = _read_resource_json(main_files.get("json_path"))
            render = {}
            if main_files.get("md_path"):
                render["markdown"] = _read_text_file(main_files.get("md_path"))
            if main_files.get("mermaid_path"):
                render["mermaid"] = _read_text_file(main_files.get("mermaid_path"))
            material = {
                **summary,
                "content": content,
                "render": render,
            }
        if not material:
            return jsonify(
                {
                    "success": False,
                    "material": None,
                    "error_message": "not found",
                    "error_code": "not_found",
                }
            ), 404
        return jsonify(
            {
                "success": True,
                "material": material,
                "error_message": "",
                "error_code": "",
            }
        ), 200
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "material": None,
                "error_message": str(e),
                "error_code": "exception",
            }
        ), 500
