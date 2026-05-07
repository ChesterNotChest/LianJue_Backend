from __future__ import annotations

import copy
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple, Union


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "experiments" / "user_analize" / "samples"
OUTPUTS_DIR = REPO_ROOT / "experiments" / "user_analize" / "outputs"

COURSE_TERMS = (
    "hdfs",
    "namenode",
    "datanode",
    "hbase",
    "nosql",
    "etl",
    "apriori",
    "mapreduce",
    "spark",
    "gpu",
    "tpu",
    "fpga",
    "差分隐私",
    "隐私保护",
    "可视化",
    "特征选择",
    "关联规则",
    "频繁项集",
    "列式存储",
)
HELP_WORDS = ("帮我", "能不能", "推荐", "顺便", "告诉我", "给我", "怎么", "如何", "顺序", "材料", "案例", "例题")
DIFFICULTY_WORDS = ("不会", "忘记", "卡住", "看不懂", "有点慌", "困难", "难", "混", "薄弱", "失分")
NEGATIVE_WORDS = ("慌", "急", "焦虑", "忘记", "不会", "挂", "难", "卡住", "紧", "怕", "失分")
POSITIVE_WORDS = ("掌握", "清楚", "稳定", "想", "可以", "完成", "提升")
GOAL_WORDS = ("掌握", "复习", "提到", "完成", "冲刺", "补回来", "串起来")
TIME_PATTERNS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d")
LEARNING_EVENT_TYPES = {
    "study_session",
    "video_watch",
    "practice_set",
    "summary_review",
    "flashcard_review",
    "note_view",
    "resource_scan",
    "mock_exam",
    "diagram_review",
    "quiz_review",
    "case_reading",
}
RESOURCE_CATEGORY_MAP = {
    "video": "video",
    "slide": "video",
    "infographic": "video",
    "quiz": "practice",
    "worksheet": "practice",
    "mock_exam": "practice",
    "summary_note": "text_summary",
    "pdf": "text_summary",
    "cheatsheet": "text_summary",
    "outline": "text_summary",
    "mindmap": "text_summary",
    "case_gallery": "case_study",
    "case_study": "case_study",
    "remedial_note": "remedial_notes",
}
COMPETANCE_SCORE_MAP = {
    "none": 0.1,
    "weak": 0.35,
    "normal": 0.65,
    "master": 0.85,
}


def resolve_repo_path(path_value: Union[str, Path]) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def load_json_file(path_value: Union[str, Path]) -> Any:
    return json.loads(resolve_repo_path(path_value).read_text(encoding="utf-8"))


def write_json_file(path_value: Union[str, Path], payload: Any) -> None:
    path = resolve_repo_path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _unique_preserve(values: Iterable[Any]) -> List[Any]:
    seen = set()
    ordered = []
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
        if marker in seen:
            continue
        seen.add(marker)
        ordered.append(value)
    return ordered


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        texts: List[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                item_text = item.strip()
                if item_text:
                    texts.append(item_text)
            else:
                item_text = str(item).strip()
                if item_text:
                    texts.append(item_text)
        return texts
    text = str(value).strip()
    return [text] if text else []


def _parse_timestamp(value: Any) -> Tuple[Optional[int], Optional[str]]:
    if value is None or value == "":
        return None, "missing_timestamp"
    if isinstance(value, (int, float)):
        return int(value), None
    text = str(value).strip()
    if not text:
        return None, "missing_timestamp"
    if text.isdigit():
        return int(text), None
    iso_text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp()), None
    except ValueError:
        pass
    for pattern in TIME_PATTERNS:
        try:
            dt = datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
            return int(dt.timestamp()), None
        except ValueError:
            continue
    return None, f"unrecognized_timestamp:{text}"


def _label_from_score(score: float, thresholds: Sequence[Tuple[float, str]], default: str) -> str:
    for boundary, label in thresholds:
        if score <= boundary:
            return label
    return default


def _level_bucket(score: float) -> str:
    if score < 0.34:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


def _extract_keywords_from_text(texts: Sequence[str]) -> List[str]:
    merged = " ".join(texts).lower()
    return [term for term in COURSE_TERMS if term in merged]


def normalize_learning_profile_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    request = dict(payload or {})
    missing_fields: List[str] = []
    format_issues: List[str] = []

    user_id = _to_int(request.get("user_id"))
    if user_id is None:
        missing_fields.append("user_id")

    syllabus_id = _to_int(request.get("syllabus_id", request.get("syllabusId")))
    dialogue_text = _normalize_text_list(request.get("dialogue_text", request.get("dialogueText")))
    learning_goal = request.get("learning_goal", request.get("learningGoal"))
    learning_goal = str(learning_goal).strip() if learning_goal is not None and str(learning_goal).strip() else None
    if not learning_goal:
        missing_fields.append("learning_goal")

    learning_records = request.get("learning_records", request.get("learningRecords")) or []
    answer_records = request.get("answer_records", request.get("answerRecords")) or []
    resource_usage = request.get("resource_usage", request.get("resourceUsage")) or []

    if not isinstance(learning_records, list):
        format_issues.append("learning_records_not_list")
        learning_records = [learning_records]
    if not isinstance(answer_records, list):
        format_issues.append("answer_records_not_list")
        answer_records = [answer_records]
    if not isinstance(resource_usage, list):
        format_issues.append("resource_usage_not_list")
        resource_usage = [resource_usage]

    if not dialogue_text:
        missing_fields.append("dialogue_text")
    if not learning_records:
        missing_fields.append("learning_records")
    if not answer_records:
        missing_fields.append("answer_records")
    if not resource_usage:
        missing_fields.append("resource_usage")

    return {
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "dialogue_text": dialogue_text,
        "learning_goal": learning_goal,
        "learning_records": learning_records,
        "answer_records": answer_records,
        "resource_usage": resource_usage,
        "missing_fields": _unique_preserve(missing_fields),
        "format_issues": _unique_preserve(format_issues),
    }


