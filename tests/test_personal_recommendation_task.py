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
        assert isinstance(candidate["full_path"], list)
        assert isinstance(candidate["actionable_path"], list)
        assert isinstance(candidate["context_path"], list)
        assert isinstance(candidate["skills"], list)
        assert isinstance(candidate["path_edges"], list)
        assert isinstance(candidate["full_path_edges"], list)
        assert isinstance(candidate["path_depth"], int)
        assert "selected" in candidate
    if result["best_path"]:
        assert isinstance(result["best_path"]["path"], list)
        assert isinstance(result["best_path"]["full_path"], list)
        assert isinstance(result["best_path"]["actionable_path"], list)
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


def test_generate_state_does_not_start_from_unmet_prerequisite_target():
    state, starts = generate_state(
        {"knowledge_levels": {"data_basic": 1.0, "stats_basic": 0.0, "ml_basic": 0.0}},
        {
            "n1": {"outcomes": ["data_basic"], "prerequisites": []},
            "n2": {"outcomes": ["stats_basic"], "prerequisites": ["n1"]},
            "n4": {"outcomes": ["ml_basic"], "prerequisites": ["n2"]},
        },
    )


def test_rag_overlay_ignores_character_level_reasoning_edges():
    from tasks.personal_recommendation.rag_overlay import build_rag_overlay

    learning_tree = {
        "分布式文件系统及主流技术HDFS.Hadoop": {
            "id": "分布式文件系统及主流技术HDFS.Hadoop",
            "title": "Hadoop",
            "outcomes": ["Hadoop"],
        },
        "分布式数据库中典型技术HBase.Hadoop": {
            "id": "分布式数据库中典型技术HBase.Hadoop",
            "title": "HBase",
            "outcomes": ["HBase"],
        },
    }
    rag_context = {
        "success": True,
        "reasoning_paths": {
            "edges": [
                "Hadoop-HBase:  , d, e, f, l, m, n, o, p, t, v",
            ]
        },
        "paragraphs": [
            {"title": "Hadoop", "content": "Hadoop 是大数据生态组件。"},
            {"title": "HBase", "content": "HBase 是分布式数据库。"},
        ],
    }

    overlay = build_rag_overlay(rag_context, learning_tree)

    assert overlay["enabled"] is True
    assert overlay["temporary_edges"] == []


def test_recommendation_outputs_full_and_actionable_paths(monkeypatch):
    tree = {
        "n1": {"title": "Intro", "outcomes": ["data_basic"], "prerequisites": [], "learning_time_est": 1, "difficulty": 1},
        "n2": {"title": "Stats", "outcomes": ["stats_basic"], "prerequisites": ["n1"], "learning_time_est": 1, "difficulty": 1},
        "n4": {"title": "ML", "outcomes": ["ml_basic"], "prerequisites": ["n2"], "learning_time_est": 1, "difficulty": 1},
    }
    monkeypatch.setattr(
        prt,
        "build_recommendation_profile",
        lambda user_id, syllabus_id=None: {
            "knowledge_levels": {"data_basic": 1.0, "stats_basic": 0.0, "ml_basic": 0.0},
            "preferences": {},
            "constraints": {},
        },
    )
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: tree)

    result = prt.run_recommendation_route(user_id=8, goals=["ml_basic"], K=10, beam_width=4)

    assert result["best_path"]["path"] == ["n2", "n4"]
    assert result["best_path"]["context_path"] == ["n1"]
    assert result["best_path"]["full_path"] == ["n1", "n2", "n4"]
    assert result["best_path"]["actionable_path"] == ["n2", "n4"]
    assert result["best_path"]["full_path_edges"][0]["edge_id"] == "n1->n2"


