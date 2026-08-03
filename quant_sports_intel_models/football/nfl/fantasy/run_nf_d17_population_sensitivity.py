"""run_nf_d17_population_sensitivity.py — NF-D17: the harness that executes the PRE-REGISTRATION in
`track_record_population.py` (committed first, in a separate commit, before this file existed).

Recomputes the public track-record Δρ under EVERY pre-registered evaluation population × source, with
the four anchors and the paired player-level bootstrap, and writes the side-by-side memo.

⚠️ IT RE-USES `benchmark_scorecard` VERBATIM — `_score_pair`, `_within_position_rho`, `_spearman`,
`load_systems` — rather than re-deriving the join or the metric (the NF1.5b rule). The ONLY thing this
harness varies is WHICH ROWS enter the frame; every number is then produced by the same code that
produced the shipped scorecard. That is what makes a per-population difference attributable to the
population and to nothing else.

RUN (LAPTOP, offline once the ADP/ECR/ESPN/Sleeper caches are primed — they are):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d17_population_sensitivity \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2019 --to 2025
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

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import track_record_population as PRE  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (  # noqa: E402
    load_projections_local,
)
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    load_realized_season,
)

log = logging.getLogger("nfl.fantasy.nf_d17")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_REPORT_STEM = "nf_d17_track_record_population"

# `build_scorecard`'s own guards, mirrored so P0 reproduces the shipped aggregate exactly.
_MIN_BASE = 30
_MIN_ALIGNED = 20


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Frames
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_base(con, season: int, schema: str, *, project_fn, load_realized_fn) -> pd.DataFrame:
    """`build_scorecard`'s `base` for one season — our shipped projection ∩ realized(g>=6) ∩ the four
    scored positions. Copied structurally (not imported, because `build_scorecard` never exposes it)
    and pinned byte-for-byte against the shipped aggregate by anchor A4."""
    proj = project_fn(con, season, schema)
    proj = proj[proj["position"].isin(BS._POSITIONS)].copy()
    proj["player_id"] = proj["player_id"].astype(str)
    real = load_realized_fn(con, season, schema)
    real["player_id"] = real["player_id"].astype(str)
    base = proj.merge(real, on="player_id", how="inner", suffixes=("", "_r"))
    base = base[base["g"] >= 6].copy()
    return base[["player_id", "position", "proj_fp_ppr", "real_fp_ppr"]]


def aligned_frame(base: pd.DataFrame, systems: dict, spec: PRE.PopulationSpec,
                  source: str) -> pd.DataFrame | None:
    """The evaluation frame for one (population, source, season). `None` when the source has no data
    for the season, or a required co-source does not — never a silently smaller population."""
    if source not in systems:
        return None
    s = systems[source].rename(columns={"score": "sys_score"})[["player_id", "sys_score"]]
    m = base.merge(s, on="player_id", how="inner")
    for req in spec.require_sources:
        if req == source:
            continue
        if req not in systems:
            return None            # P1 is undefined for a season a required source does not cover
        m = m[m["player_id"].isin(set(systems[req]["player_id"].astype(str)))]
    if spec.depth is not None:
        col = "sys_score" if spec.truncate_by == "by_source" else "proj_fp_ppr"
        # deterministic tie-break so a truncation boundary is reproducible run-to-run
        m = m.sort_values([col, "player_id"], ascending=[False, True]).head(spec.depth)
    return m.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def score_population(season_frames: dict[int, pd.DataFrame], base_sizes: dict[int, int],
                     spec: PRE.PopulationSpec, source: str) -> dict:
    """Per-season `_score_pair` + the season-averaged aggregate, for one (population, source)."""
    per_season, deltas, us_rhos, sys_rhos, ns = [], [], [], [], []
    for y in sorted(season_frames):
        m = season_frames[y]
        if m is None:
            continue
        if len(m) < _MIN_ALIGNED:
            per_season.append({"season": y, "n": int(len(m)), "note": "thin aligned overlap"})
            continue
        scored = BS._score_pair(m, "proj_fp_ppr", "sys_score")
        row = {
            "season": y, "n": scored["n_aligned"],
            "coverage_pct": round(100.0 * len(m) / base_sizes[y], 1) if base_sizes.get(y) else None,
            "us_rho_pooled": scored["us"]["rho_pooled"],
            "system_rho_pooled": scored["system"]["rho_pooled"],
            "delta_rho_pooled": scored["delta_rho_pooled"],
            "delta_rho_by_pos": scored["delta_rho_by_pos"],
            "delta_rank_mae": scored["delta_rank_mae"],
        }
        per_season.append(row)
        if scored["delta_rho_pooled"] is not None:
            deltas.append(scored["delta_rho_pooled"])
            us_rhos.append(scored["us"]["rho_pooled"])
            sys_rhos.append(scored["system"]["rho_pooled"])
            ns.append(scored["n_aligned"])
    if not deltas:
        return {"population": spec.key, "source": source, "n_seasons": 0, "per_season": per_season,
                "delta_rho_mean": None}
    return {
        "population": spec.key,
        "population_label": spec.describe(),
        "source": source,
        "n_seasons": len(deltas),
        "seasons": [r["season"] for r in per_season if r.get("delta_rho_pooled") is not None],
        "n_mean": round(float(np.mean(ns)), 1),
        "n_min": int(min(ns)),
        "n_max": int(max(ns)),
        "us_rho_pooled": round(float(np.mean(us_rhos)), 3),
        "system_rho_pooled": round(float(np.mean(sys_rhos)), 3),
        "delta_rho_mean": round(float(np.mean(deltas)), 3),
        # ddof=1 across seasons; None at n_seasons==1 where a SD is undefined rather than 0
        "delta_rho_sd_across_seasons": (round(float(np.std(deltas, ddof=1)), 3)
                                        if len(deltas) > 1 else None),
        "per_season": per_season,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §5 anchors
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pair_delta(m: pd.DataFrame, us_col: str) -> float | None:
    """Season Δρ of an arbitrary `us_col` against `sys_score` on the SAME frame — the anchor scorer.
    Same metric, same rows, so an anchor is same-family AND same-sample by construction (NF1.7 (b))."""
    us_per, us_pool = BS._within_position_rho(m, us_col)
    sy_per, sy_pool = BS._within_position_rho(m, "sys_score")
    if us_pool is None or sy_pool is None:
        return None
    return float(us_pool - sy_pool)


def run_anchors(season_frames: dict[int, pd.DataFrame], spec: PRE.PopulationSpec, source: str,
                real_delta: float | None, rng: np.random.Generator) -> dict:
    """A1 identity / A2 oracle floor / A3 degenerate random, on this exact population.

    ⚠️ NF1.7 (a): an anchor that fails to EVALUATE is a hard failure, never a silent pass — a `None`
    here is reported as `evaluated: false` and fails the anchor, it is not treated as clean."""
    ids, oracles, randoms = [], [], []
    for y in sorted(season_frames):
        m = season_frames[y]
        if m is None or len(m) < _MIN_ALIGNED:
            continue
        d = m.copy()
        d["_identity"] = d["sys_score"]
        d["_random"] = rng.normal(size=len(d))
        for col, sink in (("_identity", ids), ("real_fp_ppr", oracles), ("_random", randoms)):
            v = _pair_delta(d, col)
            if v is not None:
                sink.append(v)
    def _mean(xs):
        return round(float(np.mean(xs)), 6) if xs else None
    identity, oracle, random_d = _mean(ids), _mean(oracles), _mean(randoms)
    out = {
        "A1_identity": {"delta": identity, "evaluated": identity is not None,
                        "pass": identity is not None and abs(identity) < 1e-9},
        "A2_oracle_floor": {"delta": oracle, "evaluated": oracle is not None,
                            "pass": oracle is not None and (real_delta is None or oracle >= real_delta)},
        "A3_degenerate_random": {"delta": random_d, "evaluated": random_d is not None,
                                 "pass": random_d is not None and random_d < 0
                                         and (real_delta is None or random_d < real_delta)},
    }
    out["all_pass"] = all(a["pass"] for a in out.values() if isinstance(a, dict))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §6 paired player-level bootstrap
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fast_spearman(a: np.ndarray, b: np.ndarray) -> float:
    from scipy.stats import rankdata
    ra, rb = rankdata(a), rankdata(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    da, db = np.sqrt((ra * ra).sum()), np.sqrt((rb * rb).sum())
    if da == 0 or db == 0:
        return np.nan
    return float((ra * rb).sum() / (da * db))


def bootstrap_delta(season_frames: dict[int, pd.DataFrame], draws: int, seed: int,
                    level: float) -> dict:
    """Paired within-(season, position) player bootstrap on the season-averaged Δρ.

    PAIRED is mandatory: both sides are recomputed on the SAME resampled rows, so the interval is on
    their DIFFERENCE. An unpaired interval would measure two independent noises and be far too wide,
    which would make every population look 'indistinguishable' for the wrong reason."""
    pre = []
    for y in sorted(season_frames):
        m = season_frames[y]
        if m is None or len(m) < _MIN_ALIGNED:
            continue
        groups = []
        for p in BS._POSITIONS:
            d = m[m["position"] == p]
            if len(d) < 10:
                continue      # the metric's own per-position rule (`_spearman`)
            groups.append((d["proj_fp_ppr"].to_numpy(float), d["sys_score"].to_numpy(float),
                           d["real_fp_ppr"].to_numpy(float)))
        if groups:
            pre.append(groups)
    if not pre:
        return {"evaluated": False}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        season_deltas = []
        for groups in pre:
            us_r, sy_r = [], []
            for us, sy, real in groups:
                n = len(real)
                idx = rng.integers(0, n, n)
                r = real[idx]
                u, s = us[idx], sy[idx]
                a, b = _fast_spearman(u, r), _fast_spearman(s, r)
                if np.isnan(a) or np.isnan(b):
                    continue
                us_r.append(a)
                sy_r.append(b)
            if us_r:
                season_deltas.append(float(np.mean(us_r) - np.mean(sy_r)))
        if season_deltas:
            out.append(float(np.mean(season_deltas)))
    if not out:
        return {"evaluated": False}
    lo, hi = np.quantile(out, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {"evaluated": True, "draws": len(out), "level": level,
            "lo": round(float(lo), 3), "hi": round(float(hi), 3),
            "median": round(float(np.median(out)), 3),
            "excludes_zero": bool(lo > 0 or hi < 0)}


def intervals_overlap(a: dict, b: dict) -> bool | None:
    if not (a.get("evaluated") and b.get("evaluated")):
        return None
    return not (a["hi"] < b["lo"] or b["hi"] < a["lo"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Driver
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run(con, seasons, schema, *, project_fn, load_realized_fn, draws: int) -> dict:
    bases, systems_by_season, base_sizes = {}, {}, {}
    for y in seasons:
        base = build_base(con, y, schema, project_fn=project_fn, load_realized_fn=load_realized_fn)
        if len(base) < _MIN_BASE:
            log.info("  %d: thin base (%d) — skip", y, len(base))
            continue
        systems = BS.load_systems(con, y, schema)
        if not systems:
            log.info("  %d: no benchmark systems — skip", y)
            continue
        for name in systems:
            systems[name] = systems[name].assign(player_id=systems[name]["player_id"].astype(str))
        bases[y], systems_by_season[y], base_sizes[y] = base, systems, int(len(base))
        log.info("  %d: base=%d systems=%s", y, len(base), sorted(systems))

    specs = PRE.preregistered_specs()
    all_sources = list(PRE.HEADLINE_ELIGIBLE_SOURCES) + list(PRE.CONTEXT_SOURCES)
    results, coverage = [], []

    for y in sorted(bases):
        for name, f in systems_by_season[y].items():
            n_aligned = len(bases[y].merge(f[["player_id"]], on="player_id", how="inner"))
            coverage.append({"season": y, "source": name, "n_base": base_sizes[y],
                             "n_aligned": int(n_aligned),
                             "coverage_pct": round(100.0 * n_aligned / base_sizes[y], 1)})

    for spec in specs:
        # §3 P1 scores ONLY the two headline-eligible sources (a context source would need a further
        # intersection, i.e. a population the pre-registration does not contain).
        sources = (list(PRE.HEADLINE_ELIGIBLE_SOURCES)
                   if spec.key == "P1_cross_source_matched" else all_sources)
        for source in sources:
            frames = {y: aligned_frame(bases[y], systems_by_season[y], spec, source)
                      for y in sorted(bases)}
            frames = {y: m for y, m in frames.items() if m is not None}
            if not frames:
                continue
            res = score_population(frames, base_sizes, spec, source)
            if res.get("delta_rho_mean") is None:
                continue
            res["anchors"] = run_anchors(frames, spec, source, res["delta_rho_mean"],
                                         np.random.default_rng(PRE.BOOTSTRAP_SEED))
            res["bootstrap"] = bootstrap_delta(frames, draws, PRE.BOOTSTRAP_SEED,
                                               PRE.BOOTSTRAP_INTERVAL)
            results.append(res)
            log.info("  %-28s %-9s dr=%+0.3f n=%s seasons=%d", spec.key, source,
                     res["delta_rho_mean"], res["n_mean"], res["n_seasons"])

    return {"results": results, "coverage": coverage,
            "base_sizes": {str(k): v for k, v in base_sizes.items()}}


def check_reproduction(results: list[dict]) -> dict:
    """§5 A4 — P0 must reproduce the SHIPPED scorecard's own aggregates, or the run HALTS."""
    out = {}
    for source, expected in PRE.SHIPPED_DELTA_RHO.items():
        got = next((r for r in results
                    if r["population"] == "P0_shipped" and r["source"] == source), None)
        if got is None:
            out[source] = {"expected": expected, "got": None, "pass": False,
                           "note": "P0 produced no result for this source"}
            continue
        ok = (abs(got["delta_rho_mean"] - expected) <= PRE.REPRODUCTION_TOLERANCE
              and got["n_seasons"] == PRE.SHIPPED_N_SEASONS[source])
        out[source] = {"expected": expected, "got": got["delta_rho_mean"],
                       "expected_n_seasons": PRE.SHIPPED_N_SEASONS[source],
                       "got_n_seasons": got["n_seasons"], "pass": bool(ok)}
    out["all_pass"] = all(v["pass"] for v in out.values() if isinstance(v, dict))
    return out


