"""NF-FRESH2 P2/P4 — the NFL draft-board REFRESH-AND-PUBLISH job.

Before this job the served board was a **static, hand-published S3 blob**: nothing in Dagster,
cron or CI rebuilt it. A user drafting today read a snapshot whose market inputs were ~3 weeks old
and whose depth-chart view was ~12 days old, under a UI stamp that said "built 5 days ago"
(NF-FRESH1 F1/§1.1). This job is the cadence.

  1. `nfl_board_input_refresh_op`  (P4) — a DAILY depth-chart/roster ingest slice + the NFL mart
     rebuild that makes it readable. ESPN publishes depth charts daily and we landed them weekly,
     and the depth chart is the most-decayed model input on the board — unlike ADP it decays into
     the PROJECTION (expected games, the mover-opportunity rescale, `depth_rank` itself), not just
     into a reference column.
  2. `nfl_board_publish_op`        (P2) — refresh the market, rebuild the NF1.5 projection, rebuild
     the 14 league boards, export and publish, then VERIFY the artifact it just shipped.

⭐ THE ORDERING IS THE WHOLE POINT, AND IT IS A GRAPH EDGE, NOT A CRON OFFSET (INC-25). Step 2
consumes exactly what step 1 lands, in the same run. The bug this prevents is measured, not
hypothetical: the 2026-08-10 board was generated at 05:33Z and that Monday's ingest did not commit
until 13:15Z, so the published board served the 08-03 snapshot — 7h42m too early, every week,
invisibly. Two schedules with a cron offset would re-create that race on the first slow ingest;
an edge cannot.

⚖️ TIER — "loud, but it can never blank the product", which needs stating precisely because the
two halves pull in opposite directions:
  * It can never HALT anything else. This is a standalone sports job in its own namespace
    (sport_data_platform.md §16.3): a failure fails ITS OWN run, blocks nothing MLB-serving, and
    leaves the PREVIOUS board serving from S3 untouched. A missed refresh costs freshness; it
    never costs availability.
  * ⛔ It must NEVER report SUCCESS while publishing nothing. That is not a hypothetical either —
    it is precisely how `sports_nfl_sleeper_injuries_job` produced **19 consecutive green runs
    against one 19-day-old Delta commit** (NF-FRESH1): a WARN-tier op opened a gitignored,
    deploy-ephemeral file, died in 114ms, and its bare `except` returned SUCCESS. So the ingest
    step is ALERT-continue (a stale depth chart is survivable, and the published `input_vintage`
    stamp SAYS it is stale), while the publish step PAGES AND RAISES: a red run that leaves the
    good board serving is strictly better than a green run that shipped nothing.

🚦 PRECONDITION (and it is the likely first failure on the box): the whole build chain reads the
sports DuckDB, which is **gitignored and therefore absent from the `COPY . .` image**. The publish
op checks for it FIRST and fails with a named remedy rather than dying opaquely three subprocesses
later. Until `sports_nfl_dbt_build_job` has materialized it on the box, this job pages on every
fire — which is the correct, visible behaviour, and the exact opposite of the 19-green-runs class.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dagster import In, Nothing, Out, in_process_executor, job, op

from betting_ml.utils.sports_duckdb import (
    missing_duckdb_remedy,
    sports_duckdb_env,
    sports_duckdb_path,
)
from pipeline.jobs.sports_dbt_job import _run_sports_dbt

# ── P4: the DAILY slice of the roll-forward ────────────────────────────────────────────────────
# NOT the full `ROLL_FORWARD_SOURCES`. These three are the feeds whose content genuinely changes
# day to day during camp and the season (role, roster, team). `schedules` / `nflverse_draft_picks`
# / `nflverse_combine` are effectively static once published and stay on the weekly cadence, and
# `injuries` is in-season-only upstream — it is left to the weekly roll-forward (now that P0 has
# widened that window to reach September at all, it will finally start landing).
BOARD_INPUT_SOURCES = ["depth_charts", "rosters", "weekly_rosters"]

# INC-32 — every subprocess on a Dagster path carries a finite timeout. The projection rebuild is
# the long pole (a full NF1.5 build over the training pool), so it gets its own generous ceiling.
NFL_BOARD_INGEST_TIMEOUT_SECONDS = int(
    os.environ.get("NFL_BOARD_INGEST_TIMEOUT_SECONDS", "600"))
NFL_BOARD_BUILD_TIMEOUT_SECONDS = int(
    os.environ.get("NFL_BOARD_BUILD_TIMEOUT_SECONDS", "3600"))
NFL_BOARD_EXPORT_TIMEOUT_SECONDS = int(
    os.environ.get("NFL_BOARD_EXPORT_TIMEOUT_SECONDS", "900"))

# The api-cache bucket the gated `/fantasy/nfl/*` routes read. Overridable so a soak can publish to
# a scratch bucket, but it is NOT defaulted to empty: `export_draft_board_json --publish` with no
# bucket is a HARD ERROR by design (the NF1.7 silent-no-publish lesson), and we want that error.
NFL_BOARD_CACHE_BUCKET = os.environ.get("CACHE_BUCKET", "credence-prod-s3-api-cache")

_APP_DIR = Path(os.environ.get("APP_DIR", "/app"))
_FANTASY = "quant_sports_intel_models.football.nfl.fantasy"
_STAGING_OUT = "quant_sports_intel_models/football/nfl/fantasy/artifacts/draft_board_json"


def _page(context, title: str, body: str, *, severity: str, dedup_key: str) -> None:
    """Page, and mirror it into the step log. Distinct `dedup_key` per failure mode so one noisy
    leg cannot occupy another's 1-hour rate-limit slot (INC-39)."""
    from pipeline.utils.alerting import send_alert

    send_alert(title, body, severity=severity, dedup_key=dedup_key)
    context.log.warning("ALERT [nfl board publish] %s — %s", title, body)


