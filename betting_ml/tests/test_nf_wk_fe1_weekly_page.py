"""NF-WK-FE1 — the guard suite for the WEEKLY frontend surface.

This is the story's acceptance criteria as executable clauses, and it covers the half the E2E suite
structurally cannot: the E2E asserts what the browser RENDERED from a fixture, so it can prove the
page behaves correctly on the payload it was handed. It cannot prove that the page's registries
still AGREE WITH THE CONTRACT — a component the server starts serving, an absence reason the server
adds, a paid field that changes hands — because a fixture frozen at this commit would keep the E2E
green while the real wire moved underneath it.

⭐ EVERY CLAUSE HERE IS A CROSS-CHECK BETWEEN TWO OWNERS, never a restatement of one of them. A test
that reads a value back under the key the code wrote can never catch a wrong key (NF-C0e), so each
clause below reads the CONTRACT on one side and the FRONTEND on the other and asserts they agree.

⛔ WHAT IS DELIBERATELY NOT HERE. The backend's own properties — the free/paid reduction, the
byte-identity of the free routes, the CDN allowlist membership, the gateway authorizer registration
— are pinned by `test_nf_c6_ph2_weekly_contract.py` and are NOT re-asserted here. Duplicating them
would create a second place to update and a second place to be wrong, and a guard that merely echoes
another guard adds no information.

RED-PROVEN: `uv run python betting_ml/tests/nf_wk_fe1_red_proof.py`.

Pure/offline (fast gate): reads source files and the committed contract; no DuckDB/S3/network, and
⛔ no `pipeline` import (E11.23 — `pipeline/__init__.py` reads the dbt manifest, which is absent in
the fast gate, so importing it would crash this file at COLLECTION rather than skip cleanly).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.models import nfl_weekly as C

_REPO = Path(__file__).resolve().parents[2]
_FE = _REPO / "frontend"
_COPY_TS = _FE / "lib/fantasy-claim-copy.ts"
_READ_TS = _FE / "lib/nfl-weekly.ts"
_PAGE_TSX = _FE / "components/fantasy/weekly-page.tsx"
_ROUTE_TSX = _FE / "app/fantasy/weekly/page.tsx"
_NAV_TS = _FE / "lib/nav-model.ts"
_FIXTURES = _FE / "e2e/fixtures/api"
_MANIFEST_FIXTURE = _FIXTURES / "fantasy-nfl-weekly-manifest.synthetic.json"
_FREE_FIXTURE = _FIXTURES / "fantasy-nfl-weekly-players-free.synthetic.json"
_ENTITLED_FIXTURE = _FIXTURES / "fantasy-nfl-weekly-players-entitled.synthetic.json"

#: Every source file this story owns on the frontend. The weekly TREE, so a clause about "the page"
#: cannot be satisfied by one file while another quietly does the forbidden thing.
_WEEKLY_TREE = (_READ_TS, _PAGE_TSX, _ROUTE_TSX)


def _strip_ts_comments(src: str) -> str:
    """Source with comments removed.

    ⚠️ LOAD-BEARING, NOT TIDINESS. Several clauses below scan for a token, and this file's own
    explanatory comments NAME the tokens they forbid — so an un-stripped scan would be satisfied by
    the prose explaining the rule, and would pass with the code deleted (INC-38 shipped exactly
    that, twice).
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _ts_string_literals(src: str) -> list[str]:
    return re.findall(r'"((?:[^"\\]|\\.)*)"', _strip_ts_comments(src))


def _ts_record_keys(src: str, name: str) -> list[str]:
    """The keys of an exported `Record<string, string>` object literal, in declaration order."""
    body = src.split(f"export const {name}", 1)[1].split("{", 1)[1]
    depth, end = 1, 0
    for i, ch in enumerate(body):
        depth += (ch == "{") - (ch == "}")
        if depth == 0:
            end = i
            break
    return re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", body[:end], flags=re.M)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The suite's own non-vacuity floor. Every clause below reads one of these files; if a rename made
