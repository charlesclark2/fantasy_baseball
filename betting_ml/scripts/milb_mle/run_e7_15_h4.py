"""run_e7_15_h4.py — MLB Edge-E7.15 H4: regress the TARGET toward true talent.

⚠️ **OPERATOR-RUN (>2 min).** 8 arms × the side's metrics × leave-one-debut-cohort-out folds.
No build step — H4 reads the E7.3 pairs table and nothing else.

    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h4
    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h4 --player-type pitcher

WHAT IT DECIDES
---------------
The label is the realized MLB rate over a player's first seasons, admitted at 150 PA. A 150-PA label is
~2.8x noisier a reading of the same talent than a 1,200-PA one, yet the fit treats both as equally valid
outputs of the map. H4 shrinks each TRAINING label toward a prior by its own reliability, so the model
learns the map to true talent rather than to a noisy realization.

⚠️ **H4 CHANGES THE ESTIMAND — THE ONE THING H1 DELIBERATELY DID NOT DO.** Readiness lock 3 requires the
board and betting surfaces stay comparable, so the change is confined to the TRAINING target and every
arm is scored against the SAME untouched realized held-out rate. `evaluation_target_is_untouched` is
asserted per fold per arm; `shrink_training_target_only` has no code path that can reach the test rows.
⇒ **A WINNER HERE STILL COSTS COMPARABILITY** and cannot ship without re-running E7.5b's batter
head-to-head gate (and BUILDING the pitcher one, which does not exist) — readiness lock 6.

🪤 **THE CENTRAL HAZARD, NAMED BEFORE THE RUN.** MAE against a noisy target REWARDS SHRINKAGE PER SE:
compressing predictions toward the mean lowers absolute error whether or not the map improved. That is
the E2.1-r / NF-D11 inversion class — and here the mechanism IS shrinkage, so the inversion would look
exactly like success. The field therefore contains its own degenerate (`A_shrink_full`, a constant
training target) and its own level-matched foil (`A_shrink_constant`, identical average compression with
zero per-player content). **If the constant foil ties the real arm, the reliability story is refuted and
what was measured is a global rescale the regression already had** — slice 1's `constant_reliability`
instrument applied to the target instead of the feature.

📌 **REGISTERED BUT NOT RUN — THE "MORE DATA, NOT MORE STATISTICS" ALTERNATIVE.** The other way to
de-noise a label is a LONGER label window (3-4 MLB seasons instead of 2). It is not in this field for a
stated reason, not an oversight: a longer window changes the LABELLED POPULATION (the newest cohorts no
longer have a complete label), so the arms would be scored on different players and the comparison
would not be an ablation. Running it honestly needs a pairs rebuild per window plus a population
intersection, which is a separate slice with its own operator build — recorded here with its cost so
the choice is visible rather than silently skipped.
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
from betting_ml.scripts.milb_mle.park_context import ContextSpec, apply_context  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES, SideConfig, _paired_p, bh_fdr  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import propensity_for_fold  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_15_h1 import SHIPPED_CONTEXT  # noqa: E402
from betting_ml.scripts.milb_mle.survivorship import propensity_strata  # noqa: E402
from betting_ml.scripts.milb_mle.target_regression import (  # noqa: E402
    TargetSpec,
    evaluation_target_is_untouched,
    shrink_training_target_only,
    target_coverage,
)

log = logging.getLogger("e7_15.h4")

_KEYS = ["player_id", "level"]
_ART = (_PROJECT_ROOT
        / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"


@dataclass(frozen=True)
class H4Arm:
    label: str
    spec: TargetSpec
    kind: str            # foil | target | anchor
    note: str
    projector: str = "pool"

    @property
    def selectable(self) -> bool:
        return self.kind == "target"


ARMS: tuple[H4Arm, ...] = (
    H4Arm("L0_foil", TargetSpec(), "foil",
          "⭐ THE DIRECT-LEARNED FOIL — the shipped E7.12-slice-1 configuration, trained on the raw "
          "realized MLB rate"),
    H4Arm("R1_eb_shrink", TargetSpec(mode="eb"), "target",
          "⭐ HEADLINE — each training label shrunk toward the population mean by its OWN reliability "
          "PA/(PA+k), k the metric's stabilization point. A 150-PA label stops counting as much as a "
          "1,200-PA one."),
    H4Arm("R2_eb_shrink_2k", TargetSpec(mode="eb", k_mult=2.0), "target",
          "MATCHED PARTNER to R1 — twice the stabilization constant. 'the published k is right for a "
          "MiLB-translation label' is an assumption, not a measurement, and a field carrying only one k "
          "cannot test it."),
    H4Arm("R3_shrink_to_level", TargetSpec(mode="eb_level"), "target",
          "shrink toward the row's LEVEL mean rather than the global mean — the anchor the feature-side "
          "reliability shrink already uses, applied to the target for symmetry"),
    # ── anchors ──
    H4Arm("A_target_identity", TargetSpec(mode="identity"), "anchor",
          "BYTE NO-OP — r = 1. Its MAE gap to the foil must be EXACTLY 0."),
    H4Arm("A_shrink_constant", TargetSpec(mode="constant"), "anchor",
          "⭐ THE MATCHED FOIL THAT DECIDES THE SLICE — the SAME average compression with ZERO "
          "per-player content. If it ties R1, 'reliability weighting' was a global rescale the "
          "regression already had, not a per-player de-noising (slice 1's `constant_reliability` "
          "instrument, applied to the target instead of the feature).",
          ),
    H4Arm("A_shrink_full", TargetSpec(mode="full"), "anchor",
          "⭐ THE FAMILY'S OWN DEGENERATE — r = 0, so the training target is CONSTANT and the model can "
          "learn nothing. Must lose catastrophically; a metric that likes it is inverted, which is the "
          "specific risk when the mechanism under test IS shrinkage."),
    H4Arm("A_degenerate_mean", TargetSpec(), "anchor",
          "DEGENERATE CEILING (NF-D11/NF-D14) — predict the population mean of the target.",
          "degenerate"),
)

_BY_LABEL = {a.label: a for a in ARMS}

H4_ANCHORS: tuple[Anchor, ...] = (
    Anchor("A_degenerate_mean", "block", "the DEGENERATE CEILING — predict the population mean",
           "A metric a 'predict nothing' arm wins cannot select a projection (NF-D11).",
           must_move=False),
    Anchor("A_shrink_full", "block", "TOTAL shrink — a CONSTANT training target",
           "A model trained on a constant target has learned nothing, so its winning means MAE against "
           "this noisy label is rewarding COMPRESSION rather than translation quality. The whole H4 "
           "family would be measuring the inversion, not the mechanism."),
    # ⬆ must_move stays ON: r=0 rewrites every training label, so this anchor CAN be inert (a silently
    # disabled shrink would make it byte-identical to the foil) and the guard is meaningful.
    Anchor("A_target_identity", "noop", "the BYTE NO-OP — r = 1",
           "The harness changed something it did not declare; no arm's margin can be trusted."),
    Anchor("A_shrink_constant", "refute", "CONSTANT shrink — identical average compression, no "
           "per-player content",
           "The gain is a global rescale of the target, which the regression's own slope already "
           "absorbs — not a per-player de-noising. The stated mechanism is refuted.",
           defender="R1_eb_shrink"),
)


@dataclass
class H4Result:
    metric: str
    prior_scale: float
    shipped_spec: ContextSpec
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
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


def _projector(arm: H4Arm, prior_scale: float, weight_col: str | None):
    if arm.projector == "degenerate":
        return ArchetypePriorRefProjector()
    return PartialPoolProjector(prior_scale=prior_scale, weight_col=weight_col)


def run_h4(pairs: pd.DataFrame, park: pd.DataFrame | None, metric: str, side: SideConfig,
           arms: tuple[H4Arm, ...] = ARMS, *, propensity_cache: dict | None = None,
           max_folds: int | None = None) -> H4Result:
    """Score every arm under the E7.3 fold structure, learner held fixed at the shipped configuration."""
    shipped = SHIPPED_CONTEXT[side.player_type].get(metric, ContextSpec())
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)

    adjusted = apply_context(pairs, park, shipped, metric, tuple(_KEYS))
    base = build_target(adjusted, cfg)
    labelled = base[base["has_target"]]
    cohorts = sorted(int(y) for y in labelled["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"[{metric}] need ≥2 evaluable debut cohorts; got {fold_cohorts}")
    if max_folds:
        fold_cohorts = fold_cohorts[-int(max_folds):]   # SMOKE ONLY — not a scoreable run

    mae = pd.DataFrame(index=fold_cohorts, columns=[a.label for a in arms], dtype=float)
    coverage: dict = {}
    notes, err_rows = [], []
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

        train_raw = labelled[labelled["debut_cohort"] < year]
        test = labelled[labelled["debut_cohort"] == year]
        if train_raw.empty or test.empty:
            continue

        for arm in arms:
            try:
                train = shrink_training_target_only(train_raw, metric, arm.spec)
                # 🔒 THE INVARIANT — every arm is scored against the SAME untouched realized rate. An
                # arm scored on its own shrunken label would be answering an easier question and the
                # leaderboard would rank the amount of shrinkage, not the quality of the map.
                if not evaluation_target_is_untouched(test, test):
                    raise AssertionError("the evaluation target was mutated")
                coverage.setdefault(arm.label, target_coverage(train, train_raw, arm.spec))

                mdl = _projector(arm, scale, shipped.weight_col).fit(train)
                yhat, _ = mdl.predict(test)
                err = np.abs(test["target"].to_numpy(float) - yhat)
                mae.loc[year, arm.label] = float(np.mean(err))
                err_rows.append(pd.DataFrame({
                    "fold": year, "arm": arm.label, "player_id": test["player_id"].to_numpy(),
                    "level": test["level"].to_numpy(), "abs_err": err, "moved": True}))
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
            "mean_shrink_r": cov.get("mean_shrink_r"),
            "target_sd_ratio": cov.get("target_sd_ratio"),
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
        mae, H4_ANCHORS, best, "L0_foil", coverage=coverage)

    refuted = dict(anchors.get("refuted_arms") or {})
    if refuted:
        for arm_label, why in refuted.items():
            reasons.append(f"⛔ MECHANISM REFUTED (scoped to `{arm_label}`) — {why} That arm is "
                           f"disqualified from selection; other arms on this metric are untouched.")
        sel = sel[~sel["arm"].isin(refuted)]
        best = str(sel.iloc[0]["arm"]) if not sel.empty else "L0_foil"

    anchors["oracle_floor_ok"] = oracle_ok
    stratified = stratified_lift(rows_df)
    stratified_moved = stratified_lift(rows_df, moved_only=True)
    low, low_all = low_tercile_read(stratified, stratified_moved, best)
    anchors["low_propensity_tercile_lift_pct"] = low
    anchors["low_propensity_tercile_lift_pct_all_rows"] = low_all

    # ⭐ THE INVERSION READING — recorded whatever the verdict. If the family's own degenerate scores
    # WELL, MAE on this cohort is rewarding compression rather than translation quality.
    def _lift(label: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == label, "pct_lift_vs_foil"]
        return float(r.iloc[0]) if len(r) else float("nan")

    anchors["shrinkage_inversion_probe_full_shrink_lift_pct"] = _lift("A_shrink_full")
    anchors["per_player_content_pct"] = _lift("R1_eb_shrink") - _lift("A_shrink_constant")

    verdict, winner = "DROP", "L0_foil"
    foil_mae = float(leaderboard.loc[leaderboard["arm"] == "L0_foil", "oos_mae"].iloc[0])
    if not oracle_ok:
        reasons.append("⛔ ORACLE-FLOOR VIOLATION — a candidate scored MAE < 0; the metric is inverted.")
        verdict = "BLOCKED"
    elif anchor_verdict:
        reasons.append(anchor_reason)
        verdict = anchor_verdict
    else:
        if sel.empty:
            reasons.append("🟡 no ELIGIBLE arm remains. The shipped configuration stands for this metric.")
        else:
            cand = sel.iloc[0]
            passed, reason = numeric_gate(cand, foil_mae, defl, dsr, "target regression")
            reasons.append(reason)
            if passed:
                verdict, winner = "ADD", str(cand["arm"])
                reasons.append(
                    "⚠️ ESTIMAND CHANGED — a winner here predicts SHRUNKEN true talent, not the realized "
                    "rate. Readiness lock 6 binds: a BATTER arm cannot ship without RE-RUNNING E7.5b's "
                    "batter head-to-head gate, and a PITCHER arm needs that gate BUILT (it does not "
                    "exist). Do not emit from this run.")
                if metric in side.board_metrics and np.isfinite(low) and low < 0:
                    verdict, winner = "DROP", "L0_foil"
                    reasons.append(
                        f"⛔ LOW-TERCILE DOWNGRADE — `{cand['arm']}` improves the OVERALL held-out MAE "
                        f"but is {low:+.3f}% in the LOWEST promotion-propensity tercile (H5).")

    return H4Result(
        metric=metric, prior_scale=scale, shipped_spec=shipped, leaderboard=leaderboard,
        mae_by_fold=mae, fold_cohorts=fold_cohorts, coverage=coverage, deflation=defl, dsr=dsr,
        anchors=anchors, stratified=stratified, stratified_moved=stratified_moved,
        composition=propensity_composition(rows_df), verdict=verdict, winner=winner, reasons=reasons,
        oracle_floor_ok=oracle_ok)


def write_report(results: dict[str, H4Result], fdr: dict, nulls: dict, path: Path,
                 side: SideConfig) -> None:
    def md(df: pd.DataFrame) -> str:
        return df.to_markdown(index=False) if df is not None and not df.empty else "_(empty)_"

    L: list[str] = []
    A = L.append
    A(f"# E7.15 H4 — regressing the TARGET toward true talent ({side.player_type} side)\n")
    A(f"_generated {datetime.now(timezone.utc).isoformat()} · foil = the SHIPPED E7.12-slice-1 "
      f"configuration · `best_alpha = 0`_\n")
    A("> ⚠️ **H4 CHANGES THE ESTIMAND — the one thing H1 deliberately did not do.** The change is "
      "confined to the TRAINING target; every arm is scored against the SAME untouched realized "
      "held-out rate, asserted per fold. A winner here still costs board/betting comparability and "
      "cannot ship without re-running E7.5b's batter gate (or BUILDING the pitcher one, which does not "
      "exist) — readiness lock 6.\n")
    A("> 🪤 **The central hazard, named before the run:** MAE against a noisy label REWARDS SHRINKAGE "
      "PER SE, and here the mechanism IS shrinkage — so the inversion would look exactly like success. "
      "The field carries its own degenerate (`A_shrink_full`, a constant training target) and its own "
      "level-matched foil (`A_shrink_constant`, same average compression, zero per-player content).\n")

    A("\n## Verdicts\n")
    A(md(pd.DataFrame([{
        "metric": m, "verdict": r.verdict, "winner": r.winner, "BH-FDR": fdr.get(m),
        "PBO(eligible)": r.deflation.get("pbo"), "DSR(eligible)": r.dsr.get("dsr"),
    } for m, r in results.items()])))

    A("\n## ⭐ The inversion probe and the per-player content\n")
    A("`full_shrink_lift` is what a model trained on a CONSTANT target scores. If it is positive, MAE on "
      "this cohort rewards compression rather than translation quality and the whole family is measuring "
      "the inversion. `per_player_content` is the real arm MINUS the constant-shrink foil: it is the part "
      "of any gain that is genuinely per-player rather than a global rescale.\n")
    A(md(pd.DataFrame([{
        "metric": m,
        "full_shrink_lift_pct": round(r.anchors.get(
            "shrinkage_inversion_probe_full_shrink_lift_pct", np.nan), 3),
        "per_player_content_pct": round(r.anchors.get("per_player_content_pct", np.nan), 3),
    } for m, r in results.items()])))

    for m, r in results.items():
        A(f"\n## {m}\n")
        A(f"_shipped foil: `{r.shipped_spec.label}` · prior_scale {r.prior_scale} · "
          f"{len(r.fold_cohorts)} folds {r.fold_cohorts}_\n")
        A(md(r.leaderboard.drop(columns=["note"], errors="ignore")))
        A("\n**Anchors**\n")
        for a in H4_ANCHORS:
            d = r.anchors.get(a.label)
            if isinstance(d, dict):
                A(f"- `{a.label}` ({a.what}): {d}")
        A(f"\n**Coverage (target units)**: {json.dumps(r.coverage, default=float)}\n")
        A("\n**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside "
          "every tercile read):\n")
        A(md(r.composition))
        A("\n**Reasons**\n")
        for x in r.reasons:
            A(f"- {x}")

    A("\n## Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)\n")
    A(f"**Binding constraint: {nulls['binding_constraint']}**\n")
    A(md(pd.DataFrame(nulls.get("per_metric", []))))

    A("\n## Registered but NOT run — the 'more data, not more statistics' alternative\n")
    A("The other way to de-noise a label is a LONGER label window (3-4 MLB seasons instead of 2). It is "
      "excluded for a stated reason rather than overlooked: a longer window changes the LABELLED "
      "POPULATION (the newest cohorts no longer have a complete label), so the arms would be scored on "
      "different players and the comparison would not be an ablation. Doing it honestly needs a pairs "
      "rebuild per window plus a population intersection — a separate slice with its own operator "
      "build.\n")
    A("\n- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.\n")
    path.write_text("\n".join(L) + "\n")
    log.info("wrote %s", path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.15 H4 — the target-regression bake-off")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter")
    p.add_argument("--metrics", nargs="+", default=None)
    p.add_argument("--arms", nargs="+", default=None)
    p.add_argument("--max-folds", type=int, default=None,
                   help="SMOKE ONLY — score just the last N folds. Not a scoreable run.")
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
    pairs["player_id"] = pairs["player_id"].astype(str)
    park_path = _REPORT_DIR / "e7_12_artifacts" / f"mle_park_context{suffix}.parquet"
    park = pd.read_parquet(park_path) if park_path.exists() else None

    metrics = args.metrics or list(side.metrics)
    arms = ARMS if not args.arms else tuple(_BY_LABEL[a] for a in args.arms)
    if "L0_foil" not in {a.label for a in arms}:
        arms = (_BY_LABEL["L0_foil"],) + arms

    results: dict[str, H4Result] = {}
    cache: dict = {}
    for m in metrics:
        log.info("=== E7.15 H4 [%s]: %s ===", side.player_type, m)
        results[m] = run_h4(pairs, park, m, side, arms, propensity_cache=cache,
                            max_folds=args.max_folds)
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
    (out_dir / f"e7_15_h4{suffix}_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_type": side.player_type,
        "estimand_note": "H4 changes the TRAINING target only; the evaluation target is the untouched "
                         "realized rate for every arm. A winner still costs board/betting comparability "
                         "(readiness lock 6).",
        "bh_fdr_alpha": FDR_ALPHA, "bh_fdr": fdr, "null_analysis": nulls,
        "per_metric": {m: {
            "verdict": r.verdict, "winner": r.winner,
            "leaderboard": r.leaderboard.to_dict(orient="records"),
            "mae_by_fold": r.mae_by_fold.to_dict(), "coverage": r.coverage,
            "deflation": r.deflation, "dsr": r.dsr, "anchors": r.anchors,
            "stratified": r.stratified.to_dict(orient="records"),
            "propensity_tercile_composition": r.composition.to_dict(orient="records"),
            "reasons": r.reasons,
        } for m, r in results.items()},
    }, indent=2, default=float))

    if not args.no_report:
        write_report(results, fdr, nulls,
                     _REPORT_DIR / f"e7_15_h4_target_regression{suffix}.md", side)
    log.info("E7.15 H4 VERDICTS (%s): %s", side.player_type, {m: r.verdict for m, r in results.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
