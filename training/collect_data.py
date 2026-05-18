"""
collect_data.py — Download and filter Lichess monthly PGN bulk datasets.

Architectural decisions
-----------------------
Stream without saving the compressed source
    Lichess monthly dumps are 10–50 GB compressed. Saving them to disk would
    require 100–500 GB per few months of data. Instead, this script pipes the
    HTTP response through a zstd decompressor and into the PGN parser in one
    continuous stream — peak memory usage stays under ~50 MB regardless of
    dataset size.

Resumable via stream-position state file
    Seeking into a mid-stream zstd file is impossible (Lichess does not use
    the seekable-frame extension). Instead, a JSON state file records how many
    games were read from the stream before the last checkpoint. On restart the
    stream replays from byte 0 and fast-forwards to that position, then picks
    up where it left off. Fast-forwarding is cheap — reading PGN headers
    without Stockfish evaluation takes ~50–200 µs per game.

State checkpointed every CHECKPOINT_INTERVAL games
    The state file and output file are always kept in sync: the output buffer
    is flushed before the state file is written, so a crash between the two
    only causes a few games to be re-processed on resume, never duplicated.

One output file per calendar month
    Lichess organises its dumps by month. Matching that layout keeps raw data
    files manageable (~1–5 GB each as filtered PGN) and lets you collect
    additional months without touching existing files.

Filter order: headers before move iteration
    chess.pgn.read_game() parses the full game regardless, but we iterate
    mainline_moves() only for games that pass all header checks. This keeps
    the ply-count check from adding overhead to the large majority of games
    that are rejected earlier (wrong time control, provisional ratings, etc.).
"""

import argparse
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import chess.pgn
import requests
import zstandard as zstd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LICHESS_BASE = "https://database.lichess.org/standard"

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR   = SCRIPT_DIR / "data" / "raw"

# Rapid:     estimated game time in [480, 1 500) seconds
# Classical: estimated game time >= 1 500 seconds
# Estimation formula: base_seconds + increment_seconds × 40  (standard 40-move game)
RAPID_MIN_SECONDS     =   480   # 8 minutes
CLASSICAL_MIN_SECONDS = 1_500   # 25 minutes

MIN_PLIES = 40   # 20 full moves; shorter games carry too little signal

CHUNK_SIZE          = 1 << 20   # 1 MiB HTTP read chunks
LOG_INTERVAL        = 1_000     # print progress every N games saved
CHECKPOINT_INTERVAL = 10_000    # flush state to disk every N games read


# ---------------------------------------------------------------------------
# Time-control parsing
# ---------------------------------------------------------------------------

_TC_RE = re.compile(r"^(?:\d+/)?(\d+)(?:\+(\d+))?$")


def estimated_seconds(tc: str) -> int | None:
    """
    Parse a Lichess TimeControl header and return estimated game duration.

    Supported formats (all Lichess variants):
        "600"       → 600 s base, no increment
        "600+5"     → 600 + 5×40 = 800 s
        "1/180"     → 180 s  (per-move limit — treated normally)
        "-"         → correspondence / unlimited → None
    """
    if tc in ("-", "", "?"):
        return None
    m = _TC_RE.match(tc)
    if not m:
        return None
    base = int(m.group(1))
    inc  = int(m.group(2)) if m.group(2) else 0
    return base + inc * 40


def is_rapid_or_classical(tc: str) -> bool:
    secs = estimated_seconds(tc)
    return secs is not None and secs >= RAPID_MIN_SECONDS


# ---------------------------------------------------------------------------
# Per-game filtering
# ---------------------------------------------------------------------------

def is_provisional(elo_str: str | None) -> bool:
    """Lichess appends '?' to provisional ratings, e.g. '1450?'."""
    return elo_str is not None and elo_str.endswith("?")


