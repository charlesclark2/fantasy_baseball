"""nf_inj3b_m_red_proof.py — prove every NF-INJ3b-M node-1 (D4) guard FAILS on broken source.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / NF-D17). ONE break at a time; the
named test must go RED.

The three ways a RED proof itself lies are all asserted against (#682 the mutation NO-OPS · #815 it
lands but does not move the asserted predicate · E11.24 it lands on the WRONG symbol), and stale
backups are restored AT START-UP because this harness's own worst case is being killed mid-mutation
(E11.26).

⭐ Break 1 is the ORIGINAL DEFECT, restored verbatim: `run_interval_revalidation` writing its JSON
OUTSIDE the `--no-report` branch, which is exactly how NF-INJ3b's ship path rewrote NF1.9's decided
record while asking it not to write anything.

RUN:  uv run python betting_ml/tests/nf_inj3b_m_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FANTASY = ROOT / "quant_sports_intel_models/football/nfl/fantasy"
PR = FANTASY / "run_nf_tr2b_placement_read.py"
IV = FANTASY / "run_interval_revalidation.py"
TESTS = "betting_ml/tests/test_nf_inj3b_m_out_stems.py"

BREAKS: list[tuple[str, Path, str, str, str]] = [
    ("THE ORIGINAL DEFECT — the interval JSON write moves back OUTSIDE --no-report", IV,
     "    if not args.no_report:\n        _REPORT_DIR.mkdir(parents=True, exist_ok=True)\n"
     "        (_REPORT_DIR / f\"{args.out}.json\").write_text(json.dumps(out, indent=2, default=float))",
     "    _REPORT_DIR.mkdir(parents=True, exist_ok=True)\n"
     "    (_REPORT_DIR / f\"{args.out}.json\").write_text(json.dumps(out, indent=2, default=float))\n"
     "    if not args.no_report:",
     "TestTheIntervalRunnersNoReportActuallyWritesNothing::test_no_write_site_survives_outside_the_no_report_branch"),

    ("the interval report write is dropped from the branch entirely", IV,
     '        write_report(out, _REPORT_DIR / f"{args.out}.md")',
     '        pass',
     "TestTheIntervalRunnersNoReportActuallyWritesNothing::test_write_report_is_also_inside_the_branch"),

    ("the interval --out DEFAULTS back to the DECIDED stem", IV,
     '    ap.add_argument("--out", default=DEFAULT_STEM,',
     '    ap.add_argument("--out", default=DECIDED_STEM,',
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_the_out_flag_exists_and_DEFAULTS_to_the_neutral_stem[interval_revalidation]"),

    ("the placement-read --out DEFAULTS back to the DECIDED stem", PR,
     '    ap.add_argument("--out", default=DEFAULT_STEM,',
     '    ap.add_argument("--out", default=DECIDED_STEM,',
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_the_out_flag_exists_and_DEFAULTS_to_the_neutral_stem[placement_read]"),

    ("the neutral default is made IDENTICAL to the decided stem (interval)", IV,
     'DEFAULT_STEM = "nf1_9_interval_revalidation_latest"',
     'DEFAULT_STEM = "nf1_9_interval_revalidation"',
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_the_decided_stem_and_a_neutral_default_are_BOTH_declared[interval_revalidation]"),

    ("the neutral default is made IDENTICAL to the decided stem (placement)", PR,
     'DEFAULT_STEM = "nf_tr2b_placement_read_latest"',
     'DEFAULT_STEM = "nf_tr2b_placement_read"',
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_the_decided_stem_and_a_neutral_default_are_BOTH_declared[placement_read]"),

    ("a placement-read write site is HARDCODED back to the decided path", PR,
     '        (_ART / f"{a.out}.json").write_text(json.dumps(r, indent=1, default=str))',
     '        (_ART / "nf_tr2b_placement_read.json").write_text(json.dumps(r, indent=1, default=str))',
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_every_write_site_is_parameterised_by_the_out_stem[placement_read]"),

    ("an interval write site is HARDCODED back to the decided path", IV,
     '        write_report(out, _REPORT_DIR / f"{args.out}.md")',
     '        write_report(out, _OUT_MD)',
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_every_write_site_is_parameterised_by_the_out_stem[interval_revalidation]"),

    ("the placement read stops SAYING the decided record was not updated", PR,
     "        if a.out != DECIDED_STEM:",
     "        if False:",
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_a_non_decided_write_SAYS_the_decided_record_was_not_updated[placement_read]"),

    ("the interval runner stops SAYING the decided record was not updated", IV,
     "        if args.out != DECIDED_STEM:",
     "        if False:",
     "TestTheDefaultInvocationCannotTouchADecidedArtifact::test_a_non_decided_write_SAYS_the_decided_record_was_not_updated[interval_revalidation]"),
]


def _restore(bak: Path, tgt: Path) -> None:
    if bak.exists():
        tgt.write_text(bak.read_text())
        bak.unlink()


def main() -> int:
    for f in (PR, IV):                         # E11.26: restore a stale backup AT START-UP
        _restore(f.with_suffix(f.suffix + ".redbak"), f)
    red = skipped = 0
    for i, (name, target, old, new, test) in enumerate(BREAKS, 1):
        src = target.read_text()
        if src.count(old) != 1:                # E11.24: the anchor must be UNIQUE
            print(f"{i:2d}. ⚠️  SKIP (anchor not unique: {src.count(old)}×) — {name}")
            skipped += 1
            continue
        bak = target.with_suffix(target.suffix + ".redbak")
        bak.write_text(src)
        try:
            target.write_text(src.replace(old, new, 1))
            after = target.read_text()
            assert after != src, "#682: the mutation did not LAND"
            assert old not in after, "#815: the mutation landed but the token survived"
            r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{test}", "-q",
                                "--no-header", "-p", "no:cacheprovider"],
                               cwd=ROOT, capture_output=True, text=True)
            ok = r.returncode != 0
            red += ok
            print(f"{i:2d}. {'✅ RED' if ok else '❌ STAYED GREEN'} — {name}")
            if not ok:
                print("     ⚠️ VACUOUS GUARD:", r.stdout.strip().splitlines()[-1:])
        finally:
            _restore(bak, target)
    print(f"\n{red}/{len(BREAKS)} breaks went RED ({skipped} skipped)")
    return 0 if red == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
