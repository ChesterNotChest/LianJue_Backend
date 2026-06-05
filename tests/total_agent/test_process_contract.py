import json
import shutil
from pathlib import Path
from typing import Any, Optional

from tasks import personal_recommendation_task as prt
from tasks.personal_recommendation import service as prs
from tasks.personal_recommendation.sample_data import goals, learning_tree, user_profile


TEST_TOTAL_AGENT_ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "total_agent" / "process_contract"
PROCESS_CONTRACT_SCHEMA_VERSION = "total_agent_process_contract.v1"
LEARNING_EVENT_RECORDED = "learning_event_recorded"
TOTAL_AGENT_SCHEMA_VERSION = "total_agent.v1"


def _reset_artifact_root(name: str) -> Path:
    root = TEST_TOTAL_AGENT_ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_artifact(root: Path, name: str, payload: dict) -> Path:
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _ok(payload: dict) -> dict:
    result = {
        "success": True,
        "schema_version": PROCESS_CONTRACT_SCHEMA_VERSION,
        "error_code": "",
        "error_message": "",
    }
    result.update(payload)
    return result


def _error(error_code: str, error_message: str, **extra: Any) -> dict:
    result = {
        "success": False,
        "schema_version": PROCESS_CONTRACT_SCHEMA_VERSION,
        "error_code": error_code,
        "error_message": error_message,
    }
    result.update(extra)
    return result


def _positive_int(value: Any) -> Optional[int]:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _steps(plan: Optional[dict]) -> list[dict]:
    if not isinstance(plan, dict):
        return []
    return [dict(step) for step in plan.get("steps") or [] if isinstance(step, dict)]


def _step_sort_key(step: dict) -> int:
    try:
        return int(step.get("order_index") or 0)
    except Exception:
        return 0


def _find_step(plan: Optional[dict], step_id: str | None) -> Optional[dict]:
    for step in _steps(plan):
        if str(step.get("step_id") or "") == str(step_id or ""):
            return step
    return None


def _find_next_step(plan: Optional[dict]) -> Optional[dict]:
    steps = sorted(_steps(plan), key=_step_sort_key)
    for step in steps:
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE:
            return step
    for step in steps:
        if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_PENDING:
            return step
    return None


def _metrics(plan: Optional[dict]) -> dict:
    steps = _steps(plan)
    total = len(steps)
    completed = sum(1 for step in steps if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED)
    skipped = sum(1 for step in steps if step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED)
    return {
        "total_steps": total,
        "completed_steps": completed,
        "skipped_steps": skipped,
        "remaining_steps": max(total - completed - skipped, 0),
        "progress_ratio": round(completed / total, 4) if total else 0.0,
    }


def _accept_recommendation(payload: dict) -> dict:
    user_id = _positive_int(payload.get("user_id"))
    if user_id is None:
        return _error("missing_fields", "missing user_id")
    syllabus_id = _positive_int(payload.get("syllabus_id")) if payload.get("syllabus_id") else None
    recommendation_result = payload.get("recommendation_result")
    if not isinstance(recommendation_result, dict):
        return _error("missing_recommendation", "missing recommendation_result")

    accept_result = prt.accept_recommendation_path(
        user_id=user_id,
        syllabus_id=syllabus_id,
        recommendation_result=recommendation_result,
        candidate_index=payload.get("candidate_index"),
    )
    if not accept_result.get("success"):
        return _error(
            accept_result.get("error_code") or "accept_failed",
            accept_result.get("error_message") or "failed to accept recommendation path",
            accept_result=accept_result,
        )
    plan = accept_result.get("plan") or prt.get_active_learning_plan(user_id, syllabus_id)
    return _ok({"plan": plan, "accept_result": accept_result, "next_task": _find_next_step(plan), "metrics": _metrics(plan)})


