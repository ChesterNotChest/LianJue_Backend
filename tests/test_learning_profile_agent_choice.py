import os
from types import SimpleNamespace

import pytest

from tasks import learning_profile_task as lpt


EXPECTED_TOOL_ORDER = [
    "load_history_context",
    "load_personal_syllabus_context",
    "normalize_events",
    "compute_features",
    "assemble_profile",
]


def _normalize_model_for_dashscope():
    text_config = lpt.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        lpt.get_learning_profile_agent.cache_clear()


def _trace_agent_tools(monkeypatch):
    trace = []

    def wrap(tool_name, func):
        def traced(state):
            trace.append(tool_name)
            result = func(state)
            state["tool_trace"] = trace[:]
            return result

        return traced

    monkeypatch.setattr(
        lpt,
        "_tool_load_existing_profile_context",
        wrap("load_existing_profile_context", lpt._tool_load_existing_profile_context),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_load_history_context",
        wrap("load_history_context", lpt._tool_load_history_context),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_load_personal_syllabus_context",
        wrap("load_personal_syllabus_context", lpt._tool_load_personal_syllabus_context),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_normalize_events",
        wrap("normalize_events", lpt._tool_normalize_events),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_compute_features",
        wrap("compute_features", lpt._tool_compute_features),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_assemble_profile",
        wrap("assemble_profile", lpt._tool_assemble_profile),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_save_or_update_profile",
        wrap("save_or_update_profile", lpt._tool_save_or_update_profile),
    )
    lpt.get_learning_profile_agent.cache_clear()
    return trace


@pytest.mark.llm
def test_learning_profile_agent_selects_expected_tools(monkeypatch):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real learning profile agent choice smoke test.")

    _normalize_model_for_dashscope()
    user = SimpleNamespace(
        user_id=501,
        user_name="agent-smoke",
        email="agent-smoke@example.com",
    )
    monkeypatch.setattr(lpt, "get_user_by_id", lambda user_id: user if user_id == 501 else None)
    monkeypatch.setattr(lpt, "list_user_syllabuses", lambda user_id: [])
    monkeypatch.setattr(lpt, "get_syllabus_by_id", lambda syllabus_id: None)
    monkeypatch.setattr(lpt, "_collect_history_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr(lpt, "_load_personal_syllabus", lambda *args, **kwargs: [])

    trace = _trace_agent_tools(monkeypatch)

    try:
        profile = lpt.build_learning_profile(
            user_id=501,
            dialogue_text=[
                "我最近在学 Python，函数参数总是搞不懂。",
                "我希望两周内掌握循环和函数，并多做一点练习。",
            ],
            learning_goal="掌握 Python 基础语法",
            learning_records=[
                {
                    "event_type": "study_session",
                    "duration_minutes": 42,
                    "started_at": 1759913600,
                    "meta": {"topic": "循环"},
                },
                {
                    "event_type": "practice",
                    "duration_minutes": 36,
                    "started_at": 1759996400,
                    "meta": {"topic": "函数"},
                },
            ],
            answer_records=[
                {
                    "question": "函数参数应该怎么传递？",
                    "correct": False,
                    "answered_at": 1759998200,
                    "time_spent_seconds": 160,
                    "meta": {"knowledge_points": ["函数参数"]},
                },
                {
                    "question": "循环嵌套如何执行？",
                    "correct": True,
                    "answered_at": 1759999000,
                    "time_spent_seconds": 100,
                    "meta": {"knowledge_points": ["循环嵌套"]},
                },
                {
                    "question": "函数返回值是什么？",
                    "correct": False,
                    "answered_at": 1759999800,
                    "time_spent_seconds": 180,
                    "meta": {"knowledge_points": ["函数参数"]},
                },
            ],
            resource_usage=[
                {
                    "resource_id": "video_python_functions",
                    "action": "complete",
                    "timestamp": 1759999900,
                    "duration_seconds": 900,
                    "meta": {"knowledge_points": ["函数参数"]},
                }
            ],
        )
    finally:
        lpt.get_learning_profile_agent.cache_clear()

    assert trace == EXPECTED_TOOL_ORDER
    assert profile is not None
    assert profile["user_id"] == 501
    assert len(profile) >= 30
    assert "函数参数" in profile["concept_gaps"]
    assert profile["source_events"] == ["answer_records", "learning_records", "resource_usage"]
    assert profile["knowledge_mastery"]["knowledge_point_details"]["函数参数"]["attempt_count"] == 2
