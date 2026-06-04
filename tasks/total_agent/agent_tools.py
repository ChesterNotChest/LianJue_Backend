from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from tasks import personal_recommendation_task as prt
from tasks.generative_task import generate_resources_from_request
from tasks.total_agent.agent_contracts import (
    ACTION_ASK_GOAL_CLARIFICATION,
    ACTION_GENERATE_CURRENT_STEP_RESOURCE,
    ACTION_GET_NEXT_LEARNING_TASK,
    ACTION_RECORD_LEARNING_FEEDBACK,
    ACTION_RETRY_RECOMMENDATION,
    ACTION_WAIT_USER_ACCEPTANCE,
    INTENT_ACCEPT_RECOMMENDATION,
    INTENT_ASK_GOAL_CLARIFICATION,
    INTENT_GENERATE_CURRENT_STEP_RESOURCE,
    INTENT_RECORD_LEARNING_FEEDBACK,
    INTENT_RECOMMEND_LEARNING_PATH,
    INTENT_SKIP_CURRENT_STEP,
    PROFILE_READ_ACTION_BUILD_IF_MISSING,
    PROFILE_READ_ACTION_USE_PERSISTED_ONLY,
    PROFILE_SOURCE_BUILT,
    PROFILE_SOURCE_NONE,
    PROFILE_SOURCE_PERSISTED,
    PROFILE_WARNING_BUILD_SKIPPED,
    PROFILE_WARNING_NOT_FOUND,
    PROFILE_WARNING_READ_FAILED,
    RESOURCE_STRATEGY_DEFAULT_TYPE,
    RESOURCE_STRATEGY_DIFFICULTY_REVIEW,
    RESOURCE_STRATEGY_DIFFICULTY_STANDARD,
    RESOURCE_STRATEGY_DIFFICULTY_TARGETED,
    TOOL_ACCEPT_LEARNING_PLAN,
    TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    TOOL_GET_NEXT_LEARNING_TASK,
    TOOL_INFER_USER_INTENT,
    TOOL_LOAD_TOTAL_CONTEXT,
    TOOL_NORMALIZE_LEARNING_GOAL,
    TOOL_RECORD_LEARNING_FEEDBACK,
    TOOL_RUN_LEARNING_RECOMMENDATION,
    TOOL_SKIP_CURRENT_STEP,
    TOTAL_AGENT_CONTEXT_SCHEMA_VERSION,
    TOTAL_AGENT_LEARNING_EVENT_RECORDED,
    TOTAL_AGENT_SCHEMA_VERSION,
    TOTAL_AGENT_TOOL_ORDER,
)


def _utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _list_from_any(value: Any) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any) -> Optional[int]:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _append_trace(state: Dict[str, Any], tool_name: str) -> None:
    trace = state.setdefault("tool_trace", [])
    if isinstance(trace, list):
        trace.append(tool_name)


def _tool_result(tool_name: str, success: bool = True, **payload: Any) -> dict:
    result = {"tool": tool_name, "success": bool(success)}
    result.update(payload)
    result.setdefault("error_code", "" if success else "tool_failed")
    result.setdefault("error_message", "")
    return result


def build_total_agent_result(
    state: Dict[str, Any],
    *,
    success: bool,
    intent: str,
    result: Optional[dict] = None,
    suggested_next_action: str = "",
    error_code: str = "",
    error_message: str = "",
) -> dict:
    return {
        "success": bool(success),
        "schema_version": TOTAL_AGENT_SCHEMA_VERSION,
        "intent": _safe_text(intent),
        "tool_trace": list(state.get("tool_trace") or []),
        "result": result or {},
        "suggested_next_action": _safe_text(suggested_next_action),
        "error_code": _safe_text(error_code),
        "error_message": _safe_text(error_message),
    }


def _plan_steps(plan: Any) -> List[dict]:
    steps = _safe_list(_safe_dict(plan).get("steps"))
    normalized = [dict(step) for step in steps if isinstance(step, dict)]
    normalized.sort(key=lambda item: int(item.get("order_index") or 0))
    return normalized


def _find_step(plan: dict, step_id: Any) -> Optional[dict]:
    step_id = _safe_text(step_id)
    if not step_id:
        return None
    for step in _plan_steps(plan):
        if _safe_text(step.get("step_id")) == step_id:
            return step
    return None


def _find_next_step(plan: Any) -> Optional[dict]:
    steps = _plan_steps(plan)
    for step in steps:
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE:
            return step
    for step in steps:
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_PENDING:
            return step
    return None


def _plan_metrics(plan: Any) -> dict:
    steps = _plan_steps(plan)
    total = len(steps)
    completed = sum(1 for step in steps if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED)
    skipped = sum(1 for step in steps if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED)
    remaining = sum(
        1
        for step in steps
        if step.get("status")
        in {prt.LEARNING_PLAN_STEP_STATUS_ACTIVE, prt.LEARNING_PLAN_STEP_STATUS_PENDING}
    )
    return {
        "total_steps": total,
        "completed_steps": completed,
        "skipped_steps": skipped,
        "remaining_steps": remaining,
        "progress_ratio": round(completed / total, 4) if total else 0.0,
    }


def _confirmation_requested(payload: dict) -> bool:
    if payload.get("auto_accept") is True:
        return True
    message = _safe_text(payload.get("message"))
    markers = ("采纳", "确认", "就按", "按这条", "开始这条", "接受", "accept", "confirm")
    return any(marker in message.lower() for marker in markers)


