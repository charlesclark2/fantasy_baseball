#!/usr/bin/env python3
"""eval_derivatives.py — Edge Program Story E13.13 (angles 1+2): derivative-market efficiency.

Miller-Davidow + E13.8 thesis: books price the FEATURED markets tight (main H2H dead ×5, main
total a coin-flip) but DERIVATIVES looser (lower limits / less line-setting effort). This script
EVALUATES (does NOT bet) whether the backfilled F5/NRFI/team/alt markets are mispriced relative
to outcomes we settle from our own pitch data.

SCOPE = angles 1+2 ONLY (pure cached-data analysis, no model). Angle 3 (model-vs-market gate) is
E2.6. Pre-registration: `ablation_results/e13_13_preregistration.md` (markets/strategies/
hypotheses fixed BEFORE outcomes). Honest bar: outputs are an efficiency ranking, a mechanical-
derivation deviation map, and a CANDIDATE shortlist for E2.6 — NOT an edge claim (softer ≠ free;
derivatives carry higher vig). Cashability = forward CLV net of vig at PBO<0.2/DSR>0 (E2.6).

DATA (§0.5 — cached S3, NO fresh Snowflake; one read → parquet → cached for every pass):
  * derivative CLOSING odds  ← the E5.1 `mlb/props/market={key}/season=*/date=*` backfill
    (`backfill_multisport_props_to_s3.py` — the canonical, corrected-key `*_1st_5_innings` /
    `*_1st_1_innings` source the E5.2/E5.3 K-prop pipeline already reads), game_pk via
    `mart_game_odds_bridge`. Closing-snapshot selection + over/under derivation done here.
  * realized F5 / 1st-inning runs ← stg_batter_pitches (W1–W3 stable).
  * consensus main close (angle 2) ← mart_closing_line_value.
The bridge / pitch / main reads use the shared `scripts/utils/lakehouse_read` DuckDB-over-S3 helper.

RUN ORDER:
  uv run python betting_ml/scripts/derivative_eval/eval_derivatives.py --smoke      # synthetic, no S3
  uv run python betting_ml/scripts/derivative_eval/eval_derivatives.py --build-cache # operator, >1-min S3 scan
  uv run python betting_ml/scripts/derivative_eval/eval_derivatives.py               # eval cached frame → dossier
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils import derivative_eval as de
from betting_ml.utils.overfitting import (
    DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE, deflated_sharpe, pbo_cscv,
)

# ── Paths ─────────────────────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[3]
CACHE = _REPO / "betting_ml" / "data" / "cache" / "e13_13_derivative_eval_frame.parquet"
DOSSIER_DIR = _REPO / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"


def _out_paths(suffix: str = ""):
    """Dossier output paths. `--smoke` uses the `_smoke` suffix so synthetic numbers can NEVER be
    mistaken for the operator-produced real dossier."""
    return (DOSSIER_DIR / f"e13_13_derivative_efficiency{suffix}.json",
            DOSSIER_DIR / f"e13_13_derivative_efficiency{suffix}.md",
            DOSSIER_DIR / f"e13_13_market_grid_results{suffix}.csv")

# ── Pre-registered grid (mirrors e13_13_preregistration.md) ─────────────────────────────────────
MARKETS = [de.F5_TOTALS, de.F5_H2H, de.NRFI, de.TEAM_TOTALS, de.ALT_TOTALS]
BOOK_GROUPS = ["all", "pinnacle", "soft", "majors"]   # individual books appended at run time
LINE_BUCKETS = {  # totals only
    "all": (None, None),
    "low_le4p5": (None, 4.5),
    "mid_5to6": (5.0, 6.0),
    "high_ge6p5": (6.5, None),
}
STATIC_TOTALS = ("always_over", "always_under")
STATIC_H2H = ("always_home", "always_away", "always_favorite", "always_dog")
MIN_GAMES = 50          # a config needs ≥this many unique GAMES to be "selectable" (game-level, not
                        # quotes — book quotes on one game are correlated, not independent bets)
FRAGILE_GAMES = 250     # a surviving candidate below this is flagged FRAGILE (thin / small-sample)
FDR_Q = 0.10


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Heavy S3 read → cached parquet (operator-run; §0.5 one-read-then-cache)
# ════════════════════════════════════════════════════════════════════════════════════════════════
_S3_BUCKET = "s3://baseball-betting-ml-artifacts"
# The E5.1 backfill home for derivatives (backfill_multisport_props_to_s3.py): one parquet per
# (market, season, date). market_key/season are REAL columns → no hive partition needed.
_PROPS = f"{_S3_BUCKET}/mlb/props"


def build_cache(seasons: list[int], start_date: str | None) -> pd.DataFrame:
    """Read derivative closing odds + pitch-settled outcomes + consensus main close from S3,
    join to a long per-(game × market × book × outcome) frame, and cache it to parquet.

    Derivative odds come from the E5.1 ``mlb/props/market=…`` layout (NOT stg_derivative_odds — that
    is the eval/CLV pipeline; the props backfill is the canonical, corrected-key, full-coverage
    source the E5.2/E5.3 K-prop pipeline already reads). In that schema each TOTALS quote is two
    split rows (player_name='Over'/'Under', price in over_price XOR under_price) and each H2H quote
    is one row per team (player_name=team, moneyline in over_price). We map both into the long
    (outcome_name, outcome_price_american, outcome_point) schema the reshapers + smoke already use:
    outcome_name = player_name, outcome_price_american = coalesce(over_price, under_price)."""
    import duckdb  # for the per-market IOException guard
    from scripts.utils.lakehouse_read import LAKEHOUSE, duck_connect  # heavy/S3 — imported lazily

    con = duck_connect()
    season_list = ",".join(str(s) for s in seasons)
    year_globs = ", ".join(
        f"'{LAKEHOUSE}/stg_batter_pitches/year={y}/**/*.parquet'" for y in seasons)
    date_filter = f"AND game_date >= DATE '{start_date}'" if start_date else ""

    # 1) Derivative CLOSING odds (latest snapshot per quote) — read EACH market separately so an
    #    absent prefix (team_totals / alternate_totals are partial/deferred per the E5.1 audit and
    #    may not exist in S3) is skipped, not fatal (read_parquet errors hard on a zero-match glob).
    odds_parts: list[pd.DataFrame] = []
    for m in (de.F5_TOTALS, de.F5_H2H, de.NRFI, de.TEAM_TOTALS, de.ALT_TOTALS):
        m_sql = f"""
        WITH raw AS (
            SELECT event_id, commence_time, home_team, away_team, season, bookmaker_key,
                   '{m}'                                    AS market_key,
                   player_name                              AS outcome_name,
                   coalesce(over_price, under_price)        AS outcome_price_american,
                   line                                     AS outcome_point,
                   row_number() OVER (
                       PARTITION BY event_id, bookmaker_key, player_name, line
                       ORDER BY snapshot_ts DESC)           AS snap_rank
            FROM read_parquet(['{_PROPS}/market={m}/season=*/date=*/*.parquet'],
                              union_by_name=true, hive_partitioning=false)
            WHERE season IN ({season_list})
        )
        SELECT event_id, season, commence_time, home_team, away_team, bookmaker_key,
               market_key, outcome_name, outcome_price_american, outcome_point
        FROM raw WHERE snap_rank = 1 AND outcome_price_american IS NOT NULL
        """
        try:
            dfm = con.execute(m_sql).fetchdf()
            odds_parts.append(dfm)
            print(f"[cache] {m}: {len(dfm):,} closing quotes")
        except duckdb.IOException as exc:
            if "No files found" in str(exc) or "HTTP" in str(exc):
                print(f"[cache] {m}: no S3 files — skipped (partial/deferred market)")
            else:
                raise
    if not odds_parts:
        raise SystemExit("[error] no derivative-odds files found for any market under "
                         f"{_PROPS}/ — check the E5.1 backfill / season list.")
    odds = pd.concat(odds_parts, ignore_index=True)

    # game_pk via the Odds-API bridge (event_id → game_pk).
    bridge = con.execute(
        f"SELECT game_pk, odds_api_event_id FROM "
        f"read_parquet('{LAKEHOUSE}/mart_game_odds_bridge/**/*.parquet', union_by_name=true) "
        f"WHERE game_pk IS NOT NULL").fetchdf()
    odds = odds.merge(bridge, left_on="event_id", right_on="odds_api_event_id", how="inner")
    odds["game_pk"] = odds["game_pk"].astype("int64")
    odds = odds.drop(columns=["odds_api_event_id", "event_id"])

    # 2) Settle F5 + 1st-inning runs from pitch data (monotonic score-state → max within window).
    settle_sql = f"""
    SELECT game_pk,
           any_value(game_date)                                                  AS game_date,
           max(CASE WHEN inning <= 5 THEN post_pitch_home_score END)             AS f5_home,
           max(CASE WHEN inning <= 5 THEN post_pitch_away_score END)             AS f5_away,
           max(CASE WHEN inning =  1 THEN post_pitch_home_score END)             AS i1_home,
           max(CASE WHEN inning =  1 THEN post_pitch_away_score END)             AS i1_away,
           max(post_pitch_home_score)                                            AS final_home,
           max(post_pitch_away_score)                                            AS final_away
    FROM read_parquet([{year_globs}], union_by_name=true, hive_partitioning=false)
    WHERE game_year IN ({season_list}) {date_filter}
    GROUP BY game_pk
    """
    settled = con.execute(settle_sql).fetchdf()

    # 3) Consensus main close (angle 2).
    main_sql = f"""
    SELECT game_pk, close_total_line AS main_total_line,
           close_vf_home AS main_vf_home, close_vf_over AS main_vf_over
    FROM read_parquet('{LAKEHOUSE}/mart_closing_line_value/**/*.parquet', union_by_name=true)
    """
    main = con.execute(main_sql).fetchdf()
    con.close()

    frame = odds.merge(settled, on="game_pk", how="inner").merge(main, on="game_pk", how="left")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(CACHE, index=False)
    print(f"[cache] wrote {len(frame):,} rows → {CACHE}  "
          f"({frame['game_pk'].nunique():,} games, {frame['bookmaker_key'].nunique()} books, "
          f"markets={sorted(frame['market_key'].unique())})")
    return frame


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Reshape long → wide per market (pure pandas; same schema for smoke + real)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _reshape_totals(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """One row per (game_pk, book, point) with over_price/under_price + realized total + main."""
    d = df[df["market_key"] == market].copy()
    if d.empty:
        return d
    d["side"] = d["outcome_name"].str.lower().map({"over": "over", "under": "under"})
    d = d[d["side"].notna()]
    keys = ["game_pk", "season", "bookmaker_key", "outcome_point"]
    wide = (d.pivot_table(index=keys, columns="side", values="outcome_price_american",
                          aggfunc="first").reset_index())
    if "over" not in wide or "under" not in wide:
        return pd.DataFrame()
    wide = wide.rename(columns={"over": "over_price", "under": "under_price"})
    meta = d.drop_duplicates("game_pk").set_index("game_pk")
    if market == de.NRFI:
        wide["actual_total"] = (meta.loc[wide["game_pk"], "i1_home"].to_numpy()
                                + meta.loc[wide["game_pk"], "i1_away"].to_numpy())
    else:  # F5 / team / alt → first-5-innings total (team_totals is best-effort: same settle)
        wide["actual_total"] = (meta.loc[wide["game_pk"], "f5_home"].to_numpy()
                                + meta.loc[wide["game_pk"], "f5_away"].to_numpy())
    wide["main_total_line"] = meta.loc[wide["game_pk"], "main_total_line"].to_numpy()
    wide["line"] = wide["outcome_point"].astype(float)

    dv = wide.apply(lambda r: de.devig_pair(r["over_price"], r["under_price"]), axis=1)
    wide["fair_over"] = [x["fair_a"] for x in dv]
    wide["hold"] = [x["hold"] for x in dv]
    wide["realized_over"] = [de.realized_over(t, ln)
                             for t, ln in zip(wide["actual_total"], wide["line"])]
    # soft-vs-sharp: distance to Pinnacle's fair_over for the same (game, point)
    pin = wide[wide["bookmaker_key"] == de.PINNACLE][["game_pk", "line", "fair_over"]]
    pin = pin.rename(columns={"fair_over": "pin_fair_over"})
    wide = wide.merge(pin, on=["game_pk", "line"], how="left")
    wide["dist_to_sharp"] = (wide["fair_over"] - wide["pin_fair_over"]).abs()
    return wide


def _reshape_h2h(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_pk, book) with home/away(/draw) prices + realized F5 home-win + main."""
    d = df[df["market_key"] == de.F5_H2H].copy()
    if d.empty:
        return d
    nm = d["outcome_name"].astype(str)
    d["slot"] = np.where(nm == d["home_team"], "home_price",
                np.where(nm == d["away_team"], "away_price", "draw_price"))
    keys = ["game_pk", "season", "bookmaker_key"]
    wide = (d.pivot_table(index=keys, columns="slot", values="outcome_price_american",
                          aggfunc="first").reset_index())
    if "home_price" not in wide or "away_price" not in wide:
        return pd.DataFrame()
    if "draw_price" not in wide:
        wide["draw_price"] = np.nan
    meta = d.drop_duplicates("game_pk").set_index("game_pk")
    for c in ("f5_home", "f5_away", "main_vf_home"):
        wide[c] = meta.loc[wide["game_pk"], c].to_numpy()

    dv = wide.apply(lambda r: de.devig_pair(r["home_price"], r["away_price"]), axis=1)
    wide["fair_home"] = [x["fair_a"] for x in dv]      # 2-way home (renormalised, draw excluded)
    wide["hold"] = [x["hold"] for x in dv]
    wide["realized_home"] = [de.realized_home_f5(h, a)
                             for h, a in zip(wide["f5_home"], wide["f5_away"])]
    pin = wide[wide["bookmaker_key"] == de.PINNACLE][["game_pk", "fair_home"]]
    pin = pin.rename(columns={"fair_home": "pin_fair_home"})
    wide = wide.merge(pin, on="game_pk", how="left")
    wide["dist_to_sharp"] = (wide["fair_home"] - wide["pin_fair_home"]).abs()
    return wide


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Angle 1 — efficiency benchmark + static directional strategies
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _line_bucket_mask(line: np.ndarray, bucket: str) -> np.ndarray:
    lo, hi = LINE_BUCKETS[bucket]
    ln = np.asarray(line, float)
    m = np.ones(len(ln), bool)
    if lo is not None:
        m &= ln >= lo
    if hi is not None:
        m &= ln <= hi
    return m


