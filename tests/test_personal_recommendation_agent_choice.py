import json
import os
import shutil
from pathlib import Path

import pytest

from tasks import personal_recommendation_task as prt
from tasks.personal_recommendation import agent_runtime as prar
from tasks.personal_recommendation import agent_tools as prat
from tasks.personal_recommendation import service as prs
from tasks.personal_recommendation.sample_data import goals as sample_goals
from tasks.personal_recommendation.sample_data import learning_tree, user_profile


EXPECTED_TOOL_ORDER = [
    "load_request_context",
    "search_recommendation_context",
    "run_recommendation_route",
]
TEST_RECOMMENDATION_ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts" / "personal_recommendation"


def _reset_artifact_root(name: str) -> Path:
    root = TEST_RECOMMENDATION_ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(root: Path, name: str, payload: dict) -> Path:
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _recommendation_summary(recommendation: dict | None) -> dict:
    recommendation = recommendation or {}
    graph = recommendation.get("graph") or {}
    best_path = recommendation.get("best_path") or {}
    return {
        "success": recommendation.get("success"),
        "node_count": len(graph.get("nodes") or []),
        "edge_count": len(graph.get("edges") or []),
        "candidate_count": len(recommendation.get("candidates") or []),
        "selected_count": len(recommendation.get("selected") or []),
        "best_path": best_path.get("path"),
    }


def _normalize_model_for_dashscope():
    text_config = prar.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        prar.get_personal_recommendation_agent.cache_clear()


def test_personal_recommendation_mock_agent_accepts_learning_plan(monkeypatch):
    artifact_root = _reset_artifact_root("mock_agent_learning_plan")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    monkeypatch.setattr(
        prat,
        "search_tool",
        lambda query, graph_name=None, top_k=5: {
            "success": True,
            "query": query,
            "graph_name": graph_name,
            "top_k": top_k,
            "result_count": 1,
            "reasoning_paths": [
                {"path": ["Statistics 101", "Machine Learning Intro"], "reason": "statistics supports ML basics"}
            ],
            "paragraphs": ["Statistics 101 is a common prerequisite for Machine Learning Intro."],
            "context_text": "Statistics 101 is a common prerequisite for Machine Learning Intro.",
            "error": "",
        },
    )
    monkeypatch.setattr(prs, "build_recommendation_profile", lambda user_id, syllabus_id=None: user_profile)
    monkeypatch.setattr(prs, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)

    state = {
        "payload": {
            "user_id": 12345,
            "syllabus_id": 20,
            "goals": sample_goals,
            "question": "What should I learn next for machine learning?",
            "graph_name": "mock_graph",
            "K": 10,
            "beam_width": 8,
        }
    }

    tool_outputs = [
        prat.tool_load_request_context(state),
        prat.tool_search_recommendation_context(state),
        prat.tool_run_recommendation_route(state),
    ]
    recommendation = state["recommendation_result"]
    accept_result = prt.accept_recommendation_path(
        user_id=state["payload"]["user_id"],
        syllabus_id=state["payload"]["syllabus_id"],
        recommendation_result=recommendation,
    )
    active_plan = prt.get_active_learning_plan(state["payload"]["user_id"], state["payload"]["syllabus_id"])
    manifest_entries = prt.load_learning_plan_manifest(state["payload"]["user_id"], state["payload"]["syllabus_id"])

    assert [item["tool"] for item in tool_outputs] == EXPECTED_TOOL_ORDER
    assert recommendation["success"] is True
    assert recommendation["best_path"]
    assert accept_result["success"] is True
    assert active_plan["plan_id"] == accept_result["plan_id"]
    assert active_plan["steps"]
    assert len(manifest_entries) >= 2
    assert {entry["event_type"] for entry in manifest_entries}.issuperset({"plan_created", "steps_created"})

    _write_artifact(
        artifact_root,
        "mock_agent_learning_plan_result.json",
        {
            "test_name": "test_personal_recommendation_mock_agent_accepts_learning_plan",
            "expected_tool_order": EXPECTED_TOOL_ORDER,
            "tool_outputs": tool_outputs,
            "payload": state["payload"],
            "summary": _recommendation_summary(recommendation),
            "recommendation": recommendation,
            "accept_result": accept_result,
            "active_plan": active_plan,
            "manifest_entries": manifest_entries,
        },
    )


