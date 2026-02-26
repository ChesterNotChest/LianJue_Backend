from ..extensions import db
from ..schemas.file import File

def get_file_by_id(file_id):
    return File.query.filter_by(file_id=file_id).first()

def create_file(file_id, filename, upload_time):
    new_file = File(file_id=file_id, filename=filename, upload_time=upload_time)
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