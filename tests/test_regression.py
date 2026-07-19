"""回归测试 — 确保现有功能在权限重构后仍然正常。

这些测试验证关键学习路径不被破坏。
"""

import pytest

from app import create_app
from extensions import db
from schemas.user import User
from schemas.syllabus import Syllabus


@pytest.mark.mysql
class TestRegisterBindsAll:
    def test_register_binds_all_published_syllabi(self):
        """RT-01: 新用户注册后在 UserSyllabus 中有所有现有学科绑定"""
        app = create_app()
        app.testing = True
        client = app.test_client()

        with app.app_context():
            pub_s = Syllabus(
                edu_calendar_path="/tmp/rt_pub.pdf",
                status="published",
            )
            db.session.add(pub_s)
            db.session.commit()
            pub_id = pub_s.syllabus_id

        try:
            resp = client.post(
                "/api/user_register",
                json={
                    "user_name": "rt_reg_bind",
                    "password": "test123",
                    "email": "rt_reg_bind@t",
                },
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"]

            uid = data["user"]["user_id"]

            # verify UserSyllabus exists
            from schemas.user_syllabus import UserSyllabus
            with app.app_context():
                binding = UserSyllabus.query.filter_by(
                    user_id=uid, syllabus_id=pub_id
                ).first()
                assert binding is not None, "new user must be bound to published syllabus"

            # cleanup
            with app.app_context():
                UserSyllabus.query.filter_by(user_id=uid).delete()
                User.query.filter_by(user_id=uid).delete()
                Syllabus.query.filter_by(syllabus_id=pub_id).delete()
                db.session.commit()
        except Exception:
            with app.app_context():
                from schemas.user_syllabus import UserSyllabus
                uid_resp = resp.get_json().get("user", {}).get("user_id")
                if uid_resp:
                    UserSyllabus.query.filter_by(user_id=uid_resp).delete()
                    User.query.filter_by(user_id=uid_resp).delete()
                Syllabus.query.filter_by(syllabus_id=pub_id).delete()
                db.session.commit()
            raise


@pytest.mark.mysql
class TestStudyGraphUnchanged:
    def test_study_graph_detail_with_syllabus(self):
        """RT-03: study_graph/detail?syllabus_id 仍正常工作"""
        app = create_app()
        app.testing = True
        client = app.test_client()

        with app.app_context():
            u = User(
                user_name="rt_sg",
                password_hash="-",
                email="rt_sg@t",
            )
            db.session.add(u)
            db.session.commit()
            uid = u.user_id

        try:
            resp = client.get(
                f"/api/study_graph/detail?user_id={uid}&syllabus_id=1"
            )
            assert resp.status_code in (200, 400)  # 200 if tree exists, 400 if not
            data = resp.get_json()
            # should have graph or error — but not crash
            assert "success" in data
        finally:
            with app.app_context():
                User.query.filter_by(user_id=uid).delete()
                db.session.commit()

    def test_study_graph_detail_overview(self):
        """RT-03b: study_graph/detail (无 syllabus_id) 返回增强 lifelong overview"""
        app = create_app()
        app.testing = True
        client = app.test_client()

        with app.app_context():
            u = User(
                user_name="rt_sg_overview",
                password_hash="-",
                email="rt_sg_overview@t",
            )
            db.session.add(u)
            db.session.commit()
            uid = u.user_id

        try:
            resp = client.get(
                f"/api/study_graph/detail?user_id={uid}"
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"]

            tree = data["graph"]["tree"]
            # enhanced version should have nodes and edges
            assert "nodes" in tree, "lifelong overview should include nodes"
            assert "edges" in tree, "lifelong overview should include edges"
        finally:
            with app.app_context():
                User.query.filter_by(user_id=uid).delete()
                db.session.commit()


@pytest.mark.mysql
class TestFileEndpoints:
    def test_file_upload_requires_no_operator(self):
        """RT-05: 普通 file_upload 不需要 operator 权限"""
        app = create_app()
        app.testing = True
        client = app.test_client()

        with app.app_context():
            u = User(
                user_name="rt_file",
                password_hash="-",
                email="rt_file@t",
                permission="user",
            )
            db.session.add(u)
            db.session.commit()
            uid = u.user_id

        try:
            # file_upload is NOT operator-gated
            resp = client.post(
                "/api/file_upload",
                data={"user_id": str(uid)},
            )
            # expects 400 (missing file) but NOT 403
            assert resp.status_code != 403, "file_upload should not require operator"
        finally:
            with app.app_context():
                User.query.filter_by(user_id=uid).delete()
                db.session.commit()
