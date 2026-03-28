from extensions import db
from schemas.material import Material


def create_material(syllabus_id: int, title: str = None, file_id: int = None):
    """Create a Material record and return it."""
    material = Material(syllabus_id=syllabus_id, title=title, file_id=file_id)
    db.session.add(material)
    db.session.commit()
    return material


def get_material_by_id(material_id: int):
    return Material.query.filter_by(material_id=material_id).first()


def set_material_draft_path(material_id: int, draft_path: str):
    material = get_material_by_id(material_id)
    if material:
        material.draft_material_path = draft_path
        db.session.commit()
    return material


def set_material_path(material_id: int, material_path: str):
    material = get_material_by_id(material_id)
    if material:
        material.material_path = material_path
        db.session.commit()
    return material


def set_material_pdf_path(material_id: int, pdf_path: str, file_id: int = None):
    material = get_material_by_id(material_id)
    if material:
        material.pdf_path = pdf_path
        if file_id is not None:
            material.file_id = file_id
        db.session.commit()
    return material


def set_material_title(material_id: int, title: str):
    """Update the material title."""
    material = get_material_by_id(material_id)
    if material:
        material.title = title
        db.session.commit()
    return material
