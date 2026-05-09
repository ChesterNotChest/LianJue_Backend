from flask import Flask

from blueprint import user_api


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(user_api.bp)
    return app


def test_user_learning_profile_api_requires_user_id():
    client = _make_app().test_client()

    response = client.post("/api/user_learning_profile", json={"syllabus_id": 21})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "missing_fields"


def test_user_learning_profile_api_uses_cached_profile_by_default(monkeypatch):
    calls = []

    def fake_get_or_build(user_id, syllabus_id=None, **kwargs):
        calls.append({"user_id": user_id, "syllabus_id": syllabus_id, **kwargs})
        return {
            "user_id": user_id,
            "syllabus_scope": [{"syllabus_id": syllabus_id}],
            "profile_path": "profiles/21-5.json",
            "profile_saved": True,
            "profile_refreshed": False,
        }

    monkeypatch.setattr(user_api, "get_or_build_learning_profile", fake_get_or_build)
    client = _make_app().test_client()

    response = client.post("/api/user_learning_profile", json={"user_id": 5, "syllabus_id": 21})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["profile_saved"] is True
    assert payload["profile_refreshed"] is False
    assert calls == [
        {
            "user_id": 5,
            "syllabus_id": 21,
            "refresh_profile": False,
            "dialogue_text": None,
            "learning_goal": None,
            "learning_records": None,
            "answer_records": None,
            "resource_usage": None,
        }
    ]


def test_user_learning_profile_api_forwards_refresh_profile(monkeypatch):
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
    client = _make_app().test_client()

    response = client.post(
        "/api/user_learning_profile",
        json={"user_id": 5, "syllabus_id": 21, "refresh_profile": "true"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["profile_refreshed"] is True
    assert calls[-1]["refresh_profile"] is True
