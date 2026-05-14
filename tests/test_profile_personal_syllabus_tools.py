import json
from types import SimpleNamespace

from tasks import learning_profile_task as lpt


def test_read_profile_personal_syllabus_is_read_only(monkeypatch, repo_json_factory):
    personal_path = repo_json_factory(
        "schedule/student_alt/user_31",
        {
            "syllabus_id": 91,
            "user_id": 31,
            "period": [
                {
                    "week_index": 1,
                    "competance": "weak",
                    "competance_progress": -1,
                    "suggested_competance_list": [],
                    "suggestion_review_count": 0,
                    "suggestion_history": [],
                }
            ],
        },
        prefix="91_personal",
    )
    monkeypatch.setattr(
        lpt,
        "get_user_syllabus",
        lambda user_id, syllabus_id: SimpleNamespace(personal_syllabus_path=str(personal_path)),
    )
    monkeypatch.setattr(lpt, "get_syllabus_by_id", lambda syllabus_id: None)

    before = personal_path.read_text(encoding="utf-8")
    result = lpt.read_profile_personal_syllabus(31, 91)
    after = personal_path.read_text(encoding="utf-8")

    assert result["period"][0]["competance"] == "weak"
    assert before == after


def test_init_profile_personal_syllabus_creates_default_document(monkeypatch, repo_json_factory):
    syllabus_path = repo_json_factory(
        "schedule/syllabus",
        {
            "period": [
                {
                    "week_index": 1,
                    "content": "HBase 基础",
                    "enhanced_content": "HBase RowKey 与列族",
                    "importance": "high",
                }
            ]
        },
        prefix="syllabus",
    )
    saved_paths = []
    monkeypatch.setattr(
        lpt,
        "get_syllabus_by_id",
        lambda syllabus_id: SimpleNamespace(syllabus_path=str(syllabus_path)),
    )
    monkeypatch.setattr(
        lpt,
        "set_personal_syllabus_path",
        lambda user_id, syllabus_id, path: saved_paths.append(path) or True,
    )

    result = lpt.init_profile_personal_syllabus(32, 92)

    assert result is not None
    assert saved_paths == [result["personal_syllabus_path"]]
    assert result["personal_syllabus"]["period"][0]["competance"] == "none"
    assert result["personal_syllabus"]["period"][0]["suggestion_review_count"] == 0
    assert result["personal_syllabus"]["period"][0]["suggestion_history"] == []


def test_append_suggestion_stacks_until_threshold_then_applies(monkeypatch, repo_json_factory):
    personal_path = repo_json_factory(
        "schedule/student_alt/user_33",
        {
            "syllabus_id": 93,
            "user_id": 33,
            "period": [
                {
                    "week_index": 1,
                    "content": "RowKey",
                    "competance": "none",
                    "competance_progress": 0,
                    "suggested_competance_list": [],
                    "suggestion_review_count": 0,
                    "suggestion_history": [],
                    "updated_at": 0,
                }
            ],
        },
        prefix="93_personal",
    )
    monkeypatch.setattr(
        lpt,
        "get_user_syllabus",
        lambda user_id, syllabus_id: SimpleNamespace(personal_syllabus_path=str(personal_path)),
    )
    monkeypatch.setattr(lpt, "get_syllabus_by_id", lambda syllabus_id: None)
    monkeypatch.setattr(lpt, "time", lambda: 1760000000)

    for index in range(4):
        result = lpt.append_profile_personal_syllabus_suggestion(
            33,
            93,
            {
                "week_index": 1,
                "suggested_competance": "weak",
                "confidence": 0.9,
                "reason": f"weak signal {index}",
                "evidence": "dialogue_text",
            },
        )
        assert result["applied"] is False
        assert result["suggestion_review_count"] == index + 1

    data = json.loads(personal_path.read_text(encoding="utf-8"))
    week = data["period"][0]
    assert week["competance"] == "none"
    assert week["suggested_competance_list"] == ["weak"] * 4

    result = lpt.append_profile_personal_syllabus_suggestion(
        33,
        93,
        {
            "week_index": 1,
            "suggested_competance": "weak",
            "confidence": 0.9,
            "reason": "threshold signal",
            "evidence": ["dialogue_text"],
        },
    )

    assert result["applied"] is True
    assert result["suggestion_review_count"] == 0
    assert result["competance"] == "weak"
    data = json.loads(personal_path.read_text(encoding="utf-8"))
    week = data["period"][0]
    assert week["competance"] == "weak"
    assert week["suggested_competance_list"] == []
    assert len(week["suggestion_history"]) == 5


def test_append_suggestion_rejects_low_confidence(monkeypatch, repo_json_factory):
    personal_path = repo_json_factory(
        "schedule/student_alt/user_34",
        {"period": [{"week_index": 1, "suggestion_history": []}]},
        prefix="94_personal",
    )
    monkeypatch.setattr(
        lpt,
        "get_user_syllabus",
        lambda user_id, syllabus_id: SimpleNamespace(personal_syllabus_path=str(personal_path)),
    )

    result = lpt.append_profile_personal_syllabus_suggestion(
        34,
        94,
        {
            "week_index": 1,
            "suggested_competance": "weak",
            "confidence": 0.1,
        },
    )

    assert result is None
    assert json.loads(personal_path.read_text(encoding="utf-8"))["period"][0]["suggestion_history"] == []


def test_profile_refresh_outputs_suggestions_without_writing_personal_syllabus(monkeypatch, repo_json_factory):
    personal_path = repo_json_factory(
        "schedule/student_alt/user_35",
        {
            "period": [
                {
                    "week_index": 1,
                    "content": "HBase RowKey",
                    "competance": "weak",
                    "competance_progress": -1,
                    "suggested_competance_list": [],
                    "suggestion_review_count": 0,
                    "suggestion_history": [],
                }
            ]
        },
        prefix="95_personal",
    )
    state = {
        "user_id": 35,
        "syllabus_id": 95,
        "user": SimpleNamespace(user_id=35, user_name="profile", email="p@example.com"),
        "user_syllabuses": [],
        "profile_scope": [{"syllabus_id": 95, "personal_syllabus_path": str(personal_path)}],
        "dialogue_texts": ["我在 RowKey 上很吃力，希望尽快补上。"],
        "learning_goal": "掌握 HBase",
        "learning_records": [],
        "answer_records": [
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "answered_at": 1760000000,
                "time_spent_seconds": 180,
                "meta": {"knowledge_points": ["RowKey"]},
            }
        ],
        "resource_usage": [],
        "now_ts": 1760000000,
        "history_entries": [],
        "loaded_personal_syllabuses": [
            (
                95,
                json.loads(personal_path.read_text(encoding="utf-8")),
                {},
            )
        ],
        "normalized_events": {},
        "feature_bundle": {},
        "profile": None,
    }

    before = personal_path.read_text(encoding="utf-8")
    lpt._tool_normalize_events(state)
    lpt._tool_compute_features(state)
    lpt._tool_assemble_profile(state)
    after = personal_path.read_text(encoding="utf-8")

    assert before == after
    assert state["profile"]["suggested_personal_syllabus_updates"]
