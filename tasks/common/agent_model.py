"""Shared pydantic-ai model construction helpers for tool-calling agents."""

from __future__ import annotations

import os
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai.models.openai import OpenAIModel

from pydantic_ai.providers.openai import OpenAIProvider

from config import OPENAI_COMPAT_MODEL_CONFIGS


def _import_openai_model():
    """Lazy import to avoid collection-time failures on incompatible pydantic-ai versions."""
    from pydantic_ai.models.openai import OpenAIModel

    return OpenAIModel


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def should_disable_dashscope_thinking(model_name: str, api_base: str) -> bool:
    normalized_name = model_name.lower().removeprefix("openai/")
    normalized_base = api_base.lower()
    if "dashscope.aliyuncs.com" not in normalized_base:
        return False
    thinking_prefixes = ("qwen3", "qwq", "deepseek")
    return normalized_name.startswith(thinking_prefixes)


def is_dashscope_qwen_thinking_model(model_name: str, api_base: str) -> bool:
    """Backward-compatible alias used by existing tests/imports."""

    return should_disable_dashscope_thinking(model_name, api_base)


def disable_dashscope_qwen_thinking(model_config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a model config with DashScope Qwen thinking disabled when needed."""

    normalized_config = dict(model_config or {})
    model_name = _safe_text(normalized_config.get("model_name") or normalized_config.get("name"))
    api_base = _safe_text(normalized_config.get("api_base") or normalized_config.get("base_url"))
    if not should_disable_dashscope_thinking(model_name, api_base):
        return normalized_config

    extra_body = normalized_config.get("extra_body")
    if not isinstance(extra_body, dict):
        extra_body = {}
    extra_body.setdefault("enable_thinking", False)
    normalized_config["extra_body"] = extra_body
    return normalized_config


def build_openai_compatible_model(model_key: str = "text", *, agent_name: str = "agent") -> "OpenAIModel":
    """Build a pydantic-ai OpenAIModel from project OpenAI-compatible config.

    DashScope Qwen thinking models reject required/object tool_choice while
    thinking mode is enabled. Tool-calling agents need pydantic-ai's tool_choice
    behavior, so disable thinking mode at request level for these models.
    """

    text_config = OPENAI_COMPAT_MODEL_CONFIGS.get(model_key) or {}
    model_name = _safe_text(text_config.get("model_name") or text_config.get("name"))
    if not model_name:
        raise RuntimeError(f'missing MODEL_CONFIGS["{model_key}"]["model_name"] for {agent_name}')

    base_url = _safe_text(text_config.get("api_base") or text_config.get("base_url")) or None
    api_key = _safe_text(text_config.get("api_key")) or os.getenv("OPENAI_API_KEY")
    provider = OpenAIProvider(base_url=base_url, api_key=api_key)

    settings: Dict[str, Any] = {}
    configured_settings = text_config.get("model_settings")
    if isinstance(configured_settings, dict):
        settings.update(configured_settings)

    if should_disable_dashscope_thinking(model_name, base_url or ""):
        extra_body = settings.get("extra_body")
        if not isinstance(extra_body, dict):
            extra_body = {}
        extra_body.setdefault("enable_thinking", False)
        settings["extra_body"] = extra_body

    OpenAIModel = _import_openai_model()
    return OpenAIModel(model_name, provider=provider, settings=settings or None)
