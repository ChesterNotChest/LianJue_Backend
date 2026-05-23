import json
import os

import pytest

from tests.artifact_utils import write_test_artifact, write_text_artifact
from tasks import resource_generation_agent_task as rgat
from tasks import resource_planning_agent_task as rpat
from tasks.generative import storage as generative_storage


def _load_presentation(path_value):
    pptx = pytest.importorskip("pptx")
    return pptx.Presentation(str(path_value))


def _slide_texts(slide):
    return [shape.text for shape in slide.shapes if hasattr(shape, "text") and str(shape.text).strip()]


FIXED_PAYLOAD = {
    "user_id": 19,
    "syllabus_id": 23,
    "question": "我最近在学 HBase，RowKey 热点和预分区策略总是搞不懂，想要一些针对性的学习资源。",
    "topic": "HBase RowKey 热点规避",
    "resource_types": ["documents", "mindmap", "quiz"],
    "selected_weeks": [5],
    "knowledge_items": ["RowKey 热点", "预分区策略"],
    "weak_points": ["RowKey 热点", "预分区策略"],
    "learning_goal": "掌握 HBase RowKey 设计和热点规避",
    "retrieval_context": {
        "success": True,
        "query": "HBase RowKey 热点 预分区策略",
        "paragraphs": [
            "RowKey 设计需要避免热点并保持可区分性。",
            "预分区策略可以缓解写入集中问题。",
        ],
        "reasoning_paths": ["RowKey -> 热点 -> 预分区"],
    },
}


class FakeResourceGenerationAgent:
    def generate_resource_content(self, request_payload, resource_type, planning_bundle):
        topic = request_payload["topic"]
        if resource_type == "documents":
            return {
                "schema_version": "v1",
                "title": f"{topic} 文档",
                "topic": topic,
                "summary": "面向学生问题的讲解文档。",
                "sections": [
                    {"heading": "问题背景", "body": request_payload["question"]},
                    {"heading": "核心解释", "body": "RowKey 需要避免热点，预分区能缓解写入集中。"},
                ],
                "extension_reading": [],
            }
        if resource_type == "mindmap":
            return {
                "title": f"{topic} 导图",
                "root": topic,
                "nodes": [],
                "mermaid": "\n".join(
                    [
                        "mindmap",
                        f"  root(({topic}))",
                        "    RowKey 热点",
                        "    预分区策略",
                    ]
                ),
            }
        if resource_type == "quiz":
            return {
                "schema_version": "v1",
                "title": f"{topic} 习题",
                "topic": topic,
                "questions": [
                    {
                        "id": "q1",
                        "type": "single_choice",
                        "difficulty": "medium",
                        "stem": "为什么需要预分区策略？",
                        "options": ["缓解热点", "扩大端口", "删除索引", "关闭缓存"],
                        "answer": "A",
                        "explanation": "预分区可以缓解写入热点。",
                        "knowledge_points": ["预分区策略"],
                    }
                ],
            }
        if resource_type == "coding_practice":
            return {
                "schema_version": "v1",
                "title": f"{topic} 实操案例",
                "topic": topic,
                "language": "python",
                "summary": "通过最小代码案例理解 RowKey 设计思路。",
                "learning_objectives": ["理解热点问题", "理解预分区策略"],
                "steps": [
                    {"step_index": 1, "title": "阅读背景", "instruction": request_payload["question"]},
                    {"step_index": 2, "title": "运行案例", "instruction": "执行示例程序并观察输出。"},
                ],
                "code_files": [
                    {
                        "path": "code/main.py",
                        "purpose": "entry",
                        "content": (
                            "def explain_rowkey():\n"
                            "    return 'avoid hotspot with pre-splitting'\n\n"
                            "print(explain_rowkey())\n"
                        ),
                    }
                ],
                "run_guide": {
                    "entry_file": "code/main.py",
                    "command": "python code/main.py",
                    "expected_output": "avoid hotspot with pre-splitting",
                },
            }
        if resource_type == "ppt":
            return {
                "schema_version": "v1",
                "title": f"{topic} 课件",
                "topic": topic,
                "summary": "围绕学生问题的结构化课件。",
                "theme": "academic-clean",
                "slide_style": "teaching-outline",
                "slides": [
                    {
                        "slide_index": 1,
                        "title": "问题背景",
                        "bullets": [request_payload["question"], "定位热点产生原因"],
                        "speaker_notes": "先说明学生当前问题。",
                        "visual_hint": "标题 + 问题列表",
                    },
                    {
                        "slide_index": 2,
                        "title": "解决思路",
                        "bullets": ["优化 RowKey", "使用预分区策略"],
                        "speaker_notes": "解释两条关键解决思路。",
                        "visual_hint": "左右分栏对比",
                    },
                ],
            }
        raise ValueError(f"unsupported resource_type: {resource_type}")


