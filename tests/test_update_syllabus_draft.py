import json
from types import SimpleNamespace

from tasks import syllabus_task as st


def test_update_syllabus_draft_json_replaces_file_and_updates_title(monkeypatch, repo_json_factory):
    draft_path = repo_json_factory(
        "schedule/syllabus_draft",
        {
            "title": "old_title",
            "graph_name": "graph_demo",
            "period": [{"week_index": "1", "content": "old_content", "importance": "low"}],
        },
        prefix="draft_update",
    )
    syllabus = SimpleNamespace(syllabus_id=11, syllabus_draft_path=str(draft_path))
    persisted = {}
    payload = {
        "title": "new_title",
        "graph_name": "graph_demo",
        "period": [{"week_index": "2", "content": "new_content", "importance": "high"}],
    }

    monkeypatch.setattr(st, "get_syllabus_by_id", lambda syllabus_id: syllabus)
    monkeypatch.setattr(st, "set_syllabus_title", lambda syllabus_id, title: persisted.setdefault("title", title))

    result = st.update_syllabus_draft_json(11, payload)

    assert result is syllabus
    assert persisted["title"] == "new_title"
    assert json.loads(draft_path.read_text(encoding="utf-8")) == payload
