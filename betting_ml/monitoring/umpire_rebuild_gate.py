"""E11.24 target 6 — the per-slate UMPIRE REBUILD idempotency gate.

THE FINDING (2026-07-29 pre-verification, re-confirmed 2026-07-31 on MONITOR_WH). The umpire
chain is the single largest waker left on ``COMPUTE_WH``:

    stg_statsapi_umpire_game_log   CTAS   57 provisioning waits / 8 days
    feature_pregame_umpire_features CTAS  54 provisioning waits / 8 days
                                          ───
                                          111  (~14/day, UTC hours 13-23)

Both are rebuilt by ``lineup_dbt_feature_rebuild``, the last op of ``lineup_monitor_job`` — which
the 10-minute ``lineup_monitor_sensor`` fires all the way through the slate.

🚨 THE ORIGINAL PREMISE IS FALSE ON CURRENT DATA — RE-MEASURED 2026-08-02, PRE-FLIP.

This module was written on the premise that the HP-umpire ASSIGNMENT is "written once per slate
and never re-written" (``min(loaded_at) == max(loaded_at)`` on all 6 dates the feed had then
produced). Re-measured over ``lakehouse_raw/umpire_game_log/`` for the 13 slates 2026-07-20..08-01,
counting DISTINCT same-day ``loaded_at`` instants per slate:

    10, 7, 20, 8, 7, 8, 11, 7, 7, 9, 7, 9, 10   →   median 8, range 7-20

i.e. the assignment is re-stamped roughly ONCE PER TICK from the moment MLB posts it (~16:00 UTC)
to the end of the slate — not once per slate.

MECHANISM (established, not inferred). ``ingest_umpires.py`` runs one op earlier in the SAME job
(``lineup_ingest_umpires``) with ``--skip-if-exists``, whose whole purpose is to make the repeated
fires no-ops. But that guard is gated ``if args.skip_if_exists and not args.dry_run and do_sf`` —
**SF-leg-only** — and the box runs ``W11_RAW_WRITE_MODE=s3`` ⇒ ``do_sf=False`` ⇒ **the guard never
executes**. So every post-assignment tick re-fetches the Stats API and re-writes the S3 mirror,
bumping ``loaded_at`` even though the content is unchanged.

⇒ CONSEQUENCE FOR THIS GATE. Correctness is UNAFFECTED — the gate can still only ever skip a
re-copy of an external table that provably did not move (see the ext-table note below), and it
still cannot swallow a real change. But the SAVING is bounded by the write-instant count: the gate
skips only a tick on which the ingest wrote nothing, and a pre-assignment tick already takes the
"no umpire row yet" fail-open path.

Sized by counting INVOCATIONS, not executions (the E11.24 lever-1b lesson — executions inflate with
per-model/metadata queries). Umpire-rebuild FIRES = distinct 5-minute windows in the 14-23 UTC band
containing an umpire CTAS, against same-day watermark bumps, 2026-07-22..08-01:

    fires    31  12  11  11  16  13   7   9  11  16  19     median 12
    bumps    20   8   7   8  11   7   7   9   7   9  10     median  8

Median ratio ≈ **1.5** ⇒ roughly **ONE FIRE IN THREE is not preceded by a fresh watermark** and is
what this gate removes. So expect an umpire-wait cut of order **30-35% in the band** — against the
clean pre-flip references of 11 waits (7/28) and 13 waits (7/30), roughly 7-9 post-flip. NOT the
~90% the "written once per slate" premise implies, and not zero either. Do not diagnose a ~30% cut
as a broken flip, and do not report it as the premise being vindicated.

The precursor that would actually unlock the rest is making ``--skip-if-exists`` work on the S3 leg
(and per-game rather than any-row, so a later-announced assignment is not swallowed) — a separate
change, deliberately NOT bundled with this flip.

⭐ WHY THE SKIP IS SAFE REGARDLESS (the bound that makes flipping this a low-risk act). The two
umpire ``lakehouse_ext`` tables are refreshed ONLY by ``refresh_w1_external_tables.py --w11b``,
which early-returns and is called only by the nightly W11b mirror op — never intraday, and NOT part
of the default no-arg daily refresh. So across a slate the ext tables are FROZEN, and the CTAS this
gate skips is byte-identical by construction, whatever the raw watermark did.

On the Snowflake target BOTH models are literally ``select * from lakehouse_ext.<model>`` — a CTAS
copy of an S3-derived external table. Re-copying an unchanged external table is a pure no-op that
still has to resume the warehouse.

⭐ THE GATE KEY IS "AN ASSIGNMENT NEWER THAN THE LAST REBUILD", NOT "ALREADY REBUILT TODAY".

That distinction is the whole design, for two reasons:

1. **It must not entrench the lateness.** A separate finding (docs/e11_24_literal_zero_snowflake.md)
   is that the assignment currently lands ~23:10 UTC — AFTER first pitch for 40-55% of the slate.
   A "already rebuilt today" key would latch on the first tick of the afternoon and then SUPPRESS
   the rebuild that folds in the assignment when it finally lands. A watermark key does the
   opposite: the late write bumps the watermark, so it triggers exactly one rebuild, on the first
   tick after it lands. When story 30.5 moves the assignment earlier, this gate needs no change.
2. **It is correct under re-ingest.** ``ingest_umpires.py`` is delete-then-insert scoped to
   ``statsapi`` + today's game_pks, so a corrected assignment re-stamps ``loaded_at`` and the
   watermark moves. A date-keyed gate would miss it.

The watermark is compared over ALL ``data_source`` values for the slate (not just ``statsapi``),
which is deliberately conservative: an ``umpscorecards`` tendency row landing for a slate date also
changes the z-scores the feature model computes, so it too should trigger one rebuild.

FAIL-OPEN by construction, exactly like the shipped statcast gate (1b): any S3/DuckDB/marker
problem resolves to "run the rebuild". A transient read error must never silently suppress the
umpire block — that is the "silently never runs" outage class, and this block already has an
incident history (INC-31, F2) of zeroing unnoticed.

SAFETY FLOOR: only the INTRADAY (``lineup_monitor_job``) rebuild is gated. The once-daily
``dbt_umpire_feature_rebuild`` op is deliberately left UNGATED, so even a wedged marker can only
ever cost intraday freshness for one slate, never a permanently stale block.

TIMEZONE (the LTZ/NTZ landmine — confirm a column's tz AT THE WRITER): ``loaded_at`` in the S3
mirror is stamped by ``lakehouse_raw_writer.umpire_mirror_rows`` as
``datetime.now(timezone.utc).isoformat()`` — an aware UTC ISO string. The older SF-bridged rows are
``TIMESTAMP_NTZ`` storing UTC, which ``try_cast`` yields naive. Both are routed through
``to_utc_datetime`` (naive ⇒ UTC), so the comparison is UTC-on-UTC with no session offset anywhere.

Kept in ``betting_ml`` (not ``pipeline``) on purpose: fast-gate tests may not import ``pipeline``
(it reads the dbt manifest at import, which is absent in CI).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

# Default-OFF cutover lever (E11.24 method: every cutover ships behind a flag).
UMPIRE_GATE_ENV = "E11_24_UMPIRE_REBUILD_GATE"

# The two models the gate removes from lineup_dbt_feature_rebuild's selector. Everything else in
# that selector (eb_*, starter/lineup/game features) genuinely changes with a confirmed lineup and
# is NEVER gated.
UMPIRE_MODELS = ("stg_statsapi_umpire_game_log", "feature_pregame_umpire_features")

_BUCKET = "baseball-betting-ml-artifacts"
_MARKER_KEY = "baseball/lakehouse_state/umpire_rebuild_watermark.json"


def umpire_gate_on() -> bool:
    """True when an unchanged umpire assignment should skip the intraday umpire rebuild."""
    return os.environ.get(UMPIRE_GATE_ENV, "0").strip() == "1"


# ── the two watermarks ────────────────────────────────────────────────────────────────────

def assignment_watermark(conn, day: date) -> datetime | None:
    """MAX(loaded_at) over every umpire_game_log row for `day`, as an aware UTC datetime.

    None means "no umpire row exists for this slate yet" — which is NOT the same as an error, and
    is handled by the caller as "nothing to fold in, but keep the fail-open floor".
    """
    from betting_ml.utils.lakehouse_monitor import is_missing_glob, lh_raw, to_utc_datetime

    try:
        row = conn.execute(
            f"SELECT MAX(try_cast(loaded_at AS TIMESTAMP)) "
            f"FROM read_parquet('{lh_raw('umpire_game_log')}', union_by_name=true) "
            f"WHERE try_cast(game_date AS DATE) = ?",
            [day],
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        if is_missing_glob(exc):
            return None
        raise
    return to_utc_datetime(row[0]) if row and row[0] is not None else None


def read_rebuild_marker(day: date, s3=None) -> datetime | None:
    """The assignment watermark the last successful rebuild consumed, for `day`.

    None ⇒ never rebuilt for this slate (⇒ rebuild). The marker stores its own ``game_date`` so a
    stale marker from a previous slate can never be mistaken for this slate's.
    """
    from betting_ml.utils.lakehouse_monitor import to_utc_datetime

    s3 = s3 or _s3()
    body = s3.get_object(Bucket=_BUCKET, Key=_MARKER_KEY)["Body"].read()
    payload = json.loads(body)
    if str(payload.get("game_date")) != day.isoformat():
        return None
    wm = payload.get("assignment_watermark")
    return to_utc_datetime(wm) if wm else None


def write_rebuild_marker(day: date, watermark: datetime, s3=None) -> None:
    """Record that a rebuild consumed `watermark` for `day`.

    ⚠️ The caller MUST pass the watermark it read BEFORE the rebuild ran, not "now". An assignment
    landing mid-rebuild then has ``loaded_at > watermark`` and correctly triggers one more rebuild
    on the next tick, instead of being swallowed.
    """
    s3 = s3 or _s3()
    s3.put_object(
        Bucket=_BUCKET,
        Key=_MARKER_KEY,
        Body=json.dumps({
            "game_date": day.isoformat(),
            "assignment_watermark": watermark.isoformat(),
        }).encode(),
        ContentType="application/json",
    )


def _s3():
    """Instance-role-safe boto3 client. NEVER pass aws_access_key_id=os.environ.get(...) — on the
    EC2 box that key is UNSET, and passing None DISABLES boto3's credential chain
    (AuthorizationHeaderMalformed). Guarded by test_boto3_credential_lint.py."""
    import boto3

    return boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-2"))


# ── the decision ──────────────────────────────────────────────────────────────────────────

def umpire_rebuild_decision(day: date, *, conn_factory=None, s3=None) -> tuple[bool, datetime | None, str]:
    """(should_rebuild, watermark_to_record, reason). FAIL-OPEN: any error ⇒ (True, None, why).

    ``watermark_to_record`` is None whenever we could not positively establish the watermark — in
    that case the caller rebuilds and writes NO marker, so the gate simply stays inert rather than
    persisting a value it is not sure about.
    """
    if conn_factory is None:
        from betting_ml.utils.lakehouse_monitor import duck as conn_factory  # noqa: N813

    try:
        conn = conn_factory()
    except Exception as exc:  # noqa: BLE001
        return True, None, f"lakehouse connect failed ({exc}) — failing OPEN"
    try:
        current = assignment_watermark(conn, day)
    except Exception as exc:  # noqa: BLE001
        return True, None, f"assignment watermark read failed ({exc}) — failing OPEN"
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    if current is None:
        # No umpire row for this slate yet. Rebuilding is a no-op on the SF side, but we must NOT
        # record a marker (there is no watermark to record) and must NOT skip — the block has an
        # incident history of zeroing silently, so the floor stays "run it".
        return True, None, f"no umpire row yet for {day} — failing OPEN"

    try:
        last = read_rebuild_marker(day, s3=s3)
    except Exception as exc:  # noqa: BLE001
        return True, current, f"marker read failed ({exc}) — failing OPEN"

    if last is None:
        return True, current, f"no marker for {day} — first rebuild of the slate"
    if current > last:
        return True, current, f"assignment {current.isoformat()} is newer than last rebuild {last.isoformat()}"
    return False, current, (
        f"assignment unchanged since {last.isoformat()} — SKIPPING the umpire rebuild "
        f"(the two models are `select * from lakehouse_ext.*`, so re-copying an unchanged "
        f"external table cannot change any output)"
    )
