import os
from pathlib import Path
import shutil
import uuid

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks.study_graph import student_agent as sat
from tasks.study_graph import storage as study_graph_storage


WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"
TEST_STUDY_GRAPH_ROOT = Path(__file__).resolve().parent / "artifacts" / "study_graph"


def _reset_artifact_root(name: str) -> Path:
    root = TEST_STUDY_GRAPH_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_model_for_dashscope():
    text_config = sat.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        sat.get_student_agent.cache_clear()


def _student_agent_payload(
    user_id: int,
    syllabus_id: int,
    *,
    sequence: int,
    question: str,
    topic: str,
    signal: str,
    confidence: float,
    parent_candidates: list[dict] | None = None,
    event_kind: str = "answer",
    is_correct: bool = True,
    timestamp: int = 1760000000,
) -> dict:
    return {
        "dispatch_id": f"dispatch:{user_id}:{syllabus_id}:{sequence:03d}",
        "source_kind": "total_agent",
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "subject_title": "大数据概论",
        "question": question,
        "learning_goal": "掌握 HBase RowKey 设计",
        "personal_syllabus_context": {
            "learning_goal": "掌握 HBase RowKey 设计",
            "matched_weeks": [
                {"week_index": 1, "title": "HBase RowKey 设计", "content": "RowKey 热点、散列、预分区"}
            ],
        },
        "rag_context": [{"title": topic, "summary": f"{topic} 是本轮学习的主要知识点。"}],
        "detected_topics": [{"title": topic, "confidence": confidence, "signal": signal}],
        "events": [{"kind": event_kind, "topic": topic, "question": question, "is_correct": is_correct}],
        "parent_candidates": parent_candidates or [],
        "source": {"kind": "total_agent", "summary": "total agent dispatch"},
        "timestamp": timestamp,
    }


@pytest.fixture
def db_student_agent_case():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real student agent choice smoke test.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")

    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"student-agent-{suffix}",
            password_hash="pytest-not-used",
            email=f"student-agent-{suffix}@example.com",
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
def test_student_agent_selects_expected_tools(monkeypatch, db_student_agent_case):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real student agent choice smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("integration_agent_choice")
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: artifact_root)
    user, syllabus, relation = db_student_agent_case
    trace = []

    def wrap(tool_name, func):
        def traced(*args, **kwargs):
            trace.append(tool_name)
            return func(*args, **kwargs)

        return traced

    orig_get_context = sat.get_student_learning_tree_context
    orig_submit = sat.submit_learning_tree_changes
    orig_features = sat.get_learning_tree_features
    orig_tree = sat.get_student_learning_tree

    monkeypatch.setattr(sat, "search_tool", lambda query, **kwargs: {"success": True, "result_count": 1, "paragraphs": ["RowKey 热点"]})
    monkeypatch.setattr(sat, "get_student_learning_tree_context", wrap("get_student_learning_tree_context", orig_get_context))
    monkeypatch.setattr(sat, "submit_learning_tree_changes", wrap("submit_learning_tree_changes", orig_submit))
    monkeypatch.setattr(sat, "get_learning_tree_features", wrap("get_learning_tree_features", orig_features))
    monkeypatch.setattr(sat, "get_student_learning_tree", wrap("get_student_learning_tree", orig_tree))

    payload = {
        "dispatch_id": f"dispatch:{user.user_id}:{syllabus.syllabus_id}:001",
        "source_kind": "total_agent",
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
        "subject_title": "大数据概论",
        "question": "RowKey 如何避免热点？",
        "learning_goal": "掌握 HBase RowKey 设计",
        "personal_syllabus_context": {
            "learning_goal": "掌握 HBase RowKey 设计",
            "matched_weeks": [
                {"week_index": 1, "title": "HBase RowKey 设计", "content": "RowKey 热点、散列、预分区"}
            ],
        },
        "rag_context": [{"title": "HBase RowKey 设计", "summary": "RowKey 热点通常来自单调递增键或访问集中。"}],
        "detected_topics": [{"title": "RowKey 热点", "confidence": 0.78, "signal": "struggled"}],
        "events": [{"kind": "answer", "question": "RowKey 如何避免热点？", "is_correct": False}],
        "parent_candidates": [],
        "source": {"kind": "total_agent", "summary": "total agent dispatch"},
        "timestamp": 1760000000,
    }

    result = sat.run_student_agent(payload)
    assert result.success is True
    assert result.tree is not None
    assert result.features is not None
    assert trace[:2] == ["get_student_learning_tree_context", "submit_learning_tree_changes"]
    post_submit_trace = trace[2:]
    assert "get_student_learning_tree" in post_submit_trace
    assert "get_learning_tree_features" in post_submit_trace


