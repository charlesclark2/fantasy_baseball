"""
bayesian_model_eval.py — reusable model-evaluation primitives.

This module is the importable home for evaluation logic that must run in two
places: (1) inside the offline three-layer Bayesian harness
(`evaluate_production_bayesian.py`, which imports the Layer-4 functions here),
and (2) as an operational monitor over live `daily_model_predictions` rows as
CLV labels accumulate.

Currently it hosts **Layer 4 — selective-strategy evaluation**: it formalizes the
manual betting rules that have been profitable in practice and measures whether a
model finds genuine edge *on the subset of games where a bet is triggered*, rather
than across all games indiscriminately. Layers 1–3 (prior-predictive NLL,
calibration, blended Brier) still live in `evaluate_production_bayesian.py` and
gate promotability; Layer 4 is an additional reporting layer.

The functions are deliberately pure: they take a normalized `games` DataFrame and
return plain dicts/DataFrames — no Snowflake, no model loading, no file I/O — so
the same code path runs on a stored OOS parquet and on live prediction rows.

--------------------------------------------------------------------------------
Canonical `games` schema
--------------------------------------------------------------------------------
Each row carries a `market` tag and the columns that market needs:

  market == "totals":
      model_mu        float   model's predicted total runs (NegBin/Normal loc)
      total_line      float   the book's total line (Bovada)
      actual_total    float   realized total runs (for win/loss + push)
      model_p_over    float   model P(over)  [optional; for no-bet Brier]
      market_p_over   float   de-vigged book P(over)  [optional; for no-bet Brier]

  market == "h2h":
      model_p_home    float   model P(home win)  (blended posterior)
      market_p_home   float   de-vigged book P(home win)
      home_win        int     realized outcome (1 home win, 0 away win)

Helpers `normalize_totals_parquet` / `normalize_h2h_frame` map source frames onto
this schema.

--------------------------------------------------------------------------------
ROI convention
--------------------------------------------------------------------------------
`roi_110` uses the standard -110 juice as the single comparable metric: a winning
bet earns +100, a losing bet costs -110, and ROI = total_profit / amount_risked
where amount_risked = 110 per bet. NOTE for H2H: real moneyline payouts vary by
price (underdogs pay more than +100), so `roi_110` understates the return on
winning underdog bets — it is a conservative, cross-market-comparable proxy, not
the realized book ROI. Totals at -110 are faithful.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Default thresholds + sweep grids (per spec).
DEFAULT_TOTALS_MU_THRESHOLD = 1.0
DEFAULT_H2H_MAGNITUDE_THRESHOLD = 0.12
TOTALS_THRESHOLD_GRID = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
H2H_THRESHOLD_GRID = (0.05, 0.08, 0.10, 0.12, 0.15, 0.20)
MIN_BETS_RELIABLE = 50  # below this, a sweep row is statistically unreliable
_UNCERTAINTY_ZONE = 0.5  # |model_mu - line| < this => "true uncertainty" abstain

# -110 juice payouts.
_WIN_PROFIT = 100.0
_LOSS_PROFIT = -110.0
_RISK_PER_BET = 110.0


# ---------------------------------------------------------------------------
# Per-game decision
# ---------------------------------------------------------------------------

def compute_bet_decision(
    market: str,
    *,
    model_mu: float | None = None,
    total_line: float | None = None,
    model_p_home: float | None = None,
    market_p_home: float | None = None,
    totals_mu_threshold: float = DEFAULT_TOTALS_MU_THRESHOLD,
    h2h_magnitude_threshold: float = DEFAULT_H2H_MAGNITUDE_THRESHOLD,
) -> tuple[str, str]:
    """Return ``(bet_decision, rule_type)`` for a single game.

    bet_decision ∈ {"over", "under", "home", "away", "abstain"}.
    rule_type    ∈ {"totals", "direction_flip", "magnitude", "abstain"}.

    Totals: bet over when ``model_mu - total_line > threshold``; under when
    ``< -threshold``; abstain inside the band.

    H2H (two distinct rules, evaluated separately downstream):
      * direction_flip — model and market disagree on the favorite → bet the
        model's favored team.
      * magnitude — they agree on the favorite but ``|model_p_home -
        market_p_home| > threshold`` → bet the model's favored team.
      * abstain otherwise.
    """
    if market == "totals":
        if model_mu is None or total_line is None or pd.isna(model_mu) or pd.isna(total_line):
            return "abstain", "abstain"
        diff = float(model_mu) - float(total_line)
        if diff > totals_mu_threshold:
            return "over", "totals"
        if diff < -totals_mu_threshold:
            return "under", "totals"
        return "abstain", "abstain"

    if market == "h2h":
        if (model_p_home is None or market_p_home is None
                or pd.isna(model_p_home) or pd.isna(market_p_home)):
            return "abstain", "abstain"
        mp, kp = float(model_p_home), float(market_p_home)
        model_fav = "home" if mp > 0.5 else ("away" if mp < 0.5 else None)
        mkt_fav = "home" if kp > 0.5 else ("away" if kp < 0.5 else None)
        if model_fav is None:
            return "abstain", "abstain"
        # Disagreement on the favorite → direction flip.
        if mkt_fav is not None and model_fav != mkt_fav:
            return model_fav, "direction_flip"
        # Agreement (or market pick'em) + sufficient probability gap → magnitude.
        if abs(mp - kp) > h2h_magnitude_threshold:
            return model_fav, "magnitude"
        return "abstain", "abstain"

    raise ValueError(f"unknown market: {market!r}")


def assign_decisions(
    games: pd.DataFrame,
    totals_mu_threshold: float = DEFAULT_TOTALS_MU_THRESHOLD,
    h2h_magnitude_threshold: float = DEFAULT_H2H_MAGNITUDE_THRESHOLD,
) -> pd.DataFrame:
    """Return a copy of ``games`` with ``bet_decision`` and ``rule_type`` columns."""
    g = games.copy()

    def _row(r):
        return compute_bet_decision(
            r["market"],
            model_mu=r.get("model_mu"),
            total_line=r.get("total_line"),
            model_p_home=r.get("model_p_home"),
            market_p_home=r.get("market_p_home"),
            totals_mu_threshold=totals_mu_threshold,
            h2h_magnitude_threshold=h2h_magnitude_threshold,
        )

    decisions = g.apply(_row, axis=1, result_type="expand")
    g["bet_decision"] = decisions[0]
    g["rule_type"] = decisions[1]
    return g


# ---------------------------------------------------------------------------
# Settlement (win / loss / push) and ROI
# ---------------------------------------------------------------------------

def _settle(r) -> float:
    """Return 1.0 (win), 0.0 (loss), or np.nan (push / unsettled) for one bet row."""
    d = r["bet_decision"]
    if d == "abstain":
        return np.nan
    if r["market"] == "totals":
        line, actual = r.get("total_line"), r.get("actual_total")
        if pd.isna(actual) or pd.isna(line):
            return np.nan
        if float(actual) == float(line):
            return np.nan  # push
        over = float(actual) > float(line)
        return float(over) if d == "over" else float(not over)
    # h2h
    y = r.get("home_win")
    if pd.isna(y):
        return np.nan
    return float(int(y) == 1) if d == "home" else float(int(y) == 0)


def _roi_110(results: np.ndarray) -> dict:
    """results: array of 1.0 (win) / 0.0 (loss); pushes already dropped."""
    n = int(len(results))
    if n == 0:
        return {"n_bets": 0, "win_rate": float("nan"), "roi_110": float("nan"),
                "wins": 0, "losses": 0, "profit": 0.0}
    wins = int(results.sum())
    losses = n - wins
    profit = wins * _WIN_PROFIT + losses * _LOSS_PROFIT
    return {
        "n_bets": n,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / n,
        "profit": profit,
        "roi_110": profit / (_RISK_PER_BET * n),
    }


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    m = ~np.isnan(p) & ~np.isnan(y)
    return float(np.mean((p[m] - y[m]) ** 2)) if m.any() else float("nan")


# ---------------------------------------------------------------------------
# Core selective-strategy evaluation
# ---------------------------------------------------------------------------

def evaluate_selective_strategy(
    games: pd.DataFrame,
    totals_mu_threshold: float = DEFAULT_TOTALS_MU_THRESHOLD,
    h2h_magnitude_threshold: float = DEFAULT_H2H_MAGNITUDE_THRESHOLD,
) -> dict:
    """Apply the betting rules at the given thresholds and summarize the edge.

    Returns a dict with overall bet/no-bet metrics plus per-market breakdowns:
      - overall:    n_games, n_bets, bet_rate, win_rate, roi_110
      - bet:        same, restricted to settled (non-push) bet games
      - no_bet:     n, market_brier, model_brier on abstained games (low-edge check)
      - totals:     over/under direction breakdown + uncertainty-zone analysis
      - h2h:        direction_flip vs magnitude breakdown
      - thresholds: echoed inputs
    """
    g = assign_decisions(games, totals_mu_threshold, h2h_magnitude_threshold)
    g["result"] = g.apply(_settle, axis=1)

    bet_mask = g["bet_decision"] != "abstain"
    settled = g[bet_mask & g["result"].notna()]
    pushes = int((bet_mask & g["result"].isna()).sum())

    overall = _roi_110(settled["result"].to_numpy(float))
    # De-vigged-odds ROI over settled H2H bets (NaN if none). This is the honest
    # gate metric for H2H, where roi_110 (flat -110) misprices favorites/underdogs.
    settled_h2h = settled[settled["market"] == "h2h"]
    roi_devig = _roi_devig_h2h(settled_h2h) if len(settled_h2h) else float("nan")
    out = {
        "thresholds": {
            "totals_mu_threshold": totals_mu_threshold,
            "h2h_magnitude_threshold": h2h_magnitude_threshold,
        },
        "n_games": int(len(g)),
        "n_pushes": pushes,
        "bet": {**overall, "roi_devig": roi_devig,
                "bet_rate": len(settled) / len(g) if len(g) else float("nan")},
    }

    # ---- No-bet (abstained) games: confirm low edge (market ≈ model) ----
    nb = g[g["bet_decision"] == "abstain"]
    out["no_bet"] = _no_bet_analysis(nb, totals_mu_threshold)

    # ---- Totals breakdown by direction ----
    tot = g[g["market"] == "totals"]
    if len(tot):
        out["totals"] = _totals_breakdown(tot, totals_mu_threshold)

    # ---- H2H breakdown by rule type ----
    h2h = g[g["market"] == "h2h"]
    if len(h2h):
        out["h2h"] = _h2h_breakdown(h2h)

    return out


def _no_bet_analysis(nb: pd.DataFrame, totals_mu_threshold: float) -> dict:
    res = {"n": int(len(nb))}
    if not len(nb):
        return res
    # Totals abstains: Brier of model vs market on the over outcome.
    nb_tot = nb[nb["market"] == "totals"].copy()
    if len(nb_tot) and {"model_p_over", "market_p_over"} <= set(nb_tot.columns):
        line = nb_tot["total_line"].to_numpy(float)
        actual = nb_tot["actual_total"].to_numpy(float)
        over_hit = np.where(actual == line, np.nan, (actual > line).astype(float))
        res["totals_model_brier"] = _brier(nb_tot["model_p_over"].to_numpy(float), over_hit)
        res["totals_market_brier"] = _brier(nb_tot["market_p_over"].to_numpy(float), over_hit)
        # Uncertainty zone: |mu - line| < 0.5 (genuine uncertainty) vs had-a-view-but-below-threshold.
        diff = np.abs(nb_tot["model_mu"].to_numpy(float) - line)
        in_zone = int((diff < _UNCERTAINTY_ZONE).sum())
        res["totals_n"] = int(len(nb_tot))
        res["totals_uncertainty_zone_n"] = in_zone
        res["totals_uncertainty_zone_frac"] = in_zone / len(nb_tot)
        res["totals_below_threshold_n"] = int(len(nb_tot)) - in_zone
        res["totals_below_threshold_frac"] = (len(nb_tot) - in_zone) / len(nb_tot)
    # H2H abstains: Brier of model vs market on home win.
    nb_h = nb[nb["market"] == "h2h"].copy()
    if len(nb_h):
        y = nb_h["home_win"].to_numpy(float)
        res["h2h_model_brier"] = _brier(nb_h["model_p_home"].to_numpy(float), y)
        res["h2h_market_brier"] = _brier(nb_h["market_p_home"].to_numpy(float), y)
        res["h2h_n"] = int(len(nb_h))
    return res


def _totals_breakdown(tot: pd.DataFrame, totals_mu_threshold: float) -> dict:
    settled = tot[tot["result"].notna() & (tot["bet_decision"] != "abstain")]
    res = {"n_games": int(len(tot)), **{f"all_{k}": v for k, v in
            _roi_110(settled["result"].to_numpy(float)).items()}}
    for side in ("over", "under"):
        s = settled[settled["bet_decision"] == side]
        res[side] = _roi_110(s["result"].to_numpy(float))
    return res


def _roi_devig_h2h(sub: pd.DataFrame) -> float:
    """ROI pricing each H2H bet at its DE-VIGGED fair odds (from market_p_home),
    instead of a flat -110. This corrects the -110 distortion that inflates
    favorite bets and deflates underdog bets: a win pays (1-p_side)/p_side, a loss
    -1, where p_side is the de-vigged market prob of the side actually bet. Under a
    perfectly-calibrated market this is 0 on ANY subset, so a positive value means
    the subset wins MORE than its own market price implied = genuine selection edge
    (vig-free, i.e. an optimistic upper bound on realized book ROI)."""
    if not len(sub) or "market_p_home" not in sub.columns:
        return float("nan")
    profits = []
    for dec, result, mph in zip(sub["bet_decision"], sub["result"], sub["market_p_home"]):
        p_side = float(mph) if dec == "home" else 1.0 - float(mph)
        if pd.isna(p_side) or p_side <= 0 or p_side >= 1:
            continue
        profits.append((1.0 - p_side) / p_side if result == 1.0 else -1.0)
    return float(np.mean(profits)) if profits else float("nan")


def _h2h_breakdown(h2h: pd.DataFrame) -> dict:
    settled = h2h[h2h["result"].notna() & (h2h["bet_decision"] != "abstain")]
    res = {"n_games": int(len(h2h)),
           **{f"all_{k}": v for k, v in _roi_110(settled["result"].to_numpy(float)).items()},
           "all_roi_devig": _roi_devig_h2h(settled)}
    for rule in ("direction_flip", "magnitude"):
        s = settled[settled["rule_type"] == rule]
        res[rule] = {**_roi_110(s["result"].to_numpy(float)), "roi_devig": _roi_devig_h2h(s)}
    return res


# ---------------------------------------------------------------------------
# Threshold sweep + optimal selection
# ---------------------------------------------------------------------------

def gate_metric_for(markets) -> str:
    """The ROI metric the Layer-4 gate uses, per market.

    Totals settle at -110 on both sides in the vast majority of cases, so roi_110
    is faithful there. H2H does NOT — moneyline prices vary by game, and a flat
    -110 inflates favorite (chalk) bets and deflates underdog bets. So a pure-H2H
    surface gates on roi_devig (each bet priced at its de-vigged fair odds); any
    surface containing totals gates on roi_110.
    """
    return "roi_devig" if set(markets) == {"h2h"} else "roi_110"


def sweep_thresholds(
    games: pd.DataFrame,
    totals_thresholds: tuple[float, ...] = TOTALS_THRESHOLD_GRID,
    h2h_thresholds: tuple[float, ...] = H2H_THRESHOLD_GRID,
    min_bets_reliable: int = MIN_BETS_RELIABLE,
) -> dict:
    """Run the full threshold sweep and pick the optimal combination.

    Markets present in ``games`` drive which threshold dimensions matter; absent
    markets leave their dimension inert (rows duplicate), so single-market data
    still produces a clean table. The gate metric is market-aware (see
    ``gate_metric_for``): totals → roi_110, H2H → roi_devig. The optimal row
    maximizes the gate metric among rows with ``gate_metric > 0`` and ``n_bets >=
    min_bets_reliable``; rows below the floor are flagged ``reliable=False``.
    """
    markets = set(games["market"].unique())
    gate = gate_metric_for(markets)
    tt_grid = totals_thresholds if "totals" in markets else (DEFAULT_TOTALS_MU_THRESHOLD,)
    ht_grid = h2h_thresholds if "h2h" in markets else (DEFAULT_H2H_MAGNITUDE_THRESHOLD,)

    table = []
    for tt in tt_grid:
        for ht in ht_grid:
            r = evaluate_selective_strategy(games, tt, ht)["bet"]
            table.append({
                "totals_threshold": tt,
                "h2h_threshold": ht,
                "n_bets": r["n_bets"],
                "bet_rate": r["bet_rate"],
                "win_rate": r["win_rate"],
                "roi_110": r["roi_110"],
                "roi_devig": r.get("roi_devig", float("nan")),
                "reliable": r["n_bets"] >= min_bets_reliable,
            })

    eligible = [row for row in table
                if row["reliable"] and pd.notna(row[gate]) and row[gate] > 0]
    optimal = max(eligible, key=lambda x: x[gate]) if eligible else None

    return {
        "table": table,
        "optimal": optimal,
        "gate_metric": gate,
        "min_bets_reliable": min_bets_reliable,
        "markets": sorted(markets),
    }


def layer4_verdict(sweep: dict) -> dict:
    """Layer-4 pass/fail: an optimal threshold exists with the (market-aware) gate
    metric > 0 AND n_bets >= min_bets_reliable. Totals gate on roi_110; H2H on
    roi_devig (de-vigged fair-odds ROI — the honest H2H edge test)."""
    opt = sweep.get("optimal")
    gate = sweep.get("gate_metric", "roi_110")
    passed = opt is not None
    return {
        "passed": passed,
        "gate_metric": gate,
        "optimal_totals_threshold": opt["totals_threshold"] if passed else None,
        "optimal_h2h_threshold": opt["h2h_threshold"] if passed else None,
        "n_bets": opt["n_bets"] if passed else None,
        "win_rate": opt["win_rate"] if passed else None,
        "roi_110": opt["roi_110"] if passed else None,
        "roi_devig": opt.get("roi_devig") if passed else None,
        "roi": opt[gate] if passed else None,
    }


# ---------------------------------------------------------------------------
# Source-frame normalizers
# ---------------------------------------------------------------------------

def normalize_totals_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Map an oos_predictions_totals_*.parquet frame onto the canonical schema."""
    out = pd.DataFrame({
        "market": "totals",
        "game_pk": df["game_pk"].astype(int) if "game_pk" in df else np.arange(len(df)),
        "season": df.get("season"),
        "model_mu": df["oos_mu"].astype(float),
        "total_line": df["bovada_line"].astype(float),
        "actual_total": df["actual_total_runs"].astype(float),
    })
    if "oos_p_over" in df:
        out["model_p_over"] = df["oos_p_over"].astype(float)
    if "bovada_devig_over_prob" in df:
        out["market_p_over"] = df["bovada_devig_over_prob"].astype(float)
    return out


