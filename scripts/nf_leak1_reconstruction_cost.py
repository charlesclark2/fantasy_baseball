"""NF-LEAK1 Phase 0 — MEASURE the paid-stat reconstruction attack, before and after the levers.

⭐ WHY A MEASUREMENT SCRIPT AND NOT AN ARGUMENT. The NF-EPIC 1 audit §9 recorded this vector as
"~50 authenticated round trips" and bounded-not-closed. That figure was reasoned, never measured,
and this story is judged on how much the levers RAISE it — so the baseline has to be a number
somebody re-ran, against the REAL scorer (`app.backend.services.league_scoring`) and the REAL
published 858-player artifact, not a fixture that restates the assumption.

It runs THREE attacker models, because picking the cheapest one is the attacker's job, not ours:

  A. ISOLATION   — one config per stat, every other weight zero. `pts` IS the stat.
  B. DIFFERENCING — a realistic baseline config, then baseline+δ on one stat. `(pts_i − pts_0)/δ`.
                    This is the model that survives an "only plausible leagues" validator, which is
                    why an expressiveness constraint alone cannot close the leak.
  C. PACKING     — several stats in ONE config at separated magnitudes, decoded out of the single
                   returned `pts`. This is the model that a per-request budget alone does not bound,
                   because it changes the number of REQUESTS per stat rather than the cost per request.

Run:  uv run python scripts/nf_leak1_reconstruction_cost.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend.services import league_scoring, projection_fields  # noqa: E402

#: The published artifact the API serves from S3. Deliberately the REAL one — a synthetic can prove
#: a size but never a shape (NF-C0e / ESPN-PRUNER).
ARTIFACT = (
    REPO
    / "quant_sports_intel_models/football/nfl/fantasy/artifacts/player_history_json/2026/projections.json"
)

#: The authenticated per-IP ceiling in force today (`cost_guardrails.authenticated_policy`).
AUTH_SUSTAINED_PER_SECOND = 2.0

#: A realistic 12-team half-PPR-ish config — the baseline the DIFFERENCING attacker starts from, and
#: the shape any "reject implausible leagues" rule has to admit.
REALISTIC_SCORING: dict[str, float] = {
    "pass_yds": 0.04, "pass_td": 4.0, "pass_int": -2.0,
    "rush_yds": 0.1, "rush_td": 6.0,
    "rec": 0.5, "rec_yds": 0.1, "rec_td": 6.0,
    "fumbles_lost": -2.0, "two_pt": 2.0,
    "fg_made": 3.0, "fg_missed": -1.0, "pat_made": 1.0,
    "def_sacks": 1.0, "def_int": 2.0, "def_fumble_rec": 2.0, "def_td": 6.0,
    "def_safety": 2.0, "def_blocked_kick": 2.0, "st_td": 6.0,
}

ROSTER = [
    {"name": "QB", "count": 1, "eligible": ["QB"], "bench": False},
    {"name": "RB", "count": 2, "eligible": ["RB"], "bench": False},
    {"name": "WR", "count": 2, "eligible": ["WR"], "bench": False},
    {"name": "TE", "count": 1, "eligible": ["TE"], "bench": False},
    {"name": "FLEX", "count": 1, "eligible": ["RB", "WR", "TE"], "bench": False},
    {"name": "K", "count": 1, "eligible": ["K"], "bench": False},
    {"name": "DST", "count": 1, "eligible": ["DST"], "bench": False},
    {"name": "BN", "count": 6, "eligible": [], "bench": True},
]


def _cfg(scoring: dict[str, float]) -> dict:
    return {
        "name": "probe", "sport": "nfl", "n_teams": 12, "ppr": "custom",
        "scoring": {"per_stat": dict(scoring), "position_bonuses": {}},
        "roster": ROSTER,
    }


def _board(players: list[dict], scoring: dict[str, float]) -> dict[str, float]:
    """One server-side re-score, returned as `{player_id: pts}` — exactly what the wire carries."""
    board = league_scoring.build_board(players, _cfg(scoring), projection_fields.STAT_FIELD)
    return {str(r["id"]): float(r["pts"]) for r in board["players"]}


def _present_stats(players: list[dict]) -> list[str]:
    """Stat KEYS whose payload field carries at least one real number — the attacker's target set."""
    fields = league_scoring.available_fields(players)
    return sorted(k for k, f in projection_fields.STAT_FIELD.items() if f in fields)


def _truth(players: list[dict], stat: str) -> dict[str, float]:
    field = projection_fields.STAT_FIELD[stat]
    return {str(p.get("id")): float(p.get(field) or 0.0) for p in players}


