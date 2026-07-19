from extensions import db

class Graph(db.Model):
    __tablename__ = 'graph'

    graph_id: int = db.Column(db.Integer, primary_key=True, autoincrement=True) # 数据库自增id
    graphId: str = db.Column(db.String(255), unique=True) # 本质就是graph名称，用于图数据库交互
    snapshot_cache_path: str = db.Column(db.String(512), nullable=True) # 缓存快照JSON的文件路径