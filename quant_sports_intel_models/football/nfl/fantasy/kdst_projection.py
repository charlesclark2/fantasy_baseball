"""kdst_projection.py — NF1.6 pure model: BASE season projections for KICKER (K) + TEAM DEFENSE (DST).

The completeness move, not an edge play. Before NF1.6 the fantasy tools projected OFFENSIVE SKILL
only (QB/RB/WR/TE) and the K/DST roster slots rendered "not projected". This module fills them with
a **deliberately BASE** model that emits the RAW COMPONENTS NF-C1 rescores per league, plus an
HONEST, WIDE, ASYMMETRIC 80% interval.

⚖️ HONEST FRAME (roadmap §0): edge-independent — no `best_alpha`/PBO/DSR (that is the betting
posture). The gate is FACE-VALIDITY + COVERAGE + honest uncertainty. K and DST are the LEAST
predictable fantasy positions and the framing must not imply confident ranks: the value here is
COMPLETENESS and relative TIERING (better vs worse situations), not precision.

────────────────────────────────────────────────────────────────────────────────────────────────
WHY THE MODEL LOOKS THE WAY IT DOES — every shrink is a MEASURED reliability, not a guess
────────────────────────────────────────────────────────────────────────────────────────────────
Lag-1 autocorrelation of the PER-GAME rate, 1999–2025 (824 team-season pairs / 659 same-kicker
season pairs; measured, see the report):

  DST     sacks 0.252 · INT 0.259 · fumble-rec 0.223 · ST TD 0.166 · def TD 0.094
          blocked kicks 0.019 · safeties −0.018 · points-allowed/g 0.316
  KICKER  FG make rate 0.085 · FG att/g 0.117 · PAT att/g 0.320 · ≥50yd att share 0.429

Three findings drive the whole design:

  ① **DST carries MODEST signal, and only in the volume takeaways.** Sacks / INT / fumble
    recoveries and points allowed persist at ρ ≈ 0.22–0.32; defensive TDs, safeties and blocked
    kicks are indistinguishable from noise (ρ ≈ −0.02…0.09). So the noise components are projected
    at (essentially) the LEAGUE MEAN — projecting a team's 5 defensive TDs forward would be
    manufacturing precision that does not exist. This is why the product's claim is TIERS.
  ② **A kicker's ACCURACY is near-random year to year (ρ = 0.085) but his TEAM'S SCORING
    ENVIRONMENT is partly forecastable.** PAT attempts correlate 0.948 with team points/game
    (slope 0.132) — PAT volume essentially IS offensive touchdowns. FG attempts, by contrast,
    correlate only 0.19 with team points and are NON-MONOTONE in them: the fitted quadratic peaks
    at ~25.2 points/game and turns DOWN, because elite offenses score touchdowns instead of kicking
    field goals. So a kicker's projection is mostly his offense's, his make rate is heavily
    regressed to league average, and FG-attempt volume is close to a constant ~1.94/game for
    everybody.
    ⚠️ **BUT THOSE TWO NUMBERS ARE CONTEMPORANEOUS, AND THE MODEL DOES NOT GET TO SEE THE REALIZED
    SEASON.** Refitted against the FORWARD points estimate the model actually consumes (week-1
    Vegas implied points blended with a regressed prior), the PAT correlation falls to ~0.38 and the
    FG one to ~0.03. The 0.948 is a near-identity between PATs and touchdowns; it is NOT a
    statement about forecast accuracy, and reporting it as one would be a train/serve inconsistency
    dressed up as a finding. Both numbers are reported in the run report for exactly that reason.
  ③ **Leg strength IS real.** The share of a kicker's attempts from ≥50 yards persists at
    ρ = 0.429 — by far the strongest kicker-side signal — so the distance MIX is genuinely
    per-kicker (shrunk), while the make rate WITHIN a bucket is not. That matters because
    distance-bucketed FG scoring (3/4/5) pays for leg strength.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT IT EMITS — raw components, so ANY league's scoring can score it
────────────────────────────────────────────────────────────────────────────────────────────────
Mirrors MVP-1's raw-line philosophy (`season_projection.RAW_STAT_COLS`). The `proj_fp_*` totals are
a CONVENIENCE for ranking/validation only; NF-C1 rescores the raw line per league.

  DST  proj_def_sacks · proj_def_int · proj_def_fumble_rec · proj_def_td · proj_st_td ·
       proj_def_safety · proj_def_blocked_kick · proj_dst_points_allowed (season total) ·
       proj_dst_pa_per_game / _sd  AND the POINTS-ALLOWED DISTRIBUTION as nine
       `proj_dst_pa_g_<bucket>` columns = the EXPECTED NUMBER OF GAMES landing in each bucket.
  K    proj_fg_att · proj_fg_made · proj_fg_made_0_39 / _40_49 / _50_plus · proj_fg_missed ·
       proj_pat_att · proj_pat_made

⭐ **WHY THE POINTS-ALLOWED DISTRIBUTION IS EMITTED AS EXPECTED-GAMES-PER-BUCKET.** DST
points-allowed scoring is a per-game TIER table (0 PA = +5, 46+ = −5, …), which is NOT linear in
season points allowed — so a season total cannot be scored under it. But
`Σ_bucket tier_points(bucket) × E[games in bucket]` IS linear in the emitted columns, so the
existing sport-agnostic linear scorer can express ANY tier scheme exactly, with no engine change
and no dependency on NF-C0b. The nine bucket edges are the common REFINEMENT of the ESPN
(0/1-6/7-13/14-17/18-27/28-34/35-45/46+) and Yahoo (0/1-6/7-13/14-20/21-27/28-34/35+) schemes, so
both are exact unions of them; a scheme with other edges re-integrates from
`proj_dst_pa_per_game` + `_sd` (also emitted) and is told so.

⭐ **WHY THE DISTRIBUTION IS EMPIRICAL, NOT PARAMETRIC.** A shutout is worth the most tier points
of any game outcome and P(0 PA) = 0.0099 in the data. A negative binomial matched to the observed
mean/variance of team points allowed puts ~1e-4 there — it misses the single most valuable atom by
two orders of magnitude, because NFL scores are lumpy multiples of 3 and 7 rather than a smooth
count. So the bucket mix is read off the EMPIRICAL conditional distribution of per-game points
allowed given the team's projected points-allowed rate (a monotone quantile-bin lookup with linear
interpolation) — which reproduces the shutout tail by construction.

────────────────────────────────────────────────────────────────────────────────────────────────
THE INTERVAL — inheriting the NF1.7→1.8→1.9 discipline WITHOUT re-running a bake-off
────────────────────────────────────────────────────────────────────────────────────────────────
The story is explicit that a BASE band ships with an HONEST REPORTED coverage number, not a tuned
one. Three non-negotiables are honoured:

  (a) **p10/p90 are emitted INDEPENDENTLY** and carried through the league rescore via
      `SportProfile.base_p10_column/base_p90_column` (the asymmetric plumbing NF1.7 shipped). K and
      DST bands are MORE skewed than any offensive position — both floor at 0 with a long right
      tail, and a cut kicker realises exactly 0 — so a single symmetric `sd` would slide the
      interval off its own point. `apply_band` asserts lo ≤ point ≤ hi.
  (b) **Coverage is measured on the RIGHT population.** The band panel is the PRESEASON universe
      LEFT-JOINED to realized outcomes with a 0 fill (13.1% of week-1-rostered kickers realise
      zero), never an inner join behind a games filter. Coverage is reported as a FLOOR
      (≥ nominal), never as a target to minimise distance to (E2.1-r).
  (c) **The band is REPORTED, not selected.** `fit_ratio_band` takes the empirical quantiles of
      realized/projected per band group. No candidate field, no PBO — there is no selection to
      invert. If coverage under-runs, the honest response is to widen (`widen`), not to re-pick.

The band groups are the one split that materially matters: a locked-in starting kicker and a camp
body have completely different outcome distributions (mean games share 0.923 vs 0.140). DST is one
group — all 32 defenses play a full season.

Everything in this module is PURE (numpy/pandas in, DataFrame/dataclass out, NO IO) so the whole
model is unit-tested offline against the fast gate; the DuckDB/S3 reads live in `kdst_source` and
the validation/landing in `run_kdst_projection`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MODEL_VERSION = "nfl_fantasy_kdst_base_v1"

POSITIONS = ("K", "DST")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The emitted raw-component contract (the input contract for NF-C1 / NF-C0b)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The nine points-allowed buckets — the common REFINEMENT of the ESPN and Yahoo tier edges, so
# either scheme is an exact union of them (see the module docstring). `PA_BUCKET_EDGES[i]` is the
# INCLUSIVE lower bound of bucket i.
PA_BUCKET_LABELS = ("0", "1_6", "7_13", "14_17", "18_20", "21_27", "28_34", "35_45", "46p")
PA_BUCKET_EDGES = (0, 1, 7, 14, 18, 21, 28, 35, 46)
PA_BUCKET_COLS = tuple(f"proj_dst_pa_g_{b}" for b in PA_BUCKET_LABELS)

# ── NF-C0e: the YARDS-ALLOWED tier family, the structural TWIN of the points-allowed one ─────
# Same mechanism, same reason: yards-allowed D/ST scoring is a per-game TIER table, so the season
# projection must emit `E[games in bucket]` for a linear scorer to express any table EXACTLY.
#
# ⭐ WHY THESE NINE EDGES ARE NOT A GUESS. Unlike the points-allowed ladder — where ESPN splits at
# 18-21/22-27 and we split at 18-20/21-27, so exactly one boundary is disclosed as approximate —
# the yards ladder is IDENTICAL on both platforms and both name it for us:
#   * Sleeper's keys are SELF-DESCRIBING: `yds_allow_0_100` / `_100_199` / `_200_299` / `_300_349` /
#     `_350_399` / `_400_449` / `_450_499` / `_500_549` / `_550p` — nine rungs, cut points stated.
#   * ESPN numbers its nine rungs 128..136, and `espn.py`'s identity evidence fixes their ORDER
#     (129..136 sum to 17.000 games) but NOT their cut points. The Sleeper keys supply exactly the
#     missing half, and nine-rungs-monotone matches nine-rungs-monotone.
# So the two independent payloads AGREE, which is what makes these edges evidence rather than the
# "it looked right in a table" guess `espn.py`'s header forbids.
#
# ⚠️ ONE DISCLOSED BOUNDARY. Sleeper's top rung is spelled `0_100` while ESPN's 128 is "under 100",
# so a game allowing EXACTLY 100 yards is ambiguous between the two. We resolve it as `< 100`
# (ESPN's reading). Measured cost: 1 team-game in 13,912 since 1999 sits exactly on 100.
YA_BUCKET_LABELS = ("0_99", "100_199", "200_299", "300_349", "350_399",
                    "400_449", "450_499", "500_549", "550p")
YA_BUCKET_EDGES = (0, 100, 200, 300, 350, 400, 450, 500, 550)
YA_BUCKET_COLS = tuple(f"proj_dst_ya_g_{b}" for b in YA_BUCKET_LABELS)

DST_RAW_COLS = (
    "proj_def_sacks", "proj_def_int", "proj_def_fumble_rec", "proj_def_td", "proj_st_td",
    "proj_def_safety", "proj_def_blocked_kick", "proj_def_forced_fumble",
    "proj_dst_points_allowed", "proj_dst_pa_per_game", "proj_dst_pa_per_game_sd",
    *PA_BUCKET_COLS,
    "proj_dst_yards_allowed", "proj_dst_ya_per_game", "proj_dst_ya_per_game_sd",
    *YA_BUCKET_COLS,
)
K_RAW_COLS = (
    "proj_fg_att", "proj_fg_made", "proj_fg_made_0_39", "proj_fg_made_40_49",
    "proj_fg_made_50_plus", "proj_fg_missed", "proj_pat_att", "proj_pat_made",
)
RAW_STAT_COLS = ("proj_games", *K_RAW_COLS, *DST_RAW_COLS)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# CONVENIENCE scoring — the ranking/validation metric ONLY (never the product contract)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Distance-bucketed FG + PAT, the modal default (ESPN/Yahoo agree on 3/4/5 and 1). A missed FG
# scores 0 here; a league that penalises misses expresses that through its own `ScoringRules`.
K_CONVENIENCE_SCORING = {
    "proj_fg_made_0_39": 3.0, "proj_fg_made_40_49": 4.0, "proj_fg_made_50_plus": 5.0,
    "proj_pat_made": 1.0,
}
# The ESPN-default DST scheme: the linear takeaway terms + the per-game points-allowed TIER table.
DST_CONVENIENCE_SCORING = {
    "proj_def_sacks": 1.0, "proj_def_int": 2.0, "proj_def_fumble_rec": 2.0,
    "proj_def_td": 6.0, "proj_st_td": 6.0, "proj_def_safety": 2.0,
    "proj_def_blocked_kick": 2.0,
    # ⚠️ `proj_def_forced_fumble` and the NF-C0e YARDS-ALLOWED tier columns are deliberately ABSENT
    #    from the convenience scheme even though both are now projected and both are APPLIED for a
    #    league that scores them. The convenience total's job is to RANK under the MODAL default,
    #    and neither is in ESPN's or Yahoo's default D/ST scheme — they are per-league opt-ins (the
    #    operator's league 998005 scores no yards tiers at all). Folding an opt-in rule into the
    #    default ranking would silently re-rank every league that does NOT have it.
}
# tier points per points-allowed bucket. ⚠️ 18_20 and 21_27 both sit inside ESPN's 18-27 tier (0
# points) — the finer split exists so Yahoo's 14-20 / 21-27 edges are also expressible.
DST_PA_TIER_POINTS = {
    "0": 5.0, "1_6": 4.0, "7_13": 3.0, "14_17": 1.0, "18_20": 0.0,
    "21_27": 0.0, "28_34": -1.0, "35_45": -3.0, "46p": -5.0,
}

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Measured reliabilities (the shrink targets) — REPORTED, and re-measured every run
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The DST counting components, with the lag-1 per-game autocorrelation measured on 1999–2025. The
# stored value is documentation + the offline-fallback shrink; `fit_dst_component_model` re-fits
# the shrink IN-FOLD from history strictly before the projection season and is what actually ships.
DST_COMPONENTS = ("def_sacks", "def_int", "def_fumble_rec", "def_td", "st_td",
                  "def_safety", "def_blocked_kick", "def_forced_fumble")
DST_COMPONENT_YOY = {
    "def_sacks": 0.252, "def_int": 0.259, "def_fumble_rec": 0.223, "st_td": 0.166,
    "def_td": 0.094, "def_blocked_kick": 0.019, "def_safety": -0.018,
    # NF-C0e — `def_fumbles_forced` was in `stg_nfl_team_week` the whole time and simply never
    # loaded, so a league paying for a forced fumble (the operator's own Sleeper league does, at
    # +1) had that rule CAPTURED. It carries a fitted forward slope of 0.29, and on the held-out
    # walk-forward it beats the league-mean degenerate on BOTH losses in 16/16 seasons — a WIDER
    # margin than `def_sacks`, which the program already ships as applied.
    "def_forced_fumble": 0.273,
}
# Components whose measured reliability is statistically indistinguishable from zero → projected at
# the league mean, and SAID to be. Keeping them as columns (rather than dropping them) is what lets
# a league that scores them heavily still score them; pretending we can rank them would not.
DST_NOISE_COMPONENTS = ("def_td", "def_safety", "def_blocked_kick")

# The number of prior seasons the per-game rate is averaged over, and the recency decay applied to
# them (mirrors MVP-1's veteran window: weight = decay^age).
PRIOR_WINDOW_YEARS = 3
PRIOR_RECENCY_DECAY = 0.6

# League-average FG attempt MIX + per-bucket make rates, measured on 2015+ (the modern
# long-range era: the ≥50yd attempt share rose from 13.5% career to 17.7% since 2015, so a
# full-history mix would understate today's distance profile). Offline fallback only — the runner
# re-measures both from the training window.
FG_BUCKETS = ("0_39", "40_49", "50_plus")
FG_LEAGUE_ATT_MIX = {"0_39": 0.5195, "40_49": 0.2957, "50_plus": 0.1848}
FG_LEAGUE_MAKE_RATE = {"0_39": 0.9563, "40_49": 0.8015, "50_plus": 0.6820}
PAT_LEAGUE_MAKE_RATE = 0.9750

# The four-cell expected-GAMES table for a week-1-rostered kicker, as a SHARE of team games.
# Measured on 2006–2025 (900 kicker-season rows). Offline fallback; re-fitted in-fold by
# `fit_kicker_games_table`. The cells are the honest reason a camp body is not ranked like a
# starter: (ACT, primary) plays 92% of the slate, (non-ACT, non-primary) plays 14%.
KICKER_GAMES_SHARE = {(True, True): 0.923, (True, False): 0.507,
                      (False, True): 0.369, (False, False): 0.140}
KICKER_GAMES_SHARE_DEFAULT = 0.50

_ACTIVE_STATUSES = ("ACT", "")   # "" = a roster snapshot with no status recorded → treat as active


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Small pure helpers
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _num(s) -> np.ndarray:
    return pd.to_numeric(pd.Series(s), errors="coerce").to_numpy(dtype=float)


def zscore(x) -> np.ndarray:
    """z-score, NaN-safe; a flat/degenerate input yields zeros (never NaN contamination)."""
    a = np.asarray(x, dtype=float)
    m = np.nanmean(a) if np.isfinite(a).any() else 0.0
    sd = np.nanstd(a) if np.isfinite(a).any() else 0.0
    if not np.isfinite(sd) or sd < 1e-12:
        return np.zeros_like(a)
    return np.nan_to_num((a - m) / sd, nan=0.0)


def recency_weights(seasons, base_season: int, *, decay: float = PRIOR_RECENCY_DECAY) -> np.ndarray:
    """`decay ** (base_season − season)` — MVP-1's veteran recency convention, so a down year
    regresses toward the unit's own multi-year baseline instead of becoming the whole forecast."""
    age = np.asarray(base_season, dtype=float) - _num(seasons)
    w = np.power(float(decay), np.clip(age, 0.0, None))
    return np.where(np.isfinite(w) & (age >= 0), w, 0.0)