# one unreadable, each clause would fail for the wrong reason or (worse) scan an empty string.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_every_file_this_suite_reads_exists_and_is_non_empty():
    for path in (_COPY_TS, _READ_TS, _PAGE_TSX, _ROUTE_TSX, _NAV_TS,
                 _MANIFEST_FIXTURE, _FREE_FIXTURE, _ENTITLED_FIXTURE):
        assert path.exists(), f"{path.relative_to(_REPO)} is missing — clauses reading it would be vacuous"
        assert len(path.read_text()) > 200, f"{path.relative_to(_REPO)} is suspiciously small"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 1(f) — the claims discipline, enforced by the CONTRACT'S OWN instrument
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_weekly_copy_makes_no_matchup_claim():
    """⭐ POINTED AT THE COPY BY THE CONTRACT'S OWN EXPORTED GUARD, deliberately.

    `nfl_weekly.assert_no_matchup_claim` is exported with a docstring that says it is "exported so
    the weekly FRONTEND story can point this at its copy constants rather than re-inventing the
    token list — one owner, two consumers". Re-listing the phrases here would create a second list
    that could drift from the first while both kept passing.

    The claim is MEASURED FALSE, not merely off-brand: NF-W1's `foil_matchup` lost at every
    projected position and lost to the flat foil too.
    """
    literals = _ts_string_literals(_COPY_TS.read_text())
    assert len(literals) > 50, "the copy scan extracted almost nothing — it would pass on nothing"
    C.assert_no_matchup_claim(
        [(f"fantasy-claim-copy.ts[{i}]", s) for i, s in enumerate(literals)],
        where="the NF-WK-FE1 weekly page copy",
    )


def test_the_matchup_guard_refuses_the_claim_it_is_pointed_at():
    """The two-sided half. A screen that cannot refuse is not a screen (NF1.7 (a)), and this one is
    imported from another module — so its behaviour here is an assumption until it is exercised."""
    with pytest.raises(ValueError, match="matchup"):
        C.assert_no_matchup_claim(
            [("negative-control", "Our weekly projection is matchup-based.")],
            where="negative control",
        )


def test_the_weekly_page_source_carries_no_matchup_claim_either():
    """The copy module is not the only place a sentence can reach a reader — a component's inline
    heading is exactly where a stronger one would appear, and no module-level screen sees it."""
    for path in _WEEKLY_TREE:
        text = _strip_ts_comments(path.read_text()).lower()
        hits = [p for p in C.FORBIDDEN_CLAIM_PHRASES if p in text]
        assert not hits, f"{path.name} claims {hits}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 1(a) — the POINTS HEAD IS THE PROJECTION: the component line is never summed
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_weekly_tree_never_derives_a_total_from_the_component_line():
    r"""⭐⭐ THE STORY'S CENTRAL RULE, AS A MECHANICAL PROPERTY.

    The points head and the component head are INDEPENDENT models — the promotion review measured
    the gap and it is not zero — so a total derived from the stat line is a SECOND number that does
    not equal the first and that no reader could reconcile. The spec permits either not summing or
    disclosing the discrepancy; this page does not sum, and that is the branch this clause holds.

    ⚠️⚠️ SCOPED TO ARITHMETIC OVER THE PAID FIELDS, not to the word "sum" — and the FIRST CUT OF
    THIS CLAUSE WAS VACUOUS, which is worth recording because the vacuity was invisible by
    inspection. It matched `\.<field>\s*\+`, i.e. a field IMMEDIATELY followed by `+`. A realistic
    derived total is not written that way: `(paid!.passYds ?? 0) + (paid!.rushYds ?? 0)` puts a
    null-coalesce and a bracket between the field and the operator, so the guard sailed straight
    past the exact defect it names. The red proof caught it; inspection had not.

    ⭐ THE SHAPE THAT ACTUALLY HOLDS is statement-level rather than token-adjacent: a derived total
    is a line that combines paid fields arithmetically. Three forms, each its own clause so a
    future reader can see what is covered:
      · two or more distinct paid fields on a line that also carries `+`   (`a.passYds + a.rushYds`)
      · `+=` on a line naming any paid field                              (`total += p.recYds`)
      · a `reduce(` on a line naming any paid field                       (`fields.reduce(…)`)

    ⛔ THE `+` REQUIREMENT IS LOAD-BEARING AGAINST FALSE POSITIVES, not decoration: the per-position
    display lists legitimately name six or seven paid fields on ONE line, and without the operator
    clause this would refuse them.
    """
    paid = set(C.PAID_WEEKLY_PLAYER_FIELDS)
    for path in _WEEKLY_TREE:
        for lineno, line in enumerate(_strip_ts_comments(path.read_text()).splitlines(), 1):
            named = {f for f in paid if re.search(rf"\b{f}\b", line)}
            if not named:
                continue
            where = f"{path.name}:{lineno}"
            assert not (len(named) >= 2 and "+" in line), (
                f"{where} combines paid components {sorted(named)} arithmetically — the component "
                f"head is INDEPENDENT of the points head, so a derived total is a second, "
                f"irreconcilable number: {line.strip()!r}"
            )
            assert "+=" not in line, f"{where} accumulates a paid component: {line.strip()!r}"
            assert "reduce(" not in line, f"{where} reduces over a paid component: {line.strip()!r}"


