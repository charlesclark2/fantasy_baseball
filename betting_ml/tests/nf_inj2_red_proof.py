"""nf_inj2_red_proof.py — prove every NF-INJ2 guard can actually FAIL (⛔ NOT a pytest module).

A guard that cannot go red is not a guard (NF1.7 (a); INC-38; NF-D17). This harness applies ONE
deliberate break to the source at a time, runs the clause that names it, and reports whether that
clause turned red. A clause that stays GREEN on its own break is VACUOUS and must be rewritten.

⚠️ FOUR WAYS A RED PROOF LIES, all recorded in this repo and all guarded against here:
  1. **THE MUTATION NEVER LANDS** (#682) — a quoting or match failure leaves the source unchanged and
     "the guard caught it" is indistinguishable from "the break never happened". ⇒ mutations are
     applied IN-PROCESS and the file is asserted to have CHANGED.
  2. **THE ANCHOR IS NOT UNIQUE** (#939) — a single-occurrence replace lands on the WRONG symbol and
     the run reports a FALSE VACUITY, the dangerous direction (it invites weakening a correct guard).
     ⇒ every anchor is asserted to occur EXACTLY ONCE.
  3. **THE MUTATION LANDS BUT DOES NOT MOVE THE ASSERTED PREDICATE** (#815) — e.g. a rename an
     `x in src` clause still matches. ⇒ each break names the token it removes, asserted GONE after.
  4. **THE PROOF LIVES IN NO WORKFLOW** (E9.64) — a mutation suite nobody runs decays silently. ⇒ it
     is a plain script the closeout runs, and its RED count is recorded in the story report.

⚠️ AND THIS FILE'S OWN WORST CASE: it mutates TRACKED source, so being killed mid-mutation would
leave the tree broken. Backups are restored AT START-UP as well as in `finally`, and it runs under
the PROJECT interpreter (a bare `python3` with no pytest would make a missing-pytest exit read as a
false RED — NF-INFRA1).

    uv run python betting_ml/tests/nf_inj2_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FANTASY = ROOT / "quant_sports_intel_models/football/nfl/fantasy"
RP = FANTASY / "nf_inj2_rate_permutation.py"
PC = FANTASY / "projection_coherence.py"
M1 = FANTASY / "nf1_model.py"
TESTS = "betting_ml/tests/test_nf_inj2_rate_permutation.py"


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    #: the substring that must be GONE after the mutation — defeats lie #3
    gone: str
    tests: tuple[str, ...]


BREAKS: tuple[Break, ...] = (
    Break("rate_permute re-multiplies by the POSITION MEAN games — i.e. it silently BECOMES the "
          "matched foil, which is the one change that would make the foil unable to attribute "
          "anything",
          RP,
          "                multiplier = gsafe[order]          # ⭐ the row's OWN games — never permuted",
          "                multiplier = np.full(len(order), float(np.nanmean(gsafe[idx])))",
          gone="multiplier = gsafe[order]",
          tests=("test_rate_permute_never_moves_a_rows_expected_games",
                 "test_the_matched_foil_differs_from_the_primary_in_exactly_one_thing")),

    Break("rate_permute permutes the season POINT multiset instead of the per-game RATE multiset "
          "— the incumbent's defect, wearing this story's name",
          RP,
          "            rate_desc = np.sort(b[idx] / gsafe[idx])[::-1]",
          "            rate_desc = np.sort(b[idx])[::-1] / gsafe[order]",
          gone="rate_desc = np.sort(b[idx] / gsafe[idx])[::-1]",
          tests=("test_rate_permute_hands_out_the_positions_own_per_game_rate_multiset",)),

    Break("an unknown arm falls through to the incumbent instead of raising — every arm would then "
          "score identically and the bake-off would read as a clean tie",
          RP,
          '    if arm not in ALL_ARMS:\n        raise ValueError(f"unknown arm {arm!r} — the '
          'declared field is {ALL_ARMS}")',
          "    if arm not in ALL_ARMS:\n        arm = INCUMBENT_ARM",
          gone='raise ValueError(f"unknown arm',
          tests=("test_an_unknown_arm_raises_instead_of_silently_scoring_the_incumbent",)),

    Break("an INELIGIBLE row is permuted — NF1.5b's contract broken, interleaving two scales",
          RP,
          "    elig = np.asarray(eligible, dtype=bool)",
          "    elig = np.ones(len(b), dtype=bool)",
          gone="elig = np.asarray(eligible, dtype=bool)",
          tests=("test_every_arm_leaves_an_ineligible_row_at_its_mvp1_point",)),

    Break("the feasibility clamp returns the shipped SCALAR bound — the arm stops being a clamp",
          RP,
          '    if arm != "feasibility_clamp":\n        return rescale_hi',
          "    if True:\n        return rescale_hi",
          gone='if arm != "feasibility_clamp":',
          tests=("test_feasibility_clamp_bounds_the_rescale_by_the_physical_envelope",
                 "test_every_other_arm_keeps_the_shipped_scalar_clamp")),

    Break("a position the envelope cannot speak to is given a bound anyway (NF1.7 (a) — an "
          "unevaluable check scored as a finding)",
          RP,
          '        cap = np.array([float(env.get(p, {}).get(field, np.inf)) for p in pos], '
          'dtype=float)',
          '        cap = np.array([float(env.get(p, {}).get(field, 1.0)) for p in pos], '
          'dtype=float)',
          gone="get(field, np.inf)",
          tests=("test_a_row_the_envelope_cannot_speak_to_is_unbounded_not_silently_clamped",)),

    Break("the serving policy stops checking that the gates CLEARED",
          RP,
          '        if GATE_STATUS != "CLEARED":',
          "        if False:",
          gone='if GATE_STATUS != "CLEARED":',
          tests=("test_serving_an_uncleared_arm_is_refused",)),

    Break("the serving policy stops requiring a PM disposition — clearing the gates and DECIDING "
          "to ship collapsed into one flag, the NF-D21/NF-D22 failure",
          RP,
          "        if not PM_DISPOSITION_RECORDED:",
          "        if False:",
          gone="if not PM_DISPOSITION_RECORDED:",
          tests=("test_serving_a_cleared_arm_without_a_pm_disposition_is_refused",)),

    Break("a pre-registered DEGENERATE becomes servable",
          RP,
          "    if SERVED_ARM in DEGENERATE_ARMS:",
          "    if False:",
          gone="if SERVED_ARM in DEGENERATE_ARMS:",
          tests=("test_a_degenerate_can_never_be_served",)),

    Break("an arm is quietly dropped from the declared field (the field shrinks after the fact — "
          "the MH2.2 selection bias DSR exists to deflate)",
          RP,
          '    "random_order",       # DEGENERATE — a seeded within-position random permutation\n)',
          ")",
          gone='"random_order",       # DEGENERATE',
          tests=("test_the_declared_field_is_the_pre_registered_six_plus_the_matched_foil",)),

    Break("`random_order` becomes unseeded — a degenerate that moves between runs of one report",
          RP,
          "    rng = np.random.default_rng(seed)",
          "    rng = np.random.default_rng()",
          gone="np.random.default_rng(seed)",
          tests=("test_mvp1_null_is_the_identity_and_random_order_is_not",)),

    Break("the games floor is raised until it BINDS on the real population — a guard silently "
          "turned into a tuning knob",
          RP, "GAMES_FLOOR = 0.25", "GAMES_FLOOR = 9.0",
          gone="GAMES_FLOOR = 0.25",
          tests=("test_the_games_floor_is_inert_on_the_real_population",)),

    Break("the coherence bridge stops using the SHARED field map — two maps to drift apart, so the "
          "count the bake-off scored and the count the publish guard reads stop being the same "
          "measurement",
          PC,
          "        for field, col in PARQUET_FIELD.items():",
          '        for field, col in {"passAtt": "proj_pass_att"}.items():',
          gone="for field, col in PARQUET_FIELD.items():",
          tests=("test_the_frame_bridge_reads_every_envelope_field_through_the_shared_map",)),

    Break("the shipping ordering function stops delegating to the ONE arm kernel — the arm the "
          "bake-off scored and the arm the board serves become two implementations (NF-C0e)",
          M1,
          "    remapped = _RP.assign_targets(",
          "    remapped = base.copy()\n    _unused = _RP.assign_targets(",
          gone="    remapped = _RP.assign_targets(",
          tests=("test_the_shipping_path_delegates_to_the_one_arm_kernel",)),
)


def _restore_stale_backups() -> None:
    """⚠️ AT START-UP, not only in `finally`: this harness mutates TRACKED source, so a previous
    invocation killed mid-mutation would leave a broken tree that the next run silently measures."""
    for path in (RP, PC, M1):
        bak = path.with_suffix(path.suffix + ".redproof")
        if bak.exists():
            bak.replace(path)
            print(f"  ⚠️ restored a stale backup: {bak.name}")


def _run(node: str) -> bool:
    """True when the clause turned RED."""
    r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{node}", "-q",
                        "-p", "no:randomly", "--no-header", "-x"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode != 0


def main() -> int:
    _restore_stale_backups()
    results, vacuous = [], []
    for b in BREAKS:
        src = b.path.read_text()
        n_hits = src.count(b.old)
        if n_hits != 1:
            print(f"🚨 ANCHOR NOT UNIQUE ({n_hits} hit(s)) — {b.name}")
            vacuous.append((b.name, "anchor not unique"))
            continue
        bak = b.path.with_suffix(b.path.suffix + ".redproof")
        bak.write_text(src)
        try:
            b.path.write_text(src.replace(b.old, b.new, 1))
            after = b.path.read_text()
            if after == src:
                print(f"🚨 MUTATION DID NOT LAND — {b.name}")
                vacuous.append((b.name, "mutation did not land"))
                continue
            if b.gone and b.gone in after:
                print(f"🚨 MUTATION LANDED BUT LEFT {b.gone!r} — {b.name}")
                vacuous.append((b.name, "mutation did not move the asserted predicate"))
                continue
            reds = [t for t in b.tests if _run(t)]
            greens = [t for t in b.tests if t not in reds]
            results.append((b.name, reds, greens))
            print(f"{'✅ RED' if reds else '🚨 VACUOUS':>12}  {b.name[:96]}")
            for t in greens:
                print(f"              …green on its own break: {t}")
            if not reds:
                vacuous.append((b.name, "no clause turned red"))
        finally:
            b.path.write_text(bak.read_text())
            bak.unlink()
    print(f"\n{len(results) - len(vacuous)}/{len(BREAKS)} breaks turned a guard RED")
    if vacuous:
        print("\n🚨 VACUOUS GUARDS — a guard that cannot fail is not a guard:")
        for n, why in vacuous:
            print(f"   · {n}  ({why})")
        return 1
    print("✅ every deliberate break turned its own clause red")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
