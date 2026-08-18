"""client.py — the authed PFF API client (NF-W9-0).

Modelled on `scripts/utils/fangraphs_client.py`, the repo's sanctioned authed-fetch pattern.
PFF is a PAID subscription behind login, and (like FanGraphs) fronted by Cloudflare — so this
client NEVER tries to bypass auth. It takes a credential the OPERATOR captured from their own
logged-in browser session and replays it.

THREE TRANSPORTS, because the credential shape decides which one can work:

  • `direct`       — curl_cffi with a Chrome TLS fingerprint + the operator's `Authorization:
                     Bearer …` and/or cookie. Works when PFF's edge lets a fingerprint-matched
                     client through (a token-authed XHR usually is not challenged).
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

CONFIGURATION (all operator-supplied; nothing is committed):
  PFF_AUTH_TOKEN   — bearer token from the logged-in session (Authorization: Bearer …)
  PFF_COOKIE       — raw Cookie header, the alternative/companion credential
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


class PFFClientError(RuntimeError):
    """Any PFF fetch failure. Never swallowed into an empty result."""


class PFFAuthError(PFFClientError):
    """The credential is missing, expired or rejected (401/403 with a real response)."""


class PFFChallengeError(PFFClientError):
    """A Cloudflare challenge answered instead of the API — retry via `flaresolverr`."""


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
        if self.transport not in ("direct", "flaresolverr", "sample"):
            raise PFFClientError(
                f"Unknown PFF_TRANSPORT {self.transport!r} (direct|flaresolverr|sample)"
            )

    # ── credential plumbing ────────────────────────────────────────────────────────────────
    @property
    def has_credential(self) -> bool:
        return bool(self.token or self.cookie)

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/json",
            "Referer": f"{self.api_base}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.token:
            # Accept a token pasted either bare or already prefixed.
            h["Authorization"] = self.token if self.token.lower().startswith("bearer ") \
                else f"Bearer {self.token}"
        if self.cookie:
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

    # ── the one fetch entry point ──────────────────────────────────────────────────────────
    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
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
            return self._get_flaresolverr(path, params)
        return self._get_direct(path, params)

    def _url(self, path: str, params: dict) -> str:
        url = path if path.startswith("http") else f"{self.api_base}/{path.lstrip('/')}"
        return f"{url}?{urlencode(params)}" if params else url

    # ── transports ─────────────────────────────────────────────────────────────────────────
    def _get_direct(self, path: str, params: dict) -> Any:
        from curl_cffi import requests  # imported lazily: `sample` must work without it

        url = self._url(path, params)
        last: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                r = requests.get(
                    url, headers=self._headers(), impersonate="chrome", timeout=_TIMEOUT_S
                )
                return _parse_response(url, r.status_code, r.text)
            except (PFFAuthError, PFFChallengeError):
                raise  # neither is retryable — a retry just re-answers the same challenge
            except Exception as exc:  # noqa: BLE001
                last = exc
                log.warning("PFF direct attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAYS[attempt - 1])
        raise PFFClientError(f"All {_MAX_RETRIES} direct attempts failed for {url}") from last

    def _get_flaresolverr(self, path: str, params: dict) -> Any:
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
        return _parse_response(url, int(sol.get("status") or 0), sol.get("response", ""))

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


def _cookie_header_to_list(cookie_header: str, domain: str | None) -> list[dict]:
    """`"a=1; b=2"` → FlareSolverr's cookie objects."""
    out = []
    for chunk in cookie_header.split(";"):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        c = {"name": k.strip(), "value": v.strip()}
        if domain:
            c["domain"] = domain
        out.append(c)
    return out


def _parse_response(url: str, status: int, body: str) -> Any:
    """Turn a raw response into JSON, or raise the error that NAMES what went wrong.

    The ordering matters. An expired PFF session does not reliably return 401 — it very often
    returns a cheerful 200 carrying the LOGIN PAGE, which `json.loads` then fails on with a
    baffling message about `<`. So we test the body's shape, not just the status code, and
    name the auth failure explicitly.
    """
    text = (body or "").strip()
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
    if status and status >= 500:
        raise PFFClientError(f"PFF origin returned HTTP {status} for {url}")
    if _looks_like_challenge(text):
        raise PFFChallengeError(
            f"{url} returned a Cloudflare challenge with HTTP {status} (a challenge is often "
            "served as 200 — this is why auth is verified by DATA, not by status code)."
        )
    if text[:1] not in "{[":
        # The classic expired-session shape: HTTP 200 + the login page.
        if _looks_like_login(text):
            raise PFFAuthError(
                f"{url} returned an HTML login page with HTTP {status} — the session is not "
                "authenticated. Re-capture PFF_AUTH_TOKEN/PFF_COOKIE while logged in."
            )
        raise PFFClientError(
            f"{url} returned non-JSON with HTTP {status} (first 200 chars: {text[:200]!r})"
        )
    try:
        return json.loads(text)
    except ValueError as exc:
        raise PFFClientError(f"{url} returned unparseable JSON: {exc}") from exc


def _looks_like_challenge(text: str) -> bool:
    low = text[:4000].lower()
    return any(m in low for m in ("just a moment", "cf-browser-verification", "cf_chl", "cdn-cgi/challenge"))


def _looks_like_login(text: str) -> bool:
    low = text[:4000].lower()
    return "<html" in low and any(m in low for m in ("sign in", "log in", "login", "password"))
