"""run_nf_w8_0b_tail_point.py — NF-W8-0b §0.5: the TAIL-COMPLETED cross-position ranking point.

Everything decidable in advance is a CONSTANT in `fp_tail_point.py`; this runner READS it
(NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w8_0b_preregistration.md` BEFORE any scoring run.

⭐ ONE CODE PATH, TWO READS. This story changes NOTHING about how the four certified generators
are built, scored, recalibrated or verdicted — it changes only HOW A POINT IS READ off the
certified bank. So it does not fork NF-W8-0's harness: it drives it through the registered
`point_reader` hook (`TP.tail_completed_point` in place of the truncated grid mean) and reuses
`W80.run_fold` / `W80.derive_verdict_layer` / `W80._write_input` verbatim. The generators keep
exactly one implementation (NF-W7d), the reproduction pins cannot drift, and family A / family B
/ the §6 swap clause have exactly one rule set (E9.61) — measured on the new point.

WHAT IS NEW HERE, and only this:
  · the ranking point (`TP.tail_completed_point`) — a DETERMINISTIC transform of the certified
    bank: no `y`, no fold, no fitted state, so NF-W8-0 §12.3a's non-stationarity floor cannot
    apply to it;
  · the §6 swap-clause MATERIALITY FLOOR (`TP.materiality_floor`) — NF-W8-0 §12.5(2), a design
    quantity read off family A's OWN detection resolution on this same run;
  · NF-W8-0b's verdict naming + the two `cross_rankable` readings (`TP.tail_point_verdict`).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: writes LOCAL artifacts
only — no `--publish`, no S3 client, no boto3, no dbt, no Dagster. ⛔ It also writes NO NF-W8-0
path: the predecessor's record is DECIDED and this runner is refused at import if its own
artifact paths would collide with it.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, all four positions, few draws (artifact _smoke) — no verdict
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0b_tail_point --smoke

    # the decisive run (>2 min — OPERATOR; dominated by the W6d marginal dispatch per fold)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0b_tail_point

    # re-derive every verdict from the stored fold rows at ZERO refit cost (NF-W2e / NF-W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0b_tail_point --rewrite-report

⭐ Per-fold MARGINAL BANKS are cached under `artifacts/nf_w7e_bank_cache/` — NF-W7e's own cache
directory and key scheme, inherited through `W80.run_fold`, so a machine already holding the
W7e/W7f/W8-0 cache pays only for draws + LGBM fits.
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

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_split_allrows as SA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_cross_position as XP,
)
from quant_sports_intel_models.football.nfl.fantasy import fp_tail_point as TP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_serve_stat_distributions as W6DS,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w8_0_cross_position as W80,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w8_0b")

SEASONS = W6DA.SEASONS
GATE_LEAGUE = W80.GATE_LEAGUE                      # ⛔ inherited (E2.1-r)

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w8_0b_tail_point.json")
_ROWS_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0b_rows"
_INPUT_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0b_input"

#: ⛔ NF-W8-0's record is DECIDED. A successor that writes a decided story's paths destroys its
#: audit trail with no error and no test failure (the NCAAF-P2.1 S1-serve lesson, which cost a
#: DECIDED story's calibration section on a routine re-run). Enforced at import, not by review.
_PREDECESSOR_PATHS: tuple[str, ...] = ("nf_w8_0_cross_position", "nf_w8_0_rows", "nf_w8_0_input")
for _own in (_ARTIFACT_REL, str(_ROWS_DIR), str(_INPUT_DIR)):
    for _dec in _PREDECESSOR_PATHS:
        if Path(_own).name.startswith(_dec) or f"/{_dec}" in _own:
            raise RuntimeError(f"NF-W8-0b would write NF-W8-0's decided artifact path "
                               f"({_own}) — refused (a successor never writes a decided story's "
                               f"paths)")


def family_a_on_stored_rows(rows_by_fold: dict) -> dict:
    """Family A on the tail-completed point, from the stored rows, via the SHARED statistic
    (`XP.pairwise_gap_tests`). Needed BEFORE the derive layer runs because the §6 materiality
    floor is read off family A's own MDEs — and the floor must be in force when the derive layer
    evaluates the swap clause, not patched on afterwards.

    ⚠️ This is NOT a second rule set: the statistic has one implementation, and
    `_assert_family_a_agrees` pins this pre-read byte-equal to the derive layer's own family A
    (E9.61 — two readers of one field are two rule sets unless something forbids it)."""
    bias: dict[str, list[float]] = {p: [] for p in XP.POSITIONS}
    for label in sorted(rows_by_fold):
        df = rows_by_fold[label]
        for p in XP.POSITIONS:
            sel = df["position"] == p
            bias[p].append(float((df.loc[sel, "point_consumed"] - df.loc[sel, "y"]).mean())
                           if sel.any() else np.nan)
    return XP.pairwise_gap_tests(bias)


def _assert_family_a_agrees(pre: dict, derived: dict) -> None:
    """The pre-read (which SET the floor) and the derive layer's own family A must be the same
    measurement. A silent divergence would mean the floor was formed off a different statistic
    than the one the record reports."""
    a = {k: (v.get("gap"), v.get("se"), v.get("mde_ppr")) for k, v in pre["pairs"].items()}
    b = {k: (v.get("gap"), v.get("se"), v.get("mde_ppr")) for k, v in derived["pairs"].items()}
    if a != b:
        raise ValueError("the materiality floor was formed off a DIFFERENT family A than the "
                         "record reports — refused (E9.61: one field, one rule set)")


def derive_0b(out: dict) -> dict:
    """The NF-W8-0b derivation: the shared derive layer with the registered materiality floor in
    force, then NF-W8-0b's verdict naming and the two `cross_rankable` readings."""
    rows_by_fold = W80._load_rows(out["fold_results"])
    pre_a = family_a_on_stored_rows(rows_by_fold)
    floor = TP.materiality_floor(pre_a)
    # a run with <4 evaluable folds is UNDEFINED BY CONSTRUCTION (prereg §5.4 / §6.4) and reaches
    # no verdict — that is exactly the `--smoke` path proof, where family A has one fold per
    # position and every pairwise MDE is therefore None
    verdict_reachable = (len(rows_by_fold) - 1) >= 4
    if floor["floor_ppr"] is None:
        if verdict_reachable:
            # NF1.7 (a): on a run that WOULD reach a verdict, a floor that could not be FORMED is
            # never floor-0 and never None — either would silently restore the predecessor's
            # no-floor rule under this story's name
            raise ValueError(f"the §6 materiality floor could not be formed: {floor['note']}")
        # on a path proof the clause is made UNEVALUABLE (an INFINITE floor deactivates every
        # position ⇒ INACTIVE_EVERYWHERE ⇒ the clause neither passes nor refuses) — ⛔ still NOT
        # floor-0 and NOT None, so the predecessor's rule cannot leak in through the smoke
        floor = floor | {"floor_ppr": float("inf"), "unformable_on_a_path_proof": True,
                         "note": (f"{floor['note']} — this run is UNDEFINED by construction "
                                  f"(<4 evaluable folds), so the clause is made UNEVALUABLE "
                                  f"with an infinite floor rather than dropped to the "
                                  f"predecessor's no-floor rule")}

    out = W80.derive_verdict_layer(out, swap_floor_ppr=float(floor["floor_ppr"]))
    _assert_family_a_agrees(pre_a, out["family_a"])

    out["materiality_floor"] = floor
    out["tail_point"] = {
        "form": TP.TAIL_FORM,
        "anchor_levels": {"inner_hi": TP.ANCHOR_INNER_HI, "outer_hi": TP.ANCHOR_OUTER_HI,
                          "inner_lo": TP.ANCHOR_INNER_LO, "outer_lo": TP.ANCHOR_OUTER_LO},
        "covered_mass": TP.COVERED_MASS, "tail_mass_per_side": TP.TAIL_MASS_PER_SIDE,
        "deterministic": True,
        "note": ("a pure function of the certified bank — no `y`, no fold, no fitted state, so "
                 "NF-W8-0 §12.3a's non-stationarity floor cannot apply (that is the whole "
                 "reason this successor is deterministic)"),
    }
    # the transform's own magnitudes, pooled per position over folds (NF-W7f: report the
    # MAGNITUDE beside any share — a share alone hides a mechanism that stopped mattering)
    per_pos: dict[str, dict] = {}
    for pos in XP.POSITIONS:
        ds, gs, ts = [], [], []
        for fr in out["fold_results"]:
            d = fr["positions"].get(pos, {}).get("bank_detail", {}).get("consumed")
            if d:
                ds.append(d["mean_delta"]); gs.append(d["mean_gridmean"]); ts.append(d["mean_hi_tail"])
        if ds:
            per_pos[pos] = {"n_folds": len(ds),
                            "mean_completion_delta_ppr": round(float(np.mean(ds)), 4),
                            "mean_gridmean_ppr": round(float(np.mean(gs)), 4),
                            "mean_hi_tail_ppr": round(float(np.mean(ts)), 4)}
    out["tail_completion_by_position"] = per_pos
    # the incumbent (grid-mean) bias, carried BESIDE the tail-completed one so the record shows
    # BOTH reads of the same certified banks rather than asserting the predecessor's numbers
    out["gridmean_bias_by_position"] = {
        pos: round(float(np.mean([fr["positions"][pos]["bias_gridmean"]["bias"]
                                  for fr in out["fold_results"]
                                  if "bias_gridmean" in fr["positions"].get(pos, {})])), 4)
        for pos in XP.POSITIONS
        if any("bias_gridmean" in fr["positions"].get(pos, {}) for fr in out["fold_results"])}
    # ⭐ THE ROW-POOLED completion delta — the ONLY convention under which the headline identity
    # (a pair's movement == the difference of its two positions' deltas) is EXACT. The per-fold
    # `bank_detail` means above are a MEAN OF FOLD MEANS and differ by up to 0.002 PPR, which is
    # enough to make a bound stated from them WRONG (NF1.8: pool over rows, never a mean of fold
    # means — caught here by the bound guard, on this story's own headline).
    out["completion_delta_pooled"] = {
        pos: round(float(out["identity_bias"]["pooled"][pos]["bias_pooled"]
                         - out["gridmean_bias_by_position"][pos]), 6)
        for pos in XP.POSITIONS
        if out["identity_bias"]["pooled"].get(pos, {}).get("bias_pooled") is not None
        and pos in out["gridmean_bias_by_position"]}
    if out["completion_delta_pooled"]:
        v = list(out["completion_delta_pooled"].values())
        out["completion_delta_pooled_spread"] = round(float(max(v) - min(v)), 6)

    v0b = TP.tail_point_verdict(
        predecessor_verdict=out["verdict"],
        swap_state=(out.get("swap_verification") or {}).get("state"),
        winner_clauses=out.get("recal", {}).get("winner_clauses"))
    out["verdict_0b"] = v0b
    out["cross_rankable"] = v0b["cross_rankable"]
    if "input" in out:
        # ⭐ NF-W8-0b's headline uses the STRICTER definition (the deterministic point closes the
        # gap with NO layer); the predecessor's inherited reading is kept beside it, named.
        out["input"]["cross_rankable"] = v0b["cross_rankable"]
        out["input"]["cross_rankable_with_layer"] = v0b["cross_rankable_with_layer"]
    out["promote_blockers"] = list(TP.PROMOTE_BLOCKERS)
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v = out["verdict_0b"]
    fa = out["family_a"]
    fl = out["materiality_floor"]
    L = [
        f"# NF-W8-0b — the tail-completed cross-position ranking point ({v['state']})",
        "",
        f"Generated {out['generated_at']} · gate league **{out['gate_league']}** · "
        f"{out['n_folds']} folds · target `{XP.TARGET}`",
        "",
        "⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
        "promotes nothing and publishes nothing.",
        "", "## Verdict", "",
        f"- state: **{v['state']}**",
        f"- **`cross_rankable`: {v['cross_rankable']}** (the deterministic reading — the "
        f"tail-completed point closes the gap with NO recalibration layer)",
        f"- `cross_rankable_with_layer`: {v['cross_rankable_with_layer']} (the weaker, "
        f"predecessor-inherited reading)",
        f"- {v['reason']}",
        f"- predecessor-state mapping: `{v['predecessor_state']}` · shipped arm "
        f"`{out.get('input', {}).get('shipped_arm')}`",
        "", "## The transform (deterministic — no fitting)", "",
        f"- form: `{out['tail_point']['form']}` · anchors {out['tail_point']['anchor_levels']}",
        f"- covered mass {out['tail_point']['covered_mass']} + "
        f"{out['tail_point']['tail_mass_per_side']} per side restored",
        "",
        "| pos | grid-mean bias (PPR) | tail-completed bias (PPR) | mean completion Δ (PPR) |",
        "|---|---|---|---|",
    ]
    for pos in XP.POSITIONS:
        gm = out.get("gridmean_bias_by_position", {}).get(pos)
        tc = out["identity_bias"]["pooled"].get(pos, {}).get("bias_pooled")
        d = out.get("tail_completion_by_position", {}).get(pos, {}).get("mean_completion_delta_ppr")
        # round for DISPLAY only — the stored record keeps full precision (the pins read it)
        tc = None if tc is None else round(float(tc), 4)
        L.append(f"| {pos} | {gm} | {tc} | {d} |")
    L += ["", "## Reproduction pins (the consumed generators, by identity)", "",
          "| pos | generator | reproduces | folds | max gap |", "|---|---|---|---|---|"]
    for pos in XP.POSITIONS:
        r = out["reproduction"][pos]
        L.append(f"| {pos} | `{XP.CONSUMED_GENERATOR_OF[pos]}` | {r['reproduces']} | "
                 f"{r['n_folds_compared']} | {r['max_abs_gap']} |")
    L += ["", "## Family A — the pairwise level-gap tests ON THE TAIL-COMPLETED POINT", "",
          f"- gap_detected: **{fa['gap_detected']}** (BH q={fa['bh_q']}, "
          f"{fa['n_pairs_evaluable']} evaluable pairs, max pairwise MDE {fa['max_mde_ppr']} PPR "
          f"at 80% power)", "",
          "| pair | gap (PPR) | se | p (2-sided) | BH rejected | MDE |", "|---|---|---|---|---|---|"]
    for name, d in fa["pairs"].items():
        L.append(f"| {name} | {d['gap']} | {d['se']} | {d['p_two_sided']} | "
                 f"{d['bh_rejected']} | {d['mde_ppr']} |")
    if out.get("completion_delta_pooled"):
        cd = out["completion_delta_pooled"]
        L += ["",
              f"⭐ **The bound.** A pair's movement vs the grid-mean read is EXACTLY the "
              f"difference of its two positions' ROW-POOLED completion deltas "
              f"({' · '.join(f'{k} {v:+.4f}' for k, v in cd.items())}), so the whole mechanism is "
              f"bounded by their SPREAD: **{out['completion_delta_pooled_spread']} PPR**. ⚠️ The "
              f"convention is load-bearing — the per-fold means in `tail_completion_by_position` "
              f"are a MEAN OF FOLD MEANS and imply a different (wrong) bound (NF1.8)."]
    L += ["", "## §6 swap clause under the registered MATERIALITY FLOOR", "",
          f"- floor: **{fl['floor_ppr']} PPR** (`{fl['statistic']}` over {fl['n_pairs']} pairs) "
          f"· sensitivity band {fl.get('sensitivity_band')}",
          f"- state: **{(out.get('swap_verification') or {}).get('state')}**"]
    for pos, d in ((out.get("swap_verification") or {}).get("detail") or {}).items():
        L.append(f"  - {pos}: {d}")
    L += ["", "## Family B — the recalibration contest (reported; the gate is family A)", "",
          f"- evaluable folds: {out['recal']['n_evaluable']} · winner: "
          f"`{out['recal']['winner']}` · PBO {out['recal']['pbo']} · DSR {out['recal']['dsr']}",
          f"- winner clauses: {out['recal']['winner_clauses']}", "",
          "| arm | pooled cross-position bias range (PPR) |", "|---|---|"]
    for arm, d in out["recal"]["range_by_arm"].items():
        L.append(f"| `{arm}` | {d['pooled']} |")
    L += ["", "## Null classification", "", f"- {out.get('classification')}"]
    if (out.get("classification") or {}).get("retest_trigger"):
        L += ["",
              "⚠️⚠️ **THE TRIGGER ABOVE DESCRIBES FAMILY B ONLY (the FITTED recalibration "
              "contest) AND IS NOT FAMILY A'S STATUS.** Family A — this story's gate — asks "
              "whether the DETERMINISTIC point closes the gap, and its answer is "
              "ARITHMETICALLY BOUNDED, not underpowered: the completion delta is a deterministic "
              "function of each certified bank and no fold count can widen its cross-position "
              "spread. Reading a fold trigger onto family A would be the NF-D18 "
              "misleading-trigger class."]
    L += ["", "## The input", "",
          f"- dir: `{out.get('input', {}).get('dir')}` · shipped arm "
          f"`{out.get('input', {}).get('shipped_arm')}` · banks_untouched "
          f"{out.get('input', {}).get('banks_untouched')} (max quantile drift "
          f"{out.get('input', {}).get('max_quantile_drift')})",
          f"- schema: {out.get('input', {}).get('schema')}",
          "", "## Promote blockers", ""]
    L += [f"- {b}" for b in out["promote_blockers"]]
    path.write_text("\n".join(L) + "\n")


