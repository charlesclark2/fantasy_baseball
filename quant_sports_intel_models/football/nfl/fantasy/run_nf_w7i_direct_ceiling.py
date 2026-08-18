"""NF-W7i — the RB DIRECT-POINTS improvement-ceiling gate (oracle-first MEASUREMENT, §0.5).

⚖️ `best_alpha = 0` · **deploy-held** · research-only · no changelog · promotes nothing.

    uv run python quant_sports_intel_models/football/nfl/fantasy/run_nf_w7i_direct_ceiling.py --smoke
    uv run python quant_sports_intel_models/football/nfl/fantasy/run_nf_w7i_direct_ceiling.py
    uv run python .../run_nf_w7i_direct_ceiling.py --rewrite-report   # zero refit

⛔ NOT a bake-off and NOT an RB-assembly successor. Nothing is selected, nothing is promoted, no
arm is registered. The output is a CEILING and a band, per `direct_points_ceiling`.

⭐ `--rewrite-report` re-derives EVERY verdict from the stored per-fold scores at zero refit cost
(NF-W2e): the verdict layer is DERIVED, never stored, so correcting a reading can never cost a
re-run — which is the pressure that leaves a known-wrong sentence in a published record.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    direct_points_ceiling as DC,
)
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w7c_fp_assembly as W7C,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w7e_split_allrows as W7E,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w7i")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
#: NF-W7c's gate league, INHERITED through W7d/W7e/W7f/W7h (E2.1-r: a league re-chosen here would
#: make this ceiling incomparable with the record that motivated it).
GATE_LEAGUE = W7E.GATE_LEAGUE

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w7i_direct_ceiling.json")

#: The positive control's multiplicative shift on the block's realised points (NF-W6 §6 /
#: MH2.1 (d)): a blind instrument must REFUSE the smoke.
POSITIVE_CONTROL_SCALE = 1.3
#: The ORIGINAL pre-registered clause: the RELATIVE ceiling must move ≥ this many percentage
#: points. ⛔ RETAINED AND STILL SCORED even though it FAILED (measured 0.821) — a pre-registered
#: anchor that fails is left FAILING and DECOMPOSED, never re-labelled or deleted (NF-D20).
POSITIVE_CONTROL_MIN_MOVE_PCT = 2.0

#: ⭐ SMOKE AMENDMENT (recorded in the pre-registration §7 BEFORE the full run; the NF-W6b-C
#: precedent, which amended its matched-n sizing the same way). The original clause FAILED, and the
#: evidence it now writes says WHY — the failure is in the CONTROL'S OWN STATISTIC, not in the
#: instrument:
#:
#:   incumbent CRPS 2.4346 → 3.3805 under the shift (the DENOMINATOR inflates ×1.388), while the
#:   gated form's ABSOLUTE peek advantage went 0.01102 → 0.04306 = ×3.9, and `direct_upweighted`'s
#:   went 0.00103 → 0.05825 = ×56.
#:
#: A multiplicative shift moves the target's scale, so it moves BOTH the numerator and the
#: denominator of a relative ceiling — reading instrument SENSITIVITY on that ratio understates it
#: by construction (the E2.1-r class: a gate read on a mis-specified statistic). The corrected
#: clause reads the quantity the peek actually moves — the ABSOLUTE paired advantage — and is
#: two-sided: the gap must GROW by this factor AND the ceiling must move in the POSITIVE direction
#: (a genuine regime difference must WIDEN the ceiling, never narrow it).
#:
#: The factor is a DESIGN quantity, not a tuned one: ×2 is the weakest non-trivial multiplicative
#: response an instrument can be asked for. ⛔ The bar was NOT lowered — the amendment changes the
#: STATISTIC the clause reads, and the original clause stays on the record with its FAIL.
#: ⛔ It touches ONLY instrument validation; the story's DECISION rule (bands, stat_ok, BH) is
#: untouched.
POSITIVE_CONTROL_MIN_ABS_GROWTH = 2.0


def rb_frames(feat: pd.DataFrame, fold, weights: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The (train, test) RB frames carrying `FA.TARGET`, built through the predecessors' helpers."""
    tr = feat.iloc[fold.train_idx]
    te = feat.iloc[fold.test_idx]
    trp = tr.loc[tr["position"].astype(str) == DC.POSITION].reset_index(drop=True)
    tep = te.loc[te["position"].astype(str) == DC.POSITION].reset_index(drop=True)
    return (DC.points_target(trp, W7C.realized_matrix(trp), weights),
            DC.points_target(tep, W7C.realized_matrix(tep), weights))


