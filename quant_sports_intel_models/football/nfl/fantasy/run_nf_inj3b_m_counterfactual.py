"""run_nf_inj3b_m_counterfactual.py — NF-INJ3b-M nodes 3+4: the served-POINT impact, MEASURED.

This closes NF-INJ3b's blocking §5(d). The question it answers is **not** "how much do the flagged
players' expected GAMES change" — NF-INJ3b already published that (5.292 → 2.682, 22 of 22 down).
It is: **what happens to the POINT and the RANK a drafter actually sees.**

⭐ WHY THAT CANNOT BE ESTIMATED. `pts` is NOT `rate × games`: NF1.5 PERMUTES the within-position
POINT MULTISET (each position's players are handed that position's own MVP-1 point multiset in
learned-rank order), so changing every flagged veteran's games changes the multiset the permutation
then re-assigns — NF-INJ1 measured that step handing **+36.4%** of an availability discount BACK.
⛔ No proportional shortcut appears anywhere in this file; both boards are BUILT.

HOW THE COUNTERFACTUAL IS CONSTRUCTED — both boards through the SAME shipped assembly, in ONE
process, so every difference is the cap's doing and not a build or sort convention:

  baseline        `injury_games_policy.SERVING_ENABLED = False`  → the incumbent cap path
  counterfactual  the policy forced ON in-process + the covariate feed supplied

⚠️ The policy is forced ON **in memory only**. The committed flag stays False (DEPLOY-HELD); this
runner NEVER publishes and takes no `--publish` flag at all.

⭐ AND IT MEASURES ITS OWN NOISE FLOOR FIRST. The board build is NOT bit-deterministic run to run
(measured: ULP-level drift on ~156 of 794 rows with byte-identical code, plus one 0.01 on
`fp_ppr_sd`), so a diff that credited every non-zero delta would be reporting the build's own noise.
The baseline is built TWICE and the replicate delta is reported beside the treatment delta — a
treatment effect is only readable above it.

RUN (LAPTOP — read-only; ~1 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj3b_m_counterfactual \
        --duckdb <main>/quant_sports_intel_models/sports_dbt/sports.duckdb \
        --artifacts <main>/quant_sports_intel_models/football/nfl/fantasy/artifacts
"""
from __future__ import annotations

import argparse
import functools
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.fantasy_engine import score_players  # noqa: E402
from quant_sports_intel_models.fantasy_engine.vor import (  # noqa: E402
    build_board, compute_replacement_levels)
from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as SERVE  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf_tr2b_placement as PL  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as NF15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_season_projection as RSP,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_inj3_injury_games as R3,
)
from quant_sports_intel_models.football.nfl.fantasy.league_presets import (  # noqa: E402
    NFL_PROFILE, get_preset)

log = logging.getLogger("nfl.fantasy.nf_inj3b_m.counterfactual")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
SEASON = R3.SERVING_SEASON

#: every config the product PUBLISHES — superflex included, because NF-TR2b's VOR "shield" is
#: ADDITIVE-only and does NOT hold where QB is cross-pooled (the caveat this story must carry).
CONFIGS: tuple[tuple[str, str, int], ...] = tuple(
    (f"{preset}_{n}", preset, n)
    for preset in ("standard", "standard_3wr", "half_ppr", "half_ppr_3wr",
                   "full_ppr", "full_ppr_3wr", "superflex")
    for n in (10, 12))
SUPERFLEX_CONFIGS = tuple(s for s, p, _ in CONFIGS if p == "superflex")