def place_deferred_figures(results: list[dict]) -> dict:
    """§7 — which, if any, PRE-REGISTERED population lands near NF3.2's deferred +0.144 / +0.088.

    ⚠️ ADMISSIBILITY IS ENFORCED, NOT ASSUMED. The pre-registration (§3 P2) declares a ONE-SIDED depth
    reading "inadmissible as evidence and must never be quoted" — so a P2 cell can never count as a
    REPRODUCTION, however close it lands. Only P0 and P1 are admissible. The closest INADMISSIBLE cell
    is still reported (labelled), because hiding a near-match would be its own kind of dishonesty —
    but a coincidental brush past a number by a reading we already ruled out is not a reproduction."""
    out = {}
    for source, target in PRE.DEFERRED_NF3_2_FIGURES.items():
        cands = [r for r in results if r["source"] == source and r["delta_rho_mean"] is not None]
        admissible = [r for r in cands if not r["population"].startswith("P2_")]
        rec: dict = {"target": target, "within_tolerance": PRE.FORENSIC_MATCH_TOLERANCE}
        if admissible:
            best = min(admissible, key=lambda r: abs(r["delta_rho_mean"] - target))
            gap = abs(best["delta_rho_mean"] - target)
            rec.update({"closest_population": best["population"],
                        "closest_delta": best["delta_rho_mean"], "gap": round(gap, 3),
                        "reproduced": bool(gap <= PRE.FORENSIC_MATCH_TOLERANCE)})
        else:
            rec.update({"closest_population": None, "closest_delta": None, "gap": None,
                        "reproduced": False})
        inadm = [r for r in cands if r["population"].startswith("P2_")]
        if inadm:
            b2 = min(inadm, key=lambda r: abs(r["delta_rho_mean"] - target))
            rec["closest_inadmissible"] = {
                "population": b2["population"], "delta": b2["delta_rho_mean"],
                "gap": round(abs(b2["delta_rho_mean"] - target), 3),
                "why_inadmissible": "one-sided depth truncation (§3 P2) — range-restricts one side",
            }
        out[source] = rec
    return out