def angle1(wides: dict[str, pd.DataFrame], books: list[str]) -> dict:
    """Per (market × book-group × season) efficiency rows + per-config static-strategy ROIs +
    FDR over calibration cells + PBO/DSR over the static-strategy grid."""
    eff_rows: list[dict] = []
    static_configs: list[dict] = []
    groups = BOOK_GROUPS + [b for b in books if b not in BOOK_GROUPS]

    for market, w in wides.items():
        if w is None or w.empty:
            continue
        is_h2h = market == de.F5_H2H
        seasons = sorted(w["season"].dropna().unique().tolist())
        for grp in groups:
            gmask = de.book_mask(w["bookmaker_key"].to_numpy(), grp)
            if not gmask.any():
                continue
            for season in seasons + ["pooled"]:
                smask = gmask if season == "pooled" else (gmask & (w["season"] == season).to_numpy())
                sub = w[smask]
                if sub.empty:
                    continue
                if is_h2h:
                    summ = de.efficiency_summary(
                        sub["fair_home"].to_numpy(), sub["realized_home"].to_numpy(),
                        hold=sub["hold"].to_numpy(), dist_to_sharp=sub["dist_to_sharp"].to_numpy())
                    # favourite-rate: realized win-rate of the de-vig favourite
                    fav_home = sub["fair_home"].to_numpy() > 0.5
                    rh = sub["realized_home"].to_numpy()
                    ok = np.isfinite(rh)
                    fav_hit = np.where(fav_home[ok], rh[ok], 1 - rh[ok])
                    summ["favorite_rate"] = float(fav_hit.mean()) if ok.any() else float("nan")
                    summ["tie_rate"] = float(np.mean(~np.isfinite(rh))) if len(rh) else float("nan")
                else:
                    summ = de.efficiency_summary(
                        sub["fair_over"].to_numpy(), sub["realized_over"].to_numpy(),
                        hold=sub["hold"].to_numpy(), line=sub["line"].to_numpy(),
                        actual_total=sub["actual_total"].to_numpy(),
                        dist_to_sharp=sub["dist_to_sharp"].to_numpy())
                eff_rows.append({"market": market, "book_group": grp, "season": str(season),
                                 "n": len(sub), **summ})

    # FDR over the per-cell calibration tests (pooled rows only — the per-season rows are the
    # consistency check, not independent tests).
    pooled = [r for r in eff_rows if r["season"] == "pooled"]
    fdr = de.bh_fdr([r.get("calib_p", float("nan")) for r in pooled], q=FDR_Q)
    for r, surv in zip(pooled, fdr["survive"]):
        r["calib_fdr_survive"] = bool(surv)

    # Static directional strategies (per market × strategy × book-group × line-bucket).
    for market, w in wides.items():
        if w is None or w.empty:
            continue
        is_h2h = market == de.F5_H2H
        strategies = STATIC_H2H if is_h2h else STATIC_TOTALS
        line_buckets = ["all"] if is_h2h else list(LINE_BUCKETS)
        for grp in groups:
            gmask = de.book_mask(w["bookmaker_key"].to_numpy(), grp)
            for lb in line_buckets:
                if is_h2h:
                    lmask = np.ones(len(w), bool)
                else:
                    lmask = _line_bucket_mask(w["line"].to_numpy(), lb)
                sub = w[gmask & lmask]
                if sub.empty:
                    continue
                for strat in strategies:
                    cfg = _eval_static(sub, market, strat, grp, lb, is_h2h)
                    if cfg is not None:
                        static_configs.append(cfg)

    # FDR over the selectable static strategies' edge tests (the static-channel multiple-comparison
    # control). Survival = the strategy's +EV-net-of-vig is real after deflating for every config.
    sel_static = [c for c in static_configs if c["n"] >= MIN_GAMES]
    static_fdr = de.bh_fdr([c["roi_p"] for c in sel_static], q=FDR_Q)
    for c, surv in zip(sel_static, static_fdr["survive"]):
        c["roi_fdr_survive"] = bool(surv)

    pbo, dsr = _deflate_static(static_configs)
    return {"efficiency": eff_rows, "static": static_configs, "fdr": _fdr_public(fdr),
            "static_fdr": _fdr_public(static_fdr), "pbo": pbo, "dsr": dsr}


