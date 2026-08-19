"""NF-C-LDA-0 — the CREDENTIAL RED LINE for the ESPN draft-read extension.

`docs/nf_c0_espn_access_probe.md` §3(c) refuses holding or replaying a user's `espn_s2` session
cookie (not read-scoped, not individually revocable, no consent screen, long-lived ⇒ functionally a
password). §3(d) permits the user-mediated paste because a response BODY structurally cannot carry
that cookie, while a REQUEST HEADER can.

The extension sits exactly on that line, and it is one refactor from the wrong side of it: a
content script with an ESPN host permission can call ESPN's league API and the browser will attach
the user's cookie for it. That is "an authenticated request made on the user's behalf" wearing an
extension costume — and the probe memo names the pressure that produces it (⛔ "never offer 'paste
your cookie instead' for a user who finds the copy awkward").

⇒ THE INVARIANT: **observe, never originate.** Every reading is a passive wrapper over a call the
page already made. This suite fails the build if that decays.

⚠️ EVERY CLAUSE IS INDEPENDENTLY RED-PROVABLE (NF-D17). A guard on an `and`-composed rule stays
green when you delete the clause it names, because another clause already refuses the fixture — so
each test below isolates ONE token class, and `docs/nf_c_lda_0_espn_live_draft_spike.md` §6 records
the deliberate-break run that proved each goes red.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXT = REPO / "extension"
MANIFEST = EXT / "manifest.json"
SRC_DIR = EXT / "src"


def _strip_comments(src: str) -> str:
    """Line comments BEFORE block comments — a `//` inside a `/* */` is prose, and stripping blocks
    first would leave the line stripper eating real code that follows on the same line.

    ⚠️ LOAD-BEARING HERE, not boilerplate. `main-world-probe.js` DOCUMENTS this red line in prose
    that necessarily contains the forbidden tokens ("...grows an originating call or touches
    `document.cookie`"). Without stripping, the comment explaining the rule would TRIP the rule —
    the INC-38 lesson in its most literal form, facing the false-POSITIVE direction.
    """
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _sources() -> dict[str, str]:
    return {p.name: _strip_comments(p.read_text()) for p in sorted(SRC_DIR.glob("*.js"))}


def test_the_extension_sources_exist_and_are_non_empty():
    """⚠️ NON-VACUITY FIRST. Every clause below iterates `_sources()`; an empty mapping would make
    all of them pass on nothing — the guard-that-cannot-fail class arriving through the fixture
    rather than through the assertion (NF1.7(a))."""
    srcs = _sources()
    assert srcs, "no extension sources found — every red-line clause below would pass vacuously"
    assert {"main-world-probe.js", "content.js"} <= set(srcs)
    for name, body in srcs.items():
        assert len(body.strip()) > 200, f"{name} is too small to be the real source"


# ── Clause 1: the manifest may not REQUEST a credential-bearing capability ────────────────────
#: Permissions that would let the extension reach a credential or a request header directly. A
#: `cookies` permission is the literal §3(c) path; `webRequest` sees request headers, which is the
#: one place `Cookie:`/`Authorization:` actually appear.
FORBIDDEN_PERMISSIONS = {"cookies", "webRequest", "webRequestBlocking", "declarativeNetRequest"}


def test_the_manifest_requests_no_credential_bearing_permission():
    manifest = json.loads(MANIFEST.read_text())
    declared = set(manifest.get("permissions") or []) | set(manifest.get("optional_permissions") or [])
    leaked = declared & FORBIDDEN_PERMISSIONS
    assert not leaked, (
        f"manifest requests {sorted(leaked)} — a capability that reaches the user's ESPN "
        "credential or its request headers. §3(c) refuses this."
    )


def test_the_manifest_host_scope_is_narrow():
    """A broad host permission is how a draft-read probe quietly becomes an ESPN-wide reader."""
    manifest = json.loads(MANIFEST.read_text())
    hosts = list(manifest.get("host_permissions") or [])
    assert hosts, "no host_permissions — the probe could not run, so the scope clause is vacuous"
    for h in hosts:
        assert "<all_urls>" not in h, f"host permission {h!r} is unbounded"
        assert not h.startswith("*://"), f"host permission {h!r} spans every scheme/host"
        assert "espn.com" in h, f"host permission {h!r} reaches beyond ESPN"
        assert "/football/draft" in h, (
            f"host permission {h!r} is broader than the draft room this spike reads"
        )


# ── Clause 2: no source may READ a credential ────────────────────────────────────────────────
CREDENTIAL_TOKENS = ("document.cookie", "chrome.cookies", "browser.cookies", "requestHeaders")


@pytest.mark.parametrize("token", CREDENTIAL_TOKENS)
def test_no_source_reads_a_credential(token: str):
    for name, body in _sources().items():
        assert token not in body, (
            f"{name} references {token!r}. The extension must never come into possession of the "
            "user's session credential (§3(c)); it reads response BODIES only."
        )


# ── Clause 3: no source may ORIGINATE a network call ─────────────────────────────────────────
#: ⭐ THE PRECISION HERE IS THE WHOLE POINT, and a naive check would be WRONG IN BOTH DIRECTIONS.
#: The probe legitimately WRAPS `fetch`/`XMLHttpRequest`/`WebSocket` to observe them, so a blanket
#: ban on the word `fetch` would refuse the working design; and a check loose enough to allow the
#: wrappers must still catch a real call. The discriminator is that a WRAPPER only ever re-invokes
#: the SAVED ORIGINAL (`origFetch.apply(...)`, `new OrigWS(...)`, `sendOrig.apply(...)`) and
#: assigns to the global (`window.fetch = ...`), whereas ORIGINATING requires constructing or
#: calling the global name itself. These tokens are exactly the second set.
ORIGINATING_TOKENS = (
    "fetch(",                 # a direct call; the wrapper only ever does `origFetch.apply(`
    "new WebSocket(",         # the wrapper does `new OrigWS(`
    "new XMLHttpRequest(",    # the wrapper never constructs one
    "sendBeacon",             # exfiltration primitive; no legitimate use in a read-only probe
    "navigator.connection",   # not a call, but the same "reach out" family — cheap to keep closed
)


@pytest.mark.parametrize("token", ORIGINATING_TOKENS)
def test_no_source_originates_a_network_call(token: str):
    for name, body in _sources().items():
        assert token not in body, (
            f"{name} contains {token!r}, which ORIGINATES a request rather than observing one. "
            "An extension-initiated call to ESPN carries the user's cookie automatically — that is "
            "§3(c) in an extension costume, and it is a deliberate policy decision with the "
            "operator, never a refactor."
        )


def test_the_probe_really_does_wrap_rather_than_merely_abstain():
    """⚠️ THE TWO-SIDED HALF, and without it clause 3 is satisfied by an EMPTY FILE.

    Every assertion above is a token ABSENCE, and absence is trivially satisfied by a probe that
    does nothing at all — which is also what a silently-broken probe looks like. This clause pins
    that the observe-side machinery is actually present, so "no originating call" means "it
    observes correctly" rather than "it does nothing" (NF1.7(a): a check that could not act is not
    a passing check).
    """
    body = _sources()["main-world-probe.js"]
    for wrapper in ("window.fetch =", "XMLHttpRequest.prototype.open",
                    "XMLHttpRequest.prototype.send", "window.WebSocket ="):
        assert wrapper in body, f"probe does not install the {wrapper!r} observer"
    assert "res.clone()" in body, (
        "the fetch observer must read a CLONE — consuming the page's own response stream would "
        "break the draft room it is observing"
    )

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Clause 4 — the RAW-CAPTURE invariants (added with the capability, not after it)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# The probe originally stored only STRUCTURAL summaries, which is why it could not hold a secret by
# construction. Capturing raw WebSocket frames removes that guarantee, so it has to be replaced by
# an explicit one. The trigger is concrete, not hypothetical: the first real capture showed the room
# fetching `.../teams/14/draftSecurity`, whose response is a draft-join TOKEN — so the draft socket's
# own handshake is a plausible carrier for it, and a capture file is something we hand around.


def test_a_raw_frame_is_only_ever_stored_through_the_redactor():
    """⛔ THE LOAD-BEARING ONE. `rawSample` may be assigned from `redact(...)` and nothing else."""
    body = _sources()["main-world-probe.js"]
    assigns = re.findall(r"rawSample\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)
    assert assigns, "no rawSample assignment found — this clause would pass on nothing"
    for callee in assigns:
        assert callee == "redact", (
            f"rawSample is assigned from {callee!r}, not redact(). A raw frame must never be "
            "stored unredacted — the draft socket may carry the draftSecurity token."
        )


def test_the_redactor_covers_the_shapes_that_actually_appeared():
    """Each pattern is pinned to something MEASURED, not imagined: the SWID GUID shape came out of
    the real capture's `members[].id`, and the token/secret forms from `draftSecurity`."""
    body = _sources()["main-world-probe.js"]
    for needle, why in [
        ("[0-9a-f]{8}-", "SWID GUID shape (seen in the real capture's members[].id)"),
        ("{24,}", "long opaque runs — a token, never a pick field"),
        ("security", "self-labelled secret fields (draftSecurity)"),
    ]:
        assert needle in body, f"redactor does not cover {why}"


