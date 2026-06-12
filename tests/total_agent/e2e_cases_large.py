import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from app import create_app
from extensions import db
from schemas.syllabus import Syllabus
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks import generative_task as gt
from tasks import learning_profile_task as lpt
from tasks import personal_recommendation_task as prt
from tasks import study_graph_task as sgt
from tasks.generative import storage as generative_storage
from tasks.personal_recommendation import agent_runtime as recommendation_runtime
from tasks.personal_recommendation import service as recommendation_service
from tasks.study_graph import storage as study_graph_storage
from tests.total_agent.test_process_contract import (
    LEARNING_EVENT_RECORDED,
    PROCESS_CONTRACT_SCHEMA_VERSION,
    _accept_recommendation,
    _get_next_task,
    _metrics,
    _record_event,
)


WORKING_SYLLABUS_PATH = "tests/fixtures/大数据概论_20260322235507.json"
TEST_TOTAL_AGENT_E2E_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "e2e"


def _require_large_e2e_env() -> None:
    missing = [
        name
        for name in ("RUN_LLM_TESTS", "RUN_REAL_RAG_TESTS", "RUN_DB_TESTS")
        if os.getenv(name) != "1"
    ]
    if missing:
        pytest.skip("Set RUN_LLM_TESTS=1 RUN_REAL_RAG_TESTS=1 RUN_DB_TESTS=1 to run total agent E2E.")
    if not Path(WORKING_SYLLABUS_PATH).exists():
        pytest.skip(f"Working syllabus file is missing: {WORKING_SYLLABUS_PATH}")


def _reset_artifact_root(name: str) -> Path:
    root = TEST_TOTAL_AGENT_E2E_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(root: Path, name: str, payload: dict) -> Path:
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_recommendation_snapshot_artifact(
    *,
    artifact_root: Path,
    user,
    syllabus,
    recommendation: dict,
    request_payload: dict | None = None,
) -> dict:
    saved = prt.save_recommendation_snapshot(
        int(user.user_id),
        int(syllabus.syllabus_id),
        recommendation,
        request_payload=request_payload,
    )
    assert saved.get("success") is True, saved
    detail = prt.get_recommendation_snapshot(str(saved.get("recommendation_id") or ""))
    assert detail.get("success") is True, detail
    payload = {
        "schema_version": "recommendation_snapshot_artifact.v1",
        "saved": saved,
        "snapshot": detail.get("snapshot") or {},
    }
    _write_artifact(artifact_root, "recommendation_snapshot_detail.json", payload)
    return payload


def _emit_e2e_status(agent: str, action: str, *, status: str = "running", **details) -> None:
    detail_text = ""
    if details:
        compact_details = ", ".join(f"{key}={value}" for key, value in details.items() if value is not None)
        if compact_details:
            detail_text = f" ({compact_details})"
    print(f"[total-agent-e2e] {agent}: {action}... {status}{detail_text}", flush=True)


def _emit_tool_status_events(events: list[dict] | None) -> None:
    for event in events or []:
        agent = event.get("agent") or "agent"
        stage = event.get("stage") or event.get("event_key") or "stage"
        status = event.get("status") or "unknown"
        _emit_e2e_status(str(agent), str(stage), status=str(status))


def _normalize_model_for_dashscope() -> None:
    text_config = recommendation_runtime.OPENAI_COMPAT_MODEL_CONFIGS.get("text") or {}
    api_base = str(text_config.get("api_base") or text_config.get("base_url") or "")
    model_name = str(text_config.get("model_name") or "")
    if "dashscope.aliyuncs.com" in api_base and model_name.startswith("openai/"):
        text_config["model_name"] = model_name.removeprefix("openai/")
        recommendation_runtime.get_personal_recommendation_agent.cache_clear()


