"""nf1_2_model.py — NF1.2 pure model logic: the PROJECTION-REFINEMENT candidate families
(strength-of-schedule / system-pass-rate / correlation-aware / O-line-via-cap / opportunity-
stability / spillover / contract) folded into NF1.1's per-position machinery, MARKET-BLIND.

NF1.2 pre-registers the "what NF1 doesn't yet account for" set (operator 2026-07-27) as candidate
FEATURE FAMILIES on top of the NF1.1 per-position harness, and ablates each for held-out lift on
the TOP-TIER metric under the full deflation kit. The harness is NF1.1's VERBATIM (the NF1.3
pattern): same three learner classes (`PosRidge` / `PosGBM` / `PosSimilarity`) vs the MVP-1
`PosNull` foil, same incumbent-anchored + oracle-checked `top_tier_rho`, same CSCV-PBO /
config-spread / deflated-Sharpe / BH-FDR deflation. The ONLY additions are the new feature
families and their attach builders.

⚖️ MARKET-BLIND (the story's frame): no ADP/ECR anywhere. NF1.3's market-aware dual-board moved
the QB/RB bar; a market-blind feature add's honest win condition is therefore WR/TE + the fade
universe. NF1.2 gates against the market-BLIND baseline (MVP-1, the fade-claim board).
`best_alpha = 0` — projection product, no edge claim.

── THE PRE-REGISTERED FAMILIES (hypothesis-driven adds — §0.5 feature-selection discipline) ──────

  H-SOS `sos`          — SEASON-AGGREGATE strength-of-schedule from NF-D6's forward defense
                         strength (`pass_def_strength`/`rush_def_strength`, higher = stronger D):
                         the mean opponent strength over the projection season's actual schedule.
                         ⚠️ the season AGGREGATE, not the per-GAME DVP NF1 already nulled. Churn/
                         returning-share are NOT aggregated in (NF-D6 nulled churn as a forward
                         lever; a schedule-mean of opponent churn has no pre-registered hypothesis).
  H-SYSTEM `system`    — scheme/volume context of the FORWARD team: the projection team's
                         base-season pass rate + pace, and the pass-rate DELTA a mover experiences
                         (destination − origin). Extends NF-D2 slice 3 with the pass-rate
                         dimension slice 4 didn't capture. (Forward OC changes were unobservable
                         when NF1.2 ran; the destination team's realized base-season rate was the
                         proxy. NF-D10 lifted that limit — see H-COACH below.)
  H-COACH `coach`      — ⭐ NF-D10 (2026-07-31): the COACHING-REGIME half of H-SYSTEM, i.e. the
                         part the base-season pass rate is definitionally blind to. A team's
                         base-season rate is the OLD coordinator's rate; when the OC changes, the
                         regime a projection should lean on is the NEW one's. Columns:
                         `new_oc` / `oc_tenure_years` / `new_hc` / `coach_continuity` (the
                         scheme-continuity candidate: 1 both retained, 0.5 one, 0 neither) and
                         `oc_prior_pass_rate_delta` — the SCHEME-SHOCK MAGNITUDE, the new OC's last
                         team's realized pass rate MINUS this team's base-season pass rate (0.0 for
                         a retained OC by construction; NaN for a first-time/internally-promoted
                         OC). Source: `coaching_source` (HC from nflverse schedules' per-game
                         coach columns, OC from Wikipedia team-season staff), leakage-safe as-of
                         March 15 of the projection season, so a MID-SEASON firing can never reach
                         its own season's pre-season feature.
  H-CORR `qbcorr`      — QB↔pass-catcher structural coupling: the projection team's best QB
                         projection (`mvp1_fp` max over that team's QBs) as a feature on WR/TE
                         rows — a phenomenal QB lifts his pass-catchers' environment.
  H-OLINE `oline`      — O-line quality via NF-D8's team O-line CAP share (`team_ol_cap_pct`) —
                         the concretely-realized H-OLINE proxy (QB pockets / RB lanes). ⛔ NOT a
                         second O-line family beside the contract cap — this IS the contract
                         O-line cap, registered once.
  H-CONTRACT `contract`— NF-D8 player financial features: `log_investment` (log(apy)×guaranteed_
                         ratio), `guaranteed_ratio`, `cap_hit_pct_team`, + the team skill-cap
                         Herfindahl (`team_skill_cap_concentration`). Market-ADJACENT but not
                         consensus (team $ ≠ ADP/ECR) → market-blind-safe.
  H-OPP `opp`          — opportunity-stability anchors: base-season `air_yards_share` + `wopr`
                         (weighted opportunity rating, 1.5·target_share + 0.7·air_yards_share —
                         both straight from our weekly marts). Target share itself is ALREADY in
                         the NF1 usage group, so the NEW columns are the untried air-yards axes.
                         ⚠️ PROBED 2026-07-27: routes-run and catchable-target flags are in NO
                         nflverse table we ingest (PFF-gated) → YPRR + catchable-rate are honestly
                         UNAVAILABLE and not registered.
  H-SPILL `spill`      — teammate/environment: `teammate_fp` (sum of the OTHER skill-position
                         teammates' MVP-1 projection on the projection team — the "teammate fppg"
                         scan cite) + `vacated_volume` (the target+carry share leaving the team:
                         departed players' base-season usage — season-long injury/departure
                         volume-redistribution). Overlaps H-CORR by design — deflation sorts them.

  (NF-D7 xFP features stay in the candidate sets for QB/RB/TE ONLY — NF1.1 settled they carry
  learned signal there and are a NULL at WR, so the WR base set drops them here.)

Every function here is PURE (DataFrames in/out, NO IO) so the fast gate covers the whole feature
construction offline; the DuckDB/S3/cache reads, walk-forward orchestration, Optuna, and the
report live in `run_nf1_2.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Reuse NF1.1's pure kit VERBATIM — the metric, the deflation harness, the learners.
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11
from quant_sports_intel_models.football.nfl.fantasy.nf1_1_model import (  # re-export for consumers/tests
    FDR_Q,
    PBO_MAX,
    DSR_MIN,
    POSITIONS,
    TOP_N,
    XFP_FEATURES,
    bh_fdr,
    combined_ordering_score,
    config_spread,
    cscv_pbo,
    deflated_sharpe,
    make_pos_learner,
    onesided_paired_pvalue,
    oracle_top_tier_is_ceiling,
    position_verdict,
    safe_spearman,
    top_tier_rho,
)

MODEL_VERSION = "nfl_fantasy_nf1_2_v1"

# ── Team-code normalisation (the crosswalk landmine): nflverse play-by-play/defense tables key
#    the Rams as 'LA' while our marts/schedules use 'LAR'; legacy relocations map to the current
#    franchise code so a base-2019 OAK row joins its LV successor. Applied to EVERY team key that
#    crosses a source boundary.
_TEAM_NORM = {"LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV"}


def norm_team(team) -> str | float:
    """Normalise one team code (NaN-safe, PURE)."""
    if team is None or (isinstance(team, float) and np.isnan(team)):
        return np.nan
    t = str(team).strip().upper()
    return _TEAM_NORM.get(t, t)


def norm_team_col(s: pd.Series) -> pd.Series:
    return s.map(norm_team)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered families + per-position applicability (hypothesis-driven, NOT open search)
# ══════════════════════════════════════════════════════════════════════════════════════════════
REFINEMENT_FAMILIES: dict[str, tuple[str, ...]] = {
    "sos": ("sos_pass_strength", "sos_rush_strength"),
    "system": ("team_pass_rate", "team_pace", "pass_rate_delta"),
    "qbcorr": ("team_qb_quality",),
    "oline": ("team_ol_cap_pct",),
    "contract": ("log_investment", "guaranteed_ratio", "cap_hit_pct_team",
                 "team_skill_cap_concentration"),
    "opp": ("air_yards_share", "wopr"),
    "spill": ("teammate_fp", "vacated_volume"),
    "coach": ("new_oc", "oc_tenure_years", "new_hc", "coach_continuity",
              "oc_prior_pass_rate_delta"),
}

# Which families apply to which position (the pre-registration): a QB is never targeted (no opp,
# no qbcorr — he IS the QB); O-line cap is the pocket/lanes hypothesis (QB/RB); rush-SOS matters
# where carries do (QB scrambles/RB), pass-SOS everywhere a route is run.
FAMILY_POSITIONS: dict[str, tuple[str, ...]] = {
    "sos": ("QB", "RB", "WR", "TE"),
    "system": ("QB", "RB", "WR", "TE"),
    "qbcorr": ("WR", "TE"),
    "oline": ("QB", "RB"),
    "contract": ("QB", "RB", "WR", "TE"),
    "opp": ("RB", "WR", "TE"),
    "spill": ("QB", "RB", "WR", "TE"),
    # a coordinator change redistributes targets, carries, pace and pass rate — every skill spot
    # is exposed, so H-COACH is registered league-wide rather than hand-narrowed to one position.
    "coach": ("QB", "RB", "WR", "TE"),
}

# WR/TE never carry meaningfully → their SOS leg is pass-only (the rush column would be noise).
_SOS_COLS_BY_POS = {
    "QB": ("sos_pass_strength", "sos_rush_strength"),
    "RB": ("sos_pass_strength", "sos_rush_strength"),
    "WR": ("sos_pass_strength",),
    "TE": ("sos_pass_strength",),
}


def _family_cols(family: str, pos: str) -> tuple[str, ...]:
    """The family's columns as applied to `pos` (empty when the family doesn't apply)."""
    if pos not in FAMILY_POSITIONS.get(family, ()):
        return ()
    if family == "sos":
        return _SOS_COLS_BY_POS[pos]
    return REFINEMENT_FAMILIES[family]


# The NF1.1 BASE per-position sets, with the WR xFP columns dropped (NF1.1's settled verdict:
# xFP carries learned signal at QB/RB/TE and is a NULL at WR — not re-litigated).
BASE_POSITION_FEATURES: dict[str, tuple[str, ...]] = {
    pos: (tuple(f for f in feats if f not in XFP_FEATURES) if pos == "WR" else feats)
    for pos, feats in M11.POSITION_FEATURES.items()
}

# The FULL extended per-position sets = base + every applicable family.
POSITION_FEATURES: dict[str, tuple[str, ...]] = {
    pos: base + tuple(c for fam in REFINEMENT_FAMILIES for c in _family_cols(fam, pos))
    for pos, base in BASE_POSITION_FEATURES.items()
}

# Drop-one ablation groups = NF1.1's legacy groups + the seven new families.
FEATURE_GROUPS = {**M11.FEATURE_GROUPS,
                  **{fam: cols for fam, cols in REFINEMENT_FAMILIES.items()}}

# All new columns (for cache/attach bookkeeping).
REFINEMENT_COLS: tuple[str, ...] = tuple(
    c for cols in REFINEMENT_FAMILIES.values() for c in cols)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure attach builders — each LEFT-joins one family onto the feature frame. A missing/empty input
# leaves the columns NaN (the learners median-impute; the MVP-1 null ignores them).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ensure_cols(frame: pd.DataFrame, cols: tuple[str, ...]) -> pd.DataFrame:
    out = frame.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    return out


def schedule_sos(schedule: pd.DataFrame, defense: pd.DataFrame) -> pd.DataFrame:
    """H-SOS: per (season, team) mean opponent defense strength over the season's schedule.

    `schedule`: one row per game — [season, home_team, away_team] (regular season only).
    `defense` : one row per (projection_season, team) — [projection_season, team,
                pass_def_strength, rush_def_strength] (NF-D6 forward strengths; higher=stronger).
    Returns [season, team, sos_pass_strength, sos_rush_strength] — HIGHER = a HARDER slate.
    Team codes are normalised on both sides. PURE."""
    if schedule is None or schedule.empty or defense is None or defense.empty:
        return pd.DataFrame(columns=["season", "team", "sos_pass_strength", "sos_rush_strength"])
    sch = schedule.copy()
    sch["home_team"] = norm_team_col(sch["home_team"])
    sch["away_team"] = norm_team_col(sch["away_team"])
    long = pd.concat([
        sch.rename(columns={"home_team": "team", "away_team": "opponent"})[["season", "team", "opponent"]],
        sch.rename(columns={"away_team": "team", "home_team": "opponent"})[["season", "team", "opponent"]],
    ], ignore_index=True)
    d = defense.copy()
    d["team"] = norm_team_col(d["team"])
    d = d.rename(columns={"projection_season": "season"}) if "projection_season" in d.columns else d
    m = long.merge(d[["season", "team", "pass_def_strength", "rush_def_strength"]]
                   .rename(columns={"team": "opponent"}),
                   on=["season", "opponent"], how="left")
    out = (m.groupby(["season", "team"], as_index=False)
             .agg(sos_pass_strength=("pass_def_strength", "mean"),
                  sos_rush_strength=("rush_def_strength", "mean")))
    return out


def attach_sos(frame: pd.DataFrame, sos: pd.DataFrame) -> pd.DataFrame:
    """Merge the schedule-SOS onto the frame by (projection_season, proj_team)."""
    frame = _ensure_cols(frame, REFINEMENT_FAMILIES["sos"])
    if sos is None or sos.empty or "proj_team" not in frame.columns:
        return frame
    out = frame.drop(columns=list(REFINEMENT_FAMILIES["sos"]))
    out["_team"] = norm_team_col(out["proj_team"])
    m = out.merge(sos.rename(columns={"season": "projection_season", "team": "_team"}),
                  on=["projection_season", "_team"], how="left")
    return m.drop(columns=["_team"])


def attach_system(frame: pd.DataFrame, team_rates: pd.DataFrame) -> pd.DataFrame:
    """H-SYSTEM: the projection team's BASE-season pass rate + pace, and the mover's pass-rate
    delta (destination − origin; 0 for a stayer by construction).

    `team_rates`: [season, team, off_pass_rate, off_plays_per_game] (realized team-season). The
    join is leakage-safe — both legs read the BASE season's realized rates."""
    cols = REFINEMENT_FAMILIES["system"]
    frame = _ensure_cols(frame, cols)
    if team_rates is None or team_rates.empty or "proj_team" not in frame.columns:
        return frame
    tr = team_rates.copy()
    tr["team"] = norm_team_col(tr["team"])
    out = frame.drop(columns=list(cols))
    out["_pt"] = norm_team_col(out["proj_team"])
    out["_bt"] = norm_team_col(out["base_team"]) if "base_team" in out.columns else out["_pt"]
    dest = tr.rename(columns={"team": "_pt", "season": "base_season",
                              "off_pass_rate": "team_pass_rate", "off_plays_per_game": "team_pace"})
    out = out.merge(dest[["base_season", "_pt", "team_pass_rate", "team_pace"]],
                    on=["base_season", "_pt"], how="left")
    orig = tr.rename(columns={"team": "_bt", "season": "base_season",
                              "off_pass_rate": "_origin_pass_rate"})
    out = out.merge(orig[["base_season", "_bt", "_origin_pass_rate"]],
                    on=["base_season", "_bt"], how="left")
    out["pass_rate_delta"] = out["team_pass_rate"] - out["_origin_pass_rate"]
    return out.drop(columns=["_pt", "_bt", "_origin_pass_rate"])