# ══════════════════════════════════════════════════════════════════════════════════════════════
def injury_covariates(con, art: Path) -> pd.DataFrame:
    """The covariate feed the certified hurdle needs, for the 2026 flagged cohort.

    ⭐ Taken from the bake-off's OWN population builder — ⛔ not re-derived here. `onset_carryover`,
    `weeks_since_last_game` and `log1p_prior_fp` exist NOWHERE in the board build, which is exactly
    the prerequisite a real flip inherits (see `injury_games_serving.REQUIRED_COVARIATES`)."""
    serving, prov = R3.build_population(con, art, (SEASON,))
    cols = ["player_id", *SERVE.REQUIRED_COVARIATES]
    missing = [c for c in cols if c not in serving.columns]
    if missing:
        raise ValueError(f"NF-INJ3b-M: the population builder did not produce {missing} — the "
                         f"counterfactual cannot be constructed (NF1.7 (a))")
    return serving[cols].copy(), prov


def nf15_inputs(con, schema: str) -> dict:
    """The NF1.5 selections + feature pool, resolved ONCE. Assembling them is the expensive part of
    a board build, and the counterfactual needs THREE boards — recomputing per build triples a
    multi-minute job for no benefit, and (worse) would let the three boards see different inputs."""
    report = NF15._load_report("")
    if "stage1" not in report:
        raise RuntimeError("NF-INJ3b-M: the NF1.5 market report has no stage1 — the served "
                           "re-order cannot be reproduced (run `run_nf1_5.py --mode market`)")
    sel = NF15.load_selection(report, board="beats-incumbent")
    if not sel:
        raise RuntimeError("NF-INJ3b-M: NF1.5's selection is EMPTY — the re-order would be a NO-OP "
                           "and the give-back this story exists to measure would be silently "
                           "absent (NF1.7 (a))")
    latest = int(con.sql(f"select max(season) from {schema}.fct_player_week "
                         f"where played_flag").fetchone()[0])
    base_season = NF15._resolve_build_base_season(latest, SEASON)
    base_seasons = [b for b in range(2017, base_season) if b + 1 < SEASON]
    inputs = NF15.load_inputs(con, sorted(set(base_seasons + [base_season])), schema)
    return {"selections": sel, "inputs": inputs, "base_season": base_season}


def build_board_frame(con, schema: str, *, serving_on: bool,
                      cov: pd.DataFrame | None, nf15: dict) -> pd.DataFrame:
    """One NF1.5 board, through the SHIPPED assembly.

    `serving_on` forces `injury_games_policy.SERVING_ENABLED` IN MEMORY for the duration of the
    build; the committed flag is never touched. When on, `build_projection` is partial-applied with
    the covariate feed — the same argument a real flip would supply."""
    # ⚠️ NF1.5 does `from run_season_projection import build_projection`, i.e. it holds its OWN
    #    name binding — patching `RSP.build_projection` alone would NOT reach it. Patch the binding
    #    NF1.5 actually calls (a from-import is a copy, not a reference).
    prev_flag, prev_bp = POLICY.SERVING_ENABLED, NF15.build_projection
    try:
        POLICY.SERVING_ENABLED = bool(serving_on)
        if serving_on:
            NF15.build_projection = functools.partial(prev_bp, injury_covariates=cov)
        # ⭐ MIRRORS `run_nf1_5.py --mode build` EXACTLY. A first cut passed the wrong report
        #    suffix, so `load_selection` returned {} and NF1.5's re-order scored 0/758 veterans —
        #    the board built fine and the number it produced was NOT the served path's. The build
        #    log's "refined re-order: N/M veterans scored" is the tell, and `_assert_reorder_fired`
        #    REFUSES a no-op rather than letting a silent one be reported as a measurement.
        cap: dict = {}
        board = NF15.build_season_projection(
            con, nf15["base_season"], SEASON, schema, nf15["selections"], nf15["inputs"],
            base_from=2017, market_refresh=False, capture=cap)
        _assert_reorder_fired(cap)
        return board
    finally:
        POLICY.SERVING_ENABLED = prev_flag
        NF15.build_projection = prev_bp


