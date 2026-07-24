"""test_retired_source_guard.py — prevent the "frozen native source" straggler class.

THE BUG CLASS (2026-07-23): when a raw capture flips S3-native (its Snowflake writer is retired)
or a native table is dropped, any dbt model whose SNOWFLAKE-executable branch still reads that table
via `{{ source(...) }}` silently serves FROZEN data. It hit `stg_statsapi_probable_pitchers` and
`stg_statsapi_starter_snapshots`: the native `statsapi.monthly_schedule` writer was retired on
2026-07-20 (schedule capture went S3-native), those models kept reading the native source, so games
whose starters MLB announced after 7/20 served both-NULL probables → NO prediction. `stg_statsapi_games`
had already been repointed to the fresh S3 external table; the other two were stragglers.

THE RULE: a model whose feed lives in the S3 lakehouse must read its FRESH external table
(`baseball_data.lakehouse_ext.<model>`) on the Snowflake target, NOT re-flatten the retired native
`source()`. This guard fails if any RETIRED source (below) is read in a Snowflake-executable branch.

MAINTENANCE: add a (schema, table) here THE MOMENT its writer is retired / its table is dropped. If a
model still reads it, either repoint that model's Snowflake branch to the lakehouse_ext table or (if
the model is intentionally dead on SF) mark its Snowflake branch `enabled=false` — both clear the guard.

Pure source inspection — fast gate, no IO, does NOT import `pipeline` (manifest absent in the fast gate).
"""
from __future__ import annotations

import re
from pathlib import Path

# schema.table of native Snowflake sources whose WRITER is retired / table dropped. The fresh data
# now lives in the S3 lakehouse (read via baseball_data.lakehouse_ext.<model>). Reading any of these
# on the Snowflake target serves FROZEN data.
RETIRED_NATIVE_SOURCES = {
    ("statsapi", "monthly_schedule"),  # retired 2026-07-20 — schedule capture flipped S3-native
    ("oddsapi", "mlb_odds_raw"),       # retired 2026-07-05 — odds capture flipped S3-native
    ("savant", "batter_pitches"),      # dropped 2026-07-03 (W11-E) — pitch marts read S3 parquet
}

_MODELS_DIR = Path(__file__).resolve().parents[2] / "dbt" / "models"
_REPO_ROOT = _MODELS_DIR.parents[1]

