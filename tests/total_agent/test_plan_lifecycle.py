"""Smoke tests for the learning plan lifecycle state machine.

Covers plan creation, step completion, auto-complete on last step,
plan abandon, and plan supersede — all without LLM/RAG/DB.

These tests verify the plan state machine after the completed/abandoned
event types were added (EVENT_PLAN_COMPLETED, EVENT_PLAN_ABANDONED).

Run:
  pytest tests/total_agent/test_plan_lifecycle.py -v
"""

import shutil
from pathlib import Path

import pytest

from tasks import personal_recommendation_task as prt
from tasks.personal_recommendation import service as prs
from tasks.personal_recommendation.sample_data import learning_tree, user_profile

TEST_ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "artifacts" / "plan_lifecycle"

# ── Minimal recommendation fixture with 3-node path ──────────────────────

MINIMAL_RECOMMENDATION = {
    "success": True,
    "graph": {
        "nodes": [
            {"id": "node_1", "title": "课程导论", "outcomes": ["了解课程概览"]},
            {"id": "node_2", "title": "基础概念", "outcomes": ["掌握基础概念"]},
            {"id": "node_3", "title": "核心模块", "outcomes": ["理解核心模块"]},
        ],
        "edges": [
            {"edge_id": "node_1->node_2", "source": "node_1", "target": "node_2"},
            {"edge_id": "node_2->node_3", "source": "node_2", "target": "node_3"},
        ],
    },
    "candidates": [
        {
            "path": ["node_1", "node_2", "node_3"],
            "skills": ["了解课程概览", "掌握基础概念", "理解核心模块"],
            "score": 0.95,
            "rank": 1,
        }
    ],
    "best_path": {
        "path": ["node_1", "node_2", "node_3"],
        "skills": ["了解课程概览", "掌握基础概念", "理解核心模块"],
    },
    "selected": [
        {"path": ["node_1", "node_2", "node_3"]}
    ],
}

MINIMAL_USER_ID = 90001
MINIMAL_SYLLABUS_ID = 90010


def _reset_artifact_root(name: str) -> Path:
    root = TEST_ARTIFACT_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _setup_mocks(monkeypatch, artifact_root):
    """Install mock profile + learning tree, redirect artifact writes."""
    monkeypatch.setenv("PERSONAL_RECOMMENDATION_ROOT", str(artifact_root))
    monkeypatch.setattr(
        prs, "build_recommendation_profile",
        lambda user_id, syllabus_id=None: dict(user_profile),
    )
    monkeypatch.setattr(
        prs, "load_recommendation_learning_tree",
        lambda syllabus_id=None, **kwargs: dict(learning_tree),
    )


def _create_plan():
    """Accept a recommendation to create an active plan with 3 steps."""
    return prt.accept_recommendation_path(
        user_id=MINIMAL_USER_ID,
        syllabus_id=MINIMAL_SYLLABUS_ID,
        recommendation_result=dict(MINIMAL_RECOMMENDATION),
    )


def _plan_steps(plan):
    return plan.get("steps") or []


