import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from time import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_repo import get_user_by_id
from repositories.user_syllabus_repo import list_user_syllabuses


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
		})

	now_ts = int(time())
	history_entries = _collect_history_entries(user_id, syllabus_id=syllabus_id)
	dialogue_texts = _flatten_text_inputs(dialogue_text)
	loaded_personal_syllabuses = _load_personal_syllabus(user_id, syllabus_id)
	combined_goal = _build_goal_text(_safe_text(learning_goal), dialogue_texts, loaded_personal_syllabuses)

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

	history_events = _normalize_history_events(history_entries)
	learning_events = _normalize_learning_events(learning_records)
	answer_events = _normalize_answer_events(answer_records)
	resource_events = _normalize_resource_events(resource_usage)
	all_events = [*history_events, *learning_events, *answer_events, *resource_events]

	dialogue_features = _extract_dialogue_features(dialogue_texts, _safe_text(learning_goal))
	all_texts = list(dict.fromkeys(_flatten_text_inputs(dialogue_texts, learning_records, answer_records, resource_usage, [event.get('texts') for event in history_events])))
	question_texts = _flatten_text_inputs([item.get('question') for item in history_entries], dialogue_texts)
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
			'history_sources': 1 if syllabus_id is not None else len(user_syllabuses),
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
	return profile
