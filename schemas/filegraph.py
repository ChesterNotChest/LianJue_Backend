from extensions import db

class FileGraph(db.Model):
    __tablename__ = 'file_graph'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_id = db.Column(db.Integer, db.ForeignKey('files.file_id'), nullable=False)
    graph_id = db.Column(db.Integer, db.ForeignKey('graph.graph_id'), nullable=False)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())