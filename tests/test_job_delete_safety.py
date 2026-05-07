from blueprint import knowledge_build_api as api
from tasks import jobs_task


def test_parse_bool_does_not_treat_false_string_as_true():
    assert api._parse_bool("false") is False
    assert api._parse_bool("0") is False
    assert api._parse_bool("true") is True


def test_parse_job_id_rejects_invalid_values():
    assert api._parse_job_id("12") == 12
    assert api._parse_job_id("abc") is None
    assert api._parse_job_id("-1") is None


def test_safe_remove_path_skips_paths_outside_artifact_roots(tmp_path):
    victim = tmp_path / "outside.txt"
    victim.write_text("keep", encoding="utf-8")

    jobs_task._safe_remove_path(str(victim))

    assert victim.exists()


def test_job_delete_rejects_invalid_job_id(monkeypatch):
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.register_blueprint(api.bp)
    client = flask_app.test_client()

    response = client.post("/api/job_delete", json={"job_id": "abc"})

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "missing_fields"


def test_job_delete_false_string_force_does_not_delete_non_failed_job(monkeypatch):
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.register_blueprint(api.bp)
    client = flask_app.test_client()

    monkeypatch.setattr(api.jobs_task, "get_job_status", lambda job_id: "completed")
    monkeypatch.setattr(api.jobs_task, "purge_job_record", lambda job_id: (_ for _ in ()).throw(AssertionError("should not purge")))

    response = client.post("/api/job_delete", json={"job_id": "1", "force": "false"})

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_state"
