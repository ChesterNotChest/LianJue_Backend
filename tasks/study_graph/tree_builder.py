from __future__ import annotations

import json
from typing import Any

from tasks.study_graph.contracts import (
    STUDY_GRAPH_DELTA_MAX,
    STUDY_GRAPH_DELTA_MIN,
    STUDY_GRAPH_LOW_CONFIDENCE_THRESHOLD,
    STUDY_GRAPH_SIGNAL_DEFAULT_DELTA,
    build_knowledge_node_id,
    score_to_mastery_label,
)
from tasks.study_graph.normalizer import normalize_aliases, normalize_knowledge_title


def validate_change_request(payload: dict) -> dict:
    errors = []
    try:
        int(payload.get("user_id"))
    except Exception:
        errors.append("user_id is required")
    try:
        int(payload.get("syllabus_id"))
    except Exception:
        errors.append("syllabus_id is required")
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        errors.append("changes must be a non-empty list")
    return {"valid": not errors, "payload": dict(payload or {}), "errors": errors}


def normalize_change_candidates(changes: list[dict]) -> list[dict]:
    normalized = []
    for change in changes or []:
        if not isinstance(change, dict):
            continue
        payload = dict(change)
        knowledge = payload.get("knowledge") if isinstance(payload.get("knowledge"), dict) else {}
        parent_candidate = payload.get("parent_candidate") if isinstance(payload.get("parent_candidate"), dict) else {}
        payload["normalized_title"] = normalize_knowledge_title(knowledge.get("title") or "")
        payload["normalized_aliases"] = normalize_aliases(knowledge.get("aliases") or [])
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0
        payload["confidence"] = max(0.0, min(1.0, confidence))
        payload["parent_candidate"] = parent_candidate
        normalized.append(payload)
    return normalized


def compute_mastery_update(current_mastery: dict | None, mastery_change: dict | None, confidence: float) -> dict:
    current_mastery = current_mastery if isinstance(current_mastery, dict) else {}
    mastery_change = mastery_change if isinstance(mastery_change, dict) else {}
    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = 0.0
    confidence_value = max(0.2, min(1.0, confidence_value))
    current_score = current_mastery.get("score")
    try:
        base_score = float(current_score)
    except Exception:
        base_score = 0.2
    signal = str(mastery_change.get("signal") or "").strip().lower()
    input_delta = mastery_change.get("delta")
    try:
        input_delta = float(input_delta)
    except Exception:
        input_delta = STUDY_GRAPH_SIGNAL_DEFAULT_DELTA.get(signal, 0.0)
    input_delta = max(STUDY_GRAPH_DELTA_MIN, min(STUDY_GRAPH_DELTA_MAX, input_delta))
    effective_delta = input_delta * confidence_value
    score_after = max(0.0, min(1.0, base_score + effective_delta))
    label_after = score_to_mastery_label(score_after)
    return {
        "before": {
            "label": current_mastery.get("label") or score_to_mastery_label(base_score),
            "score": base_score,
            "progress": float(current_mastery.get("progress") or base_score),
        },
        "after": {
            "label": label_after,
            "score": score_after,
            "progress": score_after,
        },
        "effective_delta": effective_delta,
        "reason": f"signal={signal or 'unknown'}",
    }


def compute_display_update(mastery_after: dict, node_age_days: float = 0, activity: dict | None = None) -> dict:
    mastery_after = mastery_after if isinstance(mastery_after, dict) else {}
    score = float(mastery_after.get("score") or 0.0)
    label = str(mastery_after.get("label") or score_to_mastery_label(score))
    mapping = {
        "weak": ("seed", "weak"),
        "learning": ("sprout", "growing"),
        "normal": ("branch", "stable"),
        "mastered": ("fruit", "mastered"),
    }
    growth_stage, color_state = mapping.get(label, ("seed", "weak"))
    return {"growth_stage": growth_stage, "height": score, "color_state": color_state}


