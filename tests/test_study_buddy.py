"""Study Buddy 单元测试 — Phase 1-2 纯函数测试，不调 LLM。"""

import json
import tempfile
from pathlib import Path

import pytest

from tasks.study_buddy.contracts import BUDDY_TREE_SCHEMA_VERSION
from tasks.study_buddy.memory import create_memory_tag, delete_memory_tag, load_memory_tags
from tasks.study_buddy.tree import build_buddy_tree
from tasks.study_buddy.tree_store import load_buddy_tree, save_buddy_tree


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_plan():
    return {
        "plan_id": "plan_test_001",
        "status": "active",
        "steps": [
            {"step_id": "step_1", "node_id": "n_intro", "title": "HBase 基础", "outcomes": ["hbase_intro"], "status": "completed", "order_index": 0},
            {"step_id": "step_2", "node_id": "n_rowkey", "title": "RowKey 设计", "outcomes": ["rowkey_design"], "status": "active", "order_index": 1},
            {"step_id": "step_3", "node_id": "n_hotspot", "title": "RowKey 热点", "outcomes": ["rowkey_hotspot"], "status": "pending", "order_index": 2},
        ],
    }


@pytest.fixture
def sample_features():
    return {
        "mastered_topics": ["大数据基础", "HDFS 基础"],
        "weak_topics": ["RowKey 热点", "预分区"],
        "stale_topics": ["MapReduce 基础"],
        "recently_grown": [],
        "by_topic": {
            "大数据基础": {"signal": "mastered", "score": 0.91},
            "HDFS 基础": {"signal": "mastered", "score": 0.88},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Tree
# ═══════════════════════════════════════════════════════════════════════════════

def test_build_buddy_tree_trunk(sample_plan, sample_features):
    tree = build_buddy_tree(1, 29, sample_plan, sample_features)
    assert tree["schema_version"] == BUDDY_TREE_SCHEMA_VERSION
    regions = tree["regions"]
    trunk = regions["trunk"]
    assert len(trunk) == 3
    assert trunk[0]["title"] == "HBase 基础"
    assert trunk[0]["status"] == "completed"
    assert trunk[1]["title"] == "RowKey 设计"
    assert trunk[1]["status"] == "active"


def test_build_buddy_tree_learned(sample_plan, sample_features):
    tree = build_buddy_tree(1, 29, sample_plan, sample_features)
    learned = tree["regions"]["learned"]
    titles = {n["title"] for n in learned}
    # mastered topics NOT in trunk
    assert "大数据基础" in titles
    assert "HDFS 基础" in titles
    # HBase topics ARE in trunk, should not appear in learned
    for n in learned:
        assert "HBase" not in n["title"]


def test_build_buddy_tree_explore(sample_plan, sample_features):
    tree = build_buddy_tree(1, 29, sample_plan, sample_features)
    explore = tree["regions"]["explore"]
    titles = {n["title"] for n in explore}
    # RowKey 热点 已在 trunk 中，不应该出现在 explore
    assert "预分区" in titles
    assert "MapReduce 基础" in titles


def test_build_buddy_tree_empty_plan(sample_features):
    tree = build_buddy_tree(1, 29, None, sample_features)
    assert tree["regions"]["trunk"] == []
    # learned/explore still populated from features
    assert len(tree["regions"]["learned"]) > 0


def test_build_buddy_tree_empty_features(sample_plan):
    tree = build_buddy_tree(1, 29, sample_plan, {})
    assert len(tree["regions"]["trunk"]) == 3
    assert tree["regions"]["learned"] == []
    assert tree["regions"]["explore"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Tree store
# ═══════════════════════════════════════════════════════════════════════════════

def test_save_and_load_tree_roundtrip(sample_plan, sample_features, monkeypatch, tmp_path):
    # Redirect buddy root to temp
    import tasks.study_buddy.tree_store as ts
    monkeypatch.setattr(ts, "_buddy_root", lambda: tmp_path)

    tree = build_buddy_tree(99, 29, sample_plan, sample_features)
    path = save_buddy_tree(99, 29, tree)
    assert Path(path).exists()

    loaded = load_buddy_tree(99, 29)
    assert loaded is not None
    assert loaded["schema_version"] == BUDDY_TREE_SCHEMA_VERSION
    assert loaded["regions"]["trunk"][0]["title"] == "HBase 基础"


def test_load_nonexistent_tree(monkeypatch, tmp_path):
    import tasks.study_buddy.tree_store as ts
    monkeypatch.setattr(ts, "_buddy_root", lambda: tmp_path)

    loaded = load_buddy_tree(999, 29)
    assert loaded is None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: Memory
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _temp_memory_root(monkeypatch, tmp_path):
    import tasks.study_buddy.memory as mem
    monkeypatch.setattr(mem, "_memory_root", lambda: tmp_path)


def test_create_memory_tag():
    r = create_memory_tag(1, 29, "RowKey 热点反复挫败")
    assert r["success"] is True
    assert r["action"] == "created"
    assert r["total_tags"] == 1


def test_create_duplicate_tag_updates():
    create_memory_tag(1, 29, "害怕考试")
    r = create_memory_tag(1, 29, "害怕考试")
    assert r["action"] == "updated"
    assert r["total_tags"] == 1  # not duplicated


def test_delete_memory_tag():
    create_memory_tag(1, 29, "test tag")
    r = delete_memory_tag(1, 29, "test tag")
    assert r["action"] == "deleted"
    assert r["total_tags"] == 0


def test_delete_nonexistent_tag():
    r = delete_memory_tag(1, 29, "nonexistent")
    assert r["action"] == "not_found"


def test_load_memory_tags_sorted():
    import time as _time
    create_memory_tag(1, 29, "old tag")
    _time.sleep(1.1)  # ensure distinct timestamps
    create_memory_tag(1, 29, "new tag")
    tags = load_memory_tags(1, 29)
    assert len(tags) == 2
    # sorted by last_referenced_at desc — newest first
    assert tags[0]["tag"] == "new tag"


def test_max_tags_pruning():
    for i in range(35):
        create_memory_tag(1, 29, f"tag_{i}")
    tags = load_memory_tags(1, 29)
    assert len(tags) <= 30
    # oldest tags should be pruned (lowest created_at)
    tag_texts = {t["tag"] for t in tags}
    assert "tag_0" not in tag_texts  # first created, should be pruned
    assert "tag_34" in tag_texts  # last created, should survive


def test_memory_survives_across_sessions(monkeypatch, tmp_path):
    """create in one "session", read in another."""
    import tasks.study_buddy.memory as mem
    monkeypatch.setattr(mem, "_memory_root", lambda: tmp_path)

    create_memory_tag(1, 29, "persistent tag")

    # simulate new session — just call load directly
    tags = load_memory_tags(1, 29)
    assert len(tags) == 1
    assert tags[0]["tag"] == "persistent tag"


def test_empty_tag_rejected():
    r = create_memory_tag(1, 29, "  ")
    assert r["success"] is False
    assert r["action"] == "empty"
