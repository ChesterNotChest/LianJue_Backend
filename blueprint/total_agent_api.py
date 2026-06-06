from flask import Blueprint, jsonify, request

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
    try:
        result = total_agent_task.run_total_agent(data, use_llm=_parse_bool(data.get("use_llm"), default=False))
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


@bp.route("/total_agent/agent_run", methods=["POST"])
def total_agent_agent_run_api():
    data = request.get_json(silent=True) or {}
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
