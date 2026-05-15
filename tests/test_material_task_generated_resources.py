import json

from tasks import material_task


def test_list_generated_resources_filters_and_sorts(monkeypatch):
    manifest = {
        "resources": [
            {
                "resource_id": "quiz-old",
                "resource_type": "quiz",
                "syllabus_id": 9,
                "created_at": 10,
                "main_files": {"json_path": "old.json"},
            },
            {
                "resource_id": "document-new",
                "resource_type": "documents",
                "syllabus_id": 9,
                "created_at": 30,
                "main_files": {"json_path": "doc.json"},
            },
            {
                "resource_id": "quiz-other",
                "resource_type": "quiz",
                "syllabus_id": 10,
                "created_at": 20,
                "main_files": {"json_path": "other.json"},
            },
        ]
    }
    monkeypatch.setattr(material_task.generative_task, "load_manifest", lambda user_id: manifest)

    resources = material_task.list_generated_resources(user_id=5, syllabus_id=9)

    assert [item["resource_id"] for item in resources] == ["document-new", "quiz-old"]


def test_list_generated_resources_by_type_applies_limit(monkeypatch):
    manifest = {
        "resources": [
            {"resource_id": "quiz-2", "resource_type": "quiz", "syllabus_id": 9, "created_at": 20},
            {"resource_id": "quiz-1", "resource_type": "quiz", "syllabus_id": 9, "created_at": 10},
            {"resource_id": "mindmap-1", "resource_type": "mindmap", "syllabus_id": 9, "created_at": 30},
        ]
    }
    monkeypatch.setattr(material_task.generative_task, "load_manifest", lambda user_id: manifest)

    grouped = material_task.list_generated_resources_by_type(
        user_id=5,
        syllabus_id=9,
        limit_per_type=1,
    )

    assert [item["resource_id"] for item in grouped["mindmap"]] == ["mindmap-1"]
    assert [item["resource_id"] for item in grouped["quiz"]] == ["quiz-2"]


def test_get_generated_resource_detail_returns_render_ready_wrapper(monkeypatch, tmp_path):
    resource_dir = tmp_path / "generative" / "user_5" / "quiz" / "quiz-1"
    resource_dir.mkdir(parents=True)
    json_path = resource_dir / "quiz.json"
    md_path = resource_dir / "quiz.md"
    json_path.write_text(json.dumps({"title": "RowKey 小测"}, ensure_ascii=False), encoding="utf-8")
    md_path.write_text("# RowKey 小测\n", encoding="utf-8")

    manifest = {
        "resources": [
            {
                "resource_id": "quiz-1",
                "resource_type": "quiz",
                "title": "RowKey 小测",
                "topic": "HBase RowKey",
                "syllabus_id": 9,
                "status": "ready",
                "resource_dir": "generative/user_5/quiz/quiz-1",
                "main_files": {
                    "json_path": str(json_path),
                    "md_path": str(md_path),
                },
                "created_at": 100,
                "updated_at": 101,
            }
        ]
    }
    monkeypatch.setattr(material_task.generative_task, "load_manifest", lambda user_id: manifest)

    detail = material_task.get_generated_resource_detail(5, "quiz-1")

    assert detail["resource_id"] == "quiz-1"
    assert detail["resource_type"] == "quiz"
    assert detail["content"] == {"title": "RowKey 小测"}
    assert detail["render"]["markdown"] == "# RowKey 小测\n"
