from tasks.personal_recommendation.candidate_generator import generate
from tasks.personal_recommendation.graph_adapter import InMemoryGraphAdapter


def make_tree():
    return {
        'n1': {'prerequisites': [], 'outcomes': ['a'], 'learning_time_est': 1},
        'n2': {'prerequisites': ['n1'], 'outcomes': ['b'], 'learning_time_est': 1},
        'n3': {'prerequisites': ['n2'], 'outcomes': ['c'], 'learning_time_est': 1},
    }


def test_generate_with_inmemory_adapter():
    tree = make_tree()
    adapter = InMemoryGraphAdapter(tree)
    S = {'knowledge': {}, 'constraints': {'max_total_time': 10}}
    starts = ['n1']
    goals = ['c']
    candidates = generate(starts, goals, tree, S, L_max=4, T_max=10, K=5, graph_adapter=adapter)
    assert isinstance(candidates, list)
    # should find a path to n3
    paths = [p['path'] for p in candidates]
    assert any(['n1', 'n2', 'n3'] == p for p in paths) or any('n3' in p for p in paths)
    stats = adapter.get_stats()
    assert stats.get('node_reads', 0) > 0