def weighted_prior_rate(hist: pd.DataFrame, base_season: int, key: str, value_col: str,
                        games_col: str = "games", *,
                        window: int = PRIOR_WINDOW_YEARS,
                        decay: float = PRIOR_RECENCY_DECAY) -> pd.DataFrame:
    """A recency+games-weighted PER-GAME rate over the `window` seasons ending at `base_season`.

    Returns `DataFrame[key, prior_rate, prior_games]`. Weighting by games as well as recency means a
    unit with one thin season is not treated as though it had three full ones — the same
    `w = decay^age × games` construction MVP-1's veteran line uses."""
    lo = int(base_season) - int(window) + 1
    h = hist[(_num(hist["season"]) >= lo) & (_num(hist["season"]) <= int(base_season))].copy()
    if h.empty:
        return pd.DataFrame({key: [], "prior_rate": [], "prior_games": []})
    g = _num(h[games_col])
    h["_w"] = recency_weights(h["season"], base_season, decay=decay) * np.clip(g, 0.0, None)
    h["_v"] = _num(h[value_col])
    out = (h.groupby(key)
             .apply(lambda d: pd.Series({
                 "prior_rate": (float(np.sum(d["_v"] * d["_w"] / np.clip(_num(d[games_col]), 1e-9, None)))
                                / float(np.sum(d["_w"]))) if float(np.sum(d["_w"])) > 0 else np.nan,
                 "prior_games": float(np.sum(_num(d[games_col]))),
             }), include_groups=False)
             .reset_index())
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The DST component model — an IN-FOLD regression, which IS the shrink
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class LinearShrink:
    """`rate = intercept + slope × prior_rate` — the honest regression-to-the-mean of a per-game
    rate on its own recency-weighted prior. The FITTED SLOPE **is** the shrink factor: slope ≈ 0
    means "this component carries no forward signal, project the league mean"; slope ≈ 1 means "it
    persists fully". Nothing is hand-tuned, and a component's reliability is therefore re-measured
    from data every run rather than pinned to a constant that can silently rot."""

    slope: float
    intercept: float
    league_mean: float
    n: int
    r: float = 0.0
    forced_mean: bool = False   # True ⇒ the component is a declared noise term (slope pinned to 0)

    def predict(self, prior_rate) -> np.ndarray:
        p = _num(prior_rate)
        out = self.intercept + self.slope * np.where(np.isfinite(p), p, self.league_mean)
        # a unit with NO prior history falls to the league mean, never to the intercept alone
        out = np.where(np.isfinite(p), out, self.league_mean)
        return np.clip(out, 0.0, None)

    def to_dict(self) -> dict:
        return {"slope": round(float(self.slope), 4), "intercept": round(float(self.intercept), 4),
                "league_mean": round(float(self.league_mean), 4), "n": int(self.n),
                "r": round(float(self.r), 4), "forced_mean": bool(self.forced_mean)}


