"""Minimal stdlib HTTP client for the platform-import adapters.

⚠️ WHY STDLIB. The API Lambda bundle (`infrastructure/lambda/deploy.sh`) installs fastapi, mangum,
boto3, pydantic, cryptography, duckdb, stripe and friends — but NOT `requests` or `httpx`, and the
zip already sits near the size cap. `urllib.request` is therefore the only HTTP client we can rely
on being present, so the adapters use this wrapper rather than adding a dependency.

🚦 EVERY call carries a FINITE timeout. This repo's INC-32 landmine is exactly this bug one layer
over: an un-timed-out call on a serialized/serving path hangs forever and takes the caller down with
it. A Lambda request thread blocked on a wedged Yahoo/Sleeper socket burns the whole invocation
window and returns a 502 with no diagnosis, so the timeout is a REQUIRED argument's default here and
is never allowed to be None.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# Generous enough for a cold third-party API, short enough that a wedged socket cannot eat an API
# Gateway request window (29s hard cap) — a hung import must fail fast and legibly, not time out
# at the edge where the user sees an unexplained 502.
DEFAULT_TIMEOUT = 8.0

USER_AGENT = "Credence-Sports/1.0 (fantasy league import)"

# 🚦 THROTTLING. Yahoo answers a rate-limited request with **HTTP 999**, not 429 — a Yahoo-wide
# convention, and one that was silently mis-classified here: 999 fell through the generic
# `status >= 400` branch and reached the user as a 502 "the platform could not be reached", i.e. we
# reported an outage for a limit WE had hit and would clear by waiting. Both statuses mean the same
# thing and are treated the same way.
RATE_LIMIT_STATUSES = (429, 999)

# ONE retry, and the budget is why. An API Gateway request dies at 29s and `DEFAULT_TIMEOUT` is 8s,
# so a single retry costs at most 8 + wait + 8 and stays inside the window; a second would not. A
# `Retry-After` longer than this cap is HONOURED BY NOT RETRYING — sleeping through the gateway's
# own deadline turns a legible 429 into an unexplained edge timeout, which is strictly worse for
# the user and undiagnosable for us (the INC-32 "an un-budgeted wait on a serving path" shape).
_RETRY_ATTEMPTS = 1
_MAX_RETRY_WAIT = 5.0
_DEFAULT_RETRY_WAIT = 1.0


class PlatformHTTPError(RuntimeError):
    """A non-2xx response (or a transport failure) from a fantasy platform.

    `status` is the HTTP status when there was one, else None (DNS/timeout/reset). Adapters map this
    onto a user-facing message; the router turns it into a 4xx/5xx. Kept distinct from ValueError so
    "the platform said no" is never confused with "the user's input was malformed".
    """

    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        # A short snippet of the upstream body. Yahoo distinguishes "this user's grant is gone" from
        # "this APP is not entitled to Fantasy data" ONLY in the body (`oauth_problem=…`) — both are
        # a bare 401 — so a status-only exception cannot tell a caller which one it is.
        self.body = body


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        # nosec B310 — the scheme is asserted https by the callers' URL builders, which interpolate
        # only regex-validated ids into a fixed host (never a user-supplied host).
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return int(resp.status), resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:  # noqa: BLE001 - a body-less error response is normal
            pass
        return int(e.code), body, dict(e.headers or {})
    except urllib.error.URLError as e:
        raise PlatformHTTPError(f"could not reach {urllib.parse.urlsplit(url).netloc}: {e.reason}") from e
    except TimeoutError as e:
        raise PlatformHTTPError(
            f"{urllib.parse.urlsplit(url).netloc} did not respond within {timeout:.0f}s"
        ) from e


def get_json(
    url: str, *, headers: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT
) -> object:
    """GET a URL and parse JSON. Raises PlatformHTTPError on a non-2xx or unparseable body.

    ⚠️ A 200 with an EMPTY or `null` body is treated as a MISS (returns None), not as an error:
    Sleeper answers an unknown user/league with `null` and a 200, and conflating that with a
    transport failure would tell a user "Sleeper is down" when they simply typed the wrong username.
    """
    status, body, resp_headers = _request(url, headers=headers, timeout=timeout)
    for _ in range(_RETRY_ATTEMPTS):
        if status not in RATE_LIMIT_STATUSES:
            break
        wait = _retry_after_seconds(resp_headers)
        if wait is None:
            break
        logger.info(
            "platform %s rate-limited (HTTP %s); retrying once in %.1fs",
            urllib.parse.urlsplit(url).netloc,
            status,
            wait,
        )
        time.sleep(wait)
        status, body, resp_headers = _request(url, headers=headers, timeout=timeout)
    if status in RATE_LIMIT_STATUSES:
        # The TRUE upstream status travels on the exception so a 999 stays diagnosable as Yahoo's
        # own throttle rather than being laundered into a 429 we invented.
        raise PlatformHTTPError(
            "the platform is rate-limiting us; try again shortly", status=status
        )
    if status == 401:
        raise PlatformHTTPError(
            "not authorized for this league", status=401, body=body[:400].decode("utf-8", "replace")
        )
    if status == 404:
        raise PlatformHTTPError("not found", status=404)
    if status >= 400:
        raise PlatformHTTPError(f"platform returned HTTP {status}", status=status)
    if not body.strip():
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise PlatformHTTPError("platform returned a response we could not parse") from e


def post_form(
    url: str,
    form: dict[str, str],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, object]:
    """POST an x-www-form-urlencoded body (the OAuth token endpoints' required encoding).

    Returns `(status, parsed_json_or_None)` WITHOUT raising on a 4xx, because an OAuth error
    response carries the diagnostic payload (`error`, `error_description`) in the body and the
    caller needs to read it to tell "the code expired" from "the client secret is wrong".
    """
    body = urllib.parse.urlencode(form).encode("utf-8")
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    # ⛔ DELIBERATELY NOT RETRIED, unlike `get_json`. An OAuth authorization code is single-use, so
    # replaying a POST that may already have been accepted upstream can spend the grant and return
    # the SECOND, failing answer — a retry that manufactures the error it is trying to survive.
    status, raw, _ = _request(url, method="POST", headers=hdrs, data=body, timeout=timeout)
    parsed: object = None
    if raw.strip():
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
    return status, parsed


def _retry_after_seconds(headers: dict[str, str]) -> float | None:
    """How long to wait before ONE retry, or None to give up now and report the limit honestly.

    Returns None when the platform asks for longer than we can afford (see `_MAX_RETRY_WAIT`), so
    "we waited and it still said no" and "it told us to come back in a minute" stay distinguishable
    rather than both arriving as a timeout.
    """
    raw = ""
    for key, value in (headers or {}).items():
        if str(key).lower() == "retry-after":
            raw = str(value).strip()
            break
    if not raw:
        return _DEFAULT_RETRY_WAIT
    try:
        wait = float(raw)
    except ValueError:
        # An HTTP-date form of `Retry-After` is legal and we do not parse it; treat it as "too long
        # to be worth guessing at" rather than silently retrying immediately.
        return None
    if wait <= 0:
        return _DEFAULT_RETRY_WAIT
    return wait if wait <= _MAX_RETRY_WAIT else None


__all__ = [
    "DEFAULT_TIMEOUT",
    "RATE_LIMIT_STATUSES",
    "PlatformHTTPError",
    "get_json",
    "post_form",
]
