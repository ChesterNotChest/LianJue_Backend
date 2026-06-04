import json
import shutil
from pathlib import Path

from tasks import personal_recommendation_task as prt


TOTAL_AGENT_CONTEXT_CONTRACT_VERSION = "total_agent_context_contract.v1"
RESOURCE_STRATEGY_DEFAULT_TYPE = "documents"
ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "context_strategy_contract"


def _recommendation_fixture() -> dict:
    return {
        "success": True,
        "best_path": {
            "path": ["hbase_intro", "rowkey_design"],
            "skills": ["hbase", "rowkey", "hotspot"],
        },
        "candidates": [
            {
                "path": ["hbase_intro", "rowkey_design"],
                "skills": ["hbase", "rowkey", "hotspot"],
            }
        ],
        "graph": {
            "nodes": [
                {
                    "id": "hbase_intro",
                    "title": "HBase 基础",
                    "outcomes": ["hbase_intro"],
                },
                {
                    "id": "rowkey_design",
                    "title": "HBase RowKey 设计",
                    "outcomes": ["rowkey_design", "rowkey_hotspot_avoidance"],
                },
            ],
            "edges": [{"source": "hbase_intro", "target": "rowkey_design"}],
        },
    }


def _reset_roots(monkeypatch, tmp_path) -> Path:
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(tmp_path / "personal_recommendation"))
    if ARTIFACT_ROOT.exists():
        shutil.rmtree(ARTIFACT_ROOT)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_ROOT


def _accept_plan(user_id: int = 8, syllabus_id: int = 20) -> dict:
    result = prt.accept_recommendation_path(
        user_id=user_id,
        syllabus_id=syllabus_id,
        recommendation_result=_recommendation_fixture(),
        candidate_index=0,
    )
    assert result["success"] is True
    return result["plan"]


def _ordered_steps(plan: dict) -> list[dict]:
    steps = [dict(step) for step in plan.get("steps") or [] if isinstance(step, dict)]
    return sorted(steps, key=lambda item: int(item.get("order_index") or 0))


def _next_task(plan: dict) -> dict:
    for step in _ordered_steps(plan):
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE:
            return step
    for step in _ordered_steps(plan):
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_PENDING:
            return step
    return {}


def _normalize_profile_summary(value: dict | None) -> dict:
    profile = value if isinstance(value, dict) else {}
    return {
        "learning_goal": str(profile.get("learning_goal") or ""),
        "weak_points": list(profile.get("weak_points") or []),
        "preferred_formats": list(profile.get("preferred_formats") or []),
        "risk_level": str(profile.get("risk_level") or ""),
        "time_budget": profile.get("time_budget") if isinstance(profile.get("time_budget"), dict) else {},
        "updated_at": profile.get("updated_at"),
    }


def _normalize_study_graph_state(features: dict | None) -> dict:
    features = features if isinstance(features, dict) else {}
    return {
        "current_node_id": str(features.get("current_node_id") or ""),
        "completed_node_ids": list(features.get("completed_node_ids") or []),
        "weak_node_ids": list(features.get("weak_node_ids") or []),
        "mastered_node_ids": list(features.get("mastered_node_ids") or []),
        "recent_node_ids": list(features.get("recent_node_ids") or []),
        "stale_node_ids": list(features.get("stale_node_ids") or []),
        "warnings": list(features.get("warnings") or []),
    }


def _load_total_context_with_profile_and_graph(
    payload: dict,
    *,
    profile_loader,
    study_graph_loader,
) -> dict:
    user_id = int(payload["user_id"])
    syllabus_id = int(payload["syllabus_id"])
    warnings = []
    active_plan = prt.get_active_learning_plan(user_id, syllabus_id) or {}
    next_task = _next_task(active_plan)

    try:
        profile_summary = _normalize_profile_summary(profile_loader(payload))
    except Exception as exc:
        warnings.append(f"profile_read_failed:{exc}")
        profile_summary = _normalize_profile_summary({})

    try:
        study_graph_state = _normalize_study_graph_state(study_graph_loader(payload))
    except Exception as exc:
        warnings.append(f"study_graph_read_failed:{exc}")
        study_graph_state = _normalize_study_graph_state({})
        study_graph_state["warnings"].append(f"study_graph_read_failed:{exc}")

    return {
        "success": True,
        "schema_version": TOTAL_AGENT_CONTEXT_CONTRACT_VERSION,
        "active_plan": active_plan,
        "next_task": next_task,
        "profile_summary": profile_summary,
        "study_graph_state": study_graph_state,
        "warnings": warnings,
        "error_code": "",
        "error_message": "",
    }


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _text_contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(marker.lower() in lowered for marker in markers)


