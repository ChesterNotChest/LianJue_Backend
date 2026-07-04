from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Dict, Iterable, List, Optional

from tasks import personal_recommendation_task as prt
from tasks.common.status_events import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_SUCCEEDED,
    emit_status_event,
    emit_status_pair,
    get_status_events,
)
from tasks.common.search_tool import search_tool
from tasks.generative_task import generate_resources_from_request
from tasks.total_agent.agent_contracts import (
    ACTION_ASK_GOAL_CLARIFICATION,
    ACTION_GENERATE_CURRENT_STEP_RESOURCE,
    ACTION_GET_NEXT_LEARNING_TASK,
    ACTION_OFFER_PRACTICE_OR_RESOURCE,
    ACTION_RECORD_LEARNING_FEEDBACK,
    ACTION_RETRY_RECOMMENDATION,
    ACTION_WAIT_USER_ACCEPTANCE,
    GLOBAL_SIGNAL_ADVANCE_OR_ENRICH,
    GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE,
    GLOBAL_SIGNAL_INDIVIDUAL_TARGETED_SUPPORT,
    GLOBAL_SIGNAL_REINFORCE_SHARED_WEAKNESS,
    INTENT_ACCEPT_RECOMMENDATION,
    INTENT_ANSWER_LEARNING_QUESTION,
    INTENT_ASK_GOAL_CLARIFICATION,
    INTENT_GENERATE_CURRENT_STEP_RESOURCE,
    INTENT_RECORD_LEARNING_FEEDBACK,
    INTENT_RECOMMEND_LEARNING_PATH,
    INTENT_SKIP_CURRENT_STEP,
    LEARNING_EFFECT_LOW_SCORE_THRESHOLD,
    LEARNING_EFFECT_MASTERED_SCORE_THRESHOLD,
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
    QA_LEVEL_ASYNC_RESOURCE,
    QA_LEVEL_CONTEXTUAL,
    QA_LEVEL_FAST,
    QA_ANSWER_STYLE_CONCISE,
    QA_ANSWER_STYLE_DETAILED,
    QA_ANSWER_STYLE_NORMAL,
    QA_CONTEXT_SESSION_WINDOW_TURNS,
    QA_NEXT_ACTION_CLARIFY_GOAL,
    QA_NEXT_ACTION_CONTINUE_CURRENT_STEP,
    QA_NEXT_ACTION_OFFER_PRACTICE,
    QA_NEXT_ACTION_OFFER_RESOURCE,
    QA_QUESTION_TYPE_CONCEPT,
    QA_QUESTION_TYPE_EXERCISE_HELP,
    QA_QUESTION_TYPE_LEARNING_STRATEGY,
    QA_QUESTION_TYPE_UNKNOWN,
    QA_TONE_ENCOURAGING,
    QA_TONE_FRIENDLY_PRAGMATIC,
    QA_TONE_PRAGMATIC,
    QA_WARNING_LOW_RELEVANCE_EVIDENCE,
    QA_WARNING_PROFILE_WEAK_POINTS_FILTERED,
    RESOURCE_FEEDBACK_ACCEPTED,
    RESOURCE_FEEDBACK_DISLIKED,
    RESOURCE_FEEDBACK_REJECTED,
    RESOURCE_FEEDBACK_UNKNOWN,
    RESOURCE_FRESHNESS_EXPIRED,
    RESOURCE_FRESHNESS_FRESH,
    RESOURCE_FRESHNESS_STALE,
    RESOURCE_QUALITY_INVALID,
    RESOURCE_QUALITY_LOW_QUALITY,
    RESOURCE_QUALITY_NEEDS_REVIEW,
    RESOURCE_QUALITY_USABLE,
    RESOURCE_GENERATION_OVERALL_FAILED,
    RESOURCE_GENERATION_OVERALL_PARTIAL_SUCCESS,
    RESOURCE_GENERATION_OVERALL_SUCCEEDED,
    RESOURCE_RECOMMENDATION_GENERATE_ALL,
    RESOURCE_RECOMMENDATION_GENERATE_MISSING,
    RESOURCE_RECOMMENDATION_REUSE_EXISTING,
    RESOURCE_REUSE_MIN_MATCH_SCORE,
    RESOURCE_REUSE_REPEATED_FAILURE_THRESHOLD,
    RESOURCE_TASK_STATUS_FAILED,
    RESOURCE_TASK_STATUS_PENDING,
    RESOURCE_TASK_STATUS_RUNNING,
    RESOURCE_TASK_STATUS_SUCCEEDED,
    REUSE_REJECT_EXPIRED_RESOURCE,
    REUSE_REJECT_INVALID_RESOURCE,
    REUSE_REJECT_REPEATED_FAILURE,
    REUSE_REJECT_STUDENT_REJECTED,
    REUSE_REJECT_TOO_EASY,
    REUSE_REJECT_TOO_HARD,
    REUSE_REJECT_TOPIC_MISMATCH,
    TOOL_ABANDON_LEARNING_PLAN,
    TOOL_ACCEPT_LEARNING_PLAN,
    TOOL_ANSWER_LEARNING_QUESTION,
    TOOL_APPLY_LEARNING_EFFECT_SIGNAL,
    TOOL_DECIDE_RESOURCE_REUSE,
    TOOL_FIND_PERSONAL_RESOURCES,
    TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    TOOL_GET_COURSE_LEARNING_TREE_SUMMARY,
    TOOL_GET_NEXT_LEARNING_TASK,
    TOOL_INFER_USER_INTENT,
    TOOL_LOAD_TOTAL_CONTEXT,
    TOOL_NORMALIZE_LEARNING_GOAL,
    TOOL_RECORD_LEARNING_FEEDBACK,
    TOOL_RETRIEVE_LEARNING_EVIDENCE,
    TOOL_RUN_LEARNING_RECOMMENDATION,
    TOOL_SKIP_CURRENT_STEP,
    TOTAL_AGENT_CONTEXT_SCHEMA_VERSION,
    TOTAL_AGENT_LEARNING_EVENT_RECORDED,
    TOTAL_AGENT_SCHEMA_VERSION,
    TOTAL_AGENT_TOOL_ORDER,
)

TOTAL_AGENT_STATUS_AGENT = "total_agent"


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


def _notify_buddy_resource_ready_from_tool(state: Dict[str, Any], tool_result: dict) -> None:
    payload = _safe_dict(state.get("payload"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id")) or 0
    if not user_id or state.get("_study_buddy_event_sent"):
        return
    if not _safe_dict(tool_result).get("success", True):
        return
    raw_generation = _safe_dict(tool_result.get("generation_result"))
    resources = _safe_list(tool_result.get("resources")) or _normalize_resources(raw_generation)
    resource = _safe_dict(resources[0]) if resources else {}
    next_task = _safe_dict(tool_result.get("next_task"))
    event_payload = {
        "next_task_title": _safe_text(next_task.get("title") or next_task.get("topic")),
        "overall_status": _safe_text(tool_result.get("overall_status") or raw_generation.get("overall_status")),
        "resource": {
            "resource_id": _safe_text(resource.get("resource_id")),
            "resource_type": _safe_text(resource.get("resource_type") or resource.get("type")),
            "title": _safe_text(resource.get("title")),
            "topic": _safe_text(resource.get("topic")),
            "count": len(resources),
        },
    }
    try:
        from tasks.study_buddy_task import notify_study_buddy_event

        message = notify_study_buddy_event(
            user_id=user_id,
            syllabus_id=syllabus_id,
            event_type="resource_ready",
            payload=event_payload,
        )
        state["_study_buddy_event_sent"] = bool(message)
        if message:
            state["_study_buddy_event_type"] = "resource_ready"
            state["_study_buddy_message"] = message
    except Exception:
        import logging

        logging.getLogger(__name__).exception("[study_buddy.total_agent] resource_tool_notify_failed")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if not callable(item)}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple) or isinstance(value, set):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if callable(value):
        return f"<callable:{getattr(value, '__name__', value.__class__.__name__)}>"
    return _safe_text(value)


def _positive_int(value: Any) -> Optional[int]:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _append_trace(state: Dict[str, Any], tool_name: str) -> None:
    state.setdefault("run_id", f"total_agent_run_{uuid4().hex[:12]}")
    trace = state.setdefault("tool_trace", [])
    if isinstance(trace, list):
        trace.append(tool_name)
    emit_status_event(state, agent=TOTAL_AGENT_STATUS_AGENT, stage=tool_name, status=STATUS_RUNNING)


def _extend_status_events(target_state: Dict[str, Any], source_state_or_result: Any) -> None:
    if not isinstance(target_state, dict) or not isinstance(source_state_or_result, dict):
        return
    events = get_status_events(source_state_or_result)
    if not events:
        return
    target_events = target_state.setdefault("tool_status_events", [])
    if isinstance(target_events, list):
        target_events.extend(events)
    else:
        target_state["tool_status_events"] = list(events)


# ── error_code 白名单：这些 code 映射为 skipped 而非 failed ──
_TOOL_END_SKIPPED_ERROR_CODES: frozenset = frozenset({
    "no_active_plan",
    "no_next_task",
    "no_target_step",
    "no_resource_tasks",
    "active_plan_exists",
    "stale_snapshot",
})


def _tool_end_status(success: bool, error_code: str) -> str:
    """根据 success 和 error_code 计算 tool_end 的展示状态。"""
    if success:
        return STATUS_SUCCEEDED
    if error_code in _TOOL_END_SKIPPED_ERROR_CODES:
        return STATUS_SKIPPED
    return STATUS_FAILED


def _tool_result(tool_name: str, success: bool = True, state: Optional[Dict[str, Any]] = None, **payload: Any) -> dict:
    result = {"tool": tool_name, "success": bool(success)}
    result.update(_json_safe(payload))
    result.setdefault("error_code", "" if success else "tool_failed")
    result.setdefault("error_message", "")
    # tool_end 展示状态：前端直接使用，不再从 success 推断
    result["_status"] = _tool_end_status(success, str(result.get("error_code") or ""))
    if state is not None:
        emit_status_event(
            state,
            agent=TOTAL_AGENT_STATUS_AGENT,
            stage=tool_name,
            status=STATUS_SUCCEEDED if success else STATUS_FAILED,
            message=result.get("error_message") or "",
            payload={"error_code": result.get("error_code") or ""} if not success else {},
        )
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
    return _json_safe({
        "success": bool(success),
        "schema_version": TOTAL_AGENT_SCHEMA_VERSION,
        "intent": _safe_text(intent),
        "tool_trace": list(state.get("tool_trace") or []),
        "tool_status_events": get_status_events(state),
        "result": result or {},
        "suggested_next_action": _safe_text(suggested_next_action),
        "error_code": _safe_text(error_code),
        "error_message": _safe_text(error_message),
    })


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


