"""E9.58 — a member of the public can create an account without a human in the loop.

WHY THIS FILE EXISTS. E9.56b made the 2026 fantasy projections public, indexable, and topped every
withheld number with a Subscribe button. E9.56c then found that the button led to `/pricing`, a
404, and fixed it to `/subscribe`. What neither story could fix from inside the frontend is that
**`/subscribe` itself ended in `mailto:charlie@credencesports.com`** — as did the nav, both home CTAs,
the About page and the login page. The entire funnel converged on "email the founder and wait."

E9.57 then established, live, that Google OAuth self-serve signup already worked end to end
(never-before-seen Gmail → account → Stripe checkout → `subscriber` group → gate opens). The flow
was real; it was simply reachable only from `/login`, a page a person with no account has no reason
to open. So the defect was never a missing capability — it was a missing wire, and a missing wire
is exactly the class that source inspection can pin and a type-checker cannot.

⛔ THE ONE THING THAT MUST NOT BE "FIXED": there is deliberately no email/password registration.
The Cognito pool has no email auto-verification, so `sign_up` creates an account that can never
confirm itself (`resend_confirmation_code` → "Auto verification not turned on") and that also
cannot reset its password later. A password signup form would manufacture permanently-broken
accounts. `test_signup_does_not_offer_the_dead_end_password_registration` is what stops a future
session from "completing" the page by adding one.

⚠️ EVERY SOURCE ASSERTION STRIPS COMMENTS FIRST — otherwise the explanatory comment written above
each change satisfies the guard with the change deleted (INC-38's "prose cannot satisfy a source
guard", which this repo has shipped once already).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path("frontend")
_APP = _FRONTEND / "app"

pytestmark = pytest.mark.skipif(not _APP.is_dir(), reason="frontend/ not present")


def _code(path: Path) -> str:
    """Source with `//` line comments and `/* */` blocks stripped."""
    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


def _tsx_sources() -> list[tuple[Path, str]]:
    out = []
    for root in (_APP, _FRONTEND / "components"):
        for src in root.rglob("*.tsx"):
            if "node_modules" in src.parts or ".next" in src.parts:
                continue
            out.append((src, _code(src)))
    return out


# ── the route exists and is what everything points at ────────────────────────────────────────────


def test_signup_is_a_real_route():
    assert (_APP / "signup" / "page.tsx").is_file(), (
        "/signup has no page.tsx — every CTA retired onto it is a 404"
    )


def test_the_shared_signup_constant_resolves_to_that_route():
    """`SIGNUP_HREF` is a CONSTANT, so E9.56c's literal-href route guard cannot see it.

    That guard matches `href="/…"` literals only; `href={SIGNUP_HREF}` is skipped entirely. Without
    this assertion, retiring every mailto onto a constant would have moved the whole funnel OUT of
    the one check that exists to catch a dead button — the same shape as the `/pricing` defect,
    one level of indirection up.
    """
    access = _code(_FRONTEND / "lib/access.ts")
    m = re.search(r'export const SIGNUP_HREF\s*=\s*"([^"]+)"', access)
    assert m, "lib/access.ts no longer exports a SIGNUP_HREF literal"
    route = m.group(1).lstrip("/")
    assert (_APP / route / "page.tsx").is_file(), f"SIGNUP_HREF={m.group(1)} has no page.tsx"


# ── the mailto dead-ends are gone, everywhere, in one change ─────────────────────────────────────

_BETA_MAILTO = "mailto:charlie@credencesports.com?subject=Beta%20Access%20Request"


def test_no_signup_affordance_is_a_mailto_any_more():
    """The literal must not reappear in ANY component or page.

    It is allowed to survive in `lib/access.ts` alone, as the named fallback for an environment
    where the Hosted UI is unconfigured — a button that silently does nothing is worse than an
    email address. Anywhere else it is the dead end coming back.
    """
    offenders = sorted(
        str(src.relative_to(_FRONTEND)) for src, code in _tsx_sources() if _BETA_MAILTO in code
    )
    assert not offenders, (
        "a 'Request Access' mailto is back — self-serve signup exists, so this is a dead end:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "rel",
    [
        "components/nav.tsx",
        "app/page.tsx",
        "app/about/page.tsx",
        "app/login/page.tsx",
        "app/subscribe/page.tsx",
    ],
)
def test_every_page_that_carried_the_mailto_now_offers_real_signup(rel: str):
    """Named one-by-one rather than as a set, so a regression names the page it happened on.

    These are precisely the five surfaces E9.56c enumerated as carrying the dead end.
    """
    code = _code(_FRONTEND / rel)
    assert "SIGNUP_HREF" in code or "signupHref" in code or "startGoogleSignIn" in code, (
        f"{rel} lost its self-serve signup affordance"
    )


def test_the_signup_cta_is_reachable_on_a_phone():
    """The logged-out nav block was `hidden sm:flex`, and the hamburger renders only when SIGNED IN.

    So on a phone a logged-out visitor had no sign-in or sign-up affordance in the nav at all —
    which did not matter while accounts were invite-only and matters a great deal now that the
    inbound path is an indexed locked projection, opened on a phone more often than not. This is
    the defect a desktop-only check cannot see, which is why the story mandates verifying both.
    """
    nav = _code(_FRONTEND / "components/nav.tsx")
    block = nav.split("SIGNUP_HREF}>Sign Up")[0][-700:]
    assert "hidden sm:flex" not in block, (
        "the logged-out nav block is hidden below the `sm` breakpoint again — the Sign Up button "
        "is invisible on a phone, and the hamburger that might have held it is signed-in-only"
    )


def test_a_logged_out_visitor_has_a_mobile_menu_at_all():
    """The hamburger was `showSubNav &&` — signed-in only.

    Combined with About/Blog being `hidden sm:block`, a logged-out visitor on a phone could not
    reach them at all, and the public surfaces had to be crammed into the bar itself beside the
    new Sign Up button — which overflowed (the wordmark overlapped "Rankings", "Track Record"
    wrapped onto two lines). The menu has to exist for the signed-out case, and it needs its OWN
    panel: the signed-in one is built from entitlement-shaped `visibleSurfaces`.
    """
    nav = _code(_FRONTEND / "components/nav.tsx")
    assert "{showSubNav && (\n            <button" not in nav, "the hamburger is signed-in-only again"
    assert "{!showSubNav && mobileOpen && (" in nav, "no signed-out mobile menu panel"
    signed_out_panel = nav.split("{!showSubNav && mobileOpen && (")[1].split("{showSubNav && mobileOpen")[0]
    for expected in ('href="/about"', 'href="/blog"', 'href="/login"', "publicNavItems()"):
        assert expected in signed_out_panel, f"the signed-out mobile menu is missing {expected}"


def test_the_inline_public_links_do_not_crowd_the_bar_on_a_phone():
    """The reported symptom, pinned directly.

    `publicNavItems()` is ALSO rendered inline in the top bar for signed-out visitors (NF3.2, so a
    public surface is reachable pre-login). With Sign Up now permanently in the bar, rendering
    three surface links inline at phone width overflows it — which is what the operator saw. The
    inline copy must be `sm`-and-up; the mobile copy lives in the menu, which the test above pins.
    """
    nav = _code(_FRONTEND / "components/nav.tsx")
    inline = nav.split("publicNavItems().map(")[1].split("))}")[0]
    assert "hidden" in inline and "sm:block" in inline, (
        "the inline public links render at phone width again — with the Sign Up button beside "
        "them the bar overflows (wordmark overlaps the first link, labels wrap mid-phrase)"
    )


def test_the_guard_can_actually_fail():
    """Anti-vacuity (NF1.7 (a)): prove the assertions above are capable of rejecting something.

    If `_code` or `_tsx_sources` silently returned nothing, every test in this file would pass
    while checking nothing at all.
    """
    srcs = _tsx_sources()
    assert len(srcs) > 20, "the source sweep found almost nothing — it is not reading the app"
    assert any("startGoogleSignIn" in code for _, code in srcs), "the sweep cannot see real code"
    # The comment-stripping is load-bearing for the mailto test: /signup's own docstring-style
    # comment names the retired mailto, and must NOT be able to trip or satisfy a source guard.
    raw = (_APP / "signup" / "page.tsx").read_text()
    assert "mailto:charlie@credencesports.com" in raw, "fixture assumption changed"
    assert "mailto:charlie@credencesports.com" not in _code(_APP / "signup" / "page.tsx")


# ── the deliberate dead end stays closed ─────────────────────────────────────────────────────────


def test_signup_does_not_offer_the_dead_end_password_registration():
    """Cognito has NO email auto-verify — a self-registered password account can never confirm.

    This is the assertion most likely to be argued with by a future session ("the signup page has
    no password field, that looks unfinished"). It is finished. See lib/access.ts.
    """
    code = _code(_APP / "signup" / "page.tsx")
    assert 'type="password"' not in code, (
        "a password signup form creates accounts that can never verify or reset — see lib/access.ts"
    )
    # `.signUp(` — the Cognito pool method — and not a bare "SignUp(", which the page's own
    # `handleGoogleSignUp()` handler contains and which would make this assertion unsatisfiable.
    assert ".signUp(" not in code, "no direct Cognito SignUp call"
    assert "startGoogleSignIn" in code, "Google is the whole of v1 and must be the CTA"


def test_access_module_records_why_password_signup_is_closed():
    """The reasoning must travel with the code — this is a decision, not an omission."""
    doc = (_FRONTEND / "lib/access.ts").read_text()
    assert "auto-verification" in doc.lower() or "auto verification" in doc.lower()


# ── the funnel actually closes: buying intent survives the round-trip ────────────────────────────


def test_the_oauth_round_trip_preserves_where_the_visitor_was_going():
    """The callback URL is a fixed Cognito allowlist entry, so the destination cannot ride in it.

    Without this, a stranger who clicked Subscribe on a locked projection, signed up, and came back
    was deposited on /dashboard — the buying intent silently discarded one step before checkout,
    which is the exact failure E9.58 exists to remove.
    """
    cognito = _code(_FRONTEND / "lib/cognito.ts")
    assert "POST_SIGNIN_REDIRECT_KEY" in cognito
    assert "export function consumePostSignInRedirect" in cognito

    callback = _code(_APP / "callback/page.tsx")
    assert "consumePostSignInRedirect()" in callback, "the callback ignores the stashed destination"
    assert 'router.replace("/dashboard")' not in callback, "the destination is hard-coded again"


def test_subscribe_returns_the_new_account_to_subscribe():
    """The one destination that must be right, since /subscribe is where every padlock points."""
    code = _code(_APP / "subscribe/page.tsx")
    assert 'startGoogleSignIn("/subscribe")' in code


def test_the_sign_in_wall_carries_the_destination_through():
    guard = _code(_FRONTEND / "components/auth-guard.tsx")
    assert "function loginHref(" in guard
    assert 'router.push("/login")' not in guard, "a bounce still drops the visitor's destination"


# ── the destination is a same-origin path and cannot become an open redirect ─────────────────────
#
# This value arrives from a query string (`/signup?next=…`) and is replayed as a navigation on the
# AUTH CALLBACK — the single worst place in the app to host an open redirect, since it is reached
# with a freshly-minted session. Each rejection clause is asserted SEPARATELY: an `if A or B or C`
# guard whose test only exercises one input is satisfied by whichever clause happens to fire, so
# deleting a different clause leaves the test green (NF-D17). One assertion per clause means one
# deletion is one RED.


@pytest.mark.parametrize(
    "clause, why",
    [
        ('raw.startsWith("/")', "anything not starting with / can be an absolute URL"),
        # NB: written as an index check in the source, NOT a two-slash string literal — `_code()`
        # strips `//` line comments and would eat a literal one, hiding the clause from this test.
        ('raw[1] === "/"', "a protocol-relative path leaves the origin"),
        ('raw.includes("\\\\")', "some browsers normalise a backslash to /, so /\\evil.com escapes"),
    ],
)
def test_the_redirect_sanitiser_rejects_each_escape_shape(clause: str, why: str):
    code = _code(_FRONTEND / "lib/cognito.ts")
    body = code.split("export function sanitizeInternalPath")[1].split("\n}")[0]
    assert clause in body, f"sanitizeInternalPath dropped a clause: {why}"


def test_nothing_navigates_to_a_raw_next_parameter():
    """The sanitiser is only worth having if every read goes through it.

    A `router.push(searchParams.get("next"))` anywhere re-opens the hole while the sanitiser sits
    there looking reassuring.
    """
    for src, code in _tsx_sources():
        for m in re.finditer(r'(router\.(?:push|replace)\()([^\n]*)', code):
            call = m.group(2)
            if 'searchParams.get("next")' in call or "searchParams.get('next')" in call:
                pytest.fail(f"{src.relative_to(_FRONTEND)} navigates to an unsanitised `next`")


# ── terms acceptance is recorded on the path that now creates every public account ────────────────


def test_the_google_path_records_terms_acceptance():
    """Google is now the ONLY self-serve signup route.

    The password path has recorded acceptance since E9.19 (at the set-password step); before
    E9.58 the federated path recorded nothing, which was tolerable while every federated user had
    been invited by hand and is not once anyone can self-register.
    """
    callback = _code(_APP / "callback/page.tsx")
    assert '"/auth/accept-terms"' in callback


@pytest.mark.parametrize("rel", ["app/signup/page.tsx", "app/subscribe/page.tsx"])
def test_the_signup_surfaces_show_the_terms_they_are_accepting(rel: str):
    code = _code(_FRONTEND / rel)
    assert 'href="/terms"' in code and 'href="/privacy"' in code, (
        f"{rel} records acceptance server-side but never shows the user what they accepted"
    )
