"""
Centipawn utilities — contextual capping and ACPL computation.

Why raw centipawn loss (CPL) distorts ACPL
-------------------------------------------
Mate evaluations are stored as ±10,000 cp. A single move that transitions
from a winning position to checkmate contributes up to 20,000 cp to the raw
average — dwarfing every other move in the game. A 40-move game with one
such move can produce an ACPL of 500 even if every other move was perfect.

Why contextual capping improves realism
----------------------------------------
A player holding a +12 advantage who blunders to +9 is still completely
winning. Their raw CPL is 300 — identical to someone who drops a piece in an
equal position. The effective loss should reflect what was actually at stake:

    effective_loss = min(raw_cp_loss, abs(eval_before), MAX_ADVANTAGE_CP)

Two bounds are applied simultaneously:
  1. abs(eval_before): you cannot throw away more than you held. If you were
     down 200 cp and blundered to −600, your effective loss is 200, not 400.
  2. MAX_ADVANTAGE_CP: no single move dominates the average beyond a fixed
     ceiling (500 cp by default). This bounds the distribution and prevents
     large-advantage blunders from inflating ACPL unrealistically.

Why this improves ML feature stability
----------------------------------------
Uncapped ACPL has high variance caused by rare extreme losses. Models trained
on such features will overfit to game-ending blunders rather than general
move quality. Effective ACPL has a bounded range [0, MAX_ADVANTAGE_CP],
producing a more stable and informative feature vector.

Why move classification is kept separate from ACPL contribution
----------------------------------------------------------------
A move that loses 25% win probability is a blunder by any meaningful measure.
But if it occurred in an already-lost position, its cp contribution to ACPL
should be small. Separating classification (WP-based) from ACPL contribution
(capped CPL) prevents one metric from contaminating the other.
"""

MAX_ADVANTAGE_CP: int = 500  # configurable; 5 pawns is the practical ceiling for ACPL contribution


def compute_effective_cp_loss(
    raw_cp_loss: int,
    eval_before: int,
    max_advantage: int = MAX_ADVANTAGE_CP,
) -> int:
    """
    Compute contextually bounded centipawn loss for ACPL contribution.

    A move can still classify as a blunder (via WP loss) without contributing
    its full raw loss to the average. The effective loss is the lesser of:
      - the raw loss
      - the advantage the moving player actually held before the move
      - a configured upper cap (max_advantage)

    Args:
        raw_cp_loss:   Uncapped cp_loss from the moving player's perspective (>= 0).
        eval_before:   Centipawn eval before the move, from White's perspective.
                       abs() is taken so the bound applies symmetrically to both sides.
        max_advantage: Ceiling on any single move's ACPL contribution.
    """
    available = min(abs(eval_before), max_advantage)
    return min(raw_cp_loss, available)


def compute_acpl(cp_losses: list[int]) -> float:
    """
    Average centipawn loss — raw, uncapped.

    Retained for ML feature extraction and advanced analytics. The full
    distribution of losses is informative for Elo estimation models.
    NOT suitable for human-facing accuracy due to mate-score distortion.
    """
    if not cp_losses:
        return 0.0
    return sum(cp_losses) / len(cp_losses)


def compute_effective_acpl(effective_cp_losses: list[int]) -> float:
    """
    Average effective (contextually capped) centipawn loss.

    Uses bounded per-move losses so mate sequences and large-advantage blunders
    do not dominate the average. More meaningful for human-facing display than
    raw ACPL.
    """
    if not effective_cp_losses:
        return 0.0
    return sum(effective_cp_losses) / len(effective_cp_losses)
