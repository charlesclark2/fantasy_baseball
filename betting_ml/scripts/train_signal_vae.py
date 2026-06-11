"""Story 19.6 — Train VAE for holistic joint-signal OOD detection.

Usage (hand to user; runtime ~2-3 min with Snowflake fetch):

    uv run python -m betting_ml.scripts.train_signal_vae
    # or
    uv run python betting_ml/scripts/train_signal_vae.py

Outputs
-------
betting_ml/models/vae_ood/signal_vae.joblib   — fitted SignalVAE artifact
betting_ml/models/vae_ood/training_report.json — backtest results + threshold

The threshold printed at the end should be copy-pasted into
sub_model_registry.yaml > bet_gate > criteria > signal_combination_ood > threshold.

GUARDS:
- Train window: 2022-2025 only.
- May-2026 is the held-out test cohort (no leakage).
- Threshold is set on training-era 95th percentile reconstruction error.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "vae_ood" / "signal_vae.joblib"
_REPORT_PATH   = _PROJECT_ROOT / "betting_ml" / "models" / "vae_ood" / "training_report.json"

sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.models.vae_ood.signal_vae import SIGNAL_MU_COLUMNS, SignalVAE
from betting_ml.scripts.load_layer3_features import load_layer3_features


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _build_signal_matrix(df: pd.DataFrame) -> np.ndarray:
    """Extract the 13 mu columns from the Layer-3 game-level dataframe.

    Missing columns are filled with NaN (SignalVAE.fit imputes with training mean).
    """
    X = np.full((len(df), len(SIGNAL_MU_COLUMNS)), np.nan, dtype=np.float64)
    for i, col in enumerate(SIGNAL_MU_COLUMNS):
        if col in df.columns:
            X[:, i] = pd.to_numeric(df[col], errors="coerce").to_numpy()
        else:
            log.warning("  Column %r not found in dataframe — will be imputed.", col)
    return X


def _per_signal_zscore_flag(
    X_test: np.ndarray,
    train_mean: np.ndarray,
    train_std: np.ndarray,
    z_thresh: float = 1.5,
) -> np.ndarray:
    """True for any game where at least one signal |z| > z_thresh."""
    z = np.abs((X_test - train_mean) / (train_std + 1e-8))
    return np.any(z > z_thresh, axis=1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Story 19.6: Train Signal VAE ===")

    # ------------------------------------------------------------------
    # 1. Load data from Snowflake (2022 onward, completed regular-season games)
    # ------------------------------------------------------------------
    log.info("Loading Layer-3 signal matrix from Snowflake (start=2022-01-01) …")
    df_all = load_layer3_features(start_date="2022-01-01")
    df_all["game_date"] = pd.to_datetime(df_all["game_date"])
    log.info("  Total games loaded: %d  (seasons %s–%s)",
             len(df_all), df_all["game_date"].dt.year.min(), df_all["game_date"].dt.year.max())

    # ------------------------------------------------------------------
    # 2. Split: train 2022-2025, test 2026
    # ------------------------------------------------------------------
    train_mask = df_all["game_date"].dt.year <= 2025
    df_train = df_all[train_mask].copy()
    df_2026  = df_all[~train_mask].copy()

    log.info("  Train (2022–2025): %d games", len(df_train))
    log.info("  Test  (2026):      %d games", len(df_2026))

    if len(df_train) < 100:
        log.error("Training set too small (%d games). Aborting.", len(df_train))
        sys.exit(1)

    X_train = _build_signal_matrix(df_train)
    X_2026  = _build_signal_matrix(df_2026)

    # May-2026 cohort — the held-out OOD event
    may26_mask = (
        (df_2026["game_date"].dt.year == 2026) &
        (df_2026["game_date"].dt.month == 5)
    )
    log.info("  May-2026 cohort (OOD test): %d games", may26_mask.sum())

    # ------------------------------------------------------------------
    # 3. Train VAE
    # ------------------------------------------------------------------
    log.info("Training SignalVAE  (input_dim=%d, hidden=8, latent=3, epochs=300) …",
             len(SIGNAL_MU_COLUMNS))
    vae = SignalVAE(input_dim=len(SIGNAL_MU_COLUMNS), hidden_dim=8, latent_dim=3, beta=0.1, seed=42)
    vae.fit(X_train, n_epochs=300, lr=1e-3, batch_size=64, train_window="2022-2025", verbose=True)

    log.info("  Training threshold (p95 recon error): %.6f", vae.threshold_)

    # ------------------------------------------------------------------
    # 4. Backtest — May-2026 cohort vs. rest of 2026
    # ------------------------------------------------------------------
    if len(df_2026) == 0 or may26_mask.sum() == 0:
        log.warning("No 2026 data available — skipping backtest.")
        auc_vae = float("nan")
        per_signal_recall = float("nan")
    else:
        from sklearn.metrics import roc_auc_score

        # VAE reconstruction errors on 2026 games
        recon_2026, _ = vae.predict_ood(X_2026)

        # Binary label: 1 = May-2026 (OOD event), 0 = other 2026 games
        y_2026 = may26_mask.astype(int).to_numpy()

        if y_2026.sum() == 0 or y_2026.sum() == len(y_2026):
            log.warning("Only one class present in 2026 — AUC undefined.")
            auc_vae = float("nan")
        else:
            auc_vae = float(roc_auc_score(y_2026, recon_2026))

        # Per-signal z>1.5 recall on May-2026 using training distribution
        per_signal_ood = _per_signal_zscore_flag(
            X_2026, vae.train_mean_, vae.train_std_, z_thresh=1.5
        )
        n_may = int(may26_mask.sum())
        n_may_flagged_per_signal = int(per_signal_ood[may26_mask.to_numpy()].sum())
        per_signal_recall = n_may_flagged_per_signal / n_may if n_may > 0 else float("nan")

        # VAE recall on May-2026 at training threshold (for reference)
        n_may_flagged_vae = int((recon_2026[may26_mask.to_numpy()] > vae.threshold_).sum())
        vae_recall_may26 = n_may_flagged_vae / n_may if n_may > 0 else float("nan")

        log.info("--- Backtest Results ---")
        log.info("  May-2026 games:                    %d", n_may)
        log.info("  VAE AUC (May-2026 vs rest of 2026): %.4f", auc_vae)
        log.info("  Per-signal z>1.5 recall on May-26:  %.4f  (%d/%d flagged)",
                 per_signal_recall, n_may_flagged_per_signal, n_may)
        log.info("  VAE recall at p95 threshold:        %.4f  (%d/%d flagged)",
                 vae_recall_may26, n_may_flagged_vae, n_may)

        ac_met = (
            not np.isnan(auc_vae)
            and not np.isnan(per_signal_recall)
            and auc_vae > per_signal_recall
        )
        log.info("  AC1 (VAE AUC > per-signal recall):  %s", "PASS" if ac_met else "FAIL / REVIEW")

        # Also show mean recon error by month for context
        df_2026_copy = df_2026.copy()
        df_2026_copy["recon_error"] = recon_2026
        df_2026_copy["month"] = df_2026_copy["game_date"].dt.month
        monthly = df_2026_copy.groupby("month")["recon_error"].agg(["mean", "median", "max"])
        log.info("  2026 monthly recon error summary:\n%s", monthly.to_string())

    # ------------------------------------------------------------------
    # 5. Save artifact
    # ------------------------------------------------------------------
    vae.save(_ARTIFACT_PATH)

    report = {
        "story": "19.6",
        "trained_at": date.today().isoformat(),
        "train_window": "2022-2025",
        "train_n_games": int(len(df_train)),
        "signal_columns": SIGNAL_MU_COLUMNS,
        "architecture": {
            "input_dim": vae.input_dim,
            "hidden_dim": vae.hidden_dim,
            "latent_dim": vae.latent_dim,
            "beta": vae.beta,
            "n_epochs": 300,
            "lr": 1e-3,
        },
        "threshold_p95": float(vae.threshold_),
        "backtest": {
            "test_cohort": "May-2026",
            "vae_auc_may26_vs_rest_2026": float(auc_vae) if not np.isnan(auc_vae) else None,
            "per_signal_z15_recall_may26": float(per_signal_recall) if not np.isnan(per_signal_recall) else None,
            "ac1_pass": bool(not np.isnan(auc_vae) and not np.isnan(per_signal_recall) and auc_vae > per_signal_recall),
        },
        "artifact_path": str(_ARTIFACT_PATH),
    }
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2))
    log.info("Report saved → %s", _REPORT_PATH)

    log.info("")
    log.info("=== NEXT STEP ===")
    log.info("Copy the threshold below into sub_model_registry.yaml:")
    log.info("  bet_gate.criteria.signal_combination_ood.threshold: %.6f", vae.threshold_)
    log.info("Then set enabled: true to activate the gate.")


if __name__ == "__main__":
    main()
