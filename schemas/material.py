from extensions import db

class Material(db.Model):
    __tablename__ = 'material'

    material_id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title: str = db.Column(db.String(255), nullable=True, default=None)
    draft_material_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None) # /material/draft_material_json/title_<timestamp>.json
    material_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None) # /material/material_json/title_<timestamp>.json
    pdf_path: str = db.Column(db.String(255), db.ForeignKey('files.file_id'), nullable=True, unique=True, default=None) # /material/material_pdf/title_<timestamp>.pdf
    file_id: int = db.Column(db.Integer, nullable=True, unique=True, default=None) # 描述的是教学资源文件的ID，便于前端展示和后续查询使用
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.syllabus_id'), nullable=False) # 外键关联到syllabus表

    def __repr__(self):
        return f"<Material {self.material_id} - Title: {self.title} - Draft Material Path: {self.draft_material_path} - Material Path: {self.material_path} - PDF Path: {self.pdf_path} - File ID (material): {self.file_id} - Syllabus ID: {self.syllabus_id}>"