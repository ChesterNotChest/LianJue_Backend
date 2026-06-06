"""Append-only learning plan manifest for accepted recommendation paths."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


LEARNING_PLAN_MANIFEST_VERSION = "learning_plan.v1"
LEARNING_PLAN_ROOT_DIR = "personal_recommendation/learning_plan"
LEARNING_PLAN_MANIFEST_FILENAME = "manifest.jsonl"

LEARNING_PLAN_STATUS_ACTIVE = "active"
LEARNING_PLAN_STATUS_COMPLETED = "completed"
LEARNING_PLAN_STATUS_SUPERSEDED = "superseded"
LEARNING_PLAN_STATUS_ABANDONED = "abandoned"

LEARNING_PLAN_STEP_STATUS_PENDING = "pending"
LEARNING_PLAN_STEP_STATUS_ACTIVE = "active"
LEARNING_PLAN_STEP_STATUS_COMPLETED = "completed"
LEARNING_PLAN_STEP_STATUS_SKIPPED = "skipped"

LEARNING_PLAN_SOURCE_RECOMMENDATION = "recommendation"
LEARNING_PLAN_SOURCE_AUTO_AGENT = "auto_agent"

EVENT_PLAN_CREATED = "plan_created"
EVENT_PLAN_SUPERSEDED = "plan_superseded"
EVENT_STEPS_CREATED = "steps_created"
EVENT_STEP_STATUS_CHANGED = "step_status_changed"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _learning_plan_root() -> Path:
    override = os.getenv("PERSONAL_RECOMMENDATION_ROOT")
    if override:
        return Path(override) / "learning_plan"
    return _backend_root() / LEARNING_PLAN_ROOT_DIR


def _normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer") from None
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def _utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _new_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{timestamp}_{uuid4().hex[:6]}"


def _manifest_path(user_id: int, syllabus_id: Optional[int] = None) -> Path:
    user_id = _normalize_positive_int(user_id, "user_id")
    root = _learning_plan_root() / f"user_{user_id}"
    if syllabus_id:
        root = root / f"syllabus_{_normalize_positive_int(syllabus_id, 'syllabus_id')}"
    return root / LEARNING_PLAN_MANIFEST_FILENAME


def _append_jsonl(path_value: Path, payload: dict) -> None:
    path_value.parent.mkdir(parents=True, exist_ok=True)
    with path_value.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def load_learning_plan_manifest(user_id: int, syllabus_id: Optional[int] = None) -> List[dict]:
    path_value = _manifest_path(user_id, syllabus_id)
    if not path_value.exists():
        return []
    entries: List[dict] = []
    for line in path_value.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def append_learning_plan_manifest_entry(user_id: int, entry: dict, syllabus_id: Optional[int] = None) -> dict:
    payload = dict(entry or {})
    payload.setdefault("entry_id", _new_id("lp_entry"))
    payload.setdefault("schema_version", LEARNING_PLAN_MANIFEST_VERSION)
    payload["user_id"] = _normalize_positive_int(payload.get("user_id") or user_id, "user_id")
    if payload.get("syllabus_id") is not None or syllabus_id is not None:
        payload["syllabus_id"] = _normalize_positive_int(payload.get("syllabus_id") or syllabus_id, "syllabus_id")
    payload.setdefault("created_at", _utc_timestamp())
    _append_jsonl(_manifest_path(payload["user_id"], payload.get("syllabus_id")), payload)
    return payload


def _select_path(recommendation_result: dict, candidate_index: Optional[int] = None) -> Optional[dict]:
    result = recommendation_result if isinstance(recommendation_result, dict) else {}
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
    if candidate_index is not None:
        try:
            index = int(candidate_index)
        except Exception:
            return None
        if 0 <= index < len(candidates) and isinstance(candidates[index], dict):
            return dict(candidates[index])
        return None
    best_path = result.get("best_path")
    return dict(best_path) if isinstance(best_path, dict) else None


def _node_lookup(recommendation_result: dict) -> dict:
    graph = recommendation_result.get("graph") if isinstance(recommendation_result, dict) else {}
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    return {
        str(node.get("id")): node
        for node in nodes or []
        if isinstance(node, dict) and node.get("id") is not None
    }


def _build_steps(selected_path: dict, recommendation_result: dict) -> List[dict]:
    nodes_by_id = _node_lookup(recommendation_result)
    path = [str(node_id) for node_id in selected_path.get("path") or []]
    steps = []
    for idx, node_id in enumerate(path):
        node = nodes_by_id.get(node_id, {})
        steps.append(
            {
                "step_id": _new_id("step"),
                "node_id": node_id,
                "title": node.get("title") or node_id,
                "outcomes": list(node.get("outcomes") or []),
                "order_index": idx,
                "status": LEARNING_PLAN_STEP_STATUS_ACTIVE if idx == 0 else LEARNING_PLAN_STEP_STATUS_PENDING,
                "resource_ids": [],
            }
        )
    return steps


def _replay_entries(entries: List[dict]) -> Dict[str, dict]:
    plans: Dict[str, dict] = {}
    for entry in entries:
        event_type = entry.get("event_type")
        plan_id = str(entry.get("plan_id") or "")
        if not plan_id:
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        if event_type == EVENT_PLAN_CREATED:
            plans[plan_id] = {
                "plan_id": plan_id,
                "user_id": entry.get("user_id"),
                "syllabus_id": entry.get("syllabus_id"),
                "status": entry.get("status") or LEARNING_PLAN_STATUS_ACTIVE,
                "source": entry.get("source") or LEARNING_PLAN_SOURCE_RECOMMENDATION,
                "created_at": entry.get("created_at"),
                "current_step_index": 0,
                "path": list(payload.get("path") or []),
                "candidate_index": payload.get("candidate_index"),
                "steps": [],
            }
        elif event_type == EVENT_PLAN_SUPERSEDED and plan_id in plans:
            plans[plan_id]["status"] = LEARNING_PLAN_STATUS_SUPERSEDED
        elif event_type == EVENT_STEPS_CREATED and plan_id in plans:
            steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
            plans[plan_id]["steps"] = [dict(step) for step in steps if isinstance(step, dict)]
        elif event_type == EVENT_STEP_STATUS_CHANGED and plan_id in plans:
            step_id = str(entry.get("step_id") or payload.get("step_id") or "")
            status = str(entry.get("status") or payload.get("status") or "")
            for step in plans[plan_id].get("steps") or []:
                if str(step.get("step_id") or "") == step_id:
                    step["status"] = status
                    break
            for idx, step in enumerate(plans[plan_id].get("steps") or []):
                if step.get("status") == LEARNING_PLAN_STEP_STATUS_ACTIVE:
                    plans[plan_id]["current_step_index"] = idx
                    break
    return plans


def get_active_learning_plan(user_id: int, syllabus_id: Optional[int] = None) -> Optional[dict]:
    entries = load_learning_plan_manifest(user_id, syllabus_id)
    plans = _replay_entries(entries)
    active = [
        plan for plan in plans.values()
        if plan.get("status") == LEARNING_PLAN_STATUS_ACTIVE
    ]
    if not active:
        return None
    active.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
    return active[0]


def accept_recommendation_path(
    user_id: int,
    syllabus_id: Optional[int],
    recommendation_result: dict,
    candidate_index: Optional[int] = None,
    source: str = LEARNING_PLAN_SOURCE_RECOMMENDATION,
) -> dict:
    user_id = _normalize_positive_int(user_id, "user_id")
    normalized_syllabus_id = _normalize_positive_int(syllabus_id, "syllabus_id") if syllabus_id else None
    selected_path = _select_path(recommendation_result, candidate_index)
    if not selected_path or not selected_path.get("path"):
        return {
            "success": False,
            "error_code": "missing_path",
            "error_message": "no recommendation path selected",
        }

    old_plan = get_active_learning_plan(user_id, normalized_syllabus_id)
    superseded_plan_id = old_plan.get("plan_id") if isinstance(old_plan, dict) else None
    if superseded_plan_id:
        append_learning_plan_manifest_entry(
            user_id,
            {
                "event_type": EVENT_PLAN_SUPERSEDED,
                "plan_id": superseded_plan_id,
                "status": LEARNING_PLAN_STATUS_SUPERSEDED,
                "payload": {"reason": "new_plan_accepted"},
            },
            normalized_syllabus_id,
        )

    plan_id = _new_id("plan")
    path = [str(node_id) for node_id in selected_path.get("path") or []]
    append_learning_plan_manifest_entry(
        user_id,
        {
            "event_type": EVENT_PLAN_CREATED,
            "plan_id": plan_id,
            "status": LEARNING_PLAN_STATUS_ACTIVE,
            "source": source,
            "payload": {
                "path": path,
                "candidate_index": candidate_index,
                "skills": list(selected_path.get("skills") or []),
            },
        },
        normalized_syllabus_id,
    )
    steps = _build_steps(selected_path, recommendation_result)
    append_learning_plan_manifest_entry(
        user_id,
        {
            "event_type": EVENT_STEPS_CREATED,
            "plan_id": plan_id,
            "status": LEARNING_PLAN_STATUS_ACTIVE,
            "payload": {"steps": steps},
        },
        normalized_syllabus_id,
    )
    plan = get_active_learning_plan(user_id, normalized_syllabus_id) or {}
    return {
        "success": True,
        "plan_id": plan_id,
        "status": LEARNING_PLAN_STATUS_ACTIVE,
        "superseded_plan_id": superseded_plan_id,
        "steps": plan.get("steps") or steps,
        "plan": plan,
    }


def update_learning_plan_step_status(
    user_id: int,
    plan_id: str,
    step_id: str,
    status: str,
    syllabus_id: Optional[int] = None,
    sync_study_graph: bool = True,
) -> dict:
    normalized_status = str(status or "").strip()
    if normalized_status not in {
        LEARNING_PLAN_STEP_STATUS_PENDING,
        LEARNING_PLAN_STEP_STATUS_ACTIVE,
        LEARNING_PLAN_STEP_STATUS_COMPLETED,
        LEARNING_PLAN_STEP_STATUS_SKIPPED,
    }:
        return {"success": False, "error_code": "invalid_status", "error_message": "invalid step status"}
    append_learning_plan_manifest_entry(
        user_id,
        {
            "event_type": EVENT_STEP_STATUS_CHANGED,
            "plan_id": str(plan_id),
            "step_id": str(step_id),
            "status": normalized_status,
            "payload": {"step_id": str(step_id), "status": normalized_status},
        },
        syllabus_id,
    )
    plan = get_active_learning_plan(user_id, syllabus_id)
    step = None
    for item in (plan or {}).get("steps") or []:
        if str(item.get("step_id") or "") == str(step_id):
            step = item
            break

    sync_result = {"attempted": False, "success": False}
    if sync_study_graph and normalized_status == LEARNING_PLAN_STEP_STATUS_COMPLETED and step:
        sync_result["attempted"] = True
        try:
            from tasks import study_graph_task

            changes = study_graph_task.build_study_graph_changes_from_resource_event(
                {
                    "user_id": user_id,
                    "syllabus_id": syllabus_id,
                    "topic": step.get("title") or step.get("node_id"),
                    "resource_type": "learning_plan_step",
                    "status": "completed",
                }
            )
            if syllabus_id and changes:
                result = study_graph_task.submit_learning_tree_changes(
                    int(user_id),
                    int(syllabus_id),
                    changes,
                    source={"kind": "learning_plan"},
                )
                sync_result["success"] = bool(result.get("success"))
                sync_result["result"] = result
            else:
                sync_result["success"] = True
                sync_result["result"] = {"skipped": True}
        except Exception as exc:
            sync_result["error"] = str(exc)

    return {
        "success": True,
        "plan_id": str(plan_id),
        "step_id": str(step_id),
        "status": normalized_status,
        "study_graph_sync": sync_result,
        "plan": plan,
    }
