"""NF-D5 — the box Dagster job for the Sleeper forward-availability feed (daily, year-round).

Continues NF-D2 slice 5 (the roster-status unavailability flag): nflverse's roster `status` lags to
camp, but Sleeper's free `v1/players/nfl` snapshot surfaces offseason PUP/IR/surgery designations as
they're reported. Three ops, chained:

  1. nfl_sleeper_injuries_ingest_op   — fetch Sleeper's player feed, resolve `player_id` (native
     gsis_id + the deterministic name/position crosswalk fallback), land to
     `nfl/raw/sleeper_injuries` (season-partitioned Delta overwrite). PAGES AND RAISES on a land
     that produced nothing or resolved almost nothing.
  2. nfl_sleeper_injuries_rebuild_op  — refresh JUST the `stg_nfl_sleeper_injuries` staging model
     so `load_forward_roster_status` sees today's snapshot. ALERT-continue: a failed rebuild means
     yesterday's (still-served) snapshot stays live one more cycle, which is survivable — but it
     pages, it does not merely log.
  3. nfl_sleeper_injuries_freshness_op — read the ARTIFACT's own `_delta_log` and page if it did
     not actually advance (INC-41). ALERT, never HALT.

🚨 WHY THIS JOB WAS REWRITTEN (NF-FRESH1, 2026-08-15 — read before loosening anything here):
it produced **19 consecutive daily SUCCESS runs while `nfl/raw/sleeper_injuries` held ONE 19-day-old
Delta commit**. The ingest op died at `duckdb.connect(read_only=True)` in ~114ms — the sports DuckDB
is gitignored, so it was absent from the `COPY . .` image and `/tmp` is wiped by every deploy — and
a bare `except Exception` turned that into a green run. Three separate things had to change:

  * ⛔ THE SWALLOW IS GONE. "Advisory, so never fail the run" was the reasoning, and it was wrong in
    a specific way: it conflated *the downstream consumer degrades gracefully* (true — the
    projection falls back to nflverse-only) with *nobody needs to know* (false). This job is
    standalone in its own namespace (sport_data_platform.md §16.3): raising fails ITS OWN run,
    blocks nothing MLB-serving, and leaves the previous snapshot serving from S3. A RED run that
    left the good snapshot alone is strictly better than a green run that wrote nothing. The run
    STATUS carried zero information for 19 days; now it carries the answer.
  * ⛔ A DEGRADED LAND IS REFUSED, NOT WRITTEN. The tempting shortcut — make the DuckDB optional
    and land Sleeper's native-`gsis_id` rows — was MEASURED in NF-FRESH1 and is strictly worse than
    today's break: native ids cover 16.7% of rostered / 22.1% of flagged players, so it would DROP
    95 of 122 flagged players (Waddle, Pacheco included), overwrite the good Delta partition, and
    report SUCCESS daily. `classify_land` refuses that write (the coverage floor's derivation is in
    `sleeper_injuries_source`).
  * ⭐ AND THE ARTIFACT IS CHECKED, NOT JUST THE OP. Both of the above are still producer-side; a
    producer that reports success and writes nothing is exactly what happened. Op 3 reads the
    commit timestamp out of the Delta transaction log itself (never an S3 mtime — INC-41).

ISOLATION (sport_data_platform.md §16.3): a standalone sports job in its own namespace — it fails
ITS OWN run on error and blocks nothing MLB-serving.

⚠️ DEPLOY PREREQUISITE (operator): the sports DuckDB must exist on the `sports_duckdb` named volume
(`SPORTS_DUCKDB_PATH`, in env.required) — materialize it once with `sports_nfl_dbt_build_job`. The
Sleeper fetch itself needs no credential (public, unauthenticated); S3 write is the instance role.
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

from betting_ml.utils.sports_duckdb import missing_duckdb_remedy, resolve_sports_duckdb
from pipeline.jobs.sports_dbt_job import _run_sports_dbt

# Cheap (one unauthenticated HTTP GET + a single-model dbt rebuild), but keep the finite-timeout
# discipline (INC-32): a Dagster op must never hang forever.
NFL_SLEEPER_INJURIES_TIMEOUT_SECONDS = int(os.environ.get("NFL_SLEEPER_INJURIES_TIMEOUT_SECONDS", "120"))

# The resolution floor below which the land is REFUSED (see `classify_land`). Overridable so the
# floor can be tightened once `pct_resolved` has been observed across real runs — it is deliberately
# loose today because nothing had ever measured the pre-drop rate.
NFL_SLEEPER_MIN_PCT_RESOLVED = float(os.environ.get("NFL_SLEEPER_MIN_PCT_RESOLVED", "50"))


def _page(context, title: str, body: str, *, severity: str, dedup_key: str) -> None:
    """Page, and mirror it into the step log. Distinct `dedup_key` per failure mode so one noisy
    leg cannot occupy another's 1-hour rate-limit slot (INC-39)."""
    from pipeline.utils.alerting import send_alert

    send_alert(title, body, severity=severity, dedup_key=dedup_key)
    context.log.warning("ALERT [nfl sleeper injuries] %s — %s", title, body)


