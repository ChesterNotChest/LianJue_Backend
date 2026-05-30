from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from config import OPENAI_COMPAT_MODEL_CONFIGS
from tasks.learning_profile import alignment
from tasks.learning_profile.models import LearningProfileDeps, LearningProfileResult
from tasks.learning_profile.agent_tools import (
    _tool_assemble_profile,
    _tool_compute_features,
    _tool_init_personal_syllabus_context,
    _tool_load_existing_profile_context,
    _tool_load_history_context,
    _tool_load_personal_syllabus_context,
    _tool_normalize_events,
    _tool_read_personal_syllabus_context,
    _tool_save_or_update_profile,
)

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
			"You are the Learning Profile Agent. Use the registered tools step by step "
			"to load context, normalize events, compute features, assemble the profile, "
			"and save it when syllabus_id is present. Call one tool at a time. "
			"Typical order: load_existing_profile_context, load_history_context, "
			"load_personal_syllabus_context, normalize_events, compute_features, "
			"assemble_profile, save_or_update_profile. Return only a LearningProfileResult JSON object."
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

