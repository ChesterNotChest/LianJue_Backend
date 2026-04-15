#!/usr/bin/env python3
"""Integration-style test for process_task and post_process_task.

This script scans `test_data/` for PDF files and, for each file:
- uploads it as a syllabus calendar via `tasks.syllabus_task.upload_calendar`
- triggers `build_syllabus_draft` (which will wait/poll until workers finish)

The test is intended to be run manually in an environment where DB and
background workers (or JobChecker) are available. It documents inputs and
expected outputs for test reporting; it does not require passing in CI.
"""
from pathlib import Path
from datetime import datetime
import sys

from app import create_app


def main():
    print("Process/post-process integration test (uses test_data PDFs)")

    root = Path(__file__).parent
    test_data_dir = root / 'test_data'
    if not test_data_dir.exists():
        print(f"test_data directory not found: {test_data_dir}")
        return

    pdfs = sorted([p for p in test_data_dir.iterdir() if p.suffix.lower() == '.pdf'])
    if not pdfs:
        print(f"No PDF files found under {test_data_dir}; place sample PDFs there to run this test.")
        return

    print(f"Found {len(pdfs)} PDFs to process:")
    for p in pdfs:
        print(" -", p.name)

    try:
        app = create_app()
    except Exception as e:
        print(f"Failed to create Flask app: {e}")
        return

    with app.app_context():
        try:
            from tasks import syllabus_task as st
        except Exception as e:
            print(f"Failed to import syllabus_task: {e}")
            return

        # Optional: allow passing a graph_id via argv
        #!/usr/bin/env python3
        """Integration-style job-checker end-to-end test.

        This test focuses on exercising `utils.job_checker.JobChecker` through a
        complete job lifecycle for knowledge ingestion and QA readiness. It:

        - Creates a temporary test graph
        - Registers a test PDF file into the file table
        - Creates a processing job (pdf->md->triples->knowledge->save)
        - Starts `JobChecker` in a background thread
        - Polls job status/stage and records timestamps for state transitions
        - Stops the JobChecker after completion or timeout and prints a report

        Notes:
        - This is an integration test script intended for manual runs in an
          environment where the DB and any required services (LLM drivers, graph
          endpoints) are available. It documents expected inputs/outputs and
          timing; it is acceptable if it fails in CI due to external dependencies.
        """

        import time
        import threading
        from pathlib import Path
        from datetime import datetime
        import sys

        from app import create_app


        def main():
            print("JobChecker end-to-end integration test")

            root = Path(__file__).parent
            test_data_dir = root / 'test_data'
            if not test_data_dir.exists():
                print(f"test_data directory not found: {test_data_dir}")
                return

            pdfs = sorted([p for p in test_data_dir.iterdir() if p.suffix.lower() == '.pdf'])
            if not pdfs:
                print(f"No PDF files found under {test_data_dir}; place sample PDFs there to run this test.")
                return

            # choose the first PDF as the test artifact
            pdf = pdfs[0]
            print(f"Using PDF for job: {pdf.name}")

            try:
                app = create_app()
            except Exception as e:
                print(f"Failed to create Flask app: {e}")
                return

            with app.app_context():
                try:
                    from repositories.graph_repo import create_graph, remove_graph
                    from tasks.file_task import add_file
                    from repositories.jobs_repo import create_job, get_status_by_job_id, get_job_stage_by_job_id, get_progress_index_by_job_id, get_job_details
                    from utils.job_checker import JobChecker
                except Exception as e:
                    print(f"Failed to import required modules: {e}")
                    return

                # create a test graph and register a file record
                graph = create_graph(f"TEST_GRAPH_{int(time.time())}")
                graph_id = getattr(graph, 'graph_id', None)
                print(f"Created test graph id: {graph_id}")

                try:
                    # register file under a temp folder inside project to avoid needing external paths
                    tmp_dir = Path(__file__).parent / 'tmp_files'
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    save_dir = str(tmp_dir.absolute())
                    file_id = add_file(save_dir, pdf.name, file_bytes=pdf.read_bytes(), upload_time=datetime.utcnow().isoformat())
                    print(f"Registered file_id: {file_id}")
                except Exception as e:
                    print(f"Failed to register file: {e}")
                    try:
                        remove_graph(graph_id)
                    except Exception:
                        pass
                    return

                # create a job that will run until knowledge is saved
                job = create_job(file_id=file_id, graph_id=graph_id, end_stage='knowledge_to_save')
                job_id = getattr(job, 'job_id', None)
                print(f"Created job id: {job_id} (status={get_status_by_job_id(job_id)})")

                # Start JobChecker in background thread
                jc = JobChecker(app=app)
                t = threading.Thread(target=jc.start, daemon=True)
                t.start()

                # Poll job status and stage transitions, record timestamps
                transitions = []
                start_time = time.time()
                timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 600  # default 10 minutes

                last_status = None
                last_stage = None
                try:
                    while True:
                        now = time.time()
                        if now - start_time > timeout:
                            print("Timeout reached while waiting for job to complete")
                            break

                        status = get_status_by_job_id(job_id)
                        stage = get_job_stage_by_job_id(job_id)
                        progress = get_progress_index_by_job_id(job_id)

                        if status != last_status or stage != last_stage:
                            ts = datetime.utcnow().isoformat()
                            transitions.append({'ts': ts, 'status': status, 'stage': stage, 'progress': progress})
                            print(f"[{ts}] status={status}, stage={stage}, progress={progress}")
                            last_status = status
                            last_stage = stage

                        if status in ('completed', 'failed'):
                            print(f"Job finished with status={status}")
                            break

                        time.sleep(2)
                finally:
                    # signal JobChecker to stop and wait briefly
                    jc.stop()
                    t.join(timeout=5)

                # collect final details and print report
                details = get_job_details(job_id)
                import json as _json
                report = {
                    'job_id': job_id,
                    'transitions': transitions,
                    'final_details': details,
                }
                print('\n=== Job Report ===')
                print(_json.dumps(report, ensure_ascii=False, indent=2))

                # cleanup: do not remove created files/graphs/jobs automatically in this test,
                # but print guidance for manual cleanup
                print('\nNOTE: test created graph_id=%s and file_id=%s. Remove them manually if desired.' % (graph_id, file_id))


        if __name__ == '__main__':
            main()