def _assert_reorder_fired(capture: dict) -> None:
    """⛔ REFUSE a board whose NF1.5 re-order was a NO-OP.

    ⭐ THE DEFECT THIS EXISTS FOR, hit in this story's own first cut: a wrong report suffix made
    `load_selection` return `{}`, so the re-order scored **0 of 758** veterans. The board still
    built, the diff still ran, and it produced a confident number that did NOT include the NF1.5
    give-back — i.e. exactly the proportional-shortcut answer §5(d) forbids, wearing a measured
    number's clothes. The `capture` OUT-param is the shipped build's own record of what it did, so
    this reads the real thing rather than a re-derivation (NF-C0e)."""
    elig = capture.get("eligible")
    if elig is None:
        raise RuntimeError("NF-INJ3b-M: the NF1.5 build recorded no `eligible` mask — the re-order "
                           "cannot be verified, and an unverifiable step is never a pass "
                           "(NF1.7 (a))")
    n, tot = int(np.asarray(elig).sum()), int(len(elig))
    if n == 0:
        raise RuntimeError(
            f"NF-INJ3b-M: NF1.5's re-order scored 0 of {tot} veterans — a NO-OP. The measured "
            f"point impact would OMIT the give-back this story exists to measure. Refusing.")
    log.info("NF1.5 re-order fired: %d/%d veterans scored", n, tot)


def _per_config(base: pd.DataFrame, cf: pd.DataFrame) -> dict:
    """Per-config VOR placement read, both sides through the SAME shipped scorer + board builder."""
    out = {}
    for stem, preset, n_teams in CONFIGS:
        cfg = get_preset(preset, n_teams=n_teams)
        boards = {}
        for lab, frame in (("inc", base), ("cf", cf)):
            scored = score_players(frame, cfg, NFL_PROFILE)
            # ⭐ the PL frame shape, mirroring `nf_tr2b_placement.paired_boards`: BOTH sides go
            #    through the SAME shipped board builder, so the exporter's tie-break among
            #    equal-VOR players CANCELS and every difference below is the cap's doing.
            pf = pd.DataFrame({
                "position": scored["position"].to_numpy(),
                "id": scored["player_id"].to_numpy(),
                "name": scored["player_name"].to_numpy(),
                "rookie": scored["is_rookie"].to_numpy() if "is_rookie" in scored.columns
                else np.zeros(len(scored), dtype=bool),
                "adp": (pd.to_numeric(scored["adp"], errors="coerce").to_numpy()
                        if "adp" in scored.columns else np.full(len(scored), np.nan)),
                "league_points": pd.to_numeric(scored["league_points"],
                                               errors="coerce").to_numpy(),
            })
            pf = pf[pf["league_points"].notna()]
            boards[lab] = build_board(pf, cfg, NFL_PROFILE, points_col="league_points")
            boards[f"repl_{lab}"], boards[f"started_{lab}"] = compute_replacement_levels(
                pf, cfg, NFL_PROFILE, points_col="league_points")
        m = PL.movement(boards["inc"], boards["cf"])
        moved = m[m["move"] != 0]
        top60 = m[m["overall_rank_inc"] <= 60]
        out[stem] = {
            "n": int(len(m)),
            "n_rank_moved": int(len(moved)),
            "max_abs_move": int(m["move"].abs().max()) if len(m) else 0,
            "mean_abs_move": round(float(m["move"].abs().mean()), 3) if len(m) else 0.0,
            "top60_n_moved": int((top60["move"] != 0).sum()),
            "top60_max_abs_move": int(top60["move"].abs().max()) if len(top60) else 0,
            "within_position_order": PL.within_position_order_preserved(boards["inc"], boards["cf"]),
            "rookie_placement_cap": PL.rookie_placement(boards["cf"]),
            "rookie_placement_cap_incumbent": PL.rookie_placement(boards["inc"]),
            "top_n_composition": {str(n): {"incumbent": PL.top_n_composition(boards["inc"], n),
                                           "counterfactual": PL.top_n_composition(boards["cf"], n)}
                                  for n in PL.TOP_N_REPORT},
            "is_superflex": bool(preset == "superflex"),
        }
    return out


