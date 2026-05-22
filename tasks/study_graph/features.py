from __future__ import annotations

from typing import Any

from tasks.study_graph.contracts import score_to_mastery_label


def build_virtual_root(manifest: dict) -> dict:
    return dict(manifest.get("virtual_root") or {})


def recompute_tree_summary(tree: dict, now_ts: int) -> dict:
    nodes = tree.get("nodes") if isinstance(tree.get("nodes"), list) else []
    mastered = 0
    weak = 0
    scores = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        mastery = node.get("mastery") if isinstance(node.get("mastery"), dict) else {}
        score = mastery.get("score")
        try:
            score_f = float(score)
        except Exception:
            score_f = 0.0
        scores.append(score_f)
        label = str(mastery.get("label") or score_to_mastery_label(score_f))
        if label == "mastered":
            mastered += 1
        if label == "weak":
            weak += 1
    learned = len(nodes)
    growth = sum(scores) / len(scores) if scores else 0.0
    return {
        "learned_node_count": learned,
        "mastered_node_count": mastered,
        "weak_node_count": weak,
        "tree_growth": round(growth, 4),
        "last_updated_at": int(now_ts),
    }


def get_learning_tree_features_payload(tree: dict, now_ts: int, stale_days: int = 14) -> dict:
    nodes = tree.get("nodes") if isinstance(tree.get("nodes"), list) else []
    stale_threshold = int(now_ts) - stale_days * 24 * 3600
    learned_topics = []
    weak_topics = []
    mastered_topics = []
    recently_grown = []
    stale_topics = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or "").strip()
        if not title:
            continue
        learned_topics.append(title)
        mastery = node.get("mastery") if isinstance(node.get("mastery"), dict) else {}
        label = str(mastery.get("label") or "")
        if label == "weak":
            weak_topics.append(title)
        if label == "mastered":
            mastered_topics.append(title)
        last_updated_at = int(node.get("last_updated_at") or 0)
        if last_updated_at >= int(now_ts) - 7 * 24 * 3600:
            recently_grown.append(title)
        if last_updated_at <= stale_threshold and label != "mastered":
            stale_topics.append(title)
    summary = tree.get("summary") if isinstance(tree.get("summary"), dict) else {}
    return {
        "tree_id": tree.get("tree_id"),
        "learned_topics": learned_topics,
        "weak_topics": weak_topics,
        "mastered_topics": mastered_topics,
        "recently_grown": recently_grown,
        "stale_topics": stale_topics,
        "tree_growth": summary.get("tree_growth", 0.0),
        "updated_at": tree.get("updated_at"),
    }

