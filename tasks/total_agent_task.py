"""Total Agent task portal.

Cross-module callers should enter the formal Total Agent through this thin
facade instead of importing package internals.
"""

from __future__ import annotations

from typing import Any, Dict

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
    TOTAL_AGENT_INTENTS,
    TOTAL_AGENT_SCHEMA_VERSION,
    TOTAL_AGENT_TOOL_ORDER,
)
from tasks.total_agent.agent_runtime import (
    get_total_agent,
    run_total_agent,
    run_total_agent_agent,
)

__all__ = [
    "ACTION_ASK_GOAL_CLARIFICATION",
    "ACTION_GENERATE_CURRENT_STEP_RESOURCE",
    "ACTION_GET_NEXT_LEARNING_TASK",
    "ACTION_RECORD_LEARNING_FEEDBACK",
    "ACTION_RETRY_RECOMMENDATION",
    "ACTION_WAIT_USER_ACCEPTANCE",
    "INTENT_ACCEPT_RECOMMENDATION",
    "INTENT_ASK_GOAL_CLARIFICATION",
    "INTENT_GENERATE_CURRENT_STEP_RESOURCE",
    "INTENT_RECORD_LEARNING_FEEDBACK",
    "INTENT_RECOMMEND_LEARNING_PATH",
    "INTENT_SKIP_CURRENT_STEP",
    "TOTAL_AGENT_INTENTS",
    "TOTAL_AGENT_SCHEMA_VERSION",
    "TOTAL_AGENT_TOOL_ORDER",
    "get_total_agent",
    "run_total_agent",
    "run_total_agent_agent",
]
