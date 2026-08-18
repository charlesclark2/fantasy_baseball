"""RED proof for NCAAF-PS's guards — `uv run python betting_ml/tests/ncaaf_ps_red_proof.py`.

Every claim in `test_ncaaf_game_prediction_snapshot.py` is proved by RE-INTRODUCING the defect it
guards against and requiring the named test to go RED. A green suite proves nothing on its own: it
is exactly what a vacuous guard also produces (NF1.7 (a) / INC-38 / NF-D17).

Harness contract (the accumulated rules — a red proof has at least four ways to lie; identical to
`ncaaf_p2_1_s1b_red_proof.py`, deliberately, so there is ONE harness shape in this vertical):

  * the mutation anchor must be **UNIQUE** in the file — two byte-identical tails make
    `replace(old, new, 1)` land on the WRONG symbol and the run returns a FALSE "vacuous guard",
    the dangerous direction because it invites weakening a correct guard (E11.24 prediction_log);
  * the mutation must be asserted to have **LANDED** — a silently no-op'd break reads as "caught"
    (E11.24 #682);
  * where the guard asserts on a TOKEN, that token must be asserted **GONE** afterwards — a break
    that lands without moving the asserted predicate is a false GREEN (E11.24 #815);
  * pytest runs in a **SUBPROCESS**, so a `pytest.raises` `Failed` (a `BaseException`) cannot leak
    past a too-narrow `except` and read as a pass (NF-W6c);
  * ⚠️ ONLY exit code 1 (tests FAILED) counts as RED — 2/3/4/5 is a BROKEN HARNESS, never a caught
    break, or a syntax error reads as "the guard caught it" (NF-INFRA1);
  * every file is restored in a `finally`.

⭐ ISOLATION: each break flips exactly ONE clause, and each selector names a test whose fixture
satisfies every OTHER clause — so only the flipped clause can change the result (NF-D17: a fixture
that trips two clauses proves neither).

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~90 s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_ncaaf_game_prediction_snapshot.py"
_M = "quant_sports_intel_models/football/ncaaf/models/game_prediction_snapshot.py"
_Q = "quant_sports_intel_models/football/ncaaf/ingest/query_lake.py"
_J = "pipeline/jobs/sports_ncaaf_prediction_snapshot_job.py"
_S = "pipeline/schedules/sports_ncaaf_prediction_snapshot_schedules.py"

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS: list[tuple[str, str, str, str, str, str | None]] = [
    # ── 1. the leakage gate ─────────────────────────────────────────────────────────────────────
    ("leakage: the bound goes non-strict (a kickoff AT the snapshot instant is admitted)", _M,
     "    late = kick <= snap",
     "    late = kick < snap",
     "exactly_at_the_snapshot_instant", "late = kick <= snap"),
    ("leakage: the gate can never fire (a post-kickoff row is written as a 'prediction')", _M,
     "    late = kick <= snap",
     "    late = kick < kick - pd.Timedelta(days=3650)",
     "date_based_not_week_based", "late = kick <= snap"),
    ("leakage: an already-started game is admitted", _M,
     "    late = kick <= snap",
     "    late = kick < kick - pd.Timedelta(days=3650)",
     "already_kicked_off", "late = kick <= snap"),
    ("leakage: an UNPARSEABLE kickoff passes instead of refusing (NF1.7 a)", _M,
     "    unusable = snap.isna() | kick.isna()",
     "    unusable = snap.isna() & kick.isna() & False",
     "unparseable_kickoff", "unusable = snap.isna() | kick.isna()"),
    ("leakage: a MISSING kickoff column passes instead of refusing (NF1.7 a)", _M,
     '        if col not in rows.columns:',
     '        if False:',
     "kickoff_column_is_absent_entirely", None),
    ("selection: the horizon lower bound stops excluding already-started games", _M,
     '    lo = _utc_ts(snapshot_ts) + pd.Timedelta(minutes=float(min_lead_minutes))',
     '    lo = _utc_ts(snapshot_ts) - pd.Timedelta(days=30)',
     "by_kickoff_instant_not_by_week", None),
    ("selection: the K−buffer is ignored", _M,
     '    sel = out[(out["commence_dt"].notna()) & (out["commence_dt"] > lo) & (out["commence_dt"] <= hi)]',
     '    sel = out[(out["commence_dt"].notna()) & (out["commence_dt"] > _utc_ts(snapshot_ts)) & (out["commence_dt"] <= hi)]',
     "min_lead_minutes_is_a_k_minus_buffer", None),
    ("tz: a naive snapshot instant is read as machine-LOCAL rather than UTC", _M,
     '    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")',
     '    return t.tz_localize("America/Los_Angeles").tz_convert("UTC") if t.tzinfo is None else t.tz_convert("UTC")',
     "naive_snapshot_instant_is_read_as_utc", None),

    # ── 2. never lose a prior week ──────────────────────────────────────────────────────────────
    ("merge: writes ONLY the new batch (the P0.6b destructive-overwrite landmine)", _M,
     "    combined = pd.concat([kept, new], ignore_index=True, sort=False)",
     "    combined = new.copy()",
     "second_snapshot_never_deletes_the_first", None),
    ("merge: the re-covered-key filter is inverted (a re-run duplicates instead of replacing)", _M,
     "    keep = ~existing[list(key)].astype(str).apply(tuple, axis=1).isin(keys)",
     "    keep = existing[list(key)].astype(str).apply(tuple, axis=1).notna()",
     "replaces_rather_than_duplicates", None),
    ("merge: an EMPTY new batch is accepted (a silent full-partition rewrite)", _M,
     "    if new.empty:",
     "    if False:",
     "no_op_on_an_empty_frame", None),
    ("lake read: a TRANSIENT failure is swallowed into 'nothing to preserve'", _Q,
     "            if is_missing_table_error(exc):",
     "            if True:",
     "transient_lake_read_raises", None),

    # ── 3. the served contract is covered, or we refuse ─────────────────────────────────────────
    ("contract: a MISSING served column is scored anyway (mean-imputed to 0.0 — NF-C0e)", _M,
     "    if missing:",
     "    if False:",
     "missing_served_column_refuses", None),
    ("contract: an all-NULL non-pace column is scored anyway", _M,
     "    if all_null:",
     "    if False:",
     "all_null_non_pace_column_refuses", None),
    ("assembly: a team with no strength row is IMPUTED rather than dropped", _M,
     "        out = out[~unpriceable].reset_index(drop=True)",
     "        out = out.reset_index(drop=True)",
     "no_strength_row_is_dropped_not_imputed", None),
    ("serving: the season-sim mode is served (the interval is UNDER-stated)", _M,
     "    sigma_margin, sigma_total = matchup_sigma(served.dispersion, strength_var, fixed_strength=False)",
     "    sigma_margin, sigma_total = matchup_sigma(served.dispersion, strength_var, fixed_strength=True)",
     "full_posterior_predictive_not_the_season_sim_mode", None),

    # ── 4. the payload makes no claim ───────────────────────────────────────────────────────────
    ("framing: an edge/pick column is admitted", _M,
     "    if offending:",
     "    if False:",
     "edge_or_pick_column_is_refused", None),
    ("framing: a non-zero best_alpha is admitted", _M,
     '    if "best_alpha" in rows.columns and not (rows["best_alpha"].astype(float) == 0.0).all():',
     "    if False:",
     "nonzero_best_alpha_is_refused", None),

    # ── 5. the schedule is wired ────────────────────────────────────────────────────────────────
    ("schedule: ships RUNNING (fires before the operator's P1.2 re-fit)", _S,
     "    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring",
     "    default_status=DefaultScheduleStatus.RUNNING,",
     "stopped", "DefaultScheduleStatus.STOPPED"),   # both the source scan AND the live object
    ("schedule: the cron starts in September and misses the 8/29 opener", _S,
     'NCAAF_PREDICTION_SNAPSHOT_CRON = "0 9 * 8-12,1 2"',
     'NCAAF_PREDICTION_SNAPSHOT_CRON = "0 9 * 9-12,1 2"',
     "fires_before_the_2026_opener", '"0 9 * 8-12,1 2"'),
    ("schedule: the horizon shrinks so the last pre-opener fire cannot reach the opener", _J,
     'SNAPSHOT_HORIZON_DAYS = float(os.environ.get("NCAAF_SNAPSHOT_HORIZON_DAYS", "7"))',
     'SNAPSHOT_HORIZON_DAYS = float(os.environ.get("NCAAF_SNAPSHOT_HORIZON_DAYS", "1"))',
     "fires_before_the_2026_opener", None),
    ("job: the futures leaf loses its dependency on the game snapshot", _J,
     "    ncaaf_futures_snapshot_op(start=ncaaf_prediction_snapshot_op())",
     "    ncaaf_prediction_snapshot_op()\n    ncaaf_futures_snapshot_op(start=ncaaf_prediction_snapshot_op.alias('x')())",
     "futures_leaf_is_downstream", None),
    ("job: reaches for a deploy-ephemeral gitignored artifact (NF-INFRA1)", _J,
     "    season = current_season()\n    context.log.info(\n        \"NCAAF prediction snapshot: season=%s",
     "    season = current_season()\n    duck = os.environ.get(\"SPORTS_DUCKDB_PATH\")\n    context.log.info(\n        \"NCAAF prediction snapshot: season=%s",
     "no_deploy_ephemeral_artifact", None),
]


def main() -> int:
    failures: list[str] = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()

        occurrences = original.count(old)
        if occurrences == 0:
            print(f"{'BROKEN ❌ (anchor not found)':34} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        if occurrences > 1:
            print(f"{'BROKEN ❌ (anchor x%d)' % occurrences:34} {name}")
            failures.append(f"{name}: anchor appears {occurrences}× in {rel} — not unique")
            continue

        mutated = original.replace(old, new, 1)
        if mutated == original:                     # #682 — the break must actually land
            print(f"{'BROKEN ❌ (mutation no-op)':34} {name}")
            failures.append(f"{name}: mutation did not change the file")
            continue
        if gone is not None and gone in mutated:    # #815 — the asserted token must be GONE
            print(f"{'BROKEN ❌ (token survives)':34} {name} -> {gone!r} still present")
            failures.append(f"{name}: asserted token survived the mutation")
            continue

        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:34} {name}\n{'':34} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every NCAAF-PS guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
