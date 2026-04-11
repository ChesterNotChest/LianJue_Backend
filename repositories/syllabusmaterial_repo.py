from extensions import db
from schemas.syllabusmaterial import SyllabusMaterial


def get_syllabusmaterials_by_material(material_id: int):
    return SyllabusMaterial.query.filter_by(material_id=material_id).all()

def get_syllabusmaterials_by_syllabus_and_weeks(syllabus_id: int, week_index: list):
    return SyllabusMaterial.query.filter(SyllabusMaterial.syllabus_id == syllabus_id, SyllabusMaterial.week_index.in_(week_index)).all()


def get_syllabusmaterial(material_id: int, syllabus_id: int, week_index: int):
    return SyllabusMaterial.query.filter_by(material_id=material_id, syllabus_id=syllabus_id, week_index=week_index).first()


def create_syllabus_material(material_id: int, syllabus_id: int, week_index: int, ok_to_recommend: bool = False):
    """Create mapping entry if not exists; return the entry."""
    existing = get_syllabusmaterial(material_id, syllabus_id, week_index)
    if existing:
        return existing
    try:
        rec = SyllabusMaterial(material_id=material_id, syllabus_id=syllabus_id, week_index=week_index, ok_to_recommend=ok_to_recommend)
        db.session.add(rec)
        db.session.commit()
        return rec
    except Exception:
        db.session.rollback()
        raise


def remove_syllabusmaterial(material_id: int, syllabus_id: int, week_index: int):
    rec = get_syllabusmaterial(material_id, syllabus_id, week_index)
    if not rec:
        return False
    try:
        db.session.delete(rec)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise


def set_ok_to_recommend(material_id: int, syllabus_id: int, week_index: int, ok: bool = True):
    rec = get_syllabusmaterial(material_id, syllabus_id, week_index)
    if not rec:
        # create if missing
        return create_syllabus_material(material_id, syllabus_id, week_index, ok_to_recommend=ok)
    try:
        rec.ok_to_recommend = bool(ok)
        db.session.commit()
        return rec
    except Exception:
        db.session.rollback()
        raise
