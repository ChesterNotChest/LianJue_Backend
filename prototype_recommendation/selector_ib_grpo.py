import random
try:
    from prototype_recommendation.evaluator import normalize_scores, scalar_scores, DEFAULT_WEIGHTS
except Exception:
    from evaluator import normalize_scores, scalar_scores, DEFAULT_WEIGHTS


def dominates(a, b):
    # a,b are dicts with same keys; a dominates b if >= on all and > on some
    ge = all(a[k] >= b[k] for k in a)
    gt = any(a[k] > b[k] for k in a)
    return ge and gt


def pareto_frontier_items(items, norm_scores):
    """Return non-dominated items (using normalized scores where higher is better)."""
    front = []
    for i, item in enumerate(items):
        si = norm_scores[i]
        dominated = False
        for j, sj in enumerate(norm_scores):
            if j == i:
                continue
            if dominates(sj, si):
                dominated = True
                break
        if not dominated:
            front.append(item)
    # remove duplicates preserving order
    seen = set()
    unique = []
    for it in front:
        t = tuple(it['path'])
        if t in seen:
            continue
        seen.add(t)
        unique.append(it)
    return unique


def jaccard(a, b):
    if not a or not b:
        return 0.0
    ia = set(a)
    ib = set(b)
    inter = len(ia & ib)
    uni = len(ia | ib)
    return inter / uni if uni > 0 else 0.0


def ib_grpo_select(candidates, raw_scores, IB_constraints=None, iterations=100, N=5,
                   diversity_beta=0.3, relax_steps=3,
                   weights_override=None,
                   pre_select_hook=None,
                   post_select_hook=None,
                   user_confirm=None):
    """
    IB-GRPO selector with:
      - dynamic IB relaxation (if no candidate meets constraints, relax thresholds)
      - randomized greedy sampling to explore
      - Pareto-front filter on normalized scores
      - diversity-aware pruning (Jaccard on skills)
    """
    if not candidates:
        return []

    # allow pre-selection hook to modify candidates/raw_scores
    if callable(pre_select_hook):
        try:
            out = pre_select_hook(list(candidates), list(raw_scores))
            if isinstance(out, tuple) and len(out) == 2:
                candidates, raw_scores = out
        except Exception:
            pass

    norm = normalize_scores(raw_scores)

    # helper to filter pool by IB, with optional threshold multipliers
    def filter_by_ib(thresholds, multiplier=1.0):
        pool = []
        pool_idx = []
        for i, itm in enumerate(candidates):
            ok = True
            if thresholds:
                for k, v in thresholds.items():
                    if norm[i].get(k, 0) < v * multiplier:
                        ok = False
                        break
            if ok:
                pool.append(itm)
                pool_idx.append(i)
        return pool, pool_idx

    # attempt to get initial pool, with relaxation if empty
    pool, pool_idx = filter_by_ib(IB_constraints, 1.0)
    relax_factor = 0.8
    relax_attempt = 0
    while not pool and IB_constraints and relax_attempt < relax_steps:
        relax_attempt += 1
        mult = relax_factor ** relax_attempt
        pool, pool_idx = filter_by_ib(IB_constraints, mult)

    # if still empty, fall back to all candidates
    if not pool:
        pool = candidates[:]
        pool_idx = list(range(len(candidates)))

    # run randomized greedy iterations
    selected = []
    for it in range(iterations):
        if not pool:
            break
        sample_size = min(max(3, len(pool) // 2), len(pool))
        sample_indices = random.sample(list(range(len(pool))), sample_size)
        best = None
        best_score = -1.0
        for idx in sample_indices:
            i_global = pool_idx[idx]
            s = norm[i_global]
            # weighted scalar using DEFAULT_WEIGHTS optionally overridden
            weights = DEFAULT_WEIGHTS if weights_override is None else {**DEFAULT_WEIGHTS, **(weights_override or {})}
            ws = sum(s.get(k, 0.0) * w for k, w in weights.items())
            ws = ws + random.random() * 0.05
            if ws > best_score:
                best_score = ws
                best = pool[idx]
        if best and best not in selected:
            selected.append(best)

    if not selected:
        return []

    # compute normalized scores for selected for Pareto filtering
    sel_indices = [candidates.index(x) for x in selected]
    sel_norm = [norm[i] for i in sel_indices]
    front_items = pareto_frontier_items(selected, sel_norm)

    # diversity-aware pruning: greedily select top-N by scalar score but encourage diversity
    front_scores = []
    for it in front_items:
        idx = candidates.index(it)
        front_scores.append(sum(norm[idx].get(k, 0.0) * w for k, w in DEFAULT_WEIGHTS.items()))
    # pair items
    paired = list(zip(front_items, front_scores))
    paired.sort(key=lambda x: x[1], reverse=True)

    final = []
    while paired and len(final) < N:
        if not final:
            final.append(paired.pop(0)[0])
            continue
        # score each remaining by (weight * scalar + diversity_beta * diversity)
        scores = []
        for it, sc in paired:
            diversity = max(1 - jaccard(it['skills'], f['skills']) for f in final)
            combined = (1 - diversity_beta) * sc + diversity_beta * diversity
            scores.append((combined, it, sc))
        scores.sort(key=lambda x: x[0], reverse=True)
        chosen = scores[0]
        # remove chosen from paired
        for i, (it2, sc2) in enumerate(paired):
            if it2 is chosen[1]:
                paired.pop(i)
                break
        final.append(chosen[1])

    # allow post-selection hook to adjust final set
    if callable(post_select_hook):
        try:
            out = post_select_hook(list(final))
            if isinstance(out, list):
                final = out
        except Exception:
            pass

    # optional user confirmation hook (returns True to accept)
    if callable(user_confirm):
        try:
            ok = user_confirm(final)
            if not ok:
                return []
        except Exception:
            pass

    return final