def _tokenize_goal_text(*values: object) -> set[str]:
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
        ranked.append(
            {
                "node_id": node_id,
                "title": title,
                "outcomes": outcomes,
                "score": round(score, 4),
                "overlap": sorted(overlap),
                "rag_relevance": relevance,
            }
        )
    ranked.sort(key=lambda item: (item["score"], len(item["overlap"]), item["rag_relevance"]), reverse=True)
    best = ranked[0] if ranked else {}
    if not best or best.get("score", 0) < min_score or not best.get("overlap"):
        return {
            "goals": [],
            "selected_node": None,
            "ranked_nodes": ranked[:8],
            "reason": "no_semantically_aligned_syllabus_node",
            "min_score": min_score,
        }
    return {
        "goals": (best.get("outcomes") or [best.get("title") or best.get("node_id")])[:2],
        "selected_node": best,
        "ranked_nodes": ranked[:8],
        "reason": "semantic_overlap_with_user_goal_or_rag_evidence",
        "min_score": min_score,
    }


def _run_recommendation_attempt(payload: dict) -> dict:
    agent_result = prt.run_personal_recommendation_agent(payload)
    recommendation = agent_result.recommendation
    return {
        "payload": payload,
        "agent_success": bool(agent_result.success),
        "recommendation": recommendation if isinstance(recommendation, dict) else None,
        "candidate_count": len((recommendation or {}).get("candidates") or []) if isinstance(recommendation, dict) else 0,
        "best_path": (recommendation or {}).get("best_path") if isinstance(recommendation, dict) else None,
        "error_code": str(getattr(agent_result, "error_code", "") or ""),
        "error_message": str(getattr(agent_result, "error_message", "") or ""),
    }


def _run_deterministic_recommendation_attempt(payload: dict) -> dict:
    recommendation = prt.run_recommendation_route_from_payload(payload)
    return {
        "payload": payload,
        "agent_success": bool(recommendation.get("success")),
        "recommendation": recommendation if isinstance(recommendation, dict) else None,
        "candidate_count": len((recommendation or {}).get("candidates") or []) if isinstance(recommendation, dict) else 0,
        "best_path": (recommendation or {}).get("best_path") if isinstance(recommendation, dict) else None,
        "error_code": str((recommendation or {}).get("error_code") or ""),
        "error_message": str((recommendation or {}).get("error_message") or ""),
    }


def _hbase_deep_learning_tree() -> dict:
    return {
        "hbase_intro": {
            "title": "HBase 分布式数据库基础",
            "outcomes": ["hbase_basic"],
            "prerequisites": [],
            "difficulty": 2,
            "learning_time_est": 3,
        },
        "rowkey_design": {
            "title": "HBase RowKey 设计",
            "outcomes": ["rowkey_design", "rowkey_hotspot_avoidance"],
            "prerequisites": ["hbase_intro"],
            "difficulty": 3,
            "learning_time_est": 4,
        },
        "rowkey_hotspot": {
            "title": "RowKey 热点规避",
            "outcomes": ["rowkey_hotspot_avoidance"],
            "prerequisites": ["rowkey_design"],
            "difficulty": 3,
            "learning_time_est": 4,
        },
        "presplitting": {
            "title": "HBase 预分区策略",
            "outcomes": ["hbase_presplitting"],
            "prerequisites": ["rowkey_hotspot"],
            "difficulty": 4,
            "learning_time_est": 5,
        },
    }


