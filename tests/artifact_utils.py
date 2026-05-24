import json
import shutil
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts"


def write_test_artifact(name: str, payload: Any) -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_ROOT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text_artifact(name: str, content: str) -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_ROOT / name
    path.write_text(str(content), encoding="utf-8")
    return path


def prepare_artifact_backend(name: str) -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
