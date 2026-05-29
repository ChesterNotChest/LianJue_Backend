"""生成资源模块门户。

跨模块调用和 API 层调用都应从这里进入；具体的规划 Agent、生成 Agent、
资源持久化、校验和存储工具下沉在 ``tasks.generative`` 包内。
"""

################
# 稳定契约：资源类型、schema 版本、manifest 版本等跨模块常量。
from tasks.generative.contracts import (
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
# 持久化入口：生成资源文件、落盘 manifest，并提供具体资源类型的保存函数。
from tasks.generative.resource_persistence import (
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
# 生成 Agent 实现：门面保留可 monkeypatch 的兼容 wrapper，真实逻辑在包内。
from tasks.generative import resource_generation_agent as _generation_impl
from tasks.generative.resource_generation_agent import (
    LLMResourceGenerationAgent as _BaseLLMResourceGenerationAgent,
    build_single_resource_payload,
    normalize_generation_request,
)

################
# 规划 Agent：为资源生成整理计划、检索材料、生成资源草稿。
from tasks.generative.resource_planning_agent import (
    ResourcePlanningAgent,
    get_resource_planning_agent,
    run_resource_planning_agent,
)

################
# 存储工具：workspace、manifest、resource id、JSON/text 文件读写。
from tasks.generative.storage import (
    _get_backend_root,
    _get_generative_root,
    append_manifest_entry,
    ensure_generative_workspace,
    get_generative_user_root,
    load_manifest,
    new_resource_id,
    normalize_positive_int,
    normalize_resource_type,
    read_json,
    repo_relative_path,
    save_manifest,
    utc_timestamp,
    write_json,
    write_text,
)

################
# 校验工具：资源 payload 校验与 Mermaid 文本校验。
from tasks.generative.validation import (
    strip_mermaid_fence,
    validate_coding_practice_payload,
    validate_document_payload,
    validate_mermaid_text,
    validate_ppt_payload,
    validate_quiz_payload,
)


LITELLM_MODEL_CONFIGS = _generation_impl.LITELLM_MODEL_CONFIGS


class LLMResourceGenerationAgent(_BaseLLMResourceGenerationAgent):
    """Compatibility wrapper preserving task-level monkeypatch points."""

    def __init__(self, model=None) -> None:
        _generation_impl.LITELLM_MODEL_CONFIGS = LITELLM_MODEL_CONFIGS
        super().__init__(model=model)


def generate_single_resource_from_request(
    request_payload: dict,
    resource_type: str,
    *,
    generation_agent=None,
    planning_agent=None,
) -> dict:
    return _generation_impl.generate_single_resource_from_request(
        request_payload,
        resource_type,
        generation_agent=generation_agent or LLMResourceGenerationAgent(),
        planning_agent=planning_agent or get_resource_planning_agent(),
    )


def run_resource_generation_agent(
    request_payload: dict,
    *,
    generation_agent=None,
    planning_agent=None,
) -> dict:
    return _generation_impl.run_resource_generation_agent(
        request_payload,
        generation_agent=generation_agent or LLMResourceGenerationAgent(),
        planning_agent=planning_agent or get_resource_planning_agent(),
    )


def generate_resources_from_request(
    request_payload: dict,
    generation_agent=None,
    planning_agent=None,
) -> dict:
    return run_resource_generation_agent(
        request_payload,
        generation_agent=generation_agent,
        planning_agent=planning_agent,
    )


# Backward-compatible aliases used by existing tests and callers.
_new_resource_id = new_resource_id
_normalize_positive_int = normalize_positive_int
_normalize_resource_type = normalize_resource_type
_read_json = read_json
_repo_relative_path = repo_relative_path
_strip_mermaid_fence = strip_mermaid_fence
_utc_timestamp = utc_timestamp
_write_json = write_json
_write_text = write_text


__all__ = [
    "GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION",
    "GENERATIVE_DOCUMENT_SCHEMA_VERSION",
    "GENERATIVE_MANIFEST_VERSION",
    "GENERATIVE_MINDMAP_SCHEMA_VERSION",
    "GENERATIVE_PPT_SCHEMA_VERSION",
    "GENERATIVE_QUIZ_SCHEMA_VERSION",
    "GENERATIVE_RESOURCE_TYPES",
    "LITELLM_MODEL_CONFIGS",
    "LLMResourceGenerationAgent",
    "MINDMAP_ALLOWED_DIAGRAM_PREFIXES",
    "ResourcePlanningAgent",
    "_get_backend_root",
    "_get_generative_root",
    "_new_resource_id",
    "_normalize_positive_int",
    "_normalize_resource_type",
    "_read_json",
    "_repo_relative_path",
    "_strip_mermaid_fence",
    "_utc_timestamp",
    "_write_json",
    "_write_text",
    "append_manifest_entry",
    "build_single_resource_payload",
    "ensure_generative_workspace",
    "generate_coding_practice",
    "generate_mindmap",
    "generate_ppt",
    "generate_quiz",
    "generate_resource",
    "generate_resources_from_request",
    "generate_single_resource_from_request",
    "generate_structured_document",
    "get_generative_user_root",
    "get_resource_planning_agent",
    "load_manifest",
    "new_resource_id",
    "normalize_positive_int",
    "normalize_generation_request",
    "normalize_resource_type",
    "persist_coding_practice_resource",
    "persist_generated_resource",
    "persist_mindmap_resource",
    "persist_ppt_resource",
    "persist_quiz_resource",
    "persist_structured_document_resource",
    "read_json",
    "repo_relative_path",
    "run_resource_generation_agent",
    "run_resource_planning_agent",
    "save_manifest",
    "strip_mermaid_fence",
    "utc_timestamp",
    "validate_coding_practice_payload",
    "validate_document_payload",
    "validate_mermaid_text",
    "validate_ppt_payload",
    "validate_quiz_payload",
    "write_json",
    "write_text",
]
