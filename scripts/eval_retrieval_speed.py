from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from config import MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion
from scripts.rag_eval_common import get_output_dir, load_test_cases, write_json, write_markdown_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure retrieval speed for all test cases, including and excluding embed time."
    )
    parser.add_argument("--graph-name", required=True, help="Graph name used by KnowLion.")
    parser.add_argument(
        "--cases-path",
        default=str(Path(__file__).resolve().parents[1] / "\u6d4b\u8bd5\u7528\u4f8b.md"),
        help="Path to test cases markdown file.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "scripts" / "eval_outputs"),
        help="Directory for report outputs.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Final retrieval top-k.")
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of timed runs per case. Reports average/min/max over repeats.",
    )
    parser.add_argument(
        "--warmup-count",
        type=int,
        default=1,
        help="Warm up the retriever with the first N test cases before timing.",
    )
    return parser.parse_args()


def _ns_to_ms(value_ns: int) -> float:
    return value_ns / 1_000_000


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
    return {
        "avg_ms": round(statistics.mean(values), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
    }


def _run_retrieval_once(retriever: Any, query_text: str, top_k: int) -> dict[str, Any]:
    embed_start = perf_counter_ns()
    query_vector = retriever.model_instance.call_embed_model([query_text])[0]
    embed_end = perf_counter_ns()

    retrieval_start = perf_counter_ns()
    all_results: dict[str, Any] = {}
    initial_para_keys, vector_para_result, bm25_para_result = retriever.vector_and_bm25_retrieval(
        query_text,
        query_vector,
        top_k * 2,
        None,
    )
    all_results["vector_similarity_para"] = vector_para_result
    all_results["bm25_similarity_para"] = bm25_para_result

    reasoning_retrieval = {"entity_in_para_details": [], "edges": []}
    if initial_para_keys:
        context_para_score_map = retriever.context_associated_retrieval(
            list(initial_para_keys),
            query_vector,
            top_k * 2,
            None,
        )
        all_results["related_context_para"] = context_para_score_map

        context_para_ids = [para_info.split("(")[0] for para_info in context_para_score_map.keys()]
        cross_doc_para_score_map, reasoning_retrieval = retriever.cross_doc_and_multi_hop_retrieval(
            list(initial_para_keys),
            context_para_ids,
            query_vector,
            top_k,
            None,
        )
        all_results["cross_doc_para"] = cross_doc_para_score_map

    final_results = retriever.rrf_fusion_with_formatted_paragraphs(all_results, top_k)
    retrieval_end = perf_counter_ns()

    embed_ms = _ns_to_ms(embed_end - embed_start)
    retrieval_only_ms = _ns_to_ms(retrieval_end - retrieval_start)
    total_ms = _ns_to_ms(retrieval_end - embed_start)

    return {
        "query": query_text,
        "embed_ms": round(embed_ms, 3),
        "retrieval_only_ms": round(retrieval_only_ms, 3),
        "total_ms": round(total_ms, 3),
        "path_scores": {key: len(value) for key, value in all_results.items()},
        "paragraph_count": len(final_results),
        "paragraphs": [para for para, _score in final_results],
        "reasoning_paths": reasoning_retrieval,
    }


def _build_case_result(case: Any, repeats: int, retriever: Any, top_k: int) -> dict[str, Any]:
    run_results = [_run_retrieval_once(retriever, case.content, top_k) for _ in range(repeats)]

    embed_values = [result["embed_ms"] for result in run_results]
    retrieval_values = [result["retrieval_only_ms"] for result in run_results]
    total_values = [result["total_ms"] for result in run_results]

    representative = run_results[0]
    return {
        "case_id": case.case_id,
        "content": case.content,
        "case_type": case.case_type,
        "repeats": repeats,
        "embed": _summarize(embed_values),
        "retrieval_only": _summarize(retrieval_values),
        "total": _summarize(total_values),
        "path_scores": representative["path_scores"],
        "paragraph_count": representative["paragraph_count"],
        "paragraphs": representative["paragraphs"],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "case_id",
                "case_type",
                "case_content",
                "repeats",
                "embed_avg_ms",
                "embed_min_ms",
                "embed_max_ms",
                "retrieval_only_avg_ms",
                "retrieval_only_min_ms",
                "retrieval_only_max_ms",
                "total_avg_ms",
                "total_min_ms",
                "total_max_ms",
                "paragraph_count",
                "path_scores",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["case_id"],
                    row["case_type"],
                    row["content"],
                    row["repeats"],
                    row["embed"]["avg_ms"],
                    row["embed"]["min_ms"],
                    row["embed"]["max_ms"],
                    row["retrieval_only"]["avg_ms"],
                    row["retrieval_only"]["min_ms"],
                    row["retrieval_only"]["max_ms"],
                    row["total"]["avg_ms"],
                    row["total"]["min_ms"],
                    row["total"]["max_ms"],
                    row["paragraph_count"],
                    json.dumps(row["path_scores"], ensure_ascii=False),
                ]
            )