def fit_linear_shrink(prior_rate, realized_rate, *, force_mean: bool = False) -> LinearShrink:
    """OLS of a realized per-game rate on its recency-weighted prior. `force_mean=True` pins the
    slope to 0 (the declared-noise path) so the projection is the league mean exactly."""
    p, y = _num(prior_rate), _num(realized_rate)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    league = float(np.mean(y)) if len(y) else 0.0
    if force_mean or len(y) < 30 or np.std(p) < 1e-12:
        return LinearShrink(slope=0.0, intercept=league, league_mean=league, n=int(len(y)),
                            r=0.0, forced_mean=True)
    slope, intercept = np.polyfit(p, y, 1)
    r = float(np.corrcoef(p, y)[0, 1])
    # ⚠️ a NEGATIVE fitted slope on a per-game rate is noise, not an anti-signal worth serving —
    #    clamp to the league mean rather than projecting a good defense to be bad next year.
    if slope <= 0:
        return LinearShrink(slope=0.0, intercept=league, league_mean=league, n=int(len(y)),
                            r=r, forced_mean=True)
    return LinearShrink(slope=float(slope), intercept=float(intercept), league_mean=league,
                        n=int(len(y)), r=r)


def build_dst_training_panel(team_def: pd.DataFrame, team_points: pd.DataFrame,
                             sos: pd.DataFrame | None, target_seasons: list[int], *,
                             window: int = PRIOR_WINDOW_YEARS,
                             team_yards: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (target season, team): each DST component's recency-weighted PRIOR per-game rate
    (from seasons ≤ target−1) beside its REALIZED per-game rate in the target season.

    This is the frame every DST regression is fitted on, and it is strictly leakage-safe: a target
    season's own data never appears among its predictors."""
    def_by = team_def.copy()
    pts = team_points.copy()
    rows = []
    for y in sorted(int(v) for v in target_seasons):
        real_def = def_by[_num(def_by["season"]) == y]
        real_pts = pts[_num(pts["season"]) == y]
        if real_def.empty or real_pts.empty:
            continue
        cur = real_def.merge(real_pts[["season", "team", "team_games", "points_against",
                                       "points_against_pg"]],
                             on=["season", "team"], how="inner")
        if cur.empty:
            continue
        rec = cur[["season", "team", "games", "team_games"]].copy()
        rec["target_season"] = y
        for c in DST_COMPONENTS:
            if c not in cur.columns or c not in def_by.columns:
                # The loaded history does not carry this component. Build NO columns for it rather
                # than zero-filling: `fit_dst_component_model` then skips it, `project_dst` emits
                # nothing, and the term is reported CAPTURED — the truth. A zero-filled component
                # would instead be fitted, projected and scored as APPLIED against fabricated data.
                continue
            rec[f"real_{c}"] = _num(cur[c]) / np.clip(_num(cur["games"]), 1e-9, None)
            pr = weighted_prior_rate(def_by, y - 1, "team", c, window=window)
            rec = rec.merge(pr.rename(columns={"prior_rate": f"prior_{c}",
                                               "prior_games": f"prior_games_{c}"}),
                            on="team", how="left")
        rec["real_pa_pg"] = _num(cur["points_against_pg"])
        pa_prior = weighted_prior_rate(
            pts.assign(pa_tot=_num(pts["points_against"]), games=_num(pts["team_games"])),
            y - 1, "team", "pa_tot", window=window)
        rec = rec.merge(pa_prior.rename(columns={"prior_rate": "prior_pa_pg",
                                                 "prior_games": "prior_pa_games"}),
                        on="team", how="left")
        # ── NF-C0e: the yards-allowed pair, built the SAME leakage-safe way ──────────────────
        # Absent `team_yards` leaves the columns out entirely rather than filling zeros: a zero
        # yards-allowed rate would read as "this defense allows no yardage", and `fit_dst_
        # component_model` then simply does not fit the family (its mix stays None and
        # `project_dst` emits no yards columns), which the coverage machinery reports honestly
        # as CAPTURED. A silently-zeroed family would instead score as an APPLIED lie.
        if team_yards is not None and not team_yards.empty:
            cur_y = team_yards[_num(team_yards["season"]) == y]
            if not cur_y.empty:
                rec = rec.merge(cur_y[["team", "yards_against_pg"]]
                                .rename(columns={"yards_against_pg": "real_ya_pg"}),
                                on="team", how="left")
                ya_prior = weighted_prior_rate(
                    team_yards.assign(ya_tot=_num(team_yards["yards_against"]),
                                      games=_num(team_yards["team_games"])),
                    y - 1, "team", "ya_tot", window=window)
                rec = rec.merge(ya_prior.rename(columns={"prior_rate": "prior_ya_pg",
                                                         "prior_games": "prior_ya_games"}),
                                on="team", how="left")
        if sos is not None and not sos.empty:
            s = sos[_num(sos["season"]) == y]
            if not s.empty:
                rec = rec.merge(s[["team", "sos_off_z"]], on="team", how="left")
        rows.append(rec)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True, sort=False)
    if "sos_off_z" not in out.columns:
        out["sos_off_z"] = 0.0
    out["sos_off_z"] = np.nan_to_num(_num(out["sos_off_z"]), nan=0.0)
    return out


@dataclass
class DstModel:
    """The fitted DST base model: one `LinearShrink` per counting component + the points-allowed
    regression (prior PA rate + a strength-of-schedule tilt) + the empirical PA bucket mix."""

    components: dict[str, LinearShrink] = field(default_factory=dict)
    pa_slope: float = 0.0
    pa_intercept: float = 0.0
    pa_sos_coef: float = 0.0
    pa_league_mean: float = 0.0
    pa_resid_sd: float = 0.0
    pa_n: int = 0
    pa_r: float = 0.0
    pa_mix: "ConditionalBucketMix | None" = None
    # ── NF-C0e: the YARDS-allowed twin. Same regression shape, its own fitted coefficients. ──
    # Measured: yards allowed per game is MORE persistent season to season than points allowed
    # (lag-1 ρ = 0.401 vs 0.316 on the same 829 team-season pairs), which is the substantive
    # reason this family graduates rather than a modelling preference.
    ya_slope: float = 0.0
    ya_intercept: float = 0.0
    ya_sos_coef: float = 0.0
    ya_league_mean: float = 0.0
    ya_resid_sd: float = 0.0
    ya_n: int = 0
    ya_r: float = 0.0
    ya_mix: "ConditionalBucketMix | None" = None

    def to_dict(self) -> dict:
        return {
            "components": {k: v.to_dict() for k, v in self.components.items()},
            "points_allowed": {"slope": round(self.pa_slope, 4),
                               "intercept": round(self.pa_intercept, 3),
                               "sos_coef": round(self.pa_sos_coef, 4),
                               "league_mean_pg": round(self.pa_league_mean, 3),
                               "resid_sd_pg": round(self.pa_resid_sd, 3),
                               "n": int(self.pa_n), "r": round(self.pa_r, 4)},
            "pa_mix": None if self.pa_mix is None else self.pa_mix.to_dict(),
            "yards_allowed": {"slope": round(self.ya_slope, 4),
                              "intercept": round(self.ya_intercept, 3),
                              "sos_coef": round(self.ya_sos_coef, 4),
                              "league_mean_pg": round(self.ya_league_mean, 3),
                              "resid_sd_pg": round(self.ya_resid_sd, 3),
                              "n": int(self.ya_n), "r": round(self.ya_r, 4)},
            "ya_mix": None if self.ya_mix is None else self.ya_mix.to_dict(),
        }


def fit_dst_component_model(panel: pd.DataFrame, *,
                            noise_components: tuple = DST_NOISE_COMPONENTS,
                            pa_bins: int = 5) -> DstModel:
    """Fit every DST component's shrink + the points-allowed model on a leakage-safe panel."""
    if panel is None or panel.empty:
        raise ValueError("fit_dst_component_model: empty training panel — refusing to fit a model "
                         "on nothing (an unfittable model that returns silently is the NF1.7 "
                         "vacuous-anchor failure wearing a model's hat)")
    comps: dict[str, LinearShrink] = {}
    for c in DST_COMPONENTS:
        if f"real_{c}" not in panel.columns:
            continue          # a component the loaded history does not carry stays UNPROJECTED
        comps[c] = fit_linear_shrink(panel.get(f"prior_{c}"), panel.get(f"real_{c}"),
                                     force_mean=c in noise_components)

    def _rate_regression(prior_col: str, real_col: str):
        """realized per-game rate ~ prior per-game rate + SOS(z of opponents' offensive strength).

        Shared verbatim by the points- and yards-allowed families so the two are the SAME model
        with different inputs — there is no second implementation to drift."""
        if prior_col not in panel.columns or real_col not in panel.columns:
            return None
        p = _num(panel[prior_col])
        s = np.nan_to_num(_num(panel["sos_off_z"]), nan=0.0)
        y = _num(panel[real_col])
        ok = np.isfinite(p) & np.isfinite(y)
        league = float(np.mean(y[ok])) if ok.any() else 0.0
        if ok.sum() >= 30 and np.std(p[ok]) > 1e-12:
            X = np.column_stack([np.ones(ok.sum()), p[ok], s[ok]])
            coef, *_ = np.linalg.lstsq(X, y[ok], rcond=None)
            intercept, slope, sos_coef = (float(coef[0]), float(coef[1]), float(coef[2]))
            resid = y[ok] - X @ coef
            r = float(np.corrcoef(X @ coef, y[ok])[0, 1])
        else:
            intercept, slope, sos_coef = league, 0.0, 0.0
            resid = y[ok] - league if ok.any() else np.array([0.0])
            r = 0.0
        return dict(slope=slope, intercept=intercept, sos_coef=sos_coef, league_mean=league,
                    resid_sd=float(np.std(resid)) if len(resid) else 0.0,
                    n=int(ok.sum()), r=r)

    pa = _rate_regression("prior_pa_pg", "real_pa_pg") or {}
    ya = _rate_regression("prior_ya_pg", "real_ya_pg") or {}
    return DstModel(components=comps,
                    pa_slope=pa.get("slope", 0.0), pa_intercept=pa.get("intercept", 0.0),
                    pa_sos_coef=pa.get("sos_coef", 0.0), pa_league_mean=pa.get("league_mean", 0.0),
                    pa_resid_sd=pa.get("resid_sd", 0.0), pa_n=pa.get("n", 0), pa_r=pa.get("r", 0.0),
                    ya_slope=ya.get("slope", 0.0), ya_intercept=ya.get("intercept", 0.0),
                    ya_sos_coef=ya.get("sos_coef", 0.0), ya_league_mean=ya.get("league_mean", 0.0),
                    ya_resid_sd=ya.get("resid_sd", 0.0), ya_n=ya.get("n", 0), ya_r=ya.get("r", 0.0))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The EMPIRICAL per-game points-allowed distribution
