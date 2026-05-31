"""
train.py — Train and compare Elo regression models; save the winner to
            backend/ml/elo_model.joblib for the FastAPI inference layer.

Modelling decisions
-------------------
Models compared
    * Ridge regression — linear baseline. Cheap to fit, easy to interpret;
      tells us how much *non-linear* gain the tree models actually buy. If
      Ridge is within ~10 Elo MAE of the trees, the extra complexity is not
      worth it.
    * RandomForestRegressor — bagged decision trees. Robust to feature scale,
      copes well with interactions between blunder_rate / avg_wp_loss / etc.
      and tends not to overfit too quickly. Acts as a strong non-linear
      baseline.
    * XGBoostRegressor — gradient-boosted trees. Usually the best on small
      structured tabular data like ours (~13 features, tens of thousands of
      rows). Sequentially corrects residuals where the random forest is
      uncertain.

Why no LightGBM, neural nets, or stacking
    With ≤15 features and ~40k rows, gradient boosting is on the right side
    of the bias/variance trade-off. LightGBM would give nearly identical
    results to XGBoost; neural nets would be slower, harder to interpret, and
    unlikely to beat a well-tuned tree on this scale; stacking adds an extra
    layer of complexity without much win.

Hyperparameter choices
    Defaults are picked to be robust, not optimal. The script reports CV-free
    test metrics so you can spot which model deserves a tuning pass first.
    Ridge alpha=1.0 is standard. RandomForest max_depth=20 and
    min_samples_leaf=5 cap variance on a 40k-row set. XGBoost lr=0.05 with
    600 trees and modest column/row subsampling keeps overfit in check
    without early stopping (kept off for a clean, reproducible single fit).

Selection criterion
    MAE (mean absolute error in Elo points) is the primary metric — it's the
    interpretable number ("our average prediction is ±X Elo off") and is
    robust to outliers, which matters because a single-game Elo estimate has
    irreducible noise. RMSE, R², and within-100 / within-200 accuracy are
    reported for context.

Validation strategy
    We split the loaded features.csv into train / test using the SAME
    deterministic player-based hash as split_dataset.py. No player appears
    on both sides, so test MAE is an honest generalisation estimate. We do
    NOT do additional CV inside train — three models compared once on a
    fixed held-out set is enough to pick a winner; a deeper tuning pass
    would warrant nested CV.

Artifact format
    The saved .joblib bundles {model, feature_cols, depth, metrics, n_train,
    n_test, trained_at, model_name}. The inference code in ml_service.py
    must read feature_cols to align the input vector and depth to refuse
    serving predictions whose features were extracted at a different depth.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Import the same player-assignment hash used by split_dataset.py so the
# train/test partition here is identical to what split_dataset.py produces.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from split_dataset import assign_player  # noqa: E402

PROJECT_ROOT = SCRIPT_DIR.parent
FEATURES_CSV = SCRIPT_DIR / "data" / "features.csv"
MODEL_OUT    = PROJECT_ROOT / "backend" / "ml" / "elo_model.joblib"

# Feature vector layout. Order matters: inference will look up these names in
# this exact order when building the input array.
FEATURE_COLS: list[str] = [
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
]
TARGET_COL = "elo"

DEFAULT_TEST_FRACTION = 0.20
DEFAULT_SEED          = "elo-split-v1"
RANDOM_STATE          = 42


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

def make_models() -> dict[str, object]:
    """Return a fresh estimator for each candidate model."""
    return {
        "Ridge": Pipeline([
            # Ridge is scale-sensitive — n_moves_analyzed (10–80) would
            # otherwise dominate avg_wp_loss (0.0–0.3) in the L2 penalty.
            ("scaler", StandardScaler()),
            ("ridge",  Ridge(alpha=1.0, random_state=RANDOM_STATE)),
        ]),
        "RandomForest": RandomForestRegressor(
            n_estimators=300,          # diminishing returns past ~300 on this size
            max_depth=20,              # caps tree variance on 40k samples
            min_samples_leaf=5,        # smooths predictions; reduces overfit
            n_jobs=-1,                 # all cores
            random_state=RANDOM_STATE,
        ),
        "XGBoost": xgb.XGBRegressor(
            n_estimators=600,
            max_depth=6,
            learning_rate=0.05,        # low LR + many trees → smoother fit
            subsample=0.85,            # row subsampling — implicit regularisation
            colsample_bytree=0.85,     # feature subsampling per tree
            reg_alpha=0.1,             # L1: pushes weak features toward zero
            reg_lambda=1.0,            # L2: shrinks all weights
            objective="reg:squarederror",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    err = np.abs(y_pred - y_true)
    return {
        "mae":        float(mean_absolute_error(y_true, y_pred)),
        "rmse":       float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2":         float(r2_score(y_true, y_pred)),
        "within_100": float(np.mean(err <= 100)),
        "within_200": float(np.mean(err <= 200)),
    }


# ---------------------------------------------------------------------------
# Player split (mirrors split_dataset.py — no leakage between train and test)
# ---------------------------------------------------------------------------

def player_split(
    df: pd.DataFrame,
    test_fraction: float,
    seed: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministic player-level partition. Same seed → same partition."""
    sides = df["username"].fillna("").map(
        lambda u: assign_player(u, seed, test_fraction)
    )
    train_df = df[sides == "train"].reset_index(drop=True)
    test_df  = df[sides == "test"].reset_index(drop=True)
    return train_df, test_df


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_comparison_table(results: dict[str, dict], winner: str) -> None:
    print()
    print(f"  {'Model':<14}  {'MAE':>7}  {'RMSE':>7}  {'R²':>6}  "
          f"{'<100':>7}  {'<200':>7}  {'Fit (s)':>8}")
    print(f"  {'-' * 14}  {'-' * 7}  {'-' * 7}  {'-' * 6}  "
          f"{'-' * 7}  {'-' * 7}  {'-' * 8}")
    for name, r in results.items():
        m   = r["metrics"]
        tag = "  ← BEST" if name == winner else ""
        print(
            f"  {name:<14}  "
            f"{m['mae']:>7.1f}  "
            f"{m['rmse']:>7.1f}  "
            f"{m['r2']:>6.3f}  "
            f"{m['within_100']:>6.1%}  "
            f"{m['within_200']:>6.1%}  "
            f"{m['fit_seconds']:>8.2f}"
            f"{tag}"
        )


