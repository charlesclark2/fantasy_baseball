"""NCAAF-PS — the box Dagster job for the weekly PRE-KICKOFF prediction snapshot.

Runs the SERVED P1.4 game model over the upcoming FBS-vs-FBS slate and appends one immutable row
per (game_id, snapshot_ts) to `ncaaf/derived/game_prediction_snapshots`, then fans out to a weekly
snapshot of the P1.5 futures board. Three ops:

  1. ncaaf_prediction_snapshot_op   — the per-game snapshot. The PRIMARY deliverable.
  2. ncaaf_futures_snapshot_op      — the P1.5 futures board, snapshotted (the cheap fan-out).
  3. ncaaf_ratings_freshness_op     — NCAAF-P1.2W: an UNBOUND ALERT leaf asserting the strength
     ratings this snapshot is computed FROM are still advancing. It rides here rather than in the
     re-fit job because a monitor hosted inside its own subject cannot see its subject stop.

⏰ WHY A MISSED RUN IS NOT RECOVERABLE — and what that means for the tiers.
A pre-kickoff prediction can only be written BEFORE kickoff. Unlike the P0.6b odds catch-up (whose
whole design is "the next fire picks up whatever piled up"), there is no catching up here: once a
game has started, the row that would have proved what we said in advance can never be written, and
a backtest is not a substitute. So op 1 RAISES on failure — a failed run is visible in the Dagit
run list and the operator can re-fire it while the games are still ahead. A silent success over a
frozen input is the failure mode this job most needs to avoid (the NF-FRESH1 "19 green runs" class).

⭐ "NO UPCOMING GAMES" IS A NO-OP, NOT A FAILURE — and the two are reported DISTINCTLY. An off-week
or a fire before the opener legitimately writes nothing; a lake we could not read must never look
the same (INC-38). `run_snapshot` returns `status="no_games"` for the first and raises for the
second.

Op 2 is an ALERT-loud-but-continue fan-out LEAF: the futures board is a bonus track record, and a
season-simulation failure must never be the reason the per-game snapshot's run goes red. It is
ordered AFTER op 1 so the deadline-critical work never waits on it.

🖥️ NO BOX PREREQUISITES BEYOND AWS. This job is lake-only: it reads the raw `games` Delta and the
derived `team_strength_week` Delta over S3, and the only local files it touches are the two
COMMITTED served artifacts (`ncaaf_game_distribution_v2.json`, `ncaaf_game_mean_v2.json`). It
deliberately does NOT read `sports.duckdb` or the strength/matrix parquet — those are gitignored,
so they are absent from the `COPY . .` image and deploy-ephemeral everywhere else (NF-INFRA1), and
an op that quietly depends on one is how a schedule runs green for 19 days over a frozen table.
No CFBD key, no Odds-API key, no credits.

⚠️ THE ONE QUALITY PREREQUISITE — ⭐ NO LONGER AN OPERATOR STEP as of NCAAF-P1.2W (2026-09-13):
`sports_ncaaf_strength_refit_schedule` now re-fits P1.2 WEEKLY, Monday 07:30 PT, upstream of this
Tuesday snapshot in time — so each week's immutable rows are computed off a posterior that has
absorbed the weekend just played, which is what this job always needed and never had. The season's
FIRST re-fit was still the operator's — ✅ DONE 2026-08-18, and worth recording WHAT it fixed, because the cold start's real defect was not the one
the P0.7 note described. Until the re-fit, the strength mart's covariates were all-zero, which does
not mis-ORDER the board so much as COMPRESS it toward the mean: Ohio State was +19.7 over Ball State
and P(home win) spanned only 0.356-0.883. With the covariates populated the same slate reads +40.4
and 0.117-0.992 — realistic talent separation. (Indiana still leads the strength board afterwards,
so "Indiana leads" was never the cold-start tell; compression was.) A snapshot is immutable by
design, so the re-fit had to land first.

⭐ AND THE RE-FIT IS NOT ONE COMMAND. P1.2 reads its covariates from the sports DuckDB MARTS, not
from the lake — so `run_team_strength` against stale marts silently reproduces the cold start and
looks successful (it did, once). The marts must be rebuilt from the fresh lake FIRST. That chain,
and the verification that distinguishes "it ran" from "it worked", is now the weekly job's graph
rather than a runbook a human follows: `sports_ncaaf_strength_refit_job` rebuilds the marts INSIDE
the run and FAILS loudly on a cold-start reproduction. See the NCAAF-PS report's operator section
for the hand-run form, and `docs/ncaaf_p1_2w_weekly_strength_refit.md` for the scheduled one.
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

from pipeline.jobs.sports_ncaaf_serving_write_job import (
    ncaaf_serving_write_after_snapshot_op,
)

#: how far ahead a snapshot reaches, in days. 7 matches the weekly cadence: every FBS kickoff is
#: inside exactly one fire's window, and a game still ahead on the next fire is simply snapshotted
#: again under a fresh `snapshot_ts` (append-only — a second vintage is information, not a dupe).
SNAPSHOT_HORIZON_DAYS = float(os.environ.get("NCAAF_SNAPSHOT_HORIZON_DAYS", "7"))

#: the K−buffer. A game kicking off within this many minutes is skipped rather than raced — the
#: leakage gate would refuse it at the write boundary anyway, and refusing the whole write for one
#: game that started mid-run would cost the entire slate.
SNAPSHOT_MIN_LEAD_MINUTES = float(os.environ.get("NCAAF_SNAPSHOT_MIN_LEAD_MINUTES", "15"))

SNAPSHOT_N_DRAWS = int(os.environ.get("NCAAF_SNAPSHOT_N_DRAWS", "20000"))
FUTURES_N_SIMS = int(os.environ.get("NCAAF_FUTURES_N_SIMS", "10000"))


@op(out=Out(Nothing))
def ncaaf_prediction_snapshot_op(context):
    """The weekly pre-kickoff per-game snapshot (RAISES on failure — see the module docstring)."""
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season
    from quant_sports_intel_models.football.ncaaf.models.run_game_prediction_snapshot import (
        run_snapshot,
    )

    season = current_season()
    context.log.info(
        "NCAAF prediction snapshot: season=%s (clock-derived) horizon=%.1fd min_lead=%.0fmin",
        season, SNAPSHOT_HORIZON_DAYS, SNAPSHOT_MIN_LEAD_MINUTES)

    manifest = run_snapshot(
        season, horizon_days=SNAPSHOT_HORIZON_DAYS,
        min_lead_minutes=SNAPSHOT_MIN_LEAD_MINUTES, n_draws=SNAPSHOT_N_DRAWS,
        to_s3=True, futures=False)

    if manifest.get("status") == "no_games":
        context.log.info(
            "NCAAF prediction snapshot: NO upcoming FBS-vs-FBS kickoff inside the next %.1f day(s) "
            "for season %s — a genuine no-op (off-week / pre-opener), NOT a failure. Nothing "
            "written; the next fire picks up whatever has entered the window.",
            SNAPSHOT_HORIZON_DAYS, season)
        return

    context.log.info(
        "NCAAF prediction snapshot: wrote %s pre-kickoff row(s) for season %s at %s "
        "(strength vintage as_of_week=%s, model %s/%s). Earliest kickoff is %.0f min out; "
        "P(home win) spans %.3f-%.3f; median 80%% intervals margin %.1f / total %.1f pts. "
        "pace_term_active=%s. best_alpha=0 — a market-blind projection, no pick or edge claim.",
        manifest.get("rows_written"), season, manifest.get("snapshot_ts"),
        manifest.get("strength_as_of_week"), manifest.get("model_version"),
        manifest.get("model_contract"), manifest.get("min_lead_minutes", float("nan")),
        manifest.get("p_home_win_min", float("nan")), manifest.get("p_home_win_max", float("nan")),
        manifest.get("median_margin_interval_width", float("nan")),
        manifest.get("median_total_interval_width", float("nan")),
        manifest.get("pace_term_active"))


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ncaaf_futures_snapshot_op(context):
    """The weekly P1.5 futures-board snapshot — an ALERT-loud-but-continue fan-out LEAF.

    Nothing depends on it, and it must never turn the per-game snapshot's run red: that snapshot is
    the deadline-critical, non-recoverable one. It runs AFTER it for exactly that reason.
    """
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season
    from quant_sports_intel_models.football.ncaaf.models.run_game_prediction_snapshot import (
        run_futures_only,
    )

    season = current_season()
    try:
        manifest = run_futures_only(season, to_s3=True, n_sims=FUTURES_N_SIMS)
    except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (E11.7); a bonus track record
        context.log.warning(
            "[ALERT] NCAAF futures-board snapshot FAILED for season=%s: %s — the PER-GAME snapshot "
            "is unaffected (it already ran and wrote). The futures track record simply misses this "
            "week; the next fire resumes it.", season, exc)
        return
    f = manifest.get("futures") or {}
    context.log.info(
        "NCAAF futures snapshot: %s team(s) over %s sims for season %s at %s (strength vintage "
        "as_of_week=%s). Championship + conference-title PROBABILITIES only; best_alpha=0.",
        f.get("n_teams"), f.get("n_sims"), season, manifest.get("snapshot_ts"),
        manifest.get("strength_as_of_week"))


@op(out=Out(Nothing))
def ncaaf_ratings_freshness_op(context):
    """ALERT (never HALT) — NCAAF-P1.2W: assert the STRENGTH RATINGS are still advancing.

    ⭐ WHY IT LIVES HERE RATHER THAN IN `sports_ncaaf_strength_refit_job`. That job verifies the
    artifact it just wrote, and that check is structurally incapable of catching this failure,
    because it only runs when the job runs. The event this op exists to detect is the weekly re-fit
    NOT RUNNING — a schedule reverted to STOPPED by a Dagster-volume reset, a code location that
    failed to load, a stalled daemon. In all of those there is no run, so there is no verification,
    no failed run, and the last run in Dagit is a genuine green one; the ratings silently freeze at
    whatever week they reached and every producer-side instrument stays quiet. A monitor hosted
    inside its own subject cannot see its subject stop (the NF-INFRA2 reading).

    ⭐ AND THIS IS THE RIGHT HOST, not merely a different one. The snapshot this job writes is
    IMMUTABLE: one row per `(game_id, snapshot_ts)`, never rewritten. A snapshot taken off a frozen
    prior is a forward track record that permanently records a stale model — so the moment this
    fact matters most is exactly the moment this job runs, beside the `strength_as_of_week` the
    snapshot op already logs. It is also weekly, which matches a weekly artifact: `send_alert`'s
    rate limit is PER PROCESS and each Dagster run is its own process, so hanging this off the
    hourly serving write would mean twenty-four real emails a day while the ratings were stale.

    ⭐ DELIBERATELY INDEPENDENT — no `ins`, so it is NOT downstream of the snapshot op. That op
    RAISES by design (a missed pre-kickoff row can never be written later), and hanging this
    monitor off it would mean a snapshot outage BLINDS the ratings monitor on exactly the days
    something is already wrong. Two unrelated failures must not share a fate.

    Terminal and never raises: by the time it runs it has only read S3, and failing this run would
    add nothing while obscuring a successful — deadline-critical — snapshot.
    """
    from betting_ml.monitoring import sports_delta_freshness as SDF

    contract = SDF.by_name("ncaaf_team_strength_week")
    reading = SDF.read_contract(contract)
    verdict = SDF.classify(contract, reading)
    context.log.info(
        "[METRIC] ncaaf_ratings_freshness=%s lag_hours=%s version=%s",
        verdict["verdict"], verdict["lag_hours"], reading.version)
    if not SDF.is_problem(verdict):
        context.log.info("[ncaaf ratings sla] artifact freshness OK — %s", verdict["detail"])
        return
    from pipeline.utils.alerting import send_alert

    body = (f"{verdict['detail']}\n\ncadence: {contract.cadence}\n\n"
            f"⚠️ The served 'ratings as of' stamp on every NCAAF surface now shows this vintage, "
            f"and the 'next update' half PROMISES the cadence above — a freeze turns that stated "
            f"date into an overclaim, which is the one thing NCAAF-P3.3b's stamp was built not to "
            f"do.")
    send_alert(f"NCAAF strength ratings {verdict['verdict']}", body,
               severity=verdict["severity"] or "WARN",
               dedup_key=f"ncaaf_team_strength_week:freshness:{verdict['verdict']}")
    context.log.warning("ALERT [ncaaf ratings sla] %s — %s", verdict["verdict"], body)


@job(executor_def=in_process_executor)
def sports_ncaaf_prediction_snapshot_job():
    """Weekly pre-kickoff per-game predictions → the lake, the futures-board snapshot, then the
    serving-store publish.

    ⭐ NCAAF-P3.1 CHAINS THE SERVING WRITE HERE ON PURPOSE (INC-25). The serving store is a
    CONSUMER of the two tables the ops above write; a publish that only ran on its own daily
    schedule would, on the morning the week's snapshot lands, still be serving LAST week's vintage
    until its next fire. Making it a downstream op means the store and the lake advance in the same
    run. The standalone `sports_ncaaf_serving_write_job` remains, for the daily top-up (the
    manifest's `current_game_day` rolls every day) and for a cheap re-fire if only the publish half
    failed.
    """
    ncaaf_serving_write_after_snapshot_op(
        start=ncaaf_futures_snapshot_op(start=ncaaf_prediction_snapshot_op()))
    # NCAAF-P1.2W — an UNBOUND leaf, on purpose: see the op's docstring for why it must not be
    # downstream of the snapshot it rides beside.
    ncaaf_ratings_freshness_op()
