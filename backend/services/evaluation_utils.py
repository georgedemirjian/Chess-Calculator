"""
Evaluation utilities — converts raw Stockfish centipawn scores to win probabilities.

Why raw centipawn differences are insufficient for move classification
----------------------------------------------------------------------
Centipawn loss (CPL) treats every eval swing identically regardless of context.
A 300 cp drop from +1200 → +900 and a 300 cp drop from +200 → -100 both
register as "lost 300 centipawns," yet their practical impact is completely
different. In the first case the position is still completely winning; in the
second the game just changed hands.

Why win probability (WP) is more human-like
-------------------------------------------
Win probability maps the evaluation to a [0, 1] score that reflects the actual
likelihood of winning from a given position. Platforms like Lichess and Chess.com
both classify moves via WP delta rather than raw CPL, which is why their
analysis feels more forgiving in already-decisive positions.

Why sigmoid mapping is the right tool
--------------------------------------
A sigmoid (logistic) function naturally:
  - Returns 50% at eval = 0 (equal position)
  - Saturates smoothly toward 0% / 100% as the eval becomes extreme
  - Gives diminishing weight to further eval gains in already-winning positions
    (e.g. going from +10 to +12 barely changes win probability)

The formula used is:
    WP(eval) = 1 / (1 + exp(-k × eval_cp))

where k = 0.00368 is Lichess's empirically derived logistic scale constant.
At k = 0.00368, a one-pawn advantage (+100 cp) corresponds to ≈ 59% win rate,
matching large-database analysis of over-the-board games.
"""

import math

# Lichess's logistic scale factor, derived from millions of games.
# A 1-pawn advantage (+100 cp) ≈ 59% win probability with this constant.
_LOGISTIC_SCALE: float = 0.00368

# Sentinel mate score — must match the value used in stockfish_service.py.
_MATE_CP: int = 10_000


def eval_to_win_prob(eval_cp: int) -> float:
    """
    Convert a centipawn evaluation (White's perspective) to White's win probability.

    Returns a float in [0.0, 1.0].

    Examples (using k = 0.00368):
        eval =     0  →  WP = 50.0%  (dead equal)
        eval =  +100  →  WP ≈ 59.1%  (+1 pawn)
        eval =  +500  →  WP ≈ 85.1%  (clearly winning)
        eval =  +900  →  WP ≈ 96.5%  (effectively won)
        eval = +1200  →  WP ≈ 98.8%  (dominant)
        eval = ±10000 →  WP ≈ 100/0%  (forced mate)
    """
    # Clamp to ±_MATE_CP to avoid math.exp overflow at extreme values.
    clamped = max(-_MATE_CP, min(_MATE_CP, eval_cp))
    return 1.0 / (1.0 + math.exp(-_LOGISTIC_SCALE * clamped))


def wp_for_side(eval_cp: int, color: str) -> float:
    """
    Return win probability from the perspective of the moving side.

    White's WP = sigmoid(eval_cp).
    Black's WP = 1 - White's WP  (Black benefits when eval is negative).

    This normalisation ensures that a "good" move always increases the moving
    player's WP regardless of which color they play.
    """
    white_wp = eval_to_win_prob(eval_cp)
    return white_wp if color == "white" else 1.0 - white_wp
