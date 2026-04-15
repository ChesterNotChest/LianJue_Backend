# -*- coding: utf-8 -*-
import argparse
import concurrent.futures
import threading
import traceback
from pathlib import Path
import os
import json
import gc
from datetime import datetime
from constant import JobStage
from tasks.jobs_task import create_process_job
from tasks.file_task import add_file
from tasks.process_task import file_to_md
from tasks.post_process_task import md_to_triples, triples_to_knowledge
from knowlion.abution_knowlion_driver import KnowLion
from abutionpy.abution_operations import *
from abutionpy.abution_connector import *
from config import MODEL_CONFIGS, PROCESSING_CONFIG
from utils.job_checker import JobChecker

from config import get_config
from app import create_app

# model_path can be configured via config.json PROCESSING_CONFIG.MODEL_PATH
cfg = get_config()
proc_cfg = cfg.get("PROCESSING_CONFIG", {}) if isinstance(cfg, dict) else {}
model_path = str(Path(proc_cfg.get("MODEL_PATH", "./model")).resolve())


def main():
    parser = argparse.ArgumentParser(description="批量处理文件夹下的文档并写入图数据库")
    parser.add_argument("--input", default="./pdfs", help="待处理的文件或文件夹路径")
    parser.add_argument("--workers", type=int, default=2, help="并行线程数")
    parser.add_argument("--host", default="0.0.0.0", help="Flask 服务监听地址")
    parser.add_argument("--port", type=int, default=5000, help="Flask 服务监听端口")
    parser.add_argument("--debug", action="store_true", help="启用 Flask debug 模式")
    parser.add_argument("--no-job-checker", action="store_true", help="只启动 Flask API，不启动后台 JobChecker")
    args = parser.parse_args()

    # create Flask app and initialize DB/models
    flask_app = create_app()

    checker = None
    if not args.no_job_checker:
        checker = JobChecker(app=flask_app)
        checker_thread = threading.Thread(target=checker.start, name="job-checker", daemon=True)
        checker_thread.start()

    try:
        flask_app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
    finally:
        if checker:
            checker.stop()


if __name__ == "__main__":
    main()