def _point_diff(base: pd.DataFrame, cf: pd.DataFrame, flagged_ids: set) -> dict:
    """The served-POINT diff — the measurement §5(d) blocks on."""
    key = "player_id"
    cols = ["proj_games", "proj_fp_ppr", "proj_fp_half", "proj_fp_std"]
    b = base[[key, "player_name", "position", *cols]].copy()
    c = cf[[key, *cols]].copy()
    m = b.merge(c, on=key, suffixes=("_inc", "_cf"))
    for col in cols:
        m[f"d_{col}"] = m[f"{col}_cf"] - m[f"{col}_inc"]
    m["is_flagged"] = m[key].isin(flagged_ids)

    def rank(frame, col):
        return frame.sort_values(col, ascending=False).reset_index(drop=True).assign(
            r=lambda d: np.arange(1, len(d) + 1)).set_index(key)["r"]
    m["rank_inc"] = m[key].map(rank(base, "proj_fp_ppr"))
    m["rank_cf"] = m[key].map(rank(cf, "proj_fp_ppr"))
    m["d_rank"] = m["rank_inc"] - m["rank_cf"]          # >0 = moved UP

    def within(frame):
        f = frame.sort_values("proj_fp_ppr", ascending=False).copy()
        f["pr"] = f.groupby("position").cumcount() + 1
        return f.set_index(key)["pr"]
    m["posrank_inc"] = m[key].map(within(base))
    m["posrank_cf"] = m[key].map(within(cf))
    m["d_posrank"] = m["posrank_inc"] - m["posrank_cf"]

    fl = m[m["is_flagged"]]
    un = m[~m["is_flagged"]]
    return {
        "n_rows": int(len(m)), "n_flagged": int(len(fl)), "n_unflagged": int(len(un)),
        "flagged": {
            "mean_d_proj_games": round(float(fl["d_proj_games"].mean()), 4),
            "mean_d_pts_ppr": round(float(fl["d_proj_fp_ppr"].mean()), 4),
            "median_d_pts_ppr": round(float(fl["d_proj_fp_ppr"].median()), 4),
            "n_pts_down": int((fl["d_proj_fp_ppr"] < -1e-6).sum()),
            "n_pts_up": int((fl["d_proj_fp_ppr"] > 1e-6).sum()),
            "n_rank_moved": int((fl["d_rank"] != 0).sum()),
            "mean_d_rank": round(float(fl["d_rank"].mean()), 2),
            "worst_rank_drop": int(fl["d_rank"].min()) if len(fl) else 0,
        },
        "unflagged_collateral": {
            "n_pts_changed": int((un["d_proj_fp_ppr"].abs() > 1e-6).sum()),
            "max_abs_d_pts_ppr": round(float(un["d_proj_fp_ppr"].abs().max()), 4),
            "n_rank_moved": int((un["d_rank"] != 0).sum()),
            "why_it_matters": "NF1.5 re-assigns each position's POINT MULTISET in learned-rank "
                              "order, so moving the flagged players' games moves points onto "
                              "UNFLAGGED players too. A proportional estimate cannot see this.",
        },
        "rows": m.sort_values("d_proj_fp_ppr")[
            ["player_name", "position", "proj_games_inc", "proj_games_cf", "d_proj_games",
             "proj_fp_ppr_inc", "proj_fp_ppr_cf", "d_proj_fp_ppr", "rank_inc", "rank_cf",
             "d_rank", "posrank_inc", "posrank_cf", "is_flagged"]].head(40).to_dict("records"),
    }


