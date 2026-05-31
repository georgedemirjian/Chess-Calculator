"""
collect_data.py — Stream Lichess monthly PGNs and assemble a STRATIFIED,
Elo-balanced training set.

Architectural decisions
-----------------------
Stratified sampling at collection time
    Naive sequential collection over-represents 1300–2000 Elo (where the bulk
    of Lichess play sits) and under-represents both tails. A regression model
    trained on that distribution drifts toward the population mean and gives
    biased predictions for strong and weak players. Instead, we define
    explicit Elo buckets and stop adding games to each bucket once its target
    is met. Once every bucket is at target the stream is closed early.

Per-color sampling
    Each game contributes two independent observations: WhiteElo / BlackElo.
    We accept a game if at least one of its colors falls in a non-full bucket
    (we'd run Stockfish on the full game anyway, so emitting both colors when
    possible is free). The accepted color set is recorded on a custom PGN
    header `[Sample "white,black"]` so `extract_features.py` knows which
    player(s) to emit as training rows.

Optional player deduplication
    A small number of Lichess users play hundreds of rated games a month. Left
    unchecked, they would dominate one or more buckets and the model would
    learn their idiosyncrasies. `--per-player-cap N` (recommended 10) bounds
    each username's contribution across all months.

Global sampling state across months
    Bucket counts accumulate across runs. If a first run on 2024-01 fills the
    1500–1700 bucket, a follow-up run on 2024-02 will skip 1500–1700 games
    automatically. The per-month state file keeps the stream cursor; the
    global file `data/raw/_sampling_state.json` keeps bucket and player
    counts. `--reset` wipes the global file but not collected PGNs.

Streaming + early stop
    The script never loads a PGN into memory. It pipes the HTTP response
    through zstd into the PGN parser one game at a time and stops as soon as
    every bucket reaches target — typically after a fraction of any given
    month's data.

Resumable via stream-position state file
    Seeking into a mid-stream zstd file is impossible (Lichess does not use
    the seekable-frame extension). A per-month JSON state file records how
    many games were read from the stream before the last checkpoint. On
    restart the stream replays from byte 0 and fast-forwards past that count
    — header-only PGN reads are cheap (~50–200 µs per game).
"""

import argparse
import io
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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
LOG_INTERVAL        = 2_000     # print bucket table every N games READ
CHECKPOINT_INTERVAL = 10_000    # flush state to disk every N games read

# ---------------------------------------------------------------------------
# Elo bucket configuration
# ---------------------------------------------------------------------------
# Each bucket is (lo_inclusive, hi_exclusive). Twelve 200-wide bins covering
# 400–2800 span ≈ 99.5 % of Lichess rapid/classical players. Edit this list
# (and re-run with --reset) if you want different ranges — e.g. wider tail
# bins to make them easier to fill.
BUCKETS: list[tuple[int, int]] = [
    ( 400,  600),
    ( 600,  800),
    ( 800, 1000),
    (1000, 1200),
    (1200, 1400),
    (1400, 1600),
    (1600, 1800),
    (1800, 2000),
    (2000, 2200),
    (2200, 2400),
    (2400, 2600),
    (2600, 2800),
]

DEFAULT_TARGET_PER_BUCKET = 2000   # samples per COLOR per bucket
DEFAULT_PER_PLAYER_CAP    = None   # None = unlimited; recommended ≈ 10

GLOBAL_STATE_PATH = DATA_DIR / "_sampling_state.json"


def _bucket_for(elo: int) -> tuple[int, int] | None:
    """Return the (lo, hi) bucket containing elo, or None if outside all buckets."""
    for lo, hi in BUCKETS:
        if lo <= elo < hi:
            return (lo, hi)
    return None


def _bucket_key(bucket: tuple[int, int]) -> str:
    return f"{bucket[0]}-{bucket[1]}"


# ---------------------------------------------------------------------------
# Time-control parsing
# ---------------------------------------------------------------------------

_TC_RE = re.compile(r"^(?:\d+/)?(\d+)(?:\+(\d+))?$")


