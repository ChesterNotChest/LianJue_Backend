import json
from types import SimpleNamespace

from tasks import syllabus_task as st


class FakeKnowLion:
    def __init__(self, model_configs, graph_name):
        self.graph_name = graph_name

    def search(self, text, top_k=10, classify_list=None):
        return {
            "reasoning_paths": [f"{self.graph_name}: reasoning"],
            "paragraphs": [f"{text}: paragraph"],
        }


def test_build_syllabus_enriches_period_and_persists_final_json(monkeypatch, repo_json_factory):
    draft_payload = {
        "title": "ml_intro",
        "graph_name": "graph_demo",
        "period": [
            {"week_index": "1", "content": "supervised learning basics", "importance": "high"},
            {"week_index": "2", "content": "unsupervised learning basics", "importance": "medium"},
        ],
    }
    draft_path = repo_json_factory("schedule/syllabus_draft", draft_payload, prefix="draft")
    syllabus = SimpleNamespace(
        syllabus_id=9,
        syllabus_draft_path=str(draft_path),
        syllabus_path=None,
        day_one_time=None,
    )
    persisted = {}

    monkeypatch.setattr(st, "get_syllabus_by_id", lambda syllabus_id: syllabus)
    monkeypatch.setattr(st, "_get_primary_graph_info", lambda syllabus_id: (1, "graph_demo"))
    monkeypatch.setattr(
        st,
        "get_model_instance",
        lambda: SimpleNamespace(call_text_model=lambda system_prompt, user_prompt: "enhanced syllabus content"),
    )
    monkeypatch.setattr(st, "set_syllabus_path", lambda syllabus_id, path: persisted.setdefault("path", path))
    monkeypatch.setattr(st, "set_syllabus_title", lambda syllabus_id, title: persisted.setdefault("title", title))
    monkeypatch.setattr("knowlion.abution_knowlion_driver.KnowLion", FakeKnowLion)
    monkeypatch.setattr(st.time, "sleep", lambda seconds: None)

    result = st.build_syllabus(syllabus_id=9)

    assert result is syllabus
    assert persisted["title"] == "ml_intro"
    assert persisted["path"]

    saved = json.loads(st._resolve_repo_path(persisted["path"]).read_text(encoding="utf-8"))
    assert saved["title"] == "ml_intro"
    assert saved["graph_name"] == "graph_demo"
    assert saved["period"][0]["enhanced_content"] == "enhanced syllabus content"
    assert saved["period"][1]["enhanced_content"] == "enhanced syllabus content"
