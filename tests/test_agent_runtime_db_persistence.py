import pytest
from flask import Flask

from extensions import db
from schemas.agent_runtime_state import (
    GeneratedResource,
    LearningPlan,
    LearningPlanEvent,
    LearningPlanStep,
    StudyGraphChangeLog,
    StudyGraphNode,
    StudyGraphTree,
)
from tasks import generative_task as gt
from tasks import personal_recommendation_task as prt
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
