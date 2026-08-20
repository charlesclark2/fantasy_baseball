"""NF-C-LDA-6 — what should a BENCH pick be measured against?

⚠️ RESEARCH ONLY. Nothing here is imported by the engine, the API or the app; it changes no shipped
ranking. It exists to answer one measured question before any of them move.

══ THE QUESTION ═══════════════════════════════════════════════════════════════════════════════════
Once every starter slot is filled, `recommend` ranks bench depth by VOR — value over the LEAGUE's
last startable player at that position. Measured on the real 2026 board, that is structurally
guaranteed to return a backup TE or QB in the back half of every draft:

    ~pick 115, best available   QB Mendoza +3.0 | TE Sadiq +23.7 | RB -37.2 | WR -27.0
    players still above replacement:      2     |        3       |     0    |     0

35 WRs and 25 RBs clear replacement and a 12-team room consumes all of them by round 8, because
every team starts two or three. Only 12 TEs and 12 QBs clear it and each team needs one. So positive
VOR survives at exactly the two positions where a bench player is LEAST useful — you can only ever
start one of him. A live 2026 mock draft reported precisely this: "WRs seemed to not even pop up …
backup TEs and QBs definitely were."

VOR is a STARTER-SCARCITY currency. The question is what replaces it for a bench seat.

══ THE FIELD (pre-registered) ═════════════════════════════════════════════════════════════════════
Every arm is a MATCHED FOIL: identical `recommend()` machinery — needs, tiers, flex re-basing, bye
penalties, the reserve constraint, K/DST deferral — with ONLY the level-0 (bench) score replaced. So
a difference between arms is attributable to the bench comparator and to nothing else (NF-D10/D15).

  incumbent           VOR x (1 - surplus)             the shipped rule; the null to beat
  own_worst_starter   his rate - MY weakest startable player's rate at a seat he could fill
  seats_covered       incumbent, scaled by how many startable seats the position has for me
  insurance           P(I actually need him) x what he adds over the next man up

  raw_points          highest projection, position-blind      reference, not a candidate
  ⚓ oracle           `insurance` computed on REALIZED availability — same family, same sample,
                      peeking. NOTHING may beat it (E2.1-r / NF1.7(b)).
  ⚓ nihilist         prefers the WORST available bench player. MUST LOSE. A metric a nihilist wins
                      cannot select anything (NF-D11).

══ THE METRIC ═════════════════════════════════════════════════════════════════════════════════════
Expected points from the STARTING LINEUP over a simulated season — the only metric on which a bench
player can be worth anything at all. ⭐ Scoring "your best nine" instead would make bench depth
worthless BY CONSTRUCTION and every arm would tie; the whole question lives in the weeks a starter
is on bye or absent and somebody has to be started in his place.

Availability is read from the board, not invented: `g` is expected games of 17 (18 weeks, one bye),
so a player misses `17 - g` non-bye weeks, and his per-game rate is `pts / g` — consistent by
construction, since `g x rate` returns his projected season.

⚠️ COMMON RANDOM NUMBERS. Every arm drafts against the same room and plays the same season — the
same bye weeks and the same realized absences. The paired delta therefore cancels almost all of the
simulation noise before it reaches the metric (NF-W7k), which is what makes a small per-draft
difference readable at this sample size.
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from quant_sports_intel_models.fantasy_engine.draft import (
    RosterRequirements,
    open_starter_slots,
    recommend,
)
from quant_sports_intel_models.fantasy_engine.league_config import (
    LeagueConfig,
    draftable_slot_count,
)

WEEKS = 18
_REPO = Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The season
# ══════════════════════════════════════════════════════════════════════════════════════════════
def per_game_rate(row: dict) -> float:
    g = float(row.get("games") or 0.0)
    return (float(row.get("league_points") or 0.0) / g) if g > 0 else 0.0


def draw_absences(rows: list[dict], rng: random.Random, contiguous: bool = False) -> dict[str, set[int]]:
    """Which non-bye weeks each player misses. ⚠️ Drawn INDEPENDENTLY per week, which fragments an
    injury a real one would keep contiguous. Neutral across arms and identical under CRN, so it
    cannot favour a candidate — but it does understate the value of a bench player who covers a
    multi-week absence, i.e. it is CONSERVATIVE toward the incumbent. Reported, not hidden."""
    out: dict[str, set[int]] = {}
    for row in rows:
        g = float(row.get("games") or 0.0)
        misses = max(0.0, 17.0 - g)
        bye = row.get("bye")
        weeks = [w for w in range(1, WEEKS + 1) if w != bye]
        if not contiguous:
            miss_p = max(0.0, min(1.0, misses / 17.0))
            out[str(row["player_id"])] = {w for w in weeks if rng.random() < miss_p}
            continue
        # ⭐ THE SENSITIVITY THAT MATTERS. A real injury is a BLOCK of weeks, not a coin flip per
        # week, and a block is exactly the case a bench player exists to cover — so the independent
        # draw UNDERSTATES depth and is conservative toward the incumbent. If the ranking survives
        # both, it does not rest on the absence model.
        n = int(misses) + (1 if rng.random() < (misses - int(misses)) else 0)
        if n <= 0:
            out[str(row["player_id"])] = set()
            continue
        start = rng.randrange(0, max(1, len(weeks) - n + 1))
        out[str(row["player_id"])] = set(weeks[start:start + n])
    return out


def _fill_lineup(available: list[dict], cfg: LeagueConfig) -> float:
    """Best legal lineup from who is available this week. Dedicated slots first (most constrained),
    then flex — identical for every arm, so the assignment heuristic cannot favour one."""
    pool = sorted(available, key=per_game_rate, reverse=True)
    used: set[int] = set()
    total = 0.0
    dedicated = [s for s in cfg.roster if not s.bench and len(s.eligible) == 1]
    flex = [s for s in cfg.roster if not s.bench and len(s.eligible) > 1]
    for slot in dedicated + flex:
        for _ in range(slot.count):
            for i, p in enumerate(pool):
                if i in used or p["position"] not in slot.eligible:
                    continue
                used.add(i)
                total += per_game_rate(p)
                break
    return total


def season_points(roster: list[dict], cfg: LeagueConfig, absences: dict[str, set[int]]) -> float:
    total = 0.0
    for week in range(1, WEEKS + 1):
        avail = [
            p for p in roster
            if p.get("bye") != week and week not in absences.get(str(p["player_id"]), ())
        ]
        total += _fill_lineup(avail, cfg)
    return total


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The bench rules
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class BenchContext:
    cfg: LeagueConfig
    req: RosterRequirements
    my_rows: list[dict]
    realized_games: dict[str, float] | None = None  # oracle only
    absences: dict[str, set[int]] | None = None     # oracle only


def _my_startable_rates(ctx: BenchContext, pos: str) -> list[float]:
    """The rates of my players who currently occupy a seat this position could fill."""
    seats = ctx.req.dedicated.get(pos, 0) + sum(n for elig, n in ctx.req.flex if pos in elig)
    same = sorted((per_game_rate(r) for r in ctx.my_rows if r["position"] == pos), reverse=True)
    return same[:seats]


def _seats_for(ctx: BenchContext, pos: str) -> int:
    return ctx.req.dedicated.get(pos, 0) + sum(n for elig, n in ctx.req.flex if pos in elig)


def bench_incumbent(row, rec, ctx):
    return rec.score


def bench_own_worst_starter(row, rec, ctx):
    """His rate minus my WEAKEST startable player at a seat he could fill. A backup QB behind an
    elite starter is hugely negative; a bench RB a shade behind my RB3 is barely negative."""
    held = _my_startable_rates(ctx, row["position"])
    if not held:
        return per_game_rate(row) * WEEKS
    return (per_game_rate(row) - held[-1]) * WEEKS


def bench_seats_covered(row, rec, ctx):
    """The incumbent, scaled by how many startable seats depth at this position can ever cover."""
    max_seats = max(_seats_for(ctx, p) for p in ("QB", "RB", "WR", "TE")) or 1
    return rec.score * (_seats_for(ctx, row["position"]) / max_seats)


def _expected_starts(row, ctx, games: dict[str, float] | None) -> float:
    """Weeks I would actually start him: the weeks enough of the players ahead of him at his
    position are unavailable that he reaches a seat."""
    pos = row["position"]
    seats = _seats_for(ctx, pos)
    ahead = sorted(
        (r for r in ctx.my_rows if r["position"] == pos), key=per_game_rate, reverse=True
    )
    mine_rate = per_game_rate(row)
    ahead = [r for r in ahead if per_game_rate(r) > mine_rate]
    if len(ahead) < seats:
        return float(WEEKS)  # he already reaches a seat on merit

    def miss_p(r: dict) -> float:
        g = (games or {}).get(str(r["player_id"]), float(r.get("games") or 0.0))
        return max(0.0, min(1.0, (17.0 - g) / 17.0))

    starts = 0.0
    for week in range(1, WEEKS + 1):
        # P(at least len(ahead) - seats + 1 of those ahead are out this week), plus byes.
        out_probs = [1.0 if r.get("bye") == week else miss_p(r) for r in ahead]
        need = len(ahead) - seats + 1
        # Poisson-binomial, exact by DP — the counts here are tiny.
        dist = [1.0]
        for p in out_probs:
            nxt = [0.0] * (len(dist) + 1)
            for k, v in enumerate(dist):
                nxt[k] += v * (1 - p)
                nxt[k + 1] += v * p
            dist = nxt
        starts += sum(dist[need:])
    return starts


def _displaced_rate(ctx: BenchContext, pos: str) -> float:
    """Who he actually takes the snaps from: my best player at this position who is NOT already in a
    startable seat. Zero if I have none — then the slot would otherwise go empty."""
    rates = sorted((per_game_rate(r) for r in ctx.my_rows if r["position"] == pos), reverse=True)
    bench = rates[_seats_for(ctx, pos):]
    return bench[0] if bench else 0.0


def bench_insurance(row, rec, ctx):
    """P(I actually need him) x what he adds over the man he would replace.

    ⚠️ The comparator is my best BENCH player at the position, not my worst starter: on the weeks he
    plays, the starter is the one who is out, so what he displaces is whoever would otherwise have
    covered that seat — or nothing, if I have no cover at all."""
    return _expected_starts(row, ctx, None) * max(
        0.0, per_game_rate(row) - _displaced_rate(ctx, row["position"])
    )


def bench_oracle(row, rec, ctx):
    """⚓ THE PEEKING FLOOR: how much this player ACTUALLY improves my realized season.

    ⚠️ THE FIRST VERSION OF THIS ANCHOR WAS INACTIVE AND IT LOOKED LIKE A RESULT. It was `insurance`
    with realized availability substituted, which only enters through a branch that rarely fires —
    so it scored BYTE-IDENTICALLY to the honest `insurance` arm (1838.1 vs 1838.1) and then "failed"
    against a third rule. An anchor that cannot act is uninformative, never a pass and never a fail
    (NF-W6d / NF-D20); reading that as a metric inversion would have been the wrong finding.

    This version cannot be inactive: it re-scores every candidate by the marginal gain it makes to
    the SAME season the arm will be graded on. It is greedy over the SAME machinery as every other
    arm (same candidate set, same reserve constraint, same slots), so it is same-family and
    same-sample — a floor, not a different model (NF1.7(b))."""
    assert ctx.absences is not None, "the oracle was run without the season it is peeking at"
    base = season_points(ctx.my_rows, ctx.cfg, ctx.absences)
    return season_points(ctx.my_rows + [row], ctx.cfg, ctx.absences) - base


def bench_raw_points(row, rec, ctx):
    return float(row.get("league_points") or 0.0)


def bench_nihilist(row, rec, ctx):
    """⚓ Prefers the WORST available. MUST LOSE."""
    return -float(row.get("league_points") or 0.0)


BENCH_RULES = {
    "incumbent": bench_incumbent,
    "own_worst_starter": bench_own_worst_starter,
    "seats_covered": bench_seats_covered,
    "insurance": bench_insurance,
    "raw_points": bench_raw_points,
    "oracle": bench_oracle,
    "nihilist": bench_nihilist,
}
ANCHORS = {"oracle", "nihilist"}
REFERENCES = {"raw_points"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The draft
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_board(season: int = 2026) -> tuple[list[dict], LeagueConfig, dict[str, float]]:
    """The real published board, scored for a real 12-team league — not a synthetic one."""
    from app.backend.services.draft_assistant import engine_row

    src = json.loads(
        (_REPO / "betting_ml/tests/fixtures/nf_c_lda_1_optimizer_parity_input.json").read_text()
    )
    raw = {str(r["id"]): r for r in src["board"]}
    rows = []
    for r in src["board"]:
        row = engine_row(r, src["replacement"])
        row["games"] = float(raw[str(r["id"])].get("g") or 0.0)
        row["adp"] = raw[str(r["id"])].get("adp")
        rows.append(row)
    cfg = LeagueConfig.from_dict(src["config"])
    return rows, cfg, src["replacement"]


def _starter_capacity(req: RosterRequirements) -> int:
    return sum(req.dedicated.values()) + sum(n for _elig, n in req.flex)


def _bench_of(roster: list[dict], cfg: LeagueConfig) -> list[dict]:
    """Who does NOT hold a starting slot on a fully-healthy week — the actual bench."""
    pool = sorted(roster, key=per_game_rate, reverse=True)
    used: set[int] = set()
    dedicated = [s for s in cfg.roster if not s.bench and len(s.eligible) == 1]
    flex = [s for s in cfg.roster if not s.bench and len(s.eligible) > 1]
    for slot in dedicated + flex:
        for _ in range(slot.count):
            for i, pl in enumerate(pool):
                if i in used or pl["position"] not in slot.eligible:
                    continue
                used.add(i)
                break
    return [pl for i, pl in enumerate(pool) if i not in used]


def _room_order(rows: list[dict], rng: random.Random) -> list[dict]:
    """How the other eleven teams draft: ADP with noise, players without an ADP last by projection.
    Identical across arms under CRN, so every rule faces the SAME room."""
    def key(r):
        adp = r.get("adp")
        base = float(adp) if adp else 500.0 - float(r.get("league_points") or 0.0) / 100.0
        return base + rng.gauss(0, 6)

    return sorted(rows, key=key)


def draft_one(
    rows: list[dict],
    cfg: LeagueConfig,
    rule_name: str,
    my_slot: int,
    rng: random.Random,
    realized_games: dict[str, float] | None,
    absences: dict[str, set[int]] | None = None,
) -> list[dict]:
    """Snake draft. Our team picks by `rule_name`; the other eleven follow the room order."""
    rule = BENCH_RULES[rule_name]
    n_teams = cfg.n_teams
    rounds = draftable_slot_count(cfg.roster)
    room = _room_order(rows, rng)
    by_id = {str(r["player_id"]): r for r in rows}
    taken: set[str] = set()
    mine: list[str] = []
    req = RosterRequirements.from_config(cfg)

    for rnd in range(1, rounds + 1):
        order = range(1, n_teams + 1) if rnd % 2 else range(n_teams, 0, -1)
        for slot in order:
            if slot != my_slot:
                for r in room:
                    pid = str(r["player_id"])
                    if pid not in taken:
                        taken.add(pid)
                        break
                continue
            my_rows = [by_id[p] for p in mine]
            recs = recommend(rows, config=cfg, drafted_ids=taken, my_player_ids=mine, top_n=40)
            if not recs:
                break
            ctx = BenchContext(cfg=cfg, req=req, my_rows=my_rows,
                               realized_games=realized_games, absences=absences)

            # ⭐⭐ THE MATCHED FOIL, AND THE SHAPE IS LOAD-BEARING. Every arm first asks the SHIPPED
            # engine what it would take. If that is a need-filler — an open starter slot, or the
            # reserve constraint binding — every arm takes it and they are identical. The arms
            # diverge ONLY on WHICH BENCH PLAYER to take, never on whether to take one.
            #
            # ⚠️ THE ALTERNATIVE — re-scoring level-0 rows inside the engine's own sort — is what
            # this harness did first, and it is WRONG: the candidate rules return season points
            # while `rec.score` is in VOR, so mixing them let an arm jump a bench pick over a
            # need-filler purely on units. It made the peeking oracle score BELOW the incumbent,
            # which reads as a metric inversion and is really a harness bug (the anchors caught it).
            shipped = max(recs, key=lambda r: (r.must_fill, not r.deferred, r.score))
            if shipped.need_level != 0:
                best = shipped
            else:
                tier = [
                    r for r in recs
                    if r.need_level == 0
                    and r.must_fill == shipped.must_fill
                    and r.deferred == shipped.deferred
                ]
                best = max(tier, key=lambda r: rule(by_id[r.player_id], r, ctx))
            taken.add(best.player_id)
            mine.append(best.player_id)
    return [by_id[p] for p in mine]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The run
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(seeds: int = 10, slots: list[int] | None = None,
        contiguous: bool = False) -> dict:
    rows, cfg, _ = load_board()
    slots = slots or list(range(1, cfg.n_teams + 1))
    arms = list(BENCH_RULES)
    per_arm: dict[str, list[float]] = {a: [] for a in arms}
    bench_mix: dict[str, dict[str, int]] = {}
    divergence: dict[str, list[int]] = {}
    per_slot: dict[str, dict[int, list[float]]] = {}
    req = RosterRequirements.from_config(cfg)
    cells: list[tuple[int, int]] = []

    for seed in range(seeds):
        for slot in slots:
            # ⭐ COMMON RANDOM NUMBERS: one room order and one realized season per (seed, slot),
            # shared by every arm, so the paired delta cancels the simulation noise (NF-W7k).
            absences = draw_absences(rows, random.Random(f"abs-{seed}"), contiguous)
            realized = {
                str(r["player_id"]): float(WEEKS - 1 - len(absences[str(r["player_id"])]))
                for r in rows
            }
            rosters = {}
            for arm in arms:
                roster = draft_one(
                    rows, cfg, arm, slot,
                    random.Random(f"room-{seed}-{slot}"),
                    realized if arm == "oracle" else None,
                    absences if arm == "oracle" else None,
                )
                rosters[arm] = roster
                per_arm[arm].append(season_points(roster, cfg, absences))
                # ⭐ WHAT each rule actually drafts, which is the question the live draft asked:
                # "WRs seemed to not even pop up, backup TEs and QBs definitely were."
                # ⚠️ Classified by whether a player ends up in a STARTING SLOT, not by draft order:
                # K and D/ST are drafted last by design, so "the last six picks" counted both of
                # them as bench in EVERY arm (an identical 17% each) and diluted every real share
                # by a third. Measured on the actual assignment instead.
                for row in _bench_of(roster, cfg):
                    bench_mix.setdefault(arm, {}).setdefault(row["position"], 0)
                    bench_mix[arm][row["position"]] += 1
            # ⚠️ TWO ARMS THAT NEVER PICK DIFFERENTLY CANNOT BE SEPARATED BY THIS STUDY, and their
            # equal scores would read as a measured tie rather than as an inert comparison
            # (NF-W6d). Measured, not assumed.
            base_ids = {str(r["player_id"]) for r in rosters["incumbent"]}
            for arm in arms:
                ids = {str(r["player_id"]) for r in rosters[arm]}
                divergence.setdefault(arm, []).append(len(ids - base_ids))
            for arm in arms:
                per_slot.setdefault(arm, {}).setdefault(slot, []).append(per_arm[arm][-1])
            cells.append((seed, slot))
    return {"arms": per_arm, "cells": cells, "n_teams": cfg.n_teams,
            "bench_mix": bench_mix, "divergence": divergence, "per_slot": per_slot}


def report(result: dict) -> str:
    arms = result["arms"]
    base = arms["incumbent"]
    n = len(base)
    lines = [
        "# NF-C-LDA-6 — what a BENCH pick should be measured against",
        "",
        f"{n} simulated drafts per arm ({len(set(s for s, _ in result['cells']))} seasons x "
        f"{result['n_teams']} draft slots), common random numbers across arms.",
        "Metric: expected STARTING-LINEUP points over an 18-week season with byes and absence.",
        "",
        "| arm | mean season pts | vs incumbent | 95% CI | won | of | "
        "players differing from incumbent | note |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    ranked = sorted(arms, key=lambda a: -statistics.mean(arms[a]))
    div = result.get("divergence", {})
    for arm in ranked:
        vals = arms[arm]
        deltas = [a - b for a, b in zip(vals, base)]
        wins = sum(1 for d in deltas if d > 0)
        note = "⚓ anchor" if arm in ANCHORS else ("reference" if arm in REFERENCES else "")
        moved = statistics.mean(div.get(arm, [0])) if arm in div else 0.0
        se = (statistics.stdev(deltas) / (n ** 0.5)) if n > 1 and any(deltas) else 0.0
        ci = f"±{1.96 * se:.1f}" if se else "—"
        lines.append(
            f"| `{arm}` | {statistics.mean(vals):.1f} | {statistics.mean(deltas):+.1f} | {ci} | "
            f"{wins} | {n} | {moved:.1f} | {note} |"
        )

    mix = result.get("bench_mix", {})
    if mix:
        positions = ["QB", "RB", "WR", "TE", "K", "DST"]
        lines += ["", "## What each rule actually puts on the bench", "",
                  "| arm | " + " | ".join(positions) + " |",
                  "|---|" + "---:|" * len(positions)]
        for arm in ranked:
            row = mix.get(arm, {})
            tot = sum(row.values()) or 1
            lines.append(f"| `{arm}` | "
                         + " | ".join(f"{100 * row.get(p, 0) / tot:.0f}%" for p in positions) + " |")
    # ⭐ THE TWO LEADERS HEAD TO HEAD, PAIRED. Their intervals against the incumbent are
    # correlated (same CRN), so the difference between those two numbers is NOT a comparison —
    # only the paired delta is (NF1.8: a rank statistic cannot tell a tie from a win).
    real = [a for a in ranked if a not in ANCHORS and a not in REFERENCES and a != "incumbent"]
    if len(real) >= 2:
        a, b = real[0], real[1]
        d = [x - y for x, y in zip(arms[a], arms[b])]
        se = statistics.stdev(d) / (n ** 0.5) if n > 1 else 0.0
        wins = sum(1 for v in d if v > 0)
        lines += ["", f"### `{a}` vs `{b}`, paired", "",
                  f"* mean delta **{statistics.mean(d):+.1f}** pts, 95% CI ±{1.96 * se:.1f}",
                  f"* `{a}` wins **{wins} of {n}** paired drafts",
                  f"* verdict: **{'separable' if abs(statistics.mean(d)) > 1.96 * se else 'a TIE — this study cannot rank them'}**"]

    per_slot = result.get("per_slot")
    if per_slot:
        lines += ["", "### By draft slot (vs incumbent)", "",
                  "| arm | " + " | ".join(f"{i}" for i in sorted(per_slot["incumbent"])) + " |",
                  "|---|" + "---:|" * len(per_slot["incumbent"])]
        for arm in ranked:
            if arm == "incumbent":
                continue
            cells_ = [statistics.mean(per_slot[arm][sl]) - statistics.mean(per_slot["incumbent"][sl])
                      for sl in sorted(per_slot[arm])]
            lines.append(f"| `{arm}` | " + " | ".join(f"{c:+.0f}" for c in cells_) + " |")
    return "\n".join(lines)


def check_anchors(result: dict) -> list[str]:
    """⚠️ THE ANCHORS ARE GATES, NOT COMMENTARY. A metric an oracle loses, or a nihilist wins, cannot
    select anything and its leaderboard must not be read (E2.1-r / NF-D11)."""
    arms = result["arms"]
    means = {a: statistics.mean(v) for a, v in arms.items()}
    problems = []
    real = [a for a in arms if a not in ANCHORS]
    best_real = max(real, key=lambda a: means[a])
    if means["oracle"] < means[best_real]:
        problems.append(
            f"ORACLE FLOOR BREACHED: `{best_real}` ({means[best_real]:.1f}) beats the peeking "
            f"oracle ({means['oracle']:.1f}) — the metric is inverted, do not read the ranking"
        )
    worst_real = min(real, key=lambda a: means[a])
    if means["nihilist"] >= means[worst_real]:
        problems.append(
            f"DEGENERATE CEILING BREACHED: the nihilist ({means['nihilist']:.1f}) is not last "
            f"(`{worst_real}` {means[worst_real]:.1f}) — a metric a nihilist wins selects nothing"
        )
    spread = max(means.values()) - min(means.values())
    if spread < 1.0:
        problems.append(
            f"INSTRUMENT BLIND: every arm within {spread:.2f} pts — the simulation cannot "
            "distinguish these rules at all, so no verdict is available"
        )
    return problems


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--slots", type=int, nargs="*", default=None)
    ap.add_argument("--contiguous", action="store_true",
                    help="injuries as a contiguous BLOCK of weeks instead of independent draws")
    ap.add_argument("--out", default="ablation_results/nf_c_lda_6_bench_valuation.md")
    args = ap.parse_args()

    result = run(seeds=args.seeds, slots=args.slots, contiguous=args.contiguous)
    text = report(result)
    problems = check_anchors(result)
    if problems:
        text += "\n\n## ⛔ ANCHOR FAILURES — the ranking above is NOT readable\n\n"
        text += "\n".join(f"* {p}" for p in problems)
    else:
        text += "\n\n✅ Anchors held: the peeking oracle is not beaten, the nihilist is last.\n"
    print(text)
    out = _REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(f"\nwrote {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
