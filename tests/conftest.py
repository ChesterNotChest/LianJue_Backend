import json
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
JSON_ARTIFACT_DIRS = (
    ROOT / "schedule" / "syllabus_draft",
    ROOT / "schedule" / "syllabus",
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _snapshot_json_files():
    files = set()
    for directory in JSON_ARTIFACT_DIRS:
        if directory.exists():
            files.update(path.resolve() for path in directory.glob("*.json"))
    return files


@pytest.fixture(autouse=True)
def repo_cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


@pytest.fixture(autouse=True)
def cleanup_new_json_artifacts():
    before = _snapshot_json_files()
    yield
    after = _snapshot_json_files()
    for path in sorted(after - before):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def repo_json_factory():
    def _create(relative_dir, payload, prefix="pytest"):
        directory = ROOT / relative_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{prefix}_{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return _create
