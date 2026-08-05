"""schema_snapshot.py — snapshot every nflverse asset's SCHEMA per ingest, so a silent field
deletion can never recur undetected.

⭐ WHY OUR OWN LAKE CANNOT DETECT THIS, AND THE RELEASE FILE CAN. The NFL ingest writes Delta with
`schema_mode='merge'`. Merge is the INC-19 cure — an ADDITIVE upstream column becomes a metadata
commit instead of a failed cast — but it is exactly what makes a DELETION invisible: the dropped
column stays in the Delta schema and is BACKFILLED WITH NULLS, so it still reads as present.
2025 produced THREE such breaks (`injuries.date_modified` deleted, `depth_charts` schema replaced,
`schedules`-adjacent drift), and none of them raised anything, anywhere.

The vendor's RELEASE PARQUET has no such amnesia: a deleted column is simply not in the file. So
this leg DESCRIBEs the release URL each ingest and stores the column set + types + a schema
fingerprint. Comparing consecutive snapshots turns a silent deletion into a dated, loud event.

TWO SIGNATURES, and the second is the one a pure schema snapshot would miss:
  • SCHEMA DRIFT — a column added / removed / retyped between snapshots. Free (a parquet footer
    read, no data scan).
  • SILENT DEATH — a column still PRESENT but newly 100% NULL. Costs one aggregate scan, so it is
    probed only for the small, high-value assets (`NULL_PROBE_SOURCES`); a 372-column PBP scan
    every ingest is not worth it. This is the signature NF-W0 named: presence is not health.

⛔ FAIL-CLOSED READING: a source whose schema could not be read is recorded as `UNREADABLE`, never
skipped silently and never scored healthy (NF1.7 (a) — a check that did not run is not a pass).

TIER: WARN — a schema snapshot never blocks an ingest. Its job is to make the NEXT deletion
visible on the day it happens, not to gate.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from . import store
from .schedule import current_season, data_expected_from, looks_like_missing_asset
from .timestamps import CaptureStamps, now_utc

log = logging.getLogger(__name__)

CAPTURE_SOURCE = "schema_snapshot"

#: Assets small enough that a per-ingest NULL-RATE probe is worth one scan. Chosen for the
#: signature they carry: `injuries` holds the deleted as-of column, `depth_charts` is the
#: schema-replaced asset, `schedules` holds the roof/temp/wind PIT fields this story depends on.
NULL_PROBE_SOURCES = frozenset({"injuries", "depth_charts", "schedules", "weekly_rosters"})

#: Columns whose disappearance or silent death we care about ENOUGH TO NAME, so the drift report
#: can say "a WATCHED column died" rather than burying it in a list of 145.
WATCHED_COLUMNS: dict[str, tuple[str, ...]] = {
    "injuries": ("date_modified", "report_status", "practice_status", "gsis_id", "week"),
    "depth_charts": ("week", "depth_team", "gsis_id", "position"),
    "schedules": ("roof", "surface", "gametime", "gameday", "temp", "wind", "location", "stadium"),
    "weekly_rosters": ("status", "gsis_id", "position", "week"),
}

#: ⭐ WATCHED COLUMNS ALREADY MISSING AND ALREADY TRIAGED — the 2025 breaks NF-W0 recorded.
#:
#: These are PERMANENT states, not events. Escalating on them would page every Tue/Fri fire
#: forever (~44 identical unactionable pages a season) about two conditions nobody can act on —
#: the monitor-gets-muted failure mode this repo names repeatedly, and the same judgement E11.30
#: already applies to `check_injury_status_health_op` (log-only on the known off-season ingest
#: hole rather than paging daily for four months). The harm is not the noise: it is that a muted
#: `NFL PIT capture:` subject line also swallows the weather leg's CRITICAL "this slate's forecast
#: is being lost permanently".
#:
#: ⚠️ THE BASELINE MUTES A NAMED (asset, column) PAIR AND NOTHING ELSE. A THIRD watched column
#: going missing still escalates immediately, and the pairs are validated against
#: `WATCHED_COLUMNS` by a guard test so a typo cannot silently widen the mute. Missing-ness is
#: still REPORTED in full every run (`watched_missing`); only the paging decision reads
#: `watched_missing_new`.
ACCEPTED_MISSING: dict[str, frozenset[str]] = {
    # nflverse DELETED the vendor as-of stamp in 2025. This is precisely why the injury leg
    # stamps our own `capture_timestamp` — the condition is handled, not outstanding.
    "injuries": frozenset({"date_modified"}),
    # `depth_charts` was schema-replaced wholesale in 2025; NF-W1 reads the new column set.
    "depth_charts": frozenset({"week", "depth_team", "position"}),
}


def _duck():
    """Box-aware (pit/duck.py) — this leg reads 30 remote parquet files, so an unbounded
    memory_limit here is exactly the INC-22 #4 host-OOM shape."""
    from .duck import connect

    return connect()


