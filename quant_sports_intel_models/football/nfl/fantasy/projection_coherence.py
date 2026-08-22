"""projection_coherence.py — NF-INJ1: is the SERVED (expected-games, stat-line) pair physically possible?

THE DEFECT THIS EXISTS TO CATCH (measured on the live 2026 board, not hypothetical). The served
`projections.json` carried **Easton Stick at 1.9 expected games with 153.4 pass attempts and 1045.6
pass yards** — 82.7 attempts and 563.6 yards PER GAME, against an all-time realized maximum of 45.4
and 371.2. Eight more veteran QBs carried the same shape. `fpPpr` is SCORED from the stat line, so
the points agree with the line and disagree with `g`: nothing in the payload is self-inconsistent
in a way a schema or a scorer could see, and every test in the repo was green.

⭐ WHY A PER-GAME RATE IS THE RIGHT INSTRUMENT. `g` and the stat line are each defensible alone —
the argument is about which one is wrong (see `ablation_results/nf_inj1_diagnosis.md` §4). Their
RATIO is not: no reading of the model makes 82.7 pass attempts per game possible. So the rate is the
one quantity that indicts the PAIR without having to first settle which half moved, which is exactly
what a guard shipped ahead of a §0.5 model change needs to be able to do.

HOW THE INCOHERENCE IS PRODUCED (NF-INJ1 §3). `season_projection.project_veterans` builds the line as
`per_game_rate × proj_games` and every availability step rescales the line by the games ratio, so
MVP-1 is coherent BY CONSTRUCTION (measured: 1 violating row, and it is a rookie from a different
path). NF1.5 then re-orders each position by the learned score and hands every player a DIFFERENT
player's point level, rescaling the line to match via `nf1_model.apply_learned_level` — whose
`_RAW_SCALE_COLS` contains the twelve stat columns and **not `proj_games`**. A low-availability
player promoted within the multiset therefore has his line multiplied by up to the 3.5 clamp while
his games are untouched.

────────────────────────────────────────────────────────────────────────────────────────────────
THE ENVELOPE IS DERIVED FROM REALIZED HISTORY, NOT CHOSEN
────────────────────────────────────────────────────────────────────────────────────────────────
`REALIZED_MAX_PER_GAME` is the MAXIMUM per-game rate any real NFL player-season posted in
2006–2025, per position, computed from `main_nfl_marts.fct_player_week`:

    with s as (select season, player_id, max(position) pos,
                      count_if(played_flag and not is_bye) g,
                      sum(pass_attempts) pa, sum(passing_yards) py, sum(rushing_carries) ra,
                      sum(rushing_yards) ry, sum(receiving_targets) tg, sum(receptions) rc,
                      sum(receiving_yards) rey
               from main_nfl_marts.fct_player_week
               where week > 0 and player_id is not null and season between 2006 and 2025
               group by 1, 2)
    select pos, max(pa/g), max(py/g), max(ra/g), max(ry/g), max(tg/g), max(rc/g), max(rey/g)
    from s where g >= 1 and pos in ('QB','RB','WR','TE') group by 1

over 11,190 player-seasons (QB 1,539 / RB 2,815 / TE 2,464 / WR 4,372). ⭐ IT IS A **MAX**, ON
PURPOSE: the bar is "no human has ever done this", so a firing is a statement about physical
possibility rather than about likelihood, and the guard cannot produce a false alarm the way a
percentile or a hand-picked "plausible" ceiling could. That also keeps it E2.1-r-clean — the numbers
are a property of twenty seasons of realized football, fixed before any board row was scored, and
⛔ they must never be re-derived from, or widened to accommodate, a board that failed them.

Stability check (part of the derivation, not a post-hoc defence): restricting the population to
seasons with ≥4 games played moves QB pass attempts 45.44 → 45.44, RB carries 27.38 → 27.38 and WR
receiving yards 122.75 → 122.75 — i.e. the envelope is not an artifact of one-game cameos.

────────────────────────────────────────────────────────────────────────────────────────────────
SCOPE
────────────────────────────────────────────────────────────────────────────────────────────────
This module MEASURES. It changes no projection and decides no model question — the coherence fix
itself is a level-adjacent model change and is pre-registered for §0.5 (`nf_inj1_preregistration.md`).
Pure: plain dicts in, plain dicts out, no pandas, no IO — so the guard can open the STAGED BYTES
(the NF-K1 lesson: a guard on the code path answers a different question from one on the artifact).
"""

from __future__ import annotations

# ── the derived envelope: {position: {published field: max realized per-game rate}} ──────────────
#: Keyed on the PUBLISHED JSON field names (`passAtt`, not `proj_pass_att`) because the guard reads
#: the staged artifact. `PARQUET_FIELD` maps them back for the build-time diagnostic.
REALIZED_MAX_PER_GAME: dict[str, dict[str, float]] = {
    "QB": {"passAtt": 45.44, "passYds": 371.20, "rushAtt": 11.73, "rushYds": 88.00},
    "RB": {"rushAtt": 27.38, "rushYds": 131.06, "tgt": 9.00, "rec": 7.25, "recYds": 67.00},
    "WR": {"tgt": 12.75, "rec": 8.79, "recYds": 122.75, "rushAtt": 8.88},
    "TE": {"tgt": 9.94, "rec": 7.41, "recYds": 94.40},
}

