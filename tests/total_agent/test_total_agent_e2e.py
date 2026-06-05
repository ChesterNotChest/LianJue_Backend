"""Unified Total Agent E2E entrypoint.

This module is the only pytest-collected Total Agent E2E entrypoint. Scenario
implementations live in e2e_cases_* modules so legacy E2E coverage is reused
without keeping multiple competing test entry files.
"""

from tests.total_agent.e2e_cases_amend import (
    test_e2e_state_fixture_builds_deep_student_state,
    test_e2e_state_fixture_real_profile_agent_optional,
    test_total_agent_e2e_answer_learning_question_learning_strategy,
    test_total_agent_e2e_answer_learning_question_no_plan_mutation,
    test_total_agent_e2e_continue_existing_plan_when_goal_unclear_but_plan_active,
    test_total_agent_e2e_feedback_updates_plan_and_study_graph,
    test_total_agent_e2e_profile_driven_continue,
    test_total_agent_e2e_study_graph_stale_step_review,
    test_total_agent_e2e_study_graph_weak_step_continue,
    test_total_agent_e2e_vague_goal_asks_clarification_without_plan,
)
from tests.total_agent.e2e_cases_large import (
    db_total_agent_user_case,
    test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph,
    test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db,
)
from tests.total_agent.e2e_cases_real_deep_state import (
    db_real_deep_state_case,
    test_total_agent_e2e_real_deep_state_all_agents,
    test_total_agent_e2e_real_deep_state_answer_learning_question,
)


__all__ = [
    "test_e2e_state_fixture_builds_deep_student_state",
    "test_e2e_state_fixture_real_profile_agent_optional",
    "test_total_agent_e2e_answer_learning_question_learning_strategy",
    "test_total_agent_e2e_answer_learning_question_no_plan_mutation",
    "test_total_agent_e2e_continue_existing_plan_when_goal_unclear_but_plan_active",
    "test_total_agent_e2e_feedback_updates_plan_and_study_graph",
    "test_total_agent_e2e_profile_driven_continue",
    "test_total_agent_e2e_study_graph_stale_step_review",
    "test_total_agent_e2e_study_graph_weak_step_continue",
    "test_total_agent_e2e_vague_goal_asks_clarification_without_plan",
    "test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph",
    "test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db",
    "test_total_agent_e2e_real_deep_state_all_agents",
    "test_total_agent_e2e_real_deep_state_answer_learning_question",
    "db_total_agent_user_case",
    "db_real_deep_state_case",
]
