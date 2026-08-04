"""run_nf_c0e_captured_terms.py — the held-out DEGENERATE-BASELINE gate every NF-C0e term faced.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_c0e_captured_terms \
        --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --out ablation_results

🎯 WHAT THIS DECIDES. NF-C0's coverage machinery reports a scoring term CAPTURED when no projection
column backs it. That is honest, but it is a TODO. This script decides which captured terms are
allowed to become APPLIED, and it is deliberately the ONLY way one may: a term projected with no
skill still MOVES the board — it just moves it on noise while wearing the "applied" label, which is
strictly worse than an honest "captured", because the user now believes we modelled it.

⚖️ THE GATE. For each candidate, walk forward season by season: fit strictly on prior seasons,
project the held-out season, and score against realized outcomes. A term graduates only if it beats
a DEGENERATE arm on BOTH mean-absolute and root-mean-square error, in enough folds to satisfy
`cv_power.fold_consistency_clause` (a calibrated sign test — the legacy `>=60% of folds` clause is
nearly free at small fold counts).

Requiring BOTH losses is the load-bearing part, not caution. These targets are heavily zero-inflated
and MAE on a zero-heavy target is minimised at the CONDITIONAL MEDIAN, so it PAYS FOR PESSIMISM and
can rank a systematically under-projecting arm first (the NF-D11 inversion). `fum` is the term that
actually tripped it: it wins MAE in 7/7 held-out seasons and loses RMSE in 7/7.

🧭 THE TWO ANCHORS, both required and both reported (E2.1-r / NF1.7 (a) / NF-D11):
  * DEGENERATE CEILING — a trivial arm that MUST LOSE. For a team family, every team gets the
    league-mean rate; for a player term, every player gets his position's in-fold mean. A real
    candidate scoring WORSE than this means the metric is inverted, not that the term is good.
  * ORACLE FLOOR — the same form fed the REALIZED season rate. Nothing honest may beat it. It is
    same-family and same-n by construction (NF1.7 (b)), so "peeking can only help" actually holds.

🔬 AND A CONTROL FAMILY. The yards-allowed family is scored beside POINTS allowed — the tier family
NF1.6 already ships — through the identical harness. Without it, "beats the degenerate by 9%" is a
number with nothing to calibrate against; with it, we can say the new family's held-out margin is
LARGER than that of one the program already serves.

⚖️ HONEST FRAME: this is a projection product, not an edge claim — no `best_alpha`, no PBO/DSR.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import kdst_projection as KD
from quant_sports_intel_models.football.nfl.fantasy import kdst_source as KS

log = logging.getLogger("nfl.fantasy.nf_c0e")

WINDOW, DECAY = KD.PRIOR_WINDOW_YEARS, KD.PRIOR_RECENCY_DECAY

# The two REAL league tier tables NF-C0d's telemetry surfaced, used as the scoring metric. Scoring
# the family under an INVENTED table would make the margin a property of our own weights.
SLEEPER_YA_TIER = (6.0, 4.0, 2.0, 1.0, 0.0, -2.0, -4.0, -6.0, -6.0)
ESPN_YA_TIER = (5.0, 3.0, 2.0, 0.0, -1.0, -3.0, -5.0, -6.0, -7.0)
ESPN_PA_TIER = tuple(KD.DST_PA_TIER_POINTS[b] for b in KD.PA_BUCKET_LABELS)


def _prior_rate(ts: pd.DataFrame, base_season: int, tot_col: str, games_col: str) -> pd.DataFrame:
    """Recency + games weighted per-game rate over the `WINDOW` seasons ending at `base_season`."""
    lo = base_season - WINDOW + 1
    h = ts[(ts["season"] >= lo) & (ts["season"] <= base_season)].copy()
    if h.empty:
        return pd.DataFrame({"team": [], "prior": []})
    h["_w"] = np.power(DECAY, base_season - h["season"]) * h[games_col]
    g = h.groupby("team").apply(
        lambda d: (np.sum((d[tot_col] / d[games_col]) * d["_w"]) / np.sum(d["_w"])
                   if np.sum(d["_w"]) > 0 else np.nan),
        include_groups=False)
    return g.rename("prior").reset_index()


def evaluate_tier_family(games: pd.DataFrame, ts: pd.DataFrame, *, value_col: str, rate_col: str,
                         tot_col: str, edges: tuple, labels: tuple, tables: dict,
                         first_season: int, last_season: int) -> pd.DataFrame:
    """Walk-forward evaluation of a per-game TIER family (points allowed / yards allowed)."""
    idx = KD.bucket_index(games[value_col], edges)
    realized = (games.assign(_b=idx)
                .pivot_table(index=["season", "team"], columns="_b", values="week", aggfunc="count")
                .reindex(columns=range(len(labels))).fillna(0.0))
    realized.columns = list(labels)
    realized = realized.reset_index()

    rows = []
    for y in range(int(first_season), int(last_season) + 1):
        h_ts, h_g = ts[ts["season"] <= y - 1], games[games["season"] <= y - 1]
        if h_ts["season"].nunique() < 5:
            continue
        panel = []
        for ty in sorted(h_ts["season"].unique()):
            if ty - 1 < h_ts["season"].min():
                continue
            cur = h_ts[h_ts["season"] == ty][["team", tot_col, "team_games"]].copy()
            cur["real"] = cur[tot_col] / cur["team_games"]
            panel.append(cur.merge(_prior_rate(h_ts, ty - 1, tot_col, "team_games"),
                                   on="team", how="left"))
        panel = pd.concat(panel, ignore_index=True).dropna(subset=["prior", "real"])
        if len(panel) < 30:
            continue
        slope, intercept = np.polyfit(panel["prior"], panel["real"], 1)
        league_mean = float(panel["real"].mean())
        if slope <= 0:            # a negative slope is noise, not an anti-signal worth serving
            slope, intercept = 0.0, league_mean
        mix = KD.fit_conditional_bucket_mix(h_g, h_ts, value_col=value_col, rate_col=rate_col,
                                            edges=edges, labels=labels)

        tgt = (realized[realized["season"] == y][["team", *labels]]
               .merge(_prior_rate(h_ts, y - 1, tot_col, "team_games"), on="team", how="left")
               .merge(ts[ts["season"] == y][["team", "team_games", tot_col]], on="team", how="left"))
        if tgt.empty:
            continue
        p = tgt["prior"].to_numpy(float)
        gm = tgt["team_games"].to_numpy(float)
        arms = {
            "projection": np.where(np.isfinite(p), intercept + slope * p, league_mean),
            "degenerate_league_mean": np.full(len(tgt), league_mean),
            "oracle_floor": (tgt[tot_col] / tgt["team_games"]).to_numpy(float),
        }
        R = tgt[list(labels)].to_numpy(float)
        for tname, weights in tables.items():
            w = np.asarray(weights, float)
            y_true = R @ w
            rec = {"season": y, "table": tname, "n": int(len(tgt)), "slope": float(slope)}
            for arm, rate in arms.items():
                y_hat = (KD.expected_bucket_games(rate, gm, mix)) @ w
                rec[f"mae_{arm}"] = float(np.mean(np.abs(y_hat - y_true)))
                rec[f"rmse_{arm}"] = float(np.sqrt(np.mean((y_hat - y_true) ** 2)))
                rec[f"rho_{arm}"] = float(pd.Series(y_hat).corr(pd.Series(y_true),
                                                                method="spearman"))
            rows.append(rec)
    return pd.DataFrame(rows)


def verdict(d: pd.DataFrame, arm: str = "projection",
            degen: str = "degenerate_league_mean") -> dict:
    """The graduate/stay-captured decision, and every number it rests on."""
    n = len(d)
    clause = cv_power.fold_consistency_clause(n)
    mae_wins = int((d[f"mae_{arm}"] < d[f"mae_{degen}"] - 1e-12).sum())
    rmse_wins = int((d[f"rmse_{arm}"] < d[f"rmse_{degen}"] - 1e-12).sum())
    mp, md = float(d[f"mae_{arm}"].mean()), float(d[f"mae_{degen}"].mean())
    rp, rd = float(d[f"rmse_{arm}"].mean()), float(d[f"rmse_{degen}"].mean())
    oracle_ok = True
    if f"mae_oracle_floor" in d.columns:
        oracle_ok = bool(float(d["mae_oracle_floor"].mean()) <= mp)
    return {
        "folds": n,
        "mae": round(mp, 4), "mae_degenerate": round(md, 4),
        "mae_gain_pct": round(100 * (1 - mp / md), 2) if md else 0.0,
        "rmse": round(rp, 4), "rmse_degenerate": round(rd, 4),
        "rmse_gain_pct": round(100 * (1 - rp / rd), 2) if rd else 0.0,
        "mae_fold_wins": mae_wins, "rmse_fold_wins": rmse_wins,
        "folds_required": clause.wins_required,
        "clause_false_fire_rate": round(clause.attained_false_fire, 4),
        "oracle_floor_respected": oracle_ok,
        "degenerate_loses": bool(mp < md and rp < rd),
        "mean_rank_corr": round(float(d[f"rho_{arm}"].mean()), 4),
        # ⚠️ REPORTED, NOT GATED ON. This window was chosen AFTER seeing the season table, so
        # selecting on it would be the post-hoc trim MH2 warns about ("you get to PRE-REGISTER a
        # family, you do not get to DISCOVER one") applied to a time window. It is published
        # because a reader deserves it, and because it is the re-validation trigger.
        "last3_rank_corr": round(float(d.tail(3)[f"rho_{arm}"].mean()), 4),
        "GRADUATES": bool(mp < md and rp < rd
                          and clause.passes(mae_wins) and clause.passes(rmse_wins)
                          and oracle_ok),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--from-season", type=int, default=1999)
    ap.add_argument("--first-eval", type=int, default=2010)
    ap.add_argument("--last-eval", type=int, default=2025)
    ap.add_argument("--out", default="ablation_results")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")
    import duckdb
    con = duckdb.connect(args.duckdb, read_only=True)

    gy = KS.load_team_game_yards(con, args.from_season, args.last_eval)
    ty = KS.load_team_yards(con, args.from_season, args.last_eval)
    gp = KS.load_team_game_points(con, args.from_season, args.last_eval)
    tp = KS.load_team_points(con, args.from_season, args.last_eval)

    ya = evaluate_tier_family(
        gy, ty, value_col="yards_against", rate_col="yards_against_pg", tot_col="yards_against",
        edges=KD.YA_BUCKET_EDGES, labels=KD.YA_BUCKET_LABELS,
        tables={"sleeper": SLEEPER_YA_TIER, "espn": ESPN_YA_TIER},
        first_season=args.first_eval, last_season=args.last_eval)
    pa = evaluate_tier_family(
        gp.rename(columns={"points_against": "points_against"}), tp,
        value_col="points_against", rate_col="points_against_pg", tot_col="points_against",
        edges=KD.PA_BUCKET_EDGES, labels=KD.PA_BUCKET_LABELS,
        tables={"espn_shipped_CONTROL": ESPN_PA_TIER},
        first_season=args.first_eval, last_season=args.last_eval)

    out: dict = {"family": {}}
    for name, frame in (("yards_allowed", ya), ("points_allowed_CONTROL", pa)):
        for table in frame["table"].unique():
            d = frame[frame["table"] == table].reset_index(drop=True)
            out["family"][f"{name}/{table}"] = verdict(d)
            log.info("%s/%s → %s", name, table,
                     "GRADUATES" if out["family"][f"{name}/{table}"]["GRADUATES"] else "REJECTED")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nf_c0e_tier_family_gate.json").write_text(json.dumps(out, indent=2))
    pd.concat([ya.assign(family="yards_allowed"), pa.assign(family="points_allowed_CONTROL")]) \
        .to_csv(out_dir / "nf_c0e_tier_family_folds.csv", index=False)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
