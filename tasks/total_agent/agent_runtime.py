from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from uuid import uuid4
from typing import Any, AsyncGenerator, Dict

from pydantic_ai import Agent, ModelRetry, RunContext

try:
    from pydantic_ai.messages import FunctionToolResultEvent as _FunctionToolResultEvent

    if "result" not in getattr(_FunctionToolResultEvent, "model_fields", {}):
        _event_init = _FunctionToolResultEvent.__init__

        def _compat_function_tool_result_event_init(self, *args, **kwargs):
            result = kwargs.pop("result", None)
            if result is not None:
                return _event_init(self, result, *args, **kwargs)
            return _event_init(self, *args, **kwargs)

        _FunctionToolResultEvent.__init__ = _compat_function_tool_result_event_init
except Exception:
    pass

from tasks.common.agent_model import build_openai_compatible_model
from tasks.total_agent.agent_contracts import (
    ACTION_ASK_GOAL_CLARIFICATION,
    ACTION_GENERATE_CURRENT_STEP_RESOURCE,
    ACTION_OFFER_PRACTICE_OR_RESOURCE,
    ACTION_RECORD_LEARNING_FEEDBACK,
    ACTION_WAIT_USER_ACCEPTANCE,
    INTENT_ACCEPT_RECOMMENDATION,
    INTENT_ANSWER_LEARNING_QUESTION,
    INTENT_GENERATE_CURRENT_STEP_RESOURCE,
    INTENT_RECORD_LEARNING_FEEDBACK,
    INTENT_RECOMMEND_LEARNING_PATH,
    INTENT_SKIP_CURRENT_STEP,
    STREAM_EVENT_FINAL,
    STREAM_EVENT_TEXT_DELTA,
    STREAM_EVENT_TEXT_START,
    STREAM_EVENT_TOOL_CALL,
    STREAM_EVENT_TOOL_END,
    STREAM_EVENT_TOOL_START,
    STREAM_EVENT_TOOL_STATUS,
    TOOL_ACCEPT_LEARNING_PLAN,
    TOOL_ANSWER_LEARNING_QUESTION,
    TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    TOOL_GET_COURSE_LEARNING_TREE_SUMMARY,
    TOOL_GET_NEXT_LEARNING_TASK,
    TOOL_NORMALIZE_LEARNING_GOAL,
    TOOL_RECORD_LEARNING_FEEDBACK,
    TOOL_RETRIEVE_LEARNING_EVIDENCE,
    TOOL_RUN_LEARNING_RECOMMENDATION,
    TOOL_SKIP_CURRENT_STEP,
    TOTAL_AGENT_TOOL_ORDER,
    TotalAgentDeps,
    TotalAgentResult,
)
from tasks.total_agent.agent_tools import (
    answer_learning_question as tool_answer_learning_question,
    build_learning_feedback_guidance,
    build_total_agent_result,
    deterministic_run_total_agent,
    get_course_learning_tree_summary as tool_get_course_learning_tree_summary,
    retrieve_learning_evidence as tool_retrieve_learning_evidence,
    tool_accept_learning_plan,
    tool_generate_current_step_resource,
    tool_get_next_learning_task,
    tool_infer_user_intent,
    tool_load_total_context,
    tool_normalize_learning_goal_for_recommendation,
    tool_record_learning_feedback,
    tool_run_learning_recommendation,
    tool_skip_current_step,
)

logger = logging.getLogger(__name__)

CHAT_TERMINAL_TOOLS = {
    TOOL_RUN_LEARNING_RECOMMENDATION,
    TOOL_ACCEPT_LEARNING_PLAN,
    TOOL_NORMALIZE_LEARNING_GOAL,
    TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    TOOL_RECORD_LEARNING_FEEDBACK,
    TOOL_SKIP_CURRENT_STEP,
    TOOL_ANSWER_LEARNING_QUESTION,
}


def build_total_agent_model():
    return build_openai_compatible_model(agent_name="total agent")


