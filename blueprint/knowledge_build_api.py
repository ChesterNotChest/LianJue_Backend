from flask import Blueprint, request, jsonify
from tasks import graph_task, jobs_task


def _parse_job_id(value):
    try:
        job_id = int(value)
    except (TypeError, ValueError):
        return None
    return job_id if job_id > 0 else None


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', '1', 'yes'):
            return True
        if normalized in ('false', '0', 'no', ''):
            return False
    raise ValueError('invalid boolean value')


bp = Blueprint('knowledge_build_api', __name__, url_prefix='/api')


@bp.route('/job_delete', methods=['POST'])
def delete_job_api():
    data = request.get_json(silent=True) or {}
    job_id = _parse_job_id(data.get('job_id'))

    if not job_id:
        return jsonify({
            'success': False,
            'deleted': False,
            'error_message': 'missing job_id',
            'error_code': 'missing_fields',
        }), 400

    try:
        force = _parse_bool(data.get('force', False))
    except ValueError:
        return jsonify({
            'success': False,
            'deleted': False,
            'error_message': 'invalid force',
            'error_code': 'invalid_fields',
        }), 400

    job_status = jobs_task.get_job_status(job_id)
    if job_status is None:
        return jsonify({
            'success': True,
            'deleted': False,
            'error_message': '',
            'error_code': '',
        }), 200

    if not force and job_status != 'failed':
        return jsonify({
            'success': False,
            'deleted': False,
            'error_message': 'only failed jobs can be deleted',
            'error_code': 'invalid_state',
        }), 400

    try:
        jobs_task.purge_job_record(job_id)
    except Exception:
        return jsonify({
            'success': False,
            'deleted': False,
            'error_message': 'delete job failed',
            'error_code': 'delete_failed',
        }), 500

    return jsonify({
        'success': True,
        'deleted': True,
        'error_message': '',
        'error_code': '',
    }), 200


# 创建新的图谱

# 展示所有图谱
# TODO
# def list_graphs_brief_info_api():

# 理论先执行file_transmit_api里的上传，再执行这个，再来做图谱构建的job管理接口
@bp.route('/job_graph_create', methods=['POST'])
def create_graph_api():
    data = request.get_json(silent=True) or {}
    graph_name = data.get('graph_name')

    if graph_name is None or str(graph_name).strip() == '':
        return jsonify({
            'success': False,
            'graph': None,
            'error_message': 'missing graph_name',
            'error_code': 'missing_fields'
        }), 400

    try:
        graph = graph_task.create_graph(str(graph_name))
        if not graph:
            return jsonify({
                'success': False,
                'graph': None,
                'error_message': 'create graph failed',
                'error_code': 'create_failed'
            }), 500

        return jsonify({
            'success': True,
            'graph': {
                'graph_id': getattr(graph, 'graph_id', None),
                'graph_name': getattr(graph, 'graphId', None)
            },
            'error_message': '',
            'error_code': ''
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'graph': None,
            'error_message': str(e),
            'error_code': 'exception'
        }), 500

@bp.route('/job_graph_list', methods=['GET'])
def list_graphs_brief_info_api():
    try:
        rows = graph_task.list_graphs_brief_info()
        return jsonify({
            'success': True,
            'graphs': rows,
            'error_message': '',
            'error_code': ''
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'graphs': [],
            'error_message': str(e),
            'error_code': 'exception'
        }), 500


@bp.route('/job_create', methods=['POST'])
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


@bp.route('/job_pause', methods=['POST'])
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


@bp.route('/job_resume', methods=['POST'])
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


@bp.route('/job_end', methods=['POST'])
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


@bp.route('/job_detail', methods=['POST'])
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


@bp.route('/job_list', methods=['GET'])
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
