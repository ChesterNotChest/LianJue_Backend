from __future__ import annotations

import json
import os
from statistics import mean
from time import time
from typing import Any, Optional, Tuple

from constant import BasePath, PersonalSyllabus, ProfilePersonalSyllabusSuggestionSource, ProfilePersonalSyllabusSuggestionThreshold
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_syllabus_repo import get_user_syllabus, set_personal_syllabus_path
from tasks.learning_profile import alignment
from tasks.learning_profile import profile_builder
from tasks.learning_profile.storage import load_json_file

_PROFILE_SUGGESTION_TO_SCORE = {
	'weak_far': 0,
	'weak': 1,
	'normal': 2,
	'master': 3,
	'master_far': 4,
}

_PROFILE_COMPETANCE_ORDER = ['weak', 'normal', 'master']


def _personal_syllabus_root_dir(user_id: Optional[int] = None) -> str:
	root_name = str(BasePath.PERSONAL_SYLLABUS_ROOT.value).strip().strip('/\\')
	root = os.path.abspath(os.path.join(os.getcwd(), root_name))
	if user_id is None:
		return root
	return os.path.join(root, f'user_{int(user_id)}')


def _build_profile_personal_syllabus_path(user_id: int, syllabus_id: int) -> str:
	root = _personal_syllabus_root_dir(user_id)
	os.makedirs(root, exist_ok=True)
	return os.path.abspath(os.path.join(root, f'{int(syllabus_id)}_personal.json'))


def _hydrate_profile_personal_syllabus(personal_json: dict, syllabus_id: int) -> dict:
	if not isinstance(personal_json, dict):
		return personal_json
	syllabus = get_syllabus_by_id(syllabus_id)
	syllabus_json = load_json_file(getattr(syllabus, 'syllabus_path', None)) if syllabus else None
	if not isinstance(syllabus_json, dict):
		return personal_json

	syllabus_period = syllabus_json.get('period', [])
	personal_period = personal_json.get('period', [])
	if not isinstance(syllabus_period, list) or not isinstance(personal_period, list):
		return personal_json

	syllabus_by_week = {
		str(entry.get('week_index')): entry
		for entry in syllabus_period
		if isinstance(entry, dict) and entry.get('week_index') is not None
	}
	for entry in personal_period:
		if not isinstance(entry, dict) or entry.get('week_index') is None:
			continue
		source = syllabus_by_week.get(str(entry.get('week_index')))
		if not isinstance(source, dict):
			continue
		for key in ('content', 'enhanced_content', 'importance'):
			if (key not in entry or entry.get(key) is None) and source.get(key) is not None:
				entry[key] = source.get(key)
		entry.setdefault('competance', 'none')
		entry.setdefault('competance_progress', 0)
		entry.setdefault('suggested_competance_list', [])
		entry.setdefault('suggestion_review_count', 0)
		entry.setdefault('suggestion_history', [])
		entry.setdefault('updated_at', 0)
	return personal_json


def read_profile_personal_syllabus(user_id: int, syllabus_id: int, hydrate: bool = True) -> Optional[dict]:
	try:
		user_id = int(user_id)
		syllabus_id = int(syllabus_id)
	except Exception:
		return None
	if user_id <= 0 or syllabus_id <= 0:
		return None
	try:
		relation = get_user_syllabus(user_id, syllabus_id)
	except Exception:
		relation = None
	path = getattr(relation, 'personal_syllabus_path', None) if relation else None
	if not path:
		return None
	personal_json = load_json_file(path)
	if not isinstance(personal_json, dict):
		return None
	if hydrate:
		personal_json = _hydrate_profile_personal_syllabus(personal_json, syllabus_id)
	return personal_json


