"""Study Buddy 门面 — 对外导出 task 级函数。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from tasks.study_buddy.buddy_agent import chat_with_buddy, proactive_buddy_message
from tasks.study_buddy.memory import create_memory_tag, delete_memory_tag, load_memory_tags
from tasks.study_buddy.tree import build_buddy_tree
from tasks.study_buddy.tree_store import load_buddy_tree, save_buddy_tree


def trigger_study_buddy(
    user_id: int,
    syllabus_id: int,
    plan: Optional[Dict[str, Any]] = None,
    study_graph_features: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """总 Agent 返回后触发学伴主动消息。

    Returns:
        1-3 句自然中文消息，或 None（无变化时）。
    """
    return proactive_buddy_message(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan,
        study_graph_features=study_graph_features,
    )


def buddy_chat(
    user_id: int,
    syllabus_id: int,
    message: str,
    plan: Optional[Dict[str, Any]] = None,
    study_graph_features: Optional[Dict[str, Any]] = None,
) -> dict:
    """学伴独立对话。

    Returns:
        {"reply": str, "memory_tags_written": [dict]}
    """
    return chat_with_buddy(
        user_id=user_id,
        syllabus_id=syllabus_id,
        message=message,
        plan=plan,
        study_graph_features=study_graph_features,
    )
