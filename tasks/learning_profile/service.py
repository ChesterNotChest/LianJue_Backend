from __future__ import annotations

import os
from time import time
from typing import Any, Dict, List, Optional, Tuple

from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_repo import get_user_by_id
from repositories.user_syllabus_repo import list_user_syllabuses
from tasks.learning_profile import alignment
from tasks.learning_profile.agent_runtime import run_learning_profile_agent
from tasks.learning_profile.agent_tools import _tool_load_existing_profile_context, _tool_save_or_update_profile
from tasks.learning_profile.models import LearningProfileResult
from tasks.learning_profile.storage import load_existing_profile, load_json_file, profile_has_required_identity


def get_persisted_learning_profile(user_id: int, syllabus_id: int) -> Optional[dict]:
	profile, profile_path = load_existing_profile(user_id, syllabus_id)
	if not isinstance(profile, dict):
		return None
	if not profile_has_required_identity(profile, user_id, syllabus_id):
		return None
	result = dict(profile)
	if profile_path:
		result['profile_path'] = profile_path
	result['profile_saved'] = True
	result['profile_refreshed'] = False
	return result


def collect_history_entries(user_id: int, syllabus_id: Optional[int] = None) -> List[dict]:
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
		data = load_json_file(path)
		if isinstance(data, list):
			for item in data:
				if isinstance(item, dict):
					entries.append(item)
	return entries


def load_personal_syllabus_rows(user_id: int, syllabus_id: Optional[int] = None) -> List[Tuple[int, dict, dict]]:
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
		personal_json = load_json_file(path)
		if not isinstance(personal_json, dict):
			continue
		syllabus = get_syllabus_by_id(getattr(relation, 'syllabus_id', None))
		syllabus_json = load_json_file(getattr(syllabus, 'syllabus_path', None)) if syllabus else None
		loaded.append(
			(
				getattr(relation, 'syllabus_id', None),
				personal_json,
				syllabus_json if isinstance(syllabus_json, dict) else {},
			)
		)
	return loaded

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
			'title': alignment.safe_text(getattr(syllabus, 'title', None)) if syllabus else '',
			'personal_syllabus_path': getattr(row, 'personal_syllabus_path', None),
			'personal_profile_path': getattr(row, 'personal_profile_path', None),
		})

	state = {
		'user_id': user_id,
		'syllabus_id': syllabus_id,
		'user': user,
		'user_syllabuses': user_syllabuses,
		'profile_scope': profile_scope,
		'dialogue_texts': alignment.flatten_text_inputs(dialogue_text),
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
	try:
		result = run_learning_profile_agent(state)
	except Exception:
		if state.get('profile'):
			if syllabus_id is not None and not state.get('profile_saved'):
				_tool_save_or_update_profile(state)
			return state['profile']
		raise
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

