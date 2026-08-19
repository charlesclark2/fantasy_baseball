"""NF-C-LDA-1 — the OUTBOUND half of the extension's red line.

`test_nf_c_lda_0_extension_red_line.py` governs what we do TO ESPN (observe, never originate) and
now scopes itself to the ESPN-context scripts. This file governs the other direction — what reaches
US — plus the two properties the overlay is judged on:

  1. ⛔ ONLY NORMALIZED DATA LEAVES. Draft state and player identity; never a session cookie, never
     a request header, never a raw response body, never a raw socket frame.
  2. ⛔ ONE HOST. The only script that can reach the network has no ESPN page context and can reach
     `api.credencesports.com` alone.
  3. ⭐ BREAK DETECTION IS A FEATURE. "We cannot read your draft" must never render the same as
     "nothing has happened yet".

⭐⭐ THE LOAD-BEARING CLAUSES RUN THE REAL JAVASCRIPT, and that is a deliberate correction of how
this extension was guarded before. The NF-C-LDA-0 suite asserts on SOURCE, which is right for "this
file contains no `fetch(`" and wrong for "no credential can leave" — and the repo has already paid
for the difference here: `test_an_off_allowlist_body_is_recorded_as_REFUSED_not_as_unreadable`
asserted the string `bodyNotRead` was present and passed over code that threw a TypeError before it
could run (the assignment referenced `entry` above its own `var`). The source said the right thing;
the behaviour was absent (NF-C4: assert RENDERED output, not source).

⚠️ NODE IS REQUIRED, AND ITS ABSENCE IS A FAILURE RATHER THAN A SKIP. A `pytest.skip` here would be
the vacuous-guard class in its purest form — the credential clauses would report green on a runner
that never executed them (NF1.7(a)). GitHub's `ubuntu-latest` ships Node; if a future runner does
not, the correct outcome is a red build naming the missing tool, not a quiet pass.

⛔ ANCHORED IN ITS OWN CLAUSE (E9.60): nothing here is bolted onto an older story's guard.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXT = REPO / "extension"
SRC_DIR = EXT / "src"
MANIFEST = EXT / "manifest.json"

#: Our API, and the ONLY host anything in this extension may send data to.
API_ORIGIN = "https://api.credencesports.com"

#: The scripts that run on an ESPN tab. Mirrors `ESPN_CONTEXT_SOURCES` in the NF-C-LDA-0 suite; the
#: exhaustiveness of the classification is pinned there, so a new file cannot fall out of both.
ESPN_CONTEXT = ("main-world-probe.js", "content.js", "draft-state.js", "overlay.js")


def _strip_comments(src: str) -> str:
    """Line comments BEFORE block comments (E9.60) — and it is load-bearing here for the same
    reason as in the NF-C-LDA-0 suite: these files DOCUMENT the rule in prose that necessarily
    contains the forbidden tokens, so an unstripped scan would trip on the explanation.

    🪤 `(?<!:)` IS NOT DECORATION. A naive `//[^\n]*` eats the `//` inside every URL LITERAL, so
    `"https://api.credencesports.com"` becomes `"https:` — and the clauses below, which exist
    precisely to check WHICH ORIGIN the worker names, then measured an empty set and reported "the
    background names no host" as a PASS-shaped failure. Caught only because the assertion printed
    the set it found. Same family as the NF-W7 substring scan that could not say "attempt" because
    it banned "temp": a scanner that cannot tell code from the thing it is scanning FOR.
    """
    src = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _src(name: str) -> str:
    return _strip_comments((SRC_DIR / name).read_text())


def _run_node(script: Path) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    assert node, (
        f"node is not on PATH, so {script.name} could not run. This is a FAILURE and not a skip: "
        "these are the clauses that prove no credential leaves the browser, and a skipped "
        "credential check is indistinguishable from a passing one (NF1.7(a))."
    )
    return subprocess.run([node, str(script)], capture_output=True, text=True, timeout=120)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The wire — behavioural
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_no_credential_or_pii_survives_the_wire():
    """Drives the REAL `wire.js` with a state polluted by every credential-shaped thing a live
    capture has actually carried — `espn_s2`, a SWID, the socket's short-integer `draftSecurity`
    token, raw bodies, request headers, PII — and asserts none survives. Includes its own RED
    proof (replace the rebuild with a passthrough; the leak clause must fire)."""
    result = _run_node(EXT / "tools" / "wire_red_proof.mjs")
    assert result.returncode == 0, f"the wire proof failed:\n{result.stdout}\n{result.stderr}"
    # ⚠️ NON-VACUITY: a harness that printed nothing and exited 0 would pass the line above.
    assert "RED PROOF" in result.stdout, "the wire proof did not run its own deliberate break"
    assert result.stdout.count("PASS") >= 9, f"too few wire clauses ran:\n{result.stdout}"


def test_break_detection_distinguishes_broken_from_quiet():
    """⭐ THE STORY'S HEADLINE PROPERTY. Drives the real `draft-state.js` through the states a live
    draft passes through (lobby, live, stalled, disconnected, unidentified team, unreadable) and
    asserts each gets a distinguishable verdict — with a RED proof that deleting the staleness
    check makes a stalled read report healthy again."""
    result = _run_node(EXT / "tools" / "state_red_proof.mjs")
    assert result.returncode == 0, f"break detection failed:\n{result.stdout}\n{result.stderr}"
    assert "RED PROOF" in result.stdout, "the break-detection proof ran no deliberate break"
    assert result.stdout.count("PASS") >= 10, f"too few clauses ran:\n{result.stdout}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. One host, one network file
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_only_the_background_worker_can_reach_the_network():
    """The context split IS the guarantee. An ESPN-context script that could `fetch` would have the
    user's `espn_s2` attached for it by the browser — §3(c) in an extension costume — so the code
    that can see an ESPN page must not be able to make a request at all."""
    manifest = json.loads(MANIFEST.read_text())
    worker = (manifest.get("background") or {}).get("service_worker")
    assert worker == "src/background.js", f"unexpected service worker: {worker!r}"
    for name in ESPN_CONTEXT:
        body = _src(name)
        for token in ("fetch(", "new WebSocket(", "new XMLHttpRequest(", "sendBeacon", "EventSource("):
            assert token not in body, (
                f"{name} contains {token!r}. It runs on an ESPN tab, so a request it makes carries "
                "the user's ESPN session automatically."
            )


#: Origins the worker may MENTION. Only the first is a destination; the other two exist solely in
#: the INBOUND `sender.origin` check that decides whose token handoff to trust. Distinguishing
#: "names" from "sends to" is the whole point of this clause — an earlier cut asserted the worker
#: mentioned exactly one origin and failed on the sender check, which would have pushed a future
#: editor toward loosening the origin check rather than tightening the destination.
MENTIONABLE_ORIGINS = {
    API_ORIGIN,
    "https://credencesports.com",
    "https://www.credencesports.com",
}


def test_the_background_reaches_exactly_one_host():
    body = _src("background.js")
    mentioned = set(re.findall(r'"(https?://[^"]+)"', body))
    assert mentioned, "the worker names no origin at all — the clause below would be vacuous"
    unexpected = mentioned - MENTIONABLE_ORIGINS
    assert not unexpected, (
        f"the background worker names {sorted(unexpected)}, which is neither our API nor our own "
        "site. A second destination — configurable or not — is an exfiltration path with a nice name."
    )
    # ⭐ THE DESTINATION CLAUSE. Every `fetch` must be built from the API constant; a literal URL
    # or a variable target would slip past the mention check above.
    targets = re.findall(r"fetch\(\s*([^,\)]+)", body)
    assert targets, "no fetch at all — the destination clause would pass on nothing"
    for t in targets:
        assert t.strip().startswith("API_ORIGIN"), (
            f"a fetch target is built from {t.strip()!r} rather than from API_ORIGIN"
        )
    # …and our SITE origins may appear only in the inbound sender check, never as a destination.
    for site in MENTIONABLE_ORIGINS - {API_ORIGIN}:
        for line in body.splitlines():
            if site in line:
                assert "origin" in line, (
                    f"{site!r} appears outside the sender-origin check: {line.strip()!r}"
                )
    assert "espn" not in body.lower(), (
        "the background worker references ESPN. It has no ESPN host permission and must never "
        "acquire a reason to want one."
    )
    manifest = json.loads(MANIFEST.read_text())
    espn_matches = [
        m for cs in manifest["content_scripts"] for m in cs["matches"] if "espn.com" in m
    ]
    assert espn_matches, "no ESPN content script — the separation claim would be vacuous"
    for entry in manifest["content_scripts"]:
        if any("espn.com" in m for m in entry["matches"]):
            assert "src/background.js" not in entry["js"], (
                "the background worker is injected into an ESPN page — the whole context split is "
                "undone by that one line"
            )


def test_the_api_origin_is_a_constant_and_not_configurable():
    """A settable endpoint turns the one-host rule into a preference."""
    body = _src("background.js")
    assert re.search(r'var API_ORIGIN = "https://api\.credencesports\.com";', body), (
        "API_ORIGIN is not a literal constant"
    )
    for token in ("chrome.storage.local.get", "API_ORIGIN =", "options_page", "options_ui"):
        if token == "API_ORIGIN =":
            assert body.count(token) == 1, "API_ORIGIN is assigned more than once"
        else:
            assert token not in body, f"background.js reads {token!r} — the endpoint is settable"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The session token
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_credence_token_never_enters_an_espn_context():
    """Our own bearer token is fine on our own origin and in the worker. It must never be readable
    by anything running on an ESPN page, because a script there sits in a document we do not
    control."""
    for name in ESPN_CONTEXT:
        body = _src(name)
        for token in ("credence_access_token", "accessToken", "Authorization", "Bearer",
                      "chrome.storage", "localStorage"):
            assert token not in body, (
                f"{name} references {token!r} — an ESPN-context script must never see our session"
            )


def test_the_token_handoff_is_origin_checked_and_scoped_to_our_own_site():
    """⛔ `sender.origin` IS SET BY CHROME, NOT BY THE PAGE. Without this check any site the user
    visits could hand the worker a token for it to attach to our API calls."""
    manifest = json.loads(MANIFEST.read_text())
    auth = [cs for cs in manifest["content_scripts"] if "src/credence-auth.js" in cs["js"]]
    assert len(auth) == 1, "credence-auth.js is not registered exactly once"
    for match in auth[0]["matches"]:
        assert re.match(r"^https://(www\.)?credencesports\.com/\*$", match), (
            f"the auth content script runs on {match!r} — it may run only on our own origin"
        )
    assert "espn" not in json.dumps(auth[0]).lower(), "the auth script is matched against ESPN"

    body = _src("background.js")
    assert "sender.origin" in body, "the token handoff does not check the sender's origin"
    assert re.search(r'origin !== "https://credencesports\.com"', body), (
        "the origin check does not name our apex domain"
    )
    assert "chrome.storage.session" in body and "chrome.storage.local" not in body, (
        "the token is persisted to disk — `chrome.storage.session` is in-memory and is what a "
        "draft assistant should hold a bearer token in"
    )


def test_the_auth_script_only_reads_a_token_and_never_writes_one():
    """It is a one-way handoff: read our own session, hand it to the worker. Nothing else."""
    body = _src("credence-auth.js")
    assert "localStorage.setItem" not in body and "localStorage.removeItem" not in body, (
        "the auth script MUTATES our site's session storage — it may only read"
    )
    assert "fetch(" not in body and "XMLHttpRequest" not in body, (
        "the auth script originates a request"
    )
    assert "espn" not in body.lower(), "the auth script references ESPN"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The overlay renders no advice it cannot attach to a pick
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_overlay_never_builds_dom_from_a_string():
    """Player, team and league names all come from ESPN's payload — strings other people chose. On
    a page we do not control, `innerHTML` would let a league named `<img onerror=…>` run script
    inside our own panel."""
    for name in ("overlay.js", "content.js"):
        body = _src(name)
        for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            assert token not in body, f"{name} builds DOM from a string via {token!r}"


def test_a_blocked_read_shows_no_recommendations():
    """A stale 'best available' list is worse than none: it is wrong in exactly the way the user
    cannot check. The overlay must gate the advice on the verdict, not merely colour it."""
    body = _src("overlay.js")
    assert re.search(r'if \(view\.verdict\.level !== "blocked"\) \{', body), (
        "the overlay does not gate its recommendations on the read verdict"
    )


def test_the_overlay_states_the_pick_it_is_reasoning_about():
    """⭐ The pick echo — the one line that makes a frozen read falsifiable by the person reading
    it, by comparison against ESPN's own pick counter."""
    body = _src("overlay.js")
    assert "Reasoning about pick" in body, "the overlay does not name the pick it reasoned about"
    assert "No pick number read yet" in body, (
        "the overlay has no wording for 'we could not read a pick number' — it would render a "
        "blank where a number belongs, which reads as a draft that has not started"
    )


def test_the_overlay_carries_the_honest_framing():
    """No win-rate or edge claim on a user-facing surface (`best_alpha = 0`)."""
    # ⚠️ STRIPPED, because this file's OWN prose says "makes no win-rate claim" — a banned-token
    # scan over comments trips on the sentence explaining the ban (INC-38, facing both ways).
    body = _src("overlay.js")
    assert "Not betting advice" in body, "the overlay makes no honest-framing statement"
    for banned in ("win rate", "win-rate", "guaranteed", "edge over the market", "beat the book"):
        assert banned.lower() not in body.lower(), f"the overlay claims {banned!r}"
