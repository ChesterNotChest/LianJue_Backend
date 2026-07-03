from flask import Blueprint, request, jsonify

from extensions import db
from schemas.user import User
from schemas.user_syllabus import UserSyllabus
from tasks.user_task import (
    register,
    login,
    change_password,
    reset_password,
    update_user_info,
    get_user_detail_info,
    list_all_user_brief_info,
)
from tasks.learning_profile_task import build_learning_profile, get_persisted_learning_profile



bp = Blueprint('user_api', __name__, url_prefix='/api')


def _parse_optional_int(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _learning_profile_response(profile):
    if profile is None:
        return jsonify({
            'success': False,
            'profile': None,
            'error_message': 'not found',
            'error_code': 'not_found'
        }), 404

    return jsonify({
        'success': True,
        'profile': profile,
        'profile_path': profile.get('profile_path') if isinstance(profile, dict) else None,
        'profile_saved': bool(profile.get('profile_saved')) if isinstance(profile, dict) else False,
        'profile_refreshed': bool(profile.get('profile_refreshed')) if isinstance(profile, dict) else False,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_register', methods=['POST'])
def register_api():
    '''
    通讯格式：
    输入：
    {
        "user_name": string,  # 用户名
        "password": string,   # 密码
        "email": string       # 邮箱
    }
    输出：
    {
        "success": boolean,  # 是否注册成功
        "user": {            # 注册成功时返回的用户信息
            "user_id": int,
            "user_name": string,
            "email": string
        },
        "error_message": string, # 注册失败时的错误信息
        "error_code": string  # 注册失败时的错误代码，如 "missing_fields", "duplicate_user", "invalid_email_format" 等
    }
    '''
    data = request.get_json(silent=True) or {}
    username = data.get('user_name') or data.get('username')
    password = data.get('password')
    email = data.get('email')
    if not username or not password or not email:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'missing user_name/password/email',
            'error_code': 'missing_fields'
        }), 400

    u = register(username, password, email)
    if not u:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'create failed or duplicate user',
            'error_code': 'create_failed_or_duplicate'
        }), 400

    return jsonify({
        'success': True,
        'user': u,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_login', methods=['POST'])
def login_api():
    '''
    通讯格式：
    输入：
    {
        "user_name": string,  # 或 "username"
        "password": string
    }
    输出：
    {
        "success": boolean,
        "user": {"user_id": int, "user_name": string, "email": string} | null,
        "error_message": string,
        "error_code": string
    }
    '''
    data = request.get_json(silent=True) or {}
    username = data.get('user_name') or data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'missing user_name/password',
            'error_code': 'missing_fields'
        }), 400
    u = login(username, password)
    if not u:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'invalid credentials',
            'error_code': 'invalid_credentials'
        }), 401
    return jsonify({
        'success': True,
        'user': u,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_change_password', methods=['POST'])
def change_password_api():
    '''
    通讯格式：
    输入：
    {
        "user_id": int,
        "old_password": string,
        "new_password": string
    }
    输出：
    {
        "success": boolean,
        "user": null,
        "error_message": string,
        "error_code": string
    }
    '''
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    if not user_id or not old_password or not new_password:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'missing user_id/old_password/new_password',
            'error_code': 'missing_fields'
        }), 400
    ok = change_password(int(user_id), old_password, new_password)
    if not ok:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'change password failed',
            'error_code': 'change_failed'
        }), 400
    return jsonify({
        'success': True,
        'user': None,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_reset_password', methods=['POST'])
def reset_password_api():
    '''
    通讯格式：
    输入：
    {
        "user_id": int
    }
    输出：
    成功时：
    {
        "success": true,
        "user": null,
        "temporary_password": string,
        "error_message": "",
        "error_code": ""
    }
    失败时：
    {
        "success": false,
        "user": null,
        "error_message": string,
        "error_code": string
    }
    '''
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400
    tmp = reset_password(int(user_id))
    if tmp is None:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'reset failed',
            'error_code': 'reset_failed'
        }), 400
    return jsonify({
        'success': True,
        'user': None,
        'temporary_password': tmp,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_update', methods=['POST'])
def update_user_api():
    '''
    通讯格式：
    输入：
    {
        "user_id": int,
        "user_name": string (optional),
        "email": string (optional)
    }
    输出：
    {
        "success": boolean,
        "user": {"user_id": int, "user_name": string, "email": string} | null,
        "error_message": string,
        "error_code": string
    }
    '''
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400
    user_name = data.get('user_name')
    email = data.get('email')
    updated = update_user_info(int(user_id), user_name=user_name, email=email)
    if not updated:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'update failed',
            'error_code': 'update_failed'
        }), 400
    return jsonify({
        'success': True,
        'user': updated,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_detail', methods=['POST'])
def get_user_api():
    '''
    通讯格式：
    输入：{ "user_id": int }

    输出：
    {
        "success": boolean,
        "user": {"user_id": int, "user_name": string, "email": string, "create_time": string} | null,
        "error_message": string,
        "error_code": string
    }
    '''
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400

    info = get_user_detail_info(int(user_id))
    if not info:
        return jsonify({
            'success': False,
            'user': None,
            'error_message': 'not found',
            'error_code': 'not_found'
        }), 404
    return jsonify({
        'success': True,
        'user': info,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/user_list', methods=['GET'])
def list_users_api():
    '''
    通讯格式：
    输入：
      - 无（可在未来添加分页参数）
    输出：
    {
        "success": boolean,
        "users": [ {"user_id": int, "user_name": string, "email": string, "create_time": string}, ... ],
        "error_message": string,
        "error_code": string
    }
    '''
    rows = list_all_user_brief_info()
    return jsonify({
        'success': True,
        'users': rows,
        'error_message': '',
        'error_code': ''
    })


@bp.route('/learning_profile_detail', methods=['POST'])
def learning_profile_detail_api():
    '''
    Read the persisted learning profile only. This endpoint never triggers the
    learning profile Agent.
    '''
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')
    if not user_id or syllabus_id is None or str(syllabus_id).strip() == '':
        return jsonify({
            'success': False,
            'profile': None,
            'error_message': 'missing user_id/syllabus_id',
            'error_code': 'missing_fields'
        }), 400

    profile = get_persisted_learning_profile(int(user_id), _parse_optional_int(syllabus_id))
    return _learning_profile_response(profile)


@bp.route('/learning_profile_refresh', methods=['POST'])
def learning_profile_refresh_api():
    '''
    Build or refresh the learning profile with the learning profile Agent.
    '''
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')
    if not user_id:
        return jsonify({
            'success': False,
            'profile': None,
            'error_message': 'missing user_id',
            'error_code': 'missing_fields'
        }), 400

    profile = build_learning_profile(
        int(user_id),
        _parse_optional_int(syllabus_id),
        dialogue_text=data.get('dialogue_text'),
        learning_goal=data.get('learning_goal'),
        learning_records=data.get('learning_records'),
        answer_records=data.get('answer_records'),
        resource_usage=data.get('resource_usage'),
    )
    if isinstance(profile, dict):
        profile['profile_refreshed'] = True
    return _learning_profile_response(profile)


def _guess_level(user_name: str) -> str:
    name = (user_name or "").lower()
    if "medium_high" in name or "medium-high" in name:
        return "medium_high"
    if "low_medium" in name or "low-medium" in name:
        return "low_medium"
    if "high" in name:
        return "high"
    if "medium" in name:
        return "medium"
    if "low" in name:
        return "low"
    return "unknown"


@bp.route('/demo_students', methods=['GET'])
def demo_students_api():
    """返回最新的 5 个演示学生（按创建时间倒序）。"""
    users = (
        User.query
        .filter(User.user_name.like('demo_%'))
        .order_by(User.create_time.desc())
        .limit(5)
        .all()
    )
    return jsonify({
        'success': True,
        'students': [
            {
                'user_id': u.user_id,
                'user_name': u.user_name,
                'level': _guess_level(u.user_name),
                'syllabus_ids': [
                    row.syllabus_id
                    for row in UserSyllabus.query
                    .filter_by(user_id=u.user_id)
                    .order_by(UserSyllabus.syllabus_id.asc())
                    .all()
                ],
                'created_at': u.create_time.isoformat() if u.create_time else None,
            }
            for u in users
        ],
        'error_code': '',
        'error_message': '',
    })


@bp.route('/graph/list', methods=['GET'])
def graph_list_api():
    """返回所有可用图谱的元数据列表。"""
    from schemas.graph import Graph

    graphs = Graph.query.all()
    return jsonify({
        'success': True,
        'graphs': [
            {
                'graph_id': g.graph_id,
                'graphId': g.graphId,
                'snapshot_cache_path': g.snapshot_cache_path,
            }
            for g in graphs
        ],
        'error_code': '',
        'error_message': '',
    })


@bp.route('/status/version', methods=['GET'])
def status_version_api():
    """四维版本摘要，供前端心跳轮询 diff。"""
    from tasks.graph_task import get_galaxy_version

    user_id = request.args.get('user_id', type=int)
    syllabus_id = request.args.get('syllabus_id', type=int)

    version = {
        'galaxy_version': get_galaxy_version(),
        'study_graph_version': None,
        'plan_version': None,
        'recommendation_version': None,
    }

    if user_id and syllabus_id:
        try:
            from tasks.study_graph.service import get_learning_tree_features
            features = get_learning_tree_features(user_id, syllabus_id)
            version['study_graph_version'] = str(features.get('updated_at') or '')
        except Exception:
            pass

        try:
            from tasks.personal_recommendation_task import get_active_learning_plan
            plan = get_active_learning_plan(user_id, syllabus_id)
            if plan:
                version['plan_version'] = str(plan.get('plan_id') or 'active')
        except Exception:
            pass

        try:
            from tasks.personal_recommendation_task import list_recommendation_snapshots
            snapshots = list_recommendation_snapshots(user_id, syllabus_id)
            if snapshots:
                version['recommendation_version'] = str((snapshots[0].get('recommendation_id') or ''))
        except Exception:
            pass

    return jsonify({'success': True, 'version': version})


@bp.route('/knowledge-graph/snapshot', methods=['GET'])
def knowledge_graph_snapshot_api():
    """返回指定 graph 的知识图谱快照（合并多个 graph）。

    Query params:
      graph_names: 逗号分隔的 graphId 列表
      refresh: 传 1 强制重新从 AbutionGraph 采集
    首次访问且无缓存时自动触发采集，后续走缓存。
    """
    import json
    from pathlib import Path

    from schemas.graph import Graph
    from repositories.graph_repo import get_graph_by_graphId
    from repositories.syllabus_graph_repo import list_syllabuses_by_graph

    graph_ids_param = request.args.get('graph_ids', '')
    if not graph_ids_param:
        return jsonify({
            'success': False, 'snapshot': None,
            'error_message': 'missing graph_ids parameter', 'error_code': 'missing_graph_ids',
        }), 400

    graph_names = [gid.strip() for gid in graph_ids_param.split(',') if gid.strip()]
    if not graph_names:
        return jsonify({
            'success': False, 'snapshot': None,
            'error_message': 'empty graph_ids', 'error_code': 'empty_graph_ids',
        }), 400

    data_dir = Path(__file__).resolve().parents[1] / 'data' / 'knowledge_graph'
    do_refresh = request.args.get('refresh', '0') == '1'

    # ── helpers ──
    def _resolve_cache_path(name: str) -> Path | None:
        record = get_graph_by_graphId(name)
        if record and getattr(record, 'snapshot_cache_path', None):
            p = Path(record.snapshot_cache_path)
            if not p.is_absolute():
                p = Path(__file__).resolve().parents[1] / p
            if p.exists():
                return p
        for c in [
            data_dir / f'{name.lower()}_probe_full_result.json',
            data_dir / f'{name.lower()}_snapshot_full.json',
        ]:
            if c.exists():
                return c
        for c in data_dir.glob(f'{name.lower()}_*_full_result.json'):
            return c
        return None

    def _build_syllabus_list(name: str) -> list[dict]:
        from repositories.syllabus_repo import get_syllabus_by_id
        result = []
        for sid in list_syllabuses_by_graph(name):
            s = get_syllabus_by_id(sid)
            if s:
                result.append({'syllabus_id': sid, 'title': getattr(s, 'title', f'学科 {sid}')})
        return result

    def _read_snapshot(name: str) -> dict | None:
        cache_path = _resolve_cache_path(name)
        if not cache_path:
            return None
        raw = json.loads(cache_path.read_text(encoding='utf-8'))
        if isinstance(raw, dict) and 'graphSnapshot' in raw:
            raw = raw['graphSnapshot']
        if isinstance(raw, dict) and 'nodes' in raw:
            raw = dict(raw)
            raw['syllabusList'] = _build_syllabus_list(name)
            for node in raw.get('nodes', []):
                if isinstance(node, dict):
                    node.setdefault('meta', {})['graphId'] = name
            return raw
        return None

    refresh_results: dict = {}

    def _refresh_one(name: str) -> dict:
        from tasks.graph_task import refresh_graph_cache
        import logging
        _log = logging.getLogger(__name__)
        try:
            _log.info("refresh_graph_cache: %s starting", name)
            result = refresh_graph_cache(name)
            if result.get("success"):
                _log.info("refresh_graph_cache: %s ok, nodes=%s edges=%s", name, result.get("node_count"), result.get("edge_count"))
            else:
                _log.warning("refresh_graph_cache: %s failed: %s", name, result.get("error"))
            refresh_results[name] = result
            return result
        except Exception as e:
            _log.exception("refresh_graph_cache: %s exception: %s", name, e)
            err = {"success": False, "error": str(e)}
            refresh_results[name] = err
            return err

    # ── main: read cache (with auto-refresh on miss) ──
    if do_refresh:
        for graph_name in graph_names:
            _refresh_one(graph_name)

    snapshots = []
    missing = []

    for graph_name in graph_names:
        snap = _read_snapshot(graph_name)
        if snap:
            snapshots.append(snap)
        else:
            missing.append(graph_name)

    # Auto-refresh on first miss (best-effort, never blocks)
    if missing and not do_refresh:
        for graph_name in missing:
            _refresh_one(graph_name)
        missing_retry = []
        for graph_name in missing:
            snap = _read_snapshot(graph_name)
            if snap:
                snapshots.append(snap)
            else:
                missing_retry.append(graph_name)
        missing = missing_retry

    if not snapshots:
        refresh_errors = {k: v for k, v in refresh_results.items() if not v.get('success')}
        return jsonify({
            'success': False, 'snapshot': None,
            'error_message': f'no cached data found for: {", ".join(missing)}',
            'error_code': 'no_cached_data',
            'refresh_attempted': not not refresh_results,
            'refresh_errors': refresh_errors,
        }), 404

    # merge
    all_nodes = []
    all_edges = []
    all_recs = []
    for snap in snapshots:
        all_nodes.extend(snap.get('nodes') or [])
        all_edges.extend(snap.get('edges') or [])
        all_recs.extend(snap.get('recommendations') or [])

    merged = {
        'schemaVersion': 1,
        'generatedAt': max(
            (s.get('generatedAt', '') for s in snapshots if s.get('generatedAt')),
            key=lambda t: t or '', default='',
        ) or None,
        'layout': {
            'mode': 'spiral',
            'radius': 5200,
            'graphId': '+'.join(graph_names),
        },
        'nodes': all_nodes,
        'edges': all_edges,
        'recommendations': sorted(
            all_recs, key=lambda r: r.get('score', 0), reverse=True
        )[:36],
        '_meta': {
            'graph_ids': graph_names,
            'missing': missing,
            'node_count': len(all_nodes),
            'edge_count': len(all_edges),
            'cached': True,
            'syllabusListPerGraph': {
                graph_name: _build_syllabus_list(graph_name)
                for graph_name in graph_names
                if graph_name not in missing
            },
        },
    }
    return jsonify({
        'success': True,
        'snapshot': merged,
        'error_code': '',
        'error_message': '',
    })
