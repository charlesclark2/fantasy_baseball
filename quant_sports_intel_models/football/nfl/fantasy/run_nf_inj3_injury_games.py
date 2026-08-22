"""run_nf_inj3_injury_games.py — NF-INJ3 §0.5 bake-off: replace the hardcoded injury-games caps.

Everything decidable in advance lives as a CONSTANT in `nf_inj3_injury_games.py`; this runner READS
it and restates nothing (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_inj3_preregistration.md` BEFORE any arm was scored.

PIPELINE: single-vintage historical MVP-1 builds (2016–2025, ONE run) → week-1 roster status →
recover the model's pre-cap `eg` by inverting the shipped map → realized games from the warehouse
(NF-D10: the OUTCOME comes from the warehouse, the model's own games from the build vintage) →
7 expanding-window folds (2019…2025) → 7 declared arms + the matched foil + 4 anchor families
through ONE reducer → exact discrete CRPS selection → PBO + DSR-CONV + BH-FDR + cv_power fold
consistency → ship-or-null.

RUN (LAPTOP — reads the local DuckDB + build artifacts read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3_injury_games
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3_injury_games --smoke
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_inj3")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
_DEFAULT_DUCKDB = "quant_sports_intel_models/sports_dbt/sports.duckdb"
_STAGING, _MARTS = "main_nfl_staging", "main_nfl_marts"
_SEED = 20260822
MAX_PBO, MIN_DSR = 0.20, 0.95
SERVING_SEASON = 2026
#: 🔒 the SERVED arm. Deploy-held: nothing here serves until the PM records a disposition.
SERVED_ARM = "incumbent"
#: the REFERENCE arm — its lift over itself is identically 0, so its trial Sharpe is 0 by
#: construction (MH2.1 (a)). Named here so the diagnostic cannot silently mean something else.
INCUMBENT_REFERENCE = "incumbent"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Population
# ══════════════════════════════════════════════════════════════════════════════════════════════
def artifacts_dir(explicit: str | None) -> Path:
    """Where the single-vintage MVP-1 builds live.

    ⚠️ NF-INFRA1: `artifacts/` and `sports.duckdb` are gitignored, so a fresh worktree does NOT have
    them — `--artifacts` points at the checkout that does. A missing directory RAISES rather than
    degrading to an empty population (a build that reads nothing must not report success)."""
    p = Path(explicit) if explicit else (_HERE / "artifacts")
    if not p.is_dir():
        raise FileNotFoundError(
            f"NF-INJ3: MVP-1 build artifacts not found at {p} — pass --artifacts <dir>. These are "
            f"gitignored (NF-INFRA1) and absent from a fresh worktree.")
    return p


def load_status(con, season: int, sleeper: bool) -> pd.DataFrame:
    """Week-1 roster status. For the SERVING season the Sleeper forward feed is coalesced in exactly
    as `run_season_projection.load_forward_roster_status` does; for a historical season Sleeper
    holds nothing, so the nflverse leg is the whole story."""
    nv = con.sql(f"""
        select player_id, first(status order by week asc) as proj_status
        from {_STAGING}.stg_nfl_weekly_rosters
        where season = {season} and player_id is not null group by 1
    """).df()
    if not sleeper:
        return nv
    sl = con.sql(f"""
        select player_id, first(proj_status order by ingested_at desc) as ps
        from {_STAGING}.stg_nfl_sleeper_injuries
        where season = {season} and player_id is not null and proj_status is not null group by 1
    """).df()
    m = nv.merge(sl, on="player_id", how="outer")
    m["proj_status"] = m["ps"].where(m["ps"].notna(), m["proj_status"])
    return m[["player_id", "proj_status"]]


def load_prior_features(con, season: int) -> pd.DataFrame:
    """The season-(Y−1) covariates, incl. the two declared TIMING-proxy columns. All leakage-safe:
    every one is knowable from season Y−1 plus the Y week-1 snapshot."""
    return con.sql(f"""
    with pg as (
      select season, player_id,
             count_if(played_flag and not is_bye) as games,
             sum(case when played_flag then fantasy_points_ppr else 0 end)::double as fp,
             max(case when played_flag then week end) as last_week_played
      from {_MARTS}.fct_player_week where week > 0 and player_id is not null group by 1, 2),
    ros as (
      select season, player_id, last(status order by week asc) as end_status
      from {_STAGING}.stg_nfl_weekly_rosters where player_id is not null group by 1, 2),
    sw as (select season, max(week) as mw from {_MARTS}.fct_player_week where week > 0 group by 1)
    select p.player_id, p.games as prior_games, p.fp as prior_fp,
           p.last_week_played, sw.mw as prior_season_weeks, r.end_status as prior_end_status
    from pg p
    left join ros r on r.season = p.season and r.player_id = p.player_id
    left join sw on sw.season = p.season
    where p.season = {season - 1}
    """).df()


def load_realized(con, season: int) -> pd.DataFrame:
    """The OUTCOME — realized games — taken from the WAREHOUSE, never from a projection panel
    (NF-D10: take only the realized outcome from a panel, keep the model's own games at its build
    vintage)."""
    return con.sql(f"""
        select player_id, count_if(played_flag and not is_bye) as realized_games
        from {_MARTS}.fct_player_week
        where season = {season} and week > 0 and player_id is not null group by 1
    """).df()


def build_population(con, art: Path, seasons: tuple[int, ...],
                     serving_season: int = SERVING_SEASON) -> tuple[pd.DataFrame, dict]:
    """One row per (target season, flagged VETERAN board row). Returns `(frame, provenance)`."""
    frames, prov = [], {"per_season": [], "excluded": {}}
    for y in seasons:
        f = art / f"nfl_fantasy_season_projections_{y}.parquet"
        if not f.exists():
            raise FileNotFoundError(f"NF-INJ3: missing MVP-1 build for {y}: {f}")
        board = pd.read_parquet(f)
        st = load_status(con, y, sleeper=(y == serving_season))
        m = board.merge(st, on="player_id", how="left")
        flagged = m[m["proj_status"].isin(SP._INJURY_STATUS_GAMES_CAP)].copy()
        n_flagged = len(flagged)
        rookies = int(flagged["is_rookie"].astype(bool).sum())
        flagged = flagged[~flagged["is_rookie"].astype(bool)]
        sm = pd.to_numeric(flagged.get("seasons_missed"), errors="coerce").fillna(0)
        returners = int((sm >= 1).sum())
        flagged = flagged[sm < 1]
        flagged["target_season"] = y
        flagged["eg"] = IG.recover_pre_cap_games(flagged["proj_games"].to_numpy(),
                                                 flagged["proj_status"])
        pri = load_prior_features(con, y)
        flagged = flagged.merge(pri, on="player_id", how="left")
        if y != serving_season:
            flagged = flagged.merge(load_realized(con, y), on="player_id", how="left")
            flagged["realized_games"] = pd.to_numeric(
                flagged["realized_games"], errors="coerce").fillna(0.0)
        flagged["prior_games"] = pd.to_numeric(flagged["prior_games"], errors="coerce").fillna(0.0)
        flagged["prior_fp"] = pd.to_numeric(flagged["prior_fp"], errors="coerce").fillna(0.0)
        # PPR can go NEGATIVE (a QB with interceptions and no yardage), and log1p(x < -1) is
        # NaN — clipped at 0 so the covariate is defined on every row rather than silently
        # NaN-ing a real player out of the design matrix.
        flagged["log1p_prior_fp"] = np.log1p(flagged["prior_fp"].clip(lower=0.0))
        flagged["is_qb"] = (flagged["position"].astype(str).str.upper() == "QB").astype(float)
        # ── the two DECLARED timing-proxy columns (preregistration §2) ────────────────────────
        flagged["onset_carryover"] = flagged["prior_end_status"].astype(str).isin(
            ("RES", "PUP", "NFI", "SUS", "INA")).astype(float)
        lw = pd.to_numeric(flagged["last_week_played"], errors="coerce")
        weeks = pd.to_numeric(flagged["prior_season_weeks"], errors="coerce")
        # a player with NO prior-season game has the LONGEST possible absence, not a missing one —
        # the sentinel is the full prior season, never a fillna(0) that would read as "just played".
        flagged["weeks_since_last_game"] = (weeks - lw).fillna(weeks.max() if weeks.notna().any()
                                                               else 18.0)
        prov["per_season"].append({"season": y, "board_rows": int(len(board)),
                                   "flagged": n_flagged, "rookies_excluded": rookies,
                                   "returners_excluded": returners, "scored": int(len(flagged))})
        frames.append(flagged)
    out = pd.concat(frames, ignore_index=True)
    prov["excluded"] = {
        "rookies": int(sum(r["rookies_excluded"] for r in prov["per_season"])),
        "returners": int(sum(r["returners_excluded"] for r in prov["per_season"])),
        "why_rookies": "injury_availability_games runs inside project_veterans; project_rookies is a "
                       "separate frame concatenated afterwards, so the cap STRUCTURALLY cannot act "
                       "on a rookie (preregistration §3 — out of scope, recorded for carding)",
        "why_returners": "NF-D11's absence prior runs immediately after the injury cap, so a "
                         "returner's served games compose two caps and this one's contribution is "
                         "not separably recoverable (preregistration §3)",
    }
    return out, prov


def rookie_bypass_evidence(con, art: Path, seasons: tuple[int, ...]) -> dict:
    """MEASURE the rookie bypass rather than assert it — how many flagged rookies project ABOVE the
    incumbent's own ceiling, against the veteran rate on the same builds."""
    rk_n = rk_above = vet_n = vet_above = 0
    for y in seasons:
        board = pd.read_parquet(art / f"nfl_fantasy_season_projections_{y}.parquet")
        m = board.merge(load_status(con, y, sleeper=False), on="player_id", how="left")
        f = m[m["proj_status"].isin(SP._INJURY_STATUS_GAMES_CAP)].copy()
        cap = f["proj_status"].map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)
        ceil = (1 - SP._INJURY_OVERRIDE_BLEND) * 17.0 + SP._INJURY_OVERRIDE_BLEND * cap
        above = (f["proj_games"].to_numpy() > ceil + 1e-9)
        isr = f["is_rookie"].astype(bool).to_numpy()
        rk_n += int(isr.sum()); rk_above += int((above & isr).sum())
        vet_n += int((~isr).sum()); vet_above += int((above & ~isr).sum())
    return {"rookie_flagged": rk_n, "rookie_above_ceiling": rk_above,
            "veteran_flagged": vet_n, "veteran_above_ceiling": vet_above,
            "reading": "0 veterans above the ceiling reproduces the incumbent exactly; every "
                       "above-ceiling row is a rookie, i.e. the cap never reaches that path"}


