from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, MutableMapping, Optional


STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_WARNING = "warning"

STATUS_VALUES = {
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_WARNING,
}


def utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def build_event_key(agent: str, stage: str, status: str) -> str:
    return f"{safe_text(agent)}.{safe_text(stage)}.{safe_text(status)}"


def build_label_key(agent: str, stage: str, status: str) -> str:
    agent_key = safe_text(agent)
    if agent_key.endswith("_agent"):
        agent_key = agent_key[: -len("_agent")]
    return f"agent.{agent_key}.{safe_text(stage)}.{safe_text(status)}"


def create_status_event(
    *,
    run_id: Any = "",
    agent: str,
    stage: str,
    status: str,
    message: str = "",
    payload: Optional[dict] = None,
    event_id: str = "",
    timestamp: Optional[int] = None,
) -> dict:
    normalized_agent = safe_text(agent)
    normalized_stage = safe_text(stage)
    normalized_status = safe_text(status)
    if normalized_status not in STATUS_VALUES:
        normalized_status = STATUS_WARNING
    ts = utc_timestamp() if timestamp is None else int(timestamp)
    event = {
        "event_id": safe_text(event_id) or f"evt_{ts}_{normalized_agent}_{normalized_stage}_{normalized_status}",
        "run_id": safe_text(run_id),
        "agent": normalized_agent,
        "stage": normalized_stage,
        "status": normalized_status,
        "event_key": build_event_key(normalized_agent, normalized_stage, normalized_status),
        "label_key": build_label_key(normalized_agent, normalized_stage, normalized_status),
        "message": safe_text(message),
        "timestamp": ts,
        "payload": payload if isinstance(payload, dict) else {},
    }
    return event


def append_status_event(state_or_payload: MutableMapping[str, Any], event: dict) -> dict:
    events = state_or_payload.setdefault("tool_status_events", [])
    if isinstance(events, list):
        events.append(event)
    else:
        state_or_payload["tool_status_events"] = [event]
    return event


def emit_status_event(
    state_or_payload: MutableMapping[str, Any],
    *,
    agent: str,
    stage: str,
    status: str,
    message: str = "",
    payload: Optional[dict] = None,
    run_id: Any = None,
) -> dict:
    event = create_status_event(
        run_id=state_or_payload.get("run_id") if run_id is None else run_id,
        agent=agent,
        stage=stage,
        status=status,
        message=message,
        payload=payload,
    )
    append_status_event(state_or_payload, event)
    callback = state_or_payload.get("status_callback")
    if callable(callback):
        callback(event)
    return event


def emit_status_pair(
    state_or_payload: MutableMapping[str, Any],
    *,
    agent: str,
    stage: str,
    fn: Callable[[], Any],
    message: str = "",
    payload: Optional[dict] = None,
) -> Any:
    emit_status_event(
        state_or_payload,
        agent=agent,
        stage=stage,
        status=STATUS_RUNNING,
        message=message,
        payload=payload,
    )
    try:
        result = fn()
    except Exception as exc:
        emit_status_event(
            state_or_payload,
            agent=agent,
            stage=stage,
            status=STATUS_FAILED,
            message=safe_text(exc),
            payload=payload,
        )
        raise
    success = True
    if isinstance(result, dict) and result.get("success") is False:
        success = False
    emit_status_event(
        state_or_payload,
        agent=agent,
        stage=stage,
        status=STATUS_SUCCEEDED if success else STATUS_FAILED,
        message=message,
        payload=payload,
    )
    return result


def get_status_events(state_or_payload: MutableMapping[str, Any]) -> list[dict]:
    events = state_or_payload.get("tool_status_events")
    return list(events) if isinstance(events, list) else []
