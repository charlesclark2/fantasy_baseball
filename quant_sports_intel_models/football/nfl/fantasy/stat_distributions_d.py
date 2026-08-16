"""stat_distributions_d.py — NF-W6d: distributional outputs for ALL optimizer-input metrics —
complete the per-stat distribution substrate (pure).

THE STORY IN ONE PARAGRAPH. NF-W6b/W6c (+ W6b-C / W6c-wire) shipped honest per-stat
distributions for 7 cells — the yardage backbone, QB passing_tds and RB rushing_tds. The rest of
the scored weekly stat line is still POINT-ONLY: receptions (1 PPR point each) and receiving TDs
(6 points) above all, then passing interceptions, carries / attempts / targets, fumbles lost and
two-point conversions. A win-probability (boom/bust) optimizer is only as good as the per-player-
week fantasy-point distribution it samples, and that distribution is assembled from PER-STAT
distributions — so every scored stat needs a calibrated one. The same per-stat objects power the
"what might this player do this week" range on the frontend. NF-W6d completes the substrate in
three phases, each a pre-registered instrument, each derived from stored fold scores at zero refit
cost (the NF-W2e/W3 verdict-derived-not-stored rule):

  PHASE A — CEILING-GATE FIRST (NF-W6's oracle-first discipline, extended). Every remaining
  optimizer-input cell is measured for distributional HEADROOM over its point mean before anything
  is built: per-FORM block-peeking oracles (NF-D16 (g‴) — the forms differ in capacity and the
  candidate forms NEST the marginal, so one field-wide ceiling would be a false veto) floored at
  MATCHED-n controls (NF1.9 (f)) — and, ⭐ the NF-W6b-C refinement, the conditional forms' matched
  window is sized to the cross-fit PEEK'S EFFECTIVE fit size ((K−1)/K of the block), because a
  full-block control hands the CONTROL ~1.5× the rows the peek trains on and reads as a false
  near-tie (NF1.7 (b): same-family AND same-sample). A cell with no ceiling is a RECORDED FINDING
  (the point mean is already near-optimal there), never something a bake-off is forced on.

  PHASE B — §0.5 BAKE-OFF the licensed cells (the NF-W6b methodology, atom-aware): a FRESH
  pre-registered per-CLASS family — a COUNT class (attempts / carries / targets / receptions:
  moderate atoms, real conditional spread) and an EVENT class (TDs / INTs / fumbles / 2-pt: zero-
  heavy) — declared up front. ⛔ NO linear-residual arm on a zero-heavy cell and ⛔ NO non-atom-
  aware `inc_head_bank` foil there (the NF-W6b-C field-inflation lesson: a position-constant
  residual bank around a mean cannot express an 86% atom, and its guaranteed huge loss inflates
  the very deflation bar that refuses the cell). CRPS primary (`crps_q199`; ⛔ MAE is AST-banned
  — NF-D11/D14); the nihilist and both sharpness degenerates are SCORED, never reasoned about;
  the coverage floor is ONE-SIDED on these zero-atom targets (NF1.9 (e)); `tie_with_foil` for
  the nested forms (Batter-Props Ph2); per-FORM oracle floors; PBO<0.2, DSR≥0.95 with DSR-CONV
  pre-registered FORWARD (anchors never enter the trial field — MH2.1 (a) — so the degenerate-
  excluded V is the structural fact, stated as provenance), two-family BH-FDR (own AND pooled);
  `cv_power.classify_null(declared_field_size=…)` read through `field_remedy_admissible` (MH2.7).
  ⭐ A DSR failure is READ FOR ITS MECHANISM (observed SR vs the field's SR0, and which trial arm
  inflates V) BEFORE it is filed POWER_LIMITED (NF-W6b-C: "≈0 more folds" is a misleading trigger
  when the mechanism is field dispersion). ⚠️ REPRODUCTION CONTROL (NF-W2d): the 7 already-served
  cells' winning constructions are re-run through the SERVING DISPATCH on every fold and must
  reproduce the certifying records' fold CRPS byte-identically, or THE RUN IS INVALID.

  PHASE C — A PRINCIPLED DEFAULT for the no-ceiling cells: the optimizer needs a distribution for
  EVERY scored stat, so cells Phase A found no headroom on (and Phase-B nulls, and the minor
  channels outside the modeled map) get a CALIBRATED DEFAULT — chosen by a pre-registered ORDER
  (a discrete NB2/Poisson around the champion head mean with a purged-calibration dispersion, then
  the per-position discrete climatology), each VALIDATED for calibration (coverage floor + randomized
  PIT decile flatness — E2.1-r: for a discrete predictive gate on PIT flatness, keep coverage as a
  floor). ⛔ NOT a bake-off winner and NOT selected on CRPS — there is no ceiling to beat; it is
  recorded as a calibrated default. The nihilist is still SCORED against it (NF-D14).

⚖️ EDGE-INDEPENDENT (`best_alpha` N/A) · DEPLOY-HELD · NF-G0-GOVERNED: promotes nothing,
publishes nothing, retrains nothing; research-only, no changelog. Runtime gate N/A — no
`--publish`, no `deploy.sh`, no Dagster, no S3 write, no dbt: local artifacts + a registry entry
read only by governance. Every emitted string is a calibrated RANGE, never an edge / win-rate claim.

⏭️ EXPLICITLY OUT OF SCOPE (the named follow-on): the arbitrary-league RE-SCORING ASSEMBLY —
per-stat distributions → one per-player fantasy-point distribution under a league's scoring, WITH
cross-stat correlation — is where these become optimizer-ready, and it triggers the three-
implementations parity tax (fantasy_engine / browser TS / Lambda). This story COMPLETES the
per-stat inputs; the assembly is its own PR.

Pure module — no lake IO. Runners: `run_nf_w6d_ceiling_gate.py` (A), `run_nf_w6d_stat_bakeoff.py`
(B), `run_nf_w6d_defaults.py` (C), `run_nf_w6d_serve_stat_distributions.py` (serve + stage).
"""
from __future__ import annotations

import json
import zlib
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin2_tail_extension as M2
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_c as SDC
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W6d"
PRIMARY_METRIC = "crps_q199"
EVAL_LEVELS: np.ndarray = MC.EVAL_LEVELS
#: ⭐ FRESH registration ⇒ fresh seed, deliberately ≠ SD._SEED (20260815) and SDC._SEED (20260816).
_SEED = 20260817

# ── The optimizer-input stat universe ───────────────────────────────────────────────────────────
#: The champion's raw-line components (`WP.COMPONENTS`, imported — never re-typed) plus the two
#: scored stats the weekly line does not yet emit at all (fumbles lost, two-point conversions).
#: These 13 are the weekly stats a league's scoring can price (`STAT_FIELD` minus K/DST).
EXTRA_STATS: tuple[str, ...] = ("fumbles_lost", "two_pt")
ALL_STATS: tuple[str, ...] = (*WP.COMPONENTS, *EXTRA_STATS)
#: Labels this story must ATTACH to the certified NF-W6 matrix (the others already ride it).
ATTACH_STATS: tuple[str, ...] = ("passing_interceptions", "fumbles_lost", "two_pt")
#: The nflverse columns each attached label is the SUM of (fumbles/2-pt are split by phase upstream).
ATTACH_SOURCES: dict[str, tuple[str, ...]] = {
    "passing_interceptions": ("passing_interceptions",),
    "fumbles_lost": ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"),
    "two_pt": ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"),
}

