from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence


TOPIC_KEYWORDS = {
	'code': ['代码', '编程', '实现', '程序', '示例代码', '案例', 'notebook', 'ipynb'],
	'visual': ['图', '思维导图', '流程图', '表格', '结构图', '脑图'],
	'theory': ['原理', '概念', '定义', '机制', '解释', '讲解', '讲义', '文档', 'pdf'],
	'practice': ['题目', '练习', '作业', '测试', '实操', '演练', '刷题'],
	'example': ['举例', '示例', '例子', '案例'],
	'video': ['视频', '录屏', '讲课', '课程回放', 'mp4'],
}

GOAL_TERMS = ['目标', '想要', '希望', '准备', '计划', '掌握', '达到', '完成', '学会', '冲刺']
TIME_TERMS = ['今天', '本周', '这周', '一周', '两周', '本月', '月底', '天内', '周内', '月内']
QUESTION_TERMS = ['怎么', '为什么', '如何', '能不能', '请问', '?', '？']
NEGATIVE_EMOTION_TERMS = ['不会', '看不懂', '听不懂', '困难', '吃力', '卡住', '挫败', '焦虑', '跟不上', '太难']
POSITIVE_EMOTION_TERMS = ['掌握', '清楚', '明白', '会了', '熟悉', '有信心']
DIFFICULTY_TERMS = ['薄弱', '不会', '困难', '卡住', '跟不上', '没掌握', '不太会', '吃力']


def safe_text(value: Any) -> str:
	if value is None:
		return ''
	if isinstance(value, str):
		return value.strip()
	return str(value).strip()


def flatten_text_inputs(*values: Any) -> List[str]:
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
				texts.extend(flatten_text_inputs(item))
			continue
		if isinstance(value, (list, tuple, set)):
			for item in value:
				texts.extend(flatten_text_inputs(item))
			continue
		text = safe_text(value)
		if text:
			texts.append(text)
	return texts


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
	try:
		value = float(value)
	except Exception:
		value = 0.0
	return max(low, min(high, value))


def parse_timestamp(value: Any) -> Optional[int]:
	if value in (None, ''):
		return None
	if isinstance(value, (int, float)):
		return int(value)
	text = safe_text(value)
	if not text:
		return None
	for candidate in (text, text.replace('/', '-')):
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


def normalize_duration_minutes(entry: dict) -> Optional[float]:
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


def day_bucket(timestamp_value: int) -> str:
	return datetime.fromtimestamp(timestamp_value).strftime('%Y-%m-%d')


def extract_knowledge_points(entry: Any) -> List[str]:
	if not isinstance(entry, dict):
		return []
	candidates: List[str] = []
	meta = entry.get('meta') if isinstance(entry.get('meta'), dict) else {}
	for container in (entry, meta):
		for key in ('knowledge_points', 'knowledge_point', 'knowledgePoints', 'topic', 'topics'):
			value = container.get(key)
			candidates.extend(flatten_text_inputs(value))
	return list(dict.fromkeys([text for text in candidates if text]))


def extract_texts_for_event(entry: dict, extra_fields: Optional[Sequence[str]] = None) -> List[str]:
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
	values.append(extract_knowledge_points(entry))
	return list(dict.fromkeys(flatten_text_inputs(values)))


