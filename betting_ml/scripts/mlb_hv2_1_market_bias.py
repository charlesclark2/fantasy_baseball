#!/usr/bin/env python3
"""MLB-HV2-1 — Bovada H2H market-bias backtest (MODEL-INDEPENDENT).

Question: does Bovada's recreational H2H pricing carry a persistent,
pre-registrable SEGMENT bias (the public overweighting favorites / home teams /
marquee clubs) that a flat-stake RULE would have exploited historically?

`best_alpha = 0`. Nothing here is a bet, a tout, or a served change. The output
is a MEASUREMENT with a verdict. A surviving segment is recorded as a CANDIDATE
for an operator-gated forward paper-trade accrual; a classified null CLOSES the
market-bias direction.

⛔ **MODEL-INDEPENDENCE IS A CHECKABLE PROPERTY OF THIS FILE.** No Credence model
artifact, no learner library, and no serving/prediction module may appear in this
module's transitive import closure. `betting_ml/tests/test_mlb_hv2_1_market_bias.py`
enforces it by importing this module in a SUBPROCESS and inspecting `sys.modules`
(an in-process check would be vacuous — pytest itself has already imported half
the scientific stack). The only reads are stored ODDS and stored GAME RESULTS.

Everything after `extract()` is a PURE function of the extracted frame, so the
whole study reproduces offline from the committed fixture (reproduction pin 1e-9).

Run
---
    uv run python -m betting_ml.scripts.mlb_hv2_1_market_bias --audit   # coverage only
    uv run python -m betting_ml.scripts.mlb_hv2_1_market_bias           # full study
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from betting_ml.utils.cv_power import classify_null, fold_consistency_clause
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv

# ═════════════════════════════════════════════════════════════════════════════
# THE PRE-REGISTRATION.  Frozen at node 2, BEFORE any scoring.
# `ablation_results/mlb_hv2_1_prereg.md` is the human-readable twin of this block
# and `test_prereg_document_matches_the_registered_family` pins them together, so
# neither can drift from the other.
# ═════════════════════════════════════════════════════════════════════════════

STORY = "MLB-HV2-1"

# ── Population (node 1 re-registered the SMALLER window explicitly) ───────────
BOOKMAKER = "bovada"
MARKET = "h2h"
SPORT_KEY = "baseball_mlb"
GAME_TYPE = "R"
#: Scheduled first pitch must fall in these UTC hours. Node 1 measured the store
#: at 0.93-0.96 coverage inside this band and 0.098-0.119 outside it (the
#: historical backfill captured ZERO post-00:00-UTC games in 5 of 6 seasons — the
#: INC-22 UTC-date class). Restricting makes the sample a near-census of a named
#: population instead of an unknown-selection mixture.
FIRST_PITCH_UTC_HOURS = (3, 23)
#: A season enters the fold design iff its EARLY-STRATUM coverage clears this.
#: Measured: 2020 .897 / 2021 .954 / 2022 .918 / 2023 .070 / 2024 .983 /
#: 2025 .999 / 2026 .899. The threshold is NOT load-bearing — the partition is
#: identical anywhere in [0.08, 0.89].
MIN_SEASON_COVERAGE = 0.50
SEASONS = (2020, 2021, 2022, 2024, 2025, 2026)
EXCLUDED_SEASONS = (2023,)

#: The public clubs, declared in advance on an EXTERNAL basis (top US media
#: markets + the heaviest national-broadcast presence). Fixed before scoring; it
#: is a judgment call and is recorded as one. ⚠️ node 1 measured that West-Coast
#: clubs appear disproportionately as ROAD teams (LAD 97 home / 234 away), which
#: is why NO marquee x home/away interaction arm is registered.
MARQUEE_TEAMS = ("ATL", "BOS", "CHC", "LAD", "NYM", "NYY")

#: Overround removal, applied uniformly: proportional / multiplicative.
#:     p_i = (1/d_i) / sum_j (1/d_j)
#: ⭐ The PRIMARY metric (ROI) does NOT depend on this choice — it uses the actual
#: American price and the actual result. Only the CALIBRATION diagnostic (realized
#: win rate vs implied) does, which is why the de-vig method can never manufacture
#: the headline. Shin is registered as a declared sensitivity for that diagnostic
#: only, and gates nothing.
NOVIG_METHOD = "proportional"
NOVIG_SENSITIVITY = "shin"

# ── Gate thresholds ──────────────────────────────────────────────────────────
BH_ALPHA = 0.05
MAX_PBO = 0.20
MIN_DSR = 0.95
FOLD_ALPHA = 0.20          # cv_power.fold_consistency_clause default
PBO_BUCKET = "season_month"

# ═════════════════════════════════════════════════════════════════════════════
# The registered arm family.  CLOSED and SHORT — every entry is a directional
# hypothesis ("bet the side the public does NOT like"), so each arm is a ONE-SIDED
# test.  ⛔ No post-hoc trims (MH2.2), no mirrored "follow" twins (they would
# double the multiplicity for no new hypothesis), and ⛔ a significantly NEGATIVE
# arm is recorded as a FINDING but is never promoted — flipping a registered
# direction after seeing the sign is the E2.1-r inversion.
#
# `day/night` was CONSIDERED and DECLINED: it carries no directional public-bias
# hypothesis, so registering it would spend multiplicity on a fishing axis.
# ═════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Arm:
    arm_id: str
    family: str
    hypothesis: str
    #: (frame) -> boolean mask of the games this arm bets
    eligible: Callable[[pd.DataFrame], pd.Series]
    #: (frame) -> boolean Series, True = bet the HOME side, False = bet the AWAY side
    bet_home: Callable[[pd.DataFrame], pd.Series]


def _fav_is_home(f: pd.DataFrame) -> pd.Series:
    return f["home_decimal"] < f["away_decimal"]


def _has_fav(f: pd.DataFrame) -> pd.Series:
    """Non-tie games only. A pick'em (identical decimals) has no favorite, so it
    is excluded from every arm that references favorite/dog status."""
    return f["home_decimal"] != f["away_decimal"]


def _fav_american(f: pd.DataFrame) -> pd.Series:
    return np.where(_fav_is_home(f), f["home_american"], f["away_american"])


def _marquee_home(f: pd.DataFrame) -> pd.Series:
    return f["home_team"].isin(MARQUEE_TEAMS)


def _marquee_away(f: pd.DataFrame) -> pd.Series:
    return f["away_team"].isin(MARQUEE_TEAMS)


def _exactly_one_marquee(f: pd.DataFrame) -> pd.Series:
    return _marquee_home(f) ^ _marquee_away(f)


REGISTERED_ARMS: tuple[Arm, ...] = (
    # ── Family A — favorite-longshot: the public overbets favorites, so bet the DOG ──
    Arm("dog_vs_heavy_fav", "A_favorite_longshot",
        "The public overbets HEAVY favorites (price <= -200); bet the dog.",
        lambda f: _has_fav(f) & (pd.Series(_fav_american(f), index=f.index) <= -200),
        lambda f: ~_fav_is_home(f)),
    Arm("dog_vs_mod_fav", "A_favorite_longshot",
        "The public overbets MODERATE favorites (-200 < price <= -140); bet the dog.",
        lambda f: _has_fav(f) & (pd.Series(_fav_american(f), index=f.index) > -200)
                              & (pd.Series(_fav_american(f), index=f.index) <= -140),
        lambda f: ~_fav_is_home(f)),
    Arm("dog_vs_slight_fav", "A_favorite_longshot",
        "The public overbets SLIGHT favorites (-140 < price <= -100); bet the dog.",
        lambda f: _has_fav(f) & (pd.Series(_fav_american(f), index=f.index) > -140),
        lambda f: ~_fav_is_home(f)),
    # ── Family B — home bias: the public overbets HOME teams, so bet the ROAD team ──
    Arm("road_all", "B_home_bias",
        "The public overbets HOME teams across the board; bet every road team.",
        lambda f: pd.Series(True, index=f.index),
        lambda f: pd.Series(False, index=f.index)),
    Arm("road_dog", "B_home_bias",
        "Home bias is strongest where the home side is also the favorite; bet the road DOG.",
        lambda f: _has_fav(f) & _fav_is_home(f),
        lambda f: pd.Series(False, index=f.index)),
    Arm("road_fav", "B_home_bias",
        "A road FAVORITE is under-backed because the public still leans home; bet it.",
        lambda f: _has_fav(f) & ~_fav_is_home(f),
        lambda f: pd.Series(False, index=f.index)),
    # ── Family C — marquee bias: the public overbets marquee clubs, so FADE them ──
    Arm("fade_marquee", "C_marquee_bias",
        "The public overbets marquee clubs; bet against them when exactly one side is marquee.",
        _exactly_one_marquee,
        lambda f: _marquee_away(f)),          # bet home iff the AWAY side is the marquee one
    Arm("fade_marquee_fav", "C_marquee_bias",
        "The marquee premium is largest when the marquee club is also the favorite; bet the non-marquee dog.",
        lambda f: _exactly_one_marquee(f) & _has_fav(f)
                  & (_marquee_home(f) == _fav_is_home(f)),
        lambda f: _marquee_away(f)),
)

DECLARED_FIELD_SIZE = len(REGISTERED_ARMS)          # == n_trials for the deflation gates

# ═════════════════════════════════════════════════════════════════════════════
# Anchors.  ⭐ MH2.1 (a): a DIAGNOSTIC anchor is NEVER a trial — these are excluded
# from `n_trials` AND from the cross-trial dispersion `V`. They exist to POLICE the
# metric, and letting them set the deflation bar is exactly the defect MH2.1 found.
# NF-D11: the field is anchored on BOTH sides — an oracle FLOOR nothing may beat and
# degenerate CEILINGS that must lose.
# ═════════════════════════════════════════════════════════════════════════════

ANCHORS: tuple[Arm, ...] = (
    Arm("anchor_oracle_winner", "anchor",
        "ORACLE FLOOR — bets the actual winner every game. Nothing may beat it; an arm that "
        "does is proof the metric is inverted, not a finding.",
        lambda f: pd.Series(True, index=f.index),
        lambda f: f["home_won"].astype(bool)),
    Arm("anchor_all_home", "anchor",
        "DEGENERATE CEILING — bets home every game. The exact mirror of `road_all`; scored so "
        "the home/road result cannot be read as an artifact of which side was registered.",
        lambda f: pd.Series(True, index=f.index),
        lambda f: pd.Series(True, index=f.index)),
    Arm("anchor_all_fav", "anchor",
        "DEGENERATE CEILING — bets the favorite every game. The mirror of family A.",
        _has_fav,
        _fav_is_home),
    Arm("anchor_coin_flip", "anchor",
        "NO-SKILL REFERENCE — a deterministic pseudo-random side (seeded on game_pk). Its ROI "
        "measures the vig a rule pays for showing up; a real arm must clear it, and it must be "
        "negative or the price data is wrong.",
        lambda f: pd.Series(True, index=f.index),
        lambda f: (f["game_pk"].astype("int64") * 2654435761 % 2147483647) % 2 == 0),
)

_ANCHOR_IDS = tuple(a.arm_id for a in ANCHORS)

# ═════════════════════════════════════════════════════════════════════════════
# Extraction  (the only impure function in the module)
# ═════════════════════════════════════════════════════════════════════════════

FRAME_COLUMNS = ("game_pk", "season", "game_date", "first_pitch_utc_hour",
                 "home_team", "away_team", "home_american", "away_american", "home_won")


def _extract_sql() -> str:
    """The stored-odds read. INC-23: `commence_time`, `bookmaker_last_update` and
    `stg_statsapi_games.game_date` are VARCHAR in parquet — every comparison casts
    at the use-site or DuckDB raises (it did, on the first audit pass).

    E9.52: the two sides are taken from the SAME `bookmaker_last_update` snapshot
    (a `group by` on it), never max()'d across snapshots — a cross-snapshot pair is
    the "most favourable price ever posted", which is worse than a null because it
    looks like data.

    Node 1: `ingestion_ts` is the 2026-04-23 BACKFILL time for 2020-2025, so it
    cannot be the pre-game bound. `bookmaker_last_update` is the book's own
    last-moved stamp and is strictly pre-first-pitch on every historical row."""
    return f"""
    with quotes as (
        select
            event_id,
            commence_time::timestamp                         as commence_time,
            bookmaker_last_update::timestamp                 as quote_ts,
            max(case when is_home_outcome then outcome_price_american end) as home_american,
            max(case when is_away_outcome then outcome_price_american end) as away_american
        from mart_odds_outcomes
        where bookmaker_key = '{BOOKMAKER}'
          and market_key    = '{MARKET}'
          and sport_key     = '{SPORT_KEY}'
          and outcome_price_american is not null
          and bookmaker_last_update::timestamp < commence_time::timestamp
        group by 1, 2, 3
        having count(distinct outcome_name) = 2
           and max(case when is_home_outcome then outcome_price_american end) is not null
           and max(case when is_away_outcome then outcome_price_american end) is not null
    ),
    latest as (
        select * from quotes
        qualify row_number() over (partition by event_id order by quote_ts desc) = 1
    ),
    sched as (
        select game_pk, min(game_date::timestamp) as first_pitch
        from stg_statsapi_games group by 1
    )
    select
        r.game_pk::bigint                       as game_pk,
        year(r.game_date)::int                  as season,
        r.game_date                             as game_date,
        hour(s.first_pitch)::int                as first_pitch_utc_hour,
        r.home_team                             as home_team,
        r.away_team                             as away_team,
        q.home_american::int                    as home_american,
        q.away_american::int                    as away_american,
        r.home_team_won::boolean                as home_won
    from mart_game_results r
    join sched s                     on s.game_pk = r.game_pk
    join mart_game_odds_bridge b     on b.game_pk = r.game_pk and b.event_id is not null
    join latest q                    on q.event_id = b.event_id
    where r.game_type = '{GAME_TYPE}'
      and r.home_final_score is not null
      and r.home_team_won is not null
    """


def extract() -> pd.DataFrame:
    """Read the FULL observed sample (every season, both strata). Population
    restriction happens in `restrict()` so the sensitivity read stays available."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    register_views(conn, ["mart_odds_outcomes", "mart_game_results",
                          "mart_game_odds_bridge", "stg_statsapi_games"])
    frame = conn.execute(_extract_sql()).fetch_df()
    conn.close()
    frame = frame.sort_values("game_pk").reset_index(drop=True)
    return frame[list(FRAME_COLUMNS)]


