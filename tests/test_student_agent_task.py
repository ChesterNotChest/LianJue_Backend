from tasks.study_graph import student_agent as sat


def test_merge_parent_candidates_uses_tree_context_for_missing_child_mapping():
    payload = {
        "question": "RowKey 如何避免热点？",
        "learning_goal": "掌握 HBase RowKey 设计",
        "detected_topics": [{"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}],
        "events": [{"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": False}],
        "parent_candidates": [],
    }
    tree_context = {
        "ranked_candidates": [
            {"node_id": "knowledge:parent:001", "title": "HBase RowKey 设计", "score": 0.91, "matched_by": "substring"},
        ]
    }

    merged = sat._merge_parent_candidates(payload, tree_context)

    assert merged == [
        {
            "title": "HBase RowKey 设计",
            "child_title": "RowKey 热点",
            "existing_node_id": "knowledge:parent:001",
            "score": 0.91,
            "matched_by": "substring",
        }
    ]


def test_normalize_rag_context_items_merges_payload_and_runtime_results():
    payload = {
        "question": "RowKey 如何避免热点？",
        "learning_goal": "掌握 HBase RowKey 设计",
        "rag_context": [{"title": "HBase RowKey 设计", "summary": "原始上下文"}],
    }
    runtime_rag_context = {
        "results": [{"content": "运行时检索结果"}],
        "paragraphs": ["补充段落"],
    }

    normalized = sat._normalize_rag_context_items(payload, runtime_rag_context)

    assert normalized[0] == {"title": "HBase RowKey 设计", "summary": "原始上下文"}
    assert any(item["summary"] == "运行时检索结果" for item in normalized)
    assert any(item["summary"] == "补充段落" for item in normalized)
