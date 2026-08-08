#!/usr/bin/env python3
"""
parity_check_eb_reader_repoint.py  (E11.24 target-6 successor — the EB reader repoint gate)
-------------------------------------------------------------------------------------------
Asserts that repointing `update_player_posteriors.py`'s EB prior/role reads from Snowflake to
the S3 lakehouse does not change WHAT THE OP CONSUMES.

⭐ WHY THIS IS NOT `parity_check_w8a.py`. That script compares whole-table fingerprints, and on
these two models it is GUARANTEED to differ: `betting.eb_starter_posteriors` and
`eb_batter_posteriors_raw` are `incremental` + `incremental_strategy='merge'`, and a MERGE never
DELETES — so the Snowflake table is an ACCUMULATING SUPERSET, retaining rows for lineup/probable
snapshots a later rebuild superseded (a scratched starter; a batter dropped from a confirmed
order). #662 measured that surplus at +3 / +32 rows. A whole-table row-count delta therefore
says NOTHING about whether the op's INPUT moved — the op does not read the table, it reads
    (a) the season-FIRST-appearance (mu_0, sigma_0) per player, and
    (b) the (pitcher, game_pk) -> starter|bullpen role map for one date,
and a surplus row only matters if it lands on one of those. This script compares (a) and (b)
directly, on both backends, using the SAME query bodies the op issues.

WHAT IT REPORTS, per player_type and per date:
  • only_in_sf   — a player the Snowflake read seeds that the S3 read does not. This is the one
                   with teeth: post-repoint the op finds no prior and SKIPS them (n_skipped++),
                   so their chain never cold-starts this season.
  • only_in_s3   — the reverse (Snowflake's merge has not caught up with the current rebuild).
  • value_diff   — present in both, but (mu_0, sigma_0) differ beyond --tol: the season-first row
                   itself moved (a ghost sorted earlier, or the rebuild recomputed history).
  • role_diff    — a (pitcher, game_pk) classified starter on one backend and bullpen on the other.
Exit code 1 if ANY of those is non-empty; 0 only on an exact match of the consumed structures.

🔌 WAREHOUSE — READ THIS BEFORE RUNNING. The Snowflake side connects on **MONITOR_WH** by default
(`get_monitoring_connection`), NOT COMPUTE_WH. Running this on COMPUTE_WH during an E11.24 soak
would RESUME the very warehouse whose wake census is being measured and corrupt that day's
reading (the same observer-effect that forced the 2026-07-29 census to discard its own UTC day).
`--warehouse compute` exists as a deliberate opt-out; do not use it inside a soak window.

RUN (LAPTOP — read-only, safe; needs SNOWFLAKE_PRIVATE_KEY_PATH + AWS creds):
  AWS_DEFAULT_REGION=us-east-2 LAKEHOUSE_DELTA_W1=cutover \
    uv run python scripts/parity_check_eb_reader_repoint.py --season 2026 --dates 2026-08-06,2026-08-07

⚠️ LAKEHOUSE_DELTA_W1=cutover is REQUIRED — a hand-run does not inherit the daily op's env, and
without it the shared registrar falls back to the parquet glob that E11.20 phase 1.5 deleted.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from betting_ml.scripts.sequential_bayes import update_player_posteriors as upp  # noqa: E402

_PLAYER_TYPES = ("batter", "starter", "bullpen")


def _sf_conn(warehouse: str):
    from betting_ml.utils.data_loader import (
        get_monitoring_connection,
        get_snowflake_connection,
    )
    if warehouse == "compute":
        print("  ⚠️  connecting on COMPUTE_WH — this RESUMES the warehouse under cost measurement.")
        return get_snowflake_connection()
    return get_monitoring_connection()


def _compare_priors(sf: dict, s3: dict, tol: float) -> dict[str, list]:
    """Diff the {player_id: (mu_0, sigma_0)} maps the op seeds cold starts from."""
    only_sf = sorted(set(sf) - set(s3))
    only_s3 = sorted(set(s3) - set(sf))
    value_diff = []
    for pid in sorted(set(sf) & set(s3)):
        (mu_a, sg_a), (mu_b, sg_b) = sf[pid], s3[pid]
        if abs(mu_a - mu_b) > tol or abs(sg_a - sg_b) > tol:
            value_diff.append((pid, (mu_a, sg_a), (mu_b, sg_b)))
    return {"only_in_sf": only_sf, "only_in_s3": only_s3, "value_diff": value_diff}


def _compare_roles(sf: dict, s3: dict) -> dict[str, list]:
    """Diff the {(pitcher_id, game_pk): 'starter'|'bullpen'} map for one date."""
    only_sf = sorted(set(sf) - set(s3))
    only_s3 = sorted(set(s3) - set(sf))
    role_diff = [(k, sf[k], s3[k]) for k in sorted(set(sf) & set(s3)) if sf[k] != s3[k]]
    return {"only_in_sf": only_sf, "only_in_s3": only_s3, "role_diff": role_diff}


def _report(label: str, diff: dict, sample: int) -> bool:
    """Print one section; return True if it is CLEAN."""
    clean = all(not v for v in diff.values())
    print(f"\n  {label}: {'✅ MATCH' if clean else '❌ DIFF'}")
    for key, rows in diff.items():
        if rows:
            print(f"      {key}: {len(rows)}")
            for r in rows[:sample]:
                print(f"        {r}")
            if len(rows) > sample:
                print(f"        … {len(rows) - sample} more")
    return clean


def main() -> int:
    ap = argparse.ArgumentParser(description="E11.24 EB reader repoint parity gate")
    ap.add_argument("--season", type=int, required=True, help="Season for the cold-start prior read")
    ap.add_argument("--dates", default="",
                    help="Comma-separated ISO dates for the pitcher-role read (recommend 2 recent "
                         "COMPLETED slates — the op only ever reads roles for completed dates)")
    ap.add_argument("--tol", type=float, default=1e-9,
                    help="Absolute tolerance on mu_0 / sigma_0 (default 1e-9 — these are stored "
                         "FLOAT on both sides, so a real match is exact, not approximate)")
    ap.add_argument("--sample", type=int, default=5, help="Rows to print per non-empty diff bucket")
    ap.add_argument("--warehouse", choices=("monitor", "compute"), default="monitor",
                    help="Snowflake warehouse (default monitor = MONITOR_WH; see the module "
                         "docstring before choosing compute)")
    args = ap.parse_args()

    dates = [date.fromisoformat(d.strip()) for d in args.dates.split(",") if d.strip()]

    print("E11.24 target-6 successor — EB reader repoint parity")
    print(f"  season={args.season}  dates={[d.isoformat() for d in dates] or '(none)'}  "
          f"tol={args.tol}  warehouse={args.warehouse}")

    duck = upp._maybe_duck(True)
    conn = _sf_conn(args.warehouse)
    all_clean = True
    try:
        print("\n── Cold-start EB priors (season-first appearance per player) ──")
        sf_priors = upp._load_eb_priors(conn, args.season)
        s3_priors = upp._load_eb_priors(None, args.season, duck=duck)
        for ptype in _PLAYER_TYPES:
            sf_p, s3_p = sf_priors.get(ptype, {}), s3_priors.get(ptype, {})
            label = f"{ptype:<7} (SF {len(sf_p):,} vs S3 {len(s3_p):,} players)"
            all_clean &= _report(label, _compare_priors(sf_p, s3_p, args.tol), args.sample)

        if dates:
            print("\n── Pitcher role map (starter|bullpen per pitcher-game) ──")
        for d in dates:
            sf_r = upp._load_pitcher_roles(conn, d)
            s3_r = upp._load_pitcher_roles(None, d, duck=duck)
            # NF1.7 (a): an anchor that measured NOTHING must never read as a pass. Two empty
            # role maps compare equal — which is exactly what a wrong-date predicate (E9.52) or
            # an un-built parquet looks like. Refuse the date instead of scoring it clean.
            if not sf_r and not s3_r:
                print(f"\n  {d}: ⚠️  UNEVALUABLE — BOTH backends returned an EMPTY role map. "
                      f"Not a pass. Pick a date with completed games.")
                all_clean = False
                continue
            label = f"{d} (SF {len(sf_r)} vs S3 {len(s3_r)} pitcher-games)"
            all_clean &= _report(label, _compare_roles(sf_r, s3_r), args.sample)
        if not dates:
            print("\n  ⚠️  no --dates given: the ROLE half of the repoint was NOT checked.")
            all_clean = False
    finally:
        conn.close()

    print("\n" + ("=" * 78))
    if all_clean:
        print("✅ PARITY CLEAN — the repoint does not change what update_player_posteriors consumes.")
        return 0
    print("❌ PARITY DIFF — read the buckets above BEFORE deploying the repoint.\n"
          "   `only_in_sf` on a prior is the consequential one: that player loses their cold-start\n"
          "   seed and is skipped. Confirm each such row is a superseded snapshot (a ghost the\n"
          "   current rebuild no longer produces), not a row the S3 build is missing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
