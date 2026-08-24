"""query_lake.py  (NCAAF-P0.2 — the DuckDB-over-lake parity tool, sport_data_platform.md §7A)
==============================================================================================
The first-class dev-loop affordance: query the sports lake via DuckDB with ZERO connection
boilerplate — the parity tool to the Snowflake MCP (there is no warehouse to resume, no
credits, instant). Every later NCAAF session explores the lake through here.

  from quant_sports_intel_models.football.ncaaf.ingest.query_lake import q, delta
  q("select season, count(*) from delta('games') group by 1 order by 1")
  q("select raw_json->>'homeTeam' t from delta('games') limit 5")

`delta(source)` expands to `delta_scan('s3://<bucket>/ncaaf/raw/<source>')`. The raw tier is
Delta, so reads go through DuckDB's (read-only) `delta` extension. AWS creds resolve via the
credential chain (same instance-role / env the writers use); region is pinned per resource.
"""
from __future__ import annotations

import logging
import os
import re

from . import s3io

log = logging.getLogger(__name__)

_con = None


def _connect():
    global _con
    if _con is not None:
        return _con
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute("INSTALL delta; LOAD delta")
    try:
        con.execute(
            f"CREATE OR REPLACE SECRET sports_s3 "
            f"(TYPE S3, PROVIDER credential_chain, REGION '{s3io.DEFAULT_REGION}')"
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; see note below
        # `credential_chain` VALIDATES eagerly at CREATE-SECRET time, so an environment with NO
        # AWS credential source anywhere (env / profile / IMDS role — e.g. a CI sandbox that
        # intentionally mocks all external IO) fails HERE, before any query even runs. A query
        # that only reads a LOCAL path (`local()`) never needs this secret, so don't let its
        # absence break local-only usage — a query that DOES need S3 (`delta()`) will still fail
        # naturally, with a clear credentials error, at actual S3 access.
        log.debug("sports_s3 credential-chain secret unavailable (%s) — local-only reads still "
                  "work; an S3 read will fail at actual access, not here.", str(exc)[:160])
    _con = con
    return con


def delta(source: str, *, sport: str = "ncaaf", tier: str = "raw", bucket: str | None = None) -> str:
    """A `delta_scan(...)` expression for a lake source — drop it into a FROM clause."""
    uri = s3io.table_uri(sport, source, bucket=bucket or s3io.DEFAULT_BUCKET, tier=tier)
    return f"delta_scan('{uri}')"


def local(source: str, root: str, *, sport: str = "ncaaf", tier: str = "raw") -> str:
    """A `delta_scan(...)` for a LOCAL-FS Delta table (the offline smoke output)."""
    return f"delta_scan('{s3io.local_table_uri(root, sport, source, tier=tier)}')"


def q(sql: str):
    """Run SQL against the lake; returns a pandas DataFrame. Use delta('<source>') in FROM."""
    return _connect().sql(sql).df()


# ── "absent table" vs "transient read failure" (the destructive-overwrite guard) ────────────
#
# ⭐ ONE implementation, several callers. Every READ-MERGE-WRITE writer in this vertical
# (`odds_recurring_capture`, `game_prediction_snapshot`) preserves what is already in the lake by
# READING it first — so "I could not read it" must NEVER be indistinguishable from "there is
# nothing there yet." The second is a licence to overwrite; the first is a bug that silently
# deletes every prior week. A real CI flake (a read-after-write `delta_scan` hiccup on a partition
# the same run had just written) proved that swallowing any read exception into `None` loses data.
# Two renderers of this rule would be two rule sets (the E9.61 lesson), so it lives here.
#
# 🩹 NCAAF-LAKE1 (2026-08-24) — THIS USED TO MATCH THE ENGINE'S ERROR MESSAGE, AND THAT WAS WRONG
# ON THE ONE SUBSTRATE PRODUCTION ACTUALLY USES.
#
# The retired implementation asked `is_missing_table_error(exc)`, matching
# ("InvalidTableLocationError", "Path does not exist") in the exception text. That was verified
# empirically when written — against a LOCAL directory, which is what the tests exercise
# (`tmp_path`). Production reads S3, and the two substrates report absence DIFFERENTLY, because an
# object store has no directories:
#
#     local path never created      → "InvalidTableLocationError … Path does not exist"   ✅ matched
#     local dir exists, no log      → "Generic delta kernel error: No files in log segment" ❌ missed
#     S3 prefix never written       → "Generic delta kernel error: No files in log segment" ❌ missed
#
# (All three measured on duckdb 1.5.3 AND 1.5.5; the local case is unchanged across both, so this
# was never a dependency regression — the marker set simply never covered S3.)
#
# The consequence was not theoretical. `game_prediction_snapshot.write_snapshot` reads its table
# back BEFORE its first-ever write — correctly, that IS the never-lose-a-prior-week contract — so
# on S3 a never-written table became UNBOOTSTRAPPABLE: the read raised instead of returning
# "nothing to preserve", and NCAAF-PS could not create its own snapshot tables at all. The guard
# that should have caught it passed, because it asked the question on a local directory.
#
# ⇒ THE FIX IS TO STOP CLASSIFYING BY MESSAGE. "Does this table exist?" is a question about the
# STORE, and the store can be asked directly: list `<table>/_delta_log/` and see whether any commit
# is there. That answer is substrate-correct by construction, needs no per-engine string, and
# cannot rot when a dependency rewords an error.
#
# ⭐ AND IT FAILS SAFE ON THE HAZARD THE OLD NARROWNESS EXISTED TO PROTECT. A read-after-write
# visibility blip means the log file IS present — so the listing FINDS it, `_table_has_commits`
# returns True, and we RAISE rather than reporting "absent". S3 has been strongly read-after-write
# consistent for LIST since Dec 2020, so the check is not itself a race. Anything we cannot
# determine (no boto3, denied listing, a URI we cannot parse) returns None and also RAISES — the
# only direction that can lose data is "absent", and nothing reaches it by accident.
#
# ⛔ The message-matching path is REMOVED rather than kept as a fallback: a dead fallback that
# message-matches is the same bomb on a longer fuse.

#: Pulls every `delta_scan('<uri>')` target out of a lake SELECT. The callers all build their SQL
#: through `delta()` / `local()`, which emit exactly this form.
_DELTA_SCAN_RE = re.compile(r"delta_scan\(\s*'([^']+)'")


def delta_scan_targets(sql: str) -> tuple[str, ...]:
    """The Delta table URIs a lake SELECT reads. Empty ⇒ we cannot tell what it touches."""
    return tuple(_DELTA_SCAN_RE.findall(sql))


def _table_has_commits(uri: str) -> bool | None:
    """Does the Delta table at `uri` hold at least one committed `_delta_log` file?

    True  — it exists (so a read failure is something OTHER than absence).
    False — it provably holds no commit: a genuine first-ever-write situation.
    None  — UNDETERMINED (no boto3, a denied listing, an unparseable URI). Never guessed.

    Deliberately a listing rather than a read: it answers the existence question without going
    through the engine whose error text we no longer trust.
    """
    try:
        if uri.startswith("s3://"):
            import boto3

            bucket, _, key = uri[len("s3://"):].partition("/")
            if not bucket:
                return None
            # ⛔ region pinned PER RESOURCE, never inherited from a serving env's
            # AWS_DEFAULT_REGION (INC-45); and NO explicit aws_access_key_id — passing a `None`
            # from an unset env var DISABLES boto3's credential chain on the box (the AKID
            # landmine), so the instance role must be left to resolve itself.
            client = boto3.client("s3", region_name=s3io.DEFAULT_REGION)
            prefix = f"{key.rstrip('/')}/_delta_log/" if key else "_delta_log/"
            resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
            return int(resp.get("KeyCount", 0)) > 0
        log_dir = os.path.join(uri, "_delta_log")
        if not os.path.isdir(log_dir):
            return False
        return any(os.scandir(log_dir))
    except Exception as exc:  # noqa: BLE001 — an undetermined answer is never "absent"
        log.warning("could not determine whether the Delta table at %s exists (%s) — treating the "
                    "read failure as REAL rather than as an absent table", uri, exc)
        return None


def table_is_absent(sql: str) -> bool:
    """True only when a table this SELECT reads provably holds NO committed Delta log.

    Conservative in every direction that matters: an unparseable SQL, an undetermined listing, or
    a set of tables that all exist all return False, which sends the caller down the RAISE path.
    """
    targets = delta_scan_targets(sql)
    if not targets:
        return False
    verdicts = [_table_has_commits(uri) for uri in targets]
    if any(v is None for v in verdicts):
        return False
    return any(v is False for v in verdicts)


def query_or_missing(sql: str, *, retries: int = 2, retry_sleep: float = 0.15):
    """Run a read-only lake SELECT. Returns the DataFrame, or `None` if the table
    genuinely does not exist yet (proven by LISTING the store — see `table_is_absent`). Any OTHER failure is retried a bounded number of times (a
    transient `delta_scan` hiccup usually clears within one retry) and then RAISED — never
    silently swallowed into "nothing there yet."

    A caller that cannot CONFIRM what is already in the lake must fail loud, never guess "empty."
    """
    import time

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return q(sql)
        except Exception as exc:  # noqa: BLE001 — inspected immediately below, never blindly swallowed
            if table_is_absent(sql):
                log.info("lake read failed and the table it reads holds NO committed Delta log — "
                         "reporting it as genuinely absent (a first-ever write). Verified by "
                         "LISTING the store, not by matching the engine's message (NCAAF-LAKE1).")
                return None
            last_exc = exc
            if attempt < retries:
                try:
                    _connect().execute("LOAD delta")  # defensive re-affirm; cheap, idempotent
                except Exception:  # noqa: BLE001 — best-effort; a persistent problem surfaces below
                    pass
                time.sleep(retry_sleep)
    raise RuntimeError(
        f"lake read failed {retries + 1}x and the table(s) it reads DO hold a Delta log (or we "
        f"could not determine it) — refusing to treat this as a missing table "
        f"this as 'nothing is there yet' (that would risk a destructive merge overwrite): "
        f"{last_exc}"
    ) from last_exc
