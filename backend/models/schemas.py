from pydantic import BaseModel, field_validator
from typing import List, Literal, Optional


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    pgn: str

    @field_validator("pgn")
    @classmethod
    def pgn_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("PGN string cannot be empty.")
        return v


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

# Classification labels ordered from best to worst.
MoveClassification = Literal["best", "excellent", "good", "inaccuracy", "mistake", "blunder", "forced"]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class GameInfo(BaseModel):
    """Metadata extracted from the PGN header block."""
    event:   str
    site:    str
    date:    str
    result:  str                  # "1-0", "0-1", "1/2-1/2", or "*" (ongoing / unknown)
    eco:     Optional[str] = None  # ECO opening code, e.g. "B85"
    opening: Optional[str] = None  # Opening name, e.g. "Sicilian Defense"


class MoveAnalysis(BaseModel):
    # --- Identity ---
    move_number: int                    # Full-move number (1-based; same value for both colors)
    color:       Literal["white", "black"]
    san:         str                    # Standard Algebraic Notation: "Nf3", "O-O", "e8=Q+"
    uci:         str                    # UCI format: "g1f3", "e1g1", "e7e8q"

    # FEN of the position BEFORE this move — used by StockfishService for evaluation.
    fen_before: str
    # FEN of the position AFTER this move — used by the frontend to display the board.
    fen_after:  str

    # --- Move-type flags (derived from python-chess, no Stockfish needed) ---
    piece_moved:   str                  # "P", "N", "B", "R", "Q", or "K"
    is_capture:    bool                 # True for regular captures and en passant
    is_en_passant: bool
    is_castling:   bool
    is_check:      bool                 # True if this move delivers check (not checkmate)
    is_checkmate:  bool
    promotion:     Optional[str] = None  # "Q", "R", "B", or "N" when a pawn promotes

    # --- Stockfish evaluation (populated in the next implementation step) ---
    # Centipawn values are from White's perspective:
    #   positive → White is better, negative → Black is better.
    eval_before:    Optional[int] = None
    eval_after:     Optional[int] = None

    # Centipawn loss from the moving player's perspective (always >= 0).
    cp_loss:        Optional[int] = None

    classification: Optional[MoveClassification] = None


class AnalyzeResponse(BaseModel):
    player_white: str
    player_black: str
    game_info:    GameInfo
    moves:        List[MoveAnalysis]
    acpl_white:   float    # Average centipawn loss for White across all their moves
    acpl_black:   float    # Average centipawn loss for Black across all their moves
    total_moves:  int      # Total half-moves (plies) in the game
