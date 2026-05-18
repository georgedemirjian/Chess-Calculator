"""
Move Classifier — classifies moves using win probability loss.

Why win probability instead of raw centipawn loss?
--------------------------------------------------
Raw CPL treats all eval differences equally, regardless of position context.
A +1200 → +900 swing is 300 cp — identical to +200 → -100 — but these carry
completely different practical weight. In the first case the position is still
completely winning; in the second the game just changed hands.

Win probability (WP) is a sigmoid of the eval that naturally saturates in
decisive positions. Near ±12 pawns, further eval swings barely move WP, so
the classifier correctly labels them as minor errors rather than blunders.
This matches the behaviour of Lichess and Chess.com, which also classify moves
via WP delta rather than raw CPL.

Classification thresholds (WP loss as a fraction of 1.0):
    best        wp_loss ≈ 0  AND  move matches engine's top choice
    excellent   wp_loss < 2%   (0.02)
    good        wp_loss < 5%   (0.05)
    inaccuracy  wp_loss < 10%  (0.10)
    mistake     wp_loss < 20%  (0.20)
    blunder     wp_loss ≥ 20%  (0.20+)
    forced      only one legal move existed

Example outcomes with these thresholds:
    +1200 → +900  (−300 cp, White to move): WP 98.8% → 96.5%, loss ≈ 2.3% → good
    +50   → −200  (−250 cp, White to move): WP 54.6% → 32.4%, loss ≈ 22%  → blunder
    +100  → +50   (−50 cp,  White to move): WP 59.1% → 54.6%, loss ≈ 4.5% → good

ACPL computation has moved to centipawn_utils.py to separate the concerns of
move severity (WP-based, here) from ACPL contribution (capped CPL, there).
"""

from models.schemas import MoveClassification


# (upper_bound_exclusive, label) — evaluated in order; first match wins.
# Thresholds are fractions in [0.0, 1.0], not percentages.
_WP_THRESHOLDS: list[tuple[float, MoveClassification]] = [
    (0.02, "excellent"),
    (0.05, "good"),
    (0.10, "inaccuracy"),
    (0.20, "mistake"),
]


def classify_move(
    wp_loss: float,
    is_best_move: bool,
    is_forced: bool,
) -> MoveClassification:
    """
    Classify a move from its win probability loss.

    Args:
        wp_loss:      Fraction of win probability lost by the moving player (0.0–1.0).
        is_best_move: True if the played move matches the engine's top choice.
        is_forced:    True if there was only one legal move in the position.
    """
    if is_forced:
        return "forced"

    # "best" requires playing the engine's exact move with negligible WP cost.
    # The 2% ceiling handles rare cases of evaluation variance between Stockfish
    # calls at different tree depths.
    if is_best_move and wp_loss < 0.02:
        return "best"

    for threshold, label in _WP_THRESHOLDS:
        if wp_loss < threshold:
            return label

    return "blunder"
