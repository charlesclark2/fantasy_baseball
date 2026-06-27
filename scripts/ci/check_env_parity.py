#!/usr/bin/env python3
"""INC-16-P5 CI guard — env-parity (template completeness).

Asserts every REQUIRED key (services/dagster/aws/env.required) is documented in
services/dagster/aws/.env.example, so a fresh box's .env (copied from the example)
prompts for the full set. This catches "the box .env is missing a key the ops read"
at PR time instead of as a silent/late runtime failure (P4 lost cycles to
CACHE_BUCKET / USER_BETS_TABLE / ARTIFACTS_FROM_S3 / USERS_TABLE this way).

The NON-EMPTY enforcement against the live box .env happens at deploy time in
services/dagster/aws/deploy.sh (CI can't see the gitignored box .env).

Exit 1 on any required key absent from .env.example.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_AWS = _ROOT / "services" / "dagster" / "aws"
_REQUIRED = _AWS / "env.required"
_EXAMPLE = _AWS / ".env.example"


def _keys_from_required(p: Path) -> list[str]:
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.split("=", 1)[0].strip())
    return out


def _keys_from_env_file(p: Path) -> set[str]:
    keys = set()
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def main() -> int:
    for f in (_REQUIRED, _EXAMPLE):
        if not f.is_file():
            print(f"ERROR: missing {f.relative_to(_ROOT)}", file=sys.stderr)
            return 1

    required = _keys_from_required(_REQUIRED)
    documented = _keys_from_env_file(_EXAMPLE)

    missing = [k for k in required if k not in documented]
    if missing:
        print("ERROR: required env keys missing from services/dagster/aws/.env.example:",
              file=sys.stderr)
        for k in missing:
            print(f"  - {k}", file=sys.stderr)
        print("\nAdd them to .env.example (a fresh box copies it) and to env.required "
              "if newly required.", file=sys.stderr)
        return 1

    print(f"OK — all {len(required)} required env keys are documented in .env.example.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