# ── Main ────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W8-0b — the tail-completed cross-position "
                                             "ranking point (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, all four positions, few draws (artifact _smoke) — "
                         "no verdict (reproduction pins cannot hit at smoke draws)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored fold rows (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true",
                    help="ignore the per-fold marginal-bank cache and refit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")
    rows_dir = _ROWS_DIR.with_name(_ROWS_DIR.name + suffix)
    input_dir = _INPUT_DIR.with_name(_INPUT_DIR.name + suffix)

    if args.rewrite_report:
        out = json.loads(art.read_text())
        out["input_dir"] = str(input_dir)
        out = derive_0b(out)
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W8-0b report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else FA.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    log.info("NF-W8-0b: %d folds × %d positions, %d draws%s [tail-completed point]",
             len(folds), len(XP.POSITIONS), draws, " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    fold_results = [W80.run_fold(f, feat, smap, draws=draws, matrix_key=matrix_key,
                                 rows_dir=rows_dir, rebuild_banks=args.rebuild_banks,
                                 point_reader=TP.tail_completed_point,
                                 bank_detail=TP.bank_report)
                    for f in folds]
    out = {
        "story": TP.STORY, "predecessor": TP.PREDECESSOR, "phase": "tail_completed_ranking_point",
        "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "matrix_key": matrix_key, "pit_audit": pit_audit, "attach_audit": attach,
        "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "seed": SA._SEED,
        "consumed_generators": dict(XP.CONSUMED_GENERATOR_OF),
        "swap_generators": dict(XP.SWAP_GENERATOR_OF),
        "declared_field": {"incumbent": XP.INCUMBENT, "real_arms": list(XP.REAL_ARMS),
                           "anchors": list(XP.ANCHOR_ARMS),
                           "declared_field_size": XP.DECLARED_FIELD_SIZE},
        "input_dir": str(input_dir),
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_0b(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W8-0b %s (cross_rankable=%s) → %s (%.1fs)", out["verdict_0b"]["state"],
             out["cross_rankable"], art.name, out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