def passes_filters(game: chess.pgn.Game) -> tuple[bool, str]:
    """
    Return (True, "") to keep the game, or (False, rejection_reason).

    Filters are ordered cheapest-first: header lookups before move iteration.
    """
    h = game.headers

    # 1. Rated games only — Lichess Event header always contains "Rated"
    if "Rated" not in h.get("Event", ""):
        return False, "not_rated"

    # 2. Rapid or Classical time controls only
    if not is_rapid_or_classical(h.get("TimeControl", "")):
        return False, "time_ctrl"

    # 3. Established (non-provisional) ratings for both players
    if is_provisional(h.get("WhiteElo")) or is_provisional(h.get("BlackElo")):
        return False, "provisional"

    # 4. Both players must have a recorded rating (not "?" or missing)
    we = h.get("WhiteElo", "")
    be = h.get("BlackElo", "")
    if not we.rstrip("?").isdigit() or not be.rstrip("?").isdigit():
        return False, "no_rating"

    # 5. Minimum move count — only iterate moves after all header checks pass
    plies = sum(1 for _ in game.mainline_moves())
    if plies < MIN_PLIES:
        return False, "short"

    return True, ""


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _state_path(output_pgn: Path) -> Path:
    return output_pgn.with_suffix(".state.json")


def load_state(output_pgn: Path) -> dict:
    sp = _state_path(output_pgn)
    if sp.exists():
        return json.loads(sp.read_text())
    return {"games_read": 0, "games_saved": 0, "stream_complete": False}


def save_state(output_pgn: Path, state: dict) -> None:
    # Atomic write: write to a temp file then rename so a crash here never
    # leaves a corrupt state file.
    tmp = _state_path(output_pgn).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(_state_path(output_pgn))


# ---------------------------------------------------------------------------
# HTTP + zstd streaming
# ---------------------------------------------------------------------------

def open_lichess_stream(url: str) -> tuple[io.TextIOWrapper, int]:
    """
    Open a streaming HTTP connection to a Lichess .pgn.zst file and return a
    decoded text stream plus the remote file size in bytes (0 if unknown).

    The decompressor is wired directly to the HTTP response body — no
    intermediate bytes are buffered beyond the zstd window (~8 MB).
    """
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    total_bytes = int(resp.headers.get("Content-Length", 0))
    if total_bytes:
        print(f"  Remote compressed size: {total_bytes / 1e9:.2f} GB")

    # max_window_size raised to 2 GiB to handle Lichess's large frames.
    dctx    = zstd.ZstdDecompressor(max_window_size=2 ** 31)
    raw     = dctx.stream_reader(resp.raw, read_size=CHUNK_SIZE)
    text    = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
    return text, total_bytes


# ---------------------------------------------------------------------------
# Collection loop
# ---------------------------------------------------------------------------

class FilterStats(NamedTuple):
    read:             int
    saved:            int
    skip_not_rated:   int
    skip_time_ctrl:   int
    skip_provisional: int
    skip_no_rating:   int
    skip_short:       int


