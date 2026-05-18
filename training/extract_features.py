"""
extract_features.py — Run Stockfish analysis on collected PGNs and write a
feature matrix suitable for Elo-estimation model training.

Performance considerations
--------------------------
Stockfish is the dominant cost. For a 40-move game (~80 plies), the script runs
~80 position evaluations plus a few terminal checks. Approximate wall-clock per
game on a modern laptop:

    depth 12   ~ 1.0 – 1.5 s/game     (rough screening; not recommended)
    depth 14   ~ 2.0 – 4.0 s/game     ← recommended for training & inference
    depth 16   ~ 4.0 – 8.0 s/game     (slower; marginal classification gain)
    depth 18   ~ 8.0 – 18  s/game     (current backend default; too slow at ML scale)
    depth 22   ~ 30+      s/game     (Lichess server analysis; overkill here)

CRITICAL: training and inference must use the SAME depth.
The ML model learns the distribution of `avg_wp_loss`, `blunder_rate`, etc. at
the training depth. Increasing depth at inference shifts those distributions
and produces miscalibrated Elo predictions. Pick one depth and use it for
collect → train → predict.

Parallelism
    Stockfish itself is single-threaded by default. The cleanest way to use
    multiple cores is to run several instances of this script in parallel on
    different input files (--files 2024-01.pgn vs. --files 2024-02.pgn). Each
    instance keeps its own state file, so they will not collide. We deliberately
    avoid multiprocessing.Pool inside the script — it complicates checkpointing
    and offers no speedup over running parallel processes on disjoint files.

Memory
    Games are streamed one at a time from disk via chess.pgn.read_game(). At
    any moment the process holds one Game object, its analysed move list (~80
    dicts), and a small batch of rows pending CSV write. Peak memory stays
    under ~100 MB regardless of dataset size.

Checkpointing
    A state file <pgn>.features.state.json tracks how many games of the PGN
    have been processed. On restart the script fast-forwards through that many
    games using chess.pgn.skip_game() (no full parse, no Stockfish calls), then
    resumes. Output rows are appended to the CSV between checkpoints; the CSV
    is flushed before the state file is written so a crash cannot lose or
    duplicate rows.
"""

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

# --- Backend imports ------------------------------------------------------
# The training pipeline must use the exact same analysis logic as the FastAPI
# backend, so we add backend/ to sys.path and import its services directly.
# This guarantees feature parity between training and inference — features
# computed here are identical to features computed at request time.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import chess.pgn  # noqa: E402

from config import STOCKFISH_PATH  # noqa: E402
from services import classifier, pgn_parser  # noqa: E402
from services.centipawn_utils import compute_effective_acpl  # noqa: E402
from services.probability_utils import compute_avg_wp_loss  # noqa: E402
from services.stockfish_service import StockfishService  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_DIR    = SCRIPT_DIR / "data" / "raw"
CSV_PATH   = SCRIPT_DIR / "data" / "features.csv"

DEFAULT_DEPTH        =   14   # see module docstring — match training & inference
DEFAULT_BATCH_SIZE   =   25   # rows held in memory before CSV flush
DEFAULT_CHECKPOINT   =  100   # save state every N processed games
DEFAULT_LOG_INTERVAL =   10   # print progress every N processed games

# Column ordering for the output CSV. The same list is consumed by train.py
# to ensure feature-vector alignment between training and inference.
CSV_COLUMNS: list[str] = [
    "game_id",
    "source_file",
    "color",
    "elo",
    "avg_wp_loss",
    "effective_acpl",
    "best_rate",
    "excellent_rate",
    "good_rate",
    "inaccuracy_rate",
    "mistake_rate",
    "blunder_rate",
    "forced_rate",
    "n_moves_analyzed",
    "depth",
]


# ---------------------------------------------------------------------------
# Per-game feature extraction
# ---------------------------------------------------------------------------

def _game_id(game: chess.pgn.Game, source_file: str, index: int) -> str:
    """
    Stable identifier for a single game. Lichess PGNs always include a
    Site URL like "https://lichess.org/abc123" — extract the slug. Fall back
    to a hash of (source file + index + headers) for non-Lichess sources.
    """
    site = game.headers.get("Site", "")
    if "lichess.org/" in site:
        slug = site.split("lichess.org/")[-1].split("/")[0]
        if slug:
            return slug
    fingerprint = f"{source_file}:{index}:{game.headers.get('UTCDate','')}:{game.headers.get('White','')}:{game.headers.get('Black','')}"
    return hashlib.md5(fingerprint.encode()).hexdigest()[:12]


