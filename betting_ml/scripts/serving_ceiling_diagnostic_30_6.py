"""
serving_ceiling_diagnostic_30_6.py — Story 30.6 GATE CHECK (Branch A vs B).

THE QUESTION. Live home_win on the honest dense surface (prediction_type='post_lineup',
data_source='feature_store') sits at corr ~0.074 / Brier ~0.275 (n≈49) — near coinflip,
nowhere near the 0.42 offline ceiling. Two competing explanations:
  • BRANCH A (serving skew persists): the SAME deployed model, scored on the OFFLINE-DENSE
    (post-game-backfilled) matrix for the SAME games, recovers real skill → the gap is the
    as-served-vs-backfill VALUE difference at lineup-lock → 30.6's AS-OF retrain is the lever.
  • BRANCH B (illusory ceiling): the deployed model scores ~coinflip on the dense matrix TOO →
    the 0.42 was optimistic for this model class → 30.6 is the WRONG lever (it's a skill problem).

THE TEST (apples-to-apples, same model + same games):
  1. Pull the honest-surface settled games: (game_pk, as-served p_home_win_classifier, y_home).
  2. Load the DEPLOYED v5 home_win model + its registry contract.
  3. Re-score it on the OFFLINE-DENSE matrix for those same game_pks (load_features re-reads the
     now-backfilled dense rows; imputer fit on ≤2025, mirroring train≤2025/eval-2026).
  4. Compare Brier/corr/acc/ECE of p_offline_dense vs p_served on the identical games.

VERDICT: p_offline_dense materially better than p_served (e.g. Brier ≤0.22 vs ~0.275, corr ≫) ⇒
BRANCH A (build the forward-capture infra). Both ~coinflip ⇒ BRANCH B (pivot off 30.6).

HAND-OFF: loads ~30k rows via load_features + downloads the S3 model artifact — minutes. Run:
    uv run python betting_ml/scripts/serving_ceiling_diagnostic_30_6.py
    uv run python betting_ml/scripts/serving_ceiling_diagnostic_30_6.py --since 2026-01-01

Output: prints the comparison + verdict; writes
    betting_ml/evaluation/feature_selection/serving_ceiling_30_6.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.artifact_store import load_artifact  # noqa: E402
from betting_ml.utils.data_loader import get_snowflake_connection, load_features  # noqa: E402
from betting_ml.utils.feature_selection import load_retained_features  # noqa: E402
from betting_ml.utils.preprocessing import build_imputation_pipeline  # noqa: E402

_REGISTRY = _PROJECT_ROOT / "betting_ml/models/model_registry.yaml"
_OUT = _PROJECT_ROOT / "betting_ml/evaluation/feature_selection/serving_ceiling_30_6.json"

# The honest live surface (Story 30.3): dense post_lineup serve, feature_store source, no backfills.
_HONEST_SQL = """
SELECT dmp.game_pk,
       dmp.p_home_win_classifier                                              AS p_served,
       CASE WHEN r.home_final_score > r.away_final_score THEN 1 ELSE 0 END    AS y_home
FROM baseball_data.betting_ml.daily_model_predictions dmp
JOIN baseball_data.betting.mart_game_results r USING (game_pk)
WHERE dmp.game_date >= '{since}'
  AND r.home_final_score IS NOT NULL
  AND COALESCE(dmp.is_backfill, FALSE) = FALSE
  AND dmp.prediction_type = 'post_lineup'
  AND dmp.data_source = 'feature_store'
  AND dmp.p_home_win_classifier IS NOT NULL