@lru_cache(maxsize=1)
def get_total_agent() -> Agent:
    agent = Agent(
        model=build_total_agent_model(),
        deps_type=TotalAgentDeps,
        system_prompt=(
            "You are a dedicated teacher helping a student learn. "
            "Before taking any action, briefly tell the student what you're about to do and why - be clear and encouraging. "
            "Always start by understanding their current learning context (load_total_context, infer_user_intent). "
            "When they want a learning path: recommend first (run_learning_recommendation), clarify their goal if needed (normalize_learning_goal_for_recommendation). "
            "When they accept a plan: confirm it (accept_learning_plan). "
            "When they want to continue learning: check what's next (get_next_learning_task) then prepare materials (generate_current_step_resource). "
            "When they give feedback: record it (record_learning_feedback) then show the next step (get_next_learning_task). "
            "When a student's question or reasoning demonstrates knowledge of a topic, note it as an implicit learning signal and include that topic in record_learning_feedback. "
            "When they skip a step: skip it (skip_current_step) then show the next step (get_next_learning_task). "
            "When they ask a question: find relevant materials (retrieve_learning_evidence) then answer thoughtfully (answer_learning_question). "
            "When class-wide context might help: check the course overview (get_course_learning_tree_summary). "
            "IMPORTANT: When the student explicitly asks you to generate a specific resource type (PPT, document, quiz, mindmap, coding practice), just do it. Do NOT ask for confirmation or offer multiple plans. Call generate_current_step_resource immediately after load_total_context and infer_user_intent. "
            "When calling generate_current_step_resource, you MUST pass the resource_types parameter as a list. Available types: [\"ppt\", \"documents\", \"quiz\", \"mindmap\", \"coding_practice\"]. "
            "If the student asks for multiple types (e.g. '给我生成PPT和文档'), pass ALL requested types in the list and the system will generate them in parallel. "
            "If the student does not specify a type, you may omit resource_types and the system will choose based on their profile. "
            "Never make up learning plans, paths, resources, or study data - always use the tools."
        ),
        name="total_agent",
        description="Tool-calling agent for multi-turn learning process scheduling",
        retries=2,
        defer_model_check=True,
    )

    def _remember_terminal(ctx: RunContext[TotalAgentDeps], tool_name: str, result: dict) -> dict:
        if tool_name in CHAT_TERMINAL_TOOLS:
            ctx.deps.state["terminal_tool_result"] = result
        return result

    @agent.tool(sequential=True)
    def load_total_context(ctx: RunContext[TotalAgentDeps]) -> dict:
        return tool_load_total_context(ctx.deps.state)

    @agent.tool(sequential=True)
    def infer_user_intent(ctx: RunContext[TotalAgentDeps]) -> dict:
        return tool_infer_user_intent(ctx.deps.state)

    @agent.tool(sequential=True)
    def run_learning_recommendation(ctx: RunContext[TotalAgentDeps]) -> dict:
        return _remember_terminal(ctx, TOOL_RUN_LEARNING_RECOMMENDATION, tool_run_learning_recommendation(ctx.deps.state))

    @agent.tool(sequential=True)
    def normalize_learning_goal_for_recommendation(ctx: RunContext[TotalAgentDeps]) -> dict:
        return _remember_terminal(ctx, TOOL_NORMALIZE_LEARNING_GOAL, tool_normalize_learning_goal_for_recommendation(ctx.deps.state))

    @agent.tool(sequential=True)
    def accept_learning_plan(ctx: RunContext[TotalAgentDeps]) -> dict:
        return _remember_terminal(ctx, TOOL_ACCEPT_LEARNING_PLAN, tool_accept_learning_plan(ctx.deps.state))

    @agent.tool(sequential=True)
    def get_next_learning_task(ctx: RunContext[TotalAgentDeps]) -> dict:
        return tool_get_next_learning_task(ctx.deps.state)

    @agent.tool(sequential=True)
    def get_course_learning_tree_summary(ctx: RunContext[TotalAgentDeps]) -> dict:
        payload = ctx.deps.state.get("payload") if isinstance(ctx.deps.state.get("payload"), dict) else {}
        summary_payload = payload.get("course_tree_summary_payload") if isinstance(payload.get("course_tree_summary_payload"), dict) else {}
        if not summary_payload:
            summary_payload = {
                "syllabus_id": payload.get("syllabus_id"),
                "class_id": payload.get("class_id"),
                "teacher_id": payload.get("teacher_id"),
                "focus_user_id": payload.get("user_id"),
                "user_ids": payload.get("course_user_ids") or payload.get("class_user_ids") or [],
            }
        result = tool_get_course_learning_tree_summary(summary_payload)
        ctx.deps.state["course_learning_tree_summary_result"] = result
        ctx.deps.state.setdefault("total_context", {})["course_learning_tree_summary"] = result
        trace = ctx.deps.state.setdefault("tool_trace", [])
        if isinstance(trace, list) and TOOL_GET_COURSE_LEARNING_TREE_SUMMARY not in trace:
            trace.append(TOOL_GET_COURSE_LEARNING_TREE_SUMMARY)
        return result

    @agent.tool(sequential=True)
    def generate_current_step_resource(
        ctx: RunContext[TotalAgentDeps],
        resource_types: list[str] = None,
    ) -> dict:
        if ctx.deps.state.get("intent") != INTENT_GENERATE_CURRENT_STEP_RESOURCE:
            raise ModelRetry(
                "generate_current_step_resource is only allowed when inferred intent is "
                "generate_current_step_resource. For feedback or skip turns, return after recording "
                "the update and reading get_next_learning_task."
            )
        if resource_types:
            payload = ctx.deps.state.setdefault("payload", {})
            payload["resource_types"] = list(resource_types)
        return _remember_terminal(ctx, TOOL_GENERATE_CURRENT_STEP_RESOURCE, tool_generate_current_step_resource(ctx.deps.state))

    @agent.tool(sequential=True)
    def record_learning_feedback(ctx: RunContext[TotalAgentDeps]) -> dict:
        return _remember_terminal(ctx, TOOL_RECORD_LEARNING_FEEDBACK, tool_record_learning_feedback(ctx.deps.state))

    @agent.tool(sequential=True)
    def retrieve_learning_evidence(ctx: RunContext[TotalAgentDeps]) -> dict:
        return tool_retrieve_learning_evidence(ctx.deps.state)

    @agent.tool(sequential=True)
    def answer_learning_question(ctx: RunContext[TotalAgentDeps]) -> dict:
        if ctx.deps.state.get("intent") != INTENT_ANSWER_LEARNING_QUESTION:
            raise ModelRetry("answer_learning_question is only allowed when inferred intent is answer_learning_question.")
        if TOOL_RETRIEVE_LEARNING_EVIDENCE not in list(ctx.deps.state.get("tool_trace") or []):
            raise ModelRetry("Call retrieve_learning_evidence before answer_learning_question.")
        return _remember_terminal(ctx, TOOL_ANSWER_LEARNING_QUESTION, tool_answer_learning_question(ctx.deps.state))

    @agent.tool(sequential=True)
    def skip_current_step(ctx: RunContext[TotalAgentDeps]) -> dict:
        return _remember_terminal(ctx, TOOL_SKIP_CURRENT_STEP, tool_skip_current_step(ctx.deps.state))

    return agent


def build_total_agent_user_prompt(state: Dict[str, Any]) -> str:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    summary = {
        "user_id": payload.get("user_id"),
        "syllabus_id": payload.get("syllabus_id"),
        "message": payload.get("message") or payload.get("question") or "",
        "context": payload.get("context") or {},
        "intent_hint": payload.get("intent") or "",
        "resource_types": payload.get("resource_types") or [],
        "auto_accept": bool(payload.get("auto_accept")),
        "tool_order_by_intent": TOTAL_AGENT_TOOL_ORDER,
    }
    return json.dumps(summary, ensure_ascii=False)