def resolve_target_node(tree: dict, change: dict) -> dict:
    knowledge = change.get("knowledge") if isinstance(change.get("knowledge"), dict) else {}
    node_id = knowledge.get("node_id")
    nodes = tree.get("nodes") if isinstance(tree.get("nodes"), list) else []
    if node_id:
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == node_id:
                return {
                    "action": "update",
                    "node_id": node_id,
                    "matched_by": "id",
                    "existing_node": node,
                    "reason": "explicit node_id hit",
                }
    normalized_title = change.get("normalized_title") or normalize_knowledge_title(knowledge.get("title") or "")
    if normalized_title:
        matched = [node for node in nodes if isinstance(node, dict) and node.get("normalized_title") == normalized_title]
        if len(matched) == 1:
            return {
                "action": "merge",
                "node_id": matched[0].get("node_id"),
                "matched_by": "normalized_title",
                "existing_node": matched[0],
                "reason": "normalized title hit",
            }
        if len(matched) > 1:
            return {
                "action": "needs_review",
                "node_id": None,
                "matched_by": "ambiguous_alias",
                "existing_node": None,
                "reason": "ambiguous normalized title",
            }
    aliases = change.get("normalized_aliases") or normalize_aliases(knowledge.get("aliases") or [])
    alias_hits = []
    for alias in aliases:
        alias_norm = normalize_knowledge_title(alias)
        if not alias_norm:
            continue
        for node in nodes:
            if isinstance(node, dict) and node.get("normalized_title") == alias_norm:
                alias_hits.append(node)
    if len(alias_hits) == 1:
        return {
            "action": "merge",
            "node_id": alias_hits[0].get("node_id"),
            "matched_by": "alias",
            "existing_node": alias_hits[0],
            "reason": "alias hit",
        }
    if len(alias_hits) > 1:
        return {
            "action": "needs_review",
            "node_id": None,
            "matched_by": "ambiguous_alias",
            "existing_node": None,
            "reason": "ambiguous alias",
        }
    if not normalized_title:
        return {
            "action": "reject",
            "node_id": None,
            "matched_by": "none",
            "existing_node": None,
            "reason": "empty title",
        }
    return {
        "action": "create",
        "node_id": build_knowledge_node_id(tree["user_id"], tree["syllabus_id"], normalized_title),
        "matched_by": "none",
        "existing_node": None,
        "reason": "new node",
    }


def resolve_parent_node(tree: dict, change: dict, target_resolution: dict) -> dict:
    parent_candidate = change.get("parent_candidate") if isinstance(change.get("parent_candidate"), dict) else {}
    nodes = tree.get("nodes") if isinstance(tree.get("nodes"), list) else []
    if target_resolution.get("existing_node") and target_resolution["existing_node"].get("parent_node_id"):
        return {
            "action": "keep_existing",
            "parent_node_id": target_resolution["existing_node"].get("parent_node_id"),
            "reason": "existing parent preserved",
        }
    existing_parent_id = parent_candidate.get("existing_node_id")
    if existing_parent_id:
        for node in nodes:
            if isinstance(node, dict) and node.get("node_id") == existing_parent_id:
                return {"action": "attach", "parent_node_id": existing_parent_id, "reason": "explicit parent node id"}
    parent_title = normalize_knowledge_title(parent_candidate.get("title") or "")
    if parent_title:
        matched = [node for node in nodes if isinstance(node, dict) and node.get("normalized_title") == parent_title]
        if len(matched) == 1:
            return {"action": "attach", "parent_node_id": matched[0].get("node_id"), "reason": "parent title hit"}
        if len(matched) > 1:
            return {"action": "needs_review", "parent_node_id": None, "reason": "ambiguous parent"}
    return {"action": "top_level", "parent_node_id": None, "reason": "top level"}


def build_write_operations(results: list[dict]) -> list[dict]:
    operations = []
    for result in results or []:
        status = result.get("status")
        change_log_entry = result.get("change_log_entry")
        if status in ("rejected", "needs_review", "skipped"):
            if isinstance(change_log_entry, dict) and change_log_entry.get("client_change_id"):
                operations.append({"type": "append_change_log", "entry": change_log_entry})
            continue
        node = result.get("node")
        if isinstance(node, dict):
            operations.append({"type": "upsert_node", "node": node})
        parent_node_id = result.get("attached_parent_id")
        if parent_node_id and isinstance(node, dict):
            operations.append({"type": "upsert_edge", "source": parent_node_id, "target": node.get("node_id"), "edge_type": "parent_of"})
        if isinstance(change_log_entry, dict) and change_log_entry.get("client_change_id"):
            operations.append({"type": "append_change_log", "entry": change_log_entry})
    return operations


def _build_change_log_entry(client_change_id: str, status: str, change: dict, now_ts: int, *, result: dict | None = None, reason: str = "") -> dict:
    return {
        "client_change_id": client_change_id,
        "status": status,
        "request": dict(change or {}),
        "result": dict(result or {}),
        "reason": str(reason or ""),
        "created_at": now_ts,
    }


