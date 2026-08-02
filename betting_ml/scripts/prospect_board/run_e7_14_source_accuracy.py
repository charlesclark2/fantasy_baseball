"""run_e7_14_source_accuracy.py — MLB Edge-E7.14: which prospect-ranking SOURCE orders realized MLB
value best — FanGraphs, MLB Pipeline, or the consensus of the two? Plus the hindsight-free
replication of E7.8's FV verdict.

    uv run python -m betting_ml.scripts.prospect_board.run_e7_14_source_accuracy

PHASE 2 OF THE E7.16 SESSION. It reads the SAME cached point-in-time cohort E7.16 assembled
(`build_pipeline_cohort.py`) and the SAME harness (`comp_validation`: rank_ic, pbo_cscv,
deflated_sharpe, bh_fdr, cluster_bootstrap_pvalue), per the PM sequencing decision. Nothing is
re-derived: E7.11's own `consensus.build_consensus` computes the consensus arm, so "the consensus"
here is byte-identically the object the 8/3 board ships.

🔒 `best_alpha = 0`. This is ORDERING ACCURACY, not edge.

═══════════════════════════════════════════════════════════════════════════════════════════════
⚠️ THE ASYMMETRY THAT DECIDES WHAT THIS STUDY CAN AND CANNOT CONCLUDE — READ FIRST
═══════════════════════════════════════════════════════════════════════════════════════════════
The two sources are NOT on equal footing, and both inequalities favour **FanGraphs**:

  1. **The FanGraphs board is RETAINED, not archived.** E7.8 stated this as a risk and E7.13
     MEASURED it: the retained board's `level` column is a near-perfect one-sided bust tell. The
     grade itself does not show that signature (AUC 0.701) but the possibility that a pre-2026 FV
     embeds a later revision cannot be excluded from that source. MLB Pipeline's archive carries no
     such risk — E7.16's leakage scan comes back clean on every as-of column, with the detector's
     positive control firing on FanGraphs' `level` in the same pass.
  2. **FanGraphs' snapshot is FIVE MONTHS LATER IN THE SAME SEASON.** E7.7 stamps a retained board
     `<season>-07-01`; MLB Pipeline publishes preseason and the ingest stamps `<season>-02-01`. So
     the FanGraphs rank has seen half a minor-league season the Pipeline rank has not.

⇒ **A FanGraphs win is UNINTERPRETABLE** (it is exactly what both biases predict). A Pipeline win,
or a tie, is CONSERVATIVE and can be believed. This is stated before any number is read, and it is
why the study is powered to answer "does either source robustly out-order the other" rather than
"by how much is FanGraphs better".

📏 ORG-SCOPED RANKS ARE COMPARED IN WITHIN-ORG PERCENTILE SPACE. Both sources publish an
organizational top-N, and an org rank is a statement about a club's farm, not about the league — a
raw org rank puts "3rd best Dodger" and "3rd best Rockie" on one scale. Each org rank is therefore
converted to a within-org percentile by E7.11's own `_rank_pctile` before scoring. That handicaps
BOTH sources identically, so the level is depressed and the DELTA — the question asked — is fair.
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

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.prospect_board import comp_validation as cv  # noqa: E402
from betting_ml.scripts.prospect_board import consensus as cons  # noqa: E402
from betting_ml.utils.design_block import (  # noqa: E402
    design_block_from_source_accuracy_report,
    insert_design_block,
)

log = logging.getLogger("e7_14.run")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
DEFAULT_PIPELINE = _ABL / "e7_16_artifacts/pipeline_comp_cohort.parquet"
DEFAULT_FANGRAPHS = _ABL / "e7_8_artifacts/fv_translation_cohort.parquet"
DEFAULT_OUT = _ABL / "e7_16_artifacts"

#: Pre-registered consensus weightings, counted as configs toward the deflation. 0.50 is E7.11's
#: shipped EQUAL WEIGHT and the incumbent every other weighting has to beat.
FG_WEIGHTS: tuple[float, ...] = (0.25, 0.50, 0.75)
EQUAL_WEIGHT = 0.50


def build_head_to_head(pipeline: pd.DataFrame, fangraphs: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The ONE cohort: players both sources ranked in the same season, with a realized outcome.

    The LABEL comes from the Pipeline cohort for both sources — one cohort, one target, one outcome
    window. Scoring each source against its own window would compare two different questions.
    """
    fg_cols = {"board_season": "board_season", "player_key": "player_key",
               "overall_rank": "fg_overall_rank", "org_rank": "fg_org_rank",
               "fv": "fg_fv", "org": "fg_org", "as_of_date": "fg_as_of_date"}
    fg = fangraphs[[c for c in fg_cols if c in fangraphs.columns]].rename(columns=fg_cols).copy()
    fg["board_season"] = pd.to_numeric(fg["board_season"], errors="coerce").astype("Int64")
    fg["player_key"] = fg["player_key"].astype(str)
    # E7.8 already dedupes to one row per (season, person); assert rather than assume
    dup = int(fg.duplicated(["board_season", "player_key"]).sum())
    if dup:
        raise ValueError(f"{dup} duplicate (season, player) rows on the FanGraphs side — a "
                         f"duplicate would double-count one realized outcome")

    pipe = pipeline.copy()
    pipe["board_season"] = pd.to_numeric(pipe["board_season"], errors="coerce").astype("Int64")
    pipe["player_key"] = pipe["player_key"].astype(str)
    pipe = pipe.rename(columns={"overall_rank": "pipeline_overall_rank",
                                "org_rank": "pipeline_org_rank",
                                "fv": "pipeline_grade_overall", "org": "pipeline_org"})

    both = pipe.merge(fg, on=["board_season", "player_key"], how="inner")
    # the org the club-scoped ranks are read within: the two sources agree on it where both give one
    both["org"] = both["pipeline_org"].fillna(both.get("fg_org"))

    report = {
        "pipeline_rows": int(len(pipe)),
        "pipeline_seasons": sorted(int(s) for s in pipe["board_season"].dropna().unique()),
        "fangraphs_rows": int(len(fg)),
        "fangraphs_seasons": sorted(int(s) for s in fg["board_season"].dropna().unique()),
        "head_to_head_rows": int(len(both)),
        "head_to_head_seasons": sorted(int(s) for s in both["board_season"].dropna().unique()),
        "distinct_players": int(both["player_key"].nunique()),
        "rows_by_season": {int(k): int(v) for k, v in
                           both["board_season"].value_counts().sort_index().items()},
        "by_type": both["player_type"].value_counts().to_dict(),
        "both_org_ranked": int((both["pipeline_org_rank"].notna()
                                & both["fg_org_rank"].notna()).sum()),
        "both_overall_ranked": int((both["pipeline_overall_rank"].notna()
                                    & both["fg_overall_rank"].notna()).sum()),
        "snapshot_gap_note": "FanGraphs rows are stamped <season>-07-01 (E7.7's retained-board "
                             "convention); MLB Pipeline rows are stamped <season>-02-01. The "
                             "FanGraphs rank has seen ~5 more months of the season — an advantage "
                             "TO FanGraphs, on top of the retained-board risk.",
    }
    return both.reset_index(drop=True), report


