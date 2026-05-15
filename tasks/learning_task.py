"""Legacy learning facade.

This module used to own the learning Q&A flow, semantic week matching, RAG
lookup, LLM competence judgement, and personal syllabus mutation. Those
responsibilities have moved to the profile/generative agents and the future
total agent.

The only runtime responsibilities kept here are page-load personal syllabus
initialization and display-oriented reads. Both delegate to
``tasks.learning_profile_task`` so there is only one personal syllabus schema.
"""

from __future__ import annotations

import warnings
from typing import Any, Optional

from repositories.user_syllabus_repo import get_user_syllabus
from tasks import learning_profile_task as profile_task


LEGACY_ASK_QUESTION_ERROR = (
    "learning_task.ask_question is deprecated. Use the total agent flow instead."
)
LEGACY_UPDATE_PERSONAL_SYLLABUS_ERROR = (
    "learning_task.update_personal_syllabus is deprecated. Personal syllabus "
    "updates should be produced by the learning profile agent or future total agent."
)


def _warn_legacy(function_name: str, replacement: str) -> None:
    warnings.warn(
        f"tasks.learning_task.{function_name} is legacy; use {replacement}.",
        DeprecationWarning,
        stacklevel=2,
    )


def _coerce_positive_ids(user_id: int, syllabus_id: int) -> Optional[tuple[int, int]]:
    try:
        normalized_user_id = int(user_id)
        normalized_syllabus_id = int(syllabus_id)
    except Exception:
        return None
    if normalized_user_id <= 0 or normalized_syllabus_id <= 0:
        return None
    return normalized_user_id, normalized_syllabus_id


def _get_personal_syllabus_path(user_id: int, syllabus_id: int) -> Optional[str]:
    try:
        relation = get_user_syllabus(user_id, syllabus_id)
    except Exception:
        return None
    path = getattr(relation, "personal_syllabus_path", None) if relation else None
    return path if isinstance(path, str) and path.strip() else None


def init_personal_syllabus(user_id: int, syllabus_id: int):
    """LEGACY FACADE: page-load initialization for display flows.

    Kept because the frontend may initialize a personal syllabus when a
    learning page opens. Existing personal syllabuses are not overwritten.
    New files are created by ``learning_profile_task.init_profile_personal_syllabus``.

    Returns:
        The personal syllabus path on success, or ``False`` on failure, matching
        the legacy API contract.
    """
    _warn_legacy(
        "init_personal_syllabus",
        "learning_profile_task.init_profile_personal_syllabus",
    )
    normalized = _coerce_positive_ids(user_id, syllabus_id)
    if normalized is None:
        return False
    user_id, syllabus_id = normalized

    existing = profile_task.read_profile_personal_syllabus(user_id, syllabus_id, hydrate=False)
    if isinstance(existing, dict):
        return _get_personal_syllabus_path(user_id, syllabus_id) or False

    created = profile_task.init_profile_personal_syllabus(user_id, syllabus_id)
    if not isinstance(created, dict):
        return False
    return created.get("personal_syllabus_path") or False


def get_personal_syllabus_detail_info(user_id: int, syllabus_id: int) -> Optional[dict]:
    """LEGACY FACADE: read the display-ready personal syllabus.

    Kept for the frontend display endpoint. If the page has not initialized the
    personal syllabus yet, this method initializes it once and then returns the
    hydrated document.
    """
    _warn_legacy(
        "get_personal_syllabus_detail_info",
        "learning_profile_task.read_profile_personal_syllabus",
    )
    normalized = _coerce_positive_ids(user_id, syllabus_id)
    if normalized is None:
        return None
    user_id, syllabus_id = normalized

    personal = profile_task.read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)
    if isinstance(personal, dict):
        return personal

    created = profile_task.init_profile_personal_syllabus(user_id, syllabus_id)
    if not isinstance(created, dict):
        return None

    personal = profile_task.read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)
    if isinstance(personal, dict):
        return personal
    fallback = created.get("personal_syllabus")
    return fallback if isinstance(fallback, dict) else None


def ask_question(user_id: int, syllabus_id: int, question: str) -> dict[str, Any]:
    """DEPRECATED: old LLM/RAG learning Q&A flow.

    The total agent will own this orchestration. This method is intentionally
    disabled so new code cannot accidentally use the legacy flow.
    """
    _warn_legacy("ask_question", "the future total agent flow")
    raise NotImplementedError(LEGACY_ASK_QUESTION_ERROR)


def update_personal_syllabus(
    user_id: int,
    syllabus_id: int,
    week_index: int,
    study_time_spent: int = -1,
    competance: str = None,
    competance_progress: int = None,
) -> dict[str, Any]:
    """DEPRECATED: old direct personal syllabus mutation flow.

    Personal syllabus updates should now come from the profile agent suggestion
    workflow, or later from the total agent. Display reads remain available via
    ``get_personal_syllabus_detail_info``.
    """
    _warn_legacy(
        "update_personal_syllabus",
        "learning_profile_task.append_profile_personal_syllabus_suggestion",
    )
    raise NotImplementedError(LEGACY_UPDATE_PERSONAL_SYLLABUS_ERROR)
