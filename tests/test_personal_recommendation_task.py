import json
import shutil
from pathlib import Path

from tasks.personal_recommendation.evaluator import normalize_scores
from tasks.personal_recommendation.graph_adapter import InMemoryGraphAdapter
from tasks.personal_recommendation.perception import generate_state
from tasks.personal_recommendation.sample_data import goals, learning_tree, user_profile
from tasks.personal_recommendation_task import run_recommendation_route
from tasks import personal_recommendation_task as prt_facade
from tasks.personal_recommendation import agent_tools as prat
from tasks.personal_recommendation import service as prt


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


def _recommendation_summary(result: dict) -> dict:
    graph = result.get("graph") or {}
    best_path = result.get("best_path") or {}
    return {
        "success": result.get("success"),
        "node_count": len(graph.get("nodes") or []),
        "edge_count": len(graph.get("edges") or []),
        "candidate_count": len(result.get("candidates") or []),
        "selected_count": len(result.get("selected") or []),
        "best_path": best_path.get("path"),
    }


def test_personal_recommendation_task_generates_candidates(monkeypatch):
    monkeypatch.setattr(
        "tasks.personal_recommendation.service.build_recommendation_profile",
        lambda user_id, syllabus_id=None: user_profile,
    )
    monkeypatch.setattr(
        "tasks.personal_recommendation.service.load_recommendation_learning_tree",
        lambda syllabus_id=None: learning_tree,
    )

    result = run_recommendation_route(
        user_id=123,
        syllabus_id=456,
        goals=goals,
        L_max=6,
        T_max=50,
        K=10,
        beam_width=4,
    )

    assert result["success"] is True
    assert result["schema_version"] == prt.RECOMMENDATION_SCHEMA_VERSION
    assert "planning_hints" in result
    assert isinstance(result["candidates"], list)
    assert isinstance(result["graph"]["nodes"], list)
    assert isinstance(result["graph"]["edges"], list)
    assert result["graph"]["nodes"]
    assert result["error_code"] == ""
    if result["candidates"]:
        candidate = result["candidates"][0]
        assert isinstance(candidate["path"], list)
        assert isinstance(candidate["skills"], list)
        assert isinstance(candidate["path_edges"], list)
        assert isinstance(candidate["path_depth"], int)
        assert "selected" in candidate
    if result["best_path"]:
        assert isinstance(result["best_path"]["path"], list)
        assert isinstance(result["best_path"]["path_edges"], list)


def test_personal_recommendation_task_requires_user_id():
    result = run_recommendation_route(user_id=0)

    assert result["success"] is False
    assert result["error_code"] == "missing_fields"


def test_personal_recommendation_graph_adapter_finds_path():
    tree = {
        "n1": {"prerequisites": [], "outcomes": ["a"], "learning_time_est": 1},
        "n2": {"prerequisites": ["n1"], "outcomes": ["b"], "learning_time_est": 1},
        "n3": {"prerequisites": ["n2"], "outcomes": ["c"], "learning_time_est": 1},
    }
    adapter = InMemoryGraphAdapter(tree)
    state = {"knowledge": {}, "constraints": {"max_total_time": 10}}

    from tasks.personal_recommendation.candidate_generator import generate

    candidates = generate(
        ["n1"],
        ["c"],
        tree,
        state,
        L_max=4,
        T_max=10,
        K=5,
        graph_adapter=adapter,
    )

    paths = [candidate["path"] for candidate in candidates]
    assert any(path == ["n1", "n2", "n3"] for path in paths) or any("n3" in path for path in paths)
    assert adapter.get_stats().get("node_reads", 0) > 0


