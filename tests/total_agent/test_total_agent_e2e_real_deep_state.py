import json
import os
import shutil
import uuid
from time import time
from pathlib import Path

import pytest

from app import create_app
from config import OPENAI_COMPAT_MODEL_CONFIGS
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from tasks import personal_recommendation_task as prt
from tasks import study_graph_task as sgt
from tasks import total_agent_task as tat
from tasks.generative import storage as generative_storage
from tasks.learning_profile import agent_runtime as profile_runtime
from tasks.learning_profile import storage as profile_storage
from tasks.study_graph import storage as study_graph_storage
from tasks.total_agent import agent_contracts as tac
from tasks.total_agent import agent_runtime as total_runtime
from tests.total_agent.test_total_agent_e2e_amend import (
    DEEP_STUDENT_STATE_FIXTURE_PATH,
    _build_profile_input_records,
    _recommendation_fixture,
    _state_artifact_payload,
    _submit_deep_study_graph,
    StudentE2EState,
)


WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"
ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "e2e_real_deep_state"


class StatusReporter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, agent: str, action: str, *, status: str = "running", **details) -> None:
        event = {
            "ts": int(time()),
            "agent": agent,
            "action": action,
            "status": status,
        }
        if details:
            event["details"] = details
        self.events.append(event)
        print(f"[total-agent-e2e] {agent}: {action}... {status}", flush=True)

    def emit_event(self, event: dict) -> None:
        if not isinstance(event, dict):
            return
        self.events.append(event)
        agent = event.get("agent") or "agent"
        stage = event.get("stage") or event.get("event_key") or "stage"
        status = event.get("status") or "unknown"
        print(f"[total-agent-e2e] {agent}: {stage}... {status}", flush=True)


def _require_real_deep_state_env() -> None:
    missing = [
        name
        for name in ("RUN_LLM_TESTS", "RUN_REAL_RAG_TESTS", "RUN_DB_TESTS")
        if os.getenv(name) != "1"
    ]
    if missing:
        pytest.skip(
            "Set RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 to run real deep-state Total Agent E2E."
        )
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")


def _normalize_model_for_dashscope() -> None:
    text_config = OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        profile_runtime.get_learning_profile_agent.cache_clear()
        total_runtime.get_total_agent.cache_clear()


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