def restrict(frame: pd.DataFrame) -> pd.DataFrame:
    """The REGISTERED population: early-stratum first pitch, registered seasons."""
    lo, hi = FIRST_PITCH_UTC_HOURS
    mask = (frame["first_pitch_utc_hour"].between(lo, hi)
            & frame["season"].isin(SEASONS))
    return frame.loc[mask].reset_index(drop=True)


# ═════════════════════════════════════════════════════════════════════════════
# Derivation + scoring — PURE from here down
# ═════════════════════════════════════════════════════════════════════════════

def american_to_decimal(american) -> np.ndarray:
    a = np.asarray(american, dtype=float)
    return np.where(a > 0, a / 100.0 + 1.0, 100.0 / np.abs(a) + 1.0)


def novig_proportional(d_home, d_away) -> tuple[np.ndarray, np.ndarray]:
    """Proportional (multiplicative) overround removal — the REGISTERED method."""
    ph, pa = 1.0 / np.asarray(d_home, float), 1.0 / np.asarray(d_away, float)
    tot = ph + pa
    return ph / tot, pa / tot


def novig_shin(d_home, d_away, tol: float = 1e-13, max_iter: int = 200):
    """Shin (1993) overround removal — the DECLARED SENSITIVITY for the calibration
    diagnostic only. It gates nothing.

    Shin models the book's posted probabilities as arising from a share `z` of
    insider money, so the fair probability solves

        pi_i / ov = ( sqrt(z^2 + 4(1-z) * p_i^2 / ov) - z ) / ( 2(1-z) )     [1]

    with `z` fixed by `sum_i p_i = 1`.

    ⭐ Solved by BISECTION on z in [0, 0.5), not by a closed form. A two-outcome
    closed form exists but is easy to misremember, and a wrong one fails SILENTLY:
    the first cut here returned values identical to the proportional method to 1e-16
    (z collapsed to 0), i.e. a "sensitivity" that was a copy of the primary and would
    have tested nothing. `f(z) = sum_i p_i(z) - 1` is continuous and strictly
    decreasing in z, so bisection is exact to `tol` and cannot fail quietly; the
    guard `test_shin_and_proportional_differ_on_a_lopsided_price` pins that the two
    methods actually differ."""
    ph, pa = 1.0 / np.asarray(d_home, float), 1.0 / np.asarray(d_away, float)
    ov = ph + pa

    def _p(pi, z):
        return (np.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / ov) - z) / (2.0 * (1.0 - z))

    def _sum(z):
        return _p(ph, z) + _p(pa, z) - 1.0

    lo = np.zeros_like(ov)
    hi = np.full_like(ov, 0.5)
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = _sum(mid)
        # f(z) = sum_i p_i(z) - 1 is DECREASING in z: f(0) = sqrt(ov) - 1 > 0, and
        # more insider share pushes the fair probabilities down. So a POSITIVE f
        # means z is too SMALL and the search moves the LOWER bound up.
        # ⚠️ The first cut had these two lines the other way round. It converged to
        # z ~ 0.5, where the probabilities sum to 0.757 rather than 1 — and the
        # guard of the day ("Shin must differ from proportional") passed happily,
        # because a badly wrong answer differs too. The invariant that actually
        # binds is `sum_i p_i == 1`, which is now asserted.
        lo = np.where(f_mid > 0, mid, lo)
        hi = np.where(f_mid > 0, hi, mid)
        if float(np.max(hi - lo)) < tol:
            break
    z = 0.5 * (lo + hi)
    out_h, out_a = _p(ph, z), _p(pa, z)
    #: An overround at or below 1 (never observed here — node 1 measured 1.023-1.070)
    #: leaves Shin degenerate; fall back to proportional rather than emit a NaN that
    #: would silently shrink the diagnostic's population.
    degenerate = ~np.isfinite(out_h) | ~np.isfinite(out_a) | (ov <= 1.0)
    out_h = np.where(degenerate, ph / ov, out_h)
    out_a = np.where(degenerate, pa / ov, out_a)
    return out_h, out_a


