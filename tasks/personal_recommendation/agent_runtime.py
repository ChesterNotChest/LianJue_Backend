import json
import os
from functools import lru_cache
from typing import Any, Dict

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel

from config import OPENAI_COMPAT_MODEL_CONFIGS
from tasks.common.agent_model import build_openai_compatible_model
from tasks.personal_recommendation.agent_contracts import (
    ConceptDecompositionAgentResult,
    ConceptDecompositionDeps,
    PersonalRecommendationDeps,
    PersonalRecommendationResult,
)
from tasks.personal_recommendation.agent_tools import (
    tool_decompose_period_concepts,
    safe_text,
    tool_load_request_context,
    tool_read_period_context,
    tool_retrieve_period_evidence,
    tool_run_recommendation_route,
    tool_search_recommendation_context,
    tool_validate_concept_graph,
)
from tasks.personal_recommendation.concept_decomposer import CONCEPT_DECOMPOSITION_TOOL_ORDER


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


@lru_cache(maxsize=1)
def get_period_concept_decomposer_agent() -> Agent:
    agent = Agent(
        model=build_openai_compatible_model(agent_name="period concept decomposer agent"),
        deps_type=ConceptDecompositionDeps,
        output_type=ConceptDecompositionAgentResult,
        system_prompt=(
            "You are the period concept decomposition agent. "
            "You must use tools in order: read_period_context, retrieve_period_evidence, "
            "decompose_period_concepts, validate_concept_graph. "
            "Your job is to propose a structured concept graph from course period content and RAG evidence. "
            "Do not generate learning paths. Do not persist data. "
            "The decompose_period_concepts tool must receive a JSON object with concepts and edges. "
            "Each concept should include title, source_period.week_index, prerequisite_titles, confidence, matched_by, and reason. "
            "Concept titles must be ONLY ONE noun or phrase regarding the point of KNOWLEDGE (≤10 Chinese characters | NO symbols). "
            "Outcomes should also be short noun phrases, no more than a sentence. "
            "Return only the validated concept graph result."
        ),
        name="period_concept_decomposer_agent",
        description="Tool-calling agent for decomposing period syllabus content into concept graph",
        retries=2,
        defer_model_check=True,
    )

    @agent.tool(sequential=True)
    def read_period_context(ctx: RunContext[ConceptDecompositionDeps]) -> dict:
        return tool_read_period_context(ctx.deps.state)

    @agent.tool(sequential=True)
    def retrieve_period_evidence(ctx: RunContext[ConceptDecompositionDeps]) -> dict:
        return tool_retrieve_period_evidence(ctx.deps.state)

    @agent.tool(sequential=True)
    def decompose_period_concepts(ctx: RunContext[ConceptDecompositionDeps], proposal: Dict[str, Any]) -> dict:
        return tool_decompose_period_concepts(ctx.deps.state, proposal)

    @agent.tool(sequential=True)
    def validate_concept_graph(ctx: RunContext[ConceptDecompositionDeps]) -> dict:
        return tool_validate_concept_graph(ctx.deps.state)

    @agent.output_validator
    def require_concept_decomposition_tools(
        ctx: RunContext[ConceptDecompositionDeps],
        output: ConceptDecompositionAgentResult,
    ) -> ConceptDecompositionAgentResult:
        if not isinstance(ctx.deps.state.get("decomposition_result"), dict):
            raise ModelRetry("You must call all concept decomposition tools before returning.")
        return output

    return agent


def build_period_concept_decomposer_user_prompt(state: Dict[str, Any]) -> str:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    summary = {
        "syllabus_id": payload.get("syllabus_id"),
        "period_count": len(payload.get("periods") or []),
        "graph_name": payload.get("graph_name") or "",
        "tool_requirements": CONCEPT_DECOMPOSITION_TOOL_ORDER,
    }
    return json.dumps(summary, ensure_ascii=False)


def run_period_concept_decomposer_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = {
        "payload": payload or {},
        "periods": [],
        "rag_context": None,
        "normalized_rag_context": None,
        "concept_proposal": None,
        "decomposition_result": None,
        "tool_trace": [],
    }
    deps = ConceptDecompositionDeps(state=state)
    agent = get_period_concept_decomposer_agent()
    result = agent.run_sync(build_period_concept_decomposer_user_prompt(state), deps=deps)
    output = result.output
    decomposition = state.get("decomposition_result") if isinstance(state.get("decomposition_result"), dict) else {}
    if not decomposition:
        decomposition = {
            "success": False,
            "concepts": [],
            "edges": [],
            "fallback_used": False,
            "error_message": "",
            "error_code": "missing_decomposition_result",
        }
    decomposition["tool_trace"] = list(state.get("tool_trace") or [])
    if os.getenv("PERSONAL_RECOMMENDATION_DECOMPOSER_DEBUG") == "1":
        normalized_rag = state.get("normalized_rag_context") if isinstance(state.get("normalized_rag_context"), dict) else {}
        evidence_items = normalized_rag.get("evidence_items") if isinstance(normalized_rag.get("evidence_items"), list) else []
        decomposition["debug"] = {
            "concept_proposal": state.get("concept_proposal") if isinstance(state.get("concept_proposal"), dict) else {},
            "rag_context_summary": {
                "success": bool(normalized_rag.get("success")),
                "query": normalized_rag.get("query") or "",
                "graph_name": normalized_rag.get("graph_name") or "",
                "evidence_count": len(evidence_items),
                "first_evidence_items": evidence_items[:3],
                "reasoning_edges": normalized_rag.get("reasoning_edges") or [],
                "entity_detail_count": len(normalized_rag.get("entity_details") or []),
                "path_scores": normalized_rag.get("path_scores") or {},
                "warnings": normalized_rag.get("warnings") or [],
            },
        }
    if isinstance(output, ConceptDecompositionAgentResult):
        decomposition.setdefault("success", output.success)
    return decomposition
