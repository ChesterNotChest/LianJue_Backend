"""推荐结果 → 前端数据契约测试。

不调 LLM/DB/RAG，只验证：
1. 真实快照 JSON 能被解析为前端期望的结构
2. 图、候选路径、RAG overlay 字段完整
"""

import json
from pathlib import Path

import pytest

# 最新真实 E2E 产物目录
E2E_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "e2e"
REQUIRED_NODE_FIELDS = {"id", "title", "difficulty", "learning_time_est", "node_source"}
REQUIRED_EDGE_FIELDS = {"edge_id", "source", "target", "type"}
REQUIRED_CANDIDATE_FIELDS = {"path", "cost", "skills", "path_depth"}
REQUIRED_BEST_PATH_FIELDS = {"path", "cost", "skills", "path_depth"}
REQUIRED_RAG_MATCHED_FIELDS = {"node_id", "title", "relevance"}


def _load_latest_snapshot() -> dict | None:
    """Find the newest recommendation_snapshot_detail.json under any E2E artifact dir."""
    candidates = sorted(
        E2E_ARTIFACT_DIR.glob("*/recommendation_snapshot_detail.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            snapshot = data.get("snapshot", data)
            rec = snapshot.get("recommendation", snapshot)
            if isinstance(rec, dict) and rec.get("graph"):
                return rec
        except (json.JSONDecodeError, KeyError):
            continue
    return None


rec = _load_latest_snapshot()

@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_graph_nodes_have_required_fields():
    nodes = (rec["graph"] or {}).get("nodes", [])
    assert len(nodes) > 0
    for node in nodes:
        missing = REQUIRED_NODE_FIELDS - set(node.keys())
        assert not missing, f"node {node.get('id')}: missing {missing}"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_graph_nodes_title_not_empty():
    for node in (rec["graph"] or {}).get("nodes", []):
        assert isinstance(node.get("title"), str) and node["title"].strip(), (
            f"node {node.get('id')} has empty title"
        )


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_graph_edges_have_required_fields():
    edges = (rec["graph"] or {}).get("edges", [])
    assert len(edges) > 0
    for edge in edges:
        missing = REQUIRED_EDGE_FIELDS - set(edge.keys())
        assert not missing, f"edge {edge.get('edge_id')}: missing {missing}"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_edges_reference_existing_nodes():
    node_ids = {n["id"] for n in (rec["graph"] or {}).get("nodes", [])}
    for edge in (rec["graph"] or {}).get("edges", []):
        assert edge["source"] in node_ids, f"edge {edge['edge_id']}: source {edge['source']} not in nodes"
        assert edge["target"] in node_ids, f"edge {edge['edge_id']}: target {edge['target']} not in nodes"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_candidates_have_required_fields():
    candidates = rec.get("candidates", [])
    for c in candidates:
        missing = REQUIRED_CANDIDATE_FIELDS - set(c.keys())
        assert not missing, f"candidate missing {missing}"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_best_path_exists_and_valid():
    bp = rec.get("best_path")
    assert isinstance(bp, dict), "best_path must be a dict"
    assert len(bp.get("path", [])) > 0, "best_path.path must not be empty"
    for field in REQUIRED_BEST_PATH_FIELDS:
        assert field in bp, f"best_path missing {field}"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_rag_overlay_matched_nodes():
    rag = rec.get("rag_overlay")
    if not isinstance(rag, dict) or not rag.get("matched_nodes"):
        pytest.skip("no RAG overlay")
    for mn in rag["matched_nodes"]:
        missing = REQUIRED_RAG_MATCHED_FIELDS - set(mn.keys())
        assert not missing, f"RAG matched_node {mn.get('node_id')}: missing {missing}"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_best_path_nodes_in_graph():
    node_ids = {n["id"] for n in (rec["graph"] or {}).get("nodes", [])}
    bp = rec.get("best_path", {})
    for nid in bp.get("path", []):
        assert nid in node_ids, f"best_path node {nid} not in graph"


@pytest.mark.skipif(rec is None, reason="no valid recommendation snapshot found")
def test_candidate_paths_exist_and_in_graph():
    node_ids = {n["id"] for n in (rec["graph"] or {}).get("nodes", [])}
    bp_path = set(rec.get("best_path", {}).get("path", []))
    for c in rec.get("candidates", []):
        for nid in c.get("path", []):
            assert nid in node_ids, f"candidate node {nid} not in graph"
    # at least one candidate should match best_path
    assert any(
        set(c.get("path", [])) == bp_path for c in rec.get("candidates", [])
    ), "best_path must match at least one candidate"
