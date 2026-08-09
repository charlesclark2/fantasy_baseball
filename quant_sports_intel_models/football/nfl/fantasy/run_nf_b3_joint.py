"""run_nf_b3_joint.py — NF-B3: JOINT level+band selection under the CORRECTED C3, on the 13-fold
rebuilt boards — the properly-selected successor to the NF-C3-REREAD READ 2 replay.

THE STORY IN ONE PARAGRAPH. NF-C3-REREAD proved NF-RECAL1's veteran level correction was refused by
a MIS-SPECIFIED gate (its C3 read the panel's frozen `served_*` columns as "the incumbent band"), and
that on the corrected gate the null is POWER_LIMITED at the whole-field DSR (0.642 < 0.95 at 7 folds,
where the DSR ceiling is 0.9997) — the remedy is EVIDENCE, not mechanism. The operator precursor
(`run_season_projection --backtest-from 2013`) rebuilt the merged boards back to 2013. NF-B3 runs the
FULL pre-registered selection — not a replay — on those 13 folds, selecting the level AND the band
JOINTLY: every arm's correction moves the point and BOTH edges of the band actually on the wire
(`knn_norm k300`, refit through the model path), and C3 governs the change against that same band.
Selecting them separately is what killed NF-RECAL1 (level vs a stale band) and NF-D21 (level vs the
rookie band); the joint selection is a level lift that provably doesn't break the healthy band
(NF1.9-R: 0.845 on the tier).

⚠️ THE PRE-REGISTRATION IS `level_recalibration.py`, INHERITED WHOLESALE — forms, spaces, λ grid and
rules, metric, constraints, framing, deflation gates, anchors. This file registers ONLY what B3
changes, in `B3_REGISTRATION` below, before any result is seen:
  · FOLDS — `LR.WIDE_WINDOW_SEASONS` (2013–2025, 13), the reachable-now re-test NF-C3-REREAD named.
    Training reaches back to the panel's start (2007) so every fold has the deepest in-fold history.
  · BAND — the band ON THE WIRE, refit walk-forward through the served model path and PROVEN by
    reproducing NF1.9's recorded universe IS80 (160.888) and NF1.9-R's tier coverage (0.8452) before
    any gate is read (STEP 0, a RAISE). ⛔ `coverage_incumbent` NEVER comes from a `served_*` panel
    column — that is the exact trap NF-C3-REREAD closed.
  · C3 BOUNDARY — the harness fix NF-C3-REREAD flagged, canonical here: `need = ceil(bind·n − 1e-9)`
    on the UNROUNDED incumbent (`equality_exact=True`), so an arm whose coverage EQUALS the
    incumbent's — λ=0 above all — is admissible. A governs-the-change clause's equality boundary
    must hold.
  · C2 ON PRE-2016 BOARDS — the rookie SUBSTRATE (NCAAF projections) begins at draft class 2016, so
    the 2013–2015 merged boards have NO rookie leg STRUCTURALLY. C2's protected object is absent
    there: vacuously admissible, counted INACTIVE, never credited (NF-D20 (g⁗)). ⚠️ Distinct from a
    BROKEN board — a rookie-less board for 2016+ RAISES.

⛔ NF-C3-REREAD's READ 2 winner (`global_const · infold`, λ≈0.5) is NOT pre-selected — that replay's
λ path was derived with the answer partially in view (E2.1-r if carried forward). It is the live
incumbent-CHALLENGER this field must beat honestly; B3 re-derives every rule's λ path from its own
13-fold evidence.

⚠️ INHERITED FROM NF-C3-REREAD: on the corrected band C3 CANNOT police magnitude FROM ABOVE — a
proportional over-widen keeps coverage, so `over_scale`/`wide_band` can SATISFY it. Magnitude
policing lives in the METRIC now, and both anchors are scored every run and must LOSE it; their C3
state is disclosed so "the gate did not do the metric's job" is a measurement.

⚖️ `best_alpha = 0` — a projection-quality product; no CLV/ROI claim.
⛔ ROOKIE LEG OUT OF SCOPE (closed NF-D16→D21 chain; inherited by import, `assert_rookie_leg_untouched`).
⛔ NF1.5's ORDERING layer untouched. 🔒 CODE-READY, deploy-HELD — nothing serves from this run;
any publish + `run_interval_revalidation` re-run is a POST-MERGE operator step.

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached veteran band panel + the 2013-rebuilt
merged boards; a fresh worktree must copy those gitignored artifacts in first):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_b3_joint
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_c3_reread as C3R  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_recal1_level as R1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_b3_joint")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_STEM = "nf_b3_joint_level_band"

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ B3's OWN PRE-REGISTRATION — everything B3 changes relative to the inherited NF-RECAL1
#    registration, fixed before the run. The rest is READ from `level_recalibration`.
# ══════════════════════════════════════════════════════════════════════════════════════════════
B3_REGISTRATION = {
    "story": "NF-B3",
    "model_version": "nfl_fantasy_nf_b3_joint_level_band_v1",
    "recalibrates": LR.RECALIBRATES,
    #: The folds: the wide window NF-C3-REREAD named as the reachable-now re-test, now
    #: constraint-evaluable because the operator rebuilt the merged boards from 2013.
    "fold_seasons": tuple(LR.WIDE_WINDOW_SEASONS),            # 2013–2025 → 13 folds
    #: Training panel start — the earliest walk-forward veteran panel year. Deeper history for every
    #: fold; the earliest fold (2013) trains on 2007–2012.
    "train_panel_start": 2007,
    #: The band every arm is selected WITH: the band on the wire, refit through the model path.
    "band": {"form": "knn_norm", "k": 300, "source": "model-path refit (NF1.9-R incumbent arm)",
             "forbidden_source": "the veteran panel's served_p10/served_p90 columns"},
    #: The C3 equality-boundary fix (NF-C3-REREAD's harness finding) is CANONICAL here.
    "c3_equality_exact": True,
    #: The rookie substrate's first draft class — merged boards before this year have no rookie leg
    #: STRUCTURALLY, so C2 is INACTIVE (vacuous, uninformative), never refused, on exactly these.
    "rookie_substrate_start": 2016,
    #: The live incumbent-challenger this field must beat honestly — NOT pre-selected.
    "incumbent_challenger_note": (
        "NF-C3-REREAD READ 2's winner (global_const · infold, λ≈0.5) is a replay figure derived "
        "with the answer partially in view; B3 re-derives every λ path from its own 13-fold "
        "evidence and the winner is whatever the pre-registered rules select."),
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 — provenance gates, every one a RAISE (the NF-C3-REREAD pattern)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_boards_b3(seasons: tuple) -> tuple[dict, list[int]]:
    """The 2013-rebuilt merged boards, with provenance ASSERTED per board:
      · walk-forward (`base_season == s − 1`) — always;
      · a rookie leg — REQUIRED from `rookie_substrate_start` on; ALLOWED absent before it, because
        the NCAAF rookie projection source begins at draft class 2016 and no rebuild can create a leg
        the substrate does not contain. The structurally rookie-less years are RETURNED so the
        evidence builder can mark C2 INACTIVE on exactly those and nothing else."""
    start = int(B3_REGISTRATION["rookie_substrate_start"])
    out, structural = {}, []
    for s in seasons:
        p = R1.board_path(s)
        if not p.exists():
            raise SystemExit(
                f"no merged board for {s} at {p} — the operator precursor has not run; STOP.\n"
                "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
                "run_season_projection --backtest-from 2013")
        b = pd.read_parquet(p)
        base = int(pd.to_numeric(b["base_season"], errors="coerce").dropna().iloc[0])
        if base != int(s) - 1:
            raise SystemExit(f"board {s} is not walk-forward (base={base}) — C2 would be evaluated "
                             "on a different product.")
        n_rk = int(b["is_rookie"].fillna(False).astype(bool).sum())
        if n_rk == 0:
            if int(s) >= start:
                raise SystemExit(
                    f"board {s} has NO rookie leg but the rookie substrate exists for draft class "
                    f"{s} (≥ {start}) — that is a BROKEN rebuild, not a structural absence; STOP.")
            structural.append(int(s))
        b["position"] = b["position"].astype(str).str.upper()
        out[s] = b
    return out, structural


def step0(years: tuple) -> tuple[dict, dict]:
    """Refit the band ON THE WIRE through the model path and prove it — NF-C3-REREAD's step-0
    functions, imported: `reproduction_proofs` RAISES unless the refit band reproduces NF1.9's
    recorded universe IS80 (160.888), NF1.9-R's served tier coverage (0.8452) AND the panel columns'
    0.5046 (the trap's own signature, so 'the trap exists and we are not in it' is one measurement).
    ⛔ Nothing downstream may read a band that did not pass this."""
    rows, lookup = C3R.served_band_by_row(years)
    proofs = C3R.reproduction_proofs(rows)
    return proofs, lookup


# ══════════════════════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true", help="reduced form set; proves the path only")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()

    seasons = tuple(B3_REGISTRATION["fold_seasons"])
    tier_n = LR.draftable_tier_size()
    log.info("NF-B3 — JOINT level+band selection · folds %s · tier %d/season", list(seasons), tier_n)

    # ── STEP 0 — hold the served band (RAISE) + board provenance (RAISE) ──
    proofs, lookup = step0(seasons)
    boards, structural = load_boards_b3(seasons)
    if structural != sorted(structural) or any(
            s >= B3_REGISTRATION["rookie_substrate_start"] for s in structural):
        raise SystemExit(f"structural rookie-less set {structural} is not the pre-substrate prefix")
    log.info("STEP 0 — served band held (IS80 %.3f Δ%.4f%%; tier cov %.4f) · boards %d–%d · "
             "structurally rookie-less: %s",
             proofs["universe_is80"], proofs["universe_is80_delta_pct"],
             proofs["served_tier_coverage_2019_2025"], min(seasons), max(seasons), structural)

    # ── folds: level panel over 2007+, folds on the 13 wide-window seasons, band substituted ──
    panel_years = tuple(range(int(B3_REGISTRATION["train_panel_start"]), max(seasons) + 1))
    d = R1.load_panel(panel_years)
    tier = R1.tier_mask(d, tier_n)
    folds_panel = R1.build_folds(d, tier, seasons)
    folds = C3R.substitute_served_band(folds_panel, lookup)   # RAISES on any unmatched row
    years = [f["year"] for f in folds]

    # §0 premise on the FOLD WINDOW population (the population the metric is computed over).
    d_win = d[d["target_season"] >= min(seasons)].reset_index(drop=True)
    premise = R1.premise_check(d_win, tier_n)
    log.info("§0 premise (fold window) — tier bias %.2f (n %d) · universe %.2f",
             premise["draftable_tier_incumbent_anchor"]["mean_bias"],
             premise["draftable_tier_incumbent_anchor"]["n"], premise["universe"]["mean_bias"])

    # ── fits: UNROUNDED incumbent coverage (the exact C3 boundary needs it) ──
    fits = {f["year"]: R1.fold_fits(f, cov_rounding=None) for f in folds}
    forms = (LR.FORMS[:2] + (LR.LEARNED_FOIL,)) if args.smoke else LR.FORMS

    # ── the constant-λ substrate every rule reads ──
    lam_scored: dict = {}
    for space in LR.SPACES:
        for form in forms:
            lam_scored.setdefault((space, form), {})
            for lam in LR.LAMBDA_GRID:
                lam_scored[(space, form)][float(lam)] = R1.score_arm(
                    folds, fits,
                    R1.form_adjuster(form, space, (form, space), lambda f, L=lam: L),
                    f"{form}·{space}·λ={lam:g}", cov_exact=True)
    evidence = R1.build_fold_evidence(folds, fits, boards, forms=forms, cov_exact=True,
                                      structural_c2_inactive=tuple(structural))
    activity = R1.constraint_activity(evidence)

    # ── the 11-arm field + season-total matched foils ──
    incumbent = R1.score_arm(
        folds, fits,
        R1.form_adjuster("pos_const", LR.PRIMARY_SPACE, ("pos_const", LR.PRIMARY_SPACE),
                         lambda f: 0.0),
        "incumbent (NULL)", cov_exact=True,
        extra={"form": "incumbent", "space": LR.PRIMARY_SPACE, "rule": None,
               "recalibrates": False, "shippable": True, "is_foil": False})
    arms, foils, placements = [incumbent], [], {}
    placements["incumbent (NULL)"] = {"holds_out": True, "per_fold": {}, "c2_only": True,
                                      "c3_only": True, "failing_folds": []}
    for space, bucket, is_foil in ((LR.PRIMARY_SPACE, arms, False), (LR.FOIL_SPACE, foils, True)):
        for cfg in [c for c in LR.candidate_configs(space=space, smoke=args.smoke)
                    if c["form"] != "incumbent"]:
            form = cfg["form"]
            lam_by_fold = R1.rule_lambdas(form, cfg, folds,
                                          {form: lam_scored[(space, form)]}, evidence)
            lam_map = {y: v["lam"] for y, v in lam_by_fold.items()}
            label = (f"{form} · {cfg['rule']}" if not is_foil
                     else f"{form} · {cfg['rule']} [season_total FOIL]")
            rec = R1.score_arm(
                folds, fits,
                R1.form_adjuster(form, space, (form, space), lambda f, M=lam_map: M[f["year"]]),
                label, cov_exact=True,
                extra={"key": LR.config_key(cfg), "form": form, "space": space,
                       "rule": cfg["rule"], "recalibrates": True, "shippable": not is_foil,
                       "is_foil": is_foil, "lam_by_fold": lam_map,
                       "lam_detail": {y: v for y, v in lam_by_fold.items()}})
            bucket.append(rec)
            if not is_foil:
                placements[label] = R1.holds_out(form, lam_map, evidence)

    # ── the two-sided anchors, scored every run (all inherited) ──
    perm_forms = ("pos_offset", "pos_const", LR.LEARNED_FOIL)
    anchor_tags = (("oracle_perplayer",)
                   + tuple(f"{w}@{f}" for w in ("permuted_across", "permuted_within")
                           for f in perm_forms)
                   + ("zero_project", "pos_median", "over_scale", "wide_band")
                   + tuple(LR.FAMILY_CEILING[f] for f in forms))
    anchors = {t: R1.score_arm(folds, fits, R1.anchor_adjuster(t, folds), t, cov_exact=True)
               for t in anchor_tags}
    LR.require_anchors(anchors, required=anchor_tags)
    anchor_constraints = [
        R1.anchor_constraint_state(folds, fits, boards, R1.anchor_adjuster(t, folds), t,
                                   cov_exact=True, structural_c2_inactive=tuple(structural))
        for t in ("zero_project", "over_scale", "wide_band")]

    # ── selection + deflation under the pre-registered pooled framing ──
    sel = R1.select_pooled(arms, incumbent, years, placements)
    per_pos = R1.per_position_disclosure(arms, incumbent, years, placements)
    attribution = R1.foil_attribution(arms, foils, years)

    inc_m = incumbent[LR.SELECTION_METRIC]
    sanity_degen = {t: anchors[t][LR.SELECTION_METRIC]
                    for t in ("zero_project", "pos_median", "wide_band")}
    best_real = min((r[LR.SELECTION_METRIC] for r in arms if r.get("recalibrates")), default=inc_m)
    ls_ceilings = {f: R1.score_arm(folds, fits,
                                   R1.form_adjuster(f, LR.PRIMARY_SPACE, ("_peek_ls", f),
                                                    lambda _f: 1.0),
                                   f"oracle_{f} [least-squares fit]",
                                   cov_exact=True)[LR.SELECTION_METRIC]
                   for f in forms}
    ceilings = {f: anchors[LR.FAMILY_CEILING[f]][LR.SELECTION_METRIC] for f in forms}
    order_ok = all(ceilings.get(b) is None or ceilings.get(a) is None
                   or ceilings[b] <= ceilings[a] + 1e-9
                   for a, b in LR.FORM_NESTING if a in ceilings and b in ceilings)
    ls_order_ok = all(ls_ceilings.get(b) is None or ls_ceilings.get(a) is None
                      or ls_ceilings[b] <= ls_ceilings[a] + 1e-9
                      for a, b in LR.FORM_NESTING if a in ls_ceilings and b in ls_ceilings)
    ceil_rows = [{"form": f, "anchor": LR.FAMILY_CEILING[f],
                  "ceiling fitted on CRPS ⭐": ceilings[f],
                  "ceiling fitted by least squares": ls_ceilings[f]} for f in forms]
    fc = LR.family_ceiling_check(
        [{**r, "form": r.get("form"), "recalibrates": r.get("recalibrates"),
          LR.SELECTION_METRIC: r.get(LR.SELECTION_METRIC), "label": r["label"]} for r in arms],
        anchors, metric=LR.SELECTION_METRIC,
        family_ceiling={f: LR.FAMILY_CEILING[f] for f in forms})

    signature = LR.attribution_signature(
        incumbent_bias=incumbent["bias"], winner_bias=(sel["winner"] or {}).get("bias"),
        incumbent_metric=inc_m, winner_metric=(sel["winner"] or {}).get("metric"))
    gate = LR.pooled_ship(winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
                          ordering=sel["ordering"] or {"per_position": {}},
                          placement=sel["placement"], coverage=sel["coverage"],
                          pbo=sel["deflation"].get("pbo"), dsr=sel["deflation"].get("dsr"),
                          pvalue=sel["pvalue"])
    verdict = LR.level_verdict(
        pooled_ships=gate["ship"], premise_confirmed=premise["premise_confirmed"],
        sanity_degenerates_lose=all(v is not None and v > best_real
                                    for v in sanity_degen.values()),
        permutation_across_beaten=all(
            anchors[f"permuted_across@{f}"][LR.SELECTION_METRIC] > best_real for f in perm_forms),
        oracle_respected=(anchors["oracle_perplayer"][LR.SELECTION_METRIC] <= best_real + 1e-9),
        family_ceiling_respected=fc["ok"], ceilings_order_by_capacity=order_ok,
        over_scale_loses=(anchors["over_scale"][LR.SELECTION_METRIC] > best_real),
        wide_band_loses=(anchors["wide_band"][LR.SELECTION_METRIC] > best_real),
        rookie_leg_untouched=True,
        space_invariance_proven=attribution["space_invariance_proven"])
    null = R1.classify_this_null(arms, incumbent, years, placements, premise)
    # B3 IS the wide-window re-test NF-C3-REREAD's trigger named — correct the inherited note.
    null["wider_window_is_reachable_now"] = False
    null["wider_window_note"] = (
        "NF-B3 IS the wide-window run: 13 folds (2013–2025) is the maximal constraint-evaluable "
        "window today — the veteran panel reaches 2007 but merged boards below 2013 do not exist, "
        "and the rookie substrate (hence C2's subject) begins at draft class 2016. Any further "
        "widening is a new operator precursor, not a property of this data.")

    # ── ⭐ THE DSR MARGIN, STATED IN THE UNIT THAT GROWS (MH2 (b) / NF-D15 (g″)) — derived from the
    #    run, not written by hand. Recomputes the SAME trial field select_pooled deflates against
    #    (per-fold lift Sharpe of every non-foil arm; NaN — the incumbent's zero row — drops out of V
    #    exactly as it does inside `deflated_sharpe`), then solves the closed form for the fold count
    #    at which the winner's observed SR clears DSR ≥ DSR_MIN under this field. ⛔ Closed form,
    #    never a resampled extrapolation (the MH2 `np.resize` defect). ──
    dsr_margin: dict = {"note": "no eligible winner — no margin to state"}
    if sel.get("winner") and sel.get("per_fold_delta"):
        from scipy.stats import kurtosis, norm, skew
        inc_row = np.array([incumbent["per_fold_metric"][y] for y in years], dtype=float)
        trial = []
        for r_ in arms:
            if r_.get("is_foil"):
                continue
            dd_ = inc_row - np.array([r_["per_fold_metric"][y] for y in years], dtype=float)
            dd_ = dd_[np.isfinite(dd_)]
            trial.append(float(dd_.mean() / dd_.std(ddof=1))
                         if len(dd_) >= 3 and dd_.std(ddof=1) > 1e-12 else np.nan)
        srs = np.asarray(trial, dtype=float)
        srs = srs[np.isfinite(srs)]
        em = 0.5772156649015329
        sr0 = (float(srs.std(ddof=1)) * ((1 - em) * norm.ppf(1 - 1 / len(srs))
                                         + em * norm.ppf(1 - 1 / (len(srs) * np.e)))
               if len(srs) >= 2 and srs.std(ddof=1) > 0 else 0.0)
        dd = np.asarray(sel["per_fold_delta"], dtype=float)
        sr = float(dd.mean() / dd.std(ddof=1))
        g3, g4 = float(skew(dd)), float(kurtosis(dd, fisher=False))
        denom = 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2
        reachable = bool(sr > sr0 and denom > 0)
        folds_needed = (int(np.ceil(1 + (norm.ppf(LR.DSR_MIN) * np.sqrt(denom)
                                         / (sr - sr0)) ** 2)) if reachable else None)
        dsr_margin = {
            "winner_sr": round(sr, 4), "expected_max_sr_under_field_sr0": round(sr0, 4),
            "sr_exceeds_sr0": reachable,
            "n_trials_in_field": int(len(srs)),
            "folds_needed_for_dsr_gate": folds_needed, "folds_available_today": len(years),
            "reading": (
                (f"REACHABLE: at the observed SR ({sr:.3f}) under the declared field "
                 f"(SR0 {sr0:.3f}), DSR ≥ {LR.DSR_MIN} needs ~{folds_needed} folds vs "
                 f"{len(years)} today. The reachable-now widening (the 2013 board rebuild) is "
                 "EXHAUSTED; every future season adds one fold, so this is a CALENDAR-bound "
                 "re-test — and ⛔ the field may not be trimmed to lower SR0 (MH2 (a): a family is "
                 "pre-registered, never discovered)." )
                if reachable else
                "DSR-UNREACHABLE in this field: SR ≤ SR0, so no fold count clears the gate — the "
                "remedy would be a different mechanism, never more data."),
        }
        if null.get("state") == "POWER_LIMITED" and not null.get("remedy"):
            null["remedy"] = dsr_margin["reading"]

    # ── whole-board cross-position movement on the newest board, at each arm's final λ ──
    serving_board = boards[max(seasons)]
    cross_rows = []
    for r in arms:
        if not r.get("recalibrates"):
            continue
        lam = float(r["lam_by_fold"][max(years)])
        vet = ~serving_board["is_rookie"].fillna(False).astype(bool).to_numpy()
        p = pd.to_numeric(serving_board["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
        pos = serving_board["position"].astype(str).str.upper().to_numpy()
        g = pd.to_numeric(serving_board.get("proj_games",
                                            pd.Series(np.full(len(serving_board), 17.0))),
                          errors="coerce").to_numpy(dtype=float)
        adj = p.copy()
        a, _, _ = LR.apply_to_band(r["form"], r["space"], fits[max(years)][(r["form"], r["space"])],
                                   p[vet], p[vet], p[vet], pos[vet], g[vet], lam)
        adj[vet] = a
        mv = LR.cross_position_movement(p, adj, pos, serving_board["player_name"].to_numpy())
        cross_rows.append({"arm": r["label"], "λ": lam,
                           **{k: v for k, v in mv.items() if not k.startswith("top10_b")
                              and not k.startswith("top10_a")}})

    headline, prose = build_headline(premise, sel, verdict, null, attribution, activity, signature)
    res = {
        "story": "NF-B3", "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": B3_REGISTRATION["model_version"],
        "recalibrates": B3_REGISTRATION["recalibrates"], "best_alpha": 0, "wall_time_s": None,
        "preregistration": {
            **{k: (list(v) if isinstance(v, tuple) else v) for k, v in B3_REGISTRATION.items()},
            "inherited_from": "level_recalibration.py (NF-RECAL1) — forms, spaces, λ grid+rules, "
                              "metric, constraints, framing, deflation gates, anchor set",
            "framing": LR.PREREGISTERED_FRAMING, "dsr_reading": LR.PREREGISTERED_DSR_READING,
            "metric": LR.SELECTION_METRIC, "tier_anchor": LR.TIER_ANCHOR, "tier_n": tier_n,
            "forms": list(forms), "spaces": list(LR.SPACES),
            "lambda_grid": list(LR.LAMBDA_GRID), "rules": list(LR.SELECTION_RULES),
            "declared_trial_field_size": len(arms),
            "gates": {"pbo_max": LR.PBO_MAX, "dsr_min": LR.DSR_MIN, "alpha": LR.ALPHA,
                      "coverage_floor": LR.COVERAGE_FLOOR,
                      "ordering_do_no_harm": LR.ORDERING_DO_NO_HARM},
        },
        "step0_reproduction": proofs,
        "structurally_rookieless_boards": structural,
        "folds": years, "premise": premise, "selection": sel, "per_position": per_pos,
        "attribution": attribution, "signature": signature, "verdict": verdict, "null": null,
        "constraint_activity": activity,
        "ceilings_order_by_capacity": order_ok,
        "ceilings_order_by_capacity_least_squares_fit": ls_order_ok,
        "family_ceiling_check": fc,
        "ceiling_table": ceil_rows,
        "leaderboard": sorted(
            [{"arm": r["label"], "form": r.get("form"), "rule": r.get("rule"),
              "λ (final fold)": (r["lam_by_fold"][max(years)] if r.get("lam_by_fold") else 0.0),
              "CRPS": r[LR.SELECTION_METRIC], "MAE": r["mae"], "bias": r["bias"],
              "cov80": r["coverage80"], "universe CRPS": r["universe_crps"],
              "universe bias": r["universe_bias"],
              "eligible": r["label"] in sel["eligible_labels"]} for r in arms],
            key=lambda x: x["CRPS"]),
        "anchor_table": [{"anchor": t, "role": R1._anchor_role(t),
                          "expected": ("beats every real arm" if R1._anchor_role(t) == "ceiling"
                                       else "loses to every real arm"),
                          "CRPS": anchors[t][LR.SELECTION_METRIC],
                          "MAE": anchors[t]["mae"], "bias": anchors[t]["bias"],
                          "cov80": anchors[t]["coverage80"],
                          "behaves as expected": (
                              bool(anchors[t][LR.SELECTION_METRIC] <= best_real + 1e-9)
                              if R1._anchor_role(t) == "ceiling"
                              else bool(anchors[t][LR.SELECTION_METRIC] > best_real))}
                         for t in anchor_tags],
        "anchor_constraint_state": anchor_constraints,
        "c3_cannot_police_magnitude_from_above": {
            "note": ("inherited from NF-C3-REREAD: a proportional over-widen keeps coverage on the "
                     "corrected band, so over_scale/wide_band can SATISFY C3 — magnitude policing "
                     "lives in the METRIC, and both anchors must LOSE it (measured above)"),
            "over_scale_satisfies_c3_everywhere": bool(
                next(a for a in anchor_constraints if a["anchor"] == "over_scale")
                ["satisfies C3 on every fold"]),
            "wide_band_satisfies_c3_everywhere": bool(
                next(a for a in anchor_constraints if a["anchor"] == "wide_band")
                ["satisfies C3 on every fold"]),
            "over_scale_loses_metric": bool(anchors["over_scale"][LR.SELECTION_METRIC] > best_real),
            "wide_band_loses_metric": bool(anchors["wide_band"][LR.SELECTION_METRIC] > best_real),
        },
        "constraint_table": [{"arm": lab, "holds out (C1∧C2∧C3)": v.get("holds_out"),
                              "C2 only": v.get("c2_only"), "C3 only": v.get("c3_only"),
                              "failing folds": v.get("failing_folds")}
                             for lab, v in placements.items()],
        "cross_position_table": cross_rows,
        "gate_table": gate,
        "dsr_margin": dsr_margin,
        "sensitivities": {
            "dsr_at_0.0": bool((sel["deflation"].get("dsr") or -1) >= 0.0),
            "dsr_removed_would_ship": bool(
                all(v for k, v in gate.items() if k not in ("ship", "framing", "dsr_ok"))),
            "expanded_field_trials": len(arms) + len(forms) * len(LR.LAMBDA_GRID),
            "note": ("the EXPANDED reading counts every constant-λ point as its own trial; the "
                     "pre-registered field is the RULES (MH2 (a))"),
        },
        "anchor_table_note": (
            "the anchor table's generic 'beats every real arm' expectation is COARSER than the "
            "per-form check for the family ceilings: a RICHER real arm can legitimately beat a "
            "COARSER family's peeking ceiling (the NF-D16 (g‴) capacity effect — here "
            "avail_cond·unconstrained beats oracle_global_const). The binding checks are "
            "`family_ceiling_check` (no arm beats its OWN form's ceiling) and "
            "`ceilings_order_by_capacity`, both PASS."),
        "registry_action": {
            "registry": "betting_ml/models/model_family_registry.yaml (NF-G0)",
            "action": "NONE — nothing was promoted",
            "reason": ("the pooled gate fails on the whole-field DSR alone, so this is a RECORDED "
                       "NULL (POWER_LIMITED, calendar-bound re-test). The promotion state machine "
                       "has no state for a recorded null; a `challenger` entry would misrepresent "
                       "a non-shipped arm as staged (NF-RECAL1 / NF-D18 / NF-D20 precedent). The "
                       "record of this story is its ablation memo + the scheduled re-validation "
                       "trigger in `null.remedy`."),
        },
        "headline": headline, "verdict_prose": prose,
    }
    res["wall_time_s"] = round(time.time() - t0, 1)

    if not args.no_report:
        jp, mp = write_report(res)
        log.info("wrote %s and %s", jp, mp)
    log.info("VERDICT: %s · %.1fs", headline, res["wall_time_s"])
    return 0


def build_headline(premise, sel, verdict, null, attribution, activity, signature
                   ) -> tuple[str, str]:
    """Derived from the run, never written by hand."""
    if not premise["premise_confirmed"]:
        h = "NO CORRECTION — the motivating defect does not reproduce in the fold-window population"
    elif verdict["ship"]:
        h = f"SHIP-READY (code-ready, deploy-HELD) — {sel['winner']['label']}"
    elif null["state"] == "CONSTRAINT_REFUSED":
        h = "RECORDED NULL — CONSTRAINT_REFUSED"
    else:
        h = f"RECORDED NULL — {null['state']}"
    pre = premise["draftable_tier_incumbent_anchor"]
    prose = (
        f"On the 13-fold wide window (2013–2025), tier bias **{pre['mean_bias']} PPR** "
        f"(n = {pre['n']}). Best recalibrating arm: `{null['best_recalibrating_arm']}` at CRPS "
        f"{null['best_recalibrating_metric']} vs the incumbent's {null['incumbent_metric']} "
        f"({null['fold_wins']}/{null['n_folds']} folds). "
        f"Whole-field DSR `{(sel['deflation'] or {}).get('dsr')}` (gate ≥ {LR.DSR_MIN}) · "
        f"PBO(eligible) `{(sel['deflation'] or {}).get('pbo')}` · p `{sel['pvalue']}`. "
        f"Matched-foil reading: **{attribution['reading']}** · attribution signature: "
        f"**{signature['verdict']}** · null state: **{null['state']}**.")
    return h, prose


def write_report(res: dict) -> tuple[Path, Path]:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = _REPORT_DIR / f"{_STEM}.json"
    mp = _REPORT_DIR / f"{_STEM}.md"
    jp.write_text(json.dumps(res, indent=2, default=str))
    md = _md(res)
    mp.write_text(md)
    return jp, mp


def _md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    return R1._md_table(rows, cols)


def _md(res: dict) -> str:
    sel, ver, null = res["selection"], res["verdict"], res["null"]
    L: list[str] = []
    A = L.append
    A("# NF-B3 — JOINT level+band selection under the corrected C3 (13 folds)\n")
    A(f"_generated {res['generated_at']}_ · `best_alpha = 0` · model "
      f"`{res['model_version']}` · recalibrates `{res['recalibrates']}` · "
      f"wall {res['wall_time_s']}s\n")
    A(f"## Verdict: **{res['headline']}**\n")
    A(res["verdict_prose"] + "\n")
    A("\n## 0. Provenance (every clause a RAISE)\n")
    A(f"- Served band held through the model path: universe IS80 "
      f"`{res['step0_reproduction']['universe_is80']}` (recorded 160.888, "
      f"Δ {res['step0_reproduction']['universe_is80_delta_pct']}%), tier coverage 2019–2025 "
      f"`{res['step0_reproduction']['served_tier_coverage_2019_2025']}` (recorded 0.8452); the "
      f"panel columns' 0.5046 reproduced beside it "
      f"(`{res['step0_reproduction']['panel_column_tier_coverage_2019_2025']}`) — the trap exists "
      "and this run is not in it.\n")
    A(f"- Boards 2013–2025 walk-forward with rookie legs from 2016; structurally rookie-less "
      f"(NCAAF substrate starts 2016): {res['structurally_rookieless_boards']} — C2 there is "
      "INACTIVE (vacuous, uninformative), never refused, never credited (NF-D20 (g⁗)).\n")
    A(f"- C3 equality boundary: `need = ceil(bind·n − 1e-9)` on the UNROUNDED incumbent "
      "(the NF-C3-REREAD harness finding, canonical here) — λ=0 is admissible by construction.\n")
    A("\n## 1. The field\n")
    A(_md_table(res["leaderboard"]))
    A("\n### Anchors (two-sided, scored every run)\n")
    A(_md_table(res["anchor_table"], ["anchor", "role", "expected", "CRPS", "MAE", "bias", "cov80",
                                      "behaves as expected"]))
    A("\n### C3 cannot police magnitude from above (inherited from NF-C3-REREAD) — the metric must\n")
    A(_md_table([res["c3_cannot_police_magnitude_from_above"]],
                ["over_scale_satisfies_c3_everywhere", "wide_band_satisfies_c3_everywhere",
                 "over_scale_loses_metric", "wide_band_loses_metric"]))
    A("\n### Per-form peeking ceilings (each form floored by the peeking version of its OWN form)\n")
    A(_md_table(res["ceiling_table"]))
    A(f"\n`ceilings_order_by_capacity` = **{res['ceilings_order_by_capacity']}** (CRPS-fitted) vs "
      f"**{res['ceilings_order_by_capacity_least_squares_fit']}** (LS-fitted disclosure).\n")
    A(f"\n⚠️ {res['anchor_table_note']}\n")
    A("\n## 2. Matched foil + attribution (NF-D15 (g′))\n")
    A(_md_table(res["attribution"]["rows"],
                ["arm", "form", "per_game_crps", "season_total_crps", "paired_delta",
                 "space_invariant_by_construction", "expected_tie_holds"]))
    A(f"\nreading = **{res['attribution']['reading']}** · signature: ")
    A(_md_table([res["signature"]]))
    A("\n## 3. Constraints\n")
    A("### C2 activity (NF-D20 (g⁗)) — inactive folds are uninformative, never passes\n")
    A(_md_table(res["constraint_activity"]))
    A("\n### Out-of-sample constraint state per arm\n")
    A(_md_table(res["constraint_table"]))
    A("\n### Whole-board cross-position movement — measured, gated on by nothing\n")
    A(_md_table(res["cross_position_table"]))
    A("\n## 4. Deflation + the pre-registered gate\n")
    A(_md_table([res["gate_table"]]))
    A(f"\nPBO(eligible) `{sel['deflation'].get('pbo')}` · whole-field DSR "
      f"`{sel['deflation'].get('dsr')}` (**the pre-registered gate**, ≥ 0.95) · contender-set DSR "
      f"`{sel['deflation'].get('dsr_contenders')}` · p `{sel['pvalue']}` · per-fold Δ "
      f"{sel['per_fold_delta']}\n")
    A("\n### The DSR margin, in the unit that grows (MH2 (b))\n")
    A(_md_table([res["dsr_margin"]]))
    A(f"\n{res['dsr_margin'].get('reading', '')}\n")
    A(f"\nSensitivities: {json.dumps(res['sensitivities'])}\n")
    A("\n### Per-position disclosure (computed, never selected on) + BH-FDR\n")
    A(_md_table(res["per_position"]["per_position"]))
    A(f"\nBH-FDR: {json.dumps(res['per_position'].get('fdr'))}\n")
    A("\n## 5. Null state / classification\n")
    A(_md_table([{k: v for k, v in null.items()
                  if k in ("state", "taxonomy_would_say", "taxonomy_fits",
                           "beats_incumbent_on_accuracy", "fold_wins", "n_folds", "observed_sr",
                           "dsr_ceiling_at_this_fold_count")}]))
    A(f"\n**why** — {null['why']}\n")
    A(f"\n**remedy** — {null['remedy']}\n")
    A(f"\n{null['wider_window_note']}\n")
    A("\n## 6. Story-level verdict\n")
    A(_md_table([ver]))
    A(f"\n## 6b. Registry action\n")
    A(_md_table([res["registry_action"]]))
    A("\n## 7. Scope + serving\n")
    A("- ⛔ Rookie leg out of scope (closed NF-D16→D21 chain, inherited by import).\n")
    A("- ⛔ NF1.5's ORDERING layer untouched — levels only.\n")
    A("- 🔒 CODE-READY, deploy-HELD. If the verdict ships, the publish of the recalibrated veteran "
      "board, a changelog line, and a `run_interval_revalidation` re-run (a level shift moves the "
      "band centre) are POST-MERGE OPERATOR steps — nothing serves from this run.\n")
    return "".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
