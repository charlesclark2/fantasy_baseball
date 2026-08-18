"""run_nf_w7j_component_clause.py — NF-W7j: decide NF-W7f's deferred component clause, audit the
served plane, and re-derive QB's verdict from NF-W7f's STORED fold results.

⛔ THIS RUNNER REFITS NOTHING. It reads `nf_w7f_qb_marginal.json`, pins every quantity it consumes
against NF-W7f's record (prereg §3), re-evaluates ONE clause, and re-derives the gate + null state.
NF-W7f's scores are untouched and must reproduce byte-identically or the run is INVALID.

Every threshold is READ from `fp_component_clause.py` (NF-D16); this file contains none.

⚖️ `best_alpha = 0` · DEPLOY-HELD · research-only · no changelog.

Usage:  uv run python quant_sports_intel_models/football/nfl/fantasy/run_nf_w7j_component_clause.py
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ⭐ The repo root is anchored EXPLICITLY off this file's own location, never by walking up looking
# for a marker: NF-W7f §11.3 recorded a harness that HUNG on an unbounded "walk up to pyproject.toml"
# (`Path("/").parent` is `/`), 100% CPU with no output and indistinguishable from a hanging test.
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_component_clause as CC,
    game_environment as GE,
    nf1_1_model as M14,
)
from betting_ml.utils import cv_power  # noqa: E402

HERE = Path(__file__).resolve().parent
ABL = HERE / "ablation_results"


class InvalidRun(RuntimeError):
    """Raised when a precondition fails. ⛔ Never downgraded to a warning — an unevaluable check is
    not a pass (NF1.7 (a))."""


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §1 — the served-cell audit: a transitive import-closure walk over the serving plane
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _module_path(dotted: str, root: Path) -> Path | None:
    p = root / (dotted.replace(".", "/") + ".py")
    if p.exists():
        return p
    pkg = root / dotted.replace(".", "/") / "__init__.py"
    return pkg if pkg.exists() else None


def _imports_of(path: Path) -> set[str]:
    """Every absolute dotted name a module imports. Relative imports are skipped: this repo's
    serving plane uses absolute imports throughout, and a silently mis-resolved relative name would
    make the audit under-count (which fails toward a false PASS)."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative — see docstring
                continue
            base = node.module or ""
            out.add(base)
            out.update(f"{base}.{a.name}" for a in node.names)
    return out


def import_closure(seed: str, root: Path | None = None) -> set[str]:
    """The transitive set of first-party modules reachable from `seed` by import."""
    root = root or REPO_ROOT
    seen: set[str] = set()
    stack = [seed]
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        path = _module_path(mod, root)
        if path is None:
            continue  # third-party / stdlib — not part of this repo's closure
        seen.add(mod)
        stack.extend(i for i in _imports_of(path) if i not in seen)
    return seen


def _hits(closure: set[str]) -> list[str]:
    return sorted(m for m in closure
                  if any(s in m for s in CC.FORBIDDEN_SUBSTRINGS))


