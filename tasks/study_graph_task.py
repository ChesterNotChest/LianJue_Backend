from __future__ import annotations

import json
from time import time
from typing import Any

from tasks.search_tool import search_tool
from tasks.study_graph.contracts import (
    STUDY_GRAPH_LOW_CONFIDENCE_THRESHOLD,
    STUDY_GRAPH_MAX_CONTEXT_CANDIDATES,
    build_client_change_id,
    build_tree_id,
    build_virtual_root_node,
)
from tasks.study_graph.features import build_virtual_root, get_learning_tree_features_payload, recompute_tree_summary
from tasks.study_graph.normalizer import evidence_key_from_payload, normalize_knowledge_title, rank_tree_candidates
from tasks.study_graph.storage import (
    append_change_log,
    create_tree_if_missing,
    get_change_log,
    get_tree,
    list_edges,
    list_nodes,
    save_tree_manifest,
    update_summary,
    upsert_edge,
    upsert_node,
)
from tasks.study_graph.tree_builder import (
    apply_learning_tree_changes,
    normalize_change_candidates,
    validate_change_request,
)


def _default_title(payload: dict) -> str | None:
    subject_title = str(payload.get("subject_title") or "").strip()
    learning_goal = str(payload.get("learning_goal") or "").strip()
    if subject_title:
        return subject_title
    if learning_goal:
        return learning_goal
    return None


def _load_tree_snapshot(user_id: int, syllabus_id: int, title: str | None, now_ts: int, subject_title: str | None = None) -> dict:
    tree = create_tree_if_missing(user_id, syllabus_id, title=title, now_ts=now_ts, subject_title=subject_title)
    tree = dict(tree)
    tree["virtual_root"] = build_virtual_root_node(user_id, syllabus_id, subject_title or title, now_ts)
    return tree


def get_student_learning_tree_context(user_id: int, syllabus_id: int, query: str, max_candidates: int = STUDY_GRAPH_MAX_CONTEXT_CANDIDATES) -> dict:
    now_ts = int(time())
    tree = _load_tree_snapshot(user_id, syllabus_id, title=None, now_ts=now_ts)
    nodes = list_nodes(tree["tree_id"])
    ranked_candidates = rank_tree_candidates(nodes, query, max_candidates)
    return {
        "tree_id": tree["tree_id"],
        "query": query,
        "normalized_query": normalize_knowledge_title(query),
        "ranked_candidates": ranked_candidates,
        "personal_syllabus_hints": [],
        "warnings": [],
    }