def _build_agent_final_result(state: Dict[str, Any], model_output: TotalAgentResult | None = None) -> dict:
    intent = str(state.get("intent") or getattr(model_output, "intent", "") or "")
    terminal = state.get("terminal_tool_result") if isinstance(state.get("terminal_tool_result"), dict) else {}
    terminal_tool = terminal.get("tool") or ""

    suggested = getattr(model_output, "suggested_next_action", "") if model_output else ""
    success = bool(terminal.get("success", True))
    context_result = state.get("total_context") if isinstance(state.get("total_context"), dict) else {}
    result: dict[str, Any] = {
        "context": context_result,
        "intent": state.get("intent_result") or {},
        "terminal_tool": terminal,
    }
    error_code = str(terminal.get("error_code") or "")
    error_message = str(terminal.get("error_message") or "")
    recommendation_terminal = (
        terminal
        if terminal_tool == TOOL_RUN_LEARNING_RECOMMENDATION
        else state.get("recommendation_result")
        if isinstance(state.get("recommendation_result"), dict)
        else {}
    )
    normalization_terminal = (
        terminal
        if terminal_tool == TOOL_NORMALIZE_LEARNING_GOAL
        else state.get("goal_normalization_result")
        if isinstance(state.get("goal_normalization_result"), dict)
        else {}
    )
    accept_terminal = (
        terminal
        if terminal_tool == TOOL_ACCEPT_LEARNING_PLAN
        else state.get("accept_learning_plan_result")
        if isinstance(state.get("accept_learning_plan_result"), dict)
        else {}
    )
    resource_terminal = (
        terminal
        if terminal_tool == TOOL_GENERATE_CURRENT_STEP_RESOURCE
        else state.get("resource_generation_result")
        if isinstance(state.get("resource_generation_result"), dict)
        else {}
    )
    feedback_terminal = (
        terminal
        if terminal_tool == TOOL_RECORD_LEARNING_FEEDBACK
        else state.get("record_learning_feedback_result")
        if isinstance(state.get("record_learning_feedback_result"), dict)
        else {}
    )
    skip_terminal = (
        terminal
        if terminal_tool == TOOL_SKIP_CURRENT_STEP
        else state.get("skip_current_step_result")
        if isinstance(state.get("skip_current_step_result"), dict)
        else {}
    )
    answer_terminal = (
        terminal
        if terminal_tool == TOOL_ANSWER_LEARNING_QUESTION
        else state.get("answer_learning_question_result")
        if isinstance(state.get("answer_learning_question_result"), dict)
        else {}
    )
    evidence_terminal = state.get("learning_evidence_result") if isinstance(state.get("learning_evidence_result"), dict) else {}
    course_summary_terminal = (
        state.get("course_learning_tree_summary_result")
        if isinstance(state.get("course_learning_tree_summary_result"), dict)
        else {}
    )

    if course_summary_terminal:
        result["course_learning_tree_summary"] = course_summary_terminal
    if recommendation_terminal:
        result["recommendation"] = recommendation_terminal
    if normalization_terminal:
        result["goal_normalization"] = normalization_terminal
    if accept_terminal:
        result["accept_learning_plan"] = accept_terminal
    if resource_terminal:
        result["resource_generation"] = resource_terminal
    if feedback_terminal:
        result["record_learning_feedback"] = feedback_terminal
        payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
        next_task_result = state.get("next_task_result") if isinstance(state.get("next_task_result"), dict) else {}
        guidance = build_learning_feedback_guidance(payload, feedback_terminal, next_task_result)
        result["learning_guidance"] = guidance
        if guidance.get("reply"):
            result["reply"] = guidance["reply"]
    if skip_terminal:
        result["skip_current_step"] = skip_terminal
    if evidence_terminal:
        result["retrieve_learning_evidence"] = evidence_terminal
    if answer_terminal:
        result["answer_learning_question"] = answer_terminal

    if intent == INTENT_RECOMMEND_LEARNING_PATH or terminal_tool == TOOL_RUN_LEARNING_RECOMMENDATION:
        suggested = recommendation_terminal.get("suggested_next_action") or ACTION_WAIT_USER_ACCEPTANCE
    elif terminal_tool == TOOL_NORMALIZE_LEARNING_GOAL:
        suggested = normalization_terminal.get("suggested_next_action") or ACTION_ASK_GOAL_CLARIFICATION
    elif intent == INTENT_ACCEPT_RECOMMENDATION or terminal_tool == TOOL_ACCEPT_LEARNING_PLAN:
        suggested = accept_terminal.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
    elif intent == INTENT_GENERATE_CURRENT_STEP_RESOURCE or terminal_tool == TOOL_GENERATE_CURRENT_STEP_RESOURCE:
        suggested = resource_terminal.get("suggested_next_action") or ACTION_RECORD_LEARNING_FEEDBACK
    elif intent == INTENT_RECORD_LEARNING_FEEDBACK or terminal_tool == TOOL_RECORD_LEARNING_FEEDBACK:
        suggested = feedback_terminal.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
    elif intent == INTENT_SKIP_CURRENT_STEP or terminal_tool == TOOL_SKIP_CURRENT_STEP:
        suggested = skip_terminal.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
    elif intent == INTENT_ANSWER_LEARNING_QUESTION or terminal_tool == TOOL_ANSWER_LEARNING_QUESTION:
        suggested = answer_terminal.get("suggested_next_action") or ACTION_OFFER_PRACTICE_OR_RESOURCE

    final = build_total_agent_result(
        state,
        success=success,
        intent=intent,
        result=result,
        suggested_next_action=suggested,
        error_code=error_code,
        error_message=error_message,
    )

    if state.get("_study_buddy_event_sent") and state.get("_study_buddy_message"):
        final["buddy_message"] = str(state.get("_study_buddy_message") or "")
        final["buddy_event"] = {
            "event_type": str(state.get("_study_buddy_event_type") or ""),
            "payload": {},
        }
        return final

    # Trigger at most one study-buddy proactive message per total-agent turn.
    try:
        from tasks.study_buddy_task import notify_study_buddy_event, trigger_study_buddy
        payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
        uid = int(payload.get("user_id") or 0)
        sid = int(payload.get("syllabus_id") or 0) if payload.get("syllabus_id") else None
        if uid:
            logger.info(
                "[study_buddy.total_agent] hook_start user_id=%s syllabus_id=%s intent=%s terminal_tool=%s success=%s",
                uid,
                sid or 0,
                intent,
                terminal_tool,
                success,
            )
            selected_event = _select_buddy_event(
                terminal_tool=terminal_tool,
                recommendation_terminal=recommendation_terminal,
                accept_terminal=accept_terminal,
                resource_terminal=resource_terminal,
                feedback_terminal=feedback_terminal,
                skip_terminal=skip_terminal,
                answer_terminal=answer_terminal,
            )
            logger.info(
                "[study_buddy.total_agent] selected_event user_id=%s syllabus_id=%s event_type=%s payload=%s",
                uid,
                sid or 0,
                selected_event.get("event_type") if selected_event else "",
                selected_event.get("payload") if selected_event else {},
            )
            plan = selected_event.get("plan") if isinstance(selected_event.get("plan"), dict) else None
            if not plan and isinstance(result.get("accept_learning_plan"), dict):
                plan = result.get("accept_learning_plan", {}).get("plan")
            buddy_msg = None
            if selected_event:
                logger.info(
                    "[study_buddy.total_agent] notify_event_call user_id=%s syllabus_id=%s event_type=%s has_plan=%s",
                    uid,
                    sid or 0,
                    selected_event.get("event_type") or "",
                    isinstance(plan, dict),
                )
                buddy_msg = notify_study_buddy_event(
                    user_id=uid,
                    syllabus_id=sid or 0,
                    event_type=str(selected_event.get("event_type") or ""),
                    payload=selected_event.get("payload") if isinstance(selected_event.get("payload"), dict) else {},
                    plan=plan if isinstance(plan, dict) else None,
                )
                logger.info(
                    "[study_buddy.total_agent] notify_event_result user_id=%s syllabus_id=%s event_type=%s has_message=%s message_preview=%s",
                    uid,
                    sid or 0,
                    selected_event.get("event_type") or "",
                    bool(buddy_msg),
                    str(buddy_msg or "")[:120],
                )
            if not buddy_msg:
                logger.info(
                    "[study_buddy.total_agent] tree_fallback_call user_id=%s syllabus_id=%s has_plan=%s",
                    uid,
                    sid or 0,
                    isinstance(plan, dict),
                )
                buddy_msg = trigger_study_buddy(
                    user_id=uid,
                    syllabus_id=sid or 0,
                    plan=plan if isinstance(plan, dict) else None,
                )
                logger.info(
                    "[study_buddy.total_agent] tree_fallback_result user_id=%s syllabus_id=%s has_message=%s message_preview=%s",
                    uid,
                    sid or 0,
                    bool(buddy_msg),
                    str(buddy_msg or "")[:120],
                )
            if buddy_msg:
                final["buddy_message"] = buddy_msg
                if selected_event:
                    final["buddy_event"] = {
                        "event_type": selected_event.get("event_type") or "",
                        "payload": selected_event.get("payload") if isinstance(selected_event.get("payload"), dict) else {},
                    }
                logger.info(
                    "[study_buddy.total_agent] hook_done user_id=%s syllabus_id=%s has_message=true event_type=%s",
                    uid,
                    sid or 0,
                    selected_event.get("event_type") if selected_event else "",
                )
            else:
                logger.info("[study_buddy.total_agent] hook_done user_id=%s syllabus_id=%s has_message=false", uid, sid or 0)
    except Exception:
        logger.exception("[study_buddy.total_agent] hook_failed")
    return final


