def hard_prune(candidates, S, blocked_nodes=None):
    """硬剪枝：剔除超过用户约束（时间、deadline）或包含被屏蔽节点的候选。"""
    max_time = S.get('constraints', {}).get('max_total_time', None)
    out = []
    for c in candidates:
        if max_time is not None and c.get('cost', 0) > max_time:
            continue
        if blocked_nodes:
            bad = False
            for n in c.get('path', []):
                if n in blocked_nodes:
                    bad = True
                    break
            if bad:
                continue
        out.append(c)
    return out


def dominates(a, b):
    # a,b are dicts of metrics where higher is better
    ge = all(a[k] >= b[k] for k in a)
    gt = any(a[k] > b[k] for k in a)
    return ge and gt


def soft_prune_by_dominance(candidates, raw_scores):
    """软剪枝：移除被其他候选严格支配的解（Pareto dominated）。"""
    keep = []
    for i, ci in enumerate(candidates):
        si = raw_scores[i]
        dominated = False
        for j, sj in enumerate(raw_scores):
            if j == i:
                continue
            if dominates(sj, si):
                dominated = True
                break
        if not dominated:
            keep.append(ci)
    # 如果全部被保留，则返回原始集合
    return keep if keep else candidates


def local_replace_candidates(candidates, learning_tree, S, max_attempts=100):
    """尝试对候选集合做单节点替换以改进效率指标（E）。

    策略：随机挑选候选与路径位置，尝试用同一前驱的其他子节点替换当前节点，
    若新路径的简单收益（new_skills / new_cost）更优则加入集合。
    这是轻量启发式替换，不保证全局最优，但可补充多样性与可行解。
    """
    import random

    def simple_score(path_item):
        cost = path_item.get('cost', 1)
        skills = path_item.get('skills', set())
        new_skills = [s for s in skills if S.get('knowledge', {}).get(s, 0) == 0]
        return len(new_skills) / (cost + 1e-6)

    out = list(candidates)
    attempts = 0
    while attempts < max_attempts:
        if not out:
            break
        c = random.choice(out)
        path = list(c.get('path', []))
        if len(path) < 2:
            attempts += 1
            continue
        # choose a replaceable position not the first node
        idx = random.randrange(1, len(path))
        pred = path[idx-1]
        # candidate siblings: nodes that have pred as prerequisite
        siblings = [nid for nid, n in learning_tree.items() if pred in n.get('prerequisites', []) and nid != path[idx]]
        if not siblings:
            attempts += 1
            continue
        new_node = random.choice(siblings)
        new_path = path[:idx] + [new_node] + path[idx+1:]
        # compute simple cost and skills
        new_cost = sum(learning_tree[n].get('learning_time_est', 1) for n in new_path)
        new_skills = set()
        for n in new_path:
            new_skills.update(learning_tree[n].get('outcomes', []))
        new_item = {'path': new_path, 'cost': new_cost, 'skills': new_skills}
        if simple_score(new_item) > simple_score(c):
            out.append(new_item)
        attempts += 1
    return out
