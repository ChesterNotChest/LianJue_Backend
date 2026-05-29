import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from tasks.learning_profile import agent_runtime as profile_runtime
from tasks.learning_profile import agent_tools as profile_tools
from tasks.learning_profile import personal_syllabus as profile_syllabus
from tasks.learning_profile import service as profile_service
from tasks.learning_profile import storage as profile_storage
from tasks.learning_profile.models import LearningProfileResult
from config import OPENAI_COMPAT_MODEL_CONFIGS


WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"


class _FakeRunResult:
    def __init__(self, output):
        self.output = output


class _ProfileToolchainAgent:
    def __init__(self):
        self.calls = 0

    def run_sync(self, user_prompt, deps=None, **kwargs):
        self.calls += 1
        state = deps.state
        profile_tools._tool_load_history_context(state)
        profile_tools._tool_load_personal_syllabus_context(state)
        profile_tools._tool_normalize_events(state)
        profile_tools._tool_compute_features(state)
        profile_tools._tool_assemble_profile(state)
        return _FakeRunResult(LearningProfileResult(success=True, profile=state["profile"]))


def _normalize_model_for_dashscope():
    text_config = OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        profile_runtime.get_learning_profile_agent.cache_clear()


@pytest.fixture
def db_real_learning_profile_case():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real learning profile agent full-chain integration test.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")

    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"real-agent-user-{suffix}",
            password_hash="pytest-not-used",
            email=f"real-agent-{suffix}@example.com",
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


