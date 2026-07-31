"""run_kdst_projection.py — NF1.6 CLI: BASE season projections for KICKER (K) + TEAM DEFENSE (DST).

The honest-completeness build. MVP-1 projects offensive skill only, so the K and DST roster slots
rendered "not projected" in every fantasy surface; this lands a deliberately BASE projection for both
so the slots FILL and the positions are rankable, with honest wide uncertainty and framing that does
not imply confident ranks.

⭐ RUN ON THE LAPTOP (like NF-FASTPATH / NCAAF-P1A). SF-free throughout: the NFL marts DuckDB supplies
the spine/roster/schedule reads and the raw nflverse Delta lake supplies the kicking + team-defense
box lines. Laptop compute + S3 I/O, ZERO shared-box CPU/RAM — it cannot contend with the live MLB
pipeline.

Prereq — the NFL marts must be built into the DuckDB first (dbt-core, NOT dbtf; the delta_scan
staging segfaults fusion). From `quant_sports_intel_models/sports_dbt`:
    export SPORTS_LAKE_REGION=us-east-2
    python -m dbt.cli.main run --select nfl.staging --threads 1
    python -m dbt.cli.main run --select nfl.marts --threads 1

Then (laptop):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_kdst_projection \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --s3

Outputs:
  * <out-dir>/nfl_fantasy_kdst_projections_<year>.parquet      — the raw K/DST component projection
  * <out-dir>/nfl_fantasy_kdst_projections_<year>_ranked.csv   — a readable ranked board
  * <out-dir>/nfl_fantasy_kdst_band_panel.parquet              — the walk-forward band/coverage panel
  * s3://credence-sports-lakehouse/nfl/fantasy/derived/kdst_projections/season=<year>/  (--s3)
  * quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf1_6_kdst_base_projection.md

⚖️ THE GATE (edge-independent — no `best_alpha`/PBO/DSR; that is the betting posture):
  1. FACE VALIDITY — do the top projected DSTs sit on defenses projected to allow fewer points, and
     the top Ks on higher-scoring offenses? Does a starter out-project his own backup? Does every
     interval contain its own point? Does the points-allowed bucket mass sum to the projected games?
  2. COVERAGE — walk-forward, on the PRESEASON universe LEFT-JOINED to realized outcomes (a cut
     kicker's zero included). Reported against a FLOOR, never tuned toward a target.
  3. HOLDOUT RANK CORRELATION — a behavioural "does this have any signal at all" read, reported
     per position and expected to be MODEST. That is the finding, not a failure.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import kdst_projection as KD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_source as KS  # noqa: E402

log = logging.getLogger("nfl.fantasy.kdst")

MARTS_SCHEMA = KS.MARTS_SCHEMA
STAGING_SCHEMA = KS.STAGING_SCHEMA
_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf1_6_kdst_base_projection.md"
)
_PANEL_CACHE = _DEFAULT_OUT / "nfl_fantasy_kdst_band_panel.parquet"

# The first season the walk-forward panel can produce a target for. The kicker universe comes from
# `weekly_rosters`, whose usable week-1 coverage starts in the mid-2000s, and every target needs a
# 3-season prior window behind it.
HISTORY_FIRST_SEASON = 1999
PANEL_FIRST_TARGET = 2006

# The emitted schema — the input contract for NF-C1 / NF-C0b / the board. Deliberately schema-
# COMPATIBLE with MVP-1's `OUTPUT_COLS` on the shared keys so a consumer can `concat` the two
# projections and score them with one profile.
OUTPUT_COLS = [
    "sport", "projection_season", "base_season", "player_id", "player_name", "position",
    "team_id", "source", "is_rookie", "confidence",
    # K/DST-specific provenance the board + the report read
    "is_primary", "is_active", "games_share", "team_points_est_pg", "sos_off_pg", "sos_off_z",
    "band_group",
    *KD.RAW_STAT_COLS,
    "proj_fp_std", "fp_p10", "fp_p90", "fp_sd", "uncertainty_type",
    # ── MVP-1 CONTRACT ALIASES ────────────────────────────────────────────────────────────────
    # The same four values under MVP-1's column names, so a consumer can `pd.concat` the K/DST
    # projection onto the offensive one and score BOTH with a single `SportProfile` — no
    # per-position base-column plumbing, no engine change. `_ppr` is a misnomer for K/DST (there
    # are no receptions), but it is the SHARED CONTRACT SLOT for "the projection's own convenience
    # point total + its 80% bounds", and duplicating into it is what makes the concat drop-in.
    "proj_fp_ppr", "fp_ppr_sd", "fp_ppr_p10", "fp_ppr_p90",
    "model_version", "generated_at",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Loading — one pass over history, reused by every projection season
# ══════════════════════════════════════════════════════════════════════════════════════════════
class Inputs:
    """Every historical frame the model needs, loaded once. Cheap to hold (a few thousand rows)."""

    def __init__(self, con, lo: int, hi: int, *, schema: str = MARTS_SCHEMA,
                 staging: str = STAGING_SCHEMA, refresh: bool = False):
        self.lo, self.hi, self.staging = int(lo), int(hi), staging
        self.team_def = KS.load_team_defense_seasons(con, lo, hi, refresh=refresh)
        self.team_game_points = KS.load_team_game_points(con, lo, hi, staging=staging)
        self.team_points = KS.load_team_points(con, lo, hi, staging=staging)
        self.kickers = KS.load_kicker_seasons(con, lo, hi, refresh=refresh)
        self._implied: dict[int, pd.DataFrame] = {}
        self._sched: dict[int, pd.DataFrame] = {}
        self._universe_k: dict[int, pd.DataFrame] = {}
        self._universe_d: dict[int, pd.DataFrame] = {}
        self._con = con

    def implied(self, season: int) -> pd.DataFrame:
        if season not in self._implied:
            self._implied[season] = KS.load_week1_implied_points(self._con, season,
                                                                 staging=self.staging)
        return self._implied[season]

    def schedule(self, season: int) -> pd.DataFrame:
        if season not in self._sched:
            self._sched[season] = KS.load_schedule_opponents(self._con, season, staging=self.staging)
        return self._sched[season]

    def kicker_universe(self, season: int) -> pd.DataFrame:
        if season not in self._universe_k:
            self._universe_k[season] = KS.load_kicker_universe(self._con, season,
                                                              staging=self.staging)
        return self._universe_k[season]

    def dst_universe(self, season: int) -> pd.DataFrame:
        if season not in self._universe_d:
            self._universe_d[season] = KS.load_dst_universe(self._con, season, staging=self.staging)
        return self._universe_d[season]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The FORWARD team scoring-environment estimate — train/serve consistent by construction
# ══════════════════════════════════════════════════════════════════════════════════════════════
_ENV_VEGAS_WEIGHT = 0.5


def team_points_estimate(inp: Inputs, projection_season: int, *,
                         vegas_weight: float = _ENV_VEGAS_WEIGHT) -> pd.DataFrame:
    """Each team's FORWARD points-per-game estimate for `projection_season`.

    A 50/50 blend of (a) the WEEK-1 Vegas implied points — the market's forward read, posted before
    a single game of the season is played — and (b) the team's recency-weighted prior points-for
    rate, regressed toward the league mean by the measured season-to-season reliability of scoring
    (ρ ≈ 0.44). Missing Vegas ⇒ the prior alone; missing prior ⇒ Vegas alone; neither ⇒ league mean.

    ⭐ WHY THIS EXACT QUANTITY: it is the ONLY scoring-environment predictor that is constructible
    identically in history and at serve time (week-1 lines are complete for every season 1999–2026).
    Fitting the FG/PAT regressions against a realized season total would flatter them with
    information production can never have — a train/serve inconsistency, not a modelling nicety.
    """
    base = int(projection_season) - 1
    prior = KD.weighted_prior_rate(
        inp.team_points.assign(pf_tot=pd.to_numeric(inp.team_points["points_for"], errors="coerce"),
                               games=pd.to_numeric(inp.team_points["team_games"], errors="coerce")),
        base, "team", "pf_tot")
    hist = inp.team_points[pd.to_numeric(inp.team_points["season"], errors="coerce") <= base]
    league = float(np.nanmean(pd.to_numeric(hist["points_for_pg"], errors="coerce"))) if len(hist) else 22.0
    vegas = inp.implied(projection_season)
    teams = sorted(set(inp.dst_universe(projection_season)["team"]))
    out = pd.DataFrame({"team": teams})
    out = out.merge(prior[["team", "prior_rate"]], on="team", how="left")
    out = out.merge(vegas, on="team", how="left")
    p = pd.to_numeric(out["prior_rate"], errors="coerce").to_numpy(dtype=float)
    v = pd.to_numeric(out["implied_points"], errors="coerce").to_numpy(dtype=float)
    # ρ(points-for/g, next season) ≈ 0.44 ⇒ the prior is regressed most of the way to league mean
    p_reg = np.where(np.isfinite(p), league + 0.44 * (p - league), np.nan)
    both = np.isfinite(p_reg) & np.isfinite(v)
    est = np.where(both, vegas_weight * v + (1 - vegas_weight) * p_reg,
                   np.where(np.isfinite(v), v, np.where(np.isfinite(p_reg), p_reg, league)))
    out["team_points_est_pg"] = est
    out["vegas_implied_points"] = v
    out["prior_points_for_pg"] = p
    return out[["team", "team_points_est_pg", "vegas_implied_points", "prior_points_for_pg"]]


def team_kick_panel(inp: Inputs, con, target_seasons: list[int]) -> pd.DataFrame:
    """Per (season, team) realized FG/PAT attempt RATES beside the FORWARD points estimate for that
    season — the frame the kicker volume regressions are fitted on. Leakage-safe: the predictor is
    built from ≤ season−1 data plus that season's week-1 line."""
    kt = (inp.kickers.groupby(["season", "team"], as_index=False)
                     .agg(fg_att=("fg_att", "sum"), pat_att=("pat_att", "sum")))
    tp = inp.team_points[["season", "team", "team_games"]]
    kt = kt.merge(tp, on=["season", "team"], how="inner")
    kt["fg_att_pg"] = pd.to_numeric(kt["fg_att"], errors="coerce") / np.clip(
        pd.to_numeric(kt["team_games"], errors="coerce"), 1e-9, None)
    kt["pat_att_pg"] = pd.to_numeric(kt["pat_att"], errors="coerce") / np.clip(
        pd.to_numeric(kt["team_games"], errors="coerce"), 1e-9, None)
    envs = []
    for y in sorted(int(v) for v in target_seasons):
        e = team_points_estimate(inp, y)[["team", "team_points_est_pg"]].assign(season=y)
        envs.append(e)
    if not envs:
        return pd.DataFrame()
    env = pd.concat(envs, ignore_index=True)
    return kt.merge(env, on=["season", "team"], how="inner")


