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
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# Generous enough for a cold third-party API, short enough that a wedged socket cannot eat an API
# Gateway request window (29s hard cap) — a hung import must fail fast and legibly, not time out
# at the edge where the user sees an unexplained 502.
DEFAULT_TIMEOUT = 8.0

USER_AGENT = "Credence-Sports/1.0 (fantasy league import)"


class PlatformHTTPError(RuntimeError):
    """A non-2xx response (or a transport failure) from a fantasy platform.

    `status` is the HTTP status when there was one, else None (DNS/timeout/reset). Adapters map this
    onto a user-facing message; the router turns it into a 4xx/5xx. Kept distinct from ValueError so
    "the platform said no" is never confused with "the user's input was malformed".
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        # nosec B310 — the scheme is asserted https by the callers' URL builders, which interpolate
        # only regex-validated ids into a fixed host (never a user-supplied host).
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:  # noqa: BLE001 - a body-less error response is normal
            pass
        return int(e.code), body
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
    status, body = _request(url, headers=headers, timeout=timeout)
    if status == 401:
        raise PlatformHTTPError("not authorized for this league", status=401)
    if status == 404:
        raise PlatformHTTPError("not found", status=404)
    if status == 429:
        raise PlatformHTTPError("the platform is rate-limiting us; try again shortly", status=429)
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
    status, raw = _request(url, method="POST", headers=hdrs, data=body, timeout=timeout)
    parsed: object = None
    if raw.strip():
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
    return status, parsed


__all__ = ["DEFAULT_TIMEOUT", "PlatformHTTPError", "get_json", "post_form"]
