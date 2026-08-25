#!/usr/bin/env python
"""ncaaf_p3_1b_red_proof.py — prove every NCAAF-P3.1b guard actually FAILS on a deliberate break.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / INC-39). This harness applies one
deliberate defect at a time to the real source, runs the named test(s), and REQUIRES a failure.

The spec names three directions and all three are broken here: a post-kickoff snapshot must be
REFUSED, a valid T-1 must ATTACH, and an absent line must STAY absent.

THREE WAYS A RED PROOF ITSELF LIES, each guarded (this repo has hit all three):

  1. **THE MUTATION NEVER LANDED** (#682) — a quoting or anchor bug edits nothing and the run comes
     back green, reported as "the guard is vacuous". Every break asserts the file CHANGED.
  2. **THE ANCHOR WAS NOT UNIQUE** (#815 sibling) — a single-occurrence replace lands on the WRONG
     symbol and the guard never sees its mutation. A false VACUITY report is the dangerous
     direction: it reads as a finding and invites weakening a correct guard. Every anchor is
     asserted to occur EXACTLY ONCE.
  3. **IT LANDED BUT DID NOT MOVE THE ASSERTED PREDICATE** (#815) — a rename that still satisfies
     an `x in src` check. Where a break is meant to REMOVE a token, its absence is asserted too.

⚠️ Restores happen in a `finally`, and any stale backup from a previous killed run is restored at
START-UP — a source-mutating harness's worst case is being killed mid-mutation, which leaves the
deliberate break on disk (E11.26).

Run:  uv run python betting_ml/tests/ncaaf_p3_1b_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TEST = "betting_ml/tests/test_ncaaf_p3_1b_market_source.py"

CONTRACT = _REPO / "app/backend/models/ncaaf.py"
PAYLOADS = _REPO / "quant_sports_intel_models/football/ncaaf/serving/payloads.py"
WRITER = _REPO / "scripts/write_ncaaf_serving_store.py"
BAKEOFF = _REPO / "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_game.py"
PANEL = _REPO / "frontend/components/ncaaf/market-comparison.tsx"

#: (label, file, old, new, pytest -k selector, token that must DISAPPEAR or None)
BREAKS: list[tuple[str, Path, str, str, str, str | None]] = [
    # ── direction 1: a valid T-1 must ATTACH, and under its own label ────────────────────────
    ("the close is preferred over the T-1 line again",
     PAYLOADS,
     "    (MARKET_SOURCE_T1, \"t1_\"),\n    (MARKET_SOURCE_CLOSE, \"close_\"),",
     "    (MARKET_SOURCE_CLOSE, \"close_\"),\n    (MARKET_SOURCE_T1, \"t1_\"),",
     "t1_line_is_preferred or t1_only_kickoff or as_of_always_equals", None),

    ("a T-1 line is served under the `close` label (the mislabel this story fixes)",
     PAYLOADS,
     'MARKET_SOURCE_T1 = "odds_api_historical_t_minus_1"',
     'MARKET_SOURCE_T1 = "odds_api_historical_close"',
     "t1_only_kickoff or t1_line_is_preferred or differing_only_in_source",
     '"odds_api_historical_t_minus_1"'),

    ("`as_of` is dropped from the served block (the E9.41 silent strip)",
     CONTRACT,
     "    as_of: str | None = None",
     "    # as_of removed",
     "additive_over_what_the_deployed_client or declared_field_is_on_the_wire",
     "    as_of: str | None = None"),

    ("`as_of` is stamped from the OTHER candidate's instant",
     PAYLOADS,
     '        return {"status": "available", "reason": None, "source": source,\n'
     '                "as_of": line["snapshot_ts"], **line}',
     '        return {"status": "available", "reason": None, "source": source,\n'
     '                "as_of": _s(market_row.get("close_snapshot_ts")), **line}',
     "as_of_always_equals", None),

    # ── direction 2: a post-kickoff snapshot must be REFUSED ──────────────────────────────────
    ("the leakage guard is removed entirely",
     PAYLOADS,
     "        if not snapshot < kickoff:",
     "        if False:",
     "at_or_after_kickoff or refusal_is_logged or out_of_bounds_close",
     "if not snapshot < kickoff:"),

    ("the guard accepts a snapshot exactly AT kickoff",
     PAYLOADS,
     "        if not snapshot < kickoff:",
     "        if not snapshot <= kickoff:",
     "at_or_after_kickoff", None),

    ("a refused row attaches its numbers anyway instead of nothing",
     PAYLOADS,
     "            refusal = refusal or MARKET_REASON_NOT_PRE_KICKOFF\n            continue",
     '            return {"status": "available", "reason": None, "source": source,\n'
     '                    "as_of": line["snapshot_ts"], **line}',
     "at_or_after_kickoff", None),

    ("the refusal is swallowed instead of logged loudly",
     PAYLOADS,
     '            log.warning(\n                "[ALERT] NCAAF market line REFUSED for game_id=%s source=%s: snapshot %s is NOT "',
     '            log.debug(\n                "[ALERT] NCAAF market line REFUSED for game_id=%s source=%s: snapshot %s is NOT "',
     "refusal_is_logged", None),

    ("the guard FAILS OPEN when the kickoff instant cannot be read",
     PAYLOADS,
     "        if kickoff is None or snapshot is None:",
     "        if snapshot is None:",
     "kickoff_we_cannot_read", None),

    ("the guard FAILS OPEN when the snapshot instant cannot be read",
     PAYLOADS,
     "        if kickoff is None or snapshot is None:",
     "        if kickoff is None:",
     "snapshot_instant_we_cannot_read", None),

    ("the builder stops handing the kickoff to the guard (the guard cannot run at all)",
     PAYLOADS,
     '        "market": _market(market_row, read_failed=market_read_failed,\n'
     '                          commence_time=row.get("commence_time"), game_id=row.get("game_id")),',
     '        "market": _market(market_row, read_failed=market_read_failed),',
     "payload_passes_the_kickoff", "commence_time=row.get"),

    ("one refused candidate blanks the whole block instead of falling through",
     PAYLOADS,
     "            refusal = refusal or MARKET_REASON_NOT_PRE_KICKOFF\n            continue",
     "            return _unavailable_market(MARKET_REASON_NOT_PRE_KICKOFF)",
     "refused_t1_does_not_veto_a_valid_close", None),

    # ── direction 3: absent must STAY absent, and the causes stay distinguishable ─────────────
    ("a refusal renders identically to 'nobody priced this kickoff'",
     PAYLOADS,
     'MARKET_REASON_NOT_PRE_KICKOFF = "market_snapshot_not_pre_kickoff"',
     'MARKET_REASON_NOT_PRE_KICKOFF = "no_line_captured_for_this_kickoff"',
     "distinguishable_from_never_having_been_priced",
     '"market_snapshot_not_pre_kickoff"'),

    ("an unprovable instant renders identically to a refused one",
     PAYLOADS,
     'MARKET_REASON_INSTANT_UNPROVABLE = "market_snapshot_instant_unprovable"',
     'MARKET_REASON_INSTANT_UNPROVABLE = "market_snapshot_not_pre_kickoff"',
     "distinguishable_from_never_having_been_priced",
     '"market_snapshot_instant_unprovable"'),

    ("a staging row with no numbers is served as an `available` blank",
     PAYLOADS,
     '    if all(line[k] is None for k in\n'
     '           ("home_spread", "total", "home_moneyline_american",\n'
     '            "home_moneyline_implied_probability")):\n        return None',
     "    if False:\n        return None",
     "carrying_no_numbers_is_absent", None),

    # ── the staging read: one join, opt-in, and the kind string that must not drift ───────────
    ("the T-1 columns land in the DEFAULT frame and become model features",
     BAKEOFF,
     "def build_clv_staging(min_year: int = 2020, *, with_t1: bool = False) -> pd.DataFrame:",
     "def build_clv_staging(min_year: int = 2020, *, with_t1: bool = True) -> pd.DataFrame:",
     "opt_in_so_they_can_never_become_a_model_feature", None),

    ("the serving writer stops asking for the T-1 leg",
     WRITER,
     "clv = build_clv_staging(min_year=int(season), with_t1=True)",
     "clv = build_clv_staging(min_year=int(season))",
     "serving_writer_is_the_caller_that_opts_in",
     "build_clv_staging(min_year=int(season), with_t1=True)"),

    ("the T-1 leg forks into a second copy of the join",
     BAKEOFF,
     "    latest as (   -- the single latest pre-commence snapshot per event\n"
     "        select *, row_number() over (partition by event_id order by snap_ts desc) rn from snaps\n"
     "    ),",
     "    latest as (\n"
     "        select *, row_number() over (partition by event_id order by snap_ts {'asc' if prefix == 't1_' else 'desc'}) rn from snaps\n"
     "    ),",
     "same_join_filtered_by_snapshot_kind", None),

    ("the T-1 filter names a snapshot kind nothing writes (a silently EMPTY read)",
     BAKEOFF,
     '_SNAPSHOT_KIND_T1 = "t_minus_1"',
     '_SNAPSHOT_KIND_T1 = "t1"',
     "snapshot_kind_string_matches_the_ingest_module", '"t_minus_1"'),

    ("the DEFAULT leg grows a kind filter, changing the mart P1.4 was decided on",
     BAKEOFF,
     '    kind_filter = "" if kind is None else (',
     '    kind_filter = "" if kind == "never" else (',
     "same_join_filtered_by_snapshot_kind", None),

    # ── the run log, and the no-client-change claim ───────────────────────────────────────────
    ("the run log stops saying WHICH line attached",
     WRITER,
     '        market_lines_by_source=_count_by(slates, "source"),',
     "        market_lines_by_source={},",
     "real_write_run_reports_which_line", '_count_by(slates, "source")'),

    ("the panel starts branching on WHICH snapshot it is (a client change is now needed)",
     PANEL,
     "  const available = market.status === \"available\"",
     "  const available = market.status === \"available\" && market.source !== null",
     "branches_on_status_not_on_which_snapshot", None),

    ("the panel drops its reason fallback, so a new reason renders as a blank",
     PANEL,
     "          {(market.reason && MARKET_REASON_COPY[market.reason]) || MARKET_REASON_FALLBACK}",
     "          {market.reason && MARKET_REASON_COPY[market.reason]}",
     "absent_reason_copy_falls_back", "MARKET_REASON_FALLBACK}"),

    # ⚠️ This break edits the COMMITTED FIXTURE, not the generator: this suite reads the fixture
    # bytes, so a generator-only mutation would be a false GREEN (#815 — it lands but does not move
    # the asserted predicate). The generator↔fixture link is RED-proven by P3.2's own
    # `test_the_generated_fixtures_are_the_shipping_builders_own_output`.
    ("the shipped market fixture stops carrying a recognisable source",
     _REPO / "frontend/e2e/fixtures/api/ncaaf-slate-2026-08-29-market.synthetic.json",
     '"source": "odds_api_historical_close",\n        "snapshot_ts": "2025-10-03T22:50:39Z",',
     '"source": "somewhere_else",\n        "snapshot_ts": "2025-10-03T22:50:39Z",',
     "generated_e2e_fixtures_still_clear", None),
]


def _run(selector: str) -> bool:
    """True iff pytest FAILED (which is the outcome a break must produce)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", _TEST, "-q", "-k", selector, "--no-header", "-p",
         "no:cacheprovider"],
        cwd=_REPO, capture_output=True, text=True)
    if "no tests ran" in proc.stdout or "collected 0 items" in proc.stdout:
        print(f"      ⚠️  selector {selector!r} matched NO tests — the proof would be vacuous")
        return False
    return proc.returncode != 0


