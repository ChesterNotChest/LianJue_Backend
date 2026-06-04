import json
from pathlib import Path

import pytest

from tasks import personal_recommendation_task as prt
from tasks import total_agent_task as tat
from tasks import learning_profile_task as lpt
from tasks.learning_profile import storage as profile_storage
from tasks.total_agent import agent_contracts as tac
from tasks.total_agent import agent_runtime as tar
from tasks.total_agent import agent_tools as tagt


ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts" / "total_agent"


def _recommendation_fixture() -> dict:
    return {
        "success": True,
        "best_path": {
            "path": ["hbase_intro", "rowkey_design"],
            "skills": ["hbase", "rowkey", "hotspot"],
        },
        "candidates": [
            {
                "path": ["hbase_intro", "rowkey_design"],
                "skills": ["hbase", "rowkey", "hotspot"],
            }
        ],
        "graph": {
            "nodes": [
                {
                    "id": "hbase_intro",
                    "title": "HBase Basics",
                    "outcomes": ["hbase"],
                },
                {
                    "id": "rowkey_design",
                    "title": "HBase RowKey Design",
                    "outcomes": ["rowkey_design", "rowkey_hotspot_avoidance"],
                },
            ],
            "edges": [{"source": "hbase_intro", "target": "rowkey_design"}],
        },
        "error_code": "",
        "error_message": "",
    }


def _reset_learning_plan_root(monkeypatch, tmp_path):
    root = tmp_path / "personal_recommendation"
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(root))
    return root


def _accept_plan(user_id: int = 8, syllabus_id: int = 20) -> dict:
    result = prt.accept_recommendation_path(
        user_id=user_id,
        syllabus_id=syllabus_id,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert result["success"] is True
    return result["plan"]


def _fake_generation(request_payload: dict) -> dict:
    return {
        "success": True,
        "resources": [
            {
                "resource_id": "documents-total-agent-test",
                "resource_type": "documents",
                "status": "ready",
                "topic": request_payload.get("topic"),
            }
        ],
    }


def _write_artifact(name: str, payload: dict) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_ROOT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_total_agent_returns_structured_error_for_missing_user_id():
    result = tat.run_total_agent({"message": "continue"})

    assert result["success"] is False
    assert result["schema_version"] == tac.TOTAL_AGENT_SCHEMA_VERSION
    assert result["error_code"] == "missing_user_id"
    assert result["tool_trace"] == [tac.TOOL_LOAD_TOTAL_CONTEXT]


def test_total_agent_agent_final_result_includes_loaded_context():
    context = {
        "success": True,
        "profile_summary": {
            "profile_source": tac.PROFILE_SOURCE_PERSISTED,
            "preferred_formats": ["documents", "quiz"],
        },
        "study_graph_state": {"weak_node_ids": ["hbase_intro"]},
    }
    state = {
        "tool_trace": [tac.TOOL_LOAD_TOTAL_CONTEXT, tac.TOOL_INFER_USER_INTENT, tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE],
        "intent": tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE,
        "intent_result": {"intent": tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE},
        "total_context": context,
        "terminal_tool_result": {
            "tool": tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE,
            "success": True,
            "resource_strategy": {"profile_source": tac.PROFILE_SOURCE_PERSISTED},
        },
    }

    result = tar._build_agent_final_result(state)

    assert result["success"] is True
    assert result["result"]["context"]["profile_summary"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert result["result"]["resource_generation"]["resource_strategy"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED


def test_total_agent_agent_final_result_uses_record_feedback_state_fallback():
    state = {
        "tool_trace": [tac.TOOL_LOAD_TOTAL_CONTEXT, tac.TOOL_INFER_USER_INTENT, tac.TOOL_RECORD_LEARNING_FEEDBACK],
        "intent": tac.INTENT_RECORD_LEARNING_FEEDBACK,
        "intent_result": {"intent": tac.INTENT_RECORD_LEARNING_FEEDBACK},
        "total_context": {"profile_summary": {"profile_source": tac.PROFILE_SOURCE_PERSISTED}},
        "terminal_tool_result": {},
        "record_learning_feedback_result": {
            "tool": tac.TOOL_RECORD_LEARNING_FEEDBACK,
            "success": True,
            "updated_step": {"status": prt.LEARNING_PLAN_STEP_STATUS_COMPLETED},
            "activated_step": {"status": prt.LEARNING_PLAN_STEP_STATUS_ACTIVE},
            "suggested_next_action": tac.ACTION_GENERATE_CURRENT_STEP_RESOURCE,
        },
    }

    result = tar._build_agent_final_result(state)

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_RECORD_LEARNING_FEEDBACK
    assert result["suggested_next_action"] == tac.ACTION_GENERATE_CURRENT_STEP_RESOURCE
    assert result["result"]["record_learning_feedback"]["updated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED


def test_total_agent_recommendation_waits_for_user_acceptance(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    payload = {
        "user_id": 8,
        "syllabus_id": 20,
        "message": "recommend a RowKey learning path",
        "recommendation_result": _recommendation_fixture(),
    }

    result = tat.run_total_agent(payload)
    active_plan = prt.get_active_learning_plan(8, 20)

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_RECOMMEND_LEARNING_PATH
    assert result["suggested_next_action"] == tac.ACTION_WAIT_USER_ACCEPTANCE
    assert active_plan is None
    assert result["tool_trace"] == [
        tac.TOOL_LOAD_TOTAL_CONTEXT,
        tac.TOOL_INFER_USER_INTENT,
        tac.TOOL_RUN_LEARNING_RECOMMENDATION,
    ]


def test_total_agent_accepts_learning_plan_only_with_confirmation(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)

    waiting = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "intent": tac.INTENT_ACCEPT_RECOMMENDATION,
            "message": "maybe this path",
            "recommendation_result": _recommendation_fixture(),
            "candidate_index": 0,
        }
    )
    assert waiting["success"] is True
    assert waiting["suggested_next_action"] == tac.ACTION_WAIT_USER_ACCEPTANCE
    assert prt.get_active_learning_plan(8, 20) is None

    accepted = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "confirm this path",
            "recommendation_result": _recommendation_fixture(),
            "candidate_index": 0,
            "auto_accept": True,
        }
    )
    active_plan = prt.get_active_learning_plan(8, 20)

    assert accepted["success"] is True
    assert accepted["intent"] == tac.INTENT_ACCEPT_RECOMMENDATION
    assert accepted["suggested_next_action"] == tac.ACTION_GENERATE_CURRENT_STEP_RESOURCE
    assert active_plan and active_plan["steps"][0]["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE


def test_total_agent_history_driven_continue_generates_current_step_resource(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "continue learning",
            "resource_types": ["documents"],
        }
    )
    resource_generation = result["result"]["resource_generation"]

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert result["suggested_next_action"] == tac.ACTION_RECORD_LEARNING_FEEDBACK
    assert resource_generation["resources"][0]["resource_type"] == "documents"
    assert resource_generation["request"]["topic"] == "HBase Basics"
    assert result["tool_trace"] == tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE]


