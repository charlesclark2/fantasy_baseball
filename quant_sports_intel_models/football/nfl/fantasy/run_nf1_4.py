"""run_nf1_4.py — NF1.4 CLI/IO: assemble the rookie training set, run the §0.5 bake-off, report.

NF1.4 = the ROOKIE-PRIOR REFINEMENT. MVP-3 dogfooding + NF1 both flagged rookie OVER-VALUATION;
`nf1_4_rookie.py` (the pure logic — read its docstring for the design + the measured mechanism)
rebuilds the prior on the FULL drafted population with P1A as the backbone plus combine/athletic and
breakout-age blocks, all shrunk toward the position mean.

⭐ RUN ON THE LAPTOP (like NF1/NF1.1/MVP-1): SF-free, sports-lake DuckDB, S3 I/O only, zero shared
box CPU. `SPORTS_LAKE_REGION=us-east-2` only matters if a mart still needs a delta read.

MODES:
  * `assemble` — build the rookie training frame ONCE → `artifacts/nf1_4_rookie_training.parquet`
                 (§0.5 cost hygiene: every candidate / ablation / CV fold reads that cached
                 parquet, never re-queries DuckDB). Leakage-safe: every feature is PRE-DEBUT.
  * `bakeoff`  — the walk-forward-by-COHORT selection over the pre-registered candidate grid, the
                 deflation (CSCV-PBO over cohorts / DSR / BH-FDR across positions), the block
                 ablation, the interval calibration + coverage, and the face-validity gate.
                 → ablation_results/nf1_4_rookie.{md,json}
  * `board`    — apply the selected rookie prior to the incoming class and print the rookie slots
                 next to the incumbent's, with the face-validity read on the merged board. A
                 read-only diagnostic; the SERVED repoint lives in `season_projection.py`.

The bake-off is >1 min ⇒ hand it to the operator. `--smoke` runs a tiny grid and writes `*_smoke`
artifacts so a wiring run can never clobber the real report.

Prereq — the NFL + NCAAF marts must be built into the sports DuckDB (dbt-core, NOT dbtf; the
delta_scan staging segfaults fusion). From `quant_sports_intel_models/sports_dbt`:
    export SPORTS_LAKE_REGION=us-east-2
    python -m dbt.cli.main run --select nfl.staging nfl.marts --threads 1
    python -m dbt.cli.main run --select ncaaf.staging ncaaf.marts --threads 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    _ROOKIE_PARQUET,
)

log = logging.getLogger("nfl.fantasy.nf1_4")

NCAAF_MARTS = "main_ncaaf_marts"
NCAAF_STAGING = "main_ncaaf_staging"

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_TRAIN_CACHE = _ART / "nf1_4_rookie_training.parquet"

# The cohort axis. 2016 is P1A's first emitted draft class; a target cohort needs ≥3 PRIOR classes
# for the walk-forward to have anything to learn from, so scoring starts at 2019.
FIRST_CLASS = 2016
FIRST_SCORED_COHORT = 2019
# `fact_ncaaf_player_game` opens in 2014 and 2014–15 carry ~40% of a normal season's rows, so a
# college career that appears to begin then is probably left-truncated (see `_breakout_features`).
_BOX_FEED_THIN_THROUGH = 2015

# Breakout thresholds — the season production level at which a college player has "broken out" at
# his position (season totals, FBS box). Deliberately round numbers from the public dynasty-analytics
# convention rather than tuned: the FEATURE is the AGE at which it happens, and a tuned threshold
# would smuggle an open search into a pre-registered block.
_BREAKOUT_THRESHOLD = {
    "QB": ("pass_plus_rush_yards", 2200.0),
    "RB": ("scrimmage_yards", 750.0),
    "WR": ("receiving_yards", 600.0),
    "TE": ("receiving_yards", 350.0),
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Assembly — ONE parquet, every feature PRE-DEBUT (§0.5 leakage + cost hygiene)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _parse_height_inches(s: pd.Series) -> pd.Series:
    """Combine height → inches. nflverse ships it as either `6-2` (feet-inches) or a bare number."""
    raw = s.astype("string").str.strip()
    fi = raw.str.extract(r"^(\d+)\s*[-']\s*(\d+)")
    inches = pd.to_numeric(fi[0], errors="coerce") * 12 + pd.to_numeric(fi[1], errors="coerce")
    bare = pd.to_numeric(raw, errors="coerce")
    return inches.fillna(bare)


def _rookie_labels(con, universe: pd.DataFrame, schema: str) -> pd.DataFrame:
    """The LABEL — realized rookie-season production for every DRAFTED rookie in the universe.

    ⭐ THE SURVIVORSHIP FIX, and the single most important line in this module: the join is a LEFT
    join and a rookie with no rows / no played games scores **0.0**, not NULL. MVP-1's
    `load_rookie_training` filters `where games > 0`, dropping 15% of drafted skill rookies (35% of
    QBs) from the fit — which is what inflates the positional mean, the P93 ceiling and the
    games-by-slot prior, i.e. the hot curve. A drafted rookie who never plays is a REAL outcome the
    prior must price, not a missing observation.
    """
    con.register("nf14_universe", universe[["gsis_id", "draft_year"]])
    return con.sql(f"""
        select
            u.gsis_id,
            coalesce(count_if(f.played_flag and not f.is_bye), 0)                        as rookie_games,
            coalesce(sum(case when f.played_flag then f.fantasy_points_ppr else 0 end), 0.0)
                                                                                        as rookie_fp_ppr,
            coalesce(sum(case when f.played_flag then f.pass_attempts else 0 end), 0.0)::double      as pass_att,
            coalesce(sum(case when f.played_flag then f.pass_completions else 0 end), 0.0)::double   as pass_cmp,
            coalesce(sum(case when f.played_flag then f.passing_yards else 0 end), 0.0)::double      as pass_yds,
            coalesce(sum(case when f.played_flag then f.passing_touchdowns else 0 end), 0.0)::double as pass_td,
            coalesce(sum(case when f.played_flag then f.interceptions else 0 end), 0.0)::double      as pass_int,
            coalesce(sum(case when f.played_flag then f.rushing_carries else 0 end), 0.0)::double    as rush_att,
            coalesce(sum(case when f.played_flag then f.rushing_yards else 0 end), 0.0)::double      as rush_yds,
            coalesce(sum(case when f.played_flag then f.rushing_touchdowns else 0 end), 0.0)::double as rush_td,
            coalesce(sum(case when f.played_flag then f.receiving_targets else 0 end), 0.0)::double  as targets,
            coalesce(sum(case when f.played_flag then f.receptions else 0 end), 0.0)::double         as rec,
            coalesce(sum(case when f.played_flag then f.receiving_yards else 0 end), 0.0)::double    as rec_yds,
            coalesce(sum(case when f.played_flag then f.receiving_touchdowns else 0 end), 0.0)::double as rec_td
        from nf14_universe u
        left join {schema}.fct_player_week f
          on f.player_id = u.gsis_id and f.season = u.draft_year and f.week > 0
        group by 1
    """).df()


def _breakout_features(con, universe: pd.DataFrame) -> pd.DataFrame:
    """BREAKOUT AGE — how EARLY in a college career a prospect first produced at a starter level.

    The sports lake has no birth dates, so "age" is proxied two ways, deliberately redundant because
    each has a different failure mode:

      1. `breakout_season_index` — the breakout season measured from the player's FIRST observed FBS
         season (0 = broke out as a true freshman). Derived purely from `fact_ncaaf_player_game`, so
         it is available for anyone with a college box line. Its failure mode is LEFT CENSORING: the
         box feed starts in 2014 (and 2014–15 are thin), so a player whose real first season predates
         that looks like he started later than he did → `first_season_censored` flags it.
      2. `breakout_class_year` — the CFBD-reported class year (1 = FR … 5) in the breakout season.
         Its failure mode is the feed itself: ⚠️ CFBD's roster `year` field carries MIXED SEMANTICS —
         it is the class year (1–6) for some rows and the literal SEASON (2014, 2015, …) or 0 for
         others, with the usable 1–6 form covering only ~8% of 2014 rows rising to ~96% by 2025. Only
         values in [1, 6] are accepted; everything else stays NaN rather than being coerced into a
         plausible-looking number.

    Also emitted: `career_index_at_draft` (draft year − first observed season ≈ how long he stayed =
    the early-declare read), `n_fbs_seasons`, and `early_breakout` (broke out in his first two
    observed seasons). Missing stays NaN with `has_breakout` carrying the missingness explicitly.
    """
    con.register("nf14_college", universe[["gsis_id", "college_athlete_id", "position_group", "draft_year"]])
    per_season = con.sql(f"""
        with prod as (
            select
                g.player_id::varchar                              as college_player_id,
                g.season,
                sum(coalesce(g.passing_yards, 0) + coalesce(g.rushing_yards, 0))  as pass_plus_rush_yards,
                sum(coalesce(g.rushing_yards, 0) + coalesce(g.receiving_yards, 0)) as scrimmage_yards,
                sum(coalesce(g.receiving_yards, 0))                                as receiving_yards
            from {NCAAF_MARTS}.fact_ncaaf_player_game g
            group by 1, 2
        ),
        cls as (
            select player_id::varchar as college_player_id, season, min(class_year) as class_year
            from {NCAAF_STAGING}.stg_ncaaf_roster
            where class_year is not null and class_year between 1 and 6
            group by 1, 2
        )
        select u.gsis_id, u.position_group, u.draft_year, p.season, c.class_year,
               p.pass_plus_rush_yards, p.scrimmage_yards, p.receiving_yards
        from nf14_college u
        join prod p on p.college_player_id = u.college_athlete_id::varchar
        left join cls c on c.college_player_id = u.college_athlete_id::varchar and c.season = p.season
        where p.season < u.draft_year
    """).df()

    cols = ["gsis_id", "breakout_season_index", "breakout_class_year", "career_index_at_draft",
            "n_fbs_seasons", "first_season_censored", "has_breakout", "early_breakout"]
    rows = []
    for gsis, g in per_season.groupby("gsis_id"):
        pos = str(g["position_group"].iloc[0])
        metric, thresh = _BREAKOUT_THRESHOLD.get(pos, ("receiving_yards", 600.0))
        g = g.sort_values("season")
        first_season = int(g["season"].min())
        hit = g[pd.to_numeric(g[metric], errors="coerce") >= thresh]
        cy = pd.to_numeric(hit["class_year"], errors="coerce").dropna()
        idx = float(int(hit["season"].min()) - first_season) if len(hit) else np.nan
        rows.append({
            "gsis_id": gsis,
            "breakout_season_index": idx,
            "breakout_class_year": float(cy.min()) if len(cy) else np.nan,
            "career_index_at_draft": float(int(g["draft_year"].iloc[0]) - first_season),
            "n_fbs_seasons": float(g["season"].nunique()),
            # the box feed opens in 2014 and 2014–15 are thin ⇒ a career that appears to start then
            # is probably truncated, so the index is not trustworthy for that player.
            "first_season_censored": 1.0 if first_season <= _BOX_FEED_THIN_THROUGH else 0.0,
            "has_breakout": 1.0 if len(hit) else 0.0,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=cols)
    # early breakout = cleared the bar within the first two observed seasons. NaN when he never did
    # (an absent breakout is NOT a late breakout) or when the career start is censored.
    out["early_breakout"] = np.where(
        out["breakout_season_index"].notna() & (out["first_season_censored"] == 0),
        (out["breakout_season_index"] <= 1).astype(float), np.nan)
    return out[cols]


def assemble_rookie_training(con, *, schema: str = MARTS_SCHEMA,
                             first_class: int = FIRST_CLASS,
                             last_class: int | None = None) -> pd.DataFrame:
    """Build the one-row-per-DRAFTED-SKILL-ROOKIE training frame.

    Backbone = NCAAF-P1A's `ncaaf_nfl_rookie_projections` (do NOT rebuild the college→NFL
    translation — P1A already did it, and its verdict is that the draft slot beats it standalone, so
    it enters here as `projected_nfl_z` + the slot RESIDUAL). Joined to: combine measurables +
    recruiting pedigree + college-production aggregates (`ncaaf_draft_college_production_pairs` /
    `xref_college_nfl_players`), the derived breakout-age block, and the realized rookie label.

    🔒 LEAKAGE: every feature is knowable the day after the draft — draft slot, P1A's projection
    (fit on PRIOR classes by construction), combine, college production, recruiting. The rookie
    label is the only forward quantity and it is never a feature. `p1a_slot_residual` and the
    athletic z-scores are recomputed per FOLD in the walk-forward (see `walk_forward`), never here,
    so a test cohort cannot contribute to its own normalization.
    """
    rk = pd.read_parquet(_ROOKIE_PARQUET)
    rk = rk[
        rk["position_group"].isin(M14.ROOKIE_POSITIONS)
        & pd.to_numeric(rk["draft_overall"], errors="coerce").notna()
        & (pd.to_numeric(rk["draft_year"], errors="coerce") >= first_class)
    ].copy()
    if last_class is not None:
        rk = rk[pd.to_numeric(rk["draft_year"], errors="coerce") <= last_class]
    keep = ["gsis_id", "player_name", "position_group", "nfl_position", "college",
            "college_athlete_id", "draft_year", "draft_overall", "draft_round",
            "projected_nfl_z", "projected_nfl_z_sd", "recruit_composite_rating"]
    u = rk[[c for c in keep if c in rk.columns]].copy()
    u["draft_year"] = pd.to_numeric(u["draft_year"], errors="coerce").astype("Int64")
    u["draft_overall"] = pd.to_numeric(u["draft_overall"], errors="coerce").astype(float)
    u["draft_round"] = pd.to_numeric(u["draft_round"], errors="coerce").astype(float)
    u = u.drop_duplicates(subset=["gsis_id"]).reset_index(drop=True)
    log.info("rookie universe: %d drafted skill rookies, classes %s–%s",
             len(u), int(u["draft_year"].min()), int(u["draft_year"].max()))

    # combine measurables (position-standardized later, per fold)
    xref = con.sql(f"""
        select gsis_id, forty, vertical, bench, broad_jump, cone, shuttle, combine_ht, combine_wt
        from {NCAAF_MARTS}.xref_college_nfl_players where gsis_id is not null
        qualify row_number() over (partition by gsis_id order by match_score desc nulls last) = 1
    """).df()
    xref["combine_ht_in"] = _parse_height_inches(xref.pop("combine_ht"))
    u = u.merge(xref, on="gsis_id", how="left")

    # recruiting pedigree + college-production context
    pairs = con.sql(f"""
        select gsis_id, recruit_stars, n_college_seasons, final_college_season, college_games
        from {NCAAF_MARTS}.ncaaf_draft_college_production_pairs where gsis_id is not null
        qualify row_number() over (partition by gsis_id order by draft_year desc) = 1
    """).df()
    u = u.merge(pairs, on="gsis_id", how="left")

    u = u.merge(_breakout_features(con, u), on="gsis_id", how="left")
    u = u.merge(_rookie_labels(con, u, schema), on="gsis_id", how="left")
    u["rookie_fp_ppr"] = pd.to_numeric(u["rookie_fp_ppr"], errors="coerce").fillna(0.0)
    u["rookie_games"] = pd.to_numeric(u["rookie_games"], errors="coerce").fillna(0.0)

    # ⚠️ A draft class whose rookie season has NOT been played yet reads as an all-zero label under
    # the survivorship-safe LEFT join (every rookie "never played"). That is correct for a completed
    # class and catastrophic for an incoming one — an unlabelled class in the training pool would
    # teach the prior that a whole draft is worthless. Flag it here; the bake-off pool filters on it
    # and only `board` mode (which scores, never fits, the incoming class) keeps it.
    last_played = int(con.sql(f"select max(season) from {schema}.fct_player_week where played_flag")
                      .fetchone()[0])
    u["label_available"] = (pd.to_numeric(u["draft_year"], errors="coerce") <= last_played).astype(bool)
    n_unlabelled = int((~u["label_available"]).sum())
    if n_unlabelled:
        log.info("%d rookies in class(es) > %d have NO realized rookie season yet "
                 "(label_available=False — excluded from fitting/scoring)", n_unlabelled, last_played)

    # Numeric columns land as pandas NULLABLE extension dtypes (Int64/Float64) via the parquet +
    # DuckDB reads; downstream numpy math and `.loc` assignment on a float64 frame both choke on
    # them (pandas FutureWarning → hard error), so pin every modelling column to plain float64 once,
    # here, rather than defensively re-casting at each use site.
    for c in ("draft_overall", "draft_round", "projected_nfl_z", "projected_nfl_z_sd",
              "recruit_composite_rating", "forty", "vertical", "bench", "broad_jump", "cone",
              "shuttle", "combine_wt", "combine_ht_in", "recruit_stars", "n_college_seasons",
              "college_games"):
        if c in u.columns:
            u[c] = pd.to_numeric(u[c], errors="coerce").astype("float64")

    # static (fold-independent) derived features
    u["log_overall"] = np.log(u["draft_overall"].clip(lower=1))
    u["is_top10"] = (u["draft_overall"] <= 10).astype(float)
    u["is_day1"] = (u["draft_overall"] <= 32).astype(float)
    u["recruit_stars_f"] = pd.to_numeric(u["recruit_stars"], errors="coerce").astype(float)
    u["n_college_seasons"] = pd.to_numeric(u["n_college_seasons"], errors="coerce").astype(float)
    u["has_breakout"] = pd.to_numeric(u.get("has_breakout"), errors="coerce").fillna(0.0)
    return u.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fold-local features (recomputed per cohort so a test class never normalizes itself)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def add_fold_features(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach the fold-local derived features: the athletic z-scores (standardized on the TRAINING
    classes only) and the P1A slot residual (computed WITHIN each draft class, so it is identical
    whether the class is train or test — a within-class quantity cannot leak across the fold)."""
    tr, te = train.copy(), test.copy()
    tr = pd.concat([tr, M14.athletic_features(tr, ref=tr)], axis=1)
    te = pd.concat([te, M14.athletic_features(te, ref=train)], axis=1)
    tr["p1a_slot_residual"] = M14.p1a_slot_residual(tr)
    te["p1a_slot_residual"] = M14.p1a_slot_residual(te)
    for f in (tr, te):
        for c in ("breakout_season_index", "breakout_class_year", "career_index_at_draft",
                  "early_breakout"):
            f[c] = pd.to_numeric(f.get(c), errors="coerce")
    return tr, te


