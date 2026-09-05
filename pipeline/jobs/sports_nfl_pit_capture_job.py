"""NF-W0a — the box Dagster jobs for the NFL point-in-time FORWARD CAPTURE.

⏰ THE CLOCK IS THE WHOLE POINT. The 2026 season opens **2026-09-09** (SEA-NE; the Melbourne game
is 09-10). A forecast is only point-in-time-honest if it was CAPTURED AT THE TIME — the
Open-Meteo archive returns OBSERVATIONS, not the forecast that stood on a historical Tuesday —
and the odds history holds only CLOSING lines, so no Tuesday-build market feature can ever be
backtested without forward capture. Every week these jobs do not run is a week PERMANENTLY absent
from the training frame. There is no backfill.

THREE JOBS, split by what gates them rather than by cadence, because the gates differ in kind:

  `sports_nfl_pit_weather_job`   hourly ladder [120,72,48,24,3,1]h. FREE (Open-Meteo, no key).
  `sports_nfl_pit_metadata_job`  injuries (stamped with OUR capture_timestamp) + per-ingest
                                 nflverse schema snapshots. FREE.
  `sports_nfl_pit_market_job`    Tue/Fri live odds board. ⚠️ PAID (Odds-API credits) → its
                                 schedule ships STOPPED, operator-gated.

TIER: WARN / ALERT-loud-but-continue for every op. A capture failure is not a serving outage —
nothing downstream reads these tables yet — so an op must never fail the run. But a failure IS
irreversible data loss, so every op PAGES via `send_alert` when its manifest escalates. That is
the E11.30 lesson applied at birth rather than retrofitted: an "ALERT-tier" op that only reaches
`context.log.warning` is an op nobody is notified about, and this repo shipped four of those.

⚠️ RUNTIME GATE (CLAUDE.md 🟥): CI mocks all IO, so green tests do NOT prove these fire. The
merge bar for this story is a real box run producing a captured row with a real
`capture_timestamp` — see the story handoff for the exact command.
"""

from dagster import Nothing, Out, in_process_executor, job, op


def _page(context, leg: str, manifest: dict, *, severity: str) -> None:
    """Page on an escalating leg. Keyed per leg so one noisy leg cannot suppress another's page
    (the INC-39 dedup-slot lesson)."""
    from pipeline.utils.alerting import send_alert

    send_alert(
        f"NFL PIT capture: {leg} needs attention",
        f"The NF-W0a {leg} capture leg reported an escalation.\n\n"
        f"manifest: {manifest}\n\n"
        f"WHY THIS MATTERS: a point-in-time capture cannot be backfilled — the Open-Meteo archive "
        f"returns observations rather than the forecast that stood at the time, and the odds "
        f"history holds only closing lines. A lost checkpoint is lost permanently.\n"
        f"FIRST ACTION: re-run the leg manually "
        f"(`python -m quant_sports_intel_models.football.nfl.pit.run_capture --leg {leg}`) "
        f"while the game is still pre-kickoff.",
        severity=severity,
        dedup_key=f"nfl_pit_capture:{leg}",
    )
    context.log.warning("ALERT [nfl/pit/%s] escalated: %s", leg, manifest)


def _run_leg(context, leg: str, *, severity: str = "ERROR", **kwargs) -> dict:
    """Run one capture leg. Never raises — WARN tier — but always pages on escalation."""
    from quant_sports_intel_models.football.nfl.pit.run_capture import run_legs

    try:
        manifest = run_legs((leg,), **kwargs).get(leg) or {}
    except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue
        context.log.warning("ALERT [nfl/pit/%s] raised: %s", leg, exc)
        _page(context, leg, {"error": str(exc)}, severity=severity)
        return {"error": str(exc)}

    context.log.info("[nfl/pit/%s] %s", leg, manifest)
    if manifest.get("escalate") or manifest.get("error"):
        _page(context, leg, manifest, severity=severity)
    return manifest


@op(out=Out(Nothing))
def nfl_pit_weather_capture_op(context):
    """Hourly weather-forecast ladder capture (FREE; Open-Meteo, no API key).

    CRITICAL severity: this is the leg with the hardest deadline. A missed T-120h rung for a
    Sunday game cannot be recovered at T-72h — that is a DIFFERENT forecast, and the Tuesday
    build's feature is the one that is gone.
    """
    _run_leg(context, "weather", severity="CRITICAL")


@op(out=Out(Nothing))
def nfl_pit_metadata_capture_op(context):
    """Injuries stamped with OUR `capture_timestamp` + a per-ingest nflverse schema snapshot.

    The injury leg exists because nflverse DELETED `injuries.date_modified` in 2025, so the only
    as-of timestamp left is one we make. The schema leg exists because our own lake CANNOT see a
    deletion (`schema_mode='merge'` backfills the dropped column with NULLs) while the vendor's
    release file can — 2025 produced three such silent breaks.
    """
    for leg in ("injuries", "schema"):
        _run_leg(context, leg, severity="ERROR")


@op(out=Out(Nothing))
def nfl_pit_market_capture_op(context):
    """A Tue/Fri point-in-time market board (⚠️ PAID — Odds-API credits).

    3 credits per game-line snapshot (≈132/season at this cadence) — MEASURED live 2026-09-05 (NF-CAP1) against x-requests-remaining, bracketed by free /sports reads;
    the previous ~30/~1,300 figures were 10× high because the Odds-API 10× multiplier applies to
    the `/historical` endpoint, not the LIVE one this leg uses. Player props are a SEPARATE opt-in
    (`NFL_PIT_CAPTURE_PROPS=1`, default OFF) at ~10 credits PER EVENT over the whole ~272-event
    board ≈ 2,720/snapshot ≈ 60,000/season — confirm the balance before enabling.
    """
    _run_leg(context, "market", severity="CRITICAL")


@job(executor_def=in_process_executor)
def sports_nfl_pit_weather_job():
    """Hourly in-season weather-forecast ladder → the immutable `nfl/pit/weather` store."""
    nfl_pit_weather_capture_op()


@job(executor_def=in_process_executor)
def sports_nfl_pit_metadata_job():
    """Injury reports (own capture stamp) + nflverse schema snapshots → `nfl/pit/*`."""
    nfl_pit_metadata_capture_op()


@job(executor_def=in_process_executor)
def sports_nfl_pit_market_job():
    """Tue/Fri point-in-time market board → the immutable `nfl/pit/market` store (PAID)."""
    nfl_pit_market_capture_op()
