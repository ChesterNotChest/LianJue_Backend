import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from statistics import mean
from time import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from config import OPENAI_COMPAT_MODEL_CONFIGS
from constant import BasePath
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_repo import get_user_by_id
from repositories.user_syllabus_repo import get_user_syllabus, list_user_syllabuses, set_personal_profile_path
from utils.llm_utils import get_model_instance


_COMPETANCE_SCORE = {
	'weak_far': 0,
	'weak': 1,
	'normal': 2,
	'master': 3,
	'master_far': 4,
	'none': None,
}

_TOPIC_KEYWORDS = {
	'code': ['代码', '编程', '实现', '程序', '示例代码', '案例', 'notebook', 'ipynb'],
	'visual': ['图', '思维导图', '流程图', '表格', '结构图', '脑图'],
	'theory': ['原理', '概念', '定义', '机制', '解释', '讲解', '讲义', '文档', 'pdf'],
	'practice': ['题目', '练习', '作业', '测试', '实操', '演练', '刷题'],
	'example': ['举例', '示例', '例子', '案例'],
	'video': ['视频', '录屏', '讲课', '课程回放', 'mp4'],
}

_PATTERN_KEYWORDS = {
	'detail-seeking': ['为什么', '原理', '机制', '区别', '详细', '展开', '推导'],
	'example-seeking': ['举例', '示例', '案例', '怎么做', '怎么写'],
	'code-seeking': ['代码', '实现', '编程', '程序'],
	'practical': ['练习', '题目', '作业', '测试', '实操'],
}

_GOAL_TERMS = ['目标', '想要', '希望', '准备', '计划', '掌握', '达到', '完成', '学会', '冲刺']
_TIME_TERMS = ['今天', '本周', '这周', '一周', '两周', '本月', '月底', '天内', '周内', '月内']
_QUESTION_TERMS = ['怎么', '为什么', '如何', '能不能', '请问', '?', '？']
_NEGATIVE_EMOTION_TERMS = ['不会', '看不懂', '听不懂', '困难', '吃力', '卡住', '挫败', '焦虑', '跟不上', '太难']
_POSITIVE_EMOTION_TERMS = ['掌握', '清楚', '明白', '会了', '熟悉', '有信心']
_DIFFICULTY_TERMS = ['薄弱', '不会', '困难', '卡住', '跟不上', '没掌握', '不太会', '吃力']


def _load_json_file(path: str) -> Any:
	if not path or not os.path.exists(path):
		return None
	try:
		with open(path, 'r', encoding='utf-8') as f:
			return json.load(f)
	except Exception:
		return None


def _profile_root_dir() -> str:
	root_name = str(BasePath.PERSONAL_PROFILE_ROOT.value).strip().strip('/\\')
	return os.path.abspath(os.path.join(os.getcwd(), root_name))


def _build_personal_profile_path(user_id: int, syllabus_id: int) -> str:
	root = _profile_root_dir()
	os.makedirs(root, exist_ok=True)
	return os.path.abspath(os.path.join(root, f'{syllabus_id}-{user_id}.json'))


def _load_existing_profile(user_id: int, syllabus_id: Optional[int]) -> Tuple[Optional[dict], Optional[str]]:
	if syllabus_id is None:
		return None, None

	candidate_path = _build_personal_profile_path(user_id, syllabus_id)
	try:
		relation = get_user_syllabus(user_id, syllabus_id)
	except Exception:
		relation = None

	db_path = getattr(relation, 'personal_profile_path', None) if relation else None
	for path in (db_path, candidate_path):
		if not path:
			continue
		profile = _load_json_file(path)
		if isinstance(profile, dict):
			return profile, os.path.abspath(path)
	return None, candidate_path


def _merge_profile_update(existing_profile: Optional[dict], new_profile: dict) -> dict:
	if not isinstance(new_profile, dict):
		return {}

	merged = dict(new_profile)
	if isinstance(existing_profile, dict) and existing_profile:
		previous_revision = existing_profile.get('profile_revision') or 0
		try:
			previous_revision = int(previous_revision)
		except Exception:
			previous_revision = 0
		merged['previous_profile_updated_at'] = existing_profile.get('updated_at') or existing_profile.get('saved_at')
		merged['previous_confidence'] = existing_profile.get('confidence')
		merged['profile_revision'] = previous_revision + 1
	else:
		merged['profile_revision'] = int(merged.get('profile_revision') or 1)
	return merged


def _save_personal_profile(user_id: int, syllabus_id: int, profile: dict) -> Optional[str]:
	if not isinstance(profile, dict):
		return None

	try:
		profile_path = _build_personal_profile_path(user_id, syllabus_id)
		payload = dict(profile)
		payload['profile_schema_version'] = int(payload.get('profile_schema_version') or 1)
		payload['profile_path'] = profile_path
		payload['profile_saved'] = True
		payload['saved_at'] = int(time())
		with open(profile_path, 'w', encoding='utf-8') as f:
			json.dump(payload, f, ensure_ascii=False, indent=2)
		if not set_personal_profile_path(user_id, syllabus_id, profile_path):
			return None
		profile.clear()
		profile.update(payload)
		return profile_path
	except Exception:
		return None


def _profile_has_required_identity(profile: dict, user_id: int, syllabus_id: int) -> bool:
	if not isinstance(profile, dict):
		return False
	try:
		if int(profile.get('user_id')) != int(user_id):
			return False
	except Exception:
		return False

	scope = profile.get('syllabus_scope')
	if isinstance(scope, list):
		for item in scope:
			if not isinstance(item, dict):
				continue
			try:
				if int(item.get('syllabus_id')) == int(syllabus_id):
					return True
			except Exception:
				continue
	return bool(profile.get('profile_path') or profile.get('saved_at'))


def get_persisted_learning_profile(user_id: int, syllabus_id: int) -> Optional[dict]:
	profile, profile_path = _load_existing_profile(user_id, syllabus_id)
	if not isinstance(profile, dict):
		return None
	if not _profile_has_required_identity(profile, user_id, syllabus_id):
		return None
	result = dict(profile)
	if profile_path:
		result['profile_path'] = profile_path
	result['profile_saved'] = True
	result['profile_refreshed'] = False
	return result


def _safe_text(value: Any) -> str:
	if value is None:
		return ''
	if isinstance(value, str):
		return value.strip()
	return str(value).strip()


def _flatten_text_inputs(*values: Any) -> List[str]:
	texts: List[str] = []
	for value in values:
		if value is None:
			continue
		if isinstance(value, str):
			text = value.strip()
			if text:
				texts.append(text)
			continue
		if isinstance(value, dict):
			for item in value.values():
				texts.extend(_flatten_text_inputs(item))
			continue
		if isinstance(value, (list, tuple, set)):
			for item in value:
				texts.extend(_flatten_text_inputs(item))
			continue
		text = _safe_text(value)
		if text:
			texts.append(text)
	return texts


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
	return max(low, min(high, value))


def _mean_or_zero(values: Sequence[float]) -> float:
	valid = [float(value) for value in values if value is not None]
	return mean(valid) if valid else 0.0


def _parse_timestamp(value: Any) -> Optional[int]:
	if value is None or value == '':
		return None
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		parsed = int(value)
		return parsed if parsed > 0 else None
	text = _safe_text(value)
	if not text:
		return None
	try:
		parsed = int(float(text))
		return parsed if parsed > 0 else None
	except Exception:
		pass
	text = text.replace('Z', '+00:00')
	for candidate in (
		text,
		text.replace('/', '-'),
	):
		try:
			return int(datetime.fromisoformat(candidate).timestamp())
		except Exception:
			continue
	for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
		try:
			return int(datetime.strptime(text, fmt).timestamp())
		except Exception:
			continue
	return None


