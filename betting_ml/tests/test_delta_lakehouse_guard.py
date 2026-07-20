"""E11.20 — Delta-lakehouse rollout guards (fast gate).

Mechanical invariants for the Delta migration, in the repo's source-inspection style
(fast-gate rule: inspect source or import from betting_ml/scripts utilities — NEVER
import `pipeline`, whose __init__ reads the dbt manifest absent in the fast gate):

  1. The registry is PURE (no heavy imports) and its mode parsing is loud on typos.
  2. The write/read predicates agree with the mode semantics (mirror writes but does
     not read Delta; cutover does both; off does neither).
  3. DELTA_W1_TABLES == run_w1_lakehouse.MART_MODELS *exactly* — a W1 mart added to the
     builder but not the registry would WRITE Delta (the build loops MART_MODELS) while
     every reader resolved the frozen legacy parquet: the INC-31 stale-key class by
     construction. Set equality makes that drift impossible to merge.
  4. The AKID landmine (W7b-1) in delta-rs dress: storage_options() must NEVER emit a
     None/empty AWS key (behavioral test, not just a lint).
  5. Vacuum retention is floored at 168h (spike gotcha #3 — below it, time-travel is
     physically destroyed) and merge predicates must pin the partition column
     (spike gotcha #8 — else the MERGE scans all history).
  6. The decomposed daily job wires the lakehouse waves in the load-bearing order
     (schedule export → W1 → W2 → W3 → W3pre → W6 → W7b → spine → W8a → W8b → W11 →
     ext-refresh), and every read choke point carries the delta_scan branch.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

REGISTRY_SRC = (REPO / "betting_ml" / "utils" / "delta_lakehouse.py").read_text()
DELTA_LAKE_SRC = (REPO / "scripts" / "utils" / "delta_lake.py").read_text()
BUILDER_SRC = (REPO / "scripts" / "run_w1_lakehouse.py").read_text()
OPS_SRC = (REPO / "pipeline" / "ops" / "daily_ingestion_ops.py").read_text()
JOB_SRC = (REPO / "pipeline" / "jobs" / "daily_ingestion_job.py").read_text()
READ_SRC = (REPO / "scripts" / "utils" / "lakehouse_read.py").read_text()
MONITOR_SRC = (REPO / "betting_ml" / "utils" / "lakehouse_monitor.py").read_text()
REFRESH_SRC = (REPO / "scripts" / "refresh_w1_external_tables.py").read_text()


# ── 1+2: registry purity + mode semantics ────────────────────────────────────────────

def test_registry_is_pure_stdlib():
    # The registry is imported by sensors (lakehouse_monitor) and lean contexts —
    # importing it must never drag in heavy deps.
    for forbidden in ("import deltalake", "import duckdb", "import boto3",
                      "import pandas", "import polars", "import pyarrow",
                      "import betting_ml", "from betting_ml"):
        assert forbidden not in REGISTRY_SRC, f"registry must stay pure stdlib: {forbidden}"


def test_registry_siblings_are_byte_identical():
    # The registry has TWO homes (betting_ml for sensors/builder; scripts/utils for the
    # lean-image-copied read helpers, which may not carry a betting_ml import node —
    # test_lean_capture_images_selfcontained). Drift between them would split the
    # write/read semantics across contexts — keep them byte-identical.
    sibling = (REPO / "scripts" / "utils" / "delta_lakehouse.py").read_text()
    assert sibling == REGISTRY_SRC, (
        "scripts/utils/delta_lakehouse.py must be byte-identical to "
        "betting_ml/utils/delta_lakehouse.py — edit one, copy to the other"
    )


def test_mode_parsing_and_predicates(monkeypatch):
    from betting_ml.utils import delta_lakehouse as reg

    monkeypatch.delenv(reg.DELTA_W1_MODE_ENV, raising=False)
    assert reg.delta_w1_mode() == "off"
    assert not reg.delta_write_enabled("mart_pitch_play_event")
    assert not reg.delta_read_enabled("mart_pitch_play_event")

    monkeypatch.setenv(reg.DELTA_W1_MODE_ENV, "mirror")
    assert reg.delta_write_enabled("mart_pitch_play_event")
    assert not reg.delta_read_enabled("mart_pitch_play_event"), \
        "mirror mode must keep reads on the authoritative parquet"

    monkeypatch.setenv(reg.DELTA_W1_MODE_ENV, "cutover")
    assert reg.delta_write_enabled("mart_pitch_play_event")
    assert reg.delta_read_enabled("mart_pitch_play_event")
    # non-registry tables are never Delta-routed regardless of mode
    assert not reg.delta_read_enabled("mart_game_spine")

    # a typo'd mode must raise LOUDLY, never silently read as 'off'
    monkeypatch.setenv(reg.DELTA_W1_MODE_ENV, "cutovr")
    with pytest.raises(ValueError):
        reg.delta_w1_mode()


# ── 3: registry ↔ builder set equality ───────────────────────────────────────────────

def test_registry_matches_builder_w1_list():
    from betting_ml.utils.delta_lakehouse import DELTA_W1_TABLES

    m = re.search(r"^MART_MODELS = \[(.*?)\]", BUILDER_SRC, re.DOTALL | re.MULTILINE)
    assert m, "could not parse MART_MODELS from run_w1_lakehouse.py"
    builder_w1 = set(re.findall(r'"(\w+)"', m.group(1)))
    assert builder_w1 == set(DELTA_W1_TABLES), (
        "DELTA_W1_TABLES must equal run_w1_lakehouse.MART_MODELS exactly — a mart in one "
        "but not the other splits the write and read paths across stores (INC-31 class). "
        f"diff: {builder_w1 ^ set(DELTA_W1_TABLES)}"
    )


# ── 4: the AKID landmine, behaviorally ───────────────────────────────────────────────

def test_storage_options_never_emits_empty_creds(monkeypatch):
    import sys
    sys.path.insert(0, str(REPO))
    from scripts.utils import delta_lake
    from scripts.utils.delta_lake import storage_options

    # Pin the botocore-chain fallback to "no credentials found" so these asserts test the
    # env handling, not whatever this machine's ambient AWS profile resolves to.
    monkeypatch.setattr(delta_lake, "_chain_credentials", lambda: None)

    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    opts = storage_options()
    assert "AWS_ACCESS_KEY_ID" not in opts and "AWS_SECRET_ACCESS_KEY" not in opts, \
        "unset env keys (+ an empty chain) must yield NO cred entries — never empty strings"
    assert opts.get("AWS_REGION") == "us-east-2", \
        "region must be PINNED to the artifacts bucket, never inherited from AWS_DEFAULT_REGION"

    # an ambient AWS_DEFAULT_REGION (e.g. a us-east-1 laptop/serving env) must NOT leak in
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    assert storage_options()["AWS_REGION"] == "us-east-2"

    # key without secret (half-configured env) must also fall through to the chain
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    opts = storage_options()
    assert "AWS_ACCESS_KEY_ID" not in opts

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    opts = storage_options()
    assert opts["AWS_ACCESS_KEY_ID"] == "AKIAEXAMPLE"


def test_storage_options_resolves_the_chain_when_env_is_empty_strings(monkeypatch):
    """The 2026-07-12 box --delta-full failure: compose `${AWS_ACCESS_KEY_ID}` of an
    UNSET host var lands in the container as an EMPTY STRING; delta-rs's object_store
    reads the env ITSELF and signs with the empty AKID (AuthorizationHeaderMalformed)
    unless storage_options passes explicit credentials. So with empty-string env,
    storage_options must (a) not forward the empty strings and (b) forward the
    botocore-chain credentials (the instance role on the box) explicitly."""
    import sys
    from collections import namedtuple

    sys.path.insert(0, str(REPO))
    from scripts.utils import delta_lake

    Frozen = namedtuple("Frozen", "access_key secret_key token")
    monkeypatch.setattr(delta_lake, "_chain_credentials",
                        lambda: Frozen("AKIAROLE", "rolesecret", "roletoken"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    opts = delta_lake.storage_options()
    assert opts["AWS_ACCESS_KEY_ID"] == "AKIAROLE", \
        "empty-string env must be ignored and the chain-resolved role creds passed explicitly"
    assert opts["AWS_SECRET_ACCESS_KEY"] == "rolesecret"
    assert opts["AWS_SESSION_TOKEN"] == "roletoken", \
        "instance-role creds are temporary — dropping the session token breaks the signature"

    # a chain hit WITHOUT a token (plain long-lived keys in a profile) must omit the token key
    monkeypatch.setattr(delta_lake, "_chain_credentials",
                        lambda: Frozen("AKIAPROF", "profsecret", None))
    opts = delta_lake.storage_options()
    assert opts["AWS_ACCESS_KEY_ID"] == "AKIAPROF" and "AWS_SESSION_TOKEN" not in opts


# ── 5: retention floor + partition-pinned merge ─────────────────────────────────────

def test_retention_floor_is_168_and_clamped():
    from betting_ml.utils.delta_lakehouse import DELTA_MIN_RETENTION_HOURS

    assert DELTA_MIN_RETENTION_HOURS >= 168, \
        "vacuum below 168h physically destroys time-travel (spike gotcha #3)"
    assert "retention_hours < DELTA_MIN_RETENTION_HOURS" in DELTA_LAKE_SRC
    assert "retention_hours = DELTA_MIN_RETENTION_HOURS" in DELTA_LAKE_SRC, \
        "compact_and_vacuum must CLAMP a too-low retention, not just warn"


def test_merge_predicate_must_pin_partition(monkeypatch):
    import sys
    sys.path.insert(0, str(REPO))
    from scripts.utils.delta_lake import merge_upsert

    with pytest.raises(ValueError, match="partition column"):
        merge_upsert("mart_pitch_play_event", None, "t.game_pk = s.game_pk")


# ── 6: decomposition wiring + choke-point coverage ──────────────────────────────────

def test_daily_job_wires_lakehouse_waves_in_order():
    ordered_calls = [
        "lakehouse_schedule_export_op(",
        "lakehouse_w1_pitch_marts_op(",
        "lakehouse_w2_marts_op(",
        "lakehouse_w3_marts_op(",
        "lakehouse_w3pre_flatten_op(",
        "lakehouse_w6_odds_marts_op(",
        "lakehouse_w7b_serving_op(",
        "lakehouse_spine_odds_bridge_op(",
        "lakehouse_w8a_feature_layer_op(",
        "lakehouse_w8b_aggregator_op(",
        "lakehouse_w11_nightly_op(",
        "refresh_w1_external_tables_op(",
    ]
    body = JOB_SRC[JOB_SRC.index("def daily_ingestion_job"):]
    positions = [body.index(c) for c in ordered_calls]  # raises if any op is unwired
    assert positions == sorted(positions), (
        "the decomposed lakehouse ops must keep the monolith's order — the invariants "
        "(spine before bridge, W8a before W8b, W11d after W8b) are load-bearing"
    )


def test_wave_ops_pass_their_wave_flags():
    for op_name, flag in [
        ("lakehouse_w1_pitch_marts_op", '"--w1-only"'),
        ("lakehouse_w2_marts_op", '"--w2-only"'),
        ("lakehouse_w3_marts_op", '"--w3-only"'),
        ("lakehouse_w6_odds_marts_op", '"--w6-only"'),
    ]:
        body = OPS_SRC[OPS_SRC.index(f"def {op_name}"):]
        body = body[:body.index("\n@op")]
        assert flag in body, f"{op_name} must invoke run_w1_lakehouse.py {flag}"


def test_gated_wave_ops_skip_loudly():
    # ALERT-tier contract: a gated-off wave logs a WARNING, never an invisible `if`.
    for op_name in (
        "lakehouse_w3pre_flatten_op", "lakehouse_w7b_serving_op",
        "lakehouse_spine_odds_bridge_op", "lakehouse_w8a_feature_layer_op",
        "lakehouse_w8b_aggregator_op", "lakehouse_w11_nightly_op",
        "lakehouse_delta_maintenance_op",
    ):
        body = OPS_SRC[OPS_SRC.index(f"def {op_name}"):]
        next_op = body.find("\n@op")
        body = body[:next_op] if next_op != -1 else body
        assert "context.log.warning" in body, \
            f"{op_name}: a gated skip / caught failure must call context.log.warning"


def test_read_choke_points_carry_delta_branch():
    for name, src in [("lakehouse_read", READ_SRC), ("lakehouse_monitor", MONITOR_SRC)]:
        assert "delta_read_enabled(" in src and "delta_scan_view_sql(" in src, \
            f"{name} must route Delta-backed tables through delta_scan under cutover"
    # the builder's own three registration helpers too
    assert BUILDER_SRC.count("delta_read_enabled(") >= 3, \
        "run_w1_lakehouse view registration (_register_mart_views/_register_s3_glob_views/" \
        "_register_w8a_views) must all be Delta-aware"


def test_refresh_script_w1_retired_from_daily_refresh():
    # E11.20 PHASE 1.5 (2026-07-20): the SF mart_pitch_* objects are DROPPED, so the W1
    # tables must be OUT of the daily refresh entirely — refreshing a dropped ext table
    # raises → the refresh op is HALT-tier → the whole daily job dies. (This inverts the
    # phase-1 pin that kept W1 REQUIRED for the compat mirror.)
    default_required = REFRESH_SRC[REFRESH_SRC.index("required = (set(STG_BATTER_PITCHES_TABLE)"):]
    refresh_call = default_required[default_required.index("_refresh("):]
    refresh_call = refresh_call[:refresh_call.index(")")]
    default_required = default_required[:default_required.index("_refresh(")]
    assert "set(W1_TABLES)" not in default_required, (
        "W1_TABLES must NOT be in the default REQUIRED refresh set — the SF mart_pitch_* "
        "ext tables are dropped (phase 1.5); refreshing them HALTs the daily"
    )
    assert "W1_TABLES" not in refresh_call, (
        "W1_TABLES must NOT be in the daily _refresh() list at all — even best-effort "
        "refreshes of dropped ext tables are daily error noise"
    )


def test_builder_daily_delta_is_partition_scoped_with_empty_guard():
    body = BUILDER_SRC[BUILDER_SRC.index("def _build_w1_marts"):]
    body = body[:body.index("\ndef _raw_source_for")]
    assert "overwrite_partition(" in body
    assert "num_rows == 0" in body, \
        "an empty season slice must SKIP (an empty replaceWhere would delete the partition)"
    assert "create_ok=delta_full" in body, \
        "auto-creating a Delta table on the daily path would serve a silent partial table"


def test_builder_cutover_writes_sf_compat_mirror_and_retires_legacy_key():
    # PHASE 1.5 update (2026-07-20): the SF-compat season mirror is RETIRED by default —
    # its write + season self-heal must BOTH be gated on _sf_compat_mirror_enabled()
    # (W1_SF_COMPAT_MIRROR=1 = the rollback path). Without the gate, deleting the mirror
    # S3 files after the SF drop is futile: the self-heal rebuilds every season next run.
    # The mirror code path itself must survive (rollback), as must the legacy-key
    # retirement (glob-dup guard — unconditional).
    body = BUILDER_SRC[BUILDER_SRC.index("def _build_w1_marts"):]
    body = body[:body.index("\ndef _raw_source_for")]
    assert "season_{year}/data.parquet" in body, \
        "the SF-compat mirror write path must survive for rollback (W1_SF_COMPAT_MIRROR=1)"
    assert body.count('if mode == "cutover" and _sf_compat_mirror_enabled()') >= 2, (
        "BOTH the compat-mirror season self-heal AND the season-mirror COPY must be "
        "gated on _sf_compat_mirror_enabled() — an ungated leg either rebuilds the "
        "mirror after the SF drop (self-heal) or keeps writing dead files (COPY)"
    )
    helper_src = BUILDER_SRC[BUILDER_SRC.index("def _sf_compat_mirror_enabled"):]
    helper_src = helper_src[:helper_src.index("\ndef ")]
    assert '"W1_SF_COMPAT_MIRROR", "0"' in helper_src, \
        "the compat mirror must default OFF (phase 1.5 — the SF objects are dropped)"
    assert "_retire_legacy_w1_parquet(" in body, \
        "cutover must retire the legacy data.parquet (glob-dup guard)"
    # the compat dir name must NOT be hive `key=value` style — DuckDB hive-partition
    # inference would fabricate a phantom column from the path
    assert "season={year}" not in body and "game_year={year}/data.parquet" not in body
    # the retire helper must raise on delete failure (silent failure = double-count)
    helper = BUILDER_SRC[BUILDER_SRC.index("def _retire_legacy_w1_parquet"):]
    helper = helper[:helper.index("\ndef _build_w1_marts")]
    assert "make_s3_client" in helper, \
        "legacy-key retirement must use the shared instance-role-safe S3 client (AKID landmine)"