def _build_current_step_resource_strategy(context: dict) -> dict:
    message = str(context.get("message") or "")
    next_task = context.get("next_task") if isinstance(context.get("next_task"), dict) else {}
    profile = context.get("profile_summary") if isinstance(context.get("profile_summary"), dict) else {}
    graph_state = context.get("study_graph_state") if isinstance(context.get("study_graph_state"), dict) else {}
    explicit_resource_types = list(context.get("explicit_resource_types") or [])

    next_node_id = str(next_task.get("node_id") or "")
    outcomes = list(next_task.get("outcomes") or [])
    weak_points = list(profile.get("weak_points") or [])
    preferred_formats = list(profile.get("preferred_formats") or [])
    weak_node_ids = list(graph_state.get("weak_node_ids") or [])

    message_requests_practice = _text_contains_any(message, ("练习", "代码", "coding", "practice"))
    message_requests_review = _text_contains_any(message, ("复习", "总结", "梳理", "review"))
    matched_study_graph_weak_node = bool(next_node_id and next_node_id in weak_node_ids)
    matched_profile_weak_point = any(str(point) for point in weak_points)

    if explicit_resource_types:
        resource_types = explicit_resource_types
        reason = "user explicitly requested resource types"
    elif message_requests_practice and _text_contains_any(message, ("代码", "coding")):
        resource_types = ["coding_practice"]
        reason = "message requests coding practice"
    elif matched_profile_weak_point or matched_study_graph_weak_node:
        resource_types = _unique([RESOURCE_STRATEGY_DEFAULT_TYPE, "quiz", *preferred_formats])
        reason = "current step is weak and profile/study graph indicates targeted practice"
    elif message_requests_review:
        resource_types = ["mindmap"]
        reason = "message requests review or summary"
    else:
        resource_types = [RESOURCE_STRATEGY_DEFAULT_TYPE]
        reason = "default lightweight current-step resource"

    difficulty = "targeted" if matched_profile_weak_point or matched_study_graph_weak_node else "standard"
    if message_requests_review:
        difficulty = "review"

    return {
        "success": True,
        "schema_version": TOTAL_AGENT_CONTEXT_CONTRACT_VERSION,
        "resource_types": resource_types,
        "difficulty": difficulty,
        "knowledge_items": _unique([*outcomes, *weak_points]),
        "reason": reason,
        "strategy_signals": {
            "explicit_resource_types": bool(explicit_resource_types),
            "matched_profile_weak_point": matched_profile_weak_point,
            "matched_study_graph_weak_node": matched_study_graph_weak_node,
            "message_requests_practice": message_requests_practice,
            "message_requests_review": message_requests_review,
        },
        "error_code": "",
        "error_message": "",
    }


def test_context_contract_loads_profile_and_study_graph_state(monkeypatch, tmp_path):
    _reset_roots(monkeypatch, tmp_path)
    plan = _accept_plan()
    first_step = plan["steps"][0]
    prt.update_learning_plan_step_status(
        8,
        plan["plan_id"],
        first_step["step_id"],
        prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
        syllabus_id=20,
        sync_study_graph=False,
    )
    prt.update_learning_plan_step_status(
        8,
        plan["plan_id"],
        plan["steps"][1]["step_id"],
        prt.LEARNING_PLAN_STEP_STATUS_ACTIVE,
        syllabus_id=20,
        sync_study_graph=False,
    )

    context = _load_total_context_with_profile_and_graph(
        {"user_id": 8, "syllabus_id": 20, "message": "继续学习 RowKey"},
        profile_loader=lambda payload: {
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": ["RowKey 热点", "预分区"],
            "preferred_formats": ["documents", "quiz"],
            "risk_level": "medium",
            "time_budget": {"minutes_per_day": 30},
            "updated_at": 1760000000,
        },
        study_graph_loader=lambda payload: {
            "current_node_id": "rowkey_design",
            "completed_node_ids": ["hbase_intro"],
            "weak_node_ids": ["rowkey_design"],
            "recent_node_ids": ["hbase_intro"],
        },
    )

    assert context["success"] is True
    assert context["schema_version"] == TOTAL_AGENT_CONTEXT_CONTRACT_VERSION
    assert context["next_task"]["node_id"] == "rowkey_design"
    assert context["profile_summary"]["preferred_formats"] == ["documents", "quiz"]
    assert context["study_graph_state"]["weak_node_ids"] == ["rowkey_design"]
    assert context["warnings"] == []