def _message_has_any(message: str, markers: Iterable[str]) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in markers)


def _unique_texts(items: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _safe_text(item)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _normalize_resource_preferences(items: Iterable[Any]) -> list[str]:
    mapping = {
        "theory": "documents",
        "text": "documents",
        "article": "documents",
        "document": "documents",
        "documents": "documents",
        "practice": "quiz",
        "exercise": "quiz",
        "quiz": "quiz",
        "test": "quiz",
        "visual": "mindmap",
        "mindmap": "mindmap",
        "diagram": "mindmap",
        "video": "documents",
        "code": "coding_practice",
        "coding": "coding_practice",
        "coding_practice": "coding_practice",
        "ppt": "ppt",
        "slides": "ppt",
    }
    normalized: list[str] = []
    for item in items:
        text = _safe_text(item)
        if not text:
            continue
        mapped = mapping.get(text.lower(), text)
        normalized.append(mapped)
    return _unique_texts(normalized)


def _tokenize_goal_text(*values: Any) -> set[str]:
    text = " ".join(_safe_text(value) for value in values if _safe_text(value))
    raw = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower())
    tokens = {item for item in raw if len(item) >= 2}
    for word in ("rowkey", "hbase", "region", "热点", "规避", "预分区"):
        if word.lower() in text.lower():
            tokens.add(word.lower())
    return tokens


def _extract_graph_nodes(recommendation: dict) -> list[dict]:
    graph = _safe_dict(recommendation.get("graph"))
    return [dict(node) for node in _safe_list(graph.get("nodes")) if isinstance(node, dict)]


def _node_score(node: dict, tokens: set[str]) -> int:
    if not tokens:
        return 0
    node_text = " ".join(
        [
            _safe_text(node.get("id")),
            _safe_text(node.get("title")),
            " ".join(_safe_text(item) for item in _safe_list(node.get("outcomes"))),
            " ".join(_safe_text(item) for item in _safe_list(node.get("skills"))),
        ]
    ).lower()
    return sum(1 for token in tokens if token and token.lower() in node_text)


def _refresh_active_plan(state: Dict[str, Any], user_id: int, syllabus_id: Optional[int]) -> dict:
    plan = prt.get_active_learning_plan(user_id, syllabus_id)
    plan = dict(plan) if isinstance(plan, dict) else {}
    state["active_plan"] = plan
    total_context = _safe_dict(state.get("total_context"))
    total_context["active_plan"] = plan
    total_context["next_task"] = _find_next_step(plan) or {}
    state["total_context"] = total_context
    return plan


def _active_plan_matches_context(plan: dict, context: dict) -> bool:
    requested_plan_id = _safe_text(context.get("active_plan_id"))
    if not requested_plan_id:
        return True
    return _safe_text(plan.get("plan_id")) == requested_plan_id


def normalize_profile_summary(profile: dict | None) -> dict:
    source = _safe_dict(profile)
    profile_source = _safe_text(source.get("source") or source.get("profile_source")) or PROFILE_SOURCE_NONE
    if isinstance(source.get("profile_summary"), dict):
        source = source["profile_summary"]
    elif isinstance(source.get("profile"), dict):
        profile_source = _safe_text(source.get("source") or source.get("profile_source")) or profile_source
        source = source["profile"]
    elif isinstance(source.get("result"), dict):
        nested = source["result"]
        if isinstance(nested.get("profile_summary"), dict):
            profile_source = _safe_text(nested.get("source") or nested.get("profile_source")) or profile_source
            source = nested["profile_summary"]
        elif isinstance(nested.get("profile"), dict):
            profile_source = _safe_text(nested.get("source") or nested.get("profile_source")) or profile_source
            source = nested["profile"]

    preferences = _safe_dict(source.get("preferences"))
    time_budget = _safe_dict(source.get("time_budget") or _safe_dict(source.get("constraints")).get("time_budget"))
    preferred_formats = (
        source.get("preferred_formats")
        or preferences.get("preferred_formats")
        or preferences.get("resource_types")
        or source.get("resource_preferences")
        or source.get("preferred_resource_types")
        or source.get("resource_preference")
    )
    weak_points = _list_from_any(
        source.get("weak_points")
        or source.get("weaknesses")
        or source.get("knowledge_weaknesses")
        or source.get("concept_gaps")
        or source.get("bottleneck_topics")
    )
    mastery = _safe_dict(source.get("knowledge_mastery"))
    details = _safe_dict(mastery.get("knowledge_point_details"))
    for title, detail in details.items():
        if not isinstance(detail, dict):
            continue
        level = _safe_text(detail.get("level") or detail.get("mastery") or detail.get("label"))
        try:
            score = float(detail.get("score") or 0.0)
        except Exception:
            score = 0.0
        if level in {"low", "weak"} or score < 0.5:
            weak_points.append(title)
    return {
        "learning_goal": _safe_text(
            source.get("learning_goal")
            or source.get("goal")
            or source.get("target_goal")
        ),
        "weak_points": _unique_texts(weak_points),
        "preferred_formats": _normalize_resource_preferences(_list_from_any(preferred_formats)),
        "risk_level": _safe_text(source.get("risk_level") or source.get("risk") or source.get("dropout_risk")),
        "time_budget": time_budget,
        "updated_at": source.get("updated_at") or source.get("saved_at"),
        "profile_source": _safe_text(source.get("profile_source") or profile_source) or PROFILE_SOURCE_NONE,
    }


