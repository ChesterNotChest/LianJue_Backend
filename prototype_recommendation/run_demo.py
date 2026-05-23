from sample_data import learning_tree, user_profile, goals
from perception import generate_state
from candidate_generator import generate
from evaluator import score
from selector_ib_grpo import ib_grpo_select
from pruning import hard_prune, soft_prune_by_dominance


def main():
    S, starts = generate_state(user_profile, learning_tree)
    print('start nodes:', starts)
    candidates = generate(starts, goals, learning_tree, S, L_max=6, T_max=50, K=20)
    # 早期替换算子：在进行硬剪枝/评分前尝试本地替换以提升候选多样性与效率
    try:
        from pruning import local_replace_candidates
    except Exception:
        from prototype_recommendation.pruning import local_replace_candidates
    candidates = local_replace_candidates(candidates, learning_tree, S, max_attempts=100)
    print('generated candidates:', len(candidates))
    # 硬剪枝：用户约束（示例没有 blocked_nodes）
    candidates = hard_prune(candidates, S, blocked_nodes=None)
    print('after hard prune:', len(candidates))
    raw_scores = [score(c, S, learning_tree) for c in candidates]
    # 软剪枝：Pareto dominated removal
    candidates = soft_prune_by_dominance(candidates, raw_scores)
    raw_scores = [score(c, S, learning_tree) for c in candidates]
    # for visibility
    for i,c in enumerate(candidates):
        print(i, c['path'], 'cost', c['cost'], 'scores', raw_scores[i])
    # 示例：向 Selector 注入权重覆写与确认回调
    def pre_hook(cands, scores):
        # 可以在此处根据策略移除或 re-rank 候选集合
        return cands, scores

    def user_confirm(selected):
        # 简单示例：总是接受；在生产可替换为 UI / human-in-loop
        return True

    selected = ib_grpo_select(
        candidates,
        raw_scores,
        IB_constraints={'E': 0.0},
        iterations=30,
        N=3,
        weights_override={'E': 0.5, 'D': 0.2, 'R': 0.2, 'P': 0.1},
        pre_select_hook=pre_hook,
        user_confirm=user_confirm,
    )
    print('\nselected paths:')
    for s in selected:
        print(s)

if __name__ == '__main__':
    main()