def test_personal_recommendation_agent_tools_keep_rag_outside_algorithm(monkeypatch):
    calls = {}

    def fake_search(query, graph_name=None, top_k=5):
        calls["search"] = {"query": query, "graph_name": graph_name, "top_k": top_k}
        return {
            "success": True,
            "query": query,
            "graph_name": graph_name,
            "top_k": top_k,
            "result_count": 1,
            "reasoning_paths": [{"path": ["intro", "ml_basic"]}],
            "paragraphs": ["mock context"],
            "context_text": "mock context",
            "error": "",
        }

    def fake_route(payload):
        calls["route_payload"] = payload
        return {
            "success": True,
            "candidates": [],
            "selected": [],
            "graph": {"nodes": [], "edges": []},
            "best_path": None,
            "error_code": "",
            "error_message": "",
        }

    monkeypatch.setattr(prat, "search_tool", fake_search)
    monkeypatch.setattr(prt_facade, "run_recommendation_route_from_payload", fake_route)
    state = {
        "payload": {
            "user_id": 123,
            "syllabus_id": 456,
            "goals": ["ml_basic"],
            "question": "What should I learn next?",
            "graph_name": "mock_graph",
        }
    }

    request_result = prat.tool_load_request_context(state)
    search_result = prat.tool_search_recommendation_context(state)
    route_result = prat.tool_run_recommendation_route(state)

    assert request_result["tool"] == "load_request_context"
    assert search_result["tool"] == "search_recommendation_context"
    assert route_result["tool"] == "run_recommendation_route"
    assert calls["search"]["graph_name"] == "mock_graph"
    assert "ml_basic" in calls["search"]["query"]
    assert "rag_context" in calls["route_payload"]


def test_personal_recommendation_mock_rag_route_graph_closes(monkeypatch):
    artifact_root = _reset_artifact_root("mock_rag_route_graph_closure")
    mock_rag = {
        "success": True,
        "query": "master machine learning",
        "graph_name": "mock_graph",
        "top_k": 5,
        "result_count": 2,
        "reasoning_paths": [
            {"path": ["n2", "n4"], "reason": "statistics supports machine learning"},
            {"path": ["n3", "n4"], "reason": "python supports machine learning practice"},
        ],
        "paragraphs": [
            "Statistics and Python are common foundations for machine learning.",
            "Deep learning follows the machine learning introduction.",
        ],
        "context_text": "mock recommendation context",
        "error": "",
    }
    state = {
        "payload": {
            "user_id": 123,
            "syllabus_id": 456,
            "goals": goals,
            "question": "What should I learn next for machine learning?",
            "graph_name": "mock_graph",
            "K": 10,
            "beam_width": 4,
        },
        "rag_context": mock_rag,
    }

    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: user_profile)
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)

    route_result = prat.tool_run_recommendation_route(state)
    result = state["recommendation_result"]

    assert route_result["tool"] == "run_recommendation_route"
    assert result["success"] is True
    assert result["graph"]["nodes"]
    assert result["graph"]["edges"]
    assert result["rag_overlay"]["enabled"] is True
    assert result["rag_overlay"]["matched_nodes"]
    assert result["candidates"]
    assert result["best_path"]
    assert "rag_relevance" in result["best_path"]

    graph_node_ids = {node["id"] for node in result["graph"]["nodes"]}
    graph_edge_ids = {edge["edge_id"] for edge in result["graph"]["edges"]}
    candidate_paths = {tuple(candidate["path"]) for candidate in result["candidates"]}
    rag_matched_nodes = [node for node in result["graph"]["nodes"] if node.get("rag_matched")]

    assert tuple(result["best_path"]["path"]) in candidate_paths
    assert set(result["best_path"]["path"]).issubset(graph_node_ids)
    assert rag_matched_nodes
    for edge in result["best_path"]["path_edges"]:
        assert edge["edge_id"] in graph_edge_ids
        assert edge["source"] in graph_node_ids
        assert edge["target"] in graph_node_ids

    for candidate in result["candidates"]:
        assert set(candidate["path"]).issubset(graph_node_ids)
        for edge in candidate["path_edges"]:
            assert edge["edge_id"] in graph_edge_ids

    _write_artifact(
        artifact_root,
        "route_result.json",
        {
            "test_name": "test_personal_recommendation_mock_rag_route_graph_closes",
            "mock_rag": mock_rag,
            "tool_result": route_result,
            "summary": _recommendation_summary(result),
            "recommendation": result,
        },
    )


def test_normalize_scores_inverts_lower_is_better_metrics():
    normalized = normalize_scores([
        {"E": 1.0, "D": 2.0, "R": 0.4, "P": 0.5},
        {"E": 2.0, "D": 4.0, "R": 0.8, "P": 0.5},
    ])

    assert normalized[0]["D"] == 1.0
    assert normalized[1]["D"] == 0.0
    assert normalized[0]["R"] == 1.0
    assert normalized[1]["R"] == 0.0
    assert "G" in normalized[0]
    assert "C" in normalized[0]


