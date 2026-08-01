"""
check_intraday_fallback.py — E11.27 per-slate intraday_fallback monitor.

WHY THIS EXISTS (E11.24 §8 / the CLAUDE.md silent-degrade note / INC-35):
    predict_today's feature-source selection (betting_ml.utils.data_loader.load_todays_features)
    silently falls through to the intraday assembly whenever the feature store has no rows for
    today or its coverage is below the gate — no HALT, no alarm, just a `data_source` stamp of
    'intraday_fallback' (team-carry-forward only) or 'intraday_assembly' (lineup/starter overlay
    applied) on the written daily_model_predictions row instead of 'feature_store'. This class
    has cost multiple days of degraded/zero-edge serving TWICE and gone undetected until someone
    happened to query the column by hand:
      - 7/24-7/25 (the phase-2b tz-incident fingerprint): the ENTIRE tier fell through —
        feature_store=0 for the whole slate (7/24 landed on 'intraday_assembly', 7/25 on
        'intraday_fallback' — the data_source VALUE differs by whether the lineup/starter
        overlay found anything, but a tier-wide feature_store=0 is the real signal either way).
      - 7/25-7/27 (pre-lakehouse rot): a high but not total share of the slate fell to
        'intraday_fallback'.
    Meanwhile `intraday_fallback` is CHRONIC at ~1 game/slate ever since ~7/01 (INC-35) — a
    single game whose lineup/starter data simply hasn't posted yet is completely normal and must
    NOT page every morning, or the monitor gets muted and is worse than nothing.

WHAT IT CHECKS (per prediction_type / serving tier that has rows for the served date):
    (a) SLATE-WIDE / HIGH-SHARE FALLBACK — data_source='intraday_fallback' on
        ≥ FALLBACK_ALERT_COUNT games AND ≥ FALLBACK_ALERT_SHARE of the tier. Both a count floor
        and a share floor must clear so a large multi-game slate isn't flagged by a share blip
        and a tiny slate isn't flagged by a single game's share looking large.
    (b) FEATURE_STORE=0 — zero games on the tier came from the feature store at all (the
        phase-2b tz-incident fingerprint, the real P1). Checked INDEPENDENTLY of (a): 7/24
        proved a tier can fall through ENTIRELY via 'intraday_assembly' with ZERO
        'intraday_fallback' rows, so a check keyed only on the fallback share would have missed
        it outright.
    The CHRONIC ~1-game/slate baseline is reported as an INFORMATIONAL metric on every run
    (never contributes to the ALERT) so a slow creeping regression is still visible in the
    Dagster metadata trend even while it stays below the serious threshold.

THRESHOLD RATIONALE (state per the story's "don't cry wolf" requirement):
    FALLBACK_ALERT_COUNT = 3, FALLBACK_ALERT_SHARE = 0.30 — a chronic single game on a typical
    10-16 game MLB slate is ~6-10% share, well under both floors, so the steady-state day stays
    silent. 3+ games AND ≥30% share means at least a third of the slate degraded — a materially
    different (and rare, pre-lakehouse-rot-class) event, not the daily noise floor. A FIXED
    threshold was chosen over a trailing-median share for determinism/testability: a moving
    baseline that itself absorbs a slow regression is exactly the kind of instrument that would
    let this class re-normalize unnoticed a second time.
    MIN_GAMES_FOR_CHECK = 5 mirrors check_served_prediction_integrity.py — below this even the
    count/share signals are too noisy (an off-morning re-score, a doubleheader-only day) to
    assess at all.

TIER (E11.7 pipeline failure-handling contract): ALERT-loud-but-continue, ALWAYS — this check
    has NO --strict escalation and NEVER exits non-zero. A degraded slate is a real signal an
    operator must see, not a reason to fail the daily job (it must not become a second blind
    spot the other direction: a monitor that can HALT the pipeline invites being disabled under
    pressure). See CLAUDE.md's E11.7 op→tier table: `check_intraday_fallback_op` = ALERT (never
    HALT).

Snowflake-FREE: reads `daily_model_predictions` via DuckDB over its S3 lakehouse mirror (the
same parquet `predict_today.py` re-exports immediately after each write — see
`scripts/lineup_monitor.py::_games_with_post_lineup_s3`, the reference pattern for this read).

Usage:
    uv run python scripts/check_intraday_fallback.py --env prod
    uv run python scripts/check_intraday_fallback.py --env dev --date 2026-07-25
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.game_day import current_game_date

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# A tier needs at least this many served games before we assess it — below this even the
# count/share signals are too noisy (an off-morning re-score, a doubleheader-only day).
MIN_GAMES_FOR_CHECK = 5
# The SERIOUS threshold (part a): both floors must clear — see the module docstring rationale.
FALLBACK_ALERT_COUNT = 3
FALLBACK_ALERT_SHARE = 0.30


@dataclass
class TierFallbackStat:
    """Per-serving-tier data_source breakdown over today's served slate (one prediction_type)."""
    tier: str
    n: int
    n_feature_store: int
    n_intraday_fallback: int
    n_intraday_assembly: int