def schema_fingerprint(columns: list[tuple[str, str]]) -> str:
    """A stable digest of (name, type) pairs — one value a drift check can compare cheaply."""
    blob = ";".join(f"{n}:{t}" for n, t in columns)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def describe_asset(url: str, *, con=None) -> list[tuple[str, str]]:
    """`[(column_name, column_type), …]` from the parquet FOOTER (no data scan)."""
    con = con or _duck()
    rows = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [url]).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def null_rates(url: str, columns: list[str], *, con=None) -> dict[str, float]:
    """Fraction of NULLs per column, in ONE aggregate scan.

    Returns `{}` on an empty file — a zero-row asset has no null RATE, and reporting 0.0 there
    would read as "fully populated", inverting the signal.
    """
    con = con or _duck()
    total = con.execute("SELECT count(*) FROM read_parquet(?)", [url]).fetchone()[0]
    if not total:
        return {}
    quoted = ", ".join(f'count("{c}") AS "{c}"' for c in columns)
    row = con.execute(f"SELECT {quoted} FROM read_parquet(?)", [url]).fetchone()
    return {c: round(1.0 - (row[i] or 0) / total, 6) for i, c in enumerate(columns)}


def _asset_urls(season: int) -> dict[str, str]:
    """The registry's nflverse URLs for one season, resolved WITHOUT duplicating the URL logic.

    Built by asking `ingest.sources` for its own specs so a registry change (a new asset, a moved
    release tag) is picked up here automatically — a hand-copied URL list is exactly the
    "one logical thing, two owners" shape that goes stale silently.
    """
    from ..ingest import sources as nfl_sources

    urls: dict[str, str] = {}
    for name, spec in nfl_sources.SOURCES.items():
        if spec.tier != "nflverse":
            continue
        url = getattr(spec.fetch, "nflverse_url", None)
        if callable(url):
            try:
                url = url(season)
            except Exception:  # noqa: BLE001
                url = None
        if isinstance(url, str) and url:
            urls[name] = url
    return urls