def test_soft_prune_preserves_alternative_start_branches(monkeypatch):
    tree = {
        "n1": {"title": "Intro", "outcomes": ["data_basic"], "prerequisites": [], "learning_time_est": 1, "difficulty": 1},
        "n2": {"title": "Stats", "outcomes": ["stats_basic"], "prerequisites": ["n1"], "learning_time_est": 1, "difficulty": 1},
        "n3": {"title": "Python", "outcomes": ["python_basic"], "prerequisites": ["n1"], "learning_time_est": 1, "difficulty": 1},
        "n4": {"title": "ML", "outcomes": ["ml_basic"], "prerequisites": ["n2", "n3"], "learning_time_est": 1, "difficulty": 1},
    }
    monkeypatch.setattr(
        prt,
        "build_recommendation_profile",
        lambda user_id, syllabus_id=None: {
            "knowledge_levels": {"data_basic": 1.0, "stats_basic": 0.0, "python_basic": 0.0, "ml_basic": 0.0},
            "preferences": {},
            "constraints": {},
        },
    )
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: tree)

    result = prt.run_recommendation_route(user_id=8, goals=["ml_basic"], K=10, beam_width=4)
    candidate_paths = {tuple(candidate["path"]) for candidate in result["candidates"]}

    assert ("n2", "n4") in candidate_paths
    assert ("n3", "n4") in candidate_paths


def test_recommendation_route_uses_agent_decomposed_concepts(monkeypatch):
    syllabus_json = {
        "period": [
            {
                "week_index": "6",
                "content": "大数据存储与管理：分布式数据库中典型技术HBase",
                "enhanced_content": "HBase 是面向列、可伸缩的分布式数据库。",
            }
        ]
    }

    def fake_decomposer(payload):
        return {
            "concepts": [
                {"title": "HBase", "source_period": {"week_index": "6"}, "confidence": 0.9},
                {
                    "title": "RowKey",
                    "source_period": {"week_index": "6"},
                    "prerequisite_titles": ["HBase"],
                    "confidence": 0.86,
                },
            ],
            "edges": [{"source_title": "HBase", "target_title": "RowKey", "confidence": 0.8}],
        }

    monkeypatch.setattr(prt, "get_syllabus_by_id", lambda syllabus_id: type("Syllabus", (), {"syllabus_path": "unused"})())
    monkeypatch.setattr(prt, "load_json_file", lambda path: syllabus_json)
    monkeypatch.setattr(
        prt,
        "build_recommendation_profile",
        lambda user_id, syllabus_id=None: {
            "knowledge_levels": {},
            "preferences": {},
            "constraints": {"max_total_time": 30},
        },
    )

    result = prt.run_recommendation_route(
        user_id=8,
        syllabus_id=20,
        goals=["RowKey"],
        L_max=4,
        K=10,
        beam_width=4,
        concept_decomposer=fake_decomposer,
    )

    assert result["candidates"]
    assert result["best_path"]
    assert any("RowKey" in node_id for node_id in result["best_path"]["path"])
    graph_nodes = {node["id"]: node for node in result["graph"]["nodes"]}
    rowkey_node = next(node for node in graph_nodes.values() if node["title"] == "RowKey")
    assert rowkey_node["decomposition_method"] == "agent"
    assert rowkey_node["fallback_tag"] == ""
    diagnostics = result["debug"]["graph_diagnostics"]
    assert diagnostics["learning_tree"]["agent_node_count"] == 2
    assert diagnostics["recommendation_graph_tree"]["agent_node_count"] == 2
    assert diagnostics["output_graph"]["agent_node_count"] == 2
    assert diagnostics["output_graph"]["node_count"] == len(result["graph"]["nodes"])


def test_recommendation_route_reports_fallback_dependency(monkeypatch):
    tree = {
        "hbase": {
            "title": "HBase",
            "outcomes": ["HBase"],
            "prerequisites": [],
            "learning_time_est": 1,
            "difficulty": 1,
            "reliability": 0.8,
        },
        "hotspot": {
            "title": "热点规避",
            "outcomes": ["热点规避"],
            "prerequisites": ["hbase"],
            "learning_time_est": 1,
            "difficulty": 1,
            "decomposition_method": "rule_fallback",
            "fallback_tag": "period_concept_rule_implied_fallback",
            "implied": True,
            "reliability": 0.35,
            "edge_confidence": {"hbase": 0.35},
        },
    }
    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: tree)

    result = prt.run_recommendation_route(user_id=8, goals=["热点规避"], L_max=3, K=5, beam_width=3)

    assert result["best_path"]["fallback_dependency"]["has_fallback"] is True
    assert result["best_path"]["fallback_dependency"]["implied_fallback_node_count"] == 1
    assert result["best_path"]["fallback_dependency"]["suggested_agent_action"] == "reretrieve_and_retry"
    assert result["best_path"]["scores"]["C"] < 1.0


