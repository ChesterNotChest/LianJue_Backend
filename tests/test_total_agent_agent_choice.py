import json
import os
import shutil
from pathlib import Path

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from config import OPENAI_COMPAT_MODEL_CONFIGS
from tasks import personal_recommendation_task as prt
from tasks import total_agent_task as tat
from tasks.learning_profile import agent_runtime as profile_runtime
from tasks.total_agent import agent_contracts as tac
from tasks.total_agent import agent_runtime as tar
from tasks.total_agent import agent_tools as tagt


ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts" / "total_agent"
WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"


def _normalize_model_for_dashscope():
    text_config = OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        tar.get_total_agent.cache_clear()
        profile_runtime.get_learning_profile_agent.cache_clear()


def _reset_artifact_root(name: str) -> Path:
    root = ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(root: Path, name: str, payload: dict) -> None:
    (root / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def db_total_agent_profile_case():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the Total Agent profile integration smoke test.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")

    app = create_app()
    with app.app_context():
        suffix = os.urandom(4).hex()
        user = User(
            user_name=f"total-agent-profile-{suffix}",
            password_hash="pytest-not-used",
            email=f"total-agent-profile-{suffix}@example.com",
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


def _recommendation_fixture() -> dict:
    return {
        "success": True,
        "best_path": {
            "path": ["hbase_intro", "rowkey_design"],
            "skills": ["hbase", "rowkey"],
        },
        "candidates": [
            {
                "path": ["hbase_intro", "rowkey_design"],
                "skills": ["hbase", "rowkey"],
            }
        ],
        "graph": {
            "nodes": [
                {"id": "hbase_intro", "title": "HBase Basics", "outcomes": ["hbase"]},
                {"id": "rowkey_design", "title": "HBase RowKey Design", "outcomes": ["rowkey_design"]},
            ],
            "edges": [{"source": "hbase_intro", "target": "rowkey_design"}],
        },
    }


def _fake_generation(request_payload: dict) -> dict:
    return {
        "success": True,
        "resources": [
            {
                "resource_id": "documents-total-agent-llm-choice",
                "resource_type": "documents",
                "status": "ready",
                "topic": request_payload.get("topic"),
            }
        ],
    }


def _trace_agent_tools(monkeypatch):
    trace = []
    tool_outputs = []

    def wrap(tool_name, func):
        def traced(state):
            result = func(state)
            trace[:] = list(state.get("tool_trace") or [])
            tool_outputs.append({"tool": tool_name, "result": result})
            return result

        return traced

    monkeypatch.setattr(tar, "tool_load_total_context", wrap(tac.TOOL_LOAD_TOTAL_CONTEXT, tagt.tool_load_total_context))
    monkeypatch.setattr(tar, "tool_infer_user_intent", wrap(tac.TOOL_INFER_USER_INTENT, tagt.tool_infer_user_intent))
    monkeypatch.setattr(tar, "tool_get_next_learning_task", wrap(tac.TOOL_GET_NEXT_LEARNING_TASK, tagt.tool_get_next_learning_task))
    monkeypatch.setattr(
        tar,
        "tool_generate_current_step_resource",
        wrap(tac.TOOL_GENERATE_CURRENT_STEP_RESOURCE, tagt.tool_generate_current_step_resource),
    )
    monkeypatch.setattr(
        tar,
        "tool_run_learning_recommendation",
        wrap(tac.TOOL_RUN_LEARNING_RECOMMENDATION, tagt.tool_run_learning_recommendation),
    )
    tar.get_total_agent.cache_clear()
    return trace, tool_outputs


@pytest.mark.llm
def test_total_agent_real_llm_selects_continue_tool_chain(monkeypatch, tmp_path):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the Total Agent tool-choice smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("agent_choice_continue")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)
    trace, tool_outputs = _trace_agent_tools(monkeypatch)

    accepted = prt.accept_recommendation_path(
        user_id=8,
        syllabus_id=20,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert accepted["success"] is True

    try:
        result = tat.run_total_agent_agent(
            {
                "user_id": 8,
                "syllabus_id": 20,
                "message": "请继续学习当前步骤，并给我一份文档资料",
                "resource_types": ["documents"],
            }
        )
    finally:
        tar.get_total_agent.cache_clear()

    assert result["success"] is True
    assert result["intent"] == tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE
    assert result["tool_trace"] == tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE]
    assert result["suggested_next_action"] == tac.ACTION_RECORD_LEARNING_FEEDBACK
    _write_artifact(
        artifact_root,
        "agent_choice_continue_result.json",
        {
            "test_name": "test_total_agent_real_llm_selects_continue_tool_chain",
            "expected_tool_order": tac.TOTAL_AGENT_TOOL_ORDER[tac.INTENT_GENERATE_CURRENT_STEP_RESOURCE],
            "tool_trace": trace,
            "tool_outputs": tool_outputs,
            "result": result,
        },
    )


@pytest.mark.llm
def test_total_agent_reads_real_profile_agent_output_for_resource_strategy(
    monkeypatch,
    tmp_path,
    db_total_agent_profile_case,
):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the Total Agent profile integration smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("real_profile_to_total_agent")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    monkeypatch.setattr(tagt, "generate_resources_from_request", _fake_generation)
    user, syllabus, relation = db_total_agent_profile_case

    profile = lpt.get_or_build_learning_profile(
        user.user_id,
        syllabus.syllabus_id,
        refresh_profile=True,
        dialogue_text=[
            "我最近在学大数据概论，HBase 的 RowKey 热点总是搞不懂。",
            "我希望两周内掌握 HBase 和预分区策略，并多做一点练习。",
        ],
        learning_goal="掌握大数据概论中的 HBase RowKey 设计",
        learning_records=[
            {
                "event_type": "study_session",
                "duration_minutes": 42,
                "meta": {"topic": "HBase"},
            }
        ],
        answer_records=[
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "time_spent_seconds": 160,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
        resource_usage=[
            {
                "resource_id": "video_hbase_rowkey",
                "action": "complete",
                "duration_seconds": 900,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
    )
    persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    assert isinstance(profile, dict), profile
    assert isinstance(persisted, dict), profile
    assert persisted.get("profile_saved") is True

    accepted = prt.accept_recommendation_path(
        user_id=user.user_id,
        syllabus_id=syllabus.syllabus_id,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert accepted["success"] is True

    result = tat.run_total_agent(
        {
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "message": "请继续学习当前步骤，并给我一点练习",
        }
    )
    profile_summary = result["result"]["context"]["profile_summary"]
    resource_strategy = result["result"]["resource_generation"]["resource_strategy"]

    assert result["success"] is True
    assert profile_summary["profile_source"] == tac.PROFILE_SOURCE_PERSISTED
    assert profile_summary["weak_points"] or profile_summary["learning_goal"]
    assert resource_strategy["profile_source"] == tac.PROFILE_SOURCE_PERSISTED

    _write_artifact(
        artifact_root,
        "real_profile_to_total_agent_result.json",
        {
            "test_name": "test_total_agent_reads_real_profile_agent_output_for_resource_strategy",
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "personal_profile_path": relation.personal_profile_path,
            "built_profile": profile,
            "persisted_profile": persisted,
            "total_agent_result": result,
            "profile_summary": profile_summary,
            "resource_strategy": resource_strategy,
        },
    )
