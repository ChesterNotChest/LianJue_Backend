import json
from types import SimpleNamespace

from tasks import syllabus_task as st


def test_build_syllabus_draft_creates_json_and_binds_graph(monkeypatch, tmp_path):
    syllabus = SimpleNamespace(
        syllabus_id=7,
        file_id=101,
        edu_calendar_path="schedule/calendar/sample.pdf",
    )
    markdown_path = tmp_path / "build_syllabus_draft_source.md"
    markdown_path.write_text("# title\nweek1 content", encoding="utf-8")

    created = {}
    bound = []

    monkeypatch.setattr(st, "get_syllabus_by_id", lambda syllabus_id: syllabus)
    monkeypatch.setattr(st, "create_job", lambda file_id, end_stage, graph_id: SimpleNamespace(job_id=88))
    monkeypatch.setattr(st, "_get_latest_job_status", lambda job_id: "completed")
    monkeypatch.setattr(st, "_get_latest_job", lambda job_id: SimpleNamespace(markdown_path=str(markdown_path)))
    monkeypatch.setattr(st, "get_graphId_by_job_id", lambda job_id: "graph_demo")
    monkeypatch.setattr(
        st,
        "get_model_instance",
        lambda: SimpleNamespace(
            call_text_model=lambda system_prompt, user_prompt: json.dumps(
                {
                    "period": [
                        {
                            "week_index": "1",
                            "content": "course intro",
                            "importance": "high",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        ),
    )
    monkeypatch.setattr(st, "set_syllabus_draft_path", lambda syllabus_id, path: created.setdefault("path", path))
    monkeypatch.setattr(st, "create_syllabus_graph", lambda syllabus_id, graph_id: bound.append((syllabus_id, graph_id)))

    result = st.build_syllabus_draft(syllabus_id=7, graph_id=3, initial_prompt="Generate a syllabus draft.")

    assert result is syllabus
    assert bound == [(7, 3)]
    assert created["path"]

    saved = json.loads(st._resolve_repo_path(created["path"]).read_text(encoding="utf-8"))
    assert saved["title"] == "sample.pdf"
    assert saved["graph_name"] == "graph_demo"
    assert saved["period"][0]["week_index"] == "1"
