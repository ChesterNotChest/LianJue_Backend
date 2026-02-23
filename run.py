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
    # 线性逐个处理文件以节省内存（保留 Ctrl+C 友好退出）
    try:
        for f in files:
            res = process_document(knowlion, f, model_path)
            results.append(res)
    except KeyboardInterrupt:
        print("\n⏸️ 收到 Ctrl+C，正在中断后续任务并生成汇总...")
        # 标记尚未处理的文件为被用户取消
        processed = {r.get("file") for r in results}
        for f in files:
            fp = str(f)
            if fp not in processed:
                results.append({"file": fp, "status": "error", "error": "cancelled_by_user"})

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