def normalize_study_graph_state(features: dict | None) -> dict:
    source = _safe_dict(features)
    if isinstance(source.get("features"), dict):
        source = source["features"]
    elif isinstance(source.get("result"), dict):
        nested = source["result"]
        if isinstance(nested.get("features"), dict):
            source = nested["features"]
        elif isinstance(nested.get("study_graph_state"), dict):
            source = nested["study_graph_state"]

    return {
        "current_node_id": _safe_text(source.get("current_node_id") or source.get("current_node")),
        "completed_node_ids": _unique_texts(
            _list_from_any(source.get("completed_node_ids") or source.get("completed_nodes") or source.get("learned_topics"))
        ),
        "weak_node_ids": _unique_texts(
            _list_from_any(source.get("weak_node_ids") or source.get("weak_nodes") or source.get("weak_topics"))
        ),
        "mastered_node_ids": _unique_texts(
            _list_from_any(source.get("mastered_node_ids") or source.get("mastered_nodes") or source.get("mastered_topics"))
        ),
        "recent_node_ids": _unique_texts(
            _list_from_any(source.get("recent_node_ids") or source.get("recent_nodes") or source.get("recently_grown"))
        ),
        "stale_node_ids": _unique_texts(
            _list_from_any(source.get("stale_node_ids") or source.get("stale_nodes") or source.get("stale_topics"))
        ),
        "blocked_node_ids": _unique_texts(
            _list_from_any(source.get("blocked_node_ids") or source.get("blocked_nodes"))
        ),
        "warnings": _unique_texts(_list_from_any(source.get("warnings"))),
    }


def load_profile_summary(payload: dict) -> dict:
    user_id = _positive_int(_safe_dict(payload).get("user_id"))
    syllabus_id = _positive_int(_safe_dict(payload).get("syllabus_id"))
    if not user_id:
        return {
            "success": False,
            "source": PROFILE_SOURCE_NONE,
            "profile": {},
            "warnings": [PROFILE_WARNING_NOT_FOUND],
            "error_code": "missing_user_id",
            "error_message": "user_id must be a positive integer",
        }
    if not syllabus_id:
        return {
            "success": False,
            "source": PROFILE_SOURCE_NONE,
            "profile": {},
            "warnings": [PROFILE_WARNING_NOT_FOUND],
            "error_code": PROFILE_WARNING_NOT_FOUND,
            "error_message": "syllabus_id is required to read a persisted learning profile",
        }

    action = _safe_text(_safe_dict(payload).get("profile_read_action")) or PROFILE_READ_ACTION_USE_PERSISTED_ONLY
    warnings: list[str] = []
    try:
        from tasks import learning_profile_task

        profile = learning_profile_task.get_persisted_learning_profile(user_id, syllabus_id)
        if isinstance(profile, dict) and profile:
            return {
                "success": True,
                "source": PROFILE_SOURCE_PERSISTED,
                "profile": profile,
                "warnings": [],
                "error_code": "",
                "error_message": "",
            }

        warnings.append(PROFILE_WARNING_NOT_FOUND)
        if action == PROFILE_READ_ACTION_BUILD_IF_MISSING:
            built = learning_profile_task.get_or_build_learning_profile(
                user_id,
                syllabus_id,
                refresh_profile=False,
                dialogue_text=_safe_dict(payload).get("message") or _safe_dict(payload).get("question"),
                learning_goal=_safe_dict(payload).get("learning_goal"),
            )
            if isinstance(built, dict) and built:
                return {
                    "success": True,
                    "source": PROFILE_SOURCE_BUILT,
                    "profile": built,
                    "warnings": warnings,
                    "error_code": "",
                    "error_message": "",
                }
        else:
            warnings.append(PROFILE_WARNING_BUILD_SKIPPED)

        return {
            "success": False,
            "source": PROFILE_SOURCE_NONE,
            "profile": {},
            "warnings": warnings,
            "error_code": PROFILE_WARNING_NOT_FOUND,
            "error_message": "no persisted learning profile",
        }
    except Exception as exc:
        return {
            "success": False,
            "source": PROFILE_SOURCE_NONE,
            "profile": {},
            "warnings": [f"{PROFILE_WARNING_READ_FAILED}:{exc}"],
            "error_code": PROFILE_WARNING_READ_FAILED,
            "error_message": _safe_text(exc),
        }


def get_study_graph_features(user_id: int, syllabus_id: int) -> dict:
    from tasks import study_graph_task

    features = study_graph_task.get_learning_tree_features(user_id, syllabus_id)
    return features if isinstance(features, dict) else {}


