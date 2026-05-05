from extensions import db

class File(db.Model):
    __tablename__ = 'files'

    file_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    path = db.Column(db.String(255), unique=True)
    upload_time = db.Column(db.DateTime)
