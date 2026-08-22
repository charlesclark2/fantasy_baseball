#!/usr/bin/env python3
"""NF-C9 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/nf_c9_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run whenever `test_nf_c9_designation_disclosure.py` is refactored.

WHY IT EXISTS HERE SPECIFICALLY. NF-C9's suite is almost entirely SOURCE INSPECTION and COPY
SCREENING, which is exactly the shape that reads as coverage while proving nothing — this repo has
been bitten by a source guard a COMMENT could satisfy (INC-38), by a clause whose fixture a
different clause already refused (NF-D17), by a guard whose subject had quietly moved (NF-C4), and
by an ADJUSTMENT/duration screen that any rewrite could route around. Every one was found by
breaking the source, never by a green run.

⭐ AND THE STORY'S HIGHEST-VALUE CLAUSE IS THE ONE MOST LIKELY TO BE VACUOUS.
`test_the_designation_is_not_nested_inside_the_availability_flag` protects the motivating case —
Jordyn Tyson sat at 13.6 projected games, ABOVE the flag threshold, so he carries a designation and
NO flag, and a disclosure rendered from inside `AvailabilityFlag` would never have reached the
player the story was written for. That clause reads two files and a JSX branch; if it does not
actually go red when the designation is nested, the whole story ships broken and green.

The harness contract is carried verbatim from `nf_c8_red_proof.py`, including all three ways a red
proof lies: a mutation that never LANDS (E11.24 #682), one that lands on the WRONG symbol (the
non-unique anchor, E11.24 prediction_log), and one that lands and does not MOVE the asserted
predicate (E11.24 #815). And it restores stale backups AT START-UP, because a `| head` closing
stdout mid-mutation leaves deliberately-broken source on disk (E11.26).

⛔ Deliberately not `git checkout --`: that destroys uncommitted work in the files it patches.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
PROJECTIONS = REPO / "frontend/components/fantasy/projections-table.tsx"
PLAYER = REPO / "frontend/components/fantasy/player-page.tsx"
SOURCE = REPO / "quant_sports_intel_models/football/nfl/fantasy/sleeper_injuries_source.py"
EXPORTER = REPO / "quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py"
SEASON = REPO / "quant_sports_intel_models/football/nfl/fantasy/season_projection.py"
SUITE = "betting_ml/tests/test_nf_c9_designation_disclosure.py"

#: `(label, file, anchor, replacement, gone_after, the ONE test that must go red)`.
#:
#: `gone_after` is the token the named clause actually asserts on; after the mutation it must NOT be
#: in the file, or the break landed without moving the assertion and a GREEN result would mean "the
#: mutation missed" rather than "the guard is vacuous". `None` where the clause asserts on an
#: ABSENCE (the mutation ADDS the forbidden thing), which cannot be expressed that way.
CASES = [
    # ══ ⛔⛔ 1. THE DISCLOSURE MUST NOT BECOME AN ADJUSTMENT ═══════════════════════════════════
    ("claim the projection prices the designation in", COPY,
     "We show it because we hold it, not because we have built it into anything.",
     "It is already priced in.",
     "not because we have built it into anything",
     "test_the_designation_copy_never_claims_the_projection_prices_it_in"
     "[WEEKLY_DESIGNATION_NOT_MODELLED]"),

    # ⭐ The same failure on a DIFFERENT constant — the parametrisation must actually cover each one
    # rather than passing because the first is clean.
    ("claim it in the summary instead", COPY,
     "Listed {status} on the most recent game-status report our injury feed carries.",
     "Listed {status} — factored into our projection from the most recent report our feed carries.",
     "on the most recent game-status report our injury feed carries",
     "test_the_designation_copy_never_claims_the_projection_prices_it_in"
     "[WEEKLY_DESIGNATION_SUMMARY]"),

    ("drop the disclaimer's negative statement", COPY,
     "Our projected-games figure does not take this into account.",
     "Our projected-games figure is one of several inputs on this page.",
     "does not take this into account",
     "test_the_definition_says_out_loud_that_the_projection_does_not_price_it_in"),

    ("stop naming the channel the discount DOES move on", COPY,
     "That number moves only on a formal roster move — injured reserve, the "
     "physically-unable-to-perform list, the non-football-injury list, or a suspension — so a "
     "weekly designation like this one applies no discount to it at all.",
     "A weekly designation like this one applies no discount to it at all.",
     "roster move",
     "test_the_disclaimer_names_what_the_projection_does_move_on"),

    # ══ ⛔⛔ 2. IT MUST NOT BECOME A MEDICAL FORECAST, AND CARRIES NO DURATION ══════════════════
    ("forecast an injury in the disclaimer", COPY,
     "We show it because we hold it, not because we have built it into anything.",
     "We show it because a player listed this way will miss time.",
     None,
     "test_the_designation_copy_never_forecasts_an_injury[WEEKLY_DESIGNATION_NOT_MODELLED]"),

    ("invent a duration in the summary", COPY,
     "Listed {status} on the most recent game-status report our injury feed carries.",
     "Listed {status} — typically a player in this position is out for several games.",
     None,
     "test_the_designation_copy_never_implies_a_duration[WEEKLY_DESIGNATION_SUMMARY]"),

    ("drop the not-a-diagnosis refusal", COPY,
     "It is not a diagnosis, it is not our own read on how a player is doing",
     "It is not our own read on how a player is doing",
     # ⚠️ SCOPED: NF-C8's own definition also says "not a diagnosis" a few hundred lines up, so the
     # bare token is present whatever this constant says.
     "It is not a diagnosis, it is not our own read",
     "test_the_definition_says_out_loud_that_it_is_not_a_diagnosis"),

    ("state the designation without attributing it", COPY,
     "Listed {status} on the most recent game-status report our injury feed carries.",
     "Listed {status}.",
     "game-status report our injury feed carries",
     "test_the_copy_attributes_the_designation_to_its_source_not_to_us"),

    ("type the designation into the copy instead of reading it", COPY,
     'export const WEEKLY_DESIGNATION_SUMMARY =\n'
     '  "Listed {status} on the most recent game-status report our injury feed carries."',
     'export const WEEKLY_DESIGNATION_SUMMARY =\n'
     '  "Listed Questionable on the most recent game-status report our injury feed carries."',
     # ⚠️ SCOPED: `{status}` is also named in the constant's own doc comment.
     '"Listed {status} on the most recent',
     "test_no_designation_is_typed_into_the_copy"),

    # ══ 3. THE MODEL BOUNDARY ═════════════════════════════════════════════════════════════════
    # ⭐ THE DISCLAIMER GOES FALSE WITHOUT A SINGLE STRING CHANGING. An IR row would render "our
    # projected-games figure does not take this into account" over a status capped at 4.0 games.
    ("let a MODELLED roster status reach the disclosure channel", SOURCE,
     "    if map_injury_status(raw) is not None:      # the projection already acts on this one\n"
     "        return False, None\n",
     "",
     "if map_injury_status(raw) is not None",
     "test_a_modelled_roster_status_never_reaches_the_disclosure_channel"),

    # ⭐ THE VACUOUS IMPLEMENTATION — disclose nothing, ever. It satisfies every "never claims X"
    # clause above, which is exactly why the positive clause has to exist.
    ("disclose nothing at all", SOURCE,
     "    return True, WEEKLY_DESIGNATIONS.get(raw.upper())",
     "    return False, None",
     "return True, WEEKLY_DESIGNATIONS.get",
     "test_a_weekly_designation_is_disclosed_with_its_label"),

    # ⭐ NF1.7 (a): an unreadable value collapsing into "no designation" reads as a clean bill of
    # health. `NA`/`DNR` are live values, so this is production behaviour, not a hypothetical.
    ("silently drop a value we cannot interpret", SOURCE,
     "    return True, WEEKLY_DESIGNATIONS.get(raw.upper())",
     "    hit = WEEKLY_DESIGNATIONS.get(raw.upper())\n"
     "    return (True, hit) if hit is not None else (False, None)",
     None,
     "test_an_uninterpretable_value_is_disclosed_as_an_explicit_unknown"),

    ("fabricate a status for a player the feed says nothing about", SOURCE,
     "    if injury_status is None:\n        return False, None\n    raw = str(injury_status).strip()",
     "    if injury_status is None:\n        return True, None\n    raw = str(injury_status).strip()",
     None,
     "test_no_designation_at_all_says_nothing"),

    ("attach a games penalty to the disclosure map", SOURCE,
     '    "QUESTIONABLE": "Questionable",\n}',
     '    "QUESTIONABLE": 0.75,\n}',
     '"QUESTIONABLE": "Questionable"',
     "test_the_disclosure_map_carries_no_games_number_or_weight"),

    # ⭐ THE COPY GOES FALSE EVERYWHERE IT RENDERS, WITH NO STRING TOUCHED.
    ("wire the disclosure channel into the projection", SEASON,
     "def injury_availability_games(",
     "def _nf_c9_would_be_a_lie(x):\n"
     "    return disclosable_designation(x)\n\n\ndef injury_availability_games(",
     None,
     "test_the_projection_path_never_reads_the_disclosure_channel"),

    # ══ 4. THE EXPORTER'S THREE STATES ════════════════════════════════════════════════════════
    # ⭐ "unknown" under every player on every board, during any routine ingest gap.
    ("spray a null designation across every row", EXPORTER,
     "        if pid in lookup:\n            rec[\"gameStatus\"] = lookup[pid]\n            n += 1",
     "        rec[\"gameStatus\"] = lookup.get(pid)\n        n += 1",
     "if pid in lookup:",
     "test_the_exporter_omits_the_key_where_there_is_nothing_to_disclose"),

    # ⚠️ THE FIRST CUT OF THIS MUTATION WAS A NO-OP — it defaulted a missing feed to `{}`, which
    # attaches nothing, so the clause stayed green for the RIGHT reason and reported as vacuous. The
    # realistic defect is the "helpful" one: treat an unreadable feed as unknown-for-everyone, which
    # writes a key on every row of every board during any routine ingest gap.
    ("render unknown on every row when the feed is unreadable", EXPORTER,
     "    if not designations:\n        return 0",
     "    if designations is None:\n"
     "        designations = {str(r.get(\"id\")): None for r in recs}",
     "if not designations:",
     "test_an_unreadable_feed_leaves_every_record_untouched"),

    ("stop reporting an unrecognised token to the operator", EXPORTER,
     '        log.warning("[ALERT] NF-C9: %d player(s) carry a game-status value this build does not "',
     '        log.debug("NF-C9: %d player(s) carry an unrecognised game-status value "',
     "[ALERT] NF-C9: %d player(s) carry a game-status value",
     "test_an_unrecognised_token_is_reported_to_the_operator"),

    # ⭐⭐ THE DEFECT THAT ACTUALLY SHIPPED (2026-08-22, live for a few hours). 275 of 2,501 feed
    # rows carry a LEADING SPACE in `player_id`; an exact match drops them SILENTLY, and a silent
    # drop here is indistinguishable from "the feed says nothing about him". Josh Jacobs and DK
    # Metcalf were both listed Questionable and both undisclosed on a published board.
    ("drop the id normalisation on the lookup side", EXPORTER,
     "    lookup = {_norm_player_id(k): v for k, v in designations.items()}",
     "    lookup = dict(designations)",
     "_norm_player_id(k)",
     "test_a_whitespace_padded_feed_id_still_reaches_its_board_row"),

    ("drop the id normalisation on the board-row side", EXPORTER,
     '        pid = _norm_player_id(rec.get("id"))',
     '        pid = str(rec.get("id"))',
     '_norm_player_id(rec.get("id"))',
     "test_both_sides_of_the_id_join_go_through_the_one_normaliser"),

    ("open-code the strip instead of using the shared normaliser", EXPORTER,
     "        out[_norm_player_id(pid)] = label",
     "        out[str(pid).strip()] = label",
     "_norm_player_id(pid)",
     "test_both_sides_of_the_id_join_go_through_the_one_normaliser"),

    # ══ 5. THE SURFACES ═══════════════════════════════════════════════════════════════════════
    ("drop the designation from the rankings board", RANKINGS,
     "                            <WeeklyDesignation\n"
     "                              status={p.gameStatus}\n"
     "                              freshness={manifest?.freshness}\n"
     "                            />\n",
     "",
     "<WeeklyDesignation",
     "test_every_games_surface_renders_the_designation[rankings-board.tsx]"),

    ("drop the designation from the projections table", PROJECTIONS,
     "                      <WeeklyDesignation status={p.gameStatus} freshness={data?.freshness} />\n",
     "",
     "<WeeklyDesignation",
     "test_every_games_surface_renders_the_designation[projections-table.tsx]"),

    ("drop the designation from the player page", PLAYER,
     "                      <WeeklyDesignation\n"
     "                        status={proj.gameStatus}\n"
     "                        freshness={projPayload?.freshness}\n"
     "                      />\n",
     "",
     "<WeeklyDesignation",
     "test_every_games_surface_renders_the_designation[player-page.tsx]"),

    ("hardcode a designation instead of reading the payload", PROJECTIONS,
     "<WeeklyDesignation status={p.gameStatus} freshness={data?.freshness} />",
     '<WeeklyDesignation status={"Questionable"} freshness={data?.freshness} />',
     "status={p.gameStatus}",
     "test_every_surface_passes_the_served_status_rather_than_a_literal"
     "[projections-table.tsx]"),

    # ⭐⭐ THE CLAUSE THAT PROTECTS THE MOTIVATING CASE. Nested inside the flag, the designation
    # renders only where `g` is already materially low — i.e. never for the 13.6-game row that
    # produced the finding.
    ("nest the designation inside the availability flag", SHARED,
     "        {GLOSSARY.projectedGames}\n      </p>\n      {asOf && ",
     "        {GLOSSARY.projectedGames}\n"
     "        <WeeklyDesignation status={undefined} />\n      </p>\n      {asOf && ",
     None,
     "test_the_designation_is_not_nested_inside_the_availability_flag"),

    ("bury the player page's designation inside the availability branch", PLAYER,
     "                      <InfoTip label={`${num(proj.g)} ${PROJECTED_GAMES_LABEL.toLowerCase()}`}>\n"
     "                        {GLOSSARY.projectedGames}\n"
     "                      </InfoTip>\n                    )}",
     "                      <InfoTip label={`${num(proj.g)} ${PROJECTED_GAMES_LABEL.toLowerCase()}`}>\n"
     "                        {GLOSSARY.projectedGames}\n"
     "                        <WeeklyDesignation status={proj.gameStatus} />\n"
     "                      </InfoTip>\n                    )}",
     None,
     "test_the_designation_is_not_nested_inside_the_availability_flag"),

    # ══ 6. THE COMPONENT ══════════════════════════════════════════════════════════════════════
    # ⭐ THE NF-FRESH2 COLLAPSE: absent and null treated as one thing → "unknown" on ~93% of rows.
    ("collapse an absent status into unknown", SHARED,
     "  if (status === undefined) return null",
     "  if (status == null) return null",
     "status === undefined",
     "test_an_absent_status_renders_nothing_and_a_null_one_renders_unknown"),

    ("stop rendering unknown for an unreadable value", SHARED,
     "  const label = known ?? WEEKLY_DESIGNATION_UNKNOWN\n"
     "  const glyph = known == null ? WEEKLY_DESIGNATION_UNKNOWN : (WEEKLY_DESIGNATION_CODE[known] ?? known)",
     "  const label = known ?? \"\"\n"
     "  const glyph = known == null ? \"\" : (WEEKLY_DESIGNATION_CODE[known] ?? known)",
     # ⚠️ `WEEKLY_DESIGNATION_UNKNOWN` is a PREFIX of `WEEKLY_DESIGNATION_UNKNOWN_SUMMARY`, which
     # this component also renders — so the gone-token has to be a use of the LABEL specifically.
     "?? WEEKLY_DESIGNATION_UNKNOWN",
     "test_an_absent_status_renders_nothing_and_a_null_one_renders_unknown"),

    ("invent a clean status for an undesignated player", SHARED,
     "      label={<span className={DESIGNATION_CHIP}>{glyph}</span>}",
     "      label={<span className={DESIGNATION_CHIP}>{glyph || \"Healthy\"}</span>}",
     None,
     "test_the_component_never_invents_a_clean_status"),

    ("put the disclaimer on a hover-only title attribute", SHARED,
     "  return (\n    <InfoTip\n      // `bare` because the bordered chip IS the affordance",
     "  return (\n    <span title=\"see the designation\">\n    <InfoTip\n      // `bare` because the bordered chip IS the affordance",
     None,
     "test_the_definition_travels_through_infotip_and_not_a_hover_only_tooltip"),

    ("re-type the disclaimer in the component", SHARED,
     '      <p className="mt-2">{WEEKLY_DESIGNATION_NOT_MODELLED}</p>',
     '      <p className="mt-2">Our projected-games figure does not take this into account.</p>',
     # ⚠️ SCOPED: the constant NAME is also in the file's import list.
     "{WEEKLY_DESIGNATION_NOT_MODELLED}",
     "test_the_component_prose_is_the_canonical_constants_and_not_retyped"),

    # ⭐ "unknown" with no disclaimer beneath it reads MORE like a model input than a designation
    # does — so the branch has to be checked separately from the recognised one.
    ("render the disclaimer only on the recognised branch", SHARED,
     "          ? WEEKLY_DESIGNATION_UNKNOWN_SUMMARY\n"
     "          : WEEKLY_DESIGNATION_SUMMARY.replace(\"{status}\", known)}\n"
     "      </p>\n"
     "      {/* ⭐⭐ THE LINE THE STORY IS FOR. It renders on BOTH branches — an unrecognised value is\n"
     "          exactly as un-modelled as a recognised one, and a reader who meets \"unknown\" with no\n"
     "          disclaimer would have no way to tell. */}\n"
     '      <p className="mt-2">{WEEKLY_DESIGNATION_NOT_MODELLED}</p>',
     "          ? WEEKLY_DESIGNATION_UNKNOWN_SUMMARY\n"
     "          : WEEKLY_DESIGNATION_SUMMARY.replace(\"{status}\", known)}\n"
     "      </p>\n"
     '      {known != null && <p className="mt-2">{WEEKLY_DESIGNATION_NOT_MODELLED}</p>}',
     None,
     "test_the_disclaimer_renders_on_the_unknown_branch_too"),

    # ⭐ NF-C0 SKEW, the other way round: a newer exporter's designation on an older client is not
    # an unknown — the server told us the word.
    ("report our own staleness as the feed's", SHARED,
     "(WEEKLY_DESIGNATION_CODE[known] ?? known)",
     "(WEEKLY_DESIGNATION_CODE[known] ?? WEEKLY_DESIGNATION_UNKNOWN)",
     "WEEKLY_DESIGNATION_CODE[known] ?? known",
     "test_an_unknown_designation_label_renders_verbatim_rather_than_as_unknown"),
]

FILES = {c[1] for c in CASES}

#: Where the on-disk copies live while a mutation is applied. Inside the repo (obvious + greppable)
#: and gitignored-by-name via the leading dot; removed on a clean exit.
_BACKUP_DIR = REPO / ".nf_c9_red_proof_backup"


def _slug(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("/", "__")


def _restore_stale_backups() -> None:
    """⚠️ RUN THIS BEFORE ANYTHING ELSE (E11.26). A backup dir surviving from a previous run means
    that run was killed mid-mutation and the file on disk is the DELIBERATELY BROKEN version."""
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
            # the one under test and report a sound guard as vacuous (the dangerous direction).
            if src.count(old) != 1:
                failures.append(f"{label}: ANCHOR IS NOT UNIQUE ({src.count(old)}×) in {path.name}")
                print(f"⚠️  ANCHOR AMBIGUOUS  {label}  ({path.name})")
                continue
            patched = src.replace(old, new, 1)
            assert patched != src, f"{label}: the replacement is a no-op"
            # ⚠️ AND IT MUST MOVE THE ASSERTED PREDICATE (E11.24 #815).
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
