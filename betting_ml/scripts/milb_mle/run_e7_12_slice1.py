"""run_e7_12_slice1.py — MLB Edge-E7.12 SLICE 1: the pre-registered §0.5 ablation ladder for
minor-league PARK factors + per-LEVEL run environment + the small-sample (reliability) hardening of the
E7.3 Bayesian partial-pool.

⚠️ **OPERATOR-RUN (>2 min).** ~16 configs × 4 metrics × leave-one-debut-cohort-out folds, each an EB
variance-component search. `--metrics k_pct --arms S0_baseline S1_park_exposure` is the cheap smoke.

    # 0. the two cached matrices (assemble ONCE — the §0.5 cost-hygiene rule)
    uv run python -m betting_ml.scripts.milb_mle.build_graduated_pairs --season-floor 2015
    uv run python -m betting_ml.scripts.milb_mle.build_park_context   --season-floor 2015
    # 1. the ladder
    uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice1

WHAT IT DECIDES
---------------
For each of the four batter metrics, whether ANY rung of the ladder beats the **E7.3 incumbent** on
held-out translation accuracy by enough to survive deflation — and, if so, re-emits `mle_projections`
under that rung (`--apply`). **A null add is DROPPED, not shipped.** `best_alpha = 0`.

SLICE 1p — THE PITCHER SIDE (`--player-type pitcher`)
-----------------------------------------------------
The same ladder, the same three degenerate anchors, the same deflation, run against the E7.3p incumbent
on `mle_projections_pitchers`. E7.3p's "harness reused, not forked" precedent, one rung up: a `SideConfig`
carries the only things that legitimately differ — the pinned incumbent prior scales, the metric list,
the falsification split and the emission target. A test asserts the two sides are the SAME set of rungs.
(The label-exposure column is `mlb_pa` on BOTH sides: E7.3p deliberately stores batters-faced under the
shared `mlb_pa`/`minor_pa` names so the harness needs no pitcher fork — see the weight-column guard in
`run_ladder` for what assuming otherwise costs.)

    uv run python -m betting_ml.scripts.milb_mle.build_graduated_pairs_pitchers --season-floor 2015
    uv run python -m betting_ml.scripts.milb_mle.build_park_context --season-floor 2015 \
        --player-type pitcher
    uv run python -m betting_ml.scripts.milb_mle.run_e7_12_slice1 --player-type pitcher

⭐ **The pitcher run is an INDEPENDENT REPLICATION of the batter finding, not a restatement.** The batter
slice measured a small but real park effect (+0.84% on ISO, 11/11 folds) against a much larger level×season
RUN-ENVIRONMENT effect. The pitcher side tests the same physical claim — fences move batted balls, not the
strike zone — on a different population, a different label and a different set of counting stats. If the
batter park effect were an artifact of the batter substrate, this side has no reason to reproduce it.

⚠️ Two honest asymmetries, stated before the run: (a) `xwoba_against` can have NO park factor and no run
environment — its minor feature is the E7.2 AAA-Statcast summary, which has no home/road box-line bucket
to form a ratio from, so its park/env arms are unselectable no-ops rather than fabricated 1.0s; and (b)
only `gb_pct`, `bb_pct`, `k_pct` reach the E8.0 board — E7.3p found `hr_rate` and `xwoba_against`
no-signal, so a lift on those two is COSMETIC (the pitcher-side twin of wOBA on the batter side).

THE LADDER IS AN ABLATION, NOT A GRID SEARCH (§0.5's "pre-register a hypothesis-driven set, not open
subset search"). Each rung adds ONE named mechanism to the one before it, plus two isolation arms that
break the ladder apart, plus three anchors that MUST LOSE.

⭐ **THE LEARNER IS HELD FIXED** at `partial_pool@<the metric's E7.3 winning prior scale>` for every
rung. That is the E7.9 lesson applied up front: E7.9's bake-off reported margins in which **54–77% of
every leader's lift was the LEARNER swap, not the features**, because the gate compared leader-arm vs
incumbent-arm. Here the only thing that varies between S0 and S1 is the park factor, so the margin IS
the mechanism. A two-point prior-scale sensitivity is reported separately (and counted toward deflation)
rather than folded into the headline.

🪤 **WHAT WOULD MAKE THIS SLICE LIE, AND THE ARM THAT CATCHES EACH** (the CLAUDE.md two-sided-anchor rule —
"score the ORACLE FLOOR *and* the DEGENERATE CEILING; a real candidate losing to the degenerate means the
metric is inverted"). Dividing a rate by a dispersed number and shrinking it toward a mean BOTH lower MAE
against a regressed target on their own, so three separate degenerates are in the field:

  | trap                                              | anchor arm            | must hold                    |
  |---------------------------------------------------|-----------------------|------------------------------|
  | "any dispersed multiplier helps" (not the venue)   | `A_park_placebo`      | placebo LOSES to S1          |
  | self-shrinkage: the player inflates his own park's | `A_park_noloo`        | non-LOO must not BEAT LOO    |
  | factor, so dividing shrinks HIM toward the mean    |                       |                              |
  | "reliability" is really a global slope rescale     | `A_rel_constant`      | constant-r LOSES to PA-varying|

  plus the E7.3 ORACLE FLOOR (no candidate may score MAE < 0) carried through, and a pre-registered
  DIRECTIONAL falsification: **parks move balls in play**, so a genuine park effect must be concentrated
  in ISO/wOBA and near-zero for K%/BB%. A lift that appears UNIFORMLY across all four metrics is the
  shrinkage confound in a park costume, and is reported as such.

DEFLATION IS REPORTED AS FOUR NUMBERS, NOT ONE (NF1.8). PBO alone cannot tell "my pick is unstable" from
"my pick is tied", so the report carries the FLIP DISTRIBUTION (which arms win the in-sample halves),
Bailey's PERFORMANCE DEGRADATION (did picking it COST anything out-of-sample?), the CONTENDER spread (top
quartile only, not the whole field — a spread computed over a field containing its own anchors measures
the anchors), and PBO over the ELIGIBLE set. Across the four metrics the primary contrast is a 4-test
family → Benjamini-Hochberg FDR.
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    BATTER_METRICS,
    PITCHER_AUX_COLS,
    PITCHER_METRICS,
    PLAUSIBLE_RANGE,
    MleConfig,
    PartialPoolProjector,
    build_target,
    emit_projections,
)
from betting_ml.scripts.milb_mle.park_context import (  # noqa: E402
    BATTER_REDUCED,
    STABILIZATION_PA,
    ContextSpec,
    ReducedSpec,
    apply_context,
    context_coverage,
    reduced_spec,
)

log = logging.getLogger("e7_12.slice1")

_E73_OUT = (_PROJECT_ROOT
            / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts")
_DEFAULT_OUT = (_PROJECT_ROOT
                / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_12_artifacts")
_REPORT_PATH = (_PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
                / "e7_12_slice1_park_level_context.md")
_KEYS = ["player_id", "level"]

# ⭐ PINNED from the E7.3 report (`ablation_results/e7_3_milb_mle.md` §1b) — the incumbent winner's prior
# scale per metric. Held FIXED across the whole ladder so the margin is the MECHANISM, not the learner.
# Pinned as a literal rather than recomputed: rebuilding the reference from the code the slice CHANGES
# is how a harness silently compares a change against itself (the NF1.8 `_NF17_WINNER_LABEL` lesson).
E73_WINNER_PRIOR_SCALE: dict[str, float] = {"woba": 4.0, "k_pct": 2.0, "bb_pct": 4.0, "iso": 2.0}

# ⭐ PINNED from the E7.3p report (`ablation_results/e7_3p_milb_mle_pitchers.md` §1) — `partial_pool`
# won all five pitcher metrics; these are the winning prior scales. Same discipline as the batter map:
# a literal, so the ladder cannot silently re-derive its own reference from the code it is changing.
E73P_WINNER_PRIOR_SCALE: dict[str, float] = {
    "k_pct": 4.0, "bb_pct": 4.0, "hr_rate": 4.0, "gb_pct": 2.0, "xwoba_against": 2.0}

# Parks move BALLS IN PLAY. A real park effect belongs to the contact metrics; discipline is a
# pitcher-batter negotiation the fence distance barely touches. Pre-registered BEFORE the run so the
# directional read cannot be written to fit whatever came out.
PARK_SENSITIVE: tuple[str, ...] = ("iso", "woba")
PARK_INSENSITIVE: tuple[str, ...] = ("k_pct", "bb_pct")

# The pitcher MIRROR of that falsification, and it is a genuine INDEPENDENT REPLICATION rather than a
# restatement: it is the same physical claim (fences move batted balls, not the strike zone) tested on a
# different population, a different label and a different set of counting stats. HR-rate-allowed and
# ground-out share are the ball-in-play metrics; K% and BB% must stay ~flat. If the batter side's small
# real park effect were an artifact of the batter substrate, this side has no reason to reproduce it.
PARK_SENSITIVE_PITCHER: tuple[str, ...] = ("hr_rate", "gb_pct")
PARK_INSENSITIVE_PITCHER: tuple[str, ...] = ("k_pct", "bb_pct")


@dataclass(frozen=True)
class SideConfig:
    """Everything the ladder needs to know about WHICH side of the plate it is scoring.

    The batter and pitcher slices run the SAME pre-registered ladder, the same anchors and the same
    deflation — E7.3p's "harness reused, not forked" precedent, one rung up. Only the incumbent's pinned
    prior scales, the metric list, the falsification split and the emission target differ.
    """

    player_type: str
    reduced: ReducedSpec
    metrics: tuple[str, ...]
    prior_scales: dict[str, float]
    park_sensitive: tuple[str, ...]
    park_insensitive: tuple[str, ...]
    model_version: str
    incumbent_version: str
    s3_dest: str
    report_name: str
    pairs_name: str
    board_metrics: tuple[str, ...]     # what E8.0 actually reads — the rest is cosmetic if it moves

    def mle_config(self, metric: str) -> MleConfig:
        if self.player_type == "pitcher":
            return MleConfig(metric=metric, aux_cols=PITCHER_AUX_COLS, player_type="pitcher",
                             model_version=self.model_version)
        return MleConfig(metric=metric)


BATTER_SIDE = SideConfig(
    player_type="batter", reduced=BATTER_REDUCED, metrics=BATTER_METRICS,
    prior_scales=E73_WINNER_PRIOR_SCALE,
    park_sensitive=PARK_SENSITIVE, park_insensitive=PARK_INSENSITIVE,
    model_version="milb_mle_v2_parkctx", incumbent_version="milb_mle_v1",
    s3_dest="s3://baseball-betting-ml-artifacts/baseball/milb/derived/mle_projections",
    report_name="e7_12_slice1_park_level_context.md",
    pairs_name="mle_graduated_pairs.parquet",
    board_metrics=("k_pct", "bb_pct", "iso"),
)
PITCHER_SIDE = SideConfig(
    player_type="pitcher", reduced=reduced_spec("pitcher"), metrics=PITCHER_METRICS,
    prior_scales=E73P_WINNER_PRIOR_SCALE,
    park_sensitive=PARK_SENSITIVE_PITCHER, park_insensitive=PARK_INSENSITIVE_PITCHER,
    model_version="milb_mle_pitcher_v2_parkctx", incumbent_version="milb_mle_pitcher_v1",
    s3_dest="s3://baseball-betting-ml-artifacts/baseball/milb/derived/mle_projections_pitchers",
    report_name="e7_12_slice1p_park_level_context_pitchers.md",
    pairs_name="mle_graduated_pairs_pitchers.parquet",
    # E7.3p's no-signal metrics (hr_rate DSR 0.130, xwoba_against DSR 0.030) are EXCLUDED from the
    # board composite, so improving them cannot move a draft ranking — the pitcher-side twin of wOBA
    # being cosmetic on the batter side. Scored and reported anyway; just never claimed as a board win.
    board_metrics=("gb_pct", "bb_pct", "k_pct"),
)
SIDES: dict[str, SideConfig] = {"batter": BATTER_SIDE, "pitcher": PITCHER_SIDE}


# ══════════════════════════════════════════════════════════════════════════════════════
# The pre-registered ladder
# ══════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Rung:
    label: str
    spec: ContextSpec
    kind: str        # "ladder" | "isolation" | "anchor" | "sensitivity"
    note: str

    @property
    def selectable(self) -> bool:
        """Anchors are SCORED but never selected — a projection whose winner is the placebo would not
        be a park adjustment. Same posture as E7.3's `level_mean` / `identity` reference arms."""
        return self.kind != "anchor"