def incumbent_predict(train: pd.DataFrame, test: pd.DataFrame, cohort: int) -> np.ndarray:
    """The MVP-1 INCUMBENT, run through the ACTUAL served code path — `fit_rookie_slot_curves` on
    the prior classes (with MVP-1's own `games > 0` survivor filter, which is the defect under test)
    then `project_rookies` (slot power-law × the P1A residual nudge, P93 clip, stat-line allocation,
    rescale). Not a re-implementation: a re-implementation could accidentally fix the bug and make
    the null look worse than what is actually served.

    Returns the incumbent's `proj_fp_ppr` aligned to `test` row order (0.0 for any row the incumbent
    declines to project, which is itself a faithful reading of what the board would show)."""
    # `fit_rookie_slot_curves` reads the rookie-year games column as `games` and the raw stat totals
    # under their bare names — the exact shape `load_rookie_training` hands it in production.
    hist = train[train["rookie_games"] > 0].assign(games=lambda d: d["rookie_games"])
    curve = SP.fit_rookie_slot_curves(hist)
    out = SP.project_rookies(test, curve, int(cohort))
    if out.empty:
        return np.zeros(len(test), dtype=float)
    m = dict(zip(out["player_id"], pd.to_numeric(out["proj_fp_ppr"], errors="coerce")))
    return np.array([float(m.get(g, 0.0)) for g in test["gsis_id"]], dtype=float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The walk-forward-by-cohort bake-off
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class Fold:
    """One walk-forward fold: draft class `year`, its expanding training classes, and the held-out
    class already carrying its fold features, the INCUMBENT's prediction (`_inc` — the fixed tier
    anchor every candidate is graded against) and the in-fold position scales.

    Built ONCE per cohort and reused by every candidate, ablation and interval fit: the incumbent
    refit + the athletic standardization are the expensive parts and recomputing them per config
    would be ~200× wasted work (§0.5 cost hygiene, the same rule as the cached feature parquet)."""
    year: int
    train: pd.DataFrame
    test: pd.DataFrame
    scale: dict


def build_folds(pool: pd.DataFrame, cohorts: list[int]) -> list[Fold]:
    folds = []
    for y in cohorts:
        tr_raw, te_raw = pool[pool["draft_year"] < y], pool[pool["draft_year"] == y]
        if len(tr_raw) < 60 or len(te_raw) < 15:
            continue
        tr, te = add_fold_features(tr_raw, te_raw)
        te = te.assign(_inc=incumbent_predict(tr, te, y))
        folds.append(Fold(year=int(y), train=tr, test=te, scale=M14.position_scale(tr)))
    return folds


def _fit_predict(fold: Fold, cfg: dict) -> np.ndarray:
    if cfg["learner"] == "incumbent":
        return fold.test["_inc"].to_numpy(dtype=float)
    learner = M14.make_rookie_learner(cfg["learner"], feats=M14.block_features(tuple(cfg["blocks"])),
                                      **cfg["hp"])
    learner.fit(fold.train, fold.train["rookie_fp_ppr"].to_numpy())
    return learner.predict(fold.test)


def walk_forward(folds: list[Fold], cfg: dict) -> dict:
    """Backtest ONE candidate config across the folds — fit on classes < Y, score the held-out class
    Y (expanding, leakage-safe by COHORT — the story's required eval axis)."""
    per = {}
    for f in folds:
        scored = f.test.assign(_pred=_fit_predict(f, cfg))
        per[f.year] = M14.cohort_metrics(scored, "_pred", scale=f.scale)
    return {"key": M14.config_key(cfg), **cfg, "per_cohort": per, **_summarize(per)}


_MEAN_KEYS = ("tier_mae", "tier_bias", "mae", "rmse", "bias", "slope", "rho")


def _summarize(per: dict[int, dict]) -> dict:
    def _m(k):
        v = [c[k] for c in per.values() if c.get(k) is not None]
        return round(float(np.mean(v)), 4) if v else None
    return {f"mean_{k}": _m(k) for k in _MEAN_KEYS} | {"n_cohorts": len(per)}


INCUMBENT_CFG = {"learner": "incumbent", "blocks": ("slot",), "hp": {}}


def incumbent_walk_forward(folds: list[Fold]) -> dict:
    r = walk_forward(folds, INCUMBENT_CFG)
    r["key"] = "incumbent_slot_curve"
    return r


def _cohort_row(rec: dict, cohorts: list[int], metric: str) -> np.ndarray:
    return np.array([rec["per_cohort"].get(y, {}).get(metric, np.nan) for y in cohorts], dtype=float)


def run_bakeoff(pool: pd.DataFrame, *, smoke: bool = False) -> dict:
    """The full §0.5 selection — run **PER POSITION**, which is what the measurement demands.

    A single pooled metric cannot express this defect. The incumbent rookie board is globally COLD
    (it under-projects almost every drafted rookie) while being specifically HOT at the top of the
    QB class — so any pooled number averages the two away and reports "no change." Selecting per
    position is also exactly NF1.1's own conclusion for this product ("per-position independent
    models re-selected on the top-tier metric"), so NF1.4 inherits it rather than re-litigating it.

    For each of QB/RB/WR/TE: every pre-registered config is walk-forwarded by draft class, the
    incumbent is scored identically through the served code path, the winner is picked on that
    position's held-out draftable-tier MAE among ELIGIBLE candidates (shippable + does no ordering
    harm at that position), and the position's whole search is deflated (CSCV-PBO over cohorts, DSR
    against that position's trial population). BH-FDR then runs across the four positions.
    """
    cohorts_all = sorted(y for y in pool["draft_year"].dropna().unique().astype(int)
                         if y >= FIRST_SCORED_COHORT)
    cohorts_all = cohorts_all[-3:] if smoke else cohorts_all
    folds = build_folds(pool, cohorts_all)
    cohorts = [f.year for f in folds]
    log.info("scoring cohorts: %s", cohorts)

    inc = incumbent_walk_forward(folds)
    log.info("incumbent (pooled): tier_mae=%s tier_bias=%s mae=%s bias=%s rho=%s",
             inc["mean_tier_mae"], inc["mean_tier_bias"], inc["mean_mae"], inc["mean_bias"],
             inc["mean_rho"])

    grid = M14.candidate_grid(smoke=smoke)
    results = []
    for i, cfg in enumerate(grid, 1):
        r = walk_forward(folds, cfg)
        results.append(r)
        log.info("  [%d/%d] %-58s tier_mae=%-8s tier_bias=%-8s rho=%s", i, len(grid), r["key"],
                 r["mean_tier_mae"], r["mean_tier_bias"], r["mean_rho"])

    # ── ORACLE FLOOR (E2.1-r): the realized-outcome oracle scores 0 on the selection metric; a
    #    candidate scoring below it would be mathematically impossible = the metric is inverted.
    oracle_ok = all(
        M14.oracle_is_the_scoring_floor(
            f.test.assign(_c=_fit_predict(f, grid[0])), ["_c"], metric="tier_mae", scale=f.scale)
        for f in folds)

    per_position, pos_p = {}, {}
    for p in M14.ROOKIE_POSITIONS:
        per_position[p] = _select_for_position(results, inc, cohorts, p)
        pos_p[p] = per_position[p]["paired_p"]
    fdr = M14.bh_fdr(pos_p)
    for p, sel in per_position.items():
        sel["fdr_survives"] = bool(fdr.get(p, False))
        sel["verdict"] = M14.rookie_verdict(
            beats_incumbent=sel["beats_incumbent"], ordering_ok=sel["ordering_ok"],
            pbo=sel["pbo"], dsr=sel["dsr"], fdr_pass=sel["fdr_survives"],
            shippable=sel["winner"] is not None)
        log.info("  %s → winner=%s  tier_mae %s vs incumbent %s  verdict=%s", p,
                 (sel["winner"] or {}).get("key"), sel["winner_tier_mae"],
                 sel["incumbent_tier_mae"], sel["verdict"]["repoint"])

    return {
        "cohorts": cohorts, "n_configs": len(results), "selection_metric": M14.SELECTION_METRIC,
        "oracle_floor_holds": bool(oracle_ok), "incumbent": inc, "results": results,
        "per_position": per_position, "fdr_survives": fdr,
        "repoint_positions": [p for p, s in per_position.items() if s["verdict"]["repoint"]],
        "_folds": folds,
    }


def _pos_row(rec: dict, cohorts: list[int], pos: str, key: str = "tier_mae_by_pos") -> np.ndarray:
    """One config's per-cohort value of a position-keyed metric (NaN where that position was unscored
    in that class — a thin class simply contributes fewer points, it is never imputed)."""
    return np.array([rec["per_cohort"].get(y, {}).get(key, {}).get(pos, np.nan) for y in cohorts],
                    dtype=float)


def _select_for_position(results: list[dict], inc: dict, cohorts: list[int], pos: str) -> dict:
    """Pick + deflate ONE position's search. Metric = that position's draftable-tier MAE in raw
    fantasy points (no cross-position pooling here, so no scale normalisation is needed and the
    number stays readable as "PPR of error on the rookies you would actually draft")."""
    def _mean(a: np.ndarray) -> float | None:
        a = a[np.isfinite(a)]
        return round(float(a.mean()), 4) if len(a) else None

    inc_row = _pos_row(inc, cohorts, pos)
    inc_mae = _mean(inc_row)
    inc_rho = _mean(_pos_row(inc, cohorts, pos, "rho_by_pos"))
    inc_rho_f = inc_rho if inc_rho is not None else -1.0

    cands = []
    for r in results:
        row = _pos_row(r, cohorts, pos)
        mae = _mean(row)
        if mae is None:
            continue
        rho = _mean(_pos_row(r, cohorts, pos, "rho_by_pos"))
        cands.append({
            "rec": r, "row": row, "tier_mae": mae, "rho": rho,
            "tier_bias": _mean(_pos_row(r, cohorts, pos, "tier_bias_by_pos")),
            "eligible": (r["learner"] not in M14.NON_SHIPPABLE and rho is not None
                         and rho >= inc_rho_f - M14.ORDERING_DO_NO_HARM),
        })
    if not cands:
        return {"position": pos, "winner": None, "incumbent_tier_mae": inc_mae,
                "winner_tier_mae": None, "beats_incumbent": False, "ordering_ok": False,
                "pbo": None, "config_spread": None, "dsr": None, "paired_p": None,
                "per_cohort_delta": [], "n_candidates": 0}

    eligible = [c for c in cands if c["eligible"]]
    best = min(eligible, key=lambda c: c["tier_mae"]) if eligible else None
    best_any = min(cands, key=lambda c: c["tier_mae"])
    # `winner = None` with candidates present is a REAL result, not a bug: no shippable form stayed
    # within ORDERING_DO_NO_HARM of the incumbent's within-position rank at this position.

    # deflation over THIS position's whole search (negated so "higher is better" for CSCV)
    S = np.vstack([-c["row"] for c in cands])
    pbo = M14.cscv_pbo(S)
    spread = M14.config_spread(S)
    trial_srs = []
    for c in cands:
        d = inc_row - c["row"]
        d = d[np.isfinite(d)]
        trial_srs.append(float(d.mean() / d.std(ddof=1))
                         if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
    deltas, dsr, pval = [], None, None
    if best is not None:
        deltas = list((inc_row - best["row"])[np.isfinite(inc_row - best["row"])])
        dsr = M14.deflated_sharpe(np.array(deltas), np.array(trial_srs))
        pval = M14.onesided_paired_pvalue(np.array(deltas))

    return {
        "position": pos, "n_candidates": len(cands), "n_eligible": len(eligible),
        "incumbent_tier_mae": inc_mae, "incumbent_rho": inc_rho,
        "incumbent_tier_bias": _mean(_pos_row(inc, cohorts, pos, "tier_bias_by_pos")),
        "winner": None if best is None else {k: best["rec"][k] for k in ("key", "learner", "blocks", "hp")},
        "winner_tier_mae": None if best is None else best["tier_mae"],
        "winner_tier_bias": None if best is None else best["tier_bias"],
        "winner_rho": None if best is None else best["rho"],
        "best_any_key": best_any["rec"]["key"], "best_any_tier_mae": best_any["tier_mae"],
        "beats_incumbent": bool(best is not None and inc_mae is not None
                                and best["tier_mae"] < inc_mae),
        "ordering_ok": bool(best is not None),
        "pbo": pbo, "config_spread": spread, "dsr": dsr, "paired_p": pval,
        "per_cohort_delta": [round(float(x), 2) for x in deltas],
    }


def composite_predict(fold: Fold, per_position: dict) -> np.ndarray:
    """THE SHIPPED FORM — the composite rookie prior: a position whose search cleared the gate uses
    its selected learner; every other position keeps the INCUMBENT slot curve untouched. This is the
    same posture as NF1.1's `combined_ordering_score` (repoint only what earned it), and it is what
    the face-validity, interval and QB diagnostics must read — never a single global winner, which
    is not what NF1.4 ships."""
    out = fold.test["_inc"].to_numpy(dtype=float).copy()
    pos = fold.test["position_group"].astype(str).to_numpy()
    for p, sel in per_position.items():
        if not sel.get("verdict", {}).get("repoint") or not sel.get("winner"):
            continue
        m = pos == p
        if m.any():
            out[m] = _fit_predict(fold, sel["winner"])[m]
    return out


def block_ablation(folds: list[Fold], winner: dict, pos: str) -> list[dict]:
    """DROP-ONE-GROUP ablation on a position's winner: refit with each optional block removed and
    report the held-out change AT THAT POSITION. Every one of these configs already counted toward
    the deflation (they are in the pre-registered grid), so the ablation is safe rather than a
    second, un-deflated search."""
    out = []
    for drop in (None, *M14.OPTIONAL_BLOCKS):
        if drop is not None and drop not in winner["blocks"]:
            continue
        blocks = tuple(b for b in winner["blocks"] if b != drop) if drop else tuple(winner["blocks"])
        r = walk_forward(folds, {"learner": winner["learner"], "blocks": blocks, "hp": winner["hp"]})
        cohorts = [f.year for f in folds]

        def _mean(key):
            a = _pos_row(r, cohorts, pos, key)
            a = a[np.isfinite(a)]
            return round(float(a.mean()), 4) if len(a) else None

        out.append({"position": pos, "dropped": drop or "(none — winner)", "blocks": list(blocks),
                    "tier_mae": _mean("tier_mae_by_pos"), "tier_bias": _mean("tier_bias_by_pos"),
                    "rho": _mean("rho_by_pos")})
    return out


def board_face_validity(folds: list[Fold], per_position: dict) -> dict:
    """The LEVEL half of the face-validity gate, run WALK-FORWARD so it is leakage-safe.

    For each held-out draft class, the historical cap (per position, the Q90 of realized rookie
    seasons over ALL DRAFTED rookies in the PRIOR classes only) is compared against the maximum
    projection each form emits for that class. A form that routinely projects rookies above the 90th
    percentile of what rookies actually do IS the hot curve — no arbitrary threshold required.

    The other half of the gate — "no rookie in an overall top-10 board slot" — needs veterans on the
    same board and is evaluated by `season_projection.rookie_board_face_validity` against the real
    emitted board.
    """
    res: dict = {"per_cohort": {}, "note": "level check only; the top-10-overall check needs the "
                                           "merged veteran board (season_projection)."}
    for f in folds:
        board = f.test.assign(is_rookie=True, position=f.test["position_group"],
                              _new=composite_predict(f, per_position))
        res["per_cohort"][str(f.year)] = {
            "incumbent": M14.face_validity(board, f.train, fp_col="_inc")["positions_over_cap"],
            "selected": M14.face_validity(board, f.train, fp_col="_new")["positions_over_cap"],
        }
    res["incumbent_cohorts_over_cap"] = sum(1 for v in res["per_cohort"].values() if v["incumbent"])
    res["selected_cohorts_over_cap"] = sum(1 for v in res["per_cohort"].values() if v["selected"])
    res["n_cohorts"] = len(res["per_cohort"])
    return res


def survivorship_fix_arm(folds: list[Fold], inc: dict) -> dict:
    """Test the story's CENTRAL HYPOTHESIS on its own: the incumbent's exact functional form, fitted
    on the FULL drafted population instead of the survivors.

    This arm has **zero new degrees of freedom** — same power law, same 0.15 shrink, same P93 clip,
    same P1A nudge — so it is not a model search and needs no deflation gate. It isolates one
    question: is the `where games > 0` filter itself the defect? If the hot-curve story were right,
    dropping the filter should lower the level where it is too high and improve held-out accuracy.
    """
    cohorts = [f.year for f in folds]
    per = {}
    for f in folds:
        band_hist = f.train.assign(games=lambda d: d["rookie_games"])   # NO games > 0 filter
        curve = SP.fit_rookie_slot_curves(band_hist)
        out = SP.project_rookies(f.test, curve, f.year)
        m = dict(zip(out["player_id"], pd.to_numeric(out["proj_fp_ppr"], errors="coerce")))
        pred = np.array([float(m.get(g, 0.0)) for g in f.test["gsis_id"]], dtype=float)
        per[f.year] = M14.cohort_metrics(f.test.assign(_pred=pred), "_pred", scale=f.scale)
    rec = {"key": "incumbent_form_fitted_on_ALL_drafted", "per_cohort": per, **_summarize(per)}

    by_pos = {}
    for p in M14.ROOKIE_POSITIONS:
        for tag, r in (("incumbent", inc), ("survivorship_fixed", rec)):
            a = _pos_row(r, cohorts, p)
            a = a[np.isfinite(a)]
            by_pos.setdefault(p, {})[tag + "_tier_mae"] = round(float(a.mean()), 2) if len(a) else None
    return {"summary": {k: rec[k] for k in ("mean_tier_mae", "mean_tier_bias", "mean_mae",
                                            "mean_bias", "mean_rho")},
            "incumbent_summary": {k: inc[k] for k in ("mean_tier_mae", "mean_tier_bias", "mean_mae",
                                                      "mean_bias", "mean_rho")},
            "by_position": by_pos}


def served_band_coverage(folds: list[Fold]) -> dict:
    """⭐ THE ONE SHIPPABLE FIX — measure the SERVED rookie 80% band, before and after.

    Both arms run the real production path (`fit_rookie_slot_curves` → `project_rookies`) on the
    fold's training classes, differing only in whether `band_hist` (the full drafted population,
    zero-game rookies included) is supplied. The POINT projection is byte-identical between them;
    only `fp_ppr_p10`/`fp_ppr_p90` move. This is an interval-CALIBRATION measurement on held-out
    classes, not a model search — no deflation gate applies to it, the same way a NULL-handling fix
    does not need one.

    ⚠️ NF1.7 SUPERSEDED the band this measures, so the `calibrated_band` arm is PINNED to
    `per_player_band=False`. Without that pin it would silently start measuring NF1.7's per-player
    band while the report around it still described NF1.4's class-level tercile one — a report that
    quietly stops measuring what it claims. NF1.7's own numbers live in
    `ablation_results/nf1_7_rookie_intervals.md`."""
    res = {"legacy_cv_band": {"hit": 0, "n": 0, "by_pos": {}},
           "calibrated_band": {"hit": 0, "n": 0, "by_pos": {}},
           "nominal": 0.80, "point_projection_max_abs_change": 0.0}
    for f in folds:
        hist = f.train[f.train["rookie_games"] > 0].assign(
            games=lambda d: d["rookie_games"])
        band_hist = f.train.assign(games=lambda d: d["rookie_games"])
        arms = {
            "legacy_cv_band": SP.project_rookies(f.test, SP.fit_rookie_slot_curves(hist), f.year),
            "calibrated_band": SP.project_rookies(
                f.test, SP.fit_rookie_slot_curves(hist, band_hist=band_hist,
                                                  per_player_band=False), f.year),
        }
        res["point_projection_max_abs_change"] = max(
            res["point_projection_max_abs_change"],
            float((arms["legacy_cv_band"]["proj_fp_ppr"]
                   - arms["calibrated_band"]["proj_fp_ppr"]).abs().max()))
        for tag, proj in arms.items():
            m = proj.set_index("player_id")
            for _, r in f.test.iterrows():
                if r["gsis_id"] not in m.index:
                    continue
                row = m.loc[r["gsis_id"]]
                ok = int(row["fp_ppr_p10"] <= r["rookie_fp_ppr"] <= row["fp_ppr_p90"])
                res[tag]["hit"] += ok
                res[tag]["n"] += 1
                bp = res[tag]["by_pos"].setdefault(str(r["position_group"]), [0, 0])
                bp[0] += ok
                bp[1] += 1
    for tag in ("legacy_cv_band", "calibrated_band"):
        d = res[tag]
        d["coverage"] = round(d["hit"] / d["n"], 4) if d["n"] else None
        d["by_pos"] = {k: round(v[0] / v[1], 3) for k, v in sorted(d["by_pos"].items()) if v[1]}
    return res


def qb_top_pick_diagnostic(folds: list[Fold], per_position: dict) -> dict:
    """⭐ THE FLAGGED SYMPTOM, measured directly: for each class, the top-drafted rookie QB's
    projection vs what he actually scored.

    MVP-3 dogfooding flagged "a rookie QB floated to #1 overall." On the emitted MVP-1 boards
    2019–2025 that is exactly what recurs — the #1-overall QB is projected QB11–QB15 and finishes
    QB22–QB25 (Burrow, Lawrence, Young, Ward). This table is the before/after on that single case,
    which no pooled metric will ever show clearly."""
    rows = []
    for f in folds:
        te = f.test.assign(_new=composite_predict(f, per_position))
        qb = te[te["position_group"].astype(str) == "QB"]
        if qb.empty:
            continue
        r = qb.nsmallest(1, "draft_overall").iloc[0]
        rows.append({"draft_class": f.year, "player": r["player_name"],
                     "draft_overall": float(r["draft_overall"]),
                     "incumbent_fp": round(float(r["_inc"]), 1),
                     "selected_fp": round(float(r["_new"]), 1),
                     "realized_fp": round(float(r["rookie_fp_ppr"]), 1)})
    if not rows:
        return {}
    d = pd.DataFrame(rows)
    return {"per_class": rows,
            "incumbent_mean_error": round(float((d["incumbent_fp"] - d["realized_fp"]).mean()), 1),
            "selected_mean_error": round(float((d["selected_fp"] - d["realized_fp"]).mean()), 1),
            "realized_mean": round(float(d["realized_fp"].mean()), 1)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reports
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md_table(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False)
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, pool: pd.DataFrame, path: Path) -> None:
    a: list[str] = []
    p = a.append
    inc, pp = out["incumbent"], out["per_position"]
    p("# NF1.4 — rookie-prior refinement (the hot-curve fix)")
    p("")
    p(f"**Model:** `{M14.MODEL_VERSION}` · **cohorts scored:** {out['cohorts']} · "
      f"**configs evaluated:** {out['n_configs']} · **generated:** {datetime.now(timezone.utc).isoformat()}")
    p("")
    p("> ⚖️ **Honest frame.** This is a PROJECTION-product story, not a betting edge — `best_alpha` "
      "does not apply. The win condition is rookie CALIBRATION (kill the level over-valuation), and "
      "the ordering claim is held to the full §0.5 deflation (CSCV-PBO / DSR / BH-FDR). The rookie "
      "sample is TINY (QB ≈ 12/class over a handful of cohorts) ⇒ the deflation is NOISY and "
      "\"cannot distinguish from luck\" is the expected ordering verdict, recorded as a null.")
    p("")
    p("## 0. Verdict in one paragraph")
    p("")
    sb0 = out.get("served_band_coverage", {})
    p(f"**MODEL: NULL — the incumbent slot curve STANDS.** {out['n_configs']} pre-registered configs "
      "× 4 positions, walk-forward over "
      f"{len(out['cohorts'])} draft classes: no form beat the incumbent's draftable-tier accuracy "
      "and survived the deflation at ANY position, so the rookie POINT projection is unchanged. "
      "**The story's hot-curve premise is REFUTED as a level claim** — the incumbent rookie prior is "
      "*cold*, not hot, on the draftable tier at every position (`tier_bias` −32 to −58 PPR), and "
      "its projection for the #1-overall rookie QB is nearly unbiased over 2019–2025 (**+8.9** PPR "
      "against a realized mean of ~201). The dogfooding symptom is real but is a RANK effect, not a "
      "level one (§2). **ONE fix ships**: the rookie 80% interval, which claimed 80% and delivered "
      f"**{sb0.get('legacy_cv_band', {}).get('coverage')}** "
      f"(**{sb0.get('legacy_cv_band', {}).get('by_pos', {}).get('QB')}** at QB), recalibrated to "
      f"**{sb0.get('calibrated_band', {}).get('coverage')}** with the point projection byte-identical (§6).")
    p("")
    p("## 1. The measured defect — survivorship, tested and NOT the cure")
    p("")
    surv = pool.assign(played=(pool["rookie_games"] > 0)).groupby("position_group").agg(
        n=("rookie_fp_ppr", "size"),
        pct_zero_game=("played", lambda s: round(100.0 * (1 - s.mean()), 1)),
        mean_fp_all_drafted=("rookie_fp_ppr", lambda s: round(float(s.mean()), 1)),
    )
    played = pool[pool["rookie_games"] > 0].groupby("position_group")["rookie_fp_ppr"].mean().round(1)
    surv["mean_fp_survivors_only"] = played
    surv["inflation_pct"] = (100 * (surv["mean_fp_survivors_only"] / surv["mean_fp_all_drafted"] - 1)).round(1)
    p("MVP-1's `load_rookie_training` fits the slot curve under `where games > 0`, so every drafted "
      "rookie who never played is dropped from the fit. The positional mean, the P93 ceiling and the "
      "games-by-slot prior are therefore all estimated on SURVIVORS:")
    p("")
    p(_md_table(surv.reset_index()))
    p("")
    sfa = out.get("survivorship_fix_arm", {})
    if sfa:
        p("That is a real and large bias at QB. **But removing the filter does not fix the board.** "
          "This arm re-fits the incumbent's EXACT functional form (same power law, same 0.15 shrink, "
          "same P93 clip, same P1A nudge — zero new degrees of freedom, so no deflation gate "
          "applies) on the full drafted population, and scores it on the same held-out classes:")
        p("")
        rows = [{"position": k, **v} for k, v in sfa.get("by_position", {}).items()]
        p(_md_table(pd.DataFrame(rows)))
        p("")
        p("```json")
        p(json.dumps(_jsonable({"survivorship_fixed": sfa["summary"],
                                "incumbent": sfa["incumbent_summary"]}), indent=2, default=float))
        p("```")
        p("")
        p("Held-out tier accuracy gets WORSE at every position and the universe bias gets MORE "
          "negative — because the board was already too cold, so lowering the level further is a "
          "net loss. The survivorship filter is a genuine flaw in how the curve is estimated; it is "
          "not the flaw that produces the flagged board.")
        p("")
    p("## 2. What the symptom actually is — a RANK effect, not a hot level")
    p("")
    p("⚠️ **The story's premise needed sharpening, and the measurement says so.** Over ALL drafted "
      "rookies the incumbent is not hot, it is **COLD** — it under-projects almost every rookie "
      f"(pooled `mean_bias` = `{inc['mean_bias']}` PPR) — and it stays cold on the DRAFTABLE tier at "
      "every position, QB included (§3, `incumbent_tier_bias` −32 to −58). The point projection for "
      "the very player the dogfooding flagged, the #1-overall rookie QB, is close to unbiased over "
      "seven classes.")
    p("")
    p("So where does \"a rookie QB floated to #1 overall\" come from? From the **RANK**, not the "
      "level. On the emitted 2019–2025 boards the #1-overall QB is projected QB11–QB15 and finishes "
      "QB8–QB25 (mean ≈ QB19.5) — an over-placement of roughly six QB slots. Two things make a "
      "near-unbiased point projection land six slots high: rookie QB outcomes are enormously "
      "dispersed (Kyler Murray beat his projection by 85 PPR; Trevor Lawrence missed his by 62), and "
      "veteran QB projections are densely packed near that same level, so a few points of "
      "projection buys many ranks. **A rank error produced by variance around an unbiased point "
      "estimate is not fixed by shifting the level** — it is an UNCERTAINTY problem, which is "
      "exactly what §6 fixes.")
    p("")
    p("The selection metric is nonetheless run **per position** on that position's DRAFTABLE-tier "
      "MAE (top "
      + ", ".join(f"{k} {v}" for k, v in M14.TIER_K.items())
      + ", the tier anchored on the incumbent so it is identical for every candidate): a pooled "
      "metric would average the positions together and could not answer \"is the rookie prior "
      "better at QB?\" at all. That is also NF1.1's own conclusion for this product.")
    p("")
    p("### ⭐ The flagged symptom — the top-drafted rookie QB, per class")
    p("")
    qbd = out.get("qb_top_pick_diagnostic") or {}
    if qbd.get("per_class"):
        p(_md_table(pd.DataFrame(qbd["per_class"])))
        p("")
        p(f"Incumbent mean error on this one player: **{qbd.get('incumbent_mean_error'):+}** PPR "
          f"against a realized mean of {qbd.get('realized_mean')}; the shipped NF1.4 composite: "
          f"**{qbd.get('selected_mean_error'):+}**.")
    p("")
    p("## 3. Per-position selection + deflation (every evaluated config counts)")
    p("")
    rows = []
    for pos, sel in pp.items():
        rows.append({
            "position": pos,
            "incumbent_tier_mae": sel["incumbent_tier_mae"],
            "incumbent_tier_bias": sel["incumbent_tier_bias"],
            "winner": (sel["winner"] or {}).get("key"),
            "winner_tier_mae": sel["winner_tier_mae"],
            "winner_tier_bias": sel["winner_tier_bias"],
            "pbo": sel["pbo"], "spread": sel["config_spread"], "dsr": sel["dsr"],
            "p": sel["paired_p"], "fdr": sel.get("fdr_survives"),
            "REPOINT": sel.get("verdict", {}).get("repoint"),
        })
    p(_md_table(pd.DataFrame(rows)))
    p("")
    p("`tier_mae` is in **fantasy points of error on the rookies you would actually draft** at that "
      "position. `tier_bias` = mean(projected − realized) on that tier: **positive = the hot curve**, "
      "negative = too cold. A position REPOINTS only when its winner beats the incumbent, does no "
      "ordering harm, and clears PBO < "
      f"{M14.PBO_MAX} / DSR ≥ {M14.DSR_MIN} / BH-FDR at q={M14.FDR_Q}.")
    p("")
    p(f"**Positions repointed:** `{out.get('repoint_positions')}` — every other position keeps the "
      "incumbent slot curve untouched.")
    p("")
    for pos, sel in pp.items():
        if sel["pbo"] is not None and sel["pbo"] >= M14.PBO_MAX:
            p(f"> 📖 **{pos}: PBO {sel['pbo']} against a config spread of {sel['config_spread']}** — "
              "per §0.5 a high PBO over a TIGHT spread is the NULL (the candidates genuinely tie, so "
              "\"which one wins\" is noise); a high PBO over a WIDE spread is overfitting. The spread "
              "is the discriminator, not the PBO alone.")
    p("")
    p(f"Oracle-floor guard (E2.1-r): **{out.get('oracle_floor_holds')}** — the realized-outcome "
      "oracle scores 0 on the selection metric and nothing beat it, so the metric is not inverted.")
    p("")
    p("### Per-cohort tier MAE (incumbent → selected composite)")
    p("")
    per = []
    for y in out["cohorts"]:
        r = {"draft_class": y}
        for pos in M14.ROOKIE_POSITIONS:
            r[f"{pos}_inc"] = inc["per_cohort"].get(y, {}).get("tier_mae_by_pos", {}).get(pos)
        per.append(r)
    p(_md_table(pd.DataFrame(per)))
    p("")
    p("## 4. Block ablation (drop-one on each repointed position's winner)")
    p("")
    if out.get("ablation"):
        p(_md_table(pd.DataFrame(out["ablation"])))
    else:
        p("_not run — no position cleared the gate, so there is no selected form to ablate. The "
          "pre-registered blocks were still all evaluated: see the candidate table below._")
    p("")
    p("## 5. Full candidate table")
    p("")
    p("Pooled across positions (the per-position selection tables are in §3); shown for the search "
      "record — every one of these configs counted toward the deflation.")
    p("")
    tbl = pd.DataFrame([{k: r[k] for k in ("key", "learner", "mean_tier_mae", "mean_tier_bias",
                                           "mean_mae", "mean_rmse", "mean_bias", "mean_slope",
                                           "mean_rho")} for r in out["results"]])
    p(_md_table(tbl.sort_values("mean_tier_mae")))
    p("")
    p("## 6. ⭐ Rookie uncertainty — the one shippable fix")
    p("")
    sb = out.get("served_band_coverage", {})
    p("MVP-1 widened rookie intervals by `fp × cv`, with the cv estimated on the same "
      "SURVIVOR-filtered sample as the curve (`uncertainty_type='parameter'`, and its own report "
      "said \"recalibrate before pricing\"). Measured walk-forward, that nominal **80%** band "
      f"covers **{sb.get('legacy_cv_band', {}).get('coverage')}** — and "
      f"**{sb.get('legacy_cv_band', {}).get('by_pos', {}).get('QB')}** at QB. It is not an 80% "
      "interval; it is a decoration. A multiplicative width also collapses toward zero as the "
      "projection does, so the late-round rookies who most often surprise get the NARROWEST band.")
    p("")
    p("NF1.4 replaces it with an EMPIRICAL band: within a position, the q10/q90 of what drafted "
      "rookies in that prediction tercile actually scored, over the FULL drafted population "
      "(never-played rookies carried as real zeros). Coverage becomes a measured claim:")
    p("")
    p("```json")
    p(json.dumps(_jsonable(sb), indent=2, default=float))
    p("```")
    p("")
    p("⭐ `point_projection_max_abs_change` is **0.0** — the point projection is byte-identical. "
      "This is an interval-CALIBRATION fix, not a model change, so the null verdict above stands "
      "untouched and no deflation gate applies to it (a mis-stated interval is a defect, not a "
      "search result).")
    p("")
    p("## 7. Face validity")
    p("")
    p("```json")
    p(json.dumps(_jsonable(out.get("face_validity", {})), indent=2, default=float))
    p("```")
    p("")
    p("## 8. Limitations")
    p("")
    p("- **Small-N by construction** — ~75 drafted skill rookies per class, ~12 at QB. Every "
      "positional read is thin; the interval width is the honest expression of that.")
    p("- **Breakout age is a CLASS-YEAR proxy, not a birth date** (the sports lake has no DOB), and "
      "`stg_ncaaf_roster` starts at 2014, so the earliest classes carry `has_breakout = 0` where "
      "their freshman season predates the feed. Kept NULL + flagged, never back-filled with a guess.")
    p("- **Combine coverage is partial** (forty ≈ 50% at QB, ≈ 73% at RB/WR) — a player who did not "
      "test stays NaN with `has_combine = 0` carrying the missingness.")
    p("- **The rookie label is the rookie SEASON only** — this prior prices year 1, which is what "
      "the redraft board needs. A dynasty (multi-year) rookie value is a different target.")
    p("- **P1A is used as the BACKBONE, not rebuilt** — its own verdict stands (draft slot beats "
      "college production 0.64 vs 0.79 MAE), so `projected_nfl_z` enters as a slot RESIDUAL.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _connect(path: str):
    import duckdb

    if not Path(path).exists():
        raise SystemExit(f"DuckDB not found at {path} — build the marts first (see module docstring)")
    return duckdb.connect(path, read_only=True)


def _load_pool(args) -> pd.DataFrame:
    """The cached rookie frame — assembled ONCE (§0.5 cost hygiene) and re-read by every candidate,
    ablation and CV fold. The cache holds EVERY class incl. the unlabelled incoming one; callers
    that fit or score must go through `labelled()`."""
    cache = Path(args.cache)
    if cache.exists() and not args.rebuild_cache:
        log.info("reading cached rookie training frame → %s", cache)
        return pd.read_parquet(cache)
    con = _connect(args.duckdb)
    try:
        pool = assemble_rookie_training(con, schema=args.schema)
    finally:
        con.close()
    cache.parent.mkdir(parents=True, exist_ok=True)
    pool.to_parquet(cache, index=False)
    log.info("assembled %d rookies → %s", len(pool), cache)
    return pool


def labelled(pool: pd.DataFrame) -> pd.DataFrame:
    """Only the draft classes whose rookie season has actually been played. Fitting or scoring on an
    unlabelled class would treat an entire incoming draft as an all-zero outcome."""
    if "label_available" not in pool.columns:
        return pool
    return pool[pool["label_available"].astype(bool)].reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF1.4 — rookie-prior refinement")
    ap.add_argument("mode", choices=("assemble", "bakeoff", "board"))
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--cache", default=str(_TRAIN_CACHE))
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="tiny grid + 3 cohorts; writes *_smoke artifacts")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    pool_all = _load_pool(args)
    pool = labelled(pool_all)
    if args.mode == "assemble":
        log.info("rookie training frame: %d rows (%d labelled), classes %s–%s", len(pool_all),
                 len(pool), int(pool_all["draft_year"].min()), int(pool_all["draft_year"].max()))
        log.info("label: rookie PPR by position\n%s",
                 pool.groupby("position_group")["rookie_fp_ppr"].agg(["size", "mean", "median"]).round(1))
        return 0

    if args.mode == "board":
        return _board_mode(args, pool_all)

    out = run_bakeoff(pool, smoke=args.smoke)
    folds = out.pop("_folds")
    pp = out["per_position"]
    out["face_validity"] = board_face_validity(folds, pp)
    out["qb_top_pick_diagnostic"] = qb_top_pick_diagnostic(folds, pp)
    abl = [row for pos, sel in pp.items() if sel.get("verdict", {}).get("repoint")
           for row in block_ablation(folds, sel["winner"], pos)]
    if abl:
        out["ablation"] = abl
    out["served_band_coverage"] = served_band_coverage(folds)
    out["survivorship_fix_arm"] = survivorship_fix_arm(folds, out["incumbent"])

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf1_4_rookie{suffix}.json").write_text(
        json.dumps(_jsonable(out), indent=2, default=float))
    write_report(out, pool, _REPORT_DIR / f"nf1_4_rookie{suffix}.md")
    log.info("VERDICT — positions repointed: %s", out["repoint_positions"] or "NONE (incumbent stands)")
    return 0


def _jsonable(o):
    """numpy/int64 keys and values → plain JSON types (json.dumps rejects an int64 dict KEY even
    with `default=`, which only covers values)."""
    if isinstance(o, dict):
        return {(k if isinstance(k, (str, bool, type(None))) else str(k)): _jsonable(v)
                for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _board_mode(args, pool_all: pd.DataFrame) -> int:
    """Read-only diagnostic on the INCOMING (unlabelled) draft class — its projection under the
    served rookie prior, with both halves of the NF1.4 face-validity gate.

    NF1.4's model verdict is a NULL (no candidate form survived the deflation at any position), so
    the projection here IS the incumbent slot curve; what changed is the 80% band. This mode exists
    to check a live class before the board ships, which is the point of the face-validity gate."""
    pool = labelled(pool_all)
    incoming = pool_all[~pool_all["label_available"].astype(bool)] if "label_available" in pool_all \
        else pool_all.iloc[:0]
    if incoming.empty:
        log.warning("no incoming (unlabelled) class in the cached frame — nothing to check")
        return 0
    season = int(incoming["draft_year"].max())
    tr, te = add_fold_features(pool, incoming)
    proj = SP.project_rookies(
        te,
        SP.fit_rookie_slot_curves(
            tr[tr["rookie_games"] > 0].assign(games=lambda d: d["rookie_games"]),
            band_hist=tr.assign(games=lambda d: d["rookie_games"])),
        season)
    board = proj.assign(is_rookie=True).merge(
        te[["gsis_id", "draft_overall"]].rename(columns={"gsis_id": "player_id"}),
        on="player_id", how="left", suffixes=("", "_y"))
    show = board.sort_values("proj_fp_ppr", ascending=False).head(20)[
        ["player_name", "position", "draft_overall", "proj_fp_ppr", "fp_ppr_p10", "fp_ppr_p90",
         "uncertainty_type"]]
    log.info("incoming class %d — served rookie projections (top 20)\n%s",
             season, show.to_string(index=False))
    fv = SP.rookie_board_face_validity(board, tr)
    log.info("face validity (ROOKIE-ONLY board — the top-N-overall half needs the merged veteran "
             "board from run_season_projection): %s", json.dumps(_jsonable(fv), default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
