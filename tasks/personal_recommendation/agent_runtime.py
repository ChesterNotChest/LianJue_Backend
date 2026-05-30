import json
from functools import lru_cache
from typing import Any, Dict

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel

from config import OPENAI_COMPAT_MODEL_CONFIGS
from tasks.common.agent_model import build_openai_compatible_model
from tasks.personal_recommendation.agent_contracts import (
    PersonalRecommendationDeps,
    PersonalRecommendationResult,
)
from tasks.personal_recommendation.agent_tools import (
    safe_text,
    tool_load_request_context,
    tool_run_recommendation_route,
    tool_search_recommendation_context,
)


PERSONAL_RECOMMENDATION_TOOL_ORDER = [
    "load_request_context",
    "search_recommendation_context",
    "run_recommendation_route",
]


def build_personal_recommendation_model() -> OpenAIModel:
    return build_openai_compatible_model(agent_name="personal recommendation agent")


@lru_cache(maxsize=1)
def get_personal_recommendation_agent() -> Agent:
    agent = Agent(
        model=build_personal_recommendation_model(),
        deps_type=PersonalRecommendationDeps,
        output_type=PersonalRecommendationResult,
        system_prompt=(
            "You are the personal learning path recommendation agent. "
            "You must use tools to complete the job. "
            "First call load_request_context to read the payload from the supervisor agent. "
            "Then call search_recommendation_context to retrieve RAG or multi-route context. "
            "Finally call run_recommendation_route to execute pruning, scoring, and path selection. "
            "Do not invent recommendation paths yourself; the recommendation must come from the run_recommendation_route tool. "
            "Return only a JSON object matching: "
            '{"success": true, "recommendation": <recommendation_result>, "error_message": "", "error_code": ""}.'
        ),
        name="personal_recommendation_agent",
        description="Tool-calling agent for learning path recommendation",
        retries=2,
        defer_model_check=True,
    )

    @agent.tool(sequential=True)
    def load_request_context(ctx: RunContext[PersonalRecommendationDeps]) -> dict:
        return tool_load_request_context(ctx.deps.state)

    @agent.tool(sequential=True)
    def search_recommendation_context(ctx: RunContext[PersonalRecommendationDeps]) -> dict:
        return tool_search_recommendation_context(ctx.deps.state)

    @agent.tool(sequential=True)
    def run_recommendation_route(ctx: RunContext[PersonalRecommendationDeps]) -> dict:
        return tool_run_recommendation_route(ctx.deps.state)

    @agent.output_validator
    def require_recommendation_tools(
        ctx: RunContext[PersonalRecommendationDeps],
        output: PersonalRecommendationResult,
    ) -> PersonalRecommendationResult:
        if not isinstance(ctx.deps.state.get("recommendation_result"), dict):
            raise ModelRetry(
                "You must call load_request_context, search_recommendation_context, "
                "and run_recommendation_route before returning the final result."
            )
        return output

    return agent


def build_personal_recommendation_user_prompt(state: Dict[str, Any]) -> str:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    summary = {
        "user_id": payload.get("user_id"),
        "syllabus_id": payload.get("syllabus_id"),
        "goals": payload.get("goals") or [],
        "question": payload.get("question") or "",
        "graph_name": payload.get("graph_name") or payload.get("rag_graph_name") or "",
        "tool_requirements": PERSONAL_RECOMMENDATION_TOOL_ORDER,
    }
    return json.dumps(summary, ensure_ascii=False)


def run_personal_recommendation_agent(payload: Dict[str, Any]) -> PersonalRecommendationResult:
    state = {
        "payload": payload or {},
        "request_context": {},
        "rag_context": None,
        "recommendation_result": None,
        "tool_trace": [],
    }
    deps = PersonalRecommendationDeps(state=state)
    agent = get_personal_recommendation_agent()
    result = agent.run_sync(build_personal_recommendation_user_prompt(state), deps=deps)
    output = result.output
    recommendation_result = state.get("recommendation_result")
    if isinstance(output, PersonalRecommendationResult):
        if isinstance(recommendation_result, dict):
            output.recommendation = recommendation_result
            output.success = bool(recommendation_result.get("success"))
            output.error_message = str(recommendation_result.get("error_message") or output.error_message or "")
            output.error_code = str(recommendation_result.get("error_code") or output.error_code or "")
        return output
    return PersonalRecommendationResult(
        success=bool(recommendation_result.get("success")) if isinstance(recommendation_result, dict) else False,
        recommendation=recommendation_result if isinstance(recommendation_result, dict) else None,
        error_message="",
        error_code="",
    )
