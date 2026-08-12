"""INC-42 — the box healthcheck must measure clock skew against S3's own clock.

On 2026-08-11 the box clock drifted past AWS SigV4's ~900s tolerance. S3 answered every DuckDB
`httpfs` GET with `403 RequestTimeTooSkewed`, so `run_w1_lakehouse --w3pre-only` HALTed at the
INC-23 DESCRIBE and the served game-state flatten froze.

Nothing saw it, and the reason is the interesting part: **botocore auto-corrects for skew** (it
reads S3's `Date` header, caches the offset and retries), so every boto3 capture kept writing on the
half-hour and looked healthy, while DuckDB `httpfs` and delta-rs/`object_store` sign with the local
clock and hard-fail. Writers green, readers dead, containers up, endpoints 2xx.

Each test below pins ONE property and is independently RED-provable: deleting the clause it names
fails exactly this test (NF-D17 — a guard whose fixture trips a *different* clause proves nothing).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_HEALTHCHECK = (
    Path(__file__).resolve().parents[2] / "services" / "dagster" / "aws" / "healthcheck.sh"
)


@pytest.fixture(scope="module")
def script() -> str:
    return _HEALTHCHECK.read_text()


@pytest.fixture(scope="module")
def code(script: str) -> str:
    """Comments stripped — INC-38: prose must never be able to satisfy a source guard."""
    return "\n".join(ln for ln in script.splitlines() if not ln.lstrip().startswith("#"))


@pytest.fixture(scope="module")
def skew_block(code: str) -> str:
    """Just the skew stanza, so a match elsewhere in the file cannot satisfy these assertions."""
    m = re.search(r"_skew_max=.*?^fi$", code, re.S | re.M)
    assert m, "the clock-skew stanza is missing from healthcheck.sh entirely"
    return m.group(0)


def test_the_probe_exists_and_reports_through_the_paging_path(skew_block):
    """It must feed `fails` — that is what carries the fail-threshold, cooldown and notify."""
    assert "fails+=(" in skew_block
    assert "clock skew" in skew_block


def test_it_reads_s3s_own_clock_not_a_local_ntp_estimate(skew_block):
    """S3's `Date` header IS the clock that decides whether a signature is accepted."""
    assert "s3.us-east-2.amazonaws.com" in skew_block
    assert re.search(r"-D\s+-", skew_block), "must dump response headers to read Date"


def test_the_curl_does_not_use_dash_f(skew_block):
    """`-f` suppresses output on >=400 — it would discard the header the moment S3 answers 403."""
    curl = re.search(r"curl[^\n|]*", skew_block).group(0)
    assert not re.search(r"(?<![\w-])-f(?![\w-])", curl), "-f would drop the Date header on a 4xx"
    assert not re.search(r"--fail", curl)


def test_the_curl_does_not_follow_redirects(skew_block):
    """The root endpoint answers 307 to aws.amazon.com — following it measures another host's clock."""
    curl = re.search(r"curl[^\n|]*", skew_block).group(0)
    assert not re.search(r"(?<![\w-])-L(?![\w-])", curl)
    assert "--location" not in curl


def test_the_header_match_is_portable_not_gnu_awk_only(skew_block):
    """`IGNORECASE` is a gawk extension; under BSD/mawk it matches NOTHING, so the probe would report
    UNEVALUABLE every 5 minutes and the monitor would get muted."""
    assert "IGNORECASE" not in skew_block
    assert "tolower(" in skew_block, "case-insensitive header match must be portable"


def test_an_unevaluable_probe_is_never_scored_healthy(skew_block):
    """NF1.7(a) — a check that did not run is not a pass. Both the no-header and the unparseable-date
    paths must page, not fall through."""
    unevaluable = re.findall(r"fails\+=\(\"clock skew UNEVALUABLE", skew_block)
    assert len(unevaluable) >= 2, "missing an UNEVALUABLE branch (empty header / unparseable date)"


def test_the_threshold_leaves_runway_below_the_sigv4_hard_bound(skew_block):
    """SigV4 hard-fails at ~900s; paging only at 900 would page after the outage, not before it."""
    m = re.search(r"CLOCK_SKEW_MAX_S:-(\d+)", skew_block)
    assert m, "threshold must be configurable with an explicit default"
    assert 0 < int(m.group(1)) < 900


def test_the_skew_is_compared_as_an_absolute_value(skew_block):
    """A clock running FAST is just as fatal as one running slow; a signed compare misses half."""
    assert "#-" in skew_block or "abs" in skew_block, "negative skew must be folded to absolute"