def _get_next_task(user_id: int, syllabus_id: Optional[int] = None) -> dict:
    normalized_user_id = _positive_int(user_id)
    if normalized_user_id is None:
        return _error("missing_fields", "missing user_id")
    normalized_syllabus_id = _positive_int(syllabus_id) if syllabus_id else None
    plan = prt.get_active_learning_plan(normalized_user_id, normalized_syllabus_id)
    if not plan:
        return _error("no_active_plan", "no active learning plan", plan=None, next_task=None)
    return _ok({"plan": plan, "next_task": _find_next_step(plan), "metrics": _metrics(plan)})


def _record_event(payload: dict) -> dict:
    user_id = _positive_int(payload.get("user_id"))
    if user_id is None:
        return _error("missing_fields", "missing user_id")
    syllabus_id = _positive_int(payload.get("syllabus_id")) if payload.get("syllabus_id") else None
    plan = prt.get_active_learning_plan(user_id, syllabus_id)
    if not plan:
        return _error("no_active_plan", "no active learning plan")

    plan_id = str(payload.get("plan_id") or plan.get("plan_id") or "")
    step_id = str(payload.get("step_id") or ((_find_next_step(plan) or {}).get("step_id") or ""))
    if not step_id:
        return _error("no_active_step", "no active or pending learning plan step", plan=plan)
    status = str(payload.get("status") or prt.LEARNING_PLAN_STEP_STATUS_ACTIVE)

    event_entry = prt.append_learning_plan_manifest_entry(
        user_id,
        {
            "event_type": LEARNING_EVENT_RECORDED,
            "plan_id": plan_id,
            "step_id": step_id,
            "status": status,
            "payload": {"step_id": step_id, "event": dict(payload)},
        },
        syllabus_id,
    )
    update_result = prt.update_learning_plan_step_status(
        user_id=user_id,
        plan_id=plan_id,
        step_id=step_id,
        status=status,
        syllabus_id=syllabus_id,
        sync_study_graph=False,
    )
    plan_after = update_result.get("plan") or prt.get_active_learning_plan(user_id, syllabus_id)
    activated_step = None
    if status in {prt.LEARNING_PLAN_STEP_STATUS_COMPLETED, prt.LEARNING_PLAN_STEP_STATUS_SKIPPED}:
        next_step = _find_next_step(plan_after)
        if next_step and next_step.get("status") == prt.LEARNING_PLAN_STEP_STATUS_PENDING:
            activate_result = prt.update_learning_plan_step_status(
                user_id=user_id,
                plan_id=plan_id,
                step_id=str(next_step.get("step_id")),
                status=prt.LEARNING_PLAN_STEP_STATUS_ACTIVE,
                syllabus_id=syllabus_id,
                sync_study_graph=False,
            )
            plan_after = activate_result.get("plan") or prt.get_active_learning_plan(user_id, syllabus_id)
            activated_step = _find_step(plan_after, str(next_step.get("step_id")))
    return _ok(
        {
            "plan": plan_after,
            "updated_step": _find_step(plan_after, step_id),
            "activated_step": activated_step,
            "next_task": _find_next_step(plan_after),
            "metrics": _metrics(plan_after),
            "event_entry": event_entry,
            "step_update": update_result,
        }
    )


def _recommend_and_accept(payload: dict) -> dict:
    recommendation_result = prt.run_recommendation_route_from_payload(payload)
    if not recommendation_result.get("success"):
        return _error(
            recommendation_result.get("error_code") or "recommendation_failed",
            recommendation_result.get("error_message") or "recommendation failed",
            recommendation_result=recommendation_result,
        )
    result = _accept_recommendation(
        {
            "user_id": payload.get("user_id"),
            "syllabus_id": payload.get("syllabus_id"),
            "candidate_index": payload.get("candidate_index"),
            "recommendation_result": recommendation_result,
        }
    )
    result["recommendation_result"] = recommendation_result
    return result