def _format_percent(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ""
    if score <= 1:
        score *= 100
    return f"{round(score)}%"


def build_learning_feedback_guidance(payload: dict, feedback_result: dict, next_task_result: Optional[dict] = None) -> dict:
    """Turn structured learning feedback into a student-facing coaching note."""
    payload = _safe_dict(payload)
    feedback_result = _safe_dict(feedback_result)
    next_task_result = _safe_dict(next_task_result)
    event_payload = _safe_dict(_safe_dict(feedback_result.get("event_entry")).get("payload"))
    updated_step = _safe_dict(feedback_result.get("updated_step"))
    activated_step = _safe_dict(feedback_result.get("activated_step"))
    next_task = _safe_dict(feedback_result.get("next_task"))
    if next_task_result:
        next_task = _safe_dict(next_task_result.get("next_task")) or _safe_dict(next_task_result.get("task")) or next_task

    score = payload.get("score")
    if score is None:
        score = event_payload.get("score")
    score_text = _format_percent(score)
    wrong_items = _unique_texts(
        _list_from_any(payload.get("wrong_knowledge_items"))
        or _list_from_any(event_payload.get("wrong_knowledge_items"))
    )
    answer_record_count = len(_safe_list(payload.get("answer_records"))) or int(event_payload.get("answer_record_count") or 0)
    next_title = _safe_text(next_task.get("title") or next_task.get("topic"))
    updated_title = _safe_text(updated_step.get("title") or updated_step.get("topic"))
    activated_title = _safe_text(activated_step.get("title") or activated_step.get("topic"))

    lines: list[str] = []
    if score_text:
        lines.append(f"我已经记录这次练习结果，得分约 {score_text}。")
    else:
        lines.append("我已经记录这次学习反馈。")

    if wrong_items:
        preview = "、".join(wrong_items[:4])
        suffix = "等" if len(wrong_items) > 4 else ""
        lines.append(f"这次主要需要补的是：{preview}{suffix}。先把这些点讲清楚，再继续往后会更稳。")
    elif score_text:
        lines.append("这次没有明显错题知识点，说明当前小节掌握得还可以，可以进入下一步。")
    elif updated_title:
        lines.append(f"我会把“{updated_title}”作为已反馈内容，后续资源会按你的状态继续调整。")

    if next_title:
        lines.append(f"下一步建议看“{next_title}”。如果你愿意，我可以先围绕薄弱点给你做一个短讲解，再生成对应练习。")
    elif activated_title:
        lines.append(f"接下来可以进入“{activated_title}”。如果刚才有不确定的地方，可以先让我补讲一遍。")
    else:
        lines.append("接下来可以先回看错题解析，再告诉我你想补讲哪一题或直接继续下一份资源。")

    return {
        "reply": "\n".join(lines),
        "score": score,
        "score_text": score_text,
        "wrong_knowledge_items": wrong_items,
        "answer_record_count": answer_record_count,
        "updated_step_title": updated_title,
        "activated_step_title": activated_title,
        "next_task_title": next_title,
    }


def _confirmation_requested(payload: dict) -> bool:
    if payload.get("auto_accept") is True:
        return True
    message = _safe_text(payload.get("message"))
    markers = ("采纳", "确认", "就按", "按这条", "开始这条", "接受", "accept", "confirm")
    return any(marker in message.lower() for marker in markers)


def _has_pending_recommendation(state: Dict[str, Any]) -> bool:
    """Check if there's a proposed recommendation that can be accepted."""
    # Direct recommendation result in state (from prior agent tool call)
    recommendation = _safe_dict(state.get("recommendation_result"))
    if recommendation.get("best_path"):
        return True
    # Payload may carry a recommendation_result (e.g. from tests or API)
    payload = _safe_dict(state.get("payload"))
    payload_rec = _safe_dict(payload.get("recommendation_result"))
    if payload_rec.get("best_path"):
        return True
    # Total context may embed it from load_total_context
    total_context = _safe_dict(state.get("total_context"))
    rec_context = _safe_dict(total_context.get("recommendation") or total_context.get("recommendation_result"))
    return bool(rec_context.get("best_path"))


def _message_has_any(message: str, markers: Iterable[str]) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in markers)


def _message_is_vague_resource_request(message: str) -> bool:
    lowered = _safe_text(message).lower()
    if not lowered:
        return False
    vague_markers = ("随便", "任意", "都行", "来一个", "anything", "whatever", "random")
    if not any(marker in lowered for marker in vague_markers):
        return False
    concrete_markers = (
        "ppt",
        "slide",
        "slides",
        "文档",
        "资料",
        "quiz",
        "练习",
        "题",
        "代码",
        "coding",
        "mindmap",
        "思维导图",
        "总结",
        "复习",
        "继续",
        "下一步",
        "学习",
        "resource",
    )
    return not any(marker in lowered for marker in concrete_markers)


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
    return {item for item in raw if len(item) >= 2 and item not in _TOPIC_HINT_STOPWORDS}


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


def load_profile_summary(payload: dict, status_state: Optional[Dict[str, Any]] = None) -> dict:
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
    local_state: Dict[str, Any] = {
        "run_id": _safe_dict(status_state).get("run_id") or _safe_dict(payload).get("run_id") or "",
        "status_callback": _safe_dict(status_state).get("status_callback") or _safe_dict(payload).get("status_callback"),
        "tool_status_events": [],
    }
    try:
        from tasks import learning_profile_task

        profile = emit_status_pair(
            local_state,
            agent="profile_agent",
            stage="load_context",
            fn=lambda: learning_profile_task.get_persisted_learning_profile(user_id, syllabus_id),
            payload={"user_id": user_id, "syllabus_id": syllabus_id},
        )
        if isinstance(profile, dict) and profile:
            result = {
                "success": True,
                "source": PROFILE_SOURCE_PERSISTED,
                "profile": profile,
                "warnings": [],
                "error_code": "",
                "error_message": "",
            }
            result["tool_status_events"] = get_status_events(local_state)
            if status_state is not None:
                _extend_status_events(status_state, local_state)
            return result

        warnings.append(PROFILE_WARNING_NOT_FOUND)
        if action == PROFILE_READ_ACTION_BUILD_IF_MISSING:
            built = emit_status_pair(
                local_state,
                agent="profile_agent",
                stage="assemble_profile",
                fn=lambda: learning_profile_task.get_or_build_learning_profile(
                    user_id,
                    syllabus_id,
                    refresh_profile=False,
                    dialogue_text=_safe_dict(payload).get("message") or _safe_dict(payload).get("question"),
                    learning_goal=_safe_dict(payload).get("learning_goal"),
                ),
                payload={"user_id": user_id, "syllabus_id": syllabus_id},
            )
            if isinstance(built, dict) and built:
                result = {
                    "success": True,
                    "source": PROFILE_SOURCE_BUILT,
                    "profile": built,
                    "warnings": warnings,
                    "error_code": "",
                    "error_message": "",
                }
                result["tool_status_events"] = get_status_events(local_state)
                if status_state is not None:
                    _extend_status_events(status_state, local_state)
                return result
        else:
            warnings.append(PROFILE_WARNING_BUILD_SKIPPED)

        result = {
            "success": False,
            "source": PROFILE_SOURCE_NONE,
            "profile": {},
            "warnings": warnings,
            "error_code": PROFILE_WARNING_NOT_FOUND,
            "error_message": "no persisted learning profile",
        }
        result["tool_status_events"] = get_status_events(local_state)
        if status_state is not None:
            _extend_status_events(status_state, local_state)
        return result
    except Exception as exc:
        result = {
            "success": False,
            "source": PROFILE_SOURCE_NONE,
            "profile": {},
            "warnings": [f"{PROFILE_WARNING_READ_FAILED}:{exc}"],
            "error_code": PROFILE_WARNING_READ_FAILED,
            "error_message": _safe_text(exc),
        }
        result["tool_status_events"] = get_status_events(local_state)
        if status_state is not None:
            _extend_status_events(status_state, local_state)
        return result


def get_study_graph_features(user_id: int, syllabus_id: int, status_state: Optional[Dict[str, Any]] = None) -> dict:
    from tasks import study_graph_task

    local_state: Dict[str, Any] = {
        "run_id": _safe_dict(status_state).get("run_id") or "",
        "status_callback": _safe_dict(status_state).get("status_callback"),
        "tool_status_events": [],
    }
    features = emit_status_pair(
        local_state,
        agent="study_graph",
        stage="read_features",
        fn=lambda: study_graph_task.get_learning_tree_features(user_id, syllabus_id),
        payload={"user_id": user_id, "syllabus_id": syllabus_id},
    )
    if status_state is not None:
        _extend_status_events(status_state, local_state)
    return features if isinstance(features, dict) else {}


def build_current_step_resource_strategy(state: dict) -> dict:
    payload = _safe_dict(state.get("payload"))
    total_context = _safe_dict(state.get("total_context"))
    next_task = _safe_dict(state.get("next_task") or total_context.get("next_task"))
    profile = normalize_profile_summary(total_context.get("profile_summary"))
    study_graph_state = normalize_study_graph_state(total_context.get("study_graph_state"))
    course_summary = _safe_dict(total_context.get("course_learning_tree_summary"))
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
    message_requests_ppt = _message_has_any(message, ("ppt", "PPT", "幻灯片", "课件", "slides", "slide", "演示", "讲稿"))
    message_requests_doc = _message_has_any(message, ("文档", "doc", "document", "资料", "文章", "讲解", "说明"))
    matched_study_graph_weak_node = bool(
        (next_node_id and next_node_id in weak_node_ids)
        or (next_title and next_title in weak_node_ids)
        or bool(next_outcomes & weak_node_ids)
    )
    matched_profile_weak_point = bool(_unique_texts(weak_points))
    course_signal = _find_course_weak_signal(course_summary, [next_title, next_node_id, *outcomes, *weak_points])
    global_arbitration = {}
    if course_signal:
        personal_signal = _build_personal_signal_for_strategy(
            next_title=next_title,
            next_node_id=next_node_id,
            next_outcomes=outcomes,
            weak_points=weak_points,
            study_graph_state=study_graph_state,
            matched_profile_weak_point=matched_profile_weak_point,
            matched_study_graph_weak_node=matched_study_graph_weak_node,
        )
        global_arbitration = combine_global_and_personal_learning_signals(
            {"personal_signal": personal_signal, "course_signal": course_signal}
        )

    if explicit_resource_types:
        resource_types = explicit_resource_types
        reason = "user explicitly requested resource types"
    elif message_requests_ppt:
        resource_types = ["ppt"]
        reason = "message explicitly requests PPT/slides"
    elif message_requests_doc:
        resource_types = ["documents"]
        reason = "message explicitly requests documents"
    elif message_requests_coding:
        resource_types = ["coding_practice"]
        reason = "message requests coding practice"
    elif matched_profile_weak_point or matched_study_graph_weak_node:
        resource_types = _unique_texts([RESOURCE_STRATEGY_DEFAULT_TYPE, "quiz", *preferred_formats])
        reason = "current step is weak and profile/study graph indicates targeted practice"
    elif message_requests_practice:
        resource_types = ["quiz"]
        reason = "message explicitly requests quiz/practice"
    elif message_requests_review:
        resource_types = ["mindmap"]
        reason = "message requests review or summary"
    else:
        resource_types = [RESOURCE_STRATEGY_DEFAULT_TYPE]
        reason = "default lightweight current-step resource"

    difficulty = RESOURCE_STRATEGY_DIFFICULTY_STANDARD
    if matched_profile_weak_point or matched_study_graph_weak_node:
        difficulty = RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    if message_requests_review:
        difficulty = RESOURCE_STRATEGY_DIFFICULTY_REVIEW
    global_signal_action = _safe_text(_safe_dict(_safe_dict(global_arbitration).get("strategy_signal")).get("action"))
    if global_signal_action == GLOBAL_SIGNAL_INDIVIDUAL_TARGETED_SUPPORT:
        difficulty = RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    elif global_signal_action == GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE and difficulty == RESOURCE_STRATEGY_DIFFICULTY_STANDARD:
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
            "matched_course_global_weak_node": bool(course_signal),
            "global_signal_action": global_signal_action,
            "message_requests_practice": message_requests_practice,
            "message_requests_review": message_requests_review,
        },
        "global_signal_arbitration": _safe_dict(global_arbitration.get("strategy_signal")),
        "error_code": "",
        "error_message": "",
    }