def evaluate_tier(
    stat: TierFallbackStat,
    *,
    min_games: int = MIN_GAMES_FOR_CHECK,
    fallback_alert_count: int = FALLBACK_ALERT_COUNT,
    fallback_alert_share: float = FALLBACK_ALERT_SHARE,
) -> list[str]:
    """Pure classifier: given one tier's data_source aggregates, return the list of ALERT-worthy
    problems (empty = healthy / chronic-only). No IO — unit-tested directly with synthetic
    TierFallbackStats."""
    problems: list[str] = []
    if stat.n < min_games:
        return problems  # too few served games to assess this tier

    share = stat.n_intraday_fallback / stat.n if stat.n else 0.0

    # (b) FEATURE_STORE=0 — the tier fell through ENTIRELY (the phase-2b tz-incident
    # fingerprint). Independent of (a): the fallen-through rows may be 'intraday_assembly'
    # (7/24) rather than 'intraday_fallback' (7/25), so this must not depend on the fallback
    # share at all.
    if stat.n_feature_store == 0:
        problems.append(
            f"{stat.tier}: feature_store=0 of {stat.n} — the ENTIRE tier fell through to the "
            f"intraday assembly (fallback={stat.n_intraday_fallback}, "
            f"assembly={stat.n_intraday_assembly}) — the phase-2b tz-incident fingerprint "
            f"(a real P1 unless this is the very first run of the morning)"
        )
    # (a) SLATE-WIDE / HIGH-SHARE FALLBACK — only asserted when (b) didn't already fire, so a
    # feature_store=0 tier reports one clear problem instead of two overlapping ones.
    elif stat.n_intraday_fallback >= fallback_alert_count and share >= fallback_alert_share:
        problems.append(
            f"{stat.tier}: intraday_fallback served {stat.n_intraday_fallback}/{stat.n} games "
            f"({share:.0%}) — at/above the serious threshold "
            f"(≥{fallback_alert_count} games AND ≥{fallback_alert_share:.0%} share), NOT the "
            f"chronic ~1-game/slate baseline (INC-35)"
        )
    return problems


