"""Personal recommendation agent implementation (migrated from prototype_recommendation).
Expose the core functions used by the blueprint.
"""
from .perception import generate_state
from .candidate_generator import generate
from .pruning import hard_prune, soft_prune_by_dominance
from .evaluator import score, normalize_scores, scalar_scores
from .selector_ib_grpo import ib_grpo_select

__all__ = [
    'generate_state', 'generate', 'hard_prune', 'soft_prune_by_dominance',
    'score', 'normalize_scores', 'scalar_scores', 'ib_grpo_select'
]
