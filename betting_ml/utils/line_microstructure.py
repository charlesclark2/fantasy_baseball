"""line_microstructure.py — Edge Program Story E13.16: odds-as-a-price-series (pure math).

E13.16 asks a DIFFERENT question than every prior program null. E5.4 / E13.13 / E13.14 / E13.8 all
asked "is the PRICE right?" (efficient, PBO≈0.5). This asks: **"does the price's own MOVEMENT reveal
structure?"** — treat each game's odds line from first-posted → first-pitch as a PRICE TIME-SERIES
and test whether a signal on the trajectory lets us BEAT THE CLOSE (CLV), the gold-standard skill
measure. CLV is a price-vs-price quantity (no realized game outcome needed) → the PRIMARY gate here.

SCOPE = pure cached-data analysis, NO predictive model (an eval/harness story per guide §0.5). The
pre-registration (`ablation_results/e13_16_preregistration.md`) fixes the trajectory features, the
signals, the anchors, the thresholds, and the deflation BEFORE any close/outcome was joined.

This module is the PURE machinery; the orchestration
(`betting_ml/scripts/line_microstructure/eval_line_microstructure.py`) reads the cached S3 snapshots,
assembles the per-(game,book,market) trajectories, runs the signal grid, and writes the dossier.

HONEST BAR (the E13.13 lesson, reused wholesale from `cross_market_eval`):
  * GAME-LEVEL collapse FIRST — book quotes on one game are correlated; per-(game×book) CLV is
    averaged to ONE return per game before any t-test / DSR / PBO (`score_game_level`).
  * FORCED side — the bet side is a deterministic function of the observed TRAJECTORY (the move sign,
    the sharp-soft divergence sign, a fixed side, or game_pk parity for the placebo control) — never
    the realized outcome or the closing line.
  * CLV net of vig — measured on the DE-VIGGED fair series (h2h prob points) / the line (totals runs);
    the realized-ROI cross-check settles at the offered American price (vig-loaded), exactly as E13.13.
  * Deflate over EVERY signal × market × book-group × line-bucket × θ × anchor (PBO<0.2 + DSR + FDR),
    per market (different units) with a pooled FDR.
  * NEGATIVE CONTROL `placebo` (side = game_pk parity, trajectory-independent) MUST NOT survive.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Reuse the program's odds + deflation primitives (single source of truth for de-vig / FDR / PBO /
# DSR / game-level collapse / book groups) so the math matches E13.13 / E13.14 exactly.
from betting_ml.utils.cross_market_eval import (  # noqa: F401  (re-exported on purpose)
    MAJOR_BOOKS, PINNACLE, bh_fdr, book_mask, deflate_configs, devig_pair, score_game_level,
)
from betting_ml.utils.derivative_eval import h2h_payoff_vec  # noqa: F401
from betting_ml.utils.overfitting import DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE
from betting_ml.utils.prop_gate import payoff_vec

_EPS = 1e-9

# ── Curated US book set (mirrors write_serving_store._BOOK_ORDER; williamhill_us folded to caesars) ──
BOOK_ORDER = ["pinnacle", "betmgm", "caesars", "fanduel", "draftkings", "fanatics", "bovada"]

# ── Pre-registered grid (mirrors e13_16_preregistration.md — fixed BEFORE any outcome/close join) ──
BOOK_GROUPS = ["all", "pinnacle", "soft", "majors", "bovada"]
TOTALS_THETA = (0.5, 1.0)              # totals trigger in runs
H2H_THETA = (0.02, 0.04)               # h2h trigger in probability points
ANCHORS_PATH = ("t50", "t75")          # interior bet-time anchors for path-dependent signals
LINE_BUCKETS = {                       # totals only; (lo, hi) inclusive test on the anchor line
    "all": (None, None),
    "low": (None, 7.5),                # ≤ 7.5
    "mid": (8.0, 9.0),                 # 8–9
    "high": (9.5, None),               # ≥ 9.5
}
MIN_GAMES = 50                         # a config needs ≥ this many unique GAMES to be selectable
FRAGILE_GAMES = 250                    # a surviving candidate below this is FRAGILE (thin)
FDR_Q = 0.10
MIN_SNAPS_PATH = 3                     # path signals need ≥3 snaps (open + interior anchor + close)

# Long decisions frame — one row per (game, book, market, signal, anchor) that COULD fire. θ is
# applied at CONFIG time (a move ≥1.0 is also ≥0.5) via `trigger_mag`; static/placebo carry inf.
DEC_COLS = ["game_pk", "season", "ym", "market", "book", "signal", "anchor",
            "trigger_mag", "anchor_line", "side", "clv", "realized_payoff"]

# Signal registry: (market, kind, is_control). kind ∈ {static, reversion, continuation, sharp, placebo}
SIGNALS: dict[str, dict] = {
    "static_over":       dict(market="totals", kind="static", side="over",  is_control=False,
                              prior="retail/open-staleness probe"),
    "static_under":      dict(market="totals", kind="static", side="under", is_control=False,
                              prior="retail/open-staleness probe"),
    "static_home":       dict(market="h2h",    kind="static", side="home",  is_control=False,
                              prior="retail/open-staleness probe"),
    "static_away":       dict(market="h2h",    kind="static", side="away",  is_control=False,
                              prior="retail/open-staleness probe"),
    "reversion":         dict(market="both",   kind="reversion",    is_control=False,
                              prior="over-reaction → mean-reversion"),
    "continuation":      dict(market="both",   kind="continuation", is_control=False,
                              prior="steam persists (opposite of reversion)"),
    "sharp_convergence": dict(market="both",   kind="sharp",        is_control=False,
                              prior="LOW (12.10′ ~tapped)"),
    "placebo":           dict(market="both",   kind="placebo",      is_control=True,
                              prior="NEGATIVE CONTROL — must NOT survive"),
}


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Trajectory features + anchors (per game × book × market; snapshots pre-ordered ascending)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def trajectory_features(vals, hours_to_commence) -> dict:
    """Per-(game,book,market) movement features on the ascending pre-commence value series.

    vals : the price series (de-vigged home prob for h2h; total line for totals), time-ordered.
    hours_to_commence : signed T-minus at each snapshot (larger = earlier); used for velocity/window.
    Returns open/close, the total drift, #reversals, path length (total variation), realized vol,
    the peak excursion from open, and `retention` = drift / peak (how much of the peak move stuck)."""
    v = np.asarray(vals, float)
    h = np.asarray(hours_to_commence, float)
    ok = np.isfinite(v)
    v = v[ok]
    h = h[ok] if len(h) == len(ok) else h
    n = len(v)
    if n == 0:
        return {"n_snaps": 0}
    open_v, close_v = float(v[0]), float(v[-1])
    gap = close_v - open_v
    d = np.diff(v)
    reversals = int(np.sum(np.sign(d[:-1]) * np.sign(d[1:]) < 0)) if n >= 3 else 0
    path_len = float(np.sum(np.abs(d))) if n >= 2 else 0.0
    vol = float(np.std(d, ddof=1)) if n >= 3 else 0.0
    excursion = float(np.max(np.abs(v - open_v))) if n >= 2 else 0.0
    span_h = float(abs(h[0] - h[-1])) if (len(h) == n and n >= 2) else float("nan")
    velocity = float(gap / span_h) if (np.isfinite(span_h) and span_h > _EPS) else float("nan")
    return {"n_snaps": n, "open_val": open_v, "close_val": close_v, "open_close_gap": gap,
            "n_reversals": reversals, "path_length": path_len, "realized_vol": vol,
            "max_excursion": excursion, "velocity": velocity,
            "retention": float(gap / excursion) if excursion > _EPS else float("nan")}


def nearest_anchor_idx(hours_to_commence, frac: float) -> int:
    """Index of the snapshot nearest to `frac` of the open→close time window.

    The window runs from the open (max hours_to_commence) to the close (min). `frac`=0 → open,
    1 → close. Returns the index whose hours_to_commence is closest to the target T-minus."""
    h = np.asarray(hours_to_commence, float)
    if len(h) == 0:
        return 0
    h0, h1 = float(h[0]), float(h[-1])           # ascending time ⇒ h decreasing (h0=earliest)
    target = h0 + frac * (h1 - h0)
    return int(np.argmin(np.abs(h - target)))


# ════════════════════════════════════════════════════════════════════════════════════════════════
# CLV (beat-the-close) — the PRIMARY gate metric (no realized outcome needed)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def clv_runs(side: str, line_anchor: float, line_close: float) -> float:
    """Totals CLV in runs: positive ⇒ the number moved in your favour vs the close.

    OVER: you want the number to RISE (you locked the lower total) → L_close − L_anchor.
    UNDER: you want it to FALL → L_anchor − L_close."""
    if not (np.isfinite(line_anchor) and np.isfinite(line_close)):
        return float("nan")
    return float(line_close - line_anchor) if side == "over" else float(line_anchor - line_close)


def clv_prob(side: str, p_home_anchor: float, p_home_close: float) -> float:
    """H2H CLV in de-vigged probability points: positive ⇒ your side's fair prob ROSE after you bet
    (the market moved toward you) ⇒ you beat the close. side ∈ {home, away}."""
    if not (np.isfinite(p_home_anchor) and np.isfinite(p_home_close)):
        return float("nan")
    ps_anchor = p_home_anchor if side == "home" else 1.0 - p_home_anchor
    ps_close = p_home_close if side == "home" else 1.0 - p_home_close
    return float(ps_close - ps_anchor)


def _h2h_realized_payoff(side: str, home_won, american: float) -> float:
    """Per-$1 h2h settlement net of the offered vig (home_won ∈ {0,1,nan})."""
    if home_won is None or not np.isfinite(home_won) or not np.isfinite(american):
        return float("nan")
    won = (side == "home") == bool(home_won)
    profit = (american / 100.0) if american > 0 else (100.0 / abs(american))
    return float(profit if won else -1.0)


def _line_bucket_ok(line: float, bucket: str) -> bool:
    if bucket == "all":
        return True
    lo, hi = LINE_BUCKETS[bucket]
    if not np.isfinite(line):
        return False
    if lo is not None and line < lo:
        return False
    if hi is not None and line > hi:
        return False
    return True


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Adversarial control — drop off-market / STALE book quotes before the trajectory is built
# ════════════════════════════════════════════════════════════════════════════════════════════════
def drop_stale_snaps(snaps: pd.DataFrame, *, totals_tol: float = 0.75, h2h_tol: float = 0.06,
                     min_books: int = 3, bucket_hours: float = 1.0) -> tuple[pd.DataFrame, dict]:
    """Remove stale / off-market book quotes BEFORE the trajectory is built (the adversarial control
    for the stale-quote artifact that inflates `sharp_convergence` / large-θ `reversion`).

    At each (game_pk, market, ~hourly time-bucket) we take the cross-book CONSENSUS = median value
    across the curated books present in that bucket, and DROP any book-snapshot whose value deviates
    from it by more than the market tolerance. The discriminator is exactly the one we need: a
    genuine MARKET-WIDE move keeps every book near consensus (KEPT — real reversion/steam survives),
    while a SINGLE book's stale spike (the ≥1-run soft-vs-Pinnacle gap sharp_convergence mechanically
    fed on) is an outlier (DROPPED). Only buckets with ≥ min_books get a consensus; thinner buckets
    are left as-is (can't judge). value = line (totals) / fair_home (h2h). Returns (filtered, stats)."""
    stats = {"n_in": int(len(snaps)), "n_stale_dropped": 0, "pct_dropped": 0.0,
             "totals_tol": totals_tol, "h2h_tol": h2h_tol, "min_books": min_books}
    if snaps.empty:
        return snaps, stats
    df = snaps.copy()
    df["_val"] = np.where(df["market"].to_numpy() == "totals",
                          df["line"].to_numpy(float), df["fair_home"].to_numpy(float))
    ts = pd.to_datetime(df["snapshot_ts"], utc=True, errors="coerce")
    epoch_h = (ts - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds() / 3600.0
    df["_bucket"] = np.floor(epoch_h.to_numpy(float) / bucket_hours + 0.5)
    grp = df.groupby(["game_pk", "market", "_bucket"], dropna=False)["_val"]
    cons = grp.transform("median")
    nbk = grp.transform("size")
    tol = np.where(df["market"].to_numpy() == "totals", totals_tol, h2h_tol)
    dev = (df["_val"] - cons).abs().to_numpy(float)
    stale = ((nbk.to_numpy(float) >= min_books) & np.isfinite(df["_val"].to_numpy(float))
             & np.isfinite(cons.to_numpy(float)) & (dev > tol))
    kept = df.loc[~stale].drop(columns=["_val", "_bucket"]).reset_index(drop=True)
    stats["n_stale_dropped"] = int(stale.sum())
    stats["pct_dropped"] = round(100.0 * float(stale.mean()), 3) if len(stale) else 0.0
    return kept, stats


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Build the decisions long-frame from the per-snapshot cache (the trajectory work, done ONCE)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def build_decisions(snaps: pd.DataFrame) -> pd.DataFrame:
    """Assemble one decision row per (game, book, market, signal, anchor) that COULD fire.

    `snaps` schema (one row per pre-commence snapshot × book × market):
      game_pk, season, ym, book, market ∈ {h2h, totals}, snapshot_ts, hours_to_commence,
      line (totals), fair_over (totals), fair_home (h2h), over_price/under_price (totals),
      home_price/away_price (h2h), realized_total, home_won.
    The trajectory value = fair_home (h2h) / line (totals). Sharp-convergence needs the per-game
    Pinnacle anchor value, so we precompute it. Every decision carries the forced side, the primary
    CLV, the secondary realized payoff, and the trigger magnitude (θ applied at config time)."""
    if snaps.empty:
        return pd.DataFrame(columns=DEC_COLS)
    snaps = snaps.copy()
    snaps["snapshot_ts"] = pd.to_datetime(snaps["snapshot_ts"], errors="coerce", utc=True)
    snaps = snaps.dropna(subset=["snapshot_ts"]).sort_values("snapshot_ts")

    # Pass 1: per (game, market, book) trajectory summary + anchor values.
    traj: dict[tuple, dict] = {}
    for (gp, mkt, bk), sub in snaps.groupby(["game_pk", "market", "book"], sort=False):
        val_col = "fair_home" if mkt == "h2h" else "line"
        v = sub[val_col].to_numpy(float)
        keep = np.isfinite(v)
        if keep.sum() < 2:
            continue
        sub = sub.loc[keep]
        v = v[keep]
        h = sub["hours_to_commence"].to_numpy(float)
        rec = {"sub": sub.reset_index(drop=True), "v": v, "h": h,
               "feat": trajectory_features(v, h),
               "season": sub["season"].iloc[0], "ym": sub["ym"].iloc[0]}
        # anchor indices
        rec["idx"] = {"open": 0, "close": len(v) - 1,
                      "t50": nearest_anchor_idx(h, 0.5), "t75": nearest_anchor_idx(h, 0.75)}
        traj[(gp, mkt, bk)] = rec

    # Per (game, market, anchor): the Pinnacle anchor value (for sharp-convergence divergence).
    pinn_val: dict[tuple, float] = {}
    for (gp, mkt, bk), rec in traj.items():
        if bk != PINNACLE:
            continue
        for anc, i in rec["idx"].items():
            pinn_val[(gp, mkt, anc)] = float(rec["v"][i])

    rows: list[dict] = []
    for (gp, mkt, bk), rec in traj.items():
        v, sub, feat = rec["v"], rec["sub"], rec["feat"]
        season, ym = rec["season"], rec["ym"]
        i_open, i_close = rec["idx"]["open"], rec["idx"]["close"]
        n = len(v)
        realized_total = _first_finite(sub.get("realized_total"))
        home_won = _first_finite(sub.get("home_won"))

        def _emit(signal, anchor, side, trigger_mag):
            i_a = rec["idx"][anchor]
            anchor_line = float(v[i_a]) if mkt == "totals" else float("nan")
            # primary CLV (beat-the-close), net of vig via the de-vigged / line series
            if mkt == "totals":
                clv = clv_runs(side, float(v[i_a]), float(v[i_close]))
                price = _price_at(sub, i_a, "over_price" if side == "over" else "under_price")
                realized = payoff_vec([realized_total], [float(v[i_a])], [side], [price])[0]
            else:
                clv = clv_prob(side, float(v[i_a]), float(v[i_close]))
                price = _price_at(sub, i_a, "home_price" if side == "home" else "away_price")
                realized = _h2h_realized_payoff(side, home_won, price)
            rows.append({"game_pk": gp, "season": season, "ym": ym, "market": mkt, "book": bk,
                         "signal": signal, "anchor": anchor, "trigger_mag": float(trigger_mag),
                         "anchor_line": anchor_line, "side": side,
                         "clv": float(clv) if np.isfinite(clv) else np.nan,
                         "realized_payoff": float(realized) if np.isfinite(realized) else np.nan})

        # ── Static probes (P) + placebo control: anchor = open ────────────────────────────────
        if mkt == "totals":
            _emit("static_over", "open", "over", np.inf)
            _emit("static_under", "open", "under", np.inf)
            placebo_side = "over" if (gp % 2 == 0) else "under"
        else:
            _emit("static_home", "open", "home", np.inf)
            _emit("static_away", "open", "away", np.inf)
            placebo_side = "home" if (gp % 2 == 0) else "away"
        _emit("placebo", "open", placebo_side, np.inf)

        # ── Path-dependent signals (reversion / continuation): interior anchors ──────────────────
        if n >= MIN_SNAPS_PATH:
            for anchor in ANCHORS_PATH:
                i_a = rec["idx"][anchor]
                if i_a in (i_open, i_close):        # no genuine interior anchor → skip (logged as absent)
                    continue
                early_move = float(v[i_a] - v[i_open])
                mag = abs(early_move)
                if mag < _EPS:
                    continue
                move_up = early_move > 0             # totals: line up ⇒ "toward over"; h2h: p_home up ⇒ "toward home"
                with_side = ("over" if move_up else "under") if mkt == "totals" else \
                            ("home" if move_up else "away")
                against_side = {"over": "under", "under": "over",
                                "home": "away", "away": "home"}[with_side]
                _emit("reversion", anchor, against_side, mag)
                _emit("continuation", anchor, with_side, mag)

            # ── Sharp convergence: soft book diverges from Pinnacle at the anchor ──────────────
            if bk != PINNACLE:
                for anchor in ANCHORS_PATH:
                    i_a = rec["idx"][anchor]
                    pv = pinn_val.get((gp, mkt, anchor))
                    if pv is None or i_a in (i_open, i_close):
                        continue
                    div = pv - float(v[i_a])          # + ⇒ Pinnacle higher ⇒ bet toward over/home
                    mag = abs(div)
                    if mag < _EPS:
                        continue
                    toward = ("over" if div > 0 else "under") if mkt == "totals" else \
                             ("home" if div > 0 else "away")
                    _emit("sharp_convergence", anchor, toward, mag)

    return pd.DataFrame(rows, columns=DEC_COLS) if rows else pd.DataFrame(columns=DEC_COLS)


def _first_finite(series):
    if series is None:
        return float("nan")
    arr = pd.to_numeric(series, errors="coerce").to_numpy(float)
    fin = arr[np.isfinite(arr)]
    return float(fin[0]) if len(fin) else float("nan")


def _price_at(sub: pd.DataFrame, i: int, col: str) -> float:
    if col not in sub.columns:
        return float("nan")
    try:
        return float(sub[col].to_numpy(float)[i])
    except (IndexError, ValueError, TypeError):
        return float("nan")


# ════════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered config grid + per-market deflation
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _config_specs() -> list[dict]:
    """Enumerate every pre-registered (signal × market × book-group × line-bucket × θ × anchor) config.
    Static/placebo: anchor=open, θ='na'. Path/sharp: interior anchors × the market's θ grid."""
    specs: list[dict] = []
    for sig, meta in SIGNALS.items():
        kind = meta["kind"]
        markets = ([meta["market"]] if meta["market"] != "both" else ["totals", "h2h"])
        for mkt in markets:
            thetas = (TOTALS_THETA if mkt == "totals" else H2H_THETA)
            buckets = list(LINE_BUCKETS) if mkt == "totals" else ["all"]
            for grp in BOOK_GROUPS:
                if kind == "sharp" and grp == "pinnacle":
                    continue                          # divergence from self ≡ 0 → not a config
                for bucket in buckets:
                    if kind in ("static", "placebo"):
                        specs.append(dict(signal=sig, market=mkt, book_group=grp, bucket=bucket,
                                          theta=None, anchor="open", is_control=meta["is_control"]))
                    else:
                        for theta in thetas:
                            for anchor in ANCHORS_PATH:
                                specs.append(dict(signal=sig, market=mkt, book_group=grp,
                                                  bucket=bucket, theta=theta, anchor=anchor,
                                                  is_control=meta["is_control"]))
    return specs


def _eval_config(dec: pd.DataFrame, spec: dict) -> dict | None:
    """Score ONE config at GAME level on the primary CLV series (+ the secondary realized ROI)."""
    m = ((dec["signal"].to_numpy() == spec["signal"]) & (dec["market"].to_numpy() == spec["market"])
         & (dec["anchor"].to_numpy() == spec["anchor"]))
    if spec["theta"] is not None:
        m &= dec["trigger_mag"].to_numpy(float) >= spec["theta"]
    m &= book_mask(dec["book"].to_numpy(object), spec["book_group"])
    if spec["market"] == "totals" and spec["bucket"] != "all":
        m &= np.array([_line_bucket_ok(x, spec["bucket"]) for x in dec["anchor_line"].to_numpy(float)])
    m &= np.isfinite(dec["clv"].to_numpy(float))
    if not m.any():
        return None
    s = dec[m]
    stats = score_game_level(s["clv"].to_numpy(float), s["game_pk"].to_numpy(),
                             s["season"].to_numpy(object), s["ym"].to_numpy(object))
    if stats is None or stats["n"] == 0:
        return None
    # secondary realized-ROI (thin sample; reported, NOT the gate)
    rp = s["realized_payoff"].to_numpy(float)
    rstats = score_game_level(rp, s["game_pk"].to_numpy(), s["season"].to_numpy(object),
                              s["ym"].to_numpy(object))
    theta_label = "na" if spec["theta"] is None else f"{spec['theta']:g}"
    name = (f"{spec['signal']}|{spec['market']}|{spec['book_group']}|{spec['bucket']}"
            f"|θ{theta_label}|{spec['anchor']}")
    return {"name": name, "signal": spec["signal"], "market": spec["market"],
            "book_group": spec["book_group"], "bucket": spec["bucket"], "theta": theta_label,
            "anchor": spec["anchor"], "is_control": spec["is_control"], "roi_fdr_survive": False,
            "realized_roi": (rstats["roi"] if rstats else float("nan")),
            "realized_n": (rstats["n"] if rstats else 0), **stats}


def evaluate(decisions: pd.DataFrame) -> dict:
    """Run the full pre-registered grid, deflate PER MARKET (CLV units differ), pool the FDR.

    Returns {markets: {mkt: {configs, deflation, n_games}}, all_configs, candidates}. `roi` on each
    config is the mean per-GAME CLV (beat-the-close), the primary gate quantity."""
    all_configs: list[dict] = []
    per_market: dict[str, dict] = {}
    for mkt in ("totals", "h2h"):
        cfgs = [c for c in (_eval_config(decisions, s) for s in _config_specs() if s["market"] == mkt)
                if c is not None]
        if not cfgs:
            continue
        defl = deflate_configs(cfgs, min_games=MIN_GAMES, fdr_q=FDR_Q)
        per_market[mkt] = {"configs": cfgs, "deflation": defl,
                           "n_games": int(decisions[decisions["market"] == mkt]["game_pk"].nunique())}
        all_configs.extend(cfgs)
    # pooled FDR across BOTH markets (p-values are unit-free) — the honest multiple-comparison count
    sel = [c for c in all_configs if c.get("n", 0) >= MIN_GAMES]
    pooled = bh_fdr([c.get("roi_p", float("nan")) for c in sel], q=FDR_Q)
    for c, surv in zip(sel, pooled["survive"]):
        c["roi_fdr_survive"] = bool(surv)
    cands = build_candidates(per_market, all_configs, pooled)
    return {"markets": per_market, "all_configs": all_configs,
            "pooled_fdr": {"n_survive": pooled["n_survive"], "n_tested": pooled["n_tested"],
                           "threshold": pooled["threshold"], "q": FDR_Q},
            "candidates": cands}


def build_candidates(per_market: dict, all_configs: list[dict], pooled_fdr: dict) -> dict:
    """A config is a CANDIDATE (for the forward-CLV leg — NOT a declared edge) iff, in ITS market's
    deflation: n≥MIN_GAMES, mean CLV>0, season-sign-consistent, survives pooled FDR, AND the market's
    grid clears PBO<0.2. The `placebo` control MUST NOT appear — a control candidate ⇒ method bug."""
    def _grid_pbo_ok(mkt):
        p = per_market.get(mkt, {}).get("deflation", {}).get("pbo", {}).get("pbo")
        return p is not None and np.isfinite(p) and p < PBO_SHADOW_TO_LIVE

    surviving = [c for c in all_configs
                 if c.get("n", 0) >= MIN_GAMES and c["roi"] > 0 and c["season_sign_consistent"]
                 and c.get("roi_fdr_survive") and _grid_pbo_ok(c["market"])]

    # dedup overlapping book-groups → one candidate per (signal, market, bucket, θ, anchor)
    by_sig: dict[tuple, list] = {}
    for c in surviving:
        by_sig.setdefault((c["signal"], c["market"], c["bucket"], c["theta"], c["anchor"]), []).append(c)
    cands = []
    for key, group in by_sig.items():
        best = max(group, key=lambda c: c["n"])
        cands.append({"name": best["name"], "signal": best["signal"], "market": best["market"],
                      "n": best["n"], "clv_mean": best["roi"], "clv_p": best.get("roi_p"),
                      "realized_roi": best.get("realized_roi"),
                      "book_groups": sorted({c["book_group"] for c in group}),
                      "per_season_clv": {k: round(v, 4) for k, v in best["per_season"].items()},
                      "is_control": best["is_control"], "fragile": bool(best["n"] < FRAGILE_GAMES)})

    control_breaks = [c for c in cands if c["is_control"]]
    real = [c for c in cands if not c["is_control"]]
    n_fragile = sum(1 for c in real if c["fragile"])
    if control_breaks:
        verdict = ("⚠️ METHOD CHECK FAILED — the `placebo` NEGATIVE CONTROL produced a 'candidate'; "
                   "the harness manufactures CLV where none exists. Investigate before trusting any result.")
    elif not real:
        verdict = ("CLEAN NULL — the line trajectory is efficient too (no CLV-timing edge beats the "
                   "deflated, game-level, multiple-comparison-corrected bar)")
    elif n_fragile == len(real):
        verdict = (f"NO ROBUST EDGE — {len(real)} FRAGILE thin CLV-timing candidate(s) for the "
                   "forward-CLV leg ONLY (granularity-limited; confirm prospectively)")
    else:
        verdict = (f"CLV-TIMING CANDIDATE(S) — {len(real) - n_fragile} robust + {n_fragile} fragile; "
                   "each is a forward-CLV target, NOT a declared live edge")
    return {"candidates": real, "control_breaks": control_breaks,
            "control_present": any(SIGNALS[c["signal"]]["is_control"] for c in cands) if cands else True,
            "n_fragile": n_fragile, "verdict": verdict}


__all__ = [
    "BOOK_ORDER", "BOOK_GROUPS", "TOTALS_THETA", "H2H_THETA", "ANCHORS_PATH", "LINE_BUCKETS",
    "MIN_GAMES", "FRAGILE_GAMES", "FDR_Q", "MIN_SNAPS_PATH", "DEC_COLS", "SIGNALS",
    "trajectory_features", "nearest_anchor_idx", "clv_runs", "clv_prob",
    "drop_stale_snaps", "build_decisions", "evaluate", "build_candidates",
]
