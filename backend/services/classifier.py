"""
Move Classifier — converts a centipawn loss into a human-readable label.

Classification thresholds (from the moving player's perspective):

    best        cp_loss == 0  AND  move matches the engine's top choice
    excellent   cp_loss < 20
    good        cp_loss < 50
    inaccuracy  cp_loss < 90
    mistake     cp_loss < 200
    blunder     cp_loss >= 200
    forced      only one legal move existed in the position

Thresholds are defined in _THRESHOLDS and can be tuned without touching the logic.
"""

from models.schemas import MoveClassification


# (upper_bound_exclusive, label) — evaluated in order; first match wins.
_THRESHOLDS: list[tuple[int, MoveClassification]] = [
    (20,  "excellent"),
    (50,  "good"),
    (90,  "inaccuracy"),
    (200, "mistake"),
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
        if cp_loss < threshold:
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
