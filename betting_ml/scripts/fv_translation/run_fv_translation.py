"""run_fv_translation.py — MLB Edge-E7.8 CLI: does FanGraphs FV/rank translate to MLB fantasy value?

Reads the cohort parquet built by `build_fv_cohort.py`, runs the §0.5 bake-off for every
(player_type × stage), applies the deflation gates (PBO / config spread / DSR / BH-FDR), and writes
the registered verdict + the draft-actionable takeaway.

  # 1. assemble the cohort ONCE (SF-free DuckDB/S3 — see build_fv_cohort.py; >2 min ⇒ operator)
  uv run python -m betting_ml.scripts.fv_translation.build_fv_cohort --horizon 3 --season-ceiling 2022
  # 2. the study (reads the cached parquet)
  uv run python -m betting_ml.scripts.fv_translation.run_fv_translation \
      --cohort quant_sports_intel_models/baseball/edge_program/ablation_results/e7_8_artifacts/fv_translation_cohort.parquet

Outputs:
  * ablation_results/e7_8_fv_translation.md    — the registered verdict (OVERWRITES the pre-registration)
  * ablation_results/e7_8_fv_translation.json  — leaderboards, per-fold matrices, gates, verdicts
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.fv_translation.fv_translation import (  # noqa: E402
    BAT_FP_WEIGHTS,
    DSR_MIN,
    FDR_Q,
    PBO_MAX,
    PIT_FP_WEIGHTS,
    PRIMARY_CONTRAST,
    SECONDARY_CONTRAST,
    STAGES,
    STUDY_VERSION,
    bh_fdr,
    draft_takeaway,
    mechanism_read,
    mechanism_rows,
    run_stage,
    stage_verdict,
)

log = logging.getLogger("e7_8.run")

_ABLATION = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
_DEFAULT_COHORT = _ABLATION / "e7_8_artifacts/fv_translation_cohort.parquet"
_REPORT_MD = _ABLATION / "e7_8_fv_translation.md"
_REPORT_JSON = _ABLATION / "e7_8_fv_translation.json"

_STAGE_BLURB = {
    "debut": ("SELECTION channel — P(reach MLB with real playing time inside the window), scored by "
              "AUC on the FULL board cohort. This is the survivorship mechanism modelled EXPLICITLY "
              "instead of being allowed to inflate a production fit."),
    "conditional": ("PRODUCTION GIVEN ARRIVAL — fantasy points among prospects who debuted, Spearman ρ. "
                    "⚠️ This stage is survivorship-EXPOSED by construction (its population is the "
                    "survivors); it is reported so the inflation is visible, and it is NOT the "
                    "headline."),
    "unconditional": ("⭐ THE DRAFT-RELEVANT STAGE — fantasy points over the WHOLE cohort with a hard 0 "
                      "for a prospect who never arrived, Spearman ρ. Zero is a realized dynasty "
                      "outcome, not missing data, so this stage carries NO survivorship selection."),
}


def run_study(cohort: pd.DataFrame, *, strict_realtime: bool = False,
              horizon: int = 3, learner: str = "linear", learner_set=None) -> dict:
    """Every (player_type × stage), then the family-wide BH-FDR and the verdicts."""
    types = [t for t in ("batter", "pitcher") if (cohort["player_type"] == t).sum() >= 100]
    results: dict[tuple[str, str], object] = {}
    skipped: list[str] = []
    for t in types:
        for stage in STAGES:
            try:
                results[(t, stage)] = run_stage(cohort, player_type=t, stage=stage,
                                                horizon=horizon, strict_realtime=strict_realtime,
                                                learner_set=learner_set)
            except Exception as e:  # noqa: BLE001 — an unscorable cell is reported, never forced
                skipped.append(f"{t}/{stage}: {type(e).__name__}: {e}")
                log.warning("skipped %s/%s — %s", t, stage, e)

    # ── BH-FDR across the study family (the FIXED primary contrast only) ──────────────────────────
    pvals = {f"{t}/{s}": (r.contrasts.get("primary", {}).get(learner, {}) or {}).get("p_value")
             for (t, s), r in results.items()}
    fdr = bh_fdr(pvals, q=FDR_Q)
    verdicts = [stage_verdict(r, fdr_pass=fdr.get(f"{t}/{s}", False), learner=learner)
                for (t, s), r in results.items()]
    return {"results": results, "pvals": pvals, "fdr": fdr, "verdicts": verdicts,
            "skipped": skipped, "types": types}


class _RenderedStage:
    """A StageResult-shaped view over a saved JSON cell, so the report can be RE-RENDERED without
    re-fitting. A prose or table improvement to the report must not cost a multi-minute refit — and
    re-running to change wording invites 'just tweak it until it reads well', which is how a report
    stops matching its numbers."""

    def __init__(self, cell: dict):
        self.leaderboard = pd.DataFrame(cell["leaderboard"])
        self.per_fold = pd.DataFrame(cell["per_fold"]).T if cell.get("per_fold") else pd.DataFrame()
        self.fold_cohorts = cell.get("fold_cohorts", [])
        self.n_train_rows = cell.get("n_train_rows", 0)
        self.n_test_rows = cell.get("n_test_rows", 0)
        self.n_purged_rows = cell.get("n_purged_rows", 0)
        self.oracle_ok = cell.get("oracle_ok", True)
        self.oracle_score = cell.get("oracle_score")
        self.pbo = cell.get("pbo")
        self.config_spread = cell.get("config_spread")
        self.full_spread = cell.get("full_spread")
        self.dsr = cell.get("dsr")
        self.contrasts = cell.get("contrasts", {})
        self.notes = cell.get("notes", [])


def study_from_json(payload: dict) -> dict:
    """Rebuild the `run_study` shape from a saved summary JSON (report re-render only)."""
    results = {}
    for key, cell in payload.get("per_cell", {}).items():
        ptype, stage = key.split("/", 1)
        results[(ptype, stage)] = _RenderedStage(cell)
    return {"results": results, "pvals": payload.get("pvalues", {}),
            "fdr": payload.get("fdr_survives", {}), "verdicts": payload.get("verdicts", []),
            "skipped": payload.get("skipped", []),
            "types": sorted({k.split("/")[0] for k in payload.get("per_cell", {})})}


def _term(weight: float, label: str) -> str:
    """Render a signed scoring term ('− 0.5·K' / '+ 1.0·BB') so the formula reads like arithmetic."""
    sign = "−" if weight < 0 else "+"
    return f"{sign} {abs(weight)}·{label}"


def _cohort_summary(cohort: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (t, s), g in cohort.groupby(["player_type", "board_season"]):
        rows.append({
            "player_type": t, "board_season": int(s), "prospects": len(g),
            "debut_rate": round(float(g["debuted"].mean()), 3),
            "median_fv": float(pd.to_numeric(g["fv"], errors="coerce").median()),
            "mean_fantasy_points": round(float(pd.to_numeric(g["fantasy_points"],
                                                             errors="coerce").mean()), 1),
        })
    return pd.DataFrame(rows).sort_values(["player_type", "board_season"])


def write_report(study: dict, cohort: pd.DataFrame, args, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    verdicts = study["verdicts"]
    a("# MLB Edge-E7.8 — do FanGraphs prospect rankings translate to MLB projection?")
    a("")
    a(f"**Study:** `{STUDY_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()} · "
      f"**outcome window:** {args.horizon} MLB seasons · **learner for the headline contrast:** "
      f"`{args.learner}`")
    a("")
    a("> ⚠️ **This is a projection-VALIDATION study, not an edge claim — `best_alpha = 0`.** It asks "
      "one question: does The Board's as-of FV/rank add incremental projection lift on realized "
      "dynasty-FANTASY value **over an age-relative-to-level + level + pedigree null**, once the "
      "survivorship and level confounds are controlled? A CLEAN NULL is a valid, high-value answer "
      "(it says: lean on our own MLE + age-relative-to-level, do not pay up for FV hype) and is NOT "
      "forced into a survivor.")
    a("")

    # ── the headline ──────────────────────────────────────────────────────────────────────────────
    a("## 0. Verdict")
    a("")
    vt = pd.DataFrame([{k: v for k, v in d.items() if k in
                        ("player_type", "stage", "adds_lift", "mean_lift", "p_value", "dsr",
                         "pbo", "config_spread", "full_spread")} for d in verdicts])
    a(vt.to_markdown(index=False, floatfmt=".4f") if len(vt) else "_no scorable cell_")
    a("")
    a(f"**🎯 DRAFT TAKEAWAY —** {draft_takeaway(verdicts)}")
    a("")
    # ── the mechanism — the question the headline contrast cannot answer ─────────────────────────
    rows = mechanism_rows(study["results"])
    if rows:
        a("")
        a("### 0b. WHY — is FV a substitute for our own MLE, or a complement to it?")
        a("")
        a("A positive contrast says FV adds something; it does not say whether FV adds something our "
          "own model already knew. This decomposes the same leaderboard into **how much our MiLB "
          "performance read adds over the null**, and **how much FV adds ON TOP of it** (each feature "
          "set at its best learner):")
        a("")
        a(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".4f"))
        a("")
        for ptype, note in mechanism_read(rows).items():
            a(f"- **`{ptype}`** — {note}")
        a("")
        a("> This is a *computed* read, not a narrative imposed on the numbers — a future re-run can "
          "overturn it. Where it lands as COMPLEMENTS, note the independent corroboration from "
          "**E7.3 vs E7.3p**: minor-league rates translate far better for bats than for arms (batter "
          "K% OOS corr **0.637** vs pitcher K% **0.366** on the same harness), so the statistical "
          "record leaves more unexplained on the pitching side — exactly the room a scouting grade "
          "would fill.")
        a("")
    a(f"Gates: PBO < {PBO_MAX} · DSR ≥ {DSR_MIN} · BH-FDR q = {FDR_Q} across the "
      f"{len(study['pvals'])}-test family (player_type × stage). Every stage's PBO reading:")
    for d in verdicts:
        a(f"- `{d['player_type']}/{d['stage']}` — {d['pbo_read']}")
    if study["skipped"]:
        a("")
        a("**Unscorable cells (reported, not silently dropped):**")
        for s in study["skipped"]:
            a(f"- {s}")
    a("")

    # ── target definition ────────────────────────────────────────────────────────────────────────
    a("## 1. The outcome target (stated + defended)")
    a("")
    a("The consumers are a **dynasty board and a fantasy draft**, not a front office — so the target "
      "is fantasy VALUE, never WAR. Concretely, for each (board season, prospect):")
    a("")
    a(f"* **Batter fantasy points** = `{BAT_FP_WEIGHTS['hit_non_hr']}·(H − HR) + "
      f"{BAT_FP_WEIGHTS['hr']}·HR + {BAT_FP_WEIGHTS['bb']}·BB {_term(BAT_FP_WEIGHTS['k'], 'K')}`, "
      f"accumulated over the **{args.horizon} MLB seasons following the board snapshot**. The `1.3` weight on "
      "non-HR hits is the population mean total bases per non-home-run hit — it recovers total bases "
      "in expectation without the 2B/3B split, which the Statcast-derived mart does not expose at "
      "game grain.")
    a(f"* **Pitcher fantasy points** = `{PIT_FP_WEIGHTS['ip']}·IP + {PIT_FP_WEIGHTS['k']}·K "
      f"{_term(PIT_FP_WEIGHTS['hit'], 'H')} {_term(PIT_FP_WEIGHTS['bb'], 'BB')} "
      f"{_term(PIT_FP_WEIGHTS['hr'], 'HR')}`, with `IP = (BF − H − BB)/3`.")
    a("* **A prospect who never reaches the majors inside the window scores ZERO** — for a dynasty "
      "owner that is a realized outcome, not missing data. This is what makes the headline stage "
      "survivorship-free.")
    a("")
    a("**Why accumulated points and not a rate:** dynasty value is `playing time × quality`, and the "
      "single biggest source of prospect value dispersion is whether he plays at all. A rate target "
      "would hand the study back the survivorship confound it exists to control.")
    a("")
    a("**Known target limitations (stated, not buried):** R / RBI / SB are absent from the Statcast "
      "substrate. R and RBI are lineup-context terms that largely track playing time and production "
      "(both already in the target), but **SB is a genuinely distinct speed skill this target cannot "
      "see** — a speed-first prospect is under-valued here. Pitcher W / SV / ER are likewise "
      "unavailable; HR carries the earned-run weight as the proxy, and innings are reconstructed from "
      "batters faced minus baserunners.")
    a("")

    # ── cohort ───────────────────────────────────────────────────────────────────────────────────
    a("## 2. The cohort (and how thin it is)")
    a("")
    a(_cohort_summary(cohort).to_markdown(index=False))
    a("")
    a(f"Total study rows **{len(cohort):,}** across **{cohort['player_key'].nunique():,}** distinct "
      f"prospects and **{cohort['board_season'].nunique()}** board cohorts.")
    a("")
    a("⚠️ **Small-N is the defining constraint** (the NF1.4 rookie-prior situation). The CV fold unit "
      "is the BOARD COHORT, and a full outcome window costs one cohort per horizon season, so the "
      "study has a handful of folds — enough for an honest read, not enough to resolve a small true "
      "effect. Where PBO is not computable it is reported as such, never quietly omitted.")
    a("")

    # ── design ───────────────────────────────────────────────────────────────────────────────────
    a("## 3. Design — the confounds, and how each is controlled")
    a("")
    a("**Survivorship.** Modelled as its own channel rather than corrected after the fact: the "
      "`debut` stage predicts WHO ARRIVES on the full cohort, the `conditional` stage measures "
      "production among survivors (and is explicitly labelled as the survivorship-exposed one), and "
      "the `unconditional` stage — the headline — scores the whole cohort with a hard zero for "
      "non-arrivals, so no selection is applied at all.")
    a("")
    a("**Level confound.** `level` (one-hot) and **age-relative-to-level** (age minus the "
      "TRAIN-fold mean age at that level) are in the NULL arm, so FV is never credited for what level "
      "already told us. The level means are fitted in-fold and applied verbatim to the eval cohort.")
    a("")
    a("**Leakage.** Board attributes are read at the season's as-of snapshot; the MiLB line "
      "aggregates only games STRICTLY BEFORE that date; the outcome window opens strictly AFTER it. "
      "The CV **purges from every training fold any player who appears in the eval cohort** — the "
      "same prospect sits on 3–5 consecutive boards sharing one overlapping outcome window, so "
      "without the purge a 'projection' is partly a memory.")
    a("")
    a(f"**The pre-registered contrasts** (fixed in advance — no post-hoc winner picking): PRIMARY "
      f"`{PRIMARY_CONTRAST[0]}` vs `{PRIMARY_CONTRAST[1]}` (does FV add over our own performance read "
      f"plus the null?) and SECONDARY `{SECONDARY_CONTRAST[0]}` vs `{SECONDARY_CONTRAST[1]}` (is FV "
      f"informative at all, before our read?). The wider feature-set × FV-transform × learner search "
      f"is run too and deflated — it answers the different question 'could a cherry-picked FV "
      f"configuration look good by chance?'.")
    a("")
    a("**⚠️ Two documented deviations, both biasing TOWARD finding FV lift (so a null is "
      "conservative):**")
    a("1. **Pedigree is a proxy, not draft round/bonus.** MLB draft round and signing bonus are NOT "
      "in the lake (no StatsAPI draft ingest exists — that is a real follow-up story). The null uses "
      "`pro_experience_years` + level-for-age instead, which makes the null WEAKER than the story "
      "pre-registered.")
    a("2. **Pre-2026 as-of dating is approximate.** FanGraphs serves the RETAINED past board rather "
      "than a true point-in-time snapshot (E7.7 stamps those rows `<season>-07-01`), so a pre-2026 "
      "grade may embed a later revision — i.e. hindsight. The forward daily capture builds the "
      "genuine point-in-time series from 2026 onward.")
    a("")

    # ── per-stage detail ─────────────────────────────────────────────────────────────────────────
    for (t, stage), res in study["results"].items():
        a(f"## 4. `{t}` — stage `{stage}`")
        a("")
        a(f"> {_STAGE_BLURB[stage]}")
        a("")
        a(f"Folds (board cohorts scored): `{res.fold_cohorts}` · train rows {res.n_train_rows:,} "
          f"(after purging {res.n_purged_rows:,} rows of prospects who recur in the eval cohort) · "
          f"eval rows {res.n_test_rows:,} · oracle ceiling "
          f"{'n/a' if res.oracle_score is None else f'{res.oracle_score:.3f}'} "
          f"({'holds ✅' if res.oracle_ok else 'VIOLATED ❌'})")
        a("")
        a("**Leaderboard** (mean out-of-sample "
          f"{'AUC' if stage == 'debut' else 'Spearman ρ'}, higher is better; `uses_fangraphs` marks "
          "the FV/rank arms):")
        a("")
        a(res.leaderboard.to_markdown(index=False, floatfmt=".4f"))
        a("")
        for tag, pair in (("PRIMARY", PRIMARY_CONTRAST), ("SECONDARY", SECONDARY_CONTRAST)):
            c = res.contrasts.get(tag.lower(), {})
            if not c:
                continue
            a(f"**{tag} contrast — `{pair[0]}` − `{pair[1]}`:**")
            a("")
            a(pd.DataFrame([{"learner": k, "mean_lift": v["mean_lift"], "p_value": v["p_value"],
                             "dsr": v["dsr"], "per_fold_delta": v["per_fold_delta"]}
                            for k, v in c.items()]).to_markdown(index=False, floatfmt=".4f"))
            a("")
        if res.notes:
            a("_Notes:_")
            for n_ in res.notes[:12]:
                a(f"- {n_}")
            a("")

    # ── limitations ──────────────────────────────────────────────────────────────────────────────
    a("## 5. Limitations")
    a("")
    a("- **Small-N by construction** — one CV fold per board cohort with a closed outcome window. A "
      "true small effect is not resolvable here; the study can honestly rule out a LARGE one.")
    a("- **The CV is cohort-out, not strictly real-time.** A model tested on cohort *S* trains on "
      "earlier boards whose outcome windows had not fully closed by *S*. The strictly-real-time "
      "variant (`--strict-realtime`) leaves too few folds for PBO at this cohort count; it is run as "
      "a sensitivity where the folds exist.")
    a("- **Pedigree proxy, not draft round/bonus** (see §3) — the null is weaker than pre-registered.")
    a("- **Pre-2026 as-of is approximate** (see §3) — a retained board, not a point-in-time snapshot.")
    a("- **The target cannot see stolen bases** (nor pitcher W/SV/ER) — see §1.")
    a("- **The board is FanGraphs' graded population**, ~1.3k names a season. Prospects FanGraphs "
      "never graded are outside the study, so this measures 'is the GRADE informative among the "
      "graded', not 'is the board's coverage complete'.")
    a("- **`best_alpha = 0`** — a Dynasty projection-validation study, never a market claim.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def _json_payload(study: dict, cohort: pd.DataFrame, args) -> dict:
    return {
        "study_version": STUDY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_seasons": args.horizon,
        "headline_learner": args.learner,
        "strict_realtime": bool(args.strict_realtime),
        "gates": {"pbo_max": PBO_MAX, "dsr_min": DSR_MIN, "fdr_q": FDR_Q},
        "cohort": {
            "rows": int(len(cohort)),
            "players": int(cohort["player_key"].nunique()),
            "board_seasons": sorted(int(s) for s in cohort["board_season"].dropna().unique()),
            "by_type": cohort["player_type"].value_counts().to_dict(),
            "debut_rate": {t: round(float(g["debuted"].mean()), 4)
                           for t, g in cohort.groupby("player_type")},
        },
        "pvalues": study["pvals"],
        "fdr_survives": study["fdr"],
        "verdicts": study["verdicts"],
        "draft_takeaway": draft_takeaway(study["verdicts"]),
        "skipped": study["skipped"],
        "per_cell": {
            f"{t}/{s}": {
                "fold_cohorts": r.fold_cohorts,
                "n_train_rows": r.n_train_rows, "n_test_rows": r.n_test_rows,
                "n_purged_rows": r.n_purged_rows,
                "oracle_ok": r.oracle_ok, "oracle_score": r.oracle_score,
                "pbo": r.pbo, "config_spread": r.config_spread, "full_spread": r.full_spread,
                "dsr": r.dsr,
                "leaderboard": r.leaderboard.to_dict(orient="records"),
                "per_fold": r.per_fold.to_dict(orient="index"),
                "contrasts": r.contrasts,
                "notes": r.notes[:20],
            } for (t, s), r in study["results"].items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.8 — does FanGraphs FV/rank translate to MLB fantasy value?")
    p.add_argument("--cohort", default=str(_DEFAULT_COHORT),
                   help="the cohort parquet from build_fv_cohort.py")
    p.add_argument("--horizon", type=int, default=3,
                   help="outcome-window seasons the cohort was built with (used by the CV purge)")
    p.add_argument("--learner", default="linear",
                   help="learner carrying the headline contrast (default `linear` — the "
                        "lowest-variance choice at this sample size)")
    p.add_argument("--strict-realtime", action="store_true",
                   help="sensitivity: train only on cohorts whose outcome window had CLOSED by the "
                        "eval cohort's board date (usually too few folds for PBO)")
    p.add_argument("--render-only", action="store_true",
                   help="re-render the markdown report from the SAVED summary JSON — no re-fitting, "
                        "seconds. Use after a report prose/table change; the numbers are untouched")
    p.add_argument("--fast", action="store_true",
                   help="smoke: run the linear learner only (the full grid adds the two GBM "
                        "settings). A narrowed grid narrows the DSR trial count too — correct, but "
                        "NOT the registered run")
    p.add_argument("--report", default=str(_REPORT_MD))
    p.add_argument("--json", dest="json_path", default=str(_REPORT_JSON))
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if args.render_only:
        if not Path(args.json_path).exists():
            p.error(f"--render-only needs the saved summary at {args.json_path}")
        if not Path(args.cohort).exists():
            p.error(f"--render-only still reads the cohort for §2 — not found at {args.cohort}")
        payload = json.loads(Path(args.json_path).read_text())
        args.horizon = payload.get("horizon_seasons", args.horizon)
        args.learner = payload.get("headline_learner", args.learner)
        study = study_from_json(payload)
        write_report(study, pd.read_parquet(args.cohort), args, Path(args.report))
        log.info("re-rendered %s from %s (numbers untouched)", args.report, args.json_path)
        return 0

    if not Path(args.cohort).exists():
        p.error(f"cohort parquet not found at {args.cohort} — run build_fv_cohort.py first")
    cohort = pd.read_parquet(args.cohort)
    log.info("loaded %d cohort rows (%d players, seasons %s)", len(cohort),
             cohort["player_key"].nunique(),
             sorted(int(s) for s in cohort["board_season"].dropna().unique()))

    from betting_ml.scripts.fv_translation.fv_translation import Learner
    study = run_study(cohort, strict_realtime=args.strict_realtime,
                      horizon=args.horizon, learner=args.learner,
                      learner_set=[Learner("linear", "linear")] if args.fast else None)
    for v in study["verdicts"]:
        log.info("verdict %-8s/%-14s adds_lift=%-5s lift=%s p=%s dsr=%s pbo=%s",
                 v["player_type"], v["stage"], v["adds_lift"],
                 None if v["mean_lift"] is None else round(v["mean_lift"], 4),
                 v["p_value"], v["dsr"], v["pbo"])
    log.info("DRAFT TAKEAWAY — %s", draft_takeaway(study["verdicts"]))

    Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_path).write_text(json.dumps(_json_payload(study, cohort, args), indent=2,
                                               default=_default))
    log.info("summary → %s", args.json_path)
    if not args.no_report:
        write_report(study, cohort, args, Path(args.report))
    return 0


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


if __name__ == "__main__":
    raise SystemExit(main())
