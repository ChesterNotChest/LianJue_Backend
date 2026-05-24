"""个人学习路径推荐的内部实现包。

外部调用统一走 ``tasks.personal_recommendation_task``。本包只放内部实现：
Agent 契约、Agent 工具、Agent 运行时，以及确定性的路径推荐算法分别拆开，
方便后续按同一层级维护其它 Agent。
"""

################
# Agent 契约：PydanticAI wrapper 使用的依赖对象和结果对象。
from .agent_contracts import PersonalRecommendationDeps, PersonalRecommendationResult

################
# Agent 运行时：构造并运行 LLM 工具调用型路径推荐 Agent。
from .agent_runtime import get_personal_recommendation_agent, run_personal_recommendation_agent

################
# Agent 工具：注册给路径推荐 Agent 的确定性工具函数。
from .agent_tools import (
    build_recommendation_search_query,
    tool_load_request_context,
    tool_run_recommendation_route,
    tool_search_recommendation_context,
)

################
# 路径感知：把画像和学习树转换为搜索状态与起点节点。
from .perception import generate_state

################
# 候选生成：基于图结构生成候选学习路径。
from .candidate_generator import generate

################
# 剪枝：执行硬约束过滤和 Pareto 风格软剪枝。
from .pruning import hard_prune, soft_prune_by_dominance

################
# 评估：为候选路径打分，并提供归一化与标量化能力。
from .evaluator import score, normalize_scores, scalar_scores

################
# 选择：从已评分候选中选出最终推荐路径。
from .selector_ib_grpo import ib_grpo_select

__all__ = [
    "PersonalRecommendationDeps",
    "PersonalRecommendationResult",
    "get_personal_recommendation_agent",
    "run_personal_recommendation_agent",
    "build_recommendation_search_query",
    "tool_load_request_context",
    "tool_run_recommendation_route",
    "tool_search_recommendation_context",
    "generate_state",
    "generate",
    "hard_prune",
    "soft_prune_by_dominance",
    "score",
    "normalize_scores",
    "scalar_scores",
    "ib_grpo_select",
]
