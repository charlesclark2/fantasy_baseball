"""rookie_availability.py — NF-D14 pure model logic: the ROOKIE AVAILABILITY prior.

WHY THIS STORY EXISTS. NF1.8 lifted rookie-QB 80% coverage 0.741 → 0.815 with a Mondrian
(per-position) conformal layer, and cleared the 0.80 floor with **1 covered rookie-season of slack out
of 81**. Its own diagnosis was that the RESIDUAL QB gap is class-to-class VARIANCE rather than fittable
miscalibration — so more recalibration cannot close it (a per-group conformal layer already did all it
can). The honest lever is at the SOURCE of the uncertainty: **35.3% of drafted rookie QBs never take an
NFL snap** (measured on the 2016–2025 drafted population — 42 of 119), against 10.9–13.0% at RB/WR/TE.
AVAILABILITY — whether he plays at all, and for how many games — is the dominant term in a rookie QB's
season outcome, and the served band prices it only implicitly through the point projection.

This module is the AVAILABILITY PRIOR itself: a per-player predictive distribution over ROOKIE-SEASON
GAMES PLAYED, from information that exists BEFORE the season (draft capital, the week-1 depth-chart
rank, the NCAAF-P1A college translation). `run_nf_d14_availability.py` is the §0.5 gate that selects
among the pre-registered forms and then measures what the winner does to the rookie-QB interval.

⚠️ **HONEST FRAMING, PRE-REGISTERED BEFORE ANY RESULT WAS READ (roadmap §0.5).** This is the most
speculative of the fantasy modeling stories. NF1.8 showed the QB gap is variance on a ~12-QB/class
cohort; a prior fitted on that same thin cohort may not close it. A CLEAN, DEFLATED NULL — "the QB
interval variance is irreducible at this N" — is a legitimate and valuable outcome, and the floor does
NOT move either way (E2.1-r; NF1.8 §1).

────────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IS EMITTED, AND WHY IT IS A DISTRIBUTION RATHER THAN A NUMBER
────────────────────────────────────────────────────────────────────────────────────────────────────
Every form emits a full PMF over games ∈ {0, 1, …, 17}. Not an expected-games scalar, for two reasons:

  1. **The target has a 35% point mass at exactly 0 and a hard ceiling at 17.** A Gaussian/point
     summary of that is a lie about its own shape, and it is the exact population CLAUDE.md's E2.1-r /
     NF-D11 / NF1.9 landmines all fire on.
  2. **The band needs the SPREAD, not the mean.** A 7th-round QB3 with `p_play ≈ 0.05` has a *low*
     outcome variance (he will score ~nothing, confidently). A second-round QB in an open competition
     with `p_play ≈ 0.5` has an *enormous* one. Availability risk is NOT monotone in expected games —
     it peaks in the middle — so an "expected games" haircut cannot be the interval driver. A PMF
     gives `p_play`, `e_games` AND `sd_games` from one object, and the harness pre-registers the
     naive driver (bust risk) beside the principled one (predictive sd) rather than assuming.

────────────────────────────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED CANDIDATE FORMS (≥3 classes + a direct-learned foil, per §0.5)
────────────────────────────────────────────────────────────────────────────────────────────────────
  • `pos_empirical`  — THE HONEST NULL. The position's own in-fold empirical games distribution, given
                       to every rookie at that position. Carries the zero atom and the ceiling exactly
                       right, and ZERO per-player information. Everything must beat this or the story
                       is a null.
  • `tier_empirical` — a distribution per (position × TIER), EB-shrunk toward the position's. `tier` is
                       pre-registered as draft-ROUND capital, DEPTH-chart rank, or their cross. This is
                       the story's named "depth-chart-tier prior".
  • `hurdle_logit`   — the story's named "draft-capital logistic": a logistic P(plays) on the feature
                       blocks, times the position's conditional-on-playing shape. Only the ZERO ATOM
                       moves per player — the cleanest test of "availability is the dominant term".
  • `haircut_ratio`  — **the NF-D11 return-from-absence form ported to rookies**: a MULTIPLICATIVE
                       haircut on the player's own expected games (`ratio` family), realised by
                       transporting the position's empirical games sample by that ratio.
  • `learned_gbm`    — THE DIRECT-LEARNED FOIL: gradient boosting on realized games over the same
                       blocks, transported the same way. It differs from `haircut_ratio` ONLY in the
                       functional form of the mean, so a win is attributable to the learner and not to
                       the transport.
Each non-null form × a `blend` grid — the weight on the candidate PMF against the position's null PMF.
`blend = 0` IS the null by construction (asserted in the tests), which is what makes the grid honest.

FEATURE BLOCKS (bounded + hypothesis-driven, §0.5 — not an open subset search):
  `capital` (log draft slot, round, top-10, day-1), `depth` (week-1 depth-chart rank as 1 / 2 / 3+ /
  absent, plus the explicit `has_depth` missingness flag), `p1a` (the NCAAF-P1A `projected_nfl_z`).

────────────────────────────────────────────────────────────────────────────────────────────────────
📏 SELECTION METRIC — the DISCRETE CRPS (= the Ranked Probability Score), and why NOT MAE
────────────────────────────────────────────────────────────────────────────────────────────────────
    CRPS(F, y) = Σ_{g=0..17} ( F(g) − 1{g ≥ y} )²                                (lower is better)

It is PROPER — uniquely minimised by the true predictive — and it grades the emitted mass AND its
spread jointly, on the integer support the outcome actually lives on.

⚠️ **MAE IS INVERTED ON THIS COHORT, and that is not a hypothetical — it is the CLAUDE.md NF-D11
landmine verbatim, one population over.** MAE is minimised at the conditional MEDIAN, and the rookie-QB
games distribution is so zero-heavy (median 3, 35% exact zeros) that MAE PAYS FOR PESSIMISM: the
`all_zero` degenerate ("project zero games for every rookie") is scored in the field precisely so that
inversion is visible rather than assumed. MAE and RMSE stay REPORTED; they are never selectable.

⭐ TWO-SIDED ANCHORS, EVERY RUN (E2.1-r (b)/(d), NF1.7 (a)/(b), NF1.9 (f)) — and every one of them is
REQUIRED, because an anchor that fails to fit makes its own check vacuously true:
  · `oracle_empirical`   — the ORACLE FLOOR: the held-out class's OWN realized per-position games
                           distribution. It peeks; nothing may beat it.
  · `matched_n_candidate`— the NF1.9 (f) guard that makes that floor WELL-POSED: the winner's own arm
                           trained on ONE prior class. A peeking oracle is a floor only at matched
                           family AND matched sample size, so the gate is "the oracle beats THIS",
                           not "the oracle beats the full-history winner".
  · `permuted`           — the winner's own family fitted against SHUFFLED training outcomes. Well-posed
                           at any n (family and resolution held exactly equal; only information moves).
                           Knowing the answer must beat not knowing it.
  · `all_zero`           — DEGENERATE CEILING: all mass at 0 games. Wins MAE, must LOSE CRPS.
  · `all_mean`           — DEGENERATE CEILING: all mass at the pooled mean games. Must LOSE.

Everything here is PURE (numpy/pandas in, arrays/dicts out, NO IO) so it is fast-gate testable; the
DuckDB panel assembly, the walk-forward and the reports live in `run_nf_d14_availability.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MODEL_VERSION = "nfl_fantasy_nf_d14_rookie_availability_v1"

# The support of a rookie season. 17 is the modern regular-season game count; the pre-2021 seasons cap
# at 16 and simply put no mass on 17, which the empirical forms carry for free.
GAMES_MAX = 17
GAMES_GRID = np.arange(0, GAMES_MAX + 1)

POSITIONS = ("QB", "RB", "WR", "TE")

# Deflation gates. PBO/FDR inherited from NF1.1 so this search is held to the same bar; DSR is the
# story's own pre-registered level (≥0.95 = "P(true SR > 0 | the search) at least 95%"), which is
# STRICTER than NF1.1/NF1.4's 0.0 — deliberately, because a thin-cohort availability claim that only
# just clears zero is exactly the claim this story promised not to manufacture.
PBO_MAX = 0.2
DSR_MIN = 0.95
FDR_Q = 0.10

SELECTION_METRIC = "crps"

# Forms that exist to CHARACTERISE the metric or to bound it, never to ship.
NON_SHIPPABLE = ("all_zero", "all_mean", "oracle_empirical", "permuted", "matched_n_candidate")

FEATURE_BLOCKS: dict[str, tuple[str, ...]] = {
    "capital": ("log_overall", "draft_round", "is_top10", "is_day1"),
    "depth": ("depth_rank1", "depth_rank2", "depth_rank3plus", "has_depth"),
    "p1a": ("projected_nfl_z",),
}
ALWAYS_ON_BLOCK = "capital"
BLOCK_SETS: tuple[tuple[str, ...], ...] = (
    ("capital",),
    ("capital", "depth"),
    ("capital", "depth", "p1a"),
)
TIERS = ("round", "depth", "round_depth")
BLEND_GRID = (0.3, 0.5, 0.7, 1.0)

# The EB pseudo-count for a (position × tier) cell: the count at which the cell's own evidence equals
# the position prior. Coarse on purpose — a rookie-QB depth cell carries ~10 rows a decade.
EB_K = 8.0
# Below this many in-fold rows a position cannot carry its own distribution and falls back to the
# pooled one. Recorded, never silent (the NF1.7 vacuous-anchor lesson).
MIN_POS_ROWS = 25

__all__ = [
    "MODEL_VERSION", "GAMES_MAX", "GAMES_GRID", "POSITIONS", "PBO_MAX", "DSR_MIN", "FDR_Q",
    "SELECTION_METRIC", "NON_SHIPPABLE", "FEATURE_BLOCKS", "BLOCK_SETS", "TIERS", "BLEND_GRID",
    "AvailabilityPrior", "candidate_configs", "config_key", "block_features",
    "capital_tier", "depth_tier", "empirical_pmf", "transport_pmf", "blend_pmf",
    "discrete_crps", "pmf_stats", "score_pmf", "availability_features",
    "degenerate_pmf", "oracle_pmf", "availability_verdict",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PMF primitives
# ══════════════════════════════════════════════════════════════════════════════════════════════
def empirical_pmf(games) -> np.ndarray:
    """The empirical PMF over {0..17} of a realized-games sample. A missing/negative value is dropped;
    a value above the grid is CLIPPED into 17 rather than discarded (an 18-game season is still a
    fully-available one, and dropping it would silently thin the top of the support)."""
    g = pd.to_numeric(pd.Series(games), errors="coerce").to_numpy(dtype=float)
    g = g[np.isfinite(g)]
    if len(g) == 0:
        return np.full(GAMES_MAX + 1, 1.0 / (GAMES_MAX + 1))
    idx = np.clip(np.rint(g), 0, GAMES_MAX).astype(int)
    pmf = np.bincount(idx, minlength=GAMES_MAX + 1).astype(float)
    return pmf / pmf.sum()


def blend_pmf(candidate: np.ndarray, null: np.ndarray, weight: float) -> np.ndarray:
    """`weight` on the candidate, the rest on the null PMF. A MIXTURE, not an interpolation of
    parameters — so `weight = 0` reproduces the null EXACTLY (asserted in the tests), which is what
    makes the blend grid an honest shrink toward "no availability information" rather than a knob that
    quietly changes shape at both ends."""
    w = float(np.clip(weight, 0.0, 1.0))
    out = w * np.asarray(candidate, dtype=float) + (1.0 - w) * np.asarray(null, dtype=float)
    s = out.sum(axis=-1, keepdims=True)
    return np.divide(out, np.where(s > 0, s, 1.0))


def transport_pmf(base_games: np.ndarray, ratio: float) -> np.ndarray:
    """The MULTIPLICATIVE-haircut PMF — NF-D11's `ratio` family, ported.

    Scale a position's realized-games SAMPLE by the player's own availability ratio and re-bin. This
    keeps the shape the position actually produced (the zero atom, the 17-game pile-up) while moving
    its LOCATION per player, which is exactly what a haircut on expected games means for a distribution.
    Ratios below 1 push mass INTO the zero atom by rounding, which is the honest behaviour: haircutting
    a 3-game rookie does not produce a fractional season, it produces a rookie who does not play."""
    g = np.asarray(base_games, dtype=float)
    g = g[np.isfinite(g)]
    if len(g) == 0:
        return np.full(GAMES_MAX + 1, 1.0 / (GAMES_MAX + 1))
    idx = np.clip(np.rint(g * float(max(ratio, 0.0))), 0, GAMES_MAX).astype(int)
    pmf = np.bincount(idx, minlength=GAMES_MAX + 1).astype(float)
    return pmf / pmf.sum()


def pmf_stats(pmf: np.ndarray) -> dict:
    """`p_play`, `e_games`, `sd_games` from a (n, 18) PMF block — the three quantities the band leg
    may condition on. ⭐ `sd_games` is the PRINCIPLED interval driver: availability risk is NOT
    monotone in expected games, it peaks where the outcome is a coin flip. `p_short` (= 1 − p_play) is
    the naive driver the story's framing suggests, carried beside it so the harness can pre-register
    both rather than assume."""
    p = np.atleast_2d(np.asarray(pmf, dtype=float))
    mean = p @ GAMES_GRID
    var = p @ (GAMES_GRID.astype(float) ** 2) - mean ** 2
    return {
        "p_play": 1.0 - p[:, 0],
        "p_short": p[:, 0],
        "e_games": mean,
        "sd_games": np.sqrt(np.clip(var, 0.0, None)),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The selection metric + its secondaries
# ══════════════════════════════════════════════════════════════════════════════════════════════
def discrete_crps(pmf: np.ndarray, y) -> np.ndarray:
    """The DISCRETE CRPS (= the Ranked Probability Score) of a PMF over {0..17} against realized games.

        CRPS(F, y) = Σ_g ( F(g) − 1{g ≥ y} )²

    PROPER — uniquely minimised by the true predictive — so unlike MAE it cannot be won by projecting
    zero for everyone, and unlike a coverage target it cannot be won by spreading mass everywhere. It
    is the NF-D11 CRPS argument on the integer support this outcome actually lives on: a closed-form
    Normal CRPS would misprice a distribution with 35% of its mass on one atom and a hard ceiling."""
    p = np.atleast_2d(np.asarray(pmf, dtype=float))
    yy = np.clip(np.rint(pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(dtype=float)),
                 0, GAMES_MAX)
    cdf = np.cumsum(p, axis=1)
    ind = (GAMES_GRID[None, :] >= yy[:, None]).astype(float)
    return np.sum((cdf - ind) ** 2, axis=1)


def score_pmf(pmf: np.ndarray, y, positions=None) -> dict:
    """Every reading of one arm on one held-out cohort, ROW-POOLED (the NF1.8 convention: a position
    thin in one class is never silently dropped from a mean).

    `crps` SELECTS. `mae_games`/`rmse_games` are REPORTED so the inversion stays visible — the
    `all_zero` degenerate beats every real candidate on `mae_games` and loses on `crps`, and a report
    that hid MAE would hide the evidence for its own metric choice. `brier_play` is the calibration of
    the zero atom alone, which is the term this whole story is about."""
    p = np.atleast_2d(np.asarray(pmf, dtype=float))
    yy = np.clip(np.rint(pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(dtype=float)),
                 0, GAMES_MAX)
    st = pmf_stats(p)
    crps = discrete_crps(p, yy)
    played = (yy >= 1).astype(float)
    out = {
        "n": int(len(yy)),
        "crps": round(float(np.mean(crps)), 4),
        "mae_games": round(float(np.mean(np.abs(st["e_games"] - yy))), 3),
        "rmse_games": round(float(np.sqrt(np.mean((st["e_games"] - yy) ** 2))), 3),
        "bias_games": round(float(np.mean(st["e_games"] - yy)), 3),
        "brier_play": round(float(np.mean((st["p_play"] - played) ** 2)), 4),
        "mean_e_games": round(float(np.mean(st["e_games"])), 3),
        "mean_p_play": round(float(np.mean(st["p_play"])), 4),
        "mean_sd_games": round(float(np.mean(st["sd_games"])), 3),
        "distinct_pmf_frac": round(float(len({tuple(np.round(r, 4)) for r in p})) / max(1, len(p)), 4),
    }
    if positions is not None:
        pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
        for q in sorted(set(pos.tolist())):
            sel = pos == q
            if sel.sum() < 3:
                continue
            out[f"crps_{q}"] = round(float(np.mean(crps[sel])), 4)
            out[f"n_{q}"] = int(sel.sum())
            out[f"mae_{q}"] = round(float(np.mean(np.abs(st["e_games"][sel] - yy[sel]))), 3)
            out[f"zero_rate_{q}"] = round(float(np.mean(yy[sel] == 0)), 4)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pre-season features — every one known BEFORE the rookie season starts
# ══════════════════════════════════════════════════════════════════════════════════════════════
def capital_tier(draft_round) -> np.ndarray:
    """Draft capital in four pre-registered bands: R1 / R2–3 / R4–5 / R6–7. Coarse because the cells
    have to survive being crossed with position AND depth rank on ~12 QBs a class."""
    r = pd.to_numeric(pd.Series(draft_round), errors="coerce").to_numpy(dtype=float)
    out = np.full(len(r), "R6-7", dtype=object)
    out[r <= 5] = "R4-5"
    out[r <= 3] = "R2-3"
    out[r <= 1] = "R1"
    return out


def depth_tier(depth_rank, has_depth=None) -> np.ndarray:
    """Week-1 depth-chart rank as a tier: `1` / `2` / `3+` / `none`.

    ⚠️ `none` — no week-1 depth-chart row at all — is a REAL tier, not missing data, and it is the most
    informative one for QBs (measured 2016–2025: 85% of rookie QBs with no week-1 row played zero
    games, against 0% of QB1s). Treating it as missing and imputing would delete the story's strongest
    single signal. The honest caveat lives in the report, not in the encoding: the historical proxy is
    the WEEK-1 chart, while the live board reads an August `stg_nfl_depth_charts_current` snapshot, so
    the proxy is marginally FRESHER than the served signal."""
    r = pd.to_numeric(pd.Series(depth_rank), errors="coerce").to_numpy(dtype=float)
    have = (np.isfinite(r) if has_depth is None
            else pd.to_numeric(pd.Series(has_depth), errors="coerce").to_numpy(dtype=float) > 0)
    out = np.full(len(r), "none", dtype=object)
    ok = have & np.isfinite(r)
    out[ok & (r >= 3)] = "3+"
    out[ok & (r == 2)] = "2"
    out[ok & (r <= 1)] = "1"
    return out


def availability_features(frame: pd.DataFrame) -> pd.DataFrame:
    """The derived pre-season predictors, added to a rookie frame. Pure and idempotent."""
    out = frame.copy()
    overall = pd.to_numeric(out.get("draft_overall"), errors="coerce")
    out["log_overall"] = np.log(overall.clip(lower=1).fillna(300.0))
    rnd = pd.to_numeric(out.get("draft_round"), errors="coerce").fillna(7.0)
    out["draft_round"] = rnd
    out["is_top10"] = (overall.fillna(300.0) <= 10).astype(float)
    out["is_day1"] = (rnd <= 1).astype(float)
    dr = pd.to_numeric(out.get("depth_rank"), errors="coerce")
    has = dr.notna()
    out["has_depth"] = has.astype(float)
    out["depth_rank1"] = (has & (dr <= 1)).astype(float)
    out["depth_rank2"] = (has & (dr == 2)).astype(float)
    out["depth_rank3plus"] = (has & (dr >= 3)).astype(float)
    out["projected_nfl_z"] = pd.to_numeric(out.get("projected_nfl_z"), errors="coerce").fillna(0.0)
    out["_capital_tier"] = capital_tier(rnd)
    out["_depth_tier"] = depth_tier(dr)
    return out


def block_features(blocks: tuple[str, ...]) -> tuple[str, ...]:
    """The flat feature list for a block selection. `capital` is always included — draft capital is the
    backbone of every published rookie model and a form without it is not one we pre-registered."""
    out: list[str] = list(FEATURE_BLOCKS[ALWAYS_ON_BLOCK])
    for b in blocks:
        if b == ALWAYS_ON_BLOCK:
            continue
        out.extend(FEATURE_BLOCKS[b])
    return tuple(dict.fromkeys(out))


def _design(frame: pd.DataFrame, feats: tuple[str, ...],
            cols: tuple[str, ...] | None = None) -> tuple[np.ndarray, tuple[str, ...]]:
    """Numeric design = the selected features + one-hot position, in a FIXED column order so a scoring
    frame missing a position still aligns with the fitted model."""
    d = frame.reindex(columns=list(feats)).apply(pd.to_numeric, errors="coerce")
    pos = frame["position_group"].astype(str).str.upper()
    for p in POSITIONS:
        d[f"_pos_{p}"] = (pos == p).astype(float)
    if cols:
        d = d.reindex(columns=list(cols))
    x = d.to_numpy(dtype=float)
    med = np.zeros(x.shape[1])
    present = np.isfinite(x).any(axis=0)
    if present.any():
        med[present] = np.nanmedian(x[:, present], axis=0)
    bad = np.where(~np.isfinite(x))
    if len(bad[0]):
        x[bad] = med[bad[1]]
    return x, tuple(d.columns)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The prior
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class AvailabilityPrior:
    """One pre-registered availability form, fitted IN-FOLD on prior draft classes.

    `fit(train)` reads `rookie_games` (the FULL drafted population — a rookie who never played is a
    REAL 0, LEFT-joined, never an inner join on games ≥ 1; that filter is exactly what NF1.4 documented
    as the survivorship bug and what NF1.9 re-learned on veterans). `pmf(frame)` returns an (n, 18)
    block of predictive PMFs over games.

    A form that cannot fit for a position falls back to that position's empirical PMF and RECORDS it in
    `fallback_positions_` — a silently-degraded row would let a candidate satisfy a per-position claim
    while BEING the null at the position the claim was written for (the NF1.8 fallback-mask lesson)."""

    form: str = "pos_empirical"
    tier: str = "round"
    blocks: tuple[str, ...] = ("capital",)
    blend: float = 1.0
    eb_k: float = EB_K

    # ── fitted state ───────────────────────────────────────────────────────────────────────
    pos_pmf_: dict = field(default_factory=dict)          # position -> PMF over 0..17 (the null)
    pos_play_pmf_: dict = field(default_factory=dict)     # position -> PMF conditional on games ≥ 1
    pos_games_: dict = field(default_factory=dict)        # position -> realized games sample
    pos_mean_: dict = field(default_factory=dict)         # position -> mean realized games
    pool_pmf_: np.ndarray | None = None
    tier_pmf_: dict = field(default_factory=dict)         # (position, tier) -> EB-shrunk PMF
    coef_: dict = field(default_factory=dict)             # linear/logistic coefficients
    cols_: tuple = ()
    model_: object = None
    n_fit_: int = 0
    fallback_positions_: tuple = ()

    # ── fit ────────────────────────────────────────────────────────────────────────────────
    def fit(self, train: pd.DataFrame) -> "AvailabilityPrior":
        d = availability_features(train)
        pos = d["position_group"].astype(str).str.upper().to_numpy()
        y = pd.to_numeric(d["rookie_games"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(y)
        d, pos, y = d[ok].copy(), pos[ok], y[ok]
        self.n_fit_ = int(len(y))
        self.pool_pmf_ = empirical_pmf(y)

        thin: list[str] = []
        for p in np.unique(pos):
            sel = pos == p
            if sel.sum() < MIN_POS_ROWS:
                thin.append(str(p))
                continue
            g = y[sel]
            self.pos_games_[p] = g
            self.pos_pmf_[p] = empirical_pmf(g)
            self.pos_mean_[p] = float(np.mean(g))
            played = g[g >= 1]
            self.pos_play_pmf_[p] = (empirical_pmf(played) if len(played) >= 5
                                     else empirical_pmf(g))
        self.fallback_positions_ = tuple(sorted(thin))

        if self.form == "tier_empirical":
            key = self._tier_key(d)
            for p in self.pos_pmf_:
                prior = self.pos_pmf_[p]
                for t in np.unique(key[pos == p]):
                    cell = y[(pos == p) & (key == t)]
                    n = len(cell)
                    self.tier_pmf_[(p, str(t))] = (
                        (n * empirical_pmf(cell) + self.eb_k * prior) / (n + self.eb_k)
                        if n else prior)
        elif self.form == "hurdle_logit":
            self._fit_logit(d, y)
        elif self.form == "haircut_ratio":
            self._fit_ratio(d, y)
        elif self.form == "learned_gbm":
            self._fit_gbm(d, y)
        return self

    def _tier_key(self, d: pd.DataFrame) -> np.ndarray:
        if self.tier == "round":
            return d["_capital_tier"].to_numpy()
        if self.tier == "depth":
            return d["_depth_tier"].to_numpy()
        return (d["_capital_tier"].astype(str) + "|" + d["_depth_tier"].astype(str)).to_numpy()

    def _fit_logit(self, d: pd.DataFrame, y: np.ndarray) -> None:
        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError:                                   # pragma: no cover - sklearn is a dep
            return
        x, cols = _design(d, block_features(self.blocks))
        self.cols_ = cols
        played = (y >= 1).astype(int)
        if played.min() == played.max():
            return                                            # degenerate cohort → the null PMF
        # A modest L2 — the cells behind a rookie-QB logistic are tiny and an unregularised fit on a
        # near-separable feature (depth rank 1 ⇒ always plays) would emit probabilities of 0 and 1.
        m = LogisticRegression(C=1.0, max_iter=2000)
        m.fit(x, played)
        self.model_ = m

    def _fit_ratio(self, d: pd.DataFrame, y: np.ndarray) -> None:
        """NF-D11's `ratio` family: a multiplicative haircut on the player's OWN expected games. Fitted
        as least squares on log1p(games) so the haircut is multiplicative in the natural scale."""
        x, cols = _design(d, block_features(self.blocks))
        self.cols_ = cols
        xx = np.column_stack([np.ones(len(x)), x])
        beta, *_ = np.linalg.lstsq(xx, np.log1p(np.clip(y, 0.0, None)), rcond=None)
        self.coef_ = {"beta": beta.tolist()}

    def _fit_gbm(self, d: pd.DataFrame, y: np.ndarray) -> None:
        try:
            from sklearn.ensemble import GradientBoostingRegressor
        except ImportError:                                   # pragma: no cover - sklearn is a dep
            return
        x, cols = _design(d, block_features(self.blocks))
        self.cols_ = cols
        # Deliberately shallow + heavily regularised: ~500 training rows across four positions is
        # nowhere near enough for a deep tree, and an over-fit foil makes for a dishonest bake-off
        # (the NF1.4 convention, inherited verbatim).
        self.model_ = GradientBoostingRegressor(
            n_estimators=220, learning_rate=0.04, max_depth=2, min_samples_leaf=25,
            subsample=0.8, random_state=17).fit(x, np.clip(y, 0.0, None))

    # ── predict ────────────────────────────────────────────────────────────────────────────
    def pmf(self, frame: pd.DataFrame) -> np.ndarray:
        d = availability_features(frame)
        pos = d["position_group"].astype(str).str.upper().to_numpy()
        null = np.array([self.pos_pmf_.get(p, self.pool_pmf_ if self.pool_pmf_ is not None
                                           else np.full(GAMES_MAX + 1, 1.0 / (GAMES_MAX + 1)))
                         for p in pos], dtype=float)
        if self.form == "pos_empirical":
            return null
        cand = null.copy()

        if self.form == "tier_empirical":
            key = self._tier_key(d)
            for i, (p, t) in enumerate(zip(pos, key)):
                got = self.tier_pmf_.get((p, str(t)))
                if got is not None:
                    cand[i] = got
        elif self.form == "hurdle_logit" and self.model_ is not None:
            x, _ = _design(d, block_features(self.blocks), cols=self.cols_)
            p_play = np.clip(self.model_.predict_proba(x)[:, 1], 1e-6, 1 - 1e-6)
            for i, p in enumerate(pos):
                shape = self.pos_play_pmf_.get(p)
                if shape is None:
                    continue
                row = np.zeros(GAMES_MAX + 1)
                row[1:] = p_play[i] * shape[1:] / max(shape[1:].sum(), 1e-12)
                row[0] = 1.0 - p_play[i]
                cand[i] = row
        elif self.form in ("haircut_ratio", "learned_gbm"):
            mean = self._expected_games(d)
            for i, p in enumerate(pos):
                base = self.pos_games_.get(p)
                mu = self.pos_mean_.get(p)
                if base is None or not mu or not np.isfinite(mean[i]):
                    continue
                cand[i] = transport_pmf(base, float(mean[i]) / float(mu))

        return blend_pmf(cand, null, self.blend)

    def _expected_games(self, d: pd.DataFrame) -> np.ndarray:
        if self.form == "haircut_ratio":
            if not self.coef_:
                return np.full(len(d), np.nan)
            x, _ = _design(d, block_features(self.blocks), cols=self.cols_)
            beta = np.asarray(self.coef_["beta"], dtype=float)
            return np.clip(np.expm1(np.column_stack([np.ones(len(x)), x]) @ beta), 0.0, GAMES_MAX)
        if self.model_ is None:
            return np.full(len(d), np.nan)
        x, _ = _design(d, block_features(self.blocks), cols=self.cols_)
        return np.clip(self.model_.predict(x), 0.0, GAMES_MAX)

    def stats(self, frame: pd.DataFrame) -> pd.DataFrame:
        """`p_play` / `p_short` / `e_games` / `sd_games` for a frame — the per-player availability read
        the interval leg conditions on."""
        return pd.DataFrame(pmf_stats(self.pmf(frame)), index=frame.index)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Anchors — two-sided, and every one REQUIRED (a missing anchor passes on NOTHING)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def degenerate_pmf(kind: str, n: int, mean_games: float = 0.0) -> np.ndarray:
    """The DEGENERATE CEILINGS that must LOSE.

      · `all_zero` — every rookie projected to play zero games. ⭐ It WINS MAE on this cohort (MAE is
        minimised at the conditional median and the median rookie QB plays 3 games with 35% exact
        zeros), which is the whole reason the selection metric is CRPS. A metric a nihilist wins
        cannot select a projection (CLAUDE.md, NF-D11 verbatim).
      · `all_mean` — every rookie projected at the pooled mean, as a point mass. Maximally "unbiased"
        in level and useless in shape; it must lose a PROPER score."""
    row = np.zeros(GAMES_MAX + 1)
    if kind == "all_zero":
        row[0] = 1.0
    elif kind == "all_mean":
        row[int(np.clip(np.rint(mean_games), 0, GAMES_MAX))] = 1.0
    else:
        raise ValueError(f"unknown degenerate: {kind!r}")
    return np.tile(row, (int(n), 1))


def oracle_pmf(test: pd.DataFrame) -> np.ndarray:
    """The ORACLE FLOOR — the held-out class's OWN realized per-position games distribution. It peeks;
    nothing may beat it.

    ⚠️ SAME-FAMILY BY CONSTRUCTION (NF1.7 (b)): it is an empirical PMF, the same family as the null and
    the tier arms, so "peeking can only help" is well-posed on family. It is NOT matched on SAMPLE
    SIZE — one draft class is ~80 rows against ~500 training rows — which is why the harness also scores
    `matched_n_candidate` (NF1.9 (f)) and gates the floor on the oracle beating THAT."""
    pos = test["position_group"].astype(str).str.upper().to_numpy()
    y = pd.to_numeric(test["rookie_games"], errors="coerce").to_numpy(dtype=float)
    pool = empirical_pmf(y)
    by = {p: empirical_pmf(y[pos == p]) for p in np.unique(pos) if (pos == p).sum() >= 3}
    return np.array([by.get(p, pool) for p in pos], dtype=float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered search grid (EVERY config counts toward PBO/DSR — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs(*, smoke: bool = False) -> list[dict]:
    """The full pre-registered candidate list, fixed before any result was read.

    `smoke=True` keeps one config per form so a wiring run stays seconds; it writes to `*_smoke`
    artifacts so it can never be mistaken for the real search."""
    cfgs: list[dict] = [{"label": "pos_empirical (NULL)", "form": "pos_empirical",
                         "blocks": ("capital",), "blend": 0.0}]
    blends = (1.0,) if smoke else BLEND_GRID
    tiers = TIERS[:1] if smoke else TIERS
    blocksets = BLOCK_SETS[:1] if smoke else BLOCK_SETS
    for t in tiers:
        for b in blends:
            cfgs.append({"label": f"tier_empirical[{t}] · blend {b:g}", "form": "tier_empirical",
                         "tier": t, "blocks": ("capital",), "blend": b})
    for form in ("hurdle_logit", "haircut_ratio", "learned_gbm"):
        for blocks in blocksets:
            for b in blends:
                cfgs.append({"label": f"{form}[{'+'.join(blocks)}] · blend {b:g}", "form": form,
                             "blocks": blocks, "blend": b})
    return cfgs


def config_key(cfg: dict) -> str:
    return (f"{cfg['form']}[{cfg.get('tier', '')}|{'+'.join(cfg.get('blocks', ()))}]"
            f"@{cfg.get('blend', 1.0):g}")


def make_prior(cfg: dict) -> AvailabilityPrior:
    return AvailabilityPrior(form=cfg["form"], tier=cfg.get("tier", "round"),
                             blocks=tuple(cfg.get("blocks", ("capital",))),
                             blend=float(cfg.get("blend", 1.0)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict
# ══════════════════════════════════════════════════════════════════════════════════════════════
def availability_verdict(*, beats_null: bool, oracle_respected: bool, degenerates_lose: bool,
                         permutation_beaten: bool, pbo: float | None, dsr: float | None,
                         fdr_pass: bool, pbo_max: float = PBO_MAX,
                         dsr_min: float = DSR_MIN) -> dict:
    """The SHIP decision for the availability prior itself (leg 1).

    A prior is only carried into the interval leg when it beats the position-empirical null on the
    pre-registered proper score, respects BOTH sanity anchors, beats its own permutation, and survives
    the deflation. Anything else is a recorded NULL — which this story pre-registered as a legitimate
    outcome, not a failure. ⚠️ Passing here does NOT ship anything on its own: the story's GATE is what
    the prior does to held-out rookie-QB COVERAGE, decided separately in `interval_verdict`."""
    checks = {
        "beats_null": bool(beats_null),
        "oracle_respected": bool(oracle_respected),
        "degenerates_lose": bool(degenerates_lose),
        "permutation_beaten": bool(permutation_beaten),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "fdr_ok": bool(fdr_pass),
    }
    return {"prior_is_real": all(checks.values()), **checks}


def interval_verdict(*, qb_coverage_base: float | None, qb_coverage_arm: float | None,
                     floors_met: bool, beats_base_interval_score: bool,
                     pbo: float | None, point_invariant: bool,
                     pbo_max: float = PBO_MAX) -> dict:
    """⭐ THE STORY'S GATE (leg 2). The availability prior SHIPS into the served rookie band only when
    it (a) leaves every per-position coverage floor met, (b) does not degrade the primary interval
    score, (c) survives the deflation, (d) moves rookie-QB coverage UP, and (e) leaves the rookie POINT
    projection byte-identical (NF1.7/NF1.8 discipline — a band story must not smuggle a point change).

    ⚠️ A failure here is the pre-registered NULL: the rookie-QB interval variance is irreducible at this
    sample size, the floor does NOT move (E2.1-r; NF1.8 §1), and the shipped NF1.8 band stands."""
    lifts = (isinstance(qb_coverage_base, (int, float)) and isinstance(qb_coverage_arm, (int, float))
             and qb_coverage_arm > qb_coverage_base)
    checks = {
        "qb_coverage_improves": bool(lifts),
        "floors_met": bool(floors_met),
        "no_interval_score_harm": bool(beats_base_interval_score),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "point_invariant": bool(point_invariant),
    }
    return {"ship": all(checks.values()), **checks}
