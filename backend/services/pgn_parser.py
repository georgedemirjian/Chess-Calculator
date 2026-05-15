"""
PGN Parser — converts a raw PGN string into structured game and move data.

Responsibilities:
  - Validate that the input is a parseable PGN string.
  - Extract game-level metadata from PGN headers (players, event, result, ECO, …).
  - Walk every ply in the mainline, reconstructing board state move-by-move and
    capturing per-move metadata (piece moved, capture flags, check, FEN, …).
  - Return a plain dict that the router maps onto Pydantic response models.

No Stockfish dependency here — this module only concerns itself with what the
game contains, not how good each move was. Centipawn evaluation is added later
by StockfishService using the fen_before values produced here.
"""

import io
from typing import Any, Dict, List, Optional

import chess
import chess.pgn

# Maps python-chess PieceType constants to the single-letter abbreviations
# used in the API response ("P", "N", "B", "R", "Q", "K").
# chess.PIECE_SYMBOLS is indexed by PieceType int: ['', 'p', 'n', 'b', 'r', 'q', 'k']
_PIECE_LETTER: Dict[int, str] = {
    chess.PAWN:   "P",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK:   "R",
    chess.QUEEN:  "Q",
    chess.KING:   "K",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_headers(game: chess.pgn.Game) -> Dict[str, Any]:
    """
    Pull structured metadata out of the PGN header block.

    PGN headers look like:
        [Event "World Championship"]
        [White "Kasparov, G."]
        [ECO "B85"]

    Headers that are absent or set to the PGN placeholder "?" are returned as
    None for Optional fields so the frontend can distinguish missing data from
    an empty string.
    """
    h = game.headers

    def optional(key: str) -> Optional[str]:
        """Return None for absent or PGN-placeholder values."""
        val = h.get(key)
        return val if val and val != "?" else None

    return {
        "white":   h.get("White",  "Unknown"),
        "black":   h.get("Black",  "Unknown"),
        "event":   h.get("Event",  "Unknown"),
        "site":    h.get("Site",   "Unknown"),
        "date":    h.get("Date",   "Unknown"),
        "result":  h.get("Result", "*"),
        "eco":     optional("ECO"),
        "opening": optional("Opening"),
    }


def _extract_move(
    ply: int,
    move: chess.Move,
    board: chess.Board,
    san: str,
) -> Dict[str, Any]:
    """
    Extract all per-move metadata from the board state BEFORE the move is pushed.

    This function must be called before board.push(move) because:
      - The moving piece only exists on its source square in the pre-move position.
      - board.is_capture() / is_en_passant() / is_castling() query the pre-move board.
      - board.fen() must capture the position the engine will evaluate.

    Check and checkmate flags are read from the SAN string rather than calling
    board.is_check() after the push, since python-chess already annotates SAN
    with '+' (check) and '#' (checkmate) during generation.

    Args:
        ply   — 0-based half-move index. Even plies are White's moves.
        move  — chess.Move object about to be played.
        board — board state before this move (not yet modified).
        san   — SAN string for this move, generated before the push.
    """
    # --- Which piece is moving? ---
    # board.piece_at() returns None on an empty square, which shouldn't happen
    # for a legal move. Guard defensively to avoid an AttributeError crash.
    moving_piece = board.piece_at(move.from_square)
    piece_letter = _PIECE_LETTER.get(moving_piece.piece_type, "?") if moving_piece else "?"

    # --- Move-type flags ---
    # is_capture() covers both regular captures and en passant (both remove a piece).
    is_capture    = board.is_capture(move)
    is_en_passant = board.is_en_passant(move)
    is_castling   = board.is_castling(move)

    # move.promotion is a chess.PieceType int when a pawn reaches the back rank,
    # None otherwise. Convert to the same single-letter format as piece_letter.
    promotion: Optional[str] = _PIECE_LETTER.get(move.promotion) if move.promotion else None

    # --- Check / checkmate from the SAN annotation ---
    # python-chess appends '+' for check and '#' for checkmate when generating SAN.
    # Reading the trailing character avoids re-interrogating the board after push.
    is_checkmate = san.endswith("#")
    is_check     = san.endswith("+")  # True only for check, not checkmate

    return {
        "move_number":   (ply // 2) + 1,   # Full-move number (1-based)
        "color":         "white" if board.turn == chess.WHITE else "black",
        "san":           san,
        "uci":           move.uci(),
        # FEN of the position BEFORE this move — fed to Stockfish in the next step.
        "fen_before":    board.fen(),
        "piece_moved":   piece_letter,
        "is_capture":    is_capture,
        "is_en_passant": is_en_passant,
        "is_castling":   is_castling,
        "is_check":      is_check,
        "is_checkmate":  is_checkmate,
        "promotion":     promotion,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(pgn_string: str) -> Dict[str, Any]:
    """
    Parse a PGN string and return structured game data.

    Validation performed:
        1. The string must be parseable by chess.pgn.read_game().
        2. Every move in the mainline must be a legal chess move.
        3. The game must contain at least one move.

    Raises:
        ValueError — with a human-readable message describing what went wrong.

    Returns a dict with the following top-level keys:
        white, black        — player names from PGN headers
        event, site, date   — game context from PGN headers
        result              — game result string ("1-0", "0-1", "1/2-1/2", "*")
        eco, opening        — optional opening classification (None if absent)
        total_moves         — number of half-moves (plies) in the mainline
        moves               — list of per-move dicts (see _extract_move)
    """
    # ------------------------------------------------------------------
    # Step 1: Read the PGN string
    # ------------------------------------------------------------------
    # io.StringIO wraps the string as a file-like object so chess.pgn.read_game()
    # can consume it exactly as it would a .pgn file opened from disk.
    pgn_io = io.StringIO(pgn_string.strip())

    try:
        game = chess.pgn.read_game(pgn_io)
    except Exception as exc:
        raise ValueError(f"PGN could not be read: {exc}") from exc

    if game is None:
        raise ValueError(
            "Invalid PGN: the text could not be parsed. "
            "Make sure it starts with header tags like [Event \"...\"] "
            "or at least contains a move list (e.g. '1. e4 e5')."
        )

    # ------------------------------------------------------------------
    # Step 2: Reconstruct the board and walk every move in the mainline
    # ------------------------------------------------------------------
    # game.board() returns a fresh chess.Board already configured for the
    # starting position described by the PGN headers (standard setup by default,
    # or a custom FEN if the PGN contains a [SetUp "1"] / [FEN "..."] header pair).
    board = game.board()
    moves: List[Dict[str, Any]] = []

    for ply, move in enumerate(game.mainline_moves()):
        # Generate SAN BEFORE pushing the move.
        # board.san() needs the pre-move position to correctly disambiguate
        # moves like "Rad1" vs "Rfd1" (two rooks that can both reach d1).
        try:
            san = board.san(move)
        except (ValueError, AssertionError) as exc:
            raise ValueError(
                f"Could not generate SAN for move at ply {ply + 1} ({move.uci()}). "
                f"The move may be illegal in the current position. Details: {exc}"
            ) from exc

        # Collect all metadata from the current (pre-move) board state.
        moves.append(_extract_move(ply, move, board, san))

        # Advance the board. chess.Board.push() validates legality and raises
        # ValueError if the move is illegal — catches corrupted PGN move sequences.
        try:
            board.push(move)
        except ValueError as exc:
            raise ValueError(
                f"Illegal move at ply {ply + 1} ({san}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Step 3: Confirm the game has actual content
    # ------------------------------------------------------------------
    if not moves:
        raise ValueError(
            "The PGN was parsed successfully but contains no moves. "
            "Paste a complete game, not just headers."
        )

    # Merge header metadata with the move list into one flat return dict.
    return {
        **_extract_headers(game),
        "total_moves": len(moves),
        "moves": moves,
    }