def init_profile_personal_syllabus(user_id: int, syllabus_id: int) -> Optional[dict]:
	try:
		user_id = int(user_id)
		syllabus_id = int(syllabus_id)
	except Exception:
		return None
	if user_id <= 0 or syllabus_id <= 0:
		return None

	syllabus = get_syllabus_by_id(syllabus_id)
	syllabus_json = load_json_file(getattr(syllabus, 'syllabus_path', None)) if syllabus else None
	if not isinstance(syllabus_json, dict):
		return None

	personal_json = {
		'syllabus_id': syllabus_id,
		'user_id': user_id,
		'period': [],
	}
	for entry in syllabus_json.get('period', []) if isinstance(syllabus_json.get('period'), list) else []:
		if not isinstance(entry, dict):
			continue
		personal_json['period'].append({
			'week_index': entry.get('week_index'),
			'content': entry.get('content'),
			'enhanced_content': entry.get('enhanced_content'),
			'importance': entry.get('importance'),
			'competance': 'none',
			'competance_progress': 0,
			'suggested_competance_list': [],
			'suggestion_review_count': 0,
			'suggestion_history': [],
			'updated_at': 0,
		})

	personal_path = _build_profile_personal_syllabus_path(user_id, syllabus_id)
	try:
		with open(personal_path, 'w', encoding='utf-8') as f:
			json.dump(personal_json, f, ensure_ascii=False, indent=2)
		if not set_personal_syllabus_path(user_id, syllabus_id, personal_path):
			return None
	except Exception:
		return None

	return {
		'personal_syllabus_path': personal_path,
		'personal_syllabus': personal_json,
	}


def _find_profile_personal_syllabus_week(personal_syllabus: dict, week_index: Any) -> Optional[dict]:
	try:
		target_week = int(week_index)
	except Exception:
		return None
	for entry in personal_syllabus.get('period', []) if isinstance(personal_syllabus, dict) else []:
		if not isinstance(entry, dict):
			continue
		try:
			if int(entry.get('week_index')) == target_week:
				return entry
		except Exception:
			continue
	return None


def normalize_profile_personal_syllabus_suggestion(
	suggestion: dict,
	default_source: str = ProfilePersonalSyllabusSuggestionSource.PROFILE_AGENT.value,
) -> Optional[dict]:
	if not isinstance(suggestion, dict):
		return None
	try:
		week_index = int(suggestion.get('week_index'))
	except Exception:
		return None
	suggested = alignment.safe_text(suggestion.get('suggested_competance') or suggestion.get('competance') or suggestion.get('level')).lower()
	if suggested not in _PROFILE_SUGGESTION_TO_SCORE:
		return None
	try:
		confidence = float(suggestion.get('confidence'))
	except Exception:
		confidence = 0.0
	confidence = alignment.clip(confidence)
	try:
		confidence_min = float(ProfilePersonalSyllabusSuggestionThreshold.CONFIDENCE_MIN.value)
	except Exception:
		confidence_min = 0.65
	if confidence < confidence_min:
		return None
	evidence = suggestion.get('evidence')
	if evidence is None:
		evidence_list = []
	elif isinstance(evidence, list):
		evidence_list = [alignment.safe_text(item) for item in evidence if alignment.safe_text(item)]
	else:
		evidence_list = [alignment.safe_text(evidence)] if alignment.safe_text(evidence) else []
	source = alignment.safe_text(suggestion.get('source') or default_source) or default_source
	return {
		'week_index': week_index,
		'suggested_competance': suggested,
		'confidence': confidence,
		'reason': alignment.safe_text(suggestion.get('reason')),
		'evidence': evidence_list,
		'source': source,
		'created_at': int(suggestion.get('created_at') or time()),
	}


def _profile_suggestion_to_base_level(suggested: str) -> str:
	if suggested == 'weak_far':
		return 'weak'
	if suggested == 'master_far':
		return 'master'
	if suggested in _PROFILE_COMPETANCE_ORDER:
		return suggested
	return 'normal'


def _apply_profile_personal_syllabus_level(entry: dict, suggested_level: str) -> bool:
	current = alignment.safe_text(entry.get('competance') or 'none').lower()
	try:
		progress = int(entry.get('competance_progress') or 0)
	except Exception:
		progress = 0

	base_level = _profile_suggestion_to_base_level(suggested_level)
	if current not in _PROFILE_COMPETANCE_ORDER:
		entry['competance'] = base_level
		entry['competance_progress'] = 0
		entry['updated_at'] = int(time())
		return True

	current_index = _PROFILE_COMPETANCE_ORDER.index(current)
	target_index = _PROFILE_COMPETANCE_ORDER.index(base_level)
	if target_index == current_index:
		if current == 'normal':
			progress += 1
	else:
		progress += target_index - current_index
	if suggested_level == 'weak_far':
		progress -= 1
	elif suggested_level == 'master_far':
		progress += 1

	try:
		progress_max = int(PersonalSyllabus.PROGRESS_MAX.value)
		progress_min = int(PersonalSyllabus.PROGRESS_MIN.value)
	except Exception:
		progress_max = 5
		progress_min = -5

	new_index = current_index
	if progress >= progress_max and current_index < len(_PROFILE_COMPETANCE_ORDER) - 1:
		new_index += 1
		progress = 0
	elif progress <= progress_min and current_index > 0:
		new_index -= 1
		progress = 0

	changed = entry.get('competance') != _PROFILE_COMPETANCE_ORDER[new_index] or int(entry.get('competance_progress') or 0) != progress
	entry['competance'] = _PROFILE_COMPETANCE_ORDER[new_index]
	entry['competance_progress'] = progress
	if changed:
		entry['updated_at'] = int(time())
	return changed


