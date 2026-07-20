"""E11.20 phase-2a — the intraday Snowflake consumers stay repointed.

Two peripheral-but-frequent writers used to open a Snowflake session on every run:
  • scripts/write_pitcher_k_projections.py — hourly host cron (capture.crontab, ~15×/day)
  • scripts/generate_zone_overlays_today.py — daily op, now also a lineup_monitor_job leaf
E11.20-COST established that warehouse cost is WAKE/IDLE-dominated, so a frequent consumer is
expensive no matter how cheap its queries are. Both now read the S3 lakehouse via DuckDB.

These are SOURCE-INSPECTION guards on purpose: the fast gate has no dbt manifest, so a test here
may not import `pipeline`, and importing the scripts themselves would drag in pandas/duckdb/boto3
for no benefit. They encode the invariants a future edit is most likely to break — re-introducing
a Snowflake read, or hardcoding a lakehouse glob (the 2026-07-20 P0, where a consumer pinned to the
retired parquet layout took the whole daily job down).
"""
from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_K_WRITER = _ROOT / "scripts" / "write_pitcher_k_projections.py"
_ZONE = _ROOT / "scripts" / "generate_zone_overlays_today.py"

_SCRIPTS = pytest.mark.parametrize(
    "path", [_K_WRITER, _ZONE], ids=lambda p: p.name
)


def _code_only(path: Path) -> str:
    """Source with docstrings and `#` comments stripped.

    A banned-pattern scan must look at CODE, not prose: these files DOCUMENT the anti-patterns
    they fixed (\"used to call date.today()\"), and a naive substring scan flags that explanation as
    a regression. Same trap as the E9.26 honest-framing scan tripping on its own disclaimer text.
    """
    import ast
    import io
    import tokenize

    src = path.read_text()
    tree = ast.parse(src)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        # NB `body` is a LIST on Module/ClassDef/FunctionDef but a single node on e.g. IfExp,
        # so the isinstance check is load-bearing, not defensive noise.
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body or not isinstance(body[0], ast.Expr):
            continue
        val = body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            doc_lines.update(range(val.lineno, (val.end_lineno or val.lineno) + 1))

    out: list[str] = []
    readline = io.StringIO(src).readline
    comment_spans: dict[int, list[tuple[int, int]]] = {}
    for tok in tokenize.generate_tokens(readline):
        if tok.type == tokenize.COMMENT:
            comment_spans.setdefault(tok.start[0], []).append((tok.start[1], tok.end[1]))

    for i, line in enumerate(src.splitlines(), start=1):
        if i in doc_lines:
            continue
        for start, _end in sorted(comment_spans.get(i, []), reverse=True):
            line = line[:start]
        out.append(line)
    return "\n".join(out)


@_SCRIPTS
def test_no_snowflake_connection_in_the_read_path(path: Path) -> None:
    """Neither script may open a Snowflake connection.

    The ONE sanctioned exception is the K writer's starter_ip self-heal, which shells OUT to the
    signal generator + the W9 export mirror in a subprocess (that signal store's writer is still a
    Snowflake MERGE). A subprocess is not an in-process connection, so the ban below is absolute:
    no get_snowflake_connection import, no snowflake.connector.
    """
    src = _code_only(path)
    assert "get_snowflake_connection" not in src, (
        f"{path.name} re-introduced an in-process Snowflake connection. This script runs "
        f"frequently; a connect IS a warehouse wake (E11.20-COST). Read the S3 lakehouse instead."
    )
    assert "snowflake.connector" not in src, f"{path.name} imports the Snowflake connector."


@_SCRIPTS
def test_no_fully_qualified_snowflake_tables(path: Path) -> None:
    """No `baseball_data.<schema>.<table>` references — those only resolve in Snowflake."""
    src = _code_only(path)
    assert "baseball_data." not in src, (
        f"{path.name} still references a fully-qualified Snowflake table. Register the lakehouse "
        f"table as a bare-name view via register_lakehouse_views and query that."
    )


@_SCRIPTS
def test_lakehouse_views_go_through_the_delta_aware_registrar(path: Path) -> None:
    """Reads must route through register_lakehouse_views, never a hardcoded parquet glob.

    Phase 1.5 deleted the compat parquet for the Delta-migrated W1 marts. A pinned
    `read_parquet('.../lakehouse/<table>/**/*.parquet')` therefore raises "No files found" for
    those tables — which is exactly how the 2026-07-20 P0 killed the daily job before predict.
    """
    src = _code_only(path)
    assert "register_lakehouse_views" in src, (
        f"{path.name} must register lakehouse views through the Delta-aware registrar."
    )
    assert "/lakehouse/" not in src, (
        f"{path.name} appears to hardcode a lakehouse path. Use register_lakehouse_views so a "
        f"cut-over table resolves via delta_scan instead of the retired parquet layout."
    )


def test_zone_overlay_uses_the_baseball_day_clock() -> None:
    """INC-22: the target date must be the US baseball-day, not the raw UTC box clock.

    `date.today()` here is defect (a) of the three-week zone-overlay outage — after ~17:00 PT the
    UTC clock rolls to tomorrow, so the pair query asked for a date with no lineups, wrote nothing,
    and still exited 0.
    """
    src = _code_only(_ZONE)
    assert "current_game_date_iso" in src, "zone overlays must use current_game_date_iso()."
    assert "date.today()" not in src, (
        "zone overlays reverted to the raw UTC clock (INC-22)."
    )


def test_zone_overlay_warns_loudly_when_it_writes_nothing() -> None:
    """A WARN-tier script that exits 0 while writing nothing is how the outage hid for 3 weeks.

    The zero-pair and zero-overlay paths must emit a stderr WARNING, per the E11.7 contract that a
    graceful skip is never a silent one.
    """
    src = _code_only(_ZONE)
    assert src.count("file=sys.stderr") >= 3, (
        "zone overlays must WARN to stderr on the zero-pair and zero-overlay paths — a silent "
        "exit-0 is what made this dead feature invisible."
    )


def test_k_writer_reads_the_history_frame_from_s3() -> None:
    """The 2021-present context frame must come from the lakehouse, not Snowflake.

    betting_ml/data/cache is gitignored, so a CD-built image starts with an EMPTY cache — without
    use_s3 the first hourly run of every new image pulled the whole windowed frame from Snowflake.
    """
    src = _code_only(_K_WRITER)
    assert "use_s3=True" in src, (
        "write_pitcher_k_projections must call load_frame_cached(..., use_s3=True); the cache is "
        "gitignored so a fresh container would otherwise fall back to Snowflake."
    )


def test_frame_query_rewrite_maps_every_snowflake_reference() -> None:
    """_duckdb_frame_query must fully rewrite the shared Snowflake SQL — no silent leftovers."""
    from betting_ml.scripts.prop_pricing.fit_prop_pricing import _duckdb_frame_query

    sql = _duckdb_frame_query(2021, 2026)
    assert "baseball_data." not in sql
    # TRAILING is reserved in DuckDB but not Snowflake — the CTE has to stay quoted.
    assert '"trailing"' in sql
    # starter_ip_signals.GAME_PK is VARCHAR in the W9 mirror; the join key needs the cast.
    assert "sig.game_pk::bigint" in sql
