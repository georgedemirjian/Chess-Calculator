"""
Stockfish Service — manages a single engine process and evaluates chess positions.

Responsibilities:
  - Open and close a Stockfish subprocess once for the application lifetime.
  - Evaluate board positions and return centipawn scores from White's perspective.
  - Normalize mate scores to ±10_000 cp so downstream code never sees infinity.
  - Enrich pgn_parser move dicts with eval_before, eval_after, cp_loss, is_best_move,
    and is_forced — the inputs classifier.py needs to label each move.

Does NOT classify moves (that is classifier.py's job).
Does NOT know about FastAPI or HTTP (lifecycle is managed by main.py's lifespan).
"""

import chess
import chess.engine

from config import STOCKFISH_DEPTH, STOCKFISH_PATH
from services.centipawn_utils import compute_effective_cp_loss
from services.evaluation_utils import eval_to_win_prob
from services.probability_utils import compute_wp_loss

_MATE_SCORE = 10_000  # cp value substituted for a forced mate in either direction


class StockfishService:
    """Wraps a single Stockfish engine process for position evaluation."""

    def __init__(self, path: str = STOCKFISH_PATH, depth: int = STOCKFISH_DEPTH) -> None:
        self._path = path
        self._depth = depth
        self._engine: chess.engine.SimpleEngine | None = None

    def open(self) -> None:
        """Start the Stockfish subprocess. Call once at application startup."""
        self._engine = chess.engine.SimpleEngine.popen_uci(self._path)

    def close(self) -> None:
        """Terminate the engine process. Call once at application shutdown."""
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def _evaluate_position(self, board: chess.Board) -> tuple[int, str | None, int, int | None]:
        """
        Evaluate a single position.

        Returns (cp, best_move_uci, legal_move_count, mate_in):
            cp              — centipawns from White's perspective (positive = White better)
            best_move_uci   — engine's top choice in UCI format, None for terminal positions
            legal_move_count — 0 for checkmate/stalemate, used to detect forced moves
            mate_in         — moves until forced mate from White's POV (positive=white mates,
                              negative=black mates, 0=checkmate already on the board, None=no forced mate)
        """
        assert self._engine is not None, "open() must be called before evaluating positions."

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            # Terminal position — no engine call needed.
            if board.is_checkmate():
                cp = -_MATE_SCORE if board.turn == chess.WHITE else _MATE_SCORE
                mate_in: int | None = 0  # checkmate has already occurred
            else:
                cp = 0  # Stalemate or insufficient material
                mate_in = None
            return cp, None, 0, mate_in

        info = self._engine.analyse(board, chess.engine.Limit(depth=self._depth))
        score = info["score"].white()

        if score.is_mate():
            mate_in = score.mate()  # positive = white mates in N, negative = black mates in N
            cp = _MATE_SCORE if mate_in > 0 else -_MATE_SCORE  # type: ignore[operator]
        else:
            mate_in = None
            cp = score.score(mate_score=_MATE_SCORE)

        pv = info.get("pv") or []
        best_uci = pv[0].uci() if pv else None

        return cp, best_uci, len(legal_moves), mate_in

    def analyse_game(self, moves: list[dict]) -> list[dict]:
        """
        Evaluate every position in a game and return enriched move dicts.

        Each returned dict is the original move dict extended with:
            eval_before   — cp (White's POV) before the move is played
            eval_after    — cp (White's POV) after the move is played
            cp_loss       — centipawn loss from the moving player's perspective (>= 0)
            is_best_move  — True if the played move matches the engine's top choice
            is_forced     — True if there was only one legal move in the position

        Args:
            moves: list of move dicts from pgn_parser.parse(), each containing at
                   minimum "fen_before", "uci", and "color".
        """
        if not moves:
            return []

        # Build a board for every position: fen_before of each move, plus the
        # position after the final move (needed for eval_after on that last ply).
        boards = [chess.Board(m["fen_before"]) for m in moves]
        final_board = chess.Board(moves[-1]["fen_before"])
        final_board.push(chess.Move.from_uci(moves[-1]["uci"]))
        boards.append(final_board)

        # Evaluate each position sequentially. Stockfish processes one position at
        # a time internally, so parallel calls would not improve throughput.
        evals = [self._evaluate_position(b) for b in boards]

        enriched: list[dict] = []
        for i, move in enumerate(moves):
            cp_before, best_uci, legal_count, _ = evals[i]
            cp_after,  best_uci_after, _, mate_after = evals[i + 1]

            is_forced = legal_count == 1
            # Both UCIs come from chess.Move.uci(), so formatting is consistent.
            is_best_move = best_uci is not None and best_uci == move["uci"]

            # White wants eval to rise; Black wants it to fall.
            # Loss is always >= 0 (clamped): a move that gains material has 0 loss.
            if move["color"] == "white":
                cp_loss = max(0, cp_before - cp_after)
            else:
                cp_loss = max(0, cp_after - cp_before)

            enriched.append({
                **move,
                "eval_before": cp_before,
                "eval_after": cp_after,
                "cp_loss": cp_loss,
                "is_best_move": is_best_move,
                "is_forced": is_forced,
                "wp_before":         eval_to_win_prob(cp_before),
                "wp_after":          eval_to_win_prob(cp_after),
                "wp_loss":           compute_wp_loss(cp_before, cp_after, move["color"]),
                "effective_cp_loss": compute_effective_cp_loss(cp_loss, cp_before),
                "mate_after":        mate_after,
                # Engine's best move from the position AFTER this move was played
                # (i.e. what the opponent should play next). None on terminal
                # positions — the frontend uses this for the best-move arrow.
                "best_move_next_uci": best_uci_after,
            })

        return enriched
