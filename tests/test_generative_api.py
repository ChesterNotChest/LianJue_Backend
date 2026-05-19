from flask import Flask

from blueprint import generative_api
from tasks import resource_generation_agent_task as rgat
from tasks import resource_planning_agent_task as rpat
from tasks.generative import storage as generative_storage


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
        raise ValueError(f"unsupported resource_type: {resource_type}")


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(generative_api.bp)
    return app


def test_generative_generate_api_requires_required_fields():
    client = _make_app().test_client()

    response = client.post("/api/generative_generate", json={"user_id": 7})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "missing_fields"


def test_generative_api_full_chain_generate_list_and_detail(monkeypatch, tmp_path):
    client = _make_app().test_client()

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)
    monkeypatch.setattr(generative_api, "_get_backend_root", lambda: tmp_path)
    monkeypatch.setattr(rgat, "LLMResourceGenerationAgent", FakeResourceGenerationAgent)
    monkeypatch.setattr(
        rpat,
        "get_resource_planning_agent",
        lambda: rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"]),
    )

    generate_response = client.post("/api/generative_generate", json=dict(FIXED_PAYLOAD))
    assert generate_response.status_code == 200
    generate_payload = generate_response.get_json()
    assert generate_payload["success"] is True
    assert generate_payload["resource_count"] == 3
    assert [item["resource_type"] for item in generate_payload["resources"]] == ["documents", "mindmap", "quiz"]

    list_response = client.post(
        "/api/generative_list",
        json={"user_id": FIXED_PAYLOAD["user_id"], "syllabus_id": FIXED_PAYLOAD["syllabus_id"]},
    )
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload["success"] is True
    assert len(list_payload["materials"]) == 3

    quiz_item = next(item for item in list_payload["materials"] if item["resource_type"] == "quiz")
    detail_response = client.post(
        "/api/generative_detail",
        json={"user_id": FIXED_PAYLOAD["user_id"], "resource_id": quiz_item["resource_id"]},
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["success"] is True
    assert detail_payload["material"]["resource_id"] == quiz_item["resource_id"]
    assert detail_payload["material"]["content"]["title"] == quiz_item["title"]
    assert detail_payload["material"]["render"]["markdown"]
