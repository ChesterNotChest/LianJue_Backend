from flask import Flask

from blueprint import user_api


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(user_api.bp)
    return app


def test_learning_profile_detail_api_reads_persisted_profile_only(monkeypatch):
    calls = []

    def fake_get_persisted(user_id, syllabus_id):
        calls.append({"user_id": user_id, "syllabus_id": syllabus_id})
        return {
            "user_id": user_id,
            "syllabus_scope": [{"syllabus_id": syllabus_id}],
            "profile_path": "profiles/21-5.json",
            "profile_saved": True,
            "profile_refreshed": False,
        }

    def fail_build(*args, **kwargs):
        raise AssertionError("detail API must not build profile")

    monkeypatch.setattr(user_api, "get_persisted_learning_profile", fake_get_persisted)
    monkeypatch.setattr(user_api, "build_learning_profile", fail_build)
    client = _make_app().test_client()

    response = client.post("/api/learning_profile_detail", json={"user_id": 5, "syllabus_id": 21})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["profile_saved"] is True
    assert payload["profile_refreshed"] is False
    assert calls == [{"user_id": 5, "syllabus_id": 21}]


def test_learning_profile_detail_api_requires_user_id_and_syllabus_id():
    client = _make_app().test_client()

    missing_user = client.post("/api/learning_profile_detail", json={"syllabus_id": 21})
    missing_syllabus = client.post("/api/learning_profile_detail", json={"user_id": 5})

    assert missing_user.status_code == 400
    assert missing_user.get_json()["error_code"] == "missing_fields"
    assert missing_syllabus.status_code == 400
    assert missing_syllabus.get_json()["error_code"] == "missing_fields"


def test_learning_profile_refresh_api_calls_build_learning_profile(monkeypatch):
    calls = []

    def fake_build(user_id, syllabus_id=None, **kwargs):
        calls.append({"user_id": user_id, "syllabus_id": syllabus_id, **kwargs})
        return {
            "user_id": user_id,
            "syllabus_scope": [{"syllabus_id": syllabus_id}],
            "profile_path": "profiles/21-5.json",
            "profile_saved": True,
        }

    def fail_get_persisted(*args, **kwargs):
        raise AssertionError("refresh API must not read-only profile")

    monkeypatch.setattr(user_api, "build_learning_profile", fake_build)
    monkeypatch.setattr(user_api, "get_persisted_learning_profile", fail_get_persisted)
    client = _make_app().test_client()

    response = client.post(
        "/api/learning_profile_refresh",
        json={
            "user_id": 5,
            "syllabus_id": 21,
            "refresh_profile": False,
            "answer_records": [{"question": "Q", "correct": True}],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["profile_refreshed"] is True
    assert calls == [
        {
            "user_id": 5,
            "syllabus_id": 21,
            "dialogue_text": None,
            "learning_goal": None,
            "learning_records": None,
            "answer_records": [{"question": "Q", "correct": True}],
            "resource_usage": None,
        }
    ]


def test_learning_profile_refresh_api_requires_user_id():
    client = _make_app().test_client()

    response = client.post("/api/learning_profile_refresh", json={"syllabus_id": 21})

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "missing_fields"


def test_user_learning_profile_api_removed():
    client = _make_app().test_client()

    response = client.post("/api/user_learning_profile", json={"user_id": 5, "syllabus_id": 21})

    assert response.status_code == 404
