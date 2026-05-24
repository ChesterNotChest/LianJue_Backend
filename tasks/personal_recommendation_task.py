"""Task entry for the personal recommendation route agent.

The lower-level implementation lives in ``tasks.personal_recommendation``.
This module provides the same kind of task-facing boundary used by the other
agents, so API code and tests do not assemble the recommendation pipeline
directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.syllabus_repo import get_syllabus_by_id
from tasks.learning_profile.storage import load_json_file
from tasks.learning_profile_task import get_or_build_learning_profile
from tasks.personal_recommendation.candidate_generator import generate
from tasks.personal_recommendation.evaluator import score
from tasks.personal_recommendation.perception import generate_state
from tasks.personal_recommendation.pruning import hard_prune, soft_prune_by_dominance
from tasks.personal_recommendation.rag_overlay import build_rag_overlay, score_candidate_with_overlay
from tasks.personal_recommendation.sample_data import learning_tree as sample_learning_tree
from tasks.personal_recommendation.selector_ib_grpo import ib_grpo_select
from tasks.syllabus_to_learning_tree import syllabus_json_to_learning_tree


def run_personal_recommendation_agent(payload: Dict[str, Any]) -> Any:
    from tasks.personal_recommendation.agent_runtime import run_personal_recommendation_agent as _run_agent

    return _run_agent(payload)


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


def _path_edges(path: List[Any]) -> List[Dict[str, str]]:
    edges = []
    for idx in range(len(path) - 1):
        source = str(path[idx])
        target = str(path[idx + 1])
        edges.append({
            "edge_id": f"{source}->{target}",
            "source": source,
            "target": target,
        })
    return edges


def _build_recommendation_graph(learning_tree: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    nodes = []
    edges = []
    for node_id, raw_node in learning_tree.items():
        node = raw_node if isinstance(raw_node, dict) else {}
        normalized_id = str(node_id)
        nodes.append({
            "id": normalized_id,
            "title": node.get("title") or normalized_id,
            "difficulty": node.get("difficulty", 1),
            "learning_time_est": node.get("learning_time_est", 1),
            "outcomes": list(node.get("outcomes") or []),
            "prerequisites": [str(item) for item in node.get("prerequisites") or []],
        })
        for prerequisite in node.get("prerequisites") or []:
            source = str(prerequisite)
            target = normalized_id
            edges.append({
                "edge_id": f"{source}->{target}",
                "source": source,
                "target": target,
                "type": "prerequisite",
            })
    return {"nodes": nodes, "edges": edges}


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
) -> Dict[str, Any]:
    item = _json_safe(dict(candidate))
    path = [str(node_id) for node_id in item.get("path") or []]
    item["path"] = path
    item["path_edges"] = _path_edges(path)
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


def load_recommendation_learning_tree(syllabus_id: Optional[int] = None) -> Dict[str, Any]:
    """Load the recommendation graph, preferring a real syllabus-derived tree."""
    if not syllabus_id:
        return sample_learning_tree

    try:
        syllabus = get_syllabus_by_id(int(syllabus_id))
        syllabus_path = getattr(syllabus, "syllabus_path", None) if syllabus else None
        if not syllabus_path:
            return sample_learning_tree
        syllabus_json = load_json_file(syllabus_path)
        mapped = syllabus_json_to_learning_tree(syllabus_json)
        return mapped or sample_learning_tree
    except Exception:
        return sample_learning_tree


def build_recommendation_profile(user_id: int, syllabus_id: Optional[int] = None) -> Dict[str, Any]:
    """Fetch or build a profile, falling back to a minimal transient profile."""
    profile = get_or_build_learning_profile(
        int(user_id),
        int(syllabus_id) if syllabus_id else None,
        refresh_profile=False,
    )
    if profile is not None:
        return profile
    return {
        "user_id": int(user_id),
        "syllabus_id": int(syllabus_id) if syllabus_id else None,
        "knowledge_levels": {},
        "learning_goals": [],
    }


def run_recommendation_route(
    user_id: int,
    syllabus_id: Optional[int] = None,
    goals: Optional[List[str]] = None,
    L_max: int = 6,
    T_max: int = 100,
    K: int = 20,
    beam_width: int = 6,
    rag_context: Optional[Dict[str, Any]] = None,
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

    profile = build_recommendation_profile(int(user_id), syllabus_id)
    chosen_goals = goals or profile.get("learning_goals") or []
    learning_tree = load_recommendation_learning_tree(syllabus_id)
    rag_overlay = build_rag_overlay(rag_context, learning_tree)

    state, starts = generate_state(profile, learning_tree)
    candidates = generate(
        starts,
        chosen_goals,
        learning_tree,
        state,
        L_max=int(L_max),
        T_max=int(T_max),
        K=int(K),
        beam_width=int(beam_width),
    )

    candidates = hard_prune(
        candidates,
        state,
        blocked_nodes=state.get("constraints", {}).get("blocked_nodes"),
    )
    raw_scores = [score(candidate, state, learning_tree) for candidate in candidates]

    candidates = soft_prune_by_dominance(candidates, raw_scores)
    raw_scores = [score(candidate, state, learning_tree) for candidate in candidates]

    response_candidates = []
    for candidate, candidate_score in zip(candidates, raw_scores):
        response_candidates.append(
            _serialize_path_item(
                candidate,
                candidate_score=candidate_score,
                rank=len(response_candidates) + 1,
                rag_overlay=rag_overlay,
            )
        )

    response_candidates.sort(
        key=lambda item: (
            float(item.get("rag_relevance") or 0.0),
            -int(item.get("rank") or 0),
        ),
        reverse=True,
    )
    for idx, candidate in enumerate(response_candidates, start=1):
        candidate["rank"] = idx

    selected = []
    if response_candidates:
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
            )
        for candidate in selected
    ]
    best_path = response_selected[0] if response_selected else (response_candidates[0] if response_candidates else None)
    graph = _apply_rag_overlay_to_graph(_build_recommendation_graph(learning_tree), rag_overlay)

    return {
        "success": True,
        "graph": graph,
        "rag_overlay": {
            key: value
            for key, value in rag_overlay.items()
            if key != "node_relevance"
        },
        "candidates": response_candidates,
        "selected": response_selected,
        "best_path": best_path,
        "error_message": "",
        "error_code": "",
    }


def run_recommendation_route_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and run the route using an API/task payload."""
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

    return run_recommendation_route(
        user_id=int(user_id),
        syllabus_id=int(payload["syllabus_id"]) if payload.get("syllabus_id") else None,
        goals=payload.get("goals"),
        L_max=int(payload.get("L_max") or 6),
        T_max=int(payload.get("T_max") or 100),
        K=int(payload.get("K") or 20),
        beam_width=int(payload.get("beam_width") or 6),
        rag_context=payload.get("rag_context") if isinstance(payload.get("rag_context"), dict) else None,
    )