# ═══════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanLifecycle:
    """Plan creation, completion, abandon, and supersede."""

    def test_plan_accept_creates_active_plan(self, monkeypatch):
        """Accepting a recommendation creates an active plan with steps."""
        artifact_root = _reset_artifact_root("accept")
        _setup_mocks(monkeypatch, artifact_root)

        result = _create_plan()
        assert result["success"] is True
        assert result["status"] == prt.LEARNING_PLAN_STATUS_ACTIVE

        plan = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        assert plan is not None
        assert plan["status"] == prt.LEARNING_PLAN_STATUS_ACTIVE
        steps = _plan_steps(plan)
        assert len(steps) == 3
        # First step active, rest pending
        assert steps[0]["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE
        assert steps[1]["status"] == prt.LEARNING_PLAN_STEP_STATUS_PENDING
        assert steps[2]["status"] == prt.LEARNING_PLAN_STEP_STATUS_PENDING

    def test_step_completion_updates_status(self, monkeypatch):
        """Completing a step via update_learning_plan_step_status updates that step."""
        artifact_root = _reset_artifact_root("step_status")
        _setup_mocks(monkeypatch, artifact_root)

        plan_result = _create_plan()
        plan = plan_result["plan"]

        # Complete step 1 — this only updates the step, does not auto-activate next
        step1 = _plan_steps(plan)[0]
        update = prt.update_learning_plan_step_status(
            MINIMAL_USER_ID,
            plan["plan_id"],
            step1["step_id"],
            prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
            syllabus_id=MINIMAL_SYLLABUS_ID,
            sync_study_graph=False,
        )
        assert update["success"] is True

        refreshed = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        steps = _plan_steps(refreshed)
        assert steps[0]["status"] == prt.LEARNING_PLAN_STEP_STATUS_COMPLETED
        # Next step is still pending — activation is handled by the total agent layer
        assert steps[1]["status"] == prt.LEARNING_PLAN_STEP_STATUS_PENDING

        # Explicitly activate the next step (simulating what _activate_next_pending does)
        step2 = steps[1]
        prt.update_learning_plan_step_status(
            MINIMAL_USER_ID,
            plan["plan_id"],
            step2["step_id"],
            prt.LEARNING_PLAN_STEP_STATUS_ACTIVE,
            syllabus_id=MINIMAL_SYLLABUS_ID,
            sync_study_graph=False,
        )
        refreshed2 = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        steps2 = _plan_steps(refreshed2)
        assert steps2[1]["status"] == prt.LEARNING_PLAN_STEP_STATUS_ACTIVE

    def test_plan_auto_completes_on_last_step(self, monkeypatch):
        """When all steps are completed (via tool), plan transitions to completed."""
        artifact_root = _reset_artifact_root("auto_complete")
        _setup_mocks(monkeypatch, artifact_root)

        plan_result = _create_plan()
        plan = plan_result["plan"]
        plan_id = plan["plan_id"]

        # Complete all 3 steps via step status updates
        for step in _plan_steps(plan):
            prt.update_learning_plan_step_status(
                MINIMAL_USER_ID,
                plan_id,
                step["step_id"],
                prt.LEARNING_PLAN_STEP_STATUS_COMPLETED,
                syllabus_id=MINIMAL_SYLLABUS_ID,
                sync_study_graph=False,
            )

        # After completing last step, call complete_learning_plan explicitly
        # (this simulates what _record_step_status does when _activate_next_pending
        #  returns empty — the total agent tool layer triggers this)
        complete_result = prt.complete_learning_plan(
            MINIMAL_USER_ID, plan_id, syllabus_id=MINIMAL_SYLLABUS_ID
        )
        assert complete_result["success"] is True
        assert complete_result["status"] == prt.LEARNING_PLAN_STATUS_COMPLETED

        # No active plan after completion
        active = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        assert active is None

        # Manifest entries include plan_completed event
        entries = prt.load_learning_plan_manifest(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        event_types = {e["event_type"] for e in entries}
        assert prt.EVENT_PLAN_COMPLETED in event_types

    def test_plan_abandon(self, monkeypatch):
        """Abandoning a plan marks it abandoned and clears active plan."""
        artifact_root = _reset_artifact_root("abandon")
        _setup_mocks(monkeypatch, artifact_root)

        plan_result = _create_plan()
        plan_id = plan_result["plan_id"]

        result = prt.abandon_learning_plan(
            MINIMAL_USER_ID,
            plan_id,
            syllabus_id=MINIMAL_SYLLABUS_ID,
            reason="student wants to switch topics",
        )
        assert result["success"] is True
        assert result["status"] == prt.LEARNING_PLAN_STATUS_ABANDONED

        # No active plan after abandon
        active = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        assert active is None

        # Manifest includes plan_abandoned event
        entries = prt.load_learning_plan_manifest(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        event_types = {e["event_type"] for e in entries}
        assert prt.EVENT_PLAN_ABANDONED in event_types

    def test_plan_supersede_on_new_accept(self, monkeypatch):
        """Accepting a new recommendation supersedes the old active plan."""
        artifact_root = _reset_artifact_root("supersede")
        _setup_mocks(monkeypatch, artifact_root)

        # Accept first plan
        first = _create_plan()
        first_plan_id = first["plan_id"]
        assert prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID) is not None

        # Accept second plan (same recommendation — real scenario would differ)
        second = _create_plan()
        assert second["plan_id"] != first_plan_id
        assert second["superseded_plan_id"] == first_plan_id

        # Old plan is superseded
        entries = prt.load_learning_plan_manifest(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        # Verify the first plan's superseded event exists
        plan_events = {}
        for e in entries:
            pid = e.get("plan_id")
            if pid not in plan_events:
                plan_events[pid] = set()
            plan_events[pid].add(e.get("event_type"))
        assert prt.EVENT_PLAN_SUPERSEDED in plan_events.get(first_plan_id, set())

        # New plan is active
        active = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        assert active["plan_id"] == second["plan_id"]

    def test_new_plan_after_completion(self, monkeypatch):
        """After a plan completes and a new one is accepted, it's a fresh start."""
        artifact_root = _reset_artifact_root("after_complete")
        _setup_mocks(monkeypatch, artifact_root)

        # Create, complete
        first = _create_plan()
        prt.complete_learning_plan(
            MINIMAL_USER_ID, first["plan_id"], syllabus_id=MINIMAL_SYLLABUS_ID
        )
        assert prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID) is None

        # Create second plan — should be independent
        second = _create_plan()
        assert second["success"] is True
        active = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        assert active is not None
        assert active["plan_id"] == second["plan_id"]
        # First plan was already completed, not superseded by the new one
        assert second.get("superseded_plan_id") is None

    def test_step_skip_updates_status(self, monkeypatch):
        """Skipping a step updates its status; activation is a separate step."""
        artifact_root = _reset_artifact_root("skip")
        _setup_mocks(monkeypatch, artifact_root)

        plan_result = _create_plan()
        plan = plan_result["plan"]
        step1 = _plan_steps(plan)[0]

        update = prt.update_learning_plan_step_status(
            MINIMAL_USER_ID,
            plan["plan_id"],
            step1["step_id"],
            prt.LEARNING_PLAN_STEP_STATUS_SKIPPED,
            syllabus_id=MINIMAL_SYLLABUS_ID,
            sync_study_graph=False,
        )
        assert update["success"] is True

        refreshed = prt.get_active_learning_plan(MINIMAL_USER_ID, MINIMAL_SYLLABUS_ID)
        steps = _plan_steps(refreshed)
        assert steps[0]["status"] == prt.LEARNING_PLAN_STEP_STATUS_SKIPPED
        # Next step is still pending until explicitly activated
        assert steps[1]["status"] == prt.LEARNING_PLAN_STEP_STATUS_PENDING
