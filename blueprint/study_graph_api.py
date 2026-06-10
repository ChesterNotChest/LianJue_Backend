from flask import Blueprint, jsonify, request

from tasks.study_graph_task import get_student_learning_graph, get_learning_tree_features, run_student_agent


bp = Blueprint('study_graph_api', __name__, url_prefix='/api')


def _parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    return default


def _parse_positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_ids(data):
    user_id = _parse_positive_int(data.get('user_id'))
    syllabus_id = _parse_positive_int(data.get('syllabus_id'))
    return user_id, syllabus_id


@bp.route('/study_graph/detail', methods=['GET'])
def study_graph_detail_api():
    data = request.args or {}
    user_id, syllabus_id = _extract_ids(data)
    if not user_id or not syllabus_id:
        return jsonify({
            'success': False,
            'graph': None,
            'error_message': 'missing user_id/syllabus_id',
            'error_code': 'missing_fields',
        }), 400

    include_debug = _parse_bool(data.get('include_debug'), default=False)
    try:
        result = get_student_learning_graph(user_id, syllabus_id, include_debug=include_debug)
        status_code = 200 if result.get('success') else 400
        return jsonify({
            'success': bool(result.get('success')),
            'graph': result,
            'error_message': result.get('error_message') or '',
            'error_code': result.get('error_code') or '',
        }), status_code
    except Exception as e:
        return jsonify({
            'success': False,
            'graph': None,
            'error_message': str(e),
            'error_code': 'exception',
        }), 500


@bp.route('/study_graph/features', methods=['GET'])
def study_graph_features_api():
    data = request.args or {}
    user_id, syllabus_id = _extract_ids(data)
    if not user_id or not syllabus_id:
        return jsonify({
            'success': False,
            'features': None,
            'error_message': 'missing user_id/syllabus_id',
            'error_code': 'missing_fields',
        }), 400

    try:
        result = get_learning_tree_features(user_id, syllabus_id)
        status_code = 200 if result.get('success') else 400
        return jsonify({
            'success': bool(result.get('success')),
            'features': {key: value for key, value in result.items() if key != 'success'},
            'error_message': result.get('error_message') or '',
            'error_code': result.get('error_code') or '',
        }), status_code
    except Exception as e:
        return jsonify({
            'success': False,
            'features': None,
            'error_message': str(e),
            'error_code': 'exception',
        }), 500


@bp.route('/study_graph/agent_run', methods=['POST'])
def study_graph_agent_run_api():
    data = request.get_json(silent=True) or {}
    user_id, syllabus_id = _extract_ids(data)
    if not user_id or not syllabus_id:
        return jsonify({
            'success': False,
            'result': None,
            'error_message': 'missing user_id/syllabus_id',
            'error_code': 'missing_fields',
        }), 400

    try:
        result = run_student_agent(data)
        result_payload = result.model_dump() if hasattr(result, 'model_dump') else dict(result)
        status_code = 200 if result_payload.get('success') else 400
        return jsonify({
            'success': bool(result_payload.get('success')),
            'result': result_payload,
            'tree': result_payload.get('tree'),
            'features': result_payload.get('features'),
            'changes': result_payload.get('changes') or [],
            'tool_trace': result_payload.get('tool_trace') or [],
            'error_message': result_payload.get('error_message') or '',
            'error_code': result_payload.get('error_code') or '',
        }), status_code
    except Exception as e:
        return jsonify({
            'success': False,
            'result': None,
            'error_message': str(e),
            'error_code': 'exception',
        }), 500