def test_run_recommendation_route_from_payload_accepts_max_candidates_alias(monkeypatch):
    captured = {}

    def fake_route(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(prt, "run_recommendation_route", fake_route)

    prt.run_recommendation_route_from_payload({"user_id": 1, "max_candidates": 7})

    assert captured["K"] == 7


def test_run_recommendation_route_from_payload_saves_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))

    def fake_route(**kwargs):
        return {
            "success": True,
            "graph": {"nodes": [{"id": "n1", "title": "Intro"}], "edges": []},
            "candidates": [{"path": ["n1"], "rank": 1}],
            "selected": [{"path": ["n1"]}],
            "best_path": {"path": ["n1"]},
            "error_code": "",
            "error_message": "",
        }

    monkeypatch.setattr(prt, "run_recommendation_route", fake_route)

    result = prt.run_recommendation_route_from_payload({"user_id": 8, "syllabus_id": 20, "goals": ["intro"]})

    assert result["recommendation_id"]
    assert result["snapshot_status"] == prt_facade.RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED
    detail = prt_facade.get_recommendation_snapshot(result["recommendation_id"])
    assert detail["success"] is True
    assert detail["snapshot"]["recommendation"]["graph"]["nodes"][0]["id"] == "n1"


def test_run_recommendation_route_from_payload_can_disable_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    monkeypatch.setattr(
        prt,
        "run_recommendation_route",
        lambda **kwargs: {
            "success": True,
            "graph": {"nodes": [{"id": "n1"}], "edges": []},
            "candidates": [],
            "selected": [],
            "best_path": None,
        },
    )

    result = prt.run_recommendation_route_from_payload({"user_id": 8, "syllabus_id": 20, "persist_snapshot": False})

    assert "recommendation_id" not in result
    assert prt_facade.list_recommendation_snapshots(8, 20)["snapshots"] == []


def test_ensure_recommendation_snapshot_backfills_injected_result(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    result = {
        "success": True,
        "graph": {"nodes": [{"id": "n1"}], "edges": []},
        "candidates": [{"path": ["n1"]}],
        "selected": [],
        "best_path": {"path": ["n1"]},
    }

    prt.ensure_recommendation_snapshot(8, 20, result, request_payload={"message": "recommend"})
    first_id = result["recommendation_id"]
    prt.ensure_recommendation_snapshot(8, 20, result, request_payload={"message": "recommend"})

    assert result["recommendation_id"] == first_id
    assert len(prt_facade.list_recommendation_snapshots(8, 20)["snapshots"]) == 1


def test_ensure_recommendation_snapshot_can_resave_proposed(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    result = {
        "success": True,
        "graph": {"nodes": [{"id": "n1"}], "edges": []},
        "candidates": [{"path": ["n1"]}],
        "selected": [],
        "best_path": {"path": ["n1"]},
    }

    prt.ensure_recommendation_snapshot(8, 20, result, request_payload={"message": "recommend"})
    first_id = result["recommendation_id"]
    prt.ensure_recommendation_snapshot(
        8,
        20,
        result,
        request_payload={"message": "recommend again"},
        allow_proposed_resave=True,
    )

    assert result["recommendation_id"] != first_id
    assert len(prt_facade.list_recommendation_snapshots(8, 20)["snapshots"]) == 2


def test_ensure_recommendation_snapshot_does_not_resave_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    result = {
        "success": True,
        "graph": {"nodes": [{"id": "n1"}], "edges": []},
        "candidates": [{"path": ["n1"]}],
        "selected": [],
        "best_path": {"path": ["n1"]},
    }

    prt.ensure_recommendation_snapshot(8, 20, result, request_payload={"message": "recommend"})
    first_id = result["recommendation_id"]
    result["snapshot_status"] = prt_facade.RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED
    prt.ensure_recommendation_snapshot(8, 20, result, allow_proposed_resave=True)

    assert result["recommendation_id"] == first_id
    assert len(prt_facade.list_recommendation_snapshots(8, 20)["snapshots"]) == 1


def test_run_recommendation_route_from_payload_auto_injects_agent_decomposer_with_rag(monkeypatch):
    captured = {}

    def fake_load(syllabus_id=None, *, concept_decomposer=None, rag_context=None):
        captured["concept_decomposer"] = concept_decomposer
        captured["rag_context"] = rag_context
        return {
            "n1": {
                "title": "Intro",
                "outcomes": ["intro"],
                "prerequisites": [],
                "learning_time_est": 1,
                "difficulty": 1,
            }
        }

    monkeypatch.setattr(prt, "load_recommendation_learning_tree", fake_load)
    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})

    result = prt.run_recommendation_route_from_payload(
        {
            "user_id": 1,
            "syllabus_id": 20,
            "goals": ["intro"],
            "rag_context": {"success": True, "paragraphs": []},
        }
    )

    assert result["success"] is True
    assert callable(captured["concept_decomposer"])
    assert captured["rag_context"]["success"] is True


