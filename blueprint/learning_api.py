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


@bp.route('/ask_question', methods=['POST'])
def ask_question_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')
    question = data.get('question')

    if not user_id or not syllabus_id or question is None or str(question).strip() == '':
        return jsonify({
            'success': False,
            'answer': '',
            'matched_files': [],
            'raw': None,
            'error_message': 'missing user_id/syllabus_id/question',
            'error_code': 'missing_fields'
        }), 400

    try:
        result = learning_task.ask_question(int(user_id), int(syllabus_id), str(question))
        if result is None:
            return jsonify({
                'success': False,
                'answer': '',
                'matched_files': [],
                'raw': None,
                'error_message': 'ask question failed',
                'error_code': 'ask_failed'
            }), 500

        return jsonify({
            'success': True,
            'answer': result.get('answer', ''),
            'matched_files': result.get('matched_files', []),
            'raw': result.get('raw'),
            'error_message': '',
            'error_code': ''
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'answer': '',
            'matched_files': [],
            'raw': None,
            'error_message': str(e),
            'error_code': 'exception'
        }), 500


@bp.route('/update_personal_syllabus', methods=['POST'])
def update_personal_syllabus_api():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')
    week_index = data.get('week_index')
    study_time_spent = data.get('study_time_spent', -1)

    if not user_id or not syllabus_id or week_index is None:
        return jsonify({
            'success': False,
            'syllabus': None,
            'error_message': 'missing user_id/syllabus_id/week_index',
            'error_code': 'missing_fields'
        }), 400

    try:
        syllabus = learning_task.update_personal_syllabus(
            int(user_id),
            int(syllabus_id),
            int(week_index),
            study_time_spent=int(study_time_spent),
        )
        if syllabus is None:
            return jsonify({
                'success': False,
                'syllabus': None,
                'error_message': 'update failed',
                'error_code': 'update_failed'
            }), 400

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