# ══════════════════════════════════════════════════════════════════════════════════════════════
def bucket_index(value, edges: tuple) -> np.ndarray:
    """Map a per-game value → the index of its bucket under `edges` (inclusive lower bounds)."""
    return np.digitize(_num(value), np.asarray(edges[1:], dtype=float), right=False)


def pa_bucket_index(points_allowed) -> np.ndarray:
    """Map per-game points allowed → the index of its `PA_BUCKET_LABELS` bucket."""
    return bucket_index(points_allowed, PA_BUCKET_EDGES)


def ya_bucket_index(yards_allowed) -> np.ndarray:
    """Map per-game yards allowed → the index of its `YA_BUCKET_LABELS` bucket."""
    return bucket_index(yards_allowed, YA_BUCKET_EDGES)


@dataclass
class ConditionalBucketMix:
    """The empirical per-game points-allowed bucket mix, CONDITIONAL on a team's points-allowed
    rate — a monotone quantile-bin lookup with linear interpolation between bin centres.

    Why not a parametric count model: a shutout is the most valuable game outcome under every tier
    scheme and P(0 PA) = 0.0099 in the data, while a negative binomial matched to the observed
    mean/variance puts ~1e-4 there. The empirical table reproduces the atom by construction, and it
    also reproduces the observed monotonicity (best-quintile defenses are shut-out-capable 2.4% of
    games, worst-quintile 0.0%)."""

    anchors: np.ndarray                    # bin-centre per-game RATE values, ascending
    mix: np.ndarray                        # (n_bins, 9) row-normalised bucket probabilities
    labels: tuple = PA_BUCKET_LABELS
    n_games: int = 0
    edges: tuple = PA_BUCKET_EDGES

    def probabilities(self, pa_per_game) -> np.ndarray:
        """(n, 9) bucket probabilities for each requested points-allowed rate."""
        x = _num(pa_per_game)
        x = np.where(np.isfinite(x), x, float(np.mean(self.anchors)))
        out = np.empty((len(x), self.mix.shape[1]), dtype=float)
        for j in range(self.mix.shape[1]):
            out[:, j] = np.interp(x, self.anchors, self.mix[:, j])
        tot = out.sum(axis=1, keepdims=True)
        return out / np.where(tot > 1e-12, tot, 1.0)

    def to_dict(self) -> dict:
        return {"n_games": int(self.n_games),
                "anchors": [round(float(a), 2) for a in self.anchors],
                "mix": [[round(float(v), 4) for v in row] for row in self.mix],
                "labels": list(self.labels)}


# NF1.6 named this class for the one family it had. NF-C0e added a second (yards allowed) that
# differs ONLY in its bucket edges, so the class is now general and the old name is kept as an
# alias — an import or a construction written against NF1.6 keeps working byte-identically.
PointsAllowedMix = ConditionalBucketMix


def fit_conditional_bucket_mix(team_games: pd.DataFrame, team_seasons: pd.DataFrame, *,
                               value_col: str, rate_col: str, edges: tuple, labels: tuple,
                               n_bins: int = 5) -> ConditionalBucketMix:
    """Fit the empirical per-game bucket mix CONDITIONAL on a team-season's own per-game rate.

    `n_bins=5` (quintiles) keeps ≥600 team-games per cell at the historical panel size — fine
    enough to show the monotone structure, coarse enough that a ~1% tail atom (the shutout, on the
    points family) is estimated off hundreds of games rather than dozens."""
    g = team_games.merge(team_seasons[["season", "team", rate_col]],
                         on=["season", "team"], how="inner")
    if g.empty:
        raise ValueError(f"fit_conditional_bucket_mix({value_col}): no team-game rows to fit on")
    g = g.assign(_b=bucket_index(g[value_col], edges))
    # quantile bins on the team-season rate; `duplicates='drop'` guards a degenerate slice
    try:
        g["_bin"] = pd.qcut(_num(g[rate_col]), n_bins, labels=False, duplicates="drop")
    except ValueError:
        g["_bin"] = 0
    anchors, rows = [], []
    for _b, d in g.groupby("_bin"):
        counts = np.bincount(_num(d["_b"]).astype(int), minlength=len(labels)).astype(float)
        tot = counts.sum()
        if tot <= 0:
            continue
        anchors.append(float(np.mean(_num(d[rate_col]))))
        rows.append(counts / tot)
    if not rows:
        raise ValueError(f"fit_conditional_bucket_mix({value_col}): every bin was empty")
    order = np.argsort(anchors)
    return ConditionalBucketMix(anchors=np.asarray(anchors, dtype=float)[order],
                                mix=np.vstack(rows)[order], labels=labels, edges=edges,
                                n_games=int(len(g)))


def fit_points_allowed_mix(team_game_points: pd.DataFrame, team_points: pd.DataFrame, *,
                           n_bins: int = 5) -> ConditionalBucketMix:
    """Fit the per-game POINTS-allowed bucket mix (NF1.6's original; now a thin instantiation)."""
    return fit_conditional_bucket_mix(
        team_game_points, team_points, value_col="points_against",
        rate_col="points_against_pg", edges=PA_BUCKET_EDGES, labels=PA_BUCKET_LABELS,
        n_bins=n_bins)


def fit_yards_allowed_mix(team_game_yards: pd.DataFrame, team_yards: pd.DataFrame, *,
                          n_bins: int = 5) -> ConditionalBucketMix:
    """Fit the per-game YARDS-allowed bucket mix (NF-C0e). Identical machinery, new edges."""
    return fit_conditional_bucket_mix(
        team_game_yards, team_yards, value_col="yards_against",
        rate_col="yards_against_pg", edges=YA_BUCKET_EDGES, labels=YA_BUCKET_LABELS,
        n_bins=n_bins)


def expected_bucket_games(per_game_rate, games, mix: ConditionalBucketMix) -> np.ndarray:
    """(n, 9) EXPECTED NUMBER OF GAMES in each bucket = games × P(bucket).

    ⭐ This is the linear-scoreable form, and it is the whole reason a tier table needs no engine
    change: a per-game tier table scores a season as `Σ_bucket tier_points × expected_games`, which
    is LINEAR in these columns, so the existing sport-agnostic scorer expresses ANY tier scheme
    EXACTLY rather than approximating it."""
    return mix.probabilities(per_game_rate) * _num(games).reshape(-1, 1)


def expected_pa_bucket_games(pa_per_game, games, mix: ConditionalBucketMix) -> np.ndarray:
    """NF1.6's points-allowed name for `expected_bucket_games`, kept for existing callers."""
    return expected_bucket_games(pa_per_game, games, mix)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# DST projection
# ══════════════════════════════════════════════════════════════════════════════════════════════
def schedule_offense_strength(sched: pd.DataFrame, team_points: pd.DataFrame,
                              projection_season: int, *,
                              window: int = PRIOR_WINDOW_YEARS) -> pd.DataFrame:
    """Strength of schedule for a DEFENSE = how good the offenses on its schedule are.

    Each opponent's offensive level is its recency-weighted prior points-for rate (≤ projection−1 —
    leakage-safe); a team's SOS is the mean over its scheduled opponents, z-scored across the
    league. Returns `DataFrame[season, team, sos_off_z, sos_off_pg]`. A team with no schedule row
    gets 0 (league-average), never NaN."""
    pri = weighted_prior_rate(
        team_points.assign(pf_tot=_num(team_points["points_for"]),
                           games=_num(team_points["team_games"])),
        int(projection_season) - 1, "team", "pf_tot", window=window)
    lvl = dict(zip(pri["team"], _num(pri["prior_rate"])))
    league = float(np.nanmean(list(lvl.values()))) if lvl else 0.0
    s = sched.copy()
    s["_opp_level"] = [lvl.get(o, league) for o in s["opponent"]]
    out = (s.groupby("team", as_index=False)["_opp_level"].mean()
            .rename(columns={"_opp_level": "sos_off_pg"}))
    out["season"] = int(projection_season)
    out["sos_off_z"] = zscore(out["sos_off_pg"])
    return out[["season", "team", "sos_off_pg", "sos_off_z"]]


