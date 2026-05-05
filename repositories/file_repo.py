from datetime import datetime, timezone

from extensions import db
from schemas.file import File


def _normalize_upload_time(upload_time):
    if upload_time is None:
        return datetime.utcnow()

    if isinstance(upload_time, datetime):
        if upload_time.tzinfo is not None:
            return upload_time.astimezone(timezone.utc).replace(tzinfo=None)
        return upload_time

    if isinstance(upload_time, str):
        value = upload_time.strip()
        if not value:
            return datetime.utcnow()

        # Accept frontend ISO-8601 timestamps like 2026-04-16T07:15:56.436Z.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    raise TypeError(f"unsupported upload_time type: {type(upload_time)!r}")

def get_file_by_id(file_id):
    return File.query.filter_by(file_id=file_id).first()

def create_file(file_path: str, upload_time):
    # Normalize path (strip surrounding whitespace)
    norm_path = file_path.strip() if isinstance(file_path, str) else file_path

    # If a file with the same path already exists, return it instead of creating a duplicate
    existing = File.query.filter_by(path=norm_path).first()
    if existing:
        return existing

    new_file = File(path=norm_path, upload_time=_normalize_upload_time(upload_time))
    db.session.add(new_file)
    db.session.commit()
    return new_file

def delete_file(file_id):
    file = get_file_by_id(file_id)
    if file:
        db.session.delete(file)
        db.session.commit()
        return True
    return False
