from flask import Blueprint, request, jsonify
from tasks import generative_task, syllabus_task
from utils.auth import require_operator
from constant import SyllabusStatus

bp = Blueprint('syllabus_material_api', __name__, url_prefix='/api')


def _check_not_published(syllabus_id):
    """Return error_response if syllabus is published/locked, else None."""
    from repositories.syllabus_repo import get_syllabus_by_id
    syllabus = get_syllabus_by_id(syllabus_id)
    if syllabus and getattr(syllabus, 'status', None) == SyllabusStatus.PUBLISHED.value:
        return jsonify({
            'success': False, 'syllabus': None,
            'error_message': '已发布的学科不可编辑',
            'error_code': 'syllabus_locked',
        }), 403
    return None


@bp.route('/syllabus_build_draft', methods=['POST'])
@require_operator
def build_syllabus_draft_api():
    '''
    通讯格式：
    输入：
    {
        "syllabus_id": int,   # 必须
        "graph_id": int,      # 必须
        "initial_prompt": string  # 可选，生成草稿的附加说明
    }

    输出：
    {
        "success": true | false,
        "syllabus": {"syllabus_id": int} | null,
        "error_message": string,
        "error_code": string
    }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    graph_id = data.get('graph_id')
    initial_prompt = data.get('initial_prompt') or ''
    if not syllabus_id or not graph_id:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'missing syllabus_id/graph_id', 'error_code': 'missing_fields'}), 400
    try:
        s = syllabus_task.build_syllabus_draft(int(syllabus_id), int(graph_id), initial_prompt)
        if not s:
            return jsonify({'success': False, 'syllabus': None, 'error_message': 'build draft failed', 'error_code': 'build_failed'}), 500
        return jsonify({'success': True, 'syllabus': {'syllabus_id': getattr(s, 'syllabus_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_build', methods=['POST'])
@require_operator
def build_syllabus_api():
    '''
    通讯格式：
    输入：
    { "syllabus_id": int, "graph_name": string (optional) }

    输出：
    { "success": true|false, "syllabus": {"syllabus_id": int}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    if not syllabus_id:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'missing syllabus_id', 'error_code': 'missing_fields'}), 400
    try:
        s = syllabus_task.build_syllabus(int(syllabus_id))
        if not s:
            return jsonify({'success': False, 'syllabus': None, 'error_message': 'build failed', 'error_code': 'build_failed'}), 500
        return jsonify({'success': True, 'syllabus': {'syllabus_id': getattr(s, 'syllabus_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_update_draft', methods=['POST'])
@require_operator
def update_syllabus_draft_api():
    '''
    通讯格式：
    输入：
    {
        "syllabus_id": int, "week_index": str,
        "day_one": string (optional), "new_content": string (optional), "new_importance": string (optional), "new_title": string (optional)
    }

    输出：
    { "success": true|false, "syllabus": {"syllabus_id": int}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    syllabus_draft_json = data.get('syllabus_draft_json')
    if not syllabus_id or not isinstance(syllabus_draft_json, dict):
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'missing syllabus_id/syllabus_draft_json', 'error_code': 'missing_fields'}), 400
    locked = _check_not_published(int(syllabus_id))
    if locked:
        return locked
    try:
        s = syllabus_task.update_syllabus_draft_json(int(syllabus_id), syllabus_draft_json)
        if not s:
            return jsonify({'success': False, 'syllabus': None, 'error_message': 'update failed', 'error_code': 'update_failed'}), 400
        return jsonify({'success': True, 'syllabus': {'syllabus_id': getattr(s, 'syllabus_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_update', methods=['POST'])
@require_operator
def update_syllabus_api():
    '''
    Input:
        {
            "syllabus_id": int,
            optional "title": string,
            optional "day_one": string,
            optional "syllabus_path": string
        }

    Output:
        { "success": true|false, "syllabus": {"syllabus_id": int}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    syllabus_json = data.get('syllabus_json')
    if not syllabus_id or not isinstance(syllabus_json, dict):
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'missing syllabus_id/syllabus_json', 'error_code': 'missing_fields'}), 400
    locked = _check_not_published(int(syllabus_id))
    if locked:
        return locked
    try:
        s = syllabus_task.update_syllabus_json(int(syllabus_id), syllabus_json)
        if not s:
            return jsonify({'success': False, 'syllabus': None, 'error_message': 'update failed', 'error_code': 'update_failed'}), 400
        return jsonify({'success': True, 'syllabus': {'syllabus_id': getattr(s, 'syllabus_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_detail', methods=['POST'])
def get_syllabus_detail_api():
    '''
    通讯格式：
    输入：{ "syllabus_id": int }

    输出：
    { "success": true|false, "syllabus": { ... }|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    if not syllabus_id:
        return jsonify({'success': False, 'syllabus': None, 'error_message': 'missing syllabus_id', 'error_code': 'missing_fields'}), 400
    try:
        info = syllabus_task.get_syllabus_detail_info(int(syllabus_id))
        if info is None:
            return jsonify({'success': False, 'syllabus': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'syllabus': info, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_status', methods=['POST'])
def get_syllabus_status_api():
    if not request.is_json:
        return jsonify({'success': False, 'status': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    if not syllabus_id:
        return jsonify({'success': False, 'status': None, 'error_message': 'missing syllabus_id', 'error_code': 'missing_fields'}), 400
    try:
        status = syllabus_task.get_syllabus_status(int(syllabus_id))
        if status is None:
            return jsonify({'success': False, 'status': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'status': status, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'status': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_draft_detail', methods=['POST'])
def get_syllabus_draft_detail_api():
    '''
    通讯格式：
    输入：{ "syllabus_id": int }

    输出：
    { "success": true|false, "syllabus_draft": { ... }|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'syllabus_draft': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    if not syllabus_id:
        return jsonify({'success': False, 'syllabus_draft': None, 'error_message': 'missing syllabus_id', 'error_code': 'missing_fields'}), 400
    try:
        info = syllabus_task.get_syllabus_draft_detail_info(int(syllabus_id))
        if info is None:
            return jsonify({'success': False, 'syllabus_draft': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'syllabus_draft': info, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus_draft': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_list', methods=['POST'])
def list_syllabuses_api():
    '''
    通讯格式：
    输入：{ "user_id": int (optional) }

    输出：{ "success": true|false, "syllabuses": [ {...} ], "error_message": "", "error_code": "" }
    - user_id 不传：返回所有学科（teacher-style）
    - user_id 为 operator：返回所有学科含 bound_users + status
    - user_id 为普通 user：仅返回已发布且已绑定的学科
    '''
    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id')
        if user_id is not None:
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'syllabuses': [], 'error_message': 'invalid user_id', 'error_code': 'invalid_fields'}), 400
        rows = syllabus_task.list_all_syllabuses_brief_info(user_id=user_id)
        return jsonify({'success': True, 'syllabuses': rows, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabuses': [], 'error_message': str(e), 'error_code': 'exception'}), 500


# Material endpoints under same blueprint but with '/material' prefix
@bp.route('/syllabus_material_generate_draft', methods=['POST'])
def generate_material_draft_api():
    '''
    通讯格式：
    输入：
    {
        "syllabus_id": int,            # 必须
        "involved_weeks": [int, ...],  # 必须
        "question_type_distribution": {"single": int, "judge": int, "short": int}  # 必须
    }

    输出：
    { "success": true|false, "material": {"material_id": int}|null, "error_message": "", "error_code": "" }
    '''
    return jsonify({
        'success': False,
        'material': None,
        'error_message': 'syllabus_material_generate_draft is deprecated; use generative resource agents',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_update_draft', methods=['POST'])
def update_material_draft_api():
    '''
    通讯格式：
    输入：{
        "material_id": int, (required)
        optional fields: "material_title", "new_related_knowledge", "new_query_keys", "involved_weeks"
    }

    输出：{ "success": true|false, "material": {"material_id": int}|null, "error_message": "", "error_code": "" }
    '''
    return jsonify({
        'success': False,
        'material': None,
        'error_message': 'syllabus_material_update_draft is deprecated; generated resources do not use drafts',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_update', methods=['POST'])
def update_final_material_api():
    return jsonify({
        'success': False,
        'material': None,
        'error_message': 'syllabus_material_update is deprecated; generated resources are immutable artifacts',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_draft_detail', methods=['POST'])
def get_material_draft_detail_api():
    '''
    通讯格式：输入：{ "material_id": int }
    输出：{ "success": true|false, "material_draft": {...}|null, "error_message": "", "error_code": "" }
    '''
    return jsonify({
        'success': False,
        'material_draft': None,
        'error_message': 'syllabus_material_draft_detail is deprecated; generated resources do not use drafts',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_generate_final', methods=['POST'])
def generate_final_material_api():
    '''
    通讯格式：
    输入：{ "material_id": int }

    输出：{ "success": true|false, "material": {"material_id": int}|null, "error_message": "", "error_code": "" }
    '''
    return jsonify({
        'success': False,
        'material': None,
        'error_message': 'syllabus_material_generate_final is deprecated; use generative resource agents',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_publish', methods=['POST'])
def publish_material_api():
    '''
    通讯格式：
    输入: { "material_id": int, "new_pdf": bool (optional), "do_publish": bool (optional) }

    输出: { "success": true|false, "material": {"material_id": int}|null, "error_message": "", "error_code": "" }
    '''
    return jsonify({
        'success': False,
        'material': None,
        'error_message': 'syllabus_material_publish is deprecated; render generated resources directly',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_detail', methods=['POST'])
def get_material_detail_api():
    '''
    通讯格式：输入 { "material_id": int }
    输出：{ "success": true|false, "material": {...}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'material': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    user_id = data.get('user_id')
    resource_id = data.get('resource_id')
    if not material_id and not (user_id and resource_id):
        return jsonify({'success': False, 'material': None, 'error_message': 'missing material_id or user_id/resource_id', 'error_code': 'missing_fields'}), 400
    try:
        if user_id and resource_id:
            info = generative_task.get_generated_resource_detail(int(user_id), str(resource_id))
        else:
            return jsonify({
                'success': False,
                'material': None,
                'error_message': 'material_id detail is deprecated; use user_id/resource_id or /api/generative_detail',
                'error_code': 'deprecated',
            }), 410
        if not info:
            return jsonify({'success': False, 'material': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'material': info, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_material_status', methods=['POST'])
def get_material_status_api():
    return jsonify({
        'success': False,
        'status': None,
        'error_message': 'syllabus_material_status is deprecated; generated resources expose status in manifest entries',
        'error_code': 'deprecated',
    }), 410


@bp.route('/syllabus_material_list', methods=['POST'])
def list_materials_api():
    '''
    通讯格式：输入 { "syllabus_id": int } (optional)
    输出：{ "success": true|false, "materials": [...], "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'materials': [], 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    user_id = data.get('user_id')
    resource_type = data.get('resource_type')
    limit = data.get('limit')
    limit_per_type = data.get('limit_per_type')
    group_by_type = bool(data.get('group_by_type'))
    try:
        if user_id and group_by_type:
            rows = generative_task.list_generated_resources_by_type(
                int(user_id),
                syllabus_id=int(syllabus_id) if syllabus_id else None,
                limit_per_type=limit_per_type,
            )
        elif user_id:
            rows = generative_task.list_generated_resources(
                int(user_id),
                syllabus_id=int(syllabus_id) if syllabus_id else None,
                resource_type=str(resource_type) if resource_type else None,
                limit=limit,
            )
        elif syllabus_id:
            rows = []
        else:
            # list all materials is not directly implemented; fall back to empty list
            rows = []
        return jsonify({'success': True, 'materials': rows, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'materials': [], 'error_message': str(e), 'error_code': 'exception'}), 500
