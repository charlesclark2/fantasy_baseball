"""run_nf_inj2c_dominance_baseline.py — NF-INJ2c node 3b: the capture-pinned give-back re-measure.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2c_dominance_baseline \
        --capture            # ONCE, at study start — stamps the published board
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj2c_dominance_baseline

⛔ THIS SCORES NO ARM AGAINST A REALIZED OUTCOME. It reads the CURRENT SERVED BOARD and measures the
board-level dominance inputs M2/M3/M4 of `nf_inj2c_margin_construction_rule.md` on it. It computes no
CV gate and reaches no verdict.

WHY IT EXISTS (PM re-scope ruling 3, verbatim): "the 82.70% -> 27.85% figures rode a board whose pin
failed at 40.58/797 rows. Capture-pin a fresh board + market snapshot (the D3 convention) and
re-measure the give-back and the coherence table on it BEFORE the prereg quotes any number. If the
re-measured dominance no longer holds on any dimension, that is a NULL, not a margin to adjust."

⭐ THE D3 CONVENTION, OPERATIONALISED — the half NF-INJ2b did not have. A reproduction pin over a
LIVE-SNAPSHOT-fed surface must bind an artifact CAPTURED AT STUDY START, never a re-pull:
`run_season_projection --market-refresh` pulls an ADP/ECR consensus that FEEDS THE ORDERING and moves
intraday, so a board re-pulled later is a different board and the pin fails for a reason that is a
property of the chain rather than of any arm. `--capture` stamps the staged artifact ONCE
(sha256 + captured_at + its own `generated_at`) into `nf_inj2c_capture.json`; every later run
ASSERTS the staged bytes still match that stamp and REFUSES if they moved. So "we pinned against the
capture" is a checkable fact rather than a claim about what somebody did first.

⛔ THE MARGINS ARE NOT SET HERE. `nf_inj2c_margin_construction_rule.md` (node 3a) was committed BEFORE
this runs, precisely so the numbers below cannot shape them. This module READS that rule's TIE BANDS
and applies them; it defines none. A band appearing here that is not in the rule is a defect.

🚦 OPERATOR RUN (>2 min: it rebuilds one full 2026 board per arm). `best_alpha = 0`; nothing serves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB  # noqa: E402,E501

log = logging.getLogger("nfl.fantasy.nf_inj2c_baseline")

_STEM = "nf_inj2c_dominance_baseline"
_REPORT_DIR = RB._REPORT_DIR
_BASELINE_DIR = RB._ART / "nf_inj2b_baseline"
_SERVED_JSON = _BASELINE_DIR / "served_projections_2026.json"
_CAPTURE_STAMP = _BASELINE_DIR / "nf_inj2c_capture.json"

#: the arms this node builds. `incumbent` + `stratified` are the dominance PAIR; `mvp1_null` is the
#: attribution CONTROL M2 requires and is therefore not optional; the rest populate the DISCLOSED
#: residual table PM ruling 2 asks for ("coherence is MEASURED AND REPORTED, both residual
#: populations"). ⛔ This arm list is NOT the declared FIELD — the field is a pre-registration act
#: and is not settled by this module.
BASELINE_ARMS: tuple[str, ...] = (
    "mvp1_null", "incumbent", "stratified", "feasibility_clamp",
    "points_rate_permute", "rate_refit", "points_rate_stratified", "rate_refit_stratified",
)

#: the STAGING command, quoted in every refusal so an operator never has to go and find it.
_STAGE_CMD = (
    "aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/projections.json "
    f"{_SERVED_JSON} --region us-east-1")

# ── the margin rule's TIE BANDS, READ not defined (node 3a owns them) ──────────────────────────
#: M3 — `times_over` is recorded at 2 decimals, so its band is that precision (rule R2).
M3_TIE_BAND = 0.01
#: M4 — `giveback_pct` is recorded at 2 decimals (rule R2).
M4_TIE_BAND = 0.01


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def capture(force: bool = False) -> dict:
    """Stamp the staged published board ONCE, at study start (the D3 convention)."""
    if not _SERVED_JSON.exists():
        raise SystemExit(f"nothing staged at {_SERVED_JSON} — stage it first:\n  {_STAGE_CMD}")
    if _CAPTURE_STAMP.exists() and not force:
        raise SystemExit(
            f"a capture already exists at {_CAPTURE_STAMP}. ⛔ Re-capturing MID-STUDY is exactly "
            "what the D3 convention forbids — the pin would then bind a board captured AFTER the "
            "arms were measured. Pass --recapture ONLY to start the study over.")
    doc = json.loads(_SERVED_JSON.read_text())
    stamp = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(_SERVED_JSON),
        "served_generated_at": doc.get("generated_at"),
        "n_players": len(doc.get("players") or []),
        "source": str(_SERVED_JSON),
        "convention": ("D3 — a reproduction pin over a live-snapshot-fed surface binds a CAPTURED "
                       "artifact, never a re-pull; --market-refresh moves the ADP/ECR consensus "
                       "that feeds the ordering, so a later pull is a different board"),
    }
    _CAPTURE_STAMP.write_text(json.dumps(stamp, indent=2))
    log.info("captured the published board: generated_at=%s sha256=%s...",
             stamp["served_generated_at"], stamp["sha256"][:12])
    return stamp


def assert_capture_intact() -> dict:
    """The staged bytes must still be the ones the capture stamped. REFUSES, never warns."""
    if not _CAPTURE_STAMP.exists():
        raise SystemExit(
            f"no capture stamp at {_CAPTURE_STAMP} — the D3 convention requires the published board "
            "to be CAPTURED AT STUDY START and pinned against that capture. Stage it and capture:\n"
            f"  {_STAGE_CMD}\n"
            "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
            "run_nf_inj2c_dominance_baseline --capture")
    stamp = json.loads(_CAPTURE_STAMP.read_text())
    if not _SERVED_JSON.exists():
        raise SystemExit(f"the captured board is gone from {_SERVED_JSON}; re-stage:\n  {_STAGE_CMD}")
    now = _sha256(_SERVED_JSON)
    if now != stamp.get("sha256"):
        raise SystemExit(
            f"the staged board has CHANGED since it was captured "
            f"(sha256 {stamp.get('sha256','?')[:12]}... -> {now[:12]}...). A pin against a re-pull "
            "is the exact failure D3 names — NF-INJ2b's freshness bar PASSED at 7.30h while its pin "
            "FAILED at 40.58 over 797 rows, because the ADP/ECR snapshot feeding the ordering moves "
            "intraday. Either restore the captured bytes or start the study over with --recapture.")
    return stamp


def _giveback_measure(pct) -> float | None:
    """M4 = `max(give_back_pct, 0)` — declared in the margin rule §3(a) BEFORE this ran.

    The defect NF-INJ1 named is injured players marked back UP, i.e. a POSITIVE give-back. Scoring
    the signed value would let an arm bank credit for OVER-discounting, which is a different defect
    wearing this measure's clothes. The signed figure is reported beside it, always."""
    return None if pct is None else max(float(pct), 0.0)


