"""RED proof for NF-C0-Yahoo-ENABLE (Half A) — break the source, watch the guards fire.

A guard that cannot fail is worse than no guard (NF1.7 (a)), and this repo has shipped several:
a clause satisfied by a comment (INC-38), a clause a sibling clause already refused (NF-D17), a
clause whose break no longer bit (E9.64). None of those were found by a green suite — each was
found by deliberately breaking the code and noticing nothing went red.

So each break below removes ONE property and names the clauses that must go red for it. A break
that leaves the suite green is reported as a VACUOUS GUARD, which is a finding.

⚠️ THE HARNESS'S OWN FAILURE MODES, each of which has produced a FALSE result in this repo before:
  · #682 — a mutation that never LANDS reports "the guard is vacuous". Every break asserts the file
    actually changed on disk before pytest is invoked.
  · #815 — a mutation that lands but does not move the ASSERTED predicate. Each break declares the
    token that must DISAPPEAR, and that absence is asserted too.
  · E11.26 — a source-mutating proof that dies mid-run leaves the break on disk. Stale `.nfc0bak`
    files are restored at START-UP, before anything is mutated.
  · NF-W6c — `pytest.raises` raises `Failed`, a `BaseException`. Nothing here wraps pytest in an
    `except Exception`; the subprocess's EXIT CODE is the whole signal.

Run: `uv run python betting_ml/tests/nf_c0_yahoo_halfa_red_proof.py`
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_c0_yahoo_halfa_compliance.py"
BAK = ".nfc0bak"

DYNAMO = REPO / "app/backend/services/dynamo.py"
ROUTER = REPO / "app/backend/routers/fantasy_import.py"
MODELS = REPO / "app/backend/models/fantasy.py"
PRIVACY = REPO / "frontend/app/privacy/page.tsx"
TS_RETENTION = REPO / "frontend/lib/platform-retention.ts"
MY_TEAMS = REPO / "frontend/components/fantasy/my-teams.tsx"
SITE_FOOTER = REPO / "frontend/components/site-footer.tsx"
PROVIDERS = REPO / "frontend/components/providers.tsx"
IMPORT_UI = REPO / "frontend/components/fantasy/league-import.tsx"


@dataclass
class Break:
    """One deliberate defect: what it removes, and what must notice."""

    name: str
    path: Path
    old: str
    new: str
    #: A substring that must be GONE after the mutation. Without this, a break that lands but does
    #: not move the asserted predicate reads as a vacuous guard (#815).
    must_vanish: str
    expects: str


BREAKS = [
    Break(
        name="the disconnect purges nothing (the pre-story behaviour, restored)",
        path=ROUTER,
        old="    dynamo.purge_platform_league_data(user_id, yahoo.PLATFORM)\n    dynamo.delete_platform_token",
        new="    dynamo.delete_platform_token",
        must_vanish="dynamo.purge_platform_league_data(user_id, yahoo.PLATFORM)",
        expects="TestTheDisconnectRouteDeletesBeforeItForgets",
    ),
    Break(
        name="the disconnect drops the token BEFORE purging",
        path=ROUTER,
        old=(
            "    dynamo.purge_platform_league_data(user_id, yahoo.PLATFORM)\n"
            "    dynamo.delete_platform_token(user_id, yahoo.PLATFORM)"
        ),
        new=(
            "    dynamo.delete_platform_token(user_id, yahoo.PLATFORM)\n"
            "    dynamo.purge_platform_league_data(user_id, yahoo.PLATFORM)"
        ),
        must_vanish=(
            "    dynamo.purge_platform_league_data(user_id, yahoo.PLATFORM)\n"
            "    dynamo.delete_platform_token(user_id, yahoo.PLATFORM)"
        ),
        expects="test_a_failed_purge_fails_the_disconnect_rather_than_dropping_the_token",
    ),
    Break(
        name="the purge masks on read instead of removing the stored bytes",
        path=DYNAMO,
        old="    _remove_roster_attributes(user_id, targets)\n    if targets:",
        new="    if targets:",
        must_vanish="    _remove_roster_attributes(user_id, targets)\n    if targets:",
        expects="test_the_purge_round_trips_the_rosters_out_of_the_store",
    ),
    Break(
        name="the purge ignores which platform was disconnected",
        path=DYNAMO,
        old='        if str(record.get("source_platform") or "").lower() != platform.lower():\n            continue\n',
        new="",
        # ⚠️ NEWLINE-ANCHORED, and it took two attempts to get right — worth recording.
        # `iter_platform_league_holders` (§6) carries the SAME predicate at a deeper indent, so a
        # bare `!= platform.lower()` matches BOTH functions; and the 8-space form is a SUBSTRING of
        # the 16-space form, so indenting the token does not disambiguate it either. Only anchoring
        # at the line start does. Both wrong versions were caught by the #815 must-vanish check
        # reporting "landed but did not move the asserted predicate" — a later change made an
        # existing break's token ambiguous, which is precisely the drift that check exists for.
        must_vanish='\n        if str(record.get("source_platform") or "").lower() != platform.lower():',
        expects="test_only_the_disconnected_platform_is_purged",
    ),
    Break(
        name="the purge takes the league's own scoring config with it",
        path=DYNAMO,
        old='PLATFORM_ROSTER_FIELDS = (\n    "imported_roster",',
        new='PLATFORM_ROSTER_FIELDS = (\n    "scoring",\n    "roster",\n    "imported_roster",',
        must_vanish='PLATFORM_ROSTER_FIELDS = (\n    "imported_roster",',
        expects="test_the_league_the_user_configured_survives",
    ),
    Break(
        name="stored rosters are never stamped with an expiry",
        path=DYNAMO,
        old="        record[_ROSTER_EXPIRES_AT] = roster_retention_expiry()",
        new="        pass",
        must_vanish="record[_ROSTER_EXPIRES_AT] = roster_retention_expiry()",
        expects="test_a_fresh_save_is_stamped_with_an_expiry",
    ),
    Break(
        name="an unstamped roster is treated as fresh instead of expired (fail-OPEN)",
        path=DYNAMO,
        old="    if not stamp:\n        return True",
        new="    if not stamp:\n        return False",
        must_vanish="    if not stamp:\n        return True",
        expects="test_an_unstamped_roster_fails_closed",
    ),
    Break(
        name="the retention window is never enforced on a read",
        path=DYNAMO,
        old="            if _roster_retention_expired(item, now_iso):",
        new="            if False and _roster_retention_expired(item, now_iso):",
        must_vanish="            if _roster_retention_expired(item, now_iso):",
        expects="test_a_roster_past_the_window_is_unreadable",
    ),
    Break(
        name="EVERY roster is treated as expired (the over-eager fix)",
        path=DYNAMO,
        old="            if _roster_retention_expired(item, now_iso):",
        new="            if _has_platform_roster(item):",
        must_vanish="            if _roster_retention_expired(item, now_iso):",
        expects="test_a_roster_inside_the_window_still_reads",
    ),
    # ⭐ THE FLAG HAS TWO WRITERS, AND THE FIRST CUT OF THIS PROOF ONLY BROKE ONE OF THEM — which
    # reported the purge clause as VACUOUS when the clause was fine and the BREAK had missed.
    # `_strip_platform_rosters` sets it on the READ-MASK path (expiry), and
    # `_remove_roster_attributes` sets it in the STORE (both the purge and the sweep). Breaking the
    # read-mask writer left the purge test green because the purge gets its flag from the store.
    # One break per writer, each pointed at the clause that actually depends on it.
    Break(
        name="a PURGED deletion is not marked in the store, so it cannot be explained",
        path=DYNAMO,
        old='                    + " SET #fl.#id.#purged = :true"\n',
        new="",
        must_vanish='SET #fl.#id.#purged = :true',
        expects="test_the_purge_marks_the_league_so_the_deletion_can_be_explained",
    ),
    Break(
        name="an EXPIRED deletion is not marked on the read, so it cannot be explained",
        path=DYNAMO,
        old="    if removed:\n        record[_ROSTER_PURGED] = True",
        new="    if removed:\n        pass",
        must_vanish="record[_ROSTER_PURGED] = True",
        expects="test_a_roster_past_the_window_is_unreadable",
    ),
    Break(
        name="the purged flag is inherited by the SAVE model (E9.49's read/write split)",
        path=MODELS,
        old="    roster_retention_purged: bool = False",
        new="",
        must_vanish="roster_retention_purged: bool = False",
        expects="test_the_purged_flag_is_outbound_only_and_a_save_cannot_assert_it",
    ),
    Break(
        name="the client and the store disagree about the retention window",
        path=TS_RETENTION,
        old="export const PLATFORM_ROSTER_RETENTION_DAYS = 30",
        new="export const PLATFORM_ROSTER_RETENTION_DAYS = 90",
        must_vanish="PLATFORM_ROSTER_RETENTION_DAYS = 30",
        expects="test_the_retention_window_is_the_same_number_on_both_sides",
    ),
    Break(
        name="the privacy policy hardcodes the window instead of rendering it",
        path=PRIVACY,
        old="expire {PLATFORM_ROSTER_RETENTION_DAYS} days after we copy them",
        new="expire 30 days after we copy them",
        must_vanish="expire {PLATFORM_ROSTER_RETENTION_DAYS} days after we copy them",
        expects="test_the_privacy_policy_states_the_window_from_the_constant",
    ),
    Break(
        name="the privacy policy stops promising deletion on disconnect",
        path=PRIVACY,
        old="<strong>Disconnecting deletes the rosters immediately.</strong>",
        new="<strong>Disconnecting.</strong>",
        must_vanish="Disconnecting deletes the rosters immediately",
        expects="test_the_privacy_policy_covers_the_league_import",
    ),
    Break(
        name="the credit drifts back out of the page FOOTER",
        path=SITE_FOOTER,
        old='          <PlatformAttributionFooterSlot className="mt-2" />\n',
        new="",
        must_vanish="<PlatformAttributionFooterSlot",
        expects="test_the_credit_is_wired_into_the_page_FOOTER",
    ),
    Break(
        name="the provider stops wrapping the footer, so nothing can reach it",
        path=PROVIDERS,
        old="<PlatformAttributionProvider>{children}</PlatformAttributionProvider>",
        new="{children}",
        must_vanish="<PlatformAttributionProvider>{children}</PlatformAttributionProvider>",
        expects="test_the_credit_is_wired_into_the_page_FOOTER",
    ),
    Break(
        name="the import screen credits only the preview, not the league LIST",
        path=IMPORT_UI,
        old="            <PlatformAttribution sources={platformId} />\n",
        new="",
        must_vanish="<PlatformAttribution sources={platformId} />",
        expects="test_the_import_screen_credits_the_league_LIST_not_only_the_preview",
    ),
    Break(
        name="§6 — the account-wide enumeration stops paginating",
        path=DYNAMO,
        old='        if "LastEvaluatedKey" not in resp:\n            return\n        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]',
        new="        return",
        must_vanish='        if "LastEvaluatedKey" not in resp:\n            return\n        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]',
        expects="test_the_enumeration_paginates",
    ),
    Break(
        name="§6 — the enumeration reports accounts whose rosters are already gone",
        path=DYNAMO,
        old="                if _has_platform_roster(record):\n                    holding += 1",
        new="                holding += 1",
        must_vanish="                if _has_platform_roster(record):\n                    holding += 1",
        expects="test_it_skips_an_account_whose_rosters_are_already_gone",
    ),
    Break(
        name="§6 — the termination purge deletes by DEFAULT instead of dry-running",
        path=REPO / "scripts/purge_platform_data.py",
        old="    if not args.apply:",
        new="    if False:",
        must_vanish="    if not args.apply:",
        expects="test_the_operator_script_defaults_to_a_dry_run_and_uses_the_shared_purge",
    ),
    Break(
        name="a league-aware surface ships without the platform credit",
        path=MY_TEAMS,
        old="          <PlatformAttribution sources={teams.map((t) => t.league)} />",
        new="",
        must_vanish="<PlatformAttribution",
        expects="test_every_league_aware_component_renders_the_shared_attribution",
    ),
]


def _restore_all() -> None:
    """Put back anything a previous, interrupted run left mutated. Runs FIRST (E11.26)."""
    for path in {b.path for b in BREAKS}:
        bak = path.with_suffix(path.suffix + BAK)
        if bak.exists():
            print(f"  ↩︎ restoring stale backup for {path.relative_to(REPO)}")
            path.write_text(bak.read_text())
            bak.unlink()


def _run(expr: str) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-x", "-q", "-k", expr],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    _restore_all()

    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q"], cwd=REPO, capture_output=True, text=True
    )
    if baseline.returncode != 0:
        print("⛔ the suite is RED before any break — fix that first\n")
        print(baseline.stdout[-3000:])
        return 2
    print(f"✅ baseline green\n\nRED-proving {len(BREAKS)} deliberate breaks:\n")

    vacuous = []
    for b in BREAKS:
        original = b.path.read_text()
        if b.old not in original:
            print(f"  ⛔ {b.name}\n       anchor not found in {b.path.relative_to(REPO)} — re-anchor")
            vacuous.append(b.name)
            continue
        if original.count(b.old) != 1:
            # #815's sibling: an anchor appearing twice mutates whichever comes first, which may not
            # be the symbol under test.
            print(f"  ⛔ {b.name}\n       anchor is not unique ({original.count(b.old)} matches)")
            vacuous.append(b.name)
            continue

        b.path.with_suffix(b.path.suffix + BAK).write_text(original)
        try:
            b.path.write_text(original.replace(b.old, b.new, 1))
            landed = b.path.read_text()
            assert landed != original, "the mutation did not change the file"
            assert b.must_vanish not in landed, (
                f"the mutation landed but {b.must_vanish!r} is still present — it did not move the "
                f"asserted predicate"
            )
            rc = _run(b.expects)
            mark = "🔴 RED" if rc != 0 else "🟢 GREEN (VACUOUS)"
            print(f"  {mark}  {b.name}\n           → {b.expects}")
            if rc == 0:
                vacuous.append(b.name)
        finally:
            bak = b.path.with_suffix(b.path.suffix + BAK)
            b.path.write_text(bak.read_text())
            bak.unlink()

    print()
    if vacuous:
        print(f"⛔ {len(vacuous)} guard(s) did not fire:")
        for name in vacuous:
            print(f"   · {name}")
        return 1
    print(f"✅ all {len(BREAKS)} breaks went RED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