def apply_learning_tree_changes(input_payload: dict) -> dict:
    tree = input_payload.get("tree") if isinstance(input_payload.get("tree"), dict) else {}
    changes = input_payload.get("changes") if isinstance(input_payload.get("changes"), list) else []
    existing_change_logs = input_payload.get("existing_change_logs") if isinstance(input_payload.get("existing_change_logs"), list) else []
    now_ts = int(input_payload.get("now_ts") or 0)
    results = []
    seen_client_change_ids = {
        str(item.get("client_change_id") or "")
        for item in existing_change_logs
        if isinstance(item, dict) and str(item.get("client_change_id") or "")
    }
    for change in changes:
        if not isinstance(change, dict):
            continue
        client_change_id = str(change.get("client_change_id") or "")
        if client_change_id and client_change_id in seen_client_change_ids:
            results.append({
                "client_change_id": client_change_id,
                "status": "skipped",
                "reason": "duplicate client_change_id",
                "change_log_entry": _build_change_log_entry(client_change_id, "skipped", change, now_ts, reason="duplicate client_change_id"),
            })
            continue
        if client_change_id:
            seen_client_change_ids.add(client_change_id)
        confidence = float(change.get("confidence") or 0.0)
        if confidence < STUDY_GRAPH_LOW_CONFIDENCE_THRESHOLD:
            results.append({
                "client_change_id": client_change_id,
                "status": "needs_review",
                "reason": "low confidence",
                "change_log_entry": _build_change_log_entry(client_change_id, "needs_review", change, now_ts, reason="low confidence"),
            })
            continue
        op = str(change.get("op") or "").strip()
        if op == "upsert_knowledge_node":
            target_resolution = resolve_target_node(tree, change)
            if target_resolution["action"] == "reject":
                results.append({
                    "client_change_id": client_change_id,
                    "status": "rejected",
                    "reason": target_resolution["reason"],
                    "change_log_entry": _build_change_log_entry(client_change_id, "rejected", change, now_ts, reason=target_resolution["reason"]),
                })
                continue
            if target_resolution["action"] == "needs_review":
                results.append({
                    "client_change_id": client_change_id,
                    "status": "needs_review",
                    "reason": target_resolution["reason"],
                    "change_log_entry": _build_change_log_entry(client_change_id, "needs_review", change, now_ts, reason=target_resolution["reason"]),
                })
                continue
            parent_resolution = resolve_parent_node(tree, change, target_resolution)
            existing_node = target_resolution.get("existing_node") if isinstance(target_resolution.get("existing_node"), dict) else {}
            current_mastery = existing_node.get("mastery") if target_resolution["action"] != "create" else {}
            mastery_update = compute_mastery_update(current_mastery, change.get("mastery"), confidence)
            display_update = compute_display_update(mastery_update["after"])
            node = {
                "node_id": target_resolution["node_id"],
                "tree_id": tree.get("tree_id"),
                "type": "knowledge",
                "title": change.get("knowledge", {}).get("title"),
                "normalized_title": change.get("normalized_title"),
                "aliases": change.get("normalized_aliases") or [],
                "summary": change.get("knowledge", {}).get("summary"),
                "parent_node_id": parent_resolution.get("parent_node_id"),
                "mastery": mastery_update["after"],
                "display": display_update,
                "source": input_payload.get("source") or {},
                "last_updated_at": now_ts,
            }
            if target_resolution["action"] == "create":
                node["first_seen_at"] = now_ts
            elif existing_node.get("first_seen_at") not in (None, ""):
                node["first_seen_at"] = existing_node.get("first_seen_at")
            status = "accepted" if target_resolution["action"] == "create" else "merged"
            results.append({
                "client_change_id": client_change_id,
                "status": status,
                "created_node_id": node["node_id"] if target_resolution["action"] == "create" else None,
                "updated_node_id": node["node_id"] if target_resolution["action"] != "create" else None,
                "attached_parent_id": parent_resolution.get("parent_node_id"),
                "node": node,
                "change_log_entry": _build_change_log_entry(client_change_id, status, change, now_ts, result=node, reason=target_resolution["reason"]),
                "reason": target_resolution["reason"],
            })
            continue
        if op == "update_mastery":
            results.append({
                "client_change_id": client_change_id,
                "status": "rejected",
                "reason": "update_mastery not yet implemented",
                "change_log_entry": _build_change_log_entry(client_change_id, "rejected", change, now_ts, reason="update_mastery not yet implemented"),
            })
            continue
        if op == "attach_parent":
            results.append({
                "client_change_id": client_change_id,
                "status": "rejected",
                "reason": "attach_parent not yet implemented",
                "change_log_entry": _build_change_log_entry(client_change_id, "rejected", change, now_ts, reason="attach_parent not yet implemented"),
            })
            continue
        results.append({
            "client_change_id": client_change_id,
            "status": "rejected",
            "reason": f"unsupported op: {op}",
            "change_log_entry": _build_change_log_entry(client_change_id, "rejected", change, now_ts, reason=f"unsupported op: {op}"),
        })
    write_operations = build_write_operations(results)
    return {
        "tree_id": tree.get("tree_id"),
        "results": results,
        "write_operations": write_operations,
        "summary_delta": {},
        "warnings": [],
    }
