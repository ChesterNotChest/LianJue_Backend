from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from utils.llm_utils import get_model_instance
from utils.markdown_utils import clean_llm_response


@dataclass
class TestCase:
    case_id: int
    content: str
    case_type: str


def load_test_cases(cases_path: str | Path) -> list[TestCase]:
    path = Path(cases_path)
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    cases: list[TestCase] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        case_id_raw, content, case_type = parts[0], parts[1], parts[2]
        try:
            case_id = int(case_id_raw)
        except ValueError:
            continue
        cases.append(
            TestCase(
                case_id=case_id,
                content=content.strip(),
                case_type=case_type.strip(),
            )
        )
    return cases


def filter_cases(
    cases: list[TestCase],
    case_ids: list[int] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[TestCase]:
    selected = cases
    if case_ids:
        case_id_set = set(case_ids)
        selected = [case for case in selected if case.case_id in case_id_set]
    if offset and offset > 0:
        selected = selected[offset:]
    if limit is not None and limit >= 0:
        selected = selected[:limit]
    return selected


def build_knowlion(graph_name: str):
    from config import MODEL_CONFIGS
    from knowlion.abution_knowlion_driver import KnowLion

    return KnowLion(model_configs=MODEL_CONFIGS or {}, graph_name=graph_name)


def get_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: str | Path, payload: Any) -> None:
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _escape_markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", "<br>")
    return text.replace("|", "\\|")


def write_markdown_table(
    path: str | Path,
    headers: list[str],
    rows: list[list[Any]],
    title: str | None = None,
    intro_lines: list[str] | None = None,
) -> None:
    lines: list[str] = []
    if title:
        lines.append(f"# {title}")
        lines.append("")
    for line in intro_lines or []:
        lines.append(line)
    if intro_lines:
        lines.append("")

    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_escape_markdown_cell(cell) for cell in row) + " |")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_json_response(raw: str, default_key: str = "answer") -> dict[str, Any]:
    cleaned = clean_llm_response(raw or "")
    if not cleaned:
        return {default_key: ""}

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return {default_key: cleaned}


def call_json_llm(
    model: Any,
    system_prompt: str,
    user_prompt: str,
    default_key: str = "answer",
) -> dict[str, Any]:
    raw = model.call_text_model(system_prompt, user_prompt, stream=False)
    parsed = parse_json_response(raw, default_key=default_key)
    parsed["_raw"] = raw
    return parsed


def retrieve_with_rag(
    knowlion: KnowLion,
    question: str,
    top_k: int,
) -> dict[str, Any]:
    result = knowlion.search(question, top_k=top_k)
    paragraphs = result.get("paragraphs", []) if isinstance(result, dict) else []
    reasoning_paths = result.get("reasoning_paths", {}) if isinstance(result, dict) else {}
    return {
        "search_result": result,
        "paragraphs": paragraphs if isinstance(paragraphs, list) else [],
        "reasoning_paths": reasoning_paths,
    }


def build_rag_answer(
    knowlion: KnowLion,
    model: Any,
    question: str,
    top_k: int,
) -> dict[str, Any]:
    retrieval = retrieve_with_rag(knowlion, question, top_k=top_k)
    paragraphs = retrieval["paragraphs"]
    reasoning_paths = retrieval["reasoning_paths"]

    system_prompt = """
你是一个严格依据资料作答的知识问答助手。
你必须只输出 JSON，不要输出任何额外说明。
输出格式必须是：
{"answer":"<string>"}

要求：
- 优先依据提供的检索资料回答。
- 如果资料不足以支持确定答案，明确回答“根据提供资料无法确定”或“资料不足以支持更具体结论”。
- 不要编造资料中没有出现的事实。
""".strip()

    user_prompt = json.dumps(
        {
            "question": question,
            "retrieved_paragraphs": paragraphs,
            "reasoning_paths": reasoning_paths,
            "top_k": top_k,
        },
        ensure_ascii=False,
    )
    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="answer")
    return {
        "answer": str(parsed.get("answer", "")).strip(),
        "llm_result": parsed,
        **retrieval,
    }