def test_the_raw_frame_capture_is_bounded():
    """An unbounded raw capture is a payload capture wearing a different name."""
    body = _sources()["main-world-probe.js"]
    m = re.search(r"RAW_FRAME_LIMIT\s*=\s*(\d+)", body)
    assert m, "no RAW_FRAME_LIMIT declared"
    assert 0 < int(m.group(1)) <= 2000, f"RAW_FRAME_LIMIT={m.group(1)} is not a bound"
    assert "slice(0, RAW_FRAME_LIMIT)" in body, "the limit is declared but never applied"


#: Fields the pool extractor must NEVER carry. These are league-private or bulky; the five identity
#: fields it does keep are ESPN's PUBLIC player universe (identical for every league), which is what
#: makes keeping them proportionate. A pool extractor that grows one of these has quietly become a
#: payload capture.
FORBIDDEN_POOL_FIELDS = ("ownership", "stats", "draftRanksByRankType", "ratings",
                         "notificationSettings")


@pytest.mark.parametrize("field", FORBIDDEN_POOL_FIELDS)
def test_the_pool_extractor_keeps_identity_fields_only(field: str):
    body = _sources()["main-world-probe.js"]
    m = re.search(r"function extractPool\([\s\S]*?\n  \}", body)
    assert m, "extractPool not found — this clause would pass on nothing"
    assert field not in m.group(0), (
        f"extractPool carries {field!r}. It must keep identity fields only "
        "(id / fullName / proTeamId / defaultPositionId / eligibleSlots)."
    )


