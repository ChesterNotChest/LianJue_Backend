import json

from app import create_app
from repositories.syllabus_repo import create_syllabus, set_syllabus_path


def test_personal_recommendation_api_with_syllabus(tmp_path):
    app = create_app()
    app.testing = True
    client = app.test_client()

    sample = [
        {"id": "s1", "title": "Start", "outcomes": ["skill_a"]},
        {"id": "s2", "title": "Next", "prerequisites": ["s1"], "outcomes": ["skill_b"]},
    ]
    out_file = tmp_path / "sample_syllabus.json"
    out_file.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")

    with app.app_context():
        syllabus = create_syllabus(title="test-integ")
        assert getattr(syllabus, "syllabus_id", None) is not None
        set_syllabus_path(int(syllabus.syllabus_id), str(out_file))
        syllabus_id = int(syllabus.syllabus_id)

    response = client.post(
        "/api/personal_recommendation",
        json={"user_id": 12345, "syllabus_id": syllabus_id},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert isinstance(data["graph"]["nodes"], list)
    assert isinstance(data["graph"]["edges"], list)
    assert isinstance(data["candidates"], list)
    assert isinstance(data["selected"], list)
    assert "best_path" in data


def test_personal_recommendation_api_requires_user_id():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post("/api/personal_recommendation", json={})

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error_code"] == "missing_fields"