def estimated_seconds(tc: str) -> int | None:
    """Parse a Lichess TimeControl header and return estimated game duration."""
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


def is_provisional(elo_str: str | None) -> bool:
    """Lichess appends '?' to provisional ratings, e.g. '1450?'."""
    return elo_str is not None and elo_str.endswith("?")


# ---------------------------------------------------------------------------
# Sampling state — global across months
# ---------------------------------------------------------------------------

def load_sampling_state() -> dict:
    """Load global bucket-fill / player-count state shared across months."""
    if GLOBAL_STATE_PATH.exists():
        s = json.loads(GLOBAL_STATE_PATH.read_text())
        # Backfill any newly-added buckets so editing BUCKETS doesn't crash a resume.
        for b in BUCKETS:
            s["bucket_counts"].setdefault(_bucket_key(b), {"white": 0, "black": 0})
        return s
    return {
        "bucket_counts": {_bucket_key(b): {"white": 0, "black": 0} for b in BUCKETS},
        "player_counts": {},
    }


def save_sampling_state(state: dict) -> None:
    GLOBAL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = GLOBAL_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(GLOBAL_STATE_PATH)


def all_buckets_full(state: dict, target: int) -> bool:
    return all(
        c["white"] >= target and c["black"] >= target
        for c in state["bucket_counts"].values()
    )


