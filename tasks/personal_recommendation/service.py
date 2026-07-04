"""Deterministic personal recommendation service implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.syllabus_repo import get_syllabus_by_id
from tasks.learning_profile.storage import load_json_file
from tasks.learning_profile_task import get_or_build_learning_profile
from tasks.personal_recommendation.candidate_generator import DEFAULT_DEPTH_STRATEGY, SUPPORTED_DEPTH_STRATEGIES, generate
from tasks.personal_recommendation.concept_decomposer import summarize_fallback_dependency
from tasks.personal_recommendation.evaluator import score
from tasks.personal_recommendation.graph_builder import build_recommendation_graph_tree
from tasks.personal_recommendation.perception import generate_state
from tasks.personal_recommendation.pruning import hard_prune, soft_prune_by_dominance
from tasks.personal_recommendation.rag_overlay import build_rag_overlay, score_candidate_with_overlay
from tasks.personal_recommendation.sample_data import learning_tree as sample_learning_tree
from tasks.personal_recommendation.selector_ib_grpo import ib_grpo_select
from tasks.personal_recommendation.snapshot import (
    RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
    RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED,
    save_recommendation_snapshot,
)
from tasks.personal_recommendation.syllabus_adapter import syllabus_json_to_learning_tree


RECOMMENDATION_SCHEMA_VERSION = "personal_recommendation.v2"
NEXT_ACTION_CONFIRM_PATH = "confirm_path"
NEXT_ACTION_GENERATE_RESOURCES = "generate_resources"
NEXT_ACTION_ASK_GOAL_CLARIFICATION = "ask_goal_clarification"
NODE_SOURCE_SAMPLE_FALLBACK = "sample_fallback"
DECOMPOSER_MODE_AUTO = "auto"
DECOMPOSER_MODE_AGENT = "agent"
DECOMPOSER_MODE_DISABLED = "disabled"
DEFAULT_RECOMMENDATION_CANDIDATE_LIMIT = 5
MAX_KNOWLEDGE_EXPANSION_PER_CHAPTER = 2
MAX_KNOWLEDGE_EXPANSION_TOTAL = 4
_UNKNOWN_WEEK_INDEX = 10**9


def _json_safe(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _sample_learning_tree_with_source(reason: str = "") -> Dict[str, Any]:
    tree = _json_safe(sample_learning_tree)
    for node in tree.values():
        if isinstance(node, dict):
            node["node_source"] = NODE_SOURCE_SAMPLE_FALLBACK
            if reason:
                node["fallback_reason"] = reason
    return tree


def _path_edges(path: List[Any], learning_tree: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    edges = []
    for idx in range(len(path) - 1):
        source = str(path[idx])
        target = str(path[idx + 1])
        edge = {
            "edge_id": f"{source}->{target}",
            "source": source,
            "target": target,
        }
        if isinstance(learning_tree, dict):
            target_node = learning_tree.get(target, {})
            edge_sources = target_node.get("edge_sources") if isinstance(target_node.get("edge_sources"), dict) else {}
            edge_confidence = target_node.get("edge_confidence") if isinstance(target_node.get("edge_confidence"), dict) else {}
            edge["source_type"] = edge_sources.get(source, "syllabus")
            edge["confidence"] = edge_confidence.get(source, 1.0)
        edges.append(edge)
    return edges


def _has_nonempty_path(item: Any) -> bool:
    return isinstance(item, dict) and bool(item.get("path"))


def _node_outcomes_known(node: Dict[str, Any], state: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(state, dict):
        return False
    knowledge = state.get("knowledge") if isinstance(state.get("knowledge"), dict) else {}
    outcomes = node.get("outcomes") if isinstance(node, dict) else []
    if not outcomes:
        return False
    return all(float(knowledge.get(outcome) or 0.0) > 0 for outcome in outcomes)


def _completed_nodes(state: Optional[Dict[str, Any]]) -> set[str]:
    if not isinstance(state, dict):
        return set()
    study_state = state.get("study_graph_state") if isinstance(state.get("study_graph_state"), dict) else {}
    return {str(item) for item in study_state.get("completed_node_ids") or [] if item not in (None, "")}


def _context_prefix_for_path(path: List[str], learning_tree: Optional[Dict[str, Any]], state: Optional[Dict[str, Any]]) -> List[str]:
    if not path or not isinstance(learning_tree, dict):
        return []
    path_set = set(path)
    completed = _completed_nodes(state)
    prefix: List[str] = []
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            return
        visiting.add(node_id)
        node = learning_tree.get(node_id, {})
        for prerequisite in node.get("prerequisites") or []:
            prerequisite_id = str(prerequisite)
            if prerequisite_id in path_set:
                continue
            prerequisite_node = learning_tree.get(prerequisite_id, {})
            if prerequisite_id in completed or _node_outcomes_known(prerequisite_node, state):
                visit(prerequisite_id)
                if prerequisite_id not in prefix:
                    prefix.append(prerequisite_id)
        visiting.discard(node_id)

    visit(path[0])
    return prefix


def _actionable_path(path: List[str], learning_tree: Optional[Dict[str, Any]], state: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(learning_tree, dict):
        return list(path)
    completed = _completed_nodes(state)
    actionable = []
    for node_id in path:
        node = learning_tree.get(str(node_id), {})
        if str(node_id) in completed:
            continue
        if _node_outcomes_known(node, state):
            continue
        actionable.append(str(node_id))
    return actionable or list(path)


def _path_node_details(path: List[str], learning_tree: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not path or not isinstance(learning_tree, dict):
        return []
    details = []
    for order_index, node_id in enumerate(path):
        normalized_id = str(node_id)
        node = learning_tree.get(normalized_id, {})
        node = node if isinstance(node, dict) else {}
        item = {
            "id": normalized_id,
            "node_id": normalized_id,
            "title": node.get("title") or normalized_id,
            "order_index": order_index,
            "learning_time_est": node.get("learning_time_est", 1),
            "difficulty": node.get("difficulty", 1),
            "outcomes": list(node.get("outcomes") or []),
            "node_source": node.get("node_source"),
            "decomposition_method": node.get("decomposition_method"),
            "fallback_tag": node.get("fallback_tag"),
            "reliability": node.get("reliability"),
            "confidence": node.get("confidence"),
            "source_period": node.get("source_period"),
            "profile_state": node.get("profile_state"),
            "study_graph_state": node.get("study_graph_state"),
            "prerequisites": [str(item) for item in node.get("prerequisites") or []],
        }
        item.update(_node_display_metadata(normalized_id, node))
        details.append(item)
    return details


def _node_display_metadata(node_id: str, node: Dict[str, Any]) -> Dict[str, Any]:
    source_period = node.get("source_period") if isinstance(node.get("source_period"), dict) else {}
    week_index = source_period.get("week_index") or node.get("week_index")
    title = str(node.get("title") or node_id)
    if _is_chapter_anchor(node):
        display_type = "chapter"
        display_group = "章节骨干"
        display_label = f"第{week_index}章" if week_index not in (None, "") else "章节"
    elif _is_chapter_concept(node):
        display_type = "knowledge"
        display_group = "知识点发散"
        display_label = "知识点"
    else:
        display_type = "resource"
        display_group = "关联节点"
        display_label = "节点"
    week_label = f"第{week_index}周" if week_index not in (None, "") else ""
    return {
        "display_type": display_type,
        "display_group": display_group,
        "display_label": display_label,
        "week_index": str(week_index) if week_index not in (None, "") else "",
        "week_label": week_label,
        "display_title": f"{display_label} · {title}" if display_label else title,
    }


def _build_recommendation_graph(learning_tree: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    nodes = []
    edges = []
    for node_id, raw_node in learning_tree.items():
        node = raw_node if isinstance(raw_node, dict) else {}
        normalized_id = str(node_id)
        graph_node = {
            "id": normalized_id,
            "title": node.get("title") or normalized_id,
            "difficulty": node.get("difficulty", 1),
            "learning_time_est": node.get("learning_time_est", 1),
            "outcomes": list(node.get("outcomes") or []),
            "prerequisites": [str(item) for item in node.get("prerequisites") or []],
            "node_source": node.get("node_source"),
            "decomposition_method": node.get("decomposition_method"),
            "fallback_tag": node.get("fallback_tag"),
            "reliability": node.get("reliability"),
            "confidence": node.get("confidence"),
            "source_period": node.get("source_period"),
            "profile_state": node.get("profile_state"),
            "study_graph_state": node.get("study_graph_state"),
        }
        graph_node.update(_node_display_metadata(normalized_id, node))
        nodes.append(graph_node)
        for prerequisite in node.get("prerequisites") or []:
            source = str(prerequisite)
            target = normalized_id
            edge_sources = node.get("edge_sources") if isinstance(node.get("edge_sources"), dict) else {}
            edge_confidence = node.get("edge_confidence") if isinstance(node.get("edge_confidence"), dict) else {}
            edges.append({
                "edge_id": f"{source}->{target}",
                "source": source,
                "target": target,
                "type": "prerequisite" if edge_sources.get(source, "syllabus") != "rag" else "rag_evidence",
                "source_type": edge_sources.get(source, "syllabus"),
                "confidence": edge_confidence.get(source, 1.0),
            })
    return {"nodes": nodes, "edges": edges}


def _graph_diagnostics(
    *,
    learning_tree: Dict[str, Any],
    recommendation_graph_tree: Dict[str, Any],
    graph: Dict[str, Any],
    rag_overlay: Dict[str, Any],
    goals: Optional[List[str]],
    chosen_goals: List[str],
    starts: List[str],
    candidates: List[Dict[str, Any]],
    response_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    def summarize_tree(tree: Dict[str, Any]) -> Dict[str, Any]:
        node_source_counts: Dict[str, int] = {}
        decomposition_method_counts: Dict[str, int] = {}
        fallback_tag_counts: Dict[str, int] = {}
        source_period_counts: Dict[str, int] = {}
        agent_nodes = []
        concept_nodes = []
        sample_nodes = []
        for node_id, raw_node in (tree or {}).items():
            node = raw_node if isinstance(raw_node, dict) else {}
            node_source = str(node.get("node_source") or "")
            method = str(node.get("decomposition_method") or "")
            fallback_tag = str(node.get("fallback_tag") or "")
            node_source_counts[node_source or "<empty>"] = node_source_counts.get(node_source or "<empty>", 0) + 1
            decomposition_method_counts[method or "<empty>"] = decomposition_method_counts.get(method or "<empty>", 0) + 1
            if fallback_tag:
                fallback_tag_counts[fallback_tag] = fallback_tag_counts.get(fallback_tag, 0) + 1
            source_period = node.get("source_period") if isinstance(node.get("source_period"), dict) else {}
            week_index = str(source_period.get("week_index") or node.get("week_index") or "")
            if week_index:
                source_period_counts[week_index] = source_period_counts.get(week_index, 0) + 1
            item = {
                "id": str(node_id),
                "title": node.get("title") or str(node_id),
                "node_source": node_source,
                "decomposition_method": method,
                "fallback_tag": fallback_tag,
                "prerequisite_count": len(node.get("prerequisites") or []),
            }
            if method == "agent":
                agent_nodes.append(item)
            if "concept" in node_source or method in {"agent", "rule_fallback"}:
                concept_nodes.append(item)
            if node_source == NODE_SOURCE_SAMPLE_FALLBACK:
                sample_nodes.append(item)
        return {
            "node_count": len(tree or {}),
            "edge_count": sum(len((node if isinstance(node, dict) else {}).get("prerequisites") or []) for node in (tree or {}).values()),
            "node_source_counts": node_source_counts,
            "decomposition_method_counts": decomposition_method_counts,
            "fallback_tag_counts": fallback_tag_counts,
            "source_period_counts": source_period_counts,
            "agent_node_count": len(agent_nodes),
            "concept_node_count": len(concept_nodes),
            "sample_fallback_node_count": len(sample_nodes),
            "agent_nodes_preview": agent_nodes[:12],
            "concept_nodes_preview": concept_nodes[:12],
            "sample_nodes_preview": sample_nodes[:8],
        }

    graph_nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    graph_edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    return {
        "schema_version": "personal_recommendation.graph_diagnostics.v1",
        "input_goals": list(goals or []),
        "chosen_goals": list(chosen_goals or []),
        "start_node_count": len(starts or []),
        "starts_preview": [str(item) for item in (starts or [])[:12]],
        "raw_candidate_count": len(candidates or []),
        "response_candidate_count": len(response_candidates or []),
        "best_candidate_paths_preview": [
            {
                "path": item.get("path") or [],
                "title_path": item.get("title_path") or [],
                "rank": item.get("rank"),
            }
            for item in (response_candidates or [])[:5]
            if isinstance(item, dict)
        ],
        "learning_tree": summarize_tree(learning_tree),
        "recommendation_graph_tree": summarize_tree(recommendation_graph_tree),
        "output_graph": {
            "node_count": len(graph_nodes),
            "edge_count": len(graph_edges),
            "agent_node_count": sum(1 for node in graph_nodes if isinstance(node, dict) and node.get("decomposition_method") == "agent"),
            "concept_node_count": sum(
                1
                for node in graph_nodes
                if isinstance(node, dict)
                and ("concept" in str(node.get("node_source") or "") or node.get("decomposition_method") in {"agent", "rule_fallback"})
            ),
            "nodes_preview": [
                {
                    "id": node.get("id"),
                    "title": node.get("title"),
                    "node_source": node.get("node_source"),
                    "decomposition_method": node.get("decomposition_method"),
                    "fallback_tag": node.get("fallback_tag"),
                }
                for node in graph_nodes[:12]
                if isinstance(node, dict)
            ],
        },
        "rag_overlay": {
            "enabled": bool((rag_overlay or {}).get("enabled")),
            "matched_node_count": len((rag_overlay or {}).get("matched_nodes") or []),
            "temporary_edge_count": len((rag_overlay or {}).get("temporary_edges") or []),
            "matched_nodes_preview": [
                {
                    "node_id": item.get("node_id"),
                    "title": item.get("title"),
                    "relevance": item.get("relevance"),
                }
                for item in ((rag_overlay or {}).get("matched_nodes") or [])[:8]
                if isinstance(item, dict)
            ],
        },
    }


def _apply_rag_overlay_to_graph(graph: Dict[str, Any], rag_overlay: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(rag_overlay, dict) or not rag_overlay.get("enabled"):
        return graph
    node_relevance = rag_overlay.get("node_relevance") if isinstance(rag_overlay.get("node_relevance"), dict) else {}
    matched_by_node = {
        item.get("node_id"): item
        for item in rag_overlay.get("matched_nodes") or []
        if isinstance(item, dict) and item.get("node_id")
    }
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        if node_id in node_relevance:
            node["rag_relevance"] = node_relevance[node_id]
            node["rag_matched"] = True
            node["rag_evidence"] = matched_by_node.get(node_id, {})
        else:
            node["rag_matched"] = False
    for edge in rag_overlay.get("temporary_edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source and target:
            graph.setdefault("edges", []).append(
                {
                    "edge_id": f"rag:{source}->{target}",
                    "source": source,
                    "target": target,
                    "type": "rag_evidence",
                    "reason": edge.get("reason") or "",
                    "persistent": False,
                }
            )
    return graph


def _serialize_path_item(
    candidate: Dict[str, Any],
    candidate_score: Optional[Dict[str, Any]] = None,
    rank: Optional[int] = None,
    selected: bool = False,
    rag_overlay: Optional[Dict[str, Any]] = None,
    learning_tree: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = _json_safe(dict(candidate))
    path = [str(node_id) for node_id in item.get("path") or []]
    context_path = _context_prefix_for_path(path, learning_tree, state)
    full_path = context_path + [node_id for node_id in path if node_id not in context_path]
    item["path"] = path
    item["context_path"] = context_path
    item["full_path"] = full_path
    item["actionable_path"] = _actionable_path(path, learning_tree, state)
    item["path_nodes"] = _path_node_details(path, learning_tree)
    item["context_path_nodes"] = _path_node_details(context_path, learning_tree)
    item["full_path_nodes"] = _path_node_details(full_path, learning_tree)
    item["actionable_path_nodes"] = _path_node_details(item["actionable_path"], learning_tree)
    item["path_edges"] = _path_edges(path, learning_tree)
    item["full_path_edges"] = _path_edges(full_path, learning_tree)
    item["fallback_dependency"] = summarize_fallback_dependency(path, learning_tree or {})
    item["path_depth"] = int(item.get("path_depth") or len(path))
    item["full_path_depth"] = len(full_path)
    item["selected"] = selected
    if rank is not None:
        item["rank"] = rank
    if candidate_score is not None:
        item["scores"] = _json_safe(candidate_score)
    if rag_overlay is not None:
        item["rag_relevance"] = score_candidate_with_overlay(item, rag_overlay)
        item["rag_matched_nodes"] = [
            node_id
            for node_id in path
            if (rag_overlay.get("node_relevance") or {}).get(str(node_id))
        ]
    return item


def _normalize_depth_strategy(value: Any) -> str:
    normalized = str(value or DEFAULT_DEPTH_STRATEGY).strip()
    return normalized if normalized in SUPPORTED_DEPTH_STRATEGIES else DEFAULT_DEPTH_STRATEGY


def _node_week_index(node: Dict[str, Any]) -> int:
    if not isinstance(node, dict):
        return _UNKNOWN_WEEK_INDEX
    source_period = node.get("source_period") if isinstance(node.get("source_period"), dict) else {}
    raw_value = source_period.get("week_index") or node.get("week_index")
    text = str(raw_value or "").strip()
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
        elif digits:
            break
    if not digits:
        return _UNKNOWN_WEEK_INDEX
    try:
        return int(digits)
    except Exception:
        return _UNKNOWN_WEEK_INDEX


def _path_week_index(path: List[Any], learning_tree: Optional[Dict[str, Any]]) -> int:
    if not path or not isinstance(learning_tree, dict):
        return _UNKNOWN_WEEK_INDEX
    weeks = [
        _node_week_index(learning_tree.get(str(node_id), {}))
        for node_id in path
    ]
    weeks = [week for week in weeks if week < _UNKNOWN_WEEK_INDEX]
    return min(weeks) if weeks else _UNKNOWN_WEEK_INDEX


def _path_week_sequence(path: List[Any], learning_tree: Optional[Dict[str, Any]]) -> List[int]:
    if not path or not isinstance(learning_tree, dict):
        return []
    weeks = []
    for node_id in path:
        week = _node_week_index(learning_tree.get(str(node_id), {}))
        if week < _UNKNOWN_WEEK_INDEX:
            weeks.append(week)
    return weeks


def _path_syllabus_linearity_key(path: List[Any], learning_tree: Dict[str, Any]) -> tuple:
    normalized_path = [str(node_id) for node_id in path or []]
    if len(normalized_path) <= 1:
        return (1, 0, 0, 0)

    non_syllabus_edges = 0
    backward_edges = 0
    large_week_jumps = 0
    unknown_week_edges = 0
    weeks = _path_week_sequence(normalized_path, learning_tree)
    week_by_node = {
        node_id: _node_week_index(learning_tree.get(node_id, {}))
        for node_id in normalized_path
    }
    for source, target in zip(normalized_path, normalized_path[1:]):
        target_node = learning_tree.get(target, {}) if isinstance(learning_tree, dict) else {}
        edge_sources = target_node.get("edge_sources") if isinstance(target_node.get("edge_sources"), dict) else {}
        edge_source = str(edge_sources.get(source, "syllabus"))
        if edge_source not in {"syllabus", "syllabus_period", "syllabus_period_concept"}:
            non_syllabus_edges += 1
        source_week = week_by_node.get(source, _UNKNOWN_WEEK_INDEX)
        target_week = week_by_node.get(target, _UNKNOWN_WEEK_INDEX)
        if source_week >= _UNKNOWN_WEEK_INDEX or target_week >= _UNKNOWN_WEEK_INDEX:
            unknown_week_edges += 1
            continue
        if target_week < source_week:
            backward_edges += 1
        if target_week - source_week > 1:
            large_week_jumps += target_week - source_week - 1

    return (
        non_syllabus_edges,
        backward_edges,
        large_week_jumps,
        unknown_week_edges,
        -len(set(weeks)),
    )


def _has_foundation_gap(learning_tree: Dict[str, Any], state: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(learning_tree, dict):
        return False
    if not isinstance(state, dict):
        return True
    study_state = state.get("study_graph_state") if isinstance(state.get("study_graph_state"), dict) else {}
    if study_state.get("weak_node_ids") or study_state.get("current_node_id"):
        return True

    completed = _completed_nodes(state)
    completed_weeks = [
        _node_week_index(learning_tree.get(node_id, {}))
        for node_id in completed
        if node_id in learning_tree
    ]
    completed_weeks = [week for week in completed_weeks if week < _UNKNOWN_WEEK_INDEX]
    if not completed_weeks:
        return True

    earliest_available = _UNKNOWN_WEEK_INDEX
    blocked = {str(item) for item in state.get("constraints", {}).get("blocked_nodes") or []}
    for node_id, raw_node in learning_tree.items():
        normalized_id = str(node_id)
        node = raw_node if isinstance(raw_node, dict) else {}
        if normalized_id in blocked or normalized_id in completed or _node_outcomes_known(node, state):
            continue
        earliest_available = min(earliest_available, _node_week_index(node))
    return earliest_available < max(completed_weeks)


def _gap_priority(path: List[Any], learning_tree: Dict[str, Any], state: Optional[Dict[str, Any]]) -> int:
    if not isinstance(state, dict):
        return 2
    study_state = state.get("study_graph_state") if isinstance(state.get("study_graph_state"), dict) else {}
    path_set = {str(node_id) for node_id in path or []}
    weak = {str(item) for item in study_state.get("weak_node_ids") or [] if item not in (None, "")}
    if weak.intersection(path_set):
        return 0
    current = str(study_state.get("current_node_id") or "")
    if current and current in path_set:
        return 1
    return 2


def _candidate_foundation_sort_key(candidate: Dict[str, Any], learning_tree: Dict[str, Any], state: Optional[Dict[str, Any]]) -> tuple:
    path = [str(node_id) for node_id in candidate.get("actionable_path") or candidate.get("path") or []]
    return (
        _gap_priority(path, learning_tree, state),
        _path_week_index(path, learning_tree),
        _path_syllabus_linearity_key(path, learning_tree),
        len(path),
    )


def _candidate_syllabus_sort_key(candidate: Dict[str, Any], learning_tree: Dict[str, Any]) -> tuple:
    path = [str(node_id) for node_id in candidate.get("actionable_path") or candidate.get("path") or []]
    return (
        _path_syllabus_linearity_key(path, learning_tree),
        _path_week_index(path, learning_tree),
        len(path),
    )


def _rank_candidate_pairs(
    candidates: List[Dict[str, Any]],
    raw_scores: List[Dict[str, Any]],
    learning_tree: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    *,
    limit: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    pairs = list(zip(candidates, raw_scores))
    if _has_foundation_gap(learning_tree, state):
        pairs.sort(
            key=lambda pair: (
                _candidate_foundation_sort_key(pair[0], learning_tree, state),
                -float((pair[1] or {}).get("R") or 0.0),
                float((pair[1] or {}).get("D") or 0.0),
            )
        )
    else:
        pairs.sort(
            key=lambda pair: (
                _candidate_syllabus_sort_key(pair[0], learning_tree),
                -float((pair[1] or {}).get("R") or 0.0),
                float((pair[1] or {}).get("D") or 0.0),
            )
        )
    pairs = pairs[:max(1, int(limit))]
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def _candidate_has_actionable_node(candidate: Dict[str, Any], learning_tree: Dict[str, Any], state: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(candidate, dict):
        return False
    path = [str(node_id) for node_id in candidate.get("path") or []]
    if not path:
        return False
    completed = _completed_nodes(state)
    for node_id in path:
        node = learning_tree.get(node_id, {}) if isinstance(learning_tree, dict) else {}
        if node_id in completed:
            continue
        if _node_outcomes_known(node, state):
            continue
        return True
    return False


def _is_chapter_anchor(node: Dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    node_source = str(node.get("node_source") or "")
    method = str(node.get("decomposition_method") or "")
    if method == "period_anchor":
        return True
    return node_source in {"syllabus_period", "syllabus_period_fallback"}


def _is_chapter_concept(node: Dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    node_source = str(node.get("node_source") or "")
    method = str(node.get("decomposition_method") or "")
    return bool(node.get("source_period")) or "concept" in node_source or method in {"agent", "rule_fallback"}


def _anchor_for_node(node_id: str, learning_tree: Dict[str, Any]) -> str:
    node = learning_tree.get(str(node_id), {}) if isinstance(learning_tree, dict) else {}
    if _is_chapter_anchor(node):
        return str(node_id)
    source_period = node.get("source_period") if isinstance(node.get("source_period"), dict) else {}
    source_anchor = str(source_period.get("node_id") or "")
    if source_anchor and source_anchor in learning_tree:
        return source_anchor
    for prerequisite in node.get("prerequisites") or []:
        prerequisite_id = str(prerequisite)
        prerequisite_node = learning_tree.get(prerequisite_id, {})
        if _is_chapter_anchor(prerequisite_node):
            return prerequisite_id
    return ""


def _chapter_anchor_ids(learning_tree: Dict[str, Any]) -> List[str]:
    anchors = [
        str(node_id)
        for node_id, node in (learning_tree or {}).items()
        if _is_chapter_anchor(node if isinstance(node, dict) else {})
    ]
    anchors.sort(key=lambda node_id: (_node_week_index(learning_tree.get(node_id, {})), str(learning_tree.get(node_id, {}).get("title") or node_id)))
    return anchors


def _goal_match_score(node_id: str, learning_tree: Dict[str, Any], goals: List[str]) -> int:
    if not goals:
        return 1
    node = learning_tree.get(str(node_id), {}) if isinstance(learning_tree, dict) else {}
    text = " ".join(
        [str(node.get("title") or node_id)]
        + [str(item) for item in node.get("outcomes") or []]
    ).lower()
    for goal in goals:
        goal_text = str(goal or "").lower()
        if goal_text and (goal_text in text or text in goal_text):
            return 0
    return 1


def _study_state_priority(node_id: str, learning_tree: Dict[str, Any]) -> int:
    node = learning_tree.get(str(node_id), {}) if isinstance(learning_tree, dict) else {}
    state = str(node.get("study_graph_state") or "")
    if state == "current":
        return 0
    if state == "weak":
        return 1
    if state == "unknown":
        return 2
    return 3


def _concept_expansion_sort_key(node_id: str, learning_tree: Dict[str, Any], goals: List[str], preferred: set[str]) -> tuple:
    node = learning_tree.get(str(node_id), {}) if isinstance(learning_tree, dict) else {}
    try:
        reliability = float(node.get("reliability", node.get("confidence", 1.0)) or 1.0)
    except Exception:
        reliability = 1.0
    return (
        0 if node_id in preferred else 1,
        _study_state_priority(node_id, learning_tree),
        _goal_match_score(node_id, learning_tree, goals),
        -reliability,
        str(node.get("title") or node_id),
    )


def _two_stage_candidate(
    candidate: Dict[str, Any],
    learning_tree: Dict[str, Any],
    goals: List[str],
    *,
    L_max: int,
) -> Dict[str, Any]:
    path = [str(node_id) for node_id in (candidate or {}).get("path") or []]
    anchors_all = _chapter_anchor_ids(learning_tree)
    if not path or not anchors_all:
        return candidate

    original_anchor_order: List[str] = []
    concepts_by_anchor: Dict[str, List[str]] = {}
    for node_id in path:
        anchor_id = _anchor_for_node(node_id, learning_tree)
        if anchor_id and anchor_id not in original_anchor_order:
            original_anchor_order.append(anchor_id)
        node = learning_tree.get(node_id, {})
        if anchor_id and node_id != anchor_id and _is_chapter_concept(node):
            concepts_by_anchor.setdefault(anchor_id, [])
            if node_id not in concepts_by_anchor[anchor_id]:
                concepts_by_anchor[anchor_id].append(node_id)

    if not original_anchor_order:
        return candidate

    week_by_anchor = {
        anchor_id: _node_week_index(learning_tree.get(anchor_id, {}))
        for anchor_id in anchors_all
    }
    selected_weeks = [
        week_by_anchor.get(anchor_id, _UNKNOWN_WEEK_INDEX)
        for anchor_id in original_anchor_order
        if week_by_anchor.get(anchor_id, _UNKNOWN_WEEK_INDEX) < _UNKNOWN_WEEK_INDEX
    ]
    if selected_weeks:
        min_week = min(selected_weeks)
        max_week = max(selected_weeks)
        backbone = [
            anchor_id
            for anchor_id in anchors_all
            if min_week <= week_by_anchor.get(anchor_id, _UNKNOWN_WEEK_INDEX) <= max_week
        ]
    else:
        backbone = list(original_anchor_order)

    if not backbone:
        return candidate

    max_len = max(1, int(L_max or len(path)))
    two_stage_path: List[str] = []
    knowledge_expansion: List[Dict[str, Any]] = []
    total_expanded = 0
    for anchor_id in backbone:
        if anchor_id not in two_stage_path and len(two_stage_path) < max_len:
            two_stage_path.append(anchor_id)
        preferred_concepts = set(concepts_by_anchor.get(anchor_id) or [])
        concepts = [
            str(node_id)
            for node_id, node in (learning_tree or {}).items()
            if _anchor_for_node(str(node_id), learning_tree) == anchor_id and str(node_id) != anchor_id and _is_chapter_concept(node if isinstance(node, dict) else {})
        ]
        for concept_id in preferred_concepts:
            if concept_id not in concepts:
                concepts.append(concept_id)
        concepts.sort(key=lambda node_id: _concept_expansion_sort_key(node_id, learning_tree, goals, preferred_concepts))
        expansion_nodes = []
        for concept_id in concepts:
            if len(expansion_nodes) >= MAX_KNOWLEDGE_EXPANSION_PER_CHAPTER:
                break
            if total_expanded >= MAX_KNOWLEDGE_EXPANSION_TOTAL:
                break
            if concept_id not in two_stage_path and len(two_stage_path) < max_len:
                two_stage_path.append(concept_id)
                expansion_nodes.append(concept_id)
                total_expanded += 1
        knowledge_expansion.append({
            "chapter_node_id": anchor_id,
            "chapter_title": learning_tree.get(anchor_id, {}).get("title") or anchor_id,
            "week_index": _node_week_index(learning_tree.get(anchor_id, {})),
            "knowledge_node_ids": expansion_nodes,
            "knowledge_count": len(expansion_nodes),
        })

    if not two_stage_path:
        return candidate

    normalized = dict(candidate)
    normalized["path"] = two_stage_path
    normalized["path_depth"] = len(two_stage_path)
    normalized["chapter_backbone"] = [
        {
            "node_id": anchor_id,
            "title": learning_tree.get(anchor_id, {}).get("title") or anchor_id,
            "week_index": _node_week_index(learning_tree.get(anchor_id, {})),
        }
        for anchor_id in backbone
        if anchor_id in two_stage_path
    ]
    normalized["knowledge_expansion"] = knowledge_expansion
    normalized["route_structure"] = "chapter_backbone_then_knowledge_expansion"
    normalized["cost"] = sum(float((learning_tree.get(node_id, {}) or {}).get("learning_time_est") or 1.0) for node_id in two_stage_path)
    skills = set()
    for node_id in two_stage_path:
        skills.update(str(item) for item in (learning_tree.get(node_id, {}) or {}).get("outcomes") or [])
    normalized["skills"] = skills
    return normalized


def _apply_two_stage_routes(
    candidates: List[Dict[str, Any]],
    learning_tree: Dict[str, Any],
    goals: List[str],
    *,
    L_max: int,
) -> List[Dict[str, Any]]:
    if not candidates or not _chapter_anchor_ids(learning_tree):
        return candidates
    normalized = [
        _two_stage_candidate(candidate, learning_tree, goals, L_max=L_max)
        for candidate in candidates
    ]
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in normalized:
        path_key = tuple(str(node_id) for node_id in candidate.get("path") or [])
        if not path_key or path_key in seen:
            continue
        seen.add(path_key)
        deduped.append(candidate)
    return deduped


def _build_planning_hints(result: Dict[str, Any]) -> Dict[str, Any]:
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
    best_path = result.get("best_path") if isinstance(result.get("best_path"), dict) else None
    if not candidates and not _has_nonempty_path(best_path):
        return {
            "path_depth": 0,
            "has_rag_edges": False,
            "has_low_confidence_edges": False,
            "suggested_next_action": NEXT_ACTION_ASK_GOAL_CLARIFICATION,
        }
    path_edges = best_path.get("path_edges") if _has_nonempty_path(best_path) else []
    has_rag_edges = any((edge or {}).get("source_type") == "rag" or (edge or {}).get("type") == "rag_evidence" for edge in path_edges or [])
    has_low_confidence_edges = False
    for edge in path_edges or []:
        try:
            if float((edge or {}).get("confidence", 1.0)) < 0.8:
                has_low_confidence_edges = True
                break
        except Exception:
            continue
    path = best_path.get("path") if _has_nonempty_path(best_path) else []
    return {
        "path_depth": len(path or []),
        "has_rag_edges": bool(has_rag_edges),
        "has_low_confidence_edges": bool(has_low_confidence_edges),
        "suggested_next_action": NEXT_ACTION_CONFIRM_PATH if (has_rag_edges or has_low_confidence_edges) else NEXT_ACTION_GENERATE_RESOURCES,
    }


def _fallback_candidate_paths(
    learning_tree: Dict[str, Any],
    state: Dict[str, Any],
    goals: List[str],
    *,
    L_max: int,
    T_max: int,
    K: int,
) -> List[Dict[str, Any]]:
    if not learning_tree:
        return []

    blocked = {str(item) for item in state.get("constraints", {}).get("blocked_nodes") or []}
    completed = _completed_nodes(state)
    goal_set = {str(goal) for goal in goals or [] if goal}
    children_by_parent: Dict[str, List[str]] = {}
    for node_id, raw_node in learning_tree.items():
        node = raw_node if isinstance(raw_node, dict) else {}
        for prerequisite in node.get("prerequisites") or []:
            children_by_parent.setdefault(str(prerequisite), []).append(str(node_id))

    def is_available(node_id: str) -> bool:
        node = learning_tree.get(node_id, {})
        return node_id not in blocked and node_id not in completed and not _node_outcomes_known(node, state)

    def node_cost(node_id: str) -> float:
        try:
            return float((learning_tree.get(node_id) or {}).get("learning_time_est") or 1.0)
        except Exception:
            return 1.0

    def node_goal_score(node_id: str) -> int:
        outcomes = {str(item) for item in (learning_tree.get(node_id) or {}).get("outcomes") or []}
        title = str((learning_tree.get(node_id) or {}).get("title") or "")
        if goal_set and outcomes.intersection(goal_set):
            return 0
        if goal_set and any(goal in title or title in goal for goal in goal_set if title):
            return 1
        return 2

    def node_sort_key(node_id: str) -> tuple:
        node = learning_tree.get(node_id) or {}
        try:
            difficulty = float(node.get("difficulty") or 1.0)
        except Exception:
            difficulty = 1.0
        return (
            _node_week_index(node),
            node_goal_score(node_id),
            len(node.get("prerequisites") or []),
            difficulty,
            node_cost(node_id),
            str(node.get("title") or node_id),
        )

    starts = [str(node_id) for node_id in learning_tree if is_available(str(node_id))]
    if not starts:
        starts = [str(node_id) for node_id in learning_tree if str(node_id) not in blocked]
    starts.sort(key=node_sort_key)

    results: List[Dict[str, Any]] = []
    seen_paths: set[tuple[str, ...]] = set()
    for start in starts:
        path: List[str] = []
        seen_nodes: set[str] = set()
        cost = 0.0
        current = start
        while current and len(path) < max(1, int(L_max)):
            if current in seen_nodes or current in blocked:
                break
            next_cost = node_cost(current)
            if path and cost + next_cost > T_max:
                break
            path.append(current)
            seen_nodes.add(current)
            cost += next_cost
            children = [
                child for child in children_by_parent.get(current, [])
                if child not in seen_nodes and child not in blocked and child not in completed
            ]
            children.sort(key=node_sort_key)
            if not children:
                break
            if goal_set and any(str(outcome) in goal_set for outcome in (learning_tree.get(current) or {}).get("outcomes") or []):
                break
            current = children[0]
        path_key = tuple(path)
        if not path or path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        skills = set()
        for node_id in path:
            skills.update(str(item) for item in (learning_tree.get(node_id) or {}).get("outcomes") or [])
        results.append({
            "path": path,
            "cost": cost,
            "skills": skills,
            "path_depth": len(path),
        })
        if len(results) >= max(1, int(K)):
            break
    return results


def load_recommendation_learning_tree(
    syllabus_id: Optional[int] = None,
    *,
    concept_decomposer: Any = None,
    rag_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load the recommendation graph, preferring a real syllabus-derived tree."""
    if not syllabus_id:
        return _sample_learning_tree_with_source("missing_syllabus_id")

    try:
        syllabus = get_syllabus_by_id(int(syllabus_id))
        syllabus_path = getattr(syllabus, "syllabus_path", None) if syllabus else None
        if not syllabus_path:
            return _sample_learning_tree_with_source("missing_syllabus_path")
        syllabus_json = load_json_file(syllabus_path)
        mapped = syllabus_json_to_learning_tree(
            syllabus_json,
            concept_decomposer=concept_decomposer,
            rag_context=rag_context,
        )
        return mapped or _sample_learning_tree_with_source("empty_syllabus_mapping")
    except Exception:
        return _sample_learning_tree_with_source("syllabus_load_error")


