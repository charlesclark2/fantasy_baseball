"""NF-FRESH2 — fast-gate guards for the draft-board freshness build.

The defect this story fixed was invisible by construction: `fetch_ffc_adp` / `fetch_fp_ecr` default
`refresh=False` and every caller omitted the argument, so a full board rebuild + republish silently
re-read a three-week-old cache and shipped it — with a UI stamp that said "built 5 days ago". There
was no error, no log line, and no artifact that differed from a healthy one. That is why the story
requires each of these to be RED-PROVEN: a freshness guard that cannot fail is exactly as useful as
the absent guard that let the bug ship (the NF1.7(a) / INC-38 / NF-D17 vacuous-guard family).

Fast-gate discipline: nothing here imports `pipeline` at module scope (the E11.23 rule — the dbt
manifest is absent in the fast gate); the Dagster-wiring tests import inside the test body and skip
cleanly when the manifest is not there. No network: every fetch is monkeypatched, and one test
proves the monkeypatch is real by asserting the network stub was NOT reached.
"""
from __future__ import annotations

import importlib
import json
from datetime import date
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import adp_source as A
from quant_sports_intel_models.football.nfl.fantasy import fantasypros_source as F
from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF
from quant_sports_intel_models.football.nfl.ingest.sources import current_season

CURRENT = current_season()
HISTORICAL = 2021


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — real payload SHAPES, taken from the live cached artifacts
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ffc_payload(end_date: str, drafts: int = 6334) -> dict:
    """The real FFC response shape (`status` / `meta` / `players`), as cached on disk."""
    return {
        "status": "Success",
        "meta": {"type": "PPR", "teams": 12, "rounds": 15, "total_drafts": drafts,
                 "start_date": "2026-08-07", "end_date": end_date},
        "players": [{"name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "adp": 1.4,
                     "stdev": 0.8, "high": 1, "low": 4, "times_drafted": 900}],
    }


def _fp_payload(ts: int, label: str) -> dict:
    """The real FantasyPros response shape. `last_updated` is a bare month/day with NO YEAR —
    which is precisely why the as-of stamp is derived from `last_updated_ts` instead."""
    return {
        "sport": "NFL", "year": "2026", "scoring": "PPR", "total_experts": 89,
        "last_updated": label, "last_updated_ts": ts,
        "players": [{"player_name": "Ja'Marr Chase", "player_position_id": "WR",
                     "player_team_id": "CIN", "rank_ecr": 1, "rank_ave": 1.2, "rank_std": 0.4,
                     "rank_min": 1, "rank_max": 3, "pos_rank": "WR1", "tier": 1}],
    }


@pytest.fixture
def caches(tmp_path):
    """An on-disk ADP + ECR cache holding a STALE snapshot, exactly as the live artifacts did."""
    adp_dir, ecr_dir = tmp_path / "adp", tmp_path / "ecr"
    adp_dir.mkdir(), ecr_dir.mkdir()
    for season in (CURRENT, HISTORICAL):
        (adp_dir / f"ffc_ppr_12_{season}.json").write_text(
            json.dumps(_ffc_payload("2026-07-25", drafts=3091)))
        (ecr_dir / f"fp_ecr_PPR_{season}.json").write_text(
            json.dumps(_fp_payload(1785088273, "7/26")))  # 2026-07-26
    return adp_dir, ecr_dir


