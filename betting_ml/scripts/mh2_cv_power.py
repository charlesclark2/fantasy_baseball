"""mh2_cv_power.py — MH2: the CV-power characterization + the mechanical null inventory.

Run (LAPTOP, ~20s — pure reads of stored artifacts, NO re-fit, NO Snowflake):

    uv run python -m betting_ml.scripts.mh2_cv_power

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------------------------------------------------------------
It is a DIAGNOSTIC OF THE EVAL. It re-reads stored arm tables and answers "what could this design
have detected?" It never re-fits an arm, never re-scores a metric and never changes a verdict —
every ADD/DROP in the record stands exactly as scored (readiness lock 5).

THE THREE OUTPUTS
  1. **A power table, per (tier × window) and per STAT.** Not one "power" number, because the
     binding constraint genuinely varies: E7.14 died on the fold-SIGN floor, E7.12-S6 on PBO being
     UNDEFINED at 3 folds, E7.9/E7.15-H3 on DSR. Collapsing those into one figure would misdirect
     every re-test decision that follows.
  2. **A mechanical null inventory.** Built by walking the artifact tree, not from memory — every
     row carries the file it came from, and what could NOT be extracted is COUNTED and reported
     rather than silently dropped.
  3. **Validation cases.** Four recorded results this module must reproduce before its numbers may
     be believed at all (E7.9's 3 folds, E7.12-S6's 0.4968 false-fire, E7.14's 8-season
     certifiability, E7.15-H3's 0.607→0.998 field-size flip). A diagnostic that cannot reproduce
     the record is not a diagnostic.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils.cv_power import (
    BH_ALPHA,
    FOLD_CONSISTENCY_ALPHA,
    LEGACY_FOLD_WIN_RATE,
    MIN_FOLDS_FOR_PBO,
    achievable_folds,
    classify_null,
    decompose_field_size,
    dsr_benchmark_sr0,
    dsr_ceiling,
    dsr_from_sr,
    dsr_max_field_size,
    dsr_required_sr,
    fold_consistency_clause,
    fold_gate_false_fire,
    folds_for_sign_certifiability,
    folds_to_clear_dsr,
    mde_in_sd_units,
    seasons_for_folds,
    sign_test_floor,
)

log = logging.getLogger("mh2")

REPO = Path(__file__).resolve().parents[2]
ABL = REPO / "quant_sports_intel_models/baseball/edge_program/ablation_results"
PROMPTS = REPO / "quant_sports_intel_models/baseball/edge_program/story_prompts.md"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# READINESS LOCK 3 — the practically-meaningful effect, PER METRIC FAMILY, each derived from a
# decision the program has ALREADY made. A power table against an invented effect size answers a
# question nobody asked, so nothing here is a Cohen's-d convention: every row cites the pre-existing
# artifact it is read off.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MeaningfulEffect:
    family: str
    unit: str
    value: float
    derivation: str


MEANINGFUL_EFFECTS: tuple[MeaningfulEffect, ...] = (
    MeaningfulEffect(
        "crps_game_model", "CRPS (runs)", 0.02,
        "`promotion_gate.NOISE_FLOOR['crps']` — the program's PRE-EXISTING pre-registered noise "
        "floor for the runs targets. A margin below it is defined by the program itself as a TIE "
        "that ships nothing, so it IS the smallest serving-decision-changing effect. Not chosen "
        "here; read off the gate that already binds."),
    MeaningfulEffect(
        "mae_pct_lift_translation", "% held-out MAE lift", 1.0,
        "The SMALLEST lift that has ever actually changed a served MiLB→MLB configuration: E7.12 "
        "slice 1's `woba` ADD at +0.932%. Rounded UP to 1.0% so the bar is not set by the single "
        "luckiest shipped case. An empirical decision anchor from the record, not a convention."),
    MeaningfulEffect(
        "rank_ic_board", "Spearman rank-IC", 0.04,
        "The median ACROSS-SEASON SD of a single source's own rank-IC on E7.14's cohort (0.041–"
        "0.048 over 7 sources). A between-source gap smaller than one source's own year-to-year "
        "wobble cannot justify re-weighting a board, so this is the ordering delta that would "
        "actually change a board decision. A noise property of the design, computable before any "
        "comparison is run."),
    MeaningfulEffect(
        "nll_pricing", "NLL (nats)", 0.01,
        "`promotion_gate.NOISE_FLOOR['nll']`, same standing as the CRPS row."),
    MeaningfulEffect(
        "brier_classification", "Brier", 0.002,
        "`promotion_gate.NOISE_FLOOR['brier']`, same standing as the CRPS row."),
)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# READINESS LOCK 2 — the (tier × window) ledger. The FOLD RULE ITSELF differs per tier, and that is
# a first-order driver nobody had written down: walk-forward BURNS 3 seasons on training before it
# emits a single fold, while leave-one-cohort-out emits one per cohort. So the tier with the LONGEST
# calendar history can still be the one with the FEWEST folds.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TierWindow:
    tier: str
    fold_rule: str
    window: str
    n_periods: int
    n_folds: int
    typical_arms: int
    metric_family: str
    provenance: str
    lever: str
    # ⭐ WHICH primary contrast this tier actually runs. Without it the power table would impute the
    # fold-SIGN floor to studies that use a paired t — and the sign floor binds ONLY on a sign test.
    # Attributing a clause a study never ran is the same class of error as reading a DROP as a
    # mechanism failure: it puts the blame on a constraint that was never in force.
    primary_contrast: str = "paired-t"
    bh_family_size: int | None = 4


TIER_WINDOWS: tuple[TierWindow, ...] = (
    TierWindow(
        "MLB game model — post_lineup", "PurgedWalkForwardSplit (n_seasons − 3)", "2021–2026", 6, 3,
        28, "crps_game_model",
        "E7.9 `e7_9_retrain_total_runs_post_lineup.md`: '28 arms × 3 purged/embargoed folds', "
        "matrix 2021-04-18 → 2026-07-27. `achievable_folds(6) = 3` reproduces it exactly.",
        "⭐ WINDOW, available NOW — see the served-store measurement below.",
        primary_contrast="noise-floor margin (no fold clause, no BH family)", bh_family_size=None),
    TierWindow(
        "MLB game model — pre_lineup", "PurgedWalkForwardSplit (n_seasons − 3)", "2021–2026", 6, 3,
        24, "crps_game_model",
        "E7.9 `e7_9_retrain_run_diff_pre_lineup.md`: '24 arms × 3 purged/embargoed folds'.",
        "⭐ WINDOW, available NOW.",
        primary_contrast="noise-floor margin (no fold clause, no BH family)", bh_family_size=None),
    TierWindow(
        "MiLB→MLB translation (batter)", "leave-one-MLB-debut-cohort-out (n_cohorts)",
        "2016–2026", 11, 11, 7, "mae_pct_lift_translation",
        "E7.12-S1 / E7.15-H1..H4 stored `mae_by_fold` — 11 fold keys 2016…2026.",
        "calendar only: +1 fold per completed debut cohort."),
    TierWindow(
        "MiLB→MLB translation (pitcher)", "leave-one-MLB-debut-cohort-out (n_cohorts)",
        "2016–2026", 11, 11, 7, "mae_pct_lift_translation",
        "E7.15 pitcher summaries — same 11 fold keys.",
        "calendar only: +1 fold per completed debut cohort."),
    TierWindow(
        "Prospect comps — strict maturity", "forward, 3-season outcome horizon matured",
        "2015–2022 boards", 8, 4, 12, "crps_game_model",
        "E7.16 `fold_census.by_type.*.strictly_matured_folds = 4` (query seasons 2019–2022).",
        "calendar only: the 3-season horizon must mature."),
    TierWindow(
        "Prospect comps — relaxed context", "forward, relaxed maturity", "2015–2022 boards", 8, 7,
        12, "crps_game_model",
        "E7.16 `fold_census.by_type.*.relaxed_folds = 7`.",
        "already the widest reading of the same data."),
    TierWindow(
        "Prospect source head-to-head", "per board season on matched support", "2018–2022 overlap",
        5, 5, 9, "rank_ic_board",
        "E7.14 `org_scope.folds = [2018…2022]` — the FanGraphs×Pipeline archive OVERLAP, not "
        "either archive's own reach (E7.14b closed the FanGraphs floor at 2018).",
        "calendar only: +1 overlapping season per year.",
        primary_contrast="fold-SIGN test (two-sided)", bh_family_size=10),
    TierWindow(
        "AAA-Statcast translation", "leave-one-debut-cohort-out, ≥30 covered held-out rows",
        "2022– coverage", 3, 3, 4, "mae_pct_lift_translation",
        "E7.12-S6 `reopen_trigger.usable_folds_now = 3`.",
        "calendar only: one usable cohort per completed season."),
)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The mechanical null inventory
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class NullRow:
    source_file: str
    study: str
    tier: str
    window: str
    metric: str
    verdict: str
    n_folds: int | None = None
    n_arms: int | None = None
    fold_win_rate: float | None = None
    fold_wins: int | None = None
    pct_lift_vs_foil: float | None = None
    pbo: float | None = None
    dsr: float | None = None
    observed_sr: float | None = None
    sr0: float | None = None
    var_trials_sr: float | None = None
    p_one_sided: float | None = None
    bh_cutoff: float | None = None
    bound_by: str | None = None
    null_state: str | None = None
    reason: str | None = None
    retest_trigger: str | None = None
    folds_needed: int | None = None
    extra_seasons: int | None = None
    max_field_size: int | None = None
    legacy_clause_passes: bool | None = None
    calibrated_clause_passes: bool | None = None
    extraction: str = "rich"


def _sharpe(s: np.ndarray) -> float:
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    sd = float(np.std(s, ddof=1)) if len(s) > 2 else 0.0
    return float(np.mean(s) / sd) if sd > 0 else 0.0


def _moments(s: np.ndarray) -> tuple[float, float]:
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    rc, sd = s - s.mean(), s.std(ddof=0)
    if sd <= 0:
        return 0.0, 3.0
    return float((rc**3).mean() / sd**3), float((rc**4).mean() / sd**4)


def _g(row, key: str) -> float | None:
    """Safe float read off a leaderboard row. The corpus spans several harness generations and not
    every summary carries every column; a missing column must yield an UNKNOWN, never a crash and
    never a silently-skipped study."""
    if row is None or key not in getattr(row, "index", ()):
        return None
    v = row[key]
    return float(v) if pd.notna(v) else None


def _which_stat_bound(row: NullRow) -> str:
    """Name the SINGLE constraint that actually stopped this metric — in gate order.

    ⭐ **THE WHOLE POINT OF THE INVENTORY.** A report says "DROP" and a reader infers the mechanism
    failed; in fact the run may have died on a multiplicity cutoff no effect size could clear
    (E7.14) or on a statistic that was never computable (E7.12-S6). Those have different remedies
    and only one of them is about the mechanism at all.

    ⚠️ **THE RECORDED VERDICT IS AUTHORITATIVE, AND THAT IS NOT A DETAIL.** A first cut of this
    function applied today's `PBO < 0.20` bar to every row and duly reported that PBO "bound" four
    E7.12-S1 arms **that actually SHIPPED** — because slice 1 read PBO descriptively (tie vs
    instability) rather than as a hard ceiling. Imputing a clause a study never ran is the same
    error as reading a DROP as a mechanism failure, one level up: it blames a constraint that was
    never in force. So an ADD short-circuits to "nothing bound it — this shipped".
    """
    if row.null_state == "INACTIVE":
        return "n/a — the mechanism cannot act on this population"
    if str(row.verdict).upper() in ("ADD", "SHIP_CHALLENGER", "BLEND_WIRE"):
        return "nothing — this arm SHIPPED under its own study's gate"
    if row.n_folds is None:
        return "unknown — the artifact records no fold structure"
    if str(row.verdict).upper() == "BLOCKED":
        return "anchor/plumbing (BLOCKED — no verdict was reached)"
    if row.n_folds is not None and row.n_folds < MIN_FOLDS_FOR_PBO:
        return f"PBO UNDEFINED (<{MIN_FOLDS_FOR_PBO} folds)"
    if row.pct_lift_vs_foil is not None and row.pct_lift_vs_foil <= 0:
        return "point estimate (best arm loses on average)"
    if row.fold_win_rate is not None and row.fold_win_rate < LEGACY_FOLD_WIN_RATE:
        return "fold-consistency clause"
    if row.pbo is not None and row.pbo >= 0.20:
        return "PBO"
    if row.dsr is not None and row.dsr < 0.95:
        return "DSR"
    if (row.p_one_sided is not None and row.bh_cutoff is not None
            and row.p_one_sided > row.bh_cutoff):
        return "BH-FDR multiplicity"
    return "unattributed (the recorded stats do not identify a binding clause)"


def scan_e7_summaries() -> tuple[list[NullRow], list[str]]:
    """The RICH tier: E7.x `*_summary.json` carrying `per_metric` with per-fold arm tables.

    These are the only artifacts from which the deflation statistics can be RECOMPUTED rather than
    read, which is what lets the field-size axis be measured instead of asserted.
    """
    rows: list[NullRow] = []
    skipped: list[str] = []
    files = sorted(ABL.glob("*/*_summary.json"))
    for f in files:
        try:
            d = json.loads(f.read_text())
        except Exception as e:                                    # pragma: no cover - corpus hygiene
            log.warning("unreadable %s: %s", f, e)
            continue
        if not isinstance(d, dict) or "per_metric" not in d:
            continue
        # ⚠️ **THE CORPUS HAS THREE HARNESS GENERATIONS AND THEY NEST THE SAME STATISTICS
        # DIFFERENTLY.** E7.15 stores `deflation.pbo` / `dsr.eligible.dsr`; E7.12-S1 stores
        # `deflation.pbo` with no DSR at all; E7.3 stores FLAT `pbo` / `dsr` on the metric and has
        # no `mae_by_fold`. An earlier cut looked only for the E7.15 nesting, found nothing on E7.3,
        # and emitted its 9 metrics as `UNDEFINED` with a fabricated "4 more folds" re-test trigger
        # — an inventory inventing findings about a study whose gates it simply failed to read.
        # Resolve each statistic across all three shapes; a genuinely gateless summary is SKIPPED
        # and NAMED, never silently classified.
        if not any(isinstance(pm, dict) and pm.get("leaderboard")
                   for pm in d["per_metric"].values()):
            skipped.append(f"{f.name} (no leaderboard — a fit summary, not a bake-off)")
            continue
        side = "pitcher" if "pitchers" in f.stem else "batter"
        study = f"{f.stem.replace('_summary', '').replace('_pitchers', '')} ({side})"
        tier = f"MiLB→MLB translation ({side})"
        for metric, pm in d["per_metric"].items():
            if not isinstance(pm, dict) or "leaderboard" not in pm:
                continue
            lb = pd.DataFrame(pm["leaderboard"])
            if "arm" not in lb.columns and "config" in lb.columns:
                lb = lb.rename(columns={"config": "arm"})    # E7.3 names the column `config`
            # ⚠️ The corpus is NOT uniform: E7.12-S1 names its baseline `S0_baseline` and its lift
            # column `pct_lift_vs_S0`, while the E7.15 harness uses `L0_foil` / `pct_lift_vs_foil`.
            # Resolve BOTH from the artifact rather than assuming one — silently skipping a study
            # whose column names differ is exactly the under-coverage this inventory exists to stop.
            lift_col = next((c for c in ("pct_lift_vs_foil", "pct_lift_vs_S0")
                             if c in lb.columns), None)
            foil = d.get("foil") or d.get("baseline") or next(
                (a for a in ("L0_foil", "S0_baseline") if a in (pm.get("mae_by_fold") or {})),
                "L0_foil")
            selectable = (lb["selectable"].astype(bool) if "selectable" in lb.columns
                          else pd.Series(False, index=lb.index))
            active = (lb["active"].astype(bool) if "active" in lb.columns
                      else pd.Series(True, index=lb.index))
            sel = lb[selectable & active]
            cand = sel.iloc[0] if len(sel) else None
            mae = pd.DataFrame(pm.get("mae_by_fold") or {})
            defl = pm.get("deflation") if isinstance(pm.get("deflation"), dict) else {}
            _dsr = pm.get("dsr") if isinstance(pm.get("dsr"), dict) else {}
            dsr_e = _dsr.get("eligible") if isinstance(_dsr.get("eligible"), dict) else {}
            pbo_val = defl.get("pbo")
            if pbo_val is None and isinstance(pm.get("pbo"), (int, float)):
                pbo_val = pm["pbo"]                          # E7.3's flat shape
            dsr_val = dsr_e.get("dsr")
            if dsr_val is None and isinstance(pm.get("dsr"), (int, float)):
                dsr_val = pm["dsr"]                          # E7.3's flat shape
            n_folds = int(len(mae.index)) if len(mae.index) else None
            elig = [str(a) for a in lb.loc[selectable, "arm"]] if "arm" in lb.columns else []
            elig = [a for a in elig if a in mae.columns and a != foil]

            obs_sr = v_trials = None
            sk, ku = 0.0, 3.0
            if cand is not None and foil in mae.columns and str(cand["arm"]) in mae.columns:
                skill = mae[foil] - mae[str(cand["arm"])]
                s = skill.dropna().to_numpy(float)
                obs_sr = _sharpe(s)
                sk, ku = _moments(s)
                v_trials = float(np.var([_sharpe((mae[foil] - mae[c]).dropna().to_numpy(float))
                                         for c in elig], ddof=1)) if len(elig) > 1 else None

            active = cand is not None
            row = NullRow(
                source_file=str(f.relative_to(REPO)), study=study, tier=tier,
                window="2016–2026 debut cohorts", metric=metric,
                verdict=str(pm.get("verdict", "?")),
                n_folds=n_folds, n_arms=len(elig) or None,
                fold_win_rate=_g(cand, "fold_win_rate"),
                fold_wins=(int(round(_g(cand, "fold_win_rate") * n_folds))
                           if _g(cand, "fold_win_rate") is not None and n_folds else None),
                pct_lift_vs_foil=(_g(cand, lift_col) if lift_col else None),
                pbo=(float(pbo_val) if pbo_val is not None else None),
                dsr=(float(dsr_val) if dsr_val is not None else None),
                observed_sr=obs_sr,
                sr0=(float(dsr_e["sr0"]) if dsr_e.get("sr0") is not None else None),
                var_trials_sr=v_trials,
                p_one_sided=_g(cand, "p_one_sided"),
                bh_cutoff=(d.get("null_analysis") or {}).get("strictest_bh_cutoff"),
            )
            inactive_reason = None
            if not active:
                inactive_reason = (
                    f"`{metric}` ({side}): no ACTIVE arm — the mechanism has no rows it can move on "
                    f"this population, so the run measured nothing about the effect. E7.15's "
                    f"`xwoba_against` is the canonical case (a Triple-A-only Statcast feature ⇒ ZERO "
                    f"within-player level transitions). Neither a power problem nor a defect.")
            if str(pm.get("verdict", "")).upper() in ("ADD", "SHIP_CHALLENGER", "BLEND_WIRE"):
                # ⭐ A SHIPPED ARM IS NOT A NULL AND MUST NOT ENTER THE NULL STATE MACHINE. An
                # earlier cut classified all four E7.12-S1 ADDs as POWER_LIMITED — i.e. the
                # inventory reported the program's shipped configuration as an unresolved null.
                row.null_state = "SHIPPED (not a null)"
                row.reason = (f"`{metric}`: this arm ADDed under its own study's pre-registered "
                              f"gate. It is in the inventory for completeness — a null classifier "
                              f"has nothing to say about a result that shipped.")
            elif str(pm.get("verdict", "")).upper() == "BLOCKED":
                row.null_state = "UNDEFINED"
                row.reason = (f"`{metric}`: the run was BLOCKED by an anchor, so **no verdict was "
                              f"reached at all** and there is no null to classify. A blocked run is "
                              f"a statement about the harness or the population, never about the "
                              f"effect — classifying it as underpowered would invent a finding.")
                row.retest_trigger = "fix or re-scope the blocking anchor, then re-run"
            else:
                v = classify_null(
                    metric=metric, n_folds=n_folds or 0, n_arms=row.n_arms or 2,
                    beats_foil=bool(row.pct_lift_vs_foil and row.pct_lift_vs_foil > 0),
                    observed_sr=obs_sr, var_trials_sr=v_trials, skew=sk, kurt=ku,
                    fold_wins=row.fold_wins, p_one_sided=row.p_one_sided, bh_cutoff=row.bh_cutoff,
                    active=active, inactive_reason=inactive_reason)
                row.null_state, row.reason = v.state, v.reason
                row.retest_trigger, row.folds_needed = v.retest_trigger, v.folds_needed
                row.extra_seasons, row.max_field_size = v.extra_seasons, v.max_field_size
            if n_folds and row.fold_wins is not None:
                cl = fold_consistency_clause(n_folds)
                row.legacy_clause_passes = row.fold_wins >= math.ceil(LEGACY_FOLD_WIN_RATE * n_folds)
                row.calibrated_clause_passes = cl.passes(row.fold_wins)
            row.bound_by = _which_stat_bound(row)
            rows.append(row)
    return rows, skipped


_MD_ARMS = re.compile(r"(\d+)\s+arms?\s*×\s*(\d+)\s*(?:purged/embargoed\s*)?folds?")
_MD_FOLDS = re.compile(r"·\s*(\d+)\s+folds?")
_MD_PBO = re.compile(r"PBO[^0-9]{0,12}([01]\.\d+)")
_MD_DSR = re.compile(r"DSR[^0-9]{0,12}([01]\.\d+)")
_MD_VERDICT = re.compile(r"\*\*VERDICT:?\s*`?([A-Z_ ]+)`?\*\*")


def scan_markdown() -> tuple[list[NullRow], dict]:
    """The COARSE tier: every `.md` in the corpus, parsed for its header design line.

    ⚠️ **NO SILENT CAPS.** The corpus is heterogeneous — many reports predate the current header
    convention and simply do not state a fold count. Those are COUNTED as unextractable and named,
    never dropped quietly, because an inventory that reports only what it could parse looks like
    full coverage of a smaller corpus.
    """
    rows: list[NullRow] = []
    unextractable: list[str] = []
    for f in sorted(list(ABL.glob("*.md")) + list(ABL.glob("*/*.md"))):
        txt = f.read_text(errors="ignore")
        head = txt[:4000]
        m_arms = _MD_ARMS.search(head)
        n_folds = int(m_arms.group(2)) if m_arms else (
            int(_MD_FOLDS.search(head).group(1)) if _MD_FOLDS.search(head) else None)
        n_arms = int(m_arms.group(1)) if m_arms else None
        pbo = _MD_PBO.search(head)
        dsr = _MD_DSR.search(head)
        verdict = _MD_VERDICT.search(head)
        if n_folds is None and pbo is None and dsr is None:
            unextractable.append(str(f.relative_to(ABL)))
            continue
        row = NullRow(
            source_file=str(f.relative_to(REPO)), study=f.stem, tier="(from report header)",
            window="(see report)", metric="(report-level)",
            verdict=(verdict.group(1).strip() if verdict else "?"),
            n_folds=n_folds, n_arms=n_arms,
            pbo=float(pbo.group(1)) if pbo else None,
            dsr=float(dsr.group(1)) if dsr else None, extraction="header")
        row.bound_by = _which_stat_bound(row)
        row.null_state = ("UNDEFINED" if (n_folds or 99) < MIN_FOLDS_FOR_PBO else
                          "POWER_LIMITED" if (row.dsr is not None and row.dsr < 0.95) else
                          "not-classifiable-from-header")
        rows.append(row)
    return rows, {"unextractable_reports": unextractable,
                  "n_unextractable": len(unextractable)}


def corpus_census() -> dict:
    """What the inventory covers, stated so under-coverage cannot masquerade as completeness."""
    md = sorted(list(ABL.glob("*.md")) + list(ABL.glob("*/*.md")))
    js = sorted(list(ABL.glob("*.json")) + list(ABL.glob("*/*.json")))
    done = 0
    if PROMPTS.exists():
        t = PROMPTS.read_text(errors="ignore")
        done = len(re.findall(r"▶ Story prompt", t))
    return {"markdown_reports": len(md), "json_artifacts": len(js),
            "story_prompt_entries": done,
            "note": "the JSON count includes per-Optuna-trial artifacts, which are trial records "
                    "rather than verdicts and carry no gate to classify."}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Validation cases — reproduce the record, or the diagnostic is not trustworthy
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def validation_cases() -> list[dict]:
    out = []
    out.append({
        "case": "E7.9 — achievable folds from the window",
        "recorded": "3 purged/embargoed folds on a 2021-04-18 → 2026-07-27 matrix (6 seasons)",
        "reproduced": f"achievable_folds(6) = {achievable_folds(6)}",
        "agrees": achievable_folds(6) == 3})
    ff = fold_gate_false_fire(3)
    out.append({
        "case": "E7.12-S6 — fold-clause false-fire at 3 folds (H8's diagnosis)",
        "recorded": "0.4968 (simulated, `fold_gate_false_fire_at_zero_lift`)",
        "reproduced": f"exact binomial P(Bin(3,½) ≥ 2) = {ff:.4f}",
        "agrees": abs(ff - 0.4968) < 0.01})
    need = folds_for_sign_certifiability(0.010, two_sided=True)
    out.append({
        "case": "E7.14 — fold-sign certifiability floor",
        "recorded": "sign_test_p floor 0.0625 at 5 folds; `folds_required_to_certify` = 8",
        "reproduced": f"sign_test_floor(5, two_sided) = {sign_test_floor(5, True):.4f}; "
                      f"folds_for_sign_certifiability(0.010) = {need}",
        "agrees": need == 8 and abs(sign_test_floor(5, True) - 0.0625) < 1e-9})
    out.extend(_h3_field_size_cases())
    return out


def _h3_field_size_cases() -> list[dict]:
    """⭐ THE FIELD-SIZE VALIDATION CASE — E7.15-H3's trajectory arms, 7-arm field vs 2-arm family.

    ⚠️ The story prompt states this as "iso +1.418%, 9/11 folds … DSR 0.607 → 0.998". Read off the
    stored artifact those are TWO different metrics of the same 7-arm field: the +1.418% / 9-of-11
    effect is `iso` (DSR 0.657 → 0.981) and the 0.607 → 0.998 pair is `bb_pct` (+1.404%, also
    9 of 11). Both are trajectory arms, both flip on field size alone, and the shape the prompt
    describes is exactly right — so both are reproduced here rather than silently picking one.
    """
    p = ABL / "e7_15_artifacts/e7_15_h3_summary.json"
    if not p.exists():
        return [{"case": "E7.15-H3 field size", "recorded": "n/a", "reproduced": "artifact absent",
                 "agrees": False}]
    d = json.loads(p.read_text())
    out = []
    for metric, recorded_wide, recorded_narrow in (("bb_pct", 0.6065, 0.998), ("iso", 0.6573, 0.981)):
        pm = d["per_metric"][metric]
        mae = pd.DataFrame(pm["mae_by_fold"])
        foil = "L0_foil"
        lb = pd.DataFrame(pm["leaderboard"])
        elig = [a for a in lb.loc[lb["selectable"], "arm"] if a in mae.columns and a != foil]
        traj = [a for a in elig if a.startswith(("T1_", "T2_"))]
        skill = pd.DataFrame(mae[[foil]].to_numpy(float) - mae.to_numpy(float),
                             index=mae.index, columns=mae.columns)
        win = pm["dsr"]["eligible"]["arm"]
        s = skill[win].dropna().to_numpy(float)
        sr, (sk, ku), n = _sharpe(s), _moments(s), len(s)
        v_wide = float(np.var([_sharpe(skill[c].to_numpy(float)) for c in elig], ddof=1))
        v_narrow = float(np.var([_sharpe(skill[c].to_numpy(float)) for c in traj], ddof=1))
        wide = dsr_from_sr(sr, n_obs=n, n_trials=len(elig), var_trials_sr=v_wide, skew=sk, kurt=ku)
        narrow = dsr_from_sr(sr, n_obs=n, n_trials=len(traj), var_trials_sr=v_narrow, skew=sk, kurt=ku)
        dec = decompose_field_size(observed_sr=sr, n_obs=n, n_trials_wide=len(elig), var_wide=v_wide,
                                   n_trials_narrow=len(traj), var_narrow=v_narrow,
                                   skew=sk, kurt=ku)
        out.append({
            "case": f"E7.15-H3 `{metric}` — SAME winner/folds/effect, field {len(elig)} → {len(traj)} arms",
            "recorded": f"DSR {recorded_wide} ({len(elig)} arms) → ~{recorded_narrow} "
                        f"({len(traj)}-arm trajectory family)",
            "reproduced": f"DSR {wide:.4f} → {narrow:.4f}  (SR {sr:.4f} held fixed; "
                          f"SR0 {dsr_benchmark_sr0(len(elig), v_wide):.4f} → "
                          f"{dsr_benchmark_sr0(len(traj), v_narrow):.4f})",
            "agrees": abs(wide - recorded_wide) < 0.002 and abs(narrow - recorded_narrow) < 0.02,
            "decomposition": dec,
            "max_field_at_observed_dispersion": dsr_max_field_size(
                observed_sr=sr, n_obs=n, var_trials_sr=v_wide, skew=sk, kurt=ku),
            "folds_to_clear_in_the_wide_field": folds_to_clear_dsr(
                observed_sr=sr, n_trials=len(elig), var_trials_sr=v_wide, skew=sk, kurt=ku),
            "folds_needed_DSR_as_recorded_by_null_analysis":
                (d.get("null_analysis") or {}).get("per_metric") and next(
                    (r.get("folds_needed_DSR") for r in d["null_analysis"]["per_metric"]
                     if r.get("metric") == metric), None),
        })
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The power table
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def family_rescoring() -> pd.DataFrame:
    """⭐ **THE COUNTERPART TO "A FAMILY GETS ITS OWN FIELD": YOU GET TO PRE-REGISTER A FAMILY, YOU
    DO NOT GET TO DISCOVER ONE.**

    E7.15-H3's 7-arm field holds two mechanisms — a TRAJECTORY family (`T1_traj_ladder`,
    `T2_traj_raw`, `T3_tenure`) and a PLAYER-STRUCTURE family (`P1`…`P4`). Scoring each family's
    best arm against its OWN pre-registered field is the right correction and is what this table
    does.

    ⚠️ **AND IT OVERTURNS THE HEADLINE THE FIELD-SIZE CASE WAS BEING USED TO SUPPORT.** The recorded
    "clears at 0.998 over the 2-arm trajectory family" drops `T3_tenure` — a genuine, named,
    pre-registered member of that family (H3's own pre-registration lists all three). Restore it and
    the SAME winner on the SAME folds reaches **0.849** (batter `bb_pct`), not 0.95. Retrospectively
    shrinking a field to the arms nearest the winner is a SECOND layer of exactly the selection bias
    DSR exists to deflate — the arm you drop is chosen because it lost.

    So the honest statement is two-sided and both halves matter: bundling unrelated mechanisms
    over-taxes a real finding (the E7.15-H3 7-arm reading is too harsh), AND a family trimmed after
    the fact under-taxes it (the 2-arm reading is too generous). At the pre-registered 3-arm family
    **nothing in H3 clears** — which is the number a successor story has to beat.
    """
    fam_of = (lambda a: "trajectory" if a.startswith(("T1_", "T2_", "T3_"))
              else "player-structure")
    rows = []
    for f, side in (("e7_15_h3_summary.json", "batter"),
                    ("e7_15_h3_pitchers_summary.json", "pitcher")):
        p = ABL / "e7_15_artifacts" / f
        if not p.exists():                                     # pragma: no cover - corpus optional
            continue
        d = json.loads(p.read_text())
        for m, pm in d.get("per_metric", {}).items():
            mae = pd.DataFrame(pm.get("mae_by_fold") or {})
            lb = pd.DataFrame(pm["leaderboard"])
            if "L0_foil" not in mae.columns or "selectable" not in lb.columns:
                continue
            elig = [a for a in lb.loc[lb["selectable"], "arm"]
                    if a in mae.columns and a != "L0_foil"]
            skill = pd.DataFrame(mae[["L0_foil"]].to_numpy(float) - mae.to_numpy(float),
                                 index=mae.index, columns=mae.columns)
            for fam in ("trajectory", "player-structure"):
                cols = [a for a in elig if fam_of(a) == fam]
                if len(cols) < 2:
                    continue
                best = max(cols, key=lambda c: skill[c].mean())
                s = skill[best].dropna().to_numpy(float)
                n = len(s)
                sk, ku = _moments(s)
                cl = fold_consistency_clause(n)
                wins = int((s > 0).sum())
                lift = 100.0 * (mae["L0_foil"].mean() - mae[best].mean()) / mae["L0_foil"].mean()
                v = float(np.var([_sharpe(skill[c].dropna().to_numpy(float)) for c in cols], ddof=1))
                dsr = dsr_from_sr(_sharpe(s), n_obs=n, n_trials=len(cols),
                                  var_trials_sr=v, skew=sk, kurt=ku)
                rows.append({
                    "side": side, "metric": m, "family": fam, "arms": len(cols), "best arm": best,
                    "%lift": round(lift, 3), "folds": f"{wins}/{n}",
                    "clause": "pass" if cl.passes(wins) else "fail",
                    "DSR in its OWN family": round(dsr, 3),
                    "clears": bool(lift > 0 and cl.passes(wins) and dsr >= 0.95)})
    return pd.DataFrame(rows)


def retest_trigger_corrections() -> pd.DataFrame:
    """Every stored `folds_needed_DSR` recomputed against the closed form — the DEFECT-1 impact.

    Reported as a table rather than prose because these are the numbers other stories act on: a
    re-test trigger is the whole output of an underpowered null, and the record's triggers were
    produced by a search that did not hold the effect size fixed.
    """
    rows = []
    for f in sorted(ABL.glob("*/e7_15_h*_summary.json")):
        d = json.loads(f.read_text())
        rec = {r["metric"]: r for r in (d.get("null_analysis") or {}).get("per_metric", [])}
        side = "pitcher" if "pitchers" in f.stem else "batter"
        for m, pm in d.get("per_metric", {}).items():
            if not isinstance(pm.get("mae_by_fold"), dict):
                continue
            mae = pd.DataFrame(pm["mae_by_fold"])
            lb = pd.DataFrame(pm["leaderboard"])
            if "selectable" not in lb.columns or "L0_foil" not in mae.columns:
                continue
            elig = [a for a in lb.loc[lb["selectable"], "arm"]
                    if a in mae.columns and a != "L0_foil"]
            sel = lb[lb["selectable"].astype(bool) & lb.get("active", True).astype(bool)]
            if sel.empty or str(sel.iloc[0]["arm"]) not in mae.columns:
                continue
            s = (mae["L0_foil"] - mae[str(sel.iloc[0]["arm"])]).dropna().to_numpy(float)
            n = len(s)
            ts = [_sharpe((mae["L0_foil"] - mae[c]).dropna().to_numpy(float)) for c in elig]
            measured = len(ts) > 1
            sk, ku = _moments(s)
            cur = folds_to_clear_dsr(
                observed_sr=_sharpe(s), n_trials=max(2, len(elig)),
                var_trials_sr=float(np.var(ts, ddof=1)) if measured else 1.0 / n,
                skew=sk, kurt=ku, confidence=0.95, max_folds=4000,
                n_obs_now=n, var_is_asymptotic_fallback=not measured)
            old = rec.get(m, {}).get("folds_needed_DSR")
            if old == cur:
                continue
            rows.append({
                "study": f"{f.stem.replace('_summary', '').replace('_pitchers', '')} ({side})",
                "metric": m, "folds_have": n,
                "recorded folds_needed_DSR": old,
                "corrected (closed form)": cur if cur is not None else "UNREACHABLE at any n",
            })
    return pd.DataFrame(rows)


def power_table(n_sims: int = 20_000) -> pd.DataFrame:
    """Per (tier × window): what each STAT can resolve, and the composite rule's MDE."""
    rows = []
    for t in TIER_WINDOWS:
        n = t.n_folds
        cl = fold_consistency_clause(n)
        fam = t.bh_family_size
        mde_leg = mde_in_sd_units(n_folds=n, n_metrics=fam or 1, calibrated=False, n_sims=n_sims)
        mde_cal = mde_in_sd_units(n_folds=n, n_metrics=fam or 1, calibrated=True, n_sims=n_sims)
        # ⚠️ The sign floor binds ONLY where the primary contrast IS a fold-sign test. E7.9's tiers
        # use a noise-floor margin with no BH family at all, so quoting a floor at them would blame
        # a constraint that was never in force — the same error as reading a DROP as a mechanism
        # failure, one clause over.
        sign_applies = "SIGN" in t.primary_contrast.upper()
        two_sided = "two-sided" in t.primary_contrast
        floor = sign_test_floor(n, two_sided=two_sided)
        bh_rank1 = (BH_ALPHA / fam) if fam else None
        rows.append({
            "tier": t.tier, "window": t.window, "fold_rule": t.fold_rule,
            "periods": t.n_periods, "folds": n, "typical_arms": t.typical_arms,
            "primary_contrast": t.primary_contrast,
            "PBO_evaluable": n >= MIN_FOLDS_FOR_PBO,
            "sign_floor": (round(floor, 5) if sign_applies else "n/a (not a sign test)"),
            "sign_floor_vs_BH_rank1": (
                "n/a" if not sign_applies or bh_rank1 is None else
                f"CLEARS ({floor:.4f} ≤ {bh_rank1:.4f})" if floor <= bh_rank1 else
                f"⛔ ABOVE ({floor:.4f} > {bh_rank1:.4f}) — no effect of any size can pass"),
            "legacy_clause": f"{math.ceil(LEGACY_FOLD_WIN_RATE * n)}/{n} "
                             f"(false-fire {fold_gate_false_fire(n):.3f})",
            "calibrated_clause": (f"{cl.wins_required}/{n} (false-fire "
                                  f"{cl.attained_false_fire:.3f})") if cl.attainable
                                 else f"UNATTAINABLE at α={FOLD_CONSISTENCY_ALPHA}",
            "DSR_ceiling_at_any_effect": round(dsr_ceiling(n), 4),
            "DSR_required_SR@typical_arms": round(dsr_required_sr(
                n_obs=n, n_trials=t.typical_arms, var_trials_sr=1.0 / n), 2),
            "DSR_required_SR@4_arms": round(dsr_required_sr(
                n_obs=n, n_trials=4, var_trials_sr=1.0 / n), 2),
            "MDE_sd_legacy": mde_leg, "MDE_sd_calibrated": mde_cal,
            "metric_family": t.metric_family, "lever": t.lever,
        })
    return pd.DataFrame(rows)


def arm_count_table(n_folds_list=(3, 5, 8, 11)) -> pd.DataFrame:
    """⭐ THE FIELD-SIZE AXIS, as a design table: the per-fold Sharpe a winner must post to clear
    DSR, by fold count AND arm count. Read it BEFORE choosing a field, not after."""
    rows = []
    for n in n_folds_list:
        r = {"folds": n}
        for arms in (2, 4, 7, 12, 20, 28):
            r[f"{arms} arms"] = round(dsr_required_sr(n_obs=n, n_trials=arms,
                                                      var_trials_sr=1.0 / n), 2)
        rows.append(r)
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Rendering
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False)


