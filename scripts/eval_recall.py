from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from rag_eval_common import (
    chunked,
    filter_cases,
    get_default_model,
    get_output_dir,
    judge_recall,
    load_json_if_exists,
    load_test_cases,
    merge_case_records,
    retrieve_with_rag,
    write_json,
    write_markdown_table,
    build_knowlion,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval recall@1/@3/@5 for KnowLion.")
    parser.add_argument("--graph-name", required=True, help="Graph name used by KnowLion.")
    parser.add_argument(
        "--cases-path",
        default=str(Path(__file__).resolve().parents[1] / "\u6d4b\u8bd5\u7528\u4f8b.md"),
        help="Path to test cases markdown file.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs"),
        help="Directory for markdown/json outputs.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N cases.")
    parser.add_argument(
        "--phase",
        choices=["all", "retrieve", "judge"],
        default="all",
        help="Run retrieval only, judge only, or both.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Process and persist results in batches.",
    )
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N filtered cases.")
    parser.add_argument("--append", action="store_true", help="Append/merge into existing result file.")
    parser.add_argument(
        "--case-ids",
        nargs="*",
        type=int,
        default=None,
        help="Only run specific case ids.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = get_output_dir(args.output_dir)
    json_path = output_dir / "recall_eval.json"
    model = get_default_model()

    if args.phase in ("all", "retrieve"):
        cases = filter_cases(load_test_cases(args.cases_path), args.case_ids, args.offset, args.limit)
        knowlion = build_knowlion(args.graph_name)
        existing_payload = load_json_if_exists(json_path, {"summary": {}, "cases": []}) if args.append else {"summary": {}, "cases": []}
        case_results: list[dict] = existing_payload.get("cases", [])
        new_results: list[dict] = []
        for batch in chunked(cases, args.batch_size):
            for case in batch:
                retrieval = retrieve_with_rag(knowlion, case.content, top_k=5)
                new_results.append(
                    {
                        **asdict(case),
                        "paragraphs": retrieval["paragraphs"],
                        "reasoning_paths": retrieval["reasoning_paths"],
                        "search_result": retrieval["search_result"],
                        "recall": {},
                    }
                )
            case_results = merge_case_records(case_results, new_results, key_fields=("case_id",))
            write_json(
                json_path,
                {
                    "summary": {
                        "graph_name": args.graph_name,
                        "cases_path": args.cases_path,
                        "case_count": len(case_results),
                        "status": "retrieved",
                        "offset": args.offset,
                        "limit": args.limit,
                        "append": args.append,
                    },
                    "cases": case_results,
                },
            )
            new_results = []

    if args.phase in ("all", "judge"):
        payload = __import__("json").loads(json_path.read_text(encoding="utf-8"))
        all_case_results = payload.get("cases", [])
        selected_case_results = all_case_results
        if args.case_ids:
            case_id_set = set(args.case_ids)
            selected_case_results = [case for case in selected_case_results if case.get("case_id") in case_id_set]
        if args.offset and args.offset > 0:
            selected_case_results = selected_case_results[args.offset:]
        if args.limit is not None and args.limit >= 0:
            selected_case_results = selected_case_results[:args.limit]

        hit_counter = {1: 0, 3: 0, 5: 0}
        for batch in chunked(selected_case_results, args.batch_size):
            for case in batch:
                paragraphs = case.get("paragraphs", []) or []
                recall_result: dict[str, dict] = {}
                for top_k in (1, 3, 5):
                    judge = judge_recall(model, case.get("content", ""), paragraphs[:top_k])
                    recall_result[f"top{top_k}"] = judge
                    if judge["hit"]:
                        hit_counter[top_k] += 1
                case["recall"] = recall_result
            all_case_results = merge_case_records(all_case_results, batch, key_fields=("case_id",))
            write_json(json_path, {"summary": payload.get("summary", {}), "cases": all_case_results})

        total = len(all_case_results) or 1
        hit_counter = {1: 0, 3: 0, 5: 0}
        for case in all_case_results:
            for top_k in (1, 3, 5):
                if case.get("recall", {}).get(f"top{top_k}", {}).get("hit"):
                    hit_counter[top_k] += 1
        summary = {
            "graph_name": args.graph_name,
            "cases_path": args.cases_path,
            "case_count": len(all_case_results),
            "recall_at_1": hit_counter[1] / total,
            "recall_at_3": hit_counter[3] / total,
            "recall_at_5": hit_counter[5] / total,
            "hit_counter": hit_counter,
            "status": "judged",
        }
        write_json(json_path, {"summary": summary, "cases": all_case_results})

        table_rows = [
            [
                case.get("case_id"),
                case.get("content"),
                "hit" if case.get("recall", {}).get("top1", {}).get("hit") else "miss",
                "hit" if case.get("recall", {}).get("top3", {}).get("hit") else "miss",
                "hit" if case.get("recall", {}).get("top5", {}).get("hit") else "miss",
            ]
            for case in all_case_results
        ]
        write_markdown_table(
            output_dir / "recall_eval.md",
            headers=["Case ID", "Case Content", "Top1", "Top3", "Top5"],
            rows=table_rows,
            title="Recall Evaluation",
            intro_lines=[
                f"- Graph: `{args.graph_name}`",
                f"- Case count: `{len(all_case_results)}`",
                f"- Batch size: `{args.batch_size}`",
                f"- Recall@1: `{summary['recall_at_1']:.2%}`",
                f"- Recall@3: `{summary['recall_at_3']:.2%}`",
                f"- Recall@5: `{summary['recall_at_5']:.2%}`",
            ],
        )


if __name__ == "__main__":
    main()