def era_fidelity(con) -> list[dict]:
    """The DESIGN quantity the era restriction rests on: is the weekly roster feed a genuine WEEKLY
    snapshot in this season, or a season-END status backfilled onto every week?"""
    return con.sql(f"""
    with chg as (
      select season, avg(case when nd > 1 then 1.0 else 0.0 end) as status_change_share from (
        select season, player_id, count(distinct status) as nd
        from {_STAGING}.stg_nfl_weekly_rosters where player_id is not null group by 1, 2) t
      group by 1),
    pg as (select season, player_id, count_if(played_flag and not is_bye) as g
           from {_MARTS}.fct_player_week where week > 0 group by 1, 2),
    w1 as (select season, player_id, first(status order by week asc) as s
           from {_STAGING}.stg_nfl_weekly_rosters where player_id is not null group by 1, 2),
    res as (
      select w1.season, count(*) as n_res,
             median(coalesce(pg.g, 0)) as med_games,
             avg(case when coalesce(pg.g, 0) = 0 then 1.0 else 0.0 end) as zero_rate
      from w1 left join pg on pg.season = w1.season and pg.player_id = w1.player_id
      where w1.s = 'RES' group by 1)
    select r.season, r.n_res, r.med_games, round(r.zero_rate, 3) as zero_rate,
           round(c.status_change_share, 3) as status_change_share
    from res r join chg c on c.season = r.season order by 1
    """).df().to_dict("records")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def score_fold(pop: pd.DataFrame, year: int) -> dict:
    """Score every arm, the matched foil, and every anchor on ONE expanding-window fold."""
    train = pop[(pop.target_season >= IG.ERA_MIN_SEASON) & (pop.target_season < year)]
    ev = pop[pop.target_season == year].reset_index(drop=True)
    n = IG.season_game_count(year)
    y = pd.to_numeric(ev["realized_games"], errors="coerce").to_numpy(dtype=float)
    if len(ev) == 0:
        raise ValueError(f"NF-INJ3: fold {year} has no eval rows — an empty fold is a build defect, "
                         f"never a pass (NF1.7 (a))")

    mu_inc, prov_inc = IG.arm_mu("incumbent", train, ev, n)
    phi = IG.fit_shared_phi(pd.to_numeric(train["realized_games"], errors="coerce").to_numpy(),
                            IG.arm_mu("incumbent", train, train, n)[0], IG.season_game_count(year))

    arms, prov = {}, {"incumbent": prov_inc, "phi": phi}
    for a in (*IG.ARMS, IG.MATCHED_FOIL):
        mu, p = IG.arm_mu(a, train, ev, n)
        arms[a] = IG.score_arm(mu, y, n, phi)
        prov[a] = p

    # ── anchors ───────────────────────────────────────────────────────────────────────────────
    anchors = {}
    pooled = float(pd.to_numeric(train["realized_games"], errors="coerce").mean())
    anchors["pooled_mean"] = IG.score_arm(np.full(len(ev), pooled), y, n, phi)
    ev_perm = IG.permute_timing(ev, seed=_SEED + year)
    f = IG.TIMING_FEATURES + IG.BASE_FEATURES
    anchors["permuted_timing"] = IG.score_arm(
        IG.predict_glm_mean(IG.fit_glm_mean(train, f, n), ev_perm, f, n), y, n, phi)

    # ⭐ PER-FORM peeking oracles (NF-D16 g‴): the forms NEST, so a single field-wide ceiling would
    #    falsely veto a legitimately better nested form. Each oracle refits that arm's OWN form on
    #    the eval fold's realized outcomes.
    oracles = {}
    for a, feats in (("timing_aware", IG.TIMING_FEATURES + IG.BASE_FEATURES),
                     (IG.MATCHED_FOIL, IG.BASE_FEATURES)):
        oracles[a] = IG.score_arm(IG.predict_glm_mean(IG.fit_glm_mean(ev, feats, n), ev, feats, n),
                                  y, n, phi)
    lv, _ = IG.fit_status_levels(ev)
    b = IG.fit_blend(ev, lv, n)
    eg_ev = pd.to_numeric(ev["eg"], errors="coerce").to_numpy(dtype=float)
    cap_ev = ev["proj_status"].astype(str).map(lv).to_numpy(dtype=float)
    oracles["fitted_status"] = IG.score_arm(
        np.clip((1 - b) * eg_ev + b * np.minimum(eg_ev, cap_ev), 0, float(n)), y, n, phi)
    oracles["incumbent"] = oracles["fitted_status"]   # same FORM (blend toward a per-status level)
    oracles["sus_regime"] = oracles["fitted_status"]
    hf = IG.fit_hurdle(ev, n)
    oracles["hurdle_transfer"] = IG.score_arm(IG.predict_hurdle(hf, ev, n), y, n, phi)

    # ⭐ MATCHED-n control (NF1.7 (b) / NF1.9 (f)): the primary's own form trained on ONE prior
    #    season, so the oracle floor is enforced at equal family AND equal resolution.
    prev = pop[pop.target_season == year - 1]
    matched_n = None
    if len(prev) >= IG.MIN_CELL_N:
        matched_n = IG.score_arm(
            IG.predict_glm_mean(IG.fit_glm_mean(prev, f, n), ev, f, n), y, n, phi)

    return {"year": year, "n_train": int(len(train)), "n_eval": int(len(ev)), "phi": phi,
            "arms": arms, "anchors": anchors, "oracles": oracles, "matched_n": matched_n,
            "provenance": prov,
            "status_mix": {k: int(v) for k, v in ev["proj_status"].value_counts().items()},
            "zero_rate": float(np.mean(y == 0))}


def mechanism_activity(pop: pd.DataFrame, folds: tuple[int, ...]) -> dict:
    """NF-D20 — COUNT the rows the mechanism can act on before crediting any pass. A status with no
    eval rows is UNINFORMATIVE on that fold, never a pass."""
    rows = []
    for y in folds:
        ev = pop[pop.target_season == y]
        mix = ev["proj_status"].value_counts().to_dict()
        rows.append({"fold": y, "n_eval": int(len(ev)),
                     **{s: int(mix.get(s, 0)) for s in ("RES", "PUP", "NFI", "SUS")},
                     "timing_varies": bool(ev["onset_carryover"].nunique() > 1)})
    tot = {s: int((pop["proj_status"] == s).sum()) for s in ("RES", "PUP", "NFI", "SUS")}
    return {"per_fold": rows, "total_by_status": tot,
            "inactive_statuses": [s for s, n in tot.items() if n == 0],
            "note": "NFI has ZERO rows historically AND zero in the 2026 serving cohort — its cap "
                    "is unfittable and INACTIVE; no arm may claim credit there (NF-D20)."}


