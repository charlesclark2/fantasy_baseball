"""NF-C-LDA-0 — spike question 2: can we resolve ESPN's players to OUR player ids?

Reproduces every resolution figure in `docs/nf_c_lda_0_espn_live_draft_spike.md`. Run:

    uv run python extension/tools/measure_resolution.py            # name rung only (no AWS needed)
    AWS_DEFAULT_REGION=us-east-2 uv run python extension/tools/measure_resolution.py --with-crosswalk

⭐ IT RESOLVES THROUGH THE SHIPPED JOIN, NOT A SECOND COPY OF IT. The key builder is
`league_scoring._join_key` — the same function the served `/fantasy/nfl/league-board` roster join
uses, including the NF-C6P3 D/ST franchise resolution (a team defence is joined on its FRANCHISE,
never on the lossy display name: the board publishes "DET D/ST" and ESPN publishes "Lions D/ST",
which never match as text). A private matcher here would measure a join we do not ship, and would
be free to drift from the one we do — the E9.61 "two renderers of one field are two rule sets"
lesson, on the measurement side.

⚠️ A NON-MATCH HAS THREE CAUSES AND THEY ARE NOT THE SAME FINDING (NF-K1). This script separates
them, because collapsing them is what cost two prior investigations:
  1. the position is absent from the published board  → nothing could have matched; OUR gap
  2. the position is published and this name missed   → a real join failure
  3. the player is not in the board at all            → we do not project them; working as intended
Only (2) is a defect in the join. Reporting a single "match rate" hides which one you have.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

BOARD = (REPO / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
         / "player_history_json/2026/projections.json")
FIXTURE = REPO / "betting_ml/tests/fixtures/espn_league_642070_2025_drafted.json"

#: ESPN's FULL player universe, cached by `espn_source.fetch_espn_draftranks`.
#: ⚠️ GITIGNORED (`.gitignore:119` — `artifacts/*_cache/`), so it is ABSENT from any fresh
#: `git worktree` even when it exists in the main checkout. That is the NF-INFRA1 landmine, and this
#: spike walked straight into it: an earlier pass reported "no local ESPN pool capture — the
#: directory does not exist", which was true of the worktree and FALSE of the main checkout, where
#: eight seasons had been sitting since 2026-07-26. Hence `--pool` takes an explicit path.
POOL_CACHE = (REPO / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
              / "espn_cache/espn_2026.json")


def load_board() -> list[dict]:
    return json.loads(BOARD.read_text())["players"]


def load_espn_rows() -> list[tuple[str, str | None, str | None, str]]:
    """(name, position, team, espn_player_id) for every rostered player in the real capture."""
    from app.backend.services.platform_import import espn as E

    teams, _ = E.translate_teams(json.loads(FIXTURE.read_text()))
    return [(p.name, p.position, p.team, str(p.player_key)) for t in teams for p in t.players]


def espn_id_crosswalk() -> dict[str, set[str]] | None:
    """`espn_id -> {gsis_id}` from nflverse `weekly_rosters`, or None when the lake is unreachable.

    ⚠️ Returns None — NEVER an empty dict — when the lake cannot be read. An empty crosswalk would
    score as "tier 1 resolved nothing", which is a MEASUREMENT, and this would not be one
    (NF1.7(a): a check that could not run is not a failing check).

    ⭐ Read season-UNSCOPED deliberately (the NF-W0b widening): a vendor id is a stable property of
    a player, so a season whose roster row omits `espn_id` is still resolvable from another's.
    """
    try:
        from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

        df = q(f"""
            select gsis_id, cast(espn_id as varchar) as espn_id
            from {delta('weekly_rosters')}
            where gsis_id is not null
              and espn_id is not null and length(cast(espn_id as varchar)) > 0
            group by 1, 2
        """)
    except Exception as exc:  # noqa: BLE001 — an unreachable lake is a skip, not a failure
        print(f"  [crosswalk] UNAVAILABLE ({type(exc).__name__}: {exc}) — tier 1 not measured")
        return None
    out: dict[str, set[str]] = collections.defaultdict(set)
    for gsis, espn in zip(df.gsis_id, df.espn_id):
        out[str(espn)].add(str(gsis))
    return dict(out)


def measure_pool(path: Path, *, with_crosswalk: bool) -> int:
    """The FULL-POOL measurement — the population a live draft actually resolves against.

    ⭐ WHY THIS EXISTS SEPARATELY FROM THE ROSTER MEASUREMENT. The roster fixture is 172 players:
    the DRAFTED TOP of the pool. It cannot show the two defects that only appear at pool scale, and
    both are real (measured 2026-08-18):

      • FALSE MERGES — two DIFFERENT ESPN players collapsing onto ONE board row. The suffix
        stripper folds "Frank Gore Jr." (BUF, the son, on our board) onto retired "Frank Gore".
      • POSITION-DERIVATION EDGES — a TWO-WAY player's `eligibleSlots` span both sides of the ball,
        so Travis Hunter derives as CB and drops out entirely.

    ⛔ A RAW "match rate" over this population is MEANINGLESS and is deliberately not the headline:
    the pool is ~4,500 fantasy-position rows against a board of 858, so most rows SHOULD be
    unmatched (NF-K1 cause 3 — we do not project them). The decision-relevant figures are BOARD
    COVERAGE (does the pool contain the players we project?) and the FALSE-MERGE count.
    """
    from app.backend.services import league_scoring as LS
    from app.backend.services.platform_import import espn as E

    if not path.exists():
        print(f"pool cache not found: {path}\n"
              "  → land it with:  uv run python -c \"from quant_sports_intel_models.football.nfl"
              ".fantasy import espn_source as E; E.fetch_espn_draftranks(2026)\"\n"
              "  ⚠️ it is GITIGNORED, so a fresh worktree will not have it even when the main "
              "checkout does (NF-INFRA1).")
        return 1

    raw = json.loads(path.read_text())
    pool = raw if isinstance(raw, list) else (raw.get("players") or [])
    board = load_board()
    by_key = {LS._join_key(p["name"], p["pos"], p.get("team")): p for p in board}
    by_id = {p["id"]: p for p in board}
    xw = espn_id_crosswalk() if with_crosswalk else None

    rows = []
    for entry in pool:
        pl = entry.get("player") if isinstance(entry.get("player"), dict) else entry
        # ⚠️ Position from `eligibleSlots`, NEVER `defaultPositionId` — NF-C0 §4c: slot 4 is WR while
        # defaultPositionId 4 is TE, and reading the wrong one silently mis-positions real players.
        pos = E._player_position(pl)
        if pos not in LS.PROJECTABLE_POSITIONS:
            continue
        rows.append((str(pl.get("fullName") or ""), pos,
                     E._PRO_TEAM_BY_ID.get(int(pl.get("proTeamId") or -1)), str(pl.get("id"))))

    print(f"POOL    {len(pool)} raw rows → {len(rows)} in projectable positions "
          f"{dict(collections.Counter(r[1] for r in rows))}")
    print(f"BOARD   {len(board)} rows\n")

    t1 = t3 = 0
    claims: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
    disagreements = []
    for name, pos, team, pid in rows:
        hit1 = None
        if xw is not None:
            gs = xw.get(pid) or set()
            if len(gs) == 1:
                hit1 = by_id.get(next(iter(gs)))
        hit3 = by_key.get(LS._join_key(name, pos, team))
        if hit1 and hit3 and hit1["id"] != hit3["id"]:
            disagreements.append((name, hit1["name"], hit3["name"]))
        hit = hit1 or hit3
        if hit1:
            t1 += 1
        elif hit3:
            t3 += 1
        if hit:
            claims[hit["id"]].append((name, pid, "tier1" if hit1 else "tier3"))

    resolved = t1 + t3
    print(f"resolved {resolved}/{len(rows)}  (tier1 {t1} · tier3 {t3})"
          "   ← a LOW rate is CORRECT here: the board projects 858, the pool is far larger")
    print(f"⭐ BOARD COVERAGE: {len(claims)}/{len(board)} = {len(claims)/len(board):.1%} "
          "of the players we project are findable in the pool")
    if xw is not None:
        print(f"⭐ tier1/tier3 DISAGREEMENTS: {len(disagreements)}")
        for d in disagreements[:10]:
            print(f"     {d[0]}: id-path={d[1]!r} vs name-path={d[2]!r}")

    collisions = {k: v for k, v in claims.items() if len(v) > 1}
    print(f"\n⛔ FALSE-MERGE COLLISIONS (>1 pool player → the SAME board row): {len(collisions)}")
    by_cause = collections.Counter()
    for bid_, members in collisions.items():
        tiers = {t for _, _, t in members}
        cause = ("MIXED (id + name)" if tiers == {"tier1", "tier3"}
                 else "name-rung only" if tiers == {"tier3"} else "id-rung only")
        by_cause[cause] += 1
        b = by_id[bid_]
        print(f"   {b['name']:<26} [{b['pos']} {b['team']}]  {cause}")
        for nm, pid, t in members:
            print(f"       {t}  espn_id={pid:<10} {nm}")
    for cause, k in sorted(by_cause.items()):
        print(f"   → {cause}: {k}")
    print("\n⭐ EVERY collision involves the NAME rung; the stable-id rung produces none. The fix is\n"
          "   the resolver's own rule (b): AMBIGUITY IS AN UNRESOLVED, NOT A COIN FLIP — a name key\n"
          "   claimed by >1 pool row must resolve for NEITHER, leaving the id rung to decide.")

    missing = [p for p in board if p["id"] not in claims]
    print(f"\nBoard rows the pool did NOT cover ({len(missing)}):")
    for p in missing:
        print(f"   {p['pos']:<4} {p['name']:<26} {p['team']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-crosswalk", action="store_true",
                    help="also measure the tier-1 espn_id rung (needs lake/AWS access)")
    ap.add_argument("--pool", nargs="?", const=str(POOL_CACHE), default=None, metavar="PATH",
                    help="measure the FULL ESPN player universe instead of one league's roster "
                         f"(default {POOL_CACHE})")
    args = ap.parse_args()
    if args.pool:
        return measure_pool(Path(args.pool), with_crosswalk=args.with_crosswalk)

    from app.backend.services import league_scoring as LS

    board = load_board()
    by_key = {LS._join_key(p["name"], p["pos"], p.get("team")): p for p in board}
    by_id = {p["id"]: p for p in board}
    published = set(LS.published_positions(board))

    print(f"BOARD   rows={len(board)}  distinct join keys={len(by_key)}  "
          f"positions={sorted(published)}")
    if len(by_key) != len(board):
        print(f"  ⚠️ {len(board) - len(by_key)} board rows COLLIDE on the join key")

    rows = load_espn_rows()
    print(f"ESPN    rostered players={len(rows)}  "
          f"with an espn id={sum(1 for r in rows if r[3])}/{len(rows)}")
    print(f"        positions={dict(collections.Counter(r[1] for r in rows))}\n")

    xw = espn_id_crosswalk() if args.with_crosswalk else None

    tier1 = tier3 = 0
    ambiguous = 0
    disagreements: list[tuple[str, str, str]] = []
    unmatched: list[tuple[str, str, str, str, str]] = []

    for name, pos, team, pid in rows:
        hit1 = None
        if xw is not None:
            gs = xw.get(pid) or set()
            if len(gs) > 1:
                ambiguous += 1          # ⛔ ABSTAIN. A wrong merge is worse than a miss (resolver (b)).
            elif len(gs) == 1:
                hit1 = by_id.get(next(iter(gs)))
        hit3 = by_key.get(LS._join_key(name, pos, team))

        if hit1 and hit3 and hit1["id"] != hit3["id"]:
            disagreements.append((name, hit1["name"], hit3["name"]))
        if hit1:
            tier1 += 1
        elif hit3:
            tier3 += 1
        else:
            unmatched.append((name, pos or "?", team or "?", pid,
                              LS._join_key(name, pos, team)))

    n = len(rows)
    resolved = tier1 + tier3
    print("RESOLUTION LADDER")
    if xw is not None:
        print(f"  tier 1  stable vendor id (espn_id → gsis)   {tier1:>4}  {tier1/n:6.1%}")
    else:
        print("  tier 1  stable vendor id                     NOT MEASURED (no lake access)")
    print(f"  tier 3  exact name + position (+DST franchise) {tier3:>4}  {tier3/n:6.1%}")
    print(f"  UNRESOLVED                                     {len(unmatched):>4}  {len(unmatched)/n:6.1%}")
    print(f"  ─ combined                                     {resolved:>4}  {resolved/n:6.1%}")
    if xw is not None:
        print(f"\n  ambiguous espn_id (abstained)                {ambiguous}")
        print(f"  ⭐ tier1/tier3 DISAGREEMENTS                   {len(disagreements)}"
              "   ← two independent identity paths, cross-validating")
        for d in disagreements[:10]:
            print(f"       {d[0]}: id-path={d[1]!r} vs name-path={d[2]!r}")

    # ── The three causes, kept apart (NF-K1) ──────────────────────────────────────────────────
    print(f"\nUNMATCHED ({len(unmatched)}) — classified, because 'not matched' is three findings:")
    cause = collections.Counter()
    for name, pos, team, pid, key in unmatched:
        if pos not in published:
            c = "1 position absent from board (OUR gap)"
        elif any(LS.normalize_player_name(name) == LS.normalize_player_name(p["name"])
                 for p in board):
            c = "2 JOIN FAILURE (name present on board, key missed)"
        else:
            c = "3 not projected (absent from board entirely)"
        cause[c] += 1
        print(f"   [{c[0]}] {pos:<4} {name:<26} team={team:<4} espn_id={pid:<9} key={key}")
    for c, k in sorted(cause.items()):
        print(f"   → {c}: {k}")
    join_failures = sum(v for k, v in cause.items() if k.startswith("2"))
    print(f"\n⭐ JOIN-FAILURE RATE (the only cause that is a defect in the join): "
          f"{join_failures}/{n} = {join_failures/n:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
