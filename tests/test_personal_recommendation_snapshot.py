import json

from tasks import personal_recommendation_task as prt


def _recommendation_result() -> dict:
    return {
        "success": True,
        "graph": {
            "nodes": [
                {"id": "n1", "title": "Intro", "outcomes": ["a"]},
                {"id": "n2", "title": "Default Next", "outcomes": ["b"]},
                {"id": "n3", "title": "Alternative Next", "outcomes": ["c"]},
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                {"source": "n1", "target": "n3"},
            ],
        },
        "candidates": [
            {"path": ["n1", "n2"], "skills": ["a", "b"], "rank": 1},
            {"path": ["n1", "n3"], "skills": ["a", "c"], "rank": 2},
        ],
        "selected": [{"path": ["n1", "n2"], "skills": ["a", "b"]}],
        "best_path": {"path": ["n1", "n2"], "skills": ["a", "b"]},
        "rag_overlay": {"used": True},
        "planning_hints": {"path_depth": 2},
    }


def test_save_recommendation_snapshot_file_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))

    saved = prt.save_recommendation_snapshot(
        8,
        20,
        _recommendation_result(),
        request_payload={"goals": ["learn hbase"], "message": "recommend", "session_id": "sess-1"},
    )

    assert saved["success"] is True
    assert saved["status"] == prt.RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED
    snapshot_file = (
        tmp_path
        / "personal_recommendation"
        / "recommendation_snapshot"
        / "user_8"
        / "syllabus_20"
        / f"{saved['recommendation_id']}.json"
    )
    assert snapshot_file.exists()
    payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert payload["recommendation"]["graph"]["nodes"][0]["id"] == "n1"
    assert payload["summary"]["candidate_count"] == 2


def test_get_recommendation_snapshot_returns_full_recommendation(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    saved = prt.save_recommendation_snapshot(8, 20, _recommendation_result())

    result = prt.get_recommendation_snapshot(saved["recommendation_id"])

    assert result["success"] is True
    snapshot = result["snapshot"]
    assert snapshot["recommendation"]["graph"]["edges"]
    assert snapshot["recommendation"]["candidates"][1]["path"] == ["n1", "n3"]
    assert snapshot["summary"]["best_path_titles"] == ["Intro", "Default Next"]


def test_list_recommendation_snapshots_returns_summary_only(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    prt.save_recommendation_snapshot(8, 20, _recommendation_result())

    result = prt.list_recommendation_snapshots(8, 20)

    assert result["success"] is True
    assert len(result["snapshots"]) == 1
    item = result["snapshots"][0]
    assert item["candidate_count"] == 2
    assert item["best_path"] == ["n1", "n2"]
    assert "recommendation" not in item
    assert "graph" not in item


def test_save_recommendation_snapshot_rejects_missing_graph(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))

    result = prt.save_recommendation_snapshot(8, 20, {"success": True, "graph": {}})

    assert result["success"] is False
    assert result["error_code"] == "missing_graph"


def test_accept_recommendation_snapshot_path_accepts_non_default_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    saved = prt.save_recommendation_snapshot(8, 20, _recommendation_result())

    accepted = prt.accept_recommendation_snapshot_path(8, 20, saved["recommendation_id"], candidate_index=1)
    active_plan = prt.get_active_learning_plan(8, 20)
    snapshot = prt.get_recommendation_snapshot(saved["recommendation_id"])["snapshot"]

    assert accepted["success"] is True
    assert accepted["snapshot_status"] == prt.RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED
    assert accepted["accepted_candidate_index"] == 1
    assert active_plan["path"] == ["n1", "n3"]
    assert [step["node_id"] for step in active_plan["steps"]] == ["n1", "n3"]
    assert snapshot["status"] == prt.RECOMMENDATION_SNAPSHOT_STATUS_ACCEPTED
    assert snapshot["accepted_plan_id"] == accepted["plan_id"]


def test_accept_recommendation_snapshot_path_rejects_wrong_user(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    saved = prt.save_recommendation_snapshot(8, 20, _recommendation_result())

    result = prt.accept_recommendation_snapshot_path(9, 20, saved["recommendation_id"], candidate_index=0)

    assert result["success"] is False
    assert result["error_code"] == "wrong_owner"


def test_accept_recommendation_snapshot_path_rejects_invalid_candidate_index(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    saved = prt.save_recommendation_snapshot(8, 20, _recommendation_result())

    result = prt.accept_recommendation_snapshot_path(8, 20, saved["recommendation_id"], candidate_index=99)

    assert result["success"] is False
    assert result["error_code"] == prt.RECOMMENDATION_SNAPSHOT_ERROR_INVALID_CANDIDATE