def derive(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    f["home_decimal"] = american_to_decimal(f["home_american"])
    f["away_decimal"] = american_to_decimal(f["away_american"])
    f["overround"] = 1.0 / f["home_decimal"] + 1.0 / f["away_decimal"]
    ph, pa = novig_proportional(f["home_decimal"], f["away_decimal"])
    f["novig_home"], f["novig_away"] = ph, pa
    sh, sa = novig_shin(f["home_decimal"], f["away_decimal"])
    f["shin_home"], f["shin_away"] = sh, sa
    f["home_won"] = f["home_won"].astype(bool)
    f["season_month"] = (f["season"].astype(str) + "-"
                         + pd.to_datetime(f["game_date"]).dt.month.astype(str).str.zfill(2))
    return f


def bet_series(f: pd.DataFrame, arm: Arm) -> pd.DataFrame:
    """One row per BET: the flat 1-unit stake this arm places, and its PnL."""
    elig = arm.eligible(f).to_numpy(dtype=bool)
    sub = f.loc[elig]
    if sub.empty:
        return pd.DataFrame(columns=["game_pk", "season", "season_month", "pnl",
                                     "won", "implied", "implied_shin", "decimal"])
    home = arm.bet_home(sub).to_numpy(dtype=bool)
    dec = np.where(home, sub["home_decimal"], sub["away_decimal"])
    won = np.where(home, sub["home_won"], ~sub["home_won"])
    return pd.DataFrame({
        "game_pk": sub["game_pk"].to_numpy(),
        "season": sub["season"].to_numpy(),
        "season_month": sub["season_month"].to_numpy(),
        "pnl": np.where(won, dec - 1.0, -1.0),          # flat 1-unit stake
        "won": won,
        "implied": np.where(home, sub["novig_home"], sub["novig_away"]),
        "implied_shin": np.where(home, sub["shin_home"], sub["shin_away"]),
        "decimal": dec,
    })


def _roi(pnl: np.ndarray) -> float:
    return float(np.mean(pnl)) if len(pnl) else float("nan")


def _sharpe(pnl: np.ndarray) -> float:
    if len(pnl) < 2:
        return float("nan")
    sd = float(np.std(pnl, ddof=1))
    return float(np.mean(pnl) / sd) if sd > 0 else float("nan")


def _t_test_one_sided(pnl: np.ndarray) -> float:
    """H1: mean PnL > 0. Normal approximation (n is in the thousands)."""
    n = len(pnl)
    if n < 3:
        return float("nan")
    sd = float(np.std(pnl, ddof=1))
    if sd <= 0:
        return 0.0 if float(np.mean(pnl)) > 0 else 1.0
    t = float(np.mean(pnl)) / (sd / math.sqrt(n))
    return float(0.5 * math.erfc(t / math.sqrt(2.0)))


def _season_block_bootstrap_ci(bets: pd.DataFrame, seasons: Sequence[int],
                               n_boot: int = 2000, seed: int = 20260824) -> tuple[float, float]:
    """Resample whole SEASONS (blocks), not bets — a per-bet bootstrap would ignore
    any within-season dependence. Reported, never gating."""
    rng = np.random.default_rng(seed)
    blocks = [bets.loc[bets["season"] == s, "pnl"].to_numpy() for s in seasons]
    blocks = [b for b in blocks if len(b)]
    if len(blocks) < 2:
        return (float("nan"), float("nan"))
    draws = np.empty(n_boot)
    idx = np.arange(len(blocks))
    for i in range(n_boot):
        pick = rng.choice(idx, size=len(blocks), replace=True)
        draws[i] = float(np.concatenate([blocks[j] for j in pick]).mean())
    return (float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975)))


