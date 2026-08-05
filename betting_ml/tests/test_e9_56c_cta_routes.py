"""E9.56c — every internal link a user can click must resolve to a route that exists.

WHY THIS FILE EXISTS. E9.56 and E9.56b shipped the entire conversion path off the locked fantasy
view pointing at **`/pricing`** — the `LockChip` on every withheld cell (hundreds per page), both
"Subscribe to unlock" buttons, the two "…included with a subscription" footers, and the backend's
own `upgrade.ctaHref`. There has never been a `frontend/app/pricing/` directory. Verified against
production: `/pricing` → 404, `/subscribe` → 200. The login page's only "I have no account yet"
button had the same defect independently (`/request-access` → 404).

Nothing in the toolchain could see it:
  • `next build` resolves `<Link>` targets it can analyse statically — every one of these is a plain
    `<a href>`, which it does not check at all;
  • `tsc` type-checks a string as a string;
  • the E9.56b guards asserted the CTA was PRESENT and that it carried the right copy — never that
    it went anywhere. A link's target is exactly the part that source inspection skips unless it is
    asked, which is the lesson: a guard that reads a value back is not a guard on where it points.

So the general invariant is pinned here rather than the two specific URLs: every literal internal
`href` in the app resolves to a real `page.tsx` or to a declared redirect. That would have gone RED
on both defects the day they were written, and goes RED on the next one.

⚠️ EVERY SOURCE ASSERTION STRIPS COMMENTS FIRST — otherwise the explanatory comment written above
each fix satisfies the guard on source with the fix deleted (INC-38's "prose cannot satisfy a source
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


# ── the route table, derived from the filesystem ─────────────────────────────────────────────────


def _static_routes() -> set[str]:
    """Every non-dynamic route that has a `page.tsx`, as a URL path."""
    out = set()
    for page in _APP.rglob("page.tsx"):
        rel = page.relative_to(_APP).parent
        parts = [p for p in rel.parts if not (p.startswith("(") and p.endswith(")"))]
        if any(p.startswith("[") for p in parts):
            continue  # dynamic — matched separately
        out.add("/" + "/".join(parts) if parts else "/")
    return out


def _dynamic_route_patterns() -> list[re.Pattern]:
    """`/fantasy/player/[playerId]` → a regex matching `/fantasy/player/<anything>`."""
    pats = []
    for page in _APP.rglob("page.tsx"):
        rel = page.relative_to(_APP).parent
        parts = [p for p in rel.parts if not (p.startswith("(") and p.endswith(")"))]
        if not any(p.startswith("[") for p in parts):
            continue
        pats.append(
            re.compile("^/" + "/".join(r"[^/]+" if p.startswith("[") else re.escape(p) for p in parts) + "$")
        )
    return pats


def _declared_redirects() -> set[str]:
    """`source:` values from next.config.mjs's `redirects()` — a redirect is a real destination."""
    cfg = _code(_FRONTEND / "next.config.mjs")
    block = re.search(r"async redirects\(\)\s*\{(.*?)\n  \},", cfg, flags=re.S)
    return set(re.findall(r'source:\s*"([^"]+)"', block.group(1))) if block else set()


# Non-page targets that are legitimately not `page.tsx`: API route handlers and static assets.
_NON_PAGE_PREFIXES = ("/api/", "/ingest/", "/brand/", "/_next/")
_STATIC_SUFFIXES = (".svg", ".png", ".jpg", ".ico", ".xml", ".txt", ".json", ".webmanifest")


def _internal_hrefs() -> list[tuple[Path, str]]:
    """Every literal internal href/Link target in app + components, with its source file."""
    found: list[tuple[Path, str]] = []
    for root in (_APP, _FRONTEND / "components"):
        for src in root.rglob("*.tsx"):
            if "node_modules" in src.parts or ".next" in src.parts:
                continue
            code = _code(src)
            for m in re.finditer(r'href=(?:"(/[^"{}]*)"|\{"(/[^"{}]*)"\})', code):
                href = m.group(1) or m.group(2)
                path = href.split("?")[0].split("#")[0].rstrip("/") or "/"
                if path.startswith(_NON_PAGE_PREFIXES) or path.endswith(_STATIC_SUFFIXES):
                    continue
                found.append((src, path))
    return found


def test_every_internal_link_resolves_to_a_real_route():
    """THE guard. RED on `/pricing` and on `/request-access` as originally written."""
    static, dynamic, redirects = _static_routes(), _dynamic_route_patterns(), _declared_redirects()
    broken = sorted(
        {
            f"{src.relative_to(_FRONTEND)} → {path}"
            for src, path in _internal_hrefs()
            if path not in static
            and path not in redirects
            and not any(p.match(path) for p in dynamic)
        }
    )
    assert not broken, (
        "internal link(s) point at a route with no page.tsx and no declared redirect — "
        "this is a 404 behind a button:\n  " + "\n  ".join(broken)
    )


