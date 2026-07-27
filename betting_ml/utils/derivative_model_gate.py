"""derivative_model_gate.py — Edge Program Story E2.6: the model-vs-market derivative gate (pure).

E13.13 asked "is the derivative market EFFICIENT vs its own de-vigged price?" (angles 1+2, NO
model → CLEAN NULL). **E2.6 is angle 3:** does OUR market-blind model — the E2.5 per-side NegBin
marginals (`totals_generative_v1`) convolved into the honest game-total distribution (E2.2/E2.3,
ρ=0) — DISAGREE with the derivative's CLOSING line in a way that a *beat-the-close* backtest
rewards? We price each derivative (team-total / alt-total / full total) from the convolved
distribution, de-vig its close, bet the model's disagreement, and settle the realized PnL AT THE
CLOSE net of the derivative's own vig.

THE HONEST BAR (baked into every output):
  * **Beating the CLOSE is the strongest cashability test there is** — the close is the sharpest
    number the book posts. History carries only CLOSES (E2.0), so the historical gate is
    realized ROI net of vig at the close, scored GAME-level. (True bet-time-vs-close CLV needs
    the E2.0b forward stream; the same harness runs on it once accumulated.)
  * **Collapse correlated book-quotes to ONE game-level return BEFORE significance/PBO/DSR** — the
    E13.13 lesson: 15 books on one game are one correlated bet, not 15; counting quotes inflates
    a fake edge out of the multiple-comparison surface.
  * **A market is a CANDIDATE only if it clears every deflated leg** (game-level ROI>0 net of vig
    + season-sign-consistent + BH-FDR across the whole config grid + PBO<0.2 + DSR≥0.95). With
    `best_alpha=0`, MLB main-market efficiency (E13.8), E5.4's null, and E13.13's null, a CLEAN
    NULL (no derivative beats its own close after deflation) is the likely AND fully-valid result.
    Report the deflated number honestly; never manufacture a survivor.

⛔ MARKET-BLIND (architecture Principle 3): the model prices come from `totals_generative_v1`,
which took ZERO market features. Market data enters ONLY here, at the eval/CLV-gating layer.

Pure NumPy/SciPy + the program's shared primitives (so the de-vig / settlement / PBO-DSR match
everywhere) — no Snowflake, no model state, fully unit-tested. The orchestration
(`betting_ml/scripts/derivative_eval/eval_derivative_model_gate.py`) reads the cached S3 frame,
scores the served signal, runs this gate per market, and writes the dossier.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.utils.derivative_eval import bh_fdr, book_mask
from betting_ml.utils.overfitting import (
    DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE, deflated_sharpe, pbo_cscv,
)
from betting_ml.utils.prop_gate import payoff_vec
from betting_ml.utils.totals_distribution import (
    derive_distributions, draw_independent_samples,
)

# ── Markets this gate prices from the FULL-GAME per-side model ──────────────────────────────────
# team_totals  : P(that team's total > line)          ← the per-side marginal (home_total/away_total)
# alternate_totals : P(game total > alt line)         ← the convolved total at off-market lines
# totals (main): P(game total > line)                 ← the convolved total (anchor / E2.3 surface)
TEAM_TOTALS = "team_totals"
ALT_TOTALS = "alternate_totals"
MAIN_TOTALS = "totals"
FULLGAME_MARKETS = (TEAM_TOTALS, ALT_TOTALS, MAIN_TOTALS)

# ── Pre-registered gate grid (fixed BEFORE looking at any outcome) ──────────────────────────────
# Conviction thresholds on the model-vs-close edge (probability points). Mirrors prop_gate.TAU_GRID.
TAU_GRID: tuple[float, ...] = (0.02, 0.03, 0.04, 0.06, 0.08)
# Totals line buckets (full-game total lines cluster 7–11; team-totals 3–5.5).
LINE_BUCKETS: dict[str, tuple[float | None, float | None]] = {
    "all": (None, None),
    "low": (None, 7.5),
    "mid": (8.0, 9.5),
    "high": (10.0, None),
}
BOOK_GROUPS = ("all", "pinnacle", "soft", "majors")
MIN_GAMES = 50          # a config needs ≥ this many unique GAMES to be selectable
FRAGILE_GAMES = 250     # a surviving candidate below this is flagged FRAGILE
FDR_Q = 0.10
DEFAULT_N_DRAWS = 5_000
_EPS = 1e-9


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Model pricing — convolve the per-side NegBin marginals → P(over line)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def price_game_samples(
    mu_home: np.ndarray, mu_away: np.ndarray, r_home: float, r_away: float,
    rng: np.random.Generator, *, n_draws: int = DEFAULT_N_DRAWS,
) -> dict[str, np.ndarray]:
    """Convolve the per-side NegBin marginals (E2.2/E2.3 independent, ρ=0) → per-game sample arrays.

    Returns {'total','home_total','away_total'} each (n_games, n_draws). `mu_home`/`mu_away` are the
    E2.5 served per-side means (`totals_perside_mu_v1`, home/away); `r_home`/`r_away` the E2.3
    held-out-calibrated dispersions (NOT the artifact train-fit r — that re-introduces the ~24%
    variance deficit E2.3 fixed). This is the SAME machinery E2.3 calibrated + E2.5 serves."""
    y_home, y_away = draw_independent_samples(
        np.asarray(mu_home, float), np.asarray(mu_away, float),
        float(r_home), rng, r_away=float(r_away), n_draws=n_draws,
    )
    dist = derive_distributions(y_home, y_away)
    return {"total": dist["total"], "home_total": dist["home_total"],
            "away_total": dist["away_total"]}


def prob_over_at_lines(
    samples_by_kind: dict[str, np.ndarray], game_index: np.ndarray,
    kind: np.ndarray, line: np.ndarray, *, chunk: int = 4_000,
) -> np.ndarray:
    """Model P(outcome > line) per row, looking each row's game/kind sample array up by position.

    `game_index` maps each row to its row in the (n_games, n_draws) arrays; `kind` selects
    total/home_total/away_total per row; `line` is the row's betting line. Chunked so the
    (rows × n_draws) boolean never blows memory. Integer-line PUSH mass is handled by the caller's
    settlement (a strict `>` here = the model's P(over), the quantity compared to the de-vig fair)."""
    n = len(game_index)
    out = np.full(n, np.nan)
    gi = np.asarray(game_index)
    ln = np.asarray(line, float)
    kd = np.asarray(kind, dtype=object)
    for start in range(0, n, chunk):
        sl = slice(start, min(start + chunk, n))
        for k in ("total", "home_total", "away_total"):
            m = (kd[sl] == k)
            if not m.any():
                continue
            S = samples_by_kind[k]                      # (n_games, n_draws)
            rows = S[gi[sl][m]]                          # (n_sel, n_draws)
            out[np.arange(start, min(start + chunk, n))[m]] = (
                rows > ln[sl][m][:, None]).mean(axis=1)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Bet construction — model disagrees with the de-vigged close by ≥ τ
# ════════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class DerivConfig:
    """One pre-registered model-vs-close betting strategy over a derivative market.

    market ∈ FULLGAME_MARKETS; book_group ∈ {all,pinnacle,soft,majors,<book>}; line_bucket a key of
    LINE_BUCKETS; tau the minimum |model_p − fair_close_p| (prob points) to bet. Selection is a pure
    function of (model, close) columns — it NEVER touches the realized outcome."""
    market: str
    book_group: str
    line_bucket: str
    tau: float

    @property
    def name(self) -> str:
        return f"{self.market}|{self.book_group}|{self.line_bucket}|tau{self.tau:g}"


def make_config_grid(market: str, books: list[str]) -> list[DerivConfig]:
    """Full pre-registered grid for one market = book-group × line-bucket × tau (deterministic; no
    outcome peek). Each real book is tested individually too, so every cell feeds the deflation."""
    groups = list(BOOK_GROUPS) + [b for b in sorted(books) if b not in BOOK_GROUPS]
    return [DerivConfig(market, g, lb, tau)
            for g in groups for lb in LINE_BUCKETS for tau in TAU_GRID]


def _line_mask(line: np.ndarray, bucket: str) -> np.ndarray:
    lo, hi = LINE_BUCKETS[bucket]
    ln = np.asarray(line, float)
    m = np.ones(len(ln), bool)
    if lo is not None:
        m &= ln >= lo
    if hi is not None:
        m &= ln <= hi
    return m


def select_bets(df: pd.DataFrame, cfg: DerivConfig) -> pd.DataFrame:
    """Rows the config BETS, with `bet_side`/`bet_price`/`edge` attached.

    `df` (already filtered to `cfg.market`) must carry: game_pk, bookmaker_key, line, over_price,
    under_price, fair_over (de-vig close P(over)), model_p_over, devig_valid, plus the realized
    settlement columns. Bet OVER when model_p_over − fair_over ≥ τ, UNDER when fair_over − model_p_over
    ≥ τ. Pure selection — never reads the outcome."""
    base = (df["devig_valid"].to_numpy(bool)
            & book_mask(df["bookmaker_key"].to_numpy(object), cfg.book_group)
            & _line_mask(df["line"].to_numpy(float), cfg.line_bucket))
    edge = df["model_p_over"].to_numpy(float) - df["fair_over"].to_numpy(float)  # +→over cheap
    finite = np.isfinite(edge)
    bet = base & finite & (np.abs(edge) >= cfg.tau)
    out = df.loc[bet].copy()
    if out.empty:
        for c, dt in (("bet_side", object), ("bet_price", float), ("edge", float)):
            out[c] = pd.Series(dtype=dt)
        return out
    e = edge[bet]
    side = np.where(e >= 0, "over", "under").astype(object)
    out["bet_side"] = side
    out["bet_price"] = np.where(side == "over", out["over_price"].to_numpy(float),
                                out["under_price"].to_numpy(float))
    out["edge"] = e
    return out


def game_level_returns(bet_rows: pd.DataFrame) -> pd.DataFrame:
    """Collapse correlated book-quotes → ONE realized return per game (the E13.13 anti-clustering
    rule). Each row's per-$1 PnL is settled at its OWN close price net of vig (`bet_payoff`), then
    averaged across every quote bet on that game_pk. Returns a per-game frame with p / season / ym /
    mean model edge. An empty input → empty frame."""
    if bet_rows.empty:
        return pd.DataFrame(columns=["game_pk", "p", "season", "ym", "edge"])
    pay = payoff_vec(bet_rows["actual_total"].to_numpy(float), bet_rows["line"].to_numpy(float),
                     bet_rows["bet_side"].to_numpy(object), bet_rows["bet_price"].to_numpy(float))
    if "game_date" in bet_rows.columns and bet_rows["game_date"].notna().any():
        ym = pd.to_datetime(bet_rows["game_date"], errors="coerce").dt.strftime("%Y-%m")
    else:
        ym = bet_rows["season"].astype("Int64").astype(str)
    q = pd.DataFrame({"game_pk": bet_rows["game_pk"].to_numpy(), "p": pay,
                      "season": bet_rows["season"].to_numpy(), "ym": ym.to_numpy(),
                      "edge": bet_rows["edge"].to_numpy(float)})
    q = q[np.isfinite(q["p"].to_numpy())]
    if q.empty:
        return pd.DataFrame(columns=["game_pk", "p", "season", "ym", "edge"])
    return (q.groupby("game_pk")
            .agg(p=("p", "mean"), season=("season", "first"), ym=("ym", "first"),
                 edge=("edge", "mean")).reset_index())


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Per-config scoring + per-market deflated verdict
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _upper_tail_p(mean: float, sd: float, n: int) -> float:
    """One-sided p-value that game-level ROI > 0 (normal approx)."""
    from math import erfc, sqrt
    if not (sd > 0 and n > 1):
        return float("nan")
    t = mean / (sd / np.sqrt(n))
    return float(0.5 * erfc(t / sqrt(2.0)))


def score_config(df_market: pd.DataFrame, cfg: DerivConfig) -> dict | None:
    """Score one config GAME-level: ROI net of vig, Sharpe, per-season/per-ym, roi_p, mean model
    edge. `None` when nothing is bet. `_payoffs` is the game-level series (used by DSR)."""
    games = game_level_returns(select_bets(df_market, cfg))
    if games.empty:
        return None
    g = games["p"].to_numpy(float)
    n = len(g)
    sd = g.std(ddof=1) if n > 1 else 0.0
    per_season = {str(s): float(gg["p"].mean()) for s, gg in games.groupby("season")}
    per_ym = {str(y): float(gg["p"].mean()) for y, gg in games.groupby("ym")}
    signs = [np.sign(v) for v in per_season.values()]
    return {
        "name": cfg.name, "market": cfg.market, "book_group": cfg.book_group,
        "line_bucket": cfg.line_bucket, "tau": cfg.tau, "n": n,
        "roi": float(g.mean()), "sharpe": float(g.mean() / sd) if sd > 0 else 0.0,
        "roi_p": _upper_tail_p(float(g.mean()), float(sd), n),
        "mean_edge": float(games["edge"].mean()),
        "per_season": per_season, "per_ym": per_ym,
        "season_sign_consistent": bool(len(signs) >= 2 and len(set(signs)) == 1 and signs[0] != 0),
        "roi_fdr_survive": False, "_payoffs": g,
    }


def deflate_grid(configs: list[dict]) -> tuple[dict, dict]:
    """PBO (CSCV over year-month slices × selectable configs) + DSR on the in-sample-best config,
    deflated by the selectable-config count (the multiple-comparison surface)."""
    sel = [c for c in configs if c["n"] >= MIN_GAMES]
    if len(sel) < 2:
        return ({"pbo": float("nan"), "note": f"only {len(sel)} selectable configs (need ≥2)"},
                {"dsr": float("nan"), "note": "no selectable config"})
    yms = sorted({ym for c in sel for ym in c["per_ym"]})
    if len(yms) < 4:
        pbo = {"pbo": float("nan"), "note": f"only {len(yms)} ym slices (need ≥4)"}
    else:
        mat = np.array([[c["per_ym"].get(ym, np.nan) for c in sel] for ym in yms], float)
        dense = ~np.isnan(mat).any(axis=0)
        if dense.sum() >= 2:
            res = pbo_cscv(mat[:, dense], higher_is_better=True,
                           n_splits=min(16, len(yms)), max_combos=2000)
            pbo = {"pbo": res.pbo, "n_combos": res.n_combos, "n_configs": int(dense.sum()),
                   "n_splits": res.n_splits, "clears_live_pbo": bool(res.clears_live_pbo)}
        else:
            pbo = {"pbo": float("nan"), "note": "no config dense across all ym slices"}
    best = max(sel, key=lambda c: c["roi"])
    if len(best["_payoffs"]) >= 3:
        d = deflated_sharpe(best["_payoffs"], n_trials=len(sel),
                            trial_sharpes=[c["sharpe"] for c in sel])
        dsr = {"dsr": d.dsr, "observed_sr": d.observed_sr, "sr0": d.sr0, "n_obs": d.n_obs,
               "n_trials": d.n_trials, "passes_live": bool(d.passes_live),
               "best_config": best["name"], "best_roi": best["roi"]}
    else:
        dsr = {"dsr": float("nan"), "note": "best config <3 games"}
    return pbo, dsr


def evaluate_market(df_market: pd.DataFrame, market: str, books: list[str]) -> dict:
    """Full model-vs-close gate for one market: score every pre-registered config game-level, apply
    BH-FDR across the grid's ROI tests, deflate with PBO + DSR, and emit a per-market verdict +
    CLEAN candidate flags. Empty/absent market → an explicit empty result (never a silent pass)."""
    if df_market is None or df_market.empty:
        return {"market": market, "present": False, "configs": [], "n_selectable": 0,
                "pbo": {"pbo": float("nan")}, "dsr": {"dsr": float("nan")},
                "fdr": {"n_survive": 0, "n_tested": 0}, "candidates": [],
                "verdict": "ABSENT — no closes for this market in S3"}
    grid = make_config_grid(market, books)
    configs = [c for c in (score_config(df_market, cfg) for cfg in grid) if c is not None]
    sel = [c for c in configs if c["n"] >= MIN_GAMES]
    fdr = bh_fdr([c["roi_p"] for c in sel], q=FDR_Q)
    for c, surv in zip(sel, fdr["survive"]):
        c["roi_fdr_survive"] = bool(surv)
    pbo, dsr = deflate_grid(configs)
    pbo_ok = np.isfinite(pbo.get("pbo", np.nan)) and pbo["pbo"] < PBO_SHADOW_TO_LIVE
    dsr_ok = np.isfinite(dsr.get("dsr", np.nan)) and dsr["dsr"] >= DSR_CONFIDENCE

    # A market cell is a CANDIDATE only if EVERY deflated leg clears (dedup overlapping book-groups
    # per (line_bucket, tau) so the same games aren't triple-counted across all/soft/majors).
    raw = [c for c in sel if c["roi"] > 0 and c["season_sign_consistent"]
           and c["roi_fdr_survive"] and pbo_ok and dsr_ok]
    by_signal: dict[tuple, list] = defaultdict(list)
    for c in raw:
        by_signal[(c["line_bucket"], c["tau"])].append(c)
    candidates = []
    for (lb, tau), group in by_signal.items():
        best = max(group, key=lambda c: c["n"])
        candidates.append({
            "name": f"{market}|{lb}|tau{tau:g}", "n": best["n"], "roi_net_vig": best["roi"],
            "roi_p": best["roi_p"], "mean_edge": best["mean_edge"],
            "per_season_roi": {k: round(v, 4) for k, v in best["per_season"].items()},
            "book_groups": sorted({c["book_group"] for c in group}),
            "fragile": bool(best["n"] < FRAGILE_GAMES),
            "grid_pbo_lt_0p2": bool(pbo_ok), "grid_dsr_ge_0p95": bool(dsr_ok)})

    n_fragile = sum(1 for c in candidates if c["fragile"])
    if not candidates:
        verdict = "CLEAN NULL — no config beats the close after deflation"
    elif n_fragile == len(candidates):
        verdict = f"NO ROBUST EDGE — {len(candidates)} FRAGILE thin-sample candidate(s)"
    else:
        verdict = f"CANDIDATE(S) — {len(candidates) - n_fragile} robust + {n_fragile} fragile"
    return {"market": market, "present": True, "configs": configs, "n_selectable": len(sel),
            "pbo": pbo, "dsr": dsr, "fdr": {"threshold": fdr["threshold"],
            "n_survive": fdr["n_survive"], "n_tested": fdr["n_tested"], "q": FDR_Q},
            "candidates": candidates, "n_fragile": n_fragile, "verdict": verdict}


__all__ = [
    "TEAM_TOTALS", "ALT_TOTALS", "MAIN_TOTALS", "FULLGAME_MARKETS",
    "TAU_GRID", "LINE_BUCKETS", "BOOK_GROUPS", "MIN_GAMES", "FRAGILE_GAMES", "FDR_Q",
    "price_game_samples", "prob_over_at_lines",
    "DerivConfig", "make_config_grid", "select_bets", "game_level_returns",
    "score_config", "deflate_grid", "evaluate_market",
]
