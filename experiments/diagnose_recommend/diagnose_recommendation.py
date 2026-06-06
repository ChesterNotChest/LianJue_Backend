"""Diagnose recommendation graph shape and pruning behavior.

This script is intentionally outside tests. It writes a JSON artifact that helps
inspect why a route is shallow, why a start node disappears, and whether the
input graph has enough branching for diverse paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tasks.personal_recommendation.candidate_generator import generate
from tasks.personal_recommendation.evaluator import score
from tasks.personal_recommendation.graph_builder import build_recommendation_graph_tree
from tasks.personal_recommendation.perception import generate_state
from tasks.personal_recommendation.pruning import hard_prune, soft_prune_by_dominance
from tasks.personal_recommendation.rag_overlay import build_rag_overlay
from tasks.personal_recommendation.sample_data import goals as sample_goals
from tasks.personal_recommendation.sample_data import learning_tree as sample_learning_tree
from tasks.personal_recommendation.sample_data import user_profile as sample_user_profile
from tasks.personal_recommendation.syllabus_adapter import syllabus_json_to_learning_tree


DEFAULT_OUT = Path("experiments/diagnose_recommend/outputs/diagnosis.json")


def _load_json(path: str | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _graph_stats(tree: dict[str, Any]) -> dict[str, Any]:
    out_degree: dict[str, int] = {str(node_id): 0 for node_id in tree}
    in_degree: dict[str, int] = {str(node_id): 0 for node_id in tree}
    missing_prerequisites = []
    for node_id, raw_node in tree.items():
        node = raw_node if isinstance(raw_node, dict) else {}
        for prerequisite in node.get("prerequisites") or []:
            prerequisite = str(prerequisite)
            target = str(node_id)
            if prerequisite not in out_degree:
                missing_prerequisites.append({"source": prerequisite, "target": target})
                continue
            out_degree[prerequisite] += 1
            in_degree[target] += 1

    out_counter = Counter(out_degree.values())
    branch_nodes = [
        {
            "node_id": node_id,
            "title": (tree.get(node_id) or {}).get("title") or node_id,
            "out_degree": degree,
            "children": [
                child_id
                for child_id, raw_child in tree.items()
                if node_id in [str(item) for item in (raw_child if isinstance(raw_child, dict) else {}).get("prerequisites") or []]
            ],
        }
        for node_id, degree in sorted(out_degree.items(), key=lambda item: (-item[1], item[0]))
        if degree >= 2
    ]
    roots = [node_id for node_id, degree in in_degree.items() if degree == 0]
    leaves = [node_id for node_id, degree in out_degree.items() if degree == 0]
    return {
        "node_count": len(tree),
        "edge_count": sum(out_degree.values()),
        "root_count": len(roots),
        "leaf_count": len(leaves),
        "roots": roots[:20],
        "leaves": leaves[:20],
        "out_degree_histogram": dict(sorted(out_counter.items())),
        "max_out_degree": max(out_degree.values()) if out_degree else 0,
        "branch_node_count": len(branch_nodes),
        "branch_nodes": branch_nodes[:20],
        "missing_prerequisites": missing_prerequisites[:20],
    }


def _decomposition_stats(tree: dict[str, Any]) -> dict[str, Any]:
    method_counts = Counter()
    fallback_tag_counts = Counter()
    reliabilities = []
    for raw_node in tree.values():
        node = raw_node if isinstance(raw_node, dict) else {}
        method = str(node.get("decomposition_method") or "none")
        fallback_tag = str(node.get("fallback_tag") or "")
        method_counts[method] += 1
        if fallback_tag:
            fallback_tag_counts[fallback_tag] += 1
        try:
            if node.get("reliability") not in (None, ""):
                reliabilities.append(float(node.get("reliability")))
        except Exception:
            continue
    return {
        "method_counts": dict(sorted(method_counts.items())),
        "fallback_tag_counts": dict(sorted(fallback_tag_counts.items())),
        "reliability": {
            "count": len(reliabilities),
            "min": min(reliabilities) if reliabilities else None,
            "max": max(reliabilities) if reliabilities else None,
            "avg": round(sum(reliabilities) / len(reliabilities), 4) if reliabilities else None,
        },
    }


def _index_candidates(candidates: list[dict[str, Any]]) -> dict[tuple[str, ...], dict[str, Any]]:
    return {
        tuple(str(node_id) for node_id in candidate.get("path") or []): candidate
        for candidate in candidates
    }


def _candidate_rows(candidates: list[dict[str, Any]], raw_scores: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = []
    raw_scores = raw_scores or [{} for _ in candidates]
    for idx, (candidate, candidate_score) in enumerate(zip(candidates, raw_scores), start=1):
        path = [str(node_id) for node_id in candidate.get("path") or []]
        rows.append(
            {
                "index": idx,
                "path": path,
                "path_depth": int(candidate.get("path_depth") or len(path)),
                "cost": candidate.get("cost"),
                "skills": sorted(str(skill) for skill in candidate.get("skills") or []),
                "scores": candidate_score,
            }
        )
    return rows


def _explain_dropped(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    after_keys = set(_index_candidates(after))
    dropped = []
    for candidate in before:
        path = tuple(str(node_id) for node_id in candidate.get("path") or [])
        if path not in after_keys:
            dropped.append(
                {
                    "path": list(path),
                    "path_depth": int(candidate.get("path_depth") or len(path)),
                    "cost": candidate.get("cost"),
                    "skills": sorted(str(skill) for skill in candidate.get("skills") or []),
                }
            )
    return dropped


def _path_start_report(candidates: list[dict[str, Any]], starts: list[str]) -> dict[str, Any]:
    by_start = defaultdict(int)
    for candidate in candidates:
        path = [str(node_id) for node_id in candidate.get("path") or []]
        if path:
            by_start[path[0]] += 1
    missing = [str(start) for start in starts if by_start.get(str(start), 0) == 0]
    return {
        "candidate_count_by_start": dict(sorted(by_start.items())),
        "starts_without_candidate": missing,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.syllabus_json:
        syllabus_json = _load_json(args.syllabus_json)
        learning_tree = syllabus_json_to_learning_tree(syllabus_json)
        tree_source = args.syllabus_json
    else:
        learning_tree = dict(sample_learning_tree)
        tree_source = "sample_data.learning_tree"

    profile = _load_json(args.profile_json) or dict(sample_user_profile)
    requested_goals = args.goals or list(sample_goals)
    rag_context = _load_json(args.rag_json)
    study_graph_state = _load_json(args.study_graph_state_json) or None

    rag_overlay = build_rag_overlay(rag_context, learning_tree)
    graph_tree = build_recommendation_graph_tree(
        learning_tree,
        rag_overlay=rag_overlay,
        profile=profile,
        study_graph_state=study_graph_state,
    )
    state, starts = generate_state(profile, graph_tree, study_graph_state=study_graph_state)
    generated = generate(
        starts,
        requested_goals,
        graph_tree,
        state,
        L_max=args.l_max,
        T_max=args.t_max,
        K=args.k,
        beam_width=args.beam_width,
        depth_strategy=args.depth_strategy,
    )
    after_hard = hard_prune(
        generated,
        state,
        blocked_nodes=state.get("constraints", {}).get("blocked_nodes"),
    )
    raw_scores_before_soft = [score(candidate, state, graph_tree) for candidate in after_hard]
    after_soft = soft_prune_by_dominance(after_hard, raw_scores_before_soft)
    raw_scores_after_soft = [score(candidate, state, graph_tree) for candidate in after_soft]

    result = {
        "input": {
            "tree_source": tree_source,
            "goals": requested_goals,
            "depth_strategy": args.depth_strategy,
            "L_max": args.l_max,
            "T_max": args.t_max,
            "K": args.k,
            "beam_width": args.beam_width,
            "has_rag_context": bool(rag_context),
            "has_study_graph_state": bool(study_graph_state),
        },
        "graph_stats_before_overlay": _graph_stats(learning_tree),
        "graph_stats_after_overlay": _graph_stats(graph_tree),
        "decomposition_stats_before_overlay": _decomposition_stats(learning_tree),
        "decomposition_stats_after_overlay": _decomposition_stats(graph_tree),
        "starts": [str(start) for start in starts],
        "state": _json_safe(state),
        "rag_overlay_summary": {
            "enabled": rag_overlay.get("enabled"),
            "matched_node_count": len(rag_overlay.get("matched_nodes") or []),
            "temporary_edge_count": len(rag_overlay.get("temporary_edges") or []),
            "matched_nodes": rag_overlay.get("matched_nodes") or [],
            "temporary_edges": rag_overlay.get("temporary_edges") or [],
            "warnings": rag_overlay.get("warnings") or [],
        },
        "pipeline_counts": {
            "generated": len(generated),
            "after_hard_prune": len(after_hard),
            "after_soft_prune": len(after_soft),
        },
        "start_report_generated": _path_start_report(generated, [str(start) for start in starts]),
        "start_report_after_soft": _path_start_report(after_soft, [str(start) for start in starts]),
        "generated_candidates": _candidate_rows(generated),
        "after_hard_prune_candidates": _candidate_rows(after_hard, raw_scores_before_soft),
        "after_soft_prune_candidates": _candidate_rows(after_soft, raw_scores_after_soft),
        "dropped_by_hard_prune": _explain_dropped(generated, after_hard),
        "dropped_by_soft_prune": _explain_dropped(after_hard, after_soft),
    }
    return _json_safe(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--syllabus-json", help="Path to a syllabus JSON file. Omit to use sample tree.")
    parser.add_argument("--profile-json", help="Optional recommendation profile JSON.")
    parser.add_argument("--rag-json", help="Optional RAG context JSON.")
    parser.add_argument("--study-graph-state-json", help="Optional study graph state JSON.")
    parser.add_argument("--goals", nargs="*", help="Recommendation goals. Omit to use sample goals.")
    parser.add_argument("--depth-strategy", default="balanced", choices=["shortest", "balanced", "deep_prerequisite"])
    parser.add_argument("--l-max", type=int, default=6)
    parser.add_argument("--t-max", type=int, default=100)
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--beam-width", type=int, default=6)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    result = run(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(
        {
            "out": str(out),
            "node_count": result["graph_stats_after_overlay"]["node_count"],
            "edge_count": result["graph_stats_after_overlay"]["edge_count"],
            "branch_node_count": result["graph_stats_after_overlay"]["branch_node_count"],
            "starts": result["starts"][:10],
            "pipeline_counts": result["pipeline_counts"],
            "best_after_soft": (result["after_soft_prune_candidates"] or [{}])[0].get("path"),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