def test_build_recommendation_profile_normalizes_learning_profile(monkeypatch):
    raw_profile = {
        "user_id": 8,
        "learning_goal": "掌握 HBase RowKey 设计",
        "concept_gaps": ["rowkey_design"],
        "resource_preference": ["video", "practice"],
        "learning_style": "example-driven",
        "knowledge_mastery": {
            "by_knowledge_point": {"rowkey_design": 0.2},
            "knowledge_point_details": {
                "rowkey_design": {"score": 0.25, "confidence": 0.8},
            },
        },
    }
    monkeypatch.setattr(prt, "get_or_build_learning_profile", lambda *args, **kwargs: raw_profile)

    profile = prt.build_recommendation_profile(8, 20)

    assert profile["knowledge_levels"] == {"rowkey_design": 0.25}
    assert profile["learning_goals"] == ["掌握 HBase RowKey 设计", "rowkey_design"]
    assert profile["preferences"]["preferred_formats"] == ["video", "practice"]
    assert profile["preferences"]["learning_style"] == "example-driven"


def test_run_recommendation_route_uses_learning_profile_goal_fallback(monkeypatch):
    captured = {}

    def fake_generate(start_nodes, route_goals, learning_tree, state, **kwargs):
        captured["goals"] = list(route_goals)
        return []

    monkeypatch.setattr(
        prt,
        "build_recommendation_profile",
        lambda user_id, syllabus_id=None: {
            "knowledge_levels": {},
            "learning_goal": "rowkey_design",
            "learning_goals": ["rowkey_design"],
            "preferences": {},
            "constraints": {},
        },
    )
    monkeypatch.setattr(
        prt,
        "load_recommendation_learning_tree",
        lambda syllabus_id=None: {
            "n1": {"title": "RowKey 设计", "outcomes": ["rowkey_design"], "prerequisites": [], "learning_time_est": 1, "difficulty": 1},
        },
    )
    monkeypatch.setattr(prt, "generate", fake_generate)

    prt.run_recommendation_route(user_id=8, syllabus_id=20, goals=None)

    assert captured["goals"] == ["rowkey_design"]


def test_generate_state_accepts_learning_profile_mastery_schema():
    state, starts = generate_state(
        {
            "knowledge_mastery": {
                "knowledge_point_details": {
                    "data_basic": {"score": 1.0},
                    "stats_basic": {"score": 0.0},
                }
            }
        },
        {
            "n1": {"outcomes": ["data_basic"], "prerequisites": []},
            "n2": {"outcomes": ["stats_basic"], "prerequisites": []},
        },
    )

    assert state["knowledge"]["data_basic"] == 1.0
    assert "n2" in starts


def test_run_recommendation_route_from_payload_accepts_max_candidates_alias(monkeypatch):
    captured = {}

    def fake_route(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(prt, "run_recommendation_route", fake_route)

    prt.run_recommendation_route_from_payload({"user_id": 1, "max_candidates": 7})

    assert captured["K"] == 7


def test_recommendation_depth_strategy_rejects_unknown_value(monkeypatch):
    captured = {}

    def fake_generate(start_nodes, route_goals, learning_tree, state, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: user_profile)
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(prt, "generate", fake_generate)

    prt.run_recommendation_route_from_payload({"user_id": 1, "depth_strategy": "bad"})

    assert captured["depth_strategy"] == "balanced"


def test_study_graph_blocked_nodes_enter_constraints(monkeypatch):
    captured = {}

    def fake_generate(start_nodes, route_goals, learning_tree, state, **kwargs):
        captured["starts"] = list(start_nodes)
        captured["blocked"] = state.get("constraints", {}).get("blocked_nodes")
        return []

    tree = {
        "n1": {"title": "A", "outcomes": ["a"], "prerequisites": [], "learning_time_est": 1, "difficulty": 1},
        "n2": {"title": "B", "outcomes": ["b"], "prerequisites": [], "learning_time_est": 1, "difficulty": 1},
    }
    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: tree)
    monkeypatch.setattr(prt, "generate", fake_generate)

    prt.run_recommendation_route_from_payload(
        {
            "user_id": 1,
            "study_graph_state": {"blocked_node_ids": ["n2"], "completed_node_ids": ["n1"]},
        }
    )

    assert "n1" not in captured["starts"]
    assert "n2" not in captured["starts"]
    assert captured["blocked"] == ["n2"]


def test_planning_hints_ask_for_clarification_when_no_candidates(monkeypatch):
    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: {})

    result = prt.run_recommendation_route(user_id=1, goals=["unknown"])

    assert result["planning_hints"]["suggested_next_action"] == prt.NEXT_ACTION_ASK_GOAL_CLARIFICATION