def format_bucket_table(state: dict, target: int) -> str:
    """One-line-per-bucket fill table for periodic progress logs."""
    lines = [f"  {'Bucket':<10}  {'White':>13}  {'Black':>13}"]
    for b in BUCKETS:
        bk = _bucket_key(b)
        w  = state["bucket_counts"][bk]["white"]
        bl = state["bucket_counts"][bk]["black"]
        w_pct  = min(100, int(100 * w / target)) if target else 0
        b_pct  = min(100, int(100 * bl / target)) if target else 0
        w_full = "✓" if w >= target else " "
        b_full = "✓" if bl >= target else " "
        lines.append(
            f"  {bk:<10}  "
            f"{w:>5}/{target} {w_pct:>3}%{w_full}  "
            f"{bl:>5}/{target} {b_pct:>3}%{b_full}"
        )
    total_w = sum(c["white"] for c in state["bucket_counts"].values())
    total_b = sum(c["black"] for c in state["bucket_counts"].values())
    total_target = target * len(BUCKETS)
    lines.append(
        f"  {'TOTAL':<10}  "
        f"{total_w:>5}/{total_target}        "
        f"{total_b:>5}/{total_target}"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-game eligibility
# ---------------------------------------------------------------------------

def evaluate_game(
    game: chess.pgn.Game,
    sampling_state: dict,
    target: int,
    per_player_cap: int | None,
) -> tuple[list[str], str]:
    """
    Decide whether to keep a game and which color(s) to mark as training samples.

    Returns:
        (accepted_colors, reason)
            accepted_colors — subset of ["white", "black"]
            reason          — empty if accepted, otherwise a short tag
                              ("not_rated", "time_ctrl", "provisional",
                              "no_rating", "short", "out_of_range",
                              "buckets_full", "player_cap")

    Pure: does not mutate sampling_state.
    """
    h = game.headers

    # ---- basic header filters (cheapest first, header-only) ---------------
    if "Rated" not in h.get("Event", ""):
        return [], "not_rated"
    if not is_rapid_or_classical(h.get("TimeControl", "")):
        return [], "time_ctrl"
    if is_provisional(h.get("WhiteElo")) or is_provisional(h.get("BlackElo")):
        return [], "provisional"

    we = h.get("WhiteElo", "")
    be = h.get("BlackElo", "")
    if not we.rstrip("?").isdigit() or not be.rstrip("?").isdigit():
        return [], "no_rating"

    # ---- bucket eligibility (header-only, still no move iteration) --------
    white_elo = int(we)
    black_elo = int(be)
    white_bucket = _bucket_for(white_elo)
    black_bucket = _bucket_for(black_elo)

    if white_bucket is None and black_bucket is None:
        return [], "out_of_range"

    white_user = h.get("White", "")
    black_user = h.get("Black", "")

    accepted: list[str] = []
    capped = False
    bucket_full = False

    if white_bucket is not None:
        bk = _bucket_key(white_bucket)
        has_room = sampling_state["bucket_counts"][bk]["white"] < target
        player_ok = (
            per_player_cap is None
            or sampling_state["player_counts"].get(white_user, 0) < per_player_cap
        )
        if has_room and player_ok:
            accepted.append("white")
        elif not has_room:
            bucket_full = True
        else:
            capped = True

    if black_bucket is not None:
        bk = _bucket_key(black_bucket)
        has_room = sampling_state["bucket_counts"][bk]["black"] < target
        player_ok = (
            per_player_cap is None
            or sampling_state["player_counts"].get(black_user, 0) < per_player_cap
        )
        if has_room and player_ok:
            accepted.append("black")
        elif not has_room:
            bucket_full = True
        else:
            capped = True

    if accepted:
        # Only iterate moves once we know we want the game.
        plies = sum(1 for _ in game.mainline_moves())
        if plies < MIN_PLIES:
            return [], "short"
        return accepted, ""

    return [], ("player_cap" if capped and not bucket_full else "buckets_full")


# ---------------------------------------------------------------------------
# Per-month state — stream cursor only
# ---------------------------------------------------------------------------

def _state_path(output_pgn: Path) -> Path:
    return output_pgn.with_suffix(".state.json")


def load_state(output_pgn: Path) -> dict:
    sp = _state_path(output_pgn)
    if sp.exists():
        return json.loads(sp.read_text())
    return {"games_read": 0, "games_saved": 0, "stream_complete": False}


def save_state(output_pgn: Path, state: dict) -> None:
    tmp = _state_path(output_pgn).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(_state_path(output_pgn))


# ---------------------------------------------------------------------------
# HTTP + zstd streaming
# ---------------------------------------------------------------------------

def open_lichess_stream(url: str) -> tuple[io.TextIOWrapper, int]:
    """Open an HTTP-streamed zstd decoder for a Lichess monthly .pgn.zst."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    total_bytes = int(resp.headers.get("Content-Length", 0))
    if total_bytes:
        print(f"  Remote compressed size: {total_bytes / 1e9:.2f} GB")

    dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)
    raw  = dctx.stream_reader(resp.raw, read_size=CHUNK_SIZE)
    text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
    return text, total_bytes


# ---------------------------------------------------------------------------
# Collection loop
# ---------------------------------------------------------------------------

def collect_month(
    year: int,
    month: int,
    target: int,
    per_player_cap: int | None,
    max_games: int | None,
    sampling_state: dict,
) -> dict:
    """Stream one month of Lichess rated games and append accepted ones to
    `training/data/raw/<YYYY-MM>.pgn`. Returns a summary dict."""

    month_str  = f"{year:04d}-{month:02d}"
    url        = f"{LICHESS_BASE}/lichess_db_standard_rated_{month_str}.pgn.zst"
    output_pgn = DATA_DIR / f"{month_str}.pgn"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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
            f"[done] {month_str} stream was already drained "
            f"({state['games_saved']:,} games saved). "
            f"Delete the .state.json to reprocess."
        )
        return {"read": state["games_read"], "saved": state["games_saved"], "skips": {}}

    games_read_prev = state.get("games_read", 0)
    if games_read_prev:
        print(
            f"[resume] {month_str}: fast-forwarding past {games_read_prev:,} "
            f"already-processed stream games …"
        )

    print(f"\n{'=' * 64}")
    print(f"Collecting {month_str}  →  {output_pgn.name}")
    print(f"Source:    {url}")
    print(f"Target:    {target:,} per color per bucket   "
          f"(per-player-cap = {per_player_cap})")
    print(f"{'=' * 64}")

    games_read  = 0
    games_saved = state.get("games_saved", 0)   # cumulative for this month
    skip_counts: dict[str, int] = defaultdict(int)
    t_start = time.monotonic()

    out_file = output_pgn.open("a", encoding="utf-8")

    def _flush_state(complete: bool) -> None:
        out_file.flush()
        save_state(output_pgn, {
            "games_read":      games_read_prev + games_read,
            "games_saved":     games_saved,
            "stream_complete": complete,
        })
        save_sampling_state(sampling_state)

    try:
        text_stream, _ = open_lichess_stream(url)

        while True:
            try:
                game = chess.pgn.read_game(text_stream)
            except Exception as exc:
                print(
                    f"[warn] PGN parse error near game ~{games_read_prev + games_read}: {exc}",
                    file=sys.stderr,
                )
                continue

            if game is None:
                break

            games_read += 1
            total_read = games_read_prev + games_read

            # Fast-forward past games already written in a previous run.
            if total_read <= games_read_prev:
                if games_read % 50_000 == 0:
                    pct = 100 * games_read / games_read_prev
                    print(f"  [ff] {games_read:,} / {games_read_prev:,} ({pct:.1f}%)")
                continue

            # Bail out fast: don't waste cycles once everything is full.
            if all_buckets_full(sampling_state, target):
                print("\n[done] All buckets at target — closing stream.")
                _flush_state(complete=False)
                break

            accepted, reason = evaluate_game(
                game, sampling_state, target, per_player_cap,
            )

            if not accepted:
                skip_counts[reason] += 1
                if games_read % CHECKPOINT_INTERVAL == 0:
                    _flush_state(complete=False)
                continue

            # Mutate sampling state for accepted colors.
            for color in accepted:
                elo_str  = game.headers[f"{color.capitalize()}Elo"].rstrip("?")
                username = game.headers[color.capitalize()]
                bucket   = _bucket_for(int(elo_str))
                if bucket is not None:
                    sampling_state["bucket_counts"][_bucket_key(bucket)][color] += 1
                if per_player_cap is not None and username:
                    sampling_state["player_counts"][username] = (
                        sampling_state["player_counts"].get(username, 0) + 1
                    )

            game.headers["Sample"] = ",".join(accepted)
            print(game, file=out_file, end="\n\n")
            games_saved += 1

            # Periodic bucket-table progress log
            if games_read % LOG_INTERVAL == 0:
                elapsed = time.monotonic() - t_start
                rate    = games_read / max(elapsed, 0.001)
                skip_summary = " ".join(f"{k}={v}" for k, v in skip_counts.items())
                print(
                    f"\n  read={total_read:>9,} | saved={games_saved:>7,} | "
                    f"{rate:,.0f} games/s | skips[{skip_summary}]"
                )
                print(format_bucket_table(sampling_state, target))

            if games_read % CHECKPOINT_INTERVAL == 0:
                _flush_state(complete=False)

            if max_games is not None and games_saved >= max_games:
                print(f"[limit] Reached --max-games={max_games}, stopping {month_str}.")
                _flush_state(complete=False)
                break

    except KeyboardInterrupt:
        print(
            f"\n[interrupt] Stopped at stream game "
            f"{games_read_prev + games_read:,}. Saving state …"
        )
        _flush_state(complete=False)
        out_file.close()
        raise

    # Mark stream complete only if we naturally hit EOF (game is None).
    _flush_state(complete=(max_games is None and game is None))
    out_file.close()

    elapsed = time.monotonic() - t_start
    size_mb = output_pgn.stat().st_size / 1e6

    print(f"\n[done] {month_str} in {elapsed:.0f}s")
    print(f"  Stream games read : {games_read_prev + games_read:>10,}")
    print(f"  Saved (cumulative): {games_saved:>10,}  ({size_mb:.1f} MB)")
    for reason, count in sorted(skip_counts.items()):
        print(f"  Skip {reason:<16}: {count:>10,}")
    print()
    print(format_bucket_table(sampling_state, target))

    return {
        "read":  games_read_prev + games_read,
        "saved": games_saved,
        "skips": dict(skip_counts),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_months(spec: str) -> list[tuple[int, int]]:
    """'2024-01'  →  [(2024,1)];  '2023-11:2024-02'  →  [(2023,11)..(2024,2)]."""
    if ":" in spec:
        lo_str, hi_str = spec.split(":", 1)
        lo = datetime.strptime(lo_str.strip(), "%Y-%m")
        hi = datetime.strptime(hi_str.strip(), "%Y-%m")
        result: list[tuple[int, int]] = []
        cur = lo
        while cur <= hi:
            result.append((cur.year, cur.month))
            cur = cur.replace(
                month=cur.month % 12 + 1,
                year=cur.year + (cur.month // 12),
            )
        return result
    d = datetime.strptime(spec.strip(), "%Y-%m")
    return [(d.year, d.month)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream Lichess PGNs into an Elo-stratified training set.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: balanced 12-bucket sample, 2000 per color per bucket
  python collect_data.py --months 2024-01:2024-06

  # Cap each user at 10 games (recommended for serious training)
  python collect_data.py --months 2024-01:2024-06 --per-player-cap 10

  # Larger target for a production-grade dataset
  python collect_data.py --months 2024-01:2024-12 --target 5000 --per-player-cap 10

  # Quick smoke test
  python collect_data.py --months 2024-01 --target 50 --max-games 5000

  # Start over: wipe global counts (does NOT touch collected PGNs)
  python collect_data.py --reset

Output:
  training/data/raw/<YYYY-MM>.pgn          accepted games, with [Sample] header
  training/data/raw/<YYYY-MM>.state.json   per-month stream cursor
  training/data/raw/_sampling_state.json   global bucket + player counts

Resuming:
  Re-run the same command — bucket counts and per-month cursors are persisted.
  Add more months freely; previously-filled buckets are skipped automatically.
        """,
    )
    parser.add_argument("--months", metavar="SPEC",
                        help="Month or range: YYYY-MM or YYYY-MM:YYYY-MM")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_PER_BUCKET,
                        metavar="N",
                        help=f"Samples per color per bucket (default: {DEFAULT_TARGET_PER_BUCKET})")
    parser.add_argument("--per-player-cap", type=int, default=DEFAULT_PER_PLAYER_CAP,
                        metavar="N",
                        help="Maximum games per username across all months (default: unlimited)")
    parser.add_argument("--max-games", type=int, default=None, metavar="N",
                        help="Per-month safety cap on saved games (useful for smoke tests)")
    parser.add_argument("--reset", action="store_true",
                        help="Delete the global sampling state and exit")
    args = parser.parse_args()

    if args.reset:
        if GLOBAL_STATE_PATH.exists():
            GLOBAL_STATE_PATH.unlink()
            print(f"[reset] Removed {GLOBAL_STATE_PATH}")
        else:
            print(f"[reset] No global state file at {GLOBAL_STATE_PATH} — nothing to do")
        return

    if not args.months:
        parser.error("--months is required (unless --reset is used)")

    months = _parse_months(args.months)
    print(f"Months to process: {[f'{y}-{m:02d}' for y, m in months]}")
    print(f"Target / bucket / color: {args.target:,}")
    print(f"Per-player cap:          {args.per_player_cap}")

    sampling_state = load_sampling_state()
    print("\nStarting bucket fill:")
    print(format_bucket_table(sampling_state, args.target))

    grand_read  = 0
    grand_saved = 0
    for year, month in months:
        if all_buckets_full(sampling_state, args.target):
            print(f"\n[skip] All buckets already at target — skipping {year}-{month:02d}")
            continue
        s = collect_month(
            year, month,
            target=args.target,
            per_player_cap=args.per_player_cap,
            max_games=args.max_games,
            sampling_state=sampling_state,
        )
        grand_read  += s["read"]
        grand_saved += s["saved"]

    print(f"\n{'=' * 64}")
    print("FINAL BUCKET FILL")
    print(format_bucket_table(sampling_state, args.target))
    print(f"\nGrand totals: read={grand_read:,}  saved={grand_saved:,}")


if __name__ == "__main__":
    main()
