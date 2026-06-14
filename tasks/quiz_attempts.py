from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


MAX_ATTEMPTS_PER_RESOURCE = 100


def _root() -> Path:
    return Path(os.environ.get("QUIZ_ATTEMPT_ROOT") or Path(__file__).resolve().parents[1] / "quiz_attempts")


def _safe_resource_id(resource_id: Any) -> str:
    text = str(resource_id or "").strip()
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)[:120]


def _attempt_path(user_id: int, resource_id: str) -> Path:
    directory = _root() / f"user_{int(user_id)}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{_safe_resource_id(resource_id)}.jsonl"


def _read_attempts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    attempts: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("attempt_id"):
                attempts.append(item)
    return attempts


def _write_attempts(path: Path, attempts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in attempts) + "\n"
    fd, tmp_path = tempfile.mkstemp(suffix=".jsonl", prefix=".tmp_quiz_attempts_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def list_quiz_attempts(user_id: int, resource_id: str, limit: int = 20) -> list[dict]:
    attempts = _read_attempts(_attempt_path(user_id, resource_id))
    try:
        normalized_limit = max(1, int(limit))
    except Exception:
        normalized_limit = 20
    return attempts[-normalized_limit:]


def submit_quiz_attempt(
    *,
    user_id: int,
    syllabus_id: int,
    resource_id: str,
    attempt_id: str | None = None,
    answers: dict[str, Any] | None = None,
    score: float | None = None,
    correct_count: int | None = None,
    total_count: int | None = None,
    wrong_knowledge_items: list[str] | None = None,
    answer_records: list[dict] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    if not user_id:
        return {"success": False, "error_code": "missing_user_id", "error_message": "user_id is required"}
    resource_id = str(resource_id or "").strip()
    if not resource_id:
        return {"success": False, "error_code": "missing_resource_id", "error_message": "resource_id is required"}

    path = _attempt_path(user_id, resource_id)
    attempts = _read_attempts(path)
    normalized_attempt_id = str(attempt_id or "").strip()
    if normalized_attempt_id:
        for item in attempts:
            if item.get("attempt_id") == normalized_attempt_id:
                return {
                    "success": True,
                    "attempt": item,
                    "attempts": attempts[-20:],
                    "duplicate": True,
                    "error_code": "",
                    "error_message": "",
                }

    now_ts = int(time.time())
    new_attempt = {
        "attempt_id": normalized_attempt_id or f"attempt_{now_ts}_{uuid.uuid4().hex[:8]}",
        "user_id": int(user_id),
        "syllabus_id": int(syllabus_id or 0),
        "resource_id": resource_id,
        "submitted_at": now_ts,
        "score": score,
        "correct_count": correct_count,
        "total_count": total_count,
        "answers": answers or {},
        "wrong_knowledge_items": list(wrong_knowledge_items or []),
        "answer_records": list(answer_records or []),
        "metadata": metadata or {},
    }
    attempts.append(new_attempt)
    if len(attempts) > MAX_ATTEMPTS_PER_RESOURCE:
        attempts = attempts[-MAX_ATTEMPTS_PER_RESOURCE:]
    _write_attempts(path, attempts)
    return {
        "success": True,
        "attempt": new_attempt,
        "attempts": attempts[-20:],
        "duplicate": False,
        "error_code": "",
        "error_message": "",
    }
