from flask import Flask

from blueprint import syllabus_material_api


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(syllabus_material_api.bp)
    return app


def test_generate_material_draft_api_is_deprecated():
    client = _make_app().test_client()

    response = client.post(
        "/api/syllabus_material_generate_draft",
        json={
            "syllabus_id": 1,
            "involved_weeks": [1],
            "question_type_distribution": {"single": 1, "judge": 0, "short": 0},
        },
    )

    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_generate_final_material_api_is_deprecated():
    client = _make_app().test_client()

    response = client.post("/api/syllabus_material_generate_final", json={"material_id": 1})

    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_publish_material_api_is_deprecated():
    client = _make_app().test_client()

    response = client.post("/api/syllabus_material_publish", json={"material_id": 1})

    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_update_material_draft_api_is_deprecated():
    client = _make_app().test_client()

    response = client.post(
        "/api/syllabus_material_update_draft",
        json={"material_id": 1, "material_draft_json": {"title": "draft"}},
    )

    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_material_draft_detail_api_is_deprecated():
    client = _make_app().test_client()

    response = client.post("/api/syllabus_material_draft_detail", json={"material_id": 1})

    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_material_detail_api_rejects_legacy_material_id():
    client = _make_app().test_client()

    response = client.post("/api/syllabus_material_detail", json={"material_id": 7})

    assert response.status_code == 410
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "deprecated"


def test_material_detail_api_supports_generated_resource_handle(monkeypatch):
    client = _make_app().test_client()

    monkeypatch.setattr(
        syllabus_material_api.generative_task,
        "get_generated_resource_detail",
        lambda user_id, resource_id: {
            "user_id": user_id,
            "resource_id": resource_id,
            "resource_type": "quiz",
        },
    )

    response = client.post(
        "/api/syllabus_material_detail",
        json={"user_id": 5, "resource_id": "quiz-abc"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["material"] == {
        "user_id": 5,
        "resource_id": "quiz-abc",
        "resource_type": "quiz",
    }


def test_material_list_api_returns_empty_for_legacy_syllabus_only():
    client = _make_app().test_client()

    response = client.post("/api/syllabus_material_list", json={"syllabus_id": 11})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["materials"] == []


def test_material_list_api_supports_generated_resource_grouping(monkeypatch):
    client = _make_app().test_client()

    monkeypatch.setattr(
        syllabus_material_api.generative_task,
        "list_generated_resources_by_type",
        lambda user_id, syllabus_id=None, limit_per_type=None: {
            "quiz": [{"resource_id": "quiz-1", "syllabus_id": syllabus_id}],
            "mindmap": [{"resource_id": "mindmap-1", "syllabus_id": syllabus_id}],
        },
    )

    response = client.post(
        "/api/syllabus_material_list",
        json={"user_id": 5, "syllabus_id": 9, "group_by_type": True, "limit_per_type": 2},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["materials"] == {
        "quiz": [{"resource_id": "quiz-1", "syllabus_id": 9}],
        "mindmap": [{"resource_id": "mindmap-1", "syllabus_id": 9}],
    }
