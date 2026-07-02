"""演示学生播种 — opt-in，不可 monkeypatch，持久化到真实路径。

生成 3 个学生（低/中/高进度），每个有：画像 + [学习计划 + 学习树 + 生成资源]。

运行：
  RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v
  RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 pytest tests/total_agent/test_seed_demo_students.py -v -k demo_medium
"""

import json
import os
import time
import uuid
from pathlib import Path

import pytest

from werkzeug.security import generate_password_hash

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import learning_profile_task as lpt
from tasks import personal_recommendation_task as prt
from tasks import study_graph_task as sgt
from tasks.generative_task import generate_resources_from_request

DEMO_SYLLABUS_IDS = [8]
WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"
DEMO_PASSWORD = "demo123"
DEMO_SUMMARY_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "demo_students"
PROCESS_CONTRACT_SCHEMA_VERSION = "total_agent_process_contract.v1"
LEVEL_LOW = "low"
LEVEL_MEDIUM = "medium"
LEVEL_HIGH = "high"


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def demo_seed_use_db_backends(monkeypatch, default_runtime_file_backends):
    """Override conftest FILE_BACKEND — demo students use production DB paths."""
    monkeypatch.setenv("LEARNING_PLAN_FILE_BACKEND", "0")
    monkeypatch.setenv("GENERATIVE_FILE_BACKEND", "0")
    monkeypatch.setenv("STUDY_GRAPH_FILE_BACKEND", "0")
    yield


@pytest.fixture(autouse=True)
def cleanup_new_json_artifacts():
    """Override conftest autouse — preserve demo profiles on disk."""
    yield


def _require_seed_demo_env():
    missing = [
        name for name in ("RUN_LLM_TESTS", "RUN_REAL_RAG_TESTS", "RUN_DB_TESTS")
        if os.getenv(name) != "1"
    ]
    if missing:
        pytest.skip(
            "Set RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1"
        )
    if not DEMO_SYLLABUS_IDS:
        pytest.skip("DEMO_SYLLABUS_IDS is empty")


def _normalize_model_for_dashscope():
    from tasks.personal_recommendation import agent_runtime as recommendation_runtime
    text_config = recommendation_runtime.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        recommendation_runtime.get_personal_recommendation_agent.cache_clear()


def _graph_name() -> str:
    return (
        os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME")
        or os.getenv("SEARCH_TOOL_GRAPH_NAME")
        or "RAG"
    )


def _get_demo_syllabus():
    """Pick the first configured demo syllabus. Add more ids to DEMO_SYLLABUS_IDS later."""
    for syllabus_id in DEMO_SYLLABUS_IDS:
        syllabus = Syllabus.query.filter_by(syllabus_id=syllabus_id).first()
        if syllabus is not None:
            return syllabus
    pytest.skip(f"No configured demo syllabus found; expected one of {DEMO_SYLLABUS_IDS}")


@pytest.fixture
def demo_db_env():
    _require_seed_demo_env()
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"demo_{suffix}",
            password_hash=generate_password_hash(DEMO_PASSWORD),
            email=f"demo_{suffix}@lianjue.example.com",
        )
        syllabus = _get_demo_syllabus()
        db.session.add(user)
        db.session.commit()
        relation = UserSyllabus(
            user_id=user.user_id,
            syllabus_id=syllabus.syllabus_id,
            syllabus_permission="user",
        )
        db.session.add(relation)
        db.session.commit()
        # NOTE: no teardown — demo users persist. Tests may rename user
        # (with explicit .user_name assignment + db.session.commit()).
        yield user, syllabus, relation


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Profile input records
# ═══════════════════════════════════════════════════════════════════════════════

