import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import time
from types import SimpleNamespace
from typing import Callable

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from tasks import personal_recommendation_task as prt
from tasks import study_graph_task as sgt
from tasks import total_agent_task as tat
from tasks.learning_profile import agent_tools as profile_tools
from tasks.learning_profile import storage as profile_storage
from tasks.study_graph import storage as study_graph_storage
from tasks.total_agent import agent_contracts as tac
from tasks.total_agent import agent_tools as tagt


WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"
DEEP_STUDENT_STATE_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "total_agent" / "deep_student_state.json"
ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "e2e_amend"


@dataclass
class StudentE2EState:
    user_id: int
    syllabus_id: int
    subject_title: str
    profile_input_records: dict
    profile: dict
    learning_plan: dict
    study_graph_state: dict
    study_graph_tree: dict
    current_resource: dict
    current_resource_id: str
    messages: dict
    artifact_root: Path
    cleanup: Callable | None = None


def _reset_artifact_root(name: str) -> Path:
    root = ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(root: Path, name: str, payload: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_deep_student_state_fixture() -> dict:
    return json.loads(DEEP_STUDENT_STATE_FIXTURE_PATH.read_text(encoding="utf-8"))


def _state_artifact_payload(state: StudentE2EState) -> dict:
    return {
        "user_id": state.user_id,
        "syllabus_id": state.syllabus_id,
        "subject_title": state.subject_title,
        "profile_input_records": state.profile_input_records,
        "profile": state.profile,
        "learning_plan": state.learning_plan,
        "study_graph_state": state.study_graph_state,
        "study_graph_tree": state.study_graph_tree,
        "current_resource": state.current_resource,
        "current_resource_id": state.current_resource_id,
        "messages": state.messages,
        "artifact_root": str(state.artifact_root),
    }


def _recommendation_fixture() -> dict:
    return _load_deep_student_state_fixture()["recommendation"]


def _fake_generation(request_payload: dict) -> dict:
    resource_type = (request_payload.get("resource_types") or ["documents"])[0]
    return {
        "success": True,
        "resources": [
            {
                "resource_id": f"{resource_type}-e2e-amend-current",
                "resource_type": resource_type,
                "status": "ready",
                "topic": request_payload.get("topic"),
            }
        ],
    }


def _build_profile_input_records(now_ts: int) -> dict:
    fixture_records = _load_deep_student_state_fixture()["profile_input_records"]
    records = json.loads(json.dumps(fixture_records, ensure_ascii=False))
    for item in records.get("learning_records") or []:
        offset = int(item.pop("started_at_offset_seconds", 0) or 0)
        item["started_at"] = now_ts + offset
    for item in records.get("answer_records") or []:
        offset = int(item.pop("answered_at_offset_seconds", 0) or 0)
        item["answered_at"] = now_ts + offset
    for item in records.get("resource_usage") or []:
        offset = int(item.pop("timestamp_offset_seconds", 0) or 0)
        item["timestamp"] = now_ts + offset
    return records


def _save_fixture_profile(user_id: int, syllabus_id: int, profile_input_records: dict) -> dict:
    now_ts = int(time())
    state = {
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "user": SimpleNamespace(
            user_id=user_id,
            user_name=f"e2e-amend-user-{user_id}",
            email=f"e2e-amend-user-{user_id}@example.com",
        ),
        "user_syllabuses": [],
        "profile_scope": [{"syllabus_id": syllabus_id, "title": "大数据概论"}],
        "dialogue_texts": profile_input_records["dialogue_text"],
        "learning_goal": profile_input_records["learning_goal"],
        "learning_records": profile_input_records["learning_records"],
        "answer_records": profile_input_records["answer_records"],
        "resource_usage": profile_input_records["resource_usage"],
        "now_ts": now_ts,
        "history_entries": [],
        "existing_profile": None,
        "existing_profile_path": None,
        "existing_profile_loaded": False,
        "loaded_personal_syllabuses": [],
        "history_loaded": False,
        "personal_syllabus_loaded": False,
        "normalized_events": {},
        "feature_bundle": {},
        "profile": None,
        "profile_path": None,
        "profile_saved": False,
        "tool_trace": [],
    }
    profile_tools._tool_normalize_events(state)
    profile_tools._tool_compute_features(state)
    profile_tools._tool_assemble_profile(state)
    profile = state["profile"]
    assert isinstance(profile, dict)
    profile["syllabus_scope"] = [{"syllabus_id": syllabus_id, "title": "大数据概论"}]
    saved = profile_storage.save_personal_profile(user_id, syllabus_id, profile)
    assert saved and saved.get("profile_saved") is True
    persisted = lpt.get_persisted_learning_profile(user_id, syllabus_id)
    assert persisted and persisted.get("profile_saved") is True
    return persisted


def _study_change(
    user_id: int,
    syllabus_id: int,
    key: str,
    title: str,
    *,
    signal: str,
    summary: str,
    confidence: float = 0.9,
    parent_title: str = "",
    delta: float | None = None,
) -> dict:
    mastery = {"signal": signal}
    if delta is not None:
        mastery["delta"] = delta
    change = {
        "op": "upsert_knowledge_node",
        "client_change_id": f"e2e-amend:{user_id}:{syllabus_id}:{key}",
        "knowledge": {
            "title": title,
            "summary": summary,
            "aliases": [title],
        },
        "mastery": mastery,
        "confidence": confidence,
    }
    if parent_title:
        change["parent_candidate"] = {"title": parent_title}
    return change


def _submit_study_batch(
    user_id: int,
    syllabus_id: int,
    subject_title: str,
    changes: list[dict],
    *,
    timestamp: int,
    phase: str,
) -> dict:
    result = sgt.submit_learning_tree_changes(
        user_id,
        syllabus_id,
        changes,
        source={"kind": "total_agent_e2e_amend", "phase": phase},
        timestamp=timestamp,
        subject_title=subject_title,
    )
    assert result["success"] is True
    return result


def _submit_deep_study_graph(user_id: int, syllabus_id: int, subject_title: str, *, stale: bool = False) -> dict:
    now_ts = int(time())
    batches = []
    fixture = _load_deep_student_state_fixture()
    for batch in fixture["study_graph_batches"]:
        offset_key = "stale_timestamp_offset_seconds" if stale and batch.get("phase") == "active_step_foundation" else "timestamp_offset_seconds"
        timestamp = now_ts + int(batch.get(offset_key) or batch.get("timestamp_offset_seconds") or 0)
        changes = [
            _study_change(
                user_id,
                syllabus_id,
                str(change["key"]),
                str(change["title"]),
                signal=str(change["signal"]),
                summary=str(change["summary"]),
                confidence=float(change.get("confidence") or 0.9),
                parent_title=str(change.get("parent_title") or ""),
                delta=change.get("delta"),
            )
            for change in batch.get("changes") or []
        ]
        batches.append(
            _submit_study_batch(
                user_id,
                syllabus_id,
                subject_title,
                changes,
                timestamp=timestamp,
                phase=str(batch["phase"]),
            )
        )
    tree = sgt.get_student_learning_tree(user_id, syllabus_id)
    features = sgt.get_learning_tree_features(user_id, syllabus_id, stale_days=14)
    assert features["success"] is True
    nodes = tree["tree"].get("nodes") or []
    edges = tree["tree"].get("edges") or []
    titles = {node.get("title") for node in nodes if isinstance(node, dict)}
    assert len(nodes) >= 10
    assert len(edges) >= 6
    assert {"HBase 基础", "HBase RowKey 设计", "RowKey 热点", "预分区"} <= titles
    assert "HBase 基础" in features["weak_topics"]
    assert "RowKey 热点" in features["weak_topics"]
    assert "大数据基础" in features["mastered_topics"]
    assert "HDFS 基础" in features["mastered_topics"]
    assert "MapReduce 基础" in features["stale_topics"]
    assert features["recently_grown"]
    return {
        "submit_result": batches[-1],
        "submit_batches": batches,
        "tree": tree,
        "features": features,
    }


def _accept_fixture_plan(user_id: int, syllabus_id: int) -> dict:
    accepted = prt.accept_recommendation_path(
        user_id=user_id,
        syllabus_id=syllabus_id,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert accepted["success"] is True
    return accepted["plan"]


def _build_total_agent_e2e_student_state(
    *,
    monkeypatch,
    tmp_path,
    artifact_name: str,
    user_id: int = 808,
    syllabus_id: int = 2020,
    stale_graph: bool = False,
) -> StudentE2EState:
    artifact_root = _reset_artifact_root(artifact_name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root / "learning_plan"))
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: artifact_root / "study_graph")
    monkeypatch.setattr(profile_storage, "set_personal_profile_path", lambda user_id, syllabus_id, path: True)
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)

    now_ts = int(time())
    profile_input_records = _build_profile_input_records(now_ts)
    profile = _save_fixture_profile(user_id, syllabus_id, profile_input_records)
    plan = _accept_fixture_plan(user_id, syllabus_id)
    graph_bundle = _submit_deep_study_graph(user_id, syllabus_id, "大数据概论", stale=stale_graph)
    current_step = next(step for step in plan["steps"] if step["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE)
    fixture = _load_deep_student_state_fixture()
    current_resource = dict(fixture["current_resource"])
    current_resource["topic"] = current_step["title"]
    current_resource["attached_step_id"] = current_step["step_id"]
    current_resource_id = current_resource["resource_id"]
    messages = dict(fixture["messages"])
    messages["dialogue_history"] = profile_input_records["dialogue_text"]
    state = StudentE2EState(
        user_id=user_id,
        syllabus_id=syllabus_id,
        subject_title="大数据概论",
        profile_input_records=profile_input_records,
        profile=profile,
        learning_plan=plan,
        study_graph_state=graph_bundle["features"],
        study_graph_tree=graph_bundle["tree"],
        current_resource=current_resource,
        current_resource_id=current_resource_id,
        messages=messages,
        artifact_root=artifact_root,
    )
    _write_artifact(
        artifact_root,
        "student_state_fixture_result.json",
        {
            "success": True,
            "user_id": user_id,
            "syllabus_id": syllabus_id,
            "profile_input_records": profile_input_records,
            "profile": profile,
            "learning_plan": plan,
            "study_graph_state": graph_bundle["features"],
            "study_graph_tree": graph_bundle["tree"],
            "current_resource": current_resource,
            "current_resource_id": current_resource_id,
            "current_step": current_step,
            "messages": messages,
        },
    )
    return state


def _assert_continue_resource_result(result: dict) -> dict:
    assert result["success"] is True
    assert result["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert result["tool_trace"] == tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE]
    return result["result"]["resource_generation"]["resource_strategy"]


def test_e2e_state_fixture_builds_deep_student_state(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="student_state_fixture",
    )

    assert state.profile["profile_saved"] is True
    assert state.profile["profile_schema_version"] == 1
    assert "knowledge_mastery" in state.profile
    assert "source_events" in state.profile
    assert {"answer_records", "learning_records", "resource_usage"} <= set(state.profile["source_events"])
    assert state.profile["signals"]["learning_record_count"] >= 5
    assert state.profile["signals"]["answer_record_count"] >= 5
    assert state.profile["signals"]["resource_event_count"] >= 5
    assert len(state.profile_input_records["learning_records"]) >= 5
    assert len(state.profile_input_records["answer_records"]) >= 5
    assert len(state.profile_input_records["resource_usage"]) >= 5
    assert state.learning_plan["status"] == prt.LEARNING_PLAN_STATUS_ACTIVE
    assert len(state.learning_plan["steps"]) == 3
    tree = state.study_graph_tree["tree"]
    assert len(tree["nodes"]) >= 10
    assert len(tree["edges"]) >= 6
    assert state.study_graph_state["weak_topics"]
    assert state.study_graph_state["mastered_topics"]
    assert state.study_graph_state["recently_grown"]
    assert state.study_graph_state["stale_topics"]
    assert state.current_resource["resource_id"] == state.current_resource_id
    assert state.messages["first_question"]
    assert len(state.messages["follow_up"]) >= 5


def test_total_agent_e2e_profile_driven_continue(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="profile_driven_continue",
    )

    result = tat.run_total_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "继续学习，给我一点练习",
        }
    )
    strategy = _assert_continue_resource_result(result)

    assert result["result"]["context"]["profile_summary"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert "HBase 基础" in result["result"]["context"]["study_graph_state"]["weak_node_ids"]
    assert strategy["resource_types"][:2] == ["documents", "quiz"]
    assert strategy["difficulty"] == tac.RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    assert strategy["strategy_signals"]["matched_profile_weak_point"] is True
    assert strategy["strategy_signals"]["matched_study_graph_weak_node"] is True
    _write_artifact(
        state.artifact_root,
        "profile_driven_continue_result.json",
        {"student_state": _state_artifact_payload(state), "total_agent_result": result},
    )


def test_total_agent_e2e_study_graph_weak_step_continue(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="study_graph_weak_continue",
    )

    result = tat.run_total_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "继续学习",
        }
    )
    strategy = _assert_continue_resource_result(result)

    assert "HBase 基础" in result["result"]["context"]["study_graph_state"]["weak_node_ids"]
    assert strategy["difficulty"] == tac.RESOURCE_STRATEGY_DIFFICULTY_TARGETED
    assert strategy["strategy_signals"]["matched_study_graph_weak_node"] is True
    _write_artifact(
        state.artifact_root,
        "study_graph_weak_continue_result.json",
        {"student_state": _state_artifact_payload(state), "total_agent_result": result},
    )