def test_the_guard_can_actually_fail():
    """Anti-vacuity: prove the route table would REJECT the URL that shipped.

    Without this, a bug in `_static_routes` that returned everything would leave the test above
    passing forever while checking nothing (NF1.7 (a) — a check that cannot fail is not a check).
    """
    assert "/pricing" not in _static_routes(), "no page.tsx at /pricing — the whole point"
    assert "/request-access" not in _static_routes()
    assert "/subscribe" in _static_routes(), "the route we redirect TO must be real"


# ── the specific defects, pinned ─────────────────────────────────────────────────────────────────


def test_subscribe_href_is_a_constant_and_no_component_hardcodes_pricing():
    shared = _code(_FRONTEND / "components/fantasy/shared.tsx")
    assert 'export const SUBSCRIBE_HREF = "/subscribe"' in shared

    for rel in ("components/fantasy/shared.tsx",
                "components/fantasy/projections-table.tsx",
                "components/fantasy/rankings-board.tsx"):
        assert '"/pricing"' not in _code(_FRONTEND / rel), f"{rel} still links at /pricing"


def test_the_server_cta_target_is_allowlisted_not_trusted():
    """NF-C0 deploy skew, on a LINK TARGET.

    The API Lambda ships only via a manual `deploy.sh`, so a frontend deployed today can be talking
    to a backend still sending the old `/pricing`. Rendering `upgrade.ctaHref` verbatim is what made
    a server value into a client-side 404 in the first place.
    """
    shared = _code(_FRONTEND / "components/fantasy/shared.tsx")
    assert "resolveUpgradeHref" in shared
    assert "KNOWN_CTA_ROUTES.has(href)" in shared, "must allowlist, not merely default"
    assert 'href={upgrade?.ctaHref ?? "/pricing"}' not in shared


def test_backend_cta_target_agrees_with_the_frontend_allowlist():
    """Cross-language pin: the Python constant must be a route the TS allowlist accepts.

    These two live in different languages, different deploys and different test suites, and the
    only thing that ties them together is that one is rendered as the other's href.
    """
    env = Path("app/backend/services/entitlement.py")
    if not env.exists():
        pytest.skip("backend not present")
    cta = re.search(r'"ctaHref":\s*"([^"]+)"', env.read_text())
    assert cta, "the upgrade envelope no longer carries a ctaHref"
    assert cta.group(1) in _static_routes(), f"backend ctaHref {cta.group(1)!r} is not a real route"


def test_login_offers_a_working_no_account_path():
    login = _code(_APP / "login/page.tsx")
    assert "/request-access" not in login, "that route does not exist"
    assert "REQUEST_ACCESS_MAILTO" in login


def test_subscribe_signed_out_is_not_a_dead_end():
    """A logged-out visitor must be able to see what they'd buy AND get an account from here."""
    page = _code(_APP / "subscribe/page.tsx")
    assert "REQUEST_ACCESS_MAILTO" in page, "no way to obtain an account"
    signed_out = page.split("signedIn &&")[0]
    assert "PerkList" in signed_out, "perks were rendered only inside the signed-in branch"


def test_the_paid_product_mentions_fantasy():
    """Locked fantasy pages are now the largest inbound path to this page."""
    perks = _code(_APP / "subscribe/page.tsx").split("]")[0]
    assert "fantasy" in perks.lower()


# ── the locked cells that rendered NaN / an honest-absence dash ───────────────────────────────────


def test_no_locked_cell_renders_a_bare_model_value():
    """Rank, tier, positional rank and `vs ADP` are all derived from stripped fields.

    `vs ADP` is the one the operator SAW: it is `theRoomsRank - ourRank`, and `ourRank` is absent on
    a locked row, so it evaluated `number - undefined` and rendered the literal string "NaN" in
    every row of the free board.
    """
    board = _code(_FRONTEND / "components/fantasy/rankings-board.tsx")
    assert "{p.locked ? <LockChip title=\"Subscribe to unlock our rank\" /> : rank}" in board
    assert 'ref != null && Number.isFinite(rank) ? ref - rank : null' in board, "NaN guard gone"

    # Each locked branch must be inside its own cell, so one fix cannot be mistaken for four.
    assert board.count("p.locked ? (") + board.count("p.locked ?") >= 4


def test_locked_confidence_and_range_basis_do_not_read_as_absent():
    """An em-dash here means "no value exists" — a meaning we use deliberately for K/DST.

    Rendering a WITHHELD value the same way sells nothing and tells the user the wrong thing.
    """
    proj = _code(_FRONTEND / "components/fantasy/projections-table.tsx")
    conf = proj.split("ConfidenceBadge conf=")[0][-400:]
    assert "p.locked ?" in conf and "LockChip" in conf


def test_no_csv_export_on_a_locked_board():
    """Every exportable column is withheld; the file would be names, ADP, and a NaN column."""
    board = _code(_FRONTEND / "components/fantasy/rankings-board.tsx")
    assert "{!boardLocked && (" in board
    assert board.index("{!boardLocked && (") < board.index("Export CSV")
