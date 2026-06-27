from __future__ import annotations

import json
from time import time
from typing import Any

from tasks.common.search_tool import search_tool
from tasks.study_graph.contracts import (
    COURSE_TREE_NODE_MIN_SAMPLE_SIZE,
    COURSE_TREE_SUMMARY_DEFAULT_LIMIT,
    COURSE_TREE_SUMMARY_MIN_GROUP_SIZE,
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


def _load_existing_change_logs(tree_id: str, changes: list[dict]) -> list[dict]:
    existing_logs: list[dict] = []
    seen_client_change_ids: set[str] = set()
    for change in changes or []:
        if not isinstance(change, dict):
            continue
        client_change_id = str(change.get("client_change_id") or "").strip()
        if not client_change_id or client_change_id in seen_client_change_ids:
            continue
        seen_client_change_ids.add(client_change_id)
        existing = get_change_log(tree_id, client_change_id)
        if isinstance(existing, dict):
            existing_logs.append(existing)
    return existing_logs


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
    direct_titles: list[str] = []
    context_titles: list[str] = []
    fallback_titles: list[str] = []

    def append_unique(target: list[str], value: Any) -> None:
        title = str(value or "").strip()
        if title and title not in target:
            target.append(title)

    for item in payload.get("detected_topics") or []:
        if isinstance(item, dict):
            append_unique(direct_titles, item.get("title"))
    for item in payload.get("events") or []:
        if not isinstance(item, dict):
            continue
        append_unique(direct_titles, item.get("topic"))
        append_unique(fallback_titles, item.get("question"))
        append_unique(fallback_titles, item.get("content"))
        meta_points = item.get("meta", {}).get("knowledge_points") if isinstance(item.get("meta"), dict) else []
        if isinstance(meta_points, list):
            for point in meta_points:
                append_unique(direct_titles, point)
    context = payload.get("personal_syllabus_context") if isinstance(payload.get("personal_syllabus_context"), dict) else {}
    for week in context.get("matched_weeks") or []:
        if not isinstance(week, dict):
            continue
        for key in ("title", "content", "enhanced_content"):
            append_unique(context_titles, week.get(key))
    for item in payload.get("rag_context") or []:
        if isinstance(item, dict):
            append_unique(context_titles, item.get("title"))
    append_unique(fallback_titles, payload.get("question"))

    for title in direct_titles + context_titles + ([] if direct_titles else fallback_titles):
        append_unique(candidate_titles, title)
    return candidate_titles


def _has_touch_evidence(payload: dict, normalized_title: str) -> bool:
    if _detect_topic_hit(payload, normalized_title)[0] > 0:
        return True
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
        if detected_topic_hit > 0:
            evidence_score = max(evidence_score, min(1.0, detected_topic_hit))
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


def submit_learning_tree_changes(
    user_id: int,
    syllabus_id: int,
    changes: list[dict],
    source: dict | None = None,
    timestamp: int | None = None,
    subject_title: str | None = None,
) -> dict:
    now_ts = int(timestamp or time())
    validation = validate_change_request(
        {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "changes": changes,
            "source": source or {},
            "timestamp": now_ts,
            "subject_title": subject_title,
        }
    )
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
    existing_change_logs = _load_existing_change_logs(tree["tree_id"], normalized_changes)
    apply_result = apply_learning_tree_changes(
        {
            "user_id": int(user_id),
            "syllabus_id": int(syllabus_id),
            "tree": tree,
            "changes": normalized_changes,
            "source": source or {},
            "existing_change_logs": existing_change_logs,
            "now_ts": now_ts,
        }
    )
    for result in apply_result["results"]:
        if result.get("node"):
            upsert_node(tree["tree_id"], result["node"])
        if result.get("attached_parent_id") and result.get("node"):
            upsert_edge(tree["tree_id"], result["attached_parent_id"], result["node"]["node_id"], "parent_of", now_ts)
        change_log_entry = result.get("change_log_entry")
        if isinstance(change_log_entry, dict) and change_log_entry.get("client_change_id"):
            append_change_log(tree["tree_id"], change_log_entry)
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


def get_student_lifelong_overview(user_id: int) -> dict:
    """Return a merged force-graph of all StudyGraphTrees for a user.

    The merged graph uses the user as the central root node, each subject
    as a child branch, and all knowledge nodes as leaves.  Designed for
    D3GraphViewer with layout='force'.
    """
    from schemas.agent_runtime_state import StudyGraphTree

    trees = StudyGraphTree.query.filter_by(user_id=user_id).order_by(StudyGraphTree.updated_at.desc()).all()

    user_root = {
        "node_id": f"user_root:{user_id}",
        "tree_id": f"student_{user_id}",
        "type": "user_root",
        "title": "学习全景",
        "label": "学习全景",
        "group": "user_root",
        "virtual": False,
        "radius": 18,
        "mastery": {},
    }

    all_nodes: list[dict] = [user_root]
    all_edges: list[dict] = []
    syllabi: list[dict] = []

    for tree in trees:
        raw_nodes = [n for n in list_nodes(tree.tree_id) if isinstance(n, dict)]
        raw_edges = [e for e in list_edges(tree.tree_id) if isinstance(e, dict)]

        subject_id = f"subject:{tree.syllabus_id}"
        all_nodes.append({
            "node_id": subject_id,
            "type": "subject",
            "title": tree.subject_title or f"学科 {tree.syllabus_id}",
            "label": tree.subject_title or f"学科 {tree.syllabus_id}",
            "group": "chapter",
            "radius": 12,
            "mastery": {},
        })
        all_edges.append({
            "source": user_root["node_id"],
            "target": subject_id,
            "edge_type": "enrolled",
        })

        # prefix node ids with syllabus_id to avoid collisions across subjects
        for n in raw_nodes:
            original_id = n.get("node_id", "")
            n["original_node_id"] = original_id
            n["node_id"] = f"{tree.syllabus_id}:{original_id}"
            if n.get("parent_node_id"):
                n["parent_node_id"] = f"{tree.syllabus_id}:{n['parent_node_id']}"
            all_nodes.append(n)

        for e in raw_edges:
            e["source"] = f"{tree.syllabus_id}:{e.get('source', '')}"
            e["target"] = f"{tree.syllabus_id}:{e.get('target', '')}"
            all_edges.append(e)

        syllabi.append({
            "syllabus_id": tree.syllabus_id,
            "subject_title": tree.subject_title,
            "tree_id": tree.tree_id,
            "node_count": len(raw_nodes),
        })

    return {
        "success": True,
        "tree": {
            "tree_id": f"student_{user_id}",
            "type": "student",
            "user_id": user_id,
            "nodes": all_nodes,
            "edges": all_edges,
            "syllabi": syllabi,
        },
    }


def get_student_learning_tree(
    user_id: int,
    syllabus_id: int,
    include_debug: bool = False,
    include_siblings: bool = False,
) -> dict:
    tree = get_tree(user_id, syllabus_id)
    if tree is None:
        tree = create_tree_if_missing(user_id, syllabus_id, title=None, now_ts=int(time()))
    tree = dict(tree)
    tree["virtual_root"] = build_virtual_root(tree)
    if include_debug:
        tree["debug"] = {"change_log_exists": True}
    result: dict = {"success": True, "tree": tree, "debug": tree.get("debug", {}) if include_debug else {}}
    if include_siblings:
        from schemas.agent_runtime_state import StudyGraphTree
        siblings = StudyGraphTree.query.filter(
            StudyGraphTree.user_id == user_id,
            StudyGraphTree.syllabus_id != syllabus_id,
        ).order_by(StudyGraphTree.updated_at.desc()).all()
        result["sibling_trees"] = [
            {
                "syllabus_id": s.syllabus_id,
                "subject_title": s.subject_title,
                "tree_id": s.tree_id,
                "preview_nodes": [
                    {"node_id": n.get("node_id"), "title": n.get("title")}
                    for n in list_nodes(s.tree_id)[:2]
                ],
                "node_count": len(list_nodes(s.tree_id)),
            }
            for s in siblings
        ]
    return result


def get_learning_tree_features(user_id: int, syllabus_id: int, stale_days: int = 14) -> dict:
    tree = get_tree(user_id, syllabus_id)
    if tree is None:
        tree = create_tree_if_missing(user_id, syllabus_id, title=None, now_ts=int(time()))
    payload = get_learning_tree_features_payload(tree, int(time()), stale_days=stale_days)
    return {"success": True, **payload}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_texts(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _safe_text(item)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _coerce_tree_summary_source(item: Any) -> dict:
    if not isinstance(item, dict):
        return {}
    if isinstance(item.get("tree"), dict):
        tree = item["tree"]
        return {
            "user_id": item.get("user_id") or tree.get("user_id"),
            "tree": tree,
            "features": item.get("features") if isinstance(item.get("features"), dict) else {},
        }
    if isinstance(item.get("nodes"), list):
        return {"user_id": item.get("user_id"), "tree": item, "features": {}}
    if any(key in item for key in ("weak_topics", "mastered_topics", "learned_topics", "recently_grown")):
        return {"user_id": item.get("user_id"), "tree": {}, "features": item}
    return {}


def _iter_course_summary_sources(payload: dict) -> list[dict]:
    explicit = payload.get("student_tree_summaries") or payload.get("student_summaries") or payload.get("student_trees")
    if isinstance(explicit, list):
        return [_coerce_tree_summary_source(item) for item in explicit]

    syllabus_id = _safe_int(payload.get("syllabus_id"))
    user_ids = payload.get("user_ids") if isinstance(payload.get("user_ids"), list) else []
    sources: list[dict] = []
    for user_id in user_ids:
        normalized_user_id = _safe_int(user_id)
        if normalized_user_id <= 0 or syllabus_id <= 0:
            continue
        tree = get_tree(normalized_user_id, syllabus_id)
        if isinstance(tree, dict):
            sources.append({"user_id": normalized_user_id, "tree": tree, "features": {}})
    return sources


def _collect_node_signal(source: dict) -> list[dict]:
    tree = source.get("tree") if isinstance(source.get("tree"), dict) else {}
    nodes = tree.get("nodes") if isinstance(tree.get("nodes"), list) else []
    signals: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        title = _safe_text(node.get("title"))
        if not title:
            continue
        mastery = node.get("mastery") if isinstance(node.get("mastery"), dict) else {}
        score = _safe_float(mastery.get("score"), 0.0)
        label = _safe_text(mastery.get("label") or "")
        if not label:
            if score < 0.4:
                label = "weak"
            elif score >= 0.8:
                label = "mastered"
            else:
                label = "learning"
        signals.append(
            {
                "title": title,
                "label": label,
                "score": score,
                "recent": _safe_int(node.get("last_updated_at")) > 0,
                "wrong_points": node.get("common_wrong_points") if isinstance(node.get("common_wrong_points"), list) else [],
            }
        )
    features = source.get("features") if isinstance(source.get("features"), dict) else {}
    for title in features.get("weak_topics") or features.get("weak_node_ids") or []:
        signals.append({"title": _safe_text(title), "label": "weak", "score": 0.0, "recent": False, "wrong_points": []})
    for title in features.get("mastered_topics") or features.get("mastered_node_ids") or []:
        signals.append({"title": _safe_text(title), "label": "mastered", "score": 1.0, "recent": False, "wrong_points": []})
    for title in features.get("recently_grown") or features.get("recent_node_ids") or []:
        signals.append({"title": _safe_text(title), "label": "recent", "score": 0.0, "recent": True, "wrong_points": []})
    return [signal for signal in signals if signal.get("title")]


def get_course_learning_tree_summary(payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    syllabus_id = _safe_int(payload.get("syllabus_id"))
    class_id = _safe_text(payload.get("class_id"))
    limit = _safe_int(payload.get("limit"), COURSE_TREE_SUMMARY_DEFAULT_LIMIT)
    if limit <= 0:
        limit = COURSE_TREE_SUMMARY_DEFAULT_LIMIT
    limit = min(limit, COURSE_TREE_SUMMARY_DEFAULT_LIMIT)
    min_group_size = _safe_int(payload.get("min_group_size"), COURSE_TREE_SUMMARY_MIN_GROUP_SIZE)
    node_min_sample_size = _safe_int(payload.get("node_min_sample_size"), COURSE_TREE_NODE_MIN_SAMPLE_SIZE)

    sources = [source for source in _iter_course_summary_sources(payload) if source]
    student_count = len(sources)
    warnings: list[str] = []
    if student_count < min_group_size:
        warnings.append("course_summary_group_too_small")

    buckets: dict[str, dict] = {}
    for source in sources:
        seen_titles: set[str] = set()
        for signal in _collect_node_signal(source):
            title = _safe_text(signal.get("title"))
            if not title:
                continue
            bucket = buckets.setdefault(
                title,
                {
                    "title": title,
                    "sample_size": 0,
                    "weak_student_count": 0,
                    "mastered_student_count": 0,
                    "recent_student_count": 0,
                    "scores": [],
                    "wrong_points": [],
                },
            )
            if title not in seen_titles:
                bucket["sample_size"] += 1
                seen_titles.add(title)
            label = _safe_text(signal.get("label"))
            score = _safe_float(signal.get("score"))
            bucket["scores"].append(score)
            if label == "weak":
                bucket["weak_student_count"] += 1
            if label == "mastered":
                bucket["mastered_student_count"] += 1
            if label == "recent" or signal.get("recent"):
                bucket["recent_student_count"] += 1
            bucket["wrong_points"].extend(signal.get("wrong_points") or [])

    visible = [
        bucket for bucket in buckets.values()
        if student_count >= min_group_size and bucket["sample_size"] >= node_min_sample_size
    ]
    hidden_count = len(buckets) - len(visible)
    if hidden_count > 0:
        warnings.append("small_sample_nodes_redacted")

    def average(bucket: dict) -> float:
        scores = [float(score) for score in bucket.get("scores") or []]
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    weak_nodes = sorted(
        [
            {
                "title": bucket["title"],
                "weak_student_count": bucket["weak_student_count"],
                "sample_size": bucket["sample_size"],
                "average_mastery": average(bucket),
                "common_wrong_points": _unique_texts(bucket.get("wrong_points") or [])[:5],
            }
            for bucket in visible
            if bucket["weak_student_count"] > 0
        ],
        key=lambda item: (item["weak_student_count"], -item["average_mastery"]),
        reverse=True,
    )[:limit]
    mastered_nodes = sorted(
        [
            {
                "title": bucket["title"],
                "mastered_student_count": bucket["mastered_student_count"],
                "sample_size": bucket["sample_size"],
                "average_mastery": average(bucket),
            }
            for bucket in visible
            if bucket["mastered_student_count"] > 0
        ],
        key=lambda item: (item["mastered_student_count"], item["average_mastery"]),
        reverse=True,
    )[:limit]
    recently_active_nodes = sorted(
        [
            {
                "title": bucket["title"],
                "recent_student_count": bucket["recent_student_count"],
                "sample_size": bucket["sample_size"],
            }
            for bucket in visible
            if bucket["recent_student_count"] > 0
        ],
        key=lambda item: item["recent_student_count"],
        reverse=True,
    )[:limit]
    recommended_intervention = [
        f"建议补充 {node['title']} 的针对性讲解和练习。"
        for node in weak_nodes[:3]
    ]

    return {
        "success": True,
        "summary": {
            "syllabus_id": syllabus_id,
            "class_id": class_id,
            "student_count": student_count,
            "weak_nodes": weak_nodes,
            "mastered_nodes": mastered_nodes,
            "recently_active_nodes": recently_active_nodes,
            "recommended_intervention": recommended_intervention,
        },
        "privacy": {
            "aggregation": True,
            "student_ids_redacted": True,
            "min_group_size": min_group_size,
            "node_min_sample_size": node_min_sample_size,
            "hidden_node_count": max(0, hidden_count),
        },
        "warnings": _unique_texts(warnings),
        "error_code": "",
        "error_message": "",
    }
