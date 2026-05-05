from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
PLOT_DATA_DIR = OUTPUTS_DIR / "plot_data"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TABLES_DIR = OUTPUTS_DIR / "tables"

TEXT = "#222222"
GRID = "#dddddd"
SPINE = "#bbbbbb"
BLUE = "#4c78a8"
RED = "#e45756"
GRAY = "#7f7f7f"

VARIANT_ORDER = [
    "no_dialogue_text_confidence",
    "no_answer_records_confidence",
    "no_resource_usage_confidence",
    "no_learning_records_confidence",
    "id_only_confidence",
]
VARIANT_LABELS = {
    "no_dialogue_text_confidence": "No dialogue",
    "no_answer_records_confidence": "No answers",
    "no_resource_usage_confidence": "No resource",
    "no_learning_records_confidence": "No learning",
    "id_only_confidence": "ID only",
}
FIELD_LABELS = {
    "goal_clarity": "Goal clarity",
    "term_familiarity": "Term familiarity",
    "resource_preference": "Resource preference",
    "dropout_risk": "Dropout risk",
    "confidence": "Confidence",
    "emotion_state": "Emotion state",
    "help_seeking_level": "Help seeking",
    "recent_anomaly": "Recent anomaly",
    "learning_style": "Learning style",
    "warning_count": "Warnings",
    "missing_field_report": "Missing fields",
    "format_issue_report": "Format issues",
}


def _configure_style() -> None:
    sns.set_theme(
        style="whitegrid",
        context="paper",
        rc={
            "font.family": "serif",
            "font.serif": [
                "Times New Roman",
                "Noto Serif CJK SC",
                "SimSun",
                "STSong",
                "DejaVu Serif",
            ],
            "axes.edgecolor": SPINE,
            "grid.color": GRID,
            "axes.labelcolor": TEXT,
            "xtick.color": TEXT,
            "ytick.color": TEXT,
            "text.color": TEXT,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        },
    )