def test_run_recommendation_route_agent_decomposer_mode_rejects_silent_fallback(monkeypatch):
    def fake_load(syllabus_id=None, *, concept_decomposer=None, rag_context=None):
        return {
            "n1": {
                "title": "Intro",
                "outcomes": ["intro"],
                "prerequisites": [],
                "learning_time_est": 1,
                "difficulty": 1,
                "decomposition_method": "rule_fallback",
                "fallback_tag": "period_concept_rule_fallback",
            }
        }

    monkeypatch.setattr(prt, "load_recommendation_learning_tree", fake_load)

    result = prt.run_recommendation_route_from_payload(
        {
            "user_id": 1,
            "syllabus_id": 20,
            "goals": ["intro"],
            "rag_context": {"success": True, "paragraphs": []},
            "decomposer_mode": "agent",
        }
    )

    assert result["success"] is False
    assert result["error_code"] == "agent_decomposer_required"
    assert result["candidates"] == []


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


def test_recommendation_falls_back_to_path_when_generator_returns_no_candidates(monkeypatch):
    learning_tree = {
        "n1": {"title": "Intro", "outcomes": ["intro"], "prerequisites": [], "difficulty": 1, "learning_time_est": 1},
        "n2": {"title": "Core", "outcomes": ["core"], "prerequisites": ["n1"], "difficulty": 2, "learning_time_est": 1},
        "n3": {"title": "Goal", "outcomes": ["goal"], "prerequisites": ["n2"], "difficulty": 3, "learning_time_est": 1},
    }
    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(prt, "generate", lambda *args, **kwargs: [])

    result = prt.run_recommendation_route(user_id=1, syllabus_id=2, goals=["goal"])

    assert result["success"] is True
    assert result["candidates"]
    assert result["best_path"]
    assert result["best_path"]["path"]
    assert result["planning_hints"]["suggested_next_action"] != prt.NEXT_ACTION_ASK_GOAL_CLARIFICATION


