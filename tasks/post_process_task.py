from pathlib import Path
import json
import time
import pickle
from datetime import datetime

from config import PROCESSING_CONFIG
 
from constant import JobStatus
from extensions import db
from repositories.graph_repo import get_graph_by_id
from repositories.graph_repo import get_graph_by_graphId, create_graph
from repositories.filegraph_repo import list_graphs_by_file
from repositories.file_repo import get_file_by_id
from repositories.jobs_repo import (
    get_job_by_id,
    update_job_stage,
    update_split_markdown_path,
    update_triples_path,
    update_knowledge_path,
    update_partial_md_path,
    update_markdown_path,
    update_job_status,
    update_error_message
)

#########

#########
# md到三元组
def md_to_triples(knowlion, job_id):
    job = get_job_by_id(job_id)
    if not job:
        print(f"   ❌ [POST] 无效的 job_id: {job_id}")
        return []
    file = get_file_by_id(job.file_id)
    if not file:
        print(f"   ❌ [POST] 无效的 file_id: {job.file_id}")
        return []
    file_path = file.path
    md_path = job.markdown_path
    if not md_path:
        print(f"   ❌ [POST] Job {job_id} 没有 markdown_path，无法进行 md_to_triples")
        return []
    
    # 读取md文件
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
    except Exception as e:
        print(f"   ❌ [POST] 读取 Markdown 文件失败: {e}")
        return []
    

    # 首先持久化待处理列表（to_process） — 仅在 job.split_markdown_path 不存在时执行一次
    try:
        if not job.split_markdown_path:
            paragraphs = knowlion.markdown_split_paragraphs(md_content)
            print(f"   ℹ️ [POST] 切分得到 {len(paragraphs)} 个段落")
            # 构建 to_process 结构并写入文件：[{"paragraph_index":xxx,"content_to_process": "..."}, ...]
            to_process = []
            for p in paragraphs:
                to_process.append({
                    "paragraph_index": p.get("index"),
                    "content_to_process": p.get("content")
                })
            # persist to triples dir using job_id prefix
            try:
                triples_dir = Path("./triples")
                triples_dir.mkdir(parents=True, exist_ok=True)
                to_process_path = triples_dir / f"{job_id}_to_process.json"
                with open(to_process_path, 'w', encoding='utf-8') as f:
                    json.dump(to_process, f, ensure_ascii=False, indent=2)
                update_split_markdown_path(job_id, str(to_process_path))
                print(f"   💾 [POST] to_process 已保存: {to_process_path}")
            except Exception as e:
                print(f"   ⚠️ [POST] 保存 to_process 失败: {e}")
        else:
            print(f"   ℹ️ [POST] job 已存在 split_markdown_path: {job.split_markdown_path}，跳过切分持久化")
    except Exception as e:
        print(f"   ⚠️ [POST] 切分并保存 to_process 失败: {e}")

    # 使用 job_id 驱动后续处理，driver 将从 job.split_markdown_path 中读取待处理条目
    triples = knowlion.markdown_to_triple(job_id)
    print(f"   ✅ [POST] 三元组数量: {len(triples)}")

    # 根据配置保存 triples
    try:
        proc_cfg = PROCESSING_CONFIG or {}
        if proc_cfg.get("save_triples", True):
            triples_dir = Path("./triples")
            triples_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            triples_fname = f"{Path(file_path).stem}_{ts}.json"
            triples_path = triples_dir / triples_fname
            with open(triples_path, 'w', encoding='utf-8') as f:
                json.dump(triples, f, ensure_ascii=False, indent=2)
            print(f"   💾 [POST] Triples 已保存: {triples_path}")
            update_triples_path(job_id, str(triples_path))
    except Exception as e:
        print(f"   ⚠️ [POST] 保存 Triples 失败: {e}")

#########

#########
# 三元组到知识对象
def triples_to_knowledge(knowlion, job_id: int):
    
    job = get_job_by_id(job_id)
    if not job:
        print(f"   ❌ [POST] 无效的 job_id: {job_id}")
        return []
    file = get_file_by_id(job.file_id)
    if not file:
        print(f"   ❌ [POST] 无效的 file_id: {job.file_id}")
        return []
    file_path = file.path
    triples_path = job.triples_path

    # 读取 triples 文件
    try:
        with open(triples_path, 'r', encoding='utf-8') as f:
            triples = json.load(f)
    except Exception as e:
        print(f"   ❌ [POST] 读取 Triples 文件失败: {e}")
        return []

    # list of knowledge objects
    knowledge = knowlion.triple_to_knowledge(triples, job_id=job_id)
    print(f"   ✅ [POST] 知识对象数量: {len(knowledge)}")

    # 保存为 pickle（二进制），不再使用 JSON 序列化回退
    try:
        knowledge_dir = Path("./knowledge")
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        knowledge_fname = f"{Path(file_path).stem}_{ts}.pkl"
        knowledge_path = knowledge_dir / knowledge_fname
        with open(knowledge_path, 'wb') as f:
            pickle.dump(knowledge, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"   💾 [POST] 知识对象已以 pickle 存储: {knowledge_path}")
        update_knowledge_path(job_id, str(knowledge_path))
    except Exception as e:
        print(f"   ⚠️ [POST] 保存知识对象失败: {e}")


def knowledge_to_save(knowlion, job_id: int):
    job = get_job_by_id(job_id)
    if not job:
        print(f"   ❌ [POST] 无效的 job_id: {job_id}")
        return []

    knowledge_path = job.knowledge_path

    # 读取 pickle 格式的知识对象文件
    try:
        with open(knowledge_path, 'rb') as f:
            knowledge = pickle.load(f)
    except Exception as e:
        print(f"   ❌ [POST] 读取知识对象文件失败: {e}")
        return []

    # Ensure a graph record exists in MySQL and initialize graph lazily if needed.
    try:
        graphId = knowlion.graph_name
        existing = get_graph_by_graphId(graphId)
        if not existing:
            # create a DB record so callers/ops can see this graph
            try:
                created = create_graph(graphId)
                print(f"   ℹ️ [POST] 已在 MySQL 中创建 graph 记录: {graphId}")
            except Exception as e:
                print(f"   ⚠️ [POST] 创建 graph 记录失败: {e}")

        # Attempt to initialize graph on KnowLion instance (will be tolerant to failures)
        try:
            knowlion.init_graph()
        except Exception as e:
            print(f"   ⚠️ [POST] init_graph 失败（已记录 outbox），继续执行：{e}")

    except Exception as e:
        print(f"   ⚠️ [POST] 检查/创建 graph 记录时发生错误: {e}")

    knowlion.knowledge_to_save(knowledge)
    print(f"   ✅ [POST] 已写入图数据库（或已入 outbox）")
    