def snapshot_schemas(
    season: int | None = None,
    *,
    urls: dict[str, str] | None = None,
    now: datetime | None = None,
    con=None,
    probe_nulls: bool = True,
) -> list[dict]:
    """DESCRIBE every asset and return one capture row per asset (no store write)."""
    now = now or now_utc()
    season = season if season is not None else current_season(now)
    urls = urls if urls is not None else _asset_urls(season)
    con = con or _duck()

    rows: list[dict] = []
    for asset, url in sorted(urls.items()):
        status, columns, nulls, error = "OK", [], {}, None
        try:
            columns = describe_asset(url, con=con)
        except Exception as exc:  # noqa: BLE001 — fail-closed: recorded UNREADABLE, never skipped
            status, error = "UNREADABLE", str(exc)[:300]
            log.warning("ALERT [nfl/pit/schema] %s (%s) UNREADABLE: %s", asset, url, error)

        if status == "OK" and probe_nulls and asset in NULL_PROBE_SOURCES:
            try:
                nulls = null_rates(url, [c for c, _ in columns], con=con)
            except Exception as exc:  # noqa: BLE001
                log.warning("ALERT [nfl/pit/schema] %s null-probe failed: %s", asset, str(exc)[:200])

        watched = WATCHED_COLUMNS.get(asset, ())
        names = [c for c, _ in columns]
        payload = {
            "asset": asset, "url": url, "status": status, "error": error,
            "columns": [{"name": n, "type": t} for n, t in columns],
            "null_rates": nulls,
        }
        stamps = CaptureStamps.build(
            capture_source=CAPTURE_SOURCE,
            subject_key=f"{asset}|{season}",
            checkpoint=now.strftime("%Y-%m-%dT%H"),
            payload=payload,
            feature_timestamp=now,
            capture_timestamp=now,
            source_timestamp=None,
            vendor_release_timestamp=None,
        )
        row = stamps.as_dict()
        row.update(
            {
                "record_tier": "schema",
                "source_timestamp_absent_reason": (
                    "a release asset's schema has no vendor as-of stamp; the GitHub release "
                    "asset's Last-Modified is not exposed through the parquet reader"
                ),
                "asset": asset, "season": season, "url": url, "status": status, "error": error,
                "column_count": len(columns),
                "column_names": names,
                # Stored ALONGSIDE the names (positionally aligned) because the retype check needs
                # them. Keeping only names meant a reconstructed prior carried `type=""` for every
                # column, and `"" != "VARCHAR"` read as a RETYPE on every column of every asset.
                "column_types": [t for _, t in columns],
                "schema_fingerprint": schema_fingerprint(columns),
                # ⚠️ ONLY MEANINGFUL FOR A READABLE ASSET. An UNREADABLE asset has `columns=[]`, so
                # a naive computation reports EVERY watched column as "missing" — which is false:
                # they are UNKNOWN, not absent. That is NF1.7 (a) inverted (an unevaluable check
                # reported as a definite negative finding), and it double-reports one condition
                # (the asset could not be read) as two. `unreadable` already carries that signal,
                # once. Measured 2026-08-05: an absent `injuries_2026.parquet` had the leg
                # announcing four columns as newly deleted that nobody had looked at.
                "watched_missing": [c for c in watched if c not in names] if status == "OK" else [],
                "watched_all_null": sorted(
                    c for c in watched if nulls.get(c) is not None and nulls[c] >= 1.0
                ),
                "null_probed": bool(nulls),
                "payload": payload,
            }
        )
        rows.append(row)
    return rows


def diff_snapshots(previous: dict, current: dict) -> dict:
    """Drift between two snapshots of the SAME asset. Both are `snapshot_schemas` rows."""
    prev_cols = {c["name"]: c["type"] for c in (previous.get("payload", {}).get("columns") or [])}
    cur_cols = {c["name"]: c["type"] for c in (current.get("payload", {}).get("columns") or [])}
    prev_nulls = previous.get("payload", {}).get("null_rates") or {}
    cur_nulls = current.get("payload", {}).get("null_rates") or {}

    removed = sorted(set(prev_cols) - set(cur_cols))
    added = sorted(set(cur_cols) - set(prev_cols))
    # ⚠️ AN UNKNOWN TYPE IS NOT A CHANGED TYPE (NF1.7 (a) again). A snapshot stored before
    # `column_types` existed reconstructs with `type=""`, and comparing that verbatim declares a
    # RETYPE on every column of every asset — measured live 2026-08-05: 17 assets, including a
    # `schedules` "watched drift" naming roof/temp/wind/gameday, with the schema fingerprint
    # IDENTICAL on both sides. Comparing only where both types are known degrades gracefully to a
    # name-set diff (still catching deletions and additions, which is what the leg is for) and
    # self-heals as soon as one snapshot carries types.
    retyped = sorted(
        c for c in set(prev_cols) & set(cur_cols)
        if prev_cols[c] and cur_cols[c] and prev_cols[c] != cur_cols[c]
    )
    # SILENTLY DEAD: was populated, is now entirely NULL. Only computable where BOTH snapshots
    # probed nulls — otherwise it is UNKNOWN, which is not the same as clean.
    silently_dead = sorted(
        c for c in set(prev_nulls) & set(cur_nulls) if prev_nulls[c] < 1.0 <= cur_nulls[c]
    )
    watched = set(WATCHED_COLUMNS.get(current.get("asset") or "", ()))
    return {
        "asset": current.get("asset"),
        "columns_removed": removed,
        "columns_added": added,
        "columns_retyped": retyped,
        "silently_dead": silently_dead,
        "watched_affected": sorted(watched & (set(removed) | set(retyped) | set(silently_dead))),
        "fingerprint_changed": previous.get("schema_fingerprint") != current.get("schema_fingerprint"),
        "drifted": bool(removed or added or retyped or silently_dead),
    }