#: published field → the `season_projection` frame column, for the build-time diagnostic.
PARQUET_FIELD: dict[str, str] = {
    "passAtt": "proj_pass_att", "passYds": "proj_pass_yds",
    "rushAtt": "proj_rush_att", "rushYds": "proj_rush_yds",
    "tgt": "proj_targets", "rec": "proj_rec", "recYds": "proj_rec_yds",
}

#: The population the envelope was derived over — carried so a reader can check the claim without
#: re-running the query, and so a future re-derivation is a reviewable diff.
ENVELOPE_PROVENANCE = {
    "source": "main_nfl_marts.fct_player_week",
    "seasons": "2006-2025",
    "statistic": "max realized SEASON per-game rate among players with >=1 game played",
    "n_player_seasons": {"QB": 1539, "RB": 2815, "TE": 2464, "WR": 4372},
}


def _num(v) -> float | None:
    """Coerce a published value to float; None for anything not a finite number (never 0.0 — a
    missing stat and a genuine zero are different, and only the latter can be scored)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def row_violations(row: dict) -> list[dict]:
    """Every envelope breach on ONE published row. Empty for a coherent row, an UNEVALUABLE row, or
    a position the envelope does not cover (K/DST have no per-game counting line here).

    ⛔ An unevaluable row (no position, no/zero `g`) returns [] but is COUNTED separately by
    `coherence_summary` — NF1.7 (a): a row the check could not read has not passed it."""
    pos = str(row.get("pos") or "").upper()
    env = REALIZED_MAX_PER_GAME.get(pos)
    if not env:
        return []
    g = _num(row.get("g"))
    if g is None or g <= 0:
        return []
    out: list[dict] = []
    for field, ceiling in env.items():
        v = _num(row.get(field))
        if v is None:
            continue
        rate = v / g
        if rate > ceiling:
            out.append({
                "id": row.get("id"), "name": row.get("name"), "pos": pos, "stat": field,
                "season_total": round(v, 1), "expected_games": round(g, 2),
                "implied_per_game": round(rate, 2), "max_ever_per_game": ceiling,
                "times_over": round(rate / ceiling, 2),
            })
    return out


def _carries_stat_line(row: dict) -> bool:
    """Does this row carry ANY of the envelope's stat fields? The league-board blobs publish only
    `g` + `pts` (no counting line), so on them the whole check is structurally INERT — and an inert
    check reporting "0 violations" is precisely the vacuous pass NF1.7 (a) / NF-D20 forbid. The
    summary reports `applicable=False` for such a blob instead of a clean bill of health."""
    env = REALIZED_MAX_PER_GAME.get(str(row.get("pos") or "").upper()) or {}
    return any(_num(row.get(f)) is not None for f in env)


def _is_evaluable(row: dict) -> bool:
    pos = str(row.get("pos") or "").upper()
    if pos not in REALIZED_MAX_PER_GAME:
        return False          # out of scope, not unevaluable
    g = _num(row.get("g"))
    return g is not None and g > 0


def coherence_summary(rows: list) -> dict:
    """Measure one published board/projections row list.

    Returns `applicable` / `n_rows` / `n_in_scope` / `n_with_stat_line` / `n_unevaluable` /
    `n_violating_players` / `by_position` / `violations`.

    ⭐ TWO WAYS THIS CHECK CAN REPORT ZERO WITHOUT HAVING CHECKED ANYTHING, both surfaced rather than
    hidden: `applicable=False` when no row carries a stat line at all (the league-board blobs — the
    check cannot fire there BY CONSTRUCTION), and `n_unevaluable` when in-scope rows carry no usable
    `g`. A caller that reads only `n_violating_players` would score both as a clean board."""
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    in_scope = [r for r in rows if str(r.get("pos") or "").upper() in REALIZED_MAX_PER_GAME]
    unevaluable = [r for r in in_scope if not _is_evaluable(r)]
    with_line = [r for r in in_scope if _carries_stat_line(r)]
    viol: list[dict] = []
    for r in rows:
        viol.extend(row_violations(r))
    players = {(v.get("id"), v.get("name")) for v in viol}
    by_pos: dict[str, int] = {}
    for pos in sorted({v["pos"] for v in viol}):
        by_pos[pos] = len({(v.get("id"), v.get("name")) for v in viol if v["pos"] == pos})
    return {
        "applicable": bool(with_line),
        "n_rows": len(rows),
        "n_in_scope": len(in_scope),
        "n_with_stat_line": len(with_line),
        "n_unevaluable": len(unevaluable),
        "n_violating_players": len(players),
        "n_violations": len(viol),
        "by_position": by_pos,
        "violations": sorted(viol, key=lambda v: -v["times_over"]),
    }


def format_summary(summary: dict, label: str = "", limit: int = 12) -> str:
    """A human-readable banner for a run log. Names the players — an operator cannot act on a count."""
    if not summary.get("applicable"):
        return (f"NF-INJ1 coherence [{label}]: NOT APPLICABLE — none of the "
                f"{summary['n_in_scope']} in-scope rows carries a counting stat line, so the "
                "envelope cannot fire here. ⛔ This is NOT a clean board (NF1.7 (a)).")
    head = (f"NF-INJ1 coherence [{label}]: {summary['n_violating_players']} player(s) exceed the "
            f"all-time realized per-game envelope "
            f"({summary['n_violations']} stat breaches over {summary['n_in_scope']} in-scope rows"
            + (f"; {summary['n_unevaluable']} UNEVALUABLE" if summary["n_unevaluable"] else "")
            + ")")
    if summary["by_position"]:
        head += " — by position: " + ", ".join(f"{p}={n}" for p, n in summary["by_position"].items())
    lines = [head]
    for v in summary["violations"][:limit]:
        lines.append(f"    {v['pos']:<3} {str(v['name'])[:26]:<26} {v['stat']:>8} "
                     f"{v['season_total']:>7} over {v['expected_games']:>5}g "
                     f"= {v['implied_per_game']:>6}/g  (max ever {v['max_ever_per_game']}, "
                     f"{v['times_over']}x)")
    extra = len(summary["violations"]) - limit
    if extra > 0:
        lines.append(f"    … and {extra} more")
    return "\n".join(lines)


# ── injury-input freshness (facet 1) ─────────────────────────────────────────────────────────────
#: The board's injury input may lag the FEED by at most this many hours before it is reported STALE.
#: DERIVED, not chosen: it is 2x the feed's own declared INC-41 SLA
#: (`betting_ml.monitoring.sports_delta_freshness` → `nfl_sleeper_injuries.max_lag_hours` = 36.0),
#: which is the smallest bar that cannot fire on a board built immediately after a feed that is
#: itself within SLA. Anything larger would let a whole extra daily capture go missing unremarked.
INJURY_INPUT_MAX_LAG_HOURS = 72.0

#: The `input_vintage` key the projection build stamps (NF-FRESH2 P2).
INJURY_VINTAGE_KEY = "sleeper_status_as_of"


def assess_injury_input_freshness(input_vintage: dict | None, now_iso: str,
                                  max_lag_hours: float = INJURY_INPUT_MAX_LAG_HOURS) -> dict:
    """Is the injury status the board was BUILT on still current at publish time?

    THE GAP THIS CLOSES (NF-INJ1 §2, measured). NF-FRESH2 P2 already stamps
    `input_vintage.sleeper_status_as_of` into the served payload, so the staleness was VISIBLE —
    the 2026 board shipped stamped `2026-07-26` beside a `depth_chart_as_of` of `2026-08-14`. What
    was missing is anything that ACTS on it: the upstream S3 Delta was healthy the whole time (15.4h
    lag against its 36h INC-41 SLA), and the board still went out on a 20-day-old injury snapshot,
    projecting 18 currently-flagged players at their healthy rate. Visible is not the same as gated.

    Verdicts: `OK` · `STALE` (lag over the bar) · `UNKNOWN` (no stamp / unparseable — ⛔ WARN, never
    scored healthy: NF1.7 (a))."""
    from datetime import datetime

    def _parse(s):
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None

    stamp = (input_vintage or {}).get(INJURY_VINTAGE_KEY)
    at, now = _parse(stamp), _parse(now_iso)
    if at is None or now is None:
        return {"verdict": "UNKNOWN", "lag_hours": None, "as_of": stamp,
                "max_lag_hours": max_lag_hours,
                "detail": (f"no readable `{INJURY_VINTAGE_KEY}` stamp on the projection build — the "
                           "board's injury vintage cannot be verified, which is a WARN, not a pass")}
    if at.tzinfo is None or now.tzinfo is None:
        at, now = at.replace(tzinfo=None), now.replace(tzinfo=None)
    lag = (now - at).total_seconds() / 3600.0
    verdict = "STALE" if lag > max_lag_hours else "OK"
    return {"verdict": verdict, "lag_hours": round(lag, 1), "as_of": stamp,
            "max_lag_hours": max_lag_hours,
            "detail": (f"the board's injury status is {lag:.1f}h old (bar {max_lag_hours:.0f}h). "
                       "Refresh it with `dbt run --select stg_nfl_sleeper_injuries` and REBUILD the "
                       "projection — the export cannot repair a vintage the build baked in."
                       if verdict == "STALE" else
                       f"injury status {lag:.1f}h old, within the {max_lag_hours:.0f}h bar")}
