"""Contracts for the tool-calling resource generation agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


RESOURCE_AGENT_SCHEMA_VERSION = "generative_agent.v1"

RESOURCE_GENERATION_TOOL_ORDER = [
    "read_generation_request",
    "read_generation_plan",
    "retrieve_generation_materials",
    "write_generation_draft",
    "generate_resource_payload",
    "persist_generated_resource",
]

RESOURCE_AGENT_ERROR_MISSING_REQUEST = "missing_request"
RESOURCE_AGENT_ERROR_TOOLCHAIN_INCOMPLETE = "toolchain_incomplete"
RESOURCE_AGENT_ERROR_GENERATION_FAILED = "generation_failed"
RESOURCE_AGENT_ERROR_PERSIST_FAILED = "persist_failed"


@dataclass
class ResourceGenerationDeps:
    state: Dict[str, Any] = field(default_factory=dict)


def _parse_json_dict(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return value
        return parsed if isinstance(parsed, dict) else value
    return value


def _parse_json_list(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            return value
        return parsed if isinstance(parsed, list) else value
    return value


class ResourceGenerationAgentResult(BaseModel):
    success: bool = True
    schema_version: str = RESOURCE_AGENT_SCHEMA_VERSION
    resource_type: str = ""
    resource: Optional[Dict[str, Any]] = None
    generated_content: Optional[Dict[str, Any]] = None
    planning_bundle: Optional[Dict[str, Any]] = None
    tool_trace: List[str] = Field(default_factory=list)
    error_message: str = ""
    error_code: str = ""

    @field_validator("resource", "generated_content", "planning_bundle", mode="before")
    @classmethod
    def parse_dict_fields(cls, value: Any) -> Any:
        return _parse_json_dict(value)

    @field_validator("tool_trace", mode="before")
    @classmethod
    def parse_tool_trace(cls, value: Any) -> Any:
        return _parse_json_list(value)