def normalize_h2h_frame(
    df: pd.DataFrame,
    model_p_col: str = "model_p_home_win",
    market_p_col: str = "market_devig_home",
    outcome_col: str = "home_win",
) -> pd.DataFrame:
    """Map a leakage-free H2H OOS frame onto the canonical schema."""
    out = pd.DataFrame({
        "market": "h2h",
        "game_pk": df["game_pk"].astype(int) if "game_pk" in df else np.arange(len(df)),
        "season": df.get("season"),
        "model_p_home": df[model_p_col].astype(float),
        "market_p_home": df[market_p_col].astype(float),
        "home_win": df[outcome_col].astype(float),
    })
    return out


# ---------------------------------------------------------------------------
# Reporting (markdown table for a sweep)
# ---------------------------------------------------------------------------

def sweep_table_markdown(sweep: dict) -> list[str]:
    gate = sweep.get("gate_metric", "roi_110")
    lines = [f"_Gate metric: **{gate}** (⭐ = optimal by gate)._", "",
             "| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |",
             "|---:|---:|---:|---:|---:|---:|---:|:--:|"]
    opt = sweep.get("optimal")
    for row in sweep["table"]:
        is_opt = (opt is not None and row["totals_threshold"] == opt["totals_threshold"]
                  and row["h2h_threshold"] == opt["h2h_threshold"])
        mark = " ⭐" if is_opt else ""
        wr = f"{row['win_rate']:.3f}" if pd.notna(row["win_rate"]) else "—"
        roi = f"{row['roi_110']:+.4f}" if pd.notna(row["roi_110"]) else "—"
        rdv = f"{row['roi_devig']:+.4f}" if pd.notna(row.get("roi_devig", float("nan"))) else "—"
        lines.append(
            f"| {row['totals_threshold']:.2f} | {row['h2h_threshold']:.2f} | "
            f"{row['n_bets']}{mark} | {row['bet_rate']:.3f} | {wr} | {roi} | {rdv} | "
            f"{'✅' if row['reliable'] else '⚠️'} |")
    return lines


