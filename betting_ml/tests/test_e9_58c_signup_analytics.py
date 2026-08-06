"""E9.58c — a signup surface must emit an event, and that event must survive the redirect.

WHY THIS FILE EXISTS. E9.58 shipped, a real signup completed in production, and PostHog showed
NOTHING. Two independent defects, and the funnel this story exists to build was unmeasurable
because of them:

  1. `/subscribe` — the surface EVERY padlock in the product points at, and therefore the
     highest-volume signup path — called `startGoogleSignIn` with no `posthog.capture` at all.
     `/signup` had one; the money page did not.

  2. Even where a capture existed it could be LOST. What follows it is
     `window.location.href = <cognito>`, a full-page navigation: posthog-js batches events, and
     a batched event still sitting in the queue when the document is torn down is never sent.
     `send_instantly: true` bypasses the queue.

Defect 2 is the nastier one: it is invisible in code review (the capture is right there on the
line above), intermittent in testing (it depends on whether a flush happened to land first), and
it fails in the direction that looks like "nobody used the feature" rather than like a bug.

⚠️ NOTE THE SHAPE, because it generalises past analytics: any side effect fired immediately
before a full-page navigation needs to be told not to queue. If another beacon, log, or metric
is added to one of these handlers, it inherits this problem.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path("frontend")
_APP = _FRONTEND / "app"

pytestmark = pytest.mark.skipif(not _APP.is_dir(), reason="frontend/ not present")


def _code(path: Path) -> str:
    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


# Every page with a "Continue with Google" button, and the event each one owes.
# `/subscribe` is listed FIRST because it is the one that was missing.
_OAUTH_SURFACES = [
    ("app/subscribe/page.tsx", "user_signup_started"),
    ("app/signup/page.tsx", "user_signup_started"),
    ("app/login/page.tsx", "user_signin_started"),
]


def _handler(rel: str) -> str:
    """The body of the handler that kicks off the OAuth redirect."""
    code = _code(_FRONTEND / rel)
    assert "startGoogleSignIn(" in code, f"{rel} no longer starts a Google sign-in"
    # from the handler declaration through the startGoogleSignIn call
    start = code.rfind("function handle", 0, code.index("startGoogleSignIn("))
    return code[start : code.index("startGoogleSignIn(") + 40]


@pytest.mark.parametrize("rel,event", _OAUTH_SURFACES)
def test_every_oauth_surface_captures_an_event(rel: str, event: str):
    """Defect 1: /subscribe emitted nothing, so the highest-volume path was invisible."""
    body = _handler(rel)
    assert "posthog.capture(" in body, f"{rel} starts an OAuth redirect with no analytics event"
    assert event in body, f"{rel} does not emit {event}"


@pytest.mark.parametrize("rel,event", _OAUTH_SURFACES)
def test_the_event_is_not_left_in_a_queue_the_redirect_destroys(rel: str, event: str):
    """Defect 2: a batched event does not survive `window.location.href`."""
    body = _handler(rel)
    assert "send_instantly" in body, (
        f"{rel} captures an event and then immediately navigates away — posthog-js batches, so "
        "the event dies with the document. Pass { send_instantly: true }."
    )


def test_the_redirect_really_is_a_full_page_navigation():
    """Grounds the rule above. If this ever became a client-side route change, `send_instantly`
    would stop being necessary — and this test is what would tell the next reader that."""
    cognito = _code(_FRONTEND / "lib/cognito.ts")
    body = cognito.split("export async function startGoogleSignIn")[1].split("\n}")[0]
    assert "window.location.href" in body


def test_the_guard_can_actually_fail():
    """Anti-vacuity: `_handler` must return a real slice of source, not an empty string."""
    for rel, _ in _OAUTH_SURFACES:
        body = _handler(rel)
        assert len(body) > 80, f"{rel}: handler slice is too small to be real source"
        assert "startGoogleSignIn(" in body
