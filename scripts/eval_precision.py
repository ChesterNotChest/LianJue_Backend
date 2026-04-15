from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from rag_eval_common import (
    build_knowlion,
    build_rag_answer,
    chunked,
    filter_cases,
    get_default_model,
    get_output_dir,
    judge_precision,
    load_json_if_exists,
    load_test_cases,
    merge_case_records,
    write_json,
    write_markdown_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate answer precision with RAG top-k contexts.")
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
    parser.add_argument(
        "--top-k",
        nargs="*",
        type=int,
        default=[1, 3],
        help="Top-k values for precision evaluation.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N cases.")
    parser.add_argument(
        "--phase",
        choices=["all", "generate", "judge"],
        default="all",
        help="Run answer generation only, judge only, or both.",
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
    model = get_default_model()
    summary_rows: list[list[str]] = []

    if args.phase in ("all", "generate"):
        cases = filter_cases(load_test_cases(args.cases_path), args.case_ids, args.offset, args.limit)
        knowlion = build_knowlion(args.graph_name)
        for top_k in args.top_k:
            json_path = output_dir / f"precision_top{top_k}.json"
            existing_payload = load_json_if_exists(json_path, {"summary": {}, "cases": []}) if args.append else {"summary": {}, "cases": []}
            case_results: list[dict] = existing_payload.get("cases", [])
            new_results: list[dict] = []
            for batch in chunked(cases, args.batch_size):
                for case in batch:
                    answer_bundle = build_rag_answer(knowlion, model, case.content, top_k=top_k)
                    new_results.append(
                        {
                            **asdict(case),
                            "top_k": top_k,
                            "answer": answer_bundle["answer"],
                            "judge": None,
                            "paragraphs": answer_bundle["paragraphs"],
                            "reasoning_paths": answer_bundle["reasoning_paths"],
                            "search_result": answer_bundle["search_result"],
                            "llm_result": answer_bundle["llm_result"],
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
                            "top_k": top_k,
                            "status": "generated",
                            "offset": args.offset,
                            "limit": args.limit,
                            "append": args.append,
                        },
                        "cases": case_results,
                    },
                )
                new_results = []

            table_rows = [[case["case_id"], case["content"], case["answer"]] for case in case_results]
            write_markdown_table(
                output_dir / f"precision_top{top_k}.md",
                headers=["Case ID", "Case Content", "Answer"],
                rows=table_rows,
                title=f"Precision Evaluation Top{top_k} Answers",
                intro_lines=[
                    f"- Graph: `{args.graph_name}`",
                    f"- Case count: `{len(case_results)}`",
                    f"- Batch size: `{args.batch_size}`",
                    "- Phase: `generated`",
                ],
            )

    if args.phase in ("all", "judge"):
        for top_k in args.top_k:
            json_path = output_dir / f"precision_top{top_k}.json"
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

            for batch in chunked(selected_case_results, args.batch_size):
                for case in batch:
                    judge = judge_precision(
                        model,
                        question=case.get("content", ""),
                        answer=case.get("answer", ""),
                        contexts=case.get("paragraphs", []) or [],
                    )
                    case["judge"] = judge
                all_case_results = merge_case_records(all_case_results, batch, key_fields=("case_id",))
                write_json(json_path, {"summary": payload.get("summary", {}), "cases": all_case_results})

            precise_count = sum(
                1
                for case in all_case_results
                if (case.get("judge") or {}).get("is_precise")
            )
            total = len(all_case_results) or 1
            summary = {
                "graph_name": args.graph_name,
                "cases_path": args.cases_path,
                "case_count": len(all_case_results),
                "top_k": top_k,
                "precision_rate": precise_count / total,
                "precise_count": precise_count,
                "status": "judged",
            }
            summary_rows.append(
                [f"Top{top_k}", len(all_case_results), precise_count, f"{summary['precision_rate']:.2%}"]
            )
            write_json(json_path, {"summary": summary, "cases": all_case_results})

            table_rows = [[case["case_id"], case["content"], case["answer"]] for case in all_case_results]
            write_markdown_table(
                output_dir / f"precision_top{top_k}.md",
                headers=["Case ID", "Case Content", "Answer"],
                rows=table_rows,
                title=f"Precision Evaluation Top{top_k} Answers",
                intro_lines=[
                    f"- Graph: `{args.graph_name}`",
                    f"- Case count: `{len(all_case_results)}`",
                    f"- Batch size: `{args.batch_size}`",
                    f"- Judge precision rate: `{summary['precision_rate']:.2%}`",
                ],
            )

        if summary_rows:
            write_markdown_table(
                output_dir / "precision_summary.md",
                headers=["Metric", "Case Count", "Precise Count", "Precision Rate"],
                rows=summary_rows,
                title="Precision Evaluation Summary",
                intro_lines=[f"- Graph: `{args.graph_name}`", f"- Batch size: `{args.batch_size}`"],
            )


if __name__ == "__main__":
    main()