def test_the_pool_extractor_is_bounded():
    body = _sources()["main-world-probe.js"]
    m = re.search(r"POOL_LIMIT\s*=\s*(\d+)", body)
    assert m, "no POOL_LIMIT declared"
    assert 0 < int(m.group(1)) <= 20000, f"POOL_LIMIT={m.group(1)} is not a bound"


def test_binary_frames_are_DECODED_rather_than_dropped():
    """⭐ HALF ONE of the first capture's actual defect.

    25 frames arrived on the draft socket and NONE were recorded, because the JSON branch `return`ed
    on anything unparseable — so a binary pick protocol was indistinguishable from "no messages"
    (NF1.7(a)). This pins that `decodePrefix` is CALLED, not merely defined: "wired ≠ invoked"
    (NF-C0e) is precisely how a decoder ships and never runs.
    """
    body = _sources()["main-world-probe.js"]
    calls = len(re.findall(r"decodePrefix\s*\(", body)) - len(
        re.findall(r"function\s+decodePrefix\s*\(", body))
    # ⭐ >= 2, and that is a real invariant rather than a test convenience: a socket delivers binary
    # as EITHER an ArrayBuffer or a Blob depending on `binaryType`, so a decoder wired to only one
    # carrier still loses half the frames silently — the same defect in a narrower costume. (The red
    # proof found this: removing just the ArrayBuffer call left a `>= 1` assertion green.)
    assert calls >= 2, (
        f"decodePrefix is called {calls}× — both binary carriers (ArrayBuffer and Blob) must "
        "decode, or frames arriving as the other one are still dropped silently"
    )