def _worst_times_over(rec: dict) -> float | None:
    w = [v["implied_per_game"] / v["max_ever_per_game"]
         for v in rec.get("worst_violations") or []
         if v.get("max_ever_per_game") and v.get("implied_per_game") is not None]
    return round(max(w), 4) if w else None


def dominance_table(app: dict) -> dict:
    """M2 / M3 / M4 for every built arm, against the SERVED incumbent, through the node-3a bands."""
    arms = app["arms"]
    inc = arms.get("incumbent")
    if inc is None:
        raise SystemExit("the incumbent was not built — there is no baseline to dominate against")
    base = {
        "M2_violations_attributable": inc["coherence_violating_players_attributable"],
        "M3_worst_times_over": _worst_times_over(inc),
        "M4_giveback_measure": _giveback_measure(inc["injury_giveback"].get("giveback_pct")),
        "M4_giveback_signed": inc["injury_giveback"].get("giveback_pct"),
    }
    out: dict = {
        "served_incumbent_baseline": base,
        "bands": {
            "M2": ("SE of the per-fold PAIRED difference — a FOLD quantity computed by the decisive "
                   "run, ⛔ not on a single board; the board figure here is the BASELINE the "
                   "pre-registration quotes"),
            "M3": M3_TIE_BAND, "M4": M4_TIE_BAND,
            "source": "nf_inj2c_margin_construction_rule.md (node 3a), committed before this ran",
        },
        "arms": {},
    }
    for arm, rec in arms.items():
        gb = rec["injury_giveback"]
        m2 = rec["coherence_violating_players_attributable"]
        m3, m4 = _worst_times_over(rec), _giveback_measure(gb.get("giveback_pct"))
        row = {
            "M2_violations_attributable": m2,
            "M2_delta_vs_incumbent": m2 - base["M2_violations_attributable"],
            "M3_worst_times_over": m3,
            "M4_giveback_measure": m4,
            "M4_giveback_signed": gb.get("giveback_pct"),
            "coherence_violating_players_raw": rec["coherence_violating_players"],
            "coherence_by_position": rec["coherence_by_position"],
            "clamp_hi": rec["clamp_saturation_high"], "clamp_lo": rec["clamp_saturation_low"],
        }
        for key, mine, theirs, band in (("M3", m3, base["M3_worst_times_over"], M3_TIE_BAND),
                                        ("M4", m4, base["M4_giveback_measure"], M4_TIE_BAND)):
            if mine is None or theirs is None:
                row[f"{key}_verdict"] = "UNEVALUABLE"   # ⛔ never scored as a pass (NF1.7 (a))
                continue
            d = theirs - mine                            # both measures: LOWER is better
            row[f"{key}_verdict"] = ("IMPROVES" if d > band else
                                     "REGRESSES" if d < -band else "TIES")
        row["M2_verdict"] = ("IMPROVES" if row["M2_delta_vs_incumbent"] < 0 else
                             "REGRESSES" if row["M2_delta_vs_incumbent"] > 0 else "TIES")
        row["M1_M5_M6"] = "UNEVALUATED HERE — fold measures, owned by the decisive run (node 4)"
        out["arms"][arm] = row
    return out