def _wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def score_arm(f: pd.DataFrame, arm: Arm, seasons: Sequence[int]) -> dict:
    bets = bet_series(f, arm)
    pnl = bets["pnl"].to_numpy(dtype=float)
    n = len(pnl)
    wins = int(bets["won"].sum()) if n else 0
    per_season, fold_wins = {}, 0
    for s in seasons:
        sp = bets.loc[bets["season"] == s, "pnl"].to_numpy(dtype=float)
        per_season[str(s)] = {"n": int(len(sp)), "roi": _roi(sp)}
        if len(sp) and _roi(sp) > 0:
            fold_wins += 1
    lo, hi = _wilson(wins, n)
    boot_lo, boot_hi = _season_block_bootstrap_ci(bets, seasons)
    return {
        "arm_id": arm.arm_id, "family": arm.family, "hypothesis": arm.hypothesis,
        "n_bets": n,
        "roi": _roi(pnl),
        "roi_boot_ci95": [boot_lo, boot_hi],
        "sharpe_per_bet": _sharpe(pnl),
        "p_one_sided": _t_test_one_sided(pnl),
        "hit_rate": (wins / n) if n else float("nan"),
        "hit_rate_ci95": [lo, hi],
        "implied_mean": float(bets["implied"].mean()) if n else float("nan"),
        "implied_mean_shin": float(bets["implied_shin"].mean()) if n else float("nan"),
        "calibration_gap": (wins / n - float(bets["implied"].mean())) if n else float("nan"),
        "calibration_gap_shin": (wins / n - float(bets["implied_shin"].mean())) if n else float("nan"),
        "fold_wins": fold_wins,
        "per_season": per_season,
    }