def _build_profile_input_records(level: str, now_ts: int) -> dict:
    """Build profile input records for a given level.

    All *_offset_seconds are negative offsets from now_ts.
    """
    if level == LEVEL_LOW:
        return {
            "dialogue_text": [
                "我刚接触大数据，正在学课程导论部分。",
                "对大数据的基本概念有一些了解，想继续学下去。",
            ],
            "learning_goal": "了解大数据基本概念和核心框架",
            "learning_records": [
                {
                    "event_type": "study_session", "topic": "大数据课程导论",
                    "duration_minutes": 30, "status": "completed", "score": 0.72,
                    "started_at": now_ts - 172800,
                    "meta": {"knowledge_points": ["大数据基础"]},
                },
                {
                    "event_type": "study_session", "topic": "大数据定义与特征",
                    "duration_minutes": 25, "status": "completed", "score": 0.68,
                    "started_at": now_ts - 86400,
                    "meta": {"knowledge_points": ["大数据基础"]},
                },
            ],
            "answer_records": [
                {
                    "question": "大数据的4V特征是什么？", "correct": True,
                    "time_spent_seconds": 60, "answered_at": now_ts - 86400,
                    "meta": {"knowledge_points": ["大数据基础"]},
                },
            ],
            "resource_usage": [
                {
                    "resource_id": "doc-intro-001", "resource_type": "documents",
                    "action": "complete", "duration_seconds": 600,
                    "timestamp": now_ts - 172800,
                    "meta": {"knowledge_points": ["大数据基础"]},
                },
            ],
        }
    elif level == LEVEL_MEDIUM:
        return {
            "dialogue_text": [
                "我已经学完了大数据基础、数据感知与获取、ETL和HDFS的内容。",
                "现在开始学HBase，分布式数据库的概念有点复杂。",
                "希望能从HBase基础逐步深入，非关系型数据库也想了解一下。",
            ],
            "learning_goal": "系统掌握HBase及非关系型数据库基础知识",
            "learning_records": [
                {"event_type": "study_session", "topic": "大数据课程导论", "duration_minutes": 40, "status": "completed", "score": 0.88, "started_at": now_ts - 3628800, "meta": {"knowledge_points": ["大数据课程导论"]}},
                {"event_type": "study_session", "topic": "大数据感知与获取", "duration_minutes": 35, "status": "completed", "score": 0.85, "started_at": now_ts - 3024000, "meta": {"knowledge_points": ["大数据感知与获取"]}},
                {"event_type": "study_session", "topic": "数据抽取转换装载过程", "duration_minutes": 35, "status": "completed", "score": 0.82, "started_at": now_ts - 2419200, "meta": {"knowledge_points": ["数据抽取转换装载"]}},
                {"event_type": "study_session", "topic": "分布式文件系统 HDFS", "duration_minutes": 45, "status": "completed", "score": 0.86, "started_at": now_ts - 1814400, "meta": {"knowledge_points": ["HDFS"]}},
                {"event_type": "practice", "topic": "HDFS读写流程", "duration_minutes": 25, "status": "completed", "score": 0.80, "started_at": now_ts - 1728000, "meta": {"knowledge_points": ["HDFS"]}},
                {"event_type": "study_session", "topic": "分布式数据库 HBase", "duration_minutes": 30, "status": "completed", "score": 0.72, "started_at": now_ts - 1209600, "meta": {"knowledge_points": ["HBase"]}},
                {"event_type": "study_session", "topic": "非关系型数据库入门", "duration_minutes": 30, "status": "partial", "score": 0.48, "started_at": now_ts - 345600, "meta": {"knowledge_points": ["非关系型数据库"]}},
            ],
            "answer_records": [
                {"question": "HDFS的NameNode负责什么？", "correct": True, "time_spent_seconds": 75, "answered_at": now_ts - 1728000, "meta": {"knowledge_points": ["HDFS"]}},
                {"question": "数据ETL过程中转换阶段的主要工作是什么？", "correct": True, "time_spent_seconds": 90, "answered_at": now_ts - 2246400, "meta": {"knowledge_points": ["数据抽取转换装载"]}},
                {"question": "HBase和传统关系型数据库的主要区别是什么？", "correct": True, "time_spent_seconds": 120, "answered_at": now_ts - 864000, "meta": {"knowledge_points": ["HBase"]}},
                {"question": "非关系型数据库的CAP理论是什么？", "correct": False, "time_spent_seconds": 110, "answered_at": now_ts - 172800, "meta": {"knowledge_points": ["非关系型数据库"]}},
                {"question": "大数据感知与获取中的数据源有哪些类型？", "correct": True, "time_spent_seconds": 65, "answered_at": now_ts - 2764800, "meta": {"knowledge_points": ["大数据感知与获取"]}},
            ],
            "resource_usage": [
                {"resource_id": "doc-bigdata-intro", "resource_type": "documents", "action": "complete", "duration_seconds": 800, "timestamp": now_ts - 3456000, "meta": {"knowledge_points": ["大数据课程导论"]}},
                {"resource_id": "doc-hdfs-001", "resource_type": "documents", "action": "complete", "duration_seconds": 700, "timestamp": now_ts - 1728000, "meta": {"knowledge_points": ["HDFS"]}},
                {"resource_id": "quiz-hdfs-001", "resource_type": "quiz", "action": "submit", "score": 0.82, "duration_seconds": 300, "timestamp": now_ts - 1641600, "meta": {"knowledge_points": ["HDFS"]}},
            ],
        }
    else:  # HIGH
        return {
            "dialogue_text": [
                "我已经完成了大数据概论的大部分内容，包括HDFS、HBase、MapReduce、非关系型数据库等。",
                "对Spark和RowKey热点还有疑惑，需要加强复习。",
                "希望针对弱项进行有重点的巩固练习。",
            ],
            "learning_goal": "巩固大数据核心技术，强化Spark及RowKey热点知识",
            "learning_records": [
                {"event_type": "study_session", "topic": "大数据课程导论", "duration_minutes": 40, "status": "completed", "score": 0.91, "started_at": now_ts - 7257600, "meta": {"knowledge_points": ["大数据课程导论"]}},
                {"event_type": "study_session", "topic": "大数据感知与获取", "duration_minutes": 35, "status": "completed", "score": 0.87, "started_at": now_ts - 6652800, "meta": {"knowledge_points": ["大数据感知与获取"]}},
                {"event_type": "study_session", "topic": "数据抽取转换装载", "duration_minutes": 35, "status": "completed", "score": 0.84, "started_at": now_ts - 6048000, "meta": {"knowledge_points": ["数据抽取转换装载"]}},
                {"event_type": "study_session", "topic": "分布式文件系统 HDFS", "duration_minutes": 45, "status": "completed", "score": 0.89, "started_at": now_ts - 5443200, "meta": {"knowledge_points": ["HDFS"]}},
                {"event_type": "practice", "topic": "HDFS读写流程", "duration_minutes": 30, "status": "completed", "score": 0.83, "started_at": now_ts - 4838400, "meta": {"knowledge_points": ["HDFS"]}},
                {"event_type": "study_session", "topic": "分布式数据库 HBase", "duration_minutes": 45, "status": "completed", "score": 0.82, "started_at": now_ts - 4233600, "meta": {"knowledge_points": ["HBase"]}},
                {"event_type": "study_session", "topic": "非关系型数据库对比", "duration_minutes": 35, "status": "completed", "score": 0.78, "started_at": now_ts - 3931200, "meta": {"knowledge_points": ["非关系型数据库"]}},
                {"event_type": "study_session", "topic": "关联规则挖掘 Apriori", "duration_minutes": 40, "status": "completed", "score": 0.75, "started_at": now_ts - 3628800, "meta": {"knowledge_points": ["关联规则挖掘"]}},
                {"event_type": "study_session", "topic": "大数据可视化方法", "duration_minutes": 35, "status": "completed", "score": 0.80, "started_at": now_ts - 3024000, "meta": {"knowledge_points": ["大数据可视化"]}},
                {"event_type": "study_session", "topic": "MapReduce 基础", "duration_minutes": 40, "status": "completed", "score": 0.76, "started_at": now_ts - 2419200, "meta": {"knowledge_points": ["MapReduce"]}},
                {"event_type": "study_session", "topic": "Spark 基础", "duration_minutes": 35, "status": "partial", "score": 0.48, "started_at": now_ts - 1209600, "meta": {"knowledge_points": ["Spark"]}},
                {"event_type": "study_session", "topic": "RowKey 热点规避", "duration_minutes": 30, "status": "partial", "score": 0.42, "started_at": now_ts - 864000, "meta": {"knowledge_points": ["RowKey"]}},
                {"event_type": "study_session", "topic": "预分区策略", "duration_minutes": 25, "status": "partial", "score": 0.38, "started_at": now_ts - 604800, "meta": {"knowledge_points": ["预分区"]}},
            ],
            "answer_records": [
                {"question": "HDFS的NameNode和DataNode各自负责什么？", "correct": True, "time_spent_seconds": 70, "answered_at": now_ts - 4838400, "meta": {"knowledge_points": ["HDFS"]}},
                {"question": "数据ETL过程中转换阶段的主要工作是什么？", "correct": True, "time_spent_seconds": 85, "answered_at": now_ts - 5443200, "meta": {"knowledge_points": ["数据抽取转换装载"]}},
                {"question": "非关系型数据库相比关系型数据库的优势是什么？", "correct": True, "time_spent_seconds": 80, "answered_at": now_ts - 3628800, "meta": {"knowledge_points": ["非关系型数据库"]}},
                {"question": "关联规则挖掘中支持度和置信度分别指什么？", "correct": True, "time_spent_seconds": 95, "answered_at": now_ts - 3326400, "meta": {"knowledge_points": ["关联规则挖掘"]}},
                {"question": "MapReduce的执行流程是什么？", "correct": True, "time_spent_seconds": 90, "answered_at": now_ts - 2116800, "meta": {"knowledge_points": ["MapReduce"]}},
                {"question": "HBase的RowKey设计原则有哪些？", "correct": False, "time_spent_seconds": 130, "answered_at": now_ts - 864000, "meta": {"knowledge_points": ["RowKey"]}},
                {"question": "什么是预分区？为什么需要预分区？", "correct": False, "time_spent_seconds": 140, "answered_at": now_ts - 604800, "meta": {"knowledge_points": ["预分区"]}},
                {"question": "Spark相比MapReduce的优势有哪些？", "correct": False, "time_spent_seconds": 120, "answered_at": now_ts - 518400, "meta": {"knowledge_points": ["Spark"]}},
            ],
            "resource_usage": [
                {"resource_id": "doc-intro-001", "resource_type": "documents", "action": "complete", "duration_seconds": 800, "timestamp": now_ts - 6900000, "meta": {"knowledge_points": ["大数据课程导论"]}},
                {"resource_id": "doc-hdfs-001", "resource_type": "documents", "action": "complete", "duration_seconds": 700, "timestamp": now_ts - 5100000, "meta": {"knowledge_points": ["HDFS"]}},
                {"resource_id": "quiz-hdfs-001", "resource_type": "quiz", "action": "submit", "score": 0.82, "duration_seconds": 300, "timestamp": now_ts - 5000000, "meta": {"knowledge_points": ["HDFS"]}},
                {"resource_id": "doc-hbase-001", "resource_type": "documents", "action": "complete", "duration_seconds": 750, "timestamp": now_ts - 4000000, "meta": {"knowledge_points": ["HBase"]}},
                {"resource_id": "mindmap-hbase-001", "resource_type": "mindmap", "action": "complete", "duration_seconds": 400, "timestamp": now_ts - 3900000, "meta": {"knowledge_points": ["HBase"]}},
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: Recommendation + Plan seeding
# ═══════════════════════════════════════════════════════════════════════════════

def _tokenize_goal_text(*values: object) -> set[str]:
    """Copy from e2e_cases_large.py — tokenize for goal alignment."""
    raw = " ".join(str(value or "") for value in values)
    normalized = raw.lower()
    for char in "，。；;、/\\|:：()（）[]【】{}<>《》!?！？+-_":
        normalized = normalized.replace(char, " ")
    tokens = {part.strip() for part in normalized.split() if len(part.strip()) >= 2}
    for keyword in ["hbase", "rowkey", "热点", "预分区", "分区", "region", "regionserver", "salt", "加盐"]:
        if keyword.lower() in raw.lower():
            tokens.add(keyword.lower())
    return tokens


def _derive_graph_aligned_goals(recommendation: dict | None, user_goal_tokens: set[str], min_score: float = 1.5) -> dict:
    """Copy from e2e_cases_large.py — map tokenized goals to graph node outcomes."""
    recommendation = recommendation if isinstance(recommendation, dict) else {}
    graph = recommendation.get("graph") if isinstance(recommendation.get("graph"), dict) else {}
    rag_overlay = recommendation.get("rag_overlay") if isinstance(recommendation.get("rag_overlay"), dict) else {}
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    matched_nodes = {
        str(item.get("node_id")): item
        for item in (rag_overlay.get("matched_nodes") or [])
        if isinstance(item, dict) and item.get("node_id")
    }
    ranked = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        title = str(node.get("title") or "")
        outcomes = [str(item) for item in node.get("outcomes") or [] if str(item or "").strip()]
        evidence = matched_nodes.get(node_id) or node.get("rag_evidence") or {}
        evidence_entities = evidence.get("evidence_entities") if isinstance(evidence, dict) else []
        matched_by = evidence.get("matched_by") if isinstance(evidence, dict) else []
        node_tokens = _tokenize_goal_text(node_id, title, " ".join(outcomes), " ".join(evidence_entities or []), " ".join(matched_by or []))
        overlap = user_goal_tokens & node_tokens
        relevance = float(node.get("rag_relevance") or (evidence.get("relevance") if isinstance(evidence, dict) else 0) or 0)
        score = len(overlap) + relevance
        if overlap:
            score += 0.5
        ranked.append({
            "node_id": node_id, "title": title, "outcomes": outcomes,
            "score": round(score, 4), "overlap": sorted(overlap),
            "rag_relevance": relevance,
        })
    ranked.sort(key=lambda item: (item["score"], len(item["overlap"]), item["rag_relevance"]), reverse=True)
    best = ranked[0] if ranked else {}
    if not best or best.get("score", 0) < min_score or not best.get("overlap"):
        return {"goals": [], "selected_node": None, "ranked_nodes": ranked[:8], "reason": "no_semantically_aligned_syllabus_node", "min_score": min_score}
    return {"goals": (best.get("outcomes") or [best.get("title") or best.get("node_id")])[:2], "selected_node": best, "ranked_nodes": ranked[:8], "reason": "semantic_overlap_with_user_goal_or_rag_evidence", "min_score": min_score}


def _has_best_path(recommendation: dict | None) -> bool:
    if not isinstance(recommendation, dict):
        return False
    best_path = recommendation.get("best_path")
    return isinstance(best_path, dict) and bool(best_path.get("path"))


def _run_recommendation_for_demo(user_id: int, syllabus_id: int, graph_name: str, goals: list[str], learning_goal: str, question: str) -> dict:
    """Run real LLM recommendation with deterministic fallback, then save snapshot and accept plan."""
    _normalize_model_for_dashscope()
    payload = {
        "user_id": user_id, "syllabus_id": syllabus_id,
        "goals": goals, "question": question, "learning_goal": learning_goal,
        "graph_name": graph_name, "rag_top_k": 5,
        "decomposer_mode": "agent", "K": 10, "beam_width": 8,
    }
    # Step 1: LLM agent
    agent_result = prt.run_personal_recommendation_agent(payload)
    recommendation = agent_result.recommendation if isinstance(agent_result.recommendation, dict) else None
    flow = "agent"

    # Step 2: fallback via goal alignment
    if not _has_best_path(recommendation):
        user_goal_tokens = _tokenize_goal_text(question, learning_goal, " ".join(goals))
        goal_alignment = _derive_graph_aligned_goals(recommendation, user_goal_tokens)
        aligned_goals = goal_alignment.get("goals") or []
        if aligned_goals:
            aligned_payload = dict(payload)
            aligned_payload["goals"] = aligned_goals
            aligned_payload["goal_normalization_source"] = "syllabus_learning_tree"
            aligned_payload.pop("graph_name", None)
            aligned_payload.pop("rag_top_k", None)
            recommendation = prt.run_recommendation_route_from_payload(aligned_payload)
            flow = "deterministic_retry"
        else:
            return {"recommendation": None, "snapshot": None, "plan": None, "flow": "failed", "error": goal_alignment.get("reason")}

    if not _has_best_path(recommendation):
        return {"recommendation": recommendation, "snapshot": None, "plan": None, "flow": flow, "error": "no_best_path"}

    # Step 3: snapshot (proposed only — do NOT auto-accept; demo users should
    # see the candidate-selection UI before a plan is confirmed)
    snapshot = prt.save_recommendation_snapshot(user_id, syllabus_id, recommendation, request_payload=payload)
    return {"recommendation": recommendation, "snapshot": snapshot, "plan": None, "flow": flow}


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3: Study graph seeding
# ═══════════════════════════════════════════════════════════════════════════════

def _study_change(uid: int, sid: int, key: str, title: str, *, signal: str, summary: str, confidence: float = 0.9, parent_title: str = "", delta: float | None = None) -> dict:
    """Copy from e2e_cases_amend.py — build a single knowledge node change."""
    mastery: dict = {"signal": signal}
    if delta is not None:
        mastery["delta"] = delta
    change = {
        "op": "upsert_knowledge_node",
        "client_change_id": f"demo-seed:{uid}:{sid}:{key}",
        "knowledge": {"title": title, "summary": summary, "aliases": [title]},
        "mastery": mastery,
        "confidence": confidence,
    }
    if parent_title:
        change["parent_candidate"] = {"title": parent_title}
    return change


def _submit_study_batch(uid: int, sid: int, subject_title: str, changes: list[dict], *, timestamp: int, phase: str) -> dict:
    result = sgt.submit_learning_tree_changes(
        uid, sid, changes,
        source={"kind": "demo_student_seed", "phase": phase},
        timestamp=timestamp, subject_title=subject_title,
    )
    assert result["success"] is True
    return result


def _submit_study_batches_for_demo(uid: int, sid: int, subject_title: str, batches: list[dict], now_ts: int) -> dict:
    submit_results = []
    for batch in batches:
        ts = now_ts + int(batch.get("timestamp_offset_seconds") or 0)
        changes = [
            _study_change(
                uid, sid,
                str(c["key"]), str(c["title"]),
                signal=str(c["signal"]), summary=str(c["summary"]),
                confidence=float(c.get("confidence") or 0.9),
                parent_title=str(c.get("parent_title") or ""),
                delta=c.get("delta"),
            )
            for c in batch.get("changes") or []
        ]
        submit_results.append(
            _submit_study_batch(uid, sid, subject_title, changes, timestamp=ts, phase=str(batch["phase"]))
        )
    tree = sgt.get_student_learning_tree(uid, sid)
    features = sgt.get_learning_tree_features(uid, sid, stale_days=14)
    return {"tree": tree, "features": features, "submit_batches": submit_results, "node_count": len((tree.get("tree") or {}).get("nodes") or [])}


# ═══════════════════════════════════════════════════════════════════════════════
# Study graph batch data
# ═══════════════════════════════════════════════════════════════════════════════

MEDIUM_STUDY_BATCHES = [
    {
        "phase": "mastered_foundations",
        "timestamp_offset_seconds": -1814400,  # 21 days ago
        "changes": [
            {"key": "bigdata_basics", "title": "大数据基础", "signal": "mastered", "summary": "对大数据基本概念、4V特征有稳定理解"},
            {"key": "hdfs_basics", "title": "HDFS 基础", "signal": "mastered", "summary": "掌握HDFS架构、NameNode/DataNode职责和读写流程"},
        ],
    },
    {
        "phase": "data_perception_etl",
        "timestamp_offset_seconds": -1209600,  # 14 days ago
        "changes": [
            {"key": "data_perception", "title": "数据感知", "signal": "mastered", "summary": "理解多源异构数据特征和数据感知流程"},
            {"key": "etl_process", "title": "ETL过程", "signal": "practiced", "summary": "掌握数据抽取、转换、装载的基本方法和开源工具"},
        ],
    },
    {
        "phase": "hbase_start",
        "timestamp_offset_seconds": -345600,  # 4 days ago
        "changes": [
            {"key": "hbase_basics", "title": "HBase 基础", "signal": "struggled", "summary": "对HBase数据模型和与HDFS的关系感到困惑"},
        ],
    },
    {
        "phase": "hbase_model",
        "timestamp_offset_seconds": -259200,  # 3 days ago
        "changes": [
            {"key": "hbase_data_model", "title": "HBase 数据模型", "signal": "learned", "summary": "开始理解HBase的表、行键、列族和Region概念", "parent_title": "HBase 基础"},
        ],
    },
    {
        "phase": "hdfs_detail",
        "timestamp_offset_seconds": -1728000,  # 20 days ago
        "changes": [
            {"key": "hdfs_read_write", "title": "HDFS读写流程", "signal": "practiced", "summary": "熟悉HDFS数据写入pipeline和读取就近原则"},
        ],
    },
]

HIGH_STUDY_BATCHES = [
    {
        "phase": "stale_history",
        "timestamp_offset_seconds": -5184000,  # 60 days ago
        "changes": [
            {"key": "mapreduce_basics", "title": "MapReduce 基础", "signal": "mastered", "summary": "较早学习过MapReduce计算模型"},
        ],
    },
    {
        "phase": "mastered_foundations_0",
        "timestamp_offset_seconds": -4838400,  # 56 days ago
        "changes": [
            {"key": "bigdata_basics", "title": "大数据基础", "signal": "mastered", "summary": "多次学习与测验后已较稳定"},
            {"key": "data_perception", "title": "数据感知", "signal": "mastered", "summary": "对数据源类型和多源异构特征有清晰理解"},
        ],
    },
    {
        "phase": "mastered_foundations_1",
        "timestamp_offset_seconds": -4233600,  # 49 days ago
        "changes": [
            {"key": "etl_process", "title": "ETL过程", "signal": "mastered", "summary": "掌握数据抽取、转换、装载完整流程"},
            {"key": "hdfs_basics", "title": "HDFS 基础", "signal": "mastered", "summary": "已通过多次练习巩固HDFS架构和读写流程"},
        ],
    },
    {
        "phase": "mastered_foundations_2",
        "timestamp_offset_seconds": -3628800,  # 42 days ago
        "changes": [
            {"key": "hbase_basics", "title": "HBase 基础", "signal": "mastered", "summary": "对HBase分布式数据库基础概念和架构有较好掌握"},
            {"key": "nosql_basics", "title": "非关系型数据库基础", "signal": "mastered", "summary": "理解NoSQL与关系型数据库的对比和适用场景"},
        ],
    },
    {
        "phase": "active_step_foundation",
        "timestamp_offset_seconds": -1728000,  # 20 days ago
        "stale_timestamp_offset_seconds": -2592000,  # 30 days ago (stale)
        "changes": [
            {"key": "hbase_data_model", "title": "HBase 数据模型", "signal": "mastered", "summary": "理解HBase表、行键、列族、时间戳、Region等核心概念", "parent_title": "HBase 基础"},
        ],
    },
    {
        "phase": "rowkey_region_branch",
        "timestamp_offset_seconds": -1209600,  # 14 days ago
        "changes": [
            {"key": "hbase_rowkey", "title": "HBase RowKey 设计", "signal": "learned", "summary": "能理解部分排序与定位逻辑，但对热点问题认识不足", "parent_title": "HBase 数据模型"},
            {"key": "region_split", "title": "Region 划分", "signal": "learned", "summary": "了解Region是HBase负载均衡的基本单位", "parent_title": "HBase 数据模型"},
        ],
    },
    {
        "phase": "hotspot_branch",
        "timestamp_offset_seconds": -864000,  # 10 days ago
        "changes": [
            {"key": "rowkey_hotspot", "title": "RowKey 热点", "signal": "struggled", "summary": "单调递增行键导致写入热点，对规避策略理解不足", "parent_title": "HBase RowKey 设计"},
        ],
    },
    {
        "phase": "mitigation_branch",
        "timestamp_offset_seconds": -604800,  # 7 days ago
        "changes": [
            {"key": "presplitting", "title": "预分区", "signal": "struggled", "summary": "预分区边界估算和热点缓解理解不足", "parent_title": "Region 划分"},
            {"key": "salt_prefix", "title": "加盐前缀", "signal": "learned", "summary": "开始理解前缀打散写入以缓解热点", "parent_title": "RowKey 热点"},
            {"key": "hash_prefix", "title": "散列前缀", "signal": "learned", "summary": "了解散列前缀降低集中写入风险的机制", "parent_title": "RowKey 热点"},
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4: Resource generation
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_demo_resource(user_id: int, syllabus_id: int, step: dict, graph_name: str, resource_type: str) -> dict:
    topic = step.get("title") or step.get("node_id") or "current learning step"
    outcomes = step.get("outcomes") if isinstance(step.get("outcomes"), list) else []
    result = generate_resources_from_request({
        "user_id": user_id,
        "syllabus_id": syllabus_id,
        "question": f"请为 {topic} 生成学习资料，帮助学生深入理解并完成练习。",
        "topic": topic,
        "learning_objectives": outcomes,
        "resource_types": [resource_type],
        "graph_name": graph_name,
        "generation_requirements": {},
    })
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5: Summary output
# ═══════════════════════════════════════════════════════════════════════════════

def _write_demo_summary_entry(entry: dict) -> None:
    DEMO_SUMMARY_ROOT.mkdir(parents=True, exist_ok=True)
    summary_path = DEMO_SUMMARY_ROOT / "summary.json"
    existing: list[dict] = []
    if summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            existing = []
    # dedupe by level — keep latest
    existing = [e for e in existing if e.get("level") != entry["level"]]
    existing.append(entry)
    existing.sort(key=lambda e: e.get("created_at", 0))
    summary_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Test functions
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_low_student(monkeypatch, demo_db_env):
    """Low-progress student: profile only, no plan/tree/resources."""
    user, syllabus, _relation = demo_db_env
    now_ts = int(time.time())
    level = LEVEL_LOW
    user.user_name = f"demo_{level}_{uuid.uuid4().hex[:8]}"
    user.email = f"{user.user_name}@lianjue.example.com"
    db.session.commit()  # persist rename to DB

    records = _build_profile_input_records(level, now_ts)
    profile = lpt.get_or_build_learning_profile(
        user.user_id, syllabus.syllabus_id,
        refresh_profile=True,
        dialogue_text=records["dialogue_text"],
        learning_goal=records["learning_goal"],
        learning_records=records["learning_records"],
        answer_records=records["answer_records"],
        resource_usage=records["resource_usage"],
    )
    assert isinstance(profile, dict), f"profile must be dict, got {type(profile)}"
    persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    assert isinstance(persisted, dict) and persisted.get("profile_saved") is True

    _write_demo_summary_entry({
        "level": level, "user_id": user.user_id, "user_name": user.user_name,
        "syllabus_id": syllabus.syllabus_id, "password": DEMO_PASSWORD,
        "profile_path": persisted.get("profile_path"),
        "learning_plan_id": None, "recommendation_snapshot_id": None,
        "study_graph_node_count": None, "generated_resource_id": None,
        "current_step_title": None, "created_at": now_ts,
    })


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_medium_student(monkeypatch, demo_db_env):
    """Medium-progress student: profile + plan + study graph + documents resource."""
    user, syllabus, _relation = demo_db_env
    now_ts = int(time.time())
    level = LEVEL_MEDIUM
    user.user_name = f"demo_{level}_{uuid.uuid4().hex[:8]}"
    user.email = f"{user.user_name}@lianjue.example.com"
    db.session.commit()
    graph_name = _graph_name()

    # Phase 1: Profile
    records = _build_profile_input_records(level, now_ts)
    profile = lpt.get_or_build_learning_profile(
        user.user_id, syllabus.syllabus_id, refresh_profile=True,
        dialogue_text=records["dialogue_text"], learning_goal=records["learning_goal"],
        learning_records=records["learning_records"], answer_records=records["answer_records"],
        resource_usage=records["resource_usage"],
    )
    assert isinstance(profile, dict)
    persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    assert isinstance(persisted, dict) and persisted.get("profile_saved") is True

    # Phase 2: Recommendation + Plan
    rec_result = _run_recommendation_for_demo(
        user.user_id, syllabus.syllabus_id, graph_name,
        goals=["分布式数据库中典型技术HBase", "HBase"],
        learning_goal=records["learning_goal"],
        question="我想深入学习HBase分布式数据库的核心概念和应用。",
    )
    assert rec_result["recommendation"] is not None, f"Recommendation failed: {rec_result.get('error')}"
    recommendation = rec_result["recommendation"]

    # Derive active step from best_path (no auto-accept — demo users see candidate selection)
    best_path = recommendation.get("best_path") if isinstance(recommendation, dict) else {}
    path_node_ids = best_path.get("path") if isinstance(best_path, dict) else []
    graph_nodes = recommendation.get("graph", {}).get("nodes") if isinstance(recommendation, dict) else []
    node_by_id = {n.get("id"): n for n in (graph_nodes or []) if isinstance(n, dict)}
    first_node = node_by_id.get(path_node_ids[0]) if path_node_ids else None
    active_step = {
        "step_id": "seed-step-0",
        "node_id": path_node_ids[0] if path_node_ids else "",
        "title": (first_node.get("title") if isinstance(first_node, dict) else "") or (path_node_ids[0] if path_node_ids else ""),
        "outcomes": (first_node.get("outcomes") if isinstance(first_node, dict) else []) or [],
        "order_index": 0,
        "status": "active",
    } if path_node_ids else {}
    assert active_step, "No active step derived from best_path"

    # Phase 3: Study graph
    graph_result = _submit_study_batches_for_demo(
        user.user_id, syllabus.syllabus_id, syllabus.title or "大数据概论",
        MEDIUM_STUDY_BATCHES, now_ts,
    )
    assert graph_result["node_count"] >= 5, f"Expected >=5 nodes, got {graph_result['node_count']}"

    # Phase 4: Resource
    resource_result = _generate_demo_resource(
        user.user_id, syllabus.syllabus_id, active_step, graph_name, "documents",
    )
    assert resource_result.get("success") is True, f"Resource generation failed: {resource_result.get('error_message')}"
    resource_id = (resource_result.get("resources") or [{}])[0].get("resource_id") if resource_result.get("resources") else None

    snapshot_id = (rec_result.get("snapshot") or {}).get("recommendation_id")

    _write_demo_summary_entry({
        "level": level, "user_id": user.user_id, "user_name": user.user_name,
        "syllabus_id": syllabus.syllabus_id, "password": DEMO_PASSWORD,
        "profile_path": persisted.get("profile_path"),
        "learning_plan_id": None,
        "recommendation_snapshot_id": snapshot_id,
        "study_graph_node_count": graph_result["node_count"],
        "generated_resource_id": resource_id,
        "current_step_title": active_step.get("title"),
        "created_at": now_ts,
    })


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_seed_demo_high_student(monkeypatch, demo_db_env):
    """High-progress student: profile + plan + deep study graph + mindmap resource."""
    user, syllabus, _relation = demo_db_env
    now_ts = int(time.time())
    level = LEVEL_HIGH
    user.user_name = f"demo_{level}_{uuid.uuid4().hex[:8]}"
    user.email = f"{user.user_name}@lianjue.example.com"
    db.session.commit()
    graph_name = _graph_name()

    # Phase 1: Profile
    records = _build_profile_input_records(level, now_ts)
    profile = lpt.get_or_build_learning_profile(
        user.user_id, syllabus.syllabus_id, refresh_profile=True,
        dialogue_text=records["dialogue_text"], learning_goal=records["learning_goal"],
        learning_records=records["learning_records"], answer_records=records["answer_records"],
        resource_usage=records["resource_usage"],
    )
    assert isinstance(profile, dict)
    persisted = lpt.get_persisted_learning_profile(user.user_id, syllabus.syllabus_id)
    assert isinstance(persisted, dict) and persisted.get("profile_saved") is True

    # Phase 2: Recommendation + Plan
    rec_result = _run_recommendation_for_demo(
        user.user_id, syllabus.syllabus_id, graph_name,
        goals=["HBase RowKey 设计", "预分区策略", "RowKey 热点规避"],
        learning_goal=records["learning_goal"],
        question="我已经学完了大部分核心课程，想针对RowKey热点和预分区策略进行复习巩固。",
    )
    assert rec_result["recommendation"] is not None, f"Recommendation failed: {rec_result.get('error')}"
    recommendation = rec_result["recommendation"]

    # Derive active step from best_path (no auto-accept — demo users see candidate selection)
    best_path = recommendation.get("best_path") if isinstance(recommendation, dict) else {}
    path_node_ids = best_path.get("path") if isinstance(best_path, dict) else []
    graph_nodes = recommendation.get("graph", {}).get("nodes") if isinstance(recommendation, dict) else []
    node_by_id = {n.get("id"): n for n in (graph_nodes or []) if isinstance(n, dict)}
    first_node = node_by_id.get(path_node_ids[0]) if path_node_ids else None
    active_step = {
        "step_id": "seed-step-0",
        "node_id": path_node_ids[0] if path_node_ids else "",
        "title": (first_node.get("title") if isinstance(first_node, dict) else "") or (path_node_ids[0] if path_node_ids else ""),
        "outcomes": (first_node.get("outcomes") if isinstance(first_node, dict) else []) or [],
        "order_index": 0,
        "status": "active",
    } if path_node_ids else {}
    assert active_step, "No active step derived from best_path"

    # Phase 3: Study graph
    graph_result = _submit_study_batches_for_demo(
        user.user_id, syllabus.syllabus_id, syllabus.title or "大数据概论",
        HIGH_STUDY_BATCHES, now_ts,
    )
    assert graph_result["node_count"] >= 10, f"Expected >=10 nodes, got {graph_result['node_count']}"

    # Phase 4: Resource — mindmap for review
    resource_result = _generate_demo_resource(
        user.user_id, syllabus.syllabus_id, active_step, graph_name, "mindmap",
    )
    assert resource_result.get("success") is True, f"Resource generation failed: {resource_result.get('error_message')}"
    resource_id = (resource_result.get("resources") or [{}])[0].get("resource_id") if resource_result.get("resources") else None

    snapshot_id = (rec_result.get("snapshot") or {}).get("recommendation_id")

    _write_demo_summary_entry({
        "level": level, "user_id": user.user_id, "user_name": user.user_name,
        "syllabus_id": syllabus.syllabus_id, "password": DEMO_PASSWORD,
        "profile_path": persisted.get("profile_path"),
        "learning_plan_id": None,
        "recommendation_snapshot_id": snapshot_id,
        "study_graph_node_count": graph_result["node_count"],
        "generated_resource_id": resource_id,
        "current_step_title": active_step.get("title"),
        "created_at": now_ts,
    })
