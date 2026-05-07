import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_config_file():
    # repo root is this file's directory
    root = Path(__file__).resolve().parent
    config_path = root / "config.json"
    example_path = root / "config.example.json"

    if config_path.exists():
        path = config_path
    elif example_path.exists():
        path = example_path
        logger.warning("Using config.example.json because config.json not found.\nPlease copy it to config.json and fill API keys.")
    else:
        logger.warning("No config.json or config.example.json found. returning empty config.")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception as e:
        logger.error(f"Failed to read config file {path}: {e}")
        return {}


def _normalize_litellm_model_name(model_name, api_base):
    if not isinstance(model_name, str):
        return model_name

    normalized_name = model_name.strip()
    normalized_base = str(api_base or "")

    if not normalized_name:
        return normalized_name

    if "dashscope.aliyuncs.com" in normalized_base and not normalized_name.startswith("openai/"):
        return f"openai/{normalized_name}"

    return normalized_name


def _normalize_openai_compatible_model_name(model_name, api_base):
    if not isinstance(model_name, str):
        return model_name

    normalized_name = model_name.strip()
    normalized_base = str(api_base or "")

    if "dashscope.aliyuncs.com" in normalized_base and normalized_name.startswith("openai/"):
        return normalized_name[len("openai/"):]

    return normalized_name


def _build_model_configs(model_configs, normalize_model_name):
    if not isinstance(model_configs, dict):
        return {}

    normalized_configs = {}
    for key, value in model_configs.items():
        if not isinstance(value, dict):
            normalized_configs[key] = value
            continue

        normalized_value = dict(value)
        normalized_value["model_name"] = normalize_model_name(
            normalized_value.get("model_name"),
            normalized_value.get("api_base") or normalized_value.get("base_url"),
        )
        normalized_configs[key] = normalized_value

    return normalized_configs


def _build_litellm_model_configs(model_configs):
    return _build_model_configs(model_configs, _normalize_litellm_model_name)


def _build_openai_compatible_model_configs(model_configs):
    return _build_model_configs(model_configs, _normalize_openai_compatible_model_name)


# Load full config dict
_CONFIG = _load_config_file()

# Expose MODEL_CONFIGS and ABUTION_CONFIG with sensible defaults
MODEL_CONFIGS = _CONFIG.get("MODEL_CONFIGS", {})
LITELLM_MODEL_CONFIGS = _build_litellm_model_configs(MODEL_CONFIGS)
OPENAI_COMPAT_MODEL_CONFIGS = _build_openai_compatible_model_configs(MODEL_CONFIGS)
ABUTION_CONFIG = _CONFIG.get("ABUTION_CONFIG", {})
# Expose processing config (save flags, device mode, batching)
PROCESSING_CONFIG = _CONFIG.get("PROCESSING_CONFIG", {})

# Expose database config (support common casings)
MYSQL = _CONFIG.get("MYSQL")


def get_mysql():
    """Return MySQL configuration dict (may be empty)."""
    return MYSQL


def get_config():
    """Return full loaded config dict."""
    return _CONFIG


# Convenience top-level names for common keys (fall back to env usage if empty)
MYSQL_HOST = MYSQL.get("host") if isinstance(MYSQL, dict) else None
MYSQL_PORT = MYSQL.get("port") if isinstance(MYSQL, dict) else None
MYSQL_USER = MYSQL.get("user") if isinstance(MYSQL, dict) else None
MYSQL_PASSWORD = MYSQL.get("password") if isinstance(MYSQL, dict) else None
MYSQL_DATABASE = MYSQL.get("database") if isinstance(MYSQL, dict) else None
