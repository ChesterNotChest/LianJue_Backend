from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_eval_common import (
    build_knowlion,
    build_plain_answer,
    build_rag_answer,
    chunked,
    get_default_model,
    get_output_dir,
    judge_hallucination,
    load_json_if_exists,
    load_test_cases,
    merge_case_records,
    write_json,
    write_markdown_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate hallucination for no-RAG vs with-RAG answers.")
    parser.add_argument("--graph-name", default=None, help="Graph name used when RAG results must be regenerated.")
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
        "--rag-results",
        default=None,
        help="Precision result json to reuse. Defaults to precision_top3.json under output dir.",
    )
    parser.add_argument(
        "--rag-top-k",
        type=int,
        default=3,
        help="Top-k used when regenerating RAG answers.",
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
    return parser.parse_args()


def load_rag_cases(rag_results_path: Path) -> list[dict]:
    payload = json.loads(rag_results_path.read_text(encoding="utf-8"))
    return payload.get("cases", []) if isinstance(payload, dict) else []


def build_rag_cases_from_scratch(
    graph_name: str,
    cases_path: str,
    rag_top_k: int,
    limit: int | None,
) -> list[dict]:
    cases = load_test_cases(cases_path)
    if limit is not None and limit >= 0:
        cases = cases[:limit]

    model = get_default_model()
    knowlion = build_knowlion(graph_name)
    built_cases: list[dict] = []
    for case in cases:
        answer_bundle = build_rag_answer(knowlion, model, case.content, top_k=rag_top_k)
        built_cases.append(
            {
                "case_id": case.case_id,
                "content": case.content,
                "case_type": case.case_type,
                "top_k": rag_top_k,
                "answer": answer_bundle["answer"],
                "paragraphs": answer_bundle["paragraphs"],
                "reasoning_paths": answer_bundle["reasoning_paths"],
                "search_result": answer_bundle["search_result"],
                "llm_result": answer_bundle["llm_result"],
            }
        )
    return built_cases


def main() -> None:
    args = parse_args()
    output_dir = get_output_dir(args.output_dir)
    json_path = output_dir / "hallucination_eval.json"
    rag_results_path = (
        Path(args.rag_results)
        if args.rag_results
        else output_dir / f"precision_top{args.rag_top_k}.json"
    )

    model = get_default_model()
    if args.phase in ("all", "generate"):
        if rag_results_path.exists():
            rag_cases = load_rag_cases(rag_results_path)
        else:
            if not args.graph_name:
                raise FileNotFoundError(
                    f"RAG results not found: {rag_results_path}. "
                    "Provide --rag-results or provide --graph-name to regenerate."
                )
            rag_cases = build_rag_cases_from_scratch(
                graph_name=args.graph_name,
                cases_path=args.cases_path,
                rag_top_k=args.rag_top_k,
                limit=args.limit,
            )

        if args.limit is not None and args.limit >= 0:
            rag_cases = rag_cases[args.offset:args.offset + args.limit]
        elif args.offset and args.offset > 0:
            rag_cases = rag_cases[args.offset:]

        existing_payload = load_json_if_exists(json_path, {"summary": {}, "cases": []}) if args.append else {"summary": {}, "cases": []}
        case_results: list[dict] = existing_payload.get("cases", [])
        new_results: list[dict] = []
        for batch in chunked(rag_cases, args.batch_size):
            for case in batch:
                question = case["content"]
                no_rag_bundle = build_plain_answer(model, question)
                new_results.append(
                    {
                        "case_id": case["case_id"],
                        "content": question,
                        "case_type": case.get("case_type"),
                        "rag_top_k": case.get("top_k", args.rag_top_k),
                        "no_rag_answer": no_rag_bundle["answer"],
                        "rag_answer": case.get("answer", ""),
                        "contexts": case.get("paragraphs", []) or [],
                        "no_rag_judge": None,
                        "rag_judge": None,
                        "rag_case": case,
                        "no_rag_llm_result": no_rag_bundle["llm_result"],
                    }
                )
            case_results = merge_case_records(case_results, new_results, key_fields=("case_id",))
            write_json(
                json_path,
                {
                    "summary": {
                        "case_count": len(case_results),
                        "rag_results_path": str(rag_results_path),
                        "status": "generated",
                        "offset": args.offset,
                        "limit": args.limit,
                        "append": args.append,
                    },
                    "cases": case_results,
                },
            )
            new_results = []

        table_rows = [
            [case["case_id"], case["content"], case["no_rag_answer"], case["rag_answer"]]
            for case in case_results
        ]
        write_markdown_table(
            output_dir / "hallucination_eval.md",
            headers=["Case ID", "Case Content", "No-RAG Answer", "RAG Answer"],
            rows=table_rows,
            title="Hallucination Evaluation",
            intro_lines=[
                f"- Reused RAG result: `{rag_results_path}`",
                f"- Case count: `{len(case_results)}`",
                f"- Batch size: `{args.batch_size}`",
                "- Phase: `generated`",
            ],
        )

    if args.phase in ("all", "judge"):
        payload = __import__("json").loads(json_path.read_text(encoding="utf-8"))
        all_case_results = payload.get("cases", [])
        selected_case_results = all_case_results
        if args.offset and args.offset > 0:
            selected_case_results = selected_case_results[args.offset:]
        if args.limit is not None and args.limit >= 0:
            selected_case_results = selected_case_results[:args.limit]

        for batch in chunked(selected_case_results, args.batch_size):
            for case in batch:
                question = case["content"]
                contexts = case.get("contexts", []) or []
                no_rag_judge = judge_hallucination(model, question, case.get("no_rag_answer", ""), contexts)
                rag_judge = judge_hallucination(model, question, case.get("rag_answer", ""), contexts)
                case["no_rag_judge"] = no_rag_judge
                case["rag_judge"] = rag_judge
            all_case_results = merge_case_records(all_case_results, batch, key_fields=("case_id",))
            write_json(json_path, {"summary": payload.get("summary", {}), "cases": all_case_results})

        no_rag_hallucinated = sum(
            1
            for case in all_case_results
            if (case.get("no_rag_judge") or {}).get("is_hallucinated")
        )
        rag_hallucinated = sum(
            1
            for case in all_case_results
            if (case.get("rag_judge") or {}).get("is_hallucinated")
        )
        total = len(all_case_results) or 1
        summary = {
            "case_count": len(all_case_results),
            "rag_results_path": str(rag_results_path),
            "no_rag_hallucination_rate": no_rag_hallucinated / total,
            "rag_hallucination_rate": rag_hallucinated / total,
            "no_rag_hallucinated_count": no_rag_hallucinated,
            "rag_hallucinated_count": rag_hallucinated,
            "status": "judged",
        }

        write_json(json_path, {"summary": summary, "cases": all_case_results})
        table_rows = [
            [case["case_id"], case["content"], case["no_rag_answer"], case["rag_answer"]]
            for case in all_case_results
        ]
        write_markdown_table(
            output_dir / "hallucination_eval.md",
            headers=["Case ID", "Case Content", "No-RAG Answer", "RAG Answer"],
            rows=table_rows,
            title="Hallucination Evaluation",
            intro_lines=[
                f"- Reused RAG result: `{rag_results_path}`",
                f"- Case count: `{len(all_case_results)}`",
                f"- Batch size: `{args.batch_size}`",
                f"- No-RAG hallucination rate: `{summary['no_rag_hallucination_rate']:.2%}`",
                f"- RAG hallucination rate: `{summary['rag_hallucination_rate']:.2%}`",
            ],
        )


if __name__ == "__main__":
    main()