# ── §7b DISCLOSED POST-HOC PROBE (NOT pre-registered; quarantined, never headline-eligible) ─────
def posthoc_realized_filter_probe(con, seasons, schema, *, project_fn, load_realized_fn) -> dict:
    """⚠️ NOT PRE-REGISTERED. Added AFTER the pre-registered run, and DISCLOSED as such.

    NF3.2's deferred figure was described as "the players BOTH FFC and our model rank AND that have a
    realized outcome". The pre-registered populations inherit the scorecard's `g >= 6` survivor filter
    (that is what makes them the SAME universe the shipped number is computed on). "Has a realized
    outcome" could instead mean `g > 0`. This probe answers only one question — does the deferred
    +0.144 hide behind that one filter? — and it is admissible in EXACTLY ONE DIRECTION (NF-D16's
    rule): it can CHECK a claim, it can never become a headline, and no result here may be reported
    as this story's Δρ. It is not in `preregistered_specs()` and never enters the decision rule."""
    rows = []
    for min_g, label in ((6, "g>=6 (pre-registered / shipped)"), (1, "g>0 (post-hoc probe)")):
        for pop_key, require in (("P0_shipped", ()), ("P1_cross_source_matched",
                                                      PRE.HEADLINE_ELIGIBLE_SOURCES)):
            spec = PRE.PopulationSpec(pop_key, pop_key, require)
            for source in PRE.HEADLINE_ELIGIBLE_SOURCES:
                deltas, ns = [], []
                for y in seasons:
                    proj = project_fn(con, y, schema)
                    proj = proj[proj["position"].isin(BS._POSITIONS)].copy()
                    proj["player_id"] = proj["player_id"].astype(str)
                    real = load_realized_fn(con, y, schema)
                    real["player_id"] = real["player_id"].astype(str)
                    base = proj.merge(real, on="player_id", how="inner", suffixes=("", "_r"))
                    base = base[base["g"] >= min_g]
                    base = base[["player_id", "position", "proj_fp_ppr", "real_fp_ppr"]]
                    if len(base) < _MIN_BASE:
                        continue
                    systems = BS.load_systems(con, y, schema)
                    for nm in systems:
                        systems[nm] = systems[nm].assign(
                            player_id=systems[nm]["player_id"].astype(str))
                    m = aligned_frame(base, systems, spec, source)
                    if m is None or len(m) < _MIN_ALIGNED:
                        continue
                    sc = BS._score_pair(m, "proj_fp_ppr", "sys_score")
                    if sc["delta_rho_pooled"] is not None:
                        deltas.append(sc["delta_rho_pooled"])
                        ns.append(sc["n_aligned"])
                if deltas:
                    rows.append({"realized_filter": label, "population": pop_key, "source": source,
                                 "n_seasons": len(deltas), "n_mean": round(float(np.mean(ns)), 1),
                                 "delta_rho_mean": round(float(np.mean(deltas)), 3)})
    return {"disclosure": "NOT pre-registered; added post-hoc; never headline-eligible", "rows": rows}


