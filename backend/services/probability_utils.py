"""
Win probability utilities — computes how much win probability a move costs.

These functions bridge the raw evaluation output from evaluation_utils.py and
the classification logic in classifier.py. The core idea: measure move quality
by how much the moving player's likelihood of winning changed, not by how many
abstract centipawn units were gained or lost.
"""

from services.evaluation_utils import wp_for_side


def compute_wp_loss(eval_before: int, eval_after: int, color: str) -> float:
    """
    Compute the win probability lost by the moving player for a single move.

    Returns a value in [0.0, 1.0], always non-negative:
      - A move that improves the position → 0.0 (no loss; gains are clamped)
      - A decisive blunder → close to 0.5 (threw away a 50/50 game)
      - A game-ending blunder from a winning position → up to ~0.98

    Sign normalisation: both eval_before and eval_after are stored from White's
    perspective. wp_for_side() converts them to the moving player's perspective
    so the arithmetic is sign-consistent regardless of color.
    """
    wp_before = wp_for_side(eval_before, color)
    wp_after  = wp_for_side(eval_after,  color)
    return max(0.0, wp_before - wp_after)


def compute_avg_wp_loss(wp_losses: list[float]) -> float:
    """
    Average win probability loss per move (result in [0.0, 1.0]).

    Used as the primary accuracy signal — naturally bounded and position-context-aware.
    A player whose moves average 5% WP loss is notably worse than one averaging 1%,
    regardless of how those losses are distributed across the centipawn scale.
    """
    if not wp_losses:
        return 0.0
    return sum(wp_losses) / len(wp_losses)


def wp_white(eval_cp: int) -> float:
    """White's absolute win probability — stored in the response for analytics."""
    from services.evaluation_utils import eval_to_win_prob
    return eval_to_win_prob(eval_cp)