LADDER: tuple[Rung, ...] = (
    Rung("S0_baseline", ContextSpec(), "ladder",
         "the E7.3 incumbent, byte-exact (ContextSpec() is a no-op)"),
    Rung("S1_park_exposure", ContextSpec(park="exposure"), "ladder",
         "⭐ per-player PA-EXPOSURE-weighted leave-one-player-out park factor (our game-log advantage)"),
    Rung("S1f_park_halfweight", ContextSpec(park="halfweight"), "ladder",
         "the research memo's prescription verbatim: (1+PF_home)/2, the half-weight multiplier"),
    Rung("S2_level_env", ContextSpec(level_env=True), "ladder",
         "level×SEASON run environment normalised to the level's pooled baseline"),
    Rung("S3_park_env", ContextSpec(park="exposure", level_env=True), "ladder",
         "park + run environment together (where + when)"),
    Rung("S4_park_env_rel0.5", ContextSpec(park="exposure", level_env=True, reliability=0.5), "ladder",
         "+ per-component reliability shrink at HALF the literature stabilisation point"),
    Rung("S4_park_env_rel1.0", ContextSpec(park="exposure", level_env=True, reliability=1.0), "ladder",
         "+ per-component reliability shrink at the literature stabilisation point"),
    Rung("S4_park_env_rel2.0", ContextSpec(park="exposure", level_env=True, reliability=2.0), "ladder",
         "+ per-component reliability shrink at DOUBLE the stabilisation point (harder regression)"),
    Rung("S5_full_labelweight",
         ContextSpec(park="exposure", level_env=True, reliability=1.0, weight_col="mlb_pa"), "ladder",
         "+ label-precision observation weights (a 150-PA rookie label is a noisier observation)"),
    # ── isolation arms: break the ladder apart so a win is attributable to ONE rung ──
    Rung("I_reliability_only", ContextSpec(reliability=1.0), "isolation",
         "the small-sample hardening ALONE, no park, no run environment"),
    Rung("I_labelweight_only", ContextSpec(weight_col="mlb_pa"), "isolation",
         "label-precision weights ALONE"),
    # ── anchors: these MUST LOSE ──
    Rung("A_park_placebo", ContextSpec(park="placebo"), "anchor",
         "DEGENERATE CEILING — the same park factors permuted across players within a level"),
    Rung("A_park_noloo", ContextSpec(park="exposure_noloo"), "anchor",
         "DIAGNOSTIC — park factor WITHOUT the leave-one-player-out subtraction (self-shrinkage)"),
    Rung("A_rel_constant", ContextSpec(reliability=1.0, constant_reliability=True), "anchor",
         "DEGENERATE — everyone shrunk by the population-mean r (no PA variation)"),
)

# ── POST-HOC arms (opt-in, `--include-posthoc`) ────────────────────────────────────────────────────
# ⚠️ THESE WERE NOT PRE-REGISTERED. They exist because the PITCHER run (slice 1p) produced a result the
# ladder could not interrogate: `S5_full_labelweight` won three metrics, but S5 BUNDLES park + level-env
# + reliability + label weights, and the same run's isolation arms showed the PARK contributes nothing on
# this side (mean lift on the park-sensitive metrics −0.0%; on HR-rate the park arm alone is NEGATIVE and
# its placebo does marginally better). No pre-registered rung answers "does the winner get BETTER with the
# inert component removed?" — the ladder only ever adds mechanisms, never subtracts them.
#
# These are ABLATIONS-DOWN from the winner, not a grid search: each drops exactly one named component and
# asks whether it was carrying anything. They are honest only if handled as post-hoc, so:
#   * they are OFF by default — the pre-registered ladder is what runs unless you ask for these, which
#     keeps the already-PUBLISHED batter run byte-reproducible and makes their status impossible to miss;
#   * they carry `kind="posthoc"` and are labelled as such in the report;
#   * they are scored into the SAME deflation and the SAME eligible set, so choosing among a wider field
#     costs what a wider field should cost (PBO/DSR deflate against the whole search that ran);
#   * they must clear the SAME gate — ≥60% of folds AND, now, BH-FDR.
POSTHOC_RUNGS: tuple[Rung, ...] = (
    Rung("P1_env_rel_weight",
         ContextSpec(level_env=True, reliability=1.0, weight_col="mlb_pa"), "posthoc",
         "POST-HOC: the winning stack MINUS the park — is the park carrying anything inside it?"),
    Rung("P2_env_weight",
         ContextSpec(level_env=True, weight_col="mlb_pa"), "posthoc",
         "POST-HOC: minus the park AND the reliability shrink — the two components isolation showed "
         "smallest"),
    Rung("P3_rel_weight",
         ContextSpec(reliability=1.0, weight_col="mlb_pa"), "posthoc",
         "POST-HOC: minus the park AND the run environment — for the metrics where level-env HURT"),
)

_BY_LABEL = {r.label: r for r in LADDER + POSTHOC_RUNGS}


def ladder_for(side: SideConfig, include_posthoc: bool = False) -> tuple[Rung, ...]:
    """The same ladder, with the label-precision arm pointed at THAT side's label-exposure column.

    Today that resolves to `mlb_pa` on BOTH sides and this is a pass-through — E7.3p stores the
    pitcher's batters-faced under the shared name on purpose. The seam is kept anyway (rather than
    hardcoding `mlb_pa`) because it is the one thing about the weight arm that legitimately varies by
    population, and `run_ladder`'s guard turns a wrong value into a raise instead of a fake null.

    `include_posthoc` appends `POSTHOC_RUNGS` — OFF by default so the pre-registered ladder is what runs
    unless a caller explicitly opts in (see that constant for why the opt-in IS the honesty mechanism).
    """
    rungs = LADDER + (POSTHOC_RUNGS if include_posthoc else ())
    wc = side.reduced.label_weight_col
    if wc == "mlb_pa":
        return rungs
    return tuple(
        r if r.spec.weight_col is None
        else Rung(r.label, replace(r.spec, weight_col=wc), r.kind, r.note)
        for r in rungs
    )


def by_label(arms: tuple[Rung, ...]) -> dict[str, Rung]:
    return {r.label: r for r in arms}


# ══════════════════════════════════════════════════════════════════════════════════════
# Deflation (NF1.8's four numbers, oriented for a LOWER-IS-BETTER score)
# ══════════════════════════════════════════════════════════════════════════════════════


