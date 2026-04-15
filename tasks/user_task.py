import secrets
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash

from repositories.user_repo import (
    get_user_by_id,
    get_user_by_username,
    get_user_by_email,
    create_user,
    set_password_by_user_id,
    update_user,
    list_all_users_brief,
)
from repositories.syllabus_repo import list_all_syllabuses
from repositories.user_syllabus_repo import create_user_syllabus
from constant import SyllabusPermission


def register(user_name: str, password: str, email: str) -> Optional[dict]:
    """Register a new user. Returns user dict on success, None on failure or duplicate."""
    # check duplicates
    if get_user_by_username(user_name) or get_user_by_email(email):
        return None
    ph = generate_password_hash(password)
    u = create_user(user_name, ph, email)
    if not u:
        return None

    try:
        for syllabus in list_all_syllabuses():
            syllabus_id = getattr(syllabus, 'syllabus_id', None)
            if syllabus_id is None:
                continue
            create_user_syllabus(
                user_id=u.user_id,
                syllabus_id=syllabus_id,
                syllabus_permission=SyllabusPermission.USER.value,
            )
    except Exception:
        # registering the user itself has succeeded; relation backfill failure should not mask it
        pass

    return {'user_id': u.user_id, 'user_name': u.user_name, 'email': u.email}


def login(user_name: str, password: str) -> Optional[dict]:
    """Verify credentials and return user brief dict on success."""
    u = get_user_by_username(user_name)
    if not u:
        return None
    if not check_password_hash(u.password_hash, password):
        return None
    return {'user_id': u.user_id, 'user_name': u.user_name, 'email': u.email}


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    u = get_user_by_id(user_id)
    if not u:
        return False
    if not check_password_hash(u.password_hash, old_password):
        return False
    ph = generate_password_hash(new_password)
    updated = set_password_by_user_id(user_id, ph)
    return updated is not None


def reset_password(user_id: int) -> Optional[str]:
    """Generate a temporary password, set it, and return the plaintext temporary password."""
    u = get_user_by_id(user_id)
    if not u:
        return None
    temp = secrets.token_urlsafe(8)
    ph = generate_password_hash(temp)
    updated = set_password_by_user_id(user_id, ph)
    if not updated:
        return None
    return temp


def update_user_info(user_id: int, user_name: str = None, email: str = None) -> Optional[dict]:
    u = update_user(user_id, user_name=user_name, email=email)
    if not u:
        return None
    return {'user_id': u.user_id, 'user_name': u.user_name, 'email': u.email}


def get_user_detail_info(user_id: int) -> Optional[dict]:
    u = get_user_by_id(user_id)
    if not u:
        return None
    return {'user_id': u.user_id, 'user_name': u.user_name, 'email': u.email, 'create_time': getattr(u, 'create_time', None)}


def list_all_user_brief_info() -> list:
    return list_all_users_brief()
