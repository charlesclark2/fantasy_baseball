"""Guard — the E11.24 Bundle: the last three check_data_freshness blockers and their re-exports.

WHAT THIS DEFENDS. Three tables kept ``check_data_freshness.py`` opening a Snowflake connection
on every run. They looked like one problem ("the mirror is stale") and were three different
defects, so they get three isolating fixtures rather than one shared one:

  team_sequential_posteriors          INC-25 ORDERING TRAIL. lakehouse_w8b_aggregator_op mirrors
                                      it at lk10; update_team_posteriors_op writes ~40 min later.
                                      Measured 2026-08-14: SF 13:03:04 / 83,636 rows vs S3
                                      10:16:26 / 83,619 — 2.78h and 17 rows behind. This is the
                                      #693 defect one table over; PR #772 refused the freshness
                                      flip because of it.
  player_profiles_raw                 WRITER GAP. ingest_player_profiles.py writes only Snowflake;
                                      the mirror's only writer (export_w4_raw_to_s3.py) is a
                                      hand-run W4 precursor no job schedules, so it froze at
                                      2026-06-28 — ~1,133h against a 192h threshold.
  matchup_cell_sequential_posteriors  NO MIRROR AT ALL (a DuckDB IOException, not a stale read).
                                      The export had to be built.

⚠️ THESE ASSERT THE DEPENDENCY EDGE, NOT SOURCE-LINE ORDER. Every job here uses
``in_process_executor``, which executes TOPOLOGICALLY, so an op written lower in the file but
wired ``start=<something early>`` still runs early — a line-number test would be vacuous (INC-40).
The source-inspection tests read the ``start=`` WIRING; the compiled-graph class at the bottom
re-proves the same edges off the real Dagster graph, with a positive control.

⚠️ COMMENTS AND DOCSTRINGS ARE STRIPPED BEFORE EVERY MATCH. The fix's own prose names every op,
variable and table repeatedly, so an un-stripped match would pass on source with the wiring
deleted (the INC-38 prose-satisfiable-guard lesson). ``test_the_strippers_actually_strip`` is the
non-vacuity anchor for that machinery: without it, a stripper that returned "" would make most
assertions below unfalsifiable in the *other* direction.

SOURCE-INSPECTION, not an import, for the fast-gate half: ``pipeline/__init__.py`` reads the dbt
manifest, absent in the fast gate, so importing ``pipeline`` there would crash at COLLECTION
rather than skip (E11.23).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = REPO_ROOT / "pipeline" / "jobs"
DAILY_JOB = JOBS_DIR / "daily_ingestion_job.py"
SENSOR_JOBS = JOBS_DIR / "sensor_jobs.py"
WEEKLY_PROFILES_JOB = JOBS_DIR / "weekly_player_profiles_job.py"
DAILY_OPS = REPO_ROOT / "pipeline" / "ops" / "daily_ingestion_ops.py"
SCRIPTS = REPO_ROOT / "scripts"
W8B_EXPORT = SCRIPTS / "export_w8b_precursors_to_s3.py"

# (writer op, re-export op, exporter script, mirrored table, job modules that wire the writer)
BUNDLE = [
    pytest.param(
        "update_team_posteriors_op", "reexport_team_seq_posteriors_op",
        "export_w8b_precursors_to_s3.py", "team_sequential_posteriors",
        ("daily_ingestion_job.py", "sensor_jobs.py"),
        id="team_seq",
    ),
    pytest.param(
        "update_matchup_cell_posteriors_op", "reexport_matchup_cell_posteriors_op",
        "export_w8b_precursors_to_s3.py", "matchup_cell_sequential_posteriors",
        ("daily_ingestion_job.py", "sensor_jobs.py"),
        id="matchup_cell",
    ),
    pytest.param(
        "ingest_player_profiles_update", "reexport_player_profiles_op",
        "export_w4_raw_to_s3.py", "player_profiles_raw",
        ("weekly_player_profiles_job.py",),
        id="player_profiles",
    ),
]

# The freshness-entry key each mirrored table is registered under.
FRESHNESS_KEY = {
    "team_sequential_posteriors": "baseball_data.betting.team_sequential_posteriors",
    "matchup_cell_sequential_posteriors":
        "baseball_data.betting.matchup_cell_sequential_posteriors",
    "player_profiles_raw": "baseball_data.statsapi.player_profiles_raw",
}

# Entries this bundle does NOT own. PR #772 flips these two; until it merges to `dev` they are
# legitimately Snowflake-sourced here, and after it merges this set is simply empty. Naming them
# explicitly is what lets `test_no_entry_outside_pr_772_still_reads_snowflake` be a real assertion
# on both bases instead of a vacuous one on either.
PR_772_ENTRIES = {
    "baseball_data.betting.eb_bullpen_team_posteriors",
    "baseball_data.betting.eb_park_factors_raw",
}


def _code_only(path: Path) -> str:
    """Source with whole-line comments removed, so prose can never satisfy a guard."""
    return "\n".join(
        line for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


def _op_body(op_name: str) -> str:
    """The comment-stripped, DOCSTRING-stripped body of one op in daily_ingestion_ops.py.

    Both strips matter: these ops' docstrings quote their own argv, table name and tier, so an
    unstripped body would satisfy every assertion below with the real code deleted.
    """
    code = _code_only(DAILY_OPS)
    start = code.find(f"def {op_name}(")
    assert start != -1, f"{op_name} not found in {DAILY_OPS.name}"
    body = code[start:]
    if '"""' in body:
        head, _, rest = body.partition('"""')
        body = head + rest.partition('"""')[2]
    nxt = body.find("@op(")          # stop at the next op definition
    return body[:nxt] if nxt != -1 else body