def collect_month(year: int, month: int, max_games: int | None = None) -> FilterStats:
    """
    Stream one month of Lichess rated games, apply filters, and append passing
    games to training/data/raw/<YYYY-MM>.pgn.

    Returns a FilterStats summary of this run (not cumulative across resumes).
    """
    month_str  = f"{year:04d}-{month:02d}"
    url        = f"{LICHESS_BASE}/lichess_db_standard_rated_{month_str}.pgn.zst"
    output_pgn = DATA_DIR / f"{month_str}.pgn"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # --- Guard against a missing state file when output already exists -----
    state = load_state(output_pgn)
    if output_pgn.exists() and not _state_path(output_pgn).exists():
        print(
            f"[warn] {output_pgn.name} exists but no state file was found.\n"
            f"       Delete {output_pgn.name} to start fresh, or restore the "
            f"state file to resume.",
            file=sys.stderr,
        )
        sys.exit(1)

    if state.get("stream_complete"):
        print(
            f"[done] {month_str} was already fully processed "
            f"({state['games_saved']:,} games saved). "
            f"Delete the .state.json to reprocess."
        )
        return FilterStats(state["games_read"], state["games_saved"], 0, 0, 0, 0, 0)

    # --- Resume position ---------------------------------------------------
    # games_read_prev is our stream cursor: the number of games consumed from
    # the Lichess stream before the last checkpoint. We replay from byte 0 and
    # fast-forward past this count before resuming saves.
    games_read_prev = state.get("games_read", 0)
    if games_read_prev:
        print(
            f"[resume] {month_str}: fast-forwarding past {games_read_prev:,} "
            f"already-processed games …"
        )

    print(f"\n{'=' * 60}")
    print(f"Collecting {month_str}  →  {output_pgn.name}")
    print(f"Source:    {url}")
    print(f"{'=' * 60}")

    # Per-run accumulators (do not include work from previous runs)
    games_read       = 0
    games_saved      = state.get("games_saved", 0)   # cumulative total
    skip_not_rated   = 0
    skip_time_ctrl   = 0
    skip_provisional = 0
    skip_no_rating   = 0
    skip_short       = 0
    t_start          = time.monotonic()

    def _flush_state(complete: bool) -> None:
        out_file.flush()   # ensure output is on disk before touching state
        save_state(output_pgn, {
            "games_read":      games_read_prev + games_read,
            "games_saved":     games_saved,
            "stream_complete": complete,
        })

    try:
        text_stream, _ = open_lichess_stream(url)

        with output_pgn.open("a", encoding="utf-8") as out_file:
            while True:
                try:
                    game = chess.pgn.read_game(text_stream)
                except Exception as exc:
                    print(f"[warn] PGN parse error (game ~{games_read_prev + games_read}): {exc}", file=sys.stderr)
                    continue

                if game is None:
                    break  # clean end of stream

                games_read += 1
                total_read = games_read_prev + games_read

                # Fast-forward past games already written in a previous run.
                if total_read <= games_read_prev:
                    if games_read % 50_000 == 0:
                        pct = 100 * games_read / games_read_prev
                        print(f"  [ff] {games_read:,} / {games_read_prev:,} ({pct:.1f}%)")
                    continue

                # --- Apply filters ---
                ok, reason = passes_filters(game)
                if not ok:
                    if   reason == "not_rated":   skip_not_rated   += 1
                    elif reason == "time_ctrl":   skip_time_ctrl   += 1
                    elif reason == "provisional": skip_provisional += 1
                    elif reason == "no_rating":   skip_no_rating   += 1
                    elif reason == "short":       skip_short       += 1
                    # Periodic checkpoint on rejected games too so stream
                    # position is saved even in months with low pass rates.
                    if games_read % CHECKPOINT_INTERVAL == 0:
                        _flush_state(complete=False)
                    continue

                # --- Write passing game ---
                print(game, file=out_file, end="\n\n")
                games_saved += 1

                if games_saved % LOG_INTERVAL == 0:
                    elapsed = time.monotonic() - t_start
                    rate    = games_read / max(elapsed, 0.001)
                    print(
                        f"  read={total_read:>9,} | saved={games_saved:>8,} | "
                        f"{rate:,.0f} games/s | "
                        f"skip[rated={skip_not_rated} tc={skip_time_ctrl} "
                        f"prov={skip_provisional} short={skip_short}]"
                    )

                if games_read % CHECKPOINT_INTERVAL == 0:
                    _flush_state(complete=False)

                if max_games is not None and games_saved >= max_games:
                    print(f"[limit] Reached --max-games={max_games}, stopping.")
                    _flush_state(complete=False)
                    break

    except KeyboardInterrupt:
        print(f"\n[interrupt] Stopped at stream game {games_read_prev + games_read:,}. Saving state …")
        _flush_state(complete=False)
        raise

    _flush_state(complete=(max_games is None))

    elapsed = time.monotonic() - t_start
    size_mb = output_pgn.stat().st_size / 1e6

    print(f"\n[done] {month_str} in {elapsed:.0f}s")
    print(f"  Stream games read : {games_read_prev + games_read:>10,}")
    print(f"  Saved (cumulative): {games_saved:>10,}  ({size_mb:.1f} MB)")
    print(f"  Rejected - not rated   : {skip_not_rated:>10,}")
    print(f"  Rejected - time ctrl   : {skip_time_ctrl:>10,}")
    print(f"  Rejected - provisional : {skip_provisional:>10,}")
    print(f"  Rejected - no rating   : {skip_no_rating:>10,}")
    print(f"  Rejected - too short   : {skip_short:>10,}")

    return FilterStats(
        read=games_read_prev + games_read,
        saved=games_saved,
        skip_not_rated=skip_not_rated,
        skip_time_ctrl=skip_time_ctrl,
        skip_provisional=skip_provisional,
        skip_no_rating=skip_no_rating,
        skip_short=skip_short,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_months(spec: str) -> list[tuple[int, int]]:
    """
    Parse a month specification string into a list of (year, month) pairs.

    "2024-01"          → [(2024, 1)]
    "2023-11:2024-02"  → [(2023,11), (2023,12), (2024,1), (2024,2)]
    """
    if ":" in spec:
        lo_str, hi_str = spec.split(":", 1)
        lo = datetime.strptime(lo_str.strip(), "%Y-%m")
        hi = datetime.strptime(hi_str.strip(), "%Y-%m")
        result: list[tuple[int, int]] = []
        cur = lo
        while cur <= hi:
            result.append((cur.year, cur.month))
            cur = cur.replace(month=cur.month % 12 + 1, year=cur.year + (cur.month // 12))
        return result
    d = datetime.strptime(spec.strip(), "%Y-%m")
    return [(d.year, d.month)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and filter Lichess PGN bulk datasets for Elo estimation training.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download one month
  python collect_data.py --months 2024-01

  # Download an inclusive range (6 months)
  python collect_data.py --months 2023-07:2023-12

  # Quick sample — stop after 50 000 saved games (useful for testing)
  python collect_data.py --months 2024-01 --max-games 50000

Output:
  training/data/raw/<YYYY-MM>.pgn        filtered PGN
  training/data/raw/<YYYY-MM>.state.json resumability checkpoint

Resuming:
  Simply re-run the same command. The script reads the state file and
  fast-forwards past already-processed stream games before saving new ones.
        """,
    )
    parser.add_argument(
        "--months",
        required=True,
        metavar="SPEC",
        help="Month or range: YYYY-MM  or  YYYY-MM:YYYY-MM",
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        metavar="N",
        help="Stop after saving N games per month (useful for sampling)",
    )
    args = parser.parse_args()

    months = _parse_months(args.months)
    labels = [f"{y}-{m:02d}" for y, m in months]
    print(f"Months to process: {labels}")

    totals = FilterStats(0, 0, 0, 0, 0, 0, 0)
    for year, month in months:
        s = collect_month(year, month, max_games=args.max_games)
        totals = FilterStats(
            read=totals.read + s.read,
            saved=totals.saved + s.saved,
            skip_not_rated=totals.skip_not_rated + s.skip_not_rated,
            skip_time_ctrl=totals.skip_time_ctrl + s.skip_time_ctrl,
            skip_provisional=totals.skip_provisional + s.skip_provisional,
            skip_no_rating=totals.skip_no_rating + s.skip_no_rating,
            skip_short=totals.skip_short + s.skip_short,
        )

    if len(months) > 1:
        print(f"\n{'=' * 60}")
        print("TOTAL ACROSS ALL MONTHS")
        print(f"  Stream games read : {totals.read:>10,}")
        print(f"  Saved             : {totals.saved:>10,}")


if __name__ == "__main__":
    main()
