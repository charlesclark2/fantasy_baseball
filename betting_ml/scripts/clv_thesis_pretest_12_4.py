"""clv_thesis_pretest_12_4.py — Story 12.4 thesis PRE-TEST.

Question: does the market-blind MORNING model edge predict open→close CLV — i.e. does the
line move TOWARD the side the morning model favored? If yes, the market-blind morning pick
anticipates information the market later prices in (the Epic-12 thesis), and a market-meta
model is worth building.

Design (point-in-time, no leakage):
  - MORNING side: the earliest live `prediction_type='morning'` row per 2026 game
    (is_backfill=false) → market-blind model home-win prob (calibrated_win_prob) and
    pred_total_runs. These were generated live each morning → genuinely OOS.
  - MARKET side: mart_odds_line_movement (Bovada, now sourced from the dense Odds-API
    backfill for 2026 — Story 12.3.4). open_* = first pre-game snapshot, pregame_* = last
    before commence, *_line_movement = pregame − open (signed).
  - EDGE AT OPEN: h2h = model_home_prob − open_home_win_prob; totals = pred_total_runs −
    open_total_line. CLV = the *_line_movement (did the line move our way after the open?).

Metrics: Pearson + Spearman corr (edge vs movement) with bootstrap 95% CI; directional hit
on MEDIAN-CENTERED edge (removes the constant vig bias in open_home_win_prob — the mart only
stores the home implied prob, so a true de-vig isn't possible yet); CLV by edge quintile
(monotone increasing ⇒ real signal); and the actionable read: avg CLV in the top-edge decile.
Split by data_source (historical Odds-API vs live Parlay) to rule out a one-source artifact.

Read-only, ~1k rows → runs in seconds.
Usage:  uv run python betting_ml/scripts/clv_thesis_pretest_12_4.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

_OUT = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "clv_thesis_pretest_12_4.md"

_SQL = """
with morn as (
  select game_pk,
         coalesce(calibrated_win_prob, consensus_win_prob, h2h_posterior_prob) as model_home_prob,
         pred_total_runs
  from baseball_data.betting_ml.daily_model_predictions
  where prediction_type='morning' and coalesce(is_backfill,false)=false
    and date_part('year',game_date)=2026
  qualify row_number() over (partition by game_pk order by inserted_at asc)=1
)
select
  mv.game_pk,
  mv.data_source,
  mv.snapshot_count,
  morn.model_home_prob,
  morn.pred_total_runs,
  mv.open_home_win_prob,
  mv.h2h_line_movement,
  mv.open_total_line,
  mv.total_line_movement