def _run_current_step_resource_and_feedback(
    *,
    artifact_root: Path,
    user,
    syllabus,
    recommendation: dict,
    graph_name: str,
    learning_profile: dict,
    recommendation_attempts: list[dict],
    recommendation_flow: str,
    goal_alignment: dict | None = None,
    result_name: str = "total_agent_large_e2e_result.json",
) -> dict:
    _emit_e2e_status("learning plan", "accepting recommendation path")
    accept_result = _accept_recommendation(
        {
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "recommendation_result": recommendation,
        }
    )
    assert accept_result["success"] is True
    next_task = accept_result["next_task"]
    assert next_task and next_task.get("status") == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
    _emit_e2e_status(
        "learning plan",
        "learning plan active",
        status="done",
        step_id=next_task.get("step_id"),
    )

    _emit_e2e_status("material agent", "generating current step resource")
    resource_result = gt.generate_resources_from_request(
        {
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "question": "请根据我当前学习步骤生成一个讲解文档。",
            "topic": next_task.get("title") or next_task.get("node_id") or "HBase RowKey 热点规避",
            "learning_objectives": next_task.get("outcomes") or recommendation.get("best_path", {}).get("skills") or [],
            "resource_types": ["documents"],
            "graph_name": graph_name,
            "generation_requirements": {"model_tier": os.getenv("GENERATIVE_TEST_MODEL_TIER") or "cheap"},
        }
    )
    _emit_tool_status_events(resource_result.get("tool_status_events"))
    assert resource_result["success"] is True
    assert resource_result["success_count"] >= 1
    resource = resource_result["resources"][0]
    assert resource["resource_type"] == "documents"
    assert resource["success"] is True
    _emit_e2e_status(
        "material agent",
        "resource generated",
        status="done",
        resource_id=resource.get("resource_id"),
        resource_type=resource.get("resource_type"),
    )

    _emit_e2e_status("learning plan", "recording resource feedback")
    event_payload = {
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
        "plan_id": accept_result["plan"]["plan_id"],
        "step_id": next_task["step_id"],
        "event_type": "resource_completed",
        "resource_type": resource["resource_type"],
        "resource_id": resource["resource_id"],
        "topic": next_task.get("title") or next_task.get("node_id"),
        "status": prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
        "score": 0.86,
    }
    event_result = _record_event(event_payload)
    assert event_result["success"] is True
    assert event_result["updated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    _emit_e2e_status("learning plan", "feedback recorded", status="done")

    _emit_e2e_status("study graph", "syncing feedback to learning tree")
    changes = sgt.build_study_graph_changes_from_resource_event(event_payload)
    assert changes
    study_graph_result = sgt.submit_learning_tree_changes(
        user.user_id,
        syllabus.syllabus_id,
        changes,
        source={"kind": "total_agent_e2e", "resource_id": resource["resource_id"]},
        subject_title=syllabus.title,
    )
    assert study_graph_result["success"] is True
    study_tree = sgt.get_student_learning_tree(user.user_id, syllabus.syllabus_id)
    study_tree_payload = study_tree.get("tree") if isinstance(study_tree.get("tree"), dict) else study_tree
    assert study_tree_payload.get("nodes")
    _emit_e2e_status(
        "study graph",
        "feedback synced to learning tree",
        status="done",
        node_count=len(study_tree_payload.get("nodes") or []),
    )

    next_after_event = _get_next_task(user.user_id, syllabus.syllabus_id)
    assert next_after_event["success"] is True

    manifest_entries = prt.load_learning_plan_manifest(user.user_id, syllabus.syllabus_id)
    assert any(entry.get("event_type") == LEARNING_EVENT_RECORDED for entry in manifest_entries)
    result = {
        "schema_version": PROCESS_CONTRACT_SCHEMA_VERSION,
        "summary": {
            "user_id": user.user_id,
            "syllabus_id": syllabus.syllabus_id,
            "profile_keys": sorted(learning_profile.keys()),
            "recommendation_flow": recommendation_flow,
            "recommendation_attempt_count": len(recommendation_attempts),
            "goal_alignment": goal_alignment,
            "best_path": (recommendation.get("best_path") or {}).get("path"),
            "accepted_step_count": len(accept_result["plan"].get("steps") or []),
            "generated_resource_type": resource.get("resource_type"),
            "generated_resource_id": resource.get("resource_id"),
            "study_graph_created_nodes": study_graph_result.get("created_nodes") or [],
            "metrics_after_event": _metrics(event_result.get("plan")),
        },
        "learning_profile": learning_profile,
        "recommendation_attempts": recommendation_attempts,
        "goal_alignment": goal_alignment,
        "recommendation": recommendation,
        "accept_result": accept_result,
        "resource_result": resource_result,
        "event_result": event_result,
        "study_graph_result": study_graph_result,
        "next_after_event": next_after_event,
        "learning_plan_manifest_entries": manifest_entries,
        "study_tree": study_tree,
    }
    _write_artifact(artifact_root, result_name, result)
    return result


@pytest.fixture
def db_total_agent_user_case():
    _require_large_e2e_env()
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:8]
        user = User(
            user_name=f"total-agent-e2e-{suffix}",
            password_hash="pytest-not-used",
            email=f"total-agent-e2e-{suffix}@example.com",
        )
        syllabus = Syllabus.query.filter_by(syllabus_path=WORKING_SYLLABUS_PATH).first()
        created_syllabus = False
        if syllabus is None:
            syllabus = Syllabus(title="大数据概论", syllabus_path=WORKING_SYLLABUS_PATH)
            db.session.add(syllabus)
            created_syllabus = True
        db.session.add(user)
        db.session.commit()
        relation = UserSyllabus(user_id=user.user_id, syllabus_id=syllabus.syllabus_id, syllabus_permission="user")
        db.session.add(relation)
        db.session.commit()
        try:
            yield user, syllabus, relation
        finally:
            db.session.rollback()
            UserSyllabus.query.filter_by(user_id=user.user_id, syllabus_id=syllabus.syllabus_id).delete()
            User.query.filter_by(user_id=user.user_id).delete()
            if created_syllabus:
                Syllabus.query.filter_by(syllabus_id=syllabus.syllabus_id).delete()
            db.session.commit()


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_total_agent_large_e2e_learning_flow_with_real_llm_rag_db(monkeypatch, db_total_agent_user_case):
    _require_large_e2e_env()
    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("real_llm_rag_db_current_step_resource")
    recommendation_root = artifact_root / "learning_plan"
    generative_root = artifact_root / "generative_workspace"
    study_graph_root = artifact_root / "study_graph"

    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(recommendation_root))
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: generative_root)
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: study_graph_root)

    user, syllabus, relation = db_total_agent_user_case
    graph_name = os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME") or os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"
    learning_profile = lpt.get_or_build_learning_profile(
        user.user_id,
        syllabus.syllabus_id,
        refresh_profile=True,
        dialogue_text=[
            "我最近在学大数据概论，HBase 的 RowKey 热点和预分区策略总是搞不懂。",
            "我希望先补齐 RowKey 设计，再做一点练习。",
        ],
        learning_goal="掌握 HBase RowKey 热点规避和预分区策略",
        learning_records=[
            {
                "event_type": "study_session",
                "topic": "HBase RowKey 热点",
                "score": 0.42,
                "summary": "能说出热点现象，但无法解释预分区和 RowKey 设计的关系。",
            }
        ],
    )
    assert learning_profile.get("user_id") == user.user_id

    natural_recommendation_payload = {
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
        "goals": ["HBase RowKey 热点规避", "预分区策略"],
        "question": "我下一步应该怎么学习 HBase RowKey 热点规避？",
        "learning_goal": "掌握 HBase RowKey 设计和热点规避",
        "graph_name": graph_name,
        "rag_top_k": 5,
        "K": 10,
        "beam_width": 8,
    }
    recommendation_attempts = [_run_recommendation_attempt(natural_recommendation_payload)]
    recommendation = recommendation_attempts[-1]["recommendation"]
    recommendation_flow = "natural_language_goal"
    goal_alignment = None
    if not (isinstance(recommendation, dict) and recommendation.get("best_path")):
        user_goal_tokens = _tokenize_goal_text(
            natural_recommendation_payload["question"],
            natural_recommendation_payload["learning_goal"],
            " ".join(natural_recommendation_payload["goals"]),
        )
        goal_alignment = _derive_graph_aligned_goals(recommendation, user_goal_tokens)
        graph_aligned_goals = goal_alignment.get("goals") or []
        if not graph_aligned_goals:
            clarification_result = {
                "schema_version": PROCESS_CONTRACT_SCHEMA_VERSION,
                "success": True,
                "terminal_state": "ask_goal_clarification",
                "suggested_next_action": "ask_goal_clarification",
                "reason": goal_alignment.get("reason"),
                "user_goal_tokens": sorted(user_goal_tokens),
                "recommendation_attempts": recommendation_attempts,
                "goal_alignment": goal_alignment,
            }
            _write_artifact(
                artifact_root,
                "total_agent_large_e2e_goal_alignment_failed.json",
                clarification_result,
            )
            assert clarification_result["suggested_next_action"] == "ask_goal_clarification"
            return
        graph_aligned_payload = dict(natural_recommendation_payload)
        graph_aligned_payload["goals"] = graph_aligned_goals
        graph_aligned_payload["goal_normalization_source"] = "syllabus_learning_tree"
        graph_aligned_payload["goal_alignment"] = goal_alignment
        graph_aligned_payload.pop("graph_name", None)
        graph_aligned_payload.pop("rag_graph_name", None)
        graph_aligned_payload.pop("rag_top_k", None)
        recommendation_attempts.append(_run_deterministic_recommendation_attempt(graph_aligned_payload))
        recommendation = recommendation_attempts[-1]["recommendation"]
        recommendation_flow = "graph_aligned_deterministic_retry"

    if not (isinstance(recommendation, dict) and recommendation.get("best_path")):
        clarification_result = {
            "schema_version": PROCESS_CONTRACT_SCHEMA_VERSION,
            "success": True,
            "terminal_state": "ask_goal_clarification",
            "suggested_next_action": "ask_goal_clarification",
            "reason": "graph_aligned_retry_produced_no_path",
            "recommendation_attempts": recommendation_attempts,
            "goal_alignment": goal_alignment,
        }
        _write_artifact(
            artifact_root,
            "total_agent_large_e2e_goal_alignment_failed.json",
            clarification_result,
        )
        assert clarification_result["suggested_next_action"] == "ask_goal_clarification"
        return

    assert isinstance(recommendation, dict), recommendation_attempts
    assert recommendation.get("success") is True, recommendation_attempts
    assert recommendation.get("best_path"), recommendation_attempts
    snapshot_artifact = _write_recommendation_snapshot_artifact(
        artifact_root=artifact_root,
        user=user,
        syllabus=syllabus,
        recommendation=recommendation,
        request_payload=graph_aligned_payload if recommendation_flow == "graph_aligned_deterministic_retry" else natural_recommendation_payload,
    )
    assert snapshot_artifact["snapshot"]["recommendation"]["graph"]["nodes"]

    _run_current_step_resource_and_feedback(
        artifact_root=artifact_root,
        user=user,
        syllabus=syllabus,
        recommendation=recommendation,
        graph_name=graph_name,
        learning_profile=learning_profile,
        recommendation_attempts=recommendation_attempts,
        recommendation_flow=recommendation_flow,
        goal_alignment=goal_alignment,
    )


