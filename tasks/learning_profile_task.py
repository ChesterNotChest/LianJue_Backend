import json
import os
from functools import lru_cache
from statistics import mean
from time import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from config import OPENAI_COMPAT_MODEL_CONFIGS
from constant import BasePath, PersonalSyllabus, ProfilePersonalSyllabusSuggestionSource, ProfilePersonalSyllabusSuggestionThreshold
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_repo import get_user_by_id
from repositories.user_syllabus_repo import get_user_syllabus, list_user_syllabuses, set_personal_profile_path, set_personal_syllabus_path
from tasks.learning_profile import (
	LearningProfileDeps,
	LearningProfileResult,
	build_personal_profile_path,
	load_existing_profile,
	load_json_file,
	merge_profile_update,
	profile_has_required_identity,
)
from tasks.learning_profile import alignment
from tasks.learning_profile import profile_builder
from tasks.learning_profile import storage as profile_storage


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


def _build_learning_profile_model() -> OpenAIModel:
	text_config = OPENAI_COMPAT_MODEL_CONFIGS.get('text') or {}
	model_name = alignment.safe_text(text_config.get('model_name') or text_config.get('name'))
	if not model_name:
		raise RuntimeError('missing MODEL_CONFIGS["text"]["model_name"] for learning profile agent')
	base_url = alignment.safe_text(text_config.get('api_base') or text_config.get('base_url')) or None
	api_key = alignment.safe_text(text_config.get('api_key')) or os.getenv('OPENAI_API_KEY')
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
			'如果 state 中有 syllabus_id 且画像尚未保存，assemble_profile 后必须调用 save_or_update_profile。'
			'最终只能返回符合 LearningProfileResult 结构的 JSON 对象，不要返回解释、Markdown 或自然语言总结。'
			'成功时 JSON 必须包含 {"success": true, "profile": <state.profile>, "error_message": "", "error_code": ""}。'
		),
		name='learning_profile_agent',
		description='Learning profile tool-calling agent',
		retries=2,
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
	def read_personal_syllabus(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_read_personal_syllabus_context(ctx.deps.state)

	@agent.tool(sequential=True)
	def init_personal_syllabus(ctx: RunContext[LearningProfileDeps]) -> dict:
		return _tool_init_personal_syllabus_context(ctx.deps.state)

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
		'learning_goal': alignment.safe_text(state.get('learning_goal')),
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


def fallback_next_learning_profile_tool(state: Dict[str, Any]) -> Dict[str, Any]:
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


def _tool_load_history_context(state: Dict[str, Any]) -> Dict[str, Any]:
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
				'reason': f"画像计算发现第 {week_index} 周学习状态偏向 {suggested}",
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
