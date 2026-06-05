import json
from pathlib import Path

import pytest

from tasks import personal_recommendation_task as prt
from tasks import total_agent_task as tat
from tasks import learning_profile_task as lpt
from tasks import study_graph_task as sgt
from tasks.common import status_events
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
        "tool_status_events": [
            status_events.create_status_event(
                run_id=request_payload.get("run_id"),
                agent="resource_agent",
                stage="generate_resource_payload",
                status=status_events.STATUS_SUCCEEDED,
                payload={"resource_type": "documents"},
            )
        ],
        "resources": [
            {
                "resource_id": "documents-total-agent-test",
                "resource_type": "documents",
                "status": "ready",
                "topic": request_payload.get("topic"),
            }
        ],
    }


def _student_tree_summary(user_id: int, weak: list[str] | None = None, mastered: list[str] | None = None) -> dict:
    nodes = []
    now_ts = 1780650000
    for index, title in enumerate(weak or []):
        nodes.append(
            {
                "node_id": f"knowledge:{user_id}:20:weak_{index}",
                "title": title,
                "mastery": {"label": "weak", "score": 0.28},
                "last_updated_at": now_ts,
                "common_wrong_points": ["单调递增 RowKey"] if title == "RowKey 热点" else [],
            }
        )
    for index, title in enumerate(mastered or []):
        nodes.append(
            {
                "node_id": f"knowledge:{user_id}:20:mastered_{index}",
                "title": title,
                "mastery": {"label": "mastered", "score": 0.91},
                "last_updated_at": now_ts,
            }
        )
    return {
        "user_id": user_id,
        "tree": {
            "tree_id": f"study_tree:{user_id}:20",
            "user_id": user_id,
            "syllabus_id": 20,
            "nodes": nodes,
        },
    }


def test_status_event_helper_builds_stable_keys():
    event = status_events.create_status_event(
        run_id="run_1",
        agent="resource_agent",
        stage="generate_resource_payload",
        status=status_events.STATUS_RUNNING,
    )

    assert event["event_key"] == "resource_agent.generate_resource_payload.running"
    assert event["label_key"] == "agent.resource.generate_resource_payload.running"
    assert event["payload"] == {}


def test_total_agent_next_closure_constants_are_registered_and_unique():
    assert tac.INTENT_ANSWER_LEARNING_QUESTION in tac.TOTAL_AGENT_INTENTS
    assert tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_ANSWER_LEARNING_QUESTION] == [
        tac.TOOL_LOAD_TOTAL_CONTEXT,
        tac.TOOL_INFER_USER_INTENT,
        tac.TOOL_RETRIEVE_LEARNING_EVIDENCE,
        tac.TOOL_ANSWER_LEARNING_QUESTION,
    ]
    intents = list(tac.TOTAL_AGENT_INTENTS)
    assert len(intents) == len(set(intents))
    resource_modes = [
        tac.RESOURCE_RECOMMENDATION_REUSE_EXISTING,
        tac.RESOURCE_RECOMMENDATION_GENERATE_MISSING,
        tac.RESOURCE_RECOMMENDATION_GENERATE_ALL,
    ]
    assert len(resource_modes) == len(set(resource_modes))


def _write_artifact(name: str, payload: dict) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_ROOT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_total_agent_returns_structured_error_for_missing_user_id():
    result = tat.run_total_agent({"message": "continue"})

    assert result["success"] is False
    assert result["schema_version"] == tac.TOTAL_AGENT_SCHEMA_VERSION
    assert result["error_code"] == "missing_user_id"
    assert result["tool_trace"] == [tac.TOOL_LOAD_TOTAL_CONTEXT]
    assert [event["event_key"] for event in result["tool_status_events"]] == [
        "total_agent.load_total_context.running",
        "total_agent.load_total_context.failed",
    ]


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


