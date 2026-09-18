"""run_nf_wk_acc1_idp_scope_verify.py — does Sleeper pay an OFFENSIVE player an IDP term?

═══════════════════════════════════════════════════════════════════════════════════════════════════
⛔ THIS IS A PRE-REGISTERED GATE, AND ITS RULE WAS DECLARED BEFORE IT WAS RUN
═══════════════════════════════════════════════════════════════════════════════════════════════════

PM ruling ② (2026-09-18), verbatim, because the whole value of this file is that the bar was set
before the answer was known:

    "Scope the IDP defensive terms (def_fumble_rec, forced-fumble, sack — the family, not just the
    one that fired) to defensive positions — but your evidence for Sleeper's scoping is n=1, and we
    do not extrapolate a platform's semantics from one row. Pre-declare this before touching the
    map: run the harness over all 19 measured 2025 rows (9 recoveries, 9 forced fumbles, 1 sack at
    offensive positions) in leagues where the relevant weights are nonzero; the fix ships only if
    every row reads zero-delta after scoping. If even one row shows Sleeper paying an offensive
    player under an IDP term, revert to option C on the spot and record the split — that outcome
    means Sleeper's rule is something other than position-scoping and needs its own study, not a
    guess."

⭐ WHAT "ZERO-DELTA AFTER SCOPING" REDUCES TO, and why this is the sharpest available instrument.
Scoping makes OUR contribution for such a row exactly 0. So the row reads zero-delta iff SLEEPER's
contribution is also 0 — and Sleeper's contribution is `weight × its own credited stat`. With the
weight nonzero (the operator's league pays `def_fumble_rec` 1.0, `def_forced_fumble` 1.0,
`def_sacks` 1.0), that is zero iff Sleeper credits the player with NONE of the stat. So the test is:
does Sleeper's own per-player stat line credit an offensively-listed player with `fum_rec` / `ff` /
`sack`? Sleeper's raw keys are read off our own importer's map, not guessed (`sleeper._PER_STAT`).

⛔ THE SCOPING POSITION IS THE LAKE'S, so the population must be selected on the LAKE's position.
Our scorer scopes on the position `realized_board` carries, which comes from `stats_player_week`. A
population selected on SLEEPER's position would be testing a rule we do not implement. Both
positions are reported per row, because a row the two sides disagree about is exactly the case this
gate must not silently pass (it is also the shape part 3's two-way-player join was about).

⛔ AN UNRESOLVED ROW IS `UNVERIFIED`, NEVER A PASS. Sleeper's `gsis_id` is null for most recent
players (3,125 of 9,421 active), so these rows resolve by name + position + team against Sleeper's
player dump — auditable at n≈19 and refused when ambiguous. A row we could not look up has not been
checked, and answering "we could not tell" with "it passed" is the NF1.7(a) vacuous pass. The verdict
is PASS only when EVERY row resolved AND every resolved row shows Sleeper crediting nothing.

RUN (LAPTOP — reads the S3 NFL lake + Sleeper's public API, writes nothing):

    env -u TOKEN AWS_DEFAULT_REGION=us-east-2 uv run python -m \\
      quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_acc1_idp_scope_verify --season 2025

⚠️ `env -u TOKEN` is not decoration: a bare `TOKEN` in the shell is swallowed by delta-rs as an S3
session token and every lake read fails `400 InvalidToken` (NF-ROS1b).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

log = logging.getLogger("nfl.fantasy.acc1_idp_scope")

_SLEEPER_WEEK_STATS = "https://api.sleeper.app/v1/stats/nfl/regular/{season}/{week}"
_SLEEPER_PLAYERS = "https://api.sleeper.app/v1/players/nfl"

#: ⚠️⚠️ THE FIRST RUN OF THIS GATE WAS VACUOUS, AND THE HEADER ABOVE PREDICTED THE EXACT MECHANISM
#: WITHOUT PREVENTING IT. It is recorded here rather than quietly corrected, because the correction
#: is what produced the story's answer.
#:
#: The first cut took Sleeper's raw keys from our own importer's `_PER_STAT` map — `fum_rec`, `ff`,
#: `sack` — reasoning that the importer cannot be wrong about Sleeper's vocabulary. It is not wrong;
#: it is about a DIFFERENT VOCABULARY. Sleeper has TWO stat namespaces, and the importer maps the
#: one that appears in LEAGUE SETTINGS:
#:
#:   * TEAM-DEFENCE stats — `sack`, `ff`, `fum_rec`, `blk_kick`, `def_st_ff`, `def_st_fum_rec`.
#:     Measured on 2025 wk1: credited ONLY to `DEF` and `TEAM_*` entries, never to any individual
#:     player of any position. These are the keys a league's `def_*` weights reference.
#:   * INDIVIDUAL stats — `idp_sack`, `idp_ff`, `idp_fum_rec`, `idp_blk_kick`, and the special-teams
#:     `st_ff` / `st_fum_rec`. These are what an individual player is credited with.
#:
#: So EVERY individual player scores 0 on the first cut's keys BY CONSTRUCTION, offensive or
#: defensive — the gate could not have failed, and it returned PASS on nothing (the NF1.7(a) /
#: MH2.6 vacuity-floor class, landing on a gate written by someone who had just written a comment
#: warning about it).
#:
#: ⭐ THE RULE IS UNCHANGED — only the instrument is. The bar the PM pre-declared ("every row
#: zero-delta, else option C") is untouched; what moved is which column the gate reads to evaluate
#: it. Both runs are reported, because "the first answer was PASS" is only honest beside why it was
#: worthless.
#:
#: our scorer key → (the lake column that feeds it, the TEAM-DEFENCE key the league's weight
#: references, the INDIVIDUAL keys Sleeper credits the event under).
IDP_FAMILY: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "def_fumble_rec": ("fumble_recovery_opp", "fum_rec", ("idp_fum_rec", "st_fum_rec")),
    "def_forced_fumble": ("def_fumbles_forced", "ff", ("idp_ff", "st_ff")),
    "def_sacks": ("def_sacks", "sack", ("idp_sack",)),
}

#: The keys the first, vacuous cut read — kept so the two runs can be reported side by side and so a
#: future reader can reproduce the vacuity rather than take it on trust.
SUPERSEDED_TEAM_GRAIN_KEYS: dict[str, str] = {k: v[1] for k, v in IDP_FAMILY.items()}

#: The positions the scoping would treat as OFFENSIVE (i.e. the rows it would zero). Mirrors the
#: scorer's own ranked set; a position outside it is one the scoping does not touch.
OFFENSIVE_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "K")


def _fetch(url: str, cache: Path | None) -> dict:
    if cache and cache.is_file():
        return json.loads(cache.read_text())
    with urllib.request.urlopen(url, timeout=180) as resp:  # noqa: S310 — a public vendor endpoint
        blob = json.loads(resp.read())
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(blob))
    return blob


def _fold(name: str) -> str:
    """The name form both sides are compared under — the scorer's own normalizer, so this gate and
    the join it is about cannot disagree about who two rows are."""
    from app.backend.services.league_scoring import normalize_player_name
    return normalize_player_name(name)


def population(season: int, *, q, delta) -> list[dict]:
    """Every OFFENSIVELY-listed player-week in `season` carrying a nonzero IDP counter.

    This IS the 19 rows the ruling names — re-derived rather than hard-coded, so the gate describes
    the data in hand rather than a session's note of it (the NF-K1 direction).
    """
    cols = ", ".join(f"coalesce({v[0]}, 0) as {v[0]}" for v in IDP_FAMILY.values())
    any_nonzero = " or ".join(f"coalesce({v[0]}, 0) <> 0" for v in IDP_FAMILY.values())
    positions = ", ".join(f"'{p}'" for p in OFFENSIVE_POSITIONS)
    rows = q(f"""
        select season, week, player_id, player_display_name, position, team, {cols}
        from {delta('stats_player_week')}
        where season = {int(season)} and season_type = 'REG'
          and position in ({positions}) and ({any_nonzero})
        order by week, player_display_name
    """).to_dict("records")
    out = []
    for row in rows:
        for term, (lake, _team_key, _indiv) in IDP_FAMILY.items():
            if float(row.get(lake) or 0.0) != 0.0:
                out.append({"season": int(row["season"]), "week": int(row["week"]),
                            "playerId": str(row["player_id"]),
                            "name": str(row["player_display_name"] or ""),
                            "lakePosition": str(row["position"] or ""),
                            "team": str(row["team"] or ""),
                            "term": term, "lakeColumn": lake,
                            "lakeValue": float(row[lake])})
    return out


def _sleeper_index(players: dict) -> dict[str, list[tuple[str, dict]]]:
    """folded name → every Sleeper player carrying it. Kept as a LIST so an ambiguous name is
    visible rather than silently collapsed to whichever entry came first."""
    index: dict[str, list[tuple[str, dict]]] = {}
    for sid, entry in players.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get("full_name") or entry.get("last_name") or ""
        folded = _fold(str(name))
        if folded:
            index.setdefault(folded, []).append((sid, entry))
    return index


def resolve(row: dict, index: dict[str, list[tuple[str, dict]]]) -> tuple[str | None, str]:
    """This lake row → a Sleeper player id, or `(None, why)`.

    Name + TEAM first, then name + POSITION, then a unique name. Each rung is reported so a reader
    can see which one carried the row — a resolution nobody can audit is not evidence at n=19.
    """
    candidates = index.get(_fold(row["name"]) or "~none~") or []
    if not candidates:
        return None, "no Sleeper player carries this name"
    by_team = [c for c in candidates if str((c[1].get("team") or "")).upper() == row["team"].upper()]
    if len(by_team) == 1:
        return by_team[0][0], "name+team"
    by_pos = [c for c in candidates
              if str((c[1].get("position") or "")).upper() == row["lakePosition"].upper()]
    if len(by_pos) == 1:
        return by_pos[0][0], "name+position"
    if len(candidates) == 1:
        return candidates[0][0], "unique name"
    return None, f"ambiguous — {len(candidates)} Sleeper players share this name"


def verify(season: int, *, q, delta, cache_dir: Path | None) -> dict:
    rows = population(season, q=q, delta=delta)
    players = _fetch(_SLEEPER_PLAYERS, cache_dir / "sleeper_players.json" if cache_dir else None)
    index = _sleeper_index(players)

    weeks = sorted({r["week"] for r in rows})
    stats = {w: _fetch(_SLEEPER_WEEK_STATS.format(season=season, week=w),
                       cache_dir / f"sleeper_stats_{season}_{w}.json" if cache_dir else None)
             for w in weeks}

    checked, unresolved, contradicting = [], [], []
    for row in rows:
        sid, how = resolve(row, index)
        if sid is None:
            unresolved.append({**row, "resolution": how})
            continue
        line = stats[row["week"]].get(sid) or {}
        entry = players.get(sid) or {}
        _lake, team_key, indiv_keys = IDP_FAMILY[row["term"]]
        # What the LEAGUE'S weight references (a team-defence stat): always 0 for an individual, and
        # reporting it is what makes the first cut's vacuity legible rather than merely asserted.
        team_credit = float(line.get(team_key) or 0.0)
        # What Sleeper ACTUALLY credits this individual with. A nonzero here proves the platform
        # records the event for an offensively-listed player, i.e. its rule is NOT position-scoping.
        indiv = {k: float(line.get(k) or 0.0) for k in indiv_keys if float(line.get(k) or 0.0) != 0.0}
        record = {**row, "sleeperId": sid, "resolution": how,
                  "sleeperPosition": str(entry.get("position") or ""),
                  "leagueWeightKey": team_key, "sleeperTeamGrainCredit": team_credit,
                  "sleeperIndividualCredits": indiv, "sleeperLineFound": bool(line)}
        checked.append(record)
        if indiv:
            contradicting.append(record)

    # ⛔ THE VERDICT, exactly as pre-declared. UNVERIFIED is its own outcome: a row nobody could look
    # up has not been checked, and reporting that as a pass is the vacuous pass this gate forbids.
    if unresolved:
        verdict = "UNVERIFIED"
    elif contradicting:
        verdict = "CONTRADICTED"
    elif not checked:
        verdict = "UNVERIFIED"   # an empty population proves nothing about the rule
    else:
        verdict = "PASS"
    # ⭐ THE VACUITY CONTROL, and it is not optional: the whole verdict rests on the individual keys
    # being real. If Sleeper credits NOBODY anywhere under them, a clean sweep of zeros means the
    # keys are wrong, not that the platform scopes by position — which is exactly how the first cut
    # of this gate returned PASS on nothing.
    # ⚠️ SUMMED ACROSS WEEKS, and the first cut of THIS control was itself wrong: a dict
    # comprehension looping `for w in weeks for k in every_key` writes every week to the same key, so
    # only the last week survived and two live keys reported as DEAD. It failed in the SAFE direction
    # (claiming the instrument unsound rather than sound), which is the only reason it was harmless.
    every_key = sorted({k for v in IDP_FAMILY.values() for k in v[2]})
    totals = {k: 0 for k in every_key}
    for w in weeks:
        for line in (stats[w] or {}).values():
            if not isinstance(line, dict):
                continue
            for k in every_key:
                if float(line.get(k) or 0.0) != 0.0:
                    totals[k] += 1
    dead = sorted(k for k, n in totals.items() if n == 0)
    return {"season": season, "verdict": verdict, "rows": len(rows),
            "checked": checked, "unresolved": unresolved, "contradicting": contradicting,
            "termCounts": {t: sum(1 for r in rows if r["term"] == t) for t in IDP_FAMILY},
            "keyReach": totals, "deadKeys": dead,
            "instrumentSound": not dead}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--season", type=int, default=2025)
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q
    out = verify(args.season, q=q, delta=delta, cache_dir=args.cache_dir)

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"── IDP-at-offensive-grain, {out['season']} REG · population {out['rows']} rows "
              f"{out['termCounts']}")
        print(f"   instrument sound (every individual key reaches someone): "
              f"{out['instrumentSound']}  reach={out['keyReach']}")
        if out["deadKeys"]:
            print(f"   ⛔ DEAD KEYS {out['deadKeys']} — a sweep of zeros would be vacuous, not a PASS")
        for r in out["checked"]:
            flag = "⛔ CREDITED" if r["sleeperIndividualCredits"] else "   none      "
            print(f"   {flag} wk{r['week']:>2} {r['name']:<22} lake={r['lakePosition']:<3} "
                  f"{r['term']:<18} ours={r['lakeValue']:.0f} "
                  f"league-weight[{r['leagueWeightKey']}]={r['sleeperTeamGrainCredit']:.0f} "
                  f"individual={r['sleeperIndividualCredits'] or '{}'}")
        for r in out["unresolved"]:
            print(f"   ⚠️ UNRESOLVED  wk{r['week']:>2} {r['name']:<22} {r['term']:<18} "
                  f"— {r['resolution']}")
        print(f"\nVERDICT: {out['verdict']}")
        if out["verdict"] == "PASS":
            print("  ⇒ ruling ② ships: scoping the IDP family to defensive positions is zero-delta "
                  "on every measured row.")
        elif out["verdict"] == "CONTRADICTED":
            print("  ⇒ ruling ② REVERTS TO OPTION C ON THE SPOT. Sleeper records these events for "
                  "offensively-listed players perfectly well — it puts them in a DIFFERENT KEY "
                  "NAMESPACE from the team-defence keys a league's `def_*` weights reference. The "
                  "rule is NAMESPACE, not position, so position-scoping would give the right answer "
                  "for the wrong reason here and the WRONG answer for a league paying `idp_*`.")
        else:
            print("  ⇒ NOT a pass. A row that could not be resolved has not been checked.")
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