def build_plain_answer(model: Any, question: str) -> dict[str, Any]:
    system_prompt = """
你是一个知识问答助手。
你必须只输出 JSON，不要输出任何额外说明。
输出格式必须是：
{"answer":"<string>"}
""".strip()

    user_prompt = json.dumps({"question": question}, ensure_ascii=False)
    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="answer")
    return {
        "answer": str(parsed.get("answer", "")).strip(),
        "llm_result": parsed,
    }


def judge_recall(model: Any, question: str, contexts: list[str]) -> dict[str, Any]:
    system_prompt = """
你是 RAG 检索评估器。
请判断给定资料是否已经足以支持回答问题。
只输出 JSON：
{"hit": true, "reason": "<string>"}

判断标准：
- `hit=true`：这些资料中已经包含能支持正确回答问题的关键信息。
- `hit=false`：资料不够，或只有泛泛相关但不足以支撑回答。
""".strip()

    user_prompt = json.dumps(
        {"question": question, "retrieved_paragraphs": contexts},
        ensure_ascii=False,
    )
    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="hit")
    return {
        "hit": bool(parsed.get("hit", False)),
        "reason": str(parsed.get("reason", "")).strip(),
        "judge_raw": parsed.get("_raw", ""),
    }


def judge_precision(
    model: Any,
    question: str,
    answer: str,
    contexts: list[str],
) -> dict[str, Any]:
    system_prompt = """
你是问答精确率评估器。
请判断答案是否准确、直接地回答了问题，且没有明显偏离提供资料。
只输出 JSON：
{"is_precise": true, "reason": "<string>"}

判断标准：
- `is_precise=true`：回答切题、准确，没有明显多余或错误信息。
- `is_precise=false`：回答不切题、错误、过度泛化，或包含资料无法支持的关键结论。
""".strip()

    user_prompt = json.dumps(
        {
            "question": question,
            "answer": answer,
            "retrieved_paragraphs": contexts,
        },
        ensure_ascii=False,
    )
    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="is_precise")
    return {
        "is_precise": bool(parsed.get("is_precise", False)),
        "reason": str(parsed.get("reason", "")).strip(),
        "judge_raw": parsed.get("_raw", ""),
    }


def judge_hallucination(
    model: Any,
    question: str,
    answer: str,
    contexts: list[str],
) -> dict[str, Any]:
    system_prompt = """
你是问答幻觉评估器。
请判断答案中是否存在资料未支持的关键事实、明显编造，或过度确定的表述。
只输出 JSON：
{"is_hallucinated": true, "reason": "<string>"}

判断标准：
- `is_hallucinated=true`：答案包含资料中没有根据的关键结论、细节或明显编造。
- `is_hallucinated=false`：答案整体受资料支持，或明确承认资料不足。
""".strip()

    user_prompt = json.dumps(
        {
            "question": question,
            "answer": answer,
            "retrieved_paragraphs": contexts,
        },
        ensure_ascii=False,
    )
    parsed = call_json_llm(model, system_prompt, user_prompt, default_key="is_hallucinated")
    return {
        "is_hallucinated": bool(parsed.get("is_hallucinated", False)),
        "reason": str(parsed.get("reason", "")).strip(),
        "judge_raw": parsed.get("_raw", ""),
    }


def get_default_model() -> Any:
    return get_model_instance()


def serialize_cases(cases: list[TestCase]) -> list[dict[str, Any]]:
    return [asdict(case) for case in cases]


def chunked(items: list[Any], chunk_size: int) -> list[list[Any]]:
    if chunk_size <= 0:
        return [items]
    return [items[index:index + chunk_size] for index in range(0, len(items), chunk_size)]


def load_json_if_exists(path: str | Path, default: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def merge_case_records(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    key_fields: tuple[str, ...] = ("case_id",),
) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in existing:
        key = tuple(record.get(field) for field in key_fields)
        merged[key] = record
    for record in incoming:
        key = tuple(record.get(field) for field in key_fields)
        merged[key] = record
    return sorted(
        merged.values(),
        key=lambda item: tuple(item.get(field) for field in key_fields),
    )
