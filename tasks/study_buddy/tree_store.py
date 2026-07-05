"""学习进度树持久化 — 原子 JSON 读写，v2 schema。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .contracts import BUDDY_TREE_FILENAME, BUDDY_TREE_SCHEMA_VERSION


def _buddy_root() -> Path:
    return Path(__file__).resolve().parents[2] / "study_buddy"


def _tree_dir(user_id: int, syllabus_id: int) -> Path:
    return _buddy_root() / f"user_{user_id}" / f"syllabus_{syllabus_id}"


def _tree_path(user_id: int, syllabus_id: int) -> Path:
    return _tree_dir(user_id, syllabus_id) / BUDDY_TREE_FILENAME


def save_buddy_tree(user_id: int, syllabus_id: int, tree: dict) -> str:
    """原子写入树 JSON（v2 schema），返回文件路径。"""
    directory = _tree_dir(user_id, syllabus_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = _tree_path(user_id, syllabus_id)
    payload = json.dumps(tree, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix=".tmp_buddy_tree_", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, str(target))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return str(target)


def load_buddy_tree(user_id: int, syllabus_id: int) -> Optional[dict]:
    """读取树 JSON。v1 schema 返回 None（触发重建）。"""
    target = _tree_path(user_id, syllabus_id)
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    # v1 schema 没有 "nodes" dict——重建
    if not isinstance(data.get("nodes"), dict):
        return None
    if data.get("schema_version") != BUDDY_TREE_SCHEMA_VERSION:
        return None
    return data
