"""run_nf_w2_injury_bakeoff.py — NF-W2 §0.5 bake-off: the availability channel (current-week
injury-report state) vs the NF-W1 champion as incumbent AND matched foil.

Everything decidable-in-advance lives as a CONSTANT in `weekly_projection_w2.py`; this runner
READS it and restates nothing (the NF-D16 discipline). The narrative pre-registration is
committed at `ablation_results/nf_w2_preregistration.md` BEFORE the full run.

PIPELINE: certified NF-W0 frame → NF-W1 feature engineering + the injury_report family
(admissible = date_modified < target gameday 00:00 UTC, fail-closed) → per-GAME PIT gate
(injury source records carry date_modified) → 12 gated folds (2019H1…2024H2, family ACTIVE on
all) + 2 SHADOW folds (2025 — family structurally unmeasured; expected near-tie, never gated)
→ 3 arms + the incumbent foil + 5 anchors through ONE reducer → per-position CRPS selection →
NF18 PBO + M14 DSR/FDR + cv_power fold-consistency → ship-or-null per position.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2_injury_bakeoff
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2_injury_bakeoff --smoke
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
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff import (  # noqa: E402
    load_sources_w1,
    score_qmat,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w0_audit import (  # noqa: E402
    _resolve_snap_identities,  # noqa: F401  (re-exported via load_sources_w1)
)

log = logging.getLogger("nfl.fantasy.nf_w2")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
SEASONS = (2016, 2025)

SCOREABLE = (W2.FOIL_W2, *W2.REAL_ARMS_W2, *W2.ANCHORS_W2)


def load_sources_w2(seasons: tuple[int, int]) -> dict[str, pd.DataFrame]:
    from quant_sports_intel_models.football.nfl.ingest.query_lake import q, delta
    src = load_sources_w1(seasons)
    lo, hi = seasons
    src["injuries"] = q(f"""
        select season, week, gsis_id, report_status, practice_status, date_modified
        from {delta('injuries')}
        where season between {lo} and {hi} and game_type = 'REG' and gsis_id is not null
    """)
    return src


def build_matrix(seasons: tuple[int, int], *, rebuild_cache: bool = False) -> tuple[pd.DataFrame, dict]:
    """Assemble (or reload) the W2 matrix. ⭐ THE PIT GATE RUNS ON EVERY BUILD, cache hit or not
    (the NF-C0e wired-≠-invoked shape, cache edition)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    key = W2.matrix_key_w2(seasons)
    cache = _ARTIFACTS / f"nf_w2_weekly_matrix_{key}.parquet"
    if cache.exists() and not rebuild_cache:
        log.info("matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        feat = pd.read_parquet(cache)
        feat["_inj_dm_utc"] = pd.to_datetime(feat["_inj_dm_utc"], utc=True, errors="coerce")
        audit = W2.run_pit_gate_w2(feat)
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
    modeled, audit = W2.assemble_matrix_w2(
        frame, src["stats"], src["snaps"], src["schedule"], src["injuries"]
    )
    modeled.to_parquet(cache, index=False)
    log.info("matrix cached → %s (%d rows; PIT: %d game-groups / %d records (%d injury) checked, "
             "%d rows dropped)", cache.name, len(modeled), audit["game_groups_checked"],
             audit["records_checked"], audit["injury_records_checked"], audit["rows_dropped"])
    return modeled, audit


# ── One fold: every arm + anchor through the shared reducer ─────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    train = feat.loc[fold.train_idx]
    test = feat.loc[fold.test_idx]
    t0 = time.time()
    base_feats = list(WP.FEATURES)
    inj_feats = list(W2.FEATURES_W2)

    # shared fits: base parts (the incumbent) + inj_both parts
    p0_base, cond_base = W2.hurdle_parts(train, test, base_feats, base_feats)
    p0_both, cond_both = W2.hurdle_parts(train, test, inj_feats, inj_feats)
    # injury family in the P(zero) leg ONLY — conditional leg SHARED with base (identical fit)
    p0_zero_leg, _ = W2.hurdle_parts(train, test, inj_feats, base_feats)
    # the surgical override on the base parts
    p0_ovr, ovr_meta = W2.override_p0(p0_base, train, test)
    # content-not-capacity permutation (train AND test values permuted within pos×gw)
    tr_perm = W2.permute_injury_within_pos_week(train)
    te_perm = W2.permute_injury_within_pos_week(test)
    p0_perm, cond_perm = W2.hurdle_parts(tr_perm, te_perm, inj_feats, inj_feats)
    # peeking availability oracles (per FORM — NF-D16)
    y_te = test["fantasy_points"].to_numpy(dtype=float)
    p0_oracle = (y_te == 0.0).astype(float)

    qmats: dict[str, np.ndarray] = {
        "base_hurdle": W2.mix_parts(p0_base, cond_base),
        "inj_both": W2.mix_parts(p0_both, cond_both),
        "inj_zero_leg": W2.mix_parts(p0_zero_leg, cond_base),
        "inj_override": W2.mix_parts(p0_ovr, cond_base),
        # anchors — diagnostic, never trials
        "nihilist_zero": WP.anchor_nihilist(test),
        "pos_marginal": WP.anchor_pos_marginal(train, test),
        "inj_permuted": W2.mix_parts(p0_perm, cond_perm),
        "oracle_avail__base": W2.mix_parts(p0_oracle, cond_base),
        "oracle_avail__inj": W2.mix_parts(p0_oracle, cond_both),
    }
    scores = {label: score_qmat(m, test) for label, m in qmats.items()}
    coverage = {label: {p: WP.interval_coverage(
        qmats[label][(test["position"] == p).to_numpy()],
        test.loc[test["position"] == p, "fantasy_points"].to_numpy(dtype=float))
        for p in WP.POSITIONS}
        for label in (W2.FOIL_W2, *W2.REAL_ARMS_W2)}
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
    winner = str(mean_crps[list(W2.REAL_ARMS_W2)].idxmin())
    deltas = (crps[W2.FOIL_W2] - crps[winner]).to_numpy(dtype=float)  # >0 = winner better
    beats_foil = bool(np.nanmean(deltas) > 0)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = [W2.FOIL_W2, *W2.REAL_ARMS_W2]
    defl = NF18.deflate(crps[eligible], subset=eligible)

    trial_srs = []
    for arm in W2.REAL_ARMS_W2:
        d = (crps[W2.FOIL_W2] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    # matched-pair attribution: every arm's per-fold delta vs the incumbent (NF-D10 — this IS
    # the attribution; the family must earn its keep as a paired delta, never a rank)
    pair_deltas = {
        arm: {
            "mean": round(float(np.nanmean((crps[W2.FOIL_W2] - crps[arm]).to_numpy())), 4),
            "fold_wins": int(((crps[W2.FOIL_W2] - crps[arm]) > 0).sum()),
        }
        for arm in W2.REAL_ARMS_W2
    }

    anchor_checks = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "pos_marginal_loses": bool(mean_crps["pos_marginal"] > mean_crps[winner]),
        # the permutation must NOT beat the incumbent — content, not capacity (NF-D10)
        "inj_permuted_does_not_beat_base": bool(
            mean_crps["inj_permuted"] >= mean_crps[W2.FOIL_W2]),
        # NF-D16 per-form floors: no arm may beat ITS OWN form's availability oracle
        "no_arm_beats_own_oracle": bool(all(
            mean_crps[arm] > mean_crps[W2.ORACLE_OF_FORM[arm]] for arm in W2.REAL_ARMS_W2)),
        "base_respects_oracle": bool(
            mean_crps[W2.FOIL_W2] > mean_crps[W2.ORACLE_OF_FORM[W2.FOIL_W2]]),
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
        "winner": winner, "foil": W2.FOIL_W2,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_crps.items()},
        "mean_mae_report_only": {
            label: round(float(np.mean([fr["scores"][label][f"mae_{pos}"] for fr in fold_results])), 4)
            for label in (winner, W2.FOIL_W2, "nihilist_zero")
        },
        "pair_deltas_vs_base": pair_deltas,
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "beats_foil": beats_foil, "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval,
        "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": None if observed_sr is None else round(observed_sr, 3),
        "var_trials_sr": None if var_trials is None else round(var_trials, 5),
        "anchors": anchor_checks, "coverage": coverage,
    }


