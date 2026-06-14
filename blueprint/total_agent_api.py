import asyncio
import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from tasks import total_agent_task
from tasks.total_agent import agent_runtime
from tasks.total_agent import agent_contracts as tac


bp = Blueprint("total_agent_api", __name__, url_prefix="/api")


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _build_detail_payload():
    return {
        "success": True,
        "agent": {
            "name": "total_agent",
            "schema_version": tac.TOTAL_AGENT_SCHEMA_VERSION,
            "intents": list(tac.TOTAL_AGENT_INTENTS),
            "tool_order": tac.TOTAL_AGENT_TOOL_ORDER,
            "entrypoints": ["run_total_agent", "run_total_agent_agent", "get_total_agent"],
        },
        "error_message": "",
        "error_code": "",
    }


def _append_stream_text(accumulator, event):
    if not isinstance(event, dict):
        return
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if event.get("type") == tac.STREAM_EVENT_TEXT_START:
        accumulator.append(str(data.get("content") or ""))
    elif event.get("type") == tac.STREAM_EVENT_TEXT_DELTA:
        accumulator.append(str(data.get("content_delta") or ""))


def _apply_stream_event_snapshot(snapshot, event):
    if not isinstance(event, dict):
        return
    event_type = event.get("type")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    timestamp = event.get("timestamp")

    if event_type == tac.STREAM_EVENT_TEXT_START:
        content = str(data.get("content") or "")
        snapshot["segments"].append({"kind": "text", "content": content})
    elif event_type == tac.STREAM_EVENT_TEXT_DELTA:
        content = str(data.get("content_delta") or "")
        if snapshot["segments"] and snapshot["segments"][-1].get("kind") == "text":
            snapshot["segments"][-1]["content"] = str(snapshot["segments"][-1].get("content") or "") + content
        else:
            snapshot["segments"].append({"kind": "text", "content": content})
    elif event_type == tac.STREAM_EVENT_TOOL_CALL:
        tool_call = {
            "tool_name": str(data.get("tool_name") or ""),
            "tool_call_id": str(data.get("tool_call_id") or ""),
            "args": data.get("args"),
            "status": "pending",
        }
        snapshot["toolCalls"].append(tool_call)
        snapshot["segments"].append({"kind": "tools", "toolCallIds": [tool_call["tool_call_id"]], "subagentEventIds": []})
    elif event_type == tac.STREAM_EVENT_TOOL_START:
        tool_name = str(data.get("tool_name") or "")
        tool_call_id = str(data.get("tool_call_id") or "")
        for tool_call in snapshot["toolCalls"]:
            if (tool_call_id and tool_call.get("tool_call_id") == tool_call_id) or (tool_name and tool_call.get("tool_name") == tool_name):
                tool_call["status"] = "running"
                tool_call["startedAt"] = timestamp
                break
    elif event_type == tac.STREAM_EVENT_TOOL_END:
        tool_name = str(data.get("tool_name") or "")
        tool_call_id = str(data.get("tool_call_id") or "")
        result = data.get("result")
        status = "failed" if isinstance(result, dict) and result.get("success") is False else "succeeded"
        for tool_call in snapshot["toolCalls"]:
            if (tool_call_id and tool_call.get("tool_call_id") == tool_call_id) or (tool_name and tool_call.get("tool_name") == tool_name):
                tool_call["status"] = status
                tool_call["result"] = result
                tool_call["completedAt"] = timestamp
                break
    elif event_type == tac.STREAM_EVENT_TOOL_STATUS:
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        subagent_event = {
            "event_id": str(data.get("event_id") or ""),
            "event_key": str(data.get("event_key") or ""),
            "agent": str(data.get("agent") or ""),
            "stage": str(data.get("stage") or ""),
            "status": str(data.get("status") or "running"),
            "message": str(data.get("message") or ""),
            "timestamp": timestamp,
            "payload": payload,
            "task_id": payload.get("task_id"),
            "resource_type": payload.get("resource_type"),
        }
        snapshot["subagentEvents"].append(subagent_event)
        event_id = subagent_event["event_id"]
        if snapshot["segments"] and snapshot["segments"][-1].get("kind") == "tools":
            snapshot["segments"][-1].setdefault("subagentEventIds", []).append(event_id)
        else:
            snapshot["segments"].append({"kind": "tools", "toolCallIds": [], "subagentEventIds": [event_id]})
    elif event_type == tac.STREAM_EVENT_FINAL:
        snapshot["finalResult"] = data


def _persist_stream_text_before_close(data, accumulator, snapshot):
    content = "".join(accumulator).strip()
    if not content:
        return
    try:
        agent_runtime.persist_streamed_agent_reply(data, content, metadata=snapshot)
    except Exception:
        try:
            from extensions import db
            db.session.rollback()
        except Exception:
            pass