def _normalize_duration_minutes(entry: dict) -> Optional[float]:
	if not isinstance(entry, dict):
		return None
	for key in ('duration_minutes', 'study_minutes'):
		value = entry.get(key)
		if value not in (None, ''):
			try:
				duration = float(value)
				return duration if duration > 0 else None
			except Exception:
				pass
	for key in ('duration_seconds', 'time_spent_seconds', 'watch_seconds'):
		value = entry.get(key)
		if value not in (None, ''):
			try:
				duration = float(value) / 60.0
				return duration if duration > 0 else None
			except Exception:
				pass
	return None


def _day_bucket(timestamp_value: int) -> str:
	return datetime.fromtimestamp(timestamp_value).strftime('%Y-%m-%d')


def _extract_knowledge_points(entry: Any) -> List[str]:
	if not isinstance(entry, dict):
		return []
	candidates: List[str] = []
	meta = entry.get('meta') if isinstance(entry.get('meta'), dict) else {}
	for container in (entry, meta):
		for key in ('knowledge_points', 'knowledge_point', 'knowledgePoints', 'topic', 'topics'):
			value = container.get(key)
			candidates.extend(_flatten_text_inputs(value))
	return list(dict.fromkeys([text for text in candidates if text]))


def _extract_texts_for_event(entry: dict, extra_fields: Optional[Sequence[str]] = None) -> List[str]:
	if not isinstance(entry, dict):
		return []
	values: List[Any] = []
	for key in ('question', 'answer', 'dialogue_text', 'content', 'title', 'description', 'note', 'notes', 'resource_id', 'event_type', 'action'):
		values.append(entry.get(key))
	if extra_fields:
		for key in extra_fields:
			values.append(entry.get(key))
	meta = entry.get('meta')
	if isinstance(meta, dict):
		values.append(meta)
	values.append(_extract_knowledge_points(entry))
	return list(dict.fromkeys(_flatten_text_inputs(values)))


def _collect_history_entries(user_id: int, syllabus_id: Optional[int] = None) -> List[dict]:
	history_dir = os.path.join(os.getcwd(), 'history')
	if not os.path.exists(history_dir):
		return []

	paths: List[str] = []
	if syllabus_id is not None:
		paths.append(os.path.join(history_dir, f'{syllabus_id}_{user_id}.json'))
	else:
		try:
			for name in os.listdir(history_dir):
				if name.endswith(f'_{user_id}.json'):
					paths.append(os.path.join(history_dir, name))
		except Exception:
			return []

	entries: List[dict] = []
	for path in paths:
		data = _load_json_file(path)
		if isinstance(data, list):
			for item in data:
				if isinstance(item, dict):
					entries.append(item)
	return entries


def _load_personal_syllabus(user_id: int, syllabus_id: Optional[int] = None) -> List[Tuple[int, dict, dict]]:
	relations = []
	if syllabus_id is not None:
		for row in list_user_syllabuses(user_id):
			if getattr(row, 'syllabus_id', None) == syllabus_id:
				relations.append(row)
				break
	else:
		relations = list_user_syllabuses(user_id)

	loaded: List[Tuple[int, dict, dict]] = []
	for relation in relations:
		path = getattr(relation, 'personal_syllabus_path', None)
		if not path:
			continue
		personal_json = _load_json_file(path)
		if not isinstance(personal_json, dict):
			continue
		syllabus = get_syllabus_by_id(getattr(relation, 'syllabus_id', None))
		syllabus_json = _load_json_file(getattr(syllabus, 'syllabus_path', None)) if syllabus else None
		loaded.append(
			(
				getattr(relation, 'syllabus_id', None),
				personal_json,
				syllabus_json if isinstance(syllabus_json, dict) else {},
			)
		)
	return loaded


def _competance_to_score(level: Any) -> Optional[int]:
	if level is None:
		return None
	return _COMPETANCE_SCORE.get(str(level).strip(), None)


def _level_from_score(score: float) -> str:
	if score <= 0.5:
		return 'weak_far'
	if score <= 1.5:
		return 'weak'
	if score <= 2.5:
		return 'normal'
	if score <= 3.5:
		return 'master'
	return 'master_far'


def _score_to_band(score: float) -> str:
	if score < 0.35:
		return 'low'
	if score < 0.7:
		return 'medium'
	return 'high'


def _build_goal_text(explicit_goal: str, dialogue_texts: Sequence[str], syllabus_rows: Sequence[Tuple[int, dict, dict]]) -> str:
	goal = _safe_text(explicit_goal)
	if goal:
		return goal
	for text in dialogue_texts:
		if text:
			return text[:80]
	for _, _, syllabus_json in syllabus_rows:
		title = _safe_text(syllabus_json.get('title'))
		if title:
			return title
		period = syllabus_json.get('period', []) if isinstance(syllabus_json, dict) else []
		if isinstance(period, list):
			for entry in period:
				content = _safe_text(entry.get('content') or entry.get('enhanced_content'))
				if content:
					return content[:80]
	return '未提供'


def _build_week_signals(personal_json: dict, syllabus_json: dict) -> Dict[str, Any]:
	period = personal_json.get('period', []) if isinstance(personal_json, dict) else []
	week_items: List[dict] = []
	weak_weeks: List[int] = []
	mastered_weeks: List[int] = []
	concept_gaps: List[str] = []
	total_score = 0.0
	count = 0
	for entry in period if isinstance(period, list) else []:
		if not isinstance(entry, dict):
			continue
		week_index = entry.get('week_index')
		competance = _safe_text(entry.get('competance') or 'none')
		try:
			progress_value = int(entry.get('competance_progress') or 0)
		except Exception:
			progress_value = 0
		score = _competance_to_score(competance)
		if score is None:
			score = 0
		week_score = min(4.0, max(0.0, score + (progress_value / 5.0)))
		total_score += week_score
		count += 1
		content = _safe_text(entry.get('enhanced_content') or entry.get('content'))
		week_items.append({
			'week_index': week_index,
			'competance': competance,
			'competance_progress': progress_value,
			'score': round(week_score / 4.0, 4),
			'content': content[:80],
		})
		if week_score <= 1.0:
			weak_weeks.append(week_index)
			if content:
				concept_gaps.append(content[:40])
		elif week_score >= 2.5:
			mastered_weeks.append(week_index)

	if count == 0:
		overall_score = 0.0
		overall_level = 'none'
	else:
		overall_score = round(total_score / (count * 4.0), 4)
		if overall_score < 0.35:
			overall_level = 'weak'
		elif overall_score < 0.7:
			overall_level = 'normal'
		else:
			overall_level = 'master'

	return {
		'overall_score': overall_score,
		'overall_level': overall_level,
		'week_items': week_items,
		'weak_weeks': weak_weeks,
		'mastered_weeks': mastered_weeks,
		'concept_gaps': concept_gaps[:8],
	}


