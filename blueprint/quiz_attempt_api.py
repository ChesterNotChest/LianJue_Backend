from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from tasks.quiz_attempts import list_quiz_attempts, submit_quiz_attempt


bp = Blueprint("quiz_attempt_api", __name__, url_prefix="/api")


def _parse_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@bp.route("/quiz_attempts", methods=["GET"])
def quiz_attempts_list_api():
    user_id = _parse_int(request.args.get("user_id"))
    resource_id = str(request.args.get("resource_id") or "").strip()
    limit = _parse_int(request.args.get("limit")) or 20
    if not user_id or not resource_id:
        return jsonify({
            "success": False,
            "attempts": [],
            "error_code": "missing_fields",
            "error_message": "user_id and resource_id are required",
        }), 400
    attempts = list_quiz_attempts(user_id, resource_id, limit=limit)
    current_app.logger.info(
        "[quiz_attempts] list user_id=%s resource_id=%s count=%s",
        user_id,
        resource_id,
        len(attempts),
    )
    return jsonify({
        "success": True,
        "attempts": attempts,
        "error_code": "",
        "error_message": "",
    })


@bp.route("/quiz_attempts", methods=["POST"])
def quiz_attempts_submit_api():
    data = request.get_json(silent=True) or {}
    user_id = _parse_int(data.get("user_id"))
    syllabus_id = _parse_int(data.get("syllabus_id")) or 0
    resource_id = str(data.get("resource_id") or "").strip()
    if not user_id or not resource_id:
        return jsonify({
            "success": False,
            "attempt": None,
            "attempts": [],
            "duplicate": False,
            "error_code": "missing_fields",
            "error_message": "user_id and resource_id are required",
        }), 400

    result = submit_quiz_attempt(
        user_id=user_id,
        syllabus_id=syllabus_id,
        resource_id=resource_id,
        attempt_id=data.get("attempt_id"),
        answers=data.get("answers") if isinstance(data.get("answers"), dict) else {},
        score=data.get("score"),
        correct_count=data.get("correct_count"),
        total_count=data.get("total_count"),
        wrong_knowledge_items=data.get("wrong_knowledge_items") if isinstance(data.get("wrong_knowledge_items"), list) else [],
        answer_records=data.get("answer_records") if isinstance(data.get("answer_records"), list) else [],
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    )
    current_app.logger.info(
        "[quiz_attempts] submit user_id=%s syllabus_id=%s resource_id=%s attempt_id=%s duplicate=%s score=%s",
        user_id,
        syllabus_id,
        resource_id,
        (result.get("attempt") or {}).get("attempt_id") if isinstance(result.get("attempt"), dict) else "",
        result.get("duplicate"),
        (result.get("attempt") or {}).get("score") if isinstance(result.get("attempt"), dict) else None,
    )
    return jsonify(result), 200 if result.get("success") else 400