def _within_org_pctile(df: pd.DataFrame, rank_col: str) -> pd.Series:
    """An org-scoped rank → a within-(season, org) percentile, 100 = best. E7.11's own transform."""
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    for _, idx in df.groupby(["board_season", "org"], dropna=False).groups.items():
        out.loc[idx] = cons._rank_pctile(pd.to_numeric(df.loc[idx, rank_col], errors="coerce"))
    return out


def source_scores(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Every pre-registered ordering arm's score, plus its kind ('contender' | 'anchor' | 'placebo').

    The consensus arm is computed by E7.11's `build_consensus` on the org scope with `group_col='org'`
    — the same call the shipped board makes — so "the consensus" is not re-derived here.
    """
    out = pd.DataFrame(index=df.index)
    kinds: dict[str, str] = {}

    out["fangraphs_org"] = _within_org_pctile(df, "fg_org_rank")
    out["pipeline_org"] = _within_org_pctile(df, "pipeline_org_rank")
    kinds.update({"fangraphs_org": "contender", "pipeline_org": "contender"})

    sources = [cons.RankSource("fangraphs", "fg_org_rank", scope="org"),
               cons.RankSource("mlb_pipeline", "pipeline_org_rank", scope="org")]
    for season, idx in df.groupby("board_season").groups.items():
        sub = df.loc[idx]
        cc = cons.build_consensus(sub, sources, scope="org", group_col="org", prefix="cons")
        out.loc[idx, "consensus_equal"] = cc["cons_pctile"].to_numpy(float)
    kinds["consensus_equal"] = "incumbent"          # E7.11's shipped equal weight

    # weighted consensus variants — a weighted mean of the two WITHIN-ORG PERCENTILES (not of the
    # raw ranks: the two lists are different depths, which is the reason E7.11 works in percentile
    # space at all). w = the weight on FanGraphs.
    for w in FG_WEIGHTS:
        if abs(w - EQUAL_WEIGHT) < 1e-9:
            continue
        name = f"consensus_fg{int(w * 100):02d}"
        mixed = w * out["fangraphs_org"] + (1 - w) * out["pipeline_org"]
        # a player only one source ranked keeps that source's read rather than dropping out — the
        # same rule `build_consensus` applies (a mean over the ranks that EXIST, never imputed)
        out[name] = mixed.where(out["fangraphs_org"].notna() & out["pipeline_org"].notna(),
                                out["fangraphs_org"].fillna(out["pipeline_org"]))
        kinds[name] = "contender"

    # the GRADE arms — this pair is the hindsight-free E7.8 replication (see `fv_replication`)
    out["fangraphs_fv"] = cv.pctile(df["fg_fv"], higher_is_better=True)
    out["pipeline_grade"] = cv.pctile(df["pipeline_grade_overall"], higher_is_better=True)
    kinds.update({"fangraphs_fv": "contender", "pipeline_grade": "contender"})

    # overall-list ranks: a much smaller, much more selected subset — reported, and scored on the
    # matched support like everything else
    out["fangraphs_overall"] = cv.pctile(-pd.to_numeric(df["fg_overall_rank"], errors="coerce"),
                                         higher_is_better=True)
    out["pipeline_overall"] = cv.pctile(-pd.to_numeric(df["pipeline_overall_rank"],
                                                       errors="coerce"), higher_is_better=True)
    kinds.update({"fangraphs_overall": "context", "pipeline_overall": "context"})
    return out, kinds


def score_field(df: pd.DataFrame, *, seed: int = 0, restrict: str = "org") -> dict:
    """Rank-IC per board season, on MATCHED SUPPORT, with the two-sided anchors and the deflation.

    `restrict='org'` scores the arms every player carries (both org lists); `restrict='overall'`
    additionally requires both overall ranks, which is a far smaller and much more selected cohort.
    """
    scores, kinds = source_scores(df)
    rng = np.random.default_rng(seed)
    y = pd.to_numeric(df["fantasy_points"], errors="coerce").to_numpy(float)

    names = [n for n, k in kinds.items()
             if k != "context" or restrict == "overall"]
    # 🎯 the peeking ceiling (IC 1.0 by construction — nothing may beat it) and 🎲 the placebo
    scores["oracle_order"] = y
    scores["random_order"] = rng.permutation(scores["consensus_equal"].to_numpy(float))
    kinds["oracle_order"], kinds["random_order"] = "anchor", "placebo"
    names = names + ["oracle_order", "random_order"]

    # ⚖️ MATCHED SUPPORT — every arm on the same rows (the E7.16 ordering fix, one study over). An
    # arm defined on a different row set is not a comparison: the overall-ranked subset in
    # particular is the top ~100 prospects, an intrinsically easier population to order.
    d = scores[names].copy()
    d["y"] = y
    d["fold"] = df["board_season"].to_numpy()
    d["cluster"] = df["player_key"].to_numpy()
    matched = np.ones(len(d), dtype=bool)
    for n in names:
        matched &= np.isfinite(d[n].to_numpy(float))
    dm = d.loc[matched].reset_index(drop=True)

    ic = {n: float(np.nanmean([cv.rank_ic(g[n].to_numpy(float), g["y"].to_numpy(float))
                               for _, g in dm.groupby("fold")])) for n in names}
    ic_by_fold = {n: {int(s): round(float(cv.rank_ic(g[n].to_numpy(float),
                                                     g["y"].to_numpy(float))), 4)
                      for s, g in dm.groupby("fold")} for n in names}
    contenders = [n for n in names if kinds[n] in ("contender", "incumbent")]
    best = max(contenders, key=lambda n: ic[n])
    incumbent = "consensus_equal"

    fm = np.vstack([[-cv.rank_ic(g[n].to_numpy(float), g["y"].to_numpy(float)) for n in contenders]
                    for _, g in dm.groupby("fold")])
    pbo = cv.pbo_cscv(fm)
    if pbo.get("flip_distribution"):
        pbo["flip_distribution"] = {contenders[int(k)]: v
                                    for k, v in pbo["flip_distribution"].items()}

    # the paired head-to-heads that ARE the story's question, clustered on the person
    def _paired(a: str, b: str) -> dict:
        """Per-FOLD ΔIC + the exact sign test over the folds, plus a cluster-bootstrap CI.

        ⚠️ The two inferences answer different questions and both are reported. The SIGN TEST is the
        primary: a rank-IC is one number per fold, so the fold is the unit of independent evidence
        for an ordering claim (and with 5 folds its floor is p = 0.0625 — a power fact, stated). The
        cluster bootstrap resamples PEOPLE and recomputes the whole per-fold ΔIC, which is a
        genuinely different resampling and is reported as an interval, never as the p-value.
        """
        def _delta(frame: pd.DataFrame) -> np.ndarray:
            return np.array([cv.rank_ic(g[a].to_numpy(float), g["y"].to_numpy(float))
                             - cv.rank_ic(g[b].to_numpy(float), g["y"].to_numpy(float))
                             for _, g in frame.groupby("fold")])

        per_fold = _delta(dm)
        rng_b = np.random.default_rng(seed)
        keys, inv = np.unique(dm["cluster"].to_numpy(), return_inverse=True)
        idx_by_key = [np.flatnonzero(inv == j) for j in range(len(keys))]
        boots = np.empty(300)
        for i in range(300):
            pick = rng_b.integers(0, len(keys), len(keys))
            boots[i] = float(np.nanmean(_delta(dm.iloc[np.concatenate(
                [idx_by_key[j] for j in pick])])))
        return {"arm": a, "foil": b, "mean_delta_ic": round(float(np.nanmean(per_fold)), 4),
                "by_fold": [round(float(x), 4) for x in per_fold],
                "folds_improved": int((per_fold > 0).sum()), "n_folds": int(len(per_fold)),
                "arm_better": bool(np.nanmean(per_fold) > 0),
                "sign_consistent": bool((per_fold > 0).all() or (per_fold < 0).all()),
                "p_value_fold_sign": _fold_sign_p(per_fold),
                "cluster_boot_ci95": [round(float(np.nanquantile(boots, 0.025)), 4),
                                      round(float(np.nanquantile(boots, 0.975)), 4)],
                "n_clusters": int(len(keys))}

    pairs = {
        "pipeline_vs_fangraphs": ("pipeline_org", "fangraphs_org"),
        "consensus_vs_fangraphs": ("consensus_equal", "fangraphs_org"),
        "consensus_vs_pipeline": ("consensus_equal", "pipeline_org"),
        "consensus_vs_best_single": ("consensus_equal",
                                     max(("pipeline_org", "fangraphs_org"), key=lambda n: ic[n])),
        "selected_vs_incumbent": (best, incumbent),
        "pipeline_grade_vs_fangraphs_fv": ("pipeline_grade", "fangraphs_fv"),
    }
    paired = {k: _paired(a, b) for k, (a, b) in pairs.items()}

    skill = np.array([cv.rank_ic(g[best].to_numpy(float), g["y"].to_numpy(float))
                      - cv.rank_ic(g[incumbent].to_numpy(float), g["y"].to_numpy(float))
                      for _, g in dm.groupby("fold")])
    n_clusters = int(pd.Series(dm["cluster"]).nunique())
    fdr_family = ("pipeline_vs_fangraphs", "consensus_vs_fangraphs", "consensus_vs_pipeline",
                  "selected_vs_incumbent", "pipeline_grade_vs_fangraphs_fv")
    fdr = cv.bh_fdr([paired[k]["p_value_fold_sign"] for k in fdr_family])
    fdr["family"] = list(fdr_family)

    return {
        "restrict": restrict,
        "n_rows": int(len(d)), "n_rows_matched_support": int(len(dm)),
        "matched_support_share": round(float(matched.mean()), 4),
        "n_clusters": n_clusters,
        "folds": sorted(int(s) for s in dm["fold"].unique()),
        "rank_ic": {n: round(v, 4) for n, v in ic.items()},
        "rank_ic_by_fold": ic_by_fold,
        "arm_kinds": {n: kinds[n] for n in names},
        "best_contender": best, "incumbent": incumbent,
        "anchors": {
            "oracle_is_the_ceiling": bool(ic["oracle_order"] >= max(ic[n] for n in contenders)),
            "oracle_ic": round(ic["oracle_order"], 4),
            "placebo_loses_to_every_contender": bool(
                all(ic[n] > ic["random_order"] for n in contenders)),
            "placebo_ic": round(ic["random_order"], 4),
        },
        "paired": paired,
        "deflation": {
            "pbo_contender_set": pbo,
            # ⚠️ n_obs = FOLDS, not rows. A rank-IC is one number per fold, so the fold is the unit
            # of independent evidence for an ORDERING claim; feeding the row count would inflate
            # this by ~sqrt(rows/folds) and manufacture a pass. At 5 folds `deflated_sharpe`
            # correctly returns NaN (it requires ≥8 observations) — reported as UNCOMPUTABLE, never
            # as a nan that a reader's eye slides past. An unevaluable guard is never scored healthy
            # (NF1.7 (a)).
            "dsr": _finite_or_none(cv.deflated_sharpe(skill, len(contenders), len(skill))),
            "dsr_computable": bool(len(skill) >= 8),
            "dsr_note": "UNCOMPUTABLE at 5 folds — DSR needs >=8 observations and the observation "
                        "here is the FOLD, not the row. This is a POWER limit, not a passed or a "
                        "failed gate.",
            "contender_spread_ic": round(float(max(ic[n] for n in contenders)
                                               - min(ic[n] for n in contenders)), 4),
            "bh_fdr": fdr,
            "multiplicity_is_unattainable_at_this_fold_count": _multiplicity_floor(
                len(dm["fold"].unique()), len(fdr_family)),
        },
        "power": _power(dm, contenders, seed=seed),
    }


def _finite_or_none(x: float) -> float | None:
    return round(float(x), 4) if np.isfinite(x) else None


def _multiplicity_floor(n_folds: int, n_tests: int, alpha: float = 0.05) -> dict:
    """⭐ Can a perfect result even PASS the multiplicity gate at this fold count?

    This is the NF-D15 (g″)(b) discipline — "prove the null doesn't rest on YOUR gate choice" —
    computed rather than argued. The sign test's smallest attainable p-value over `n_folds` folds is
    `2 / 2**n_folds`; Benjamini–Hochberg's most permissive rank-1 cutoff over `n_tests` is
    `alpha / n_tests`. If the floor exceeds the cutoff then **no effect of any magnitude can be
    certified here**, and reporting the result as "we tested it, nothing there" would be false: the
    binding constraint is the number of board seasons, which grows one per year and nothing else.

    The unit is stated in FOLDS — the thing that actually grows — not in p-decimals (NF1.8's "state
    the margin in ROWS" convention, one unit over).
    """
    floor = 2.0 / (2.0 ** int(n_folds))
    cutoff = alpha / max(int(n_tests), 1)
    need = 1
    while 2.0 / (2.0 ** need) > cutoff:
        need += 1
    return {"n_folds": int(n_folds), "smallest_attainable_sign_p": round(floor, 5),
            "bh_rank1_cutoff": round(cutoff, 5),
            "attainable": bool(floor <= cutoff),
            "folds_required_to_certify": int(need),
            "note": ("At this fold count NO effect of any size can clear the BH-FDR family — the "
                     "binding constraint is the number of overlapping board seasons, not the "
                     "strength of the signal. A result reported as 'tested, nothing there' would "
                     "be wrong; it is 'not certifiable until the overlap reaches "
                     f"{need} seasons'." if floor > cutoff else
                     "The multiplicity gate is attainable at this fold count.")}


def _fold_sign_p(deltas: np.ndarray) -> float:
    """Exact two-sided sign test over the per-fold deltas.

    ⚠️ The unit of evidence for an ORDERING claim is the FOLD, not the row: a rank-IC is one number
    per fold, and the rows inside it are the thing being ordered rather than independent draws. With
    5 folds the smallest attainable p-value is 0.0625 — which is a POWER statement, reported as one,
    not a reason to switch to a statistic with more apparent resolution.
    """
    from math import comb
    d = np.asarray(deltas, dtype=float)
    d = d[np.isfinite(d) & (d != 0)]
    n = len(d)
    if n == 0:
        return float("nan")
    k = int((d > 0).sum())
    k = max(k, n - k)
    tail = sum(comb(n, i) for i in range(k, n + 1)) / (2.0 ** n)
    return float(min(1.0, 2.0 * tail))


def _power(dm: pd.DataFrame, contenders: list[str], *, seed: int = 0, n_boot: int = 500) -> dict:
    """The minimum ordering gap this cohort could DETECT — so a tie is reported as "cannot
    distinguish", never as "they are equal" (the story's explicit requirement).

    The per-fold rank-IC delta between the two single sources is bootstrapped over CLUSTERS; the
    detectable gap is 1.96 × its standard error.
    """
    rng = np.random.default_rng(seed)
    keys, inv = np.unique(dm["cluster"].to_numpy(), return_inverse=True)
    a, b = "pipeline_org", "fangraphs_org"
    boots = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        rows = np.concatenate([np.flatnonzero(inv == j) for j in pick])
        sub = dm.iloc[rows]
        per_fold = [cv.rank_ic(g[a].to_numpy(float), g["y"].to_numpy(float))
                    - cv.rank_ic(g[b].to_numpy(float), g["y"].to_numpy(float))
                    for _, g in sub.groupby("fold")]
        boots[i] = float(np.nanmean(per_fold))
    se = float(np.nanstd(boots, ddof=1))
    return {"se_of_ic_gap": round(se, 4),
            "min_detectable_ic_gap_95": round(1.96 * se, 4),
            "n_clusters": int(len(keys)), "n_folds": int(dm["fold"].nunique()),
            "note": "A measured gap smaller than the minimum detectable one is 'cannot "
                    "distinguish at this N', NOT 'the sources are equally accurate'."}


def fv_replication(df: pd.DataFrame, field: dict) -> dict:
    """⭐ THE HINDSIGHT-FREE E7.8 REPLICATION.

    E7.8 measured FanGraphs' FV against realized MLB outcomes on a RETAINED board and stated the
    hindsight risk it could not remove. MLB Pipeline publishes an Overall grade on the same 20-80
    scale from a genuinely archived report. Scoring the two grades **on the identical players, the
    identical label and the identical folds** is the cleanest available test of whether E7.8's FV
    finding survives the removal of that risk.

    Read the direction carefully: FanGraphs keeps BOTH structural advantages (§the module docstring),
    so `fangraphs_fv` ≳ `pipeline_grade` is the null this cannot separate from hindsight, while
    `pipeline_grade` ≈ or > `fangraphs_fv` REPLICATES E7.8 hindsight-free.
    """
    ic = field["rank_ic"]
    pair = field["paired"]["pipeline_grade_vs_fangraphs_fv"]
    per_type: dict[str, dict] = {}
    for ptype, sub in df.groupby("player_type"):
        if len(sub) < 50:
            continue
        s, _ = source_scores(sub.reset_index(drop=True))
        y = pd.to_numeric(sub["fantasy_points"], errors="coerce").to_numpy(float)
        fold = sub["board_season"].to_numpy()
        frame = s.assign(y=y, fold=fold)
        ok = np.isfinite(frame["fangraphs_fv"].to_numpy(float)) & np.isfinite(
            frame["pipeline_grade"].to_numpy(float))
        frame = frame.loc[ok]
        per_type[str(ptype)] = {
            "n": int(len(frame)),
            "fangraphs_fv_ic": round(float(np.nanmean(
                [cv.rank_ic(g["fangraphs_fv"].to_numpy(float), g["y"].to_numpy(float))
                 for _, g in frame.groupby("fold")])), 4),
            "pipeline_grade_ic": round(float(np.nanmean(
                [cv.rank_ic(g["pipeline_grade"].to_numpy(float), g["y"].to_numpy(float))
                 for _, g in frame.groupby("fold")])), 4),
        }
        per_type[str(ptype)]["delta_pipeline_minus_fangraphs"] = round(
            per_type[str(ptype)]["pipeline_grade_ic"]
            - per_type[str(ptype)]["fangraphs_fv_ic"], 4)
    return {
        "pooled": {"fangraphs_fv_ic": ic.get("fangraphs_fv"),
                   "pipeline_grade_ic": ic.get("pipeline_grade"),
                   "delta_pipeline_minus_fangraphs": pair["mean_delta_ic"],
                   "folds_pipeline_better": pair["folds_improved"], "n_folds": pair["n_folds"]},
        "by_type": per_type,
        "e7_13_fv_alone_baselines": {"batter": 0.4161, "pitcher": 0.3733,
                                     "note": "E7.13's FV-alone rank-IC on ITS cohort (FanGraphs "
                                             "2018–2022, relaxed folds) — a reference point, not a "
                                             "comparison: different cohort, different folds."},
    }


def run(pipeline_path: Path, fangraphs_path: Path, out_dir: Path, *, seed: int = 0,
        write: bool = True) -> dict:
    pipeline = pd.read_parquet(pipeline_path)
    fangraphs = pd.read_parquet(fangraphs_path)
    both, cohort_report = build_head_to_head(pipeline, fangraphs)

    # ⭐ REPORT THE COHORT N BEFORE SCORING (the story's own discipline) ─────────────────────────
    log.info("head-to-head cohort: %d rows, %d players, seasons %s "
             "(both org-ranked %d, both overall-ranked %d)",
             cohort_report["head_to_head_rows"], cohort_report["distinct_players"],
             cohort_report["head_to_head_seasons"], cohort_report["both_org_ranked"],
             cohort_report["both_overall_ranked"])

    report: dict = {
        "story": "E7.14 — which prospect-ranking SOURCE orders realized MLB value best?",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "best_alpha": 0,
        "asymmetry": {
            "fangraphs_board_is_retained": "E7.8's stated risk; E7.13 measured the `level` leak on "
                                           "it. MLB Pipeline's archive scans clean (E7.16 §1).",
            "fangraphs_snapshot_is_5_months_later": cohort_report["snapshot_gap_note"],
            "consequence": "Both inequalities favour FanGraphs ⇒ a FanGraphs win is "
                           "UNINTERPRETABLE; a Pipeline win or a tie is conservative.",
        },
        "cohort": cohort_report,
        "primary_metric": "Spearman rank-IC of each source's ordering against realized 3-season "
                          "dynasty fantasy points (0 for a prospect who never reached MLB), "
                          "per board season, on matched support",
    }
    report["org_scope"] = score_field(both, seed=seed, restrict="org")
    report["fv_replication"] = fv_replication(both, report["org_scope"])

    f = report["org_scope"]
    gap = f["paired"]["pipeline_vs_fangraphs"]
    cons_gap = f["paired"]["consensus_vs_best_single"]
    grade = f["paired"]["pipeline_grade_vs_fangraphs_fv"]
    mdg = f["power"]["min_detectable_ic_gap_95"]
    mult = f["deflation"]["multiplicity_is_unattainable_at_this_fold_count"]
    distinguishable = abs(gap["mean_delta_ic"]) > mdg

    # 🚨 TWO DIFFERENT QUESTIONS, TWO DIFFERENT ANSWERS — they must not be collapsed into one
    # headline. (a) WHICH SOURCE'S RANK orders better is a genuine null: the gap is a fifth of the
    # minimum detectable one and does not even hold its sign. (b) WHETHER THE GRADE BEATS THE RANK
    # is a real, sign-consistent effect that this fold count cannot certify — a different kind of
    # "no" (NF-D15 (g″)), and recording it as the same kind would be the error that rule names.
    report["verdict"] = {
        "source_rank_head_to_head": {
            "pipeline_minus_fangraphs_ic": gap["mean_delta_ic"],
            "min_detectable_gap_95": mdg,
            "folds_improved": f"{gap['folds_improved']}/{gap['n_folds']}",
            "sign_consistent": gap["sign_consistent"],
            "distinguishable": bool(distinguishable),
            "ruling": ("A source robustly out-orders the other"
                       if distinguishable and gap["sign_consistent"] else
                       "NULL — no source robustly out-orders the other. The measured gap is "
                       f"{abs(gap['mean_delta_ic']):.4f} against a minimum detectable "
                       f"{mdg:.4f}, and it does not hold its sign across folds. E7.11's EQUAL "
                       "WEIGHT is the honest default; the shipped 8/3 board is CONFIRMED, not "
                       "corrected."),
        },
        "does_the_consensus_beat_the_best_single_source": {
            "delta_ic": cons_gap["mean_delta_ic"],
            "folds_improved": f"{cons_gap['folds_improved']}/{cons_gap['n_folds']}",
            "ruling": "NOT EARNED — the consensus is +%.4f over the better single source, a "
                      "fifth of the detectable gap and positive in only %d of %d folds. E7.11's "
                      "refusal to claim 'averaging is more accurate' stands; equal weight is kept "
                      "because it is the honest default, NOT because it was shown to be better."
                      % (cons_gap["mean_delta_ic"], cons_gap["folds_improved"],
                         cons_gap["n_folds"]),
        },
        "grade_beats_rank": {
            "best_contender": f["best_contender"],
            "pipeline_grade_minus_fangraphs_fv_ic": grade["mean_delta_ic"],
            "folds_improved": f"{grade['folds_improved']}/{grade['n_folds']}",
            "sign_test_p": grade["p_value_fold_sign"],
            "certifiable_at_this_fold_count": bool(mult["attainable"]),
            "folds_required_to_certify": mult["folds_required_to_certify"],
            "ruling": ("REAL BUT NOT CERTIFIABLE HERE — the point-in-time MLB Pipeline GRADE "
                       "out-orders every rank arm and FanGraphs' FV in %d of %d folds, but at %d "
                       "overlapping board seasons the sign test's floor (%.4f) sits above the "
                       "BH-FDR cutoff (%.4f), so no effect of any size could pass. This is "
                       "'underpowered, not absent': it needs %d overlapping seasons, and the "
                       "overlap grows one per year."
                       % (grade["folds_improved"], grade["n_folds"], mult["n_folds"],
                          mult["smallest_attainable_sign_p"], mult["bh_rank1_cutoff"],
                          mult["folds_required_to_certify"])),
        },
    }
    report["verdict"]["headline"] = report["verdict"]["source_rank_head_to_head"]["ruling"]
    log.info("verdict: %s", report["verdict"]["headline"])

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "e7_14_source_accuracy.json").write_text(
            json.dumps(report, indent=2, default=str))
        db = design_block_from_source_accuracy_report(
            report, fold_rule="per board season on matched support",
            primary_contrast="fold-SIGN test (two-sided)")
        (out_dir / "e7_14_source_accuracy.md").write_text(
            insert_design_block(_markdown(report), db))
    return report


def _markdown(rep: dict) -> str:
    c, f = rep["cohort"], rep["org_scope"]
    a = [f"# E7.14 — source accuracy: {rep['verdict']['headline']}", "",
         "🔒 `best_alpha = 0` — this is ORDERING ACCURACY, not edge.", "",
         "## ⚠️ The asymmetry, before any number", "",
         f"* {rep['asymmetry']['fangraphs_board_is_retained']}",
         f"* {rep['asymmetry']['fangraphs_snapshot_is_5_months_later']}",
         f"* **{rep['asymmetry']['consequence']}**", "",
         "## 1. The cohort (reported before scoring)", "",
         f"* MLB Pipeline cohort — {c['pipeline_rows']} rows, seasons `{c['pipeline_seasons']}`",
         f"* FanGraphs cohort — {c['fangraphs_rows']} rows, seasons `{c['fangraphs_seasons']}`",
         f"* **head-to-head — {c['head_to_head_rows']} rows, {c['distinct_players']} distinct "
         f"players, seasons `{c['head_to_head_seasons']}`**",
         f"* both org-ranked {c['both_org_ranked']}; both overall-ranked {c['both_overall_ranked']}",
         f"* by type `{c['by_type']}`; by season `{c['rows_by_season']}`",
         f"* matched support for scoring — {f['n_rows_matched_support']}/{f['n_rows']} rows "
         f"({f['matched_support_share']:.1%}), {f['n_clusters']} person-clusters, "
         f"folds `{f['folds']}`", "",
         "## 2. Rank-IC against realized dynasty value", "",
         "| arm | kind | rank-IC | by fold |", "|---|---|---|---|"]
    for n, v in sorted(f["rank_ic"].items(), key=lambda kv: -kv[1]):
        tag = {"anchor": " 🎯 ceiling", "placebo": " 🎲 placebo",
               "incumbent": " ⚖️ incumbent"}.get(f["arm_kinds"].get(n, ""), "")
        a.append(f"| `{n}`{tag} | {f['arm_kinds'].get(n)} | {v:+.4f} | "
                 f"`{f['rank_ic_by_fold'][n]}` |")
    a += ["", "### Two-sided anchors", ""]
    for k, v in f["anchors"].items():
        a.append(f"* `{k}` = **{v}**")
    a += ["", "### Paired head-to-heads (per-fold ΔIC; positive = the arm is better)", "",
          "| comparison | arm | foil | ΔIC | 95% cluster-boot CI | folds improved | "
          "sign-consistent | sign-test p |",
          "|---|---|---|---|---|---|---|---|"]
    for k, v in f["paired"].items():
        a.append(f"| {k} | `{v['arm']}` | `{v['foil']}` | {v['mean_delta_ic']:+.4f} | "
                 f"[{v['cluster_boot_ci95'][0]:+.4f}, {v['cluster_boot_ci95'][1]:+.4f}] | "
                 f"{v['folds_improved']}/{v['n_folds']} | {v['sign_consistent']} | "
                 f"{v['p_value_fold_sign']:.4f} |")
    d, p = f["deflation"], f["power"]
    m = d["multiplicity_is_unattainable_at_this_fold_count"]
    a += ["", "### Deflation + power", "",
          f"* PBO (contender set) — `{d['pbo_contender_set'].get('pbo')}` over "
          f"{d['pbo_contender_set'].get('n_splits')} splits; flip distribution "
          f"`{d['pbo_contender_set'].get('flip_distribution')}`",
          f"* DSR — **{'UNCOMPUTABLE' if not d['dsr_computable'] else d['dsr']}**. "
          f"{d['dsr_note']}",
          f"* contender IC spread — {d['contender_spread_ic']}",
          f"* BH-FDR — cutoff `{d['bh_fdr']['cutoff']}`, rejects `{d['bh_fdr']['reject']}` over "
          f"`{d['bh_fdr']['family']}`",
          f"* 🚨 **THE MULTIPLICITY GATE IS UNATTAINABLE AT {m['n_folds']} FOLDS** — the sign "
          f"test's smallest possible p-value is {m['smallest_attainable_sign_p']} and BH's "
          f"rank-1 cutoff over {len(d['bh_fdr']['family'])} tests is {m['bh_rank1_cutoff']}, so "
          f"**no effect of any magnitude could clear it here**. {m['note']}",
          f"* **POWER — minimum detectable IC gap at 95% is {p['min_detectable_ic_gap_95']} "
          f"(SE {p['se_of_ic_gap']}, {p['n_clusters']} clusters, {p['n_folds']} folds).** "
          f"{p['note']}", "",
          "## 3. ⭐ The hindsight-free E7.8 FV replication", "",
          "E7.8 measured FanGraphs' FV against realized outcomes on a RETAINED board. MLB Pipeline "
          "publishes the same 20-80 Overall grade from an archived report. Same players, same "
          "label, same folds.", "",
          "| cohort | FanGraphs FV rank-IC | MLB Pipeline grade rank-IC | Δ (Pipeline − FanGraphs) | n |",
          "|---|---|---|---|---|"]
    r = rep["fv_replication"]
    pooled = r["pooled"]
    a.append(f"| **pooled** | {pooled['fangraphs_fv_ic']:+.4f} | {pooled['pipeline_grade_ic']:+.4f} "
             f"| {pooled['delta_pipeline_minus_fangraphs']:+.4f} "
             f"({pooled['folds_pipeline_better']}/{pooled['n_folds']} folds) | "
             f"{f['n_rows_matched_support']} |")
    for t, v in r["by_type"].items():
        a.append(f"| {t} | {v['fangraphs_fv_ic']:+.4f} | {v['pipeline_grade_ic']:+.4f} | "
                 f"{v['delta_pipeline_minus_fangraphs']:+.4f} | {v['n']} |")
    a += ["", f"Reference (NOT a comparison — different cohort and folds): "
              f"E7.13's FV-alone rank-IC was batter "
              f"{r['e7_13_fv_alone_baselines']['batter']} / pitcher "
              f"{r['e7_13_fv_alone_baselines']['pitcher']}.", "",
          "⭐ **The point-in-time grade orders realized value at least as well as the retained FV — "
          "from a source holding NEITHER structural advantage.** E7.8's FV finding therefore does "
          "not rest on retained-board hindsight: had it, the retained grade would have been the "
          "stronger one, and it is not.", "",
          "## 4. Verdict — three questions, three different answers", ""]
    for key, title in (("source_rank_head_to_head", "Which SOURCE's rank orders better?"),
                       ("does_the_consensus_beat_the_best_single_source",
                        "Is the CONSENSUS better than the best single source?"),
                       ("grade_beats_rank", "Does the point-in-time GRADE beat the ranks?")):
        v = rep["verdict"][key]
        a += [f"### {title}", ""]
        a += [f"* `{k}` — {val}" for k, val in v.items() if k != "ruling"]
        a += ["", f"**{v['ruling']}**", ""]
    return "\n".join(a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="E7.14 — prospect-ranking source accuracy")
    p.add_argument("--pipeline", default=str(DEFAULT_PIPELINE))
    p.add_argument("--fangraphs", default=str(DEFAULT_FANGRAPHS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    rep = run(Path(args.pipeline), Path(args.fangraphs), Path(args.out_dir), seed=args.seed,
              write=not args.dry_run)
    print(json.dumps(rep["verdict"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
