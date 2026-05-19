import os

import pytest

from tests.artifact_utils import write_test_artifact
from tasks import resource_planning_agent_task as rpat


FIXED_PAYLOAD = {
    "user_id": 19,
    "syllabus_id": 23,
    "question": "我最近在学 HBase，RowKey 热点和预分区策略总是搞不懂，想要一些针对性的学习资源。",
    "topic": "HBase RowKey 热点规避",
    "resource_types": ["documents", "mindmap", "quiz"],
    "selected_weeks": [5],
    "knowledge_items": ["RowKey 热点", "预分区策略"],
    "weak_points": ["RowKey 热点", "预分区策略"],
    "learning_goal": "掌握 HBase RowKey 设计和热点规避",
    "retrieval_context": {
        "success": True,
        "query": "HBase RowKey 热点 预分区策略",
        "paragraphs": [
            "RowKey 设计需要避免热点并保持可区分性。",
            "预分区策略可以缓解写入集中问题。",
        ],
        "reasoning_paths": ["RowKey -> 热点 -> 预分区"],
    },
}


def _require_real_search_tool():
    if os.getenv("RUN_SEARCH_TESTS") != "1":
        pytest.skip("Set RUN_SEARCH_TESTS=1 to run real search-backed planning tests.")
    try:
        from tasks.search_tool import search_tool
    except ModuleNotFoundError as exc:
        pytest.skip(f"Real search dependency is unavailable: {exc}")

    return search_tool


def _build_real_search_payload():
    payload = dict(FIXED_PAYLOAD)
    payload.pop("retrieval_context", None)
    payload["subject"] = "大数据概论"
    payload["graph_name"] = os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"
    return payload


def test_resource_planning_agent_builds_plan_retrieval_and_draft_in_one_run():
    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])

    result = rpat.run_resource_planning_agent(
        dict(FIXED_PAYLOAD),
        "documents",
        planning_agent=planner,
    )

    assert result["success"] is True
    assert result["resource_type"] == "documents"
    assert result["plan"]["resource_type"] == "documents"
    assert result["plan"]["student_question"] == FIXED_PAYLOAD["question"]
    assert result["retrieval_context"]["paragraphs"] == FIXED_PAYLOAD["retrieval_context"]["paragraphs"]
    assert result["draft"]["outline"]
    assert result["draft"]["evidence"] == FIXED_PAYLOAD["retrieval_context"]["paragraphs"][:2]
    assert result["tool_trace"] == [
        "read_generation_plan",
        "write_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
        "write_generation_draft",
    ]


def test_resource_planning_agent_reuses_existing_plan_and_draft_on_second_run():
    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])

    first = rpat.run_resource_planning_agent(
        dict(FIXED_PAYLOAD),
        "ppt",
        planning_agent=planner,
    )
    second = rpat.run_resource_planning_agent(
        dict(FIXED_PAYLOAD),
        "ppt",
        planning_agent=planner,
    )

    assert first["success"] is True
    assert second["success"] is True
    assert first["plan"] == second["plan"]
    assert first["draft"] == second["draft"]
    assert second["tool_trace"] == [
        "read_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
    ]


@pytest.mark.search
def test_resource_planning_agent_with_real_search_tool_builds_grounded_draft():
    search_tool = _require_real_search_tool()
    payload = _build_real_search_payload()
    planner = rpat.ResourcePlanningAgent(search_fn=search_tool)

    result = rpat.run_resource_planning_agent(
        payload,
        "documents",
        planning_agent=planner,
    )

    retrieval = result["retrieval_context"]
    if not isinstance(retrieval, dict) or not retrieval.get("success") or not retrieval.get("paragraphs"):
        error = retrieval.get("error") if isinstance(retrieval, dict) else ""
        pytest.skip(f"Real search returned no usable paragraphs for graph {payload['graph_name']}: {error}")

    assert result["success"] is True
    assert result["resource_type"] == "documents"
    assert result["plan"]["resource_type"] == "documents"
    assert "HBase" in (retrieval.get("query") or "")
    assert retrieval["paragraphs"]
    assert result["draft"]["outline"]
    assert result["draft"]["evidence"]
    assert result["draft"]["evidence"] == retrieval["paragraphs"][: len(result["draft"]["evidence"])]
    assert result["tool_trace"] == [
        "read_generation_plan",
        "write_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
        "write_generation_draft",
    ]

    artifact_path = write_test_artifact(
        "real_search_planning_result.json",
        {
            "request": payload,
            "result": result,
        },
    )
    assert artifact_path.exists()