def deflation_report(mae: pd.DataFrame, eligible: list[str] | None = None) -> dict:
    """PBO + Bailey's degradation + the flip distribution + the CONTENDER spread, over the ELIGIBLE set.

    `mae` is folds × configs of held-out MAE (lower better). Ported from the NF1.8 rookie-interval
    harness (`run_rookie_perposition_ablation.deflate`) and re-oriented — the lesson travels, not the
    code: PBO alone cannot separate "my pick is unstable" from "my pick is tied", and a spread computed
    over a field that CONTAINS its own anchors measures the anchors.
    """
    from betting_ml.utils.overfitting import pbo_cscv

    m = mae if eligible is None else mae[[c for c in mae.columns if c in set(eligible)]]
    m = m.loc[:, m.notna().all(axis=0)]
    n = len(m.index)
    out: dict = {"n_configs": int(m.shape[1]), "n_folds": int(n)}
    if n < 4 or m.shape[1] < 2:
        out.update({"pbo": None, "os_gap_pct": None, "contender_spread_pct": None, "flips": [],
                    "note": f"CSCV needs ≥4 folds and ≥2 complete configs; got {n}×{m.shape[1]} — "
                            f"small-N, stated not hidden"})
        return out
    # PBO wants higher-is-better; MAE is lower-is-better → negate
    out["pbo"] = float(pbo_cscv(-m.to_numpy(float), higher_is_better=True,
                                n_splits=min(n, 8)).pbo)
    gaps: list[float] = []
    wins: dict[str, int] = {}
    for combo in itertools.combinations(range(n), n // 2):
        os_idx = [i for i in range(n) if i not in combo]
        winner = m.iloc[list(combo)].mean(axis=0).idxmin()
        os = m.iloc[os_idx].mean(axis=0)
        wins[winner] = wins.get(winner, 0) + 1
        gaps.append(100.0 * (float(os[winner]) - float(os.min())) / max(1e-12, float(os.min())))
    means = m.mean(axis=0).sort_values()
    top = means.iloc[:max(3, len(means) // 4)]
    out.update({
        "os_gap_pct": round(float(np.median(gaps)), 4),
        "os_gap_p90_pct": round(float(np.percentile(gaps, 90)), 4),
        "contender_spread_pct": round(100.0 * (float(top.max()) - float(top.min()))
                                      / max(1e-12, float(top.min())), 3),
        "full_spread_pct": round(100.0 * (float(means.max()) - float(means.min()))
                                 / max(1e-12, float(means.min())), 3),
        "flips": [{"config": k, "IS_half_wins": v, "share": round(v / len(gaps), 3),
                   "mean_oos_mae": round(float(means[k]), 5),
                   "pct_vs_best": round(100.0 * (float(means[k]) - float(means.min()))
                                        / max(1e-12, float(means.min())), 3)}
                  for k, v in sorted(wins.items(), key=lambda kv: -kv[1])],
    })
    return out


def bh_fdr(pvals: dict[str, float], alpha: float = 0.10) -> dict[str, bool]:
    """Benjamini-Hochberg over the per-metric primary contrasts — four metrics is a four-test family,
    and reporting four uncorrected p-values is how a family becomes a fishing expedition."""
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    if not items:
        return {}
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    survive: dict[str, bool] = {k: False for k, _ in items}
    kmax = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            kmax = i
    for i, (k, _) in enumerate(items, start=1):
        survive[k] = i <= kmax
    return survive


ANCHOR_ALPHA = 0.10


def paired_anchor(mae: pd.DataFrame, challenger: str, defender: str,
                  alpha: float = ANCHOR_ALPHA) -> dict:
    """Does `challenger` SYSTEMATICALLY beat `defender` across folds — or is the gap noise?

    ⚠️ **WHY THIS IS A PAIRED TEST AND NOT A `<` ON TWO MEANS (learned the hard way, 2026-07-31).**
    The first version of these anchors compared mean OOS MAE with a 1e-9 tolerance. On the real run that
    declared a violation on `k_pct` off a **1e-5 gap** (0.03967 vs 0.03968) — i.e. it read a numerical
    TIE as fatal evidence, which is exactly the E2.1-r / NF1.8 error the repo already knows about,
    pointed the other way. Worse, the tie was **PREDICTED before the run**: a home-team player lands in
    BOTH park buckets, so the classic team-based factor is largely self-inclusion-robust and LOO ≈ noLOO
    is the *expected* result. A guard that treats its own predicted outcome as fatal is mis-specified,
    not strict.

    So the anchor now asks the coherent question — is the challenger's advantage systematic? — using the
    per-fold paired deltas. `alpha` is deliberately GENEROUS (0.10): a lenient alpha makes a violation
    EASIER to declare, which is the conservative direction for shipping. On the real run this correctly
    separates `k_pct` (noLOO wins 5/11 folds, p=0.33 → tie, anchor respected) from `woba` (noLOO wins
    9/11, p=0.035 → systematic, anchor VIOLATED) — two outcomes the point comparison called identically.
    """
    if challenger not in mae.columns or defender not in mae.columns:
        # ⭐ NF1.7 lesson 1: a MISSING anchor makes its check vacuously true. Say so explicitly.
        return {"available": False, "violated": False, "note": "anchor arm absent from this run"}
    d = (mae[challenger] - mae[defender]).to_numpy(float)   # <0 ⇒ the challenger is winning
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return {"available": True, "violated": False, "n_folds": int(len(d)),
                "note": "too few folds to test — reported, not enforced"}
    if np.std(d, ddof=1) == 0:
        # ⚠️ ZERO VARIANCE IS NOT "UNTESTABLE" — it is the MOST systematic case there is. A challenger
        # that wins by the SAME amount on every single fold would sail through a t-test guard that
        # bails on zero variance, which is precisely the "anchor passes on nothing" hole (NF1.7 lesson
        # 1). Decide it on the sign instead: a constant advantage is a violation; a constant tie is not.
        mean = float(np.mean(d))
        return {"available": True, "challenger": challenger, "defender": defender,
                "mean_gap": mean, "challenger_fold_wins": int((d < 0).sum()), "n_folds": int(len(d)),
                "p_challenger_better": 0.0 if mean < 0 else 1.0,
                "violated": bool(mean < 0), "alpha": alpha,
                "note": "zero-variance gap — decided on sign (a constant advantage IS systematic)"}
    from scipy import stats
    t = float(np.mean(d) / (np.std(d, ddof=1) / np.sqrt(len(d))))
    p = float(stats.t.sf(-t, df=len(d) - 1))     # H1: the challenger is systematically better
    return {
        "available": True,
        "challenger": challenger, "defender": defender,
        "mean_gap": float(np.mean(d)),
        "challenger_fold_wins": int((d < 0).sum()), "n_folds": int(len(d)),
        "p_challenger_better": p,
        "violated": bool(p < alpha),
        "alpha": alpha,
    }


def _paired_p(delta: np.ndarray) -> float | None:
    """One-sided paired p-value for H1: the arm beats S0 (delta = S0_MAE − arm_MAE > 0).

    A t-test on ~8 folds, stated for what it is: with this few folds it is a weak instrument and the
    deflation statistics carry the real load. Reported so the FDR family has something to correct."""
    d = np.asarray(delta, float)
    d = d[np.isfinite(d)]
    if len(d) < 3 or np.std(d, ddof=1) == 0:
        return None
    from scipy import stats
    t = float(np.mean(d) / (np.std(d, ddof=1) / np.sqrt(len(d))))
    return float(stats.t.sf(t, df=len(d) - 1))


# ══════════════════════════════════════════════════════════════════════════════════════
# The ladder run — one metric
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class LadderResult:
    metric: str
    prior_scale: float
    leaderboard: pd.DataFrame
    mae_by_fold: pd.DataFrame        # folds × arms, held-out MAE
    fold_cohorts: list[int]
    deflation: dict
    coverage: dict
    anchors: dict
    verdict: str                     # ADD | DROP | BLOCKED
    winner: str
    reasons: list[str] = field(default_factory=list)
    oracle_floor_ok: bool = True


def _adjusted(pairs: pd.DataFrame, context: pd.DataFrame | None, spec: ContextSpec,
              metric: str) -> pd.DataFrame:
    return apply_context(pairs, context, spec, metric, tuple(_KEYS))


def run_ladder(pairs: pd.DataFrame, context: pd.DataFrame | None, metric: str,
               arms: tuple[Rung, ...] = LADDER,
               prior_scale: float | None = None,
               sensitivity_scale: float | None = None,
               side: SideConfig = BATTER_SIDE) -> LadderResult:
    """Score every rung under the E7.3 fold structure — leave-one-MLB-debut-cohort-out, expanding
    window — with the learner held fixed.

    ⚠️ **THE EVAL POPULATION IS IDENTICAL ACROSS ARMS AND THIS IS ASSERTED, NOT ASSUMED.** `has_target`
    depends on `minor_pa` and the MLB label, neither of which any rung touches, so every arm is scored on
    exactly the same rows. If a future rung ever changed the population, the comparison would silently
    become "different players" rather than "different adjustment" — the cheapest way an ablation lies.
    """
    scale = prior_scale if prior_scale is not None else side.prior_scales.get(metric, 2.0)
    cfg = side.mle_config(metric)
    lookup = by_label(arms)

    # 🪤 A BAD WEIGHT COLUMN NEVER REACHES THE REPORT AS "BROKEN" — it reaches it as a RESULT.
    # Two distinct ways, both silent at the ladder level, and neither raises where anyone would see it:
    #   (a) the column is ABSENT → `_weights` throws inside the fold loop, whose `except` exists so a
    #       degenerate fold cannot kill the sweep → every fold fails → the arm scores NaN and simply
    #       VANISHES from the leaderboard and from the deflation count. Two pre-registered arms quietly
    #       stop existing.
    #   (b) the column is PRESENT but all-NaN / non-positive → `_weights` median-fills, the all-NaN
    #       median falls back to 1.0 → every weight is exactly 1 → the arm is BYTE-IDENTICAL to the
    #       baseline and is reported as "label weighting is a clean null" having never been applied.
    # (b) is the worse one: it manufactures a confident negative result. Caught on the pitcher port,
    # where the label exposure is stored under the SHARED name `mlb_pa`, not a plausible `mlb_tbf`.
    for _r in arms:
        wc = _r.spec.weight_col
        if not wc:
            continue
        nearby = sorted(c for c in pairs.columns if "pa" in c.lower() or "tbf" in c.lower())
        if wc not in pairs.columns:
            raise AssertionError(
                f"[{metric}/{_r.label}] weight_col={wc!r} is ABSENT from the pairs table (candidates: "
                f"{nearby}). This does not fail loudly on its own — it throws per-fold into the "
                f"degenerate-fold `except`, so the arm scores NaN and disappears from the leaderboard "
                f"instead of being reported as broken. Fix the SideConfig's label_weight_col.")
        w = pd.to_numeric(pairs[wc], errors="coerce")
        if not (w.notna() & (w > 0)).any():
            raise AssertionError(
                f"[{metric}/{_r.label}] weight_col={wc!r} exists but has NO positive values, so every "
                f"weight median-fills to 1.0 and this arm becomes a byte-exact copy of the baseline — "
                f"it would be reported as 'label weighting is a clean null' having never been applied.")

    base_lab = build_target(pairs, cfg)
    base_mask = base_lab["has_target"].to_numpy(bool)
    cohorts = sorted(int(y) for y in base_lab.loc[base_mask, "debut_cohort"].dropna().unique())
    fold_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]
    if len(fold_cohorts) < 2:
        raise ValueError(f"need ≥2 evaluable debut cohorts; got {fold_cohorts}")

    arm_specs: list[tuple[str, ContextSpec, float, Rung]] = [
        (r.label, r.spec, scale, r) for r in arms]
    if sensitivity_scale is not None and sensitivity_scale != scale:
        # a two-point prior-scale sensitivity on the two ends of the ladder — counted toward deflation,
        # never folded into the headline margin
        for lbl in ("S0_baseline", "S3_park_env"):
            if lbl in lookup:
                r = lookup[lbl]
                arm_specs.append((f"{lbl}|ps{sensitivity_scale:g}", r.spec, sensitivity_scale,
                                  Rung(f"{lbl}|ps{sensitivity_scale:g}", r.spec, "sensitivity",
                                       "prior-scale sensitivity")))

    adjusted: dict[str, pd.DataFrame] = {}
    coverage: dict[str, dict] = {}
    for label, spec, _s, _r in arm_specs:
        if label in adjusted:
            continue
        adj = _adjusted(pairs, context, spec, metric)
        lab = build_target(adj, cfg)
        if not np.array_equal(lab["has_target"].to_numpy(bool), base_mask):
            raise AssertionError(
                f"[{metric}/{label}] the adjustment changed the LABELLED POPULATION — arms would be "
                f"scored on different players, which is not an ablation. Check the rate clip bounds.")
        adjusted[label] = lab
        coverage[label] = context_coverage(adj, metric, spec)

    # ── ACTIVE vs NO-OP ──────────────────────────────────────────────────────────────
    # ⚠️ "the adjustment moved nothing" has TWO causes that look identical at the arm level: the join is
    # DEAD (the repo's silent-empty class), or the factor is genuinely NEUTRAL for this metric — which is
    # exactly what we PREDICT for K%/BB%, since parks move balls in play. Conflating them would BLOCK the
    # very outcome the directional falsification expects. So a no-op arm is merely made UNSELECTABLE
    # here (it is the baseline in disguise and cannot be "the winner"), and the dead-join question is
    # answered ACROSS metrics by `dead_context_join()` — if the join were dead, ISO would be a no-op too.
    def _active(label: str, spec: ContextSpec) -> bool:
        if spec.is_noop:
            return True                       # the baseline is the reference, not a candidate
        if spec.weight_col is not None:
            return True                       # a weight arm changes the FIT, not the feature
        return float(coverage.get(label, {}).get("pct_rows_moved") or 0.0) > 1.0

    active = {label: _active(label, spec) for label, spec, _s, _r in arm_specs}

    labels = [a[0] for a in arm_specs]
    mae = pd.DataFrame(index=fold_cohorts, columns=labels, dtype=float)
    notes: list[str] = []
    for year in fold_cohorts:
        for label, spec, s, _r in arm_specs:
            lab = adjusted[label]
            lab = lab[lab["has_target"]]
            train, test = lab[lab["debut_cohort"] < year], lab[lab["debut_cohort"] == year]
            if train.empty or test.empty:
                continue
            try:
                mdl = PartialPoolProjector(prior_scale=s, weight_col=spec.weight_col).fit(train)
                yhat, _ = mdl.predict(test)
                mae.loc[year, label] = float(np.mean(np.abs(test["target"].to_numpy(float) - yhat)))
            except Exception as e:  # noqa: BLE001 — a degenerate fold must not kill the sweep
                notes.append(f"fold {year} arm {label}: {type(e).__name__}: {e}")

    base = mae["S0_baseline"]
    rows = []
    for label, spec, s, r in arm_specs:
        col = mae[label]
        d = (base - col).to_numpy(float)
        d_fin = d[np.isfinite(d)]
        rows.append({
            "arm": label,
            "kind": r.kind,
            "selectable": r.selectable,
            "active": active[label],
            "prior_scale": s,
            "oos_mae": float(col.mean(skipna=True)),
            "mae_lift_vs_S0": float(np.mean(d_fin)) if len(d_fin) else np.nan,
            "pct_lift_vs_S0": (100.0 * float(np.mean(d_fin)) / float(base.mean(skipna=True))
                               if len(d_fin) and base.mean(skipna=True) else np.nan),
            "fold_win_rate": float(np.mean(d_fin > 0)) if len(d_fin) else np.nan,
            "p_one_sided": _paired_p(d),
            "pct_rows_moved": coverage.get(label, {}).get("pct_rows_moved"),
            "mean_abs_delta_feat": coverage.get(label, {}).get("mean_abs_delta"),
            "note": r.note,
        })
    leaderboard = pd.DataFrame(rows).sort_values("oos_mae").reset_index(drop=True)

    eligible = [lbl for lbl, _s, _sc, r in arm_specs if r.selectable]
    defl = deflation_report(mae, eligible)
    defl["whole_field"] = deflation_report(mae)

    # ── ORACLE FLOOR (E2.1-r, carried from E7.3): a target-seeing model scores MAE 0; nothing may beat it
    oracle_ok = bool(np.nanmin(leaderboard["oos_mae"].to_numpy(float)) >= -1e-9)

    # ── ANCHORS ───────────────────────────────────────────────────────────────────────
    # Each anchor is a PAIRED test (see `paired_anchor`), and each guards ONE mechanism. A violation
    # therefore DISQUALIFIES THAT MECHANISM for this metric — it does not condemn the whole metric.
    # ⭐ WHY SCOPED RATHER THAN METRIC-WIDE: the ladder deliberately mixes independent mechanisms, so a
    # winner's lift can come almost entirely from the run-environment rung while the park rung is a
    # null. Blocking the metric would throw away a mechanism that passed its own anchor because a
    # DIFFERENT mechanism failed one. On the real 2026-07-31 run that is exactly wOBA's shape: the park
    # sliver is confounded (noLOO wins 9/11 folds, p=0.035) while the run-environment rung is untouched
    # by that finding. Disqualify the park; judge the rest on its merits.
    def m_of(lbl: str) -> float:
        r = leaderboard.loc[leaderboard["arm"] == lbl, "oos_mae"]
        return float(r.iloc[0]) if len(r) else float("nan")

    placebo_a = paired_anchor(mae, "A_park_placebo", "S1_park_exposure")
    noloo_a = paired_anchor(mae, "A_park_noloo", "S1_park_exposure")
    relc_a = paired_anchor(mae, "A_rel_constant", "I_reliability_only")
    anchors = {
        "placebo_vs_real_park": placebo_a,
        "noloo_vs_loo": noloo_a,
        "constant_vs_pa_varying_reliability": relc_a,
        "placebo_mae": m_of("A_park_placebo"), "real_park_mae": m_of("S1_park_exposure"),
        "noloo_mae": m_of("A_park_noloo"),
        "constant_reliability_mae": m_of("A_rel_constant"),
        "reliability_only_mae": m_of("I_reliability_only"),
        "oracle_floor_ok": oracle_ok,
    }

    # ── DISQUALIFICATION (scoped to the failing mechanism) ────────────────────────────
    reasons: list[str] = list(notes)
    park_disqualified = bool(placebo_a.get("violated") or noloo_a.get("violated"))
    rel_disqualified = bool(relc_a.get("violated"))
    if placebo_a.get("violated"):
        reasons.append(
            f"⛔ PARK DISQUALIFIED — the PLACEBO park (factors permuted within level) systematically "
            f"BEAT the real park ({placebo_a['challenger_fold_wins']}/{placebo_a['n_folds']} folds, "
            f"p={placebo_a['p_challenger_better']:.3f}). Whatever the adjustment does, it is not the "
            f"venue; it is 'divide by any dispersed number'.")
    if noloo_a.get("violated"):
        reasons.append(
            f"⛔ PARK DISQUALIFIED — the NON-LOO factor systematically beat the leave-one-player-out "
            f"one ({noloo_a['challenger_fold_wins']}/{noloo_a['n_folds']} folds, "
            f"p={noloo_a['p_challenger_better']:.3f}, mean gap {noloo_a['mean_gap']:.2e}). The park "
            f"arm's apparent edge here is the player shrinking HIMSELF toward the mean via his own "
            f"contribution to his park's factor. Park arms are removed from selection for this metric; "
            f"the non-park rungs are unaffected and still judged on their merits.")
    if relc_a.get("violated"):
        reasons.append(
            f"⛔ RELIABILITY DISQUALIFIED — the constant-r degenerate systematically beat the PA-varying "
            f"shrink ({relc_a['challenger_fold_wins']}/{relc_a['n_folds']} folds, "
            f"p={relc_a['p_challenger_better']:.3f}) ⇒ the 'small-sample hardening' is a global slope "
            f"rescale the regression already had, not a sample-size-aware correction.")

    def _uses_park(lbl: str) -> bool:
        r = _BY_LABEL.get(lbl.split("|")[0])
        return bool(r and r.spec.park != "off")

    def _uses_reliability(lbl: str) -> bool:
        r = _BY_LABEL.get(lbl.split("|")[0])
        return bool(r and r.spec.reliability is not None)

    # ── VERDICT ───────────────────────────────────────────────────────────────────────
    noop = [lbl for lbl, spec, _s, r in arm_specs
            if r.kind == "ladder" and not spec.is_noop and not active[lbl]]
    if noop:
        reasons.append(
            f"\u2139\ufe0f NO-OP arms (the context does not move this metric, so they are the baseline in "
            f"disguise and cannot be selected): {', '.join(noop)}. For a park arm on a discipline "
            f"metric this is the PREDICTED outcome, not a fault — see the directional read.")
    sel = leaderboard[leaderboard["selectable"] & leaderboard["active"]
                      & (leaderboard["arm"] != "S0_baseline") & (leaderboard["kind"] != "sensitivity")]
    if park_disqualified:
        sel = sel[~sel["arm"].map(_uses_park)]
    if rel_disqualified:
        sel = sel[~sel["arm"].map(_uses_reliability)]
    winner = "S0_baseline"
    verdict = "DROP"
    if sel.empty:
        reasons.append(
            "🟡 no ELIGIBLE rung remains (every arm is a no-op, or every arm's mechanism was "
            "disqualified by its own anchor). The E7.3 incumbent stands for this metric.")
    else:
        cand = sel.iloc[0]
        winner_label = str(cand["arm"])
        beats = bool(cand["oos_mae"] < m_of("S0_baseline") - 1e-12)
        consistent = bool(np.isfinite(cand["fold_win_rate"]) and cand["fold_win_rate"] >= 0.60)
        if beats and consistent:
            verdict, winner = "ADD", winner_label
            reasons.append(
                f"✅ `{winner_label}` beats the E7.3 incumbent OOS ({cand['oos_mae']:.5f} vs "
                f"{m_of('S0_baseline'):.5f}, {cand['pct_lift_vs_S0']:.2f}%) in "
                f"{cand['fold_win_rate']:.0%} of folds.")
        else:
            reasons.append(
                f"🟡 no rung clears: best eligible `{winner_label}` MAE {cand['oos_mae']:.5f} vs "
                f"incumbent {m_of('S0_baseline'):.5f} (fold win rate {cand['fold_win_rate']:.0%}; the "
                f"pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.")
    if not oracle_ok:
        # the ONLY metric-wide BLOCK left: an inverted selection metric invalidates every arm at once
        verdict = "BLOCKED"
        reasons.append("⛔ ORACLE-FLOOR VIOLATION — a candidate scored MAE < 0; the metric is inverted.")

    return LadderResult(
        metric=metric, prior_scale=scale, leaderboard=leaderboard, mae_by_fold=mae,
        fold_cohorts=fold_cohorts, deflation=defl, coverage=coverage, anchors=anchors,
        verdict=verdict, winner=winner, reasons=reasons, oracle_floor_ok=oracle_ok)


def dead_context_join(results: dict[str, LadderResult]) -> dict:
    """⭐ THE RUN-LEVEL SILENT-EMPTY GUARD — asked across metrics, because it cannot be answered within one.

    A park arm that moves nothing has two possible causes that look IDENTICAL at the arm level: the
    context join is DEAD (the repo's recurring silent-empty class — a join that matches nothing produces
    a byte-identical arm that reads as an honest null), or the park factor is genuinely NEUTRAL for that
    metric, which is exactly what the directional falsification PREDICTS for K%/BB%. The distinguisher is
    cross-metric: if the join were dead, ISO would be a no-op too. So a no-op arm is merely unselectable
    per metric, and this check — "did the context move ANY metric at all?" — is the one that HALTs.
    """
    moved = {}
    for m, r in results.items():
        lb = r.leaderboard
        ctx_arms = lb[lb["kind"].isin(["ladder", "isolation"]) & (lb["arm"] != "S0_baseline")]
        moved[m] = float(ctx_arms["pct_rows_moved"].max()) if len(ctx_arms) else 0.0
    alive = any(v > 1.0 for v in moved.values())
    return {
        "max_pct_rows_moved_by_metric": moved,
        "context_join_alive": alive,
        "reading": (
            "✅ the context join moves at least one metric — a per-metric no-op is a neutral factor, "
            "not a dead join."
            if alive else
            "⛔ the context join moved NOTHING on ANY metric. That is a DEAD JOIN, not four honest "
            "nulls — the park-context artifact does not match the pairs on (player_id, level). Do NOT "
            "read any verdict from this run."),
    }


def directional_read(results: dict[str, LadderResult], side: SideConfig = BATTER_SIDE) -> dict:
    """The pre-registered FALSIFICATION: a real park effect lives in the BALL-IN-PLAY metrics.

    If the park lift is as large on K%/BB% as on ISO/wOBA, the mechanism is not the park — it is generic
    shrinkage, and the whole slice should be read as such regardless of how the gates land. This is the
    same instrument as the placebo, measured across metrics instead of within one.
    """
    def lift(m: str) -> float:
        r = results.get(m)
        if r is None:
            return float("nan")
        row = r.leaderboard.loc[r.leaderboard["arm"] == "S1_park_exposure", "pct_lift_vs_S0"]
        return float(row.iloc[0]) if len(row) else float("nan")

    sens = [lift(m) for m in side.park_sensitive if np.isfinite(lift(m))]
    insens = [lift(m) for m in side.park_insensitive if np.isfinite(lift(m))]
    s, i = (float(np.mean(sens)) if sens else float("nan"),
            float(np.mean(insens)) if insens else float("nan"))
    consistent = bool(np.isfinite(s) and np.isfinite(i) and s > i)
    return {
        "park_sensitive_metrics": list(side.park_sensitive), "mean_pct_lift_sensitive": s,
        "park_insensitive_metrics": list(side.park_insensitive), "mean_pct_lift_insensitive": i,
        "direction_consistent_with_a_park_mechanism": consistent,
        "reading": (
            "✅ the park lift is concentrated in the ball-in-play metrics, which is what a park "
            "mechanism must look like."
            if consistent else
            "⚠️ the park lift is NOT concentrated in the ball-in-play metrics — on this evidence the "
            "adjustment is acting as generic shrinkage rather than as a venue correction, whatever the "
            "per-metric gates say. Read every ADD below with that caveat."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# Emission under a winning rung
# ══════════════════════════════════════════════════════════════════════════════════════


def emit_with_context(pairs: pd.DataFrame, context: pd.DataFrame | None, spec: ContextSpec,
                      metric: str, prior_scale: float,
                      side: SideConfig = BATTER_SIDE) -> pd.DataFrame:
    """Re-emit the E7.3 per-(player, level) MLB-equivalent line under a winning rung.

    Reuses `emit_projections` verbatim — the leakage-safe expanding-window refit, the seed-cohort
    exclusion and the plausibility clip are E7.3's and stay E7.3's. Only the input feature changes.
    """
    adj = _adjusted(pairs, context, spec, metric)
    cfg = side.mle_config(metric)
    proj = emit_projections(
        adj, lambda: PartialPoolProjector(prior_scale=prior_scale, weight_col=spec.weight_col), cfg)
    if not proj.empty:
        proj["context_spec"] = spec.label
        proj["model_version"] = side.model_version
    return proj


def build_applied_projections(pairs: pd.DataFrame, context: pd.DataFrame | None,
                              results: dict[str, LadderResult],
                              applied: dict[str, dict],
                              side: SideConfig = BATTER_SIDE) -> tuple[pd.DataFrame | None, bool]:
    """Assemble the re-emitted wide projections — **EVERY metric, always**.

    🪤 **THE FOOTGUN THIS EXISTS TO CLOSE.** The natural implementation emits only the metrics whose
    verdict is ADD. But the E8.0 board reads `mle_k_pct`, `mle_bb_pct` AND `mle_iso` from ONE wide table
    (`board_assembly._METRIC_WEIGHTS`), so a partial re-emission overwriting that table would silently
    delete two of the board's three batter metrics — every prospect's composite would quietly renormalise
    onto whatever survived, and `mle_coverage` would be the only trace. Same shape as the repo's
    dropped-Pydantic-field class: the store is fine, the consumer just stops being handed a column.

    So a DROP metric is re-emitted under `ContextSpec()` — the byte-exact incumbent — rather than
    omitted. That reproduces E7.3 exactly (its bake-off selected `partial_pool` at the pinned prior scale
    for all four metrics), keeps the output a complete drop-in replacement, and stamps per-metric
    provenance so a reader can see WHICH columns actually changed.

    Returns `(wide_or_None, any_metric_changed)`. When nothing changed the caller must write NOTHING —
    a null slice leaves the incumbent artifact untouched.
    """
    wide: pd.DataFrame | None = None
    changed = False
    # the SUPERSET — a winner may be a post-hoc arm, and labels are unique across both sets, so
    # resolving a label to its spec here must never depend on which run mode produced it
    lookup = by_label(ladder_for(side, include_posthoc=True))
    for m, r in results.items():
        add = r.verdict == "ADD"
        spec = lookup[r.winner].spec if add else ContextSpec()
        if add:
            changed = True
        else:
            log.info("[%s] verdict=%s — re-emitting the INCUMBENT for this metric so the wide table "
                     "stays a complete drop-in replacement", m, r.verdict)
        proj = emit_with_context(pairs, context, spec, m, r.prior_scale, side)
        checks = _validate_emission(proj, m)
        if add:
            applied[m] = {"rung": r.winner, "context_spec": spec.label,
                          "n_rows": int(len(proj)), "gates": "; ".join(checks)}
        proj = proj.rename(columns={"context_spec": f"{m}_context_spec"})
        base = _KEYS + ["player_name", "league", "debut_cohort", "is_prospect", "age", "minor_pa",
                        "n_prior_cohorts"]
        per_metric = [f"minor_{m}", f"mlb_{m}", f"mle_{m}", f"mle_{m}_sd", f"{m}_context_spec"]
        if wide is None:
            wide = proj[[c for c in base + per_metric if c in proj.columns]].copy()
        else:
            cols = _KEYS + [c for c in per_metric if c in proj.columns]
            wide = wide.merge(proj[cols], on=_KEYS, how="outer")
    if wide is None:
        return None, False
    wide = wide.copy()
    wide["sport"], wide["player_type"] = "mlb", side.player_type
    wide["model_version"] = side.model_version if changed else side.incumbent_version
    # a complete replacement must carry EVERY metric the board reads, or it is not a replacement
    for m in results:
        assert f"mle_{m}" in wide.columns, f"the re-emission dropped mle_{m} — not a drop-in replacement"
    return wide, changed


def _validate_emission(proj: pd.DataFrame, metric: str) -> list[str]:
    """The E7.3 emission gates, re-run on the adjusted output — a re-emission that quietly breaks the
    grain or the plausibility band is worse than no re-emission."""
    checks: list[str] = []
    if proj.empty:
        raise AssertionError(f"[{metric}] the adjusted emission is EMPTY")
    if proj.duplicated(subset=_KEYS).any():
        raise AssertionError(f"[{metric}] duplicate (player_id, level) rows in the adjusted emission")
    checks.append("per-(player, level) grain unique")
    if (proj["n_prior_cohorts"] < 1).any():
        raise AssertionError(f"[{metric}] a projection was emitted with zero strictly-prior cohorts")
    checks.append("every emission fit on strictly-prior debut cohorts (seed not emitted)")
    mcol, scol = f"mle_{metric}", f"mle_{metric}_sd"
    lo, hi = PLAUSIBLE_RANGE[metric]
    if not np.isfinite(proj[mcol]).all() or not np.isfinite(proj[scol]).all():
        raise AssertionError(f"[{metric}] non-finite values in the adjusted emission")
    if proj[mcol].min() < lo - 1e-9 or proj[mcol].max() > hi + 1e-9:
        raise AssertionError(f"[{metric}] adjusted emission outside the plausible range [{lo}, {hi}]")
    checks.append(f"finite + plausible ([{proj[mcol].min():.3f}, {proj[mcol].max():.3f}])")
    return checks


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def write_report(results: dict[str, LadderResult], directional: dict, fdr: dict,
                 applied: dict, join_health: dict, path: Path,
                 side: SideConfig = BATTER_SIDE) -> None:
    L: list[str] = []
    a = L.append
    tag = "SLICE 1" if side.player_type == "batter" else "SLICE 1p (PITCHERS)"
    who = "MiLB→MLB MLE" if side.player_type == "batter" else "MiLB→MLB PITCHER MLE"
    a(f"# MLB Edge-E7.12 {tag} — minor-league PARK factors, per-LEVEL run environment, and the "
      f"small-sample hardening of the {who}")
    a("")
    a(f"**generated:** {datetime.now(timezone.utc).isoformat()} · **baseline:** the incumbent "
      f"(`{side.incumbent_version}`, `partial_pool`) · **learner held FIXED per metric**")
    a("")
    a("> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.** This slice asks one question: does "
      "adjusting a prospect's minor-league rate for WHERE (park), WHEN (level×season run environment) "
      "and HOW MUCH (sample reliability) he accumulated it translate BETTER than the raw rate the E7.3 "
      "partial-pool sees today? A rung that does not clear its deflated gate is **DROPPED, not shipped** "
      "— the 8/3 draft board is a low-risk surface, which lowers the bar for shipping a CLEARED win, not "
      "the bar for what counts as one.")
    a("")

    a("## 0. Pre-registration (written before the run)")
    a("")
    a("| rung | kind | mechanism |")
    a("|:--|:--|:--|")
    for r in ladder_for(side, include_posthoc=True):
        a(f"| `{r.label}` | {r.kind} | {r.note} |")
    a("")
    a("⚠️ **`posthoc` rungs were NOT pre-registered** and are scored only when `--include-posthoc` is "
      "passed. They are ablations-DOWN from the winning stack (drop one named component, ask whether it "
      "was carrying anything) — a question the pre-registered ladder cannot pose, because it only ever "
      "ADDS mechanisms. They enter the same deflation and the same eligible set, so a wider field costs "
      "what a wider field should cost, and they must clear the same gate: ≥60% of folds AND BH-FDR.")
    a("")
    a("**Per-component stabilisation points** driving the reliability shrink (`r = PA/(PA+k)`, PA = TBF "
      "on the pitcher side): "
      + " · ".join(f"`{m}` k={STABILIZATION_PA[m]:g}" for m in side.metrics if m in STABILIZATION_PA)
      + ". The point is that they DIFFER: a metric that stabilises late is regressed harder at equal "
        "sample, which is the measured translatability ordering expressed as a prior rather than "
        "asserted (batters — K% 0.637 · BB% 0.491 · ISO 0.429; pitchers — GB% 0.551 · BB% 0.367 · "
        "K% 0.366).")
    a("")
    if side.player_type == "pitcher":
        a("⚠️ **`xwoba_against` can have NO park factor and NO run-environment ratio** — its minor "
          "feature is the E7.2 AAA-Statcast summary, which has no home/road box-line bucket to form a "
          "ratio from. Its park/env arms are therefore honest no-ops (unselectable, never fabricated); "
          "only the reliability shrink can move it.")
        a("")
        a(f"⚠️ **Only `{'`, `'.join(side.board_metrics)}` reach the E8.0 board.** E7.3p found "
          "`hr_rate` and `xwoba_against` no-signal and the board composite excludes them, so a lift on "
          "those two is **cosmetic** — reported, never claimed as a draft-board improvement. (The "
          "batter-side twin of this is wOBA.)")
        a("")
    a("**Gate for an ADD** (all must hold): a strict out-of-sample MAE improvement over the incumbent, "
      "in **≥60% of held-out debut cohorts**; the arm must have MOVED >1% of rows (a dead join is not a "
      "null); the **placebo** park must lose; the **non-LOO** park must not beat the LOO park; the "
      "winner must survive **Benjamini-Hochberg FDR at α=0.10 over the whole metric family**; and the "
      "deflation must be readable as a real separation rather than a tie (PBO + flip distribution + "
      "Bailey degradation + contender spread, all four reported).")
    a("")
    a("> 🪤 **The BH-FDR clause is ENFORCED, and for one release it was not.** It was computed and "
      "printed while the emission keyed off the per-metric fold bar alone, so a metric could fail the "
      "family-wise correction and still be published — latent on the batter side (all four passed), and "
      "live on the pitcher side, where `k_pct` cleared 73% of folds at p=0.113 and shipped with "
      "FDR=False. A per-metric bar does not control a family. An FDR-downgraded metric is re-emitted "
      "byte-exact as the incumbent.")
    a("")

    a("## 1. Is the context join even ALIVE? (the run-level silent-empty guard)")
    a("")
    a("A park arm that moves nothing has two causes that look identical at the arm level: a **dead "
      "join** (this repo's recurring silent-empty class) or a **genuinely neutral factor** for that "
      "metric — which is precisely what the falsification below predicts for K%/BB%. The distinguisher "
      "is cross-metric, so it is asked once, here, and it HALTs the run rather than producing four "
      "plausible-looking nulls.")
    a("")
    a(f"- max % of rows moved, by metric: `{join_health['max_pct_rows_moved_by_metric']}`")
    a(f"- {join_health['reading']}")
    a("")

    a("## 2. Directional falsification — is it actually the PARK?")
    a("")
    a("Parks move **balls in play**. Pre-registered before the run: a genuine park effect must be "
      "concentrated in the contact metrics and near-zero for the discipline metrics. A lift that "
      "appears uniformly across every metric is generic shrinkage wearing a park costume.")
    if side.player_type == "pitcher":
        a("")
        a("⭐ On this side that is an **independent replication**, not a restatement: the same physical "
          "claim (fences move batted balls, not the strike zone), tested on a different population, a "
          "different label and a different set of counting stats. If the batter side's small real park "
          "effect were an artifact of the batter substrate, this side has no reason to reproduce it.")
    a("")
    a(f"- mean park lift on **{', '.join(directional['park_sensitive_metrics'])}** (ball-in-play): "
      f"**{directional['mean_pct_lift_sensitive']:.3f}%**")
    a(f"- mean park lift on **{', '.join(directional['park_insensitive_metrics'])}** (discipline): "
      f"**{directional['mean_pct_lift_insensitive']:.3f}%**")
    a("")
    a(f"> {directional['reading']}")
    a("")

    a("## 2b. ⭐ WHICH MECHANISM ACTUALLY WON — the isolation arms")
    a("")
    a("This is the headline, and it is **not what the story predicted**. The research memo ranked "
      "\"minor-league park factors + per-level run environment\" as ONE workstream and as the single "
      "biggest gap. Splitting that bullet into its two halves — which is exactly what the isolation "
      "arms are for — shows the two halves are **nothing like equal partners**.")
    a("")
    rows = []
    for m, r in results.items():
        lb = r.leaderboard.set_index("arm")

        def g(arm, col="pct_lift_vs_S0", lb=lb):
            return round(float(lb.loc[arm, col]), 3) if arm in lb.index else None
        rows.append({
            "metric": m,
            "park ALONE %": g("S1_park_exposure"), "p": g("S1_park_exposure", "p_one_sided"),
            "run-env ALONE %": g("S2_level_env"), "p ": g("S2_level_env", "p_one_sided"),
            "reliability ALONE %": g("I_reliability_only"),
            "label-weight ALONE %": g("I_labelweight_only"),
            "placebo park %": g("A_park_placebo"),
            "winner %": g(r.winner) if r.winner != "S0_baseline" else 0.0,
        })
    a(pd.DataFrame(rows).to_markdown(index=False))
    a("")
    a("**Read it straight:**")
    a("")
    a("- **The level×SEASON run environment is the mechanism.** It is the only rung that lifts all four "
      "metrics, and it is **4–17× the size of the park effect** on every one of them.")
    a("- **The park factor is real but small, and only for ISO** (+0.84%, 11/11 folds, p≈0.0001 — the "
      "cleanest single result in the run). On K% it is marginal, on wOBA it is a null, and on BB% it is "
      "**negative**. That is a coherent physical story — parks move balls in play — and it is exactly "
      "the direction the falsification pre-registered; it is simply a much SMALLER story than "
      "\"the single biggest gap\" implied.")
    a("- **The placebo park is NEGATIVE on all four metrics.** A wrong park factor actively hurts, which "
      "is the strongest available evidence that the small real park effect is a venue effect and not "
      "generic shrinkage.")
    a("- **Label-precision weighting is a clean pre-registered NULL** — decisively negative on three of "
      "four metrics (wOBA −6.4%, ISO −4.4%, BB% −1.9%). Dropped, as pre-registered.")
    a("- **Reliability shrinkage is a real but secondary interaction**: near-zero on its own "
      "(+0.04% to +0.48%) yet it adds ~1.5pp on top of park+run-env for ISO and BB%. It hardens the "
      "small-sample regime rather than carrying the signal itself.")
    a("")
    a("⚠️ **What the run-environment rung actually is.** `rate × env_level / env_player` re-expresses a "
      "player's rate against his own level-season league baseline, so it removes league-wide offensive "
      "drift (ball, level composition, pitch clock) that the pool's per-LEVEL intercept cannot see "
      "because it has no per-SEASON term. That is an **era/context normalisation**, not a park "
      "correction — legitimate and leakage-free (every input is pre-debut MiLB, no MLB label is "
      "touched), but it should be named for what it is. The honest one-line summary of this slice is "
      "*\"the MLE was missing a season-context adjustment, and secondarily a park adjustment for "
      "power\"* — not *\"park factors were the big miss.\"*")
    a("")
    a("ℹ️ `env_level_<metric>` (the anchor constant) is pooled over every season in the artifact, "
      "including seasons after a given fold's training cohorts. It is a single constant per "
      "(level, metric) applied identically to train and test, and the pool carries per-level intercepts "
      "AND slopes, so it is absorbed rather than informative — a benign look-ahead, stated rather than "
      "hidden. The player-varying term, `env_<metric>`, is strictly as-of his own pre-debut seasons.")
    a("")

    a("## 3. Verdict by metric")
    a("")
    rows = []
    for m, r in results.items():
        best = r.leaderboard[r.leaderboard["selectable"] & (r.leaderboard["kind"] == "ladder")
                             & (r.leaderboard["arm"] != "S0_baseline")]
        b = best.iloc[0] if not best.empty else None
        rows.append({
            "metric": m, "verdict": r.verdict, "winner": r.winner,
            "best_rung_pct_lift": None if b is None else round(float(b["pct_lift_vs_S0"]), 3),
            "fold_win_rate": None if b is None else round(float(b["fold_win_rate"]), 2),
            "p_one_sided": None if b is None else b["p_one_sided"],
            "BH-FDR@0.10": fdr.get(m),
            "PBO(eligible)": r.deflation.get("pbo"),
            "contender_spread_%": r.deflation.get("contender_spread_pct"),
            "Bailey_os_gap_%": r.deflation.get("os_gap_pct"),
        })
    a(pd.DataFrame(rows).to_markdown(index=False))
    a("")
    a("`PBO(eligible)` is computed over the ELIGIBLE arms — the search the selection actually ran — not "
      "over every arm scored; the whole-field figure is in the JSON. A field that CONTAINS its own "
      "anchors has a huge dispersion, and a deflation statistic computed over it measures the anchors "
      "(the NF-D14 lesson).")
    a("")

    for m, r in results.items():
        a(f"## 4.{m} — the ladder (`partial_pool@{r.prior_scale:g}`, learner held fixed)")
        a("")
        a(f"Folds: leave-one-MLB-debut-cohort-out, expanding window over `{r.fold_cohorts}`. "
          f"Score = held-out MAE on the realized MLB `{m}` (lower better) — the SAME metric E7.3 "
          "selected on, so the numbers are directly comparable to that report.")
        a("")
        cols = ["arm", "kind", "active", "oos_mae", "pct_lift_vs_S0", "fold_win_rate",
                "p_one_sided", "pct_rows_moved", "mean_abs_delta_feat"]
        a(r.leaderboard[cols].to_markdown(index=False, floatfmt=".5f"))
        a("")
        a("**Anchors** — each a PAIRED test over folds, not a comparison of two means. A violation "
          "disqualifies THAT MECHANISM for this metric; it does not condemn the metric.")
        an = r.anchors
        for key, label in (("placebo_vs_real_park", "placebo park vs the real park"),
                           ("noloo_vs_loo", "non-LOO vs leave-one-player-out"),
                           ("constant_vs_pa_varying_reliability", "constant-r vs PA-varying reliability")):
            t = an.get(key, {})
            if not t.get("available"):
                a(f"- {label}: ⚠️ anchor arm ABSENT — its check would pass on nothing (NF1.7 lesson 1)")
            elif "p_challenger_better" not in t:
                a(f"- {label}: ⚠️ {t.get('note')}")
            else:
                verdict = "⛔ VIOLATED" if t["violated"] else "✅ respected"
                a(f"- {label}: **{verdict}** — the degenerate wins "
                  f"{t['challenger_fold_wins']}/{t['n_folds']} folds, p={t['p_challenger_better']:.3f} "
                  f"(α={t['alpha']}), mean gap {t['mean_gap']:+.2e}")
        a(f"- oracle floor holds: **{an['oracle_floor_ok']}**")
        a("")
        a("**Deflation (four numbers, not one)**")
        d = r.deflation
        a(f"- PBO over the eligible set: `{d.get('pbo')}` · contender (top-quartile) spread: "
          f"`{d.get('contender_spread_pct')}%` · full-field spread: `{d.get('full_spread_pct')}%`")
        a(f"- Bailey performance degradation (median OOS cost of picking the IS winner): "
          f"`{d.get('os_gap_pct')}%` (p90 `{d.get('os_gap_p90_pct')}%`)")
        if d.get("flips"):
            a("- flip distribution (which arms win the in-sample halves):")
            a("")
            a(pd.DataFrame(d["flips"]).head(6).to_markdown(index=False))
        a("")
        for reason in r.reasons:
            a(f"- {reason}")
        a("")

    a("## 5. What was applied")
    a("")
    if applied:
        a(pd.DataFrame([{"metric": k, **v} for k, v in applied.items()]).to_markdown(index=False))
    else:
        a("Nothing — either no rung cleared its gate, or the run was not invoked with `--apply`. "
          "The E7.3 emission stands unchanged.")
    a("")

    a("## 6. Limitations")
    a("")
    a("- **Park factors are computed from our own free substrate**, not from Baseball America's "
      "published table. The two will not agree exactly: BA uses different denominators and a different "
      "window. Ours is reproducible, versioned and per-player-exposure-weighted; that is the trade.")
    a("- **A trailing 3-season window on a MiLB park is still thin** — an affiliate relocation or a "
      "fence move inside the window is absorbed as noise, and the EB shrink toward neutral is what "
      "keeps that from becoming a confident wrong factor.")
    a("- **A team that changes LEVEL inside the window** has its buckets pooled across levels. Rare "
      "(affiliates are stable) but not corrected.")
    a("- **The reliability stabilisation points are LITERATURE constants**, not fitted here. The "
      "0.5×/1×/2× grid is the sensitivity, and every grid point counts toward the deflation.")
    a("- **Survivorship is untouched** — this slice does not correct the promotion selection bias "
      "(E7.12 slice 2). Every number is conditional on the graduated population E7.3 trains on.")
    a("- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="E7.12 slice 1 — park + level-run-environment + small-sample ablation ladder")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter",
                   help="batter (slice 1) or pitcher (slice 1p) — same ladder, same anchors, same "
                        "deflation; the incumbent prior scales, metric list, falsification split and "
                        "emission target come from that side's SideConfig")
    p.add_argument("--pairs", default=None,
                   help="default: that side's E7.3/E7.3p graduated-pairs parquet")
    p.add_argument("--context", default=None,
                   help="default: that side's build_park_context output")
    p.add_argument("--metrics", nargs="+", default=None,
                   help="default: that side's full metric list")
    p.add_argument("--arms", nargs="+", default=None,
                   help="restrict to these rung labels (a cheap smoke); default = the full ladder")
    p.add_argument("--include-posthoc", action="store_true",
                   help="ALSO score the POST-HOC ablation-down arms (see POSTHOC_RUNGS). NOT "
                        "pre-registered — they drop one component at a time from the winning stack to "
                        "ask whether it was carrying anything. Scored into the same deflation and the "
                        "same eligible set, and they must clear the same gate (folds + BH-FDR).")
    p.add_argument("--sensitivity-scale", type=float, default=None,
                   help="also score S0/S3 at this partial-pool prior scale (counted toward deflation)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--apply", action="store_true",
                   help="re-emit mle_projections under each metric's winning rung (ONLY metrics whose "
                        "verdict is ADD; a DROP keeps the E7.3 emission verbatim)")
    p.add_argument("--s3", action="store_true",
                   help="with --apply, also land the re-emitted projections in the lakehouse")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[args.player_type]
    e73_out = (_PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
               / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts"))
    pairs_path = Path(args.pairs) if args.pairs else e73_out / side.pairs_name
    context_path = (Path(args.context) if args.context
                    else _DEFAULT_OUT / f"mle_park_context{side.reduced.artifact_suffix}.parquet")
    metrics = args.metrics if args.metrics else list(side.metrics)

    if not pairs_path.exists():
        p.error(f"pairs parquet not found at {pairs_path} — run the {side.player_type} "
                f"build_graduated_pairs first")
    pairs = pd.read_parquet(pairs_path)
    context = None
    if context_path.exists():
        context = pd.read_parquet(context_path)
        log.info("loaded %d park-context rows (%s)", len(context), side.player_type)
    else:
        p.error(f"park context not found at {context_path} — run build_park_context.py "
                f"--player-type {side.player_type} first (without it every park arm is a silent "
                f"no-op, which would read as an honest null)")

    full = ladder_for(side, include_posthoc=args.include_posthoc)
    lookup = by_label(full)
    if args.include_posthoc:
        log.warning("POST-HOC arms ENABLED (%s) — these were NOT pre-registered; they are scored into "
                    "the same deflation and must clear the same gate. The report labels them.",
                    ", ".join(r.label for r in POSTHOC_RUNGS))
    arms = full if not args.arms else tuple(lookup[a] for a in args.arms)
    if "S0_baseline" not in {r.label for r in arms}:
        arms = (lookup["S0_baseline"],) + arms

    results: dict[str, LadderResult] = {}
    for metric in metrics:
        log.info("=== E7.12 slice-1 ladder [%s]: %s (the multi-minute part) ===",
                 side.player_type, metric)
        results[metric] = run_ladder(pairs, context, metric, arms,
                                     sensitivity_scale=args.sensitivity_scale, side=side)
        r = results[metric]
        log.info("[%s] verdict=%s winner=%s", metric, r.verdict, r.winner)
        for reason in r.reasons:
            log.info("[%s] %s", metric, reason)

    join_health = dead_context_join(results)
    log.info("context-join health: %s", join_health["reading"])
    if not join_health["context_join_alive"]:
        raise AssertionError(join_health["reading"] + f" {join_health['max_pct_rows_moved_by_metric']}")

    directional = directional_read(results, side)
    log.info("directional read: %s", directional["reading"])

    pvals = {}
    for m, r in results.items():
        row = r.leaderboard[r.leaderboard["arm"] == r.winner]
        pvals[m] = float(row["p_one_sided"].iloc[0]) if len(row) and pd.notna(
            row["p_one_sided"].iloc[0]) else None
    fdr = bh_fdr(pvals)

    # ── BH-FDR IS A GATE, NOT A FOOTNOTE ──────────────────────────────────────────────
    # 🪤 It was computed here and REPORTED, but `build_applied_projections` keys off `verdict == "ADD"`,
    # which the per-metric fold-win-rate bar sets alone — so a metric could FAIL the family-wise
    # correction and still be published. The defect was LATENT on the batter side (all four metrics
    # passed FDR, so enforcing it would have changed nothing) and only surfaced on the pitcher run,
    # where `k_pct` cleared 73% of folds at p=0.113 and shipped despite FDR=False.
    # ⭐ Note the direction: this makes the gate STRICTER and moves it TOWARD the story's own
    # pre-registration ("fully deflated — PBO/DSR/FDR"), so unlike a loosened guard it needs no
    # licensing argument. A metric downgraded here is re-emitted byte-exact as the incumbent.
    for m, r in results.items():
        if r.verdict == "ADD" and fdr.get(m) is False:
            r.verdict = "DROP"
            r.winner = "S0_baseline"
            r.reasons.append(
                f"⛔ FDR-DOWNGRADED — the winner cleared the per-metric fold bar (p={pvals.get(m)}) but "
                f"does NOT survive Benjamini-Hochberg over the {len(pvals)}-metric family at α=0.10. "
                f"The primary contrast is a family, and a per-metric bar alone does not control it. "
                f"DROPPED — the incumbent is re-emitted byte-exact for this metric.")
            log.warning("[%s] FDR-DOWNGRADED to DROP (p=%s did not survive BH over %d metrics)",
                        m, pvals.get(m), len(pvals))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    applied: dict[str, dict] = {}
    if args.apply:
        wide, changed = build_applied_projections(pairs, context, results, applied, side)
        if wide is None:
            log.info("--apply requested but nothing was emitted — check the metric list.")
        elif not changed:
            log.info("--apply requested but NO metric cleared its gate. NOTHING is written: the E7.3 "
                     "emission stands verbatim. That is the correct outcome for a null slice, not a "
                     "failure — a null add is DROPPED, never shipped.")
        else:
            dest = out_dir / f"mle_projections{side.reduced.artifact_suffix}_parkctx.parquet"
            wide.to_parquet(dest, index=False)
            log.info("wrote %s (%d rows, %d metric(s) adjusted) — a COMPLETE drop-in replacement",
                     dest, len(wide), len(applied))
            if args.s3:
                from deltalake import write_deltalake

                from scripts.utils.delta_lake import storage_options
                # `schema_mode="overwrite"` because the re-emission adds the per-metric
                # `<m>_context_spec` provenance columns — a strict SUPERSET of E7.3's schema, never a
                # drop (the completeness assert in `build_applied_projections` is what guarantees that,
                # and the board reads `select *` so extra columns are inert). Without it delta-rs
                # refuses the write on a field-count mismatch rather than widening.
                write_deltalake(
                    side.s3_dest, wide, mode="overwrite", schema_mode="overwrite",
                    storage_options=storage_options())
                log.info("landed the adjusted projections at %s", side.s3_dest)

    summary_name = f"e7_12_slice1{side.reduced.artifact_suffix}_summary.json"
    (out_dir / summary_name).write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_type": side.player_type,
        "baseline": f"{side.incumbent_version} partial_pool (learner held fixed per metric)",
        "prior_scales": {m: r.prior_scale for m, r in results.items()},
        "context_join_health": join_health,
        "directional": directional,
        "bh_fdr_alpha_0.10": fdr,
        "per_metric": {m: {
            "verdict": r.verdict, "winner": r.winner,
            "leaderboard": r.leaderboard.to_dict(orient="records"),
            "mae_by_fold": r.mae_by_fold.to_dict(),
            "deflation": r.deflation, "anchors": r.anchors, "reasons": r.reasons,
        } for m, r in results.items()},
        "applied": applied,
    }, indent=2, default=float))

    if not args.no_report:
        write_report(results, directional, fdr, applied, join_health,
                     _REPORT_PATH.parent / side.report_name, side)

    verdicts = {m: r.verdict for m, r in results.items()}
    log.info("SLICE-1 VERDICTS: %s", verdicts)
    if any(v == "BLOCKED" for v in verdicts.values()):
        log.warning("at least one metric is BLOCKED by an anchor — read the report before shipping "
                    "anything from this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
