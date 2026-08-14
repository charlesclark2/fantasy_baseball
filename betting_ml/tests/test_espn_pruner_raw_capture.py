"""ESPN-PRUNER — the guards that must run in the FAST GATE, not only in the E2E suite.

``pruneEspnPayload`` is what keeps a real ESPN league under the server's paste cap: un-pruned, a
real drafted response is ~3.3 MB for ten teams, a 12-team league lands at ~99% of the cap and a
14-team league is refused outright. Its correctness is asserted against real un-pruned bytes in
``frontend/e2e/specs/fantasy-import-espn-pruner.spec.ts``.

Two of those guards do not belong exclusively in a Playwright suite:

1. **The cross-language cap pin.** The browser suite asserts a payload fits under a cap it has to
   re-spell as a TypeScript literal, because the real one is a Python constant. Nothing otherwise
   stops the two drifting, and the drift is silent in the safe-looking direction — the browser goes
   on passing against a cap the server stopped enforcing.

2. **"Is the capture actually un-pruned?"** This is the whole premise of the story. All three
   pre-existing ESPN captures were pruned before they were committed, so every assertion about the
   pruner passed on a payload with nothing to prune. A raw capture that gets re-saved through a
   JSON viewer, or regenerated through the app, silently becomes another one of those — and the
   E2E suite would go green. Checking it in the fast gate means the regression is caught on every
   PR rather than on whatever schedule the browser suite runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.services.platform_import import espn

REPO = Path(__file__).resolve().parents[2]
RAW_CAPTURES_TS = REPO / "frontend" / "e2e" / "support" / "espn-raw-captures.ts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# ⛔ A THIRD SPELLING, deliberately. The pruner's own list lives in `fantasy-import.ts`, the E2E
# contract re-spells it in `espn-raw-captures.ts`, and this states it again. A test that reads a
# value back under the key the code wrote can never catch a wrong key (NF-C0e) — so if these three
# ever disagree, the disagreement is the finding.
REMOVED_FIELDS = (
    "stats",
    "draftRanksByRankType",
    "ownership",
    "outlooks",
    "ratings",
    "notificationSettings",
)

# The subset that carries the bulk, and therefore the evidence that a capture is genuinely raw.
BULK_DRIVER_FIELDS = ("stats", "draftRanksByRankType", "ownership")


def _declared_raw_captures() -> list[dict]:
    """The capture registry as the TypeScript declares it: (file, teams) per entry.

    Parsed from the real declarations rather than from a duplicated Python list, so the two cannot
    drift into describing different files.
    """
    src = RAW_CAPTURES_TS.read_text()
    block = re.search(
        r"^export const ESPN_RAW_CAPTURES.*?^\]", src, re.MULTILINE | re.DOTALL
    )
    assert block, "the raw-capture registry declaration moved — update this parser"
    entries = []
    for chunk in re.finditer(
        r'file:\s*"([^"]+)".*?teams:\s*(\d+).*?source:\s*(SIZE_EXTENDED|"[a-z-]+")',
        block.group(0),
        re.DOTALL,
    ):
        source = chunk.group(3)
        entries.append(
            {
                "file": chunk.group(1),
                "teams": int(chunk.group(2)),
                # `SIZE_EXTENDED` is the exported constant whose value is "size-extended".
                "source": "size-extended" if source == "SIZE_EXTENDED" else source.strip('"'),
            }
        )
    assert entries, "parsed no registry entries — the declaration shape moved"
    return entries


class TestTheCapIsPinnedAcrossLanguages:
    def test_the_typescript_suite_states_the_servers_real_cap(self):
        """The E2E suite asserts a pruned payload fits under `MAX_PASTE_BYTES`. That number is a
        Python constant it cannot import, so it re-spells it — and a re-spelling with nothing
        holding it in place is a stale assertion waiting to happen.

        ⚠️ Matched on an ANCHORED DECLARATION (`^export const … = <digits>`), never a bare mention.
        `espn-raw-captures.ts` names `MAX_PASTE_BYTES` in prose as well, and a guard a COMMENT can
        satisfy is not a guard (INC-38).
        """
        src = RAW_CAPTURES_TS.read_text()
        declared = re.search(
            r"^export const MAX_PASTE_BYTES = ([0-9_]+)$", src, re.MULTILINE
        )
        assert declared, (
            "no `export const MAX_PASTE_BYTES = <number>` declaration in "
            f"{RAW_CAPTURES_TS.name} — the E2E cap assertion has no pinned value"
        )
        assert int(declared.group(1).replace("_", "")) == espn.MAX_PASTE_BYTES, (
            f"the browser suite tests against {declared.group(1)} bytes while the server enforces "
            f"{espn.MAX_PASTE_BYTES}. Update both in the same change."
        )

    def test_the_typescript_removal_list_matches_this_one(self):
        """Three independent spellings of the removed set are only useful while a disagreement is
        visible. This is where it becomes visible."""
        src = RAW_CAPTURES_TS.read_text()
        block = re.search(
            r"^export const ESPN_REMOVED_FIELDS = \[(.*?)\] as const",
            src,
            re.MULTILINE | re.DOTALL,
        )
        assert block, "the removal-list declaration moved — update this parser"
        assert tuple(re.findall(r'"([^"]+)"', block.group(1))) == REMOVED_FIELDS


class TestTheRawCaptureRegistry:
    def test_it_declares_the_two_sizes_the_pruner_exists_for(self):
        """A 12-team league imports today only by a hair and a 14-team league only because the
        pruner runs. Those are the sizes worth testing, so the registry has to name them."""
        assert {c["teams"] for c in _declared_raw_captures()} >= {12, 14}

    def test_at_least_one_size_demands_a_real_capture(self):
        """⭐ THE SHAPE CLAIM CANNOT BE SIZE-EXTENDED INTO EXISTENCE.

        A `size-extended` entry replicates real teams out of a real capture, which is honest for a
        SIZE claim and worth nothing for a SHAPE one — two copies of one payload are one payload.
        So the registry must always keep at least one entry that demands a genuine capture; a
        future edit that flipped every entry to `size-extended` would leave the suite green while
        no real ESPN bytes were involved anywhere.
        """
        sources = [c["source"] for c in _declared_raw_captures()]
        assert "captured" in sources, (
            "every declared league size is now size-extended, so nothing in the pruner suite reads "
            "real ESPN bytes — the denylist would be unproven while the suite reported green"
        )

    @pytest.mark.parametrize(
        "capture", _declared_raw_captures(), ids=lambda c: f"{c['teams']}-team"
    )
    def test_a_committed_raw_capture_is_genuinely_un_pruned(self, capture: dict):
        """⭐ THE NON-VACUITY GUARD, and the reason this file exists in the fast gate.

        A "raw" capture that has in fact been pruned is byte-plausible, passes every other
        assertion in the repo, and turns the entire E2E pruner suite back into what it replaced.
        That is not hypothetical: it is exactly the state all three pre-existing ESPN captures are
        in, and it is why the pruner went unexercised for as long as it did.

        SKIPS while the capture is an outstanding operator dependency — the file cannot be produced
        from anything in this repo and must not be fabricated (see `espn-raw-captures.ts`). It goes
        live the moment the capture lands, with no code change.
        """
        path = FIXTURES / capture["file"]
        if not path.exists():
            extra = (
                " (this size is SIZE-EXTENDED from the captured one when absent, which covers its "
                "size and adds no shape evidence — a real capture here would still be better, and "
                "a PUBLIC ESPN league needs no credential; see espn-raw-captures.ts)"
                if capture["source"] == "size-extended"
                else " Until it lands, pruneEspnPayload's denylist is unproven against real bytes."
            )
            pytest.skip(
                f"⏭️ OPERATOR CAPTURE OUTSTANDING: {capture['file']} — a real un-pruned "
                f"{capture['teams']}-team ESPN response.{extra}"
            )

        text = path.read_text()
        counts = {f: text.count(f'"{f}"') for f in REMOVED_FIELDS}
        for field in BULK_DRIVER_FIELDS:
            assert counts[field] > 0, (
                f"{capture['file']} contains no {field!r} key, so it is NOT an un-pruned capture — "
                "it is a pruned artifact. Every pruner assertion would pass on it while proving "
                f"nothing. Re-capture it verbatim from the ESPN read URL. Observed: {counts}"
            )

        # It also has to be the thing it claims to be: a real league of the declared size, with
        # rosters (the bulk lives in the roster entries, so an undrafted league carries almost none
        # of it and would understate the payload the pruner has to survive).
        doc = json.loads(text)
        teams = doc.get("teams") or []
        assert len(teams) == capture["teams"], (
            f"{capture['file']} carries {len(teams)} teams, not the declared {capture['teams']}"
        )
        assert any((t.get("roster") or {}).get("entries") for t in teams), (
            f"{capture['file']} has no roster entries — capture a DRAFTED season, or the payload "
            "is missing the bulk this whole guard is about"
        )