def attach_qb_quality(frame: pd.DataFrame) -> pd.DataFrame:
    """H-CORR: `team_qb_quality` = the projection team's best QB MVP-1 projection, computed from
    the frame ITSELF (must be the FULL veteran universe, not a survivorship-filtered pool — the
    runner attaches families BEFORE the realized-outcome filter)."""
    cols = REFINEMENT_FAMILIES["qbcorr"]
    frame = _ensure_cols(frame, cols)
    if "proj_team" not in frame.columns or frame.empty:
        return frame
    out = frame.drop(columns=list(cols))
    out["_team"] = norm_team_col(out["proj_team"])
    key = ["projection_season", "_team"] if "projection_season" in out.columns else ["_team"]
    qb = out[out["position"] == "QB"]
    if qb.empty:
        out["team_qb_quality"] = np.nan
        return out.drop(columns=["_team"])
    best = (qb.assign(_fp=pd.to_numeric(qb["mvp1_fp"], errors="coerce"))
              .groupby(key, as_index=False)["_fp"].max()
              .rename(columns={"_fp": "team_qb_quality"}))
    out = out.merge(best, on=key, how="left")
    return out.drop(columns=["_team"])


def attach_spillover(frame: pd.DataFrame) -> pd.DataFrame:
    """H-SPILL, from the frame ITSELF (full veteran universe — see attach_qb_quality):
      * `teammate_fp`     — sum of the OTHER skill players' `mvp1_fp` on the projection team
                            (the offensive-environment / "teammate fppg" feature).
      * `vacated_volume`  — the base-season target+carry share DEPARTING the team: for team T,
                            Σ (target_share + carry_share) over players whose base_team == T but
                            whose projection team is NOT T (moved / unsigned) — the season-long
                            volume-redistribution (floor-elevation) signal."""
    cols = REFINEMENT_FAMILIES["spill"]
    frame = _ensure_cols(frame, cols)
    if frame.empty or "proj_team" not in frame.columns:
        return frame
    out = frame.drop(columns=list(cols))
    out["_pt"] = norm_team_col(out["proj_team"])
    out["_bt"] = norm_team_col(out["base_team"]) if "base_team" in out.columns else np.nan
    key = ["projection_season", "_pt"] if "projection_season" in out.columns else ["_pt"]

    fp = pd.to_numeric(out["mvp1_fp"], errors="coerce").fillna(0.0)
    grp_sum = out.assign(_fp=fp).groupby(key)["_fp"].transform("sum")
    out["teammate_fp"] = (grp_sum - fp).where(out["_pt"].notna())

    leavers = out[(out["_bt"].notna()) & (out["_bt"] != out["_pt"])]
    if leavers.empty:
        out["vacated_volume"] = np.where(out["_pt"].notna(), 0.0, np.nan)
    else:
        vol = (pd.to_numeric(leavers["target_share"], errors="coerce").fillna(0.0)
               + pd.to_numeric(leavers["carry_share"], errors="coerce").fillna(0.0))
        vkey = (["projection_season", "_bt"] if "projection_season" in out.columns else ["_bt"])
        vac = (leavers.assign(_vol=vol).groupby(vkey, as_index=False)["_vol"].sum()
               .rename(columns={"_vol": "vacated_volume",
                                "_bt": "_pt"}))
        out = out.merge(vac, on=key, how="left")
        out["vacated_volume"] = out["vacated_volume"].fillna(0.0).where(out["_pt"].notna())
    return out.drop(columns=["_pt", "_bt"])


