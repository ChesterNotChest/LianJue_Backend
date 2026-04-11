from repositories.file_repo import get_file_by_id

from constant import JobStatus, JobStage
from extensions import db
from repositories.graph_repo import get_graph_by_id
from schemas.jobs import Jobs

###################
# 基础getter
def get_job_by_id(job_id):
    return Jobs.query.filter_by(job_id=job_id).first()

def get_jobs_by_file_id(file_id):
    return Jobs.query.filter_by(file_id=file_id).all()

def get_jobs_by_graph_id(graph_id):
    return Jobs.query.filter_by(graph_id=graph_id).all()

def get_graphId_by_job_id(job_id):
    job = get_job_by_id(job_id)
    if job:
        graph = get_graph_by_id(job.graph_id)
        return graph.graphId if graph else None
    return None

###################
# 状态getter
def get_status_by_job_id(job_id):
    job = get_job_by_id(job_id)
    return job.status if job else None

def get_end_stage_by_job_id(job_id):
    job = get_job_by_id(job_id)
    return job.end_stage if job else None

def get_job_stage_by_job_id(job_id):
    job = get_job_by_id(job_id)
    return job.stage if job else None

def get_progress_index_by_job_id(job_id):
    job = get_job_by_id(job_id)
    return job.progress_index if job else None
###################

###################
# 创建新任务
def create_job(file_id: int, graph_id: int, end_stage: str = JobStage.KNOWLEDGE_TO_SAVE.value) -> Jobs:
    # If a job for this file already exists in the same graph, return it instead of creating a duplicate
    existing = Jobs.query.filter_by(file_id=file_id, graph_id=graph_id).first()
    if existing:
        return existing

    new_job = Jobs(file_id=file_id, graph_id=graph_id, status="pending", stage="pdf_to_md", end_stage=end_stage)
    db.session.add(new_job)
    db.session.commit()
    return new_job
###################

###################
# 推动进度
def update_job_stage(job_id: int, stage: str) -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.stage = stage
        db.session.commit()
    return job
def update_job_progress(job_id: int, progress_index: int) -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.progress_index = progress_index
        db.session.commit()
    return job
###################
# 更新终止点 意为，相关任务只走到这个状态就结束了，不再继续往下走了。
def update_end_stage(job_id: int, end_stage: str) -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.end_stage = end_stage
        db.session.commit()
    return job
###################
###################
# 更新路径
def update_partial_md_path(job_id: int, partial_md_path: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.partial_md_path = partial_md_path
        db.session.commit()
    return job

def update_split_markdown_path(job_id: int, split_markdown_path: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.split_markdown_path = split_markdown_path
        db.session.commit()
    return job

def update_markdown_path(job_id: int, markdown_path: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.markdown_path = markdown_path
        db.session.commit()
    return job

def update_triples_path(job_id: int, triples_path: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.triples_path = triples_path
        db.session.commit()
    return job

def update_partial_triples_path(job_id: int, partial_triples_path: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.partial_triples_path = partial_triples_path
        db.session.commit()
    return job

def update_knowledge_path(job_id: int, knowledge_path: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.knowledge_path = knowledge_path
        db.session.commit()
    return job
###################

###################
# 更新异常
def update_job_status(job_id: int, status: str) -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.status = status
        db.session.commit()
    return job

def update_error_message(job_id: int, error_message: str = "") -> Jobs:
    job = get_job_by_id(job_id)
    if job:
        job.error_message = error_message
        db.session.commit()
    return job
###################

###################
# 展示任务列表
def list_all_jobs(**kwargs) -> list[Jobs]:
    query = Jobs.query
    for key, value in kwargs.items():
        if hasattr(Jobs, key):
            query = query.filter(getattr(Jobs, key) == value)
    return query.all()

def get_job_details(job_id: int) -> dict:
    job = get_job_by_id(job_id)
    if not job:
        return None
    file = get_file_by_id(job.file_id)
    graph = get_graph_by_id(job.graph_id)
    return {
        'job_id': job.job_id,
        'file_path': file.path if file else None,
        'graph_name': getattr(graph, 'graphId', None) if graph else None,
        'status': job.status,
        'stage': job.stage,
        'progress_index': job.progress_index,
        'end_stage': job.end_stage,
        'error_message': job.error_message,
        'partial_md_path': job.partial_md_path,
        'split_markdown_path': job.split_markdown_path,
        'markdown_path': job.markdown_path,
        'partial_triples_path': job.partial_triples_path,
        'triples_path': job.triples_path,
        'knowledge_path': job.knowledge_path
    }