def _trace_agent_tools(monkeypatch):
    trace = []
    tool_outputs = []

    def wrap(tool_name, func):
        def traced(state):
            trace.append(tool_name)
            result = func(state)
            tool_outputs.append({"tool": tool_name, "result": result})
            state["tool_trace"] = trace[:]
            return result

        return traced

    monkeypatch.setattr(
        prar,
        "tool_load_request_context",
        wrap("load_request_context", prat.tool_load_request_context),
    )
    monkeypatch.setattr(
        prar,
        "tool_search_recommendation_context",
        wrap("search_recommendation_context", prat.tool_search_recommendation_context),
    )
    monkeypatch.setattr(
        prar,
        "tool_run_recommendation_route",
        wrap("run_recommendation_route", prat.tool_run_recommendation_route),
    )
    prar.get_personal_recommendation_agent.cache_clear()
    return trace, tool_outputs


def _accept_recommendation_for_artifact(artifact_root: Path, payload: dict, recommendation: dict) -> dict:
    os.environ["PERSONAL_RECOMMENDATION_ROOT"] = str(artifact_root)
    accept_result = prt.accept_recommendation_path(
        user_id=payload["user_id"],
        syllabus_id=payload.get("syllabus_id"),
        recommendation_result=recommendation,
    )
    active_plan = prt.get_active_learning_plan(payload["user_id"], payload.get("syllabus_id"))
    manifest_entries = prt.load_learning_plan_manifest(payload["user_id"], payload.get("syllabus_id"))
    return {
        "accept_result": accept_result,
        "active_plan": active_plan,
        "manifest_entries": manifest_entries,
    }


@pytest.mark.llm
def test_personal_recommendation_agent_selects_expected_tools(monkeypatch):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real personal recommendation agent choice smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("agent_choice")
    trace, tool_outputs = _trace_agent_tools(monkeypatch)

    monkeypatch.setattr(
        prat,
        "search_tool",
        lambda query, graph_name=None, top_k=5: {
            "success": True,
            "query": query,
            "graph_name": graph_name,
            "top_k": top_k,
            "result_count": 1,
            "reasoning_paths": [
                {"path": ["Statistics 101", "Machine Learning Intro"], "reason": "statistics supports ML basics"}
            ],
            "paragraphs": ["Statistics 101 is a common prerequisite for Machine Learning Intro."],
            "context_text": "Statistics 101 is a common prerequisite for Machine Learning Intro.",
            "error": "",
        },
    )
    monkeypatch.setattr(prs, "build_recommendation_profile", lambda user_id, syllabus_id=None: user_profile)
    monkeypatch.setattr(prs, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)

    payload = {
        "user_id": 12345,
        "syllabus_id": 20,
        "goals": sample_goals,
        "question": "What should I learn next for machine learning?",
        "graph_name": "RAG",
        "K": 10,
        "beam_width": 8,
    }

    try:
        result = prt.run_personal_recommendation_agent(payload)
    finally:
        prar.get_personal_recommendation_agent.cache_clear()

    assert trace == EXPECTED_TOOL_ORDER
    assert result.success is True
    assert result.recommendation is not None
    assert result.recommendation["success"] is True
    assert result.recommendation["graph"]["nodes"]
    assert result.recommendation["candidates"]
    assert result.recommendation["best_path"]
    assert result.recommendation["rag_overlay"]["enabled"] is True
    assert result.recommendation["rag_overlay"]["matched_nodes"]
    accept_payload = _accept_recommendation_for_artifact(artifact_root, payload, result.recommendation)
    assert accept_payload["accept_result"]["success"] is True
    assert accept_payload["active_plan"]["steps"]

    graph_node_ids = {node["id"] for node in result.recommendation["graph"]["nodes"]}
    graph_edge_ids = {edge["edge_id"] for edge in result.recommendation["graph"]["edges"]}
    rag_matched_nodes = [node for node in result.recommendation["graph"]["nodes"] if node.get("rag_matched")]
    assert set(result.recommendation["best_path"]["path"]).issubset(graph_node_ids)
    assert rag_matched_nodes
    assert "rag_relevance" in result.recommendation["best_path"]
    for edge in result.recommendation["best_path"]["path_edges"]:
        assert edge["edge_id"] in graph_edge_ids
        assert edge["source"] in graph_node_ids
        assert edge["target"] in graph_node_ids

    _write_artifact(
        artifact_root,
        "agent_choice_result.json",
        {
            "test_name": "test_personal_recommendation_agent_selects_expected_tools",
            "expected_tool_order": EXPECTED_TOOL_ORDER,
            "tool_trace": trace,
            "tool_outputs": tool_outputs,
            "payload": payload,
            "summary": _recommendation_summary(result.recommendation),
            "result": result.model_dump(),
            **accept_payload,
        },
    )


