import json

import pytest

from app import create_app
from repositories.syllabus_repo import create_syllabus, set_syllabus_path


@pytest.mark.mysql
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
    assert data.get("recommendation_id")
    assert data.get("snapshot_status") == "proposed"


def test_personal_recommendation_api_requires_user_id():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post("/api/personal_recommendation", json={})

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error_code"] == "missing_fields"


def _recommendation_result() -> dict:
    return {
        "success": True,
        "schema_version": "personal_recommendation.v2",
        "graph": {
            "nodes": [
                {"id": "n1", "title": "Intro", "outcomes": ["a"]},
                {"id": "n2", "title": "Default Next", "outcomes": ["b"]},
                {"id": "n3", "title": "Alternative Next", "outcomes": ["c"]},
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                {"source": "n1", "target": "n3"},
            ],
        },
        "candidates": [
            {"path": ["n1", "n2"], "skills": ["a", "b"], "rank": 1},
            {"path": ["n1", "n3"], "skills": ["a", "c"], "rank": 2},
        ],
        "selected": [{"path": ["n1", "n2"], "skills": ["a", "b"]}],
        "best_path": {"path": ["n1", "n2"], "skills": ["a", "b"]},
        "planning_hints": {"path_depth": 2},
        "error_code": "",
        "error_message": "",
    }


def test_personal_recommendation_api_can_disable_snapshot(monkeypatch):
    from tasks.personal_recommendation import service as recommendation_service

    app = create_app()
    app.testing = True
    client = app.test_client()
    monkeypatch.setattr(recommendation_service, "run_recommendation_route", lambda **kwargs: _recommendation_result())

    response = client.post(
        "/api/personal_recommendation",
        json={"user_id": 12345, "syllabus_id": 29, "persist_snapshot": False},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "recommendation_id" not in data
    assert "snapshot_status" not in data


def test_recommendation_snapshot_detail_and_list_api(monkeypatch):
    from tasks.personal_recommendation import service as recommendation_service

    app = create_app()
    app.testing = True
    client = app.test_client()
    monkeypatch.setattr(recommendation_service, "run_recommendation_route", lambda **kwargs: _recommendation_result())

    created = client.post(
        "/api/personal_recommendation",
        json={"user_id": 12345, "syllabus_id": 29, "goals": ["learn hbase"]},
    ).get_json()
    recommendation_id = created["recommendation_id"]

    detail = client.get(f"/api/recommendations/{recommendation_id}")
    listing = client.get("/api/recommendations?user_id=12345&syllabus_id=29")

    assert detail.status_code == 200
    detail_data = detail.get_json()
    assert detail_data["success"] is True
    assert detail_data["snapshot"]["recommendation"]["graph"]["nodes"][0]["id"] == "n1"
    assert listing.status_code == 200
    list_data = listing.get_json()
    assert list_data["success"] is True
    assert list_data["snapshots"][0]["recommendation_id"] == recommendation_id
    assert "recommendation" not in list_data["snapshots"][0]


def test_recommendation_snapshot_accept_api_creates_plan(monkeypatch):
    from tasks.personal_recommendation import service as recommendation_service

    app = create_app()
    app.testing = True
    client = app.test_client()
    monkeypatch.setattr(recommendation_service, "run_recommendation_route", lambda **kwargs: _recommendation_result())

    created = client.post(
        "/api/personal_recommendation",
        json={"user_id": 12345, "syllabus_id": 29, "goals": ["learn hbase"]},
    ).get_json()
    accepted = client.post(
        f"/api/recommendations/{created['recommendation_id']}/accept",
        json={"user_id": 12345, "syllabus_id": 29, "candidate_index": 1},
    )

    assert accepted.status_code == 200
    data = accepted.get_json()
    assert data["success"] is True
    assert data["snapshot_status"] == "accepted"
    assert data["accepted_candidate_index"] == 1
    assert [step["node_id"] for step in data["steps"]] == ["n1", "n3"]
