from types import SimpleNamespace

from tasks import learning_profile_task as lpt
from tasks.learning_profile import agent_runtime as profile_runtime
from tasks.learning_profile import agent_tools as profile_tools
from tasks.learning_profile import alignment, profile_builder
from tasks.learning_profile import service as profile_service
from tasks.learning_profile.models import LearningProfileResult


def test_build_learning_profile_uses_behavior_answer_and_resource_signals(
    monkeypatch, repo_json_factory
):
    personal_path = repo_json_factory(
        "schedule/student_alt",
        {
            "period": [
                {
                    "week_index": 1,
                    "content": "Python 变量与循环",
                    "enhanced_content": "循环结构与变量作用域",
                    "competance": "weak",
                    "competance_progress": -1,
                },
                {
                    "week_index": 2,
                    "content": "函数参数与返回值",
                    "enhanced_content": "函数参数、返回值与作用域",
                    "competance": "normal",
                    "competance_progress": 1,
                },
            ]
        },
        prefix="learning_profile",
    )
    user = SimpleNamespace(user_id=7, user_name="alice", email="alice@example.com")
    user_syllabus = SimpleNamespace(
        syllabus_id=19, personal_syllabus_path=str(personal_path)
    )
    syllabus = SimpleNamespace(syllabus_id=19, title="Python 基础", syllabus_path=None)

    class FakeRunResult:
        def __init__(self, output):
            self.output = output

    class FakeAgent:
        def __init__(self):
            self.calls = 0

        def run_sync(self, user_prompt, deps=None, **kwargs):
            self.calls += 1
            state = deps.state
            profile_tools._tool_load_history_context(state)
            profile_tools._tool_normalize_events(state)
            profile_tools._tool_compute_features(state)
            profile_tools._tool_assemble_profile(state)
            return FakeRunResult(
                LearningProfileResult(success=True, profile=state["profile"])
            )

    fake_agent = FakeAgent()

    monkeypatch.setattr(profile_service, "get_user_by_id", lambda user_id: user if user_id == 7 else None)
    monkeypatch.setattr(
        profile_service, "list_user_syllabuses", lambda user_id: [user_syllabus] if user_id == 7 else []
    )
    monkeypatch.setattr(
        profile_service, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 19 else None
    )
    monkeypatch.setattr(profile_runtime, "get_learning_profile_agent", lambda: fake_agent)
    monkeypatch.setattr(profile_service, "collect_history_entries", lambda user_id, syllabus_id=None: [])
    monkeypatch.setattr(profile_service, "load_personal_syllabus_rows", lambda user_id, syllabus_id=None: [])
    monkeypatch.setattr(profile_service, "time", lambda: 1760000000)

    profile = lpt.build_learning_profile(
        user_id=7,
        syllabus_id=19,
        dialogue_text=(
            "我最近在学 Python，"
            "函数参数总是看不懂，"
            "练习时经常卡住，感觉很吃力，"
            "想两周内掌握循环和函数。"
        ),
        learning_goal="掌握 Python 基础语法",
        learning_records=[
            {
                "event_type": "study_session",
                "duration_minutes": 42,
                "started_at": 1759913600,
                "meta": {"topic": "循环"},
            },
            {
                "event_type": "practice",
                "duration_minutes": 36,
                "started_at": 1759996400,
                "meta": {"topic": "函数"},
            },
        ],
        answer_records=[
            {
                "question": "函数参数应该怎么传递？",
                "correct": False,
                "answered_at": 1759998200,
                "time_spent_seconds": 160,
                "meta": {"knowledge_points": ["函数参数"]},
            },
            {
                "question": "循环嵌套如何执行？",
                "correct": True,
                "answered_at": 1759999000,
                "time_spent_seconds": 100,
                "meta": {"knowledge_points": ["循环嵌套"]},
            },
            {
                "question": "函数返回值是什么？",
                "correct": False,
                "answered_at": 1759999800,
                "time_spent_seconds": 180,
                "meta": {"knowledge_points": ["函数参数"]},
            },
        ],
        resource_usage=[
            {
                "resource_id": "video_python_functions",
                "action": "complete",
                "timestamp": 1759999900,
                "duration_seconds": 900,
                "meta": {"knowledge_points": ["函数参数"]},
            }
        ],
    )
    assert fake_agent.calls == 1
    assert profile is not None
    assert profile["study_frequency"] in {"medium", "high"}
    assert profile["study_duration"] == "medium"
    assert "answer_records" in profile["source_events"]
    assert profile["confidence"] > 0.5
    assert profile["dropout_risk_score"] >= 0.0
    assert "函数参数" in profile["concept_gaps"]
    assert (
        profile["knowledge_mastery"]["by_knowledge_point"]["函数参数"]
        < profile["knowledge_mastery"]["by_knowledge_point"]["循环嵌套"]
    )
    assert (
        profile["knowledge_mastery"]["knowledge_point_details"]["函数参数"]["attempt_count"]
        == 2
    )
    assert profile["goal_clarity"]["score"] > 0.7
    assert profile["emotion_state"]["label"] == "frustrated"
    assert "frustration_signal" in profile["recent_anomaly"]
    assert (
        profile["conflict_resolution"]["objective_priority"]
        == "behavior_and_answer_records"
    )
    assert profile["signals"]["answer_record_count"] == 3
    assert profile["evidence"]


