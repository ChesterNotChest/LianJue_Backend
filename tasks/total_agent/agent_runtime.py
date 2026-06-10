from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from functools import lru_cache
from uuid import uuid4
from typing import Any, AsyncGenerator, Dict

from pydantic_ai import Agent, ModelRetry, RunContext

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


def build_total_agent_model():
    return build_openai_compatible_model(agent_name="total agent")


@lru_cache(maxsize=1)
def get_total_agent() -> Agent:
    agent = Agent(
        model=build_total_agent_model(),
        deps_type=TotalAgentDeps,
        system_prompt=(
            "You are a dedicated teacher helping a student learn. "
            "Before taking any action, briefly tell the student what you're about to do and why — be clear and encouraging. "
            "Always start by understanding their current learning context (load_total_context, infer_user_intent). "
            "When they want a learning path: recommend first (run_learning_recommendation), clarify their goal if needed (normalize_learning_goal_for_recommendation). "
            "When they accept a plan: confirm it (accept_learning_plan). "
            "When they want to continue learning: check what's next (get_next_learning_task) then prepare materials (generate_current_step_resource). "
            "When they give feedback: record it (record_learning_feedback) then show the next step (get_next_learning_task). "
            "When they skip a step: skip it (skip_current_step) then show the next step (get_next_learning_task). "
            "When they ask a question: find relevant materials (retrieve_learning_evidence) then answer thoughtfully (answer_learning_question). "
            "When class-wide context might help: check the course overview (get_course_learning_tree_summary). "
            "Never make up learning plans, paths, resources, or study data — always use the tools."
        ),
        name="total_agent",
        description="Tool-calling agent for multi-turn learning process scheduling",
        retries=2,
        defer_model_check=True,
    )

    _TERMINAL = {
        TOOL_RUN_LEARNING_RECOMMENDATION, TOOL_ACCEPT_LEARNING_PLAN,
        TOOL_NORMALIZE_LEARNING_GOAL, TOOL_GENERATE_CURRENT_STEP_RESOURCE,
        TOOL_RECORD_LEARNING_FEEDBACK, TOOL_SKIP_CURRENT_STEP,
        TOOL_ANSWER_LEARNING_QUESTION,
    }

    def _remember_terminal(ctx: RunContext[TotalAgentDeps], tool_name: str, result: dict) -> dict:
        if tool_name in _TERMINAL:
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
    def generate_current_step_resource(ctx: RunContext[TotalAgentDeps]) -> dict:
        if ctx.deps.state.get("intent") != INTENT_GENERATE_CURRENT_STEP_RESOURCE:
            raise ModelRetry(
                "generate_current_step_resource is only allowed when inferred intent is "
                "generate_current_step_resource. For feedback or skip turns, return after recording "
                "the update and reading get_next_learning_task."
            )
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

    return build_total_agent_result(
        state,
        success=success,
        intent=intent,
        result=result,
        suggested_next_action=suggested,
        error_code=error_code,
        error_message=error_message,
    )


def run_total_agent(payload: Dict[str, Any], *, use_llm: bool = False, stream: bool = False):
    """运行总 agent（统一入口）。

    Args:
        payload: 总 agent 输入。
        use_llm: True 时走 LLM Agent；False 时确定性执行。
        stream: True 时返回 AsyncGenerator[dict, None]（仅 use_llm=True 时生效）。

    Returns:
        dict（非流式）或 AsyncGenerator[dict, None]（流式）。
    """
    if use_llm:
        return run_total_agent_agent(payload, stream=stream)
    return deterministic_run_total_agent(payload)


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


async def _stream_total_agent_agent(payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """流式运行总 agent，逐事件 yield。

    Yields events of types: text_delta, text_start, tool_call, tool_start,
    tool_end, tool_status, final.
    """
    payload = payload or {}
    status_queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    # ── status_callback：桥接同步 emit_status_event → 异步队列 ──
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

    async with agent.iter(user_prompt, deps=deps) as run:
        async for node in run:
            # 排出上一轮工具执行期间积压的 tool_status 事件
            while not status_queue.empty():
                try:
                    yield status_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            if not hasattr(node, "stream"):
                continue

            node_type = type(node).__name__

            # ── ModelRequestNode：LLM 响应阶段 ──────────────────
            if node_type == "ModelRequestNode":
                text_started = False
                async with node.stream(run.ctx) as agent_stream:
                    # 文本：token 级流式（output_type 移除后可用）
                    if hasattr(agent_stream, "stream_text"):
                        async for text_delta in agent_stream.stream_text(delta=True):
                            if text_delta:
                                if not text_started:
                                    text_started = True
                                    yield {"type": STREAM_EVENT_TEXT_START, "data": {"content": text_delta}, "timestamp": _ts()}
                                else:
                                    yield {"type": STREAM_EVENT_TEXT_DELTA, "data": {"content_delta": text_delta}, "timestamp": _ts()}

                    # tool_call
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

                    # tool_call（从 ModelResponse 提取）
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

            # ── CallToolsNode：工具执行阶段 ─────────────────────
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
                            yield {
                                "type": STREAM_EVENT_TOOL_END,
                                "data": {
                                    "tool_name": getattr(event, "tool_name", ""),
                                    "tool_call_id": getattr(event, "tool_call_id", ""),
                                    "result": _safe_result_data(getattr(event, "result", None)),
                                },
                                "timestamp": _ts(),
                            }

    # ── 最终排出 + 结果 ──
    while not status_queue.empty():
        try:
            yield status_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    model_output = None
    if hasattr(run, "result") and hasattr(run.result, "output"):
        raw = run.result.output
        if isinstance(raw, TotalAgentResult):
            model_output = raw

    final = _build_agent_final_result(state, model_output)
    yield {"type": STREAM_EVENT_FINAL, "data": final, "timestamp": _ts()}

    # ── 最终排出 + 结果 ──
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
    yield {"type": STREAM_EVENT_FINAL, "data": final, "timestamp": _ts()}


def run_total_agent_agent(payload: Dict[str, Any], *, stream: bool = False):
    """运行 LLM 版总 agent。

    Args:
        payload: 总 agent 输入 payload。
        stream: True 时返回 AsyncGenerator[dict, None]，False 时返回 dict（行为不变）。

    Returns:
        dict（非流式）或 AsyncGenerator[dict, None]（流式）。
    """
    if stream:
        return _stream_total_agent_agent(payload)

    # ── 原有同步逻辑不变 ──
    payload = payload or {}
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
    return _build_agent_final_result(state, output)
