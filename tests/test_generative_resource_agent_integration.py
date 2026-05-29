import json
import os
import shutil
import subprocess

import pytest

from tests.artifact_utils import prepare_artifact_backend, write_test_artifact, write_text_artifact
from tasks import generative_task as gt
from tasks.generative import storage as generative_storage


def _load_presentation(path_value):
    pptx = pytest.importorskip("pptx")
    return pptx.Presentation(str(path_value))


def _slide_texts(slide):
    return [shape.text for shape in slide.shapes if hasattr(shape, "text") and str(shape.text).strip()]


def _try_render_mermaid_svg(mermaid_path, svg_path):
    """Render Mermaid when the local CLI exists; otherwise return a skipped result."""
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return {"checked": False, "reason": "mmdc not installed"}
    process = subprocess.run(
        [mmdc, "-i", str(mermaid_path), "-o", str(svg_path), "-b", "transparent"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return {
        "checked": True,
        "success": process.returncode == 0,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


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
                "title": f"{topic} 复习课件",
                "topic": topic,
                "summary": "围绕学生问题的结构化课件。",
                "theme": "academic-clean",
                "slide_style": "study-review",
                "slides": [
                    {
                        "slide_index": 1,
                        "title": "问题背景",
                        "body": "学生先定位热点产生原因，再理解 RowKey 设计和预分区的关系。",
                        "bullets": [request_payload["question"], "定位热点产生原因", "明确预分区的复习目标"],
                        "speaker_notes": "",
                        "visual_hint": "标题区 + 主题区 + 学习目标区",
                        "slide_role": "cover",
                    },
                    {
                        "slide_index": 2,
                        "title": "解决思路",
                        "body": "复习时先调整 RowKey 分布，再用预分区降低集中写入压力。",
                        "bullets": ["优化 RowKey", "使用预分区策略", "观察 Region 负载是否均衡"],
                        "speaker_notes": "注意不要把散列打散和预分区边界混为一个动作。",
                        "visual_hint": "标题区 + 导语区 + 要点区",
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
        from tasks.common.search_tool import search_tool
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


def _build_real_search_all_resource_payload():
    payload = _build_real_search_payload()
    payload["resource_types"] = ["documents", "mindmap", "quiz", "coding_practice", "ppt"]
    payload["generation_requirements"] = {
        "model_tier": os.getenv("GENERATIVE_TEST_MODEL_TIER") or "cheap",
        "ppt_model_tier": os.getenv("GENERATIVE_TEST_PPT_MODEL_TIER") or "standard",
        "slide_count_target": int(os.getenv("GENERATIVE_TEST_PPT_SLIDE_COUNT") or 8),
        "theme": "academic-rich",
        "style": "study-review",
    }
    return payload


def _assert_real_ppt_resource(tmp_path, resource, expected_min_slides=6):
    ppt_json = json.loads((tmp_path / resource["json_path"]).read_text(encoding="utf-8"))
    ppt_md = (tmp_path / resource["md_path"]).read_text(encoding="utf-8")
    pptx_path = tmp_path / resource["pptx_path"]
    presentation = _load_presentation(pptx_path)

    assert resource["resource_type"] == "ppt"
    assert resource["success"] is True
    assert resource["status"] == "ready"
    assert resource["validation"]["valid"] is True
    assert pptx_path.exists()
    assert pptx_path.stat().st_size > 0
    assert isinstance(ppt_json.get("slides"), list)
    assert len(ppt_json["slides"]) >= expected_min_slides
    assert len(presentation.slides) == len(ppt_json["slides"])
    assert isinstance(ppt_json.get("summary"), str) and ppt_json["summary"].strip()
    assert ppt_json.get("theme")
    assert ppt_json.get("slide_style")
    assert all(str(slide.get("body") or "").strip() for slide in ppt_json["slides"])

    slide_titles = [str(slide.get("title") or "").strip() for slide in ppt_json["slides"]]
    assert all(slide_titles)
    assert len(set(slide_titles)) >= min(4, len(slide_titles))
    first_slide = ppt_json["slides"][0]
    assert str(first_slide.get("slide_role") or "").strip().lower() == "cover"
    assert "标题区" in str(first_slide.get("visual_hint") or "")
    assert any(
        keyword in str(first_slide.get("title") or "") + str(first_slide.get("body") or "")
        for keyword in ["课件", "复习", "HBase", "RowKey", "热点", "预分区"]
    )
    forbidden_visual_terms = ["表格", "流程图", "时间线", "流程箭头", "复杂卡片", "左右分栏", "双色对比"]
    for slide in ppt_json["slides"]:
        body = str(slide.get("body") or "").strip()
        bullets = slide.get("bullets")
        visual_hint = str(slide.get("visual_hint") or "").strip()
        assert isinstance(bullets, list) and 3 <= len(bullets) <= 5
        assert body
        assert len(body) <= 120
        assert visual_hint
        assert not any(term in visual_hint for term in forbidden_visual_terms)

    rendered_text = "\n".join(
        text
        for slide in presentation.slides
        for text in _slide_texts(slide)
    )
    assert any(keyword in ppt_md for keyword in ["Slide 1", "HBase", "RowKey", "热点", "预分区"])
    assert any(str(slide.get("body") or "").strip() in ppt_md for slide in ppt_json["slides"][:2])
    assert any(keyword in rendered_text for keyword in ["HBase", "RowKey", "热点", "预分区"])
    body_terms = [
        term
        for slide in ppt_json["slides"][:2]
        for term in str(slide.get("body") or "").replace("，", " ").replace("。", " ").replace("、", " ").split()
        if len(term) >= 2
    ]
    assert any(term in rendered_text for term in body_terms)
    assert any(title and title in rendered_text for title in slide_titles[:3])
    return ppt_json, ppt_md


def test_ppt_generation_prefers_ppt_specific_model_key(monkeypatch):
    monkeypatch.setattr(
        gt,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "ppt_text": {"model_name": "ppt-strong"},
            "text_cheap": {"model_name": "deepseek-chat"},
        },
    )
    agent = gt.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "ppt",
        {"generation_requirements": {}},
    )

    assert selected == "ppt_text"


def test_default_generation_prefers_cheap_tier_model(monkeypatch):
    monkeypatch.setattr(
        gt,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "text_cheap": {"model_name": "deepseek-chat"},
            "text_strong": {"model_name": "qwen-max"},
        },
    )
    agent = gt.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "documents",
        {"generation_requirements": {}},
    )

    assert selected == "text_cheap"


def test_ppt_generation_honors_explicit_model_key(monkeypatch):
    monkeypatch.setattr(
        gt,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "ppt_text": {"model_name": "ppt-strong"},
            "text_strong": {"model_name": "general-strong"},
        },
    )
    agent = gt.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "ppt",
        {"generation_requirements": {"model_key": "text_strong"}},
    )

    assert selected == "text_strong"


