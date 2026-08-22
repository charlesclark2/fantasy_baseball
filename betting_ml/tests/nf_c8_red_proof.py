#!/usr/bin/env python3
"""NF-C8 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_c8_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run whenever `test_nf_c8_availability_flag_copy.py` is refactored.

WHY IT EXISTS HERE SPECIFICALLY. That suite is almost entirely SOURCE INSPECTION and COPY SCREENING
— "no constant forecasts an injury", "all three surfaces render the component", "the thresholds are
one shared constant" — which is precisely the shape that reads as coverage while proving nothing.
This repo has been bitten by a source guard a COMMENT could satisfy (INC-38), by an `and`-composed
clause whose fixture a different clause already refused (NF-D17), and by a guard whose subject had
quietly moved (NF-C4). Every one was found by breaking the source, never by a green suite.

⭐ AND IT ALREADY EARNED ITS KEEP IN THIS STORY, BEFORE ANY MUTATION RAN. The injury-forecast scan
fired during the build on the story's OWN honest hedge — "it is not a forecast that he IS HURT" —
i.e. on the sentence refusing the claim. That is the NF-C6P3 negation-blind shape, and the tempting
repair (make the scan negation-aware) is a real hole, because a forecast survives negation intact.
The scan stays absolute and the hedge is worded around the token; see the note on
`_INJURY_FORECAST_VERBS`.

⚠️ EACH BREAK MUST BE PROVEN TO LAND. A mutation that silently fails to apply makes "the guard went
red" and "nothing happened" indistinguishable, and the latter reports as the scarier finding
(E11.24 #682). The anchor is checked against the file's real text before the run, a missing anchor
is a FAILURE rather than a skip, and — the E11.24 #815 refinement — each case additionally declares
the token its clause asserts on, which must be GONE after the mutation: a break that lands on disk
without moving the asserted predicate is a false GREEN.

⚠️ AND THE ANCHOR MUST BE UNIQUE (E11.24 prediction_log). `replace(old, new, 1)` on a substring that
occurs twice patches whichever comes first, which may not be the one under test — and the run then
reports a correct guard as vacuous, the dangerous direction, because a false vacuity report invites
WEAKENING a guard that is fine.

⚠️⚠️ AND IT RESTORES STALE BACKUPS **AT START-UP**, not only in its own `finally` — the E11.26
lesson, learned here the hard way. An in-memory `finally` cannot run if the process is KILLED, and
the ordinary way to kill this one is completely mundane: piping it to `head`, which closes stdout
and delivers SIGPIPE mid-mutation. That leaves the deliberately-BROKEN source on disk, and the next
thing to read it — the next red-proof run, a test run, a commit — sees a defect that is physically
present and was never authored. It happened during this story: a `| head -12` killed a run between
`write_text(patched)` and `write_text(src)`, and the following run's baseline failed on a mutation
nobody had made. So every backup is also written to `_BACKUP_DIR` before any file is touched, and
start-up restores anything left there by a previous run before it does anything else.

⛔ Deliberately not `git checkout --`: that destroys uncommitted work in the files it patches.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
LIB = REPO / "frontend/lib/fantasy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
PROJECTIONS = REPO / "frontend/components/fantasy/projections-table.tsx"
PLAYER = REPO / "frontend/components/fantasy/player-page.tsx"
SUITE = "betting_ml/tests/test_nf_c8_availability_flag_copy.py"

#: `(label, file, anchor, replacement, gone_after, the ONE test that must go red)`.
#:
#: `gone_after` is the token the named clause actually asserts on. After the mutation it must NOT be
#: in the file — otherwise the break landed without moving the assertion (E11.24 #815), and a GREEN
#: result would mean "the mutation missed", not "the guard is vacuous". `None` where the clause
#: asserts on an ABSENCE (the mutation ADDS the forbidden thing), which cannot be expressed that way.
CASES = [
    # ── ⛔⛔ the injury-forecast boundary ───────────────────────────────────────────────────────
    ("forecast an injury in the definition", COPY,
     "so it is not a forecast about his health",
     "so he will miss time",
     "not a forecast about his health",
     "test_the_flag_copy_never_forecasts_an_injury[AVAILABILITY_FLAG_DEFINITION]"),

    ("call the chip an injury risk in its own label", COPY,
     'export const AVAILABILITY_FLAG_LABEL = "Limited projected availability"',
     'export const AVAILABILITY_FLAG_LABEL = "Elevated injury risk"',
     "Limited projected availability",
     "test_the_flag_copy_never_forecasts_an_injury[AVAILABILITY_FLAG_LABEL]"),

    # ⭐ The cheapest edit in the whole story, and the one that would make an amber chip an injury
    # claim: drop the sentence that refuses the reading. Nothing else changes; the page still
    # renders; every other clause stays green.
    ("drop the not-a-diagnosis refusal", COPY,
     "This is a statement about our projection, not a diagnosis: the games figure is an",
     "The games figure is an",
     "not a diagnosis",
     "test_the_definition_says_out_loud_that_it_is_not_a_diagnosis"),

    ("make the player the subject instead of our projection", COPY,
     "We project this player for fewer games than a full season",
     "This player plays fewer games than a full season",
     "We project this player",
     "test_the_definition_names_our_projection_as_the_subject"),

    # ── the residual hedge, and the thresholds ────────────────────────────────────────────────
    ("let the flag absorb the residual", COPY,
     "It is also not the only reason a projection lands where it does",
     "It fully explains where a projection lands",
     # ⚠️ the `gone` token must be UNIQUE TO THIS CONSTANT. A bare "not the only reason" also
     # occurs in `EXPECTED_POINTS_NOTE`, so the file still contained it after the mutation and
     # the run reported a MIS-LANDED break for a break that landed perfectly.
     "not the only reason a projection lands where it does",
     "test_the_definition_carries_the_residual_hedge"),

    ("publish the threshold in the prose", COPY,
     "We project this player for fewer games than a full season",
     "We project this player for fewer than 14 games",
     None,
     "test_the_flag_copy_publishes_no_threshold_and_no_measured_figure"),

    ("drop the per-player placeholder from the summary", COPY,
     '"Projected {games} games — limited availability priced in."',
     '"Limited availability priced in."',
     # …same trap: `{games}` also appears in the constant's own doc comment.
     "Projected {games} games",
     "test_the_summary_interpolates_the_served_games_value"),

    ("re-tune the threshold", LIB,
     "export const LIMITED_AVAILABILITY_GAMES = 12.5",
     "export const LIMITED_AVAILABILITY_GAMES = 16",
     None,
     "test_the_thresholds_are_one_shared_constant_at_the_declared_values"),

    # ⚠️ THE REGRESSION THIS STORY ACTUALLY SHIPPED: re-anchoring the threshold on the schedule.
    ("re-anchor the threshold on the schedule length", LIB,
     "export const LIMITED_AVAILABILITY_GAMES = 12.5",
     "export const LIMITED_AVAILABILITY_GAMES = FULL_SEASON_GAMES - 3",
     None,
     "test_the_threshold_is_not_anchored_on_the_schedule_length"),

    # ⭐ THE PLAUSIBLE WRONG SHAPE: the constants exist, and a surface ignores them anyway. This is
    # how three boards end up disagreeing about which rows are flagged with nothing failing.
    ("hardcode a threshold in a component", RANKINGS,
     "                          <td className=\"px-3 py-2 text-right text-gray-400\">\n"
     "                            <AvailabilityFlag",
     "                          <td className=\"px-3 py-2 text-right text-gray-400\">\n"
     "                            {p.g < 14 ? \"!\" : null}\n"
     "                            <AvailabilityFlag",
     None,
     "test_no_surface_hardcodes_its_own_availability_threshold"),

    # ⛔⛔ The display-only boundary. Reaching the optimizer makes this a model change subject to the
    # whole-board placement gate — which nobody pre-registered.
    ("let the classifier reach the optimizer", REPO / "frontend/lib/draft-optimizer.ts",
     "// draft-optimizer.ts — the LIVE draft optimizer",
     'import { availabilityTier } from "@/lib/fantasy"\n// draft-optimizer.ts — the LIVE draft optimizer',
     None,
     "test_the_classifier_is_display_only_and_never_reaches_ordering"),

    # ── coverage: each surface, one at a time ────────────────────────────────────────────────
    ("un-flag the rankings board", RANKINGS,
     "<AvailabilityFlag\n                              games={p.g}\n                              locked={p.locked}\n"
     "                              freshness={manifest?.freshness}\n                              underDefinedHeader\n"
     "                            />",
     "{numOrLock(p.g, p.locked)}",
     "<AvailabilityFlag",
     "test_every_games_surface_renders_the_shared_flag[rankings-board.tsx]"),

    ("un-flag the projections table", PROJECTIONS,
     "<AvailabilityFlag\n                        games={p.g}\n                        locked={p.locked}\n"
     "                        freshness={data?.freshness}\n                        underDefinedHeader\n"
     "                      />",
     "{numOrLock(p.g, p.locked)}",
     "<AvailabilityFlag",
     "test_every_games_surface_renders_the_shared_flag[projections-table.tsx]"),

    ("un-flag the player page", PLAYER,
     "<AvailabilityFlag games={proj.g} freshness={projPayload?.freshness} />",
     "{num(proj.g)}",
     "<AvailabilityFlag",
     "test_every_games_surface_renders_the_shared_flag[player-page.tsx]"),

    # ⭐ THE HALF-MIGRATED SURFACE — it carries the flag AND a leftover bare cell, so it satisfies
    # the coverage clause above while still rendering an unflagged games figure.
    ("leave a second, unflagged games cell behind", PROJECTIONS,
     "                      />\n                    </td>",
     "                      />{numOrLock(p.g, p.locked)}\n                    </td>",
     None,
     "test_no_games_surface_still_renders_the_bare_unflagged_figure[projections-table.tsx]"),

    # ── the component's own invariants ────────────────────────────────────────────────────────
    # ⚠️ ~95% of every board is unflagged, so this break empties the games column on three surfaces
    # — and an empty cell always looks deliberate.
    ("render nothing on an unflagged row", SHARED,
     "  if (tier == null) return <>{numOrLock(games, locked)}</>",
     "  if (tier == null) return null",
     "return <>{numOrLock(",
     "test_the_flag_falls_through_to_the_plain_figure_rather_than_rendering_nothing"),

    ("put the definition on a hover-only title attribute", SHARED,
     "    <InfoTip\n      bare={underDefinedHeader}",
     "    <span title=\"limited\">\n      <InfoTip\n      bare={underDefinedHeader}",
     None,
     "test_the_flag_definition_travels_through_infotip_and_not_a_hover_only_tooltip"),

    ("re-type the flag's prose in the component", SHARED,
     "        {AVAILABILITY_FLAG_SUMMARY.replace(\"{games}\", value)}",
     "        Projected {value} games — limited availability priced in.",
     "AVAILABILITY_FLAG_SUMMARY.replace",
     "test_the_flag_prose_is_the_canonical_constants_and_not_retyped"),

    # ── the freshness line ────────────────────────────────────────────────────────────────────
    ("stop reading the injury vintage back", SHARED,
     '  if (!vintage || !("sleeper_status_as_of" in vintage)) return null\n'
     "  const stamp = shortStamp(vintage.sleeper_status_as_of)",
     "  return null\n  const stamp = null as string | null",
     "sleeper_status_as_of",
     "test_the_flag_reads_back_the_injury_vintage_the_exporter_already_stamps"),

    # ⭐ THE NF-FRESH2 COLLAPSE: treat an ABSENT key and a NULL value as the same thing. A payload
    # that predates the stamp — every payload, in an NF-C0 deploy-skew window — then reads "unknown".
    ("collapse an absent vintage key into unknown", SHARED,
     '  if (!vintage || !("sleeper_status_as_of" in vintage)) return null',
     "  if (!vintage) return null",
     '"sleeper_status_as_of" in vintage',
     "test_an_absent_vintage_key_renders_nothing_and_a_null_one_renders_unknown"),

    ("silently drop an unresolvable vintage instead of saying unknown", SHARED,
     "  return `${AVAILABILITY_DATA_AS_OF_PREFIX} ${stamp ?? AVAILABILITY_DATA_AS_OF_UNKNOWN}`",
     "  if (!stamp) return null\n  return `${AVAILABILITY_DATA_AS_OF_PREFIX} ${stamp}`",
     # …and again: the constant is also named in the file's import list.
     "?? AVAILABILITY_DATA_AS_OF_UNKNOWN",
     "test_an_absent_vintage_key_renders_nothing_and_a_null_one_renders_unknown"),

    # ── the instruments (a stripper that eats live code makes every clause above vacuous) ──────
    ("strip block comments before line comments", REPO / SUITE,
     '    src = re.sub(r"(?<!:)//[^\\n]*", "", src)\n'
     '    return re.sub(r"/\\*.*?\\*/", "", src, flags=re.S)',
     '    src = re.sub(r"/\\*.*?\\*/", "", src, flags=re.S)\n'
     '    return re.sub(r"(?<!:)//[^\\n]*", "", src)',
     None,
     "test_the_comment_stripper_does_not_eat_code_after_a_path_glob_in_a_line_comment"),
]

FILES = {c[1] for c in CASES}

#: Where the on-disk copies live while a mutation is applied. Inside the repo (so it is obvious and
#: greppable) and gitignored-by-name via the leading dot; removed on a clean exit.
_BACKUP_DIR = REPO / ".nf_c8_red_proof_backup"


def _slug(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("/", "__")


def _restore_stale_backups() -> None:
    """⚠️ RUN THIS BEFORE ANYTHING ELSE. A backup dir surviving from a previous run means that run
    was killed mid-mutation and the file on disk is the DELIBERATELY BROKEN version. Restoring it
    silently would be wrong in the other direction, so it says so loudly."""
    if not _BACKUP_DIR.exists():
        return
    restored = []
    for saved in sorted(_BACKUP_DIR.iterdir()):
        target = REPO / saved.name.replace("__", "/")
        if target.exists() and target.read_text() != saved.read_text():
            target.write_text(saved.read_text())
            restored.append(str(target.relative_to(REPO)))
    shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
    if restored:
        print("⚠️  a previous run was killed mid-mutation; restored deliberately-broken source in:")
        for f in restored:
            print(f"     {f}")
        print()


def _write_backups(backups: dict) -> None:
    _BACKUP_DIR.mkdir(exist_ok=True)
    for path, src in backups.items():
        (_BACKUP_DIR / _slug(path)).write_text(src)


def run(test_name: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-600:]


def main() -> int:
    _restore_stale_backups()
    backups = {p: p.read_text() for p in FILES}
    _write_backups(backups)
    failures: list[str] = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for label, path, old, new, gone, test in CASES:
            src = backups[path]
            # ⚠️ A MISSING ANCHOR IS A FAILURE, NOT A SKIP (E11.24 #682).
            if old not in src:
                failures.append(f"{label}: PATCH ANCHOR NOT FOUND in {path.name}")
                print(f"⚠️  ANCHOR MISSING  {label}  ({path.name})")
                continue
            # ⚠️ AND IT MUST BE UNIQUE, or `replace(..., 1)` may patch a different occurrence than
            # the one under test and report a sound guard as vacuous.
            if src.count(old) != 1:
                failures.append(f"{label}: ANCHOR IS NOT UNIQUE ({src.count(old)}×) in {path.name}")
                print(f"⚠️  ANCHOR AMBIGUOUS  {label}  ({path.name})")
                continue
            patched = src.replace(old, new, 1)
            assert patched != src, f"{label}: the replacement is a no-op"
            # ⚠️ AND IT MUST MOVE THE ASSERTED PREDICATE (E11.24 #815): a break that lands without
            # changing what the clause reads comes back GREEN for the wrong reason.
            if gone is not None and gone in patched:
                failures.append(f"{label}: the mutation left {gone!r} in place")
                print(f"⚠️  MUTATION DID NOT BITE  {label}")
                continue
            path.write_text(patched)
            code, out = run(test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {label}  ->  {test}")
            if code == 0:
                failures.append(f"{label} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
        print("\nrestored all files")

    if failures:
        print(f"\n❌ {len(failures)} VACUOUS OR MIS-LANDED CLAUSE(S):\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ all {len(CASES)} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