def build_current_step_resource_strategy(state: dict) -> dict:
    payload = _safe_dict(state.get("payload"))
    total_context = _safe_dict(state.get("total_context"))
    next_task = _safe_dict(state.get("next_task") or total_context.get("next_task"))
    profile = normalize_profile_summary(total_context.get("profile_summary"))
    study_graph_state = normalize_study_graph_state(total_context.get("study_graph_state"))
    explicit_resource_types = _unique_texts(_list_from_any(payload.get("resource_types")))

    message = _safe_text(payload.get("message") or payload.get("question"))
    outcomes = _list_from_any(next_task.get("outcomes"))
    weak_points = _list_from_any(profile.get("weak_points"))
    preferred_formats = _list_from_any(profile.get("preferred_formats"))
    weak_node_ids = set(_unique_texts(_list_from_any(study_graph_state.get("weak_node_ids"))))
    next_node_id = _safe_text(next_task.get("node_id") or next_task.get("id"))
    next_title = _safe_text(next_task.get("title"))
    next_outcomes = set(_unique_texts(outcomes))

    message_requests_practice = _message_has_any(message, ("练习", "practice", "exercise", "quiz", "题"))
    message_requests_coding = _message_has_any(message, ("代码", "coding", "code", "编程"))
    message_requests_review = _message_has_any(message, ("复习", "总结", "梳理", "review", "summary"))
    matched_study_graph_weak_node = bool(
        (next_node_id and next_node_id in weak_node_ids)
        or (next_title and next_title in weak_node_ids)
        or bool(next_outcomes & weak_node_ids)
    )
    matched_profile_weak_point = bool(_unique_texts(weak_points))

    if explicit_resource_types:
        resource_types = explicit_resource_types
        reason = "user explicitly requested resource types"
    elif message_requests_coding:
        resource_types = ["coding_practice"]
        reason = "message requests coding practice"
    elif message_requests_review:
        resource_types = ["mindmap"]
        reason = "message requests review or summary"
    elif matched_profile_weak_point or matched_study_graph_weak_node:
        resource_types = _unique_texts([RESOURCE_STRATEGY_DEFAULT_TYPE, "quiz", *preferred_formats])
        reason = "current step is weak and profile/study graph indicates targeted practice"
    else:
        resource_types = [RESOURCE_STRATEGY_DEFAULT_TYPE]
        reason = "default lightweight current-step resource"

    difficulty = RESOURCE_STRATEGY_DIFFICULTY_STANDARD
    if matched_profile_weak_point or matched_study_graph_weak_node:
        difficulty = RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    if message_requests_review:
        difficulty = RESOURCE_STRATEGY_DIFFICULTY_REVIEW

    return {
        "success": True,
        "schema_version": TOTAL_AGENT_CONTEXT_SCHEMA_VERSION,
        "resource_types": resource_types,
        "difficulty": difficulty,
        "knowledge_items": _unique_texts([*outcomes, *weak_points]),
        "reason": reason,
        "profile_source": profile.get("profile_source") or PROFILE_SOURCE_NONE,
        "strategy_signals": {
            "explicit_resource_types": bool(explicit_resource_types),
            "matched_profile_weak_point": matched_profile_weak_point,
            "matched_study_graph_weak_node": matched_study_graph_weak_node,
            "message_requests_practice": message_requests_practice,
            "message_requests_review": message_requests_review,
        },
        "error_code": "",
        "error_message": "",
    }


