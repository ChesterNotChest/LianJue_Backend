"""学习记录树构建。

三层树结构：
- trunk:   active_plan.steps（主干学习路径）
- learned: study_graph 中 mastered/learned 但不在 trunk 中的节点
- explore: study_graph 中 weak/stale 节点，与 trunk 有关联
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .contracts import (
    BUDDY_REGION_EXPLORE,
    BUDDY_REGION_LEARNED,
    BUDDY_REGION_TRUNK,
    BUDDY_TREE_SCHEMA_VERSION,
)


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


def _title_in_trunk(title: str, trunk_titles: set[str], trunk_outcomes: set[str]) -> bool:
    """检查 title 是否已被 trunk 覆盖。"""
    t = title.lower()
    if t in trunk_titles:
        return True
    # 子串匹配：title 或其片段是否出现在 trunk 的 title/outcome 中
    for tt in trunk_titles:
        if t in tt or tt in t:
            return True
    for ot in trunk_outcomes:
        ol = ot.lower()
        if t in ol or ol in t:
            return True
    return False


def _find_association(
    title: str,
    outcomes: list[str],
    trunk_nodes: list[dict],
) -> list[str]:
    """找到与 trunk 节点的关联（按 title 或 outcomes 匹配）。"""
    associated: list[str] = []
    search_terms = {title.lower()}
    for o in outcomes:
        search_terms.add(o.lower())
    for tn in trunk_nodes:
        tn_title = _safe_text(tn.get("title")).lower()
        tn_outcomes = {_safe_text(o).lower() for o in _safe_list(tn.get("outcomes"))}
        if any(term in tn_title or term in tn_outcomes for term in search_terms if term):
            associated.append(tn.get("step_id") or tn.get("node_id") or tn_title)
        elif any(
            tn_term in title.lower()
            for tn_term in [tn_title] + list(tn_outcomes)
        ):
            associated.append(tn.get("step_id") or tn.get("node_id") or tn_title)
    return list(dict.fromkeys(associated))  # 去重保序


def build_buddy_tree(
    user_id: int,
    syllabus_id: int,
    plan: dict | None,
    study_graph_features: dict | None,
) -> dict:
    """从 active plan 和 study graph features 构建三层学习记录树。

    Args:
        user_id: 用户 ID
        syllabus_id: 大纲 ID
        plan: active_learning_plan 返回的 plan dict，含 steps 列表
        study_graph_features: get_learning_tree_features 返回的 features dict，
            含 mastered_topics / learned_topics / weak_topics / stale_topics

    Returns:
        tree dict，含 schema_version / user_id / syllabus_id / updated_at / regions
    """
    plan = plan if isinstance(plan, dict) else {}
    features = study_graph_features if isinstance(study_graph_features, dict) else {}

    now_ts = int(time.time())

    # ── trunk: plan.steps 直接取 ──────────────────────
    trunk: list[dict] = []
    trunk_titles: set[str] = set()
    trunk_outcomes: set[str] = set()
    steps = _safe_list(plan.get("steps"))
    for step in steps:
        if not isinstance(step, dict):
            continue
        title = _safe_text(step.get("title"))
        outcomes = _safe_list(step.get("outcomes"))
        trunk.append({
            "step_id": _safe_text(step.get("step_id")),
            "node_id": _safe_text(step.get("node_id")),
            "title": title,
            "outcomes": outcomes,
            "status": _safe_text(step.get("status")) or "pending",
            "order_index": int(step.get("order_index") or 0),
        })
        trunk_titles.add(title.lower())
        for o in outcomes:
            trunk_outcomes.add(o.lower())

    # ── learned: mastered/learned 但不在 trunk ─────────
    learned: list[dict] = []
    learned_titles: set[str] = set()
    # 从 features 中收集 mastered 和 learned 节点
    mastered = _safe_list(features.get("mastered_topics"))
    weak = _safe_list(features.get("weak_topics"))
    stale = _safe_list(features.get("stale_topics"))
    recently_grown = _safe_list(features.get("recently_grown"))

    # 尝试从 features 的 by_topic 或 detail 中获取更丰富的信息
    topic_details = features.get("topic_details") if isinstance(features.get("topic_details"), dict) else {}
    weak_details = features.get("weak_topic_details") if isinstance(features.get("weak_topic_details"), dict) else {}

    for topic in mastered:
        title = _safe_text(topic)
        if not title or _title_in_trunk(title, trunk_titles, trunk_outcomes):
            continue
        if title in learned_titles:
            continue
        learned_titles.add(title)
        detail = topic_details.get(title) if isinstance(topic_details.get(title), dict) else {}
        learned.append({
            "title": title,
            "signal": "mastered",
            "score": float(detail.get("score") or 0.85),
            "associated_trunk": _find_association(title, [], trunk),
        })

    # also check by_topic signals
    by_topic = features.get("by_topic") if isinstance(features.get("by_topic"), dict) else {}
    for topic_name, info in by_topic.items():
        title = _safe_text(topic_name)
        if not title or title in learned_titles:
            continue
        if _title_in_trunk(title, trunk_titles, trunk_outcomes):
            continue
        signal = _safe_text(info.get("signal") or info.get("level") if isinstance(info, dict) else "")
        if signal in ("mastered", "learned", "practiced"):
            learned_titles.add(title)
            learned.append({
                "title": title,
                "signal": signal,
                "score": float(info.get("score") or 0.8) if isinstance(info, dict) else 0.8,
                "associated_trunk": _find_association(title, [], trunk),
            })

    # ── explore: weak/stale，和 trunk 有关联 ────────────
    explore: list[dict] = []
    explore_titles: set[str] = set()

    for topic_list, signal in [(weak, "weak"), (stale, "stale")]:
        for topic in topic_list:
            title = _safe_text(topic)
            if not title or title in explore_titles:
                continue
            if _title_in_trunk(title, trunk_titles, trunk_outcomes):
                continue
            if title in learned_titles:
                continue
            explore_titles.add(title)
            detail = weak_details.get(title) if isinstance(weak_details.get(title), dict) else {}
            explore.append({
                "title": title,
                "signal": signal,
                "score": float(detail.get("score") or 0.3),
                "associated_trunk": _find_association(title, [], trunk),
                "associated_learned": _find_association(title, [], learned),
            })

    # 最近生长但不在 learned/explore 中的
    for topic in recently_grown:
        title = _safe_text(topic)
        if not title or title in explore_titles or title in learned_titles:
            continue
        if _title_in_trunk(title, trunk_titles, trunk_outcomes):
            continue
        explore_titles.add(title)
        explore.append({
            "title": title,
            "signal": "recently_grown",
            "score": 0.5,
            "associated_trunk": _find_association(title, [], trunk),
            "associated_learned": _find_association(title, [], learned),
        })

    return {
        "schema_version": BUDDY_TREE_SCHEMA_VERSION,
        "user_id": int(user_id),
        "syllabus_id": int(syllabus_id),
        "updated_at": now_ts,
        "regions": {
            BUDDY_REGION_TRUNK: trunk,
            BUDDY_REGION_LEARNED: learned,
            BUDDY_REGION_EXPLORE: explore,
        },
    }