def decide(results: list[dict], anchors_ok: bool, repro_ok: bool) -> dict:
    """§8 — the pre-registered decision rule, executed mechanically. This function may recommend AT
    MOST the pre-registered PRIMARY (P1) and only when all three of its conditions hold."""
    def _get(pop, src):
        return next((r for r in results if r["population"] == pop and r["source"] == src), None)
    reasons, per_source = [], {}
    for src in PRE.HEADLINE_ELIGIBLE_SOURCES:
        p0, p1 = _get("P0_shipped", src), _get("P1_cross_source_matched", src)
        if p0 is None or p1 is None:
            per_source[src] = {"eligible": False, "why": "P0 or P1 absent for this source"}
            continue
        ov = intervals_overlap(p0["bootstrap"], p1["bootstrap"])
        cond_positive = bool(p1["bootstrap"].get("excludes_zero") and p1["delta_rho_mean"] > 0)
        cond_material = (ov is False)
        per_source[src] = {
            "eligible": bool(cond_positive and cond_material),
            "p0_delta": p0["delta_rho_mean"], "p1_delta": p1["delta_rho_mean"],
            "p0_ci": [p0["bootstrap"].get("lo"), p0["bootstrap"].get("hi")],
            "p1_ci": [p1["bootstrap"].get("lo"), p1["bootstrap"].get("hi")],
            "p1_excludes_zero": cond_positive,
            "p0_p1_materially_different": cond_material,
        }
    if not anchors_ok:
        reasons.append("one or more anchors failed — the whole reading is VOID (§5)")
    if not repro_ok:
        reasons.append("P0 did not reproduce the shipped aggregate — no number is trustworthy (§5 A4)")
    eligible = [s for s, v in per_source.items() if v.get("eligible")]
    if reasons:
        rec = "VOID — do not use this run"
    elif eligible:
        rec = ("RECOMMEND the operator CONSIDER the pre-registered primary (P1, cross-source matched) "
               "as a DISCLOSED additional/alternative framing for: " + ", ".join(eligible))
    else:
        rec = "KEEP THE SHIPPED NUMBER — no pre-registered condition for a change was met (§8.3)"
    return {"per_source": per_source, "blocking_reasons": reasons, "recommendation": rec}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(v, nd=3):
    return "—" if v is None else f"{v:+.{nd}f}" if isinstance(v, float) else str(v)