def tool_load_total_context(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_LOAD_TOTAL_CONTEXT)
    payload = _safe_dict(state.get("payload"))
    context = _safe_dict(payload.get("context"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    if not user_id:
        result = _tool_result(
            TOOL_LOAD_TOTAL_CONTEXT,
            False,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )
        state["total_context"] = {}
        return result

    warnings: list[str] = []
    active_plan = {}
    try:
        loaded_plan = prt.get_active_learning_plan(user_id, syllabus_id)
        if isinstance(loaded_plan, dict):
            active_plan = dict(loaded_plan)
            if not _active_plan_matches_context(active_plan, context):
                warnings.append("context_active_plan_id_does_not_match_current_active_plan")
                active_plan = {}
    except Exception as exc:
        warnings.append(f"active_plan_read_failed:{exc}")

    next_task = _find_next_step(active_plan) or {}
    try:
        profile_read = load_profile_summary(payload)
        profile_summary = normalize_profile_summary(profile_read)
        for warning in _list_from_any(_safe_dict(profile_read).get("warnings")):
            text = _safe_text(warning)
            if text:
                warnings.append(text)
    except Exception as exc:
        warnings.append(f"{PROFILE_WARNING_READ_FAILED}:{exc}")
        profile_summary = normalize_profile_summary({})

    study_graph_state = normalize_study_graph_state({})
    if user_id and syllabus_id:
        try:
            study_graph_state = normalize_study_graph_state(get_study_graph_features(user_id, syllabus_id))
        except Exception as exc:
            warnings.append(f"study_graph_read_failed:{exc}")
            study_graph_state = normalize_study_graph_state({})
            study_graph_state["warnings"].append(f"study_graph_read_failed:{exc}")

    total_context = {
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "active_plan": active_plan,
        "next_task": next_task,
        "profile_summary": profile_summary,
        "current_resource_id": _safe_text(context.get("current_resource_id") or payload.get("resource_id")),
        "recent_resource_ids": list(_safe_list(context.get("recent_resource_ids"))),
        "study_graph_state": study_graph_state,
        "warnings": warnings,
    }
    state["total_context"] = total_context
    state["active_plan"] = active_plan
    state["next_task"] = next_task
    return _tool_result(
        TOOL_LOAD_TOTAL_CONTEXT,
        True,
        user_id=user_id,
        syllabus_id=syllabus_id,
        active_plan=active_plan,
        next_task=next_task,
        profile_summary=profile_summary,
        current_resource_id=total_context["current_resource_id"],
        study_graph_state=study_graph_state,
        warnings=warnings,
    )


def tool_infer_user_intent(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_INFER_USER_INTENT)
    payload = _safe_dict(state.get("payload"))
    context = _safe_dict(state.get("total_context"))
    message = _safe_text(payload.get("message") or payload.get("question"))
    explicit_intent = _safe_text(payload.get("intent"))
    active_plan = _safe_dict(context.get("active_plan"))
    current_resource_id = _safe_text(context.get("current_resource_id"))

    if explicit_intent:
        intent = explicit_intent
        confidence = 0.98
        reason = "payload provided explicit intent"
    elif _confirmation_requested(payload):
        intent = INTENT_ACCEPT_RECOMMENDATION
        confidence = 0.9
        reason = "message confirms a recommendation path"
    elif _message_has_any(message, ("完成", "做完", "看完", "学完", "得分", "通过", "done", "completed", "finished", "score")):
        intent = INTENT_RECORD_LEARNING_FEEDBACK
        confidence = 0.86
        reason = "message reports current learning feedback"
    elif _message_has_any(message, ("跳过", "太简单", "换一个", "skip")):
        intent = INTENT_SKIP_CURRENT_STEP
        confidence = 0.84
        reason = "message asks to skip or replace current step"
    elif _message_has_any(message, ("推荐", "路径", "学什么", "怎么学", "规划", "recommend", "path", "route")):
        intent = INTENT_RECOMMEND_LEARNING_PATH
        confidence = 0.82
        reason = "message asks for learning path recommendation"
    elif _message_has_any(message, ("继续", "下一步", "开始学习", "给我资料", "生成资源", "resource", "continue", "next")):
        intent = INTENT_GENERATE_CURRENT_STEP_RESOURCE
        confidence = 0.82
        reason = "message asks to continue current plan"
    elif active_plan:
        intent = INTENT_GENERATE_CURRENT_STEP_RESOURCE
        confidence = 0.72
        reason = "active plan exists and message is ambiguous"
    else:
        intent = INTENT_ASK_GOAL_CLARIFICATION
        confidence = 0.58
        reason = "no active plan or clear learning goal"

    required_context = []
    if intent in {
        INTENT_GENERATE_CURRENT_STEP_RESOURCE,
        INTENT_RECORD_LEARNING_FEEDBACK,
        INTENT_SKIP_CURRENT_STEP,
    }:
        required_context.append("active_plan")
    if intent == INTENT_RECORD_LEARNING_FEEDBACK:
        required_context.append("current_resource_id")

    result = _tool_result(
        TOOL_INFER_USER_INTENT,
        True,
        intent=intent,
        confidence=confidence,
        reason=reason,
        required_context=required_context,
        has_active_plan=bool(active_plan),
        current_resource_id=current_resource_id,
    )
    state["intent"] = intent
    state["intent_result"] = result
    return result


def tool_run_learning_recommendation(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_RUN_LEARNING_RECOMMENDATION)
    payload = deepcopy(_safe_dict(state.get("payload")))
    user_id = _positive_int(payload.get("user_id"))
    if not user_id:
        return _tool_result(
            TOOL_RUN_LEARNING_RECOMMENDATION,
            False,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )

    injected = _safe_dict(payload.get("recommendation_result"))
    if injected:
        recommendation = injected
    else:
        goals = payload.get("goals")
        if not isinstance(goals, list) or not goals:
            goal_text = _safe_text(payload.get("learning_goal") or payload.get("message") or payload.get("question"))
            payload["goals"] = [goal_text] if goal_text else []
        recommendation = prt.run_recommendation_route_from_payload(payload)

    state["recommendation_result"] = recommendation
    has_best_path = bool(_safe_dict(recommendation).get("best_path"))
    suggested = ACTION_WAIT_USER_ACCEPTANCE if has_best_path else ACTION_ASK_GOAL_CLARIFICATION
    return _tool_result(
        TOOL_RUN_LEARNING_RECOMMENDATION,
        bool(_safe_dict(recommendation).get("success", True)),
        recommendation=recommendation,
        has_best_path=has_best_path,
        suggested_next_action=suggested,
        error_code=_safe_text(_safe_dict(recommendation).get("error_code")),
        error_message=_safe_text(_safe_dict(recommendation).get("error_message")),
    )


def tool_normalize_learning_goal_for_recommendation(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_NORMALIZE_LEARNING_GOAL)
    payload = _safe_dict(state.get("payload"))
    recommendation = _safe_dict(state.get("recommendation_result") or payload.get("recommendation_result"))
    message = _safe_text(payload.get("message") or payload.get("question") or payload.get("learning_goal"))
    goals = _safe_list(payload.get("goals"))
    tokens = _tokenize_goal_text(message, *goals)

    scored = []
    for node in _extract_graph_nodes(recommendation):
        score = _node_score(node, tokens)
        if score > 0:
            scored.append((score, node))
    scored.sort(key=lambda item: item[0], reverse=True)

    if scored:
        selected = [node for _, node in scored[:3]]
        normalized_goals = []
        for node in selected:
            normalized_goals.extend(_safe_list(node.get("outcomes")) or [_safe_text(node.get("id") or node.get("title"))])
        result = _tool_result(
            TOOL_NORMALIZE_LEARNING_GOAL,
            True,
            normalized_goals=[item for item in normalized_goals if item],
            selected_nodes=[_safe_text(node.get("id") or node.get("title")) for node in selected],
            confidence=min(0.95, 0.55 + 0.12 * scored[0][0]),
            suggested_next_action=ACTION_RETRY_RECOMMENDATION,
            reason="goal tokens overlap with recommendation graph nodes",
        )
    else:
        result = _tool_result(
            TOOL_NORMALIZE_LEARNING_GOAL,
            True,
            normalized_goals=[],
            selected_nodes=[],
            confidence=0.0,
            suggested_next_action=ACTION_ASK_GOAL_CLARIFICATION,
            reason="no semantic alignment found in recommendation graph",
        )
    state["goal_normalization"] = result
    return result


def tool_accept_learning_plan(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_ACCEPT_LEARNING_PLAN)
    payload = _safe_dict(state.get("payload"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    if not user_id:
        return _tool_result(
            TOOL_ACCEPT_LEARNING_PLAN,
            False,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )
    if not _confirmation_requested(payload):
        return _tool_result(
            TOOL_ACCEPT_LEARNING_PLAN,
            True,
            accepted=False,
            plan={},
            next_task={},
            suggested_next_action=ACTION_WAIT_USER_ACCEPTANCE,
            reason="user confirmation or auto_accept=true is required",
        )

    recommendation = _safe_dict(state.get("recommendation_result") or payload.get("recommendation_result"))
    if not recommendation:
        return _tool_result(
            TOOL_ACCEPT_LEARNING_PLAN,
            False,
            error_code="missing_recommendation_result",
            error_message="recommendation_result is required to accept a learning plan",
        )
    candidate_index = payload.get("candidate_index")
    accept_result = prt.accept_recommendation_path(
        user_id=user_id,
        syllabus_id=syllabus_id,
        recommendation_result=recommendation,
        candidate_index=candidate_index,
    )
    if not accept_result.get("success"):
        return _tool_result(
            TOOL_ACCEPT_LEARNING_PLAN,
            False,
            accept_result=accept_result,
            error_code=_safe_text(accept_result.get("error_code") or "accept_learning_plan_failed"),
            error_message=_safe_text(accept_result.get("error_message")),
        )
    plan = _safe_dict(accept_result.get("plan") or prt.get_active_learning_plan(user_id, syllabus_id))
    next_task = _find_next_step(plan) or {}
    state["active_plan"] = plan
    state["next_task"] = next_task
    return _tool_result(
        TOOL_ACCEPT_LEARNING_PLAN,
        True,
        accepted=True,
        auto_accept=bool(payload.get("auto_accept") is True),
        accept_result=accept_result,
        plan=plan,
        next_task=next_task,
        metrics=_plan_metrics(plan),
        suggested_next_action=ACTION_GENERATE_CURRENT_STEP_RESOURCE,
    )


def tool_get_next_learning_task(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_GET_NEXT_LEARNING_TASK)
    payload = _safe_dict(state.get("payload"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    plan = _safe_dict(state.get("active_plan"))
    if not plan and user_id:
        plan = _safe_dict(prt.get_active_learning_plan(user_id, syllabus_id))
    if not plan:
        state["next_task"] = {}
        return _tool_result(
            TOOL_GET_NEXT_LEARNING_TASK,
            False,
            plan={},
            next_task={},
            metrics={},
            error_code="no_active_plan",
            error_message="no active learning plan",
        )
    next_task = _find_next_step(plan) or {}
    state["active_plan"] = plan
    state["next_task"] = next_task
    return _tool_result(
        TOOL_GET_NEXT_LEARNING_TASK,
        bool(next_task),
        plan={"plan_id": plan.get("plan_id"), "status": plan.get("status")},
        next_task=next_task,
        metrics=_plan_metrics(plan),
        error_code="" if next_task else "no_next_task",
        error_message="" if next_task else "no active or pending step",
    )


def _build_resource_request(state: Dict[str, Any], next_task: dict, resource_strategy: Optional[dict] = None) -> dict:
    payload = _safe_dict(state.get("payload"))
    title = _safe_text(next_task.get("title") or next_task.get("node_id") or "current learning step")
    outcomes = _safe_list(next_task.get("outcomes"))
    strategy = _safe_dict(resource_strategy) or build_current_step_resource_strategy(state)
    resource_types = _safe_list(strategy.get("resource_types")) or [RESOURCE_STRATEGY_DEFAULT_TYPE]
    knowledge_items = _safe_list(strategy.get("knowledge_items")) or outcomes or [title]
    return {
        "user_id": payload.get("user_id"),
        "syllabus_id": payload.get("syllabus_id"),
        "message": payload.get("message") or payload.get("question") or "",
        "question": payload.get("question") or payload.get("message") or f"请生成 {title} 的学习资源",
        "topic": title,
        "target": title,
        "current_step": next_task,
        "knowledge_items": knowledge_items,
        "resource_types": resource_types,
        "difficulty": strategy.get("difficulty") or RESOURCE_STRATEGY_DIFFICULTY_STANDARD,
        "strategy_reason": strategy.get("reason") or "",
        "strategy_signals": _safe_dict(strategy.get("strategy_signals")),
        "resource_strategy": strategy,
        "graph_name": payload.get("graph_name") or payload.get("rag_graph_name"),
        "rag_top_k": payload.get("rag_top_k"),
    }


def _normalize_resources(generation_result: dict) -> list[dict]:
    if isinstance(generation_result.get("resources"), list):
        return generation_result["resources"]
    if isinstance(generation_result.get("resource"), dict):
        return [generation_result["resource"]]
    if isinstance(generation_result.get("result"), dict):
        nested = generation_result["result"]
        if isinstance(nested.get("resources"), list):
            return nested["resources"]
    return []


def tool_generate_current_step_resource(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_GENERATE_CURRENT_STEP_RESOURCE)
    next_task = _safe_dict(state.get("next_task"))
    if not next_task:
        next_result = tool_get_next_learning_task(state)
        next_task = _safe_dict(next_result.get("next_task"))
    if not next_task:
        return _tool_result(
            TOOL_GENERATE_CURRENT_STEP_RESOURCE,
            False,
            next_task={},
            resources=[],
            error_code="no_next_task",
            error_message="no current learning task to generate resources for",
        )

    state["next_task"] = next_task
    resource_strategy = build_current_step_resource_strategy(state)
    state["resource_strategy"] = resource_strategy
    request_payload = _build_resource_request(state, next_task, resource_strategy)
    generation_result = generate_resources_from_request(request_payload)
    resources = _normalize_resources(_safe_dict(generation_result))
    state["resource_generation_request"] = request_payload
    state["resource_generation_result"] = generation_result
    return _tool_result(
        TOOL_GENERATE_CURRENT_STEP_RESOURCE,
        bool(_safe_dict(generation_result).get("success", True)),
        next_task=next_task,
        resource_strategy=resource_strategy,
        request=request_payload,
        generation_result=generation_result,
        resources=resources,
        suggested_next_action=ACTION_RECORD_LEARNING_FEEDBACK,
        error_code=_safe_text(_safe_dict(generation_result).get("error_code")),
        error_message=_safe_text(_safe_dict(generation_result).get("error_message")),
    )


def _append_learning_event(payload: dict, plan: dict, step: dict, status: str) -> dict:
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    event_entry = {
        "event_type": TOTAL_AGENT_LEARNING_EVENT_RECORDED,
        "plan_id": plan.get("plan_id"),
        "step_id": step.get("step_id"),
        "status": status,
        "payload": {
            "event_type": payload.get("event_type") or "resource_completed",
            "resource_type": payload.get("resource_type") or "",
            "resource_id": payload.get("resource_id") or _safe_dict(payload.get("context")).get("current_resource_id") or "",
            "score": payload.get("score"),
            "status": status,
            "recorded_at": _utc_timestamp(),
        },
    }
    return prt.append_learning_plan_manifest_entry(user_id, event_entry, syllabus_id)


def _activate_next_pending(user_id: int, syllabus_id: Optional[int], plan_id: str, plan: dict) -> tuple[dict, dict]:
    pending = None
    for step in _plan_steps(plan):
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_PENDING:
            pending = step
            break
    if not pending:
        return {}, plan
    activation = prt.update_learning_plan_step_status(
        user_id,
        plan_id,
        pending.get("step_id"),
        prt.LEARNING_PLAN_STEP_STATUS_ACTIVE,
        syllabus_id=syllabus_id,
        sync_study_graph=False,
    )
    updated_plan = _safe_dict(activation.get("plan") or prt.get_active_learning_plan(user_id, syllabus_id))
    return _safe_dict(_find_step(updated_plan, pending.get("step_id")) or pending), updated_plan


def _record_step_status(state: Dict[str, Any], status: str, tool_name: str) -> dict:
    _append_trace(state, tool_name)
    payload = _safe_dict(state.get("payload"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    if not user_id:
        return _tool_result(
            tool_name,
            False,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )
    plan = _safe_dict(state.get("active_plan") or prt.get_active_learning_plan(user_id, syllabus_id))
    if not plan:
        return _tool_result(
            tool_name,
            False,
            error_code="no_active_plan",
            error_message="no active learning plan",
        )
    step_id = _safe_text(payload.get("step_id")) or _safe_text(_safe_dict(state.get("next_task")).get("step_id"))
    step = _find_step(plan, step_id) if step_id else _find_next_step(plan)
    if not step:
        return _tool_result(
            tool_name,
            False,
            error_code="no_target_step",
            error_message="no step to update",
        )

    event_entry = _append_learning_event(payload, plan, step, status)
    update = prt.update_learning_plan_step_status(
        user_id,
        plan.get("plan_id"),
        step.get("step_id"),
        status,
        syllabus_id=syllabus_id,
        sync_study_graph=(status == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED),
    )
    updated_plan = _safe_dict(update.get("plan") or prt.get_active_learning_plan(user_id, syllabus_id))
    updated_step = _safe_dict(_find_step(updated_plan, step.get("step_id")) or step)
    activated_step, final_plan = _activate_next_pending(user_id, syllabus_id, plan.get("plan_id"), updated_plan)
    next_task = _find_next_step(final_plan) or {}
    state["active_plan"] = final_plan
    state["next_task"] = next_task
    study_graph_sync = _safe_dict(update.get("study_graph_sync"))
    if status == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED:
        study_graph_sync = {"attempted": False, "success": True, "warning": "skipped step is not synced"}
    return _tool_result(
        tool_name,
        True,
        event_entry=event_entry,
        updated_step=updated_step,
        activated_step=activated_step,
        study_graph_sync=study_graph_sync,
        next_task=next_task,
        metrics=_plan_metrics(final_plan),
        suggested_next_action=ACTION_GENERATE_CURRENT_STEP_RESOURCE if next_task else ACTION_GET_NEXT_LEARNING_TASK,
    )


def tool_record_learning_feedback(state: Dict[str, Any]) -> dict:
    return _record_step_status(
        state,
        _safe_text(_safe_dict(state.get("payload")).get("status")) or prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
        TOOL_RECORD_LEARNING_FEEDBACK,
    )


def tool_skip_current_step(state: Dict[str, Any]) -> dict:
    payload = _safe_dict(state.get("payload"))
    payload.setdefault("status", prt.LEARNING_PLAN_STEP_STATUS_SKIPPED)
    payload.setdefault("event_type", "step_skipped")
    state["payload"] = payload
    return _record_step_status(state, prt.LEARNING_PLAN_STEP_STATUS_SKIPPED, TOOL_SKIP_CURRENT_STEP)


def deterministic_run_total_agent(payload: Dict[str, Any]) -> dict:
    state: Dict[str, Any] = {"payload": payload or {}, "tool_trace": []}
    context_result = tool_load_total_context(state)
    if not context_result.get("success"):
        return build_total_agent_result(
            state,
            success=False,
            intent="",
            result={"context": context_result},
            error_code=context_result.get("error_code") or "context_failed",
            error_message=context_result.get("error_message") or "",
        )

    intent_result = tool_infer_user_intent(state)
    intent = _safe_text(intent_result.get("intent"))
    final_result: dict = {"context": context_result, "intent": intent_result}
    success = True
    suggested_next_action = ""
    error_code = ""
    error_message = ""

    if intent == INTENT_RECOMMEND_LEARNING_PATH:
        recommendation_result = tool_run_learning_recommendation(state)
        final_result["recommendation"] = recommendation_result
        if recommendation_result.get("has_best_path"):
            suggested_next_action = ACTION_WAIT_USER_ACCEPTANCE
        else:
            normalization = tool_normalize_learning_goal_for_recommendation(state)
            final_result["goal_normalization"] = normalization
            suggested_next_action = normalization.get("suggested_next_action") or ACTION_ASK_GOAL_CLARIFICATION
            if suggested_next_action == ACTION_RETRY_RECOMMENDATION:
                retry_payload = dict(payload or {})
                retry_payload["goals"] = normalization.get("normalized_goals") or retry_payload.get("goals") or []
                retry_state = {"payload": retry_payload, "tool_trace": state["tool_trace"]}
                retry = tool_run_learning_recommendation(retry_state)
                state.update({key: value for key, value in retry_state.items() if key != "payload"})
                final_result["recommendation_retry"] = retry
                if retry.get("has_best_path"):
                    suggested_next_action = ACTION_WAIT_USER_ACCEPTANCE
                else:
                    suggested_next_action = ACTION_ASK_GOAL_CLARIFICATION
    elif intent == INTENT_ACCEPT_RECOMMENDATION:
        accept = tool_accept_learning_plan(state)
        final_result["accept_learning_plan"] = accept
        success = bool(accept.get("success"))
        suggested_next_action = accept.get("suggested_next_action") or ACTION_WAIT_USER_ACCEPTANCE
        if accept.get("accepted"):
            next_task = tool_get_next_learning_task(state)
            final_result["next_task"] = next_task
        error_code = accept.get("error_code") or ""
        error_message = accept.get("error_message") or ""
    elif intent == INTENT_GENERATE_CURRENT_STEP_RESOURCE:
        next_task = tool_get_next_learning_task(state)
        final_result["next_task"] = next_task
        if next_task.get("success"):
            generated = tool_generate_current_step_resource(state)
            final_result["resource_generation"] = generated
            success = bool(generated.get("success"))
            suggested_next_action = generated.get("suggested_next_action") or ACTION_RECORD_LEARNING_FEEDBACK
            error_code = generated.get("error_code") or ""
            error_message = generated.get("error_message") or ""
        else:
            success = False
            suggested_next_action = ACTION_ASK_GOAL_CLARIFICATION
            error_code = next_task.get("error_code") or "no_active_plan"
            error_message = next_task.get("error_message") or ""
    elif intent == INTENT_RECORD_LEARNING_FEEDBACK:
        feedback = tool_record_learning_feedback(state)
        final_result["record_learning_feedback"] = feedback
        next_task = tool_get_next_learning_task(state)
        final_result["next_task"] = next_task
        success = bool(feedback.get("success"))
        suggested_next_action = feedback.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
        error_code = feedback.get("error_code") or ""
        error_message = feedback.get("error_message") or ""
    elif intent == INTENT_SKIP_CURRENT_STEP:
        skipped = tool_skip_current_step(state)
        final_result["skip_current_step"] = skipped
        next_task = tool_get_next_learning_task(state)
        final_result["next_task"] = next_task
        success = bool(skipped.get("success"))
        suggested_next_action = skipped.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
        error_code = skipped.get("error_code") or ""
        error_message = skipped.get("error_message") or ""
    else:
        suggested_next_action = ACTION_ASK_GOAL_CLARIFICATION
        final_result["clarification"] = {
            "reason": intent_result.get("reason") or "need clearer learning goal",
        }

    return build_total_agent_result(
        state,
        success=success,
        intent=intent,
        result=final_result,
        suggested_next_action=suggested_next_action,
        error_code=error_code,
        error_message=error_message,
    )


__all__ = [
    "TOTAL_AGENT_TOOL_ORDER",
    "build_current_step_resource_strategy",
    "build_total_agent_result",
    "deterministic_run_total_agent",
    "get_study_graph_features",
    "load_profile_summary",
    "normalize_profile_summary",
    "normalize_study_graph_state",
    "tool_accept_learning_plan",
    "tool_generate_current_step_resource",
    "tool_get_next_learning_task",
    "tool_infer_user_intent",
    "tool_load_total_context",
    "tool_normalize_learning_goal_for_recommendation",
    "tool_record_learning_feedback",
    "tool_run_learning_recommendation",
    "tool_skip_current_step",
]
