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

    # run the processing inside the Flask app context so models and `db` are available
    with app.app_context():

        pdf_dir = Path(args.input or "./pdfs")

        # collect added file ids so we can create jobs reliably
        # TODO 这里之后靠api
        file_ids = []
        for (root, dirs, files) in os.walk(pdf_dir):
            for file in files:
                if file.lower().endswith(('.pdf', '.docx', '.txt')):  # 支持的文件类型
                    file_path = os.path.join(root, file)
                    try:
                        fid = add_file(file_path)
                        file_ids.append(fid)
                    except Exception as e:
                        print(f"添加文件失败 {file_path}: {e}")
                        traceback.print_exc()
        # TODO 这里之后靠api
        try:
            for fid in file_ids:
                create_process_job(1, fid, JobStage.KNOWLEDGE_TO_SAVE.value) # 暂时默认使用 graph_id=1 和最终阶段为 KNOWLEDGE_TO_SAVE
        except Exception as e:
            print(f"创建处理任务失败: {e}")
            traceback.print_exc()

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