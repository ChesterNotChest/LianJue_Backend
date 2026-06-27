"""权限校验装饰器。

提供统一的 operator 权限门禁，用于管理端端点。
"""

from functools import wraps
from flask import request, jsonify

from schemas.user import User


def require_operator(f):
    """装饰器：要求调用者为 operator 权限用户。

    从 request body 或 query string 提取 user_id，
    查库验证 permission == 'operator'。
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id")
        if not user_id:
            return (
                jsonify(
                    {
                        "success": False,
                        "error_message": "missing user_id",
                        "error_code": "missing_fields",
                    }
                ),
                400,
            )

        try:
            user = User.query.get(int(user_id))
        except (TypeError, ValueError):
            return (
                jsonify(
                    {
                        "success": False,
                        "error_message": "invalid user_id",
                        "error_code": "invalid_fields",
                    }
                ),
                400,
            )

        if not user or user.permission != "operator":
            return (
                jsonify(
                    {
                        "success": False,
                        "error_message": "operator permission required",
                        "error_code": "operator_required",
                    }
                ),
                403,
            )

        return f(*args, **kwargs)

    return decorated
