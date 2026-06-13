from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION = "recommendation_snapshot.v1"
RECOMMENDATION_SNAPSHOT_ID_PREFIX = "recommendation"

RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED = "proposed"
RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED = "accepted"
RECOMMENDATION_SNAPSHOT_STATUS_EXPIRED = "expired"

RECOMMENDATION_SNAPSHOT_ROOT_DIR = "personal_recommendation/recommendation_snapshot"
RECOMMENDATION_SNAPSHOT_FILE_BACKEND_ENV = "RECOMMENDATION_SNAPSHOT_FILE_BACKEND"

RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND = "recommendation_snapshot_not_found"
RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE = "invalid_candidate"

RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED = "recommendation_snapshot_save_failed"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _snapshot_root() -> Path:
    override = os.getenv("PERSONAL_RECOMMENDATION_ROOT")
    if override:
        return Path(override) / "recommendation_snapshot"
    return _backend_root() / RECOMMENDATION_SNAPSHOT_ROOT_DIR


def _use_file_backend() -> bool:
    try:
        from flask import current_app, has_app_context

        if has_app_context() and bool(getattr(current_app, "testing", False)):
            return True
    except Exception:
        pass
    return bool(
        os.getenv("PERSONAL_RECOMMENDATION_ROOT")
        or os.getenv(RECOMMENDATION_SNAPSHOT_FILE_BACKEND_ENV) == "1"
    )


def _db_available() -> bool:
    try:
        from flask import has_app_context

        return bool(has_app_context())
    except Exception:
        return False


def _require_db_backend() -> None:
    if not _db_available():
        raise RuntimeError(
            "recommendation snapshot persistence requires a database app context; "
            "set PERSONAL_RECOMMENDATION_ROOT or RECOMMENDATION_SNAPSHOT_FILE_BACKEND=1 only for tests or offline artifacts"
        )


