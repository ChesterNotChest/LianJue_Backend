# -*- coding: utf-8 -*-
import argparse
import concurrent.futures
import traceback
from pathlib import Path

from knowlion.abution_knowlion_driver import KnowLion
from abutionpy.abution_operations import *
from abutionpy.abution_connector import *
from knowlion.config import MODEL_CONFIGS

#TODO
# OCR本地模型路径
model_path = str(Path("./model").resolve())


def process_document(knowlion: KnowLion, file_path: Path, model_path: str):
    """处理单个文档，返回结果摘要（线程安全包装）。"""
    print(f"\n📄 开始处理: {file_path}")
    try:
        md_content = knowlion.convert_to_markdown(model_path, str(file_path))
        print(f"   ✅ Markdown 长度: {len(md_content)} 字符")

        triples = knowlion.markdown_to_triple(md_content)
        print(f"   ✅ 三元组数量: {len(triples)}")

        knowledge = knowlion.triple_to_knowledge(triples)
        print(f"   ✅ 知识对象数量: {len(knowledge)}")

        knowlion.knowledge_to_save(knowledge)
        print(f"   ✅ 已写入图数据库")

        return {
            "file": str(file_path),
            "markdown_len": len(md_content),
            "triples": len(triples),
            "knowledge": len(knowledge),
            "status": "ok"
        }
    except Exception as exc:  # pragma: no cover - runtime safety
        print(f"   ❌ 处理失败: {exc}")
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
    print(f"✅ 初始化完成，将并行处理 {len(files)} 个文件，线程数 {args.workers}")

    results = []
    # 使用线程池并安全处理 Ctrl+C（KeyboardInterrupt）
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(process_document, knowlion, f, model_path): f for f in files}
        try:
            for future in concurrent.futures.as_completed(future_map):
                try:
                    res = future.result()
                except Exception as e:
                    # 单个任务异常已经在 process_document 内处理并返回错误字典，
                    # 但在极少数情况下 future.result() 可能抛出其他异常，这里捕获并记录。
                    res = {"file": str(future_map.get(future)), "status": "error", "error": str(e)}
                results.append(res)
        except KeyboardInterrupt:
            print("\n⏸️ 收到 Ctrl+C，正在尝试安全取消正在运行的任务...")
            # 尝试取消尚未开始的 future
            for fut in future_map:
                cancelled = fut.cancel()
                if cancelled:
                    print(f"  - 已取消任务: {future_map[fut]}")
            # 阻止新任务提交并等待短时间让线程结束
            executor.shutdown(wait=False)
            print("✅ 已请求线程池关闭，正在退出")
            # 将仍然已完成的结果收集
            for fut in future_map:
                if fut.done():
                    try:
                        results.append(fut.result())
                    except Exception:
                        pass
            # 保持行为一致：将未完成的文件标记为中断
            for fut, fpath in future_map.items():
                if not fut.done():
                    results.append({"file": str(fpath), "status": "error", "error": "cancelled_by_user"})
            # 退出主流程
            print("退出中...")

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