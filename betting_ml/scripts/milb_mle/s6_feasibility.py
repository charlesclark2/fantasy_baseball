"""E7.12 SLICE 6 — AAA-Statcast feasibility MEMO (step 0). NOT a bake-off.

Run (LAPTOP, ~1 min per side):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.s6_feasibility \
        --player-type batter
    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.s6_feasibility \
        --player-type pitcher

WHY THIS IS A SCRIPT AND NOT A ONE-OFF ANALYSIS
---------------------------------------------------------------------------------------------------
The story prompt's own exit condition — "≤3 usable folds ⇒ record the ceiling and stop" — is a
statement about DATA that becomes false as AAA-Statcast accrues (coverage begins 2022 and adds one
debut cohort per season). A memo written as prose goes stale silently and nobody re-checks it. A
script makes the re-open trigger mechanical: run it again after a season completes and read whether
the fold count moved.

THE THREE QUESTIONS (verbatim from the prompt), AND HOW EACH IS ANSWERED
---------------------------------------------------------------------------------------------------
  (a) how many LABELLED rows carry `sc_*` PER DEBUT COHORT      → `coverage_census`
  (b) how many EVALUABLE folds survive that                     → `fold_viability`
  (c) is the design POWERED — the minimum detectable lift       → `measure_fold_noise` + `power_curve`

⭐ (c) IS ANSWERED AGAINST THE ACTUAL DECISION RULE, NOT A TEXTBOOK FORMULA. The thing that has to
detect the effect is not a generic t-test; it is this program's gate — fold-win-rate ≥ 0.60 AND a
positive mean lift AND survival of a one-sided paired t under BH-FDR, with PBO/CSCV on top. A
generic power formula would answer a question nobody is asking and would flatter the design, because
the real rule is strictly harder than any single one of its clauses. So the MDE here is SIMULATED
against the rule as it is coded (see `power_curve`), using a noise scale MEASURED on the real folds
rather than assumed.

⚠️ WHY MEASURING THE NOISE IS NOT PEEKING AT THE ANSWER. `measure_fold_noise` does fit the candidate
arm, because the dispersion of its per-fold deltas is the only honest input to an MDE. It reports the
DISPERSION. It also reports the point estimate — concealing a number already computed would be worse
than framing it — but wrapped in its confidence interval and explicitly marked uninterpretable,
because **a bake-off that cannot detect its own effect is not a null, it is an unpowered test, and
reporting it as a null retires a live mechanism on no evidence.** That sentence is the whole reason
this slice is gated.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.milb_mle import (
    PITCHER_STATCAST_COLS,
    STATCAST_COLS,
    PartialPoolProjector,
    build_target,
)
from betting_ml.scripts.milb_mle.park_context import apply_context
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES, SideConfig
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import shipped_spec

log = logging.getLogger("e7_12_s6_feasibility")

_KEYS = ["player_id", "level"]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ABLATION = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"

# A cohort with fewer than this many COVERED held-out rows cannot serve as a fold (story prompt).
MIN_FOLD_TEST_ROWS = 30
# CSCV/PBO — the §0.5 deflation instrument — is undefined below this many folds. `deflation_report`
# returns `pbo: None` and says so; that is a STRUCTURAL blocker, independent of any effect size.
MIN_FOLDS_FOR_PBO = 4
# The gate this program actually applies, mirrored here so the power simulation tests the real rule.
FOLD_WIN_GATE = 0.60
BH_ALPHA = 0.10
TARGET_POWER = 0.80

SC_COLS = {"batter": STATCAST_COLS, "pitcher": PITCHER_STATCAST_COLS}
_MISS_SUFFIX = "__miss"


@dataclass
class S6Feasibility:
    player_type: str
    sc_cols: tuple[str, ...]
    census: pd.DataFrame
    by_level: pd.DataFrame
    folds: pd.DataFrame
    usable_folds: list[int]
    noise: dict
    power: pd.DataFrame
    mde: dict
    verdict: str
    reopen: dict
    notes: list[str] = field(default_factory=list)


def coverage_census(lab: pd.DataFrame, sc_cols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(a) Labelled rows carrying ANY `sc_*` value, per debut cohort and per level.

    "Carries the block" is `.notna().any(axis=1)` rather than `.all()`: the block arrives as a unit
    from one source, and requiring every column would understate coverage over a partial scrape.
    """
    lab = lab.copy()
    lab["has_sc"] = lab[list(sc_cols)].notna().any(axis=1)
    census = (lab.groupby("debut_cohort")["has_sc"].agg(covered="sum", labelled="count")
              .astype(int).reset_index())
    census["pct"] = (100.0 * census["covered"] / census["labelled"]).round(1)
    by_level = (lab.groupby("level")["has_sc"].agg(covered="sum", labelled="count")
                .astype(int).reset_index())
    by_level["pct"] = (100.0 * by_level["covered"] / by_level["labelled"]).round(1)
    return census, by_level