def test_the_stat_line_note_states_the_independence_rather_than_a_measured_figure():
    """⭐ WHY THE WORDING RATHER THAN THE NUMBER, recorded because it looks like a weaker choice.

    Disclosing the magnitude would require typing the coherence measurement into the copy module,
    which `test_nf_tr1_claim_copy.py::test_the_canonical_copy_module_carries_no_measured_figure`
    refuses outright — and the wire carries no coherence block to read one from, so it could never
    be reconciled against a re-score. One branch of the spec's rule was compliant and one was not.
    """
    note = next(
        s for s in _ts_string_literals(_COPY_TS.read_text())
        if "scoring this line yourself" in s
    )
    assert "independently" in note.lower(), note
    assert not re.search(r"\d\.\d{2,}", note), (
        f"the stat-line note hardcodes a measured figure: {note!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 1(c) — the absence reasons: three causes, three labels, no drift
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_every_served_absence_reason_has_a_frontend_label():
    """⭐ THE CROSS-CHECK, IN THE DIRECTION THAT MATTERS. A reason the server adds and the page has
    never heard of would render under its raw machine key — legible to nobody — which is precisely
    the merged empty state the counts exist to prevent (NF-C6b/NF-K1)."""
    labelled = set(_ts_record_keys(_COPY_TS.read_text(), "WEEKLY_ABSENCE_LABEL"))
    assert labelled, "no WEEKLY_ABSENCE_LABEL keys were extracted — this clause would pass on nothing"
    missing = set(C.ABSENCE_REASONS) - labelled
    assert not missing, (
        f"the served absence reason(s) {sorted(missing)} have no frontend label — they would render "
        "under their raw machine key"
    )


def test_the_frontend_labels_no_reason_the_contract_does_not_declare():
    """The other direction: a label for a reason nothing serves is dead copy that reads as coverage."""
    labelled = set(_ts_record_keys(_COPY_TS.read_text(), "WEEKLY_ABSENCE_LABEL"))
    extra = labelled - set(C.ABSENCE_REASONS)
    assert not extra, f"the page labels absence reason(s) {sorted(extra)} that the contract does not declare"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 2 — the paid set, and the display registry that must track it
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_display_stat_registry_covers_every_paid_component():
    """⭐ THE DERIVED SET IS THE AUTHORITY, and this is the clause that keeps the page honest about
    it. `PAID_WEEKLY_PLAYER_FIELDS` is derived server-side from the scorer's own `STAT_FIELD` map so
    that a new scorable component is withheld AUTOMATICALLY — the NF-EPIC 1 denylist hazard. That
    protects the PAYWALL; it does nothing for the RENDER, so a component added on the server would
    be correctly withheld from free callers and then silently never drawn for paying ones.
    """
    src = _READ_TS.read_text()
    rendered = set(re.findall(r'\{\s*key:\s*"(\w+)"\s*,\s*label:', src))
    assert rendered, "no WEEKLY_STAT_FIELDS entries were extracted — this clause would pass on nothing"
    # The quantile vector is paid but is not a stat-line column; it is the distribution itself.
    components = set(C.PAID_WEEKLY_PLAYER_FIELDS) - {C.QUANTILE_VECTOR_FIELD}
    assert components == rendered, (
        f"the weekly stat-line registry disagrees with the contract's derived paid set — "
        f"only on the server: {sorted(components - rendered)}; only on the page: {sorted(rendered - components)}"
    )


def test_every_position_stat_list_names_only_real_component_fields():
    """A per-position display list naming a field that does not exist renders nothing, silently."""
    src = _READ_TS.read_text()
    block = src.split("WEEKLY_STATS_BY_POSITION", 1)[1].split("}", 1)[0]
    named = set(re.findall(r'"(\w+)"', block))
    assert named, "no per-position stat fields extracted — this clause would pass on nothing"
    unknown = named - set(C.PAID_WEEKLY_PLAYER_FIELDS)
    assert not unknown, f"the per-position stat lists name non-existent field(s): {sorted(unknown)}"


def test_the_paid_read_is_never_routed_through_the_cdn_arm():
    """⛔ THE EDGE ROUTE STRIPS `Authorization` BY DESIGN, so a request for paid data through it
    arrives anonymous — and its refusal (or, far worse, a paid body) would be pinned into a PUBLIC
    cache entry and served to every visitor for the rest of the window.

    ⚠️ Asserted on the FETCHER's own body rather than page-wide: the free fetchers legitimately call
    `cdnFetch`, so a file-level scan would pass no matter what the paid one did.
    """
    src = _strip_ts_comments(_READ_TS.read_text())
    body = src.split("export function getWeeklyProjectionsFull", 1)[1].split("\n}", 1)[0]
    assert "cdnFetch" not in body, "the PAID weekly fetcher routes through the CDN arm"
    assert "apiFetch" in body, "the paid weekly fetcher does not call the tokened API path at all"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 1(e) — the pricing framing: formats that do not exist yet, never withheld ones
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_ppr_framing_says_the_other_formats_do_not_exist_rather_than_that_they_are_withheld():
    """⭐ THE ONE SENTENCE THAT COULD SELL SOMETHING WE CANNOT DELIVER. The season board has thirteen
    formats with one free; the weekly point has ONE, and it is not a paywall — re-scoring needs the
    per-stat line and a scorer, which is the deferred gate-3 story. "One free format" implies twelve
    locked ones.

    ⚠️ EACH CLAUSE HAS ITS OWN ISOLATING ASSERTION (NF-D17): the "does not exist" half and the "not
    a lock" half are checked separately, so deleting either turns exactly one of them red rather
    than both passing on the other's strength.
    """
    detail = next(
        s for s in _ts_string_literals(_COPY_TS.read_text())
        if "PPR by construction" in s
    )
    low = detail.lower()
    assert "not being withheld" in low, f"the PPR framing does not say the formats are not withheld: {detail!r}"
    assert "do not exist" in low, f"the PPR framing does not say the other formats do not exist yet: {detail!r}"
    for forbidden in ("one free format", "unlock", "upgrade to see"):
        assert forbidden not in low, f"the PPR framing reads as a paywall ({forbidden!r}): {detail!r}"


def test_the_weekly_routes_take_no_scoring_format_parameter():
    r"""The code-level half of the same rule. A `config`/`size` parameter that did nothing today
    would be declaration outrunning production, and it would invite the client to render locks over
    formats we cannot compute — the contract's own words.

    ⚠️ BOTH SPELLINGS, AND THE FIRST CUT ONLY HAD ONE. It scanned for `config=` — the query-string
    form — and missed `config: "full_ppr"` inside the `URLSearchParams` object literal, which is how
    a parameter would ACTUALLY be added in this file. The red proof caught it. `[:=]` covers both.

    ⛔ WORD-BOUNDED, so `scoring_system_id` (a real contract FIELD this module legitimately mirrors)
    does not trip the `scoring` clause: `\bscoring\s*[:=]` cannot match it, because what follows
    `scoring` there is `_system_id` rather than a separator.
    """
    src = _strip_ts_comments(_READ_TS.read_text())
    for param in ("config", "size", "scoring"):
        hit = re.search(rf"\b{param}\s*[:=]", src)
        assert not hit, (
            f"the weekly read layer sends a {param!r} parameter ({hit.group(0)!r}) — the weekly "
            "point is PPR-native and the routes accept no format parameter at all"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 2 — no fourth scorer
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_weekly_tree_imports_no_scorer():
    r"""⛔ THE REPO ALREADY CARRIES THREE IMPLEMENTATIONS of the season scoring policy under a
    merge-gating parity test. A fourth, weekly one is that tax again — and it would also be WRONG:
    the weekly point is the champion's own PPR output, not a re-scoring of a stat line.

    ⚠️⚠️ IDENTIFIER BOUNDARIES, NOT SUBSTRINGS, AND THIS CLAUSE PAID FOR THE LESSON ITSELF. Its
    first cut matched `"STAT_FIELD" in src` and fired on this story's OWN `WEEKLY_STAT_FIELDS`
    display registry — the `'temp' ⊂ 'attempt'` over-eager-guard shape, which refuses honest code
    while looking like enforcement. `\b` does the right thing here for a reason worth stating: `_`
    is a word character, so `\bSTAT_FIELD\b` cannot match inside `WEEKLY_STAT_FIELDS` at either
    end, while a real bare reference to the scorer's map still matches.
    """
    scorers = ("league-scoring", "buildBoard", "scoreRow", "STAT_FIELD", "fantasy_engine")
    for path in _WEEKLY_TREE:
        src = _strip_ts_comments(path.read_text())
        for scorer in scorers:
            # `-` is not a word char, so a module specifier needs its own literal check.
            pattern = re.escape(scorer) if "-" in scorer else rf"\b{re.escape(scorer)}\b"
            hit = re.search(pattern, src)
            assert not hit, (
                f"{path.name} reaches for a scorer ({scorer!r}) — the weekly point comes from the "
                "payload and nothing on this surface re-scores it"
            )


def test_the_no_scorer_clause_is_not_satisfied_by_this_story_s_own_registry():
    """⭐ THE TWO-SIDED PROOF OF THE FIX ABOVE, as a standing clause rather than a one-off check.

    Two assertions, and they fail differently: the first says the guard is not over-eager (it must
    ACCEPT the legitimate `WEEKLY_STAT_FIELDS` name), the second says it is not vacuous (it must
    still REFUSE a real bare reference). A guard that only ever passes is the defect this whole
    suite exists to prevent.
    """
    assert re.search(r"\bSTAT_FIELD\b", "export const WEEKLY_STAT_FIELDS = [") is None
    assert re.search(r"\bSTAT_FIELD\b", "import { STAT_FIELD } from '@/lib/scoring'") is not None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The nav door
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_weekly_nav_entry_exists_and_is_public_beside_the_season_projections():
    """⭐ REACHABILITY IS THE POINT (NCAAF-P3.9: a live surface with no route to it). The E2E clause
    drives the menu; this one pins the DECLARATION, including the `public` flag — the weekly reads
    are `GENERIC_BOARD` and take no `Request`, so the item is safe to show a logged-out visitor,
    and an item whose endpoints 403 would render a permanently broken page instead."""
    src = _strip_ts_comments(_NAV_TS.read_text())
    assert '"/fantasy/weekly"' in src, "the weekly page has no nav entry at all"
    entry = src.split('"/fantasy/weekly"', 1)[1].split("}", 1)[0]
    assert "public: true" in entry, "the weekly nav entry is not marked public"
    assert '"fantasy-weekly"' in entry, "the weekly nav entry declares no key"
    # Beside the season board: the two answer the same question over different horizons.
    weekly_at = src.index('"/fantasy/weekly"')
    projections_at = src.index('"/fantasy/projections"')
    between = src[min(weekly_at, projections_at):max(weekly_at, projections_at)]
    assert between.count("href:") <= 1, (
        "the weekly nav entry is not adjacent to Projections in the menu declaration"
    )


def test_the_nav_label_comes_from_the_canonical_copy_module():
    """A nav label is claim-adjacent copy — "This Week" is a promise the page has to keep — so it
    belongs where every other user-facing string is screened, not typed into a data module no
    denylist has ever looked at.

    ⚠️⚠️ ASSERTED ON THE USE SITE, NOT ON THE IDENTIFIER. The first cut checked
    `"WEEKLY_NAV_LABEL" in src` and stayed GREEN with the label hardcoded — because the IMPORT LINE
    still carried the name. That is the repo's recurring "a guard that greps for an identifier is
    satisfied by the import alone" shape (the NF-C0e wired-≠-invoked family), and the red proof is
    what surfaced it.
    """
    src = _strip_ts_comments(_NAV_TS.read_text())
    assert "label: WEEKLY_NAV_LABEL" in src, (
        "the weekly nav label is not READ from the copy module at its use site — importing the "
        "constant and then hardcoding the string satisfies an identifier scan but not this"
    )
    label = next(s for s in _ts_string_literals(_COPY_TS.read_text()) if s == "This Week")
    assert label == "This Week"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The fixtures are the SHIPPING writer's own output
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_weekly_fixtures_validate_against_the_contract():
    """A fixture that does not validate is a payload no server could ever send, and every E2E
    conclusion drawn from it would be about a world that does not exist."""
    C.NflWeeklyManifest.model_validate(json.loads(_MANIFEST_FIXTURE.read_text()))
    C.NflWeeklyPayload.model_validate(json.loads(_ENTITLED_FIXTURE.read_text()))
    C.NflWeeklyPayload.model_validate(json.loads(_FREE_FIXTURE.read_text()))


def test_the_free_fixture_is_the_shipping_reducer_applied_to_the_entitled_one():
    """⭐ THE ENTITLEMENT SPEC'S FOUNDATION. If the "free" fixture were hand-reduced, every clause
    asserting "a free caller cannot see this" would be asserting against the fixture author's idea
    of the paywall rather than against the paywall itself."""
    entitled = json.loads(_ENTITLED_FIXTURE.read_text())
    free = json.loads(_FREE_FIXTURE.read_text())
    assert free == C.public_weekly_payload(entitled), (
        "the free weekly fixture is not `public_weekly_payload` of the entitled one — regenerate:\n"
        "  uv run python frontend/e2e/fixtures/build-nfl-weekly.py"
    )


def test_the_fixtures_are_two_sided_so_the_leak_check_cannot_pass_vacuously():
    """⚠️ BOTH DIRECTIONS. "The free blob carries no paid field" is trivially true of a blob with no
    fields at all — so the entitled one must actually CARRY them (NF1.7 (a))."""
    entitled = json.loads(_ENTITLED_FIXTURE.read_text())
    free = json.loads(_FREE_FIXTURE.read_text())
    present = C.paid_weekly_fields_present(entitled)
    assert len(present) >= 5, f"the entitled fixture carries only {sorted(present)} — too thin to test a gate"
    assert C.paid_weekly_fields_present(free) == set(), "the free fixture carries a paid value"


@pytest.mark.parametrize(
    "prop,predicate,why",
    [
        ("a bye", lambda p: p["status"] == "bye",
         "a bye is a DETERMINISTIC zero, and the page must render it as one rather than as a gap"),
        ("a week-1 rookie", lambda p: p["histWeeks"] == 0,
         "a projection standing on position and a rookie flag alone is exactly the row whose thin "
         "evidence base has to be visible"),
        ("a final-week row", lambda p: p["rosPpr"] is None,
         "a declared null ros is a different fact from a ros of zero"),
        ("a projected row", lambda p: p["status"] == "projected",
         "the ordinary case"),
    ],
    # ⚠️ EXPLICIT IDS. Without them pytest derives a node id containing `<lambda>` and the whole
    # `why` sentence — unstable, unquotable, and a red-proof anchor keyed on it breaks the moment
    # the prose is reworded. The resolve-every-node leg of `nf_wk_fe1_red_proof.py` caught exactly
    # that before any mutation ran, which is the leg working as designed.
    ids=["bye", "rookie", "final-week", "projected"],
)
def test_the_fixture_reaches_every_state_the_page_distinguishes(prop, predicate, why):
    """⭐ ONE CLAUSE PER STATE (NF-D17's isolating-fixture rule): a single "the fixture is rich
    enough" assertion would go red for whichever state vanished first and say nothing about the
    others."""
    players = json.loads(_FREE_FIXTURE.read_text())["players"]
    assert any(predicate(p) for p in players), f"the weekly fixture carries no {prop} — {why}"