def _accuracy(recovered: dict[str, float], truth: dict[str, float]) -> tuple[float, int]:
    """`(max_abs_error, n_compared)` over the players the board actually ranked."""
    worst, n = 0.0, 0
    for pid, got in recovered.items():
        want = truth.get(pid)
        if want is None:
            continue
        worst = max(worst, abs(got - want))
        n += 1
    return worst, n


# ── Model A — isolation ──────────────────────────────────────────────────────────────────────────

def model_a_isolation(players: list[dict], stats: list[str]) -> dict:
    worst = 0.0
    for stat in stats:
        rec = _board(players, {stat: 1.0})
        e, _ = _accuracy(rec, _truth(players, stat))
        worst = max(worst, e)
    return {
        "model": "A · isolation (all-but-one weight zero)",
        "writes": len(stats), "reads": len(stats), "stats_per_config": 1.0,
        "max_abs_error": worst,
    }


# ── Model B — differencing off a realistic baseline ───────────────────────────────────────────────

def model_b_differencing(players: list[dict], stats: list[str], delta: float = 1.0) -> dict:
    base = _board(players, REALISTIC_SCORING)
    worst = 0.0
    for stat in stats:
        scoring = dict(REALISTIC_SCORING)
        scoring[stat] = scoring.get(stat, 0.0) + delta
        probe = _board(players, scoring)
        rec = {pid: (probe[pid] - base[pid]) / delta for pid in probe if pid in base}
        e, _ = _accuracy(rec, _truth(players, stat))
        worst = max(worst, e)
    return {
        "model": f"B · differencing off a realistic baseline (δ={delta})",
        "writes": len(stats) + 1, "reads": len(stats) + 1, "stats_per_config": 1.0,
        "max_abs_error": worst,
    }


# ── Model C — magnitude packing ───────────────────────────────────────────────────────────────────

#: The largest weight `LeagueSave._scoring_nonempty` admits today.
WEIGHT_BOUND = 1000.0

#: The board's own output granularity — `_round1`. This is the LOW-end wall on packing.
PTS_GRANULARITY = 0.1


def _pack_weights(players: list[dict], stats: list[str], max_ratio: float) -> list[dict[str, float]]:
    """Greedily pack stats into as few configs as possible, positionally by magnitude.

    The encoding is `pts = Σ w_j·x_j` with each place separated enough that the decoder can peel the
    top place off without the places below it carrying. Two walls bound how many stats fit:

      • the LOW end — the board rounds `pts` to 1dp, so the bottom place needs `w ≥ 1` for a stat's
        own 0.1 granularity to survive the round trip;
      • the HIGH end — the weight DYNAMIC RANGE a config may express. Today that is
        `WEIGHT_BOUND / 1 = 1000` (three decades). `max_ratio` is exactly the quantity the
        NF-LEAK1 dynamic-range lever moves, which is why it is a parameter and not a constant.

    A place needs `w_next ≥ w_cur · 20·x_max` to be separable, so a big-magnitude stat (pass_yds,
    ~4.7k) eats five decades on its own and a small one (safety, ~1.5) eats under two — which is why
    packing pays on the DST/kicker tail and not on the volume stats.
    """
    # SMALLEST-RANGE FIRST — the attacker's best play, so the measurement reports their cheapest
    # path rather than a convenient one. Small stats (safety, 2pt, blocked kicks) share a config;
    # the volume stats each need most of the available range to themselves.
    by_span = sorted(
        stats,
        key=lambda s: max((abs(v) for v in _truth(players, s).values()), default=0.0),
    )
    configs: list[dict[str, float]] = []
    current: dict[str, float] = {}
    weight = 1.0
    for stat in by_span:
        vals = [abs(v) for v in _truth(players, stat).values()]
        x_max = max(vals) if vals else 0.0
        if current and weight > max_ratio:
            configs.append(current)
            current, weight = {}, 1.0
        current[stat] = weight
        # the next place must clear this one's whole range with room for the 0.05 decode margin
        weight *= 10 ** math.ceil(math.log10(max(20.0 * x_max, 10.0)))
    if current:
        configs.append(current)
    return configs


