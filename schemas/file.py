from ..extensions import db

class File(db.Model):
    __tablename__ = 'files'

    file_id = db.Column(db.String(255), primary_key=True) # 数字id
    filename = db.Column(db.String(255))
    upload_time = db.Column(db.DateTime)