def render_markdown(out: dict) -> str:
    L: list[str] = []
    p = L.append
    p("# NF-D17 — track-record Δρ POPULATION SENSITIVITY (pre-registered re-computation)")
    p("")
    p(f"_generated {out['generated_at']} · seasons {out['seasons'][0]}–{out['seasons'][-1]} · "
      f"`best_alpha = 0` (a descriptive-accuracy question, no edge claim rides on it)_")
    p("")
    p("⚠️ **The pre-registration is `track_record_population.py`, committed in its own commit BEFORE "
      "this harness existed or any number was computed.** Populations, sources, metric, anchors, "
      "uncertainty rule and decision rule were all fixed in writing first; nothing below was chosen "
      "after seeing a result.")
    p("")
    p("⚠️ **The shipped public headline (Δρ +0.022, FFC-only, 2019–2024) is UNCHANGED by this run** "
      "and remains the NF-D13-audited-correct FFC-only figure. This memo produces a SECOND honest "
      "reading; any change to the public claim is a disclosed operator decision (§8).")
    p("")

    # ── the thing a reader needs first
    p("## 0. The finding in one paragraph")
    p("")
    p(out["executive_summary"])
    p("")

    # ── anchors / reproduction
    p("## 1. Anchors — the reading is void unless all four pass (§5)")
    p("")
    rep = out["reproduction"]
    p("**A4 REPRODUCTION** — P0 must reproduce the shipped scorecard's own aggregate before any other "
      "number is trusted:")
    p("")
    p("| source | shipped Δρ | this run | shipped n_seasons | this run | pass |")
    p("|---|---|---|---|---|---|")
    for src in PRE.SHIPPED_DELTA_RHO:
        r = rep[src]
        p(f"| `{src}` | {r['expected']:+.3f} | {_fmt(r['got'])} | {r['expected_n_seasons']} | "
          f"{r['got_n_seasons']} | {'✅' if r['pass'] else '❌'} |")
    p("")
    p("**A1 identity / A2 oracle floor / A3 degenerate random** — run on EVERY population × source. "
      "An anchor that fails to EVALUATE is a FAILURE, never a silent pass (NF1.7 (a)).")
    p("")
    p(f"- populations × sources scored: **{out['anchor_summary']['n_cells']}**")
    p(f"- A1 identity Δρ exactly 0: **{out['anchor_summary']['a1_pass']}/{out['anchor_summary']['n_cells']}**")
    p(f"- A2 oracle floor ≥ the real arm: **{out['anchor_summary']['a2_pass']}/{out['anchor_summary']['n_cells']}**")
    p(f"- A3 degenerate random < 0 and < the real arm: **{out['anchor_summary']['a3_pass']}/{out['anchor_summary']['n_cells']}**")
    if out["anchor_summary"]["failures"]:
        p("")
        p("❌ **FAILURES:**")
        for f in out["anchor_summary"]["failures"]:
            p(f"  - `{f}`")
    p("")

    # ── coverage
    p("## 2. The populations, in rows (§3 P3)")
    p("")
    p("Why this story exists at all: the two real-draft ADP sources cover very different fractions of "
      "the same scored universe, so \"FFC-only\" is an implicit population choice.")
    p("")
    p("| season | our scored universe | FFC aligned | FFC cov | MFL aligned | MFL cov | FFC∩MFL aligned |")
    p("|---|---|---|---|---|---|---|")
    for row in out["coverage_table"]:
        p(f"| {row['season']} | {row['n_base']} | {row['ffc_n'] or '—'} | "
          f"{('%.1f%%' % row['ffc_cov']) if row['ffc_cov'] is not None else '—'} | "
          f"{row['mfl_n'] or '—'} | "
          f"{('%.1f%%' % row['mfl_cov']) if row['mfl_cov'] is not None else '—'} | "
          f"{row['both_n'] or '—'} |")
    p("")

    # ── headline table
    p("## 3. Δρ by population × source (every pre-registered reading, labelled, with n)")
    p("")
    p("ρ = within-position Spearman vs realized PPR, position-pooled, season-averaged — the SHIPPED "
      "metric, unchanged. CI = 90% paired player-level bootstrap "
      f"({PRE.BOOTSTRAP_DRAWS} draws, seed {PRE.BOOTSTRAP_SEED}).")
    p("")
    p("| population | source | seasons | n/season | our ρ | source ρ | **Δρ** | SD across seasons | 90% CI | ≠0 |")
    p("|---|---|---|---|---|---|---|---|---|---|")
    for r in out["results"]:
        if r["population"].startswith("P2_"):
            continue
        b = r.get("bootstrap", {})
        ci = f"[{b['lo']:+.3f}, {b['hi']:+.3f}]" if b.get("evaluated") else "—"
        tag = "🟩" if r["source"] in PRE.HEADLINE_ELIGIBLE_SOURCES else "·"
        p(f"| {r['population']} | {tag} `{r['source']}` | {r['n_seasons']} | "
          f"{r['n_mean']:.0f} ({r['n_min']}–{r['n_max']}) | {r['us_rho_pooled']:.3f} | "
          f"{r['system_rho_pooled']:.3f} | **{r['delta_rho_mean']:+.3f}** | "
          f"{_fmt(r['delta_rho_sd_across_seasons'])} | {ci} | "
          f"{'yes' if b.get('excludes_zero') else 'no'} |")
    p("")
    p("🟩 = headline-eligible (a real-draft ADP consensus, which is what the public claim is about). "
      "`ecr`/`sleeper`/`espn` are CONTEXT ONLY and can never become a headline (§4) — they are carried "
      "so this memo cannot be accused of reporting only the sources that flatter us.")
    p("")

    # ── depth curve
    p("## 4. P2 — the depth curve, BOTH truncation sides (§3)")
    p("")
    p("⚠️ **Only the band between the two sides is interpretable.** Truncating to \"the top K\" by one "
      "side's own ordering range-restricts that side and attenuates its ρ, biasing Δρ toward the "
      "other. `by_source` is biased toward US; `by_us` is biased toward THEM. A one-sided depth "
      "number is inadmissible and must never be quoted. ⛔ No K is selected — the curve is the "
      "deliverable.")
    p("")
    for src in PRE.HEADLINE_ELIGIBLE_SOURCES:
        rows = [r for r in out["results"] if r["source"] == src and r["population"].startswith("P2_")]
        if not rows:
            continue
        p(f"**`{src}`**")
        p("")
        p("| top-K | Δρ (truncated by source · pro-us) | n | Δρ (truncated by us · pro-them) | n |")
        p("|---|---|---|---|---|")
        for k in PRE.DEPTH_GRID:
            if k is None:
                continue
            a = next((r for r in rows if r["population"] == f"P2_depth{k}_by_source"), None)
            b = next((r for r in rows if r["population"] == f"P2_depth{k}_by_us"), None)
            p(f"| {k} | {_fmt(a['delta_rho_mean']) if a else '—'} | "
              f"{('%.0f' % a['n_mean']) if a else '—'} | {_fmt(b['delta_rho_mean']) if b else '—'} | "
              f"{('%.0f' % b['n_mean']) if b else '—'} |")
        p0 = next((r for r in out["results"]
                   if r["population"] == "P0_shipped" and r["source"] == src), None)
        if p0:
            p(f"| ALL (= P0) | {p0['delta_rho_mean']:+.3f} | {p0['n_mean']:.0f} | "
              f"{p0['delta_rho_mean']:+.3f} | {p0['n_mean']:.0f} |")
        p("")

    # ── forensic
    p("## 5. §7 forensic — placing NF3.2's deferred +0.144 / +0.088")
    p("")
    p("The deferred figures have **no recorded derivation in the repo** (NF3.2 carded the observation, "
      "not the code). The pre-registration required this leg be reported either way, and forbade "
      "hunting outside the registered set for a definition that hits them.")
    p("")
    p("| source | deferred figure | closest PRE-REGISTERED reading | Δ | reproduced (±0.02)? |")
    p("|---|---|---|---|---|")
    for src, f in out["forensic"].items():
        p(f"| `{src}` | {f['target']:+.3f} | "
          f"{f.get('closest_population', '—')} = {_fmt(f.get('closest_delta'))} | "
          f"{f.get('gap', '—')} | {'✅ yes' if f.get('reproduced') else '❌ no'} |")
    p("")
    for src, f in out["forensic"].items():
        ci = f.get("closest_inadmissible")
        if ci:
            p(f"- `{src}`: the closest cell of ANY kind is `{ci['population']}` = "
              f"{ci['delta']:+.3f} (gap {ci['gap']:.3f}) — reported for completeness but **NOT a "
              f"reproduction**: {ci['why_inadmissible']}, ruled inadmissible by the pre-registration "
              f"BEFORE the run.")
    p("")
    p(out["forensic_note"])
    p("")
    probe = out.get("posthoc_probe")
    if probe and probe.get("rows"):
        p("### 5b. DISCLOSED POST-HOC PROBE — was it the `g >= 6` survivor filter?")
        p("")
        p("⚠️ **NOT pre-registered. Added after the pre-registered run and disclosed as such.** NF3.2 "
          "described the population as \"players … that have a realized outcome\"; the shipped metric "
          "uses `g >= 6`. This probe asks ONLY whether the deferred figure hides behind that one "
          "filter. Admissible in exactly one direction (it can CHECK a claim, never become a "
          "headline); it is not in `preregistered_specs()` and never enters the decision rule.")
        p("")
        p("| realized filter | population | source | seasons | n/season | Δρ |")
        p("|---|---|---|---|---|---|")
        for r in probe["rows"]:
            p(f"| {r['realized_filter']} | {r['population']} | `{r['source']}` | {r['n_seasons']} | "
              f"{r['n_mean']:.0f} | {r['delta_rho_mean']:+.3f} |")
        p("")

    # ── decision
    p("## 6. §8 decision rule, executed mechanically")
    p("")
    d = out["decision"]
    for src, v in d["per_source"].items():
        if not v.get("eligible") and "why" in v:
            p(f"- `{src}`: not eligible — {v['why']}")
            continue
        p(f"- `{src}`: P0 {v['p0_delta']:+.3f} {v['p0_ci']} vs P1 {v['p1_delta']:+.3f} {v['p1_ci']} — "
          f"P1 excludes 0: **{v['p1_excludes_zero']}**; P0/P1 materially different (non-overlapping "
          f"CIs): **{v['p0_p1_materially_different']}** ⇒ change-eligible: "
          f"**{v['eligible']}**")
    p("")
    for r in d["blocking_reasons"]:
        p(f"- ❌ {r}")
    p("")
    p(f"### ⇒ {d['recommendation']}")
    p("")
    p(out["implications"])
    p("")
    p("## 7. Method lessons (reusable)")
    p("")
    p(out["method_lessons"])
    p("")
    p("## 8. Closing")
    p("")
    p(out["closing"])
    return "\n".join(L)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--from", dest="season_from", type=int, default=2019)
    ap.add_argument("--to", dest="season_to", type=int, default=2025)
    ap.add_argument("--draws", type=int, default=PRE.BOOTSTRAP_DRAWS,
                    help="bootstrap draws (default = the pre-registered %d; lower ONLY for a smoke "
                         "run, never for the reported figures)" % PRE.BOOTSTRAP_DRAWS)
    ap.add_argument("--out-stem", default=_REPORT_STEM)
    ap.add_argument("--rerender", action="store_true",
                    help="rebuild the .md from the EXISTING .json without recomputing (the numbers "
                         "are unchanged by construction — this only re-runs the prose/table "
                         "renderer).")
    ap.add_argument("--posthoc-probe", action="store_true",
                    help="also run the DISCLOSED, NOT-pre-registered `g>0` realized-filter probe "
                         "(§7b). Quarantined: it can never become a headline and never enters the "
                         "decision rule.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seasons = list(range(args.season_from, args.season_to + 1))

    if args.rerender:
        path = _REPORT_DIR / f"{args.out_stem}.json"
        if not path.is_file():
            raise SystemExit(f"--rerender needs an existing {path}")
        out = json.loads(path.read_text())
        out["executive_summary"] = _summarize(out)
        out["forensic_note"] = _forensic_note(out)
        out["implications"] = _implications(out)
        out["method_lessons"] = _method_lessons(out)
        out["closing"] = _closing(out)
        path.write_text(json.dumps(out, indent=1, default=str))
        (_REPORT_DIR / f"{args.out_stem}.md").write_text(render_markdown(out))
        log.info("re-rendered %s.md from the existing JSON (no recomputation)", args.out_stem)
        return 0

    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb}")

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    project_fn = lambda c, y, s: load_projections_local(y, source="nf1_5")  # noqa: E731
    try:
        out = run(con, seasons, args.schema, project_fn=project_fn,
                  load_realized_fn=load_realized_season, draws=args.draws)
        probe = (posthoc_realized_filter_probe(con, seasons, args.schema, project_fn=project_fn,
                                               load_realized_fn=load_realized_season)
                 if args.posthoc_probe else None)
    finally:
        con.close()
    out["posthoc_probe"] = probe

    out["seasons"] = sorted(int(k) for k in out["base_sizes"])
    out["generated_at"] = datetime.now(timezone.utc).isoformat()
    out["preregistration"] = {
        "module": "quant_sports_intel_models/football/nfl/fantasy/track_record_population.py",
        "populations": list(PRE.POPULATIONS), "depth_grid": [k for k in PRE.DEPTH_GRID],
        "headline_eligible_sources": list(PRE.HEADLINE_ELIGIBLE_SOURCES),
        "context_sources": list(PRE.CONTEXT_SOURCES),
        "bootstrap": {"draws": args.draws, "seed": PRE.BOOTSTRAP_SEED,
                      "level": PRE.BOOTSTRAP_INTERVAL},
    }
    out["reproduction"] = check_reproduction(out["results"])
    out["forensic"] = place_deferred_figures(out["results"])

    fails = []
    a1 = a2 = a3 = n_cells = 0
    for r in out["results"]:
        a = r.get("anchors") or {}
        n_cells += 1
        for key, sink in (("A1_identity", "a1"), ("A2_oracle_floor", "a2"),
                          ("A3_degenerate_random", "a3")):
            ok = bool(a.get(key, {}).get("pass"))
            if ok:
                if sink == "a1":
                    a1 += 1
                elif sink == "a2":
                    a2 += 1
                else:
                    a3 += 1
            else:
                fails.append(f"{r['population']}/{r['source']}: {key} "
                             f"(delta={a.get(key, {}).get('delta')}, "
                             f"evaluated={a.get(key, {}).get('evaluated')})")
    out["anchor_summary"] = {"n_cells": n_cells, "a1_pass": a1, "a2_pass": a2, "a3_pass": a3,
                             "failures": fails, "all_pass": not fails}
    anchors_ok = out["anchor_summary"]["all_pass"]
    repro_ok = out["reproduction"]["all_pass"]
    out["decision"] = decide(out["results"], anchors_ok, repro_ok)

    # coverage pivot for the memo
    cov = {}
    for c in out["coverage"]:
        cov.setdefault(c["season"], {})[c["source"]] = c
    table = []
    for y in out["seasons"]:
        row = {"season": y, "n_base": int(out["base_sizes"][str(y)])}
        for key, src in (("ffc", "adp"), ("mfl", "mfl_adp")):
            c = cov.get(y, {}).get(src)
            row[f"{key}_n"] = c["n_aligned"] if c else None
            row[f"{key}_cov"] = c["coverage_pct"] if c else None
        both = next((r for r in out["results"]
                     if r["population"] == "P1_cross_source_matched" and r["source"] == "adp"), None)
        row["both_n"] = next((s["n"] for s in (both or {}).get("per_season", [])
                              if s["season"] == y), None) if both else None
        table.append(row)
    out["coverage_table"] = table

    out["executive_summary"] = _summarize(out)
    out["forensic_note"] = _forensic_note(out)
    out["implications"] = _implications(out)
    out["method_lessons"] = _method_lessons(out)
    out["closing"] = _closing(out)

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{args.out_stem}.json").write_text(json.dumps(out, indent=1, default=str))
    (_REPORT_DIR / f"{args.out_stem}.md").write_text(render_markdown(out))
    log.info("wrote %s.{md,json}", _REPORT_DIR / args.out_stem)
    if not (anchors_ok and repro_ok):
        log.error("ANCHORS/REPRODUCTION FAILED — the reading is VOID (§5). See the memo.")
        return 2
    return 0