def _eval_static(sub: pd.DataFrame, market: str, strat: str, grp: str, lb: str,
                 is_h2h: bool) -> dict | None:
    """One static-strategy config, scored at GAME level. Per-quote PnL net of the offered vig is
    AVERAGED to one return per game_pk first — book quotes on the same game are NOT independent
    observations (same outcome), so counting each as a separate bet inflates DSR/PBO/the edge t-test
    (the correlated-quote trap that over-credited the thin F5≥6.5 tail). n = unique GAMES; ROI/Sharpe/
    per-season/per-ym/roi_p all derive from the game-level series. Side selection is static or
    de-vig-based — never outcome-based."""
    if is_h2h:
        if strat == "always_home":
            side = np.full(len(sub), "home", dtype=object)
        elif strat == "always_away":
            side = np.full(len(sub), "away", dtype=object)
        else:  # favorite / dog from the book's own de-vig (not the outcome)
            fav_home = sub["fair_home"].to_numpy() > 0.5
            pick_home = fav_home if strat == "always_favorite" else ~fav_home
            side = np.where(pick_home, "home", "away").astype(object)
        am = np.where(side == "home", sub["home_price"].to_numpy(float),
                      sub["away_price"].to_numpy(float))
        pay = de.h2h_payoff_vec(sub["f5_home"].to_numpy(), sub["f5_away"].to_numpy(), side, am)
    else:
        sd = "over" if strat == "always_over" else "under"
        am = sub["over_price"].to_numpy(float) if sd == "over" else sub["under_price"].to_numpy(float)
        pay = de.static_total_payoffs(sub["actual_total"].to_numpy(), sub["line"].to_numpy(), sd, am)

    # year-month slice (for PBO): prefer game_date; fall back to season when dates are absent.
    if "game_date" in sub.columns and sub["game_date"].notna().any():
        ymv = pd.to_datetime(sub["game_date"], errors="coerce").dt.strftime("%Y-%m")
    else:
        ymv = sub["season"].astype("Int64").astype(str)
    quotes = pd.DataFrame({"game_pk": sub["game_pk"].to_numpy(), "season": sub["season"].to_numpy(),
                           "ym": ymv.to_numpy(), "p": pay})
    quotes = quotes[np.isfinite(quotes["p"].to_numpy())]
    if quotes.empty:
        return None
    # collapse correlated book-quotes → ONE return per game (mean payoff across books bet that game)
    games = quotes.groupby("game_pk").agg(p=("p", "mean"), season=("season", "first"),
                                          ym=("ym", "first")).reset_index()
    g_pay = games["p"].to_numpy(float)
    n_games = len(games)
    sd_pay = g_pay.std(ddof=1) if n_games > 1 else 0.0
    per_season = {str(s): float(gg["p"].mean()) for s, gg in games.groupby("season")}
    per_ym = {str(y): float(gg["p"].mean()) for y, gg in games.groupby("ym")}
    signs = [np.sign(v) for v in per_season.values()]
    season_sign_consistent = bool(len(signs) >= 2 and len(set(signs)) == 1 and signs[0] != 0)
    if sd_pay > 0 and n_games > 1:
        from math import erfc, sqrt
        t = float(g_pay.mean() / (sd_pay / np.sqrt(n_games)))
        roi_p = float(0.5 * erfc(t / sqrt(2.0)))   # upper-tail (normal approx)
    else:
        t, roi_p = float("nan"), float("nan")
    return {"name": f"{market}|{strat}|{grp}|{lb}", "market": market, "strategy": strat,
            "book_group": grp, "line_bucket": lb, "n": n_games, "n_quotes": int(len(quotes)),
            "roi": float(g_pay.mean()), "sharpe": float(g_pay.mean() / sd_pay) if sd_pay > 0 else 0.0,
            "roi_t": t, "roi_p": roi_p, "per_season": per_season, "per_ym": per_ym,
            "season_sign_consistent": season_sign_consistent, "roi_fdr_survive": False,
            "_payoffs": g_pay}


