import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import PROCESSING_CONFIG, MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion
from tasks.process_task import file_to_md
from tasks.post_process_task import md_to_triples, triples_to_knowledge, knowledge_to_save
from repositories.jobs_repo import (
    list_all_jobs,
    update_job_status,
    update_error_message,
    get_job_by_id,
    get_progress_index_by_job_id,
    update_job_stage,
    get_end_status_by_job_id,
)
from extensions import db

logger = logging.getLogger(__name__)


class JobChecker:
    def __init__(self, graph_name: str = "RAG", app=None):
        cfg = PROCESSING_CONFIG or {}
        self.doc_workers = int(cfg.get('doc_workers', 1))
        self.post_workers = int(cfg.get('post_workers', max(2, self.doc_workers)))
        self.poll_interval = int(cfg.get('job_poll_interval', 5))
        self.graph_name = graph_name
        # instantiate KnowLion once and reuse
        self.knowlion = KnowLion(MODEL_CONFIGS, graph_name=graph_name)
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

        try:
            while True:
                if self._stop_event.is_set():
                    logger.info("JobChecker stop event set; exiting main loop")
                    break
                # fetch jobs that are either in_progress or pending; prioritize in_progress
                # expire SQLAlchemy session to avoid returning stale objects from previous commits
                try:
                    db.session.expire_all()
                except Exception:
                    pass
                all_jobs = list_all_jobs()
                jobs_to_consider = [j for j in all_jobs if getattr(j, 'status', None) in ('in_progress', 'pending')]
                if not jobs_to_consider:
                    time.sleep(self.poll_interval)
                    continue

                # prioritize resuming in_progress jobs first
                jobs_to_consider.sort(key=lambda j: 0 if getattr(j, 'status', None) == 'in_progress' else 1)

                for job in jobs_to_consider:
                    job_id = job.job_id
                    with self._lock:
                        # Prefer reliable DB-derived indicators from the `job` object returned
                        # by `list_all_jobs`, but keep local sets as an additional guard.
                        needs_heavy_db = not getattr(job, 'markdown_path', None)
                        needs_light_db = bool(getattr(job, 'markdown_path', None)) and not getattr(job, 'status', None) == 'completed'

                        already_heavy = (job_id in self.running_heavy) or (getattr(job, 'status', None) == 'in_progress' and needs_heavy_db)
                        already_light = (job_id in self.running_light) or (getattr(job, 'status', None) == 'in_progress' and needs_light_db)

                    try:
                        job_obj = get_job_by_id(job_id)
                    except Exception as e:
                        logger.error(f"Failed to fetch job {job_id}: {e}")
                        update_error_message(job_id, str(e))
                        update_job_status(job_id, 'failed')
                        continue

                    needs_heavy = not getattr(job_obj, 'markdown_path', None)
                    needs_light = bool(getattr(job_obj, 'markdown_path', None)) and not getattr(job_obj, 'status', None) == 'completed'
                    #print(f"\n👀 检查 Job {job_id} - needs_heavy: {needs_heavy}, needs_light: {needs_light}, already_heavy: {already_heavy}, already_light: {already_light}")

                    if getattr(job_obj, 'status', None) == 'in_progress':
                        # resume without changing status
                        if needs_heavy and not already_heavy:
                            with self._lock:
                                if len(self.running_heavy) < self.doc_workers:
                                    print("   🔁 继续 heavy 工作 - job_id:", job_id)
                                    self.running_heavy.add(job_id)
                                    fut = self.heavy_executor.submit(self._heavy_wrapper, job_id)
                                    fut.add_done_callback(lambda f, jid=job_id: self._heavy_done_cb(f, jid))

                        elif needs_light and not already_light:
                            with self._lock:
                                if len(self.running_light) < self.post_workers:
                                    print("   🔁 继续 light 工作 job_id:", job_id)
                                    self.running_light.add(job_id)
                                    fut = self.light_executor.submit(self._light_wrapper, job_id)
                                    fut.add_done_callback(lambda f, jid=job_id: self._light_done_cb(f, jid))

                    else:  # pending
                        if needs_heavy and not already_heavy:
                            with self._lock:
                                if len(self.running_heavy) < self.doc_workers:
                                    print("   🚀 提交 heavy 工作 job_id:", job_id)
                                    self.running_heavy.add(job_id)
                                    update_job_status(job_id, 'in_progress')
                                    fut = self.heavy_executor.submit(self._heavy_wrapper, job_id)
                                    fut.add_done_callback(lambda f, jid=job_id: self._heavy_done_cb(f, jid))

                        elif needs_light and not already_light:
                            with self._lock:
                                if len(self.running_light) < self.post_workers:
                                    print("   🚀 提交 light 工作 job_id:", job_id)
                                    self.running_light.add(job_id)
                                    update_job_status(job_id, 'in_progress')
                                    fut = self.light_executor.submit(self._light_wrapper, job_id)
                                    fut.add_done_callback(lambda f, jid=job_id: self._light_done_cb(f, jid))

                # short sleep before next poll
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
                print(f"   🔄 [HEAVY] 单次调用 file_to_md - job_id {job_id} | 进度 - progress_index {cur_progress}")
                _file_path, _md_content, _partial_files, total_batches = file_to_md(self.knowlion, job_id, process_index=cur_progress)
                job = get_job_by_id(job_id)
                if not job:
                    return job_id

                # Log final status after `file_to_md` returns; `file_to_md` is responsible for
                # updating `progress_index` and managing any partial-file loops.
                cur_progress = get_progress_index_by_job_id(job_id) or 0
                try:
                    
                    logger.info(f"任务 {job_id} 完成: {cur_progress}/{total_batches}")
                    update_job_stage(job_id, 'md_to_triples')  # 直接更新阶段，light任务会根据这个阶段来判断下一步执行什么
                except Exception:
                    logger.debug(f"Finished heavy call for job {job_id}; progress read failed")
                return job_id
        except Exception as e:
            logger.error(f"   ❌ [HEAVY] 工作开展出现异常 - job_id {job_id}: {e}")
            raise


    def _light_wrapper(self, job_id: str):
        try:
            if self.app:
                with self.app.app_context():
                    return self._light_work_loop(job_id)
            else:
                return self._light_work_loop(job_id)
        except Exception as e:
            print(f"   ❌ [LIGHT] 工作开展出现异常 - job_id {job_id}: {e}")
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
            #设置前检查 stage == end_stage 的情况，如果相等说明这个阶段已经完成了，不需要再继续往下走了。
            if job.status == 'completed':
                logger.info(f"Job {job_id} already completed; exiting light loop")
                break
            ###################
            # 如下设置下一步执行的内容
            if not getattr(job, 'triples_path', None):
                update_job_stage(job_id, 'md_to_triples')
                md_to_triples(self.knowlion, job_id)
                # 若是终止步，则标记完成；否则继续循环
                if job.stage == job.end_stage:
                    update_job_status(job_id, 'completed')
                    logger.info(f"Job {job_id} reached end stage; marking as completed and exiting light loop")
                continue

            if not getattr(job, 'knowledge_path', None):
                update_job_stage(job_id, 'triples_to_knowledge')
                triples_to_knowledge(self.knowlion, job_id)
                # 若是终止步，则标记完成；否则继续循环
                if job.stage == job.end_stage:
                    update_job_status(job_id, 'completed')
                    logger.info(f"Job {job_id} reached end stage; marking as completed and exiting light loop")
                continue

            # if knowledge exists but not saved to graph, call knowledge_to_save
            if getattr(job, 'knowledge_path', None):
                update_job_stage(job_id, 'knowledge_to_save')
                knowledge_to_save(self.knowlion, job_id)
                # 防止二次进入这个流程，直接标记完成；否则继续循环
                if job.stage == job.end_stage:
                    update_job_status(job_id, 'completed')
                    logger.info(f"Job {job_id} reached end stage; marking as completed and exiting light loop")
                break

            # nothing to do
            break
        return job_id

    def _heavy_done_cb(self, fut, job_id: str):
        # called in worker thread when heavy future completes
        with self._lock:
            self.running_heavy.discard(job_id)
        # Fetch job record inside app context if available to avoid "working outside"
        try:
            if self.app:
                with self.app.app_context():
                    job = get_job_by_id(job_id)
            else:
                job = get_job_by_id(job_id)
        except Exception as e:
            logger.error(f"Failed to fetch job {job_id} in heavy done callback: {e}")
            return

        if not job:
            logger.error(f"Job {job_id} not found in heavy done callback")
            return

        try:
            # run callback under app context as it updates DB
            if self.app:
                with self.app.app_context():
                    exc = fut.exception()
                    if exc:
                        logger.error(f"Heavy task exception for {job_id}: {exc}")
                        update_error_message(job_id, str(exc))
                        update_job_status(job_id, 'failed')
                    else:
                        if job.stage == job.end_stage and job.markdown_path != None and job.markdown_path != "":
                            update_job_status(job_id, 'completed')
                        else:
                            # 标记为pending，等待light任务接手
                            update_job_status(job_id, 'pending')
            else:
                exc = fut.exception()
                if exc:
                    logger.error(f"Heavy task exception for {job_id}: {exc}")
                    update_error_message(job_id, str(exc))
                    update_job_status(job_id, 'failed')
                else:
                    update_job_status(job_id, 'pending')
        except Exception as e:
            logger.error(f"Error handling heavy completion for {job_id}: {e}")

    def _light_done_cb(self, fut, job_id: str):
        with self._lock:
            self.running_light.discard(job_id)
        try:
            if self.app:
                with self.app.app_context():
                    exc = fut.exception()
                    if exc:
                        logger.error(f"Light task exception for {job_id}: {exc}")
                        update_error_message(job_id, str(exc))
                        update_job_status(job_id, 'failed')
                    else:
                        update_job_status(job_id, 'completed')
            else:
                exc = fut.exception()
                if exc:
                    logger.error(f"Light task exception for {job_id}: {exc}")
                    update_error_message(job_id, str(exc))
                    update_job_status(job_id, 'failed')
                else:
                    update_job_status(job_id, 'completed')
        except Exception as e:
            logger.error(f"Error handling light completion for {job_id}: {e}")
