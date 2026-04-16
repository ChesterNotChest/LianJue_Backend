import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import PROCESSING_CONFIG, MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion
from tasks.process_task import file_to_md
from tasks.post_process_task import md_to_triples, triples_to_knowledge, knowledge_to_save
from repositories.jobs_repo import (
    get_end_stage_by_job_id,
    list_all_jobs,
    update_job_status,
    update_error_message,
    get_job_by_id,
    get_progress_index_by_job_id,
    update_job_stage,
    get_job_stage_by_job_id,
    get_status_by_job_id
)
from extensions import db
from repositories.jobs_repo import get_graphId_by_job_id
from repositories.graph_repo import get_graph_by_id

logger = logging.getLogger(__name__)


class JobChecker:
    def __init__(self, app=None):
        cfg = PROCESSING_CONFIG or {}
        self.doc_workers = int(cfg.get('doc_workers', 1))
        self.post_workers = int(cfg.get('post_workers', max(2, self.doc_workers)))
        self.poll_interval = int(cfg.get('job_poll_interval', 5))
        # Do not instantiate a global KnowLion here; create one per task for isolation.
        self.default_graph_name = cfg.get('default_graph_name', 'RAG')
        # optional Flask app so threads can push app context when touching DB
        self.app = app
        # track running jobs to avoid double-submission
        self.running_heavy = set()
        self.running_light = set()
        self._lock = threading.Lock()
        # cooperative stop event used to signal threads to exit gracefully
        self._stop_event = threading.Event()

    def start(self):
        logger.info("JobChecker started")
        # keep executors on the instance so `stop()` can shut them down
        self.heavy_executor = ThreadPoolExecutor(max_workers=self.doc_workers)
        self.light_executor = ThreadPoolExecutor(max_workers=self.post_workers)

        # On startup, reset any jobs left in 'in_progress' to 'pending'
        try:
            logger.info("Resetting lingering in_progress jobs to pending (startup)")
            self._run_with_app_context(self._reset_in_progress_jobs)
        except Exception as e:
            logger.exception(f"Failed to reset in_progress jobs on startup: {e}")

        try:
            while True:
                if self._stop_event.is_set():
                    logger.info("JobChecker stop event set; exiting main loop")
                    break

                try:
                    self._run_with_app_context(self._poll_once)
                except Exception:
                    logger.exception("JobChecker poll iteration crashed")

                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received in JobChecker; setting stop event")
            self._stop_event.set()
        finally:
            try:
                if hasattr(self, 'heavy_executor'):
                    self.heavy_executor.shutdown(wait=False)
            except Exception:
                pass
            try:
                if hasattr(self, 'light_executor'):
                    self.light_executor.shutdown(wait=False)
            except Exception:
                pass

    def stop(self):
        """Signal the JobChecker to stop gracefully."""
        self._stop_event.set()

    def _reset_in_progress_jobs(self):
        jobs = list_all_jobs()
        for j in jobs:
            if getattr(j, 'status', None) == 'in_progress':
                update_job_status(j.job_id, 'pending')
                logger.info(f"Job {j.job_id} status reset from in_progress to pending")

    def _poll_once(self):
        # expire SQLAlchemy session to avoid returning stale objects from previous commits
        try:
            db.session.expire_all()
        except Exception:
            pass

        all_jobs = list_all_jobs()
        jobs_to_consider = [j for j in all_jobs if getattr(j, 'status', None) in ('in_progress', 'pending')]
        if not jobs_to_consider:
            return

        # prioritize resuming in_progress jobs first
        jobs_to_consider.sort(key=lambda j: 0 if getattr(j, 'status', None) == 'in_progress' else 1)

        for job in jobs_to_consider:
            job_id = job.job_id
            try:
                job_obj = get_job_by_id(job_id)
            except Exception as e:
                logger.error(f"Failed to fetch job {job_id}: {e}")
                update_error_message(job_id, str(e))
                update_job_status(job_id, 'failed')
                continue

            job_status = getattr(job_obj, 'status', None)
            if job_status not in ('in_progress', 'pending'):
                self._clear_running_flags(job_id)
                continue

            work_kind = self._get_work_kind(job_obj)
            if work_kind == 'complete':
                update_job_status(job_id, 'completed')
                self._clear_running_flags(job_id)
                continue

            needs_heavy = work_kind == 'heavy'
            needs_light = work_kind == 'light'
            if not needs_heavy and not needs_light:
                logger.warning(
                    f"Job {job_id} has no schedulable work; "
                    f"status={job_status}, stage={getattr(job_obj, 'stage', None)}, "
                    f"end_stage={getattr(job_obj, 'end_stage', None)}"
                )
                self._clear_running_flags(job_id)
                continue

            already_heavy, already_light = self._sync_running_flags_by_db_status(job_id, job_status)

            if job_status == 'in_progress':
                # resume without changing status
                if needs_heavy and not already_heavy:
                    with self._lock:
                        if len(self.running_heavy) < self.doc_workers:
                            print("   [JOB_CHECKER] resume heavy job_id:", job_id)
                            self.running_heavy.add(job_id)
                            fut = self.heavy_executor.submit(self._heavy_wrapper, job_id)
                            fut.add_done_callback(lambda f, jid=job_id: self._heavy_done_cb(f, jid))

                elif needs_light and not already_light:
                    with self._lock:
                        if len(self.running_light) < self.post_workers:
                            print("   [JOB_CHECKER] resume light job_id:", job_id)
                            self.running_light.add(job_id)
                            fut = self.light_executor.submit(self._light_wrapper, job_id)
                            fut.add_done_callback(lambda f, jid=job_id: self._light_done_cb(f, jid))

            else:  # pending
                if needs_heavy and not already_heavy:
                    with self._lock:
                        if len(self.running_heavy) < self.doc_workers:
                            # Re-check DB status so DB state remains authoritative.
                            fresh = None
                            try:
                                fresh = get_job_by_id(job_id)
                            except Exception:
                                fresh = None
                            if not fresh or getattr(fresh, 'status', None) != 'pending':
                                # Do not submit jobs that are no longer pending.
                                self.running_heavy.discard(job_id)
                                logger.info(f"Skipping submit for job {job_id}; current status is {getattr(fresh, 'status', None)}")
                            else:
                                print("   [JOB_CHECKER] submit heavy job_id:", job_id)
                                self.running_heavy.add(job_id)
                                update_job_status(job_id, 'in_progress')
                                fut = self.heavy_executor.submit(self._heavy_wrapper, job_id)
                                fut.add_done_callback(lambda f, jid=job_id: self._heavy_done_cb(f, jid))

                elif needs_light and not already_light:
                    with self._lock:
                        if len(self.running_light) < self.post_workers:
                            # Re-check DB status so DB state remains authoritative.
                            fresh = None
                            try:
                                fresh = get_job_by_id(job_id)
                            except Exception:
                                fresh = None
                            if not fresh or getattr(fresh, 'status', None) != 'pending':
                                self.running_light.discard(job_id)
                                logger.info(f"Skipping submit for job {job_id}; current status is {getattr(fresh, 'status', None)}")
                            else:
                                print("   [JOB_CHECKER] submit light job_id:", job_id)
                                self.running_light.add(job_id)
                                update_job_status(job_id, 'in_progress')
                                fut = self.light_executor.submit(self._light_wrapper, job_id)
                                fut.add_done_callback(lambda f, jid=job_id: self._light_done_cb(f, jid))

    def _clear_running_flags(self, job_id: str):
        with self._lock:
            self.running_heavy.discard(job_id)
            self.running_light.discard(job_id)

    def _sync_running_flags_by_db_status(self, job_id: str, job_status: str):
        with self._lock:
            if job_status == 'pending':
                self.running_heavy.discard(job_id)
                self.running_light.discard(job_id)
                return False, False
            if job_status != 'in_progress':
                self.running_heavy.discard(job_id)
                self.running_light.discard(job_id)
                return True, True
            return job_id in self.running_heavy, job_id in self.running_light

    def _get_graph_name_for_job(self, job_id: str):
        graph_name = get_graphId_by_job_id(job_id)
        if not graph_name:
            raise RuntimeError(f"Job {job_id} has no graph binding; refusing to use default graph")
        return graph_name

    def _canonical_stage(self, stage: str):
        if stage == 'triples_to_knowledge':
            return 'triple_to_knowledge'
        return stage

    def _stage_output_exists(self, job, stage: str):
        stage = self._canonical_stage(stage)
        if stage == 'pdf_to_md':
            return bool(getattr(job, 'markdown_path', None))
        if stage == 'md_to_triples':
            return bool(getattr(job, 'triples_path', None))
        if stage == 'triple_to_knowledge':
            return bool(getattr(job, 'knowledge_path', None))
        return False

    def _end_stage_output_exists(self, job):
        end_stage = self._canonical_stage(getattr(job, 'end_stage', None))
        if end_stage == 'knowledge_to_save':
            return False
        return self._stage_output_exists(job, end_stage)

    def _mark_completed_if_end_stage_done(self, job_id: str):
        job = get_job_by_id(job_id)
        if job and self._end_stage_output_exists(job):
            update_job_status(job_id, 'completed')
            logger.info(f"Job {job_id} reached end stage; marking as completed")
            return True
        return False

    def _get_work_kind(self, job):
        if self._end_stage_output_exists(job):
            return 'complete'

        stage = self._canonical_stage(getattr(job, 'stage', None))
        if stage == 'pdf_to_md' and not self._stage_output_exists(job, 'pdf_to_md'):
            return 'heavy'
        if stage in ('md_to_triples', 'triple_to_knowledge', 'knowledge_to_save'):
            return 'light'

        # Backfill stale stage values from existing artifacts.
        if not getattr(job, 'markdown_path', None):
            return 'heavy'
        return 'light'

    def _run_with_app_context(self, fn):
        if self.app:
            with self.app.app_context():
                return fn()
        return fn()

    # wrapper that runs heavy work
    def _heavy_wrapper(self, job_id: str):
        # Delegate partial-batch looping to `file_to_md` (it will handle resume and
        # repeated partial writes). Call it once and return; JobChecker should not
        # maintain an internal loop here.

        try:
            with self.app.app_context():
                if self._stop_event.is_set():
                    logger.info(f"Stop event set; skipping heavy work for job {job_id}")
                    return job_id

                # pass current progress index to file_to_md so it can resume from that batch
                cur_progress = get_progress_index_by_job_id(job_id) or 0
                print(f"   [HEAVY] single file_to_md call - job_id {job_id} | progress_index {cur_progress}")
                # Create a KnowLion instance per task using the job's configured graph name
                try:
                    graph_name = self._get_graph_name_for_job(job_id)
                except Exception as e:
                    logger.error(f"Cannot resolve graph for job {job_id}: {e}")
                    raise
                knowlion = KnowLion(MODEL_CONFIGS, graph_name=graph_name)
                _file_path, _md_content, _partial_files, total_batches = file_to_md(knowlion, job_id, process_index=cur_progress)
                job = get_job_by_id(job_id)
                if not job:
                    return job_id

                # Log final status after `file_to_md` returns; `file_to_md` is responsible for
                # updating `progress_index` and managing any partial-file loops.
                cur_progress = get_progress_index_by_job_id(job_id) or 0
                try:
                    logger.info(f"Job {job_id} heavy stage done: {cur_progress}/{total_batches}")
                    if self._canonical_stage(job.end_stage) == 'pdf_to_md':
                        update_job_status(job_id, 'completed')
                    else:
                        update_job_stage(job_id, 'md_to_triples')
                except Exception:
                    logger.debug(f"Finished heavy call for job {job_id}; progress read failed")
                return job_id
        except Exception as e:
            logger.error(f"   [HEAVY] worker failed - job_id {job_id}: {e}")
            raise

    def _light_wrapper(self, job_id: str):
        try:
            if self.app:
                with self.app.app_context():
                    return self._light_work_loop(job_id)
            else:
                return self._light_work_loop(job_id)
        except Exception as e:
            print(f"   [LIGHT] worker failed - job_id {job_id}: {e}")
            raise

    def _light_work_loop(self, job_id: str):
        # light pipeline should consult job.stage to determine what to run next
        while True:
            if self._stop_event.is_set():
                logger.info(f"Stop event set; breaking light loop for job {job_id}")
                break
            job = get_job_by_id(job_id)
            if not job:
                raise RuntimeError(f"Job {job_id} not found in light wrapper")
            if job.status == 'completed':
                logger.info(f"Job {job_id} already completed; exiting light loop")
                break
            if self._mark_completed_if_end_stage_done(job_id):
                break

            # Create a KnowLion instance per job for isolation and proper graph scoping
            try:
                graph_name = self._get_graph_name_for_job(job_id)
            except Exception as e:
                logger.error(f"Cannot resolve graph for job {job_id}: {e}")
                raise
            knowlion = KnowLion(MODEL_CONFIGS, graph_name=graph_name)

            if not getattr(job, 'triples_path', None):
                update_job_stage(job_id, 'md_to_triples')
                md_to_triples(knowlion, job_id)
                if self._mark_completed_if_end_stage_done(job_id):
                    break
                continue

            if not getattr(job, 'knowledge_path', None):
                update_job_stage(job_id, 'triple_to_knowledge')
                triples_to_knowledge(knowlion, job_id)
                if self._mark_completed_if_end_stage_done(job_id):
                    break
                continue

            # if knowledge exists but not saved to graph, call knowledge_to_save
            if getattr(job, 'knowledge_path', None):
                update_job_stage(job_id, 'knowledge_to_save')
                knowledge_to_save(knowlion, job_id)
                update_job_status(job_id, 'completed')
                logger.info(f"Job {job_id} reached terminal stage; marking as completed and exiting light loop")
                break

            # nothing to do
            break
        return job_id

    # Override the earlier callback implementations so all DB work in Future
    # callbacks runs inside a Flask application context.
    def _heavy_done_cb(self, fut, job_id: str):
        with self._lock:
            self.running_heavy.discard(job_id)
        try:
            self._run_with_app_context(lambda: self._handle_heavy_done(fut, job_id))
        except Exception as e:
            logger.error(f"Error handling heavy completion for {job_id}: {e}")

    def _handle_heavy_done(self, fut, job_id: str):
        job = get_job_by_id(job_id)
        if not job:
            logger.error(f"Job {job_id} not found in heavy done callback")
            return

        exc = fut.exception()
        if exc:
            logger.error(f"Heavy task exception for {job_id}: {exc}")
            update_error_message(job_id, str(exc))
            update_job_status(job_id, 'failed')
            return

        fresh = get_job_by_id(job_id) or job
        if getattr(fresh, 'status', None) == 'paused':
            logger.info(f"Job {job_id} is paused after heavy work; leaving status as paused")
            return

        if self._end_stage_output_exists(fresh):
            update_job_status(job_id, 'completed')
        else:
            update_job_status(job_id, 'pending')

    def _light_done_cb(self, fut, job_id: str):
        with self._lock:
            self.running_light.discard(job_id)
        try:
            self._run_with_app_context(lambda: self._handle_light_done(fut, job_id))
        except Exception as e:
            logger.error(f"Error handling light completion for {job_id}: {e}")

    def _handle_light_done(self, fut, job_id: str):
        exc = fut.exception()
        if exc:
            logger.error(f"Light task exception for {job_id}: {exc}")
            update_error_message(job_id, str(exc))
            update_job_status(job_id, 'failed')
            return

        fresh = get_job_by_id(job_id)
        if fresh and getattr(fresh, 'status', None) == 'paused':
            logger.info(f"Job {job_id} is paused after light work; leaving status as paused")
            return

        update_job_status(job_id, 'completed')