def _assigned_from(code: str, callee: str, where: str) -> str:
    """The variable a single `<var> = <callee>(...)` call binds to."""
    hits = re.findall(rf"^\s*(\w+)\s*=\s*{callee}\(", code, re.MULTILINE)
    assert len(hits) == 1, (
        f"expected exactly one `<var> = {callee}(...)` in {where}, found {hits}"
    )
    return hits[0]


def _start_arg(code: str, callee: str, where: str) -> str:
    """The variable passed as `start=` to a single call of `callee`."""
    hits = re.findall(rf"{callee}\(\s*start\s*=\s*(\w+)\s*\)", code)
    assert len(hits) == 1, (
        f"expected exactly one `{callee}(start=<var>)` in {where}, found {hits}"
    )
    return hits[0]


def _freshness_module():
    """Load check_data_freshness.py by path (it is a script, not a package module)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_e1124_bundle_freshness", SCRIPTS / "check_data_freshness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _w8b_export_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_e1124_bundle_w8b_export", W8B_EXPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ══════════════════════════════════════════════════════════════════════════════════════════
# 0. Non-vacuity of the machinery every other test leans on
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_strippers_actually_strip():
    """A stripper that returned "" (or one that stripped nothing) would silently invert every
    assertion below — `assert X not in body` passes on an empty body, `assert X in body` passes
    on an unstripped one. Prove both directions on real source before trusting either."""
    raw = DAILY_OPS.read_text()
    assert "# " in raw, "fixture assumption broken: daily_ingestion_ops.py has no comments"
    code = _code_only(DAILY_OPS)
    assert len(code) < len(raw), "_code_only removed nothing"
    assert code.strip(), "_code_only removed everything"

    body = _op_body("reexport_team_seq_posteriors_op")
    assert body.strip(), "_op_body returned an empty body — every `not in` assertion is vacuous"
    assert "INC-25 ORDERING FIX" not in body, (
        "_op_body did not strip the docstring — every argv/tier assertion below could then be "
        "satisfied by the op's own prose (the INC-38 lesson)"
    )
    assert "_run_script(" in body, "_op_body stripped the actual code, not just the docstring"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. The ordering edge — one isolating fixture per (re-export, job)
# ══════════════════════════════════════════════════════════════════════════════════════════

def _edge_cases():
    for p in BUNDLE:
        writer, reexport, _script, _table, job_files = p.values
        for job_file in job_files:
            yield pytest.param(writer, reexport, job_file,
                               id=f"{p.id}-{job_file.removesuffix('.py')}")


@pytest.mark.parametrize("writer,reexport,job_file", list(_edge_cases()))
def test_the_reexport_is_wired_downstream_of_its_writer(writer, reexport, job_file):
    """THE regression, per job. Wired anywhere upstream of its writer, a re-export mirrors a
    table that has not been advanced yet — which is the lk10 defect verbatim, just moved to a
    new op. One fixture per (table, job) so a passing daily edge can never mask a missing
    catch-up edge, and vice versa."""
    path = JOBS_DIR / job_file
    code = _code_only(path)
    writer_out = _assigned_from(code, writer, job_file)
    reexport_start = _start_arg(code, reexport, job_file)
    assert reexport_start == writer_out, (
        f"{reexport} is wired start={reexport_start!r} in {job_file} but must be wired "
        f"start={writer_out!r} (the {writer} output). Mirroring before the writer reproduces "
        f"the trail this op exists to remove."
    )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_writer_caller_registry_is_still_exhaustive(writer, reexport, script, table, job_files):
    """INC-38: a per-caller fix fails exactly where the caller list is incomplete.

    Every job module that WIRES the writer must also wire the re-export. Matches CALL SITES, not
    bare names (an import line would over-count), and asserts non-vacuity explicitly — an empty
    match set would otherwise pass on nothing (NF1.7 (a)).
    """
    callers = {}
    for path in sorted(JOBS_DIR.glob("*.py")):
        code = _code_only(path)
        if re.search(rf"^\s*\w+\s*=\s*{writer}\(", code, re.MULTILINE):
            callers[path.name] = bool(re.search(rf"{reexport}\(\s*start\s*=", code))
    assert set(callers) == set(job_files), (
        f"the {writer} caller set changed: found {sorted(callers)}, expected {sorted(job_files)}. "
        f"A NEW job running the writer needs its own {reexport} leaf, or that job advances "
        f"Snowflake while the S3 {table} mirror freezes (the INC-38 every-caller lesson). If a "
        f"job was renamed, update BUNDLE — a short registry makes these assertions vacuous."
    )
    missing = sorted(name for name, ok in callers.items() if not ok)
    assert not missing, f"these job modules wire {writer} but not {reexport}: {missing}"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. Each op — a leaf, ALERT tier, ungated, bounded, exporting exactly one table
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("writer,reexport,job_file", list(_edge_cases()))
def test_the_reexport_is_a_fan_out_leaf(writer, reexport, job_file):
    """Structural proof it cannot withhold a slate: its result is never bound, so nothing can
    chain off it. Threading the team-seq leaf between the team and matchup-cell writers, for
    instance, would let a mirror failure skip p_matchup and predict."""
    code = _code_only(JOBS_DIR / job_file)
    bound = re.findall(rf"^\s*(\w+)\s*=\s*{reexport}\(", code, re.MULTILINE)
    assert not bound, (
        f"{reexport} binds its output to {bound} in {job_file} — it must be an unbound fan-out "
        f"leaf so a mirror failure can never block the chain behind it."
    )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_op_exports_exactly_its_own_table(writer, reexport, script, table, job_files):
    """Pin the argv, not the prose. A bare exporter call with no --table re-exports that
    script's whole default set — three needless Snowflake SELECT *s for export_w4_raw_to_s3.py,
    and for export_w8b_precursors_to_s3.py it would ALSO re-mirror feature_pregame_lineup_state
    from inside a sequential-posterior leaf, which is not this op's job."""
    body = _op_body(reexport)
    assert script in body, f"{reexport} no longer calls {script}"
    assert re.search(rf'"--table",\s*"{table}"', body), (
        f'{reexport} must pass ["--table", "{table}"] as real argv; found none in its '
        f"comment-stripped, docstring-stripped body."
    )
    others = [t for t in FRESHNESS_KEY if t != table]
    for other in others:
        assert not re.search(rf'"--table",\s*"{other}"', body), (
            f"{reexport} also passes --table {other} — one leaf per table, so a failure names "
            f"the mirror it broke."
        )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_subprocess_has_a_finite_timeout(writer, reexport, script, table, job_files):
    """INC-32 — and being a LEAF does not excuse it. Every job here uses `in_process_executor`,
    which runs steps one at a time in topological order, so a hung leaf stalls every step
    scheduled after it. Without a cap, a wedged Snowflake fetch or S3 upload is a stalled job
    instead of this op's own page."""
    body = _op_body(reexport)
    m = re.search(r"timeout\s*=\s*(\d+)", body)
    assert m, f"{reexport} calls _run_script with no finite timeout= (INC-32)"
    assert 0 < int(m.group(1)) <= 1800, (
        f"{reexport}'s timeout is {m.group(1)}s — a cap that long stops bounding the stall it "
        f"exists to prevent."
    )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_op_is_alert_tier_and_cannot_raise(writer, reexport, script, table, job_files):
    """ALERT-loud-but-continue, and it must actually PAGE — E11.30's finding was that several
    ops labelled ALERT only ever reached context.log.warning, so a real failure was detected and
    never notified. A tier enforced only by a docstring is not enforced."""
    body = _op_body(reexport)
    assert "send_alert(" in body, f"{reexport} must page via send_alert (E11.30)"
    assert "except Exception" in body, f"{reexport} must swallow its failure (ALERT tier)"
    assert not re.search(r"^\s+raise\b", body, re.MULTILINE), (
        f"{reexport} must never re-raise — it is a mirror, not a serving gate."
    )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_op_has_a_distinct_dedup_key(writer, reexport, script, table, job_files):
    """INC-39: send_alert rate-limits on `dedup_key` with a 1-hour TTL. Two mirror re-exports
    sharing one key would let the first failure of the hour SUPPRESS the other — the page would
    name one broken mirror while another was also down.

    Checked across the WHOLE re-export family, #693's `player_sequential_posteriors` leaf
    included: these four ops run minutes apart in the same job and fail for the same reasons
    (a wedged Snowflake fetch, an S3 outage), so they are exactly the set most likely to collide.
    """
    body = _op_body(reexport)
    keys = re.findall(r'dedup_key\s*=\s*"([^"]+)"', body)
    assert len(keys) == 1, f"{reexport} should pass exactly one dedup_key, found {keys}"
    family = [r for _w, r, _s, _t, _j in (p.values for p in BUNDLE)]
    family.append("reexport_player_seq_posteriors_op")   # PR #693's leaf, same failure modes
    for sib in family:
        if sib == reexport:
            continue
        sib_keys = re.findall(r'dedup_key\s*=\s*"([^"]+)"', _op_body(sib))
        assert sib_keys, f"non-vacuity: found no dedup_key in {sib} to compare against"
        assert keys[0] not in sib_keys, (
            f"{reexport} and {sib} share dedup_key {keys[0]!r} — one failure would mute the other"
        )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_op_is_not_gated_behind_a_cutover_flag(writer, reexport, script, table, job_files):
    """Deliberate, and the same reasoning as reexport_player_seq_posteriors_op: the export is a
    plain SELECT * → S3 with no dependency on any DuckDB build, and a gated mirror freezes
    silently the day the flag lapses (the W7B_LAKEHOUSE_S3 documented-but-never-set class).
    Pinned so a later 'consistency' tidy-up has to argue rather than drift."""
    body = _op_body(reexport)
    for gate in ("_w8a_mirror_on", "_w8b_mirror_on", "_w8b_serving_on", "_w7b_serving_on",
                 "_run_w8a_mirror", "_run_w8b_mirror", "_w7a_s3_args"):
        assert gate not in body, (
            f"{reexport} now calls {gate} — the re-export must run unconditionally; a gated "
            f"mirror freezes silently when the flag lapses."
        )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. The exporter — matchup_cell is reachable but must NOT join the lk10 default set
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_matchup_cell_mirror_is_exportable_at_all():
    mod = _w8b_export_module()
    assert "matchup_cell_sequential_posteriors" in mod.MIRROR_TABLES
    assert mod.MIRROR_TABLES["matchup_cell_sequential_posteriors"] == (
        "baseball_data.betting.matchup_cell_sequential_posteriors")
    assert "matchup_cell_sequential_posteriors" in mod.ALL_NAMES, (
        "ALL_NAMES feeds --table's `choices`; dropping it there makes the re-export op's argv "
        "an argparse error at runtime, invisible to every source-inspection test above."
    )


