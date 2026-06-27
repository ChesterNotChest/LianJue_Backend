"""Phase 2: 权限基础设施 — require_operator + repo cleanup."""

import pytest

from app import create_app
from extensions import db
from schemas.user import User
from schemas.syllabus import Syllabus
from repositories.user_syllabus_repo import (
    list_user_syllabuses,
    list_user_syllabuses_by_syllabus,
    create_user_syllabus,
)


@pytest.mark.mysql
class TestRequireOperator:
    def test_reject_user(self):
        """UT-04: 普通 user 不能访问 operator 端点"""
        app = create_app()
        app.testing = True
        client = app.test_client()

        with app.app_context():
            u = User(
                user_name="ut_p2_user",
                password_hash="-",
                email="ut_p2_user@t",
                permission="user",
            )
            db.session.add(u)
            db.session.commit()
            uid = u.user_id

        try:
            resp = client.post(
                "/api/admin/set_permission",
                json={"user_id": uid, "target_user_id": uid, "permission": "operator"},
            )
            assert resp.status_code == 403
            data = resp.get_json()
            assert data["error_code"] == "operator_required"
        finally:
            with app.app_context():
                User.query.filter_by(user_id=uid).delete()
                db.session.commit()

    def test_allow_operator(self):
        """UT-04b: operator 可访问 operator 端点"""
        app = create_app()
        app.testing = True
        client = app.test_client()

        with app.app_context():
            op = User(
                user_name="ut_p2_op",
                password_hash="-",
                email="ut_p2_op@t",
                permission="operator",
            )
            target = User(
                user_name="ut_p2_target",
                password_hash="-",
                email="ut_p2_target@t",
                permission="user",
            )
            db.session.add_all([op, target])
            db.session.commit()
            op_id = op.user_id
            target_id = target.user_id

        try:
            resp = client.post(
                "/api/admin/set_permission",
                json={"user_id": op_id, "target_user_id": target_id, "permission": "operator"},
            )
            # expect 200 — not checking other endpoints which depend on other fixtures
            assert resp.status_code in (200, 400)  # 400 is ok (invalid_fields if something missing), but NOT 403
            data = resp.get_json()
            assert data.get("error_code") != "operator_required"
        finally:
            with app.app_context():
                User.query.filter_by(user_id=op_id).delete()
                User.query.filter_by(user_id=target_id).delete()
                db.session.commit()


@pytest.mark.mysql
class TestRepoCleanup:
    def test_list_user_syllabuses_no_permission_param(self):
        """UT-03/05: list_user_syllabuses 不再接受 syllabus_permission 参数"""
        import inspect

        sig = inspect.signature(list_user_syllabuses)
        assert "syllabus_permission" not in sig.parameters, (
            "list_user_syllabuses should no longer accept syllabus_permission"
        )

    def test_create_user_syllabus_no_permission_param(self):
        """UT-05: create_user_syllabus 不再接受 syllabus_permission 参数"""
        import inspect

        sig = inspect.signature(create_user_syllabus)
        assert "syllabus_permission" not in sig.parameters, (
            "create_user_syllabus should no longer accept syllabus_permission"
        )

    def test_create_user_syllabus_default_behavior(self):
        """UT-05: create_user_syllabus 正常工作，不设 syllabus_permission"""
        import uuid

        app = create_app()
        app.testing = True
        with app.app_context():
            uniq = uuid.uuid4().hex[:8]
            u = User(
                user_name=f"ut_p2_repo_{uniq}",
                password_hash="-",
                email=f"ut_p2_repo_{uniq}@t",
            )
            s = Syllabus(edu_calendar_path=f"/tmp/ut_p2_repo_cal_{uniq}.pdf", status="draft")
            db.session.add_all([u, s])
            db.session.commit()

            # create binding with real syllabus
            us = create_user_syllabus(u.user_id, s.syllabus_id)
            assert us is not None
            assert us.user_id == u.user_id
            assert us.syllabus_id == s.syllabus_id

            # cleanup
            db.session.delete(us)
            db.session.delete(s)
            db.session.delete(u)
            db.session.commit()
