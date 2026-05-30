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
    build_recommendation_profile,
    load_recommendation_learning_tree,
    run_recommendation_route,
    run_recommendation_route_from_payload,
)

__all__ = [
    "build_recommendation_profile",
    "get_personal_recommendation_agent",
    "load_recommendation_learning_tree",
    "run_personal_recommendation_agent",
    "run_recommendation_route",
    "run_recommendation_route_from_payload",
]