def test_learning_record_scores_contribute_to_knowledge_mastery():
    learning_events = alignment.normalize_learning_events([
        {
            "event_type": "practice",
            "score": 0.48,
            "started_at": 1760000000,
            "meta": {"knowledge_points": ["function_practice"]},
        },
        {
            "event_type": "study_session",
            "score": 0.72,
            "started_at": 1760000000,
            "meta": {"knowledge_points": ["hbase_intro"]},
        },
    ])

    mastery = profile_builder.build_answer_mastery([], 1760000000, learning_events)

    assert mastery["by_knowledge_point"]["function_practice"] == 0.48
    assert mastery["knowledge_point_details"]["function_practice"]["level"] == "medium"
    assert mastery["by_knowledge_point"]["hbase_intro"] == 0.72
    assert mastery["knowledge_point_details"]["hbase_intro"]["level"] == "high"


def test_build_learning_profile_returns_tool_profile_when_agent_final_output_fails(monkeypatch):
    user = SimpleNamespace(user_id=7, user_name="alice", email="alice@example.com")
    user_syllabus = SimpleNamespace(syllabus_id=19, personal_syllabus_path=None)
    syllabus = SimpleNamespace(syllabus_id=19, title="Python 基础", syllabus_path=None)

    class FakeAgent:
        def run_sync(self, user_prompt, deps=None, **kwargs):
            state = deps.state
            profile_tools._tool_normalize_events(state)
            profile_tools._tool_compute_features(state)
            profile_tools._tool_assemble_profile(state)
            raise RuntimeError("final output validation failed")

    monkeypatch.setattr(profile_service, "get_user_by_id", lambda user_id: user if user_id == 7 else None)
    monkeypatch.setattr(
        profile_service, "list_user_syllabuses", lambda user_id: [user_syllabus] if user_id == 7 else []
    )
    monkeypatch.setattr(
        profile_service, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 19 else None
    )
    monkeypatch.setattr(profile_runtime, "get_learning_profile_agent", lambda: FakeAgent())
    monkeypatch.setattr(profile_service, "collect_history_entries", lambda user_id, syllabus_id=None: [])
    monkeypatch.setattr(profile_service, "load_personal_syllabus_rows", lambda user_id, syllabus_id=None: [])
    monkeypatch.setattr(profile_service, "time", lambda: 1760000000)
    monkeypatch.setattr(profile_service, "_tool_save_or_update_profile", lambda state: {"success": True})

    profile = lpt.build_learning_profile(
        user_id=7,
        syllabus_id=19,
        dialogue_text="我想补 Python 函数参数。",
        learning_goal="掌握 Python 基础语法",
    )

    assert isinstance(profile, dict)
    assert profile["user_id"] == 7
    assert profile["learning_goal"] == "掌握 Python 基础语法"


def test_build_learning_profile_can_call_context_tools_before_feature_tools(
    monkeypatch, repo_json_factory
):
    personal_path = repo_json_factory(
        "schedule/student_alt",
        {
            "period": [
                {
                    "week_index": 1,
                    "content": "Python 变量与循环",
                    "enhanced_content": "循环结构与变量作用域",
                    "competance": "weak",
                    "competance_progress": -1,
                }
            ]
        },
        prefix="learning_profile",
    )
    user = SimpleNamespace(user_id=8, user_name="bob", email="bob@example.com")
    user_syllabus = SimpleNamespace(
        syllabus_id=20, personal_syllabus_path=str(personal_path)
    )
    syllabus = SimpleNamespace(syllabus_id=20, title="Python 基础", syllabus_path=None)
    history_entries = [
        {
            "question": "循环嵌套如何执行？",
            "answer": "先执行内层循环",
            "timestamp": 1759998000,
        }
    ]

    class FakeRunResult:
        def __init__(self, output):
            self.output = output

    class FakeAgent:
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
            return FakeRunResult(
                LearningProfileResult(success=True, profile=state["profile"])
            )

    fake_agent = FakeAgent()

    monkeypatch.setattr(profile_service, "get_user_by_id", lambda user_id: user if user_id == 8 else None)
    monkeypatch.setattr(
        profile_service, "list_user_syllabuses", lambda user_id: [user_syllabus] if user_id == 8 else []
    )
    monkeypatch.setattr(
        profile_service, "get_syllabus_by_id", lambda syllabus_id: syllabus if syllabus_id == 20 else None
    )
    monkeypatch.setattr(profile_runtime, "get_learning_profile_agent", lambda: fake_agent)
    monkeypatch.setattr(profile_service, "collect_history_entries", lambda *args, **kwargs: history_entries)
    monkeypatch.setattr(
        profile_service,
        "load_personal_syllabus_rows",
        lambda *args, **kwargs: [
            (
                20,
                {
                    "period": [
                        {
                            "week_index": 1,
                            "content": "Python 变量与循环",
                            "enhanced_content": "循环结构与变量作用域",
                            "competance": "weak",
                            "competance_progress": -1,
                        }
                    ]
                },
                {},
            )
        ],
    )
    monkeypatch.setattr(profile_service, "time", lambda: 1760000000)

    profile = lpt.build_learning_profile(
        user_id=8,
        syllabus_id=20,
        dialogue_text="我想知道循环和函数的区别",
        learning_goal="掌握 Python 基础语法",
        learning_records=[
            {
                "event_type": "study_session",
                "duration_minutes": 20,
                "started_at": 1759993600,
                "meta": {"topic": "循环"},
            }
        ],
        answer_records=[
            {
                "question": "循环嵌套如何执行？",
                "correct": True,
                "answered_at": 1759999000,
                "time_spent_seconds": 100,
                "meta": {"knowledge_points": ["循环嵌套"]},
            }
        ],
        resource_usage=[],
    )

    assert fake_agent.calls == 1
    assert profile["signals"]["history_count"] == 1
    assert "history" in profile["source_events"]
    assert profile["confidence"] > 0