def maybe_apply_profile_personal_syllabus_progress(personal_syllabus: dict, week_index: int) -> Tuple[dict, bool]:
	entry = _find_profile_personal_syllabus_week(personal_syllabus, week_index)
	if not isinstance(entry, dict):
		return personal_syllabus, False
	try:
		threshold = int(ProfilePersonalSyllabusSuggestionThreshold.WEEK_REVIEW_THRESHOLD.value)
	except Exception:
		threshold = 5
	try:
		review_count = int(entry.get('suggestion_review_count') or 0)
	except Exception:
		review_count = 0
	if review_count < threshold:
		return personal_syllabus, False

	suggestion_list = entry.get('suggested_competance_list') or []
	scores = [
		_PROFILE_SUGGESTION_TO_SCORE.get(alignment.safe_text(item).lower())
		for item in suggestion_list
		if alignment.safe_text(item).lower() in _PROFILE_SUGGESTION_TO_SCORE
	]
	applied = False
	if scores:
		suggested_level = profile_builder.level_from_score(mean(scores))
		applied = _apply_profile_personal_syllabus_level(entry, suggested_level)
	entry['suggested_competance_list'] = []
	entry['suggestion_review_count'] = 0
	return personal_syllabus, applied


def append_profile_personal_syllabus_suggestion(user_id: int, syllabus_id: int, suggestion: dict) -> Optional[dict]:
	normalized = normalize_profile_personal_syllabus_suggestion(suggestion)
	if normalized is None:
		return None
	try:
		user_id = int(user_id)
		syllabus_id = int(syllabus_id)
	except Exception:
		return None

	relation = get_user_syllabus(user_id, syllabus_id)
	personal_path = getattr(relation, 'personal_syllabus_path', None) if relation else None
	personal_syllabus = read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)
	if not isinstance(personal_syllabus, dict):
		created = init_profile_personal_syllabus(user_id, syllabus_id)
		if not isinstance(created, dict):
			return None
		personal_syllabus = created.get('personal_syllabus')
		personal_path = created.get('personal_syllabus_path')
	if not isinstance(personal_syllabus, dict):
		return None
	if not personal_path:
		relation = get_user_syllabus(user_id, syllabus_id)
		personal_path = getattr(relation, 'personal_syllabus_path', None) if relation else None
	if not personal_path:
		return None

	entry = _find_profile_personal_syllabus_week(personal_syllabus, normalized['week_index'])
	if not isinstance(entry, dict):
		return None
	entry.setdefault('suggested_competance_list', [])
	entry.setdefault('suggestion_history', [])
	entry.setdefault('suggestion_review_count', 0)
	entry['suggested_competance_list'].append(normalized['suggested_competance'])
	entry['suggestion_history'].append(normalized)
	try:
		history_max = int(ProfilePersonalSyllabusSuggestionThreshold.SUGGESTION_HISTORY_MAX.value)
	except Exception:
		history_max = 50
	if len(entry['suggestion_history']) > history_max:
		entry['suggestion_history'] = entry['suggestion_history'][-history_max:]
	try:
		entry['suggestion_review_count'] = int(entry.get('suggestion_review_count') or 0) + 1
	except Exception:
		entry['suggestion_review_count'] = 1

	personal_syllabus, applied = maybe_apply_profile_personal_syllabus_progress(personal_syllabus, normalized['week_index'])
	entry = _find_profile_personal_syllabus_week(personal_syllabus, normalized['week_index']) or entry
	try:
		with open(personal_path, 'w', encoding='utf-8') as f:
			json.dump(personal_syllabus, f, ensure_ascii=False, indent=2)
	except Exception:
		return None

	return {
		'personal_syllabus': personal_syllabus,
		'personal_syllabus_path': personal_path,
		'suggestion': normalized,
		'applied': bool(applied),
		'week_index': normalized['week_index'],
		'suggestion_review_count': int(entry.get('suggestion_review_count') or 0),
		'competance': entry.get('competance'),
		'competance_progress': entry.get('competance_progress'),
	}

