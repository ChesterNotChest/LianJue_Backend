"""学伴 API — /api/study_buddy/chat"""

from flask import Blueprint, jsonify, request

from tasks import learning_profile_task as lpt
from tasks import personal_recommendation_task as prt
from tasks import study_graph_task as sgt
from tasks.study_buddy_task import buddy_chat, list_buddy_messages, trigger_study_buddy

bp = Blueprint("study_buddy_api", __name__, url_prefix="/api")


def _parse_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@bp.route("/study_buddy/chat", methods=["POST"])
def study_buddy_chat():
    """学伴独立对话。

    输入：{"user_id": 161, "syllabus_id": 29, "message": "我该先学 RowKey 吗？"}
    输出：{"success": true, "reply": "...", "memory_tags_written": [...]}
    """
    data = request.get_json(silent=True) or {}
    user_id = _parse_int(data.get("user_id"))
    syllabus_id = _parse_int(data.get("syllabus_id"))
    message = str(data.get("message") or "").strip()

    if not user_id or not message:
        return jsonify({
            "success": False,
            "reply": "",
            "memory_tags_written": [],
            "error_code": "missing_fields",
            "error_message": "user_id and message are required",
        }), 400

    # 加载上下文
    plan = prt.get_active_learning_plan(user_id, syllabus_id)
    plan_dict = plan if isinstance(plan, dict) else None
    features = sgt.get_learning_tree_features(user_id, syllabus_id)

    result = buddy_chat(
        user_id=user_id,
        syllabus_id=syllabus_id or 0,
        message=message,
        plan=plan_dict,
        study_graph_features=features if isinstance(features, dict) else None,
    )
    return jsonify({
        "success": True,
        "reply": result["reply"],
        "messages": list_buddy_messages(user_id, syllabus_id or 0),
        "memory_tags_written": result.get("memory_tags_written", []),
        "error_code": "",
        "error_message": "",
    })


@bp.route("/study_buddy/proactive", methods=["POST"])
def study_buddy_proactive():
    """手动触发学伴主动消息（调试用）。

    输入：{"user_id": 161, "syllabus_id": 29}
    输出：{"success": true, "buddy_message": "..." | null}
    """
    data = request.get_json(silent=True) or {}
    user_id = _parse_int(data.get("user_id"))
    syllabus_id = _parse_int(data.get("syllabus_id"))

    if not user_id:
        return jsonify({
            "success": False,
            "buddy_message": None,
            "error_code": "missing_fields",
            "error_message": "user_id is required",
        }), 400

    plan = prt.get_active_learning_plan(user_id, syllabus_id)
    plan_dict = plan if isinstance(plan, dict) else None
    features = sgt.get_learning_tree_features(user_id, syllabus_id)

    msg = trigger_study_buddy(
        user_id=user_id,
        syllabus_id=syllabus_id or 0,
        plan=plan_dict,
        study_graph_features=features if isinstance(features, dict) else None,
    )
    return jsonify({
        "success": True,
        "buddy_message": msg,
        "messages": list_buddy_messages(user_id, syllabus_id or 0),
        "error_code": "",
        "error_message": "",
    })


@bp.route("/study_buddy/messages", methods=["GET", "POST"])
def study_buddy_messages():
    data = request.get_json(silent=True) or {}
    user_id = _parse_int(request.args.get("user_id") or data.get("user_id"))
    syllabus_id = _parse_int(request.args.get("syllabus_id") or data.get("syllabus_id")) or 0
    limit = _parse_int(request.args.get("limit") or data.get("limit")) or 30
    if not user_id:
        return jsonify({
            "success": False,
            "messages": [],
            "error_code": "missing_fields",
            "error_message": "user_id is required",
        }), 400
    return jsonify({
        "success": True,
        "messages": list_buddy_messages(user_id, syllabus_id, limit=limit),
        "error_code": "",
        "error_message": "",
    })
