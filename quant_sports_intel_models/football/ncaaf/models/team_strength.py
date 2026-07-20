"""team_strength.py — NCAAF-P1.2: the conference/team-strength mixed-effects estimator.

WHAT THIS IS
------------
A hierarchical partial-pooling model of team strength, **team nested in conference**, refit
at every point-in-time as-of week. It answers, for a given (season, team, as_of_week):

    "Before week W kicked off, how many points better than an average FBS team was this
     team on a neutral field — and how sure are we?"

WHY (the operator's framing, roadmap P1.2)
------------------------------------------
College football has huge talent disparity and an almost non-overlapping cross-conference
schedule: ~136 FBS teams play ~12 games each, mostly inside their own league. Raw records
and raw efficiency are therefore not comparable across conferences — they mostly measure
strength of schedule. Partial pooling is the right tool for exactly this shape: a team with
a thin or lopsided sample is shrunk toward its CONFERENCE mean rather than trusted at face
value, and the amount of shrinkage is learned from the data instead of asserted.

⚠️ HONEST FRAMING. This is a strength PRIOR, not an edge claim. It produces a feature (and
its uncertainty) for P1.3 and gets ablation-tested in P1.4. Nothing here has been shown to
beat a market price, and no such claim is made. `best_alpha = 0` still holds.

THE MODEL
---------
Margin model, one row per completed FBS-vs-FBS game, response = home margin:

    margin = alpha * is_home_field  +  (theta_home - theta_away)  +  e
    theta_t = mu_{conf(t)}  +  Z_t . beta  +  u_t
    mu_c ~ N(0, tau_conf^2)      u_t ~ N(0, tau_team^2)      e ~ N(0, sigma^2 / w)

`theta_t` is the emitted strength: points better than an average FBS team, neutral field.
It is the sum of three interpretable pieces, each emitted separately:
  * `mu_conf`  — how strong this team's CONFERENCE is (the pooling level)
  * `Z_t.beta` — what the PRE-SEASON covariates say (talent, roster continuity, portal
                 flux, coaching change, last season's finish). This is the prior mean the
                 team is shrunk toward, and it is why a gutted or portal-loaded roster
                 moves the estimate before a single snap is played.
  * `u_t`      — what THIS SEASON's games say on top of that.

A second, structurally identical model on the team-game grain decomposes scoring into
offense and defense (`points_for = base + hfa + O_team - D_opponent + e`), because P1.4
targets total points as well as margin and a single margin number cannot serve a total.

🚨 SIGN CONVENTION — the one thing a consumer WILL get wrong. Both emitted numbers read
"higher is better": `strength_offense` is points generated above an average offense, and
`strength_defense` is points PREVENTED relative to an average defense. Therefore a team's
net strength is their SUM, not their difference:

    margin(t vs o) = (O_t - D_o) - (O_o - D_t) = (O_t + D_t) - (O_o + D_o)

`strength_offense - strength_defense` is the natural-looking mistake and it silently
returns a number near zero for every team (a good team is good at both, so the two large
positive components cancel). Use `strength_margin` for margin, `O + D` if you need to
rebuild it from the components, and `O_home - D_away + O_away - D_home + 2*base` for a
projected total. A regression test pins this.

LEAKAGE CONTRACT — the whole thing in four lines
------------------------------------------------
1. A row for `as_of_week = W` is fit on games with `season_order_week < W`. Strictly less
   than, and on `season_order_week`, NEVER raw `week` — CFBD restarts `week` at 1 for the
   postseason, which is the live leak P1.1 caught (2024 Ohio State had five games at
   `week <= 1`). `assert_team_strength_is_point_in_time` re-checks this DATE-wise, not
   week-wise, because a week-based test re-uses the broken ordering and passes green.
2. Hyperparameters (the covariate coefficients `beta`, the home-field advantage, and the
   variance components) are estimated on STRICTLY PRIOR SEASONS and then held fixed while
   each week of the target season is solved. Season S never sees season S.
3. Every covariate in `Z` is known pre-season (returning production, the portal class, the
   247 talent composite, the head coach and his prior-season record) or is this model's own
   FINAL estimate from the PREVIOUS season.
4. 2014 is the history floor and is NOT emitted. It is the seed: it exists only to give
   2015 a `prior_strength` covariate and to bootstrap the first hyperparameter fit. Every
   emitted row (2015+) therefore has out-of-sample hyperparameters.

NULLS
-----
NULL means unknown and stays NULL on the way IN: a missing covariate is not coalesced to 0.
It is centered-to-the-season-mean with an explicit `_missing` indicator that carries its own
coefficient, so "we don't know this team's talent composite" is a distinct statement from
"this team is exactly average." The emitted strength itself is never NULL — a team with
zero games is a legitimate posterior (the preseason prior) with an honestly large `sd`.
That is what partial pooling is FOR, and it is why this model, unlike a rollup, does not
need a NULL week-1 row.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
Not a bake-off. Per guide §0.5 this is a STRUCTURAL estimator — a state/strength model in
the same family as MLB's sequential-posterior and Kalman state models — whose OUTPUT is a
candidate feature. The bake-off discipline applies to P1.4, which decides whether this
feature earns its place against direct-learned foils.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .hierarchical import Block, DesignSpec, Posterior, fit

log = logging.getLogger(__name__)

MODEL_VERSION = "ncaaf_team_strength_v1"

# The history floor (ncaaf_data_inventory.md): the lake starts at 2014, so 2014 has no
# season-prior and no prior season to learn hyperparameters from. It seeds, it is not
# emitted. See the leakage contract, point 4.
SEED_SEASON = 2014


# ── the PRE-REGISTERED covariate set (guide §0.5 feature-selection discipline) ──────────
# Hypothesis-driven and bounded — NOT an open subset search. Each entry is (column in the
# joined season-covariate frame, group). The group tags let the report attribute how much
# of a team's prior mean comes from roster/NIL flux vs coaching vs talent vs carryover,
# which is what the P1.2 acceptance criterion asks to be demonstrated.
COVARIATE_GROUPS: dict[str, str] = {
    "prior_strength": "carryover",
    "team_talent": "talent",
    "returning_ppa_pct": "roster_flux",
    "roster_continuity_pct": "roster_flux",
    "portal_net_stars": "roster_flux",
    "hc_change_from_prev": "coaching",
    "is_first_year_at_school": "coaching",
    "hc_recent_sp_overall": "coaching",
}
COVARIATES: tuple[str, ...] = tuple(COVARIATE_GROUPS)


@dataclass
class StrengthConfig:
    """Tunables. Defaults are the pre-registered configuration."""

    # Recency weighting WITHIN a season. A September game still counts in December, just
    # less. Half-life in days, measured from that season's own last game — never from a
    # global max (see _recency_weights for what that bug did to calibration).
    half_life_days: float = 75.0
    # Weight applied per SEASON of distance in the multi-season hyperparameter fit. Last
    # year is worth less than this year (rosters turn over) but is not worthless — at 0.75,
    # four seasons back still contributes ~0.32. Kept separate from half_life_days because
    # it expresses a different belief: roster turnover, not in-season form drift.
    season_decay: float = 0.75
    # How many strictly-prior seasons the hyperparameter fit pools. More is more stable but
    # slower and mixes in older regimes (the portal era is genuinely different from 2014).
    hyper_lookback_seasons: int = 4
    # A team needs this many games in the window before `has_sufficient_sample` is true.
    # Mirrors rollup_ncaaf_team_week_asof's threshold so the two surfaces agree.
    sufficient_sample_games: int = 3
    # Optimizer inits (points^2). Margins have sd ~17, team strengths ~10.
    init_sigma2: float = 289.0
    init_tau2: float = 100.0
    # Fit the offense/defense decomposition too. Off by default only in smoke tests.
    fit_points_model: bool = True


# ══════════════════════════════════════════════════════════════════════════════════════
# Covariate preparation
# ══════════════════════════════════════════════════════════════════════════════════════


def prepare_covariates(
    roster: pd.DataFrame,
    coaching: pd.DataFrame,
    team_seasons: pd.DataFrame,
) -> pd.DataFrame:
    """Join the P0.4/P0.5 season marts onto the team-season spine and clean them honestly.

    `roster` = ncaaf_team_roster_continuity, `coaching` = ncaaf_team_coaching_change (both
    grain (season, team) — team NAME, they carry no team_id), `team_seasons` = the
    (season, team_id, team, conference) spine from the team-game fact.

    Returns the spine plus one raw column per pre-registered covariate. Values that the
    source marks as UNKNOWN are NaN here, deliberately:
      * `portal_net_stars` is NaN before 2021 — the mart coalesces the portal counts to 0,
        but `portal_data_covered = false` says that 0 means "no data", not "no churn".
        Reading it as 0 would tell the model every pre-2021 roster was perfectly stable.
      * `hc_change_from_prev` is NULL at the 2014 floor (no prior year to compare to).
      * `team_talent` is NULL for 2014 (CFBD talent starts 2015) and a few expansion teams.
      * `roster_continuity_pct` is NULL with no prior-year roster.
    `prior_strength` is added later by the recursive season loop.
    """
    out = team_seasons[["season", "team_id", "team", "conference"]].copy()

    r = roster.copy()
    if "portal_data_covered" in r.columns:
        r["portal_net_stars"] = np.where(
            r["portal_data_covered"].astype(bool), r["portal_net_stars"].astype(float), np.nan
        )
    r_cols = ["season", "team", "returning_ppa_pct", "roster_continuity_pct", "portal_net_stars", "team_talent"]
    out = out.merge(r[[c for c in r_cols if c in r.columns]], on=["season", "team"], how="left")

    c = coaching.copy()
    for b in ("hc_change_from_prev", "is_first_year_at_school"):
        if b in c.columns:
            # Preserve NULL: a bool column with NULLs must not become False on cast.
            c[b] = c[b].map({True: 1.0, False: 0.0}).astype(float)
    c_cols = ["season", "team", "hc_change_from_prev", "is_first_year_at_school", "hc_recent_sp_overall"]
    out = out.merge(c[[c_ for c_ in c_cols if c_ in c.columns]], on=["season", "team"], how="left")

    for col in COVARIATES:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def standardize_covariates(cov: pd.DataFrame) -> pd.DataFrame:
    """Center+scale each covariate WITHIN SEASON and emit an explicit missingness flag.

    Within-season standardization is the point-in-time-safe choice: every input is a
    pre-season quantity for its own season, so the season's own mean/sd are known before
    week 1 and no future season leaks into the scaling. It also absorbs league-wide drift
    (talent-composite inflation, portal volume growing every year) that would otherwise be
    read as teams getting stronger.

    A missing value becomes 0 (= this season's average) AND sets `<col>_missing` to 1. The
    indicator carries its own coefficient, so the model can learn that "unknown talent" is
    itself informative (it usually means a new or reclassified program) instead of being
    forced to pretend the team is average.
    """
    out = cov.copy().reset_index(drop=True)
    grouped = out.groupby("season")
    for col in COVARIATES:
        vals = out[col].astype(float)
        mu = grouped[col].transform("mean")
        sd = grouped[col].transform(lambda s: s.std(ddof=0))
        sd = sd.where(np.isfinite(sd) & (sd > 0), 1.0)
        z = (vals - mu) / sd
        missing = ~np.isfinite(z)
        out[f"{col}_z"] = np.where(missing, 0.0, z)
        out[f"{col}_missing"] = missing.astype(float)
    return out


# A covariate column must be supported by at least this many team-seasons in the
# hyperparameter window before it earns a coefficient. NOT arbitrary: a `_missing` indicator
# true for one or two expansion teams is technically non-degenerate, so a pure variance
# check keeps it, but its coefficient is then estimated from those two rows alone — nearly
# unidentified, with a posterior variance close to the prior's. Every team carrying that
# indicator then inherits that variance as its OWN uncertainty. That was live: 2021 New
# Mexico State reported strength_margin_sd = 913 points off a barely-supported indicator.
_MIN_COVARIATE_SUPPORT = 10


def _design_covariate_columns(cov: pd.DataFrame) -> list[str]:
    """The covariate design columns, dropping any that this frame cannot actually identify.

    Two ways a column is dropped, both honest — the model simply has no coefficient for that
    covariate in that fit rather than a meaningless one:
      * NO VARIATION — e.g. `prior_strength_missing` when EVERY team lacks a prior season
        (true for the 2015 hyperparameter fit, which pools only 2014). Rank-deficient.
      * TOO LITTLE SUPPORT — fewer than _MIN_COVARIATE_SUPPORT team-seasons carry a
        non-baseline value. See the constant above for why a variance check alone is not
        enough.
    """
    cols: list[str] = []
    for base in COVARIATES:
        for col in (f"{base}_z", f"{base}_missing"):
            v = cov[col].to_numpy(dtype=float)
            if np.nanstd(v) <= 1e-9:
                continue
            # support = rows that are not at the column's baseline (0 for both the centred
            # z-score and the indicator)
            if int(np.count_nonzero(np.abs(v) > 1e-9)) < _MIN_COVARIATE_SUPPORT:
                continue
            cols.append(col)
    return cols


# ══════════════════════════════════════════════════════════════════════════════════════
# Design construction
# ══════════════════════════════════════════════════════════════════════════════════════


def _key(season: int, value) -> str:
    """Team/conference effects are keyed per SEASON.

    A 2019 Texas and a 2024 Texas are different teams (different roster, different coach,
    and after realignment a different conference). Keying the random effects by season is
    what makes the cross-season link run through the `prior_strength` covariate — an
    explicit, estimable, shrinkable carryover — instead of through an implicit assumption
    that a team is the same entity forever.
    """
    return f"{season}|{value}"


def _recency_weights(
    seasons: pd.Series, dates: pd.Series, config: "StrengthConfig"
) -> np.ndarray:
    """Recency weight per game: decay WITHIN a season, then a flat discount PER season back.

    🚨 THE DECAY MUST BE WITHIN-SEASON. Computing days-back against the global maximum date
    looks equivalent and is not: the hyperparameter fit pools several seasons, so a game two
    years old would get 0.5^(730/75) ~ 0.001 and the "4-season" fit would be running on the
    last few weeks of the newest season. That was live, and it was not a subtle miss — it
    drove `residual_sigma` down to ~5 points when real game-margin noise is ~17, which in
    turn made every emitted `strength_margin_sd` roughly 2x too confident (80% intervals
    covering 48%). Symptoms of a weighting bug show up as a CALIBRATION failure, not as an
    error, which is why the report measures interval coverage at all.

    So: within a season, decay by `half_life_days` from that SEASON's last game. Across
    seasons, apply `season_decay` once per season of distance — an explicit, readable
    statement that last year is worth less than this year, rather than an accident of
    calendar arithmetic. Both are separately tunable because they express different beliefs
    (form drifts within a year; rosters turn over between years).
    """
    if len(dates) == 0:
        return np.zeros(0)
    d = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    s = pd.Series(seasons).reset_index(drop=True).astype(int)

    season_max = d.groupby(s).transform("max")
    days_back = (season_max - d).dt.total_seconds().to_numpy() / 86400.0
    within = np.power(0.5, days_back / max(config.half_life_days, 1e-6))

    seasons_back = (s.max() - s).to_numpy()
    across = np.power(max(config.season_decay, 1e-6), seasons_back)
    return within * across


@dataclass
class MarginDesign:
    X: np.ndarray
    y: np.ndarray
    w: np.ndarray
    spec: DesignSpec
    team_keys: list[str]
    conf_keys: list[str]
    cov_cols: list[str]


def build_margin_design(
    games: pd.DataFrame,
    cov: pd.DataFrame,
    cov_cols: list[str],
    config: StrengthConfig,
    *,
    team_keys: list[str] | None = None,
    conf_keys: list[str] | None = None,
    include_fixed: bool = True,
) -> MarginDesign:
    """One row per completed game; response = home margin.

    `games` must carry: season, season_order_week, game_date, home_team_id, away_team_id,
    home_conference, away_conference, is_neutral_site, home_margin.

    `include_fixed=False` drops the home-field + covariate block — that is the second
    stage, where those coefficients are already known from prior seasons and enter as a
    fixed offset instead of as free parameters.
    """
    cov_ix = cov.set_index(["season", "team_id"])

    home_key = [_key(s, t) for s, t in zip(games["season"], games["home_team_id"])]
    away_key = [_key(s, t) for s, t in zip(games["season"], games["away_team_id"])]
    hconf_key = [_key(s, c) for s, c in zip(games["season"], games["home_conference"])]
    aconf_key = [_key(s, c) for s, c in zip(games["season"], games["away_conference"])]

    if team_keys is None:
        team_keys = sorted(set(home_key) | set(away_key))
    if conf_keys is None:
        conf_keys = sorted(set(hconf_key) | set(aconf_key))
    team_pos = {k: i for i, k in enumerate(team_keys)}
    conf_pos = {k: i for i, k in enumerate(conf_keys)}

    n = len(games)
    parts: list[np.ndarray] = []
    blocks: list[Block] = []

    if include_fixed:
        hfa = np.where(games["is_neutral_site"].astype(bool), 0.0, 1.0).reshape(-1, 1)
        zh = _lookup_covariates(cov_ix, games["season"], games["home_team_id"], cov_cols)
        za = _lookup_covariates(cov_ix, games["season"], games["away_team_id"], cov_cols)
        parts.append(np.hstack([hfa, zh - za]))
        blocks.append(Block("fixed", ("home_field",) + tuple(cov_cols), penalized=False))

    Xc = np.zeros((n, len(conf_keys)))
    for r, (hk, ak) in enumerate(zip(hconf_key, aconf_key)):
        if hk in conf_pos:
            Xc[r, conf_pos[hk]] += 1.0
        if ak in conf_pos:
            Xc[r, conf_pos[ak]] -= 1.0
    parts.append(Xc)
    blocks.append(Block("conference", tuple(conf_keys)))

    Xt = np.zeros((n, len(team_keys)))
    for r, (hk, ak) in enumerate(zip(home_key, away_key)):
        if hk in team_pos:
            Xt[r, team_pos[hk]] += 1.0
        if ak in team_pos:
            Xt[r, team_pos[ak]] -= 1.0
    parts.append(Xt)
    blocks.append(Block("team", tuple(team_keys)))

    X = np.hstack(parts) if parts else np.zeros((n, 0))
    y = games["home_margin"].to_numpy(dtype=float)
    w = _recency_weights(games["season"], games["game_date"], config) if n else np.zeros(0)
    return MarginDesign(X, y, w, DesignSpec(tuple(blocks)), team_keys, conf_keys, cov_cols)


def _lookup_covariates(cov_ix: pd.DataFrame, seasons, team_ids, cols: list[str]) -> np.ndarray:
    if not cols:
        return np.zeros((len(seasons), 0))
    idx = pd.MultiIndex.from_arrays([list(seasons), list(team_ids)])
    got = cov_ix.reindex(idx)[cols]
    # A team-season absent from the covariate spine is unknown, not average-with-certainty;
    # its `_missing` indicators are already 1 wherever the spine had it, and a truly absent
    # row falls back to the season mean (0) which is the same statement.
    return got.to_numpy(dtype=float, na_value=0.0)


@dataclass
class PointsDesign:
    X: np.ndarray
    y: np.ndarray
    w: np.ndarray
    spec: DesignSpec
    team_keys: list[str]
    conf_keys: list[str]
    cov_cols: list[str]


def build_points_design(
    team_games: pd.DataFrame,
    cov: pd.DataFrame,
    cov_cols: list[str],
    config: StrengthConfig,
    *,
    team_keys: list[str] | None = None,
    conf_keys: list[str] | None = None,
    include_fixed: bool = True,
) -> PointsDesign:
    """Two rows per game (one per side); response = that side's points scored.

        points_for = base + hfa/2 * side + O_team - D_opponent + e

    Signs are chosen so BOTH emitted numbers read "higher is better": `O` is points
    generated above an average offense, `D` is points PREVENTED relative to an average
    defense (hence the -1 loading on the opponent's defensive effect).

    ⚠️ Known simplification: the two rows of a game share the game's conditions (weather,
    pace, officiating) so their residuals are correlated, and this model treats them as
    independent. That inflates the effective sample size and therefore makes the offense
    and defense standard deviations mildly optimistic. The MARGIN model has no such issue
    (one row per game) — prefer its `strength_margin_sd` when a single honest uncertainty
    is needed. Recorded as a limitation rather than silently absorbed.
    """
    cov_ix = cov.set_index(["season", "team_id"])

    t_key = [_key(s, t) for s, t in zip(team_games["season"], team_games["team_id"])]
    o_key = [_key(s, t) for s, t in zip(team_games["season"], team_games["opponent_team_id"])]
    tc_key = [_key(s, c) for s, c in zip(team_games["season"], team_games["conference"])]
    oc_key = [_key(s, c) for s, c in zip(team_games["season"], team_games["opponent_conference"])]

    if team_keys is None:
        team_keys = sorted(set(t_key) | set(o_key))
    if conf_keys is None:
        conf_keys = sorted(set(tc_key) | set(oc_key))
    team_pos = {k: i for i, k in enumerate(team_keys)}
    conf_pos = {k: i for i, k in enumerate(conf_keys)}

    n = len(team_games)
    parts: list[np.ndarray] = []
    blocks: list[Block] = []

    if include_fixed:
        neutral = team_games["is_neutral_site"].astype(bool).to_numpy()
        home = team_games["is_home"].astype(bool).to_numpy()
        hfa = np.where(neutral, 0.0, np.where(home, 0.5, -0.5)).reshape(-1, 1)
        zt = _lookup_covariates(cov_ix, team_games["season"], team_games["team_id"], cov_cols)
        zo = _lookup_covariates(cov_ix, team_games["season"], team_games["opponent_team_id"], cov_cols)
        parts.append(np.hstack([np.ones((n, 1)), hfa, zt, -zo]))
        blocks.append(
            Block(
                "fixed",
                ("base", "home_field")
                + tuple(f"off__{c}" for c in cov_cols)
                + tuple(f"def__{c}" for c in cov_cols),
                penalized=False,
            )
        )

    for block_name, keys, pos, key_list, sign in (
        ("conf_off", conf_keys, conf_pos, tc_key, 1.0),
        ("conf_def", conf_keys, conf_pos, oc_key, -1.0),
        ("team_off", team_keys, team_pos, t_key, 1.0),
        ("team_def", team_keys, team_pos, o_key, -1.0),
    ):
        M = np.zeros((n, len(keys)))
        for r, k in enumerate(key_list):
            if k in pos:
                M[r, pos[k]] += sign
        parts.append(M)
        blocks.append(Block(block_name, tuple(keys)))

    X = np.hstack(parts) if parts else np.zeros((n, 0))
    y = team_games["points_for"].to_numpy(dtype=float)
    w = _recency_weights(team_games["season"], team_games["game_date"], config) if n else np.zeros(0)
    return PointsDesign(X, y, w, DesignSpec(tuple(blocks)), team_keys, conf_keys, cov_cols)


# ══════════════════════════════════════════════════════════════════════════════════════
# The two-stage fit
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Hyperparameters:
    """What stage A learns from STRICTLY PRIOR seasons and stage B then holds fixed."""

    sigma2: float
    variances: dict[str, float]
    fixed_coef: dict[str, float]
    fixed_cov: np.ndarray
    cov_cols: list[str]
    n_obs: int
    seasons_used: list[int]
    converged: bool
    in_sample: bool = False  # true ONLY for the un-emitted 2014 seed fit
    # Warnings raised by the solver (a variance component pinned to a bound, a failed
    # optimizer). These are propagated all the way to the run notes and the report —
    # a degenerate fit that nobody is told about is the whole INC-class this repo keeps
    # relearning, and "tau_team hit its lower bound" means the team level of a
    # team-strength model is dead.
    notes: list[str] = field(default_factory=list)

    def coef_vector(self, cols: list[str]) -> np.ndarray:
        return np.array([self.fixed_coef.get(c, 0.0) for c in cols])


def fit_hyperparameters(
    games: pd.DataFrame,
    team_games: pd.DataFrame,
    cov: pd.DataFrame,
    seasons: list[int],
    config: StrengthConfig,
    *,
    kind: str = "margin",
    in_sample: bool = False,
) -> Hyperparameters:
    """Stage A — pool `seasons` (all weeks, complete seasons) to learn beta, HFA, taus.

    These seasons are strictly earlier than the target season, so every one of them was
    complete before the target season kicked off. Nothing here can see the future.
    """
    frame = games if kind == "margin" else team_games
    sub = frame[frame["season"].isin(seasons)].copy()
    cov_sub = cov[cov["season"].isin(seasons)].copy()
    cov_cols = _design_covariate_columns(cov_sub) if len(cov_sub) else []

    builder = build_margin_design if kind == "margin" else build_points_design
    design = builder(sub, cov, cov_cols, config)
    post = fit(
        design.X,
        design.y,
        design.spec,
        weights=design.w,
        init_sigma2=config.init_sigma2,
        init_tau2=config.init_tau2,
    )
    fixed_slice = design.spec.slice_of("fixed")
    fixed_cols = list(design.spec.blocks[0].columns)
    return Hyperparameters(
        sigma2=post.sigma2,
        variances=dict(post.variances),
        fixed_coef={c: float(v) for c, v in zip(fixed_cols, post.mean[fixed_slice])},
        fixed_cov=post.cov[fixed_slice, fixed_slice],
        cov_cols=cov_cols,
        n_obs=post.n_obs,
        seasons_used=sorted(seasons),
        converged=post.converged,
        in_sample=in_sample,
        notes=list(post.notes),
    )


def _stage_b(
    design,
    hyper: Hyperparameters,
    offset_cols: list[str],
) -> Posterior:
    """Stage B — solve the random effects with the stage-A coefficients as a fixed offset."""
    beta = hyper.coef_vector(offset_cols)
    offset = design.X[:, : len(offset_cols)] @ beta if len(offset_cols) else np.zeros(len(design.y))
    y_adj = design.y - offset
    # Re-slice off the fixed block: stage B's design is the random-effect columns only.
    X_rand = design.X[:, len(offset_cols) :]
    spec_rand = DesignSpec(tuple(b for b in design.spec.blocks if b.name != "fixed"))
    return fit(
        X_rand,
        y_adj,
        spec_rand,
        weights=design.w if len(design.w) else None,
        fixed_variances=hyper.variances,
        fixed_sigma2=hyper.sigma2,
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# The season / week driver
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class StrengthRun:
    """Everything a run produces: the week grain, and the diagnostics the report needs."""

    weekly: pd.DataFrame
    hyperparameters: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_strength(
    games: pd.DataFrame,
    team_games: pd.DataFrame,
    roster: pd.DataFrame,
    coaching: pd.DataFrame,
    config: StrengthConfig | None = None,
    *,
    seasons: list[int] | None = None,
) -> StrengthRun:
    """Fit every (season, as-of week) posterior and return the week-grained frame.

    Seasons are processed in ASCENDING order because each season's `prior_strength`
    covariate is the previous season's FINAL estimate from this same model — a recursion
    that only runs forward in time.
    """
    config = config or StrengthConfig()
    all_seasons = sorted(int(s) for s in games["season"].dropna().unique())
    if seasons is not None:
        wanted = set(int(s) for s in seasons)
        # The seed and any season needed for a lookback still have to RUN; they are simply
        # not emitted. Running 2019 alone without its predecessors would silently produce a
        # covariate-free, prior-strength-free estimate that looks fine and is not.
        #
        # ⚠️ This is one level deep, deliberately: the lookback seasons are fit, but THEIR
        # predecessors are not, so the OLDEST lookback season has no prior_strength
        # covariate and a subset run therefore differs slightly from a full run. That is
        # acceptable for a smoke run and NOT acceptable as production output — the full run
        # (no `seasons` argument) is the production path. Chasing the recursion all the way
        # back would just re-run everything, which is what the full path already does.
        need = set()
        for s in wanted:
            need.add(s)
            need.update(x for x in all_seasons if s - config.hyper_lookback_seasons <= x < s)
        need.add(min(all_seasons))
        run_seasons = sorted(s for s in all_seasons if s in need)
    else:
        wanted = set(s for s in all_seasons if s > SEED_SEASON)
        run_seasons = all_seasons

    team_seasons = (
        team_games[["season", "team_id", "team", "conference"]].drop_duplicates().reset_index(drop=True)
    )
    base_cov = prepare_covariates(roster, coaching, team_seasons)
    base_cov["prior_strength"] = np.nan

    rows: list[pd.DataFrame] = []
    hyper_log: list[dict] = []
    notes: list[str] = []
    prior_strength: dict[tuple[int, object], float] = {}  # (season, team_id) -> final strength

    for season in run_seasons:
        cov = base_cov.copy()
        cov["prior_strength"] = [
            prior_strength.get((int(s) - 1, t), np.nan)
            for s, t in zip(cov["season"], cov["team_id"])
        ]
        cov = standardize_covariates(cov)

        prior_seasons = [s for s in all_seasons if season - config.hyper_lookback_seasons <= s < season]
        if prior_seasons:
            hyper_seasons, in_sample = prior_seasons, False
        else:
            # The 2014 seed only. Its hyperparameters ARE in-sample, which is exactly why
            # 2014 is never emitted — it exists to hand 2015 a prior_strength column.
            hyper_seasons, in_sample = [season], True
            notes.append(
                f"season {season}: no prior season available; hyperparameters fit in-sample "
                f"(seed season, NOT emitted)"
            )

        hyper_margin = fit_hyperparameters(
            games, team_games, cov, hyper_seasons, config, kind="margin", in_sample=in_sample
        )
        hyper_points = (
            fit_hyperparameters(
                games, team_games, cov, hyper_seasons, config, kind="points", in_sample=in_sample
            )
            if config.fit_points_model
            else None
        )
        for label, h in (("margin", hyper_margin), ("points", hyper_points)):
            if h is None:
                continue
            for n in h.notes:
                notes.append(f"season {season} [{label}]: {n}")
            hyper_log.append(
                {
                    "season": season,
                    "model": label,
                    "seasons_used": ",".join(str(s) for s in h.seasons_used),
                    "in_sample": h.in_sample,
                    "n_obs": h.n_obs,
                    "sigma": math.sqrt(h.sigma2),
                    "home_field": h.fixed_coef.get("home_field", float("nan")),
                    "converged": h.converged,
                    **{f"tau_{k}": math.sqrt(v) for k, v in h.variances.items()},
                    **{f"beta_{k}": v for k, v in h.fixed_coef.items() if k != "home_field"},
                },
            )

        season_games = games[games["season"] == season]
        season_tg = team_games[team_games["season"] == season]
        season_teams = team_seasons[team_seasons["season"] == season].reset_index(drop=True)

        # The as-of spine — identical to rollup_ncaaf_team_week_asof's: every distinct
        # season_order_week in the season, so a team on bye still gets a row.
        weeks = sorted(int(w) for w in season_games["season_order_week"].dropna().unique())
        terminal_week = (max(weeks) + 1) if weeks else 1

        emitted = season in wanted
        for as_of_week in weeks + [terminal_week]:
            res = _fit_week(
                season=season,
                as_of_week=as_of_week,
                season_games=season_games,
                season_tg=season_tg,
                cov=cov,
                season_teams=season_teams,
                hyper_margin=hyper_margin,
                hyper_points=hyper_points,
                config=config,
            )
            if as_of_week == terminal_week:
                # The post-season-final estimate is the carryover into next season. It is
                # NOT emitted as a week row (there is no week after the last one to be
                # pregame for); it only feeds `prior_strength`.
                for tid, val in zip(res["team_id"], res["strength_margin"]):
                    prior_strength[(season, tid)] = float(val)
            elif emitted:
                rows.append(res)

    weekly = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=["season", "team_id", "as_of_week"])
    )
    return StrengthRun(weekly=weekly, hyperparameters=hyper_log, notes=notes)


def _fit_week(
    *,
    season: int,
    as_of_week: int,
    season_games: pd.DataFrame,
    season_tg: pd.DataFrame,
    cov: pd.DataFrame,
    season_teams: pd.DataFrame,
    hyper_margin: Hyperparameters,
    hyper_points: Hyperparameters | None,
    config: StrengthConfig,
) -> pd.DataFrame:
    """One point-in-time posterior. THE leakage line is the `< as_of_week` filter below."""
    window = season_games[season_games["season_order_week"] < as_of_week]
    window_tg = season_tg[season_tg["season_order_week"] < as_of_week]

    team_keys = [_key(season, t) for t in season_teams["team_id"]]
    conf_keys = sorted({_key(season, c) for c in season_teams["conference"]})

    md = build_margin_design(
        window, cov, hyper_margin.cov_cols, config, team_keys=team_keys, conf_keys=conf_keys
    )
    post_m = _stage_b(md, hyper_margin, ["home_field"] + hyper_margin.cov_cols)

    Z = _lookup_covariates(
        cov.set_index(["season", "team_id"]),
        [season] * len(season_teams),
        season_teams["team_id"],
        hyper_margin.cov_cols,
    )
    beta_cov = hyper_margin.coef_vector(hyper_margin.cov_cols)
    beta_cov_cov = (
        hyper_margin.fixed_cov[1:, 1:] if hyper_margin.fixed_cov.shape[0] > 1 else np.zeros((0, 0))
    )

    n_teams = len(season_teams)
    strength = np.zeros(n_teams)
    strength_sd = np.zeros(n_teams)
    conf_comp = np.zeros(n_teams)
    cov_comp = np.zeros(n_teams)
    team_comp = np.zeros(n_teams)
    # "unknown" is its own group ON PURPOSE. A `<cov>_missing` indicator's contribution is
    # what the model pays for NOT KNOWING a covariate — it is not evidence about the team's
    # roster, talent or coaching. Folding it into those groups makes the attribution lie:
    # the first version of this did exactly that, and the resulting "biggest roster/portal
    # movers" list was topped by first-year FBS transition programs (Sam Houston,
    # Jacksonville State, Kennesaw State) whose covariates are simply ABSENT — they showed
    # identical contributions to two decimal places, which is the tell. Keeping the
    # missingness contribution separate is what makes covariate_component_roster_flux mean
    # what its name says.
    group_comp = {g: np.zeros(n_teams) for g in set(COVARIATE_GROUPS.values()) | {"unknown"}}

    spec_b = post_m.spec
    for i, (tid, conf) in enumerate(zip(season_teams["team_id"], season_teams["conference"])):
        wv = np.zeros(spec_b.n_params)
        ck, tk = _key(season, conf), _key(season, tid)
        if ck in spec_b.columns:
            wv[spec_b.index_of(ck)] = 1.0
        if tk in spec_b.columns:
            wv[spec_b.index_of(tk)] = 1.0
        rand_mean, rand_sd = post_m.linear_combination(wv)
        zi = Z[i]
        cov_mean = float(zi @ beta_cov)
        # Honest total uncertainty: stage-B randomness PLUS the stage-A uncertainty in the
        # covariate coefficients. The two are independent — stage A saw only prior seasons.
        cov_var = float(zi @ beta_cov_cov @ zi) if beta_cov_cov.size else 0.0

        conf_comp[i] = float(wv[spec_b.index_of(ck)] * post_m.mean[spec_b.index_of(ck)]) if ck in spec_b.columns else 0.0
        team_comp[i] = float(post_m.mean[spec_b.index_of(tk)]) if tk in spec_b.columns else 0.0
        cov_comp[i] = cov_mean
        strength[i] = rand_mean + cov_mean
        strength_sd[i] = math.sqrt(max(rand_sd ** 2 + cov_var, 0.0))
        for j, col in enumerate(hyper_margin.cov_cols):
            if col.endswith("_missing"):
                group = "unknown"
            else:
                group = COVARIATE_GROUPS.get(col[:-2], "other")
            group_comp[group][i] += float(zi[j] * beta_cov[j])

    games_played = (
        window_tg.groupby("team_id").size().reindex(season_teams["team_id"]).fillna(0).to_numpy()
    )

    out = pd.DataFrame(
        {
            "sport": "ncaaf",
            "season": season,
            "team_id": season_teams["team_id"].to_numpy(),
            "team": season_teams["team"].to_numpy(),
            "conference": season_teams["conference"].to_numpy(),
            "as_of_week": as_of_week,
            "games_in_window": games_played.astype("int64"),
            "has_sufficient_sample": games_played >= config.sufficient_sample_games,
            "strength_margin": strength,
            "strength_margin_sd": strength_sd,
            "strength_conference_component": conf_comp,
            "strength_covariate_component": cov_comp,
            "strength_team_component": team_comp,
            "home_field_advantage": hyper_margin.fixed_coef.get("home_field", np.nan),
            "residual_sigma": math.sqrt(hyper_margin.sigma2),
            "tau_team": math.sqrt(hyper_margin.variances.get("team", np.nan)),
            "tau_conference": math.sqrt(hyper_margin.variances.get("conference", np.nan)),
            "hyper_seasons": ",".join(str(s) for s in hyper_margin.seasons_used),
            "hyper_n_prior_seasons": len(hyper_margin.seasons_used),
            "hyper_n_games": hyper_margin.n_obs,
            "hyper_in_sample": hyper_margin.in_sample,
            "model_version": MODEL_VERSION,
        }
    )
    for group, vals in group_comp.items():
        out[f"covariate_component_{group}"] = vals

    if hyper_points is not None:
        pd_design = build_points_design(
            window_tg, cov, hyper_points.cov_cols, config, team_keys=team_keys, conf_keys=conf_keys
        )
        offset_cols = (
            ["base", "home_field"]
            + [f"off__{c}" for c in hyper_points.cov_cols]
            + [f"def__{c}" for c in hyper_points.cov_cols]
        )
        post_p = _stage_b(pd_design, hyper_points, offset_cols)
        Zp = _lookup_covariates(
            cov.set_index(["season", "team_id"]),
            [season] * len(season_teams),
            season_teams["team_id"],
            hyper_points.cov_cols,
        )
        beta_off = np.array([hyper_points.fixed_coef.get(f"off__{c}", 0.0) for c in hyper_points.cov_cols])
        beta_def = np.array([hyper_points.fixed_coef.get(f"def__{c}", 0.0) for c in hyper_points.cov_cols])
        spec_p = post_p.spec
        off, off_sd, dfn, dfn_sd = (np.zeros(n_teams) for _ in range(4))
        for i, (tid, conf) in enumerate(zip(season_teams["team_id"], season_teams["conference"])):
            ck, tk = _key(season, conf), _key(season, tid)
            for which, arr, arr_sd, beta in (
                ("off", off, off_sd, beta_off),
                ("def", dfn, dfn_sd, beta_def),
            ):
                wv = np.zeros(spec_p.n_params)
                cslice, tslice = spec_p.slice_of(f"conf_{which}"), spec_p.slice_of(f"team_{which}")
                cnames = list(spec_p.blocks[[b.name for b in spec_p.blocks].index(f"conf_{which}")].columns)
                tnames = list(spec_p.blocks[[b.name for b in spec_p.blocks].index(f"team_{which}")].columns)
                if ck in cnames:
                    wv[cslice.start + cnames.index(ck)] = 1.0
                if tk in tnames:
                    wv[tslice.start + tnames.index(tk)] = 1.0
                m, s = post_p.linear_combination(wv)
                arr[i] = m + float(Zp[i] @ beta)
                arr_sd[i] = s
        out["strength_offense"] = off
        out["strength_offense_sd"] = off_sd
        out["strength_defense"] = dfn
        out["strength_defense_sd"] = dfn_sd
        out["league_base_points"] = hyper_points.fixed_coef.get("base", np.nan)
    else:
        for c in (
            "strength_offense",
            "strength_offense_sd",
            "strength_defense",
            "strength_defense_sd",
            "league_base_points",
        ):
            out[c] = np.nan

    return out
