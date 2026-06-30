"""
gen_type_contract.py  (INC-19 DURABLE TYPE-PIN — 2026-06-29)
============================================================
Codegen + check helper for the type-contract that cures the recurring
NUMBER<->FLOAT incremental-drift HALT class (INC-15 / W1d / INC-16-P0 / INC-19 /
INC-19-recurrence — 5 incidents). See CLAUDE.md "type-contract guard".

THE PROBLEM
  A lakehouse dual-branch migration makes an upstream column compute as DuckDB
  DOUBLE -> parquet -> Snowflake FLOAT, but a downstream `incremental` +
  `on_schema_change='sync_all_columns'` table still stores it as NUMBER(38,x).
  Snowflake can't ALTER NUMBER->FLOAT -> `002108` -> the op HALTs and an operator
  must DROP+rebuild. `feature_pregame_game_features_raw` has been the victim 5x.

THE CURE (prevention)
  `feature_pregame_game_features_raw` wraps its `final` CTE in a generated
  `-- TYPE-PIN-START ... -- TYPE-PIN-END` block that casts every FLOAT output column
  to an explicit `::double`, so the incremental's stored type is immune to any
  upstream flip. The set of pinned columns is the SOURCE OF TRUTH in
  dbt/type_contracts/feature_pregame_game_features_raw.types.json.

THE GUARD (enforcement)
  betting_ml/tests/test_type_contract_guard.py (fast gate) + `--check` here assert
  the model's TYPE-PIN block still matches the manifest, so a type-drifting PR is RED
  before merge, not discovered at the next prod rebuild.

INTENDED-TYPE-CHANGE WORKFLOW (the convention)
  When you migrate a model / intend a type change you UPDATE THE MANIFEST IN THE SAME PR:
    1. Edit the manifest (move a column in/out of `double_pinned`, or add/remove a
       column from `all_columns`). To re-derive the truth from the live table:
         select listagg(case when data_type='FLOAT'
                  then lower(column_name) else null end, ',')
                  within group (order by column_name)            -- => double_pinned
         from baseball_data.information_schema.columns
         where table_schema='BETTING_FEATURES'
           and table_name='FEATURE_PREGAME_GAME_FEATURES_RAW';
    2. `uv run python scripts/gen_type_contract.py --write`  (sync the SQL block)
    3. Commit the model + manifest diff. If a STORED type actually changed
       (NUMBER<->FLOAT), the operator must DROP+rebuild the incremental — dbt-fusion
       `--full-refresh` MERGEs, it does NOT DROP+CREATE (see CLAUDE.md).

Usage:
  uv run python scripts/gen_type_contract.py --check     # CI: exit 1 on drift
  uv run python scripts/gen_type_contract.py --write      # regenerate the SQL block
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]

# (manifest, model) pairs the contract governs. Scoped to the incremental feature
# models that actually HALT on NUMBER<->FLOAT drift (the dual-branch marts are
# view/table — rebuilt fresh, no ALTER — so they don't HALT). Add future incremental
# victims here.
CONTRACTS = [
    (
        REPO / "dbt/type_contracts/feature_pregame_game_features_raw.types.json",
        REPO / "dbt/models/feature/feature_pregame_game_features_raw.sql",
    ),
    # E11.1-W8a: the 5 EB-posterior incrementals migrated to a DuckDB/S3 dual-branch.
    # Their DuckDB branch ends in `select * from final` (inside the `{% if duckdb %}`
    # branch, immediately before `{% else %}`); the TYPE-PIN block replaces that select so
    # the S3 parquet / lakehouse_ext FLOAT types stay stable and the at-cutover DROP+rebuild
    # adopts a deterministic FLOAT schema (INC-19). (meta_model_features — the 6th INC-19
    # incremental — is DEFERRED: it depends on feature_pregame_public_betting_features, which
    # is W8b/raw-blocked, so it is NOT migrated in W8a.)
    (
        REPO / "dbt/type_contracts/eb_starter_posteriors.types.json",
        REPO / "dbt/models/eb_posteriors/eb_starter_posteriors.sql",
    ),
    (
        REPO / "dbt/type_contracts/eb_batter_posteriors_raw.types.json",
        REPO / "dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql",
    ),
    (
        REPO / "dbt/type_contracts/eb_bullpen_posteriors.types.json",
        REPO / "dbt/models/eb_posteriors/eb_bullpen_posteriors.sql",
    ),
    (
        REPO / "dbt/type_contracts/eb_bullpen_team_posteriors.types.json",
        REPO / "dbt/models/eb_posteriors/eb_bullpen_team_posteriors.sql",
    ),
    (
        REPO / "dbt/type_contracts/int_bullpen_ali_by_season.types.json",
        REPO / "dbt/models/eb_posteriors/int_bullpen_ali_by_season.sql",
    ),
]

_START = "-- TYPE-PIN-START (generated; do not hand-edit individual lines)"
_END = "-- TYPE-PIN-END"
# matches the whole generated block (header comment + START..END) so --write is idempotent
_BLOCK_RE = re.compile(
    r"-- ={4,}\n-- INC-19 DURABLE TYPE-PIN.*?" + re.escape(_END) + r"\n?",
    re.DOTALL,
)
# first-time bootstrap: the un-pinned model ends its computed branch in `select * from final`.
# Two layouts: (a) single-branch models end at EOF (feature_pregame_game_features_raw);
# (b) E11.1-W8a dual-branch models have it inside `{% if target.name == 'duckdb' %}`,
# immediately before `{% else %}` (the Snowflake branch reads `... from lakehouse_ext.<model>`,
# never `from final`, so the lookahead never matches that one). The lookahead keeps the
# replacement scoped to the DuckDB branch's terminal select.
_BOOTSTRAP_RE = re.compile(
    r"select\s+\*\s+from\s+final\s*(?=\n*\s*\{%-?\s*else|\s*$)",
    re.IGNORECASE,
)


def load_manifest(path: pathlib.Path) -> dict:
    m = json.loads(path.read_text())
    cols = m["all_columns"]
    pinned = set(m["double_pinned"])
    assert len(cols) == len(set(cols)), f"{path.name}: duplicate column in all_columns"
    missing = pinned - set(cols)
    assert not missing, f"{path.name}: double_pinned not in all_columns: {sorted(missing)}"
    return m


def build_block(manifest: dict) -> str:
    cols = manifest["all_columns"]
    pinned = set(manifest["double_pinned"])
    lines = [
        (f"    {c}::double as {c}" if c in pinned else f"    {c}")
        for c in cols
    ]
    cast_body = ",\n".join(lines)
    return f"""-- ============================================================================
