from flask import Blueprint, request, jsonify
from tasks import syllabus_task, material_gen_task, material_task


bp = Blueprint('syllabus_material_api', __name__, url_prefix='/api')


@bp.route('/syllabus_build_draft', methods=['POST'])
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
    try:
        s = syllabus_task.update_syllabus_draft_json(int(syllabus_id), syllabus_draft_json)
        if not s:
            return jsonify({'success': False, 'syllabus': None, 'error_message': 'update failed', 'error_code': 'update_failed'}), 400
        return jsonify({'success': True, 'syllabus': {'syllabus_id': getattr(s, 'syllabus_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'syllabus': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_update', methods=['POST'])
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
    输入：{ } (可选过滤字段 future)

    输出：{ "success": true|false, "syllabuses": [ {...} ], "error_message": "", "error_code": "" }
    '''
    try:
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id')
        manage_raw = data.get('manage', False)
        if isinstance(manage_raw, bool):
            manage = manage_raw
        elif isinstance(manage_raw, int) and manage_raw in (0, 1):
            manage = bool(manage_raw)
        elif isinstance(manage_raw, str):
            normalized = manage_raw.strip().lower()
            if normalized in ('true', '1', 'yes', 'y', 'on'):
                manage = True
            elif normalized in ('false', '0', 'no', 'n', 'off', ''):
                manage = False
            else:
                return jsonify({'success': False, 'syllabuses': [], 'error_message': 'invalid manage', 'error_code': 'invalid_fields'}), 400
        else:
            return jsonify({'success': False, 'syllabuses': [], 'error_message': 'invalid manage', 'error_code': 'invalid_fields'}), 400
        if user_id is not None:
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'syllabuses': [], 'error_message': 'invalid user_id', 'error_code': 'invalid_fields'}), 400
        elif manage:
            return jsonify({'success': False, 'syllabuses': [], 'error_message': 'missing user_id for manage view', 'error_code': 'missing_fields'}), 400
        rows = syllabus_task.list_all_syllabuses_brief_info(user_id=user_id, manage=manage)
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
    if not request.is_json:
        return jsonify({'success': False, 'material': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    syllabus_id = data.get('syllabus_id')
    involved_weeks = data.get('involved_weeks')
    distribution = data.get('question_type_distribution')
    if not syllabus_id or not isinstance(involved_weeks, list) or not isinstance(distribution, dict):
        return jsonify({'success': False, 'material': None, 'error_message': 'missing or invalid fields', 'error_code': 'missing_fields'}), 400
    try:
        m = material_gen_task.generate_material_draft(int(syllabus_id), involved_weeks, distribution)
        if not m:
            return jsonify({'success': False, 'material': None, 'error_message': 'generate draft failed', 'error_code': 'generate_failed'}), 500
        return jsonify({'success': True, 'material': {'material_id': getattr(m, 'material_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


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
    if not request.is_json:
        return jsonify({'success': False, 'material': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    material_draft_json = data.get('material_draft_json')
    if not material_id or not isinstance(material_draft_json, dict):
        return jsonify({'success': False, 'material': None, 'error_message': 'missing material_id/material_draft_json', 'error_code': 'missing_fields'}), 400
    try:
        m = material_gen_task.update_material_draft_json(int(material_id), material_draft_json)
        if not m:
            return jsonify({'success': False, 'material': None, 'error_message': 'update failed', 'error_code': 'update_failed'}), 400
        return jsonify({'success': True, 'material': {'material_id': getattr(m, 'material_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_material_update', methods=['POST'])
def update_final_material_api():
    if not request.is_json:
        return jsonify({'success': False, 'material': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    material_json = data.get('material_json')
    if not material_id or not isinstance(material_json, dict):
        return jsonify({'success': False, 'material': None, 'error_message': 'missing material_id/material_json', 'error_code': 'missing_fields'}), 400
    try:
        m = material_gen_task.update_final_material_json(int(material_id), material_json)
        if not m:
            return jsonify({'success': False, 'material': None, 'error_message': 'update failed', 'error_code': 'update_failed'}), 400
        return jsonify({'success': True, 'material': {'material_id': getattr(m, 'material_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_material_draft_detail', methods=['POST'])
def get_material_draft_detail_api():
    '''
    通讯格式：输入：{ "material_id": int }
    输出：{ "success": true|false, "material_draft": {...}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'material_draft': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    if not material_id:
        return jsonify({'success': False, 'material_draft': None, 'error_message': 'missing material_id', 'error_code': 'missing_fields'}), 400
    try:
        info = material_gen_task.get_material_draft_detail_info(int(material_id))
        if not info:
            return jsonify({'success': False, 'material_draft': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'material_draft': info, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material_draft': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_material_generate_final', methods=['POST'])
def generate_final_material_api():
    '''
    通讯格式：
    输入：{ "material_id": int }

    输出：{ "success": true|false, "material": {"material_id": int}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'material': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    if not material_id:
        return jsonify({'success': False, 'material': None, 'error_message': 'missing material_id', 'error_code': 'missing_fields'}), 400
    try:
        m = material_gen_task.generate_final_material(int(material_id))
        if not m:
            return jsonify({'success': False, 'material': None, 'error_message': 'generate final failed', 'error_code': 'generate_failed'}), 500
        return jsonify({'success': True, 'material': {'material_id': getattr(m, 'material_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_material_publish', methods=['POST'])
def publish_material_api():
    '''
    通讯格式：
    输入: { "material_id": int, "new_pdf": bool (optional), "do_publish": bool (optional) }

    输出: { "success": true|false, "material": {"material_id": int}|null, "error_message": "", "error_code": "" }
    '''
    if not request.is_json:
        return jsonify({'success': False, 'material': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    if not material_id:
        return jsonify({'success': False, 'material': None, 'error_message': 'missing material_id', 'error_code': 'missing_fields'}), 400
    try:
        m = material_gen_task.publish_material(int(material_id), new_pdf=bool(data.get('new_pdf')), do_publish=bool(data.get('do_publish')))
        if not m:
            return jsonify({'success': False, 'material': None, 'error_message': 'publish failed', 'error_code': 'publish_failed'}), 500
        return jsonify({'success': True, 'material': {'material_id': getattr(m, 'material_id', None)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


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
    if not material_id:
        return jsonify({'success': False, 'material': None, 'error_message': 'missing material_id', 'error_code': 'missing_fields'}), 400
    try:
        info = material_gen_task.get_material_detail_info(int(material_id))
        if not info:
            return jsonify({'success': False, 'material': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'material': info, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'material': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/syllabus_material_status', methods=['POST'])
def get_material_status_api():
    if not request.is_json:
        return jsonify({'success': False, 'status': None, 'error_message': 'invalid json', 'error_code': 'invalid_json'}), 400
    data = request.get_json()
    material_id = data.get('material_id')
    if not material_id:
        return jsonify({'success': False, 'status': None, 'error_message': 'missing material_id', 'error_code': 'missing_fields'}), 400
    try:
        status = material_task.get_material_status(int(material_id))
        if status is None:
            return jsonify({'success': False, 'status': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'status': status, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'status': None, 'error_message': str(e), 'error_code': 'exception'}), 500


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
    try:
        if syllabus_id:
            rows = material_gen_task.list_materials_draft_brief_info(int(syllabus_id))
        else:
            # list all materials is not directly implemented; fall back to empty list
            rows = []
        return jsonify({'success': True, 'materials': rows, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'materials': [], 'error_message': str(e), 'error_code': 'exception'}), 500