def test_total_agent_feedback_advances_to_next_step(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    plan = _accept_plan()
    first_step = plan["steps"][0]

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "I completed the document",
            "step_id": first_step["step_id"],
            "resource_id": "documents-total-agent-test",
            "status": "completed",
        }
    )
    active_plan = prt.get_active_learning_plan(8, 20)
    statuses = {step["node_id"]: step["status"] for step in active_plan["steps"]}

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_RECORD_LEARNING_FEEDBACK
    assert statuses["hbase_intro"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    assert statuses["rowkey_design"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
    assert result["result"]["next_task"]["next_task"]["node_id"] == "rowkey_design"


def test_total_agent_skip_advances_to_next_step(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    plan = _accept_plan()
    first_step = plan["steps"][0]

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "skip this step",
            "step_id": first_step["step_id"],
        }
    )
    active_plan = prt.get_active_learning_plan(8, 20)
    statuses = {step["node_id"]: step["status"] for step in active_plan["steps"]}

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_SKIP_CURRENT_STEP
    assert statuses["hbase_intro"] == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED
    assert statuses["rowkey_design"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE


def test_total_agent_insufficient_goal_asks_for_clarification(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "",
        }
    )

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_ASK_GOAL_CLARIFICATION
    assert result["suggested_next_action"] == tac.ACTION_ASK_GOAL_CLARIFICATION


def test_total_agent_writes_contract_artifact(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    captured_requests = []

    def fake_generation(request_payload: dict) -> dict:
        captured_requests.append(request_payload)
        return _fake_generation(request_payload)

    monkeypatch.setattr(tagt, "generate_resources_from_request", fake_generation)
    monkeypatch.setattr(lpt, "get_persisted_learning_profile", lambda user_id, syllabus_id: None)
    monkeypatch.setattr(tagt, "get_study_graph_features", lambda user_id, syllabus_id: {})

    missing_profile_result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "continue learning",
            "resource_types": ["documents"],
        }
    )

    monkeypatch.setattr(
        lpt,
        "get_persisted_learning_profile",
        lambda user_id, syllabus_id: {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": ["RowKey 热点"],
            "preferences": {"preferred_formats": ["documents", "quiz"]},
            "risk_level": "medium",
            "time_budget": {"minutes_per_day": 30},
        },
    )
    monkeypatch.setattr(
        tagt,
        "get_study_graph_features",
        lambda user_id, syllabus_id: {"weak_node_ids": ["hbase_intro"]},
    )

    profile_injected_result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "continue learning, give me practice",
        }
    )

    _write_artifact(
        "total_agent_deterministic_result.json",
        {
            "test_name": "test_total_agent_writes_contract_artifact",
            "missing_profile_case": {
                "description": "No persisted profile is available; runtime returns empty profile_summary with warnings and does not mock profile data.",
                "result": missing_profile_result,
                "captured_request": captured_requests[0],
            },
            "profile_injected_case": {
                "description": "Test side injects a persisted profile through learning_profile_task; formal Total Agent consumes it and changes resource strategy.",
                "result": profile_injected_result,
                "captured_request": captured_requests[1],
            },
            "comparison": {
                "missing_profile_source": missing_profile_result["result"]["context"]["profile_summary"]["profile_source"],
                "profile_injected_source": profile_injected_result["result"]["context"]["profile_summary"]["profile_source"],
                "missing_resource_types": missing_profile_result["result"]["resource_generation"]["resource_strategy"]["resource_types"],
                "profile_injected_resource_types": profile_injected_result["result"]["resource_generation"]["resource_strategy"]["resource_types"],
                "profile_injected_difficulty": profile_injected_result["result"]["resource_generation"]["resource_strategy"]["difficulty"],
            },
        },
    )

    assert missing_profile_result["success"] is True
    assert profile_injected_result["success"] is True
    assert missing_profile_result["result"]["context"]["profile_summary"]["profile_source"] == tac.PROFILE_SOURCE_NONE
    assert profile_injected_result["result"]["context"]["profile_summary"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert profile_injected_result["result"]["resource_generation"]["resource_strategy"]["resource_types"][:2] == [
        "documents",
        "quiz",
    ]


def test_total_agent_load_profile_summary_reads_persisted_profile(monkeypatch):
    monkeypatch.setattr(
        lpt,
        "get_persisted_learning_profile",
        lambda user_id, syllabus_id: {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": ["RowKey 热点"],
            "preferences": {"preferred_formats": ["documents", "quiz"]},
            "risk_level": "medium",
            "updated_at": 1760000000,
        },
    )

    result = tagt.load_profile_summary({"user_id": 8, "syllabus_id": 20})
    summary = tagt.normalize_profile_summary(result)

    assert result["success"] is True
    assert result["source"] == tac.PROFILE_SOURCE_PERSISTED
    assert summary["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert summary["preferred_formats"] == ["documents", "quiz"]
    assert result["profile"]["weak_points"] == ["RowKey 热点"]


def test_total_agent_profile_summary_aligns_with_real_profile_agent_output():
    summary = tagt.normalize_profile_summary(
        {
            "profile_source": tac.PROFILE_SOURCE_PERSISTED,
            "learning_goal": "掌握 HBase RowKey 热点规避和预分区策略",
            "concept_gaps": ["RowKey 热点", "预分区"],
            "bottleneck_topics": ["Region 划分"],
            "resource_preference": ["practice", "theory", "visual", "code"],
            "knowledge_mastery": {
                "knowledge_point_details": {
                    "HBase 数据模型": {"score": 1.0, "level": "high"},
                    "加盐前缀": {"score": 0.0, "level": "low"},
                }
            },
            "dropout_risk": "low",
        }
    )

    assert summary["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert summary["weak_points"] == ["RowKey 热点", "预分区", "加盐前缀"]
    assert summary["preferred_formats"] == ["quiz", "documents", "mindmap", "coding_practice"]
    assert summary["risk_level"] == "low"


def test_total_agent_reads_profile_saved_by_profile_storage(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(profile_storage, "set_personal_profile_path", lambda user_id, syllabus_id, path: True)
    saved = profile_storage.save_personal_profile(
        8,
        20,
        {
            "user_id": 8,
            "syllabus_id": 20,
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": ["RowKey 热点"],
            "preferences": {"preferred_formats": ["documents", "quiz"]},
            "risk_level": "medium",
        },
    )

    result = tagt.load_profile_summary({"user_id": 8, "syllabus_id": 20})
    summary = tagt.normalize_profile_summary(result)

    assert saved and Path(saved["profile_path"]).exists()
    assert result["success"] is True
    assert result["source"] == tac.PROFILE_SOURCE_PERSISTED
    assert summary["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert summary["weak_points"] == ["RowKey 热点"]
    assert summary["preferred_formats"] == ["documents", "quiz"]
    _write_artifact(
        "total_agent_persisted_profile_read_result.json",
        {
            "test_name": "test_total_agent_reads_profile_saved_by_profile_storage",
            "saved_profile_path": saved["profile_path"],
            "profile_read": result,
            "profile_summary": summary,
        },
    )


def test_total_agent_load_profile_summary_missing_profile_is_empty_warning(monkeypatch):
    monkeypatch.setattr(lpt, "get_persisted_learning_profile", lambda user_id, syllabus_id: None)

    result = tagt.load_profile_summary({"user_id": 8, "syllabus_id": 20})
    summary = tagt.normalize_profile_summary(result)

    assert result["success"] is False
    assert result["source"] == tac.PROFILE_SOURCE_NONE
    assert summary["profile_source"] == tac.PROFILE_SOURCE_NONE
    assert summary["weak_points"] == []
    assert tac.PROFILE_WARNING_NOT_FOUND in result["warnings"]
    assert tac.PROFILE_WARNING_BUILD_SKIPPED in result["warnings"]
    serialized = json.dumps(result, ensure_ascii=False)
    assert "HBase" not in serialized
    assert "RowKey" not in serialized


def test_total_agent_load_profile_summary_build_if_missing_opt_in(monkeypatch):
    monkeypatch.setattr(lpt, "get_persisted_learning_profile", lambda user_id, syllabus_id: None)
    monkeypatch.setattr(
        lpt,
        "get_or_build_learning_profile",
        lambda user_id, syllabus_id, **kwargs: {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "learning_goal": "built goal",
            "preferences": {"preferred_formats": ["quiz"]},
        },
    )

    result = tagt.load_profile_summary(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "profile_read_action": tac.PROFILE_READ_ACTION_BUILD_IF_MISSING,
        }
    )
    summary = tagt.normalize_profile_summary(result)

    assert result["success"] is True
    assert result["source"] == tac.PROFILE_SOURCE_BUILT
    assert summary["profile_source"] == tac.PROFILE_SOURCE_BUILT
    assert summary["preferred_formats"] == ["quiz"]


def test_total_agent_load_profile_summary_read_failure_does_not_mock(monkeypatch):
    def fail_profile(user_id, syllabus_id):
        raise RuntimeError("profile store unavailable")

    monkeypatch.setattr(lpt, "get_persisted_learning_profile", fail_profile)

    result = tagt.load_profile_summary({"user_id": 8, "syllabus_id": 20})
    summary = tagt.normalize_profile_summary(result)

    assert result["success"] is False
    assert result["source"] == tac.PROFILE_SOURCE_NONE
    assert result["error_code"] == tac.PROFILE_WARNING_READ_FAILED
    assert summary["profile_source"] == tac.PROFILE_SOURCE_NONE
    assert summary["preferred_formats"] == []
    serialized = json.dumps(result, ensure_ascii=False)
    assert "HBase" not in serialized
    assert "RowKey" not in serialized


def test_total_agent_load_context_includes_profile_summary(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    monkeypatch.setattr(
        lpt,
        "get_persisted_learning_profile",
        lambda user_id, syllabus_id: {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": ["RowKey 热点"],
            "preferences": {"preferred_formats": ["documents", "quiz"]},
            "risk_level": "medium",
            "time_budget": {"minutes_per_day": 30},
            "updated_at": 1760000000,
        },
    )
    monkeypatch.setattr(tagt, "get_study_graph_features", lambda user_id, syllabus_id: {})

    state = {"payload": {"user_id": 8, "syllabus_id": 20, "message": "continue"}, "tool_trace": []}
    context = tagt.tool_load_total_context(state)

    assert context["success"] is True
    assert context["profile_summary"]["learning_goal"] == "掌握 HBase RowKey 热点规避"
    assert context["profile_summary"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert context["profile_summary"]["preferred_formats"] == ["documents", "quiz"]
    assert state["total_context"]["profile_summary"]["weak_points"] == ["RowKey 热点"]


def test_total_agent_load_context_includes_normalized_study_graph_state(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    monkeypatch.setattr(lpt, "get_persisted_learning_profile", lambda user_id, syllabus_id: None)
    monkeypatch.setattr(
        tagt,
        "get_study_graph_features",
        lambda user_id, syllabus_id: {
            "current_node_id": "rowkey_design",
            "completed_node_ids": ["hbase_intro"],
            "weak_node_ids": ["rowkey_design"],
            "mastered_node_ids": [],
            "recent_node_ids": ["hbase_intro"],
            "stale_node_ids": ["rowkey_design"],
        },
    )

    state = {"payload": {"user_id": 8, "syllabus_id": 20, "message": "continue"}, "tool_trace": []}
    context = tagt.tool_load_total_context(state)

    assert context["success"] is True
    assert context["study_graph_state"]["current_node_id"] == "rowkey_design"
    assert context["study_graph_state"]["completed_node_ids"] == ["hbase_intro"]
    assert context["study_graph_state"]["weak_node_ids"] == ["rowkey_design"]
    assert context["study_graph_state"]["stale_node_ids"] == ["rowkey_design"]


def test_total_agent_context_read_failures_are_warnings(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()

    def fail_profile(user_id, syllabus_id):
        raise RuntimeError("profile unavailable")

    def fail_graph(user_id, syllabus_id):
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(lpt, "get_persisted_learning_profile", fail_profile)
    monkeypatch.setattr(tagt, "get_study_graph_features", fail_graph)

    state = {"payload": {"user_id": 8, "syllabus_id": 20, "message": "continue"}, "tool_trace": []}
    context = tagt.tool_load_total_context(state)

    assert context["success"] is True
    assert context["next_task"]["node_id"] == "hbase_intro"
    assert context["profile_summary"]["weak_points"] == []
    assert any("profile_read_failed" in item for item in context["warnings"])
    assert any("study_graph_read_failed" in item for item in context["warnings"])
    assert any("study_graph_read_failed" in item for item in context["study_graph_state"]["warnings"])


def test_total_agent_resource_strategy_uses_profile_and_study_graph(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    captured = {}

    def fake_generation(request_payload: dict) -> dict:
        captured["request"] = request_payload
        return _fake_generation(request_payload)

    monkeypatch.setattr(tagt, "generate_resources_from_request", fake_generation)
    monkeypatch.setattr(
        lpt,
        "get_persisted_learning_profile",
        lambda user_id, syllabus_id: {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "weak_points": ["RowKey 热点"],
            "preferences": {"preferred_formats": ["documents", "quiz"]},
        },
    )
    monkeypatch.setattr(
        tagt,
        "get_study_graph_features",
        lambda user_id, syllabus_id: {"weak_node_ids": ["hbase_intro"]},
    )

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "continue learning, give me practice",
        }
    )
    resource_generation = result["result"]["resource_generation"]

    assert result["success"] is True
    assert resource_generation["resource_strategy"]["resource_types"][:2] == ["documents", "quiz"]
    assert resource_generation["resource_strategy"]["difficulty"] == tac.RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    assert captured["request"]["resource_types"][:2] == ["documents", "quiz"]
    assert captured["request"]["resource_strategy"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert captured["request"]["strategy_signals"]["matched_profile_weak_point"] is True
    assert captured["request"]["strategy_signals"]["matched_study_graph_weak_node"] is True
    _write_artifact(
        "total_agent_profile_strategy_result.json",
        {
            "test_name": "test_total_agent_resource_strategy_uses_profile_and_study_graph",
            "result": result,
            "captured_request": captured["request"],
        },
    )


def test_total_agent_resource_strategy_respects_explicit_resource_types(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    captured = {}

    def fake_generation(request_payload: dict) -> dict:
        captured["request"] = request_payload
        return _fake_generation(request_payload)

    monkeypatch.setattr(tagt, "generate_resources_from_request", fake_generation)
    monkeypatch.setattr(
        lpt,
        "get_persisted_learning_profile",
        lambda user_id, syllabus_id: {
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "weak_points": ["RowKey 热点"],
            "preferences": {"preferred_formats": ["quiz"]},
        },
    )
    monkeypatch.setattr(
        tagt,
        "get_study_graph_features",
        lambda user_id, syllabus_id: {"weak_node_ids": ["hbase_intro"]},
    )

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "continue learning, give me practice",
            "resource_types": ["documents"],
        }
    )

    assert result["success"] is True
    assert captured["request"]["resource_types"] == ["documents"]
    assert captured["request"]["strategy_signals"]["explicit_resource_types"] is True
    assert result["result"]["resource_generation"]["resource_strategy"]["reason"] == "user explicitly requested resource types"
