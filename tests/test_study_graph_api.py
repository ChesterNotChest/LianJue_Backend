"""Smoke tests for /api/study_graph/detail with optional syllabus_id."""

import pytest

from app import create_app
from extensions import db
from schemas.user import User


@pytest.mark.mysql
def test_study_graph_detail_requires_user_id():
    """syllabus_id 可选，但 user_id 仍然必填。"""
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/api/study_graph/detail")
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error_code"] == "missing_user_id"


@pytest.mark.mysql
def test_study_graph_detail_overview_without_syllabus_id():
    """不传 syllabus_id → 返回终身学习总览（student 根 + 学科列表）。仅读操作。"""
    app = create_app()
    app.testing = True
    client = app.test_client()

    with app.app_context():
        user = User(user_name="test_sg_overview", password_hash="-", email="test_sg_overview@t")
        db.session.add(user)
        db.session.commit()
        user_id = user.user_id

    try:
        response = client.get(f"/api/study_graph/detail?user_id={user_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        tree = data["graph"]["tree"]
        assert tree["type"] == "student"
        assert tree["user_id"] == user_id
        assert isinstance(tree["syllabi"], list)
    finally:
        with app.app_context():
            User.query.filter_by(user_id=user_id).delete()
            db.session.commit()