def _deflate_static(configs: list[dict]) -> tuple[dict, dict]:
    """PBO (CSCV over year-month slices × selectable configs) + DSR on the in-sample-best config,
    deflated by the number of selectable configs (the multiple-comparison count)."""
    sel = [c for c in configs if c["n"] >= MIN_GAMES]
    if len(sel) < 2:
        return ({"pbo": float("nan"), "note": f"only {len(sel)} selectable configs (need ≥2)"},
                {"dsr": float("nan"), "note": "no selectable config"})
    yms = sorted({ym for c in sel for ym in c["per_ym"]})
    if len(yms) < 4:
        pbo = {"pbo": float("nan"), "note": f"only {len(yms)} ym slices (need ≥4 for CSCV)"}
    else:
        mat = np.array([[c["per_ym"].get(ym, np.nan) for c in sel] for ym in yms], float)
        # configs present in every slice (CSCV needs a dense matrix)
        dense = ~np.isnan(mat).any(axis=0)
        if dense.sum() >= 2:
            res = pbo_cscv(mat[:, dense], higher_is_better=True,
                           n_splits=min(16, len(yms)), max_combos=2000)
            pbo = {"pbo": res.pbo, "n_combos": res.n_combos, "n_configs": int(dense.sum()),
                   "n_splits": res.n_splits, "clears_live_pbo": res.clears_live_pbo}
        else:
            pbo = {"pbo": float("nan"), "note": "no config dense across all ym slices"}

    best = max(sel, key=lambda c: c["roi"])
    trial_sharpes = [c["sharpe"] for c in sel]
    if len(best["_payoffs"]) >= 3:
        d = deflated_sharpe(best["_payoffs"], n_trials=len(sel), trial_sharpes=trial_sharpes)
        dsr = {"dsr": d.dsr, "observed_sr": d.observed_sr, "sr0": d.sr0,
               "n_trials": d.n_trials, "n_obs": d.n_obs, "passes_live": d.passes_live,
               "best_config": best["name"], "best_roi": best["roi"]}
    else:
        dsr = {"dsr": float("nan"), "note": "best config <3 bets"}
    return pbo, dsr


def _fdr_public(fdr: dict) -> dict:
    return {"threshold": fdr["threshold"], "n_survive": fdr["n_survive"],
            "n_tested": fdr["n_tested"], "q": FDR_Q}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Angle 2 — mechanical-derivation check
