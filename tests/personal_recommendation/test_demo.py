from tasks.personal_recommendation.sample_data import learning_tree, user_profile, goals
from tasks.personal_recommendation.perception import generate_state
from tasks.personal_recommendation.candidate_generator import generate


def test_run_demo_smoke():
    # smoke: build state and generate candidates to ensure imports and basic flow work
    S, starts = generate_state(user_profile, learning_tree)
    assert isinstance(starts, list)
    cands = generate(starts, goals, learning_tree, S, L_max=6, T_max=50, K=5, beam_width=4)
    assert isinstance(cands, list)
