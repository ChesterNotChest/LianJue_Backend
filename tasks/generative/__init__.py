"""生成资源内部包。

顶层 ``tasks/generative_task.py`` 是模块间调用入口；真实实现按职责放在
本包内，方便后续维护时先看这里的分层。
"""

################
# 稳定契约：资源类型、schema 版本、manifest 版本等常量。
from .contracts import (
    GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
    GENERATIVE_DOCUMENT_SCHEMA_VERSION,
    GENERATIVE_MANIFEST_VERSION,
    GENERATIVE_MINDMAP_SCHEMA_VERSION,
    GENERATIVE_PPT_SCHEMA_VERSION,
    GENERATIVE_QUIZ_SCHEMA_VERSION,
    GENERATIVE_RESOURCE_TYPES,
    MINDMAP_ALLOWED_DIAGRAM_PREFIXES,
)

################
# 持久化入口：校验生成内容、渲染文件、写 manifest。
from .resource_persistence import (
    generate_coding_practice,
    generate_mindmap,
    generate_ppt,
    generate_quiz,
    generate_resource,
    generate_structured_document,
    persist_coding_practice_resource,
    persist_generated_resource,
    persist_mindmap_resource,
    persist_ppt_resource,
    persist_quiz_resource,
    persist_structured_document_resource,
)

################
# 资源编排 Agent：整理 plan、检索材料、生成 draft。
from .resource_planning_agent import (
    ResourcePlanningAgent,
    get_resource_planning_agent,
    run_resource_planning_agent,
)

################
# 资源生成 Agent：调用规划 Agent，生成 typed JSON，再交给持久化工具。
from .resource_generation_agent import (
    LLMResourceGenerationAgent,
    build_single_resource_payload,
    generate_resources_from_request,
    generate_single_resource_from_request,
    normalize_generation_request,
    run_resource_generation_agent,
)

__all__ = [
    "GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION",
    "GENERATIVE_DOCUMENT_SCHEMA_VERSION",
    "GENERATIVE_MANIFEST_VERSION",
    "GENERATIVE_MINDMAP_SCHEMA_VERSION",
    "GENERATIVE_PPT_SCHEMA_VERSION",
    "GENERATIVE_QUIZ_SCHEMA_VERSION",
    "GENERATIVE_RESOURCE_TYPES",
    "LLMResourceGenerationAgent",
    "MINDMAP_ALLOWED_DIAGRAM_PREFIXES",
    "ResourcePlanningAgent",
    "build_single_resource_payload",
    "generate_coding_practice",
    "generate_mindmap",
    "generate_ppt",
    "generate_quiz",
    "generate_resource",
    "generate_resources_from_request",
    "generate_single_resource_from_request",
    "generate_structured_document",
    "get_resource_planning_agent",
    "normalize_generation_request",
    "persist_coding_practice_resource",
    "persist_generated_resource",
    "persist_mindmap_resource",
    "persist_ppt_resource",
    "persist_quiz_resource",
    "persist_structured_document_resource",
    "run_resource_generation_agent",
    "run_resource_planning_agent",
]
