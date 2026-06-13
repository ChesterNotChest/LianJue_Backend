from flask import Blueprint, jsonify, request

from repositories.user_syllabus_repo import get_user_syllabus
from tasks import learning_profile_task
from tasks.common.search_tool import search_tool
from tasks.personal_recommendation_task import (
    accept_recommendation_snapshot_path,
    get_active_learning_plan,
    get_recommendation_snapshot,
    list_recommendation_snapshots,
    run_recommendation_route_from_payload,
)


bp = Blueprint('learning_api', __name__, url_prefix='/api')


def _coerce_positive_ids(user_id, syllabus_id):
    try:
        normalized_user_id = int(user_id)
        normalized_syllabus_id = int(syllabus_id)
    except Exception:
        return None
    if normalized_user_id <= 0 or normalized_syllabus_id <= 0:
        return None
    return normalized_user_id, normalized_syllabus_id


def _get_personal_syllabus_path(user_id: int, syllabus_id: int):
    try:
        relation = get_user_syllabus(user_id, syllabus_id)
    except Exception:
        return None
    path = getattr(relation, "personal_syllabus_path", None) if relation else None
    return path if isinstance(path, str) and path.strip() else None


def _init_personal_syllabus_for_display(user_id: int, syllabus_id: int):
    normalized = _coerce_positive_ids(user_id, syllabus_id)
    if normalized is None:
        return False
    user_id, syllabus_id = normalized

    existing = learning_profile_task.read_profile_personal_syllabus(user_id, syllabus_id, hydrate=False)
    if isinstance(existing, dict):
        return _get_personal_syllabus_path(user_id, syllabus_id) or False

    created = learning_profile_task.init_profile_personal_syllabus(user_id, syllabus_id)
    if not isinstance(created, dict):
        return False
    return created.get("personal_syllabus_path") or False


def _get_personal_syllabus_detail_for_display(user_id: int, syllabus_id: int):
    normalized = _coerce_positive_ids(user_id, syllabus_id)
    if normalized is None:
        return None
    user_id, syllabus_id = normalized

    personal = learning_profile_task.read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)
    if isinstance(personal, dict):
        return personal

    created = learning_profile_task.init_profile_personal_syllabus(user_id, syllabus_id)
    if not isinstance(created, dict):
        return None

    personal = learning_profile_task.read_profile_personal_syllabus(user_id, syllabus_id, hydrate=True)
    if isinstance(personal, dict):
        return personal
    fallback = created.get("personal_syllabus")
    return fallback if isinstance(fallback, dict) else None


def _positive_int_or_none(value):
    try:
        normalized = int(value)
    except Exception:
        return None
    return normalized if normalized > 0 else None


@bp.route('/learning_init_personal_syllabus', methods=['POST'])
def init_personal_syllabus_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')

    if not user_id or not syllabus_id:
        return jsonify({
            'success': False,
            'syllabus': None,
            'error_message': 'missing user_id/syllabus_id',
            'error_code': 'missing_fields'
        }), 400

    try:
        personal_path = _init_personal_syllabus_for_display(int(user_id), int(syllabus_id))
        if not personal_path:
            return jsonify({
                'success': False,
                'syllabus': None,
                'error_message': 'init failed',
                'error_code': 'init_failed'
            }), 500

        return jsonify({
            'success': True,
            'syllabus': {
                'user_id': int(user_id),
                'syllabus_id': int(syllabus_id),
                'personal_syllabus_path': personal_path
            },
            'error_message': '',
            'error_code': ''
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'syllabus': None,
            'error_message': str(e),
            'error_code': 'exception'
        }), 500


@bp.route('/learning_personal_syllabus_detail', methods=['POST'])
def get_personal_syllabus_detail_info_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')

    if not user_id or not syllabus_id:
        return jsonify({
            'success': False,
            'syllabus': None,
            'error_message': 'missing user_id/syllabus_id',
            'error_code': 'missing_fields'
        }), 400

    try:
        syllabus = _get_personal_syllabus_detail_for_display(int(user_id), int(syllabus_id))
        if syllabus is None:
            return jsonify({
                'success': False,
                'syllabus': None,
                'error_message': 'not found',
                'error_code': 'not_found'
            }), 404

        return jsonify({
            'success': True,
            'syllabus': syllabus,
            'error_message': '',
            'error_code': ''
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'syllabus': None,
            'error_message': str(e),
            'error_code': 'exception'
        }), 500


@bp.route('/learning_ask_question', methods=['POST'])
def ask_question_api():
    """Deprecated legacy endpoint.

    Learning Q&A will be owned by the future total agent. Keep this route only
    to make the deprecation explicit for older clients.
    """
    return jsonify({
        'success': False,
        'answer': '',
        'matched_files': [],
        'raw': None,
        'error_message': 'learning_ask_question is deprecated; use the total agent flow',
        'error_code': 'deprecated'
    }), 410


@bp.route('/learning_update_personal_syllabus', methods=['POST'])
def update_personal_syllabus_api():
    """Deprecated legacy endpoint.

    Manual learning record / study-time updates are no longer supported.
    Personal syllabus changes should come from the profile agent or total agent.
    """
    return jsonify({
        'success': False,
        'syllabus': None,
        'error_message': 'learning_update_personal_syllabus is deprecated; manual learning record updates are no longer supported',
        'error_code': 'deprecated'
    }), 410