class PartialFailGenerationAgent(FakeResourceGenerationAgent):
    def generate_resource_content(self, request_payload, resource_type, planning_bundle):
        if resource_type == "quiz":
            raise RuntimeError("quiz generation crashed")
        return super().generate_resource_content(request_payload, resource_type, planning_bundle)


class RetrievalAwareFakeResourceGenerationAgent(FakeResourceGenerationAgent):
    def generate_resource_content(self, request_payload, resource_type, planning_bundle):
        if resource_type != "documents":
            return super().generate_resource_content(request_payload, resource_type, planning_bundle)

        retrieval = planning_bundle.get("retrieval_context") if isinstance(planning_bundle, dict) else {}
        paragraphs = retrieval.get("paragraphs") if isinstance(retrieval, dict) else []
        evidence = [str(item).strip() for item in paragraphs[:2] if str(item).strip()]
        if not evidence:
            evidence = ["检索结果为空，无法构造 grounded 文档。"]

        return {
            "schema_version": "v1",
            "title": f"{request_payload['topic']} 文档",
            "topic": request_payload["topic"],
            "summary": "面向学生问题的检索增强讲解文档。",
            "sections": [
                {"heading": "学生问题", "body": request_payload["question"]},
                {"heading": "检索证据", "body": "\n".join(evidence)},
            ],
            "extension_reading": [],
        }


class SearchRecorder:
    def __init__(self, search_fn):
        self.search_fn = search_fn
        self.calls = []

    def __call__(self, *args, **kwargs):
        result = self.search_fn(*args, **kwargs)
        self.calls.append(
            {
                "args": args,
                "kwargs": kwargs,
                "result": result,
            }
        )
        return result


def _require_real_search_tool():
    if os.getenv("RUN_SEARCH_TESTS") != "1":
        pytest.skip("Set RUN_SEARCH_TESTS=1 to run real search-backed generation tests.")
    try:
        from tasks.search_tool import search_tool
    except ModuleNotFoundError as exc:
        pytest.skip(f"Real search dependency is unavailable: {exc}")

    return search_tool


def _require_real_llm_generation():
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run real LLM-backed generation tests.")


def _build_real_search_payload():
    payload = dict(FIXED_PAYLOAD)
    payload.pop("retrieval_context", None)
    payload["subject"] = "大数据概论"
    payload["graph_name"] = os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"
    payload["resource_types"] = ["documents"]
    return payload


def _build_real_search_ppt_payload():
    payload = _build_real_search_payload()
    payload["resource_types"] = ["ppt"]
    return payload


def test_ppt_generation_prefers_ppt_specific_model_key(monkeypatch):
    monkeypatch.setattr(
        rgat,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "ppt_text": {"model_name": "ppt-strong"},
            "text_cheap": {"model_name": "deepseek-chat"},
        },
    )
    agent = rgat.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "ppt",
        {"generation_requirements": {}},
    )

    assert selected == "ppt_text"


def test_default_generation_prefers_cheap_tier_model(monkeypatch):
    monkeypatch.setattr(
        rgat,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "text_cheap": {"model_name": "deepseek-chat"},
            "text_strong": {"model_name": "qwen-max"},
        },
    )
    agent = rgat.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "documents",
        {"generation_requirements": {}},
    )

    assert selected == "text_cheap"


def test_ppt_generation_honors_explicit_model_key(monkeypatch):
    monkeypatch.setattr(
        rgat,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "ppt_text": {"model_name": "ppt-strong"},
            "text_strong": {"model_name": "general-strong"},
        },
    )
    agent = rgat.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "ppt",
        {"generation_requirements": {"model_key": "text_strong"}},
    )

    assert selected == "text_strong"