#: The 7 cells ALREADY served (NF-W6c + NF-W6c-wire) — the reproduction-control set. Imported by
#: pointer at run time from the serving module (a second copy could drift); named here for the
#: reader. Nothing in this story re-decides them.
SERVED_CELLS_PRIOR: tuple[str, ...] = (
    "QB|passing_tds", "QB|passing_yards", "QB|rushing_yards", "RB|rushing_yards",
    "TE|receiving_yards", "WR|receiving_yards", "RB|rushing_tds")
#: The one W6b recorded null awaiting its calendar-bound re-test (PM Decision B) — NOT re-opened
#: here; it receives a Phase-C default until then.
WITHHELD_PRIOR: tuple[str, ...] = ("RB|receiving_yards",)

# ── Stat classes (declared up front — they set the family, the foils and the FDR family) ────────
#: COUNT class: volume counts with a moderate atom and real conditional spread.
COUNT_STATS: tuple[str, ...] = ("attempts", "carries", "targets", "receptions")
#: EVENT class: zero-heavy scoring events (the NF-W6b-C atom-aware regime).
EVENT_STATS: tuple[str, ...] = (
    "receiving_tds", "rushing_tds", "passing_interceptions", "fumbles_lost", "two_pt")


def stat_class(stat: str) -> str:
    if stat in COUNT_STATS:
        return "count"
    if stat in EVENT_STATS:
        return "event"
    raise KeyError(f"{stat!r} is not a NF-W6d gated stat (count {COUNT_STATS} / event "
                   f"{EVENT_STATS})")


#: ⭐ THE MODELED CELL MAP — every remaining optimizer-input (position, stat) cell on the NF-W6
#: declared scope (QB rushing is a real channel and is in; WR/TE rushing and QB/RB receiving are
#: MINOR channels — see MINOR_CHANNELS — that get a Phase-C default, never a gate). The four
#: TD cells NF-W6 closed (QB rushing_tds, RB/WR/TE receiving_tds) are RE-GATED here on purpose:
#: NF-W6 measured them with NON-atom-aware forms only (marginal / head+bank / plain quantile),
#: and NF-W6b-C then showed an atom-aware neighborhood form beating the climatology by 13% on a
#: cell the same instrument had read at 4% — re-opening needs a different MECHANISM, and the
#: atom-aware forms ARE that mechanism (declared, so it is a fresh measurement, not a re-read).
POSITION_STATS: dict[str, tuple[str, ...]] = {
    "QB": ("attempts", "passing_interceptions", "carries", "rushing_tds", "fumbles_lost",
           "two_pt"),
    "RB": ("carries", "targets", "receptions", "receiving_tds", "fumbles_lost", "two_pt"),
    "WR": ("targets", "receptions", "receiving_tds", "fumbles_lost", "two_pt"),
    "TE": ("targets", "receptions", "receiving_tds", "fumbles_lost", "two_pt"),
}
GATED_STATS: tuple[str, ...] = (
    "attempts", "passing_interceptions", "carries", "rushing_tds", "targets", "receptions",
    "receiving_tds", "fumbles_lost", "two_pt")
#: The minor channels — a distribution is still REQUIRED for the assembly (every scored stat,
#: every player), so each gets a Phase-C climatology default; none is gated or baked off.
MINOR_CHANNELS: dict[str, tuple[str, ...]] = {
    "QB": ("targets", "receptions", "receiving_yards", "receiving_tds"),
    "RB": ("attempts", "passing_yards", "passing_tds", "passing_interceptions"),
    "WR": ("attempts", "passing_yards", "passing_tds", "passing_interceptions",
           "carries", "rushing_yards", "rushing_tds"),
    "TE": ("attempts", "passing_yards", "passing_tds", "passing_interceptions",
           "carries", "rushing_yards", "rushing_tds"),
}

# ── Families (per class; the whole field is declared before any scoring) ────────────────────────
#: The COUNT family: 4 classes — every arm prices the atom and/or the conditional spread. The
#: quantile form is admissible here (moderate atoms; NF-W6b showed it winning QB passing_yards
#: DESPITE under-pricing the atom — sufficient, not necessary).
FAMILY: dict[str, tuple[str, ...]] = {
    "count": ("lgbm_quantile_tail", "lgbm_hurdle_tail", "knn_quantile", "count_negbin"),
    # The EVENT family: the NF-W6b-C coherent atom-aware family, verbatim. ⛔ NO linear-residual
    # arm, ⛔ NO plain quantile-bank arm (a position-constant/flat tail cannot express a 60–99%
    # atom, and its guaranteed loss inflates V — the exact W6b-C mechanism).
    "event": ("lgbm_hurdle_tail", "knn_quantile", "count_negbin"),
}
FOILS: dict[str, tuple[str, ...]] = {
    "count": ("inc_head_bank", "inc_climatology"),
    "event": ("inc_climatology",),           # ⛔ inc_head_bank banned on the event class
}
#: The permuted anchor runs ONE declared arm's identical code path on labels permuted within
#: (position, week) — the quantile form on COUNT (NF-W6b's choice), kNN on EVENT (NF-W6b-C's).
PERMUTED_FORM: dict[str, str] = {"count": "lgbm_quantile_tail", "event": "knn_quantile"}
#: ⛔ ON THE RECORD — a guard fails if either enters an event-class field.
BANNED_ON_EVENT: dict[str, str] = {
    "enet_residual": "the W6b field-inflating defect (trial Sharpe −9.199 on an 86%-zero cell)",
    "inc_head_bank": "the same non-atom-aware residual-bank class in the incumbent costume",
    "lgbm_quantile_tail": ("a flat-tailed pooled quantile bank cannot price a 60–99% atom; "
                           "its guaranteed loss would inflate the field's V"),
}
#: MH2.7: the smallest field pre-registered for each class — passed to `classify_null`.
DECLARED_FIELD_SIZE: dict[str, int] = {k: len(v) for k, v in FAMILY.items()}

# ── Per-form oracle / matched-n pairs (NF-D16 (g‴) / NF1.9 (f)) ─────────────────────────────────
#: form → (oracle label, matched label). `marginal` keeps the W6 sizing (a climatology is
#: n-insensitive at these sizes and this keeps its figure comparable to the W6 record); every
#: CONDITIONAL form's matched control is sized to the peek's effective (K−1)/K n (W6b-C).
ORACLE_PAIRS: dict[str, tuple[str, str]] = {
    "marginal": ("oracle_marginal", "matched_marginal"),
    "head_bank": ("oracle_head_bank", "matched_head_bank"),
    "cand_quantile": ("oracle_cand_quantile", "matched_cand_quantile"),
    "knn": ("oracle_knn", "matched_knn"),
    "hurdle": ("oracle_hurdle", "matched_hurdle"),
    "negbin": ("oracle_negbin", "matched_negbin"),
}
#: The forms measured per class in Phase A: the class's incumbents' forms + every family form.
CEILING_FORMS: dict[str, tuple[str, ...]] = {
    "count": ("marginal", "head_bank", "cand_quantile", "knn", "hurdle", "negbin"),
    "event": ("marginal", "knn", "hurdle", "negbin"),
}
#: arm → its own form (the winner's OWN pair gates in Phase B).
ARM_FORM: dict[str, str] = {
    "lgbm_quantile_tail": "cand_quantile", "lgbm_hurdle_tail": "hurdle",
    "knn_quantile": "knn", "count_negbin": "negbin",
    "inc_climatology": "marginal", "inc_head_bank": "head_bank",
}
DEGENERATES: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width")

