# -*- coding: utf-8 -*-
import argparse
import concurrent.futures
import traceback
from pathlib import Path
import os
import json
import gc
from datetime import datetime

from knowlion.abution_knowlion_driver import KnowLion
from abutionpy.abution_operations import *
from abutionpy.abution_connector import *
from knowlion.config import MODEL_CONFIGS, PROCESSING_CONFIG

#TODO
# OCR本地模型路径
model_path = str(Path("./model").resolve())


def process_document(knowlion: KnowLion, file_path: Path, model_path: str):
    """旧的单体处理函数已弃用；请使用 `doc_parse_task` 与 `post_process_task`。"""
    raise RuntimeError("process_document is deprecated; use doc_parse_task/post_process_task")


def doc_parse_task(knowlion: KnowLion, file_path: Path, model_path: str):
    """只执行耗资源的 doc_parsing（转换为 Markdown），返回 (file_path, md_content)
    在此阶段完成后会触发显式 GC 和可选的 GPU 缓存清理。
    """
    print(f"\n📄 [DOC_PARSE] 开始: {file_path}")
    try:
        md_content = knowlion.convert_to_markdown(model_path, str(file_path))
        print(f"   ✅ [DOC_PARSE] Markdown 长度: {len(md_content)} 字符")

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
                md_path = md_dir / md_fname
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                print(f"   💾 [DOC_PARSE] Markdown 已保存: {md_path}")
        except Exception as e:
            print(f"   ⚠️ [DOC_PARSE] 保存 Markdown 失败: {e}")

        return str(file_path), md_content
    except Exception as exc:
        print(f"   ❌ [DOC_PARSE] 失败: {exc}")
        traceback.print_exc()
        return str(file_path), None


def post_process_task(knowlion: KnowLion, file_path: str, md_content: str):
    """对已生成的 Markdown 执行 triples 提取、构建知识对象并保存到图库。
    返回处理结果字典。
    """
    print(f"\n🔧 [POST] 开始处理: {file_path}")
    try:
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
        except Exception as e:
            print(f"   ⚠️ [POST] 保存 Triples 失败: {e}")

        knowledge = knowlion.triple_to_knowledge(triples)
        print(f"   ✅ [POST] 知识对象数量: {len(knowledge)}")

        knowlion.knowledge_to_save(knowledge)
        print(f"   ✅ [POST] 已写入图数据库")

        return {
            "file": str(file_path),
            "markdown_len": len(md_content),
            "triples": len(triples),
            "knowledge": len(knowledge),
            "status": "ok"
        }
    except Exception as exc:
        print(f"   ❌ [POST] 处理失败: {exc}")
        traceback.print_exc()
        return {
            "file": str(file_path),
            "status": "error",
            "error": str(exc)
        }


def collect_files(input_path: Path):
    allowed_exts = {".pdf", ".doc", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".md"}
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(f"输入路径不存在: {input_path}")
    return sorted([p for p in input_path.iterdir() if p.suffix.lower() in allowed_exts and p.is_file()])


def main():
    parser = argparse.ArgumentParser(description="批量处理文件夹下的文档并写入图数据库")
    parser.add_argument("--input", default="./pdfs", help="待处理的文件或文件夹路径")
    parser.add_argument("--workers", type=int, default=2, help="并行线程数")
    parser.add_argument("--graph", default="RAG", help="图名称")
    args = parser.parse_args()

    input_path = Path(args.input)
    files = collect_files(input_path)
    if not files:
        print(f"⚠️ 未找到可处理的文件（扩展名: pdf/doc/docx/pptx/xlsx/png/jpg/jpeg/md）")
        return

    print(f"🚀 开始初始化 KnowLion 实例，图名: {args.graph}")
    knowlion = KnowLion(MODEL_CONFIGS, graph_name=args.graph)
    knowlion.init_graph()
    print(f"✅ 初始化完成，将处理 {len(files)} 个文件")

    proc_cfg = PROCESSING_CONFIG or {}
    doc_workers = int(proc_cfg.get('doc_workers', 1))
    post_workers = int(proc_cfg.get('post_workers', max(2, args.workers)))

    heavy_executor = concurrent.futures.ThreadPoolExecutor(max_workers=doc_workers)
    light_executor = concurrent.futures.ThreadPoolExecutor(max_workers=post_workers)

    heavy_futures = {heavy_executor.submit(doc_parse_task, knowlion, f, model_path): f for f in files}
    post_futures = []
    results = []

    try:
        # 当 heavy（doc_parse）完成时，提交对应的 post 任务到轻量池
        for hf in concurrent.futures.as_completed(heavy_futures):
            f = heavy_futures[hf]
            try:
                file_path_str, md_content = hf.result()
                if md_content is None:
                    results.append({"file": str(f), "status": "error", "error": "doc_parse_failed"})
                    continue
                # 提交 post 任务
                pf = light_executor.submit(post_process_task, knowlion, file_path_str, md_content)
                post_futures.append(pf)
            except Exception as e:
                print(f"⚠️ doc_parse 任务失败 for {f}: {e}")
                traceback.print_exc()

        # 收集所有 post 任务的结果
        for pf in concurrent.futures.as_completed(post_futures):
            try:
                res = pf.result()
                results.append(res)
            except Exception as e:
                print(f"⚠️ post task failed: {e}")
                traceback.print_exc()

    except KeyboardInterrupt:
        print("\n⏸️ 收到 Ctrl+C，正在尝试优雅取消未完成任务...")
        # 取消所有尚未开始或排队的 heavy future
        for hf in list(heavy_futures.keys()):
            try:
                if not hf.done():
                    hf.cancel()
            except Exception:
                pass

        # 处理已经完成的 heavy futures：为已完成的提交 post 任务
        for hf, f in heavy_futures.items():
            try:
                if hf.done() and not hf.cancelled():
                    try:
                        file_path_str, md_content = hf.result()
                        if md_content is not None:
                            pf = light_executor.submit(post_process_task, knowlion, file_path_str, md_content)
                            post_futures.append(pf)
                        else:
                            results.append({"file": str(f), "status": "error", "error": "doc_parse_failed"})
                    except Exception:
                        results.append({"file": str(f), "status": "error", "error": "doc_parse_exception"})
                else:
                    # 未完成的 heavy 任务视为用户取消
                    results.append({"file": str(f), "status": "error", "error": "cancelled_by_user"})
            except Exception:
                pass

        # 取消 any queued post_futures that haven't started
        for pf in list(post_futures):
            try:
                if not pf.done():
                    pf.cancel()
            except Exception:
                pass

        # 等待短时间让正在运行的 post 任务完成
        try:
            if post_futures:
                done, not_done = concurrent.futures.wait(post_futures, timeout=30)
                for d in done:
                    try:
                        res = d.result()
                        results.append(res)
                    except Exception:
                        pass
                for nd in not_done:
                    try:
                        nd.cancel()
                    except Exception:
                        pass
                    results.append({"file": "unknown", "status": "error", "error": "post_cancelled_by_user"})
        except Exception:
            pass
    finally:
        heavy_executor.shutdown(wait=False)
        light_executor.shutdown(wait=False)

    ok = [r for r in results if r.get("status") == "ok"]
    err = [r for r in results if r.get("status") != "ok"]
    print("\n================ 总结 ================")
    print(f"成功: {len(ok)} | 失败: {len(err)}")
    for r in ok:
        print(f"  • {r['file']} | MD={r['markdown_len']} | triples={r['triples']} | knowledge={r['knowledge']}")
    for r in err:
        print(f"  • {r['file']} | 错误: {r.get('error')}")


if __name__ == "__main__":
    main()