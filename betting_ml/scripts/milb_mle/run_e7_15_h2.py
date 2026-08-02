"""run_e7_15_h2.py — MLB Edge-E7.15 H2: the §0.5 bake-off for the OPPONENT / competition-quality
adjustment.

⚠️ **OPERATOR-RUN (>2 min).** ~7 arms × the side's metrics × leave-one-debut-cohort-out folds. The
CONTEXT BUILD (`build_opponent_context.py`) is the expensive part at ~3¼ min per side and must run first.

    uv run python -m betting_ml.scripts.milb_mle.build_opponent_context --season-floor 2015
    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h2

WHAT IT DECIDES — and why the MEASUREMENT outranks the bake-off here
--------------------------------------------------------------------
`build_park_context.py` asserts, in the docstring of a SHIPPED feature, that the park factor's residual
is "the park (plus the opponent mix, **which averages out** over a 3-season window)". Nobody ever tested
it. H2 measures the player-level version of that claim — does the competition a prospect actually faced
vary enough to bias his translation? — and only then asks whether correcting for it helps.

⭐ **THE MEASUREMENT IS THE DELIVERABLE AND IT IS WORTH HAVING EITHER WAY.** If the within-league opponent
factor has no reliable spread, the assumption is confirmed and this entire family of "adjust for who he
faced" ideas is closed for a principled reason rather than a leaderboard miss. If it does, a shipped
feature rests on a false premise regardless of what any bake-off says.

⚠️ **BE PRECISE ABOUT WHOSE CLAIM IS BEING TESTED.** The park docstring's parenthesis is about the PARK
bucket's opponent mix over a 3-season window. H2 measures the PLAYER's strength of schedule. They are
siblings, not the same quantity — the player-level one is the one that could bias a translation, which is
why it is the one measured here. Reporting this as "the park slice's assertion is refuted/confirmed"
without that distinction would be overclaiming.

THE ARMS (≥3 formulations + the direct-learned foil, per §0.5)
--------------------------------------------------------------
  | arm                  | formulation                                                             |
  |----------------------|-------------------------------------------------------------------------|
  | `L0_foil`            | ⭐ the shipped E7.12-slice-1 configuration, NO opponent adjustment       |
  | `O1_opp_leaguenorm`  | ⭐ HEADLINE — WITHIN-league strength of schedule (genuinely new info)    |
  | `O2_opp_levelnorm`   | the naive level-normalised factor                                       |
  | `O3_opp_window3`     | the 3-season opponent window (the window the park assertion assumed)     |
  | `O4_opp_extra`       | ⭐ NESTS THE FOIL — the opponent delta as a fixed regressor              |

⭐ **WHY THE HEADLINE IS LEAGUE-NORMALISED, DECIDED BY MEASUREMENT BEFORE THE RUN.** E7.3 already fits a
per-LEAGUE random intercept. Measured on the live substrate, **19–41% of the LEVEL-normalised factor's
variance is BETWEEN-LEAGUE** (the Mexican League sits at 0.89 on k_pct against the International League's
1.03), so that form is substantially a re-encoding of a feature the model already has and a lift on it
would be unattributable to opponent quality. League normalisation drops the between-league share to
0.3–1.0%. `O2_opp_levelnorm` is kept precisely so that gap is visible in the leaderboard rather than
asserted in a docstring.

🪤 **ANCHORS**
  | trap                                                          | anchor              | must hold |
  |---------------------------------------------------------------|---------------------|-----------|
  | "any dispersed multiplier helps" (not the opposition)          | `A_opp_placebo`     | must LOSE |
  | SELF-INFLATION: his own hits made his opponents look weak, so  | `A_opp_noloo`       | must not  |
  | dividing by that weakness shrinks HIM toward the mean          |                     | BEAT LOO  |
  | MAE is inverted on this cohort                                 | `A_degenerate_mean` | must LOSE |

  The self-inflation anchor is STRONGER here than its park sibling: a park factor's home and road buckets
  both contain the player's own team so self-inclusion largely cancels, whereas an opponent factor has no
  such cancellation. Shrinkage toward the mean lowers MAE against a regressed target whether or not
  opponent quality exists, so a non-LOO adjustment would MANUFACTURE the lift and no deflation gate could
  see it.
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

from betting_ml.scripts.milb_mle.h_harness import (  # noqa: E402
    FDR_ALPHA,
    MIN_PCT_ROWS_MOVED,
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
from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    ArchetypePriorRefProjector,
    PartialPoolProjector,
    build_target,
)
from betting_ml.scripts.milb_mle.opponent_context import (  # noqa: E402
    OPPONENT_METRICS,
    OpponentSpec,
    apply_opponent,
    opponent_coverage,
    opponent_spread,
)
from betting_ml.scripts.milb_mle.park_context import ContextSpec, apply_context  # noqa: E402
from betting_ml.utils.design_block import (  # noqa: E402
    design_block_from_ladder_results,
    insert_design_block,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES, SideConfig, _paired_p, bh_fdr  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_15_h1 import SHIPPED_CONTEXT  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import propensity_for_fold  # noqa: E402
from betting_ml.scripts.milb_mle.survivorship import propensity_strata  # noqa: E402

log = logging.getLogger("e7_15.h2")

_KEYS = ["player_id", "level"]
_ART = (_PROJECT_ROOT
        / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"


@dataclass(frozen=True)
class H2Arm:
    label: str
    spec: OpponentSpec
    kind: str            # foil | opponent | anchor
    note: str
    factor_suffix: str = ""      # which built factor variant this arm reads
    projector: str = "pool"      # pool | degenerate

    @property
    def selectable(self) -> bool:
        return self.kind == "opponent"


ARMS: tuple[H2Arm, ...] = (
    H2Arm("L0_foil", OpponentSpec(mode="off"), "foil",
          "⭐ THE DIRECT-LEARNED FOIL — the shipped E7.12-slice-1 configuration, no opponent adjustment"),
    H2Arm("O1_opp_leaguenorm", OpponentSpec(mode="exposure"), "opponent",
          "⭐ HEADLINE — WITHIN-league strength of schedule. League-normalised because 19–41% of the "
          "level-normalised factor is between-league variance E7.3's league intercepts already carry.",
          ""),
    H2Arm("O2_opp_levelnorm", OpponentSpec(mode="exposure"), "opponent",
          "the NAIVE level-normalised factor — kept so the league re-encoding is visible in the "
          "leaderboard rather than asserted", "_levelnorm"),
    H2Arm("O3_opp_window3", OpponentSpec(mode="exposure", window=3), "opponent",
          "a 3-season opponent bucket — the window the park slice's assertion assumed", "_w3"),
    H2Arm("O4_opp_extra", OpponentSpec(mode="exposure", as_extra=True), "opponent",
          "⭐ NESTS THE FOIL — the raw rate is kept and the opponent DELTA enters as a fixed regressor, "
          "so a win is unambiguously 'opponent quality adds information'", ""),
    # ── anchors ──
    H2Arm("A_opp_placebo", OpponentSpec(mode="placebo"), "anchor",
          "DEGENERATE — the same opponent factors permuted across players within a level. Catches "
          "'dividing by any dispersed number helps'.", ""),
    H2Arm("A_opp_noloo", OpponentSpec(mode="exposure_noloo"), "anchor",
          "⭐ SELF-INFLATION DIAGNOSTIC — the factor WITHOUT removing the player's own games. His hits "
          "are in his opponents' allowed-rate bucket, so dividing by a weakness he created shrinks HIM "
          "toward the mean and lowers MAE whether or not opponent quality exists.", "_noloo"),
    H2Arm("A_degenerate_mean", OpponentSpec(mode="off"), "anchor",
          "DEGENERATE CEILING (NF-D11/NF-D14) — predict the population mean of the target.",
          "", "degenerate"),
)

_BY_LABEL = {a.label: a for a in ARMS}

H2_ANCHORS: tuple[Anchor, ...] = (
    Anchor("A_degenerate_mean", "block", "the DEGENERATE CEILING — predict the population mean",
           "A metric a 'predict nothing' arm wins cannot select a projection (NF-D11); the selection "
           "metric is inverted for this cohort.",
           must_move=False),   # a degenerate PROJECTOR transforms no feature — legitimately moves 0%
    Anchor("A_opp_placebo", "refute", "the PLACEBO — opponent factors permuted within level",
           "Whatever the adjustment does, it is not the opposition — it is 'divide by any dispersed "
           "number', which shrinks toward the mean and lowers MAE on its own."),
    Anchor("A_opp_noloo", "refute", "the NON-LOO factor — the player's own games left in his opponents' "
           "bucket",
           "The adjustment's apparent edge is the player shrinking HIMSELF toward the mean via his own "
           "contribution to his opponents' allowed rates, not a competition-quality correction."),
)


@dataclass
class H2Result:
    metric: str
    prior_scale: float
    shipped_spec: ContextSpec
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
    spread: pd.DataFrame
    coverage: dict
    deflation: dict
    dsr: dict
    anchors: dict
    stratified: pd.DataFrame
    stratified_moved: pd.DataFrame
    composition: pd.DataFrame
    verdict: str
    winner: str
    reasons: list[str] = field(default_factory=list)
    oracle_floor_ok: bool = True


def _context_for(context: pd.DataFrame, metrics: tuple[str, ...], suffix: str) -> pd.DataFrame:
    """Present the requested factor VARIANT under the canonical `of_<m>_exposure` names.

    🪤 Renaming a variant onto the canonical name while the canonical column still exists produces
    DUPLICATE columns, and `df.get(col)` then returns a DataFrame instead of a Series — so the originals
    are dropped first. This bit the builder once already; one comment, both places.
    """
    if not suffix:
        keep = _KEYS + [f"of_{m}_exposure" for m in metrics if f"of_{m}_exposure" in context.columns]
        return context[keep].copy()
    cols = {f"of_{m}_exposure{suffix}": f"of_{m}_exposure" for m in metrics
            if f"of_{m}_exposure{suffix}" in context.columns}
    if not cols:
        return pd.DataFrame(columns=_KEYS)
    return context[_KEYS + list(cols)].rename(columns=cols).copy()


def _projector(arm: H2Arm, prior_scale: float, weight_col: str | None):
    if arm.projector == "degenerate":
        return ArchetypePriorRefProjector()
    extra = ("opp_delta",) if arm.spec.as_extra else ()
    return PartialPoolProjector(prior_scale=prior_scale, weight_col=weight_col, extra_cols=extra)


def run_h2(pairs: pd.DataFrame, park: pd.DataFrame | None, opp: pd.DataFrame, metric: str,
           side: SideConfig, arms: tuple[H2Arm, ...] = ARMS,
           *, propensity_cache: dict | None = None) -> H2Result:
    """Score every arm under the E7.3 fold structure, learner held fixed at the shipped configuration."""
    shipped = SHIPPED_CONTEXT[side.player_type].get(metric, ContextSpec())
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)
    metrics = OPPONENT_METRICS[side.player_type]

    # the park/run-env-adjusted rate the shipped model reads — the opponent factor divides THAT, so the
    # two adjustments compose in the order they are physically defined (where → when → who)
    adjusted = apply_context(pairs, park, shipped, metric, tuple(_KEYS))
    base = build_target(adjusted, cfg)
    base_mask = base["has_target"].to_numpy(bool)
    labelled = base[base_mask]
    cohorts = sorted(int(y) for y in labelled["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"[{metric}] need ≥2 evaluable debut cohorts; got {fold_cohorts}")

    frames, coverage = {}, {}
    for arm in arms:
        ctx = _context_for(opp, metrics, arm.factor_suffix)
        adj = apply_opponent(adjusted, ctx, arm.spec, metric, tuple(_KEYS))
        f = build_target(adj, cfg)
        if not np.array_equal(f["has_target"].to_numpy(bool), base_mask):
            raise AssertionError(
                f"[{metric}/{arm.label}] the opponent adjustment changed the LABELLED POPULATION — arms "
                f"would be scored on different players, which is not an ablation.")
        frames[arm.label] = f
        coverage[arm.label] = opponent_coverage(adj, metric)

    mae = pd.DataFrame(index=fold_cohorts, columns=[a.label for a in arms], dtype=float)
    err_rows, notes = [], []
    propensity_cache = propensity_cache if propensity_cache is not None else {}
    for year in fold_cohorts:
        strat = propensity_cache.get(year)
        if strat is None:
            try:
                pf = propensity_for_fold(pairs, year)
                strat = pf.propensity[_KEYS].assign(
                    stratum=propensity_strata(pf.propensity["propensity"]))
            except Exception as e:  # noqa: BLE001
                notes.append(f"fold {year} propensity: {type(e).__name__}: {e}")
                strat = pd.DataFrame(columns=_KEYS + ["stratum"])
            propensity_cache[year] = strat
        for arm in arms:
            f = frames[arm.label]
            f = f[f["has_target"]]
            train, test = f[f["debut_cohort"] < year], f[f["debut_cohort"] == year]
            if train.empty or test.empty:
                continue
            try:
                mdl = _projector(arm, scale, shipped.weight_col).fit(train)
                yhat, _ = mdl.predict(test)
                err = np.abs(test["target"].to_numpy(float) - yhat)
                mae.loc[year, arm.label] = float(np.mean(err))
                err_rows.append(pd.DataFrame({
                    "fold": year, "arm": arm.label, "player_id": test["player_id"].to_numpy(),
                    "level": test["level"].to_numpy(), "abs_err": err,
                    "moved": (pd.to_numeric(test.get("opp_delta"), errors="coerce")
                              .fillna(0.0).abs() > 1e-12).to_numpy()}))
            except Exception as e:  # noqa: BLE001
                notes.append(f"fold {year} arm {arm.label}: {type(e).__name__}: {e}")

    rows_df = pd.concat(err_rows, ignore_index=True) if err_rows else pd.DataFrame()
    strata = [s.assign(fold=y) for y, s in propensity_cache.items() if not s.empty]
    if not rows_df.empty and strata:
        sa = pd.concat(strata, ignore_index=True)
        rows_df["player_id"] = rows_df["player_id"].astype(str)
        sa["player_id"] = sa["player_id"].astype(str)
        rows_df = rows_df.merge(sa, on=["fold"] + _KEYS, how="left")

    foil = mae["L0_foil"]
    rows = []
    for arm in arms:
        d = (foil - mae[arm.label]).to_numpy(float)
        d = d[np.isfinite(d)]
        cov = coverage.get(arm.label, {})
        rows.append({
            "arm": arm.label, "kind": arm.kind, "selectable": arm.selectable,
            "active": (arm.label == "L0_foil" or arm.projector == "degenerate"
                       or float(cov.get("pct_rows_moved") or 0.0) > MIN_PCT_ROWS_MOVED),
            "oos_mae": float(mae[arm.label].mean(skipna=True)),
            "pct_lift_vs_foil": (100.0 * float(np.mean(d)) / float(foil.mean(skipna=True))
                                 if len(d) and foil.mean(skipna=True) else np.nan),
            "fold_win_rate": float(np.mean(d > 0)) if len(d) else np.nan,
            "p_one_sided": _paired_p((foil - mae[arm.label]).to_numpy(float)),
            "pct_rows_moved": cov.get("pct_rows_moved"),
            "factor_p05": cov.get("factor_p05"), "factor_p95": cov.get("factor_p95"),
            "note": arm.note,
        })
    leaderboard = pd.DataFrame(rows).sort_values("oos_mae").reset_index(drop=True)

    eligible = [a.label for a in arms if a.selectable or a.label == "L0_foil"]
    defl = deflation_report(mae, eligible)
    defl["whole_field"] = deflation_report(mae)
    dsr = dsr_report(mae, eligible)
    oracle_ok = bool(np.nanmin(leaderboard["oos_mae"].to_numpy(float)) >= -1e-9)

    reasons: list[str] = list(notes)
    sel = leaderboard[leaderboard["selectable"] & leaderboard["active"]]
    best = str(sel.iloc[0]["arm"]) if not sel.empty else "L0_foil"
    anchors, anchor_verdict, anchor_reason = evaluate_anchors(
        mae, H2_ANCHORS, best, "L0_foil", coverage=coverage)
    anchors["oracle_floor_ok"] = oracle_ok
    anchors["best_arm_mae"] = float(leaderboard.loc[leaderboard["arm"] == best, "oos_mae"].iloc[0]) \
        if best in set(leaderboard["arm"]) else np.nan
    stratified = stratified_lift(rows_df)
    stratified_moved = stratified_lift(rows_df, moved_only=True)
    low, low_all = low_tercile_read(stratified, stratified_moved, best)
    anchors["low_propensity_tercile_lift_pct"] = low
    anchors["low_propensity_tercile_lift_pct_all_rows"] = low_all

    verdict, winner = "DROP", "L0_foil"
    foil_mae = float(leaderboard.loc[leaderboard["arm"] == "L0_foil", "oos_mae"].iloc[0])
    if not oracle_ok:
        reasons.append("⛔ ORACLE-FLOOR VIOLATION — a candidate scored MAE < 0; the metric is inverted.")
        verdict = "BLOCKED"
    elif anchor_verdict:
        reasons.append(anchor_reason)
        verdict = anchor_verdict
    else:
        inactive = leaderboard[leaderboard["selectable"] & ~leaderboard["active"]]["arm"].tolist()
        if inactive:
            reasons.append(
                f"ℹ️ INACTIVE arms (the adjustment moved <{MIN_PCT_ROWS_MOVED}% of rows, so they are the "
                f"foil in disguise and cannot be selected): {', '.join(inactive)}. A mechanism that "
                f"cannot act is a finding, not an omission (NF1.9).")
        if sel.empty:
            reasons.append("🟡 no ELIGIBLE arm remains. The shipped configuration stands for this metric.")
        else:
            cand = sel.iloc[0]
            passed, reason = numeric_gate(cand, foil_mae, defl, dsr, "opponent-quality adjustment")
            reasons.append(reason)
            if passed:
                verdict, winner = "ADD", str(cand["arm"])
                if metric in side.board_metrics and np.isfinite(low) and low < 0:
                    verdict, winner = "DROP", "L0_foil"
                    reasons.append(
                        f"⛔ LOW-TERCILE DOWNGRADE — `{cand['arm']}` improves the OVERALL held-out MAE "
                        f"but is {low:+.3f}% in the LOWEST promotion-propensity tercile. A board metric "
                        f"that helps the players we do NOT serve is not a board improvement (H5).")

    return H2Result(
        metric=metric, prior_scale=scale, shipped_spec=shipped, leaderboard=leaderboard,
        mae_by_fold=mae, fold_cohorts=fold_cohorts,
        spread=opponent_spread(opp, (metric,)), coverage=coverage, deflation=defl, dsr=dsr,
        anchors=anchors, stratified=stratified, stratified_moved=stratified_moved,
        composition=propensity_composition(rows_df), verdict=verdict, winner=winner, reasons=reasons,
        oracle_floor_ok=oracle_ok)


def write_report(results: dict[str, H2Result], fdr: dict, nulls: dict, path: Path,
                 side: SideConfig, spread: pd.DataFrame, reliability: pd.DataFrame,
                 decomposition: pd.DataFrame) -> None:
    def md(df: pd.DataFrame) -> str:
        return df.to_markdown(index=False) if df is not None and not df.empty else "_(empty)_"

    L: list[str] = []
    A = L.append
    A(f"# E7.15 H2 — the opponent / competition-quality adjustment ({side.player_type} side)\n")
    A(f"_generated {datetime.now(timezone.utc).isoformat()} · foil = the SHIPPED E7.12-slice-1 "
      f"configuration · `best_alpha = 0`_\n")
    A("> ⚠️ **A projection, not an edge claim.** H2 tests an assertion that has been sitting untested "
      "under a shipped feature: `build_park_context.py` says the park factor's residual is \"the park "
      "(plus the opponent mix, **which averages out** over a 3-season window)\". This slice measures the "
      "player-level version of that claim and only then asks whether correcting for it helps.\n")
    A("> ⚠️ **Whose claim, precisely.** The park docstring's parenthesis is about the PARK bucket's "
      "opponent mix. H2 measures the PLAYER's strength of schedule — the sibling quantity, and the one "
      "that could actually bias a translation. They are not the same claim and are not reported as if "
      "they were.\n")

    A("## 1. ⭐ The measurement — does the competition a prospect faced actually vary?\n")
    A("This is the primary deliverable and it is worth having whichever way the bake-off lands.\n")
    A("\n**Observed spread of the per-player opponent factor**\n")
    A(md(spread))
    A("\n**Is that spread real, or is it the estimator?** Split-half reliability: the player's opponents "
      "are split into two halves, a factor is built on each, and the halves are correlated across "
      "players (Spearman-Brown to full length).\n")
    A(md(reliability))
    A("\n⚠️ **This estimator has a KNOWN DOWNWARD BIAS and is a ONE-SIDED instrument.** A league plays a "
      "roughly BALANCED schedule, so a player's two halves are mechanically ANTI-correlated when there "
      "is no real signal — which is why the league-normalised readings come back NEGATIVE rather than "
      "0. The negativity is itself the fingerprint of a balanced schedule. It can support \"there is no "
      "LARGE within-league component\"; it cannot be quoted as a precise reliability.\n")
    A("\n**The POSITIVE CONTROL** is what makes the near-zero reading mean anything (NF1.7 (a)): the "
      "SAME estimator on the SAME rows reads high for the LEVEL-normalised factor, whose large "
      "between-league component is shared by both halves and so escapes the fixed-sum constraint.\n")
    A("\n**How much of the factor is a LEAGUE effect the model already has?** E7.3 fits a per-league "
      "random intercept, so any part of the factor that is constant within a league is NOT new "
      "information — it is a re-encoding of a shipped feature, and a lift on it would be "
      "unattributable to opponent quality. This table is why the headline arm is league-normalised.\n")
    A(md(decomposition))

    A("\n## 2. Verdict by metric\n")
    rows = []
    for m, r in results.items():
        lb = r.leaderboard
        cand = lb[lb["selectable"] & lb["active"]]
        best = cand.iloc[0] if not cand.empty else None
        d = (r.dsr or {}).get("eligible") or {}
        rows.append({
            "metric": m, "verdict": r.verdict, "winner": r.winner,
            "best_arm": None if best is None else best["arm"],
            "pct_lift_vs_foil": None if best is None else round(float(best["pct_lift_vs_foil"]), 3),
            "fold_win_rate": None if best is None else best["fold_win_rate"],
            "p_one_sided": None if best is None else best["p_one_sided"],
            "BH-FDR": fdr.get(m), "PBO(eligible)": r.deflation.get("pbo"), "DSR(eligible)": d.get("dsr"),
        })
    A(md(pd.DataFrame(rows)))

    A("\n## 2b. ⭐ Reading the null honestly — is it the data, or is it my gate?\n")
    A(f"Re-deciding the entire run with the deflation gates REMOVED — no PBO ceiling, no DSR floor — "
      f"leaves survivors: **{nulls['survivors_with_PBO_and_DSR_gates_REMOVED'] or 'NONE'}**. "
      f"⇒ {nulls['binding_constraint']} (family of {nulls['family_size']}; strictest BH rung "
      f"p ≤ {nulls['strictest_bh_cutoff']}).\n")
    A(md(pd.DataFrame(nulls["per_metric"])))

    for m, r in results.items():
        A(f"\n## 3.{m} — the arm set (`partial_pool@{r.prior_scale:g}`, context "
          f"`{r.shipped_spec.label}`, learner held fixed)\n")
        A(md(r.leaderboard[["arm", "kind", "active", "oos_mae", "pct_lift_vs_foil", "fold_win_rate",
                            "p_one_sided", "pct_rows_moved", "factor_p05", "factor_p95"]].round(6)))
        A("\n**Anchors**\n")
        for a in H2_ANCHORS:
            res = r.anchors.get(f"{a.label}__vs_best") or r.anchors.get(f"{a.label}__vs_None") or {}
            A(f"- `{a.label}` ({a.what}): challenger wins {res.get('challenger_fold_wins')}/"
              f"{res.get('n_folds')} folds, p={res.get('p_challenger_better')}, "
              f"violated={res.get('violated')}")
        if not r.composition.empty:
            A("\n**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the "
              "one richest in Triple-A rows, not low-level prospects):\n")
            A(md(r.composition))
        for label, frame in (("rows the adjustment CAN move (what the H5 gate reads)", r.stratified_moved),
                             ("ALL scored rows", r.stratified)):
            if frame.empty:
                continue
            A(f"\n**Per promotion-propensity tercile — {label}** (stratum 0 = LOWEST propensity):\n")
            piv = (frame.pivot(index="arm", columns="stratum", values="pct_lift_vs_foil")
                   .round(3).reset_index())
            piv.columns = ["arm"] + [f"tercile_{c}_lift_%" for c in piv.columns[1:]]
            A(md(piv))
        d = r.deflation
        A(f"\n**Deflation** — PBO(eligible) `{d.get('pbo')}` · Bailey OS degradation "
          f"`{d.get('os_gap_pct')}%` · contender spread `{d.get('contender_spread_pct')}%` · "
          f"whole-field spread `{d.get('full_spread_pct')}%`\n")
        A("\n**Reading**\n")
        for reason in r.reasons:
            A(f"- {reason}")

    A("\n## 4. Limitations\n")
    A("- **The reliability instrument is one-sided.** The balanced-schedule fixed-sum constraint biases "
      "split-half reliability DOWN for the within-league factor, so the noise-corrected spread is a "
      "LOWER bound on the noise share, not a point estimate.\n")
    A("- **Opponent quality is measured at TEAM-SEASON grain**, not per-pitcher-faced. A prospect who "
      "happened to face a team's ace three times is scored as having faced that team. Per-pitcher "
      "matchup data exists in the logs and would be a finer instrument; it is not what a team-strength "
      "adjustment needs, and it is a different (larger) story.\n")
    A("- **The LOO is at GAME level**, so it removes the focal player's teammates' lines from his "
      "opponents' buckets too. Conservative, and the only form that works identically on both sides.\n")
    A("- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.\n")
    db = design_block_from_ladder_results(
        results, fold_rule="leave-one-MLB-debut-cohort-out (n_cohorts)")
    path.write_text(insert_design_block("\n".join(L) + "\n", db))
    log.info("wrote %s", path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.15 H2 — the opponent-quality adjustment bake-off")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter")
    p.add_argument("--metrics", nargs="+", default=None)
    p.add_argument("--arms", nargs="+", default=None)
    p.add_argument("--out-dir", default=str(_ART))
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[args.player_type]
    suffix = side.reduced.artifact_suffix
    e73 = _REPORT_DIR / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(e73 / side.pairs_name)
    park_path = _REPORT_DIR / "e7_12_artifacts" / f"mle_park_context{suffix}.parquet"
    opp_path = Path(args.out_dir) / f"mle_opponent_context{suffix}.parquet"
    if not opp_path.exists():
        p.error(f"opponent context not found at {opp_path} — run build_opponent_context.py "
                f"--player-type {side.player_type} first (OPERATOR-RUN, ~3¼ min). Without it every "
                f"opponent arm is a silent no-op, which would read as an honest null.")
    park = pd.read_parquet(park_path) if park_path.exists() else None
    opp = pd.read_parquet(opp_path)
    opp["player_id"] = opp["player_id"].astype(str)
    pairs["player_id"] = pairs["player_id"].astype(str)
    metrics = args.metrics or list(OPPONENT_METRICS[side.player_type])
    arms = ARMS if not args.arms else tuple(_BY_LABEL[a] for a in args.arms)
    if "L0_foil" not in {a.label for a in arms}:
        arms = (_BY_LABEL["L0_foil"],) + arms

    results: dict[str, H2Result] = {}
    cache: dict = {}
    for m in metrics:
        log.info("=== E7.15 H2 [%s]: %s ===", side.player_type, m)
        results[m] = run_h2(pairs, park, opp, m, side, arms, propensity_cache=cache)
        log.info("[%s] verdict=%s winner=%s", m, results[m].verdict, results[m].winner)
        for r in results[m].reasons:
            log.info("[%s] %s", m, r)

    pvals = {}
    for m, r in results.items():
        cand = r.leaderboard[r.leaderboard["selectable"] & r.leaderboard["active"]]
        pvals[m] = (float(cand.iloc[0]["p_one_sided"])
                    if not cand.empty and pd.notna(cand.iloc[0]["p_one_sided"]) else None)
    fdr = bh_fdr(pvals, alpha=FDR_ALPHA)
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict, r.winner = "DROP", "L0_foil"
            r.reasons.append(
                f"⛔ FDR-DOWNGRADED — cleared the per-metric bar (p={pvals.get(m)}) but does NOT survive "
                f"Benjamini-Hochberg over the {len(pvals)}-metric family at α={FDR_ALPHA}.")
    nulls = null_analysis(results, pvals)
    log.info("NULL ANALYSIS — %s", nulls["binding_constraint"])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"e7_15_h2{suffix}_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_type": side.player_type,
        "foil": "the SHIPPED E7.12-slice-1 configuration per metric (learner + weight_col held fixed)",
        "bh_fdr_alpha": FDR_ALPHA, "bh_fdr": fdr, "null_analysis": nulls,
        "per_metric": {m: {
            "verdict": r.verdict, "winner": r.winner,
            "leaderboard": r.leaderboard.to_dict(orient="records"),
            "mae_by_fold": r.mae_by_fold.to_dict(), "coverage": r.coverage,
            "deflation": r.deflation, "dsr": r.dsr, "anchors": r.anchors,
            "stratified": r.stratified.to_dict(orient="records"),
            "stratified_moved_rows_only": r.stratified_moved.to_dict(orient="records"),
            "propensity_tercile_composition": r.composition.to_dict(orient="records"),
            "reasons": r.reasons,
        } for m, r in results.items()},
    }, indent=2, default=float))

    if not args.no_report:
        def _csv(name: str) -> pd.DataFrame:
            f = out_dir / f"{name}{suffix}.csv"
            return pd.read_csv(f) if f.exists() else pd.DataFrame()

        write_report(results, fdr, nulls,
                     _REPORT_DIR / f"e7_15_h2_opponent_quality{suffix}.md", side,
                     opponent_spread(opp, tuple(metrics)),
                     _csv("e7_15_h2_opponent_reliability"), _csv("e7_15_h2_league_decomposition"))
    log.info("E7.15 H2 VERDICTS (%s): %s", side.player_type, {m: r.verdict for m, r in results.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
