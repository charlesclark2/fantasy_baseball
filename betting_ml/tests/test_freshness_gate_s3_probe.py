"""E11.20 phase-2 — the 30.13 serving-freshness gate's Snowflake-free probe.

WHY THIS EXISTS. The gate anchors staleness on
`information_schema.tables.last_altered` for FEATURE_PREGAME_GAME_FEATURES_RAW and
EB_BULLPEN_POSTERIORS. Those timestamps only advance while the SNOWFLAKE leg of the
pregame W8b family is still being rebuilt — so the moment that leg is gated off, the
anchor FREEZES, `lag_min` grows without bound and the gate reports STALE on a perfectly
fresh S3 feature store → a slate-wide false abstain. Same failure shape as INC-25 / the
spine-freeze: a cutover silently invalidates a freshness ANCHOR, not the data.

Two invariants are load-bearing and are asserted here:

  1. The S3 probe exists and returns the SF row's fields in the SAME positional order
     (the caller unpacks positionally — order is the contract, per `_aux_query`).
  2. It is behind its OWN default-OFF flag (`W8B_FRESHNESS_S3`) AND requires --s3 mode.
     `predict_today` ALREADY runs with --s3 on the daily path (W7B_LAKEHOUSE_S3=1 since
     phase-2a), so keying the branch off `_PREDICT_S3_MODE` alone would have cut the gate
     over the instant it merged — which today would abstain the whole slate, because the
     S3 `eb_starter_posteriors` parquet does not yet carry the live slate (verified
     2026-07-27: Snowflake 23 rows for the slate, S3 0; S3's newest row is 7/24).

Mostly source-inspection: importing predict_today pulls the full scoring stack, which is
not fast-gate material. The flag logic is exercised for real via a lightweight import.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "scripts" / "predict_today.py").read_text()


def test_s3_probe_exists_and_is_snowflake_free():
    assert "_FRESHNESS_QUERY_S3" in SRC and "def _freshness_probe_s3" in SRC, (
        "the S3 twin of the freshness probe is missing — gating off the pregame W8b "
        "Snowflake leg would freeze `last_altered` and abstain every game."
    )
    probe = SRC.split("def _freshness_probe_s3")[1].split("\ndef ")[0]
    assert "get_snowflake_connection" not in probe, (
        "the S3 probe must not open a Snowflake connection — it exists precisely to "
        "remove the last SF read from the serving freshness gate."
    )
    assert "information_schema" not in _query_body(), (
        "_FRESHNESS_QUERY_S3 must not read information_schema — that is the Snowflake "
        "metadata anchor the S3 probe replaces with the parquet's LastModified."
    )


def _query_body() -> str:
    return SRC.split("_FRESHNESS_QUERY_S3 = \"\"\"")[1].split('"""')[0]


def test_probe_returns_the_same_positional_contract():
    """The caller unpacks `ingest_epoch, gf_build_epoch, bullpen_build_date, score_day,
    starter_missing, starter_total` positionally from EITHER backend — a reordered
    return would silently compare a date against an epoch."""
    probe = SRC.split("def _freshness_probe_s3")[1].split("\ndef ")[0]
    returned = probe.split("return (")[1].split("\n    )")[0]
    order = [
        returned.index("ingest_epoch"),
        returned.index("gf_mtime.timestamp()"),
        returned.index("bullpen_mtime.astimezone"),
        returned.index("target_date"),
        returned.index("starter_missing"),
        returned.index("starter_total"),
    ]
    assert order == sorted(order), (
        "the S3 probe's return tuple drifted out of the Snowflake row's column order."
    )


def test_probe_is_behind_its_own_default_off_flag():
    assert re.search(
        r'os\.environ\.get\(_FRESHNESS_S3_ENV\)\s*==\s*"1"\s*and\s*_PREDICT_S3_MODE',
        SRC,
    ), (
        "_freshness_probe_is_s3 must require BOTH W8B_FRESHNESS_S3=1 AND --s3 mode. "
        "predict_today already runs --s3 on the daily path, so branching on "
        "_PREDICT_S3_MODE alone is an IMMEDIATE cutover the moment this merges."
    )
    assert 'if _freshness_probe_is_s3():' in SRC, (
        "_serving_freshness_stale must branch on the paired gate, not on --s3 directly."
    )


def test_s3_query_casts_the_varchar_ingestion_timestamp():
    """INC-23: `ingestion_ts` is an ISO VARCHAR in the parquet (the binary-timestamp
    cure), so `max()` on it without a cast compares lexically, and any date fn binds
    VARCHAR. Cast at the use-site."""
    body = _query_body()
    assert "ingestion_ts::timestamp" in body, (
        "ingestion_ts is VARCHAR in the S3 parquet — cast it at the use-site (INC-23)."
    )
    assert "try_to_date(" not in body, (
        "try_to_date is Snowflake-only; the DuckDB twin must use try_cast(... as date)."
    )


def test_bullpen_build_date_uses_the_baseball_day_tz():
    """The Snowflake twin reads `last_altered` in the SF session tz = the canonical
    baseball day. The S3 mtime is UTC, so it must be converted before the date is taken
    or the two branches disagree for any build landing in the UTC-evening window."""
    assert "astimezone(BASEBALL_DAY_TZ)" in SRC, (
        "convert the S3 LastModified into BASEBALL_DAY_TZ before comparing its DATE to "
        "the score day — never compare an mtime against a raw UTC clock."
    )


def test_s3_client_uses_the_instance_role_safe_helper():
    """W7b-1 AKID landmine: AWS_ACCESS_KEY_ID is UNSET on the box, so passing
    `aws_access_key_id=os.environ.get(...)` (=None) disables boto3's credential chain."""
    probe = SRC.split("def _s3_last_modified")[1].split("\ndef ")[0]
    assert "make_s3_client()" in probe, (
        "use scripts.utils.lakehouse_raw_writer.make_s3_client() — never hand-build a "
        "boto3 client in a box-executed path."
    )
    assert "boto3.client(" not in probe, (
        "hand-building the client here re-opens the AKID footgun; delegate to the "
        "shared helper (test_boto3_credential_lint.py guards the general case)."
    )


def test_s3_last_modified_failure_degrades_to_unknown_not_stale():
    """A head_object failure must yield None (→ that limb is skipped), never a value
    that trips the gate. The gate is a safety net; it must not become a new blocker."""
    probe = SRC.split("def _s3_last_modified")[1].split("\ndef ")[0]
    assert "return None" in probe and "except Exception" in probe
