"""
Move Classifier — converts a centipawn loss into a human-readable label.

Classification thresholds (from the moving player's perspective):

    best        cp_loss == 0  AND  move matches the engine's top choice
    excellent   cp_loss <= 10
    inaccuracy  10 < cp_loss <= 100
    mistake     100 < cp_loss <= 300
    blunder     cp_loss > 300
    forced      only one legal move existed in the position (no classification)

These thresholds mirror those used by Lichess and are intentionally simple
for the MVP. They can be tuned or extended (e.g., "good", "brilliant") later.
"""

from models.schemas import MoveClassification


# Thresholds defined once so they're easy to tune without hunting through logic.
_THRESHOLDS: list[tuple[int, MoveClassification]] = [
    (10,  "excellent"),
    (100, "inaccuracy"),
    (300, "mistake"),
]


def classify_move(
    cp_loss: int,
    is_best_move: bool,
    is_forced: bool,
) -> MoveClassification:
    """
    Return the classification label for a single move.

    Args:
        cp_loss:      Centipawn loss from the moving player's perspective (>= 0).
        is_best_move: True if the played move matches the engine's first choice.
        is_forced:    True if there was only one legal move in the position.
    """
    if is_forced:
        return "forced"

    if is_best_move and cp_loss == 0:
        return "best"

    for threshold, label in _THRESHOLDS:
        if cp_loss <= threshold:
            return label

    return "blunder"


def compute_acpl(cp_losses: list[int]) -> float:
    """
    Compute the Average Centipawn Loss for one player's moves.

    Returns 0.0 if the list is empty (e.g., a game with only one color's moves).
    """
    if not cp_losses:
        return 0.0
    return sum(cp_losses) / len(cp_losses)
