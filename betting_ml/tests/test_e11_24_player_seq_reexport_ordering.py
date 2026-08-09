"""Guard — the player_sequential_posteriors S3 mirror must be re-exported AFTER its writer.

WHAT WAS WRONG (E11.24, measured 2026-08-09 03:45 UTC on the laptop, Snowflake on MONITOR_WH):

    ``lakehouse_w8a_feature_layer_op`` mirrors ``player_sequential_posteriors`` to S3 at graph
    position lk9, near the TOP of daily_ingestion_job. ``update_player_posteriors_op`` writes
    the Snowflake table ~40 minutes LATER. Nothing re-exported it afterwards, so the parquet was
    always exactly one writer-cycle behind:

        source   max(update_ts)               max(game_date)   rows      lag
        SF       2026-08-08 13:02:18.671140   2026-08-07       400,193   14.72 h
        S3       2026-08-07 13:02:08.375345   2026-08-06       399,759   38.72 h

    +434 rows = precisely the 08-08 writer batch. 38.72h ALREADY BREACHES the entry's own 36h
    freshness threshold — the mirror was not "12h of headroom", it was over the line.

WHY THE LAG HID. ``check_data_freshness.py`` has TWO callers (the INC-38 every-caller lesson,
applied to the READ side): the in-job op at s15 AND a host cron at ``30 12,17 * * *`` UTC. At
s15 the writer has not run yet either, so Snowflake and S3 return the SAME value and the gap is
INVISIBLE. Only the off-cycle reads see it. ⇒ a mirror's lag must be measured at the reader's
WORST moment.

THE SHAPE OF THE FIX — INC-25: a consumer reading an S3 mirror must be rebuilt DOWNSTREAM of the
refresh that feeds it, in the SAME run. ``reexport_player_seq_posteriors_op`` is a FAN-OUT LEAF
off the writer, in BOTH jobs that run that writer.

⚠️ THESE ASSERT THE DEPENDENCY EDGE, NOT SOURCE-LINE ORDER. Both jobs use
``in_process_executor``, which executes TOPOLOGICALLY — an op written lower in the file but wired
``start=<something early>`` still runs early, so a line-number test would be vacuous (the INC-40
lesson). The source-inspection tests below read the ``start=`` WIRING; the compiled-graph class
at the bottom re-proves the same edges off the real Dagster graph, with a positive control.

⚠️ Comment lines are stripped before every match. The fix's own explanatory comments name
``reexport_player_seq_posteriors_op``, ``p_player`` and ``pp``, so a prose-only match would pass
on source with the wiring deleted (the INC-38 prose-satisfiable-guard lesson).

SOURCE-INSPECTION, not an import, for the fast-gate half: ``pipeline/__init__.py`` reads the dbt
manifest, absent in the fast gate, so importing ``pipeline`` there would crash at COLLECTION
rather than skip (E11.23).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DAILY_JOB = REPO_ROOT / "pipeline" / "jobs" / "daily_ingestion_job.py"
SENSOR_JOBS = REPO_ROOT / "pipeline" / "jobs" / "sensor_jobs.py"
DAILY_OPS = REPO_ROOT / "pipeline" / "ops" / "daily_ingestion_ops.py"
JOBS_DIR = REPO_ROOT / "pipeline" / "jobs"

WRITER = "update_player_posteriors_op"
REEXPORT = "reexport_player_seq_posteriors_op"
MIRRORED_TABLE = "player_sequential_posteriors"


def _code_only(path: Path) -> str:
    """Source with whole-line comments removed, so prose can never satisfy a guard."""
    return "\n".join(
        line for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


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


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. The ordering edge — one isolating test per job
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_daily_job_reexports_downstream_of_the_writer():
    """THE regression. Wired anywhere upstream of `update_player_posteriors_op`, the re-export
    mirrors a table that has not been advanced yet — which is the lk9 defect verbatim, just
    moved to a new op."""
    code = _code_only(DAILY_JOB)
    writer_out = _assigned_from(code, WRITER, DAILY_JOB.name)
    reexport_start = _start_arg(code, REEXPORT, DAILY_JOB.name)
    assert reexport_start == writer_out, (
        f"{REEXPORT} is wired start={reexport_start!r} but must be wired start={writer_out!r} "
        f"(the {WRITER} output). Mirroring before the writer reproduces the 24h lag this op "
        f"exists to remove (measured 38.72h stale against a 36h threshold, 2026-08-09)."
    )


def test_the_statcast_catchup_job_reexports_downstream_of_the_writer():
    """THE SECOND CALLER. statcast_catchup_job runs the same writer when a late Statcast slate
    lands; without its own re-export the mirror freezes until the next morning's daily run.
    Separate isolating fixture — the daily edge can hold while this one is missing."""
    code = _code_only(SENSOR_JOBS)
    writer_out = _assigned_from(code, WRITER, SENSOR_JOBS.name)
    reexport_start = _start_arg(code, REEXPORT, SENSOR_JOBS.name)
    assert reexport_start == writer_out, (
        f"{REEXPORT} is wired start={reexport_start!r} in {SENSOR_JOBS.name} but must be wired "
        f"start={writer_out!r} (the {WRITER} output)."
    )


def test_the_writer_caller_registry_is_still_exhaustive():
    """INC-38: a per-caller fix fails exactly where the caller list is incomplete.

    Every job module that WIRES the writer must also wire the re-export. Non-vacuity is
    asserted explicitly — an empty match set would otherwise pass on nothing (NF1.7 (a)), and
    a bare name count would over-count imports, so this matches CALL SITES only.
    """
    callers = {}
    for path in sorted(JOBS_DIR.glob("*.py")):
        code = _code_only(path)
        if re.search(rf"{WRITER}\(\s*start\s*=", code):
            callers[path.name] = bool(re.search(rf"{REEXPORT}\(\s*start\s*=", code))
    assert len(callers) >= 2, (
        f"expected the writer to be wired in at least 2 job modules (daily_ingestion_job, "
        f"sensor_jobs) — found {sorted(callers)}. If a job was renamed, update this guard; an "
        f"empty/short registry makes every assertion below vacuous."
    )
    assert set(callers) == {"daily_ingestion_job.py", "sensor_jobs.py"}, (
        f"the {WRITER} caller set changed: {sorted(callers)}. A NEW job running the writer "
        f"needs its own {REEXPORT} leaf, or that job advances Snowflake while the S3 mirror "
        f"freezes (the INC-38 every-caller lesson)."
    )
    missing = sorted(name for name, ok in callers.items() if not ok)
    assert not missing, (
        f"these job modules wire {WRITER} but not {REEXPORT}: {missing}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. The op itself — a leaf, ALERT tier, exporting the right table
# ══════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "path", [DAILY_JOB, SENSOR_JOBS], ids=["daily_ingestion_job", "sensor_jobs"]
)
def test_the_reexport_is_a_fan_out_leaf_and_never_threaded_into_the_chain(path: Path):
    """Structural proof it cannot withhold a slate: its result is never bound, so nothing can
    chain off it. Threading it between the player and team writers would let a mirror failure
    skip p_team / p_matchup / predict."""
    code = _code_only(path)
    bound = re.findall(rf"^\s*(\w+)\s*=\s*{REEXPORT}\(", code, re.MULTILINE)
    assert not bound, (
        f"{REEXPORT} binds its output to {bound} in {path.name} — it must be an unbound "
        f"fan-out leaf so a mirror failure can never block the sequential chain or predict."
    )


def test_the_op_exports_exactly_the_player_sequential_mirror():
    """Pin the argv, not the prose. The op's docstring names the table repeatedly, so a
    substring match on the whole function would pass with the --table argument deleted — and a
    bare `export_w8a_precursors_to_s3.py` with no --table re-exports ALL SEVEN mirrors, adding
    six needless Snowflake SELECT *s to the critical daily path."""
    code = _code_only(DAILY_OPS)
    start = code.find(f"def {REEXPORT}")
    assert start != -1, f"{REEXPORT} not found in {DAILY_OPS.name}"
    body = code[start:start + 6000]
    # drop the docstring so its prose cannot satisfy the argv match
    if '"""' in body:
        head, _, rest = body.partition('"""')
        body = head + rest.partition('"""')[2]
    assert "export_w8a_precursors_to_s3.py" in body, (
        "the re-export no longer calls the W8a precursor exporter"
    )
    assert re.search(rf'"--table",\s*"{MIRRORED_TABLE}"', body), (
        f'the re-export must pass ["--table", "{MIRRORED_TABLE}"] as real argv; found none in '
        f"the comment-stripped, docstring-stripped body."
    )


