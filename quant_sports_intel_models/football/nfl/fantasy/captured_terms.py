"""captured_terms.py — NF-C0e: project the per-player scoring terms real leagues score and we did not.

🎯 WHY THIS MODULE EXISTS. NF-C0/NF-C0b built machinery that classifies every term a league scores
as APPLIED / DERIVED / CAPTURED, mechanically, against the projection columns that actually exist
(`fantasy_engine/settings.resolve_scoring`). CAPTURED is the honest verdict — "your league scores
this, our board ignores it, and here we are telling you so" — but it was always meant as a TODO,
not an end state. The first real platform imports (NF-C0d telemetry) turned the abstract worry into
a concrete list, and this module is the part of that list which lives on the OFFENSIVE player line.

⚖️ **THE DISCIPLINE THAT MAKES THIS HONEST RATHER THAN COSMETIC.** Projecting a term so that it is
"applied" is NOT automatically an improvement. A term projected with no skill still MOVES THE BOARD
— it just moves it on noise while wearing the "applied" label, which is strictly worse than an
honest "captured", because the user now believes we modelled it. So every term here had to clear a
HELD-OUT gate before it was allowed to exist as a column:

    a term graduates only if its projection beats a DEGENERATE baseline — every player assigned his
    position's league-mean count — on BOTH mean-absolute and root-mean-square error, in enough
    walk-forward folds to satisfy `cv_power.fold_consistency_clause`.

Requiring BOTH losses is not belt-and-braces; it is the load-bearing part. These targets are
heavily zero-inflated (67% of players fumble zero times in a season), and MAE on a zero-heavy target
is minimised at the CONDITIONAL MEDIAN — so it PAYS FOR PESSIMISM and can rank a systematically
under-projecting arm first (the NF-D11 inversion). `fum` is the term that actually tripped it: it
wins MAE in 7/7 held-out seasons and LOSES RMSE in 7/7. A single-loss gate would have shipped it.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT GRADUATED, AND WHAT DID NOT (measured — see `ablation_results/nf_c0e_captured_terms.md`)
────────────────────────────────────────────────────────────────────────────────────────────────
GRADUATED (7/7 held-out seasons on both losses; the clause requires 6):

  `two_pt`        +22.7% MAE / +4.9% RMSE vs the degenerate.  Two-point conversions scale with a
                  player's TOUCHDOWN volume, which is the thing MVP-1 forecasts best.
  `pass_td_40p`   +32.9% / +20.8%      the strongest of the family (rank corr 0.67)
  `rec_td_40p`    +24.8% / +7.1%
  `rush_td_40p`   +22.9% / +4.9%

STAYED CAPTURED, with the evidence:

  `fum` (total)   MAE wins 7/7 but RMSE LOSES 7/7 — a systematic sign disagreement, not noise. 67%
                  of players record zero fumbles and realized SD (1.5-1.9) is ~3x the projection's
                  (0.46-0.57), so the touch-rate arm cannot track the tail and MAE is simply
                  rewarding it for being small. Graduating it needs a real fumble model, not a
                  rescaling of `proj_fumbles_lost` (itself a `touches x 0.006` heuristic).
  `st_player_td`  we project no return volume of ANY kind, so the only arm constructible IS the
                  league mean — i.e. it is IDENTICAL to the degenerate (measured gain exactly
                  0.000, by construction). A mechanism that cannot act is a finding, not an
                  omission (NF1.9): this needs a return-usage projection first, not a better fit.
  `fumble_rec_td` same shape; realized mean 0.004/player-season.

⚠️ **WHAT THE LONG-TD TERMS DO AND DO NOT CLAIM.** `<x>_td_40p = proj_<x>_td x league_40p_share`,
where the share is measured IN-FOLD per play type (~0.13 of passing TDs, ~0.06 of rushing TDs, and
a receiving TD's length IS its passing play's, which is why one measured pass share serves both).
The share is a LEAGUE CONSTANT, deliberately: we have no evidence that the 40+ SHARE of a player's
touchdowns is a per-player skill, and inventing a per-player share would be manufacturing precision.
So the honest claim is "we apply your league's long-TD bonus in proportion to the touchdowns we
project", NOT "we predict who scores long touchdowns". It still beats the degenerate decisively
because TOUCHDOWN VOLUME varies enormously across players and is forecastable — which is exactly
the skill being leaned on, and it is one we already have.

Everything here is PURE (frames in, frames out, no IO) so it is covered by the fast gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MODEL_VERSION = "nfl_fantasy_captured_terms_v1"

# The 40+ yard touchdown bonus terms → the projected volume column each is proportional to.
# NOTE `rec_td_40p` reads the PASS share: a 45-yard touchdown pass is ONE play that is a 40+ passing
# TD for the quarterback and a 40+ receiving TD for the receiver, so there is one share, not two.
LONG_TD_TERMS: dict[str, tuple[str, str]] = {
    "proj_pass_td_40p": ("proj_pass_td", "pass"),
    "proj_rush_td_40p": ("proj_rush_td", "rush"),
    "proj_rec_td_40p":  ("proj_rec_td",  "pass"),
}

# Two-point conversions scale with total touchdown volume (a 2-pt try only follows a TD).
TWO_PT_VOLUME_COLS = ("proj_pass_td", "proj_rush_td", "proj_rec_td")

GRADUATED_COLS = ("proj_two_pt", *LONG_TD_TERMS)

# Offline fallbacks, measured 2010-2025. The runner re-measures both IN-FOLD from the training
# window, which matters more than it looks: the shares are NOT stationary (the pass share ran
# 0.149 in 2010 and 0.090 in 2025), so a pinned constant would silently rot.
LEAGUE_LONG_TD_SHARE = {"pass": 0.1310, "rush": 0.0631}
LEAGUE_TWO_PT_RATE = 0.0370          # two-point conversions per (pass + rush + rec) touchdown

_MIN_DENOM = 1e-9


def _num(s) -> np.ndarray:
    return pd.to_numeric(pd.Series(s), errors="coerce").fillna(0.0).to_numpy(dtype=float)


@dataclass
class CapturedTermRates:
    """The in-fold league rates the graduated terms are projected with.

    Every field is a RATE PER UNIT OF PROJECTED VOLUME, never a per-player level — that is the
    whole design (see the module docstring): the per-player variation comes from a volume column
    MVP-1 already forecasts, and the rate is a measured league constant we do not pretend to
    resolve per player."""

    long_td_share: dict = field(default_factory=lambda: dict(LEAGUE_LONG_TD_SHARE))
    two_pt_rate: float = LEAGUE_TWO_PT_RATE
    n_seasons: int = 0
    fitted_through: int | None = None

    def to_dict(self) -> dict:
        return {"long_td_share": {k: round(float(v), 5) for k, v in sorted(self.long_td_share.items())},
                "two_pt_rate": round(float(self.two_pt_rate), 5),
                "n_seasons": int(self.n_seasons),
                "fitted_through": self.fitted_through}


def fit_captured_term_rates(history: pd.DataFrame, base_season: int | None = None
                            ) -> CapturedTermRates:
    """Measure the league rates from history STRICTLY BEFORE the projection season.

    `history` — one row per (season, player_id) carrying the realized counts `two_pt`,
    `pass_td_40p`, `rush_td_40p`, `pass_td`, `rush_td`, `rec_td`.

    ⚠️ RAISES on an empty/unusable history rather than silently returning the offline fallback. A
    fitter that quietly succeeds on nothing is the NF1.7 vacuous-anchor failure: every downstream
    check would then pass against constants nobody measured.
    """
    if history is None or history.empty:
        raise ValueError(
            "fit_captured_term_rates: empty history — refusing to fit. Falling back to the pinned "
            "constants here would make every rate look measured when none of them were.")
    h = history if base_season is None else history[_num(history["season"]) <= int(base_season)]
    if h.empty:
        raise ValueError(
            f"fit_captured_term_rates: no seasons at or before {base_season} — refusing to fit.")

    pass_td = float(np.sum(_num(h["pass_td"])))
    rush_td = float(np.sum(_num(h["rush_td"])))
    rec_td = float(np.sum(_num(h["rec_td"])))
    share = dict(LEAGUE_LONG_TD_SHARE)
    if pass_td > _MIN_DENOM:
        share["pass"] = float(np.sum(_num(h["pass_td_40p"]))) / pass_td
    if rush_td > _MIN_DENOM:
        share["rush"] = float(np.sum(_num(h["rush_td_40p"]))) / rush_td
    total_td = pass_td + rush_td + rec_td
    two_pt = (float(np.sum(_num(h["two_pt"]))) / total_td if total_td > _MIN_DENOM
              else LEAGUE_TWO_PT_RATE)
    return CapturedTermRates(long_td_share=share, two_pt_rate=two_pt,
                             n_seasons=int(pd.Series(h["season"]).nunique()),
                             fitted_through=None if base_season is None else int(base_season))


def project_captured_terms(projections: pd.DataFrame, rates: CapturedTermRates) -> pd.DataFrame:
    """Add the GRADUATED captured-term columns to an MVP-1 season-projection frame.

    Returns a COPY with `proj_two_pt` + the three `proj_<x>_td_40p` columns. Terms that did not
    clear the held-out gate are deliberately absent — `resolve_scoring` then reports them CAPTURED
    against the real columns, which is the honest answer and is produced by code rather than by a
    label anyone wrote.

    ⭐ `proj_two_pt` is OVERWRITTEN, not filled. MVP-1 declares the column and sets it to NaN — a
    column that exists but carries no value. That was already honest downstream (the exporter drops
    an all-null field, so `two_pt` reported CAPTURED) but it is a trap: a future consumer reading
    the frame directly would see a real column name and score `weight x NaN`. Writing a measured
    value closes that gap as well as graduating the term.
    """
    out = projections.copy()
    td_volume = np.zeros(len(out), dtype=float)
    for col in TWO_PT_VOLUME_COLS:
        if col in out.columns:
            td_volume = td_volume + _num(out[col])
    out["proj_two_pt"] = td_volume * float(rates.two_pt_rate)

    for out_col, (vol_col, play_type) in LONG_TD_TERMS.items():
        if vol_col not in out.columns:
            # No volume column ⇒ no bonus column. Never a zero: a zeroed bonus column would be
            # APPLIED-and-wrong ("this player scores no long touchdowns"), where an ABSENT one is
            # correctly reported CAPTURED.
            continue
        out[out_col] = _num(out[vol_col]) * float(rates.long_td_share.get(play_type, 0.0))
    return out


def degenerate_baseline(realized_history: pd.DataFrame, positions, column: str) -> np.ndarray:
    """The DEGENERATE arm every graduated term had to beat: each player gets his POSITION's
    in-fold league-mean count.

    Exposed as a first-class function, not buried in a one-off script, because the story's rule is
    that a term stays captured unless it beats this — so the thing it must beat has to be
    reproducible, testable, and re-runnable next season."""
    if realized_history is None or realized_history.empty:
        raise ValueError("degenerate_baseline: empty history — the anchor a gate rests on may "
                         "never be silently unfittable (NF1.7 (a)).")
    overall = float(np.mean(_num(realized_history[column])))
    means = {}
    if "position" in realized_history.columns:
        for pos, d in realized_history.groupby("position"):
            means[str(pos)] = float(np.mean(_num(d[column])))
    return np.array([means.get(str(p), overall) for p in pd.Series(positions).astype(str)],
                    dtype=float)


__all__ = [
    "GRADUATED_COLS",
    "LEAGUE_LONG_TD_SHARE",
    "LEAGUE_TWO_PT_RATE",
    "LONG_TD_TERMS",
    "MODEL_VERSION",
    "TWO_PT_VOLUME_COLS",
    "CapturedTermRates",
    "degenerate_baseline",
    "fit_captured_term_rates",
    "project_captured_terms",
]