def test_total_agent_e2e_study_graph_stale_step_review(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="study_graph_stale_review",
        stale_graph=True,
    )

    result = tat.run_total_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "继续学习，帮我复习总结一下",
        }
    )
    strategy = _assert_continue_resource_result(result)

    assert "HBase 基础" in result["result"]["context"]["study_graph_state"]["stale_node_ids"]
    assert strategy["difficulty"] == tac.RESOURCE_STRATEGY_DIFFICULTY_REVIEW
    assert strategy["resource_types"] == ["mindmap"]
    assert strategy["strategy_signals"]["message_requests_review"] is True
    _write_artifact(
        state.artifact_root,
        "study_graph_stale_review_result.json",
        {"student_state": _state_artifact_payload(state), "total_agent_result": result},
    )


def test_total_agent_e2e_feedback_updates_plan_and_study_graph(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="feedback_updates_plan_and_graph",
    )
    current_step = next(step for step in state.learning_plan["steps"] if step["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE)

    result = tat.run_total_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "我学完了这份资料",
            "step_id": current_step["step_id"],
            "resource_id": state.current_resource_id,
            "status": prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
            "score": 0.86,
        }
    )
    feedback = result["result"]["record_learning_feedback"]
    active_plan = prt.get_active_learning_plan(state.user_id, state.syllabus_id)
    manifest_entries = prt.load_learning_plan_manifest(state.user_id, state.syllabus_id)
    study_tree = sgt.get_student_learning_tree(state.user_id, state.syllabus_id)

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_RECORD_LEARNING_FEEDBACK
    assert feedback["updated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    assert feedback["activated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
    assert feedback["study_graph_sync"]["attempted"] is True
    assert feedback["study_graph_sync"]["success"] is True
    assert any(entry.get("event_type") == tac.TOTAL_AGENT_LEARNING_EVENT_RECORDED for entry in manifest_entries)
    statuses = {step["node_id"]: step["status"] for step in active_plan["steps"]}
    assert statuses["hbase_intro"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    assert statuses["rowkey_design"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
    assert study_tree["tree"]["nodes"]
    _write_artifact(
        state.artifact_root,
        "feedback_updates_plan_and_graph_result.json",
        {
            "student_state": _state_artifact_payload(state),
            "total_agent_result": result,
            "active_plan_after_feedback": active_plan,
            "learning_plan_manifest_entries": manifest_entries,
            "study_tree_after_feedback": study_tree,
        },
    )


def test_total_agent_e2e_answer_learning_question_no_plan_mutation(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="answer_learning_question",
    )
    plan_before = prt.get_active_learning_plan(state.user_id, state.syllabus_id)

    result = tat.run_total_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "为什么 RowKey 会出现热点？",
            "mock_evidence": [
                {
                    "title": "RowKey 热点",
                    "summary": "单调递增 RowKey 会让写入集中到最后一个 Region，预分区和加盐前缀可以缓解。",
                    "source": "RAG",
                    "score": 0.9,
                }
            ],
        }
    )
    plan_after = prt.get_active_learning_plan(state.user_id, state.syllabus_id)
    answer = result["result"]["answer_learning_question"]

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_ANSWER_LEARNING_QUESTION
    assert result["suggested_next_action"] == tac.ACTION_OFFER_PRACTICE_OR_RESOURCE
    assert answer["plan_mutation"] is False
    assert answer["resource_generation"] is False
    assert plan_after["current_step_index"] == plan_before["current_step_index"]
    assert result["tool_trace"] == [
        tac.TOOL_LOAD_TOTAL_CONTEXT,
        tac.TOOL_INFER_USER_INTENT,
        tac.TOOL_RETRIEVE_LEARNING_EVIDENCE,
        tac.TOOL_ANSWER_LEARNING_QUESTION,
    ]
    _write_artifact(
        state.artifact_root,
        "answer_learning_question_result.json",
        {"student_state": _state_artifact_payload(state), "total_agent_result": result, "active_plan_after_answer": plan_after},
    )


def test_total_agent_e2e_vague_goal_asks_clarification_without_plan(monkeypatch, tmp_path):
    artifact_root = _reset_artifact_root("clarification_no_force")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root / "learning_plan"))
    result = tat.run_total_agent({"user_id": 909, "syllabus_id": 3030, "message": "随便给我来一个"})
    active_plan = prt.get_active_learning_plan(909, 3030)

    assert result["success"] is True
    assert result["suggested_next_action"] == tac.ACTION_ASK_GOAL_CLARIFICATION
    assert active_plan is None
    _write_artifact(
        artifact_root,
        "vague_goal_asks_clarification_result.json",
        {"total_agent_result": result, "active_plan": active_plan},
    )