def test_total_agent_agent_final_result_uses_answer_state_fallback():
    state = {
        "tool_trace": [
            tac.TOOL_LOAD_TOTAL_CONTEXT,
            tac.TOOL_INFER_USER_INTENT,
            tac.TOOL_RETRIEVE_LEARNING_EVIDENCE,
            tac.TOOL_ANSWER_LEARNING_QUESTION,
        ],
        "intent": tac.INTENT_ANSWER_LEARNING_QUESTION,
        "intent_result": {"intent": tac.INTENT_ANSWER_LEARNING_QUESTION},
        "total_context": {"profile_summary": {"profile_source": tac.PROFILE_SOURCE_PERSISTED}},
        "learning_evidence_result": {"tool": tac.TOOL_RETRIEVE_LEARNING_EVIDENCE, "success": True, "evidence_summary": []},
        "answer_learning_question_result": {
            "tool": tac.TOOL_ANSWER_LEARNING_QUESTION,
            "success": True,
            "answer": {"text": "RowKey hotspot answer"},
            "suggested_next_action": tac.ACTION_OFFER_PRACTICE_OR_RESOURCE,
        },
    }

    result = tar._build_agent_final_result(state)

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_ANSWER_LEARNING_QUESTION
    assert result["suggested_next_action"] == tac.ACTION_OFFER_PRACTICE_OR_RESOURCE
    assert result["result"]["answer_learning_question"]["answer"]["text"] == "RowKey hotspot answer"
    assert result["result"]["retrieve_learning_evidence"]["tool"] == tac.TOOL_RETRIEVE_LEARNING_EVIDENCE


def test_total_agent_agent_final_result_includes_course_summary_tool_result():
    state = {
        "tool_trace": [
            tac.TOOL_LOAD_TOTAL_CONTEXT,
            tac.TOOL_INFER_USER_INTENT,
            tac.TOOL_GET_COURSE_LEARNING_TREE_SUMMARY,
            tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE,
        ],
        "intent": tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE,
        "intent_result": {"intent": tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE},
        "total_context": {
            "course_learning_tree_summary": {"success": True, "summary": {"weak_nodes": [{"title": "HBase Basics"}]}},
        },
        "course_learning_tree_summary_result": {"success": True, "summary": {"student_count": 5}},
        "terminal_tool_result": {
            "tool": tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE,
            "success": True,
            "resource_strategy": {"strategy_signals": {"matched_course_global_weak_node": True}},
        },
    }

    result = tar._build_agent_final_result(state)

    assert tac.TOOL_GET_COURSE_LEARNING_TREE_SUMMARY in result["tool_trace"]
    assert result["result"]["course_learning_tree_summary"]["summary"]["student_count"] == 5
    assert result["result"]["context"]["course_learning_tree_summary"]["summary"]["weak_nodes"][0]["title"] == "HBase Basics"


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
    event_keys = [event["event_key"] for event in result["tool_status_events"]]
    assert "total_agent.generate_current_step_resource.succeeded" in event_keys
    assert "resource_agent.generate_resource_payload.succeeded" in event_keys


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


def test_total_agent_answer_learning_question_uses_mock_evidence_without_mutating_plan(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    plan_before = _accept_plan()
    monkeypatch.setattr(tagt, "generate_resources_from_request", lambda payload: (_ for _ in ()).throw(AssertionError("must not generate resources")))

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "为什么 RowKey 会出现热点？",
            "mock_evidence": [
                {
                    "title": "RowKey 热点",
                    "summary": "单调递增 RowKey 会让写入集中到最后一个 Region。",
                    "source": "RAG",
                    "score": 0.9,
                }
            ],
        }
    )
    plan_after = prt.get_active_learning_plan(8, 20)
    answer = result["result"]["answer_learning_question"]

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_ANSWER_LEARNING_QUESTION
    assert result["suggested_next_action"] == tac.ACTION_OFFER_PRACTICE_OR_RESOURCE
    assert answer["plan_mutation"] is False
    assert answer["resource_generation"] is False
    assert "Region" in answer["answer"]["text"]
    assert plan_after["current_step_index"] == plan_before["current_step_index"]
    assert result["tool_trace"] == [
        tac.TOOL_LOAD_TOTAL_CONTEXT,
        tac.TOOL_INFER_USER_INTENT,
        tac.TOOL_RETRIEVE_LEARNING_EVIDENCE,
        tac.TOOL_ANSWER_LEARNING_QUESTION,
    ]


def test_total_agent_answer_learning_question_no_evidence_returns_warning(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "解释一下 Region 划分是什么？",
        }
    )
    evidence = result["result"]["retrieve_learning_evidence"]
    answer = result["result"]["answer_learning_question"]

    assert result["success"] is True
    assert evidence["warnings"] == ["no_rag_evidence"]
    assert answer["answer"]["confidence"] == 0.48
    assert answer["resource_generation"] is False


