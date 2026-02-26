from ..extensions import db

class Graph(db.Model):
    __tablename__ = 'graph'

    graph_id: int = db.Column(db.Integer, primary_key=True)
    graphId: str = db.Column(db.String(255), unique=True) # 本质就是graph名称，用于图数据库交互