-- INC-19 DURABLE TYPE-PIN (2026-06-29) — see CLAUDE.md "type-contract guard".
-- Every FLOAT output column is cast to an explicit ::double so an upstream
-- NUMBER<->FLOAT migration (a lakehouse dual-branch flip) can NEVER drift this
-- incremental's stored column type again — the recurring HALT class that fired
-- 5x (INC-15 / W1d / INC-16-P0 / INC-19 / INC-19-recurrence). ::double (NOT
-- ::float = 32-bit in DuckDB) is value-preserving 64-bit; it ADOPTS the FLOAT
-- types the table already holds, so this is a no-op incremental (no type ALTER).
--
-- This pinned set is contract-checked by betting_ml/tests/test_type_contract_guard.py
-- against dbt/type_contracts/{manifest['model']}.types.json. If you ADD a column or
-- INTEND a type change, update BOTH this block AND that manifest in the SAME PR
-- (regenerate via scripts/gen_type_contract.py --write) or CI goes red. A new
-- numeric column that can ever be FLOAT MUST be ::double-pinned here.
-- NOTE: the explicit outer select is intentional — a column added to `final` but
-- not added here is DROPPED; the guard's set-equality check catches that too.
{_START}
select
{cast_body}
from final
{_END}
"""


def extract_block(model_src: str) -> str | None:
    m = _BLOCK_RE.search(model_src)
    return m.group(0) if m else None


def render(manifest: dict, model_src: str) -> str:
    """Return model_src with the TYPE-PIN block synced to the manifest."""
    block = build_block(manifest)
    if _BLOCK_RE.search(model_src):
        return _BLOCK_RE.sub(lambda _: block, model_src)
    new_src, n = _BOOTSTRAP_RE.subn(block, model_src)
    if n != 1:
        raise SystemExit(
            "could not locate the TYPE-PIN block nor a trailing `select * from final` "
            f"to bootstrap in the model"
        )
    return new_src


def check() -> int:
    problems: list[str] = []
    for manifest_path, model_path in CONTRACTS:
        manifest = load_manifest(manifest_path)
        model_src = model_path.read_text()
        expected = build_block(manifest)
        actual = extract_block(model_src)
        if actual is None:
            problems.append(
                f"{model_path.name}: no TYPE-PIN block found — run "
                f"`gen_type_contract.py --write`"
            )
        elif actual.strip() != expected.strip():
            problems.append(
                f"{model_path.name}: TYPE-PIN block is OUT OF SYNC with "
                f"{manifest_path.name}. An intended type change must update the manifest "
                f"and re-run `gen_type_contract.py --write` in the SAME PR (and the "
                f"operator DROP+rebuilds the incremental if a stored type changed)."
            )
    if problems:
        print("TYPE-CONTRACT DRIFT:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"OK — {len(CONTRACTS)} type-contract(s) in sync.")
    return 0


def write() -> int:
    for manifest_path, model_path in CONTRACTS:
        manifest = load_manifest(manifest_path)
        model_src = model_path.read_text()
        new_src = render(manifest, model_src)
        if new_src != model_src:
            model_path.write_text(new_src)
            print(f"updated {model_path.relative_to(REPO)}")
        else:
            print(f"unchanged {model_path.relative_to(REPO)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="INC-19 type-contract codegen/guard")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="exit 1 if a model's block != manifest")
    g.add_argument("--write", action="store_true", help="regenerate the model's TYPE-PIN block")
    args = ap.parse_args()
    return check() if args.check else write()


if __name__ == "__main__":
    sys.exit(main())
