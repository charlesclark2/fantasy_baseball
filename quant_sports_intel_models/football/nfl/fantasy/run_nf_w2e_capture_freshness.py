"""run_nf_w2e_capture_freshness.py — NF-W2e: is NF-W2d's 2025 attenuation caused by CAPTURE
FRESHNESS? A mechanism-attribution study over a monotone freshness ladder.

Everything decidable-in-advance is a CONSTANT in `weekly_projection_w2e.py`; this runner reads it
and restates nothing. The narrative pre-registration is committed at
`ablation_results/nf_w2e_preregistration.md` BEFORE any lift was scored (commit 8221fb26).

⛔ CERTIFIES NOTHING, BY DESIGN — the consumption rule can only act on capture-era rows, so the
test has 2 ACTIVE folds, where the fold clause is unattainable, PBO is undefined,
`sign_test_floor(2)` = 0.25 exceeds every BH cutoff and `dsr_ceiling(2)` = 0.9214 is below the
0.95 gate. The verdict field is fixed to NO_CERTIFICATION_POSSIBLE and the primary read is a
week-CLUSTERED row-level paired delta, not a fold-level gate.

RUN (LAPTOP — reads the S3 NFL lake + the PIT store read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2e_capture_freshness
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2e_capture_freshness --smoke
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
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2e as W2E  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2_injury_bakeoff import (  # noqa: E402
    load_sources_w2,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate import (  # noqa: E402
    SEASONS,
    load_wayback_store,
)

log = logging.getLogger("nfl.fantasy.nf_w2e")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_KEY = ["season", "week", "gsis_id"]


# ── Build one matrix per rung of the ladder ─────────────────────────────────────────────────────
def build_rungs(*, rebuild_cache: bool = False) -> tuple[dict[str, pd.DataFrame], dict, pd.DataFrame]:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    store_raw = load_wayback_store()
    src = load_sources_w2(SEASONS)
    injuries = W2D.combine_injury_sources(src["injuries"], W2D.wayback_injury_rows(store_raw))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spine = WF.build_spine(src["rosters"], src["schedule"])
    frame = WF.attach_labels(spine, src["stats"], label_version=WP.LABEL_VERSION,
                             label_as_of_timestamp=stamp,
                             scoring_system_id=WP.SCORING_SYSTEM_ID, snaps=src["snaps"])
    base_feat = WP.engineer_features(frame, src["stats"], src["snaps"], src["schedule"])

    rungs: dict[str, pd.DataFrame] = {}
    audits: dict[str, dict] = {}
    for name, consumption in W2E.FRESHNESS_LADDER:
        eng = W2E.engineer_rung(base_feat, injuries, consumption_max_age_days=consumption)
        W2B.assert_feature_provenance_w2b(W2D.FEATURES_W2D)
        # ⭐ the PIT gate runs for EVERY rung — a rung is a different consumed-stamp set, so a
        # gate result borrowed from another rung would prove nothing about this one.
        audit = W2D.run_pit_gate_w2d(eng)
        kept = eng.loc[audit.pop("kept_index")].reset_index(drop=True)
        rungs[name], audits[name] = kept, audit
        log.info("rung %-13s: %d rows | PIT %d records (%d wayback) / %d dropped | listed(2025) %d",
                 name, len(kept), audit["records_checked"], audit["wayback_records_checked"],
                 audit["rows_dropped"],
                 int((pd.to_numeric(kept.loc[kept.season == 2025, "injury_report__listed"],
                                    errors="coerce") == 1.0).sum()))
    return rungs, audits, store_raw


def assert_rows_aligned(rungs: dict[str, pd.DataFrame]) -> dict:
    """Paired row-level deltas require the rungs to be the SAME rows in the SAME order.

    Fails closed rather than trusting that two independent PIT gates happened to keep the same
    set — a silently mis-aligned pairing would produce a confident, meaningless delta.
    """
    base = rungs[W2E.INCUMBENT_RUNG][_KEY].astype(str).agg("|".join, axis=1).to_numpy()
    bad = []
    for name, df in rungs.items():
        other = df[_KEY].astype(str).agg("|".join, axis=1).to_numpy()
        if len(other) != len(base) or not np.array_equal(other, base):
            bad.append(name)
    if not len(base):
        raise ValueError("zero rows — the alignment check would be vacuous (NF1.7 (a))")
    return {"state": "PASS" if not bad else "FAIL", "passes": not bad,
            "rows": int(len(base)), "misaligned_rungs": bad}


# ── The stratifier validation, recomputed at run time (MH2.1) ───────────────────────────────────
def stratifier_validation(store_raw: pd.DataFrame, feat: pd.DataFrame) -> dict:
    """Does capture age separate DESIGNATION STALENESS? Publish it BEFORE reading any lift.

    ⭐ Reports BOTH the confounded and the corrected version. The confounded one read
    "rank corr ≈ 0, the stratifier is inert" purely because nfl.com publishes practice-only rows
    with a NULL `report_status`, so a row crossing between a designation-publishing source and a
    practice-publishing one scored as a "change". Hiding the first cut would hide the reason the
    second is trustworthy.
    """
    from scipy.stats import spearmanr
    wb = W2D.wayback_injury_rows(store_raw)
    wb["cap"] = pd.to_datetime(wb["date_modified"], utc=True)
    wb["rs"] = wb["report_status"].astype(object).where(
        wb["report_status"].notna(), "<none>").astype(str)
    gd = feat[feat["season"] == W2D.WAYBACK_FIRST_SEASON][
        ["gsis_id", "week", "_target_gameday"]].drop_duplicates()
    gd["g"] = pd.to_datetime(gd["_target_gameday"]).dt.tz_localize("UTC")
    m = wb.merge(gd[["gsis_id", "week", "g"]], on=["gsis_id", "week"], how="inner")
    m["age"] = (m["g"] - m["cap"]).dt.total_seconds() / 86400.0
    m = m[(m["cap"] < m["g"]) & (m["age"] <= W2D.COVERAGE_MAX_AGE_DAYS)]

    pairs = []
    for _, g in m.sort_values("cap").groupby(["gsis_id", "week"]):
        if len(g) < 2:
            continue
        a, b = g.iloc[-2], g.iloc[-1]
        pairs.append({"gap": float((b["cap"] - a["cap"]).total_seconds() / 86400.0),
                      "older": a["rs"], "newer": b["rs"]})
    P = pd.DataFrame(pairs)
    if len(P) < 30:
        return {"state": "UNEVALUABLE", "n_pairs": int(len(P)),
                "reason": "too few multi-capture player-weeks to validate the partition — a "
                          "stratifier that cannot be validated may not be read (MH2.1)"}

    def _cut(df: pd.DataFrame) -> dict:
        df = df.copy()
        df["changed"] = (df["older"] != df["newer"]).astype(int)
        df["bin"] = pd.cut(df["gap"], [0, 0.5, 1, 2, 3, 99],
                           labels=["<0.5d", "0.5-1d", "1-2d", "2-3d", ">3d"])
        t = df.groupby("bin", observed=True).agg(n=("changed", "size"),
                                                 change_rate=("changed", "mean"))
        t["se"] = ((t["change_rate"] * (1 - t["change_rate"])) / t["n"]) ** 0.5
        r, p = spearmanr(df["gap"], df["changed"])
        lo = df[df["gap"] <= W2E.VALIDATED_STRATUM_BOUNDARY_DAYS]["changed"]
        hi = df[df["gap"] > W2E.VALIDATED_STRATUM_BOUNDARY_DAYS]["changed"]
        return {"n_pairs": int(len(df)), "overall_change_rate": round(float(df["changed"].mean()), 4),
                "by_bin": [{"bin": str(i), **{k: (round(float(v), 4) if pd.notna(v) else None)
                                              for k, v in row.items()}}
                           for i, row in t.iterrows()],
                "rank_corr": round(float(r), 4), "rank_corr_p": round(float(p), 6),
                "boundary_days": W2E.VALIDATED_STRATUM_BOUNDARY_DAYS,
                "rate_at_or_below": round(float(lo.mean()), 4) if len(lo) else None,
                "rate_above": round(float(hi.mean()), 4) if len(hi) else None,
                "n_at_or_below": int(len(lo)), "n_above": int(len(hi))}

    real = P[(P["older"] != "<none>") & (P["newer"] != "<none>")]
    corrected = _cut(real)
    confounded = _cut(P)
    separates = bool(corrected["rank_corr"] > 0 and corrected["rank_corr_p"] < 0.05
                     and corrected["rate_above"] is not None
                     and corrected["rate_above"] > corrected["rate_at_or_below"])
    return {
        "state": "VALIDATED" if separates else "DOES_NOT_SEPARATE",
        "separates_designation_staleness": separates,
        "corrected": corrected, "confounded_first_cut": confounded,
        "confound": ("nfl.com publishes practice-only rows with a NULL report_status, so a pair "
                     "crossing between a designation-publishing source and a practice-publishing "
                     "one scores as a 'change' that is a SOURCE-FORMAT difference, not a "
                     "designation change"),
        "dropped_as_source_format_crossings": int(len(P) - len(real)),
        "note": ("a stratifier that does not separate the realized quantity may not be read "
                 "(MH2.1) — this block runs BEFORE any lift is scored"),
    }


def carryover_census(feat: pd.DataFrame) -> dict:
    """How many listed capture-era rows carry a designation a FRESHER capture superseded?"""
    cap = feat[(feat["season"].astype(int) >= W2D.WAYBACK_FIRST_SEASON)
               & (pd.to_numeric(feat["injury_report__listed"], errors="coerce") == 1.0)].copy()
    if not len(cap):
        return {"state": "UNEVALUABLE", "reason": "no listed capture-era rows"}
    g = pd.to_datetime(cap["_target_gameday"]).dt.tz_localize("UTC")
    consumed_age = (g - pd.to_datetime(cap["_inj_dm_utc"], utc=True)).dt.total_seconds() / 86400.0
    carry = consumed_age - pd.to_numeric(cap["_inj_capture_age_days"], errors="coerce")
    sup = carry >= 0.01
    return {"state": "OK", "listed_rows": int(len(cap)),
            "superseded_rows": int(sup.sum()),
            "superseded_share": round(float(sup.mean()), 4),
            "carryover_gap_days": {k: round(float(v), 3) for k, v in
                                   carry[sup].describe(percentiles=[.5, .9])[
                                       ["50%", "90%", "max"]].items()} if int(sup.sum()) else {},
            "note": "structurally impossible in the legacy era (one nflverse report per "
                    "player-week), so this is a capture-regime property, not a defect"}


# ── Scoring ─────────────────────────────────────────────────────────────────────────────────────
def _per_row_crps(qmat: np.ndarray, test: pd.DataFrame) -> np.ndarray:
    return WP.crps_from_quantiles(qmat, test["fantasy_points"].to_numpy(dtype=float))


def run_fold(fold: WP.Fold, rungs: dict[str, pd.DataFrame], *, extra_rungs: bool) -> dict:
    """Fit the foil + the incumbent rung always; the tighter rungs only where they can differ
    (the capture-era folds) or where the MEASURED tie control needs them."""
    t0 = time.time()
    base = rungs[W2E.INCUMBENT_RUNG]
    train_b, test_b = base.loc[fold.train_idx], base.loc[fold.test_idx]
    rate_feats, full_feats = list(W2B.FEATURES_BASE_RATE), list(W2D.FEATURES_W2D)

    p0_rate, cond_rate = W2.hurdle_parts(train_b, test_b, rate_feats, rate_feats)
    qmats = {W2E.FOIL_W2E: W2.mix_parts(p0_rate, cond_rate),
             "nihilist_zero": WP.anchor_nihilist(test_b),
             "pos_marginal": WP.anchor_pos_marginal(train_b, test_b)}

    names = list(W2E.LADDER_ARMS) if extra_rungs else [W2E.INCUMBENT_RUNG]
    cond_inc = None
    for name in names:
        df = rungs[name]
        tr, te = df.loc[fold.train_idx], df.loc[fold.test_idx]
        p0, cond = W2.hurdle_parts(tr, te, full_feats, full_feats)
        qmats[name] = W2.mix_parts(p0, cond)
        if name == W2E.INCUMBENT_RUNG:
            cond_inc = cond
    # NF-D16 per-FORM peeking floor for the shared `inj_both` form
    y_te = test_b["fantasy_points"].to_numpy(dtype=float)
    qmats["oracle_avail__inj"] = W2.mix_parts((y_te == 0.0).astype(float), cond_inc)

    from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import score_qmat
    scores = {k: score_qmat(v, test_b) for k, v in qmats.items()}
    per_row = {k: _per_row_crps(v, test_b) for k, v in qmats.items()}
    log.info("fold %s scored in %.1fs (%d arms; extra_rungs=%s)",
             fold.label, time.time() - t0, len(qmats), extra_rungs)
    return {"label": fold.label, "scores": scores, "per_row": per_row,
            "test_index": fold.test_idx, "extra_rungs": extra_rungs,
            "n_test": int(len(test_b))}


def measured_tie_control(fold_results: list[dict]) -> dict:
    """The three rungs must agree EXACTLY on the registered legacy folds — a measured backstop to
    the mechanical inertness proof. Fails closed if the registered folds were not scored."""
    got = {fr["label"]: fr for fr in fold_results if fr["label"] in W2E.MEASURED_TIE_FOLDS}
    missing = [f for f in W2E.MEASURED_TIE_FOLDS if f not in got]
    if missing:
        return {"state": "UNEVALUABLE", "passes": False, "missing_folds": missing,
                "reason": "a registered tie-control fold was not scored — a control that did not "
                          "run is not a pass (NF1.7 (a))"}
    compared, diffs = 0, []
    for label, fr in got.items():
        for arm in W2E.LADDER_ARMS:
            if arm == W2E.INCUMBENT_RUNG or arm not in fr["scores"]:
                continue
            for pos in WP.POSITIONS:
                a = float(fr["scores"][W2E.INCUMBENT_RUNG][pos])
                b = float(fr["scores"][arm][pos])
                compared += 1
                if abs(a - b) > W2E.TIE_TOLERANCE:
                    diffs.append({"fold": label, "arm": arm, "position": pos,
                                  "abs_delta": round(abs(a - b), 12)})
    if compared == 0:
        return {"state": "UNEVALUABLE", "passes": False, "comparisons": 0,
                "reason": "zero comparisons — the tie control is vacuous"}
    return {"state": "PASS" if not diffs else "FAIL", "passes": not diffs,
            "folds": list(got), "comparisons": compared, "tolerance": W2E.TIE_TOLERANCE,
            "max_abs_delta": round(max((d["abs_delta"] for d in diffs), default=0.0), 12),
            "differences": diffs[:10]}


def capture_era_reads(fold_results: list[dict], rungs: dict[str, pd.DataFrame]) -> dict:
    """PRIMARY: week-clustered row-level paired deltas on the capture era.

    Sign convention: POSITIVE = the tighter rung is BETTER than the incumbent (CRPS is a loss,
    so the delta is `incumbent − rung`).
    """
    base = rungs[W2E.INCUMBENT_RUNG]
    cap = [fr for fr in fold_results
           if int(fr["label"][:4]) >= W2D.WAYBACK_FIRST_SEASON and fr["extra_rungs"]]
    if not cap:
        return {"state": "UNEVALUABLE", "reason": "no capture-era fold carried the tighter rungs"}
    idx = np.concatenate([fr["test_index"] for fr in cap])
    weeks = base.loc[idx, "week"].to_numpy()
    positions = base.loc[idx, "position"].to_numpy()
    inc = np.concatenate([fr["per_row"][W2E.INCUMBENT_RUNG] for fr in cap])
    foil = np.concatenate([fr["per_row"][W2E.FOIL_W2E] for fr in cap])

    out: dict = {"state": "OK", "folds": [fr["label"] for fr in cap], "n_rows": int(len(idx)),
                 "sign_convention": "positive = the tighter rung BEATS the incumbent",
                 "per_rung": {}, "incumbent_lift_over_foil": {}}
    for arm in W2E.LADDER_ARMS:
        if arm == W2E.INCUMBENT_RUNG:
            continue
        vals = np.concatenate([fr["per_row"][arm] for fr in cap])
        out["per_rung"][arm] = {
            pos: W2E.clustered_paired_delta((inc - vals)[positions == pos], weeks[positions == pos])
            for pos in WP.POSITIONS}
        out["per_rung"][arm]["ALL"] = W2E.clustered_paired_delta(inc - vals, weeks)
    for pos in WP.POSITIONS:
        sel = positions == pos
        out["incumbent_lift_over_foil"][pos] = W2E.clustered_paired_delta(
            (foil - inc)[sel], weeks[sel])
    return out


def stratified_read(fold_results: list[dict], rungs: dict[str, pd.DataFrame]) -> dict:
    """SECONDARY (pre-registered): the incumbent's per-row lift over the foil, split at the
    VALIDATED ≤1 d / >1 d consumed-age boundary. If staleness attenuates the lift, the fresh
    stratum carries more of it."""
    base = rungs[W2E.INCUMBENT_RUNG]
    cap = [fr for fr in fold_results if int(fr["label"][:4]) >= W2D.WAYBACK_FIRST_SEASON]
    if not cap:
        return {"state": "UNEVALUABLE", "reason": "no capture-era folds scored"}
    idx = np.concatenate([fr["test_index"] for fr in cap])
    sub = base.loc[idx]
    g = pd.to_datetime(sub["_target_gameday"]).dt.tz_localize("UTC")
    consumed_age = ((g - pd.to_datetime(sub["_inj_dm_utc"], utc=True)).dt.total_seconds()
                    / 86400.0).to_numpy()
    listed = (pd.to_numeric(sub["injury_report__listed"], errors="coerce") == 1.0).to_numpy()
    inc = np.concatenate([fr["per_row"][W2E.INCUMBENT_RUNG] for fr in cap])
    foil = np.concatenate([fr["per_row"][W2E.FOIL_W2E] for fr in cap])
    weeks, positions = sub["week"].to_numpy(), sub["position"].to_numpy()
    lift = foil - inc

    b = W2E.VALIDATED_STRATUM_BOUNDARY_DAYS
    strata = {f"listed_fresh_le_{b:g}d": listed & (consumed_age <= b),
              f"listed_stale_gt_{b:g}d": listed & (consumed_age > b),
              "not_listed": ~listed}
    out: dict = {"state": "OK", "boundary_days": b,
                 "note": "the boundary is the VALIDATED stratifier cut, measured before any lift",
                 "per_position": {}}
    for pos in WP.POSITIONS:
        row = {}
        for name, mask in strata.items():
            sel = mask & (positions == pos)
            row[name] = {"n": int(sel.sum()),
                         **W2E.clustered_paired_delta(lift[sel], weeks[sel])}
        out["per_position"][pos] = row
    return out


def direction_word(all_read: dict) -> str:
    """THREE-way, never two — a CI that spans zero is a TIE, not a loss.

    Calling an indistinguishable result a loss is the NF1.8 flip-distribution error in prose: a
    direction statistic cannot separate "my arm is worse" from "my arm is indistinguishable from
    the incumbent". This story's whole carry-over reading turns on that distinction — `inj_freshest`
    pooled is -0.0008 with a CI spanning zero, i.e. dropping superseded designations changes
    NOTHING, which REFUTES carry-over as the mechanism. Reported as a loss it would read as weak
    evidence FOR carry-over mattering, the opposite conclusion.

    Fails closed to TIES: an absent/unevaluable `spans_zero` must never be narrated as a
    directional finding (NF1.7 (a)).
    """
    if all_read.get("spans_zero", True):
        return "TIES"
    return "BEATS" if all_read.get("mean_delta", 0) > 0 else "LOSES TO"


def compose_verdict_text(valid: bool, controls: dict, cap_reads: dict) -> str:
    """DERIVED, never stored — so a wording fix reaches an already-scored artifact.

    Kept a pure function of (validity, controls, clustered reads) for one reason: the verdict text
    is the sentence a reader quotes, and if it is only produced at scoring time then correcting it
    costs a 17-minute refit — which is exactly the pressure that leaves a known-wrong sentence in
    an artifact. `--reanalyze` re-derives it at zero refit cost.
    """
    if not valid:
        failed = {k: v["state"] for k, v in controls.items() if not v.get("passes")}
        return ("⛔ **INVALID RUN** — a control failed: "
                f"{failed}. The consumption rule leaked outside the capture era (or the rungs are "
                "not comparable), so nothing below is a freshness effect.")
    lines = []
    for arm, by_pos in cap_reads.get("per_rung", {}).items():
        allr = by_pos.get("ALL", {})
        # the parenthetical must fail closed with the WORD — an absent interval reading
        # "excludes zero" beside a TIES verdict is a self-contradicting sentence.
        if "spans_zero" not in allr:
            interval = "interval UNEVALUABLE"
        else:
            interval = "spans zero" if allr["spans_zero"] else "excludes zero"
        lines.append(f"`{arm}` {direction_word(allr)} the incumbent pooled "
                     f"(Δ={allr.get('mean_delta')} ± {allr.get('clustered_se')} clustered, "
                     f"CI95 {allr.get('ci95_clustered')}, {interval})")
    return (f"**{W2E.VERDICT_W2E}** — by design (see the power ceiling). Direction read at row "
            "level: " + " · ".join(lines) + ".")


def multiplicity_note(cap_reads: dict) -> dict:
    """BH q=0.10 over EVERY per-position × per-rung clustered comparison reported.

    ⭐ The study reports 2 rungs × 4 positions = 8 comparisons. Presenting eight nominal 95% CIs
    and pointing at the one that excludes zero is the multiplicity failure this program keeps
    cataloguing, so the correction is computed and published beside them. It is a READING aid, not
    a gate — at 2 active folds nothing is certifiable either way (see the power ceiling).
    """
    from scipy.stats import norm
    rows = []
    for arm, by_pos in cap_reads.get("per_rung", {}).items():
        for pos, v in by_pos.items():
            if pos == "ALL" or v.get("state") != "OK" or not v.get("clustered_se"):
                continue
            z = float(v["mean_delta"]) / float(v["clustered_se"])
            rows.append({"arm": arm, "position": pos, "mean_delta": v["mean_delta"],
                         "z_clustered": round(z, 3),
                         "p_two_sided": round(float(2 * (1 - norm.cdf(abs(z)))), 5)})
    if not rows:
        return {"state": "UNEVALUABLE", "reason": "no evaluable clustered comparisons"}
    rows.sort(key=lambda r: r["p_two_sided"])
    m = len(rows)
    survives_any = False
    for i, r in enumerate(rows):
        r["bh_cutoff_q10"] = round(WP.FDR_Q * (i + 1) / m, 5)
        r["survives_bh_q10"] = bool(r["p_two_sided"] <= r["bh_cutoff_q10"])
        survives_any = survives_any or r["survives_bh_q10"]
    return {"state": "OK", "n_comparisons": m, "q": WP.FDR_Q,
            "any_survives": survives_any, "comparisons": rows,
            "note": "a READING aid over the 8 reported comparisons — never a gate; at 2 active "
                    "folds nothing is certifiable in either direction"}


def era_stratum_shares(feat: pd.DataFrame) -> dict:
    """⭐ THE CROSS-ERA CHECK that decides whether a within-2025 freshness gradient can explain the
    NF-W2d era attenuation AT ALL.

    A within-era gradient only licenses an era EXPLANATION if the eras differ on that variable in
    the right DIRECTION. This computes the share of listed rows on each side of the validated
    boundary, per era. If the capture era is not staler than the legacy era, a freshness deficit
    cannot be why its lift is smaller — no matter how strong the within-era gradient is.

    ⚠️ It also records the reason the comparison is delicate: a legacy `date_modified` is the
    REPORT's own timestamp (the definitive Friday designation), while a capture instant is when
    the page was PHOTOGRAPHED and the page may already have been showing older content. Stamp age
    is therefore not the same quantity in the two eras, and the shares below bound what the
    comparison can say rather than settling it.
    """
    b = W2E.VALIDATED_STRATUM_BOUNDARY_DAYS
    listed = feat[pd.to_numeric(feat["injury_report__listed"], errors="coerce") == 1.0].copy()
    if not len(listed):
        return {"state": "UNEVALUABLE", "reason": "no listed rows"}
    g = pd.to_datetime(listed["_target_gameday"]).dt.tz_localize("UTC")
    age = (g - pd.to_datetime(listed["_inj_dm_utc"], utc=True)).dt.total_seconds() / 86400.0
    era = np.where(listed["season"].astype(int) >= W2D.WAYBACK_FIRST_SEASON,
                   "capture(2025)", "legacy(nflverse)")
    out = {"state": "OK", "boundary_days": b, "per_era": {}}
    for name in ("legacy(nflverse)", "capture(2025)"):
        sel = era == name
        if not sel.any():
            continue
        a = age[sel]
        out["per_era"][name] = {
            "listed_rows": int(sel.sum()),
            f"share_fresh_le_{b:g}d": round(float((a <= b).mean()), 4),
            f"share_stale_gt_{b:g}d": round(float((a > b).mean()), 4),
            "median_age_days": round(float(a.median()), 3),
            "sd_age_days": round(float(a.std(ddof=1)), 3),
            "share_gt_2d": round(float((a > 2.0).mean()), 4),
        }
    eras = out["per_era"]
    if len(eras) == 2:
        cap = eras["capture(2025)"][f"share_fresh_le_{b:g}d"]
        leg = eras["legacy(nflverse)"][f"share_fresh_le_{b:g}d"]
        out["capture_era_is_fresher_on_this_cut"] = bool(cap > leg)
        out["reading"] = (
            f"the capture era is FRESHER on this cut ({cap:.3f} vs {leg:.3f} of listed rows "
            f"within {b:g} day), so a freshness DEFICIT cannot explain its smaller lift — the "
            f"within-2025 gradient is real but does not transfer into an era explanation"
            if cap > leg else
            f"the capture era is staler on this cut ({cap:.3f} vs {leg:.3f}), so a freshness "
            f"deficit is directionally CAPABLE of contributing to the era attenuation")
        out["caveat"] = ("a legacy `date_modified` is the REPORT's own timestamp; a capture "
                         "instant is when the page was photographed. Stamp age is not the same "
                         "quantity across eras, so this comparison BOUNDS the freshness "
                         "explanation rather than settling it.")
    return out


def power_ceiling() -> dict:
    """The registered ceiling, COMPUTED (not asserted) so a reader can see it is structural."""
    n = len(W2E.CAPTURE_ERA_BLOCKS)
    clause = cv_power.fold_consistency_clause(n)
    return {"active_folds": n,
            "fold_clause_attainable": bool(clause.attainable),
            "fold_clause_wins_required": clause.wins_required,
            "pbo_evaluable": bool(cv_power.pbo_evaluable(n)),
            "sign_test_floor": round(float(cv_power.sign_test_floor(n)), 4),
            "dsr_ceiling": round(float(cv_power.dsr_ceiling(n)), 4),
            "dsr_gate": WP.DSR_MIN,
            "folds_for_sign_certifiability": cv_power.folds_for_sign_certifiability(WP.FDR_Q),
            "verdict": W2E.VERDICT_W2E,
            "reason": ("the mechanism can only act on capture-era rows, so the active-fold count "
                       "is a DESIGN quantity: no effect of any size could clear these gates. The "
                       "re-test trigger is calendar-bound — the capture era gains ~2 folds per "
                       "season of NF-W0a forward capture, so PBO becomes evaluable at 4 folds "
                       "(end of 2026)."),
            }


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W2e — is NF-W2d's 2025 attenuation caused by CAPTURE FRESHNESS?")
    p("")
    p(f"**Generated:** {out['generated_at']} · folds scored: {len(out['fold_labels'])} · "
      f"capture-era (ACTIVE) folds: {out['power_ceiling']['active_folds']} · rows "
      f"{out['n_rows']}")
    p("")
    p("> ⛔ **This study CERTIFIES NOTHING, by design.** `best_alpha = 0`, deploy-held. The "
      "consumption rule can only act on capture-era rows, so the active-fold count is a DESIGN "
      "quantity — see the power ceiling below. The primary read is a week-CLUSTERED row-level "
      "paired delta, never a fold-level gate.")
    p("")
    p("## Power ceiling (computed, not asserted)")
    p("")
    p("```json")
    p(json.dumps(out["power_ceiling"], indent=2, default=str))
    p("```")
    p("")
    p("## Controls")
    p("")
    for key, title in (("inertness", "Mechanical: the ladder is inert before 2025"),
                       ("population", "The scored population is identical across rungs"),
                       ("alignment", "Rows are aligned across rungs (paired deltas are valid)"),
                       ("measured_tie", "Measured: the rungs tie on the registered legacy folds")):
        c = out["controls"][key]
        p(f"- **{title}** — `{c.get('state')}` {json.dumps({k: v for k, v in c.items() if k not in ('state',)}, default=str)[:400]}")
    p("")
    p("## Stratifier validation (published BEFORE any lift — MH2.1)")
    p("")
    sv = out["stratifier_validation"]
    p(f"**{sv['state']}** — corrected rank corr {sv.get('corrected', {}).get('rank_corr')} "
      f"(p={sv.get('corrected', {}).get('rank_corr_p')}), "
      f"change rate {sv.get('corrected', {}).get('rate_at_or_below')} (≤1 d) vs "
      f"{sv.get('corrected', {}).get('rate_above')} (>1 d).")
    p("")
    p(f"⚠️ The FIRST cut read rank corr {sv.get('confounded_first_cut', {}).get('rank_corr')} "
      f"(p={sv.get('confounded_first_cut', {}).get('rank_corr_p')}) — an artifact: "
      f"{sv.get('confound')} ({sv.get('dropped_as_source_format_crossings')} pairs dropped).")
    p("")
    if sv.get("corrected", {}).get("by_bin"):
        p(pd.DataFrame(sv["corrected"]["by_bin"]).to_markdown(index=False))
        p("")
    p("## Carry-over census + ladder activity (NF-D20)")
    p("")
    p(f"{json.dumps(out['carryover'], default=str)}")
    p("")
    p(pd.DataFrame(out["ladder_activity"]).T.to_markdown())
    p("")
    p("## PRIMARY — week-clustered row-level paired deltas on the capture era")
    p("")
    p(f"Sign convention: **{out['capture_era']['sign_convention']}**.")
    p("")
    for arm, by_pos in out["capture_era"]["per_rung"].items():
        p(f"### `{arm}` vs `{W2E.INCUMBENT_RUNG}`")
        p("")
        rows = [{"position": k, **{kk: vv for kk, vv in v.items() if kk != "state"}}
                for k, v in by_pos.items()]
        p(pd.DataFrame(rows).to_markdown(index=False))
        p("")
    p("### Multiplicity over the 8 reported comparisons (a reading aid, never a gate)")
    p("")
    mp = out["multiplicity"]
    if mp.get("comparisons"):
        p(pd.DataFrame(mp["comparisons"]).to_markdown(index=False))
        p("")
        p(f"any comparison surviving BH q={mp['q']}: **{mp['any_survives']}**")
        p("")
    p("## SECONDARY — the pre-registered stratified read")
    p("")
    for pos, row in out["stratified"]["per_position"].items():
        p(f"- **{pos}**: " + " · ".join(
            f"{k} n={v['n']} Δ={v.get('mean_delta')} ±{v.get('clustered_se')}"
            for k, v in row.items()))
    p("")
    p("## ⭐ Cross-era stratum shares — can a freshness gradient explain the era gap?")
    p("")
    ess = out["era_stratum_shares"]
    p(f"**{ess.get('reading', ess.get('reason'))}**")
    p("")
    if ess.get("per_era"):
        p(pd.DataFrame(ess["per_era"]).T.to_markdown())
        p("")
    p(f"⚠️ {ess.get('caveat', '')}")
    p("")
    p("## Fold-level CRPS (reported, NEVER gated)")
    p("")
    p(pd.DataFrame(out["fold_table"]).to_markdown(index=False))
    p("")
    p("## Anchors")
    p("")
    p(f"{json.dumps(out['anchors'], indent=2, default=str)}")
    p("")
    p("## Verdict")
    p("")
    p(out["verdict_text"])
    p("")
    path.write_text("\n".join(a))


def _reanalyze(*, smoke: bool) -> int:
    """Recompute the READING AIDS from the stored artifact — no refit.

    Decision-inert by construction: the verdict is a registered CONSTANT and the controls,
    power ceiling and clustered reads are written through untouched (asserted below).

    Both aids are pure post-processing of things already fixed: the multiplicity note reads the
    stored clustered deltas, and the cross-era shares are a descriptive statistic over the
    incumbent matrix (a ~40 s rebuild, no model fitting, no selection). Neither can move a
    decision, which is why they are re-derivable rather than requiring the 17-minute refit.
    """
    suffix = "_smoke" if smoke else ""
    path = _REPORT_DIR / f"nf_w2e_capture_freshness{suffix}.json"
    if not path.exists():
        raise SystemExit(f"{path.name} absent — run the study before --reanalyze")
    out = json.loads(path.read_text())
    before = json.dumps({k: out[k] for k in ("verdict", "controls", "power_ceiling",
                                             "capture_era")}, sort_keys=True, default=str)
    out["multiplicity"] = multiplicity_note(out["capture_era"])
    out["verdict_text"] = compose_verdict_text(bool(out.get("run_valid")), out.get("controls", {}),
                                               out["capture_era"])
    try:
        rungs, _audits, _base = build_rungs()
        out["era_stratum_shares"] = era_stratum_shares(rungs[W2E.INCUMBENT_RUNG])
    except Exception as exc:  # noqa: BLE001 — an unevaluable aid is never scored healthy
        # NF1.7 (a): a check that could not run is UNEVALUABLE, never silently omitted (an
        # absent key would read downstream as "the cross-era comparison was not needed").
        log.warning("cross-era shares unevaluable during --reanalyze: %s", exc)
        out["era_stratum_shares"] = {"state": "UNEVALUABLE", "reason": str(exc)}
    out["reanalyzed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    after = json.dumps({k: out[k] for k in ("verdict", "controls", "power_ceiling",
                                            "capture_era")}, sort_keys=True, default=str)
    if before != after:
        raise SystemExit("--reanalyze moved a verdict/control — refusing to write")
    path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w2e_capture_freshness{suffix}.md")
    print(json.dumps({"verdict": out["verdict"],
                      "any_survives_bh": out["multiplicity"].get("any_survives")},
                     indent=2))
    return 0


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W2e capture-freshness mechanism study")
    ap.add_argument("--smoke", action="store_true",
                    help="the tie-control folds + the capture-era folds only, artifacts _smoke")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--reanalyze", action="store_true",
                    help="recompute the reading aids from the stored artifact (no refit). "
                         "Decision-inert: the verdict is a registered constant and the "
                         "controls are read back unchanged.")
    args = ap.parse_args(argv)

    if args.reanalyze:
        return _reanalyze(smoke=args.smoke)

    t0 = time.time()
    rungs, audits, store_raw = build_rungs()
    controls = {
        "inertness": W2E.assert_ladder_inert_before_2025(rungs),
        "population": W2E.assert_population_identical(rungs),
        "alignment": assert_rows_aligned(rungs),
    }
    base = rungs[W2E.INCUMBENT_RUNG]
    sv = stratifier_validation(store_raw, base)
    carry = carryover_census(base)
    activity = W2E.ladder_activity(rungs)
    log.info("controls: %s", {k: v["state"] for k, v in controls.items()})
    log.info("stratifier: %s | carry-over share %s", sv["state"], carry.get("superseded_share"))

    folds = W2.build_folds_w2(base, W2E.TEST_BLOCKS_W2E)
    capture_labels = {f"{s}H{h}" for s, h in W2E.CAPTURE_ERA_BLOCKS}
    extra = capture_labels | set(W2E.MEASURED_TIE_FOLDS)
    if args.smoke:
        folds = [f for f in folds if f.label in extra]
    log.info("scoring %d folds (%d carry the full ladder)", len(folds),
             sum(1 for f in folds if f.label in extra))

    fold_results = [run_fold(f, rungs, extra_rungs=f.label in extra) for f in folds]

    tie = measured_tie_control(fold_results)
    controls["measured_tie"] = tie
    valid = all(c.get("passes") for c in controls.values())

    fold_table = [{"fold": fr["label"], "n_test": fr["n_test"],
                   **{f"{arm}_{pos}": round(float(fr["scores"][arm][pos]), 4)
                      for arm in fr["scores"] if arm in (*W2E.LADDER_ARMS, W2E.FOIL_W2E)
                      for pos in ("RB",)}}
                  for fr in fold_results]
    anchors = {}
    for pos in WP.POSITIONS:
        mean = {arm: float(np.mean([fr["scores"][arm][pos] for fr in fold_results]))
                for arm in (W2E.INCUMBENT_RUNG, *W2E.ANCHORS_W2E)}
        anchors[pos] = {
            "nihilist_loses": bool(mean["nihilist_zero"] > mean[W2E.INCUMBENT_RUNG]),
            "pos_marginal_loses": bool(mean["pos_marginal"] > mean[W2E.INCUMBENT_RUNG]),
            "incumbent_respects_own_form_oracle": bool(
                mean[W2E.INCUMBENT_RUNG] > mean["oracle_avail__inj"]),
            "mean_crps": {k: round(v, 4) for k, v in mean.items()},
        }

    cap_reads = capture_era_reads(fold_results, rungs)
    strat = stratified_read(fold_results, rungs)
    ceiling = power_ceiling()

    verdict_text = compose_verdict_text(valid, controls, cap_reads)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W2e", "smoke": bool(args.smoke),
        "elapsed_seconds": round(time.time() - t0, 1),
        "n_rows": int(len(base)), "fold_labels": [f.label for f in folds],
        "run_valid": bool(valid),
        "verdict": {pos: W2E.VERDICT_W2E for pos in WP.POSITIONS},
        "verdict_text": verdict_text,
        "power_ceiling": ceiling,
        "controls": controls,
        "stratifier_validation": sv,
        "carryover": carry,
        "ladder_activity": activity,
        "pit_audits": audits,
        "capture_era": cap_reads,
        "multiplicity": multiplicity_note(cap_reads),
        "stratified": strat,
        "era_stratum_shares": era_stratum_shares(base),
        "anchors": anchors,
        "fold_table": fold_table,
        "preregistration": {
            "hypothesis": "NF-W2d's 2025 attenuation is caused by consuming designations a "
                          "fresher available capture has already superseded; restricting "
                          "consumption to fresher captures should recover lift. The competing "
                          "outcome (freshness costs volume) is registered as equally informative.",
            "ladder": [[n, ("freshest" if c is None else c)] for n, c in W2E.FRESHNESS_LADDER],
            "foil": W2E.FOIL_W2E, "anchors": list(W2E.ANCHORS_W2E),
            "arm_form": W2E.LADDER_FORM,
            "arm_form_justification_max_spread": W2E.ARM_INVARIANCE_MAX_SPREAD_AT_REGISTRATION,
            "validated_stratum_boundary_days": W2E.VALIDATED_STRATUM_BOUNDARY_DAYS,
            "coverage_max_age_days": W2D.COVERAGE_MAX_AGE_DAYS,
            "measured_tie_folds": list(W2E.MEASURED_TIE_FOLDS),
            "certifies_nothing": True,
            "deploy_held": "best_alpha=0; changes no incumbent, no construction, no serving",
        },
        "fold_results": [{"label": fr["label"], "scores": fr["scores"], "n_test": fr["n_test"],
                          "extra_rungs": fr["extra_rungs"]} for fr in fold_results],
    }
    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_w2e_capture_freshness{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_w2e_capture_freshness{suffix}.md")
    log.info("%s (%.1fs)", verdict_text[:200], out["elapsed_seconds"])
    print(json.dumps({"run_valid": valid, "verdict": W2E.VERDICT_W2E,
                      "controls": {k: v["state"] for k, v in controls.items()},
                      "stratifier": sv["state"],
                      "pooled": {arm: by.get("ALL", {}).get("mean_delta")
                                 for arm, by in cap_reads.get("per_rung", {}).items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
