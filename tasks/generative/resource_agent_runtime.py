"""pydantic-ai runtime for the resource generation agent."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel

from tasks.common.agent_model import build_openai_compatible_model
from tasks.common.status_events import get_status_events
from tasks.generative.resource_agent_contracts import (
    RESOURCE_AGENT_ERROR_TOOLCHAIN_INCOMPLETE,
    RESOURCE_GENERATION_TOOL_ORDER,
    ResourceGenerationAgentResult,
    ResourceGenerationDeps,
)
from tasks.generative.resource_agent_tools import (
    tool_generate_resource_payload,
    tool_persist_generated_resource,
    tool_read_generation_plan,
    tool_read_generation_request,
    tool_retrieve_generation_materials,
    tool_write_generation_draft,
)


def build_resource_generation_model() -> OpenAIModel:
    return build_openai_compatible_model(agent_name="resource generation agent")


@lru_cache(maxsize=1)
def build_resource_generation_agent() -> Agent:
    agent = Agent(
        model=build_resource_generation_model(),
        deps_type=ResourceGenerationDeps,
        output_type=ResourceGenerationAgentResult,
        system_prompt=(
            "You are the resource generation agent. You must complete the task by calling tools. "
            "Call tools in this order: read_generation_request, read_generation_plan, "
            "retrieve_generation_materials, write_generation_draft, generate_resource_payload, "
            "persist_generated_resource. Do not invent the final persisted resource yourself. "
            "The final resource must come from persist_generated_resource. Return only a JSON object "
            "matching the ResourceGenerationAgentResult schema. "
            "Before calling retrieve_generation_materials, compose a focused search_query: "
            "extract key concepts from the topic and learning goal, translate meta-instructions "
            "(e.g. '请生成文档') into concrete knowledge terms, and include both Chinese and "
            "English technical keywords. The search_query should be a single concise string "
            "(max 200 chars) that targets the specific knowledge needed for the resource."
        ),
        name="resource_generation_agent",
        description="Tool-calling agent for generating and persisting learning resources",
        retries=2,
        defer_model_check=True,
    )

    @agent.tool(sequential=True)
    def read_generation_request(ctx: RunContext[ResourceGenerationDeps]) -> dict:
        return tool_read_generation_request(ctx.deps.state)

    @agent.tool(sequential=True)
    def read_generation_plan(ctx: RunContext[ResourceGenerationDeps]) -> dict:
        return tool_read_generation_plan(ctx.deps.state)

    @agent.tool(sequential=True)
    def retrieve_generation_materials(ctx: RunContext[ResourceGenerationDeps], search_query: str = "") -> dict:
        return tool_retrieve_generation_materials(ctx.deps.state, search_query=search_query)

    @agent.tool(sequential=True)
    def write_generation_draft(ctx: RunContext[ResourceGenerationDeps]) -> dict:
        return tool_write_generation_draft(ctx.deps.state)

    @agent.tool(sequential=True)
    def generate_resource_payload(ctx: RunContext[ResourceGenerationDeps]) -> dict:
        return tool_generate_resource_payload(ctx.deps.state)

    @agent.tool(sequential=True)
    def persist_generated_resource(ctx: RunContext[ResourceGenerationDeps]) -> dict:
        return tool_persist_generated_resource(ctx.deps.state)

    @agent.output_validator
    def require_persisted_resource(
        ctx: RunContext[ResourceGenerationDeps],
        output: ResourceGenerationAgentResult,
    ) -> ResourceGenerationAgentResult:
        if not isinstance(ctx.deps.state.get("persisted_resource"), dict):
            raise ModelRetry(
                "You must call the full resource generation tool chain and persist_generated_resource "
                "before returning the final result."
            )
        return output

    return agent


def _build_resource_generation_user_prompt(state: Dict[str, Any]) -> str:
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    summary = {
        "resource_type": state.get("resource_type"),
        "user_id": request.get("user_id"),
        "syllabus_id": request.get("syllabus_id"),
        "topic": request.get("topic"),
        "question": request.get("question"),
        "knowledge_items": request.get("knowledge_items") or [],
        "weak_points": request.get("weak_points") or [],
        "tool_requirements": RESOURCE_GENERATION_TOOL_ORDER,
    }
    return json.dumps(summary, ensure_ascii=False)


def _result_from_state(state: Dict[str, Any], resource_type: str, fallback_error: str = "") -> ResourceGenerationAgentResult:
    resource = state.get("persisted_resource") if isinstance(state.get("persisted_resource"), dict) else None
    generated_content = state.get("generated_content") if isinstance(state.get("generated_content"), dict) else None
    planning_bundle = state.get("planning_bundle") if isinstance(state.get("planning_bundle"), dict) else None
    tool_trace = state.get("tool_trace") if isinstance(state.get("tool_trace"), list) else []
    tool_status_events = get_status_events(state)
    success = bool(resource and resource.get("success") is True)
    return ResourceGenerationAgentResult(
        success=success,
        resource_type=resource_type,
        resource=resource,
        generated_content=generated_content,
        planning_bundle=planning_bundle,
        tool_trace=tool_trace[:],
        tool_status_events=tool_status_events,
        error_message="" if success else (fallback_error or state.get("persist_error") or state.get("generation_error") or ""),
        error_code="" if success else RESOURCE_AGENT_ERROR_TOOLCHAIN_INCOMPLETE,
    )


def run_single_resource_generation_agent(
    request_payload: dict,
    resource_type: str,
    *,
    generation_tool: Any = None,
    planning_agent: Any = None,
    status_callback: Any = None,
) -> ResourceGenerationAgentResult:
    from tasks.generative.resource_generation_agent import LLMResourceGenerationAgent, build_single_resource_payload

    single_payload = build_single_resource_payload(request_payload, resource_type)
    state: Dict[str, Any] = {
        "request": single_payload,
        "resource_type": resource_type,
        "planning_agent": planning_agent,
        "generation_tool": generation_tool or LLMResourceGenerationAgent(),
        "planning_bundle": None,
        "generated_content": None,
        "persisted_resource": None,
        "tool_trace": [],
        "tool_status_events": [],
        "run_id": request_payload.get("run_id") or "",
        "status_callback": status_callback or request_payload.get("status_callback"),
    }
    deps = ResourceGenerationDeps(state=state)
    agent = build_resource_generation_agent()
    try:
        result = agent.run_sync(_build_resource_generation_user_prompt(state), deps=deps)
    except Exception as exc:
        return _result_from_state(state, resource_type, fallback_error=str(exc))
    output = result.output
    state_result = _result_from_state(state, resource_type)
    if isinstance(output, ResourceGenerationAgentResult):
        output.success = state_result.success
        output.resource_type = resource_type
        output.resource = state_result.resource
        output.generated_content = state_result.generated_content
        output.planning_bundle = state_result.planning_bundle
        output.tool_trace = state_result.tool_trace
        output.tool_status_events = state_result.tool_status_events
        output.error_message = state_result.error_message
        output.error_code = state_result.error_code
        return output
    return state_result