def _recommendation_result():
    return {
        "success": True,
        "graph": {
            "nodes": [
                {"id": "n1", "title": "Intro", "outcomes": ["a"]},
                {"id": "n2", "title": "Next", "outcomes": ["b"]},
                {"id": "n3", "title": "Practice", "outcomes": ["c"]},
            ],
            "edges": [
                {"edge_id": "n1->n2", "source": "n1", "target": "n2"},
                {"edge_id": "n2->n3", "source": "n2", "target": "n3"},
            ],
        },
        "candidates": [
            {"path": ["n1", "n2", "n3"], "skills": ["a", "b", "c"], "path_edges": []},
        ],
        "best_path": {"path": ["n1", "n2", "n3"], "skills": ["a", "b", "c"], "path_edges": []},
    }


def _infer_total_agent_intent(message: str, context: Optional[dict] = None) -> str:
    text = str(message or "").strip().lower()
    if any(keyword in text for keyword in ["推荐", "路径", "重新规划", "别的推荐", "recommend"]):
        return "recommend_learning_path"
    if any(keyword in text for keyword in ["完成", "做完", "学完", "通过", "completed", "done"]):
        return "record_learning_feedback"
    if any(keyword in text for keyword in ["跳过", "skip"]):
        return "skip_current_step"
    if any(keyword in text for keyword in ["继续", "下一步", "继续学习", "continue", "next"]):
        return "generate_current_step_resource"
    if isinstance(context, dict) and context.get("active_plan_id"):
        return "generate_current_step_resource"
    return "recommend_learning_path"


def _resource_stub_for_step(user_id: int, syllabus_id: Optional[int], step: Optional[dict]) -> dict:
    if not isinstance(step, dict):
        return {}
    node_id = str(step.get("node_id") or "unknown")
    return {
        "resource_id": f"stub_resource_{user_id}_{syllabus_id or 0}_{node_id}",
        "resource_type": "documents",
        "topic": step.get("title") or node_id,
        "node_id": node_id,
    }


