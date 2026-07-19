"""Phase 1: 数据层 — model default values + enum correctness."""

import pytest

from app import create_app
from extensions import db
from schemas.user import User
from schemas.syllabus import Syllabus
from constant import UserPermission, SyllabusStatus


@pytest.mark.mysql
class TestPhase1Model:
    def test_user_permission_default(self):
        """UT-01: 新建 User 自动获得 permission='user'"""
        app = create_app()
        app.testing = True
        with app.app_context():
            u = User(
                user_name="ut_p1_perm",
                password_hash="-",
                email="ut_p1_perm@t",
            )
            db.session.add(u)
            db.session.commit()

            assert u.permission == "user"

            db.session.delete(u)
            db.session.commit()

    def test_syllabus_status_default(self):
        """UT-07: 新建 Syllabus 自动获得 status='draft'"""
        app = create_app()
        app.testing = True
        with app.app_context():
            s = Syllabus(edu_calendar_path="/tmp/ut_p1_status.pdf")
            db.session.add(s)
            db.session.commit()

            assert s.status == "draft"

            db.session.delete(s)
            db.session.commit()


class TestPhase1Enums:
    def test_user_permission_enum_values(self):
        """UT-02: UserPermission enum"""
        assert UserPermission.USER.value == "user"
        assert UserPermission.OPERATOR.value == "operator"

    def test_syllabus_status_enum_values(self):
        """UT-08: SyllabusStatus enum"""
        assert SyllabusStatus.DRAFT.value == "draft"
        assert SyllabusStatus.PUBLISHED.value == "published"


def test_syllabus_permission_replaced():
    """UT-03: SyllabusPermission 已被 UserPermission + SyllabusStatus 替换"""
    import constant

    # 旧枚举不应存在
    assert not hasattr(constant, "SyllabusPermission"), (
        "SyllabusPermission should be removed from constant"
    )

    # 新枚举应存在
    assert hasattr(constant, "UserPermission")
    assert hasattr(constant, "SyllabusStatus")
    assert constant.UserPermission.USER.value == "user"
    assert constant.SyllabusStatus.DRAFT.value == "draft"