#: A conditional (hurdle) fit needs at least this many NON-ZERO rows on its fitting side; below
#: it the form is INAPPLICABLE for that (stat, fold) — recorded loudly (a score of None), never
#: silently scored on a constant (NF1.7 (a) / NF-W3 (b)). = the champion LGBM `min_child_samples`.
MIN_COND_ROWS = 40

#: The NF-W5/W6 bands on ceiling_pct — <2 NO · 2–5 MARGINAL · ≥5 YES — imported.
CEILING_BANDS = EM.CEILING_BANDS
#: ⭐ THE LICENSING RULE (declared BEFORE the run): a cell is licensed for the Phase-B bake-off
#: at MARGINAL as well as YES (≥ 2% AND stat_ok). WHY, on the record: the block-peeking ceiling is
#: a conservative reader of the ATOM-AWARE forms' full-train capacity — a K-fold cross-fit peek
#: trains on ~2/3 of a ~4k-row block (kNN with k=300 there is nearly the marginal; a boosted
#: hurdle on ~700 position rows is weak), while the bake-off arm trains on ~75k rows. NF-W6b-C
#: measured exactly this: RB|rushing_tds read MARGINAL 4.08% at the gate and the bake-off arm
#: then beat the climatology by 12.97% (SHIP). Under-reading is the safe direction for a NO but
#: the wrong direction for a MARGINAL, so MARGINAL licenses here; a NO stays a recorded finding.
LICENSE_BANDS: tuple[str, ...] = ("YES", "MARGINAL")

#: REPORT-ONLY PPR weights (⛔ never a gate): CRPS lift × weight = a points-units MARGINAL
#: contribution, quoted so the "prioritize by fantasy-point weight" reading is legible.
PPR_WEIGHTS: dict[str, float] = {
    "receptions": 1.0, "receiving_tds": 6.0, "rushing_tds": 6.0, "passing_interceptions": -2.0,
    "fumbles_lost": -2.0, "two_pt": 2.0, "targets": 0.0, "carries": 0.0, "attempts": 0.0,
}

#: Batter-Props Ph2 `tie_with_foil`: the nested forms (kNN k→n reproduces the climatology; NB2 at
#: the α floor is Poisson; hurdle p0→marginal) make a lead within numerical precision a COLLAPSE
#: = a TIE, never a win. Same constant as W6b-C.
TIE_EPS_CRPS = SDC.TIE_EPS_CRPS

# ── Phase C: the calibrated default ─────────────────────────────────────────────────────────────
#: The pre-registered ORDER — the FIRST default that passes calibration is recorded; there is NO
#: CRPS contest between them (a default is not a selected model). MODELED cells try the NB2 form
#: first (it moves P(0) and the spread with the head mean); MINOR channels take the climatology.
DEFAULT_ORDER: dict[str, tuple[str, ...]] = {
    "modeled": ("count_negbin", "climatology"),
    "minor": ("climatology",),
}
DEFAULT_FORMS: tuple[str, ...] = ("count_negbin", "climatology")
#: Calibration gates for a default: the one-sided coverage FLOOR (E2.1-r: a floor, never a
#: target; the atom makes an upper gate inverted — NF1.9 (e)) AND randomized-PIT decile flatness
#: (E2.1-r: gate a DISCRETE predictive on PIT flatness). 0.03 ≈ 8+ binomial SE at the cell sizes
#: here (~5–10k rows: SE per decile ≈ 0.003–0.004) — a MATERIALITY bound, declared, not a
#: significance test (a significance test at n=10k would fail every honest discrete predictive).
PIT_MAX_DECILE_DEV = 0.03
#: A cell whose EVERY default fails calibration is emitted with the LAST form and a LOUD
#: `calibration_warning` — never silently, never withheld (the optimizer needs a distribution).

KNN_K = SD.KNN_K
MIN_TAIL_N = SD.MIN_TAIL_N
FIT_LEVELS: tuple[float, ...] = WP.FIT_LEVELS
TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
POSITIONS = WP.POSITIONS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
CAPTURE_ERA_FOLDS: tuple[str, ...] = EM.CAPTURE_ERA_FOLDS
CROSSFIT_K = EM.CROSSFIT_K

# Shared machinery — IMPORTED, never re-typed (NF-W2d discipline). The arms ARE the pinned W6b /
# W6b-C code paths, by identity (guard-tested), so this field re-derives nothing.
arm_lgbm_quantile_tail = SD.arm_lgbm_quantile_tail
arm_lgbm_hurdle_tail = SD.arm_lgbm_hurdle_tail
arm_knn_quantile = SD.arm_knn_quantile
arm_count_negbin = SDC.arm_count_negbin
mixture_quantiles199 = SD.mixture_quantiles199
structural_coverage_note = SD.structural_coverage_note
score_bank = EM.score_bank                       # ONE reducer; refuses non-finite (NF-W3 (b))
cell_crps_matrix = EM.cell_crps_matrix
cell_key = EM.cell_key
paired_ci95 = GE.paired_ci95
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
gate_sensitivity = GE.gate_sensitivity
matched_window = SDC.matched_window              # (K−1)/K sizing — the W6b-C refinement
oracle_knn = SDC.oracle_knn
matched_knn = SDC.matched_knn
oracle_negbin = SDC.oracle_negbin
matched_negbin = SDC.matched_negbin
nb2_bank199 = SDC.nb2_bank199
fit_nb2_dispersion_by_pos = SDC.fit_nb2_dispersion_by_pos
compose_gate_w6bc = SDC.compose_gate_w6bc        # the SAME ten named clauses, by identity
STATISTICAL_CHECKS = SDC.W6BC_STATISTICAL_CHECKS
CONSTRAINT_CHECKS = SDC.W6BC_CONSTRAINT_CHECKS
ANCHOR_CHECKS = SDC.W6BC_ANCHOR_CHECKS
randomized_pit_levels = M2.randomized_pit_levels
pit_stats = MC.pit_stats
pool_pit_stats = MC.pool_pit_stats


class InapplicableForm(ValueError):
    """A declared form cannot be fit on this (stat, fold) — too few non-zero rows on its fitting
    side. Raised LOUDLY by the constructing function; the runner records the reason and a score
    of None for that label, and the selection layer treats the form as INAPPLICABLE on that cell
    (excluded from the ceiling max / the field, and SAID so). Never a silent constant."""


# ── Cells ───────────────────────────────────────────────────────────────────────────────────────
def cells() -> tuple[str, ...]:
    return tuple(cell_key(p, s) for p in POSITIONS for s in POSITION_STATS[p])


def cells_for_class(cls: str) -> tuple[str, ...]:
    return tuple(c for c in cells() if stat_class(c.split("|", 1)[1]) == cls)


def minor_cells() -> tuple[str, ...]:
    return tuple(cell_key(p, s) for p in POSITIONS for s in MINOR_CHANNELS[p])


def substrate_cells() -> tuple[str, ...]:
    """EVERY (position, stat) cell the assembly needs: the 7 served + the withheld null + this
    story's gated cells + the minor channels — 4 positions × 13 stats = 52, each exactly once."""
    out = [*SERVED_CELLS_PRIOR, *WITHHELD_PRIOR, *cells(), *minor_cells()]
    if len(out) != len(set(out)):
        dup = sorted({c for c in out if out.count(c) > 1})
        raise ValueError(f"substrate cell map double-counts {dup}")
    return tuple(out)