def _load_fixture() -> dict:
    return json.loads(DEEP_STUDENT_STATE_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def db_real_deep_state_case():
    _require_real_deep_state_env()
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"total-agent-real-deep-{suffix}",
            password_hash="pytest-not-used",
            email=f"total-agent-real-deep-{suffix}@example.com",
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
            yield user, syllabus, relation
        finally:
            db.session.rollback()
            UserSyllabus.query.filter_by(user_id=user.user_id, syllabus_id=syllabus.syllabus_id).delete()
            User.query.filter_by(user_id=user.user_id).delete()
            if created_syllabus:
                Syllabus.query.filter_by(syllabus_id=syllabus.syllabus_id).delete()
            db.session.commit()


def _build_real_deep_state(
    monkeypatch,
    artifact_root: Path,
    user,
    syllabus,
    reporter: StatusReporter,
) -> StudentE2EState:
    profile_root = artifact_root / "profiles"
    learning_plan_root = artifact_root / "learning_plan"
    study_graph_root = artifact_root / "study_graph"
    generative_root = artifact_root / "generative_workspace"

    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(learning_plan_root))
    monkeypatch.setattr(profile_storage, "profile_root_dir", lambda: str(profile_root))
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: study_graph_root)
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: generative_root)

    now_ts = int(os.getenv("TOTAL_AGENT_REAL_DEEP_STATE_NOW_TS") or time())
    profile_input_records = _build_profile_input_records(now_ts)
    reporter.emit("profile agent", "building deep profile")
    profile = lpt.get_or_build_learning_profile(
        user.user_id,
        syllabus.syllabus_id,
        refresh_profile=True,
        dialogue_text=profile_input_records["dialogue_text"],
        learning_goal=profile_input_records["learning_goal"],
        learning_records=profile_input_records["learning_records"],
        answer_records=profile_input_records["answer_records"],
        resource_usage=profile_input_records["resource_usage"],
    )
    persisted_profile = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    if not isinstance(profile, dict) or not isinstance(persisted_profile, dict):
        _write_artifact(
            artifact_root,
            "profile_agent_failure_result.json",
            {
                "success": False,
                "user_id": user.user_id,
                "syllabus_id": syllabus.syllabus_id,
                "profile_is_dict": isinstance(profile, dict),
                "profile": profile if isinstance(profile, dict) else None,
                "persisted_profile_is_dict": isinstance(persisted_profile, dict),
                "persisted_profile": persisted_profile if isinstance(persisted_profile, dict) else None,
                "profile_input_records": profile_input_records,
                "tool_status_events": reporter.events,
            },
        )
    assert isinstance(profile, dict), profile
    assert isinstance(persisted_profile, dict), profile
    assert persisted_profile.get("profile_saved") is True
    assert isinstance(persisted_profile.get("resource_preference"), list)
    assert persisted_profile["resource_preference"]
    assert isinstance(persisted_profile.get("concept_gaps"), list)
    assert isinstance(persisted_profile.get("knowledge_mastery"), dict)
    reporter.emit(
        "profile agent",
        "profile persisted",
        status="done",
        profile_path=persisted_profile.get("profile_path"),
        resource_preference=persisted_profile.get("resource_preference"),
    )

    reporter.emit("learning plan", "accepting prepared recommendation path")
    accepted = prt.accept_recommendation_path(
        user_id=user.user_id,
        syllabus_id=syllabus.syllabus_id,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert accepted["success"] is True
    reporter.emit(
        "learning plan",
        "learning plan active",
        status="done",
        plan_id=accepted["plan"].get("plan_id"),
    )
    reporter.emit("study graph", "writing deep learning tree batches")
    graph_bundle = _submit_deep_study_graph(user.user_id, syllabus.syllabus_id, syllabus.title or "大数据概论")
    reporter.emit(
        "study graph",
        "deep learning tree ready",
        status="done",
        node_count=len((graph_bundle["tree"].get("tree") or {}).get("nodes") or []),
        edge_count=len((graph_bundle["tree"].get("tree") or {}).get("edges") or []),
    )
    current_step = next(
        step
        for step in accepted["plan"]["steps"]
        if step["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
    )
    fixture = _load_fixture()
    current_resource = dict(fixture["current_resource"])
    current_resource["topic"] = current_step["title"]
    current_resource["attached_step_id"] = current_step["step_id"]
    messages = dict(fixture["messages"])
    messages["dialogue_history"] = profile_input_records["dialogue_text"]
    return StudentE2EState(
        user_id=user.user_id,
        syllabus_id=syllabus.syllabus_id,
        subject_title=syllabus.title or fixture["subject_title"],
        profile_input_records=profile_input_records,
        profile=persisted_profile,
        learning_plan=accepted["plan"],
        study_graph_state=graph_bundle["features"],
        study_graph_tree=graph_bundle["tree"],
        current_resource=current_resource,
        current_resource_id=current_resource["resource_id"],
        messages=messages,
        artifact_root=artifact_root,
    )


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_total_agent_e2e_real_deep_state_all_agents(monkeypatch, db_real_deep_state_case):
    _require_real_deep_state_env()
    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("all_agents")
    user, syllabus, relation = db_real_deep_state_case
    reporter = StatusReporter()

    reporter.emit("fixture", "preparing deep student state")
    state = _build_real_deep_state(monkeypatch, artifact_root, user, syllabus, reporter)
    reporter.emit("fixture", "deep student state ready", status="done")
    _write_artifact(
        artifact_root,
        "student_state_fixture_result.json",
        {
            "success": True,
            "student_state": _state_artifact_payload(state),
            "tool_status_events": reporter.events,
        },
    )

    graph_name = os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME") or os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"
    reporter.emit("total agent", "calling continue flow")
    continue_result = tat.run_total_agent_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": state.messages["follow_up"][0],
            "graph_name": graph_name,
            "rag_top_k": 5,
            "status_callback": reporter.emit_event,
        }
    )
    reporter.emit(
        "total agent",
        "continue flow completed",
        status="done" if continue_result.get("success") else "failed",
        intent=continue_result.get("intent"),
        tool_trace=continue_result.get("tool_trace"),
    )
    assert continue_result["success"] is True
    assert continue_result["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert continue_result["suggested_next_action"] == tac.ACTION_RECORD_LEARNING_FEEDBACK
    resource_generation = continue_result["result"]["resource_generation"]
    assert resource_generation["resource_strategy"]["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    profile_summary = continue_result["result"]["context"]["profile_summary"]
    assert profile_summary["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert profile_summary["preferred_formats"]
    assert set(profile_summary["preferred_formats"]).issubset(
        {"documents", "quiz", "mindmap", "coding_practice", "ppt"}
    )
    assert resource_generation["resources"], continue_result
    reporter.emit(
        "material agent",
        "material generated",
        status="done",
        resource_count=len(resource_generation["resources"]),
        resource_types=resource_generation["resource_strategy"].get("resource_types"),
    )
    generated_resource = resource_generation["resources"][0]
    assert generated_resource.get("resource_type") in set(resource_generation["resource_strategy"]["resource_types"])

    current_step = resource_generation["next_task"]
    reporter.emit("total agent", "calling feedback flow")
    feedback_result = tat.run_total_agent_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": state.messages["follow_up"][3],
            "step_id": current_step["step_id"],
            "resource_id": generated_resource.get("resource_id"),
            "resource_type": generated_resource.get("resource_type"),
            "status": prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
            "score": 0.86,
            "context": {"current_resource_id": generated_resource.get("resource_id")},
            "status_callback": reporter.emit_event,
        }
    )
    reporter.emit(
        "total agent",
        "feedback flow completed",
        status="done" if feedback_result.get("success") else "failed",
        intent=feedback_result.get("intent"),
        tool_trace=feedback_result.get("tool_trace"),
    )
    assert feedback_result["success"] is True
    assert feedback_result["intent"] == tac.INTENT_RECORD_LEARNING_FEEDBACK
    feedback = feedback_result["result"]["record_learning_feedback"]
    assert feedback["updated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    assert feedback["activated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
    assert feedback["study_graph_sync"]["attempted"] is True
    assert feedback["study_graph_sync"]["success"] is True

    active_plan_after = prt.get_active_learning_plan(state.user_id, state.syllabus_id)
    manifest_entries = prt.load_learning_plan_manifest(state.user_id, state.syllabus_id)
    study_graph_after = sgt.get_student_learning_tree(state.user_id, state.syllabus_id)
    assert any(entry.get("event_type") == tac.TOTAL_AGENT_LEARNING_EVENT_RECORDED for entry in manifest_entries)
    assert study_graph_after["tree"]["nodes"]
    reporter.emit(
        "study graph",
        "feedback synced to learning tree",
        status="done",
        node_count=len((study_graph_after.get("tree") or {}).get("nodes") or []),
    )

    _write_artifact(
        artifact_root,
        "real_deep_state_all_agents_result.json",
        {
            "student_state": _state_artifact_payload(state),
            "personal_profile_path": relation.personal_profile_path,
            "graph_name": graph_name,
            "continue_result": continue_result,
            "feedback_result": feedback_result,
            "generated_resource": generated_resource,
            "active_plan_after": active_plan_after,
            "learning_plan_manifest_entries": manifest_entries,
            "study_graph_after": study_graph_after,
            "tool_status_events": reporter.events,
        },
    )


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_total_agent_e2e_real_deep_state_answer_learning_question(monkeypatch, db_real_deep_state_case):
    _require_real_deep_state_env()
    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("answer_learning_question_real_rag")
    user, syllabus, relation = db_real_deep_state_case
    reporter = StatusReporter()

    reporter.emit("fixture", "preparing deep student state")
    state = _build_real_deep_state(monkeypatch, artifact_root, user, syllabus, reporter)
    reporter.emit("fixture", "deep student state ready", status="done")
    plan_before = prt.get_active_learning_plan(state.user_id, state.syllabus_id)
    graph_name = os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME") or os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"

    reporter.emit("total agent", "calling answer question flow")
    answer_result = tat.run_total_agent_agent(
        {
            "user_id": state.user_id,
            "syllabus_id": state.syllabus_id,
            "message": "为什么 HBase RowKey 会出现热点？",
            "graph_name": graph_name,
            "rag_top_k": 5,
            "status_callback": reporter.emit_event,
        }
    )
    reporter.emit(
        "total agent",
        "answer question flow completed",
        status="done" if answer_result.get("success") else "failed",
        intent=answer_result.get("intent"),
        tool_trace=answer_result.get("tool_trace"),
    )
    plan_after = prt.get_active_learning_plan(state.user_id, state.syllabus_id)
    answer = answer_result["result"]["answer_learning_question"]
    evidence = answer_result["result"]["retrieve_learning_evidence"]

    assert answer_result["success"] is True
    assert answer_result["intent"] == tac.INTENT_ANSWER_LEARNING_QUESTION
    assert answer_result["suggested_next_action"] == tac.ACTION_OFFER_PRACTICE_OR_RESOURCE
    assert evidence["success"] is True
    assert "evidence_summary" in evidence
    assert answer["plan_mutation"] is False
    assert answer["resource_generation"] is False
    assert answer["answer"]["text"]
    assert plan_after["plan_id"] == plan_before["plan_id"]
    assert plan_after["current_step_index"] == plan_before["current_step_index"]
    assert tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE not in answer_result["tool_trace"]
    assert tac.TOOL_RECORD_LEARNING_FEEDBACK not in answer_result["tool_trace"]

    _write_artifact(
        artifact_root,
        "real_deep_state_answer_learning_question_result.json",
        {
            "student_state": _state_artifact_payload(state),
            "personal_profile_path": relation.personal_profile_path,
            "graph_name": graph_name,
            "answer_result": answer_result,
            "active_plan_before": plan_before,
            "active_plan_after": plan_after,
            "tool_status_events": reporter.events,
        },
    )
