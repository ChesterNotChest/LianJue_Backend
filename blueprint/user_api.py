from flask import Blueprint, request, jsonify

from extensions import db
from schemas.user import User
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


@bp.route('/demo_students', methods=['GET'])
def demo_students_api():
    """返回最新的演示学生列表（按创建时间倒序）。"""
    users = (
        User.query
        .filter(User.user_name.like('demo_%'))
        .order_by(User.create_time.desc())
        .limit(12)
        .all()
    )
    return jsonify({
        'success': True,
        'students': [
            {
                'user_id': u.user_id,
                'user_name': u.user_name,
                'email': u.email,
                'created_at': u.create_time.isoformat() if u.create_time else None,
            }
            for u in users
        ],
        'error_code': '',
        'error_message': '',
    })