def write_md(rep: dict, path: Path) -> None:
    app, dom = rep["application_2026"], rep["dominance"]
    cap, pin = rep["capture"], app.get("reproduction_pin") or {}
    fresh = app.get("baseline_freshness") or {}
    L = ["# NF-INJ2c node 3b — the capture-pinned dominance baseline", "",
         "> ⛔ A BOARD MEASUREMENT, not a bake-off: no arm is scored against a realized outcome and "
         "no CV gate is computed here. The fold measures M1/M5/M6 belong to the decisive run.", "",
         f"Generated {rep['generated_at']}. PM re-scope ruling 3.", "",
         "## 1. The capture (D3 — pinned against a CAPTURED artifact, never a re-pull)", "",
         "| field | value |", "|---|---|",
         f"| captured_at | {cap['captured_at']} |",
         f"| served `generated_at` | {cap['served_generated_at']} |",
         f"| sha256 | `{cap['sha256'][:16]}...` |",
         f"| players | {cap['n_players']} |",
         f"| local MVP-1 `generated_at` | {app.get('board_generated_at')} |",
         f"| lag vs served | {fresh.get('lag_hours')}h (bar {fresh.get('max_lag_hours')}h) |", "",
         f"**Reproduction pin:** worst absolute difference **{pin.get('worst_abs_diff')}** over "
         f"{pin.get('n')} rows against a tolerance of {pin.get('tolerance')} ⇒ "
         f"**{pin.get('reproduces')}**.", ""]
    if not pin.get("reproduces", False):
        L += ["> ⛔ **THE PIN DOES NOT HOLD, so this run is VOID — not a null** (margin rule §5 "
              "branch 3). A dominance claim against a board nobody is served is not a measurement.",
              ""]
    L += ["## 2. The board-level dominance measures, against the SERVED incumbent", "",
          "Bands are READ from `nf_inj2c_margin_construction_rule.md` (node 3a, committed BEFORE "
          "this ran); ⛔ none is defined here.", "",
          "| arm | M2 attributable viol. | Δ vs inc | M2 | M3 worst × | M3 | M4 give-back "
          "(measure) | M4 signed | M4 | clamp hi/lo |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for arm, r in dom["arms"].items():
        L.append(f"| `{arm}` | {r['M2_violations_attributable']} | "
                 f"{r['M2_delta_vs_incumbent']:+d} | {r['M2_verdict']} | "
                 f"{r['M3_worst_times_over']} | {r['M3_verdict']} | {r['M4_giveback_measure']} | "
                 f"{r['M4_giveback_signed']} | {r['M4_verdict']} | {r['clamp_hi']}/{r['clamp_lo']} |")
    L += ["", "⭐ **M4 is `max(give_back_pct, 0)`** — declared in the margin rule §3(a) before this "
              "ran, because the defect NF-INJ1 named is injured players marked back UP; the SIGNED "
              "figure is reported beside it always.", "",
          f"⭐ **ATTRIBUTION BY CONTROL:** {app.get('attribution_control')}", "",
          "⚠️ M1 (CRPS), M5 (per-position ordering) and M6 (interval floors) are FOLD measures and "
          "are UNEVALUATED here — named rather than silently omitted, because a dominance table "
          "missing three of its six measures must not read as a complete one (NF1.7 (a)).", ""]
    path.write_text("\n".join(L) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ2c node 3b — capture-pinned dominance baseline")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=N15.MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--capture", action="store_true",
                    help="stamp the staged published board ONCE, at study start (D3)")
    ap.add_argument("--recapture", action="store_true",
                    help="start the study over — overwrites an existing capture stamp")
    ap.add_argument("--arms", default=None, help="comma-separated; default = BASELINE_ARMS")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    logging.getLogger("nfl").setLevel(logging.INFO)

    if args.capture or args.recapture:
        capture(force=args.recapture)
        return 0
    stamp = assert_capture_intact()

    import duckdb
    if not Path(args.duckdb).is_absolute() and not Path(args.duckdb).exists():
        cand = _PROJECT_ROOT / args.duckdb
        if cand.exists():
            args.duckdb = str(cand)
    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — a fresh worktree does not carry the "
                         "gitignored artifact (NF-INFRA1); pass --duckdb with an absolute path.")
    con = duckdb.connect(args.duckdb, read_only=True)
    selections = N15.load_selection(json.loads(RB._NF1_5_REPORT.read_text()),
                                    board="beats-incumbent")
    arms = (tuple(a.strip() for a in args.arms.split(",")) if args.arms else BASELINE_ARMS)
    if "incumbent" not in arms or "mvp1_null" not in arms:
        raise SystemExit("`incumbent` (the dominance baseline) and `mvp1_null` (M2's attribution "
                         "control) are not optional — refusing a run that could not compute M2")

    app = RB.apply_2026(con, args.schema, selections, arms, base_from=args.base_from,
                        served_json=_SERVED_JSON)
    rep = {
        "story": "NF-INJ2c node 3b — capture-pinned dominance baseline (PM re-scope ruling 3)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0,
        "capture": stamp,
        "arms": list(arms),
        "application_2026": app,
        "dominance": dominance_table(app),
    }
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{_STEM}.json").write_text(json.dumps(rep, indent=2, default=str))
    write_md(rep, _REPORT_DIR / f"{_STEM}.md")
    pin = app.get("reproduction_pin") or {}
    if not pin.get("reproduces", False):
        log.error("[ALERT] THE REPRODUCTION PIN DOES NOT HOLD (worst %s over %s rows vs %s) — this "
                  "run is VOID, not a null (margin rule §5 branch 3)",
                  pin.get("worst_abs_diff"), pin.get("n"), pin.get("tolerance"))
        return 2
    log.info("node 3b complete — pin holds; dominance table written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