def _compact_search_evidence(raw_result: Any, *, limit: int = 3) -> list[dict]:
    result = _safe_dict(raw_result)
    candidates = (
        _safe_list(result.get("contexts"))
        or _safe_list(result.get("chunks"))
        or _safe_list(result.get("results"))
        or _safe_list(result.get("documents"))
        or _safe_list(result.get("items"))
    )
    evidence = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            text = _safe_text(item)
            if text:
                evidence.append({"title": "", "summary": text[:240], "source": "RAG", "score": 0.0})
            continue
        summary = _safe_text(
            item.get("summary")
            or item.get("content")
            or item.get("text")
            or item.get("chunk")
            or item.get("paragraph")
        )
        if not summary:
            continue
        try:
            score = float(item.get("score") or item.get("similarity") or item.get("rrf_score") or 0.0)
        except Exception:
            score = 0.0
        evidence.append(
            {
                "title": _safe_text(item.get("title") or item.get("source") or item.get("doc_title") or item.get("id")),
                "summary": summary[:240],
                "source": "RAG",
                "score": score,
            }
        )
    if not evidence and _safe_text(result.get("summary")):
        evidence.append(
            {
                "title": _safe_text(result.get("title")),
                "summary": _safe_text(result.get("summary"))[:240],
                "source": "RAG",
                "score": 0.0,
            }
        )
    return evidence


def classify_learning_question(message: str) -> dict:
    text = _safe_text(message)
    lowered = text.lower()
    reason_codes: list[str] = []
    question_type = QA_QUESTION_TYPE_UNKNOWN
    confidence = 0.45
    if _message_has_any(lowered, ("下一步", "怎么学", "学习路线", "学习计划", "计划", "先学什么", "next step", "how should i learn")):
        question_type = QA_QUESTION_TYPE_LEARNING_STRATEGY
        confidence = 0.86
        reason_codes.extend(["asks_next_step", "asks_how_to_learn"])
    elif _message_has_any(lowered, ("这题", "答案", "错题", "选项", "为什么错", "practice", "exercise")):
        question_type = QA_QUESTION_TYPE_EXERCISE_HELP
        confidence = 0.78
        reason_codes.append("asks_exercise_help")
    elif _message_has_any(lowered, ("为什么", "为啥", "是什么", "解释", "区别", "关系", "原理", "why", "what is", "explain")):
        question_type = QA_QUESTION_TYPE_CONCEPT
        confidence = 0.82
        reason_codes.append("asks_concept_explanation")
    return {"question_type": question_type, "confidence": confidence, "reason_codes": _unique_texts(reason_codes)}


def _normalize_turn(item: Any) -> dict:
    if isinstance(item, str):
        return {"role": "user", "content": item[:300]}
    if not isinstance(item, dict):
        return {}
    role = _safe_text(item.get("role") or item.get("speaker") or "user") or "user"
    content = _safe_text(item.get("content") or item.get("text") or item.get("message"))
    if not content:
        return {}
    return {"role": role, "content": content[:300]}


_TOPIC_HINT_STOPWORDS = {
    "我",
    "你",
    "我们",
    "这个",
    "那个",
    "这些",
    "那些",
    "为什么",
    "为啥",
    "怎么",
    "怎样",
    "如何",
    "下一步",
    "应该",
    "可以",
    "需要",
    "学习",
    "理解",
    "解释",
    "讲讲",
    "说说",
    "当前",
    "建议",
    "先",
    "再",
    "会",
    "是",
    "的",
    "了",
    "吗",
    "呢",
    "和",
    "与",
    "或",
    "在",
    "看",
    "一下",
}


def _extract_topic_hints(*values: Any) -> list[str]:
    text = " ".join(_safe_text(value) for value in values if _safe_text(value))
    if not text:
        return []
    hints: list[str] = []
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_+-]{1,}", text):
        hints.append(match.group(0))

    chinese_text = re.sub(r"[^\u4e00-\u9fff]+", " ", text)
    for stopword in sorted(_TOPIC_HINT_STOPWORDS, key=len, reverse=True):
        chinese_text = chinese_text.replace(stopword, " ")
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,12}", chinese_text):
        chunk = chunk.strip()
        if chunk and chunk not in _TOPIC_HINT_STOPWORDS:
            hints.append(chunk)
    return _unique_texts(hints)[:8]


def build_session_context(payload: dict, limit: int = QA_CONTEXT_SESSION_WINDOW_TURNS) -> dict:
    payload = _safe_dict(payload)
    context = _safe_dict(payload.get("context"))
    raw_history = (
        payload.get("conversation_history")
        or payload.get("dialogue_history")
        or payload.get("messages")
        or context.get("conversation_history")
        or context.get("session_history")
        or []
    )
    if isinstance(raw_history, dict):
        raw_history = raw_history.get("dialogue_history") or raw_history.get("follow_up") or raw_history.get("items") or []
    if not isinstance(raw_history, list):
        raw_history = [raw_history] if raw_history else []
    recent_turns = [_normalize_turn(item) for item in raw_history[-max(1, int(limit)):]]
    recent_turns = [item for item in recent_turns if item]
    message = _safe_text(payload.get("message") or payload.get("question"))
    if message and (not recent_turns or recent_turns[-1].get("content") != message):
        recent_turns.append({"role": "user", "content": message[:300]})
        recent_turns = recent_turns[-max(1, int(limit)):]
    topic_hints = _extract_topic_hints(*[turn.get("content") for turn in recent_turns])
    return {
        "session_id": _safe_text(payload.get("session_id") or context.get("session_id")),
        "recent_turns": recent_turns,
        "last_user_message": next((turn["content"] for turn in reversed(recent_turns) if turn.get("role") == "user"), ""),
        "topic_hints": topic_hints,
        "warnings": [],
    }


def _answer_tone(payload: dict) -> dict:
    context = _safe_dict(_safe_dict(payload).get("context"))
    tone = _safe_text(payload.get("tone_style") or context.get("tone_style")) or QA_TONE_FRIENDLY_PRAGMATIC
    style = _safe_text(payload.get("answer_style") or context.get("answer_style")) or QA_ANSWER_STYLE_NORMAL
    if tone not in {QA_TONE_PRAGMATIC, QA_TONE_FRIENDLY_PRAGMATIC, QA_TONE_ENCOURAGING}:
        tone = QA_TONE_FRIENDLY_PRAGMATIC
    if style not in {QA_ANSWER_STYLE_CONCISE, QA_ANSWER_STYLE_NORMAL, QA_ANSWER_STYLE_DETAILED}:
        style = QA_ANSWER_STYLE_NORMAL
    return {"tone_style": tone, "answer_style": style}


def _short_knowledge_item(value: Any) -> bool:
    text = _safe_text(value)
    if not text:
        return False
    if len(text) > 28:
        return False
    if text in _TOPIC_HINT_STOPWORDS:
        return False
    if re.search(r"[，。；、,.!?！？]", text):
        return False
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text))


def filter_relevant_weak_points(question: str, context: dict, limit: int = 5) -> tuple[list[str], list[str]]:
    context = _safe_dict(context)
    profile = normalize_profile_summary(context.get("profile_summary"))
    study_graph = normalize_study_graph_state(context.get("study_graph_state"))
    next_task = _safe_dict(context.get("next_task"))
    session_context = _safe_dict(context.get("session_context"))
    weak_points = _unique_texts(_list_from_any(profile.get("weak_points")))
    anchors = _unique_texts(
        [
            question,
            next_task.get("title"),
            next_task.get("node_id"),
            *(_safe_list(next_task.get("outcomes"))),
            *(_safe_list(study_graph.get("weak_node_ids"))),
            *(_safe_list(session_context.get("topic_hints"))),
        ]
    )
    anchor_text = " ".join(anchors).lower()
    kept: list[str] = []
    filtered: list[str] = []
    for item in weak_points:
        text = _safe_text(item)
        if not text:
            continue
        explicit_hit = text.lower() in anchor_text or any(token.lower() in anchor_text for token in _extract_topic_hints(text))
        if _short_knowledge_item(text) and explicit_hit:
            kept.append(text)
        else:
            filtered.append(text)
    if not kept:
        for item in _safe_list(study_graph.get("weak_node_ids")):
            text = _safe_text(item)
            if _short_knowledge_item(text) and (text.lower() in anchor_text or not anchor_text):
                kept.append(text)
    return _unique_texts(kept)[:limit], _unique_texts(filtered)


def _evidence_query_terms(question: str, context: dict) -> list[str]:
    context = _safe_dict(context)
    next_task = _safe_dict(context.get("next_task"))
    profile = normalize_profile_summary(context.get("profile_summary"))
    study_graph = normalize_study_graph_state(context.get("study_graph_state"))
    session_context = _safe_dict(context.get("session_context"))
    relevant_weak, _ = filter_relevant_weak_points(question, context, limit=5)
    learning_goal = _safe_text(profile.get("learning_goal"))
    if len(learning_goal) > 40:
        learning_goal = ""
    return _unique_texts(
        [
            *_extract_topic_hints(question),
            *(_safe_list(session_context.get("topic_hints"))),
            learning_goal,
            next_task.get("title"),
            next_task.get("node_id"),
            *(_safe_list(next_task.get("outcomes"))),
            *relevant_weak,
            *(_safe_list(study_graph.get("weak_node_ids"))[:5]),
        ]
    )