"""


def _registry_home_win() -> tuple[str, list[str]]:
    import yaml
    reg = yaml.safe_load(_REGISTRY.read_text())
    hw = reg["home_win"]
    raw = json.loads((_PROJECT_ROOT / hw["feature_columns_path"]).read_text())
    cols = raw["feature_cols"] if isinstance(raw, dict) else raw
    return hw["artifact_path"], cols


def _metrics(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    y = np.asarray(y, float)
    n = len(p)
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
    ece = sum((idx == b).mean() * abs(p[idx == b].mean() - y[idx == b].mean())
              for b in range(10) if (idx == b).any())
    return {"n": int(n),
            "brier": round(float(np.mean((p - y) ** 2)), 4),
            "corr": round(float(np.corrcoef(p, y)[0, 1]), 3) if n > 1 and p.std() > 0 else None,
            "acc": round(float(np.mean((p > 0.5) == (y > 0.5))), 3),
            "ece": round(float(ece), 3),
            "nll": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4)}


def _verdict(off: dict, srv: dict) -> tuple[str, str]:
    # Branch A if the dense re-score recovers materially: Brier gap ≥ 0.03 AND a real corr lift.
    brier_gap = srv["brier"] - off["brier"]
    corr_lift = (off["corr"] or 0) - (srv["corr"] or 0)
    if off["brier"] <= 0.235 and brier_gap >= 0.03 and corr_lift >= 0.10:
        return ("A_serving",
                f"Dense re-score recovers skill (Brier {off['brier']} vs served {srv['brier']}, "
                f"corr {off['corr']} vs {srv['corr']}) → serving skew persists at lineup-lock; "
                f"30.6 AS-OF retrain is the lever. Build forward-capture.")
    if abs(brier_gap) < 0.03 and abs(corr_lift) < 0.10:
        return ("B_illusory",
                f"Dense re-score is ALSO ~coinflip (Brier {off['brier']} vs served {srv['brier']}) → "
                f"the 0.42 ceiling was optimistic for this model class; 30.6 is the WRONG lever "
                f"(skill problem, not serving). Pivot.")
    return ("ambiguous",
            f"Partial: Brier gap {brier_gap:+.3f}, corr lift {corr_lift:+.3f}. n may be too small "
            f"(n={off['n']}) — re-run when more post_lineup games settle.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01")
    args = ap.parse_args()

    artifact_path, contract = _registry_home_win()
    print(f"home_win contract: {len(contract)} features; artifact: {artifact_path}")

    print("Querying honest-surface settled games (post_lineup + feature_store)...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_HONEST_SQL.format(since=args.since))
        honest = cur.fetch_pandas_all()
        honest.columns = [c.lower() for c in honest.columns]
    finally:
        conn.close()
    honest = honest.dropna(subset=["p_served", "y_home"]).drop_duplicates("game_pk")
    pks = set(int(x) for x in honest["game_pk"])
    print(f"  honest settled games: n={len(honest)}")
    if len(honest) < 10:
        print("  ⚠ too few games for a verdict; re-run when more settle.")

    print("Loading offline-dense feature surface (load_features)...")
    df_hist = load_features().reset_index(drop=True)
    df_hist["game_pk"] = df_hist["game_pk"].astype(int)
    print(f"  {len(df_hist):,} historical rows; seasons {sorted(df_hist.game_year.unique())}")

    # Faithful predict_today matrix build; imputer fit on ≤2025 (train≤2025 / eval-2026 honest).
    retained = load_retained_features()
    feat_in = [c for c in dict.fromkeys(retained + contract) if c in df_hist.columns]
    fit_mask = df_hist["game_year"] <= 2025
    pipeline = build_imputation_pipeline()
    X_fit_imp = pipeline.fit_transform(df_hist.loc[fit_mask, feat_in]).select_dtypes(include=[np.number])
    X_all_imp = pipeline.transform(df_hist[feat_in]).reindex(columns=X_fit_imp.columns, fill_value=0.0)

    sub_mask = df_hist["game_pk"].isin(pks).values
    X_sub = X_all_imp[sub_mask].reindex(columns=contract, fill_value=0.0).values.astype(np.float32)
    pk_sub = df_hist.loc[sub_mask, "game_pk"].astype(int).values
    print(f"  scoring {len(pk_sub)}/{len(pks)} honest games found on the offline surface")

    print(f"Loading deployed model: {artifact_path}")
    model = load_artifact(artifact_path)
    p_off = model.predict_proba(X_sub)[:, 1]
    off_df = pd.DataFrame({"game_pk": pk_sub, "p_offline": p_off})

    m = honest.merge(off_df, on="game_pk", how="inner")
    y = m["y_home"].to_numpy(float)
    off = _metrics(m["p_offline"].to_numpy(float), y)
    srv = _metrics(m["p_served"].to_numpy(float), y)
    tag, why = _verdict(off, srv)

    print("\n=== SERVING-CEILING DIAGNOSTIC (same model, same games) ===")
    print(f"  matched games: {len(m)}")
    print(f"  OFFLINE-DENSE re-score : {off}")
    print(f"  AS-SERVED (live)       : {srv}")
    print(f"\n  VERDICT → {tag}\n  {why}")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps({
        "story": "30.6_gate_check", "since": args.since, "n_matched": len(m),
        "offline_dense": off, "as_served": srv, "verdict": tag, "rationale": why,
        "contract_len": len(contract), "artifact": artifact_path,
    }, indent=2))
    print(f"\nWrote {_OUT}")


if __name__ == "__main__":
    main()