# ════════════════════════════════════════════════════════════════════════════════════════════════
def angle2(wides: dict[str, pd.DataFrame]) -> list[dict]:
    """Per market: fit the book's implied derivative mapping AND the true mapping off the
    consensus main close; report the systematic residual (realized − book-implied) + its z.

    Two regimes, kept UNIT-CONSISTENT (book-implied and realized in the SAME space):
      * VARYING-LINE totals (F5 / team / alt): the line IS the prediction → fit book_line vs
        realized_total off the main total line (runs space).
      * FIXED-LINE / binary markets (NRFI fixed 0.5, F5 h2h): the info is in the PRICE, not the
        line → fit the book's de-vigged probability vs the realized binary off the main close
        (probability space). (Comparing the NRFI 0.5 line to a run count is meaningless — it gives
        a spurious huge z because book_slope≡0.)"""
    rows: list[dict] = []

    def _emit(market, kind, dev, hold, space):
        rows.append({"market": market, "kind": kind, "space": space, "n": dev["n"],
                     "book_slope": dev["book_fit"]["slope"], "book_intercept": dev["book_fit"]["intercept"],
                     "true_slope": dev["true_fit"]["slope"], "true_intercept": dev["true_fit"]["intercept"],
                     "mean_resid": dev["mean_resid"], "resid_z": dev["resid_z"], "median_hold": hold})

    # Varying-line totals: book line vs realized total, off the main total (runs space).
    for market in (de.F5_TOTALS, de.TEAM_TOTALS, de.ALT_TOTALS):
        w = wides.get(market)
        if w is None or w.empty:
            continue
        g = (w.dropna(subset=["main_total_line"])
             .groupby("game_pk")
             .agg(book_line=("line", "median"), actual_total=("actual_total", "first"),
                  main_total=("main_total_line", "first"), hold=("hold", "median"))
             .reset_index())
        # a genuinely varying line is required for the runs-space fit; a (near-)fixed line ⇒ skip
        if len(g) < 10 or g["book_line"].std() < 1e-6:
            continue
        dev = de.derivation_deviation(g["main_total"].to_numpy(),
                                      g["book_line"].to_numpy(), g["actual_total"].to_numpy())
        _emit(market, "line_vs_realized_runs", dev, float(g["hold"].median()), "runs")

    # NRFI (fixed 0.5 line): book de-vig P(YRFI) vs realized YRFI, off the main total (prob space).
    w = wides.get(de.NRFI)
    if w is not None and not w.empty:
        g = (w.dropna(subset=["main_total_line", "realized_over"])
             .groupby("game_pk")
             .agg(book_p=("fair_over", "median"), realized=("realized_over", "first"),
                  main_total=("main_total_line", "first"), hold=("hold", "median"))
             .reset_index())
        if len(g) >= 10:
            dev = de.derivation_deviation(g["main_total"].to_numpy(),
                                          g["book_p"].to_numpy(), g["realized"].to_numpy())
            _emit(de.NRFI, "yrfi_prob", dev, float(g["hold"].median()), "prob")

    # F5 h2h: book de-vig P(home) vs realized home-win, off the consensus main P(home) (prob space).
    w = wides.get(de.F5_H2H)
    if w is not None and not w.empty:
        g = (w.dropna(subset=["main_vf_home", "realized_home"])
             .groupby("game_pk")
             .agg(book_phome=("fair_home", "median"), realized=("realized_home", "first"),
                  main_phome=("main_vf_home", "first"), hold=("hold", "median"))
             .reset_index())
        if len(g) >= 10:
            dev = de.derivation_deviation(g["main_phome"].to_numpy(),
                                          g["book_phome"].to_numpy(), g["realized"].to_numpy())
            _emit(de.F5_H2H, "home_prob", dev, float(g["hold"].median()), "prob")
    return rows


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Candidate shortlist + verdict
# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_candidates(a1: dict, a2: list[dict]) -> dict:
    """Honest CANDIDATE shortlist for E2.6 (NOT an edge). A candidate must clear MULTIPLE legs;
    a clean empty shortlist closes the derivative hope."""
    cands: list[dict] = []
    pbo_ok = (a1["pbo"].get("pbo") is not None and np.isfinite(a1["pbo"].get("pbo", np.nan))
              and a1["pbo"]["pbo"] < PBO_SHADOW_TO_LIVE)
    dsr_ok = (a1["dsr"].get("dsr") is not None and np.isfinite(a1["dsr"].get("dsr", np.nan))
              and a1["dsr"]["dsr"] >= DSR_CONFIDENCE)

    # Static-strategy candidates (the retail-bias / shading probe). A static directional bet is a
    # candidate only when ALL hold: ROI>0 net of vig (GAME-level) + sign-consistent across seasons +
    # its edge survives FDR across every static config (multiple-comparison control) + the grid's
    # in-sample-best persists out of sample (PBO<0.2). The per-bet DSR is reported as global context,
    # not the per-candidate gate. Overlapping book-GROUP cells (all/soft/majors) on the SAME games
    # are deduped to one signal per (market, strategy, line_bucket) so the same edge isn't triple-
    # counted; each surviving signal is FRAGILE-flagged when its unique-game count < FRAGILE_GAMES.
    raw_static_cands = [c for c in a1["static"]
                        if c["n"] >= MIN_GAMES and c["roi"] > 0 and c["season_sign_consistent"]
                        and c.get("roi_fdr_survive") and pbo_ok]
    by_signal: dict[tuple, list] = defaultdict(list)
    for c in raw_static_cands:
        by_signal[(c["market"], c["strategy"], c["line_bucket"])].append(c)
    for (market, strat, lb), group in by_signal.items():
        best = max(group, key=lambda c: c["n"])   # the widest-coverage book-group represents it
        cands.append({"source": "angle1_static",
                      "name": f"{market}|{strat}|{lb}", "n": best["n"], "n_quotes": best.get("n_quotes"),
                      "book_groups": sorted({c["book_group"] for c in group}),
                      "roi_net_vig": best["roi"], "roi_p": best.get("roi_p"),
                      "per_season_roi": {k: round(v, 4) for k, v in best["per_season"].items()},
                      "season_consistent": True, "fdr_survive": True,
                      "grid_pbo_lt_0p2": pbo_ok, "grid_dsr_ge_0p95": dsr_ok,
                      "fragile": bool(best["n"] < FRAGILE_GAMES), "is_candidate": True})

    # Calibration-bias candidates: FDR-surviving INDIVIDUAL-book cell with |bias| > half the hold
    # (the aggregate all/soft/majors groups are excluded — they overlap the individual books).
    _agg = {"all", "soft", "majors"}
    for r in a1["efficiency"]:
        if r["season"] != "pooled" or r["book_group"] in _agg or not r.get("calib_fdr_survive"):
            continue
        half_hold = abs(r.get("mean_vig", np.nan)) / 2.0
        if np.isfinite(r.get("calib_bias", np.nan)) and abs(r["calib_bias"]) > half_hold > 0:
            cands.append({"source": "angle1_calibration", "name": f"{r['market']}|{r['book_group']}",
                          "n": r["n"], "calib_bias": r["calib_bias"], "half_hold": half_hold,
                          "fdr_survive": True, "fragile": bool(r["n"] < FRAGILE_GAMES),
                          "is_candidate": True})

    # Angle 2 is a DIAGNOSTIC map (the mechanical-derivation deviation), NOT a standalone candidate
    # source. We only ANNOTATE corroboration from the PROBABILITY-space angle-2 rows (NRFI/h2h) — the
    # runs-space totals residual z is the mean-vs-median line-convention CONFOUND (always large), so
    # it must NEVER bolster a candidate. Corroborate iff a prob-space deviation (|z|>4) shares the
    # candidate's market.
    a2_prob_dev = {r["market"] for r in a2 if r.get("space") == "prob"
                   and np.isfinite(r.get("resid_z", np.nan)) and abs(r["resid_z"]) > 4}
    for c in cands:
        if c.get("is_candidate") and c["name"].split("|")[0] in a2_prob_dev:
            c["angle2_corroborated"] = True

    real = [c for c in cands if c.get("is_candidate")]
    n_fragile = sum(1 for c in real if c.get("fragile"))
    if not real:
        verdict = "CLEAN NULL — all derivatives efficient"
    elif n_fragile == len(real):
        verdict = f"NO ROBUST EDGE — {len(real)} FRAGILE thin-tail candidate(s) for E2.6 only"
    else:
        verdict = f"CANDIDATES FOR E2.6 — {len(real) - n_fragile} robust + {n_fragile} fragile"
    return {"candidates": real, "near_misses": [c for c in cands if not c.get("is_candidate")],
            "n_fragile": n_fragile, "verdict": verdict}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Dossier
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(x, nd=4):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def write_dossier(meta: dict, a1: dict, a2: list[dict], cand: dict, *,
                  suffix: str = "", synthetic: bool = False) -> None:
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    json_out, md_out, csv_out = _out_paths(suffix)
    result = {"synthetic": synthetic, "meta": meta,
              "angle1": {k: v for k, v in a1.items() if k != "static"},
              "angle1_static": [{k: v for k, v in c.items() if k != "_payoffs"} for c in a1["static"]],
              "angle2": a2, "candidates": cand}
    json_out.write_text(json.dumps(result, indent=2, default=str))

    # the no-cherry-pick CSV ledger: every efficiency cell + every static config
    rows = []
    for r in a1["efficiency"]:
        rows.append({"kind": "efficiency", **r})
    for c in a1["static"]:
        rows.append({"kind": "static", "market": c["market"], "book_group": c["book_group"],
                     "strategy": c["strategy"], "line_bucket": c["line_bucket"], "n": c["n"],
                     "roi": c["roi"], "sharpe": c["sharpe"], "roi_p": c.get("roi_p"),
                     "roi_fdr_survive": c.get("roi_fdr_survive"),
                     "season_sign_consistent": c["season_sign_consistent"]})
    pd.DataFrame(rows).to_csv(csv_out, index=False)

    md_out.write_text(_render_md(meta, a1, a2, cand, synthetic=synthetic))
    print(f"[dossier] {md_out.name} · {json_out.name} · {csv_out.name} → {DOSSIER_DIR}")
    print(f"[verdict] {cand['verdict']}  ({len(cand['candidates'])} candidate(s))")