def test_the_op_is_alert_tier_and_cannot_raise():
    """ALERT-loud-but-continue, and it must actually PAGE — E11.30's finding was that several
    ops labelled ALERT only ever reached context.log.warning, so a real failure was detected
    and never notified. A tier enforced only by a docstring is not enforced."""
    code = _code_only(DAILY_OPS)
    start = code.find(f"def {REEXPORT}")
    body = code[start:start + 6000]
    if '"""' in body:
        head, _, rest = body.partition('"""')
        body = head + rest.partition('"""')[2]
    # stop at the next op definition so we only read this function
    nxt = body.find("@op(")
    if nxt != -1:
        body = body[:nxt]
    assert "send_alert(" in body, f"{REEXPORT} must page via send_alert (E11.30)"
    assert "except Exception" in body, f"{REEXPORT} must swallow its failure (ALERT tier)"
    assert not re.search(r"^\s+raise\b", body, re.MULTILINE), (
        f"{REEXPORT} must never re-raise — it is a mirror, not a serving gate."
    )


def test_the_op_is_not_gated_behind_the_w8a_flags():
    """Deliberate: the export is a plain SELECT * → S3 with no dependency on the --w8a DuckDB
    build, and the mirror's currency is wanted whether or not that build runs. Gating it on
    _w8a_mirror_on would also make a W8A_LAKEHOUSE_S3 lapse freeze the mirror silently — the
    documented-but-never-set class. Pinned so a later 'consistency' tidy-up has to argue."""
    code = _code_only(DAILY_OPS)
    start = code.find(f"def {REEXPORT}")
    body = code[start:start + 6000]
    if '"""' in body:
        head, _, rest = body.partition('"""')
        body = head + rest.partition('"""')[2]
    nxt = body.find("@op(")
    if nxt != -1:
        body = body[:nxt]
    for gate in ("_w8a_mirror_on", "_w8a_serving_on", "_run_w8a_mirror"):
        assert gate not in body, (
            f"{REEXPORT} now calls {gate} — the re-export must run unconditionally; a gated "
            f"mirror freezes silently when the flag lapses."
        )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. The freshness flip and the ordering fix must ship together