def test_generation_honors_explicit_model_tier(monkeypatch):
    monkeypatch.setattr(
        rgat,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "text_cheap": {"model_name": "deepseek-chat"},
            "text_standard": {"model_name": "qwen-plus"},
            "text_strong": {"model_name": "qwen-max"},
        },
    )
    agent = rgat.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "documents",
        {"generation_requirements": {"model_tier": "strong"}},
    )

    assert selected == "text_strong"


def test_resource_planning_agent_runs_atomic_tools_in_order():
    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])

    result = planner.run(dict(FIXED_PAYLOAD), "documents")

    assert result["success"] is True
    assert result["resource_type"] == "documents"
    assert result["plan"]["resource_type"] == "documents"
    assert result["retrieval_context"]["paragraphs"]
    assert result["draft"]["outline"]
    assert result["tool_trace"] == [
        "read_generation_plan",
        "write_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
        "write_generation_draft",
    ]


def test_resource_generation_agent_full_chain_persists_all_requested_resources(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = rgat.run_resource_generation_agent(
        dict(FIXED_PAYLOAD),
        generation_agent=FakeResourceGenerationAgent(),
        planning_agent=planner,
    )

    assert result["success"] is True
    assert result["resource_count"] == 3
    assert result["success_count"] == 3
    assert result["failed_count"] == 0
    assert result["tool_trace"] == [
        "invoke_resource_planning_agent",
        "persist_generated_resource",
        "invoke_resource_planning_agent",
        "persist_generated_resource",
        "invoke_resource_planning_agent",
        "persist_generated_resource",
    ]
    assert [item["resource_type"] for item in result["resources"]] == ["documents", "mindmap", "quiz"]
    assert all(item["success"] is True for item in result["resources"])
    assert all(item["planning_trace"][-1] == "write_generation_draft" for item in result["resources"])

    manifest = json.loads((tmp_path / "generative" / "user_19" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == 3
    assert [entry["resource_type"] for entry in manifest["resources"]] == ["documents", "mindmap", "quiz"]
    for entry in manifest["resources"]:
        for path_value in entry["main_files"].values():
            assert (tmp_path / path_value).exists()


def test_resource_generation_agent_keeps_partial_success_when_one_resource_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = rgat.run_resource_generation_agent(
        dict(FIXED_PAYLOAD),
        generation_agent=PartialFailGenerationAgent(),
        planning_agent=planner,
    )

    assert result["success"] is False
    assert result["success_count"] == 2
    assert result["failed_count"] == 1
    assert result["error_code"] == "partial_failure"
    assert result["resources"][0]["success"] is True
    assert result["resources"][1]["success"] is True
    assert result["resources"][2]["success"] is False
    assert result["resources"][2]["resource_type"] == "quiz"
    assert "quiz generation crashed" in result["resources"][2]["error_message"]


def test_resource_generation_agent_full_chain_persists_coding_practice(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    payload = dict(FIXED_PAYLOAD)
    payload["resource_types"] = ["coding_practice"]

    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = rgat.run_resource_generation_agent(
        payload,
        generation_agent=FakeResourceGenerationAgent(),
        planning_agent=planner,
    )

    assert result["success"] is True
    assert result["resource_count"] == 1
    resource = result["resources"][0]
    assert resource["resource_type"] == "coding_practice"
    assert resource["success"] is True
    assert resource["status"] == "ready"
    assert resource["planning_trace"][-1] == "write_generation_draft"

    practice_json = json.loads((tmp_path / resource["json_path"]).read_text(encoding="utf-8"))
    practice_md = (tmp_path / resource["md_path"]).read_text(encoding="utf-8")
    entry_file_path = tmp_path / resource["entry_file_path"]

    assert practice_json["language"] == "python"
    assert practice_json["steps"]
    assert practice_json["code_files"]
    assert "Practice Steps" in practice_md
    assert entry_file_path.exists()
    assert "avoid hotspot with pre-splitting" in entry_file_path.read_text(encoding="utf-8")


def test_resource_generation_agent_full_chain_persists_ppt(monkeypatch, tmp_path):
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    payload = dict(FIXED_PAYLOAD)
    payload["resource_types"] = ["ppt"]

    planner = rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = rgat.run_resource_generation_agent(
        payload,
        generation_agent=FakeResourceGenerationAgent(),
        planning_agent=planner,
    )

    assert result["success"] is True
    assert result["resource_count"] == 1
    resource = result["resources"][0]
    assert resource["resource_type"] == "ppt"
    assert resource["success"] is True
    assert resource["status"] == "ready"
    assert resource["planning_trace"][-1] == "write_generation_draft"

    ppt_json = json.loads((tmp_path / resource["json_path"]).read_text(encoding="utf-8"))
    ppt_md = (tmp_path / resource["md_path"]).read_text(encoding="utf-8")
    pptx_path = tmp_path / resource["pptx_path"]
    presentation = _load_presentation(pptx_path)

    assert ppt_json["theme"] == "academic-clean"
    assert ppt_json["slide_style"] == "teaching-outline"
    assert len(ppt_json["slides"]) == 2
    assert pptx_path.exists()
    assert len(presentation.slides) == 2
    assert "解决思路" in _slide_texts(presentation.slides[1])
    assert "Slide 1" in ppt_md
    assert "问题背景" in ppt_md


@pytest.mark.search
def test_resource_generation_agent_full_chain_with_real_search_persists_grounded_document(monkeypatch, tmp_path):
    search_tool = _require_real_search_tool()
    payload = _build_real_search_payload()

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    search_recorder = SearchRecorder(search_tool)
    planner = rpat.ResourcePlanningAgent(search_fn=search_recorder)
    result = rgat.run_resource_generation_agent(
        payload,
        generation_agent=RetrievalAwareFakeResourceGenerationAgent(),
        planning_agent=planner,
    )

    if not search_recorder.calls:
        pytest.skip("Real search tool was not called.")

    retrieval = search_recorder.calls[0]["result"]
    if not isinstance(retrieval, dict) or not retrieval.get("success") or not retrieval.get("paragraphs"):
        error = retrieval.get("error") if isinstance(retrieval, dict) else ""
        pytest.skip(f"Real search returned no usable paragraphs for graph {payload['graph_name']}: {error}")

    assert result["success"] is True
    assert result["resource_count"] == 1
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert len(search_recorder.calls) == 1
    assert "HBase" in (retrieval.get("query") or "")
    assert result["tool_trace"] == [
        "invoke_resource_planning_agent",
        "persist_generated_resource",
    ]

    resource = result["resources"][0]
    assert resource["resource_type"] == "documents"
    assert resource["success"] is True
    assert resource["status"] == "ready"
    assert resource["planning_trace"] == [
        "read_generation_plan",
        "write_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
        "write_generation_draft",
    ]

    document_json = json.loads((tmp_path / resource["json_path"]).read_text(encoding="utf-8"))
    document_md = (tmp_path / resource["md_path"]).read_text(encoding="utf-8")

    assert document_json["sections"]
    assert "## 检索证据" in document_md
    assert any(paragraph in document_md for paragraph in retrieval["paragraphs"][:2])

    artifact_json_path = write_test_artifact(
        "real_search_generation_result.json",
        {
            "request": payload,
            "retrieval_context": retrieval,
            "result": result,
            "resource_json": document_json,
        },
    )
    artifact_md_path = write_text_artifact(
        "real_search_generated_document.md",
        document_md,
    )
    assert artifact_json_path.exists()
    assert artifact_md_path.exists()


@pytest.mark.llm
@pytest.mark.search
def test_resource_generation_agent_full_chain_with_real_search_and_real_llm(monkeypatch, tmp_path):
    search_tool = _require_real_search_tool()
    _require_real_llm_generation()
    payload = _build_real_search_payload()

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    search_recorder = SearchRecorder(search_tool)
    planner = rpat.ResourcePlanningAgent(search_fn=search_recorder)
    result = rgat.run_resource_generation_agent(
        payload,
        generation_agent=rgat.LLMResourceGenerationAgent(),
        planning_agent=planner,
    )

    if not search_recorder.calls:
        pytest.skip("Real search tool was not called.")

    retrieval = search_recorder.calls[0]["result"]
    if not isinstance(retrieval, dict) or not retrieval.get("success") or not retrieval.get("paragraphs"):
        error = retrieval.get("error") if isinstance(retrieval, dict) else ""
        pytest.skip(f"Real search returned no usable paragraphs for graph {payload['graph_name']}: {error}")

    assert result["success"] is True
    assert result["resource_count"] == 1
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert len(search_recorder.calls) == 1
    assert "HBase" in (retrieval.get("query") or "")
    assert result["tool_trace"] == [
        "invoke_resource_planning_agent",
        "persist_generated_resource",
    ]

    resource = result["resources"][0]
    assert resource["resource_type"] == "documents"
    assert resource["success"] is True
    assert resource["status"] == "ready"
    assert resource["planning_trace"] == [
        "read_generation_plan",
        "write_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
        "write_generation_draft",
    ]

    document_json = json.loads((tmp_path / resource["json_path"]).read_text(encoding="utf-8"))
    document_md = (tmp_path / resource["md_path"]).read_text(encoding="utf-8")

    assert document_json["sections"]
    assert isinstance(document_json.get("summary"), str) and document_json["summary"].strip()
    assert any(keyword in document_md for keyword in ["HBase", "RowKey", "热点", "预分区"])

    artifact_json_path = write_test_artifact(
        "real_search_real_llm_generation_result.json",
        {
            "request": payload,
            "retrieval_context": retrieval,
            "result": result,
            "resource_json": document_json,
        },
    )
    artifact_md_path = write_text_artifact(
        "real_search_real_llm_generated_document.md",
        document_md,
    )
    assert artifact_json_path.exists()
    assert artifact_md_path.exists()


@pytest.mark.llm
@pytest.mark.search
def test_resource_generation_agent_full_chain_with_real_search_and_real_llm_ppt(monkeypatch, tmp_path):
    search_tool = _require_real_search_tool()
    _require_real_llm_generation()
    payload = _build_real_search_ppt_payload()

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    search_recorder = SearchRecorder(search_tool)
    planner = rpat.ResourcePlanningAgent(search_fn=search_recorder)
    result = rgat.run_resource_generation_agent(
        payload,
        generation_agent=rgat.LLMResourceGenerationAgent(),
        planning_agent=planner,
    )

    if not search_recorder.calls:
        pytest.skip("Real search tool was not called.")

    retrieval = search_recorder.calls[0]["result"]
    if not isinstance(retrieval, dict) or not retrieval.get("success") or not retrieval.get("paragraphs"):
        error = retrieval.get("error") if isinstance(retrieval, dict) else ""
        pytest.skip(f"Real search returned no usable paragraphs for graph {payload['graph_name']}: {error}")

    assert result["success"] is True
    assert result["resource_count"] == 1
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert len(search_recorder.calls) == 1
    assert "HBase" in (retrieval.get("query") or "")
    assert result["tool_trace"] == [
        "invoke_resource_planning_agent",
        "persist_generated_resource",
    ]

    resource = result["resources"][0]
    assert resource["resource_type"] == "ppt"
    assert resource["success"] is True
    assert resource["status"] == "ready"
    assert resource["planning_trace"] == [
        "read_generation_plan",
        "write_generation_plan",
        "retrieve_generation_materials",
        "read_generation_draft",
        "write_generation_draft",
    ]

    ppt_json = json.loads((tmp_path / resource["json_path"]).read_text(encoding="utf-8"))
    ppt_md = (tmp_path / resource["md_path"]).read_text(encoding="utf-8")
    pptx_path = tmp_path / resource["pptx_path"]
    presentation = _load_presentation(pptx_path)

    assert isinstance(ppt_json.get("slides"), list) and ppt_json["slides"]
    assert isinstance(ppt_json.get("summary"), str) and ppt_json["summary"].strip()
    assert pptx_path.exists()
    assert len(presentation.slides) == len(ppt_json["slides"])
    assert any(keyword in ppt_md for keyword in ["Slide 1", "HBase", "RowKey", "热点", "预分区"])

    artifact_json_path = write_test_artifact(
        "real_search_real_llm_ppt_generation_result.json",
        {
            "request": payload,
            "retrieval_context": retrieval,
            "result": result,
            "resource_json": ppt_json,
        },
    )
    artifact_md_path = write_text_artifact(
        "real_search_real_llm_generated_ppt.md",
        ppt_md,
    )
    assert artifact_json_path.exists()
    assert artifact_md_path.exists()