def _summarize_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    embed_avg_values = [row["embed"]["avg_ms"] for row in rows]
    retrieval_avg_values = [row["retrieval_only"]["avg_ms"] for row in rows]
    total_avg_values = [row["total"]["avg_ms"] for row in rows]

    return {
        "case_count": len(rows),
        "embed_avg_ms": round(statistics.mean(embed_avg_values), 3) if embed_avg_values else 0.0,
        "embed_min_ms": round(min(embed_avg_values), 3) if embed_avg_values else 0.0,
        "embed_max_ms": round(max(embed_avg_values), 3) if embed_avg_values else 0.0,
        "retrieval_only_avg_ms": round(statistics.mean(retrieval_avg_values), 3) if retrieval_avg_values else 0.0,
        "retrieval_only_min_ms": round(min(retrieval_avg_values), 3) if retrieval_avg_values else 0.0,
        "retrieval_only_max_ms": round(max(retrieval_avg_values), 3) if retrieval_avg_values else 0.0,
        "total_avg_ms": round(statistics.mean(total_avg_values), 3) if total_avg_values else 0.0,
        "total_min_ms": round(min(total_avg_values), 3) if total_avg_values else 0.0,
        "total_max_ms": round(max(total_avg_values), 3) if total_avg_values else 0.0,
    }


def main() -> None:
    args = parse_args()
    cases = load_test_cases(args.cases_path)
    output_dir = get_output_dir(args.output_dir)

    knowlion = KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=args.graph_name)
    retriever = knowlion._get_advanced_retriever()
    if retriever is None:
        raise RuntimeError(f"Failed to initialize retriever for graph: {args.graph_name}")

    warmup_cases = cases[: max(args.warmup_count, 0)]
    for case in warmup_cases:
        _run_retrieval_once(retriever, case.content, args.top_k)

    rows = [_build_case_result(case, args.repeats, retriever, args.top_k) for case in cases]
    summary = _summarize_report(rows)
    report_payload = {
        "summary": {
            "graph_name": args.graph_name,
            "top_k": args.top_k,
            "repeats": args.repeats,
            "warmup_count": args.warmup_count,
            **summary,
        },
        "cases": rows,
    }

    json_path = output_dir / "retrieval_speed_report.json"
    csv_path = output_dir / "retrieval_speed_report.csv"
    md_path = output_dir / "retrieval_speed_report.md"

    write_json(json_path, report_payload)
    _write_csv(csv_path, rows)

    md_rows = [
        [
            row["case_id"],
            row["case_type"],
            row["embed"]["avg_ms"],
            row["retrieval_only"]["avg_ms"],
            row["total"]["avg_ms"],
            row["paragraph_count"],
        ]
        for row in rows
    ]
    write_markdown_table(
        md_path,
        headers=[
            "Case ID",
            "Case Type",
            "Embed Avg (ms)",
            "Retrieval Only Avg (ms)",
            "Total Avg (ms)",
            "Paragraph Count",
        ],
        rows=md_rows,
        title="Retrieval Speed Evaluation",
        intro_lines=[
            f"- Graph: `{args.graph_name}`",
            f"- Case count: `{summary['case_count']}`",
            f"- Top-k: `{args.top_k}`",
            f"- Repeats per case: `{args.repeats}`",
            f"- Warmup cases: `{args.warmup_count}`",
            f"- Avg embed time: `{summary['embed_avg_ms']}` ms",
            f"- Avg retrieval-only time: `{summary['retrieval_only_avg_ms']}` ms",
            f"- Avg total time: `{summary['total_avg_ms']}` ms",
        ],
    )


if __name__ == "__main__":
    main()
