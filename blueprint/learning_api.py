from flask import Blueprint, jsonify, request

from tasks import learning_task
from tasks.learning_profile_task import get_or_build_learning_profile
from repositories.syllabus_repo import get_syllabus_by_id
from tasks.learning_profile.storage import load_json_file
from tasks.syllabus_to_learning_tree import syllabus_json_to_learning_tree

try:
    from tasks.personal_recommendation.sample_data import learning_tree as _sample_learning_tree
    from tasks.personal_recommendation.perception import generate_state as _pr_generate_state
    from tasks.personal_recommendation.candidate_generator import generate as _pr_generate
    from tasks.personal_recommendation.pruning import hard_prune, soft_prune_by_dominance
    from tasks.personal_recommendation.evaluator import score as _pr_score
    from tasks.personal_recommendation.selector_ib_grpo import ib_grpo_select
except Exception:
    _sample_learning_tree = None
    _pr_generate_state = None
    _pr_generate = None
    hard_prune = None
    soft_prune_by_dominance = None
    _pr_score = None
    ib_grpo_select = None


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
    if _sample_learning_tree is None or _pr_generate_state is None:
        return jsonify({'success': False, 'candidates': [], 'selected': [], 'error_message': 'recommendation engine not available in this deployment', 'error_code': 'not_available'}), 501

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    syllabus_id = data.get('syllabus_id')
    if not user_id:
        return jsonify({'success': False, 'candidates': [], 'selected': [], 'error_message': 'missing user_id', 'error_code': 'missing_fields'}), 400

    # build or fetch learning profile
    profile = get_or_build_learning_profile(int(user_id), int(syllabus_id) if syllabus_id else None, refresh_profile=False)
    if profile is None:
        # fallback to a minimal ephemeral profile instead of failing
        profile = {
            'user_id': int(user_id),
            'syllabus_id': int(syllabus_id) if syllabus_id else None,
            'knowledge_levels': {},
            'learning_goals': []
        }

    # use provided goals or fallback to profile/goals in sample data
    goals = data.get('goals') or profile.get('learning_goals') or []

    # prepare learning_tree: prefer syllabus-derived tree when syllabus_id provided
    chosen_tree = _sample_learning_tree
    if syllabus_id:
        try:
            syllabus = get_syllabus_by_id(int(syllabus_id))
            if syllabus and getattr(syllabus, 'syllabus_path', None):
                sj = load_json_file(getattr(syllabus, 'syllabus_path', None))
                mapped = syllabus_json_to_learning_tree(sj)
                if mapped:
                    chosen_tree = mapped
        except Exception:
            # fallback to sample tree on any error
            chosen_tree = _sample_learning_tree

    # prepare state and starts
    S, starts = _pr_generate_state(profile, chosen_tree)

    # generation params
    L_max = int(data.get('L_max') or 6)
    T_max = int(data.get('T_max') or 100)
    K = int(data.get('K') or 20)
    beam_width = int(data.get('beam_width') or 6)

    candidates = _pr_generate(starts, goals, chosen_tree, S, L_max=L_max, T_max=T_max, K=K, beam_width=beam_width)

    # pruning and scoring
    try:
        candidates = hard_prune(candidates, S, blocked_nodes=S.get('constraints', {}).get('blocked_nodes'))
    except Exception:
        pass
    raw_scores = [_pr_score(c, S, chosen_tree) for c in candidates]
    try:
        candidates = soft_prune_by_dominance(candidates, raw_scores)
        raw_scores = [_pr_score(c, S, chosen_tree) for c in candidates]
    except Exception:
        pass

    # attach scores for response
    resp_cands = []
    for c, s in zip(candidates, raw_scores):
        item = dict(c)
        item['scores'] = s
        resp_cands.append(item)

    # selection (use IB-GRPO if available)
    selected = []
    if ib_grpo_select is not None and resp_cands:
        try:
            sel = ib_grpo_select(candidates, raw_scores, IB_constraints={'E': 0.0}, iterations=20, N=1)
            selected = sel
        except Exception:
            selected = []

    return jsonify({'success': True, 'candidates': resp_cands, 'selected': selected, 'error_message': '', 'error_code': ''}), 200
