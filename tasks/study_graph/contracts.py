import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from constant import BasePath


STUDY_GRAPH_MANIFEST_VERSION = 1
STUDY_GRAPH_LOW_CONFIDENCE_THRESHOLD = 0.45
STUDY_GRAPH_DEFAULT_ROOT_ID_PREFIX = "study_tree_root"
STUDY_GRAPH_TREE_ID_PREFIX = "study_tree"
STUDY_GRAPH_NODE_ID_PREFIX = "knowledge"
STUDY_GRAPH_DEFAULT_ROOT_TITLE_SUFFIX = "学习成长树"
STUDY_GRAPH_TITLE_STOP_SUFFIXES = ["问题", "知识点", "概念", "内容"]
STUDY_GRAPH_MAX_CONTEXT_CANDIDATES = 8

COURSE_TREE_SUMMARY_DEFAULT_LIMIT = 20
COURSE_TREE_SUMMARY_MIN_GROUP_SIZE = 5
COURSE_TREE_NODE_MIN_SAMPLE_SIZE = 3

STUDY_GRAPH_SIGNAL_DEFAULT_DELTA = {
    "learned": 0.15,
    "practiced": 0.08,
    "struggled": -0.12,
    "mastered": 0.25,
}
STUDY_GRAPH_DELTA_MIN = -0.3
STUDY_GRAPH_DELTA_MAX = 0.3


@dataclass(frozen=True)
class StudyGraphBuildContext:
    user_id: int
    syllabus_id: int
    subject_title: Optional[str]
    title: Optional[str]
    now_ts: int


def _normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive integer") from None
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def study_graph_root() -> Path:
    return _backend_root() / BasePath.STUDY_GRAPH_ROOT.value.lstrip("/")


def build_tree_id(user_id: int, syllabus_id: int) -> str:
    return f"{STUDY_GRAPH_TREE_ID_PREFIX}:{_normalize_positive_int(user_id, 'user_id')}:{_normalize_positive_int(syllabus_id, 'syllabus_id')}"


def build_root_node_id(user_id: int, syllabus_id: int) -> str:
    return f"{STUDY_GRAPH_DEFAULT_ROOT_ID_PREFIX}:{_normalize_positive_int(user_id, 'user_id')}:{_normalize_positive_int(syllabus_id, 'syllabus_id')}"


def _truncate_with_hash(value: str, max_len: int = 64) -> str:
    normalized = str(value or "").strip()
    if len(normalized) <= max_len:
        return normalized
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{normalized[: max_len - 9]}-{digest}"


def build_knowledge_node_id(user_id: int, syllabus_id: int, normalized_title: str) -> str:
    normalized = str(normalized_title or "").strip()
    if not normalized:
        raise ValueError("normalized_title is required")
    if not re.fullmatch(r"[a-z0-9_-]+", normalized):
        raise ValueError("normalized_title must contain only lowercase letters, digits, underscore or hyphen")
    cleaned = _truncate_with_hash(normalized)
    return f"{STUDY_GRAPH_NODE_ID_PREFIX}:{_normalize_positive_int(user_id, 'user_id')}:{_normalize_positive_int(syllabus_id, 'syllabus_id')}:{cleaned}"


def build_virtual_root_node(user_id: int, syllabus_id: int, subject_title: str | None, now_ts: int) -> dict:
    title = str(subject_title or "").strip() or STUDY_GRAPH_DEFAULT_ROOT_TITLE_SUFFIX
    return {
        "node_id": build_root_node_id(user_id, syllabus_id),
        "tree_id": build_tree_id(user_id, syllabus_id),
        "type": "tree_root",
        "title": title,
        "virtual": True,
        "created_at": int(now_ts),
        "updated_at": int(now_ts),
    }


def _default_tree_title(subject_title: str | None, title: str | None) -> str:
    subject = str(subject_title or "").strip()
    if subject:
        return f"{subject}{STUDY_GRAPH_DEFAULT_ROOT_TITLE_SUFFIX}"
    fallback = str(title or "").strip()
    if fallback:
        return fallback
    return STUDY_GRAPH_DEFAULT_ROOT_TITLE_SUFFIX


def make_empty_tree(user_id: int, syllabus_id: int, title: str | None, now_ts: int, subject_title: str | None = None) -> dict:
    user_id = _normalize_positive_int(user_id, "user_id")
    syllabus_id = _normalize_positive_int(syllabus_id, "syllabus_id")
    tree_id = build_tree_id(user_id, syllabus_id)
    resolved_subject = str(subject_title or "").strip() or (str(title or "").strip() if title else "")
    resolved_title = _default_tree_title(resolved_subject, title)
    return {
        "schema_version": STUDY_GRAPH_MANIFEST_VERSION,
        "tree_id": tree_id,
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "subject_title": resolved_subject or None,
        "title": resolved_title,
        "virtual_root": build_virtual_root_node(user_id, syllabus_id, resolved_subject or title, now_ts),
        "nodes": [],
        "edges": [],
        "summary": {
            "learned_node_count": 0,
            "mastered_node_count": 0,
            "weak_node_count": 0,
            "tree_growth": 0.0,
            "last_updated_at": int(now_ts),
        },
        "created_at": int(now_ts),
        "updated_at": int(now_ts),
    }


def score_to_mastery_label(score: float) -> str:
    try:
        normalized = float(score)
    except Exception:
        normalized = 0.0
    if normalized < 0.40:
        return "weak"
    if normalized < 0.60:
        return "learning"
    if normalized < 0.80:
        return "normal"
    return "mastered"


def build_client_change_id(
    user_id: int,
    syllabus_id: int,
    source_kind: str,
    op: str,
    normalized_title: str,
    evidence_key: str | None,
) -> str:
    user_id = _normalize_positive_int(user_id, "user_id")
    syllabus_id = _normalize_positive_int(syllabus_id, "syllabus_id")
    source_kind = str(source_kind or "").strip() or "student"
    op = str(op or "").strip()
    normalized_title = str(normalized_title or "").strip()
    if not op or not normalized_title:
        raise ValueError("op and normalized_title are required")
    stable_evidence = str(evidence_key or "").strip()
    if not stable_evidence:
        stable_evidence = f"{source_kind}:{op}:{normalized_title}"
    digest = hashlib.sha1(stable_evidence.encode("utf-8")).hexdigest()[:8]
    return f"{source_kind}:{user_id}:{syllabus_id}:{op}:{normalized_title}:{digest}"

