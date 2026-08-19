"""client.py — the authed PFF API client (NF-W9-0).

Modelled on `scripts/utils/fangraphs_client.py`, the repo's sanctioned authed-fetch pattern.
PFF is a PAID subscription behind login, and (like FanGraphs) fronted by Cloudflare — so this
client NEVER tries to bypass auth. It takes a credential the OPERATOR captured from their own
logged-in browser session and replays it.

THREE TRANSPORTS, because the credential shape decides which one can work:

  • `direct`       — curl_cffi with a Chrome TLS fingerprint, replaying the operator's COOKIE
                     through a **cookie-persisting session**. See the Clerk note below: the
                     session is load-bearing, not a convenience.
  • `flaresolverr` — the FanGraphs escape hatch. FlareSolverr's headless browser performs the
                     request from its OWN egress IP holding live Cloudflare clearance, and we
                     hand it the session cookies. Use when `direct` returns a challenge.
  • `sample`       — read an operator-CAPTURED response off disk. This is what makes the probe
                     developable and testable without a credential at all, and it is a first-
                     class transport, not a mock: the SAME parsing/guard/resolution code runs.

⭐ AUTH IS VERIFIED BY CAPABILITY, NEVER BY REACHABILITY. `verify_auth()` does not check that
PFF is up or that a status code is 200 — it PULLS A GAMES LIST AND COUNTS ROWS, and a zero-row
answer is a FAILURE. This is the FanGraphs cf-clearance lesson and the repo's broader rule that
a check whose failure state is indistinguishable from its healthy state has not been verified:
a Cloudflare interstitial, an expired token and a logged-out session all return perfectly
cheerful HTML, and only "did we get DATA?" separates them from success.

⛔ A FAILURE IS NEVER SWALLOWED INTO AN EMPTY LIST. Every failure raises a typed error naming
the cause it could distinguish (`PFFAuthError` vs `PFFChallengeError` vs `PFFClientError`), so
an outage can never be mistaken for a quiet day — the E5.10 `lakehouse_query`-returns-`[]`
class, which cost that story a two-round-trip diagnosis it should not have needed.

⭐ HOW PFF AUTH ACTUALLY WORKS (measured live, 2026-08-18 — and it is why a naive replay fails):
PFF uses **Clerk**. There is **no separate bearer token to copy** — the `__session` cookie *is*
the JWT, and it is minted with a **60-SECOND lifetime**. A cookie captured from DevTools is
therefore essentially always expired by the time it is pasted anywhere.

An expired `__session` does NOT return 401. `premium.pff.com` answers **HTTP 307** to
`clerk.pff.com/v1/client/handshake?…&__clerk_hs_reason=se` ("session expired"). The handshake
mints a fresh session from the long-lived `__refresh_*` cookie, sets `__clerk_handshake`, and
redirects back to the original URL.

⇒ **A STATELESS `Cookie:` HEADER PER REQUEST CANNOT AUTHENTICATE.** It never carries the
handshake cookie back, so it loops the redirect until curl aborts with "maximum redirects
followed" — which looks like a network fault and is really an auth flow. The cure is a
**persistent session that follows redirects and keeps cookies**, which completes the handshake
exactly the way the browser does. Verified live: 307-loop → HTTP 200 + real JSON.

PFF also fronts `premium.pff.com` with **DataDome** (not Cloudflare; `clerk.pff.com` is behind
Cloudflare). `_looks_like_challenge` matches both.

CONFIGURATION (all operator-supplied; nothing is committed):
  PFF_COOKIE       — ⭐ THE credential. The whole `cookie:` header from a logged-in request.
  PFF_AUTH_TOKEN   — optional; sent as `Authorization: Bearer …`. PFF does not appear to issue
                     one to the browser, so the cookie is the practical credential.
  PFF_API_BASE     — default https://premium.pff.com
  PFF_TRANSPORT    — direct | flaresolverr | sample   (default: direct)
  PFF_SAMPLE_DIR   — directory of operator-captured JSON, for the `sample` transport
  FLARESOLVERR_URL — reused from the FanGraphs setup
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from .guards import assert_endpoint_allowed

log = logging.getLogger("pff.client")

DEFAULT_API_BASE = "https://premium.pff.com"
_MAX_RETRIES = 3
_RETRY_DELAYS = (2, 4, 8)
_TIMEOUT_S = 60
_FLARESOLVERR_MAX_TIMEOUT_MS = 60000
# Cookies are seeded on the parent domain so they travel to `clerk.pff.com` during the handshake
# as well as to `premium.pff.com` — the refresh cookie lives on the parent and the handshake
# cannot mint a session without it.
_COOKIE_DOMAIN = ".pff.com"


class PFFClientError(RuntimeError):
    """Any PFF fetch failure. Never swallowed into an empty result."""


class PFFAuthError(PFFClientError):
    """The credential is missing, expired or rejected (401/403 with a real response)."""


class PFFChallengeError(PFFClientError):
    """A bot-protection challenge answered instead of the API — retry via `flaresolverr`."""


class PFFNotFoundError(PFFClientError):
    """The endpoint does not exist for this game/league (PFF answers 404).

    Its own type because it is **not retryable and not an error condition** during facet
    DISCOVERY — a 404 is the expected answer for a facet PFF does not publish, and retrying it
    three times triples our request count against a paid third-party API for no information.
    """


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


class PFFClient:
    """Fetch PFF API JSON with an operator-supplied credential.

    Args:
        token / cookie: the credential; default to `PFF_AUTH_TOKEN` / `PFF_COOKIE`.
        transport: `direct` | `flaresolverr` | `sample`.
        sample_dir: for `sample`, the directory of captured responses.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        cookie: str | None = None,
        api_base: str | None = None,
        transport: str | None = None,
        sample_dir: str | Path | None = None,
        flaresolverr_url: str | None = None,
    ) -> None:
        self.token = token if token is not None else _env("PFF_AUTH_TOKEN")
        self.cookie = cookie if cookie is not None else _env("PFF_COOKIE")
        self.api_base = (api_base or _env("PFF_API_BASE", DEFAULT_API_BASE)).rstrip("/")
        self.transport = (transport or _env("PFF_TRANSPORT", "direct")).lower()
        self.sample_dir = Path(sample_dir or _env("PFF_SAMPLE_DIR") or ".")
        self.flaresolverr_url = flaresolverr_url or _env("FLARESOLVERR_URL")
        self._sess = None
        if self.transport not in ("direct", "flaresolverr", "sample"):
            raise PFFClientError(
                f"Unknown PFF_TRANSPORT {self.transport!r} (direct|flaresolverr|sample)"
            )

    # ── credential plumbing ────────────────────────────────────────────────────────────────
    @property
    def has_credential(self) -> bool:
        return bool(self.token or self.cookie)

    def _headers(self, *, include_cookie: bool = True) -> dict[str, str]:
        """Request headers.

        ⚠️ `include_cookie=False` for the SESSION path. PFF's jar is ~7 KB, so seeding the
        session cookie jar AND setting an explicit `Cookie:` header sends it TWICE and the edge
        answers **HTTP 431 (Request Header Fields Too Large) with an EMPTY body** — which
        surfaces as "unparseable JSON" and looks nothing like the header-size problem it is.
        The jar owns the cookie on that path; the header form is only for the stateless
        transports.
        """
        h = {
            "Accept": "application/json",
            "Referer": f"{self.api_base}/",
        }
        if self.token:
            # Accept a token pasted either bare or already prefixed.
            h["Authorization"] = self.token if self.token.lower().startswith("bearer ") \
                else f"Bearer {self.token}"
        if include_cookie and self.cookie:
            h["Cookie"] = self.cookie
        return h

    def _require_credential(self, path: str) -> None:
        if not self.has_credential:
            raise PFFAuthError(
                f"No PFF credential configured for {path!r}. PFF is a paid subscription behind "
                "login — set PFF_AUTH_TOKEN (and/or PFF_COOKIE) from the operator's logged-in "
                "session, or use PFF_TRANSPORT=sample with PFF_SAMPLE_DIR to run against a "
                "captured response. This client never attempts to bypass authentication."
            )

    # ── the export path: the SAME endpoint plus `export=true`, returning CSV ───────────────
    def get_export(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """GET `path` with `export=true` and parse the CSV rows.

        ⭐ THIS IS THE FULL FIELD SET, AND IT IS ONE PARAMETER AWAY FROM THE REDUCED ONE.
        `/api/v1/facet/passing/summary?league=nfl&season=2025&week=1,…,18` returns 19 basic JSON
        fields; the identical URL plus `&export=true` returns a 44-column CSV carrying every
        field the JSON reports in its `restricted` array — `avg_depth_of_target`, `dropbacks`,
        `passing_snaps`, `epa`, `btt_rate`, and the grades. NF-W9-0 spent a whole pass concluding
        the account was paywalled out of those fields; it was one query parameter.

        The RAW-STATS-ONLY guard matters MORE here, not less: the export genuinely contains PFF's
        grade columns, so this is the first path on which the strip does real work.
        """
        payload = self.get(path, {**(params or {}), "export": "true"}, expect="csv")
        return parse_csv(payload)

    # ── the one fetch entry point ──────────────────────────────────────────────────────────
    def get(self, path: str, params: dict[str, Any] | None = None, *, expect: str = "json") -> Any:
        """GET a PFF API path and return parsed JSON. Raises on ANY failure.

        `path` is guard-checked FIRST: a model-output endpoint is refused before a credential
        is even looked at, so the refusal is unconditional rather than a happy accident of not
        being logged in.
        """
        assert_endpoint_allowed(path)
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if self.transport == "sample":
            return self._get_sample(path, params)
        self._require_credential(path)
        if self.transport == "flaresolverr":
            return self._get_flaresolverr(path, params, expect=expect)
        return self._get_direct(path, params, expect=expect)

    def _url(self, path: str, params: dict) -> str:
        url = path if path.startswith("http") else f"{self.api_base}/{path.lstrip('/')}"
        return f"{url}?{urlencode(params)}" if params else url

    # ── transports ─────────────────────────────────────────────────────────────────────────
    def _session(self):
        """A persistent Chrome-impersonating session seeded with the operator's cookies.

        ⭐ THE SESSION IS LOAD-BEARING. PFF's Clerk `__session` JWT lives 60 seconds, so a
        captured cookie is always stale; the API answers 307 → Clerk handshake → back. Only a
        session that PERSISTS cookies across that redirect completes the handshake. A per-request
        `Cookie:` header loops until curl gives up with "maximum redirects followed", which reads
        as a network fault and is really the auth flow — this cost NF-W9-0 its first live run.
        """
        if self._sess is not None:
            return self._sess
        from curl_cffi import requests

        s = requests.Session(impersonate="chrome")
        for name, value in _parse_cookie_header(self.cookie):
            try:
                s.cookies.set(name, value, domain=_COOKIE_DOMAIN)
            except Exception:  # noqa: BLE001 — a malformed pair must not sink the whole jar
                log.debug("skipped un-settable cookie %r", name)
        # ⛔ include_cookie=False — the jar already carries it; both would be a 431.
        s.headers.update(self._headers(include_cookie=False))
        self._sess = s
        return s

    def _get_direct(self, path: str, params: dict, *, expect: str = "json") -> Any:
        url = self._url(path, params)
        last: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                # allow_redirects=True is REQUIRED: it is how the Clerk handshake completes.
                r = self._session().get(url, timeout=_TIMEOUT_S, allow_redirects=True)
                return _parse_response(url, r.status_code, r.text, expect=expect)
            except (PFFAuthError, PFFChallengeError, PFFNotFoundError):
                # None is retryable: a challenge re-answers identically, an auth failure needs a
                # new credential, and a 404 is a fact about the endpoint.
                raise
            except Exception as exc:  # noqa: BLE001
                last = exc
                log.warning("PFF direct attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAYS[attempt - 1])
        raise PFFClientError(f"All {_MAX_RETRIES} direct attempts failed for {url}") from last

    def _get_flaresolverr(self, path: str, params: dict, *, expect: str = "json") -> Any:
        from curl_cffi import requests

        if not self.flaresolverr_url:
            raise PFFClientError(
                "PFF_TRANSPORT=flaresolverr but FLARESOLVERR_URL is unset (e.g. "
                "http://localhost:8191/v1). See scripts/utils/fangraphs_client.py."
            )
        url = self._url(path, params)
        # FlareSolverr's browser cannot carry an Authorization header, so a cookie credential is
        # REQUIRED on this transport. Saying so plainly beats a puzzling logged-out 200.
        if not self.cookie:
            raise PFFAuthError(
                "The flaresolverr transport can only replay a COOKIE credential (its headless "
                "browser cannot send an Authorization header). Set PFF_COOKIE, or use "
                "PFF_TRANSPORT=direct with PFF_AUTH_TOKEN."
            )
        cookies = _cookie_header_to_list(self.cookie, domain=urlsplit(self.api_base).hostname)
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": _FLARESOLVERR_MAX_TIMEOUT_MS,
            "cookies": cookies,
        }
        r = requests.post(self.flaresolverr_url, json=payload, timeout=_TIMEOUT_S * 3)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            raise PFFClientError(f"FlareSolverr did not solve {url}: {data.get('message')}")
        sol = data.get("solution", {}) or {}
        return _parse_response(url, int(sol.get("status") or 0), sol.get("response", ""),
                               expect=expect)

    def _get_sample(self, path: str, params: dict) -> Any:
        """Read an operator-captured response for `path`+`params` off disk.

        The filename is the slugified path plus the sorted params, so a games list and each
        facet land in distinct, predictable files the operator can produce by hand.
        """
        name = sample_filename(path, params)
        f = self.sample_dir / name
        if not f.exists():
            raise PFFClientError(
                f"No captured sample for {path} {params} — expected {f}. Capture it from the "
                "logged-in browser (DevTools → Network → the request → Copy response) and save "
                f"it as {name!r} in PFF_SAMPLE_DIR."
            )
        return json.loads(f.read_text())


def sample_filename(path: str, params: dict[str, Any] | None = None) -> str:
    """Deterministic capture filename for a path+params pair (shared by client and operator)."""
    slug = "".join(ch if ch.isalnum() else "_" for ch in urlsplit(path).path.strip("/"))
    parts = [f"{k}-{v}" for k, v in sorted((params or {}).items())]
    return "__".join([slug, *parts]) + ".json" if parts else slug + ".json"


def _parse_cookie_header(cookie_header: str) -> list[tuple[str, str]]:
    """`"a=1; b=2"` → `[("a","1"), ("b","2")]`.

    Split on the FIRST `=` only — PFF's jar contains base64 and JWT values that themselves
    contain `=` padding, and a naive `split("=")` would truncate exactly the session token.
    """
    out = []
    for chunk in (cookie_header or "").split(";"):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out.append((k.strip(), v.strip()))
    return out


def _cookie_header_to_list(cookie_header: str, domain: str | None) -> list[dict]:
    """`"a=1; b=2"` → FlareSolverr's cookie objects."""
    out = []
    for k, v in _parse_cookie_header(cookie_header):
        c = {"name": k, "value": v}
        if domain:
            c["domain"] = domain
        out.append(c)
    return out


def parse_csv(text: str) -> list[dict]:
    """PFF's export CSV → row dicts, with numerics coerced and blanks left as None.

    Blank cells are common and meaningful in the export (a QB with no attempts has an empty
    `avg_depth_of_target`, not a zero) — coercing them to 0.0 would invent data, so they stay
    None and become NaN downstream rather than a real-looking number.
    """
    import csv as _csv
    import io

    rows: list[dict] = []
    for raw in _csv.DictReader(io.StringIO(text)):
        row: dict[str, Any] = {}
        for k, v in raw.items():
            if k is None:
                continue
            if v is None or v == "":
                row[k] = None
                continue
            try:
                row[k] = int(v) if v.lstrip("-").isdigit() else float(v)
            except ValueError:
                row[k] = v
        rows.append(row)
    return rows


def _parse_response(url: str, status: int, body: str, *, expect: str = "json") -> Any:
    """Turn a raw response into JSON, or raise the error that NAMES what went wrong.

    The ordering matters. An expired PFF session does not reliably return 401 — it very often
    returns a cheerful 200 carrying the LOGIN PAGE, which `json.loads` then fails on with a
    baffling message about `<`. So we test the body's shape, not just the status code, and
    name the auth failure explicitly.
    """
    text = (body or "").strip()
    if status == 404:
        # PFF returns 404 with the body `"Internal server error"`, which is neither. Naming it
        # keeps a routine discovery miss out of the retry loop and out of the error log.
        raise PFFNotFoundError(f"{url} does not exist (HTTP 404)")
    if status in (401, 403):
        if _looks_like_challenge(text):
            raise PFFChallengeError(
                f"Cloudflare challenged {url} (HTTP {status}). Retry with "
                "PFF_TRANSPORT=flaresolverr and a PFF_COOKIE credential."
            )
        raise PFFAuthError(
            f"PFF rejected the credential for {url} (HTTP {status}). The captured token/cookie "
            "has most likely expired — re-capture it from a fresh logged-in session."
        )
    if status == 431:
        raise PFFClientError(
            f"{url} returned HTTP 431 (Request Header Fields Too Large) with an empty body. "
            "PFF's cookie jar is ~7 KB, so this almost always means the cookie was sent TWICE "
            "— once in the session jar and once as an explicit Cookie header."
        )
    if status and status >= 500:
        raise PFFClientError(f"PFF origin returned HTTP {status} for {url}")
    if _looks_like_challenge(text):
        raise PFFChallengeError(
            f"{url} returned a Cloudflare challenge with HTTP {status} (a challenge is often "
            "served as 200 — this is why auth is verified by DATA, not by status code)."
        )
    if "__clerk_hs_reason" in text or "/v1/client/handshake" in text[:2000]:
        # We were handed the Clerk handshake itself rather than data — which means redirects
        # were not followed with cookie persistence. Naming it beats "unparseable JSON".
        raise PFFAuthError(
            f"{url} returned the Clerk handshake instead of data. PFF's `__session` JWT lives "
            "60s, so the API 307s to clerk.pff.com to refresh it — the client must FOLLOW that "
            "redirect with a cookie-persisting session. See PFFClient._session."
        )
    if _looks_like_login(text):
        # ⭐ HOISTED ABOVE THE FORMAT BRANCH ON PURPOSE. This check used to sit inside the JSON
        # arm, so a CSV request that received an expired-session login page returned the HTML
        # *as data* — a CSV parser turns it into nonsense rows instead of raising, which is the
        # silent-failure shape this module exists to refuse. EVERY auth/challenge check must
        # precede the format branch; only format-specific validation belongs below it.
        raise PFFAuthError(
            f"{url} returned an HTML login page with HTTP {status} — the session is not "
            "authenticated. Re-capture PFF_AUTH_TOKEN/PFF_COOKIE while logged in."
        )
    if expect == "csv":
        # A CSV export must not be validated as JSON — but the auth/challenge checks above
        # have already run, so an unauthenticated response can never reach the parser.
        if not text or "," not in text.splitlines()[0]:
            raise PFFClientError(
                f"{url} was requested as a CSV export but returned no comma-delimited header "
                f"(first 200 chars: {text[:200]!r})"
            )
        return text
    if text[:1] not in "{[":
        # A login page was already caught above; anything else non-JSON is a genuine surprise.
        raise PFFClientError(
            f"{url} returned non-JSON with HTTP {status} (first 200 chars: {text[:200]!r})"
        )
    try:
        return json.loads(text)
    except ValueError as exc:
        raise PFFClientError(f"{url} returned unparseable JSON: {exc}") from exc


def _looks_like_challenge(text: str) -> bool:
    """Cloudflare (on `clerk.pff.com`) AND DataDome (on `premium.pff.com`).

    Matching only Cloudflare markers would misfile a DataDome block as "unparseable JSON" and
    send the operator hunting the wrong problem.
    """
    low = text[:4000].lower()
    return any(m in low for m in (
        "just a moment", "cf-browser-verification", "cf_chl", "cdn-cgi/challenge",
        "datadome", "geo.captcha-delivery.com", "interstitial",
    ))


def _looks_like_login(text: str) -> bool:
    low = text[:4000].lower()
    return "<html" in low and any(m in low for m in ("sign in", "log in", "login", "password"))
