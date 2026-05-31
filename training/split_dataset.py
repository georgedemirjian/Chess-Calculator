"""
split_dataset.py — Partition features.csv into train.csv and test.csv with
PLAYER-LEVEL isolation (no overlapping usernames between the two sets).

Why a player-based split?
    Two rows from the same player — even from different games — share latent
    factors: opening repertoire, time-control habits, decision-making style.
    A model trained on row A and evaluated on row B from the same player can
    exploit those shared factors and report an MAE that under-states real
    generalisation error. The fix is to assign each player to exactly one of
    {train, test}; no row-level shuffling.

How the split is decided
    Each username is hashed with a seed. The first 8 bytes of the SHA-256
    digest become a float in [0, 1). If that float is below --test-fraction
    the player goes to test, otherwise train. This is deterministic given a
    seed, so:
      • re-running the split produces the same partition
      • adding new rows for an existing player keeps them on the same side
      • adding a brand-new player gets a fresh hash-based assignment
"""

import argparse
import csv
import hashlib
from collections import Counter
from pathlib import Path

SCRIPT_DIR    = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "data" / "features.csv"
DEFAULT_TRAIN = SCRIPT_DIR / "data" / "train.csv"
DEFAULT_TEST  = SCRIPT_DIR / "data" / "test.csv"

DEFAULT_TEST_FRACTION = 0.20
DEFAULT_SEED          = "elo-split-v1"


def assign_player(username: str, seed: str, test_fraction: float) -> str:
    """Deterministic player → 'train' | 'test' assignment via hash."""
    h   = hashlib.sha256(f"{seed}:{username}".encode("utf-8")).digest()
    val = int.from_bytes(h[:8], "big") / 2 ** 64   # uniform in [0, 1)
    return "test" if val < test_fraction else "train"


def split(
    input_csv:     Path,
    train_csv:     Path,
    test_csv:      Path,
    test_fraction: float,
    seed:          str,
) -> None:
    if not input_csv.exists():
        raise FileNotFoundError(f"features file not found: {input_csv}")

    # Single streaming pass — never load the full CSV into memory.
    train_csv.parent.mkdir(parents=True, exist_ok=True)
    test_csv.parent.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        if not reader.fieldnames:
            raise ValueError(f"{input_csv} has no header row")
        if "username" not in reader.fieldnames:
            raise ValueError(
                f"{input_csv} has no 'username' column. "
                "Was it produced by the post-refactor extract_features.py?"
            )
        fieldnames = reader.fieldnames

        # Cache player assignments so we hash each username at most once.
        assignment: dict[str, str] = {}
        row_counts:    Counter[str] = Counter()
        player_counts: dict[str, set[str]] = {"train": set(), "test": set()}
        bucket_counts: dict[str, Counter[str]] = {"train": Counter(), "test": Counter()}

        with (
            train_csv.open("w", newline="", encoding="utf-8") as f_train,
            test_csv.open("w",  newline="", encoding="utf-8") as f_test,
        ):
            w_train = csv.DictWriter(f_train, fieldnames=fieldnames)
            w_test  = csv.DictWriter(f_test,  fieldnames=fieldnames)
            w_train.writeheader()
            w_test.writeheader()

            for row in reader:
                username = row.get("username") or ""
                if username not in assignment:
                    assignment[username] = assign_player(username, seed, test_fraction)
                side = assignment[username]

                (w_test if side == "test" else w_train).writerow(row)
                row_counts[side]               += 1
                player_counts[side].add(username)
                bucket_counts[side][row.get("elo_bucket", "?")] += 1

    overlap = player_counts["train"] & player_counts["test"]

    print(f"\n{'=' * 56}")
    print(f"  Input : {input_csv}")
    print(f"  Train : {train_csv}")
    print(f"  Test  : {test_csv}")
    print(f"  Test fraction (target): {test_fraction:.2%}")
    print(f"  Seed : '{seed}'")
    print(f"{'=' * 56}")
    total_rows = row_counts["train"] + row_counts["test"]
    total_pl   = len(player_counts["train"]) + len(player_counts["test"])
    print(
        f"  Train : {row_counts['train']:>7,} rows "
        f"({len(player_counts['train']):>6,} players)"
    )
    print(
        f"  Test  : {row_counts['test']:>7,} rows "
        f"({len(player_counts['test']):>6,} players)"
    )
    if total_rows:
        actual = row_counts["test"] / total_rows
        print(f"  Actual test fraction (rows): {actual:.2%}")
    if total_pl:
        actual_pl = len(player_counts["test"]) / total_pl
        print(f"  Actual test fraction (players): {actual_pl:.2%}")
    print(f"  Player overlap (MUST be 0): {len(overlap)}")
    if overlap:
        raise RuntimeError("Train/test player overlap detected — split is broken")

    print("\n  Per-bucket train / test row counts:")
    all_buckets = sorted(set(bucket_counts["train"]) | set(bucket_counts["test"]))
    for b in all_buckets:
        tr = bucket_counts["train"][b]
        te = bucket_counts["test"][b]
        print(f"    {b:<14}  train={tr:>6,}  test={te:>6,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Player-based train/test split for the Elo features CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default 80/20 split using training/data/features.csv
  python split_dataset.py

  # 90/10 split with a custom seed (different random partition)
  python split_dataset.py --test-fraction 0.10 --seed elo-split-v2

  # Custom input/output paths
  python split_dataset.py --input data/features.csv \\
                          --train data/train.csv --test data/test.csv
        """,
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help=f"Features CSV (default: {DEFAULT_INPUT})")
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN,
                        help=f"Output train CSV (default: {DEFAULT_TRAIN})")
    parser.add_argument("--test",  type=Path, default=DEFAULT_TEST,
                        help=f"Output test CSV (default: {DEFAULT_TEST})")
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION,
                        help=f"Fraction of players → test (default: {DEFAULT_TEST_FRACTION})")
    parser.add_argument("--seed", default=DEFAULT_SEED,
                        help=f"Hash seed for reproducible splits (default: '{DEFAULT_SEED}')")
    args = parser.parse_args()

    if not 0 < args.test_fraction < 1:
        parser.error("--test-fraction must be in (0, 1)")

    split(args.input, args.train, args.test, args.test_fraction, args.seed)


if __name__ == "__main__":
    main()