def new_watched_missing(watched_missing: dict) -> dict:
    """The missing watched columns the accepted baseline does NOT cover — the paging driver.

    Set-subtraction per asset, so accepting `injuries.date_modified` mutes exactly that pair and
    leaves every other watched injuries column paging on the day it disappears.
    """
    out = {}
    for asset, cols in (watched_missing or {}).items():
        fresh = sorted(set(cols) - ACCEPTED_MISSING.get(asset, frozenset()))
        if fresh:
            out[asset] = fresh
    return out


def accepted_watched_missing(watched_missing: dict) -> dict:
    """The complement of `new_watched_missing` — reported, logged, never paged."""
    out = {}
    for asset, cols in (watched_missing or {}).items():
        known = sorted(set(cols) & ACCEPTED_MISSING.get(asset, frozenset()))
        if known:
            out[asset] = known
    return out


def resolved_accepted_missing(rows: list[dict]) -> dict:
    """Baseline entries whose column is PRESENT again, i.e. the mute has gone stale.

    Only decidable for a readable asset — an UNREADABLE row is UNKNOWN, and reporting it as
    "resolved" would be the vacuous-pass class (NF1.7 (a)) facing the cheerful direction.
    """
    out = {}
    for row in rows or []:
        asset = row.get("asset")
        accepted = ACCEPTED_MISSING.get(asset or "")
        if not accepted or row.get("status") != "OK":
            continue
        back = sorted(accepted - set(row.get("watched_missing") or ()))
        if back:
            out[asset] = back
    return out


#: Columns the prior-snapshot read wants, and whether the read still works without each. A column
#: added by a later story is ABSENT from every row written before it, so it must be projected
#: conditionally (see `prior_snapshot_sql`).
_PRIOR_OPTIONAL_COLUMNS = ("status", "column_types")


def prior_snapshot_sql(available: set[str], *, relation: str = "snaps") -> str:
    """The latest-snapshot-per-asset query, projecting only columns the store actually has.

    ⚠️ A NEW COLUMN CANNOT BE SELECTED FROM A STORE WRITTEN BEFORE IT EXISTED. The prior snapshot
    is read BEFORE this run writes, so on the first run after any column is added the Delta schema
    still lacks it and a plain `SELECT` raises `Binder Error: Referenced column … not found` —
    failing the whole leg exactly once, on the deploy that introduced the fix. Projecting `NULL`
    for an absent column makes the read forward- and backward-compatible, and the value then flows
    through the same "unknown" handling the diff already has.
    """
    cols = ["asset", "schema_fingerprint", "column_names", "capture_timestamp"]
    cols += [c if c in available else f"NULL AS {c}" for c in _PRIOR_OPTIONAL_COLUMNS]
    return (
        f"SELECT {', '.join(cols)} FROM {relation} WHERE season = ? "
        "QUALIFY row_number() OVER (PARTITION BY asset ORDER BY capture_timestamp DESC) = 1"
    )