def model_c_packing(players: list[dict], stats: list[str], max_ratio: float = WEIGHT_BOUND) -> dict:
    """Pack many stats per config; verify every packed stat decodes EXACTLY off the served `pts`."""
    configs = _pack_weights(players, stats, max_ratio)
    worst, packed, cells, exact = 0.0, 0, 0, 0
    for weights in configs:
        scored = _board(players, weights)
        places = sorted(weights.items(), key=lambda kv: -kv[1])
        truths = {s: _truth(players, s) for s in weights}
        packed += len(weights)
        for pid, total in scored.items():
            remaining = total
            for stat, w in places:
                got = round(remaining / w, 1)
                remaining -= got * w
                want = truths[stat].get(pid)
                if want is None:
                    continue
                cells += 1
                err = abs(got - want)
                exact += err <= 0.051
                worst = max(worst, err)
    per_config = packed / len(configs) if configs else 1.0
    return {
        "model": f"C · magnitude packing ({per_config:.1f} stats/config, weight ratio ≤ {max_ratio:g})",
        "writes": len(configs), "reads": len(configs), "stats_per_config": per_config,
        "max_abs_error": worst,
        "recovered_share": (exact / cells) if cells else 0.0,
    }


# ── AFTER — what the NF-LEAK1 levers do to each model ────────────────────────────────────────────


def _wrap(scoring: dict[str, float]) -> dict:
    return {"scoring": {"per_stat": dict(scoring), "position_bonuses": {}}}


def admissible_attack_plan(players: list[dict], stats: list[str], guard) -> tuple[int, float, float]:
    """The attacker's best SURVIVING plan: cover EVERY stat in as few admissible changes as possible.

    ⭐ COVER ALL 38, DO NOT EXTRAPOLATE FROM THE EASIEST THREE. An earlier cut measured the deepest
    single pack (3 stats) and divided — which silently assumed every stat packs as well as the three
    smallest do. They do not: `pass_yds` spans ~4,700 and eats the whole admissible window on its
    own, while `safety` spans ~2 and shares. Dividing by the best case over-credits the attacker and
    would have driven the budget tuning off a number the attacker cannot actually achieve.

    Greedy, verified group by group: open a group, keep adding the next stat at a separated weight
    while the config still passes the REAL `shape_violations` AND the whole group still decodes
    exactly out of the difference against the flat-core baseline. Returns
    `(n_changes, mean_stats_per_change, exact_share)`.
    """
    by_span = sorted(
        stats, key=lambda s: max((abs(v) for v in _truth(players, s).values()), default=0.0)
    )
    flat_core = {s: 1.0 for s in guard.CORE_STATS}
    base_board = _board(players, flat_core)

    def decode_ok(weights: dict[str, float]) -> tuple[bool, int, int]:
        if guard.shape_violations(_wrap({**flat_core, **weights})):
            return False, 0, 0
        probe = _board(players, {**flat_core, **weights})
        places = sorted(weights.items(), key=lambda kv: -kv[1])
        truths = {s: _truth(players, s) for s in weights}
        cells = exact = 0
        for pid, total in probe.items():
            remaining = total - base_board.get(pid, 0.0)
            for stat, weight in places:
                got = round(remaining / weight, 1)
                remaining -= got * weight
                want = truths[stat].get(pid)
                if want is None:
                    continue
                cells += 1
                exact += abs(got - want) <= 0.051
        return (exact / cells if cells else 0.0) >= 0.999, cells, exact

    groups: list[dict[str, float]] = []
    cells_tot = exact_tot = 0
    pending = list(by_span)
    while pending:
        weights: dict[str, float] = {}
        w = 1.0
        last_ok: dict[str, float] | None = None
        while pending:
            stat = pending[0]
            x_max = max((abs(v) for v in _truth(players, stat).values()), default=0.0)
            trial = {**weights, stat: w}
            ok, _c, _e = decode_ok(trial)
            if not ok and weights:
                break                      # this group is full; start a new one
            weights = trial
            last_ok = trial if ok else last_ok
            pending.pop(0)
            w *= max(20.0 * x_max, 10.0)
            if not ok:
                break                      # a lone stat that will not decode still costs its change
        final = last_ok if last_ok is not None else weights
        _ok, c, e = decode_ok(final)
        cells_tot += c
        exact_tot += e
        groups.append(final)

    n_changes = len(groups) + 1  # the flat-core baseline is itself one change
    per = len(stats) / len(groups) if groups else 1.0
    return n_changes, per, (exact_tot / cells_tot if cells_tot else 0.0)


