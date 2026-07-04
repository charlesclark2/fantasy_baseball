"""INC-26 (E11.1-W11-FG precursor) — unit tests for the paginated FanGraphs leaderboard fetch.

Offline (FlareSolverr is mocked). Verifies the cure for the HTTP 500 on the old single
`pageitems=2000000` request:
  • fetch_leaderboard walks pagenum at a capped page_size and concatenates pages;
  • it de-duplicates by playerid so a pagination-IGNORING API (full set every page) terminates;
  • an upstream 5xx halves the page_size and retries the SAME page (the retry path);
  • the qual floor and page_size are threaded through to the request params.
"""
import re

import pytest

from utils import fangraphs_client as fc


def _page(ids):
    return {"data": [{"playerid": str(i), "Name": f"P{i}", "WAR": 1.0} for i in ids]}


def test_paginates_and_concatenates(monkeypatch):
    """page_size=2: page 1 returns 2 (full) → continue; page 2 returns 1 (short) → stop. 3 rows total."""
    calls = []

    def fake_get(url, params, max_timeout_ms=None):
        calls.append(params)
        pagenum = int(params["pagenum"])
        return (_page([1, 2]) if pagenum == 1 else _page([3]), 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_leaderboard(stats="pit", type_id=36, season=2026, page_size=2)

    assert [r["playerid"] for r in out["data"]] == ["1", "2", "3"]
    assert len(calls) == 2
    assert out["http_status_code"] == 200
    # request_params captured is page 1, with the capped pageitems (never 2000000).
    assert out["request_params"]["pageitems"] == "2"
    assert out["request_params"]["pagenum"] == "1"


def test_pagination_ignored_terminates_and_dedups(monkeypatch):
    """An API that returns the FULL set on every page must not loop: page 2 is all-seen → stop, no dupes."""
    def fake_get(url, params, max_timeout_ms=None):
        return (_page([1, 2, 3]), 200)  # same 3 rows regardless of pagenum

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_leaderboard(stats="pit", type_id=36, season=2026, page_size=3)

    assert [r["playerid"] for r in out["data"]] == ["1", "2", "3"]  # deduped, not 6+


def test_upstream_5xx_halves_page_size_and_retries(monkeypatch):
    """A 500 on the full page → halve page_size and retry the SAME page (not re-solve the challenge)."""
    seen_page_sizes = []

    def fake_get(url, params, max_timeout_ms=None):
        ps = int(params["pageitems"])
        seen_page_sizes.append(ps)
        if ps == 1000:
            raise fc.FangraphsClientError(
                "FlareSolverr fetched ... but upstream returned HTTP 500"
            )
        return (_page([1]), 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_leaderboard(stats="pit", type_id=36, season=2026)  # default page_size=1000

    assert [r["playerid"] for r in out["data"]] == ["1"]
    assert seen_page_sizes == [1000, 500]  # halved once, retried the same page


def test_non_5xx_error_propagates(monkeypatch):
    """A challenge/solve failure (not a 5xx) is NOT a page-size problem → surfaces, not silently retried."""
    def fake_get(url, params, max_timeout_ms=None):
        raise fc.FangraphsClientError("FlareSolverr did not solve the request: timeout")

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    with pytest.raises(fc.FangraphsClientError):
        fc.fetch_leaderboard(stats="pit", type_id=36, season=2026)


def test_qual_and_pagesize_threaded_into_params(monkeypatch):
    captured = {}

    def fake_get(url, params, max_timeout_ms=None):
        captured.update(params)
        return (_page([1]), 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    fc.fetch_leaderboard(stats="bat", type_id=8, season=2025, qual=50, page_size=750)

    assert captured["qual"] == "50"
    assert captured["pageitems"] == "750"
    # never the origin-500 value
    assert captured["pageitems"] != "2000000"


def test_is_upstream_5xx_walks_chain():
    root = fc.FangraphsClientError("upstream returned HTTP 503")
    wrapped = fc.FangraphsClientError("All 3 attempts failed")
    wrapped.__cause__ = root
    assert fc._is_upstream_5xx(wrapped) is True
    assert fc._is_upstream_5xx(fc.FangraphsClientError("HTTP 403 challenge")) is False
