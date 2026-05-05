from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import matplotlib.pyplot as plt
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
PLOT_DATA_DIR = OUTPUTS_DIR / "plot_data"
CHARTS_DIR = OUTPUTS_DIR / "charts"

TEXT = "#222222"
MUTED = "#666666"
GRID = "#dddddd"
SPINE = "#bbbbbb"
BLUE = "#4c78a8"
TEAL = "#72b7b2"
RED = "#e45756"
GRAY = "#7f7f7f"
GREEN = "#54a24b"
YELLOW = "#eeca3b"
HEATMAP = ["#f7f7f7", "#d9e2f3", "#8aa7d6", "#4c78a8"]

PERSONA_LABELS = {
    "steady_mastery_builder": "Steady Mastery",
    "low_activity_risk": "Low Activity Risk",
    "deadline_crammer": "Deadline Crammer",
    "visual_practice_seeker": "Visual Practice",
}

VARIANT_ORDER = [
    "full_confidence",
    "no_dialogue_text_confidence",
    "no_answer_records_confidence",
    "no_resource_usage_confidence",
    "no_learning_records_confidence",
    "id_only_confidence",
]
VARIANT_LABELS = {
    "full_confidence": "Full",
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
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [
                "Times New Roman",
                "Noto Serif CJK SC",
                "SimSun",
                "STSong",
                "DejaVu Serif",
            ],
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "axes.edgecolor": SPINE,
            "axes.linewidth": 0.8,
            "axes.labelcolor": TEXT,
            "xtick.color": TEXT,
            "ytick.color": TEXT,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "grid.alpha": 1.0,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
        }
    )


def _load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: str, default: int = 0) -> int:
    return int(round(_to_float(value, float(default))))


def _save_figure(fig: plt.Figure, name: str) -> str:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{name}.svg"
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def _persona_label(value: str) -> str:
    return PERSONA_LABELS.get(value, value.replace("_", " ").title())


def _bundle_label(value: str) -> str:
    return value.replace("profile_bundle_", "B").upper()


