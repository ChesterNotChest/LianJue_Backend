from extensions import db

class Jobs(db.Model):
    __tablename__ = 'jobs'

    job_id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    stage: str = db.Column(db.String(255))  # "pdf_to_md", "md_to_triples", "triple_to_knowledge", "knowledge_to_save"
    end_stage: str = db.Column(db.String(255), default="") # "pdf_to_md", "md_to_triples", "triple_to_knowledge", "knowledge_to_save"
    status: int = db.Column(db.String(255), default="pending") # "pending", "in_progress", "completed", "failed"
    progress_index: int = db.Column(db.Integer, default=0) # 不是百分比。int，用于指代批次处理的进度，上限按照总批次数量计算;不同阶段的进度数据来源不同

    partial_md_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None) # 分批处理中间结果的markdown文件路径，便于中断续处理和前端展示下载
    markdown_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None) # 生成的markdown文件路径，便于中断续处理和前端展示下载
    triples_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None) # 生成的三元组文件路径，便于中断续处理和前端展示下载
    knowledge_path: str = db.Column(db.String(255), nullable=True, unique=True, default=None) # 生成的知识对象文件路径，便于前端展示下载
    error_message: str = db.Column(db.Text, default="") # 错误信息

    file_id: int = db.Column(db.Integer) # 关联的文件ID，便于前端展示
    graph_id: str = db.Column(db.String(255)) # 关联的图谱ID，便于前端展示和后续查询使用

    def __repr__(self):
        return f"<Job {self.job_id} - Stage: {self.stage} - Progress: {self.progress_index}>"