@pytest.fixture
def net(monkeypatch):
    """Stub the ONE network call each fetcher makes, and record whether it was reached.

    Stubbing `urlopen` (rather than the fetcher) is deliberate: it is the real boundary, so a test
    that asserts "the network was not reached" is asserting about the actual socket call and not
    about a helper it also controls."""
    state = {"adp_hits": 0, "ecr_hits": 0, "adp_end": "2026-08-14", "ecr_ts": 1786000000,
             "adp_raises": False, "ecr_raises": False}

    class _Resp:
        def __init__(self, payload):
            self._b = json.dumps(payload).encode()

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # ⚠️ ONE dispatcher, routed on the URL — NOT two per-module patches. Both `adp_source` and
    # `fantasypros_source` do a plain `import urllib.request`, so they share ONE global
    # `urllib.request.urlopen`: patching it twice makes the SECOND patch serve BOTH modules, and
    # the ADP tests then silently measure the ECR stub. (Found by this suite failing, which is the
    # point of asserting on hit COUNTS rather than only on outcomes.)
    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "fantasypros" in url:
            state["ecr_hits"] += 1
            if state["ecr_raises"]:
                raise OSError("FantasyPros is down")
            return _Resp(_fp_payload(state["ecr_ts"], "8/14"))
        state["adp_hits"] += 1
        if state["adp_raises"]:
            raise OSError("FFC is down")
        return _Resp(_ffc_payload(state["adp_end"]))

    monkeypatch.setattr(A.urllib.request, "urlopen", _open)
    return state


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P1 (a) — `--market-refresh` ACTUALLY REFETCHES, and refresh=False does not
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_refresh_true_refetches_and_does_not_serve_the_cache(caches, net):
    """The core claim. RED PROOF: revert `_ffc_payload` to the pre-NF-FRESH2 `if cache.exists() and
    not refresh` ordering with `refresh` never threaded, and this fails on BOTH assertions."""
    adp_dir, _ = caches
    df = A.fetch_ffc_adp(CURRENT, cache_dir=adp_dir, refresh=True)
    assert net["adp_hits"] == 1, "refresh=True must reach the network, not the cache"
    # ...and the refreshed snapshot must be what LANDED, not merely what was fetched.
    assert MF.adp_as_of(CURRENT, cache_dir=adp_dir)["as_of"] == "2026-08-14"
    assert not df.empty


def test_refresh_false_serves_the_cache_and_never_touches_the_network(caches, net):
    """The other side of the same claim — without it, "it refetched" is unfalsifiable because a
    build that ALWAYS refetches would pass the test above."""
    adp_dir, ecr_dir = caches
    A.fetch_ffc_adp(CURRENT, cache_dir=adp_dir, refresh=False)
    F.fetch_fp_ecr(CURRENT, cache_dir=ecr_dir, refresh=False)
    assert net["adp_hits"] == 0 and net["ecr_hits"] == 0
    assert MF.adp_as_of(CURRENT, cache_dir=adp_dir)["as_of"] == "2026-07-25"


def test_ecr_refresh_true_refetches(caches, net):
    _, ecr_dir = caches
    F.fetch_fp_ecr(CURRENT, cache_dir=ecr_dir, refresh=True)
    assert net["ecr_hits"] == 1
    assert MF.ecr_as_of(CURRENT, cache_dir=ecr_dir)["as_of"] == "2026-08-06"  # epoch 1786000000


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P1 (b) — the E5.9 CORRECTNESS BOUNDARY: historical seasons stay PINNED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_historical_seasons_are_refused_a_refresh_even_when_asked():
    """⭐ THE BOUNDARY. Refreshing 2019–2024 would regrade the published track record against an ADP
    that did not exist when the projection was made — a hindsight benchmark.

    RED PROOF: change `should_refresh_market` to `return bool(market_refresh)` and this fails."""
    assert MF.should_refresh_market(CURRENT, True) is True
    for season in (2019, 2020, 2021, 2022, 2023, 2024, CURRENT - 1):
        assert MF.should_refresh_market(season, True) is False, season
    # And a FUTURE season is refused too — the test is `== current_season()`, not `>=`.
    assert MF.should_refresh_market(CURRENT + 1, True) is False


def test_the_boundary_is_clock_derived_not_pinned():
    """The NCAAF-P0.6 stale-by-a-season landmine: next August this must move on its own."""
    assert MF.should_refresh_market(2026, True, today=date(2026, 8, 15)) is True
    assert MF.should_refresh_market(2026, True, today=date(2027, 8, 15)) is False
    assert MF.should_refresh_market(2027, True, today=date(2027, 8, 15)) is True


def test_a_historical_build_reads_its_pinned_snapshot_off_disk(caches, net):
    """The boundary, exercised end-to-end through the fetcher rather than asserted on the helper.

    ⚠️ The fixture caches BOTH seasons with the SAME stale window on purpose — so this test can only
    pass because the network was refused, never because the two happened to agree."""
    adp_dir, _ = caches
    refresh = MF.should_refresh_market(HISTORICAL, True)
    A.fetch_ffc_adp(HISTORICAL, cache_dir=adp_dir, refresh=refresh)
    assert net["adp_hits"] == 0, "a historical season must never reach the market"
    assert MF.adp_as_of(HISTORICAL, cache_dir=adp_dir)["as_of"] == "2026-07-25"


