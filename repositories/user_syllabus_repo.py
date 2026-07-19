from extensions import db
from schemas.user_syllabus import UserSyllabus


def get_user_syllabus(user_id: int, syllabus_id: int):
    """Return UserSyllabus row for given user and syllabus, or None."""
    return UserSyllabus.query.filter_by(user_id=user_id, syllabus_id=syllabus_id).first()


def list_user_syllabuses(user_id: int):
    """Return all UserSyllabus rows for a user."""
    return UserSyllabus.query.filter_by(user_id=user_id).all()


def list_user_syllabuses_by_syllabus(syllabus_id: int):
    """Return all UserSyllabus rows for a syllabus."""
    return UserSyllabus.query.filter_by(syllabus_id=syllabus_id).all()


def create_user_syllabus(
    user_id: int,
    syllabus_id: int,
    personal_syllabus_path: str = None,
    personal_profile_path: str = None,
):
    """Create a UserSyllabus entry and return it. If it already exists, return the existing row."""
    existing = get_user_syllabus(user_id, syllabus_id)
    if existing:
        updated = False
        if personal_syllabus_path and getattr(existing, 'personal_syllabus_path', None) != personal_syllabus_path:
            existing.personal_syllabus_path = personal_syllabus_path
            updated = True
        if personal_profile_path and getattr(existing, 'personal_profile_path', None) != personal_profile_path:
            existing.personal_profile_path = personal_profile_path
            updated = True
        if updated:
            db.session.commit()
        return existing

    us = UserSyllabus(
        user_id=user_id,
        syllabus_id=syllabus_id,
        personal_syllabus_path=personal_syllabus_path,
        personal_profile_path=personal_profile_path,
    )
    db.session.add(us)
    db.session.commit()
    return us


def set_personal_syllabus_path(user_id: int, syllabus_id: int, path: str):
    """Create or update the personal_syllabus_path for the user+syllabus.

    Returns the UserSyllabus instance on success, or None on failure.
    """
    try:
        ps = get_user_syllabus(user_id, syllabus_id)
        if not ps:
            ps = create_user_syllabus(user_id, syllabus_id, personal_syllabus_path=path)
        else:
            ps.personal_syllabus_path = path
            db.session.commit()
        return ps
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def set_personal_profile_path(user_id: int, syllabus_id: int, path: str):
    """Create or update the personal_profile_path for the user+syllabus.

    Returns the UserSyllabus instance on success, or None on failure.
    """
    try:
        ps = get_user_syllabus(user_id, syllabus_id)
        if not ps:
            ps = create_user_syllabus(user_id, syllabus_id, personal_profile_path=path)
        else:
            ps.personal_profile_path = path
            db.session.commit()
        return ps
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None