def classify_unreadable(
    rows: list[dict], previous: dict, *, now: datetime, expected_from: datetime | None
) -> tuple[list[str], list[str]]:
    """Split unreadable assets into `(unexpected, expected_absent)`.

    ⭐ THE DISCRIMINATOR IS THE SNAPSHOT STORE, NOT A CALENDAR GUESS. An asset we successfully
    described before and cannot describe now is a REGRESSION and escalates unconditionally —
    that is the silent-death signature this leg exists to date. An asset we have NEVER seen for
    this season is simply not published yet, and nflverse publishes season-scoped assets
    progressively as data appears (measured 2026-08-05: `depth_charts_2026` existed, `injuries_2026`
    and twelve others did not). Same "a known state is not an event" split the ACCEPTED_MISSING
    baseline draws for columns, one level up — applied to the asset instead of the column.

    The never-seen branch is BOUNDED by `expected_from` so it cannot become a permanent blindfold:
    past that instant every season-scoped asset should exist, and a still-absent one escalates.
    """
    unexpected, expected_absent = [], []
    for row in rows or []:
        if row.get("status") == "OK":
            continue
        asset = row.get("asset")
        prior = (previous or {}).get(asset) or {}
        seen_readable = prior.get("status") == "OK"
        missing_asset = looks_like_missing_asset(str(row.get("error") or ""))
        # An UNKNOWN bar cannot license silence — NF1.7 (a): a check that did not run is not a pass.
        before_bar = expected_from is not None and now < expected_from
        if not seen_readable and missing_asset and before_bar:
            expected_absent.append(asset)
        else:
            unexpected.append(asset)
    return sorted(unexpected), sorted(expected_absent)


def run_schema_snapshot(
    season: int | None = None,
    *,
    now: datetime | None = None,
    urls: dict[str, str] | None = None,
    rows: list[dict] | None = None,
    previous: dict | None = None,
    bucket: str | None = None,
    local_root: str | None = None,
    dry_run: bool = False,
    probe_nulls: bool = True,
    expected_from: datetime | None = None,
) -> dict:
    """Snapshot every nflverse asset schema and report drift vs the previous snapshot.

    `previous` maps `asset -> prior snapshot row`; when omitted it is read from the store, so a
    routine run compares itself to the last one with no caller bookkeeping.
    """
    now = now or now_utc()
    season = season if season is not None else current_season(now)
    if rows is None:
        rows = snapshot_schemas(season, urls=urls, now=now, probe_nulls=probe_nulls)

    if previous is None and not dry_run:
        previous = _latest_by_asset(season, bucket=bucket, local_root=local_root)
    previous = previous or {}

    drifts = []
    for row in rows:
        prior = previous.get(row["asset"])
        if not prior:
            continue
        d = diff_snapshots(prior, row)
        if d["drifted"]:
            drifts.append(d)

    # Resolved LAZILY: the bar costs a schedule read, and on a healthy run there is nothing to
    # classify. (It also keeps the fast gate free of network IO on every all-OK case.)
    if expected_from is None and any(r.get("status") != "OK" for r in rows or []):
        expected_from = data_expected_from(season)
    unexpected, expected_absent = classify_unreadable(
        rows, previous, now=now, expected_from=expected_from
    )

    watched_missing = {r["asset"]: r["watched_missing"] for r in rows if r["watched_missing"]}
    manifest = {
        "season": season, "now": now.isoformat(), "assets": len(rows),
        # The FULL list stays the record; only the ESCALATING subset drives the page.
        "unreadable": sorted(r["asset"] for r in rows if r["status"] != "OK"),
        "unreadable_unexpected": unexpected,
        "unreadable_expected_absent": expected_absent,
        "data_expected_from": expected_from.isoformat() if expected_from else None,
        # The FULL state, reported every run regardless of paging — the record must not shrink
        # just because a condition is accepted.
        "watched_missing": watched_missing,
        # The paging driver: only what the accepted baseline does NOT already cover.
        "watched_missing_new": new_watched_missing(watched_missing),
        "watched_missing_accepted": accepted_watched_missing(watched_missing),
        # A baseline entry that is PRESENT again — the mute is now stale and should be dropped.
        "accepted_missing_resolved": resolved_accepted_missing(rows),
        "watched_all_null": {r["asset"]: r["watched_all_null"] for r in rows if r["watched_all_null"]},
        "drifts": drifts, "written": 0, "skipped_duplicate": 0, "skipped_recapture": 0,
        "revisions": [], "escalate": False,
    }

    watched_drift = [d for d in drifts if d["watched_affected"]]
    if watched_drift or manifest["watched_missing_new"] or manifest["unreadable_unexpected"]:
        manifest["escalate"] = True
        log.warning(
            "ALERT [nfl/pit/schema] WATCHED nflverse columns changed/missing — "
            "drift=%s newly_missing=%s unreadable=%s. This is the 2025 silent-deletion class; "
            "any consumer of these columns must be re-verified before the next build.",
            [(d["asset"], d["watched_affected"]) for d in watched_drift],
            manifest["watched_missing_new"], manifest["unreadable_unexpected"],
        )
    elif drifts:
        log.info("[nfl/pit/schema] non-watched schema drift on %s", [d["asset"] for d in drifts])

    if expected_absent:
        log.info(
            "[nfl/pit/schema] %d asset(s) not published for season %s yet (EXPECTED, NOT paged; "
            "season-scoped nflverse assets appear as data does — anything still absent after %s "
            "escalates): %s",
            len(expected_absent), season, expected_from.date().isoformat(), expected_absent,
        )
    # Visible in every run log, but never a page: these are the already-triaged 2025 breaks.
    if manifest["watched_missing_accepted"]:
        log.info(
            "[nfl/pit/schema] accepted-baseline columns still missing (known, NOT paged): %s",
            manifest["watched_missing_accepted"],
        )
    # A restored column is good news, not an incident — but the baseline is now stale, and a stale
    # mute is exactly how a NEW deletion of the same column would later go unnoticed.
    if manifest["accepted_missing_resolved"]:
        log.warning(
            "[nfl/pit/schema] accepted-baseline columns are BACK: %s — drop them from "
            "ACCEPTED_MISSING so a future deletion pages again, and re-check whether the vendor "
            "as-of stamp can now be used.",
            manifest["accepted_missing_resolved"],
        )

    if rows and not dry_run:
        # REVISION semantics: an asset schema is expected to be STABLE, so a changed payload is
        # exactly the silent-deletion signature this leg exists to surface.
        written = store.append_captures(
            rows, source=CAPTURE_SOURCE, bucket=bucket, local_root=local_root,
            semantics=store.REVISION_SEMANTICS,
        )
        manifest.update(
            {k: written[k] for k in ("written", "skipped_duplicate", "skipped_recapture", "revisions")}
        )
    return manifest


