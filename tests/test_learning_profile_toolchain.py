from types import SimpleNamespace
from pathlib import Path

from flask import Flask

from blueprint import user_api
from tasks import learning_profile_task as lpt
from tasks.learning_profile import agent_runtime as profile_runtime
from tasks.learning_profile import agent_tools as profile_tools
from tasks.learning_profile import service as profile_service
from tasks.learning_profile import storage as profile_storage
from tasks.learning_profile.models import LearningProfileResult


def test_learning_profile_agent_and_model_can_initialize():
    model = profile_runtime._build_learning_profile_model()
    agent = profile_runtime.get_learning_profile_agent()

    assert type(model).__name__ in {"OpenAIModel", "OpenAIChatModel"}
    assert agent.name == "learning_profile_agent"
    assert agent.output_type is LearningProfileResult


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

    normalized = profile_tools._tool_normalize_events(state)
    features = profile_tools._tool_compute_features(state)
    assembled = profile_tools._tool_assemble_profile(state)

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


def test_learning_profile_concept_gaps_use_short_knowledge_phrases():
    state = {
        "user_id": 3,
        "syllabus_id": 10,
        "user": SimpleNamespace(
            user_id=3,
            user_name="gap-cleanup",
            email="gap-cleanup@example.com",
        ),
        "user_syllabuses": [],
        "profile_scope": [],
        "dialogue_texts": ["我做 RowKey 热点题时经常卡住。"],
        "learning_goal": "掌握 HBase RowKey 设计",
        "learning_records": [],
        "answer_records": [
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "answered_at": 1759998200,
                "time_spent_seconds": 160,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
        "resource_usage": [],
        "now_ts": 1760000000,
        "history_entries": [],
        "existing_profile": None,
        "existing_profile_path": None,
        "existing_profile_loaded": False,
        "loaded_personal_syllabuses": [
            (
                10,
                {
                    "period": [
                        {
                            "week_index": 1,
                            "content": "大数据课程导论与基本概念，理解数据规模、数据类型和处理模式",
                            "enhanced_content": "大数据课程导论与基本概念，理解数据规模、数据类型和处理模式",
                            "competance": "weak",
                            "competance_progress": -1,
                        }
                    ]
                },
                {},
            )
        ],
        "history_loaded": False,
        "personal_syllabus_loaded": True,
        "normalized_events": {},
        "feature_bundle": {},
        "profile": None,
        "profile_path": None,
        "profile_saved": False,
        "tool_trace": [],
    }

    profile_tools._tool_normalize_events(state)
    profile_tools._tool_compute_features(state)
    profile_tools._tool_assemble_profile(state)

    concept_gaps = state["profile"]["concept_gaps"]
    assert "RowKey 热点" in concept_gaps
    assert all(len(gap) <= 24 for gap in concept_gaps)
    assert not any("大数据课程导论与基本概念" in gap for gap in concept_gaps)


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
        profile_storage,
        "set_personal_profile_path",
        lambda user_id, syllabus_id, path: updated_paths.append((user_id, syllabus_id, path)) or True,
    )

    result = profile_tools._tool_save_or_update_profile(state)

    assert result["saved"] is True
    assert result["profile_revision"] == 4
    assert state["profile_saved"] is True
    assert state["profile"]["profile_saved"] is True
    assert state["profile"]["previous_confidence"] == 0.4
    assert updated_paths == [(2, 9, state["profile_path"])]
    assert Path(state["profile_path"]).parts[-2:] == ("profiles", "9-2.json")