def project_dst(universe: pd.DataFrame, team_def_hist: pd.DataFrame, team_points_hist: pd.DataFrame,
                model: DstModel, sos: pd.DataFrame, projection_season: int, *,
                window: int = PRIOR_WINDOW_YEARS,
                team_yards_hist: pd.DataFrame | None = None) -> pd.DataFrame:
    """Project every team defense in `universe` for `projection_season`.

    Each counting component = its fitted `LinearShrink` applied to the team's recency-weighted
    prior per-game rate, × scheduled games. Points allowed = the fitted PA regression (prior rate +
    SOS tilt), and its per-game DISTRIBUTION comes from the empirical bucket mix."""
    if model.pa_mix is None:
        raise ValueError("project_dst: the model carries no points-allowed mix — the tier-scoreable "
                         "bucket columns cannot be emitted, and emitting them as zeros would read "
                         "as 'this defense never allows points'")
    base = int(projection_season) - 1
    out = universe.copy()
    out["proj_games"] = _num(out["scheduled_games"])
    for c in DST_COMPONENTS:
        if c not in model.components or c not in team_def_hist.columns:
            continue          # unfitted / unloaded component ⇒ NO column ⇒ honestly CAPTURED
        pr = weighted_prior_rate(team_def_hist, base, "team", c, window=window)
        out = out.merge(pr.rename(columns={"prior_rate": f"_pr_{c}",
                                          "prior_games": f"_pg_{c}"}), on="team", how="left")
        rate = model.components[c].predict(out[f"_pr_{c}"])
        out[f"proj_{c}"] = rate * _num(out["proj_games"])
    pa_prior = weighted_prior_rate(
        team_points_hist.assign(pa_tot=_num(team_points_hist["points_against"]),
                                games=_num(team_points_hist["team_games"])),
        base, "team", "pa_tot", window=window)
    out = out.merge(pa_prior.rename(columns={"prior_rate": "_pr_pa"}), on="team", how="left")
    out = out.merge(sos[["team", "sos_off_z", "sos_off_pg"]], on="team", how="left")
    out["sos_off_z"] = np.nan_to_num(_num(out["sos_off_z"]), nan=0.0)
    pr_pa = _num(out["_pr_pa"])
    pa_pg = np.where(np.isfinite(pr_pa),
                     model.pa_intercept + model.pa_slope * pr_pa
                     + model.pa_sos_coef * _num(out["sos_off_z"]),
                     model.pa_league_mean)
    out["proj_dst_pa_per_game"] = np.clip(pa_pg, 0.0, None)
    out["proj_dst_pa_per_game_sd"] = float(model.pa_resid_sd)
    out["proj_dst_points_allowed"] = out["proj_dst_pa_per_game"] * _num(out["proj_games"])
    buckets = expected_bucket_games(out["proj_dst_pa_per_game"], out["proj_games"], model.pa_mix)
    for j, col in enumerate(PA_BUCKET_COLS):
        out[col] = buckets[:, j]

    # ── NF-C0e: the YARDS-allowed family, emitted only when it was actually fitted ────────────
    # No `ya_mix` ⇒ no columns at all. That is deliberate: `resolve_scoring` classifies a term
    # against the columns the frame REALLY has, so an unfitted family reports CAPTURED (the truth)
    # instead of scoring a fabricated zero behind an "applied" label.
    if model.ya_mix is not None and team_yards_hist is not None and not team_yards_hist.empty:
        ya_prior = weighted_prior_rate(
            team_yards_hist.assign(ya_tot=_num(team_yards_hist["yards_against"]),
                                   games=_num(team_yards_hist["team_games"])),
            base, "team", "ya_tot", window=window)
        out = out.merge(ya_prior.rename(columns={"prior_rate": "_pr_ya"}), on="team", how="left")
        pr_ya = _num(out["_pr_ya"])
        ya_pg = np.where(np.isfinite(pr_ya),
                         model.ya_intercept + model.ya_slope * pr_ya
                         + model.ya_sos_coef * _num(out["sos_off_z"]),
                         model.ya_league_mean)
        out["proj_dst_ya_per_game"] = np.clip(ya_pg, 0.0, None)
        out["proj_dst_ya_per_game_sd"] = float(model.ya_resid_sd)
        out["proj_dst_yards_allowed"] = out["proj_dst_ya_per_game"] * _num(out["proj_games"])
        ya_buckets = expected_bucket_games(out["proj_dst_ya_per_game"], out["proj_games"],
                                           model.ya_mix)
        for j, col in enumerate(YA_BUCKET_COLS):
            out[col] = ya_buckets[:, j]

    out["position"] = "DST"
    out["player_id"] = "DST-" + out["team"].astype(str)
    out["player_name"] = out["team"].astype(str) + " D/ST"
    out["team_id"] = out["team"]
    out["projection_season"] = int(projection_season)
    out["base_season"] = base
    out["source"] = "dst_base"
    # a defense that never played before is projected at the league mean throughout — flag it
    out["confidence"] = np.where(np.isfinite(pr_pa), "low", "very_low")
    drop = [c for c in out.columns if c.startswith(("_pr_", "_pg_"))]
    return out.drop(columns=drop)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The KICKER model
# ══════════════════════════════════════════════════════════════════════════════════════════════
def is_active_status(status) -> np.ndarray:
    """Whether a roster designation means "expected to be on the field week 1". A blank status is
    treated as ACTIVE, not as a designation — the offseason snapshot often carries no status, and
    reading blank as inactive would zero out the whole projection-season universe."""
    s = pd.Series(status).fillna("").astype(str).str.strip().str.upper()
    return s.isin(_ACTIVE_STATUSES).to_numpy()


def resolve_primary_kicker(universe: pd.DataFrame, kicker_hist: pd.DataFrame,
                           projection_season: int, *,
                           window: int = PRIOR_WINDOW_YEARS) -> pd.DataFrame:
    """Flag the INCUMBENT (`is_primary`) kicker on each team: the one with the most recency-weighted
    prior FG-attempt volume. Adds `prior_fg_att_weighted` / `prior_fg_att` / `prior_games`.

    This is the job-resolution step a K projection cannot skip: 10 of 32 teams carry two kickers on
    the 2026 offseason roster, and a camp body projected like a starter would rank ahead of real
    starters. Ties (two kickers with no prior volume — a genuine open competition) break on
    `years_exp` then name, deterministically, and BOTH are still emitted with the expected-games
    table's non-primary share so the row is honest rather than absent."""
    base = int(projection_season) - 1
    lo = base - int(window) + 1
    h = kicker_hist[(_num(kicker_hist["season"]) >= lo) & (_num(kicker_hist["season"]) <= base)].copy()
    out = universe.copy()
    if h.empty:
        out["prior_fg_att_weighted"] = 0.0
        out["prior_fg_att"] = 0.0
        out["prior_games"] = 0.0
    else:
        h["_w"] = recency_weights(h["season"], base)
        agg = (h.assign(_wa=h["_w"] * _num(h["fg_att"]))
                 .groupby("player_id", as_index=False)
                 .agg(prior_fg_att_weighted=("_wa", "sum"),
                      prior_fg_att=("fg_att", "sum"),
                      prior_games=("games", "sum")))
        out = out.merge(agg, on="player_id", how="left")
        for c in ("prior_fg_att_weighted", "prior_fg_att", "prior_games"):
            out[c] = np.nan_to_num(_num(out[c]), nan=0.0)
    out["_exp"] = np.nan_to_num(_num(out.get("years_exp")), nan=0.0)
    out = out.sort_values(["team", "prior_fg_att_weighted", "_exp", "player_id"],
                         ascending=[True, False, False, True]).reset_index(drop=True)
    out["is_primary"] = ~out.duplicated(subset=["team"], keep="first")
    return out.drop(columns=["_exp"])


def fit_kicker_games_table(panel: pd.DataFrame, *, min_cell: int = 25) -> dict:
    """The four-cell `(is_active, is_primary) → expected share of team games` table, fitted on a
    historical panel of week-1-rostered kickers.

    ⚠️ A cell thinner than `min_cell` rows falls back to the measured fallback constant and is
    reported — never silently to 1.0, which would project a camp body as a full-season starter."""
    if panel is None or panel.empty:
        return dict(KICKER_GAMES_SHARE)
    out: dict = {}
    for (a, p), d in panel.groupby(["is_active", "is_primary"]):
        share = _num(d["real_games"]) / np.clip(_num(d["team_games"]), 1e-9, None)
        share = share[np.isfinite(share)]
        key = (bool(a), bool(p))
        out[key] = (float(np.mean(share)) if len(share) >= min_cell
                    else KICKER_GAMES_SHARE.get(key, KICKER_GAMES_SHARE_DEFAULT))
    for key, val in KICKER_GAMES_SHARE.items():
        out.setdefault(key, val)
    return out


@dataclass
class KickerModel:
    """The fitted kicker base model.

    `pat_att` and `fg_att` per game are both regressions on the TEAM's forward scoring
    environment; the FG one is QUADRATIC because the relationship is non-monotone (it peaks around
    25 points/game and turns down — elite offenses score touchdowns instead of kicking). The make
    rates and the distance mix are shrinks toward league average, with the mix shrunk far LESS
    because leg strength is the one kicker-side signal that persists (ρ = 0.429 vs 0.085)."""

    pat_att_coef: tuple = (0.0, 0.0)             # (intercept, slope) on team points/game
    fg_att_coef: tuple = (0.0, 0.0, 0.0)         # (c0, c1, c2) quadratic in team points/game
    pat_att_r: float = 0.0
    fg_att_r: float = 0.0
    league_att_mix: dict = field(default_factory=lambda: dict(FG_LEAGUE_ATT_MIX))
    league_make: dict = field(default_factory=lambda: dict(FG_LEAGUE_MAKE_RATE))
    pat_make: float = PAT_LEAGUE_MAKE_RATE
    make_shrink_attempts: float = 200.0         # prior weight on the make rate, in ATTEMPTS
    mix_shrink_attempts: float = 60.0           # prior weight on the distance mix, in ATTEMPTS
    games_table: dict = field(default_factory=lambda: dict(KICKER_GAMES_SHARE))
    n: int = 0

    def pat_att_per_game(self, team_points_pg) -> np.ndarray:
        c0, c1 = self.pat_att_coef
        return np.clip(c0 + c1 * _num(team_points_pg), 0.0, None)

    def fg_att_per_game(self, team_points_pg) -> np.ndarray:
        c0, c1, c2 = self.fg_att_coef
        x = _num(team_points_pg)
        return np.clip(c0 + c1 * x + c2 * x * x, 0.0, None)

    def to_dict(self) -> dict:
        return {"pat_att_coef": [round(float(v), 4) for v in self.pat_att_coef],
                "fg_att_coef": [round(float(v), 6) for v in self.fg_att_coef],
                "pat_att_r": round(float(self.pat_att_r), 4),
                "fg_att_r": round(float(self.fg_att_r), 4),
                "league_att_mix": {k: round(float(v), 4) for k, v in self.league_att_mix.items()},
                "league_make": {k: round(float(v), 4) for k, v in self.league_make.items()},
                "pat_make": round(float(self.pat_make), 4),
                "make_shrink_attempts": float(self.make_shrink_attempts),
                "mix_shrink_attempts": float(self.mix_shrink_attempts),
                "games_table": {f"active={a},primary={p}": round(float(v), 4)
                                for (a, p), v in sorted(self.games_table.items())},
                "n": int(self.n)}