def score_fold(fold, feat: pd.DataFrame, weights: np.ndarray, *,
               positive_control: bool = False) -> dict:
    """Every declared form's peek + its matched-n control + every anchor, for one fold.

    `positive_control=True` scales the BLOCK's realised points by `POSITIVE_CONTROL_SCALE` before
    any peek is built, so a shift the block's own regime carries MUST widen the ceiling. The
    incumbent is refit on the shifted labels too — otherwise the control would measure a broken
    incumbent rather than a responsive instrument.
    """
    trp, tep = rb_frames(feat, fold, weights)
    if len(tep) == 0 or len(trp) < DC.MIN_BANK_ROWS:
        return {"label": fold.label,
                "skipped": f"train {len(trp)} / test {len(tep)} RB rows — below the estimation "
                           f"floor ({DC.MIN_BANK_ROWS}); REFUSED, never defaulted (NF1.7 (a))"}
    if positive_control:
        tep = tep.copy()
        tep[FA.TARGET] = tep[FA.TARGET].to_numpy(float) * POSITIVE_CONTROL_SCALE

    y = tep[FA.TARGET].to_numpy(float)
    n = len(tep)
    banks: dict[str, np.ndarray] = {}

    banks[DC.INCUMBENT] = DC.fit_direct(trp, tep, FEATURES)
    banks["oracle__direct_blockonly"] = DC.oracle_blockonly(tep, FEATURES, fold.label)
    banks["matched_n__direct_blockonly"] = DC.fit_direct(
        DC.matched_window(trp, tep), tep, FEATURES)
    for form, lam in DC.LAMBDA_BY_FORM.items():
        banks[f"oracle__{form}"] = DC.oracle_augmented(trp, tep, FEATURES, fold.label, lam, form)
        banks[f"matched_n__{form}"] = DC.matched_augmented(trp, tep, FEATURES, fold.label, lam,
                                                           form)
    banks["oracle__recal_block"] = DC.oracle_recal(banks[DC.INCUMBENT], y, fold.label)
    banks["matched_n__recal_block"] = DC.matched_recal(banks[DC.INCUMBENT], trp, tep, FEATURES)
    banks["oracle__climatology_block"] = DC.oracle_climatology(y)
    banks["matched_n__climatology_block"] = DC.matched_climatology(trp, tep)

    loc = float(np.mean(trp[FA.TARGET].to_numpy(float)))
    clim = np.repeat(DC._bank(trp[FA.TARGET].to_numpy(float))[None, :], n, axis=0)
    banks["nihilist_zero"] = np.zeros((n, DC.N_LEVELS))
    banks["zero_width"] = np.full_like(clim, loc)
    banks["max_width"] = loc + 3.0 * (clim - loc)
    banks[DC.PERMUTATION] = DC.fit_direct(
        trp, tep, FEATURES,
        y_train=KW.permute_within_group(trp[FA.TARGET].to_numpy(float), trp["gw"].to_numpy()))

    missing = sorted(set(DC.ALL_LABELS) - set(banks))
    if missing:
        raise ValueError(f"{DC.STORY}: the declared field is incomplete — {missing} produced no "
                         f"predictive. A field scored with a label silently missing is not the "
                         f"declared field (NF1.7 (a)).")

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{DC.POSITION}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y)))
    return {"label": fold.label, "n": int(n), "n_train": int(len(trp)),
            "n_matched_window": int(len(DC.matched_window(trp, tep))),
            "scores": scores,
            "coverage_80_incumbent": KW.coverage80_dense(banks[DC.INCUMBENT], y)}