def _load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_int(value: str, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_json_list(value: str) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        return []
    return []


def _field_label(value: str) -> str:
    return FIELD_LABELS.get(value, value.replace("_", " ").title())


def _save_figure(fig: plt.Figure, name: str) -> Dict[str, str]:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = CHARTS_DIR / f"{name}.svg"
    png_path = CHARTS_DIR / f"{name}.png"
    fig.savefig(svg_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return {
        f"{name}_svg": str(svg_path),
        f"{name}_png": str(png_path),
    }


def _write_markdown_table(path: Path, frame: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(frame.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in frame.astype(str).itertuples(index=False):
        lines.append("| " + " | ".join(row) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _write_table_files(name: str, frame: pd.DataFrame) -> Dict[str, str]:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TABLES_DIR / f"{name}.csv"
    md_path = TABLES_DIR / f"{name}.md"
    frame.to_csv(csv_path, index=False, encoding="utf-8")
    _write_markdown_table(md_path, frame)
    return {
        f"{name}_csv": str(csv_path),
        f"{name}_md": str(md_path),
    }


def _load_concept_gap_stats() -> pd.DataFrame:
    summary_path = PLOT_DATA_DIR / "concept_gap_stats.csv"
    if summary_path.exists():
        frame = pd.read_csv(summary_path)
        if "concept_gap_label" not in frame.columns and "concept_gap" in frame.columns:
            frame["concept_gap_label"] = frame["concept_gap"]
        return frame

    rows = _load_csv(PLOT_DATA_DIR / "base_profile_concept_gaps.csv")
    counts: Dict[str, set[str]] = {}
    occurrences: Dict[str, int] = {}
    for row in rows:
        label = row.get("concept_gap_label") or row.get("concept_gap") or ""
        persona = row.get("persona_label") or row.get("persona_id") or ""
        if not label:
            continue
        counts.setdefault(label, set())
        if persona:
            counts[label].add(persona)
        occurrences[label] = occurrences.get(label, 0) + 1
    frame = pd.DataFrame(
        [
            {
                "concept_gap_label": label,
                "occurrence_count": occurrences[label],
                "affected_persona_count": len(counts[label]),
            }
            for label in counts
        ]
    )
    return frame.sort_values(["occurrence_count", "affected_persona_count"], ascending=[False, False])


def _load_manual_review_summary() -> pd.DataFrame:
    summary_path = PLOT_DATA_DIR / "manual_review_summary.csv"
    if summary_path.exists():
        return pd.read_csv(summary_path)

    rows = _load_csv(PLOT_DATA_DIR / "manual_review_packets.csv")
    buckets: Dict[str, Dict[str, float]] = {}
    for row in rows:
        priority = row.get("priority", "unknown")
        bucket = buckets.setdefault(priority, {"review_count": 0, "focus_field_total": 0})
        bucket["review_count"] += 1
        focus_count = _to_int(row.get("focus_field_count", ""))
        if focus_count <= 0:
            focus_count = len(_parse_json_list(row.get("focus_fields", "")))
        bucket["focus_field_total"] += focus_count
    frame = pd.DataFrame(
        [
            {
                "priority": key,
                "review_count": int(value["review_count"]),
                "focus_field_total": int(value["focus_field_total"]),
                "average_focus_field_count": round(value["focus_field_total"] / max(value["review_count"], 1), 2),
            }
            for key, value in buckets.items()
        ]
    )
    return frame


def generate_concept_gap_frequency_chart(top_n: int = 10) -> Dict[str, str]:
    frame = _load_concept_gap_stats().copy()
    frame = frame.sort_values(["occurrence_count", "affected_persona_count"], ascending=[False, False]).head(top_n)
    frame = frame.iloc[::-1]
    frame["label"] = frame["concept_gap_label"].astype(str).map(lambda value: value if len(value) <= 28 else f"{value[:27]}...")

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    sns.barplot(data=frame, x="occurrence_count", y="label", color=BLUE, ax=ax)
    ax.set_title("Concept-gap frequency")
    ax.set_xlabel("Occurrence count")
    ax.set_ylabel("")
    sns.despine(ax=ax)
    for patch, value in zip(ax.patches, frame["occurrence_count"]):
        ax.text(patch.get_width() + 0.05, patch.get_y() + patch.get_height() / 2, str(int(value)), va="center", ha="left", fontsize=9)
    fig.tight_layout()
    return _save_figure(fig, "concept_gap_frequency")


def generate_ablation_delta_heatmap() -> Dict[str, str]:
    frame = pd.read_csv(PLOT_DATA_DIR / "ablation_confidence_matrix.csv")
    baseline = frame["full_confidence"]
    heatmap_frame = pd.DataFrame(
        {
            VARIANT_LABELS[key]: (baseline - frame[key]).round(2)
            for key in VARIANT_ORDER
        },
        index=frame["base_bundle_id"].astype(str).str.replace("profile_bundle_", "B", regex=False).str.upper(),
    )

    fig, ax = plt.subplots(figsize=(6.8, 2.8))
    sns.heatmap(
        heatmap_frame,
        annot=True,
        fmt=".2f",
        cmap="Greys",
        cbar_kws={"label": "Confidence drop"},
        linewidths=0.5,
        linecolor="white",
        ax=ax,
    )
    ax.set_title("Ablation confidence drop")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    return _save_figure(fig, "ablation_confidence_drop")


def generate_stability_heatmap() -> Dict[str, str]:
    frame = pd.read_csv(PLOT_DATA_DIR / "stability_summary.csv")
    if "field_label" not in frame.columns:
        frame["field_label"] = frame["field_name"].map(_field_label)
    pivot = frame.pivot(index="target_id", columns="field_label", values="distinct_values").fillna(0)

    fig, ax = plt.subplots(figsize=(7.8, 3.6))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".0f",
        cmap="Greys",
        cbar_kws={"label": "Distinct values"},
        linewidths=0.5,
        linecolor="white",
        ax=ax,
    )
    ax.set_title("Stability summary")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    return _save_figure(fig, "stability_heatmap")


def export_base_profile_table() -> Dict[str, str]:
    frame = pd.read_csv(PLOT_DATA_DIR / "base_profile_metrics.csv")
    table = frame[
        [
            "persona_id",
            "overall_score",
            "confidence",
            "dropout_risk",
            "dropout_risk_score",
            "concept_gap_count",
            "weak_week_count",
        ]
    ].copy()
    table.columns = [
        "Persona",
        "Overall score",
        "Confidence",
        "Risk level",
        "Risk score",
        "Concept gaps",
        "Weak weeks",
    ]
    return _write_table_files("base_profile_summary", table)


def export_edge_case_table() -> Dict[str, str]:
    frame = pd.read_csv(PLOT_DATA_DIR / "edge_case_metrics.csv")
    frame["total_issue_count"] = frame["warning_count"] + frame["missing_field_count"] + frame["format_issue_count"]
    table = frame[
        [
            "case_id",
            "template_id",
            "confidence",
            "dropout_risk",
            "warning_count",
            "missing_field_count",
            "format_issue_count",
            "total_issue_count",
        ]
    ].sort_values("total_issue_count", ascending=False)
    table.columns = [
        "Case ID",
        "Template",
        "Confidence",
        "Risk level",
        "Warnings",
        "Missing fields",
        "Format issues",
        "Total issues",
    ]
    return _write_table_files("edge_case_summary", table)


def export_manual_review_table() -> Dict[str, str]:
    frame = _load_manual_review_summary().copy()
    if "average_focus_field_count" not in frame.columns:
        frame["average_focus_field_count"] = (frame["focus_field_total"] / frame["review_count"].clip(lower=1)).round(2)
    table = frame[
        [
            "priority",
            "review_count",
            "focus_field_total",
            "average_focus_field_count",
        ]
    ].copy()
    table.columns = [
        "Priority",
        "Review count",
        "Total focus fields",
        "Average focus fields",
    ]
    return _write_table_files("manual_review_summary", table)


def generate_manifest(files: Iterable[str]) -> str:
    manifest = {"generated_files": list(files)}
    path = OUTPUTS_DIR / "statistics_asset_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def generate_all_statistics_assets() -> Dict[str, str]:
    _configure_style()
    files: Dict[str, str] = {}
    for result in (
        generate_concept_gap_frequency_chart(),
        generate_ablation_delta_heatmap(),
        generate_stability_heatmap(),
        export_base_profile_table(),
        export_edge_case_table(),
        export_manual_review_table(),
    ):
        files.update(result)
    files["manifest"] = generate_manifest(files.values())
    return files


if __name__ == "__main__":
    print(json.dumps(generate_all_statistics_assets(), ensure_ascii=False, indent=2))
