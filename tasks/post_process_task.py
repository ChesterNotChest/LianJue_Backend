from pathlib import Path
import json
import time
from datetime import datetime

from config import PROCESSING_CONFIG
 
from constant import JobStatus
from extensions import db
from repositories.graph_repo import get_graph_by_id
from repositories.filegraph_repo import list_graphs_by_file
from repositories.file_repo import get_file_by_id
from repositories.jobs_repo import (
    get_job_by_id,
    update_job_stage,
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
    

    triples = knowlion.markdown_to_triple(md_content)
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
    knowledge = knowlion.triple_to_knowledge(triples)
    print(f"   ✅ [POST] 知识对象数量: {len(knowledge)}")

    # 对象序列化保存
    try:
        knowledge_dir = Path("./knowledge")
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        knowledge_fname = f"{Path(file_path).stem}_{ts}.json"
        knowledge_path = knowledge_dir / knowledge_fname
        with open(knowledge_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
        print(f"   💾 [POST] 知识对象已保存: {knowledge_path}")
        update_knowledge_path(job_id, str(knowledge_path))
    except Exception as e:
        print(f"   ⚠️ [POST] 保存知识对象失败: {e}")


def knowledge_to_save(knowlion, job_id: int):
    job = get_job_by_id(job_id)
    if not job:
        print(f"   ❌ [POST] 无效的 job_id: {job_id}")
        return []

    knowledge_path = job.knowledge_path

    # 读取知识对象文件
    try:
        with open(knowledge_path, 'r', encoding='utf-8') as f:
            knowledge = json.load(f)
    except Exception as e:
        print(f"   ❌ [POST] 读取知识对象文件失败: {e}")
        return []

    knowlion.knowledge_to_save(knowledge)
    print(f"   ✅ [POST] 已写入图数据库")
    

