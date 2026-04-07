from flask import Blueprint, jsonify, request

from tasks import learning_task


bp = Blueprint('learning_api', __name__, url_prefix='/api/learning')


@bp.route('/init_personal_syllabus', methods=['POST'])
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


@bp.route('/personal_syllabus/detail', methods=['POST'])
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