def assert_substrate_is_complete() -> None:
    """4 positions × 13 optimizer-input stats, exactly once each — the completeness the story
    claims is measured, not asserted in prose."""
    want = {cell_key(p, s) for p in POSITIONS for s in ALL_STATS}
    have = set(substrate_cells())
    if have != want:
        raise ValueError(f"substrate incomplete: missing {sorted(want - have)}, extra "
                         f"{sorted(have - want)}")


def family_for(cell: str) -> tuple[str, ...]:
    return FAMILY[stat_class(cell.split("|", 1)[1])]


def foils_for(cell: str) -> tuple[str, ...]:
    return FOILS[stat_class(cell.split("|", 1)[1])]


def ceiling_forms_for(cell: str) -> tuple[str, ...]:
    return CEILING_FORMS[stat_class(cell.split("|", 1)[1])]


def bakeoff_labels(cls: str) -> tuple[str, ...]:
    """The full label set a Phase-B fold scores for one class."""
    return (*FAMILY[cls], *FOILS[cls], *DEGENERATES, f"permuted_{PERMUTED_FORM[cls]}",
            *(lab for f in ("marginal", *(ARM_FORM[a] for a in FAMILY[cls]))
              for lab in ORACLE_PAIRS[f]))


def eligible_labels(cls: str) -> list[str]:
    """The set the selection actually searches — real arms + foils. Anchors NEVER enter (NF1.8 /
    MH2.1 (a): a deflation statistic over a field containing its anchors measures the anchors)."""
    return [*FAMILY[cls], *FOILS[cls]]


def ceiling_labels(cls: str) -> tuple[str, ...]:
    """The full label set a Phase-A fold scores for one class."""
    return (*FOILS[cls], *DEGENERATES,
            *(lab for f in CEILING_FORMS[cls] for lab in ORACLE_PAIRS[f]))


