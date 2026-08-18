"""NF-W7i RED proof — break the source, prove each guard goes RED.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w7i.py

A guard that cannot FAIL is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness applies one
deliberate defect at a time and asserts the named guard turns RED. Four disciplines the repo has
paid for, all enforced here:

- **The mutation must LAND** (E11.24 #682) — a shell-quoting/no-op break reports a FALSE "the guard
  is vacuous", which reads as a real finding and invites weakening a correct guard. Mutations are
  applied IN-PROCESS and the file is asserted to have changed.
- **The anchor must be UNIQUE** (E11.24 #815 sibling) — two functions with byte-identical tails make
  a single-occurrence replace land on the WRONG symbol, and the run comes back green reporting a
  false vacuity. Every anchor is asserted to occur exactly once.
- **The asserted token must be GONE** (#815) — a mutation that writes but does not move the asserted
  predicate is a false GREEN.
- **A stalled harness reports HUNG**, never silently green: each pytest leg runs under a timeout and
  a timeout is a distinct, loud outcome.

⛔ Not a pytest module: it MUTATES tracked source and restores it in a `finally`. It is run by hand
(and by the story's closeout), never collected by the suite.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_MODULE = Path(__file__).with_name("direct_points_ceiling.py")
_RUNNER = Path(__file__).with_name("run_nf_w7i_direct_ceiling.py")
_TESTS = _ROOT / "betting_ml/tests/test_nf_w7i_direct_ceiling.py"
_TIMEOUT_S = 300


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    tests: tuple[str, ...]
    defect: str


BREAKS: tuple[Break, ...] = (
    Break("peek_is_in_sample_again", _MODULE,
          "out[hold] = fit_direct(test.loc[~hold], test.loc[hold], features)",
          "out[hold] = fit_direct(test, test.loc[hold], features)",
          ("test_no_declared_peek_is_an_in_sample_fit_on_the_block",),
          "reinstates NF-W7h's defect: the peek fits the WHOLE block it predicts"),
    Break("matched_window_sized_to_full_block", _MODULE,
          "n = max(int(round(len(test) * (CROSSFIT_K - 1) / CROSSFIT_K)), MIN_BANK_ROWS)",
          "n = max(len(test), MIN_BANK_ROWS)",
          ("test_matched_window_is_sized_to_the_peeks_effective_n_not_the_full_block",),
          "NF-W6b-C's false near-tie: the control gets ~1.5× the peek's rows"),
    Break("matched_control_peeks", _MODULE,
          'extra = train.sort_values("gw").tail(int((~hold).sum()))',
          "extra = test.loc[~hold]",
          ("test_the_augmented_control_never_uses_a_single_test_row",),
          "the honest control reaches into the TEST block — the attribution becomes vacuous"),
    Break("activity_rule_dropped", _MODULE,
          'active_forms = [f for f in ORACLE_FORMS if per_form[f]["oracle_beats_matched_n"]\n'
          '                    and per_form[f]["mean_delta"] is not None]',
          'active_forms = [f for f in ORACLE_FORMS if per_form[f]["mean_delta"] is not None]',
          # ⛔ Only the clause that actually DETECTS this break is named: listing a test the
          # mutation does not move would imply coverage the harness has not proven (NF-D17).
          ("test_an_inactive_form_cannot_carry_the_headline_however_large_its_ceiling",),
          "an INACTIVE peek carries the headline (NF-W6d / NF-D20)"),
    Break("unevaluable_collapsed_to_no", _MODULE,
          'if not sel["active_forms"]:',
          "if False:",
          ("test_no_active_form_is_UNEVALUABLE_and_is_never_reported_as_a_NO",),
          "'the instrument could not measure it' is reported as 'RB has no headroom'"),
    Break("immaterial_band_removed", _MODULE,
          "elif pct < CEILING_BANDS[0]:",
          "elif pct < 0.0:",
          ("test_the_bands_decide_the_answer",
           "test_a_demonstrable_but_immaterial_ceiling_is_refused"),
          "a demonstrable-but-immaterial ceiling licenses a bake-off (NF-W6)"),
    Break("thin_bank_defaults", _MODULE,
          'raise ValueError(f"{STORY}: bank fit on {len(v)} rows < {MIN_BANK_ROWS} — REFUSED, never "\n'
          '                         f"defaulted (NF1.7 (a))")',
          "pass",
          ("test_a_thin_bank_refuses_rather_than_defaulting",),
          "a bank that failed to fit silently becomes a passing anchor"),
    Break("retest_trigger_published", _MODULE,
          'd["retest_trigger"] = None',
          'd["retest_trigger"] = "re-run after two more seasons"',
          ("test_rb_is_never_given_a_season_or_fold_retest_trigger",),
          "publishes the misleading 'more seasons' trigger NF-D18 forbids"),
    Break("incomplete_field_accepted", _MODULE,
          'raise ValueError(f"{STORY}: fold {i} is missing declared labels {missing} — REFUSED; "',
          'pass  # noqa\n            _unused = (f"{STORY}: {missing} "',
          ("test_an_incomplete_declared_field_refuses",),
          "a field scored with a declared label silently absent is read as the declared field"),
    Break("weight_length_unchecked", _MODULE,
          'raise ValueError(f"{STORY}: sample_weight is {len(w)} for {len(y)} rows — REFUSED")',
          "pass",
          ("test_the_weighted_fit_refuses_a_mismatched_weight_vector",),
          "a mismatched weight vector is silently broadcast/truncated"),
    Break("positive_control_cannot_refuse", _RUNNER,
          "            raise AssertionError(",
          "            _skip = (",
          ("test_the_positive_control_is_wired_and_fails_the_smoke_when_blind",),
          "a BLIND instrument reports a ceiling instead of refusing the smoke"),
)


def _run(tests: tuple[str, ...]) -> tuple[str, str]:
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    for t in tests:
        args += [f"{_TESTS}::{t}"]
    try:
        p = subprocess.run(args, cwd=_ROOT, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "HUNG", f"no verdict within {_TIMEOUT_S}s"
    tail = (p.stdout or p.stderr).strip().splitlines()
    return ("RED" if p.returncode != 0 else "GREEN"), (tail[-1] if tail else "")


def main() -> int:
    rows, failures = [], 0
    for b in BREAKS:
        original = b.path.read_text()
        occurrences = original.count(b.old)
        if occurrences != 1:
            rows.append((b.name, "ANCHOR", f"anchor occurs {occurrences}× — must be exactly 1"))
            failures += 1
            continue
        try:
            mutated = original.replace(b.old, b.new, 1)
            b.path.write_text(mutated)
            on_disk = b.path.read_text()
            if on_disk == original:
                rows.append((b.name, "NO-OP", "mutation did not LAND (E11.24 #682)"))
                failures += 1
                continue
            if b.old in on_disk:
                rows.append((b.name, "TOKEN", "asserted token still present (#815)"))
                failures += 1
                continue
            verdict, note = _run(b.tests)
        finally:
            b.path.write_text(original)
        rows.append((b.name, verdict, note))
        if verdict != "RED":
            failures += 1

    w = max(len(r[0]) for r in rows)
    print(f"\nNF-W7i RED proof — {len(BREAKS)} deliberate defects\n")
    for name, verdict, note in rows:
        mark = "✅" if verdict == "RED" else "❌"
        print(f"{mark} {name:<{w}}  {verdict:<6} {note[:88]}")
    print(f"\n{len(rows) - failures}/{len(rows)} guards proven to FAIL on broken source.")
    if failures:
        print("⛔ a guard that stayed GREEN on a deliberate defect is VACUOUS — fix it, and do "
              "NOT weaken it to match (a false vacuity report reads as a real finding).")
    # restore-integrity check: every mutated file must be byte-identical to its committed state
    diff = subprocess.run(["git", "diff", "--stat", "--", str(_MODULE), str(_RUNNER)],
                          cwd=_ROOT, capture_output=True, text=True)
    if diff.stdout.strip():
        print(f"\n⚠️ source not restored cleanly:\n{diff.stdout}")
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
