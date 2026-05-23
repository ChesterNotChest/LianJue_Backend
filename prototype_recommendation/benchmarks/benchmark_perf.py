import time
import random
import json
import argparse
import tracemalloc
import statistics
import os
import sys

# ensure prototype_recommendation parent is importable when running from repo root
THIS_DIR = os.path.dirname(__file__)
PROJ_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if PROJ_ROOT not in sys.path:
    sys.path.insert(0, PROJ_ROOT)

try:
    # prefer local direct imports when running from repo root
    from candidate_generator import generate
    import candidate_generator as cg
    from perception import generate_state
    from evaluator import score, normalize_scores, scalar_scores
    from selector_ib_grpo import ib_grpo_select
    from sample_data import user_profile, goals
except Exception:
    # fallback to package-style imports
    from prototype_recommendation.candidate_generator import generate
    from prototype_recommendation import candidate_generator as cg
    from prototype_recommendation.perception import generate_state
    from prototype_recommendation.evaluator import score, normalize_scores, scalar_scores
    from prototype_recommendation.selector_ib_grpo import ib_grpo_select
    from prototype_recommendation.sample_data import user_profile, goals


def make_synthetic_tree(n_nodes=200, max_prereq=3, seed=42):
    random.seed(seed)
    tree = {}
    for i in range(1, n_nodes + 1):
        nid = f'n{i}'
        difficulty = random.randint(1, 4)
        learning_time_est = random.randint(1, 10)
        # prerequisites from earlier nodes to keep DAG
        if i == 1:
            prereqs = []
        else:
            k = random.randint(0, min(max_prereq, i - 1))
            prereqs = [f'n{random.randint(1, i-1)}' for _ in range(k)]
            # deduplicate
            prereqs = list(dict.fromkeys(prereqs))
        outcomes = [f'skill_{i}']
        tree[nid] = {
            'id': nid,
            'title': f'Node {i}',
            'difficulty': difficulty,
            'prerequisites': prereqs,
            'learning_time_est': learning_time_est,
            'outcomes': outcomes,
        }
    return tree


def bench(tree, user_profile, goals, configs, runs=5, out_dir='prototype_recommendation/benchmarks/results'):
    os.makedirs(out_dir, exist_ok=True)
    all_results = []
    for cfg in configs:
        cfg_name = f"beam{cfg['beam_width']}_K{cfg['K']}_L{cfg['L_max']}"
        stats = {'cfg': cfg, 'runs': []}
        for r in range(runs):
            tracemalloc.start()
            t0 = time.perf_counter()
            S, starts = generate_state(user_profile, tree)
            t1 = time.perf_counter()
            # simulate DB reads (optional: only if helper functions exist)
            try:
                if hasattr(cg, 'reset_db_stats'):
                    cg.reset_db_stats()
                if hasattr(cg, 'set_db_simulation'):
                    cg.set_db_simulation(enabled=cfg.get('db_sim', False), delay=cfg.get('db_delay', 0.0))
            except Exception:
                pass
            gen_start = time.perf_counter()
            candidates = generate(starts, goals, tree, S, L_max=cfg['L_max'], T_max=cfg.get('T_max', 1000), K=cfg['K'], beam_width=cfg['beam_width'])
            gen_end = time.perf_counter()
            score_start = time.perf_counter()
            raw = [score(c, S, tree) for c in candidates]
            score_end = time.perf_counter()
            select_start = time.perf_counter()
            selected = ib_grpo_select(candidates, raw, IB_constraints=cfg.get('IB', None), iterations=cfg.get('iterations', 50), N=cfg.get('N', 5))
            select_end = time.perf_counter()
            t_end = time.perf_counter()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            node_reads = 0
            try:
                if hasattr(cg, 'get_db_stats'):
                    node_reads = (cg.get_db_stats() or {}).get('node_reads', 0)
            except Exception:
                node_reads = 0

            run_info = {
                'perception_time': t1 - t0,
                'gen_time': gen_end - gen_start,
                'score_time': score_end - score_start,
                'select_time': select_end - select_start,
                'total_time': t_end - t0,
                'candidates': len(candidates),
                'selected': len(selected),
                'mem_peak_bytes': peak,
                'node_reads': node_reads,
            }
            stats['runs'].append(run_info)
            print(f"cfg={cfg_name} run={r} gen={run_info['gen_time']:.3f}s score={run_info['score_time']:.3f}s select={run_info['select_time']:.3f}s total={run_info['total_time']:.3f}s candidates={run_info['candidates']} selected={run_info['selected']} mem_peak={run_info['mem_peak_bytes']}")
        # summarize
        summary = {}
        for key in ['gen_time', 'score_time', 'select_time', 'total_time', 'candidates', 'selected', 'mem_peak_bytes']:
            vals = [x[key] for x in stats['runs']]
            summary[key] = {'mean': statistics.mean(vals), 'stdev': statistics.pstdev(vals)}
        stats['summary'] = summary
        all_results.append(stats)
        # write per-config json
        with open(os.path.join(out_dir, f'{cfg_name}.json'), 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    # write overall
    with open(os.path.join(out_dir, 'all_results.json'), 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    return all_results


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--nodes', type=int, default=200)
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--out', type=str, default='prototype_recommendation/benchmarks/results')
    return p.parse_args()


if __name__ == '__main__':
    args = parse_args()
    tree = make_synthetic_tree(n_nodes=args.nodes)
    # auto-select goals that exist in the synthetic tree
    all_outcomes = [o for v in tree.values() for o in v.get('outcomes', [])]
    if all_outcomes:
        # choose up to 3 random goals from the existing outcomes
        goals = random.sample(all_outcomes, min(3, len(all_outcomes)))
    else:
        goals = ['skill_1']
    configs = [
        {'beam_width': 6, 'K': 50, 'L_max': 6, 'iterations': 50, 'N': 5},
        {'beam_width': 12, 'K': 100, 'L_max': 8, 'iterations': 80, 'N': 5},
    ]
    results = bench(tree, user_profile, goals, configs, runs=args.runs, out_dir=args.out)
    print('Benchmark finished. Results saved to', args.out)
