"""
pinnacle_sharp_money_ablation_12_10.py — Story 12.10′

Does the Pinnacle sharp-money signal add CLV-predictive lift beyond the market-blind
morning model edge? Runs BOTH framings (operator chose "C — validate completely"):

  OPEN  (actionable / non-leaky): sharp features known AT THE OPEN — Pinnacle OPEN devig
        + the Bovada-open−Pinnacle-open gap (+ AN handle-ticket). If our book opens off the
        sharp book, Bovada drifts toward Pinnacle → predictable CLV at decision time.
  CLOSE (card-literal / leaky):   Pinnacle CLOSE devig, steam (close−open), Bovada-close−
        Pinnacle-close gap. These include the CLOSE — unknown when you bet at open — and
        share components with the label, so any "lift" is partly mechanical co-movement.

The gap (lift_close − lift_open) quantifies how much apparent lift is leakage vs real.

Population = the proven 12.4 pre-test set: earliest LIVE morning prediction per 2026 game
(is_backfill=false) ⋈ mart_odds_line_movement (Bovada, snapshot_count>1). Label = direction
of Bovada's open→close de-vig move (clv_up = h2h_line_movement > 0; flat games dropped).
Predicting Bovada's MOVE direction from features — the edge is NOT baked into the label, so
the lift is a clean incremental test. Sharp features are a DIFFERENT book → legitimate.

Method: repeated stratified k-fold CV AUC on the SAME rows for BASE / BASE+OPEN / BASE+CLOSE.
Gate (Betfair-parity): retain the sharp group only if the ACTIONABLE (OPEN) framing adds
≥ +0.01 mean CV AUC. The CLOSE framing is reported for leakage diagnosis, NOT for the gate.

Output: quant_sports_intel_models/baseball/ablation_results/pinnacle_sharp_money_12_10.md
Run (hand-off — Snowflake, ~1 min):
    uv run python betting_ml/scripts/pinnacle_sharp_money_ablation_12_10.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

_OUT = (PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
        / "ablation_results" / "pinnacle_sharp_money_12_10.md")

GATE = 0.01
N_SPLITS, N_REPEATS, SEED = 5, 20, 1210

_SQL = """
with morn as (
  select game_pk,
         coalesce(calibrated_win_prob, consensus_win_prob, h2h_posterior_prob) as model_home_prob
  from baseball_data.betting_ml.daily_model_predictions
  where prediction_type='morning' and coalesce(is_backfill,false)=false
    and date_part('year', game_date)=2026
  qualify row_number() over (partition by game_pk order by inserted_at asc)=1
),
gs as (select game_pk, game_date as game_dt from baseball_data.betting.stg_statsapi_games),
psnap as (
  select h.game_pk, h.snapshot_ts,
         h.home_win_prob/nullif(h.home_win_prob+h.away_win_prob,0) as pin_devig,
         row_number() over (partition by h.game_pk order by h.snapshot_ts asc)  as rn_open,
         row_number() over (partition by h.game_pk order by h.snapshot_ts desc) as rn_close,
         count(*) over (partition by h.game_pk)                                 as n_snaps
  from baseball_data.oddsapi.odds_snapshots_historical h
  join gs on gs.game_pk = h.game_pk
  where h.bookmaker='pinnacle' and h.snapshot_ts < gs.game_dt
    and h.home_win_prob is not null and h.away_win_prob is not null
),
pin as (
  select game_pk, max(n_snaps) as snaps,
         max(case when rn_open=1  then pin_devig end) as pin_open_devig,
         max(case when rn_close=1 then pin_devig end) as pin_close_devig
  from psnap group by game_pk
),
pb as (
  select game_pk, home_ml_money_pct - home_ml_ticket_pct as an_handle_ticket_div
  from baseball_data.betting_features.feature_pregame_public_betting_features
)
select mv.game_pk, mv.data_source,
       morn.model_home_prob,
       mv.open_home_win_prob, mv.pregame_home_win_prob, mv.h2h_line_movement,
       pin.snaps as pin_snaps, pin.pin_open_devig, pin.pin_close_devig,
       pb.an_handle_ticket_div
