import json
import os

import pytest

from tasks import generative_task as gt
from tasks.generative import storage as generative_storage


def _load_presentation(path_value):
    pptx = pytest.importorskip("pptx")
    return pptx.Presentation(str(path_value))


def _slide_texts(slide):
    return [shape.text for shape in slide.shapes if hasattr(shape, "text") and str(shape.text).strip()]


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
                {
                    "heading": "核心概念",
                    "body": "RowKey 是 HBase 中用于唯一定位行的数据，也是 Region 划分和访问路由的重要依据。",
                    "key_points": ["RowKey 决定数据排序", "RowKey 影响 Region 分布"],
                    "pitfalls": ["不要只按时间戳单调递增设计 RowKey"],
                },
                {
                    "heading": "设计原则",
                    "body": "应避免热点并保持可区分性，同时兼顾查询模式、键长度和业务可读性。",
                    "examples": ["设备ID散列前缀 + 时间戳可以缓解单点写入集中"],
                    "checklist": ["能解释热点成因", "能说出至少一种打散策略", "能判断预分区是否适用"],
                },
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


class FakeCodingPracticeAgent:
    def generate_coding_practice(self, payload):
        return {
            "schema_version": gt.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
            "title": f"{payload['topic']} 实操案例",
            "topic": payload["topic"],
            "language": "python",
            "summary": "通过一个可运行示例理解函数定义、参数传递和返回值。",
            "learning_objectives": [
                "理解函数定义",
                "理解参数传递",
            ],
            "steps": [
                {"step_index": 1, "title": "阅读案例目标", "instruction": "先理解程序要完成的功能。"},
                {"step_index": 2, "title": "运行示例程序", "instruction": "执行 main.py，观察输出。"},
            ],
            "code_files": [
                {
                    "path": "code/main.py",
                    "purpose": "entry",
                    "content": (
                        "def greet(name):\n"
                        "    # 返回问候语\n"
                        "    return f'Hello, {name}'\n\n"
                        "print(greet('Alice'))\n"
                    ),
                }
            ],
            "run_guide": {
                "entry_file": "code/main.py",
                "command": "python code/main.py",
                "expected_output": "Hello, Alice",
            },
        }


class InvalidCodingPracticeAgent:
    def generate_coding_practice(self, payload):
        return {
            "schema_version": gt.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
            "title": payload["topic"],
            "topic": payload["topic"],
            "language": "python",
            "summary": "非法结构",
            "learning_objectives": [],
            "steps": [
                {"step_index": 1, "title": "坏步骤", "instruction": ""}
            ],
            "code_files": [
                {
                    "path": "code/main.py",
                    "purpose": "entry",
                    "content": "def broken(:\n    pass\n",
                }
            ],
            "run_guide": {
                "entry_file": "code/main.py",
                "command": "python code/main.py",
            },
        }


class FakePptAgent:
    def generate_ppt(self, payload):
        return {
            "schema_version": gt.GENERATIVE_PPT_SCHEMA_VERSION,
            "title": f"{payload['topic']} 复习课件",
            "topic": payload["topic"],
            "summary": "用于学生自学和复习的结构化课件大纲。",
            "theme": "academic-clean",
            "slide_style": "study-review",
            "slides": [
                {
                    "slide_index": 1,
                    "title": "课程目标",
                    "body": "学生先明确本资源要解决的问题，再把目标拆成概念理解和步骤掌握。",
                    "bullets": ["理解核心概念", "掌握关键步骤", "识别常见易错点"],
                    "speaker_notes": "",
                    "visual_hint": "标题区 + 主题区 + 学习目标区",
                },
                {
                    "slide_index": 2,
                    "title": "关键知识点",
                    "body": "本页给出关键知识点的核心判断，再用要点拆开概念、场景和注意事项。",
                    "bullets": ["概念定义要能复述", "应用场景要对应真实问题", "注意事项聚焦易错边界"],
                    "speaker_notes": "注意区分概念定义和使用条件。",
                    "visual_hint": "标题区 + 导语区 + 要点区",
                },
            ],
        }


