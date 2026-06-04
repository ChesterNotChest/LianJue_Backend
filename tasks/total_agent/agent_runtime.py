from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict

from pydantic_ai import Agent, ModelRetry, RunContext

from tasks.common.agent_model import build_openai_compatible_model
from tasks.total_agent.agent_contracts import (
    ACTION_ASK_GOAL_CLARIFICATION,
    ACTION_GENERATE_CURRENT_STEP_RESOURCE,
    ACTION_RECORD_LEARNING_FEEDBACK,
    ACTION_WAIT_USER_ACCEPTANCE,
    INTENT_ACCEPT_RECOMMENDATION,
    INTENT_GENERATE_CURRENT_STEP_RESOURCE,
    INTENT_RECORD_LEARNING_FEEDBACK,
    INTENT_RECOMMEND_LEARNING_PATH,
    INTENT_SKIP_CURRENT_STEP,
    TOOL_ACCEPT_LEARNING_PLAN,
    TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    TOOL_GET_NEXT_LEARNING_TASK,
    TOOL_INFER_USER_INTENT,
    TOOL_LOAD_TOTAL_CONTEXT,
    TOOL_NORMALIZE_LEARNING_GOAL,
    TOOL_RECORD_LEARNING_FEEDBACK,
    TOOL_RUN_LEARNING_RECOMMENDATION,
    TOOL_SKIP_CURRENT_STEP,
    TOTAL_AGENT_TOOL_ORDER,
    TotalAgentDeps,
    TotalAgentResult,
)
from tasks.total_agent.agent_tools import (
    build_total_agent_result,
    deterministic_run_total_agent,
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


TERMINAL_TOTAL_AGENT_TOOLS = {
    TOOL_RUN_LEARNING_RECOMMENDATION,
    TOOL_ACCEPT_LEARNING_PLAN,
    TOOL_NORMALIZE_LEARNING_GOAL,
    TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    TOOL_RECORD_LEARNING_FEEDBACK,
    TOOL_SKIP_CURRENT_STEP,
}


def build_total_agent_model():
    return build_openai_compatible_model(agent_name="total agent")


@lru_cache(maxsize=1)
def get_total_agent() -> Agent:
    agent = Agent(
        model=build_total_agent_model(),
        deps_type=TotalAgentDeps,
        output_type=TotalAgentResult,
        system_prompt=(
            "You are the Total Agent for a learning platform. "
            "You must use tools to decide the next action. "
            "Always call load_total_context first, then infer_user_intent. "
            "For recommend_learning_path, call run_learning_recommendation; if no best path, call "
            "normalize_learning_goal_for_recommendation. "
            "For accept_recommendation, call accept_learning_plan. "
            "For generate_current_step_resource, call get_next_learning_task then generate_current_step_resource. "
            "For record_learning_feedback, call record_learning_feedback then get_next_learning_task; do not generate resources in the same turn. "
            "For skip_current_step, call skip_current_step then get_next_learning_task; do not generate resources in the same turn. "
            "Do not invent learning plans, recommendation paths, resources, or study graph changes yourself. "
            "Return a JSON object matching TotalAgentResult."
        ),
        name="total_agent",
        description="Tool-calling agent for multi-turn learning process scheduling",
        retries=2,
        defer_model_check=True,
    )

    def _remember_terminal(ctx: RunContext[TotalAgentDeps], tool_name: str, result: dict) -> dict:
        if tool_name in TERMINAL_TOTAL_AGENT_TOOLS:
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
    def skip_current_step(ctx: RunContext[TotalAgentDeps]) -> dict:
        return _remember_terminal(ctx, TOOL_SKIP_CURRENT_STEP, tool_skip_current_step(ctx.deps.state))

    @agent.output_validator
    def require_total_agent_tools(
        ctx: RunContext[TotalAgentDeps],
        output: TotalAgentResult,
    ) -> TotalAgentResult:
        trace = list(ctx.deps.state.get("tool_trace") or [])
        if TOOL_LOAD_TOTAL_CONTEXT not in trace or TOOL_INFER_USER_INTENT not in trace:
            raise ModelRetry("You must call load_total_context and infer_user_intent before returning.")
        if not any(tool_name in trace for tool_name in TERMINAL_TOTAL_AGENT_TOOLS):
            raise ModelRetry("You must call an intent-specific terminal tool before returning.")
        return output

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

    return build_total_agent_result(
        state,
        success=success,
        intent=intent,
        result=result,
        suggested_next_action=suggested,
        error_code=error_code,
        error_message=error_message,
    )


def run_total_agent(payload: Dict[str, Any], *, use_llm: bool = False) -> dict:
    if use_llm:
        return run_total_agent_agent(payload)
    return deterministic_run_total_agent(payload)


def run_total_agent_agent(payload: Dict[str, Any]) -> dict:
    state = {
        "payload": payload or {},
        "tool_trace": [],
        "total_context": {},
        "intent": "",
        "terminal_tool_result": None,
    }
    deps = TotalAgentDeps(state=state)
    agent = get_total_agent()
    result = agent.run_sync(build_total_agent_user_prompt(state), deps=deps)
    output = result.output if isinstance(result.output, TotalAgentResult) else None
    return _build_agent_final_result(state, output)