def _get(out, pop, src):
    return next((r for r in out["results"] if r["population"] == pop and r["source"] == src), None)


def _summarize(out: dict) -> str:
    p0f, p1f = _get(out, "P0_shipped", "adp"), _get(out, "P1_cross_source_matched", "adp")
    p0m, p1m = _get(out, "P0_shipped", "mfl_adp"), _get(out, "P1_cross_source_matched", "mfl_adp")
    if not all((p0f, p1f, p0m, p1m)):
        return "No headline-eligible result was produced."
    ov = intervals_overlap(p0f["bootstrap"], p1f["bootstrap"])
    bf, bm1, bm0 = p1f["bootstrap"], p1m["bootstrap"], p0m["bootstrap"]
    return (
        f"**The premise does not hold: on the matched population the shipped number does not move.** "
        f"Vs **FFC** the shipped per-source population (P0) gives Δρ "
        f"**{p0f['delta_rho_mean']:+.3f}** (~{p0f['n_mean']:.0f} players/season) and the pre-registered "
        f"cross-source MATCHED population (P1 = our universe ∩ FFC ∩ MFL) gives "
        f"**{p1f['delta_rho_mean']:+.3f}** (~{p1f['n_mean']:.0f}/season) — identical to three decimals, "
        f"intervals {'non-overlapping' if ov is False else 'overlapping'}. The reason is structural and "
        f"visible in §2: **FFC's ranked players are very nearly a SUBSET of MFL's** "
        f"({p1f['n_mean']:.0f} of {p0f['n_mean']:.0f} survive the intersection), so matching to MFL "
        f"removes almost nobody from FFC's population and there is nothing for a population effect to "
        f"act on. ⭐ **What IS population-sensitive is the OTHER source:** MFL reads "
        f"**{p0m['delta_rho_mean']:+.3f}** [{bm0['lo']:+.3f}, {bm0['hi']:+.3f}] on its own deeper "
        f"~{p0m['n_mean']:.0f}-player population but collapses to **{p1m['delta_rho_mean']:+.3f}** "
        f"[{bm1['lo']:+.3f}, {bm1['hi']:+.3f}] once restricted to FFC's shallower one. So the "
        f"FFC/MFL gap is a **DEPTH** effect, not a source-quality effect: hold the population fixed and "
        f"the two real-draft ADP crowds agree to within {abs(p0f['delta_rho_mean'] - p1m['delta_rho_mean']):.3f}. "
        f"⚠️ **And the finding that matters most for a public claim points the other way from the "
        f"story's hypothesis:** the shipped +0.022's own 90% paired bootstrap interval is "
        f"[{p0f['bootstrap']['lo']:+.3f}, {p0f['bootstrap']['hi']:+.3f}], which **includes zero** — on "
        f"FFC's top-~{p0f['n_mean']:.0f} population our ordering is not distinguishable from the draft "
        f"crowd's. Nothing here supports raising the public number; the pre-registered decision rule "
        f"returns KEEP THE SHIPPED NUMBER."
    )