def _latest_by_asset(season: int, *, bucket=None, local_root=None) -> dict:
    """The most recent stored snapshot per asset (best-effort — a missing store is a first run)."""
    try:
        from deltalake import DeltaTable
        from deltalake.exceptions import TableNotFoundError

        from ..ingest import s3io
        from .duck import connect
    except ImportError:  # pragma: no cover
        return {}

    uri = store.table_uri(CAPTURE_SOURCE, bucket=bucket, local_root=local_root)
    opts = s3io.storage_options() if uri.startswith("s3://") else None
    try:
        dt = DeltaTable(uri, storage_options=opts)
    except TableNotFoundError:
        return {}

    con = connect(httpfs=False)  # box-aware; a Delta/pyarrow read needs no httpfs
    con.register("snaps", dt.to_pyarrow_dataset())
    try:
        # `status` is what separates "we saw this asset and it was fine" from "we have never had
        # a readable snapshot of it" — the whole basis of `classify_unreadable`. Selecting only
        # the column list would force that judgement onto an empty-list proxy.
        have = {str(r[0]).lower() for r in con.execute("DESCRIBE snaps").fetchall()}
        rows = con.execute(prior_snapshot_sql(have), [int(season)]).fetchall()
    finally:
        con.unregister("snaps")

    # The stored row keeps the column list + types (not the nested payload), so the diff sees a
    # faithful schema. A row written before `column_types` existed yields `""` per column, which
    # `diff_snapshots` treats as UNKNOWN — degrading to a name-set diff rather than declaring
    # every column retyped.
    def _cols(names, types):
        names = list(names or [])
        types = list(types or [])
        types += [""] * (len(names) - len(types))
        return [{"name": n, "type": t or ""} for n, t in zip(names, types)]

    return {
        r[0]: {
            "asset": r[0],
            "schema_fingerprint": r[1],
            "status": r[4],
            "payload": {"columns": _cols(r[2], r[5]), "null_rates": {}},
        }
        for r in rows
    }
