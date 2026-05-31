"""
ML Service — loads the trained Elo regression model and produces single-game
performance estimates.

Responsibilities:
  - Open the joblib artifact at application startup.
  - Compute the feature vector for one player from a fully analysed game.
  - Run model.predict and return an integer Elo estimate.

Does NOT:
  - Train or evaluate the model (see training/train.py).
  - Run Stockfish (StockfishService produces the analysed moves).

Depth invariant:
  The artifact stores the Stockfish depth used at training time. Inference
  features MUST be extracted at the same depth or the predicted Elo is
  miscalibrated. main.py's lifespan reads .depth from the loaded model and
  passes it to StockfishService so the constraint holds automatically.
"""

from pathlib import Path

import joblib
import numpy as np

from services.centipawn_utils import compute_effective_acpl
from services.probability_utils import compute_avg_wp_loss

# Path is relative to backend/. main.py constructs the absolute path before
# passing it in, so this module never has to care about the CWD.


def compute_player_features(
    enriched_moves: list[dict],
    color: str,
) -> dict[str, float] | None:
    """
    Build the feature dict for one player from an analysed game.

    Returns None when the player has no non-forced moves — extremely rare
    (a 40-ply game where one side was in check on every move). The same
    function is used by training/extract_features.py, so training and
    inference cannot diverge.
    """
    player_moves = [m for m in enriched_moves if m["color"] == color]
    n_total = len(player_moves)
    if n_total == 0:
        return None

    non_forced = [m for m in player_moves if m["classification"] != "forced"]
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


class MLService:
    """
    Wraps the trained Elo regression model for inference.

    The app must still boot when the model is missing (it might not exist
    yet on a fresh checkout). `is_loaded` lets the router skip predictions
    in that case rather than 500-ing every analyse call.
    """

    def __init__(self, model_path: Path) -> None:
        self._model_path = model_path
        self._artifact: dict | None = None

    def open(self) -> None:
        """Load the joblib artifact. Call once at application startup."""
        if not self._model_path.exists():
            print(f"[ml] no model at {self._model_path} — Elo estimates disabled")
            return

        artifact = joblib.load(self._model_path)
        required = {"model", "feature_cols", "depth"}
        missing  = required - set(artifact)
        if missing:
            print(f"[ml] artifact missing fields {missing} — Elo estimates disabled")
            return

        self._artifact = artifact
        m = artifact.get("metrics", {})
        print(
            f"[ml] loaded {artifact.get('model_name', 'unknown')} "
            f"(depth={artifact['depth']}, "
            f"n_train={artifact.get('n_train', '?')}, "
            f"MAE={m.get('mae', float('nan')):.0f})"
        )

    def close(self) -> None:
        self._artifact = None

    @property
    def is_loaded(self) -> bool:
        return self._artifact is not None

    @property
    def depth(self) -> int | None:
        return self._artifact["depth"] if self._artifact else None

    @property
    def mae(self) -> float | None:
        if not self._artifact:
            return None
        return self._artifact.get("metrics", {}).get("mae")

    def predict_for_player(
        self,
        enriched_moves: list[dict],
        color: str,
    ) -> int | None:
        """End-to-end: enriched moves → feature dict → predicted Elo (integer)."""
        if self._artifact is None:
            return None

        features = compute_player_features(enriched_moves, color)
        if features is None:
            return None

        cols   = self._artifact["feature_cols"]
        vector = np.array([[features[c] for c in cols]], dtype=np.float32)
        pred   = float(self._artifact["model"].predict(vector)[0])
        return int(round(pred))
