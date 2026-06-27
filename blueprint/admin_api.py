"""管理员端点 — operator 权限要求。

- POST /api/admin/syllabus/<id>/publish        发布学科（批量绑定+锁定）
- GET  /api/admin/syllabus/<id>/students_progress  学员进度总览
- POST /api/admin/set_permission                用户提权/降权
"""

from flask import Blueprint, jsonify, request

from extensions import db
from schemas.user import User
from repositories.syllabus_repo import get_syllabus_by_id
from repositories.user_repo import list_all_users_brief, get_user_by_id
from repositories.user_syllabus_repo import (
    create_user_syllabus,
    list_user_syllabuses_by_syllabus,
)
from utils.auth import require_operator

bp = Blueprint("admin_api", __name__, url_prefix="/api/admin")


# ── publish ─────────────────────────────────────────────────────
@bp.route("/syllabus/<int:syllabus_id>/publish", methods=["POST"])
@require_operator
def publish_syllabus_api(syllabus_id):
    """发布学科：校验 → 批量绑定所有用户 → 状态切换 published → 锁定。

    Body: { "user_id": int }  — operator ID
    """
    syllabus = get_syllabus_by_id(syllabus_id)
    if not syllabus:
        return (
            jsonify({"success": False, "error_code": "not_found", "error_message": "syllabus not found"}),
            404,
        )

    if not getattr(syllabus, "syllabus_path", None):
        return (
            jsonify(
                {
                    "success": False,
                    "error_message": "最终大纲未生成，无法发布",
                    "error_code": "syllabus_incomplete",
                }
            ),
            400,
        )

    if getattr(syllabus, "status", None) == "published":
        return (
            jsonify(
                {
                    "success": False,
                    "error_message": "学科已发布",
                    "error_code": "already_published",
                }
            ),
            400,
        )

    # 批量绑定所有现有用户
    users = list_all_users_brief()
    bound = 0
    for u in users:
        try:
            create_user_syllabus(u["user_id"], syllabus_id)
            bound += 1
        except Exception:
            pass

    syllabus.status = "published"
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "syllabus_id": syllabus_id,
            "bound_users": bound,
            "status": "published",
        }
    )


# ── students_progress ────────────────────────────────────────────
@bp.route("/syllabus/<int:syllabus_id>/students_progress", methods=["GET"])
@require_operator
def students_progress_api(syllabus_id):
    """某学科全部学员的学习进度树 + 学伴树。

    Query params: user_id (operator), limit (default 50, max 100)

    Response:
      { students: [{ user_index, study_graph: StudyGraphTree|null,
                     buddy_tree: BuddyTree|null }], total: N }
    """
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (TypeError, ValueError):
        limit = 50

    from tasks.study_graph.storage import get_tree, list_nodes, list_edges
    from tasks.study_buddy.tree_store import load_buddy_tree

    bindings = list_user_syllabuses_by_syllabus(syllabus_id)
    students = []

    for idx, binding in enumerate(bindings[:limit]):
        uid = binding.user_id
        tree = get_tree(uid, syllabus_id)
        buddy_tree = load_buddy_tree(uid, syllabus_id)
        students.append(
            {
                "user_index": idx + 1,
                "study_graph": tree,
                "buddy_tree": buddy_tree,
            }
        )

    return jsonify(
        {
            "success": True,
            "syllabus_id": syllabus_id,
            "students": students,
            "total": len(bindings),
        }
    )


# ── set_permission ───────────────────────────────────────────────
@bp.route("/set_permission", methods=["POST"])
@require_operator
def set_permission_api():
    """设置用户权限。

    Body: { "user_id": int (operator), "target_user_id": int, "permission": "user"|"operator" }
    """
    data = request.get_json(silent=True) or {}
    target_id = data.get("target_user_id")
    new_perm = data.get("permission")

    if not target_id or new_perm not in ("user", "operator"):
        return (
            jsonify({"success": False, "error_code": "invalid_fields", "error_message": "missing target_user_id or permission"}),
            400,
        )

    target = get_user_by_id(int(target_id))
    if not target:
        return (
            jsonify({"success": False, "error_code": "not_found", "error_message": "user not found"}),
            404,
        )

    target.permission = new_perm
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "user": {
                "user_id": target.user_id,
                "user_name": target.user_name,
                "permission": target.permission,
            },
        }
    )