def test_profile_personal_syllabus_full_chain(monkeypatch, repo_json_factory):
    syllabus_path = repo_json_factory(
        "schedule/syllabus",
        {
            "title": "HBase 个性化学习",
            "period": [
                {
                    "week_index": 1,
                    "content": "HBase RowKey 设计",
                    "enhanced_content": "RowKey 热点、散列、预分区与列族设计",
                    "importance": "high",
                }
            ],
        },
        prefix="full_chain_syllabus",
    )

    relation = SimpleNamespace(
        user_id=71,
        syllabus_id=171,
        personal_syllabus_path=None,
        personal_profile_path=None,
    )
    user = SimpleNamespace(user_id=71, user_name="full-chain-user", email="full@example.com")
    syllabus = SimpleNamespace(syllabus_id=171, title="HBase 个性化学习", syllabus_path=str(syllabus_path))
    agent = _ProfileToolchainAgent()

    def fake_set_personal_syllabus_path(user_id, syllabus_id, path):
        relation.personal_syllabus_path = path
        return relation

    monkeypatch.setattr(profile_service, "get_user_by_id", lambda user_id: user if user_id == 71 else None)
    monkeypatch.setattr(profile_syllabus, "get_user_syllabus", lambda user_id, syllabus_id: relation)
    monkeypatch.setattr(profile_service, "list_user_syllabuses", lambda user_id: [relation] if user_id == 71 else [])
    monkeypatch.setattr(profile_service, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 171 else None)
    monkeypatch.setattr(profile_syllabus, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 171 else None)
    monkeypatch.setattr(profile_tools, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 171 else None)
    monkeypatch.setattr(profile_syllabus, "set_personal_syllabus_path", fake_set_personal_syllabus_path)
    monkeypatch.setattr(profile_storage, "set_personal_profile_path", lambda user_id, syllabus_id, path: True)
    monkeypatch.setattr(profile_runtime, "get_learning_profile_agent", lambda: agent)
    monkeypatch.setattr(profile_service, "collect_history_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr(profile_service, "time", lambda: 1760000000)
    monkeypatch.setattr(profile_syllabus, "time", lambda: 1760000000)

    first_profile = lpt.build_learning_profile(
        user_id=71,
        syllabus_id=171,
        dialogue_text="我现在学 HBase，RowKey 热点问题很容易卡住。",
        learning_goal="掌握 HBase RowKey 设计",
        answer_records=[
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "answered_at": 1760000000,
                "time_spent_seconds": 180,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
    )

    initialized_path = relation.personal_syllabus_path
    initialized = json.loads(open(initialized_path, "r", encoding="utf-8").read())
    first_week = initialized["period"][0]

    assert agent.calls == 1
    assert initialized_path
    assert first_week["competance"] == "none"
    assert first_week["suggestion_history"] == []
    assert first_profile["suggested_personal_syllabus_updates"]

    apply_results = []
    for index in range(5):
        apply_results.append(
            lpt.append_profile_personal_syllabus_suggestion(
                71,
                171,
                {
                    "week_index": 1,
                    "suggested_competance": "weak",
                    "confidence": 0.9,
                    "reason": f"full-chain weak signal {index + 1}",
                    "evidence": ["dialogue_text", "answer_records"],
                },
            )
        )

    updated = json.loads(open(initialized_path, "r", encoding="utf-8").read())
    updated_week = updated["period"][0]

    assert [item["applied"] for item in apply_results] == [False, False, False, False, True]
    assert updated_week["competance"] == "weak"
    assert updated_week["suggestion_review_count"] == 0
    assert updated_week["suggested_competance_list"] == []
    assert len(updated_week["suggestion_history"]) == 5

    refreshed_profile = lpt.build_learning_profile(
        user_id=71,
        syllabus_id=171,
        dialogue_text="我继续复习 RowKey 设计。",
        learning_goal="掌握 HBase RowKey 设计",
        answer_records=[],
    )

    week_items = refreshed_profile["knowledge_mastery"]["week_items"]
    assert week_items[0]["competance"] == "weak"
    assert refreshed_profile["knowledge_mastery"]["weak_weeks"] == [1]

    print(
        "\nFULL_CHAIN_RESULT",
        json.dumps(
            {
                "initialized_path": initialized_path,
                "initial_competance": first_week["competance"],
                "suggestion_count_after_profile": len(first_profile["suggested_personal_syllabus_updates"]),
                "append_applied_sequence": [item["applied"] for item in apply_results],
                "final_competance": updated_week["competance"],
                "final_suggestion_history_count": len(updated_week["suggestion_history"]),
                "refreshed_profile_week_items": week_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )


def test_profile_personal_syllabus_multi_round_propagation(monkeypatch, repo_json_factory):
    syllabus_path = repo_json_factory(
        "schedule/syllabus",
        {
            "title": "HBase 多轮传播观察",
            "period": [
                {
                    "week_index": 1,
                    "content": "HBase RowKey 设计",
                    "enhanced_content": "RowKey 热点、散列、预分区与查询模式",
                    "importance": "high",
                }
            ],
        },
        prefix="multi_round_syllabus",
    )

    relation = SimpleNamespace(
        user_id=72,
        syllabus_id=172,
        personal_syllabus_path=None,
        personal_profile_path=None,
    )
    user = SimpleNamespace(user_id=72, user_name="multi-round-user", email="multi@example.com")
    syllabus = SimpleNamespace(syllabus_id=172, title="HBase 多轮传播观察", syllabus_path=str(syllabus_path))
    agent = _ProfileToolchainAgent()

    def fake_set_personal_syllabus_path(user_id, syllabus_id, path):
        relation.personal_syllabus_path = path
        return relation

    monkeypatch.setattr(profile_service, "get_user_by_id", lambda user_id: user if user_id == 72 else None)
    monkeypatch.setattr(profile_syllabus, "get_user_syllabus", lambda user_id, syllabus_id: relation)
    monkeypatch.setattr(profile_service, "list_user_syllabuses", lambda user_id: [relation] if user_id == 72 else [])
    monkeypatch.setattr(profile_service, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 172 else None)
    monkeypatch.setattr(profile_syllabus, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 172 else None)
    monkeypatch.setattr(profile_tools, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 172 else None)
    monkeypatch.setattr(profile_syllabus, "set_personal_syllabus_path", fake_set_personal_syllabus_path)
    monkeypatch.setattr(profile_storage, "set_personal_profile_path", lambda user_id, syllabus_id, path: True)
    monkeypatch.setattr(profile_runtime, "get_learning_profile_agent", lambda: agent)
    monkeypatch.setattr(profile_service, "collect_history_entries", lambda *args, **kwargs: [])

    now = {"value": 1760000000}
    monkeypatch.setattr(profile_service, "time", lambda: now["value"])
    monkeypatch.setattr(profile_syllabus, "time", lambda: now["value"])

    def build_profile(dialogue_text, correct):
        return lpt.build_learning_profile(
            user_id=72,
            syllabus_id=172,
            dialogue_text=dialogue_text,
            learning_goal="掌握 HBase RowKey 设计",
            answer_records=[
                {
                    "question": "RowKey 如何避免热点？",
                    "correct": correct,
                    "answered_at": now["value"],
                    "time_spent_seconds": 120,
                    "meta": {"knowledge_points": ["RowKey 热点"]},
                }
            ],
        )

    def append_many(level, count):
        results = []
        for index in range(count):
            now["value"] += 1
            results.append(
                lpt.append_profile_personal_syllabus_suggestion(
                    72,
                    172,
                    {
                        "week_index": 1,
                        "suggested_competance": level,
                        "confidence": 0.92,
                        "reason": f"{level} signal {index + 1}",
                        "evidence": ["dialogue_text", "answer_records"],
                    },
                )
            )
        return results

    observations = []

    initial_profile = build_profile("我对 RowKey 热点还是很不清楚。", False)
    initial_data = json.loads(open(relation.personal_syllabus_path, "r", encoding="utf-8").read())
    observations.append({
        "round": "init_profile",
        "profile_week_competance": initial_profile["knowledge_mastery"]["week_items"][0]["competance"],
        "file_competance": initial_data["period"][0]["competance"],
        "candidate_suggestions": len(initial_profile["suggested_personal_syllabus_updates"]),
    })

    weak_results = append_many("weak", 5)
    weak_profile = build_profile("我继续补 RowKey 热点。", False)
    weak_data = json.loads(open(relation.personal_syllabus_path, "r", encoding="utf-8").read())
    observations.append({
        "round": "after_weak_threshold",
        "append_applied_sequence": [item["applied"] for item in weak_results],
        "profile_week_competance": weak_profile["knowledge_mastery"]["week_items"][0]["competance"],
        "file_competance": weak_data["period"][0]["competance"],
        "file_progress": weak_data["period"][0]["competance_progress"],
    })

    master_round_one = append_many("master_far", 5)
    profile_after_master_one = build_profile("我已经能解释 RowKey 预分区了。", True)
    master_one_data = json.loads(open(relation.personal_syllabus_path, "r", encoding="utf-8").read())
    observations.append({
        "round": "after_master_threshold_one",
        "append_applied_sequence": [item["applied"] for item in master_round_one],
        "profile_week_competance": profile_after_master_one["knowledge_mastery"]["week_items"][0]["competance"],
        "file_competance": master_one_data["period"][0]["competance"],
        "file_progress": master_one_data["period"][0]["competance_progress"],
    })

    master_round_two = append_many("master_far", 5)
    profile_after_master_two = build_profile("我可以独立设计 RowKey 方案。", True)
    master_two_data = json.loads(open(relation.personal_syllabus_path, "r", encoding="utf-8").read())
    observations.append({
        "round": "after_master_threshold_two",
        "append_applied_sequence": [item["applied"] for item in master_round_two],
        "profile_week_competance": profile_after_master_two["knowledge_mastery"]["week_items"][0]["competance"],
        "file_competance": master_two_data["period"][0]["competance"],
        "file_progress": master_two_data["period"][0]["competance_progress"],
    })

    assert observations[0]["file_competance"] == "none"
    assert observations[1]["file_competance"] == "weak"
    assert observations[1]["profile_week_competance"] == "weak"
    assert observations[2]["file_competance"] == "weak"
    assert observations[2]["file_progress"] == 3
    assert observations[3]["file_competance"] == "normal"
    assert observations[3]["profile_week_competance"] == "normal"
    assert observations[3]["file_progress"] == 0
    assert len(master_two_data["period"][0]["suggestion_history"]) == 15

    print(
        "\nMULTI_ROUND_PROPAGATION_RESULT",
        json.dumps(observations, ensure_ascii=False, indent=2),
    )


@pytest.mark.llm
def test_real_learning_profile_agent_full_chain_integration(monkeypatch, db_real_learning_profile_case):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real learning profile agent full-chain integration test.")

    _normalize_model_for_dashscope()
    user, syllabus, relation = db_real_learning_profile_case
    monkeypatch.setattr(profile_service, "collect_history_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr(profile_service, "time", lambda: 1760000000)
    monkeypatch.setattr(profile_syllabus, "time", lambda: 1760000000)

    trace = []

    def wrap(tool_name, func):
        def traced(state):
            trace.append(tool_name)
            result = func(state)
            state["tool_trace"] = trace[:]
            return result

        return traced

    monkeypatch.setattr(profile_tools, "_tool_load_existing_profile_context", wrap("load_existing_profile_context", profile_tools._tool_load_existing_profile_context))
    monkeypatch.setattr(profile_tools, "_tool_load_history_context", wrap("load_history_context", profile_tools._tool_load_history_context))
    monkeypatch.setattr(profile_tools, "_tool_load_personal_syllabus_context", wrap("load_personal_syllabus_context", profile_tools._tool_load_personal_syllabus_context))
    monkeypatch.setattr(profile_tools, "_tool_normalize_events", wrap("normalize_events", profile_tools._tool_normalize_events))
    monkeypatch.setattr(profile_tools, "_tool_compute_features", wrap("compute_features", profile_tools._tool_compute_features))
    monkeypatch.setattr(profile_tools, "_tool_assemble_profile", wrap("assemble_profile", profile_tools._tool_assemble_profile))
    monkeypatch.setattr(profile_tools, "_tool_save_or_update_profile", wrap("save_or_update_profile", profile_tools._tool_save_or_update_profile))
    profile_runtime.get_learning_profile_agent.cache_clear()
    payload = {
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
        "dialogue_text": [
            "我正在学 HBase，RowKey 热点和预分区很容易卡住。",
            "我希望一周内能做出一个合理的 RowKey 设计。"
        ],
        "learning_goal": "掌握 HBase RowKey 设计",
        "answer_records": [
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "answered_at": 1760000000,
                "time_spent_seconds": 180,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            }
        ],
        "resource_usage": [
            {
                "resource_id": "mindmap_rowkey",
                "action": "view",
                "timestamp": 1760000000,
                "meta": {"title": "RowKey 思维导图"},
            }
        ],
    }

    try:
        profile = lpt.build_learning_profile(**payload)
    finally:
        profile_runtime.get_learning_profile_agent.cache_clear()

    initialized = json.loads(open(relation.personal_syllabus_path, "r", encoding="utf-8").read())
    working_syllabus = json.loads(open(WORKING_SYLLABUS_PATH, "r", encoding="utf-8").read())
    output = {
        "profile": profile,
        "tool_trace": trace,
        "personal_syllabus_path": relation.personal_syllabus_path,
        "personal_profile_path": relation.personal_profile_path,
        "initialized_personal_syllabus": initialized,
    }

    assert output["profile"] is not None
    assert output["personal_syllabus_path"]
    assert len(output["initialized_personal_syllabus"]["period"]) == len(working_syllabus["period"])
    assert any("HBase" in str(item.get("content", "")) for item in output["initialized_personal_syllabus"]["period"])
    assert output["initialized_personal_syllabus"]["period"][0]["competance"] == "none"
    assert output["initialized_personal_syllabus"]["period"][0]["suggestion_history"] == []
    assert output["profile"]["suggested_personal_syllabus_updates"] is not None
    assert "load_personal_syllabus_context" in trace
    assert "normalize_events" in trace
    assert "compute_features" in trace
    assert "assemble_profile" in trace
    assert output["personal_profile_path"]

    print(
        "\nREAL_AGENT_FULL_CHAIN_RESULT",
        json.dumps(
            {
                "tool_trace": trace,
                "personal_syllabus_path": output["personal_syllabus_path"],
                "profile_path": output["personal_profile_path"],
                "initial_personal_competance": output["initialized_personal_syllabus"]["period"][0]["competance"],
                "suggestion_count": len(profile.get("suggested_personal_syllabus_updates") or []),
                "source_events": profile.get("source_events"),
                "resource_preference": profile.get("resource_preference"),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
