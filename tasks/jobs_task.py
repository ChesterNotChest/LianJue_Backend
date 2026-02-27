from datetime import datetime

from constant import JobStatus
from extensions import db
from repositories.graph_repo import get_graph_by_id
from repositories.filegraph_repo import list_graphs_by_file
from repositories.file_repo import create_file, get_file_by_id
from repositories.jobs_repo import create_job, update_job_status, list_all_jobs
from repositories import jobs_repo

#########
# 上传文件
def add_file(file_path, upload_time: str = None): # TODO 这里之后准备从api那边接收内容；理论暂时不调用
    # 这里可以添加文件上传的逻辑，比如保存文件到服务器或云存储
    # 然后创建一个新的任务来处理这个文件
    if not upload_time:
        upload_time = datetime.utcnow().isoformat()
    file = create_file(file_path, upload_time=upload_time)
    return file.file_id
#########

#########
# 任务构建与启停
def create_process_job(graphId: str, file_id: int, end_stage: str):
    job = create_job(file_id=file_id, graph_id=graphId, end_stage=end_stage)
    return job.job_id if job else None
    # notify_worker_to_resume(job_id, file_id)

def pause_job(job_id):
    # notify_worker_to_pause(job_id)
    update_job_status(job_id, JobStatus.PAUSED.value)

def resume_job(job_id):
    update_job_status(job_id, JobStatus.IN_PROGRESS.value)
    # notify_worker_to_resume(job_id)

def end_job(job_id):
    update_job_status(job_id, JobStatus.COMPLETED.value)
    # notify_worker_to_end(job_id)

#########

#########
# 进度展示
def list_all_jobs(**kwargs):
    return jobs_repo.list_all_jobs(**kwargs)
    