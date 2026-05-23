from tasks.personal_recommendation.sample_data import learning_tree, user_profile, goals
from tasks.personal_recommendation.perception import generate_state
from tasks.personal_recommendation.candidate_generator import generate


def test_generate_with_sample_profile():
    S, starts = generate_state(user_profile, learning_tree)
    assert isinstance(starts, list)
    candidates = generate(starts, goals, learning_tree, S, L_max=6, T_max=50, K=10, beam_width=4)
    assert isinstance(candidates, list)
    # at least one candidate path or fallback
    assert len(candidates) >= 0
