"""in_season_stats.py  (NF-INC-0916 node 1 — the weekly model's two training feeds)
=============================================================================================
`stats_player_week` and `snap_counts` are what the weekly model LEARNS FROM: the realized weekly
stat line and the usage that conditions it. Until this module existed, nothing ingested either of
them on any cadence, and the consequence is the incident this module is named for — the 2026
week-1 training rows carried no stat line, `attach_labels` filled them with zeros under the
retained-zero convention, and the fit's hurdle learned a `P(zero)` from a week in which nobody
had scored anything.

══ WHY THESE TWO ARE NOT IN `ROLL_FORWARD_SOURCES`, WHICH IS THE OBVIOUS PLACE ══════════════════

Because the roll-forward's cadence is structurally wrong for them, and the repo had already said
so: `roll_forward.py`'s own scope boundary reads "It does NOT pull the realized-game stack
(pbp / stats_player_* / snap_counts / NGS / PFR / QBR) — those don't exist for an unplayed season
and are the in-season NF-D2/NF1 concern ON THEIR OWN CADENCE." That cadence was never built. This
is it.

⭐ THE MEASUREMENT, because "weekly is fine" is exactly the assumption that would put the incident
back (all of it read live on 2026-09-15/16):

  * An NFL week ENDS on a Monday night. Measured on the 2026 schedule, week 1 ran 09-09 → 09-14
    and week 2 runs 09-17 → 09-21.
  * The vendor publishes a completed week the NEXT MORNING. `stats_player_week_2026.parquet` was
    republished 2026-09-15T14:21:38Z (≈07:21 PT Tuesday) and `snap_counts_2026.parquet` at
    2026-09-15T11:25:15Z (≈04:25 PT) — the morning after week 1's Monday-night close — and each
    carried week 1 and nothing later.
  * `NFL_ROLL_FORWARD_CRON` is `15 6 * 3-12,1-2 1` — MONDAY 06:15 PT. A Monday-morning fire lands
    a file that does not yet contain the week ending that very night, and the next fire is seven
    days later. ⇒ on a weekly cadence the just-completed week is ALWAYS missing for a full week,
    and every Monday-night participant carries no line for seven days.

Under the retained-zero convention a missing line is a ZERO, so that is not a freshness nuisance —
it is this incident recurring every week at one-sixteenth the size. The feeds therefore need a
DAILY in-season cadence, which is also what their consumer already runs on.

══ ONE OWNER ═══════════════════════════════════════════════════════════════════════════════════

⛔ These two are ingested by EXACTLY ONE thing: `nfl_weekly_stats_ingest_op`, the first op of
`sports_nfl_weekly_serving_job`, immediately upstream of the build that reads them. That placement
is the INC-25 rule in its strongest form — the consumer is refreshed downstream of its feed IN THE
SAME RUN, so there is no cron window in which the build can read a lake the ingest has not yet
touched, and no second schedule that can silently revert to STOPPED (NF-INFRA1).

The assertions below make the exclusivity mechanical: a future edit that adds either name to
`ROLL_FORWARD_SOURCES` fails at import, because two writers on one Delta table is the defect this
repo has paid for repeatedly (INC-30's two crontabs, INC-36's two deploys, INC-38's four callers).

══ THE WRITE SCOPE, VERIFIED BEFORE SCHEDULING ANYTHING ═════════════════════════════════════════

The spec's precondition was whether a season-scoped partition overwrite can clobber in-season
weekly rows. It cannot, and the reason is worth stating because it is not obvious from the write
side alone:

  * `sources._nflverse_seasonal` reads the WHOLE season file every time — nflverse publishes one
    cumulative `<asset>_YYYY.parquet` per season, not a per-week file — so what is written back is
    always the full season to date, never one week.
  * `s3io.write_season_partition` then does `replaceWhere season = <season>`, i.e. it replaces
    that season with the superset. Cumulative, idempotent, and value-identical on a re-run.
  * `s3io.write_dataframe` SKIPS a 0-row frame outright, so a not-yet-published week (a 404 → an
    empty slice) can never overwrite a good partition with an empty one.

⇒ the danger the spec asked about is real in general and absent here, and the third bullet is what
makes it absent: the failure mode would be a truncating write, and an empty write is refused.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from . import s3io
from .handler import load_env
from .roll_forward import run_roll_forward
from .sources import ROLL_FORWARD_SOURCES, SOURCES, current_season

log = logging.getLogger(__name__)

#: The weekly model's two training feeds. ⛔ Not a general "in-season stack" — these are exactly
#: the feeds `run_weekly_serving` learns from, and widening this set widens what a daily build
#: pulls before every publish.
WEEKLY_STAT_SOURCES: list[str] = ["stats_player_week", "snap_counts"]

# ── registry integrity, mirroring the ROLL_FORWARD_SOURCES assertions ────────────────────────
assert all(n in SOURCES for n in WEEKLY_STAT_SOURCES), "WEEKLY_STAT_SOURCES has an unknown source"
assert all(SOURCES[n].tier == "nflverse" and not SOURCES[n].on_demand for n in WEEKLY_STAT_SOURCES), (
    "WEEKLY_STAT_SOURCES must be free (non-on_demand) nflverse sources only — this set is pulled "
    "before EVERY daily weekly build, so a paid or per-event source here would bill daily"
)
# ⛔ ONE OWNER. See the module docstring: two writers on one Delta table is a defect class this
# repo has paid for more than once, and the cadences differ, so the overlap would not even be a
# harmless duplicate — the weekly fire would periodically write a staler view of the same season.
_OVERLAP = sorted(set(WEEKLY_STAT_SOURCES) & set(ROLL_FORWARD_SOURCES))
assert not _OVERLAP, (
    f"{_OVERLAP} are in BOTH WEEKLY_STAT_SOURCES and ROLL_FORWARD_SOURCES. These feeds have "
    "exactly one ingest owner (the weekly serving job, daily, immediately upstream of the build "
    "that reads them). The roll-forward runs weekly on Monday morning, which is structurally one "
    "week stale for a feed whose week closes on Monday night — see the module docstring."
)


def run_weekly_stats_ingest(
    season: int | None = None,
    *,
    bucket: str = s3io.DEFAULT_BUCKET,
    local_root: str | None = None,
    ctx=None,
) -> dict[str, Any]:
    """Refresh the weekly model's training feeds for `season` (default `current_season()`).

    ⭐ DELEGATES TO `run_roll_forward` WITH A SCOPED SOURCE SET rather than re-implementing the
    fetch/land/summarise loop. That function is already "ingest these sources for this season and
    report landed / not-yet-published / errored", and its `sources` argument is a documented
    override; a second copy of that loop is precisely the many-owners drift this repo keeps
    getting caught by. What is story-specific is the SET and the CADENCE, and both live here.

    Returns the `run_ingest` manifest ({source/season: rows | "ERROR: …"}). Per-source failures are
    ALERT-loud-but-continue: a feed the vendor has not published yet must not sink the batch, and
    the protection against training on what did not land is the target week's own COVERAGE REFUSAL
    (node 2), not this ingest's exit code.
    """
    season = int(season) if season is not None else current_season()
    log.info("NFL in-season weekly-stat ingest: season=%s sources=%s", season, WEEKLY_STAT_SOURCES)
    return run_roll_forward(season, sources=WEEKLY_STAT_SOURCES, bucket=bucket,
                            local_root=local_root, ctx=ctx)


def _cli() -> None:
    p = argparse.ArgumentParser(
        description="NFL in-season weekly-stat ingest (NF-INC-0916 node 1): refresh "
                    "stats_player_week + snap_counts for a season.")
    p.add_argument("--season", type=int, default=None,
                   help="season to refresh (default: current_season() — clock-derived)")
    p.add_argument("--local-root", help="write Delta to a local dir instead of S3 (offline dry run)")
    p.add_argument("--bucket", default=s3io.DEFAULT_BUCKET)
    p.add_argument("--dry-run", action="store_true",
                   help="print the resolved season + source set and exit — ZERO network calls")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()  # no-op for nflverse (unauthenticated); kept for parity with the sibling runners
    season = args.season if args.season is not None else current_season()

    if args.dry_run:
        log.info("[dry-run] in-season weekly stats season=%s (clock-derived: %s) sources=%s — "
                 "no network calls", season, current_season(), WEEKLY_STAT_SOURCES)
        return

    manifest = run_weekly_stats_ingest(season, bucket=args.bucket, local_root=args.local_root)
    for k, v in manifest.items():
        if not k.startswith("_"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    _cli()
