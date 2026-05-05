import json
from datetime import datetime
from types import SimpleNamespace

from tasks import syllabus_task as st


def test_update_syllabus_json_replaces_file_and_persists_day_one(monkeypatch, repo_json_factory):
    final_path = repo_json_factory(
        "schedule/syllabus",
        {
            "title": "old_syllabus",
            "day_one": "3-2",
            "graph_name": "graph_demo",
            "period": [{"week_index": "1", "content": "old_content", "importance": "medium"}],
        },
        prefix="final_update",
    )
    syllabus = SimpleNamespace(syllabus_id=13, syllabus_path=str(final_path))
    captured = {}
    payload = {
        "title": "new_syllabus",
        "day_one": "2026-03-02",
        "graph_name": "graph_demo",
        "period": [{"week_index": "3", "content": "new_content", "importance": "high"}],
    }

    monkeypatch.setattr(st, "get_syllabus_by_id", lambda syllabus_id: syllabus)
    monkeypatch.setattr(st, "set_syllabus_title", lambda syllabus_id, title: captured.setdefault("title", title))
    monkeypatch.setattr(st, "set_syllabus_day_one", lambda syllabus_id, value: captured.setdefault("day_one", value))
    monkeypatch.setattr(st, "list_user_syllabuses_by_syllabus", lambda syllabus_id: [])

    result = st.update_syllabus_json(13, payload)

    assert result is syllabus
    assert captured["title"] == "new_syllabus"
    assert isinstance(captured["day_one"], datetime)
    assert captured["day_one"].strftime("%Y-%m-%d") == "2026-03-02"
    assert json.loads(final_path.read_text(encoding="utf-8")) == payload