def test_the_matchup_cell_mirror_is_not_in_the_default_lk10_set():
    """THE point of building this export inside the bundle. The no-arg invocation is the one
    lakehouse_w8b_aggregator_op makes at lk10, ~40 min BEFORE update_matchup_cell_posteriors_op
    writes. Putting the table in the default set would have created the mirror with the INC-25
    trail already installed — the fourth member of the family this bundle closes — and would
    have raced the on-demand writer for the same S3 key (the INC-31 two-writers-one-key shape)."""
    mod = _w8b_export_module()
    assert "matchup_cell_sequential_posteriors" in mod.ON_DEMAND_ONLY
    assert "matchup_cell_sequential_posteriors" not in mod.DEFAULT_NAMES


def test_the_team_seq_mirror_is_still_in_the_default_lk10_set():
    """The two-sided half, and it is load-bearing: without it, ON_DEMAND_ONLY could swallow
    every table and the test above would still pass. team_sequential_posteriors MUST stay in the
    default set because the --w8b DuckDB build READS it (feature_pregame_game_features_raw), so
    the mirror has to exist before that build runs. Its re-export leaf is additive to that, not
    a replacement for it."""
    mod = _w8b_export_module()
    assert "team_sequential_posteriors" in mod.DEFAULT_NAMES
    assert "feature_pregame_lineup_state" in mod.DEFAULT_NAMES
    assert set(mod.DEFAULT_NAMES) == set(mod.ALL_NAMES) - set(mod.ON_DEMAND_ONLY)