def _set_spines(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(SPINE)
    ax.spines["bottom"].set_color(SPINE)


def _field_label(value: str) -> str:
    return FIELD_LABELS.get(value, value.replace("_", " ").title())


def generate_base_profile_overview() -> str:
    rows = _load_csv(PLOT_DATA_DIR / "base_profile_metrics.csv")
    labels = [_persona_label(row["persona_id"]) for row in rows]
    overall = [_to_float(row["overall_score"]) for row in rows]
    confidence = [_to_float(row["confidence"]) for row in rows]
    risk = [_to_float(row["dropout_risk_score"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    y = np.arange(len(labels))
    offsets = np.array([-0.18, 0.0, 0.18])

    ax.scatter(overall, y + offsets[0], s=36, color=BLUE, label="Overall score", zorder=3)
    ax.scatter(confidence, y + offsets[1], s=36, color=TEAL, label="Confidence", zorder=3)
    ax.scatter(risk, y + offsets[2], s=36, color=RED, label="Risk score", zorder=3)

    for values, offset, color in [(overall, offsets[0], BLUE), (confidence, offsets[1], TEAL), (risk, offsets[2], RED)]:
        for value, ypos in zip(values, y + offset):
            ax.hlines(ypos, 0, value, color=color, linewidth=0.9, alpha=0.65, zorder=2)

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Score")
    ax.set_title("Base profile overview")
    ax.grid(axis="x")
    _set_spines(ax)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=3,
        fontsize=9,
        handletextpad=0.5,
        columnspacing=1.2,
    )
    ax.invert_yaxis()
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.28)
    return _save_figure(fig, "base_profile_overview")


def generate_ablation_confidence_chart() -> str:
    rows = _load_csv(PLOT_DATA_DIR / "ablation_confidence_matrix.csv")
    data = np.array(
        [[_to_float(row[key]) for key in VARIANT_ORDER] for row in rows],
        dtype=float,
    )
    row_labels = [_bundle_label(row["base_bundle_id"]) for row in rows]
    col_labels = [VARIANT_LABELS[key] for key in VARIANT_ORDER]

    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    im = ax.imshow(data, cmap="Blues", vmin=0.0, vmax=1.0, aspect="auto")
    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=20, ha="right")
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_title("Ablation confidence matrix")

    for row_index in range(data.shape[0]):
        for col_index in range(data.shape[1]):
            value = data[row_index, col_index]
            color = "white" if value >= 0.62 else TEXT
            ax.text(col_index, row_index, f"{value:.2f}", ha="center", va="center", fontsize=9, color=color)

    _set_spines(ax)
    cbar = fig.colorbar(im, ax=ax, fraction=0.048, pad=0.04)
    cbar.ax.set_ylabel("Confidence", rotation=90)
    fig.tight_layout()
    return _save_figure(fig, "ablation_confidence")


def generate_edge_case_chart() -> str:
    rows = _load_csv(PLOT_DATA_DIR / "edge_case_metrics.csv")
    labels = [row["case_id"].replace("edge_", "").replace("_", " ") for row in rows]
    warning_count = np.array([_to_float(row["warning_count"]) for row in rows], dtype=float)
    missing_count = np.array([_to_float(row["missing_field_count"]) for row in rows], dtype=float)
    format_count = np.array([_to_float(row["format_issue_count"]) for row in rows], dtype=float)

    order = np.argsort(-(warning_count + missing_count + format_count))
    labels = [labels[index] for index in order]
    warning_count = warning_count[order]
    missing_count = missing_count[order]
    format_count = format_count[order]

    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    y = np.arange(len(labels))
    ax.barh(y, warning_count, color=GRAY, label="Warnings")
    ax.barh(y, missing_count, left=warning_count, color=BLUE, label="Missing fields")
    ax.barh(y, format_count, left=warning_count + missing_count, color=RED, label="Format issues")

    totals = warning_count + missing_count + format_count
    for total, ypos in zip(totals, y):
        ax.text(total + 0.08, ypos, f"{int(total)}", va="center", ha="left", fontsize=9, color=TEXT)

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Issue count")
    ax.set_title("Edge-case issue counts")
    ax.grid(axis="x")
    _set_spines(ax)
    ax.legend(loc="lower right", ncol=3, fontsize=9)
    ax.invert_yaxis()
    fig.tight_layout()
    return _save_figure(fig, "edge_case_warnings")


def generate_stability_heatmap() -> str:
    rows = _load_csv(PLOT_DATA_DIR / "stability_summary.csv")
    targets: List[str] = []
    fields: List[str] = []
    label_map: Dict[str, str] = {}
    for row in rows:
        if row["target_id"] not in targets:
            targets.append(row["target_id"])
        if row["field_name"] not in fields:
            fields.append(row["field_name"])
        label_map[row["field_name"]] = row.get("field_label") or _field_label(row["field_name"])

    data = np.zeros((len(targets), len(fields)), dtype=float)
    for row in rows:
        target_index = targets.index(row["target_id"])
        field_index = fields.index(row["field_name"])
        data[target_index, field_index] = _to_int(row["distinct_values"])

    fig, ax = plt.subplots(figsize=(8.3, 3.6))
    im = ax.imshow(data, cmap="Greys", vmin=1, vmax=max(3, int(data.max(initial=1))), aspect="auto")
    ax.set_xticks(np.arange(len(fields)))
    ax.set_xticklabels([label_map[field] for field in fields], rotation=22, ha="right")
    ax.set_yticks(np.arange(len(targets)))
    ax.set_yticklabels(targets)
    ax.set_title("Stability heatmap")

    for row_index in range(data.shape[0]):
        for col_index in range(data.shape[1]):
            value = int(data[row_index, col_index])
            color = "white" if value >= 3 else TEXT
            ax.text(col_index, row_index, str(value), ha="center", va="center", fontsize=9, color=color)

    _set_spines(ax)
    cbar = fig.colorbar(im, ax=ax, fraction=0.048, pad=0.04)
    cbar.ax.set_ylabel("Distinct values", rotation=90)
    fig.tight_layout()
    return _save_figure(fig, "stability_heatmap")


def generate_manifest(files: Iterable[str]) -> str:
    manifest = {"generated_files": list(files)}
    path = CHARTS_DIR / "chart_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def generate_all_charts() -> Dict[str, str]:
    _configure_style()
    files = {
        "base_profile_overview": generate_base_profile_overview(),
        "ablation_confidence": generate_ablation_confidence_chart(),
        "edge_case_warnings": generate_edge_case_chart(),
        "stability_heatmap": generate_stability_heatmap(),
    }
    files["manifest"] = generate_manifest(files.values())
    return files


if __name__ == "__main__":
    print(json.dumps(generate_all_charts(), ensure_ascii=False, indent=2))
