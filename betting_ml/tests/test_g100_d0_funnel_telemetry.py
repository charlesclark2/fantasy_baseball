"""G100-D0 — the funnel event contract, pinned across the three places that must agree.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS FILE GUARDS
═══════════════════════════════════════════════════════════════════════════════════════════════════

A conversion dashboard has a failure mode that no other kind of code has: when it breaks, it does
not error. It renders a number. An event that was renamed, or that quietly stopped being emitted,
produces a chart reading ZERO — and a zero on a conversion chart looks like a conversion collapse,
not like a bug. Somebody then spends a sprint fixing pricing.

Three artifacts have to say the same thing, and nothing but a test can hold them together:

  · `frontend/lib/funnel-telemetry.ts`                  — the names the app emits
  · `scripts/provision_posthog_funnel_dashboard.py`     — the names the dashboard reads
  · `docs/g100_d0_funnel.md`                            — the names a human is told about

⭐ AND THE HARDEST ONE: an event can be DECLARED in all three and never actually FIRE. That is the
NF-C0e "wired ≠ invoked" class, and it cost this repo a projection module that appeared in the
profile, the catalog, both frontend mirrors and the export map while nothing ever called it. So
this file does not check that names MATCH — matching names is cheap and proves nothing. It checks
that every declared step has a real CALL SITE, and that every emitter helper has a real CALLER.

═══════════════════════════════════════════════════════════════════════════════════════════════════
HOW THESE ASSERTIONS AVOID BEING VACUOUS
═══════════════════════════════════════════════════════════════════════════════════════════════════

Two rules, both learned expensively in this repo, are applied throughout:

  1. ⛔ PROSE MUST NOT BE ABLE TO SATISFY A SOURCE GUARD (INC-38). Every source scan below runs on
     COMMENT-STRIPPED text. The names in this codebase appear constantly in explanatory comments —
     `funnel-telemetry.ts` alone mentions all six in its header — so a guard matching raw source
     would go green with every capture deleted.
  2. ⛔ AN ITERATED ASSERTION MUST PROVE ITS MATCH SET IS NON-EMPTY (DSR-CONV #690). A loop over
     zero matches passes on nothing and reads as coverage. Every discovery below is asserted
     non-empty before anything is concluded from it.

⛔ WHAT THIS FILE CANNOT PROVE: that the events leave the browser. A name present in the source is
not an event on the wire — posthog-js silently drops captures under a bot filter, and this repo has
already been in exactly that state. `frontend/e2e/specs/funnel-telemetry.spec.ts` drives the real
rendered app and reads the ingest request body; and neither can prove the events reach OUR PostHog
project, which is the operator walk in `docs/g100_d0_funnel.md` §7.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.provision_posthog_funnel_dashboard import (
    FUNNEL_SPINE,
    MAX_DESCRIPTION_CHARS,
    RATES,
    STEP_LABELS,
    build_dashboard_spec,
)

REPO = Path(__file__).resolve().parents[2]
CONTRACT_TS = REPO / "frontend" / "lib" / "funnel-telemetry.ts"
EMIT_TS = REPO / "frontend" / "lib" / "funnel-telemetry-emit.ts"
DOC = REPO / "docs" / "g100_d0_funnel.md"

#: Where application code lives. `frontend/e2e` is excluded on purpose: a test file naming an event
#: must never be able to satisfy "this event is emitted" — that is the guard measuring itself.
APP_DIRS = ("app", "components", "lib", "hooks")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════════════════════


def strip_ts_comments(source: str) -> str:
    """Remove `//` and `/* */` comments without mangling string literals.

    A single pass with explicit state, rather than two regex passes, because the two-pass form is
    order-dependent and wrong in both orders: stripping block comments first destroys a `//` inside
    one, stripping line comments first destroys the `//` in a `https://` URL sitting inside a block
    comment. Tracking quotes is what makes a `"// not a comment"` string literal survive.
    """
    out: list[str] = []
    i, n = 0, len(source)
    quote: str | None = None
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if quote:
            out.append(ch)
            if ch == "\\":  # escape: consume the next char verbatim
                if i + 1 < n:
                    out.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def app_sources() -> dict[Path, str]:
    """Every application `.ts`/`.tsx` file, comment-stripped, keyed by path."""
    found: dict[Path, str] = {}
    for directory in APP_DIRS:
        root = REPO / "frontend" / directory
        if not root.exists():
            continue
        for path in root.rglob("*.ts*"):
            if path.suffix not in (".ts", ".tsx"):
                continue
            found[path] = strip_ts_comments(path.read_text(encoding="utf8"))
    return found


def contract_event_map() -> dict[str, str]:
    """`FUNNEL_EVENTS` as {CONSTANT_KEY: "event_name"}, read from the TS source."""
    body = strip_ts_comments(CONTRACT_TS.read_text(encoding="utf8"))
    block = re.search(r"export const FUNNEL_EVENTS = \{(.*?)\n\} as const", body, re.S)
    assert block, "FUNNEL_EVENTS is no longer a recognisable object literal in the TS contract"
    pairs = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block.group(1)))
    assert pairs, "FUNNEL_EVENTS parsed to nothing — the guard below would pass on an empty set"
    return pairs


#: Every `.capture(...)` call site in application code, as the event name it names.
CAPTURE_CALL = re.compile(r"\.capture\(\s*(?:\"([^\"]+)\"|FUNNEL_EVENTS\.([A-Z_0-9]+))")


def capture_call_sites() -> dict[str, set[Path]]:
    """{event name -> files that CALL capture with it}.

    ⚠️ A CALL-SITE regex, not a substring search. This repo names things after the functions that
    use them — a `FUNNEL_EVENTS` key, a dict key, a doc row — so `grep -c "landing_view"` counts
    declarations as if they were emissions and a guard built on it passes with every capture
    deleted (the defect DSR-CONV #690 shipped, in a guard written to prevent exactly this).
    """
    keys = contract_event_map()
    sites: dict[str, set[Path]] = {}
    for path, body in app_sources().items():
        for literal, key in CAPTURE_CALL.findall(body):
            name = literal or keys.get(key)
            if name:
                sites.setdefault(name, set()).add(path)
    return sites


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The three artifacts agree
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_ts_contract_and_the_dashboard_name_the_same_spine_in_the_same_order():
    keys = contract_event_map()
    body = strip_ts_comments(CONTRACT_TS.read_text(encoding="utf8"))
    block = re.search(r"export const FUNNEL_SPINE = \[(.*?)\n\] as const", body, re.S)
    assert block, "FUNNEL_SPINE is no longer a recognisable array in the TS contract"

    ts_spine = [keys[k] for k in re.findall(r"FUNNEL_EVENTS\.([A-Z_0-9]+)", block.group(1))]
    assert ts_spine, "FUNNEL_SPINE parsed to nothing"
    # ORDER, not just membership: the dashboard's funnel is ORDERED, so a person is counted at step
    # n+1 only if they reached step n. A reordered spine silently re-defines every rate.
    assert ts_spine == list(FUNNEL_SPINE)


def test_every_spine_step_is_documented_for_a_human():
    doc = DOC.read_text(encoding="utf8")
    missing = [e for e in FUNNEL_SPINE if f"`{e}`" not in doc]
    assert not missing, f"undocumented funnel steps: {missing}"
    # And every step is labelled on the dashboard itself — an unlabelled funnel step renders as a
    # raw event name, which is where a reader stops being able to tell step 4 is ACTIVATION.
    assert set(STEP_LABELS) == set(FUNNEL_SPINE)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⭐ Declared IS emitted — the "wired ≠ invoked" guard
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("event", FUNNEL_SPINE)
def test_every_charted_event_has_a_real_capture_call_site(event: str):
    """⛔ Do not chart a metric that is not emitted.

    One case per event rather than one loop, so a step that stops firing fails on its OWN row
    instead of being masked by a sibling — and so the failure message names the dead step.
    """
    sites = capture_call_sites()
    assert sites, "no capture call sites found at all — the scan is broken, not the app"
    assert event in sites, (
        f"`{event}` is on the dashboard's spine but nothing in frontend/{{{','.join(APP_DIRS)}}} "
        f"calls capture with it. The chart for this step will read a permanent ZERO, which looks "
        f"like a conversion collapse rather than missing instrumentation."
    )


def test_every_emitter_helper_has_a_caller_outside_its_own_module():
    """The NF-C0e defect, verbatim: a module wired into every registry that nothing ever calls.

    A helper that exists, type-checks and is exported is not instrumentation until something
    invokes it.
    """
    emit_body = strip_ts_comments(EMIT_TS.read_text(encoding="utf8"))
    helpers = re.findall(r"export function (\w+)\(", emit_body)
    assert helpers, "no exported emitters found — this test would otherwise pass on nothing"
    # Non-vacuity with teeth: the three captures must be among them, so a rename that empties the
    # discovery cannot quietly satisfy the loop.
    assert {"captureLandingView", "captureCheckoutStarted", "captureSubscriptionStarted"} <= set(
        helpers
    )

    uncalled = []
    for helper in helpers:
        call = re.compile(rf"\b{helper}\(")
        callers = [p for p, b in app_sources().items() if p != EMIT_TS and call.search(b)]
        if not callers:
            uncalled.append(helper)
    assert not uncalled, (
        f"declared but never invoked: {uncalled}. Exported and imported is not the same as called; "
        f"an emitter nobody calls charts a zero."
    )


def test_the_activation_event_is_emitted_from_both_doors_into_a_league():
    """`league_config_completed` must fire from the manual editor AND the importer.

    A funnel that saw only one door would read the other's users as never having activated — and
    the manual editor is the FLOOR beneath platform import (NF-C0b), i.e. exactly the users whose
    platform we cannot reach.
    """
    sites = capture_call_sites().get("league_config_completed", set())
    names = {p.name for p in sites}
    assert "league-settings-editor.tsx" in names, "the manual door stopped emitting activation"
    assert "league-import.tsx" in names, "the import door stopped emitting activation"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The dashboard counts PERSONS, and its rates are the documented ones
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_no_series_anywhere_on_the_dashboard_counts_events():
    """⭐ THE CORRECTNESS RISK THE WHOLE STORY TURNS ON.

    `custom_board_viewed` fires once per page MOUNT, and one real user produced three in an hour
    during G100-C1's live testing. A single series left on `math: "total"` inflates activation with
    revisits; an inflated activation rate reads as a CONVERSION problem; and the next story goes and
    rebuilds pricing. `dau` is PostHog's unique-persons-in-period aggregation.
    """
    spec = build_dashboard_spec()
    maths: list[str] = []
    for insight in spec["insights"]:
        for series in insight["query"]["source"].get("series", []):
            if insight["query"]["source"]["kind"] == "TrendsQuery":
                maths.append(series.get("math", "<unset>"))
    assert maths, "no trend series found — this assertion would pass on an empty dashboard"
    assert set(maths) == {"dau"}, f"a series counts events rather than persons: {sorted(set(maths))}"


def test_funnels_are_ordered_and_person_level():
    spec = build_dashboard_spec()
    funnels = [i for i in spec["insights"] if i["query"]["source"]["kind"] == "FunnelsQuery"]
    assert funnels, "the dashboard has no funnel insight — the cohort-correct rates are gone"
    for insight in funnels:
        f = insight["query"]["source"]["funnelsFilter"]
        assert f["funnelOrderType"] == "ordered", insight["name"]
        # A funnel with no window counts a conversion that happened months later as if it followed
        # from the visit, which makes every rate drift upward forever.
        assert f["funnelWindowInterval"] > 0, insight["name"]
        # ⛔ Never group-level. `aggregation_group_type_index` would aggregate by organisation
        # rather than by person; absent means person-level, which is what every rate is defined on.
        assert "aggregation_group_type_index" not in insight["query"]["source"], insight["name"]


@pytest.mark.parametrize("rate", RATES, ids=lambda r: r.key)
def test_each_rate_divides_the_documented_numerator_by_the_documented_denominator(rate):
    """One case per rate, so an inverted ratio fails on its own row.

    ⚠️ Series ORDER is load-bearing: PostHog's `formula` addresses series positionally as A, B, …
    so swapping them silently inverts the rate — and an inverted conversion rate is a plausible
    number, not an obvious error.
    """
    assert rate.numerator in FUNNEL_SPINE and rate.denominator in FUNNEL_SPINE
    insight = next(i for i in build_dashboard_spec()["insights"] if i["name"] == rate.title)
    source = insight["query"]["source"]
    assert [s["event"] for s in source["series"]] == [rate.denominator, rate.numerator]
    assert source["trendsFilter"]["formula"] == "B / A"
    # The definition travels with the chart. A rate whose denominator is not visible beside it will
    # be misread, and each of these statements names the specific misreading it is exposed to.
    assert "NUMERATOR:" in insight["description"] and "DENOMINATOR:" in insight["description"]


def test_no_description_exceeds_what_posthog_will_accept():
    """⭐ A LIVE PROVISIONING FAILURE, turned into an offline one.

    The first real `--apply` created three insights and then died on the fourth with
    `{"code":"max_length","detail":"Ensure this field has no more than 400 characters."}` — an
    ONLINE, PARTIAL failure, which is the worst shape available for a step the operator runs once
    and reads the output of. It left a half-built dashboard behind.

    `build_dashboard_spec` now refuses over-budget text itself, so `--dry-run` catches it with no
    network and no credential; this pins the budget so a future edit that grows a description finds
    out in CI rather than mid-provision.
    """
    spec = build_dashboard_spec()
    texts = [("<dashboard>", spec["dashboard"]["description"])]
    texts += [(i["name"], i["description"]) for i in spec["insights"]]
    assert texts, "no descriptions found — this assertion would pass on an empty dashboard"
    over = [(n, len(t)) for n, t in texts if len(t) > MAX_DESCRIPTION_CHARS]
    assert not over, f"PostHog will reject these: {over}"


def test_the_dashboard_lookup_never_uses_the_insight_filter_posthog_500s_on():
    """⭐ THE OTHER LIVE FAILURE. `GET /insights/?dashboards=<id>` returns HTTP 500 from PostHog.

    Measured 2026-08-09 against us.posthog.com: the same key lists `/insights/?limit=1` at 200, so
    it is a server-side fault in that filter rather than a scope or auth problem. The idempotency
    lookup therefore reads `tiles[].insight` off the dashboard's own detail payload.

    ⭐ That is also the BETTER question — a name-matched global insight list would collide with an
    insight of the same name on somebody ELSE'S dashboard, so the original form was one PostHog
    bugfix away from silently updating the wrong object.

    ⚠️ ASSERTS THE REQUEST, NOT THE SOURCE TEXT. The first cut of this test scanned the module for
    the offending URL and FAILED — because `insights_on`'s own docstring documents the trap, and a
    `#`-only comment stripper does not remove docstrings. That is the INC-38 prose problem facing
    the other way: prose causing a false FAILURE rather than a false pass. Driving the real method
    against a recording transport is immune to both, and it exercises the tile parsing as well.
    """
    from scripts.provision_posthog_funnel_dashboard import PostHogApi

    api = PostHogApi("https://example.invalid", "1", "key")
    calls: list[tuple[str, str]] = []

    def record(method: str, path: str, body: dict | None = None) -> dict:
        calls.append((method, path))
        return {
            "tiles": [
                {"insight": {"id": 1, "name": "Live one"}},
                # A soft-deleted insight keeps its row; a detached tile must not be mistaken for a
                # live one, or the next run would "update" a chart nobody can see.
                {"insight": {"id": 2, "name": "Removed one", "deleted": True}},
                # Text/widget tiles carry no insight at all.
                {"insight": None, "text": {"body": "a note"}},
            ]
        }

    api._request = record  # type: ignore[method-assign]
    found = api.insights_on(1974886)

    assert calls == [("GET", "/dashboards/1974886/")], (
        f"the idempotency lookup requested {calls} — it must read the dashboard's own tiles, never "
        f"the insight filter PostHog 500s on"
    )
    assert found == {"Live one": 1}


def test_activation_is_the_denominator_of_paid_conversion():
    r3 = next(r for r in RATES if r.key == "r3_activation_to_paid")
    assert r3.denominator == "custom_board_viewed"
    assert r3.numerator == "subscription_started"


@pytest.mark.parametrize(
    ("substring", "why"),
    [
        ("COGNITO", "new-account counts must be attributed to Cognito, not to a funnel event"),
        ("STRIPE", "the paid COUNT must be attributed to Stripe, not to a client-confirmed event"),
    ],
)
def test_the_dashboard_states_where_the_real_numbers_come_from(substring: str, why: str):
    """Two source-of-truth caveats, one case each so deleting either fails on its own row.

    `user_signup_completed` includes a returning user who clicked Sign Up; `subscription_started` is
    lost when a buyer closes the tab during provisioning. Both are the right funnel STEPS and the
    wrong TOTALS, and a dashboard that does not say so will be read as if they were the totals.
    """
    spec = build_dashboard_spec()
    blob = spec["dashboard"]["description"] + " ".join(i["description"] for i in spec["insights"])
    assert substring in blob, why


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The two structural properties that were shipped defects in the first cut
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_contract_module_stays_importable_from_a_server_component():
    """⭐ A SHIPPED DEFECT, caught on the wire by the E2E suite and pinned here.

    The first cut had `"use client"` and a `posthog` import at the top of the contract module. The
    home page is a SERVER component; it imported `ACQUISITION_SURFACES.HOME` from there and passed
    it as a prop, and Next.js resolved the module to a client REFERENCE rather than to its values —
    so the prop serialised to `undefined` and every `landing_view` from the highest-traffic page in
    the product shipped with no `surface`. `tsc` was happy, `next build` was happy, the event still
    fired, and nothing anywhere looked wrong.

    The contract must therefore stay free of both, with everything posthog-touching in the emit
    module.
    """
    body = CONTRACT_TS.read_text(encoding="utf8")
    stripped = strip_ts_comments(body)
    assert '"use client"' not in stripped, (
        "the contract module is a client boundary again — a server component importing a constant "
        "from it now receives `undefined`, silently"
    )
    assert "posthog" not in stripped, "the contract module imports posthog again"
    # Non-vacuity: it must still actually BE the contract, or the two assertions above are trivially
    # satisfied by an empty file.
    assert "ACQUISITION_SURFACES" in stripped and "FUNNEL_EVENTS" in stripped


def test_no_comped_group_is_ever_counted_as_a_paying_conversion():
    """⭐ THE GUARD ON THE HEADLINE NUMBER.

    `admin`, `beta_tester` and `fantasy_comp` have full access and pay nothing. Folding them into
    `paid` puts the operator's own account and every beta tester into the numerator of
    ACTIVATION→paid. At launch scale that is not a rounding error — it is most of the numerator, and
    the resulting rate is flattering and fictional.
    """
    body = strip_ts_comments(CONTRACT_TS.read_text(encoding="utf8"))
    paying = re.search(r"const PAYING_GROUPS = \[(.*?)\]", body, re.S)
    comped = re.search(r"const COMPED_GROUPS = \[(.*?)\]", body, re.S)
    assert paying and comped, "the paid/comped split is no longer expressed as two group lists"

    paying_groups = set(re.findall(r"\"([^\"]+)\"", paying.group(1)))
    comped_groups = set(re.findall(r"\"([^\"]+)\"", comped.group(1)))
    assert paying_groups == {"subscriber"}, f"a non-paying group joined PAYING_GROUPS: {paying_groups}"
    assert {"admin", "beta_tester", "fantasy_comp"} <= comped_groups
    assert not (paying_groups & comped_groups)


def test_landing_view_is_mounted_only_on_declared_acquisition_surfaces():
    """The funnel's DENOMINATOR is whatever set of pages mounts `<LandingView/>`.

    A new public route quietly joining it depresses every rate below with no code change anywhere
    near the funnel — so the set is pinned. ⛔ `/subscribe` and `/login` are public and are NOT
    acquisition surfaces: one is the conversion surface, the other a return path, and counting
    people already deep in the funnel as fresh visitors manufactures a conversion problem that is
    not there.
    """
    mounting = {
        path.relative_to(REPO / "frontend" / "app").as_posix()
        for path, body in app_sources().items()
        if "<LandingView" in body and (REPO / "frontend" / "app") in path.parents
    }
    assert mounting, "nothing mounts <LandingView/> — the funnel has no denominator"
    assert mounting == {
        "page.tsx",
        "fantasy/rankings/page.tsx",
        "fantasy/projections/page.tsx",
        "fantasy/player/[playerId]/page.tsx",
    }, (
        f"the top of the funnel changed shape: {sorted(mounting)}. If this is deliberate, update "
        f"docs/g100_d0_funnel.md too — every rate's denominator moved."
    )