def best_admissible_pack(players: list[dict], stats: list[str], guard) -> tuple[int, float]:
    """SEARCH for the most stats an ADMISSIBLE config can still leak per round trip.

    ⭐ A SEARCH, NOT A DERIVATION. The shape rules interact (the core-stat requirement forces
    big-range quantities into the score, and the ratio cap then bounds how far a packed place can be
    pushed away from them), and the composition is exactly the kind of thing that reads as airtight
    and measures as leaky. So this constructs the attacker's best play and scores it:

      • a baseline whose core weights are FLATTENED to 1.0 — the attacker's move, since it buys the
        widest admissible window between the smallest and largest weight in the config;
      • k target stats added at geometrically separated weights inside that window;
      • both configs run through the REAL `shape_violations`, then the REAL scorer, then decoded out
        of the DIFFERENCE (which cancels the core contribution the attacker cannot otherwise remove).

    Returns `(k, exact_share)` for the largest k that still recovers ≥99% of cells exactly.
    """
    by_span = sorted(
        stats, key=lambda s: max((abs(v) for v in _truth(players, s).values()), default=0.0)
    )
    flat_core = {s: 1.0 for s in guard.CORE_STATS}
    base_board = _board(players, flat_core)
    best = (1, 1.0)

    for k in range(2, 6):
        targets = by_span[:k]
        weights, w = {}, 1.0
        for stat in targets:
            x_max = max((abs(v) for v in _truth(players, stat).values()), default=0.0)
            weights[stat] = w
            w *= max(20.0 * x_max, 10.0)
        probe_cfg = {**flat_core, **weights}
        if guard.shape_violations(_wrap(probe_cfg)):
            break  # the window is spent — no admissible config packs this deep
        probe_board = _board(players, probe_cfg)
        places = sorted(weights.items(), key=lambda kv: -kv[1])
        truths = {s: _truth(players, s) for s in targets}
        cells = exact = 0
        for pid, total in probe_board.items():
            remaining = total - base_board.get(pid, 0.0)
            for stat, weight in places:
                got = round(remaining / weight, 1)
                remaining -= got * weight
                want = truths[stat].get(pid)
                if want is None:
                    continue
                cells += 1
                exact += abs(got - want) <= 0.051
        share = (exact / cells) if cells else 0.0
        if share < 0.99:
            break
        best = (k, share)
    return best


def after_state(players: list[dict], stats: list[str]) -> dict:
    """Re-price every attacker model against the shipped guard, and the guard against real leagues.

    TWO-SIDED ON PURPOSE. A refusal rule is only as good as the population it does NOT refuse, so the
    same call that measures the attack also runs every shipped preset and every real imported-league
    fixture through `shape_violations` — a false refusal there is a broken product, not a win.
    """
    from app.backend.services import scoring_probe_guard as guard

    # 1. which attacker models survive the shape rules
    survives: dict[str, bool] = {
        "A": not guard.shape_violations(_wrap({stats[0]: 1.0})),
        "B": not guard.shape_violations(
            _wrap({**REALISTIC_SCORING, stats[0]: REALISTIC_SCORING.get(stats[0], 0.0) + 1.0})
        ),
        "C": any(
            not guard.shape_violations(_wrap(w))
            for w in _pack_weights(players, stats, WEIGHT_BOUND)
            if len(w) > 1
        ),
    }

    # 2/3. the attacker's best SURVIVING plan, covering every stat — searched, not derived
    pack_k, _share = best_admissible_pack(players, stats, guard)
    n_changes, pack_per, pack_share = admissible_attack_plan(players, stats, guard)
    burst, refill = guard.BUDGET_BURST, guard.BUDGET_REFILL_PER_DAY
    floor_days = max(0.0, (n_changes - burst)) / refill
    surcharged = burst + guard.PROBE_SURCHARGE * max(0.0, n_changes - burst)
    detected_days = max(0.0, (surcharged - burst)) / refill

    # 4. the false-refusal check — every REAL config must pass
    real: list[tuple[str, list[str]]] = []
    sys.path.insert(0, str(REPO))
    from quant_sports_intel_models.football.nfl.fantasy import league_presets as lp

    for name in lp.PRESETS:
        real.append((f"preset:{name}", guard.shape_violations(lp.get_preset(name).to_dict())))
    for path in sorted((REPO / "frontend/e2e/fixtures/api").glob("fantasy-import-*.json")):
        for cfg in _fixture_configs(json.loads(path.read_text())):
            real.append((f"fixture:{path.name[:44]}", guard.shape_violations(cfg)))

    return {
        "survives": survives, "pack_k": pack_k, "pack_share": pack_share, "pack_per": pack_per,
        "n_changes": n_changes, "floor_days": floor_days, "detected_days": detected_days,
        "real": real,
    }