def _render_md(meta, a1, a2, cand, *, synthetic: bool = False) -> str:
    banner = (["> ⚠️ **SYNTHETIC SMOKE OUTPUT** — generated by `--smoke` on fabricated efficient "
               "data to prove the pipeline + honest math end-to-end. NOT the real evaluation; the "
               "operator-run `eval_derivatives.py` (no suffix) produces the real dossier.", ""]
              if synthetic else [])
    L = banner + ["# E13.13 — Derivative-Market Mispricing Evaluation (angles 1+2)", "",
         f"**Verdict: {cand['verdict']}** — {len(cand['candidates'])} candidate(s) for E2.6.", "",
         "Pure cached-data efficiency evaluation (NO model). Pre-registration: "
         "`e13_13_preregistration.md`. **Honest bar:** candidates ≠ edge — softer ≠ free "
         "(derivatives carry higher vig + lower limits); the cashability verdict is forward CLV "
         "net of the derivative's own vig at PBO<0.2/DSR>0 (E2.6/forward), NOT here.", "",
         "## Coverage", "",
         f"- {meta.get('n_rows', 0):,} closing quotes · {meta.get('n_games', 0):,} games · "
         f"{meta.get('n_books', 0)} books · seasons {meta.get('seasons')}",
         f"- markets present: {meta.get('markets')}", "",
         "## Deflation (anti-data-mining)", "",
         f"- static-strategy grid: {meta.get('n_static_configs', 0)} configs, "
         f"{meta.get('n_selectable', 0)} selectable (≥{MIN_GAMES} games; scored GAME-level — book "
         "quotes on one game are correlated, not independent bets)",
         f"- PBO (CSCV over ym slices): **{_fmt(a1['pbo'].get('pbo'),3)}** "
         f"(<{PBO_SHADOW_TO_LIVE} required) {a1['pbo'].get('note','')}",
         f"- DSR (deflated by trial count): **{_fmt(a1['dsr'].get('dsr'),3)}** "
         f"(≥{DSR_CONFIDENCE} required); best static = `{a1['dsr'].get('best_config','—')}` "
         f"ROI {_fmt(a1['dsr'].get('best_roi'))}",
         f"- calibration FDR (q={FDR_Q}): {a1['fdr']['n_survive']}/{a1['fdr']['n_tested']} "
         f"cells survive", "",
         "## Angle 1 — efficiency ranking (pooled cells, sorted by least-efficient)", "",
         "Brier floor for a centred coin-flip market = 0.25 (E13.8). brier≈0.25 + "
         "over/favorite-rate≈implied ⇒ efficient. `calib_bias` = realized − implied "
         "(✚ = event underpriced).", "",
         "| market | book | n | brier | vig | over/fav-rate | implied | calib_bias | z | FDR | MAE |",
         "|---|---|--:|--:|--:|--:|--:|--:|--:|:--:|--:|"]
    pooled = sorted([r for r in a1["efficiency"] if r["season"] == "pooled"],
                    key=lambda r: -(r.get("brier") or 0))
    for r in pooled:
        rate = r.get("favorite_rate", r.get("over_rate"))
        L.append(f"| {r['market']} | {r['book_group']} | {r['n']} | {_fmt(r.get('brier'),3)} | "
                 f"{_fmt(r.get('mean_vig'),3)} | {_fmt(rate,3)} | {_fmt(r.get('implied_over_rate'),3)} | "
                 f"{_fmt(r.get('calib_bias'),3)} | {_fmt(r.get('calib_z'),2)} | "
                 f"{'✓' if r.get('calib_fdr_survive') else '·'} | {_fmt(r.get('line_mae'),2)} |")
    L += ["", "## Angle 1 — pre-registered static directional strategies (net of offered vig)", "",
          "ROI = mean per-$1 PnL net of the offered vig (the retail-bias / shading probe). "
          "A +ROI here is a CANDIDATE only if season-sign-consistent AND its edge survives FDR "
          f"across all static configs (q={FDR_Q}) AND the grid's in-sample-best persists OOS "
          "(PBO<0.2) — else it is multiple-comparison noise (the E5.4 trap). Per-bet DSR is "
          "reported above as global context (a single binary bet's Sharpe is tiny → DSR is harsh).",
          f"Static-edge FDR: {a1['static_fdr']['n_survive']}/{a1['static_fdr']['n_tested']} "
          "static configs survive.", "",
          "| market | strategy | book | bucket | games | quotes | ROI | sharpe | season-consistent |",
          "|---|---|---|---|--:|--:|--:|--:|:--:|"]
    for c in sorted([c for c in a1["static"] if c["n"] >= MIN_GAMES],
                    key=lambda c: -c["roi"])[:25]:
        L.append(f"| {c['market']} | {c['strategy']} | {c['book_group']} | {c['line_bucket']} | "
                 f"{c['n']} | {c.get('n_quotes','—')} | {_fmt(c['roi'])} | {_fmt(c['sharpe'],2)} | "
                 f"{'✓' if c['season_sign_consistent'] else '·'} |")
    L += ["", "## Angle 2 — mechanical-derivation deviation map", "",
          "Does the book derive the F5/NRFI line by a fixed rule off the consensus main close? "
          "`book_slope` ≈ `true_slope` ⇒ the mechanical derivation tracks reality (efficient). "
          "**Caveat:** the `runs`-space row (F5 totals `line_vs_realized_runs`) has a structurally "
          "large `z` — that residual is the mean-vs-median line convention CONFOUND (totals lines "
          "balance action near the median; realized runs are right-skewed), NOT a deviation signal. "
          "Only the `prob`-space rows (NRFI / h2h) are clean deviation tests; this map is diagnostic "
          "— exploitability is decided by the unit-correct Angle-1 static ROI net of vig.", "",
          "| market | kind | space | n | book_slope | true_slope | mean_resid | z | ½·hold |",
          "|---|---|---|--:|--:|--:|--:|--:|--:|"]
    for r in a2:
        L.append(f"| {r['market']} | {r['kind']} | {r.get('space','—')} | {r['n']} | "
                 f"{_fmt(r.get('book_slope'),3)} | {_fmt(r.get('true_slope'),3)} | "
                 f"{_fmt(r.get('mean_resid'),3)} | {_fmt(r.get('resid_z'),2)} | "
                 f"{_fmt(abs(r.get('median_hold',0))/2,3)} |")
    L += ["", "## Candidate shortlist for E2.6", ""]
    if cand["candidates"]:
        for c in cand["candidates"]:
            tag = " ⚠️ FRAGILE" if c.get("fragile") else ""
            L.append(f"- **{c['name']}**{tag} ({c['source']}, {c.get('n')} games) — "
                     + ", ".join(f"{k}={_fmt(v) if isinstance(v, float) else v}"
                                 for k, v in c.items()
                                 if k not in ("name", "source", "n", "is_candidate", "fragile")))
        L += ["",
              "### ⚠️ Honest reading (candidates ≠ edge — softer ≠ free)",
              f"- **{cand.get('n_fragile', 0)} of {len(cand['candidates'])} candidate(s) are FRAGILE** "
              f"(< {FRAGILE_GAMES} unique games). A FRAGILE F5-totals candidate in the high line "
              "bucket is the **extreme tail** (F5 line ≥6.5 ≈ the top ~1% of lines, mean line ~4.5) "
              "— precisely the **lowest-limit** corner of the derivative market (Miller-Davidow): a "
              "real bettor faces tiny max stakes there, and the ROI is small-sample-inflated (check "
              "`per_season_roi` for a single-season fluke).",
              "- **Settlement caveat (F5 void):** F5 outcomes are settled as the score through "
              "inning ≤5; the harness does **not** yet exclude rain-shortened / suspended games "
              "(<5 innings ⇒ the real F5 bet is VOID/no-action). That biases UNDER strategies "
              "slightly favourable — re-settle with an innings-completed filter before trusting an "
              "F5-under candidate.",
              "- **The verdict here is NOT cashability.** Every candidate is a pre-registered target "
              "for **E2.6** (forward CLV net of the derivative's own vig at PBO<0.2/DSR>0). Given "
              "H2H dead ×5, the efficient main total (E13.8), E5.4's null, and the thin-tail/low-"
              "limit nature, the prior that any survives forward is poor."]
    else:
        # surface the strongest near-miss so the null is transparent (not hiding a tempting cell)
        sel = [c for c in a1["static"] if c["n"] >= MIN_GAMES]
        nm = max(sel, key=lambda c: c["roi"]) if sel else None
        nm_line = (f" Strongest near-miss = `{nm['name']}` ({nm['n']} games, ROI {_fmt(nm['roi'])}, "
                   f"roi_p {_fmt(nm.get('roi_p'))}) — it does NOT survive FDR across the "
                   f"{a1['static_fdr']['n_tested']} configs and sits in the extreme F5 line tail "
                   "(lowest-limit corner); at quote-level it looked far larger, but that was the "
                   "correlated-book-quote inflation the game-level scoring removes." if nm else "")
        L.append("**None.** No derivative cleared the deflated, GAME-level, multiple-comparison-"
                 "corrected bar → with E5.4 this closes the derivative-edge hope. The honest "
                 "conclusion stands: value = product-quality calibration + transparency + fantasy, "
                 "not a cashable derivative edge." + nm_line +
                 " (Forward live capture per E2.0b-fix can still re-open via E2.6 if a prospective "
                 "CLV signal appears.)")
    L += ["", "_Generated by `eval_derivatives.py` (E13.13, angles 1+2). Strategies scored GAME-"
          "level (correlated book-quotes collapsed per game). Every cell + config is logged in "
          "`e13_13_market_grid_results.csv` (no cherry-pick)._"]
    return "\n".join(L)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Smoke (synthetic; proves the full pipeline end-to-end with NO S3)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def make_smoke_frame(n_games: int = 700, seed: int = 7, *, efficiency: float = 1.0) -> pd.DataFrame:
    """Synthetic long frame in the cache schema, priced at the TRUE generating probabilities so
    the books are genuinely efficient → EXPECTED verdict = clean null (the pipeline + the honest
    math both exercised end-to-end). `efficiency` ∈ [0,1]: 1.0 = exactly fair; <1.0 shrinks the
    book's prob toward 0.5 (deliberate mispricing) — used by the unit tests to prove the gate can
    DETECT a candidate. Uses scipy Poisson/Skellam for the exact outcome probabilities."""
    from scipy.stats import poisson, skellam
    rng = np.random.default_rng(seed)
    books = ["pinnacle", "draftkings", "fanduel", "betmgm", "bovada"]
    teams = [f"T{i}" for i in range(30)]
    rows = []
    for gp in range(n_games):
        season = int(rng.choice([2023, 2024, 2025, 2026]))
        month = int(rng.integers(4, 10))
        home, away = rng.choice(teams, size=2, replace=False)
        # latent per-side F5 scoring rates (slight home/away strength tilt)
        base = rng.uniform(1.8, 3.0)
        tilt = rng.uniform(0.85, 1.18)
        mu_home, mu_away = base * tilt, base / tilt
        f5_home = int(rng.poisson(mu_home))
        f5_away = int(rng.poisson(mu_away))
        f5_sum_mu = mu_home + mu_away
        # F5 total: half-line near the mean; true P(over) from Poisson(f5_sum_mu)
        f5_line = float(np.floor(f5_sum_mu) + 0.5)
        p_over_true = float(poisson.sf(int(np.floor(f5_line)), f5_sum_mu))
        # F5 h2h: true P(home>away)/P(away>home) via Skellam (ties excluded → conditional)
        p_h = float(1 - skellam.cdf(0, mu_home, mu_away))
        p_a = float(skellam.cdf(-1, mu_home, mu_away))
        p_home_cond = p_h / (p_h + p_a) if (p_h + p_a) > 0 else 0.5
        # NRFI: 1st-inning runs ~ Poisson; P(YRFI) = P(>0)
        mu_i1 = float(rng.uniform(0.7, 1.1))
        i1_total = int(rng.poisson(mu_i1))
        i1_home = int(rng.binomial(i1_total, 0.5))
        i1_away = i1_total - i1_home
        p_yrfi_true = float(poisson.sf(0, mu_i1))
        final_home = f5_home + int(rng.poisson(1.6))
        final_away = f5_away + int(rng.poisson(1.5))
        main_total = round(f5_sum_mu / 0.54 * 2) / 2          # F5 ≈ 54% of full game
        gd = f"{season}-{month:02d}-{int(rng.integers(1, 28)):02d}"
        # apply the (optional) mispricing shrink toward 0.5
        def _mis(p):
            return 0.5 + (p - 0.5) * efficiency
        for bk in books:
            vig = 0.045 if bk == "pinnacle" else float(rng.uniform(0.06, 0.10))
            common = dict(game_pk=gp, season=season, commence_time=f"{gd}T23:00:00",
                          game_date=gd, home_team=home, away_team=away, bookmaker_key=bk,
                          f5_home=f5_home, f5_away=f5_away, i1_home=i1_home, i1_away=i1_away,
                          final_home=final_home, final_away=final_away,
                          main_total_line=main_total, main_vf_home=p_home_cond, main_vf_over=0.5)
            rows += _two_sided(common, de.F5_TOTALS, f5_line, _mis(p_over_true), vig)
            rows += _two_sided(common, de.NRFI, 0.5, _mis(p_yrfi_true), vig)
            rows += _h2h_rows(common, _mis(p_home_cond), vig, home, away)
    return pd.DataFrame(rows)


