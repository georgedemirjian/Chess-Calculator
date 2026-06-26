"""
generate_examples.py — Pre-analyse the curated portfolio games and write each
AnalyzeResponse as static JSON into frontend/public/examples/.

Why: the landing page lets visitors click a famous game and see a fully
populated analysis instantly, with no backend round-trip and no Stockfish
wait. Generation is offline; the request path stays untouched.

Run once (or whenever a PGN is added/replaced or the schema changes):
    source .venv/bin/activate
    cd backend
    python scripts/generate_examples.py

Each .pgn file under scripts/example_pgns/ becomes one JSON file using the
filename (minus extension) as the slug. The pipeline mirrors routers/analysis.py.
"""

import json
import sys
from pathlib import Path

# Make backend/ importable when running this file directly.
HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
sys.path.insert(0, str(BACKEND_DIR))

from config import STOCKFISH_DEPTH
from models.schemas import AnalyzeResponse, GameInfo, MoveAnalysis
from services import centipawn_utils, classifier, pgn_parser
from services.ml_service import MLService
from services.probability_utils import compute_avg_wp_loss
from services.stockfish_service import StockfishService

ML_MODEL_PATH = BACKEND_DIR / "ml" / "elo_model.joblib"
PGN_DIR       = HERE / "example_pgns"
OUT_DIR       = BACKEND_DIR.parent / "frontend" / "public" / "examples"


def analyse(pgn: str, engine: StockfishService, ml: MLService) -> dict:
    """Run parse → Stockfish → classify → ML, returning a JSON-ready dict."""
    game     = pgn_parser.parse(pgn)
    enriched = engine.analyse_game(game["moves"])

    white_raw, black_raw = [], []
    white_eff, black_eff = [], []
    white_wp,  black_wp  = [], []
    moves: list[MoveAnalysis] = []

    for m in enriched:
        label = classifier.classify_move(
            wp_loss=m["wp_loss"],
            is_best_move=m["is_best_move"],
            is_forced=m["is_forced"],
        )
        # ml_service.predict_for_player reads this back off the enriched dict.
        m["classification"] = label

        if m["color"] == "white":
            white_raw.append(m["cp_loss"])
            white_eff.append(m["effective_cp_loss"])
            white_wp.append(m["wp_loss"])
        else:
            black_raw.append(m["cp_loss"])
            black_eff.append(m["effective_cp_loss"])
            black_wp.append(m["wp_loss"])

        moves.append(MoveAnalysis(**{k: m[k] for k in (
            "move_number", "color", "san", "uci", "fen_before", "fen_after",
            "piece_moved", "is_capture", "is_en_passant", "is_castling",
            "is_check", "is_checkmate", "promotion",
            "eval_before", "eval_after", "cp_loss", "effective_cp_loss",
            "wp_before", "wp_after", "wp_loss", "mate_after",
            "best_move_next_uci",
        )}, classification=label))

    response = AnalyzeResponse(
        player_white=game["white"],
        player_black=game["black"],
        game_info=GameInfo(
            event=game["event"], site=game["site"], date=game["date"],
            result=game["result"], eco=game["eco"], opening=game["opening"],
        ),
        moves=moves,
        acpl_white=centipawn_utils.compute_acpl(white_raw),
        acpl_black=centipawn_utils.compute_acpl(black_raw),
        acpl_white_effective=centipawn_utils.compute_effective_acpl(white_eff),
        acpl_black_effective=centipawn_utils.compute_effective_acpl(black_eff),
        avg_wp_loss_white=compute_avg_wp_loss(white_wp),
        avg_wp_loss_black=compute_avg_wp_loss(black_wp),
        elo_estimate_white=ml.predict_for_player(enriched, "white"),
        elo_estimate_black=ml.predict_for_player(enriched, "black"),
        total_moves=game["total_moves"],
    )
    return response.model_dump(mode="json")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pgn_files = sorted(PGN_DIR.glob("*.pgn"))
    if not pgn_files:
        print(f"[examples] no .pgn files found in {PGN_DIR}")
        return

    ml = MLService(ML_MODEL_PATH)
    ml.open()
    depth = ml.depth if ml.is_loaded else STOCKFISH_DEPTH

    engine = StockfishService(depth=depth)
    engine.open()

    failures: list[tuple[str, str]] = []
    try:
        for pgn_path in pgn_files:
            slug = pgn_path.stem
            print(f"[examples] {slug} @ depth {depth} ...", flush=True)
            try:
                data = analyse(pgn_path.read_text(), engine, ml)
            except Exception as exc:
                print(f"[examples] FAILED {slug}: {exc}")
                failures.append((slug, str(exc)))
                continue
            out_path = OUT_DIR / f"{slug}.json"
            out_path.write_text(json.dumps(data, indent=2))
            print(f"[examples] wrote {out_path.relative_to(BACKEND_DIR.parent)} "
                  f"({len(data['moves'])} moves)")
    finally:
        engine.close()
        ml.close()

    if failures:
        print(f"\n[examples] {len(failures)} failed — fix the .pgn file and rerun:")
        for slug, err in failures:
            print(f"  - {slug}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
