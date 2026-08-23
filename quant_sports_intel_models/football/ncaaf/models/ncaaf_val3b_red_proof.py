"""RED proof for the NCAAF-VAL3b guards.

Every break is applied IN-PROCESS to the real source, and the mutation is asserted to be UNIQUE, to
have LANDED on disk, and to have REMOVED the target — the three ways a RED proof has lied in this
repo (E11.24 #682 "it didn't write", #815 "it wrote but didn't move the asserted predicate",
prediction_log "it landed on the WRONG symbol"). Backups are restored at START-UP too, so a kill
mid-mutation cannot leave a broken tree.

⛔ `except BaseException`, not `Exception`: pytest's `Failed` derives from `BaseException`, so an
inner failure would otherwise sail through and the proof would report SUCCESS (NF-W6c).

⭐ The breaks are chosen to attack the SUCCESSOR SHAPE specifically — a study whose declared field
is smaller than its parent's is exactly the thing a reader should be suspicious of, so each of the
conditions that make the narrowing admissible gets a break that removes it.

  uv run python quant_sports_intel_models/football/ncaaf/models/ncaaf_val3b_red_proof.py
"""
import subprocess
import sys
from pathlib import Path

M = Path("quant_sports_intel_models/football/ncaaf/models")
V3B = M / "ncaaf_val3b_single_contrast.py"
PAR = M / "ncaaf_val3b_serve_parity.py"
TEST = "betting_ml/tests/test_ncaaf_val3b_single_contrast.py"

BREAKS: list[tuple[str, Path, str, str]] = [
    # ── the field: what makes PBO inapplicable at all ──────────────────────────────────────────
    ("field: a second selectable arm appears (PBO stops being inapplicable)", V3B,
     'CANDIDATES: tuple[str, ...] = (CANDIDATE,)',
     'CANDIDATES: tuple[str, ...] = (CANDIDATE, "shrunk_bucket")'),
    ("field: the declared field size is padded", V3B,
     "DECLARED_FIELD_SIZE = 2", "DECLARED_FIELD_SIZE = 8"),
    ("field: a δ-SCALING arm is registered (the inadmissible-λ shape)", V3B,
     '    Arm("oracle_bucket", "diagnostic",',
     '    Arm("over_scale", "candidate", "2x the bucket constant", "cold", "over2"),\n'
     '    Arm("oracle_bucket", "diagnostic",'),
    ("field: a matched FOIL is smuggled back in as a 'diagnostic'", V3B,
     '    Arm("matched_n_bucket", "diagnostic",',
     '    Arm("week_blind", "diagnostic", "the pooled magnitude on cold rows", "cold", '
     '"pooled_cold"),\n    Arm("matched_n_bucket", "diagnostic",'),

    # ── PBO: INAPPLICABLE, never a number ──────────────────────────────────────────────────────
    ("PBO: a two-arm CSCV number is computed after all", V3B,
     '            "pbo": None,\n            "pbo_state": "INAPPLICABLE",',
     '            "pbo": float(pbo_cscv(np.zeros((4, 2)), higher_is_better=False).pbo),\n'
     '            "pbo_state": "INAPPLICABLE",'),
    ("PBO: the state is recorded as a PASS rather than as inapplicable", V3B,
     '            "pbo_state": "INAPPLICABLE",',
     '            "pbo_state": "INAPPLICABLE", "pbo_pass": True,'),
    ("PBO: `classify_null` is told a padded arm count (resurrecting the fold trigger)", V3B,
     "            metric=\"crps_total_wk1_3\", n_folds=n_folds, n_arms=len(CANDIDATES),",
     "            metric=\"crps_total_wk1_3\", n_folds=n_folds, n_arms=4,"),

    # ── V: the bar the successor is accused of lowering ────────────────────────────────────────
    ("V: the PARENT's measured dispersion is imported into the BINDING call", V3B,
     "VAR_TRIALS_SR: float | None = None", "VAR_TRIALS_SR: float | None = 0.05878"),
    ("V: the DSR sensitivity stops carrying the parent's harsher bar", V3B,
     '    ("val3_full_field", 8, 0.05878),', '    ("val3_full_field", 2, 0.125),'),
    ("V: a sensitivity is allowed to BIND", V3B,
     '"clears_gate": bool(r.dsr >= DSR_GATE), "binds": False}',
     '"clears_gate": bool(r.dsr >= DSR_GATE), "binds": True}'),

    # ── materiality: the bars VAL3 handed forward ──────────────────────────────────────────────
    ("M2: the literal drifts away from its derivation", V3B,
     "MATERIAL_REL_CRPS_GAIN = 0.007543", "MATERIAL_REL_CRPS_GAIN = 0.001"),
    ("M2: the derivation check stops being able to refuse", V3B,
     "    if abs(derived - MATERIAL_REL_CRPS_GAIN) > tol:",
     "    if False and abs(derived - MATERIAL_REL_CRPS_GAIN) > tol:"),
    ("M1: VAL2's inherited band is quietly relaxed", V3B,
     "MATERIAL_BIAS_PTS = 1.00", "MATERIAL_BIAS_PTS = 0.10"),
    ("M1: the bias clause reads the SIGNED move so a sign flip counts as a reduction", V3B,
     "    bias_reduction = abs(foil_bias) - abs(arm_bias)",
     "    bias_reduction = foil_bias - arm_bias"),
    ("M2: the relative gain becomes an ABSOLUTE one (σ- and scale-dependent again)", V3B,
     "    rel_gain = (foil_crps - arm_crps) / foil_crps",
     "    rel_gain = foil_crps - arm_crps"),

    # ── the clauses are the parent's, called ───────────────────────────────────────────────────
    ("clauses: C1–C8 become a local COPY instead of the parent's function", V3B,
     "    clauses = V3.ship_clauses(CANDIDATE, arm_rows, foil, anchors)",
     "    def ship_clauses(*a, **k):\n        return {'C1_x': {'ok': True}}\n"
     "    clauses = ship_clauses(CANDIDATE, arm_rows, foil, anchors)"),
    ("estimator: the parent's in-fold estimator is replaced by a local one", V3B,
     "        infold = V3.infold_oos(df_sorted, feat, cols, fold.eval_year)",
     "        infold = V3.infold_oos(df_sorted, feat, cols, fold.eval_year + 1)"),

    # ── the pin ────────────────────────────────────────────────────────────────────────────────
    ("pin: the date leg becomes a BINDING target again", V3B,
     'PIN_REPORTED_ONLY: tuple[str, ...] = ("cache_assembled_at",)',
     'PIN_REPORTED_ONLY: tuple[str, ...] = ()'),
    ("pin: a population leg stops binding", V3B,
     '        "n_oos_games": (int(len(oos)), PIN["n_oos_games"]),', "        "),
    ("pin: `all_ok` stops reading the binding legs", V3B,
     '    return {"checks": out, "all_ok": all(v["ok"] for v in out.values() if v["binds"]),',
     '    return {"checks": out, "all_ok": True,'),
    ("pin: the source stops naming the parent it came from", V3B,
     '    "source": "ncaaf_val3_s1_serve_reanchor.json (S1-serve --stage finalize, '
     'repaired _clv_eval)",',
     '    "source": "hand-set",'),

    # ── the runner does not clobber its parent's record ────────────────────────────────────────
    ("output: the runner writes over the PARENT's decided record", V3B,
     '_OUT_MD = _RESULTS / "ncaaf_val3b_single_contrast_table.md"',
     '_OUT_MD = _RESULTS / "ncaaf_val3_cold_start_readout.md"'),

    # ── the descriptive market read ────────────────────────────────────────────────────────────
    ("tilt: the row-misaligned `_clv_eval` is resurrected", V3B,
     '        "over_tilt": V3.over_tilt_report(df, oos, arm_folds),',
     '        "over_tilt": B._clv_eval(df, oos, arm_folds),'),
    ("tilt: the implementation stops being NAMED", V3B,
     '        "over_tilt_implementation": ("ncaaf_val3_cold_start_mu.over_tilt_report',
     '        "over_tilt_impl": ("ncaaf_val3_cold_start_mu.over_tilt_report'),

    # ── the parity check ───────────────────────────────────────────────────────────────────────
    ("parity: leg (iii) reverts to the SUBSTRING check that returned a FALSE PASS", PAR,
     "    assigns = _week_col_assignments(_SNAPSHOT_PY, STUDY_WEEK_COL)\n"
     "    aliases = [a for a in assigns if a[\"is_raw_week_alias\"]]\n"
     "    honest = [a for a in assigns if not a[\"is_raw_week_alias\"]]\n"
     "    ok = bool(honest) and not aliases",
     "    assigns = _week_col_assignments(_SNAPSHOT_PY, STUDY_WEEK_COL)\n"
     "    aliases = [a for a in assigns if a[\"is_raw_week_alias\"]]\n"
     "    honest = [a for a in assigns if not a[\"is_raw_week_alias\"]]\n"
     "    ok = STUDY_WEEK_COL in _SNAPSHOT_PY.read_text()"),
    ("parity: an `.astype()` cast is allowed to launder a raw-week alias", PAR,
     '        base = rhs.split(".astype")[0].split(".to_numpy")[0].strip()',
     '        base = rhs.strip()'),
    ("parity: ONE green leg is enough to permit a pre-opener ship", PAR,
     '    ok = all(l["ok"] for l in legs)', '    ok = any(l["ok"] for l in legs)'),
]


