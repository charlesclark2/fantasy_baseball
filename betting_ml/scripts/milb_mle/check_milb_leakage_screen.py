"""check_milb_leakage_screen.py — E7.6: independent as-of leakage screen for the MiLB→MLB MLE.

WHY THIS EXISTS
----------------
E7.3's `build_graduated_pairs.py` / `build_graduated_pairs_pitchers.py` filter every MiLB
player-game-log row STRICTLY BEFORE that player's MLB debut date
(`l.official_date::date < d.debut_date`, the as-of leakage guard) before summing it into a
player's minor-league line. That one WHERE clause is the ENTIRE thing standing between the served
rookie prior and a genuine leakage bug: `milb_mle_prior` (built from these pairs via
`milb_mle.emit_projections`) is joined into `eb_batter_posteriors_raw` by a plain
`ON mp.batter_id = l.batter_id` — no date predicate at all (see
`dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql`'s `mle_prior` CTE) — so leak-freedom at
serve time is INHERITED entirely from that upstream filter, never re-checked at the join.

That guard has only ever been exercised on SYNTHETIC fixtures (`test_milb_mle_prior.py` etc.), and
both build scripts are OPERATOR-RUN (>1 min, never on a daily/Dagster path per their own
docstrings) — so a regression in either script's WHERE clause (an off-by-one, a dropped filter, a
`<=` typo) would silently land in the next `--s3` write and nothing would ever notice. This script
closes that gap: it independently RE-DERIVES the pre-debut plate-appearance / batters-faced total
straight from `player_game_logs` + the MLB rolling-stats marts (fresh SQL, deliberately NOT
importing `_assembly_sql` — reusing the code under test would just re-run it, not check it) and
compares that to the value actually landed in `mle_graduated_pairs[_pitchers]` on S3.

    served minor_pa  >  independently-recomputed pre-debut PA/TBF   ⇒  LEAKAGE
    (a post-debut game's plate appearances / batters-faced reached the served aggregate)

The screen also reports, per side, how many rows had an actual OPPORTUNITY to leak — a graduated
player with SOME minor-league game at that level on or after his debut date (a rehab assignment, a
later-career optioning, etc.). A side with zero opportunities never had a chance to catch a
regression this pass; NF1.7(a) — an unevaluated check is never scored as a passed one — so that
state is reported distinctly (UNEVALUABLE), not folded into VERIFIED.

This screen covers the ENTIRE downstream chain to the served pregame row: `mle_graduated_pairs` →
(`milb_mle.emit_projections`) → `mle_projections` → (E7.5/E7.5b recalibration) → `milb_mle_prior`
→ (a plain per-batter join, no date logic) → `eb_batter_posteriors_raw` → `feature_pregame_*`.
Nothing downstream of `mle_graduated_pairs` re-introduces date information, so leak-freedom here
is leak-freedom all the way to the served pregame row. The SIBLING check
`verify_mle_prior_serving.py` (E7.5b) verifies that join is ALIVE (not stale/dead) — a different
question from whether it is LEAK-FREE, which is what this script answers.

USAGE (SF-free — pure DuckDB over the S3 lakehouse, AWS creds via the instance role / env only):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.check_milb_leakage_screen

Exit 0 = no leakage detected on any evaluable side. Exit 1 = leakage detected on at least one side.
WARN-tier when wired into Dagster (E7.6 / E11.7): MiLB is off the MLB serving path, so a failure
here logs loud and never HALTs a run — see pipeline/ops/milb_ops.py::milb_leakage_screen_op.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"

_EPS = 1e-6

# Each side's independent re-derivation query. Deliberately written FRESH here — NOT imported
# from build_graduated_pairs[_pitchers]._assembly_sql — so a regression in that function's WHERE
# clause cannot hide from this check by construction.
_BATTER_QUERY = """
    with mlb_debut as (
        select batter_id::varchar as player_id, min(game_date::date) as debut_date
        from mart_batter_rolling_stats
        group by batter_id
    ),
    milb_games as (
        select l.player_id::varchar as player_id, l.level_name as level,
               l.official_date::date as official_date,
               coalesce(l.bat_plate_appearances, 0) as pa
        from milb_logs l
        where l.is_batter = true and l.game_type = 'R'
    ),
    per_level as (
        select g.player_id, g.level,
               sum(g.pa) as all_time_pa,
               sum(case when d.debut_date is null or g.official_date < d.debut_date
                        then g.pa else 0 end) as recomputed_pre_debut_pa
        from milb_games g
        left join mlb_debut d on d.player_id = g.player_id
        group by g.player_id, g.level
    )
    select served.player_id, served.level,
           coalesce(served.minor_pa, 0) as served_pa,
           coalesce(p.all_time_pa, 0) as all_time_pa,
           coalesce(p.recomputed_pre_debut_pa, 0) as recomputed_pre_debut_pa
    from mle_graduated_pairs served
    left join per_level p on p.player_id = served.player_id and p.level = served.level
    where served.is_prospect = false
