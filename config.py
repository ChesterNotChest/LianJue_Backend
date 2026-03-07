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


# Load full config dict
_CONFIG = _load_config_file()

# Expose MODEL_CONFIGS and ABUTION_CONFIG with sensible defaults
MODEL_CONFIGS = _CONFIG.get("MODEL_CONFIGS", {})
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
