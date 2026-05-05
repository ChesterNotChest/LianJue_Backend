# -*- coding: utf-8 -*-
import argparse
import threading
from utils.job_checker import JobChecker

from app import create_app


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
