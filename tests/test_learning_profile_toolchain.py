from types import SimpleNamespace

from flask import Flask

from blueprint import user_api
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
        "existing_profile": None,
        "existing_profile_path": None,
        "existing_profile_loaded": False,
        "loaded_personal_syllabuses": [],
        "history_loaded": False,
        "personal_syllabus_loaded": False,
        "normalized_events": {},
        "feature_bundle": {},
        "profile": None,
        "profile_path": None,
        "profile_saved": False,
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


def test_learning_profile_save_tool_persists_course_profile(monkeypatch):
    state = {
        "user_id": 2,
        "syllabus_id": 9,
        "profile": {"user_id": 2, "confidence": 0.7, "updated_at": 1760000000},
        "existing_profile": {"profile_revision": 3, "updated_at": 1750000000, "confidence": 0.4},
        "profile_path": None,
        "profile_saved": False,
    }
    updated_paths = []
    monkeypatch.setattr(
        lpt,
        "set_personal_profile_path",
        lambda user_id, syllabus_id, path: updated_paths.append((user_id, syllabus_id, path)) or True,
    )

    result = lpt._tool_save_or_update_profile(state)

    assert result["saved"] is True
    assert result["profile_revision"] == 4
    assert state["profile_saved"] is True
    assert state["profile"]["profile_saved"] is True
    assert state["profile"]["previous_confidence"] == 0.4
    assert updated_paths == [(2, 9, state["profile_path"])]
    assert state["profile_path"].endswith("profiles\\9-2.json") or state["profile_path"].endswith("profiles/9-2.json")


def test_learning_profile_fallback_prefers_existing_profile_then_save():
    load_state = {
        "user_id": 2,
        "syllabus_id": 9,
        "existing_profile_loaded": False,
    }
    assert lpt._fallback_next_learning_profile_tool(load_state)["tool_name"] == "load_existing_profile_context"

    save_state = {
        "user_id": 2,
        "syllabus_id": 9,
        "existing_profile_loaded": True,
        "history_loaded": True,
        "personal_syllabus_loaded": True,
        "normalized_events": {"all_events": []},
        "feature_bundle": {"profile": {}},
        "profile": {"user_id": 2},
        "profile_saved": False,
    }
    assert lpt._fallback_next_learning_profile_tool(save_state)["tool_name"] == "save_or_update_profile"


def test_get_or_build_learning_profile_returns_persisted_profile_without_refresh(monkeypatch):
    persisted = {
        "user_id": 3,
        "syllabus_scope": [{"syllabus_id": 11}],
        "confidence": 0.8,
        "profile_path": "profiles/11-3.json",
        "saved_at": 1760000000,
    }
    build_calls = []
    monkeypatch.setattr(lpt, "_load_existing_profile", lambda user_id, syllabus_id: (persisted, persisted["profile_path"]))
    monkeypatch.setattr(lpt, "build_learning_profile", lambda *args, **kwargs: build_calls.append((args, kwargs)) or {"user_id": 3})

    profile = lpt.get_or_build_learning_profile(3, 11)

    assert profile["confidence"] == 0.8
    assert profile["profile_saved"] is True
    assert profile["profile_refreshed"] is False
    assert build_calls == []


def test_get_or_build_learning_profile_builds_when_missing_or_refreshing(monkeypatch):
    build_calls = []

    def fake_build(*args, **kwargs):
        build_calls.append((args, kwargs))
        return {"user_id": args[0], "confidence": 0.6}

    monkeypatch.setattr(lpt, "_load_existing_profile", lambda user_id, syllabus_id: (None, None))
    monkeypatch.setattr(lpt, "build_learning_profile", fake_build)

    missing_profile = lpt.get_or_build_learning_profile(4, 12)

    assert missing_profile["profile_refreshed"] is True
    assert len(build_calls) == 1

    persisted = {
        "user_id": 4,
        "syllabus_scope": [{"syllabus_id": 12}],
        "confidence": 0.9,
        "profile_path": "profiles/12-4.json",
        "saved_at": 1760000000,
    }
    monkeypatch.setattr(lpt, "_load_existing_profile", lambda user_id, syllabus_id: (persisted, persisted["profile_path"]))

    refreshed_profile = lpt.get_or_build_learning_profile(4, 12, refresh_profile=True)

    assert refreshed_profile["profile_refreshed"] is True
    assert len(build_calls) == 2


def test_get_persisted_learning_profile_rejects_identity_mismatch(monkeypatch):
    wrong_user = {
        "user_id": 99,
        "syllabus_scope": [{"syllabus_id": 12}],
        "profile_path": "profiles/12-99.json",
        "saved_at": 1760000000,
    }
    wrong_syllabus = {
        "user_id": 4,
        "syllabus_scope": [{"syllabus_id": 99}],
        "profile_path": "profiles/99-4.json",
        "saved_at": 1760000000,
    }

    monkeypatch.setattr(lpt, "_load_existing_profile", lambda user_id, syllabus_id: (wrong_user, wrong_user["profile_path"]))
    assert lpt.get_persisted_learning_profile(4, 12) is None

    monkeypatch.setattr(lpt, "_load_existing_profile", lambda user_id, syllabus_id: (wrong_syllabus, wrong_syllabus["profile_path"]))
    assert lpt.get_persisted_learning_profile(4, 12) is None


def test_user_learning_profile_api_defaults_to_cached_read_and_parses_refresh(monkeypatch):
    app = Flask(__name__)
    calls = []

    def fake_get_or_build(user_id, syllabus_id=None, **kwargs):
        calls.append(kwargs)
        return {
            "user_id": user_id,
            "syllabus_scope": [{"syllabus_id": syllabus_id}],
            "profile_path": "profiles/21-5.json",
            "profile_saved": True,
            "profile_refreshed": kwargs["refresh_profile"],
        }

    monkeypatch.setattr(user_api, "get_or_build_learning_profile", fake_get_or_build)

    with app.test_request_context(
        "/api/user_learning_profile",
        method="POST",
        json={"user_id": 5, "syllabus_id": 21, "refresh_profile": "false"},
    ):
        response = user_api.user_learning_profile_api()

    assert response.status_code == 200
    assert calls[-1]["refresh_profile"] is False
    assert response.get_json()["profile_refreshed"] is False

    with app.test_request_context(
        "/api/user_learning_profile",
        method="POST",
        json={"user_id": 5, "syllabus_id": 21, "refresh_profile": "true"},
    ):
        response = user_api.user_learning_profile_api()

    assert response.status_code == 200
    assert calls[-1]["refresh_profile"] is True
    assert response.get_json()["profile_refreshed"] is True


def test_learning_profile_result_schema_accepts_profile():
    result = lpt.LearningProfileResult(
        success=True,
        profile={"user_id": 1, "confidence": 0.5},
    )

    assert result.success is True
    assert result.profile["user_id"] == 1
    assert result.error_message == ""
