"""RED proof for the NCAAB-P0 guards: break the source, prove each guard goes red.

Run:  uv run python betting_ml/tests/ncaab_p0_red_proof.py

⛔ NOT a pytest module (no `test_` prefix) — it MUTATES SOURCE FILES on disk and restores them.
Collecting it into the suite would let a mutation escape into an unrelated run.

THE FOUR CONTROLS, each present because a RED proof without it can report a false result:

  1. UNIQUE ANCHOR — the string being replaced must occur EXACTLY ONCE in the target file.
     Two functions with byte-identical tails make `replace(old, new, 1)` land on the WRONG one,
     and the harness then reports "the guard is vacuous" when the guard is fine and the break
     missed. A false VACUITY report is the dangerous direction: it invites weakening a correct
     guard.

  2. BASELINE PASS — the guard must pass on UNMUTATED source before any break is applied. A
     guard that is already red proves nothing when it is red again.

  3. NOT-SELECTED — pytest exits non-zero for many reasons, and "no tests matched this node id"
     is one of them. A harness that reads any non-zero exit as RED would score a typo'd node id
     as a passing proof. So the collected count is asserted to be non-zero, and a run that
     collected nothing is reported as NOT-SELECTED rather than as a pass.

  4. RESOLVE EVERY NODE — every break's target node id must exist. A break aimed at a renamed
     test silently proves nothing, which is how a RED proof rots as the suite is refactored.

Plus the mutation-landed check (#682) AND the token-gone check (#815): a mutation that writes
but does not move the asserted predicate comes back GREEN and reads as a vacuous guard. Both
are asserted, because "it did not land" and "it landed but did not bite" are different faults.

⭐ Stale backups are restored AT START-UP, before anything else. This harness's own worst case
is being killed mid-mutation (E11.26), which would otherwise leave a deliberately-broken file
on disk for the next session to find.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARDS = "betting_ml/tests/test_ncaab_p0_foundation.py"
SUFFIX = ".ncaab_p0_red_proof.bak"


@dataclass(frozen=True)
class Break:
    label: str
    path: str
    old: str
    new: str
    node: str          # the test node id expected to go RED
    why: str           # what a GREEN here would mean


BREAKS: tuple[Break, ...] = (
    Break(
        label="fan-out ceiling truncates instead of refusing",
        path="quant_sports_intel_models/basketball/ncaab/ingest/budget.py",
        old="    if n_events > ceiling:\n        bulk = HISTORICAL_GAME_LINE_SNAPSHOT",
        new="    if False:\n        bulk = HISTORICAL_GAME_LINE_SNAPSHOT",
        node=f"{GUARDS}::TestFanOutCeilingRefusesRatherThanTruncating::"
             "test_it_never_silently_returns_a_truncated_count",
        why="a board-sized fan-out would be silently priced and allowed",
    ),
    Break(
        label="the refusal stops naming the cheaper bulk alternative",
        path="quant_sports_intel_models/basketball/ncaab/ingest/budget.py",
        old='f"It would cost {cost:,} credits. The SAME board is available from ONE bulk "\n'
            '            f"/odds snapshot for {bulk} credits ({cost // max(bulk, 1)}x cheaper) — use the "\n'
            '            f"bulk call. If a genuine per-event repair of more than {ceiling} events is "',
        new='f"It would cost {cost:,} credits. "\n'
            '            f"Refused. If a genuine per-event repair of more than {ceiling} events is "',
        node=f"{GUARDS}::TestFanOutCeilingRefusesRatherThanTruncating::"
             "test_the_refusal_names_the_cheaper_alternative",
        why="the refusal would be worked around by raising the ceiling",
    ),
    Break(
        label="an in-season empty landing stops escalating",
        path="quant_sports_intel_models/basketball/ncaab/ingest/sources.py",
        old="    if in_season(when):\n        return (f\"🚨 {spec.name}: ZERO ROWS landed",
        new="    if False:\n        return (f\"🚨 {spec.name}: ZERO ROWS landed",
        node=f"{GUARDS}::TestLandingStatesAreThreeNotTwo::test_an_in_season_empty_escalates",
        why="the repo's silent-empty signature would land quietly in February",
    ),
    Break(
        label="absence classification collapses to always-quiet",
        path="quant_sports_intel_models/basketball/ncaab/ingest/sources.py",
        old="    if season == season_for(when) and not in_season(when):\n        return None",
        new="    if season == season_for(when):\n        return None",
        node=f"{GUARDS}::TestLandingStatesAreThreeNotTwo::"
             "test_absence_is_quiet_pre_season_and_loud_in_season",
        why="a feed that vanished mid-season would be indistinguishable from pre-season",
    ),
    Break(
        label="the season label loses its July cut",
        path="quant_sports_intel_models/basketball/ncaab/ingest/sources.py",
        old="    return d.year + 1 if d.month >= 7 else d.year",
        new="    return d.year",
        node=f"{GUARDS}::TestSeasonLabelling::test_season_for",
        why="the ingest would silently load LAST season's file, which exists, with no error",
    ),
    Break(
        label="the monitor's season window narrows below the ingest's",
        path="betting_ml/monitoring/ncaab_freshness.py",
        old="SEASON_MONTHS: tuple[int, ...] = (11, 12, 1, 2, 3, 4)",
        new="SEASON_MONTHS: tuple[int, ...] = (11, 12, 1, 2, 3)",
        node=f"{GUARDS}::TestFreshnessContractsAreDeclaredNotArmed::"
             "test_the_season_window_contains_every_in_season_day",
        why="the monitor would be blind on live April game days",
    ),
    Break(
        label="NCAAB grows its own fork of the shared lake layer",
        path="quant_sports_intel_models/basketball/ncaab/ingest/sources.py",
        # ⚠️ This break REPLACES the seam import rather than adding a line beside it. The first
        # cut PREPENDED a football import and left `from .lake import SPORT` in place, so the
        # harness's token-gone control (#815) correctly refused it: a mutation that writes
        # without removing the asserted token can leave the predicate unmoved, and a GREEN
        # there would have read as a vacuous guard rather than as a bad break.
        old="from .lake import SPORT  # noqa: F401 — re-exported; the sport prefix has one owner",
        new="from quant_sports_intel_models.football.nfl.ingest.s3io import DEFAULT_BUCKET  "
            "# noqa: F401\nSPORT = \"ncaab\"",
        node=f"{GUARDS}::TestNcaabDoesNotForkTheSharedLakeLayer::"
             "test_every_lake_import_goes_through_the_single_seam",
        why="the single seam would erode one import at a time",
    ),
)


def _restore_all(quiet: bool = False) -> int:
    """Control 0: restore any stale backup BEFORE doing anything else."""
    n = 0
    for bak in REPO.rglob(f"*{SUFFIX}"):
        target = bak.with_suffix("")
        if target.suffix == "":  # ".py.bak" -> strip only our suffix
            target = pathlib.Path(str(bak)[: -len(SUFFIX)])
        target.write_text(bak.read_text())
        bak.unlink()
        n += 1
        if not quiet:
            print(f"  ↺ restored stale backup: {target.relative_to(REPO)}")
    return n


def _pytest(node: str) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _collected(out: str) -> int:
    """How many tests actually RAN. Control 3: a run that collected nothing is NOT a pass."""
    m = re.search(r"(\d+) (?:passed|failed|error)", out)
    if not m:
        return 0
    return sum(int(x) for x in re.findall(r"(\d+) (?:passed|failed)", out))


def main() -> int:
    stale = _restore_all()
    if stale:
        print(f"(restored {stale} stale backup(s) before starting)\n")

    # ── Control 4: every target node must RESOLVE.
    print("Control: resolve-every-node")
    unresolved = []
    for b in BREAKS:
        rc, out = _pytest(b.node)
        if _collected(out) == 0:
            unresolved.append(b.label)
            print(f"  ❌ NOT-SELECTED  {b.label}")
        else:
            print(f"  ✅ resolves      {b.label}")
    if unresolved:
        print(f"\n⛔ {len(unresolved)} node(s) do not resolve — those breaks would prove nothing.")
        return 1

    # ── Control 2: baseline must be GREEN.
    print("\nControl: baseline-pass")
    rc, out = _pytest(GUARDS)
    n = _collected(out)
    if rc != 0 or n == 0:
        print(f"  ❌ baseline is not green (rc={rc}, collected={n}) — a RED proves nothing here")
        print(out[-1500:])
        return 1
    print(f"  ✅ baseline green: {n} guards pass on unmutated source")

    # ── The breaks.
    print("\nBreaks")
    failures = 0
    for b in BREAKS:
        path = REPO / b.path
        src = path.read_text()

        # Control 1: UNIQUE ANCHOR.
        occurrences = src.count(b.old)
        if occurrences != 1:
            print(f"  ❌ {b.label}: anchor occurs {occurrences}x (must be exactly 1) — the "
                  f"mutation could land on the wrong symbol and report a false vacuity")
            failures += 1
            continue

        bak = pathlib.Path(str(path) + SUFFIX)
        bak.write_text(src)
        try:
            mutated = src.replace(b.old, b.new, 1)
            path.write_text(mutated)

            # #682: the mutation LANDED.  #815: the token is GONE (it wrote AND it bit).
            on_disk = path.read_text()
            if on_disk == src:
                print(f"  ❌ {b.label}: mutation did not land on disk")
                failures += 1
                continue
            if b.old in on_disk:
                print(f"  ❌ {b.label}: mutation landed but the original token survives — the "
                      f"asserted predicate may not have moved")
                failures += 1
                continue

            rc, out = _pytest(b.node)
            collected = _collected(out)
            if collected == 0:
                print(f"  ❌ {b.label}: NOT-SELECTED under mutation (collected 0) — a non-zero "
                      f"exit here would be a false RED")
                failures += 1
            elif rc == 0:
                print(f"  ❌ {b.label}: guard stayed GREEN on broken source — VACUOUS. "
                      f"Without it, {b.why}.")
                failures += 1
            else:
                print(f"  ✅ RED  {b.label}")
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    # Control 2 again: the restore must be complete.
    rc, out = _pytest(GUARDS)
    if rc != 0:
        print("\n⛔ the suite is NOT green after restore — a mutation leaked. Check git status.")
        return 1
    print(f"\nRestored clean; suite green again ({_collected(out)} guards).")

    print(f"\n{len(BREAKS) - failures}/{len(BREAKS)} breaks went RED.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