def normalize_history_events(history_entries: Sequence[dict]) -> List[dict]:
	events: List[dict] = []
	for entry in history_entries or []:
		if not isinstance(entry, dict):
			continue
		events.append({
			'source': 'history',
			'timestamp': parse_timestamp(entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': normalize_duration_minutes(entry),
			'texts': extract_texts_for_event(entry),
			'knowledge_points': extract_knowledge_points(entry),
			'correct': entry.get('correct'),
			'score': entry.get('score'),
			'action': safe_text(entry.get('action')),
			'event_type': safe_text(entry.get('event_type') or entry.get('type') or 'history'),
		})
	return events


def normalize_learning_events(learning_records: Any) -> List[dict]:
	events: List[dict] = []
	if not isinstance(learning_records, (list, tuple)):
		return events
	for entry in learning_records:
		if not isinstance(entry, dict):
			continue
		events.append({
			'source': 'learning_records',
			'timestamp': parse_timestamp(entry.get('started_at') or entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': normalize_duration_minutes(entry),
			'texts': extract_texts_for_event(entry),
			'knowledge_points': extract_knowledge_points(entry),
			'correct': None,
			'score': float(entry.get('score')) if isinstance(entry.get('score'), (int, float)) else None,
			'action': safe_text(entry.get('action')),
			'event_type': safe_text(entry.get('event_type') or 'study_session'),
		})
	return events


def normalize_answer_events(answer_records: Any) -> List[dict]:
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
			'timestamp': parse_timestamp(entry.get('answered_at') or entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': normalize_duration_minutes(entry),
			'texts': extract_texts_for_event(entry),
			'knowledge_points': extract_knowledge_points(entry),
			'correct': bool(correct) if correct is not None else None,
			'score': float(score) if isinstance(score, (int, float)) else None,
			'action': 'answer',
			'event_type': 'answer',
		})
	return events


def guess_resource_kind(texts: Sequence[str]) -> str:
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


def normalize_resource_events(resource_usage: Any) -> List[dict]:
	events: List[dict] = []
	if not isinstance(resource_usage, (list, tuple)):
		return events
	for entry in resource_usage:
		if not isinstance(entry, dict):
			continue
		texts = extract_texts_for_event(entry)
		kind = guess_resource_kind(texts)
		events.append({
			'source': 'resource_usage',
			'timestamp': parse_timestamp(entry.get('timestamp') or entry.get('created_at')),
			'duration_minutes': normalize_duration_minutes(entry),
			'texts': texts,
			'knowledge_points': extract_knowledge_points(entry),
			'correct': None,
			'score': None,
			'action': safe_text(entry.get('action') or 'view'),
			'event_type': kind,
			'resource_kind': kind,
		})
	return events


def extract_dialogue_features(
	dialogue_texts: Sequence[str],
	explicit_goal: str,
	score_to_band: Callable[[float], str],
) -> Dict[str, Any]:
	texts = [text for text in dialogue_texts if text]
	joined = '\n'.join(texts)
	goal_term_hits = sum(1 for term in GOAL_TERMS if term in joined)
	time_term_hits = sum(1 for term in TIME_TERMS if term in joined)
	question_hits = sum(1 for term in QUESTION_TERMS if term in joined)
	negative_hits = sum(1 for term in NEGATIVE_EMOTION_TERMS if term in joined)
	positive_hits = sum(1 for term in POSITIVE_EMOTION_TERMS if term in joined)
	difficulty_hits = sum(1 for term in DIFFICULTY_TERMS if term in joined)
	text_count = len(texts)

	goal_score = 0.9 if safe_text(explicit_goal) else clip(0.2 + 0.18 * goal_term_hits + 0.08 * time_term_hits)
	goal_confidence = round(clip(0.35 + 0.18 * text_count + (0.2 if safe_text(explicit_goal) else 0.0)), 4)
	term_score = round(clip(0.12 * len(set([term for terms in TOPIC_KEYWORDS.values() for term in terms if term in joined]))), 4)
	help_score = round(clip(0.2 + 0.18 * question_hits + 0.08 * text_count), 4)
	self_difficulty_score = round(clip(0.15 + 0.18 * difficulty_hits + 0.08 * negative_hits), 4)

	if negative_hits >= positive_hits + 1:
		emotion_label = 'frustrated'
	elif positive_hits >= negative_hits + 1:
		emotion_label = 'positive'
	else:
		emotion_label = 'neutral'

	return {
		'goal_clarity': {
			'level': score_to_band(goal_score),
			'score': round(goal_score, 4),
			'confidence': goal_confidence,
		},
		'term_familiarity': {
			'level': score_to_band(term_score),
			'score': term_score,
			'confidence': round(clip(0.25 + 0.16 * text_count), 4),
		},
		'help_seeking_level': {
			'level': score_to_band(help_score),
			'score': help_score,
		},
		'self_reported_difficulty': {
			'level': score_to_band(self_difficulty_score),
			'score': self_difficulty_score,
		},
		'emotion_state': {
			'label': emotion_label,
			'negative_hits': negative_hits,
			'positive_hits': positive_hits,
		},
	}
