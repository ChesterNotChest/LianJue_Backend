from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from pydantic import BaseModel, Field


TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"
TOTAL_AGENT_CONTEXT_SCHEMA_VERSION = "total_agent.context.v1"

INTENT_RECOMMEND_LEARNING_PATH = "recommend_learning_path"
INTENT_ACCEPT_RECOMMENDATION = "accept_recommendation"
INTENT_GENERATE_CURRENT_STEP_RESOURCE = "generate_current_step_resource"
INTENT_RECORD_LEARNING_FEEDBACK = "record_learning_feedback"
INTENT_SKIP_CURRENT_STEP = "skip_current_step"
INTENT_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"

TOTAL_AGENT_INTENTS = {
    INTENT_RECOMMEND_LEARNING_PATH,
    INTENT_ACCEPT_RECOMMENDATION,
    INTENT_GENERATE_CURRENT_STEP_RESOURCE,
    INTENT_RECORD_LEARNING_FEEDBACK,
    INTENT_SKIP_CURRENT_STEP,
    INTENT_ASK_GOAL_CLARIFICATION,
}

ACTION_WAIT_USER_ACCEPTANCE = "wait_user_acceptance"
ACTION_GENERATE_CURRENT_STEP_RESOURCE = "generate_current_step_resource"
ACTION_RECORD_LEARNING_FEEDBACK = "record_learning_feedback"
ACTION_GET_NEXT_LEARNING_TASK = "get_next_learning_task"
ACTION_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"
ACTION_RETRY_RECOMMENDATION = "retry_recommendation"
ACTION_CONTINUE_EXISTING_PLAN = "continue_existing_plan"

TOOL_LOAD_TOTAL_CONTEXT = "load_total_context"
TOOL_INFER_USER_INTENT = "infer_user_intent"
TOOL_RUN_LEARNING_RECOMMENDATION = "run_learning_recommendation"
TOOL_NORMALIZE_LEARNING_GOAL = "normalize_learning_goal_for_recommendation"
TOOL_ACCEPT_LEARNING_PLAN = "accept_learning_plan"
TOOL_GET_NEXT_LEARNING_TASK = "get_next_learning_task"
TOOL_GENERATE_CURRENT_STEP_RESOURCE = "generate_current_step_resource"
TOOL_RECORD_LEARNING_FEEDBACK = "record_learning_feedback"
TOOL_SKIP_CURRENT_STEP = "skip_current_step"

TOTAL_AGENT_LEARNING_EVENT_RECORDED = "learning_event_recorded"

RESOURCE_STRATEGY_DEFAULT_TYPE = "documents"
RESOURCE_STRATEGY_DIFFICULTY_STANDARD = "standard"
RESOURCE_STRATEGY_DIFFICULTY_TARGETED = "targeted"
RESOURCE_STRATEGY_DIFFICULTY_REVIEW = "review"

PROFILE_SOURCE_NONE = "none"
PROFILE_SOURCE_PERSISTED = "persisted_profile"
PROFILE_SOURCE_BUILT = "built_profile"

PROFILE_READ_ACTION_USE_PERSISTED_ONLY = "use_persisted_only"
PROFILE_READ_ACTION_BUILD_IF_MISSING = "build_if_missing"

PROFILE_WARNING_NOT_FOUND = "profile_not_found"
PROFILE_WARNING_READ_FAILED = "profile_read_failed"
PROFILE_WARNING_BUILD_SKIPPED = "profile_build_skipped"

RECOVERY_RETRY_RECOMMENDATION = ACTION_RETRY_RECOMMENDATION
RECOVERY_ASK_GOAL_CLARIFICATION = ACTION_ASK_GOAL_CLARIFICATION
RECOVERY_CONTINUE_EXISTING_PLAN = ACTION_CONTINUE_EXISTING_PLAN

RECOMMENDATION_RECOVERY_ACTIONS = {
    RECOVERY_RETRY_RECOMMENDATION,
    RECOVERY_ASK_GOAL_CLARIFICATION,
    RECOVERY_CONTINUE_EXISTING_PLAN,
}

TOTAL_AGENT_TOOL_ORDER = {
    INTENT_RECOMMEND_LEARNING_PATH: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_RUN_LEARNING_RECOMMENDATION,
    ],
    INTENT_ACCEPT_RECOMMENDATION: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_ACCEPT_LEARNING_PLAN,
        TOOL_GET_NEXT_LEARNING_TASK,
    ],
    INTENT_GENERATE_CURRENT_STEP_RESOURCE: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_GET_NEXT_LEARNING_TASK,
        TOOL_GENERATE_CURRENT_STEP_RESOURCE,
    ],
    INTENT_RECORD_LEARNING_FEEDBACK: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_RECORD_LEARNING_FEEDBACK,
        TOOL_GET_NEXT_LEARNING_TASK,
    ],
    INTENT_SKIP_CURRENT_STEP: [
        TOOL_LOAD_TOTAL_CONTEXT,
        TOOL_INFER_USER_INTENT,
        TOOL_SKIP_CURRENT_STEP,
        TOOL_GET_NEXT_LEARNING_TASK,
    ],
}


@dataclass
class TotalAgentDeps:
    state: Dict[str, Any] = field(default_factory=dict)


class TotalAgentResult(BaseModel):
    success: bool = True
    schema_version: str = TOTAL_AGENT_SCHEMA_VERSION
    intent: str = ""
    tool_trace: List[str] = Field(default_factory=list)
    result: Dict[str, Any] = Field(default_factory=dict)
    suggested_next_action: str = ""
    error_code: str = ""
    error_message: str = ""