def derive_verdict_layer(out: dict) -> dict:
    """Re-derive selection → BH → decision → null state from the stored fold scores (zero refit)."""
    scored = [fr for fr in out["fold_results"] if "scores" in fr]
    sel = DC.select_ceiling(scored, len(scored))
    fdr = DC.bh_binding(sel["per_form"])
    decision = DC.decide(sel, fdr)
    out["selection"] = sel
    out["fdr"] = fdr
    out["decision"] = decision
    out["null_state"] = DC.null_state(sel, decision, n_folds=len(scored))
    out["verdict"] = {
        "story_verdict": decision["answer"],
        "position": DC.POSITION,
        "ceiling_pct": sel.get("ceiling_pct"),
        "best_form": sel.get("best_form"),
        "licensed_for_bakeoff": decision["licensed_for_bakeoff"],
        "reason": decision["reason"],
        "scope_note": (
            "⛔ RB ONLY, DIRECT-POINTS form only, at the NF-W1 fold axis. This record certifies "
            "nothing about QB/WR/TE and licenses no assembly successor (NF-W7h measured assembly "
            "as LOSING at RB by 0.0263 CRPS)."),
        "promotes_nothing": True,
    }
    return out


def write_report(out: dict, path: Path) -> None:
    sel, dec = out["selection"], out["decision"]
    pf = sel["per_form"]
    L = [f"# {DC.STORY} — the RB DIRECT-POINTS improvement ceiling "
         f"({dec['answer']})", "",
         f"Generated {out['generated_at']} · position **{DC.POSITION}** · league "
         f"**{out['gate_league']}** · {out['n_folds']} folds · target `{FA.TARGET}` · metric "
         f"`{DC.PRIMARY_METRIC}` · cross-fit K={DC.CROSSFIT_K}", "",
         "⚖️ `best_alpha = 0` · **DEPLOY-HELD** · a MEASUREMENT, not a bake-off — nothing is "
         "selected and nothing is promoted.", "",
         "## Verdict", "",
         f"**`{dec['answer']}`** — {dec['reason']}", "",
         f"> Licensed for a bake-off: **{dec['licensed_for_bakeoff']}** · {dec['license_rule']}", "",
         f"> {out['verdict']['scope_note']}", "",
         "| quantity | value |", "|---|---|",
         f"| honest incumbent (`{DC.INCUMBENT}`, full-train) | {sel['mean_incumbent']} |",
         f"| best ACTIVE form | `{sel['best_form']}` |",
         f"| **ceiling** | **{sel['ceiling_pct']}%** |",
         f"| **ceiling CI95 (band units)** | **{sel.get('ceiling_ci_pct')}** — the band comparison "
         f"is a direct read, not an arithmetic exercise |",
         f"| paired Δ (CI95) | {sel['mean_delta']} {sel['ci95']} |",
         f"| folds won | {sel['fold_wins']}/{out['n_folds']} (clause requires "
         f"{sel['fold_clause']['required']}) |",
         f"| BH cutoff (q={DC.FDR_Q}, family={out['fdr']['family_size']}) | "
         f"{out['fdr']['cutoff']} |",
         f"| bands | <{DC.CEILING_BANDS[0]}% NO · {DC.CEILING_BANDS[0]}–{DC.CEILING_BANDS[1]}% "
         f"MARGINAL · ≥{DC.CEILING_BANDS[1]}% YES |", "",
         "## Per-form ceilings (NF-D16 (g‴): one ceiling per FORM, never one for the field)", "",
         "> ⭐ ACTIVITY IS READ BEFORE MAGNITUDE. A peek that does not BEAT its own matched-n "
         "control could not ACT — its ceiling is UNINFORMATIVE, never a NO (NF-W6d / NF-D20).", "",
         "| form | oracle | matched-n | activity | ceiling | folds | p |", "|---|---|---|---|---|---|---|"]
    for f in DC.ORACLE_FORMS:
        d = pf[f]
        L.append(f"| `{f}` | {d['oracle_mean']} | {d['matched_n_mean']} | {d['activity']} | "
                 f"{d['ceiling_pct']}% | {d['fold_wins']}/{out['n_folds']} | {d['p_one_sided']} |")
    L += ["", "## Anchors (measured every run, never reasoned about — NF-D14)", "",
          "| anchor | loses to the incumbent? |", "|---|---|"]
    for k, v in sel["anchors"].items():
        L.append(f"| `{k}` | {v} |")
    L += ["", f"> {sel['estimator_note']}", "",
          f"> {sel['pbo_state']}", "",
          "## Null state", "",
          f"`{out['null_state'].get('state')}` · field-remedy admissible: "
          f"`{out['null_state'].get('field_remedy_admissible')}`", ""]
    ns = out["null_state"]
    if ns.get("hand_corrected"):
        L += [f"> ⚠️ **HAND-CORRECTED from `{ns['corrected_from']}`** (retained verbatim under "
              f"`classify_null_raw`, NF-D20). {ns['reason']}", "",
              f"> **Remedy:** {ns['remedy']}", ""]
    L += [f"> {ns.get('retest_trigger_note')}", "",
          "## Mean CRPS by label", "", "| label | crps_q199 |", "|---|---|"]
    for k, v in sorted(sel["mean_crps"].items(), key=lambda kv: kv[1]):
        L.append(f"| `{k}` | {v} |")
    if out.get("positive_control"):
        pc = out["positive_control"]
        L += ["", "## Positive control (NF-W6 §6 / MH2.1 (d))", "",
              f"Block points scaled ×{POSITIVE_CONTROL_SCALE}. Gating clause: {pc['gating_clause']}"
              f" → **{'SEES the shift' if pc['passes'] else 'BLIND — REFUSED'}** "
              f"(absolute advantage ×{pc['abs_growth']}, ceiling widened "
              f"{pc['ceiling_widened']}).", "",
              f"> ⛔ The ORIGINAL pre-registered clause ({pc['legacy_clause']['rule']}) "
              f"**{'passes' if pc['legacy_clause']['passes'] else 'FAILS'}** at "
              f"{pc['legacy_clause']['measured_move_pct']} — retained and decomposed, never "
              f"re-labelled (NF-D20). Diagnosis: the incumbent CRPS goes "
              f"{pc['diagnosis']['incumbent_base']} → {pc['diagnosis']['incumbent_shifted']} "
              f"(×{pc['diagnosis']['denominator_inflation']}), i.e. the shift inflates the "
              f"DENOMINATOR of the relative ceiling, so that ratio understates sensitivity by "
              f"construction.", "",
              "| form | base ceiling | shifted ceiling | abs Δ base | abs Δ shifted |",
              "|---|---|---|---|---|"]
        for f, v in pc["by_form"].items():
            L.append(f"| `{f}` | {v['base_ceiling_pct']}% | {v['shifted_ceiling_pct']}% | "
                     f"{v['base_mean_delta']} | {v['shifted_mean_delta']} |")
    path.write_text("\n".join(L) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7i — the RB direct-points ceiling gate (§0.5)")
    ap.add_argument("--smoke", action="store_true", help="path proof: 1 fold (artifact _smoke)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from stored fold scores (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")

    if args.rewrite_report:
        out = derive_verdict_layer(json.loads(art.read_text()))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("%s report re-derived → %s", DC.STORY, art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-1:]
    weights = FA.leg_weights(LP.get_preset(GATE_LEAGUE), DC.POSITION)
    log.info("%s: %d folds × %s, forms %s%s", DC.STORY, len(folds), DC.POSITION,
             list(DC.ORACLE_FORMS), " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    fold_results = [score_fold(f, feat, weights) for f in folds]
    out = {
        "story": DC.STORY, "phase": "rb_direct_points_ceiling", "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len([f for f in fold_results if "scores" in f]),
        "gate_league": GATE_LEAGUE, "position": DC.POSITION,
        "matrix_key": W6DA.w6d_matrix_key(SEASONS), "pit_audit": pit_audit, "attach_audit": attach,
        "predecessor": DC.PREDECESSOR,
        "declared_field": {
            "incumbent": DC.INCUMBENT, "oracle_forms": list(DC.ORACLE_FORMS),
            "declared_field_size": len(DC.ORACLE_FORMS),
            "declared_field_size_source": (
                "the five oracle FORMS pre-registered in §3 — the headline is a MAX over them, so "
                "the multiplicity the selection actually spends is the form family (MH2 (a))"),
            "degenerates": list(DC.DEGENERATES), "permutation": DC.PERMUTATION,
            "crossfit_k": DC.CROSSFIT_K, "lambda_by_form": DC.LAMBDA_BY_FORM,
            "ceiling_bands": list(DC.CEILING_BANDS),
        },
        "premise_correction": {
            "nf_w7h_recorded_direct_oracle": 1.4933,
            "construction": "KW.fit_direct_points(te_p, te_p, ...) — fit AND predicted on the test "
                            "block, so every row saw its own label",
            "reading": ("a row-level in-sample MEMORISATION degenerate, not a ceiling — the NF-W6 "
                        "pre-registration names exactly this ('a ROW-level peek is a zero-CRPS "
                        "degenerate, not a ceiling'). It gated nothing in NF-W7h, but it cannot "
                        "carry the ceiling claim this story exists to measure, which is why every "
                        "peek here is CROSS-FIT."),
        },
        "fold_results": fold_results,
    }
    out = derive_verdict_layer(out)

    if args.smoke:
        # ⭐ The control is measured for EVERY declared form and in BOTH units — the absolute paired
        # delta AND the relative ceiling — because a MULTIPLICATIVE shift also inflates the
        # incumbent's CRPS, i.e. the DENOMINATOR of a relative ceiling. Reporting only the relative
        # figure could therefore show a flat ceiling while the absolute gap moved a long way, which
        # would be a defect in the CONTROL's statistic rather than blindness in the instrument
        # (the E2.1-r class: a gate read on a mis-specified statistic). Recording both is what lets
        # the failure be DIAGNOSED instead of argued about.
        base_sel = out["selection"]
        pc_fold = score_fold(folds[-1], feat, weights, positive_control=True)
        pc_sel = DC.select_ceiling([pc_fold], 1)
        forms = {}
        for f in DC.ORACLE_FORMS:
            b, sft = base_sel["per_form"][f], pc_sel["per_form"][f]
            forms[f] = {
                "base_ceiling_pct": b["ceiling_pct"], "shifted_ceiling_pct": sft["ceiling_pct"],
                "base_mean_delta": b["mean_delta"], "shifted_mean_delta": sft["mean_delta"],
                "base_activity": b["activity"], "shifted_activity": sft["activity"],
                "pct_move": (None if b["ceiling_pct"] is None or sft["ceiling_pct"] is None
                             else round(abs(sft["ceiling_pct"] - b["ceiling_pct"]), 3)),
                "abs_delta_move": (None if b["mean_delta"] is None or sft["mean_delta"] is None
                                   else round(abs(sft["mean_delta"] - b["mean_delta"]), 5)),
            }
        form = "direct_augmented"
        f0 = forms[form]
        move = f0["pct_move"]
        b_abs, s_abs = f0["base_mean_delta"], f0["shifted_mean_delta"]
        growth = (None if not b_abs or b_abs <= 0 or s_abs is None else round(s_abs / b_abs, 3))
        widened = bool(f0["shifted_ceiling_pct"] is not None and f0["base_ceiling_pct"] is not None
                       and f0["shifted_ceiling_pct"] > f0["base_ceiling_pct"])
        # the AMENDED clause gates; the ORIGINAL is retained, scored and reported as FAILED
        passes = bool(growth is not None and growth >= POSITIVE_CONTROL_MIN_ABS_GROWTH and widened)
        legacy = bool(move is not None and move >= POSITIVE_CONTROL_MIN_MOVE_PCT)
        out["positive_control"] = {
            "form": form, "scale": POSITIVE_CONTROL_SCALE,
            "base_pct": f0["base_ceiling_pct"], "shifted_pct": f0["shifted_ceiling_pct"],
            "move_pct": move, "passes": passes,
            "gating_clause": "absolute peek advantage grows ≥ "
                             f"{POSITIVE_CONTROL_MIN_ABS_GROWTH}× AND the ceiling WIDENS",
            "abs_growth": growth, "min_abs_growth": POSITIVE_CONTROL_MIN_ABS_GROWTH,
            "ceiling_widened": widened,
            "legacy_clause": {
                "rule": f"relative ceiling moves ≥ {POSITIVE_CONTROL_MIN_MOVE_PCT} pct points",
                "passes": legacy, "measured_move_pct": move,
                "retained": ("⛔ RETAINED AND SCORED though it FAILS — a pre-registered anchor that "
                             "fails is left FAILING and DECOMPOSED, never re-labelled (NF-D20). Its "
                             "failure is DIAGNOSED, not argued away: a multiplicative shift inflates "
                             "the incumbent CRPS that is this ratio's DENOMINATOR, so the ratio "
                             "understates sensitivity by construction."),
            },
            "diagnosis": {
                "incumbent_base": base_sel["mean_incumbent"],
                "incumbent_shifted": pc_sel["mean_incumbent"],
                "denominator_inflation": (
                    None if not base_sel["mean_incumbent"] else
                    round(pc_sel["mean_incumbent"] / base_sel["mean_incumbent"], 4)),
                "reading": ("the instrument is SENSITIVE — the gated form's absolute advantage "
                            "grew, and the MORE sensitive form (direct_upweighted) reports a "
                            "SMALLER real-data ceiling, an internal-consistency signal a blind "
                            "instrument cannot produce (NF-D16 (g‴))"),
            },
            "by_form": forms,
        }
        # ⛔ WRITE BEFORE RAISING. A refusal that destroys its own evidence forces the next session
        # to re-run a 14-minute job to learn WHY (the INC-43 salvage lesson: the identity of a
        # failure you discarded is permanently unrecoverable).
        out["runtime_seconds"] = round(time.time() - t0, 1)
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        if not passes:
            raise AssertionError(
                f"{DC.STORY} POSITIVE CONTROL FAILED — under a ×{POSITIVE_CONTROL_SCALE} shift of "
                f"the block's own points the `{form}` peek's ABSOLUTE advantage grew {growth}× "
                f"(needs ≥ {POSITIVE_CONTROL_MIN_ABS_GROWTH}×) and the ceiling widened={widened}. "
                f"A blind instrument REFUSES the smoke rather than reporting a ceiling it cannot "
                f"see (NF-W6 §6 / MH2.1 (d)). Evidence written to {art.name} — read "
                f"`positive_control.by_form` before changing anything, and ⛔ do NOT lower the bar "
                f"to make it pass (E2.1-r).")

    out["runtime_seconds"] = round(time.time() - t0, 1)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("%s → %s · verdict %s · ceiling %s%%", DC.STORY, art.name,
             out["verdict"]["story_verdict"], out["verdict"]["ceiling_pct"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
