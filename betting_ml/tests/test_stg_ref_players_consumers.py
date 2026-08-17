"""
test_stg_ref_players_consumers.py   (E5.10 follow-up — the stg_ref_players staleness bomb; fast gate)
=====================================================================================================
``stg_ref_players`` was written by ``scripts/export_ref_players_to_s3.py``, whose own docstring said
"Run ONCE … re-run when ref_players changes". NOTHING ran it: no op, no schedule, no workflow. E5.10
measured the parquet 53 days stale with ZERO players at ``mlb_played_last = 2026``, and the batter-TB
serving writer silently skipped 34 batters. ~11 other consumers read the same frozen prefix.

⭐ AND THE FIX THE CARD PROPOSED WOULD NOT HAVE WORKED. The Snowflake source is itself dead:
``savant.ref_players`` has NO writer anywhere in the repo and reports ``last_altered = 2025-10-13``
(~308 days) with ``max(mlb_played_last) = 2025``. Scheduling the old export would have re-copied the
same 25,900 rows on a timer, refreshing the object mtime over frozen content — and an INC-41
freshness SLA on top of that reads GREEN forever. So the dimension is now MERGED from a live feed
(``build_ref_players_dimension.py``: ``player_profiles_raw`` over the archive) and the old export
was demoted to seeding ``stg_ref_players_archive/``.

WHAT THIS GUARD MECHANIZES — four distinct failure modes, one clause each:
  1. the dimension has a SCHEDULED WRITER wired into a job (the NF-INFRA1 "a table nothing writes"
     class this story exists to close);
  2. the writer is ordered DOWNSTREAM of the mirror it reads (INC-25), pinned as a DATA-FLOW EDGE
     via AST — not source-line order, which is vacuous under a topological executor;
  3. the dead-source export writes ONLY the archive prefix, never the live one (a regression here
     silently reinstates the frozen table under the name every consumer reads);
  4. the CONSUMER REGISTRY is EXHAUSTIVE — a per-consumer conclusion fails exactly where the list
     is incomplete, which is the whole lesson of INC-27 (the dbt DAG cannot see a raw SQL string)
     and INC-38 (a per-caller fix fails where the caller registry is short).

Every clause below is independently RED-provable, and each fixture is built so that ONLY the clause
under test can flip it — an ``and``-composed guard whose fixture trips a DIFFERENT clause proves
nothing (NF-D17). Pure source scan: no ``pipeline`` import, so it runs in the fast gate (E11.23 —
``pipeline/__init__.py`` reads the dbt manifest, which is absent there).
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

LIVE_PREFIX = "stg_ref_players"
ARCHIVE_PREFIX = "stg_ref_players_archive"

BUILDER = REPO / "scripts" / "build_ref_players_dimension.py"
ARCHIVE_EXPORT = REPO / "scripts" / "export_ref_players_to_s3.py"
WEEKLY_JOB = REPO / "pipeline" / "jobs" / "weekly_player_profiles_job.py"
DAILY_JOB = REPO / "pipeline" / "jobs" / "daily_ingestion_job.py"
OPS = REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"

BUILD_OP = "build_ref_players_dimension_op"
LAKEHOUSE_W1_OP = "lakehouse_w1_pitch_marts_op"
MIRROR_OP = "reexport_player_profiles_op"

# ── The MEASURED consumer registry ───────────────────────────────────────────────────────────
# Every file that reads the stg_ref_players dimension, found by grepping the WHOLE repo for the
# PREFIX STRING and the bare table name across .py/.sql — never `dbt ls`/the manifest (INC-27: a
# raw-SQL-string reader in a .py writer is a real consumer the DAG cannot see). Most of these read
# the S3 PREFIX directly, which is exactly why the fix rebuilds the ARTIFACT rather than repointing
# each consumer: one contract instead of 11 independent name resolutions free to drift (E9.61).
#
# ➕ IF YOU ADD A CONSUMER, ADD IT HERE — test_the_consumer_registry_is_exhaustive stays RED until
#    you do, so a new reader of this dimension cannot ship unnoticed.
CONSUMERS: dict[str, str] = {
    # ── Direct S3-prefix readers (raw strings; invisible to the dbt DAG) ──
    "betting_ml/scripts/batter_clustering/cluster_batters.py":
        "batter_id → player_name for the --s3 clustering build",
    "betting_ml/scripts/pitcher_clustering/cluster_pitchers.py":
        "pitcher_id → player_name for the --s3 clustering build",
    "betting_ml/scripts/cross_market_eval/eval_cross_market.py":
        "prop player_name → batter_id bridge (E5.3)",
    "betting_ml/scripts/prop_pricing/edge_devig_props.py":
        "prop name → modelled pitcher_id bridge",
    "betting_ml/scripts/build_zone_matchup.py":
        "best-effort id → name for the zone-matchup overlay (names are cosmetic)",
    "scripts/generate_zone_overlays_today.py":
        "best-effort id → name for today's zone overlays (names are cosmetic)",
    "scripts/build_batter_prop_substrate.py":
        "name_key/li_key join from prop names to batter_id",
    "scripts/write_batter_tb_projections.py":
        "display-name FALLBACK behind the posted-lineup feed (E5.10 repointed the primary)",
    # ── dbt models (DAG-visible) ──
    "dbt/models/mart/mart_pitch_hitter_profile.sql":
        "batter first/last/display name per pitch",
    "dbt/models/mart/mart_pitch_pitcher_profile.sql":
        "pitcher first/last/display name per pitch",
    # ── The lakehouse build that registers the view the two marts resolve ──
    "scripts/run_w1_lakehouse.py":
        "registers stg_ref_players as a DuckDB view so the mart refs resolve",
}

# Where a consumer could plausibly live. Docs/tests/roadmaps are excluded: they discuss the table
# rather than read it, and sweeping them in would make the exhaustiveness clause unmaintainable.
_SCAN_ROOTS = ("scripts", "pipeline", "app/backend", "betting_ml/scripts", "betting_ml/utils", "dbt/models")
_SCAN_SUFFIXES = (".py", ".sql")

# Files that MENTION the dimension without consuming it — the writer, the archive seed, and the
# dbt model that DEFINES it. Listed explicitly so the exhaustiveness scan cannot be silently
# widened to swallow a real consumer.
_NON_CONSUMERS = {
    "scripts/build_ref_players_dimension.py",   # the writer
    "scripts/export_ref_players_to_s3.py",      # the archive seed
    "dbt/models/staging/stg_ref_players.sql",   # the model that DEFINES the dimension
    # Hosts build_ref_players_dimension_op, which INVOKES the writer and names the dimension in
    # its alert text. A Dagster op shells out to a script; it never reads the parquet itself, so
    # it is a producer, not a consumer. Its wiring is asserted by the ordering clause above
    # instead — which is a stronger check than appearing in this list would be.
    "pipeline/ops/daily_ingestion_ops.py",
}


def _strip_comments(src: str, suffix: str) -> str:
    """Remove comments AND Python docstrings so a guard cannot be satisfied by PROSE.

    INC-38's lesson twice over: a source-inspection guard that matches anywhere in the file passes
    on the explanatory comment written above the very code it is checking.

    ⚠️ DOCSTRINGS ARE THE HALF THAT IS EASY TO MISS, and the first cut of this file missed it — a
    `#`-only strip left every module/function docstring in scope, so this story's OWN explanatory
    docstrings in bets.py, daily_ingestion_ops.py and ingest_player_profiles.py registered as
    consumers. A Python docstring is an expression statement, not a comment, so stripping it needs
    the AST. SQL block comments are stripped BEFORE line comments, or a `--` inside a /* */ block
    truncates the wrong span.
    """
    if suffix == ".sql":
        src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)   # block comments FIRST
        return "\n".join(l.split("--")[0] for l in src.splitlines())

    lines = [l for l in src.splitlines() if not l.lstrip().startswith("#")]
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:  # pragma: no cover — a `#`-strip inside a multiline string
        return "\n".join(lines)
    blanked = set()
    for node in ast.walk(tree):
        # A bare string expression statement == a docstring (or a block-comment-by-string).
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            blanked.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return "\n".join(l for i, l in enumerate(lines, start=1) if i not in blanked)


def _assigned_str_constants(path: pathlib.Path, name: str) -> list[str]:
    """Values assigned to a module-level `name = "..."`, read from the AST.

    Used instead of a regex over the file so the clause reads the CODE, never the prose that
    explains it — the failure the docstring note above describes.
    """
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                out.append(node.value.value)
    return out


def _read(path: pathlib.Path) -> str:
    return _strip_comments(path.read_text(), path.suffix)


# ── 1. The dimension has a scheduled writer ──────────────────────────────────────────────────

def test_the_dimension_has_a_scheduled_writer():
    """A table nothing writes on a schedule is a silent-staleness bomb (NF-INFRA1 / this story).

    The builder must exist AND be invoked by an op AND that op must be wired into a job. Checking
    only that the script exists would pass on the pre-fix world, where export_ref_players_to_s3.py
    also existed and was run by nothing at all.
    """
    assert BUILDER.exists(), f"{BUILDER} is missing — the dimension has no live writer"

    ops = _read(OPS)
    assert f"def {BUILD_OP}" in ops, f"{BUILD_OP} is not defined in {OPS.name}"
    assert "build_ref_players_dimension.py" in ops, (
        f"{BUILD_OP} does not invoke build_ref_players_dimension.py — the op is a shell"
    )

    # ⚠️ BOTH jobs, not "at least one". The first cut of this clause accepted either, and the RED
    # proof caught it: unwiring the DAILY pass left the guard green while silently dropping the
    # dimension to weekly-only. That is a real regression, not a cosmetic one — the profiles
    # WRITER is weekly, but mlb_played_first/last are derived from Statcast appearances, which
    # advance every night. Weekly-only means the column E5.10 found frozen lags up to 7 days for
    # every player who just debuted. A guard weaker than the invariant it names is the
    # vacuous-guard class (NF1.7(a)) in its quietest form.
    assert f"{BUILD_OP}(" in _read(DAILY_JOB), (
        f"{BUILD_OP} is not wired into {DAILY_JOB.name} — that is exactly the pre-fix state of "
        "export_ref_players_to_s3.py (a writer nothing runs). The DAILY job is the load-bearing "
        "cadence: mlb_played_first/last are derived from Statcast appearances, which advance every "
        "night, so a weekly-only rebuild would leave the very column E5.10 found frozen lagging "
        "by up to 7 days for every player who just debuted."
    )


def test_the_builder_is_not_wired_into_the_weekly_profiles_job():
    """⛔ Deliberately ABSENT there, and this clause exists so a future session does not 'helpfully'
    add it back.

    Chaining the builder off reexport_player_profiles_op is the obvious move — the builder reads
    the mirror that op refreshes, so INC-25 wants it downstream. But binding that leaf's output
    destroys the property test_e11_24_bundle_freshness_reexports.py defends (an UNBOUND fan-out
    leaf structurally cannot withhold whatever is chained behind it), and wiring it upstream leaves
    the two unordered under a topological executor — the INC-25 hazard itself. The daily job runs
    ~2h after the weekly one and rebuilds the dimension from the fresh mirror anyway, so neither
    compromise is needed.
    """
    assert f"{BUILD_OP}(" not in _read(WEEKLY_JOB), (
        f"{BUILD_OP} was wired into {WEEKLY_JOB.name}. If it chains off {MIRROR_OP} it breaks that "
        "op's unbound-fan-out-leaf invariant; if it chains off the ingest it races the mirror. "
        "The daily job already covers this — see the comment in the weekly job."
    )


def test_the_writer_op_is_alert_tier_and_never_halts():
    """E11.7 tier contract + E11.30: an ALERT-tier op must actually page, not just log.

    A peripheral identity dimension must never HALT a slate, so the op has to swallow its
    exception — which is precisely why it must also call send_alert, or the failure is invisible
    (E11.30 found four ops whose 'ALERT tier' meant 'detected, nobody notified').
    """
    body = _op_source(BUILD_OP)
    assert "send_alert(" in body, (
        f"{BUILD_OP} is ALERT tier but never calls send_alert — a tier enforced only by a "
        "docstring is not enforced at all (E11.30)."
    )
    assert "except" in body, f"{BUILD_OP} must catch its failure — a name dimension must not HALT a slate"
    assert "raise" not in body, f"{BUILD_OP} must not re-raise — ALERT tier, never HALT"
    assert "timeout=" in body, (
        f"{BUILD_OP} must pass a finite timeout= (INC-32): in_process_executor runs steps one at "
        "a time, so even a fan-out leaf can stall the job."
    )


# ── 2. Ordering: the writer runs DOWNSTREAM of the mirror it reads (INC-25) ───────────────────

def _op_source(name: str) -> str:
    tree = ast.parse(OPS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(OPS.read_text(), node) or ""
    raise AssertionError(f"op {name} not found in {OPS}")


def _daily_job_edges() -> tuple[dict[str, str], dict[str, set[str]]]:
    """(var -> producing op, op -> set of ops it depends on) for the daily job, from the AST."""
    tree = ast.parse(DAILY_JOB.read_text())
    produced_by: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        produced_by[tgt.id] = fn.id

    deps: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            upstream = {
                produced_by[kw.value.id]
                for kw in node.keywords
                if isinstance(kw.value, ast.Name) and kw.value.id in produced_by
            }
            deps.setdefault(node.func.id, set()).update(upstream)
    return produced_by, deps


def test_the_builder_runs_downstream_of_the_lakehouse_build_it_reads():
    """INC-25 — a consumer of a lakehouse artifact must be rebuilt DOWNSTREAM of the refresh that
    feeds it, IN THE SAME RUN.

    The builder derives mlb_played_first/last from `stg_batter_pitches`, which
    lakehouse_w1_pitch_marts_op rebuilds earlier in this job. Scheduled ahead of it, the dimension
    would be stamped from YESTERDAY's pitch data — so a player who debuted last night would still
    be missing, silently, which is the whole defect this story fixes. That is the same shape as
    INC-37 (the schedule consumer ordered ahead of its own ingest): invisible on almost every run
    and wrong exactly when it matters.

    ⚠️ Asserted as TRANSITIVE REACHABILITY over the dependency edges, not source-line order: the
    job runs under in_process_executor, which orders steps TOPOLOGICALLY, so 'appears later in the
    file' is vacuous (INC-40's lesson, and CLAUDE.md's explicit warning that a source-line-order
    test pins nothing).
    """
    _, deps = _daily_job_edges()
    assert BUILD_OP in deps, f"{BUILD_OP} is not called in {DAILY_JOB.name} — nothing to order"

    # Walk the dependency closure upward from the builder.
    seen: set[str] = set()
    stack = list(deps.get(BUILD_OP, set()))
    while stack:
        op = stack.pop()
        if op in seen:
            continue
        seen.add(op)
        stack.extend(deps.get(op, set()))

    assert LAKEHOUSE_W1_OP in seen, (
        f"{BUILD_OP} is not transitively downstream of {LAKEHOUSE_W1_OP} in {DAILY_JOB.name} "
        f"(its upstream closure is {sorted(seen)}). It derives mlb_played_last from "
        "stg_batter_pitches, so ordered ahead of that build it stamps the dimension from "
        "yesterday's pitch data (INC-25)."
    )


# ── 3. The dead-source export must never write the LIVE prefix again ─────────────────────────

def test_the_dead_source_export_writes_only_the_archive_prefix():
    """savant.ref_players has no writer and has not moved since 2025-10-13.

    If this export ever writes the live prefix again it silently reinstates the frozen table under
    the name every consumer reads — the original defect, restored. It may write ONLY the archive.
    """
    # Read the ASSIGNED S3 key from the AST — not a regex over the file, which the docstring
    # explaining this very change would satisfy (and did, on the first cut).
    keys = _assigned_str_constants(ARCHIVE_EXPORT, "_S3_KEY")
    assert keys, "no _S3_KEY assignment found in the archive export — did the S3 key move?"
    prefixes = {k.split("/")[2] for k in keys if k.startswith("baseball/lakehouse/")}
    assert prefixes == {ARCHIVE_PREFIX}, (
        f"export_ref_players_to_s3.py writes {sorted(prefixes)}; it must write ONLY "
        f"'{ARCHIVE_PREFIX}'. Writing '{LIVE_PREFIX}' from the dead Snowflake source is the "
        "defect this story fixed."
    )


def test_the_builder_publishes_the_live_prefix_and_reads_the_archive():
    """The merge must PUBLISH the prefix consumers read and CONSUME the archive — not the reverse."""
    src = _read(BUILDER)
    assert f'OUTPUT_KEY = "baseball/lakehouse/{LIVE_PREFIX}/' in src, (
        "the builder must publish the live stg_ref_players/ prefix — that is what makes all ~11 "
        "consumers correct without touching any of them"
    )
    assert f'ARCHIVE_PREFIX = "{ARCHIVE_PREFIX}"' in src, "the builder must read the frozen archive"
    assert 'LIVE_PREFIX = "player_profiles_raw"' in src, (
        "the builder must read the LIVE profiles feed — merging the archive with itself would "
        "reproduce the frozen dimension while looking like a fresh build"
    )


def test_the_builder_refuses_to_publish_a_dimension_with_no_current_season_players():
    """NF-K1 — count the rows that CARRY THE VALUE, never just the rows.

    A row-count check is satisfied by an archive-only rebuild (25,900 rows, zero current players),
    which is exactly the broken artifact E5.10 found. The publish guard must key on current-season
    coverage.
    """
    src = _read(BUILDER)
    assert "min_current_season_players" in src, "the builder has no current-season coverage floor"
    assert "REFUSING TO PUBLISH" in src, (
        "the coverage floor must REFUSE the publish, not merely warn — a warning on a leaf op "
        "nobody reads is how the original 53-day rot survived"
    )


def test_the_builder_routes_lakehouse_reads_through_the_shared_registry():
    """E11.20 phase-1.5 (P0, zero-prediction slate): stg_batter_pitches is Delta-backed under
    cutover and its legacy compat parquet was DELETED. A hardcoded `**/*.parquet` glob for it
    reads NOTHING. The shared registry routes Delta tables via delta_scan."""
    src = _read(BUILDER)
    assert "register_views" in src, "the builder must register lakehouse views via lakehouse_read"
    assert "read_parquet(" not in src, (
        "the builder must not hardcode a read_parquet glob — route every lakehouse source through "
        "lakehouse_read.register_views so a Delta-backed table resolves via delta_scan"
    )


# ── 4. The consumer registry is exhaustive (INC-27 / INC-38) ─────────────────────────────────

def _scan_for_consumers() -> set[str]:
    found: set[str] = set()
    for root in _SCAN_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in _SCAN_SUFFIXES or not path.is_file():
                continue
            rel = path.relative_to(REPO).as_posix()
            if rel in _NON_CONSUMERS:
                continue
            body = _strip_comments(path.read_text(errors="replace"), path.suffix)
            # The prefix string OR the bare table name (a raw-SQL `from stg_ref_players`).
            if re.search(rf"\b{LIVE_PREFIX}\b", body):
                found.add(rel)
    return found


def test_the_consumer_registry_is_exhaustive():
    """INC-38 — a per-consumer conclusion fails exactly where the registry is short.

    This story's central claim is "~11 consumers, all fixed at the artifact". That claim is only
    true if the list is complete, so the list is re-derived from the source on every run.
    """
    found = _scan_for_consumers()
    assert found, (
        "VACUITY: the scan found NO consumers at all. Either the scan roots are wrong or the "
        "prefix was renamed — either way this clause is passing on nothing."
    )
    registered = set(CONSUMERS)
    unregistered = found - registered
    assert not unregistered, (
        "these files read stg_ref_players but are NOT in the CONSUMERS registry: "
        f"{sorted(unregistered)}. Add them (with the reason they read it) — the fix's correctness "
        "argument is 'every consumer reads the merged artifact', which is only checkable against "
        "a complete list."
    )


@pytest.mark.parametrize("rel", sorted(CONSUMERS))
def test_every_registered_consumer_actually_reads_the_dimension(rel):
    """Anti-vacuity, the other direction: a registry entry that no longer reads the dimension is
    stale bookkeeping and quietly weakens the exhaustiveness clause above."""
    path = REPO / rel
    assert path.exists(), f"registered consumer {rel} does not exist — remove or fix the entry"
    body = _strip_comments(path.read_text(), path.suffix)
    assert re.search(rf"\b{LIVE_PREFIX}\b", body), (
        f"{rel} is registered as a consumer but no longer references {LIVE_PREFIX} in "
        "comment-stripped source."
    )


def test_the_registry_size_matches_the_measured_count():
    """Pins the count this story reported, so a silent drift is visible in review."""
    assert len(CONSUMERS) == 11, (
        f"the consumer registry holds {len(CONSUMERS)} entries; E5.10 and this story both measured "
        "11. If a consumer was genuinely added or removed, update this number IN THE SAME CHANGE "
        "so the count stays a measurement rather than a memory."
    )


# ── 5. The freshness SLA exists and reads a CONTENT timestamp ────────────────────────────────

def test_the_dimension_has_an_inc41_freshness_contract():
    """INC-41 — the old rot was invisible to every SOURCE-watching check (the feed was healthy,
    the marts built, nothing raised). Only an assertion on the DERIVED artifact can see it."""
    src = (REPO / "betting_ml" / "monitoring" / "artifact_freshness.py").read_text()
    assert f'name="{LIVE_PREFIX}"' in src, (
        "stg_ref_players has no freshness contract — a scheduled writer alone does not prove the "
        "artifact advanced (a skipped or gated build freezes it in total silence)"
    )
    contract = src[src.index(f'name="{LIVE_PREFIX}"'):]
    contract = contract[:contract.index("),")]
    assert "built_at" in contract, (
        "the contract must read the build stamp written INSIDE the parquet — never an S3 "
        "LastModified, which an atomic server-side copy refreshes even on unchanged data (INC-41)"
    )