def test_build_personal_profile_path_has_no_read_side_effect(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    profile_path = profile_storage.build_personal_profile_path(2, 9)

    assert Path(profile_path).parts[-2:] == ("profiles", "9-2.json")
    assert not (tmp_path / "profiles").exists()


def test_save_personal_profile_removes_temp_file_when_db_update_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(profile_storage, "set_personal_profile_path", lambda user_id, syllabus_id, path: None)
    profile = {"user_id": 2, "syllabus_id": 9, "confidence": 0.7}

    saved = profile_storage.save_personal_profile(2, 9, profile)
    profile_path = Path(profile_storage.build_personal_profile_path(2, 9))

    assert saved is None
    assert not profile_path.exists()
    assert not Path(f"{profile_path}.tmp").exists()
    assert profile == {"user_id": 2, "syllabus_id": 9, "confidence": 0.7}


def test_save_personal_profile_returns_payload_without_mutating_input(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(profile_storage, "set_personal_profile_path", lambda user_id, syllabus_id, path: SimpleNamespace())
    profile = {"user_id": 2, "syllabus_id": 9, "confidence": 0.7}

    saved = profile_storage.save_personal_profile(2, 9, profile)

    assert saved["profile_saved"] is True
    assert saved["profile_path"].endswith(str(Path("profiles") / "9-2.json"))
    assert profile == {"user_id": 2, "syllabus_id": 9, "confidence": 0.7}
    assert Path(saved["profile_path"]).exists()


def test_learning_profile_fallback_prefers_existing_profile_then_save():
    load_state = {
        "user_id": 2,
        "syllabus_id": 9,
        "existing_profile_loaded": False,
    }
    assert lpt.fallback_next_learning_profile_tool(load_state)["tool_name"] == "load_existing_profile_context"

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
    assert lpt.fallback_next_learning_profile_tool(save_state)["tool_name"] == "save_or_update_profile"


def test_get_or_build_learning_profile_returns_persisted_profile_without_refresh(monkeypatch):
    persisted = {
        "user_id": 3,
        "syllabus_scope": [{"syllabus_id": 11}],
        "confidence": 0.8,
        "profile_path": "profiles/11-3.json",
        "saved_at": 1760000000,
    }
    build_calls = []
    monkeypatch.setattr(profile_service, "load_existing_profile", lambda user_id, syllabus_id: (persisted, persisted["profile_path"]))
    monkeypatch.setattr(profile_service, "build_learning_profile", lambda *args, **kwargs: build_calls.append((args, kwargs)) or {"user_id": 3})

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

    monkeypatch.setattr(profile_service, "load_existing_profile", lambda user_id, syllabus_id: (None, None))
    monkeypatch.setattr(profile_service, "build_learning_profile", fake_build)

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
    monkeypatch.setattr(profile_service, "load_existing_profile", lambda user_id, syllabus_id: (persisted, persisted["profile_path"]))

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

    monkeypatch.setattr(profile_service, "load_existing_profile", lambda user_id, syllabus_id: (wrong_user, wrong_user["profile_path"]))
    assert lpt.get_persisted_learning_profile(4, 12) is None

    monkeypatch.setattr(profile_service, "load_existing_profile", lambda user_id, syllabus_id: (wrong_syllabus, wrong_syllabus["profile_path"]))
    assert lpt.get_persisted_learning_profile(4, 12) is None


def test_get_persisted_learning_profile_accepts_root_syllabus_id(monkeypatch):
    persisted = {
        "user_id": 4,
        "syllabus_id": 12,
        "confidence": 0.8,
    }

    monkeypatch.setattr(profile_service, "load_existing_profile", lambda user_id, syllabus_id: (persisted, "profiles/12-4.json"))

    profile = lpt.get_persisted_learning_profile(4, 12)

    assert profile["profile_saved"] is True
    assert profile["profile_path"].endswith("profiles/12-4.json")


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
    result = LearningProfileResult(
        success=True,
        profile={"user_id": 1, "confidence": 0.5},
    )

    assert result.success is True
    assert result.profile["user_id"] == 1
    assert result.error_message == ""


def test_learning_profile_result_schema_parses_stringified_profile():
    result = LearningProfileResult(
        success=True,
        profile='{"user_id": 1, "confidence": 0.5}',
    )

    assert result.profile == {"user_id": 1, "confidence": 0.5}