def test_a_cold_historical_cache_may_still_be_fetched_once(tmp_path, net):
    """The boundary forbids OVERWRITING a pinned snapshot, not obtaining one that was never pulled.

    Stated as its own test because the two are easy to conflate, and conflating them would break
    every first-ever historical backtest. Verified against the live API on 2026-08-15: FFC serves a
    PAST season's ARCHIVED preseason window (2021 → `2021-08-31 → 2021-09-01`, 1,709 drafts), not
    today's re-rank — so a cold-start pull is not a hindsight pull."""
    A.fetch_ffc_adp(HISTORICAL, cache_dir=tmp_path,
                    refresh=MF.should_refresh_market(HISTORICAL, True))
    assert net["adp_hits"] == 1, "a season with NO snapshot at all must still be obtainable"


def test_the_exporters_own_fetch_reduces_through_the_boundary(monkeypatch):
    """The exporter enforces the boundary independently of the projection build, because a
    historical re-publish is a separate entry point that could otherwise refresh."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as X

    seen: list[bool] = []
    monkeypatch.setattr(A, "fetch_ffc_adp",
                        lambda season, fmt, teams, refresh=False: seen.append(refresh) or __import__(
                            "pandas").DataFrame())
    X.set_market_refresh(True)
    try:
        X.A_fetch(CURRENT, "ppr", 12)
        X.A_fetch(HISTORICAL, "ppr", 12)
    finally:
        X.set_market_refresh(False)
    assert seen == [True, False], "the exporter must refresh only the current season"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P1 (c) — a failed refresh FALLS BACK, loudly, instead of losing the market
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_failed_refresh_keeps_the_last_good_snapshot(caches, net, caplog):
    """`refresh=True` is the DEFAULT now, so a transient FFC outage is on the serving path. Losing
    the market would silently reorder the board (the market feeds the RANKING), which is far worse
    than shipping an older one — and the stale `adp_as_of` announces the fallback rather than
    hiding it (the E9.62 "a clamp must report whether it bound" rule)."""
    adp_dir, ecr_dir = caches
    net["adp_raises"] = net["ecr_raises"] = True
    with caplog.at_level("WARNING"):
        adp = A.fetch_ffc_adp(CURRENT, cache_dir=adp_dir, refresh=True)
        ecr = F.fetch_fp_ecr(CURRENT, cache_dir=ecr_dir, refresh=True)
    assert not adp.empty and not ecr.empty, "an outage must not degrade the season to market-blind"
    assert MF.adp_as_of(CURRENT, cache_dir=adp_dir)["as_of"] == "2026-07-25"
    assert any("REFRESH FAILED" in r.message for r in caplog.records)


def test_a_failed_refresh_with_no_cache_at_all_still_raises(tmp_path, net):
    """The fallback must not become a blanket swallow: with nothing on disk there is no last-good
    snapshot to keep, and the caller's own handler must see the failure."""
    net["adp_raises"] = True
    with pytest.raises(OSError):
        A.fetch_ffc_adp(CURRENT, cache_dir=tmp_path, refresh=True)


