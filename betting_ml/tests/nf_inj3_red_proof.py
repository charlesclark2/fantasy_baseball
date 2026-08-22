"""nf_inj3_red_proof.py — prove every NF-INJ3 guard actually FAILS on deliberately-broken source.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / NF-D17). This harness applies ONE
break at a time and asserts the named test goes RED.

Three failure modes of a RED proof itself are guarded against, because all three have shipped a
FALSE result in this repo before:
  · #682 — the mutation silently NO-OPS ⇒ assert the file CHANGED on disk;
  · #815 — it lands but does not move the asserted predicate ⇒ assert the token is GONE afterwards;
  · E11.24 — it lands on the WRONG symbol ⇒ assert the anchor is UNIQUE in the file before applying.
Backups are restored AT START-UP as well as in `finally`, because this harness's own worst case is
being killed mid-mutation (E11.26).

RUN:  uv run python betting_ml/tests/nf_inj3_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "quant_sports_intel_models/football/nfl/fantasy/nf_inj3_injury_games.py"
RUN = ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_nf_inj3_injury_games.py"
TESTS = "betting_ml/tests/test_nf_inj3_injury_games.py"

BREAKS: list[tuple[str, Path, str, str, str]] = [
    ("incumbent re-implements the blend instead of delegating", MOD,
     "    return SP.injury_availability_games(df, blend=blend)",
     "    cap = df['proj_status'].map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)\n"
     "    eg = df['proj_games'].to_numpy(dtype=float)\n"
     "    import numpy as _np\n"
     "    return _np.where(_np.isfinite(cap), (1-blend)*eg + blend*_np.minimum(eg, cap), eg)",
     "TestIncumbentIsTheShippedMap::test_incumbent_arm_delegates_to_season_projection"),

    ("the pre-cap inversion loses its branch (no longer a bijection)", MOD,
     "    eg[hi] = (g[hi] - blend * cap[hi]) / (1.0 - blend)",
     "    eg[hi] = g[hi]",
     "TestIncumbentIsTheShippedMap::test_recovering_the_pre_cap_games_round_trips_exactly"),

    ("CRPS degrades to a 5-point quantile grid (the NF-W4 tie)", MOD,
     "    f = np.cumsum(np.asarray(pmf, dtype=float), axis=1)",
     "    f = np.round(np.cumsum(np.asarray(pmf, dtype=float), axis=1) * 5.0) / 5.0",
     "TestMetricIsNotInverted::test_two_means_a_hair_apart_do_not_tie"),

    ("PBO is fed RAW CRPS, ranking the field upside down", RUN,
     '    mat = np.array([[-f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)',
     '    mat = np.array([[f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)',
     "TestDeflationWiring::test_pbo_is_computed_on_negated_crps"),

    ("the MH2.1(a) diagnostic is marked ACTIONABLE (licensing a post-hoc re-read)", RUN,
     '        "admissible_to_act_on": False,',
     '        "admissible_to_act_on": True,',
     "TestDeflationWiring::test_the_mh2_1a_diagnostic_is_marked_inadmissible"),

    ("the winner-deletion refusal is removed (NF-W7h)", RUN,
     "    if far == winner:",
     "    if False:",
     "TestDeflationWiring::test_a_dsr_reached_by_deleting_the_winner_is_refused"),

    ("the matched foil quietly keeps a timing column", MOD,
     '        f = BASE_FEATURES\n        return predict_glm_mean',
     '        f = ("onset_carryover", *BASE_FEATURES)\n        return predict_glm_mean',
     "TestMatchedFoil::test_the_foil_strips_exactly_the_timing_columns_and_nothing_else"),

    ("a too-thin in-fold history silently no-ops instead of raising", MOD,
     "    if len(train) < MIN_FIT_N:\n        raise ValueError(",
     "    if False:\n        raise ValueError(",
     "TestFailsLoudly::test_a_too_thin_in_fold_history_raises"),

    ("a thin status cell falls back SILENTLY", MOD,
     '            prov[s] = {"n": int(len(cell)), "used_fallback": True,',
     '            prov[s] = {"n": int(len(cell)), "used_fallback": False,',
     "TestFailsLoudly::test_a_thin_status_cell_records_its_fallback_rather_than_hiding_it"),

    ("a missing own-form oracle is scored as a PASS", RUN,
     '            out[a] = {"evaluable": False,',
     '            out[a] = {"evaluable": True, "respects_oracle": True,',
     "TestFailsLoudly::test_a_missing_own_form_oracle_is_recorded_as_NOT_evaluable"),

    ("a missing artifacts dir degrades to an empty population", RUN,
     "    if not p.is_dir():\n        raise FileNotFoundError(",
     "    if False:\n        raise FileNotFoundError(",
     "TestFailsLoudly::test_a_missing_artifacts_dir_raises_rather_than_returning_an_empty_population"),

    ("the permutation anchor becomes a no-op", MOD,
     "        perm = rng.permutation(len(ix))",
     "        perm = np.arange(len(ix))",
     "TestPermutationAnchor::test_it_actually_changes_the_linkage"),

    ("the 'never played' sentinel becomes fillna(0) — reads as 'just played'", RUN,
     '.fillna(weeks.max() if weeks.notna().any()\n                                                               else 18.0)',
     ".fillna(0.0)",
     "TestPopulation::test_no_prior_game_means_the_LONGEST_absence_not_a_missing_one"),

    ("the matched foil is promoted into the shippable field", MOD,
     '    "no_cap",           # DEGENERATE\n)',
     '    "no_cap",           # DEGENERATE\n    "timing_aware_minus_timing",\n)',
     "TestMatchedFoil::test_the_foil_is_not_shippable"),
]


def _restore(bak: Path, tgt: Path) -> None:
    if bak.exists():
        tgt.write_text(bak.read_text())
        bak.unlink()


def main() -> int:
    for f in (MOD, RUN):                       # E11.26: restore a stale backup AT START-UP
        _restore(f.with_suffix(f.suffix + ".redbak"), f)
    red = 0
    for i, (name, target, old, new, test) in enumerate(BREAKS, 1):
        src = target.read_text()
        if src.count(old) != 1:                # E11.24: the anchor must be UNIQUE
            print(f"{i:2d}. ⚠️  SKIP (anchor not unique: {src.count(old)}×) — {name}")
            continue
        bak = target.with_suffix(target.suffix + ".redbak")
        bak.write_text(src)
        try:
            target.write_text(src.replace(old, new, 1))
            after = target.read_text()
            assert after != src, "#682: the mutation did not LAND"
            assert old not in after, "#815: the mutation landed but the token survived"
            r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{test}", "-q",
                                "--no-header", "-p", "no:cacheprovider"],
                               cwd=ROOT, capture_output=True, text=True)
            ok = r.returncode != 0
            red += ok
            print(f"{i:2d}. {'✅ RED' if ok else '❌ STAYED GREEN'} — {name}")
            if not ok:
                print("     ⚠️ VACUOUS GUARD:", r.stdout.strip().splitlines()[-1:])
        finally:
            _restore(bak, target)
    print(f"\n{red}/{len(BREAKS)} breaks went RED")
    return 0 if red == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