def _run_total_agent_contract_turn(payload: dict) -> dict:
    user_id = _positive_int(payload.get("user_id"))
    if user_id is None:
        return _error("missing_fields", "missing user_id")
    syllabus_id = _positive_int(payload.get("syllabus_id")) if payload.get("syllabus_id") else None
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    intent = _infer_total_agent_intent(str(payload.get("message") or ""), context)
    tool_trace = ["load_total_context"]
    result_payload: dict[str, Any] = {"context": context}
    suggested_next_action = "ask_user_to_confirm_path"

    if intent == "recommend_learning_path":
        recommendation_result = payload.get("recommendation_result")
        if not isinstance(recommendation_result, dict):
            recommendation_result = _recommendation_result()
        if payload.get("force_recommendation_failure"):
            recommendation_result = {
                "success": True,
                "graph": {"nodes": [], "edges": []},
                "candidates": [],
                "selected": [],
                "best_path": None,
                "planning_hints": {"suggested_next_action": "ask_goal_clarification"},
                "error_code": "NO_RECOMMENDATION_FOUND",
                "error_message": "",
            }
        tool_trace.extend(["run_recommendation_route", "accept_recommendation_path", "get_next_learning_task"])
        if not recommendation_result.get("best_path"):
            next_result = _get_next_task(user_id, syllabus_id)
            if next_result.get("success") and next_result.get("next_task"):
                resource = _resource_stub_for_step(user_id, syllabus_id, next_result.get("next_task"))
                return {
                    "success": True,
                    "schema_version": TOTAL_AGENT_SCHEMA_VERSION,
                    "intent": "generate_current_step_resource",
                    "tool_trace": ["load_total_context", "run_recommendation_route", "get_next_learning_task", "generate_learning_resources"],
                    "result": {
                        "recommendation": recommendation_result,
                        "next_result": next_result,
                        "next_task": next_result.get("next_task"),
                        "resources": [resource],
                        "fallback_reason": "active_plan_exists_after_recommendation_failure",
                    },
                    "suggested_next_action": "record_learning_feedback",
                    "error_code": "",
                    "error_message": "",
                }
            return _error("no_recommendation_found", "recommendation produced no best_path and no active plan")
        accept_result = _accept_recommendation(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "candidate_index": payload.get("candidate_index"),
                "recommendation_result": recommendation_result,
            }
        )
        if not accept_result.get("success"):
            return _error(accept_result.get("error_code") or "accept_failed", accept_result.get("error_message") or "")
        result_payload.update(
            {
                "recommendation": recommendation_result,
                "accept_result": accept_result,
                "plan": accept_result.get("plan"),
                "next_task": accept_result.get("next_task"),
                "metrics": accept_result.get("metrics"),
            }
        )
        suggested_next_action = "generate_current_step_resource"

    elif intent == "generate_current_step_resource":
        tool_trace.extend(["get_next_learning_task", "generate_learning_resources"])
        next_result = _get_next_task(user_id, syllabus_id)
        if not next_result.get("success"):
            return _error(next_result.get("error_code") or "no_active_plan", next_result.get("error_message") or "")
        resource = _resource_stub_for_step(user_id, syllabus_id, next_result.get("next_task"))
        result_payload.update({"next_result": next_result, "next_task": next_result.get("next_task"), "resources": [resource]})
        suggested_next_action = "record_learning_feedback"

    elif intent in {"record_learning_feedback", "skip_current_step"}:
        tool_trace.extend(["get_next_learning_task", "record_learning_feedback", "get_next_learning_task"])
        next_result = _get_next_task(user_id, syllabus_id)
        if not next_result.get("success"):
            return _error(next_result.get("error_code") or "no_active_plan", next_result.get("error_message") or "")
        status = (
            prt.LEARNING_PLAN_STEP_STATUS_SKIPPED
            if intent == "skip_current_step"
            else prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
        )
        step = next_result.get("next_task") or {}
        event_result = _record_event(
            {
                "user_id": user_id,
                "syllabus_id": syllabus_id,
                "plan_id": (next_result.get("plan") or {}).get("plan_id"),
                "step_id": step.get("step_id"),
                "event_type": "resource_skipped" if status == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED else "resource_completed",
                "resource_id": context.get("current_resource_id") or payload.get("resource_id") or "",
                "resource_type": context.get("resource_type") or payload.get("resource_type") or "documents",
                "status": status,
                "score": payload.get("score"),
            }
        )
        if not event_result.get("success"):
            return _error(event_result.get("error_code") or "record_event_failed", event_result.get("error_message") or "")
        result_payload.update(
            {
                "event_result": event_result,
                "plan": event_result.get("plan"),
                "next_task": event_result.get("next_task"),
                "metrics": event_result.get("metrics"),
            }
        )
        suggested_next_action = (
            "generate_current_step_resource"
            if event_result.get("next_task")
            else "recommend_learning_path"
        )

    return {
        "success": True,
        "schema_version": TOTAL_AGENT_SCHEMA_VERSION,
        "intent": intent,
        "tool_trace": tool_trace,
        "result": result_payload,
        "suggested_next_action": suggested_next_action,
        "error_code": "",
        "error_message": "",
    }


