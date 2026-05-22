import shutil
from pathlib import Path

from tasks.study_graph import storage as study_graph_storage
from tasks.study_graph_task import build_study_graph_changes_from_student_payload, get_student_learning_tree, get_learning_tree_features, submit_learning_tree_changes


TEST_STUDY_GRAPH_ROOT = Path(__file__).resolve().parent / "artifacts" / "study_graph"


def _reset_artifact_root(name: str) -> Path:
    root = TEST_STUDY_GRAPH_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _base_payload() -> dict:
    return {
        "user_id": 900008,
        "syllabus_id": 900020,
        "subject_title": "大数据概论",
        "learning_goal": "掌握 HBase RowKey 设计",
        "personal_syllabus_context": {
            "learning_goal": "掌握 HBase RowKey 设计",
            "matched_weeks": [
                {"week_index": 1, "title": "HBase RowKey 设计", "content": "RowKey 热点、散列、预分区"}
            ],
        },
        "parent_candidates": [],
        "source": {"kind": "student_agent", "summary": "student agent payload"},
        "timestamp": 1760000000,
    }


def _submit_payload(payload: dict) -> dict:
    changes = build_study_graph_changes_from_student_payload(payload)
    assert changes
    submit_result = submit_learning_tree_changes(
        payload["user_id"],
        payload["syllabus_id"],
        changes,
        source=payload["source"],
        timestamp=payload["timestamp"],
        subject_title=payload["subject_title"],
    )
    assert submit_result["success"] is True
    return submit_result


def test_student_payload_round_trip_builds_changes_and_tree(monkeypatch):
    artifact_root = _reset_artifact_root("unit_payload_flow")
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: artifact_root)

    parent_payload = {
        **_base_payload(),
        "question": "HBase RowKey 设计包含哪些核心原则？",
        "rag_context": [{"title": "HBase RowKey 设计", "summary": "RowKey 设计需要结合查询模式、热点规避和预分区。"}],
        "detected_topics": [{"title": "HBase RowKey 设计", "confidence": 0.86, "signal": "learned"}],
        "events": [{"kind": "answer", "topic": "HBase RowKey 设计", "is_correct": True}],
        "timestamp": 1760000000,
    }
    hotspot_payload = {
        **_base_payload(),
        "question": "RowKey 如何避免热点？",
        "rag_context": [{"title": "HBase RowKey 设计", "summary": "RowKey 热点通常来自单调递增键或访问集中。"}],
        "detected_topics": [{"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}],
        "events": [{"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": False}],
        "parent_candidates": [{"title": "HBase RowKey 设计", "child_title": "RowKey 热点"}],
        "timestamp": 1760000600,
    }
    pre_split_payload = {
        **_base_payload(),
        "question": "预分区策略如何缓解 RowKey 热点？",
        "rag_context": [{"title": "预分区策略", "summary": "预分区可以提前拆分 Region，降低热点写入压力。"}],
        "detected_topics": [{"title": "预分区策略", "confidence": 0.74, "signal": "learned"}],
        "events": [{"kind": "answer", "topic": "预分区策略", "is_correct": True}],
        "parent_candidates": [{"title": "RowKey 热点", "child_title": "预分区策略"}],
        "timestamp": 1760001200,
    }
    hash_prefix_payload = {
        **_base_payload(),
        "question": "散列前缀为什么能减少写入集中？",
        "rag_context": [{"title": "散列前缀", "summary": "散列前缀把相邻业务键打散到不同 Region。"}],
        "detected_topics": [{"title": "散列前缀", "confidence": 0.72, "signal": "practiced"}],
        "events": [{"kind": "practice", "topic": "散列前缀", "is_correct": True}],
        "parent_candidates": [{"title": "RowKey 热点", "child_title": "散列前缀"}],
        "timestamp": 1760001800,
    }

    for payload in [parent_payload, hotspot_payload, pre_split_payload, hash_prefix_payload]:
        _submit_payload(payload)

    changes = build_study_graph_changes_from_student_payload(hotspot_payload)
    assert any(change["knowledge"]["title"] == "RowKey 热点" for change in changes)

    tree = get_student_learning_tree(parent_payload["user_id"], parent_payload["syllabus_id"])
    features = get_learning_tree_features(parent_payload["user_id"], parent_payload["syllabus_id"])
    assert tree["success"] is True
    assert features["success"] is True
    assert tree["tree"]["subject_title"] == "大数据概论"
    assert tree["tree"]["title"] == "大数据概论学习成长树"
    assert tree["tree"]["virtual_root"]["title"] == "大数据概论"
    assert {"HBase RowKey 设计", "RowKey 热点", "预分区策略", "散列前缀"}.issubset(set(features["learned_topics"]))

    nodes = tree["tree"]["nodes"]
    nodes_by_title = {node["title"]: node for node in nodes}
    assert len(nodes) == 4
    assert nodes_by_title["RowKey 热点"]["parent_node_id"] == nodes_by_title["HBase RowKey 设计"]["node_id"]
    assert nodes_by_title["预分区策略"]["parent_node_id"] == nodes_by_title["RowKey 热点"]["node_id"]
    assert nodes_by_title["散列前缀"]["parent_node_id"] == nodes_by_title["RowKey 热点"]["node_id"]
    assert len(tree["tree"]["edges"]) == 3