class RichLayoutPptAgent:
    def generate_ppt(self, payload):
        return {
            "schema_version": gt.GENERATIVE_PPT_SCHEMA_VERSION,
            "title": f"{payload['topic']} 进阶课件",
            "topic": payload["topic"],
            "summary": "即使输入提示包含复杂版式，也应按简单站位元素渲染。",
            "theme": "academic-clean",
            "slide_style": "study-review",
            "slides": [
                {
                    "slide_index": 1,
                    "title": "课程导入",
                    "body": "复习时先统一目标和场景，确认后续流程页和策略页分别解决什么问题。",
                    "bullets": ["统一目标", "明确场景"],
                    "speaker_notes": "",
                    "visual_hint": "标题区 + 主题区 + 学习目标区",
                },
                {
                    "slide_index": 2,
                    "title": "实施步骤",
                    "body": "本页把热点识别、RowKey 设计和效果验证拆成连续步骤，学生可以按顺序检查自己是否掌握。",
                    "bullets": [
                        "第1步：识别热点；定位高频前缀",
                        "第2步：设计 RowKey；加入散列或盐值",
                        "第3步：验证效果；观察 Region 分布",
                    ],
                    "speaker_notes": "注意不要把步骤顺序和适用条件混在一起。",
                    "visual_hint": "流程图",
                },
                {
                    "slide_index": 3,
                    "title": "策略对照",
                    "body": "本页把不同策略放在同一张表中比较，帮助学生复习时区分成因、适用条件和设计取舍。",
                    "bullets": [
                        "热点成因：单调递增前缀导致写入集中",
                        "预分区策略：提前拆分 Region，降低单点压力",
                        "盐值方案：打散写入键空间，均衡落点",
                    ],
                    "speaker_notes": "注意区分策略适用条件，不要只比较名称。",
                    "visual_hint": "表格对照",
                },
            ],
        }


class InvalidPptAgent:
    def generate_ppt(self, payload):
        return {
            "schema_version": gt.GENERATIVE_PPT_SCHEMA_VERSION,
            "title": payload["topic"],
            "topic": payload["topic"],
            "summary": "",
            "slides": [
                {
                    "slide_index": 1,
                    "title": "",
                    "bullets": [],
                }
            ],
        }


def test_ensure_generative_workspace_creates_expected_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    workspace = gt.ensure_generative_workspace(7)

    assert workspace["user_root"] == "generative/user_7"
    assert (tmp_path / "generative" / "user_7" / "documents").exists()
    assert (tmp_path / "generative" / "user_7" / "mindmap").exists()
    assert (tmp_path / "generative" / "user_7" / "ppt").exists()
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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    assert "## 核心概念" in saved_md
    assert "### Key Points" in saved_md
    assert "### Common Pitfalls" in saved_md
    assert "### Examples" in saved_md
    assert "### Self Check" in saved_md
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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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