def _build_evidence_query(message: str, context: dict) -> str:
    terms = _evidence_query_terms(message, context)
    query = " ".join(_unique_texts([message, *terms]))
    return query[:180]


def score_evidence_relevance(evidence: list[dict], query_terms: list[str]) -> list[dict]:
    terms = [term.lower() for term in _unique_texts(query_terms) if len(term) >= 2]
    scored = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        text = f"{_safe_text(item.get('title'))} {_safe_text(item.get('summary'))}".lower()
        hits = sum(1 for term in terms if term and term in text)
        payload = dict(item)
        payload["relevance_score"] = round(min(1.0, hits / max(1, min(len(terms), 5))), 4)
        payload["relevance"] = "high" if hits >= 3 else "medium" if hits >= 1 else "low"
        scored.append(payload)
    return scored


def retrieve_learning_evidence(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_RETRIEVE_LEARNING_EVIDENCE)
    payload = _safe_dict(state.get("payload"))
    context = _safe_dict(state.get("total_context"))
    message = _safe_text(payload.get("message") or payload.get("question"))
    qa_level = _safe_text(payload.get("qa_level")) or QA_LEVEL_FAST
    graph_name = _safe_text(payload.get("graph_name") or payload.get("rag_graph_name"))
    top_k = _positive_int(payload.get("rag_top_k")) or 3
    evidence = [dict(item) for item in _safe_list(payload.get("evidence_summary") or payload.get("mock_evidence")) if isinstance(item, dict)]
    warnings: list[str] = []

    query = _build_evidence_query(message, context)
    query_terms = _evidence_query_terms(message, context)

    if not evidence and graph_name and message and qa_level != QA_LEVEL_ASYNC_RESOURCE:
        try:
            raw_result = emit_status_pair(
                state,
                agent=TOTAL_AGENT_STATUS_AGENT,
                stage=TOOL_RETRIEVE_LEARNING_EVIDENCE,
                fn=lambda: search_tool(query or message, graph_name=graph_name, top_k=top_k),
                payload={"graph_name": graph_name, "top_k": top_k, "query": query or message},
            )
            evidence = _compact_search_evidence(raw_result, limit=top_k)
        except Exception as exc:
            warnings.extend(["rag_retrieval_failed", _safe_text(exc)])
    evidence = score_evidence_relevance(evidence, query_terms)
    if evidence and all(_safe_text(item.get("relevance")) == "low" for item in evidence):
        warnings.append(QA_WARNING_LOW_RELEVANCE_EVIDENCE)
    if not evidence:
        warnings.append("no_rag_evidence")

    result = _tool_result(
        TOOL_RETRIEVE_LEARNING_EVIDENCE,
        True,
        state=state,
        qa_level=qa_level,
        retrieval_query=query or message,
        query_terms=query_terms,
        evidence_summary=evidence,
        context_used={
            "profile": qa_level == QA_LEVEL_CONTEXTUAL,
            "active_plan": bool(context.get("active_plan")),
            "study_graph": bool(context.get("study_graph_state")),
            "rag": bool(evidence),
        },
        warnings=_unique_texts(warnings),
    )
    state["learning_evidence_result"] = result
    return result


def normalize_answer_payload(payload: dict) -> dict:
    payload = dict(payload or {})
    warnings = _unique_texts(_list_from_any(payload.get("warnings")))
    question_type = _safe_text(payload.get("question_type")) or QA_QUESTION_TYPE_UNKNOWN
    if question_type not in {
        QA_QUESTION_TYPE_CONCEPT,
        QA_QUESTION_TYPE_LEARNING_STRATEGY,
        QA_QUESTION_TYPE_EXERCISE_HELP,
        QA_QUESTION_TYPE_UNKNOWN,
    }:
        question_type = QA_QUESTION_TYPE_UNKNOWN
        warnings.append("invalid_question_type")
    text = _safe_text(payload.get("text"))
    key_points = _unique_texts(_list_from_any(payload.get("key_points")))
    if not key_points and text:
        key_points = [text[:120]]
    try:
        confidence = float(payload.get("confidence"))
    except Exception:
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    tone = _safe_dict(payload.get("tone"))
    tone_style = _safe_text(tone.get("tone_style")) or QA_TONE_FRIENDLY_PRAGMATIC
    answer_style = _safe_text(tone.get("answer_style")) or QA_ANSWER_STYLE_NORMAL
    if tone_style not in {QA_TONE_PRAGMATIC, QA_TONE_FRIENDLY_PRAGMATIC, QA_TONE_ENCOURAGING}:
        tone_style = QA_TONE_FRIENDLY_PRAGMATIC
        warnings.append("invalid_tone_style")
    if answer_style not in {QA_ANSWER_STYLE_CONCISE, QA_ANSWER_STYLE_NORMAL, QA_ANSWER_STYLE_DETAILED}:
        answer_style = QA_ANSWER_STYLE_NORMAL
        warnings.append("invalid_answer_style")
    return {
        "question_type": question_type,
        "text": text,
        "key_points": key_points[:6],
        "evidence_used": _safe_list(payload.get("evidence_used")),
        "plan_reference": _safe_dict(payload.get("plan_reference")),
        "relevant_weak_points": _safe_list(payload.get("relevant_weak_points")),
        "filtered_weak_points": _safe_list(payload.get("filtered_weak_points")),
        "next_actions": _safe_list(payload.get("next_actions")),
        "session_context_used": bool(payload.get("session_context_used")),
        "confidence": round(confidence, 4),
        "tone": {"tone_style": tone_style, "answer_style": answer_style},
        "warnings": warnings,
    }


def validate_answer_payload(payload: dict) -> dict:
    normalized = normalize_answer_payload(payload)
    return {"success": bool(normalized.get("text")), "answer": normalized, "error_code": "" if normalized.get("text") else "missing_answer_text"}


def _answer_key_points(question: str, evidence: list[dict], context: dict) -> list[str]:
    joined = " ".join([question, *[_safe_text(item.get("summary")) for item in evidence if isinstance(item, dict)]])
    points = []
    if _message_has_any(joined, ("rowkey", "热点", "hotspot")):
        points.extend(
            [
                "HBase 按 RowKey 的字典序和 key range 组织数据。",
                "单调递增或集中前缀的 RowKey 容易把写入压到少数 Region。",
                "加盐前缀、散列前缀和预分区可以帮助打散写入分布。",
            ]
        )
    elif evidence:
        points.extend(_safe_text(item.get("summary"))[:120] for item in evidence[:3] if isinstance(item, dict))
    weak_points, _ = filter_relevant_weak_points(question, context, limit=3)
    if weak_points:
        points.append(f"结合你的画像，当前可以优先补：{', '.join(_safe_text(item) for item in weak_points[:3])}。")
    return _unique_texts(points)[:5]


def _plan_reference(context: dict) -> dict:
    plan = _safe_dict(context.get("active_plan"))
    next_task = _safe_dict(context.get("next_task"))
    return {
        "plan_id": _safe_text(plan.get("plan_id")),
        "current_step_id": _safe_text(next_task.get("step_id")),
        "current_step_title": _safe_text(next_task.get("title")),
        "current_step_status": _safe_text(next_task.get("status")),
    } if plan or next_task else {}


def _next_action(action: str, resource_type: str = "") -> dict:
    return {
        "action": action,
        "label_key": f"agent.answer.next_action.{action}",
        "resource_type": resource_type,
    }


def _render_text(key_points: list[str], tone: dict, question_type: str = QA_QUESTION_TYPE_CONCEPT) -> str:
    style = tone.get("answer_style")
    points = key_points[:3 if style == QA_ANSWER_STYLE_CONCISE else 6 if style == QA_ANSWER_STYLE_DETAILED else 4]
    text = " ".join(points)
    if tone.get("tone_style") == QA_TONE_ENCOURAGING and text:
        if question_type == QA_QUESTION_TYPE_LEARNING_STRATEGY:
            return f"可以的，按这个节奏推进会更稳。{text}"
        if question_type == QA_QUESTION_TYPE_EXERCISE_HELP:
            return f"可以的，这题先拆开看。{text}"
        return f"可以的，先抓住主线。{text}"
    if tone.get("tone_style") == QA_TONE_FRIENDLY_PRAGMATIC and text:
        if question_type == QA_QUESTION_TYPE_LEARNING_STRATEGY:
            return f"你现在可以这样走：{text}"
        if question_type == QA_QUESTION_TYPE_EXERCISE_HELP:
            return f"这题可以这样拆：{text}"
        return f"可以先这样理解：{text}"
    return text


def build_learning_strategy_answer(state: dict, evidence: list[dict]) -> dict:
    payload = _safe_dict(state.get("payload"))
    context = _safe_dict(state.get("total_context"))
    question = _safe_text(payload.get("question") or payload.get("message"))
    tone = _answer_tone(payload)
    next_task = _safe_dict(context.get("next_task"))
    active_plan = _safe_dict(context.get("active_plan"))
    relevant_weak, filtered_weak = filter_relevant_weak_points(question, context, limit=5)
    key_points: list[str] = []
    next_actions: list[dict] = []
    if next_task:
        title = _safe_text(next_task.get("title") or next_task.get("node_id"))
        key_points.append(f"当前步骤：{title}。")
        focus_terms = _unique_texts(
            [
                *relevant_weak[:3],
                *(_safe_list(_safe_dict(context.get("session_context")).get("topic_hints"))[:3]),
                *(_safe_list(next_task.get("outcomes"))[:3]),
            ]
        )
        if focus_terms:
            key_points.append(f"先完成当前 step，再围绕 {', '.join(focus_terms[:3])} 做针对练习。")
        else:
            key_points.append("先完成当前 step，再进入后续知识点。")
        next_actions.append(_next_action(QA_NEXT_ACTION_CONTINUE_CURRENT_STEP, "documents"))
    elif active_plan:
        key_points.append("已有学习计划，但当前没有明确 active step，建议先读取下一步任务。")
        next_actions.append(_next_action(QA_NEXT_ACTION_CONTINUE_CURRENT_STEP))
    else:
        key_points.append("当前还没有 active plan，建议先确认学习目标并生成学习路径。")
        next_actions.append(_next_action(QA_NEXT_ACTION_CLARIFY_GOAL))
    if relevant_weak:
        key_points.append(f"重点补：{', '.join(relevant_weak[:3])}。")
    if relevant_weak:
        key_points.append("下一份资源建议用短文档打底，再接 targeted quiz 检查薄弱点。")
    else:
        key_points.append("下一份资源建议用短文档打底，再接一个小测确认是否可以推进。")
    next_actions.append(_next_action(QA_NEXT_ACTION_OFFER_PRACTICE, "quiz"))
    answer = normalize_answer_payload(
        {
            "question_type": QA_QUESTION_TYPE_LEARNING_STRATEGY,
            "text": _render_text(key_points, tone, QA_QUESTION_TYPE_LEARNING_STRATEGY),
            "key_points": key_points,
            "evidence_used": [_safe_dict(item) for item in evidence[:2]],
            "plan_reference": _plan_reference(context),
            "relevant_weak_points": relevant_weak,
            "filtered_weak_points": filtered_weak,
            "next_actions": next_actions,
            "session_context_used": bool(_safe_dict(context.get("session_context")).get("recent_turns")),
            "confidence": 0.84 if next_task else 0.66,
            "tone": tone,
        }
    )
    if filtered_weak:
        answer["warnings"] = _unique_texts([*answer.get("warnings", []), QA_WARNING_PROFILE_WEAK_POINTS_FILTERED])
    return answer


