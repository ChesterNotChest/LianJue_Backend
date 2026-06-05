from collections import Counter, defaultdict
import re
from statistics import mean
from time import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tasks.learning_profile import alignment


COMPETANCE_SCORE = {
	'weak_far': 0,
	'weak': 1,
	'normal': 2,
	'master': 3,
	'master_far': 4,
	'none': None,
}

TOPIC_KEYWORDS = {
	'code': ['代码', '编程', '实现', '程序', '示例代码', '案例', 'notebook', 'ipynb'],
	'visual': ['图', '思维导图', '流程图', '表格', '结构图', '脑图'],
	'theory': ['原理', '概念', '定义', '机制', '解释', '讲解', '讲义', '文档', 'pdf'],
	'practice': ['题目', '练习', '作业', '测试', '实操', '演练', '刷题'],
	'example': ['举例', '示例', '例子', '案例'],
	'video': ['视频', '录屏', '讲课', '课程回放', 'mp4'],
}

PATTERN_KEYWORDS = {
	'detail-seeking': ['为什么', '原理', '机制', '区别', '详细', '展开', '推导'],
	'example-seeking': ['举例', '示例', '案例', '怎么做', '怎么写'],
	'code-seeking': ['代码', '实现', '编程', '程序'],
	'practical': ['练习', '题目', '作业', '测试', '实操'],
}

DIFFICULTY_TERMS = ['薄弱', '不会', '困难', '卡住', '跟不上', '没掌握', '不太会', '吃力']

_CONCEPT_GAP_MAX_CHARS = 24
_CONCEPT_GAP_SENTENCE_TERMS = [
	'如何',
	'为什么',
	'怎么',
	'请问',
	'学习',
	'掌握',
	'了解',
	'能够',
	'熟悉',
	'完成',
	'课程',
	'导论',
	'基本概念',
]
_CONCEPT_GAP_SPLIT_RE = re.compile(r"[\r\n。；;，,]+")


def normalize_concept_gap(value: Any) -> str:
	text = alignment.safe_text(value)
	if not text:
		return ''
	text = re.sub(r'^\s*(?:第\s*)?\d+\s*(?:周|章|节|课|讲)?[\.\)、:：-]?\s*', '', text).strip()
	parts = [part.strip(' -•\t') for part in _CONCEPT_GAP_SPLIT_RE.split(text) if part.strip(' -•\t')]
	if parts:
		text = parts[0]
	if ':' in text or '：' in text:
		left, right = re.split(r'[:：]', text, maxsplit=1)
		left = left.strip()
		right = right.strip()
		if right and len(left) <= 8:
			text = right
		else:
			text = left or right
	text = text.strip(' -•\t?？!！.')
	if not text or len(text) > _CONCEPT_GAP_MAX_CHARS:
		return ''
	if any(marker in text for marker in ['?', '？', '。', '；', ';']):
		return ''
	if len(text) >= 12 and any(term in text for term in _CONCEPT_GAP_SENTENCE_TERMS):
		return ''
	return text


def dedupe_concept_gaps(values: Sequence[Any], *, limit: int = 10) -> List[str]:
	gaps: List[str] = []
	seen = set()
	for value in values:
		gap = normalize_concept_gap(value)
		if not gap or gap in seen:
			continue
		seen.add(gap)
		gaps.append(gap)
		if len(gaps) >= limit:
			break
	return gaps


def mean_or_zero(values: Sequence[float]) -> float:
	valid = [float(value) for value in values if isinstance(value, (int, float))]
	return mean(valid) if valid else 0.0


def competance_to_score(level: Any) -> Optional[int]:
	if level is None:
		return None
	return COMPETANCE_SCORE.get(str(level).strip(), None)


def level_from_score(score: float) -> str:
	if score <= 0.5:
		return 'weak_far'
	if score <= 1.5:
		return 'weak'
	if score <= 2.5:
		return 'normal'
	if score <= 3.5:
		return 'master'
	return 'master_far'


def score_to_band(score: float) -> str:
	if score < 0.35:
		return 'low'
	if score < 0.7:
		return 'medium'
	return 'high'