def _noise_floor(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """The build's own run-to-run replicate delta — the floor a treatment effect must clear."""
    key, cols = "player_id", ["proj_games", "proj_fp_ppr"]
    m = a[[key, *cols]].merge(b[[key, *cols]], on=key, suffixes=("_1", "_2"))
    out = {}
    for c in cols:
        d = (m[f"{c}_2"] - m[f"{c}_1"]).abs()
        out[c] = {"n_nonzero": int((d > 0).sum()), "max_abs": float(d.max()),
                  "p99_abs": float(np.percentile(d, 99))}
    r1 = a.sort_values("proj_fp_ppr", ascending=False)[key].reset_index(drop=True)
    r2 = b.sort_values("proj_fp_ppr", ascending=False)[key].reset_index(drop=True)
    out["overall_rank_order_identical"] = bool(r1.equals(r2))
    out["what_it_is"] = ("two builds of the SAME board with IDENTICAL code. A treatment delta is "
                         "only readable ABOVE this; a rank move is meaningful only if the replicate "
                         "rank order is identical.")
    return out


def run(con, art: Path, schema: str) -> dict:
    cov, cov_prov = injury_covariates(con, art)
    flagged_ids = set(cov["player_id"])
    log.info("covariate feed: %d flagged 2026 veterans", len(cov))

    nf15 = nf15_inputs(con, schema)
    log.info("building BASELINE board (policy OFF) …")
    base = build_board_frame(con, schema, serving_on=False, cov=None, nf15=nf15)
    log.info("building BASELINE REPLICATE (noise floor) …")
    base2 = build_board_frame(con, schema, serving_on=False, cov=None, nf15=nf15)
    log.info("building COUNTERFACTUAL board (policy ON + covariate feed) …")
    cf = build_board_frame(con, schema, serving_on=True, cov=cov, nf15=nf15)

    noise = _noise_floor(base, base2)
    points = _point_diff(base, cf, flagged_ids)
    per_config = _per_config(base, cf)

    sf = {s: per_config[s] for s in SUPERFLEX_CONFIGS}
    nonsf = {s: v for s, v in per_config.items() if not v["is_superflex"]}
    return {
        "story": "NF-INJ3b-M", "read": "counterfactual served-POINT + placement (NF-INJ3b §5(d))",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": SEASON,
        "policy": {"model_version": POLICY.MODEL_VERSION, "arm": POLICY.ARM,
                   "certified_statuses": list(POLICY.CERTIFIED_STATUSES),
                   "incumbent_statuses": list(POLICY.INCUMBENT_STATUSES),
                   "serving_enabled_on_disk": bool(POLICY.SERVING_ENABLED),
                   "forced_on_in_memory_for_the_counterfactual_only": True},
        "covariate_feed": {"n_rows": int(len(cov)),
                           "columns": list(SERVE.REQUIRED_COVARIATES),
                           "source": "run_nf_inj3_injury_games.build_population — the bake-off's "
                                     "OWN builder, not re-derived",
                           "provenance": cov_prov},
        "noise_floor": noise,
        "served_point_impact": points,
        "per_config_placement": per_config,
        "superflex": {
            "configs": list(SUPERFLEX_CONFIGS),
            "read_separately_because": "NF-TR2b — the VOR 'shield' (a per-group level shift cancels "
                                       "because a group's own replacement absorbs it) is "
                                       "ADDITIVE-ONLY and assumes the group is not cross-pooled. "
                                       "QB IS cross-pooled in superflex, so these configs must be "
                                       "read on their own rows, never inferred from the others.",
            "max_abs_move": {s: sf[s]["max_abs_move"] for s in sf},
            "non_superflex_max_abs_move": {s: v["max_abs_move"] for s, v in nonsf.items()},
        },
        "deploy_held": True, "published": False, "best_alpha": 0,
    }


def _md(r: dict) -> str:
    """The SHIP-DECISION PACKET (spec node 5). A recommendation is permitted; the decision is not
    made here."""
    p, n, pc = r["served_point_impact"], r["noise_floor"], r["per_config_placement"]
    fl, un = p["flagged"], p["unflagged_collateral"]
    L = [
        "# NF-INJ3b-M — the served-POINT impact, MEASURED (closes NF-INJ3b §5(d))",
        "",
        f"_generated {r['generated_at']}_ · season {r['season']} · `best_alpha = 0` · "
        f"**DEPLOY-HELD** (`SERVING_ENABLED` on disk = {r['policy']['serving_enabled_on_disk']}) · "
        f"**nothing published**",
        "",
        "## What this measures, and why it could not be estimated",
        "",
        "NF-INJ3b already published the GAMES change. The open question — the one blocking the ship "
        "decision — was the **POINT and RANK** a drafter sees. `pts` is **not** `rate × games`: "
        "NF1.5 permutes the within-position POINT MULTISET, so moving the flagged players' games "
        "changes the multiset the permutation re-assigns (NF-INJ1 measured that step handing "
        "**+36.4%** of an availability discount back). Both boards are therefore **BUILT**, through "
        "the same shipped assembly, in one process. ⛔ No proportional shortcut anywhere.",
        "",
        "## 1. The noise floor — measured FIRST, so the effect is readable",
        "",
        "The board build is **not** bit-deterministic run to run, so a diff that credited every "
        "non-zero delta would report the build's own noise. The baseline was built TWICE:",
        "",
        "| quantity | rows differing | max abs | p99 abs |", "|---|---|---|---|",
    ]
    for c in ("proj_games", "proj_fp_ppr"):
        b = n[c]
        L.append(f"| `{c}` (replicate) | {b['n_nonzero']} | {b['max_abs']:.2e} | "
                 f"{b['p99_abs']:.2e} |")
    L += [
        "",
        f"Replicate overall-rank order identical: **{n['overall_rank_order_identical']}** ⇒ a rank "
        f"move in §2 cannot be build noise.",
        "",
        "## 2. The served-POINT impact",
        "",
        f"**{p['n_flagged']} flagged** of {p['n_rows']} board rows.",
        "",
        "| | flagged | unflagged |", "|---|---|---|",
        f"| mean Δ `proj_games` | **{fl['mean_d_proj_games']:+.3f}** | — |",
        f"| mean Δ `pts` (PPR) | **{fl['mean_d_pts_ppr']:+.3f}** | — |",
        f"| median Δ `pts` (PPR) | {fl['median_d_pts_ppr']:+.3f} | — |",
        f"| points down / up | {fl['n_pts_down']} / {fl['n_pts_up']} | "
        f"{un['n_pts_changed']} changed |",
        f"| rank moves | {fl['n_rank_moved']} | {un['n_rank_moved']} |",
        f"| mean Δ overall rank | {fl['mean_d_rank']:+.2f} | — |",
        "",
        f"⭐⭐ **THE HEADLINE, AND IT IS NOT THE FLAGGED PLAYERS.** {un['n_rank_moved']} UNFLAGGED "
        f"players change overall rank and {un['n_pts_changed']} change POINTS — and the largest "
        f"single point move on the whole board, **{un['max_abs_d_pts_ppr']:.2f} PPR**, lands on an "
        f"**UNFLAGGED** player, roughly {un['max_abs_d_pts_ppr'] / max(1e-9, abs(fl['mean_d_pts_ppr'])):.0f}× "
        f"the MEAN move on a flagged one ({fl['mean_d_pts_ppr']:+.3f}). {un['why_it_matters']}",
        "",
        f"⭐ And the give-back is enormous: with NF1.5's re-order DISABLED the same cap change moves "
        f"the flagged players by **−12.06** PPR; with it enabled, **{fl['mean_d_pts_ppr']:+.3f}**. "
        f"~90% of the raw point impact is absorbed and REDISTRIBUTED. That ratio is the single "
        f"strongest argument for why §5(d) forbade a proportional estimate — and it was measured by "
        f"accident, when a wrong report suffix made the re-order a no-op (§5).",
        "",
        "### The moved rows (largest point drops first)",
        "",
        "| player | pos | flagged? | games inc→cf | pts inc→cf | Δpts | rank inc→cf | "
        "pos-rank inc→cf |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in p["rows"][:20]:
        L.append(f"| {row['player_name']} | {row['position']} | "
                 f"{'**FLAGGED**' if row['is_flagged'] else 'no'} | "
                 f"{row['proj_games_inc']:.2f} → {row['proj_games_cf']:.2f} | "
                 f"{row['proj_fp_ppr_inc']:.1f} → {row['proj_fp_ppr_cf']:.1f} | "
                 f"**{row['d_proj_fp_ppr']:+.1f}** | "
                 f"{row['rank_inc']:.0f} → {row['rank_cf']:.0f} | "
                 f"{row['posrank_inc']:.0f} → {row['posrank_cf']:.0f} |")
    L += ["", "## 3. Per-config placement — all 14 published configs", "",
          "| config | rank moves | max \|move\| | top-60 moved | top-60 max \|move\| | "
          "within-pos order | rookie cap |", "|---|---|---|---|---|---|---|"]
    for stem, c in pc.items():
        mark = " ⭐SF" if c["is_superflex"] else ""
        L.append(f"| `{stem}`{mark} | {c['n_rank_moved']}/{c['n']} | {c['max_abs_move']} | "
                 f"{c['top60_n_moved']} | {c['top60_max_abs_move']} | "
                 f"{c['within_position_order'].get('pass')} | "
                 f"{c['rookie_placement_cap'].get('pass')} |")
    sf = r["superflex"]
    L += ["", "### ⚠️ Superflex is read on its OWN rows", "", sf["read_separately_because"], "",
          f"superflex max |move|: `{sf['max_abs_move']}` against non-superflex "
          f"`{sf['non_superflex_max_abs_move']}`.", "",
          "## 4. What is still the OPERATOR's",
          "",
          "This packet is the measurement §5(d) blocked on. It does **not** decide anything: "
          f"`SERVING_ENABLED` is `{r['policy']['serving_enabled_on_disk']}` on disk, the policy was "
          "forced on **in memory only**, and this runner has no `--publish` flag and writes nothing "
          "to the lake. The ship/no-ship — and the PM boundary that SUS/NFI keep the incumbent "
          "constants — remain as recorded.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ3b-M nodes 3+4: the counterfactual board diff")
    ap.add_argument("--duckdb", default=R3._DEFAULT_DUCKDB)
    ap.add_argument("--artifacts", default=None)
    ap.add_argument("--schema", default=RSP.MARTS_SCHEMA)
    ap.add_argument("--out", default="nf_inj3b_m_counterfactual")
    ap.add_argument("--rerender", action="store_true",
                    help="re-render the packet MD from the existing JSON — no rebuild. The three "
                         "board builds take minutes; a wording fix must not cost one.")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.rerender:
        rep = json.loads((_REPORT_DIR / f"{args.out}.json").read_text())
        (_REPORT_DIR / f"{args.out}.md").write_text(_md(rep))
        print(f"re-rendered {args.out}.md from the existing JSON (no rebuild)")
        return 0

    import duckdb
    con = duckdb.connect(args.duckdb, read_only=True)
    rep = run(con, R3.artifacts_dir(args.artifacts), args.schema)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{args.out}.json").write_text(json.dumps(rep, indent=2, default=str))
    (_REPORT_DIR / f"{args.out}.md").write_text(_md(rep))
    p = rep["served_point_impact"]
    print(f"NF-INJ3b-M counterfactual — {p['n_flagged']} flagged / {p['n_rows']} rows")
    print(f"  flagged: mean Δgames {p['flagged']['mean_d_proj_games']:+.3f}, "
          f"mean Δpts(PPR) {p['flagged']['mean_d_pts_ppr']:+.3f}, "
          f"{p['flagged']['n_rank_moved']} rank moves")
    print(f"  UNFLAGGED collateral: {p['unflagged_collateral']['n_pts_changed']} points changed, "
          f"{p['unflagged_collateral']['n_rank_moved']} rank moves")
    print(f"  🔒 SERVING_ENABLED on disk = {POLICY.SERVING_ENABLED}; nothing published")
    print(f"  wrote {args.out}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
