"""E9.58d — the signup funnel must have a finish, not just a start.

WHY THIS FILE EXISTS. E9.58c fixed the START of the funnel (`user_signup_started` was missing on
/subscribe and was being lost to the redirect on the surfaces that had it). What came back from
the OAuth round-trip was `user_signed_in` — which is BYTE-IDENTICAL for a brand-new signup and a
returning user. So the one number worth having off this funnel, "of the people who clicked Sign
Up, how many came back with a session", was not computable from the event stream at all.

The only thing that knows the difference is the SURFACE (a Sign Up button vs a Sign In button),
and the surface is on the far side of a cross-origin redirect from the callback — hence the
intent is stashed and consumed exactly like the post-sign-in destination.

⚠️ THE FAILURE DIRECTION IS DELIBERATE. `consumeSignInContext` returns null on anything absent,
malformed, or unrecognised, and the callback then reports intent "unknown" rather than assuming
"signup". A bug in this path can therefore only ever UNDER-count conversions. An analytics
number that silently over-reports its own success metric is much worse than one that misses
some, because nothing downstream will ever question it.
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


# Each OAuth surface and the intent it must declare.
_SURFACES = [
    ("app/subscribe/page.tsx", "signup", "subscribe"),
    ("app/signup/page.tsx", "signup", "signup"),
    ("app/login/page.tsx", "signin", "login"),
]


@pytest.mark.parametrize("rel,intent,surface", _SURFACES)
def test_every_surface_declares_what_the_user_was_trying_to_do(rel: str, intent: str, surface: str):
    code = _code(_FRONTEND / rel)
    call = code[code.index("startGoogleSignIn(") : code.index("startGoogleSignIn(") + 200]
    assert f'intent: "{intent}"' in call, f"{rel} does not declare intent={intent}"
    assert f'surface: "{surface}"' in call, f"{rel} does not declare its surface"


def test_the_callback_emits_a_completion_event_paired_with_the_start():
    """⚠️ RE-ANCHORED TWICE — the PROPERTY is unchanged, its implementation has moved twice.

    G100-C0 moved the completion capture out of this page into `lib/post-signin.ts`, because a
    SECOND self-serve door (email OTP) has to fire the identical event and a hand-copied second
    implementation is how one of them ends up not firing it.

    ⭐ G100-D0-R1 then changed WHAT THE CONDITION IS. The property E9.58d defends is that the
    completion is CONDITIONAL — an event fired on every sign-in makes the conversion rate
    meaningless. E9.58d's condition was the client's stashed intent, which was the only thing a
    client could know and was wrong in both directions (Google federation auto-provisions at
    either door). The condition is now the server's `created` answer. So this asserts the
    conditionality and that the intent still reaches the module — not the specific predicate,
    which `test_g100_d0_r1_signup_authoritative.py` owns.

    ⛔ The old assertion (`'intent === "signup"' in post`) would still PASS today, on the
    deploy-skew fallback branch — i.e. it would keep describing a retired rule while reading as
    a live guarantee. That is why it is replaced rather than left alone.
    """
    cb = _code(_APP / "callback/page.tsx")
    assert "consumeSignInContext()" in cb, "the callback cannot see what the user was trying to do"
    assert "completeSignIn(" in cb, "the callback no longer closes the funnel at all"
    assert "intent:" in cb, "the callback does not pass the intent on"

    post = _code(_FRONTEND / "lib/post-signin.ts")
    assert "user_signup_completed" in post, "the funnel still has no finish"
    assert "intent" in post, "the intent no longer reaches the module that closes the funnel"
    decide = post.split("function reportSignupCompletion(")[1]
    assert "acceptance.created" in decide.split("user_signup_completed")[0], (
        "the completion is no longer conditional on this sign-in having created an account — "
        "firing it on every sign-in would make the conversion rate meaningless"
    )


def test_both_ends_of_the_funnel_carry_surface():
    """Conversion has to break down per entry point, or it cannot tell you WHICH door works."""
    post = _code(_FRONTEND / "lib/post-signin.ts")
    completed = post.split("user_signup_completed")[1][:200]
    assert "surface" in completed
    for rel, _, _ in _SURFACES:
        code = _code(_FRONTEND / rel)
        if "user_signup_started" in code or "user_signin_started" in code:
            assert "surface" in code, f"{rel}'s start event carries no surface"


def test_a_stale_context_cannot_manufacture_a_conversion():
    """An ABANDONED attempt leaves a context behind. If the next, unrelated sign-in picked it up,
    it would report a conversion that did not happen — inflating the metric this exists to
    measure. Single-use, and cleared on every start."""
    lib = _code(_FRONTEND / "lib/cognito.ts")
    consume = lib.split("export function consumeSignInContext")[1].split("\n}")[0]
    assert "removeItem(SIGNIN_CONTEXT_KEY)" in consume, "the context is not single-use"

    start = lib.split("export async function startGoogleSignIn")[1].split("\n}")[0]
    assert "removeItem(SIGNIN_CONTEXT_KEY)" in start, (
        "a start with no context must CLEAR any previous one, not leave it to be picked up"
    )


def test_an_unrecognised_context_under_counts_rather_than_over_counts():
    """The safe direction. Anything unparseable or unexpected must NOT become a 'signup'."""
    lib = _code(_FRONTEND / "lib/cognito.ts")
    consume = lib.split("export function consumeSignInContext")[1].split("\n}")[0]
    assert "return null" in consume
    assert 'parsed?.intent !== "signup"' in consume, "an arbitrary stored value is trusted as an intent"

    cb = _code(_APP / "callback/page.tsx")
    assert 'ctx?.intent ?? "unknown"' in cb, "a missing intent must report unknown, not a default"


def test_the_guard_can_actually_fail():
    lib = _code(_FRONTEND / "lib/cognito.ts")
    assert "SIGNIN_CONTEXT_KEY" in lib
    assert len(lib.split("export function consumeSignInContext")[1].split("\n}")[0]) > 100
