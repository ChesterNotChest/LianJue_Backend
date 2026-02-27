from extensions import db
from schemas.file import File

def get_file_by_id(file_id):
    return File.query.filter_by(file_id=file_id).first()

def create_file(file_path: str, upload_time: str):
    # Normalize path (strip surrounding whitespace)
    norm_path = file_path.strip() if isinstance(file_path, str) else file_path

    # If a file with the same path already exists, return it instead of creating a duplicate
    existing = File.query.filter_by(path=norm_path).first()
    if existing:
        return existing

    new_file = File(path=norm_path, upload_time=upload_time)
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