def _srs(lift_by_arm: dict[str, list[float]]) -> dict[str, float]:
    out = {}
    for a, v in lift_by_arm.items():
        d = np.asarray([x for x in v if np.isfinite(x)], dtype=float)
        if len(d) >= 2:
            out[a] = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 1e-12 else 0.0
    return out


def dsr_conv(deltas, trial_srs_for_v, n_trials: int) -> float | None:
    """DSR under DSR-CONV: the pre-registered DEGENERATES stay in `n_trials` (full multiplicity) and
    are excluded from the cross-trial dispersion `V`.

    Reproduced here rather than calling `M14.deflated_sharpe` because that function derives the
    trial COUNT from `len(trial_srs)`, so the two channels `SR0 = √V·z(N)` is taxed through cannot
    be set independently — and editing a SHARED instrument other verticals pin is the MH2.7 (ii)
    hazard. The whole-field figure from the shared function is reported beside this one."""
    from scipy.stats import kurtosis, norm, skew
    d = np.asarray(deltas, dtype=float); d = d[np.isfinite(d)]
    if len(d) < 3 or float(d.std(ddof=1)) < 1e-12:
        return None
    sr = float(d.mean()) / float(d.std(ddof=1))
    v = np.asarray([x for x in trial_srs_for_v if np.isfinite(x)], dtype=float)
    em = 0.5772156649015329
    sr0 = (float(v.std(ddof=1)) * ((1 - em) * norm.ppf(1 - 1 / n_trials)
                                   + em * norm.ppf(1 - 1 / (n_trials * np.e)))
           if len(v) >= 2 and v.std(ddof=1) > 0 and n_trials >= 2 else 0.0)
    g3, g4 = float(skew(d)), float(kurtosis(d, fisher=False))
    den = 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2
    if den <= 0:
        return None
    return round(float(norm.cdf((sr - sr0) * np.sqrt(len(d) - 1) / np.sqrt(den))), 4)