def attach_opportunity(frame: pd.DataFrame, opp_shares: pd.DataFrame) -> pd.DataFrame:
    """H-OPP: base-season `air_yards_share` + `wopr` per player (from the weekly marts; the
    runner aggregates played, non-bye weeks). `opp_shares`: [season, player_id, air_yards_share,
    wopr]; joined on (base_season, player_id)."""
    cols = REFINEMENT_FAMILIES["opp"]
    frame = _ensure_cols(frame, cols)
    if opp_shares is None or opp_shares.empty:
        return frame
    out = frame.drop(columns=list(cols))
    o = opp_shares.rename(columns={"season": "base_season"})
    return out.merge(o[["base_season", "player_id", "air_yards_share", "wopr"]],
                     on=["base_season", "player_id"], how="left")


def attach_contract(frame: pd.DataFrame, player_contracts: pd.DataFrame,
                    team_caps: pd.DataFrame) -> pd.DataFrame:
    """H-CONTRACT + H-OLINE: NF-D8 player financial features joined by (projection_season,
    player_id); the TEAM aggregates (`team_ol_cap_pct`, `team_skill_cap_concentration`) joined by
    (projection_season, proj_team) — the FORWARD team, so a mover carries his new team's line/
    room, not his old contract team's."""
    pcols = ("log_investment", "guaranteed_ratio", "cap_hit_pct_team")
    tcols = ("team_ol_cap_pct", "team_skill_cap_concentration")
    frame = _ensure_cols(frame, pcols + tcols)
    out = frame
    if player_contracts is not None and not player_contracts.empty:
        out = out.drop(columns=list(pcols))
        p = player_contracts.rename(columns={"season": "projection_season"})
        out = out.merge(p[["projection_season", "player_id", *pcols]].drop_duplicates(
            subset=["projection_season", "player_id"]),
            on=["projection_season", "player_id"], how="left")
    if team_caps is not None and not team_caps.empty and "proj_team" in out.columns:
        out = out.drop(columns=list(tcols))
        t = team_caps.rename(columns={"season": "projection_season", "team_abbr": "_team"})
        t["_team"] = norm_team_col(t["_team"])
        out["_team"] = norm_team_col(out["proj_team"])
        out = out.merge(t[["projection_season", "_team", *tcols]].drop_duplicates(
            subset=["projection_season", "_team"]),
            on=["projection_season", "_team"], how="left").drop(columns=["_team"])
    return out