def build_goal_text(explicit_goal: str, dialogue_texts: Sequence[str], syllabus_rows: Sequence[Tuple[int, dict, dict]]) -> str:
	goal = alignment.safe_text(explicit_goal)
	if goal:
		return goal
	for text in dialogue_texts:
		if text:
			return text[:80]
	for _, _, syllabus_json in syllabus_rows:
		title = alignment.safe_text(syllabus_json.get('title'))
		if title:
			return title
		period = syllabus_json.get('period', []) if isinstance(syllabus_json, dict) else []
		if isinstance(period, list):
			for entry in period:
				content = alignment.safe_text(entry.get('content') or entry.get('enhanced_content'))
				if content:
					return content[:80]
	return '未提供'


def build_week_signals(personal_json: dict, syllabus_json: dict) -> Dict[str, Any]:
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
		competance = alignment.safe_text(entry.get('competance') or 'none')
		try:
			progress_value = int(entry.get('competance_progress') or 0)
		except Exception:
			progress_value = 0
		score = competance_to_score(competance)
		if score is None:
			score = 0
		week_score = min(4.0, max(0.0, score + (progress_value / 5.0)))
		total_score += week_score
		count += 1
		content = alignment.safe_text(entry.get('enhanced_content') or entry.get('content'))
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
				concept_gaps.append(content)
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
		'concept_gaps': dedupe_concept_gaps(concept_gaps, limit=8),
	}


def infer_topic_preferences(texts: Sequence[str], resource_events: Sequence[dict]) -> Dict[str, float]:
	counter = Counter()
	for text in texts:
		for label, terms in TOPIC_KEYWORDS.items():
			if any(term in text for term in terms):
				counter[label] += 1
	for event in resource_events:
		resource_kind = event.get('resource_kind')
		action = alignment.safe_text(event.get('action'))
		if resource_kind in {'video', 'code', 'visual', 'theory'}:
			counter[resource_kind] += 2 if action == 'complete' else 1
		if action in {'download', 'complete'}:
			counter['practice'] += 1
	total = sum(counter.values()) or 1
	return {key: round(value / total, 4) for key, value in counter.items()}


def infer_learning_style(topic_preferences: Dict[str, float]) -> str:
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


def infer_answer_pattern(texts: Sequence[str]) -> str:
	counts = Counter()
	for text in texts:
		for label, terms in PATTERN_KEYWORDS.items():
			if any(term in text for term in terms):
				counts[label] += 1
	if not counts:
		return 'general'
	return counts.most_common(1)[0][0]


def summarize_activity(events: Sequence[dict], now_ts: int) -> Dict[str, Any]:
	events_with_time = [event for event in events if event.get('timestamp')]
	timestamps = sorted([int(event['timestamp']) for event in events_with_time if int(event['timestamp']) > 0])
	latest_ts = timestamps[-1] if timestamps else 0
	durations = [float(event['duration_minutes']) for event in events if event.get('duration_minutes')]
	avg_duration = mean_or_zero(durations)

	recent_7_days = {
		alignment.day_bucket(ts)
		for ts in timestamps
		if now_ts - ts <= 7 * 24 * 3600
	}
	recent_30_days = {
		alignment.day_bucket(ts)
		for ts in timestamps
		if now_ts - ts <= 30 * 24 * 3600
	}
	all_days = {alignment.day_bucket(ts) for ts in timestamps}

	if not timestamps:
		frequency = 'none'
		frequency_score = 0.0
	else:
		active_days = len(recent_7_days) or min(len(recent_30_days), len(all_days))
		frequency_score = alignment.clip(active_days / 7.0)
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
		duration_score = alignment.clip(avg_duration / 45.0)
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


def build_answer_mastery(answer_events: Sequence[dict], latest_ts: int) -> Dict[str, Any]:
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
		confidence = alignment.clip(0.25 + 0.18 * min(attempt_count, 4) + (0.18 if total >= 2.0 else 0.0))
		answer_mastery_scores[kp] = round(score, 4)
		knowledge_point_details[kp] = {
			'score': round(score, 4),
			'confidence': round(confidence, 4),
			'attempt_count': attempt_count,
			'level': score_to_band(score),
		}
	return {
		'by_knowledge_point': answer_mastery_scores,
		'knowledge_point_details': knowledge_point_details,
	}


