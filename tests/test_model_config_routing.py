from config import (
    _build_litellm_model_configs,
    _build_openai_compatible_model_configs,
)
from knowlion.multi_model_litellm import LitellmMultiModel
from utils.llm_utils import get_model_instance


def test_dashscope_model_names_are_normalized_for_litellm_and_openai_provider():
    raw_configs = {
        "text": {
            "model_name": "qwen-max",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "test-key",
        },
        "embed": {
            "model_name": "openai/text-embedding-v4",
            "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "test-key",
        },
    }

    litellm_configs = _build_litellm_model_configs(raw_configs)
    openai_compatible_configs = _build_openai_compatible_model_configs(raw_configs)

    assert litellm_configs["text"]["model_name"] == "openai/qwen-max"
    assert litellm_configs["embed"]["model_name"] == "openai/text-embedding-v4"
    assert openai_compatible_configs["text"]["model_name"] == "qwen-max"
    assert openai_compatible_configs["embed"]["model_name"] == "text-embedding-v4"


def test_global_llm_helper_uses_litellm_config():
    model = get_model_instance()

    assert isinstance(model, LitellmMultiModel)
    text_config = model.MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base:
        assert model_name.startswith("openai/")
