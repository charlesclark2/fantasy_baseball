"""NF-W8-0d — the RED proof: every guard is shown to FAIL on deliberately broken source.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w8_0d.py

A guard that cannot fail is worse than no guard (NF1.7 (a) / INC-38 / NF-D17). This harness makes
each clause earn its keep by breaking the ONE thing it claims to defend and requiring the suite to
go RED — and it is written against the four ways a RED proof has lied in this repo:

- **#682 — the mutation must LAND.** Every break asserts the file actually changed on disk;
  a break that silently no-ops reports a FALSE "the guard is vacuous", the dangerous direction.
- **E11.24/#815 — the anchor must be UNIQUE, and the token must be GONE.** Two functions with
  byte-identical tails make a single-occurrence `replace` land on the WRONG symbol; each break
  asserts its anchor occurs exactly once and that the anchor is absent afterwards.
- **NF-W6c — catch `BaseException`.** A clause asserting through `pytest.raises` raises
  `_pytest.outcomes.Failed`, which derives from `BaseException`; an `except Exception` harness lets
  a deliberate break sail straight through and reports SUCCESS.
- **E11.26 — restore a stale backup AT START-UP.** This harness's own worst case is being killed
  mid-mutation, which would leave broken source on disk; it heals that before doing anything else.

⛔ Run with `uv run` — a bare `python3` with no pytest makes a missing-pytest non-zero exit read as
"the guard caught it", a FALSE red (NF-INFRA1).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "fp_dsr_frontier.py"
BACKUP = TARGET.with_suffix(".py.redproof.bak")
SUITE = "betting_ml/tests/test_nf_w8_0d_dsr_frontier.py"
ROOT = Path(__file__).resolve().parents[4]

Break = tuple[str, str, str, str]   # (label, old, new, the clause it must turn RED)

BREAKS: list[Break] = [
    ("the statistic loses its |·| — an overshooting arm stops being penalised",
     "    abs_inc = np.abs(bias[INCUMBENT])\n    return {a: abs_inc - np.abs(bias[a]) for a in REAL_ARMS}",
     "    inc = bias[INCUMBENT]\n    return {a: inc - bias[a] for a in REAL_ARMS}",
     "TestTheKnownCaseIsPinned"),
    ("`scale_dispersion` scales the MEAN too, so it stops being a pure dispersion change",
     "    mu = float(d.mean())\n    return mu + (d - mu) * float(c)",
     "    return d * float(c)",
     "TestTheLockstepInvariant"),
    ("the split-field carrier ignores `n_trials` and charges multiplicity at the reduced size",
     "    base = np.arange(n, dtype=float)",
     "    base = np.arange(len(s), dtype=float)",
     "TestTheSplitFieldCarrier"),
    ("`synth_trials_for_split_field` accepts a single retained Sharpe (deflating by ZERO)",
     '    if len(s) < 2:\n        raise ValueError(f"a split-field `V` needs',
     '    if len(s) < 0:\n        raise ValueError(f"a split-field `V` needs',
     "TestTheSplitFieldCarrier"),
    ("the verdict binds on `P(clear)` instead of the MEDIAN",
     '    clears = bool(feas["dsr_median"] >= DSR_MIN)',
     '    clears = bool(feas.get("p_clears", 0.0) >= 0.40)',
     "TestTheVerdictBindsOnTheMedian"),
    ("an INFEASIBLE grid point is allowed to carry the verdict",
     '    pool = [r for r in rows if r["feasible"]] if feasible_only else list(rows)',
     '    pool = list(rows)',
     "TestTheVerdictBindsOnTheMedian"),
    ("an unknown scaling law silently falls back instead of raising",
     '    raise ValueError(f"unknown scaling law `{law}` — the declared laws are {LAWS}; an '
     'unrecognised "\n                     f"law must RAISE, never silently default to one of them")',
     "    return 1.0",
     "TestTheFrontierRefusesRatherThanGuessing"),
    ("a non-positive excess variance is silently clamped to zero",
     '        "excess_var": excess,',
     '        "excess_var": max(excess, 1e-12),',
     "TestTheDecompositionAndTheStructuralBound"),
    ("the paired-noise bound reports the LEVEL's sd, erasing the cancellation finding",
     "        sd = math.sqrt(max(worst_shift * (raw_shift - worst_shift), 0.0))",
     "        sd = sigma_row",
     "TestTheDecompositionAndTheStructuralBound"),
    ("the paired-noise bound reports its most FAVOURABLE rung instead of its worst",
     '    worst = max(ladder, key=lambda r: r["share_of_level_variance"])',
     '    worst = min(ladder, key=lambda r: r["share_of_level_variance"])',
     "TestTheDecompositionAndTheStructuralBound"),
    ("`lockstep_is_live` passes unconditionally, so a dead ladder scores healthy",
     '    srs = [r["winner_sharpe"] for r in rows]\n    return len(srs) >= 2 and all(abs(b) > abs(a) + 1e-9 for a, b in zip(srs, srs[1:]))',
     "    return True",
     "TestTheLockstepInvariant"),
    ("the granularity floor silently DROPS a point instead of marking it infeasible",
     '            granular = block_weeks >= MIN_BLOCK_WEEKS',
     '            granular = True',
     "TestTheDeclaredConstantsAreInherited"),
    ("`load_observed` tolerates an evaluable fold that is absent from `fold_results`",
     '    if missing:\n        raise KeyError',
     '    if False:\n        raise KeyError',
     "TestTheRecordReaderRefusesAnInconsistentRecord"),
]


def _run(node: str = "") -> int:
    target = f"{SUITE}::{node}" if node else SUITE
    r = subprocess.run([sys.executable, "-m", "pytest", target, "-q",
                        "--no-header", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    if "no tests ran" in r.stdout or "ERROR: not found" in r.stdout:
        # ⚠️ a selector that matches NOTHING exits non-zero and would read as a RED — the vacuous
        # -proof failure mode this harness exists to rule out (NF1.7 (a)).
        print(f"❌ the selector `{target}` matched NO tests — a non-zero exit from an empty "
              f"selection is not a RED")
        return 0
    return r.returncode


def main() -> int:
    # E11.26 — heal a stale backup FIRST: this harness's own worst case is dying mid-mutation.
    if BACKUP.exists():
        print("⚠️  a stale backup was on disk — restoring it before doing anything else")
        TARGET.write_text(BACKUP.read_text())
        BACKUP.unlink()

    original = TARGET.read_text()
    BACKUP.write_text(original)
    reds = 0
    try:
        if _run() != 0:
            print("❌ the suite is not GREEN on unbroken source — nothing below is interpretable")
            return 1
        print(f"✅ baseline GREEN  ({SUITE})\n")
        for label, old, new, node in BREAKS:
            n = original.count(old)
            if n != 1:
                print(f"❌ ANCHOR NOT UNIQUE ({n} occurrences) for: {label}")
                return 1
            broken = original.replace(old, new, 1)
            if broken == original:
                print(f"❌ the mutation did not change the file for: {label}")
                return 1
            TARGET.write_text(broken)
            landed = TARGET.read_text()
            if old in landed:                     # #815 — the token must be GONE
                print(f"❌ the mutation landed but the anchor SURVIVES for: {label}")
                return 1
            rc = _run(node)
            TARGET.write_text(original)
            if rc == 0:
                print(f"❌ GREEN on broken source — {node} is VACUOUS for: {label}")
            else:
                reds += 1
                print(f"✅ RED  {node:<52s} ← {label}")
    except BaseException:                          # NF-W6c — `Failed` is not an `Exception`
        TARGET.write_text(original)
        raise
    finally:
        TARGET.write_text(original)
        if BACKUP.exists():
            BACKUP.unlink()
    print(f"\n{reds}/{len(BREAKS)} deliberate breaks turned the suite RED")
    return 0 if reds == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