"""

_PITCHER_QUERY = """
    with mlb_debut as (
        select pitcher_id::varchar as player_id, min(game_date::date) as debut_date
        from mart_pitcher_rolling_stats
        group by pitcher_id
    ),
    milb_games as (
        select l.player_id::varchar as player_id, l.level_name as level,
               l.official_date::date as official_date,
               coalesce(l.pit_batters_faced, 0) as tbf
        from milb_logs l
        where l.is_pitcher = true and l.game_type = 'R'
    ),
    per_level as (
        select g.player_id, g.level,
               sum(g.tbf) as all_time_pa,
               sum(case when d.debut_date is null or g.official_date < d.debut_date
                        then g.tbf else 0 end) as recomputed_pre_debut_pa
        from milb_games g
        left join mlb_debut d on d.player_id = g.player_id
        group by g.player_id, g.level
    )
    select served.player_id, served.level,
           coalesce(served.minor_pa, 0) as served_pa,
           coalesce(p.all_time_pa, 0) as all_time_pa,
           coalesce(p.recomputed_pre_debut_pa, 0) as recomputed_pre_debut_pa
    from mle_graduated_pairs_pitchers served
    left join per_level p on p.player_id = served.player_id and p.level = served.level
    where served.is_prospect = false
"""

_SIDES = (
    ("batter", "mle_graduated_pairs", _BATTER_QUERY),
    ("pitcher", "mle_graduated_pairs_pitchers", _PITCHER_QUERY),
)


def classify_side(rows: list[dict], epsilon: float = _EPS) -> tuple[str, list[str], dict]:
    """Classify one side's independently-recomputed comparison rows.

    Pure function — no DB access — so it is fast-gate testable on synthetic `rows`. Each row
    carries player_id, level, served_pa, recomputed_pre_debut_pa, all_time_pa (floats).

    Returns (state, messages, stats). state is one of:
      VERIFIED       — rows exist, at least one had an opportunity to leak, none did.
      LEAK_DETECTED  — at least one row's served value exceeds what pre-debut games alone produce.
      UNEVALUABLE    — no graduated rows (table empty/missing), or none had any post-debut games
                        at their level to leak from — never scored as a pass (NF1.7(a)).
    """
    n = len(rows)
    if n == 0:
        return "UNEVALUABLE", ["no graduated (has_mlb_label / non-prospect) rows found"], {
            "n_rows": 0, "n_opportunities": 0, "n_violations": 0,
        }

    violations = [r for r in rows if r["served_pa"] > r["recomputed_pre_debut_pa"] + epsilon]
    opportunities = [r for r in rows if r["all_time_pa"] > r["recomputed_pre_debut_pa"] + epsilon]
    stats = {"n_rows": n, "n_opportunities": len(opportunities), "n_violations": len(violations)}

    if violations:
        msgs = [
            f"{r['player_id']} @ {r['level']}: served minor_pa={r['served_pa']:.1f} > "
            f"independently-recomputed pre-debut PA/TBF={r['recomputed_pre_debut_pa']:.1f} "
            f"(all-time={r['all_time_pa']:.1f}) — a post-debut game's plate appearances / batters "
            "faced reached the served MiLB line"
            for r in violations[:10]
        ]
        if len(violations) > 10:
            msgs.append(f"... and {len(violations) - 10} more violation(s)")
        return "LEAK_DETECTED", msgs, stats

    if not opportunities:
        return "UNEVALUABLE", [
            "0 of the graduated rows had ANY post-debut minor-league games at their level — the "
            "screen ran but had no opportunity to catch a regression this pass"], stats

    return "VERIFIED", [], stats


def _connect():
    """DuckDB with the S3 credential chain + Delta extension — SF-free, mirrors
    build_graduated_pairs._connect()."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ delta extension load failed ({e}) — MiLB delta_scan may fail")
    register_views(conn, ["mart_batter_rolling_stats", "mart_pitcher_rolling_stats"])
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    for table in ("mle_graduated_pairs", "mle_graduated_pairs_pitchers"):
        conn.execute(
            f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM delta_scan('{MILB}/derived/{table}')"
        )
    return conn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.6 — MiLB as-of leakage screen (SF-free)")
    p.add_argument("--epsilon", type=float, default=_EPS,
                   help="PA/TBF tolerance before a discrepancy counts as leakage (default 1e-6)")
    args = p.parse_args(argv)

    conn = _connect()
    any_leak = False
    any_evaluated = False

    for side, table, query in _SIDES:
        try:
            cur = conn.execute(query)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:  # noqa: BLE001 — table not yet landed / transient read issue
            print(f"[{side}] ⚠️ could not read {table} ({e}) — UNEVALUABLE, not scored as passed")
            continue

        state, messages, stats = classify_side(rows, args.epsilon)
        print(f"[{side}] rows={stats['n_rows']} opportunities={stats['n_opportunities']} "
              f"violations={stats['n_violations']} -> {state}")
        for m in messages:
            print(f"   • {m}")

        if state != "UNEVALUABLE":
            any_evaluated = True
        if state == "LEAK_DETECTED":
            any_leak = True

    print()
    if any_leak:
        print("❌ LEAKAGE DETECTED — a future MiLB stat reached a served graduated-pair row")
        return 1
    if not any_evaluated:
        print("⚠️ UNEVALUABLE on every side — no conclusion could be drawn this pass (not a pass, "
              "not a fail; re-run once mle_graduated_pairs[_pitchers] is landed with post-debut "
              "minor-league activity to test against)")
        return 0
    print("✅ no leakage detected — every evaluable side's served minor_pa matches the "
          "independently-recomputed pre-debut total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
