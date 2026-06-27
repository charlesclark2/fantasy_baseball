#!/usr/bin/env python3
"""INC-16-P5 CI guard — deploy-wiring asserts.

Catches the DEPLOY-ONLY failure modes that plain unit/compile CI never sees
(surfaced repeatedly in INC-16 P2/P4):

  1. PEM normalization present at every SNOWFLAKE_PRIVATE_KEY consumer — a Compose
     env_file can't carry real newlines, so the key arrives `\\n`-escaped/base64 and
     MUST be normalized before use, or ALL container Snowflake access breaks (P2).
  2. AWS_DEFAULT_REGION wired in the compose env — region-less boto3 dials an empty
     endpoint (P2).
  3. No DATABASE_URL / psycopg reintroduced on serving/capture paths — the serving
     store is DynamoDB+S3 now (P2); a stray PG ref would dial the dead Railway PG.

Exit 1 (loud) on any violation. Pure stdlib; no deps.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# (path, [accepted markers]) — file must contain at least one marker.
_PEM_CONSUMERS = [
    ("pipeline/resources/__init__.py", ["_normalize_pem"]),
    ("scripts/write_serving_store.py", ["_normalize_pem", "b64decode", r'replace("\\n"']),
    ("services/dbt_runner/entrypoint.sh", ["base64 -d"]),
    ("services/odds_capture/entrypoint.sh", ["base64 -d"]),
    ("services/schedule_capture/entrypoint.sh", ["base64 -d"]),
    ("services/derivative_capture/entrypoint.sh", ["base64 -d"]),
    ("services/weather_capture/entrypoint.sh", ["base64 -d"]),
]

# Serving/capture paths that must NOT reference the dead serving Postgres.
_NO_PG_PATHS = [
    "app/backend",
    "scripts/write_serving_store.py",
    "scripts/write_api_cache.py",
    "services/odds_capture",
    "services/schedule_capture",
    "services/derivative_capture",
    "services/weather_capture",
]
_PG_PATTERN = re.compile(r"DATABASE_URL|psycopg")

_COMPOSE = "services/dagster/aws/docker-compose.yml"


def _iter_py_and_sh(base: Path):
    if base.is_file():
        yield base
        return
    for p in base.rglob("*"):
        if p.suffix in (".py", ".sh") and p.is_file():
            yield p


def main() -> int:
    errors: list[str] = []

    # 1. PEM normalization at every consumer
    for rel, markers in _PEM_CONSUMERS:
        f = _ROOT / rel
        if not f.is_file():
            errors.append(f"PEM consumer missing: {rel}")
            continue
        text = f.read_text()
        if not any(m in text for m in markers):
            errors.append(f"{rel}: no PEM-normalization marker {markers} — "
                          f"SNOWFLAKE_PRIVATE_KEY consumed without \\n/base64 normalization")

    # 2. AWS_DEFAULT_REGION wired in compose
    compose = _ROOT / _COMPOSE
    if not compose.is_file():
        errors.append(f"missing {_COMPOSE}")
    elif "AWS_DEFAULT_REGION" not in compose.read_text():
        errors.append(f"{_COMPOSE}: AWS_DEFAULT_REGION not wired (region-less boto3 = empty endpoint)")

    # 3. No DATABASE_URL / psycopg on serving/capture paths
    for rel in _NO_PG_PATHS:
        base = _ROOT / rel
        if not base.exists():
            continue
        for f in _iter_py_and_sh(base):
            for i, line in enumerate(f.read_text().splitlines(), 1):
                if _PG_PATTERN.search(line):
                    errors.append(f"{f.relative_to(_ROOT)}:{i}: reintroduced PG reference "
                                  f"(serving cache is DynamoDB+S3 now): {line.strip()}")

    if errors:
        print("ERROR: deploy-wiring check failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("OK — deploy-wiring asserts pass (PEM normalization, region wired, no PG on serving/capture).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
