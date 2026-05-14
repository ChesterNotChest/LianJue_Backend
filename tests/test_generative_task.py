import json

import pytest

from tasks import generative_task as gt


class FakeMindmapAgent:
    def generate_mindmap(self, payload):
        return {
            "title": f"{payload['topic']} 思维导图",
            "root": payload["topic"],
            "nodes": [
                {
                    "label": "HDFS",
                    "children": [
                        {"label": "NameNode"},
                        {"label": "DataNode"},
                    ],
                }
            ],
            "mermaid": "\n".join(
                [
                    "mindmap",
                    "  root((分布式存储))",
                    "    HDFS",
                    "      NameNode",
                    "      DataNode",
                ]
            ),
        }


class InvalidMindmapAgent:
    def generate_mindmap(self, payload):
        return {
            "title": payload["topic"],
            "mermaid": "not_a_mermaid_diagram\njust text",
        }


class FakeQuizAgent:
    def generate_quiz(self, payload):
        return {
            "schema_version": gt.GENERATIVE_QUIZ_SCHEMA_VERSION,
            "title": f"{payload['topic']} 单题练习",
            "topic": payload["topic"],
            "questions": [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "difficulty": "medium",
                    "stem": "哪一项最符合 RowKey 设计原则？",
                    "options": ["尽量递增", "避免热点并保证可区分", "越长越好", "全部使用时间戳原文"],
                    "answer": "B",
                    "explanation": "RowKey 设计需要兼顾散列性和可区分性，避免热点。",
                    "knowledge_points": ["RowKey设计"],
                }
            ],
        }


class InvalidQuizAgent:
    def generate_quiz(self, payload):
        return {
            "schema_version": gt.GENERATIVE_QUIZ_SCHEMA_VERSION,
            "title": payload["topic"],
            "questions": [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "stem": "缺少 options 的选择题",
                    "answer": "A",
                    "explanation": "故意构造非法结构",
                }
            ],
        }


class FakeDocumentAgent:
    def generate_document(self, payload):
        return {
            "schema_version": gt.GENERATIVE_DOCUMENT_SCHEMA_VERSION,
            "title": f"{payload['topic']} 讲解文档",
            "topic": payload["topic"],
            "summary": "面向课程学习的知识点说明。",
            "sections": [
                {"heading": "概念", "body": "RowKey 是 HBase 中用于唯一定位行的数据。"},
                {"heading": "设计原则", "body": "应避免热点并保持可区分性。"},
            ],
            "extension_reading": [
                {"title": "HBase Schema Design", "reason": "扩展理解 RowKey 与表设计关系"}
            ],
        }


class InvalidDocumentAgent:
    def generate_document(self, payload):
        return {
            "schema_version": gt.GENERATIVE_DOCUMENT_SCHEMA_VERSION,
            "title": payload["topic"],
            "summary": "",
            "sections": [
                {"heading": "", "body": "故意构造非法结构"}
            ],
        }