from baseball_data.betting.mart_odds_line_movement mv
join morn on morn.game_pk = mv.game_pk
left join pin on pin.game_pk = mv.game_pk
left join pb  on pb.game_pk  = mv.game_pk
where mv.snapshot_count > 1
"""

BASE = ["morning_edge"]
OPEN = ["pin_open_devig", "bovada_open_vs_pin_open", "an_handle_ticket_div"]
CLOSE = ["pin_close_devig", "pin_steam", "bovada_close_vs_pin_close", "an_handle_ticket_div"]


def _load() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SQL)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    df["morning_edge"] = df["model_home_prob"] - df["open_home_win_prob"]
    df["bovada_open_vs_pin_open"] = df["open_home_win_prob"] - df["pin_open_devig"]
    df["bovada_close_vs_pin_close"] = df["pregame_home_win_prob"] - df["pin_close_devig"]
    df["pin_steam"] = df["pin_close_devig"] - df["pin_open_devig"]
    df["an_handle_ticket_div"] = df["an_handle_ticket_div"].fillna(0.0)  # missing AN = neutral
    df["clv_up"] = (df["h2h_line_movement"] > 0).astype(int)
    return df


def _cv_auc(X: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    cv = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=SEED)
    s = cross_val_score(pipe, X, y, cv=cv, scoring="roc_auc")
    return float(s.mean()), float(s.std())


def _uni_auc(x: np.ndarray, y: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    if np.unique(x).size < 2:
        return float("nan")
    a = roc_auc_score(y, x)
    return float(max(a, 1 - a))


def main() -> None:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    raw = _load()

    # Same rows for all three models: Pinnacle present with steam (≥2 snaps), line moved.
    # dict.fromkeys dedupes (an_handle_ticket_div is in both OPEN and CLOSE) while keeping order.
    cols = list(dict.fromkeys(["clv_up"] + BASE + OPEN + CLOSE))
    df = raw[(raw["pin_snaps"] >= 2) & (raw["h2h_line_movement"] != 0)].copy()
    df = df[cols].replace([np.inf, -np.inf], np.nan).dropna()
    n, pos = len(df), df["clv_up"].mean()
    y = df["clv_up"].values

    base_auc, base_sd = _cv_auc(df[BASE].values, y)
    open_auc, open_sd = _cv_auc(df[BASE + OPEN].values, y)
    close_auc, close_sd = _cv_auc(df[BASE + CLOSE].values, y)
    lift_open, lift_close = open_auc - base_auc, close_auc - base_auc
    leakage = lift_close - lift_open

    L = ["# Story 12.10′ — Pinnacle sharp-money lift (OPEN vs CLOSE framing)", ""]
    L += [f"Population: 2026 live morning-edge ⋈ Bovada line movement. n={n} (Pinnacle+steam, moved). "
          f"clv_up rate={pos:.3f}. Label = Bovada open→close move direction. Gate ≥ +{GATE:.2f} on OPEN (actionable)."]
    L += ["", "| Model | CV AUC | Lift vs BASE |", "|---|---|---|",
          f"| BASE (morning edge) | {base_auc:.4f} ± {base_sd:.4f} | — |",
          f"| BASE + OPEN (actionable) | {open_auc:.4f} ± {open_sd:.4f} | **{lift_open:+.4f}** |",
          f"| BASE + CLOSE (leaky) | {close_auc:.4f} ± {close_sd:.4f} | {lift_close:+.4f} |"]
    verdict = "✅ PASS — retain (actionable)" if lift_open >= GATE else "❌ below gate — drop"
    L += ["", f"**Actionable (OPEN) verdict: {verdict}** (lift {lift_open:+.4f} vs gate +{GATE:.2f}).",
          f"**Leakage check:** CLOSE−OPEN lift gap = {leakage:+.4f} "
          f"({'most apparent lift is mechanical close co-movement' if leakage > lift_open else 'open signal holds up'}).",
          "", "Per-feature univariate AUC (direction-agnostic) + logistic coef:"]
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    for name, feats in (("OPEN", BASE + OPEN), ("CLOSE", BASE + CLOSE)):
        Xs = StandardScaler().fit_transform(df[feats].values)
        coef = dict(zip(feats, LogisticRegression(max_iter=1000).fit(Xs, y).coef_[0]))
        L.append(f"\n*{name} framing:*")
        for f in feats:
            L.append(f"  - {f:26s} uni-AUC={_uni_auc(df[f].values.astype(float), y):.3f}  coef={coef[f]:+.3f}")

    _OUT.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nReport → {_OUT}")


if __name__ == "__main__":
    main()
