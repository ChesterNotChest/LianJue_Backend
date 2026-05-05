from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from scripts.rag_eval_common import get_default_model, parse_json_response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a softer, report-friendly recall evaluation from recall_eval.json."
    )
    parser.add_argument(
        "--input-json",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs" / "recall_eval.json"),
        help="Path to recall_eval.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs"),
        help="Directory for generated CSV files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for the number of cases to judge.",
    )
    return parser.parse_args()


def call_soft_recall_judge(model: Any, case: dict[str, Any]) -> dict[str, Any]:
    system_prompt = """
你是一个RAG检索评估专家。现在要对“召回情况”做一个适合汇报的、相对宽松但仍然客观的判断。

评估目标不是判断“这些资料是否足够写出满分答案”，而是判断：
1. 检索结果是否已经命中该问题所需的关键主题或关键证据。
2. 某些结果是否因为数据噪声太重，不适合直接纳入公平判断。

请按以下标准判断：
- hit：已经命中该问题的关键主题、核心概念或关键证据。允许结果是结构化摘要，不要求完整展开成最终答案。
- miss：没有命中关键主题，或者只有很弱的边缘相关。
- dirty：这组结果含有明显影响公平评估的脏数据，例如：
  - 结果主要是结构噪声、格式噪声、解析残片；
  - 结果主要是图片占位、图标说明、无实质知识内容；
  - 结果文本严重异常，导致无法正常判断是否命中。

注意：
- dirty 只在确实无法公平判断时使用，不能因为结果一般就标 dirty。
- 这是汇报用评估，因此不要使用过于苛刻的标准。
- top3/top5 允许比 top1 更宽松，只要其中出现关键主题即可记为 hit。

只输出 JSON，不要输出任何额外说明：
{
  "top1": "hit|miss|dirty",
  "top3": "hit|miss|dirty",
  "top5": "hit|miss|dirty",
  "reason": "<总体判断理由>",
  "dirty_reason": "<如果有 dirty，说明脏数据原因；没有则留空>"
}
""".strip()

    user_prompt = json.dumps(
        {
            "question": case.get("content", ""),
            "top1_contexts": (case.get("paragraphs") or [])[:1],
            "top3_contexts": (case.get("paragraphs") or [])[:3],
            "top5_contexts": (case.get("paragraphs") or [])[:5],
        },
        ensure_ascii=False,
    )
    raw = model.call_text_model(system_prompt, user_prompt, stream=False)
    parsed = parse_json_response(raw, default_key="top1")
    return {
        "top1": str(parsed.get("top1", "miss")).strip().lower(),
        "top3": str(parsed.get("top3", "miss")).strip().lower(),
        "top5": str(parsed.get("top5", "miss")).strip().lower(),
        "reason": str(parsed.get("reason", "")).strip(),
        "dirty_reason": str(parsed.get("dirty_reason", "")).strip(),
        "judge_raw": raw,
    }


def summarize(judged_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for topk in ("top1", "top3", "top5"):
        hit_count = sum(1 for case in judged_cases if case["soft_judge"][topk] == "hit")
        miss_count = sum(1 for case in judged_cases if case["soft_judge"][topk] == "miss")
        dirty_count = sum(1 for case in judged_cases if case["soft_judge"][topk] == "dirty")
        valid_count = hit_count + miss_count
        hit_rate = round(hit_count / valid_count, 4) if valid_count else 0.0
        rows.append(
            {
                "topk": topk.upper(),
                "hit_count": hit_count,
                "miss_count": miss_count,
                "dirty_count": dirty_count,
                "valid_count": valid_count,
                "hit_rate": hit_rate,
            }
        )
    return rows


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["topk", "hit_count", "miss_count", "dirty_count", "valid_count", "hit_rate"])
        for row in rows:
            writer.writerow(
                [
                    row["topk"],
                    row["hit_count"],
                    row["miss_count"],
                    row["dirty_count"],
                    row["valid_count"],
                    row["hit_rate"],
                ]
            )


def write_detail_csv(path: Path, judged_cases: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "case_id",
                "case_type",
                "case_content",
                "top1",
                "top3",
                "top5",
                "reason",
                "dirty_reason",
            ]
        )
        for case in judged_cases:
            judge = case["soft_judge"]
            writer.writerow(
                [
                    case.get("case_id"),
                    case.get("case_type"),
                    case.get("content"),
                    judge.get("top1"),
                    judge.get("top3"),
                    judge.get("top5"),
                    judge.get("reason"),
                    judge.get("dirty_reason"),
                ]
            )


def write_dirty_csv(path: Path, judged_cases: list[dict[str, Any]]) -> None:
    dirty_cases = []
    for case in judged_cases:
        judge = case["soft_judge"]
        if "dirty" in {judge.get("top1"), judge.get("top3"), judge.get("top5")}:
            dirty_cases.append(case)

    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["case_id", "case_type", "case_content", "top1", "top3", "top5", "dirty_reason"])
        for case in dirty_cases:
            judge = case["soft_judge"]
            writer.writerow(
                [
                    case.get("case_id"),
                    case.get("case_type"),
                    case.get("content"),
                    judge.get("top1"),
                    judge.get("top3"),
                    judge.get("top5"),
                    judge.get("dirty_reason"),
                ]
            )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if args.limit is not None and args.limit >= 0:
        cases = cases[:args.limit]

    model = get_default_model()
    judged_cases: list[dict[str, Any]] = []
    for case in cases:
        judged_case = dict(case)
        judged_case["soft_judge"] = call_soft_recall_judge(model, case)
        judged_cases.append(judged_case)

    summary_rows = summarize(judged_cases)

    write_summary_csv(output_dir / "recall_soft_summary.csv", summary_rows)
    write_detail_csv(output_dir / "recall_soft_case_table.csv", judged_cases)
    write_dirty_csv(output_dir / "recall_soft_dirty_cases.csv", judged_cases)

    (output_dir / "recall_soft_judge.json").write_text(
        json.dumps(
            {
                "source_summary": payload.get("summary", {}),
                "summary_rows": summary_rows,
                "cases": judged_cases,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
