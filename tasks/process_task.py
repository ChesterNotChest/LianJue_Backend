import gc
from pathlib import Path
from datetime import datetime
import traceback
from knowlion.abution_knowlion_driver import KnowLion
from constant import JobStatus
from extensions import db
from repositories.graph_repo import get_graph_by_id
from repositories.filegraph_repo import list_graphs_by_file
from repositories.file_repo import get_file_by_id
from repositories.jobs_repo import create_job, get_job_by_id, update_job_stage, update_markdown_path, update_job_status
from config import MODEL_CONFIGS, PROCESSING_CONFIG, get_config


# model_path can be configured via config.json PROCESSING_CONFIG.MODEL_PATH
cfg = get_config()
proc_cfg = cfg.get("PROCESSING_CONFIG", {}) if isinstance(cfg, dict) else {}
model_path = str(Path(proc_cfg.get("MODEL_PATH", "./model")).resolve())



#########
# 原 doc_parse_task；唯一的heavy


def file_to_md(knowlion: KnowLion,  job_id: str, process_index: int = 0):
    """只执行耗资源的 doc_parsing（转换为 Markdown），返回 (file_path, md_content)
    在此阶段完成后会触发显式 GC 和可选的 GPU 缓存清理。
    """

    try:
        update_job_status(job_id, JobStatus.IN_PROGRESS.value)
    except Exception as e:
        print(f"   ⚠️ [DOC_PARSE] 无法更新 Job 状态: {e}")
        return None, None, [], None


    job = get_job_by_id(job_id)  # 确保 job 存在
    if not job:
        print(f"   ❌ [DOC_PARSE] 无效的 job_id: {job_id}")
        return None, None, [], None
    file = get_file_by_id(job.file_id)
    if not file:
        print(f"   ❌ [POST] 无效的 file_id: {job.file_id}")
        return []
    file_path = file.path


    print(f"\n📄 [DOC_PARSE] 开始: {file_path}")
    try:
        md_res = knowlion.convert_to_markdown(model_path, str(file_path), job_id=job_id, process_index=process_index)
        # convert_to_markdown may return (md_content, partial_files) or (md_content, partial_files, total_batches)
        total_batches = None
        if isinstance(md_res, tuple):
            if len(md_res) >= 3:
                md_content, partial_files, total_batches = md_res[0], md_res[1], md_res[2]
            elif len(md_res) >= 2:
                md_content, partial_files = md_res[0], md_res[1]
            else:
                md_content = md_res[0]
                partial_files = []
        else:
            md_content = md_res
            partial_files = []
        print(f"   ✅ [DOC_PARSE] Markdown 长度: {len(md_content)} 字符，partial files: {len(partial_files)}")

        # doc_parsing 阶段完成后，显式释放内存并在需要时清理 GPU 缓存
        try:
            gc.collect()
            device_mode = str(PROCESSING_CONFIG.get("device_mode", "cpu")).lower()
            if device_mode in ("cuda", "gpu"):
                try:
                    import torch
                    if getattr(torch, "cuda", None) is not None:
                        torch.cuda.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass

        # 根据配置保存 Markdown（避免覆盖通过时间戳）
        try:
            proc_cfg = PROCESSING_CONFIG or {}
            if proc_cfg.get("save_md", True):
                md_dir = Path("./markdowns")
                md_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                md_fname = f"{Path(file_path).stem}_{ts}.md"
                update_markdown_path(job_id, str(md_dir / md_fname))  # 更新数据库中的 markdown 路径
                md_path = md_dir / md_fname
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                print(f"   💾 [DOC_PARSE] Markdown 已保存: {md_path}")
        except Exception as e:
            print(f"   ⚠️ [DOC_PARSE] 保存 Markdown 失败: {e}")

        return str(file_path), md_content, partial_files, total_batches
    except Exception as exc:
        print(f"   ❌ [DOC_PARSE] 失败: {exc}")
        traceback.print_exc()
        return str(file_path), None, [], None
    