def test_total_agent_process_contract_deterministic_closure(monkeypatch):
    artifact_root = _reset_artifact_root("deterministic_closure")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    create_result = _accept_recommendation(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "candidate_index": 0,
            "recommendation_result": _recommendation_result(),
        }
    )
    assert create_result["success"] is True
    assert create_result["next_task"]["node_id"] == "n1"
    assert create_result["metrics"]["total_steps"] == 3

    first_step = create_result["next_task"]
    update_result = _record_event(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "plan_id": create_result["plan"]["plan_id"],
            "step_id": first_step["step_id"],
            "event_type": "resource_completed",
            "resource_type": "quiz",
            "resource_id": "res_1",
            "score": 0.9,
            "status": prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
        }
    )
    next_result = _get_next_task(8, 20)
    manifest_entries = prt.load_learning_plan_manifest(8, 20)

    assert update_result["success"] is True
    assert update_result["updated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    assert update_result["activated_step"]["node_id"] == "n2"
    assert update_result["next_task"]["node_id"] == "n2"
    assert next_result["next_task"]["node_id"] == "n2"
    assert next_result["metrics"]["completed_steps"] == 1
    assert any(entry["event_type"] == LEARNING_EVENT_RECORDED for entry in manifest_entries)

    _write_artifact(
        artifact_root,
        "process_contract_result.json",
        {
            "create_result": create_result,
            "update_result": update_result,
            "next_result": next_result,
            "manifest_entries": manifest_entries,
        },
    )


def test_total_agent_process_contract_accepts_real_recommendation_output(monkeypatch):
    artifact_root = _reset_artifact_root("recommendation_contract_closure")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))
    monkeypatch.setattr(prs, "build_recommendation_profile", lambda user_id, syllabus_id=None: user_profile)
    monkeypatch.setattr(prs, "load_recommendation_learning_tree", lambda syllabus_id=None: learning_tree)

    result = _recommend_and_accept(
        {
            "user_id": 12345,
            "syllabus_id": 20,
            "goals": goals,
            "K": 10,
            "beam_width": 8,
        }
    )

    assert result["success"] is True
    assert result["recommendation_result"]["success"] is True
    assert result["recommendation_result"].get("best_path")
    assert (result["recommendation_result"]["best_path"] or {}).get("path")
    assert result["plan"]["steps"]
    assert result["next_task"] == result["plan"]["steps"][0]
    assert result["metrics"]["total_steps"] == len(result["plan"]["steps"])
    assert result["accept_result"]["success"] is True
    assert result["accept_result"]["plan_id"] == result["plan"]["plan_id"]
    assert result["next_task"]["node_id"] in result["recommendation_result"]["best_path"]["path"]

    first_step = result["next_task"]
    update_result = _record_event(
        {
            "user_id": 12345,
            "syllabus_id": 20,
            "plan_id": result["plan"]["plan_id"],
            "step_id": first_step["step_id"],
            "event_type": "resource_completed",
            "status": prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
        }
    )
    assert update_result["success"] is True
    assert update_result["metrics"]["completed_steps"] == 1
    assert update_result["updated_step"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
    if len(result["plan"]["steps"]) > 1:
        assert update_result["next_task"]["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
        assert update_result["next_task"]["node_id"] != first_step["node_id"]
    next_result = _get_next_task(12345, 20)
    assert next_result["success"] is True
    assert next_result["next_task"] == update_result["next_task"]
    manifest_entries = prt.load_learning_plan_manifest(12345, 20)
    event_entries = [entry for entry in manifest_entries if entry.get("event_type") == LEARNING_EVENT_RECORDED]
    assert event_entries
    assert event_entries[-1]["step_id"] == first_step["step_id"]

    _write_artifact(
        artifact_root,
        "recommendation_contract_result.json",
        {
            "summary": {
                "candidate_count": len(result["recommendation_result"].get("candidates") or []),
                "best_path": (result["recommendation_result"].get("best_path") or {}).get("path"),
                "step_count": len(result["plan"]["steps"]),
                "next_after_event": (update_result.get("next_task") or {}).get("node_id"),
            },
            "result": result,
            "update_result": update_result,
            "next_result": next_result,
            "manifest_entries": manifest_entries,
        },
    )


def test_total_agent_process_contract_next_task_requires_active_plan(monkeypatch):
    artifact_root = _reset_artifact_root("no_active_plan")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    result = _get_next_task(8, 20)

    assert result["success"] is False
    assert result["error_code"] == "no_active_plan"


def test_total_agent_process_contract_multi_turn_intent_and_context(monkeypatch):
    artifact_root = _reset_artifact_root("multi_turn_intent_context")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    turns = []
    turn_1 = _run_total_agent_contract_turn(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "帮我推荐一条学习路径",
            "recommendation_result": _recommendation_result(),
        }
    )
    turns.append(turn_1)
    assert turn_1["intent"] == "recommend_learning_path"
    assert turn_1["suggested_next_action"] == "generate_current_step_resource"
    assert turn_1["result"]["next_task"]["node_id"] == "n1"
    plan_id = turn_1["result"]["plan"]["plan_id"]

    turn_2 = _run_total_agent_contract_turn(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "继续学习",
            "context": {"active_plan_id": plan_id},
        }
    )
    turns.append(turn_2)
    assert turn_2["intent"] == "generate_current_step_resource"
    assert turn_2["tool_trace"] == ["load_total_context", "get_next_learning_task", "generate_learning_resources"]
    assert turn_2["suggested_next_action"] == "record_learning_feedback"
    assert turn_2["result"]["next_task"]["node_id"] == "n1"
    resource_id = turn_2["result"]["resources"][0]["resource_id"]

    turn_3 = _run_total_agent_contract_turn(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "我完成了当前资源",
            "context": {"active_plan_id": plan_id, "current_resource_id": resource_id, "resource_type": "documents"},
            "score": 0.92,
        }
    )
    turns.append(turn_3)
    assert turn_3["intent"] == "record_learning_feedback"
    assert turn_3["suggested_next_action"] == "generate_current_step_resource"
    assert turn_3["result"]["event_result"]["updated_step"]["node_id"] == "n1"
    assert turn_3["result"]["next_task"]["node_id"] == "n2"
    assert turn_3["result"]["metrics"]["completed_steps"] == 1

    turn_4 = _run_total_agent_contract_turn(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "跳过当前步骤",
            "context": {"active_plan_id": plan_id},
        }
    )
    turns.append(turn_4)
    assert turn_4["intent"] == "skip_current_step"
    assert turn_4["result"]["event_result"]["updated_step"]["node_id"] == "n2"
    assert turn_4["result"]["metrics"]["skipped_steps"] == 1
    assert turn_4["result"]["next_task"]["node_id"] == "n3"

    manifest_entries = prt.load_learning_plan_manifest(8, 20)
    assert len([entry for entry in manifest_entries if entry.get("event_type") == LEARNING_EVENT_RECORDED]) == 2
    assert _get_next_task(8, 20)["next_task"]["node_id"] == "n3"

    _write_artifact(
        artifact_root,
        "multi_turn_intent_context_result.json",
        {
            "turns": turns,
            "active_plan": prt.get_active_learning_plan(8, 20),
            "manifest_entries": manifest_entries,
        },
    )


