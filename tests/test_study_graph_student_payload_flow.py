from tasks.study_graph_task import build_study_graph_changes_from_student_payload, get_student_learning_tree, get_learning_tree_features, submit_learning_tree_changes


def test_student_payload_round_trip_builds_changes_and_tree(monkeypatch):
    payload = {
        "user_id": 8,
        "syllabus_id": 20,
        "subject_title": "大数据概论",
        "question": "RowKey 如何避免热点？",
        "learning_goal": "掌握 HBase RowKey 设计",
        "personal_syllabus_context": {
            "learning_goal": "掌握 HBase RowKey 设计",
            "matched_weeks": [
                {"week_index": 1, "title": "HBase RowKey 设计", "content": "RowKey 热点、散列、预分区"}
            ],
        },
        "rag_context": [
            {"title": "HBase RowKey 设计", "summary": "RowKey 热点通常来自单调递增键或访问集中。"}
        ],
        "detected_topics": [{"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}],
        "events": [{"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": False}],
        "parent_candidates": [],
        "source": {"kind": "student_agent", "summary": "student agent payload"},
        "timestamp": 1760000000,
    }

    changes = build_study_graph_changes_from_student_payload(payload)
    assert changes
    submit_result = submit_learning_tree_changes(
        payload["user_id"],
        payload["syllabus_id"],
        changes,
        source=payload["source"],
        timestamp=payload["timestamp"],
    )
    assert submit_result["success"] is True
    tree = get_student_learning_tree(payload["user_id"], payload["syllabus_id"])
    features = get_learning_tree_features(payload["user_id"], payload["syllabus_id"])
    assert tree["success"] is True
    assert features["success"] is True
    assert "RowKey 热点" in features["learned_topics"]