def test_recommendation_fallback_prioritizes_earlier_chapters(monkeypatch):
    learning_tree = {
        "late": {
            "title": "Late Goal",
            "outcomes": ["goal"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "source_period": {"week_index": "6"},
        },
        "early": {
            "title": "Foundation",
            "outcomes": ["foundation"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "source_period": {"week_index": "1"},
        },
    }
    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(prt, "generate", lambda *args, **kwargs: [])

    result = prt.run_recommendation_route(user_id=1, syllabus_id=2, goals=["goal"])

    assert result["best_path"]["path"][0] == "early"


def test_recommendation_gap_ranking_prioritizes_earlier_candidates(monkeypatch):
    learning_tree = {
        "early": {
            "title": "Foundation",
            "outcomes": ["foundation"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "source_period": {"week_index": "1"},
        },
        "middle": {
            "title": "Middle",
            "outcomes": ["middle"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "source_period": {"week_index": "3"},
        },
        "late": {
            "title": "Late",
            "outcomes": ["late"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "source_period": {"week_index": "6"},
        },
    }

    def fake_generate(*args, **kwargs):
        return [
            {"path": ["late"], "cost": 1, "skills": {"late"}, "path_depth": 1},
            {"path": ["early"], "cost": 1, "skills": {"foundation"}, "path_depth": 1},
            {"path": ["middle"], "cost": 1, "skills": {"middle"}, "path_depth": 1},
        ]

    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(prt, "generate", fake_generate)

    result = prt.run_recommendation_route(
        user_id=1,
        syllabus_id=2,
        goals=["late"],
        study_graph_state={"completed_node_ids": ["late"]},
    )

    assert [candidate["path"][0] for candidate in result["candidates"]] == ["early", "middle"]
    assert len(result["candidates"]) <= prt.DEFAULT_RECOMMENDATION_CANDIDATE_LIMIT
    assert result["best_path"]["path"][0] == "early"


def test_recommendation_prefers_syllabus_linear_route_over_similarity_jump(monkeypatch):
    learning_tree = {
        "w1": {
            "title": "Week 1",
            "outcomes": ["foundation"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "1",
        },
        "w2": {
            "title": "Week 2",
            "outcomes": ["middle"],
            "prerequisites": ["w1"],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "2",
            "edge_sources": {"w1": "syllabus"},
        },
        "w3": {
            "title": "Week 3",
            "outcomes": ["goal"],
            "prerequisites": ["w2", "similar"],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "3",
            "edge_sources": {"w2": "syllabus", "similar": "rag"},
            "edge_confidence": {"w2": 1.0, "similar": 0.6},
        },
        "similar": {
            "title": "Similar Knowledge",
            "outcomes": ["related"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "8",
        },
    }

    def fake_generate(*args, **kwargs):
        return [
            {"path": ["similar", "w3"], "cost": 2, "skills": {"related", "goal"}, "path_depth": 2},
            {"path": ["w1", "w2", "w3"], "cost": 3, "skills": {"foundation", "middle", "goal"}, "path_depth": 3},
        ]

    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(prt, "generate", fake_generate)

    result = prt.run_recommendation_route(user_id=1, syllabus_id=2, goals=["goal"])

    assert result["best_path"]["path"] == ["w1", "w2", "w3"]
    assert result["candidates"][0]["path"] == ["w1", "w2", "w3"]


def test_recommendation_outputs_two_stage_route_and_display_labels(monkeypatch):
    learning_tree = {
        "chapter_1": {
            "title": "数据采集",
            "outcomes": ["data_collection"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "1",
            "node_source": "syllabus_period",
            "decomposition_method": "period_anchor",
        },
        "chapter_2": {
            "title": "分布式存储",
            "outcomes": ["distributed_storage"],
            "prerequisites": ["chapter_1"],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "2",
            "node_source": "syllabus_period",
            "decomposition_method": "period_anchor",
            "edge_sources": {"chapter_1": "syllabus"},
        },
        "chapter_2.hdfs": {
            "title": "HDFS",
            "outcomes": ["HDFS"],
            "prerequisites": ["chapter_2"],
            "difficulty": 1,
            "learning_time_est": 1,
            "node_source": "syllabus_period_concept",
            "decomposition_method": "agent",
            "source_period": {"week_index": "2", "title": "分布式存储", "node_id": "chapter_2"},
            "edge_sources": {"chapter_2": "agent"},
        },
    }

    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(
        prt,
        "generate",
        lambda *args, **kwargs: [{"path": ["chapter_2.hdfs"], "cost": 1, "skills": {"HDFS"}, "path_depth": 1}],
    )

    result = prt.run_recommendation_route(user_id=1, syllabus_id=2, goals=["HDFS"])

    assert result["best_path"]["route_structure"] == "chapter_backbone_then_knowledge_expansion"
    assert result["best_path"]["chapter_backbone"][0]["node_id"] == "chapter_2"
    assert result["best_path"]["knowledge_expansion"][0]["knowledge_node_ids"] == ["chapter_2.hdfs"]
    assert result["best_path"]["path_nodes"][0]["learning_time_est"] == 1
    assert result["best_path"]["path_nodes"][0]["display_type"] == "chapter"
    assert result["best_path"]["path_nodes"][-1]["display_type"] == "knowledge"
    assert result["candidates"][0]["path_nodes"][0]["difficulty"] == 1
    assert result["selected"][0]["full_path_nodes"]
    node_by_id = {node["id"]: node for node in result["graph"]["nodes"]}
    assert node_by_id["chapter_2"]["display_type"] == "chapter"
    assert node_by_id["chapter_2.hdfs"]["display_type"] == "knowledge"
    assert node_by_id["chapter_2"]["display_group"] == "章节骨干"
    assert node_by_id["chapter_2.hdfs"]["display_group"] == "知识点发散"


def test_two_stage_route_expands_multiple_prioritized_knowledge_nodes(monkeypatch):
    learning_tree = {
        "chapter_1": {
            "title": "HBase",
            "outcomes": ["HBase"],
            "prerequisites": [],
            "difficulty": 1,
            "learning_time_est": 1,
            "week_index": "1",
            "node_source": "syllabus_period",
            "decomposition_method": "period_anchor",
        },
        "chapter_1.rowkey": {
            "title": "RowKey",
            "outcomes": ["RowKey"],
            "prerequisites": ["chapter_1"],
            "difficulty": 1,
            "learning_time_est": 1,
            "node_source": "syllabus_period_concept",
            "decomposition_method": "agent",
            "study_graph_state": "weak",
            "source_period": {"week_index": "1", "node_id": "chapter_1"},
        },
        "chapter_1.region": {
            "title": "Region",
            "outcomes": ["Region"],
            "prerequisites": ["chapter_1"],
            "difficulty": 1,
            "learning_time_est": 1,
            "node_source": "syllabus_period_concept",
            "decomposition_method": "agent",
            "source_period": {"week_index": "1", "node_id": "chapter_1"},
        },
        "chapter_1.column_family": {
            "title": "Column Family",
            "outcomes": ["Column Family"],
            "prerequisites": ["chapter_1"],
            "difficulty": 1,
            "learning_time_est": 1,
            "node_source": "syllabus_period_concept",
            "decomposition_method": "agent",
            "source_period": {"week_index": "1", "node_id": "chapter_1"},
        },
    }

    monkeypatch.setattr(prt, "build_recommendation_profile", lambda user_id, syllabus_id=None: {"knowledge_levels": {}, "preferences": {}, "constraints": {}})
    monkeypatch.setattr(prt, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)
    monkeypatch.setattr(
        prt,
        "generate",
        lambda *args, **kwargs: [{"path": ["chapter_1"], "cost": 1, "skills": {"HBase"}, "path_depth": 1}],
    )

    result = prt.run_recommendation_route(
        user_id=1,
        syllabus_id=2,
        goals=["Region"],
        L_max=6,
        study_graph_state={"weak_node_ids": ["chapter_1.rowkey"]},
    )

    expansion = result["best_path"]["knowledge_expansion"][0]
    assert expansion["knowledge_count"] == 2
    assert expansion["knowledge_node_ids"] == ["chapter_1.rowkey", "chapter_1.region"]
    assert "chapter_1.column_family" not in result["best_path"]["path"]


def test_load_recommendation_learning_tree_marks_sample_fallback(monkeypatch):
    monkeypatch.setattr(prt, "get_syllabus_by_id", lambda syllabus_id: None)

    tree = prt.load_recommendation_learning_tree(999)

    assert tree
    assert {node.get("node_source") for node in tree.values()} == {prt.NODE_SOURCE_SAMPLE_FALLBACK}
    assert all(node.get("fallback_reason") == "missing_syllabus_path" for node in tree.values())