def test_an_unreadable_frame_is_COUNTED_rather_than_dropped():
    """⭐ HALF TWO, deliberately a SEPARATE clause (NF-D17: one isolating fixture per clause).

    ⚠️ THE FIRST VERSION OF THIS TEST WAS VACUOUS AND THE RED PROOF CAUGHT IT. It asserted
    `"nonTextFrames" in body`, which stayed GREEN when the branch was disabled to `else if (false)`,
    because the token still occurred on the increment line — the #815 shape ("a break that lands but
    does not move the ASSERTED PREDICATE"), and proof that an `x in src` guard is the weak form. It
    now pins the DISCRIMINATING PREDICATE: the branch must actually test for an unreadable body.
    """
    body = _sources()["main-world-probe.js"]
    assert re.search(r"else if \([^)]*bodyText === null[^)]*\)", body), (
        "no branch discriminates on an unreadable (non-string) body — 'we saw N frames we could "
        "not read' is a finding; silence is not"
    )
    assert re.search(r"nonTextFrames\s*\+=\s*1", body), "unreadable frames are never counted"


def test_the_xhr_observer_handles_every_response_representation():
    """⭐ THE SECOND BLIND SPOT, found by the probe's own error log.

    `responseText` THROWS when the page set `responseType = "json"` — the DOM spec makes it readable
    only for "" and "text". The first deep capture recorded exactly that, meaning every XHR the app
    declared as JSON was silently missed. Same defect as the WebSocket blind spot in another
    costume: a reader that handles one representation reports silence for all the others.

    Pins BOTH branches, because handling only the text one is what shipped and looked fine.
    """
    body = _sources()["main-world-probe.js"]
    assert re.search(r'responseType', body), "the observer never inspects responseType"
    assert re.search(r'rt === "json"', body), (
        "no branch reads a responseType='json' body via `.response` — those calls are still dropped"
    )
    assert re.search(r'rt === ""\s*\|\|\s*rt === "text"', body), (
        "the text branch no longer guards on responseType, so responseText can throw again"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Clause 5 — the HOST ALLOWLIST. A refuted premise, not a tidy-up.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# NF-C0 §3(d) argued the paste flow is safe because a response BODY is "structurally incapable" of
# carrying `espn_s2`. Verified against the LEAGUE endpoint, that is true. A real draft-room capture
# (2026-08-19) REFUTED it for the room as a whole: `registerdisney.go.com/.../guest/{SWID}` returns
# `s2` in its body alongside the user's name, email, DOB and SWID. The credential VALUE escaped only
# because `summarize` truncates strings over 200 chars — a SIZE decision, not a credential guard.
#
# ⇒ "observe everything the page requests" is unsafe, because a draft room requests things that have
# nothing to do with drafting.

#: Hosts observed carrying PII/credential material in a real capture. None may ever be readable.
KNOWN_PII_HOSTS = ("registerdisney.go.com", "fan.api.espn.com", "consent-api.onetrust.com",
                   "log.go.com", "bamgrid.com")


def _allowlist() -> list[str]:
    body = _sources()["main-world-probe.js"]
    m = re.search(r"var BODY_CAPTURE_HOSTS = \[(.*?)\];", body, flags=re.S)
    assert m, "no BODY_CAPTURE_HOSTS declared — every clause below would pass on nothing"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_the_body_allowlist_is_narrow_and_non_empty():
    hosts = _allowlist()
    assert hosts, "empty allowlist — the probe would read nothing, which is not the invariant"
    assert len(hosts) <= 3, f"allowlist has grown to {hosts} — each entry is a host we read bodies from"
    for h in hosts:
        assert "espn.com" in h, f"{h!r} is not an ESPN host"


@pytest.mark.parametrize("host", KNOWN_PII_HOSTS)
def test_hosts_observed_carrying_pii_are_not_readable(host: str):
    """⭐ THE TWO-SIDED HALF. An allowlist that merely EXISTS proves nothing; these are the hosts a
    real capture caught carrying `s2`, email, DOB and SWID, and they must be refused by name."""
    for entry in _allowlist():
        assert host not in entry, f"{host!r} is on the body allowlist — it carries PII"


def test_an_off_allowlist_response_body_is_discarded_before_it_is_read():
    """The allowlist must be applied at the TOP of `recordCall`, before any shaping. Declaring it
    and not consulting it is the 'wired ≠ invoked' class (NF-C0e)."""
    body = _sources()["main-world-probe.js"]
    assert re.search(r"if \(!bodyCaptureAllowed\(url\)\) bodyText = null;", body), (
        "recordCall does not discard off-allowlist bodies — the allowlist is declared but not applied"
    )


def test_the_allowlist_fails_closed_on_an_unparseable_url():
    body = _sources()["main-world-probe.js"]
    m = re.search(r"function bodyCaptureAllowed\(url\) \{[\s\S]*?\n  \}", body)
    assert m, "bodyCaptureAllowed not found"
    assert re.search(r"catch \([^)]*\) \{ return false;", m.group(0)), (
        "bodyCaptureAllowed does not fail CLOSED — an unparseable URL must be refused, not allowed"
    )
    assert "hostname" in m.group(0), (
        "the check is not on hostname — a substring match would let "
        "https://evil.com/lm-api-reads.fantasy.espn.com through"
    )


def test_sensitive_keys_are_omitted_from_a_summarized_body():
    """Defence in depth BEHIND the allowlist: if an allowed host ever starts returning a profile
    block, the value is dropped rather than summarized."""
    body = _sources()["main-world-probe.js"]
    assert "SENSITIVE_KEYS" in body, "no sensitive-key scrub declared"
    for key in ("s2", "swid", "email", "dateOfBirth"):
        assert key in body, f"sensitive-key scrub does not cover {key!r}"
    assert re.search(r"SENSITIVE_KEYS\.test\(k\)", body), (
        "the scrub is declared but never applied inside summarize()"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Clause 6 — FIRST-OBSERVATION-ONLY cannot see a protocol
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# Everything else records content ONCE per URL and then only increments `count`. Right for "does a
# structured source EXIST", wrong for "does the state EVOLVE" — a capture at pick 30 would carry the
# byte-identical join frame and the byte-identical empty `picks[]` as one at pick 0, so capturing
# "at a couple of points" adds nothing but bigger counters.


def test_every_frame_is_pattern_recorded_not_just_the_first():
    body = _sources()["main-world-probe.js"]
    calls = len(re.findall(r"recordFramePattern\s*\(", body)) - len(
        re.findall(r"function\s+recordFramePattern\s*\(", body))
    assert calls >= 1, "recordFramePattern is defined but never CALLED (wired ≠ invoked)"
    # It must sit on the non-JSON path, AFTER the once-only rawSample block, or it inherits the
    # very first-observation-only limit it exists to remove.
    assert re.search(r"entry\.rawSample = redact\(bodyText\);[\s\S]{0,200}?recordFramePattern", body), (
        "recordFramePattern is not called on the per-frame path"
    )


def test_frame_pattern_capture_is_bounded_and_reports_its_overflow():
    """⛔ Unbounded frame capture is a capture of the whole draft. But a SILENT cap re-creates the
    blind spot at the boundary, so the overflow is counted (NF1.7(a))."""
    body = _sources()["main-world-probe.js"]
    m = re.search(r"FRAME_PATTERN_LIMIT\s*=\s*(\d+)", body)
    assert m and 0 < int(m.group(1)) <= 100, "FRAME_PATTERN_LIMIT is missing or not a bound"
    assert "framePatternOverflow" in body, (
        "frames past the cap are dropped silently — an unrecorded frame CLASS is the blind spot "
        "this section exists to remove"
    )


def test_a_stored_frame_example_goes_through_the_redactor():
    body = _sources()["main-world-probe.js"]
    m = re.search(r"function recordFramePattern\([\s\S]*?\n  \}", body)
    assert m, "recordFramePattern not found"
    assert re.search(r"example:\s*redact\(", m.group(0)), (
        "a stored frame example bypasses the redactor"
    )


def test_a_changed_body_is_reshaped_rather_than_frozen():
    """The only way to see `picks[]` fill if the room RE-POLLS instead of pushing over the socket."""
    body = _sources()["main-world-probe.js"]
    assert "shapeLatest" in body, "a re-polled endpoint's newer body is never shaped"
    assert re.search(r"bodyText\.length !== entry\.bytes", body), (
        "the re-shape is not gated on a cheap length change — it would re-parse 1.4 MB every poll"
    )