def restore() -> None:
    for p in (V3B, PAR):
        b = p.with_suffix(p.suffix + ".redbak")
        if b.exists():
            p.write_text(b.read_text())
            b.unlink()


restore()                                        # a prior kill may have left a mutation on disk
red = 0
for i, (label, path, old, new) in enumerate(BREAKS, 1):
    src = path.read_text()
    n = src.count(old)
    if n != 1:
        print(f"{i:>2}. {label}\n    ⛔ ANCHOR NOT UNIQUE ({n} occurrences) — verdict VOID")
        continue
    path.with_suffix(path.suffix + ".redbak").write_text(src)
    mutated = src.replace(old, new, 1)
    path.write_text(mutated)
    try:
        on_disk = path.read_text()
        assert on_disk == mutated and on_disk != src, "the mutation did not LAND"
        assert (old not in on_disk) or (old in new), "it landed but did not REMOVE the target"
        r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header",
                            "-p", "no:cacheprovider"], capture_output=True, text=True)
    except BaseException as e:                   # ⛔ pytest's Failed derives from BaseException
        restore()
        print(f"{i:>2}. {label}\n    ⛔ HARNESS ERROR ({e}) — verdict VOID")
        continue
    restore()
    ok = r.returncode != 0
    red += ok
    tail = [ln for ln in r.stdout.splitlines()
            if "passed" in ln or "failed" in ln or "error" in ln]
    print(f"{i:>2}. {label}\n    {'RED ✅' if ok else 'GREEN ❌ — THE GUARD IS VACUOUS'}  {tail[-1:]}")

print(f"\n{red}/{len(BREAKS)} deliberate breaks caught")
restore()
sys.exit(0 if red == len(BREAKS) else 1)
