from copy import deepcopy

from tasks.personal_recommendation.concept_decomposer import (
    DECOMPOSITION_METHOD_AGENT,
    DECOMPOSITION_METHOD_RULE_FALLBACK,
    FALLBACK_TAG_RULE_CONCEPT,
    FALLBACK_TAG_RULE_IMPLIED_CONCEPT,
    decompose_periods_to_concepts,
    normalize_decomposition_rag_context,
)


def _period():
    return {
        "week_index": "6",
        "content": "大数据存储与管理：分布式数据库中典型技术HBase",
        "enhanced_content": "HBase 涉及 RowKey、Region、预分区和热点规避。",
    }


def test_concept_decomposer_accepts_mock_agent_output():
    def fake_agent(payload):
        return {
            "concepts": [
                {
                    "title": "HBase",
                    "source_period": {"week_index": "6", "title": "HBase"},
                    "confidence": 0.9,
                    "matched_by": ["period.enhanced_content"],
                    "reason": "base concept",
                },
                {
                    "title": "RowKey",
                    "source_period": {"week_index": "6", "title": "HBase"},
                    "prerequisite_titles": ["HBase"],
                    "confidence": 0.86,
                    "matched_by": ["rag.paragraph"],
                    "reason": "row identifier",
                },
            ],
            "edges": [
                {"source_title": "HBase", "target_title": "RowKey", "confidence": 0.8},
            ],
        }

    result = decompose_periods_to_concepts([_period()], decomposer=fake_agent)

    assert result["success"] is True
    assert result["method"] == DECOMPOSITION_METHOD_AGENT
    assert result["fallback_used"] is False
    assert [item["title"] for item in result["concepts"]] == ["HBase", "RowKey"]
    assert result["concepts"][1]["reliability"] == 0.86
    assert result["edges"][0]["target_title"] == "RowKey"


def test_concept_decomposer_normalizes_agent_drift():
    def drifting_agent(payload):
        return {
            "concepts": [
                {"title": "RowKey", "source_period": {"week_index": "6"}, "confidence": "0.7"},
                {"title": "RowKey", "source_period": {"week_index": "6"}, "confidence": 2},
                {"title": "", "source_period": {"week_index": "6"}},
            ],
            "edges": [
                {"source_title": "HBase", "target_title": "RowKey", "confidence": "bad"},
                {"source_title": "RowKey", "target_title": "Unknown", "confidence": 0.5},
            ],
        }

    result = decompose_periods_to_concepts([_period()], decomposer=drifting_agent)

    assert result["success"] is True
    assert len(result["concepts"]) == 1
    assert result["concepts"][0]["confidence"] == 0.7
    assert result["edges"] == []


def test_concept_decomposer_accepts_real_agent_shape_drift():
    def drifting_agent(payload):
        return {
            "concepts": [
                {
                    "title": "Vector Embeddings",
                    "source_period": {"week_index": 1},
                    "confidence": 0.92,
                    "matched_by": "exact_match",
                    "reason": "embedding concept",
                },
                {
                    "title": "Semantic Search",
                    "source_period": {"week_index": 1},
                    "prerequisite_titles": "Vector Embeddings",
                    "confidence": 0.9,
                    "matched_by": "exact_match",
                    "reason": "retrieval concept",
                },
            ],
            "edges": [
                {"from": "Vector Embeddings", "to": "Semantic Search", "relation": "enables"},
            ],
        }

    result = decompose_periods_to_concepts([{"week_index": "1", "content": "RAG"}], decomposer=drifting_agent)

    assert result["success"] is True
    assert result["method"] == DECOMPOSITION_METHOD_AGENT
    assert result["fallback_used"] is False
    assert result["concepts"][0]["matched_by"] == ["exact_match"]
    assert result["concepts"][1]["prerequisite_titles"] == ["Vector Embeddings"]
    assert result["edges"][0]["source_title"] == "Vector Embeddings"
    assert result["edges"][0]["target_title"] == "Semantic Search"
    assert result["edges"][0]["reason"] == "enables"


def test_concept_decomposer_falls_back_when_agent_invalid():
    def invalid_agent(payload):
        return {"concepts": []}

    def rule(period):
        return [
            {
                "title": "RowKey",
                "confidence": 0.75,
                "matched_by": ["RowKey"],
                "fallback_tag": FALLBACK_TAG_RULE_CONCEPT,
            },
            {
                "title": "热点规避",
                "confidence": 0.55,
                "matched_by": ["implied_by:HBase"],
                "fallback_tag": FALLBACK_TAG_RULE_IMPLIED_CONCEPT,
                "implied": True,
            },
        ]

    result = decompose_periods_to_concepts([_period()], decomposer=invalid_agent, rule_decomposer=rule)

    assert result["success"] is True
    assert result["method"] == DECOMPOSITION_METHOD_RULE_FALLBACK
    assert result["fallback_used"] is True
    assert result["fallback_summary"]["needs_review"] is True
    assert result["concepts"][0]["fallback_tag"] == FALLBACK_TAG_RULE_CONCEPT
    assert result["concepts"][1]["reliability"] == 0.35


def test_concept_decomposer_does_not_mutate_original_period():
    periods = [_period()]
    before = deepcopy(periods)

    decompose_periods_to_concepts(periods, decomposer=lambda payload: {"concepts": []})

    assert periods == before


def test_normalize_decomposition_rag_context_prefers_results_metadata():
    rag_context = {
        "success": True,
        "query": "RowKey",
        "graph_name": "RAG",
        "results": [
            {
                "rank": 2,
                "content": "RowKey evidence",
                "source": "paragraphs",
                "metadata": {"doc": "HBase Guide"},
            }
        ],
        "paragraphs": ["fallback paragraph"],
        "reasoning_paths": {"edges": ["HBase-RowKey"], "entity_in_para_details": ["detail"]},
        "path_scores": {"vector_similarity_para": 10},
        "context_text": "ctx",
    }

    normalized = normalize_decomposition_rag_context(rag_context)

    assert normalized["success"] is True
    assert normalized["evidence_items"][0]["content"] == "RowKey evidence"
    assert normalized["evidence_items"][0]["metadata"] == {"doc": "HBase Guide"}
    assert normalized["reasoning_edges"] == ["HBase-RowKey"]
    assert normalized["entity_details"] == ["detail"]
    assert normalized["path_scores"]["vector_similarity_para"] == 10
