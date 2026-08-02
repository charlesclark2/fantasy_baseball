"""run_e7_15_h1.py — MLB Edge-E7.15 H1: the §0.5 bake-off for the WITHIN-PLAYER level-translation ladder.

⚠️ **OPERATOR-RUN (>2 min).** ~10 arms × the side's metrics × leave-one-debut-cohort-out folds, each an
EB variance-component search, plus a per-fold promotion-hazard fit for the propensity terciles.
`--transitions-only` is a seconds-long census; `--metrics iso --arms L0_foil L1_chain_ols` is the cheap
scoring smoke.

    # 0. the cached matrices (assemble ONCE — the §0.5 cost-hygiene rule; both already exist from E7.12)
    uv run python -m betting_ml.scripts.milb_mle.build_graduated_pairs --season-floor 2015
    uv run python -m betting_ml.scripts.milb_mle.build_park_context   --season-floor 2015
    # 1. the per-rung census — REPORTED BEFORE ANY SCORE (readiness lock 2)
    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h1 --transitions-only
    # 2. the bake-off
    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h1
    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h1 --player-type pitcher

WHAT IT DECIDES
---------------
For each metric, whether learning the level-translation ladder from WITHIN-PLAYER minor→minor transitions
beats the **shipped E7.12-slice-1 configuration** on held-out translation accuracy by enough to survive
deflation. A null arm is **DROPPED, not shipped**. `best_alpha = 0`.

THIS IS A BAKE-OFF, NOT A SINGLE LADDER (readiness lock 1)
----------------------------------------------------------
§0.5 forbids testing one architecture and calling its miss a null. Four ladder FORMULATIONS are
pre-registered against a DIRECT-LEARNED FOIL:

  | arm                   | formulation                                                              |
  |-----------------------|--------------------------------------------------------------------------|
  | `L0_foil`             | ⭐ the shipped slice-1 configuration, NO ladder — the matched pair         |
  | `L1_chain_ols`        | composed adjacent-rung OLS maps (A→A+→AA→AAA)                            |
  | `L2_chain_paweighted` | the same chain, rung regressions weighted by pair line-length             |
  | `L3_direct_to_ref`    | one-step (level → Triple-A) maps from the players who made that jump      |
  | `L4_ladder_delta`     | the raw line KEPT, the ladder delta added as a fixed regressor (NESTS L0) |

`L1` vs `L2` is itself a matched pair (weighting alone), and `L3` vs `L1` isolates the compounding
attenuation the module's docstring pre-registers as the chain's structural hazard. `L4` is the cleanest
"does the ladder ADD information" test, because it contains the foil at coefficient 0.

⭐ **THE LEARNER IS HELD FIXED** at each metric's pinned E7.3 prior scale, with the shipped slice-1
`weight_col`, for every arm. E7.9 measured that 54–77% of a bake-off leader's apparent margin can be the
LEARNER swap rather than the mechanism; here the only thing that varies is the feature.

🪤 **WHAT WOULD MAKE THIS LIE, AND THE ANCHOR THAT CATCHES EACH** (the two-sided-anchor rule):

  | trap                                                        | anchor                | must hold             |
  |-------------------------------------------------------------|-----------------------|-----------------------|
  | the ladder CODE PATH itself perturbs the fit                 | `A_ladder_identity`   | byte no-op vs L0      |
  | it is really a per-level RE-CENTRING, not per-player content | `A_ladder_meanshift`  | must LOSE (NF-D15 g′) |
  | the marginals do the work; the within-player link is fake    | `A_ladder_shuffled`   | must LOSE             |
  | MAE is inverted on this cohort                               | `A_degenerate_mean`   | must LOSE (NF-D14)    |

  plus the ORACLE FLOOR (no candidate may score MAE < 0), and — the NF1.7 (a) lesson — a MISSING anchor
  is a hard failure, never a vacuous pass.

📏 **PER-PROPENSITY-TERCILE SCORING (H5).** Every arm is also scored inside promotion-propensity terciles
computed by E7.12 slice 2's hazard, fit on seasons strictly before the held-out cohort. The board serves
UN-PROMOTED prospects, and slice 2 measured its winner helping the low tercile +0.54% against +0.07% at
the high end. A board metric whose winner is NEGATIVE in the low tercile is downgraded: it improves the
players we do not serve.

🔒 **ESTIMAND PRESERVED (lock 3).** Same target column, same labelled population, same emission meaning —
so the E8.0 board and the E7.5b betting prior stay comparable. Asserted per fold, not assumed.

🔁 **IF AN ARM SHIPS (lock 6).** A BATTER arm ⇒ re-run E7.5b's batter head-to-head gate
(`mle_prior.head_to_head`) before the served run_diff / pre-lineup rookie prior moves — re-emitting the
MLE does NOT auto-update it. A PITCHER arm ⇒ the pitcher head-to-head gate **does not exist yet** and
building it is in-scope for that ship, not a re-run.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.level_ladder import (  # noqa: E402
    ASC_LEVELS,
    REFERENCE_LEVEL,
    LadderSpec,
    apply_ladder,
    build_transitions,
    fit_ladder,
    ladder_coverage,
    transition_census,
)
from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    PLAUSIBLE_RANGE,
    ArchetypePriorRefProjector,
    PartialPoolProjector,
    build_target,
    emit_projections,
)
from betting_ml.scripts.milb_mle.park_context import ContextSpec, apply_context  # noqa: E402
from betting_ml.utils.design_block import (  # noqa: E402
    design_block_from_ladder_results,
    insert_design_block,
)
from betting_ml.scripts.milb_mle.h_harness import (  # noqa: E402
    FDR_ALPHA,
    MAX_PBO,
    MIN_DSR,
    MIN_FOLD_WIN_RATE,
    MIN_PCT_ROWS_MOVED,
    TIE_CONTENDER_SPREAD_PCT,
    Anchor,
    deflation_report,
    dsr_report,
    evaluate_anchors,
    low_tercile_read,
    null_analysis,
    numeric_gate,
    propensity_composition,
    stratified_lift,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (  # noqa: E402
    SIDES,
    SideConfig,
    _paired_p,
    _validate_emission,
    bh_fdr,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import propensity_for_fold  # noqa: E402
from betting_ml.scripts.milb_mle.survivorship import propensity_strata  # noqa: E402

log = logging.getLogger("e7_15.h1")

_KEYS = ["player_id", "level"]
_DEFAULT_OUT = (_PROJECT_ROOT
                / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

# ⭐ PINNED from the E7.12 slice-1 reports' "What was applied" tables — the configuration that is LIVE on
# the board today, per metric. This is the FOIL: the ladder's margin is measured against what actually
# ships, not against the pre-slice-1 E7.3 incumbent. Pinned as literals for the same reason slice 1 pins
# `E73_WINNER_PRIOR_SCALE`: rebuilding the reference by re-running the code under test is how a harness
# silently compares a change against itself.
SHIPPED_CONTEXT: dict[str, dict[str, ContextSpec]] = {
    # `ablation_results/e7_12_slice1_park_level_context.md` §5 (all four metrics ADDed)
    "batter": {
        "woba":   ContextSpec(level_env=True),
        "k_pct":  ContextSpec(park="exposure", level_env=True, reliability=0.5),
        "bb_pct": ContextSpec(park="exposure", level_env=True, reliability=2.0),
        "iso":    ContextSpec(park="exposure", level_env=True, reliability=2.0),
    },
    # `ablation_results/e7_12_slice1p_park_level_context_pitchers.md` §5 — only bb_pct and hr_rate ADDed;
    # k_pct / gb_pct / xwoba_against were DROPPED, so their shipped configuration IS the bare incumbent.
    "pitcher": {
        "k_pct":         ContextSpec(),
        "bb_pct":        ContextSpec(park="exposure", level_env=True, reliability=1.0,
                                     weight_col="mlb_pa"),
        "hr_rate":       ContextSpec(park="exposure", level_env=True, reliability=1.0,
                                     weight_col="mlb_pa"),
        "gb_pct":        ContextSpec(),
        "xwoba_against": ContextSpec(),
    },
}


# ══════════════════════════════════════════════════════════════════════════════════════
# The pre-registered arm set
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class H1Arm:
    label: str
    spec: LadderSpec
    kind: str          # foil | ladder | sensitivity | anchor
    note: str
    projector: str = "pool"     # pool | degenerate

    @property
    def selectable(self) -> bool:
        """Anchors are SCORED but never selected, and the foil is the DEFENDER rather than a candidate."""
        return self.kind in ("ladder", "sensitivity")


ARMS: tuple[H1Arm, ...] = (
    H1Arm("L0_foil", LadderSpec(mode="off"), "foil",
          "⭐ THE DIRECT-LEARNED FOIL — the shipped E7.12-slice-1 configuration with NO ladder"),
    H1Arm("L1_chain_ols", LadderSpec(mode="chain"), "ladder",
          "composed adjacent-rung OLS maps, unweighted (the matched pair for L2's weighting)"),
    H1Arm("L2_chain_paweighted", LadderSpec(mode="chain", weighted=True), "ladder",
          "the same chain with rung regressions weighted by the pair's harmonic-mean line length"),
    H1Arm("L3_direct_to_ref", LadderSpec(mode="direct", weighted=True), "ladder",
          "⭐ one-step (level → Triple-A) maps — avoids the chain's THREEFOLD attenuation compounding"),
    H1Arm("L4_ladder_delta", LadderSpec(mode="chain", as_extra=True), "ladder",
          "⭐ NESTS THE FOIL — the raw line is kept and the ladder DELTA enters as a fixed regressor, so "
          "a win is unambiguously 'the ladder adds information beyond the raw line'"),
    H1Arm("L1p_chain_purged", LadderSpec(mode="chain", calendar_purge=True), "sensitivity",
          "REGISTERED SENSITIVITY — L1 with every transition that had not FINISHED before the held-out "
          "cohort purged. Settles the calendar-leakage question by measurement instead of argument."),
    # ── anchors: these MUST hold ──
    H1Arm("A_ladder_identity", LadderSpec(mode="identity"), "anchor",
          "PLUMBING IDENTITY — rung maps forced to 0 + 1·x, so this must be a BYTE no-op vs L0. A gap "
          "here means the ladder code path itself perturbs the fit and every arm is confounded."),
    H1Arm("A_ladder_meanshift", LadderSpec(mode="meanshift"), "anchor",
          "⭐ MATCHED LEVEL-ONLY FOIL (NF-D15 g′) — per-rung ADDITIVE mean shift, slope pinned to 1. It "
          "keeps the level scale and strips every per-player content. If it ties the fitted ladder, the "
          "ladder's stated mechanism is refuted and what happened is level re-centring."),
    H1Arm("A_ladder_shuffled", LadderSpec(mode="shuffled"), "anchor",
          "LINK ANCHOR — rung maps fit with the DESTINATION rates permuted within rung. Both marginals "
          "survive; only the within-player pairing dies. Must LOSE."),
    H1Arm("A_degenerate_mean", LadderSpec(mode="off"), "anchor",
          "DEGENERATE CEILING (NF-D11/NF-D14) — predict the population mean of the target. A real "
          "candidate losing to this means the selection metric is inverted.", "degenerate"),
)

_BY_LABEL = {a.label: a for a in ARMS}


# ══════════════════════════════════════════════════════════════════════════════════════
# The run — one metric
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class H1Result:
    metric: str
    prior_scale: float
    shipped_spec: ContextSpec
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
    census: pd.DataFrame
    per_fold_transitions: pd.DataFrame
    coverage: dict
    deflation: dict
    dsr: dict
    anchors: dict
    stratified: pd.DataFrame            # all scored rows
    stratified_moved: pd.DataFrame      # ONLY rows the ladder can act on — what the H5 gate reads
    composition: pd.DataFrame           # what each tercile actually CONTAINS (level mix)
    verdict: str                    # ADD | DROP | BLOCKED
    winner: str
    reasons: list[str] = field(default_factory=list)
    oracle_floor_ok: bool = True


def _projector(arm: H1Arm, prior_scale: float, weight_col: str | None):
    """The learner for one arm. Held FIXED except for the two things an arm is allowed to change: which
    feature it reads (`extra_cols`) and, for the degenerate ceiling, that it reads none at all."""
    if arm.projector == "degenerate":
        return ArchetypePriorRefProjector()
    extra = ("ladder_delta",) if arm.spec.as_extra else ()
    return PartialPoolProjector(prior_scale=prior_scale, weight_col=weight_col, extra_cols=extra)


def run_h1(pairs: pd.DataFrame, context: pd.DataFrame | None, metric: str,
           side: SideConfig, arms: tuple[H1Arm, ...] = ARMS,
           *, propensity_cache: dict | None = None) -> H1Result:
    """Score every arm under the E7.3 fold structure — leave-one-MLB-debut-cohort-out, expanding window.

    ⚠️ **THE EVAL POPULATION IS IDENTICAL ACROSS ARMS AND THIS IS ASSERTED, NOT ASSUMED.** `has_target`
    reads `minor_pa` and the MLB label — never the rate's VALUE — so no ladder can change which rows are
    scored. If a future formulation ever could, the comparison would silently become "different players"
    rather than "different translation", which is the cheapest way an ablation lies.
    """
    shipped = SHIPPED_CONTEXT[side.player_type].get(metric, ContextSpec())
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)
    weight_col = shipped.weight_col

    # ── the substrate, assembled ONCE (the §0.5 cost-hygiene rule) ─────────────────────
    # ⭐ THE LADDER IS BUILT ON THE CONTEXT-ADJUSTED RATE, NOT THE RAW ONE. The pooled learner reads the
    # park/run-environment-adjusted line, so a rung map fitted on the RAW line would be translating a
    # different quantity than the one it is applied to — a mismatch that produces plausible numbers and
    # no error.
    adjusted = apply_context(pairs, context, shipped, metric, tuple(_KEYS))
    trans = build_transitions(adjusted, metric)
    census = transition_census(trans)
    if census.empty:
        log.warning("[%s] NO within-player transitions exist for this metric — the ladder is "
                    "structurally inert here, not null. (Expected for a metric whose minor feature is "
                    "the Triple-A-only Statcast summary.)", metric)

    base = build_target(adjusted, cfg)
    base_mask = base["has_target"].to_numpy(bool)
    labelled = base[base_mask]
    cohorts = sorted(int(y) for y in labelled["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"[{metric}] need ≥2 evaluable debut cohorts; got {fold_cohorts}")

    # ── coverage / composed maps, reported from a FULL-SUBSTRATE fit ──────────────────
    # Deliberately NOT the fold-0 fit: the per-fold maps differ (each excludes its own held-out players),
    # and reporting whichever one happened to be built first would make the published coefficients an
    # arbitrary fold's. This is the same fit `emit_with_ladder` would use, so the table a reader sees is
    # the table that would ship. The per-fold variation is reported separately as `per_fold_transitions`.
    coverage: dict[str, dict] = {}
    for arm in arms:
        f0 = fit_ladder(trans, arm.spec, metric)
        coverage[arm.label] = ladder_coverage(apply_ladder(adjusted, f0, metric), metric, f0)

    labels = [a.label for a in arms]
    mae = pd.DataFrame(index=fold_cohorts, columns=labels, dtype=float)
    err_rows: list[pd.DataFrame] = []
    rung_rows: list[dict] = []
    notes: list[str] = []
    propensity_cache = propensity_cache if propensity_cache is not None else {}

    for year in fold_cohorts:
        test_players = frozenset(
            labelled.loc[labelled["debut_cohort"] == year, "player_id"].astype(str).unique())
        # per-fold promotion propensity (E7.12 slice 2's hazard, fit on seasons strictly before the
        # held-out cohort so the strata cannot be a function of the test fold's own promotions)
        strat = propensity_cache.get(year)
        if strat is None:
            try:
                pf = propensity_for_fold(pairs, year)
                strat = pf.propensity[_KEYS].assign(
                    stratum=propensity_strata(pf.propensity["propensity"]))
            except Exception as e:  # noqa: BLE001 — a thin early fold must not kill the sweep
                notes.append(f"fold {year} propensity: {type(e).__name__}: {e}")
                strat = pd.DataFrame(columns=_KEYS + ["stratum"])
            propensity_cache[year] = strat

        for arm in arms:
            fit = fit_ladder(trans, arm.spec, metric,
                             exclude_players=test_players,
                             cutoff_season=year if arm.spec.calendar_purge else None)
            rung_rows.append({"fold": year, "arm": arm.label,
                              "n_transitions_used": fit.n_transitions_used,
                              "n_identity_fallbacks": len(fit.fallbacks),
                              **{f"b_{lv}": fit.composed.get(lv, (0.0, 1.0, ""))[1]
                                 for lv in ASC_LEVELS if lv != REFERENCE_LEVEL}})
            lad = apply_ladder(adjusted, fit, metric)
            frame = build_target(lad, cfg)
            if not np.array_equal(frame["has_target"].to_numpy(bool), base_mask):
                raise AssertionError(
                    f"[{metric}/{arm.label}] the ladder changed the LABELLED POPULATION — arms would be "
                    f"scored on different players, which is not an ablation.")

            f = frame[frame["has_target"]]
            train, test = f[f["debut_cohort"] < year], f[f["debut_cohort"] == year]
            if train.empty or test.empty:
                continue
            try:
                mdl = _projector(arm, scale, weight_col).fit(train)
                yhat, _ = mdl.predict(test)
                err = np.abs(test["target"].to_numpy(float) - yhat)
                mae.loc[year, arm.label] = float(np.mean(err))
                err_rows.append(pd.DataFrame({
                    "fold": year, "arm": arm.label,
                    "player_id": test["player_id"].to_numpy(),
                    "level": test["level"].to_numpy(), "abs_err": err,
                    # can this arm act on this row at all? A reference-level row has a delta of
                    # identically 0, so it contributes exactly zero lift by construction — see
                    # `stratified_lift(moved_only=)` for why averaging over those is a dilution.
                    "moved": (pd.to_numeric(test.get("ladder_delta"), errors="coerce")
                              .fillna(0.0).abs() > 1e-12).to_numpy()}))
            except Exception as e:  # noqa: BLE001 — a degenerate fold must not kill the sweep
                notes.append(f"fold {year} arm {arm.label}: {type(e).__name__}: {e}")

    per_fold_transitions = pd.DataFrame(rung_rows)
    rows_df = pd.concat(err_rows, ignore_index=True) if err_rows else pd.DataFrame()
    strata = [s.assign(fold=y) for y, s in propensity_cache.items() if not s.empty]
    if not rows_df.empty and strata:
        strat_all = pd.concat(strata, ignore_index=True)
        rows_df["player_id"] = rows_df["player_id"].astype(str)
        strat_all["player_id"] = strat_all["player_id"].astype(str)
        rows_df = rows_df.merge(strat_all, on=["fold"] + _KEYS, how="left")

    # ── leaderboard ───────────────────────────────────────────────────────────────────
    foil = mae["L0_foil"]
    rows = []
    for arm in arms:
        col = mae[arm.label]
        d = (foil - col).to_numpy(float)
        d_fin = d[np.isfinite(d)]
        cov = coverage.get(arm.label, {})
        rows.append({
            "arm": arm.label, "kind": arm.kind, "selectable": arm.selectable,
            "active": (arm.label == "L0_foil"
                       or float(cov.get("pct_rows_moved") or 0.0) > MIN_PCT_ROWS_MOVED
                       or arm.projector == "degenerate"),
            "oos_mae": float(col.mean(skipna=True)),
            "mae_lift_vs_foil": float(np.mean(d_fin)) if len(d_fin) else np.nan,
            "pct_lift_vs_foil": (100.0 * float(np.mean(d_fin)) / float(foil.mean(skipna=True))
                                 if len(d_fin) and foil.mean(skipna=True) else np.nan),
            "fold_win_rate": float(np.mean(d_fin > 0)) if len(d_fin) else np.nan,
            "p_one_sided": _paired_p(d),
            "pct_rows_moved": cov.get("pct_rows_moved"),
            "mean_abs_delta_feat": cov.get("mean_abs_delta"),
            "note": arm.note,
        })
    leaderboard = pd.DataFrame(rows).sort_values("oos_mae").reset_index(drop=True)

    eligible = [a.label for a in arms if a.selectable or a.label == "L0_foil"]
    defl = deflation_report(mae, eligible)
    defl["whole_field"] = deflation_report(mae)
    dsr = dsr_report(mae, eligible)

    oracle_ok = bool(np.nanmin(leaderboard["oos_mae"].to_numpy(float)) >= -1e-9)
    anchors, stratified, stratified_moved, verdict, winner, reasons = _judge(
        metric, side, mae, leaderboard, rows_df, defl, dsr, oracle_ok, notes, coverage)

    return H1Result(
        metric=metric, prior_scale=scale, shipped_spec=shipped, leaderboard=leaderboard,
        mae_by_fold=mae, fold_cohorts=fold_cohorts, census=census,
        per_fold_transitions=per_fold_transitions, coverage=coverage, deflation=defl, dsr=dsr,
        anchors=anchors, stratified=stratified, stratified_moved=stratified_moved,
        composition=propensity_composition(rows_df), verdict=verdict, winner=winner, reasons=reasons,
        oracle_floor_ok=oracle_ok)


# ⭐ H1's anchors, DECLARED. The numeric gate, the deflation reading and the tercile machinery are
# shared with every other E7.15 slice (`h_harness`); the anchors are not, because each hypothesis has
# its own way of being wrong. Declaring them as records is what stops a later slice from silently
# shipping with fewer anchors than this one.
H1_ANCHORS: tuple[Anchor, ...] = (
    Anchor("A_ladder_identity", "noop",
           "rung maps forced to 0 + 1·x",
           "The ladder CODE PATH perturbs the fit on its own, so every arm's margin is confounded with "
           "plumbing rather than with the ladder."),
    Anchor("A_degenerate_mean", "block",
           "the DEGENERATE CEILING — predict the population mean",
           "A metric a 'predict nothing' arm wins cannot select a projection (NF-D11); the selection "
           "metric is inverted for this cohort.",
           must_move=False),   # a degenerate PROJECTOR transforms no feature — legitimately moves 0%
    Anchor("A_ladder_meanshift", "refute",
           "the MATCHED LEVEL-ONLY foil — per-rung additive mean shift, slope pinned to 1",
           "Whatever helps here is a per-LEVEL re-centring, which the E7.3 level intercepts already "
           "own — not the per-player 'how his line changed as he climbed' content H1 claims "
           "(NF-D15 g′)."),
    Anchor("A_ladder_shuffled", "refute",
           "the LINK anchor — destination rates permuted within rung, both marginals intact",
           "The within-player pairing is not what is doing the work."),
)


def _judge(metric: str, side: SideConfig, mae: pd.DataFrame, leaderboard: pd.DataFrame,
           rows_df: pd.DataFrame, defl: dict, dsr: dict, oracle_ok: bool,
           notes: list[str],
           coverage: dict | None = None
           ) -> tuple[dict, pd.DataFrame, pd.DataFrame, str, str, list[str]]:
    """Anchors → disqualification → verdict. Pre-registered; nothing here is decided after the fact."""
    reasons: list[str] = list(notes)

    def m_of(lbl: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == lbl, "oos_mae"]
        return float(r.iloc[0]) if len(r) else float("nan")

    # the best ACTIVE, SELECTABLE ladder arm — the thing the anchors are asked about
    sel = leaderboard[leaderboard["selectable"] & leaderboard["active"]]
    best = str(sel.iloc[0]["arm"]) if not sel.empty else "L0_foil"

    anchors, anchor_verdict, anchor_reason = evaluate_anchors(
        mae, H1_ANCHORS, best, "L0_foil", coverage=coverage)
    anchors["oracle_floor_ok"] = oracle_ok
    anchors["best_ladder"] = best
    anchors["best_ladder_mae"], anchors["foil_mae"] = m_of(best), m_of("L0_foil")

    # Two readings, and the GATE uses the MOVED-ONLY one — see `h_harness.stratified_lift`.
    stratified = stratified_lift(rows_df)
    stratified_moved = stratified_lift(rows_df, moved_only=True)
    low, low_all = low_tercile_read(stratified, stratified_moved, best)
    anchors["low_propensity_tercile_lift_pct"] = low
    anchors["low_propensity_tercile_lift_pct_all_rows"] = low_all

    winner = "L0_foil"
    # ── metric-wide BLOCKS ────────────────────────────────────────────────────────────
    if not oracle_ok:
        reasons.append("⛔ ORACLE-FLOOR VIOLATION — a candidate scored MAE < 0; the metric is inverted.")
        return anchors, stratified, stratified_moved, "BLOCKED", winner, reasons
    if anchor_verdict:
        reasons.append(anchor_reason)
        return anchors, stratified, stratified_moved, anchor_verdict, winner, reasons

    # ── the gate ──────────────────────────────────────────────────────────────────────
    inactive = leaderboard[leaderboard["selectable"] & ~leaderboard["active"]]["arm"].tolist()
    if inactive:
        reasons.append(
            f"ℹ️ INACTIVE arms (the ladder moved <{MIN_PCT_ROWS_MOVED}% of rows, so they are the foil in "
            f"disguise and cannot be selected): {', '.join(inactive)}. For a metric whose minor feature "
            f"exists only at Triple-A this is STRUCTURAL — a mechanism that cannot act is a finding, not "
            f"an omission (NF1.9).")
    if sel.empty:
        reasons.append("🟡 no ELIGIBLE arm remains — every ladder arm is inactive. The shipped slice-1 "
                       "configuration stands for this metric.")
        return anchors, stratified, stratified_moved, "DROP", winner, reasons

    cand = sel.iloc[0]
    passed, reason = numeric_gate(cand, m_of("L0_foil"), defl, dsr, "within-player level ladder")
    reasons.append(reason)
    if not passed:
        return anchors, stratified, stratified_moved, "DROP", winner, reasons

    verdict, winner = "ADD", str(cand["arm"])

    # ── H5: the board serves the LOW-propensity population ────────────────────────────
    if metric in side.board_metrics and np.isfinite(low) and low < 0:
        verdict, winner = "DROP", "L0_foil"
        reasons.append(
            f"⛔ LOW-TERCILE DOWNGRADE — `{cand['arm']}` improves the OVERALL held-out MAE but is "
            f"{low:+.3f}% in the LOWEST promotion-propensity tercile, the closest observable proxy we "
            f"have for the un-promoted prospects the E8.0 board serves. A board metric that helps the "
            f"players we do NOT serve is not a board improvement (H5). Reported, not shipped.")
    elif np.isfinite(low):
        scope = ("board metric" if metric in side.board_metrics else
                 "cosmetic metric — NOT on the E8.0 board, so a move here cannot change a draft ranking")
        reasons.append(f"ℹ️ low-propensity-tercile lift {low:+.3f}% ({scope}).")
    return anchors, stratified, stratified_moved, verdict, winner, reasons



# ══════════════════════════════════════════════════════════════════════════════════════
# Reading a null honestly (NF-D15 g″) — computed, not asserted
# ══════════════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════════════
# Emission under a winning arm
# ══════════════════════════════════════════════════════════════════════════════════════


def emit_with_ladder(pairs: pd.DataFrame, context: pd.DataFrame | None, shipped: ContextSpec,
                     ladder: LadderSpec, metric: str, prior_scale: float,
                     side: SideConfig) -> pd.DataFrame:
    """Re-emit the per-(player, level) MLB-equivalent line under a winning ladder arm.

    Reuses `emit_projections` verbatim — the leakage-safe expanding-window refit, the seed-cohort
    exclusion and the plausibility clip stay E7.3's. Only the input feature changes.

    ⚠️ **STATED LIMITATION.** The EMISSION ladder is fitted over the whole transition substrate (slice 1's
    posture for a MiLB-only transform), whereas the EVALUATION ladder excluded each held-out player.
    A player therefore contributes ≲1/2000 of his own rung map at emission time. The evaluation is the
    conservative one, so the reported margin is not inflated by this; the emitted number is very slightly
    more in-sample than the number that was gated.
    """
    adj = apply_context(pairs, context, shipped, metric, tuple(_KEYS))
    if not ladder.is_noop:
        fit = fit_ladder(build_transitions(adj, metric), ladder, metric)
        adj = apply_ladder(adj, fit, metric)
    cfg = side.mle_config(metric)
    extra = ("ladder_delta",) if ladder.as_extra else ()
    proj = emit_projections(
        adj,
        lambda: PartialPoolProjector(prior_scale=prior_scale, weight_col=shipped.weight_col,
                                     extra_cols=extra),
        cfg)
    if not proj.empty:
        proj["ladder_spec"] = ladder.label
        proj["context_spec"] = shipped.label
        proj["model_version"] = side.model_version.replace("_parkctx", "_ladder")
    return proj


def build_applied_projections(pairs: pd.DataFrame, context: pd.DataFrame | None,
                              results: dict[str, H1Result], applied: dict[str, dict],
                              side: SideConfig) -> tuple[pd.DataFrame | None, bool]:
    """Assemble the re-emitted wide projections — **EVERY metric, always** (slice 1's footgun, carried).

    The E8.0 board reads all of a side's board metrics from ONE wide table, so a partial re-emission that
    overwrote it would silently delete the columns it did not write and every prospect's composite would
    quietly renormalise onto whatever survived. A DROP metric is therefore re-emitted under its SHIPPED
    slice-1 configuration with NO ladder — byte-exact today's board — rather than omitted.
    """
    wide: pd.DataFrame | None = None
    changed = False
    for m, r in results.items():
        add = r.verdict == "ADD"
        ladder = _BY_LABEL[r.winner].spec if add else LadderSpec(mode="off")
        if add:
            changed = True
        else:
            log.info("[%s] verdict=%s — re-emitting the SHIPPED configuration so the wide table stays a "
                     "complete drop-in replacement", m, r.verdict)
        proj = emit_with_ladder(pairs, context, r.shipped_spec, ladder, m, r.prior_scale, side)
        checks = _validate_emission(proj, m)
        if add:
            applied[m] = {"arm": r.winner, "ladder_spec": ladder.label,
                          "context_spec": r.shipped_spec.label,
                          "n_rows": int(len(proj)), "gates": "; ".join(checks)}
        proj = proj.rename(columns={"ladder_spec": f"{m}_ladder_spec",
                                    "context_spec": f"{m}_context_spec"})
        base = _KEYS + ["player_name", "league", "debut_cohort", "is_prospect", "age", "minor_pa",
                        "n_prior_cohorts"]
        per_metric = [f"minor_{m}", f"mlb_{m}", f"mle_{m}", f"mle_{m}_sd",
                      f"{m}_context_spec", f"{m}_ladder_spec"]
        if wide is None:
            wide = proj[[c for c in base + per_metric if c in proj.columns]].copy()
        else:
            wide = wide.merge(proj[_KEYS + [c for c in per_metric if c in proj.columns]],
                              on=_KEYS, how="outer")
    if wide is None:
        return None, False
    wide = wide.copy()
    wide["sport"], wide["player_type"] = "mlb", side.player_type
    wide["model_version"] = (side.model_version.replace("_parkctx", "_ladder") if changed
                             else side.model_version)
    for m in results:
        assert f"mle_{m}" in wide.columns, f"the re-emission dropped mle_{m} — not a drop-in replacement"
    return wide, changed


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def write_report(results: dict[str, H1Result], fdr: dict, applied: dict, path: Path,
                 side: SideConfig, nulls: dict | None = None) -> None:
    def md(df: pd.DataFrame) -> str:
        return df.to_markdown(index=False) if not df.empty else "_(empty)_"

    L: list[str] = []
    A = L.append
    A(f"# E7.15 H1 — the within-player level-translation ladder ({side.player_type} side)\n")
    A(f"_generated {datetime.now(timezone.utc).isoformat()} · "
      f"foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_\n")
    A("> ⚠️ **A projection, not an edge claim.** H1 asks one question: does learning the LEVEL part of "
      "the MiLB→MLB translation from within-player minor→minor transitions — a substrate with no MLB "
      "label, no promotion selection, and 4–7× the rows of the labelled per-level cohort — translate "
      "better than learning it from graduates alone? An arm that does not clear its deflated gate is "
      "**DROPPED, not shipped**.\n")

    A("## 0. Pre-registration (written before the run)\n")
    A("- **Foil.** Every arm is measured against `L0_foil` = the configuration LIVE on the board today "
      "(the shipped slice-1 `ContextSpec` per metric), with the learner and its `weight_col` held FIXED. "
      "The only thing that varies is the feature (E7.9: 54–77% of a bake-off margin can be the learner "
      "swap).\n")
    A("- **Four ladder formulations**, not one: `L1_chain_ols`, `L2_chain_paweighted` (L1's matched pair "
      "for the weighting), `L3_direct_to_ref` (one-step maps, which avoid the chain's threefold "
      "attenuation compounding), `L4_ladder_delta` (NESTS the foil at coefficient 0). Plus "
      "`L1p_chain_purged` as a registered calendar-leakage sensitivity. A single architecture missing "
      "its gate is not a trustworthy null; the whole set missing it is.\n")
    A("- **Anchors.** `A_ladder_identity` must be a BYTE no-op; `A_ladder_meanshift` (the matched "
      "level-only foil) and `A_ladder_shuffled` (the within-player link destroyed) must LOSE; "
      "`A_degenerate_mean` must LOSE. A MISSING anchor BLOCKS — it is not a pass.\n")
    A(f"- **Gate for an ADD** (all must hold): strict OOS MAE improvement over the foil in "
      f"≥{MIN_FOLD_WIN_RATE:.0%} of held-out debut cohorts; the ladder MOVED >{MIN_PCT_ROWS_MOVED}% of "
      f"rows; every anchor holds; PBO(eligible) < {MAX_PBO}; DSR(eligible) ≥ {MIN_DSR}; Benjamini-"
      f"Hochberg over the metric family at α={FDR_ALPHA}; and — for a board metric — a non-negative "
      f"lift in the LOWEST promotion-propensity tercile.\n")
    A("- **Estimand preserved.** Same target, same labelled population, same emitted meaning, so the "
      "E8.0 board and the E7.5b betting prior stay comparable. Asserted per fold.\n")

    A("## 1. ⭐ The transition census — REPORTED BEFORE ANY SCORE\n")
    A("The n-multiplication is H1's entire premise, so the counts come first. `pct_never_mlb` is the "
      "share of transitions whose source player NEVER reached MLB — the population a graduates-only fit "
      "structurally cannot see, and the population the draft board is served on.\n")
    for m, r in results.items():
        A(f"\n**{m}**\n")
        A(md(r.census))
        A(f"\n_evaluable debut cohorts: {r.fold_cohorts}; labelled rows scored per fold are E7.3's._\n")
        if not r.per_fold_transitions.empty:
            pf = (r.per_fold_transitions[r.per_fold_transitions["arm"] == "L1p_chain_purged"]
                  [["fold", "n_transitions_used", "n_identity_fallbacks"]])
            if not pf.empty:
                A("\nCalendar-PURGED transitions available per fold (the sensitivity arm's cost — the "
                  "substrate starts in 2015, so the early folds see almost nothing):\n")
                A(md(pf))

    A("\n## 2. Verdict by metric\n")
    rows = []
    for m, r in results.items():
        lb = r.leaderboard
        cand = lb[lb["selectable"] & lb["active"]]
        best = cand.iloc[0] if not cand.empty else None
        d_el = (r.dsr or {}).get("eligible") or {}
        rows.append({
            "metric": m, "verdict": r.verdict, "winner": r.winner,
            "best_arm": None if best is None else best["arm"],
            "pct_lift_vs_foil": None if best is None else round(float(best["pct_lift_vs_foil"]), 3),
            "fold_win_rate": None if best is None else best["fold_win_rate"],
            "p_one_sided": None if best is None else best["p_one_sided"],
            "BH-FDR": fdr.get(m),
            "PBO(eligible)": r.deflation.get("pbo"),
            "DSR(eligible)": d_el.get("dsr"),
            "low_tercile_lift_%": r.anchors.get("low_propensity_tercile_lift_pct"),
        })
    A(md(pd.DataFrame(rows)))
    A("\n`PBO(eligible)` and `DSR(eligible)` are computed over the ELIGIBLE arms — the search the "
      "selection actually ran — not over every arm scored; the whole-field figures are in the JSON. A "
      "field that CONTAINS its own anchors has a huge dispersion, and a deflation statistic computed "
      "over it measures the anchors (NF-D14). The eligible-set figure is the one pre-registered to bind.\n")

    for m, r in results.items():
        A(f"\n## 3.{m} — the arm set (`partial_pool@{r.prior_scale:g}`"
          f"{', weights=' + r.shipped_spec.weight_col if r.shipped_spec.weight_col else ''}, "
          f"context `{r.shipped_spec.label}`, learner held fixed)\n")
        cols = ["arm", "kind", "active", "oos_mae", "pct_lift_vs_foil", "fold_win_rate",
                "p_one_sided", "pct_rows_moved", "mean_abs_delta_feat"]
        A(md(r.leaderboard[cols].round(6)))
        A("\n**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and "
          "direct arms — the compounding-attenuation hazard is visible here as a much smaller composed "
          "`b` for the chain than for the one-step direct fit:\n")
        comp = []
        for lbl in ("L1_chain_ols", "L2_chain_paweighted", "L3_direct_to_ref", "A_ladder_meanshift"):
            c = (r.coverage.get(lbl) or {}).get("composed") or {}
            for lv, v in c.items():
                comp.append({"arm": lbl, "level": lv, "a": v["a"], "b": v["b"],
                             "source": v["source"]})
        A(md(pd.DataFrame(comp)))
        A("\n**Anchors**\n")
        A(f"- identity byte no-op: `{r.anchors.get('identity_is_a_noop')}` "
          f"(max |Δ| = {r.anchors.get('identity_max_abs_gap')})")
        for k in ("meanshift_vs_best_ladder", "shuffled_vs_best_ladder", "degenerate_vs_best_ladder"):
            a = r.anchors.get(k) or {}
            A(f"- `{k}`: challenger wins {a.get('challenger_fold_wins')}/{a.get('n_folds')} folds, "
              f"p={a.get('p_challenger_better')}, violated={a.get('violated')}")
        if not r.composition.empty:
            A("\n**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the "
              "tercile lifts. E7.12 slice 2 introduced these terciles as \"the observable proxy for the "
              "un-promoted prospects we serve\" and H5 inherited that reading; on the labelled cohort it "
              "runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows "
              "and POOREST in Single-A rows — it selects late-arriving graduates, not low-level "
              "prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is "
              "identically 0 and it cannot be moved at all:\n")
            A(md(r.composition))
        for label, frame, why in (
            ("rows the ladder CAN move (⭐ what the H5 gate reads)", r.stratified_moved,
             "a reference-level row contributes exactly zero lift by construction, so including it "
             "averages the mechanism over rows it structurally cannot touch"),
            ("ALL scored rows", r.stratified,
             "published beside the gated view, because changing which population a gate reads without "
             "showing both is how a gate quietly starts measuring something else")):
            if frame.empty:
                continue
            A(f"\n**Per promotion-propensity tercile — {label}** (stratum 0 = LOWEST propensity; "
              f"{why}):\n")
            piv = (frame.pivot(index="arm", columns="stratum", values="pct_lift_vs_foil")
                   .round(3).reset_index())
            piv.columns = ["arm"] + [f"tercile_{c}_lift_%" for c in piv.columns[1:]]
            A(md(piv))
        A("\n**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' "
          "(NF1.8), so all four numbers:\n")
        d = r.deflation
        A(f"- PBO(eligible) `{d.get('pbo')}` · Bailey OS degradation `{d.get('os_gap_pct')}%` "
          f"(p90 `{d.get('os_gap_p90_pct')}%`) · contender spread `{d.get('contender_spread_pct')}%` · "
          f"whole-field spread `{d.get('full_spread_pct')}%`")
        if d.get("flips"):
            A("\nFlip distribution (which arm wins the in-sample halves):\n")
            A(md(pd.DataFrame(d["flips"])))
        A("\n**Reading**\n")
        for reason in r.reasons:
            A(f"- {reason}")

    if nulls:
        A("\n## 3b. ⭐ Reading the null honestly — is it the data, or is it my gate?\n")
        A(f"**Does the null rest on the gate choice?** Re-deciding the entire run with the deflation "
          f"gates REMOVED — no PBO ceiling, no DSR floor — leaves survivors: "
          f"**{nulls['survivors_with_PBO_and_DSR_gates_REMOVED'] or 'NONE'}**. "
          f"⇒ {nulls['binding_constraint']} (family of {nulls['family_size']}; the strictest "
          f"Benjamini-Hochberg rung is p ≤ {nulls['strictest_bh_cutoff']}).\n")
        A("**The margin in the unit that GROWS.** Folds here ARE seasons — one held-out MLB debut "
          "cohort each — so an underpowered effect converts to a calendar re-test date, and a best arm "
          "that does not beat the foil ON AVERAGE is a genuine absence that no sample size rescues. The "
          "two are different kinds of null and are not recorded as the same thing (NF-D15 g″):\n")
        A(md(pd.DataFrame(nulls["per_metric"])))

    A("\n## 4. What was applied\n")
    if applied:
        A(md(pd.DataFrame([{"metric": k, **v} for k, v in applied.items()])))
    else:
        A("_Nothing. No metric cleared its deflated gate, so the shipped E7.12-slice-1 emission stands "
          "verbatim. A null add is DROPPED, never shipped — that is the correct outcome for a null "
          "bake-off, not a failure._\n")

    A("\n## 5. Limitations\n")
    A("- **The chain composes attenuation.** Each rung regression is attenuated by measurement error in "
      "its source rate; composing three attenuates three times, so a Single-A line is shrunk harder by "
      "the chain than a single-step fit would shrink it. `L3_direct_to_ref` exists precisely to bound "
      "that, and the composed-`b` table above is the measurement.\n")
    A("- **The final rung still carries survivorship.** H1 confines the promotion-selection problem "
      "(E7.12 slice 2) to AAA→MLB — it does not remove it. Every number here remains conditional on the "
      "graduated population, and the per-tercile table is the honest read of who benefits.\n")
    A("- **A level stint is aggregated, not seasonal.** The pairs grain is (player, level), so a "
      "transition is 'his whole High-A line → his whole Double-A line'. A player who yo-yos is one "
      "temporally-ordered pair, not several; that is a real coarseness of the substrate.\n")
    A("- **The emission ladder is fitted over the whole substrate** while the evaluation ladder excluded "
      "each held-out player. The gate is therefore the conservative number.\n")
    A("- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.\n")
    db = design_block_from_ladder_results(
        results, fold_rule="leave-one-MLB-debut-cohort-out (n_cohorts)")
    path.write_text(insert_design_block("\n".join(L) + "\n", db))
    log.info("wrote %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="E7.15 H1 — the within-player level-translation ladder bake-off")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter")
    p.add_argument("--pairs", default=None)
    p.add_argument("--context", default=None)
    p.add_argument("--metrics", nargs="+", default=None)
    p.add_argument("--arms", nargs="+", default=None,
                   help="restrict to these arm labels (a cheap smoke); L0_foil is always included")
    p.add_argument("--transitions-only", action="store_true",
                   help="print the per-rung transition census and EXIT (readiness lock 2 — seconds, "
                        "no scoring)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--apply", action="store_true",
                   help="re-emit the projections under each metric's winning arm (ADD metrics only; a "
                        "DROP is re-emitted byte-exact under its shipped slice-1 configuration)")
    p.add_argument("--s3", action="store_true", help="with --apply, also land them in the lakehouse")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[args.player_type]
    e73_out = (_REPORT_DIR / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts"))
    pairs_path = Path(args.pairs) if args.pairs else e73_out / side.pairs_name
    ctx_default = (_REPORT_DIR / "e7_12_artifacts"
                   / f"mle_park_context{side.reduced.artifact_suffix}.parquet")
    context_path = Path(args.context) if args.context else ctx_default
    metrics = args.metrics if args.metrics else list(side.metrics)

    if not pairs_path.exists():
        p.error(f"pairs parquet not found at {pairs_path} — run the {side.player_type} "
                f"build_graduated_pairs first")
    pairs = pd.read_parquet(pairs_path)
    if not context_path.exists():
        p.error(f"park context not found at {context_path} — run build_park_context.py "
                f"--player-type {side.player_type} first. Without it the FOIL is not the shipped "
                f"configuration, and the ladder would be measured against the wrong baseline.")
    context = pd.read_parquet(context_path)
    log.info("loaded %d pairs rows + %d park-context rows (%s)",
             len(pairs), len(context), side.player_type)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.transitions_only:
        frames = []
        for m in metrics:
            shipped = SHIPPED_CONTEXT[side.player_type].get(m, ContextSpec())
            adj = apply_context(pairs, context, shipped, m, tuple(_KEYS))
            c = transition_census(build_transitions(adj, m)).assign(metric=m)
            frames.append(c)
            print(f"\n=== {side.player_type} / {m} (context `{shipped.label}`) ===")
            print(c.to_string(index=False) if not c.empty
                  else "  NO within-player transitions — the ladder is structurally inert for this "
                       "metric (its minor feature exists only at Triple-A).")
        dest = out_dir / f"e7_15_h1_transition_census{side.reduced.artifact_suffix}.csv"
        pd.concat(frames, ignore_index=True).to_csv(dest, index=False)
        log.info("wrote %s", dest)
        return 0

    arms = ARMS if not args.arms else tuple(_BY_LABEL[a] for a in args.arms)
    if "L0_foil" not in {a.label for a in arms}:
        arms = (_BY_LABEL["L0_foil"],) + arms

    results: dict[str, H1Result] = {}
    cache: dict = {}
    for metric in metrics:
        log.info("=== E7.15 H1 [%s]: %s (the multi-minute part) ===", side.player_type, metric)
        results[metric] = run_h1(pairs, context, metric, side, arms, propensity_cache=cache)
        r = results[metric]
        log.info("[%s] verdict=%s winner=%s", metric, r.verdict, r.winner)
        for reason in r.reasons:
            log.info("[%s] %s", metric, reason)

    pvals = {}
    for m, r in results.items():
        lb = r.leaderboard
        cand = lb[lb["selectable"] & lb["active"]]
        pvals[m] = (float(cand.iloc[0]["p_one_sided"])
                    if not cand.empty and pd.notna(cand.iloc[0]["p_one_sided"]) else None)
    fdr = bh_fdr(pvals, alpha=FDR_ALPHA)

    # BH-FDR IS A GATE, NOT A FOOTNOTE (the slice-1 defect, not repeated here).
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict, r.winner = "DROP", "L0_foil"
            r.reasons.append(
                f"⛔ FDR-DOWNGRADED — the winner cleared the per-metric bar (p={pvals.get(m)}) but does "
                f"NOT survive Benjamini-Hochberg over the {len(pvals)}-metric family at α={FDR_ALPHA}. "
                f"DROPPED — the shipped configuration is re-emitted byte-exact for this metric.")
            log.warning("[%s] FDR-DOWNGRADED to DROP", m)

    nulls = null_analysis(results, pvals)
    log.info("NULL ANALYSIS — %s", nulls["binding_constraint"])

    applied: dict[str, dict] = {}
    if args.apply:
        wide, changed = build_applied_projections(pairs, context, results, applied, side)
        if wide is None:
            log.info("--apply requested but nothing was emitted — check the metric list.")
        elif not changed:
            log.info("--apply requested but NO metric cleared its gate. NOTHING is written: the shipped "
                     "E7.12-slice-1 emission stands verbatim. That is the correct outcome for a null "
                     "bake-off, not a failure.")
        else:
            dest = out_dir / f"mle_projections{side.reduced.artifact_suffix}_ladder.parquet"
            wide.to_parquet(dest, index=False)
            log.info("wrote %s (%d rows, %d metric(s) adjusted)", dest, len(wide), len(applied))
            if args.s3:
                from deltalake import write_deltalake

                from scripts.utils.delta_lake import storage_options
                write_deltalake(side.s3_dest, wide, mode="overwrite", schema_mode="overwrite",
                                storage_options=storage_options())
                log.info("landed the ladder projections at %s", side.s3_dest)
            log.warning(
                "⚠️ A SHIPPED %s ARM DOES NOT MOVE THE SERVED BETTING PRIOR ON ITS OWN. %s",
                side.player_type,
                ("Re-run E7.5b's batter head-to-head gate (`mle_prior.head_to_head`) before the served "
                 "run_diff / pre-lineup rookie prior changes." if side.player_type == "batter" else
                 "The PITCHER head-to-head gate DOES NOT EXIST — building it is in scope for this ship, "
                 "and the pitcher recalibration must not be re-run ungated until it does."))

    suffix = side.reduced.artifact_suffix
    (out_dir / f"e7_15_h1{suffix}_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_type": side.player_type,
        "foil": "the SHIPPED E7.12-slice-1 configuration per metric (learner + weight_col held fixed)",
        "shipped_context": {m: SHIPPED_CONTEXT[side.player_type].get(m, ContextSpec()).label
                            for m in metrics},
        "prior_scales": {m: r.prior_scale for m, r in results.items()},
        "bh_fdr_alpha": FDR_ALPHA, "bh_fdr": fdr,
        "null_analysis": nulls,
        "per_metric": {m: {
            "verdict": r.verdict, "winner": r.winner,
            "census": r.census.to_dict(orient="records"),
            "leaderboard": r.leaderboard.to_dict(orient="records"),
            "mae_by_fold": r.mae_by_fold.to_dict(),
            "coverage": r.coverage, "deflation": r.deflation, "dsr": r.dsr,
            "anchors": r.anchors,
            "stratified": r.stratified.to_dict(orient="records"),
            "stratified_moved_rows_only": r.stratified_moved.to_dict(orient="records"),
            "propensity_tercile_composition": r.composition.to_dict(orient="records"),
            "per_fold_transitions": r.per_fold_transitions.to_dict(orient="records"),
            "reasons": r.reasons,
        } for m, r in results.items()},
        "applied": applied,
    }, indent=2, default=float))

    if not args.no_report:
        name = f"e7_15_h1_level_ladder{suffix}.md"
        write_report(results, fdr, applied, _REPORT_DIR / name, side, nulls)

    verdicts = {m: r.verdict for m, r in results.items()}
    log.info("E7.15 H1 VERDICTS (%s): %s", side.player_type, verdicts)
    if any(v == "BLOCKED" for v in verdicts.values()):
        log.warning("at least one metric is BLOCKED by an anchor — read the report before shipping "
                    "anything from this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