@op(out=Out(Nothing))
def nfl_sleeper_injuries_ingest_op(context):
    """Land Sleeper's `v1/players/nfl` forward-availability snapshot.

    PAGES AND RAISES rather than reporting a green run that wrote nothing (see the module
    docstring). The precondition is checked FIRST so an absent sports DuckDB produces one legible
    sentence with a named remedy instead of a 114ms death nobody reads."""
    import duckdb

    from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI
    from quant_sports_intel_models.football.nfl.ingest import s3io
    from quant_sports_intel_models.football.nfl.ingest.sources import current_season

    season = current_season()
    duckdb_path = resolve_sports_duckdb()

    # ⭐ PRECONDITION FIRST — this exact absence is the NF-FRESH1 bug.
    if not duckdb_path.exists():
        msg = missing_duckdb_remedy(duckdb_path)
        _page(context, "NFL Sleeper injuries: sports DuckDB missing", msg,
              severity="CRITICAL", dedup_key="nfl_sleeper_injuries:no_duckdb")
        raise Exception(f"NFL Sleeper injuries ingest precondition failed — {msg}")

    try:
        con = duckdb.connect(str(duckdb_path), read_only=True)
        try:
            df, cov = SI.load_sleeper_injuries_with_coverage(
                con, season, timeout=NFL_SLEEPER_INJURIES_TIMEOUT_SECONDS)
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — paged AND re-raised; never swallowed
        _page(context, "NFL Sleeper injuries: fetch/crosswalk FAILED",
              f"season={season} duckdb={duckdb_path}: {type(exc).__name__}: {exc}\n\n"
              "NOTHING WAS LANDED THIS CYCLE — the previous Delta commit is still being served, "
              "so the projection is not down; it is just not advancing.",
              severity="CRITICAL", dedup_key="nfl_sleeper_injuries:fetch_failed")
        raise

    verdict = SI.classify_land(cov, min_pct_resolved=NFL_SLEEPER_MIN_PCT_RESOLVED)
    context.log.info("[nfl sleeper] season=%s coverage=%s verdict=%s",
                     season, cov, verdict["verdict"])

    # ⛔ Refuse the write BEFORE it happens: the Delta write is a whole-PARTITION overwrite, so a
    # degraded frame does not sit beside the good snapshot — it replaces it.
    if not verdict["should_write"]:
        body = (f"season={season} verdict={verdict['verdict']}\n\n{verdict['reason']}\n\n"
                f"coverage={cov}\n\nThe write was REFUSED, so the previous good snapshot is intact.")
        _page(context, f"NFL Sleeper injuries: land REFUSED ({verdict['verdict']})", body,
              severity=verdict["severity"] or "CRITICAL",
              dedup_key=f"nfl_sleeper_injuries:refused:{verdict['verdict']}")
        raise Exception(f"NFL Sleeper injuries land refused ({verdict['verdict']}): "
                        f"{verdict['reason']}")

    n = s3io.write_dataframe(df, sport="nfl", source="sleeper_injuries", season=int(season),
                             tier="raw")
    if not n:
        # write_dataframe skips an empty slice (returns 0) — a green op over an unwritten table is
        # the entire NF-FRESH1 failure mode, so it is an error here, not a log line.
        _page(context, "NFL Sleeper injuries: the write landed ZERO rows",
              f"season={season} coverage={cov}\n\n`s3io.write_dataframe` reported 0 rows written "
              "even though the land verdict passed — the Delta partition did NOT advance.",
              severity="CRITICAL", dedup_key="nfl_sleeper_injuries:wrote_nothing")
        raise Exception(f"NFL Sleeper injuries wrote 0 rows for season {season}")

    # A PARTIAL land is written and REPORTS ITS MAGNITUDE, rather than passing silently.
    if verdict["severity"]:
        _page(context, f"NFL Sleeper injuries: {verdict['verdict']} land",
              f"season={season}: {verdict['reason']}\n\ncoverage={cov}\n\n"
              f"{n} rows were still written — this is a quality warning, not an outage.",
              severity=verdict["severity"],
              dedup_key=f"nfl_sleeper_injuries:partial:{verdict['verdict']}")

    context.log.info(
        "NFL Sleeper injuries: landed %d rows for season=%s (%s of %s fetched resolved; "
        "%d flagged: %s)",
        n, season, cov["n_resolved"], cov["n_fetched"], cov["n_flagged"],
        cov.get("by_injury_status"))


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_sleeper_injuries_rebuild_op(context):
    """ALERT-continue — refresh just `stg_nfl_sleeper_injuries` (a single cheap model) so
    `load_forward_roster_status` sees today's snapshot.

    Continues on failure BECAUSE the land above already succeeded and is durable: the fresh snapshot
    is in the lake and the next cycle's rebuild picks it up, so failing the run here would discard a
    good capture over a downstream refresh. It PAGES though — E11.30's finding is that an
    "ALERT-tier" op which only reaches `context.log.warning` has detection without notification."""
    result = _run_sports_dbt(
        context, ["run", "--select", "stg_nfl_sleeper_injuries", "--threads", "1"],
        "stg_nfl_sleeper_injuries")
    if result.returncode != 0:
        _page(context, "NFL Sleeper injuries: staging rebuild FAILED",
              f"`dbt run --select stg_nfl_sleeper_injuries` exited {result.returncode}. Today's "
              "snapshot IS landed in the lake, but the projection keeps reading the previously "
              "built staging model until this rebuild succeeds.\n\n"
              f"stderr tail:\n{(result.stderr or '')[-1500:]}",
              severity="ERROR", dedup_key="nfl_sleeper_injuries:rebuild_failed")
    else:
        context.log.info("stg_nfl_sleeper_injuries rebuilt — today's Sleeper snapshot is live.")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_sleeper_injuries_freshness_op(context):
    """ALERT (never HALT) — INC-41: assert the ARTIFACT advanced, by reading the commit timestamp
    out of the Delta transaction log.

    ⭐ This is the check that would have caught NF-FRESH1 on DAY ONE. Everything else in this job
    watches the PRODUCER, and the producer reported success for 19 days; only the landed data
    disagreed. It is a terminal leaf that never raises — by the time it runs the snapshot is already
    written, so failing the run would add nothing and only obscure a successful capture."""
    from betting_ml.monitoring import sports_delta_freshness as SDF

    contract = SDF.by_name("nfl_sleeper_injuries")
    reading = SDF.read_contract(contract)
    verdict = SDF.classify(contract, reading)
    context.log.info("[METRIC] sleeper_injuries_freshness=%s lag_hours=%s version=%s",
                     verdict["verdict"], verdict["lag_hours"], reading.version)
    if not SDF.is_problem(verdict):
        context.log.info("[nfl sleeper] artifact freshness OK — %s", verdict["detail"])
        return
    _page(context, f"NFL Sleeper injuries artifact {verdict['verdict']}",
          f"{verdict['detail']}\n\ncadence: {contract.cadence}",
          severity=verdict["severity"] or "WARN",
          dedup_key=f"nfl_sleeper_injuries:freshness:{verdict['verdict']}")


@job(executor_def=in_process_executor)
def sports_nfl_sleeper_injuries_job():
    """Daily Sleeper forward-availability capture → refresh the staging model → assert the artifact
    actually advanced. The ingest fails loud; the rebuild and the freshness check page and continue."""
    landed = nfl_sleeper_injuries_ingest_op()
    nfl_sleeper_injuries_freshness_op(start=nfl_sleeper_injuries_rebuild_op(start=landed))
