import importlib

import pytest

st = importlib.import_module("tasks.common.search_tool")


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def search(self, query, top_k=10, classify_list=None):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "classify_list": classify_list,
            }
        )
        return {
            "query": query,
            "path_scores": {
                "vector_similarity_para": 2,
                "bm25_similarity_para": 1,
                "related_context_para": 1,
                "cross_doc_para": 1,
            },
            "reasoning_paths": {
                "entity_in_para_details": ["RowKey: HBase row identifier"],
                "edges": ["RowKey-hotspot: may cause write pressure"],
            },
            "paragraphs": [
                "para_1([HBase Guide]) RowKey should avoid monotonically increasing values.",
                "para_2([HBase Guide]) Pre-splitting can reduce hotspot pressure.",
            ],
        }


def test_search_tool_normalizes_advanced_retrieval_result():
    retriever = FakeRetriever()

    result = st.search_tool(
        "RowKey hotspot",
        graph_name="graph_demo",
        top_k=2,
        classify_list=["doc-a", "doc-a", "", None],
        retriever=retriever,
    )

    assert result["success"] is True
    assert result["query"] == "RowKey hotspot"
    assert result["top_k"] == 2
    assert result["graph_name"] == "graph_demo"
    assert result["path_scores"]["vector_similarity_para"] == 2
    assert result["paragraphs"] == [
        "para_1([HBase Guide]) RowKey should avoid monotonically increasing values.",
        "para_2([HBase Guide]) Pre-splitting can reduce hotspot pressure.",
    ]
    assert result["reasoning_paths"]["edges"] == ["RowKey-hotspot: may cause write pressure"]
    assert result["result_count"] == 2
    assert result["results"][0]["rank"] == 1
    assert result["results"][0]["source"] == "paragraphs"
    assert "[HBase Guide]" in result["results"][0]["content"]
    assert "reasoning_paths" in result["context_text"]
    assert "paragraphs" in result["context_text"]
    assert result["raw"]["query"] == "RowKey hotspot"
    assert retriever.calls == [
        {
            "query": "RowKey hotspot",
            "top_k": 2,
            "classify_list": ["doc-a"],
        }
    ]


def test_search_tool_returns_structured_failure_for_retriever_error():
    class ErrorRetriever:
        def search(self, query, top_k=10, classify_list=None):
            return {"query": query, "error": "graph unavailable"}

    result = st.search_tool("Spark shuffle", retriever=ErrorRetriever())

    assert result["success"] is False
    assert result["query"] == "Spark shuffle"
    assert result["results"] == []
    assert result["context_text"] == ""
    assert result["error"] == "graph unavailable"


def test_search_tool_requires_query():
    with pytest.raises(ValueError, match="query is required"):
        st.search_tool("   ", retriever=FakeRetriever())


def test_search_tool_requires_positive_top_k():
    with pytest.raises(ValueError, match="top_k must be a positive integer"):
        st.search_tool("RowKey", top_k=0, retriever=FakeRetriever())


def test_search_tool_rejects_non_list_classify_list():
    with pytest.raises(ValueError, match="classify_list must be a list"):
        st.search_tool("RowKey", classify_list="doc-a", retriever=FakeRetriever())


def test_search_tool_builds_knowlion_when_retriever_is_not_provided(monkeypatch):
    captured = {}

    class FakeKnowLion:
        def __init__(self, model_configs, graph_name):
            captured["model_configs"] = model_configs
            captured["graph_name"] = graph_name

        def search(self, query, top_k=10, classify_list=None):
            captured["query"] = query
            captured["top_k"] = top_k
            captured["classify_list"] = classify_list
            return {
                "query": query,
                "paragraphs": ["para([Doc]) content"],
                "reasoning_paths": [],
                "path_scores": {},
            }

    monkeypatch.setattr(st, "KnowLion", FakeKnowLion)

    result = st.search_tool(
        "MapReduce",
        graph_name="graph_demo",
        top_k=3,
        classify_list=["material"],
        model_configs={"text": {"model_name": "fake"}},
    )

    assert result["success"] is True
    assert result["result_count"] == 1
    assert captured == {
        "model_configs": {"text": {"model_name": "fake"}},
        "graph_name": "graph_demo",
        "query": "MapReduce",
        "top_k": 3,
        "classify_list": ["material"],
    }


def test_search_tool_requires_graph_name_without_retriever():
    result = st.search_tool("MapReduce")

    assert result["success"] is False
    assert "graph_name is required" in result["error"]