def attach_coach(frame: pd.DataFrame, coach: pd.DataFrame,
                 team_rates: pd.DataFrame) -> pd.DataFrame:
    """H-COACH (NF-D10): the FORWARD team's coaching regime, joined by (projection_season,
    proj_team) — a mover carries his NEW team's coordinator, not his old one's.

    `coach`: [season, team, new_oc, oc_tenure_years, new_hc, coach_continuity, oc_prev_team,
              oc_prev_season] from `coaching_source.load_coach_features` (already leakage-safe:
              built from stints known as of March 15 of the projection season).
    `team_rates`: [season, team, off_pass_rate, …] — the same realized team-season frame H-SYSTEM
              uses, needed for the derived scheme-shock column.

    `oc_prior_pass_rate_delta` = (the new OC's LAST team's realized pass rate in his last season
    there) − (this team's BASE-season pass rate). Both legs are historical realized rates, so the
    column is leakage-safe. A RETAINED OC gets exactly 0.0 (no shock, by construction — not a
    missing value); a new OC with no prior coordinator season keeps NaN (an honest unknown, which
    the learners median-impute and the MVP-1 null ignores).

    ⚠️ COVERAGE FLOOR: `rollup_nfl_team_season.off_pass_rate` exists only from 2020, so for
    projection seasons ≤2020 this column DEGENERATES to '0.0 iff the OC was retained, NaN
    otherwise' — the same information `new_oc` already carries, not a measured shock. It becomes a
    genuinely distinct signal only from projection season 2021 onward. Stated so a family lift
    that is really a pre-2021 duplicate of `new_oc` is not mistaken for the scheme-shock
    hypothesis clearing. PURE."""
    cols = REFINEMENT_FAMILIES["coach"]
    frame = _ensure_cols(frame, cols)
    if coach is None or coach.empty or "proj_team" not in frame.columns:
        return frame
    out = frame.drop(columns=list(cols))
    out["_team"] = norm_team_col(out["proj_team"])

    c = coach.copy()
    c["_team"] = norm_team_col(c["team"])
    c = c.rename(columns={"season": "projection_season"})
    keep = ["projection_season", "_team", "new_oc", "oc_tenure_years", "new_hc",
            "coach_continuity", "oc_prev_team", "oc_prev_season"]
    keep = [k for k in keep if k in c.columns]
    out = out.merge(c[keep].drop_duplicates(subset=["projection_season", "_team"]),
                    on=["projection_season", "_team"], how="left")

    out["oc_prior_pass_rate_delta"] = np.nan
    if (team_rates is not None and not team_rates.empty
            and {"oc_prev_team", "oc_prev_season"} <= set(out.columns)):
        tr = team_rates.copy()
        tr["_t"] = norm_team_col(tr["team"])
        rate = {(int(s), t): r for s, t, r in
                zip(pd.to_numeric(tr["season"], errors="coerce").fillna(-1).astype(int), tr["_t"],
                    pd.to_numeric(tr["off_pass_rate"], errors="coerce"))}

        def _rate(season, team):
            if team is None or (isinstance(team, float) and np.isnan(team)):
                return np.nan
            s = pd.to_numeric(season, errors="coerce")
            return rate.get((int(s), norm_team(team)), np.nan) if pd.notna(s) else np.nan

        prior = [_rate(s, t) for s, t in zip(out["oc_prev_season"], out["oc_prev_team"])]
        base = ([_rate(s, t) for s, t in zip(out["base_season"], out["_team"])]
                if "base_season" in out.columns else [np.nan] * len(out))
        new_oc = pd.to_numeric(out["new_oc"], errors="coerce").to_numpy(dtype=float)
        delta = np.asarray(prior, dtype=float) - np.asarray(base, dtype=float)
        out["oc_prior_pass_rate_delta"] = np.where(new_oc == 0.0, 0.0, delta)
    return out.drop(columns=[c for c in ("_team", "oc_prev_team", "oc_prev_season")
                             if c in out.columns])