@bp.route("/total_agent/detail", methods=["GET"])
def total_agent_detail_api():
    return jsonify(_build_detail_payload()), 200


@bp.route("/total_agent/run", methods=["POST"])
def total_agent_run_api():
    data = request.get_json(silent=True) or {}
    use_llm = _parse_bool(data.get("use_llm"), default=False)
    use_stream = _parse_bool(data.get("stream"), default=False)

    if not use_stream:
        try:
            result = total_agent_task.run_total_agent(data, use_llm=use_llm)
            return jsonify(result), 200
        except Exception as exc:
            return jsonify(
                {
                    "success": False,
                    "schema_version": tac.TOTAL_AGENT_SCHEMA_VERSION,
                    "intent": "",
                    "tool_trace": [],
                    "tool_status_events": [],
                    "result": {},
                    "suggested_next_action": "",
                    "error_code": "exception",
                    "error_message": str(exc),
                }
            ), 500

    # ── 流式分支（SSE） ──
    async_gen = total_agent_task.run_total_agent(data, use_llm=True, stream=True)

    def generate():
        streamed_text = []
        stream_snapshot = {"toolCalls": [], "subagentEvents": [], "segments": [], "finalResult": None}

        async def _consume():
            try:
                async for event in async_gen:
                    _append_stream_text(streamed_text, event)
                    _apply_stream_event_snapshot(stream_snapshot, event)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            finally:
                _persist_stream_text_before_close(data, streamed_text, stream_snapshot)
                yield "event: close\ndata: {}\n\n"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            agen = _consume()
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
                except Exception:
                    yield "event: close\ndata: {}\n\n"
                    break
        finally:
            loop.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Chat session history APIs ──────────────────────────────────────────────

def _chat_positive_int_or_none(value):
    try:
        v = int(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


@bp.route("/chat/sessions", methods=["GET"])
def list_chat_sessions_api():
    user_id = _chat_positive_int_or_none(request.args.get("user_id"))
    syllabus_id = _chat_positive_int_or_none(request.args.get("syllabus_id"))
    if not user_id:
        return jsonify({"success": False, "sessions": [], "error_message": "user_id required"}), 400
    from schemas.agent_runtime_state import ChatSession
    q = ChatSession.query.filter_by(user_id=user_id)
    if syllabus_id:
        q = q.filter_by(syllabus_id=syllabus_id)
    rows = q.order_by(ChatSession.updated_at.desc()).limit(50).all()
    sessions = [{
        "session_id": r.session_id,
        "title": r.title,
        "turn_count": r.turn_count,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    } for r in rows]
    return jsonify({"success": True, "sessions": sessions})


@bp.route("/chat/sessions/<session_id>/turns", methods=["GET"])
def get_chat_turns_api(session_id):
    if not session_id:
        return jsonify({"success": False, "turns": [], "error_message": "session_id required"}), 400
    from schemas.agent_runtime_state import ChatTurn
    rows = ChatTurn.query.filter_by(session_id=session_id).order_by(ChatTurn.id.asc()).limit(200).all()
    turns = []
    for r in rows:
        metadata = {}
        raw_metadata = getattr(r, "metadata_json", None)
        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}
        turns.append({"role": r.role, "content": r.content, "timestamp": r.created_at, "metadata": metadata})
    return jsonify({"success": True, "turns": turns})


@bp.route("/total_agent/agent_run", methods=["POST"])
def total_agent_agent_run_api():
    data = request.get_json(silent=True) or {}
    use_stream = _parse_bool(data.get("stream"), default=False)

    if not use_stream:
        # ── 原有同步逻辑不变 ──
        try:
            result = total_agent_task.run_total_agent_agent(data)
            return jsonify(result), 200
        except Exception as exc:
            return jsonify(
                {
                    "success": False,
                    "schema_version": tac.TOTAL_AGENT_SCHEMA_VERSION,
                    "intent": "",
                    "tool_trace": [],
                    "tool_status_events": [],
                    "result": {},
                    "suggested_next_action": "",
                    "error_code": "exception",
                    "error_message": str(exc),
                }
            ), 500

    # ── 流式分支（SSE） ──
    async_gen = total_agent_task.run_total_agent_agent(data, stream=True)

    def generate():
        streamed_text = []
        stream_snapshot = {"toolCalls": [], "subagentEvents": [], "segments": [], "finalResult": None}

        async def _consume():
            try:
                async for event in async_gen:
                    _append_stream_text(streamed_text, event)
                    _apply_stream_event_snapshot(stream_snapshot, event)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            finally:
                _persist_stream_text_before_close(data, streamed_text, stream_snapshot)
                yield "event: close\ndata: {}\n\n"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            agen = _consume()
            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
                except Exception:
                    yield "event: close\ndata: {}\n\n"
                    break
        finally:
            loop.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
