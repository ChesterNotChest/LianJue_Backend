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


VALID_STATUSES = {"correct", "incorrect", "dirty"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LLM judge for precision evaluation and export CSV reports.")
    parser.add_argument(
        "--top1-json",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs" / "precision_top1.json"),
        help="Path to Top1 answer json.",
    )
    parser.add_argument(
        "--top3-json",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs" / "precision_top3.json"),
        help="Path to Top3 answer json.",
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
    return text if text in VALID_STATUSES else "incorrect"


def load_cases(path: str) -> dict[int, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    return {int(case["case_id"]): case for case in cases}


def judge_case(model: Any, top1_case: dict[str, Any], top3_case: dict[str, Any]) -> dict[str, Any]:
    system_prompt = """
你是一个用于汇报材料的 RAG 回答准确率评估器。
请基于问题、回答、以及检索到的资料，判断回答是否正确。
请保持客观，但不要使用过于苛刻的标准：
- 如果回答抓住了主要知识点，结论基本正确，即可判为 `correct`
- 只有在回答明显错误、偏题、或关键事实不成立时，才判为 `incorrect`
- 只有在问题/回答/上下文本身明显损坏、乱码严重、或结构残缺到无法公平判断时，才判为 `dirty`

请一次性判断 Top1 回答和 Top3 回答。
如果整条样本整体就是 dirty，则 Top1/Top3 都应优先判成 dirty。

严格只输出 JSON，不要输出其他说明：
{
  "dirty": false,
  "dirty_reason": "",
  "top1_status": "correct|incorrect|dirty",
  "top1_reason": "",
  "top3_status": "correct|incorrect|dirty",
  "top3_reason": ""
}
""".strip()

    user_prompt = json.dumps(
        {
            "case_id": top1_case.get("case_id"),
            "question": top1_case.get("content"),
            "top1_answer": top1_case.get("answer"),
            "top1_context": top1_case.get("paragraphs", []) or [],
            "top3_answer": top3_case.get("answer"),
            "top3_context": top3_case.get("paragraphs", []) or [],
        },
        ensure_ascii=False,
    )

    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="dirty")
    dirty = bool(parsed.get("dirty", False))
    dirty_reason = str(parsed.get("dirty_reason", "")).strip()

    top1_status = normalize_status(parsed.get("top1_status"))
    top3_status = normalize_status(parsed.get("top3_status"))
    if dirty:
        top1_status = "dirty"
        top3_status = "dirty"

    return {
        "dirty": dirty or top1_status == "dirty" or top3_status == "dirty",
        "dirty_reason": dirty_reason,
        "top1_status": top1_status,
        "top1_reason": str(parsed.get("top1_reason", "")).strip(),
        "top3_status": top3_status,
        "top3_reason": str(parsed.get("top3_reason", "")).strip(),
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
    rows: list[dict[str, Any]] = []
    for top_k in ("top1", "top3"):
        correct_count = sum(1 for case in cases if case.get(f"{top_k}_status") == "correct")
        incorrect_count = sum(1 for case in cases if case.get(f"{top_k}_status") == "incorrect")
        dirty_count = sum(1 for case in cases if case.get(f"{top_k}_status") == "dirty")
        valid_count = correct_count + incorrect_count
        accuracy_rate = round(correct_count / valid_count, 4) if valid_count else 0.0
        rows.append(
            {
                "top_k": top_k.upper(),
                "correct_count": correct_count,
                "incorrect_count": incorrect_count,
                "dirty_count": dirty_count,
                "accuracy_rate": accuracy_rate,
            }
        )
    return rows


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
                "top1_answer",
                "top1_status",
                "top1_reason",
                "top3_answer",
                "top3_status",
                "top3_reason",
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
                    row.get("top1_answer"),
                    row.get("top1_status"),
                    row.get("top1_reason"),
                    row.get("top3_answer"),
                    row.get("top3_status"),
                    row.get("top3_reason"),
                ]
            )


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["top_k", "correct_count", "incorrect_count", "dirty_count", "accuracy_rate"])
        for row in rows:
            writer.writerow(
                [
                    row["top_k"],
                    row["correct_count"],
                    row["incorrect_count"],
                    row["dirty_count"],
                    row["accuracy_rate"],
                ]
            )


def main() -> None:
    args = parse_args()
    output_dir = get_output_dir(args.output_dir)

    top1_cases = load_cases(args.top1_json)
    top3_cases = load_cases(args.top3_json)
    common_case_ids = sorted(set(top1_cases) & set(top3_cases))

    json_path = output_dir / "precision_llm_judge_report.json"
    existing_payload = load_json_if_exists(json_path, {"summary": {}, "cases": []}) if args.append else {"summary": {}, "cases": []}
    existing_cases_by_id = {int(case["case_id"]): case for case in existing_payload.get("cases", [])}

    model = get_default_model()
    judged_cases: list[dict[str, Any]] = []

    for case_id in common_case_ids:
        if case_id in existing_cases_by_id:
            judged_cases.append(existing_cases_by_id[case_id])
            continue

        top1_case = top1_cases[case_id]
        top3_case = top3_cases[case_id]
        judge_result = judge_case(model, top1_case, top3_case)
        judged_case = {
            "case_id": case_id,
            "case_type": top1_case.get("case_type"),
            "content": top1_case.get("content"),
            "top1_answer": top1_case.get("answer"),
            "top3_answer": top3_case.get("answer"),
            **judge_result,
        }
        judged_cases.append(judged_case)
        merged_cases = merge_cases_by_id(existing_payload.get("cases", []), judged_cases)
        write_json(json_path, {"summary": existing_payload.get("summary", {}), "cases": merged_cases})

    judged_cases = merge_cases_by_id(existing_payload.get("cases", []), judged_cases)
    summary_rows = build_summary(judged_cases)
    payload = {
        "summary": {
            "top1_source_json": args.top1_json,
            "top3_source_json": args.top3_json,
            "case_count": len(judged_cases),
            "topk_summary": summary_rows,
        },
        "cases": judged_cases,
    }

    write_json(json_path, payload)
    write_case_csv(output_dir / "precision_llm_judge_cases.csv", judged_cases)
    write_summary_csv(output_dir / "precision_llm_judge_summary.csv", summary_rows)


if __name__ == "__main__":
    main()
