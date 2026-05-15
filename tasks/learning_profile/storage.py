import json
import os
from time import time
from typing import Any, Optional, Tuple

from constant import BasePath
from repositories.user_syllabus_repo import get_user_syllabus, set_personal_profile_path


def load_json_file(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def profile_root_dir() -> str:
    root_name = str(BasePath.PERSONAL_PROFILE_ROOT.value).strip().strip('/\\')
    return os.path.abspath(os.path.join(os.getcwd(), root_name))


def build_personal_profile_path(user_id: int, syllabus_id: int) -> str:
    root = profile_root_dir()
    return os.path.abspath(os.path.join(root, f'{syllabus_id}-{user_id}.json'))


def load_existing_profile(user_id: int, syllabus_id: Optional[int]) -> Tuple[Optional[dict], Optional[str]]:
    if syllabus_id is None:
        return None, None

    candidate_path = build_personal_profile_path(user_id, syllabus_id)
    try:
        relation = get_user_syllabus(user_id, syllabus_id)
    except Exception:
        relation = None

    db_path = getattr(relation, 'personal_profile_path', None) if relation else None
    for path in (db_path, candidate_path):
        if not path:
            continue
        profile = load_json_file(path)
        if isinstance(profile, dict):
            return profile, os.path.abspath(path)
    return None, candidate_path


def merge_profile_update(existing_profile: Optional[dict], new_profile: dict) -> dict:
    if not isinstance(new_profile, dict):
        return {}

    merged = dict(new_profile)
    if isinstance(existing_profile, dict) and existing_profile:
        previous_revision = existing_profile.get('profile_revision') or 0
        try:
            previous_revision = int(previous_revision)
        except Exception:
            previous_revision = 0
        merged['previous_profile_updated_at'] = existing_profile.get('updated_at') or existing_profile.get('saved_at')
        merged['previous_confidence'] = existing_profile.get('confidence')
        merged['profile_revision'] = previous_revision + 1
    else:
        merged['profile_revision'] = int(merged.get('profile_revision') or 1)
    return merged


def save_personal_profile(user_id: int, syllabus_id: int, profile: dict) -> Optional[dict]:
    if not isinstance(profile, dict):
        return None

    try:
        profile_path = build_personal_profile_path(user_id, syllabus_id)
        profile_dir = os.path.dirname(profile_path)
        os.makedirs(profile_dir, exist_ok=True)
        payload = dict(profile)
        payload['profile_schema_version'] = int(payload.get('profile_schema_version') or 1)
        payload['profile_path'] = profile_path
        payload['profile_saved'] = True
        payload['saved_at'] = int(time())
        temp_path = f"{profile_path}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        if not set_personal_profile_path(user_id, syllabus_id, profile_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return None
        os.replace(temp_path, profile_path)
        return payload
    except Exception:
        try:
            os.remove(f"{build_personal_profile_path(user_id, syllabus_id)}.tmp")
        except Exception:
            pass
        return None


def profile_has_required_identity(profile: dict, user_id: int, syllabus_id: int) -> bool:
    if not isinstance(profile, dict):
        return False
    try:
        if int(profile.get('user_id')) != int(user_id):
            return False
    except Exception:
        return False

    scope = profile.get('syllabus_scope')
    if isinstance(scope, list):
        for item in scope:
            if not isinstance(item, dict):
                continue
            try:
                if int(item.get('syllabus_id')) == int(syllabus_id):
                    return True
            except Exception:
                continue
        return False
    try:
        if int(profile.get('syllabus_id')) == int(syllabus_id):
            return True
    except Exception:
        pass
    return bool(profile.get('profile_path') or profile.get('saved_at'))


def get_persisted_learning_profile(user_id: int, syllabus_id: int) -> Optional[dict]:
    profile, profile_path = load_existing_profile(user_id, syllabus_id)
    if not isinstance(profile, dict):
        return None
    if not profile_has_required_identity(profile, user_id, syllabus_id):
        return None
    result = dict(profile)
    if profile_path:
        result['profile_path'] = profile_path
    result['profile_saved'] = True
    result['profile_refreshed'] = False
    return result