def _player_features(enriched_moves: list[dict[str, Any]], color: str) -> dict[str, Any] | None:
    """
    Compute the feature vector for one player from a fully-analysed move list.

    Returns None if the player has zero non-forced moves (extremely rare —
    only possible when the game is so short the player was always forced).
    """
    player_moves = [m for m in enriched_moves if m["color"] == color]
    n_total      = len(player_moves)
    if n_total == 0:
        return None

    non_forced   = [m for m in player_moves if m["classification"] != "forced"]
    n_non_forced = len(non_forced)
    if n_non_forced == 0:
        return None

    counts: dict[str, int] = {
        "best": 0, "excellent": 0, "good": 0,
        "inaccuracy": 0, "mistake": 0, "blunder": 0,
    }
    for m in non_forced:
        cls = m["classification"]
        if cls in counts:
            counts[cls] += 1

    return {
        "avg_wp_loss":      compute_avg_wp_loss([m["wp_loss"]           for m in non_forced]),
        "effective_acpl":   compute_effective_acpl([m["effective_cp_loss"] for m in non_forced]),
        "best_rate":        counts["best"]       / n_non_forced,
        "excellent_rate":   counts["excellent"]  / n_non_forced,
        "good_rate":        counts["good"]       / n_non_forced,
        "inaccuracy_rate":  counts["inaccuracy"] / n_non_forced,
        "mistake_rate":     counts["mistake"]    / n_non_forced,
        "blunder_rate":     counts["blunder"]    / n_non_forced,
        "forced_rate":      (n_total - n_non_forced) / n_total,
        "n_moves_analyzed": n_non_forced,
    }


def analyse_one_game(
    game: chess.pgn.Game,
    stockfish: StockfishService,
    depth: int,
    source_file: str,
    index: int,
) -> list[dict[str, Any]] | None:
    """
    Analyse a single chess.pgn.Game and return up to two CSV rows (one per
    player). Returns None if the game cannot be used as a training observation.
    """
    # --- 1. Elo labels --------------------------------------------------
    # Both players must have a numeric, non-provisional rating. collect_data.py
    # already filters these, but we re-check defensively in case raw PGNs
    # were added manually.
    white_str = game.headers.get("WhiteElo", "").rstrip("?").strip()
    black_str = game.headers.get("BlackElo", "").rstrip("?").strip()
    if not (white_str.isdigit() and black_str.isdigit()):
        return None
    white_elo = int(white_str)
    black_elo = int(black_str)

    # --- 2. Re-use backend parsing -------------------------------------
    # str(game) re-serialises the game to PGN. pgn_parser.parse() then
    # produces the exact same move dicts the FastAPI /api/analyze route uses.
    try:
        parsed = pgn_parser.parse(str(game))
    except ValueError:
        # Illegal moves, empty mainline, or other PGN problems — skip.
        return None

    # --- 3. Stockfish analysis -----------------------------------------
    enriched = stockfish.analyse_game(parsed["moves"])

    # --- 4. Classify each move (same call signature as backend router) --
    for m in enriched:
        m["classification"] = classifier.classify_move(
            wp_loss=m["wp_loss"],
            is_best_move=m["is_best_move"],
            is_forced=m["is_forced"],
        )

    # --- 5. Per-player aggregates ---------------------------------------
    white_feats = _player_features(enriched, "white")
    black_feats = _player_features(enriched, "black")
    if white_feats is None or black_feats is None:
        return None

    gid = _game_id(game, source_file, index)
    common = {"game_id": gid, "source_file": source_file, "depth": depth}
    return [
        {**common, "color": "white", "elo": white_elo, **white_feats},
        {**common, "color": "black", "elo": black_elo, **black_feats},
    ]


# ---------------------------------------------------------------------------
# CSV + state management
# ---------------------------------------------------------------------------

