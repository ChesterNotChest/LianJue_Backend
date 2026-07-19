"""回填：将 Chester 已有的 study_graph 节点写入 profile 的 learning_records。"""
import os; os.environ["FLASK_APP"] = "app.py"
from app import create_app
app = create_app()

with app.app_context():
    from tasks.learning_profile.storage import load_existing_profile, save_personal_profile
    from tasks.study_graph.service import get_student_learning_tree

    for sid, title in [(8,"大数据"),(18,"算法"),(104,"软件")]:
        tree = get_student_learning_tree(1, sid)
        if not tree.get("success"):
            print(f"[{title}] 无学习树，跳过")
            continue
        nodes = tree["tree"].get("nodes", [])
        if not nodes:
            print(f"[{title}] 0 节点")
            continue

        existing, _ = load_existing_profile(1, sid)
        if not existing:
            print(f"[{title}] 无 profile，跳过")
            continue

        records = existing.setdefault("learning_records", [])
        added = 0
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title_n = node.get("title", "")
            mastery = node.get("mastery", {}) if isinstance(node.get("mastery"), dict) else {}
            score_n = mastery.get("score", 0.5)
            ts = node.get("last_updated_at") or node.get("first_seen_at", 0)
            # 去重
            if any(r.get("topic") == title_n for r in records):
                continue
            records.append({
                "event_type": "study_session",
                "topic": title_n,
                "status": "completed",
                "score": score_n,
                "started_at": int(ts),
                "duration_minutes": 25,
                "meta": {"knowledge_points": [title_n]},
            })
            added += 1

        if added:
            save_personal_profile(1, sid, existing)
        print(f"[{title}] {len(nodes)} nodes → +{added} learning_records (total: {len(records)})")
