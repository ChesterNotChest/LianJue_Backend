# -*- coding: utf-8 -*-
import argparse
import concurrent.futures
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
    args = parser.parse_args()

    # create Flask app and initialize DB/models
    app = create_app()

    # print(f"🚀 开始初始化 KnowLion 实例，图名: {args.graph}")
    # knowlion = KnowLion(MODEL_CONFIGS, graph_name=args.graph)
    knowlion = KnowLion(MODEL_CONFIGS, graph_name="RAG")
    knowlion.init_graph()

    # run the processing inside the Flask app context so models and `db` are available
    with app.app_context():

        pdf_dir = Path(args.input or "./pdfs")

        # collect added file ids so we can create jobs reliably

        # start JobChecker which will poll DB and orchestrate tasks
        checker = JobChecker(app=app)
        try:
            checker.start()
        except KeyboardInterrupt:
            print("Shutting down JobChecker")
            try:
                checker.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()