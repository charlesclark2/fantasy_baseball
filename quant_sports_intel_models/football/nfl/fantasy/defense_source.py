"""defense_source.py — NF-D6 FORWARD DEFENSE-STRENGTH PROJECTION (roster-adjusted; the SOS baseline).

Strength-of-schedule for an offensive player = the sum of the DEFENSES he faces, so NF1.2's SOS (and
NFL-betting N1) need a FORWARD, roster-adjusted defense projection — not a stale carry-forward of last
year's defense, which is wrong exactly for the teams that reshaped their D via the draft / FA / trades.
This module projects each team's defensive strength forward, split PASS-D vs RUSH-D (a WR cares about
pass-D, an RB about rush-D), leakage-safe as-of preseason, uncertainty-aware.

THE CONSTRUCT (three leakage-safe layers, all ≤ prior-season on-field data):

  1. OPPONENT-ADJUSTED EFFICIENCY (the 2-pass pattern, done in ONE principled fit) — for each
     (season, unit∈{pass,rush}) fit the canonical partial-pooling Gaussian
         epa_play = intercept + O[posteam] + D[defteam] + e          (O, D random effects)
     via `betting_ml/utils/hierarchical.fit` (the shared solver — NCAAF-P1.2 / E7.3). The DEFENSE
     random-effect posterior mean is the EPA a defense ALLOWS controlling for the OFFENSES it faced
     (the opponent adjustment) AND is empirical-Bayes SHRUNK toward the league mean (few games ⇒ pulled
     to average); its posterior SD is honest measurement uncertainty. `def_strength = −D_effect`
     (lower EPA allowed ⇒ stronger D), z-scored across the 32 teams so HIGHER = STRONGER (a harder
     matchup). Raw (unadjusted) EPA-allowed / success-rate-allowed are kept as the baseline arm + the
     realized walk-forward target.

  2. ROSTER-CHURN (the NF-D1/NF-D2 mover pattern, DEFENSIVE side) — from last season's defensive
     SNAP shares (`snap_counts`, who actually played the D) joined to THIS season's preseason ROSTER
     (`rosters`, who is on the team now, crosswalked on pfr id), the fraction of last year's defensive
     snaps that RETURNS. Split by position group: pass-unit continuity = secondary + edge rushers,
     rush-unit continuity = the front seven. `churn = 1 − returning_share`. Key adds/losses are the
     departed high-snap players and the incoming veterans (snaps elsewhere last year).

  3. THE FORWARD PROJECTION — the prior-season opponent-adjusted z, additionally shrunk toward the mean
     by churn (a heavily-reshaped D reverts further — we are less sure last year's number repeats) and
     with WIDER uncertainty by churn (⭐ the headline: churn is a real forward-surprise signal). The
     churn shrink/widen coefficients are SELECTED on the walk-forward metric + interval calibration
     (`run_forward_defense.py`, the §0.5 bake-off).

DELIVERABLE (the whole point — NF1.2 is blocked without it): `load_forward_defense(season)` → one row
per team with `pass_def_strength` / `rush_def_strength` (+ `_sd` uncertainty + churn / returning-share
diagnostics), read from the landed Delta `nfl/fantasy/defense/forward_defense_strength` (season-
partitioned) if present, else computed on the fly. NF1.2's SOS joins it the SAME way NF1.1 joins the
xFP set. Edge-independent, `best_alpha=0` — a projection, not an edge claim.

Pure helpers (`zscore`, `churn_shrink`, `churn_widen`, `classify_position`) take arrays in and out with
NO IO, so the construct is unit-tested offline against the fast gate; the DuckDB/S3 reads + the mixed-
model fit live in `load_def_plays` / `fit_unit_strength` / `team_strengths` / `load_snap_continuity`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nfl.fantasy.defense")

_ART = Path(__file__).resolve().parent / "artifacts"
_PLAYS_CACHE = _ART / "defense_plays_cache"
_STRENGTH_CACHE = _ART / "defense_strength_cache"

UNITS = ("pass", "rush")

# The raw nflverse S3 Delta relations (same lake NF-D7 / NF-D1 / NF-D2 read). Overridable for a local
# Delta tree in tests.
PBP_RELATION = "delta_scan('s3://credence-sports-lakehouse/nfl/raw/pbp')"
SNAP_RELATION = "delta_scan('s3://credence-sports-lakehouse/nfl/raw/snap_counts')"
ROSTER_RELATION = "delta_scan('s3://credence-sports-lakehouse/nfl/raw/rosters')"

# The landed forward-defense Delta table (the serving deliverable). tier/source → the story's path
# s3://credence-sports-lakehouse/nfl/fantasy/defense/forward_defense_strength/season=YYYY/.
LAKE_SPORT = "nfl"
LAKE_TIER = "fantasy"
LAKE_SOURCE = "defense/forward_defense_strength"

# Position groups for the pass-D vs rush-D churn split (snap_counts `position` vocabulary: LB/CB/DE/DT/
# FS/SS/NT/DB dominate). Pass unit = the coverage + pass-rush players; rush unit = the front seven.
# DE / EDGE / OLB matter for BOTH fronts, so they appear in both groups (this is a weighting, not a
# partition — a snap can count toward both units' continuity).
_PASS_POSITIONS = frozenset({"CB", "FS", "SS", "S", "DB", "NB", "DE", "EDGE", "OLB"})
_RUSH_POSITIONS = frozenset({"DT", "NT", "DL", "NG", "DE", "EDGE", "LB", "ILB", "MLB", "OLB"})

# Snap-count era (snap_counts starts 2013) — a projection season S needs snap_counts for S−1, so the
# earliest churn-adjusted projection is 2014; PBP efficiency goes back further but we scope to the era
# where the roster-churn layer is available.
MIN_SNAP_SEASON = 2013

MIN_PLAYS_PER_UNIT = 2000   # below this a season's fit is untrustworthy (skip)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers (no IO — fast-gate tested)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def zscore(x: np.ndarray) -> np.ndarray:
    """Cross-team z-score (mean 0, sd 1). A degenerate (all-equal) input → zeros, never NaN."""
    a = np.asarray(x, dtype=float)
    sd = a.std()
    if not (sd > 0):
        return np.zeros_like(a)
    return (a - a.mean()) / sd


def churn_shrink(prior_z: np.ndarray, churn: np.ndarray, k: float) -> np.ndarray:
    """Shrink the prior-season strength toward the league mean (0 on the z-scale) by an amount that
    grows with roster churn: `fwd = (1 − k·churn)·prior_z`. `k`∈[0,1] is the churn-shrink coefficient
    (0 = no churn shrink = the pure opponent-adjusted arm; selected on the walk-forward metric). A fully
    reshaped defense (churn→1) at k=1 collapses to the mean; churn is clamped to [0,1]. PURE."""
    c = np.clip(np.asarray(churn, dtype=float), 0.0, 1.0)
    return (1.0 - float(k) * c) * np.asarray(prior_z, dtype=float)


def forward_sd(prior_sd: np.ndarray, churn: np.ndarray, forward_noise: float,
               churn_widen_k: float) -> np.ndarray:
    """The FORWARD projection uncertainty (honest, calibrated): three variance sources in quadrature —
        fwd_sd = sqrt( prior_sd²  +  forward_noise²  +  (churn_widen_k · churn)² )
    (a) `prior_sd` — the measurement uncertainty on last year's opponent-adjusted number (the mixed-
        model posterior sd; small, ~0.3 z-units).
    (b) `forward_noise` — the season-to-season VOLATILITY floor. ⭐ THE HONEST FINDING (NF-D6 walk-
        forward): defensive strength is genuinely volatile year-over-year, so the realized value
        scatters FAR more than the measurement sd implies — the forward interval must be WIDE
        (~1 z-unit) to cover at the nominal rate. This term dominates and is calibrated to ≈0.68 1-sd
        coverage.
    (c) `churn_widen_k · churn` — the churn-SPECIFIC add the operator hypothesised ("bigger churn ⇒
        wider"). The walk-forward found this is ≈NULL for defense (roster churn does NOT predict a
        larger forward surprise — continuity is entangled with having been good, and good units regress
        unpredictably), so the shipped `churn_widen_k` is small/0; the term is kept so a future re-
        selection (or a different sport) can turn it on if it earns coverage. PURE."""
    c = np.clip(np.asarray(churn, dtype=float), 0.0, 1.0)
    return np.sqrt(np.asarray(prior_sd, dtype=float) ** 2 + float(forward_noise) ** 2
                   + (float(churn_widen_k) * c) ** 2)


def classify_position(position: str) -> tuple[bool, bool]:
    """(is_pass_unit, is_rush_unit) for a snap-count defensive position. Unknown positions count toward
    NEITHER group (they still count toward the overall `def` continuity). PURE."""
    p = (position or "").upper().strip()
    return (p in _PASS_POSITIONS, p in _RUSH_POSITIONS)


@dataclass(frozen=True)
class DefenseConfig:
    """One arm of the §0.5 shrinkage/form bake-off. `opp_adjust` off = the raw-EPA-allowed baseline;
    `window` > 1 recency-weights the prior-season strength over the last N seasons; the churn
    coefficients drive layer 3. The SHIPPED config is chosen on the walk-forward metric + calibration."""
    name: str
    opp_adjust: bool = True
    window: int = 1
    recency_decay: float = 0.6
    churn_shrink_k: float = 0.0
    forward_noise: float = 0.0   # season-to-season volatility floor (z-units), calibrated to coverage
    churn_widen_k: float = 0.0
    metric: str = "epa"          # "epa" | "success" — the efficiency the strength is built from


# ══════════════════════════════════════════════════════════════════════════════════════════════
# S3 play-by-play → slim per-(season, unit) play frame (cached per season)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ensure_s3(con) -> None:
    """Make a plain DuckDB connection able to `delta_scan` the S3 lake (idempotent, best-effort — a
    connection that already has the extension/secret, or has no network, just proceeds). Mirrors
    `xfp_source._ensure_s3`."""
    for stmt in ("install delta", "load delta", "install httpfs", "load httpfs",
                 "create secret (type s3, provider credential_chain, region 'us-east-2')"):
        try:
            con.sql(stmt)
        except Exception:  # noqa: BLE001 — already loaded / secret exists / offline
            pass


_PLAYS_SQL = """
select
    season,
    posteam,
    defteam,
    case when pass = 1 then 'pass' else 'rush' end as unit,
    epa,
    cast(success as double) as success,
    coalesce(yards_gained, 0.0) as yards_gained
