"""RED proof for the NCAAF-VAL3 guards.

Every break is applied IN-PROCESS to the real source, the mutation is asserted to be UNIQUE, to have
LANDED on disk, and to have REMOVED the target — the three ways a RED proof has lied in this repo
(E11.24 #682 "it didn't write", #815 "it wrote but didn't move the asserted predicate",
prediction_log "it landed on the wrong symbol"). Backups are restored at START-UP too, so a kill
mid-mutation cannot leave a broken tree.

⛔ `except BaseException`, not `Exception`: pytest's `Failed` derives from `BaseException`, so an
inner failure would otherwise sail through and the proof would report SUCCESS (NF-W6c).

  uv run python quant_sports_intel_models/football/ncaaf/models/ncaaf_val3_red_proof.py
"""
import subprocess
import sys
from pathlib import Path

M = Path("quant_sports_intel_models/football/ncaaf/models")
V3 = M / "ncaaf_val3_cold_start_mu.py"
TEST = "betting_ml/tests/test_ncaaf_val3_cold_start_mu.py"

BREAKS: list[tuple[str, Path, str, str]] = [
    # ── C4: the market-blindness of the estimator ──────────────────────────────────────────────
    ("C4: the estimator stops refusing a market column", V3,
     "    leaks = find_market_columns(frame.columns)\n    if leaks:",
     "    leaks = find_market_columns(frame.columns)\n    if False and leaks:"),
    ("C4: the column contract stops being a contract", V3,
     "    extra = [c for c in frame.columns if c not in ESTIMATOR_COLUMNS]\n    if extra:",
     "    extra = [c for c in frame.columns if c not in ESTIMATOR_COLUMNS]\n    if False and extra:"),
    ("C4: `close_total` is admitted to the estimator contract", V3,
     'ESTIMATOR_COLUMNS: tuple[str, ...] = (WEEK_COL, "season", "mu_total", "y_total", "model_err")',
     'ESTIMATOR_COLUMNS: tuple[str, ...] = (WEEK_COL, "season", "mu_total", "y_total", '
     '"model_err", "close_total")'),
    ("C4: the peek source stops being market-blind checked", V3,
     "    src = src[list(ESTIMATOR_COLUMNS)]\n    assert_estimator_is_market_blind(src)\n    return src",
     "    src = src[list(ESTIMATOR_COLUMNS)]\n    return src"),

    # ── in-fold-ness: the admissibility argument ───────────────────────────────────────────────
    ("in-fold: the inner walk-forward is allowed to see the eval season", V3,
     '    inner = df[df["game_year"] < eval_year].reset_index(drop=True)',
     '    inner = df[df["game_year"] <= eval_year].reset_index(drop=True)'),
    ("in-fold: an outer fold with no inner fold silently returns nothing", V3,
     '    if not splits:\n        raise SystemExit(f"[{_STORY}] outer fold {eval_year} has ZERO inner folds at "',
     '    if False:\n        raise SystemExit(f"[{_STORY}] outer fold {eval_year} has ZERO inner folds at "'),
    ("in-fold: an HONEST arm is handed the peeking source", V3,
     '            src = {"oracle_bucket": peek_src, "matched_n_bucket": matched_src}.get(a.name, infold)',
     '            src = {"matched_n_bucket": matched_src}.get(a.name, peek_src)'),

    # ── the estimator forms ────────────────────────────────────────────────────────────────────
    ("form: the week-scoped correction leaks into weeks 4+", V3,
     '        d[is_cold] = delta\n        info.update({"delta": delta, "raw_mean": m, "se": se,',
     '        d[:] = delta\n        info.update({"delta": delta, "raw_mean": m, "se": se,'),
    ("form: the shrunk arm stops shrinking (it becomes a second bucket arm)", V3,
     "    return float(mean * max(0.0, 1.0 - (se * se) / (mean * mean)))",
     "    return float(mean)"),
    ("form: `over_scale` stops being 2x the bucket constant", V3,
     'delta = {"bucket": m, "over2": 2.0 * m, "shrunk": _js_shrink(m, se)}[form]',
     'delta = {"bucket": m, "over2": m, "shrunk": _js_shrink(m, se)}[form]'),
    ("form: the two matched foils stop differing in SCOPE", V3,
     '        if form == "pooled_all":\n            d[:] = m',
     '        if form == "pooled_all":\n            d[is_cold] = m'),
    ("form: an empty source returns 0.0 instead of HALTing", V3,
     '        if len(v) == 0:\n            raise SystemExit(f"[{_STORY}] form {form!r} has no cold-start source rows; an "',
     '        if False:\n            raise SystemExit(f"[{_STORY}] form {form!r} has no cold-start source rows; an "'),
    ("form: the linear ramp stops refusing a single source week", V3,
     "        if len(np.unique(w)) < 2:", "        if False:"),

    # ── the CRPS instrument ────────────────────────────────────────────────────────────────────
    ("crps: a non-positive sigma is scored instead of HALTing", V3,
     "    if np.any(sigma <= 0):", "    if False:"),
    ("crps: the closed form drops its -1/sqrt(pi) term (it stops being CRPS)", V3,
     "    return sigma * (z * (2.0 * stats.norm.cdf(z) - 1.0) + 2.0 * stats.norm.pdf(z) - _INV_SQRT_PI)",
     "    return sigma * (z * (2.0 * stats.norm.cdf(z) - 1.0) + 2.0 * stats.norm.pdf(z))"),
    ("crps: the metric becomes |bias| (a pessimism arm could then win it)", V3,
     "    z = (np.asarray(y, float) - np.asarray(mu, float)) / sigma\n    return sigma * (z",
     "    z = (np.asarray(y, float) - np.asarray(mu, float)) / sigma\n    return 0.0 * sigma + np.abs(z) * 0.0 + sigma * 0.0 * (z"),

    # ── the anchors ────────────────────────────────────────────────────────────────────────────
    ("anchor: an INACTIVE anchor pair is scored as a PASS", V3,
     '        state = ("INACTIVE" if not active else',
     '        state = ("FLOORED" if not active else'),
    ("anchor: the oracle stops being per-FORM (one bucket ceiling for the field)", V3,
     "                d_pk, i_pk = _estimate(a.form, peek_src, wk)",
     "                d_pk, i_pk = _estimate('bucket', peek_src, wk)"),
    ("anchor: the matched-n control stops being sized to the eval cell", V3,
     "        n_match = min(int(cold_mask.sum()), len(infold_cold))",
     "        n_match = len(infold_cold)"),

    # ── the gates ──────────────────────────────────────────────────────────────────────────────
    ("gate: PBO drops out of the ship rule", V3,
     '                    and r["fold_consistency_ok"] and pbo < PBO_GATE)',
     '                    and r["fold_consistency_ok"])'),
    ("gate: BH drops out of the ship rule", V3,
     '                    and r["dsr"] >= DSR_GATE and r["bh_pass"]',
     '                    and r["dsr"] >= DSR_GATE'),
    ("gate: a registered-to-LOSE arm becomes selectable", V3,
     '        return bool(spec.role == "candidate" and r["clauses"]["all_ok"]',
     '        return bool(spec.role in ("candidate", "lose") and r["clauses"]["all_ok"]'),
    ("gate: the calib floor becomes a target rather than a floor", V3,
     '        "C2_pooled_calib_floor": {"ok": bool(pooled_cal >= CALIB_FLOOR),',
     '        "C2_pooled_calib_floor": {"ok": bool(abs(pooled_cal - CALIB_FLOOR) < 0.5),'),
    ("gate: the DSR-CONV variant becomes the BINDING V", V3,
     "        d = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, var_trials_sr=V_binding)",
     "        d = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, var_trials_sr=V_convention)"),
    ("gate: the declared field size stops excluding the diagnostics", V3,
     "DECLARED_FIELD_SIZE: int = 1 + len(CANDIDATES) + len(LOSERS)",
     "DECLARED_FIELD_SIZE: int = len(ARMS)"),
    ("gate: the null classifier stops being told the declared field size", V3,
     "            declared_field_size=DECLARED_FIELD_SIZE, degenerates_excluded_from_v=False)",
     "            degenerates_excluded_from_v=False)"),
    ("gate: a deflation refusal is recorded as a plain statistical one", V3,
     '            "binding_half": ("constraint" if failed else\n'
     '                             "deflation" if deflation_failed else "statistical"),',
     '            "binding_half": ("constraint" if failed else "statistical"),'),
    ("gate: the fold-consistency clause reverts to the uncalibrated 60% rule", V3,
     "    clause = cv_power.fold_consistency_clause(n_folds)",
     "    clause = cv_power.fold_consistency_clause(n_folds, alpha=0.99)"),

    # ── the pin ────────────────────────────────────────────────────────────────────────────────
    ("pin: the targets stop naming the parent they came from", V3,
     '    "source": "ncaaf_val3_s1_serve_reanchor.json (S1-serve --stage finalize, '
     'repaired _clv_eval)",',
     '    "source": "hand-set",'),
    ("pin: a failing pin no longer HALTs", V3,
     '    if not pin["all_ok"] and not args.allow_pin_fail:',
     '    if False:'),
    ("pin: one leg stops being checked", V3,
     '        "n_oos_games": (int(len(oos)), PIN["n_oos_games"]),', "        "),

    # ── the descriptive over-tilt report ───────────────────────────────────────────────────────
    ("tilt: the market-facing report enters a ship clause", V3,
     '        "C3_cold_calib_floor": {"ok": bool(cold_cal >= CALIB_FLOOR),',
     '        "C3_cold_calib_floor": {"ok": bool(cold_cal >= CALIB_FLOOR) and "over_tilt" == "",'),
    ("tilt: the row-count invariant behind the join is dropped", V3,
     '    if len(merged) != len(oos):\n        raise SystemExit(f"[{_STORY}] the close join changed the row count; refusing to report.")',
     "    pass"),
    ("tilt: an unevaluable report renders as a number instead of a state", V3,
     '        return {"n_close_carrying_cold": 0, "over_actually_hit": None, "arms": {},\n'
     '                "state": "UNEVALUABLE",',
     '        return {"n_close_carrying_cold": 0, "over_actually_hit": 0.0, "arms": {},\n'
     '                "state": "EVALUABLE",'),
]


def restore() -> None:
    b = V3.with_suffix(V3.suffix + ".redbak")
    if b.exists():
        V3.write_text(b.read_text())
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
    tail = [ln for ln in r.stdout.splitlines() if "passed" in ln or "failed" in ln or "error" in ln]
    print(f"{i:>2}. {label}\n    {'RED ✅' if ok else 'GREEN ❌ — THE GUARD IS VACUOUS'}  {tail[-1:]}")

print(f"\n{red}/{len(BREAKS)} deliberate breaks caught")
restore()
sys.exit(0 if red == len(BREAKS) else 1)
