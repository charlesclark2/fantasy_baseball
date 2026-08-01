"""E7.12 SLICE 4 — do 20-80 SCOUTING GRADES improve the MiLB→MLB translation?

Run (LAPTOP, ~1-2 min per side; build the context first — see `grade_context.py`):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice4 \
        --player-type batter
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice4 \
        --player-type pitcher

WHY THIS ONE IS WORTH RUNNING EVEN THOUGH THE LAST THREE MECHANISMS WERE ~NULL
---------------------------------------------------------------------------------------------------
Park, run-environment, reliability and label weights are all re-expressions of the same minor-league box
score. A 20-80 grade is the only input we carry that is **not derived from the line** — a human watched
the player. Every previous slice has been asking the box score to explain itself.

PRE-REGISTERED, AND THE ASYMMETRY IS THE DESIGN
---------------------------------------------------------------------------------------------------
E7.8 MEASURED that FanGraphs FV **COMPLEMENTS** our pitcher line (+0.031 on top of our +0.014, gates
cleared) and **SUBSTITUTES** for our hitter line (+0.015 on top of our +0.047, no stage cleared).
⇒ **grades should ADD on PITCHERS and be ~NULL on HITTERS.** A UNIFORM lift on both sides is the
shrinkage confound in a scouting costume — a grade column is just another dispersed number to shift by —
and is the same shape slice 1 caught with the park placebo. **A hitter null is the PREDICTED result and
must not be read as a failure.**

THREE FOILS, BECAUSE "THE GRADE HELPED" HAS THREE CHEAPER EXPLANATIONS
---------------------------------------------------------------------------------------------------
  • **`A_flag_only`** — the "was this player RANKED at all" indicator with NO grade value. ⭐ The most
    important arm in the slice. Grade coverage rises monotonically with S2's promotion propensity
    (batters 38.0/58.1/68.1%, pitchers 21.7/40.3/53.7% across terciles), so *being graded* is itself a
    selection signal. If `A_flag_only` matches `G1_grade`, the slice has credited SELECTION to SCOUTING.
  • **`A_grade_placebo`** — grades permuted within board-season. Must lose (the slice-1 park placebo).
  • **`G3_fv_only`** — the board's overall FV instead of the mapped tool grade. The matched foil for
    "does the SPECIFIC tool add over the scout's overall verdict?" (NF-D10: to attribute a mechanism,
    register it beside the identical bundle minus that mechanism, and read the PAIRED delta.)

🚨 THE FOLD SET IS RESTRICTED AND THIS IS NOT OPTIONAL — see `grade_context.ACTIVE_FOLD_MIN`. The board
starts 2018-07-01, so 4 of the 11 E7.3 folds carry ZERO graded training rows and the grade arm is
byte-identical to the baseline in them. Counting a structurally-impossible fold as a loss caps the
achievable fold-win-rate at 7/11 = 0.636 against a 0.60 gate. The inert folds are REPORTED, not hidden.
⚠️ Consequence to state in any comparison: **S4's fold counts are NOT comparable to slice 1/2's eleven.**
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.grade_context import (
    ACTIVE_FOLD_MIN,
    FLAG_COL,
    FV_COL,
    GRADE_FOR_METRIC,
    SIDE_GRADES,
)
from betting_ml.scripts.milb_mle.milb_mle import PartialPoolProjector, build_target
from betting_ml.scripts.milb_mle.park_context import apply_context
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import (
    SIDES,
    SideConfig,
    _paired_p,
    bh_fdr,
    deflation_report,
    paired_anchor,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import shipped_spec

log = logging.getLogger("e7_12_slice4")

_KEYS = ["player_id", "level"]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ABLATION = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

_Z = "_g_"          # prefix for the standardized grade columns handed to `extra_cols`


@dataclass(frozen=True)
class GradeArm:
    label: str
    cols: tuple[str, ...]      # raw context columns to join into the UNPENALIZED fixed block
    kind: str                  # "ladder" | "anchor"
    note: str
    permute: bool = False

    @property
    def selectable(self) -> bool:
        return self.kind != "anchor"


def ladder_for(side: SideConfig, metric: str) -> tuple[GradeArm, ...]:
    """The arms for ONE metric. The mapped grade differs per component, so the ladder does too."""
    mapped = GRADE_FOR_METRIC[side.player_type].get(metric)
    arms = [GradeArm("G0_shipped", (), "ladder",
                     "the SHIPPED slice-1 configuration for this metric — the real incumbent")]
    if mapped:
        arms += [
            GradeArm("G1_grade", (mapped, FLAG_COL), "ladder",
                     f"⭐ the mapped tool grade ({mapped}) + a 'was graded' indicator. The indicator is "
                     f"not optional: without it an ungraded player is indistinguishable from an "
                     f"average-graded one, and the coefficient absorbs the difference"),
            GradeArm("G2_grade_fv", (mapped, FV_COL, FLAG_COL), "ladder",
                     "the mapped tool grade PLUS the scout's overall FV verdict"),
            GradeArm("G3_fv_only", (FV_COL, FLAG_COL), "ladder",
                     "FV alone — the MATCHED FOIL for 'does the specific tool add over the overall "
                     "verdict?' (NF-D10: read the paired delta, not the rank)"),
            GradeArm("A_grade_placebo", (mapped, FLAG_COL), "anchor",
                     "DEGENERATE FOIL — the SAME grades permuted within board-season. Must LOSE; catches "
                     "'any dispersed number shifts MAE'", permute=True),
        ]
    arms += [
        GradeArm("G4_all_grades", tuple(SIDE_GRADES[side.player_type]) + (FLAG_COL,), "ladder",
                 "every grade the side carries — the kitchen sink, counted toward deflation"),
        GradeArm("A_flag_only", (FLAG_COL,), "anchor",
                 "🚨 THE LOAD-BEARING FOIL — 'was this player RANKED' with NO grade value. Grade coverage "
                 "rises monotonically with promotion propensity, so being graded is a SELECTION signal. "
                 "If this matches the grade arm, the slice has credited selection to scouting."),
    ]
    return tuple(arms)


@dataclass
class S4Result:
    metric: str
    prior_scale: float
    shipped_rung: str
    mapped_grade: str | None
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame
    fold_cohorts: list[int]
    inert_folds: list[int]
    coverage: dict
    deflation: dict
    anchors: dict
    graded_subset: pd.DataFrame
    verdict: str
    winner: str
    reasons: list[str] = field(default_factory=list)


def _prepare(frame: pd.DataFrame, arm: GradeArm, rng: np.random.Generator) -> tuple[pd.DataFrame, tuple]:
    """Attach this arm's columns under a `_g_` prefix and return the `extra_cols` tuple.

    🪤 The columns are COPIED under a prefix rather than used in place because `A_grade_placebo` mutates
    them; writing a permuted grade back over the shared frame would silently poison every later arm in
    the same fold, and the leaderboard would look completely normal.
    """
    out = frame.copy()
    cols = []
    for c in arm.cols:
        z = f"{_Z}{c}"
        v = pd.to_numeric(out.get(c), errors="coerce")
        if arm.permute and c != FLAG_COL:
            # permute WITHIN board-season so the placebo keeps the season's grade distribution and
            # destroys only the player↔grade pairing — the slice-1 park-placebo shape
            v = (v.groupby(out["board_season"].fillna(-1))
                  .transform(lambda s: rng.permutation(s.to_numpy())))
        out[z] = v
        cols.append(z)
    return out, tuple(cols)


def run_s4_ladder(pairs: pd.DataFrame, park_ctx: pd.DataFrame | None, grade_ctx: pd.DataFrame,
                  metric: str, side: SideConfig, seed: int = 11) -> S4Result:
    base_spec = shipped_spec(side, metric)
    scale = side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)
    rng = np.random.default_rng(seed)
    arms = ladder_for(side, metric)
    mapped = GRADE_FOR_METRIC[side.player_type].get(metric)

    adj = apply_context(pairs, park_ctx, base_spec, metric, tuple(_KEYS))
    lab = build_target(adj, cfg)
    lab = lab[lab["has_target"]].merge(grade_ctx, on=_KEYS, how="left").reset_index(drop=True)

    cohorts = sorted(int(y) for y in lab["debut_cohort"].dropna().unique())
    evaluable = [y for y in cohorts if any(c < y for c in cohorts)]
    fold_cohorts = [y for y in evaluable if y >= ACTIVE_FOLD_MIN]
    inert = [y for y in evaluable if y < ACTIVE_FOLD_MIN]
    if len(fold_cohorts) < 2:
        raise ValueError(f"need >=2 ACTIVE folds; got {fold_cohorts}")

    labels = [a.label for a in arms]
    mae = pd.DataFrame(index=fold_cohorts, columns=labels, dtype=float)
    rows: list[pd.DataFrame] = []
    notes: list[str] = []

    for year in fold_cohorts:
        for arm in arms:
            frame, extra = _prepare(lab, arm, rng)
            train = frame[frame["debut_cohort"] < year]
            test = frame[frame["debut_cohort"] == year]
            if train.empty or test.empty:
                continue
            try:
                mdl = PartialPoolProjector(prior_scale=scale, weight_col=base_spec.weight_col,
                                           extra_cols=extra).fit(train)
                yhat, _ = mdl.predict(test)
                err = np.abs(test["target"].to_numpy(float) - yhat)
                mae.loc[year, arm.label] = float(np.mean(err))
                rows.append(pd.DataFrame({
                    "fold": year, "arm": arm.label, "abs_err": err,
                    "player_id": test["player_id"].to_numpy(), "level": test["level"].to_numpy(),
                    "graded": test[FLAG_COL].fillna(0).to_numpy() > 0}))
            except Exception as e:  # noqa: BLE001 — a degenerate fold must not kill the sweep
                notes.append(f"fold {year} arm {arm.label}: {type(e).__name__}: {e}")

    if not rows:
        raise RuntimeError(f"[{metric}] no fold scored — {notes}")
    per_row = pd.concat(rows, ignore_index=True)

    # ⭐ THE SAME FOLD TEST RESTRICTED TO THE GRADED ROWS — the instrument that separates "grades do not
    # work" from "grades work but 36-45% ungraded rows dilute the fold statistic below a coarse gate".
    # With only 7 active folds the gate has NO RESOLUTION between 4/7 = 0.571 and 5/7 = 0.714, so a real
    # but modest effect can fail it on one fold. Reported for every arm; it is a POWER diagnostic and is
    # NOT part of the gate — the pre-registered gate stays the overall fold-win rate.
    gm = _graded_fold_mae(per_row, fold_cohorts, labels)

    base = mae["G0_shipped"]
    gbase = gm["G0_shipped"] if "G0_shipped" in gm else None
    board = []
    for arm in arms:
        col = mae[arm.label]
        d = (base - col).to_numpy(float)
        dfin = d[np.isfinite(d)]
        gwr = np.nan
        if gbase is not None and arm.label in gm:
            gd = (gbase - gm[arm.label]).to_numpy(float)
            gd = gd[np.isfinite(gd)]
            gwr = float(np.mean(gd > 0)) if len(gd) else np.nan
        board.append({
            "arm": arm.label, "kind": arm.kind, "selectable": arm.selectable,
            "oos_mae": float(col.mean(skipna=True)),
            "pct_lift_vs_G0": (100.0 * float(np.mean(dfin)) / float(base.mean(skipna=True))
                               if len(dfin) and base.mean(skipna=True) else np.nan),
            "fold_win_rate": float(np.mean(dfin > 0)) if len(dfin) else np.nan,
            "graded_fold_win_rate": gwr,
            "p_one_sided": _paired_p(d),
            "note": arm.note,
        })
    leaderboard = pd.DataFrame(board).sort_values("oos_mae").reset_index(drop=True)

    eligible = [a.label for a in arms if a.selectable]
    defl = deflation_report(mae, eligible)
    defl["whole_field"] = deflation_report(mae)

    graded = graded_subset_lift(per_row, "G0_shipped")
    anchors = s4_anchors(mae, leaderboard, graded)
    cov = {
        "active_folds": fold_cohorts, "inert_folds": inert,
        "pct_test_rows_graded": round(100.0 * float(
            per_row[per_row["arm"] == "G0_shipped"]["graded"].mean()), 2),
    }
    verdict, winner, reasons = s4_verdict(leaderboard, anchors, mapped, notes)
    return S4Result(metric=metric, prior_scale=scale, shipped_rung=base_spec.label,
                    mapped_grade=mapped, leaderboard=leaderboard, mae_by_fold=mae,
                    fold_cohorts=fold_cohorts, inert_folds=inert, coverage=cov, deflation=defl,
                    anchors=anchors, graded_subset=graded, verdict=verdict, winner=winner,
                    reasons=reasons)


def _graded_fold_mae(rows: pd.DataFrame, folds: list[int], labels: list[str]) -> pd.DataFrame:
    """folds × arms held-out MAE computed over the GRADED test rows only."""
    g = rows[rows["graded"]]
    if g.empty:
        return pd.DataFrame(index=folds, columns=labels, dtype=float)
    piv = g.groupby(["fold", "arm"])["abs_err"].mean().unstack("arm")
    return piv.reindex(index=folds, columns=labels)


def graded_subset_lift(rows: pd.DataFrame, reference: str) -> pd.DataFrame:
    """Held-out lift split by whether the test row HAS a grade — the mechanism read.

    ⭐ Pre-registered as a SECONDARY read, and legitimate as one because grade presence does not depend on
    which arm is being scored (the labelled population is identical across arms; only the subset boundary
    is fixed in advance). The OVERALL number is the shipping number and is diluted by the 23-38% of test
    rows that fall back to the incumbent; the GRADED number is what the mechanism can actually do.

    🪤 And it is a two-sided check, not a rescue: **a grade arm that moves the UNGRADED rows is broken.**
    An ungraded row's standardized grade is 0 by construction, so its prediction can only move through
    the shared intercept/coefficients — a large ungraded delta means the arm is re-fitting the whole
    model, not applying scouting information.
    """
    ref = (rows[rows["arm"] == reference]
           .set_index(["fold", "player_id", "level"])["abs_err"].rename("ref_err"))
    out = []
    for arm, d in rows.groupby("arm"):
        j = d.set_index(["fold", "player_id", "level"]).join(ref, how="inner")
        for is_graded, ds in j.groupby("graded"):
            base = float(ds["ref_err"].mean())
            out.append({"arm": arm, "graded": bool(is_graded), "n": int(len(ds)),
                        "mae": float(ds["abs_err"].mean()),
                        "pct_lift_vs_ref": (100.0 * float((ds["ref_err"] - ds["abs_err"]).mean()) / base
                                            if base else np.nan)})
    return pd.DataFrame(out)


def s4_anchors(mae: pd.DataFrame, leaderboard: pd.DataFrame, graded: pd.DataFrame) -> dict:
    def m_of(lbl: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == lbl, "oos_mae"]
        return float(r.iloc[0]) if len(r) else float("nan")

    out = {
        "grade_placebo_vs_grade": paired_anchor(mae, "A_grade_placebo", "G1_grade"),
        "flag_only_vs_grade": paired_anchor(mae, "A_flag_only", "G1_grade"),
        "grade_mae": m_of("G1_grade"), "placebo_mae": m_of("A_grade_placebo"),
        "flag_only_mae": m_of("A_flag_only"), "fv_only_mae": m_of("G3_fv_only"),
    }
    # ⭐ WHERE DID THE MOVEMENT LAND? A grade arm can only reach an UNGRADED row through the shared
    # intercept/coefficients (its standardized grade is 0 by construction), so some ungraded movement is
    # the normal cost of adding a regressor. But if the ungraded rows move as much as — or MORE than —
    # the graded ones, the arm is re-fitting the whole model rather than applying scouting information,
    # and calling the result "the tool grade helped" would be wrong whichever way the MAE went.
    if len(graded):
        gg = graded[graded["arm"] == "G1_grade"]
        on = gg[gg["graded"]]["pct_lift_vs_ref"]
        off = gg[~gg["graded"]]["pct_lift_vs_ref"]
        if len(on) and len(off):
            a, b = float(on.iloc[0]), float(off.iloc[0])
            out["graded_rows_lift_pct"] = round(a, 4)
            out["ungraded_rows_lift_pct"] = round(b, 4)
            out["movement_is_mostly_the_shared_refit"] = bool(abs(b) >= abs(a))
    return out


def s4_verdict(leaderboard: pd.DataFrame, anchors: dict, mapped: str | None,
               notes: list[str]) -> tuple[str, str, list[str]]:
    reasons = list(notes)
    if mapped is None:
        reasons.append("no scouting grade maps to this component — the tool-grade arms are UNSELECTABLE "
                       "no-ops here rather than a fabricated neutral (the slice-1p `xwoba_against` "
                       "precedent). Only the kitchen-sink and flag arms ran.")
    sel = leaderboard[leaderboard["selectable"] & (leaderboard["arm"] != "G0_shipped")]
    sel = sel[sel["fold_win_rate"] >= 0.60]
    if sel.empty:
        reasons.append("no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts")
        return "DROP", "G0_shipped", reasons

    win = sel.sort_values("oos_mae").iloc[0]
    label = str(win["arm"])
    if label.startswith("G1") or label.startswith("G2"):
        if anchors.get("grade_placebo_vs_grade", {}).get("violated"):
            reasons.append("⛔ the PERMUTED-grade placebo matched or beat the real grades — the movement "
                           "is dispersion, not scouting information")
            return "DROP", "G0_shipped", reasons
        if anchors.get("flag_only_vs_grade", {}).get("violated"):
            reasons.append("⛔ the 'was RANKED' indicator ALONE matched or beat the graded arm — this is "
                           "SELECTION, not scouting. Grade coverage rises monotonically with promotion "
                           "propensity, so a ranked-ness indicator carries real signal that has nothing "
                           "to do with the tool grade, and crediting it to scouting would be wrong.")
            return "DROP", "G0_shipped", reasons
    return "ADD", label, reasons


def write_report(results: dict[str, S4Result], fdr: dict, side: SideConfig, dest: Path,
                 coverage_csv: Path | None) -> None:
    L: list[str] = []
    A = L.append
    A(f"# E7.12 slice 4 — 20-80 scouting grades as component priors ({side.player_type}s)\n")
    A("> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.**\n")
    A("The 20-80 grade is the only input this program carries that is **not derived from the "
      "minor-league line** — every mechanism tried so far (park, run environment, reliability, label "
      "weights) has been a re-expression of the same box score.\n")
    A("\n## 🚨 Read this before the leaderboard — the fold set is RESTRICTED\n")
    A(f"`the_board` begins 2018-07-01 and the as-of guard admits only snapshots STRICTLY BEFORE a "
      f"player's debut season, so the earliest debut cohorts have **structurally zero** grade coverage "
      f"and their folds carry no graded training row at all. The grade arm is byte-identical to the "
      f"baseline in those folds, scoring `delta = 0`, which the `d > 0` fold test counts as a LOSS — "
      f"capping the achievable fold-win-rate at 7/11 = 0.636 against a 0.60 gate. **A perfect grade "
      f"signal would clear by one fold.** So the gate runs over ACTIVE folds only "
      f"(>= {ACTIVE_FOLD_MIN}); the inert folds are listed per metric, not hidden.\n")
    A("⚠️ **S4 fold counts are therefore NOT comparable to slice 1/2's eleven.**\n")
    A("\n### Pre-registered asymmetry (E7.8)\n")
    A("FV **complements** our pitcher line and **substitutes** for our hitter line ⇒ grades should ADD "
      "on PITCHERS and be ~NULL on HITTERS. **A hitter null is the PREDICTED result, not a failure.** A "
      "uniform lift on both sides would be the shrinkage confound in a scouting costume.\n")
    A("\n### ⚠️ A graded player is a SELECTED player — this slice interacts with S2\n")
    A("Grade coverage rises monotonically with S2's promotion propensity (batters 38.0 / 58.1 / 68.1%, "
      "pitchers 21.7 / 40.3 / 53.7% across the low/mid/high terciles), so **the tool grade is least "
      "available exactly where S2 showed the model most needs help.** `A_flag_only` — the 'was this "
      "player RANKED' indicator carrying no grade value — is the arm that keeps the slice from crediting "
      "selection to scouting, and it is a DISQUALIFIER, not a footnote.\n")
    if coverage_csv and coverage_csv.exists():
        A("\n### As-of grade coverage on the labelled population\n")
        A(pd.read_csv(coverage_csv).to_markdown(index=False))

    A("\n## Verdicts\n")
    A(pd.DataFrame([{
        "metric": m, "mapped_grade": r.mapped_grade or "— (no scouting analogue)",
        "shipped_baseline": r.shipped_rung, "verdict": r.verdict, "winner": r.winner,
        "active_folds": len(r.fold_cohorts), "inert_folds": len(r.inert_folds),
        "pct_test_graded": r.coverage["pct_test_rows_graded"],
        "BH-FDR@0.10": fdr.get(m),
    } for m, r in results.items()]).to_markdown(index=False))

    for m, r in results.items():
        A(f"\n---\n\n## `{m}` (grade = `{r.mapped_grade or 'none'}`, baseline = `{r.shipped_rung}`)\n")
        A(f"active folds {r.fold_cohorts} · **inert (excluded, mechanism cannot act): {r.inert_folds}** · "
          f"{r.coverage['pct_test_rows_graded']}% of held-out rows carry a grade\n")
        A(r.leaderboard.drop(columns=["note"]).round(6).to_markdown(index=False))
        A(f"\n⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the {r.coverage['pct_test_rows_graded']}"
          f"% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the "
          f"gate**. With {len(r.fold_cohorts)} active folds the gate has no resolution between 4/7 = "
          f"0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being "
          f"diluted by the ungraded fallback rather than failing on the mechanism. That distinction is "
          f"the difference between a clean null and an underpowered one, and only the first retires a "
          f"mechanism.\n")
        A("\n### Graded vs ungraded held-out rows\n")
        A("The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back "
          "to the incumbent; the graded number is what the mechanism can do. **An arm that moves the "
          "UNGRADED rows is re-fitting the whole model, not applying scouting information.**\n")
        if len(r.graded_subset):
            A(r.graded_subset.round(4).to_markdown(index=False))
        A("\n### Anchors\n")
        A("```\n" + json.dumps(r.anchors, indent=2, default=str) + "\n```")
        A("\n### Deflation\n")
        A("```\n" + json.dumps(r.deflation, indent=2, default=str) + "\n```")
        if r.reasons:
            A("\n### Notes\n")
            for x in r.reasons:
                A(f"- {x}")
    dest.write_text("\n".join(L))
    log.info("wrote %s", dest)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.12 slice 4 — tool grades as component priors")
    p.add_argument("--player-type", choices=sorted(SIDES), default="batter")
    p.add_argument("--metrics", nargs="*", default=None)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[a.player_type]
    suffix = side.reduced.artifact_suffix
    art = _ABLATION / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(art / side.pairs_name)

    gctx_path = _ABLATION / "e7_12_artifacts" / f"mle_grade_context{suffix}.parquet"
    if not gctx_path.exists():
        raise SystemExit(f"missing {gctx_path} — build it first:\n  AWS_DEFAULT_REGION=us-east-2 uv run "
                         f"python -m betting_ml.scripts.milb_mle.grade_context "
                         f"--player-type {side.player_type}")
    grade_ctx = pd.read_parquet(gctx_path)
    pctx_path = _ABLATION / "e7_12_artifacts" / f"mle_park_context{suffix}.parquet"
    park_ctx = pd.read_parquet(pctx_path) if pctx_path.exists() else None
    log.info("pairs %d · grade ctx %d (%d graded) · park ctx %s", len(pairs), len(grade_ctx),
             int(grade_ctx[FLAG_COL].sum()), len(park_ctx) if park_ctx is not None else "ABSENT")

    metrics = tuple(a.metrics) if a.metrics else side.metrics
    results: dict[str, S4Result] = {}
    for m in metrics:
        log.info("── %s ──", m)
        results[m] = run_s4_ladder(pairs, park_ctx, grade_ctx, m, side, seed=a.seed)
        log.info("[%s] verdict=%s winner=%s", m, results[m].verdict, results[m].winner)

    pvals = {m: float(r.leaderboard.loc[r.leaderboard["arm"] == r.winner, "p_one_sided"].iloc[0])
             for m, r in results.items()
             if r.verdict == "ADD" and r.winner in set(r.leaderboard["arm"])
             and np.isfinite(r.leaderboard.loc[r.leaderboard["arm"] == r.winner, "p_one_sided"].iloc[0])}
    fdr = bh_fdr(pvals)
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict, r.winner = "DROP", "G0_shipped"
            r.reasons.append("⛔ FDR-DOWNGRADED — did not survive Benjamini-Hochberg at alpha=0.10 "
                             "across the metrics tested in this run")

    dest = _ABLATION / f"e7_12_slice4_tool_grades{suffix}.md"
    write_report(results, fdr, side, dest,
                 _ABLATION / "e7_12_artifacts" / f"mle_grade_coverage{suffix}.csv")
    for m, r in results.items():
        log.info("FINAL [%s] %s → %s", m, r.verdict, r.winner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
