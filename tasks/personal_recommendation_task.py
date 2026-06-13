"""个人学习路径推荐模块门户。

跨模块调用和 API 层调用都应从这里进入；确定性推荐算法、Agent 工具和
Agent 运行时下沉在 ``tasks.personal_recommendation`` 包内。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

################
# Agent 入口：构造或运行个人推荐 Agent。
from tasks.personal_recommendation.agent_runtime import (
    get_personal_recommendation_agent,
    run_personal_recommendation_agent,
)

################
# 推荐服务：画像适配、学习树读取、确定性路径推荐和 payload 入口。
from tasks.personal_recommendation.service import (
    NEXT_ACTION_ASK_GOAL_CLARIFICATION,
    NEXT_ACTION_CONFIRM_PATH,
    NEXT_ACTION_GENERATE_RESOURCES,
    RECOMMENDATION_SCHEMA_VERSION,
    build_recommendation_profile,
    ensure_recommendation_snapshot,
    load_recommendation_learning_tree,
    run_recommendation_route,
    run_recommendation_route_from_payload,
)
from tasks.personal_recommendation.learning_plan import (
    LEARNING_PLAN_MANIFEST_VERSION,
    LEARNING_PLAN_SOURCE_AUTO_AGENT,
    LEARNING_PLAN_SOURCE_RECOMMENDATION,
    LEARNING_PLAN_STATUS_ACTIVE,
    LEARNING_PLAN_STATUS_ABANDONED,
    LEARNING_PLAN_STATUS_COMPLETED,
    LEARNING_PLAN_STATUS_SUPERSEDED,
    LEARNING_PLAN_STEP_STATUS_ACTIVE,
    LEARNING_PLAN_STEP_STATUS_COMPLETED,
    LEARNING_PLAN_STEP_STATUS_PENDING,
    LEARNING_PLAN_STEP_STATUS_SKIPPED,
    accept_recommendation_path,
    append_learning_plan_manifest_entry,
    get_active_learning_plan,
    load_learning_plan_manifest,
    update_learning_plan_step_status,
)
from tasks.personal_recommendation.snapshot import (
    RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE,
    RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND,
    RECOMMENDATION_SNAPSHOT_FILE_BACKEND_ENV,
    RECOMMENDATION_SNAPSHOT_ID_PREFIX,
    RECOMMENDATION_SNAPSHOT_ROOT_DIR,
    RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION,
    RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED,
    RECOMMENDATION_SNAPSHOT_STATUS_EXPIRED,
    RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
    RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED,
    accept_recommendation_snapshot_path,
    get_recommendation_snapshot,
    list_recommendation_snapshots,
    save_recommendation_snapshot,
)

__all__ = [
    "build_recommendation_profile",
    "accept_recommendation_path",
    "append_learning_plan_manifest_entry",
    "get_personal_recommendation_agent",
    "get_active_learning_plan",
    "ensure_recommendation_snapshot",
    "LEARNING_PLAN_MANIFEST_VERSION",
    "LEARNING_PLAN_SOURCE_AUTO_AGENT",
    "LEARNING_PLAN_SOURCE_RECOMMENDATION",
    "LEARNING_PLAN_STATUS_ACTIVE",
    "LEARNING_PLAN_STATUS_ABANDONED",
    "LEARNING_PLAN_STATUS_COMPLETED",
    "LEARNING_PLAN_STATUS_SUPERSEDED",
    "LEARNING_PLAN_STEP_STATUS_ACTIVE",
    "LEARNING_PLAN_STEP_STATUS_COMPLETED",
    "LEARNING_PLAN_STEP_STATUS_PENDING",
    "LEARNING_PLAN_STEP_STATUS_SKIPPED",
    "RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE",
    "RECOMMENDATION_SNAPSHOT_ERROR_NOT_FOUND",
    "RECOMMENDATION_SNAPSHOT_FILE_BACKEND_ENV",
    "RECOMMENDATION_SNAPSHOT_ID_PREFIX",
    "RECOMMENDATION_SNAPSHOT_ROOT_DIR",
    "RECOMMENDATION_SNAPSHOT_SCHEMA_VERSION",
    "RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED",
    "RECOMMENDATION_SNAPSHOT_STATUS_EXPIRED",
    "RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED",
    "RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED",
    "accept_recommendation_snapshot_path",
    "get_recommendation_snapshot",
    "load_recommendation_learning_tree",
    "load_learning_plan_manifest",
    "list_recommendation_snapshots",
    "NEXT_ACTION_ASK_GOAL_CLARIFICATION",
    "NEXT_ACTION_CONFIRM_PATH",
    "NEXT_ACTION_GENERATE_RESOURCES",
    "RECOMMENDATION_SCHEMA_VERSION",
    "run_personal_recommendation_agent",
    "run_recommendation_route",
    "run_recommendation_route_from_payload",
    "save_recommendation_snapshot",
    "update_learning_plan_step_status",
]