def bucket_matrix(f: pd.DataFrame, arms: Sequence[Arm]) -> tuple[np.ndarray, list[str]]:
    """(T buckets x N arms) of bucket ROI for CSCV/PBO.

    ⭐ MH2/NCAAF-P2.1: PBO and DSR want DIFFERENT return series and this study
    registers them separately — PBO gets many season-MONTH buckets (CSCV needs
    partitions), DSR gets the per-BET PnL series (low-noise observations).

    A bucket in which an arm places NO bet scores 0.0, which is the economically
    correct return of a flat-stake rule that did not fire — not a missing value."""
    buckets = sorted(f["season_month"].unique())
    idx = {b: i for i, b in enumerate(buckets)}
    M = np.zeros((len(buckets), len(arms)), dtype=float)
    for j, arm in enumerate(arms):
        bets = bet_series(f, arm)
        if bets.empty:
            continue
        for b, grp in bets.groupby("season_month"):
            M[idx[b], j] = float(grp["pnl"].mean())
    return M, buckets


def benjamini_hochberg(pvals: Sequence[float], alpha: float = BH_ALPHA) -> tuple[list[bool], float]:
    """BH-FDR over the FULL registered family (declared_field_size), never a subset."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = int(np.max(np.nonzero(passed)[0]) + 1) if passed.any() else 0
    cutoff = float(thresh[k - 1]) if k else float(thresh[0])
    keep = np.zeros(m, dtype=bool)
    if k:
        keep[order[:k]] = True
    return keep.tolist(), cutoff


def run_gates(f: pd.DataFrame, seasons: Sequence[int] = SEASONS) -> dict:
    """Score the registered family + anchors and apply every pre-registered gate."""
    arm_results = [score_arm(f, a, seasons) for a in REGISTERED_ARMS]
    anchor_results = [score_arm(f, a, seasons) for a in ANCHORS]

    clause = fold_consistency_clause(len(seasons), alpha=FOLD_ALPHA)
    keep, bh_cutoff = benjamini_hochberg([r["p_one_sided"] for r in arm_results])

    M, buckets = bucket_matrix(f, REGISTERED_ARMS)
    pbo = pbo_cscv(M, higher_is_better=True, n_splits=min(16, len(buckets) - (len(buckets) % 2)))

    # ⭐ MH2.1 (a): `V` is measured over the REGISTERED arms only — an anchor that
    # SEES the outcome (the oracle) would drive the cross-trial dispersion and set
    # the gate's own bar, which is the defect that made DSR unclearable there.
    trial_sharpes = [r["sharpe_per_bet"] for r in arm_results
                     if r["n_bets"] >= 3 and np.isfinite(r["sharpe_per_bet"])]

    for i, (arm, res) in enumerate(zip(REGISTERED_ARMS, arm_results)):
        bets = bet_series(f, arm)
        pnl = bets["pnl"].to_numpy(dtype=float)
        if len(pnl) >= 3:
            d = deflated_sharpe(pnl, n_trials=DECLARED_FIELD_SIZE,
                                trial_sharpes=trial_sharpes)
            res["dsr"] = float(d.dsr)
            res["dsr_sr0"] = float(d.sr0)
        else:
            res["dsr"] = float("nan")
            res["dsr_sr0"] = float("nan")
        res["bh_pass"] = bool(keep[i])
        res["pbo"] = float(pbo.pbo)
        res["gates"] = {
            "roi_positive": bool(res["roi"] > 0),
            "fold_consistency": bool(clause.passes(res["fold_wins"])),
            "bh_fdr": bool(keep[i]),
            "pbo": bool(pbo.pbo < MAX_PBO),
            "dsr": bool(np.isfinite(res["dsr"]) and res["dsr"] >= MIN_DSR),
        }
        res["survives"] = all(res["gates"].values())

    by_id = {r["arm_id"]: r for r in anchor_results}
    oracle_roi = by_id["anchor_oracle_winner"]["roi"]
    best_arm_roi = max((r["roi"] for r in arm_results if r["n_bets"]), default=float("nan"))
    anchor_gates = {
        # NF-D11 / E2.1-r: nothing may beat a peeking oracle. An arm that does is a
        # metric inversion, not a finding.
        "oracle_is_the_floor": bool(oracle_roi > best_arm_roi),
        # The vig must be real and must cost: a no-skill rule loses.
        "coin_flip_loses": bool(by_id["anchor_coin_flip"]["roi"] < 0),
        # NF1.8: a DEGENERATE must lose the primary metric.
        "all_home_loses": bool(by_id["anchor_all_home"]["roi"] < 0),
        "all_fav_loses": bool(by_id["anchor_all_fav"]["roi"] < 0),
    }
    return {
        "n_games": int(len(f)),
        "seasons": list(seasons),
        "declared_field_size": DECLARED_FIELD_SIZE,
        "fold_clause": {
            "n_folds": clause.n_folds, "alpha": clause.alpha,
            "wins_required": clause.wins_required,
            "attained_false_fire": clause.attained_false_fire,
            "attainable": clause.attainable,
        },
        "bh_cutoff": bh_cutoff,
        "pbo": {"pbo": float(pbo.pbo), "n_combos": int(pbo.n_combos),
                "n_buckets": len(buckets), "n_arms": len(REGISTERED_ARMS)},
        "arms": arm_results,
        "anchors": anchor_results,
        "anchor_gates": anchor_gates,
        "survivors": [r["arm_id"] for r in arm_results if r["survives"]],
    }


# ═════════════════════════════════════════════════════════════════════════════
# Pre-registered harness controls (MH2.6's vacuity floor: a harness that cannot
# FAIL and a harness that cannot FIRE are both worthless, so prove BOTH directions)
# ═════════════════════════════════════════════════════════════════════════════

def negative_control_permutation(f: pd.DataFrame, seed: int = 20260824,
                                 seasons: Sequence[int] = SEASONS) -> dict:
    """THE PRE-REGISTERED negative control: shuffle the OUTCOMES, keep every price
    and segment; no arm may survive.

    ⚠️ **IT IS MIS-SPECIFIED, IT FAILED, AND IT IS LEFT HERE FAILING** (NF-D20: a
    pre-registered anchor that fails is decomposed, never re-labelled). Permuting
    outcomes does not implement "no segment bias" — it severs the price↔probability
    link entirely, so a +250 dog now wins at the pooled ~47 % base rate instead of
    ~29 %, which is a MASSIVE artificial dog bias. Measured: `dog_vs_heavy_fav`
    returns +0.378 ROI under it and clears every gate. The failure is a statement
    about THIS CONTROL, not about the gate family.

    `negative_control_efficient_market` below is the correctly-specified null,
    added AFTER this one was found to be mis-specified, and labelled as the
    amendment it is."""
    rng = np.random.default_rng(seed)
    g = f.copy()
    g["home_won"] = rng.permutation(g["home_won"].to_numpy())
    return run_gates(g, seasons)


def negative_control_efficient_market(f: pd.DataFrame, seed: int = 20260824,
                                      seasons: Sequence[int] = SEASONS) -> dict:
    """AMENDED negative control — a PERFECTLY EFFICIENT market.

    Re-draw each game's outcome from **its own no-vig implied probability**. Prices,
    segments and the vig are untouched; what is removed is exactly the thing the
    study is looking for — any systematic gap between a segment's implied and
    realized win rate. Under this null the truth is "the price is right", so **no
    arm may survive**, and every arm's ROI should sit at roughly minus the vig.

    This is the null the permutation control was *meant* to implement."""
    rng = np.random.default_rng(seed)
    g = f.copy()
    g["home_won"] = rng.random(len(g)) < g["novig_home"].to_numpy()
    return run_gates(g, seasons)


def positive_control(f: pd.DataFrame, edge: float = 0.06, seed: int = 20260824,
                     seasons: Sequence[int] = SEASONS) -> dict:
    """Inject a KNOWN dog bias — resample outcomes so the dog wins `edge` more often
    than its no-vig implied probability — and require `dog_vs_*` to survive. A gate
    family that cannot detect a real, sizeable bias returns a null for free."""
    rng = np.random.default_rng(seed)
    g = f.copy()
    fav_home = (g["home_decimal"] < g["away_decimal"]).to_numpy()
    p_home = g["novig_home"].to_numpy().copy()
    # push probability toward the DOG side
    p_home = np.where(fav_home, p_home - edge, p_home + edge)
    g["home_won"] = rng.random(len(g)) < np.clip(p_home, 0.01, 0.99)
    return run_gates(g, seasons)


def efficient_market_null_band(f: pd.DataFrame, n_sims: int = 500,
                               seed: int = 20260824) -> dict:
    """The DECISIVE reference read: what would each arm's ROI be if Bovada's price
    were exactly right?

    Re-draw every game's outcome from its own no-vig implied probability `n_sims`
    times and record each arm's ROI. Prices, segments, eligibility and the vig are
    untouched — the ONLY thing removed is a systematic implied-vs-realized gap, i.e.
    precisely the bias this study is looking for. An arm whose REAL ROI sits inside
    this band is behaving exactly like a fair-but-vigged market; an arm outside it
    is the thing a candidate would look like.

    ⭐ This is a DIAGNOSTIC that explains the verdict, not a gate. It changes no
    registered clause — it is added because the amended negative control is a single
    draw, and a single draw carries its own sampling noise.

    Eligibility and bet-side depend only on PRICES and TEAMS, never on outcomes, so
    they are computed ONCE and reused across every simulation."""
    rng = np.random.default_rng(seed)
    p_home = f["novig_home"].to_numpy(dtype=float)
    n = len(f)
    plans = []
    for arm in REGISTERED_ARMS:
        elig = arm.eligible(f).to_numpy(dtype=bool)
        sub = f.loc[elig]
        if sub.empty:
            plans.append((arm.arm_id, None, None, None))
            continue
        home = arm.bet_home(sub).to_numpy(dtype=bool)
        dec = np.where(home, sub["home_decimal"], sub["away_decimal"]).astype(float)
        plans.append((arm.arm_id, np.flatnonzero(elig), home, dec))

    draws: dict[str, list[float]] = {a.arm_id: [] for a in REGISTERED_ARMS}
    for _ in range(n_sims):
        home_won = rng.random(n) < p_home
        for arm_id, idx, home, dec in plans:
            if idx is None:
                draws[arm_id].append(float("nan"))
                continue
            won = np.where(home, home_won[idx], ~home_won[idx])
            draws[arm_id].append(float(np.mean(np.where(won, dec - 1.0, -1.0))))
    out = {}
    for arm_id, vals in draws.items():
        v = np.asarray(vals, dtype=float)
        out[arm_id] = {
            "mean": float(np.mean(v)),
            "p2_5": float(np.quantile(v, 0.025)),
            "p97_5": float(np.quantile(v, 0.975)),
        }
    return {"n_sims": int(n_sims), "per_arm": out}


def _blocking_gates(gates: dict) -> dict:
    """Which gate stopped each arm. A control that fails is only informative once
    you know WHICH clause bound (NF-W7i: diagnose a failing control before
    concluding the instrument is blind)."""
    out = {}
    for r in gates["arms"]:
        out[r["arm_id"]] = [name for name, ok in r["gates"].items() if not ok]
    return out


def fold_winner_distribution(f: pd.DataFrame, seasons: Sequence[int] = SEASONS) -> dict:
    """NF1.8's FLIP DISTRIBUTION — the cheapest and most informative companion to
    PBO: which arm posts the best ROI in each season fold, and how often.

    Mass on two arms a fraction of a percent apart is a TIE (and a high PBO is then
    the NULL, not evidence of overfitting); mass spread thinly over unrelated arms
    is a search that learnt nothing. A rank statistic alone cannot tell those apart."""
    counts: dict[str, int] = {a.arm_id: 0 for a in REGISTERED_ARMS}
    for s in seasons:
        best, best_roi = None, -np.inf
        for arm in REGISTERED_ARMS:
            bets = bet_series(f, arm)
            sp = bets.loc[bets["season"] == s, "pnl"].to_numpy(dtype=float)
            roi = _roi(sp)
            if len(sp) and np.isfinite(roi) and roi > best_roi:
                best, best_roi = arm.arm_id, roi
        if best is not None:
            counts[best] += 1
    return counts


def contender_spread(gates: dict) -> float:
    """NF1.8: the spread over the CONTENDER set (top quartile), not the whole field.
    A spread computed over a field that contains its own known-bad arms measures
    those arms, not the contest."""
    rois = sorted((r["roi"] for r in gates["arms"] if np.isfinite(r["roi"])), reverse=True)
    if not rois:
        return float("nan")
    top = rois[: max(2, len(rois) // 4)]
    return float(max(top) - min(top))


def _controls(pop: pd.DataFrame) -> dict:
    """Both pre-registered controls plus the amended negative control, each reported
    with the gates that bound — never a bare survivor list."""
    perm = negative_control_permutation(pop)
    eff = negative_control_efficient_market(pop)
    pos = positive_control(pop)
    return {
        "negative_permuted_outcomes": {
            "status": "PRE-REGISTERED; MIS-SPECIFIED; FAILED — left failing and decomposed",
            "survivors": perm["survivors"],
            "roi": {r["arm_id"]: r["roi"] for r in perm["arms"]},
            "why": ("permuting outcomes severs the price-probability link, which is a "
                    "massive ARTIFICIAL dog bias rather than the absence of one; it does "
                    "not implement the null it names"),
        },
        "negative_efficient_market": {
            "status": "AMENDED control (added after the permutation control was found "
                      "mis-specified); this is the null the permutation was meant to be",
            "survivors": eff["survivors"],
            "roi": {r["arm_id"]: r["roi"] for r in eff["arms"]},
            "pbo": eff["pbo"]["pbo"],
        },
        "positive_injected_dog_edge": {
            "status": "PRE-REGISTERED; FAILED — no arm survives a 6pp injected dog bias",
            "survivors": pos["survivors"],
            "roi": {r["arm_id"]: r["roi"] for r in pos["arms"]},
            "pbo": pos["pbo"]["pbo"],
            "blocking_gates": _blocking_gates(pos),
            "why": ("the METRIC gates all fire (roi_positive, fold_consistency, bh_fdr "
                    "pass for 6 of 8 arms); the DEFLATION gates block every one. A 6pp "
                    "edge injected into a family of near-clones makes 'which arm is best "
                    "in-sample' a coin flip, so CSCV PBO rises to 0.426 (NF1.8: a high "
                    "PBO over near-clones is a TIE, not overfitting), and the same edge "
                    "inflates cross-trial dispersion V so SR0 outruns every arm's Sharpe "
                    "(the MH2.5 / NF-W6b-C mechanism). ⇒ the deflation gates as "
                    "registered are hostile to a correlated field and CANNOT certify a "
                    "real effect of this size. This bounds what a SURVIVOR would have "
                    "meant; it does NOT rescue this study's null, which rests on G1 "
                    "(every arm's ROI is negative) — a de-vig-free, PBO-free, DSR-free "
                    "clause no gate change can move."),
        },
    }


# ═════════════════════════════════════════════════════════════════════════════
# Verdict
# ═════════════════════════════════════════════════════════════════════════════

def classify(gates: dict) -> dict:
    """Classify the study with `cv_power.classify_null`, passing
    `declared_field_size` (MH2.7) so no remedy may prescribe a field below the
    one that was pre-registered."""
    arms = gates["arms"]
    live = [r for r in arms if r["n_bets"] >= 3 and np.isfinite(r["roi"])]
    if not live:
        return {"state": "UNDEFINED", "reason": "no registered arm placed a scoreable bet"}
    best = max(live, key=lambda r: r["roi"])
    sharpes = [r["sharpe_per_bet"] for r in live if np.isfinite(r["sharpe_per_bet"])]
    v = float(np.var(np.asarray(sharpes), ddof=1)) if len(sharpes) > 1 else None
    verdict = classify_null(
        metric="roi_per_unit_staked",
        n_folds=len(gates["seasons"]),
        n_arms=len(arms),
        beats_foil=bool(best["roi"] > 0),
        observed_sr=best["sharpe_per_bet"] if np.isfinite(best["sharpe_per_bet"]) else None,
        var_trials_sr=v,
        fold_wins=best["fold_wins"],
        p_one_sided=best["p_one_sided"],
        bh_cutoff=gates["bh_cutoff"],
        degenerates_excluded_from_v=True,
        declared_field_size=DECLARED_FIELD_SIZE,
    )
    return {
        "state": verdict.state, "reason": verdict.reason,
        "retest_trigger": verdict.retest_trigger,
        "best_arm": best["arm_id"], "best_arm_roi": best["roi"],
        "detail": verdict.detail,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "ablation_results" / "mlb_hv2_1_market_bias.json"
FIXTURE = REPO / "betting_ml" / "tests" / "fixtures" / "mlb_hv2_1_input.csv.gz"


def _coverage_audit(full: pd.DataFrame) -> dict:
    lo, hi = FIRST_PITCH_UTC_HOURS
    early = full["first_pitch_utc_hour"].between(lo, hi)
    per = {}
    for s in sorted(full["season"].unique()):
        m = full["season"] == s
        per[str(int(s))] = {"observed": int(m.sum()),
                            "observed_early": int((m & early).sum()),
                            "observed_late": int((m & ~early).sum())}
    return {"observed_total": int(len(full)), "per_season": per}


def _efficient_market_read(pop: pd.DataFrame, gates: dict) -> dict:
    band = efficient_market_null_band(pop)
    per = band["per_arm"]
    rows = {}
    for r in gates["arms"]:
        b = per[r["arm_id"]]
        rows[r["arm_id"]] = {
            "real_roi": r["roi"],
            "efficient_mean": b["mean"],
            "efficient_ci95": [b["p2_5"], b["p97_5"]],
            "delta_vs_efficient": r["roi"] - b["mean"],
            "above_band": bool(r["roi"] > b["p97_5"]),
            "below_band": bool(r["roi"] < b["p2_5"]),
        }
    return {"n_sims": band["n_sims"], "per_arm": rows,
            "arms_above_band": [k for k, v in rows.items() if v["above_band"]],
            "arms_below_band": [k for k, v in rows.items() if v["below_band"]]}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", action="store_true", help="coverage only; score nothing")
    ap.add_argument("--from-fixture", action="store_true",
                    help="score the committed fixture instead of reading S3")
    ap.add_argument("--write-fixture", action="store_true")
    args = ap.parse_args(argv)

    full = pd.read_csv(FIXTURE) if args.from_fixture else extract()
    if args.write_fixture:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        full.to_csv(FIXTURE, index=False, compression="gzip")
        print(f"fixture -> {FIXTURE} ({len(full)} rows)")

    audit = _coverage_audit(full)
    if args.audit:
        print(json.dumps(audit, indent=2))
        return 0

    pop = derive(restrict(full))
    gates = run_gates(pop)
    result = {
        "story": STORY,
        "best_alpha": 0,
        "population": {
            "bookmaker": BOOKMAKER, "market": MARKET, "game_type": GAME_TYPE,
            "first_pitch_utc_hours": list(FIRST_PITCH_UTC_HOURS),
            "seasons": list(SEASONS), "excluded_seasons": list(EXCLUDED_SEASONS),
            "min_season_coverage": MIN_SEASON_COVERAGE,
            "novig_method": NOVIG_METHOD, "novig_sensitivity": NOVIG_SENSITIVITY,
            "marquee_teams": list(MARQUEE_TEAMS),
            "n_games": int(len(pop)),
        },
        "audit": audit,
        "gates": gates,
        "efficient_market_null_band": _efficient_market_read(pop, gates),
        "nf1_8_diagnostics": {
            "fold_winner_distribution": fold_winner_distribution(pop),
            "contender_spread_roi": contender_spread(gates),
            "note": ("reported beside PBO because a rank statistic cannot tell a TIE "
                     "from an unstable pick (NF1.8). Not load-bearing here: every arm "
                     "is negative, so the verdict is decided by G1 before PBO is read."),
        },
        "verdict": classify(gates),
        "controls": _controls(pop),
        "sensitivity_full_observed_sample": run_gates(
            derive(full), sorted(int(s) for s in full["season"].unique())),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=float))
    print(f"wrote {OUT_JSON}")
    print(json.dumps({"verdict": result["verdict"]["state"],
                      "survivors": gates["survivors"],
                      "n_games": len(pop)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
