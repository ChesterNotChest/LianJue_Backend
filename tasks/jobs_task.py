from datetime import datetime

from constant import JobStatus
from extensions import db
from repositories.graph_repo import get_graph_by_id
from repositories.filegraph_repo import add_binding
from repositories.file_repo import create_file, get_file_by_id
from repositories.jobs_repo import create_job, update_job_status, list_all_jobs
from repositories import jobs_repo



#########
# 任务构建与启停
def create_process_job(graph_id: int, file_id: int, end_stage: str):
    job = create_job(file_id=file_id, graph_id=graph_id, end_stage=end_stage)
    add_binding(file_id, graph_id)
    return job.job_id if job else None
    # notify_worker_to_resume(job_id, file_id)

def pause_job(job_id):
    update_job_status(job_id, JobStatus.PAUSED.value)

def resume_job(job_id):
    update_job_status(job_id, JobStatus.PENDING.value)

def end_job(job_id):
    update_job_status(job_id, JobStatus.COMPLETED.value)

#########

#########
# 进度展示
def list_all_jobs(**kwargs):
    return jobs_repo.list_all_jobs(**kwargs)
    