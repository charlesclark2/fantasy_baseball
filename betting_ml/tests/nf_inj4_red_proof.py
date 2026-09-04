"""nf_inj4_red_proof.py — prove every NF-INJ4 guard actually FAILS on a deliberately broken source.

A guard that cannot fail is not a guard (NF1.7 (a) / INC-38), and this repo has produced FOUR
distinct ways a RED proof itself lies:
  · the mutation never LANDED on disk (#682) — asserted here;
  · it landed but did not move the ASSERTED predicate (#815) — the retired token is asserted GONE;
  · it landed on the WRONG symbol because the anchor was not unique (prediction_log) — uniqueness
    is asserted before the edit;
  · the inner clause raised `Failed`, a `BaseException`, and sailed through `except Exception`
    (NF-W6c) — every subprocess result is read from its return code, not from an exception.
Plus a BASELINE pass and a NOT-SELECTED control per case: the named guard must go RED while an
unrelated guard stays GREEN, so a mutation that simply breaks the module cannot be mistaken for a
guard that caught something.

⚠️ Stale backups are restored AT START-UP — this harness's own worst case is being killed
mid-mutation, and a leftover `.orig` would silently poison the next run (E11.26).

RUN (LAPTOP, ~1 min):  uv run python betting_ml/tests/nf_inj4_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/nf_inj4_designation_duration.py"
_SEASON = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/season_projection.py"
_TESTS = _ROOT / "betting_ml/tests/test_nf_inj4_designation_duration.py"


@dataclass(frozen=True)
class Case:
    name: str
    path: Path
    #: The UNIQUE anchor to replace ("" ⇒ append `new` at EOF). ⚠️ It must genuinely DISAPPEAR:
    #: the gone-token check (#815) is what proves the break moved the ASSERTED predicate rather
    #: than merely writing bytes, so an INSERTION has to be expressed as a replacement whose anchor
    #: is consumed — widen the anchor to span the insertion point rather than relaxing the check.
    old: str
    new: str
    target: str              #: the guard that MUST go RED
    not_selected: str        #: an unrelated guard that MUST stay GREEN


CASES: tuple[Case, ...] = (
    Case("espn re-admitted", _KERNEL,
         'ADMISSIBLE_SOURCES: tuple[str, ...] = ("nfl", "cbs")',
         'ADMISSIBLE_SOURCES: tuple[str, ...] = ("nfl", "cbs", "espn")',
         "test_espn_is_excluded_from_the_admissible_sources",
         "test_crps_is_the_exact_discrete_form_not_a_quantile_grid"),
    Case("a blank capture wins on recency", _KERNEL,
         'df = df.assign(_has_designation=df["report_status"].notna().astype(int))',
         'df = df.assign(_has_designation=0)',
         "test_a_blank_capture_never_overwrites_an_earlier_designation",
         "test_espn_is_excluded_from_the_admissible_sources"),
    Case("the earliest row wins instead of the latest", _KERNEL,
         '.sort_values(["_has_designation", "capture_ts"])\n'
         '             .drop_duplicates(subset=["week", "gsis_id"], keep="last")',
         '.sort_values(["_has_designation", "capture_ts"])\n'
         '             .drop_duplicates(subset=["week", "gsis_id"], keep="first")',
         "test_resolution_takes_the_whole_row_not_the_column_wise_last_non_null",
         "test_the_degenerates_sit_at_opposite_ends_of_the_support"),
    Case("absence from the spine stops being a miss", _KERNEL,
         'g["missed"] = g["has_game"] & ~g["appeared"]',
         'g["missed"] = g["has_game"] & False',
         "test_a_team_game_with_no_certified_appearance_is_a_miss",
         "test_a_bye_is_skipped_never_counted_as_a_miss"),
    Case("the spell counts every later miss, not the consecutive run", _KERNEL,
         'spell = int(len(missed)) if played.size == 0 else int(played[0])',
         'spell = int(missed.sum())',
         "test_the_spell_is_consecutive_and_stops_at_the_next_appearance",
         "test_espn_is_excluded_from_the_admissible_sources"),
    Case("the support bound stops being applied", _KERNEL,
         'p[k > np.asarray(games_remaining, dtype=float)[:, None]] = 0.0',
         'p[k > 999] = 0.0',
         "test_every_predictive_is_truncated_to_the_rows_own_support",
         "test_crps_is_the_exact_discrete_form_not_a_quantile_grid"),
    Case("an empty cell stops raising", _KERNEL,
         '    if tot <= 0:\n        raise ValueError("empirical_pmf received ZERO observations',
         '    if tot < 0:\n        raise ValueError("empirical_pmf received ZERO observations',
         "test_an_empty_cell_raises_rather_than_yielding_a_silent_predictive",
         "test_espn_is_excluded_from_the_admissible_sources"),
    Case("the thin-cell backoff is disabled", _KERNEL,
         "MIN_CELL_N = 30",
         "MIN_CELL_N = 1",
         "test_the_thin_cell_backoff_uses_the_parent_not_a_one_row_distribution",
         "test_espn_is_excluded_from_the_admissible_sources"),
    Case("only one degenerate is declared", _KERNEL,
         'DEGENERATE_ARMS: tuple[str, ...] = ("always_zero", "always_max")',
         'DEGENERATE_ARMS: tuple[str, ...] = ("always_zero",)',
         "test_the_degenerates_sit_at_opposite_ends_of_the_support",
         "test_the_incumbent_reference_is_itself_a_declared_degenerate"),
    Case("a gate drops out of the declared partition", _KERNEL,
         '    "beats_permutation": "metric",\n',
         '',
         "test_gate_classes_classifies_every_gate_the_study_scores",
         "test_espn_is_excluded_from_the_admissible_sources"),
    Case("pbo is carried as a per-arm gate", _KERNEL,
         '    "dsr_ok": "deflation",\n    "degenerates_lose": "invariant",',
         '    "dsr_ok": "deflation",\n    "pbo": "deflation",\n'
         '    "degenerates_lose": "invariant",',
         "test_pbo_is_never_carried_as_a_per_arm_gate",
         "test_the_bh_family_is_declared_as_a_single_hypothesis"),
    Case("the fold count drops below sign-certifiability", _KERNEL,
         "N_FOLDS = 10",
         "N_FOLDS = 7",
         "test_the_fold_count_is_sign_certifiable_under_both_declared_bh_readings",
         "test_espn_is_excluded_from_the_admissible_sources"),
    Case("the caps compose instead of taking the strongest", _KERNEL,
         "        if float(val) < best_val - 1e-12:",
         "        if float(val) > best_val - 1e-12:",
         "test_a_player_with_both_a_news_cap_and_a_designation_takes_ONE_of_them",
         "test_no_channel_leaves_the_projection_untouched"),
    # ⭐ RE-ANCHORED BY NF-INJ4b (MH2.7 — never weakened, never deleted). The guard this case
    #    drives used to forbid the model being wired into the serving owner AT ALL; NF-INJ4b
    #    certified the model and wired the channel DEFAULT-OFF, so the property being defended is
    #    no longer "there is no code" but "no PRODUCTION CALLER passes it". The mutation moves with
    #    it: a serving caller that passes `designation_games=` is what must go RED now. Leaving the
    #    old mutation in place produced a case that ran against a property nothing holds.
    Case("a production caller passes the designation channel (the deploy hold is lifted)", _SEASON,
         "", "\n\n# RED-PROOF MUTATION — a production caller turning the certified channel ON\n"
         "def _nf_inj4b_serving_caller(df):\n"
         "    return apply_availability_chain(df, designation_games=lambda d: d['proj_games'])\n",
         "test_the_designation_channel_is_wired_but_structurally_off_in_production",
         "test_espn_is_excluded_from_the_admissible_sources"),
)


def _restore_stale() -> int:
    """A leftover `.orig` means a previous run was killed mid-mutation; restoring FIRST is what
    stops that run's break poisoning this one."""
    n = 0
    for p in (_KERNEL, _SEASON):
        b = p.with_suffix(p.suffix + ".redproof.orig")
        if b.exists():
            p.write_text(b.read_text())
            b.unlink()
            n += 1
    return n


