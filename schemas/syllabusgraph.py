from extensions import db


class SyllabusGraph(db.Model):
    __tablename__ = 'syllabus_graph'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.syllabus_id'), nullable=False)
    graph_id = db.Column(db.Integer, db.ForeignKey('graph.graph_id'), nullable=False)
    create_time = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f"<SyllabusGraph id={self.id} syllabus_id={self.syllabus_id} graph_id={self.graph_id}>"