def _first_resource_summary(resource_terminal: dict) -> dict:
    resources = resource_terminal.get("resources") if isinstance(resource_terminal.get("resources"), list) else []
    if resources:
        item = resources[0] if isinstance(resources[0], dict) else {}
        return {
            "resource_id": item.get("resource_id") or "",
            "resource_type": item.get("resource_type") or "",
            "title": item.get("title") or "",
            "topic": item.get("topic") or "",
            "count": len(resources),
        }
    generation_result = resource_terminal.get("generation_result") if isinstance(resource_terminal.get("generation_result"), dict) else {}
    raw_resources = generation_result.get("resources") if isinstance(generation_result.get("resources"), list) else []
    item = raw_resources[0] if raw_resources and isinstance(raw_resources[0], dict) else {}
    return {
        "resource_id": item.get("resource_id") or "",
        "resource_type": item.get("resource_type") or "",
        "title": item.get("title") or "",
        "topic": item.get("topic") or "",
        "count": len(raw_resources),
    }


def _select_buddy_event(
    *,
    terminal_tool: str,
    recommendation_terminal: dict,
    accept_terminal: dict,
    resource_terminal: dict,
    feedback_terminal: dict,
    skip_terminal: dict,
    answer_terminal: dict,
) -> dict:
    events: list[tuple[int, dict]] = []
    if accept_terminal.get("accepted"):
        next_task = accept_terminal.get("next_task") if isinstance(accept_terminal.get("next_task"), dict) else {}
        metrics = accept_terminal.get("metrics") if isinstance(accept_terminal.get("metrics"), dict) else {}
        events.append((100, {
            "event_type": "plan_accepted",
            "payload": {
                "next_task_title": next_task.get("title") or next_task.get("topic") or "",
                "total_steps": metrics.get("total_steps"),
            },
            "plan": accept_terminal.get("plan") if isinstance(accept_terminal.get("plan"), dict) else None,
        }))
    if resource_terminal and resource_terminal.get("success", True):
        next_task = resource_terminal.get("next_task") if isinstance(resource_terminal.get("next_task"), dict) else {}
        events.append((90, {
            "event_type": "resource_ready",
            "payload": {
                "next_task_title": next_task.get("title") or next_task.get("topic") or "",
                "overall_status": resource_terminal.get("overall_status") or "",
                "resource": _first_resource_summary(resource_terminal),
            },
        }))
    if feedback_terminal and feedback_terminal.get("success", True):
        updated_step = feedback_terminal.get("updated_step") if isinstance(feedback_terminal.get("updated_step"), dict) else {}
        activated_step = feedback_terminal.get("activated_step") if isinstance(feedback_terminal.get("activated_step"), dict) else {}
        events.append((80, {
            "event_type": "learning_feedback_recorded",
            "payload": {
                "updated_step_title": updated_step.get("title") or "",
                "updated_step_status": updated_step.get("status") or "",
                "activated_step_title": activated_step.get("title") or "",
                "metrics": feedback_terminal.get("metrics") if isinstance(feedback_terminal.get("metrics"), dict) else {},
            },
        }))
    if skip_terminal and skip_terminal.get("success", True):
        next_task = skip_terminal.get("next_task") if isinstance(skip_terminal.get("next_task"), dict) else {}
        events.append((75, {
            "event_type": "step_skipped",
            "payload": {
                "next_task_title": next_task.get("title") or next_task.get("topic") or "",
                "metrics": skip_terminal.get("metrics") if isinstance(skip_terminal.get("metrics"), dict) else {},
            },
        }))
    if recommendation_terminal and recommendation_terminal.get("has_best_path"):
        recommendation = recommendation_terminal.get("recommendation") if isinstance(recommendation_terminal.get("recommendation"), dict) else {}
        best_path = recommendation.get("best_path") if isinstance(recommendation.get("best_path"), dict) else {}
        events.append((60, {
            "event_type": "recommendation_ready",
            "payload": {
                "recommendation_id": recommendation_terminal.get("recommendation_id") or recommendation.get("recommendation_id") or "",
                "path_title": best_path.get("title") or "",
                "path_length": len(best_path.get("path") or []) if isinstance(best_path.get("path"), list) else None,
            },
        }))
    if answer_terminal and terminal_tool == TOOL_ANSWER_LEARNING_QUESTION:
        answer = answer_terminal.get("answer") if isinstance(answer_terminal.get("answer"), dict) else {}
        events.append((40, {
            "event_type": "question_answered",
            "payload": {
                "question_type": answer_terminal.get("question_profile", {}).get("question_type")
                if isinstance(answer_terminal.get("question_profile"), dict)
                else "",
                "next_actions": answer.get("next_actions") if isinstance(answer.get("next_actions"), list) else [],
            },
        }))
    events.sort(key=lambda item: item[0], reverse=True)
    return events[0][1] if events else {}