def _normalize_history_events(history_entries: Sequence[dict]) -> List[dict]:
	events: List[dict] = []
	for entry in history_entries:
		if not isinstance(entry, dict):
			continue
		events.append({
			'source': 'history',
			'timestamp': _parse_timestamp(entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': _normalize_duration_minutes(entry),
			'texts': _extract_texts_for_event(entry),
			'knowledge_points': _extract_knowledge_points(entry),
			'correct': None,
			'score': None,
			'action': 'qa',
			'event_type': 'qa',
		})
	return events


def _normalize_learning_events(learning_records: Any) -> List[dict]:
	events: List[dict] = []
	if not isinstance(learning_records, (list, tuple)):
		return events
	for entry in learning_records:
		if not isinstance(entry, dict):
			continue
		events.append({
			'source': 'learning_records',
			'timestamp': _parse_timestamp(entry.get('started_at') or entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': _normalize_duration_minutes(entry),
			'texts': _extract_texts_for_event(entry),
			'knowledge_points': _extract_knowledge_points(entry),
			'correct': None,
			'score': None,
			'action': _safe_text(entry.get('action')),
			'event_type': _safe_text(entry.get('event_type') or 'study_session'),
		})
	return events


def _normalize_answer_events(answer_records: Any) -> List[dict]:
	events: List[dict] = []
	if not isinstance(answer_records, (list, tuple)):
		return events
	for entry in answer_records:
		if not isinstance(entry, dict):
			continue
		correct = entry.get('correct')
		score = entry.get('score')
		if correct is None and score is not None:
			try:
				correct = float(score) >= 0.6
			except Exception:
				correct = None
		events.append({
			'source': 'answer_records',
			'timestamp': _parse_timestamp(entry.get('answered_at') or entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': _normalize_duration_minutes(entry),
			'texts': _extract_texts_for_event(entry),
			'knowledge_points': _extract_knowledge_points(entry),
			'correct': bool(correct) if correct is not None else None,
			'score': float(score) if isinstance(score, (int, float)) else None,
			'action': 'answer',
			'event_type': 'answer',
		})
	return events


def _guess_resource_kind(texts: Sequence[str]) -> str:
	joined = ' '.join([text.lower() for text in texts if text])
	if any(token in joined for token in ('video', 'mp4', '录屏', '回放', '课程视频')):
		return 'video'
	if any(token in joined for token in ('code', 'notebook', 'ipynb', '代码')):
		return 'code'
	if any(token in joined for token in ('mindmap', '思维导图', '流程图', '结构图')):
		return 'visual'
	if any(token in joined for token in ('pdf', 'doc', '讲义', '文档', '材料')):
		return 'theory'
	return 'general'


def _normalize_resource_events(resource_usage: Any) -> List[dict]:
	events: List[dict] = []
	if not isinstance(resource_usage, (list, tuple)):
		return events
	for entry in resource_usage:
		if not isinstance(entry, dict):
			continue
		texts = _extract_texts_for_event(entry)
		events.append({
			'source': 'resource_usage',
			'timestamp': _parse_timestamp(entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': _normalize_duration_minutes(entry),
			'texts': texts,
			'knowledge_points': _extract_knowledge_points(entry),
			'correct': None,
			'score': None,
			'action': _safe_text(entry.get('action') or 'view'),
			'event_type': _guess_resource_kind(texts),
			'resource_kind': _guess_resource_kind(texts),
		})
	return events


def _extract_dialogue_features(dialogue_texts: Sequence[str], explicit_goal: str) -> Dict[str, Any]:
	texts = [text for text in dialogue_texts if text]
	joined = '\n'.join(texts)
	goal_term_hits = sum(1 for term in _GOAL_TERMS if term in joined)
	time_term_hits = sum(1 for term in _TIME_TERMS if term in joined)
	question_hits = sum(1 for term in _QUESTION_TERMS if term in joined)
	negative_hits = sum(1 for term in _NEGATIVE_EMOTION_TERMS if term in joined)
	positive_hits = sum(1 for term in _POSITIVE_EMOTION_TERMS if term in joined)
	difficulty_hits = sum(1 for term in _DIFFICULTY_TERMS if term in joined)
	term_hits = sum(1 for terms in _TOPIC_KEYWORDS.values() for term in terms if term in joined)
	text_count = len(texts)

	goal_score = 0.9 if _safe_text(explicit_goal) else _clip(0.2 + 0.18 * goal_term_hits + 0.08 * time_term_hits)
	goal_confidence = round(_clip(0.35 + 0.18 * text_count + (0.2 if _safe_text(explicit_goal) else 0.0)), 4)
	term_score = round(_clip(0.12 * len(set([term for terms in _TOPIC_KEYWORDS.values() for term in terms if term in joined]))), 4)
	help_score = round(_clip(0.2 + 0.18 * question_hits + 0.08 * text_count), 4)
	self_difficulty_score = round(_clip(0.15 + 0.18 * difficulty_hits + 0.08 * negative_hits), 4)

	if negative_hits >= positive_hits + 1:
		emotion_label = 'frustrated'
	elif positive_hits >= negative_hits + 1:
		emotion_label = 'positive'
	else:
		emotion_label = 'neutral'

	return {
		'goal_clarity': {
			'level': _score_to_band(goal_score),
			'score': round(goal_score, 4),
			'confidence': goal_confidence,
		},
		'term_familiarity': {
			'level': _score_to_band(term_score),
			'score': term_score,
			'confidence': round(_clip(0.25 + 0.16 * text_count), 4),
		},
		'help_seeking_level': {
			'level': _score_to_band(help_score),
			'score': help_score,
		},
		'self_reported_difficulty': {
			'level': _score_to_band(self_difficulty_score),
			'score': self_difficulty_score,
		},
		'emotion_state': {
			'label': emotion_label,
			'negative_hits': negative_hits,
			'positive_hits': positive_hits,
		},
	}


def _infer_topic_preferences(texts: Sequence[str], resource_events: Sequence[dict]) -> Dict[str, float]:
	counter = Counter()
	for text in texts:
		for label, terms in _TOPIC_KEYWORDS.items():
			if any(term in text for term in terms):
				counter[label] += 1
	for event in resource_events:
		resource_kind = event.get('resource_kind')
		action = _safe_text(event.get('action'))
		if resource_kind in {'video', 'code', 'visual', 'theory'}:
			counter[resource_kind] += 2 if action == 'complete' else 1
		if action in {'download', 'complete'}:
			counter['practice'] += 1
	total = sum(counter.values()) or 1
	return {key: round(value / total, 4) for key, value in counter.items()}


def _infer_learning_style(topic_preferences: Dict[str, float]) -> str:
	if not topic_preferences:
		return 'balanced'
	top_label = sorted(topic_preferences.items(), key=lambda item: item[1], reverse=True)[0][0]
	if top_label in {'code', 'practice'}:
		return 'practice-driven'
	if top_label == 'example':
		return 'example-driven'
	if top_label in {'visual', 'video'}:
		return 'visual-driven'
	if top_label == 'theory':
		return 'theory-driven'
	return 'balanced'


def _infer_answer_pattern(texts: Sequence[str]) -> str:
	counts = Counter()
	for text in texts:
		for label, terms in _PATTERN_KEYWORDS.items():
			if any(term in text for term in terms):
				counts[label] += 1
	if not counts:
		return 'general'
	return counts.most_common(1)[0][0]


def _summarize_activity(events: Sequence[dict], now_ts: int) -> Dict[str, Any]:
	events_with_time = [event for event in events if event.get('timestamp')]
	timestamps = sorted([int(event['timestamp']) for event in events_with_time if int(event['timestamp']) > 0])
	latest_ts = timestamps[-1] if timestamps else 0
	durations = [float(event['duration_minutes']) for event in events if event.get('duration_minutes')]
	avg_duration = _mean_or_zero(durations)

	recent_7_days = {
		_day_bucket(ts)
		for ts in timestamps
		if now_ts - ts <= 7 * 24 * 3600
	}
	recent_30_days = {
		_day_bucket(ts)
		for ts in timestamps
		if now_ts - ts <= 30 * 24 * 3600
	}
	all_days = {_day_bucket(ts) for ts in timestamps}

	if not timestamps:
		frequency = 'none'
		frequency_score = 0.0
	else:
		active_days = len(recent_7_days) or min(len(recent_30_days), len(all_days))
		frequency_score = _clip(active_days / 7.0)
		if active_days <= 1:
			frequency = 'low'
		elif active_days <= 4:
			frequency = 'medium'
		else:
			frequency = 'high'

	if not durations:
		duration_label = 'unknown'
		duration_score = 0.0
	else:
		duration_score = _clip(avg_duration / 45.0)
		if avg_duration < 15:
			duration_label = 'short'
		elif avg_duration < 40:
			duration_label = 'medium'
		else:
			duration_label = 'long'

	resource_events = [event for event in events if event.get('source') == 'resource_usage']
	completion_ratio = 0.0
	if resource_events:
		completion_ratio = sum(1 for event in resource_events if event.get('action') in {'complete', 'download', 'like'}) / float(len(resource_events))

	attention_pattern = 'stable'
	if frequency in {'none', 'low'}:
		attention_pattern = 'sporadic'
	elif durations and avg_duration < 8 and len(events_with_time) >= 4:
		attention_pattern = 'bursty'

	return {
		'frequency': frequency,
		'frequency_score': round(frequency_score, 4),
		'duration': duration_label,
		'duration_score': round(duration_score, 4),
		'avg_duration_minutes': round(avg_duration, 2) if avg_duration else 0.0,
		'active_days_7d': len(recent_7_days),
		'active_days_30d': len(recent_30_days),
		'latest_ts': latest_ts,
		'attention_pattern': attention_pattern,
		'completion_ratio': round(completion_ratio, 4),
	}


def _build_answer_mastery(answer_events: Sequence[dict], latest_ts: int) -> Dict[str, Any]:
	answer_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {
		'weighted_total': 0.0,
		'weighted_correct': 0.0,
		'attempt_count': 0.0,
		'evidence': [],
		'latest_ts': 0.0,
	})
	for event in answer_events:
		knowledge_points = event.get('knowledge_points') or []
		if not knowledge_points:
			continue
		timestamp_value = int(event.get('timestamp') or 0)
		age_days = ((latest_ts - timestamp_value) / 86400.0) if latest_ts and timestamp_value else 999.0
		if age_days <= 7:
			weight = 1.0
		elif age_days <= 30:
			weight = 0.75
		else:
			weight = 0.5
		correct = event.get('correct')
		score = event.get('score')
		score_value = float(score) if isinstance(score, (int, float)) else (1.0 if correct is True else 0.0 if correct is False else 0.5)
		for kp in knowledge_points:
			item = answer_stats[kp]
			item['weighted_total'] += weight
			item['weighted_correct'] += weight * score_value
			item['attempt_count'] += 1
			item['latest_ts'] = max(float(item['latest_ts']), float(timestamp_value))

	answer_mastery_scores: Dict[str, float] = {}
	knowledge_point_details: Dict[str, Dict[str, Any]] = {}
	for kp, stats in answer_stats.items():
		total = stats['weighted_total']
		score = (stats['weighted_correct'] / total) if total > 0 else 0.0
		attempt_count = int(stats['attempt_count'])
		confidence = _clip(0.25 + 0.18 * min(attempt_count, 4) + (0.18 if total >= 2.0 else 0.0))
		answer_mastery_scores[kp] = round(score, 4)
		knowledge_point_details[kp] = {
			'score': round(score, 4),
			'confidence': round(confidence, 4),
			'attempt_count': attempt_count,
			'level': _score_to_band(score),
		}
	return {
		'by_knowledge_point': answer_mastery_scores,
		'knowledge_point_details': knowledge_point_details,
	}


def _infer_comprehension_level(question_texts: Sequence[str], mastery_score: float) -> Dict[str, Any]:
	lengths = [len(text) for text in question_texts if text]
	avg_len = mean(lengths) if lengths else 0.0
	depth_bonus = 0.0
	for text in question_texts:
		if any(token in text for token in ['为什么', '原理', '区别', '对比', '推导', '实现']):
			depth_bonus += 0.1
	if avg_len >= 80:
		depth_bonus += 0.12
	elif avg_len >= 40:
		depth_bonus += 0.06
	score = _clip(mastery_score * 0.6 + depth_bonus + 0.18)
	return {
		'level': _score_to_band(score),
		'score': round(score, 4),
	}


def _infer_practice_ability(
	topic_preferences: Dict[str, float],
	mastery_score: float,
	answer_events: Sequence[dict],
	activity_summary: Dict[str, Any],
) -> Dict[str, Any]:
	practice_signal = topic_preferences.get('practice', 0.0) + topic_preferences.get('code', 0.0)
	answer_count = len(answer_events)
	persistence_bonus = 0.0
	if answer_count >= 5:
		persistence_bonus += 0.12
	if activity_summary.get('completion_ratio', 0.0) >= 0.4:
		persistence_bonus += 0.08
	score = _clip(mastery_score * 0.5 + practice_signal * 0.8 + persistence_bonus)
	return {'level': _score_to_band(score), 'score': round(score, 4)}


def _infer_difficulty_tolerance(
	answer_events: Sequence[dict],
	activity_summary: Dict[str, Any],
	dialogue_features: Dict[str, Any],
) -> str:
	repeated_attempts = Counter()
	for event in answer_events:
		for kp in event.get('knowledge_points') or []:
			repeated_attempts[kp] += 1
	retry_score = _clip(sum(1 for count in repeated_attempts.values() if count >= 2) / 3.0)
	duration_score = activity_summary.get('duration_score', 0.0)
	emotion_penalty = 0.15 if dialogue_features['emotion_state']['label'] == 'frustrated' else 0.0
	score = _clip(0.42 * retry_score + 0.38 * duration_score + 0.2 * activity_summary.get('completion_ratio', 0.0) - emotion_penalty)
	return _score_to_band(score)


def _infer_conflict_resolution(self_reported_difficulty: Dict[str, Any], overall_score: float) -> Dict[str, Any]:
	self_score = float(self_reported_difficulty.get('score') or 0.0)
	objective_difficulty = 1.0 - overall_score
	gap = round(self_score - objective_difficulty, 4)
	if gap >= 0.28:
		alignment = 'under_confident'
	elif gap <= -0.28:
		alignment = 'over_confident'
	else:
		alignment = 'aligned'
	return {
		'alignment': alignment,
		'gap': gap,
		'objective_priority': 'behavior_and_answer_records',
	}


def _detect_recent_anomalies(
	answer_events: Sequence[dict],
	activity_summary: Dict[str, Any],
	dialogue_features: Dict[str, Any],
	now_ts: int,
) -> List[str]:
	anomalies: List[str] = []
	latest_ts = int(activity_summary.get('latest_ts') or 0)
	if latest_ts and now_ts - latest_ts > 14 * 24 * 3600:
		anomalies.append('inactive_recently')
	if dialogue_features['emotion_state']['label'] == 'frustrated':
		anomalies.append('frustration_signal')
	if len(answer_events) >= 4:
		ordered = sorted(answer_events, key=lambda item: int(item.get('timestamp') or 0))
		recent = ordered[-5:]
		previous = ordered[:-5]
		recent_acc = _mean_or_zero([1.0 if item.get('correct') is True else 0.0 for item in recent if item.get('correct') is not None])
		prev_acc = _mean_or_zero([1.0 if item.get('correct') is True else 0.0 for item in previous if item.get('correct') is not None]) if previous else recent_acc
		if previous and prev_acc - recent_acc >= 0.3:
			anomalies.append('accuracy_drop')
		if recent_acc <= 0.35:
			anomalies.append('persistent_errors')
	if activity_summary.get('attention_pattern') == 'bursty':
		anomalies.append('fragmented_attention')
	return list(dict.fromkeys(anomalies))


def _infer_drop_risk(
	overall_score: float,
	activity_summary: Dict[str, Any],
	dialogue_features: Dict[str, Any],
	recent_anomalies: Sequence[str],
) -> Dict[str, Any]:
	inactivity_penalty = 1.0 - float(activity_summary.get('frequency_score') or 0.0)
	emotion_penalty = 0.8 if dialogue_features['emotion_state']['label'] == 'frustrated' else 0.2
	anomaly_penalty = min(1.0, len(recent_anomalies) / 4.0)
	score = _clip(
		0.4 * inactivity_penalty
		+ 0.3 * (1.0 - overall_score)
		+ 0.2 * emotion_penalty
		+ 0.1 * anomaly_penalty
	)
	if score < 0.35:
		level = 'low'
	elif score < 0.65:
		level = 'medium'
	else:
		level = 'high'
	return {'level': level, 'score': round(score, 4)}


def _build_concept_gaps(
	existing_gaps: Sequence[str],
	knowledge_point_details: Dict[str, Dict[str, Any]],
	dialogue_texts: Sequence[str],
) -> List[str]:
	gaps = [gap for gap in existing_gaps if gap]
	for kp, detail in knowledge_point_details.items():
		if float(detail.get('score') or 0.0) < 0.55:
			gaps.append(kp)
	joined = '\n'.join(dialogue_texts)
	for token in ['函数', '循环', '递归', '指针', '概率', '矩阵', 'SQL', '索引']:
		if token in joined and any(term in joined for term in _DIFFICULTY_TERMS):
			gaps.append(token)
	return list(dict.fromkeys(gaps))[:10]


def _build_evidence(
	activity_summary: Dict[str, Any],
	dialogue_features: Dict[str, Any],
	knowledge_point_details: Dict[str, Dict[str, Any]],
	week_signals: Sequence[dict],
	recent_anomalies: Sequence[str],
) -> List[str]:
	evidence: List[str] = []
	active_days = int(activity_summary.get('active_days_7d') or 0)
	evidence.append(f'近7天活跃 {active_days} 天')
	avg_duration = float(activity_summary.get('avg_duration_minutes') or 0.0)
	if avg_duration > 0:
		evidence.append(f'平均单次学习时长约 {round(avg_duration, 1)} 分钟')
	if dialogue_features['emotion_state']['label'] == 'frustrated':
		evidence.append('对话中出现明显的困难或挫败表达')
	for kp, detail in sorted(knowledge_point_details.items(), key=lambda item: item[1]['score'])[:2]:
		evidence.append(f'知识点“{kp}”当前掌握度约为 {int(detail["score"] * 100)}%')
	for signal in week_signals:
		for week in signal.get('week_items', []):
			if float(week.get('score') or 0.0) <= 0.3 and week.get('content'):
				evidence.append(f'个人大纲周次 {week.get("week_index")} 的能力表现偏弱：{week.get("content")}')
				break
		if len(evidence) >= 6:
			break
	if 'inactive_recently' in recent_anomalies:
		evidence.append('最近超过 14 天无新学习事件')
	return list(dict.fromkeys(evidence))[:8]


def _build_confidence(
	events: Sequence[dict],
	latest_ts: int,
	source_events: Sequence[str],
	week_signals: Sequence[dict],
	now_ts: int,
) -> float:
	sample_factor = _clip(len(events) / 18.0)
	source_factor = _clip(len(source_events) / 4.0)
	week_factor = 0.2 if week_signals else 0.0
	if latest_ts <= 0:
		freshness_factor = 0.3
	else:
		age_days = max(0.0, (now_ts - latest_ts) / 86400.0)
		if age_days <= 7:
			freshness_factor = 1.0
		elif age_days <= 30:
			freshness_factor = 0.7
		else:
			freshness_factor = 0.4
	return round(_clip(0.38 * sample_factor + 0.26 * source_factor + 0.24 * freshness_factor + week_factor), 4)


@dataclass
class LearningProfileDeps:
	state: Dict[str, Any] = field(default_factory=dict)


class LearningProfileResult(BaseModel):
	success: bool = True
	profile: Optional[dict] = None
	error_message: str = ''
	error_code: str = ''


def _build_learning_profile_model() -> OpenAIModel:
	text_config = OPENAI_COMPAT_MODEL_CONFIGS.get('text') or {}
	model_name = _safe_text(text_config.get('model_name') or text_config.get('name'))
	if not model_name:
		raise RuntimeError('missing MODEL_CONFIGS["text"]["model_name"] for learning profile agent')
	base_url = _safe_text(text_config.get('api_base') or text_config.get('base_url')) or None
	api_key = _safe_text(text_config.get('api_key')) or os.getenv('OPENAI_API_KEY')
	provider = OpenAIProvider(base_url=base_url, api_key=api_key)
	return OpenAIModel(model_name, provider=provider)


@lru_cache(maxsize=1)
def get_learning_profile_agent() -> Agent:
	agent = Agent(
		model=_build_learning_profile_model(),
		deps_type=LearningProfileDeps,
		output_type=LearningProfileResult,
		system_prompt=(
			'你是学习画像编排器。你必须通过工具逐步完成上下文读取、事件归一化、特征计算和画像汇总。'
			'一次只调用一个工具，拿到结果后再决定下一步。'
			'工具顺序通常是：load_history_context、load_personal_syllabus_context、normalize_events、compute_features、assemble_profile。'
			'最终必须返回 LearningProfileResult。'
		),
		name='learning_profile_agent',
		description='Learning profile tool-calling agent',
		retries=1,
		defer_model_check=True,
	)

	@agent.tool(sequential=True)
	def load_existing_profile_context(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_load_existing_profile_context(ctx.deps.state)

	@agent.tool(sequential=True)
	def load_history_context(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_load_history_context(ctx.deps.state)

	@agent.tool(sequential=True)
	def load_personal_syllabus_context(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_load_personal_syllabus_context(ctx.deps.state)

	@agent.tool(sequential=True)
	def normalize_events(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_normalize_events(ctx.deps.state)

	@agent.tool(sequential=True)
	def compute_features(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_compute_features(ctx.deps.state)

	@agent.tool(sequential=True)
	def assemble_profile(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_assemble_profile(ctx.deps.state)

	@agent.tool(sequential=True)
	def save_or_update_profile(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_save_or_update_profile(ctx.deps.state)

	return agent



def _build_learning_profile_user_prompt(state: Dict[str, Any]) -> str:
	request_summary = {
		'user_id': state.get('user_id'),
		'syllabus_id': state.get('syllabus_id'),
		'dialogue_sample': (state.get('dialogue_texts') or [])[:3],
		'learning_goal': _safe_text(state.get('learning_goal')),
		'learning_record_count': len(state.get('learning_records') or []) if isinstance(state.get('learning_records'), (list, tuple)) else 0,
		'answer_record_count': len(state.get('answer_records') or []) if isinstance(state.get('answer_records'), (list, tuple)) else 0,
		'resource_usage_count': len(state.get('resource_usage') or []) if isinstance(state.get('resource_usage'), (list, tuple)) else 0,
		'available_context': {
			'existing_profile': state.get('syllabus_id') is not None,
			'history_entries': state.get('syllabus_id') is not None,
			'personal_syllabus': bool(state.get('profile_scope')),
		},
		'state_summary': _summarize_learning_profile_state(state),
	}
	return json.dumps(request_summary, ensure_ascii=False)



def run_learning_profile_agent(state: Dict[str, Any]) -> LearningProfileResult:
	deps = LearningProfileDeps(state=state)
	agent = get_learning_profile_agent()
	result = agent.run_sync(_build_learning_profile_user_prompt(state), deps=deps)
	state['agent_output'] = result.output
	return result.output



def _summarize_learning_profile_state(state: Dict[str, Any]) -> Dict[str, Any]:
	normalized_events = state.get('normalized_events') if isinstance(state.get('normalized_events'), dict) else {}
	feature_bundle = state.get('feature_bundle') if isinstance(state.get('feature_bundle'), dict) else {}
	return {
		'user_id': state.get('user_id'),
		'syllabus_id': state.get('syllabus_id'),
		'raw_inputs': {
			'dialogue_text_count': len(state.get('dialogue_texts') or []),
			'learning_record_count': len(state.get('learning_records') or []) if isinstance(state.get('learning_records'), (list, tuple)) else 0,
			'answer_record_count': len(state.get('answer_records') or []) if isinstance(state.get('answer_records'), (list, tuple)) else 0,
			'resource_usage_count': len(state.get('resource_usage') or []) if isinstance(state.get('resource_usage'), (list, tuple)) else 0,
		},
		'loaded_context': {
			'existing_profile_loaded': bool(state.get('existing_profile_loaded')),
			'existing_profile_found': bool(state.get('existing_profile')),
			'history_loaded': bool(state.get('history_loaded')),
			'personal_syllabus_loaded': bool(state.get('personal_syllabus_loaded')),
			'history_count': len(state.get('history_entries') or []),
			'personal_syllabus_count': len(state.get('loaded_personal_syllabuses') or []),
		},
		'normalized_ready': bool(normalized_events),
		'normalized_counts': {
			'history_events': len(normalized_events.get('history_events') or []),
			'learning_events': len(normalized_events.get('learning_events') or []),
			'answer_events': len(normalized_events.get('answer_events') or []),
			'resource_events': len(normalized_events.get('resource_events') or []),
			'all_events': len(normalized_events.get('all_events') or []),
		},
		'features_ready': bool(feature_bundle),
		'profile_ready': bool(state.get('profile')),
		'profile_saved': bool(state.get('profile_saved')),
		'profile_path': state.get('profile_path') or state.get('existing_profile_path'),
		'feature_summary': {
			'confidence': feature_bundle.get('global_confidence'),
			'overall_score': feature_bundle.get('overall_score'),
			'dropout_risk': feature_bundle.get('drop_risk', {}).get('level') if isinstance(feature_bundle.get('drop_risk'), dict) else None,
		} if feature_bundle else {},
	}


def _build_learning_profile_tool_prompt(state: Dict[str, Any]) -> str:
	return (
		'你是学习画像的工具编排器。你必须根据当前状态，每轮只返回一个下一步工具指令。\n'
		'可用工具：\n'
		'1. load_history_context: 读取历史学习与问答记录\n'
		'2. load_personal_syllabus_context: 读取个人教学大纲\n'
		'3. normalize_events: 将原始输入和上下文归一化为事件\n'
		'4. compute_features: 基于事件计算画像特征\n'
		'5. assemble_profile: 汇总生成最终 profile\n'
		'决策规则：\n'
		'- 如果还缺历史或个人大纲，优先调用读取类工具。\n'
		'- 如果读取类信息已足够，调用 normalize_events。\n'
		'- 只有在事件已归一化后才能调用 compute_features。\n'
		'- 只有在特征已计算后才能调用 assemble_profile。\n'
		'- 只输出 JSON，不要输出解释。格式为 {"action":"tool","tool_name":"...","reason":"..."}。\n'
		'- 如果当前已经完成最终 profile，也可以返回 {"action":"finalize"}。'
	)


def _extract_tool_instruction(text: Any) -> Optional[Dict[str, Any]]:
	payload = _extract_json_object(text)
	if not payload:
		return None
	action = _safe_text(payload.get('action') or payload.get('type') or payload.get('next_action')).lower()
	tool_name = _safe_text(payload.get('tool_name') or payload.get('tool') or payload.get('name')).lower()
	reason = _safe_text(payload.get('reason') or payload.get('thought'))
	if action in {'finalize', 'finish', 'done', 'stop'}:
		return {'action': 'finalize', 'tool_name': None, 'reason': reason}
	if action in {'tool', 'call', 'use', 'next'} and tool_name:
		return {'action': 'tool', 'tool_name': tool_name, 'reason': reason}
	if tool_name in {'load_existing_profile_context', 'load_history_context', 'load_personal_syllabus_context', 'normalize_events', 'compute_features', 'assemble_profile', 'save_or_update_profile'}:
		return {'action': 'tool', 'tool_name': tool_name, 'reason': reason}
	return None


def _fallback_next_learning_profile_tool(state: Dict[str, Any]) -> Dict[str, Any]:
	if state.get('syllabus_id') is not None and not state.get('existing_profile_loaded'):
		return {'action': 'tool', 'tool_name': 'load_existing_profile_context', 'reason': 'fallback load existing profile'}
	if not state.get('history_loaded') and state.get('syllabus_id') is not None:
		return {'action': 'tool', 'tool_name': 'load_history_context', 'reason': 'fallback load history'}
	if not state.get('personal_syllabus_loaded') and state.get('profile_scope'):
		return {'action': 'tool', 'tool_name': 'load_personal_syllabus_context', 'reason': 'fallback load personal syllabus'}
	if not state.get('normalized_events'):
		return {'action': 'tool', 'tool_name': 'normalize_events', 'reason': 'fallback normalize events'}
	if not state.get('feature_bundle'):
		return {'action': 'tool', 'tool_name': 'compute_features', 'reason': 'fallback compute features'}
	if not state.get('profile'):
		return {'action': 'tool', 'tool_name': 'assemble_profile', 'reason': 'fallback assemble profile'}
	if state.get('syllabus_id') is not None and not state.get('profile_saved'):
		return {'action': 'tool', 'tool_name': 'save_or_update_profile', 'reason': 'fallback save profile'}
	return {'action': 'finalize', 'tool_name': None, 'reason': 'fallback finalize'}


def _decide_next_learning_profile_tool(state: Dict[str, Any]) -> Dict[str, Any]:
	try:
		model = get_model_instance()
		raw = model.call_text_model(_build_learning_profile_tool_prompt(state), json.dumps(_summarize_learning_profile_state(state), ensure_ascii=False), stream=False)
		instruction = _extract_tool_instruction(raw)
		if instruction:
			return instruction
	except Exception:
		pass
	return _fallback_next_learning_profile_tool(state)


def _tool_load_history_context(state: Dict[str, Any]) -> Dict[str, Any]:
	history_entries = _collect_history_entries(int(state['user_id']), syllabus_id=state.get('syllabus_id'))
	state['history_entries'] = history_entries
	state['history_loaded'] = True
	return {
		'tool': 'load_history_context',
		'history_count': len(history_entries),
		'has_history': bool(history_entries),
	}


def _tool_load_existing_profile_context(state: Dict[str, Any]) -> Dict[str, Any]:
	existing_profile, profile_path = _load_existing_profile(int(state['user_id']), state.get('syllabus_id'))
	state['existing_profile'] = existing_profile
	state['existing_profile_path'] = profile_path
	state['existing_profile_loaded'] = True
	return {
		'tool': 'load_existing_profile_context',
		'has_existing_profile': bool(existing_profile),
		'profile_path': profile_path,
		'existing_updated_at': existing_profile.get('updated_at') if isinstance(existing_profile, dict) else None,
	}


def _tool_load_personal_syllabus_context(state: Dict[str, Any]) -> Dict[str, Any]:
	loaded_personal_syllabuses = _load_personal_syllabus(int(state['user_id']), state.get('syllabus_id'))
	state['loaded_personal_syllabuses'] = loaded_personal_syllabuses
	state['personal_syllabus_loaded'] = True
	return {
		'tool': 'load_personal_syllabus_context',
		'personal_syllabus_count': len(loaded_personal_syllabuses),
	}


def _tool_normalize_events(state: Dict[str, Any]) -> Dict[str, Any]:
	history_entries = state.get('history_entries') or []
	learning_records = state.get('learning_records')
	answer_records = state.get('answer_records')
	resource_usage = state.get('resource_usage')
	history_events = _normalize_history_events(history_entries)
	learning_events = _normalize_learning_events(learning_records)
	answer_events = _normalize_answer_events(answer_records)
	resource_events = _normalize_resource_events(resource_usage)
	all_events = [*history_events, *learning_events, *answer_events, *resource_events]
	normalized_events = {
		'history_events': history_events,
		'learning_events': learning_events,
		'answer_events': answer_events,
		'resource_events': resource_events,
		'all_events': all_events,
		'question_texts': _flatten_text_inputs([item.get('question') for item in history_entries], state.get('dialogue_texts') or []),
		'all_texts': list(dict.fromkeys(_flatten_text_inputs(
			state.get('dialogue_texts') or [],
			learning_records,
			answer_records,
			resource_usage,
			[event.get('texts') for event in history_events],
		))),
	}
	state['normalized_events'] = normalized_events
	return {
		'tool': 'normalize_events',
		'event_counts': {
			'history_events': len(history_events),
			'learning_events': len(learning_events),
			'answer_events': len(answer_events),
			'resource_events': len(resource_events),
			'all_events': len(all_events),
		},
	}


def _compute_learning_profile_bundle(state: Dict[str, Any]) -> Dict[str, Any]:
	if not state.get('normalized_events'):
		_tool_normalize_events(state)
	if not state.get('loaded_personal_syllabuses'):
		state['loaded_personal_syllabuses'] = []
	normalized = state.get('normalized_events') if isinstance(state.get('normalized_events'), dict) else {}
	history_entries = state.get('history_entries') or []
	loaded_personal_syllabuses = state.get('loaded_personal_syllabuses') or []
	dialogue_texts = state.get('dialogue_texts') or []
	learning_goal = _safe_text(state.get('learning_goal'))
	now_ts = int(state.get('now_ts') or time())
	profile_scope = state.get('profile_scope') or []
	user = state.get('user')
	all_events = normalized['all_events']
	history_events = normalized['history_events']
	learning_events = normalized['learning_events']
	answer_events = normalized['answer_events']
	resource_events = normalized['resource_events']
	combined_goal = _build_goal_text(learning_goal, dialogue_texts, loaded_personal_syllabuses)

	week_signals = [_build_week_signals(personal_json, syllabus_json) for _, personal_json, syllabus_json in loaded_personal_syllabuses]
	if week_signals:
		syllabus_mastery_score = round(mean([item['overall_score'] for item in week_signals]), 4)
		all_weak_weeks = sorted({week for item in week_signals for week in item['weak_weeks'] if week is not None})
		all_mastered_weeks = sorted({week for item in week_signals for week in item['mastered_weeks'] if week is not None})
		all_concept_gaps: List[str] = []
		for item in week_signals:
			all_concept_gaps.extend(item['concept_gaps'])
	else:
		syllabus_mastery_score = 0.0
		all_weak_weeks = []
		all_mastered_weeks = []
		all_concept_gaps = []

	dialogue_features = _extract_dialogue_features(dialogue_texts, learning_goal)
	question_texts = normalized['question_texts']
	all_texts = normalized['all_texts']
	activity_summary = _summarize_activity(all_events, now_ts)
	latest_ts = int(activity_summary.get('latest_ts') or 0) or now_ts

	answer_mastery = _build_answer_mastery(answer_events, latest_ts)
	answer_mastery_scores = answer_mastery['by_knowledge_point']
	knowledge_point_details = answer_mastery['knowledge_point_details']
	answer_mean = _mean_or_zero(list(answer_mastery_scores.values()))
	engagement_score = round(
		_clip(
			0.45 * float(activity_summary.get('frequency_score') or 0.0)
			+ 0.3 * float(activity_summary.get('duration_score') or 0.0)
			+ 0.25 * float(activity_summary.get('completion_ratio') or 0.0)
		),
		4,
	)

	score_components = []
	if week_signals:
		score_components.append(0.45 * syllabus_mastery_score)
	if answer_mastery_scores:
		score_components.append(0.4 * answer_mean)
	score_components.append(0.15 * engagement_score)
	overall_score = round(sum(score_components), 4) if score_components else 0.0

	if not week_signals and answer_mastery_scores:
		overall_score = round(_clip(0.75 * answer_mean + 0.25 * engagement_score), 4)

	resource_pref = _infer_topic_preferences(all_texts, resource_events)
	learning_style = _infer_learning_style(resource_pref)
	answer_pattern = _infer_answer_pattern(question_texts or all_texts)
	comprehension_level = _infer_comprehension_level(question_texts, overall_score)
	practice_ability = _infer_practice_ability(resource_pref, overall_score, answer_events, activity_summary)
	difficulty_tolerance = _infer_difficulty_tolerance(answer_events, activity_summary, dialogue_features)
	conflict_resolution = _infer_conflict_resolution(dialogue_features['self_reported_difficulty'], overall_score)
	recent_anomaly = _detect_recent_anomalies(answer_events, activity_summary, dialogue_features, now_ts)
	drop_risk = _infer_drop_risk(overall_score, activity_summary, dialogue_features, recent_anomaly)
	concept_gaps = _build_concept_gaps(all_concept_gaps, knowledge_point_details, dialogue_texts)
	bottleneck_topics = concept_gaps[:8]
	source_events = sorted({event['source'] for event in all_events if event.get('source')})
	global_confidence = _build_confidence(all_events, latest_ts, source_events, week_signals, now_ts)
	evidence = _build_evidence(activity_summary, dialogue_features, knowledge_point_details, week_signals, recent_anomaly)

	knowledge_mapping = {
		'mapped_nodes': sorted(knowledge_point_details.keys()),
		'mapped_node_count': len(knowledge_point_details),
		'graph_binding': 'knowledge_point_proxy_nodes',
	}

	goal_text = combined_goal or _safe_text(getattr(user, 'user_name', None)) or '未提供'
	target_level = '入门'
	if overall_score >= 0.85:
		target_level = '熟练'
	elif overall_score >= 0.7:
		target_level = '进阶'

	mastery_level = 'none'
	if week_signals:
		mastery_level = week_signals[0]['overall_level'] if len(week_signals) == 1 else _level_from_score(overall_score * 4.0)
	elif answer_mastery_scores:
		mastery_level = _level_from_score(overall_score * 4.0)

	profile = {
		'user_id': user.user_id,
		'user_name': user.user_name,
		'email': user.email,
		'syllabus_scope': profile_scope,
		'learning_goal': goal_text,
		'goal_clarity': dialogue_features['goal_clarity'],
		'term_familiarity': dialogue_features['term_familiarity'],
		'help_seeking_level': dialogue_features['help_seeking_level'],
		'self_reported_difficulty': dialogue_features['self_reported_difficulty'],
		'emotion_state': dialogue_features['emotion_state'],
		'target_level': target_level,
		'deadline': None,
		'knowledge_mastery': {
			'overall_level': mastery_level,
			'overall_score': overall_score,
			'syllabus_score': syllabus_mastery_score,
			'answer_score': round(answer_mean, 4),
			'engagement_score': engagement_score,
			'week_items': [item for signal in week_signals for item in signal['week_items']],
			'mastered_weeks': all_mastered_weeks,
			'weak_weeks': all_weak_weeks,
			'by_knowledge_point': answer_mastery_scores,
			'knowledge_point_details': knowledge_point_details,
		},
		'concept_gaps': concept_gaps,
		'practice_ability': practice_ability,
		'comprehension_level': comprehension_level,
		'study_frequency': activity_summary['frequency'],
		'study_duration': activity_summary['duration'],
		'resource_preference': sorted(resource_pref, key=resource_pref.get, reverse=True)[:4],
		'answer_pattern': answer_pattern,
		'learning_style': learning_style,
		'attention_pattern': activity_summary['attention_pattern'],
		'difficulty_tolerance': difficulty_tolerance,
		'bottleneck_topics': bottleneck_topics,
		'dropout_risk': drop_risk['level'],
		'dropout_risk_score': drop_risk['score'],
		'recent_anomaly': recent_anomaly,
		'confidence': global_confidence,
		'evidence': evidence,
		'source_events': source_events,
		'knowledge_mapping': knowledge_mapping,
		'conflict_resolution': conflict_resolution,
		'updated_at': latest_ts,
		'signals': {
			'history_count': len(history_entries),
			'history_sources': 1 if state.get('syllabus_id') is not None else len(state.get('user_syllabuses') or []),
			'question_text_count': len(question_texts),
			'profile_scope_count': len(profile_scope),
			'learning_record_count': len(learning_events),
			'answer_record_count': len(answer_events),
			'resource_event_count': len(resource_events),
			'active_days_7d': activity_summary['active_days_7d'],
			'active_days_30d': activity_summary['active_days_30d'],
			'avg_duration_minutes': activity_summary['avg_duration_minutes'],
		},
	}

	return {
		'now_ts': now_ts,
		'combined_goal': goal_text,
		'week_signals': week_signals,
		'syllabus_mastery_score': syllabus_mastery_score,
		'all_weak_weeks': all_weak_weeks,
		'all_mastered_weeks': all_mastered_weeks,
		'all_concept_gaps': all_concept_gaps,
		'dialogue_features': dialogue_features,
		'question_texts': question_texts,
		'all_texts': all_texts,
		'activity_summary': activity_summary,
		'latest_ts': latest_ts,
		'answer_mastery': answer_mastery,
		'answer_mastery_scores': answer_mastery_scores,
		'knowledge_point_details': knowledge_point_details,
		'answer_mean': answer_mean,
		'engagement_score': engagement_score,
		'overall_score': overall_score,
		'resource_pref': resource_pref,
		'learning_style': learning_style,
		'answer_pattern': answer_pattern,
		'comprehension_level': comprehension_level,
		'practice_ability': practice_ability,
		'difficulty_tolerance': difficulty_tolerance,
		'conflict_resolution': conflict_resolution,
		'recent_anomaly': recent_anomaly,
		'drop_risk': drop_risk,
		'concept_gaps': concept_gaps,
		'bottleneck_topics': bottleneck_topics,
		'source_events': source_events,
		'global_confidence': global_confidence,
		'evidence': evidence,
		'knowledge_mapping': knowledge_mapping,
		'target_level': target_level,
		'mastery_level': mastery_level,
		'profile': profile,
	}


def _tool_compute_features(state: Dict[str, Any]) -> Dict[str, Any]:
	state['feature_bundle'] = _compute_learning_profile_bundle(state)
	return {
		'tool': 'compute_features',
		'confidence': state['feature_bundle']['global_confidence'],
		'overall_score': state['feature_bundle']['overall_score'],
		'feature_count': len(state['feature_bundle']),
	}


def _tool_assemble_profile(state: Dict[str, Any]) -> Dict[str, Any]:
	if not state.get('feature_bundle'):
		_tool_compute_features(state)
	state['profile'] = state['feature_bundle']['profile']
	return {
		'tool': 'assemble_profile',
		'profile_ready': True,
		'profile_keys': len(state['profile']) if isinstance(state.get('profile'), dict) else 0,
	}


def _tool_save_or_update_profile(state: Dict[str, Any]) -> Dict[str, Any]:
	syllabus_id = state.get('syllabus_id')
	if syllabus_id is None:
		state['profile_saved'] = False
		return {
			'tool': 'save_or_update_profile',
			'saved': False,
			'profile_path': None,
			'profile_revision': None,
		}
	if not state.get('profile'):
		_tool_assemble_profile(state)

	merged_profile = _merge_profile_update(state.get('existing_profile'), state.get('profile') or {})
	profile_path = _save_personal_profile(int(state['user_id']), int(syllabus_id), merged_profile)
	if profile_path:
		state['profile'] = merged_profile
		state['profile_path'] = profile_path
		state['profile_saved'] = True
	else:
		if isinstance(state.get('profile'), dict):
			state['profile']['profile_saved'] = False
		state['profile_saved'] = False
	return {
		'tool': 'save_or_update_profile',
		'saved': bool(profile_path),
		'profile_path': profile_path,
		'profile_revision': merged_profile.get('profile_revision'),
	}


def build_learning_profile(
	user_id: int,
	syllabus_id: Optional[int] = None,
	dialogue_text: Any = None,
	learning_goal: Optional[str] = None,
	learning_records: Any = None,
	answer_records: Any = None,
	resource_usage: Any = None,
) -> Optional[dict]:
	user = get_user_by_id(user_id)
	if not user:
		return None

	user_syllabuses = list_user_syllabuses(user_id)
	if syllabus_id is not None:
		user_syllabuses = [row for row in user_syllabuses if getattr(row, 'syllabus_id', None) == syllabus_id]

	profile_scope = []
	for row in user_syllabuses:
		syllabus = get_syllabus_by_id(getattr(row, 'syllabus_id', None))
		profile_scope.append({
			'syllabus_id': getattr(row, 'syllabus_id', None),
			'title': _safe_text(getattr(syllabus, 'title', None)) if syllabus else '',
			'personal_syllabus_path': getattr(row, 'personal_syllabus_path', None),
			'personal_profile_path': getattr(row, 'personal_profile_path', None),
		})

	state = {
		'user_id': user_id,
		'syllabus_id': syllabus_id,
		'user': user,
		'user_syllabuses': user_syllabuses,
		'profile_scope': profile_scope,
		'dialogue_texts': _flatten_text_inputs(dialogue_text),
		'learning_goal': learning_goal,
		'learning_records': learning_records,
		'answer_records': answer_records,
		'resource_usage': resource_usage,
		'now_ts': int(time()),
		'history_entries': [],
		'existing_profile': None,
		'existing_profile_path': None,
		'existing_profile_loaded': False,
		'loaded_personal_syllabuses': [],
		'history_loaded': False,
		'personal_syllabus_loaded': False,
		'normalized_events': {},
		'feature_bundle': {},
		'profile': None,
		'profile_path': None,
		'profile_saved': False,
		'tool_trace': [],
	}
	if syllabus_id is not None:
		_tool_load_existing_profile_context(state)
	result = run_learning_profile_agent(state)
	if state.get('profile'):
		if syllabus_id is not None and not state.get('profile_saved'):
			_tool_save_or_update_profile(state)
		return state['profile']
	if isinstance(result, LearningProfileResult):
		if isinstance(result.profile, dict):
			state['profile'] = result.profile
			if syllabus_id is not None and not state.get('profile_saved'):
				_tool_save_or_update_profile(state)
			return state['profile']
		return result.profile
	return None


def get_or_build_learning_profile(
	user_id: int,
	syllabus_id: Optional[int] = None,
	refresh_profile: bool = False,
	dialogue_text: Any = None,
	learning_goal: Optional[str] = None,
	learning_records: Any = None,
	answer_records: Any = None,
	resource_usage: Any = None,
) -> Optional[dict]:
	if syllabus_id is not None and not refresh_profile:
		profile = get_persisted_learning_profile(user_id, int(syllabus_id))
		if profile is not None:
			return profile

	profile = build_learning_profile(
		user_id,
		syllabus_id,
		dialogue_text=dialogue_text,
		learning_goal=learning_goal,
		learning_records=learning_records,
		answer_records=answer_records,
		resource_usage=resource_usage,
	)
	if isinstance(profile, dict):
		profile['profile_refreshed'] = True
	return profile
