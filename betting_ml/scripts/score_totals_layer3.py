"""
score_totals_layer3.py — Epic 10, Story 10.3

Scoring engine for the Layer 3 totals champion (`totals_v1`): turns the NegBin
(mu, r) predictive distribution + the across-model epistemic sigma into the ten
betting columns for `daily_model_predictions`:

    totals_mu, totals_r, totals_p_over, totals_p_under, totals_p_push,
    totals_p_over_ci_low, totals_p_over_ci_high, bovada_devig_over_prob,
    bovada_line, totals_edge   (+ total_line_source, combined_sigma)

Reused by Story 10.4 (historical backfill) and Story 10.7 (live daily / predict_today
`--model-source layer3`). This module does NOT write to Snowflake or flip the
production totals source — callers own persistence (10.4/10.7).

Usage (engine; callers pass game_pks):
    from betting_ml.scripts.score_totals_layer3 import score_games
    df = score_games([745812, 745813], env="prod")
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import (  # noqa: E402
    compute_across_model_sigma,
    load_layer3_features_for_inference,
    load_total_line_bovada,
)
from betting_ml.models.totals_negbin_model import TotalsNegBinModel  # noqa: E402,F401 — needed to unpickle
from betting_ml.utils.totals_probability import (  # noqa: E402
    compute_over_prob_ci,
    compute_over_under_probs,
    compute_totals_edge,
    devig_over_prob,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_REGISTRY_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
_LOCAL_ARTIFACT = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "totals_v1.pkl"

_OUTPUT_COLUMNS = [
    "game_pk", "totals_mu", "totals_r", "combined_sigma",
    "totals_p_over", "totals_p_under", "totals_p_push",
    "totals_p_over_ci_low", "totals_p_over_ci_high",
    "bovada_devig_over_prob", "bovada_line", "total_line_source", "totals_edge",
]


def load_champion(model=None):
    """Load the `totals_v1` champion (registry S3 path, else the local artifact)."""
    if model is not None:
        return model
    entry = (yaml.safe_load(_REGISTRY_PATH.read_text()) or {}).get("layer3_totals", {})
    path = entry.get("artifact_path")
    if path and str(path).startswith("s3://"):
        from betting_ml.utils.artifact_store import load_artifact
        log.info("Loading champion from %s", path)
        return load_artifact(path)
    if _LOCAL_ARTIFACT.exists():
        log.info("Loading champion from local %s", _LOCAL_ARTIFACT)
        return joblib.load(_LOCAL_ARTIFACT)
    raise FileNotFoundError("No totals_v1 champion found (registry artifact_path null and no local pkl). Run train_totals.py --promote.")


def score_games(game_pks: list[int], env: str = "prod", model=None) -> pd.DataFrame:
    """Score the Layer 3 totals model for `game_pks` → the betting-column DataFrame.

    Games with no Bovada/consensus line get `totals_mu`/`totals_r` but null
    probability/edge columns (P(over) is defined only relative to a line). Games
    with a line but no over/under prices (consensus fallback) get probabilities +
    CI but null de-vig/edge.
    """
    model = load_champion(model)
    feats = load_layer3_features_for_inference(game_pks, env=env)
    mu, r = model.predict_mu_r(feats)
    sigma = compute_across_model_sigma(feats).to_numpy()
    lines = load_total_line_bovada(game_pks, env=env)

    base = pd.DataFrame({
        "game_pk": feats["game_pk"].to_numpy(),
        "totals_mu": mu, "totals_r": r, "combined_sigma": sigma,
    }).merge(lines, on="game_pk", how="left")

    recs = []
    for row in base.itertuples(index=False):
        line = getattr(row, "total_line_bovada", None)
        rec = {
            "game_pk": int(row.game_pk),
            "totals_mu": round(float(row.totals_mu), 4),
            "totals_r": round(float(row.totals_r), 4),
            "combined_sigma": round(float(row.combined_sigma), 4),
            "bovada_line": (None if pd.isna(line) else float(line)),
            "total_line_source": getattr(row, "total_line_source", None),
            "totals_p_over": None, "totals_p_under": None, "totals_p_push": None,
            "totals_p_over_ci_low": None, "totals_p_over_ci_high": None,
            "bovada_devig_over_prob": None, "totals_edge": None,
        }
        if not pd.isna(line):
            po, pu, pp = compute_over_under_probs(row.totals_mu, row.totals_r, line)
            lo, hi = compute_over_prob_ci(row.totals_mu, row.combined_sigma, row.totals_r, line)
            rec.update(totals_p_over=round(po, 4), totals_p_under=round(pu, 4),
                       totals_p_push=round(pp, 4),
                       totals_p_over_ci_low=round(lo, 4), totals_p_over_ci_high=round(hi, 4))
            op, up = getattr(row, "over_price", None), getattr(row, "under_price", None)
            if not pd.isna(op) and not pd.isna(up):
                devig = devig_over_prob(op, up)
                rec["bovada_devig_over_prob"] = round(devig, 4)
                rec["totals_edge"] = round(compute_totals_edge(po, devig), 4)
        recs.append(rec)

    out = pd.DataFrame(recs)[_OUTPUT_COLUMNS]
    n_line = int(out["bovada_line"].notna().sum())
    n_edge = int(out["totals_edge"].notna().sum())
    log.info("Scored %d games | %d with a line | %d with de-vig edge", len(out), n_line, n_edge)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Score the Layer 3 totals champion (Epic 10.3)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--game-pks", required=True, help="Comma-separated game_pks to score")
    p.add_argument("--out", default=None, help="Optional parquet output path")
    args = p.parse_args()
    pks = [int(x) for x in args.game_pks.split(",") if x.strip()]
    df = score_games(pks, env=args.env)
    if args.out:
        df.to_parquet(args.out, index=False)
        log.info("Wrote %s", args.out)
    else:
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