def test_generation_honors_explicit_model_tier(monkeypatch):
    monkeypatch.setattr(
        gt,
        "LITELLM_MODEL_CONFIGS",
        {
            "text": {"model_name": "baseline"},
            "text_cheap": {"model_name": "deepseek-chat"},
            "text_standard": {"model_name": "qwen-plus"},
            "text_strong": {"model_name": "qwen-max"},
        },
    )
    agent = gt.LLMResourceGenerationAgent(model=object())

    selected = agent._resolve_model_key(
        "documents",
        {"generation_requirements": {"model_tier": "strong"}},
    )

    assert selected == "text_strong"


def test_resource_planning_agent_runs_atomic_tools_in_order():
    planner = gt.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])

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

    planner = gt.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = gt.run_resource_generation_agent(
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

    planner = gt.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = gt.run_resource_generation_agent(
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

    planner = gt.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = gt.run_resource_generation_agent(
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

    planner = gt.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"])
    result = gt.run_resource_generation_agent(
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

    ppt_json, ppt_md = _assert_real_ppt_resource(tmp_path, resource, expected_min_slides=2)
    assert ppt_json["theme"] == "academic-clean"
    assert ppt_json["slide_style"] == "study-review"
    assert "解决思路" in ppt_md


@pytest.mark.search
def test_resource_generation_agent_full_chain_with_real_search_persists_grounded_document(monkeypatch, tmp_path):
    search_tool = _require_real_search_tool()
    payload = _build_real_search_payload()

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)

    search_recorder = SearchRecorder(search_tool)
    planner = gt.ResourcePlanningAgent(search_fn=search_recorder)
    result = gt.run_resource_generation_agent(
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
def test_resource_generation_agent_full_chain_with_real_search_and_real_llm_all_resource_types():
    search_tool = _require_real_search_tool()
    _require_real_llm_generation()
    payload = _build_real_search_all_resource_payload()
    expected_types = ["documents", "mindmap", "quiz", "coding_practice", "ppt"]
    artifact_backend = prepare_artifact_backend("resources_generative_real_search_real_llm_workspace")

    original_backend_fn = generative_storage._get_backend_root
    generative_storage._get_backend_root = lambda: artifact_backend
    try:
        search_recorder = SearchRecorder(search_tool)
        planner = gt.ResourcePlanningAgent(search_fn=search_recorder)
        result = gt.run_resource_generation_agent(
            payload,
            generation_agent=gt.LLMResourceGenerationAgent(),
            planning_agent=planner,
        )
    finally:
        generative_storage._get_backend_root = original_backend_fn

    if not search_recorder.calls:
        pytest.skip("Real search tool was not called.")

    retrievals = [call["result"] for call in search_recorder.calls]
    if not any(isinstance(item, dict) and item.get("success") and item.get("paragraphs") for item in retrievals):
        errors = [item.get("error") for item in retrievals if isinstance(item, dict) and item.get("error")]
        pytest.skip(f"Real search returned no usable paragraphs for graph {payload['graph_name']}: {errors}")

    assert result["success"] is True
    assert result["resource_count"] == len(expected_types)
    assert result["success_count"] == len(expected_types)
    assert result["failed_count"] == 0
    assert [item["resource_type"] for item in result["resources"]] == expected_types
    assert len(search_recorder.calls) == len(expected_types)
    assert result["tool_trace"] == [
        item
        for _ in expected_types
        for item in ["invoke_resource_planning_agent", "persist_generated_resource"]
    ]

    manifest = json.loads((artifact_backend / "generative" / f"user_{payload['user_id']}" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["resource_count"] == len(expected_types)
    assert [entry["resource_type"] for entry in manifest["resources"]] == expected_types

    by_type = {item["resource_type"]: item for item in result["resources"]}
    failed_results = [
        {
            "resource_type": item.get("resource_type"),
            "status": item.get("status"),
            "validation": item.get("validation"),
            "title": item.get("title"),
        }
        for item in result.get("resources", [])
        if item.get("status") != "ready" or item.get("validation", {}).get("valid") is not True
    ]
    assert failed_results == []
    for resource_type in expected_types:
        resource = by_type[resource_type]
        assert resource["success"] is True
        assert resource["status"] == "ready"
        assert resource["validation"]["valid"] is True
        assert resource["planning_trace"] == [
            "read_generation_plan",
            "write_generation_plan",
            "retrieve_generation_materials",
            "read_generation_draft",
            "write_generation_draft",
        ]

    document_json = json.loads((artifact_backend / by_type["documents"]["json_path"]).read_text(encoding="utf-8"))
    document_md = (artifact_backend / by_type["documents"]["md_path"]).read_text(encoding="utf-8")
    assert document_json["sections"]
    headings = [str(section.get("heading") or "").strip() for section in document_json["sections"]]
    assert len(set(headings)) >= min(3, len(headings))
    assert not (headings and set(headings) == {"知识点说明"})
    assert any(keyword in document_md for keyword in ["HBase", "RowKey", "热点", "预分区"])

    mindmap_json_path = artifact_backend / by_type["mindmap"]["json_path"]
    mindmap_mermaid_path = artifact_backend / by_type["mindmap"]["mermaid_path"]
    mindmap_svg_path = mindmap_mermaid_path.with_suffix(".svg")
    mindmap_json = json.loads(mindmap_json_path.read_text(encoding="utf-8"))
    mindmap_text = mindmap_mermaid_path.read_text(encoding="utf-8")
    assert mindmap_json["mermaid"].strip().startswith("mindmap")
    assert "RowKey" in mindmap_text or "热点" in mindmap_text
    assert by_type["mindmap"]["validation"]["valid"] is True
    assert by_type["mindmap"]["validation"]["diagram_type"] == "mindmap"
    assert by_type["mindmap"]["validation"]["node_count"] >= 3
    render_result = _try_render_mermaid_svg(mindmap_mermaid_path, mindmap_svg_path)
    if render_result["checked"]:
        assert render_result["success"] is True, render_result["stderr"]
        assert mindmap_svg_path.exists()
        assert "<svg" in mindmap_svg_path.read_text(encoding="utf-8", errors="ignore")
    write_test_artifact(
        "real_search_real_llm_mindmap_render.json",
        {
            "mermaid_path": str(mindmap_mermaid_path),
            "svg_path": str(mindmap_svg_path),
            "render_result": render_result,
        },
    )

    quiz_json = json.loads((artifact_backend / by_type["quiz"]["json_path"]).read_text(encoding="utf-8"))
    quiz_md = (artifact_backend / by_type["quiz"]["md_path"]).read_text(encoding="utf-8")
    assert quiz_json["questions"]
    assert all(question.get("answer") for question in quiz_json["questions"])
    assert "## Q1." in quiz_md
    assert "Answer:" in quiz_md
    assert "Explanation:" in quiz_md

    practice_json = json.loads((artifact_backend / by_type["coding_practice"]["json_path"]).read_text(encoding="utf-8"))
    practice_md = (artifact_backend / by_type["coding_practice"]["md_path"]).read_text(encoding="utf-8")
    entry_file_path = artifact_backend / by_type["coding_practice"]["entry_file_path"]
    assert practice_json["steps"]
    assert practice_json["code_files"]
    assert entry_file_path.exists()
    assert "Practice Steps" in practice_md

    ppt_json, ppt_md = _assert_real_ppt_resource(artifact_backend, by_type["ppt"], expected_min_slides=6)

    artifact_json_path = write_test_artifact(
        "resources_generative_real_search_real_llm_all_resources_result.json",
        {
            "request": payload,
            "retrieval_contexts": retrievals,
            "summary": {
                "resource_types": expected_types,
                "success_count": result["success_count"],
                "failed_count": result["failed_count"],
                "ppt_slide_count": len(ppt_json["slides"]),
                "search_call_count": len(retrievals),
            },
            "result": result,
            "resource_json": {
                "ppt": ppt_json,
            },
            "artifact_backend": str(artifact_backend),
        },
    )
    artifact_md_path = write_text_artifact(
        "resources_generative_real_search_real_llm_all_resources_ppt.md",
        ppt_md,
    )
    assert artifact_json_path.exists()
    assert artifact_md_path.exists()
