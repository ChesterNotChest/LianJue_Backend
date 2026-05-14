from types import SimpleNamespace

from tasks import learning_profile_task as lpt


class _FakeRunResult:
    def __init__(self, output):
        self.output = output


class _ProfileToolchainAgent:
    def run_sync(self, user_prompt, deps=None, **kwargs):
        state = deps.state
        lpt._tool_load_history_context(state)
        lpt._tool_load_personal_syllabus_context(state)
        lpt._tool_normalize_events(state)
        lpt._tool_compute_features(state)
        lpt._tool_assemble_profile(state)
        return _FakeRunResult(lpt.LearningProfileResult(success=True, profile=state["profile"]))


def _install_profile_mocks(monkeypatch, user, syllabuses, relations, personal_payloads):
    relation_by_syllabus = {relation.syllabus_id: relation for relation in relations}
    syllabus_by_id = {syllabus.syllabus_id: syllabus for syllabus in syllabuses}
    personal_by_syllabus = dict(personal_payloads)

    monkeypatch.setattr(lpt, "get_user_by_id", lambda user_id: user if user_id == user.user_id else None)
    monkeypatch.setattr(lpt, "list_user_syllabuses", lambda user_id: relations if user_id == user.user_id else [])
    monkeypatch.setattr(lpt, "get_user_syllabus", lambda user_id, syllabus_id: relation_by_syllabus.get(syllabus_id))
    monkeypatch.setattr(lpt, "get_syllabus_by_id", lambda syllabus_id: syllabus_by_id.get(syllabus_id))
    monkeypatch.setattr(
        lpt,
        "_load_personal_syllabus",
        lambda user_id, syllabus_id=None: [
            (
                sid,
                personal_by_syllabus[sid],
                {},
            )
            for sid in sorted(personal_by_syllabus)
            if syllabus_id is None or sid == syllabus_id
        ],
    )
    monkeypatch.setattr(lpt, "_collect_history_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr(lpt, "set_personal_profile_path", lambda *args, **kwargs: True)
    monkeypatch.setattr(lpt, "get_learning_profile_agent", lambda: _ProfileToolchainAgent())
    monkeypatch.setattr(lpt, "time", lambda: 1760000000)


def test_profile_from_personal_syllabus_only(monkeypatch):
    user = SimpleNamespace(user_id=81, user_name="syllabus-only", email="s@example.com")
    syllabus = SimpleNamespace(syllabus_id=181, title="HBase", syllabus_path=None)
    relation = SimpleNamespace(
        user_id=81,
        syllabus_id=181,
        personal_syllabus_path="schedule/student_alt/user_81/181_personal.json",
        personal_profile_path=None,
    )
    personal = {
        "period": [
            {
                "week_index": 1,
                "content": "RowKey 热点",
                "competance": "weak",
                "competance_progress": -1,
            },
            {
                "week_index": 2,
                "content": "列族设计",
                "competance": "master",
                "competance_progress": 1,
            },
        ]
    }
    _install_profile_mocks(monkeypatch, user, [syllabus], [relation], {181: personal})

    profile = lpt.build_learning_profile(user_id=81, syllabus_id=181)

    assert profile["knowledge_mastery"]["weak_weeks"] == [1]
    assert profile["knowledge_mastery"]["mastered_weeks"] == [2]
    assert profile["knowledge_mastery"]["week_items"][0]["competance"] == "weak"
    assert profile["source_events"] == []
    assert profile["confidence"] > 0.0


def test_profile_resolves_personal_syllabus_and_answer_record_conflict(monkeypatch):
    user = SimpleNamespace(user_id=82, user_name="conflict", email="c@example.com")
    syllabus = SimpleNamespace(syllabus_id=182, title="HBase", syllabus_path=None)
    relation = SimpleNamespace(
        user_id=82,
        syllabus_id=182,
        personal_syllabus_path="schedule/student_alt/user_82/182_personal.json",
        personal_profile_path=None,
    )
    personal = {
        "period": [
            {
                "week_index": 1,
                "content": "RowKey 热点",
                "competance": "master",
                "competance_progress": 1,
            }
        ]
    }
    _install_profile_mocks(monkeypatch, user, [syllabus], [relation], {182: personal})

    profile = lpt.build_learning_profile(
        user_id=82,
        syllabus_id=182,
        dialogue_text="我以为自己懂 RowKey，但最近题目都错了。",
        answer_records=[
            {
                "question": "RowKey 如何避免热点？",
                "correct": False,
                "answered_at": 1760000000,
                "time_spent_seconds": 150,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            },
            {
                "question": "预分区为什么能缓解热点？",
                "correct": False,
                "answered_at": 1760000100,
                "time_spent_seconds": 160,
                "meta": {"knowledge_points": ["RowKey 热点"]},
            },
        ],
    )

    assert profile["knowledge_mastery"]["week_items"][0]["competance"] == "master"
    assert profile["knowledge_mastery"]["knowledge_point_details"]["RowKey 热点"]["attempt_count"] == 2
    assert profile["knowledge_mastery"]["by_knowledge_point"]["RowKey 热点"] < 0.5
    assert profile["conflict_resolution"]["objective_priority"] == "behavior_and_answer_records"
    assert "RowKey 热点" in profile["concept_gaps"]


def test_profile_handles_dialogue_only_and_dirty_inputs(monkeypatch):
    user = SimpleNamespace(user_id=83, user_name="dirty", email="d@example.com")
    _install_profile_mocks(monkeypatch, user, [], [], {})

    profile = lpt.build_learning_profile(
        user_id=83,
        dialogue_text=[
            "我很焦虑，HBase 怎么都看不懂。",
            {"note": "希望一周内掌握 RowKey 基础"},
            None,
        ],
        learning_records=["bad-shape", {"duration_minutes": "not-a-number"}],
        answer_records=[None, "bad-answer"],
        resource_usage=[
            {
                "resource_id": "mindmap_rowkey",
                "action": "view",
                "timestamp": 1760000000,
                "meta": {"title": "RowKey 思维导图"},
            },
            "bad-resource",
        ],
    )

    assert profile["emotion_state"]["label"] == "frustrated"
    assert profile["goal_clarity"]["score"] > 0.0
    assert "resource_usage" in profile["source_events"]
    assert "visual" in profile["resource_preference"]


def test_profile_merges_multiple_syllabus_scopes(monkeypatch):
    user = SimpleNamespace(user_id=84, user_name="multi", email="m@example.com")
    syllabus_a = SimpleNamespace(syllabus_id=184, title="HBase A", syllabus_path=None)
    syllabus_b = SimpleNamespace(syllabus_id=185, title="HBase B", syllabus_path=None)
    relation_a = SimpleNamespace(
        user_id=84,
        syllabus_id=184,
        personal_syllabus_path="schedule/student_alt/user_84/184_personal.json",
        personal_profile_path=None,
    )
    relation_b = SimpleNamespace(
        user_id=84,
        syllabus_id=185,
        personal_syllabus_path="schedule/student_alt/user_84/185_personal.json",
        personal_profile_path=None,
    )
    personal_a = {
        "period": [
            {
                "week_index": 1,
                "content": "HBase RowKey",
                "competance": "weak",
                "competance_progress": -1,
            }
        ]
    }
    personal_b = {
        "period": [
            {
                "week_index": 3,
                "content": "HDFS 副本机制",
                "competance": "master",
                "competance_progress": 1,
            }
        ]
    }
    _install_profile_mocks(
        monkeypatch,
        user,
        [syllabus_a, syllabus_b],
        [relation_a, relation_b],
        {184: personal_a, 185: personal_b},
    )

    profile = lpt.build_learning_profile(user_id=84)

    week_items = profile["knowledge_mastery"]["week_items"]
    assert len(profile["syllabus_scope"]) == 2
    assert {item["week_index"] for item in week_items} == {1, 3}
    assert profile["knowledge_mastery"]["weak_weeks"] == [1]
    assert profile["knowledge_mastery"]["mastered_weeks"] == [3]