def test_the_default_set_is_what_a_bare_invocation_selects():
    """DEFAULT_NAMES is only a declaration until main() reads it — the NF-C0e wired-≠-invoked
    class. Pin the actual selection expression, on comment-stripped source."""
    code = _code_only(W8B_EXPORT)
    assert re.search(r"selected\s*=\s*\[args\.table\]\s*if\s*args\.table\s+else\s+"
                     r"list\(DEFAULT_NAMES\)", code), (
        "main() no longer selects DEFAULT_NAMES for a bare invocation — if it fell back to "
        "ALL_NAMES, lk10 would start mirroring matchup_cell_sequential_posteriors before its "
        "writer runs and ON_DEMAND_ONLY would be decorative."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. The freshness flips, and the coupling that makes them safe
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_the_freshness_entry_now_reads_s3(writer, reexport, script, table, job_files):
    fresh = _freshness_module()
    cfg = fresh.FRESHNESS_THRESHOLDS[FRESHNESS_KEY[table]]
    assert fresh.entry_source(cfg) == "s3", (
        f"the {table} freshness entry should read the S3 mirror now that its re-export keeps "
        f"the mirror current."
    )


@pytest.mark.parametrize("writer,reexport,script,table,job_files", BUNDLE)
def test_reading_s3_requires_the_reexport_in_every_writer_job(
        writer, reexport, script, table, job_files):
    """THE COUPLING, made mechanical. An S3-sourced entry on a box still running the un-reordered
    graph is a guaranteed false STALE. NON-VACUOUS today because every entry IS s3 — if a future
    change reverts the wiring while leaving the source flipped, it goes red here rather than on
    the box."""
    fresh = _freshness_module()
    cfg = fresh.FRESHNESS_THRESHOLDS[FRESHNESS_KEY[table]]
    assert fresh.entry_source(cfg) == "s3", (
        "non-vacuity anchor: this coupling only means anything while the entry reads S3"
    )
    for job_file in job_files:
        code = _code_only(JOBS_DIR / job_file)
        assert re.search(rf"{reexport}\(\s*start\s*=", code), (
            f"the {table} freshness entry reads the S3 mirror but {job_file} no longer wires "
            f"{reexport} — the mirror falls behind and the monitor reports a false STALE."
        )


def test_no_entry_outside_pr_772_still_reads_snowflake():
    """The bundle's own scope, asserted rather than narrated. Anything Snowflake-sourced here
    other than PR #772's two cheap flips means a blocker was missed or a new Snowflake-resident
    entry was added — and a single such entry silently re-opens the connection and puts this
    script back in the COMPUTE_WH wake queue (#679: wake is a queue, so one entry costs the
    whole saving)."""
    fresh = _freshness_module()
    still_sf = {t for t, c in fresh.FRESHNESS_THRESHOLDS.items()
                if fresh.entry_source(c) == "snowflake"}
    assert still_sf <= PR_772_ENTRIES, (
        f"Snowflake-sourced entries outside PR #772's set: {sorted(still_sf - PR_772_ENTRIES)}. "
        f"Each one keeps check_data_freshness resuming COMPUTE_WH on every run."
    )


def test_the_union_with_pr_772_leaves_no_snowflake_read():
    """The dividend, proven on the union rather than asserted in prose. On a base that already
    has PR #772 this is exactly `needs_snowflake() is False`; on a base without it, it proves
    that #772's two flips are the ONLY thing between this branch and a Snowflake-free run."""
    fresh = _freshness_module()
    with_772 = {
        k: ({**v, "source": "s3"} if k in PR_772_ENTRIES else v)
        for k, v in fresh.FRESHNESS_THRESHOLDS.items()
    }
    assert fresh.needs_snowflake(with_772) is False


def test_needs_snowflake_still_discriminates():
    """Two-sided control for the test above: a helper that returned False unconditionally would
    satisfy it. Regress ONE entry and the answer must flip."""
    fresh = _freshness_module()
    regressed = dict(fresh.FRESHNESS_THRESHOLDS)
    victim = FRESHNESS_KEY["team_sequential_posteriors"]
    regressed[victim] = {**regressed[victim], "source": "snowflake"}
    assert fresh.needs_snowflake(regressed) is True


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4b. A mirror that does not exist yet must cost ONE entry, not the whole check
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_duckdb_binds_a_parquet_view_at_create_time_not_lazily():
    """THE PREMISE, measured rather than assumed — everything below depends on it.

    If DuckDB were lazy, an absent prefix would surface at query time and `run()`'s existing
    per-table try/except would already contain it. It is NOT lazy (duckdb 1.5.3): CREATE VIEW
    over a missing glob raises immediately, which is why the registration loop needs its own
    isolation. This test is what tells a future reader if that ever changes.
    """
    duckdb = pytest.importorskip("duckdb")
    conn = duckdb.connect()
    with pytest.raises(Exception) as exc:
        conn.execute(
            "CREATE OR REPLACE VIEW t AS SELECT * FROM "
            "read_parquet('/tmp/e1124_definitely_missing_prefix/**/*.parquet', union_by_name=true)"
        )
    assert "No files found" in str(exc.value) or "IO Error" in str(exc.value)


def test_duck_connection_actually_uses_the_isolated_loop():
    """The split is only worth something if `_duck_connection` INVOKES it — otherwise the test
    below proves an isolated loop that production never runs (the NF-C0e wired-≠-invoked class,
    made possible precisely by extracting the loop to make it testable).

    Also pins that the batch helper is not back in the CODE: `register_lakehouse_views` registers
    every view in one loop with no per-table isolation, which is the regression this whole section
    exists to prevent. ⚠️ Matched as an IMPORT or a CALL, never as a bare name — the docstrings
    here discuss that helper by name to explain why it was dropped, and a substring check would
    fire on that prose (the INC-38 lesson, in its false-RED direction).
    """
    path = SCRIPTS / "check_data_freshness.py"
    code = _code_only(path)
    body = code[code.find("def _duck_connection("):code.find("def _register_views_isolated(")]
    assert "_register_views_isolated(" in body, (
        "_duck_connection no longer calls _register_views_isolated — the isolation is dead code"
    )
    import ast
    tree = ast.parse(path.read_text())
    banned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            banned |= {a.name for a in node.names if a.name == "register_lakehouse_views"}
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "register_lakehouse_views":
                banned.add("call")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "register_lakehouse_views":
                banned.add("call")
    assert not banned, (
        "check_data_freshness imports or calls the batch register_lakehouse_views helper, which "
        "aborts on the FIRST unreadable prefix and blinds every other entry"
    )


def test_one_unregisterable_mirror_does_not_blind_the_other_entries(tmp_path, monkeypatch):
    """THE REGRESSION this isolation prevents. A re-export leaf's mirror does not exist until
    that leaf's job first RUNS, so a fresh deploy genuinely has an absent prefix — and the batch
    registration helper would abort `_duck_connection` before the first entry was read, blinding
    EVERY check. That is the savant.batter_pitches decommission failure (2026-07-06) reproduced
    one layer earlier, where `run()`'s per-table try/except cannot reach it.

    Driven through the REAL registration loop (`_register_views_isolated`) against REAL DuckDB
    over local parquet — a mocked connection would only restate the loop's own structure. The
    loop is split out of `_duck_connection` precisely so this can run in the fast gate: `duck()`
    creates a DuckDB S3 SECRET that needs a live AWS credential chain, and CI mocks all IO.
    """
    duckdb = pytest.importorskip("duckdb")
    pytest.importorskip("pandas")
    import pandas as pd

    present = tmp_path / "present_table"
    present.mkdir()
    pd.DataFrame({"update_ts": pd.to_datetime(["2026-08-14 13:03:04"])}).to_parquet(
        present / "data.parquet")

    fresh = _freshness_module()

    import betting_ml.utils.delta_lakehouse as dl
    monkeypatch.setattr(
        dl, "lakehouse_view_sql",
        lambda t: ("SELECT * FROM read_parquet('"
                   f"{tmp_path / t}/**/*.parquet', union_by_name=true)"))

    conn = fresh._register_views_isolated(
        duckdb.connect(), ["present_table", "absent_table"])
    try:
        # the healthy table still answers …
        ts = fresh._max_ingestion_timestamp_s3(
            "baseball_data.betting.present_table", "update_ts", conn)
        assert ts is not None and ts.year == 2026, (
            "the absent mirror took the healthy one down with it — the registration loop is not "
            "isolated"
        )
        # … and the absent one raises for ITSELF, which run()'s per-table except turns into a
        # QUERY ERROR for that entry alone. It must NOT read as fresh (NF1.7 (a)).
        with pytest.raises(Exception):
            fresh._max_ingestion_timestamp_s3(
                "baseball_data.betting.absent_table", "update_ts", conn)
    finally:
        conn.close()


def test_the_snowflake_escape_hatch_is_retained_deliberately():
    """The Snowflake read path is kept (not deleted) as the escape hatch for a genuinely
    Snowflake-resident future feed, with `_DEFAULT_SOURCE` still failing toward the store that
    certainly exists. Pinned so a "dead code" tidy-up and a real removal are distinguishable:
    removing it is a decision to make explicitly, alongside this test."""
    fresh = _freshness_module()
    assert fresh._DEFAULT_SOURCE == "snowflake"
    assert callable(fresh._max_ingestion_timestamp)
    assert callable(fresh._get_connection)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5. The same edges, re-proven off the COMPILED Dagster graph
# ══════════════════════════════════════════════════════════════════════════════════════════
# Needs the dbt manifest to import `pipeline` (E11.23), so these are @slow — CI's slow gate runs
# `dbtf parse` first, which builds it. Marked skipif as well so a fresh worktree without the
# manifest reports a skip instead of a collection crash (NF-D18).

_MANIFEST = REPO_ROOT / "dbt" / "target" / "manifest.json"
requires_pipeline = pytest.mark.skipif(
    not _MANIFEST.exists(), reason="needs the dbt manifest to import `pipeline` (E11.23)"
)

_GRAPH_EDGES = [
    pytest.param("daily", "reexport_team_seq_posteriors_op", "update_team_posteriors_op",
                 id="daily-team_seq"),
    pytest.param("daily", "reexport_matchup_cell_posteriors_op",
                 "update_matchup_cell_posteriors_op", id="daily-matchup_cell"),
    pytest.param("catchup", "reexport_team_seq_posteriors_op", "update_team_posteriors_op",
                 id="catchup-team_seq"),
    pytest.param("catchup", "reexport_matchup_cell_posteriors_op",
                 "update_matchup_cell_posteriors_op", id="catchup-matchup_cell"),
    pytest.param("weekly", "reexport_player_profiles_op", "ingest_player_profiles_update",
                 id="weekly-player_profiles"),
]


@pytest.mark.slow
@requires_pipeline
class TestTheCompiledGraph:
    @staticmethod
    def _upstreams(job) -> dict[str, list[str]]:
        """{node -> its upstream node names}, read off the COMPILED Dagster graph."""
        graph = job.graph
        deps = graph.dependency_structure
        return {
            node: sorted({h.node_name
                          for handles in deps.input_to_upstream_outputs_for_node(node).values()
                          for h in handles})
            for node in graph.node_dict
        }

    def _graph(self, which: str) -> dict[str, list[str]]:
        if which == "daily":
            from pipeline.jobs.daily_ingestion_job import daily_ingestion_job
            return self._upstreams(daily_ingestion_job)
        if which == "catchup":
            from pipeline.jobs.sensor_jobs import statcast_catchup_job
            return self._upstreams(statcast_catchup_job)
        from pipeline.jobs.weekly_player_profiles_job import weekly_player_profiles_job
        return self._upstreams(weekly_player_profiles_job)

    @pytest.mark.parametrize("which", ["daily", "catchup", "weekly"])
    def test_the_dependency_probe_actually_finds_edges(self, which):
        """POSITIVE CONTROL. Without it, an empty upstream set below could mean 'the op is a
        leaf' OR 'the probe sees nothing at all' — not the same finding (NF1.7 (a))."""
        ups = self._graph(which)
        assert ups, f"{which}: the compiled graph has no nodes at all"
        assert any(v for v in ups.values()), (
            f"{which}: the probe found ZERO dependency edges in the whole job — it is broken, "
            f"and every 'is downstream of' assertion below would pass on nothing"
        )

    @pytest.mark.parametrize("which,reexport,writer", _GRAPH_EDGES)
    def test_the_reexport_is_downstream_of_its_writer(self, which, reexport, writer):
        ups = self._graph(which)
        assert reexport in ups, f"{reexport} is not in the compiled {which} graph"
        assert writer in ups[reexport], (
            f"in the compiled {which} graph {reexport} depends on {ups[reexport]}, not on "
            f"{writer} — it would mirror a table its writer has not advanced yet."
        )

    @pytest.mark.parametrize("which,reexport,writer", _GRAPH_EDGES)
    def test_nothing_depends_on_the_reexport(self, which, reexport, writer):
        """Fan-out leaf, proven on the compiled graph rather than on source text."""
        ups = self._graph(which)
        dependents = sorted(n for n, u in ups.items() if reexport in u)
        assert not dependents, (
            f"in the compiled {which} graph these ops depend on {reexport}: {dependents}. A "
            f"mirror must never be able to withhold work scheduled after it."
        )