_TAG = re.compile(r"{%-?\s*(if|else|endif)\b.*?-?%}", re.DOTALL)
_DUCKDB_IF = re.compile(r"{%-?\s*if\s+target\.name\s*==\s*'duckdb'\s*-?%}")
# SQL line/block comments + Jinja comments — stripped before scanning so PROSE mentioning a source
# (e.g. a cutover note explaining what the model USED to read) is never mistaken for a real ref
# (the "banned-scan trips on disclaimer prose" landmine, E9.26).
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/|{#.*?#}", re.DOTALL)


def _snowflake_region(sql: str) -> str:
    """Return the portion of a model that EXECUTES on the Snowflake target.

    - No `target.name == 'duckdb'` split → the whole file runs on Snowflake.
    - Split present → the `{% else %}` arm that pairs with the duckdb `{% if %}` (depth-matched, so a
      nested `{% if is_incremental() %}{% else %}` inside the duckdb arm is not mistaken for it).
    The duckdb-only arm is intentionally excluded — it may read raw parquet / a source for the S3
    build, which is correct there; only the Snowflake arm can serve a frozen native table.
    """
    m = _DUCKDB_IF.search(sql)
    if not m:
        return sql
    depth, else_start = 1, None
    for t in _TAG.finditer(sql, m.end()):
        kind = t.group(1)
        if kind == "if":
            depth += 1
        elif kind == "else" and depth == 1:
            else_start = t.end()
        elif kind == "endif":
            depth -= 1
            if depth == 0:
                return sql[else_start:t.start()] if else_start is not None else ""
    return sql[else_start:] if else_start is not None else ""


def _retired_reads(region: str) -> set[str]:
    body = _COMMENTS.sub(" ", region)  # drop prose so only executable Jinja refs are matched
    hits = set()
    for schema, table in RETIRED_NATIVE_SOURCES:
        # a REAL dbt source read is always Jinja-wrapped: {{ source('schema', 'table') }}
        pat = r"{{-?\s*source\(\s*['\"]%s['\"]\s*,\s*['\"]%s['\"]\s*\)\s*-?}}" % (
            re.escape(schema), re.escape(table))
        if re.search(pat, body):
            hits.add(f"{schema}.{table}")
    return hits


def test_no_model_reads_a_retired_native_source_on_snowflake():
    violations = []
    for sql_path in sorted(_MODELS_DIR.rglob("*.sql")):
        region = _snowflake_region(sql_path.read_text())
        # A Snowflake branch disabled via `enabled=false` can never run → not a violation.
        if re.search(r"enabled\s*=\s*false", region, re.IGNORECASE):
            continue
        hits = _retired_reads(region)
        if hits:
            violations.append(f"{sql_path.relative_to(_REPO_ROOT)} :: {sorted(hits)}")
    assert not violations, (
        "A dbt model reads a RETIRED native source on the Snowflake target — it will serve FROZEN "
        "data now that the writer is retired (see stg_statsapi_probable_pitchers / _starter_snapshots, "
        "2026-07-23). Repoint the Snowflake branch to `baseball_data.lakehouse_ext.<model>`:\n  "
        + "\n  ".join(violations)
    )


def test_registry_is_nonempty_and_well_formed():
    # Guard against an accidental wipe of the registry (which would make the check vacuously pass).
    assert RETIRED_NATIVE_SOURCES
    assert all(isinstance(s, str) and isinstance(t, str) for s, t in RETIRED_NATIVE_SOURCES)


# ── Python raw-SQL readers ────────────────────────────────────────────────────────
# The dbt guard above is blind to Python scripts that embed a retired table as a raw SQL string
# (the INC-27 lesson: the dbt DAG can't see them). backfill_lineup_state_scd2.py read the frozen
# native statsapi.monthly_schedule this way → feature_pregame_lineup_state froze at 7/20. This scan
# flags any `FROM`/`JOIN <fully-qualified retired table>` in the Python pipeline/serving code.
_PY_ROOTS = ["scripts", "pipeline", "betting_ml"]
_LINE_COMMENT = re.compile(r"#[^\n]*")
# Bytes pre-filter: only decode+scan a file that even mentions a retired table (skips ~all files).
_RETIRED_TOKENS = tuple(f"{s}.{t}".encode() for s, t in RETIRED_NATIVE_SOURCES)


def _retired_fqn_reads(py_src: str) -> set[str]:
    body = _LINE_COMMENT.sub(" ", py_src)  # drop # comments; SQL usually lives in string literals
    hits = set()
    for schema, table in RETIRED_NATIVE_SOURCES:
        fqn = rf"baseball_data\.{re.escape(schema)}\.{re.escape(table)}"
        # A READ site is FROM/JOIN <fqn>. A writer (CREATE/INSERT INTO) or a config dict entry is not
        # a stale-read and is intentionally NOT matched — only a direct table read serves frozen data.
        if re.search(rf"\b(?:FROM|JOIN)\s+{fqn}\b", body, re.IGNORECASE):
            hits.add(f"{schema}.{table}")
    return hits


def test_no_python_script_reads_a_retired_native_source():
    violations = []
    for root in _PY_ROOTS:
        base = _REPO_ROOT / root
        if not base.exists():
            continue
        for py_path in sorted(base.rglob("*.py")):
            if "/tests/" in py_path.as_posix():
                continue  # test fixtures legitimately embed example SQL
            raw = py_path.read_bytes()
            if not any(tok in raw for tok in _RETIRED_TOKENS):
                continue  # fast skip — file never mentions a retired table
            # errors="ignore": a few vendored/fixture files carry non-UTF-8 encodings; a retired-source
            # read would still be ASCII, so lossy decoding can't hide one.
            hits = _retired_fqn_reads(raw.decode("utf-8", errors="ignore"))
            if hits:
                violations.append(f"{py_path.relative_to(_REPO_ROOT)} :: {sorted(hits)}")
    assert not violations, (
        "A Python script reads a RETIRED native source via raw SQL (FROM/JOIN) — it serves FROZEN "
        "data now that the writer is retired (see backfill_lineup_state_scd2.py → the 7/20 lineup-state "
        "freeze, 2026-07-23). Repoint it to the fresh S3 feed (lakehouse_ext.* / the flattened staging "
        "table):\n  " + "\n  ".join(violations)
    )
