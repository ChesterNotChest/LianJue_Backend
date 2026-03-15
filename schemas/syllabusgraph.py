from extensions import db

class Syllabus(db.Model):
    __tablename__ = 'syllabus'

    id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    syllabus_id: int = db.Column(db.Integer, db.ForeignKey('syllabus.syllabus_id'), autoincrement=True)
    graph_id: int = db.Column(db.Integer, db.ForeignKey('graph.graph_id')) # 关联的图谱ID，便于前端展示和后续查询使用

    def __repr__(self):
        return f"<Syllabus {self.syllabus_id} - Graph ID: {self.graph_id} - File ID: {self.file_id}>"