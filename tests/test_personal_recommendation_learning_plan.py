import json
import shutil
from pathlib import Path

from tasks import personal_recommendation_task as prt


TEST_RECOMMENDATION_ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts" / "personal_recommendation"


def _reset_artifact_root(name: str) -> Path:
    root = TEST_RECOMMENDATION_ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _recommendation_result():
    return {
        "graph": {
            "nodes": [
                {"id": "n1", "title": "Intro", "outcomes": ["a"]},
                {"id": "n2", "title": "Next", "outcomes": ["b"]},
            ],
            "edges": [{"edge_id": "n1->n2", "source": "n1", "target": "n2"}],
        },
        "candidates": [
            {"path": ["n1", "n2"], "skills": ["a", "b"], "path_edges": []},
        ],
        "best_path": {"path": ["n1"], "skills": ["a"], "path_edges": []},
    }


def test_accept_recommendation_path_creates_active_plan(monkeypatch):
    artifact_root = _reset_artifact_root("learning_plan_manifest_create")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    result = prt.accept_recommendation_path(8, 20, _recommendation_result(), candidate_index=0)

    assert result["success"] is True
    assert result["status"] == prt.LEARNING_PLAN_STATUS_ACTIVE
    active = prt.get_active_learning_plan(8, 20)
    assert active["plan_id"] == result["plan_id"]
    assert [step["node_id"] for step in active["steps"]] == ["n1", "n2"]


def test_accept_recommendation_path_supersedes_old_active_plan(monkeypatch):
    artifact_root = _reset_artifact_root("learning_plan_manifest_supersede")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    first = prt.accept_recommendation_path(8, 20, _recommendation_result(), candidate_index=0)
    second = prt.accept_recommendation_path(8, 20, _recommendation_result(), candidate_index=0)

    assert second["superseded_plan_id"] == first["plan_id"]
    assert prt.get_active_learning_plan(8, 20)["plan_id"] == second["plan_id"]


def test_learning_plan_manifest_is_append_only_jsonl(monkeypatch):
    artifact_root = _reset_artifact_root("learning_plan_manifest_append_only")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    prt.accept_recommendation_path(8, 20, _recommendation_result(), candidate_index=0)
    active = prt.get_active_learning_plan(8, 20)
    prt.update_learning_plan_step_status(
        8,
        active["plan_id"],
        active["steps"][0]["step_id"],
        prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
        syllabus_id=20,
        sync_study_graph=False,
    )

    manifest_path = artifact_root / "learning_plan" / "user_8" / "syllabus_20" / "manifest.jsonl"
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert all(isinstance(json.loads(line), dict) for line in lines)


def test_learning_plan_step_stores_node_reference_only(monkeypatch):
    artifact_root = _reset_artifact_root("learning_plan_manifest_node_reference")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    result = prt.accept_recommendation_path(8, 20, _recommendation_result(), candidate_index=0)
    step = result["steps"][0]

    assert step["node_id"] == "n1"
    assert "edges" not in step
    assert "graph" not in step
