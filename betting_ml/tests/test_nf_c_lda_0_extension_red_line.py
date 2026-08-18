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