def _sports_duckdb_path() -> str:
    """⚠️ ONE reader, ONE default — now enforced repo-wide.

    When this job shipped, four owners each carried their own default (`sports_dbt/sports.duckdb`,
    `/tmp/sports_ncaaf.duckdb`, `/tmp/sports_nfl.duckdb`, `profiles.yml`'s own) — the "one path,
    many owners, none authoritative" shape that let the Sleeper op die silently. NF-INFRA1 collapsed
    all of them onto `betting_ml.utils.sports_duckdb`, so this is now a thin alias kept only because
    the module's own call sites and its guard test read it."""
    return sports_duckdb_path()


def _run(context, args: list[str], label: str, timeout: int) -> subprocess.CompletedProcess:
    """Run one build-chain step as a subprocess, with a finite timeout (INC-32).

    Subprocess rather than an in-process import on purpose: these scripts pull the whole modelling
    stack (pandas/sklearn/lightgbm/Optuna), and importing that into the Dagster code-location
    process would put it on every op's import path in this container."""
    cmd = [sys.executable, "-m", *args]
    context.log.info("[nfl board] %s: %s", label, " ".join(cmd))
    # `sports_duckdb_env()` pins the RESOLVED ABSOLUTE path, so the op and the subprocess can never
    # bind a relative default to different files (NF-INFRA1's single-owner contract).
    env = {**sports_duckdb_env(),
           "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2")}
    try:
        proc = subprocess.run(cmd, cwd=str(_APP_DIR), env=env, timeout=timeout,
                              capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        # ⛔ Never `|| echo 0`-style swallowing: an unreachable step must be distinguishable from a
        # clean one (INC-32/INC-36). A timeout is returned as a real non-zero result.
        context.log.warning("[nfl board] %s TIMED OUT after %ss", label, timeout)
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr="timeout")
    for line in (proc.stdout or "").splitlines()[-60:]:
        context.log.info("[%s] %s", label, line)
    if proc.returncode != 0:
        for line in (proc.stderr or "").splitlines()[-60:]:
            context.log.warning("[%s:stderr] %s", label, line)
    return proc


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. P4 — the daily depth-chart / roster ingest (ALERT-continue)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@op(out=Out(Nothing))
def nfl_board_input_refresh_op(context):
    """ALERT-continue — land today's depth charts / rosters, then rebuild the NFL marts.

    Continues on failure BECAUSE the market half of this job is independently valuable and is the
    launch-critical fix; publishing on yesterday's depth chart is a real, bounded degradation and
    the published `input_vintage` stamp reports it honestly rather than hiding it. What it must not
    do is fail silently — every branch here pages."""
    from quant_sports_intel_models.football.nfl.ingest.roll_forward import run_roll_forward
    from quant_sports_intel_models.football.nfl.ingest.sources import current_season

    season = current_season()
    context.log.info("[nfl board] input refresh: season=%s sources=%s", season, BOARD_INPUT_SOURCES)
    try:
        manifest = run_roll_forward(season, sources=BOARD_INPUT_SOURCES)
    except Exception as exc:  # noqa: BLE001 — ALERT-continue (see the op docstring)
        _page(context, "NFL board: daily input ingest failed",
              f"`run_roll_forward({season}, sources={BOARD_INPUT_SOURCES})` raised: {exc}\n\n"
              "The board will still publish, on the PREVIOUS depth-chart/roster snapshot. The "
              "served payload's `freshness.input_vintage.depth_chart_as_of` will show that older "
              "date, so the staleness is visible rather than inferred.",
              severity="ERROR", dedup_key="nfl_board_publish:input_ingest")
        return

    keyed = {k: v for k, v in manifest.items() if not k.startswith("_")}
    landed = [k for k, v in keyed.items() if isinstance(v, int) and v > 0]
    bad = [k for k, v in keyed.items() if not (isinstance(v, int) and v > 0)]
    if not landed:
        # Every source empty/errored is the "op succeeded, wrote nothing" signature — page on it.
        _page(context, "NFL board: daily input ingest landed NOTHING",
              f"season={season} sources={BOARD_INPUT_SOURCES} manifest={keyed}\n\n"
              "Zero rows across every source is an outage signature, not a quiet day — these three "
              "feeds are published continuously. Publishing continues on the previous snapshot.",
              severity="ERROR", dedup_key="nfl_board_publish:input_empty")
    elif bad:
        context.log.warning("⚠️ [nfl board] %d of %d input source(s) did not land: %s",
                            len(bad), len(keyed), sorted(bad))
    context.log.info("[nfl board] input refresh landed: %s", {k: keyed[k] for k in landed})

    # Make the fresh rows readable by the board build. Serial staging then marts, mirroring
    # `nfl_roll_forward_rebuild_op` — but ALERT-continue here rather than HALT, for the same reason
    # the ingest is: an unpublished board helps nobody, and the vintage stamp tells the truth.
    for select, label in (("nfl.staging", "nfl.staging (serial)"), ("nfl.marts", "nfl.marts")):
        result = _run_sports_dbt(context, ["run", "--select", select, "--threads", "1"], label)
        if result.returncode != 0:
            _page(context, f"NFL board: {label} rebuild failed",
                  f"exit {result.returncode}. The board will publish on the previously-built "
                  "marts; `freshness.input_vintage` will show the older depth-chart date.",
                  severity="ERROR", dedup_key=f"nfl_board_publish:rebuild:{select}")
            return


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. P2 — refresh the market, rebuild, export, publish, VERIFY (pages AND raises)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_board_publish_op(context):
    """Rebuild the NF1.5 projection with a REFRESHED market, re-export the 14 boards, publish, and
    verify the artifact that was actually shipped.

    Pages and RAISES on failure. Raising fails only this standalone run — the previously published
    board keeps serving from S3 — and it is what makes "published nothing" impossible to mistake
    for "published fine" (the NF-FRESH1 19-green-runs lesson)."""
    from quant_sports_intel_models.football.nfl.ingest.sources import current_season

    started = datetime.now(timezone.utc)
    season = current_season()
    duckdb_path = Path(_sports_duckdb_path())
    resolved = duckdb_path if duckdb_path.is_absolute() else (_APP_DIR / duckdb_path)

    # ⭐ PRECONDITION FIRST, with a named remedy. `*.duckdb` is gitignored, so it is absent from the
    # deployed image until `sports_nfl_dbt_build_job` has run on this box. Checking here turns an
    # opaque death three subprocesses deep into one legible sentence.
    if not resolved.exists():
        msg = missing_duckdb_remedy(resolved)
        _page(context, "NFL board publish: sports DuckDB missing", msg,
              severity="CRITICAL", dedup_key="nfl_board_publish:no_duckdb")
        raise Exception(f"NFL board publish precondition failed — {msg}")

    steps = (
        # ⭐ `--market-refresh` is the default, but it is passed EXPLICITLY here. A scheduled
        # publish is the one caller that must never silently inherit a changed default — this is
        # the whole reason the job exists, so it states it (and the guard test reads this list).
        (f"{_FANTASY}.run_nf1_5", ["--mode", "build", "--market-refresh",
                                   "--duckdb", str(resolved)],
         "nf1_5 build", NFL_BOARD_BUILD_TIMEOUT_SECONDS),
        # ⚠️ `run_league_board` takes NO `--duckdb`: it opens the lake itself and reads the NF1.5
        # projection from the local artifact the step above just wrote. `--projection-season` is
        # passed explicitly so a clock-derived season and a script default can never diverge.
        (f"{_FANTASY}.run_league_board", ["--projection-season", str(season)],
         "league boards", NFL_BOARD_BUILD_TIMEOUT_SECONDS),
        (f"{_FANTASY}.export_draft_board_json",
         ["--season", str(season), "--market-refresh",
          "--s3-bucket", NFL_BOARD_CACHE_BUCKET, "--publish"],
         "export + publish", NFL_BOARD_EXPORT_TIMEOUT_SECONDS),
    )
    for module, argv, label, timeout in steps:
        proc = _run(context, [module, *argv], label, timeout)
        if proc.returncode != 0:
            body = (f"step `{label}` exited {proc.returncode}.\n\n"
                    "NOTHING WAS PUBLISHED THIS CYCLE — the previously published board is still "
                    "being served, so the product is not down; it is just not advancing.\n"
                    f"stderr tail:\n{(proc.stderr or '')[-1500:]}")
            _page(context, f"NFL board publish FAILED at {label}", body,
                  severity="CRITICAL", dedup_key=f"nfl_board_publish:step:{label}")
            raise Exception(f"NFL board publish failed at {label} (exit {proc.returncode})")

    _verify_published(context, season, started)
    context.log.info("[nfl board] publish complete for season %s", season)