def fold_viability(census: pd.DataFrame) -> pd.DataFrame:
    """(b) Which leave-one-debut-cohort-out folds can actually carry the mechanism.

    A fold Y trains on cohorts < Y and scores cohort Y, so it needs BOTH:
      * covered rows in the TRAINING window — otherwise the feature is all-missing at fit, the arm is
        byte-identical to the baseline, and the fold scores `delta = 0` which the `d > 0` fold test
        counts as a LOSS. **Scoring a mechanism on folds where it provably cannot act is not a
        stricter test, it is a broken one** (the S4 `ACTIVE_FOLD_MIN` lesson, which capped an
        achievable fold-win-rate at 0.636 against a 0.60 gate before it was caught);
      * at least `MIN_FOLD_TEST_ROWS` covered rows in the TEST cohort, or the fold's own MAE delta is
        a handful of players and contributes noise rather than evidence.
    """
    c = census.sort_values("debut_cohort").reset_index(drop=True)
    cum_prior = c["covered"].cumsum().shift(1).fillna(0).astype(int)
    rows = []
    for i, r in c.iterrows():
        year = int(r["debut_cohort"])
        if i == 0:
            continue  # the seed cohort has no strictly-prior training window at all
        train_cov, test_cov = int(cum_prior[i]), int(r["covered"])
        if train_cov == 0:
            status = "INERT (no covered TRAINING row — arm is byte-identical to baseline)"
        elif test_cov < MIN_FOLD_TEST_ROWS:
            status = f"THIN (<{MIN_FOLD_TEST_ROWS} covered held-out rows)"
        else:
            status = "USABLE"
        rows.append({"fold": year, "covered_train": train_cov, "covered_test": test_cov,
                     "labelled_test": int(r["labelled"]),
                     "pct_test_covered": round(100.0 * test_cov / max(int(r["labelled"]), 1), 1),
                     "status": status})
    return pd.DataFrame(rows)


