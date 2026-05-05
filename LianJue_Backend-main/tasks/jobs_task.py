from constant import JobStatus
from repositories.graph_repo import get_graph_by_id
from repositories.filegraph_repo import add_binding
from repositories.file_repo import get_file_by_id
from repositories.jobs_repo import create_job, update_job_status
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
    
def get_job_detail_info(job_id: int):
    job = jobs_repo.get_job_by_id(job_id)
    if not job:
        return None
    graph = get_graph_by_id(job.graph_id)
    file = get_file_by_id(job.file_id)
    return {
        "job_id": job.job_id,
        "file_id": job.file_id,
        "file_path": file.path if file else None,
        "graph_id": job.graph_id,
        "graph_name": getattr(graph, 'graphId', None) if graph else None,
        "status": job.status,
        "stage": job.stage,
        "progress_index": job.progress_index,
        "end_stage": job.end_stage
    }
