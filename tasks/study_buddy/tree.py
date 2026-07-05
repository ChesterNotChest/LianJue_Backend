"""学习进度树构建 — 快照 study_graph + merge plan + 保留 buddy_notes。

v2 schema:
  nodes: dict[node_id → {node_id, title, normalized_title, mastery, summary,
         parent_node_id, edges: [{target, relation}], buddy_notes: [{note,created_at,source,mastery_hint}]}]
  regions: {trunk: [node_id], learned: [node_id], explore: [node_id]}
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .contracts import (
    BUDDY_REGION_EXPLORE,
    BUDDY_REGION_LEARNED,
    BUDDY_REGION_TRUNK,
    BUDDY_TREE_SCHEMA_VERSION,
)
from .tree_store import load_buddy_tree


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _safe_list(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _snapshot_from_study_graph(user_id: int, syllabus_id: int) -> dict:
    """从 study_graph 读取完整节点+边，映射为 buddy 节点格式。

    Returns: dict with nodes (dict[node_id→node]) and edges list.
    """
    nodes: dict = {}
    edges: list[dict] = []
    try:
        from tasks import study_graph_task

        tree_result = study_graph_task.get_student_learning_tree(user_id, syllabus_id)
        study_tree = _safe_dict(tree_result.get("tree") if isinstance(tree_result, dict) else {})
        raw_nodes = _safe_list(study_tree.get("nodes"))
        raw_edges = _safe_list(study_tree.get("edges"))

        for node in raw_nodes:
            if not isinstance(node, dict):
                continue
            nid = _safe_text(node.get("node_id"))
            title = _safe_text(node.get("title"))
            if not nid or not title:
                continue
            mastery = _safe_dict(node.get("mastery"))
            nodes[nid] = {
                "node_id": nid,
                "title": title,
                "normalized_title": _safe_text(node.get("normalized_title") or title),
                "mastery": {
                    "label": _safe_text(mastery.get("label")) or "learning",
                    "score": float(mastery.get("score") or 0.5),
                },
                "summary": _safe_text(node.get("summary")),
                "parent_node_id": _safe_text(node.get("parent_node_id")),
                "edges": [],
                "buddy_notes": [],
            }

        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue
            src = _safe_text(edge.get("source") or edge.get("source_node_id"))
            tgt = _safe_text(edge.get("target") or edge.get("target_node_id"))
            rel = _safe_text(edge.get("edge_type") or "parent_of")
            if not src or not tgt:
                continue
            edges.append({"source": src, "target": tgt, "relation": rel})
            if src in nodes:
                nodes[src]["edges"].append({"target": tgt, "relation": rel})
    except Exception:
        pass
    return {"nodes": nodes, "edges": edges}


def _title_in_trunk(title: str, trunk_titles: set[str], trunk_outcomes: set[str]) -> bool:
    t = title.lower()
    if t in trunk_titles:
        return True
    for tt in trunk_titles:
        if t in tt or tt in t:
            return True
    for ot in trunk_outcomes:
        ol = ot.lower()
        if t in ol or ol in t:
            return True
    return False


def _classify_node(node: dict, trunk_ids: set[str], trunk_titles: set[str], trunk_outcomes: set[str]) -> str | None:
    """将一个节点分类到 trunk / learned / explore / None（跳过）。"""
    nid = node.get("node_id", "")
    title = node.get("title", "")
    mastery = node.get("mastery", {})
    label = mastery.get("label", "learning")
    score = mastery.get("score", 0.5)

    if nid in trunk_ids or _title_in_trunk(title, trunk_titles, trunk_outcomes):
        return BUDDY_REGION_TRUNK
    if label == "mastered" or score >= 0.85:
        return BUDDY_REGION_LEARNED
    if label == "weak" or score < 0.5:
        return BUDDY_REGION_EXPLORE
    if label in ("learning", "practiced"):
        return BUDDY_REGION_LEARNED if score >= 0.5 else BUDDY_REGION_EXPLORE
    return None  # unknown — skip


def build_buddy_tree(
    user_id: int,
    syllabus_id: int,
    plan: dict | None,
    study_graph_features: dict | None,
) -> dict:
    """快照 study_graph + merge plan 投影 + 保留 buddy_notes。

    Args:
        user_id / syllabus_id: 用户和大纲 ID
        plan: active_learning_plan，含 steps
        study_graph_features: 当前未使用（保留兼容），节点数据改为从 study_graph 直接读

    Returns:
        v2 tree dict
    """
    plan = plan if isinstance(plan, dict) else {}
    now_ts = int(time.time())

    # ── 1. 加载已有 buddy_tree（保留 buddy_notes） ──
    old_tree = load_buddy_tree(user_id, syllabus_id)
    old_nodes: dict = {}
    if isinstance(old_tree, dict) and isinstance(old_tree.get("nodes"), dict):
        old_nodes = old_tree["nodes"]

    # ── 2. 快照 study_graph ──
    snapshot = _snapshot_from_study_graph(user_id, syllabus_id)
    sg_nodes = snapshot["nodes"]
    sg_edges = snapshot["edges"]

    # ── 3. Merge：study_graph 节点覆盖 mastery，保留已有 buddy_notes ──
    merged_nodes: dict = {}
    for nid, node in sg_nodes.items():
        merged = dict(node)
        old = old_nodes.get(nid) if isinstance(old_nodes.get(nid), dict) else {}
        # 保留已有 buddy_notes
        existing_notes = _safe_list(old.get("buddy_notes"))
        if existing_notes:
            merged["buddy_notes"] = existing_notes
        merged_nodes[nid] = merged

    # ── 4. trunk region：从 plan.steps 投影 ──
    trunk_ids: set[str] = set()
    trunk_titles: set[str] = set()
    trunk_outcomes: set[str] = set()
    steps = _safe_list(plan.get("steps"))
    for step in steps:
        if not isinstance(step, dict):
            continue
        title = _safe_text(step.get("title"))
        trunk_titles.add(title.lower())
        for o in _safe_list(step.get("outcomes")):
            trunk_outcomes.add(o.lower())

    # 尝试将 step 匹配到 study_graph 节点
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_title = _safe_text(step.get("title")).lower()
        matched = False
        for nid, node in merged_nodes.items():
            nt = node.get("title", "").lower()
            if step_title in nt or nt in step_title:
                trunk_ids.add(nid)
                matched = True
                break
        if not matched and step_title:
            # step 没有匹配到现有节点，创一个占位
            sid = _safe_text(step.get("step_id"))
            trunk_ids.add(sid)
            merged_nodes[sid] = {
                "node_id": sid,
                "title": _safe_text(step.get("title")),
                "normalized_title": step_title,
                "mastery": {"label": _safe_text(step.get("status")) or "pending", "score": 0.0},
                "summary": "",
                "parent_node_id": "",
                "edges": [],
                "buddy_notes": [],
            }

    # ── 5. 分类 regions ──
    regions: dict = {BUDDY_REGION_TRUNK: [], BUDDY_REGION_LEARNED: [], BUDDY_REGION_EXPLORE: []}
    for nid, node in merged_nodes.items():
        if nid in trunk_ids:
            regions[BUDDY_REGION_TRUNK].append(nid)
            continue
        region = _classify_node(node, trunk_ids, trunk_titles, trunk_outcomes)
        if region:
            regions[region].append(nid)

    return {
        "schema_version": BUDDY_TREE_SCHEMA_VERSION,
        "user_id": int(user_id),
        "syllabus_id": int(syllabus_id),
        "updated_at": now_ts,
        "nodes": merged_nodes,
        "edges": sg_edges,
        "regions": regions,
    }