def test_total_agent_e2e_continue_existing_plan_when_goal_unclear_but_plan_active(monkeypatch, tmp_path):
    state = _build_total_agent_e2e_student_state(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        artifact_name="continue_existing_plan_when_unclear",
    )

    result = tat.run_total_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "继续",
        }
    )

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert result["result"]["next_task"]["next_task"]["node_id"] == "hbase_intro"
    assert "recommendation" not in result["result"]
    _write_artifact(
        state.artifact_root,
        "continue_existing_plan_when_unclear_result.json",
        {"student_state": _state_artifact_payload(state), "total_agent_result": result},
    )


@pytest.mark.llm
@pytest.mark.mysql
def test_e2e_state_fixture_real_profile_agent_optional(monkeypatch, tmp_path):
    if os.getenv("RUN_LLM_TESTS") != "1" or os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 RUN_DB_TESTS=1 to run the real profile fixture E2E.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")

    artifact_root = _reset_artifact_root("student_state_real_profile")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root / "learning_plan"))
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: artifact_root / "study_graph")
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)

    app = create_app()
    with app.app_context():
        user = User(
            user_name=f"e2e-amend-real-profile-{os.urandom(4).hex()}",
            password_hash="pytest-not-used",
            email=f"e2e-amend-real-profile-{os.urandom(4).hex()}@example.com",
        )
        syllabus = Syllabus.query.filter_by(syllabus_path=WORKING_SYLLABUS_PATH).first()
        created_syllabus = False
        if syllabus is None:
            syllabus = Syllabus(title="大数据概论", syllabus_path=WORKING_SYLLABUS_PATH)
            db.session.add(syllabus)
            created_syllabus = True
        db.session.add(user)
        db.session.commit()
        relation = UserSyllabus(user_id=user.user_id, syllabus_id=syllabus.syllabus_id, syllabus_permission="user")
        db.session.add(relation)
        db.session.commit()
        try:
            profile = lpt.get_or_build_learning_profile(
                user.user_id,
                syllabus.syllabus_id,
                refresh_profile=True,
                dialogue_text=[
                    "我最近在学大数据概论，HBase 的 RowKey 热点总是搞不懂。",
                    "我希望先补齐 RowKey 设计，再做一点练习。",
                ],
                learning_goal="掌握 HBase RowKey 热点规避和预分区策略",
                learning_records=[{"event_type": "study_session", "topic": "HBase RowKey 热点", "score": 0.42}],
                answer_records=[
                    {
                        "question": "RowKey 如何避免热点？",
                        "correct": False,
                        "meta": {"knowledge_points": ["RowKey 热点"]},
                    }
                ],
            )
            persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
            assert isinstance(profile, dict)
            assert isinstance(persisted, dict)
            assert persisted.get("profile_saved") is True
            _write_artifact(
                artifact_root,
                "student_state_real_profile_result.json",
                {
                    "user_id": user.user_id,
                    "syllabus_id": syllabus.syllabus_id,
                    "profile": profile,
                    "persisted_profile": persisted,
                    "personal_profile_path": relation.personal_profile_path,
                },
            )
        finally:
            db.session.rollback()
            UserSyllabus.query.filter_by(user_id=user.user_id, syllabus_id=syllabus.syllabus_id).delete()
            User.query.filter_by(user_id=user.user_id).delete()
            if created_syllabus:
                Syllabus.query.filter_by(syllabus_id=syllabus.syllabus_id).delete()
            db.session.commit()
