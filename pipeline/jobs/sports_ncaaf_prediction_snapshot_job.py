"""NCAAF-PS — the box Dagster job for the weekly PRE-KICKOFF prediction snapshot.

Runs the SERVED P1.4 game model over the upcoming FBS-vs-FBS slate and appends one immutable row
per (game_id, snapshot_ts) to `ncaaf/derived/game_prediction_snapshots`, then fans out to a weekly
snapshot of the P1.5 futures board. Two ops:

  1. ncaaf_prediction_snapshot_op   — the per-game snapshot. The PRIMARY deliverable.
  2. ncaaf_futures_snapshot_op      — the P1.5 futures board, snapshotted (the cheap fan-out).

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

⚠️ THE ONE QUALITY PREREQUISITE (operator, not code): the season's P1.2 RE-FIT. Until it runs with
fall-camp covariates populated, the strength mart carries the pre-season COLD START (2025
carry-forward — the 2026 board has Indiana leading), so the first real snapshot would freeze that
into the permanent track record. Re-fit first; see the NCAAF-PS handoff.
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

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


@job(executor_def=in_process_executor)
def sports_ncaaf_prediction_snapshot_job():
    """Weekly pre-kickoff per-game predictions → the lake, then the futures-board snapshot."""
    ncaaf_futures_snapshot_op(start=ncaaf_prediction_snapshot_op())
