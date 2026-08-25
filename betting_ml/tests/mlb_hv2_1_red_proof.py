#!/usr/bin/env python3
"""RED proof for MLB-HV2-1's guards.

A guard that cannot FAIL is worse than no guard (NF1.7 (a) / INC-38 / INC-39).
This harness breaks the source on purpose, one clause at a time, and requires the
NAMED test to go red. A break that leaves the suite green is reported as a
VACUOUS GUARD.

Three ways a RED proof lies, all defended against here:
  * #682 — the mutation silently NO-OPs. Every break asserts the file CHANGED.
  * #815 — the mutation lands but does not move the ASSERTED predicate. Every
    break asserts the old token is GONE afterwards.
  * E11.24 — the mutation lands on the WRONG symbol. Every break asserts its
    anchor occurs EXACTLY ONCE in the file.

E11.26: stale backups are restored at START-UP, because this harness's own worst
case is being killed mid-mutation.

    uv run python betting_ml/tests/mlb_hv2_1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STUDY = REPO / "betting_ml" / "scripts" / "mlb_hv2_1_market_bias.py"
TESTS = REPO / "betting_ml" / "tests" / "test_mlb_hv2_1_market_bias.py"


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    expect_red: tuple[str, ...]


BREAKS: tuple[Break, ...] = (
    Break("favorite buckets leave a gap", STUDY,
          "<= -140),", "<= -150),",
          ("test_the_favorite_buckets_partition_every_non_pickem_game",)),
    Break("marquee list gains a team", STUDY,
          'MARQUEE_TEAMS = ("ATL", "BOS", "CHC", "LAD", "NYM", "NYY")',
          'MARQUEE_TEAMS = ("ATL", "BOS", "CHC", "LAD", "NYM", "NYY", "PIT")',
          ("test_prereg_document_matches_the_gate_thresholds",)),
    Break("PBO threshold loosened", STUDY,
          "MAX_PBO = 0.20", "MAX_PBO = 0.50",
          ("test_prereg_document_matches_the_gate_thresholds",)),
    Break("2023 quietly re-enters the fold design", STUDY,
          "SEASONS = (2020, 2021, 2022, 2024, 2025, 2026)",
          "SEASONS = (2020, 2021, 2022, 2023, 2024, 2025, 2026)",
          ("test_prereg_document_matches_the_gate_thresholds",
           "test_the_fold_clause_is_the_one_the_prereg_states")),
    Break("a losing bet costs the full decimal, not the stake", STUDY,
          '"pnl": np.where(won, dec - 1.0, -1.0),',
          '"pnl": np.where(won, dec - 1.0, -dec),',
          ("test_a_flat_stake_win_pays_decimal_minus_one_and_a_loss_pays_minus_one",)),
    Break("fade_marquee always bets the road side", STUDY,
          '        _exactly_one_marquee,\n        lambda f: _marquee_away(f)),',
          '        _exactly_one_marquee,\n        lambda f: pd.Series(False, index=f.index)),',
          ("test_fade_marquee_bets_against_the_marquee_side_on_both_orientations",)),
    Break("an empty PBO bucket becomes NaN", STUDY,
          "M = np.zeros((len(buckets), len(arms)), dtype=float)",
          "M = np.full((len(buckets), len(arms)), np.nan, dtype=float)",
          ("test_an_empty_bucket_scores_zero_not_missing",)),
    Break("Shin collapses onto the proportional method", STUDY,
          "    out_h, out_a = _p(ph, z), _p(pa, z)",
          "    out_h, out_a = ph / ov, pa / ov",
          ("test_shin_and_proportional_differ_on_a_lopsided_price",)),
    Break("BH-FDR is computed over the surviving subset", STUDY,
          "    m = len(p)", "    m = max(1, int((p < 0.5).sum()))",
          ("test_benjamini_hochberg_is_computed_over_the_full_declared_field",)),
    Break("the study imports a learner", STUDY,
          "import numpy as np\nimport pandas as pd",
          "import numpy as np\nimport pandas as pd\nimport sklearn.linear_model  # noqa: F401",
          ("test_the_study_imports_no_model_serving_or_learner_module",)),
    Break("the pick'em exclusion is dropped", STUDY,
          'return f["home_decimal"] != f["away_decimal"]',
          'return pd.Series(True, index=f.index)',
          ("test_a_pickem_is_excluded_from_every_favorite_referencing_arm",)),
    Break("the oracle anchor stops seeing the outcome", STUDY,
          'lambda f: f["home_won"].astype(bool)),',
          'lambda f: pd.Series(True, index=f.index)),',
          ("test_the_oracle_anchor_never_loses_a_bet",)),
    Break("the leak detector's own probe is disarmed", TESTS,
          'if any(m == p or m.startswith(p + ".")\n                         for p in FORBIDDEN_MODULE_PREFIXES))',
          'if False and any(m == p or m.startswith(p + ".")\n                         for p in FORBIDDEN_MODULE_PREFIXES))',
          ("test_the_probe_can_actually_detect_a_leak",)),
)


def _restore_stale() -> None:
    for path in (STUDY, TESTS):
        bak = path.with_suffix(path.suffix + ".redproof.bak")
        if bak.exists():
            print(f"  restoring stale backup for {path.name}")
            path.write_text(bak.read_text())
            bak.unlink()


def _run(test_names: tuple[str, ...]) -> bool:
    """True == at least one named test FAILED (i.e. the guard fired)."""
    sel = " or ".join(test_names)
    out = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-k", sel, "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True, timeout=900)
    if "no tests ran" in out.stdout:
        raise AssertionError(f"selector {sel!r} matched NO tests — the proof is vacuous")
    return out.returncode != 0


def main() -> int:
    _restore_stale()
    failures: list[str] = []
    for brk in BREAKS:
        src = brk.path.read_text()
        n = src.count(brk.old)
        if n != 1:
            failures.append(f"{brk.name}: anchor occurs {n}x (must be exactly 1) — "
                            "the mutation could land on the wrong symbol (E11.24)")
            continue
        bak = brk.path.with_suffix(brk.path.suffix + ".redproof.bak")
        bak.write_text(src)
        try:
            brk.path.write_text(src.replace(brk.old, brk.new, 1))
            after = brk.path.read_text()
            assert after != src, f"{brk.name}: mutation did not land (#682)"
            if brk.old not in brk.new:
                # #815 applies to a REPLACEMENT: if the anchor survives, the break
                # landed without moving the asserted predicate. An ADDITIVE break
                # (inserting a line) keeps its anchor by construction, so the check
                # is scoped rather than dropped.
                assert brk.old not in after, (
                    f"{brk.name}: the old token survived the mutation, so the "
                    "asserted predicate may not have moved (#815)")
            red = _run(brk.expect_red)
            print(f"  {'RED  ' if red else 'GREEN'}  {brk.name}")
            if not red:
                failures.append(f"{brk.name}: guard(s) {brk.expect_red} stayed GREEN "
                                "on deliberately broken source — VACUOUS")
        finally:
            brk.path.write_text(bak.read_text())
            bak.unlink()

    print()
    if failures:
        for f in failures:
            print(f"VACUOUS: {f}")
        return 1
    print(f"all {len(BREAKS)} deliberate breaks went RED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