def _normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer") from None
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def _normalize_optional_positive_int(value: Any, field_name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    return _normalize_positive_int(value, field_name)


def _utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _new_recommendation_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{RECOMMENDATION_SNAPSHOT_ID_PREFIX}_{timestamp}_{uuid4().hex[:6]}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _snapshot_dir(user_id: int, syllabus_id: Optional[int]) -> Path:
    root = _snapshot_root() / f"user_{_normalize_positive_int(user_id, 'user_id')}"
    if syllabus_id is not None:
        root = root / f"syllabus_{_normalize_positive_int(syllabus_id, 'syllabus_id')}"
    return root


def _snapshot_path(user_id: int, syllabus_id: Optional[int], recommendation_id: str) -> Path:
    return _snapshot_dir(user_id, syllabus_id) / f"{recommendation_id}.json"


def _iter_snapshot_files(user_id: int, syllabus_id: Optional[int] = None) -> list[Path]:
    if syllabus_id is not None:
        root = _snapshot_dir(user_id, syllabus_id)
        return sorted(root.glob("*.json")) if root.exists() else []
    user_root = _snapshot_root() / f"user_{_normalize_positive_int(user_id, 'user_id')}"
    if not user_root.exists():
        return []
    files = list(user_root.glob("*.json"))
    files.extend(user_root.glob("syllabus_*/*.json"))
    return sorted(files)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _build_goal_payload(request_payload: Optional[dict], session_id: Optional[str]) -> dict:
    payload = _as_dict(request_payload)
    result = {
        "goals": _as_list(payload.get("goals")),
        "learning_goal": str(payload.get("learning_goal") or "").strip(),
        "message": str(payload.get("message") or "").strip(),
        "question": str(payload.get("question") or "").strip(),
        "session_id": str(session_id or payload.get("session_id") or "").strip(),
    }
    return {key: value for key, value in result.items() if value not in ("", [])}


def _node_title_lookup(graph: dict) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for node in _as_list(_as_dict(graph).get("nodes")):
        if isinstance(node, dict) and node.get("id") is not None:
            lookup[str(node.get("id"))] = str(node.get("title") or node.get("id") or "")
    return lookup


def _build_result_summary(recommendation_result: dict) -> dict:
    graph = _as_dict(recommendation_result.get("graph"))
    candidates = _as_list(recommendation_result.get("candidates"))
    selected = _as_list(recommendation_result.get("selected"))
    best_path = _as_dict(recommendation_result.get("best_path"))
    title_lookup = _node_title_lookup(graph)
    path = [str(node_id) for node_id in _as_list(best_path.get("path"))]
    return {
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "node_count": len(_as_list(graph.get("nodes"))),
        "edge_count": len(_as_list(graph.get("edges"))),
        "best_path": path,
        "best_path_titles": [title_lookup.get(node_id, node_id) for node_id in path],
    }


def _snapshot_payload(
    *,
    recommendation_id: str,
    user_id: int,
    syllabus_id: Optional[int],
    recommendation_result: dict,
    request_payload: Optional[dict],
    session_id: Optional[str],
    status: str,
    created_at: int,
    updated_at: int,
    accepted_plan_id: Optional[str] = None,
    accepted_candidate_index: Optional[int] = None,
    expires_at: Optional[int] = None,
) -> dict:
    goal_payload = _build_goal_payload(request_payload, session_id)
    return {
        "recommendation_id": recommendation_id,
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "session_id": goal_payload.get("session_id") or None,
        "status": status,
        "schema_version": RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION,
        "goal": goal_payload,
        "query_text": goal_payload.get("message") or goal_payload.get("question") or goal_payload.get("learning_goal") or "",
        "recommendation": {
            "graph": _as_dict(recommendation_result.get("graph")),
            "candidates": _as_list(recommendation_result.get("candidates")),
            "selected": _as_list(recommendation_result.get("selected")),
            "best_path": _as_dict(recommendation_result.get("best_path")),
            "rag_overlay": _as_dict(recommendation_result.get("rag_overlay")),
            "planning_hints": _as_dict(recommendation_result.get("planning_hints")),
            "debug": _as_dict(recommendation_result.get("debug")),
        },
        "summary": _build_result_summary(recommendation_result),
        "accepted_plan_id": accepted_plan_id,
        "accepted_candidate_index": accepted_candidate_index,
        "created_at": created_at,
        "updated_at": updated_at,
        "expires_at": expires_at,
    }


def _summary_item(snapshot: dict) -> dict:
    summary = _as_dict(snapshot.get("summary"))
    return {
        "recommendation_id": snapshot.get("recommendation_id") or "",
        "user_id": snapshot.get("user_id"),
        "syllabus_id": snapshot.get("syllabus_id"),
        "session_id": snapshot.get("session_id") or "",
        "status": snapshot.get("status") or RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
        "schema_version": snapshot.get("schema_version") or RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION,
        "candidate_count": int(summary.get("candidate_count") or 0),
        "selected_count": int(summary.get("selected_count") or 0),
        "node_count": int(summary.get("node_count") or 0),
        "edge_count": int(summary.get("edge_count") or 0),
        "best_path": _as_list(summary.get("best_path")),
        "best_path_titles": _as_list(summary.get("best_path_titles")),
        "accepted_plan_id": snapshot.get("accepted_plan_id"),
        "accepted_candidate_index": snapshot.get("accepted_candidate_index"),
        "created_at": snapshot.get("created_at") or 0,
        "updated_at": snapshot.get("updated_at") or 0,
    }


def _row_to_snapshot(row: Any) -> dict:
    recommendation = {
        "graph": _json_loads(row.graph_json, {}) or {},
        "candidates": _json_loads(row.candidates_json, []) or [],
        "selected": _json_loads(row.selected_json, []) or [],
        "best_path": _json_loads(row.best_path_json, {}) or {},
        "rag_overlay": _json_loads(row.rag_overlay_json, {}) or {},
        "planning_hints": _json_loads(row.planning_hints_json, {}) or {},
        "debug": {},
    }
    return {
        "recommendation_id": row.recommendation_id,
        "user_id": row.user_id,
        "syllabus_id": row.syllabus_id,
        "session_id": row.session_id or "",
        "status": row.status,
        "schema_version": row.schema_version or RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION,
        "goal": _json_loads(row.goal_json, {}) or {},
        "query_text": row.query_text or "",
        "recommendation": recommendation,
        "summary": _json_loads(row.result_summary_json, {}) or {},
        "accepted_plan_id": row.accepted_plan_id,
        "accepted_candidate_index": row.accepted_candidate_index,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "expires_at": row.expires_at,
    }


def _persist_snapshot_db(snapshot: dict) -> None:
    from extensions import db
    from schemas.agent_runtime_state import RecommendationSnapshot

    row = db.session.get(RecommendationSnapshot, snapshot["recommendation_id"])
    if row is None:
        row = RecommendationSnapshot(recommendation_id=snapshot["recommendation_id"])
        db.session.add(row)
    recommendation = _as_dict(snapshot.get("recommendation"))
    row.user_id = int(snapshot["user_id"])
    row.syllabus_id = snapshot.get("syllabus_id")
    row.session_id = snapshot.get("session_id") or None
    row.status = snapshot.get("status") or RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED
    row.schema_version = snapshot.get("schema_version") or RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION
    row.goal_json = _json_dumps(_as_dict(snapshot.get("goal")))
    row.query_text = snapshot.get("query_text") or ""
    row.graph_json = _json_dumps(_as_dict(recommendation.get("graph")))
    row.candidates_json = _json_dumps(_as_list(recommendation.get("candidates")))
    row.selected_json = _json_dumps(_as_list(recommendation.get("selected")))
    row.best_path_json = _json_dumps(_as_dict(recommendation.get("best_path")))
    row.rag_overlay_json = _json_dumps(_as_dict(recommendation.get("rag_overlay")))
    row.planning_hints_json = _json_dumps(_as_dict(recommendation.get("planning_hints")))
    row.result_summary_json = _json_dumps(_as_dict(snapshot.get("summary")))
    row.accepted_plan_id = snapshot.get("accepted_plan_id")
    row.accepted_candidate_index = snapshot.get("accepted_candidate_index")
    row.created_at = int(snapshot.get("created_at") or row.created_at or _utc_timestamp())
    row.updated_at = int(snapshot.get("updated_at") or _utc_timestamp())
    row.expires_at = snapshot.get("expires_at")
    db.session.commit()


def save_recommendation_snapshot(
    user_id: int,
    syllabus_id: int | None,
    recommendation_result: dict,
    *,
    request_payload: dict | None = None,
    session_id: str | None = None,
    status: str = RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
) -> dict:
    try:
        normalized_user_id = _normalize_positive_int(user_id, "user_id")
        normalized_syllabus_id = _normalize_optional_positive_int(syllabus_id, "syllabus_id")
    except ValueError as exc:
        return {"success": False, "error_code": "invalid_input", "error_message": str(exc)}

    result = _as_dict(recommendation_result)
    graph = _as_dict(result.get("graph"))
    if not isinstance(graph.get("nodes"), list):
        return {"success": False, "error_code": "missing_graph", "error_message": "recommendation graph.nodes is required"}

    normalized_status = str(status or "").strip() or RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED
    if normalized_status not in {
        RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
        RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED,
        RECOMMENDATION_SNAPSHOT_STATUS_EXPIRED,
    }:
        normalized_status = RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED

    now_ts = _utc_timestamp()
    recommendation_id = _new_recommendation_id()
    snapshot = _snapshot_payload(
        recommendation_id=recommendation_id,
        user_id=normalized_user_id,
        syllabus_id=normalized_syllabus_id,
        recommendation_result=result,
        request_payload=request_payload,
        session_id=session_id,
        status=normalized_status,
        created_at=now_ts,
        updated_at=now_ts,
    )

    if not _use_file_backend():
        _require_db_backend()
        _persist_snapshot_db(snapshot)
    else:
        path = _snapshot_path(normalized_user_id, normalized_syllabus_id, recommendation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dumps(snapshot), encoding="utf-8")

    return {
        "success": True,
        "recommendation_id": recommendation_id,
        "status": normalized_status,
        "schema_version": RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION,
        "created_at": now_ts,
        "error_code": "",
        "error_message": "",
    }


def get_recommendation_snapshot(recommendation_id: str) -> dict:
    recommendation_id = str(recommendation_id or "").strip()
    if not recommendation_id:
        return {"success": False, "snapshot": {}, "error_code": RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND, "error_message": "recommendation_id is required"}

    if not _use_file_backend():
        _require_db_backend()
        from schemas.agent_runtime_state import RecommendationSnapshot

        row = RecommendationSnapshot.query.filter_by(recommendation_id=recommendation_id).first()
        snapshot = _row_to_snapshot(row) if row is not None else None
    else:
        snapshot = None
        root = _snapshot_root()
        if root.exists():
            matches = list(root.glob(f"user_*/{recommendation_id}.json")) + list(root.glob(f"user_*/syllabus_*/{recommendation_id}.json"))
            if matches:
                snapshot = _json_loads(matches[0].read_text(encoding="utf-8"), {}) or {}

    if not snapshot:
        return {"success": False, "snapshot": {}, "error_code": RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND, "error_message": "recommendation snapshot not found"}
    return {"success": True, "snapshot": snapshot, "error_code": "", "error_message": ""}


def list_recommendation_snapshots(
    user_id: int,
    syllabus_id: int | None = None,
    limit: int = 20,
) -> dict:
    try:
        normalized_user_id = _normalize_positive_int(user_id, "user_id")
        normalized_syllabus_id = _normalize_optional_positive_int(syllabus_id, "syllabus_id")
    except ValueError as exc:
        return {"success": False, "snapshots": [], "error_code": "invalid_input", "error_message": str(exc)}
    try:
        normalized_limit = max(1, min(100, int(limit)))
    except Exception:
        normalized_limit = 20

    if not _use_file_backend():
        _require_db_backend()
        from schemas.agent_runtime_state import RecommendationSnapshot

        query = RecommendationSnapshot.query.filter_by(user_id=normalized_user_id)
        if normalized_syllabus_id is not None:
            query = query.filter_by(syllabus_id=normalized_syllabus_id)
        rows = query.order_by(RecommendationSnapshot.created_at.desc()).limit(normalized_limit).all()
        snapshots = [_summary_item(_row_to_snapshot(row)) for row in rows]
    else:
        loaded = []
        for path in _iter_snapshot_files(normalized_user_id, normalized_syllabus_id):
            item = _json_loads(path.read_text(encoding="utf-8"), {}) or {}
            if isinstance(item, dict):
                loaded.append(item)
        loaded.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
        snapshots = [_summary_item(item) for item in loaded[:normalized_limit]]

    return {"success": True, "snapshots": snapshots, "error_code": "", "error_message": ""}


def _recommendation_result_from_snapshot(snapshot: dict) -> dict:
    recommendation = _as_dict(snapshot.get("recommendation"))
    return {
        "success": True,
        "graph": _as_dict(recommendation.get("graph")),
        "candidates": _as_list(recommendation.get("candidates")),
        "selected": _as_list(recommendation.get("selected")),
        "best_path": _as_dict(recommendation.get("best_path")),
        "rag_overlay": _as_dict(recommendation.get("rag_overlay")),
        "planning_hints": _as_dict(recommendation.get("planning_hints")),
        "debug": _as_dict(recommendation.get("debug")),
    }


def _update_snapshot_acceptance(
    snapshot: dict,
    *,
    plan_id: str,
    candidate_index: Optional[int],
) -> None:
    now_ts = _utc_timestamp()
    snapshot["status"] = RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED
    snapshot["accepted_plan_id"] = plan_id
    snapshot["accepted_candidate_index"] = candidate_index
    snapshot["updated_at"] = now_ts

    if not _use_file_backend():
        _require_db_backend()
        _persist_snapshot_db(snapshot)
    else:
        path = _snapshot_path(int(snapshot["user_id"]), snapshot.get("syllabus_id"), str(snapshot["recommendation_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dumps(snapshot), encoding="utf-8")


def accept_recommendation_snapshot_path(
    user_id: int,
    syllabus_id: int | None,
    recommendation_id: str,
    candidate_index: int | None = None,
) -> dict:
    try:
        normalized_user_id = _normalize_positive_int(user_id, "user_id")
        normalized_syllabus_id = _normalize_optional_positive_int(syllabus_id, "syllabus_id")
        normalized_candidate_index = int(candidate_index) if candidate_index is not None else None
    except (TypeError, ValueError) as exc:
        return {"success": False, "error_code": "invalid_input", "error_message": str(exc)}

    snapshot_result = get_recommendation_snapshot(recommendation_id)
    if not snapshot_result.get("success"):
        return {
            "success": False,
            "recommendation_id": recommendation_id,
            "error_code": snapshot_result.get("error_code") or RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND,
            "error_message": snapshot_result.get("error_message") or "recommendation snapshot not found",
        }

    snapshot = _as_dict(snapshot_result.get("snapshot"))
    if int(snapshot.get("user_id") or 0) != normalized_user_id:
        return {"success": False, "error_code": "wrong_owner", "error_message": "recommendation snapshot user_id does not match"}
    snapshot_syllabus_id = snapshot.get("syllabus_id")
    if normalized_syllabus_id is not None and snapshot_syllabus_id is not None and int(snapshot_syllabus_id) != normalized_syllabus_id:
        return {"success": False, "error_code": "wrong_syllabus", "error_message": "recommendation snapshot syllabus_id does not match"}

    recommendation_result = _recommendation_result_from_snapshot(snapshot)
    if normalized_candidate_index is not None:
        candidates = _as_list(recommendation_result.get("candidates"))
        if normalized_candidate_index < 0 or normalized_candidate_index >= len(candidates):
            return {
                "success": False,
                "error_code": RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE,
                "error_message": "candidate_index is out of range",
            }

    from tasks.personal_recommendation.learning_plan import accept_recommendation_path

    plan_result = accept_recommendation_path(
        normalized_user_id,
        normalized_syllabus_id if normalized_syllabus_id is not None else snapshot_syllabus_id,
        recommendation_result,
        candidate_index=normalized_candidate_index,
    )
    if not plan_result.get("success"):
        return plan_result

    plan_id = str(plan_result.get("plan_id") or "")
    _update_snapshot_acceptance(snapshot, plan_id=plan_id, candidate_index=normalized_candidate_index)
    return {
        **plan_result,
        "recommendation_id": recommendation_id,
        "snapshot_status": RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED,
        "accepted_candidate_index": normalized_candidate_index,
        "accepted_plan_id": plan_id,
    }


__all__ = [
    "RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE",
    "RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND",
    "RECOMMENDATION_SNAPSHOT_FILE_BACKEND_ENV",
    "RECOMMENDATION_SNAPSHOT_ID_PREFIX",
    "RECOMMENDATION_SNAPSHOT_ROOT_DIR",
    "RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION",
    "RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED",
    "RECOMMENDATION_SNAPSHOT_STATUS_EXPIRED",
    "RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED",
    "RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED",
    "accept_recommendation_snapshot_path",
    "get_recommendation_snapshot",
    "list_recommendation_snapshots",
    "save_recommendation_snapshot",
]