def _fixture_configs(obj, out=None) -> list[dict]:
    """Every `{scoring: {per_stat: …}}` config nested anywhere in a captured fixture."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        scoring = obj.get("scoring")
        if isinstance(scoring, dict) and isinstance(scoring.get("per_stat"), dict):
            out.append(obj)
        for v in obj.values():
            _fixture_configs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _fixture_configs(v, out)
    return out


def main() -> int:
    data = json.loads(ARTIFACT.read_text())
    players = data.get("players") or []
    stats = _present_stats(players)

    print("═" * 99)
    print("NF-LEAK1 · Phase 0 — measured cost of reconstructing the PAID per-stat line")
    print("═" * 99)
    print(f"artifact           {ARTIFACT.relative_to(REPO)}")
    print(f"players scored     {len(players)}")
    print(f"scorable stats     {len(projection_fields.STAT_FIELD)} declared · "
          f"{len(stats)} carry data in this artifact (the attacker's real target set)")
    print(f"per-IP ceiling     {AUTH_SUSTAINED_PER_SECOND}/s sustained (authenticated_policy)")
    print()

    results = [
        model_a_isolation(players, stats),
        model_b_differencing(players, stats),
        model_c_packing(players, stats),
    ]

    print(f"{'attacker model':<62}{'writes':>8}{'reads':>8}{'wall-clock':>18}")
    print("─" * 99)
    for r in results:
        rt = r["writes"] + r["reads"]
        secs = rt / AUTH_SUSTAINED_PER_SECOND
        print(f"{r['model']:<62}{r['writes']:>8}{r['reads']:>8}{_dur(secs):>18}")
    print("─" * 99)
    for r in results:
        share = r.get("recovered_share")
        tail = f" · cells recovered exactly: {share:.4%}" if share is not None else ""
        print(f"  {r['model'][:1]} · worst recovery error over all players: "
              f"{r['max_abs_error']:.4f} (the board rounds pts to 1dp){tail}")
    print()
    cheapest = min(results, key=lambda r: r["writes"] + r["reads"])
    rt = cheapest["writes"] + cheapest["reads"]
    print(f"⇒ CHEAPEST PATH BEFORE NF-LEAK1: {cheapest['model']}")
    print(f"   {rt} round trips · {_dur(rt / AUTH_SUSTAINED_PER_SECOND)} at the per-IP ceiling")
    print("   ALL positions at once — one board scores every player, so there is no per-position cost.")

    # ── AFTER ────────────────────────────────────────────────────────────────────────────────────
    a = after_state(players, stats)
    print()
    print("═" * 99)
    print("AFTER — the NF-LEAK1 levers")
    print("═" * 99)
    for key, label in (("A", "isolation"), ("B", "differencing"), ("C", "packing")):
        state = "ADMITTED" if a["survives"][key] else "REFUSED at write time (shape rules)"
        print(f"  model {key} · {label:<14} {state}")
    print(f"  deepest ADMISSIBLE pack (searched):   {a['pack_k']} stats — but only for the "
          f"smallest-range stats")
    print(f"  full-coverage plan (all {len(stats)} stats):  {a['pack_per']:.2f} stats/change "
          f"at {a['pack_share']:.2%} exact — was {results[2]['stats_per_config']:.2f}")
    print()
    print(f"  surviving cheapest path: {a['n_changes']} scoring CHANGES "
          f"(a baseline plus one admissible variant per group)")
    print(f"  budget floor  (detector evaded): {a['floor_days']:.1f} days")
    print(f"  with surcharge (detector fires): {a['detected_days']:.1f} days")
    print(f"  pre-registered gate: ≥ 14 days   ⇒ "
          f"{'MET' if a['floor_days'] >= 14 else 'NOT MET'} on the floor alone")
    print()
    refused = [(n, p) for n, p in a["real"] if p]
    print(f"  false-refusal check: {len(a['real'])} REAL configs "
          f"(8 shipped presets + every captured import fixture)")
    if refused:
        print("  ⛔ THESE REAL CONFIGS WOULD BE REFUSED — the rule is wrong, not the league:")
        for name, problems in refused:
            print(f"     {name}: {'; '.join(problems)}")
        return 1
    print("  ✅ every real config still saves — the rules refuse probes, not leagues")
    print()
    print("  ⚠️ RESIDUAL, NOT CLOSED: signup is free and self-serve, so 38 fresh accounts buy the")
    print("     same reconstruction in one pass. Bounded by the per-IP limiter and email OTP, and")
    print("     every probe is attributable to a Cognito sub — but it is a cost, not a wall.")
    return 0


def _dur(secs: float) -> str:
    if secs < 90:
        return f"{secs:.0f}s"
    if secs < 5400:
        return f"{secs / 60:.1f} min"
    if secs < 172800:
        return f"{secs / 3600:.1f} h"
    return f"{secs / 86400:.1f} days"


if __name__ == "__main__":
    raise SystemExit(main())