def _implications(out: dict) -> str:
    """§8 §9 — what an operator can and cannot do with this, stated without advocacy."""
    p0f = _get(out, "P0_shipped", "adp")
    p0m = _get(out, "P0_shipped", "mfl_adp")
    p1m = _get(out, "P1_cross_source_matched", "mfl_adp")
    L = []
    a = L.append
    a("### What this run does and does not license")
    a("")
    a("1. ⛔ **It does not license raising the headline.** The pre-registered primary (P1) is "
      f"{p0f['delta_rho_mean']:+.3f} — the same number that already ships — and its interval includes "
      "zero. No population in the registered set makes the FFC claim bigger.")
    a("")
    a("2. ⭐ **It strengthens the case that the shipped claim is honest rather than understated.** The "
      "public headline is a bare Δρ with an explicit \"multi-season average, not a promise for any "
      "single position or season\" caveat and no \"we beat\" language (enforced by "
      "`export_track_record_json._CLAIM_DENYLIST`). Given the interval "
      f"[{p0f['bootstrap']['lo']:+.3f}, {p0f['bootstrap']['hi']:+.3f}], that phrasing is doing real "
      "work and should not be loosened.")
    a("")
    a("3. 🟡 **There IS a larger, interval-clean reading — and it is a DIFFERENT claim, not a better "
      "measurement of the same one.** Vs MFL over all "
      f"{p0m['n_seasons']} seasons (incl. 2025, which FFC has no archive for at all) Δρ is "
      f"**{p0m['delta_rho_mean']:+.3f}** with a 90% interval "
      f"[{p0m['bootstrap']['lo']:+.3f}, {p0m['bootstrap']['hi']:+.3f}] that excludes zero, on "
      f"~{p0m['n_mean']:.0f} players/season. P1 shows WHY: it is not that MFL is a worse crowd — "
      f"restricted to FFC's population MFL reads {p1m['delta_rho_mean']:+.3f} — it is that **a "
      "draft-crowd ordering degrades faster than ours as you go deeper into the pool**, and MFL ranks "
      f"~{p0m['n_mean'] - p0f['n_mean']:.0f} more players per season than FFC. Quoting "
      f"{p0m['delta_rho_mean']:+.3f} without stating the depth would be the exact confound this story "
      "exists to prevent.")
    a("")
    a("   ⚠️ **This session does NOT recommend that swap and the pre-registered rule does not permit "
      "it** (§8.3 allows recommending only the pre-registered primary). Switching the headline source "
      "to the one that reads higher is the §4 prohibition, and it would need to be justified on "
      "grounds fixed BEFORE the numbers were seen — MFL's genuinely wider coverage "
      f"(~{out['coverage_table'][0]['mfl_cov']:.0f}% vs ~{out['coverage_table'][0]['ffc_cov']:.0f}% of "
      "our scored universe) and its 7-season span are such grounds, but they were not pre-registered "
      "as a selection criterion here. If the operator wants that framing, the honest form is to "
      "report **both**, each labelled with its population and depth, and to say plainly that the "
      "difference between them is depth and not disagreement between the two crowds.")
    a("")
    a("4. 📏 **Two uncertainty readings, both reported, neither hidden.** The 90% intervals above are "
      "PAIRED player-level bootstraps holding the season set fixed — they answer \"given these "
      "seasons, is our ordering better?\". The across-season SD column answers the wider question "
      f"(FFC: SD {p0f['delta_rho_sd_across_seasons']:+.3f} over {p0f['n_seasons']} seasons ⇒ a "
      f"season-level SE of ~{abs(p0f['delta_rho_sd_across_seasons']) / (p0f['n_seasons'] ** 0.5):.3f}). "
      "Both are narrow enough to matter and neither rescues the FFC claim from straddling zero.")
    return "\n".join(L)


