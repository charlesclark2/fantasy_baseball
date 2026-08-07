#!/bin/bash
# Generate REAL dbt-fusion run_results.json fixtures for the INC-41 dbt-test pager tests.
#
#   bash betting_ml/tests/fixtures/inc41_dbt_run_results/generate_fixtures.sh
#
# LAPTOP only; needs the dbt-fusion binary (`dbtf`) + the dbt-duckdb adapter. ~10s, no warehouse.
# The fixtures are REAL dbt output rather than hand-written JSON on purpose: a hand-authored
# fixture encodes the author's BELIEF about dbt's format, so the suite would stay green if that
# belief were wrong (NF-C0e). Re-run this only when upgrading dbt-fusion — and when you do, re-read
# the four statuses, because the whole classifier rests on that encoding.
# See docs/inc41_dbt_test_pager.md.
set -u
DBT="${DBT:-dbtf}"                              # the dbt-fusion binary (repo convention: dbtf)
OUT="${1:-$(cd "$(dirname "$0")" && pwd)}"      # fixtures destination (default: alongside this script)
P="$(mktemp -d)/fixgen"                         # throwaway dbt project, never inside the repo

emit () {  # $1 = scenario name
  local name="$1"
  mkdir -p "$OUT/$name"
  cp "$P/target/run_results.json" "$OUT/$name/run_results.json"
  python3 - "$P/target/manifest.json" "$OUT/$name/manifest_severities.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
# Extract exactly what load_severity_map reads, preserving fusion's real UPPERCASE values.
out = {"nodes": {uid: {"config": {"severity": n.get("config", {}).get("severity")}}
                 for uid, n in m["nodes"].items() if uid.startswith("test.")}}
json.dump(out, open(sys.argv[2], "w"), indent=2, sort_keys=True)
PY
  echo "  -> $name"
}

setup () {
  rm -rf "$P"; mkdir -p "$P/models" "$P/tests"
  cat > "$P/dbt_project.yml" <<'EOF'
name: credence_fixture
version: '1.0'
profile: credence_fixture
model-paths: ["models"]
test-paths: ["tests"]
EOF
  cat > "$P/profiles.yml" <<'EOF'
credence_fixture:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: fixture.duckdb
      schema: main
EOF
  # Mirrors the repo's real contract split: a serving-critical not_null (severity: error)
  # beside a peripheral data-quality check (severity: warn).
  cat > "$P/models/schema.yml" <<'EOF'
models:
  - name: served_prices
    columns:
      - name: price
        data_tests:
          - not_null:
              config:
                severity: error
          - unique:
              config:
                severity: warn
EOF
}

run () { (cd "$P" && $DBT build --project-dir "$P" --profiles-dir "$P" >/dev/null 2>&1); }

mkdir -p "$OUT"

# A — clean suite: both tests pass.
setup
echo "select 1 as price union all select 2 as price" > "$P/models/served_prices.sql"
run; emit all_pass

# B — the INC-41 shape: a serving-critical (severity: error) not_null goes red on a nulled price.
setup
echo "select 1 as price union all select null as price" > "$P/models/served_prices.sql"
run; emit error_severity_failure

# C — a peripheral (severity: warn) check goes red. Must NOT page.
setup
echo "select 1 as price union all select 1 as price" > "$P/models/served_prices.sql"
run; emit warn_severity_failure

# D — the false-page guard: a severity:warn test that CANNOT EXECUTE reports status "error",
#     which is indistinguishable from a broken serving contract at the status level.
setup
echo "select 1 as price union all select 2 as price" > "$P/models/served_prices.sql"
cat > "$P/tests/peripheral_broken.sql" <<'EOF'
{{ config(severity='warn') }}
select * from {{ ref('served_prices') }} where column_that_does_not_exist = 1
EOF
run; emit warn_severity_errored

echo "done"