@pytest.mark.llm
def test_student_agent_accumulates_multi_payload_tree(monkeypatch, db_student_agent_case):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real student agent choice smoke test.")

    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("integration_multi_payload_tree")
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: artifact_root)
    user, syllabus, relation = db_student_agent_case
    submit_trace = []

    orig_submit = sat.submit_learning_tree_changes

    def traced_submit(*args, **kwargs):
        submit_trace.append({"args": args, "kwargs": kwargs})
        return orig_submit(*args, **kwargs)

    monkeypatch.setattr(
        sat,
        "search_tool",
        lambda query, **kwargs: {
            "success": True,
            "result_count": 1,
            "paragraphs": [f"{query} 相关资料"],
            "results": [{"rank": 1, "content": f"{query} 相关资料"}],
        },
    )
    monkeypatch.setattr(sat, "submit_learning_tree_changes", traced_submit)

    payloads = [
        _student_agent_payload(
            user.user_id,
            syllabus.syllabus_id,
            sequence=1,
            question="HBase RowKey 设计包含哪些核心原则？",
            topic="HBase RowKey 设计",
            signal="learned",
            confidence=0.86,
            timestamp=1760000000,
        ),
        _student_agent_payload(
            user.user_id,
            syllabus.syllabus_id,
            sequence=2,
            question="RowKey 如何避免热点？",
            topic="RowKey 热点",
            signal="struggled",
            confidence=0.78,
            parent_candidates=[{"title": "HBase RowKey 设计", "child_title": "RowKey 热点"}],
            is_correct=False,
            timestamp=1760000600,
        ),
        _student_agent_payload(
            user.user_id,
            syllabus.syllabus_id,
            sequence=3,
            question="预分区策略如何缓解 RowKey 热点？",
            topic="预分区策略",
            signal="learned",
            confidence=0.74,
            parent_candidates=[{"title": "RowKey 热点", "child_title": "预分区策略"}],
            timestamp=1760001200,
        ),
        _student_agent_payload(
            user.user_id,
            syllabus.syllabus_id,
            sequence=4,
            question="散列前缀为什么能减少写入集中？",
            topic="散列前缀",
            signal="practiced",
            confidence=0.72,
            parent_candidates=[{"title": "RowKey 热点", "child_title": "散列前缀"}],
            event_kind="practice",
            timestamp=1760001800,
        ),
    ]

    for payload in payloads:
        result = sat.run_student_agent(payload)
        assert result.success is True

    assert len(submit_trace) >= len(payloads)
    assert all(item["kwargs"].get("subject_title") == "大数据概论" for item in submit_trace)

    tree_result = sat.get_student_learning_tree(user.user_id, syllabus.syllabus_id)
    features = sat.get_learning_tree_features(user.user_id, syllabus.syllabus_id)
    assert tree_result["success"] is True
    assert features["success"] is True
    tree = tree_result["tree"]
    nodes = tree.get("nodes") or []
    edges = tree.get("edges") or []
    learned_topics = set(features.get("learned_topics") or [])

    assert tree["subject_title"] == "大数据概论"
    assert tree["title"] == "大数据概论学习成长树"
    assert tree["virtual_root"]["title"] == "大数据概论"
    assert len(nodes) >= 3
    assert len(edges) >= 1
    assert {"HBase RowKey 设计", "RowKey 热点"}.issubset(learned_topics)