def _with_missing_indicators(frame: pd.DataFrame, sc_cols: tuple[str, ...]
                             ) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Attach the block PLUS an explicit missing indicator per column.

    🚨 **THE LANDMINE THIS EXISTS TO AVOID, FLAGGED FOR WHOEVER EVENTUALLY RUNS THE BAKE-OFF.**
    `PartialPoolProjector._design` calls `s.transform(df)[0]` — it takes the standardized VALUE and
    DISCARDS the missing flag `_Scaler` returns beside it. So a row with no Statcast gets z = 0, which
    is the mean OF THE COVERED SUBSET: a fabricated neutral, asserted about ~88% of rows, and exactly
    what the story prompt forbids ("never fabricate a zero"). With the indicator present the model can
    offset that imputation instead of believing it. Any future S6 arm must carry these; passing the
    raw `sc_*` columns through `extra_cols` alone would quietly assert that every uncovered prospect
    is an average Triple-A batted-ball profile.
    """
    out = frame.copy()
    cols: list[str] = []
    for c in sc_cols:
        v = pd.to_numeric(out.get(c), errors="coerce")
        out[c] = v
        out[c + _MISS_SUFFIX] = v.isna().astype(float)
        cols += [c, c + _MISS_SUFFIX]
    return out, tuple(cols)


def measure_fold_noise(pairs: pd.DataFrame, park_ctx: pd.DataFrame | None, metric: str,
                       side: SideConfig, sc_cols: tuple[str, ...],
                       usable_folds: list[int]) -> dict:
    """(c-i) The per-fold MAE-delta DISPERSION — the only honest input to an MDE.

    Fits the incumbent and a properly-specified AAA-Statcast arm on the usable folds and returns the
    spread of their per-fold differences. See the module docstring on why this is a power measurement
    and not a verdict: the point estimate is returned, with its interval, marked uninterpretable.
    """
    base_spec = shipped_spec(side, metric)
    scale = side.prior_scales.get(metric, 2.0)
    adj = apply_context(pairs, park_ctx, base_spec, metric, tuple(_KEYS))
    lab = build_target(adj, side.mle_config(metric))
    lab = lab[lab["has_target"]].reset_index(drop=True)
    frame, extra = _with_missing_indicators(lab, sc_cols)

    deltas, base_maes = [], []
    for year in usable_folds:
        train, test = frame[frame["debut_cohort"] < year], frame[frame["debut_cohort"] == year]
        if train.empty or test.empty:
            continue
        y = test["target"].to_numpy(float)
        b = PartialPoolProjector(prior_scale=scale, weight_col=base_spec.weight_col).fit(train)
        a = PartialPoolProjector(prior_scale=scale, weight_col=base_spec.weight_col,
                                 extra_cols=extra).fit(train)
        mb = float(np.mean(np.abs(y - b.predict(test)[0])))
        ma = float(np.mean(np.abs(y - a.predict(test)[0])))
        deltas.append(mb - ma)          # > 0 ⇒ the Statcast arm is better on this fold
        base_maes.append(mb)
    d = np.asarray(deltas, float)
    if len(d) < 2:
        return {"n_folds": int(len(d)), "note": "too few folds to estimate a dispersion"}
    sd = float(np.std(d, ddof=1))
    mean = float(np.mean(d))
    se = sd / np.sqrt(len(d))
    from scipy import stats
    tcrit = float(stats.t.ppf(0.975, df=len(d) - 1))
    return {
        "n_folds": int(len(d)), "base_mae": float(np.mean(base_maes)),
        "fold_delta_sd": sd, "fold_delta_sd_pct_of_mae": round(100.0 * sd / np.mean(base_maes), 4),
        "point_estimate_pct": round(100.0 * mean / np.mean(base_maes), 4),
        "ci95_pct": [round(100.0 * (mean - tcrit * se) / np.mean(base_maes), 4),
                     round(100.0 * (mean + tcrit * se) / np.mean(base_maes), 4)],
        "point_estimate_is_uninterpretable": True,
        "why": ("reported for completeness, NOT as a result — at this fold count the interval spans "
                "both a large positive and a large negative lift, which is the definition of an "
                "unpowered design. Reading a sign off it would be the exact failure this memo exists "
                "to prevent."),
    }


def power_curve(fold_delta_sd: float, base_mae: float, n_folds: int, n_metrics: int,
                lifts_pct: np.ndarray | None = None, n_sims: int = 4000,
                seed: int = 6) -> pd.DataFrame:
    """(c-ii) Power of THE ACTUAL GATE, simulated, over a sweep of true lifts.

    The rule mirrored here is the S5 form: an arm ships only if it wins ≥60% of folds AND improves the
    mean AND survives a one-sided paired t under BH-FDR. Simulating the composite rule matters because
    each clause fails differently at small n — the fold-count clause is coarse (at 3 folds it can only
    read 0, 0.33, 0.67 or 1.0) while the t-clause has fat tails (df=2), and a formula for either one
    alone would materially overstate what the design can detect.
    """
    if lifts_pct is None:
        lifts_pct = np.arange(0.0, 12.01, 0.25)
    rng = np.random.default_rng(seed)
    from scipy import stats
    # The BH cutoff a single winning metric must clear when `n_metrics` are tested together. This is
    # BH at rank 1 (`alpha * 1 / m`), the CONSERVATIVE reading — if several metrics survive together
    # their cutoffs are looser. `n_metrics=1` recovers the most generous possible reading, and the
    # memo reports both so the conclusion is visibly not an artifact of this choice (NF-D15 g″: prove
    # the null does not rest on your own gate selection).
    bh_cut = BH_ALPHA / max(n_metrics, 1)
    rows = []
    for lift_pct in lifts_pct:
        true_delta = base_mae * lift_pct / 100.0
        d = rng.normal(true_delta, fold_delta_sd, size=(n_sims, n_folds))
        win = (d > 0).mean(axis=1) >= FOLD_WIN_GATE
        positive = d.mean(axis=1) > 0
        sd = d.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = d.mean(axis=1) / (sd / np.sqrt(n_folds))
        p = stats.t.sf(t, df=n_folds - 1)
        rows.append({
            "true_lift_pct": round(float(lift_pct), 3),
            "power_fold_gate": round(float(win.mean()), 4),
            "power_bh": round(float((p <= bh_cut).mean()), 4),
            "power_full_rule": round(float((win & positive & (p <= bh_cut)).mean()), 4),
        })
    return pd.DataFrame(rows)


def minimum_detectable(power: pd.DataFrame, covered_frac: float,
                       target: float = TARGET_POWER) -> dict:
    """The smallest TRUE lift the full rule detects at `target` power, in both honest units.

    ⭐ TWO UNITS, BECAUSE THE FOLD STATISTIC IS DILUTED. The arm is level-gated to AAA and only a
    fraction of a cohort's held-out rows carry the block, but the fold's MAE is computed over ALL of
    them — so a lift of X% on covered rows enters the gate as roughly `covered_frac × X%`. Quoting
    only the fold-level number would understate what the mechanism must actually do by ~4x, and
    quoting only the covered-row number would overstate what the gate can see. (The S4 dilution
    lesson, applied before the run instead of after it.)
    """
    hit = power[power["power_full_rule"] >= target]
    fold_level = float(hit["true_lift_pct"].iloc[0]) if len(hit) else None
    return {
        "target_power": target,
        "mde_fold_level_pct": fold_level,
        "mde_on_covered_rows_pct": (round(fold_level / covered_frac, 3)
                                    if fold_level and covered_frac > 0 else None),
        "covered_frac_of_test_rows": round(covered_frac, 4),
        "note": ("the fold statistic averages over ALL held-out rows while the arm can only move the "
                 "covered ones, so the effect the MECHANISM must produce is the fold-level MDE "
                 "divided by the covered fraction"),
        "unreachable": fold_level is None,
    }


def reopen_trigger(census: pd.DataFrame, folds: pd.DataFrame) -> dict:
    """WHEN this slice becomes worth re-running, stated as a DATA condition rather than a date.

    Coverage adds one debut cohort per season, so the fold count grows deterministically. The binding
    threshold is `MIN_FOLDS_FOR_PBO`: below it CSCV cannot be computed at all and the §0.5 deflation
    requirement is not merely failed but UNDEFINED — no effect size can fix that.
    """
    usable = folds[folds["status"] == "USABLE"]
    thin = folds[folds["status"].str.startswith("THIN")]
    typical = int(usable["covered_test"].median()) if len(usable) else 0
    need = max(MIN_FOLDS_FOR_PBO - len(usable), 0)
    return {
        "usable_folds_now": int(len(usable)),
        "folds_needed_for_pbo": MIN_FOLDS_FOR_PBO,
        "additional_usable_folds_required": need,
        "thin_folds_one_season_from_usable": [int(x) for x in thin["fold"]],
        "typical_covered_rows_per_cohort": typical,
        "condition": (
            f"re-run when {need} more debut cohort(s) clear {MIN_FOLD_TEST_ROWS} covered held-out "
            f"rows. The cohorts listed as THIN are in-progress seasons, not permanently short — a "
            f"completed season has been running ~{typical} covered rows, comfortably over the "
            f"threshold, so each completed season should convert one THIN fold to USABLE."),
        "how": "re-run this script; if `usable_folds_now` reaches the PBO minimum, the gate re-opens",
    }


def assess(pairs: pd.DataFrame, park_ctx: pd.DataFrame | None, side: SideConfig,
           metric: str | None = None) -> S6Feasibility:
    sc = SC_COLS[side.player_type]
    missing = [c for c in sc if c not in pairs.columns]
    if missing:
        raise KeyError(f"pairs is missing Statcast columns {missing}")
    lab = pairs[pairs["has_mlb_label"].astype(bool)].copy()
    census, by_level = coverage_census(lab, sc)
    folds = fold_viability(census)
    usable = [int(x) for x in folds.loc[folds["status"] == "USABLE", "fold"]]
    notes: list[str] = []

    # ISO is the pre-registered target: E7.3 leaves the most on the table there (its weakest
    # translator, oos_corr 0.429). On the pitcher side the sibling quantity is xwoba_against — the
    # metric whose minor feature IS the Statcast summary, and which already came back no-signal.
    metric = metric or ("iso" if side.player_type == "batter" else "xwoba_against")

    if len(usable) >= 2:
        noise = measure_fold_noise(pairs, park_ctx, metric, side, sc, usable)
    else:
        noise = {"n_folds": len(usable),
                 "note": "fewer than 2 usable folds — a dispersion cannot be estimated at all"}

    cov_frac = float(folds.loc[folds["status"] == "USABLE", "pct_test_covered"].mean() / 100.0) \
        if usable else 0.0
    if noise.get("fold_delta_sd"):
        power = power_curve(noise["fold_delta_sd"], noise["base_mae"], max(len(usable), 2),
                            n_metrics=len(side.metrics))
        mde = minimum_detectable(power, cov_frac)
        # ⭐ ROBUSTNESS: re-derive the MDE under the MOST GENEROUS gate available — no multiplicity
        # penalty at all — so a reader can see the conclusion is not manufactured by the conservative
        # BH reading above. If the slice is still unpowered when handed every benefit, the binding
        # constraint is the DATA, which is the claim this memo is actually making.
        generous = power_curve(noise["fold_delta_sd"], noise["base_mae"], max(len(usable), 2),
                               n_metrics=1)
        mde["sensitivity_no_multiplicity_penalty"] = minimum_detectable(generous, cov_frac)
        mde["conclusion_survives_generous_gate"] = bool(
            (mde["sensitivity_no_multiplicity_penalty"].get("mde_on_covered_rows_pct") or 99) > 10.0)
        # the null-lift false-fire rate of the COARSE clause, which is the one small n degrades worst
        z = power[power["true_lift_pct"] == 0.0]
        if len(z):
            mde["fold_gate_false_fire_at_zero_lift"] = float(z["power_fold_gate"].iloc[0])
    else:
        power, mde = pd.DataFrame(), {"unreachable": True,
                                      "note": "no dispersion estimate ⇒ no MDE"}

    # ⭐ NAME WHICH CONSTRAINT BINDS, rather than stopping on the first one that happens to trip.
    # Two independent things can block this slice, they have different remedies, and conflating them
    # would misdirect whoever re-opens it: a STRUCTURAL blocker is cured only by more debut cohorts,
    # while a POWER blocker could in principle be cured by a bigger effect or a sharper metric.
    structural = len(usable) < MIN_FOLDS_FOR_PBO
    underpowered = bool(mde.get("unreachable") or (mde.get("mde_on_covered_rows_pct") or 99) > 10.0)
    if structural:
        notes.append(
            f"🚧 **STRUCTURAL — THIS IS THE BINDING CONSTRAINT.** {len(usable)} usable fold(s) < "
            f"{MIN_FOLDS_FOR_PBO}: CSCV/PBO is UNDEFINED at this fold count (`deflation_report` "
            f"returns `pbo=None` and says so), so the §0.5 deflation requirement cannot be EVALUATED "
            f"— not failed, undefined. No effect size and no choice of gate fixes this; only more "
            f"debut cohorts do.")
    if underpowered:
        notes.append(
            f"📉 POWER — under the pre-registered (conservative) gate the minimum detectable lift is "
            f"also implausibly large: {mde.get('mde_on_covered_rows_pct')}% on covered rows, against "
            f"a slice-1 best-ever delivered lift of ~3.5%.")
    # The qualification below is keyed on the GENEROUS-gate result, not on `underpowered`, because
    # `underpowered` is computed from the conservative gate — keying it the other way would suppress
    # the caveat in exactly the case that needs it (a conclusion that holds only under the strict
    # reading), which is the failure mode the caveat exists to prevent.
    if not mde.get("unreachable") and mde.get("conclusion_survives_generous_gate") is False:
        # Say so out loud when the power argument alone would NOT have carried the day. Letting the
        # stronger-sounding of two arguments stand in for the real one is how a conclusion survives
        # after its actual support has expired (NF-D15 g″).
        notes.append(
            f"⚖️ HONEST QUALIFICATION: under the MOST GENEROUS gate (no multiplicity penalty) the "
            f"minimum detectable lift falls to "
            f"{mde['sensitivity_no_multiplicity_penalty'].get('mde_on_covered_rows_pct')}% on covered "
            f"rows, so the POWER argument alone would be arguable rather than decisive. **The stop "
            f"rests on the STRUCTURAL blocker above, not on the power calculation** — stated because "
            f"an argument that quietly leans on its weaker half is how a stale conclusion survives.")
    verdict = "STOP — RECORD THE CEILING" if (structural or underpowered) \
        else "PROCEED TO THE BAKE-OFF"
    return S6Feasibility(player_type=side.player_type, sc_cols=sc, census=census, by_level=by_level,
                         folds=folds, usable_folds=usable, noise=noise, power=power, mde=mde,
                         verdict=verdict, reopen=reopen_trigger(census, folds), notes=notes)


def write_memo(f: S6Feasibility, side: SideConfig, metric: str, dest: Path) -> None:
    L: list[str] = []
    A = L.append
    A(f"# E7.12 slice 6 — AAA-Statcast FEASIBILITY MEMO ({side.player_type}s)\n")
    A("> ⚠️ **This is a feasibility memo, not a bake-off.** `best_alpha = 0`.\n")
    A(f"## Verdict: **{f.verdict}**\n")
    for n in f.notes:
        A(f"- {n}")
    A("\n⭐ **A bake-off that cannot detect its own effect is NOT a null — it is an unpowered test, and "
      "recording it as a null would retire a live mechanism on no evidence.** That is why this slice "
      "was gated, and it is why the point estimate below is reported with an interval and explicitly "
      "marked uninterpretable rather than being turned into a verdict.\n")

    A("\n## (a) Coverage — labelled rows carrying the `sc_*` block\n")
    A(f"Block: `{', '.join(f.sc_cols)}`\n")
    A("\n### By level\n")
    A(f.by_level.to_markdown(index=False))
    A("\n\nThe block is **Triple-A only** by construction — AAA is the only minor level with Hawk-Eye "
      "tracking — so any S6 arm is inherently level-gated, and the ceiling below is a property of the "
      "data source rather than of our ingest.\n")
    A("\n### By debut cohort\n")
    A(f.census.to_markdown(index=False))

    A("\n## (b) Fold viability\n")
    A("A fold Y trains on cohorts `< Y` and scores cohort Y, so it needs covered rows on BOTH sides: "
      "without covered TRAINING rows the arm is byte-identical to the baseline and scores `delta = 0`, "
      "which the `d > 0` fold test counts as a LOSS. **Scoring a mechanism on folds where it provably "
      "cannot act is not a stricter test, it is a broken one** — the S4 lesson, where exactly this "
      "capped an achievable fold-win-rate at 0.636 against a 0.60 gate.\n")
    A(f.folds.to_markdown(index=False))
    A(f"\n**Usable folds: {f.usable_folds or 'NONE'} "
      f"({len(f.usable_folds)} of {len(f.folds)} evaluable cohorts).**\n")

    A(f"\n## (c) Power — is the design able to detect the effect worth chasing? (`{metric}`)\n")
    A("Simulated against **the gate as it is actually coded** — fold-win-rate ≥ 0.60 AND a positive "
      "mean lift AND a one-sided paired t surviving BH-FDR — not against a generic power formula. "
      "Each clause fails differently at small n (the fold clause is coarse; the t clause has fat "
      "tails at low df), so any single-clause formula would flatter the design.\n")
    A("\n### Measured noise\n")
    A("```\n" + json.dumps(f.noise, indent=2, default=str) + "\n```")
    if len(f.power):
        A("\n### Power curve\n")
        A(f.power[f.power["true_lift_pct"] <= 12].to_markdown(index=False))
    A("\n### Minimum detectable lift\n")
    A("```\n" + json.dumps(f.mde, indent=2, default=str) + "\n```")
    ff = f.mde.get("fold_gate_false_fire_at_zero_lift")
    if ff is not None:
        A(f"\n⚠️ **At this fold count the fold-win-rate clause is close to a coin flip: it fires "
          f"{ff:.1%} of the time on a TRUE lift of ZERO.** With 3 folds \"≥60% of folds\" collapses to "
          f"\"≥2 of 3\", which a null clears about half the time — so essentially all of the "
          f"discrimination is coming from the paired-t/BH clause, on 2 degrees of freedom. This is the "
          f"same weakness E7.12-S5 hit from the other side, where a permuted-bucket placebo cleared "
          f"the same clause 9/11.\n")

    A("\n## Re-open trigger\n")
    A("Stated as a DATA condition rather than a date, and mechanical: re-run this script.\n")
    A("```\n" + json.dumps(f.reopen, indent=2, default=str) + "\n```")

    A("\n## 🚨 For whoever eventually runs the bake-off — a landmine in the plumbing\n")
    A("`PartialPoolProjector._design` calls `s.transform(df)[0]`: it takes `_Scaler`'s standardized "
      "VALUE and **discards the missing flag returned beside it**. So passing the `sc_*` columns "
      "through `extra_cols` alone gives every uncovered row `z = 0` — the mean OF THE COVERED SUBSET "
      "— which is a fabricated neutral asserted about ~88% of rows, and precisely what the story "
      "prompt forbids (\"never fabricate a zero\"). The arm must carry an explicit missing indicator "
      "per column so the model can offset the imputation instead of believing it; "
      "`_with_missing_indicators` in this module is the reference. Without it the bake-off would be "
      "measuring an assertion about uncovered players, not a Statcast effect.\n")
    dest.write_text("\n".join(L))
    log.info("wrote %s", dest)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.12 slice 6 — AAA-Statcast feasibility memo")
    p.add_argument("--player-type", choices=sorted(SIDES), default="batter")
    p.add_argument("--metric", default=None, help="power target (default: iso / xwoba_against)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    side = SIDES[a.player_type]
    suffix = side.reduced.artifact_suffix
    art = _ABLATION / ("e7_3p_artifacts" if side.player_type == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(art / side.pairs_name)
    pctx = _ABLATION / "e7_12_artifacts" / f"mle_park_context{suffix}.parquet"
    park_ctx = pd.read_parquet(pctx) if pctx.exists() else None

    metric = a.metric or ("iso" if side.player_type == "batter" else "xwoba_against")
    f = assess(pairs, park_ctx, side, metric=metric)
    dest = _ABLATION / f"e7_12_slice6_feasibility{suffix}.md"
    write_memo(f, side, metric, dest)
    log.info("VERDICT [%s] %s · usable folds %s · MDE(covered rows) %s%%",
             side.player_type, f.verdict, f.usable_folds, f.mde.get("mde_on_covered_rows_pct"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