def _verify_published(context, season: int, started: datetime) -> None:
    """Read back the manifest this run staged and assert it is THIS run's, and that it carries the
    market stamp.

    ⭐ VERIFY THE ARTIFACT, NOT THE EXIT CODE. Three exit-0 steps prove each script ran; they do not
    prove a board advanced. Two checks, each of which fails for a distinct real reason:
      * `generated_at >= this run's start` — an exporter that silently reused a staged directory,
        or a publish that ran against yesterday's export, cannot pass this.
      * `adp_as_of` present — the whole P1 chain (refresh → cache write → as-of read → payload)
        held. A null here means the board published with an unknown market vintage, which is the
        original defect wearing a new stamp.
    ⛔ An UNREADABLE manifest is a FAILURE, never a pass (NF1.7(a) — a check that could not run is
    not a check that succeeded)."""
    path = _APP_DIR / _STAGING_OUT / str(season) / "manifest.json"
    try:
        blob = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        _page(context, "NFL board publish: cannot verify what was published",
              f"could not read {path} ({type(exc).__name__}: {exc}). The publish steps exited 0, "
              "so something may well have shipped — but this run cannot prove it, and an "
              "unverifiable publish is reported as a failure, never as a pass.",
              severity="CRITICAL", dedup_key="nfl_board_publish:verify_unreadable")
        raise Exception(f"NFL board publish verification could not read {path}: {exc}") from exc

    problems: list[str] = []
    raw = blob.get("generated_at")
    try:
        # A tiny tolerance absorbs clock skew between the op and the subprocess, nothing more.
        if datetime.fromisoformat(str(raw)) < started - timedelta(minutes=2):
            problems.append(f"manifest.generated_at={raw} predates this run ({started.isoformat()})"
                            " — a STALE artifact was published")
    except Exception:  # noqa: BLE001
        problems.append(f"manifest.generated_at is unparseable ({raw!r})")
    if not blob.get("adp_as_of"):
        problems.append("manifest.adp_as_of is missing/null — the board shipped with an UNKNOWN "
                        "market vintage (the NF-FRESH2 P1 chain did not hold)")

    if problems:
        _page(context, "NFL board publish: the published artifact failed verification",
              "\n".join(f"- {p}" for p in problems),
              severity="CRITICAL", dedup_key="nfl_board_publish:verify_failed")
        raise Exception("NFL board publish verification failed: " + "; ".join(problems))
    context.log.info("[nfl board] verified: generated_at=%s adp_as_of=%s ecr_as_of=%s",
                     raw, blob.get("adp_as_of"), blob.get("ecr_as_of"))


@job(executor_def=in_process_executor)
def sports_nfl_board_publish_job():
    """Daily/weekly draft-board refresh: ingest today's depth charts/rosters → rebuild the marts →
    refresh the market → rebuild + export + publish the board → verify what shipped."""
    nfl_board_publish_op(start=nfl_board_input_refresh_op())
