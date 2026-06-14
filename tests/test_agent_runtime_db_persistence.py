import json

import pytest
from flask import Flask
from pydantic_ai.messages import FunctionToolResultEvent, ToolReturnPart

from extensions import db
from schemas.agent_runtime_state import (
    ChatSession,
    ChatTurn,
    GeneratedResource,
    LearningPlan,
    LearningPlanEvent,
    LearningPlanStep,
    RecommendationSnapshot,
    StudyGraphChangeLog,
    StudyGraphNode,
    StudyGraphTree,
)
from tasks import generative_task as gt
from tasks import personal_recommendation_task as prt
from tasks.common import status_events
from tasks.total_agent import agent_contracts as tac
from tasks.total_agent import agent_runtime
from tasks.total_agent import agent_tools as tagt
from tasks.study_graph import storage as study_graph_storage
from tasks.study_graph_task import build_study_graph_changes_from_student_payload, get_student_learning_tree, submit_learning_tree_changes


def _make_sqlite_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


def _make_threaded_sqlite_app(tmp_path):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(tmp_path / "threaded-runtime.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


def _recommendation_result():
    return {
        "graph": {
            "nodes": [
                {"id": "n1", "title": "Intro", "outcomes": ["a"]},
                {"id": "n2", "title": "Next", "outcomes": ["b"]},
            ],
            "edges": [{"edge_id": "n1->n2", "source": "n1", "target": "n2"}],
        },
        "candidates": [{"path": ["n1", "n2"], "skills": ["a", "b"], "path_edges": []}],
        "best_path": {"path": ["n1", "n2"], "skills": ["a", "b"], "path_edges": []},
    }


def _recommendation_snapshot_result():
    result = _recommendation_result()
    result.update(
        {
            "success": True,
            "selected": [result["best_path"]],
            "rag_overlay": {"used": True},
            "planning_hints": {"path_depth": 2},
        }
    )
    return result


def test_learning_plan_uses_database_backend_when_app_context(monkeypatch):
    monkeypatch.delenv("PERSONAL_RECOMMENDATION_ROOT", raising=False)
    monkeypatch.delenv("LEARNING_PLAN_FILE_BACKEND", raising=False)
    app = _make_sqlite_app()
    with app.app_context():
        result = prt.accept_recommendation_path(101, 202, _recommendation_result(), candidate_index=0)
        assert result["success"] is True

        active = prt.get_active_learning_plan(101, 202)
        assert active["plan_id"] == result["plan_id"]
        assert [step["node_id"] for step in active["steps"]] == ["n1", "n2"]
        assert LearningPlan.query.count() == 1
        assert LearningPlanStep.query.count() == 2
        assert LearningPlanEvent.query.count() == 2


def test_recommendation_snapshot_uses_database_backend_when_app_context(monkeypatch):
    monkeypatch.delenv("PERSONAL_RECOMMENDATION_ROOT", raising=False)
    monkeypatch.delenv("RECOMMENDATION_SNAPSHOT_FILE_BACKEND", raising=False)
    app = _make_sqlite_app()
    with app.app_context():
        saved = prt.save_recommendation_snapshot(
            111,
            222,
            _recommendation_snapshot_result(),
            request_payload={"goals": ["a"], "session_id": "sess-db"},
        )
        detail = prt.get_recommendation_snapshot(saved["recommendation_id"])
        listing = prt.list_recommendation_snapshots(111, 222)

        assert saved["success"] is True
        assert detail["success"] is True
        assert detail["snapshot"]["recommendation"]["graph"]["nodes"][0]["id"] == "n1"
        assert listing["snapshots"][0]["candidate_count"] == 1
        assert RecommendationSnapshot.query.count() == 1


def test_generated_resource_metadata_uses_database_backend_when_app_context(monkeypatch):
    monkeypatch.delenv("GENERATIVE_FILE_BACKEND", raising=False)
    monkeypatch.delenv("GENERATOR_FILE_BACKEND", raising=False)
    app = _make_sqlite_app()
    with app.app_context():
        entry = gt.append_manifest_entry(
            303,
            {
                "resource_id": "documents-test-db",
                "resource_type": "documents",
                "title": "Intro document",
                "topic": "Intro",
                "user_id": 303,
                "syllabus_id": 404,
                "status": "ready",
                "resource_dir": "generative/user_303/documents/documents-test-db",
                "main_files": {"json_path": "resource.json", "md_path": "resource.md"},
                "validation": {"valid": True},
                "metadata": {"step_id": "step_1"},
                "created_at": 1780000000,
                "updated_at": 1780000001,
            },
        )
        manifest = gt.load_manifest(303)
        assert entry["resource_id"] == "documents-test-db"
        assert manifest["resource_count"] == 1
        assert manifest["resources"][0]["main_files"]["md_path"] == "resource.md"
        assert GeneratedResource.query.count() == 1


def test_resource_processor_parallel_tasks_keep_database_app_context(monkeypatch, tmp_path):
    monkeypatch.delenv("GENERATIVE_FILE_BACKEND", raising=False)
    monkeypatch.delenv("GENERATOR_FILE_BACKEND", raising=False)
    app = _make_threaded_sqlite_app(tmp_path)

    def fake_generation(request_payload: dict) -> dict:
        resource_type = request_payload["resource_types"][0]
        entry = {
            "resource_id": f"{resource_type}-threaded-db",
            "resource_type": resource_type,
            "title": f"{resource_type} resource",
            "topic": request_payload.get("topic") or "Intro",
            "user_id": request_payload["user_id"],
            "syllabus_id": request_payload["syllabus_id"],
            "status": "ready",
            "resource_dir": f"generative/user_{request_payload['user_id']}/{resource_type}/{resource_type}-threaded-db",
            "main_files": {"json_path": "resource.json"},
            "validation": {"valid": True},
            "metadata": {"step_id": "step_1"},
            "created_at": 1780000000,
            "updated_at": 1780000001,
        }
        gt.append_manifest_entry(request_payload["user_id"], entry)
        return {
            "success": True,
            "resources": [entry],
            "tool_status_events": [
                status_events.create_status_event(
                    run_id=request_payload.get("run_id"),
                    agent="resource_agent",
                    stage="persist_generated_resource",
                    status=status_events.STATUS_SUCCEEDED,
                )
            ],
        }

    monkeypatch.setattr(tagt, "generate_resources_from_request", fake_generation)

    with app.app_context():
        result = tagt.process_resource_generation_request(
            {"tool_status_events": [], "run_id": "run-threaded-db"},
            {
                "user_id": 707,
                "syllabus_id": 808,
                "topic": "Intro",
                "resource_types": ["documents", "quiz", "ppt"],
                "run_id": "run-threaded-db",
            },
        )

        assert result["success"] is True
        assert result["overall_status"] == tac.RESOURCE_GENERATION_OVERALL_SUCCEEDED
        assert GeneratedResource.query.count() == 3
        assert {row.resource_type for row in GeneratedResource.query.all()} == {"documents", "quiz", "ppt"}


def test_study_graph_uses_database_backend_when_app_context(monkeypatch):
    monkeypatch.delenv("STUDY_GRAPH_FILE_BACKEND", raising=False)
    app = _make_sqlite_app()
    with app.app_context():
        payload = {
            "user_id": 505,
            "syllabus_id": 606,
            "subject_title": "Data Systems",
            "learning_goal": "Learn RowKey",
            "detected_topics": [{"title": "RowKey Hotspot", "confidence": 0.8, "signal": "struggled"}],
            "events": [{"kind": "answer", "topic": "RowKey Hotspot", "is_correct": False}],
            "source": {"kind": "test"},
            "timestamp": 1780000000,
        }
        changes = build_study_graph_changes_from_student_payload(payload)
        result = submit_learning_tree_changes(
            payload["user_id"],
            payload["syllabus_id"],
            changes,
            source=payload["source"],
            timestamp=payload["timestamp"],
            subject_title=payload["subject_title"],
        )
        tree = get_student_learning_tree(payload["user_id"], payload["syllabus_id"])["tree"]

        assert result["success"] is True
        assert tree["nodes"]
        assert StudyGraphTree.query.count() == 1
        assert StudyGraphNode.query.count() == 1
        assert StudyGraphChangeLog.query.count() == 1


def test_runtime_persistence_does_not_silently_fallback_to_manifest(monkeypatch):
    monkeypatch.delenv("PERSONAL_RECOMMENDATION_ROOT", raising=False)
    monkeypatch.delenv("LEARNING_PLAN_FILE_BACKEND", raising=False)
    monkeypatch.delenv("GENERATIVE_FILE_BACKEND", raising=False)
    monkeypatch.delenv("GENERATOR_FILE_BACKEND", raising=False)
    monkeypatch.delenv("STUDY_GRAPH_FILE_BACKEND", raising=False)

    with pytest.raises(RuntimeError, match="learning plan persistence requires a database app context"):
        prt.load_learning_plan_manifest(1, 2)
    with pytest.raises(RuntimeError, match="generated resource metadata requires a database app context"):
        gt.load_manifest(1)
    with pytest.raises(RuntimeError, match="study graph persistence requires a database app context"):
        study_graph_storage.load_tree_manifest(1, 2)
    with pytest.raises(RuntimeError, match="recommendation snapshot persistence requires a database app context"):
        prt.get_recommendation_snapshot("recommendation_missing")


def test_total_agent_deterministic_run_persists_chat_session_and_turns(monkeypatch):
    app = _make_sqlite_app()

    final = {
        "success": True,
        "result": {
            "answer_learning_question": {
                "answer": {"text": "Persisted answer"},
            },
            "context": {},
        },
    }

    def fake_deterministic_run(payload):
        return final

    monkeypatch.setattr(agent_runtime, "deterministic_run_total_agent", fake_deterministic_run)

    with app.app_context():
        result = agent_runtime.run_total_agent(
            {
                "user_id": 101,
                "syllabus_id": 202,
                "session_id": "sess-chat-db",
                "message": "hello persistence",
            },
            use_llm=False,
        )

        assert result is final
        session = ChatSession.query.get("sess-chat-db")
        assert session is not None
        assert session.user_id == 101
        assert session.syllabus_id == 202
        assert session.turn_count == 2

        turns = ChatTurn.query.filter_by(session_id="sess-chat-db").order_by(ChatTurn.id.asc()).all()
        assert [(turn.role, turn.content) for turn in turns] == [
            ("user", "hello persistence"),
            ("agent", "Persisted answer"),
        ]


def test_total_agent_stream_creation_persists_user_turn_before_consumption():
    app = _make_sqlite_app()

    with app.app_context():
        stream = agent_runtime.run_total_agent(
            {
                "user_id": 101,
                "syllabus_id": 202,
                "session_id": "sess-stream-db",
                "message": "hello stream",
            },
            use_llm=True,
            stream=True,
        )

        assert stream is not None
        session = ChatSession.query.get("sess-stream-db")
        assert session is not None
        assert session.turn_count == 1

        turns = ChatTurn.query.filter_by(session_id="sess-stream-db").order_by(ChatTurn.id.asc()).all()
        assert [(turn.role, turn.content) for turn in turns] == [
            ("user", "hello stream"),
        ]


def test_terminal_tool_result_persists_agent_turn_once():
    app = _make_sqlite_app()

    payload = {
        "user_id": 101,
        "syllabus_id": 202,
        "session_id": "sess-terminal-tool-db",
        "message": "hello terminal",
    }
    state = {
        "terminal_tool_result": {
            "success": True,
            "answer": {"text": "Terminal persisted answer"},
        },
        "total_context": {},
    }

    with app.app_context():
        agent_runtime._persist_user_chat_turn(payload)
        agent_runtime._persist_agent_chat_turn(payload, state)
        agent_runtime._persist_agent_chat_turn(payload, state)

        session = ChatSession.query.get("sess-terminal-tool-db")
        assert session is not None
        assert session.turn_count == 2

        turns = ChatTurn.query.filter_by(session_id="sess-terminal-tool-db").order_by(ChatTurn.id.asc()).all()
        assert [(turn.role, turn.content) for turn in turns] == [
            ("user", "hello terminal"),
            ("agent", "Terminal persisted answer"),
        ]


def test_real_tool_result_event_unwraps_terminal_content():
    event = FunctionToolResultEvent(
        result=ToolReturnPart(
            tool_name=agent_runtime.TOOL_ANSWER_LEARNING_QUESTION,
            tool_call_id="call-answer",
            content={"success": True, "answer": {"text": "Real event answer"}},
        )
    )

    tool_name, tool_call_id, tool_result = agent_runtime._safe_tool_result_event_data(event)

    assert tool_name == agent_runtime.TOOL_ANSWER_LEARNING_QUESTION
    assert tool_call_id == "call-answer"
    assert tool_result == {"success": True, "answer": {"text": "Real event answer"}}


def test_streamed_text_persistence_uses_agent_turn():
    app = _make_sqlite_app()
    payload = {
        "user_id": 101,
        "syllabus_id": 202,
        "session_id": "sess-streamed-text-db",
        "message": "hello streamed text",
    }

    with app.app_context():
        agent_runtime._persist_user_chat_turn(payload)
        agent_runtime.persist_streamed_agent_reply(payload, "hello from the same SSE stream")

        turns = ChatTurn.query.filter_by(session_id="sess-streamed-text-db").order_by(ChatTurn.id.asc()).all()
        assert [(turn.role, turn.content) for turn in turns] == [
            ("user", "hello streamed text"),
            ("agent", "hello from the same SSE stream"),
        ]


def test_streamed_text_persistence_stores_tool_metadata():
    app = _make_sqlite_app()
    payload = {
        "user_id": 101,
        "syllabus_id": 202,
        "session_id": "sess-streamed-tool-db",
        "message": "hello tools",
    }
    metadata = {
        "toolCalls": [
            {
                "tool_name": "load_total_context",
                "tool_call_id": "call-load",
                "args": {},
                "status": "succeeded",
                "result": {"success": True},
            }
        ],
        "subagentEvents": [],
        "segments": [
            {"kind": "text", "content": "before"},
            {"kind": "tools", "toolCallIds": ["call-load"], "subagentEventIds": []},
            {"kind": "text", "content": "after"},
        ],
        "finalResult": None,
    }

    with app.app_context():
        agent_runtime._persist_user_chat_turn(payload)
        agent_runtime.persist_streamed_agent_reply(payload, "beforeafter", metadata=metadata)

        turn = ChatTurn.query.filter_by(session_id="sess-streamed-tool-db", role="agent").one()
        assert turn.metadata_json
        saved = json.loads(turn.metadata_json)
        assert saved["toolCalls"][0]["tool_call_id"] == "call-load"
        assert saved["segments"][1]["kind"] == "tools"