def _print_feature_importance(name: str, model) -> None:
    """Per-model importance — coefficients for Ridge, gain for tree models."""
    if isinstance(model, Pipeline):
        # Ridge inside a StandardScaler → coefs are on standardised features,
        # so their magnitudes are directly comparable to each other.
        coefs = model.named_steps["ridge"].coef_
        importances = np.abs(coefs)
    elif hasattr(model, "feature_importances_"):
        importances = np.asarray(model.feature_importances_)
    else:
        print(f"  [{name}] no native feature_importances available")
        return

    total = importances.sum()
    importances = importances / total if total > 0 else importances

    print(f"\n  {name}")
    pairs = sorted(zip(FEATURE_COLS, importances), key=lambda p: p[1], reverse=True)
    for feat, imp in pairs:
        bar = "█" * int(imp * 40)
        print(f"    {feat:<18}  {imp:.3f}  {bar}")


def _print_per_bucket_mae(test_df: pd.DataFrame, preds: np.ndarray, name: str) -> None:
    err = np.abs(preds - test_df[TARGET_COL].to_numpy())
    diag = (
        pd.DataFrame({"bucket": test_df["elo_bucket"].values, "err": err})
        .groupby("bucket", sort=True)
        .agg(n=("err", "size"), mae=("err", "mean"))
    )
    print(f"\n  Per-bucket test MAE — {name}:")
    print(f"    {'Bucket':<14}  {'n':>5}  {'MAE':>7}")
    print(f"    {'-' * 14}  {'-' * 5}  {'-' * 7}")
    for bucket, row in diag.iterrows():
        print(f"    {bucket:<14}  {int(row['n']):>5}  {row['mae']:>7.1f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _validate_columns(df: pd.DataFrame) -> None:
    needed = FEATURE_COLS + [TARGET_COL, "username", "elo_bucket"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(
            f"features CSV is missing required columns: {missing}. "
            "Re-run extract_features.py after pulling the latest schema."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train Elo regression models and save the best.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train with defaults (loads training/data/features.csv)
  python train.py

  # Custom split fraction and seed
  python train.py --test-fraction 0.15 --seed elo-split-v2

  # Use a different input or output path
  python train.py --features data/features.csv --output backend/ml/elo_model.joblib
        """,
    )
    parser.add_argument("--features", type=Path, default=FEATURES_CSV,
                        help=f"Features CSV (default: {FEATURES_CSV})")
    parser.add_argument("--output", type=Path, default=MODEL_OUT,
                        help=f"Path to write the winning model (default: {MODEL_OUT})")
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION,
                        help=f"Fraction of PLAYERS held out for testing (default: {DEFAULT_TEST_FRACTION})")
    parser.add_argument("--seed", default=DEFAULT_SEED,
                        help=f"Player-split hash seed (default: '{DEFAULT_SEED}')")
    args = parser.parse_args()

    if not args.features.exists():
        print(f"[error] features file not found: {args.features}\n"
              f"        Run extract_features.py first.", file=sys.stderr)
        sys.exit(2)

    # ----------------------------------------------------------------- load
    df = pd.read_csv(args.features)
    print(f"\nLoaded {len(df):,} rows from {args.features}")
    _validate_columns(df)

    depths = df["depth"].value_counts()
    if len(depths) > 1:
        print(f"[warn] features were extracted at multiple Stockfish depths: "
              f"{depths.to_dict()}. The saved model will be tagged with the "
              f"majority depth, but mixed-depth training is uncalibrated.")
    training_depth = int(depths.idxmax())
    print(f"Stockfish depth: {training_depth}")

    # -------------------------------------------------------------- split
    train_df, test_df = player_split(df, args.test_fraction, args.seed)
    n_train_players = train_df["username"].nunique()
    n_test_players  = test_df["username"].nunique()
    overlap         = set(train_df["username"]) & set(test_df["username"])
    print(f"Train: {len(train_df):,} rows  ({n_train_players:,} players)")
    print(f"Test:  {len(test_df):,} rows  ({n_test_players:,} players)")
    print(f"Player overlap (must be 0): {len(overlap)}")
    if overlap:
        raise RuntimeError("Train/test player overlap — split is broken")

    X_train = train_df[FEATURE_COLS].to_numpy()
    y_train = train_df[TARGET_COL].to_numpy()
    X_test  = test_df[FEATURE_COLS].to_numpy()
    y_test  = test_df[TARGET_COL].to_numpy()

    # --------------------------------------------------------------- train
    print("\nTraining models …")
    models = make_models()
    results: dict[str, dict] = {}
    for name, model in models.items():
        t0 = time.monotonic()
        model.fit(X_train, y_train)
        fit_s = time.monotonic() - t0
        preds = model.predict(X_test)
        metrics = compute_metrics(y_test, preds)
        metrics["fit_seconds"] = fit_s
        results[name] = {"model": model, "preds": preds, "metrics": metrics}
        print(f"  [{name:<13}] fit in {fit_s:>5.1f}s  ·  test MAE = {metrics['mae']:.1f}")

    # ------------------------------------------------------------ compare
    print(f"\n{'=' * 76}")
    print("Model comparison (lower MAE / RMSE, higher R² / within-X is better)")
    print(f"{'=' * 76}")
    winner = min(results, key=lambda k: results[k]["metrics"]["mae"])
    _print_comparison_table(results, winner)

    # -------------------------------------------------- feature importance
    print(f"\n{'=' * 76}")
    print("Feature importance (per model)")
    print(f"{'=' * 76}")
    for name, r in results.items():
        _print_feature_importance(name, r["model"])

    # ------------------------------------------------ per-bucket breakdown
    print(f"\n{'=' * 76}")
    print(f"Bucket-wise test MAE for the winning model")
    print(f"{'=' * 76}")
    _print_per_bucket_mae(test_df, results[winner]["preds"], winner)

    # -------------------------------------------------------------- save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model":         results[winner]["model"],
        "model_name":    winner,
        "feature_cols":  FEATURE_COLS,
        "depth":         training_depth,
        "metrics":       results[winner]["metrics"],
        "n_train":       len(train_df),
        "n_test":        len(test_df),
        "test_fraction": args.test_fraction,
        "seed":          args.seed,
        "trained_at":    datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(artifact, args.output)
    print(f"\n{'=' * 76}")
    print(f"Saved {winner} → {args.output}")
    print(f"  Test MAE       : {results[winner]['metrics']['mae']:.1f} Elo")
    print(f"  Within ±100    : {results[winner]['metrics']['within_100']:.1%}")
    print(f"  Within ±200    : {results[winner]['metrics']['within_200']:.1%}")
    print(f"  R²             : {results[winner]['metrics']['r2']:.3f}")
    print(f"  Stockfish depth: {training_depth}  (inference MUST match)")


if __name__ == "__main__":
    main()