# Chat history persistence (session-isolated, DB + file fallback)

def _now_ts():
    return int(datetime.now(timezone.utc).timestamp())


def _safe_log_text(value):
    try:
        return str(value)
    except Exception:
        return "<unprintable>"


def _chat_log(msg):
    try:
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'chat_debug.log'), 'a', encoding='utf-8') as f:
            f.write(f"{_now_ts()} {msg}\n")
    except Exception:
        pass


def _resolve_session_id(payload):
    sid = str(payload.get('session_id') or payload.get('sessionId') or '')
    return sid.strip()


def _chat_history_path(user_id, syllabus_id, session_id):
    history_dir = os.path.join(os.getcwd(), 'history')
    return os.path.join(history_dir, f'{syllabus_id}_{user_id}_{session_id}_chat.json')


def _load_chat_history_db(user_id, syllabus_id, session_id, max_turns=20):
    from schemas.agent_runtime_state import ChatTurn
    rows = (
        ChatTurn.query
        .filter_by(session_id=session_id)
        .order_by(ChatTurn.id.desc())
        .limit(max_turns)
        .all()
    )
    rows.reverse()
    return [{'role': r.role, 'content': r.content, 'timestamp': r.created_at} for r in rows]


def _load_chat_history_file(user_id, syllabus_id, session_id, max_turns=20):
    if not session_id:
        return []
    path = _chat_history_path(user_id, syllabus_id, session_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return [t for t in data if isinstance(t, dict)][-max_turns:]
    except Exception:
        return []
    return []


def _load_chat_history(user_id, syllabus_id, session_id, max_turns=20):
    if not session_id:
        return []
    try:
        return _load_chat_history_db(user_id, syllabus_id, session_id, max_turns)
    except Exception as exc:
        _chat_log(f"load_history DB FAIL {type(exc).__name__}: {_safe_log_text(exc)}; file fallback")
        try:
            from extensions import db
            db.session.rollback()
        except Exception:
            pass
        return _load_chat_history_file(user_id, syllabus_id, session_id, max_turns)


def _chat_title_from_message(message):
    text = str(message or '').strip()
    return (text[:40] + ('...' if len(text) > 40 else '')) if text else 'New chat'


def _get_chat_session_db(user_id, syllabus_id, session_id, now, title=None):
    from extensions import db
    from schemas.agent_runtime_state import ChatSession

    sess = ChatSession.query.get(session_id)
    if sess and sess.user_id != user_id:
        raise ValueError(
            f"chat session owner mismatch: session_id={session_id} "
            f"existing_user={sess.user_id} request_user={user_id}"
        )
    if not sess:
        sess = ChatSession(
            session_id=session_id,
            user_id=user_id,
            syllabus_id=syllabus_id,
            title=title or 'New chat',
            turn_count=0,
            created_at=now,
            updated_at=now,
        )
        db.session.add(sess)
    else:
        sess.syllabus_id = syllabus_id
        sess.updated_at = now
        if title and (not sess.title or sess.title == 'New chat'):
            sess.title = title
    return sess


def _append_chat_turn_file(user_id, syllabus_id, session_id, role, content):
    content = str(content or '')
    if not content or not session_id:
        return
    path = _chat_history_path(user_id, syllabus_id, session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    history = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                history = data
        except Exception:
            pass
    history.append({'role': role, 'content': content, 'timestamp': _now_ts()})
    history = history[-50:]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _append_chat_message_db(user_id, syllabus_id, session_id, role, content, metadata=None):
    from extensions import db
    from schemas.agent_runtime_state import ChatTurn

    content = str(content or '')
    if not content:
        return
    now = _now_ts()
    title = _chat_title_from_message(content) if role == 'user' else None
    sess = _get_chat_session_db(user_id, syllabus_id, session_id, now, title=title)
    metadata_json = None
    if metadata:
        metadata_json = json.dumps(metadata, ensure_ascii=False)
    db.session.add(ChatTurn(session_id=session_id, role=role, content=content, metadata_json=metadata_json, created_at=now))
    sess.turn_count = (sess.turn_count or 0) + 1
    sess.updated_at = now
    db.session.commit()


def _append_chat_message(user_id, syllabus_id, session_id, role, content, metadata=None):
    content = str(content or '')
    _chat_log(f"append_message role={role} ses={session_id} len={len(content)}")
    if not session_id or not content:
        _chat_log(f"append_message SKIP ses={bool(session_id)} content={bool(content)}")
        return
    try:
        _append_chat_message_db(user_id, syllabus_id, session_id, role, content, metadata=metadata)
        _chat_log("append_message DB OK")
    except Exception as exc:
        _chat_log(f"append_message DB FAIL {type(exc).__name__}: {_safe_log_text(exc)}; file fallback")
        try:
            from extensions import db
            db.session.rollback()
        except Exception:
            pass
        _append_chat_turn_file(user_id, syllabus_id, session_id, role, content)


def _persist_user_chat_turn(payload):
    if payload.get('_chat_user_turn_persisted'):
        return
    uid = payload.get('user_id')
    sid = payload.get('syllabus_id')
    session_id = _resolve_session_id(payload)
    if not uid or not sid or not session_id:
        _chat_log("persist_user_turn SKIP missing fields")
        return
    try:
        uid = int(uid)
        sid = int(sid)
    except (TypeError, ValueError):
        _chat_log("persist_user_turn SKIP invalid ids")
        return
    user_msg = str(payload.get('message') or payload.get('question') or '')
    if not user_msg:
        _chat_log("persist_user_turn SKIP empty message")
        return
    _append_chat_message(uid, sid, session_id, 'user', user_msg)
    payload['_chat_user_turn_persisted'] = True


def _ensure_session_created(payload):
    uid = payload.get('user_id')
    sid = payload.get('syllabus_id')
    session_id = _resolve_session_id(payload)
    _chat_log(f"ensure_session uid={uid} sid={sid} ses={session_id} msg={str(payload.get('message',''))[:30]}")
    if not uid or not sid or not session_id:
        _chat_log("ensure_session SKIP missing fields")
        return
    try:
        uid = int(uid)
        sid = int(sid)
    except (TypeError, ValueError):
        _chat_log("ensure_session SKIP invalid ids")
        return
    now = _now_ts()
    try:
        from flask import has_app_context
        if has_app_context():
            from extensions import db
            _get_chat_session_db(
                uid,
                sid,
                session_id,
                now,
                title=_chat_title_from_message(payload.get('message') or payload.get('question')),
            )
            db.session.commit()
            _chat_log("ensure_session DB OK")
    except Exception as exc:
        _chat_log(f"ensure_session DB FAIL {type(exc).__name__}: {_safe_log_text(exc)}")
        try:
            from extensions import db
            db.session.rollback()
        except Exception:
            pass


def _inject_chat_history(payload):
    _ensure_session_created(payload)
    uid = payload.get('user_id')
    sid = payload.get('syllabus_id')
    session_id = _resolve_session_id(payload)
    if not uid or not sid or not session_id:
        return payload
    try:
        uid = int(uid)
        sid = int(sid)
    except (TypeError, ValueError):
        return payload
    disk_history = _load_chat_history(uid, sid, session_id)
    context = payload.get('context')
    if not isinstance(context, dict):
        context = {}
        payload['context'] = context
    frontend_history = context.get('conversation_history') or context.get('session_history') or []
    if not isinstance(frontend_history, list):
        frontend_history = []
    disk_set = {json.dumps(t, ensure_ascii=False, sort_keys=True) for t in disk_history}
    merged = list(disk_history)
    for turn in frontend_history:
        if json.dumps(turn, ensure_ascii=False, sort_keys=True) not in disk_set:
            merged.append(turn)
    context['conversation_history'] = merged
    return payload


def _extract_agent_reply(final_result, state, terminal=None):
    terminal = terminal if isinstance(terminal, dict) else {}
    candidates = []
    if isinstance(final_result, dict):
        result = final_result.get('result') if isinstance(final_result.get('result'), dict) else {}
        candidates.extend([
            final_result.get('reply'),
            final_result.get('message'),
            final_result.get('summary'),
            result.get('reply'),
            result.get('message'),
            result.get('summary'),
        ])
        for key in (
            'answer_learning_question',
            'resource_generation',
            'record_learning_feedback',
            'skip_current_step',
            'accept_learning_plan',
            'goal_normalization',
            'recommendation',
            'next_task',
        ):
            value = result.get(key)
            if isinstance(value, dict):
                answer = value.get('answer')
                if isinstance(answer, dict):
                    candidates.extend([answer.get('text'), answer.get('content'), answer.get('message')])
                candidates.extend([value.get('reply'), value.get('message'), value.get('summary'), value.get('answer')])
    if isinstance(terminal, dict):
        answer = terminal.get('answer')
        if isinstance(answer, dict):
            candidates.extend([answer.get('text'), answer.get('content'), answer.get('message')])
        candidates.extend([terminal.get('reply'), terminal.get('message'), terminal.get('summary'), terminal.get('answer')])
    for value in candidates:
        if value:
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)[:2000]
            return str(value)
    if terminal:
        return json.dumps(terminal, ensure_ascii=False)[:2000]
    ctx = state.get('total_context') if isinstance(state.get('total_context'), dict) else {}
    for key in ('reply', 'message', 'summary'):
        if ctx.get(key):
            return str(ctx.get(key))
    return '(no reply)'


def _persist_agent_chat_turn(payload, state):
    if state.get('_chat_agent_turn_persisted'):
        _chat_log("persist_agent_turn SKIP already persisted")
        return
    _chat_log(f"persist_agent_turn uid={payload.get('user_id')} ses={payload.get('session_id')} terminal={bool(state.get('terminal_tool_result'))}")
    uid = payload.get('user_id')
    sid = payload.get('syllabus_id')
    session_id = _resolve_session_id(payload)
    if not uid or not sid or not session_id:
        _chat_log("persist_agent_turn SKIP missing fields")
        return
    try:
        uid = int(uid)
        sid = int(sid)
    except (TypeError, ValueError):
        _chat_log("persist_agent_turn SKIP invalid ids")
        return
    final_result = state.get('final_result') if isinstance(state.get('final_result'), dict) else {}
    terminal = state.get('terminal_tool_result') if isinstance(state.get('terminal_tool_result'), dict) else {}
    agent_reply = _extract_agent_reply(final_result, state, terminal)
    if not agent_reply or agent_reply == '(no reply)':
        _chat_log("persist_agent_turn SKIP empty reply")
        return
    _chat_log(f"persist_agent_turn len={len(agent_reply)}")
    _append_chat_message(uid, sid, session_id, 'agent', agent_reply)
    state['_chat_agent_turn_persisted'] = True


def _persist_final_agent_turn(payload, state, final):
    if isinstance(state, dict):
        state['final_result'] = final if isinstance(final, dict) else {}
    _persist_agent_chat_turn(payload, state)


def persist_streamed_agent_reply(payload, content, metadata=None):
    state = {
        'payload': payload or {},
        'terminal_tool_result': {'reply': str(content or '')},
        'total_context': {},
    }
    uid = (payload or {}).get('user_id')
    sid = (payload or {}).get('syllabus_id')
    session_id = _resolve_session_id(payload or {})
    try:
        from flask import has_app_context
        if has_app_context() and uid and sid and session_id:
            from extensions import db
            from schemas.agent_runtime_state import ChatTurn
            last = (
                ChatTurn.query.filter_by(session_id=session_id, role='agent')
                .order_by(ChatTurn.id.desc())
                .first()
            )
            if last and last.content == str(content or ''):
                if metadata:
                    last.metadata_json = json.dumps(metadata, ensure_ascii=False)
                    db.session.commit()
                    return
            if last and last.content != str(content or '') and metadata:
                last.content = str(content or '')
                last.metadata_json = json.dumps(metadata, ensure_ascii=False)
                db.session.commit()
                return
    except Exception:
        try:
            from extensions import db
            db.session.rollback()
        except Exception:
            pass
    uid = (payload or {}).get('user_id')
    sid = (payload or {}).get('syllabus_id')
    session_id = _resolve_session_id(payload or {})
    try:
        uid = int(uid)
        sid = int(sid)
    except (TypeError, ValueError):
        _persist_agent_chat_turn(payload or {}, state)
        return
    if uid and sid and session_id:
        _append_chat_message(uid, sid, session_id, 'agent', str(content or ''), metadata=metadata)
        return
    _persist_agent_chat_turn(payload or {}, state)


def run_total_agent(payload: Dict[str, Any], *, use_llm: bool = False, stream: bool = False):
    """Run Total Agent."""
    payload = payload or {}
    _chat_log(f"run_total_agent uid={payload.get('user_id')} ses={payload.get('session_id')}")
    _inject_chat_history(payload)
    _persist_user_chat_turn(payload)
    if use_llm:
        return run_total_agent_agent(payload, stream=stream)
    final = deterministic_run_total_agent(payload)
    state = {
        'payload': payload,
        'terminal_tool_result': {},
        'total_context': final.get('result', {}).get('context', {}) if isinstance(final, dict) else {},
        'final_result': final if isinstance(final, dict) else {},
    }
    _persist_final_agent_turn(payload, state, final)
    return final


def _ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _extract_event_part_type(event: Any) -> str:
    """Best-effort extraction of the part / delta type name from a pydantic_ai event."""
    for attr in ("part", "delta"):
        obj = getattr(event, attr, None)
        if obj is not None:
            return type(obj).__name__
    return ""


def _safe_args_dict(args: Any) -> Any:
    """Unwrap pydantic_ai argument wrappers (e.g. ToolCallArgs) to plain dict if possible."""
    if args is None:
        return None
    if isinstance(args, dict):
        return args
    if hasattr(args, "args_dict"):
        return args.args_dict
    if hasattr(args, "model_dump"):
        return args.model_dump()
    return str(args)


def _safe_result_data(result: Any) -> Any:
    """Unwrap pydantic_ai result wrappers to plain dict / scalar."""
    if result is None:
        return None
    if isinstance(result, (dict, list, str, int, float, bool)):
        return result
    if hasattr(result, "data"):
        return result.data
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return str(result)


def _safe_tool_result_event_data(event: Any) -> tuple[str, str, Any]:
    raw_result = getattr(event, "result", None)
    tool_name = getattr(event, "tool_name", "") or getattr(raw_result, "tool_name", "")
    tool_call_id = getattr(event, "tool_call_id", "") or getattr(raw_result, "tool_call_id", "")
    if hasattr(raw_result, "content"):
        result = _safe_result_data(getattr(raw_result, "content", None))
    else:
        result = _safe_result_data(raw_result)
    return str(tool_name or ""), str(tool_call_id or ""), result


async def _stream_total_agent_agent(payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream Total Agent events."""
    payload = payload or {}
    status_queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    def _status_callback(event: dict) -> None:
        try:
            status_queue.put_nowait(
                {"type": STREAM_EVENT_TOOL_STATUS, "data": event, "timestamp": _ts()}
            )
        except asyncio.QueueFull:
            pass

    state: Dict[str, Any] = {
        "payload": payload,
        "tool_trace": [],
        "tool_status_events": [],
        "run_id": f"total_agent_run_{uuid4().hex[:12]}",
        "status_callback": _status_callback,
        "total_context": {},
        "intent": "",
        "terminal_tool_result": None,
    }

    deps = TotalAgentDeps(state=state)
    agent = get_total_agent()
    user_prompt = build_total_agent_user_prompt(state)
    run = None

    _chat_log("GEN_START")
    async with agent.iter(user_prompt, deps=deps) as run:
        async for node in run:
            while not status_queue.empty():
                try:
                    yield status_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            if not hasattr(node, "stream"):
                continue

            node_type = type(node).__name__
            if node_type == "ModelRequestNode":
                text_started = False
                async with node.stream(run.ctx) as agent_stream:
                    if hasattr(agent_stream, "stream_text"):
                        async for text_delta in agent_stream.stream_text(delta=True):
                            if text_delta:
                                if not text_started:
                                    text_started = True
                                    yield {"type": STREAM_EVENT_TEXT_START, "data": {"content": text_delta}, "timestamp": _ts()}
                                else:
                                    yield {"type": STREAM_EVENT_TEXT_DELTA, "data": {"content_delta": text_delta}, "timestamp": _ts()}

                    async for event in agent_stream:
                        ek = getattr(event, "event_kind", "")
                        if ek == "part_start":
                            part = event.part
                            if getattr(part, "part_kind", "") == "tool-call":
                                yield {
                                    "type": STREAM_EVENT_TOOL_CALL,
                                    "data": {
                                        "tool_name": getattr(part, "tool_name", ""),
                                        "tool_call_id": getattr(part, "tool_call_id", ""),
                                        "args": _safe_args_dict(getattr(part, "args", None)),
                                    },
                                    "timestamp": _ts(),
                                }

                    response = getattr(agent_stream, "response", None)
                    if response is not None:
                        for tc in getattr(response, "tool_calls", None) or []:
                            yield {
                                "type": STREAM_EVENT_TOOL_CALL,
                                "data": {
                                    "tool_name": getattr(tc, "tool_name", ""),
                                    "tool_call_id": getattr(tc, "tool_call_id", ""),
                                    "args": _safe_args_dict(getattr(tc, "args", None)),
                                },
                                "timestamp": _ts(),
                            }

            elif node_type == "CallToolsNode":
                async with node.stream(run.ctx) as tool_stream:
                    async for event in tool_stream:
                        evt_type = type(event).__name__
                        if evt_type == "FunctionToolCallEvent":
                            yield {
                                "type": STREAM_EVENT_TOOL_START,
                                "data": {
                                    "tool_name": getattr(event, "tool_name", ""),
                                    "args": _safe_args_dict(getattr(event, "args", None)),
                                    "tool_call_id": getattr(event, "tool_call_id", ""),
                                },
                                "timestamp": _ts(),
                            }
                        elif evt_type == "FunctionToolResultEvent":
                            tool_name, tool_call_id, tool_result = _safe_tool_result_event_data(event)
                            if tool_name in CHAT_TERMINAL_TOOLS and isinstance(tool_result, dict):
                                state["terminal_tool_result"] = tool_result
                                _chat_log(f"STREAM_TERMINAL_TOOL_SAVE tool={tool_name}")
                                _persist_agent_chat_turn(payload, state)
                            yield {
                                "type": STREAM_EVENT_TOOL_END,
                                "data": {
                                    "tool_name": tool_name,
                                    "tool_call_id": tool_call_id,
                                    "result": tool_result,
                                },
                                "timestamp": _ts(),
                            }

            _chat_log("LOOP_BOTTOM")

    _chat_log("AFTER_LOOP_MARKER")
    while not status_queue.empty():
        try:
            yield status_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    model_output = None
    if run is not None and hasattr(run, "result") and hasattr(run.result, "output"):
        raw = run.result.output
        if isinstance(raw, TotalAgentResult):
            model_output = raw

    final = _build_agent_final_result(state, model_output)
    _chat_log("PRE_SAVE_1")
    _persist_final_agent_turn(payload, state, final)
    yield {"type": STREAM_EVENT_FINAL, "data": final, "timestamp": _ts()}


def run_total_agent_agent(payload: Dict[str, Any], *, stream: bool = False):
    """Run the LLM Total Agent."""
    payload = payload or {}
    _inject_chat_history(payload)
    _persist_user_chat_turn(payload)
    if stream:
        return _stream_total_agent_agent(payload)

    state = {
        "payload": payload,
        "tool_trace": [],
        "tool_status_events": [],
        "run_id": f"total_agent_run_{uuid4().hex[:12]}",
        "status_callback": payload.get("status_callback") if isinstance(payload, dict) else None,
        "total_context": {},
        "intent": "",
        "terminal_tool_result": None,
    }
    deps = TotalAgentDeps(state=state)
    agent = get_total_agent()
    result = agent.run_sync(build_total_agent_user_prompt(state), deps=deps)
    output = result.output if isinstance(result.output, TotalAgentResult) else None
    final = _build_agent_final_result(state, output)
    _persist_final_agent_turn(payload, state, final)
    return final
