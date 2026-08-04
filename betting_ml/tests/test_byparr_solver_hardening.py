"""2026-08-03 — guards for the Byparr/FanGraphs solver blind spot (7-day silent outage).

WHAT HAPPENED: Byparr's Camoufox browser stopped launching ("BrowserType.launch: Connection closed
while reading from the driver"). Its FastAPI server kept answering, so the process never exited and
`restart: unless-stopped` never fired; the container sat `Up 3 weeks (unhealthy)` with restarts=0.
Meanwhile healthcheck.sh probed `/health || /` with `curl -fsS` — and because `-f` only fails on
>= 400, Byparr's `301 Moved Permanently` on `/` satisfied the fallback. Result: every FanGraphs
ingest 500'd for seven days behind a GREEN healthcheck. A `docker restart` cured it instantly.

These are SOURCE-INSPECTION guards (the box shell/compose can't run in CI). Per the INC-38 lesson a
source guard is worthless unless it (a) ignores comments — prose must not be able to satisfy it —
and (b) is proven to go RED on the actual pre-fix source. Both predicates below are pure functions
exercised against BOTH the real file AND a synthetic pre-fix snippet, so the RED proof lives in the
suite rather than in a reviewer's memory.

Fast-gate safe: pure text inspection + one pure-function import; no `pipeline`, no IO.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HEALTHCHECK = REPO / "services" / "dagster" / "aws" / "healthcheck.sh"
COMPOSE = REPO / "services" / "dagster" / "aws" / "docker-compose.yml"

# The EXACT probe as it shipped before this fix — the thing that passed a broken solver.
PRE_FIX_PROBE = (
    "$COMPOSE exec -T dagster-codeloc sh -c 'curl -fsS -o /dev/null --max-time 10 "
    "http://flaresolverr:8191/health || curl -fsS -o /dev/null --max-time 10 "
    "http://flaresolverr:8191/' 2>/dev/null \\\n"
    '  || fails+=("flaresolverr unreachable on :8191")'
)

# A pre-fix probe whose COMMENT claims 2xx (the real file's comment did say "Probe /health for a
# 2xx") while the code still asserts nothing. A guard that greps the whole file would pass this.
PRE_FIX_PROBE_WITH_2xx_PROSE = (
    "# Probe /health for a 2xx, falling back to / for a classic FlareSolverr.\n"
    "# Anything 2?? counts as healthy. case $code in 2??) — described here, not enforced.\n"
    + PRE_FIX_PROBE
)


def _strip_comments(src: str) -> str:
    """Drop whole-line shell comments so prose can never satisfy a guard (INC-38)."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def probe_requires_2xx(src: str) -> bool:
    """True iff the solver probe ASSERTS a 2xx status rather than relying on `curl -f`.

    Two conditions, both on comment-stripped source: the 2xx case arm must be present, AND the
    vulnerable `-f`-only fallback chain must be gone (a file could otherwise contain both).
    """
    code = _strip_comments(src)
    asserts_2xx = "2??)" in code and "%{http_code}" in code
    has_vulnerable_chain = "curl -fsS" in code and "flaresolverr:8191/health ||" in code
    return asserts_2xx and not has_vulnerable_chain


def checks_container_health(src: str) -> bool:
    """True iff the script reads Docker's own health status (catches running-but-unhealthy)."""
    code = _strip_comments(src)
    return ".State.Health.Status" in code and "unhealthy" in code


# ── the RED proofs: these predicates must FAIL on the pre-fix source ────────────────────


def test_the_guard_fails_on_the_actual_pre_fix_probe():
    # If this ever passes, the guard is vacuous and proves nothing about the real file.
    assert probe_requires_2xx(PRE_FIX_PROBE) is False


def test_a_comment_claiming_2xx_cannot_satisfy_the_guard():
    # INC-38: the pre-fix file's comment DID say "Probe /health for a 2xx" while asserting nothing.
    assert probe_requires_2xx(PRE_FIX_PROBE_WITH_2xx_PROSE) is False


def test_the_health_guard_fails_on_source_without_the_health_check():
    assert checks_container_health("running=$($COMPOSE ps --status running --services)") is False


