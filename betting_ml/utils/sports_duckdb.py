"""NF-INFRA1 — the ONE authoritative resolver for the sports (NCAAF/NFL) DuckDB path.

WHY THIS MODULE EXISTS (NF-FRESH1, 2026-08-15 — 19 green runs over a dead feed):
`sports_nfl_sleeper_injuries_schedule` reported SUCCESS on 19 consecutive daily runs while
`nfl/raw/sleeper_injuries` held ONE 19-day-old Delta commit. The op died at
`duckdb.connect(read_only=True)` in ~114ms and a bare `except` swallowed it. Two independent
defects produced that, and this module fixes the second one:

  1. the file was ABSENT (gitignored ⇒ not in the `COPY . .` image, `/tmp` wiped by every deploy,
     `/app` replaced by the image) — cured by the `sports_duckdb` named VOLUME in
     `services/dagster/aws/docker-compose.yml`, mounted at `BOX_VOLUME_DIR`; and
  2. ⭐ nothing agreed on WHERE it was. `SPORTS_DUCKDB_PATH` was unset on the box and FOUR owners
     each supplied their own default: the Sleeper ingest op → `sports_dbt/sports.duckdb`, the
     dbt-build op → `/tmp/sports_ncaaf.duckdb`, `profiles.yml` → its own, and the game-day
     schedules → `/tmp/sports_ncaaf.duckdb` **and** `/tmp/sports_nfl.duckdb`. So the NFL build
     wrote one file while the NFL game-day gate read a file that never existed (permanently
     fail-open, `nf_nflverse_data_health_audit.md` #8). This is the repo's recurring
     "one logical thing, many execution owners" shape — INC-30 (crontab under two users),
     INC-36 (deploy lock), INC-38 (a per-caller flag on 2 of 4 callers).

⭐ THE CONTRACT — ONE env var, ONE default, no per-owner literals:
  * On the BOX, `SPORTS_DUCKDB_PATH` is REQUIRED: it is listed in `services/dagster/aws/env.required`,
    so `deploy.sh` FAILS the deploy when it is missing or empty. It must be `BOX_DUCKDB_PATH`
    (inside the mounted volume) — anything else is deploy-ephemeral again.
  * OFF the box (laptop research, CI) it falls back to `REPO_DEFAULT`, the path every
    `run_*.py --duckdb` flag already defaults to, so laptop workflows are unchanged.
  * Every owner calls `sports_duckdb_path()`. A module that writes its own default literal
    re-creates the divergence — `betting_ml/tests/test_nf_infra1_sports_duckdb_path.py` fails on one.

⚠️ NCAAF AND NFL SHARE ONE FILE, deliberately: `_run_sports_dbt` exports a single
`SPORTS_DUCKDB_PATH` for both projects and dbt materializes each sport into its own SCHEMA
(`main_ncaaf_marts`, `main_nfl_staging`, …), so one database file holds both and every gate
relation stays schema-qualified. Two paths never bought isolation — they only ever produced a
gate reading a file nothing wrote.

Import-safe for the fast gate (E11.23): pure stdlib, no `pipeline`, no IO at import.
"""

from __future__ import annotations

import os
from pathlib import Path

# The env var every owner reads. Listed in services/dagster/aws/env.required ⇒ deploy-time gated.
ENV_VAR = "SPORTS_DUCKDB_PATH"

# The PERSISTENT directory on the box — the `sports_duckdb` named volume's mount point on
# `dagster-codeloc`. A named volume is what survives `docker compose up -d` / a redeploy;
# `/app` is replaced by the new image and `/tmp` is wiped, which is exactly how a DAILY op came
# to depend on a WEEKLY-rebuilt, deploy-ephemeral artifact (the INC-25 shape).
BOX_VOLUME_DIR = "/var/lib/credence/sports"

# What SPORTS_DUCKDB_PATH must be set to on the box.
BOX_DUCKDB_PATH = f"{BOX_VOLUME_DIR}/sports.duckdb"

# The laptop/CI default: repo-root-relative, matching every `run_*.py --duckdb` default.
REPO_DEFAULT = "quant_sports_intel_models/sports_dbt/sports.duckdb"


def sports_duckdb_path() -> str:
    """The sports DuckDB path for THIS process — the single source of truth.

    ⚠️ An env var that is PRESENT BUT EMPTY is treated as unset. An empty value shadows a code
    default (`os.environ.get(k, d)` returns `""`), which is the exact trap `env.required`
    documents for `CACHE_BUCKET`/`USER_BETS_TABLE` — here it would silently point DuckDB at `""`.
    """
    return (os.environ.get(ENV_VAR) or "").strip() or REPO_DEFAULT


def resolve_sports_duckdb(app_dir: "str | Path | None" = None) -> Path:
    """`sports_duckdb_path()` as an ABSOLUTE path, anchoring a relative value on `app_dir`
    (default `$APP_DIR`, i.e. `/app` in the container) rather than on the process CWD — a Dagster
    op and the subprocess it spawns must never resolve the same string differently."""
    raw = Path(sports_duckdb_path())
    if raw.is_absolute():
        return raw
    base = Path(app_dir if app_dir is not None else os.environ.get("APP_DIR", "/app"))
    return base / raw


def sports_duckdb_env(env: "dict[str, str] | None" = None) -> dict[str, str]:
    """A subprocess env with `SPORTS_DUCKDB_PATH` pinned to the resolved ABSOLUTE path.

    Passing the resolved path (not the raw value) is load-bearing: `_run_sports_dbt` runs dbt with
    `cwd=SPORTS_DBT_DIR`, so a repo-root-relative default would bind to a different file inside the
    subprocess than the op just checked for.
    """
    out = dict(os.environ if env is None else env)
    out[ENV_VAR] = str(resolve_sports_duckdb())
    return out


def missing_duckdb_remedy(resolved: "str | Path") -> str:
    """The one-sentence operator remedy for an absent sports DuckDB.

    Shared so every caller names the SAME cure — the NF-FRESH1 failure was legible only because
    someone read the Delta log; an op that dies must say what to do instead of dying opaquely.
    """
    return (
        f"the sports DuckDB is MISSING at {resolved} ({ENV_VAR}="
        f"{os.environ.get(ENV_VAR) or '<unset>'}).\n\n"
        f"`*.duckdb` is gitignored, so it is NOT in the deployed image — it lives on the "
        f"`sports_duckdb` named volume mounted at {BOX_VOLUME_DIR} and is materialized by running "
        f"`sports_nfl_dbt_build_job` on the box. Confirm the box `.env` sets "
        f"{ENV_VAR}={BOX_DUCKDB_PATH} (it is in env.required, so a deploy fails without it), then "
        f"launch that job once. Until then this step pages rather than reporting a green run that "
        f"did nothing."
    )