def append_rows(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    """Append a batch of feature rows to the CSV, writing the header on first use."""
    if not rows:
        return
    is_new = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
        f.flush()  # ensure rows are on disk before state file is updated


def _state_path(pgn_path: Path) -> Path:
    """State file lives alongside the PGN: 2024-01.pgn → 2024-01.features.state.json."""
    return pgn_path.with_suffix(".features.state.json")


def load_state(pgn_path: Path) -> dict[str, Any]:
    sp = _state_path(pgn_path)
    if sp.exists():
        return json.loads(sp.read_text())
    return {"games_processed": 0, "games_succeeded": 0, "games_failed": 0, "complete": False}


def save_state(pgn_path: Path, state: dict[str, Any]) -> None:
    tmp = _state_path(pgn_path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(_state_path(pgn_path))


# ---------------------------------------------------------------------------
# Per-file processing loop
# ---------------------------------------------------------------------------

def process_pgn_file(
    pgn_path:    Path,
    csv_path:    Path,
    stockfish:   StockfishService,
    depth:       int,
    batch_size:  int,
    checkpoint:  int,
    log_every:   int,
    max_games:   int | None,
) -> dict[str, int]:
    """
    Stream all games from a single PGN file, extract features, append to CSV.
    Returns a summary dict with processing counts for this run.
    """
    state = load_state(pgn_path)
    if state.get("complete"):
        print(f"[done] {pgn_path.name} already fully processed "
              f"({state['games_succeeded']:,} usable / "
              f"{state['games_processed']:,} read). "
              f"Delete its .features.state.json to reprocess.")
        return {"processed": 0, "succeeded": 0, "failed": 0}

    skip_count = state["games_processed"]
    if skip_count:
        print(f"[resume] {pgn_path.name}: fast-forwarding past {skip_count:,} games …")

    print(f"\n{'=' * 60}")
    print(f"File:   {pgn_path.name}")
    print(f"Output: {csv_path}")
    print(f"Depth:  {depth}")
    print(f"{'=' * 60}")

    games_processed = state["games_processed"]
    games_succeeded = state["games_succeeded"]
    games_failed    = state["games_failed"]
    batch: list[dict[str, Any]] = []
    t_start  = time.monotonic()
    t_window = t_start
    run_processed = 0   # games processed in THIS run (for rate calc)

    def _checkpoint(complete: bool) -> None:
        nonlocal batch
        if batch:
            append_rows(csv_path, batch)
            batch = []
        save_state(pgn_path, {
            "games_processed": games_processed,
            "games_succeeded": games_succeeded,
            "games_failed":    games_failed,
            "complete":        complete,
        })

    try:
        with pgn_path.open("r", encoding="utf-8", errors="replace") as handle:
            # Fast-forward without parsing moves or calling Stockfish.
            # chess.pgn.skip_game advances the stream past one game very cheaply.
            for _ in range(skip_count):
                if not chess.pgn.skip_game(handle):
                    print(f"[warn] {pgn_path.name}: state claims {skip_count:,} games "
                          f"processed but file ended early — restarting from EOF",
                          file=sys.stderr)
                    break

            while True:
                game_idx = games_processed   # 0-based position in the file
                game = chess.pgn.read_game(handle)
                if game is None:
                    break

                games_processed += 1
                run_processed   += 1

                try:
                    rows = analyse_one_game(game, stockfish, depth, pgn_path.name, game_idx)
                except Exception as exc:
                    games_failed += 1
                    print(f"[warn] {pgn_path.name} game #{game_idx}: {exc}", file=sys.stderr)
                    rows = None

                if rows is None:
                    # Not a usable training observation (missing ratings, parse
                    # failure, all-forced moves, etc.) — counted but not written.
                    pass
                else:
                    batch.extend(rows)
                    games_succeeded += 1

                # Flush the row batch
                if len(batch) >= batch_size:
                    append_rows(csv_path, batch)
                    batch = []

                # Save state periodically so an interrupted run loses minutes,
                # not hours.
                if games_processed % checkpoint == 0:
                    _checkpoint(complete=False)

                # Progress log
                if run_processed % log_every == 0:
                    now      = time.monotonic()
                    rate     = log_every / max(now - t_window, 1e-6)
                    overall  = run_processed / max(now - t_start, 1e-6)
                    t_window = now
                    print(
                        f"  [{pgn_path.name}] processed={games_processed:>7,} | "
                        f"saved={games_succeeded:>7,} | "
                        f"failed={games_failed:>5,} | "
                        f"window={rate:>4.2f} g/s | "
                        f"overall={overall:>4.2f} g/s"
                    )

                if max_games is not None and run_processed >= max_games:
                    print(f"[limit] Reached --max-games={max_games}, stopping {pgn_path.name}.")
                    _checkpoint(complete=False)
                    return {"processed": run_processed, "succeeded": games_succeeded, "failed": games_failed}

    except KeyboardInterrupt:
        print(f"\n[interrupt] Saving progress for {pgn_path.name} before exit …")
        _checkpoint(complete=False)
        raise

    _checkpoint(complete=True)

    elapsed = time.monotonic() - t_start
    print(f"\n[done] {pgn_path.name} in {elapsed/60:.1f} min "
          f"({run_processed} processed, {games_succeeded - state['games_succeeded']} saved this run)")

    return {"processed": run_processed, "succeeded": games_succeeded, "failed": games_failed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_input_files(arg_files: list[str] | None) -> list[Path]:
    """If --files was provided, resolve each name within RAW_DIR. Otherwise
    take every .pgn file in RAW_DIR sorted alphabetically (which sorts by month)."""
    if arg_files:
        out: list[Path] = []
        for name in arg_files:
            p = (RAW_DIR / name) if not Path(name).is_absolute() else Path(name)
            if not p.exists():
                print(f"[error] PGN file not found: {p}", file=sys.stderr)
                sys.exit(2)
            out.append(p)
        return out

    files = sorted(RAW_DIR.glob("*.pgn"))
    if not files:
        print(f"[error] No .pgn files found in {RAW_DIR}. "
              f"Run collect_data.py first.", file=sys.stderr)
        sys.exit(2)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Stockfish analysis on collected PGNs and write features.csv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process every PGN file in training/data/raw/ at default depth (14)
  python extract_features.py

  # Process specific files in parallel (run each in its own terminal)
  python extract_features.py --files 2024-01.pgn
  python extract_features.py --files 2024-02.pgn

  # Smoke test on a small sample
  python extract_features.py --files 2024-01.pgn --max-games 100

  # Higher depth for a small high-quality test set
  python extract_features.py --files 2024-12.pgn --depth 16

Output:
  training/data/features.csv                     feature matrix (append-only)
  training/data/raw/<file>.features.state.json   per-file resumability state

Resuming:
  Re-run the same command. The script fast-forwards past games already in the
  state file and continues appending to the same features.csv.
        """,
    )
    parser.add_argument("--files", nargs="+", metavar="PGN",
                        help="One or more PGN filenames inside training/data/raw/ (default: all)")
    parser.add_argument("--output", type=Path, default=CSV_PATH, metavar="CSV",
                        help=f"Output CSV path (default: {CSV_PATH.relative_to(PROJECT_ROOT)})")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, metavar="N",
                        help=f"Stockfish depth (default: {DEFAULT_DEPTH}; MUST match inference depth)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, metavar="N",
                        help=f"Rows held in memory before CSV flush (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--checkpoint", type=int, default=DEFAULT_CHECKPOINT, metavar="N",
                        help=f"Save state every N processed games (default: {DEFAULT_CHECKPOINT})")
    parser.add_argument("--log-every", type=int, default=DEFAULT_LOG_INTERVAL, metavar="N",
                        help=f"Print progress every N games (default: {DEFAULT_LOG_INTERVAL})")
    parser.add_argument("--max-games", type=int, default=None, metavar="N",
                        help="Stop after processing N games per file (useful for sampling)")
    args = parser.parse_args()

    input_files = _resolve_input_files(args.files)
    print(f"Input files ({len(input_files)}):")
    for p in input_files:
        print(f"  - {p.name}")
    print(f"Stockfish path:  {STOCKFISH_PATH}")
    print(f"Stockfish depth: {args.depth}")
    print(f"Output:          {args.output}")

    stockfish = StockfishService(path=STOCKFISH_PATH, depth=args.depth)
    stockfish.open()

    totals = {"processed": 0, "succeeded": 0, "failed": 0}
    try:
        for pgn_path in input_files:
            summary = process_pgn_file(
                pgn_path=pgn_path,
                csv_path=args.output,
                stockfish=stockfish,
                depth=args.depth,
                batch_size=args.batch_size,
                checkpoint=args.checkpoint,
                log_every=args.log_every,
                max_games=args.max_games,
            )
            for k, v in summary.items():
                totals[k] += v
    finally:
        stockfish.close()

    print(f"\n{'=' * 60}")
    print(f"TOTAL across {len(input_files)} file(s)")
    print(f"  Processed: {totals['processed']:,}")
    print(f"  Saved:     {totals['succeeded']:,}  (×2 rows per game)")
    print(f"  Failed:    {totals['failed']:,}")
    print(f"  Output:    {args.output}")


if __name__ == "__main__":
    main()