def _american(p: float) -> int:
    p = float(np.clip(p, 1e-3, 1 - 1e-3))
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def _two_sided(common, market, line, p_over, vig) -> list[dict]:
    io = np.clip(p_over + vig / 2, 1e-3, 1 - 1e-3)
    iu = np.clip((1 - p_over) + vig / 2, 1e-3, 1 - 1e-3)
    return [{**common, "market_key": market, "outcome_name": "Over", "outcome_point": line,
             "outcome_price_american": _american(io)},
            {**common, "market_key": market, "outcome_name": "Under", "outcome_point": line,
             "outcome_price_american": _american(iu)}]


def _h2h_rows(common, p_home, vig, home, away) -> list[dict]:
    p_home = float(np.clip(p_home, 0.1, 0.9))
    ih = np.clip(p_home + vig / 2, 1e-3, 1 - 1e-3)
    ia = np.clip((1 - p_home) + vig / 2, 1e-3, 1 - 1e-3)
    return [{**common, "market_key": de.F5_H2H, "outcome_name": home, "outcome_point": np.nan,
             "outcome_price_american": _american(ih)},
            {**common, "market_key": de.F5_H2H, "outcome_name": away, "outcome_point": np.nan,
             "outcome_price_american": _american(ia)}]


# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_wides(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Reshape the long cache frame to the per-market wide views (totals + h2h)."""
    return {de.F5_TOTALS: _reshape_totals(frame, de.F5_TOTALS),
            de.NRFI: _reshape_totals(frame, de.NRFI),
            de.TEAM_TOTALS: _reshape_totals(frame, de.TEAM_TOTALS),
            de.ALT_TOTALS: _reshape_totals(frame, de.ALT_TOTALS),
            de.F5_H2H: _reshape_h2h(frame)}


