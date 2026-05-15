import json
from typing import Any, Dict, List, Optional

from config import LITELLM_MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion


DEFAULT_SEARCH_TOP_K = 6


def _normalize_positive_int(value: Any, default: int, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def _normalize_classify_list(classify_list: Any) -> Optional[List[str]]:
    if classify_list in (None, ""):
        return None
    if not isinstance(classify_list, list):
        raise ValueError("classify_list must be a list when provided")
    normalized = []
    for item in classify_list:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized or None


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_reasoning_paths(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, (dict, list)):
        return value
    return [value]


def _stringify_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value).strip()


def _normalize_search_result(raw_result: Any, *, query: str, top_k: int, graph_name: Optional[str]) -> Dict[str, Any]:
    if not isinstance(raw_result, dict):
        return {
            "success": False,
            "query": query,
            "top_k": top_k,
            "graph_name": graph_name,
            "results": [],
            "paragraphs": [],
            "reasoning_paths": [],
            "path_scores": {},
            "context_text": "",
            "result_count": 0,
            "error": "retriever returned a non-dict result",
            "raw": raw_result,
        }

    if raw_result.get("error"):
        return {
            "success": False,
            "query": raw_result.get("query") or query,
            "top_k": top_k,
            "graph_name": graph_name,
            "results": [],
            "paragraphs": _as_list(raw_result.get("paragraphs")),
            "reasoning_paths": _normalize_reasoning_paths(raw_result.get("reasoning_paths")),
            "path_scores": raw_result.get("path_scores") if isinstance(raw_result.get("path_scores"), dict) else {},
            "context_text": "",
            "result_count": 0,
            "error": str(raw_result.get("error")),
            "raw": raw_result,
        }

    paragraphs = [_stringify_content(item) for item in _as_list(raw_result.get("paragraphs"))]
    paragraphs = [item for item in paragraphs if item]
    reasoning_paths = _normalize_reasoning_paths(raw_result.get("reasoning_paths"))
    path_scores = raw_result.get("path_scores") if isinstance(raw_result.get("path_scores"), dict) else {}

    results = []
    for rank, content in enumerate(paragraphs, start=1):
        results.append(
            {
                "rank": rank,
                "content": content,
                "source": "paragraphs",
                "metadata": {
                    "query": raw_result.get("query") or query,
                    "graph_name": graph_name,
                },
            }
        )

    context_parts = []
    if reasoning_paths:
        context_parts.append(
            "reasoning_paths:\n"
            + json.dumps(reasoning_paths, ensure_ascii=False, indent=2)
        )
    if paragraphs:
        context_parts.append(
            "paragraphs:\n"
            + json.dumps(paragraphs, ensure_ascii=False, indent=2)
        )

    return {
        "success": True,
        "query": raw_result.get("query") or query,
        "top_k": top_k,
        "graph_name": graph_name,
        "results": results,
        "paragraphs": paragraphs,
        "reasoning_paths": reasoning_paths,
        "path_scores": path_scores,
        "context_text": "\n\n".join(context_parts),
        "result_count": len(results),
        "error": "",
        "raw": raw_result,
    }


def search_tool(
    query: str,
    *,
    graph_name: Optional[str] = None,
    top_k: int = DEFAULT_SEARCH_TOP_K,
    classify_list: Optional[List[str]] = None,
    retriever: Any = None,
    model_configs: Optional[dict] = None,
) -> Dict[str, Any]:
    """Cheap public retrieval tool for agents.

    The caller is responsible for choosing a good query. This wrapper performs
    no LLM query expansion; it only calls the advanced KnowLion retrieval path
    and normalizes the result into a stable structure.
    """
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise ValueError("query is required")

    normalized_top_k = _normalize_positive_int(top_k, DEFAULT_SEARCH_TOP_K, "top_k")
    normalized_classify_list = _normalize_classify_list(classify_list)

    try:
        active_retriever = retriever
        if active_retriever is None:
            if not graph_name:
                raise ValueError("graph_name is required when retriever is not provided")
            active_retriever = KnowLion(model_configs or LITELLM_MODEL_CONFIGS or {}, graph_name=str(graph_name))

        raw_result = active_retriever.search(
            normalized_query,
            top_k=normalized_top_k,
            classify_list=normalized_classify_list,
        )
    except Exception as exc:
        raw_result = {"query": normalized_query, "error": str(exc)}

    return _normalize_search_result(
        raw_result,
        query=normalized_query,
        top_k=normalized_top_k,
        graph_name=str(graph_name).strip() if graph_name else None,
    )