def normalize_dialogue_events(dialogue_text: Sequence[str], learning_goal: Optional[str]) -> Dict[str, Any]:
    events = []
    for index, text in enumerate(_normalize_text_list(dialogue_text)):
        events.append(
            {
                "source": "dialogue_text",
                "event_type": "dialogue",
                "timestamp": None,
                "duration_minutes": None,
                "texts": [text],
                "knowledge_points": _extract_keywords_from_text([text]),
                "action": "ask",
                "sequence": index,
            }
        )
    if learning_goal:
        events.append(
            {
                "source": "dialogue_text",
                "event_type": "learning_goal",
                "timestamp": None,
                "duration_minutes": None,
                "texts": [learning_goal],
                "knowledge_points": _extract_keywords_from_text([learning_goal]),
                "action": "goal",
                "sequence": len(events),
            }
        )
    return {
        "events": events,
        "question_text_count": len(_normalize_text_list(dialogue_text)),
        "missing_fields": [],
        "format_issues": [],
    }


def normalize_history_events(history_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    events = []
    format_issues: List[str] = []
    for row in history_rows or []:
        timestamp, issue = _parse_timestamp(row.get("timestamp"))
        if issue and not issue.startswith("missing"):
            format_issues.append(issue)
        question = str(row.get("question", "")).strip()
        answer = str(row.get("answer", "")).strip()
        texts = [item for item in (question, answer) if item]
        if not texts:
            continue
        events.append(
            {
                "source": "history",
                "event_type": "history",
                "timestamp": timestamp,
                "duration_minutes": None,
                "texts": texts,
                "knowledge_points": _extract_keywords_from_text(texts),
                "action": "history_window",
            }
        )
    return {
        "events": events,
        "missing_fields": [],
        "format_issues": _unique_preserve(format_issues),
    }


def normalize_learning_records(learning_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    events = []
    format_issues: List[str] = []
    missing_fields: List[str] = []
    for index, record in enumerate(learning_records or []):
        event_type = str(record.get("event_type", "")).strip()
        if not event_type:
            missing_fields.append(f"learning_records[{index}].event_type")
            event_type = "unknown"
        elif event_type not in LEARNING_EVENT_TYPES:
            format_issues.append(f"unknown_event_type:{event_type}")
        timestamp, ts_issue = _parse_timestamp(record.get("started_at"))
        if ts_issue:
            format_issues.append(ts_issue)
        duration_minutes = _to_float(record.get("duration_minutes"), 0.0)
        meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
        topic = str(meta.get("topic", "")).strip()
        knowledge_points = meta.get("knowledge_points") if isinstance(meta.get("knowledge_points"), list) else []
        if topic and not knowledge_points:
            knowledge_points = [topic]
        events.append(
            {
                "source": "learning_records",
                "event_type": event_type,
                "timestamp": timestamp,
                "duration_minutes": duration_minutes,
                "texts": [topic] if topic else [],
                "knowledge_points": _normalize_text_list(knowledge_points),
                "action": event_type,
                "source_client": record.get("source"),
                "meta": meta,
            }
        )
    return {
        "events": events,
        "missing_fields": _unique_preserve(missing_fields),
        "format_issues": _unique_preserve(format_issues),
    }


def normalize_answer_records(answer_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    events = []
    format_issues: List[str] = []
    missing_fields: List[str] = []
    for index, record in enumerate(answer_records or []):
        timestamp, ts_issue = _parse_timestamp(record.get("answered_at"))
        if ts_issue:
            format_issues.append(ts_issue)
        meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
        knowledge_points = record.get("knowledge_points")
        if not isinstance(knowledge_points, list):
            knowledge_points = meta.get("knowledge_points")
        if not isinstance(knowledge_points, list) or not knowledge_points:
            missing_fields.append(f"answer_records[{index}].knowledge_points")
            knowledge_points = []
        events.append(
            {
                "source": "answer_records",
                "event_type": "answer",
                "timestamp": timestamp,
                "duration_minutes": _to_float(record.get("time_spent_seconds"), 0.0) / 60.0,
                "texts": [str(record.get("question_id", "")).strip()] if record.get("question_id") is not None else [],
                "knowledge_points": _normalize_text_list(knowledge_points),
                "action": "answer",
                "question_id": record.get("question_id"),
                "correct": bool(record.get("correct")),
                "score": _clip(_to_float(record.get("score"), 0.0)),
                "time_spent_seconds": _to_float(record.get("time_spent_seconds"), 0.0),
                "meta": meta,
            }
        )
    return {
        "events": events,
        "missing_fields": _unique_preserve(missing_fields),
        "format_issues": _unique_preserve(format_issues),
    }


def normalize_resource_usage(resource_usage: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    events = []
    format_issues: List[str] = []
    missing_fields: List[str] = []
    for index, record in enumerate(resource_usage or []):
        timestamp, ts_issue = _parse_timestamp(record.get("timestamp"))
        if ts_issue:
            format_issues.append(ts_issue)
        action = str(record.get("action", "")).strip()
        if not action:
            missing_fields.append(f"resource_usage[{index}].action")
        meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
        knowledge_points = meta.get("knowledge_points") if isinstance(meta.get("knowledge_points"), list) else []
        topic = str(meta.get("topic", "")).strip()
        resource_type = str(meta.get("resource_type", "")).strip()
        if topic and not knowledge_points:
            knowledge_points = [topic]
        events.append(
            {
                "source": "resource_usage",
                "event_type": "resource",
                "timestamp": timestamp,
                "duration_minutes": _to_float(record.get("duration_seconds"), 0.0) / 60.0,
                "texts": [topic] if topic else [],
                "knowledge_points": _normalize_text_list(knowledge_points),
                "action": action or "unknown",
                "resource_id": record.get("resource_id"),
                "resource_type": resource_type,
                "meta": meta,
            }
        )
    return {
        "events": events,
        "missing_fields": _unique_preserve(missing_fields),
        "format_issues": _unique_preserve(format_issues),
    }


def merge_profile_events(*normalized_groups: Dict[str, Any]) -> Dict[str, Any]:
    events = []
    missing_fields: List[str] = []
    format_issues: List[str] = []
    for group in normalized_groups:
        events.extend(group.get("events", []))
        missing_fields.extend(group.get("missing_fields", []))
        format_issues.extend(group.get("format_issues", []))
    events.sort(key=lambda item: (item.get("timestamp") is None, item.get("timestamp") or 0, item.get("source", "")))
    return {
        "events": events,
        "missing_fields": _unique_preserve(missing_fields),
        "format_issues": _unique_preserve(format_issues),
        "source_events": _unique_preserve(item.get("source") for item in events if item.get("source")),
    }


def compute_dialogue_features(dialogue_events: Sequence[Dict[str, Any]], learning_goal: Optional[str]) -> Dict[str, Any]:
    texts: List[str] = []
    for event in dialogue_events:
        texts.extend(event.get("texts", []))
    merged = " ".join(texts)
    lowered = merged.lower()
    term_hits = _unique_preserve(_extract_keywords_from_text(texts))
    help_hits = sum(1 for word in HELP_WORDS if word in merged)
    difficulty_hits = sum(1 for word in DIFFICULTY_WORDS if word in merged)
    negative_hits = sum(1 for word in NEGATIVE_WORDS if word in merged)
    positive_hits = sum(1 for word in POSITIVE_WORDS if word in merged)
    goal_hits = sum(1 for word in GOAL_WORDS if word in merged)
    explicit_deadline = bool(re.search(r"(\d+\s*(天|周)|下次|本周|测验前|小测前|两天内)", merged))
    explicit_metric = bool(re.search(r"\d+\s*%|\d+\s*分", merged))

    goal_score = 0.0
    if learning_goal:
        goal_score += 0.3
    if explicit_deadline:
        goal_score += 0.25
    if explicit_metric:
        goal_score += 0.2
    if goal_hits > 0:
        goal_score += 0.15
    if len(texts) >= 2:
        goal_score += 0.1
    goal_score = _clip(goal_score)

    term_score = _clip(len(term_hits) / 5.0)
    help_score = _clip(0.15 + help_hits * 0.2 if texts else 0.0)
    difficulty_score = _clip(difficulty_hits * 0.2 + negative_hits * 0.08)

    if "冲刺" in merged or "只剩" in merged or "时间太紧" in merged:
        emotion_label = "tense"
    elif negative_hits >= 2:
        emotion_label = "frustrated"
    elif negative_hits == 1:
        emotion_label = "anxious"
    elif positive_hits >= 2:
        emotion_label = "positive"
    elif goal_score >= 0.7 and negative_hits == 0:
        emotion_label = "calm"
    else:
        emotion_label = "neutral"

    answer_pattern = "conceptual"
    if "例题" in merged or "做题" in merged or "习题" in merged:
        answer_pattern = "practice-seeking"
    if "案例" in merged or "例子" in merged:
        answer_pattern = "example-seeking"

    deadline = None
    if explicit_deadline:
        match = re.search(r"(\d+\s*(天|周))", merged)
        deadline = match.group(1) if match else "upcoming_assessment"

    return {
        "goal_clarity": {
            "level": _label_from_score(goal_score, ((0.34, "low"), (0.67, "medium")), "high"),
            "score": round(goal_score, 4),
            "confidence": round(_clip(0.4 + min(len(texts), 4) * 0.1), 4),
        },
        "term_familiarity": {
            "level": _label_from_score(term_score, ((0.25, "low"), (0.65, "medium")), "high"),
            "score": round(term_score, 4),
            "confidence": round(_clip(0.35 + len(term_hits) * 0.08), 4),
        },
        "help_seeking_level": {
            "level": _label_from_score(help_score, ((0.25, "low"), (0.55, "medium")), "high"),
            "score": round(help_score, 4),
        },
        "self_reported_difficulty": {
            "level": _label_from_score(difficulty_score, ((0.25, "low"), (0.55, "medium")), "high"),
            "score": round(difficulty_score, 4),
        },
        "emotion_state": {
            "label": emotion_label,
            "negative_hits": negative_hits,
            "positive_hits": positive_hits,
        },
        "answer_pattern": answer_pattern,
        "deadline": deadline,
        "question_text_count": len(texts),
        "term_hits": term_hits,
    }


def compute_behavior_features(
    learning_events: Sequence[Dict[str, Any]],
    resource_events: Sequence[Dict[str, Any]],
    reference_ts: Optional[int] = None,
) -> Dict[str, Any]:
    all_events = [event for event in list(learning_events) + list(resource_events) if event.get("timestamp") is not None]
    if reference_ts is None:
        reference_ts = max((event["timestamp"] for event in all_events), default=_now_ts())
    seven_days = reference_ts - 7 * 24 * 3600
    thirty_days = reference_ts - 30 * 24 * 3600

    learning_with_ts = [event for event in learning_events if event.get("timestamp") is not None]
    day_values = [datetime.fromtimestamp(event["timestamp"], tz=timezone.utc).date().isoformat() for event in all_events]
    unique_days = sorted(set(day_values))
    active_days_7d = len(
        {
            datetime.fromtimestamp(event["timestamp"], tz=timezone.utc).date().isoformat()
            for event in all_events
            if event["timestamp"] >= seven_days
        }
    )
    active_days_30d = len(
        {
            datetime.fromtimestamp(event["timestamp"], tz=timezone.utc).date().isoformat()
            for event in all_events
            if event["timestamp"] >= thirty_days
        }
    )
    durations = [event.get("duration_minutes", 0.0) for event in learning_with_ts if event.get("duration_minutes") is not None]
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    if active_days_7d == 0:
        study_frequency = "none"
    elif active_days_7d <= 2:
        study_frequency = "low"
    elif active_days_7d <= 4:
        study_frequency = "medium"
    else:
        study_frequency = "high"

    if avg_duration <= 0:
        study_duration = "unknown"
    elif avg_duration < 15:
        study_duration = "short"
    elif avg_duration < 45:
        study_duration = "medium"
    else:
        study_duration = "long"

    if len(unique_days) <= 1 and len(all_events) >= 4:
        attention_pattern = "bursty"
    elif len(unique_days) >= 3 and len(all_events) >= 4:
        attention_pattern = "stable"
    else:
        attention_pattern = "sporadic"

    if avg_duration >= 60 or study_frequency == "high":
        difficulty_tolerance = "high"
    elif avg_duration >= 25 or study_frequency == "medium":
        difficulty_tolerance = "medium"
    else:
        difficulty_tolerance = "low"

    engagement_score = _clip(
        active_days_7d * 0.12
        + active_days_30d * 0.03
        + min(avg_duration, 90.0) / 180.0
    )

    return {
        "study_frequency": study_frequency,
        "study_duration": study_duration,
        "attention_pattern": attention_pattern,
        "difficulty_tolerance": difficulty_tolerance,
        "engagement_score": round(engagement_score, 4),
        "signals": {
            "learning_record_count": len(learning_events),
            "resource_event_count": len(resource_events),
            "active_days_7d": active_days_7d,
            "active_days_30d": active_days_30d,
            "avg_duration_minutes": round(avg_duration, 2),
        },
    }


def compute_resource_preference_features(
    resource_events: Sequence[Dict[str, Any]],
    learning_events: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    category_counter: Counter = Counter()
    category_duration: DefaultDict[str, float] = defaultdict(float)
    completion_events = 0

    for event in resource_events:
        category = RESOURCE_CATEGORY_MAP.get(event.get("resource_type"), None)
        if category is None and event.get("resource_type"):
            category = "text_summary"
        if category:
            category_counter[category] += 1
            category_duration[category] += _to_float(event.get("duration_minutes"), 0.0)
        if event.get("action") in {"complete", "submit", "repeat_view"}:
            completion_events += 1

    # Learning-side practice is also a useful signal.
    practice_boost = sum(1 for event in learning_events if event.get("event_type") in {"practice_set", "mock_exam", "quiz_review"})
    if practice_boost:
        category_counter["practice"] += practice_boost

    ranked = sorted(
        category_counter.keys(),
        key=lambda key: (category_counter[key], category_duration.get(key, 0.0)),
        reverse=True,
    )
    resource_preference = ranked[:2] if ranked else []

    dominant = ranked[0] if ranked else None
    if dominant == "video":
        learning_style = "visual-driven"
    elif dominant == "practice":
        learning_style = "practice-driven"
    elif dominant == "case_study":
        learning_style = "case-driven"
    elif dominant == "remedial_notes":
        learning_style = "support-seeking"
    elif dominant == "text_summary":
        learning_style = "text-driven"
    else:
        learning_style = "mixed"

    total_resource_events = len(resource_events)
    completion_rate = round(completion_events / total_resource_events, 4) if total_resource_events else 0.0
    return {
        "resource_preference": resource_preference,
        "learning_style": learning_style,
        "resource_completion_rate": completion_rate,
        "resource_category_counts": dict(category_counter),
    }


def compute_answer_mastery_features(
    answer_events: Sequence[Dict[str, Any]],
    reference_ts: Optional[int] = None,
) -> Dict[str, Any]:
    if reference_ts is None:
        reference_ts = max((event.get("timestamp") or 0 for event in answer_events), default=_now_ts())

    aggregated_scores: DefaultDict[str, float] = defaultdict(float)
    aggregated_weights: DefaultDict[str, float] = defaultdict(float)
    attempts: DefaultDict[str, int] = defaultdict(int)
    raw_time_spent: List[float] = []
    raw_score_values: List[float] = []

    for event in answer_events:
        timestamp = event.get("timestamp")
        age_days = 0.0 if timestamp is None else max(reference_ts - timestamp, 0) / 86400.0
        if age_days <= 7:
            weight = 1.0
        elif age_days <= 30:
            weight = 0.75
        else:
            weight = 0.5
        score = _clip(_to_float(event.get("score"), 0.0))
        raw_score_values.append(score)
        raw_time_spent.append(_to_float(event.get("time_spent_seconds"), 0.0))
        for knowledge_point in event.get("knowledge_points", []):
            aggregated_scores[knowledge_point] += score * weight
            aggregated_weights[knowledge_point] += weight
            attempts[knowledge_point] += 1

    by_knowledge_point: Dict[str, float] = {}
    details: Dict[str, Any] = {}
    concept_gaps: List[str] = []
    for knowledge_point in sorted(aggregated_scores.keys()):
        score = aggregated_scores[knowledge_point] / aggregated_weights[knowledge_point]
        by_knowledge_point[knowledge_point] = round(score, 4)
        level = "low" if score < 0.45 else "medium" if score < 0.75 else "high"
        details[knowledge_point] = {
            "score": round(score, 4),
            "confidence": round(_clip(0.35 + attempts[knowledge_point] * 0.12), 4),
            "attempt_count": attempts[knowledge_point],
            "level": level,
        }
        if score < 0.45:
            concept_gaps.append(knowledge_point)

    answer_score = round(sum(by_knowledge_point.values()) / len(by_knowledge_point), 4) if by_knowledge_point else 0.0
    avg_time_spent = sum(raw_time_spent) / len(raw_time_spent) if raw_time_spent else 0.0
    avg_raw_score = sum(raw_score_values) / len(raw_score_values) if raw_score_values else 0.0

    if avg_raw_score >= 0.75 and avg_time_spent <= 70:
        answer_pattern = "efficient-and-accurate"
    elif avg_raw_score < 0.45 and avg_time_spent >= 100:
        answer_pattern = "careful-but-uncertain"
    elif avg_raw_score < 0.45:
        answer_pattern = "guessing-or-unstable"
    else:
        answer_pattern = "mixed"

    return {
        "answer_score": answer_score,
        "by_knowledge_point": by_knowledge_point,
        "knowledge_point_details": details,
        "concept_gaps": concept_gaps,
        "answer_pattern": answer_pattern,
        "attempt_count": len(answer_events),
    }


def compute_syllabus_mastery_features(personal_syllabus: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    period = list((personal_syllabus or {}).get("period", []) or [])
    if not period:
        return {
            "syllabus_score": 0.0,
            "week_items": [],
            "mastered_weeks": [],
            "weak_weeks": [],
            "review_count": 0,
        }

    week_items = []
    scores: List[float] = []
    mastered_weeks: List[int] = []
    weak_weeks: List[int] = []
    weak_topics: List[str] = []

    for entry in period:
        competance = str(entry.get("competance", "none"))
        base_score = COMPETANCE_SCORE_MAP.get(competance, 0.1)
        progress = _to_int(entry.get("competance_progress"), 0) or 0
        score = _clip(base_score + (progress / 5.0) * 0.12)
        week_index = _to_int(entry.get("week_index"), None)
        if week_index is None:
            week_index = entry.get("week_index")
        item = {
            "week_index": week_index,
            "competance": competance,
            "competance_progress": progress,
            "score": round(score, 4),
            "content": entry.get("content", ""),
        }
        week_items.append(item)
        scores.append(score)
        if score >= 0.78 and isinstance(week_index, int):
            mastered_weeks.append(week_index)
        if score < 0.45:
            if isinstance(week_index, int):
                weak_weeks.append(week_index)
            if entry.get("content"):
                weak_topics.append(entry["content"])

    return {
        "syllabus_score": round(sum(scores) / len(scores), 4),
        "week_items": week_items,
        "mastered_weeks": mastered_weeks,
        "weak_weeks": weak_weeks,
        "weak_topics": weak_topics,
        "review_count": _to_int((personal_syllabus or {}).get("review_count"), 0) or 0,
    }


def compute_risk_features(
    dialogue_features: Dict[str, Any],
    behavior_features: Dict[str, Any],
    answer_features: Dict[str, Any],
    syllabus_features: Dict[str, Any],
) -> Dict[str, Any]:
    risk_score = 0.45
    recent_anomaly: List[str] = []

    freq = behavior_features.get("study_frequency")
    if freq == "none":
        risk_score += 0.28
        recent_anomaly.append("inactive_recently")
    elif freq == "low":
        risk_score += 0.12

    if behavior_features.get("attention_pattern") == "bursty":
        risk_score += 0.08
        recent_anomaly.append("cramming_pattern")

    emotion_label = dialogue_features.get("emotion_state", {}).get("label")
    if emotion_label in {"frustrated", "anxious", "tense"}:
        risk_score += 0.12
        recent_anomaly.append("frustration_signal")

    answer_score = answer_features.get("answer_score", 0.0)
    if answer_score < 0.35 and answer_features.get("attempt_count", 0) >= 2:
        risk_score += 0.16
        recent_anomaly.append("accuracy_drop")
    elif answer_score >= 0.75:
        risk_score -= 0.08

    syllabus_score = syllabus_features.get("syllabus_score", 0.0)
    if syllabus_score < 0.35:
        risk_score += 0.1
    elif syllabus_score >= 0.7:
        risk_score -= 0.08

    goal_clarity_score = dialogue_features.get("goal_clarity", {}).get("score", 0.0)
    if goal_clarity_score >= 0.7:
        risk_score -= 0.05

    risk_score = round(_clip(risk_score), 4)
    if risk_score < 0.35:
        risk_label = "low"
    elif risk_score < 0.65:
        risk_label = "medium"
    else:
        risk_label = "high"

    return {
        "dropout_risk": risk_label,
        "dropout_risk_score": risk_score,
        "recent_anomaly": _unique_preserve(recent_anomaly),
    }


def resolve_profile_conflicts(
    dialogue_features: Dict[str, Any],
    answer_features: Dict[str, Any],
    behavior_features: Dict[str, Any],
    syllabus_features: Dict[str, Any],
) -> Dict[str, Any]:
    subjective = (
        dialogue_features.get("term_familiarity", {}).get("score", 0.0) * 0.5
        + (1.0 - dialogue_features.get("self_reported_difficulty", {}).get("score", 0.0)) * 0.5
    )
    objective = (
        answer_features.get("answer_score", 0.0) * 0.5
        + syllabus_features.get("syllabus_score", 0.0) * 0.3
        + behavior_features.get("engagement_score", 0.0) * 0.2
    )
    gap = round(abs(subjective - objective), 4)
    if gap < 0.2:
        alignment = "aligned"
    elif gap < 0.45:
        alignment = "mild_conflict"
    else:
        alignment = "objective_priority"
    if objective <= subjective:
        objective_priority = "behavior_and_answer_records"
    else:
        objective_priority = "dialogue_and_goal"
    return {
        "alignment": alignment,
        "gap": gap,
        "objective_priority": objective_priority,
    }


def build_profile_evidence(
    dialogue_features: Dict[str, Any],
    behavior_features: Dict[str, Any],
    answer_features: Dict[str, Any],
    syllabus_features: Dict[str, Any],
    risk_features: Dict[str, Any],
) -> List[str]:
    evidence: List[str] = []
    active_days = behavior_features.get("signals", {}).get("active_days_7d", 0)
    avg_duration = behavior_features.get("signals", {}).get("avg_duration_minutes", 0.0)
    if active_days:
        evidence.append(f"近7天活跃 {active_days} 天")
    if avg_duration:
        evidence.append(f"平均单次学习时长约 {avg_duration} 分钟")
    weak_points = answer_features.get("concept_gaps", [])
    if weak_points:
        evidence.append(f"知识点“{weak_points[0]}”当前掌握度偏低")
    weak_weeks = syllabus_features.get("weak_weeks", [])
    if weak_weeks:
        evidence.append(f"个人教学大纲显示第 {weak_weeks[0]} 周掌握较弱")
    resource_preference = behavior_features.get("resource_preference", None)
    if resource_preference:
        evidence.append(f"近期资源偏好偏向 {resource_preference[0]}")
    if risk_features.get("recent_anomaly"):
        evidence.append(f"检测到近期异常：{', '.join(risk_features['recent_anomaly'])}")
    if dialogue_features.get("deadline"):
        evidence.append(f"学生明确表达了时限目标：{dialogue_features['deadline']}")
    return evidence[:5]


def build_profile_signals(
    merged_events: Dict[str, Any],
    history_events: Sequence[Dict[str, Any]],
    dialogue_features: Dict[str, Any],
    behavior_features: Dict[str, Any],
) -> Dict[str, Any]:
    signals = {
        "history_count": len(history_events),
        "history_sources": 1 if history_events else 0,
        "question_text_count": dialogue_features.get("question_text_count", 0),
        "profile_scope_count": 1,
    }
    signals.update(behavior_features.get("signals", {}))
    signals["answer_record_count"] = sum(1 for event in merged_events["events"] if event.get("source") == "answer_records")
    return signals


def build_profile_confidence(
    merged_events: Dict[str, Any],
    personal_syllabus: Optional[Dict[str, Any]],
) -> float:
    source_count = len(merged_events.get("source_events", []))
    history_count = sum(1 for event in merged_events.get("events", []) if event.get("source") == "history")
    missing_penalty = min(len(merged_events.get("missing_fields", [])) * 0.03, 0.18)
    format_penalty = min(len(merged_events.get("format_issues", [])) * 0.025, 0.15)
    personal_bonus = 0.08 if personal_syllabus else 0.0
    confidence = 0.32 + source_count * 0.11 + min(history_count, 3) * 0.03 + personal_bonus - missing_penalty - format_penalty
    return round(_clip(confidence, 0.18, 0.95), 4)


def _target_level_from_goal(goal_text: Optional[str], overall_score: float) -> str:
    merged = goal_text or ""
    if any(word in merged for word in ("熟练", "深入", "精通")):
        return "熟练"
    if any(word in merged for word in ("进阶", "提升", "冲刺")):
        return "进阶"
    if overall_score >= 0.78:
        return "熟练"
    if overall_score >= 0.5:
        return "进阶"
    return "入门"


def assemble_learning_profile(
    request_data: Dict[str, Any],
    context: Dict[str, Any],
    merged_events: Dict[str, Any],
    dialogue_features: Dict[str, Any],
    behavior_features: Dict[str, Any],
    resource_features: Dict[str, Any],
    answer_features: Dict[str, Any],
    syllabus_features: Dict[str, Any],
    risk_features: Dict[str, Any],
    conflict_resolution: Dict[str, Any],
) -> Dict[str, Any]:
    resource_preference = resource_features.get("resource_preference", [])
    behavior_features = dict(behavior_features)
    behavior_features["resource_preference"] = resource_preference

    answer_score = answer_features.get("answer_score", 0.0)
    syllabus_score = syllabus_features.get("syllabus_score", 0.0)
    engagement_score = behavior_features.get("engagement_score", 0.0)
    overall_score = round(answer_score * 0.4 + syllabus_score * 0.35 + engagement_score * 0.25, 4)
    overall_level = "weak" if overall_score < 0.45 else "normal" if overall_score < 0.75 else "master"

    concept_gaps = _unique_preserve(answer_features.get("concept_gaps", []) + syllabus_features.get("weak_topics", []))
    evidence = build_profile_evidence(dialogue_features, behavior_features, answer_features, syllabus_features, risk_features)
    signals = build_profile_signals(
        merged_events,
        [event for event in merged_events["events"] if event.get("source") == "history"],
        dialogue_features,
        behavior_features,
    )
    confidence = build_profile_confidence(merged_events, context.get("personal_syllabus"))

    user_context = context.get("user") or {}
    syllabus_context = context.get("syllabus") or {}
    personal_path = context.get("personal_syllabus_path")
    syllabus_scope = []
    if request_data.get("syllabus_id") or syllabus_context.get("syllabus_id"):
        syllabus_scope.append(
            {
                "syllabus_id": request_data.get("syllabus_id") or syllabus_context.get("syllabus_id"),
                "title": syllabus_context.get("title"),
                "personal_syllabus_path": personal_path,
            }
        )

    mapped_nodes = _unique_preserve(answer_features.get("by_knowledge_point", {}).keys())
    profile = {
        "user_id": request_data.get("user_id"),
        "user_name": user_context.get("user_name"),
        "email": user_context.get("email"),
        "syllabus_scope": syllabus_scope,
        "learning_goal": request_data.get("learning_goal"),
        "goal_clarity": dialogue_features.get("goal_clarity"),
        "term_familiarity": dialogue_features.get("term_familiarity"),
        "help_seeking_level": dialogue_features.get("help_seeking_level"),
        "self_reported_difficulty": dialogue_features.get("self_reported_difficulty"),
        "emotion_state": dialogue_features.get("emotion_state"),
        "target_level": _target_level_from_goal(request_data.get("learning_goal"), overall_score),
        "deadline": dialogue_features.get("deadline"),
        "knowledge_mastery": {
            "overall_level": overall_level,
            "overall_score": overall_score,
            "syllabus_score": syllabus_score,
            "answer_score": answer_score,
            "engagement_score": round(engagement_score, 4),
            "week_items": syllabus_features.get("week_items", []),
            "mastered_weeks": syllabus_features.get("mastered_weeks", []),
            "weak_weeks": syllabus_features.get("weak_weeks", []),
            "by_knowledge_point": answer_features.get("by_knowledge_point", {}),
            "knowledge_point_details": answer_features.get("knowledge_point_details", {}),
        },
        "concept_gaps": concept_gaps,
        "practice_ability": {
            "level": _level_bucket((answer_score + engagement_score) / 2.0),
            "score": round((answer_score + engagement_score) / 2.0, 4),
        },
        "comprehension_level": {
            "level": _level_bucket((dialogue_features.get("term_familiarity", {}).get("score", 0.0) + answer_score) / 2.0),
            "score": round((dialogue_features.get("term_familiarity", {}).get("score", 0.0) + answer_score) / 2.0, 4),
        },
        "study_frequency": behavior_features.get("study_frequency"),
        "study_duration": behavior_features.get("study_duration"),
        "resource_preference": resource_preference,
        "answer_pattern": answer_features.get("answer_pattern") or dialogue_features.get("answer_pattern"),
        "learning_style": resource_features.get("learning_style", "mixed"),
        "attention_pattern": behavior_features.get("attention_pattern"),
        "difficulty_tolerance": behavior_features.get("difficulty_tolerance"),
        "bottleneck_topics": concept_gaps[:5],
        "dropout_risk": risk_features.get("dropout_risk"),
        "dropout_risk_score": risk_features.get("dropout_risk_score"),
        "recent_anomaly": risk_features.get("recent_anomaly", []),
        "confidence": confidence,
        "evidence": evidence,
        "source_events": merged_events.get("source_events", []),
        "knowledge_mapping": {
            "mapped_nodes": list(mapped_nodes),
            "mapped_node_count": len(mapped_nodes),
            "graph_binding": "knowledge_point_proxy_nodes",
        },
        "conflict_resolution": conflict_resolution,
        "updated_at": _now_ts(),
        "signals": signals,
        "missing_field_report": merged_events.get("missing_fields", []),
        "format_issue_report": merged_events.get("format_issues", []),
        "normalization_report": {
            "missing_fields": merged_events.get("missing_fields", []),
            "format_issues": merged_events.get("format_issues", []),
            "warning_count": len(merged_events.get("missing_fields", [])) + len(merged_events.get("format_issues", [])),
        },
    }
    return profile


def compute_learning_profile(request_payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    context = context or {}
    normalized_request = normalize_learning_profile_request(request_payload)
    history_rows = context.get("history", []) or []

    dialogue_group = normalize_dialogue_events(normalized_request["dialogue_text"], normalized_request["learning_goal"])
    history_group = normalize_history_events(history_rows)
    learning_group = normalize_learning_records(normalized_request["learning_records"])
    answer_group = normalize_answer_records(normalized_request["answer_records"])
    resource_group = normalize_resource_usage(normalized_request["resource_usage"])

    merged = merge_profile_events(dialogue_group, history_group, learning_group, answer_group, resource_group)
    merged["missing_fields"] = _unique_preserve(merged["missing_fields"] + normalized_request["missing_fields"])
    merged["format_issues"] = _unique_preserve(merged["format_issues"] + normalized_request["format_issues"])

    dialogue_features = compute_dialogue_features(
        dialogue_group["events"] + history_group["events"],
        normalized_request["learning_goal"],
    )
    behavior_features = compute_behavior_features(learning_group["events"], resource_group["events"])
    resource_features = compute_resource_preference_features(resource_group["events"], learning_group["events"])
    answer_features = compute_answer_mastery_features(answer_group["events"])
    syllabus_features = compute_syllabus_mastery_features(context.get("personal_syllabus"))
    risk_features = compute_risk_features(dialogue_features, behavior_features, answer_features, syllabus_features)
    conflict_resolution = resolve_profile_conflicts(dialogue_features, answer_features, behavior_features, syllabus_features)

    profile = assemble_learning_profile(
        normalized_request,
        context,
        merged,
        dialogue_features,
        behavior_features,
        resource_features,
        answer_features,
        syllabus_features,
        risk_features,
        conflict_resolution,
    )
    return {
        "success": True,
        "profile": profile,
        "error_message": "",
        "error_code": "",
    }


def load_experiment_datasets(samples_dir: Optional[Path] = None) -> Dict[str, Any]:
    base_dir = samples_dir or SAMPLES_DIR
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(base_dir.glob("*.json"))
    }


def build_sample_indices(datasets: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        "bundle_by_id": {
            item["bundle_id"]: item
            for item in datasets["profile_input_bundles.json"]["bundles"]
        },
        "dialogue_by_id": {
            item["sample_id"]: item
            for item in datasets["dialogue_profile_dataset.json"]["samples"]
        },
        "learning_by_id": {
            item["sample_id"]: item
            for item in datasets["learning_records_dataset.json"]["samples"]
        },
        "answer_by_id": {
            item["sample_id"]: item
            for item in datasets["answer_records_dataset.json"]["samples"]
        },
        "resource_by_id": {
            item["sample_id"]: item
            for item in datasets["resource_usage_dataset.json"]["samples"]
        },
        "personal_by_id": {
            item["sample_id"]: item
            for item in datasets["personal_syllabus_dataset.json"]["profiles"]
        },
        "edge_template_by_id": {
            item["template_id"]: item
            for item in datasets.get("edge_case_bundles.json", {}).get("templates", [])
        },
        "edge_case_by_id": {
            item["case_id"]: item
            for item in datasets.get("edge_case_bundles.json", {}).get("cases", [])
        },
    }
