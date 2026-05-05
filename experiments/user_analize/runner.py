from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from experiments.user_analize.profile_runtime import (
    OUTPUTS_DIR,
    build_sample_indices,
    compute_learning_profile,
    load_experiment_datasets,
    write_json_file,
)


def _extract_path(data: Dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for piece in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(piece)
        else:
            return None
    return current


def _write_output(output_dir: Path, name: str, payload: Any) -> str:
    path = output_dir / name
    write_json_file(path, payload)
    return str(path)


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = {}
            for field in fieldnames:
                value = row.get(field)
                if isinstance(value, (list, dict)):
                    normalized[field] = json.dumps(value, ensure_ascii=False)
                else:
                    normalized[field] = value
            writer.writerow(normalized)
    return str(path)


VARIANT_LABELS = {
    "full": "Full Input",
    "no_dialogue_text": "No Dialogue Text",
    "no_answer_records": "No Answer Records",
    "no_resource_usage": "No Resource Usage",
    "no_learning_records": "No Learning Records",
    "id_only": "ID Only",
}


FIELD_LABELS = {
    "goal_clarity": "Goal Clarity",
    "term_familiarity": "Term Familiarity",
    "resource_preference": "Resource Preference",
    "dropout_risk": "Dropout Risk",
    "confidence": "Confidence",
    "emotion_state": "Emotion State",
    "help_seeking_level": "Help Seeking Level",
    "recent_anomaly": "Recent Anomaly",
    "learning_style": "Learning Style",
    "warning_count": "Warning Count",
    "missing_field_report": "Missing Field Report",
    "format_issue_report": "Format Issue Report",
}


PRIORITY_LABELS = {
    "high": "High Priority",
    "medium": "Medium Priority",
    "low": "Low Priority",
}


def _humanize_token(value: str) -> str:
    if not value:
        return value
    return " ".join(piece.capitalize() for piece in value.replace(".", "_").split("_") if piece)


def _build_bundle_context(bundle: Dict[str, Any], datasets: Dict[str, Any], indices: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    refs = bundle["references"]
    syllabus_base = datasets["syllabus_base_dataset.json"]
    personal = indices["personal_by_id"][refs["personal_syllabus_sample_id"]]
    return {
        "user": {
            "user_id": bundle["user_id"],
            "user_name": bundle["persona_id"],
            "email": f"user_{bundle['user_id']}@example.local",
        },
        "syllabus": {
            "syllabus_id": datasets["dataset_index.json"]["course_context"]["syllabus_id"],
            "title": syllabus_base["title"],
            "graph_name": syllabus_base["graph_name"],
            "weeks": syllabus_base["weeks"],
        },
        "personal_syllabus": personal,
        "personal_syllabus_path": None,
        "history": [],
    }


def _materialize_ablation_bundle(base_bundle: Dict[str, Any], variant_template: Dict[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(base_bundle)
    payload.pop("expected_profile_labels", None)
    payload.pop("references", None)
    payload.pop("bundle_id", None)
    payload.pop("persona_id", None)
    for field in variant_template.get("drop_fields", []):
        payload.pop(field, None)
    return payload


def _apply_mutation(payload: Dict[str, Any], mutation: Dict[str, Any]) -> None:
    field = mutation["field"]
    action = mutation["action"]
    if field == "learning_goal" and action == "remove":
        payload.pop("learning_goal", None)
        return
    if field == "learning_records" and action == "replace_with_empty_array":
        payload["learning_records"] = []
        return
    if field == "resource_usage" and action == "replace_with_empty_array":
        payload["resource_usage"] = []
        return
    if field == "learning_records[*].started_at" and action == "inject_nonstandard_time_strings":
        for index, record in enumerate(payload.get("learning_records", [])):
            if index % 2 == 0:
                record["started_at"] = "2026/04/29 21:10"
            else:
                record["started_at"] = "2026-04-29 23:05:00"
        return
    if field == "answer_records[*].answered_at" and action == "mix_timestamp_and_legacy_string":
        for index, record in enumerate(payload.get("answer_records", [])):
            if index % 2 == 0:
                record["answered_at"] = "2026/04/30 00:11"
            else:
                record["answered_at"] = 1777461000
        return
    if field == "answer_records[*].meta.knowledge_points" and action == "remove_from_one_record":
        if payload.get("answer_records"):
            payload["answer_records"][0].setdefault("meta", {}).pop("knowledge_points", None)
        return
    if field == "answer_records[*].meta.week_index" and action == "set_conflicting_week_index":
        if payload.get("answer_records"):
            payload["answer_records"][0].setdefault("meta", {})["week_index"] = "99"
        return
    if field == "learning_records[*].event_type" and action == "set_unknown_event_type":
        if payload.get("learning_records"):
            payload["learning_records"][0]["event_type"] = "mystery_event"
        return
    if field == "resource_usage" and action == "duplicate_first_record":
        if payload.get("resource_usage"):
            payload["resource_usage"].append(copy.deepcopy(payload["resource_usage"][0]))
        return


def _materialize_edge_case_bundle(base_bundle: Dict[str, Any], template: Dict[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(base_bundle)
    payload.pop("expected_profile_labels", None)
    payload.pop("references", None)
    payload.pop("bundle_id", None)
    payload.pop("persona_id", None)
    for mutation in template.get("mutations", []):
        _apply_mutation(payload, mutation)
    return payload


def run_base_profiles(datasets: Dict[str, Any], indices: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for bundle in datasets["profile_input_bundles.json"]["bundles"]:
        context = _build_bundle_context(bundle, datasets, indices)
        payload = copy.deepcopy(bundle)
        expected = payload.pop("expected_profile_labels", {})
        references = payload.pop("references", {})
        payload.pop("bundle_id", None)
        payload.pop("persona_id", None)
        result = compute_learning_profile(payload, context)
        results.append(
            {
                "bundle_id": bundle["bundle_id"],
                "persona_id": bundle["persona_id"],
                "expected_profile_labels": expected,
                "references": references,
                "profile": result["profile"],
            }
        )
    return results


def run_ablation_experiment(datasets: Dict[str, Any], indices: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    ablation = datasets["ablation_bundles.json"]
    templates = {item["variant"]: item for item in ablation["variant_templates"]}
    results = []
    for row in ablation["case_matrix"]:
        base_bundle = indices["bundle_by_id"][row["base_bundle_id"]]
        context = _build_bundle_context(base_bundle, datasets, indices)
        for variant_case in row["variants"]:
            payload = _materialize_ablation_bundle(base_bundle, templates[variant_case["variant"]])
            result = compute_learning_profile(payload, context)
            results.append(
                {
                    "case_id": variant_case["case_id"],
                    "base_bundle_id": row["base_bundle_id"],
                    "variant": variant_case["variant"],
                    "expected_confidence_trend": variant_case["expected_confidence_trend"],
                    "expected_primary_signal": variant_case["expected_primary_signal"],
                    "profile_summary": {
                        "confidence": result["profile"]["confidence"],
                        "dropout_risk": result["profile"]["dropout_risk"],
                        "source_events": result["profile"]["source_events"],
                        "normalization_report": result["profile"]["normalization_report"],
                    },
                }
            )
    return results


def run_edge_case_experiment(datasets: Dict[str, Any], indices: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    edge = datasets["edge_case_bundles.json"]
    results = []
    for case in edge["cases"]:
        base_bundle = indices["bundle_by_id"][case["base_bundle_id"]]
        template = indices["edge_template_by_id"][case["template_id"]]
        context = _build_bundle_context(base_bundle, datasets, indices)
        payload = _materialize_edge_case_bundle(base_bundle, template)
        result = compute_learning_profile(payload, context)
        results.append(
            {
                "case_id": case["case_id"],
                "template_id": case["template_id"],
                "expected_outcome": case["expected_outcome"],
                "expected_warnings": template.get("expected_warnings", []),
                "profile_summary": {
                    "confidence": result["profile"]["confidence"],
                    "dropout_risk": result["profile"]["dropout_risk"],
                    "missing_field_report": result["profile"]["missing_field_report"],
                    "format_issue_report": result["profile"]["format_issue_report"],
                    "normalization_report": result["profile"]["normalization_report"],
                },
            }
        )
    return results


def run_stability_experiment(datasets: Dict[str, Any], indices: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    stability = datasets["stability_eval_set.json"]
    edge = datasets["edge_case_bundles.json"]
    edge_template_by_id = indices["edge_template_by_id"]
    edge_case_by_id = indices["edge_case_by_id"]
    repeat_count = stability["recommended_repeat_count"]
    results = []
    for target in stability["targets"]:
        if target["source_type"] == "profile_bundle":
            bundle = indices["bundle_by_id"][target["source_id"]]
            payload = copy.deepcopy(bundle)
            payload.pop("expected_profile_labels", None)
            payload.pop("references", None)
            payload.pop("bundle_id", None)
            payload.pop("persona_id", None)
            context = _build_bundle_context(bundle, datasets, indices)
        else:
            edge_case = edge_case_by_id[target["source_id"]]
            base_bundle = indices["bundle_by_id"][edge_case["base_bundle_id"]]
            template = edge_template_by_id[edge_case["template_id"]]
            payload = _materialize_edge_case_bundle(base_bundle, template)
            context = _build_bundle_context(base_bundle, datasets, indices)

        snapshots = [compute_learning_profile(payload, context)["profile"] for _ in range(repeat_count)]
        field_values = {}
        for field in target["check_fields"]:
            values = [_extract_path(snapshot, field) for snapshot in snapshots]
            field_values[field] = {
                "distinct_values": len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values}),
                "values": values,
            }
        results.append(
            {
                "target_id": target["target_id"],
                "stability_expectation": target["stability_expectation"],
                "repeat_count": repeat_count,
                "field_values": field_values,
            }
        )
    return results


def run_manual_review_packet(datasets: Dict[str, Any], indices: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    packets = []
    for item in datasets["manual_review_set.json"]["items"]:
        if item["source_type"] == "profile_bundle":
            bundle = indices["bundle_by_id"][item["source_id"]]
            payload = copy.deepcopy(bundle)
            payload.pop("expected_profile_labels", None)
            payload.pop("references", None)
            payload.pop("bundle_id", None)
            payload.pop("persona_id", None)
            context = _build_bundle_context(bundle, datasets, indices)
            expected = bundle.get("expected_profile_labels", {})
        else:
            edge_case = indices["edge_case_by_id"][item["source_id"]]
            base_bundle = indices["bundle_by_id"][edge_case["base_bundle_id"]]
            template = indices["edge_template_by_id"][edge_case["template_id"]]
            payload = _materialize_edge_case_bundle(base_bundle, template)
            context = _build_bundle_context(base_bundle, datasets, indices)
            expected = {"expected_outcome": edge_case["expected_outcome"]}
        profile = compute_learning_profile(payload, context)["profile"]
        packets.append(
            {
                "review_id": item["review_id"],
                "priority": item["priority"],
                "reason": item["reason"],
                "focus_fields": item["focus_fields"],
                "expected": expected,
                "profile_excerpt": {field: _extract_path(profile, field) for field in item["focus_fields"]},
            }
        )
    return packets


def export_plot_csvs(
    output_dir: Path,
    base_profiles: List[Dict[str, Any]],
    ablation_results: List[Dict[str, Any]],
    edge_results: List[Dict[str, Any]],
    stability_results: List[Dict[str, Any]],
    manual_packets: List[Dict[str, Any]],
) -> Dict[str, str]:
    plot_dir = output_dir / "plot_data"
    base_profile_count = max(len(base_profiles), 1)

    base_metric_rows: List[Dict[str, Any]] = []
    base_gap_rows: List[Dict[str, Any]] = []
    concept_gap_stats: Dict[str, Dict[str, Any]] = {}
    for item in base_profiles:
        profile = item["profile"]
        base_metric_rows.append(
            {
                "bundle_id": item["bundle_id"],
                "persona_id": item["persona_id"],
                "confidence": profile.get("confidence"),
                "dropout_risk": profile.get("dropout_risk"),
                "dropout_risk_score": profile.get("dropout_risk_score"),
                "overall_score": profile.get("knowledge_mastery", {}).get("overall_score"),
                "answer_score": profile.get("knowledge_mastery", {}).get("answer_score"),
                "syllabus_score": profile.get("knowledge_mastery", {}).get("syllabus_score"),
                "engagement_score": profile.get("knowledge_mastery", {}).get("engagement_score"),
                "goal_clarity_score": profile.get("goal_clarity", {}).get("score"),
                "term_familiarity_score": profile.get("term_familiarity", {}).get("score"),
                "study_frequency": profile.get("study_frequency"),
                "study_duration": profile.get("study_duration"),
                "attention_pattern": profile.get("attention_pattern"),
                "learning_style": profile.get("learning_style"),
                "resource_preference_1": (profile.get("resource_preference") or [None, None])[0],
                "resource_preference_2": (profile.get("resource_preference") or [None, None])[1],
                "concept_gap_count": len(profile.get("concept_gaps", [])),
                "weak_week_count": len(profile.get("knowledge_mastery", {}).get("weak_weeks", [])),
            }
        )
        for gap in profile.get("concept_gaps", []):
            row = {
                "bundle_id": item["bundle_id"],
                "sample_id": item["bundle_id"],
                "persona_id": item["persona_id"],
                "persona_label": item["persona_id"],
                "concept_gap": gap,
                "concept_gap_label": gap,
            }
            base_gap_rows.append(row)
            stats = concept_gap_stats.setdefault(
                gap,
                {
                    "concept_gap_label": gap,
                    "sample_ids": set(),
                    "persona_labels": set(),
                    "occurrence_count": 0,
                },
            )
            stats["sample_ids"].add(item["bundle_id"])
            stats["persona_labels"].add(item["persona_id"])
            stats["occurrence_count"] += 1

    concept_gap_stat_rows: List[Dict[str, Any]] = []
    for label, details in sorted(
        concept_gap_stats.items(),
        key=lambda pair: (
            -pair[1]["occurrence_count"],
            -len(pair[1]["persona_labels"]),
            pair[0],
        ),
    ):
        sample_ids = sorted(details["sample_ids"])
        persona_labels = sorted(details["persona_labels"])
        concept_gap_stat_rows.append(
            {
                "concept_gap_label": label,
                "occurrence_count": details["occurrence_count"],
                "affected_sample_count": len(sample_ids),
                "affected_persona_count": len(persona_labels),
                "persona_coverage_ratio": round(len(persona_labels) / base_profile_count, 4),
                "sample_ids": sample_ids,
                "persona_labels": persona_labels,
            }
        )

    ablation_long_rows: List[Dict[str, Any]] = []
    ablation_matrix: Dict[str, Dict[str, Any]] = {}
    for item in ablation_results:
        summary = item["profile_summary"]
        ablation_long_rows.append(
            {
                "case_id": item["case_id"],
                "base_bundle_id": item["base_bundle_id"],
                "variant": item["variant"],
                "variant_label": VARIANT_LABELS.get(item["variant"], _humanize_token(item["variant"])),
                "expected_confidence_trend": item["expected_confidence_trend"],
                "expected_primary_signal": item["expected_primary_signal"],
                "confidence": summary.get("confidence"),
                "dropout_risk": summary.get("dropout_risk"),
                "warning_count": summary.get("normalization_report", {}).get("warning_count"),
                "source_event_count": len(summary.get("source_events", [])),
            }
        )
        row = ablation_matrix.setdefault(item["base_bundle_id"], {"base_bundle_id": item["base_bundle_id"]})
        row[f"{item['variant']}_confidence"] = summary.get("confidence")
        row[f"{item['variant']}_warning_count"] = summary.get("normalization_report", {}).get("warning_count")

    edge_rows: List[Dict[str, Any]] = []
    for item in edge_results:
        summary = item["profile_summary"]
        edge_rows.append(
            {
                "case_id": item["case_id"],
                "template_id": item["template_id"],
                "expected_outcome": item["expected_outcome"],
                "confidence": summary.get("confidence"),
                "dropout_risk": summary.get("dropout_risk"),
                "missing_field_count": len(summary.get("missing_field_report", [])),
                "format_issue_count": len(summary.get("format_issue_report", [])),
                "warning_count": summary.get("normalization_report", {}).get("warning_count"),
                "missing_field_report": summary.get("missing_field_report", []),
                "format_issue_report": summary.get("format_issue_report", []),
            }
        )

    stability_rows: List[Dict[str, Any]] = []
    for item in stability_results:
        for field_name, details in item["field_values"].items():
            stability_rows.append(
                {
                    "target_id": item["target_id"],
                    "stability_expectation": item["stability_expectation"],
                    "repeat_count": item["repeat_count"],
                    "field_name": field_name,
                    "field_label": FIELD_LABELS.get(field_name, _humanize_token(field_name)),
                    "distinct_values": details.get("distinct_values"),
                }
            )

    manual_rows: List[Dict[str, Any]] = []
    manual_summary_map: Dict[str, Dict[str, Any]] = {}
    for item in manual_packets:
        focus_fields = item.get("focus_fields", [])
        manual_rows.append(
            {
                "review_id": item["review_id"],
                "priority": item["priority"],
                "priority_label": PRIORITY_LABELS.get(item["priority"], _humanize_token(item["priority"])),
                "reason": item["reason"],
                "focus_field_count": len(focus_fields),
                "focus_fields": focus_fields,
                "expected": item.get("expected", {}),
                "profile_excerpt": item.get("profile_excerpt", {}),
            }
        )
        summary = manual_summary_map.setdefault(
            item["priority"],
            {
                "priority": item["priority"],
                "priority_label": PRIORITY_LABELS.get(item["priority"], _humanize_token(item["priority"])),
                "review_ids": [],
                "reasons": [],
                "review_count": 0,
                "focus_field_total": 0,
            },
        )
        summary["review_ids"].append(item["review_id"])
        summary["reasons"].append(item["reason"])
        summary["review_count"] += 1
        summary["focus_field_total"] += len(focus_fields)

    manual_summary_rows: List[Dict[str, Any]] = []
    for priority in ["high", "medium", "low"]:
        if priority not in manual_summary_map:
            continue
        summary = manual_summary_map[priority]
        review_count = max(summary["review_count"], 1)
        manual_summary_rows.append(
            {
                "priority": summary["priority"],
                "priority_label": summary["priority_label"],
                "review_count": summary["review_count"],
                "focus_field_total": summary["focus_field_total"],
                "average_focus_field_count": round(summary["focus_field_total"] / review_count, 2),
                "review_ids": summary["review_ids"],
                "reasons": summary["reasons"],
            }
        )

    files = {
        "base_profile_metrics_csv": _write_csv(
            plot_dir / "base_profile_metrics.csv",
            base_metric_rows,
            [
                "bundle_id",
                "persona_id",
                "confidence",
                "dropout_risk",
                "dropout_risk_score",
                "overall_score",
                "answer_score",
                "syllabus_score",
                "engagement_score",
                "goal_clarity_score",
                "term_familiarity_score",
                "study_frequency",
                "study_duration",
                "attention_pattern",
                "learning_style",
                "resource_preference_1",
                "resource_preference_2",
                "concept_gap_count",
                "weak_week_count",
            ],
        ),
        "base_profile_concept_gaps_csv": _write_csv(
            plot_dir / "base_profile_concept_gaps.csv",
            base_gap_rows,
            [
                "bundle_id",
                "sample_id",
                "persona_id",
                "persona_label",
                "concept_gap",
                "concept_gap_label",
            ],
        ),
        "concept_gap_stats_csv": _write_csv(
            plot_dir / "concept_gap_stats.csv",
            concept_gap_stat_rows,
            [
                "concept_gap_label",
                "occurrence_count",
                "affected_sample_count",
                "affected_persona_count",
                "persona_coverage_ratio",
                "sample_ids",
                "persona_labels",
            ],
        ),
        "ablation_long_csv": _write_csv(
            plot_dir / "ablation_long.csv",
            ablation_long_rows,
            [
                "case_id",
                "base_bundle_id",
                "variant",
                "variant_label",
                "expected_confidence_trend",
                "expected_primary_signal",
                "confidence",
                "dropout_risk",
                "warning_count",
                "source_event_count",
            ],
        ),
        "ablation_matrix_csv": _write_csv(
            plot_dir / "ablation_confidence_matrix.csv",
            list(ablation_matrix.values()),
            [
                "base_bundle_id",
                "full_confidence",
                "no_dialogue_text_confidence",
                "no_answer_records_confidence",
                "no_resource_usage_confidence",
                "no_learning_records_confidence",
                "id_only_confidence",
                "full_warning_count",
                "no_dialogue_text_warning_count",
                "no_answer_records_warning_count",
                "no_resource_usage_warning_count",
                "no_learning_records_warning_count",
                "id_only_warning_count",
            ],
        ),
        "edge_case_metrics_csv": _write_csv(
            plot_dir / "edge_case_metrics.csv",
            edge_rows,
            [
                "case_id",
                "template_id",
                "expected_outcome",
                "confidence",
                "dropout_risk",
                "missing_field_count",
                "format_issue_count",
                "warning_count",
                "missing_field_report",
                "format_issue_report",
            ],
        ),
        "stability_summary_csv": _write_csv(
            plot_dir / "stability_summary.csv",
            stability_rows,
            [
                "target_id",
                "stability_expectation",
                "repeat_count",
                "field_name",
                "field_label",
                "distinct_values",
            ],
        ),
        "manual_review_packets_csv": _write_csv(
            plot_dir / "manual_review_packets.csv",
            manual_rows,
            [
                "review_id",
                "priority",
                "priority_label",
                "reason",
                "focus_field_count",
                "focus_fields",
                "expected",
                "profile_excerpt",
            ],
        ),
        "manual_review_summary_csv": _write_csv(
            plot_dir / "manual_review_summary.csv",
            manual_summary_rows,
            [
                "priority",
                "priority_label",
                "review_count",
                "focus_field_total",
                "average_focus_field_count",
                "review_ids",
                "reasons",
            ],
        ),
    }
    return files


def run_full_experiment_suite(output_dir: Optional[Path] = None) -> Dict[str, Any]:
    datasets = load_experiment_datasets()
    indices = build_sample_indices(datasets)
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    base_profiles = run_base_profiles(datasets, indices)
    ablation_results = run_ablation_experiment(datasets, indices)
    edge_results = run_edge_case_experiment(datasets, indices)
    stability_results = run_stability_experiment(datasets, indices)
    manual_packets = run_manual_review_packet(datasets, indices)

    base_path = _write_output(output_dir, "base_profile_results.json", base_profiles)
    ablation_path = _write_output(output_dir, "ablation_results.json", ablation_results)
    edge_path = _write_output(output_dir, "edge_case_results.json", edge_results)
    stability_path = _write_output(output_dir, "stability_results.json", stability_results)
    manual_path = _write_output(output_dir, "manual_review_packets.json", manual_packets)
    csv_files = export_plot_csvs(output_dir, base_profiles, ablation_results, edge_results, stability_results, manual_packets)

    summary = {
        "base_profile_count": len(base_profiles),
        "ablation_case_count": len(ablation_results),
        "edge_case_count": len(edge_results),
        "stability_target_count": len(stability_results),
        "manual_review_count": len(manual_packets),
        "output_files": {
            "base_profiles": base_path,
            "ablation_results": ablation_path,
            "edge_case_results": edge_path,
            "stability_results": stability_path,
            "manual_review_packets": manual_path,
        },
        "plot_csv_files": csv_files,
    }
    summary_path = _write_output(output_dir, "profile_experiment_summary.json", summary)
    summary["summary_path"] = summary_path
    return summary


if __name__ == "__main__":
    result = run_full_experiment_suite()
    print(json.dumps(result, ensure_ascii=False, indent=2))
