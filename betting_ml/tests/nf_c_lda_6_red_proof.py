"""RED proof for the NF-C-LDA-6 study guards —
`uv run python betting_ml/tests/nf_c_lda_6_red_proof.py`.

⭐ WHY A RESEARCH HARNESS GETS A RED PROOF AT ALL. The study ships no code; its only output is a
VERDICT, and the anchors are the whole of what makes that verdict readable. During the build they
caught two real defects that each produced a confident, wrong leaderboard — an INACTIVE peeking
oracle that scored byte-identically to an honest arm, and a unit mismatch that let a bench pick
outrank a need-filler. A detector with that hit rate is worth proving can still fail.

Same harness contract as `nf_k1_red_proof.py` / `nf_c_lda_1_roster_red_proof.py`: mutation asserted
to LAND (#682), asserted-token GONE where relevant (#815), anchor asserted UNIQUE (prediction_log),
pytest in a SUBPROCESS (NF-W6c), and ONLY exit code 1 counts as RED (NF-INFRA1).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_c_lda_6_bench_valuation.py"
_S = "quant_sports_intel_models/fantasy_engine/bench_valuation_study.py"

BREAKS = [
    ("anchors: stop checking the oracle floor", _S,
     "    if means[\"oracle\"] < means[best_real]:",
     "    if False:",
     "beating_the_peeking_oracle", None),
    ("anchors: stop checking the degenerate ceiling", _S,
     "    if means[\"nihilist\"] >= means[worst_real]:",
     "    if False:",
     "nihilist_that_is_not_last", None),
    ("anchors: stop checking whether the instrument can see anything", _S,
     "    if spread < 1.0:",
     "    if False:",
     "cannot_be_told_apart", None),
    # ⛔ DELIBERATELY NOT A BREAK: widening `best_real` from the real arms to the whole field is
    # BEHAVIOURALLY EQUIVALENT for this check — if the oracle is the maximum both versions report
    # nothing, and if a real arm beats it both report the breach. It was written as a break, came
    # back GREEN, and the GREEN was correct. Recorded rather than deleted, because "the guard did
    # not catch it" and "there was nothing to catch" look identical in a red-proof log.
    ("anchors: let a missing arm pass silently instead of raising", _S,
     "    means = {a: statistics.mean(v) for a, v in arms.items()}",
     "    means = {a: statistics.mean(v) for a, v in arms.items()}\n"
     "    means = {**{k: 0.0 for k in ('oracle', 'nihilist')}, **means}",
     "names_every_arm_it_scores", None),

    ("metric: score the best nine, so bench depth is worth nothing by construction", _S,
     "    for week in range(1, WEEKS + 1):\n"
     "        avail = [\n"
     "            p for p in roster\n"
     "            if p.get(\"bye\") != week and week not in absences.get(str(p[\"player_id\"]), ())\n"
     "        ]\n"
     "        total += _fill_lineup(avail, cfg)",
     "    for week in range(1, WEEKS + 1):\n"
     "        total += _fill_lineup(roster, cfg)",
     "rewards_a_bench_that_covers_absence", None),
    ("availability: ignore the board's projected games, everyone plays every week", _S,
     "            miss_p = max(0.0, min(1.0, misses / 17.0))",
     "            miss_p = 0.0",
     "tracks_the_boards_own_projected_games or rewards_a_bench", None),
    ("CRN: reseed from entropy, so two arms see different seasons", _S,
     "def draw_absences(rows: list[dict], rng: random.Random, contiguous: bool = False) -> dict[str, set[int]]:",
     "def draw_absences(rows: list[dict], rng: random.Random, contiguous: bool = False) -> dict[str, set[int]]:\n"
     "    import random as _r; rng = _r.Random()",
     "same_seed_produces_the_same_season", None),
    ("contiguous mode: silently fall back to independent draws", _S,
     "        if not contiguous:",
     "        if True:",
     "contiguous_absence_is_one_block", None),
    ("bench classification: go back to counting the last picks as the bench", _S,
     "def _bench_of(roster: list[dict], cfg: LeagueConfig) -> list[dict]:",
     "def _bench_of(roster: list[dict], cfg: LeagueConfig) -> list[dict]:\n"
     "    return roster[9:]\n"
     "def _unused(roster, cfg):",
     "classified_by_slot_not_by_draft_order", None),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        n = original.count(old)
        if n == 0:
            print(f"{'BROKEN ❌ (anchor not found)':34} {name}")
            failures.append(f"{name}: anchor not found")
            continue
        if n > 1:
            print(f"{'BROKEN ❌ (anchor not unique)':34} {name} -> {n}x")
            failures.append(f"{name}: anchor appears {n}x")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name
        if gone is not None and gone in mutated:
            print(f"{'BROKEN ❌ (token survives)':34} {name}")
            failures.append(f"{name}: token survived")
            continue
        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: rc={proc.returncode}")
            print(f"{verdict:34} {name}\n{'':34} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every study guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