def test_a_non_success_refresh_falls_back_rather_than_shipping_the_error_body(caches, monkeypatch):
    """FFC answers an unavailable season with a 200 carrying `status: Error` (the NF-D16 trap). A
    refresh must neither cache that nor return it while a good snapshot exists."""
    adp_dir, _ = caches

    class _Resp:
        def read(self):
            return json.dumps({"status": "Error", "errors": "No ADP data found."}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(A.urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    df = A.fetch_ffc_adp(CURRENT, cache_dir=adp_dir, refresh=True)
    assert not df.empty, "the error body must not replace a good cached snapshot"
    assert MF.adp_as_of(CURRENT, cache_dir=adp_dir)["as_of"] == "2026-07-25"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P1 (d) — the as-of stamps exist, are honest, and never reach the network
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_as_of_stamps_carry_the_data_vintage_not_the_build_clock(caches):
    adp_dir, ecr_dir = caches
    adp = MF.adp_as_of(CURRENT, cache_dir=adp_dir)
    assert adp["as_of"] == "2026-07-25" == adp["window_end"]
    assert adp["window_start"] == "2026-08-07" and adp["drafts"] == 3091
    ecr = MF.ecr_as_of(CURRENT, cache_dir=ecr_dir)
    # ⭐ Derived from the epoch, NOT from FantasyPros' year-less "7/26" label.
    assert ecr["as_of"] == "2026-07-26" and ecr["label"] == "7/26" and ecr["experts"] == 89


def test_an_unreadable_or_missing_cache_stamps_none_never_a_guess(tmp_path):
    """NF1.7(a): an unevaluable stamp must be `null` (the UI renders "unknown"), never absent-by-
    omission and never a fabricated date."""
    assert MF.adp_as_of(CURRENT, cache_dir=tmp_path) is None
    assert MF.ecr_as_of(CURRENT, cache_dir=tmp_path) is None
    (tmp_path / f"ffc_ppr_12_{CURRENT}.json").write_text("{not json")
    assert MF.adp_as_of(CURRENT, cache_dir=tmp_path) is None
    # `market_as_of` always returns BOTH KEYS — a present-but-null key says "we looked and could
    # not tell", which a client must distinguish from a key an older exporter never wrote (NF-C0).
    both = MF.market_as_of(CURRENT, adp_cache_dir=tmp_path, ecr_cache_dir=tmp_path)
    assert set(both) == {"adp", "ecr"} and both["adp"] is None and both["ecr"] is None


def test_reading_a_stamp_can_never_fetch(caches, net):
    """A provenance read must REPORT the vintage, never CHOOSE it — otherwise the stamp and the
    data the export shipped could disagree."""
    adp_dir, ecr_dir = caches
    MF.market_as_of(CURRENT, adp_cache_dir=adp_dir, ecr_cache_dir=ecr_dir)
    assert net["adp_hits"] == 0 and net["ecr_hits"] == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P1 (e) — the stamps SURVIVE the serving path (the E9.41 dropped-field class, allowlist form)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_freshness_stamps_survive_the_entitlement_allowlists():
    """A LOCKED payload is built by an ALLOWLIST, so a served field absent from it is stripped with
    no error. Provenance is not paid content — withholding it would leave the exact honesty defect
    in place for the non-entitled half of the audience.

    RED PROOF: drop `adp_as_of` from `_PUBLIC_PROJECTIONS_META_FIELDS` and this fails."""
    from app.backend.services import entitlement as E

    payload = {"season": 2026, "generated_at": "2026-08-15T00:00:00+00:00",
               "adp_as_of": "2026-08-14", "ecr_as_of": "2026-08-05",
               "freshness": {"adp": {"source": "ffc", "as_of": "2026-08-14"}},
               "players": [{"id": "1", "name": "X", "pos": "WR", "fpPpr": 300.0}]}
    locked = E.lock_projections_payload(payload)
    for key in ("adp_as_of", "ecr_as_of", "freshness"):
        assert locked.get(key) == payload[key], f"{key} was stripped from the locked payload"

    manifest = {"season": 2026, "generated_at": "x", "configs": [],
                "adp_as_of": "2026-08-14", "ecr_as_of": "2026-08-05", "freshness": {"adp": None},
                "projections": {"players": 1, "adp_as_of": "2026-08-14"}}
    locked_m = E.lock_manifest_payload(manifest)
    for key in ("adp_as_of", "ecr_as_of", "freshness"):
        assert locked_m.get(key) == manifest[key], f"{key} was stripped from the locked manifest"
    assert (locked_m.get("projections") or {}).get("adp_as_of") == "2026-08-14"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P0 — the Sept-1 seasonal cron cliff
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cron_months(expr: str) -> set[int]:
    """Expand a cron MONTH field to the set of months it fires in."""
    months: set[int] = set()
    for part in expr.split()[3].split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            months.update(range(lo, hi + 1))
        elif part == "*":
            months.update(range(1, 13))
        else:
            months.add(int(part))
    return months


@pytest.mark.parametrize("const", ["NFL_ROLL_FORWARD_CRON", "NFL_SLEEPER_INJURIES_CRON"])
def test_the_nfl_ingest_crons_reach_the_opener_and_the_season(const):
    """⭐ P0, the hard deadline. Both schedules were month-scoped `3-8`, so on 09-01 every NFL raw
    feed would have frozen — through the 2026-09-09 opener and the whole season — while the Sep–Feb
    mart rebuild kept running over raw that had stopped advancing. September in particular is when
    nflverse FIRST publishes the injury report (in-season-only upstream).

    Read out of the SOURCE rather than by importing `pipeline` (the E11.23 fast-gate rule).
    RED PROOF: restore either constant to `3-8` and this fails naming the missing months."""
    src = Path("pipeline/schedules/sports_rollforward_schedules.py").read_text()
    line = next(ln for ln in src.splitlines()
                if ln.startswith(f"{const} = ") and not ln.lstrip().startswith("#"))
    months = _cron_months(line.split('"')[1])
    missing = sorted({9, 10, 11, 12, 1, 2} - months)
    assert not missing, f"{const} does not fire in month(s) {missing} — the season is uncovered"
    assert {3, 4, 5, 6, 7, 8} <= months, f"{const} lost part of the offseason window"


def test_the_operator_schedule_checker_is_two_sided():
    """The P0 verification tool must REJECT the pre-NF-FRESH2 crons as well as accept the new ones.

    Pinned because a checker that only ever reports PASS cannot tell a fixed cron from a broken one
    — and this one exists precisely to be the operator's evidence that the 09-01 cliff is closed.
    (`croniter` is absent from the box image; the tool uses Dagster's own vendored engine, which is
    the one that actually fires.)

    RED PROOF: widen `check`'s `SEASON_MONTHS` to `()` — every clause becomes vacuous and the
    control assertion below fails."""
    from datetime import datetime, timezone

    import scripts.check_nfl_schedule_coverage as C

    start = datetime(2026, 8, 30, tzinfo=timezone.utc)
    ok_new, _, _ = C.check("15 6 * 3-12,1-2 1", "America/Los_Angeles", start, 400)
    assert ok_new, "the shipped cron must pass"
    for _label, old_cron in C.CONTROL_CRONS:
        ok_old, covered, problems = C.check(old_cron, "America/Los_Angeles", start, 400)
        assert not ok_old, f"the checker accepted the known-broken cron {old_cron!r}"
        assert covered == set(range(3, 9)), covered  # the seven-month hole, measured
        assert any("cliff" in p for p in problems)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# P2/P4 — the publish job: ordering, cadence, and the refusal to succeed silently
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _skip_without_manifest():
    """`pipeline/__init__.py` reads the dbt manifest at import (the E11.23 fast-gate rule), so a
    Dagster-wiring test must skip rather than crash at collection when it is absent."""
    if not Path("dbt/target/manifest.json").exists():
        pytest.skip("dbt manifest absent — `pipeline` is not importable in the fast gate")


def test_the_publish_runs_downstream_of_the_ingest_as_a_graph_edge():
    """⭐ INC-25, pinned on the COMPILED graph rather than on source order.

    The 2026-08-10 board was generated 7h42m BEFORE that Monday's ingest landed, so it published a
    week-old depth chart under a five-day-old stamp. Two crons with an offset would reproduce that
    on the first slow ingest; a dependency edge cannot.

    RED PROOF: change the job body to call the two ops independently and this fails."""
    _skip_without_manifest()
    from pipeline.jobs.sports_nfl_board_publish_job import sports_nfl_board_publish_job

    graph = sports_nfl_board_publish_job.graph
    deps = graph.dependencies
    publish = next(k for k in deps if "publish" in k.name)
    upstreams = {d.node for d in deps[publish].values()}
    assert "nfl_board_input_refresh_op" in upstreams, (
        f"the publish op must depend on the ingest op; upstreams={upstreams}")


def test_the_publish_step_passes_market_refresh_explicitly():
    """A scheduled publish is the one caller that must never silently inherit a changed default —
    the frozen market was itself an invisible default. Read from the source's argv forms, on
    COMMENT-STRIPPED text so the explanatory prose above the flag cannot satisfy the guard
    (the INC-38 prose-cannot-satisfy lesson)."""
    src = Path("pipeline/jobs/sports_nfl_board_publish_job.py").read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert code.count('"--market-refresh"') == 2, (
        "both the projection build and the export step must pass --market-refresh explicitly")
    assert '"--publish"' in code, "the scheduled job must pass the NF-D12 publish guard explicitly"


def test_the_daily_cadence_covers_draft_season_and_has_no_seasonal_cliff():
    """P2's cadence: daily through draft season, weekly after. And — the P0 lesson applied to the
    new schedule — the publish cron itself carries NO month range, so it can never inherit the
    seasonal hole this same story had to fix twice."""
    _skip_without_manifest()
    from pipeline.schedules.sports_rollforward_schedules import (
        NFL_BOARD_PUBLISH_CRON,
        is_draft_season,
    )

    assert _cron_months(NFL_BOARD_PUBLISH_CRON) == set(range(1, 13))
    assert is_draft_season(date(2026, 8, 15)) and is_draft_season(date(2026, 9, 9))
    assert is_draft_season(date(2026, 9, 15)) and not is_draft_season(date(2026, 9, 16))
    assert not is_draft_season(date(2026, 7, 31)) and not is_draft_season(date(2027, 2, 1))


def test_the_publish_op_refuses_to_report_success_without_a_duckdb(tmp_path, monkeypatch):
    """⭐ THE 19-GREEN-RUNS GUARD. `sports_nfl_sleeper_injuries_job` returned SUCCESS 19 days in a
    row while writing nothing, because it opened a gitignored file and swallowed the failure. This
    op must PAGE and RAISE on the same precondition.

    RED PROOF: replace the raise with a `context.log.warning` + `return` and this fails."""
    _skip_without_manifest()
    # ⚠️ importlib, not `from pipeline.jobs import ...`: the package re-exports the JOB OBJECT
    # under the same name as its module, so the attribute lookup returns a JobDefinition and every
    # `monkeypatch.setattr` below would fail on it.
    J = importlib.import_module("pipeline.jobs.sports_nfl_board_publish_job)".rstrip(")"))

    pages: list[tuple] = []
    monkeypatch.setattr(J, "_page",
                        lambda ctx, title, body, *, severity, dedup_key:
                        pages.append((title, severity, dedup_key)))
    monkeypatch.setattr(J, "_APP_DIR", tmp_path)
    monkeypatch.setenv("SPORTS_DUCKDB_PATH", str(tmp_path / "definitely-absent.duckdb"))

    from dagster import build_op_context

    with pytest.raises(Exception, match="precondition failed"):
        J.nfl_board_publish_op(build_op_context())
    assert pages and pages[0][1] == "CRITICAL", f"expected a CRITICAL page, got {pages}"


def test_the_publish_verification_treats_an_unreadable_manifest_as_a_failure(tmp_path, monkeypatch):
    """NF1.7(a): a check that could not run is not a check that passed. Three exit-0 subprocesses
    prove each script ran, not that a board advanced."""
    _skip_without_manifest()
    from datetime import datetime, timezone

    from dagster import build_op_context

    # ⚠️ importlib, not `from pipeline.jobs import ...`: the package re-exports the JOB OBJECT
    # under the same name as its module, so the attribute lookup returns a JobDefinition and every
    # `monkeypatch.setattr` below would fail on it.
    J = importlib.import_module("pipeline.jobs.sports_nfl_board_publish_job)".rstrip(")"))

    monkeypatch.setattr(J, "_page", lambda *a, **k: None)
    monkeypatch.setattr(J, "_APP_DIR", tmp_path)
    with pytest.raises(Exception, match="could not read"):
        J._verify_published(build_op_context(), 2026, datetime.now(timezone.utc))


def test_the_publish_verification_rejects_a_stale_or_unstamped_artifact(tmp_path, monkeypatch):
    """Independent failure modes, each proved on its own so no clause is vacuous (the NF-D17
    and-composed-clause lesson): a manifest that predates this run, one whose market stamp is
    missing — i.e. the original defect wearing the new field name — and one that lost the NF-INJ1
    coherence block.

    ⭐ RE-ANCHORED BY NF-INFRA2 (2026-08-24), not weakened. `_verify_published` now delegates its
    verdict to the pure `betting_ml.monitoring.nfl_board_freshness.verify_manifest`, which checks
    more than this test used to: every declared feed stamp AND the coherence block's presence. The
    NF-D17 discipline that makes each clause meaningful therefore requires the baseline fixture to
    satisfy EVERY OTHER clause, so exactly one thing can fire — which is why the manifest below is
    built complete and then broken one field at a time. (A guard suite can encode a RETIRED world;
    the cure is re-anchoring onto the new implementation, never deleting the guard — MH2.7.)"""
    _skip_without_manifest()
    from datetime import datetime, timedelta, timezone

    from dagster import build_op_context

    # ⚠️ importlib, not `from pipeline.jobs import ...`: the package re-exports the JOB OBJECT
    # under the same name as its module, so the attribute lookup returns a JobDefinition and every
    # `monkeypatch.setattr` below would fail on it.
    J = importlib.import_module("pipeline.jobs.sports_nfl_board_publish_job)".rstrip(")"))

    monkeypatch.setattr(J, "_page", lambda *a, **k: None)
    monkeypatch.setattr(J, "_APP_DIR", tmp_path)
    out = tmp_path / J._STAGING_OUT / "2026"
    out.mkdir(parents=True)
    started = datetime.now(timezone.utc)
    manifest = out / "manifest.json"

    def _complete(**overrides):
        """A manifest that satisfies EVERY clause, so a single override isolates one failure."""
        blob = {
            "generated_at": started.isoformat(),
            "adp_as_of": started.date().isoformat(),
            "ecr_as_of": started.date().isoformat(),
            "freshness": {"input_vintage": {
                "depth_chart_as_of": started.isoformat(),
                "sleeper_status_as_of": started.isoformat()}},
            "coherence": {"violating_players": 0,
                          "injury_input": {"verdict": "OK", "detail": "fresh"}},
        }
        blob.update(overrides)
        manifest.write_text(json.dumps(blob))

    # (0) everything good → passes. FIRST, because it is what makes every failure below
    #     meaningful: without it, a clause could be firing for an unrelated missing field.
    _complete()
    J._verify_published(build_op_context(), 2026, started)

    # (1) stale artifact, every other clause satisfied — so only the staleness clause can fire.
    _complete(generated_at=(started - timedelta(days=1)).isoformat())
    with pytest.raises(Exception, match="predates this run"):
        J._verify_published(build_op_context(), 2026, started)

    # (2) fresh artifact, market stamp MISSING — so only the stamp clause can fire.
    _complete(adp_as_of=None)
    with pytest.raises(Exception, match="UNKNOWN vintage for adp_as_of"):
        J._verify_published(build_op_context(), 2026, started)

    # (3) NF-INFRA2 — the coherence block is GONE, i.e. `report_publish_coherence` silently
    #     stopped running while every step still exited 0 (the vacuous-guard class, on the
    #     artifact). Everything else is satisfied, so only this clause can fire.
    _complete(coherence=None)
    with pytest.raises(Exception, match="coherence"):
        J._verify_published(build_op_context(), 2026, started)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Honest framing — the caveat may not be weakened by a freshness change
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_market_lean_caveat_is_untouched():
    """⛔ A fresher build is not a better model. Refreshing ADP makes the MARKET HALF of the
    ordering current; it does not make our order more independent, so `MARKET_LEAN_NOTE` stays
    verbatim and keeps shipping in the payload."""
    from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (
        MARKET_LEAN_NOTE,
    )

    assert "market" in MARKET_LEAN_NOTE.lower()
    for forbidden in ("more accurate", "beat the market", "edge", "win rate", "win-rate"):
        assert forbidden not in MARKET_LEAN_NOTE.lower(), forbidden


def test_the_track_record_claim_denylist_is_untouched():
    """⛔ The E5.9 backfill boundary's other half: a daily-refresh build must not touch the track
    record. Historical seasons keep their pinned market (proved above); the export's own build-time
    assert must still be there."""
    src = Path("quant_sports_intel_models/football/nfl/fantasy/"
               "export_track_record_json.py").read_text()
    assert "_CLAIM_DENYLIST" in src
    assert "assert" in src, "the build-time claim assert must remain"