def test_total_agent_resource_reuse_decision_skips_rejected_and_reuses_good_resource():
    matches = tagt.find_personal_resources(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "node_id": "hbase_intro",
            "knowledge_items": ["HBase 基础"],
            "resource_types": ["documents", "quiz"],
            "personal_resources": [
                {
                    "user_id": 8,
                    "syllabus_id": 20,
                    "resource_id": "documents-good",
                    "resource_type": "documents",
                    "node_id": "hbase_intro",
                    "knowledge_items": ["HBase 基础"],
                    "quality_state": tac.RESOURCE_QUALITY_USABLE,
                    "freshness_state": tac.RESOURCE_FRESHNESS_FRESH,
                    "student_feedback_state": tac.RESOURCE_FEEDBACK_ACCEPTED,
                    "validation": {"valid": True},
                },
                {
                    "user_id": 8,
                    "syllabus_id": 20,
                    "resource_id": "quiz-rejected",
                    "resource_type": "quiz",
                    "node_id": "hbase_intro",
                    "knowledge_items": ["HBase 基础"],
                    "quality_state": tac.RESOURCE_QUALITY_USABLE,
                    "freshness_state": tac.RESOURCE_FRESHNESS_FRESH,
                    "student_feedback_state": tac.RESOURCE_FEEDBACK_REJECTED,
                    "validation": {"valid": True},
                },
            ],
        }
    )
    decision = tagt.decide_resource_reuse(
        {
            "requested_resource_types": ["documents", "quiz"],
            "matches": matches["matches"],
            "learning_effect": {},
        }
    )

    assert decision["resource_recommendation_mode"] == tac.RESOURCE_RECOMMENDATION_GENERATE_MISSING
    assert decision["reusable_resources"][0]["resource_id"] == "documents-good"
    assert decision["skipped_resources"][0]["skip_reason_codes"] == [tac.REUSE_REJECT_STUDENT_REJECTED]
    assert decision["missing_resource_types"] == ["quiz"]


def test_total_agent_learning_effect_low_score_marks_targeted_refresh():
    signal = tagt.apply_learning_effect_signal(
        {
            "score": 0.43,
            "wrong_knowledge_items": ["RowKey 热点", "预分区"],
            "student_feedback": {"too_hard": True},
        }
    )

    assert signal["learning_effect"]["mastery_signal"] == "struggled"
    assert signal["learning_effect"]["weak_knowledge_items"] == ["RowKey 热点", "预分区"]
    assert signal["learning_effect"]["resource_feedback_state"] == tac.RESOURCE_FEEDBACK_DISLIKED
    assert signal["learning_effect"]["next_resource_strategy"] == tac.RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    assert signal["profile_signal"]["refresh_recommended"] is True


def test_course_learning_tree_summary_redacts_student_ids_and_aggregates_weak_nodes():
    summary = sgt.get_course_learning_tree_summary(
        {
            "syllabus_id": 20,
            "class_id": "class-rowkey",
            "student_tree_summaries": [
                _student_tree_summary(101, weak=["RowKey 热点"], mastered=["HDFS 基础"]),
                _student_tree_summary(102, weak=["RowKey 热点"]),
                _student_tree_summary(103, weak=["RowKey 热点", "预分区"]),
                _student_tree_summary(104, weak=["RowKey 热点"]),
                _student_tree_summary(105, weak=["HBase 基础"]),
            ],
        }
    )

    assert summary["success"] is True
    assert summary["summary"]["student_count"] == 5
    assert summary["privacy"]["student_ids_redacted"] is True
    assert summary["summary"]["weak_nodes"][0]["title"] == "RowKey 热点"
    assert summary["summary"]["weak_nodes"][0]["weak_student_count"] == 4
    assert "101" not in json.dumps(summary, ensure_ascii=False)


def test_course_learning_tree_summary_hides_small_sample_nodes():
    summary = sgt.get_course_learning_tree_summary(
        {
            "syllabus_id": 20,
            "student_tree_summaries": [
                _student_tree_summary(101, weak=["RowKey 热点"]),
                _student_tree_summary(102, weak=["RowKey 热点"]),
                _student_tree_summary(103, weak=["预分区"]),
                _student_tree_summary(104, weak=["HBase 基础"]),
                _student_tree_summary(105, weak=["Region 划分"]),
            ],
        }
    )

    assert summary["summary"]["weak_nodes"] == []
    assert "small_sample_nodes_redacted" in summary["warnings"]
    assert summary["privacy"]["hidden_node_count"] >= 1


