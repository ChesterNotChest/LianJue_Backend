from flask import Blueprint, request, jsonify
from tasks import jobs_task


bp = Blueprint('knowledge_build_api', __name__, url_prefix='/api/job')


# 创建新的图谱
# TODO
# def create_graph_api():

# 展示所有图谱
# TODO
# def list_graphs_api():

@bp.route('/create', methods=['POST'])
def create_job_api():
    '''
    通讯格式：
    输入：
    {
        "graph_id": int,    # 必须
        "file_id": int,     # 必须
        "end_stage": string  # 可选，默认走到 knowledge_to_save
    }

    输出：
    {
        "success": true | false,
        "job": {"job_id": 123} | null,
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = request.get_json(silent=True) or {}
    graph_id = data.get('graph_id')
    file_id = data.get('file_id')
    end_stage = data.get('end_stage')

    if not graph_id or not file_id:
        return jsonify({
            'success': False,
            'job': None,
            'error_message': 'missing graph_id/file_id',
            'error_code': 'missing_fields'
        }), 400

    try:
        jid = jobs_task.create_process_job(graph_id=int(graph_id), file_id=int(file_id), end_stage=end_stage)
        if not jid:
            return jsonify({
                'success': False,
                'job': None,
                'error_message': 'create job failed',
                'error_code': 'create_failed'
            }), 500
        return jsonify({
            'success': True,
            'job': {'job_id': jid},
            'error_message': '',
            'error_code': ''
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'job': None,
            'error_message': str(e),
            'error_code': 'exception'
        }), 500


@bp.route('/pause', methods=['POST'])
def pause_job_api():
    '''
    通讯格式：
    输入：{ "job_id": int }

    输出：
    {
        "success": true | false,
        "job": {"job_id": 123} | null,
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'success': False, 'job': None, 'error_message': 'missing job_id', 'error_code': 'missing_fields'}), 400
    try:
        jobs_task.pause_job(int(job_id))
        return jsonify({'success': True, 'job': {'job_id': int(job_id)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'job': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/resume', methods=['POST'])
def resume_job_api():
    '''
    通讯格式：
    输入：{ "job_id": int }

    输出：
    {
        "success": true | false,
        "job": {"job_id": 123} | null,
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'success': False, 'job': None, 'error_message': 'missing job_id', 'error_code': 'missing_fields'}), 400
    try:
        jobs_task.resume_job(int(job_id))
        return jsonify({'success': True, 'job': {'job_id': int(job_id)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'job': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/end', methods=['POST'])
def end_job_api():
    '''
    通讯格式：
    输入：{ "job_id": int }

    输出：
    {
        "success": true | false,
        "job": {"job_id": 123} | null,
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'success': False, 'job': None, 'error_message': 'missing job_id', 'error_code': 'missing_fields'}), 400
    try:
        jobs_task.end_job(int(job_id))
        return jsonify({'success': True, 'job': {'job_id': int(job_id)}, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'job': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/detail', methods=['POST'])
def get_job_api():
    '''
    通讯格式：
    输入：{ "job_id": int }

    输出：
    {
        "success": true | false,
        "job": { ... } | null,
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    if not job_id:
        return jsonify({'success': False, 'job': None, 'error_message': 'missing job_id', 'error_code': 'missing_fields'}), 400
    try:
        info = jobs_task.get_job_detail_info(int(job_id))
        if not info:
            return jsonify({'success': False, 'job': None, 'error_message': 'not found', 'error_code': 'not_found'}), 404
        return jsonify({'success': True, 'job': info, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'job': None, 'error_message': str(e), 'error_code': 'exception'}), 500


@bp.route('/list', methods=['GET'])
def list_jobs_api():
    '''
    通讯格式：
    支持可选查询参数：`graph_id`, `file_id`, `status`

    输出：
    {
        "success": true | false,
        "jobs": [ {...}, ... ] | [],
        "error_message": "描述性错误信息",
        "error_code": "短错误码"
    }
    '''
    try:
        params = {}
        for k in ('graph_id', 'file_id'):
            v = request.args.get(k)
            if v is not None and v != '':
                try:
                    params[k] = int(v)
                except Exception:
                    params[k] = v
        # status may be string
        status = request.args.get('status')
        if status:
            params['status'] = status

        rows = jobs_task.list_all_jobs(**params)
        # rows may be model objects; convert to dicts using get_job_detail_info
        out = []
        for r in rows:
            try:
                out.append(jobs_task.get_job_detail_info(r.job_id))
            except Exception:
                out.append({'job_id': getattr(r, 'job_id', None)})

        return jsonify({'success': True, 'jobs': out, 'error_message': '', 'error_code': ''}), 200
    except Exception as e:
        return jsonify({'success': False, 'jobs': [], 'error_message': str(e), 'error_code': 'exception'}), 500