# ── the real file must satisfy both ────────────────────────────────────────────────────


def test_the_solver_probe_asserts_a_2xx_not_merely_a_non_error():
    src = HEALTHCHECK.read_text()
    assert probe_requires_2xx(src), (
        "healthcheck.sh's flaresolverr probe must compare the ACTUAL status code and require 2xx. "
        "`curl -f` only fails on >= 400, so Byparr's 301 on / silently satisfied the old `||` "
        "fallback and hid a dead solver for 7 days."
    )


def test_healthcheck_detects_a_running_but_unhealthy_container():
    src = HEALTHCHECK.read_text()
    assert checks_container_health(src), (
        "A container can be `running` yet `unhealthy` indefinitely — Byparr sat that way for 3 "
        "weeks with restarts=0. The running-set check alone cannot see it."
    )


def test_autoheal_is_itself_a_core_service():
    # A watchdog nobody watches reproduces the outage it exists to prevent.
    code = _strip_comments(HEALTHCHECK.read_text())
    assert "autoheal" in code.split("CORE_SERVICES=(")[1].split(")")[0]


# ── compose: the actor that restarts an unhealthy container ────────────────────────────


@pytest.fixture(scope="module")
def compose():
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(COMPOSE.read_text())


def test_byparr_is_opted_in_to_autoheal(compose):
    assert compose["services"]["flaresolverr"]["labels"]["autoheal"] == "true"


def test_autoheal_service_is_scoped_by_label_not_global(compose):
    # Scope matters: unlabelled restarts could bounce Dagster/Postgres mid-job.
    ah = compose["services"]["autoheal"]
    assert ah["environment"]["AUTOHEAL_CONTAINER_LABEL"] == "autoheal"
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in ah["volumes"]


def test_autoheal_image_is_pinned_not_latest(compose):
    # This file's own pinning discipline — an unpinned :latest floats the watchdog under us.
    assert ":latest" not in compose["services"]["autoheal"]["image"]


# ── fangraphs_client: pin the solver-vs-origin 5xx discrimination ───────────────────────
#
# NOT a bug fix — a REGRESSION PIN. `_is_upstream_5xx` decides whether to halve the leaderboard
# page and retry (the INC-26 origin-500 cure). It correctly ignores a Byparr-side 500, but only
# because curl_cffi renders it "HTTP Error 500: ..." — the word "Error" sits between "HTTP " and
# the digits, so the `HTTP 5\d\d` regex misses it. That is correct BY LUCK: it depends on a third-
# party message format we do not control. These pin both directions so a curl_cffi rewording (or a
# well-meaning regex "simplification") surfaces here instead of silently mis-attributing a dead
# browser as a FanGraphs origin fault.


def _attempts_failed_chain(cause: Exception) -> Exception:
    """Rebuild the exact chain _flaresolverr_get raises: the summary error `from last_exc`."""
    from scripts.utils.fangraphs_client import FangraphsClientError

    err = FangraphsClientError("All 3 attempts failed for https://www.fangraphs.com/api/...")
    err.__cause__ = cause
    return err


def test_a_byparr_side_500_is_NOT_classified_as_an_upstream_5xx():
    from scripts.utils.fangraphs_client import _is_upstream_5xx

    # What curl_cffi raises from r.raise_for_status() when Byparr itself 500s (browser dead).
    byparr_side = Exception("HTTP Error 500: Internal Server Error")
    assert _is_upstream_5xx(_attempts_failed_chain(byparr_side)) is False, (
        "A Byparr-side 500 means the SOLVER failed, not that FanGraphs' origin 5xx'd — halving "
        "the page size cannot help and mis-names the fault in the logs."
    )


def test_a_fangraphs_origin_5xx_IS_classified_as_an_upstream_5xx():
    from scripts.utils.fangraphs_client import FangraphsClientError, _is_upstream_5xx

    origin = FangraphsClientError(
        "FlareSolverr fetched https://www.fangraphs.com/api/... but upstream returned HTTP 503"
    )
    assert _is_upstream_5xx(_attempts_failed_chain(origin)) is True
