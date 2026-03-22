from knowlion.multi_model_litellm import LitellmMultiModel
from config import MODEL_CONFIGS


def get_model_instance() -> LitellmMultiModel:
    """Return a LitellmMultiModel initialized from global MODEL_CONFIGS."""
    return LitellmMultiModel(MODEL_CONFIGS)
