"""run_e7_15_h3.py — MLB Edge-E7.15 H3: the §0.5 bake-off for PLAYER-LEVEL STRUCTURE.

⚠️ **OPERATOR-RUN (>2 min).** 12 arms × the side's metrics × leave-one-debut-cohort-out folds, and the
three random-intercept arms each fit a ~600–1,050-column penalized design per fold (~1.1s each,
measured). No context build is needed — H3 reads the E7.3 pairs table and nothing else.

    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h3
    uv run python -m betting_ml.scripts.milb_mle.run_e7_15_h3 --player-type pitcher

WHAT IT DECIDES
---------------
The training matrix is one row per (player, level) with **the same MLB label on every one of a player's
rows** — 2,171 labelled batter rows from 736 players, 2.95× replication, and 57% of the fitted weight
carried by 42% of the people. H3 asks whether taking the PLAYER as the unit — by reweighting, by a
random intercept, or by reading his TRAJECTORY across levels — beats treating each row as independent.

⚠️ **NOT A LEAKAGE BUG.** Folds are debut cohorts and `debut_cohort` is a per-player join, so all of a
player's rows share one fold and no player straddles the train/test boundary. This is an efficiency and
weighting question only; framing it as leakage would be wrong.

⭐ **THE RANDOM-INTERCEPT ARMS ARE REGISTERED AS A DECOMPOSITION WITH AN EXPECTED LOSS.** With a label
constant within a player, a player intercept can absorb all BETWEEN-player variation, leaving the fixed
effects identified only by WITHIN-player contrasts — the same variation H1 measured and found null — and
a held-out player's intercept is 0 at predict time. We expect P3/P4 to lose; that measures where the
incumbent's skill lives. A win would overturn the reading. The direction is stated in
`e7_15_h3_preregistration.md`, written before any arm was scored.

🎏 **EVERY MECHANISM CARRIES ITS MATCHED FOIL** (NF-D15 g′) — `A_re_shuffled` for the random intercept
(same block width, same group-size multiset, wrong grouping), `T2_traj_raw` for the ladder's
contribution to the trajectory, `P2_dedup_sqrt` for the strength of the reweighting.
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
from betting_ml.scripts.milb_mle.level_ladder import (  # noqa: E402
    LadderSpec,
    build_transitions,
    fit_ladder,
)
from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    ArchetypePriorRefProjector,
    PartialPoolProjector,
    build_target,
)
from betting_ml.scripts.milb_mle.park_context import ContextSpec, apply_context  # noqa: E402
from betting_ml.scripts.milb_mle.player_structure import (  # noqa: E402
    TRAJ_PRESENT,
    PlayerSpec,
    apply_player_structure,
    bucket_col_for,
    extra_cols_for,
    player_coverage,
    player_structure_census,
    weight_column_for,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES, SideConfig, _paired_p, bh_fdr  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import propensity_for_fold  # noqa: E402
from betting_ml.scripts.milb_mle.run_e7_15_h1 import SHIPPED_CONTEXT  # noqa: E402
from betting_ml.scripts.milb_mle.survivorship import propensity_strata  # noqa: E402

log = logging.getLogger("e7_15.h3")

_KEYS = ["player_id", "level"]
_ART = (_PROJECT_ROOT
        / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

# The trajectory arms translate a player's levels onto one scale with H1's ladder. `direct` is H1's
# best-performing formulation (7 of 9 metrics) and avoids the compounding attenuation H1 measured in the
# chain (composed Single-A→AAA slope 0.182 vs 0.463 one-step). H1's null was about the ladder as a
# FEATURE ADJUSTMENT; using it to make a within-player DIFFERENCE comparable is a different use, which is
# why `T2_traj_raw` re-tests the ladder's contribution here rather than inheriting H1's answer.
_LADDER_SPEC = LadderSpec(mode="direct", weighted=True)


@dataclass(frozen=True)
class H3Arm:
    label: str
    spec: PlayerSpec
    kind: str            # foil | player | anchor
    note: str
    projector: str = "pool"      # pool | degenerate

    @property
    def selectable(self) -> bool:
        return self.kind == "player"


ARMS: tuple[H3Arm, ...] = (
    H3Arm("L0_foil", PlayerSpec(), "foil",
          "⭐ THE DIRECT-LEARNED FOIL — the shipped E7.12-slice-1 configuration; each row an independent "
          "observation, the arm's own shipped weight_col retained"),
    H3Arm("P1_dedup", PlayerSpec(weight_mode="dedup"), "player",
          "⭐ FULL DE-PSEUDO-REPLICATION — the observation weight is divided by the player's row count so "
          "every PLAYER carries equal total weight. Multiplies the foil's own weight rather than "
          "replacing it, so a pitcher arm does not silently drop its shipped `w:mlb_pa`."),
    H3Arm("P2_dedup_sqrt", PlayerSpec(weight_mode="dedup_sqrt"), "player",
          "MATCHED PARTNER to P1 — the classic half-measure. '1/n over-corrects' is a separate hypothesis "
          "from '1/n is right', and a field carrying only one of them cannot tell them apart."),
    H3Arm("P3_player_re", PlayerSpec(player_re=True), "player",
          "⭐ THE TEXTBOOK FIX — a penalized per-player intercept. PRE-REGISTERED TO LOSE: with a label "
          "constant within a player it absorbs the between-player variation and leaves the fixed effects "
          "identified by within-player contrasts alone. Run as a DECOMPOSITION, not a hopeful."),
    H3Arm("P4_re_dedup", PlayerSpec(weight_mode="dedup", player_re=True), "player",
          "P3 + P1 — do the two corrections compose, or is one redundant given the other?"),
    H3Arm("T1_traj_ladder", PlayerSpec(trajectory="ladder"), "player",
          "⭐ GENUINELY NEW INFORMATION — the ladder-adjusted rate change from the player's previous "
          "level, as a fixed regressor (+ an impute flag). NESTS THE FOIL at coefficient 0."),
    H3Arm("T2_traj_raw", PlayerSpec(trajectory="raw"), "player",
          "MATCHED FOIL FOR THE LADDER'S CONTRIBUTION — the same delta computed on RAW rates, which "
          "confounds 'the player improved' with 'the level got harder'. If it ties T1, the ladder adds "
          "nothing here either."),
    H3Arm("T3_tenure", PlayerSpec(tenure=True), "player",
          "years-at-level + levels-logged — repeating a level is a scouting-legible negative signal the "
          "aggregated box line erases (two identical Double-A lines, one taking three seasons)."),
    # ── anchors ──
    H3Arm("A_weight_identity", PlayerSpec(weight_mode="identity"), "anchor",
          "BYTE NO-OP — a constant weight column. Its MAE gap to the foil must be EXACTLY 0; anything "
          "else means the harness changed something it did not declare."),
    H3Arm("A_re_shuffled", PlayerSpec(player_re=True, shuffle_players=True), "anchor",
          "⭐ THE SHARPEST TEST IN THE SLICE — the row→player assignment permuted with the group-size "
          "multiset PRESERVED EXACTLY, so the block has identical width and shrinkage geometry and the "
          "only difference is whether the grouping is the truth. If a random grouping does as well, the "
          "win is extra regularization, not 'players'."),
    H3Arm("A_traj_shuffled", PlayerSpec(trajectory="shuffled"), "anchor",
          "the trajectory delta permuted across players within a level — catches 'any dispersed extra "
          "regressor helps' rather than the ordering carrying information."),
    H3Arm("A_degenerate_mean", PlayerSpec(), "anchor",
          "DEGENERATE CEILING (NF-D11/NF-D14) — predict the population mean of the target.",
          "degenerate"),
)

_BY_LABEL = {a.label: a for a in ARMS}

H3_ANCHORS: tuple[Anchor, ...] = (
    Anchor("A_degenerate_mean", "block", "the DEGENERATE CEILING — predict the population mean",
           "A metric a 'predict nothing' arm wins cannot select a projection (NF-D11); the selection "
           "metric is inverted for this cohort.",
           must_move=False),   # a degenerate PROJECTOR transforms nothing — legitimately moves 0%
    Anchor("A_weight_identity", "noop", "the BYTE NO-OP — a constant observation weight",
           "The harness changed something it did not declare; no arm's margin can be trusted."),
    Anchor("A_re_shuffled", "refute", "the SHUFFLED player grouping — same block width, same group-size "
           "multiset, wrong grouping",
           "Whatever a player random intercept buys is extra regularization at that block width, not "
           "anything to do with players — so it would not transfer to a differently-shaped cohort.",
           defender="P3_player_re"),
    Anchor("A_traj_shuffled", "refute", "the SHUFFLED trajectory delta — permuted within level",
           "The trajectory's apparent edge is 'any dispersed extra regressor helps', not the direction a "
           "player was moving.",
           defender="T1_traj_ladder"),
)


@dataclass
class H3Result:
    metric: str
    prior_scale: float
    shipped_spec: ContextSpec
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
    census: dict
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


def _projector(arm: H3Arm, prior_scale: float, base_weight_col: str | None):
    """Build the arm's projector.

    ⭐ NO SUBCLASS. The random intercept rides the slice-5 `bucket_col`/`bucket_intercept` machinery,
    which `clone_projector` already carries field-by-field. A `PartialPoolProjector` subclass would be
    silently downgraded to a plain one on every expanding-window refit (the documented E7.12-S5 landmine)
    and the arm would score AS THE FOIL under its own name — the H2 inert-arm class, one layer out.
    """
    if arm.projector == "degenerate":
        return ArchetypePriorRefProjector()
    bucket = bucket_col_for(arm.spec)
    return PartialPoolProjector(
        prior_scale=prior_scale,
        weight_col=weight_column_for(arm.spec, base_weight_col),
        extra_cols=extra_cols_for(arm.spec),
        bucket_col=bucket, bucket_intercept=bool(bucket), bucket_slope=False,
    )


def _ladder_for_fold(pairs: pd.DataFrame, metric: str, holdout_players: frozenset[str]):
    """Fit H1's ladder LEAVING THE HELD-OUT COHORT'S PLAYERS OUT (readiness lock 4).

    Returns None if the rungs cannot be fitted, in which case the trajectory arms fall back to raw
    deltas — a documented degradation, reported in `notes`, never a silent substitution.
    """
    try:
        trans = build_transitions(pairs, metric)
        if trans.empty:
            return None
        return fit_ladder(trans, _LADDER_SPEC, metric, exclude_players=holdout_players)
    except Exception:  # noqa: BLE001
        return None


def run_h3(pairs: pd.DataFrame, park: pd.DataFrame | None, metric: str, side: SideConfig,
           arms: tuple[H3Arm, ...] = ARMS, *, propensity_cache: dict | None = None,
           max_folds: int | None = None) -> H3Result:
    """Score every arm under the E7.3 fold structure, learner held fixed at the shipped configuration."""
    shipped = SHIPPED_CONTEXT[side.player_type].get(metric, ContextSpec())
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)

    # the park/run-env-adjusted rate the shipped model reads — H3 changes the FIT, not the feature, so
    # every arm sits on top of the identical shipped adjustment
    adjusted = apply_context(pairs, park, shipped, metric, tuple(_KEYS))
    base = build_target(adjusted, cfg)
    base_mask = base["has_target"].to_numpy(bool)
    labelled = base[base_mask]
    cohorts = sorted(int(y) for y in labelled["debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"[{metric}] need ≥2 evaluable debut cohorts; got {fold_cohorts}")
    if max_folds:
        # SMOKE ONLY — a truncated fold list is not a scoreable run (it changes the deflation field and
        # the "unit that grows" arithmetic). Kept so the code path can be proven cheaply in-session.
        fold_cohorts = fold_cohorts[-int(max_folds):]

    census = player_structure_census(adjusted)
    notes: list[str] = []
    ladder_fallback_folds: list[int] = []

    mae = pd.DataFrame(index=fold_cohorts, columns=[a.label for a in arms], dtype=float)
    coverage: dict = {}
    err_rows: list[pd.DataFrame] = []
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

        # 🔒 leave-the-held-out-players-out: the ladder that translates a player's levels must not have
        # been fitted using that player's own transitions (H1's posture, reused not re-argued)
        holdout = frozenset(adjusted.loc[adjusted["debut_cohort"] == year, "player_id"].astype(str))
        ladder = _ladder_for_fold(adjusted, metric, holdout)
        if ladder is None:
            notes.append(f"fold {year}: ladder unavailable — trajectory arms degrade to RAW deltas")
        elif ladder.fallbacks:
            # ⭐ A THIN RUNG FALLS BACK TO IDENTITY, WHICH MAKES `T1_traj_ladder` BYTE-IDENTICAL TO
            # `T2_traj_raw` — the matched foil then compares an arm against itself and its tie is a pass
            # on nothing (the H2 inert-anchor shape, third costume). Recorded per fold rather than
            # inferred from a near-zero margin.
            ladder_fallback_folds.append(year)
            notes.append(f"fold {year}: ladder rungs fell back to identity ({len(ladder.fallbacks)}) — "
                         f"the T1-vs-T2 ladder comparison is WEAKENED for this fold")

        for arm in arms:
            adj = apply_player_structure(adjusted, arm.spec, metric,
                                         base_weight_col=shipped.weight_col, ladder=ladder,
                                         fitted_mask=base_mask)
            f = build_target(adj, cfg)
            if not np.array_equal(f["has_target"].to_numpy(bool), base_mask):
                raise AssertionError(
                    f"[{metric}/{arm.label}] the player-structure arm changed the LABELLED POPULATION — "
                    f"arms would be scored on different players, which is not an ablation.")
            # ⚠️ coverage over the FITTED population (labelled rows), not the whole pairs table — the
            # pairs table is ~5× bigger because it carries the un-promoted prospects, and a fit-side
            # mechanism never touches them. Measuring over everything understated every arm toward the
            # inert threshold (81.2% vs the true 94.2% for the random intercept).
            coverage.setdefault(arm.label, player_coverage(adj, arm.spec, shipped.weight_col,
                                                           fitted_mask=base_mask))

            f = f[f["has_target"]]
            train, test = f[f["debut_cohort"] < year], f[f["debut_cohort"] == year]
            if train.empty or test.empty:
                continue
            try:
                mdl = _projector(arm, scale, shipped.weight_col).fit(train)
                yhat, _ = mdl.predict(test)
                err = np.abs(test["target"].to_numpy(float) - yhat)
                mae.loc[year, arm.label] = float(np.mean(err))
                moved = (pd.to_numeric(test.get(TRAJ_PRESENT), errors="coerce").fillna(1.0) > 0
                         if arm.spec.trajectory else pd.Series(True, index=test.index))
                err_rows.append(pd.DataFrame({
                    "fold": year, "arm": arm.label, "player_id": test["player_id"].to_numpy(),
                    "level": test["level"].to_numpy(), "abs_err": err,
                    "moved": np.asarray(moved, dtype=bool)}))
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
            "n_player_blocks": cov.get("n_player_blocks"),
            "weight_ratio_p05": cov.get("weight_ratio_p05"),
            "weight_ratio_p95": cov.get("weight_ratio_p95"),
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
        mae, H3_ANCHORS, best, "L0_foil", coverage=coverage)

    # ⭐ A MATCHED FOIL REFUTES ITS OWN MECHANISM, NOT THE WHOLE FIELD (NF-D16 g‴, one instrument over).
    # `A_re_shuffled` foils the random intercept and `A_traj_shuffled` foils the trajectory; neither says
    # anything about the other, nor about the reweighting arms. Letting either veto the METRIC would
    # reject a legitimately-better arm for an unrelated mechanism's sin — exactly the failure a single
    # field-wide peeking ceiling produced in NF-D16. So a scoped refutation disqualifies ONLY its
    # defender, loudly, and selection re-runs over what survives.
    refuted = dict(anchors.get("refuted_arms") or {})
    if refuted:
        for arm_label, why in refuted.items():
            reasons.append(f"⛔ MECHANISM REFUTED (scoped to `{arm_label}`) — {why} That arm is "
                           f"disqualified from selection; other mechanisms on this metric are untouched.")
        sel = sel[~sel["arm"].isin(refuted)]
        best = str(sel.iloc[0]["arm"]) if not sel.empty else "L0_foil"
    anchors["oracle_floor_ok"] = oracle_ok
    anchors["best_arm_mae"] = float(leaderboard.loc[leaderboard["arm"] == best, "oos_mae"].iloc[0]) \
        if best in set(leaderboard["arm"]) else np.nan
    stratified = stratified_lift(rows_df)
    stratified_moved = stratified_lift(rows_df, moved_only=True)
    low, low_all = low_tercile_read(stratified, stratified_moved, best)
    anchors["low_propensity_tercile_lift_pct"] = low
    anchors["low_propensity_tercile_lift_pct_all_rows"] = low_all

    # ⭐ THE DECOMPOSITION READING — recorded whatever the verdict, because P3/P4 were pre-registered to
    # lose and their MARGIN is the measurement of where the incumbent's skill lives.
    def _lift(label: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == label, "pct_lift_vs_foil"]
        return float(r.iloc[0]) if len(r) else float("nan")

    anchors["between_vs_within_player_decomposition_pct"] = _lift("P3_player_re")
    anchors["re_shuffled_minus_re_true_pct"] = _lift("A_re_shuffled") - _lift("P3_player_re")
    anchors["ladder_contribution_to_trajectory_pct"] = _lift("T1_traj_ladder") - _lift("T2_traj_raw")
    anchors["ladder_identity_fallback_folds"] = ladder_fallback_folds
    if ladder_fallback_folds and len(ladder_fallback_folds) >= len(fold_cohorts):
        reasons.append(
            f"⚠️ THE LADDER FELL BACK TO IDENTITY IN EVERY FOLD ({ladder_fallback_folds}) — "
            f"`T1_traj_ladder` is byte-identical to `T2_traj_raw`, so their comparison is VACUOUS and "
            f"the ladder's contribution here is UNMEASURED, not zero (NF1.9: a mechanism that cannot "
            f"act is a finding, not an omission).")

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
                f"ℹ️ INACTIVE arms (the mechanism moved <{MIN_PCT_ROWS_MOVED}% of rows in its OWN units, "
                f"so they are the foil in disguise and cannot be selected): {', '.join(inactive)}. A "
                f"mechanism that cannot act is a finding, not an omission (NF1.9).")
        if sel.empty:
            reasons.append("🟡 no ELIGIBLE arm remains. The shipped configuration stands for this metric.")
        else:
            cand = sel.iloc[0]
            passed, reason = numeric_gate(cand, foil_mae, defl, dsr, "player-level structure")
            reasons.append(reason)
            if passed:
                verdict, winner = "ADD", str(cand["arm"])
                if metric in side.board_metrics and np.isfinite(low) and low < 0:
                    verdict, winner = "DROP", "L0_foil"
                    reasons.append(
                        f"⛔ LOW-TERCILE DOWNGRADE — `{cand['arm']}` improves the OVERALL held-out MAE "
                        f"but is {low:+.3f}% in the LOWEST promotion-propensity tercile. A board metric "
                        f"that helps the players we do NOT serve is not a board improvement (H5).")

    return H3Result(
        metric=metric, prior_scale=scale, shipped_spec=shipped, leaderboard=leaderboard,
        mae_by_fold=mae, fold_cohorts=fold_cohorts, census=census, coverage=coverage,
        deflation=defl, dsr=dsr, anchors=anchors, stratified=stratified,
        stratified_moved=stratified_moved, composition=propensity_composition(rows_df),
        verdict=verdict, winner=winner, reasons=reasons, oracle_floor_ok=oracle_ok)


def write_report(results: dict[str, H3Result], fdr: dict, nulls: dict, path: Path,
                 side: SideConfig, census: dict) -> None:
    def md(df: pd.DataFrame) -> str:
        return df.to_markdown(index=False) if df is not None and not df.empty else "_(empty)_"

    L: list[str] = []
    A = L.append
    A(f"# E7.15 H3 — player-level structure ({side.player_type} side)\n")
    A(f"_generated {datetime.now(timezone.utc).isoformat()} · foil = the SHIPPED E7.12-slice-1 "
      f"configuration · `best_alpha = 0`_\n")
    A("> Pre-registration (written before any arm was scored): `e7_15_h3_preregistration.md`.\n")
    A("> ⚠️ **A projection, not an edge claim.**\n")

    A("## 1. The premise, measured before any score\n")
    A("The training matrix is one row per (player, level) and **every one of a player's rows carries the "
      "same MLB label**, so the fit treats a four-level player as four independent observations.\n")
    A(md(pd.DataFrame([census])))
    A("\n⚠️ **This is an EFFICIENCY question, not a leakage bug.** Folds are MLB debut cohorts and "
      "`debut_cohort` is a per-PLAYER join, so all of a player's rows share one fold and no player "
      "straddles the train/test boundary. What is at stake is only whose line the coefficients are "
      "fitted to.\n")

    A("\n## 2. Verdicts\n")
    A(md(pd.DataFrame([{
        "metric": m, "verdict": r.verdict, "winner": r.winner,
        "best_arm": (r.leaderboard[r.leaderboard["selectable"] & r.leaderboard["active"]]
                     .iloc[0]["arm"] if not r.leaderboard[r.leaderboard["selectable"]
                                                          & r.leaderboard["active"]].empty else "—"),
        "pct_lift_vs_foil": round(float(r.leaderboard[r.leaderboard["selectable"]
                                                      & r.leaderboard["active"]].iloc[0]
                                        ["pct_lift_vs_foil"]), 3)
        if not r.leaderboard[r.leaderboard["selectable"] & r.leaderboard["active"]].empty else np.nan,
        "BH-FDR": fdr.get(m),
        "PBO(eligible)": r.deflation.get("pbo"), "DSR(eligible)": r.dsr.get("dsr"),
    } for m, r in results.items()])))

    A("\n## 3. ⭐ The decomposition — where does the incumbent's skill live?\n")
    A("`P3_player_re` was **pre-registered to lose**: with a label constant within a player, a player "
      "intercept absorbs the between-player variation and leaves the fixed effects identified by "
      "within-player contrasts alone, which is the variation H1 already found null. Its margin is "
      "therefore a MEASUREMENT, not a miss.\n")
    A(md(pd.DataFrame([{
        "metric": m,
        "P3_lift_vs_foil_pct": round(r.anchors.get("between_vs_within_player_decomposition_pct", np.nan), 3),
        "shuffled_minus_true_pct": round(r.anchors.get("re_shuffled_minus_re_true_pct", np.nan), 3),
        "ladder_contribution_to_traj_pct": round(
            r.anchors.get("ladder_contribution_to_trajectory_pct", np.nan), 3),
    } for m, r in results.items()])))
    A("\n- **`shuffled_minus_true`** > 0 means the SHUFFLED grouping scored better than the true one — "
      "i.e. whatever a player block buys is block-width regularization, not 'players'.\n")
    A("- **`ladder_contribution_to_traj`** > 0 means H1's ladder made the within-player difference more "
      "informative than the raw difference. H1's null was about the ladder as a FEATURE ADJUSTMENT; this "
      "is a different use of it and is re-tested here rather than inherited.\n")

    for m, r in results.items():
        A(f"\n## {m}\n")
        A(f"_shipped foil: `{r.shipped_spec.label}` · prior_scale {r.prior_scale} · "
          f"{len(r.fold_cohorts)} folds {r.fold_cohorts}_\n")
        A(md(r.leaderboard.drop(columns=["note"], errors="ignore")))
        A("\n**Anchors**\n")
        for a in H3_ANCHORS:
            d = r.anchors.get(a.label)
            if isinstance(d, dict):
                A(f"- `{a.label}` ({a.what}): {d}")
        A(f"\n**Coverage (the mechanism's OWN units)**: {json.dumps(r.coverage, default=float)}\n")
        A("\n**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one "
          "richest in Triple-A rows, so its level mix is published beside every stratified read):\n")
        A(md(r.composition))
        A("\n**Stratified lift, MOVED ROWS ONLY** (H5):\n")
        A(md(r.stratified_moved))
        A("\n**Reasons**\n")
        for x in r.reasons:
            A(f"- {x}")

    A("\n## Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)\n")
    A(f"**Binding constraint: {nulls['binding_constraint']}**\n")
    A(md(pd.DataFrame(nulls.get("per_metric", []))))

    A("\n## Reading notes\n")
    A("- **`pct_rows_moved` is measured in EACH MECHANISM'S OWN UNITS.** H1 and H2 rewrote "
      "`minor_<metric>`, so 'did the arm act' was a feature diff. H3's weighting and random-effect arms "
      "move no feature value at all — a feature-diff activity check would report 0% for every one of "
      "them and the `must_move` guard would block the slice for the wrong reason. **The H2 inert-anchor "
      "lesson generalises: an inert-anchor guard is only as good as its activity metric.**\n")
    A("- **No new projector class.** The random intercept rides the slice-5 `bucket_col` machinery, "
      "which `clone_projector` already carries field-by-field. A subclass would be silently downgraded "
      "on every refit and would score AS THE FOIL under its own name (the E7.12-S5 landmine).\n")
    A("- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.\n")
    path.write_text("\n".join(L) + "\n")
    log.info("wrote %s", path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.15 H3 — the player-level-structure bake-off")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter")
    p.add_argument("--metrics", nargs="+", default=None)
    p.add_argument("--arms", nargs="+", default=None)
    p.add_argument("--census-only", action="store_true",
                   help="print the pseudo-replication census and exit (readiness lock 2, seconds)")
    p.add_argument("--max-folds", type=int, default=None,
                   help="SMOKE ONLY — score just the last N folds to prove the code path cheaply. Not a "
                        "scoreable run: it changes the deflation field and the extra-cohorts arithmetic.")
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

    census = player_structure_census(pairs)
    log.info("PSEUDO-REPLICATION CENSUS (%s): %s", side.player_type, json.dumps(census))
    if args.census_only:
        return 0

    metrics = args.metrics or list(side.metrics)
    arms = ARMS if not args.arms else tuple(_BY_LABEL[a] for a in args.arms)
    if "L0_foil" not in {a.label for a in arms}:
        arms = (_BY_LABEL["L0_foil"],) + arms

    results: dict[str, H3Result] = {}
    cache: dict = {}
    for m in metrics:
        log.info("=== E7.15 H3 [%s]: %s ===", side.player_type, m)
        results[m] = run_h3(pairs, park, m, side, arms, propensity_cache=cache,
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
    (out_dir / f"e7_15_h3{suffix}_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_type": side.player_type,
        "foil": "the SHIPPED E7.12-slice-1 configuration per metric (learner + weight_col held fixed)",
        "pseudo_replication_census": census,
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
        write_report(results, fdr, nulls,
                     _REPORT_DIR / f"e7_15_h3_player_structure{suffix}.md", side, census)
    log.info("E7.15 H3 VERDICTS (%s): %s", side.player_type, {m: r.verdict for m, r in results.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
