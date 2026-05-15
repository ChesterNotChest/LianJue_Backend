import os
from pathlib import Path
import uuid

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt


WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"


EXPECTED_TOOL_ORDER = [
    "load_existing_profile_context",
    "load_history_context",
    "load_personal_syllabus_context",
    "normalize_events",
    "compute_features",
    "assemble_profile",
    "save_or_update_profile",
]


def _normalize_model_for_dashscope():
    text_config = lpt.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        lpt.get_learning_profile_agent.cache_clear()


def _trace_agent_tools(monkeypatch):
    trace = []

    def wrap(tool_name, func):
        def traced(state):
            trace.append(tool_name)
            result = func(state)
            state["tool_trace"] = trace[:]
            return result

        return traced

    monkeypatch.setattr(
        lpt,
        "_tool_load_existing_profile_context",
        wrap("load_existing_profile_context", lpt._tool_load_existing_profile_context),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_load_history_context",
        wrap("load_history_context", lpt._tool_load_history_context),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_load_personal_syllabus_context",
        wrap("load_personal_syllabus_context", lpt._tool_load_personal_syllabus_context),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_normalize_events",
        wrap("normalize_events", lpt._tool_normalize_events),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_compute_features",
        wrap("compute_features", lpt._tool_compute_features),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_assemble_profile",
        wrap("assemble_profile", lpt._tool_assemble_profile),
    )
    monkeypatch.setattr(
        lpt,
        "_tool_save_or_update_profile",
        wrap("save_or_update_profile", lpt._tool_save_or_update_profile),
    )
    lpt.get_learning_profile_agent.cache_clear()
    return trace


@pytest.fixture
def db_learning_profile_case():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real learning profile agent choice smoke test.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")

    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"agent-smoke-{suffix}",
            password_hash="pytest-not-used",
            email=f"agent-smoke-{suffix}@example.com",
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


@pytest.mark.llm
def test_learning_profile_agent_selects_expected_tools(monkeypatch, db_learning_profile_case):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real learning profile agent choice smoke test.")

    _normalize_model_for_dashscope()
    user, syllabus, relation = db_learning_profile_case
    monkeypatch.setattr(lpt, "_collect_history_entries", lambda *args, **kwargs: [])

    trace = _trace_agent_tools(monkeypatch)
    payload = {
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
        "dialogue_text": [
            "我最近在学大数据概论，HBase 的 RowKey 热点总是搞不懂。",
            "我希望两周内掌握 HBase 和预分区策略，并多做一点练习。",
        ],
        "learning_goal": "掌握大数据概论中的 HBase RowKey 设计",
        "learning_records": [
            {
                "event_type": "study_session",
                "duration_minutes": 42,
                "started_at": 1759913600,
                "meta": {"topic": "HBase"},
            },
            {
                "event_type": "practice",
                "duration_minutes": 36,
                "started_at": 1759996400,
                "meta": {"topic": "RowKey 设计"},
            },
        ],
        "answer_records": [
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "answered_at": 1759998200,
                "time_spent_seconds": 160,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            },
            {
                "question": "HBase 适合什么查询场景？",
                "correct": True,
                "answered_at": 1759999000,
                "time_spent_seconds": 100,
                "meta": {"knowledge_points": ["HBase"]},
            },
            {
                "question": "预分区策略如何缓解热点？",
                "correct": False,
                "answered_at": 1759999800,
                "time_spent_seconds": 180,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            },
        ],
        "resource_usage": [
            {
                "resource_id": "video_hbase_rowkey",
                "action": "complete",
                "timestamp": 1759999900,
                "duration_seconds": 900,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
    }

    try:
        profile = lpt.build_learning_profile(**payload)
    finally:
        lpt.get_learning_profile_agent.cache_clear()

    output = {
        "profile": profile,
        "tool_trace": trace,
        "personal_syllabus_path": relation.personal_syllabus_path,
        "personal_profile_path": relation.personal_profile_path,
    }

    assert trace == EXPECTED_TOOL_ORDER
    assert output["profile"] is not None
    assert output["profile"]["user_id"] == payload["user_id"]
    assert output["personal_syllabus_path"]
    assert output["personal_profile_path"]
    assert len(output["profile"]) >= 30
    assert "RowKey 热点" in output["profile"]["concept_gaps"]
    assert output["profile"]["source_events"] == ["answer_records", "learning_records", "resource_usage"]
    assert output["profile"]["knowledge_mastery"]["knowledge_point_details"]["RowKey 热点"]["attempt_count"] == 2