def infer_comprehension_level(question_texts: Sequence[str], mastery_score: float) -> Dict[str, Any]:
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
	score = alignment.clip(mastery_score * 0.6 + depth_bonus + 0.18)
	return {
		'level': score_to_band(score),
		'score': round(score, 4),
	}


def infer_practice_ability(
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
	score = alignment.clip(mastery_score * 0.5 + practice_signal * 0.8 + persistence_bonus)
	return {'level': score_to_band(score), 'score': round(score, 4)}


def infer_difficulty_tolerance(
	answer_events: Sequence[dict],
	activity_summary: Dict[str, Any],
	dialogue_features: Dict[str, Any],
) -> str:
	repeated_attempts = Counter()
	for event in answer_events:
		for kp in event.get('knowledge_points') or []:
			repeated_attempts[kp] += 1
	retry_score = alignment.clip(sum(1 for count in repeated_attempts.values() if count >= 2) / 3.0)
	duration_score = activity_summary.get('duration_score', 0.0)
	emotion_penalty = 0.15 if dialogue_features['emotion_state']['label'] == 'frustrated' else 0.0
	score = alignment.clip(0.42 * retry_score + 0.38 * duration_score + 0.2 * activity_summary.get('completion_ratio', 0.0) - emotion_penalty)
	return score_to_band(score)


def infer_conflict_resolution(self_reported_difficulty: Dict[str, Any], overall_score: float) -> Dict[str, Any]:
	self_score = float(self_reported_difficulty.get('score') or 0.0)
	objective_difficulty = 1.0 - overall_score
	gap = round(self_score - objective_difficulty, 4)
	if gap >= 0.28:
		alignment_label = 'under_confident'
	elif gap <= -0.28:
		alignment_label = 'over_confident'
	else:
		alignment_label = 'aligned'
	return {
		'alignment': alignment_label,
		'gap': gap,
		'objective_priority': 'behavior_and_answer_records',
	}


def detect_recent_anomalies(
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
		recent_acc = mean_or_zero([1.0 if item.get('correct') is True else 0.0 for item in recent if item.get('correct') is not None])
		prev_acc = mean_or_zero([1.0 if item.get('correct') is True else 0.0 for item in previous if item.get('correct') is not None]) if previous else recent_acc
		if previous and prev_acc - recent_acc >= 0.3:
			anomalies.append('accuracy_drop')
		if recent_acc <= 0.35:
			anomalies.append('persistent_errors')
	if activity_summary.get('attention_pattern') == 'bursty':
		anomalies.append('fragmented_attention')
	return list(dict.fromkeys(anomalies))


def infer_drop_risk(
	overall_score: float,
	activity_summary: Dict[str, Any],
	dialogue_features: Dict[str, Any],
	recent_anomalies: Sequence[str],
) -> Dict[str, Any]:
	inactivity_penalty = 1.0 - float(activity_summary.get('frequency_score') or 0.0)
	emotion_penalty = 0.8 if dialogue_features['emotion_state']['label'] == 'frustrated' else 0.2
	anomaly_penalty = min(1.0, len(recent_anomalies) / 4.0)
	score = alignment.clip(
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


def build_concept_gaps(
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
		if token in joined and any(term in joined for term in DIFFICULTY_TERMS):
			gaps.append(token)
	return dedupe_concept_gaps(gaps, limit=10)


def build_evidence(
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
		evidence.append('最近超过14天无新学习事件')
	return list(dict.fromkeys(evidence))[:8]


def build_confidence(
	events: Sequence[dict],
	latest_ts: int,
	source_events: Sequence[str],
	week_signals: Sequence[dict],
	now_ts: int,
) -> float:
	sample_factor = alignment.clip(len(events) / 18.0)
	source_factor = alignment.clip(len(source_events) / 4.0)
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
	return round(alignment.clip(0.38 * sample_factor + 0.26 * source_factor + 0.24 * freshness_factor + week_factor), 4)


def compute_learning_profile_bundle(state: Dict[str, Any], normalize_events) -> Dict[str, Any]:
	if not state.get('normalized_events'):
		normalize_events(state)
	if not state.get('loaded_personal_syllabuses'):
		state['loaded_personal_syllabuses'] = []
	normalized = state.get('normalized_events') if isinstance(state.get('normalized_events'), dict) else {}
	history_entries = state.get('history_entries') or []
	loaded_personal_syllabuses = state.get('loaded_personal_syllabuses') or []
	dialogue_texts = state.get('dialogue_texts') or []
	learning_goal = alignment.safe_text(state.get('learning_goal'))
	now_ts = int(state.get('now_ts') or time())
	profile_scope = state.get('profile_scope') or []
	user = state.get('user')
	all_events = normalized['all_events']
	learning_events = normalized['learning_events']
	answer_events = normalized['answer_events']
	resource_events = normalized['resource_events']
	combined_goal = build_goal_text(learning_goal, dialogue_texts, loaded_personal_syllabuses)

	week_signals = [build_week_signals(personal_json, syllabus_json) for _, personal_json, syllabus_json in loaded_personal_syllabuses]
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

	dialogue_features = alignment.extract_dialogue_features(dialogue_texts, learning_goal, score_to_band=score_to_band)
	question_texts = normalized['question_texts']
	all_texts = normalized['all_texts']
	activity_summary = summarize_activity(all_events, now_ts)
	latest_ts = int(activity_summary.get('latest_ts') or 0) or now_ts

	answer_mastery = build_answer_mastery(answer_events, latest_ts)
	answer_mastery_scores = answer_mastery['by_knowledge_point']
	knowledge_point_details = answer_mastery['knowledge_point_details']
	answer_mean = mean_or_zero(list(answer_mastery_scores.values()))
	engagement_score = round(
		alignment.clip(
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
		overall_score = round(alignment.clip(0.75 * answer_mean + 0.25 * engagement_score), 4)

	resource_pref = infer_topic_preferences(all_texts, resource_events)
	learning_style = infer_learning_style(resource_pref)
	answer_pattern = infer_answer_pattern(question_texts or all_texts)
	comprehension_level = infer_comprehension_level(question_texts, overall_score)
	practice_ability = infer_practice_ability(resource_pref, overall_score, answer_events, activity_summary)
	difficulty_tolerance = infer_difficulty_tolerance(answer_events, activity_summary, dialogue_features)
	conflict_resolution = infer_conflict_resolution(dialogue_features['self_reported_difficulty'], overall_score)
	recent_anomaly = detect_recent_anomalies(answer_events, activity_summary, dialogue_features, now_ts)
	drop_risk = infer_drop_risk(overall_score, activity_summary, dialogue_features, recent_anomaly)
	concept_gaps = build_concept_gaps(all_concept_gaps, knowledge_point_details, dialogue_texts)
	bottleneck_topics = concept_gaps[:8]
	source_events = sorted({event['source'] for event in all_events if event.get('source')})
	global_confidence = build_confidence(all_events, latest_ts, source_events, week_signals, now_ts)
	evidence = build_evidence(activity_summary, dialogue_features, knowledge_point_details, week_signals, recent_anomaly)

	knowledge_mapping = {
		'mapped_nodes': sorted(knowledge_point_details.keys()),
		'mapped_node_count': len(knowledge_point_details),
		'graph_binding': 'knowledge_point_proxy_nodes',
	}

	goal_text = combined_goal or alignment.safe_text(getattr(user, 'user_name', None)) or '未提供'
	target_level = '入门'
	if overall_score >= 0.85:
		target_level = '熟练'
	elif overall_score >= 0.7:
		target_level = '进阶'

	mastery_level = 'none'
	if week_signals:
		mastery_level = week_signals[0]['overall_level'] if len(week_signals) == 1 else level_from_score(overall_score * 4.0)
	elif answer_mastery_scores:
		mastery_level = level_from_score(overall_score * 4.0)

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
