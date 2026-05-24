from flask import Blueprint, jsonify, request

from tasks import learning_task
from tasks.personal_recommendation_task import run_recommendation_route_from_payload


bp = Blueprint('learning_api', __name__, url_prefix='/api')


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
        personal_path = learning_task.init_personal_syllabus(int(user_id), int(syllabus_id))
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
        syllabus = learning_task.get_personal_syllabus_detail_info(int(user_id), int(syllabus_id))
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
      - max_candidates, beam_width 等可选参数

    输出（JSON）:
      - success: bool
      - candidates: list of {path,cost,skills,scores}
      - selected: list of selected paths
    """
    data = request.get_json(silent=True) or {}
    result = run_recommendation_route_from_payload(data)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code