def test_course_learning_tree_summary_hides_small_group():
    summary = sgt.get_course_learning_tree_summary(
        {
            "syllabus_id": 20,
            "student_tree_summaries": [
                _student_tree_summary(101, weak=["RowKey 热点"]),
                _student_tree_summary(102, weak=["RowKey 热点"]),
            ],
        }
    )

    assert summary["summary"]["weak_nodes"] == []
    assert "course_summary_group_too_small" in summary["warnings"]


def test_global_signal_personal_weak_class_weak_reinforces():
    result = tagt.combine_global_and_personal_learning_signals(
        {
            "personal_signal": {"knowledge_item": "RowKey 热点", "mastery_label": "weak", "mastery_score": 0.22},
            "course_signal": {"knowledge_item": "RowKey 热点", "is_class_weak": True, "average_mastery": 0.34},
        }
    )

    signal = result["strategy_signal"]
    assert signal["action"] == tac.GLOBAL_SIGNAL_REINFORCE_SHARED_WEAKNESS
    assert signal["resource_strategy"] == tac.RESOURCE_STRATEGY_DIFFICULTY_TARGETED


def test_global_signal_personal_strong_class_weak_checkpoint_only():
    result = tagt.combine_global_and_personal_learning_signals(
        {
            "personal_signal": {"knowledge_item": "RowKey 热点", "mastery_label": "mastered", "mastery_score": 0.92},
            "course_signal": {"knowledge_item": "RowKey 热点", "is_class_weak": True, "average_mastery": 0.34},
        }
    )

    signal = result["strategy_signal"]
    assert signal["action"] == tac.GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE
    assert signal["resource_strategy"] == tac.RESOURCE_STRATEGY_DIFFICULTY_REVIEW


def test_global_signal_personal_weak_class_strong_individual_support():
    result = tagt.combine_global_and_personal_learning_signals(
        {
            "personal_signal": {"knowledge_item": "RowKey 热点", "mastery_label": "weak", "mastery_score": 0.22},
            "course_signal": {"knowledge_item": "RowKey 热点", "is_class_weak": False, "average_mastery": 0.82},
        }
    )

    signal = result["strategy_signal"]
    assert signal["action"] == tac.GLOBAL_SIGNAL_INDIVIDUAL_TARGETED_SUPPORT
    assert signal["resource_strategy"] == tac.RESOURCE_STRATEGY_DIFFICULTY_TARGETED


def test_global_signal_personal_strong_class_strong_advances():
    result = tagt.combine_global_and_personal_learning_signals(
        {
            "personal_signal": {"knowledge_item": "RowKey 热点", "mastery_label": "mastered", "mastery_score": 0.92},
            "course_signal": {"knowledge_item": "RowKey 热点", "is_class_weak": False, "average_mastery": 0.82},
        }
    )

    signal = result["strategy_signal"]
    assert signal["action"] == tac.GLOBAL_SIGNAL_ADVANCE_OR_ENRICH
    assert signal["resource_strategy"] == tac.RESOURCE_STRATEGY_DIFFICULTY_STANDARD


def test_total_agent_resource_strategy_uses_course_global_signal_checkpoint(monkeypatch, tmp_path):
    _reset_learning_plan_root(monkeypatch, tmp_path)
    _accept_plan()
    monkeypatch.setattr(
        tagt,
        "load_profile_summary",
        lambda payload, status_state=None: {"success": True, "profile": {}, "source": "none", "warnings": []},
    )
    monkeypatch.setattr(
        tagt,
        "get_study_graph_features",
        lambda user_id, syllabus_id, status_state=None: {"mastered_topics": ["HBase Basics"], "weak_topics": []},
    )
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)

    result = tat.run_total_agent(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "继续学习",
            "course_tree_summary_payload": {
                "syllabus_id": 20,
                "student_tree_summaries": [
                    _student_tree_summary(101, weak=["HBase Basics"]),
                    _student_tree_summary(102, weak=["HBase Basics"]),
                    _student_tree_summary(103, weak=["HBase Basics"]),
                    _student_tree_summary(104, weak=["RowKey 热点"]),
                    _student_tree_summary(105, weak=["预分区"]),
                ],
            },
        }
    )

    strategy = result["result"]["resource_generation"]["resource_strategy"]
    assert strategy["strategy_signals"]["matched_course_global_weak_node"] is True
    assert strategy["strategy_signals"]["global_signal_action"] == tac.GLOBAL_SIGNAL_CHECKPOINT_THEN_ADVANCE
    assert strategy["difficulty"] == tac.RESOURCE_STRATEGY_DIFFICULTY_REVIEW