def test_generate_coding_practice_persists_bundle_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_coding_practice(
        {
            "user_id": 14,
            "syllabus_id": 18,
            "topic": "Python 函数封装与参数传递",
            "language": "python",
        },
        FakeCodingPracticeAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "coding_practice"
    assert result["status"] == "ready"

    resource_dir = tmp_path / result["resource_dir"]
    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    saved_md = (tmp_path / result["md_path"]).read_text(encoding="utf-8")
    saved_code = (tmp_path / result["entry_file_path"]).read_text(encoding="utf-8")

    assert resource_dir.exists()
    assert saved_json["schema_version"] == gt.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION
    assert saved_json["language"] == "python"
    assert saved_json["run_guide"]["entry_file"] == "code/main.py"
    assert saved_md.startswith("# Python 函数封装与参数传递 实操案例")
    assert "## Learning Objectives" in saved_md
    assert "## Practice Steps" in saved_md
    assert "Command: `python code/main.py`" in saved_md
    assert "def greet(name):" in saved_md
    assert "def greet(name):" in saved_code

    manifest = json.loads((tmp_path / "generative" / "user_14" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "coding_practice"
    assert entry["main_files"]["json_path"] == result["json_path"]
    assert entry["main_files"]["md_path"] == result["md_path"]
    assert entry["main_files"]["entry_file_path"] == result["entry_file_path"]
    assert entry["validation"]["language"] == "python"
    assert entry["validation"]["step_count"] == 2
    assert entry["metadata"]["file_count"] == 1
    assert entry["metadata"]["entry_file"] == "code/main.py"


def test_generate_coding_practice_marks_invalid_when_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_coding_practice(
        {
            "user_id": 15,
            "topic": "非法代码案例",
            "language": "python",
        },
        InvalidCodingPracticeAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "invalid"
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"]

    manifest = json.loads((tmp_path / "generative" / "user_15" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "coding_practice"
    assert entry["status"] == "invalid"
    assert any("instruction" in error or "syntax error" in error for error in entry["validation"]["errors"])


def test_generate_coding_practice_normalizes_llm_schema_drift(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    class DriftedCodingPracticeAgent:
        def generate_coding_practice(self, payload):
            return {
                "schema_version": gt.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
                "title": payload["topic"],
                "topic": payload["topic"],
                "language": "Java",
                "summary": "LLM returned a Java-style practice with loose fields.",
                "learning_objectives": ["理解 RowKey hash salt"],
                "steps": ["Read the example", "Run the Java program"],
                "code_files": [
                    {
                        "name": "Main",
                        "code": (
                            "public class Main {\n"
                            "  public static void main(String[] args) {\n"
                            "    System.out.println(\"RowKey\");\n"
                            "  }\n"
                            "}\n"
                        ),
                    }
                ],
                "run_guide": {},
            }

    result = gt.generate_coding_practice(
        {"user_id": 151, "topic": "RowKey hotspot mitigation", "language": "java"},
        DriftedCodingPracticeAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "ready"
    assert result["validation"]["valid"] is True

    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    assert saved_json["language"] == "java"
    assert saved_json["steps"][0]["instruction"] == "Read the example"
    assert saved_json["code_files"][0]["path"] == "code/Main.java"
    assert result["entry_file_path"].endswith("code/Main.java")


def test_generate_coding_practice_repoints_missing_entry_file(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    class MismatchedEntryFileAgent:
        def generate_coding_practice(self, payload):
            return {
                "schema_version": gt.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
                "title": payload["topic"],
                "topic": payload["topic"],
                "language": "python",
                "summary": "LLM returned an entry file that does not match code_files.",
                "learning_objectives": ["Check generated entry file"],
                "steps": [{"title": "Run", "instruction": "Run the generated example."}],
                "code_files": [
                    {
                        "path": "code/rowkey_demo.py",
                        "purpose": "entry",
                        "content": "print('RowKey')\n",
                    }
                ],
                "run_guide": {"entry_file": "code/main.py", "command": "python code/main.py"},
            }

    result = gt.generate_coding_practice(
        {"user_id": 152, "topic": "RowKey entry file mismatch", "language": "python"},
        MismatchedEntryFileAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "ready"
    assert result["entry_file_path"].endswith("code/rowkey_demo.py")
    assert (tmp_path / result["entry_file_path"]).exists()

    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    assert saved_json["run_guide"]["entry_file"] == "code/rowkey_demo.py"


def test_generate_resource_dispatches_to_coding_practice(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_resource(
        {
            "user_id": 16,
            "resource_type": "coding_practice",
            "topic": "Python 函数封装与参数传递",
            "language": "python",
        },
        FakeCodingPracticeAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "coding_practice"
    assert result["status"] == "ready"


def test_generate_ppt_persists_bundle_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_ppt(
        {
            "user_id": 17,
            "syllabus_id": 18,
            "topic": "MapReduce 基础",
        },
        FakePptAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "ppt"
    assert result["status"] == "ready"

    resource_dir = tmp_path / result["resource_dir"]
    saved_json = json.loads((tmp_path / result["json_path"]).read_text(encoding="utf-8"))
    saved_md = (tmp_path / result["md_path"]).read_text(encoding="utf-8")
    saved_pptx = tmp_path / result["pptx_path"]
    presentation = _load_presentation(saved_pptx)

    assert resource_dir.exists()
    assert saved_json["schema_version"] == gt.GENERATIVE_PPT_SCHEMA_VERSION
    assert saved_json["theme"] == "academic-clean"
    assert len(saved_json["slides"]) == 2
    assert saved_pptx.exists()
    assert len(presentation.slides) == 2
    assert "课程目标" in _slide_texts(presentation.slides[0])
    assert saved_md.startswith("# MapReduce 基础 复习课件")
    assert "## Slide 1: 课程目标" in saved_md
    assert "Speaker Notes:" in saved_md
    assert "Visual Hint: 标题区 + 主题区 + 学习目标区" in saved_md

    manifest = json.loads((tmp_path / "generative" / "user_17" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "ppt"
    assert entry["main_files"]["json_path"] == result["json_path"]
    assert entry["main_files"]["md_path"] == result["md_path"]
    assert entry["main_files"]["pptx_path"] == result["pptx_path"]
    assert entry["validation"]["slide_count"] == 2
    assert entry["metadata"]["theme"] == "academic-clean"
    assert entry["metadata"]["slide_style"] == "study-review"


def test_generate_ppt_keeps_complex_hints_in_simple_placeholders(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_ppt(
        {
            "user_id": 27,
            "syllabus_id": 18,
            "topic": "HBase RowKey 热点规避",
        },
        RichLayoutPptAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "ready"
    presentation = _load_presentation(tmp_path / result["pptx_path"])

    assert len(presentation.slides) == 3
    assert "课程导入" in _slide_texts(presentation.slides[0])
    assert "实施步骤" in _slide_texts(presentation.slides[1])
    assert "热点识别" in "\n".join(_slide_texts(presentation.slides[1]))
    assert "策略对照" in _slide_texts(presentation.slides[2])


def test_generate_ppt_marks_invalid_when_schema_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_ppt(
        {
            "user_id": 18,
            "topic": "非法课件",
        },
        InvalidPptAgent(),
    )

    assert result["success"] is True
    assert result["status"] == "invalid"
    assert result["validation"]["valid"] is False
    assert result["validation"]["errors"]

    manifest = json.loads((tmp_path / "generative" / "user_18" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 1
    entry = manifest["resources"][0]
    assert entry["resource_type"] == "ppt"
    assert entry["status"] == "invalid"
    assert any("summary" in error or "bullets" in error for error in entry["validation"]["errors"])


def test_generate_resource_dispatches_to_ppt(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    result = gt.generate_resource(
        {
            "user_id": 19,
            "resource_type": "ppt",
            "topic": "Spark Shuffle",
        },
        FakePptAgent(),
    )

    assert result["success"] is True
    assert result["resource_type"] == "ppt"
    assert result["status"] == "ready"


def test_generate_mindmap_marks_invalid_when_mermaid_validation_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

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
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    with pytest.raises(ValueError, match="topic is required"):
        gt.generate_mindmap(
            {
                "user_id": 1,
                "topic": "",
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


def test_validate_coding_practice_payload_rejects_unsafe_path_and_empty_steps():
    validation = gt.validate_coding_practice_payload(
        {
            "schema_version": gt.GENERATIVE_CODING_PRACTICE_SCHEMA_VERSION,
            "title": "bad coding practice",
            "topic": "Python basics",
            "language": "python",
            "summary": "bad",
            "steps": [],
            "code_files": [
                {
                    "path": "../escape.py",
                    "content": "print('bad')\n",
                }
            ],
            "run_guide": {
                "entry_file": "../escape.py",
                "command": "python ../escape.py",
            },
        }
    )

    assert validation["valid"] is False
    assert any("steps" in error for error in validation["errors"])
    assert any("safe relative path" in error for error in validation["errors"])


def test_validate_ppt_payload_rejects_empty_slides():
    validation = gt.validate_ppt_payload(
        {
            "schema_version": gt.GENERATIVE_PPT_SCHEMA_VERSION,
            "title": "bad ppt",
            "topic": "Spark",
            "summary": "bad",
            "slides": [
                {
                    "title": "",
                    "bullets": [],
                }
            ],
        }
    )

    assert validation["valid"] is False
    assert any("missing title" in error or "bullets" in error for error in validation["errors"])


def test_load_manifest_backfills_version_and_resource_count(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)
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


def test_generate_resource_full_user_chain_persists_all_resource_types(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    user_id = 21
    syllabus_id = 31
    resources = [
        gt.generate_resource(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "resource_type": "documents",
                "topic": "HBase RowKey",
            },
            FakeDocumentAgent(),
        ),
        gt.generate_resource(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "resource_type": "mindmap",
                "topic": "HBase RowKey",
                "knowledge_items": ["hotspot", "pre-split"],
            },
            FakeMindmapAgent(),
        ),
        gt.generate_resource(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "resource_type": "quiz",
                "topic": "HBase RowKey",
            },
            FakeQuizAgent(),
        ),
        gt.generate_resource(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "resource_type": "coding_practice",
                "topic": "HBase RowKey",
                "language": "python",
            },
            FakeCodingPracticeAgent(),
        ),
        gt.generate_resource(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "resource_type": "ppt",
                "topic": "HBase RowKey",
            },
            FakePptAgent(),
        ),
    ]

    manifest = gt.load_manifest(user_id)

    assert [item["resource_type"] for item in resources] == ["documents", "mindmap", "quiz", "coding_practice", "ppt"]
    assert all(item["success"] is True for item in resources)
    assert all(item["status"] == "ready" for item in resources)
    assert manifest["resource_count"] == 5
    assert [entry["resource_type"] for entry in manifest["resources"]] == ["documents", "mindmap", "quiz", "coding_practice", "ppt"]
    assert [entry["syllabus_id"] for entry in manifest["resources"]] == [syllabus_id, syllabus_id, syllabus_id, syllabus_id, syllabus_id]
    assert len({entry["resource_id"] for entry in manifest["resources"]}) == 5

    for entry in manifest["resources"]:
        assert (tmp_path / entry["resource_dir"]).exists()
        assert entry["validation"]["valid"] is True
        for path_value in entry["main_files"].values():
            assert (tmp_path / path_value).exists()


def _extract_json_object(raw_text):
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class RealLLMGenerativeAgent:
    def __init__(self, model):
        self.model = model

    def _call_json(self, task_name, payload, required_keys):
        system_prompt = (
            "You are a course resource generation adapter. "
            "Return only one valid JSON object. Do not use markdown fences."
        )
        user_prompt = json.dumps(
            {
                "task": task_name,
                "topic": payload.get("topic"),
                "required_keys": required_keys,
                "constraints": [
                    "Use concise educational content.",
                    "For Mermaid mindmap, start the mermaid field with 'mindmap'.",
                    "For quiz, include exactly one single_choice question with at least 4 options.",
                ],
            },
            ensure_ascii=False,
        )
        raw = self.model.call_text_model(system_prompt, user_prompt, stream=False)
        return _extract_json_object(raw)

    def generate_mindmap(self, payload):
        generated = self._call_json(
            "generate_mindmap",
            payload,
            ["title", "root", "nodes", "mermaid"],
        )
        mermaid = str(generated.get("mermaid") or "").strip()
        if not mermaid.startswith("mindmap"):
            mermaid = "\n".join(["mindmap", f"  root(({payload['topic']}))", "    core idea"])
        generated["mermaid"] = mermaid
        generated.setdefault("title", f"{payload['topic']} mindmap")
        generated.setdefault("root", payload["topic"])
        generated.setdefault("nodes", [])
        return generated

    def generate_document(self, payload):
        generated = self._call_json(
            "generate_document",
            payload,
            ["schema_version", "title", "topic", "summary", "sections", "extension_reading"],
        )
        generated["schema_version"] = gt.GENERATIVE_DOCUMENT_SCHEMA_VERSION
        generated.setdefault("title", f"{payload['topic']} document")
        generated.setdefault("topic", payload["topic"])
        generated.setdefault("summary", f"Short explanation for {payload['topic']}.")
        normalized_sections = []
        sections = generated.get("sections")
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                heading = section.get("heading") or section.get("section_title") or section.get("title")
                body = section.get("body") or section.get("content") or section.get("text")
                normalized_sections.append(
                    {
                        "heading": str(heading or "Overview").strip() or "Overview",
                        "body": str(body or f"Core ideas of {payload['topic']}.").strip(),
                    }
                )
        if not normalized_sections:
            normalized_sections = [{"heading": "Overview", "body": f"Core ideas of {payload['topic']}."}]
        generated["sections"] = normalized_sections

        normalized_extension_reading = []
        extension_reading = generated.get("extension_reading")
        if isinstance(extension_reading, list):
            for item in extension_reading:
                if isinstance(item, dict):
                    normalized_extension_reading.append(
                        {
                            "title": str(item.get("title") or item.get("name") or "Extension reading").strip(),
                            "reason": str(item.get("reason") or item.get("description") or "Extend the topic.").strip(),
                        }
                    )
                elif str(item or "").strip():
                    normalized_extension_reading.append(
                        {
                            "title": str(item).strip(),
                            "reason": "Extend the topic.",
                        }
                    )
        generated["extension_reading"] = normalized_extension_reading
        return generated

    def generate_quiz(self, payload):
        generated = self._call_json(
            "generate_quiz",
            payload,
            ["schema_version", "title", "topic", "questions"],
        )
        generated["schema_version"] = gt.GENERATIVE_QUIZ_SCHEMA_VERSION
        generated.setdefault("title", f"{payload['topic']} quiz")
        generated.setdefault("topic", payload["topic"])
        if not isinstance(generated.get("questions"), list) or not generated["questions"]:
            generated["questions"] = [
                {
                    "type": "single_choice",
                    "stem": f"Which option best describes {payload['topic']}?",
                    "options": ["A core concept", "An unrelated idea", "A file format", "A network port"],
                    "answer": "A",
                    "explanation": "The topic is being tested as a core learning concept.",
                }
            ]
        normalized_questions = []
        for index, question in enumerate(generated["questions"], start=1):
            if not isinstance(question, dict):
                question = {}
            question["type"] = "single_choice"
            question["stem"] = str(
                question.get("stem")
                or question.get("question")
                or f"Which option best describes {payload['topic']}?"
            )
            options = question.get("options")
            if not isinstance(options, list) or len(options) < 4:
                options = ["A core concept", "An unrelated idea", "A file format", "A network port"]
            question["options"] = options
            answer = question.get("answer")
            if answer in (None, ""):
                answer = "A"
            question["answer"] = str(answer)
            question["explanation"] = str(
                question.get("explanation")
                or "The selected answer follows from the generated learning content."
            )
            question.setdefault("id", f"q{index}")
            normalized_questions.append(question)
        generated["questions"] = normalized_questions
        return generated


class RAGBackedLLMGenerativeAgent(RealLLMGenerativeAgent):
    def __init__(self, model, search_tool):
        super().__init__(model)
        self.search_tool = search_tool
        self.search_queries = []

    def _build_search_query(self, payload):
        query_parts = [
            payload.get("subject"),
            payload.get("topic"),
            payload.get("learning_goal"),
            " ".join(map(str, payload.get("weak_points") or [])),
        ]
        return " ".join(str(item).strip() for item in query_parts if str(item or "").strip())

    def _ensure_retrieval_context(self, payload):
        if isinstance(payload.get("retrieval_context"), dict) and payload["retrieval_context"].get("paragraphs"):
            return payload["retrieval_context"]
        query = self._build_search_query(payload)
        self.search_queries.append(query)
        retrieval = self.search_tool(query, graph_name=payload.get("graph_name"), top_k=3)
        payload["retrieval_context"] = retrieval
        return retrieval

    def _call_json(self, task_name, payload, required_keys):
        system_prompt = (
            "You are a personalized course resource generation adapter. "
            "Use the provided retrieval_context as grounding evidence. "
            "Return only one valid JSON object. Do not use markdown fences."
        )
        retrieval_context = self._ensure_retrieval_context(payload)
        user_prompt = json.dumps(
            {
                "task": task_name,
                "subject": payload.get("subject"),
                "topic": payload.get("topic"),
                "weak_points": payload.get("weak_points") or [],
                "learning_goal": payload.get("learning_goal"),
                "required_keys": required_keys,
                "retrieval_context": {
                    "query": retrieval_context.get("query"),
                    "paragraphs": retrieval_context.get("paragraphs") or [],
                    "reasoning_paths": retrieval_context.get("reasoning_paths") or [],
                },
                "constraints": [
                    "Generate content for the subject 大数据概论.",
                    "Make the resource personalized to the weak_points.",
                    "Use retrieved facts when possible.",
                    "For quiz, include exactly one single_choice question with at least 4 options.",
                ],
            },
            ensure_ascii=False,
        )
        raw = self.model.call_text_model(system_prompt, user_prompt, stream=False)
        return _extract_json_object(raw)


@pytest.mark.llm
@pytest.mark.search
def test_real_rag_generative_agent_creates_personalized_resource(monkeypatch, tmp_path):
    if os.getenv("RUN_LLM_TESTS") != "1" or os.getenv("RUN_SEARCH_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 and RUN_SEARCH_TESTS=1 to run the real RAG generative chain.")

    from tasks.common.search_tool import search_tool
    from utils.llm_utils import get_model_instance

    graph_name = os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"
    subject = "大数据概论"

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)
    agent = RAGBackedLLMGenerativeAgent(get_model_instance(), search_tool)
    base_payload = {
        "user_id": 61,
        "syllabus_id": 71,
        "subject": subject,
        "topic": "HBase RowKey 热点规避",
        "graph_name": graph_name,
        "learning_goal": "掌握大数据概论中的 HBase RowKey 设计与热点规避",
        "weak_points": ["RowKey 热点", "预分区策略"],
    }
    payloads = [
        {**base_payload, "resource_type": "documents"},
        {**base_payload, "resource_type": "mindmap", "knowledge_items": ["RowKey 热点", "预分区策略"]},
        {**base_payload, "resource_type": "quiz"},
    ]

    results = []
    for payload in payloads:
        result = gt.generate_resource(payload, agent)
        retrieval = payload.get("retrieval_context")
        if not isinstance(retrieval, dict) or not retrieval["success"] or not retrieval["paragraphs"]:
            error = retrieval.get("error") if isinstance(retrieval, dict) else ""
            pytest.skip(f"Real search returned no usable paragraphs for graph {graph_name}: {error}")
        results.append((payload, result))

    manifest = gt.load_manifest(base_payload["user_id"])
    success_results = [
        (payload, result)
        for payload, result in results
        if result.get("success") is True
        and result.get("status") == "ready"
        and (result.get("validation") or {}).get("valid") is True
    ]
    failed_results = [
        {
            "resource_type": payload.get("resource_type"),
            "status": result.get("status"),
            "validation": result.get("validation"),
            "title": result.get("title"),
        }
        for payload, result in results
        if (payload, result) not in success_results
    ]

    assert [result["resource_type"] for _, result in results] == ["documents", "mindmap", "quiz"]
    assert failed_results == []
    assert [result["resource_type"] for _, result in success_results] == ["documents", "mindmap", "quiz"]
    assert len(agent.search_queries) == len(payloads)
    assert all("RowKey" in query for query in agent.search_queries)
    assert manifest["resource_count"] == 3
    assert [entry["resource_type"] for entry in manifest["resources"]] == ["documents", "mindmap", "quiz"]
    assert [entry["syllabus_id"] for entry in manifest["resources"]] == [base_payload["syllabus_id"]] * 3

    documents_result = results[0][1]
    documents_json = json.loads((tmp_path / documents_result["json_path"]).read_text(encoding="utf-8"))
    documents_md = (tmp_path / documents_result["md_path"]).read_text(encoding="utf-8")
    assert documents_json["schema_version"] == gt.GENERATIVE_DOCUMENT_SCHEMA_VERSION
    assert documents_json["sections"]
    assert any(point in documents_md for point in ["RowKey", "热点", "预分区", "HBase"])

    mindmap_result = results[1][1]
    mindmap_json = json.loads((tmp_path / mindmap_result["json_path"]).read_text(encoding="utf-8"))
    mindmap_mermaid = (tmp_path / mindmap_result["mermaid_path"]).read_text(encoding="utf-8")
    assert mindmap_json["mermaid"].startswith("mindmap")
    assert mindmap_mermaid.startswith("mindmap")
    assert mindmap_json["knowledge_items"] == ["RowKey 热点", "预分区策略"]

    quiz_result = results[2][1]
    quiz_json = json.loads((tmp_path / quiz_result["json_path"]).read_text(encoding="utf-8"))
    quiz_md = (tmp_path / quiz_result["md_path"]).read_text(encoding="utf-8")
    assert quiz_json["schema_version"] == gt.GENERATIVE_QUIZ_SCHEMA_VERSION
    assert quiz_json["questions"]
    assert any(point in quiz_md for point in ["RowKey", "热点", "预分区", "HBase"])

    for _, result in results:
        assert (tmp_path / result["json_path"]).exists()
        if result["resource_type"] in ("documents", "quiz"):
            assert (tmp_path / result["md_path"]).exists()
        if result["resource_type"] == "mindmap":
            assert (tmp_path / result["mermaid_path"]).exists()