def test_ensure_generative_workspace_creates_expected_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    workspace = gt.ensure_generative_workspace(7)

    assert workspace["user_root"] == "generative/user_7"
    assert (tmp_path / "generative" / "user_7" / "documents").exists()
    assert (tmp_path / "generative" / "user_7" / "mindmap").exists()
    manifest = json.loads((tmp_path / workspace["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["version"] == gt.GENERATIVE_MANIFEST_VERSION
    assert manifest["user_id"] == 7
    assert manifest["resource_count"] == 0
    assert isinstance(manifest["updated_at"], int)
    assert manifest["resources"] == []


def test_validate_mermaid_text_accepts_fenced_mermaid_block():
    validation = gt.validate_mermaid_text(
        """```mermaid
mindmap
  root((RowKey))
    设计原则
```"""
    )

    assert validation["valid"] is True
    assert validation["diagram_type"] == "mindmap"
    assert validation["node_count"] >= 2
    assert validation["cleaned_text"].startswith("mindmap")


def test_generate_mindmap_persists_bundle_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_mindmap(
        {
            "user_id": 3,
            "syllabus_id": 12,
            "topic": "分布式存储",
            "knowledge_items": ["HDFS", "HBase"],
        },
        FakeMindmapAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "ready"

    resource_dir = tmp_path / result["resource_dir"]
    assert resource_dir.exists()

    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    assert saved_json["title"] == "分布式存储 思维导图"
    assert saved_json["knowledge_items"] == ["HDFS", "HBase"]
    assert saved_json["mermaid"].startswith("mindmap")

    saved_mermaid = (tmp_path / result["mermaid_path"]).read_text(encoding="utf-8")
    assert saved_mermaid.startswith("mindmap")

    manifest = json.loads((tmp_path / "generative" / "user_3" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == gt.GENERATIVE_MANIFEST_VERSION
    assert manifest["resource_count"] == 1
    assert isinstance(manifest["updated_at"], int)
    assert len(manifest["resources"]) == 1
    entry = manifest["resources"][0]
    assert entry["resource_id"] == result["resource_id"]
    assert entry["status"] == "ready"
    assert isinstance(entry["created_at"], int)
    assert isinstance(entry["updated_at"], int)
    assert entry["main_files"]["json_path"] == result["json_path"]
    assert entry["main_files"]["mermaid_path"] == result["mermaid_path"]
    assert "resource_path" not in entry["main_files"]
    assert not (resource_dir / "resource.json").exists()


def test_generate_resource_dispatches_to_mindmap(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_resource(
        {
            "user_id": 5,
            "syllabus_id": 2,
            "resource_type": "mindmap",
            "topic": "MapReduce",
            "knowledge_items": ["Mapper", "Reducer"],
        },
        FakeMindmapAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "mindmap"
    assert result["status"] == "ready"


def test_generate_structured_document_persists_bundle_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_structured_document(
        {
            "user_id": 11,
            "syllabus_id": 18,
            "topic": "HBase RowKey",
        },
        FakeDocumentAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "documents"
    assert result["status"] == "ready"

    resource_dir = tmp_path / result["resource_dir"]
    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    saved_md = (tmp_path / result["md_path"]).read_text(encoding="utf-8")

    assert resource_dir.exists()
    assert saved_json["schema_version"] == gt.GENERATIVE_DOCUMENT_SCHEMA_VERSION
    assert len(saved_json["sections"]) == 2
    assert saved_md.startswith("# HBase RowKey 讲解文档")
    assert "## 概念" in saved_md
    assert "## Extension Reading" in saved_md

    manifest = json.loads((tmp_path / "generative" / "user_11" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "documents"
    assert entry["main_files"]["json_path"] == result["json_path"]
    assert entry["main_files"]["md_path"] == result["md_path"]
    assert entry["validation"]["section_count"] == 2
    assert entry["metadata"]["extension_reading_count"] == 1


def test_generate_structured_document_marks_invalid_when_schema_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_structured_document(
        {
            "user_id": 12,
            "topic": "非法文档",
        },
        InvalidDocumentAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "invalid"
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"]

    manifest = json.loads((tmp_path / "generative" / "user_12" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "documents"
    assert entry["status"] == "invalid"
    assert any("summary" in error or "heading" in error for error in entry["validation"]["errors"])


def test_generate_quiz_persists_bundle_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_quiz(
        {
            "user_id": 6,
            "syllabus_id": 18,
            "topic": "HBase RowKey",
        },
        FakeQuizAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "quiz"
    assert result["status"] == "ready"

    resource_dir = tmp_path / result["resource_dir"]
    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    saved_md = (tmp_path / result["md_path"]).read_text(encoding="utf-8")

    assert resource_dir.exists()
    assert saved_json["schema_version"] == gt.GENERATIVE_QUIZ_SCHEMA_VERSION
    assert saved_json["questions"][0]["type"] == "single_choice"
    assert saved_md.startswith("# HBase RowKey 单题练习")
    assert "Answer: B" in saved_md

    manifest = json.loads((tmp_path / "generative" / "user_6" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "quiz"
    assert entry["main_files"]["json_path"] == result["json_path"]
    assert entry["main_files"]["md_path"] == result["md_path"]
    assert entry["validation"]["question_count"] == 1
    assert entry["metadata"]["question_types"] == ["single_choice"]


def test_generate_quiz_marks_invalid_when_schema_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_quiz(
        {
            "user_id": 10,
            "topic": "非法题",
        },
        InvalidQuizAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "invalid"
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"]

    manifest = json.loads((tmp_path / "generative" / "user_10" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "quiz"
    assert entry["status"] == "invalid"
    assert any("options" in error for error in entry["validation"]["errors"])


def test_generate_resource_dispatches_to_quiz(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_resource(
        {
            "user_id": 8,
            "resource_type": "quiz",
            "topic": "Spark Shuffle",
        },
        FakeQuizAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "quiz"
    assert result["status"] == "ready"


def test_generate_resource_dispatches_to_documents(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_resource(
        {
            "user_id": 13,
            "resource_type": "documents",
            "topic": "Spark Shuffle",
        },
        FakeDocumentAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "documents"
    assert result["status"] == "ready"


def test_generate_mindmap_marks_invalid_when_mermaid_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_mindmap(
        {
            "user_id": 9,
            "topic": "错误图",
        },
        InvalidMindmapAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "invalid"
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"]

    manifest = json.loads((tmp_path / "generative" / "user_9" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    assert len(manifest["resources"]) == 1
    entry = manifest["resources"][0]
    assert entry["status"] == "invalid"
    assert entry["validation"]["errors"]
    assert "resource_path" not in entry["main_files"]
    assert not (tmp_path / result["resource_dir"] / "resource.json").exists()


def test_generate_mindmap_requires_topic(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    with pytest.raises(ValueError, match="topic is required"):
        gt.generate_mindmap(
            {
                "user_id": 1,
                "topic": "",
            },
            FakeMindmapAgent(),
        )


def test_generate_resource_rejects_unimplemented_type(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)

    with pytest.raises(ValueError, match="is not implemented yet"):
        gt.generate_resource(
            {
                "user_id": 1,
                "resource_type": "coding_practice",
                "topic": "HDFS",
            },
            FakeMindmapAgent(),
        )


def test_validate_quiz_payload_rejects_missing_options():
    validation = gt.validate_quiz_payload(
        {
            "schema_version": gt.GENERATIVE_QUIZ_SCHEMA_VERSION,
            "title": "bad quiz",
            "questions": [
                {
                    "type": "single_choice",
                    "stem": "invalid",
                    "answer": "A",
                    "explanation": "invalid",
                }
            ],
        }
    )

    assert validation["valid"] is False
    assert any("options" in error for error in validation["errors"])


def test_validate_document_payload_rejects_missing_summary():
    validation = gt.validate_document_payload(
        {
            "schema_version": gt.GENERATIVE_DOCUMENT_SCHEMA_VERSION,
            "title": "bad document",
            "summary": "",
            "sections": [
                {
                    "heading": "概念",
                    "body": "内容",
                }
            ],
        }
    )

    assert validation["valid"] is False
    assert any("summary" in error for error in validation["errors"])


def test_load_manifest_backfills_version_and_resource_count(monkeypatch, tmp_path):
    monkeypatch.setattr(gt, "_get_backend_root", lambda: tmp_path)
    user_root = tmp_path / "generative" / "user_4"
    user_root.mkdir(parents=True, exist_ok=True)
    legacy_manifest_path = user_root / "manifest.json"
    legacy_manifest_path.write_text(
        json.dumps(
            {
                "user_id": 4,
                "resources": [
                    {"resource_id": "legacy-1", "resource_type": "mindmap"},
                    {"resource_id": "legacy-2", "resource_type": "mindmap"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manifest = gt.load_manifest(4)

    assert manifest["version"] == gt.GENERATIVE_MANIFEST_VERSION
    assert manifest["resource_count"] == 2
    assert isinstance(manifest["updated_at"], int)