def build_concept_explanation_answer(state: dict, evidence: list[dict]) -> dict:
    payload = _safe_dict(state.get("payload"))
    context = _safe_dict(state.get("total_context"))
    question = _safe_text(payload.get("question") or payload.get("message"))
    tone = _answer_tone(payload)
    relevant_weak, filtered_weak = filter_relevant_weak_points(question, context, limit=5)
    key_points = _answer_key_points(question, evidence, context)
    text = _render_text(key_points, tone, QA_QUESTION_TYPE_CONCEPT) if key_points else "当前证据不足，我先给一个简短解释，后续建议补一份资料或练习。"
    answer = normalize_answer_payload(
        {
            "question_type": QA_QUESTION_TYPE_CONCEPT,
            "text": text,
            "key_points": key_points,
            "evidence_used": [_safe_dict(item) for item in evidence[:3]],
            "plan_reference": _plan_reference(context),
            "relevant_weak_points": relevant_weak,
            "filtered_weak_points": filtered_weak,
            "next_actions": [_next_action(QA_NEXT_ACTION_OFFER_RESOURCE, "documents")],
            "session_context_used": bool(_safe_dict(context.get("session_context")).get("recent_turns")),
            "confidence": 0.82 if evidence else 0.48,
            "tone": tone,
        }
    )
    if filtered_weak:
        answer["warnings"] = _unique_texts([*answer.get("warnings", []), QA_WARNING_PROFILE_WEAK_POINTS_FILTERED])
    return answer


def build_exercise_help_answer(state: dict, evidence: list[dict]) -> dict:
    payload = _safe_dict(state.get("payload"))
    tone = _answer_tone(payload)
    points = ["先定位题目考查的知识点，再对照 RowKey 排序、Region 边界和热点成因逐项排除。", "如果是热点规避题，优先判断写入是否集中、前缀是否能打散、预分区边界是否合理。"]
    return normalize_answer_payload(
        {
            "question_type": QA_QUESTION_TYPE_EXERCISE_HELP,
            "text": _render_text(points, tone, QA_QUESTION_TYPE_EXERCISE_HELP),
            "key_points": points,
            "evidence_used": [_safe_dict(item) for item in evidence[:2]],
            "plan_reference": _plan_reference(_safe_dict(state.get("total_context"))),
            "next_actions": [_next_action(QA_NEXT_ACTION_OFFER_PRACTICE, "quiz")],
            "session_context_used": bool(_safe_dict(_safe_dict(state.get("total_context")).get("session_context")).get("recent_turns")),
            "confidence": 0.72,
            "tone": tone,
        }
    )


def answer_learning_question(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_ANSWER_LEARNING_QUESTION)
    payload = _safe_dict(state.get("payload"))
    context = _safe_dict(state.get("total_context"))
    evidence_result = _safe_dict(state.get("learning_evidence_result"))
    question = _safe_text(payload.get("question") or payload.get("message"))
    qa_level = _safe_text(evidence_result.get("qa_level") or payload.get("qa_level")) or QA_LEVEL_FAST
    evidence = _safe_list(evidence_result.get("evidence_summary"))
    question_profile = classify_learning_question(_safe_text(payload.get("question_type_hint")) if _safe_text(payload.get("question_type_hint")) not in {"", "auto"} else question)
    question_type_hint = _safe_text(payload.get("question_type_hint"))
    if question_type_hint in {QA_QUESTION_TYPE_CONCEPT, QA_QUESTION_TYPE_LEARNING_STRATEGY, QA_QUESTION_TYPE_EXERCISE_HELP}:
        question_profile = {"question_type": question_type_hint, "confidence": 1.0, "reason_codes": ["explicit_hint"]}

    if qa_level == QA_LEVEL_ASYNC_RESOURCE:
        answer_payload = normalize_answer_payload(
            {
                "question_type": question_profile.get("question_type") or QA_QUESTION_TYPE_UNKNOWN,
                "text": "这个问题更适合生成专题资料或练习来系统处理。",
                "key_points": ["这个问题更适合生成专题资料或练习来系统处理。"],
                "next_actions": [_next_action(QA_NEXT_ACTION_OFFER_RESOURCE)],
                "confidence": 0.7,
                "tone": _answer_tone(payload),
            }
        )
        suggested = ACTION_GENERATE_CURRENT_STEP_RESOURCE
    elif question_profile.get("question_type") == QA_QUESTION_TYPE_LEARNING_STRATEGY:
        answer_payload = build_learning_strategy_answer(state, evidence)
        suggested = ACTION_OFFER_PRACTICE_OR_RESOURCE
    elif question_profile.get("question_type") == QA_QUESTION_TYPE_EXERCISE_HELP:
        answer_payload = build_exercise_help_answer(state, evidence)
        suggested = ACTION_OFFER_PRACTICE_OR_RESOURCE
    else:
        answer_payload = build_concept_explanation_answer(state, evidence)
        suggested = ACTION_OFFER_PRACTICE_OR_RESOURCE
    warnings = _unique_texts([*(_safe_list(evidence_result.get("warnings"))), *(_safe_list(answer_payload.get("warnings")))])
    answer_payload["warnings"] = warnings

    result = _tool_result(
        TOOL_ANSWER_LEARNING_QUESTION,
        True,
        state=state,
        answer=answer_payload,
        question_profile=question_profile,
        evidence_summary=evidence,
        suggested_next_action=suggested,
        plan_mutation=False,
        resource_generation=False,
        warnings=warnings,
    )
    state["answer_learning_question_result"] = result
    return result


