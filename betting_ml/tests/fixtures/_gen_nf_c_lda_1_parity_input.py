import json, sys, random
sys.path.insert(0, '.')
from app.backend.services import league_scoring as LS, projection_fields as PF
from quant_sports_intel_models.football.nfl.fantasy.league_presets import full_ppr

# ⭐ A REAL board, built by the SHIPPED server-side builder from the SHIPPED 2026 projections —
# not a synthetic frame. The optimizer's behaviour depends on the actual shape of each position's
# pool (cliffs, pool depth, replacement spread), and a hand-made board cannot reproduce that.
players = json.loads(open('quant_sports_intel_models/football/nfl/fantasy/artifacts/'
                          'player_history_json/2026/projections.json').read())["players"]
cfg = full_ppr(12).to_dict()
built = LS.build_board(players, cfg, PF.STAT_FIELD)

# Only the fields the optimizer's own `Player` interface declares — the fixture is the ENGINE'S
# INPUT, so carrying the other ~40 projection columns would just make it big and imply they matter.
KEEP = ("id", "name", "pos", "team", "bye", "rookie", "g", "pts", "repl", "vor",
        "posRank", "ovrRank", "vorP10", "vorP90", "adp", "lowPred")
board = [{k: p.get(k) for k in KEEP} for p in built["players"]]
ids = [p["id"] for p in board]

# Draft states chosen to EXERCISE each mechanism rather than to be tidy: an untouched board, an
# early roster, a mid draft, a flex-only roster (the NF-C2.1 seat re-basing), a nearly-full roster
# (the reserve constraint + K/DST deferral), plus 30 pseudo-random states so the guard is not
# limited to the cases whose answers were already known.
scenarios = {
    "empty_board": {"drafted": [], "mine": []},
    "early": {"drafted": ids[:5], "mine": [ids[1]]},
    "mid_draft": {"drafted": ids[:30], "mine": [ids[0], ids[7], ids[18]]},
    "flex_seat": {"drafted": ids[:60], "mine": [ids[2], ids[5], ids[9], ids[20], ids[33]]},
    "deep": {"drafted": ids[:140], "mine": ids[3:15:2]},
    "top_n_20": {"drafted": ids[:30], "mine": [ids[0], ids[7]], "topN": 20},
    # ⭐ A DEEP top-N, AND IT EXISTS BECAUSE THE ANTI-VACUITY CLAUSE FOUND A HOLE. Every entry in a
    # top-8 panel is its position's best available player, so all eight are tier 1 BY CONSTRUCTION
    # — the NF-D19 tier-SIZING mechanism (merge undersized groups, split oversized ones) was one of
    # the two drifts this guard exists to catch and the fixture did not reach it at all. A deep
    # request walks far enough down each position to cross real tier boundaries.
    "deep_top_n": {"drafted": ids[:24], "mine": [ids[1], ids[9]], "topN": 120},
    "deep_top_n_late": {"drafted": ids[:110], "mine": ids[2:14:2], "topN": 120},
    # ⭐ NF-C7 DEPTH TARGETS. Without a state that SETS one, the parity guard would agree on the
    # feature by never reaching it — the vacuous-guard class (NF1.7(a)), and the anti-vacuity clause
    # in the test asserts a non-zero `depthBonus` exists somewhere in the fixture for exactly that
    # reason. Three states, because the mechanism has three distinct behaviours to pin:
    #   · `depth_target_mid`   — targets ABOVE what the roster holds, mid-draft, so the bonus fires;
    #   · `depth_target_met`   — the SAME roster with targets it already MEETS, so it must NOT fire
    #     (an "on" state alone cannot tell a working gate from one that always pays);
    #   · `depth_target_reserve` — a nearly-full roster where the RESERVE CONSTRAINT binds, with a
    #     huge K/DST target. It pins the load-bearing guard: a preference must never outrank a slot
    #     the lineup requires, and must never lift a deferred K/DST above a real candidate.
    "depth_target_mid": {"drafted": ids[:110], "mine": ids[2:14:2], "topN": 30,
                         "depthTargets": {"QB": 2, "RB": 6, "WR": 6, "TE": 2}},
    "depth_target_met": {"drafted": ids[:110], "mine": ids[2:14:2], "topN": 30,
                         "depthTargets": {"QB": 0, "RB": 1, "WR": 1, "TE": 0}},
    # ⭐ NF-C7c — the CAP half. `depth_target_met` above sets targets of 0/1/1/0, which the engine
    # reads as "no target" for QB/TE, so it exercises the SHORT and NEUTRAL tiers and never reaches
    # SATISFIED. This one sets a target the roster has already MET at every position, which is the
    # only state that produces `depthTier = 1` — without it the cap is agreed on by never being run
    # (the vacuous-guard class), and the parity test's non-vacuity clause asserts a satisfied tier
    # exists somewhere in this fixture for exactly that reason.
    "depth_target_capped": {"drafted": ids[:110], "mine": ids[2:14:2], "topN": 30,
                            "depthTargets": {"QB": 1, "RB": 1, "WR": 1, "TE": 1}},
    "depth_target_reserve": {"drafted": ids[:150], "mine": ids[1:27:2], "topN": 20,
                             "depthTargets": {"QB": 4, "TE": 4, "K": 5, "DST": 5}},
}
random.seed(20260819)
for t in range(30):
    n_drafted = random.randint(0, 150)
    pool = ids[: max(n_drafted + 40, 60)]
    drafted = random.sample(pool, min(n_drafted, len(pool)))
    mine = random.sample(drafted, min(len(drafted), random.randint(0, 13))) if drafted else []
    scenarios[f"rand{t:02d}"] = {"drafted": sorted(drafted), "mine": sorted(mine)}

out = {
    "_note": "Generated by betting_ml/tests/fixtures/_gen_nf_c_lda_1_parity_input.py — real 2026 "
             "board through league_scoring.build_board(full_ppr, 12).",
    "config": cfg,
    "replacement": built["replacement"],
    "board": board,
    "scenarios": scenarios,
}
path = "betting_ml/tests/fixtures/nf_c_lda_1_optimizer_parity_input.json"
open(path, "w").write(json.dumps(out, separators=(",", ":")) + "\n")
print(f"wrote {path}: {len(board)} board rows, {len(scenarios)} scenarios")