def selective_report_lines(label: str, games: pd.DataFrame) -> list[str]:
    """Full markdown block for one games set: sweep table, verdict, default-threshold
    breakdown, and no-bet analysis."""
    markets = sorted(set(games["market"].unique()))
    sw = sweep_thresholds(games)
    v = layer4_verdict(sw)
    out = [f"## {label}  (n_games={len(games)}, markets={markets})", ""]
    out += sweep_table_markdown(sw) + [""]
    gate = v["gate_metric"]
    if v["passed"]:
        caveat = (" — ⚠️ roi_devig is **vig-free (optimistic upper bound)**; a roi_devig PASS is "
                  "**evaluation-pending, NOT deployable** (real book ROI is lower, and the model "
                  "still fails L1/L3 vs the credible market)." if gate == "roi_devig" else "")
        out += [f"- **Layer 4: ✅ PASS** (gate={gate}) — optimal totals_thr="
                f"{v['optimal_totals_threshold']}, h2h_thr={v['optimal_h2h_threshold']}: "
                f"n_bets {v['n_bets']}, win_rate {v['win_rate']:.3f}, {gate} {v['roi']:+.4f}.{caveat}", ""]
    else:
        out += [f"- **Layer 4: ❌ FAIL** (gate={gate}) — no threshold with {gate}>0 AND "
                f"n_bets≥{MIN_BETS_RELIABLE}.", ""]
    d = evaluate_selective_strategy(games)
    if "totals" in d:
        tb, nb = d["totals"], d["no_bet"]
        out += ["**Totals @ default 1.0 run:**",
                f"- over: n={tb['over']['n_bets']} win_rate {tb['over']['win_rate']:.3f} "
                f"roi {tb['over']['roi_110']:+.4f}",
                f"- under: n={tb['under']['n_bets']} win_rate {tb['under']['win_rate']:.3f} "
                f"roi {tb['under']['roi_110']:+.4f}",
                f"- no-bet n={nb.get('totals_n', nb['n'])}: uncertainty-zone |μ−line|<0.5 frac "
                f"{nb.get('totals_uncertainty_zone_frac', float('nan')):.3f} "
                f"(n={nb.get('totals_uncertainty_zone_n')}); view-below-threshold frac "
                f"{nb.get('totals_below_threshold_frac', float('nan')):.3f}",
                f"- no-bet Brier: model {nb.get('totals_model_brier', float('nan')):.4f} vs "
                f"market {nb.get('totals_market_brier', float('nan')):.4f}", ""]
    if "h2h" in d:
        hb, nb = d["h2h"], d["no_bet"]
        out += ["**H2H @ default 0.12** (roi_110 = flat -110; roi_devig = priced at "
                "de-vigged fair odds, the honest edge test):",
                f"- direction_flip: n={hb['direction_flip']['n_bets']} win_rate "
                f"{hb['direction_flip']['win_rate']:.3f} roi_110 {hb['direction_flip']['roi_110']:+.4f} "
                f"roi_devig {hb['direction_flip']['roi_devig']:+.4f}",
                f"- magnitude: n={hb['magnitude']['n_bets']} win_rate "
                f"{hb['magnitude']['win_rate']:.3f} roi_110 {hb['magnitude']['roi_110']:+.4f} "
                f"roi_devig {hb['magnitude']['roi_devig']:+.4f}",
                f"- no-bet Brier: model {nb.get('h2h_model_brier', float('nan')):.4f} vs "
                f"market {nb.get('h2h_market_brier', float('nan')):.4f}", ""]
    return out