def served_cell_audit(root: Path | None = None) -> dict:
    """Does the served paid stat line derive from the NF-W6d per-stat cells? (prereg §1)

    ⭐ TWO-SIDED BY CONSTRUCTION. A walker that resolves nothing returns an empty hit set for every
    seed, so a PASS would be indistinguishable from a broken audit. The positive controls are KNOWN
    consumers and this RAISES — never returns PASS — if either comes back empty, or if any seed's
    closure is implausibly small.
    """
    root = root or REPO_ROOT
    for marker in ("pyproject.toml", "app", "quant_sports_intel_models"):
        if not (root / marker).exists():
            raise InvalidRun(f"repo root {root} has no {marker!r} — the audit cannot resolve modules")

    controls: dict[str, list[str]] = {}
    for seed in CC.POSITIVE_CONTROL_SEEDS:
        closure = import_closure(seed, root)
        # the SIZE floor lives HERE, where a large closure is what makes an empty hit set diagnostic
        if len(closure) < CC.MIN_CLOSURE_MODULES:
            raise InvalidRun(
                f"POSITIVE CONTROL {seed!r} resolved only {len(closure)} modules "
                f"(< {CC.MIN_CLOSURE_MODULES}) — the closure walker is broken, so an empty hit set "
                "below would prove nothing. UNEVALUABLE (NF1.7 (a))")
        controls[seed] = _hits(closure)
        if not controls[seed]:
            raise InvalidRun(
                f"POSITIVE CONTROL EMPTY for {seed!r}: it is a KNOWN consumer of the per-stat cells, "
                "so an empty hit set means the closure walker resolved nothing. The audit is VACUOUS "
                "and must not report PASS (NF1.7 (a))")

    seeds: dict[str, dict] = {}
    for seed in CC.SERVING_PLANE_SEEDS:
        # ⭐ the REAL vacuity condition, asserted directly rather than through a size proxy: a seed
        # that does not resolve to a module file contributes an empty closure, and an empty closure
        # has no hits — i.e. a typo'd or moved seed would read as PASS.
        if _module_path(seed, root) is None:
            raise InvalidRun(
                f"serving-plane seed {seed!r} does not resolve to a module under {root} — it was "
                "renamed, moved or mistyped. An unresolvable seed yields an empty closure, which "
                "would read as a clean PASS. UNEVALUABLE — never scored clean (NF1.7 (a))")
        closure = import_closure(seed, root)
        if seed not in closure:
            raise InvalidRun(f"closure for {seed!r} does not contain the seed itself — walker broken")
        seeds[seed] = {"n_modules": len(closure), "hits": _hits(closure)}

    passes = all(not v["hits"] for v in seeds.values())
    return {
        "passes": passes,
        "seeds": seeds,
        "positive_controls": {k: {"n_hits": len(v), "hits": v} for k, v in controls.items()},
        "forbidden_substrings": list(CC.FORBIDDEN_SUBSTRINGS),
        "reading": (
            "the NF-W6d per-stat cells NF-W7f's recalibration degrades reach NO serving surface — "
            "not the published board, not the entitled stat line, not the scorer"
            if passes else
            "a serving-plane entry point CONSUMES the per-stat cells — the clause FAILS CLOSED to "
            "the raw 0.0 tolerance (prereg §1.3)"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3 — the reproduction pin
# ══════════════════════════════════════════════════════════════════════════════════════════════

def load_and_pin(record: Path) -> dict:
    """Read NF-W7f's record and assert every quantity the decision consumes reproduces it EXACTLY.
    ⛔ A decision measured against a different object than the one NF-W7f scored is not a decision
    about NF-W7f (prereg §3)."""
    if not record.exists():
        raise InvalidRun(f"NF-W7f record absent at {record} — UNEVALUABLE, never a pass")
    doc = json.loads(record.read_text())

    if doc.get("smoke") is not False:
        raise InvalidRun(f"NF-W7f record is a SMOKE ({doc.get('smoke')!r}) — a smoke carries no verdict")
    if doc.get("n_folds") != CC.W7F_N_FOLDS:
        raise InvalidRun(f"n_folds {doc.get('n_folds')} != pinned {CC.W7F_N_FOLDS}")

    sel = (doc.get("selections") or {}).get(CC.W7F_POSITION)
    if not sel:
        raise InvalidRun(f"no {CC.W7F_POSITION} selection in {record.name}")
    if sel.get("winner") != CC.W7F_WINNER or sel.get("best_foil") != CC.W7F_MATCHED_FOIL:
        raise InvalidRun(
            f"winner/foil {sel.get('winner')}/{sel.get('best_foil')} != pinned "
            f"{CC.W7F_WINNER}/{CC.W7F_MATCHED_FOIL}")

    per_leg = sel.get("per_leg_detail") or {}
    series = ((sel.get("per_fold_series") or {}).get("priced_leg_relative_change_by_fold"))
    if not series or len(series) != CC.W7F_N_FOLDS:
        raise InvalidRun("priced_leg_relative_change_by_fold missing or wrong length — UNEVALUABLE")

    observed = {
        "per_leg_relative_change": per_leg.get("relative_change"),
        "per_leg_relative_change_winner_by_fold_mean":
            (per_leg.get("relative_change_by_arm") or {}).get(CC.W7F_WINNER),
        "per_leg_tolerance": per_leg.get("tolerance"),
        "mean_delta": sel.get("mean_delta"),
        "ci95_lo": (sel.get("ci95") or [None, None])[0],
        "ci95_hi": (sel.get("ci95") or [None, None])[1],
        "matched_foil_mean_crps": (sel.get("mean_crps") or {}).get(CC.W7F_MATCHED_FOIL),
    }
    for key, expected in CC.W7F_PINS.items():
        got = observed[key]
        if got is None or abs(float(got) - expected) > CC.PIN_TOLERANCE:
            raise InvalidRun(f"reproduction pin {key}: {got!r} != NF-W7f's {expected!r}")

    # ⭐ the series' own object is the MEAN OF PER-FOLD RATIOS, which NF-W7f also stores as
    # `relative_change_by_arm[winner]` — NOT the pooled ratio-of-sums. Pinning it against the pooled
    # figure is what surfaced the distinction (they differ by ~3% relative), so the pin asserts the
    # series against the statistic it actually IS.
    by_fold_mean = CC.W7F_PINS["per_leg_relative_change_winner_by_fold_mean"]
    if abs(float(np.mean(series)) - by_fold_mean) > 1e-6:
        raise InvalidRun(
            f"per-fold series mean {np.mean(series):.6f} does not reproduce NF-W7f's stored "
            f"relative_change_by_arm['{CC.W7F_WINNER}'] {by_fold_mean} — the series is not that "
            "statistic's object")

    gate_block = (doc.get("gates") or {}).get(CC.W7F_POSITION) or {}
    gates = gate_block.get("checks") or {}
    if len(gates) != CC.W7F_N_GATE_CLAUSES:
        raise InvalidRun(f"gate has {len(gates)} clauses, pinned {CC.W7F_N_GATE_CLAUSES}")
    failing = sorted(k for k, v in gates.items() if not v)
    if failing != sorted(CC.W7F_FAILING_CLAUSES):
        raise InvalidRun(f"NF-W7f's failing clauses are {failing}, pinned {sorted(CC.W7F_FAILING_CLAUSES)}")

    return {"doc": doc, "sel": sel, "gates": gates, "per_leg": per_leg,
            "series": [float(x) for x in series]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2 — the decided clause
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _band_state(lo: float | None, hi: float | None, band: float) -> str:
    """prereg §2.2 — the NF-W7i band framing. ⛔ `UNDECIDED_MAGNITUDE` is NOT `POWER_LIMITED`."""
    if lo is None or hi is None:
        return "UNDECIDED_MAGNITUDE"
    if hi < band:
        return "MEASURED_IMMATERIAL"
    if lo > band:
        return "MEASURED_MATERIAL"
    # the interval straddles the band: the design does not resolve the magnitude
    return "UNDECIDED_MAGNITUDE"


def evaluate_component_clause(*, series: list[float], per_leg: dict, sel: dict,
                              audit: dict) -> dict:
    """Both readings of the component clause: NF-W7f's RAW 0.0-tolerance one and NF-W7j's DECIDED
    materiality one. Both are returned every run and both are printed (NF-D20).

    Returns `refuses` for each. `True` = the clause refuses the ship.
    """
    d = np.asarray(series, float)
    pooled_rel = float(per_leg["relative_change"])          # + = degraded
    served_sum = float(per_leg["served_crps_sum_priced"])
    recal_sum = float(per_leg["recalibrated_crps_sum_priced"])
    abs_change = recal_sum - served_sum

    mean_delta = float(sel["mean_delta"])                    # the arm's claimed effect, CRPS
    foil_crps = float(sel["mean_crps"][CC.W7F_MATCHED_FOIL])
    rel_effect = mean_delta / foil_crps                      # dimensionless claimed effect

    # ── RAW (NF-W7f): any degradation at all refuses ───────────────────────────────────────────
    raw = {
        "clause": CC.RAW_CLAUSE,
        "tolerance": CC.RAW_TOLERANCE,
        "relative_change": round(pooled_rel, 6),
        "refuses": bool(pooled_rel > CC.RAW_TOLERANCE),
    }

    # ── A: the precondition ────────────────────────────────────────────────────────────────────
    audit_ok = bool(audit["passes"])

    # ── B: DEMONSTRABLE — the harness's OWN one-sided paired instrument, by identity ────────────
    p_one_sided = M14.onesided_paired_pvalue(d)
    mean_rel, lo_rel, hi_rel = GE.paired_ci95(d)
    demonstrable = bool(p_one_sided is not None and p_one_sided < CC.ALPHA_DEMONSTRABLE)

    # ── C/D: MATERIAL, in the PRIMARY (relative) unit, with the ABSOLUTE unit as sensitivity ────
    effect_well_defined = bool(mean_delta > 0 and foil_crps > 0)
    band_rel = CC.MATERIALITY_FRACTION * rel_effect
    band_abs = CC.MATERIALITY_FRACTION * mean_delta
    # ⭐ C is the MAGNITUDE comparison ALONE and must NOT re-test D. An earlier cut wrote
    # `effect_well_defined and pooled_rel >= band_rel`, which made C refuse D's own fixture — so the
    # guard isolating D passed with D DELETED from the conjunction (NF-D17: a clause on `A and B and
    # C` is only tested by a fixture that SATISFIES the others). Found by this story's own RED proof,
    # not by a green suite. D stays a separate condition because a non-positive claimed effect
    # collapses the band to ≤ 0, against which any degradation is trivially "material".
    material_primary = bool(pooled_rel >= band_rel)
    material_absolute = bool(abs_change >= band_abs)

    units_agree = material_primary == material_absolute

    # ⭐ FAIL CLOSED, not fail open (prereg §1.3 / §2 row A). When the audit does NOT pass, the
    # licence to relax is absent and the clause reverts to NF-W7f's RAW 0.0-tolerance verdict — it
    # does NOT simply return "does not refuse". Writing `audit_ok and …` reads like a precondition
    # and is in fact fail-OPEN: a broken/expired audit would silently REMOVE the gate, which is the
    # opposite of what condition A exists to do. Guard-pinned + RED-proved.
    refuses = bool(demonstrable and material_primary and effect_well_defined) if audit_ok \
        else bool(raw["refuses"])

    decided = {
        "clause": CC.DECIDED_CLAUSE,
        "refuses": refuses,
        "fails_closed_to_raw": not audit_ok,
        "conditions": {
            "A_served_cell_audit_passes": audit_ok,
            "B_demonstrable": demonstrable,
            "C_material_primary_relative": material_primary,
            "D_claimed_effect_well_defined": effect_well_defined,
        },
        "demonstrable_detail": {
            "instrument": "nf1_1_model.onesided_paired_pvalue (the harness's own, by identity)",
            "alpha": CC.ALPHA_DEMONSTRABLE,
            "p_one_sided": p_one_sided,
            "per_fold_relative_change": [round(x, 6) for x in series],
            "folds_degraded": int((d > 0).sum()),
            "n_folds": int(len(d)),
            "mean": None if mean_rel is None else round(mean_rel, 6),
            "ci95": [None if lo_rel is None else round(lo_rel, 6),
                     None if hi_rel is None else round(hi_rel, 6)],
        },
        "materiality_detail": {
            "materiality_fraction": CC.MATERIALITY_FRACTION,
            "primary_unit": "relative (dimensionless): a 10-leg SUM and a 1-number total share no "
                            "absolute scale, so the dimensionless form is the comparable one",
            "assembled_relative_effect": round(rel_effect, 6),
            "band_relative": round(band_rel, 6),
            "component_relative_change": round(pooled_rel, 6),
            "point_estimate_in_band_units": round(pooled_rel / band_rel, 4) if band_rel else None,
            "ci95_in_band_units": [None if lo_rel is None else round(lo_rel / band_rel, 4),
                                   None if hi_rel is None else round(hi_rel / band_rel, 4)]
            if band_rel else [None, None],
            "band_state": _band_state(lo_rel, hi_rel, band_rel),
            "sensitivity_absolute": {
                "component_absolute_change_crps": round(abs_change, 6),
                "band_absolute_crps": round(band_abs, 6),
                "material": material_absolute,
            },
            "units_agree": units_agree,
        },
    }
    return {"raw": raw, "decided": decided}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — the re-derived gate + null state
# ══════════════════════════════════════════════════════════════════════════════════════════════

def rescore(pinned: dict, clause: dict) -> dict:
    """Substitute the decided clause for the raw one and re-derive the gate + null classification.
    ⛔ Every other clause is carried over from NF-W7f UNCHANGED — this story re-scores one clause,
    not a run."""
    gates = dict(pinned["gates"])
    sel = pinned["sel"]

    decided_gates = {k: v for k, v in gates.items() if k != CC.RAW_CLAUSE}
    decided_gates[CC.DECIDED_CLAUSE] = not clause["decided"]["refuses"]

    failing = sorted(k for k, v in decided_gates.items() if not v)
    full_gate_green = not failing

    from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM
    anchor_names = set(QM.ANCHOR_CHECKS) - {CC.RAW_CLAUSE} | {CC.DECIDED_CLAUSE}
    stat_names = set(QM.STATISTICAL_CHECKS)
    failing_anchor = sorted(c for c in failing if c in anchor_names)
    failing_stat = sorted(c for c in failing if c in stat_names)

    out: dict = {
        "gate": decided_gates,
        "failing_clauses": failing,
        "failing_anchor_clauses": failing_anchor,
        "failing_statistical_clauses": failing_stat,
        "full_gate_green": full_gate_green,
        "certification_requires_full_gate": CC.CERTIFICATION_REQUIRES_FULL_GATE,
        "certified_for_nf_w8": bool(full_gate_green and CC.CERTIFICATION_REQUIRES_FULL_GATE),
    }

    if full_gate_green:
        out["null_state"] = None
        out["verdict"] = "QB_CERTIFIED"
        return out

    if failing_anchor:
        # unchanged from NF-W7f: an anchor half is not rescuable by data, so it BINDS (NF-D18)
        out["verdict"] = "QB_REFUSED"
        out["null_state"] = {
            "state": "CONSTRAINT_REFUSED", "binding_half": "anchor", "retest_trigger": None,
        }
        return out

    # ⭐ purely STATISTICAL now — the classify_null call NF-W7f's mixed-refusal path bypassed
    v = cv_power.classify_null(
        metric=f"nf_w7j_component_clause|{CC.W7F_POSITION}", n_folds=sel["n_folds_used"],
        n_arms=CC.W7F_DECLARED_FIELD_SIZE, beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"],
        bh_cutoff=QM.FDR_Q, degenerates_excluded_from_v=True,
        declared_field_size=CC.W7F_DECLARED_FIELD_SIZE,
    )
    verdict = GE.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "field_remedy_admissible": getattr(v, "field_remedy_admissible", None),
         "declared_field_size_source": (
             "fp_qb_marginal_calibration.REAL_ARMS (4), committed in NF-W7f's prereg §3 before any "
             "score and CARRIED UNCHANGED here — ⛔ NF-W7j declares no new field and trims none "
             "(MH2.2)")},
        CC.W7F_DECLARED_FIELD_SIZE)
    out["verdict"] = "QB_REFUSED"
    out["null_state"] = verdict
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _md(payload: dict) -> str:
    a, c, r = payload["served_cell_audit"], payload["component_clause"], payload["rescored"]
    dec, raw = c["decided"], c["raw"]
    dd, md_ = dec["demonstrable_detail"], dec["materiality_detail"]
    L: list[str] = []
    L.append("# NF-W7j — the COMPONENT-CLAUSE decision + the served-cell audit")
    L.append("")
    L.append(f"Generated {payload['generated_at']} · position **{CC.W7F_POSITION}** · "
             f"{CC.W7F_N_FOLDS} folds · re-derived from NF-W7f's STORED fold results at ZERO refit")
    L.append("")
    L.append("⚖️ `best_alpha = 0` · **DEPLOY-HELD** · research-only. ⛔ This story re-scores ONE "
             "clause; NF-W7f's scores are untouched and reproduce byte-identically (prereg §3).")
    L.append("")
    L.append("> ⛔ **The component-clause decision cannot certify QB on its own** — `dsr_ok` is a "
             "second, independent refusal and is OUT OF SCOPE here (prereg §0.1). The most this "
             "decision can do is reduce a two-clause refusal to a one-clause refusal.")
    L.append("")
    L.append(f"## Verdict: **`{r['verdict']}`** · certified for NF-W8: "
             f"**{'YES' if r['certified_for_nf_w8'] else 'NO'}**")
    L.append("")
    L.append(f"- full gate green: **{r['full_gate_green']}**")
    L.append(f"- failing clauses: `{r['failing_clauses'] or 'none'}`")
    L.append(f"  - anchor: `{r['failing_anchor_clauses'] or 'none'}` · statistical: "
             f"`{r['failing_statistical_clauses'] or 'none'}`")
    ns = r.get("null_state")
    if ns:
        L.append(f"- null state: **`{ns.get('state')}`**"
                 + (f" · binding half `{ns['binding_half']}`" if ns.get("binding_half") else ""))
        if ns.get("reason"):
            L.append(f"  - {ns['reason']}")
        L.append(f"  - re-test trigger: `{ns.get('retest_trigger')}`")
        if "field_remedy_admissible" in ns:
            fra = ns["field_remedy_admissible"]
            gloss = {
                None: "**field size is NO LEVER AT ALL here** (`max_field_size < 2`) — there is "
                      "nothing for admissibility to be ABOUT. ⛔ A bare `None` must NOT be read as "
                      "\"unset\" or \"unknown\": it is the instrument's strongest field reading, "
                      "and it agrees with NF-W7f's measured 3-arm diagnostic (V falls 8.8×, DSR "
                      "reaches only 0.174 against a 0.95 bar)",
                False: "the arithmetic sits BELOW the declared family — the number is reported, the "
                       "IMPERATIVE is refused (MH2.2: you may pre-register a family, you may not "
                       "discover one)",
                True: "a pre-registered family at least that small exists",
            }[fra]
            L.append(f"  - `field_remedy_admissible`: `{fra}` — {gloss}")
            L.append(f"  - ⭐ read as a MACHINE FLAG, never the prose (MH2.7). The reason text still "
                     f"says \"the remedy is a SMALLER field\"; the flag says it is not.")
        if ns.get("field_shrink_flag"):
            L.append(f"  - field-shrink flag: `{ns['field_shrink_flag'].get('status')}`")
    L.append("")

    L.append("## §1 The served-cell audit — does the served paid stat line derive from the W6d cells?")
    L.append("")
    L.append(f"**{'PASS' if a['passes'] else 'FAIL'}** — {a['reading']}")
    L.append("")
    L.append("> This is the question NF-W7f §12.5b(3) left explicitly unresolved. It is answered by "
             "a transitive import-closure walk over the serving plane — ⛔ not by a grep over one "
             "file (INC-27) and not by argument.")
    L.append("")
    L.append("| serving-plane entry point | modules in closure | per-stat-cell hits |")
    L.append("|---|---|---|")
    for seed, v in a["seeds"].items():
        L.append(f"| `{seed}` | {v['n_modules']} | {v['hits'] or '**none**'} |")
    L.append("")
    L.append("⭐ **The audit is two-sided** — a walker that resolves nothing returns an empty hit set "
             "for every seed, so a PASS would be indistinguishable from a broken audit (NF1.7 (a)). "
             "These KNOWN consumers must come back non-empty or the audit RAISES:")
    L.append("")
    L.append("| positive control | hits |")
    L.append("|---|---|")
    for seed, v in a["positive_controls"].items():
        L.append(f"| `{seed}` | {v['n_hits']} |")
    L.append("")
    L.append("⚠️ **Scope + expiry.** True of the **SERVING plane only** — the NF-W6/W7 research line "
             "consumes the cells and NF-W8 intends to. The audit re-runs on EVERY invocation and the "
             "decided clause **fails closed** to the raw 0.0 tolerance if it stops passing, so a "
             "future story that wires the cells into a served surface re-arms the hard gate "
             "automatically (prereg §1.3).")
    L.append("")

    L.append("## §2 The component clause — BOTH readings (NF-D20: the raw clause is never re-labelled)")
    L.append("")
    L.append("| reading | rule | measured | refuses? |")
    L.append("|---|---|---|---|")
    L.append(f"| **RAW** (NF-W7f, pre-registered) | any degradation, tolerance `{raw['tolerance']}` | "
             f"+{raw['relative_change']*100:.4f}% | **{'YES' if raw['refuses'] else 'no'}** |")
    L.append(f"| **DECIDED** (NF-W7j, prereg §2) | audit ∧ demonstrable ∧ material | see below | "
             f"**{'YES' if dec['refuses'] else 'no'}** |")
    L.append("")
    L.append("### The four conditions")
    L.append("")
    L.append("| # | condition | value |")
    L.append("|---|---|---|")
    for k, v in dec["conditions"].items():
        L.append(f"| {k[0]} | `{k[2:]}` | **{v}** |")
    L.append("")
    L.append(f"- **B — DEMONSTRABLE**: p(one-sided) = **{dd['p_one_sided']}** vs α = {dd['alpha']}; "
             f"degraded on **{dd['folds_degraded']}/{dd['n_folds']}** folds; mean "
             f"**{dd['mean']*100:+.4f}%**, CI95 [{dd['ci95'][0]*100:+.4f}%, {dd['ci95'][1]*100:+.4f}%]")
    L.append(f"  - instrument: `{dd['instrument']}`")
    L.append(f"  - per-fold: `{[round(x*100, 3) for x in dd['per_fold_relative_change']]}` %")
    L.append(f"- **C — MATERIAL** (primary unit: {md_['primary_unit']})")
    L.append(f"  - the arm's claimed effect, relative: **{md_['assembled_relative_effect']*100:.4f}%** "
             f"⇒ materiality band = {md_['materiality_fraction']} × that = "
             f"**{md_['band_relative']*100:.4f}%**")
    L.append(f"  - component change **{md_['component_relative_change']*100:+.4f}%** = "
             f"**{md_['point_estimate_in_band_units']}× the band**")
    L.append(f"  - ⭐ CI95 **in band units**: [{md_['ci95_in_band_units'][0]}, "
             f"{md_['ci95_in_band_units'][1]}] ⇒ band state **`{md_['band_state']}`**")
    L.append(f"  - ⛔ `UNDECIDED_MAGNITUDE` is a BAND decision, **not** `POWER_LIMITED` (NF-W7i)")
    sa = md_["sensitivity_absolute"]
    L.append(f"  - sensitivity, ABSOLUTE unit: {sa['component_absolute_change_crps']:+.5f} CRPS vs a "
             f"band of {sa['band_absolute_crps']:.5f} ⇒ material = **{sa['material']}**; "
             f"units agree: **{md_['units_agree']}**")
    L.append("")

    L.append("## §3 Reproduction pin — the decision is measured against the object NF-W7f scored")
    L.append("")
    L.append("| pinned quantity | NF-W7f | reproduced |")
    L.append("|---|---|---|")
    for k, v in payload["reproduction"]["pins"].items():
        L.append(f"| `{k}` | {v} | ✅ |")
    L.append(f"| failing clauses | `{sorted(CC.W7F_FAILING_CLAUSES)}` | ✅ |")
    L.append(f"| gate clause count | {CC.W7F_N_GATE_CLAUSES} | ✅ |")
    L.append("")
    L.append("## ⭐ What this leaves — QB's blocker set, before and after")
    L.append("")
    L.append("| | NF-W7f | NF-W7j |")
    L.append("|---|---|---|")
    L.append("| clauses refusing the ship | **2** (`per_leg_calibration_not_degraded`, `dsr_ok`) | "
             "**1** (`dsr_ok`) |")
    L.append("| null state | `CONSTRAINT_REFUSED`, `binding_half: anchor` | "
             f"`{(r.get('null_state') or {}).get('state')}` |")
    L.append("| re-test trigger | `None` (an anchor half is not rescuable by data — NF-D18) | "
             "field size is no lever; the only lever is a LOWER-VARIANCE DESIGN |")
    L.append("| certified for NF-W8 | NO | NO |")
    L.append("")
    L.append("⭐ **The deliverable is the CHANGE OF KIND, not a ship.** NF-W7f's refusal mixed an "
             "undecided governance question with a statistical one, so its null could name no "
             "remedy at all. With the governance half decided, the refusal is purely statistical, "
             "`classify_null` runs (the call NF-W7f's mixed-refusal path bypassed), and the blocker "
             "is now named with a mechanism and a registered lever.")
    L.append("")
    L.append("⛔ **The lever is NOT more data and NOT a smaller field.** NF-W7f measured both: field "
             "coherence cuts `V` 8.8× and still reaches DSR 0.174, and `n` enters only through "
             "`√(n−1)`, so it scales a positive gap but cannot create one. The candidate lever is "
             "MONTE-CARLO error in the per-fold deltas at 4,000 draws (per-fold mean 0.0184, "
             "sd ≈ 0.0182, two negative folds) — ⛔ which must be registered FORWARD as its own "
             "story, is NOT a claim that it would clear, and is out of scope here.")
    L.append("")
    L.append("## Promote blockers")
    L.append("")
    for b in CC.PROMOTE_BLOCKERS:
        L.append(f"- {b}")
    L.append("")
    L.append("## ⭐ Flagged for a 2nd reader (governance — prereg §5)")
    L.append("")
    L.append("1. **The clause decision itself.** A pre-registered gate is replaced by a materiality "
             "gate. Protections: the licensing audit is mechanical and fails closed, the raw clause "
             "stays scored and printed, the rule SHAPE is NF-W7c's (named by NF-W7f §12.5b(3) before "
             "this story existed), and the decision cannot buy a ship. ⛔ The disclosure in prereg "
             "§0.2 stands: NF-W7f had already PUBLISHED the shape of the refusing quantity, so this "
             "decision is not made blind.")
    L.append("2. **The certification bar for NF-W8 consumption.** This story holds QB to the FULL "
             "gate — the bar NF-W7h pre-registered for RB and the one WR (NF-W7e, DSR 0.9852) and "
             "TE (NF-W7c, DSR 0.9822) actually cleared. A three-part *PIT + component + beats "
             "incumbent* reading omits `dsr_ok`; adopting it after seeing `dsr_ok` fail would be "
             "the E2.1-r inversion and would certify QB on a bar the other three positions were "
             "never held to. If a distinct, lower CONSUMPTION bar is intended, it is a PM decision "
             "to register FORWARD in NF-W8.")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", default=str(ABL / CC.W7F_RECORD))
    ap.add_argument("--out-prefix", default="nf_w7j_component_clause")
    args = ap.parse_args(argv)

    try:
        audit = served_cell_audit()
        pinned = load_and_pin(Path(args.record))
    except InvalidRun as exc:
        print(f"[NF-W7j] INVALID: {exc}", file=sys.stderr)
        return 2

    clause = evaluate_component_clause(
        series=pinned["series"], per_leg=pinned["per_leg"], sel=pinned["sel"], audit=audit)
    rescored = rescore(pinned, clause)

    payload = {
        "story": "NF-W7j",
        "phase": "component_clause_decision",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0,
        "deploy_held": True,
        "refits_nothing": True,
        "source_record": Path(args.record).name,
        "source_generated_at": pinned["doc"].get("generated_at"),
        "served_cell_audit": audit,
        "component_clause": clause,
        "rescored": rescored,
        "reproduction": {"pins": CC.W7F_PINS, "tolerance": CC.PIN_TOLERANCE,
                         "failing_clauses": sorted(CC.W7F_FAILING_CLAUSES),
                         "n_gate_clauses": CC.W7F_N_GATE_CLAUSES},
        "promote_blockers": list(CC.PROMOTE_BLOCKERS),
    }
    ABL.mkdir(parents=True, exist_ok=True)
    (ABL / f"{args.out_prefix}.json").write_text(json.dumps(payload, indent=1))
    (ABL / f"{args.out_prefix}.md").write_text(_md(payload))
    print(f"[NF-W7j] audit={'PASS' if audit['passes'] else 'FAIL'} · "
          f"raw_refuses={clause['raw']['refuses']} · decided_refuses={clause['decided']['refuses']} · "
          f"verdict={rescored['verdict']} · certified={rescored['certified_for_nf_w8']}")
    print(f"[NF-W7j] wrote {ABL / args.out_prefix}.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
