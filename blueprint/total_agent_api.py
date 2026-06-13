import asyncio
import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from tasks import total_agent_task
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
        async def _consume():
            async for event in async_gen:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
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
        finally:
            loop.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        async def _consume():
            async for event in async_gen:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
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
        finally:
            loop.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