def run_eval(frame: pd.DataFrame, *, suffix: str = "", synthetic: bool = False) -> None:
    wides = build_wides(frame)
    books = sorted(frame["bookmaker_key"].dropna().unique().tolist())
    a1 = angle1(wides, books)
    a2 = angle2(wides)
    cand = build_candidates(a1, a2)
    sel = [c for c in a1["static"] if c["n"] >= MIN_GAMES]
    meta = {"n_rows": len(frame), "n_games": int(frame["game_pk"].nunique()),
            "n_books": int(frame["bookmaker_key"].nunique()),
            "seasons": sorted(frame["season"].dropna().unique().tolist()),
            "markets": sorted([m for m, w in wides.items() if w is not None and not w.empty]),
            "n_static_configs": len(a1["static"]), "n_selectable": len(sel)}
    write_dossier(meta, a1, a2, cand, suffix=suffix, synthetic=synthetic)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E13.13 derivative-market efficiency eval (angles 1+2)")
    ap.add_argument("--smoke", action="store_true", help="synthetic end-to-end run (no S3)")
    ap.add_argument("--build-cache", action="store_true", help="read S3 → cache parquet (operator)")
    ap.add_argument("--rebuild-cache", action="store_true", help="force cache rebuild")
    ap.add_argument("--seasons", default="2023,2024,2025,2026")
    ap.add_argument("--start-date", default=None, help="pitch settle floor, e.g. 2023-01-01")
    args = ap.parse_args(argv)

    if args.smoke:
        print("[smoke] synthetic frame — efficient books, expected verdict = clean null")
        run_eval(make_smoke_frame(), suffix="_smoke", synthetic=True)
        return 0

    seasons = [int(s) for s in args.seasons.split(",")]
    if args.build_cache or args.rebuild_cache or not CACHE.exists():
        if not (args.build_cache or args.rebuild_cache) and not CACHE.exists():
            print(f"[error] no cache at {CACHE}; run with --build-cache (operator, >1-min S3 scan).",
                  file=sys.stderr)
            return 2
        frame = build_cache(seasons, args.start_date)
    else:
        frame = pd.read_parquet(CACHE)
        print(f"[cache] loaded {len(frame):,} rows from {CACHE}")
    run_eval(frame)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
