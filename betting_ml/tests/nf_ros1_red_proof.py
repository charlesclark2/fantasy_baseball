"""nf_ros1_red_proof.py — prove every NF-ROS1 guard can actually FAIL (⛔ NOT a pytest module).

A guard that cannot go red is not a guard (NF1.7 (a); INC-38; NF-D17). One deliberate break at a
time is applied to the source IN-PROCESS; the clause(s) that name it are run; a clause that stays
green on its own break is VACUOUS.

The repo's four red-proof lies are guarded as in `nf_d22_red_proof.py` (mutation lands, anchor is
unique, the removed token is GONE, the proof is a script the closeout runs). Three more, which the
NF-ROS1 spec names:

  * BASELINE-PASS — every named clause must PASS on the clean tree first, or a "red" proves nothing.
  * RESOLVE-EVERY-NODE — every named clause must COLLECT to exactly one test; a typo'd node id
    otherwise makes pytest exit non-zero and reads as a red.
  * NOT-SELECTED — only pytest exit code 1 ("tests failed") counts as RED. Exit 5 (nothing
    selected) and exit 2/4 (collection/usage error) are reported as NOT A RED.

    uv run python betting_ml/tests/nf_ros1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RV = ROOT / "quant_sports_intel_models/football/nfl/fantasy/ros_value.py"
RUN = ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_nf_ros1.py"
TESTS = "betting_ml/tests/test_nf_ros1_value.py"
PATHS = (RV, RUN)


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    gone: str
    tests: tuple[str, ...]


BREAKS: tuple[Break, ...] = (
    Break("m = ∞ no longer returns the prior exactly", RV,
          "    if math.isinf(m):\n        return r0.copy()\n    return (m * r0 + x_sum) / (m + n)",
          "    return (m * r0 + x_sum) / (m + n)",
          gone="return r0.copy()\n    return (m * r0 + x_sum)",
          tests=("test_infinite_prior_strength_reproduces_the_prorated_incumbent_exactly",)),
    Break("a single dead channel reads as a collapse", RV,
          '"collapsed_to_incumbent": all(math.isinf(v)',
          '"collapsed_to_incumbent": any(math.isinf(v)',
          gone='"collapsed_to_incumbent": all(',
          tests=("test_a_real_signal_is_not_flagged_as_a_collapse",)),
    Break("CRPS loses its factor of two", RV,
          "    return 2.0 * pin.mean(axis=1)", "    return pin.mean(axis=1)",
          gone="return 2.0 * pin.mean",
          tests=("test_crps_q_is_twice_the_mean_pinball_loss",)),
    Break("PIT spreads the lower tail over the whole unit interval", RV,
          "    u[below] = 0.05 * draws[below]", "    u[below] = draws[below]",
          gone="0.05 * draws[below]",
          # the loose censored control (0.02) CANNOT see this — measured vacuous on the first run;
          # the focused lower-tail clause is the guard that owns it
          tests=("test_mass_below_the_lowest_knot_lands_below_the_first_level",)),
    Break("PIT is blind (returns the raw uniforms)", RV,
          "    u[i] = f0 + (f1 - f0) * (y[i] - x0) / (x1 - x0)\n    return u\n",
          "    u[i] = f0 + (f1 - f0) * (y[i] - x0) / (x1 - x0)\n    return draws\n",
          gone="(x1 - x0)\n    return u\n",
          tests=("test_the_pit_detects_a_miscalibrated_predictive",)),
    Break("expected excess forgets the positive part", RV,
          "    return np.maximum(qgrid - c, 0.0).mean(axis=1)",
          "    return (qgrid - c).mean(axis=1)",
          gone="np.maximum(qgrid - c, 0.0)",
          tests=("test_expected_excess_is_zero_for_a_predictive_entirely_below_the_cutoff",
                 "test_a_narrow_position_does_not_float_on_expected_excess")),
    Break("the pace mirror drifts from the frontend", RV,
          '{"QB": 471.1, "RB": 512.3', '{"QB": 471.0, "RB": 512.3',
          gone='"QB": 471.1',
          tests=("test_the_pace_anchor_mirrors_the_frontend_constant",)),
    Break("ros_value grows an IO import", RV,
          "import numpy as np\nimport pandas as pd\n\n# ── registered constants",
          "import numpy as np\nimport pandas as pd\nimport requests  # noqa: F401\n\n# ── registered constants",
          gone="import pandas as pd\n\n# ── registered constants",
          tests=("test_ros_value_never_imports_pipeline_or_does_io",)),
    Break("realized-to-date reads week k+1 (future leak)", RUN,
          "            upto = weeks <= k\n", "            upto = weeks <= k + 1\n",
          gone="upto = weeks <= k\n",
          tests=("test_no_row_reads_a_week_after_k",)),
    Break("unsigned players lose the league-median schedule", RUN,
          '            elif not upto.any() and not b["team_id"]:',
          "            elif False:",
          gone='elif not upto.any() and not b["team_id"]',
          tests=("test_an_unsigned_never_played_player_gets_the_league_median_schedule",)),
    Break("the schedule side is not canonicalized", RUN,
          "        sched[c] = [normalize_team(t) for t in sched[c]]",
          "        sched[c] = list(sched[c])",
          gone="sched[c] = [normalize_team(t)",
          tests=("test_the_era_code_resolves_to_the_schedule_team",)),
    Break("byes count as games", RUN,
          "            t = int((weeks <= k).sum())", "            t = int(k)",
          gone="t = int((weeks <= k).sum())",
          tests=("test_bye_weeks_are_not_games",)),
    Break("prior and realized score on the UNION of terms", RUN,
          "    both = keys_prior & keys_real", "    both = keys_prior | keys_real",
          gone="keys_prior & keys_real",
          tests=("test_prior_and_realized_are_scored_on_the_same_term_set",)),
    Break("kickers are dropped from the realized read", RUN,
          'REALIZED_POSITIONS = {"QB", "RB", "FB", "HB", "WR", "TE", "K"}',
          'REALIZED_POSITIONS = {"QB", "RB", "FB", "HB", "WR", "TE"}',
          gone='"TE", "K"}',
          tests=("test_kickers_are_scored_by_the_existing_scorer",)),
    Break("max_width reverts to q10 = max", RUN,
          "    q[:, V.LEVELS >= 0.5] = hi[:, None]", "    q[:, 1:] = hi[:, None]",
          gone="V.LEVELS >= 0.5",
          tests=("test_max_width_is_the_registered_zero_to_max_interval",)),
)


def _restore_stale_backups() -> None:
    for p in PATHS:
        bak = p.with_suffix(p.suffix + ".redproof")
        if bak.exists():
            bak.replace(p)
            print(f"  ⚠️ restored a stale backup: {bak.name}")


def _pytest(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "-p", "no:randomly",
                           "-p", "no:cacheprovider", "--no-header"],
                          cwd=ROOT, capture_output=True, text=True)


def _collects_one(node: str) -> bool:
    r = _pytest(["--collect-only", f"{TESTS}::{node}"])
    lines = [ln for ln in r.stdout.splitlines() if "::" in ln]
    return r.returncode == 0 and len(lines) == 1


def main() -> int:
    _restore_stale_backups()
    nodes = sorted({t for b in BREAKS for t in b.tests})
    bad = [n for n in nodes if not _collects_one(n)]
    if bad:
        print(f"🚨 NODES THAT DO NOT RESOLVE TO EXACTLY ONE TEST: {bad}")
        return 1
    base = _pytest([f"{TESTS}::{n}" for n in nodes])
    if base.returncode != 0:
        print("🚨 BASELINE FAILED — a red on a tree that is already red proves nothing")
        print(base.stdout[-2000:])
        return 1
    print(f"baseline: {len(nodes)} clauses pass on the clean tree")

    vacuous = []
    for b in BREAKS:
        src = b.path.read_text()
        if src.count(b.old) != 1:
            print(f"🚨 ANCHOR NOT UNIQUE ({src.count(b.old)} hit(s)) — {b.name}")
            vacuous.append((b.name, "anchor not unique"))
            continue
        bak = b.path.with_suffix(b.path.suffix + ".redproof")
        bak.write_text(src)
        try:
            b.path.write_text(src.replace(b.old, b.new, 1))
            after = b.path.read_text()
            if after == src:
                vacuous.append((b.name, "mutation did not land"))
                continue
            if b.gone in after:
                vacuous.append((b.name, f"mutation left {b.gone!r}"))
                continue
            outcomes = {}
            for t in b.tests:
                code = _pytest([f"{TESTS}::{t}", "-x"]).returncode
                outcomes[t] = code
            reds = [t for t, c in outcomes.items() if c == 1]
            other = {t: c for t, c in outcomes.items() if c not in (0, 1)}
            print(f"{'✅ RED' if reds else '🚨 VACUOUS':>12}  {b.name}"
                  + (f"   (NOT A RED — pytest exit {other})" if other else ""))
            if not reds:
                vacuous.append((b.name, f"no clause turned red {outcomes}"))
        finally:
            b.path.write_text(bak.read_text())
            bak.unlink()
    print(f"\n{len(BREAKS) - len(vacuous)}/{len(BREAKS)} breaks turned a guard RED")
    if vacuous:
        for n, why in vacuous:
            print(f"   🚨 {n}  ({why})")
        return 1
    print("✅ every deliberate break turned its own clause red")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
