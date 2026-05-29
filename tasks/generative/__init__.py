"""生成资源内部包。

跨模块业务入口请使用 ``tasks.generative_task``。
本包只承载生成资源模块的内部实现，具体分层按文件名进入：
contracts、resource_planning_agent、resource_generation_agent、
resource_persistence、storage、validation。
"""

__all__: list[str] = []
