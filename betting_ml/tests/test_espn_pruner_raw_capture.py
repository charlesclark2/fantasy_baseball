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
        r'file:\s*"([^"]+)".*?teams:\s*(\d+|null).*?source:\s*(SIZE_EXTENDED|"[a-z-]+")',
        block.group(0),
        re.DOTALL,
    ):
        source = chunk.group(3)
        entries.append(
            {
                "file": chunk.group(1),
                "teams": None if chunk.group(2) == "null" else int(chunk.group(2)),
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

    def test_the_shape_carrying_entry_does_not_demand_a_league_size(self):
        """⭐ The denylist claim is about ESPN's FIELD NAMES, not about league size, so the entry
        that requires a real capture must accept ANY drafted league (`teams: null`).

        Pinning it to a size would reject a perfectly good capture for a reason unrelated to what it
        proves — and that is not hypothetical: the first capture attempt was a 12-team league that
        had not drafted (useless here), while a 10-team league that HAD drafted was available and
        would have carried the claim completely.
        """
        captured = [c for c in _declared_raw_captures() if c["source"] == "captured"]
        assert captured, "no entry demands a real capture"
        assert all(c["teams"] is None for c in captured), (
            "the shape-carrying capture is pinned to a league size; it must accept any DRAFTED "
            "league, because the denylist claim does not depend on size"
        )

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
        "capture", _declared_raw_captures(), ids=lambda c: c["file"]
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
        doc = json.loads(text)
        teams = doc.get("teams") or []
        counts = {f: text.count(f'"{f}"') for f in REMOVED_FIELDS}

        # ⚠️ ORDER IS LOAD-BEARING — DIAGNOSE THE UNDRAFTED CASE FIRST.
        #
        # An UNDRAFTED league and a PRUNED artifact both present as "no bulk fields", and they need
        # opposite fixes: re-capture a different SEASON vs re-capture without the transform. The
        # first real capture attempt hit exactly this — a 2026 pre-draft league, 48 KB, `stats`
        # occurring zero times, 12 teams with 0 roster entries each — and an earlier version of this
        # guard reported it as "it is a pruned artifact", which is false and sends the reader at the
        # wrong fix. An alert's suggested cause is diagnostic anchoring (INC-40), so it has to be
        # right or absent, never merely plausible.
        entry_counts = [len((t.get("roster") or {}).get("entries") or []) for t in teams]
        assert any(entry_counts), (
            f"{capture['file']} has {len(teams)} teams and NO roster entries on any of them "
            f"(drafted={((doc.get('draftDetail') or {}).get('drafted'))!r}, "
            f"{path.stat().st_size} bytes) — this is a faithful capture of a league that has NOT "
            "DRAFTED. The removable bulk lives in the roster entries, so a pre-draft league carries "
            "none of it. Re-capture a season this league has already drafted; nothing about the "
            "capture procedure was wrong."
        )

        for field in BULK_DRIVER_FIELDS:
            assert counts[field] > 0, (
                f"{capture['file']} has populated rosters but no {field!r} key, so the bulk was "
                "stripped in transit — it is a pruned artifact, and every pruner assertion would "
                f"pass on it while proving nothing. Re-capture verbatim from the ESPN read URL "
                f"without routing it through the app or a JSON viewer. Observed: {counts}"
            )

        # A sized entry must be the size it claims. The shape-carrying entry declares `teams: null`
        # — any drafted league proves the denylist, so demanding a size there would reject a good
        # capture for a reason unrelated to what it proves.
        if capture["teams"] is not None:
            assert len(teams) == capture["teams"], (
                f"{capture['file']} carries {len(teams)} teams, not the declared {capture['teams']}"
            )


class TestPruningDoesNotChangeWhatGetsImported:
    """⭐ THE INVARIANT THAT ACTUALLY MATTERS, now provable against REAL bytes.

    `test_nf_c0_platform_import.py::test_pruning_does_not_change_what_gets_imported` proves this by
    re-pruning an ALREADY-PRUNED payload — i.e. it proves IDEMPOTENCE, and says so, because "the
    3.3 MB original is far too large to commit". That premise no longer holds: the real un-pruned
    response is 834 KB and is committed, so the real claim is now directly testable.

    Idempotence and equivalence are different claims. A pruner that deleted the wrong subtree would
    be perfectly idempotent (pruning twice changes nothing after the first pass) while destroying
    the league — which is the exact NF-C0e wrong-key shape this whole story exists to close.
    """

    def test_the_raw_and_pruned_payloads_import_as_the_same_league(self):
        path = FIXTURES / "espn_league_raw_unpruned.json"
        if not path.exists():
            pytest.skip("⏭️ OPERATOR CAPTURE OUTSTANDING: espn_league_raw_unpruned.json")

        from app.backend.services.platform_import import espn

        raw = path.read_text()
        doc = json.loads(raw)

        # ⛔ A SECOND SPELLING of the pruner, not an import of it — a test that applies the code's
        # own transform and compares to itself cannot catch a wrong key (NF-C0e).
        for m in doc.get("members") or []:
            m.pop("notificationSettings", None)
        for t in doc.get("teams") or []:
            for e in (t.get("roster") or {}).get("entries") or []:
                pool = e.get("playerPoolEntry") or {}
                pool.pop("ratings", None)
                for f in ("stats", "draftRanksByRankType", "ownership", "outlooks"):
                    (pool.get("player") or {}).pop(f, None)
        pruned = json.dumps(doc)

        # Non-vacuity: if pruning changed nothing, the comparison below proves nothing.
        assert len(pruned) < len(raw) * 0.5, (
            "pruning barely shrank the payload, so this equivalence check is near-vacuous"
        )

        assert (
            espn.parse_settings_payload(pruned).to_dict()
            == espn.parse_settings_payload(raw).to_dict()
        ), "the pruned payload imports as a DIFFERENT league than the raw one"