from baseball_data.betting.mart_odds_line_movement mv
join morn on morn.game_pk = mv.game_pk
where mv.snapshot_count > 1
"""


def _load() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SQL)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    df["h2h_edge"] = df["model_home_prob"] - df["open_home_win_prob"]
    df["tot_edge"] = df["pred_total_runs"] - df["open_total_line"]
    return df


def _boot_corr(x: np.ndarray, y: np.ndarray, n: int = 2000) -> tuple[float, float]:
    """Bootstrap 95% CI for Pearson r by resampling game pairs."""
    rng = np.random.default_rng(12)
    idx = np.arange(len(x))
    rs = []
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        rs.append(np.corrcoef(x[s], y[s])[0, 1])
    return float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))


def _analyze(df: pd.DataFrame, edge_col: str, move_col: str, label: str) -> dict:
    d = df[[edge_col, move_col, "data_source"]].dropna()
    x = d[edge_col].to_numpy(float)
    y = d[move_col].to_numpy(float)
    n = len(d)

    pear, p_pear = stats.pearsonr(x, y)
    spear, p_spear = stats.spearmanr(x, y)
    lo, hi = _boot_corr(x, y)

    # Directional hit on MEDIAN-CENTERED edge (removes the constant vig bias), excluding
    # games where the line didn't move (move == 0 → no direction to predict).
    xc = x - np.median(x)
    moved = y != 0
    dir_hit = float(np.mean(np.sign(xc[moved]) == np.sign(y[moved]))) if moved.any() else float("nan")

    # CLV by edge quintile — monotone increasing avg movement ⇒ real signal.
    q = pd.qcut(d[edge_col], 5, labels=[f"Q{i}" for i in range(1, 6)], duplicates="drop")
    quint = d.groupby(q, observed=True)[move_col].agg(["mean", "count"]).round(4)

    # Actionable: avg CLV in the top-edge decile (the games we'd most want to bet at open).
    dec_cut = d[edge_col].quantile(0.9)
    top_dec_clv = float(d.loc[d[edge_col] >= dec_cut, move_col].mean())
    bot_dec_clv = float(d.loc[d[edge_col] <= d[edge_col].quantile(0.1), move_col].mean())

    # Source split (rule out a one-source artifact).
    by_src = {}
    for src, g in d.groupby("data_source"):
        if len(g) >= 30:
            by_src[src] = (len(g), round(float(np.corrcoef(g[edge_col], g[move_col])[0, 1]), 4))

    print(f"\n=== {label}  (n={n}) ===")
    print(f"  Pearson r  = {pear:+.4f}  (p={p_pear:.2e})  95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  Spearman r = {spear:+.4f}  (p={p_spear:.2e})")
    print(f"  Directional hit (centered, moved-only) = {dir_hit:.3f}  (n_moved={int(moved.sum())})")
    print(f"  CLV top-edge decile = {top_dec_clv:+.4f}   bottom-edge decile = {bot_dec_clv:+.4f}")
    print("  CLV by edge quintile (mean movement, should rise Q1→Q5):")
    for qlab, row in quint.iterrows():
        print(f"    {qlab}: {row['mean']:+.4f}  (n={int(row['count'])})")
    print(f"  By source: {by_src}")

    return {
        "label": label, "n": n,
        "pearson": round(pear, 4), "pearson_p": p_pear, "pearson_ci": [round(lo, 4), round(hi, 4)],
        "spearman": round(spear, 4), "spearman_p": p_spear,
        "dir_hit_centered": round(dir_hit, 3), "n_moved": int(moved.sum()),
        "clv_top_decile": round(top_dec_clv, 4), "clv_bottom_decile": round(bot_dec_clv, 4),
        "quintile_clv": {str(k): [round(float(v["mean"]), 4), int(v["count"])] for k, v in quint.iterrows()},
        "by_source": by_src,
    }


def _verdict(h2h: dict, tot: dict) -> str:
    sig = h2h["pearson_ci"][0] > 0          # CI excludes 0
    strong = h2h["pearson"] >= 0.15
    if sig and strong:
        return (f"SIGNAL — the market-blind morning H2H edge predicts open→close CLV "
                f"(Pearson {h2h['pearson']:+.3f}, 95% CI {h2h['pearson_ci']}, n={h2h['n']}). "
                f"The morning model anticipates line movement ⇒ the Epic-12 market-meta model is "
                f"worth building. Totals weaker (r={tot['pearson']:+.3f}).")
    if sig:
        return (f"WEAK SIGNAL — H2H corr {h2h['pearson']:+.3f} (CI {h2h['pearson_ci']}) is positive "
                f"but small; revisit with more games / a de-vigged edge before committing to 12.4.")
    return (f"NO SIGNAL — H2H corr {h2h['pearson']:+.3f} (CI {h2h['pearson_ci']}) not reliably > 0. "
            f"The morning edge does not predict CLV; reconsider the thesis.")


def main() -> None:
    print("Loading paired morning-prediction ↔ open→close movement data ...")
    df = _load()
    print(f"Loaded {len(df)} paired games "
          f"(sources: {df['data_source'].value_counts().to_dict()})")

    h2h = _analyze(df, "h2h_edge", "h2h_line_movement", "H2H")
    tot = _analyze(df, "tot_edge", "total_line_movement", "TOTALS")
    verdict = _verdict(h2h, tot)
    print(f"\n>>> 12.4 PRE-TEST VERDICT: {verdict}")

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Story 12.4 — CLV thesis pre-test", "",
        "**Question:** does the market-blind MORNING model edge predict open→close CLV "
        "(the line moving toward our side)?", "",
        f"**Verdict:** {verdict}", "",
        f"Paired games: {len(df)} (2026 live morning predictions ⋈ Bovada open→close movement, "
        "snapshot_count>1). Edge measured vs the OPEN line; CLV = pregame−open line movement.", "",
        "## H2H", _fmt(h2h),
        "## Totals", _fmt(tot),
        "## Caveats",
        "- `h2h_edge` uses `open_home_win_prob` (carries vig — the mart stores only the home "
        "implied prob, so a true de-vig isn't possible yet); correlation is vig-robust, the "
        "directional hit uses the MEDIAN-CENTERED edge to neutralize the constant bias.",
        "- Mean-reversion is not controlled; a positive corr is consistent with (not proof of) "
        "the morning model carrying leading information. A sharp-anchor control is the 12.4 follow-up.",
    ]
    _OUT.write_text("\n".join(lines))
    print(f"\nWrote {_OUT}")


def _fmt(r: dict) -> str:
    q = "\n".join([f"  - {k}: {v[0]:+.4f} (n={v[1]})" for k, v in r["quintile_clv"].items()])
    return (f"- n = {r['n']}\n"
            f"- Pearson r = **{r['pearson']:+.4f}** (95% CI {r['pearson_ci']}, p={r['pearson_p']:.1e})\n"
            f"- Spearman r = {r['spearman']:+.4f} (p={r['spearman_p']:.1e})\n"
            f"- Directional hit (centered, moved-only) = {r['dir_hit_centered']:.3f} (n_moved={r['n_moved']})\n"
            f"- CLV top-edge decile = {r['clv_top_decile']:+.4f}; bottom-edge decile = {r['clv_bottom_decile']:+.4f}\n"
            f"- By source (n, r): {r['by_source']}\n"
            f"- CLV by edge quintile (Q1→Q5 should rise):\n{q}\n")


if __name__ == "__main__":
    main()
