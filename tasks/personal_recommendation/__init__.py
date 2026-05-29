"""个人学习路径推荐内部包。

跨模块业务入口请使用 ``tasks.personal_recommendation_task``。
本包只承载推荐模块的内部实现，具体分层按文件名进入：
agent_contracts、agent_tools、agent_runtime、service、perception、
candidate_generator、pruning、evaluator、selector_ib_grpo。
"""

__all__: list[str] = []