@pytest.mark.llm
def test_personal_recommendation_agent_real_rag_optional(monkeypatch):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real personal recommendation agent choice smoke test.")
    if os.getenv("RUN_REAL_RAG_TESTS") != "1":
        pytest.skip("Set RUN_REAL_RAG_TESTS=1 to run the optional real RAG recommendation integration test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("agent_choice_real_rag")
    trace, tool_outputs = _trace_agent_tools(monkeypatch)

    monkeypatch.setattr(prs, "build_recommendation_profile", lambda user_id, syllabus_id=None: user_profile)
    monkeypatch.setattr(prs, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)

    payload = {
        "user_id": 12345,
        "syllabus_id": 20,
        "goals": sample_goals,
        "question": os.getenv("PERSONAL_RECOMMENDATION_RAG_QUERY")
        or "What should I learn next for machine learning?",
        "graph_name": os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME")
        or os.getenv("SEARCH_TOOL_GRAPH_NAME")
        or "RAG",
        "K": int(os.getenv("PERSONAL_RECOMMENDATION_ROUTE_K") or "10"),
        "beam_width": int(os.getenv("PERSONAL_RECOMMENDATION_BEAM_WIDTH") or "8"),
        "rag_top_k": int(os.getenv("PERSONAL_RECOMMENDATION_RAG_TOP_K") or "5"),
    }

    try:
        result = prt.run_personal_recommendation_agent(payload)
    finally:
        prar.get_personal_recommendation_agent.cache_clear()

    assert trace == EXPECTED_TOOL_ORDER
    assert result.success is True
    assert result.recommendation is not None
    assert result.recommendation["success"] is True
    assert result.recommendation["graph"]["nodes"]
    assert result.recommendation["candidates"]
    assert result.recommendation["best_path"]
    assert result.recommendation["rag_overlay"]["enabled"] is True
    assert result.recommendation["rag_overlay"]["matched_nodes"]
    accept_payload = _accept_recommendation_for_artifact(artifact_root, payload, result.recommendation)
    assert accept_payload["accept_result"]["success"] is True
    assert accept_payload["active_plan"]["steps"]

    _write_artifact(
        artifact_root,
        "agent_choice_real_rag_result.json",
        {
            "test_name": "test_personal_recommendation_agent_real_rag_optional",
            "expected_tool_order": EXPECTED_TOOL_ORDER,
            "tool_trace": trace,
            "tool_outputs": tool_outputs,
            "payload": payload,
            "summary": _recommendation_summary(result.recommendation),
            "result": result.model_dump(),
            **accept_payload,
        },
    )