def position_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": sel["beats_foil"],
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < WP.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= WP.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["nihilist_loses"]
                                 and sel["anchors"]["pos_marginal_loses"]),
        "permutation_behaves": bool(sel["anchors"]["inj_permuted_does_not_beat_base"]),
        "oracle_floors_respected": bool(sel["anchors"]["no_arm_beats_own_oracle"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}


def shadow_report(shadow_results: list[dict]) -> dict:
    """The 2025 mechanism-cannot-act check: every arm should sit ~on top of the incumbent."""
    out: dict = {}
    for pos in WP.POSITIONS:
        rows = {}
        for arm in W2.REAL_ARMS_W2:
            ds = [fr["scores"][W2.FOIL_W2][pos] - fr["scores"][arm][pos] for fr in shadow_results]
            rows[arm] = {"mean_delta_vs_base": round(float(np.mean(ds)), 4),
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
    p("# NF-W2 — the availability channel: current-week injury-report state (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **gated folds:** {out['n_folds']} half-season "
      f"blocks ({out['fold_labels'][0]}…{out['fold_labels'][-1]}; family ACTIVE on all) · "
      f"**shadow folds:** {', '.join(out['shadow_fold_labels']) or 'none'} (2025 — family "
      f"structurally unmeasured, never gated) · **modeled rows:** {out['n_rows']} · **label:** "
      f"`{out['evaluation_label_version']}` / `{out['scoring_system_id']}`")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      "Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects. The incumbent "
      "NF-W1 champion (`base_hurdle`) is simultaneously the MATCHED FOIL (NF-D10): each arm is "
      "the identical bundle plus the `injury_report` family, so the paired delta IS the "
      "attribution.")
    p("")
    p(f"**PIT gate (per-game as-of instants; injury source records carry `date_modified`):** "
      f"{out['pit_audit']['game_groups_checked']} game-groups / "
      f"{out['pit_audit']['records_checked']} records "
      f"({out['pit_audit']['injury_records_checked']} injury) checked; "
      f"{out['pit_audit']['rows_dropped']} rows in "
      f"{len(out['pit_audit']['groups_dropped'])} groups dropped fail-closed.")
    p("")
    p("## Per-position verdicts (gated folds)")
    p("")
    for pos in WP.POSITIONS:
        sel, gate = out["positions"][pos], out["gates"][pos]
        verdict = "SHIP" if gate["ship"] else f"NULL ({out['null_states'].get(pos, {}).get('state', 'n/a')})"
        p(f"### {pos} — **{verdict}**")
        p("")
        rows = [{"arm": k, "mean_crps": v} for k, v in sel["mean_crps"].items()]
        p(pd.DataFrame(rows).sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- winner `{sel['winner']}` vs incumbent `{sel['foil']}`: mean lift "
          f"{np.mean(sel['deltas_by_fold']):+.4f} CRPS, fold wins {sel['fold_wins']}/{out['n_folds']} "
          f"(clause requires {sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} "
          f"· p {sel['p_one_sided']} · FDR pass {gate['checks']['fdr_ok']}")
        p(f"- matched-pair deltas vs base (the attribution): {sel['pair_deltas_vs_base']}")
        p(f"- anchors: {sel['anchors']} · coverage(80) {sel['coverage']}")
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
    ap = argparse.ArgumentParser(description="NF-W2 availability-channel bake-off")
    ap.add_argument("--smoke", action="store_true",
                    help="last 2 gated folds + 1 shadow fold, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)

    feat, pit_audit = build_matrix(SEASONS, rebuild_cache=args.rebuild_cache)
    gated = W2.build_folds_w2(feat, W2.TEST_BLOCKS_W2)
    shadow = W2.build_folds_w2(feat, W2.SHADOW_BLOCKS_W2)
    if args.smoke:
        gated, shadow = gated[-2:], shadow[-1:]
    n_folds = len(gated)
    log.info("running %d gated + %d shadow folds over %d rows (%d arms + %d anchors)",
             n_folds, len(shadow), len(feat), len(W2.REAL_ARMS_W2) + 1, len(W2.ANCHORS_W2))

    fold_results = [run_fold(f, feat) for f in gated]
    shadow_results = [run_fold(f, feat) for f in shadow]

    positions = {pos: select_position(pos, fold_results, n_folds) for pos in WP.POSITIONS}
    pvals = {pos: positions[pos]["p_one_sided"] for pos in WP.POSITIONS}
    fdr = M14.bh_fdr(pvals, q=WP.FDR_Q)
    gates = {pos: position_gate(positions[pos], fdr[pos]) for pos in WP.POSITIONS}

    null_states: dict[str, dict] = {}
    for pos in WP.POSITIONS:
        if gates[pos]["ship"]:
            continue
        sel = positions[pos]
        v = cv_power.classify_null(
            metric=f"nf_w2_injury_crps_{pos}", n_folds=n_folds, n_arms=len(W2.REAL_ARMS_W2),
            beats_foil=sel["beats_foil"], observed_sr=sel["observed_sr"],
            var_trials_sr=sel["var_trials_sr"], fold_wins=sel["fold_wins"],
            p_one_sided=sel["p_one_sided"], bh_cutoff=WP.FDR_Q,
        )
        null_states[pos] = {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger}

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W2", "smoke": bool(args.smoke),
        "evaluation_label_version": WP.LABEL_VERSION,
        "scoring_system_id": WP.SCORING_SYSTEM_ID,
        "selection_metric": WP.SELECTION_METRIC,
        "n_rows": int(len(feat)), "n_folds": n_folds,
        "fold_labels": [f.label for f in gated],
        "shadow_fold_labels": [f.label for f in shadow],
        "pit_audit": pit_audit,
        "preregistration": {
            "hypothesis": "current-week injury-report state improves the weekly distribution, "
                          "primarily through the zero/availability leg (NF-W4 lean form)",
            "real_arms": list(W2.REAL_ARMS_W2), "foil": W2.FOIL_W2,
            "anchors": list(W2.ANCHORS_W2), "oracle_of_form": dict(W2.ORACLE_OF_FORM),
            "test_blocks": [list(t) for t in W2.TEST_BLOCKS_W2],
            "shadow_blocks": [list(t) for t in W2.SHADOW_BLOCKS_W2],
            "purge_weeks": WP.PURGE_WEEKS, "pbo_max": WP.PBO_MAX, "dsr_min": WP.DSR_MIN,
            "fdr_q": WP.FDR_Q, "coverage_floor": WP.COVERAGE_FLOOR,
            "injury_features": list(W2.INJURY_FEATURES),
            "injury_verified_max_season": W2.INJURY_VERIFIED_MAX_SEASON,
            "override_statuses": list(W2.OVERRIDE_STATUSES),
            "override_min_n": W2.OVERRIDE_MIN_N,
            "features": list(W2.FEATURES_W2),
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
    (_REPORT_DIR / f"nf_w2_injury_bakeoff{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_w2_injury_bakeoff{suffix}.md")
    log.info("verdict: %s", out["headline"])
    print(json.dumps({"verdict": verdicts, "headline": out["headline"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
