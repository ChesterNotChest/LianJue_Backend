import heapq
from .graph_adapter import InMemoryGraphAdapter, GraphAdapter
from .evaluator import score as eval_score, normalize_scores as eval_normalize, scalar_scores as eval_scalar


def h_estimate(node, goals, learning_tree, knowledge):
    # heuristic: number of goal outcomes not covered by this node's subtree
    node_outcomes = set(learning_tree.get(node, {}).get('outcomes', []))
    remained = sum(1 for g in goals if g not in node_outcomes and knowledge.get(g, 0) == 0)
    return remained


def generate(start_nodes, goals, learning_tree, S, L_max=6, T_max=100, K=20,
             beam_width=6, expand_mode='forward', heuristic_weight=1.0, graph_adapter: GraphAdapter = None):
    """
    混合 Beam + 启发式搜索的候选生成。
    参数说明:
      - beam_width: 每层保留的路径数量（控制分支）
      - expand_mode: 'forward'（默认）或 'backward'，控制展开方向
      - heuristic_weight: 启发式权重，f = g + heuristic_weight * h
    返回: list of {'path':..., 'cost':..., 'skills': set(...) }
    """
    # normalize adapter: if none provided, use in-memory adapter backed by learning_tree
    adapter = graph_adapter if graph_adapter is not None else InMemoryGraphAdapter(learning_tree)

    def expand_fn(node):
        return adapter.get_neighbors(node, direction='forward') if expand_mode == 'forward' else adapter.get_prerequisites(node)

    def cost_fn(node):
        return adapter.get_cost(node)

    def outcomes_fn(node):
        return adapter.get_outcomes(node)

    # 初始化 beam 为起始路径集合
    beam = []
    for s in start_nodes:
        g = cost_fn(s)
        f = g + heuristic_weight * h_estimate(s, goals, learning_tree, S['knowledge'])
        beam.append((f, g, [s]))

    results = []
    depth = 0
    seen = set()
    while beam and len(results) < K and depth < L_max:
        # 保留 top beam_width
        beam.sort(key=lambda x: x[0])
        beam = beam[:beam_width]
        new_beam = []
        for f, g, path in beam:
            last = path[-1]
            # compute covered skills
            covered = set()
            for n in path:
                covered.update(outcomes_fn(n) or [])
            if any(goal in covered for goal in goals):
                results.append({'path': path, 'cost': g, 'skills': covered})
                if len(results) >= K:
                    break
                continue
            if len(path) >= L_max or g >= T_max:
                continue
            for nbr in expand_fn(last):
                # early hard pruning: skip blocked nodes and cost exceed
                blocked = S.get('constraints', {}).get('blocked_nodes')
                if blocked and nbr in blocked:
                    continue
                if nbr in path:
                    continue
                g2 = g + cost_fn(nbr)
                if g2 > T_max or g2 > S.get('constraints', {}).get('max_total_time', T_max):
                    continue
                f2 = g2 + heuristic_weight * h_estimate(nbr, goals, learning_tree, S['knowledge'])
                key = tuple(path + [nbr])
                if key in seen:
                    continue
                seen.add(key)
                new_beam.append((f2, g2, path + [nbr]))
        # Early soft pruning using actual evaluator scores on partial paths:
        # Build candidate items and call evaluator.score -> normalize -> scalar, then keep top-N by scalar.
        items = []
        for f3, g3, p3 in new_beam:
            skills = set()
            for n in p3:
                skills.update(outcomes_fn(n) or [])
            items.append({'path': p3, 'cost': g3, 'skills': skills})
        if items:
            raw_scores = [eval_score(it, S, learning_tree) for it in items]
            norm = eval_normalize(raw_scores)
            weights = S.get('weights_override') if S.get('weights_override') else None
            scalars = eval_scalar(norm, weights=weights)
            scored = list(zip(scalars, new_beam, items))
            # keep top by scalar score, limit to a multiple of beam_width to keep diversity
            scored.sort(key=lambda x: x[0], reverse=True)
            cap = max(beam_width * 4, 20)
            pruned = [t[1] for t in scored[:cap]]
            beam = pruned
        else:
            beam = []
        depth += 1

    # 若候选不足，可将部分未达goal的路径按评分也加入结果以保证多样性
    if len(results) < K:
        # 从最后一层 beam 中选取最优若干
        beam.sort(key=lambda x: x[0])
        for f, g, path in beam[:max(0, K - len(results))]:
            covered = set()
            for n in path:
                covered.update(outcomes_fn(n) or [])
            results.append({'path': path, 'cost': g, 'skills': covered})

    return results
