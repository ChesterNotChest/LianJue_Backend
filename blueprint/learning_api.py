from flask import Blueprint, jsonify, request

from repositories.user_syllabus_repo import get_user_syllabus
from tasks import learning_profile_task
from tasks.personal_recommendation_task import (
    RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
    RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED,
    accept_recommendation_snapshot_path,
    get_recommendation_snapshot,
    list_recommendation_snapshots,
    run_recommendation_route_from_payload,
    save_recommendation_snapshot,
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
    if (
        result.get('success')
        and data.get('persist_snapshot') is not False
        and isinstance(result.get('graph'), dict)
        and isinstance(result.get('graph', {}).get('nodes'), list)
    ):
        try:
            snapshot = save_recommendation_snapshot(
                int(data.get('user_id')),
                int(data['syllabus_id']) if data.get('syllabus_id') else None,
                result,
                request_payload=data,
                session_id=data.get('session_id'),
                status=RECOMMENDATION_SNAPSHOT_STATUS_PROPOSED,
            )
            if snapshot.get('success'):
                result['recommendation_id'] = snapshot.get('recommendation_id')
                result['snapshot_status'] = snapshot.get('status')
            else:
                warnings = result.setdefault('warnings', [])
                if isinstance(warnings, list):
                    warnings.append(RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED)
        except Exception:
            warnings = result.setdefault('warnings', [])
            if isinstance(warnings, list):
                warnings.append(RECOMMENDATION_SNAPSHOT_WARNING_SAVE_FAILED)
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