def test_context_contract_profile_and_study_graph_failures_are_warnings(monkeypatch, tmp_path):
    _reset_roots(monkeypatch, tmp_path)
    _accept_plan()

    def fail_profile(payload):
        raise RuntimeError("profile unavailable")

    def fail_graph(payload):
        raise RuntimeError("graph unavailable")

    context = _load_total_context_with_profile_and_graph(
        {"user_id": 8, "syllabus_id": 20, "message": "继续学习"},
        profile_loader=fail_profile,
        study_graph_loader=fail_graph,
    )

    assert context["success"] is True
    assert context["next_task"]["node_id"] == "hbase_intro"
    assert context["profile_summary"]["weak_points"] == []
    assert any("profile_read_failed" in item for item in context["warnings"])
    assert any("study_graph_read_failed" in item for item in context["warnings"])


def test_resource_strategy_uses_weak_profile_and_graph_when_no_explicit_type():
    strategy = _build_current_step_resource_strategy(
        {
            "message": "继续学习，最好给我一点练习",
            "next_task": {
                "node_id": "rowkey_design",
                "outcomes": ["rowkey_design", "rowkey_hotspot_avoidance"],
            },
            "profile_summary": {
                "weak_points": ["RowKey 热点"],
                "preferred_formats": ["documents", "quiz"],
            },
            "study_graph_state": {"weak_node_ids": ["rowkey_design"]},
            "explicit_resource_types": [],
        }
    )

    assert strategy["resource_types"][:2] == ["documents", "quiz"]
    assert strategy["difficulty"] == "targeted"
    assert "RowKey 热点" in strategy["knowledge_items"]
    assert strategy["strategy_signals"]["matched_profile_weak_point"] is True
    assert strategy["strategy_signals"]["matched_study_graph_weak_node"] is True


def test_resource_strategy_respects_explicit_resource_types():
    strategy = _build_current_step_resource_strategy(
        {
            "message": "继续学习，最好给我一点练习",
            "next_task": {"node_id": "rowkey_design", "outcomes": ["rowkey_design"]},
            "profile_summary": {
                "weak_points": ["RowKey 热点"],
                "preferred_formats": ["quiz"],
            },
            "study_graph_state": {"weak_node_ids": ["rowkey_design"]},
            "explicit_resource_types": ["documents"],
        }
    )

    assert strategy["resource_types"] == ["documents"]
    assert strategy["strategy_signals"]["explicit_resource_types"] is True
    assert strategy["reason"] == "user explicitly requested resource types"


def test_resource_strategy_routes_coding_message_to_coding_practice():
    strategy = _build_current_step_resource_strategy(
        {
            "message": "给我一个代码练习 coding practice",
            "next_task": {"node_id": "rowkey_design", "outcomes": ["rowkey_design"]},
            "profile_summary": {"weak_points": [], "preferred_formats": ["documents"]},
            "study_graph_state": {"weak_node_ids": []},
            "explicit_resource_types": [],
        }
    )

    assert strategy["resource_types"] == ["coding_practice"]
    assert strategy["strategy_signals"]["message_requests_practice"] is True


def test_context_strategy_contract_writes_artifact(monkeypatch, tmp_path):
    artifact_root = _reset_roots(monkeypatch, tmp_path)
    plan = _accept_plan()
    context = _load_total_context_with_profile_and_graph(
        {"user_id": 8, "syllabus_id": 20, "message": "继续学习，最好给我一点练习"},
        profile_loader=lambda payload: {
            "learning_goal": "掌握 HBase RowKey 热点规避",
            "weak_points": ["RowKey 热点"],
            "preferred_formats": ["documents", "quiz"],
            "risk_level": "medium",
            "time_budget": {"minutes_per_day": 30},
        },
        study_graph_loader=lambda payload: {
            "current_node_id": "hbase_intro",
            "weak_node_ids": ["hbase_intro"],
        },
    )
    strategy = _build_current_step_resource_strategy(
        {
            "message": "继续学习，最好给我一点练习",
            "next_task": context["next_task"],
            "profile_summary": context["profile_summary"],
            "study_graph_state": context["study_graph_state"],
            "explicit_resource_types": [],
        }
    )

    artifact = {
        "test_name": "test_context_strategy_contract_writes_artifact",
        "schema_version": TOTAL_AGENT_CONTEXT_CONTRACT_VERSION,
        "plan_id": plan["plan_id"],
        "context": context,
        "strategy": strategy,
    }
    path = artifact_root / "context_strategy_contract_result.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    assert path.exists()
    assert strategy["resource_types"][:2] == ["documents", "quiz"]
