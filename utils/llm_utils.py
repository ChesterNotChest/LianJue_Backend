from knowlion.multi_model_litellm import LitellmMultiModel
from config import LITELLM_MODEL_CONFIGS


def get_model_instance() -> LitellmMultiModel:
    """Return a LitellmMultiModel initialized from LiteLLM-compatible config."""
    return LitellmMultiModel(LITELLM_MODEL_CONFIGS)