def fit_kicker_model(team_kick_panel: pd.DataFrame, kicker_hist: pd.DataFrame,
                     games_panel: pd.DataFrame | None = None) -> KickerModel:
    """Fit the kicker base model on leakage-safe history.

    `team_kick_panel` — one row per (season, team) with `fg_att_pg`, `pat_att_pg` and
    `team_points_est_pg` (the FORWARD points estimate, i.e. the same quantity available at serve
    time; never the realized season total — that would be a train/serve inconsistency that flatters
    the fit and cannot be reproduced in production).
    `kicker_hist` — kicker-seasons, for the league attempt mix + per-bucket make rates.
    `games_panel` — the week-1-roster panel for the expected-games table.
    """
    p = team_kick_panel.dropna(subset=["team_points_est_pg"]).copy()
    x = _num(p["team_points_est_pg"])
    pat = _num(p["pat_att_pg"])
    fga = _num(p["fg_att_pg"])
    ok_pat = np.isfinite(x) & np.isfinite(pat)
    ok_fga = np.isfinite(x) & np.isfinite(fga)
    if ok_pat.sum() >= 30:
        c1, c0 = np.polyfit(x[ok_pat], pat[ok_pat], 1)
        pat_coef, pat_r = (float(c0), float(c1)), float(np.corrcoef(x[ok_pat], pat[ok_pat])[0, 1])
    else:
        pat_coef, pat_r = (float(np.mean(pat[ok_pat])) if ok_pat.any() else 2.3, 0.0), 0.0
    if ok_fga.sum() >= 60:
        q2, q1, q0 = np.polyfit(x[ok_fga], fga[ok_fga], 2)
        fg_coef = (float(q0), float(q1), float(q2))
        fg_r = float(np.corrcoef(np.polyval([q2, q1, q0], x[ok_fga]), fga[ok_fga])[0, 1])
    else:
        fg_coef, fg_r = (float(np.mean(fga[ok_fga])) if ok_fga.any() else 1.94, 0.0, 0.0), 0.0

    att_mix, make = {}, {}
    tot_att = 0.0
    for b in FG_BUCKETS:
        a = float(np.nansum(_num(kicker_hist[f"fg_made_{b}"]))
                  + np.nansum(_num(kicker_hist[f"fg_missed_{b}"])))
        m = float(np.nansum(_num(kicker_hist[f"fg_made_{b}"])))
        att_mix[b], make[b] = a, (m / a if a > 0 else FG_LEAGUE_MAKE_RATE[b])
        tot_att += a
    att_mix = ({b: att_mix[b] / tot_att for b in FG_BUCKETS} if tot_att > 0
               else dict(FG_LEAGUE_ATT_MIX))
    pat_att_tot = float(np.nansum(_num(kicker_hist["pat_att"])))
    pat_make = (float(np.nansum(_num(kicker_hist["pat_made"]))) / pat_att_tot
                if pat_att_tot > 0 else PAT_LEAGUE_MAKE_RATE)
    return KickerModel(pat_att_coef=pat_coef, fg_att_coef=fg_coef, pat_att_r=pat_r, fg_att_r=fg_r,
                       league_att_mix=att_mix, league_make=make, pat_make=pat_make,
                       games_table=fit_kicker_games_table(games_panel),
                       n=int(max(ok_pat.sum(), ok_fga.sum())))


def _shrink_to_prior(observed_num, observed_den, prior_value: float, prior_weight: float) -> np.ndarray:
    """Beta-binomial-style shrink of a rate: `(made + prior_w × prior) / (att + prior_w)`."""
    num, den = _num(observed_num), _num(observed_den)
    num = np.where(np.isfinite(num), num, 0.0)
    den = np.where(np.isfinite(den), den, 0.0)
    return (num + prior_weight * prior_value) / (den + prior_weight)


def project_kickers(universe: pd.DataFrame, kicker_hist: pd.DataFrame, model: KickerModel,
                    team_env: pd.DataFrame, team_games: pd.DataFrame, projection_season: int, *,
                    window: int = PRIOR_WINDOW_YEARS) -> pd.DataFrame:
    """Project every kicker in `universe` (the week-1 roster population) for `projection_season`.

    `team_env`   — `DataFrame[team, team_points_est_pg]`, the FORWARD scoring-environment estimate.
    `team_games` — `DataFrame[team, scheduled_games]`.
    """
    base = int(projection_season) - 1
    lo = base - int(window) + 1
    out = resolve_primary_kicker(universe, kicker_hist, projection_season, window=window)
    h = kicker_hist[(_num(kicker_hist["season"]) >= lo) & (_num(kicker_hist["season"]) <= base)]
    # a kicker's own history: total attempts + makes per bucket over the window (volume-weighted;
    # no recency decay here because the quantity being estimated is a RATE, and every attempt is
    # equally informative about it — decay is for LEVELS, which change with role)
    # ⚠️ The `own_*` column set must exist UNCONDITIONALLY, not only when history is non-empty. A
    #    projection season in which NO kicker in the universe has any prior NFL attempts (an early
    #    season, or an upstream outage) is a legitimate state — every kicker then projects off the
    #    league mix, which is exactly what the shrink is for. Building the column set only in the
    #    non-empty branch made that state a KeyError instead.
    own_cols = ["own_fg_att", "own_pat_att"]
    for b in FG_BUCKETS:
        own_cols += [f"own_made_{b}", f"own_missed_{b}"]
    if h.empty:
        agg = pd.DataFrame({c: pd.Series(dtype=float) for c in ["player_id", *own_cols]})
    else:
        spec = {"own_fg_att": ("fg_att", "sum"), "own_pat_att": ("pat_att", "sum")}
        for b in FG_BUCKETS:
            spec[f"own_made_{b}"] = (f"fg_made_{b}", "sum")
            spec[f"own_missed_{b}"] = (f"fg_missed_{b}", "sum")
        agg = h.groupby("player_id", as_index=False).agg(**spec)
    out = out.merge(agg, on="player_id", how="left")
    for c in own_cols:
        out[c] = np.nan_to_num(_num(out.get(c)), nan=0.0)

    out = out.merge(team_env[["team", "team_points_est_pg"]], on="team", how="left")
    out = out.merge(team_games[["team", "scheduled_games"]], on="team", how="left")
    env = _num(out["team_points_est_pg"])
    env = np.where(np.isfinite(env), env, float(np.nanmean(env)) if np.isfinite(env).any() else 22.0)
    sched = _num(out["scheduled_games"])
    sched = np.where(np.isfinite(sched) & (sched > 0), sched, 17.0)

    active = is_active_status(out.get("status"))
    primary = out["is_primary"].to_numpy(dtype=bool)
    share = np.array([model.games_table.get((bool(a), bool(p)), KICKER_GAMES_SHARE_DEFAULT)
                      for a, p in zip(active, primary)], dtype=float)
    out["is_active"] = active
    out["games_share"] = share
    out["proj_games"] = share * sched

    # per-game attempt volume comes from the TEAM (the kicker barely moves it — FG att/g ρ = 0.117)
    fga_pg = model.fg_att_per_game(env)
    pata_pg = model.pat_att_per_game(env)
    out["proj_fg_att"] = fga_pg * out["proj_games"]
    out["proj_pat_att"] = pata_pg * out["proj_games"]

    # DISTANCE MIX — genuinely per-kicker (leg strength persists, ρ(≥50yd att share) = 0.429),
    # shrunk toward the league mix with a `mix_shrink_attempts`-attempt prior.
    own_att_by_b = {b: _num(out[f"own_made_{b}"]) + _num(out[f"own_missed_{b}"]) for b in FG_BUCKETS}
    own_att_tot = sum(own_att_by_b.values())
    mix = {}
    for b in FG_BUCKETS:
        mix[b] = ((own_att_by_b[b] + model.mix_shrink_attempts * model.league_att_mix[b])
                  / (own_att_tot + model.mix_shrink_attempts))
    mix_tot = sum(mix.values())
    for b in FG_BUCKETS:
        mix[b] = mix[b] / np.where(mix_tot > 1e-12, mix_tot, 1.0)

    # MAKE RATE — near-random year-to-year (ρ = 0.085), so shrunk HARD (a 200-attempt prior is
    # roughly two and a half full seasons of a starter's volume, i.e. a kicker's own record barely
    # moves the projection). This is the honest expression of "kicker accuracy is not a skill we
    # can forecast", not a modelling shortcut.
    made_cols = {}
    for b in FG_BUCKETS:
        rate = _shrink_to_prior(out[f"own_made_{b}"], own_att_by_b[b],
                                model.league_make[b], model.make_shrink_attempts)
        made_cols[b] = out["proj_fg_att"].to_numpy() * mix[b] * rate
    out["proj_fg_made_0_39"] = made_cols["0_39"]
    out["proj_fg_made_40_49"] = made_cols["40_49"]
    out["proj_fg_made_50_plus"] = made_cols["50_plus"]
    out["proj_fg_made"] = sum(made_cols.values())
    out["proj_fg_missed"] = np.clip(out["proj_fg_att"] - out["proj_fg_made"], 0.0, None)
    pat_rate = _shrink_to_prior(out["own_pat_att"] * model.pat_make, out["own_pat_att"],
                                model.pat_make, model.make_shrink_attempts)
    out["proj_pat_made"] = out["proj_pat_att"] * pat_rate
    # ⛔ NF-C0e DELIBERATELY DOES NOT EMIT `proj_pat_missed`, THOUGH IT IS ONE SUBTRACTION AWAY.
    #    `pat_att - pat_made` is right there, and a league that scores a missed PAT (the operator's
    #    Sleeper league does, at -1) has that rule CAPTURED. It stays captured because it FAILED
    #    its held-out gate, not because it was hard: against a league-mean degenerate over 16
    #    seasons of kickers it wins MAE in 8/16 folds (+0.21%) where the calibrated clause requires
    #    11/16. The reason is the same one NF1.6 already measured — make rate is near-random
    #    (ρ=0.085) — so the projection reduces to `volume × a league constant` and 44% of
    #    kicker-seasons record ZERO misses. Emitting it would move every board on noise while
    #    wearing the "applied" label, which is strictly worse than an honest "captured".

    out["position"] = "K"
    out["team_id"] = out["team"]
    out["projection_season"] = int(projection_season)
    out["base_season"] = base
    out["source"] = "k_base"
    # a kicker with no NFL attempts in the window is projected almost entirely off the league mix
    out["confidence"] = np.where(_num(out["own_fg_att"]) >= 20, "low", "very_low")
    return out.drop(columns=[c for c in out.columns if c.startswith("own_")])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CONVENIENCE scoring (ranking + validation only)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def score_convenience(df: pd.DataFrame, *, out_col: str = "proj_fp_std") -> pd.Series:
    """The convenience fantasy total for a mixed K/DST frame under the modal default scheme.

    ⚠️ NOT the product contract — exactly like MVP-1's `proj_fp_ppr`, this exists so the board can
    be RANKED and the projection VALIDATED. NF-C1 rescores the raw components per league, and the
    points-allowed tier terms are expressed through the `proj_dst_pa_g_*` expected-games columns
    (which is what makes any tier scheme exact under a linear scorer)."""
    pts = pd.Series(0.0, index=df.index)
    for col, w in {**K_CONVENIENCE_SCORING, **DST_CONVENIENCE_SCORING}.items():
        if col in df.columns:
            pts = pts + w * pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for label, col in zip(PA_BUCKET_LABELS, PA_BUCKET_COLS):
        if col in df.columns:
            pts = pts + DST_PA_TIER_POINTS[label] * pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return pts.rename(out_col)