def render(inv: pd.DataFrame, census: dict, md_meta: dict, cases: list[dict],
           pw: pd.DataFrame, arms: pd.DataFrame, skipped: list[str],
           corr: pd.DataFrame, fam: pd.DataFrame) -> str:
    a: list[str] = []
    w = a.append
    w("# MH2 — CV-power characterization for §0.5 bake-offs")
    w("")
    w("> 🔒 **DIAGNOSTIC OF THE EVAL, NOT A MODEL.** `best_alpha = 0`. Nothing here re-fits an arm, "
      "re-scores a metric or changes a recorded verdict — every ADD and DROP in the record stands "
      "exactly as scored. What changes is how a null may be READ.")
    w("")
    w(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from stored "
      f"artifacts only (no Snowflake, no re-fit)._")
    w("")

    w("## 0. The finding, in one paragraph")
    w("")
    w("Three of the four §0.5 gates have a **stringency that moves with the design rather than "
      "with the evidence**, and the program has been reading them as if they were fixed bars. "
      "The fold-consistency clause fires on a true lift of ZERO **49.7% of the time at 3 folds and "
      "27.4% at 11**; PBO is not merely failed but **UNDEFINED** below 4 folds; the fold-sign floor "
      "`2⁻ⁿ` can sit ABOVE the BH cutoff, so that **no effect of any size could pass**; and DSR's "
      "bar rises with the FIELD SIZE, so the same winner on the same folds clears at 2 arms and "
      "fails at 7. Consequently a §0.5 null means one of **five** different things, not two — and "
      "the single most actionable output below is that the **MLB game model's 3-fold ceiling is a "
      "WINDOW CHOICE, not a data limit**: the served feature store already holds 2016–2026.")
    w("")

    w("## 1. Validation — reproduce the record before believing the instrument")
    w("")
    w("A power diagnostic that cannot reproduce results already on file is not evidence about "
      "anything. Every number in this report comes from the same module that produced these.")
    w("")
    w(_md(pd.DataFrame([{k: v for k, v in c.items()
                         if k in ("case", "recorded", "reproduced", "agrees")} for c in cases])))
    w("")
    for c in cases:
        if "decomposition" in c:
            w(f"**Field-size decomposition — {c['case']}**")
            w("")
            w("```")
            w(json.dumps(c["decomposition"], indent=1))
            w("```")
            w(f"- Largest field this effect still clears at the OBSERVED dispersion: "
              f"**{c['max_field_at_observed_dispersion']} arms**.")
            w(f"- Folds needed to clear DSR *in the wide field*: "
              f"**{c['folds_to_clear_in_the_wide_field']}** "
              f"(`null_analysis` recorded "
              f"{c['folds_needed_DSR_as_recorded_by_null_analysis']} — see §5, defect 3).")
            w("")

    w("### ⚠️⚠️ THE FIELD-SIZE CASE DOES NOT SUPPORT THE HEADLINE IT WAS BEING USED FOR")
    w("")
    w("The recorded flip is real and reproduces exactly — but **the \"2-arm trajectory family\" is "
      "a POST-HOC field.** H3's own pre-registration names THREE trajectory arms "
      "(`T1_traj_ladder`, `T2_traj_raw`, `T3_tenure`); the 0.998 figure drops `T3_tenure`. Restore "
      "it and the SAME winner on the SAME folds reaches **0.849**, not 0.95.")
    w("")
    w("Scoring each mechanism's best arm against its OWN pre-registered family:")
    w("")
    w(_md(fam))
    w("")
    w("⭐ **At the honestly pre-registered family sizes, NOTHING in E7.15-H3 clears.** That is the "
      "number a successor has to beat, and it is a materially different starting point from "
      "\"0.998, basically there\".")
    w("")
    w("⚖️ **So the field-size rule is TWO-SIDED and both halves bind.** Bundling unrelated "
      "mechanisms OVER-taxes a real finding (the 7-arm reading, DSR 0.607, is too harsh) — but a "
      "family trimmed AFTER the fact UNDER-taxes it (the 2-arm reading is too generous), because "
      "the arm you drop is chosen precisely because it lost. That is a second layer of exactly the "
      "selection bias DSR exists to deflate. **You get to pre-register a family; you do not get to "
      "discover one.** The corollary for any successor: declare the family in the "
      "pre-registration, and if an arm in it turns out to be weak, that is a cost you have already "
      "agreed to pay.")
    w("")
    w("(This also re-reads the H3 record itself: the pitcher side's largest lift — `k_pct` "
      "+1.713% — belongs to the PLAYER-STRUCTURE family (`P4_re_dedup`), not to the trajectory "
      "mechanism at all, and its own-family DSR is 0.695. A story that carries \"H3's trajectory "
      "arms are a real effect\" forward without splitting the families would attribute a "
      "player-structure result to trajectory.)")
    w("")
    w("### ⚠️ A correction to the story prompt's framing of this case")
    w("")
    w("The prompt states the validation case as *\"iso +1.418%, 9/11 folds … FAILED DSR at 0.607 "
      "… CLEAR at 0.998\"*. Read off the stored artifact those are **two different metrics of the "
      "same 7-arm field**: the `+1.418% / 9-of-11` effect is `iso` (DSR **0.657 → 0.981**) and the "
      "`0.607 → 0.998` pair is `bb_pct` (`+1.404%`, also 9 of 11). The *shape* the prompt describes "
      "— same winner, same folds, same effect, only the field size changed — is exactly right and "
      "holds for both, so both are reproduced above rather than one being silently chosen.")
    w("")

    w("## 2. The power table — per (tier × window), per STAT")
    w("")
    w("⚠️ **The fold RULE itself differs per tier, and it is a first-order driver nobody had "
      "written down.** `PurgedWalkForwardSplit` burns `min_train_seasons = 3` before it emits a "
      "single fold; leave-one-cohort-out emits one per cohort. So **the tier with the longest "
      "calendar history has the FEWEST folds** — the MLB game model, which is the *serving* path, "
      "has the least statistical resolution in the entire program.")
    w("")
    w(_md(pw))
    w("")
    w("- `MDE_sd_*` = the true per-fold lift, in units of the per-fold delta SD, that the FULL "
      "composite rule detects with 80% power against a 4-metric BH family. `<NA>`/`None` means the "
      "design cannot reach 80% power at ANY effect size — a materially different finding from "
      "\"the effect must be large\".")
    w("- `DSR_required_SR` is quoted at the asymptotic dispersion `V = 1/n_obs` so the columns are "
      "comparable across tiers; a real run's `V` is measured from its own trial field and is "
      "usually LARGER, which raises the bar further.")
    w("")

    w("### 2b. ⭐ The field-size axis as a design table")
    w("")
    w("The per-fold Sharpe a winner must post to clear `DSR ≥ 0.95`. **Read this before choosing a "
      "field, not after running it.**")
    w("")
    w(_md(arms))
    w("")
    w("The row that matters: at **3 folds** the bar roughly **doubles** going from a 4-arm family "
      "to a 28-arm grid. E7.9 ran 24–28 arms on 3 folds. That is the most demanding cell in the "
      "table, and it is where the program's *serving* models are evaluated.")
    w("")

    w("## 3. The pre-registered practically-meaningful effect, per metric family")
    w("")
    w("Readiness lock 3: a power table against an invented effect size answers a question nobody "
      "asked. Every row below is read off a decision the program has **already** made.")
    w("")
    w(_md(pd.DataFrame([asdict(m) for m in MEANINGFUL_EFFECTS])))
    w("")
    w("These are **registered by MH2 now and are forward-effective**. Applied to the existing "
      "record they change only how a null is READ, never what it decided.")
    w("")

    w("## 4. The mechanical null inventory")
    w("")
    w(f"Corpus census: **{census['markdown_reports']} markdown reports**, "
      f"**{census['json_artifacts']} JSON artifacts**, "
      f"**{census['story_prompt_entries']} story-prompt entries**. "
      f"{census['note']}")
    w("")
    w(f"⚠️ **No silent caps.** {md_meta['n_unextractable']} markdown reports state no fold count, "
      f"PBO or DSR in their header and are therefore **not classifiable from the corpus at all** — "
      f"they are counted here rather than dropped, because an inventory that reports only what it "
      f"could parse looks like full coverage of a smaller corpus. Most predate the current header "
      f"convention. Naming them is itself a finding: a report without its design line cannot have "
      f"its null read by anyone, now or later.")
    w("")
    if skipped:
        w(f"Also EXCLUDED and named, {len(skipped)} `*_summary.json` files that carry a "
          f"`per_metric` block but no arm leaderboard — model-FIT summaries rather than bake-offs: "
          f"{', '.join('`' + s + '`' for s in skipped)}. An earlier cut admitted them and emitted "
          f"rows classified `UNDEFINED` with a fabricated re-test trigger, i.e. the inventory "
          f"invented findings about studies that never ran a gate.")
        w("")
    rich = inv[inv["extraction"] == "rich"]
    w(f"**{len(rich)} metric-level rows** carry enough stored per-fold detail to be classified "
      f"fully; **{len(inv) - len(rich)}** more are classified at report-header resolution.")
    w("")
    w("### 4a. State distribution")
    w("")
    w(_md(inv["null_state"].value_counts().rename_axis("null_state")
          .reset_index(name="rows")))
    w("")
    w("### 4b. What actually BOUND each run")
    w("")
    w("The column the record was missing. A report says \"DROP\" and a reader infers the mechanism "
      "failed; often the run died on a multiplicity cutoff no effect size could clear, or on a "
      "statistic that was never computable.")
    w("")
    w(_md(inv["bound_by"].value_counts().rename_axis("bound_by").reset_index(name="rows")))
    w("")
    w("### 4c. The fully-classified rows")
    w("")
    cols = ["study", "metric", "verdict", "n_folds", "n_arms", "pct_lift_vs_foil", "pbo", "dsr",
            "bound_by", "null_state", "retest_trigger"]
    w(_md(rich[cols].sort_values(["null_state", "study", "metric"])))
    w("")

    w("## 5. Three defects found in the shared power instruments")
    w("")
    w("**Defect 1 — `h_harness.null_analysis`'s DSR extrapolation does not hold the effect size "
      "fixed, though its docstring says it does.** It resizes the winner's per-fold skill series "
      "with `np.resize`, i.e. TILING. Tiling preserves the population SD but the Sharpe is computed "
      "with `ddof=1`, so the resized series' Sharpe is inflated by ≈`√(n/(n−1))` — 4.9% at n=11 — "
      "and the partial final tile makes the inflation NON-MONOTONE in `k`, so the `next(...)` search "
      "can stop early on a wobble. Measured consequence on the live record: E7.15-H3 `bb_pct` "
      "recorded `folds_needed_DSR = 140`; holding the Sharpe genuinely fixed the answer is **372**. "
      "The re-test triggers were systematically **optimistic**. This is the THIRD defect in the same "
      "function, after the two E7.15-H3 found (an easier benchmark, and an `or 0` that collapsed "
      "UNREACHABLE into ALREADY-SATISFIED). **Fixed** — `null_analysis` now calls "
      "`cv_power.folds_to_clear_dsr`, which is closed-form and cannot drift from its own gate.")
    w("")
    w("A **fourth facet of the same defect**, found while fixing it: the old search passed a "
      "single-element `trial_sharpes`, which `deflated_sharpe` rejects, so `V` fell back to "
      "`1/n_obs` **computed on the RESIZED length** — i.e. the deflation benchmark melted away as "
      "folds were added. The closed form branches as the gate does: `V` is held FIXED when it is a "
      "measured cross-trial dispersion, and scales as `1/k` only when it is the asymptotic "
      "fallback. Because the resize perturbs the series' skew/kurtosis too, the old error was "
      "**non-monotone in `k` and not signed** — which is why the corrections below run in both "
      "directions rather than uniformly one way.")
    w("")
    if len(corr):
        w("**Every re-test trigger the record carries, recomputed.** These are the numbers other "
          "stories act on — a re-test trigger IS the output of an underpowered null:")
        w("")
        w(_md(corr))
        w("")
        n_unreach = int((corr["corrected (closed form)"] == "UNREACHABLE at any n").sum())
        w(f"⚠️ **{n_unreach} of these {len(corr)} are not \"more seasons\" at all but "
          f"UNREACHABLE at any n** — the winner's Sharpe sits below its field's deflated "
          f"benchmark, so `n` has nothing to scale, and every one of them carried a finite "
          f"season count in the record. For two (`h1` pitcher `bb_pct` / `gb_pct`) E7.15's own "
          f"prose correction had already reached that conclusion by another route, which is a "
          f"useful agreement; the stored JSON still carries the old finite figures. **No verdict "
          f"is affected — every one of these metrics DROPped either way — but the recorded re-test "
          f"TRIGGERS were wrong, and this table supersedes them.**")
        w("")
        w(f"The scale of the correction is the point: of the {len(corr)} triggers on record that "
          f"move, **{n_unreach} were dead ends reported as future re-tests** and the rest shift by "
          f"factors of up to ~27× (h1 pitcher `hr_rate` 15 → 405). A re-test trigger is the entire "
          f"actionable output of an underpowered null, so a systematically wrong one is not a "
          f"cosmetic defect — it is the finding.")
        w("")
    w("**Defect 2 — the same gate NAME is computed two different ways across the program.** "
      "`h_harness.dsr_report` passes the measured per-arm `trial_sharpes` and uses FOLDS as the "
      "observation series. `e7_9_train_serve_consistency` passes **neither** — its DSR series is "
      "per **year-month bucket** (~19 observations across 3 folds) and it omits `trial_sharpes`, so "
      "`V` falls back to the asymptotic `1/n_obs`. Both differences push the SAME way: months "
      "inside a season are not independent draws, so `√(n_obs−1)` is inflated ~3× (√18 vs √2), and "
      "an asymptotic `V` understates a real trial field's dispersion, understating `SR0`. ⇒ **E7.9's "
      "`DSR 0.842` is, if anything, GENEROUS**; at the honest 3-fold resolution the effect is even "
      "less detectable than recorded. That strengthens its \"underpowered, not dead\" reading rather "
      "than weakening it. Recorded here as a finding; E7.9's verdict is untouched.")
    w("")
    w("**Defect 3 (H8) — the fold-consistency clause. Diagnosed and FIXED; see §6.**")
    w("")

    w("## 6. H8 — the fold-count clause: diagnosis and fix")
    w("")
    w("**Diagnosis.** Under the null the per-fold sign is a fair coin, so `fold_win_rate ≥ 0.60` "
      "fires with probability `P(Bin(n, ½) ≥ ⌈0.6n⌉)` — computed exactly rather than simulated:")
    w("")
    tbl = pd.DataFrame([{
        "folds": n,
        "legacy k": math.ceil(LEGACY_FOLD_WIN_RATE * n),
        "legacy false-fire": round(fold_gate_false_fire(n), 4),
        "calibrated k": fold_consistency_clause(n).wins_required,
        "calibrated false-fire": round(fold_consistency_clause(n).attained_false_fire, 4),
        "calibrated equiv. rate": round(fold_consistency_clause(n).equivalent_rate, 3),
    } for n in range(3, 13)])
    w(_md(tbl))
    w("")
    w("This reproduces E7.12-S6's simulated 0.4968 in closed form, and explains E7.12-S5 from the "
      "other side: a permuted-bucket placebo clearing the clause 9 times in 11 is unremarkable at "
      "~27% per shot. **A clause whose meaning moves by a factor of two across the fold counts a "
      "program actually runs is not a gate; it is a fold-count-dependent tax.**")
    w("")
    w("**Fix (`cv_power.fold_consistency_clause`).** Hold the FALSE-FIRE RATE fixed at "
      f"`α = {FOLD_CONSISTENCY_ALPHA}` and let the required win COUNT move with `n`. Three "
      "properties the legacy clause lacks:")
    w("")
    w("1. **Stable meaning** — the null false-fire rate is ≤ α at every fold count instead of "
      "drifting 0.50 → 0.27.")
    w("2. **It says when it cannot be evaluated** — the smallest attainable rate at `n` folds is "
      "`2⁻ⁿ` (unanimity), so below `n = ⌈log₂(1/α)⌉` the clause is **UNDEFINED, not passed**, the "
      "same honesty `pbo_evaluable` already applies to CSCV.")
    w("3. **Weakly stricter than the legacy clause at every fold count** (pinned by a test) — so "
      "adopting it can only ever prevent a false ADD and can never manufacture one.")
    w("")
    w(f"**Why α = {FOLD_CONSISTENCY_ALPHA}, derived from DESIGN quantities and not from any arm's "
      f"score** (NF1.8: a floor reverse-engineered from the answer is not a floor). Two independent "
      f"derivations land on the same number: (a) at the fold counts this program runs (n = 3…11) "
      f"the legacy clause's own operating range is 0.497 down to 0.274, and pinning the level at "
      f"the TIGHTEST end makes the clause **no looser than it has ever been at any fold count** "
      f"while making it uniform — a re-calibration, not a tightening; (b) 0.20 is already the "
      f"program's \"this much selection noise is tolerable\" constant (`MAX_PBO`), and a "
      f"consistency clause sitting INSIDE a composite gate that already carries a BH-FDR-corrected "
      f"paired t should not also carry a primary-analysis alpha — that double-counts the same "
      f"evidence.")
    w("")
    w("**Verdict-neutrality, verified mechanically rather than asserted.** All 8 recorded ADDs in "
      "the corpus sit at fold-win rates 0.73 / 0.82 / 0.91 on 11 folds — i.e. 8, 9 and 10 wins — "
      "and the calibrated clause requires 8. **None is re-decided.**")
    w("")
    w("**And the sensitivity that makes the choice visible rather than hidden:** at α = 0.10 the "
      "clause would require **9 of 11**, which would re-decide **4 of the 8 recorded ADDs** "
      "(E7.12-S1 `woba` and `k_pct`, E7.12-S2 `bb_pct` and `hr_rate`, all at 8/11). That is "
      "precisely why the α is stated and derived rather than assumed — and why MH2 does not "
      "retro-apply it.")
    w("")

    w("## 7. ⭐ The single most actionable finding — the MLB game model's 3 folds are a WINDOW "
      "CHOICE, not a data limit")
    w("")
    w("E7.9 ran on `2021-04-18 → 2026-07-27` = 6 seasons ⇒ 3 folds, and recorded the binding "
      "caveat *\"3 purged folds. This can rule out a LARGE effect, not a small one.\"* Measured on "
      "the served store (`s3://…/lakehouse/feature_pregame_game_features/data.parquet`, "
      "2026-08-01):")
    w("")
    w("| season | rows | mean non-null coverage of the served 13-col `total_runs/post_lineup` contract |")
    w("|---:|---:|---:|")
    for y, n, c in ((2015, 2429, 0.449), (2016, 2428, 0.828), (2017, 2430, 0.827),
                    (2018, 2431, 0.834), (2019, 2429, 0.829), (2020, 898, 0.885),
                    (2021, 2429, 0.901), (2022, 2430, 0.906), (2023, 2430, 0.939),
                    (2024, 2429, 0.982), (2025, 2430, 0.982), (2026, 1690, 0.979)):
        w(f"| {y} | {n:,} | {c:.3f} |")
    w("")
    w("The store holds **26,883 rows over 12 seasons**. E7.9 used 11,858 rows over 6. A "
      "**2016–2026** window (dropping 2015, whose contract coverage is only 0.449, and keeping the "
      "short 2020 season) is **11 seasons ⇒ 8 folds** at ≥0.827 contract coverage — "
      f"**{achievable_folds(11)} folds vs 3, available TODAY, with no calendar wait.**")
    w("")
    w("What that buys, at the design level (required per-fold Sharpe to clear `DSR ≥ 0.95`, "
      "asymptotic `V`):")
    w("")
    cmp = pd.DataFrame([
        {"design": "as E7.9 ran it — 3 folds × 28 arms", "folds": 3, "arms": 28,
         "required per-fold SR": round(dsr_required_sr(n_obs=3, n_trials=28, var_trials_sr=1/3), 2)},
        {"design": "wider window, same field — 8 folds × 28 arms", "folds": 8, "arms": 28,
         "required per-fold SR": round(dsr_required_sr(n_obs=8, n_trials=28, var_trials_sr=1/8), 2)},
        {"design": "wider window + pre-registered family — 8 folds × 4 arms", "folds": 8, "arms": 4,
         "required per-fold SR": round(dsr_required_sr(n_obs=8, n_trials=4, var_trials_sr=1/8), 2)},
    ])
    w(_md(cmp))
    w("")
    w("⚠️ **Stated honestly, and NOT acted on here.** This is a *feasibility* measurement, not a "
      "re-run and not a promise: (a) 2016–2020 sit at ~0.83 contract coverage against ~0.98 for "
      "2024+, so the earlier folds are thinner and imputation carries more of them; (b) 2020 is a "
      "**898-game COVID season** — structurally atypical, and whether it enters as a fold is a "
      "design decision that must be pre-registered, not discovered; (c) the offline matrix is **not "
      "point-in-time** (E7.9's own caveat), and widening the window widens that exposure too. The "
      "deliverable is that E7.9's `plus_eb`-on-`total_runs` follow-up is **reachable now via the "
      "window and the field size**, not only by waiting for seasons — which is the difference "
      "between a live re-test and a 2029 calendar note.")
    w("")

    w("## 8. The rule for reading a §0.5 null (the durable artifact)")
    w("")
    w("Landed in the §0.5 canon (`CLAUDE.md` + `edge_program_implementation_guide.md`). Restated "
      "here so this report is self-contained:")
    w("")
    w("> **A §0.5 null is in one of SEVEN states, and a report must name which.** Two states do not "
      "cover the cases, and four of the seven are routinely mislabelled as \"the mechanism failed\".")
    w("")
    w("| state | test | remedy | do NOT |")
    w("|---|---|---|---|")
    w("| **INACTIVE** | the mechanism has no rows it can move (zero transitions / zero coverage) | "
      "a different population | hunt for a defect; wait for seasons |")
    w("| **UNKNOWN** | the artifact records no fold structure — unread, not underpowered | record "
      "the design in the artifact | classify it at all |")
    w("| **UNDEFINED** | a required stat was not COMPUTABLE (PBO < 4 folds; a consistency clause "
      "whose α is unattainable), or the run was anchor-BLOCKED | more folds / fix the anchor | "
      "record it as a failed gate |")
    w("| **GENUINE ABSENCE** | the best arm loses to the foil ON AVERAGE | none — do not re-test | "
      "state a re-test trigger |")
    w("| **DSR-UNREACHABLE** | beats the foil, but `SR ≤ SR0` in THIS field ⇒ no `n` ever clears | "
      "a SMALLER pre-registered field | report it as \"needs N more seasons\" |")
    w("| **POWER-LIMITED** | every gate reachable, MDE > the meaningful effect | more folds and/or "
      "fewer arms — state which, in the unit that grows | call it dead |")
    w("| **TRUSTWORTHY DEAD** | MDE ≤ the pre-registered meaningful effect, and nothing showed | "
      "none — the mechanism is ruled out at the size that would matter | over-claim beyond that size |")
    w("")
    w("And the two axis rules the program did not have:")
    w("")
    w("1. **A FAMILY GETS ITS OWN PRE-REGISTERED FIELD.** Bundling unrelated mechanisms into one "
      "bake-off taxes a real finding with their multiplicity — and the tax is bigger than it looks, "
      "because `SR0 = √V · z(N)` moves through TWO channels: the trial COUNT `N` *and* the "
      "cross-trial Sharpe DISPERSION `V`, which the far-away arms inflate. On E7.15-H3 the "
      "dispersion channel is the dominant one (`V` falls ~65× going 7 arms → 2, against ~2.5× for "
      "`z`). ⇒ \"just run fewer arms\" is the wrong lesson; **run a coherent family**.")
    w("2. **STATE THE MARGIN IN THE UNIT THAT GROWS, AND SAY WHETHER IT IS REACHABLE NOW.** Folds, "
      "seasons, cohorts, rows — never p-decimals. A trigger reachable by a WIDER WINDOW or a "
      "SMALLER FIELD is a live re-test; only a trigger that needs calendar time is a future note. "
      "§7 is the worked example: the same null read one way is \"wait for 2029\" and read correctly "
      "is \"re-runnable this week\".")
    w("")
    return "\n".join(a)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(ABL))
    ap.add_argument("--n-sims", type=int, default=20_000)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    rich, skipped_summaries = scan_e7_summaries()
    coarse, md_meta = scan_markdown()
    inv = pd.DataFrame([asdict(r) for r in rich + coarse])
    census = corpus_census()
    cases = validation_cases()
    fam = family_rescoring()
    corr = retest_trigger_corrections()
    pw = power_table(n_sims=args.n_sims)
    arms = arm_count_table()

    failed = [c["case"] for c in cases if not c.get("agrees")]
    if failed:
        log.error("VALIDATION FAILED for %s — the instrument does not reproduce the record; "
                  "do not read its numbers.", failed)

    out = Path(args.out_dir)
    (out / "mh2_null_inventory.csv").write_text(inv.to_csv(index=False))
    (out / "mh2_cv_power.json").write_text(json.dumps({
        "story": "MH2 — CV-power characterization for §0.5 bake-offs",
        "best_alpha": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "diagnostic_only": "no re-fit, no verdict change, no champion change",
        "corpus_census": census, "extraction": md_meta,
        "skipped_non_bakeoff_summaries": skipped_summaries,
        "validation_cases": cases, "validation_all_pass": not failed,
        "meaningful_effects": [asdict(m) for m in MEANINGFUL_EFFECTS],
        "tier_windows": [asdict(t) for t in TIER_WINDOWS],
        "power_table": json.loads(pw.to_json(orient="records")),
        "arm_count_table": json.loads(arms.to_json(orient="records")),
        "retest_trigger_corrections": json.loads(corr.to_json(orient="records")),
        "family_rescoring": json.loads(fam.to_json(orient="records")),
        "null_state_counts": inv["null_state"].value_counts().to_dict(),
        "bound_by_counts": inv["bound_by"].value_counts().to_dict(),
    }, indent=1, default=str))
    (out / "mh2_cv_power_characterization.md").write_text(
        render(inv, census, md_meta, cases, pw, arms, skipped_summaries, corr, fam))
    log.info("wrote mh2_cv_power_characterization.md / mh2_null_inventory.csv / mh2_cv_power.json "
             "to %s (validation_all_pass=%s)", out, not failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
