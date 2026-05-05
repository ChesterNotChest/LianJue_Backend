from extensions import db
from schemas.syllabus import Syllabus

def create_syllabus(edu_calendar_path: str = None, file_id: int = None, title: str = None):
    """Create a syllabus record. Graph associations are handled by syllabus_graph_repo."""
    syllabus = Syllabus(edu_calendar_path=edu_calendar_path, file_id=file_id, title=title)
    db.session.add(syllabus)
    db.session.commit()
    return syllabus

def get_syllabus_by_id(syllabus_id: int):
    return Syllabus.query.filter_by(syllabus_id=syllabus_id).first()

def set_syllabus_draft_path(syllabus_id: int, syllabus_draft_path: str):
    syllabus = get_syllabus_by_id(syllabus_id)
    if syllabus:
        syllabus.syllabus_draft_path = syllabus_draft_path
        db.session.commit()
    return syllabus

def set_syllabus_path(syllabus_id: int, syllabus_path: str):
    syllabus = get_syllabus_by_id(syllabus_id)
    if syllabus:
        syllabus.syllabus_path = syllabus_path
        db.session.commit()
    return syllabus


def set_syllabus_day_one(syllabus_id: int, day_one_dt):
    """Set the syllabus.day_one_time field. day_one_dt may be a datetime.date/datetime or None."""
    syllabus = get_syllabus_by_id(syllabus_id)
    if syllabus:
        try:
            syllabus.day_one_time = day_one_dt
            db.session.commit()
        except Exception:
            db.session.rollback()
    return syllabus


def set_syllabus_title(syllabus_id: int, title: str):
    """Set the syllabus.title field."""
    syllabus = get_syllabus_by_id(syllabus_id)
    if syllabus:
        try:
            syllabus.title = title
            db.session.commit()
        except Exception:
            db.session.rollback()
    return syllabus


def list_all_syllabuses():
    """Return all syllabus records as a list."""
    return Syllabus.query.all()