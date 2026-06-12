"""标签式自演化记忆 — jsonl 读写。

每行一条 JSON：{"tag": "...", "created_at": int, "last_referenced_at": int}
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BUDDY_MEMORY_MAX_TAGS, BUDDY_MEMORY_TAG_MAX_CHARS


def _memory_root() -> Path:
    return Path(__file__).resolve().parents[2] / "study_buddy"


def _memory_path(user_id: int, syllabus_id: int) -> Path:
    directory = _memory_root() / f"user_{user_id}" / f"syllabus_{syllabus_id}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "buddy_memory.jsonl"


def _read_tags(path: Path) -> list[dict]:
    if not path.exists():
        return []
    tags: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("tag"):
                tags.append(item)
    return tags


def _write_tags(path: Path, tags: list[dict]) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(
        json.dumps(t, ensure_ascii=False) for t in tags
    ) + "\n"
    fd, tmp_path = tempfile.mkstemp(suffix=".jsonl", prefix=".tmp_buddy_memory_", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def create_memory_tag(user_id: int, syllabus_id: int, tag: str) -> dict:
    """创建或刷新记忆标签。

    Returns: {"success": bool, "tag": str, "action": "created"|"updated", "total_tags": int}
    """
    tag = tag.strip()[:BUDDY_MEMORY_TAG_MAX_CHARS]
    if not tag:
        return {"success": False, "tag": "", "action": "empty", "total_tags": 0}

    path = _memory_path(user_id, syllabus_id)
    tags = _read_tags(path)
    now_ts = int(time.time())

    # 检查是否已存在相同文本
    for item in tags:
        if item.get("tag") == tag:
            item["last_referenced_at"] = now_ts
            _write_tags(path, tags)
            return {"success": True, "tag": tag, "action": "updated", "total_tags": len(tags)}

    # 新增
    tags.append({"tag": tag, "created_at": now_ts, "last_referenced_at": now_ts})

    # 超出上限则删最旧的
    if len(tags) > BUDDY_MEMORY_MAX_TAGS:
        tags.sort(key=lambda t: t.get("created_at", 0))
        tags = tags[-(BUDDY_MEMORY_MAX_TAGS):]

    _write_tags(path, tags)
    return {"success": True, "tag": tag, "action": "created", "total_tags": len(tags)}


def delete_memory_tag(user_id: int, syllabus_id: int, tag: str) -> dict:
    """精确删除一条记忆标签。

    Returns: {"success": bool, "tag": str, "action": "deleted"|"not_found", "total_tags": int}
    """
    tag = tag.strip()
    if not tag:
        return {"success": False, "tag": "", "action": "empty", "total_tags": 0}

    path = _memory_path(user_id, syllabus_id)
    tags = _read_tags(path)
    before = len(tags)
    tags = [t for t in tags if t.get("tag") != tag]

    if len(tags) == before:
        return {"success": True, "tag": tag, "action": "not_found", "total_tags": len(tags)}

    _write_tags(path, tags)
    return {"success": True, "tag": tag, "action": "deleted", "total_tags": len(tags)}


def load_memory_tags(user_id: int, syllabus_id: int) -> list[dict]:
    """加载全部记忆标签，按 last_referenced_at desc 排序。"""
    tags = _read_tags(_memory_path(user_id, syllabus_id))
    tags.sort(key=lambda t: t.get("last_referenced_at", 0), reverse=True)
    return tags