def _normalize_decomposer_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"0", "false", "off", "no", "none", "disabled", "disable"}:
        return DECOMPOSER_MODE_DISABLED
    if text in {"1", "true", "on", "yes", "agent", "llm"}:
        return DECOMPOSER_MODE_AGENT
    return DECOMPOSER_MODE_AUTO


def _build_agent_concept_decomposer(
    *,
    syllabus_id: Optional[int],
    graph_name: Optional[str] = None,
    rag_top_k: Optional[int] = None,
):
    def decompose(payload: Dict[str, Any]) -> Dict[str, Any]:
        from tasks.personal_recommendation.agent_runtime import run_period_concept_decomposer_agent

        periods = payload.get("periods") if isinstance(payload.get("periods"), list) else []
        request = {
            "syllabus_id": syllabus_id,
            "periods": periods,
            "rag_context": payload.get("rag_context") if isinstance(payload.get("rag_context"), dict) else None,
        }
        if graph_name:
            request["graph_name"] = graph_name
        if rag_top_k:
            request["rag_top_k"] = rag_top_k
        return run_period_concept_decomposer_agent(request)

    return decompose


def _agent_decomposed_node_count(learning_tree: Dict[str, Any]) -> int:
    return sum(
        1
        for node in (learning_tree or {}).values()
        if isinstance(node, dict) and node.get("decomposition_method") == DECOMPOSER_MODE_AGENT
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            if item in (None, ""):
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    return [text] if text else []


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _normalize_knowledge_levels(profile: Dict[str, Any]) -> Dict[str, float]:
    knowledge = profile.get("knowledge_levels")
    if isinstance(knowledge, dict) and knowledge:
        return {
            str(key): _safe_float(value, 0.0)
            for key, value in knowledge.items()
        }

    mastery = profile.get("knowledge_mastery")
    if not isinstance(mastery, dict):
        return {}

    details = mastery.get("knowledge_point_details")
    if isinstance(details, dict) and details:
        normalized = {}
        for key, item in details.items():
            if not isinstance(item, dict):
                continue
            normalized[str(key)] = _safe_float(item.get("score"), 0.0)
        if normalized:
            return normalized

    by_point = mastery.get("by_knowledge_point")
    if isinstance(by_point, dict):
        return {
            str(key): _safe_float(value, 0.0)
            for key, value in by_point.items()
        }
    return {}


def _normalize_preferences(profile: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(profile.get("preferences") or {}) if isinstance(profile.get("preferences"), dict) else {}
    preferred_formats = normalized.get("preferred_formats")
    if not preferred_formats:
        resource_preference = _as_string_list(profile.get("resource_preference"))
        if resource_preference:
            normalized["preferred_formats"] = resource_preference
    if not normalized.get("learning_style") and profile.get("learning_style"):
        normalized["learning_style"] = profile.get("learning_style")
    return normalized


def _normalize_constraints(profile: Dict[str, Any]) -> Dict[str, Any]:
    return dict(profile.get("constraints") or {}) if isinstance(profile.get("constraints"), dict) else {}


def _normalize_learning_goals(profile: Dict[str, Any]) -> List[str]:
    goals = []
    goals.extend(_as_string_list(profile.get("learning_goals")))
    goals.extend(_as_string_list(profile.get("learning_goal")))
    goals.extend(_as_string_list(profile.get("concept_gaps")))
    goals.extend(_as_string_list(profile.get("bottleneck_topics")))
    return _dedupe_keep_order(goals)


def _normalize_recommendation_profile(
    profile: Optional[Dict[str, Any]],
    user_id: int,
    syllabus_id: Optional[int] = None,
) -> Dict[str, Any]:
    normalized = dict(profile) if isinstance(profile, dict) else {}
    normalized["user_id"] = int(normalized.get("user_id") or user_id)
    normalized["syllabus_id"] = int(normalized.get("syllabus_id") or syllabus_id) if (normalized.get("syllabus_id") or syllabus_id) else None
    normalized["knowledge_levels"] = _normalize_knowledge_levels(normalized)
    normalized["learning_goals"] = _normalize_learning_goals(normalized)
    normalized["preferences"] = _normalize_preferences(normalized)
    normalized["constraints"] = _normalize_constraints(normalized)
    return normalized


def _resolve_recommendation_goals(
    goals: Optional[List[str]],
    profile: Dict[str, Any],
    learning_tree: Dict[str, Any],
) -> List[str]:
    requested = _as_string_list(goals)
    if not requested:
        requested = _normalize_learning_goals(profile)
    if not requested:
        return []

    outcome_lookup: Dict[str, List[str]] = {}
    title_lookup: Dict[str, List[str]] = {}
    node_lookup: Dict[str, List[str]] = {}
    all_outcomes: List[str] = []

    for node_id, raw_node in learning_tree.items():
        node = raw_node if isinstance(raw_node, dict) else {}
        outcomes = _as_string_list(node.get("outcomes"))
        title = str(node.get("title") or "").strip().lower()
        node_key = str(node_id).strip().lower()
        if outcomes:
            node_lookup[node_key] = outcomes
        for outcome in outcomes:
            all_outcomes.append(outcome)
            outcome_lookup.setdefault(outcome.lower(), []).append(outcome)
        if title and outcomes:
            title_lookup[title] = outcomes

    resolved: List[str] = []
    for goal in requested:
        lowered = goal.lower()
        exact_matches = outcome_lookup.get(lowered)
        if exact_matches:
            resolved.extend(exact_matches)
            continue

        title_matches = title_lookup.get(lowered)
        if title_matches:
            resolved.extend(title_matches)
            continue

        node_matches = node_lookup.get(lowered)
        if node_matches:
            resolved.extend(node_matches)
            continue

        fuzzy_matches = []
        for outcome in all_outcomes:
            outcome_lower = outcome.lower()
            if outcome_lower in lowered or lowered in outcome_lower:
                fuzzy_matches.append(outcome)
        if len(set(fuzzy_matches)) == 1:
            resolved.extend(fuzzy_matches)

    resolved = _dedupe_keep_order(resolved)
    return resolved or requested


def build_recommendation_profile(user_id: int, syllabus_id: Optional[int] = None) -> Dict[str, Any]:
    """Fetch or build a profile, falling back to a minimal transient profile."""
    profile = get_or_build_learning_profile(
        int(user_id),
        int(syllabus_id) if syllabus_id else None,
        refresh_profile=False,
    )
    if profile is not None:
        return _normalize_recommendation_profile(profile, int(user_id), int(syllabus_id) if syllabus_id else None)
    return _normalize_recommendation_profile({
        "user_id": int(user_id),
        "syllabus_id": int(syllabus_id) if syllabus_id else None,
        "knowledge_levels": {},
        "learning_goals": [],
    }, int(user_id), int(syllabus_id) if syllabus_id else None)


def run_recommendation_route(
    user_id: int,
    syllabus_id: Optional[int] = None,
    goals: Optional[List[str]] = None,
    L_max: int = 6,
    T_max: int = 100,
    K: int = DEFAULT_RECOMMENDATION_CANDIDATE_LIMIT,
    beam_width: int = 6,
    rag_context: Optional[Dict[str, Any]] = None,
    study_graph_state: Optional[Dict[str, Any]] = None,
    depth_strategy: str = DEFAULT_DEPTH_STRATEGY,
    concept_decomposer: Any = None,
    decomposer_mode: str = DECOMPOSER_MODE_AUTO,
    graph_name: Optional[str] = None,
    rag_top_k: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the full recommendation pipeline and return API-ready data."""
    if not user_id:
        return {
            "success": False,
            "candidates": [],
            "selected": [],
            "error_message": "missing user_id",
            "error_code": "missing_fields",
        }

    normalized_decomposer_mode = _normalize_decomposer_mode(decomposer_mode)
    effective_decomposer = concept_decomposer
    if effective_decomposer is None and normalized_decomposer_mode != DECOMPOSER_MODE_DISABLED and rag_context is not None:
        effective_decomposer = _build_agent_concept_decomposer(
            syllabus_id=syllabus_id,
            graph_name=graph_name,
            rag_top_k=rag_top_k,
        )

    if effective_decomposer is not None or rag_context is not None:
        try:
            learning_tree = load_recommendation_learning_tree(
                syllabus_id,
                concept_decomposer=effective_decomposer,
                rag_context=rag_context,
            )
        except TypeError:
            if effective_decomposer is not None and concept_decomposer is not None:
                raise
            learning_tree = load_recommendation_learning_tree(syllabus_id)
    else:
        learning_tree = load_recommendation_learning_tree(syllabus_id)
    if normalized_decomposer_mode == DECOMPOSER_MODE_AGENT and effective_decomposer is not None and _agent_decomposed_node_count(learning_tree) == 0:
        return {
            "success": False,
            "schema_version": RECOMMENDATION_SCHEMA_VERSION,
            "graph": _build_recommendation_graph(learning_tree if isinstance(learning_tree, dict) else {}),
            "rag_overlay": {},
            "candidates": [],
            "selected": [],
            "best_path": None,
            "planning_hints": {
                "path_depth": 0,
                "has_rag_edges": False,
                "has_low_confidence_edges": False,
                "suggested_next_action": NEXT_ACTION_ASK_GOAL_CLARIFICATION,
            },
            "debug": {
                "graph_diagnostics": {
                    "schema_version": "personal_recommendation.graph_diagnostics.v1",
                    "learning_tree": {
                        "node_count": len(learning_tree or {}) if isinstance(learning_tree, dict) else 0,
                        "agent_node_count": 0,
                    },
                    "decomposer_mode": normalized_decomposer_mode,
                }
            },
            "error_message": "agent decomposer mode requires at least one agent-decomposed concept node",
            "error_code": "agent_decomposer_required",
        }
    profile = build_recommendation_profile(int(user_id), syllabus_id)
    rag_overlay = build_rag_overlay(rag_context, learning_tree)
    recommendation_graph_tree = build_recommendation_graph_tree(
        learning_tree,
        rag_overlay=rag_overlay,
        profile=profile,
        study_graph_state=study_graph_state if isinstance(study_graph_state, dict) else None,
    )
    chosen_goals = _resolve_recommendation_goals(goals, profile, recommendation_graph_tree)
    depth_strategy = _normalize_depth_strategy(depth_strategy)
    candidate_limit = max(1, int(K or DEFAULT_RECOMMENDATION_CANDIDATE_LIMIT))

    state, starts = generate_state(profile, recommendation_graph_tree, study_graph_state=study_graph_state)
    candidates = generate(
        starts,
        chosen_goals,
        recommendation_graph_tree,
        state,
        L_max=int(L_max),
        T_max=int(T_max),
        K=candidate_limit,
        beam_width=int(beam_width),
        depth_strategy=depth_strategy,
    )

    candidates = hard_prune(
        candidates,
        state,
        blocked_nodes=state.get("constraints", {}).get("blocked_nodes"),
    )
    candidates = [
        candidate
        for candidate in candidates
        if _candidate_has_actionable_node(candidate, recommendation_graph_tree, state)
    ]
    if not candidates:
        candidates = _fallback_candidate_paths(
            recommendation_graph_tree,
            state,
            chosen_goals,
            L_max=int(L_max),
            T_max=int(T_max),
            K=candidate_limit,
        )
    raw_scores = [score(candidate, state, recommendation_graph_tree) for candidate in candidates]

    candidates = soft_prune_by_dominance(candidates, raw_scores)
    candidates = [
        candidate
        for candidate in candidates
        if _candidate_has_actionable_node(candidate, recommendation_graph_tree, state)
    ]
    if not candidates:
        candidates = _fallback_candidate_paths(
            recommendation_graph_tree,
            state,
            chosen_goals,
            L_max=int(L_max),
            T_max=int(T_max),
            K=candidate_limit,
        )
    candidates = _apply_two_stage_routes(
        candidates,
        recommendation_graph_tree,
        chosen_goals,
        L_max=int(L_max),
    )
    raw_scores = [score(candidate, state, recommendation_graph_tree) for candidate in candidates]
    candidates, raw_scores = _rank_candidate_pairs(
        candidates,
        raw_scores,
        recommendation_graph_tree,
        state,
        limit=candidate_limit,
    )

    response_candidates = []
    for candidate, candidate_score in zip(candidates, raw_scores):
        response_candidates.append(
            _serialize_path_item(
                candidate,
                candidate_score=candidate_score,
                rank=len(response_candidates) + 1,
                rag_overlay=rag_overlay,
                learning_tree=recommendation_graph_tree,
                state=state,
            )
        )

    if _has_foundation_gap(recommendation_graph_tree, state):
        response_candidates.sort(
            key=lambda item: (
                _candidate_foundation_sort_key(item, recommendation_graph_tree, state),
                -float(item.get("rag_relevance") or 0.0),
                int(item.get("rank") or 0),
            )
        )
    else:
        response_candidates.sort(
            key=lambda item: (
                _candidate_syllabus_sort_key(item, recommendation_graph_tree),
                -float(item.get("rag_relevance") or 0.0),
                int(item.get("rank") or 0),
            )
        )
    response_candidates = response_candidates[:candidate_limit]
    for idx, candidate in enumerate(response_candidates, start=1):
        candidate["rank"] = idx

    foundation_gap = _has_foundation_gap(recommendation_graph_tree, state)
    selected = []
    if response_candidates:
        if foundation_gap:
            selected = candidates[:1]
        else:
            try:
                selected = ib_grpo_select(
                    candidates,
                    raw_scores,
                    IB_constraints={"E": 0.0},
                    iterations=20,
                    N=1,
                )
            except Exception:
                selected = []

    score_by_path = {
        tuple(str(node_id) for node_id in candidate.get("path") or []): candidate_score
        for candidate, candidate_score in zip(candidates, raw_scores)
    }
    selected_paths = {
        tuple(str(node_id) for node_id in candidate.get("path") or [])
        for candidate in selected
    }
    for candidate in response_candidates:
        if tuple(candidate.get("path") or []) in selected_paths:
            candidate["selected"] = True

    response_selected = [
            _serialize_path_item(
                candidate,
                candidate_score=score_by_path.get(tuple(str(node_id) for node_id in candidate.get("path") or [])),
                selected=True,
                rag_overlay=rag_overlay,
                learning_tree=recommendation_graph_tree,
                state=state,
        )
        for candidate in selected
        if candidate.get("path")
    ]
    best_path = response_selected[0] if response_selected else next(
        (candidate for candidate in response_candidates if _has_nonempty_path(candidate)),
        None,
    )
    graph = _apply_rag_overlay_to_graph(_build_recommendation_graph(recommendation_graph_tree), rag_overlay)
    debug = {
        "graph_diagnostics": _graph_diagnostics(
            learning_tree=learning_tree,
            recommendation_graph_tree=recommendation_graph_tree,
            graph=graph,
            rag_overlay=rag_overlay,
            goals=goals,
            chosen_goals=chosen_goals,
            starts=starts,
            candidates=candidates,
            response_candidates=response_candidates,
        )
    }

    result = {
        "success": True,
        "schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "graph": graph,
        "rag_overlay": {
            key: value
            for key, value in rag_overlay.items()
            if key != "node_relevance"
        },
        "candidates": response_candidates,
        "selected": response_selected,
        "best_path": best_path,
        "debug": debug,
        "error_message": "",
        "error_code": "",
    }
    result["planning_hints"] = _build_planning_hints(result)
    return result


def run_recommendation_route_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and run the route using an API/task payload.

    Guard: rejects generation when an active learning plan exists.
    The plan must be completed or abandoned before a new recommendation can be generated.
    """
    payload = payload or {}
    user_id = payload.get("user_id")
    if not user_id:
        return {
            "success": False,
            "candidates": [],
            "selected": [],
            "error_message": "missing user_id",
            "error_code": "missing_fields",
        }

    # ----- guard: don't generate new recommendation when an active plan exists -----
    syllabus_id = int(payload["syllabus_id"]) if payload.get("syllabus_id") else None
    active_plan = None
    try:
        from tasks.personal_recommendation.learning_plan import get_active_learning_plan
        active_plan = get_active_learning_plan(int(user_id), syllabus_id)
    except Exception:
        pass  # best-effort: allow if plan lookup is unavailable
    if active_plan is not None:
        return {
            "success": False,
            "candidates": [],
            "selected": [],
            "error_message": (
                f"an active learning plan ({active_plan.get('plan_id', 'unknown')}) already exists. "
                "Complete or abandon the current plan before generating a new recommendation."
            ),
            "error_code": "active_plan_exists",
            "active_plan_id": active_plan.get("plan_id"),
        }

    result = run_recommendation_route(
        user_id=int(user_id),
        syllabus_id=syllabus_id,
        goals=payload.get("goals"),
        L_max=int(payload.get("L_max") or 6),
        T_max=int(payload.get("T_max") or 100),
        K=int(payload.get("K") or payload.get("max_candidates") or DEFAULT_RECOMMENDATION_CANDIDATE_LIMIT),
        beam_width=int(payload.get("beam_width") or 6),
        rag_context=payload.get("rag_context") if isinstance(payload.get("rag_context"), dict) else None,
        study_graph_state=payload.get("study_graph_state") if isinstance(payload.get("study_graph_state"), dict) else None,
        depth_strategy=_normalize_depth_strategy(payload.get("depth_strategy")),
        concept_decomposer=payload.get("concept_decomposer") if callable(payload.get("concept_decomposer")) else None,
        decomposer_mode=_normalize_decomposer_mode(payload.get("decomposer_mode") if payload.get("decomposer_mode") is not None else payload.get("use_agent_decomposer")),
        graph_name=str(payload.get("graph_name") or payload.get("rag_graph_name") or "") or None,
        rag_top_k=int(payload.get("rag_top_k") or 0) or None,
    )
    ensure_recommendation_snapshot(
        int(user_id),
        int(payload["syllabus_id"]) if payload.get("syllabus_id") else None,
        result,
        request_payload=payload,
        session_id=payload.get("session_id"),
        persist_snapshot=payload.get("persist_snapshot") is not False,
    )
    return result


def ensure_recommendation_snapshot(
    user_id: int,
    syllabus_id: Optional[int],
    recommendation_result: Dict[str, Any],
    *,
    request_payload: Optional[dict] = None,
    session_id: Optional[str] = None,
    persist_snapshot: bool = True,
    allow_proposed_resave: bool = False,
) -> Dict[str, Any]:
    result = recommendation_result if isinstance(recommendation_result, dict) else {}
    if not persist_snapshot:
        return result
    if not result.get("success"):
        return result
    existing_status = str(result.get("snapshot_status") or "").strip()
    if result.get("recommendation_id") and (
        not allow_proposed_resave
        or existing_status
        and existing_status != RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED
    ):
        return result
    if not isinstance(result.get("graph"), dict) or not isinstance(result.get("graph", {}).get("nodes"), list):
        return result

    try:
        snapshot = save_recommendation_snapshot(
            int(user_id),
            int(syllabus_id) if syllabus_id else None,
            result,
            request_payload=request_payload,
            session_id=session_id,
            status=RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
        )
    except Exception as exc:
        warnings = result.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED)
        result["snapshot_save_error_code"] = "exception"
        result["snapshot_save_error_message"] = str(exc)
        return result

    if snapshot.get("success"):
        result["recommendation_id"] = snapshot.get("recommendation_id")
        result["snapshot_status"] = snapshot.get("status")
        result["snapshot"] = snapshot
    else:
        warnings = result.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED)
        result["snapshot_save_error_code"] = snapshot.get("error_code") or "snapshot_save_failed"
        result["snapshot_save_error_message"] = snapshot.get("error_message") or ""
    return result