def _pytest(node: str) -> int:
    """⛔ **A NODE ID THAT COLLECTS NOTHING MUST NOT READ AS RED.** pytest exits NON-ZERO on an
    unresolvable node id, so a guard that has merely been RENAMED reports a perfect RED for a test
    that no longer exists — the harness's own worst failure mode, and it fired for real: NF-INJ4b
    renamed this file's wiring guard and this proof went on reporting 14/14 RED, one of them
    against nothing at all. The collection is asserted FIRST, and a non-collecting node is a HARD
    ERROR, never a red (the "a red proof's RED can mean the clause never ran" class)."""
    target = f"{_TESTS}::{node}"
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "--collect-only", "-p",
         "no:cacheprovider"],
        cwd=_ROOT, capture_output=True, text=True)
    if probe.returncode != 0 or "no tests ran" in (probe.stdout + probe.stderr):
        raise SystemExit(
            f"⛔ `{node}` collects NOTHING — it has been renamed, moved or deleted. Every 'RED' "
            f"credited to it would be pytest refusing an unresolvable node id, not a guard "
            f"catching a break. Re-anchor this proof onto the guard's current name (MH2.7).")
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p",
         "no:cacheprovider"],
        cwd=_ROOT, capture_output=True, text=True).returncode


def main() -> int:
    stale = _restore_stale()
    if stale:
        print(f"⚠️  restored {stale} stale backup(s) from a killed run before starting")

    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", str(_TESTS), "-q", "--no-header",
         "-p", "no:cacheprovider"], cwd=_ROOT, capture_output=True, text=True)
    if baseline.returncode != 0:
        print("BASELINE FAILED — the suite must be GREEN before any mutation means anything")
        print(baseline.stdout[-3000:])
        return 1
    print(f"baseline: GREEN ({len(CASES)} cases to prove)\n")

    failures = []
    for c in CASES:
        original = c.path.read_text()
        backup = c.path.with_suffix(c.path.suffix + ".redproof.orig")
        backup.write_text(original)
        try:
            if c.old:
                n = original.count(c.old)
                if n != 1:
                    failures.append(f"{c.name}: anchor appears {n}x (must be exactly 1) — a "
                                    f"non-unique anchor lands the break on the WRONG symbol and "
                                    f"reports a FALSE vacuity")
                    continue
                mutated = original.replace(c.old, c.new, 1)
            else:
                mutated = original + c.new
            c.path.write_text(mutated)

            on_disk = c.path.read_text()
            if on_disk == original:
                failures.append(f"{c.name}: the mutation did NOT land on disk (#682)")
                continue
            if c.old and c.old in on_disk:
                failures.append(f"{c.name}: the retired token is still present — the break landed "
                                f"but did not move the asserted predicate (#815)")
                continue
            if not c.old and c.new not in on_disk:
                failures.append(f"{c.name}: the appended mutation is absent from disk")
                continue

            red = _pytest(c.target)
            green = _pytest(c.not_selected)
            ok = (red != 0) and (green == 0)
            print(f"{'✅' if ok else '❌'} {c.name}\n"
                  f"     target       {c.target}: {'RED' if red else 'GREEN'}\n"
                  f"     not-selected {c.not_selected}: {'GREEN' if green == 0 else 'RED'}")
            if red == 0:
                failures.append(f"{c.name}: the guard stayed GREEN on broken source — VACUOUS")
            if green != 0:
                failures.append(f"{c.name}: the NOT-SELECTED control also went RED — the mutation "
                                f"broke the module rather than tripping the named guard")
        finally:
            c.path.write_text(backup.read_text())
            backup.unlink()

    print()
    if failures:
        print(f"RED PROOF FAILED — {len(failures)} problem(s):")
        for f in failures:
            print("  ·", f)
        return 1
    print(f"RED PROOF PASSED — {len(CASES)}/{len(CASES)} guards go RED on broken source, "
          f"each with a unique anchor, a landed mutation and a green NOT-SELECTED control.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
