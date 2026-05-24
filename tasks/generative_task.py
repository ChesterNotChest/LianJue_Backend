"""Public task facade for generative resources.

All cross-module calls for resource generation should enter here. The internal
implementation lives under ``tasks.generative``.
"""

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
from tasks.generative import resource_generation_agent as _generation_impl
from tasks.generative.resource_generation_agent import (
    LLMResourceGenerationAgent as _BaseLLMResourceGenerationAgent,
    build_single_resource_payload,
    normalize_generation_request,
)
from tasks.generative.resource_planning_agent import (
    ResourcePlanningAgent,
    get_resource_planning_agent,
    run_resource_planning_agent,
)
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
