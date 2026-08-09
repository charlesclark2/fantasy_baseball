"""run_nf_w2d_2025_regate.py — NF-W2d §0.5 bake-off: the injury-availability family re-gated with
2025 in the fold set.

Everything decidable-in-advance lives as a CONSTANT in `weekly_projection_w2d.py`; this runner
READS it and restates nothing (the NF-D16 discipline). The narrative pre-registration is committed
at `ablation_results/nf_w2d_preregistration.md` BEFORE the full run.

⛔ ONLY THE FOLD SET CHANGES vs NF-W2b. The per-fold reducer, the selection, the deflation and the
gate composition are IMPORTED from the NF-W2b runner/module — they are not re-implemented here, so
they cannot drift. 2025H1/2025H2 leave SHADOW and join the gated set (12 → 14 folds).

PIPELINE: certified NF-W0 frame → NF-W1 engineering → the TWO-ERA injury family (nflverse
`date_modified` ≤2024; the landed `nfl/pit/wayback_injuries` capture instants for 2025, per-row
coverage bounded at one NFL game week) → injury_rate family → per-GAME PIT gate with source-aware
provenance (a wayback record DECLARES its absent `source_timestamp`) → 14 gated folds → 3 arms +
the rate foil + 6 anchors through the SHARED reducer → per-position CRPS selection → NF18 PBO +
M14 DSR/FDR + cv_power fold-consistency → ship-or-null, anchor refusals hand-classified
CONSTRAINT_REFUSED → the REPRODUCTION CONTROL over the 12 legacy folds.

RUN (LAPTOP — reads the S3 NFL lake + the PIT store read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate --smoke
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
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import (  # noqa: E402
    score_qmat,
)
# ⭐ the per-fold reducer is IMPORTED, never re-implemented — "only the fold set changed" has to
# be a mechanical fact, not a claim a reader has to diff two files to verify.
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_injury_rate_bakeoff import (  # noqa: E402
    run_fold,
    select_position,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2_injury_bakeoff import (  # noqa: E402
    load_sources_w2,
)

log = logging.getLogger("nfl.fantasy.nf_w2d")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_W2B_ARTIFACT = _REPORT_DIR / "nf_w2b_injury_rate_bakeoff.json"
SEASONS = (2016, 2025)


# ── Sources: nflverse for the stamped era, the landed capture store for 2025 ────────────────────
def load_wayback_store() -> pd.DataFrame:
    """Read the immutable NF-W0a capture store landed by NF-W2c + NF-W2c-CBS.

    An empty/unreadable store RAISES: a 2025 family silently built from zero captures would score
    as a clean "the mechanism does nothing" null, which is the NF1.7 (a) vacuous-anchor failure in
    its most expensive form (a whole era's verdict resting on a read that never happened).
    """
    import duckdb
    from deltalake import DeltaTable

    from quant_sports_intel_models.football.nfl.ingest import s3io
    from quant_sports_intel_models.football.nfl.pit import store

    uri = store.table_uri(W2D.WAYBACK_STORE_SOURCE)
    dt = DeltaTable(uri, storage_options=s3io.storage_options() if uri.startswith("s3://") else None)
    con = duckdb.connect()
    con.register("pit_captures", dt.to_pyarrow_dataset())
    try:
        df = con.sql(
            "select subject_key, season, week, gsis_id, position, report_status, "
            "practice_status, capture_timestamp from pit_captures"
        ).df()
    finally:
        con.unregister("pit_captures")
    if df.empty:
        raise SystemExit(
            f"the {W2D.WAYBACK_STORE_SOURCE} store returned ZERO rows — refusing to gate 2025 on "
            f"an unread source (NF1.7 (a): an empty read must never be scored as a measured null)"
        )
    log.info("capture store: %d rows / %d subjects / weeks %s–%s", len(df),
             df["subject_key"].nunique(), int(df["week"].min()), int(df["week"].max()))
    return df


def build_matrix_w2d(seasons: tuple[int, int], *, rebuild_cache: bool = False
                     ) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Assemble (or reload) the W2d matrix. ⭐ THE PIT GATE RUNS ON EVERY BUILD, cache hit or not
    (the NF-C0e wired-≠-invoked shape, cache edition)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    key = W2D.matrix_key_w2d(seasons)
    cache = _ARTIFACTS / f"nf_w2d_weekly_matrix_{key}.parquet"
    store_raw = load_wayback_store()
    if cache.exists() and not rebuild_cache:
        log.info("matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        feat = pd.read_parquet(cache)
        for c in ("_inj_dm_utc", "_rate_max_stamp_utc"):
            feat[c] = pd.to_datetime(feat[c], utc=True, errors="coerce")
        audit = W2D.run_pit_gate_w2d(feat)
        feat = feat.loc[audit.pop("kept_index")].reset_index(drop=True)
        return feat, audit, store_raw

    src = load_sources_w2(seasons)
    injuries = W2D.combine_injury_sources(src["injuries"], W2D.wayback_injury_rows(store_raw))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spine = WF.build_spine(src["rosters"], src["schedule"])
    frame = WF.attach_labels(
        spine, src["stats"], label_version=WP.LABEL_VERSION, label_as_of_timestamp=stamp,
        scoring_system_id=WP.SCORING_SYSTEM_ID, snaps=src["snaps"],
    )
    log.info("certified frame: %d rows (%d zeros retained)", len(frame), int(frame["is_zero"].sum()))
    modeled, audit = W2D.assemble_matrix_w2d(
        frame, src["stats"], src["snaps"], src["schedule"], injuries)
    modeled.to_parquet(cache, index=False)
    log.info("matrix cached → %s (%d rows; PIT: %d game-groups / %d records "
             "(%d injury, %d rate, %d wayback-provenance) checked, %d rows dropped)",
             cache.name, len(modeled), audit["game_groups_checked"], audit["records_checked"],
             audit["injury_records_checked"], audit["rate_records_checked"],
             audit["wayback_records_checked"], audit["rows_dropped"])
    return modeled, audit, store_raw


def _crps_frame(fold_results: list[dict], pos: str) -> pd.DataFrame:
    return pd.DataFrame({
        fr["label"]: {label: fr["scores"][label][pos] for label in fr["scores"]}
        for fr in fold_results
    }).T


def reproduction_control(fold_results: list[dict]) -> dict:
    """⭐ THE POSITIVE CONTROL that makes "only the fold set changed" a MEASUREMENT.

    The 12 legacy folds train only on `gw ≤ start − 3` and test inside 2019–2024, so nothing they
    touch can depend on the 2025 source. Their per-fold CRPS must therefore reproduce the recorded
    NF-W2b artifact to `REPRO_TOLERANCE`. A mismatch means the inherited harness was perturbed by
    the 2025 plumbing ⇒ the run is INVALID, and it is NEVER reported as an era effect.

    ⛔ Fails CLOSED: a missing artifact, a missing fold, or a missing arm is UNEVALUABLE, never a
    pass (NF1.7 (a)) — and the comparison asserts it actually compared something.
    """
    if not _W2B_ARTIFACT.exists():
        return {"state": "UNEVALUABLE", "passes": False,
                "reason": f"{_W2B_ARTIFACT.name} absent — cannot prove the legacy folds are "
                          f"unchanged; a control that cannot run is not a pass"}
    prior = json.loads(_W2B_ARTIFACT.read_text())
    ref = {fr["label"]: fr["scores"] for fr in prior.get("fold_results", [])}
    legacy = [fr for fr in fold_results
              if int(fr["label"][:4]) in W2D.LEGACY_SEASONS]
    compared, diffs, missing = 0, [], []
    for fr in legacy:
        prior_scores = ref.get(fr["label"])
        if prior_scores is None:
            missing.append(fr["label"])
            continue
        for arm, by_pos in fr["scores"].items():
            if arm not in prior_scores:
                missing.append(f"{fr['label']}:{arm}")
                continue
            for pos in WP.POSITIONS:
                a, b = float(by_pos[pos]), float(prior_scores[arm][pos])
                compared += 1
                if abs(a - b) > W2D.REPRO_TOLERANCE:
                    diffs.append({"fold": fr["label"], "arm": arm, "position": pos,
                                  "w2d": round(a, 8), "w2b": round(b, 8),
                                  "abs_delta": round(abs(a - b), 10)})
    # a control that compared nothing has proven nothing
    if compared == 0:
        return {"state": "UNEVALUABLE", "passes": False, "comparisons": 0,
                "reason": "zero legacy (fold, arm, position) cells were compared — the control "
                          "is vacuous, which is not a pass (NF1.7 (a))",
                "missing": sorted(set(missing))[:20]}
    return {
        "state": "PASS" if not diffs and not missing else "FAIL",
        "passes": bool(not diffs and not missing),
        "tolerance": W2D.REPRO_TOLERANCE,
        "legacy_folds_compared": len(legacy), "comparisons": compared,
        "max_abs_delta": round(max((d["abs_delta"] for d in diffs), default=0.0), 12),
        "mismatches": diffs[:20], "missing": sorted(set(missing))[:20],
        "note": ("the 12 NF-W2b folds reproduce exactly ⇒ the 2025 plumbing did not perturb the "
                 "inherited harness, so every difference below is an ERA effect"
                 if not diffs and not missing else
                 "⛔ the inherited harness MOVED on the legacy folds — this run is INVALID and "
                 "the differences are NOT an era effect"),
    }


def era_delta(fold_results: list[dict], winners: dict[str, str]) -> dict:
    """The 12-fold sub-read beside the 14-fold read, so what adding 2025 DID is a QUANTITY rather
    than an inference.

    The SAME arm (the official 14-fold winner) is scored on each subset — comparing a different
    argmin per subset would confound "the era moved the lift" with "the era moved the pick".
    Diagnostic; the gate never reads it.
    """
    legacy = [fr for fr in fold_results if int(fr["label"][:4]) in W2D.LEGACY_SEASONS]
    new = [fr for fr in fold_results if int(fr["label"][:4]) not in W2D.LEGACY_SEASONS]
    out: dict = {"legacy_folds": [fr["label"] for fr in legacy],
                 "new_folds": [fr["label"] for fr in new],
                 "note": "the 14-fold winner scored on each subset; a per-subset argmin would "
                         "confound an era effect with a change of pick"}
    for pos in WP.POSITIONS:
        winner, row = winners[pos], {"arm": winners[pos]}
        for tag, subset in (("full_14", fold_results), ("legacy_12", legacy), ("new_2025", new)):
            if not subset:
                row[tag] = None
                continue
            crps = _crps_frame(subset, pos)
            d = (crps[W2D.FOIL_W2D] - crps[winner]).to_numpy(dtype=float)
            row[tag] = {"n_folds": len(subset),
                        "mean_lift_vs_foil": round(float(np.nanmean(d)), 4),
                        "fold_wins": int((d > 0).sum()),
                        "mean_lift_vs_production": round(float(np.nanmean(
                            (crps[W2D.PROD_INCUMBENT_W2D] - crps[winner]).to_numpy())), 4)}
        out[pos] = row
    return out


def covered_subset_diagnostic(feat: pd.DataFrame, folds: list[WP.Fold]) -> dict:
    """Where the mechanism CAN act on the new folds (NF-D20 active-fold count).

    Diagnostic only — the gate reads the FULL population, because a partially-covered feed is
    exactly what the champion faces at serve time. Reported so a null caused by coverage dilution
    is distinguishable from a null caused by the mechanism.
    """
    out = []
    for fold in folds:
        test = feat.loc[fold.test_idx]
        obs = pd.to_numeric(test["injury_report__observed"], errors="coerce").fillna(0.0)
        listed = pd.to_numeric(test["injury_report__listed"], errors="coerce")
        out.append({
            "fold": fold.label, "n_test": int(len(test)),
            "observed_rows": int((obs == 1.0).sum()),
            "observed_share": round(float((obs == 1.0).mean()), 4),
            "listed_share_over_observed": (
                round(float(np.nansum(listed.to_numpy()) / max(int((obs == 1.0).sum()), 1)), 4)),
            "weeks_fully_uncovered": sorted(
                int(w) for w, g in test.groupby("week")
                if float(pd.to_numeric(g["injury_report__observed"],
                                       errors="coerce").fillna(0.0).max()) == 0.0),
        })
    return {"per_fold": out}


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W2d — the injury-availability family re-gated with 2025 in the fold set "
      "(§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **gated folds:** {out['n_folds']} "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}) · **modeled rows:** {out['n_rows']} · "
      f"**label:** `{out['evaluation_label_version']}` / `{out['scoring_system_id']}`")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim, "
      "**deploy-held**: this story validates a TRAINING ERA and promotes, publishes and retrains "
      "nothing. Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects "
      "(inverted at QB/TE on this frame). ONLY the fold set changed vs NF-W2b — 2025H1/2025H2 "
      "leave SHADOW and join the gated set; the reproduction control below measures that claim.")
    p("")
    rc = out["reproduction_control"]
    p(f"## Reproduction control — **{rc['state']}**")
    p("")
    p(f"{rc.get('note', rc.get('reason', ''))} "
      f"({rc.get('comparisons', 0)} legacy (fold, arm, position) cells compared at tolerance "
      f"{rc.get('tolerance')}; max |Δ| {rc.get('max_abs_delta')}).")
    p("")
    p("## 2025 coverage — the registered design quantities, recomputed at run time")
    p("")
    cov = out["coverage"]
    p(f"- primary bound **{cov.get('coverage_primary_bound_days')} d** (one NFL game week, "
      f"registered on sport structure, not tuned): coverage **{cov.get('coverage_primary')}** of "
      f"{cov.get('capture_era_rows')} modeled 2025 rows · diagnostics-only "
      f"{cov.get('coverage_diagnostic_only')}")
    p(f"- by position {cov.get('by_position')} · fully-uncovered weeks "
      f"**{cov.get('uncovered_weeks')}** · capture age (days) {cov.get('capture_age_days')}")
    p(f"- listed share over covered rows **{cov.get('listed_share_over_covered')}** "
      f"(the NF-D20 activity count — compare the 2016–2024 fold activity table below)")
    p(f"- ⚠️ per-COLUMN absence over listed 2025 rows (MH2.1 (c) — never a pooled mean): "
      f"{cov.get('per_column_absence_over_listed')}")
    p("")
    p(pd.DataFrame(cov.get("by_week", [])).to_markdown(index=False))
    p("")
    p(f"**Revision-clause activity (NF-D20):** {out['revision_clause']}")
    p("")
    p("## Per-position verdicts (14 gated folds)")
    p("")
    for pos in WP.POSITIONS:
        sel, gate = out["positions"][pos], out["gates"][pos]
        verdict = ("SHIP" if gate["ship"]
                   else f"NULL ({out['null_states'].get(pos, {}).get('state', 'n/a')})")
        p(f"### {pos} — **{verdict}**")
        p("")
        rows = [{"arm": k, "mean_crps": v} for k, v in sel["mean_crps"].items()]
        p(pd.DataFrame(rows).sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- winner `{sel['winner']}` vs rate foil `{sel['foil']}`: mean lift "
          f"{np.mean(sel['deltas_by_fold']):+.4f} CRPS, fold wins "
          f"{sel['fold_wins']}/{out['n_folds']} (clause requires "
          f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} · "
          f"p {sel['p_one_sided']} · FDR pass {gate['checks']['fdr_ok']}")
        p(f"- pure player-level attribution (vs `base_rate`): {sel['pair_deltas_vs_base_rate']}")
        p(f"- decomposition (vs production `base_noRate`): {sel['decomposition']}")
        p(f"- anchors: {sel['anchors']} · permutation detail {sel['permutation_detail']} · "
          f"coverage(80) {sel['coverage']}")
        p(f"- MAE (report-only, never selects): {sel['mean_mae_report_only']}")
        p(f"- ERA DELTA (diagnostic): {out['era_delta'][pos]}")
        p("")
    p("## Per-fold family activity (the NF-D20 discipline)")
    p("")
    p(pd.DataFrame(out["fold_activity"]).to_markdown(index=False))
    p("")
    p("## Covered-subset diagnostic (where the mechanism can act) — never gated")
    p("")
    p(pd.DataFrame(out["covered_subset"]["per_fold"]).to_markdown(index=False))
    p("")
    p("## Deflation convention")
    p("")
    p(out["deflation_convention"])
    p("")
    for title, key in (("Gate detail", "gates"),
                       ("Null-state classification (failing positions)", "null_states")):
        p(f"## {title}")
        p("")
        p("```json")
        p(json.dumps(out[key], indent=2, default=str))
        p("```")
        p("")
    path.write_text("\n".join(a))


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W2d 2025 re-gate of the injury family")
    ap.add_argument("--smoke", action="store_true",
                    help="last 2 legacy folds + both 2025 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)

    t0 = time.time()
    feat, pit_audit, store_raw = build_matrix_w2d(SEASONS, rebuild_cache=args.rebuild_cache)
    coverage = W2D.coverage_report(feat, W2D.wayback_injury_rows(store_raw))
    revision = W2D.revision_clause_activity(store_raw)
    log.info("2025 coverage @%.0fd = %s (uncovered weeks %s)", W2D.COVERAGE_MAX_AGE_DAYS,
             coverage.get("coverage_primary"), coverage.get("uncovered_weeks"))

    gated = W2.build_folds_w2(feat, W2D.TEST_BLOCKS_W2D)
    if args.smoke:
        legacy = [f for f in gated if int(f.label[:4]) in W2D.LEGACY_SEASONS][-2:]
        gated = legacy + [f for f in gated if int(f.label[:4]) not in W2D.LEGACY_SEASONS]
    n_folds = len(gated)
    log.info("running %d gated folds over %d rows (%d arms + foil + %d anchors)",
             n_folds, len(feat), len(W2D.REAL_ARMS_W2D), len(W2D.ANCHORS_W2D))

    fold_results = [run_fold(f, feat) for f in gated]

    positions = {pos: select_position(pos, fold_results, n_folds) for pos in WP.POSITIONS}
    pvals = {pos: positions[pos]["p_one_sided"] for pos in WP.POSITIONS}
    fdr = M14.bh_fdr(pvals, q=WP.FDR_Q)
    gates = {pos: W2B.position_gate_w2b(positions[pos], fdr[pos]) for pos in WP.POSITIONS}

    null_states: dict[str, dict] = {}
    for pos in WP.POSITIONS:
        if gates[pos]["ship"]:
            continue
        sel = positions[pos]
        # ⭐ the hand-check classify_null cannot do (NF-D18/MH2.7, hit twice on this very line):
        # an anchor/registration refusal with green statistical gates is CONSTRAINT_REFUSED —
        # never POWER_LIMITED, never a sample-size re-test trigger.
        hand = W2B.hand_classify_refusal(gates[pos]["checks"])
        machine = cv_power.classify_null(
            metric=f"nf_w2d_injury_crps_{pos}", n_folds=n_folds, n_arms=len(W2D.REAL_ARMS_W2D),
            beats_foil=sel["beats_foil"], observed_sr=sel["observed_sr"],
            var_trials_sr=sel["var_trials_sr"], fold_wins=sel["fold_wins"],
            p_one_sided=sel["p_one_sided"], bh_cutoff=WP.FDR_Q,
        )
        if hand is not None:
            null_states[pos] = {**hand, "classify_null_raw": {
                "state": machine.state, "note": "recorded for the instrument's record only — "
                "overridden by the hand classification above"}}
        else:
            null_states[pos] = {"state": machine.state, "reason": machine.reason,
                                "retest_trigger": machine.retest_trigger}

    repro = reproduction_control(fold_results)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W2d", "smoke": bool(args.smoke),
        "elapsed_seconds": round(time.time() - t0, 1),
        "evaluation_label_version": WP.LABEL_VERSION,
        "scoring_system_id": WP.SCORING_SYSTEM_ID,
        "selection_metric": WP.SELECTION_METRIC,
        "n_rows": int(len(feat)), "n_folds": n_folds,
        "fold_labels": [f.label for f in gated],
        "pit_audit": pit_audit,
        "coverage": coverage,
        "revision_clause": revision,
        "reproduction_control": repro,
        "deflation_convention": (
            "The fantasy vertical calls `M14.deflated_sharpe` DIRECTLY — the DSR-CONV "
            "degenerate-exclusion change reached only the two MLB legs (`e7_9`, `mh2_5`). "
            "NF-W2d uses that whole-field call unchanged over the declared 3-arm family, "
            "byte-identically the convention NF-W2 and NF-W2b used. No field trim, no convention "
            "switch. In this harness anchors and degenerates were never in `trial_srs`, so there "
            "is no degenerate-inflated V for DSR-CONV to remove and the question does not arise."),
        "preregistration": {
            "hypothesis": "the certified NF-W2b injury-availability family still beats its "
                          "matched foil `base_rate` when the fold set is extended to include "
                          "2025 — an era whose injury signal is composed of as-of-that-instant "
                          "capture observations rather than the vendor's own date_modified "
                          "stamp, i.e. the signal character it will have at serve time",
            "only_the_fold_set_changed": True,
            "real_arms": list(W2D.REAL_ARMS_W2D), "foil": W2D.FOIL_W2D,
            "production_incumbent": W2D.PROD_INCUMBENT_W2D,
            "anchors": list(W2D.ANCHORS_W2D),
            "oracle_of_form": dict(W2D.ORACLE_OF_FORM_W2D),
            "test_blocks": [list(t) for t in W2D.TEST_BLOCKS_W2D],
            "shadow_blocks": [list(t) for t in W2D.SHADOW_BLOCKS_W2D],
            "legacy_blocks_for_repro_control": [list(t) for t in W2D.LEGACY_BLOCKS_W2D],
            "coverage_max_age_days": W2D.COVERAGE_MAX_AGE_DAYS,
            "diagnostic_coverage_bounds": [None if not np.isfinite(b) else b
                                           for b in W2D.DIAGNOSTIC_COVERAGE_BOUNDS],
            "wayback_store": W2D.WAYBACK_STORE_SOURCE,
            "purge_weeks": WP.PURGE_WEEKS, "pbo_max": WP.PBO_MAX, "dsr_min": WP.DSR_MIN,
            "fdr_q": WP.FDR_Q, "coverage_floor": WP.COVERAGE_FLOOR,
            "features": list(W2D.FEATURES_W2D),
            "deploy_held": "best_alpha=0; promotes nothing, publishes nothing, retrains nothing",
        },
        "positions": positions, "gates": gates, "fdr": fdr, "null_states": null_states,
        "fold_activity": [{"fold": fr["label"], **fr["activity"],
                           "override": fr["override_meta"]} for fr in fold_results],
        "covered_subset": covered_subset_diagnostic(feat, gated),
        "era_delta": era_delta(fold_results,
                               {pos: positions[pos]["winner"] for pos in WP.POSITIONS}),
        "fold_results": [{k: fr[k] for k in ("label", "scores", "n_train", "n_test")}
                         for fr in fold_results],
    }
    verdicts = {pos: ("SHIP" if gates[pos]["ship"]
                      else null_states.get(pos, {}).get("state", "NULL"))
                for pos in WP.POSITIONS}
    if not repro["passes"]:
        # ⛔ an invalid run must never present per-position verdicts as findings
        verdicts = {pos: f"INVALID_RUN ({repro['state']})" for pos in WP.POSITIONS}
    out["verdict"] = verdicts
    out["headline"] = " · ".join(f"{pos}:{v}" for pos, v in verdicts.items())

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_w2d_2025_regate{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_w2d_2025_regate{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["elapsed_seconds"])
    print(json.dumps({"verdict": verdicts, "headline": out["headline"],
                      "reproduction_control": repro["state"],
                      "coverage_primary": coverage.get("coverage_primary")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