# ══════════════════════════════════════════════════════════════════════════════════════════

def _freshness_module():
    """Load check_data_freshness.py by path (it is a script, not a package module)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_e1124_freshness_for_reexport", REPO_ROOT / "scripts" / "check_data_freshness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_player_seq_freshness_entry_reads_s3():
    """The dividend this change buys for E11.24 target 3: its third blocker is cleared."""
    fresh = _freshness_module()
    cfg = fresh.FRESHNESS_THRESHOLDS[f"baseball_data.betting.{MIRRORED_TABLE}"]
    assert fresh.entry_source(cfg) == "s3", (
        "the player_sequential_posteriors freshness entry should read the S3 mirror now that "
        "the re-export keeps it current."
    )


def test_reading_s3_requires_the_reexport_to_be_wired_in_every_writer_job():
    """THE COUPLING, made mechanical. An S3-sourced entry on a box still running the
    un-reordered graph is a guaranteed daily false STALE (38.72h vs a 36h threshold). This test
    is NON-VACUOUS today because the entry IS s3 — if a future change reverts the wiring while
    leaving the source flipped, it goes red here rather than on the box."""
    fresh = _freshness_module()
    cfg = fresh.FRESHNESS_THRESHOLDS[f"baseball_data.betting.{MIRRORED_TABLE}"]
    if fresh.entry_source(cfg) != "s3":
        pytest.skip("entry is Snowflake-sourced — the coupling does not apply")
    for path in (DAILY_JOB, SENSOR_JOBS):
        code = _code_only(path)
        assert re.search(rf"{REEXPORT}\(\s*start\s*=", code), (
            f"the freshness entry reads the S3 mirror but {path.name} no longer wires "
            f"{REEXPORT} — the mirror will fall a writer-cycle behind and the monitor will "
            f"report a false STALE every evening."
        )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. The same edges, re-proven off the COMPILED Dagster graph
# ══════════════════════════════════════════════════════════════════════════════════════════
# Needs the dbt manifest to import `pipeline` (E11.23), so these are @slow — CI's slow gate
# runs `dbtf parse` first, which builds it. Marked skipif as well so a fresh worktree without
# the manifest reports a skip instead of a collection crash (NF-D18).

_MANIFEST = REPO_ROOT / "dbt" / "target" / "manifest.json"
requires_pipeline = pytest.mark.skipif(
    not _MANIFEST.exists(), reason="needs the dbt manifest to import `pipeline` (E11.23)"
)


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

    def _daily(self):
        from pipeline.jobs.daily_ingestion_job import daily_ingestion_job
        return self._upstreams(daily_ingestion_job)

    def _catchup(self):
        from pipeline.jobs.sensor_jobs import statcast_catchup_job
        return self._upstreams(statcast_catchup_job)

    def test_the_dependency_probe_actually_finds_edges(self):
        """POSITIVE CONTROL. Without it, an empty upstream set below could mean 'the op is a
        leaf' OR 'the probe sees nothing at all' — not the same finding (NF1.7 (a))."""
        daily = self._daily()
        assert daily[WRITER] == ["dbt_build_bullpen_posteriors_op"], (
            f"the probe cannot even see the writer's own upstream edge: {daily.get(WRITER)}"
        )
        assert len([n for n, u in daily.items() if u]) > 20

    def test_the_daily_reexport_edge(self):
        assert self._daily()[REEXPORT] == [WRITER]

    def test_the_catchup_job_reexport_edge(self):
        assert self._catchup()[REEXPORT] == [WRITER]

    @pytest.mark.parametrize("which", ["daily", "catchup"])
    def test_the_reexport_is_a_leaf_in_the_compiled_graph(self, which):
        upstreams = self._daily() if which == "daily" else self._catchup()
        dependents = sorted(n for n, u in upstreams.items() if REEXPORT in u)
        assert dependents == [], (
            f"{REEXPORT} must be a leaf in the {which} job; depended on by {dependents}"
        )