def _fetch_tier_stats(served_date: date) -> list[TierFallbackStat]:
    """SF-free: DuckDB over the S3 lakehouse mirror of daily_model_predictions (the parquet
    predict_today.py re-exports immediately after each write). Rows are DEDUPED to the
    currently-serving row per (tier, game_pk) — latest inserted_at — before aggregating, same as
    check_served_prediction_integrity.py, because morning predict re-runs across the day and does
    not supersede its prior rows."""
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    try:
        register_lakehouse_views(conn, ["daily_model_predictions"])
        rows = conn.execute(
            """
            with ranked as (
                select
                    prediction_type, game_pk, data_source,
                    row_number() over (
                        partition by prediction_type, game_pk
                        order by inserted_at desc
                    ) as rn
                from daily_model_predictions
                where score_date::date = ?::date
            )
            select
                prediction_type,
                count(*)                                        as n,
                count_if(data_source = 'feature_store')         as n_feature_store,
                count_if(data_source = 'intraday_fallback')     as n_intraday_fallback,
                count_if(data_source = 'intraday_assembly')     as n_intraday_assembly
            from ranked
            where rn = 1
            group by prediction_type
            """,
            [served_date.isoformat()],
        ).fetchall()
    finally:
        conn.close()
    return [
        TierFallbackStat(
            tier=str(r[0]),
            n=int(r[1]),
            n_feature_store=int(r[2]),
            n_intraday_fallback=int(r[3]),
            n_intraday_assembly=int(r[4]),
        )
        for r in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Per-slate intraday_fallback monitor (E11.27, ALERT-tier, never HALTs)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Served date to inspect. Default: current US baseball date.")
    args = parser.parse_args()

    served_date = date.fromisoformat(args.date) if args.date else current_game_date()
    log.info(f"[{args.env.upper()}] intraday_fallback monitor — served_date={served_date}")

    stats = _fetch_tier_stats(served_date)

    if not stats:
        # No predictions for today yet — benign (empty-serve-vs-off-day is
        # check_prediction_coverage's domain), never an alert.
        print("[METRIC] intraday_fallback_alert_count=0")
        print("[METRIC] intraday_fallback_zero_feature_store_tiers=0")
        print("[METRIC] intraday_fallback_chronic_games=0")
        log.info(f"No predictions for {served_date} yet — nothing to assess.")
        return 0

    problems: list[str] = []
    zero_fs_tiers = 0
    chronic_fallback_games = 0
    assessed = 0
    # INC-37 — rows on tiers we SKIPPED. A skipped tier is UNVERIFIED, not healthy: on 2026-08-01
    # a mis-run left 4 of 15 games served and BOTH tiers fell under MIN_GAMES_FOR_CHECK, so this
    # script printed `alert_count=0` while 11 games sat unserved. Track and report it so the
    # calling op can say "could not verify" instead of implying "verified fine".
    unassessed_rows = 0
    for stat in sorted(stats, key=lambda s: s.tier):
        if stat.n < MIN_GAMES_FOR_CHECK:
            unassessed_rows += stat.n
            log.info(f"  tier '{stat.tier}': n={stat.n} (< {MIN_GAMES_FOR_CHECK}) — too small to assess.")
            continue
        assessed += 1
        chronic_fallback_games += stat.n_intraday_fallback
        tier_problems = evaluate_tier(stat)
        share = stat.n_intraday_fallback / stat.n if stat.n else 0.0
        fs_share = stat.n_feature_store / stat.n if stat.n else 0.0
        head = (f"  tier '{stat.tier}': n={stat.n}, feature_store={stat.n_feature_store} "
                f"({fs_share:.0%}), intraday_fallback={stat.n_intraday_fallback} ({share:.0%}), "
                f"intraday_assembly={stat.n_intraday_assembly}")
        if tier_problems:
            log.error(head + "  [PROBLEM]")
            problems.extend(tier_problems)
            if stat.n_feature_store == 0:
                zero_fs_tiers += 1
        else:
            note = "  [OK — chronic single-game fallback, informational]" if stat.n_intraday_fallback else "  [OK]"
            log.info(head + note)

    print(f"[METRIC] intraday_fallback_alert_count={len(problems)}")
    print(f"[METRIC] intraday_fallback_zero_feature_store_tiers={zero_fs_tiers}")
    print(f"[METRIC] intraday_fallback_chronic_games={chronic_fallback_games}")
    print(f"[METRIC] intraday_fallback_tiers_assessed={assessed}")
    # INC-37: >0 means the served date HAS predictions this check could not verify. The op pages
    # WARN when NOTHING was assessed (assessed=0 while rows exist) — the state in which an
    # `alert_count=0` is entirely vacuous.
    print(f"[METRIC] intraday_fallback_unassessed_rows={unassessed_rows}")

    if assessed == 0 and unassessed_rows:
        log.warning(
            f"[ALERT] NOT ASSESSED — {unassessed_rows} served row(s) exist for {served_date} but "
            f"every tier was under the {MIN_GAMES_FOR_CHECK}-game floor, so NOTHING was checked. "
            f"Treat the metrics above as UNKNOWN, not healthy (INC-37): a mis-run that deletes "
            f"most of a slate lands exactly here. Verify the served row count per tier directly."
        )

    if problems:
        _emit(problems)
    else:
        log.info(f"intraday_fallback monitor OK across {assessed} tier(s) for {served_date} "
                 f"(chronic informational count: {chronic_fallback_games} game(s) on "
                 f"intraday_fallback — below the serious threshold).")
    # ALERT-tier, ALWAYS — see the module docstring. Never HALT.
    return 0


def _emit(problems: list[str]) -> None:
    banner = (
        "INTRADAY_FALLBACK monitor problem(s) on today's slate — the model silently degraded to "
        "the intraday assembly (E11.27 / E11.24 §8 / INC-35 blind-spot closer): "
        + " | ".join(problems)
        + ". Investigate with: check load_todays_features' coverage gate + the W8a/W8b served "
        "parquet freshness, the daily-job build ordering (INC-25 class), and (for a "
        "feature_store=0 slate) whether this is the very first predict run of the morning "
        "(the feature store may simply not be populated yet) vs a genuine pipeline stall."
    )
    log.warning("[ALERT] " + banner)


if __name__ == "__main__":
    sys.exit(main())
