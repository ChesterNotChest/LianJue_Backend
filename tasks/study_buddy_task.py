"""Study Buddy 门面 — 对外导出 task 级函数。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from tasks.study_buddy.buddy_agent import (
    chat_with_buddy,
    proactive_buddy_event_message,
    proactive_buddy_message,
    synthesis_proactive_message,
)
from tasks.study_buddy.contracts import BUDDY_MESSAGE_SOURCE_SYNTHESIS, BUDDY_SYNTHESIS_CACHE_SECONDS
from tasks.study_buddy.memory import create_memory_tag, delete_memory_tag, load_memory_tags
from tasks.study_buddy.messages import append_buddy_message, load_buddy_messages
from tasks.study_buddy.tree import build_buddy_tree
from tasks.study_buddy.tree_store import load_buddy_tree, save_buddy_tree

logger = logging.getLogger(__name__)


def _service_log(level: int, message: str, *args: Any) -> None:
    logger.log(level, message, *args)
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            current_app.logger.log(level, message, *args)
    except Exception:
        pass


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
    _service_log(
        logging.INFO,
        "[study_buddy] trigger_tree_start user_id=%s syllabus_id=%s has_plan=%s has_graph_features=%s",
        user_id,
        syllabus_id,
        bool(plan),
        bool(study_graph_features),
    )
    message = proactive_buddy_message(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan,
        study_graph_features=study_graph_features,
    )
    if message:
        saved = append_buddy_message(user_id, syllabus_id, role="buddy", text=message, source="proactive")
        _service_log(
            logging.INFO,
            "[study_buddy] trigger_tree_saved user_id=%s syllabus_id=%s message_id=%s text_preview=%s",
            user_id,
            syllabus_id,
            (saved or {}).get("message_id"),
            message[:120],
        )
    else:
        _service_log(logging.INFO, "[study_buddy] trigger_tree_no_message user_id=%s syllabus_id=%s", user_id, syllabus_id)
    return message


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
    _service_log(
        logging.INFO,
        "[study_buddy] chat_start user_id=%s syllabus_id=%s message_preview=%s",
        user_id,
        syllabus_id,
        str(message or "")[:120],
    )
    result = chat_with_buddy(
        user_id=user_id,
        syllabus_id=syllabus_id,
        message=message,
        plan=plan,
        study_graph_features=study_graph_features,
    )
    user_saved = append_buddy_message(user_id, syllabus_id, role="user", text=message, source="chat")
    if result.get("reply"):
        buddy_saved = append_buddy_message(user_id, syllabus_id, role="buddy", text=result["reply"], source="chat")
        _service_log(
            logging.INFO,
            "[study_buddy] chat_saved user_id=%s syllabus_id=%s user_message_id=%s buddy_message_id=%s reply_preview=%s tags_written=%s",
            user_id,
            syllabus_id,
            (user_saved or {}).get("message_id"),
            (buddy_saved or {}).get("message_id"),
            str(result.get("reply") or "")[:120],
            result.get("memory_tags_written") or [],
        )
    else:
        _service_log(
            logging.WARNING,
            "[study_buddy] chat_empty_reply user_id=%s syllabus_id=%s user_message_id=%s result_keys=%s",
            user_id,
            syllabus_id,
            (user_saved or {}).get("message_id"),
            list(result.keys()) if isinstance(result, dict) else type(result).__name__,
        )
    return result


def notify_study_buddy_event(
    user_id: int,
    syllabus_id: int,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    study_graph_features: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    _service_log(
        logging.INFO,
        "[study_buddy] event_start user_id=%s syllabus_id=%s event_type=%s payload=%s has_plan=%s has_graph_features=%s",
        user_id,
        syllabus_id,
        event_type,
        payload or {},
        bool(plan),
        bool(study_graph_features),
    )
    message = proactive_buddy_event_message(
        user_id=user_id,
        syllabus_id=syllabus_id,
        event_type=event_type,
        payload=payload or {},
        plan=plan,
        study_graph_features=study_graph_features,
    )
    if message:
        saved = append_buddy_message(
            user_id,
            syllabus_id,
            role="buddy",
            text=message,
            source="event",
            metadata={"event_type": event_type, "payload": payload or {}},
        )
        _service_log(
            logging.INFO,
            "[study_buddy] event_saved user_id=%s syllabus_id=%s event_type=%s message_id=%s text_preview=%s",
            user_id,
            syllabus_id,
            event_type,
            (saved or {}).get("message_id"),
            message[:120],
        )
    else:
        _service_log(
            logging.INFO,
            "[study_buddy] event_no_message user_id=%s syllabus_id=%s event_type=%s",
            user_id,
            syllabus_id,
            event_type,
        )
    return message


def list_buddy_messages(user_id: int, syllabus_id: int, limit: int = 30) -> list[dict]:
    messages = load_buddy_messages(user_id, syllabus_id, limit=limit)
    _service_log(
        logging.INFO,
        "[study_buddy] list_messages user_id=%s syllabus_id=%s limit=%s count=%s",
        user_id,
        syllabus_id,
        limit,
        len(messages),
    )
    return messages


# ── synthesis cache ──────────────────────────────────────────────
_synthesis_cache: dict[str, tuple[float, str | None]] = {}


def generate_buddy_synthesis(
    user_id: int,
    syllabus_id: int,
    plan: dict | None = None,
    study_graph_features: dict | None = None,
    force: bool = False,
) -> dict:
    """生成学伴综合建议，带缓存。

    Returns:
        {"synthesis": str | None, "cached": bool}
    """
    import time

    cache_key = f"{user_id}_{syllabus_id}"
    now = time.time()

    if not force:
        cached = _synthesis_cache.get(cache_key)
        if cached and (now - cached[0]) < BUDDY_SYNTHESIS_CACHE_SECONDS:
            _service_log(
                logging.INFO,
                "[study_buddy] synthesis_cache_hit user_id=%s syllabus_id=%s age_secs=%s",
                user_id,
                syllabus_id,
                int(now - cached[0]),
            )
            return {"synthesis": cached[1], "cached": True}

    # Check if there's a recent synthesis message in history
    if not force:
        recent = load_buddy_messages(user_id, syllabus_id, limit=10)
        for msg in reversed(recent):
            if msg.get("source") == BUDDY_MESSAGE_SOURCE_SYNTHESIS:
                created = msg.get("created_at", 0)
                if isinstance(created, (int, float)) and (now - created) < BUDDY_SYNTHESIS_CACHE_SECONDS:
                    _synthesis_cache[cache_key] = (now, msg.get("text", ""))
                    return {"synthesis": msg.get("text", ""), "cached": True}

    _service_log(
        logging.INFO,
        "[study_buddy] synthesis_generate_start user_id=%s syllabus_id=%s",
        user_id,
        syllabus_id,
    )
    text = synthesis_proactive_message(
        user_id=user_id,
        syllabus_id=syllabus_id,
        plan=plan,
        study_graph_features=study_graph_features,
    )

    # Persist as a buddy message
    if text:
        saved = append_buddy_message(
            user_id,
            syllabus_id,
            role="buddy",
            text=text,
            source=BUDDY_MESSAGE_SOURCE_SYNTHESIS,
        )
        _service_log(
            logging.INFO,
            "[study_buddy] synthesis_saved user_id=%s syllabus_id=%s message_id=%s text_preview=%s",
            user_id,
            syllabus_id,
            (saved or {}).get("message_id"),
            text[:120],
        )
    else:
        _service_log(
            logging.INFO,
            "[study_buddy] synthesis_empty user_id=%s syllabus_id=%s",
            user_id,
            syllabus_id,
        )

    _synthesis_cache[cache_key] = (now, text)
    return {"synthesis": text, "cached": False}