def realized_convenience(df: pd.DataFrame) -> pd.Series:
    """The REALIZED convenience total for a historical K or DST season — the band's target.

    Built from the same scheme `score_convenience` applies, off realized columns: for a kicker the
    distance-bucketed makes + PATs; for a defense the takeaways + the per-game points-allowed tier
    points (which is why the realized side needs per-GAME points allowed, not just the season sum)."""
    pts = pd.Series(0.0, index=df.index)
    for raw, w in (("fg_made_0_39", 3.0), ("fg_made_40_49", 4.0), ("fg_made_50_plus", 5.0),
                   ("pat_made", 1.0), ("def_sacks", 1.0), ("def_int", 2.0),
                   ("def_fumble_rec", 2.0), ("def_td", 6.0), ("st_td", 6.0),
                   ("def_safety", 2.0), ("def_blocked_kick", 2.0)):
        if raw in df.columns:
            pts = pts + w * pd.to_numeric(df[raw], errors="coerce").fillna(0.0)
    for label in PA_BUCKET_LABELS:
        col = f"pa_g_{label}"
        if col in df.columns:
            pts = pts + DST_PA_TIER_POINTS[label] * pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return pts


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE INTERVAL — a reported ratio band, not a selected one
# ══════════════════════════════════════════════════════════════════════════════════════════════
_ALPHA = 0.20
NOMINAL_COVERAGE = 1.0 - _ALPHA          # 0.80, the same convention as NF1.7/1.8/1.9
BAND_QUANTILES = (0.10, 0.90)
BAND_MIN_GROUP_N = 60                    # below this a group falls back to the pooled position band

# ⭐ PARAMETER-UNCERTAINTY WIDENING (pre-registered at 1.0 across-season SD, before measuring whether
#    it clears any floor). A pooled ROW quantile treats every row as an independent draw, but rows
#    inside a season share that season's regime and are not independent — the same class-clustering
#    NF1.8 makes explicit for per-position floors. Measured here: the K-starter ratio q10 moves from
#    0.31 to 0.94 ACROSS SEASONS (across-season SD ≈ 0.20) while the pooled row quantile is a single
#    0.63. So a band that quotes the pooled quantile is implicitly claiming to know next season's
#    quantile exactly, and it under-covers by exactly that unmodelled spread. Shifting each bound
#    outward by `z ×` the across-season SD of that bound prices the uncertainty in the band's OWN
#    quantile estimate — the same reason NF1.4/NF1.7 widen rookie intervals for P1A parameter
#    uncertainty. `z` is a DESIGN choice fixed in advance; it is NOT tuned until coverage clears
#    nominal (that would make the floor a target — the E2.1-r inversion).
BAND_CLUSTER_Z = 1.0
BAND_MIN_CLUSTER_SEASONS = 4             # below this the across-season SD is not estimable


def interval_score(lo, hi, y, alpha: float = _ALPHA) -> np.ndarray:
    """Winkler / Gneiting-Raftery interval score for a central (1−α) interval (LOWER is better).

    Reported, not optimised — there is no candidate field here. It is the right number to report
    because it is PROPER for the quantile pair: neither a zero-width band (full miss penalty) nor an
    all-encompassing one (pays its own width) can win it, which is what makes the two degenerate
    anchors in the report meaningful rather than decorative."""
    lo, hi, y = (np.asarray(v, dtype=float) for v in (lo, hi, y))
    return (hi - lo) + (2.0 / alpha) * (np.clip(lo - y, 0, None) + np.clip(y - hi, 0, None))


def _boolmask(v, n: int) -> np.ndarray:
    """A NaN-safe boolean view of a possibly-object/None column (`None` ⇒ all True)."""
    if v is None:
        return np.ones(n, dtype=bool)
    s = pd.Series(v)
    return s.map(lambda x: bool(x) if x is not None and x is not pd.NA and x == x
                 else False).to_numpy(dtype=bool)


def band_group(position, is_primary=None, is_active=None) -> np.ndarray:
    """The band group of each row. DST is a single group (all 32 defenses play a full season). K
    splits on the ONE factor that changes the outcome distribution completely — whether the row is
    the team's locked-in starter (mean games share 0.923) or a camp body (0.140)."""
    pos = pd.Series(position).astype(str).to_numpy()
    prim = _boolmask(is_primary, len(pos))
    act = _boolmask(is_active, len(pos))
    starter = prim & act
    return np.where(pos == "DST", "DST",
                    np.where(starter, "K_starter", "K_reserve"))


@dataclass
class RatioBand:
    """Empirical quantiles of `realized / projected` per band group → an ASYMMETRIC 80% interval.

    A multiplicative band is the right base shape for these two populations: both targets floor at
    exactly 0 (a cut kicker scores 0; a defense's takeaway line can collapse) and both have a long
    right tail, so an additive symmetric band would push the lower bound below the floor and
    understate the upside. It also carries the ZERO ATOM honestly: 13.1% of week-1-rostered kickers
    realise 0, so the `K_reserve` group's q10 ratio IS 0 and its p10 is 0 — which is the truth, not
    a modelling failure.

    ⚠️ `groups` is keyed by band group; a group thinner than `BAND_MIN_GROUP_N` falls back to the
    pooled position band **loudly** (recorded in `fell_back`), never to a silent (1,1) no-op."""

    groups: dict = field(default_factory=dict)          # group -> (q_lo, q_hi), already cluster-widened
    pooled: dict = field(default_factory=dict)          # position -> (q_lo, q_hi)
    n_by_group: dict = field(default_factory=dict)
    fell_back: tuple = ()
    quantiles: tuple = BAND_QUANTILES
    widen: float = 1.0                                  # honest post-hoc widening multiplier
    cluster_z: float = 0.0                              # the pre-registered parameter-uncertainty z
    raw_groups: dict = field(default_factory=dict)      # the pre-widening pooled row quantiles
    cluster_sd: dict = field(default_factory=dict)      # group -> (sd_lo, sd_hi, n_seasons)

    def ratios_for(self, groups) -> tuple[np.ndarray, np.ndarray]:
        g = pd.Series(groups).astype(str).to_numpy()
        lo = np.empty(len(g)); hi = np.empty(len(g))
        for i, gg in enumerate(g):
            pos = "DST" if gg == "DST" else "K"
            q = self.groups.get(gg) or self.pooled.get(pos)
            if q is None:
                raise KeyError(
                    f"RatioBand has no band for group {gg!r} and no pooled fallback for {pos!r} — "
                    f"refusing to emit an interval. A band that quietly returns None makes every "
                    f"coverage check downstream pass on NOTHING (NF1.7 anchor lesson).")
            lo[i], hi[i] = float(q[0]), float(q[1])
        # widening is applied to the HALF-WIDTHS around 1.0 so it can only ever WIDEN (never
        # sharpen one side), the monotonicity NF1.7 (d) requires of a widen-only knob
        w = max(1.0, float(self.widen))
        return 1.0 - (1.0 - lo) * w, 1.0 + (hi - 1.0) * w

    def to_dict(self) -> dict:
        return {"quantiles": list(self.quantiles), "widen": round(float(self.widen), 4),
                "cluster_z": round(float(self.cluster_z), 3),
                "groups": {k: [round(float(v[0]), 4), round(float(v[1]), 4)]
                           for k, v in sorted(self.groups.items())},
                "raw_groups_before_cluster_widen":
                    {k: [round(float(v[0]), 4), round(float(v[1]), 4)]
                     for k, v in sorted(self.raw_groups.items())},
                "across_season_sd_of_the_quantile":
                    {k: {"sd_lo": round(float(v[0]), 4), "sd_hi": round(float(v[1]), 4),
                         "n_seasons": int(v[2])} for k, v in sorted(self.cluster_sd.items())},
                "pooled": {k: [round(float(v[0]), 4), round(float(v[1]), 4)]
                           for k, v in sorted(self.pooled.items())},
                "n_by_group": {k: int(v) for k, v in sorted(self.n_by_group.items())},
                "fell_back": list(self.fell_back)}


def _cluster_sd_of_quantile(g: pd.DataFrame, quantiles: tuple, season_col: str,
                            min_seasons: int) -> tuple[float, float, int]:
    """The ACROSS-SEASON standard deviation of a group's ratio quantile pair.

    This is the quantity the pooled row quantile silently assumes is zero. A season with too few
    rows to estimate a quantile at all is dropped from the spread (not counted as agreement)."""
    if season_col not in g.columns:
        return 0.0, 0.0, 0
    los, his = [], []
    for _, d in g.groupby(season_col):
        if len(d) < 8:      # a quantile off <8 rows is noise, not a season-level estimate
            continue
        los.append(float(np.quantile(d["_ratio"], quantiles[0])))
        his.append(float(np.quantile(d["_ratio"], quantiles[1])))
    if len(los) < min_seasons:
        return 0.0, 0.0, len(los)
    return (float(np.std(los, ddof=1)), float(np.std(his, ddof=1)), len(los))