from {pbp}
where season = {y}
  and season_type = 'REG'
  and (pass = 1 or rush = 1)
  and epa is not null
  and posteam is not null
  and defteam is not null
"""


def load_def_plays(con, seasons: list[int], *, pbp_relation: str = PBP_RELATION,
                   cache_dir: Path = _PLAYS_CACHE, use_cache: bool = True,
                   refresh: bool = False) -> pd.DataFrame:
    """The slim per-play frame (season, posteam, defteam, unit, epa, success, yards_gained) the mixed-
    model fit needs, read from the S3 play-by-play. Cached per season to parquet (the heavy 372-col S3
    read runs ONCE — assemble-once cost hygiene); `refresh` forces a re-read. Only the ~7 columns the
    opponent-adjustment needs are materialized, so a season is a few MB, not the full wide pbp."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames, to_read = [], []
    for y in seasons:
        cache = cache_dir / f"plays_season={y}.parquet"
        if use_cache and not refresh and cache.exists():
            frames.append(pd.read_parquet(cache))
        else:
            to_read.append(y)
    if to_read:
        _ensure_s3(con)
        for y in to_read:
            df = con.sql(_PLAYS_SQL.format(pbp=pbp_relation, y=y)).df()
            df.to_parquet(cache_dir / f"plays_season={y}.parquet", index=False)
            log.info("defense plays cache written: season=%d (%d plays)", y, len(df))
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["season", "posteam", "defteam", "unit", "epa", "success",
                                     "yards_gained"])
    return pd.concat(frames, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The opponent-adjusted mixed-model fit (one (season, unit) → per-team strength + honest sd)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fit_unit_strength(plays: pd.DataFrame, *, metric: str = "epa") -> pd.DataFrame:
    """Opponent-adjusted, EB-shrunk defensive strength for ONE (season, unit) slice of plays.

    Fits `y = intercept + O[posteam] + D[defteam] + e` (O, D partial-pooled random effects) with the
    shared `hierarchical.fit`. Returns one row per DEFENSIVE team with:
      • `def_effect`      — posterior mean EPA (or success prob) ALLOWED above the league baseline,
                            controlling for the offenses faced (positive = allows more = WORSE D)
      • `def_effect_sd`   — posterior SD (honest measurement uncertainty)
      • `strength_z`      — z-score of `−def_effect` across the 32 teams (HIGHER = STRONGER D)
      • `strength_z_sd`   — `def_effect_sd` on the same z-scale (÷ the cross-team sd)
      • `raw_epa_allowed` / `raw_success_allowed` — UNADJUSTED per-play means (the baseline arm + a
                            face-validity anchor), and `plays` (sample size).

    `metric` selects the response (`epa` default, or `success` for success-rate-allowed). A slice with
    too few plays or teams returns an empty frame (the caller skips that season/unit)."""
    from quant_sports_intel_models.football.ncaaf.models.hierarchical import Block, DesignSpec, fit

    if plays is None or len(plays) < MIN_PLAYS_PER_UNIT:
        return pd.DataFrame()
    teams = sorted(set(plays["posteam"]) | set(plays["defteam"]))
    T = len(teams)
    if T < 8:
        return pd.DataFrame()
    idx = {t: i for i, t in enumerate(teams)}
    y = pd.to_numeric(plays[metric], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(y)
    plays = plays.loc[ok].reset_index(drop=True)
    y = y[ok]
    n = len(y)

    X = np.zeros((n, 1 + 2 * T))
    X[:, 0] = 1.0
    r = np.arange(n)
    X[r, 1 + plays["posteam"].map(idx).to_numpy()] = 1.0
    X[r, 1 + T + plays["defteam"].map(idx).to_numpy()] = 1.0
    spec = DesignSpec((
        Block("intercept", ("b0",), penalized=False),
        Block("off", tuple(f"o_{t}" for t in teams)),
        Block("def", tuple(f"d_{t}" for t in teams)),
    ))
    # init tau2 small (team-to-team EPA spread is ~0.1) and sigma2 at the play-EPA variance so the
    # boundary-avoiding optimizer starts near the right scale.
    post = fit(X, y, spec, init_sigma2=max(float(np.var(y)), 1e-3), init_tau2=0.01)
    def_effect = post.block("def")
    def_sd = np.array([post.coef_sd(f"d_{t}") for t in teams])

    # per-team raw (unadjusted) efficiency allowed
    grp = plays.groupby("defteam")
    raw_epa = grp["epa"].mean()
    raw_succ = grp["success"].mean()
    n_plays = grp.size()

    strength_raw = -def_effect               # lower allowed ⇒ stronger
    sd_across = strength_raw.std()
    z = zscore(strength_raw)
    z_sd = def_sd / sd_across if sd_across > 0 else np.zeros_like(def_sd)

    out = pd.DataFrame({
        "team": teams,
        "def_effect": def_effect,
        "def_effect_sd": def_sd,
        "strength_z": z,
        "strength_z_sd": z_sd,
    })
    out["raw_epa_allowed"] = out["team"].map(raw_epa).to_numpy()
    out["raw_success_allowed"] = out["team"].map(raw_succ).to_numpy()
    out["plays"] = out["team"].map(n_plays).fillna(0).astype(int).to_numpy()
    return out


def team_strengths(con, seasons: list[int], *, metric: str = "epa",
                   pbp_relation: str = PBP_RELATION, plays_cache: Path = _PLAYS_CACHE,
                   strength_cache: Path = _STRENGTH_CACHE, use_cache: bool = True,
                   refresh: bool = False) -> pd.DataFrame:
    """Per-(season, unit, team) opponent-adjusted strength for every requested season. The fit is
    deterministic, so the fitted strengths are cached to parquet per (season, metric) — `--validate`
    and repeated `--land` never re-fit. Returns the long frame with the `fit_unit_strength` columns
    plus `season`, `unit`."""
    strength_cache.mkdir(parents=True, exist_ok=True)
    frames, to_fit = [], []
    for y in seasons:
        cache = strength_cache / f"strength_metric={metric}_season={y}.parquet"
        if use_cache and not refresh and cache.exists():
            frames.append(pd.read_parquet(cache))
        else:
            to_fit.append(y)
    if to_fit:
        plays_all = load_def_plays(con, to_fit, pbp_relation=pbp_relation, cache_dir=plays_cache,
                                   use_cache=use_cache, refresh=refresh)
        for y in to_fit:
            rows = []
            for unit in UNITS:
                sl = plays_all[(plays_all["season"] == y) & (plays_all["unit"] == unit)]
                fit_df = fit_unit_strength(sl, metric=metric)
                if fit_df.empty:
                    log.warning("defense fit skipped: season=%d unit=%s (%d plays)", y, unit, len(sl))
                    continue
                fit_df.insert(0, "unit", unit)
                fit_df.insert(0, "season", int(y))
                rows.append(fit_df)
            if rows:
                season_df = pd.concat(rows, ignore_index=True)
                season_df.to_parquet(
                    strength_cache / f"strength_metric={metric}_season={y}.parquet", index=False)
                frames.append(season_df)
                log.info("defense strengths fit + cached: season=%d (%d team-units)", y, len(season_df))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Roster churn — last-season defensive snap shares → this-season roster continuity (per unit)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_SNAP_SQL = """
select player, pfr_player_id, position, team, sum(defense_snaps) as snaps
from {snap}
where season = {prior} and game_type = 'REG' and coalesce(defense_snaps, 0) > 0
  and pfr_player_id is not null
group by 1, 2, 3, 4
"""

_ROSTER_SQL = """
select distinct pfr_id, team
from {roster}
where season = {proj} and pfr_id is not null
"""


def load_snap_continuity(con, proj_season: int, *, snap_relation: str = SNAP_RELATION,
                         roster_relation: str = ROSTER_RELATION) -> pd.DataFrame:
    """Per-team defensive-snap CONTINUITY for projecting `proj_season`, split by unit.

    Joins last season's (`proj_season − 1`) defensive snap shares to THIS season's preseason roster
    (crosswalk on pfr id) — a player is RETURNING iff he is on the same team's `proj_season` roster.
    `returning_share[unit]` = Σ (snaps of returning players in that unit's position group) / Σ (all
    snaps in that group last year); `churn = 1 − returning_share`. Also reports the departed high-snap
    players (`top_losses`) and incoming veterans who had defensive snaps elsewhere last year
    (`incoming_veteran_share` / `top_adds`) for face-validity.

    Leakage-safe: the `proj_season` ROSTER is preseason-known (free agency / draft resolve before Week
    1 — the same NF-D1/NF-D2 posture that reads the projection-season depth chart). Nothing here reads
    a `proj_season` on-field outcome. Returns one row per (team, unit) with the continuity diagnostics;
    an empty frame if the snap/roster seasons are unavailable."""
    prior = proj_season - 1
    _ensure_s3(con)
    snaps = con.sql(_SNAP_SQL.format(snap=snap_relation, prior=prior)).df()
    roster = con.sql(_ROSTER_SQL.format(roster=roster_relation, proj=proj_season)).df()
    if snaps.empty or roster.empty:
        return pd.DataFrame()

    # per-player unit membership (a player can be in both groups — DE/OLB)
    grp = snaps["position"].map(classify_position)
    snaps["is_pass"] = [g[0] for g in grp]
    snaps["is_rush"] = [g[1] for g in grp]

    # where is this player on the projection-season roster? (None ⇒ off the league / not on a roster)
    ros_team = roster.groupby("pfr_id")["team"].first()
    snaps["proj_team"] = snaps["pfr_player_id"].map(ros_team)
    snaps["returning"] = snaps["proj_team"] == snaps["team"]        # same team next year

    out_rows = []
    for team, g in snaps.groupby("team"):
        for unit, flag in (("pass", "is_pass"), ("rush", "is_rush")):
            gu = g[g[flag]]
            tot = float(gu["snaps"].sum())
            ret = float(gu.loc[gu["returning"], "snaps"].sum())
            returning_share = ret / tot if tot > 0 else np.nan
            # incoming veterans: players NOT here last year (other team) who ARE on this team's roster
            # AND played this unit's snaps somewhere in the prior season
            inc = snaps[(snaps[flag]) & (snaps["proj_team"] == team) & (snaps["team"] != team)]
            inc_share = float(inc["snaps"].sum()) / tot if tot > 0 else np.nan
            losses = (gu.loc[~gu["returning"]].nlargest(3, "snaps")["player"].tolist())
            adds = inc.nlargest(3, "snaps")["player"].tolist()
            out_rows.append({
                "team": team, "unit": unit,
                "returning_share": returning_share,
                "churn": (1.0 - returning_share) if returning_share == returning_share else np.nan,
                "incoming_veteran_share": inc_share,
                "prior_snaps": tot,
                "top_losses": ", ".join(losses),
                "top_adds": ", ".join(adds),
            })
    return pd.DataFrame(out_rows)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The forward projection (leakage-safe assembly) + the serving contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
# default SHIP config — set by the NF-D6 bake-off (run_forward_defense.py). Opponent-adjusted single
# prior season; churn POINT-shrink OFF (null on walk-forward ρ) and the churn-specific widen OFF (null
# — churn doesn't predict forward surprise for defense); the honest forward uncertainty is a calibrated
# season-to-season VOLATILITY floor (`forward_noise`, ≈0.68 1-sd coverage). The roster-churn / returning
# shares ship as DIAGNOSTIC columns (a legitimate feature for NF1.2 / a DST projection). Coefficients
# reconciled to the walk-forward report by run_forward_defense --land.
SHIP_CONFIG = DefenseConfig(name="oppadj", opp_adjust=True, window=1, churn_shrink_k=0.0,
                            forward_noise=0.5, churn_widen_k=0.0, metric="epa")


def _prior_strength(strengths: pd.DataFrame, proj_season: int, config: DefenseConfig) -> pd.DataFrame:
    """The leakage-safe prior-season strength for projecting `proj_season` (only seasons ≤ proj−1),
    per (unit, team). For `window`>1 a recency-weighted mean of the last N seasons' z (and its sd via
    weighted quadrature); for the raw arm the z is rebuilt from `raw_epa_allowed` instead of the
    opponent-adjusted effect."""
    zcol = "strength_z" if config.opp_adjust else "raw_z"
    df = strengths.copy()
    if not config.opp_adjust:
        # baseline arm: z-score the RAW efficiency (lower epa/success allowed ⇒ stronger)
        df["raw_z"] = np.nan
        for (s, u), g in df.groupby(["season", "unit"]):
            df.loc[g.index, "raw_z"] = zscore(-g["raw_epa_allowed"].to_numpy())
        df["strength_z_sd"] = 0.0  # raw arm carries no posterior sd

    lo = proj_season - config.window
    win = df[(df["season"] >= lo) & (df["season"] <= proj_season - 1)].copy()
    if win.empty:
        return pd.DataFrame()
    win["_w"] = config.recency_decay ** (proj_season - 1 - win["season"]).to_numpy()

    rows = []
    for (unit, team), g in win.groupby(["unit", "team"]):
        w = g["_w"].to_numpy()
        wsum = w.sum() or 1.0
        z = float((g[zcol].to_numpy() * w).sum() / wsum)
        # sd of the weighted mean (independent-season quadrature; single-season ⇒ that season's sd)
        sd_terms = (w / wsum) ** 2 * g["strength_z_sd"].fillna(0.0).to_numpy() ** 2
        sd = float(np.sqrt(sd_terms.sum()))
        rows.append({"unit": unit, "team": team, "prior_z": z, "prior_z_sd": sd})
    return pd.DataFrame(rows)


def build_forward_defense(con, proj_season: int, *, config: DefenseConfig = SHIP_CONFIG,
                          strengths: pd.DataFrame | None = None,
                          continuity: pd.DataFrame | None = None,
                          pbp_relation: str = PBP_RELATION, snap_relation: str = SNAP_RELATION,
                          roster_relation: str = ROSTER_RELATION,
                          use_cache: bool = True) -> pd.DataFrame:
    """Compute the leakage-safe forward defense-strength projection for `proj_season` — one row per
    team with `pass_def_strength` / `rush_def_strength` (+ `_sd`) and the churn diagnostics. This is the
    compute path behind both the walk-forward eval and the Delta landing. Pre-computed `strengths` /
    `continuity` frames can be passed to avoid re-fitting/re-reading (the eval passes them once)."""
    if strengths is None:
        need = list(range(proj_season - config.window, proj_season))
        strengths = team_strengths(con, need, metric=config.metric, pbp_relation=pbp_relation,
                                   use_cache=use_cache)
    if strengths is None or strengths.empty:
        return pd.DataFrame()
    prior = _prior_strength(strengths, proj_season, config)
    if prior.empty:
        return pd.DataFrame()

    if continuity is None:
        continuity = load_snap_continuity(con, proj_season, snap_relation=snap_relation,
                                          roster_relation=roster_relation)
    cont = continuity if continuity is not None else pd.DataFrame()

    merged = prior.merge(
        cont[["team", "unit", "returning_share", "churn", "incoming_veteran_share",
              "top_losses", "top_adds"]] if not cont.empty else
        pd.DataFrame(columns=["team", "unit", "returning_share", "churn", "incoming_veteran_share",
                              "top_losses", "top_adds"]),
        on=["team", "unit"], how="left")
    # a team/unit with no continuity data ⇒ churn unknown ⇒ treat as 0 (no shrink, no widen) but flag
    merged["churn_known"] = merged["churn"].notna()
    churn = merged["churn"].fillna(0.0).to_numpy()

    merged["fwd_z"] = churn_shrink(merged["prior_z"].to_numpy(), churn, config.churn_shrink_k)
    merged["fwd_sd"] = forward_sd(merged["prior_z_sd"].to_numpy(), churn, config.forward_noise,
                                  config.churn_widen_k)

    # long → wide: one row per team with pass_/rush_ columns
    wide = None
    for unit in UNITS:
        u = merged[merged["unit"] == unit].copy()
        ren = {
            "fwd_z": f"{unit}_def_strength",
            "fwd_sd": f"{unit}_def_strength_sd",
            "prior_z": f"{unit}_prior_strength",
            "returning_share": f"{unit}_returning_share",
            "churn": f"{unit}_churn",
            "incoming_veteran_share": f"{unit}_incoming_veteran_share",
            "top_losses": f"{unit}_top_losses",
            "top_adds": f"{unit}_top_adds",
        }
        u = u[["team", *ren.keys()]].rename(columns=ren)
        wide = u if wide is None else wide.merge(u, on="team", how="outer")
    if wide is None:
        return pd.DataFrame()
    wide.insert(0, "projection_season", int(proj_season))
    wide.insert(1, "config", config.name)
    return wide.sort_values("team").reset_index(drop=True)


def _read_lake(season: int):
    """Read the landed forward-defense Delta for `season` from S3 (the serving fast path). Returns a
    DataFrame or None if the table/partition is absent or the lake is unreachable."""
    import duckdb

    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri(LAKE_SPORT, LAKE_SOURCE, tier=LAKE_TIER)
    con = duckdb.connect()
    try:
        con.execute("install delta; load delta; install httpfs; load httpfs;")
        opts = s3io.storage_options()
        con.execute(f"set s3_region='{opts.get('AWS_REGION', 'us-east-2')}';")
        if opts.get("AWS_ACCESS_KEY_ID"):
            con.execute(f"set s3_access_key_id='{opts['AWS_ACCESS_KEY_ID']}';")
            con.execute(f"set s3_secret_access_key='{opts['AWS_SECRET_ACCESS_KEY']}';")
            if opts.get("AWS_SESSION_TOKEN"):
                con.execute(f"set s3_session_token='{opts['AWS_SESSION_TOKEN']}';")
        df = con.sql(f"select * from delta_scan('{uri}') where projection_season = {int(season)}").df()
        return df if not df.empty else None
    except Exception as exc:  # noqa: BLE001 — table absent / offline ⇒ caller computes
        log.info("forward-defense lake read unavailable (%s) — will compute", str(exc)[:120])
        return None
    finally:
        con.close()


def load_forward_defense(season: int, *, con=None, from_lake: bool = True,
                         config: DefenseConfig = SHIP_CONFIG, **kwargs) -> pd.DataFrame:
    """⭐ THE DELIVERABLE — per-team forward defense strength for `season`, the way NF1.2's SOS (and
    NFL-betting N1) consume it (the SAME join contract as NF1.1 ↔ the xFP set).

    Returns one row per team with `pass_def_strength` / `rush_def_strength` (HIGHER = STRONGER D, a
    harder matchup; z-scaled across the league) + `_sd` uncertainty + the churn / returning-share
    diagnostics. By default reads the landed Delta `nfl/fantasy/defense/forward_defense_strength` for
    `season` (fast serving path); if the table is absent AND a DuckDB `con` is supplied, computes on
    the fly via `build_forward_defense` (the backtest / first-land path). Raises if neither a landed
    partition nor a `con` is available."""
    if from_lake:
        df = _read_lake(season)
        if df is not None:
            return df
    if con is None:
        raise RuntimeError(
            f"forward-defense for season={season} is not in the lake and no DuckDB `con` was given to "
            f"compute it — either land it (run_forward_defense.py --land --s3) or pass con=<duckdb>.")
    return build_forward_defense(con, season, config=config, **kwargs)


# a compact serving projection of the deliverable (the columns NF1.2 SOS actually joins on)
SERVING_COLUMNS = [
    "projection_season", "team",
    "pass_def_strength", "pass_def_strength_sd", "pass_returning_share", "pass_churn",
    "rush_def_strength", "rush_def_strength_sd", "rush_returning_share", "rush_churn",
]