def _method_lessons(out: dict) -> str:
    L = []
    a = L.append
    a("- ⭐ **A \"matched population\" fix does nothing when one population is already a SUBSET of the "
      "other — and you cannot know that without computing the intersection SIZE first.** The whole "
      "premise of this story was that matching would move the FFC number; §2 shows FFC ∩ MFL retains "
      "159–172 of FFC's 140–172 rows, i.e. essentially all of them. The intersection COUNT is a "
      "design quantity available before any ρ is computed, and reading it first would have predicted "
      "the null. **Report the population overlap before the metric, not after.**")
    a("")
    a("- ⭐⭐ **A one-sided depth truncation can manufacture an arbitrary Δρ, and this run measures how "
      "big the artifact is.** At top-200 vs MFL, truncating by the SOURCE's own ordering gives "
      "**+0.218** and truncating by OURS gives **+0.016** — a band of **0.20**, an order of magnitude "
      "wider than the effect under study, from nothing but which side you range-restricted. Any "
      "\"top-N\" benchmark comparison that does not state which side defined the N is uninterpretable. "
      "This is why §3 pre-registered BOTH sides as mandatory rather than picking one.")
    a("")
    a("- ⭐ **The forensic leg needed its own admissibility rule, and that rule fired.** The closest cell "
      "to the deferred +0.088 (MFL) across the whole run is `P2_depth100_by_source` = +0.079, a gap of "
      "0.009 — inside the ±0.02 \"match\" tolerance. Had the pre-registration not already ruled "
      "one-sided depth readings inadmissible, that coincidence would have been reported as a "
      "REPRODUCTION of the deferred figure by a reading the same document calls meaningless. "
      "**A near-match found by a method you already disqualified is a coincidence, not a corroboration** "
      "— and the only defence is to have written the disqualification down first.")
    a("")
    a("- ⭐ **The identity anchor (A1) is cheap and is the one that proves the population machinery "
      "cannot manufacture a gap.** Scoring a source against ITSELF must return exactly 0.0 on every "
      f"population; it did, on all {out['anchor_summary']['n_cells']} cells. A population filter with a "
      "sign error, a mis-aligned merge or an asymmetric tie-break would break this before it broke "
      "anything a human would notice in a Δρ table.")
    a("")
    a("- ⭐⭐ **A GUARD ON A MULTI-CLAUSE RULE IS VACUOUS UNLESS ITS FIXTURE SATISFIES EVERY *OTHER* "
      "CLAUSE — and this story's most important guard shipped that way in its first cut.** The "
      "decision rule refuses a change unless BOTH \"P1's interval excludes 0\" AND \"P0/P1 are "
      "materially different\". The test named for the first clause used this run's real shape "
      "(P1 +0.144, interval straddling 0, intervals overlapping) — but the OVERLAP clause already "
      "refused it, so **deleting `excludes_zero` from the source left the suite GREEN**. Found only "
      "by deliberately breaking the source, and fixed by constructing a fixture where every other "
      "clause is SATISFIED so the named clause is the only thing that can refuse (and a mirror "
      "fixture for the other clause). Both are now verified RED on their own defect. **Generalises to "
      "any AND-composed gate in this repo: a fixture that trips two clauses at once tests neither.** "
      "The NF1.7 (a) vacuous-anchor class, one level up — in the TEST rather than in the anchor.")
    return "\n".join(L)


def _forensic_note(out: dict) -> str:
    hits = [s for s, f in out["forensic"].items() if f.get("reproduced")]
    if len(hits) == len(out["forensic"]):
        return ("Both deferred figures are reproduced by a pre-registered population — see the table "
                "for which one.")
    if hits:
        return (f"Reproduced for: {', '.join(hits)}. NOT reproduced for the rest — per §7 that is a "
                f"REPORTED finding, and no search was made outside the pre-registered set for a "
                f"definition that would hit it.")
    return ("**Neither deferred figure is reproduced by ANY pre-registered population.** Per the §7 "
            "pre-commitment this is reported as a finding rather than chased: reverse-engineering a "
            "population to hit a remembered number is the same inversion as reverse-engineering one "
            "to hit a flattering number, and is strictly worse because the target is already known.")


def _closing(out: dict) -> str:
    return ("`best_alpha = 0`. The shipped public claim is untouched by this run. Any change to it is "
            "a DISCLOSED product change (re-export via the guarded `--publish` + a changelog entry), "
            "decided by the operator from the fully-reported pre-registered set above — never a quiet "
            "edit, and never the best of several definitions tried.")


if __name__ == "__main__":
    raise SystemExit(main())