def main() -> int:
    backups = {p: p.with_suffix(p.suffix + ".redproof.bak") for p in {b[1] for b in BREAKS}}
    for original, backup in backups.items():
        if backup.exists():
            print(f"⚠️  restoring stale backup for {original.name}")
            original.write_text(backup.read_text())
            backup.unlink()

    print("baseline (all guards, unbroken source) …", end=" ", flush=True)
    base = subprocess.run([sys.executable, "-m", "pytest", _TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    if base.returncode != 0:
        print("FAILED — fix the suite before RED-proving it")
        print(base.stdout[-3000:])
        return 1
    print("green ✅")

    reds = 0
    for label, path, old, new, selector, must_vanish in BREAKS:
        src = path.read_text()
        occurrences = src.count(old)
        if occurrences != 1:
            print(f"❌ {label}\n      anchor occurs {occurrences}× in {path.name} — a "
                  "non-unique anchor can land the break on the WRONG symbol (#815)")
            continue
        backup = backups[path]
        backup.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            landed = path.read_text()
            assert landed != src, f"the mutation for {label!r} did not land on disk"
            if must_vanish is not None and must_vanish in landed:
                print(f"❌ {label}\n      the break landed but {must_vanish!r} is still present — "
                      "it would not move the asserted predicate (#815)")
                continue
            went_red = _run(selector)
        finally:
            path.write_text(backup.read_text())
            backup.unlink()
        print(("🔴 RED  " if went_red else "❌ GREEN") + f"  {label}")
        reds += int(went_red)

    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    return 0 if reds == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
