from extensions import db

class Syllabus(db.Model):
    __tablename__ = 'syllabus'

    syllabus_id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    edu_calendar_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None)
    syllabus_draft_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None)
    syllabus_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None)
    file_id: int = db.Column(db.Integer, nullable=True) # 描述的是教学日历文件的ID，便于前端展示和后续查询使用
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    day_one_time = db.Column(db.DateTime, nullable=True, default=None)

    def __repr__(self):
        return f"<Syllabus {self.syllabus_id} - Edu Calendar Path: {self.edu_calendar_path} - Syllabus Draft Path: {self.syllabus_draft_path} - Syllabus Path: {self.syllabus_path} - File ID (calendar): {self.file_id}>"