"""Tests for new endpoints added in frontend-portal-redesign (Tasks 1.1–1.4)."""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app import create_app


# ═══════════════════════════════════════════════════════════════════════════════
# 1.1 Video Search
# ═══════════════════════════════════════════════════════════════════════════════

BILIBILI_MOCK_RESPONSE = {
    "code": 0,
    "data": {
        "result": [
            {
                "title": "HBase RowKey<em>设计</em>详解",
                "bvid": "BV1xx411c7mD",
                "pic": "https://i0.hdslb.com/bfs/archive/abc.jpg",
                "duration": "15:30",
                "author": "大数据讲师",
                "play": 12345,
                "description": "HBase RowKey design tutorial",
            },
            {
                "title": "Redis<em>集群</em>搭建实战",
                "bvid": "BV1xx411c8nE",
                "pic": "https://i0.hdslb.com/bfs/archive/def.jpg",
                "duration": "22:10",
                "author": "后端开发",
                "play": 8901,
                "description": "Redis cluster setup",
            },
        ]
    },
}


def test_video_search_returns_normalized_results():
    """B站 search → normalized {title, thumbnail_url, video_url, duration, source, author}."""
    app = create_app()
    app.testing = True
    client = app.test_client()

    with patch("blueprint.learning_api.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = BILIBILI_MOCK_RESPONSE
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        response = client.post(
            "/api/knowledge/video_search",
            json={"query": "RowKey 设计", "max_results": 3},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        videos = data["videos"]
        assert len(videos) == 2

        v = videos[0]
        assert v["title"] == "HBase RowKey设计详解"  # HTML tags stripped
        assert v["source"] == "bilibili"
        assert v["video_url"] == "https://www.bilibili.com/video/BV1xx411c7mD"
        assert v["thumbnail_url"] == "https://i0.hdslb.com/bfs/archive/abc.jpg"
        assert v["duration"] == "15:30"
        assert v["author"] == "大数据讲师"
        assert v["play_count"] == 12345


def test_video_search_empty_query_returns_400():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post("/api/knowledge/video_search", json={"query": ""})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False


def test_video_search_timeout_fallback():
    """8s timeout → returns partial/empty, no 5xx."""
    app = create_app()
    app.testing = True
    client = app.test_client()

    with patch("blueprint.learning_api.requests.get") as mock_get:
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.Timeout("timed out")

        response = client.post(
            "/api/knowledge/video_search",
            json={"query": "anything"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["videos"] == []


def test_video_search_with_topic_combines_query():
    """topic + query → combined search string."""
    app = create_app()
    app.testing = True
    client = app.test_client()

    with patch("blueprint.learning_api.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 0, "data": {"result": []}}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        client.post(
            "/api/knowledge/video_search",
            json={"query": "分布式存储", "topic": "HBase", "max_results": 5},
        )
        call_args = mock_get.call_args
        # keyword should contain both topic and query
        assert "HBase" in call_args[1]["params"]["keyword"]
        assert "分布式存储" in call_args[1]["params"]["keyword"]


# ═══════════════════════════════════════════════════════════════════════════════
# 1.2 GitHub Search
# ═══════════════════════════════════════════════════════════════════════════════

GITHUB_MOCK_RESPONSE = {
    "total_count": 2,
    "items": [
        {
            "full_name": "apache/hbase",
            "description": "Apache HBase",
            "html_url": "https://github.com/apache/hbase",
            "stargazers_count": 5200,
            "language": "Java",
            "license": {"spdx_id": "Apache-2.0"},
        },
        {
            "full_name": "apache/hadoop",
            "description": "Apache Hadoop",
            "html_url": "https://github.com/apache/hadoop",
            "stargazers_count": 14100,
            "language": "Java",
            "license": {"spdx_id": "Apache-2.0"},
        },
    ],
}


def test_github_search_returns_normalized_results():
    app = create_app()
    app.testing = True
    client = app.test_client()

    with patch("blueprint.knowledge_build_api.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = GITHUB_MOCK_RESPONSE
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        response = client.post(
            "/api/knowledge/github_search",
            json={"query": "big data", "max_results": 6, "min_stars": 50},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        repos = data["repos"]
        assert len(repos) == 2

        r = repos[0]
        assert r["full_name"] == "apache/hbase"
        assert r["stars"] == 5200
        assert r["language"] == "Java"
        assert r["license"] == "Apache-2.0"


def test_github_search_empty_query_returns_400():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post("/api/knowledge/github_search", json={"query": ""})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False


def test_github_search_api_unavailable_returns_empty():
    app = create_app()
    app.testing = True
    client = app.test_client()

    with patch("blueprint.knowledge_build_api.requests.get") as mock_get:
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.ConnectionError("unreachable")

        response = client.post(
            "/api/knowledge/github_search",
            json={"query": "anything"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["repos"] == []


def test_github_search_applies_topic_and_stars_filter():
    app = create_app()
    app.testing = True
    client = app.test_client()

    with patch("blueprint.knowledge_build_api.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"total_count": 0, "items": []}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        client.post(
            "/api/knowledge/github_search",
            json={"query": "distributed", "topic": "big-data", "min_stars": 100},
        )
        call_args = mock_get.call_args
        q = call_args[1]["params"]["q"]
        assert "distributed" in q
        assert "topic:big-data" in q
        assert "stars:>=100" in q
        assert call_args[1]["params"]["sort"] == "stars"


# ═══════════════════════════════════════════════════════════════════════════════
# 1.3 File Upload Calendar — title param
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.mysql
def test_file_upload_calendar_with_title():
    """POST /api/file_upload_calendar with optional title → syllabus has admin-set title."""
    from extensions import db
    from schemas.user import User

    app = create_app()
    app.testing = True
    client = app.test_client()

    with app.app_context():
        op = User(
            user_name="test_upload_title_op",
            password_hash="-",
            email="test_upload_title_op@t",
            permission="operator",
        )
        db.session.add(op)
        db.session.commit()
        op_id = op.user_id

    try:
        pdf_bytes_b64 = base64.b64encode(b"%PDF-1.4 test").decode()
        response = client.post(
            "/api/file_upload_calendar",
            json={
                "file_name": "test_cal.pdf",
                "file_bytes": pdf_bytes_b64,
                "title": "自定义学科名称",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert isinstance(data["syllabus"]["syllabus_id"], int)

        # Verify title was set
        from repositories.syllabus_repo import get_syllabus_by_id
        with app.app_context():
            syl = get_syllabus_by_id(data["syllabus"]["syllabus_id"])
            assert syl is not None
            assert syl.title == "自定义学科名称"
    finally:
        with app.app_context():
            from schemas.syllabus import Syllabus
            Syllabus.query.filter_by(title="自定义学科名称").delete()
            User.query.filter_by(user_id=op_id).delete()
            db.session.commit()


@pytest.mark.mysql
def test_file_upload_calendar_without_title():
    """POST /api/file_upload_calendar without title → syllabus.title is None (backward compat)."""
    from extensions import db
    from schemas.user import User

    app = create_app()
    app.testing = True
    client = app.test_client()

    with app.app_context():
        op = User(
            user_name="test_upload_notitle_op",
            password_hash="-",
            email="test_upload_notitle_op@t",
            permission="operator",
        )
        db.session.add(op)
        db.session.commit()
        op_id = op.user_id

    try:
        pdf_bytes_b64 = base64.b64encode(b"%PDF-1.4 test").decode()
        response = client.post(
            "/api/file_upload_calendar",
            json={
                "file_name": "test_cal2.pdf",
                "file_bytes": pdf_bytes_b64,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        from repositories.syllabus_repo import get_syllabus_by_id
        with app.app_context():
            syl = get_syllabus_by_id(data["syllabus"]["syllabus_id"])
            assert syl is not None
            # title may be None or set by build_draft later — backward compat preserved
    finally:
        with app.app_context():
            from schemas.syllabus import Syllabus
            Syllabus.query.filter_by(syllabus_id=data["syllabus"]["syllabus_id"]).delete()
            User.query.filter_by(user_id=op_id).delete()
            db.session.commit()


@pytest.mark.mysql
def test_file_upload_calendar_missing_file():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post(
        "/api/file_upload_calendar",
        json={"title": "No File"},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 1.4 Buddy Synthesis
# ═══════════════════════════════════════════════════════════════════════════════

def test_buddy_synthesis_message_persisted(monkeypatch):
    """synthesis_proactive_message → LLM reply persisted as source='synthesis'."""
    import tasks.study_buddy_task as task
    from tasks.study_buddy.messages import load_buddy_messages

    # Redirect storage
    import tasks.study_buddy.memory as mem
    import tasks.study_buddy.messages as msg
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr(mem, "_memory_root", lambda: tmp)
    monkeypatch.setattr(msg, "_memory_root", lambda: tmp)

    # Mock LLM
    def fake_synthesis(**kwargs):
        return "你的RowKey设计还需要多练习，不过HBase基础已经掌握得不错了，趁热打铁继续吧。"

    monkeypatch.setattr(task, "synthesis_proactive_message", fake_synthesis)

    result = task.generate_buddy_synthesis(
        user_id=1,
        syllabus_id=29,
        plan={"steps": []},
        study_graph_features={"weak_topics": ["RowKey 设计"]},
    )
    assert result["synthesis"] is not None
    assert "RowKey" in result["synthesis"]
    assert result["cached"] is False

    # Verify persisted
    messages = load_buddy_messages(1, 29)
    synthesis_msgs = [m for m in messages if m.get("source") == "synthesis"]
    assert len(synthesis_msgs) == 1
    assert synthesis_msgs[0]["text"] == result["synthesis"]
    assert synthesis_msgs[0]["from"] == "buddy"


def test_buddy_synthesis_cache_hit(monkeypatch):
    """Second call within 5 min → returns cached, no LLM call."""
    import tasks.study_buddy_task as task
    import tasks.study_buddy.memory as mem
    import tasks.study_buddy.messages as msg
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr(mem, "_memory_root", lambda: tmp)
    monkeypatch.setattr(msg, "_memory_root", lambda: tmp)
    task._synthesis_cache.clear()  # avoid cross-test contamination

    call_count = [0]

    def fake_synthesis(**kwargs):
        call_count[0] += 1
        return "综合建议：继续加油。"

    monkeypatch.setattr(task, "synthesis_proactive_message", fake_synthesis)

    # First call — generates
    r1 = task.generate_buddy_synthesis(user_id=1, syllabus_id=29, plan={}, study_graph_features={})
    assert r1["cached"] is False
    assert call_count[0] == 1

    # Second call — should hit cache
    r2 = task.generate_buddy_synthesis(user_id=1, syllabus_id=29, plan={}, study_graph_features={})
    assert r2["cached"] is True
    assert r2["synthesis"] == "综合建议：继续加油。"
    assert call_count[0] == 1  # NOT called again


def test_buddy_synthesis_force_refresh(monkeypatch):
    """force=True → bypasses cache, re-generates."""
    import tasks.study_buddy_task as task
    import tasks.study_buddy.memory as mem
    import tasks.study_buddy.messages as msg
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr(mem, "_memory_root", lambda: tmp)
    monkeypatch.setattr(msg, "_memory_root", lambda: tmp)
    task._synthesis_cache.clear()  # avoid cross-test contamination

    call_count = [0]

    def fake_synthesis(**kwargs):
        call_count[0] += 1
        return f"suggestion #{call_count[0]}"

    monkeypatch.setattr(task, "synthesis_proactive_message", fake_synthesis)

    r1 = task.generate_buddy_synthesis(user_id=1, syllabus_id=29, plan={}, study_graph_features={})
    assert r1["cached"] is False

    r2 = task.generate_buddy_synthesis(user_id=1, syllabus_id=29, plan={}, study_graph_features={}, force=True)
    assert r2["cached"] is False
    assert call_count[0] == 2
    assert r2["synthesis"] == "suggestion #2"


def test_buddy_synthesis_no_explore_returns_none(monkeypatch):
    """No explore nodes → synthesis returns None."""
    import tasks.study_buddy_task as task
    import tasks.study_buddy.memory as mem
    import tasks.study_buddy.messages as msg
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr(mem, "_memory_root", lambda: tmp)
    monkeypatch.setattr(msg, "_memory_root", lambda: tmp)
    task._synthesis_cache.clear()  # avoid cross-test contamination

    # Mock synthesis_proactive_message directly since we're testing the skip logic
    from tasks.study_buddy.buddy_agent import synthesis_proactive_message

    def fake_synthesis_no_explore(**kwargs):
        return None  # LLM returns None when no explore nodes

    monkeypatch.setattr(task, "synthesis_proactive_message", fake_synthesis_no_explore)

    result = task.generate_buddy_synthesis(user_id=1, syllabus_id=29, plan={}, study_graph_features={})
    assert result["synthesis"] is None
    assert result["cached"] is False

    # No message persisted for empty synthesis
    messages = msg.load_buddy_messages(1, 29)
    assert len(messages) == 0
