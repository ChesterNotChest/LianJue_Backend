from types import SimpleNamespace

from tasks import learning_profile_task as lpt


def test_learning_profile_agent_and_model_can_initialize():
    model = lpt._build_learning_profile_model()
    agent = lpt.get_learning_profile_agent()

    assert type(model).__name__ in {"OpenAIModel", "OpenAIChatModel"}
    assert agent.name == "learning_profile_agent"
    assert agent.output_type is lpt.LearningProfileResult


def test_learning_profile_toolchain_builds_profile_without_llm():
    state = {
        "user_id": 1,
        "syllabus_id": None,
        "user": SimpleNamespace(
            user_id=1,
            user_name="toolchain-smoke",
            email="toolchain-smoke@example.com",
        ),
        "user_syllabuses": [],
        "profile_scope": [],
        "dialogue_texts": [
            "我最近在学 Python，函数参数总是搞不懂。",
            "我希望两周内掌握循环和函数。",
        ],
        "learning_goal": "掌握 Python 基础语法",
        "learning_records": [
            {
                "event_type": "study_session",
                "duration_minutes": 42,
                "started_at": 1759913600,
                "meta": {"topic": "循环"},
            }
        ],
        "answer_records": [
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
        ],
        "resource_usage": [
            {
                "resource_id": "video_python_functions",
                "action": "complete",
                "timestamp": 1759999900,
                "duration_seconds": 900,
                "meta": {"knowledge_points": ["函数参数"]},
            }
        ],
        "now_ts": 1760000000,
        "history_entries": [],
        "loaded_personal_syllabuses": [],
        "history_loaded": False,
        "personal_syllabus_loaded": False,
        "normalized_events": {},
        "feature_bundle": {},
        "profile": None,
        "tool_trace": [],
    }

    normalized = lpt._tool_normalize_events(state)
    features = lpt._tool_compute_features(state)
    assembled = lpt._tool_assemble_profile(state)

    profile = state["profile"]

    assert normalized["event_counts"]["all_events"] == 4
    assert features["feature_count"] >= 30
    assert assembled["profile_ready"] is True
    assert isinstance(profile, dict)
    assert len(profile) >= 30
    assert profile["user_id"] == 1
    assert "函数参数" in profile["concept_gaps"]
    assert profile["knowledge_mastery"]["knowledge_point_details"]["函数参数"]["attempt_count"] == 1
    assert profile["source_events"] == ["answer_records", "learning_records", "resource_usage"]


def test_learning_profile_result_schema_accepts_profile():
    result = lpt.LearningProfileResult(
        success=True,
        profile={"user_id": 1, "confidence": 0.5},
    )

    assert result.success is True
    assert result.profile["user_id"] == 1
    assert result.error_message == ""
