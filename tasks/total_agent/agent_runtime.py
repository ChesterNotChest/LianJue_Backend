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
            "For record_learning_feedback, call record_learning_feedback then get_next_learning_task. "
            "For skip_current_step, call skip_current_step then get_next_learning_task. "
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
    result: dict[str, Any] = {
        "intent": state.get("intent_result") or {},
        "terminal_tool": terminal,
    }
    error_code = str(terminal.get("error_code") or "")
    error_message = str(terminal.get("error_message") or "")

    if terminal_tool == TOOL_RUN_LEARNING_RECOMMENDATION:
        result["recommendation"] = terminal
        suggested = terminal.get("suggested_next_action") or ACTION_WAIT_USER_ACCEPTANCE
    elif terminal_tool == TOOL_NORMALIZE_LEARNING_GOAL:
        result["goal_normalization"] = terminal
        suggested = terminal.get("suggested_next_action") or ACTION_ASK_GOAL_CLARIFICATION
    elif terminal_tool == TOOL_ACCEPT_LEARNING_PLAN:
        result["accept_learning_plan"] = terminal
        suggested = terminal.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
    elif terminal_tool == TOOL_GENERATE_CURRENT_STEP_RESOURCE:
        result["resource_generation"] = terminal
        suggested = terminal.get("suggested_next_action") or ACTION_RECORD_LEARNING_FEEDBACK
    elif terminal_tool == TOOL_RECORD_LEARNING_FEEDBACK:
        result["record_learning_feedback"] = terminal
        suggested = terminal.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE
    elif terminal_tool == TOOL_SKIP_CURRENT_STEP:
        result["skip_current_step"] = terminal
        suggested = terminal.get("suggested_next_action") or ACTION_GENERATE_CURRENT_STEP_RESOURCE

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