@bp.route('/personal_recommendation', methods=['POST'])
def personal_recommendation_api():
    """Generate personalized recommendation paths for a user.

    输入（JSON）:
      - user_id: int (required)
      - syllabus_id: int (optional)
      - goals: [str,...] (optional)
      - K / max_candidates, L_max, T_max, beam_width 等可选参数

    输出（JSON）:
      - success: bool
      - candidates: list of {path,cost,skills,scores}
      - selected: list of selected paths
    """
    data = request.get_json(silent=True) or {}
    result = run_recommendation_route_from_payload(data)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@bp.route('/recommendations', methods=['GET'])
def list_recommendations_api():
    user_id = _positive_int_or_none(request.args.get('user_id'))
    if user_id is None:
        return jsonify({
            'success': False,
            'snapshots': [],
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400
    syllabus_id = _positive_int_or_none(request.args.get('syllabus_id'))
    limit = _positive_int_or_none(request.args.get('limit')) or 20
    result = list_recommendation_snapshots(user_id, syllabus_id, limit)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@bp.route('/recommendations/<recommendation_id>', methods=['GET'])
def get_recommendation_api(recommendation_id):
    result = get_recommendation_snapshot(recommendation_id)
    status_code = 200 if result.get('success') else 404
    return jsonify(result), status_code


@bp.route('/recommendations/<recommendation_id>/accept', methods=['POST'])
def accept_recommendation_api(recommendation_id):
    data = request.get_json(silent=True) or {}
    user_id = _positive_int_or_none(data.get('user_id'))
    if user_id is None:
        return jsonify({
            'success': False,
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400
    syllabus_id = _positive_int_or_none(data.get('syllabus_id'))
    candidate_index = data.get('candidate_index')
    result = accept_recommendation_snapshot_path(user_id, syllabus_id, recommendation_id, candidate_index)
    status_code = 200 if result.get('success') else 400
    if result.get('error_code') == 'recommendation_snapshot_not_found':
        status_code = 404
    return jsonify(result), status_code


@bp.route('/learning_plan', methods=['GET'])
def learning_plan_api():
    """返回用户当前激活的学习计划。

    Query params: user_id (required), syllabus_id (optional)
    """
    user_id = _positive_int_or_none(request.args.get('user_id'))
    if user_id is None:
        return jsonify({
            'success': False,
            'plan': None,
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400
    syllabus_id = _positive_int_or_none(request.args.get('syllabus_id'))
    plan = get_active_learning_plan(user_id, syllabus_id)
    if plan is None:
        return jsonify({
            'success': True,
            'plan': {'steps': []},
            'error_message': '',
            'error_code': ''
        })
    return jsonify({
        'success': True,
        'plan': plan,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/knowledge/search', methods=['GET'])
def knowledge_search():
    """知识库检索 — search_tool + 文件匹配。

    Query params: q (required), graph_name (default RAG), top_k (default 5), match_files (default true)
    """
    import re
    from extensions import db
    from schemas.agent_runtime_state import GeneratedResource

    query = str(request.args.get('q') or '').strip()
    if not query:
        return jsonify({'success': False, 'results': [], 'error': 'missing q'}), 400
    graph_name = str(request.args.get('graph_name') or 'RAG').strip()
    top_k = int(request.args.get('top_k') or 5)
    match_files = str(request.args.get('match_files') or '1') in ('1', 'true', 'yes')

    try:
        result = search_tool(query, graph_name=graph_name, top_k=top_k)
    except Exception as exc:
        return jsonify({'success': False, 'results': [], 'error': str(exc)}), 500

    # ── 文件匹配：从 paragraphs 中提取 [文件名]，匹配知识源 + 生成资源 ──
    matched_sources: list[dict] = []
    if match_files and result.get("success"):
        source_names: set[str] = set()
        for p in result.get("paragraphs", []):
            for m in re.finditer(r'\(\[(.+?)\]\)', str(p)):
                source_names.add(m.group(1))
        if source_names:
            try:
                # 1) 知识源文件（可下载的原始文档）
                from schemas.file import File as KnowledgeFile
                for src in source_names:
                    rows = KnowledgeFile.query.filter(
                        KnowledgeFile.path.contains(src)
                    ).limit(3).all()
                    for row in rows:
                        matched_sources.append({
                            "kind": "knowledge_source",
                            "file_id": row.file_id,
                            "path": row.path or "",
                            "matched_source": src,
                            "download_url": f"/api/file_download?file_id={row.file_id}",
                        })
            except Exception:
                pass

            try:
                # 2) 生成资源（学生可用的学习资料）
                for src in source_names:
                    rows = GeneratedResource.query.filter(
                        db.or_(
                            GeneratedResource.title.contains(src),
                            GeneratedResource.topic.contains(src),
                        )
                    ).limit(5).all()
                    for row in rows:
                        main_files = {}
                        try:
                            main_files = __import__("json").loads(row.main_files_json or "{}")
                        except Exception:
                            pass
                        matched_sources.append({
                            "kind": "generated_resource",
                            "resource_id": row.resource_id,
                            "resource_type": row.resource_type,
                            "title": row.title or "",
                            "topic": row.topic or "",
                            "matched_source": src,
                            "main_files": main_files,
                            "created_at": row.created_at,
                        })
            except Exception:
                pass

    result["matched_sources"] = matched_sources[:15]
    return jsonify(result)
