DEFAULT_WEIGHTS = {'E': 0.4, 'D': 0.2, 'R': 0.2, 'P': 0.2}


def score(path_item, S, learning_tree):
    # path_item: {'path': [...], 'cost': cost, 'skills': set}
    cost_val = path_item['cost']
    skills = path_item['skills']
    # E: efficiency = new skills / cost
    known = S['knowledge']
    new_skills = [s for s in skills if known.get(s,0) == 0]
    E = len(new_skills) / (cost_val + 1e-6)
    # D: difficulty mismatch = avg node difficulty - avg user level (positive worse)
    diffs = [learning_tree[n].get('difficulty',1) for n in path_item['path']]
    avg_diff = sum(diffs)/len(diffs)
    avg_user_level =  sum(known.get(s, 0) for s in known) / (len(known) if known else 1)
    D = max(0, avg_diff - avg_user_level)
    # R: risk = fraction of prerequisites in path that are not known
    prereq_total = 0
    prereq_unmet = 0
    for n in path_item['path']:
        for p in learning_tree[n].get('prerequisites',[]):
            prereq_total += 1
            # assume prereq satisfied if its outcomes known
            outcomes = learning_tree[p].get('outcomes',[])
            if not all(known.get(o,0)>0 for o in outcomes):
                prereq_unmet += 1
    R = (prereq_unmet / prereq_total) if prereq_total>0 else 0
    # P: preference match (simple 0.5 default)
    P = 0.5
    return {'E': E, 'D': D, 'R': R, 'P': P}


def normalize_scores(score_dicts, keys=None):
    """Normalize metrics across candidate list to [0,1].
    For metrics where lower is better (D,R) we invert the scale so higher is always better.
    """
    if keys is None:
        keys = ['E', 'D', 'R', 'P']
    mins = {k: float('inf') for k in keys}
    maxs = {k: float('-inf') for k in keys}
    for s in score_dicts:
        for k in keys:
            v = s.get(k, 0.0)
            mins[k] = min(mins[k], v)
            maxs[k] = max(maxs[k], v)
    out = []
    for s in score_dicts:
        ns = {}
        for k in keys:
            lo = mins[k]
            hi = maxs[k]
            val = s.get(k, 0.0)
            if hi - lo < 1e-9:
                ns[k] = 0.0
            elif k in ('D', 'R'):
                ns[k] = (hi - val) / (hi - lo)
            else:
                ns[k] = (val - lo) / (hi - lo)
        out.append(ns)
    return out


def scalar_scores(norm_scores, weights=None):
    """Compute scalar weighted score from normalized score dicts."""
    if weights is None:
        weights = DEFAULT_WEIGHTS
    scalars = []
    for s in norm_scores:
        tot = 0.0
        for k, w in weights.items():
            tot += s.get(k, 0.0) * w
        scalars.append(tot)
    return scalars