def find_personal_resources(payload: dict) -> dict:
    requested_types = _unique_texts(_list_from_any(payload.get("resource_types")))
    resources = _safe_list(payload.get("resources") or payload.get("personal_resources"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    node_id = _safe_text(payload.get("node_id"))
    knowledge_items = set(_unique_texts(_list_from_any(payload.get("knowledge_items"))))
    matches = []
    seen_types = set()
    for item in resources:
        if not isinstance(item, dict):
            continue
        if user_id and _positive_int(item.get("user_id")) not in (None, user_id):
            continue
        if syllabus_id and _positive_int(item.get("syllabus_id")) not in (None, syllabus_id):
            continue
        resource_type = _safe_text(item.get("resource_type"))
        if requested_types and resource_type not in requested_types:
            continue
        item_knowledge = set(_unique_texts(_list_from_any(item.get("knowledge_items"))))
        score = 0.0
        if resource_type in requested_types:
            score += 0.35
        if node_id and node_id == _safe_text(item.get("node_id")):
            score += 0.3
        if knowledge_items and item_knowledge:
            score += min(0.25, 0.1 * len(knowledge_items & item_knowledge))
        if _safe_text(item.get("topic")) and any(point in _safe_text(item.get("topic")) for point in knowledge_items):
            score += 0.1
        match = dict(item)
        match.setdefault("quality_state", RESOURCE_QUALITY_NEEDS_REVIEW)
        match.setdefault("freshness_state", RESOURCE_FRESHNESS_FRESH)
        match.setdefault("student_feedback_state", RESOURCE_FEEDBACK_UNKNOWN)
        match["match_score"] = round(min(score, 1.0), 4)
        matches.append(match)
        seen_types.add(resource_type)
    return {
        "success": True,
        "matches": matches,
        "missing_resource_types": [item for item in requested_types if item not in seen_types],
        "warnings": [],
        "error_code": "",
        "error_message": "",
    }


def decide_resource_reuse(payload: dict) -> dict:
    requested_types = _unique_texts(_list_from_any(payload.get("requested_resource_types") or payload.get("resource_types")))
    learning_effect = _safe_dict(payload.get("learning_effect"))
    reusable = []
    skipped = []
    reusable_types = set()
    for item in _safe_list(payload.get("matches")):
        if not isinstance(item, dict):
            continue
        reasons = []
        quality = _safe_text(item.get("quality_state")) or RESOURCE_QUALITY_NEEDS_REVIEW
        freshness = _safe_text(item.get("freshness_state")) or RESOURCE_FRESHNESS_FRESH
        feedback_state = _safe_text(item.get("student_feedback_state")) or RESOURCE_FEEDBACK_UNKNOWN
        feedback = _safe_dict(item.get("student_feedback"))
        failure_count = int(item.get("failure_count") or 0)
        match_score = float(item.get("match_score") or 0.0)
        if _safe_dict(item.get("validation")).get("valid") is False or quality in {RESOURCE_QUALITY_INVALID, RESOURCE_QUALITY_LOW_QUALITY}:
            reasons.append(REUSE_REJECT_INVALID_RESOURCE)
        if freshness == RESOURCE_FRESHNESS_EXPIRED:
            reasons.append(REUSE_REJECT_EXPIRED_RESOURCE)
        if feedback_state == RESOURCE_FEEDBACK_REJECTED or feedback.get("explicitly_rejected") is True:
            reasons.append(REUSE_REJECT_STUDENT_REJECTED)
        if feedback_state == RESOURCE_FEEDBACK_DISLIKED and failure_count >= 1:
            reasons.append(REUSE_REJECT_REPEATED_FAILURE)
        if failure_count >= RESOURCE_REUSE_REPEATED_FAILURE_THRESHOLD:
            reasons.append(REUSE_REJECT_REPEATED_FAILURE)
        if feedback.get("too_easy") is True and learning_effect.get("current_need") != "foundation_review":
            reasons.append(REUSE_REJECT_TOO_EASY)
        if feedback.get("too_hard") is True and learning_effect.get("current_need") != "challenge":
            reasons.append(REUSE_REJECT_TOO_HARD)
        if match_score < RESOURCE_REUSE_MIN_MATCH_SCORE:
            reasons.append(REUSE_REJECT_TOPIC_MISMATCH)
        if reasons:
            skipped.append({"resource_id": item.get("resource_id"), "resource_type": item.get("resource_type"), "skip_reason_codes": _unique_texts(reasons)})
            continue
        reusable.append({"resource_id": item.get("resource_id"), "resource_type": item.get("resource_type"), "reuse_reason_codes": ["fresh", "high_match"]})
        reusable_types.add(_safe_text(item.get("resource_type")))
    missing = [item for item in requested_types if item not in reusable_types]
    mode = RESOURCE_RECOMMENDATION_REUSE_EXISTING if reusable and not missing else RESOURCE_RECOMMENDATION_GENERATE_MISSING if reusable else RESOURCE_RECOMMENDATION_GENERATE_ALL
    return {"success": True, "resource_recommendation_mode": mode, "reusable_resources": reusable, "skipped_resources": skipped, "missing_resource_types": missing, "warnings": []}


def apply_learning_effect_signal(payload: dict) -> dict:
    try:
        score = float(payload.get("score"))
    except Exception:
        score = None
    wrong_items = _unique_texts(_list_from_any(payload.get("wrong_knowledge_items")))
    feedback = _safe_dict(payload.get("student_feedback"))
    if score is not None and score < LEARNING_EFFECT_LOW_SCORE_THRESHOLD:
        mastery_signal = "struggled"
        next_strategy = RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    elif score is not None and score >= LEARNING_EFFECT_MASTERED_SCORE_THRESHOLD:
        mastery_signal = "mastered"
        next_strategy = RESOURCE_STRATEGY_DIFFICULTY_STANDARD
    else:
        mastery_signal = "practiced"
        next_strategy = RESOURCE_STRATEGY_DIFFICULTY_REVIEW if wrong_items else RESOURCE_STRATEGY_DIFFICULTY_STANDARD
    resource_feedback_state = RESOURCE_FEEDBACK_UNKNOWN
    if feedback.get("explicitly_rejected") is True:
        resource_feedback_state = RESOURCE_FEEDBACK_REJECTED
    elif feedback.get("too_hard") is True or feedback.get("too_easy") is True or feedback.get("liked") is False:
        resource_feedback_state = RESOURCE_FEEDBACK_DISLIKED
    elif feedback.get("liked") is True:
        resource_feedback_state = RESOURCE_FEEDBACK_ACCEPTED
    return {
        "success": True,
        "learning_effect": {
            "mastery_signal": mastery_signal,
            "weak_knowledge_items": wrong_items if mastery_signal == "struggled" else [],
            "mastered_knowledge_items": wrong_items if mastery_signal == "mastered" else [],
            "resource_feedback_state": resource_feedback_state,
            "next_resource_strategy": next_strategy,
        },
        "profile_signal": {
            "refresh_recommended": mastery_signal == "struggled",
            "reason_codes": _unique_texts(["low_score" if mastery_signal == "struggled" else "", "weak_knowledge_items" if wrong_items else ""]),
        },
        "warnings": [],
    }


def _mastery_is_strong(signal: dict) -> bool:
    label = _safe_text(signal.get("mastery_label") or signal.get("label"))
    try:
        score = float(signal.get("mastery_score") if signal.get("mastery_score") is not None else signal.get("score"))
    except Exception:
        score = 0.0
    return label in {"mastered", "high", "strong"} or score >= LEARNING_EFFECT_MASTERED_SCORE_THRESHOLD


def _mastery_is_weak(signal: dict) -> bool:
    label = _safe_text(signal.get("mastery_label") or signal.get("label"))
    try:
        score = float(signal.get("mastery_score") if signal.get("mastery_score") is not None else signal.get("score"))
    except Exception:
        score = 1.0
    return label in {"weak", "low", "struggled"} or score < LEARNING_EFFECT_LOW_SCORE_THRESHOLD


def _course_signal_is_weak(signal: dict) -> bool:
    if signal.get("is_class_weak") is True:
        return True
    try:
        weak_count = int(signal.get("weak_student_count") or 0)
    except Exception:
        weak_count = 0
    try:
        average = float(signal.get("average_mastery") or 1.0)
    except Exception:
        average = 1.0
    return weak_count > 0 or average < LEARNING_EFFECT_LOW_SCORE_THRESHOLD


def combine_global_and_personal_learning_signals(payload: dict) -> dict:
    payload = _safe_dict(payload)
    personal = _safe_dict(payload.get("personal_signal"))
    course = _safe_dict(payload.get("course_signal"))
    knowledge_item = _safe_text(
        payload.get("knowledge_item")
        or personal.get("knowledge_item")
        or personal.get("title")
        or course.get("knowledge_item")
        or course.get("title")
    )
    personal_known = bool(personal)
    personal_weak = personal_known and _mastery_is_weak(personal)
    personal_strong = personal_known and _mastery_is_strong(personal)
    course_weak = _course_signal_is_weak(course)

    if personal_weak and course_weak:
        action = GLOBAL_SIGNAL_REINFORCE_SHARED_WEAKNESS
        resource_strategy = RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    elif personal_strong and course_weak:
        action = GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE
        resource_strategy = RESOURCE_STRATEGY_DIFFICULTY_REVIEW
    elif personal_weak and not course_weak:
        action = GLOBAL_SIGNAL_INDIVIDUAL_TARGETED_SUPPORT
        resource_strategy = RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    elif personal_strong and not course_weak:
        action = GLOBAL_SIGNAL_ADVANCE_OR_ENRICH
        resource_strategy = RESOURCE_STRATEGY_DIFFICULTY_STANDARD
    elif course_weak:
        action = GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE
        resource_strategy = RESOURCE_STRATEGY_DIFFICULTY_REVIEW
    else:
        action = GLOBAL_SIGNAL_ADVANCE_OR_ENRICH
        resource_strategy = RESOURCE_STRATEGY_DIFFICULTY_STANDARD

    return {
        "success": True,
        "strategy_signal": {
            "knowledge_item": knowledge_item,
            "matched_profile_weak_point": bool(personal.get("matched_profile_weak_point") or personal_weak),
            "matched_own_study_graph_weak_node": bool(personal.get("matched_own_study_graph_weak_node") or personal_weak),
            "matched_course_global_weak_node": course_weak,
            "personal_mastery_known": personal_known,
            "personal_mastery_label": _safe_text(personal.get("mastery_label") or personal.get("label")),
            "personal_mastery_score": personal.get("mastery_score") if personal.get("mastery_score") is not None else personal.get("score"),
            "course_average_mastery": course.get("average_mastery"),
            "action": action,
            "resource_strategy": resource_strategy,
        },
        "warnings": [],
    }


def get_course_learning_tree_summary(payload: dict) -> dict:
    from tasks import study_graph_task

    return study_graph_task.get_course_learning_tree_summary(_safe_dict(payload))


def _find_course_weak_signal(course_summary: dict, knowledge_items: Iterable[Any]) -> dict:
    summary = _safe_dict(course_summary.get("summary") if isinstance(course_summary.get("summary"), dict) else course_summary)
    weak_nodes = _safe_list(summary.get("weak_nodes"))
    candidates = _unique_texts(knowledge_items)
    for node in weak_nodes:
        if not isinstance(node, dict):
            continue
        title = _safe_text(node.get("title"))
        if title and (title in candidates or any(title in item or item in title for item in candidates)):
            result = dict(node)
            result["knowledge_item"] = title
            result["is_class_weak"] = True
            return result
    return {}


def _build_personal_signal_for_strategy(
    *,
    next_title: str,
    next_node_id: str,
    next_outcomes: Iterable[Any],
    weak_points: Iterable[Any],
    study_graph_state: dict,
    matched_profile_weak_point: bool,
    matched_study_graph_weak_node: bool,
) -> dict:
    candidates = _unique_texts([next_title, next_node_id, *list(next_outcomes), *list(weak_points)])
    weak_nodes = set(_unique_texts(_list_from_any(study_graph_state.get("weak_node_ids"))))
    mastered_nodes = set(_unique_texts(_list_from_any(study_graph_state.get("mastered_node_ids"))))
    if matched_profile_weak_point or matched_study_graph_weak_node:
        return {
            "knowledge_item": candidates[0] if candidates else "",
            "mastery_label": "weak",
            "mastery_score": 0.3,
            "matched_profile_weak_point": matched_profile_weak_point,
            "matched_own_study_graph_weak_node": matched_study_graph_weak_node,
        }
    if any(item in mastered_nodes for item in candidates):
        return {
            "knowledge_item": candidates[0] if candidates else "",
            "mastery_label": "mastered",
            "mastery_score": 0.9,
            "matched_profile_weak_point": False,
            "matched_own_study_graph_weak_node": False,
        }
    if any(item in weak_nodes for item in candidates):
        return {
            "knowledge_item": candidates[0] if candidates else "",
            "mastery_label": "weak",
            "mastery_score": 0.3,
            "matched_profile_weak_point": False,
            "matched_own_study_graph_weak_node": True,
        }
    return {}


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
            state=state,
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
        profile_read = load_profile_summary(payload, status_state=state)
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
            try:
                graph_features = get_study_graph_features(user_id, syllabus_id, status_state=state)
            except TypeError:
                graph_features = get_study_graph_features(user_id, syllabus_id)
            study_graph_state = normalize_study_graph_state(graph_features)
        except Exception as exc:
            warnings.append(f"study_graph_read_failed:{exc}")
            study_graph_state = normalize_study_graph_state({})
            study_graph_state["warnings"].append(f"study_graph_read_failed:{exc}")

    course_learning_tree_summary = _safe_dict(payload.get("course_learning_tree_summary"))
    course_summary_input = payload.get("course_tree_summary_payload")
    if not course_learning_tree_summary and isinstance(course_summary_input, dict):
        try:
            course_learning_tree_summary = get_course_learning_tree_summary(course_summary_input)
            for warning in _list_from_any(course_learning_tree_summary.get("warnings")):
                text = _safe_text(warning)
                if text:
                    warnings.append(text)
        except Exception as exc:
            warnings.append(f"course_learning_tree_summary_failed:{exc}")
            course_learning_tree_summary = {}

    session_context = build_session_context(payload)

    total_context = {
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "active_plan": active_plan,
        "next_task": next_task,
        "profile_summary": profile_summary,
        "current_resource_id": _safe_text(context.get("current_resource_id") or payload.get("resource_id")),
        "recent_resource_ids": list(_safe_list(context.get("recent_resource_ids"))),
        "study_graph_state": study_graph_state,
        "course_learning_tree_summary": course_learning_tree_summary,
        "session_context": session_context,
        "warnings": warnings,
    }
    state["total_context"] = total_context
    state["active_plan"] = active_plan
    state["next_task"] = next_task
    return _tool_result(
        TOOL_LOAD_TOTAL_CONTEXT,
        True,
        state=state,
        user_id=user_id,
        syllabus_id=syllabus_id,
        active_plan=active_plan,
        next_task=next_task,
        profile_summary=profile_summary,
        current_resource_id=total_context["current_resource_id"],
        study_graph_state=study_graph_state,
        session_context=session_context,
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
    elif _confirmation_requested(payload) and _has_pending_recommendation(state):
        intent = INTENT_ACCEPT_RECOMMENDATION
        confidence = 0.9
        reason = "message confirms a pending recommendation path"
    elif _confirmation_requested(payload):
        # User used confirmation language but there's nothing to accept —
        # fall through to later stages instead of blocking on accept.
        intent = INTENT_GENERATE_CURRENT_STEP_RESOURCE if active_plan else INTENT_RECOMMEND_LEARNING_PATH
        confidence = 0.72
        reason = "confirmation-like message but no pending recommendation; treating as continue/recommend"
    elif _message_has_any(message, ("完成", "做完", "看完", "学完", "得分", "通过", "done", "completed", "finished", "score")):
        intent = INTENT_RECORD_LEARNING_FEEDBACK
        confidence = 0.86
        reason = "message reports current learning feedback"
    elif _message_has_any(message, ("跳过", "太简单", "换一个", "skip")):
        intent = INTENT_SKIP_CURRENT_STEP
        confidence = 0.84
        reason = "message asks to skip or replace current step"
    elif active_plan and _message_has_any(message, ("下一步", "怎么学", "怎么学习", "先学什么", "next step", "how should i learn")) and not _message_has_any(message, ("推荐", "路径", "规划", "recommend", "path", "route")):
        intent = INTENT_ANSWER_LEARNING_QUESTION
        confidence = 0.85
        reason = "message asks for learning strategy within current active plan"
    elif _message_has_any(message, ("推荐", "路径", "学什么", "怎么学", "规划", "recommend", "path", "route")):
        intent = INTENT_RECOMMEND_LEARNING_PATH
        confidence = 0.82
        reason = "message asks for learning path recommendation"
    elif (
        _message_has_any(message, ("继续", "下一步", "开始学习", "给我资料", "生成资源", "给我生成", "来生成", "resource", "continue", "next", "生成", "产", "给我", "帮我生成", "帮我做", "帮我产"))
        and (active_plan or not _message_is_vague_resource_request(message))
    ):
        intent = INTENT_GENERATE_CURRENT_STEP_RESOURCE
        confidence = 0.88
        reason = "message explicitly asks to generate learning resources"
    elif _message_has_any(message, ("为什么", "为啥", "是什么", "解释", "区别", "关系", "怎么理解", "question", "why", "explain")):
        intent = INTENT_ANSWER_LEARNING_QUESTION
        confidence = 0.84
        reason = "message asks a learning question"
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
        state=state,
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
            state=state,
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
        recommendation = emit_status_pair(
            state,
            agent="recommendation_agent",
            stage="rank_path",
            fn=lambda: prt.run_recommendation_route_from_payload(payload),
            payload={"user_id": user_id, "syllabus_id": payload.get("syllabus_id")},
        )

    prt.ensure_recommendation_snapshot(
        user_id,
        _positive_int(payload.get("syllabus_id")) or None,
        recommendation,
        request_payload=payload,
        session_id=payload.get("session_id"),
        persist_snapshot=payload.get("persist_snapshot") is not False,
        allow_proposed_resave=bool(injected),
    )
    state["recommendation_result"] = recommendation
    best_path = _safe_dict(recommendation).get("best_path")
    has_best_path = isinstance(best_path, dict) and bool(best_path.get("path"))
    suggested = ACTION_WAIT_USER_ACCEPTANCE if has_best_path else ACTION_ASK_GOAL_CLARIFICATION
    return _tool_result(
        TOOL_RUN_LEARNING_RECOMMENDATION,
        bool(_safe_dict(recommendation).get("success", True)),
        state=state,
        recommendation=recommendation,
        recommendation_id=_safe_text(_safe_dict(recommendation).get("recommendation_id")),
        snapshot=_safe_dict(recommendation).get("snapshot"),
        snapshot_status=_safe_text(_safe_dict(recommendation).get("snapshot_status")),
        snapshot_save_error_code=_safe_text(_safe_dict(recommendation).get("snapshot_save_error_code")),
        snapshot_save_error_message=_safe_text(_safe_dict(recommendation).get("snapshot_save_error_message")),
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
            state=state,
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
            state=state,
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
            state=state,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )
    if not _confirmation_requested(payload):
        return _tool_result(
            TOOL_ACCEPT_LEARNING_PLAN,
            True,
            state=state,
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
            state=state,
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
            state=state,
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
        state=state,
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
            state=state,
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
        state=state,
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

    # graph_name: always derive from syllabus_id (fixed at total agent entry)
    graph_name = ""
    sid = payload.get("syllabus_id")
    if sid:
        try:
            from tasks.syllabus_task import _get_primary_graph_info
            _, graph_name = _get_primary_graph_info(int(sid))
            graph_name = _safe_text(graph_name)
        except Exception:
            graph_name = ""

    # question: build a semantically rich RAG query from structured knowledge
    # items — the resource agent does NOT interpret user intent, it needs
    # concrete technical keywords to retrieve against the knowledge graph.
    question_parts: list[str] = []
    if title:
        question_parts.append(f"学习主题: {title}")
    if outcomes:
        question_parts.append("知识点: " + "; ".join(outcomes))
    profile_summary = _safe_dict(_safe_dict(state.get("total_context")).get("profile_summary"))
    weak_points = _safe_list(profile_summary.get("weak_points"))
    if weak_points:
        question_parts.append("薄弱环节: " + "; ".join(weak_points))
    question = "\n".join(question_parts) if question_parts else _safe_text(
        payload.get("question") or payload.get("message") or f"请生成 {title} 的学习资源"
    )

    return {
        "user_id": payload.get("user_id"),
        "syllabus_id": payload.get("syllabus_id"),
        "message": payload.get("message") or payload.get("question") or "",
        "question": question,
        "topic": title,
        "target": title,
        "current_step": next_task,
        "knowledge_items": knowledge_items,
        "resource_types": resource_types,
        "difficulty": strategy.get("difficulty") or RESOURCE_STRATEGY_DIFFICULTY_STANDARD,
        "strategy_reason": strategy.get("reason") or "",
        "strategy_signals": _safe_dict(strategy.get("strategy_signals")),
        "resource_strategy": strategy,
        "graph_name": graph_name,
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


def _resource_task_id(resource_type: str) -> str:
    return f"resource_task:{_safe_text(resource_type)}"


def _resource_type_from_item(item: dict) -> str:
    return _safe_text(_safe_dict(item).get("resource_type") or _safe_dict(item).get("type"))


def _annotate_resource_status_events(events: Any, *, resource_type: str, task_id: str) -> list[dict]:
    annotated: list[dict] = []
    for event in _safe_list(events):
        if not isinstance(event, dict):
            continue
        item = deepcopy(event)
        payload = dict(_safe_dict(item.get("payload")))
        payload.setdefault("resource_type", resource_type)
        payload.setdefault("task_id", task_id)
        item["payload"] = payload
        item.setdefault("agent", "resource_agent")
        annotated.append(item)
    return annotated


def plan_resource_type_tasks(request_payload: dict) -> list[dict]:
    base_request = deepcopy(_safe_dict(request_payload))
    base_request.pop("status_callback", None)
    resource_types = _unique_texts(_safe_list(base_request.get("resource_types"))) or [RESOURCE_STRATEGY_DEFAULT_TYPE]
    tasks: list[dict] = []
    for resource_type in resource_types:
        normalized_type = _safe_text(resource_type)
        if not normalized_type:
            continue
        task_request = deepcopy(base_request)
        task_request["resource_types"] = [normalized_type]
        task_request["resource_type"] = normalized_type
        task_request["assigned_resource_type"] = normalized_type
        task_request["single_type_mode"] = True
        task_id = _resource_task_id(normalized_type)
        task_request["resource_task_id"] = task_id
        tasks.append(
            {
                "task_id": task_id,
                "resource_type": normalized_type,
                "status": RESOURCE_TASK_STATUS_PENDING,
                "request": task_request,
                "result": {},
                "error_code": "",
                "error_message": "",
            }
        )
    return tasks


def _run_single_resource_task(task: dict) -> dict:
    result_task = deepcopy(task)
    result_task["status"] = RESOURCE_TASK_STATUS_RUNNING
    resource_type = _safe_text(result_task.get("resource_type"))
    task_id = _safe_text(result_task.get("task_id"))
    try:
        generation_result = generate_resources_from_request(deepcopy(_safe_dict(result_task.get("request"))))
    except Exception as exc:
        generation_result = {
            "success": False,
            "resources": [],
            "tool_status_events": [],
            "error_code": "resource_generation_exception",
            "error_message": _safe_text(exc),
        }

    if not isinstance(generation_result, dict):
        generation_result = {
            "success": False,
            "resources": [],
            "tool_status_events": [],
            "error_code": "invalid_generation_result",
            "error_message": "resource generation returned a non-dict result",
        }

    resources = []
    warnings = _unique_texts(_safe_list(generation_result.get("warnings")))
    for resource in _normalize_resources(generation_result):
        if not isinstance(resource, dict):
            continue
        if _resource_type_from_item(resource) != resource_type:
            warnings.append("resource_type_mismatch")
            continue
        resources.append(resource)

    generation_result = dict(generation_result)
    generation_result["resources"] = resources
    generation_result["resource_count"] = len(resources)
    generation_result["warnings"] = _unique_texts(warnings)
    generation_result["tool_status_events"] = _annotate_resource_status_events(
        generation_result.get("tool_status_events"),
        resource_type=resource_type,
        task_id=task_id,
    )

    success = bool(generation_result.get("success")) and bool(resources)
    result_task["status"] = RESOURCE_TASK_STATUS_SUCCEEDED if success else RESOURCE_TASK_STATUS_FAILED
    result_task["result"] = generation_result
    result_task["error_code"] = _safe_text(generation_result.get("error_code"))
    result_task["error_message"] = _safe_text(generation_result.get("error_message"))
    return result_task


def _current_flask_app_or_none() -> Any:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            return current_app._get_current_object()
    except Exception:
        return None
    return None


def _run_single_resource_task_with_app_context(task: dict, app: Any = None) -> dict:
    if app is None:
        return _run_single_resource_task(task)
    with app.app_context():
        return _run_single_resource_task(task)


def run_resource_type_tasks(state: Dict[str, Any], resource_tasks: list[dict]) -> dict:
    tasks = [deepcopy(task) for task in resource_tasks if isinstance(task, dict)]
    if not tasks:
        return {
            "success": False,
            "overall_status": RESOURCE_GENERATION_OVERALL_FAILED,
            "resources": [],
            "resource_results": {},
            "resource_tasks": [],
            "failed_resource_types": [],
            "tool_status_events": [],
            "error_code": "no_resource_tasks",
            "error_message": "no resource tasks to execute",
        }

    max_workers = max(1, len(tasks))
    ordered_results: list[Optional[dict]] = [None] * len(tasks)
    app = _current_flask_app_or_none()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(_run_single_resource_task_with_app_context, task, app): index for index, task in enumerate(tasks)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                ordered_results[index] = future.result()
            except Exception as exc:
                failed_task = deepcopy(tasks[index])
                failed_task["status"] = RESOURCE_TASK_STATUS_FAILED
                failed_task["result"] = {
                    "success": False,
                    "resources": [],
                    "tool_status_events": [],
                    "error_code": "resource_task_failed",
                    "error_message": _safe_text(exc),
                }
                failed_task["error_code"] = "resource_task_failed"
                failed_task["error_message"] = _safe_text(exc)
                ordered_results[index] = failed_task

    completed_tasks = [task for task in ordered_results if isinstance(task, dict)]
    return aggregate_resource_generation_results(completed_tasks)


def aggregate_resource_generation_results(resource_tasks: list[dict]) -> dict:
    resources: list[dict] = []
    resource_results: dict[str, dict] = {}
    failed_resource_types: list[str] = []
    tool_status_events: list[dict] = []
    warnings: list[str] = []

    for task in resource_tasks:
        resource_type = _safe_text(task.get("resource_type"))
        result = _safe_dict(task.get("result"))
        result_resources = _normalize_resources(result)
        resources.extend(result_resources)
        tool_status_events.extend(_safe_list(result.get("tool_status_events")))
        warnings.extend(_safe_list(result.get("warnings")))
        resource_results[resource_type] = result
        if task.get("status") != RESOURCE_TASK_STATUS_SUCCEEDED:
            failed_resource_types.append(resource_type)

    success_count = len(resource_tasks) - len(failed_resource_types)
    if success_count == len(resource_tasks) and resource_tasks:
        overall_status = RESOURCE_GENERATION_OVERALL_SUCCEEDED
        success = True
    elif success_count > 0:
        overall_status = RESOURCE_GENERATION_OVERALL_PARTIAL_SUCCESS
        success = True
    else:
        overall_status = RESOURCE_GENERATION_OVERALL_FAILED
        success = False

    return {
        "success": success,
        "overall_status": overall_status,
        "resources": resources,
        "resource_count": len(resources),
        "resource_results": resource_results,
        "resource_tasks": resource_tasks,
        "failed_resource_types": failed_resource_types,
        "tool_status_events": tool_status_events,
        "warnings": _unique_texts(warnings),
        "error_code": "" if success else "resource_generation_failed",
        "error_message": "" if success else "all resource generation tasks failed",
    }


def process_resource_generation_request(state: Dict[str, Any], request_payload: dict) -> dict:
    execution_payload = deepcopy(_safe_dict(request_payload))
    status_callback = execution_payload.pop("status_callback", None)
    resource_tasks = plan_resource_type_tasks(execution_payload)
    state["resource_type_tasks"] = deepcopy(resource_tasks)
    execution_tasks = deepcopy(resource_tasks)
    if callable(status_callback):
        for task in execution_tasks:
            request = task.get("request")
            if isinstance(request, dict):
                request["status_callback"] = status_callback
    generation_result = run_resource_type_tasks(state, execution_tasks)
    if isinstance(generation_result, dict):
        safe_tasks = []
        for task in _safe_list(generation_result.get("resource_tasks")):
            if not isinstance(task, dict):
                continue
            safe_task = deepcopy(task)
            request = safe_task.get("request")
            if isinstance(request, dict):
                request.pop("status_callback", None)
            safe_tasks.append(safe_task)
        generation_result["resource_tasks"] = safe_tasks
    state["resource_type_tasks"] = deepcopy(_safe_list(generation_result.get("resource_tasks")))
    if isinstance(generation_result, dict):
        _extend_status_events(state, generation_result)
    return generation_result


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
            state=state,
            next_task={},
            resources=[],
            error_code="no_next_task",
            error_message="no current learning task to generate resources for",
        )

    state["next_task"] = next_task
    resource_strategy = build_current_step_resource_strategy(state)
    state["resource_strategy"] = resource_strategy
    request_payload = _build_resource_request(state, next_task, resource_strategy)
    request_payload["run_id"] = state.get("run_id") or ""
    execution_payload = deepcopy(request_payload)
    execution_payload["status_callback"] = state.get("status_callback")
    generation_result = process_resource_generation_request(state, execution_payload)
    resources = _normalize_resources(_safe_dict(generation_result))
    state["resource_generation_request"] = request_payload
    state["resource_generation_result"] = generation_result
    result = _tool_result(
        TOOL_GENERATE_CURRENT_STEP_RESOURCE,
        bool(_safe_dict(generation_result).get("success", True)),
        state=state,
        next_task=next_task,
        resource_strategy=resource_strategy,
        request=request_payload,
        generation_result=generation_result,
        resources=resources,
        resource_tasks=_safe_list(_safe_dict(generation_result).get("resource_tasks")),
        resource_results=_safe_dict(_safe_dict(generation_result).get("resource_results")),
        failed_resource_types=_safe_list(_safe_dict(generation_result).get("failed_resource_types")),
        overall_status=_safe_text(_safe_dict(generation_result).get("overall_status")),
        suggested_next_action=ACTION_RECORD_LEARNING_FEEDBACK,
        error_code=_safe_text(_safe_dict(generation_result).get("error_code")),
        error_message=_safe_text(_safe_dict(generation_result).get("error_message")),
    )
    _notify_buddy_resource_ready_from_tool(state, result)
    return result


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
            "wrong_knowledge_items": _unique_texts(_list_from_any(payload.get("wrong_knowledge_items"))),
            "answer_record_count": len(_safe_list(payload.get("answer_records"))),
            "student_feedback": _safe_dict(payload.get("student_feedback")),
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
            state=state,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )
    plan = _safe_dict(state.get("active_plan") or prt.get_active_learning_plan(user_id, syllabus_id))
    if not plan:
        return _tool_result(
            tool_name,
            False,
            state=state,
            error_code="no_active_plan",
            error_message="no active learning plan",
        )
    step_id = _safe_text(payload.get("step_id")) or _safe_text(_safe_dict(state.get("next_task")).get("step_id"))
    step = _find_step(plan, step_id) if step_id else _find_next_step(plan)
    if not step:
        return _tool_result(
            tool_name,
            False,
            state=state,
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
    # Auto-complete the plan when all steps are finished
    plan_completed = False
    if not activated_step and not next_task and final_plan.get("plan_id"):
        try:
            prt.complete_learning_plan(user_id, str(final_plan["plan_id"]), syllabus_id=syllabus_id)
            plan_completed = True
            final_plan["status"] = prt.LEARNING_PLAN_STATUS_COMPLETED
        except Exception:
            pass
    state["active_plan"] = final_plan if not plan_completed else {}
    state["next_task"] = {} if plan_completed else next_task
    study_graph_sync = _safe_dict(update.get("study_graph_sync"))
    if status == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED:
        study_graph_sync = {"attempted": False, "success": True, "warning": "skipped step is not synced"}
    return _tool_result(
        tool_name,
        True,
        state=state,
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


def tool_abandon_learning_plan(state: Dict[str, Any]) -> dict:
    _append_trace(state, TOOL_ABANDON_LEARNING_PLAN)
    payload = _safe_dict(state.get("payload"))
    user_id = _positive_int(payload.get("user_id"))
    syllabus_id = _positive_int(payload.get("syllabus_id"))
    if not user_id:
        return _tool_result(
            TOOL_ABANDON_LEARNING_PLAN,
            False,
            state=state,
            error_code="missing_user_id",
            error_message="user_id must be a positive integer",
        )
    total_context = _safe_dict(state.get("total_context"))
    active_plan = _safe_dict(total_context.get("active_plan"))
    plan_id = str(active_plan.get("plan_id") or "")
    if not plan_id:
        return _tool_result(
            TOOL_ABANDON_LEARNING_PLAN,
            False,
            state=state,
            error_code="no_active_plan",
            error_message="no active learning plan to abandon",
        )
    reason = _safe_text(payload.get("reason") or payload.get("message") or "student_request")
    result = prt.abandon_learning_plan(user_id, plan_id, syllabus_id=syllabus_id, reason=reason)
    state["active_plan"] = {}
    state["next_task"] = {}
    return _tool_result(
        TOOL_ABANDON_LEARNING_PLAN,
        bool(result.get("success")),
        state=state,
        plan_id=plan_id,
        status=result.get("status"),
        reason=reason,
    )


def deterministic_run_total_agent(payload: Dict[str, Any]) -> dict:
    payload = payload or {}
    state: Dict[str, Any] = {
        "payload": payload,
        "tool_trace": [],
        "tool_status_events": [],
        "run_id": f"total_agent_run_{uuid4().hex[:12]}",
        "status_callback": payload.get("status_callback") if isinstance(payload, dict) else None,
    }
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
                retry_state = {
                    "payload": retry_payload,
                    "tool_trace": state["tool_trace"],
                    "tool_status_events": state.setdefault("tool_status_events", []),
                    "run_id": state.get("run_id"),
                    "status_callback": state.get("status_callback"),
                }
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
        guidance = build_learning_feedback_guidance(payload, feedback, next_task)
        final_result["learning_guidance"] = guidance
        final_result["reply"] = guidance.get("reply") or ""
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
    elif intent == INTENT_ANSWER_LEARNING_QUESTION:
        evidence = retrieve_learning_evidence(state)
        answer = answer_learning_question(state)
        final_result["retrieve_learning_evidence"] = evidence
        final_result["answer_learning_question"] = answer
        success = bool(answer.get("success"))
        suggested_next_action = answer.get("suggested_next_action") or ACTION_OFFER_PRACTICE_OR_RESOURCE
        error_code = answer.get("error_code") or ""
        error_message = answer.get("error_message") or ""
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
    "answer_learning_question",
    "apply_learning_effect_signal",
    "build_concept_explanation_answer",
    "build_current_step_resource_strategy",
    "build_learning_feedback_guidance",
    "build_exercise_help_answer",
    "build_learning_strategy_answer",
    "build_session_context",
    "build_total_agent_result",
    "classify_learning_question",
    "decide_resource_reuse",
    "deterministic_run_total_agent",
    "filter_relevant_weak_points",
    "find_personal_resources",
    "get_study_graph_features",
    "get_course_learning_tree_summary",
    "combine_global_and_personal_learning_signals",
    "load_profile_summary",
    "normalize_profile_summary",
    "normalize_study_graph_state",
    "normalize_answer_payload",
    "plan_resource_type_tasks",
    "process_resource_generation_request",
    "retrieve_learning_evidence",
    "run_resource_type_tasks",
    "score_evidence_relevance",
    "tool_accept_learning_plan",
    "tool_generate_current_step_resource",
    "tool_get_next_learning_task",
    "tool_infer_user_intent",
    "tool_load_total_context",
    "tool_normalize_learning_goal_for_recommendation",
    "tool_record_learning_feedback",
    "tool_run_learning_recommendation",
    "tool_skip_current_step",
    "tool_abandon_learning_plan",
]