def fit_ratio_band(panel: pd.DataFrame, *, quantiles: tuple = BAND_QUANTILES,
                   min_group_n: int = BAND_MIN_GROUP_N, widen: float = 1.0,
                   cluster_z: float = BAND_CLUSTER_Z, season_col: str = "target_season",
                   min_cluster_seasons: int = BAND_MIN_CLUSTER_SEASONS) -> RatioBand:
    """Fit the ratio band from a leakage-safe panel of `[position, band_group, point, realized]`.

    ⚠️ The panel must be the PRESEASON universe LEFT-JOINED to realized outcomes (0 where the
    entity never played), never an inner join behind a games filter. That population — a cut
    kicker's zero, a defense's collapse — is precisely the tail the band exists to price, and
    excluding it is how the veteran band went five stories covering 0.55 of its nominal 0.80
    (NF1.9).

    Two steps, in order:
      1. the pooled ROW quantiles of `realized / projected` per band group (`raw_groups`);
      2. each bound shifted OUTWARD by `cluster_z ×` the ACROSS-SEASON SD of that bound
         (`BAND_CLUSTER_Z`, pre-registered) — the parameter-uncertainty widening. Step 1 alone
         implicitly claims to know next season's quantile exactly; step 2 prices the fact that it
         does not. The shift is outward-only, so it can never sharpen a bound.
    """
    if panel is None or panel.empty:
        raise ValueError("fit_ratio_band: empty panel — refusing to fit (a band nobody could fit "
                         "must RAISE, not return a vacuous pass)")
    d = panel.copy()
    d["_pt"] = _num(d["point"])
    d["_y"] = _num(d["realized"])
    d = d[np.isfinite(d["_pt"]) & (d["_pt"] > 1e-6) & np.isfinite(d["_y"])]
    if d.empty:
        raise ValueError("fit_ratio_band: no usable rows (every projected point was 0/NaN)")
    d["_ratio"] = d["_y"] / d["_pt"]
    z = max(0.0, float(cluster_z))
    pooled = {}
    for pos, g in d.groupby("position"):
        lo = float(np.quantile(g["_ratio"], quantiles[0]))
        hi = float(np.quantile(g["_ratio"], quantiles[1]))
        sd_lo, sd_hi, _ = _cluster_sd_of_quantile(g, quantiles, season_col, min_cluster_seasons)
        pooled[str(pos)] = (lo - z * sd_lo, hi + z * sd_hi)
    groups, raw, sds, n_by, fell = {}, {}, {}, {}, []
    for grp, g in d.groupby("band_group"):
        key = str(grp)
        n_by[key] = int(len(g))
        if len(g) < min_group_n:
            fell.append(key)
            continue
        lo = float(np.quantile(g["_ratio"], quantiles[0]))
        hi = float(np.quantile(g["_ratio"], quantiles[1]))
        sd_lo, sd_hi, n_seasons = _cluster_sd_of_quantile(g, quantiles, season_col,
                                                          min_cluster_seasons)
        raw[key] = (lo, hi)
        sds[key] = (sd_lo, sd_hi, n_seasons)
        groups[key] = (lo - z * sd_lo, hi + z * sd_hi)
    return RatioBand(groups=groups, pooled=pooled, n_by_group=n_by, fell_back=tuple(fell),
                     quantiles=quantiles, widen=widen, cluster_z=z, raw_groups=raw, cluster_sd=sds)


def apply_band(point, groups, band: RatioBand) -> tuple[np.ndarray, np.ndarray]:
    """`(p10, p90)` for each row — EMITTED INDEPENDENTLY, never reconstructed from a single sd.

    Coherence is enforced here, not asserted downstream: the bounds are clipped to `[0, ∞)` (both
    targets floor at 0) and then to contain their own point estimate, so `lo ≤ point ≤ hi` always
    holds — the NF1.7 invariant the league rescore relies on."""
    pt = _num(point)
    r_lo, r_hi = band.ratios_for(groups)
    lo = np.clip(pt * r_lo, 0.0, None)
    hi = np.clip(pt * r_hi, 0.0, None)
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    lo = np.minimum(lo, np.clip(pt, 0.0, None))
    hi = np.maximum(hi, np.clip(pt, 0.0, None))
    return lo, hi


def band_report(lo, hi, y, position=None) -> dict:
    """Coverage + width + interval score, POOLED OVER ROWS and per position.

    ⚠️ Coverage is a FLOOR here, never a target to tune toward (E2.1-r). Both these targets are
    heavily skewed with a point mass at 0, which is exactly the shape that makes a coverage TARGET
    structurally inverted (NF1.9 (e)): hitting 0.80 exactly on a zero-atom population can require
    deliberately under-covering the right tail. So the number is REPORTED against a floor and the
    interval score is reported beside it."""
    lo, hi, y = (np.asarray(v, dtype=float) for v in (lo, hi, y))
    inside = (y >= lo) & (y <= hi)
    isc = interval_score(lo, hi, y)
    out = {"n": int(len(y)), "coverage_80": round(float(np.mean(inside)), 4),
           "below_p10": round(float(np.mean(y < lo)), 4),
           "above_p90": round(float(np.mean(y > hi)), 4),
           "mean_width": round(float(np.mean(hi - lo)), 2),
           "median_width": round(float(np.median(hi - lo)), 2),
           "interval_score": round(float(np.mean(isc)), 3),
           "nominal": NOMINAL_COVERAGE}
    if position is not None:
        pos = pd.Series(position).astype(str).to_numpy()
        for p in sorted(set(pos)):
            m = pos == p
            out[f"cov_{p}"] = round(float(np.mean(inside[m])), 4)
            out[f"n_{p}"] = int(m.sum())
            out[f"width_{p}"] = round(float(np.mean((hi - lo)[m])), 1)
            out[f"is_{p}"] = round(float(np.mean(isc[m])), 2)
    return out


def degenerate_anchors(point, y) -> dict:
    """The two-sided degenerate anchors, REPORTED so the shipped band is demonstrably not one.

    There is no selection here to invert, but a band that a degenerate beats on its own reported
    score would be a band nobody should ship. `zero_width` is maximally sharp and pays the full miss
    penalty; `max_width` covers ~everything and pays its own width. Both MUST score worse than the
    shipped band (NF1.8 / NF-D11: report a floor AND a ceiling every run)."""
    pt, yy = _num(point), _num(y)
    zero = interval_score(pt, pt, yy)
    hi = float(np.nanmax(yy)) if np.isfinite(yy).any() else 0.0
    mx = interval_score(np.zeros_like(yy), np.full_like(yy, hi), yy)
    return {
        "zero_width": {"interval_score": round(float(np.mean(zero)), 3), "coverage_80": 0.0,
                       "note": "maximally SHARP degenerate — must lose"},
        "max_width": {"interval_score": round(float(np.mean(mx)), 3),
                      "coverage_80": round(float(np.mean((yy >= 0) & (yy <= hi))), 4),
                      "mean_width": round(hi, 1),
                      "note": "maximally WIDE degenerate — satisfies any coverage floor and must "
                              "still lose the interval score"},
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# FACE VALIDITY — the edge-independent gate
# ══════════════════════════════════════════════════════════════════════════════════════════════
FACE_MIN_SPEARMAN = 0.30      # top-projected DSTs must sit on genuinely good defenses
FACE_MIN_K_SPEARMAN = 0.30    # top-projected Ks must sit on genuinely high-scoring offenses


def face_validity(proj: pd.DataFrame, *, min_dst_rho: float = FACE_MIN_SPEARMAN,
                  min_k_rho: float = FACE_MIN_K_SPEARMAN) -> dict:
    """Do the top projected DSTs sit on good defenses, and the top Ks on high-scoring offenses?

    The story's own face-validity question, made mechanical. It is a check on the DIRECTION of the
    projection against the thing it claims to be reading — the honest gate for a product whose
    claim is relative TIERING, not precision. Advisory (this is a projection product), but a trip
    is logged loudly.
    """
    out: dict = {"pass": True, "checks": []}

    def _add(name, ok, detail):
        out["checks"].append({"check": name, "pass": bool(ok), **detail})
        if not ok:
            out["pass"] = False

    dst = proj[proj["position"] == "DST"].copy()
    if len(dst) >= 10:
        # a better defense = FEWER projected points allowed, so the correlation must be NEGATIVE
        rho = float(pd.Series(_num(dst["proj_fp_std"])).corr(
            pd.Series(_num(dst["proj_dst_pa_per_game"])), method="spearman"))
        _add("dst_points_ranks_track_points_allowed", np.isfinite(rho) and rho <= -min_dst_rho,
             {"spearman": round(rho, 3), "requires": f"<= {-min_dst_rho}",
              "note": "a top-ranked DST must be projected to ALLOW FEWER points"})
    k = proj[proj["position"] == "K"].copy()
    ks = k[_boolmask(k["is_primary"], len(k))] if "is_primary" in k.columns else k
    if len(ks) >= 10:
        rho = float(pd.Series(_num(ks["proj_fp_std"])).corr(
            pd.Series(_num(ks["team_points_est_pg"])), method="spearman"))
        _add("k_points_track_team_scoring_env", np.isfinite(rho) and rho >= min_k_rho,
             {"spearman": round(rho, 3), "requires": f">= {min_k_rho}",
              "note": "a top-ranked starting K must sit on a higher-scoring offense"})
    # no starter may be out-projected by his own team's backup
    if len(k) and "is_primary" in k.columns and "team" in k.columns:
        bad = []
        k = k.assign(_prim=_boolmask(k["is_primary"], len(k)))
        for t, g in k.groupby("team"):
            prim = g[g["_prim"]]
            back = g[~g["_prim"]]
            if len(prim) and len(back) and float(back["proj_fp_std"].max()) > float(prim["proj_fp_std"].max()):
                bad.append(str(t))
        _add("primary_kicker_outprojects_his_backup", not bad, {"violations": bad})
    # every emitted interval must contain its own point (the NF1.7 coherence invariant)
    if {"fp_p10", "fp_p90", "proj_fp_std"} <= set(proj.columns):
        lo, hi, pt = _num(proj["fp_p10"]), _num(proj["fp_p90"]), _num(proj["proj_fp_std"])
        n_bad = int(np.sum(~((lo <= pt + 1e-6) & (pt <= hi + 1e-6))))
        _add("interval_contains_its_point", n_bad == 0, {"violations": n_bad})
    # the points-allowed bucket mass must be a distribution over the projected games
    if set(PA_BUCKET_COLS) <= set(proj.columns) and len(dst):
        tot = sum(_num(dst[c]) for c in PA_BUCKET_COLS)
        gap = np.abs(tot - _num(dst["proj_games"]))
        _add("pa_bucket_mass_sums_to_games", float(np.nanmax(gap)) < 1e-6,
             {"max_abs_gap": round(float(np.nanmax(gap)), 9)})
    return out
