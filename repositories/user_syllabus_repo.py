from extensions import db
from schemas.user_syllabus import UserSyllabus


def get_user_syllabus(user_id: int, syllabus_id: int):
    """Return UserSyllabus row for given user and syllabus, or None."""
    return UserSyllabus.query.filter_by(user_id=user_id, syllabus_id=syllabus_id).first()


def list_user_syllabuses(user_id: int, syllabus_permission: str = None):
    """Return all UserSyllabus rows for a user, optionally filtered by permission."""
    q = UserSyllabus.query.filter_by(user_id=user_id)
    if syllabus_permission is not None:
        q = q.filter_by(syllabus_permission=syllabus_permission)
    return q.all()


def list_user_syllabuses_by_syllabus(syllabus_id: int, syllabus_permission: str = None):
    """Return all UserSyllabus rows for a syllabus, optionally filtered by permission."""
    q = UserSyllabus.query.filter_by(syllabus_id=syllabus_id)
    if syllabus_permission is not None:
        q = q.filter_by(syllabus_permission=syllabus_permission)
    return q.all()


def create_user_syllabus(user_id: int, syllabus_id: int, syllabus_permission: str = 'user', personal_syllabus_path: str = None):
    """Create a UserSyllabus entry and return it. If it already exists, return the existing row."""
    existing = get_user_syllabus(user_id, syllabus_id)
    if existing:
        updated = False
        if syllabus_permission and getattr(existing, 'syllabus_permission', None) != syllabus_permission:
            if syllabus_permission == 'owner' or not getattr(existing, 'syllabus_permission', None):
                existing.syllabus_permission = syllabus_permission
                updated = True
        if personal_syllabus_path and getattr(existing, 'personal_syllabus_path', None) != personal_syllabus_path:
            existing.personal_syllabus_path = personal_syllabus_path
            updated = True
        if updated:
            db.session.commit()
        return existing

    us = UserSyllabus(
        user_id=user_id,
        syllabus_id=syllabus_id,
        syllabus_permission=syllabus_permission,
        personal_syllabus_path=personal_syllabus_path,
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