# ── Label attach (INT / fumbles lost / 2-pt join the certified matrix) ──────────────────────────
def attach_extra_labels(feat: pd.DataFrame, extra_feed: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Merge the three attached labels onto the certified matrix at (season, week, gsis_id) —
    the `EM.attach_td_labels` shape verbatim: a rostered-no-stat week is a REAL ZERO (the frame's
    retained-zero convention — a LABEL fill, never a feature fillna); duplicate-grain and
    conservation refusals, both loud. `extra_feed` carries the SOURCE columns; the label is their
    row SUM (fumbles/2-pt are split by phase upstream and a league scores the total)."""
    keys = ["season", "week", "gsis_id"]
    s = extra_feed.rename(columns={"player_id": "gsis_id"}).copy()
    for c in ("season", "week"):
        s[c] = s[c].astype("int64")
    for lab, srcs in ATTACH_SOURCES.items():
        missing = [c for c in srcs if c not in s.columns]
        if missing:
            raise ValueError(f"extra feed lacks {missing} for `{lab}` — refusing")
        s[lab] = sum(pd.to_numeric(s[c], errors="coerce").fillna(0.0) for c in srcs)
    s = s[keys + list(ATTACH_STATS)]
    dup = int(s.duplicated(keys).sum())
    if dup:
        raise ValueError(f"extra feed carries {dup} duplicate (season, week, gsis_id) keys — "
                         f"refusing to attach labels on an unresolved grain")
    for c in ATTACH_STATS:
        if c in feat.columns:
            raise ValueError(f"matrix already carries `{c}` — refusing a second attach")
    merged = feat.merge(s, on=keys, how="left")
    if len(merged) != len(feat):
        raise ValueError(f"label attach changed the row count {len(feat)} → {len(merged)} — "
                         f"refusing (NF-W3 conservation)")
    feed_in_frame = s.merge(feat[keys].drop_duplicates(), on=keys, how="inner")
    audit: dict = {"n_rows": int(len(merged)), "feed_dup_keys": dup}
    for c in ATTACH_STATS:
        matrix_sum = float(pd.to_numeric(merged[c], errors="coerce").sum())
        feed_sum = float(pd.to_numeric(feed_in_frame[c], errors="coerce").sum())
        if abs(matrix_sum - feed_sum) > 1e-6:
            raise ValueError(f"conservation FAILED for `{c}`: matrix {matrix_sum} vs feed "
                             f"{feed_sum} — the attach corrupted the label")
        audit[f"{c}_total"] = matrix_sum
        audit[f"{c}_filled_zero_rows"] = int(merged[c].isna().sum())
        merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0.0)
    return merged, audit


def assert_all_stat_labels_present(feat: pd.DataFrame) -> None:
    missing = [c for c in ALL_STATS if c not in feat.columns]
    if missing:
        raise ValueError(f"matrix is missing per-stat label columns {missing}")


def _y(df: pd.DataFrame, stat: str) -> np.ndarray:
    return pd.to_numeric(df[stat], errors="coerce").fillna(0.0).to_numpy(dtype=float)


# ── Permutation substrate (fresh seed) ──────────────────────────────────────────────────────────
def permute_stat_within_pos_week(train: pd.DataFrame, stat: str) -> np.ndarray:
    """Labels permuted WITHIN (position, global week) — the SD/SDC substrate shape, seeded from
    THIS story's fresh seed (a fresh registration re-seeds its permutation)."""
    rng = np.random.default_rng(np.random.SeedSequence([_SEED, zlib.crc32(stat.encode())]))
    y = _y(train, stat).copy()
    keys = train["position"].astype(str) + "|" + train["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(train)), index=keys.to_numpy()).groupby(level=0):
        posn = idx.to_numpy()
        if len(posn) > 1:
            y[posn] = y[rng.permutation(posn)]
    return y


# ── The conditional forms' oracle/matched pairs at (K−1)/K sizing (W6b-C refinement) ────────────
def matched_cand_quantile(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                          stat: str) -> np.ndarray:
    """`EM.matched_cand_quantile` re-sized to the peek's effective n (`SDC.matched_window`)."""
    window = matched_window(train, test)
    knots = EM.fit_cand_knots(window, test, features, stat)
    w_knots = EM.fit_cand_knots(window, window, features, stat)
    tails = EM.tail_betas_by_pos(w_knots, _y(window, stat), window["position"].to_numpy())
    return EM.knots_to_eval(knots, tails, test["position"].to_numpy())


def matched_head_bank(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                      stat: str) -> np.ndarray:
    """`EM.matched_head_bank` re-sized to the peek's effective n."""
    window = matched_window(train, test)
    mean_w = EM.fit_head_mean(window, window, features, stat)
    bank = EM.residual_bank199(_y(window, stat) - mean_w, window["position"].to_numpy())
    mean_te = EM.fit_head_mean(window, test, features, stat)
    return EM.apply_bank199(mean_te, test["position"].to_numpy(), bank)


def _assert_cond_rows(n_nonzero: int, where: str, stat: str) -> None:
    if n_nonzero < MIN_COND_ROWS:
        raise InapplicableForm(
            f"hurdle form inapplicable for `{stat}` ({where}): {n_nonzero} non-zero rows < "
            f"MIN_COND_ROWS={MIN_COND_ROWS} — refusing to fit a conditional bank on a "
            f"near-empty side (recorded as INAPPLICABLE, never scored on a constant)")


def oracle_hurdle(test: pd.DataFrame, features: list[str], stat: str, fold_label: str) -> np.ndarray:
    """`SDC.oracle_hurdle` with the non-zero-row floor asserted per cross-fit part."""
    ids = EM.crossfit_ids(len(test), CROSSFIT_K, fold_label, stat + "|hurdle")
    y = _y(test, stat)
    for j in range(CROSSFIT_K):
        _assert_cond_rows(int((y[ids != j] != 0.0).sum()), f"cross-fit part {j}", stat)
    return SDC.oracle_hurdle(test, features, stat, fold_label)


def matched_hurdle(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                   stat: str) -> np.ndarray:
    window = matched_window(train, test)
    _assert_cond_rows(int((_y(window, stat) != 0.0).sum()), "matched window", stat)
    return SDC.matched_hurdle(train, test, features, stat)


#: form → (oracle fn(test, features, stat, fold_label), matched fn(train, test, features, stat))
def oracle_fn(form: str):
    return {
        "marginal": lambda test, feats, stat, lbl: EM.oracle_climatology(test, stat),
        "head_bank": EM.oracle_head_bank,
        "cand_quantile": lambda test, feats, stat, lbl: EM.oracle_cand_quantile(
            test, feats, stat, lbl)[0],
        "knn": oracle_knn,
        "hurdle": oracle_hurdle,
        "negbin": oracle_negbin,
    }[form]


def matched_fn(form: str):
    return {
        "marginal": lambda train, test, feats, stat: EM.matched_climatology(train, test, stat),
        "head_bank": matched_head_bank,
        "cand_quantile": matched_cand_quantile,
        "knn": matched_knn,
        "hurdle": matched_hurdle,
        "negbin": matched_negbin,
    }[form]


def arm_fn(arm: str):
    """The real arms — POINTERS at the pinned code paths (identity-guarded)."""
    return {
        "lgbm_quantile_tail": lambda tr, te, f, s: arm_lgbm_quantile_tail(tr, te, f, s)[0],
        "lgbm_hurdle_tail": lambda tr, te, f, s: arm_lgbm_hurdle_tail(tr, te, f, s)[0],
        "knn_quantile": arm_knn_quantile,
        "count_negbin": lambda tr, te, f, s: arm_count_negbin(tr, te, f, s)[0],
    }[arm]


# ── Reproduction control (NF-W2d) ───────────────────────────────────────────────────────────────
def reproduction_reference(w6b_json: Path, w6bc_json: Path,
                           served_from_w6b: dict[str, str],
                           served_from_w6bc: dict[str, str]) -> dict[str, dict]:
    """{cell: {"winner", "record", "fold_crps": {fold_label: crps}}} for the served cells, each
    read from ITS OWN certifying record (W6b for six, W6b-C for RB|rushing_tds — W6b also scored
    that cell, as a null, so the record is chosen by the SERVING module's own attribution, never
    by "which record mentions the cell"). The figures the re-run must reproduce EXACTLY."""
    w6b = json.loads(Path(w6b_json).read_text())
    w6bc = json.loads(Path(w6bc_json).read_text())
    out: dict[str, dict] = {}
    for cell, winner in served_from_w6b.items():
        rec_winner = w6b["selections"][cell]["winner"]
        if rec_winner != winner:
            raise ValueError(f"{cell}: served form {winner} ≠ the W6b record's winner {rec_winner}")
        out[cell] = {"winner": winner, "record": "NF-W6b",
                     "fold_crps": {fr["label"]: float(fr["cells"][cell]["scores"][winner]
                                                       [PRIMARY_METRIC])
                                   for fr in w6b["fold_results"]}}
    for cell, winner in served_from_w6bc.items():
        if w6bc["selection"]["cell"] != cell:
            raise ValueError(f"{cell}: not the W6b-C record's cell ({w6bc['selection']['cell']})")
        rec_winner = w6bc["selection"]["winner"]
        if rec_winner != winner:
            raise ValueError(f"{cell}: served form {winner} ≠ the W6b-C record's winner "
                             f"{rec_winner}")
        out[cell] = {"winner": winner, "record": "NF-W6b-C",
                     "fold_crps": {fr["label"]: float(fr["cells"][cell]["scores"][winner]
                                                       [PRIMARY_METRIC])
                                   for fr in w6bc["fold_results"]}}
    return out


def check_reproduction(reference: dict[str, dict], fold_label: str,
                       observed: dict[str, float]) -> dict:
    """EXACT (byte-identical) comparison per cell for one fold. Returns the audit; the caller
    decides (the runner marks the RUN INVALID on any mismatch — the story's rule)."""
    rows = {}
    ok = True
    for cell, ref in reference.items():
        if fold_label not in ref["fold_crps"]:
            raise ValueError(f"{cell}: fold {fold_label} not in the {ref['record']} record — the "
                             f"reproduction control cannot run on an unrecorded fold")
        want, got = ref["fold_crps"][fold_label], float(observed[cell])
        same = bool(want == got)
        ok &= same
        rows[cell] = {"record": ref["record"], "recorded": want, "observed": got,
                      "byte_identical": same, "abs_diff": abs(want - got)}
    return {"fold": fold_label, "all_reproduce": bool(ok), "cells": rows}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PHASE A — the ceiling gate (selection + decision, from stored fold scores)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fdr_two_families(count_p: dict, event_p: dict) -> dict:
    own = {**M14.bh_fdr(count_p, q=FDR_Q), **M14.bh_fdr(event_p, q=FDR_Q)}
    pooled_in = {f"count::{k}": v for k, v in count_p.items()}
    pooled_in.update({f"event::{k}": v for k, v in event_p.items()})
    pooled = {k.split("::", 1)[1]: v for k, v in M14.bh_fdr(pooled_in, q=FDR_Q).items()}
    binding = {k: bool(own.get(k) and pooled.get(k)) for k in own}
    return {"own_family": own, "pooled": pooled, "binding": binding}


def fdr_two_families(count_p: dict[str, float | None], event_p: dict[str, float | None]) -> dict:
    """MH2 (a): two declared families (COUNT cells / EVENT cells) corrected within themselves AND
    pooled; the STRICTER binds, so no verdict turns on the family choice."""
    return _fdr_two_families(count_p, event_p)


def crps_matrix_nullable(fold_results: list[dict], cell: str) -> pd.DataFrame:
    """Like `EM.cell_crps_matrix` but tolerant of a None score (an INAPPLICABLE form)."""
    return pd.DataFrame({
        fr["label"]: {lab: (np.nan if fr["cells"][cell]["scores"][lab] is None
                            else fr["cells"][cell]["scores"][lab][PRIMARY_METRIC])
                      for lab in fr["cells"][cell]["scores"]}
        for fr in fold_results}).T


def select_ceiling(fold_results: list[dict], cell: str, n_folds: int) -> dict:
    """The per-cell ceiling: max over the class's per-form block peeks vs the BINDING incumbent,
    each form floored at matched-n. A form INAPPLICABLE on any fold is excluded (and named)."""
    cls = stat_class(cell.split("|", 1)[1])
    crps = crps_matrix_nullable(fold_results, cell)
    mean_crps = crps.mean(axis=0, skipna=False)
    foils = list(FOILS[cls])
    binding_inc = str(mean_crps[foils].idxmin())
    inc = crps[binding_inc].to_numpy(dtype=float)
    clause = cv_power.fold_consistency_clause(n_folds)

    per_form: dict[str, dict] = {}
    inapplicable: dict[str, str] = {}
    for f in CEILING_FORMS[cls]:
        orc, mat = ORACLE_PAIRS[f]
        if crps[orc].isna().any() or crps[mat].isna().any():
            inapplicable[f] = (f"{int(crps[orc].isna().sum())} oracle / "
                               f"{int(crps[mat].isna().sum())} matched folds inapplicable")
            continue
        d = inc - crps[orc].to_numpy(dtype=float)
        m, lo, hi = paired_ci95(d)
        per_form[f] = {
            "mean_delta": None if m is None else round(m, 5),
            "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
            "fold_wins": int((d > 0).sum()),
            "oracle_mean": round(float(mean_crps[orc]), 5),
            "matched_n_mean": round(float(mean_crps[mat]), 5),
            "oracle_beats_matched_n": bool(mean_crps[orc] < mean_crps[mat]),
        }
    if not per_form:
        raise ValueError(f"{cell}: every declared form is inapplicable — the ceiling is "
                         f"unevaluable (refusing; NF1.7 (a))")
    best_form = max(per_form, key=lambda f: (per_form[f]["mean_delta"]
                                             if per_form[f]["mean_delta"] is not None
                                             else -np.inf))
    deltas = inc - crps[ORACLE_PAIRS[best_form][0]].to_numpy(dtype=float)
    mean_d, lo, hi = paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    pval = M14.onesided_paired_pvalue(deltas)
    mean_inc = float(np.mean(inc))
    pct = (100.0 * mean_d / mean_inc) if (mean_d is not None and mean_inc > 0) else None

    fold_labels = [fr["label"] for fr in fold_results]
    cap = [i for i, lbl in enumerate(fold_labels) if lbl in CAPTURE_ERA_FOLDS]
    leg = [i for i, lbl in enumerate(fold_labels) if lbl not in CAPTURE_ERA_FOLDS]
    inc_sc = [fr["cells"][cell]["scores"][binding_inc] for fr in fold_results]
    n_tot = sum(s["n"] for s in inc_sc)
    cov = (sum(s["coverage_80"] * s["n"] for s in inc_sc) / n_tot) if n_tot else float("nan")
    return {
        "cell": cell, "stat_class": cls, "n_rows": int(n_tot),
        "selection_metric": PRIMARY_METRIC,
        "mean_crps": {k: (None if pd.isna(v) else round(float(v), 5))
                      for k, v in mean_crps.items()},
        "binding_incumbent": binding_inc, "mean_incumbent": round(mean_inc, 5),
        "per_form": per_form, "inapplicable_forms": inapplicable, "best_form": best_form,
        # NF1.9 (f): the best form's peek is INFORMATIVE only if it beats its own matched control
        "best_form_oracle_beats_matched_n": bool(per_form[best_form]["oracle_beats_matched_n"]),
        "deltas_by_fold": [round(float(d), 5) for d in deltas], "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "p_one_sided": pval,
        "ceiling_pct": None if pct is None else round(pct, 3),
        "anchors": {
            "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[binding_inc]),
            "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[binding_inc]),
            "max_width_loses": bool(mean_crps["max_width"] > mean_crps[binding_inc]),
        },
        "incumbent_calibration": {
            "coverage_80": round(float(cov), 4),
            "pred_p0_mean": round(float(np.mean([s["pred_p0"] for s in inc_sc])), 4),
            "real_p0": round(float(np.mean([s["real_p0"] for s in inc_sc])), 4),
        },
        "era_note": {
            "capture_folds": [fold_labels[i] for i in cap],
            "capture_mean_delta": (round(float(np.mean(deltas[cap])), 5) if cap else None),
            "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 5) if leg else None),
        },
        "pbo": None,
        "pbo_state": ("UNDEFINED — a pre-registered anchor contrast, not a searched field "
                      "(the NF-W5/W6 ceiling rule)."),
        "fdr_binding": None,
    }


def decide_ceiling(sel: dict) -> dict:
    """NO / MARGINAL / YES by the W6 bands + stat_ok, then the LICENSING rule (YES or MARGINAL
    licenses Phase B — declared, see LICENSE_BANDS). Fails closed."""
    d = EM.decide_cell(sel)
    d["licensed_for_bakeoff"] = bool(d["answer"] in LICENSE_BANDS and d["stat_ok"])
    d["license_rule"] = (f"licensed iff answer ∈ {list(LICENSE_BANDS)} ∧ stat_ok — MARGINAL "
                         f"licenses because the block peek under-reads atom-aware full-train "
                         f"capacity (NF-W6b-C: 4.08% at the gate → 12.97% in the bake-off)")
    return d


def decide_ceiling_story(decisions: dict[str, dict]) -> dict:
    lic = sorted(c for c, d in decisions.items() if d["licensed_for_bakeoff"])
    yes = sorted(c for c, d in decisions.items() if d["answer"] == "YES")
    marg = sorted(c for c, d in decisions.items() if d["answer"] == "MARGINAL")
    no = sorted(c for c, d in decisions.items() if d["answer"] == "NO")
    return {"licensed_cells": lic, "yes_cells": yes, "marginal_cells": marg, "no_cells": no,
            "headline": (f"CEILING-GATE yes={len(yes)} marginal={len(marg)} no={len(no)} of "
                         f"{len(decisions)} cells → {len(lic)} licensed for the bake-off; "
                         f"{len(no)} point-only (Phase-C default)")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PHASE B — the bake-off (selection + gates + null reading, from stored fold scores)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pooled(fold_results: list[dict], cell: str, label: str, key: str) -> tuple[float, int]:
    parts = [fr["cells"][cell]["scores"][label] for fr in fold_results]
    n = sum(s["n"] for s in parts)
    v = (sum(s[key] * s["n"] for s in parts) / n) if n else float("nan")
    return float(v), int(n)


def dsr_mechanism(observed_sr: float | None, trial_srs: list[float],
                  arms: tuple[str, ...]) -> dict:
    """⭐ READ THE MECHANISM before filing a DSR failure (NF-W6b-C): the field's SR0 (√V·z(N)),
    whether the winner's own per-fold Sharpe even reaches it (if not, no fold count clears —
    DSR-UNREACHABLE in THIS field), and which trial arm carries the dispersion."""
    srs = np.asarray(trial_srs, dtype=float)
    sr0 = SDC.benchmark_sr0(srs)
    worst = int(np.argmin(srs)) if len(srs) else None
    return {
        "sr0_this_field": sr0,
        "observed_sr": observed_sr,
        "unreachable_in_field": bool(sr0 is not None and observed_sr is not None
                                     and observed_sr <= sr0),
        "most_dispersing_arm": (arms[worst] if worst is not None else None),
        "most_dispersing_arm_sr": (round(float(srs[worst]), 3) if worst is not None else None),
        "reading": ("if `unreachable_in_field`, the DSR null is a FIELD-DISPERSION mechanism, "
                    "not a sample-size one — more folds scale a positive gap but cannot create "
                    "one; the admissible remedy is a fresh coherent registration, never a post-hoc "
                    "trim (MH2.2)."),
    }


def select_bakeoff_cell(fold_results: list[dict], cell: str, n_folds: int,
                        deflate_fn) -> dict:
    """The per-cell selection — the W6b-C shape, parametrized by class. `deflate_fn` is the
    CSCV/PBO instrument (`NF18.deflate`), injected so this pure module imports no runner."""
    cls = stat_class(cell.split("|", 1)[1])
    arms, foils = FAMILY[cls], FOILS[cls]
    permuted = f"permuted_{PERMUTED_FORM[cls]}"
    crps = cell_crps_matrix(fold_results, cell)
    mean_crps = crps.mean(axis=0)
    winner = str(mean_crps[list(arms)].idxmin())
    binding_foil = str(mean_crps[list(foils)].idxmin())
    deltas = (crps[binding_foil] - crps[winner]).to_numpy(dtype=float)
    mean_d, lo, hi = paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)
    pval = M14.onesided_paired_pvalue(deltas)

    eligible = eligible_labels(cls)
    defl = deflate_fn(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in arms:
        d = (crps[binding_foil] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))

    perm_lift = (crps[binding_foil] - crps[permuted]).to_numpy(dtype=float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)

    winner_form = ARM_FORM[winner]
    pair_reads = {}
    for form in ("marginal", *(ARM_FORM[a] for a in arms)):
        orc, mat = ORACLE_PAIRS[form]
        pair_reads[form] = {
            "oracle_crps": round(float(mean_crps[orc]), 5),
            "matched_crps": round(float(mean_crps[mat]), 5),
            "oracle_beats_matched": bool(mean_crps[mat] > mean_crps[orc]),
        }
    own_orc = ORACLE_PAIRS[winner_form][0]
    anchors = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        "winner_beats_permuted": bool(mean_crps[permuted] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "winner_own_form_oracle_beats_matched": bool(
            pair_reads[winner_form]["oracle_beats_matched"]),
        "winner_beats_own_form_oracle": bool(mean_crps[own_orc] > mean_crps[winner]),
        "oracle_pairs": pair_reads,
    }
    cov, n_tot = _pooled(fold_results, cell, winner, "coverage_80")
    foil_cov, _ = _pooled(fold_results, cell, binding_foil, "coverage_80")
    real_p0, _ = _pooled(fold_results, cell, winner, "real_p0")
    pred_p0_w, _ = _pooled(fold_results, cell, winner, "pred_p0")
    pred_p0_f, _ = _pooled(fold_results, cell, binding_foil, "pred_p0")
    se = float(np.sqrt(COVERAGE_FLOOR * (1 - COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")
    coverage = {
        "winner_coverage_80": round(cov, 4), "binding_foil_coverage_80": round(foil_cov, 4),
        "structural_expectation": structural_coverage_note(real_p0),
        "n_rows": n_tot, "binomial_se": round(se, 4),
        "blocking_shortfall": bool(n_tot and (COVERAGE_FLOOR - cov) > COVERAGE_BLOCK_SE * se),
    }
    fold_labels = [fr["label"] for fr in fold_results]
    cap = [i for i, lbl in enumerate(fold_labels) if lbl in CAPTURE_ERA_FOLDS]
    leg = [i for i, lbl in enumerate(fold_labels) if lbl not in CAPTURE_ERA_FOLDS]
    sd_d = float(np.nanstd(deltas, ddof=1))
    observed_sr = float(np.nanmean(deltas)) / sd_d if sd_d > 1e-12 else None
    observed_sr = None if observed_sr is None else round(observed_sr, 3)
    return {
        "cell": cell, "stat_class": cls, "winner": winner, "winner_form": winner_form,
        "binding_foil": binding_foil, "selection_metric": PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "deltas_by_fold": [round(float(d), 5) for d in deltas], "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "lift_pct_of_foil": (None if mean_d is None else
                             round(100.0 * mean_d / float(mean_crps[binding_foil]), 3)),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "p_one_sided": pval,
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": observed_sr,
        "dsr_mechanism": dsr_mechanism(observed_sr, trial_srs, arms),
        "anchors": anchors, "coverage": coverage,
        "atom_calibration": {"real_p0": round(real_p0, 4), "winner_pred_p0": round(pred_p0_w, 4),
                             "binding_foil_pred_p0": round(pred_p0_f, 4),
                             "note": "REPORT-ONLY — the mechanism made visible, never a criterion."},
        "era_note": {"capture_folds": [fold_labels[i] for i in cap],
                     "capture_mean_delta": (round(float(np.mean(deltas[cap])), 5) if cap else None),
                     "legacy_mean_delta": (round(float(np.mean(deltas[leg])), 5) if leg else None)},
        "ppr_points_units": (None if mean_d is None else
                             round(float(mean_d) * abs(PPR_WEIGHTS[cell.split("|", 1)[1]]), 4)),
    }


def compose_gate(sel: dict, fdr_pass: bool) -> dict:
    """The W6b-C ten named clauses, by identity (`SDC.compose_gate_w6bc`)."""
    return compose_gate_w6bc(sel, fdr_pass)


def classify_null(sel: dict, checks: dict, n_folds: int) -> dict | None:
    """SHIP → None. Constraint/anchor-only → CONSTRAINT_REFUSED (hand; NF-D18/NF-W7). A
    STATISTICAL null → `cv_power.classify_null(declared_field_size=…)`, read through the machine
    flag `field_remedy_admissible` (MH2.7) — WITH the DSR mechanism attached, so a DSR failure
    that is field-dispersion is never mistaken for a fold shortage (NF-W6b-C)."""
    if all(checks.values()):
        return None
    cls = sel["stat_class"]
    stat_fail = [c for c in STATISTICAL_CHECKS if not checks[c]]
    other_fail = [c for c in (*CONSTRAINT_CHECKS, *ANCHOR_CHECKS) if not checks[c]]
    if not stat_fail:
        return {"state": "CONSTRAINT_REFUSED",
                "reason": (f"every statistical gate passed; the null rests on constraint/anchor "
                           f"clauses {other_fail} — more data cannot change a directional "
                           f"refusal (NF-D18/NF-W7)."),
                "retest_trigger": None, "failing_checks": other_fail,
                "classifier": "hand (the cv_power CONSTRAINT_REFUSED gap)"}
    from scipy.stats import kurtosis, skew
    d = np.asarray(sel["deltas_by_fold"], dtype=float)
    trial_srs = np.asarray(sel["trial_srs"], dtype=float)
    var_trials = float(np.var(trial_srs, ddof=1)) if len(trial_srs) >= 2 else None
    v = cv_power.classify_null(
        metric=f"{PRIMARY_METRIC}|{sel['cell']}", n_folds=int(n_folds),
        n_arms=len(FAMILY[cls]), beats_foil=bool(sel["beats_foil"]),
        observed_sr=sel["observed_sr"], var_trials_sr=var_trials, fold_wins=sel["fold_wins"],
        p_one_sided=sel["p_one_sided"], bh_cutoff=FDR_Q,
        skew=float(skew(d)) if len(d) >= 3 else 0.0,
        kurt=float(kurtosis(d, fisher=False)) if len(d) >= 3 else 3.0,
        # DSR-CONV provenance: no degenerate sits in the trial field at all (anchors never enter
        # trials — MH2.1 (a)) — structural, pre-registered FORWARD.
        degenerates_excluded_from_v=True,
        declared_field_size=DECLARED_FIELD_SIZE[cls],
    )
    out = asdict(v)
    out["failing_checks"] = stat_fail + other_fail
    out["dsr_mechanism"] = sel["dsr_mechanism"]
    if "dsr_ok" in stat_fail and sel["dsr_mechanism"]["unreachable_in_field"]:
        out["mechanism_reading"] = (
            "DSR-UNREACHABLE IN THIS FIELD (winner SR ≤ the field's SR0): a field-dispersion "
            "mechanism, NOT a fold shortage — any fold-count trigger above is misleading for "
            "this cell (NF-W6b-C).")
    out["classifier"] = ("cv_power.classify_null (declared_field_size stated — MH2.7; read "
                         "field_remedy_admissible, never the prose)")
    return out


def decide_bakeoff_story(gates: dict[str, dict]) -> dict:
    ship = sorted(c for c, g in gates.items() if g["ship"])
    null = sorted(c for c, g in gates.items() if not g["ship"])
    return {"ship_cells": ship, "null_cells": null,
            "headline": f"PERSTAT-BAKEOFF-D ship={len(ship)} null={len(null)} of {len(gates)} cells",
            "reason": f"per-cell verdicts (no story-level gate): SHIP {ship or '—'}; nulls "
                      f"{null or '—'}"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PHASE C — the calibrated default (constructions + validation + decision)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def default_climatology(train: pd.DataFrame, serve: pd.DataFrame, features: list[str],
                        stat: str) -> tuple[np.ndarray, dict]:
    """The per-position discrete empirical marginal at the dense grid (`EM.climatology_bank`,
    verbatim) — the honest atom-pricing marginal default. Uniform (bank, note) shape."""
    bank = EM.climatology_bank(_y(train, stat), train["position"].to_numpy())
    return (EM.apply_bank199(np.zeros(len(serve)), serve["position"].to_numpy(), bank),
            {"form": "climatology", "calibration_split": None})


def default_count_negbin(train: pd.DataFrame, serve: pd.DataFrame, features: list[str],
                         stat: str) -> tuple[np.ndarray, dict]:
    """`SDC.arm_count_negbin` by identity — NB2 (Poisson at the α floor) around the champion head
    mean with a purged-calibration dispersion. Prices the atom PARAMETRICALLY."""
    bank, note = arm_count_negbin(train, serve, features, stat)
    return bank, {"form": "count_negbin", **note}


DEFAULT_DISPATCH = {"count_negbin": default_count_negbin, "climatology": default_climatology}


#: The NB2 default is a COUNT likelihood — admissible only on non-negative integer count stats.
#: A yards stat can be NEGATIVE (a −3-yard reception), where a count pmf is 0 / a log-likelihood
#: −inf and the dispersion fit is meaningless — so yards cells take the climatology (declared).
YARDS_STATS: tuple[str, ...] = ("passing_yards", "rushing_yards", "receiving_yards")


def default_order_for(cell: str) -> tuple[str, ...]:
    stat = cell.split("|", 1)[1]
    if cell in minor_cells() or stat in YARDS_STATS:
        return DEFAULT_ORDER["minor"]
    return DEFAULT_ORDER["modeled"]


def pit_rng(fold_label: str, cell: str, form: str) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(
        [_SEED, zlib.crc32(fold_label.encode()), zlib.crc32(cell.encode()),
         zlib.crc32(form.encode())]))


def calibration_scores(bank: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> dict:
    """The default's per-fold calibration accounting: the bake-off reducer (CRPS/coverage/atom,
    refuses non-finite) + poolable randomized-PIT stats on the 199 grid."""
    base = score_bank(bank, y)
    u = randomized_pit_levels(bank, np.asarray(y, dtype=float), rng)
    return {**base, "pit": pit_stats(u)}


def validate_default(fold_results: list[dict], cell: str, form: str) -> dict:
    """Pool the fold accounting for one (cell, form): coverage floor (one-sided, block-SE rule)
    ∧ PIT max-decile-deviation ≤ PIT_MAX_DECILE_DEV. Both are CONSTRAINTS; the nihilist must
    lose CRPS (reported)."""
    parts = [fr["cells"][cell]["scores"][form] for fr in fold_results]
    n = sum(p["n"] for p in parts)
    cov = (sum(p["coverage_80"] * p["n"] for p in parts) / n) if n else float("nan")
    real_p0 = (sum(p["real_p0"] * p["n"] for p in parts) / n) if n else float("nan")
    pred_p0 = (sum(p["pred_p0"] * p["n"] for p in parts) / n) if n else float("nan")
    crps = float(np.mean([p[PRIMARY_METRIC] for p in parts]))
    nihil = float(np.mean([fr["cells"][cell]["scores"]["nihilist_zero"][PRIMARY_METRIC]
                           for fr in fold_results]))
    pit = pool_pit_stats([p["pit"] for p in parts])
    se = float(np.sqrt(COVERAGE_FLOOR * (1 - COVERAGE_FLOOR) / n)) if n else float("nan")
    cov_ok = bool(n and not ((COVERAGE_FLOOR - cov) > COVERAGE_BLOCK_SE * se))
    pit_ok = bool(pit.get("n", 0) and pit["max_decile_dev"] <= PIT_MAX_DECILE_DEV)
    return {"form": form, "n_rows": int(n), "crps_q199": round(crps, 5),
            "nihilist_crps": round(nihil, 5), "nihilist_loses": bool(nihil > crps),
            "coverage_80": round(float(cov), 4), "binomial_se": round(se, 4),
            "coverage_floor_ok": cov_ok,
            "structural_expectation": structural_coverage_note(real_p0),
            "real_p0": round(float(real_p0), 4), "pred_p0": round(float(pred_p0), 4),
            "pit_max_decile_dev": pit.get("max_decile_dev"), "pit_decile_freq": pit.get("decile_freq"),
            "pit_flat_ok": pit_ok, "calibrated": bool(cov_ok and pit_ok)}


def decide_default(fold_results: list[dict], cell: str) -> dict:
    """The FIRST form in the pre-registered order that is calibrated is the default. ⛔ No CRPS
    comparison decides anything (a default is not a selected model). If none is calibrated the
    LAST form is emitted with a loud `calibration_warning` — the optimizer still needs a
    distribution, and the record says plainly that it is uncalibrated on this cell."""
    order = default_order_for(cell)
    reads = {f: validate_default(fold_results, cell, f) for f in order}
    chosen = next((f for f in order if reads[f]["calibrated"]), None)
    warning = None
    if chosen is None:
        chosen = order[-1]
        warning = (f"NO default in {list(order)} is calibrated on {cell} (coverage floor / PIT "
                   f"flatness); `{chosen}` is emitted UNCALIBRATED — flagged, never silent")
    return {"cell": cell, "order": list(order), "chosen": chosen, "reads": reads,
            "calibration_warning": warning,
            "note": ("a CALIBRATED DEFAULT chosen by pre-registered ORDER + calibration gates, "
                     "NOT a bake-off winner and NOT selected on CRPS")}


def summarize_defaults(decisions: dict[str, dict]) -> dict:
    forms = {}
    for d in decisions.values():
        forms[d["chosen"]] = forms.get(d["chosen"], 0) + 1
    warned = sorted(c for c, d in decisions.items() if d["calibration_warning"])
    return {"n_cells": len(decisions), "by_form": forms, "uncalibrated_cells": warned,
            "headline": (f"DEFAULTS {len(decisions)} cells → {forms}; "
                         f"{len(warned)} uncalibrated (flagged)")}


# ── Honest framing (the shared denylist, applied at build time) ─────────────────────────────────
def screen_copy(label: str, text: str) -> str:
    """Every emitted human string goes through the shared overclaim denylist
    (`export_track_record_json._CLAIM_DENYLIST` — one list, imported)."""
    from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as TR
    return TR._screen(label, text)
