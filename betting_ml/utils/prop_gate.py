"""prop_gate.py — Edge Program Story E5.4: the HARD prop-edge gate (pure machinery).

E5.3 produced the per-(pitcher × date × book × line) K-prop edge/EV table (`best_alpha = 0`,
a transparency table). E5.4 DECIDES whether any of it is a REAL, cashable edge or a clean null.
Props are the easiest place to overfit (prop-type × player × line × book = a huge
multiple-comparison surface), so the discipline is non-negotiable (guide §0.5 + §5B E5.4):

  1. CALIBRATION FLOOR — calib_80 ≥ 0.80 per prop type under E1.1 purged walk-forward CV.
  2. PBO < 0.2 AND DSR > 0 PER MARKET, multiple-comparison-corrected ACROSS EVERY
     prop-type × line × book tried (DSR deflates for the number of configs → LOG EVERY one).
  3. POSITIVE forward CLV/ROI NET OF THE (HIGH) PROP VIG vs the prop's OWN close.
  4. COVERAGE / ROBUSTNESS report.

THE TRAP (the prop data-mining machine): "find the markets/lines where we'd have won"
manufactures fake edges. The market/line/book SELECTION is PART of the test → the grid is
PRE-REGISTERED here (written down before outcomes), every config is settled the SAME way, and
every config counts in the DSR deflation. A config that looks +EV in-sample but fails the
deflated gate is REJECTED.

This module is the PURE math (settlement net of vig + the pre-registered config grid +
reliability). The orchestration (`betting_ml/scripts/prop_pricing/gate_props.py`) joins actual
outcomes, runs the purged-CV calibration / PBO / DSR / forward leg, and writes the dossier.

Settlement uses the REAL offered American price in the E5.3 table (not an estimated hold), so
"ROI net of vig" is exact: the offered price already embeds the book's overround.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.utils.prop_edge import american_to_profit

# ── The curated US "major" books (A0.4.32). Caesars arrives as `williamhill_us` post the
#    Odds-API cutover (see reference_bookmaker_identity_map). ───────────────────────────────
MAJOR_BOOKS = ("draftkings", "fanduel", "betmgm", "williamhill_us")
PINNACLE = "pinnacle"


# ── Settlement: realized PnL of a prop bet, net of the offered vig ───────────────────────────

def settle_side(actual_k: float, line: float, side: str) -> str:
    """Settle one over/under K bet → 'win' | 'lose' | 'push'.

    Half-line (e.g. 5.5): no push — over wins iff K > line, under wins iff K < line.
    Integer line (e.g. 5): K == line is a PUSH (stake refunded) for either side.
    """
    if actual_k is None or (isinstance(actual_k, float) and np.isnan(actual_k)):
        return "void"
    k = float(actual_k)
    ln = float(line)
    if k == ln:                       # only possible at an integer line → push
        return "push"
    over_wins = k > ln
    if side == "over":
        return "win" if over_wins else "lose"
    if side == "under":
        return "lose" if over_wins else "win"
    raise ValueError(f"side must be 'over'/'under', got {side!r}")


def bet_payoff(actual_k: float, line: float, side: str, american: float) -> float:
    """Per-$1 realized PnL of a settled over/under bet at the offered American price.

    win → +profit (american_to_profit); lose → −1; push → 0 (stake refund); void → 0/NaN-safe.
    This is the CASHABILITY unit: the offered price already embeds the (large) prop vig, so the
    mean of this over a strategy's bets IS its ROI net of vig — the E5.4 gate-3 metric.
    """
    if american is None or (isinstance(american, float) and np.isnan(american)):
        return float("nan")
    outcome = settle_side(actual_k, line, side)
    if outcome == "win":
        return float(american_to_profit(american))
    if outcome == "lose":
        return -1.0
    return 0.0   # push (refund) or void


def payoff_vec(actual_k, line, side, american) -> np.ndarray:
    """Vectorised `bet_payoff` over equal-length arrays (side is a per-row 'over'/'under' array)."""
    k = np.asarray(actual_k, float)
    ln = np.asarray(line, float)
    am = np.asarray(american, float)
    sd = np.asarray(side, dtype=object)
    over_wins = k > ln
    push = k == ln
    side_is_over = sd == "over"
    won = np.where(side_is_over, over_wins, ~over_wins) & ~push
    profit = np.where(am > 0, am / 100.0, 100.0 / np.abs(np.where(am == 0, np.nan, am)))
    out = np.where(won, profit, -1.0)
    out = np.where(push, 0.0, out)
    out = np.where(np.isnan(k) | np.isnan(am), np.nan, out)
    return out.astype(float)


# ── PRE-REGISTERED config grid (written down BEFORE looking at outcomes) ──────────────────────

# Conviction thresholds on the model-vs-market edge (probability points). 0.02–0.10.
TAU_GRID = (0.02, 0.04, 0.06, 0.08, 0.10)

# Line buckets (K lines cluster 2.5–7.5; see E5.3). Pre-registered, NOT tuned to outcomes.
LINE_BUCKETS = {
    "all": (None, None),
    "low_le4p5": (None, 4.5),       # line ≤ 4.5
    "mid_5p5": (5.0, 6.0),          # line == 5.5
    "high_ge6p5": (6.5, None),      # line ≥ 6.5
}

# Anchor policies: bet vs the BOOK's own de-vigged fair, OR vs the sharp PINNACLE fair (the
# "fade the soft book toward the sharp price" prop thesis). Both are pre-registered strategies.
ANCHOR_POLICIES = ("book", "pinnacle")


@dataclass(frozen=True)
class PropConfig:
    """One pre-registered betting strategy over the K-prop surface.

    book_group : 'all' | 'pinnacle' | 'soft' | 'majors' | a single bookmaker_key.
    line_bucket: a key of LINE_BUCKETS.
    tau        : minimum |edge| (prob-points) to place the bet.
    anchor     : 'book' (edge vs the book's own de-vig) | 'pinnacle' (edge vs the sharp fair).
    """
    book_group: str
    line_bucket: str
    tau: float
    anchor: str

    @property
    def name(self) -> str:
        return f"{self.book_group}|{self.line_bucket}|tau{self.tau:g}|{self.anchor}"


def make_config_grid(books: list[str]) -> list[PropConfig]:
    """The full PRE-REGISTERED grid = book-group × line-bucket × tau × anchor.

    `books` is the set of bookmaker_keys present in the edge table; each is tested individually
    (plus the {all, pinnacle, soft, majors} groups) so EVERY prop-type × line × book combination
    is logged and feeds the multiple-comparison deflation. The grid is a deterministic function
    of the inputs — it does not look at any outcome. `pinnacle` is de-duplicated (it is both a
    named group and a real book), so it is never counted twice."""
    groups: list[str] = ["all", "pinnacle", "soft", "majors"]
    for b in sorted(books):
        if b not in groups:
            groups.append(b)
    grid: list[PropConfig] = []
    for g in groups:
        for lb in LINE_BUCKETS:
            for tau in TAU_GRID:
                for anchor in ANCHOR_POLICIES:
                    # book='pinnacle' under anchor='pinnacle' is degenerate (betting Pinnacle's
                    # own price vs its own fair) — skip the duplicate, keep the grid honest.
                    if g == PINNACLE and anchor == "pinnacle":
                        continue
                    grid.append(PropConfig(g, lb, tau, anchor))
    return grid


def _book_mask(df: pd.DataFrame, group: str) -> np.ndarray:
    bk = df["bookmaker_key"].to_numpy(dtype=object)
    if group == "all":
        return np.ones(len(df), bool)
    if group == "pinnacle":
        return bk == PINNACLE
    if group == "soft":
        return bk != PINNACLE
    if group == "majors":
        return np.isin(bk, MAJOR_BOOKS)
    return bk == group


def _line_mask(df: pd.DataFrame, bucket: str) -> np.ndarray:
    lo, hi = LINE_BUCKETS[bucket]
    ln = df["line"].to_numpy(float)
    m = np.ones(len(df), bool)
    if lo is not None:
        m &= ln >= lo
    if hi is not None:
        m &= ln <= hi
    return m


def select_config_bets(df: pd.DataFrame, cfg: PropConfig) -> pd.DataFrame:
    """Rows the config BETS, with the chosen `bet_side` and offered `bet_price` attached.

    `df` must carry: bookmaker_key, line, best_side, best_edge, over_price, under_price,
    model_p_over_cond, edge_vs_pinnacle, devig_valid. Only de-viggable rows are eligible (a
    one-sided quote has no comparable fair price). Selection is a pure function of the config +
    the (model, market) columns — it never touches the realized outcome."""
    base = df["devig_valid"].to_numpy(bool) & _book_mask(df, cfg.book_group) & _line_mask(df, cfg.line_bucket)

    if cfg.anchor == "book":
        side = df["best_side"].to_numpy(dtype=object)
        conv = df["best_edge"].to_numpy(float)
        bet = base & (conv >= cfg.tau) & np.isin(side, ["over", "under"])
        chosen_side = side
    else:  # anchor == "pinnacle": fade the book toward the sharp fair value
        evp = df["edge_vs_pinnacle"].to_numpy(float)        # model_p_over_cond − pinnacle_fair_over
        has_pin = np.isfinite(evp)
        chosen_side = np.where(evp >= 0, "over", "under").astype(object)
        bet = base & has_pin & (np.abs(evp) >= cfg.tau)

    out = df.loc[bet].copy()
    if out.empty:
        out["bet_side"] = pd.Series(dtype=object)
        out["bet_price"] = pd.Series(dtype=float)
        return out
    cs = chosen_side[bet]
    out["bet_side"] = cs
    out["bet_price"] = np.where(cs == "over", out["over_price"].to_numpy(float),
                                out["under_price"].to_numpy(float))
    return out


# ── Reliability (at-the-line betting-probability calibration) ─────────────────────────────────

def reliability_table(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> dict:
    """ECE + per-bin reliability of a probability forecast against a 0/1 outcome.

    Quantile bins on `p` (so each bin has comparable mass). Returns ECE (mass-weighted mean
    |conf − acc|), Brier, n, and the bin table. Used on `model_p_over_cond` vs realized-over to
    confirm the BETTING probability — the number the edge rests on — is calibrated."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    n = len(p)
    if n == 0:
        return {"n": 0, "ece": float("nan"), "brier": float("nan"), "bins": []}
    brier = float(np.mean((p - y) ** 2))
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 2:
        edges = np.array([p.min(), p.max() + 1e-9])
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    bins = []
    ece = 0.0
    for b in range(len(edges) - 1):
        m = idx == b
        nb = int(m.sum())
        if nb == 0:
            continue
        conf = float(p[m].mean())
        acc = float(y[m].mean())
        ece += (nb / n) * abs(conf - acc)
        bins.append({"bin": b, "n": nb, "p_mean": round(conf, 4),
                     "over_rate": round(acc, 4), "gap": round(conf - acc, 4)})
    return {"n": n, "ece": round(float(ece), 4), "brier": round(brier, 4), "bins": bins}


def central_interval_coverage(p_over: np.ndarray, realized_over: np.ndarray) -> float:
    """Fraction of bets whose realized side fell on the model's >50% side — a coarse at-the-line
    accuracy check (NOT calib_80; the served-distribution calib_80 is the E5.2 purged-CV number)."""
    p = np.asarray(p_over, float)
    y = np.asarray(realized_over, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    if len(p) == 0:
        return float("nan")
    pred_over = p >= 0.5
    return float(np.mean(pred_over == (y == 1)))