def test_total_agent_process_contract_forced_continue_uses_active_plan(monkeypatch):
    artifact_root = _reset_artifact_root("forced_continue_with_active_plan")
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))

    create_result = _accept_recommendation(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "candidate_index": 0,
            "recommendation_result": _recommendation_result(),
        }
    )
    assert create_result["success"] is True
    plan_id = create_result["plan"]["plan_id"]

    forced_result = _run_total_agent_contract_turn(
        {
            "user_id": 8,
            "syllabus_id": 20,
            "message": "推荐链路暂时失败，但我想继续学习",
            "context": {"active_plan_id": plan_id},
            "force_recommendation_failure": True,
        }
    )

    assert forced_result["success"] is True
    assert forced_result["intent"] == "generate_current_step_resource"
    assert forced_result["suggested_next_action"] == "record_learning_feedback"
    assert forced_result["result"]["fallback_reason"] == "active_plan_exists_after_recommendation_failure"
    assert forced_result["result"]["next_task"]["node_id"] == create_result["next_task"]["node_id"]
    assert forced_result["result"]["resources"][0]["node_id"] == create_result["next_task"]["node_id"]

    _write_artifact(
        artifact_root,
        "forced_continue_with_active_plan_result.json",
        {
            "create_result": create_result,
            "forced_result": forced_result,
            "active_plan": prt.get_active_learning_plan(8, 20),
            "manifest_entries": prt.load_learning_plan_manifest(8, 20),
        },
    )