def _detect_topic_hit(payload: dict, normalized_title: str) -> tuple[float, dict | None]:
    best_confidence = 0.0
    matched_topic = None
    for item in payload.get("detected_topics") or []:
        if not isinstance(item, dict):
            continue
        title = normalize_knowledge_title(item.get("title") or "")
        if title != normalized_title:
            continue
        try:
            confidence = float(item.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0
        if confidence > best_confidence:
            best_confidence = confidence
            matched_topic = item
    return best_confidence, matched_topic


def _question_hit(payload: dict, normalized_title: str) -> float:
    question = normalize_knowledge_title(payload.get("question") or "")
    if not question:
        return 0.0
    return 1.0 if normalized_title in question or question in normalized_title else 0.0


def _event_hit(payload: dict, normalized_title: str) -> float:
    for item in payload.get("events") or []:
        if not isinstance(item, dict):
            continue
        topic = normalize_knowledge_title(item.get("topic") or item.get("question") or item.get("content") or "")
        if topic == normalized_title:
            return 1.0
        meta_points = item.get("meta", {}).get("knowledge_points") if isinstance(item.get("meta"), dict) else []
        if isinstance(meta_points, list):
            for point in meta_points:
                if normalize_knowledge_title(point) == normalized_title:
                    return 1.0
    return 0.0


def _personal_syllabus_hit(payload: dict, normalized_title: str) -> float:
    context = payload.get("personal_syllabus_context") if isinstance(payload.get("personal_syllabus_context"), dict) else {}
    for week in context.get("matched_weeks") or []:
        if not isinstance(week, dict):
            continue
        if normalized_title in normalize_knowledge_title(week.get("title") or ""):
            return 1.0
        if normalized_title in normalize_knowledge_title(week.get("content") or ""):
            return 1.0
    return 0.0


def _collect_candidate_titles(payload: dict) -> list[str]:
    candidate_titles: list[str] = []
    for item in payload.get("detected_topics") or []:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            if title and title not in candidate_titles:
                candidate_titles.append(title)
    for item in payload.get("events") or []:
        if not isinstance(item, dict):
            continue
        for key in ("topic", "question", "content"):
            title = str(item.get(key) or "").strip()
            if title and title not in candidate_titles:
                candidate_titles.append(title)
        meta_points = item.get("meta", {}).get("knowledge_points") if isinstance(item.get("meta"), dict) else []
        if isinstance(meta_points, list):
            for point in meta_points:
                title = str(point or "").strip()
                if title and title not in candidate_titles:
                    candidate_titles.append(title)
    context = payload.get("personal_syllabus_context") if isinstance(payload.get("personal_syllabus_context"), dict) else {}
    for week in context.get("matched_weeks") or []:
        if not isinstance(week, dict):
            continue
        for key in ("title", "content", "enhanced_content"):
            title = str(week.get(key) or "").strip()
            if title and title not in candidate_titles:
                candidate_titles.append(title)
    for item in payload.get("rag_context") or []:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            if title and title not in candidate_titles:
                candidate_titles.append(title)
    question = str(payload.get("question") or "").strip()
    if question and question not in candidate_titles:
        candidate_titles.append(question)
    return candidate_titles


def _has_touch_evidence(payload: dict, normalized_title: str) -> bool:
    if _question_hit(payload, normalized_title) >= 1.0:
        return True
    if _event_hit(payload, normalized_title) >= 1.0:
        return True
    if _personal_syllabus_hit(payload, normalized_title) >= 1.0:
        return True
    return False


def build_study_graph_changes_from_student_payload(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    changes = []
    user_id = payload.get("user_id")
    syllabus_id = payload.get("syllabus_id")
    source_kind = str((payload.get("source") or {}).get("kind") or payload.get("source_kind") or "student").strip() or "student"
    evidence_key = evidence_key_from_payload(payload)
    detected_topics = payload.get("detected_topics") or []
    rag_context = payload.get("rag_context") or []
    parent_candidates = payload.get("parent_candidates") or []
    candidate_titles = _collect_candidate_titles(payload)
    for title in candidate_titles:
        normalized_title = normalize_knowledge_title(title)
        if not normalized_title:
            continue
        question_hit = _question_hit(payload, normalized_title)
        event_hit = _event_hit(payload, normalized_title)
        detected_topic_hit, matched_topic = _detect_topic_hit(payload, normalized_title)
        personal_syllabus_hit = _personal_syllabus_hit(payload, normalized_title)
        rag_only_hit = 1.0 if rag_context and not (question_hit or event_hit or detected_topic_hit or personal_syllabus_hit) else 0.0
        evidence_score = max(
            0.0,
            min(
                1.0,
                0.40 * question_hit
                + 0.35 * event_hit
                + 0.25 * detected_topic_hit
                + 0.10 * personal_syllabus_hit
                + 0.00 * rag_only_hit,
            ),
        )
        if evidence_score < 0.60:
            continue
        if evidence_score < 0.80 and not _has_touch_evidence(payload, normalized_title):
            continue
        client_change_id = build_client_change_id(
            user_id,
            syllabus_id,
            source_kind,
            "upsert_knowledge_node",
            normalized_title,
            evidence_key,
        )
        parent_candidate = None
        for candidate in parent_candidates:
            if not isinstance(candidate, dict):
                continue
            if normalize_knowledge_title(candidate.get("child_title") or "") == normalized_title:
                parent_candidate = candidate
                break
        changes.append(
            {
                "op": "upsert_knowledge_node",
                "client_change_id": client_change_id,
                "knowledge": {
                    "title": title,
                    "summary": f"Student Agent 识别为已触达且{('薄弱' if (matched_topic or {}).get('signal') == 'struggled' else '已学习')}的知识点",
                    "aliases": [title],
                    "node_id": None,
                },
                "parent_candidate": parent_candidate or {},
                "mastery": {
                    "signal": str((matched_topic or {}).get("signal") or "struggled"),
                    "label_hint": "weak" if evidence_score < 0.8 else "normal",
                },
                "confidence": round(evidence_score, 3),
            }
        )
    return changes


def build_study_graph_changes_from_resource_event(event: dict) -> list[dict]:
    if not isinstance(event, dict):
        return []
    topic = str(event.get("topic") or "").strip()
    normalized_title = normalize_knowledge_title(topic)
    if not normalized_title:
        return []
    resource_type = str(event.get("resource_type") or "resource").strip() or "resource"
    client_change_id = build_client_change_id(
        event.get("user_id") or 0,
        event.get("syllabus_id") or 0,
        "resource",
        "upsert_knowledge_node",
        normalized_title,
        json.dumps(event, ensure_ascii=False, sort_keys=True),
    )
    signal = "practiced" if str(event.get("status") or "").lower() in {"completed", "done", "success"} else "learned"
    return [
        {
            "op": "upsert_knowledge_node",
            "client_change_id": client_change_id,
            "knowledge": {"title": topic, "summary": f"{resource_type} 事件触发的学习节点"},
            "mastery": {"signal": signal, "delta": 0.08},
            "confidence": 0.65,
        }
    ]


def submit_learning_tree_changes(user_id: int, syllabus_id: int, changes: list[dict], source: dict | None = None, timestamp: int | None = None) -> dict:
    now_ts = int(timestamp or time())
    validation = validate_change_request({"user_id": user_id, "syllabus_id": syllabus_id, "changes": changes, "source": source or {}, "timestamp": now_ts})
    if not validation["valid"]:
        return {
            "success": False,
            "error_code": "invalid_request",
            "error_message": "; ".join(validation["errors"]),
            "results": [],
            "warnings": [],
        }
    tree = _load_tree_snapshot(user_id, syllabus_id, title=_default_title(validation["payload"]), now_ts=now_ts, subject_title=validation["payload"].get("subject_title"))
    normalized_changes = normalize_change_candidates(changes)
    apply_result = apply_learning_tree_changes(
        {
            "user_id": int(user_id),
            "syllabus_id": int(syllabus_id),
            "tree": tree,
            "changes": normalized_changes,
            "source": source or {},
            "existing_change_logs": [],
            "now_ts": now_ts,
        }
    )
    for result in apply_result["results"]:
        if result.get("node"):
            upsert_node(tree["tree_id"], result["node"])
        if result.get("attached_parent_id") and result.get("node"):
            upsert_edge(tree["tree_id"], result["attached_parent_id"], result["node"]["node_id"], "parent_of", now_ts)
        append_change_log(tree["tree_id"], result.get("change_log_entry") or {})
    saved_tree = get_tree(user_id, syllabus_id) or tree
    summary = recompute_tree_summary(saved_tree, now_ts)
    update_summary(tree["tree_id"], summary, now_ts)
    return {
        "success": True,
        "tree_id": tree["tree_id"],
        "results": apply_result["results"],
        "created_nodes": [result.get("created_node_id") for result in apply_result["results"] if result.get("created_node_id")],
        "updated_nodes": [result.get("updated_node_id") for result in apply_result["results"] if result.get("updated_node_id")],
        "created_edges": [result.get("attached_parent_id") for result in apply_result["results"] if result.get("attached_parent_id")],
        "summary": summary,
        "warnings": apply_result.get("warnings") or [],
    }


def get_student_learning_tree(user_id: int, syllabus_id: int, include_debug: bool = False) -> dict:
    tree = get_tree(user_id, syllabus_id)
    if tree is None:
        tree = create_tree_if_missing(user_id, syllabus_id, title=None, now_ts=int(time()))
    tree = dict(tree)
    tree["virtual_root"] = build_virtual_root(tree)
    if include_debug:
        tree["debug"] = {"change_log_exists": True}
    return {"success": True, "tree": tree, "debug": tree.get("debug", {}) if include_debug else {}}


def get_learning_tree_features(user_id: int, syllabus_id: int, stale_days: int = 14) -> dict:
    tree = get_tree(user_id, syllabus_id)
    if tree is None:
        tree = create_tree_if_missing(user_id, syllabus_id, title=None, now_ts=int(time()))
    payload = get_learning_tree_features_payload(tree, int(time()), stale_days=stale_days)
    return {"success": True, **payload}
