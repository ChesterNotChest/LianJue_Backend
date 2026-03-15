from extensions import db
from schemas.syllabus import Syllabus

def create_syllabus(graph_id: int, edu_calendar_path:str = None, file_id: int = None):
    syllabus = Syllabus(graph_id=graph_id, edu_calendar_path=edu_calendar_path, file_id=file_id)
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