def kicker_games_panel(inp: Inputs, con, target_seasons: list[int]) -> pd.DataFrame:
    """The historical week-1-roster kicker panel the expected-GAMES table is fitted on: for each
    (season, kicker) the roster designation, the incumbency flag, and the REALIZED games played
    (0 where the kicker never appeared — the cut-kicker class, kept, not filtered)."""
    rows = []
    for y in sorted(int(v) for v in target_seasons):
        uni = inp.kicker_universe(y)
        if uni.empty:
            continue
        u = KD.resolve_primary_kicker(uni, inp.kickers, y)
        u["is_active"] = KD.is_active_status(u.get("status"))
        real = (inp.kickers[pd.to_numeric(inp.kickers["season"], errors="coerce") == y]
                [["player_id", "games"]].rename(columns={"games": "real_games"}))
        u = u.merge(real, on="player_id", how="left")
        u["real_games"] = pd.to_numeric(u["real_games"], errors="coerce").fillna(0.0)
        tg = (inp.team_points[pd.to_numeric(inp.team_points["season"], errors="coerce") == y]
              [["team", "team_games"]])
        u = u.merge(tg, on="team", how="left")
        u["team_games"] = pd.to_numeric(u["team_games"], errors="coerce").fillna(17.0)
        rows.append(u)
    return pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Build ONE projection season
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fit_models(inp: Inputs, con, projection_season: int) -> tuple[KD.DstModel, KD.KickerModel, dict]:
    """Fit both base models on history STRICTLY BEFORE `projection_season` (in-fold by construction).

    ⚠️ Every fit RAISES on an unfittable input rather than returning silently. An
    unfittable-but-quiet model is the NF1.7 vacuous-anchor failure wearing a model's hat: the
    projection would still be emitted, the coverage check would still pass, and nobody would learn
    that the thing being validated was a constant."""
    targets = [y for y in range(PANEL_FIRST_TARGET, int(projection_season))]
    if len(targets) < 5:
        raise ValueError(f"fit_models: only {len(targets)} training target seasons before "
                         f"{projection_season} — refusing to fit a base model on that")
    sos_frames = []
    for y in targets:
        sched = inp.schedule(y)
        if sched.empty:
            continue
        sos_frames.append(KD.schedule_offense_strength(sched, inp.team_points, y))
    sos_hist = pd.concat(sos_frames, ignore_index=True) if sos_frames else pd.DataFrame()

    dst_panel = KD.build_dst_training_panel(inp.team_def, inp.team_points, sos_hist, targets)
    dst_model = KD.fit_dst_component_model(dst_panel)
    train_games = inp.team_game_points[
        pd.to_numeric(inp.team_game_points["season"], errors="coerce") < int(projection_season)]
    train_ts = inp.team_points[
        pd.to_numeric(inp.team_points["season"], errors="coerce") < int(projection_season)]
    dst_model.pa_mix = KD.fit_points_allowed_mix(train_games, train_ts)

    tk = team_kick_panel(inp, con, targets)
    hist_k = inp.kickers[pd.to_numeric(inp.kickers["season"], errors="coerce") < int(projection_season)]
    gp = kicker_games_panel(inp, con, targets)
    k_model = KD.fit_kicker_model(tk, hist_k, gp)
    diag = {"n_dst_train_rows": int(len(dst_panel)), "n_team_kick_rows": int(len(tk)),
            "n_kicker_games_rows": int(len(gp)), "train_targets": [targets[0], targets[-1]]}
    return dst_model, k_model, diag


