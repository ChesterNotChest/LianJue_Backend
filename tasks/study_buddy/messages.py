"""Study buddy chat/proactive message history."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BUDDY_MESSAGE_FILENAME, BUDDY_MESSAGE_MAX_ITEMS
from .memory import _memory_root


def _message_path(user_id: int, syllabus_id: int) -> Path:
    directory = _memory_root() / f"user_{int(user_id)}" / f"syllabus_{int(syllabus_id)}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / BUDDY_MESSAGE_FILENAME


def _read_messages(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    messages: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("text"):
                messages.append(item)
    return messages


def _write_messages(path: Path, messages: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in messages) + "\n"
    fd, tmp_path = tempfile.mkstemp(suffix=".jsonl", prefix=".tmp_buddy_messages_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def append_buddy_message(
    user_id: int,
    syllabus_id: int,
    *,
    role: str,
    text: str,
    source: str = "chat",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    text = str(text or "").strip()
    if not text:
        return None
    role = str(role or "").strip() or "buddy"
    source = str(source or "").strip() or "chat"
    now_ts = int(time.time())
    item = {
        "message_id": f"buddy_{now_ts}_{uuid.uuid4().hex[:8]}",
        "role": role,
        "from": "user" if role == "user" else "proactive" if source == "proactive" else "buddy",
        "text": text,
        "source": source,
        "created_at": now_ts,
        "metadata": metadata or {},
    }
    path = _message_path(user_id, syllabus_id)
    messages = _read_messages(path)
    messages.append(item)
    if len(messages) > BUDDY_MESSAGE_MAX_ITEMS:
        messages = messages[-BUDDY_MESSAGE_MAX_ITEMS:]
    _write_messages(path, messages)
    return item


def load_buddy_messages(user_id: int, syllabus_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    messages = _read_messages(_message_path(user_id, syllabus_id))
    try:
        normalized_limit = max(1, int(limit))
    except Exception:
        normalized_limit = 30
    return messages[-normalized_limit:]