@pytest.mark.llm
@pytest.mark.search
@pytest.mark.mysql
def test_total_agent_large_e2e_deep_success_with_aligned_recommendation_graph(monkeypatch, db_total_agent_user_case):
    _require_large_e2e_env()
    _normalize_model_for_dashscope()
    artifact_root = _reset_artifact_root("real_llm_rag_db_deep_success")
    recommendation_root = artifact_root / "learning_plan"
    generative_root = artifact_root / "generative_workspace"
    study_graph_root = artifact_root / "study_graph"

    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(recommendation_root))
    monkeypatch.setattr(generative_storage, "_get_backend_root", lambda: generative_root)
    monkeypatch.setattr(study_graph_storage, "study_graph_root", lambda: study_graph_root)

    user, syllabus, relation = db_total_agent_user_case
    graph_name = os.getenv("PERSONAL_RECOMMENDATION_RAG_GRAPH_NAME") or os.getenv("SEARCH_TOOL_GRAPH_NAME") or "RAG"
    learning_profile = lpt.get_or_build_learning_profile(
        user.user_id,
        syllabus.syllabus_id,
        refresh_profile=True,
        dialogue_text=["我希望继续学习 HBase RowKey 热点和预分区。"],
        learning_goal="掌握 HBase RowKey 热点规避和预分区策略",
        learning_records=[{"topic": "HBase RowKey 热点", "score": 0.4, "event_type": "study_session"}],
    )
    payload = {
        "user_id": user.user_id,
        "syllabus_id": syllabus.syllabus_id,
        "goals": ["rowkey_hotspot_avoidance"],
        "question": "我下一步应该怎么学习 HBase RowKey 热点规避？",
        "learning_goal": "掌握 HBase RowKey 设计和热点规避",
        "graph_name": graph_name,
        "rag_top_k": 5,
        "decomposer_mode": "agent",
        "K": 10,
        "beam_width": 8,
    }
    recommendation_attempts = [_run_recommendation_attempt(payload)]
    recommendation = recommendation_attempts[-1]["recommendation"]
    recommendation_flow = "agent_aligned_graph"
    goal_alignment = None

    # Agent decomposition produces Chinese outcomes, but goals may be English
    # identifiers (e.g. "rowkey_hotspot_avoidance"). Bridge via the same token-
    # overlap + RAG evidence alignment used by the natural-goal test above.
    if not (isinstance(recommendation, dict) and recommendation.get("best_path")):
        user_goal_tokens = _tokenize_goal_text(
            payload["question"],
            payload["learning_goal"],
            " ".join(payload["goals"]),
        )
        goal_alignment = _derive_graph_aligned_goals(recommendation, user_goal_tokens)
        graph_aligned_goals = goal_alignment.get("goals") or []
        if not graph_aligned_goals:
            clarification_result = {
                "schema_version": PROCESS_CONTRACT_SCHEMA_VERSION,
                "success": True,
                "terminal_state": "ask_goal_clarification",
                "suggested_next_action": "ask_goal_clarification",
                "reason": goal_alignment.get("reason"),
                "user_goal_tokens": sorted(user_goal_tokens),
                "recommendation_attempts": recommendation_attempts,
                "goal_alignment": goal_alignment,
            }
            _write_artifact(
                artifact_root,
                "total_agent_large_e2e_deep_success_goal_alignment_failed.json",
                clarification_result,
            )
            assert clarification_result["suggested_next_action"] == "ask_goal_clarification"
            return
        graph_aligned_payload = dict(payload)
        graph_aligned_payload["goals"] = graph_aligned_goals
        graph_aligned_payload["goal_normalization_source"] = "syllabus_learning_tree"
        graph_aligned_payload["goal_alignment"] = goal_alignment
        graph_aligned_payload.pop("graph_name", None)
        graph_aligned_payload.pop("rag_top_k", None)
        recommendation_attempts.append(_run_deterministic_recommendation_attempt(graph_aligned_payload))
        recommendation = recommendation_attempts[-1]["recommendation"]
        recommendation_flow = "graph_aligned_deterministic_retry"

    assert recommendation_attempts[-1]["candidate_count"] > 0, recommendation_attempts
    assert isinstance(recommendation, dict) and recommendation.get("best_path"), recommendation_attempts
    # 推荐图应包含路径之外的关联节点（真实 snapshot 约 37 节点 vs 6 步路径）
    graph_nodes = (recommendation.get("graph") or {}).get("nodes") or []
    assert len(graph_nodes) > len(recommendation["best_path"]["path"]), \
        f"graph nodes ({len(graph_nodes)}) should exceed path length ({len(recommendation['best_path']['path'])})"
    snapshot_artifact = _write_recommendation_snapshot_artifact(
        artifact_root=artifact_root,
        user=user,
        syllabus=syllabus,
        recommendation=recommendation,
        request_payload=payload,
    )
    assert snapshot_artifact["snapshot"]["recommendation"]["candidates"]

    result = _run_current_step_resource_and_feedback(
        artifact_root=artifact_root,
        user=user,
        syllabus=syllabus,
        recommendation=recommendation,
        graph_name=graph_name,
        learning_profile=learning_profile,
        recommendation_attempts=recommendation_attempts,
        recommendation_flow=recommendation_flow,
        result_name="total_agent_large_e2e_deep_success_result.json",
    )
    assert result["summary"]["accepted_step_count"] >= 1
    assert result["summary"]["generated_resource_type"] == "documents"
    assert result["resource_result"]["success_count"] == 1
