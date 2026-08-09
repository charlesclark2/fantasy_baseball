"""run_nf_w2b_injury_rate_bakeoff.py — NF-W2b §0.5 bake-off: the injury family re-registered
against a marginal-rate-carrying foil (`base_rate` = NF-W1 champion + week×position listing
rates), with the production incumbent (`base_noRate`) kept as the deployment-bar anchor.

Everything decidable-in-advance lives as a CONSTANT in `weekly_projection_w2b.py`; this runner
READS it and restates nothing (the NF-D16 discipline). The narrative pre-registration is
committed at `ablation_results/nf_w2b_preregistration.md` BEFORE the full run.

PIPELINE: certified NF-W0 frame → NF-W1 engineering + injury_report family (NF-W2, unchanged)
→ injury_rate family (group rates strictly before each row's OWN gameday instant) → per-GAME
PIT gate (window + injury + rate records) → 12 gated folds + 2 SHADOW folds → 3 arms + the
rate foil + 6 anchors through ONE reducer → per-position CRPS selection → NF18 PBO + M14
DSR/FDR + cv_power fold-consistency → ship-or-null per position, anchor-refusals
hand-classified CONSTRAINT_REFUSED (the NF-D18/MH2.7 classify_null gap).

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_injury_rate_bakeoff
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_injury_rate_bakeoff --smoke
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
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import (  # noqa: E402
    score_qmat,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2_injury_bakeoff import (  # noqa: E402
    load_sources_w2,
)

log = logging.getLogger("nfl.fantasy.nf_w2b")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
SEASONS = (2016, 2025)


def build_matrix_w2b(seasons: tuple[int, int], *, rebuild_cache: bool = False) -> tuple[pd.DataFrame, dict]:
    """Assemble (or reload) the W2b matrix. ⭐ THE PIT GATE RUNS ON EVERY BUILD, cache hit or
    not (the NF-C0e wired-≠-invoked shape, cache edition)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    key = W2B.matrix_key_w2b(seasons)
    cache = _ARTIFACTS / f"nf_w2b_weekly_matrix_{key}.parquet"
    if cache.exists() and not rebuild_cache:
        log.info("matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        feat = pd.read_parquet(cache)
        for c in ("_inj_dm_utc", "_rate_max_stamp_utc"):
            feat[c] = pd.to_datetime(feat[c], utc=True, errors="coerce")
        audit = W2B.run_pit_gate_w2b(feat)
        feat = feat.loc[audit.pop("kept_index")].reset_index(drop=True)
        return feat, audit

    src = load_sources_w2(seasons)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spine = WF.build_spine(src["rosters"], src["schedule"])
    frame = WF.attach_labels(
        spine, src["stats"],
        label_version=WP.LABEL_VERSION,
        label_as_of_timestamp=stamp,
        scoring_system_id=WP.SCORING_SYSTEM_ID,
        snaps=src["snaps"],
    )
    log.info("certified frame: %d rows (%d zeros retained)", len(frame), int(frame["is_zero"].sum()))
    modeled, audit = W2B.assemble_matrix_w2b(
        frame, src["stats"], src["snaps"], src["schedule"], src["injuries"]
    )
    modeled.to_parquet(cache, index=False)
    log.info("matrix cached → %s (%d rows; PIT: %d game-groups / %d records (%d injury, %d rate) "
             "checked, %d rows dropped)", cache.name, len(modeled), audit["game_groups_checked"],
             audit["records_checked"], audit["injury_records_checked"],
             audit["rate_records_checked"], audit["rows_dropped"])
    return modeled, audit


# ── One fold: every arm + anchor through the shared reducer ─────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    train = feat.loc[fold.train_idx]
    test = feat.loc[fold.test_idx]
    t0 = time.time()
    norate_feats = list(WP.FEATURES)
    rate_feats = list(W2B.FEATURES_BASE_RATE)
    full_feats = list(W2B.FEATURES_W2B)

    # shared fits: the rate foil, the full-bundle arm, the production incumbent
    p0_rate, cond_rate = W2.hurdle_parts(train, test, rate_feats, rate_feats)
    p0_both, cond_both = W2.hurdle_parts(train, test, full_feats, full_feats)
    p0_norate, cond_norate = W2.hurdle_parts(train, test, norate_feats, norate_feats)
    # player injury family in the P(zero) leg ONLY — conditional leg SHARED with base_rate
    p0_zero_leg, _ = W2.hurdle_parts(train, test, full_feats, rate_feats)
    # the surgical override on the rate foil's parts
    p0_ovr, ovr_meta = W2.override_p0(p0_rate, train, test)
    # content-not-capacity permutation: PLAYER injury columns permuted within pos×gw in train
    # AND test; the rate columns are untouched (they are the foil's, group-level)
    tr_perm = W2.permute_injury_within_pos_week(train)
    te_perm = W2.permute_injury_within_pos_week(test)
    p0_perm, cond_perm = W2.hurdle_parts(tr_perm, te_perm, full_feats, full_feats)
    # peeking availability oracles (per FORM — NF-D16)
    y_te = test["fantasy_points"].to_numpy(dtype=float)
    p0_oracle = (y_te == 0.0).astype(float)

    qmats: dict[str, np.ndarray] = {
        "base_rate": W2.mix_parts(p0_rate, cond_rate),
        "inj_both": W2.mix_parts(p0_both, cond_both),
        "inj_zero_leg": W2.mix_parts(p0_zero_leg, cond_rate),
        "inj_override": W2.mix_parts(p0_ovr, cond_rate),
        # anchors — diagnostic, never trials
        "nihilist_zero": WP.anchor_nihilist(test),
        "pos_marginal": WP.anchor_pos_marginal(train, test),
        "base_noRate": W2.mix_parts(p0_norate, cond_norate),
        "inj_permuted": W2.mix_parts(p0_perm, cond_perm),
        "oracle_avail__base": W2.mix_parts(p0_oracle, cond_rate),
        "oracle_avail__inj": W2.mix_parts(p0_oracle, cond_both),
    }
    scores = {label: score_qmat(m, test) for label, m in qmats.items()}
    coverage = {label: {p: WP.interval_coverage(
        qmats[label][(test["position"] == p).to_numpy()],
        test.loc[test["position"] == p, "fantasy_points"].to_numpy(dtype=float))
        for p in WP.POSITIONS}
        for label in (W2B.FOIL_W2B, *W2B.REAL_ARMS_W2B)}
    activity = W2.fold_activity(test)
    log.info("fold %s scored in %.1fs (train %d / test %d; listed %s, out∪dbtf %s)",
             fold.label, time.time() - t0, len(train), len(test),
             activity["listed_share"], activity["out_doubtful_share"])
    return {"label": fold.label, "scores": scores, "coverage": coverage, "activity": activity,
            "override_meta": ovr_meta, "n_train": int(len(train)), "n_test": int(len(test))}


# ── Selection + deflation per position (gated folds only) ───────────────────────────────────────
def select_position(pos: str, fold_results: list[dict], n_folds: int) -> dict:
    crps = pd.DataFrame({
        fr["label"]: {label: fr["scores"][label][pos] for label in fr["scores"]}
        for fr in fold_results
    }).T  # rows = folds, cols = labels

    mean_crps = crps.mean(axis=0)
    winner = str(mean_crps[list(W2B.REAL_ARMS_W2B)].idxmin())
    deltas = (crps[W2B.FOIL_W2B] - crps[winner]).to_numpy(dtype=float)  # >0 = winner better
    beats_foil = bool(np.nanmean(deltas) > 0)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = [W2B.FOIL_W2B, *W2B.REAL_ARMS_W2B]
    defl = NF18.deflate(crps[eligible], subset=eligible)

    trial_srs = []
    for arm in W2B.REAL_ARMS_W2B:
        d = (crps[W2B.FOIL_W2B] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    # matched-pair attribution vs the RATE foil (NF-D10 — this IS the pure player-level
    # attribution; the marginal channel lives in the foil by construction)
    pair_deltas = {
        arm: {
            "mean": round(float(np.nanmean((crps[W2B.FOIL_W2B] - crps[arm]).to_numpy())), 4),
            "fold_wins": int(((crps[W2B.FOIL_W2B] - crps[arm]) > 0).sum()),
        }
        for arm in W2B.REAL_ARMS_W2B
    }

    # the deployment bar + the three-way decomposition:
    #   winner − base_noRate (total vs production) =
    #   (base_noRate − base_rate reversed: the marginal channel) + (winner − base_rate: content)
    prod_deltas = (crps[W2B.PROD_INCUMBENT] - crps[winner]).to_numpy(dtype=float)
    beats_production = bool(np.nanmean(prod_deltas) > 0)
    marginal_channel = (crps[W2B.PROD_INCUMBENT] - crps[W2B.FOIL_W2B]).to_numpy(dtype=float)
    decomposition = {
        "winner_vs_production_mean": round(float(np.nanmean(prod_deltas)), 4),
        "winner_vs_production_fold_wins": int((prod_deltas > 0).sum()),
        "marginal_channel_mean": round(float(np.nanmean(marginal_channel)), 4),
        "marginal_channel_p_one_sided": M14.onesided_paired_pvalue(marginal_channel),
        "player_content_mean": round(float(np.nanmean(deltas)), 4),
    }

    # the calibrated permutation pair — now vs the RATE foil (⭐ the registered fix):
    # (1) content check — the winner must beat the capacity foil (permuted) on the mean;
    # (2) capacity sanity — permuted's lift over base_rate must be non-positive or
    #     non-significant (a strict binary on tied means is a ~50% false-veto — NF1.8/MH2-H8).
    perm_lift = (crps[W2B.FOIL_W2B] - crps["inj_permuted"]).to_numpy(dtype=float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    winner_vs_perm = float(np.nanmean(
        (crps["inj_permuted"] - crps[winner]).to_numpy(dtype=float)))
    anchor_checks = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "pos_marginal_loses": bool(mean_crps["pos_marginal"] > mean_crps[winner]),
        "winner_beats_permuted": bool(winner_vs_perm > 0),
        # an unevaluable p (< 3 folds — smoke only) FAILS closed, never passes (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        # NF-D16 per-form floors: no arm may beat ITS OWN form's availability oracle
        "no_arm_beats_own_oracle": bool(all(
            mean_crps[arm] > mean_crps[W2B.ORACLE_OF_FORM_W2B[arm]]
            for arm in W2B.REAL_ARMS_W2B)),
        "foil_respects_oracle": bool(
            mean_crps[W2B.FOIL_W2B] > mean_crps[W2B.ORACLE_OF_FORM_W2B[W2B.FOIL_W2B]]),
    }
    permutation_detail = {
        "permuted_lift_vs_base_rate_mean": round(float(np.nanmean(perm_lift)), 4),
        "permuted_lift_p_one_sided": p_perm,
        "winner_vs_permuted_mean": round(winner_vs_perm, 4),
    }

    covs = [fr["coverage"][winner][pos] for fr in fold_results]
    n_total = sum(c["n"] for c in covs)
    cov_pooled = (sum(c["coverage"] * c["n"] for c in covs) / n_total) if n_total else float("nan")
    se = float(np.sqrt(WP.COVERAGE_FLOOR * (1 - WP.COVERAGE_FLOOR) / n_total)) if n_total else float("nan")
    coverage = {
        "winner_coverage_80": round(cov_pooled, 4), "n_rows": n_total, "binomial_se": round(se, 4),
        "blocking_shortfall": bool(n_total and (0.80 - cov_pooled) > WP.COVERAGE_BLOCK_SE * se),
    }

    sd = float(np.nanstd(deltas, ddof=1))
    observed_sr = float(np.nanmean(deltas)) / sd if sd > 1e-12 else None
    var_trials = float(np.var(np.asarray(trial_srs), ddof=1)) if len(trial_srs) > 1 else None

    return {
        "winner": winner, "foil": W2B.FOIL_W2B, "production_incumbent": W2B.PROD_INCUMBENT,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_crps.items()},
        "mean_mae_report_only": {
            label: round(float(np.mean([fr["scores"][label][f"mae_{pos}"] for fr in fold_results])), 4)
            for label in (winner, W2B.FOIL_W2B, W2B.PROD_INCUMBENT, "nihilist_zero")
        },
        "pair_deltas_vs_base_rate": pair_deltas,
        "decomposition": decomposition,
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "beats_foil": beats_foil, "beats_production": beats_production, "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval,
        "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": None if observed_sr is None else round(observed_sr, 3),
        "var_trials_sr": None if var_trials is None else round(var_trials, 5),
        "anchors": anchor_checks, "permutation_detail": permutation_detail,
        "coverage": coverage,
    }


def shadow_report(shadow_results: list[dict]) -> dict:
    """The 2025 mechanism-cannot-act check: every arm should sit ~on top of the rate foil (and
    the rate foil ~on top of the production incumbent — its rate features are dark too)."""
    out: dict = {}
    for pos in WP.POSITIONS:
        rows = {}
        for arm in (*W2B.REAL_ARMS_W2B, W2B.FOIL_W2B):
            ref = W2B.FOIL_W2B if arm != W2B.FOIL_W2B else W2B.PROD_INCUMBENT
            ds = [fr["scores"][ref][pos] - fr["scores"][arm][pos] for fr in shadow_results]
            rows[arm] = {"vs": ref, "mean_delta": round(float(np.mean(ds)), 4),
                         "max_abs_delta": round(float(np.max(np.abs(ds))), 4)}
        out[pos] = rows
    out["activity"] = [
        {"fold": fr["label"], **fr["activity"]} for fr in shadow_results
    ]
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W2b — the injury family re-registered against a marginal-rate-carrying foil "
      "(§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **gated folds:** {out['n_folds']} half-season "
      f"blocks ({out['fold_labels'][0]}…{out['fold_labels'][-1]}; family ACTIVE on all) · "
      f"**shadow folds:** {', '.join(out['shadow_fold_labels']) or 'none'} (2025 — both "
      f"families structurally unmeasured, never gated) · **modeled rows:** {out['n_rows']} · "
      f"**label:** `{out['evaluation_label_version']}` / `{out['scoring_system_id']}`")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      "Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. The matched "
      "foil is `base_rate` (NF-W1 champion + pre-registered week×position listing-rate "
      "features): each arm is the identical bundle plus the PLAYER-level `injury_report` "
      "family, so the paired delta vs `base_rate` IS the pure player-level attribution "
      "(NF-D10). `base_noRate` (the production incumbent) anchors the deployment bar.")
    p("")
    p(f"**PIT gate (per-game as-of instants; window + injury + rate records):** "
      f"{out['pit_audit']['game_groups_checked']} game-groups / "
      f"{out['pit_audit']['records_checked']} records "
      f"({out['pit_audit']['injury_records_checked']} injury, "
      f"{out['pit_audit']['rate_records_checked']} rate) checked; "
      f"{out['pit_audit']['rows_dropped']} rows in "
      f"{len(out['pit_audit']['groups_dropped'])} groups dropped fail-closed.")
    p("")
    p("## Per-position verdicts (gated folds)")
    p("")
    for pos in WP.POSITIONS:
        sel, gate = out["positions"][pos], out["gates"][pos]
        verdict = ("SHIP" if gate["ship"]
                   else f"NULL ({out['null_states'].get(pos, {}).get('state', 'n/a')})")
        if pos == "TE":
            verdict += " — consistency check; the NF-W2 TE ship stands regardless"
        p(f"### {pos} — **{verdict}**")
        p("")
        rows = [{"arm": k, "mean_crps": v} for k, v in sel["mean_crps"].items()]
        p(pd.DataFrame(rows).sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- winner `{sel['winner']}` vs rate foil `{sel['foil']}`: mean lift "
          f"{np.mean(sel['deltas_by_fold']):+.4f} CRPS, fold wins {sel['fold_wins']}/{out['n_folds']} "
          f"(clause requires {sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} "
          f"· p {sel['p_one_sided']} · FDR pass {gate['checks']['fdr_ok']}")
        p(f"- pure player-level attribution (vs `base_rate`): {sel['pair_deltas_vs_base_rate']}")
        p(f"- decomposition (vs production `base_noRate`): {sel['decomposition']}")
        p(f"- anchors: {sel['anchors']} · permutation detail {sel['permutation_detail']} · "
          f"coverage(80) {sel['coverage']}")
        p(f"- MAE (report-only): {sel['mean_mae_report_only']}")
        p("")
    p("## Per-fold family activity (the NF-D20 discipline)")
    p("")
    p(pd.DataFrame(out["fold_activity"]).to_markdown(index=False))
    p("")
    p("## Shadow 2025 (mechanism cannot act — registered expectation: near-tie)")
    p("")
    p("```json")
    p(json.dumps(out["shadow"], indent=2, default=str))
    p("```")
    p("")
    p("## Gate detail")
    p("")
    p("```json")
    p(json.dumps(out["gates"], indent=2, default=str))
    p("```")
    p("")
    p("## Null-state classification (failing positions)")
    p("")
    p("```json")
    p(json.dumps(out["null_states"], indent=2, default=str))
    p("```")
    p("")
    path.write_text("\n".join(a))


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W2b injury-vs-rate-foil bake-off")
    ap.add_argument("--smoke", action="store_true",
                    help="last 2 gated folds + 1 shadow fold, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)

    feat, pit_audit = build_matrix_w2b(SEASONS, rebuild_cache=args.rebuild_cache)
    gated = W2.build_folds_w2(feat, W2B.TEST_BLOCKS_W2B)
    shadow = W2.build_folds_w2(feat, W2B.SHADOW_BLOCKS_W2B)
    if args.smoke:
        gated, shadow = gated[-2:], shadow[-1:]
    n_folds = len(gated)
    log.info("running %d gated + %d shadow folds over %d rows (%d arms + foil + %d anchors)",
             n_folds, len(shadow), len(feat), len(W2B.REAL_ARMS_W2B), len(W2B.ANCHORS_W2B))

    fold_results = [run_fold(f, feat) for f in gated]
    shadow_results = [run_fold(f, feat) for f in shadow]

    positions = {pos: select_position(pos, fold_results, n_folds) for pos in WP.POSITIONS}
    pvals = {pos: positions[pos]["p_one_sided"] for pos in WP.POSITIONS}
    fdr = M14.bh_fdr(pvals, q=WP.FDR_Q)
    gates = {pos: W2B.position_gate_w2b(positions[pos], fdr[pos]) for pos in WP.POSITIONS}

    null_states: dict[str, dict] = {}
    for pos in WP.POSITIONS:
        if gates[pos]["ship"]:
            continue
        sel = positions[pos]
        # ⭐ the hand-check classify_null cannot do (NF-D18/MH2.7, hit twice): an
        # anchor/registration refusal with green statistical gates is CONSTRAINT_REFUSED —
        # never POWER_LIMITED, never a sample-size re-test trigger.
        hand = W2B.hand_classify_refusal(gates[pos]["checks"])
        machine = cv_power.classify_null(
            metric=f"nf_w2b_injury_crps_{pos}", n_folds=n_folds, n_arms=len(W2B.REAL_ARMS_W2B),
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

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W2b", "smoke": bool(args.smoke),
        "evaluation_label_version": WP.LABEL_VERSION,
        "scoring_system_id": WP.SCORING_SYSTEM_ID,
        "selection_metric": WP.SELECTION_METRIC,
        "n_rows": int(len(feat)), "n_folds": n_folds,
        "fold_labels": [f.label for f in gated],
        "shadow_fold_labels": [f.label for f in shadow],
        "pit_audit": pit_audit,
        "preregistration": {
            "hypothesis": "absorbing the week×position marginal-listing-rate channel into the "
                          "base foil isolates pure player-level injury content; the family "
                          "beats that stronger foil and the calibrated permutation clause is "
                          "satisfiable by construction (NF-W2 §7 successor)",
            "real_arms": list(W2B.REAL_ARMS_W2B), "foil": W2B.FOIL_W2B,
            "production_incumbent": W2B.PROD_INCUMBENT,
            "anchors": list(W2B.ANCHORS_W2B), "oracle_of_form": dict(W2B.ORACLE_OF_FORM_W2B),
            "test_blocks": [list(t) for t in W2B.TEST_BLOCKS_W2B],
            "shadow_blocks": [list(t) for t in W2B.SHADOW_BLOCKS_W2B],
            "purge_weeks": WP.PURGE_WEEKS, "pbo_max": WP.PBO_MAX, "dsr_min": WP.DSR_MIN,
            "fdr_q": WP.FDR_Q, "coverage_floor": WP.COVERAGE_FLOOR,
            "rate_features": list(W2B.RATE_FEATURES),
            "injury_features": list(W2.INJURY_FEATURES),
            "injury_verified_max_season": W2.INJURY_VERIFIED_MAX_SEASON,
            "override_statuses": list(W2.OVERRIDE_STATUSES),
            "override_min_n": W2.OVERRIDE_MIN_N,
            "features": list(W2B.FEATURES_W2B),
            "te_scope": "consistency check only — the NF-W2 TE ship stands regardless; a pass "
                        "here makes a unified rate-augmented TE spec AVAILABLE (operator, NF-G0)",
        },
        "positions": positions, "gates": gates, "fdr": fdr, "null_states": null_states,
        "fold_activity": [{"fold": fr["label"], **fr["activity"],
                           "override": fr["override_meta"]} for fr in fold_results],
        "shadow": shadow_report(shadow_results) if shadow_results else {},
        "fold_results": [{k: fr[k] for k in ("label", "scores", "n_train", "n_test")}
                         for fr in fold_results + shadow_results],
    }
    verdicts = {pos: ("SHIP" if gates[pos]["ship"] else null_states.get(pos, {}).get("state", "NULL"))
                for pos in WP.POSITIONS}
    out["verdict"] = verdicts
    out["headline"] = " · ".join(f"{pos}:{v}" for pos, v in verdicts.items())

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_w2b_injury_rate_bakeoff{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_w2b_injury_rate_bakeoff{suffix}.md")
    log.info("verdict: %s", out["headline"])
    print(json.dumps({"verdict": verdicts, "headline": out["headline"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