def main() -> None:
    import argparse
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    default_totals = root / "betting_ml" / "models" / "layer3" / "oos_predictions_totals_v1.parquet"
    out_dir = root / "quant_sports_intel_models" / "baseball" / "ablation_results"

    ap = argparse.ArgumentParser(description="Layer 4 selective-strategy evaluation (standalone)")
    ap.add_argument("--totals-parquet", default=str(default_totals),
                    help="oos_predictions_totals_*.parquet (model_mu=oos_mu, line=bovada_line)")
    ap.add_argument("--h2h-parquet", default=None,
                    help="leakage-free H2H OOS frame (model_p_home_win, market_devig_home, home_win)")
    ap.add_argument("--season", type=int, default=None, help="restrict to one season (e.g. 2026)")
    ap.add_argument("--out", default=str(out_dir / "layer4_selective_strategy.md"))
    args = ap.parse_args()

    blocks: list[pd.DataFrame] = []
    report = ["# Layer 4 — Selective Strategy (standalone OOS sweep)", "",
              "_Formalizes the manual betting rules and measures edge on the bet-triggered "
              "subset._", "",
              "**Gate-metric asymmetry (intentional):** Totals gate on **roi_110** — totals "
              "lines settle at -110 on both sides in the vast majority of cases, so flat -110 "
              "is faithful. H2H gates on **roi_devig** (each bet priced at its de-vigged fair "
              "odds) — moneyline prices vary by game, and a flat -110 *inflates* favorite/chalk "
              "bets (which pay < +100) and *deflates* underdog bets (which pay > +100). roi_devig "
              "is 0 under a perfectly-calibrated market, so a positive value means the bet side "
              "beat its own market price = genuine selection edge — but it is **vig-free**, i.e. "
              "an optimistic upper bound on realized book ROI.", ""]

    if args.totals_parquet and Path(args.totals_parquet).exists():
        tdf = pd.read_parquet(args.totals_parquet)
        gt = normalize_totals_parquet(tdf)
        report += selective_report_lines(f"Totals — ALL seasons ({Path(args.totals_parquet).name})", gt)
        if "season" in gt.columns:
            for s in sorted(x for x in gt["season"].dropna().unique()):
                report += selective_report_lines(f"Totals — season {int(s)} only", gt[gt["season"] == s])
        blocks.append(gt)

    if args.h2h_parquet and Path(args.h2h_parquet).exists():
        hdf = pd.read_parquet(args.h2h_parquet)
        gh = normalize_h2h_frame(hdf)
        report += selective_report_lines(f"H2H — ALL seasons ({Path(args.h2h_parquet).name})", gh)
        if "season" in gh.columns:
            for s in sorted(x for x in gh["season"].dropna().unique()):
                report += selective_report_lines(f"H2H — season {int(s)} only", gh[gh["season"] == s])
        blocks.append(gh)

    if args.season is not None and blocks:
        combined = pd.concat([b[b.get("season") == args.season] for b in blocks], ignore_index=True)
        if len(combined):
            report += selective_report_lines(f"COMBINED (totals+h2h) — season {args.season}", combined)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
