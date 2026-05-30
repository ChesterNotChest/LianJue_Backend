"""学习进度图谱模块门户。

跨模块调用和 API 层调用都应从这里进入；确定性图谱服务、树存储、
树变更工具和 Student Agent 运行时下沉在 ``tasks.study_graph`` 包内。
"""

################
# 图谱服务入口：从学生事件或资源事件生成、提交、读取学习树。
from tasks.study_graph.service import (
    build_study_graph_changes_from_resource_event,
    build_study_graph_changes_from_student_payload,
    get_learning_tree_features,
    get_student_learning_tree,
    get_student_learning_tree_context,
    submit_learning_tree_changes,
)

################
# Student Agent 入口：结合 RAG 和学习树上下文生成图谱变更。
from tasks.study_graph.student_agent import (
    StudentAgentDeps,
    StudentAgentResult,
    get_student_agent,
    get_student_learning_graph,
    run_student_agent,
)

__all__ = [
    "StudentAgentDeps",
    "StudentAgentResult",
    "build_study_graph_changes_from_resource_event",
    "build_study_graph_changes_from_student_payload",
    "get_learning_tree_features",
    "get_student_agent",
    "get_student_learning_graph",
    "get_student_learning_tree",
    "get_student_learning_tree_context",
    "run_student_agent",
    "submit_learning_tree_changes",
]
