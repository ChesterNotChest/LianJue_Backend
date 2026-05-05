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


from scripts.rag_eval_common import call_json_llm, get_default_model, get_output_dir, load_json_if_exists, write_json


VALID_STATUSES = {"hit", "miss", "dirty"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LLM judge for recall evaluation and export CSV reports.")
    parser.add_argument(
        "--input-json",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs" / "recall_eval.json"),
        help="Path to retrieval-only recall json.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs"),
        help="Directory for output reports.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Reuse existing judge result file and only fill missing cases.",
    )
    return parser.parse_args()


def normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_STATUSES else "miss"


def judge_case(model: Any, case: dict[str, Any]) -> dict[str, Any]:
    paragraphs = case.get("paragraphs", []) or []
    system_prompt = """
你是一个用于汇报材料的 RAG 召回评估器。
请基于“是否命中了回答该问题所需的关键证据”来判断，不要用过于苛刻的标准。

判定原则：
- `hit`：已命中关键知识点，足以支持一个合理回答，即使资料不是完整教材式展开，也算命中。
- `miss`：检索内容与问题关系弱，或缺少回答问题所需的关键证据。
- `dirty`：问题文本或检索内容明显损坏、乱码严重、结构残缺，已无法公平判断。

请一次性分别判断 Top1、Top3、Top5。
如果某条样本整体就是 dirty，则 Top1/Top3/Top5 都应该优先判成 dirty。

严格只输出 JSON，不要输出其他说明：
{
  "dirty": false,
  "dirty_reason": "",
  "top1_status": "hit|miss|dirty",
  "top1_reason": "",
  "top3_status": "hit|miss|dirty",
  "top3_reason": "",
  "top5_status": "hit|miss|dirty",
  "top5_reason": ""
}
""".strip()

    user_prompt = json.dumps(
        {
            "case_id": case.get("case_id"),
            "question": case.get("content"),
            "top1_context": paragraphs[:1],
            "top3_context": paragraphs[:3],
            "top5_context": paragraphs[:5],
        },
        ensure_ascii=False,
    )
    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="dirty")

    dirty = bool(parsed.get("dirty", False))
    dirty_reason = str(parsed.get("dirty_reason", "")).strip()
    top1_status = normalize_status(parsed.get("top1_status"))
    top3_status = normalize_status(parsed.get("top3_status"))
    top5_status = normalize_status(parsed.get("top5_status"))

    if dirty:
        top1_status = "dirty"
        top3_status = "dirty"
        top5_status = "dirty"

    return {
        "dirty": dirty or top1_status == "dirty" or top3_status == "dirty" or top5_status == "dirty",
        "dirty_reason": dirty_reason,
        "top1_status": top1_status,
        "top1_reason": str(parsed.get("top1_reason", "")).strip(),
        "top3_status": top3_status,
        "top3_reason": str(parsed.get("top3_reason", "")).strip(),
        "top5_status": top5_status,
        "top5_reason": str(parsed.get("top5_reason", "")).strip(),
        "judge_raw": parsed.get("_raw", ""),
    }


def merge_cases_by_id(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for item in existing:
        merged[int(item["case_id"])] = item
    for item in incoming:
        merged[int(item["case_id"])] = item
    return [merged[key] for key in sorted(merged)]


def build_summary(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []
    for top_k in ("top1", "top3", "top5"):
        hit_count = sum(1 for case in cases if case.get(f"{top_k}_status") == "hit")
        miss_count = sum(1 for case in cases if case.get(f"{top_k}_status") == "miss")
        dirty_count = sum(1 for case in cases if case.get(f"{top_k}_status") == "dirty")
        valid_count = hit_count + miss_count
        hit_rate = round(hit_count / valid_count, 4) if valid_count else 0.0
        summary_rows.append(
            {
                "top_k": top_k.upper(),
                "hit_count": hit_count,
                "miss_count": miss_count,
                "dirty_count": dirty_count,
                "hit_rate": hit_rate,
            }
        )
    return summary_rows


def write_case_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "case_id",
                "case_type",
                "case_content",
                "dirty",
                "dirty_reason",
                "top1_status",
                "top1_reason",
                "top3_status",
                "top3_reason",
                "top5_status",
                "top5_reason",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.get("case_id"),
                    row.get("case_type"),
                    row.get("content"),
                    row.get("dirty"),
                    row.get("dirty_reason"),
                    row.get("top1_status"),
                    row.get("top1_reason"),
                    row.get("top3_status"),
                    row.get("top3_reason"),
                    row.get("top5_status"),
                    row.get("top5_reason"),
                ]
            )


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["top_k", "hit_count", "miss_count", "dirty_count", "hit_rate"])
        for row in rows:
            writer.writerow(
                [
                    row["top_k"],
                    row["hit_count"],
                    row["miss_count"],
                    row["dirty_count"],
                    row["hit_rate"],
                ]
            )


def main() -> None:
    args = parse_args()
    output_dir = get_output_dir(args.output_dir)
    input_payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    source_cases = input_payload.get("cases", [])

    json_path = output_dir / "recall_llm_judge_report.json"
    existing_payload = load_json_if_exists(json_path, {"summary": {}, "cases": []}) if args.append else {"summary": {}, "cases": []}
    existing_cases_by_id = {int(case["case_id"]): case for case in existing_payload.get("cases", [])}

    model = get_default_model()
    judged_cases: list[dict[str, Any]] = []

    for source_case in source_cases:
        case_id = int(source_case.get("case_id"))
        if case_id in existing_cases_by_id:
            judged_cases.append(existing_cases_by_id[case_id])
            continue

        judge_result = judge_case(model, source_case)
        judged_case = {
            "case_id": case_id,
            "case_type": source_case.get("case_type"),
            "content": source_case.get("content"),
            **judge_result,
        }
        judged_cases.append(judged_case)
        merged_cases = merge_cases_by_id(existing_payload.get("cases", []), judged_cases)
        write_json(
            json_path,
            {
                "summary": existing_payload.get("summary", {}),
                "cases": merged_cases,
            },
        )

    judged_cases = merge_cases_by_id(existing_payload.get("cases", []), judged_cases)
    summary_rows = build_summary(judged_cases)

    payload = {
        "summary": {
            "source_json": args.input_json,
            "case_count": len(judged_cases),
            "topk_summary": summary_rows,
        },
        "cases": judged_cases,
    }
    write_json(json_path, payload)
    write_case_csv(output_dir / "recall_llm_judge_cases.csv", judged_cases)
    write_summary_csv(output_dir / "recall_llm_judge_summary.csv", summary_rows)


if __name__ == "__main__":
    main()
