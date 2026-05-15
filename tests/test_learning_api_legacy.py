from flask import Flask

from blueprint.learning_api import bp


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app


def test_learning_init_personal_syllabus_uses_profile_facade(monkeypatch):
    from blueprint import learning_api

    calls = []

    def fake_init(user_id, syllabus_id):
        calls.append((user_id, syllabus_id))
        return "schedule/student_alt/user_3/12_personal.json"

    monkeypatch.setattr(learning_api.learning_task, "init_personal_syllabus", fake_init)

    client = _make_app().test_client()
    response = client.post(
        "/api/learning_init_personal_syllabus",
        json={"user_id": 3, "syllabus_id": 12},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["syllabus"]["personal_syllabus_path"].endswith("12_personal.json")
    assert calls == [(3, 12)]


def test_learning_personal_syllabus_detail_stays_display_only(monkeypatch):
    from blueprint import learning_api

    calls = []

    def fake_detail(user_id, syllabus_id):
        calls.append((user_id, syllabus_id))
        return {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "period": [{"week_index": "1", "competance": "none"}],
        }

    monkeypatch.setattr(learning_api.learning_task, "get_personal_syllabus_detail_info", fake_detail)

    client = _make_app().test_client()
    response = client.post(
        "/api/learning_personal_syllabus_detail",
        json={"user_id": 3, "syllabus_id": 12},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["syllabus"]["period"][0]["competance"] == "none"
    assert calls == [(3, 12)]


def test_learning_ask_question_is_deprecated():
    client = _make_app().test_client()
    response = client.post(
        "/api/learning_ask_question",
        json={"user_id": 3, "syllabus_id": 12, "question": "RowKey 怎么设计？"},
    )

    payload = response.get_json()
    assert response.status_code == 410
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_learning_update_personal_syllabus_is_deprecated():
    client = _make_app().test_client()
    response = client.post(
        "/api/learning_update_personal_syllabus",
        json={"user_id": 3, "syllabus_id": 12, "week_index": 1, "study_time_spent": 2},
    )

    payload = response.get_json()
    assert response.status_code == 410
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"
