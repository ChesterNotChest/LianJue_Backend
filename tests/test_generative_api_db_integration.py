import uuid

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import resource_generation_agent_task as rgat
from tasks import resource_planning_agent_task as rpat
from blueprint import generative_api
from tasks.generative import storage as generative_storage


FIXED_PAYLOAD = {
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


@pytest.fixture
def db_generative_case(repo_json_factory):
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        syllabus_path = repo_json_factory(
            "schedule/syllabus",
            {
                "title": "HBase 个性化学习",
                "period": [
                    {
                        "week_index": 5,
                        "content": "HBase RowKey 设计",
                        "enhanced_content": "RowKey 热点、预分区与散列策略",
                        "importance": "high",
                    }
                ],
            },
            prefix="generative_api_db",
        )
        user = User(
            user_name=f"generative-api-{suffix}",
            password_hash="pytest-not-used",
            email=f"generative-api-{suffix}@example.com",
        )
        syllabus = Syllabus(
            title="HBase 个性化学习",
            syllabus_path=str(syllabus_path),
        )
        db.session.add(user)
        db.session.add(syllabus)
        db.session.commit()

        relation = UserSyllabus(
            user_id=user.user_id,
            syllabus_id=syllabus.syllabus_id,
            syllabus_permission="user",
        )
        db.session.add(relation)
        db.session.commit()

        try:
            yield app, user, syllabus, relation
        finally:
            db.session.rollback()
            UserSyllabus.query.filter_by(user_id=user.user_id, syllabus_id=syllabus.syllabus_id).delete()
            Syllabus.query.filter_by(syllabus_id=syllabus.syllabus_id).delete()
            User.query.filter_by(user_id=user.user_id).delete()
            db.session.commit()


def test_generative_api_db_integration_full_chain(monkeypatch, tmp_path, db_generative_case):
    app, user, syllabus, relation = db_generative_case
    client = app.test_client()

    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: tmp_path)
    monkeypatch.setattr(generative_api, "_get_backend_root", lambda: tmp_path)
    monkeypatch.setattr(rgat, "LLMResourceGenerationAgent", FakeResourceGenerationAgent)
    monkeypatch.setattr(
        rpat,
        "get_resource_planning_agent",
        lambda: rpat.ResourcePlanningAgent(search_fn=lambda *args, **kwargs: FIXED_PAYLOAD["retrieval_context"]),
    )

    payload = {
        **FIXED_PAYLOAD,
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
    }

    response = client.post("/api/generative_generate", json=payload)
    assert response.status_code == 200
    body = response.get_json()

    assert body["success"] is True
    assert body["resource_count"] == 3
    assert body["success_count"] == 3
    assert body["failed_count"] == 0
    assert body["request"]["user_id"] == user.user_id
    assert body["request"]["syllabus_id"] == syllabus.syllabus_id
    assert [item["resource_type"] for item in body["resources"]] == ["documents", "mindmap", "quiz"]

    list_response = client.post(
        "/api/generative_list",
        json={"user_id": user.user_id, "syllabus_id": syllabus.syllabus_id},
    )
    assert list_response.status_code == 200
    list_body = list_response.get_json()
    assert list_body["success"] is True
    assert len(list_body["materials"]) == 3

    first_resource = list_body["materials"][0]
    detail_response = client.post(
        "/api/generative_detail",
        json={"user_id": user.user_id, "resource_id": first_resource["resource_id"]},
    )
    assert detail_response.status_code == 200
    detail_body = detail_response.get_json()
    assert detail_body["success"] is True
    assert detail_body["material"]["resource_id"] == first_resource["resource_id"]
    assert detail_body["material"]["syllabus_id"] == syllabus.syllabus_id
    assert relation.user_id == user.user_id
    assert relation.syllabus_id == syllabus.syllabus_id