def build_projection(inp: Inputs, con, projection_season: int,
                     dst_model: KD.DstModel, k_model: KD.KickerModel,
                     band: KD.RatioBand | None) -> pd.DataFrame:
    """Assemble the K + DST projection for one season (raw components + convenience total + band)."""
    y = int(projection_season)
    sched = inp.schedule(y)
    if sched.empty:
        raise ValueError(f"build_projection: no regular-season schedule for {y} — cannot project "
                         f"a season whose game universe is unknown")
    sos = KD.schedule_offense_strength(sched, inp.team_points, y)
    env = team_points_estimate(inp, y)
    dst_uni = inp.dst_universe(y)
    hist_def = inp.team_def[pd.to_numeric(inp.team_def["season"], errors="coerce") < y]
    hist_pts = inp.team_points[pd.to_numeric(inp.team_points["season"], errors="coerce") < y]
    dst = KD.project_dst(dst_uni, hist_def, hist_pts, dst_model, sos, y)
    dst = dst.merge(env[["team", "team_points_est_pg"]], on="team", how="left")

    k_uni = inp.kicker_universe(y)
    hist_k = inp.kickers[pd.to_numeric(inp.kickers["season"], errors="coerce") < y]
    if k_uni.empty:
        log.warning("[ALERT] no week-1 kicker roster for %d — the K population is EMPTY this "
                    "season (the board's K slot stays unfilled; investigate the roster feed)", y)
        k = pd.DataFrame()
    else:
        k = KD.project_kickers(k_uni, hist_k, k_model,
                               env.rename(columns={"team": "team"}),
                               dst_uni[["team", "scheduled_games"]], y)

    proj = pd.concat([d for d in (dst, k) if len(d)], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["is_rookie"] = False
    proj["model_version"] = KD.MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    proj["proj_fp_std"] = KD.score_convenience(proj)
    proj["band_group"] = KD.band_group(proj["position"], proj.get("is_primary"),
                                       proj.get("is_active"))
    if band is not None:
        lo, hi = KD.apply_band(proj["proj_fp_std"], proj["band_group"], band)
        proj["fp_p10"], proj["fp_p90"] = lo, hi
        proj["fp_sd"] = (hi - lo) / (2 * 1.2815515594)
        proj["uncertainty_type"] = "empirical_ratio_band_80"
    else:
        proj["fp_p10"] = proj["fp_p90"] = proj["fp_sd"] = np.nan
        proj["uncertainty_type"] = "none"
    # the MVP-1 contract aliases (see OUTPUT_COLS) — identical values, shared column names
    proj["proj_fp_ppr"] = proj["proj_fp_std"]
    proj["fp_ppr_sd"] = proj["fp_sd"]
    proj["fp_ppr_p10"] = proj["fp_p10"]
    proj["fp_ppr_p90"] = proj["fp_p90"]
    for c in OUTPUT_COLS:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[OUTPUT_COLS].sort_values("proj_fp_std", ascending=False).reset_index(drop=True)
    before = len(proj)
    proj = proj.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    if len(proj) < before:
        log.warning("grain guard dropped %d duplicate player_id row(s) — investigate the upstream "
                    "roster/schedule merge", before - len(proj))
    return proj


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Realized outcomes + the WALK-FORWARD band/coverage panel
# ══════════════════════════════════════════════════════════════════════════════════════════════
def realized_for_season(inp: Inputs, season: int) -> pd.DataFrame:
    """Realized convenience totals for both populations in `season`, keyed on `player_id`.

    The DST side needs per-GAME points allowed (the tier table is per game), so the bucket counts
    are computed from the team-game rows rather than the season total."""
    y = int(season)
    out = []
    d = inp.team_def[pd.to_numeric(inp.team_def["season"], errors="coerce") == y].copy()
    if len(d):
        g = inp.team_game_points[pd.to_numeric(inp.team_game_points["season"], errors="coerce") == y]
        if len(g):
            idx = KD.pa_bucket_index(g["points_against"])
            cnt = (pd.DataFrame({"team": g["team"].to_numpy(), "_b": idx})
                   .pivot_table(index="team", columns="_b", aggfunc="size", fill_value=0))
            for j, label in enumerate(KD.PA_BUCKET_LABELS):
                d[f"pa_g_{label}"] = d["team"].map(cnt[j] if j in cnt.columns else {}).fillna(0.0)
        d["player_id"] = "DST-" + d["team"].astype(str)
        d["position"] = "DST"
        d["realized"] = KD.realized_convenience(d)
        out.append(d[["player_id", "position", "realized"]])
    k = inp.kickers[pd.to_numeric(inp.kickers["season"], errors="coerce") == y].copy()
    if len(k):
        k["position"] = "K"
        k["realized"] = KD.realized_convenience(k)
        out.append(k[["player_id", "position", "realized"]])
    return (pd.concat(out, ignore_index=True) if out
            else pd.DataFrame(columns=["player_id", "position", "realized"]))


def build_band_panel(inp: Inputs, con, first_target: int, last_target: int) -> pd.DataFrame:
    """The WALK-FORWARD panel: for each target season, the projection built with models fitted only
    on seasons before it, LEFT-JOINED to realized outcomes.

    ⚠️ THE JOIN IS A **LEFT** JOIN WITH A 0 FILL, AND THAT IS THE WHOLE POINT (NF1.9). A kicker who
    was on a week-1 roster and then cut realises exactly 0 fantasy points, and he is 13.1% of the
    kicker population. An inner join (or a `games >= n` filter) silently deletes precisely the left
    tail the interval exists to price — which is how the veteran band shipped five stories covering
    0.55 of its nominal 0.80. Every DST row realises an outcome by construction (all 32 defenses
    play), so the absence class is a kicker-only phenomenon and is reported as such."""
    rows = []
    for y in range(int(first_target), int(last_target) + 1):
        try:
            dst_model, k_model, _ = fit_models(inp, con, y)
            proj = build_projection(inp, con, y, dst_model, k_model, band=None)
        except Exception as exc:  # noqa: BLE001
            log.warning("band panel: target season %d skipped (%s)", y, exc)
            continue
        real = realized_for_season(inp, y)
        m = proj.merge(real[["player_id", "realized"]], on="player_id", how="left")
        n_absent = int(m["realized"].isna().sum())
        m["realized_missing"] = m["realized"].isna()
        m["realized"] = pd.to_numeric(m["realized"], errors="coerce").fillna(0.0)
        m["target_season"] = y
        m = m.rename(columns={"proj_fp_std": "point"})
        rows.append(m[["target_season", "player_id", "player_name", "position", "band_group",
                       "team_id", "is_primary", "is_active", "point", "realized",
                       "realized_missing"]])
        log.info("  band panel %d: %d rows (%d with no realized line → 0-filled)",
                 y, len(m), n_absent)
    if not rows:
        raise ValueError("build_band_panel: produced NO target seasons — refusing to return an "
                         "empty panel that would make every coverage check pass on nothing")
    return pd.concat(rows, ignore_index=True, sort=False)


def walk_forward_coverage(panel: pd.DataFrame, *, min_train_targets: int = 5,
                          widen: float = 1.0,
                          cluster_z: float = KD.BAND_CLUSTER_Z) -> dict:
    """Score the band WALK-FORWARD: for each target season, fit the ratio band on every EARLIER
    target season only, then measure coverage/width/interval-score on the held-out one.

    This is the honest coverage number — the band never sees its own evaluation season. Reported
    against the nominal FLOOR (per position, and pooled over rows per NF1.8), never tuned toward it.
    """
    years = sorted(int(y) for y in panel["target_season"].unique())
    held = []
    for i, y in enumerate(years):
        if i < min_train_targets:
            continue
        train = panel[panel["target_season"] < y]
        test = panel[panel["target_season"] == y].copy()
        if train.empty or test.empty:
            continue
        band = KD.fit_ratio_band(train, widen=widen, cluster_z=cluster_z)
        lo, hi = KD.apply_band(test["point"], test["band_group"], band)
        test["lo"], test["hi"] = lo, hi
        # the SAME fold with the parameter-uncertainty widening OFF — so the report can state what
        # the widening cost on the proper score, rather than presenting it as a free lunch
        raw = KD.fit_ratio_band(train, widen=widen, cluster_z=0.0)
        rlo, rhi = KD.apply_band(test["point"], test["band_group"], raw)
        test["raw_lo"], test["raw_hi"] = rlo, rhi
        held.append(test)
    if not held:
        raise ValueError("walk_forward_coverage: no held-out target seasons — a coverage check that "
                         "scores nothing must RAISE, not report a pass")
    h = pd.concat(held, ignore_index=True)
    rep = KD.band_report(h["lo"], h["hi"], h["realized"], h["position"])
    rep["held_out_seasons"] = [int(v) for v in sorted(h["target_season"].unique())]
    rep["anchors"] = KD.degenerate_anchors(h["point"], h["realized"])
    # per band GROUP too — the K starter/reserve split is the one that moves
    for g, d in h.groupby("band_group"):
        inside = (d["realized"] >= d["lo"]) & (d["realized"] <= d["hi"])
        rep[f"cov_group_{g}"] = round(float(inside.mean()), 4)
        rep[f"n_group_{g}"] = int(len(d))
        rep[f"width_group_{g}"] = round(float((d["hi"] - d["lo"]).mean()), 1)
    # what the pre-registered parameter-uncertainty widening BOUGHT and what it COST. The raw
    # (pooled-row-quantile) band is INELIGIBLE — it breaches the coverage floor, which is a hard
    # constraint — but reporting its interval score is what stops the widening reading as free.
    rep["cluster_z"] = float(cluster_z)
    rep["without_cluster_widen"] = KD.band_report(h["raw_lo"], h["raw_hi"], h["realized"],
                                                  h["position"])
    rep["cluster_widen_is_cost_pct"] = round(
        100.0 * (rep["interval_score"] / max(1e-9, rep["without_cluster_widen"]["interval_score"]) - 1.0), 3)
    rep["zero_realized_frac"] = round(float((h["realized"] <= 0).mean()), 4)
    rep["zero_realized_frac_K"] = round(
        float((h[h["position"] == "K"]["realized"] <= 0).mean()), 4)
    rep["floors"] = {p: KD.NOMINAL_COVERAGE for p in sorted(h["position"].unique())}
    rep["floor_misses"] = [p for p in rep["floors"]
                           if (rep.get(f"cov_{p}") or 0.0) < rep["floors"][p]]
    rep["pass"] = not rep["floor_misses"]
    # a shipped band that a DEGENERATE beats on the proper score is a band nobody should ship
    rep["beats_degenerates"] = bool(
        rep["interval_score"] < rep["anchors"]["zero_width"]["interval_score"]
        and rep["interval_score"] < rep["anchors"]["max_width"]["interval_score"])
    return rep


def _rank_block(d: pd.DataFrame) -> dict:
    d = d[np.isfinite(pd.to_numeric(d["point"], errors="coerce"))]
    if len(d) < 30:
        return {"n": int(len(d)), "note": "thin"}
    sp = float(d[["point", "realized"]].corr(method="spearman").iloc[0, 1])
    pr = float(d[["point", "realized"]].corr(method="pearson").iloc[0, 1])
    mae = float((d["point"] - d["realized"]).abs().mean())
    # per-season top-8 hit rate (a 12-team league starts ~12 DSTs, so top-8 is "did we find the
    # genuinely good units") — averaged over target seasons so it is not one lucky year
    hits, tot = [], 0
    for _, g in d.groupby("target_season"):
        k = min(8, len(g) // 2)
        if k < 3:
            continue
        hits.append(len(set(g.nlargest(k, "point")["player_id"])
                         & set(g.nlargest(k, "realized")["player_id"])) / k)
        tot += 1
    return {"n": int(len(d)), "spearman": round(sp, 3), "pearson": round(pr, 3),
            "mae": round(mae, 1),
            "top8_hit_rate": (round(float(np.mean(hits)), 3) if hits else None),
            "n_seasons": tot}


def rank_signal(panel: pd.DataFrame) -> dict:
    """Held-out rank correlation of the projection against realized outcomes, per position.

    Reported, and expected to be MODEST — that IS the finding for the two least predictable fantasy
    positions, and stating it is the honest framing the story requires. It is NOT a gate: a
    projection product whose value is completeness + tiering does not get withheld because the
    ceiling on K/DST predictability is low.

    ⚠️ **`K_starters_only` IS THE HONEST KICKER READ, and the pooled `K` number is NOT.** The pooled
    kicker population mixes locked-in starters with camp bodies who realise ~0, so most of its rank
    correlation is the model correctly answering "is this man going to kick at all" — a JOB-STATUS
    read, not a kicking-skill one. Quoting the pooled number as the model's accuracy would be the
    same flattery as an inner join behind a games filter, arrived at from the other direction. The
    starters-only block is the number that describes how well one startable kicker is ranked against
    another, and it is much lower. Both are reported; only the second should ever be read as skill.
    """
    out: dict = {}
    for pos, d in panel.groupby("position"):
        out[str(pos)] = _rank_block(d)
    k = panel[panel["position"] == "K"]
    if len(k) and "band_group" in k.columns:
        out["K_starters_only"] = {
            **_rank_block(k[k["band_group"] == "K_starter"]),
            "note": "the HONEST kicker read — pooled K is inflated by job status, not skill",
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".3f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def component_reliability_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Re-measure every DST component's lag-1 per-game reliability from the training panel, so the
    documented numbers are DERIVED each run rather than a constant that can silently rot."""
    rows = []
    for c in KD.DST_COMPONENTS:
        pr, re_ = panel.get(f"prior_{c}"), panel.get(f"real_{c}")
        if pr is None or re_ is None:
            continue
        p = pd.to_numeric(pr, errors="coerce")
        r = pd.to_numeric(re_, errors="coerce")
        ok = p.notna() & r.notna()
        rows.append({"component": c, "n": int(ok.sum()),
                     "lag1_r": round(float(np.corrcoef(p[ok], r[ok])[0, 1]), 3) if ok.sum() > 5 else None,
                     "declared_noise": c in KD.DST_NOISE_COMPONENTS})
    return pd.DataFrame(rows)


def write_report(path: Path, *, projection_season: int, proj: pd.DataFrame, cov: dict,
                 signal: dict, face: dict, dst_model: KD.DstModel, k_model: KD.KickerModel,
                 rel: pd.DataFrame, band: KD.RatioBand, diag: dict, panel: pd.DataFrame) -> None:
    a: list[str] = []
    p = a.append
    p(f"# NF1.6 — BASE {projection_season} K + DST season projections (position-universe extension)")
    p("")
    p(f"**Model:** `{KD.MODEL_VERSION}` · **base season:** {projection_season - 1} → **projects:** "
      f"{projection_season} · **generated:** {datetime.now(timezone.utc).isoformat()}")
    p("")
    p("> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is "
      "the betting posture). The gate is FACE-VALIDITY + COVERAGE + honest uncertainty.")
    p("")
    p("> 🚨 **READ THIS BEFORE READING A RANK.** K and DST are the LEAST PREDICTABLE fantasy "
      "positions, and this is a **BASE** model by design. The value it delivers is **COMPLETENESS** "
      "(the K/DST roster slots now fill instead of rendering \"not projected\") and **relative "
      "TIERING** (better vs worse situations) — **not precision**. Treat the output as "
      "streaming-tier guidance. The intervals are deliberately WIDE and they are the honest part of "
      "the product; a rank ordering inside a tier is noise.")
    p("")

    p("## 1. Why the model looks the way it does — every shrink is a MEASURED reliability")
    p("")
    p("Lag-1 autocorrelation of the PER-GAME rate, re-measured from this run's own training panel "
      f"({diag.get('n_dst_train_rows')} team-season rows, targets "
      f"{diag.get('train_targets', ['?', '?'])[0]}–{diag.get('train_targets', ['?', '?'])[1]}):")
    p("")
    p(_md(rel))
    p("")
    signal_comps = [r for r in rel.to_dict("records") if not r["declared_noise"]]
    noise_comps = [r for r in rel.to_dict("records") if r["declared_noise"]]
    _rr = lambda rows: (f"{min(r['lag1_r'] for r in rows):.3f}–{max(r['lag1_r'] for r in rows):.3f}"
                        if rows and all(r["lag1_r"] is not None for r in rows) else "n/a")
    p("Three findings drive the whole design:")
    p("")
    p("1. **DST carries MODEST signal, and only in the volume takeaways.** The retained components "
      f"(sacks / INT / fumble-recoveries / ST TDs) persist at ρ = {_rr(signal_comps)}, and "
      f"points-allowed/game at ρ ≈ 0.32. The three DECLARED-NOISE components (defensive TDs, "
      f"safeties, blocked kicks) sit at ρ = {_rr(noise_comps)} — low enough that projecting a "
      "team's 5 defensive TDs forward would manufacture precision that does not exist — so they are "
      "projected at the **league mean** and said to be. This is exactly why the product's claim is "
      "TIERS. ⚠️ Note these reliabilities are measured against the model's OWN 3-season "
      "recency-weighted prior, which is a better predictor than a bare one-season lag; the "
      "single-season-lag figures are lower still (sacks 0.252, INT 0.259, fumble-rec 0.223, ST TD "
      "0.166, def TD 0.094, blocked 0.019, safety −0.018).")
    p("2. **A kicker's ACCURACY is near-random year-to-year (ρ = 0.085) but his TEAM'S SCORING "
      "ENVIRONMENT is partly forecastable.**")
    p("")
    p("   ⚠️ **THE CONTEMPORANEOUS RELATIONSHIP AND THE FORECASTABLE ONE ARE WILDLY DIFFERENT, AND "
      "ONLY THE SECOND IS A MODEL INPUT.** Measured on realized seasons, PAT attempts/game "
      "correlate **0.948** with points/game (slope 0.132) — PAT volume essentially *is* offensive "
      "touchdowns, an almost mechanical identity. But the projection cannot see the realized season; "
      "it sees the FORWARD points estimate (week-1 Vegas implied points blended with a regressed "
      f"prior), and against that the correlation is only **{k_model.pat_att_r:.3f}** (fitted slope "
      f"{k_model.pat_att_coef[1]:.3f}). Quoting the 0.948 as though it were the model's accuracy "
      "would be a train/serve inconsistency dressed up as a finding — the near-identity is real, "
      "but our ability to know next season's offense is what actually bounds the projection, and "
      "that is far weaker.")
    p("")
    p(f"   FG attempts are weaker again: **{k_model.fg_att_r:.3f}** against the forward estimate "
      "(0.19 contemporaneously) and **NON-MONOTONE** — the fitted quadratic "
      f"({k_model.fg_att_coef[2]:+.5f}·x² {k_model.fg_att_coef[1]:+.4f}·x "
      f"{k_model.fg_att_coef[0]:+.3f}) turns DOWN past ≈25 points/game, because elite offenses "
      "score touchdowns instead of kicking field goals (measured: FG att/g by team-scoring quintile "
      "runs 1.769 → 1.889 → 1.969 → 1.977 → **1.955**). So FG-attempt volume is close to a constant "
      "~1.94/game for everybody, and a kicker's ranking is driven by PAT volume (his offense) plus "
      "distance mix (his leg).")
    p("3. **Leg strength IS real.** The share of a kicker's attempts from ≥50 yards persists at "
      "ρ = 0.429 — by far the strongest kicker-side signal, and 5× the reliability of his make "
      f"rate — so the distance MIX is genuinely per-kicker (shrunk with a "
      f"{k_model.mix_shrink_attempts:.0f}-attempt prior) while the make rate WITHIN a bucket is not "
      f"(shrunk with a {k_model.make_shrink_attempts:.0f}-attempt prior ≈ two and a half full "
      "seasons, i.e. a kicker's own record barely moves the projection). That matters because "
      "distance-bucketed FG scoring (3/4/5) pays for leg strength.")
    p("")

    p("## 2. What it emits — RAW components, so any league's scoring can score it")
    p("")
    p("Mirrors MVP-1's raw-line philosophy. `proj_fp_std` is a **CONVENIENCE** total for "
      "ranking/validation only; NF-C1 rescores the raw components per league.")
    p("")
    p("```")
    p("DST  proj_def_sacks · proj_def_int · proj_def_fumble_rec · proj_def_td · proj_st_td ·")
    p("     proj_def_safety · proj_def_blocked_kick · proj_dst_points_allowed ·")
    p("     proj_dst_pa_per_game(_sd) · proj_dst_pa_g_{0,1_6,7_13,14_17,18_20,21_27,28_34,35_45,46p}")
    p("K    proj_fg_att · proj_fg_made · proj_fg_made_0_39/_40_49/_50_plus · proj_fg_missed ·")
    p("     proj_pat_att · proj_pat_made")
    p("```")
    p("")
    p("⭐ **WHY THE POINTS-ALLOWED DISTRIBUTION IS EMITTED AS EXPECTED-GAMES-PER-BUCKET, and why "
      "that un-blocks NF-C0b without NF1.6 depending on it.** DST points-allowed scoring is a "
      "per-game TIER table, which is **not linear in season points allowed** — so a season total "
      "cannot be scored under it. But `Σ_bucket tier_points × E[games in bucket]` **is** linear in "
      "the emitted columns, so the existing sport-agnostic linear scorer expresses ANY tier scheme "
      "exactly, with **no engine change**. The nine bucket edges are the common REFINEMENT of the "
      "ESPN (0/1-6/7-13/14-17/18-27/28-34/35-45/46+) and Yahoo (0/1-6/7-13/14-20/21-27/28-34/35+) "
      "schemes, so both are exact unions of them; a scheme with other edges re-integrates from "
      "`proj_dst_pa_per_game` + `_sd`, and is told so rather than silently mis-scored.")
    p("")
    p("⭐ **WHY THE DISTRIBUTION IS EMPIRICAL, NOT PARAMETRIC.** A shutout is the most valuable game "
      "outcome under every tier scheme, and P(0 PA) = **0.0099** in the data. A negative binomial "
      "matched to the observed mean/variance of team points allowed puts **~1e-4** there — it misses "
      "the single most valuable atom by two orders of magnitude, because NFL scores are lumpy "
      "multiples of 3 and 7 rather than a smooth count. So the bucket mix is read off the EMPIRICAL "
      "conditional distribution of per-game points allowed given the team's projected rate "
      f"({dst_model.pa_mix.n_games if dst_model.pa_mix else 0} team-games, quantile-binned with "
      "linear interpolation), which reproduces the atom by construction — and reproduces the "
      "observed monotonicity (best-quintile defenses are shut-out-capable ~2.4% of games, "
      "worst-quintile ~0.0%).")
    p("")

    p("## 3. Coverage — the honest number, measured on the RIGHT population")
    p("")
    p("⚠️ **The panel is the PRESEASON universe LEFT-JOINED to realized outcomes with a 0 fill, "
      "never an inner join behind a games filter.** A kicker who made a week-1 roster and was then "
      f"cut realises exactly 0 fantasy points, and that is **{cov.get('zero_realized_frac_K')}** of "
      "the held-out kicker population. Deleting it is precisely how the veteran band shipped five "
      "stories covering 0.55 of its nominal 0.80 (NF1.9). Coverage below is a **FLOOR** "
      "(≥ nominal 0.80), never a target to tune toward — both these targets are heavily skewed with "
      "a point mass at 0, which is the exact shape that makes a coverage TARGET structurally "
      "inverted (NF1.9 (e)).")
    p("")
    rows = []
    for pos in sorted(cov["floors"]):
        rows.append({"position": pos, "n (held-out)": cov.get(f"n_{pos}"),
                     "coverage": cov.get(f"cov_{pos}"), "floor": cov["floors"][pos],
                     "mean width": cov.get(f"width_{pos}"),
                     "interval score": cov.get(f"is_{pos}"),
                     "verdict": "✅ met" if (cov.get(f"cov_{pos}") or 0) >= cov["floors"][pos]
                                else "🚨 BREACH"})
    p(_md(pd.DataFrame(rows)))
    p("")
    p(f"Pooled over rows: coverage **{cov['coverage_80']}** (nominal {cov['nominal']}), "
      f"below-p10 {cov['below_p10']}, above-p90 {cov['above_p90']}, mean width "
      f"{cov['mean_width']}, interval score {cov['interval_score']}. Held-out seasons "
      f"{cov['held_out_seasons'][0]}–{cov['held_out_seasons'][-1]}, walk-forward (the band never "
      f"sees its own evaluation season).")
    p("")
    grp_rows = [{"band group": g.replace("cov_group_", ""),
                 "n": cov.get(f"n_group_{g.replace('cov_group_', '')}"),
                 "coverage": cov[g],
                 "mean width": cov.get(f"width_group_{g.replace('cov_group_', '')}")}
                for g in sorted(k for k in cov if k.startswith("cov_group_"))]
    p("Per BAND GROUP — the one split that materially matters (a locked-in starting kicker and a "
      "camp body have completely different outcome distributions; mean games share 0.923 vs 0.140):")
    p("")
    p(_md(pd.DataFrame(grp_rows)))
    p("")
    p("### ⭐ The parameter-uncertainty widening — what it fixed, and what it cost")
    p("")
    wo = cov["without_cluster_widen"]
    p("The first cut of this band used the POOLED ROW quantile of `realized / projected` per group. "
      "It **breached both floors** — and the diagnosis is structural, not a tuning problem: the "
      "quantile itself MOVES SEASON TO SEASON. Measured on the panel, the K-starter ratio q10 ranges "
      "from **0.31 to 0.94** across the 15 held-out seasons, while the pooled row quantile is a "
      "single 0.63. Rows inside a season share that season's regime and are **not independent "
      "draws** — the same class-clustering NF1.8 makes explicit for per-position floors. A band that "
      "quotes the pooled quantile is therefore implicitly claiming to know next season's quantile "
      "exactly, and it under-covers by precisely that unmodelled spread.")
    p("")
    p(f"So each bound is shifted OUTWARD by `z ×` the ACROSS-SEASON SD of that bound, with "
      f"**z = {cov['cluster_z']} fixed in advance** (`BAND_CLUSTER_Z`) — the same parameter-"
      f"uncertainty widening NF1.4/NF1.7 apply to rookie intervals for P1A's `sd`. The shift is "
      f"outward-only, so it can never sharpen a bound (the NF1.7 (d) widen-only invariant).")
    p("")
    p(_md(pd.DataFrame([
        {"band": "pooled row quantile (z = 0) — INELIGIBLE, breaches the floor",
         "coverage": wo["coverage_80"], "cov K": wo.get("cov_K"), "cov DST": wo.get("cov_DST"),
         "mean width": wo["mean_width"], "interval score": wo["interval_score"]},
        {"band": f"+ parameter-uncertainty widening (z = {cov['cluster_z']}) — SHIPPED",
         "coverage": cov["coverage_80"], "cov K": cov.get("cov_K"), "cov DST": cov.get("cov_DST"),
         "mean width": cov["mean_width"], "interval score": cov["interval_score"]},
    ])))
    p("")
    p(f"⚖️ **The widening is NOT a free lunch and is not presented as one: it cost "
      f"{cov['cluster_widen_is_cost_pct']:+.2f}% of interval score.** That is the correct trade to "
      "make here — the coverage floor is a hard CONSTRAINT and the pooled-quantile band is "
      "ineligible under it, so the interval score only ranks arms that already satisfy the floor "
      "(NF1.8). Reporting the cost is what keeps that a stated trade rather than a hidden one.")
    p("")
    p(f"⚠️ **DST over-covers ({cov.get('cov_DST')} against a 0.80 floor) and is DELIBERATELY NOT "
      "sharpened toward nominal.** Coverage is a FLOOR, never a target to minimise distance to "
      "(E2.1-r), and every notch of tightening moves the band toward the `max_width` degenerate's "
      "side of the trade rather than away from it (NF1.8). There is also a structural reason to "
      "expect coverage above nominal on these two populations: both targets have a point mass at 0 "
      "with a bound floored at 0, so the left tail is close to un-missable — the same zero-atom "
      "geometry that made a 0.80 coverage TARGET structurally inverted on the veteran board (NF1.9 "
      f"(e)). {cov['zero_realized_frac_K']} of the held-out kicker rows realise exactly 0.")
    p("")
    p("### The two-sided degenerate anchors")
    p("")
    p("There is no candidate field here to overfit — the band is **reported, not selected** — but a "
      "band that a degenerate beats on a proper score is a band nobody should ship. `zero_width` is "
      "maximally SHARP (pays the full miss penalty); `max_width` is maximally WIDE (satisfies ANY "
      "coverage floor and pays its own width). **Both must lose** the interval score, and the "
      "`max_width` line is the standing proof that the coverage figure is a CONSTRAINT rather than a "
      "criterion (NF1.8): a degenerate satisfies it, and the interval score then eliminates the "
      "degenerate.")
    p("")
    p(_md(pd.DataFrame([
        {"arm": "SHIPPED base band", "interval score": cov["interval_score"],
         "coverage": cov["coverage_80"], "mean width": cov["mean_width"]},
        {"arm": "zero_width (degenerate, sharp)",
         "interval score": cov["anchors"]["zero_width"]["interval_score"],
         "coverage": cov["anchors"]["zero_width"]["coverage_80"], "mean width": 0.0},
        {"arm": "max_width (degenerate, wide)",
         "interval score": cov["anchors"]["max_width"]["interval_score"],
         "coverage": cov["anchors"]["max_width"]["coverage_80"],
         "mean width": cov["anchors"]["max_width"]["mean_width"]},
    ])))
    p("")
    p(f"**Beats both degenerates: {'✅ yes' if cov['beats_degenerates'] else '🚨 NO — do not ship'}**")
    p("")
    p("### The shipped band")
    p("")
    p("```json")
    p(json.dumps(band.to_dict(), indent=2))
    p("```")
    p("")
    p("The band is empirical quantiles of `realized / projected` per band group — a MULTIPLICATIVE "
      "shape, because both targets floor at exactly 0 with a long right tail, so an additive "
      "symmetric band would push the lower bound below the floor and understate the upside. "
      "**p10 and p90 are emitted INDEPENDENTLY** and carried through the league rescore via "
      "`SportProfile.base_p10_column/base_p90_column` — never reconstructed from a single `sd`, "
      "which would re-symmetrise a skewed band and slide it off its own point (the exact bug NF1.7 "
      "fixed for rookies). `apply_band` enforces `lo ≤ point ≤ hi`.")
    p("")

    p("## 4. Held-out rank signal — modest, and that IS the finding")
    p("")
    p(_md(pd.DataFrame([{"position": k, **v} for k, v in signal.items()])))
    p("")
    p("These numbers are **not** a gate. A projection product whose stated value is completeness + "
      "tiering does not get withheld because the ceiling on K/DST predictability is low; the "
      "honest response is to report the ceiling, keep the intervals wide, and label the surface as "
      "streaming-tier guidance. A DST rank correlation in this range means the model separates "
      "**good situations from bad ones** and does not pretend to separate DST3 from DST7.")
    p("")

    p("## 5. Face validity — the edge-independent gate")
    p("")
    p(f"**Verdict: {'✅ PASS' if face['pass'] else '🚨 TRIPPED'}**")
    p("")
    p(_md(pd.DataFrame(face["checks"])))
    p("")

    p("## 6. The 2026 board (top of each position)")
    p("")
    for pos in ("DST", "K"):
        d = proj[proj["position"] == pos].nlargest(12, "proj_fp_std")
        if d.empty:
            continue
        cols = ["player_name", "team_id", "proj_games", "proj_fp_std", "fp_p10", "fp_p90"]
        extra = (["proj_dst_pa_per_game", "proj_def_sacks", "proj_def_int"] if pos == "DST"
                 else ["proj_fg_made", "proj_pat_made", "team_points_est_pg", "is_primary"])
        p(f"### {pos}")
        p("")
        p(_md(d[cols + extra].reset_index(drop=True)))
        p("")

    p("## 7. Model coefficients")
    p("")
    p("```json")
    p(json.dumps({"dst": dst_model.to_dict(), "kicker": k_model.to_dict(), "diagnostics": diag},
                 indent=2, default=float)[:12000])
    p("```")
    p("")

    p("## 8. Standing monitoring — the K/DST coverage floors have an OWNER")
    p("")
    p("⭐ **DECISION: `run_interval_revalidation.py` is EXTENDED to cover the K/DST floors.** The "
      "alternative (scoping K/DST out of the standing check) was rejected: a per-position coverage "
      "floor is INVISIBLE at serving time — coverage needs realized outcomes, so no board build, "
      "export guard or API check can notice it break — and leaving two brand-new positions with "
      "silently-unmonitored bands is *precisely* the gap that let the veteran band go five stories "
      "at 0.55 of nominal. Run it once a season after the completed season lands:")
    p("")
    p("```")
    p("uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation \\")
    p("  --rebuild-kdst-panel")
    p("```")
    p("")
    p("⚠️ **The breach RESPONSE differs from the rookie/veteran populations, deliberately.** Those "
      "bands were SELECTED by a §0.5 bake-off, so a breach re-triggers that selection. The K/DST "
      "band is **reported, not selected** — there is no candidate field to re-run. A breach here "
      "means WIDEN THE BASE BAND HONESTLY (`RatioBand.widen`, which is monotone: it inflates the "
      "half-widths around 1.0 so it can only ever widen, never sharpen one side — the NF1.7 (d) "
      "widen-only invariant) and re-report. It does **not** mean move the floor: a floor that moves "
      "until something clears it is not a floor (E2.1-r).")
    p("")

    p("## 9. Limitations — stated, not buried")
    p("")
    p("- **This is a BASE model on the two least predictable fantasy positions.** Deliberately so "
      "(the story's own framing): the win is completeness + honest tiering. It is NOT a §0.5 "
      "bake-off, no model class was selected, and no `best_alpha`/PBO claim is made or implied.")
    p("- **Defensive TDs, safeties and blocked kicks are projected at the LEAGUE MEAN** because "
      "their measured year-over-year reliability is indistinguishable from zero. Any league that "
      "scores them heavily should read those columns as \"the league-average expectation\", not as a "
      "team-specific forecast. They are emitted rather than dropped so a league CAN score them.")
    p("- **A kicker's make rate is barely his own.** The 200-attempt shrink prior means a kicker's "
      "personal accuracy record moves his projection very little. That is the measurement "
      "(ρ = 0.085), not a shortcut — but it does mean the model will never tell you a kicker is "
      "\"more accurate\", only that his offense is better and his leg is stronger.")
    p("- **Kicker JOB security is a roster heuristic, not an oracle.** The incumbent is resolved by "
      "recency-weighted prior FG volume, and expected games come from a 4-cell empirical table. A "
      "genuine open camp battle is expressed as two rows each carrying the non-primary games share "
      "— honest, but it means neither row is right if the battle resolves cleanly. Re-run through "
      "camp as the roster feed refreshes.")
    p("- **FG-attempt volume is close to unforecastable** (r ≈ 0.19 with team scoring, and "
      "NON-MONOTONE). The model therefore assigns nearly the league-average attempt rate to "
      "everyone. A kicker's ranking is driven by PAT volume (his offense) and distance mix (his "
      "leg), which is the honest decomposition.")
    p("- **The points-allowed distribution is conditional on the projected RATE only.** It does not "
      "model within-season correlation, weather, or specific matchups; it is the league's empirical "
      "game-level shape for a defense of that quality.")
    p("- **A tier scheme whose points-allowed edges are not a union of the nine emitted buckets** "
      "cannot be scored exactly from the bucket columns — it must re-integrate from "
      "`proj_dst_pa_per_game`/`_sd`. ESPN and Yahoo both are exact.")
    p("- **NULL/unknown is kept NULL.** A team with no prior defensive history, or a kicker with no "
      "NFL attempts, is projected at the league mean and marked `confidence = very_low` rather than "
      "being given a fabricated team-specific number.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF1.6 — BASE K + DST season projections")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--staging", default=STAGING_SCHEMA)
    ap.add_argument("--projection-season", type=int, default=None,
                    help="the season to project (default: last completed season + 1)")
    ap.add_argument("--history-from", type=int, default=HISTORY_FIRST_SEASON)
    ap.add_argument("--panel-from", type=int, default=PANEL_FIRST_TARGET,
                    help="first target season of the walk-forward band/coverage panel")
    ap.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    ap.add_argument("--s3", action="store_true", help="also land the projection to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("--rebuild-panel", action="store_true",
                    help="rebuild the walk-forward band panel (do this after a new season lands)")
    ap.add_argument("--widen", type=float, default=1.0,
                    help="honest post-hoc widening of the base band (>1 widens BOTH sides; the "
                         "sanctioned response to a coverage-floor breach)")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first (see docstring)")

    import duckdb

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        last_completed = int(con.sql(
            f"select max(season) from {args.staging}.stg_nfl_schedules "
            f"where is_regular_season and home_score is not null").fetchone()[0])
        projection_season = args.projection_season or (last_completed + 1)
        log.info("last completed season %d → projecting %d", last_completed, projection_season)

        inp = Inputs(con, args.history_from, max(last_completed, projection_season),
                     schema=args.schema, staging=args.staging)

        # ── the walk-forward band/coverage panel ────────────────────────────────────────────
        if args.rebuild_panel or not _PANEL_CACHE.exists():
            log.info("building the walk-forward band panel %d–%d …", args.panel_from, last_completed)
            panel = build_band_panel(inp, con, args.panel_from, last_completed)
            _PANEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
            panel.to_parquet(_PANEL_CACHE, index=False)
        else:
            panel = pd.read_parquet(_PANEL_CACHE)
            log.info("band panel loaded from cache: %d rows (%s to rebuild)", len(panel),
                     "--rebuild-panel")

        cov = walk_forward_coverage(panel, widen=args.widen)
        signal = rank_signal(panel)
        log.info("walk-forward coverage: %s", {k: v for k, v in cov.items()
                                              if k in ("coverage_80", "cov_K", "cov_DST",
                                                       "interval_score", "pass")})
        if not cov["pass"]:
            log.warning("[ALERT] K/DST coverage floor BREACH on %s — the sanctioned response is to "
                        "WIDEN the base band (--widen), never to move the floor", cov["floor_misses"])
        if not cov["beats_degenerates"]:
            log.warning("[ALERT] the base band does NOT beat both degenerate anchors — do not ship")

        # ── the forward projection ──────────────────────────────────────────────────────────
        band = KD.fit_ratio_band(panel[panel["target_season"] < projection_season],
                                 widen=args.widen)
        dst_model, k_model, diag = fit_models(inp, con, projection_season)
        proj = build_projection(inp, con, projection_season, dst_model, k_model, band)
        log.info("%d projection: %d rows (%d DST, %d K)", projection_season, len(proj),
                 int((proj["position"] == "DST").sum()), int((proj["position"] == "K").sum()))

        face = KD.face_validity(proj)
        if not face["pass"]:
            log.warning("[ALERT] NF1.6 face-validity gate TRIPPED: %s",
                        [c for c in face["checks"] if not c["pass"]])
        else:
            log.info("NF1.6 face validity: pass")

        # ── artifacts ───────────────────────────────────────────────────────────────────────
        proj.to_parquet(out_dir / f"nfl_fantasy_kdst_projections_{projection_season}.parquet",
                        index=False)
        ranked = proj.copy()
        ranked.insert(0, "pos_rank", ranked.groupby("position").cumcount() + 1)
        ranked.to_csv(out_dir / f"nfl_fantasy_kdst_projections_{projection_season}_ranked.csv",
                      index=False)
        if args.s3 or args.lake_root:
            from quant_sports_intel_models.football.nfl.ingest import s3io
            n = s3io.write_dataframe(proj.assign(season=int(projection_season)), sport="nfl",
                                     source="kdst_projections", season=int(projection_season),
                                     tier="fantasy/derived", local_root=args.lake_root)
            log.info("landed %d rows → nfl/fantasy/derived/kdst_projections season=%d", n,
                     projection_season)

        dst_panel_for_rel = KD.build_dst_training_panel(
            inp.team_def, inp.team_points, None,
            list(range(args.panel_from, projection_season)))
        rel = component_reliability_table(dst_panel_for_rel)

        summary = {"model_version": KD.MODEL_VERSION, "projection_season": projection_season,
                   "n_rows": int(len(proj)),
                   "n_by_position": proj.groupby("position").size().to_dict(),
                   "coverage": cov, "rank_signal": signal, "face_validity": face,
                   "band": band.to_dict(), "diagnostics": diag,
                   "generated_at": datetime.now(timezone.utc).isoformat()}
        (out_dir / "nfl_fantasy_kdst_summary.json").write_text(
            json.dumps(summary, indent=2, default=float))

        if not args.no_report:
            write_report(_REPORT_PATH, projection_season=projection_season, proj=proj, cov=cov,
                         signal=signal, face=face, dst_model=dst_model, k_model=k_model,
                         rel=rel, band=band, diag=diag, panel=panel)
    finally:
        con.close()

    print("\n=== NF1.6 K/DST base projection ===")
    print(f"  {projection_season}: {len(proj)} rows "
          f"({int((proj['position'] == 'DST').sum())} DST, {int((proj['position'] == 'K').sum())} K)")
    print(f"  walk-forward coverage: pooled {cov['coverage_80']} (nominal {cov['nominal']}) · "
          f"K {cov.get('cov_K')} · DST {cov.get('cov_DST')} · IS80 {cov['interval_score']}")
    print(f"  beats both degenerate anchors: {cov['beats_degenerates']}")
    print(f"  held-out rank signal: " + " · ".join(
        f"{k} ρ={v.get('spearman')}" for k, v in signal.items()))
    print(f"  face validity: {'PASS' if face['pass'] else 'TRIPPED'}")
    # ⭐ the coverage floor is the gate; a breach exits NON-ZERO so it cannot be a log line nobody
    #    reads. Face validity is advisory (a projection product), and is reported either way.
    return 0 if cov["pass"] and cov["beats_degenerates"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
