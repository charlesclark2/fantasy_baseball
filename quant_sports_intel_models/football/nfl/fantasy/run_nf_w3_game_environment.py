"""run_nf_w3_game_environment.py — NF-W3 §0.5 bake-off: the game-environment component
(team play-volume + pass/rush allocation), and ⭐ the gate that decides whether it is worth
anything — does it improve the ASSEMBLED player projection against the NF-W1 `lgbm_hurdle`
champion as the permanent direct foil?

Everything decidable in advance lives as a CONSTANT in `game_environment.py`; this runner READS it
(the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w3_preregistration.md` BEFORE the full run.

PIPELINE
  LAYER A (team-game): pbp → per-team-game box (the SQL itself is checked against the deferred
  contract) → `assemble_team_matrix` (features + provenance + the NF-W0a PIT GATE) → the NF-W1
  fold axis verbatim → 4 arms + 2 foils + anchors (incl. ONE PEEKING ORACLE PER ARM'S OWN FORM)
  through ONE reducer → CRPS selection → PBO / DSR / BH-FDR / fold clause → ship-or-null per target.

  LAYER B (player-week — THE GATE): the NF-W1 certified matrix → env projections produced by the
  Layer-A winners, EXPANDING-WINDOW inside the training span so a train row's env feature is
  out-of-sample for the env model too → `champion` (NF-W1 spec) vs `champion_env` (same estimator
  + the env block), with three anchors: `champion_env_foil` (env from the FOIL — the matched foil
  that attributes any lift to the LEARNED component rather than to team context in any form),
  `champion_env_shuffled` (env permuted across teams within week — must not help) and
  ⭐ `champion_env_oracle` (REALIZED week-w volume/share — the peeking upper bound on everything
  the whole environment chain can buy at the player level).

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w3_game_environment --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w3_game_environment
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w3_game_environment --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import (  # noqa: E402
    build_matrix as build_player_matrix,
)

log = logging.getLogger("nfl.fantasy.nf_w3")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
SEASONS = (2016, 2025)

#: The per-team-game aggregation. ⛔ It may not READ a deferred-contract column — markets, realized
#: weather, depth chart — and `GE.assert_source_query_is_clean` enforces that on this literal
#: (comments stripped first, so a prose mention can neither satisfy nor trip the check).
TEAM_BOX_SQL = """
select season, week, posteam as team,
       count(*) filter (where play_type in ('pass','run'))                      as off_plays,
       count(*) filter (where play_type = 'pass')                               as pass_plays,
       count(*) filter (where sack = 1)                                         as sacks,
       count(distinct fixed_drive)                                              as drives,
       avg(epa)        filter (where play_type in ('pass','run'))               as epa_per_play,
       avg(success)    filter (where play_type in ('pass','run'))               as success_rate,
       avg(pass_oe)    filter (where play_type in ('pass','run'))               as proe,
       avg(no_huddle)  filter (where play_type in ('pass','run'))               as no_huddle,
       max(posteam_score_post)                                                  as points,
       avg(case when play_type = 'pass' then 1.0 else 0.0 end)
           filter (where play_type in ('pass','run') and down in (1,2)
                   and qtr <= 3 and wp between 0.20 and 0.80)                   as neutral_pass_rate,
       (max(3600 - game_seconds_remaining) - min(3600 - game_seconds_remaining))
           / nullif(count(*) filter (where play_type in ('pass','run')), 0)     as sec_per_play
