from pathlib import Path

from constant import BasePath, JobStatus
from repositories.graph_repo import get_graph_by_id
from repositories.filegraph_repo import add_binding, get_bindings_by_file_id
from repositories.file_repo import get_file_by_id
from repositories.jobs_repo import create_job, update_job_status
from repositories import jobs_repo
from extensions import db
from schemas.filegraph import FileGraph
from schemas.material import Material
from schemas.syllabus import Syllabus


BACKEND_ROOT = Path(__file__).resolve().parent.parent
SAFE_DELETE_ROOTS = tuple(
    (BACKEND_ROOT / base_path.value.lstrip('/')).resolve()
    for base_path in (
        BasePath.FILE_CACHE,
        BasePath.PDF_ROOT,
        BasePath.MARKDOWN_ROOT,
        BasePath.TRIPLES_ROOT,
        BasePath.KNOWLEDGE_ROOT,
        BasePath.CALENDAR_ROOT,
        BasePath.MATERIAL_PDF_ROOT,
    )
)


def _is_safe_delete_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    return any(resolved == root or root in resolved.parents for root in SAFE_DELETE_ROOTS)


def _safe_remove_path(path_value):
    if not path_value:
        return
    try:
        path = Path(path_value)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        if not _is_safe_delete_path(path):
            return
        if path.exists() and path.is_file():
            path.unlink()
    except Exception:
        pass



#########
# 任务构建与启停
def create_process_job(graph_id: int, file_id: int, end_stage: str):
    job = create_job(file_id=file_id, graph_id=graph_id, end_stage=end_stage)
    add_binding(file_id, graph_id)
    return job.job_id if job else None
    # notify_worker_to_resume(job_id, file_id)


def purge_job_record(job_id: int) -> bool:
    job = jobs_repo.get_job_by_id(job_id)
    if not job:
        return False

    file_id = getattr(job, 'file_id', None)
    graph_id = getattr(job, 'graph_id', None)
    paths_to_remove = [
        getattr(job, 'partial_md_path', None),
        getattr(job, 'markdown_path', None),
        getattr(job, 'split_markdown_path', None),
        getattr(job, 'partial_triples_path', None),
        getattr(job, 'triples_path', None),
        getattr(job, 'knowledge_path', None),
    ]

    try:
        binding = FileGraph.query.filter_by(file_id=file_id, graph_id=graph_id).first()
        if binding is not None:
            db.session.delete(binding)

        db.session.delete(job)

        file = get_file_by_id(file_id) if file_id is not None else None
        if file is not None:
            remaining_bindings = get_bindings_by_file_id(file_id)
            syllabus_ref = Syllabus.query.filter_by(file_id=file_id).first()
            material_ref = Material.query.filter_by(file_id=file_id).first()
            if not remaining_bindings and syllabus_ref is None and material_ref is None:
                paths_to_remove.append(getattr(file, 'path', None))
                db.session.delete(file)

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    for path_to_remove in paths_to_remove:
        _safe_remove_path(path_to_remove)

    return True


def get_job_status(job_id: int):
    job = jobs_repo.get_job_by_id(job_id)
    return getattr(job, 'status', None) if job else None

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