@dataclass
class RefinementInputs:
    """The pre-loaded input frames the runner assembles ONCE (assemble-once cost hygiene); the
    pure attach pipeline consumes them with no IO. Any empty/None member leaves that family's
    columns NaN."""

    schedule: pd.DataFrame = field(default_factory=pd.DataFrame)        # season, home_team, away_team
    defense: pd.DataFrame = field(default_factory=pd.DataFrame)         # projection_season, team, *_def_strength
    team_rates: pd.DataFrame = field(default_factory=pd.DataFrame)      # season, team, off_pass_rate, off_plays_per_game
    opp_shares: pd.DataFrame = field(default_factory=pd.DataFrame)      # season, player_id, air_yards_share, wopr
    player_contracts: pd.DataFrame = field(default_factory=pd.DataFrame)  # season, player_id, $-features
    team_caps: pd.DataFrame = field(default_factory=pd.DataFrame)       # season, team_abbr, team-cap aggregates
    coach: pd.DataFrame = field(default_factory=pd.DataFrame)           # season, team, NF-D10 regime features


def add_refinement_features(frame: pd.DataFrame, inputs: RefinementInputs) -> pd.DataFrame:
    """Attach every pre-registered family onto a feature frame (PURE — inputs pre-loaded).

    ⚠️ `frame` must be the FULL veteran universe for its base season (BEFORE any realized-outcome
    ≥-games filter): `qbcorr` and `spill` derive team aggregates from the frame itself, and a
    survivorship-filtered frame would drop exactly the departed players whose vacated volume the
    spillover family measures."""
    out = attach_sos(frame, schedule_sos(inputs.schedule, inputs.defense))
    out = attach_system(out, inputs.team_rates)
    out = attach_qb_quality(out)
    out = attach_spillover(out)
    out = attach_opportunity(out, inputs.opp_shares)
    out = attach_contract(out, inputs.player_contracts, inputs.team_caps)
    out = attach_coach(out, inputs.coach, inputs.team_rates)
    return out
