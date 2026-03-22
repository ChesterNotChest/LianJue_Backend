import json
from pathlib import Path
from datetime import datetime
import sys

from app import create_app
from tasks import syllabus_task as st


def run_real_syllabus_draft(pdf_name: str = "大数据概论.pdf", graph_id: int = 1, initial_prompt: str = "请根据教学日历生成教学大纲草稿"):
    # ensure PDF exists
    pdf_path = Path("./schedule/calendar") / pdf_name
    if not pdf_path.exists():
        print(f"❌ PDF 未找到: {pdf_path}. 请将教学日历放到 schedule/calendar/ 并命名为 '{pdf_name}'。")
        return 2

    # create Flask app and push app context so DB operations work
    app = create_app()
    with app.app_context():
        print(f"📥 上传日历: {pdf_path}")
        syllabus = st.upload_calendar(file_path=str(pdf_path), upload_time=datetime.utcnow().isoformat())
        print(f"   🆔 创建的 syllabus_id: {getattr(syllabus, 'syllabus_id', None)}")

        print("▶️ 开始构建 Syllabus 草稿（将等待后台的 heavy worker 完成 pdf->md 转换）...")
        # This call will block until the job's status becomes 'completed' (build_syllabus_draft contains the wait loop)
        res = st.build_syllabus_draft(syllabus_id=syllabus.syllabus_id, graph_id=graph_id, initial_prompt=initial_prompt)
        print("✅ build_syllabus_draft 返回")

        # Attempt to print saved draft path and a short preview
        try:
            saved = st.get_syllabus_by_id(syllabus.syllabus_id)
            draft_path = getattr(saved, 'syllabus_draft_path', None)
            if draft_path and Path(draft_path).exists():
                print(f"   💾 草稿已保存: {draft_path}")
                content = Path(draft_path).read_text(encoding='utf-8')
                print("--- 草稿预览（前1000字符） ---")
                print(content[:1000])
            else:
                print("   ⚠️ 未找到 syllabus_draft_path 或文件不存在。请检查后台处理日志。")
        except Exception as e:
            print(f"   ⚠️ 无法读取 syllabus 记录: {e}")

    return 0


if __name__ == "__main__":
    # allow optional args: pdf_name, graph_id
    pdf = sys.argv[1] if len(sys.argv) > 1 else "大数据概论.pdf"
    gid = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rc = run_real_syllabus_draft(pdf_name=pdf, graph_id=gid)
    sys.exit(rc)
    