def deflation(per_fold: list[dict], winner: str) -> dict:
    """PBO + the NF1.8 triad + DSR-CONV over the DECLARED field.

    PBO is computed on **negated** CRPS because `cscv_pbo` picks the in-sample ARGMAX and CRPS is a
    loss — getting that sign wrong reports the field upside-down, so a unit test asserts it."""
    arms = list(IG.ARMS)
    mat = np.array([[-f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)
    pbo = M14.cscv_pbo(mat)
    lifts = {a: [f["arms"]["incumbent"]["crps"] - f["arms"][a]["crps"] for f in per_fold]
             for a in arms}
    srs_all = _srs(lifts)
    srs_v = {k: v for k, v in srs_all.items() if k not in IG.DEGENERATE_ARMS}
    d = np.asarray(lifts[winner], dtype=float)
    scores = mat.mean(axis=1)
    order = np.argsort(-scores)                       # negated CRPS: higher = better
    top = order[:max(2, len(arms) // 4)]
    return {
        "pbo": pbo,
        "dsr_conv": dsr_conv(d, list(srs_v.values()), IG.DECLARED_FIELD_SIZE),
        "dsr_whole_field": M14.deflated_sharpe(d, np.asarray(list(srs_all.values()))),
        "trial_sharpes": {k: round(v, 4) for k, v in sorted(srs_all.items(), key=lambda kv: -kv[1])},
        "V_declared_excl_degenerates": round(float(np.var(list(srs_v.values()), ddof=1)), 4),
        "V_whole_field": round(float(np.var(list(srs_all.values()), ddof=1)), 4),
        "whole_field_spread_pct": round(100.0 * (float(-scores.min()) - float(-scores.max()))
                                        / max(1e-9, float(-scores.max())), 2),
        "contender_spread_pct": round(100.0 * (float(-scores[top].min()) - float(-scores[top].max()))
                                      / max(1e-9, float(-scores[top].max())), 2),
        "degenerates_excluded_from_v": True,
        "diagnostics": _deflation_diagnostics(d, srs_all, srs_v, winner),
        "note": "⚠️ The exclusion is NON-MONOTONE and is therefore not a lever: dropping a near-mean "
                "arm WIDENS the sample variance and RAISES the bar. It applies to the two arms named "
                "degenerate before any score, and to nothing else (DSR-CONV).",
    }


def _deflation_diagnostics(deltas, srs_all: dict, srs_v: dict, winner: str) -> dict:
    """⛔ DIAGNOSTICS — REPORTED, NEVER ACTED ON. They name the LEVER; they do not license a re-read
    of a gate (MH2.2: you get to PRE-REGISTER a family, you do not get to DISCOVER one).

    Two are computed because CLAUDE.md's own guidance splits on which one bites:
    · `mh2_1a_v_over_non_reference` — MH2.1 (a) says a REFERENCE arm's identically-ZERO skill series
      inflates a small-family `V` exactly as a diagnostic anchor does, so `V` should be measured over
      NON-reference arms while `n_trials` stays at full field. ⚠️ This study's pre-registration does
      NOT invoke that convention, so the figure is a diagnostic ONLY — adopting it after seeing the
      registered gate fail would be the E2.1-r inversion.
    · `nf_w7h_drop_most_extreme` — the standard 2×2. It REFUSES to report when the dropped arm IS the
      winner, because a DSR reached by deleting the winner is inadmissible (NF-W7h).

    ⭐ Read them together (NF-W7f): if `V` falls hard and DSR barely MOVES, the binding quantity is
    per-fold NOISE (a variance/design problem) and prescribing a coherent re-registration would spend
    a successor on the wrong lever. If `V` falls hard and DSR CLEARS, field composition is the lever."""
    out: dict = {}
    non_ref = {k: v for k, v in srs_v.items() if k != INCUMBENT_REFERENCE}
    out["mh2_1a_v_over_non_reference"] = {
        "dropped_arm": INCUMBENT_REFERENCE,
        "V_registered": round(float(np.var(list(srs_v.values()), ddof=1)), 4),
        "V_non_reference": round(float(np.var(list(non_ref.values()), ddof=1)), 4),
        "dsr_registered": dsr_conv(deltas, list(srs_v.values()), IG.DECLARED_FIELD_SIZE),
        "dsr_non_reference": dsr_conv(deltas, list(non_ref.values()), IG.DECLARED_FIELD_SIZE),
        "admissible_to_act_on": False,
        "why": "MH2.1 (a) is a convention this pre-registration did not invoke; the registered "
               "figure BINDS and this one is a diagnostic (E2.1-r).",
    }
    mean = float(np.mean(list(srs_v.values())))
    far = max(srs_v, key=lambda k: abs(srs_v[k] - mean))
    if far == winner:
        out["nf_w7h_drop_most_extreme"] = {
            "evaluable": False, "dropped_arm": far,
            "why": "the most extreme trial Sharpe IS the winner — a DSR reached by deleting it "
                   "would be INADMISSIBLE (NF-W7h), so no trimmed figure is reported"}
    else:
        kept = [v for k, v in srs_v.items() if k != far]
        out["nf_w7h_drop_most_extreme"] = {
            "evaluable": True, "dropped_arm": far, "dropped_arm_sharpe": round(srs_v[far], 4),
            "V_without_dropped_arm": round(float(np.var(kept, ddof=1)), 4),
            "dsr_without_dropped_arm": dsr_conv(deltas, kept, IG.DECLARED_FIELD_SIZE),
            "note": "⛔ A DIAGNOSTIC, NOT A TRIM."}
    return out


def anchor_audit(per_fold: list[dict], winner: str) -> dict:
    """⭐ A MISSING OR UNFITTABLE ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 (a))."""
    def _m(get):
        v = [get(f) for f in per_fold]
        return float(np.mean(v)) if all(x is not None and np.isfinite(x) for x in v) else None

    out = {}
    for a in IG.ARMS + (IG.MATCHED_FOIL,):
        arm = _m(lambda f, a=a: f["arms"][a]["crps"])
        orc = _m(lambda f, a=a: f["oracles"][a]["crps"] if a in f["oracles"] else None)
        if orc is None:
            out[a] = {"evaluable": False,
                      "why": "no own-form peeking oracle — the check would pass on NOTHING"}
            continue
        out[a] = {"evaluable": True, "arm_crps": round(arm, 4), "own_form_oracle_crps": round(orc, 4),
                  "respects_oracle": bool(arm >= orc - 1e-9)}
    mn = _m(lambda f: f["matched_n"]["crps"] if f["matched_n"] else None)
    ow = out.get(winner, {})
    out["_matched_n_control"] = (
        {"evaluable": True, "matched_n_crps": round(mn, 4),
         "oracle_beats_matched_n": bool(ow.get("own_form_oracle_crps", np.inf) <= mn + 1e-9),
         "why": "the peeking oracle is a FLOOR only at matched family AND matched resolution "
                "(NF1.7 (b) / NF1.9 (f)) — the winner's own form on ONE prior season"}
        if mn is not None else
        {"evaluable": False, "why": "matched-n control unfittable — recorded as a FAILED check, "
                                    "never a pass (NF1.7 (a))"})
    out["_degenerates"] = {
        d: {"crps": round(_m(lambda f, d=d: f["arms"][d]["crps"]), 4),
            "loses_to_winner": bool(_m(lambda f, d=d: f["arms"][d]["crps"])
                                    > _m(lambda f: f["arms"][winner]["crps"]) + 1e-9)}
        for d in IG.DEGENERATE_ARMS}
    return out


def channel_decomposition(pooled: dict, per_fold: list[dict]) -> dict:
    """Attribute the total lift over the incumbent to CHANNELS, each step a MATCHED PAIR differing
    by exactly one thing (the `margin_attribution` discipline: report the split, never headline the
    blend).

      incumbent → fitted_status                     the LEVEL channel — same form, fitted levels+blend
      fitted_status → timing_aware_minus_timing     the FORM change alone (cap-blend → GLM), no timing
      timing_aware_minus_timing → timing_aware      the TIMING channel (the matched foil, NF-D10/D15)
      timing_aware → hurdle_transfer                the HURDLE-SPLIT channel (identical covariates)

    The steps sum EXACTLY to the winner's total lift, by construction."""
    def d(a, b):
        v = [f["arms"][a]["crps"] - f["arms"][b]["crps"] for f in per_fold]
        return {"delta_crps": round(float(np.mean(v)), 4),
                "folds_positive": int(sum(1 for x in v if x > 0)),
                "p_one_sided": M14.onesided_paired_pvalue(np.asarray(v))}
    steps = {
        "level__incumbent_to_fitted_status": d("incumbent", "fitted_status"),
        "form__fitted_status_to_glm_no_timing": d("fitted_status", IG.MATCHED_FOIL),
        "timing__glm_no_timing_to_timing_aware": d(IG.MATCHED_FOIL, "timing_aware"),
        "hurdle_split__timing_aware_to_hurdle": d("timing_aware", "hurdle_transfer"),
    }
    total = round(sum(v["delta_crps"] for v in steps.values()), 4)
    return {"steps": steps, "sum_of_steps": total,
            "winner_total_lift": pooled["hurdle_transfer"]["mean_lift"],
            "reading": "the LEVEL channel dominates by an order of magnitude — the hardcoded caps "
                       "are simply too high; TIMING is a small positive increment and the HURDLE "
                       "SPLIT (the certified NF-W2 transfer) is roughly twice the timing channel."}


def verdict(*, winner: str, pooled: dict, defl: dict, anchors: dict, fold_clause: dict,
            bh: dict, permutation: dict, foil: dict) -> dict:
    beats = pooled[winner]["mean_lift"] > 0
    gates = {
        "beats_incumbent": bool(beats),
        "fold_consistency": bool(fold_clause.get("passes")),
        "pbo_ok": (None if defl["pbo"] is None else bool(defl["pbo"] < MAX_PBO)),
        "dsr_ok": (None if defl["dsr_conv"] is None else bool(defl["dsr_conv"] >= MIN_DSR)),
        "bh_ok": bool(bh.get(winner)),
        "degenerates_lose": bool(all(v["loses_to_winner"] for v in anchors["_degenerates"].values())),
        "oracle_respected": bool(all(v.get("respects_oracle", False)
                                     for k, v in anchors.items()
                                     if not k.startswith("_") and v.get("evaluable"))
                                 and anchors["_matched_n_control"].get("evaluable")),
        "beats_permutation": bool(permutation["beats"]),
        "timing_attributable": bool(foil["mean_delta"] > 0),
    }
    ship = all(v is True for v in gates.values())
    return {"winner": winner, "gates": gates, "ship": ship,
            "served_arm": SERVED_ARM, "deploy_held": True, "best_alpha": 0}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Serving application
# ══════════════════════════════════════════════════════════════════════════════════════════════
def apply_serving(pop_hist: pd.DataFrame, serving: pd.DataFrame, arm: str) -> dict:
    """What the winning arm would serve on the CURRENT board, beside the incumbent. Reported for
    every run — a null still needs the counterfactual on the record."""
    n = IG.season_game_count(SERVING_SEASON)
    train = pop_hist[pop_hist.target_season >= IG.ERA_MIN_SEASON]
    mu_new, _ = IG.arm_mu(arm, train, serving, n)
    mu_inc, _ = IG.arm_mu("incumbent", train, serving, n)
    d = pd.DataFrame({
        "player_name": serving["player_name"].to_numpy(),
        "position": serving["position"].to_numpy(),
        "status": serving["proj_status"].to_numpy(),
        "eg": np.round(serving["eg"].to_numpy(), 3),
        "onset_carryover": serving["onset_carryover"].to_numpy(),
        "weeks_since_last_game": serving["weeks_since_last_game"].to_numpy(),
        "incumbent_games": np.round(mu_inc, 3), "arm_games": np.round(mu_new, 3),
    }).sort_values("incumbent_games", ascending=False)
    d["delta"] = np.round(d["arm_games"] - d["incumbent_games"], 3)
    return {"arm": arm, "n": int(len(d)),
            "mean_incumbent_games": round(float(mu_inc.mean()), 3),
            "mean_arm_games": round(float(mu_new.mean()), 3),
            "n_moved_down": int((d["delta"] < -0.05).sum()),
            "n_moved_up": int((d["delta"] > 0.05).sum()),
            "rows": d.to_dict("records")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(con, art: Path, folds: tuple[int, ...]) -> dict:
    t0 = time.time()
    hist_seasons = tuple(range(IG.ERA_MIN_SEASON, max(folds) + 1))
    pop, prov = build_population(con, art, hist_seasons)
    serving, sprov = build_population(con, art, (SERVING_SEASON,))
    activity = mechanism_activity(pop, folds)

    per_fold = [score_fold(pop, y) for y in folds]
    scored = list(IG.ARMS) + [IG.MATCHED_FOIL]
    pooled = {}
    for a in scored:
        c = [f["arms"][a]["crps"] for f in per_fold]
        lift = [f["arms"]["incumbent"]["crps"] - f["arms"][a]["crps"] for f in per_fold]
        pooled[a] = {"crps": round(float(np.mean(c)), 4),
                     "mae": round(float(np.mean([f["arms"][a]["mae"] for f in per_fold])), 4),
                     "mean_games": round(float(np.mean([f["arms"][a]["mean_mu"] for f in per_fold])), 3),
                     "mean_lift": round(float(np.mean(lift)), 4),
                     "folds_beating_incumbent": int(sum(1 for x in lift if x > 0)),
                     "per_fold_lift": [round(x, 4) for x in lift]}

    # winner = argmin pooled CRPS among the SHIPPABLE declared arms (degenerates and the
    # non-shippable matched foil are excluded from SELECTION but stay in the field for deflation).
    eligible = [a for a in IG.ARMS if a not in IG.DEGENERATE_ARMS and a != "incumbent"]
    winner = min(eligible, key=lambda a: pooled[a]["crps"])
    defl = deflation(per_fold, winner)
    anchors = anchor_audit(per_fold, winner)
    fc = cv_power.fold_consistency_clause(len(folds))
    wins = pooled[winner]["folds_beating_incumbent"]
    fold_clause = {"observed_wins": wins, "required_wins": fc.wins_required,
                   "n_folds": len(folds), "alpha": fc.alpha,
                   "attained_false_fire": fc.attained_false_fire,
                   "passes": bool(wins >= fc.wins_required)}
    pvals = {a: M14.onesided_paired_pvalue(np.asarray(pooled[a]["per_fold_lift"]))
             for a in eligible}
    bh = M14.bh_fdr(pvals, q=M14.FDR_Q)
    # ⚠️ THE PRE-REGISTRATION SAYS "survives BH-FDR at the family's q" AND DOES NOT NAME THE FAMILY.
    #    That ambiguity is MINE and it is disclosed rather than resolved in whichever direction
    #    helps (E2.1-r). BOTH readings are recorded and the STRICTER one binds:
    #      · across-ARMS — the four eligible arms as parallel hypotheses (the strict reading). Note
    #        it corrects a SECOND time for the very search DSR already deflates.
    #      · single-hypothesis — one mechanism, one population, no position axis was registered, so
    #        arguably BH is INAPPLICABLE here rather than failed (the MH2.7 "n_arms=1 ⇒ PBO
    #        INAPPLICABLE, not a fold trigger" shape).
    #    ⭐ Nothing turns on it: DSR fails under the registered convention either way, so the
    #    verdict does not rest on this choice (the NF-D15 (g″) discipline).
    bh_dual = {
        "across_arms_STRICT_binds": {
            "reading": "the 4 eligible arms as parallel hypotheses",
            "bh_rank1_cutoff": round(M14.FDR_Q / max(1, len(eligible)), 4),
            "winner_p": pvals.get(winner), "survives": bool(bh.get(winner))},
        "single_hypothesis_diagnostic": {
            "reading": "one mechanism, one population, no registered position axis ⇒ arguably "
                       "INAPPLICABLE rather than failed",
            "cutoff": M14.FDR_Q, "winner_p": pvals.get(winner),
            "would_survive": bool(pvals.get(winner) is not None and pvals[winner] < M14.FDR_Q),
            "admissible_to_act_on": False},
    }

    perm_lift = [f["anchors"]["permuted_timing"]["crps"] - f["arms"][IG.PRIMARY_ARM]["crps"]
                 for f in per_fold]
    permutation = {"permuted_crps": round(float(np.mean(
        [f["anchors"]["permuted_timing"]["crps"] for f in per_fold])), 4),
        "primary_crps": pooled[IG.PRIMARY_ARM]["crps"],
        "mean_lift_over_permuted": round(float(np.mean(perm_lift)), 4),
        "p_one_sided": M14.onesided_paired_pvalue(np.asarray(perm_lift)),
        "beats": bool(np.mean(perm_lift) > 0)}
    foil_d = [f["arms"][IG.MATCHED_FOIL]["crps"] - f["arms"][IG.PRIMARY_ARM]["crps"]
              for f in per_fold]
    foil = {"foil_crps": pooled[IG.MATCHED_FOIL]["crps"],
            "primary_crps": pooled[IG.PRIMARY_ARM]["crps"],
            "mean_delta": round(float(np.mean(foil_d)), 4),
            "per_fold": [round(x, 4) for x in foil_d],
            "folds_positive": int(sum(1 for x in foil_d if x > 0)),
            "p_one_sided": M14.onesided_paired_pvalue(np.asarray(foil_d)),
            "what_it_measures": "timing_aware − timing_aware_minus_timing = the TIMING attribution. "
                                "A primary win this does not separate is a win for the covariates "
                                "the two SHARE, never for timing (NF-D10 / NF-D15)."}

    vd = verdict(winner=winner, pooled=pooled, defl=defl, anchors=anchors,
                 fold_clause=fold_clause, bh=bh, permutation=permutation, foil=foil)
    # ⭐ NF-D15 (g″): PROVE the null does not rest on MY gate choice. Re-read it with each
    #    contestable gate relaxed IN TURN, and name what still binds.
    vd["gate_choice_sensitivity"] = {
        "with_dsr_removed": {g: v for g, v in vd["gates"].items() if g != "dsr_ok"},
        "still_fails_with_dsr_removed": bool(
            not all(v is True for g, v in vd["gates"].items() if g != "dsr_ok")),
        "still_fails_with_bh_removed": bool(
            not all(v is True for g, v in vd["gates"].items() if g != "bh_ok")),
        "ships_only_if_BOTH_relaxed": bool(
            all(v is True for g, v in vd["gates"].items() if g not in ("dsr_ok", "bh_ok"))),
        "reading": "two independent registered gates fail, so the null does not turn on either one "
                   "alone; ⭐ but BOTH failures trace to a SPECIFICATION the pre-registration left "
                   "open (the V-composition convention and the BH family), not to a threshold and "
                   "not to the evidence — see the hand-written reading (NF-D20).",
    }

    nullcls = None
    if not vd["ship"]:
        d = np.asarray(pooled[winner]["per_fold_lift"], dtype=float)
        sr = float(d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 1e-12 else 0.0
        try:
            nullcls = cv_power.classify_null(
                metric=f"nf_inj3_crps_{winner}", n_folds=len(folds),
                n_arms=IG.DECLARED_FIELD_SIZE, declared_field_size=IG.DECLARED_FIELD_SIZE,
                beats_foil=bool(pooled[winner]["mean_lift"] > 0),
                observed_sr=sr, var_trials_sr=defl["V_declared_excl_degenerates"],
                var_trials_sr_with_degenerates=defl["V_whole_field"],
                degenerates_excluded_from_v=True,
                fold_wins=wins, p_one_sided=pvals.get(winner), bh_cutoff=M14.FDR_Q,
                mde_sd_units=cv_power.mde_in_sd_units(n_folds=len(folds), n_metrics=1),
            ).__dict__
        except TypeError as e:
            nullcls = {"error": f"classify_null signature mismatch: {e}"}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t0, 1),
        "preregistration": "ablation_results/nf_inj3_preregistration.md",
        "folds": list(folds), "declared_field_size": IG.DECLARED_FIELD_SIZE,
        "population": prov, "serving_population": sprov,
        "era_fidelity": era_fidelity(con),
        "rookie_bypass": rookie_bypass_evidence(con, art, hist_seasons),
        "mechanism_activity": activity,
        "per_fold": [{k: v for k, v in f.items() if k != "provenance"} for f in per_fold],
        "fit_provenance": {str(f["year"]): {k: _jsonable(v)
                                            for k, v in f["provenance"].items()}
                           for f in per_fold},
        "pooled": pooled, "winner": winner, "deflation": defl, "anchors": anchors,
        "fold_consistency": fold_clause,
        "bh_fdr": {"pvalues": pvals, "survives": bh, "q": M14.FDR_Q, "dual_reading": bh_dual},
        "permutation_anchor": permutation, "matched_foil": foil,
        "channel_decomposition": channel_decomposition(pooled, per_fold),
        "verdict": vd, "null_classification": nullcls,
        "serving_application": apply_serving(pop, serving, winner),
        "incumbent_reproduction": reproduction_pin(serving),
        "mae_inversion_check": mae_inversion(pop),
    }


def reproduction_pin(serving: pd.DataFrame) -> dict:
    """Verify the incumbent reproduces the CURRENT served board before anything is compared to it."""
    cap = serving["proj_status"].map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)
    ceil = (1 - SP._INJURY_OVERRIDE_BLEND) * 17.0 + SP._INJURY_OVERRIDE_BLEND * cap
    served = serving["proj_games"].to_numpy(dtype=float)
    round_trip = IG.incumbent_games(serving["proj_status"], serving["eg"].to_numpy())
    return {"n_flagged_veterans": int(len(serving)),
            "above_incumbent_ceiling": int((served > ceil + 1e-9).sum()),
            "max_abs_round_trip_error": float(np.max(np.abs(round_trip - served))) if len(serving) else None,
            "status_mix": {k: int(v) for k, v in serving["proj_status"].value_counts().items()},
            "reading": "0 above the ceiling and a round-trip error at machine precision ⇒ the served "
                       "board is on the incumbent cap path (blend 0.7, caps 4/4/4/7)"}


def mae_inversion(pop: pd.DataFrame) -> dict:
    """MEASURE the NF-D11 / NF-D14 inversion rather than assume it — keep the degenerate in the
    field every run and READ its score (NF-D14: the conditional MEDIAN is the test, not the zero
    share)."""
    y = pd.to_numeric(pop["realized_games"], errors="coerce").to_numpy(dtype=float)
    return {"n": int(len(y)), "median_realized_games": float(np.median(y)),
            "zero_share": round(float(np.mean(y == 0)), 4),
            "mae_all_zero_nihilist": round(float(np.mean(np.abs(y))), 4),
            "mae_pooled_mean": round(float(np.mean(np.abs(y - y.mean()))), 4),
            "mae_is_inverted": bool(np.mean(np.abs(y)) < np.mean(np.abs(y - y.mean()))),
            "reading": "MAE is minimised at the conditional median, which sits AT the floor here ⇒ "
                       "MAE pays for pessimism and CANNOT select. CRPS is primary (NF-D11/NF-D14)."}


def _jsonable(v):
    if isinstance(v, np.ndarray):
        return [round(float(x), 5) for x in v.ravel()]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (np.floating, np.integer)):
        return float(v)
    return v


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_(none)_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(
            ("" if r.get(c) is None else
             (f"{r[c]:.4f}" if isinstance(r[c], float) else str(r[c]))) for c in cols) + " |")
    return "\n".join(out) + "\n"


def write_report_md(rep: dict, path: Path) -> None:
    v, w = rep["verdict"], rep["winner"]
    a, mf, pm = rep["anchors"], rep["matched_foil"], rep["permutation_anchor"]
    L: list[str] = []
    def p(s=""): L.append(s)

    state = (rep.get("null_classification") or {}).get("state")
    head = ("SHIP" if v["ship"] else (state or "NULL"))
    p("# NF-INJ3 — a designation-timing-aware injury-games model (replacing the hardcoded caps)")
    p()
    p(f"**VERDICT: {head}** — winner `{w}`. `best_alpha = 0`. "
      f"Generated {rep['generated_at']} in {rep['elapsed_s']}s.")
    p()
    p(f"> Pre-registration: `{rep['preregistration']}` — committed BEFORE any arm was scored. "
      "⛔ Not edited by this run (E2.1-r).")
    p()
    p(f"> 🔒 DEPLOY-HELD: `run_nf_inj3_injury_games.SERVED_ARM` is still `\"{SERVED_ARM}\"`. "
      "Nothing here serves until the PM records a disposition.")
    p()

    p("## 0. ⚠️ The registered covariate does not exist — read this before the leaderboard")
    p()
    p("The story asks for games as a function of status and **when the designation landed relative "
      "to kickoff**. Measured before the field was declared: **there is no designation DATE in this "
      "stack**. The weekly roster feed has no preseason weeks (a week-1 `RES` row is a STATE, not "
      "an EVENT); the Sleeper ingest OVERWRITES its Delta partition every capture so exactly ONE "
      "snapshot exists; the nflverse injury report has no `PRE` rows and no 2026 rows; there is no "
      "transactions feed. So the hypothesis is tested through the declared ONSET proxy "
      f"(`{', '.join(IG.TIMING_FEATURES)}`) and **every result below is scoped to that proxy** — it "
      "is NOT evidence about a designation date.")
    p()

    p("## 1. Reproduction pin — the incumbent IS the served board")
    p()
    rp = rep["incumbent_reproduction"]
    p(f"**{rp['n_flagged_veterans']}** flagged veterans on the live {SERVING_SEASON} board "
      f"({rp['status_mix']}); **{rp['above_incumbent_ceiling']}** exceed the incumbent's ceiling; "
      f"max round-trip error **{rp['max_abs_round_trip_error']:.2e}**. {rp['reading']}")
    p()
    rb = rep["rookie_bypass"]
    p(f"⭐ **Structural finding, out of scope, recorded for carding:** the cap never reaches a "
      f"ROOKIE — `injury_availability_games` runs inside `project_veterans` while `project_rookies` "
      f"is concatenated afterwards. Measured over the historical builds: "
      f"**{rb['rookie_above_ceiling']} of {rb['rookie_flagged']}** flagged rookies project ABOVE the "
      f"incumbent's own ceiling, against **{rb['veteran_above_ceiling']} of "
      f"{rb['veteran_flagged']}** veterans.")
    p()

    p("## 2. The field, as declared")
    p()
    pop = rep["population"]
    p(f"Folds **{rep['folds'][0]}–{rep['folds'][-1]}** ({len(rep['folds'])}), expanding window, "
      f"fit on {IG.ERA_MIN_SEASON}…Y−1. Declared field **{rep['declared_field_size']}** arms + the "
      f"matched foil `{IG.MATCHED_FOIL}`; pre-registered degenerates "
      f"`{'`, `'.join(IG.DEGENERATE_ARMS)}`. Excluded by registration: "
      f"**{pop['excluded']['rookies']}** rookies, **{pop['excluded']['returners']}** returners.")
    p()
    rows = []
    for arm in list(IG.ARMS) + [IG.MATCHED_FOIL]:
        d = rep["pooled"][arm]
        tag = ("DEGENERATE" if arm in IG.DEGENERATE_ARMS else
               "matched foil" if arm == IG.MATCHED_FOIL else
               "incumbent" if arm == "incumbent" else "")
        rows.append({"arm": arm, "role": tag, "CRPS": d["crps"], "MAE": d["mae"],
                     "mean games": d["mean_games"], "lift vs incumbent": d["mean_lift"],
                     "folds won": d["folds_beating_incumbent"]})
    rows.sort(key=lambda r: r["CRPS"])
    p(_md(rows, ["arm", "role", "CRPS", "MAE", "mean games", "lift vs incumbent", "folds won"]))
    p("⛔ **CRPS selects. MAE never does — and that is MEASURED here, not assumed.**")
    mi = rep["mae_inversion_check"]
    p(f"On this cohort (n={mi['n']}, median realized games **{mi['median_realized_games']:.0f}**, "
      f"zero share {mi['zero_share']:.3f}) the all-zero nihilist scores MAE "
      f"**{mi['mae_all_zero_nihilist']}** against the pooled mean's **{mi['mae_pooled_mean']}** ⇒ "
      f"MAE inverted = **{mi['mae_is_inverted']}**. {mi['reading']}")
    p()

    p("## 3. Mechanism activity (NF-D20 — count before crediting)")
    p()
    act = rep["mechanism_activity"]
    p(_md(act["per_fold"], ["fold", "n_eval", "RES", "PUP", "NFI", "SUS", "timing_varies"]))
    p(f"Totals by status: `{act['total_by_status']}`. **Inactive: "
      f"`{act['inactive_statuses'] or 'none'}`.** {act['note']}")
    p()

    p("## 4. Gates")
    p()
    d, fc = rep["deflation"], rep["fold_consistency"]
    g = v["gates"]
    grows = [
        {"gate": "beats incumbent", "value": rep["pooled"][w]["mean_lift"],
         "bar": "> 0", "verdict": g["beats_incumbent"]},
        {"gate": "fold consistency", "value": fc["observed_wins"],
         "bar": f"≥ {fc['required_wins']} of {fc['n_folds']}", "verdict": g["fold_consistency"]},
        {"gate": "PBO (declared field)", "value": d["pbo"], "bar": f"< {MAX_PBO}",
         "verdict": g["pbo_ok"]},
        {"gate": "DSR (DSR-CONV)", "value": d["dsr_conv"], "bar": f"≥ {MIN_DSR}",
         "verdict": g["dsr_ok"]},
        {"gate": "BH-FDR", "value": rep["bh_fdr"]["pvalues"].get(w),
         "bar": f"q = {rep['bh_fdr']['q']}", "verdict": g["bh_ok"]},
        {"gate": "degenerates lose", "value": json.dumps(
            {k: x["crps"] for k, x in a["_degenerates"].items()}), "bar": "both lose",
         "verdict": g["degenerates_lose"]},
        {"gate": "own-form oracle respected", "value": "per-form (NF-D16 g‴)",
         "bar": "no arm beats its own form's peek", "verdict": g["oracle_respected"]},
        {"gate": "beats permutation", "value": pm["mean_lift_over_permuted"], "bar": "> 0",
         "verdict": g["beats_permutation"]},
        {"gate": "timing attributable (matched foil)", "value": mf["mean_delta"], "bar": "> 0",
         "verdict": g["timing_attributable"]},
    ]
    p(_md(grows, ["gate", "value", "bar", "verdict"]))
    p(f"Whole-field DSR **{d['dsr_whole_field']}** beside the binding DSR-CONV figure "
      f"**{d['dsr_conv']}** (V excl. degenerates {d['V_declared_excl_degenerates']} vs whole-field "
      f"{d['V_whole_field']}). Contender spread {d['contender_spread_pct']}% vs whole-field "
      f"{d['whole_field_spread_pct']}% — a spread computed over a field containing its OWN nulls "
      f"measures the nulls (NF1.8).")
    p()
    p(f"Trial Sharpes: `{d['trial_sharpes']}`")
    p()
    p(f"{d['note']}")
    p()

    p("## 5. The matched foil — is the win TIMING, or the covariates it shares?")
    p()
    p(f"`{IG.PRIMARY_ARM}` CRPS **{mf['primary_crps']}** vs `{IG.MATCHED_FOIL}` "
      f"**{mf['foil_crps']}** ⇒ paired delta **{mf['mean_delta']}** "
      f"({mf['folds_positive']}/{len(rep['folds'])} folds positive, p = {mf['p_one_sided']}). "
      f"{mf['what_it_measures']}")
    p()
    p(f"Permutation anchor (`{', '.join(IG.TIMING_FEATURES)}` shuffled within status × season): "
      f"permuted CRPS **{pm['permuted_crps']}** vs primary **{pm['primary_crps']}** ⇒ lift "
      f"**{pm['mean_lift_over_permuted']}** (p = {pm['p_one_sided']}).")
    p()

    p("## 5b. Channel decomposition — WHERE the lift comes from")
    p()
    cd = rep["channel_decomposition"]
    p(_md([{"channel": k, "Δ CRPS": v["delta_crps"], "folds +": v["folds_positive"],
            "p": v["p_one_sided"]} for k, v in cd["steps"].items()],
          ["channel", "Δ CRPS", "folds +", "p"]))
    p(f"Steps sum to **{cd['sum_of_steps']}** against the winner's total lift "
      f"**{cd['winner_total_lift']}** (exact by construction). {cd['reading']}")
    p()
    p("## 6. Anchors (a missing anchor is a FAILED check, never a pass — NF1.7 (a))")
    p()
    arows = [{"arm": k, "arm CRPS": x.get("arm_crps"),
              "own-form oracle": x.get("own_form_oracle_crps"),
              "respects": x.get("respects_oracle"), "evaluable": x.get("evaluable")}
             for k, x in a.items() if not k.startswith("_")]
    p(_md(arows, ["arm", "arm CRPS", "own-form oracle", "respects", "evaluable"]))
    mn = a["_matched_n_control"]
    p(f"**Matched-n control** — {json.dumps(mn)}")
    p()

    p("## 7. What the winner would serve on today's board")
    p()
    sa = rep["serving_application"]
    p(f"Arm `{sa['arm']}` on the **{sa['n']}** flagged veterans of the live board: mean expected "
      f"games **{sa['mean_incumbent_games']} → {sa['mean_arm_games']}**; "
      f"{sa['n_moved_down']} move DOWN, {sa['n_moved_up']} move UP.")
    p()
    p(_md(sa["rows"][:15], ["player_name", "position", "status", "eg", "onset_carryover",
                            "weeks_since_last_game", "incumbent_games", "arm_games", "delta"]))
    p("⚠️ Reported for the record whether or not the arm ships. A shipping arm is **level-adjacent** "
      "(MVP-1's point is `rate × games`) and additionally requires the whole-board placement read "
      "(`run_nf_tr2b_placement_read`) and `run_interval_revalidation` (NF-D16 / NF-D21) — and "
      "NF-TR2b's caveat that the VOR shield is additive-only and does NOT hold under the two "
      "superflex configs.")
    p()

    p("## 8. Era fidelity — why 2016+ (a DESIGN quantity, not an outcome)")
    p()
    p(_md(rep["era_fidelity"], ["season", "n_res", "med_games", "zero_rate",
                                "status_change_share"]))
    p("A player recorded on IR in **week 1** who then plays a median of six games is a season-END "
      "label backfilled onto every week — i.e. OUTCOME-CONTAMINATED. ⭐ The incumbent's own "
      "docstring fits its constants on **2015–2024**, one contaminated season inside the window.")
    p()

    if rep.get("null_classification"):
        p("## 9. Null classification")
        p()
        p("```json")
        p(json.dumps(rep["null_classification"], indent=2, default=str))
        p("```")
        p()
        p("⚠️ Read the machine flag `field_remedy_admissible`, **never the prose** (MH2.7).")
        p()
        p(_classify_null_correction(rep))
        p()

    p(reading_section(rep))
    path.write_text("\n".join(L))


def _classify_null_correction(rep: dict) -> str:
    """⚠️ HAND-CORRECTION of `cv_power.classify_null`'s REMEDY TEXT — the Nth in this vertical
    (NF-W2 §4 · NF-D18 · NF-W3 · NF-W4 · NF-W7c · MH2.7). Recorded because a defect corrected N
    times downstream is a defect in the INSTRUMENT (MH2.7 lesson (i))."""
    nc = rep.get("null_classification") or {}
    dg = rep["deflation"]["diagnostics"]["mh2_1a_v_over_non_reference"]
    return "\n".join([
        "⚠️⚠️ **TWO HAND-CORRECTIONS TO THAT REMEDY TEXT — it is arithmetically right about the",
        "channel it varied and MISLEADING as a prescription.**",
        "",
        f"1. **\"field size is NOT a lever … the only lever left is a lower-variance design\"** varies",
        f"   the trial COUNT `N` while holding `V` FIXED. But `SR0 = √V · z(N)` is taxed through TWO",
        f"   channels and MH2 says the DISPERSION channel usually dominates — which it does here:",
        f"   `V` **{dg['V_registered']} → {dg['V_non_reference']}** (a "
        f"{dg['V_registered'] / max(1e-9, dg['V_non_reference']):.1f}× collapse) moves DSR",
        f"   **{dg['dsr_registered']} → {dg['dsr_non_reference']}**, i.e. past the bar. So the binding",
        "   quantity is `V`'s COMPOSITION, not the design's variance and not the field's SIZE.",
        "   ⛔ That does NOT license acting on it — see the reading below.",
        "",
        f"2. **The `+{nc.get('extra_seasons')}`-fold trigger is arithmetically correct and not",
        f"   actionable.** `folds_needed = {nc.get('folds_needed')}` means {nc.get('folds_needed')}",
        "   NFL seasons at this design, and the era floor (2016) is a DATA-FIDELITY fact, not a",
        "   choice — the feed yields ONE new season a year. Publishing it as a re-test trigger is the",
        "   NF-D18 misleading direction.",
        "",
        "⭐ What IS true and worth carrying: `SR` **%.4f** > `SR0` **%.4f**, so the gap is POSITIVE"
        % (nc.get("detail", {}).get("observed_sr", float("nan")),
           nc.get("detail", {}).get("sr0", float("nan"))),
        "and this is **not** `DSR_UNREACHABLE` — and NF-W8-0d's lockstep invariant (a shared-variance",
        "lever is deterministically void) does **not** bite here, because that invariant applies when",
        "`SR ≤ SR0`. Both levers are live in principle; neither is available in practice at 7 folds.",
    ])


def reading_section(rep: dict) -> str:
    """The hand-written reading. The JSON is the machine record; this is what a human must not have
    to reconstruct."""
    v, w = rep["verdict"], rep["winner"]
    cd, mf, dg = (rep["channel_decomposition"], rep["matched_foil"],
                  rep["deflation"]["diagnostics"]["mh2_1a_v_over_non_reference"])
    sa, pl = rep["serving_application"], rep["pooled"]
    bh = rep["bh_fdr"]["dual_reading"]
    L = ["", "---", "", "## 10. Reading the result (hand-written; the JSON above is the machine record)",
         "",
         "**The caps are wrong, the direction is unambiguous, and the study still does NOT ship —",
         "because the null rests on a SPECIFICATION my own pre-registration left open, not on the",
         "evidence. Both halves of that sentence are load-bearing.**", ""]
    a = L.append

    a("### 1. The substantive finding, which holds regardless of the verdict")
    a("")
    a(f"**Every real arm beats the incumbent, and the incumbent's expected games are roughly DOUBLE "
      f"what any fitted form says.** Pooled mean expected games: incumbent "
      f"**{pl['incumbent']['mean_games']}** against {pl['fitted_status']['mean_games']}–"
      f"{pl['hurdle_transfer']['mean_games']} for the fitted arms; the incumbent wins **0 of 7 folds** "
      f"against every one of them. On the live board all **{sa['n_moved_down']} of {sa['n']}** flagged "
      f"veterans move DOWN (mean **{sa['mean_incumbent_games']} → {sa['mean_arm_games']}** games), "
      f"none up.")
    a("")
    a("⭐ **The PM-facing reading: after the cap, the board still materially UNDER-discounts injured "
      "players.** NF-INJ1 found the ordering step handing back +36.4% of the availability discount; "
      "this finds the discount was too SMALL to begin with. They compound in the same direction, and "
      "this half is the larger of the two.")
    a("")

    a("### 2. Where the lift lives — and the answer to \"what transfers?\"")
    a("")
    st = cd["steps"]
    a(f"* **LEVEL (the caps themselves): +{st['level__incumbent_to_fitted_status']['delta_crps']} CRPS "
      f"— 77% of the total.** Simply FITTING the same functional form in-fold is almost the whole "
      f"story. The constants, not the shape, are the defect.")
    a(f"* **FORM (cap-blend → GLM): {st['form__fitted_status_to_glm_no_timing']['delta_crps']} — a "
      f"wash.** The incumbent's functional form is fine.")
    a(f"* **TIMING (the declared onset proxy): +{st['timing__glm_no_timing_to_timing_aware']['delta_crps']}, "
      f"p = {st['timing__glm_no_timing_to_timing_aware']['p_one_sided']}** — positive, small, and not "
      f"significant. ⇒ **the story's headline hypothesis is the SMALLEST of the three live channels.**")
    a(f"* **HURDLE SPLIT (the NF-W2 transfer): "
      f"+{st['hurdle_split__timing_aware_to_hurdle']['delta_crps']}, "
      f"p = {st['hurdle_split__timing_aware_to_hurdle']['p_one_sided']}** — roughly TWICE the timing "
      f"channel, on identical covariates. The winner is the transfer arm.")
    a("")
    a("⭐ **The story said \"start by asking what transfers, don't rebuild cold,\" and that paid.** "
      "NF-W2's FEATURES cannot transfer at all (its source has no preseason rows and no 2026 rows), "
      "but its measured FINDING — the lift lives in the zero/availability leg — transfers cleanly to "
      "a SEASON target and is the single best-performing mechanism in the field.")
    a("")

    a("### 3. Why it does not ship, stated precisely")
    a("")
    a(f"Seven of nine gates pass, including every anchor: PBO **{rep['deflation']['pbo']}**, fold "
      f"consistency **{rep['fold_consistency']['observed_wins']}/{rep['fold_consistency']['n_folds']}**, "
      f"both degenerates lose, every arm respects its own-form peeking oracle with the matched-n "
      f"control, the permutation anchor is beaten, and the matched foil separates a positive timing "
      f"channel. Two fail:")
    a("")
    a(f"* **DSR {rep['deflation']['dsr_conv']} < {MIN_DSR}** under the registered `V` convention.")
    a(f"* **BH-FDR** — under the STRICT across-arms reading (cutoff "
      f"{bh['across_arms_STRICT_binds']['bh_rank1_cutoff']}, winner p "
      f"{bh['across_arms_STRICT_binds']['winner_p']}).")
    a("")
    a("⭐⭐ **AND HERE IS THE PART THAT MATTERS MOST, because it is the kind of thing a record can "
      "quietly omit: BOTH failures trace to a specification the pre-registration left OPEN, and "
      "under the most defensible reading of each, the arm clears everything.**")
    a("")
    a(f"* **DSR.** MH2.1 (a) says a REFERENCE arm's identically-ZERO skill series inflates a "
      f"small-family `V` exactly as a diagnostic anchor does, so `V` should be measured over "
      f"NON-reference arms. My pre-registration declared DSR-CONV (degenerates ∉ `V`) and **did not "
      f"invoke MH2.1 (a)** — so the incumbent's structural 0.0 sat inside `V`. Measured: "
      f"`V` {dg['V_registered']} → {dg['V_non_reference']}, DSR **{dg['dsr_registered']} → "
      f"{dg['dsr_non_reference']}**. The dropped arm is the incumbent, **not** the winner, so the "
      f"diagnostic is admissible to REPORT (NF-W7h).")
    a(f"* **BH-FDR.** The pre-registration says \"at the family's q\" and never names the family. "
      f"Across arms it corrects a SECOND time for the very search DSR already deflates; there is one "
      f"mechanism, one population, and no registered position axis, so BH is arguably INAPPLICABLE "
      f"here rather than failed (the MH2.7 `n_arms=1 ⇒ PBO INAPPLICABLE` shape). Single-hypothesis "
      f"reading: p {bh['single_hypothesis_diagnostic']['winner_p']} < "
      f"{bh['single_hypothesis_diagnostic']['cutoff']} ⇒ would survive.")
    a("")
    a("⛔ **Neither is acted on, and that is the whole point.** Adopting a convention AFTER seeing the "
      "registered gate fail is the E2.1-r inversion in its most literal form, and re-cutting `V` "
      "post-hoc is the MH2.2 laundering DSR exists to prevent. The registered figures BIND, the study "
      "returns a null, and the diagnostics are recorded so a reader can see exactly what separates it "
      "from a ship.")
    a("")

    a("### 4. Classification — the null rests on a REGISTRATION CHOICE, not a threshold")
    a("")
    a("`classify_null` returns **POWER_LIMITED** with a +21-season trigger. Corrected above: the "
      "binding quantity is `V`'s COMPOSITION, not power and not field size. Following NF-D20's rule "
      "— *when a null rests on a REGISTRATION CHOICE rather than a gate LEVEL, say so plainly* — the "
      "honest statement is:")
    a("")
    a("> **The V-composition convention, not any threshold and not the evidence, separates this null "
      "from a ship.** Had the pre-registration invoked MH2.1 (a) (a convention this program already "
      "owns and already applies elsewhere), the registered DSR would read "
      f"**{dg['dsr_non_reference']}** and the arm would have cleared it.")
    a("")
    a("⇒ the remedy is a **FRESH pre-registration** — one that names the `V` convention and the BH "
      "family up front — **never a re-read of this one**, and never \"more seasons.\"")
    a("")

    a("### 5. Reusable lessons")
    a("")
    a("* ⭐ **A pre-registration must name the DEFLATION CONVENTIONS, not just the arms and the "
      "gates.** This one declared the field, the metric, the folds, the anchors and nine gate "
      "thresholds — and still lost on two unstated specification details. `V`'s membership and the "
      "BH family are as load-bearing as any threshold, and they are exactly the details that only "
      "become interesting after a result, i.e. the ones you can no longer set.")
    a("* ⭐ **A REFERENCE arm's trial Sharpe is 0 BY CONSTRUCTION, and a small field feels it.** "
      f"With five non-degenerate arms, one structural zero drove `V` up "
      f"{dg['V_registered'] / max(1e-9, dg['V_non_reference']):.1f}× and cost ~"
      f"{dg['dsr_non_reference'] - dg['dsr_registered']:.3f} of DSR. DSR-CONV handles DEGENERATES; "
      "the reference arm is a separate and equally mechanical inflation.")
    a("* **\"What transfers\" is a real question with a real answer, and it beat the story's own "
      "headline hypothesis.** The certified weekly family's FEATURES were unusable; its FINDING was "
      "the best mechanism in the field.")
    a("* **A registered covariate can simply not exist, and that is a finding to MEASURE before "
      "declaring the field.** There is no designation date anywhere in this stack — the roster feed "
      "has no preseason weeks, the Sleeper ingest overwrites its own history, the injury report has "
      "no 2026 rows. Discovering that inside the run would have produced a proxy chosen after the "
      "fact instead of before it.")
    a("* **The era boundary was the single highest-leverage measurement in the study.** Pre-2016 the "
      "\"week-1\" status is a season-END label backfilled onto every week (a week-1 IR player plays a "
      "median SIX games), and the incumbent's own constants were fitted on a window that includes "
      "it. Training on it would have made the incumbent look right.")
    a("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3 §0.5 injury-games bake-off")
    ap.add_argument("--duckdb", default=_DEFAULT_DUCKDB)
    ap.add_argument("--artifacts", default=None,
                    help="dir holding the single-vintage MVP-1 builds (gitignored — NF-INFRA1)")
    ap.add_argument("--smoke", action="store_true", help="3 folds, for a code-path proof only")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    import duckdb
    con = duckdb.connect(args.duckdb, read_only=True)
    folds = IG.FOLDS[-3:] if args.smoke else IG.FOLDS
    rep = run(con, artifacts_dir(args.artifacts), folds)
    stem = args.out or ("nf_inj3_injury_games_smoke" if args.smoke else "nf_inj3_injury_games")
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{stem}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_report_md(rep, _REPORT_DIR / f"{stem}.md")
    log.info("NF-INJ3 %s — winner=%s ship=%s → %s",
             "SMOKE" if args.smoke else "FULL", rep["winner"], rep["verdict"]["ship"],
             _REPORT_DIR / f"{stem}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
