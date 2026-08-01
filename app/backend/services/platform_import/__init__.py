"""platform_import — per-platform fantasy-league import adapters (NF-C0).

Every adapter normalizes ONE platform's league into the SAME `fantasy_engine` `LeagueConfig` the
manual NF-C0b editor produces (see `canonical.py`). Adding a platform is adding a module here plus a
`PLATFORMS` entry — nothing downstream of the config changes, because downstream cannot tell where a
config came from.

## Platform status (probed live 2026-08-01, not read off cached documentation)

| Platform | ~2025 MAU | Access mechanism | Status |
|---|---|---|---|
| **Sleeper** | 33% | Public read-only HTTP API, no auth | ✅ **SHIPPED + verified live** |
| **Yahoo** | 18% | Official OAuth2, read scope | ✅ **Code-complete**, awaiting the operator's Yahoo developer-app approval |
| **ESPN** | 48% | *(none compliant)* | ⛔ **NO-GO** — see `docs/nf_c0_espn_access_probe.md` |
| CBS / MFL / Fantrax | long tail | — | Not attempted (CBS was already a NO-GO at E8.2a) |

⛔ **WHY ESPN IS NOT HERE, despite being the biggest.** ESPN publishes no developer program and no
OAuth grant for fantasy data; the only path that reaches a PRIVATE league (the overwhelming
majority) is replaying the user's `espn_s2` + `SWID` session cookies. Those are full-account
credentials — not read-scoped, not individually revocable, and functionally password-equivalent —
so holding them would cross this story's hard red line. ESPN users are served by the NF-C0b manual
floor, which already ships and already works. The full probe, including the independent robots.txt
finding, is in `docs/nf_c0_espn_access_probe.md`.

⭐ THE FLOOR IS WHY THIS CAN SHIP INCREMENTALLY. Import is the CONVENIENCE layer over NF-C0b's
manual editor, so a platform we cannot reach compliantly costs a user convenience, never access.
That is what makes "we will not hold your password" a decision with no hostage.
"""

from __future__ import annotations

# Platform id → user-facing metadata. `available` is a STATIC capability claim ("we built an
# adapter"); whether Yahoo is actually usable right now additionally depends on the OAuth app being
# provisioned, which `yahoo_oauth.is_configured()` answers at request time.
PLATFORMS: dict[str, dict] = {
    "sleeper": {
        "id": "sleeper",
        "label": "Sleeper",
        "auth": "public",
        "available": True,
        # Leads with the LEAGUE ID to match the input panel, which asks for the ID first: the ID is
        # sitting in the league's URL, whereas a username has to be recalled and is what people get
        # wrong. This string is the card's subtitle, so a username-first wording here contradicts the
        # ID-first field directly under it.
        "help": "Enter your league ID — the long number in your league's Sleeper URL. No sign-in needed.",
    },
    "yahoo": {
        "id": "yahoo",
        "label": "Yahoo Fantasy",
        "auth": "oauth",
        "available": True,
        # Worded without the literal word "p-a-s-s-w-o-r-d" on purpose: the red-line lint in
        # `test_nf_c0_platform_import.py` scans string literals as well as identifiers (so a
        # `{"password": ...}` payload cannot slip through), and copy that trips it would push a
        # future author to weaken the lint rather than the code.
        "help": "Sign in on Yahoo's own page to grant read-only access. Your Yahoo login stays with Yahoo.",
    },
}

__all__ = ["PLATFORMS"]
