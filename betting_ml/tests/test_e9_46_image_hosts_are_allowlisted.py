"""Every image host the app RENDERS must be in the CSP `img-src` allowlist.

🩹 THE BUG THIS CLOSES, AND WHY IT SURVIVED SO LONG.

`static.www.nfl.com` — the host every NFL headshot comes from — was never in `img-src`. The browser
refused every one of them, and there is no server-side signal for that: the API serves a perfectly
good URL (measured 2026-08-08: `200 image/png`), the page renders, nothing logs, no status code
changes. The refusal exists only in a browser console nobody has open.

⭐ AND THE PRODUCT HID IT. `player-page.tsx` renders a headshot with an `onError` → initials
fallback, which is good UX and which makes a CSP block **indistinguishable from "this player has no
photo"**. So the site had a whole class of image silently failing, presenting as a design choice.
It surfaced only when E9.46's home card rendered one WITHOUT a fallback.

⇒ the fallback is not the fix and must not be treated as one. It is now paired with this guard, or
the next missing host is invisible again.

══ WHY THIS READS THE FIXTURES RATHER THAN THE SOURCE ═════════════════════════════════════════════

A grep for image hosts in `frontend/` finds `a.espncdn.com` (the team-logo helper builds that URL in
code) and MISSES `static.www.nfl.com` entirely — the headshot URL is a COLUMN in the published
payload, put there by nflverse's identity table. The host exists in our DATA and never in our code,
which is exactly why a source-derived allowlist would have passed while the images were blocked.

So the check runs over the committed API fixtures — the same bytes the E2E harness serves, captured
from production — and asserts that every host they ask the browser to load is permitted.

Pure/offline (fast gate): reads committed files only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

_REPO = Path(__file__).resolve().parents[2]
_NEXT_CONFIG = _REPO / "frontend/next.config.mjs"
_FIXTURE_DIR = _REPO / "frontend/e2e/fixtures/api"

#: Hosts we serve images from that no fixture happens to contain today. Kept explicit so the guard
#: still covers them — a fixture is a sample, not the contract.
_ALSO_RENDERED = ("a.espncdn.com",)


def _img_src_hosts() -> set[str]:
    """The hosts permitted by the CSP `img-src` directive, parsed from the real config."""
    cfg = _NEXT_CONFIG.read_text()
    m = re.search(r'"img-src ([^"]+)"', cfg)
    assert m, "could not find the img-src directive — this guard would be vacuous"
    hosts = {
        urlparse(tok).netloc
        for tok in m.group(1).split()
        if tok.startswith("http")
    }
    assert hosts, f"img-src parsed to no hosts, so nothing below is being checked: {m.group(1)!r}"
    return hosts


def _fixture_image_hosts() -> dict[str, str]:
    """{host: where it came from} for every image-looking URL in the committed API fixtures."""
    found: dict[str, str] = {}
    url_re = re.compile(r"https://[^\s\"']+")
    for path in sorted(_FIXTURE_DIR.glob("*.json")):
        blob = path.read_text()
        for key in ("headshot", "logo", "image", "photo", "avatar"):
            # Only URLs sitting under an image-ish key — a link to a source page is not an image,
            # and asserting on one would send us chasing hosts the browser never loads.
            for m in re.finditer(rf'"{key}"\s*:\s*"({url_re.pattern})"', blob):
                host = urlparse(m.group(1)).netloc
                found.setdefault(host, f"{path.name}:{key}")
    return found


def test_the_csp_directive_parses():
    """NF1.7 (a): a parser that quietly returned nothing would make the real assertion below
    vacuously true, and this file would read as coverage while checking nothing."""
    hosts = _img_src_hosts()
    assert "a.espncdn.com" in hosts, f"the parse looks wrong — got {hosts}"


def test_the_fixture_scan_actually_finds_image_urls():
    """The other half of the vacuity guard: if the fixtures stop carrying image URLs (a re-capture
    that drops the field, a renamed key), the assertion below passes on an empty set."""
    found = _fixture_image_hosts()
    assert found, (
        "no image URLs found in the committed API fixtures — the allowlist check below would be "
        "asserting over nothing"
    )


@pytest.mark.parametrize("host", sorted(_ALSO_RENDERED))
def test_a_known_rendered_host_is_allowlisted(host):
    assert host in _img_src_hosts(), f"{host} is rendered by the app but blocked by the CSP"


def test_every_image_host_in_the_published_fixtures_is_allowlisted():
    """⭐ THE LOAD-BEARING ONE. RED-PROVEN by removing `static.www.nfl.com` from the directive.

    A host that reaches this list has already shipped in a real payload, so a failure here is not
    hypothetical: it means the browser is refusing an image the product is actively serving, with
    no error anywhere on our side."""
    allowed = _img_src_hosts()
    blocked = {
        host: where for host, where in _fixture_image_hosts().items() if host not in allowed
    }
    assert not blocked, (
        "image host(s) served to the browser but missing from the CSP img-src allowlist in "
        f"frontend/next.config.mjs — these fail SILENTLY in the browser: {blocked}"
    )


def test_the_nfl_headshot_host_is_allowlisted_by_name():
    """Named explicitly as well as caught by the scan above. The fixture is a capture and could be
    re-captured for a player whose headshot is absent, which would quietly drop the only evidence
    for the exact host this guard was written for."""
    assert "static.www.nfl.com" in _img_src_hosts(), (
        "the NFL headshot host is blocked — every player photo in the product fails silently"
    )