from {pbp}
where season between {lo} and {hi} and season_type = 'REG' and posteam is not null
group by 1, 2, 3
"""


# ── Sources ─────────────────────────────────────────────────────────────────────────────────────
def load_team_box(seasons: tuple[int, int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q
    lo, hi = seasons
    sql = TEAM_BOX_SQL.format(pbp=delta("pbp"), lo=lo, hi=hi)
    GE.assert_source_query_is_clean(sql)
    team_box = q(sql)
    schedule = q(f"""
        select season, week, home_team, away_team, gameday, div_game
        from {delta('schedules')}
        where season between {lo} and {hi} and game_type = 'REG'
    """)
    return team_box, schedule


def build_team_matrix(seasons: tuple[int, int], *, rebuild_cache: bool = False):
    """⭐ The PIT gate runs on EVERY build, cache hit or not — a cached matrix must re-prove its
    point-in-time cleanliness, or the guard is invoked only on the day the cache was written
    (the NF-C0e wired-≠-invoked shape, cache edition)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cache = _ARTIFACTS / f"nf_w3_team_matrix_{GE.matrix_key(seasons)}.parquet"
    if cache.exists() and not rebuild_cache:
        log.info("team-matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        df = pd.read_parquet(cache)
        audit = GE.run_pit_gate(df)
        df = df.loc[audit.pop("kept_index")].reset_index(drop=True)
        df = df[df["off_plays"].notna() & (df["off_plays"] > 0)].reset_index(drop=True)
        return df, audit
    team_box, schedule = load_team_box(seasons)
    modeled, audit = GE.assemble_team_matrix(team_box, schedule)
    modeled.to_parquet(cache, index=False)
    log.info("team matrix → %s (%d rows; PIT %d weeks / %d records, %d rows dropped)",
             cache.name, len(modeled), audit["weeks_checked"], audit["records_checked"],
             audit["rows_dropped"])
    return modeled, audit


# ── One reducer for every label, both layers ────────────────────────────────────────────────────
def score_team(qmat: np.ndarray, test: pd.DataFrame, target: str, label: str = "?") -> dict:
    GE.assert_finite_predictive(qmat, label)
    y = test[target].to_numpy(dtype=float)
    c = GE.crps(qmat, y)
    med = np.sort(qmat, axis=1)[:, len(GE.Q_LEVELS) // 2]
    return {"crps": float(np.nanmean(c)), "mae_report_only": float(np.nanmean(np.abs(y - med)))}


def _fit(arm: str, train, test, target: str, *, y_train=None) -> np.ndarray:
    return GE.ARM_FITTERS[arm](train, test, GE.FEATURES, target, y_train=y_train)


def run_layer_a_fold(fold: WP.Fold, feat: pd.DataFrame, target: str) -> dict:
    """Every arm, foil and anchor for one fold and one target — all through ONE reducer."""
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    t0 = time.time()
    league_mean = float(train[target].mean())
    foil_tr = GE.foil_point(train, target, league_mean, matchup=False)
    bank = GE.residual_bank(train[target].to_numpy(float), foil_tr)
    foil_te = GE.foil_point(test, target, league_mean, matchup=False)
    foil_te_m = GE.foil_point(test, target, league_mean, matchup=True)

    qmats: dict[str, np.ndarray] = {
        "foil_team_eb": GE.apply_bank(foil_te, bank),
        "foil_team_eb_matchup": GE.apply_bank(foil_te_m, bank),
        "nihilist_zero": GE.anchor_nihilist(test),
        "marginal_train": GE.anchor_marginal(train, test, target),
        "zero_width": GE.anchor_zero_width(foil_te),
        "max_width": GE.anchor_max_width(foil_te, bank),
    }
    for arm in GE.REAL_ARMS[target]:
        qmats[arm] = _fit(arm, train, test, target)
        # NF-D16 (g‴): the peeking ceiling of THIS arm's OWN form (fit ON the test block).
        qmats[GE.oracle_of(arm)] = _fit(arm, test, test, target)
        # NF1.9 (f): the same form at the oracle's sample scale — the capacity control.
        qmats[GE.matched_n_of(arm)] = _fit(arm, GE.matched_n_train(train, test), test, target)
    # the foils' own-form oracles: an EB level fit on the test block's own league mean
    for foil, pt in (("foil_team_eb", False), ("foil_team_eb_matchup", True)):
        te_mean = float(test[target].mean())
        pt_te = GE.foil_point(test, target, te_mean, matchup=pt)
        qmats[GE.oracle_of(foil)] = GE.apply_bank(
            pt_te, GE.residual_bank(test[target].to_numpy(float), pt_te))

    # the permuted arm uses the SAME estimator family as the eventual winner is chosen from;
    # pre-registered as the boosting class so it is fixed before any score is seen.
    qmats["permuted_within_week"] = _fit(
        "lgbm_quantile", train, test, target,
        y_train=GE.permute_within_week(train, target))

    scores = {k: score_team(v, test, target, label=k) for k, v in qmats.items()}
    coverage = {k: WP.interval_coverage(qmats[k], test[target].to_numpy(float))
                for k in (*GE.REAL_ARMS[target], *GE.FOILS)}
    log.info("[A/%s] fold %s in %.1fs (train %d / test %d)",
             target, fold.label, time.time() - t0, len(train), len(test))
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "n_train": int(len(train)), "n_test": int(len(test))}


def select_layer_a(target: str, fold_results: list[dict], n_folds: int) -> dict:
    crps = pd.DataFrame({fr["label"]: {k: fr["scores"][k]["crps"] for k in fr["scores"]}
                         for fr in fold_results}).T
    mean_crps = crps.mean(axis=0)
    arms = list(GE.REAL_ARMS[target])
    winner = str(mean_crps[arms].idxmin())
    best_foil = str(mean_crps[list(GE.FOILS)].idxmin())
    deltas = (crps[best_foil] - crps[winner]).to_numpy(float)
    mean_d, lo, hi = GE.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = GE.eligible_labels(target)
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in arms:
        d = (crps[best_foil] - crps[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    perm_lift = (crps[best_foil] - crps["permuted_within_week"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    anchors = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "marginal_loses": bool(mean_crps["marginal_train"] > mean_crps[winner]),
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        "winner_beats_permuted": bool(mean_crps["permuted_within_week"] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        # NF-D16 (g‴): per-FORM floors — the ceiling of an arm is the peeking version of its OWN
        # form, never one shared ceiling (which would veto a legitimately-better nested form).
        # ⭐ STRICT reading, reported but NOT the gate:
        "no_arm_beats_own_oracle": bool(all(
            mean_crps[a] > mean_crps[GE.oracle_of(a)] for a in arms)),
        # ⭐ THE GATED reading — NF1.9 (f): a peeking oracle is a floor only AT MATCHED n. An arm
        # beating its own oracle is admissible when that oracle beats the same form trained on a
        # block-sized sample, i.e. when the gap is CAPACITY rather than leakage.
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_crps[a] > mean_crps[GE.oracle_of(a)])
            or (mean_crps[GE.oracle_of(a)] < mean_crps[GE.matched_n_of(a)])
            for a in arms)),
        "foils_respect_own_oracle": bool(all(
            mean_crps[f] > mean_crps[GE.oracle_of(f)] for f in GE.FOILS)),
    }
    oracle_detail = {
        a: {"arm": round(float(mean_crps[a]), 4),
            "own_form_oracle": round(float(mean_crps[GE.oracle_of(a)]), 4),
            "matched_n": round(float(mean_crps[GE.matched_n_of(a)]), 4),
            "oracle_beats_matched_n": bool(mean_crps[GE.matched_n_of(a)]
                                           > mean_crps[GE.oracle_of(a)])}
        for a in arms
    }

    covs = [fr["coverage"][winner] for fr in fold_results]
    n_tot = sum(c["n"] for c in covs)
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = float(np.sqrt(GE.COVERAGE_FLOOR * (1 - GE.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")

    sd = float(np.nanstd(deltas, ddof=1))
    return {
        "target": target, "winner": winner, "best_foil": best_foil,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_crps.items()},
        "mean_mae_report_only": {
            k: round(float(np.mean([fr["scores"][k]["mae_report_only"] for fr in fold_results])), 4)
            for k in (winner, best_foil, "nihilist_zero", "marginal_train")},
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "mean_delta": None if mean_d is None else round(mean_d, 4),
        "ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval, "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": round(float(np.nanmean(deltas)) / sd, 3) if sd > 1e-12 else None,
        "var_trials_sr": round(float(np.var(np.asarray(trial_srs), ddof=1)), 5) if len(trial_srs) > 1 else None,
        "anchors": anchors, "oracle_detail": oracle_detail,
        "permutation_detail": {"permuted_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 4),
                               "permuted_lift_p_one_sided": p_perm},
        "coverage": {"winner_coverage_80": round(cov, 4), "n_rows": int(n_tot),
                     "binomial_se": round(se, 4),
                     "blocking_shortfall": bool(n_tot and (GE.COVERAGE_FLOOR - cov)
                                                > GE.COVERAGE_BLOCK_SE * se)},
    }


# ── Layer B: env projections + the downstream gate ──────────────────────────────────────────────
def _point_and_sd(qmat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Point = the grid mean of the predictive; sd = the normal-equivalent from the 10/90 band.
    Declared: a grid-quantile mean is an approximation of E[Y], identical for every arm."""
    q = np.sort(qmat, axis=1)
    lo = q[:, int(np.argmin(np.abs(GE.Q_LEVELS - 0.10)))]
    hi = q[:, int(np.argmin(np.abs(GE.Q_LEVELS - 0.90)))]
    return q.mean(axis=1), (hi - lo) / (2 * 1.2815515655446004)


def _env_predict(form: str, train: pd.DataFrame, target: str, rows: pd.DataFrame):
    if form.startswith("foil"):
        pt = GE.foil_point(rows, target, float(train[target].mean()),
                           matchup=form.endswith("matchup"))
        bank = GE.residual_bank(train[target].to_numpy(float),
                                GE.foil_point(train, target, float(train[target].mean()),
                                              matchup=form.endswith("matchup")))
        return _point_and_sd(GE.apply_bank(pt, bank))
    return _point_and_sd(_fit(form, train, rows, target))


def env_projection_table(team_feat: pd.DataFrame, fold: WP.Fold, forms: dict[str, str]) -> pd.DataFrame:
    """(season, week, team) → projected volume + share for EVERY row of this fold.

    ⚠️ A projected feature must be a PROJECTION on both sides of the fold, or the player model
    learns to trust a value serving will never have. TEST rows use the form fit on the whole
    fold-train; TRAIN rows use an EXPANDING WINDOW inside the training span (season s predicted by
    a model fit on seasons < s, with a two-season minimum), so a train row's env feature is
    out-of-sample for the env model too and stays strictly causal."""
    train, test = team_feat.loc[fold.train_idx], team_feat.loc[fold.test_idx]
    pieces: list[pd.DataFrame] = []
    seasons = sorted(train["season"].unique())
    for i, s in enumerate(seasons):
        rows = train[train["season"] == s]
        fit_on = train[train["season"] < s] if i >= 2 else train[train["season"].isin(seasons[:2])]
        pieces.append((rows, fit_on))
    pieces.append((test, train))

    out: list[pd.DataFrame] = []
    for rows, fit_on in pieces:
        if not len(rows):
            continue
        blk = rows[["season", "week", "team", "opponent"]].copy()
        for target in GE.TARGETS:
            pt, sd = _env_predict(forms[target], fit_on, target, rows)
            blk[f"_pt_{target}"], blk[f"_sd_{target}"] = pt, sd
        out.append(blk)
    env = pd.concat(out, ignore_index=True)
    env["_pt_off_plays"] = env["_pt_off_plays"].clip(lower=1.0)
    env["_pt_pass_share"] = env["_pt_pass_share"].clip(0.0, 1.0)
    return env


def attach_env_features(player: pd.DataFrame, env: pd.DataFrame, *, realized: pd.DataFrame | None = None,
                        shuffle_seed: int | None = None) -> pd.DataFrame:
    """Merge the env block onto the player rows under the pre-registered ENV_FEATURES names.

    `realized` (the ORACLE) substitutes the peeking week-w truth into ORACLE_SUBSTITUTED only —
    `_sd` keeps the model's own spread, because a realized value has no spread and zeroing it
    would change the column's MEANING rather than its accuracy.
    `shuffle_seed` permutes the env block across TEAMS within (season, week) — the Layer-B
    permutation control: the same values, the wrong teams."""
    e = env.copy()
    if realized is not None:
        r = realized.rename(columns={"off_plays": "_r_off_plays", "pass_share": "_r_pass_share"})
        e = e.merge(r[["season", "week", "team", "_r_off_plays", "_r_pass_share"]],
                    on=["season", "week", "team"], how="left")
        e["_pt_off_plays"] = e["_r_off_plays"].fillna(e["_pt_off_plays"])
        e["_pt_pass_share"] = e["_r_pass_share"].fillna(e["_pt_pass_share"])
        e = e.drop(columns=["_r_off_plays", "_r_pass_share"])
    if shuffle_seed is not None and len(e):
        rng = np.random.default_rng(shuffle_seed)
        cols = ["_pt_off_plays", "_pt_pass_share", "_sd_off_plays", "_sd_pass_share"]
        e[cols] = (e.groupby(["season", "week"], sort=False)[cols]
                   .transform(lambda s: s.to_numpy()[rng.permutation(len(s))]))

    own = e.rename(columns={
        "_pt_off_plays": "team_environment__proj_off_plays",
        "_pt_pass_share": "team_environment__proj_pass_share",
        "_sd_off_plays": "team_environment__proj_off_plays_sd"})
    own = own[["season", "week", "team", "team_environment__proj_off_plays",
               "team_environment__proj_pass_share", "team_environment__proj_off_plays_sd"]]
    opp = e.drop(columns=["opponent"]).rename(
        columns={"team": "opponent",
                 "_pt_off_plays": "opponent_matchup__proj_opp_off_plays",
                 "_pt_pass_share": "_opp_share"})
    opp = opp[["season", "week", "opponent", "opponent_matchup__proj_opp_off_plays", "_opp_share"]]

    out = player.merge(own, on=["season", "week", "team"], how="left")
    out = out.merge(opp, on=["season", "week", "opponent"], how="left")
    out["team_environment__proj_pass_plays"] = (out["team_environment__proj_off_plays"]
                                                * out["team_environment__proj_pass_share"])
    out["team_environment__proj_rush_plays"] = (out["team_environment__proj_off_plays"]
                                                * (1 - out["team_environment__proj_pass_share"]))
    out["opponent_matchup__proj_opp_pass_plays"] = (out["opponent_matchup__proj_opp_off_plays"]
                                                    * out["_opp_share"])
    return out.drop(columns=["_opp_share"])


def run_layer_b_fold(pfold: WP.Fold, tfold: WP.Fold, player: pd.DataFrame,
                     team_feat: pd.DataFrame, forms: dict[str, str]) -> dict:
    """champion vs champion_env, plus the three anchors, on ONE player fold.

    ⚠️ TWO folds, deliberately: `pfold` indexes the PLAYER matrix and `tfold` the TEAM matrix.
    They carry the same label and the same week bounds but different row indices — using one
    fold's `train_idx` against the other frame would silently select the wrong rows."""
    assert pfold.label == tfold.label, "player and team folds must be the same block"
    t0 = time.time()
    fold = pfold
    # ⚠️ the player matrix inherits `weekly_rosters`/`schedules` ERA franchise codes while the team
    # matrix is canonicalised to pbp's MODERN codes — merging them un-canonicalised NaNs exactly
    # the relocated franchises (GE.TEAM_CODE_CANON), which is the same measured defect the PIT
    # guard refused upstream, arriving from the other direction.
    player = GE.canonicalize_team_codes(player, ("team", "opponent"))
    env = env_projection_table(team_feat, tfold, forms)
    foil_forms = {t: "foil_team_eb" for t in GE.TARGETS}
    env_foil = env_projection_table(team_feat, tfold, foil_forms)
    realized = team_feat[["season", "week", "team", "off_plays", "pass_share"]]

    variants = {
        "champion_env": attach_env_features(player, env),
        "champion_env_foil": attach_env_features(player, env_foil),
        "champion_env_shuffled": attach_env_features(player, env, shuffle_seed=GE._SEED),
        "champion_env_oracle": attach_env_features(player, env, realized=realized),
    }
    base_feats = list(WP.FEATURES)
    env_feats = base_feats + list(GE.ENV_FEATURES)
    GE.assert_feature_provenance_w3(GE.ENV_FEATURES)
    # ⭐ NON-VACUITY: an all-NaN env column would make every Layer-B comparison a comparison of the
    # champion against itself and the whole gate would silently pass on nothing (NF-C0e's
    # wired-≠-invoked, NF1.7 (a)'s anchor-that-cannot-fire). Assert the block actually landed.
    scope = np.concatenate([fold.train_idx, fold.test_idx])
    env_coverage = {
        label: float(frame.loc[scope, list(GE.ENV_FEATURES)].notna().all(axis=1).mean())
        for label, frame in variants.items()
    }
    if min(env_coverage.values()) < 0.99:
        raise ValueError(
            f"the NF-W3 env block did not attach to the player frame: coverage {env_coverage} on "
            f"fold {fold.label} — a NaN env column makes champion_env identical to champion and "
            f"the Layer-B gate would pass on nothing"
        )

    test_base = player.loc[fold.test_idx]
    qmats = {"champion": WP.fit_lgbm_hurdle(player.loc[fold.train_idx], test_base, base_feats)}
    for label, frame in variants.items():
        qmats[label] = WP.fit_lgbm_hurdle(frame.loc[fold.train_idx], frame.loc[fold.test_idx],
                                          env_feats)

    scores, coverage = {}, {}
    for label, m in qmats.items():
        GE.assert_finite_predictive(m, label)
        y = test_base["fantasy_points"].to_numpy(float)
        c = WP.crps_from_quantiles(m, y)
        med = np.sort(m, axis=1)[:, len(WP.Q_LEVELS) // 2]
        s = {"pooled": float(np.mean(c)), "mae_pooled": float(np.mean(np.abs(y - med)))}
        cov = {}
        for p in WP.POSITIONS:
            sel = (test_base["position"] == p).to_numpy()
            s[p] = float(np.mean(c[sel])) if sel.any() else float("nan")
            s[f"mae_{p}"] = float(np.mean(np.abs(y[sel] - med[sel]))) if sel.any() else float("nan")
            cov[p] = WP.interval_coverage(m[sel], y[sel])
        scores[label], coverage[label] = s, cov
    log.info("[B] fold %s in %.1fs (train %d / test %d; env coverage %.4f)",
             fold.label, time.time() - t0, len(fold.train_idx), len(fold.test_idx),
             min(env_coverage.values()))
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "env_coverage": env_coverage}


def select_layer_b(pos: str, fold_results: list[dict], n_folds: int) -> dict:
    crps = pd.DataFrame({fr["label"]: {k: fr["scores"][k][pos] for k in fr["scores"]}
                         for fr in fold_results}).T
    mean_crps = crps.mean(axis=0)
    foil = GE.LAYER_B_FOIL
    winner = "champion_env"
    deltas = (crps[foil] - crps[winner]).to_numpy(float)
    mean_d, lo, hi = GE.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = list(GE.LAYER_B_ELIGIBLE)
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in GE.LAYER_B_REAL_ARMS:
        d = (crps[foil] - crps[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    shuf_lift = (crps[foil] - crps["champion_env_shuffled"]).to_numpy(float)
    p_shuf = M14.onesided_paired_pvalue(shuf_lift)
    oracle_d = (crps[foil] - crps["champion_env_oracle"]).to_numpy(float)
    o_mean, o_lo, o_hi = GE.paired_ci95(oracle_d)
    foilenv_d = (crps[foil] - crps["champion_env_foil"]).to_numpy(float)
    f_mean, f_lo, f_hi = GE.paired_ci95(foilenv_d)

    anchors = {
        "winner_beats_shuffled": bool(mean_crps["champion_env_shuffled"] > mean_crps[winner]),
        # ⛔ fails CLOSED on an unevaluable p (NF1.7 (a))
        "shuffled_lift_not_significant": bool(
            float(np.nanmean(shuf_lift)) <= 0 or (p_shuf is not None and p_shuf >= 0.05)),
        "respects_realized_oracle": bool(mean_crps[winner] >= mean_crps["champion_env_oracle"]),
    }
    covs = [fr["coverage"][winner][pos] for fr in fold_results]
    n_tot = sum(c["n"] for c in covs)
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = float(np.sqrt(GE.COVERAGE_FLOOR * (1 - GE.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")
    sd = float(np.nanstd(deltas, ddof=1))
    return {
        "position": pos, "winner": winner, "best_foil": foil,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_crps.items()},
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "mean_delta": None if mean_d is None else round(mean_d, 4),
        "ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval,
        "observed_sr": round(float(np.nanmean(deltas)) / sd, 3) if sd > 1e-12 else None,
        "var_trials_sr": round(float(np.var(np.asarray(trial_srs), ddof=1)), 5) if len(trial_srs) > 1 else None,
        "anchors": anchors,
        "oracle_ceiling": {"mean_delta": None if o_mean is None else round(o_mean, 4),
                           "ci95": [None if o_lo is None else round(o_lo, 4),
                                    None if o_hi is None else round(o_hi, 4)],
                           "fold_wins": int((oracle_d > 0).sum())},
        "foil_env_anchor": {"mean_delta": None if f_mean is None else round(f_mean, 4),
                            "ci95": [None if f_lo is None else round(f_lo, 4),
                                     None if f_hi is None else round(f_hi, 4)]},
        "shuffle_detail": {"shuffled_lift_mean": round(float(np.nanmean(shuf_lift)), 4),
                           "shuffled_lift_p_one_sided": p_shuf},
        "coverage": {"winner_coverage_80": round(cov, 4), "n_rows": int(n_tot),
                     "binomial_se": round(se, 4),
                     "blocking_shortfall": bool(n_tot and (GE.COVERAGE_FLOOR - cov)
                                                > GE.COVERAGE_BLOCK_SE * se)},
    }


def layer_b_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_champion": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < GE.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= GE.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_shuffled"]
                                    and sel["anchors"]["shuffled_lift_not_significant"]),
        "oracle_floor_respected": bool(sel["anchors"]["respects_realized_oracle"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}


# ── Multiplicity: two declared families AND the pooled correction; the stricter binds ───────────
def fdr_two_families(component_p: dict[str, float | None],
                     downstream_p: dict[str, float | None]) -> dict:
    """⭐ MH2 (a): a family may be PRE-REGISTERED, never DISCOVERED. Both declared families are
    corrected within themselves AND the pooled 6-hypothesis correction is computed; a SHIP must
    survive BOTH, so no verdict can turn on which family was chosen."""
    own = {**M14.bh_fdr(component_p, q=GE.FDR_Q), **M14.bh_fdr(downstream_p, q=GE.FDR_Q)}
    pooled_in = {f"component::{k}": v for k, v in component_p.items()}
    pooled_in.update({f"downstream::{k}": v for k, v in downstream_p.items()})
    pooled_raw = M14.bh_fdr(pooled_in, q=GE.FDR_Q)
    pooled = {k.split("::", 1)[1]: v for k, v in pooled_raw.items()}
    binding = {k: bool(own.get(k) and pooled.get(k)) for k in own}
    return {"own_family": own, "pooled": pooled, "binding": binding}


# ── Report (every verdict word DERIVED at report time — never stored; NF-W2e) ───────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W3 — game environment: team play-volume + pass/rush allocation (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**team-games:** {out['n_team_rows']} · **player-weeks:** {out['n_player_rows']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving is "
      "NF-W8 / NF-C6 Ph2). Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER "
      "selects. Every direction word below is three-way and **derived from the interval at report "
      "time**, failing closed to `TIES` (NF-W2e).")
    p("")
    p(f"**PIT gate (NF-W0a `assert_point_in_time`):** {out['pit_audit']['weeks_checked']} weeks / "
      f"{out['pit_audit']['records_checked']} team-game records checked; "
      f"{out['pit_audit']['rows_dropped']} rows in {len(out['pit_audit']['weeks_dropped'])} weeks "
      f"dropped fail-closed.")
    p("")
    p("## ⭐ Headline")
    p("")
    p(f"- **Layer A (does the component beat its own baseline?)** — "
      + " · ".join(f"{t}: **{out['verdict']['layer_a'][t]}**" for t in out["targets"]))
    lb = out["verdict"].get("layer_b") or {}
    p(f"- **Layer B (does it improve the ASSEMBLED player projection vs the NF-W1 champion?)** — "
      + (" · ".join(f"{pos}: **{lb[pos]}**" for pos in WP.POSITIONS) if lb
         else "**NOT RUN** (`--skip-layer-b`) — ⛔ a run without Layer B is a development "
              "artifact, never a verdict: Layer A alone cannot say whether the component is "
              "worth serving."))
    p("")
    p("## Layer A — the component bake-offs")
    p("")
    for t in out["targets"]:
        sel, gate = out["layer_a"][t], out["gates_a"][t]
        p(f"### `{t}` — **{out['verdict']['layer_a'][t]}**")
        p("")
        p(GE.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps": v} for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} · "
          f"p {sel['p_one_sided']} · BH own-family {out['fdr']['own_family'].get(t)} / pooled "
          f"{out['fdr']['pooled'].get(t)} (binding {out['fdr']['binding'].get(t)})")
        p(f"- anchors: {sel['anchors']}")
        p(f"- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): "
          f"{sel['oracle_detail']}")
        p(f"- permutation: {sel['permutation_detail']} · coverage(80) {sel['coverage']}")
        p(f"- MAE (report-only, never selects): {sel['mean_mae_report_only']}")
        p(f"- gate: {gate['checks']}")
        nsa = out["null_states"].get(f"layer_a::{t}", {})
        if nsa.get("field_shrink_flag"):
            f = nsa["field_shrink_flag"]
            p(f"- ⚠️ **field-shrink remedy is {f['status']}** — {f['note']}")
        p("")
    p("## ⭐ Layer B — the gate: does the environment layer move the PLAYER projection?")
    p("")
    p(f"Env forms carried into Layer B (the Layer-A winners): `{out['env_forms']}`.")
    p("")
    if not lb:
        p("**NOT RUN** in this invocation (`--skip-layer-b`).")
        p("")
    for pos in (WP.POSITIONS if lb else ()):
        sel, gate = out["layer_b"][pos], out["gates_b"][pos]
        p(f"### {pos} — **{out['verdict']['layer_b'][pos]}**")
        p("")
        p(GE.verdict_sentence("champion_env", "champion", sel["mean_delta"],
                              sel["ci95"][0], sel["ci95"][1]))
        p("")
        p(pd.DataFrame([{"label": k, "mean_crps": v} for k, v in sel["mean_crps"].items()])
          .sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        oc = sel["oracle_ceiling"]
        p(f"- ⭐ **realized-environment CEILING** (`champion_env_oracle`, peeking): "
          + GE.verdict_sentence("champion_env_oracle", "champion", oc["mean_delta"],
                                oc["ci95"][0], oc["ci95"][1])
          + f", {oc['fold_wins']}/{out['n_folds']} folds. This bounds what the ENTIRE environment "
            f"chain (NF-W3→W5→W8) can buy at the player level.")
        fe = sel["foil_env_anchor"]
        p(f"- matched foil-env anchor (env from the team-EB foil, attributing any lift to the "
          f"LEARNED component rather than to team context in any form): "
          + GE.verdict_sentence("champion_env_foil", "champion", fe["mean_delta"],
                                fe["ci95"][0], fe["ci95"][1]))
        p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} · "
          f"p {sel['p_one_sided']} · BH own-family {out['fdr']['own_family'].get(pos)} / pooled "
          f"{out['fdr']['pooled'].get(pos)} (binding {out['fdr']['binding'].get(pos)})")
        p(f"- anchors {sel['anchors']} · shuffle {sel['shuffle_detail']} · "
          f"coverage(80) {sel['coverage']}")
        p(f"- gate: {gate['checks']}")
        ns = out["null_states"].get(f"layer_b::{pos}", {})
        if ns.get("pbo_state"):
            p(f"- ⚠️ **PBO is {ns['pbo_state']}** Registering `pbo_ok` as a Layer-B gate was a "
              f"MIS-SPECIFICATION; it is left in the gate as pre-registered (⛔ a gate is not "
              f"dropped after seeing it fail) and reported as undefined rather than failed.")
        if ns.get("gate_sensitivity"):
            gs = ns["gate_sensitivity"]
            p(f"- ⭐ **the null does not rest on that gate** (NF-D15 (g″), measured): waiving "
              f"`{gs['waived']}` leaves **{gs['still_refusing']}** still refusing ⇒ ships without "
              f"the waived checks: {gs['ships_without_waived_checks']}.")
        if ns.get("hand_corrected"):
            p(f"- 🩹 **hand-corrected classification.** The instrument said "
              f"`{ns['instrument_verdict']['state']}` — \"{ns['instrument_verdict']['reason']}\" "
              f"with trigger \"{ns['instrument_verdict']['retest_trigger']}\". That is wrong on "
              f"its face at {out['n_folds']} folds: the undefined-ness comes from the FIELD SIZE "
              f"(one pre-registered contrast), not the fold count, and the trigger is negative. "
              f"Corrected state **{ns['state']}** — {ns['reason']} Re-test trigger: "
              f"{ns['retest_trigger']}")
        p("")
    p("## Null-state classification")
    p("")
    p("```json")
    p(json.dumps(out["null_states"], indent=2, default=str))
    p("```")
    p("")
    p("## Pre-registration echo")
    p("")
    p("```json")
    p(json.dumps(out["preregistration"], indent=2, default=str))
    p("```")
    path.write_text("\n".join(a))


def _classify(key: str, sel: dict, n_folds: int, n_arms: int, checks: dict) -> dict:
    hand = GE.hand_classify_refusal(checks)
    if hand is not None:
        return hand
    v = cv_power.classify_null(
        metric=key, n_folds=n_folds, n_arms=n_arms, beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=GE.FDR_Q,
        # ⭐ FACTUAL PROVENANCE, not an opt-in to DSR-CONV's gate change: `trial_srs` is built from
        # the REAL ARMS only — every degenerate is an ANCHOR by pre-registration (MH2.1 (a)) and
        # was never a trial, so no degenerate contributes to `V` (nor to the trial count). Stating
        # it removes the classifier's UNVERIFIED caveat; it changes no state.
        degenerates_excluded_from_v=True,
    )
    return GE.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger}, n_arms)


def _classify_layer_b(pos: str, sel: dict, n_folds: int, checks: dict) -> dict:
    """Layer B's classification, with the instrument's own verdict recorded beside the hand
    correction (see `GE.classify_layer_b` for why the instrument cannot speak here)."""
    v = cv_power.classify_null(
        metric=f"nf_w3_downstream_crps_{pos}", n_folds=n_folds,
        n_arms=len(GE.LAYER_B_REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=GE.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    out = GE.classify_layer_b(
        sel, n_folds=n_folds,
        instrument_verdict={"state": v.state, "reason": v.reason,
                            "retest_trigger": v.retest_trigger})
    # the null must not rest on the structurally-inapplicable PBO clause — measured, not asserted
    out["gate_sensitivity"] = GE.gate_sensitivity(checks, waived=("pbo_ok",))
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored per-position/target selections — gates, BH over
    both declared families, null states, verdicts. No refit, no fold results needed.

    This is the NF-W2e rule taken one step further: not only must a verdict SENTENCE be derived
    rather than stored, so must the VERDICT — otherwise correcting a classifier defect costs a full
    re-run, which is exactly the pressure that leaves a known-wrong state in a published record."""
    n_folds = out["n_folds"]
    component_p = {t: out["layer_a"][t]["p_one_sided"] for t in out["targets"]}
    downstream_p = {p: out["layer_b"][p]["p_one_sided"] for p in out.get("layer_b", {})}
    fdr = fdr_two_families(component_p, downstream_p)

    gates_a = {t: GE.compose_gate(out["layer_a"][t], fdr["binding"].get(t, False))
               for t in out["targets"]}
    gates_b = {p: layer_b_gate(out["layer_b"][p], fdr["binding"].get(p, False))
               for p in out.get("layer_b", {})}

    null_states: dict[str, dict] = {}
    for t in out["targets"]:
        if not gates_a[t]["ship"]:
            null_states[f"layer_a::{t}"] = _classify(
                f"nf_w3_{t}_crps", out["layer_a"][t], n_folds,
                len(GE.REAL_ARMS[t]), gates_a[t]["checks"])
    for p in out.get("layer_b", {}):
        if not gates_b[p]["ship"]:
            null_states[f"layer_b::{p}"] = _classify_layer_b(
                p, out["layer_b"][p], n_folds, gates_b[p]["checks"])

    verdict = {
        "layer_a": {t: ("SHIP" if gates_a[t]["ship"]
                        else null_states.get(f"layer_a::{t}", {}).get("state", "NULL"))
                    for t in out["targets"]},
        "layer_b": {p: ("SHIP" if gates_b[p]["ship"]
                        else null_states.get(f"layer_b::{p}", {}).get("state", "NULL"))
                    for p in out.get("layer_b", {})},
    }
    headline = ("A[" + " ".join(f"{t}:{v}" for t, v in verdict["layer_a"].items()) + "] "
                "B[" + " ".join(f"{p}:{v}" for p, v in verdict["layer_b"].items()) + "]")
    return {"fdr": fdr, "gates_a": gates_a, "gates_b": gates_b,
            "null_states": null_states, "verdict": verdict, "headline": headline}


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W3 game-environment bake-off + downstream gate")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--skip-layer-b", action="store_true",
                    help="Layer A only (development aid — a run without Layer B is NOT a verdict)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md from the stored .json — no refit (NF-W2e: a verdict "
                         "sentence must be re-derivable without a full re-run)")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w3_game_environment{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: {p: (before.get(k, {}).get(p), v) for p, v in out["verdict"][k].items()
                     if before.get(k, {}).get(p) != v} for k in out["verdict"]}
        moved = {k: v for k, v in moved.items() if v}
        if moved:
            # ⛔ never silent: a re-derivation that MOVES a verdict is a correction, and the record
            # must carry what it was before (NF-W2e — a known-wrong sentence survives when fixing
            # it is expensive or invisible).
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored per-fold selections without refitting; the prior "
                "states came from `cv_power.classify_null` called with Layer B's honest "
                "`n_arms=1`, which drove `pbo_evaluable` false and rendered the cause as a FOLD "
                "shortage ('8 fold(s) < 4') with a NEGATIVE trigger ('-4 more fold(s)')")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w3_game_environment{suffix}.md")
        log.info("report + verdict layer re-derived from %s (no refit): %s",
                 json_path.name, out["headline"])
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2))
        return 0

    t_start = time.time()
    team_feat, pit_audit = build_team_matrix(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(team_feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("Layer A: %d folds over %d team-games", n_folds, len(team_feat))

    layer_a, gates_a, a_folds = {}, {}, {}
    for target in GE.TARGETS:
        frs = [run_layer_a_fold(f, team_feat, target) for f in folds]
        a_folds[target] = [{k: fr[k] for k in ("label", "scores", "n_train", "n_test")} for fr in frs]
        layer_a[target] = select_layer_a(target, frs, n_folds)

    env_forms = {t: layer_a[t]["winner"] for t in GE.TARGETS}
    log.info("Layer-A winners → env forms for Layer B: %s", env_forms)

    layer_b, b_folds, n_player_rows = {}, [], 0
    if not args.skip_layer_b:
        player, _player_pit = build_player_matrix((2016, 2025))
        n_player_rows = int(len(player))
        pfolds = WP.build_folds(player)
        if args.smoke:
            pfolds = pfolds[-2:]
        assert [f.label for f in pfolds] == [f.label for f in folds], (
            "Layer A and Layer B must run on the SAME fold labels — a mismatched axis would make "
            "the downstream comparison an anecdote rather than a matched test")
        team_by_fold = {f.label: f for f in folds}
        frs = [run_layer_b_fold(pf, team_by_fold[pf.label], player, team_feat, env_forms)
               for pf in pfolds]
        b_folds = [{"label": fr["label"], "scores": fr["scores"]} for fr in frs]
        for pos in WP.POSITIONS:
            layer_b[pos] = select_layer_b(pos, frs, n_folds)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": GE.STORY, "smoke": bool(args.smoke), "skip_layer_b": bool(args.skip_layer_b),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": GE.SELECTION_METRIC,
        "targets": list(GE.TARGETS), "n_folds": n_folds,
        "fold_labels": [f.label for f in folds],
        "n_team_rows": int(len(team_feat)), "n_player_rows": n_player_rows,
        "pit_audit": pit_audit, "env_forms": env_forms,
        "preregistration": {
            "real_arms": {t: list(v) for t, v in GE.REAL_ARMS.items()},
            "foils": list(GE.FOILS), "anchors": {t: list(GE.anchors_for(t)) for t in GE.TARGETS},
            "eligible": {t: GE.eligible_labels(t) for t in GE.TARGETS},
            "layer_b_eligible": list(GE.LAYER_B_ELIGIBLE),
            "layer_b_anchors": list(GE.LAYER_B_ANCHORS),
            "test_blocks": [list(t) for t in GE.TEST_BLOCKS], "purge_weeks": GE.PURGE_WEEKS,
            "pbo_max": GE.PBO_MAX, "dsr_min": GE.DSR_MIN, "fdr_q": GE.FDR_Q,
            "fdr_families": {k: list(v) for k, v in GE.FDR_FAMILIES.items()},
            "coverage_floor": GE.COVERAGE_FLOOR, "eb_kappa_team": GE.EB_KAPPA_TEAM,
            "matchup_clip": list(GE.MATCHUP_CLIP), "features": list(GE.FEATURES),
            "env_features": list(GE.ENV_FEATURES),
            "era_forbidden_tokens": list(GE.ERA_FORBIDDEN_TOKENS),
            "banned_source_tokens": list(GE.BANNED_SOURCE_TOKENS),
        },
        "layer_a": layer_a, "layer_b": layer_b,
        "fold_results_a": a_folds, "fold_results_b": b_folds,
    }
    # ⭐ every decision comes from ONE derivation, shared with `--rewrite-report`, so a live run and
    # a re-derivation can never disagree about a verdict (NF-W2e, one level up from the sentence).
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w3_game_environment{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
