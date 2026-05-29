from __future__ import annotations

from typing import Any, Dict, List

from constant import ProfilePersonalSyllabusSuggestionSource
from repositories.syllabus_repo import get_syllabus_by_id
from tasks.learning_profile import alignment
from tasks.learning_profile import profile_builder
from tasks.learning_profile import storage as profile_storage
from tasks.learning_profile.personal_syllabus import init_profile_personal_syllabus, read_profile_personal_syllabus
from tasks.learning_profile.storage import load_existing_profile, load_json_file, merge_profile_update

def _tool_load_history_context(state: Dict[str, Any]) -> Dict[str, Any]:
	from tasks.learning_profile.service import collect_history_entries

	history_entries = collect_history_entries(int(state['user_id']), syllabus_id=state.get('syllabus_id'))
	state['history_entries'] = history_entries
	state['history_loaded'] = True
	return {
		'tool': 'load_history_context',
		'history_count': len(history_entries),
		'has_history': bool(history_entries),
	}


def _tool_load_existing_profile_context(state: Dict[str, Any]) -> Dict[str, Any]:
	existing_profile, profile_path = load_existing_profile(int(state['user_id']), state.get('syllabus_id'))
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
	from tasks.learning_profile.service import load_personal_syllabus_rows

	loaded_personal_syllabuses = load_personal_syllabus_rows(int(state['user_id']), state.get('syllabus_id'))
	initialized = False
	if not loaded_personal_syllabuses and state.get('syllabus_id') is not None:
		created = init_profile_personal_syllabus(int(state['user_id']), int(state['syllabus_id']))
		if isinstance(created, dict):
			initialized = True
			personal_json = created.get('personal_syllabus') if isinstance(created.get('personal_syllabus'), dict) else {}
			syllabus = get_syllabus_by_id(int(state['syllabus_id']))
			syllabus_json = load_json_file(getattr(syllabus, 'syllabus_path', None)) if syllabus else None
			loaded_personal_syllabuses = [
				(
					int(state['syllabus_id']),
					personal_json,
					syllabus_json if isinstance(syllabus_json, dict) else {},
				)
			]
	state['loaded_personal_syllabuses'] = loaded_personal_syllabuses
	state['personal_syllabus_loaded'] = True
	return {
		'tool': 'load_personal_syllabus_context',
		'personal_syllabus_count': len(loaded_personal_syllabuses),
		'initialized': initialized,
	}


def _tool_read_personal_syllabus_context(state: Dict[str, Any]) -> Dict[str, Any]:
	personal_syllabus = None
	if state.get('syllabus_id') is not None:
		personal_syllabus = read_profile_personal_syllabus(int(state['user_id']), int(state['syllabus_id']))
	state['profile_personal_syllabus'] = personal_syllabus
	state['profile_personal_syllabus_loaded'] = True
	period = personal_syllabus.get('period') if isinstance(personal_syllabus, dict) else []
	return {
		'tool': 'read_personal_syllabus_context',
		'loaded': True,
		'has_personal_syllabus': isinstance(personal_syllabus, dict),
		'week_count': len(period) if isinstance(period, list) else 0,
	}


def _tool_init_personal_syllabus_context(state: Dict[str, Any]) -> Dict[str, Any]:
	created = None
	if state.get('syllabus_id') is not None:
		created = init_profile_personal_syllabus(int(state['user_id']), int(state['syllabus_id']))
	personal_syllabus = created.get('personal_syllabus') if isinstance(created, dict) else None
	state['profile_personal_syllabus'] = personal_syllabus
	state['profile_personal_syllabus_loaded'] = isinstance(personal_syllabus, dict)
	period = personal_syllabus.get('period') if isinstance(personal_syllabus, dict) else []
	return {
		'tool': 'init_personal_syllabus_context',
		'created': isinstance(created, dict),
		'personal_syllabus_path': created.get('personal_syllabus_path') if isinstance(created, dict) else None,
		'week_count': len(period) if isinstance(period, list) else 0,
	}


def _tool_normalize_events(state: Dict[str, Any]) -> Dict[str, Any]:
	history_entries = state.get('history_entries') or []
	learning_records = state.get('learning_records')
	answer_records = state.get('answer_records')
	resource_usage = state.get('resource_usage')
	history_events = alignment.normalize_history_events(history_entries)
	learning_events = alignment.normalize_learning_events(learning_records)
	answer_events = alignment.normalize_answer_events(answer_records)
	resource_events = alignment.normalize_resource_events(resource_usage)
	all_events = [*history_events, *learning_events, *answer_events, *resource_events]
	normalized_events = {
		'history_events': history_events,
		'learning_events': learning_events,
		'answer_events': answer_events,
		'resource_events': resource_events,
		'all_events': all_events,
		'question_texts': alignment.flatten_text_inputs([item.get('question') for item in history_entries], state.get('dialogue_texts') or []),
		'all_texts': list(dict.fromkeys(alignment.flatten_text_inputs(
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
	return profile_builder.compute_learning_profile_bundle(state, normalize_events=_tool_normalize_events)


def _build_personal_syllabus_update_suggestions(profile: dict, feature_bundle: dict) -> List[dict]:
	if not isinstance(profile, dict) or not isinstance(feature_bundle, dict):
		return []
	confidence = alignment.clip(float(profile.get('confidence') or feature_bundle.get('global_confidence') or 0.0))

	suggestions: List[dict] = []
	seen_weeks = set()
	for signal in feature_bundle.get('week_signals') or []:
		if not isinstance(signal, dict):
			continue
		week_items = signal.get('week_items') or []
		for item in week_items:
			if not isinstance(item, dict):
				continue
			try:
				week_index = int(item.get('week_index'))
			except Exception:
				continue
			if week_index in seen_weeks:
				continue
			try:
				score = float(item.get('score') or 0.0)
			except Exception:
				score = 0.0
			suggested = None
			if score <= 0.25:
				suggested = 'weak'
			elif score >= 0.85:
				suggested = 'master'
			if not suggested:
				continue
			seen_weeks.add(week_index)
			suggestions.append({
				'week_index': week_index,
				'suggested_competance': suggested,
				'confidence': confidence,
				'reason': f"鐢诲儚璁＄畻鍙戠幇绗?{week_index} 鍛ㄥ涔犵姸鎬佸亸鍚?{suggested}",
				'evidence': ['personal_syllabus', 'learning_profile'],
				'source': ProfilePersonalSyllabusSuggestionSource.PROFILE_AGENT.value,
			})
			if len(suggestions) >= 3:
				return suggestions
	return suggestions


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
	if isinstance(state.get('profile'), dict):
		state['profile']['suggested_personal_syllabus_updates'] = _build_personal_syllabus_update_suggestions(
			state['profile'],
			state.get('feature_bundle') or {},
		)
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

	merged_profile = merge_profile_update(state.get('existing_profile'), state.get('profile') or {})
	saved_profile = profile_storage.save_personal_profile(int(state['user_id']), int(syllabus_id), merged_profile)
	profile_path = saved_profile.get('profile_path') if isinstance(saved_profile, dict) else None
	if saved_profile:
		state['profile'] = saved_profile
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

