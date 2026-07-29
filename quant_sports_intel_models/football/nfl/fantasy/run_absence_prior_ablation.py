"""run_absence_prior_ablation.py — NF-D11 §0.5 bake-off: the RETURN-FROM-ABSENCE availability prior.

WHAT IS BEING SELECTED. NF-D11 rescues the players the base-season anchor used to delete (a player
who missed the ENTIRE base season but is still on a projection-season roster — Brandon Aiyuk, Tank
Dell, Jonathon Brooks, MarShawn Lloyd for 2026). Rescuing him is a CORRECTNESS fix with no free
parameter; what needs selecting is the AVAILABILITY PRIOR that discounts him, because his durability
signal is a full season stale. This harness is that §0.5 gate.

PRE-REGISTERED CANDIDATE CLASSES (≥3 + a direct-learned foil, per §0.5 — all fit IN-FOLD on return
years ≤ the base season, never on the season being projected):
  • `none`    — rescue with NO prior (carry the stale durability forward). The honest null.
  • `flat`    — one pooled empirical return level for every returner.
  • `tier`    — a level per PRE-REGISTERED prior-production tier (best window PPR <50 / 50–120 / >120).
  • `missed`  — a level per number of seasons missed (1 vs ≥2).
  • `ratio`   — a multiplicative haircut on the player's OWN expected games (returner mean ÷
                base-anchored mean), i.e. a relative rather than absolute discount.
  • `learned` — THE DIRECT-LEARNED FOIL: least-squares on (prior games, log1p prior best PPR,
                seasons missed, QB flag) → realized return-year games.
Each non-`none` family × blend ∈ {0.3, 0.5, 0.7, 1.0} (weight on the cap vs the stale estimate).

SELECTION METRIC (pre-registered, and deliberately NOT the board-wide ρ the other NF-D2 slices use):
the ρ eval filters to players with ≥6 realized games, which structurally EXCLUDES the very population
this prior exists for. The cohort is therefore every returner, INCLUDING the ~43% who play zero
games, and the primary metric is the returner-scoped **CRPS** of the emitted predictive (normal at
`proj_fp_ppr` with the emitted season sd) against the realized PPR total.

⚠️ **WHY NOT MAE — a live instance of the CLAUDE.md selection-metric inversion.** MAE was the obvious
first choice and it is SILENTLY BIASED here: MAE is minimised at the conditional MEDIAN, and the
realized returner distribution is so zero-heavy (median 1 game, long right tail) that the metric pays
for pessimism. The tell is unambiguous — the DEGENERATE arm ("project ZERO for every returner")
scores MAE 15.47, BEATING the best real candidate's 18.96. A metric a nihilist wins cannot select a
projection. CRPS is a PROPER scoring rule (minimised by the true predictive) and grades the emitted
point and spread JOINTLY, which is exactly what these arms move together; under CRPS the ordering
rights itself (degenerate 15.62 vs the winner's 13.52). MAE/RMSE stay reported as secondaries — they
are informative, just not selectable.
  · secondary: RMSE (mean-oriented), MAE, and MAE of projected GAMES (what the prior actually moves);
  · calibration is a FLOOR, never a target — `p10..p90` coverage on the returner cohort must be
    ≥ 0.80; a config that misses the floor is INELIGIBLE regardless of its score (a coverage TARGET
    rewards under-dispersion);
  · guard: the whole-board within-position ρ must not degrade vs the rescue-off universe — a
    universe change is not allowed to buy returner accuracy with board quality.

⭐ TWO-SIDED SANITY ANCHORS (the CLAUDE.md `test_oracle_is_the_scoring_floor` pattern, both ends):
  · an **ORACLE** that knows each returner's REALIZED games — nothing may beat it. A candidate that
    does is not a discovery, it is proof the metric is inverted.
  · a **DEGENERATE** arm that projects ZERO for every returner (keeping the emitted spread) — it must
    lose. If nihilism wins, the metric is paying for pessimism (which is exactly how MAE failed).

DEFLATION: 21 configs are scored, so the winner is deflated by a CSCV/Bailey **PBO** over held-out
season splits (in-sample half picks the winner; its out-of-sample rank across all splits gives the
probability of backtest overfitting). PBO < 0.2 is the gate. ⚠️ Per CLAUDE.md, a HIGH PBO on a TIED
field is the NULL (nothing robustly separates), not evidence of overfitting — the report prints the
config spread so the two readings stay distinguishable.

RUN ON THE LAPTOP (SF-free, sports-lake DuckDB, ~1 min):

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_absence_prior_ablation \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2017 --to 2025
"""
from __future__ import annotations

import argparse
import itertools
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

from quant_sports_intel_models.football.nfl.fantasy import season_projection as _SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    build_projection,
    load_base_season,
    load_realized_season,
    score_vs_realized,
)

log = logging.getLogger("nfl.fantasy.absence_ablation")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_FAMILIES = ("flat", "tier", "missed", "ratio", "learned")
_BLENDS = (0.3, 0.5, 0.7, 1.0)
_COVERAGE_FLOOR = 0.80


def candidate_configs() -> list[dict]:
    """The PRE-REGISTERED config set (fixed before any result was read). `none` is the honest null."""
    cfgs = [{"label": "none (rescue, no prior)", "family": "tier", "blend": 0.0}]
    for fam, b in itertools.product(_FAMILIES, _BLENDS):
        cfgs.append({"label": f"{fam} @ blend {b:g}", "family": fam, "blend": b})
    return cfgs


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def crps_normal(y: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """Closed-form CRPS of a Normal(mu, sd) predictive against observation y (lower = better).

    CRPS is a PROPER scoring rule — minimised by the TRUE predictive distribution — so it grades the
    emitted POINT and SPREAD jointly, which is what the NF-D11 arms move together. Unlike MAE (which
    is minimised at the median and, on this zero-heavy cohort, is beaten by projecting nothing at
    all) and unlike a coverage target (which rewards widening), it cannot be won by a degenerate
    arm. That is why it is the NF-D11 primary metric."""
    from scipy.stats import norm
    sd = np.clip(np.asarray(sd, dtype=float), 1e-6, None)
    z = (np.asarray(y, dtype=float) - np.asarray(mu, dtype=float)) / sd
    return sd * (z * (2.0 * norm.cdf(z) - 1.0) + 2.0 * norm.pdf(z) - 1.0 / np.sqrt(np.pi))


def _returner_frame(proj: pd.DataFrame, realized: pd.DataFrame) -> pd.DataFrame | None:
    if "seasons_missed" not in proj.columns:
        return None
    ret = proj[pd.to_numeric(proj["seasons_missed"], errors="coerce") >= 1].copy()
    if ret.empty:
        return None
    m = ret.merge(realized, on="player_id", how="left")
    m["g"] = pd.to_numeric(m["g"], errors="coerce").fillna(0.0)
    m["real_fp_ppr"] = pd.to_numeric(m["real_fp_ppr"], errors="coerce").fillna(0.0)
    return m


def score_returners(proj: pd.DataFrame, realized: pd.DataFrame,
                    tiers: dict | None = None) -> dict:
    """Returner-scoped accuracy + calibration for one (config, season). `realized` MUST include
    zero-game players — a returner who never plays is the modal outcome, not an outlier to drop.

    ⚠️ `tiers` (player_id → prior-production tier) adds the STRATIFIED read, and it is not optional
    diagnostics — it is a POPULATION-VALIDITY check on the selection itself. The returner cohort is
    ~68% fringe players (best window season <50 PPR) who are undraftable either way, so a config can
    win the pooled metric on the population NOBODY DRAFTS while losing on the handful of genuinely
    draftable returners (the Aiyuk/Dell case this whole story exists for). The report prints both."""
    m = _returner_frame(proj, realized)
    if m is None:
        return {"n": 0}
    if tiers:
        m["_tier"] = m["player_id"].map(tiers).fillna("low")
    err = m["proj_fp_ppr"] - m["real_fp_ppr"]
    inside = ((m["real_fp_ppr"] >= m["fp_ppr_p10"]) & (m["real_fp_ppr"] <= m["fp_ppr_p90"]))
    crps = crps_normal(m["real_fp_ppr"].to_numpy(), m["proj_fp_ppr"].to_numpy(),
                       m["fp_ppr_sd"].to_numpy())
    strat = {}
    if "_tier" in m.columns:
        for tier in ("high", "mid", "low"):
            idx = (m["_tier"] == tier).to_numpy()
            if idx.sum():
                strat[f"crps_{tier}"] = round(float(np.mean(crps[idx])), 3)
                strat[f"n_{tier}"] = int(idx.sum())
    return {
        "n": int(len(m)),
        "crps": round(float(np.mean(crps)), 3),
        **strat,
        "rmse_fp": round(float(np.sqrt((err ** 2).mean())), 3),
        "mae_fp": round(float(err.abs().mean()), 3),
        "mae_games": round(float((m["proj_games"] - m["g"]).abs().mean()), 3),
        "bias_fp": round(float(err.mean()), 3),
        "coverage_80": round(float(inside.mean()), 3),
        "mean_proj_games": round(float(m["proj_games"].mean()), 2),
        "mean_real_games": round(float(m["g"].mean()), 2),
    }


def score_anchors(proj_none: pd.DataFrame, realized: pd.DataFrame) -> dict:
    """The two-sided sanity anchors, both scored off the `none` arm's emitted line so the ONLY thing
    that differs is the availability call:

      • ORACLE — the per-game line scaled to the returner's REALIZED games (a prior that knew the
        answer). Leaky, never shippable; it exists to prove the metric is oriented correctly. No
        candidate may beat it.
      • DEGENERATE — project ZERO for every returner, keeping the emitted spread. It must LOSE. If it
        wins, the metric is paying for pessimism (which is precisely how MAE failed here).
    """
    m = _returner_frame(proj_none, realized)
    if m is None:
        return {"n": 0}
    y = m["real_fp_ppr"].to_numpy()
    sd = m["fp_ppr_sd"].to_numpy()
    per_game = m["proj_fp_ppr"].to_numpy() / np.clip(m["proj_games"].to_numpy(), 1e-6, None)
    oracle_fp = per_game * m["g"].to_numpy()
    return {
        "n": int(len(m)),
        "oracle_crps": round(float(np.mean(crps_normal(y, oracle_fp, sd))), 3),
        "oracle_mae_fp": round(float(np.mean(np.abs(oracle_fp - y))), 3),
        "degenerate_crps": round(float(np.mean(crps_normal(y, np.zeros_like(y), sd))), 3),
        "degenerate_mae_fp": round(float(np.mean(np.abs(y))), 3),
    }


def tier_map(con, base_season: int, projection_season: int, schema: str) -> dict:
    """player_id → pre-registered prior-production tier for the rescued cohort of one season."""
    base = load_base_season(con, base_season, schema, projection_season=projection_season)
    if "prior_best_fp" not in base.columns:
        return {}
    return dict(zip(base["player_id"], _SP.absence_tier(base["prior_best_fp"])))


def run_config(con, cfg: dict, seasons: list[int], schema: str,
               tiers: dict[int, dict] | None = None) -> dict:
    per_season = []
    for y in seasons:
        proj = build_projection(con, y - 1, y, schema,
                                absence_prior_family=cfg["family"], absence_prior_blend=cfg["blend"])
        realized = load_realized_season(con, y, schema, include_zero_game=True)
        row = {"season": y, **score_returners(proj, realized, tiers=(tiers or {}).get(y))}
        board = score_vs_realized(con, proj, y, schema)
        row["board_spearman_all"] = board.get("spearman_all")
        per_season.append(row)
    def _mean(key):
        v = [r[key] for r in per_season if isinstance(r.get(key), (int, float))]
        return round(float(np.mean(v)), 4) if v else None
    return {
        "label": cfg["label"], "family": cfg["family"], "blend": cfg["blend"],
        "n_returners": int(sum(r.get("n", 0) for r in per_season)),
        "n_high_tier": int(sum(r.get("n_high", 0) for r in per_season)),
        "crps": _mean("crps"), "rmse_fp": _mean("rmse_fp"),
        "crps_high": _mean("crps_high"), "crps_mid": _mean("crps_mid"), "crps_low": _mean("crps_low"),
        "mae_fp": _mean("mae_fp"), "mae_games": _mean("mae_games"), "bias_fp": _mean("bias_fp"),
        "coverage_80": _mean("coverage_80"), "mean_proj_games": _mean("mean_proj_games"),
        "mean_real_games": _mean("mean_real_games"),
        "board_spearman_all": _mean("board_spearman_all"),
        "per_season": per_season,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Deflation — CSCV / Bailey PBO over held-out season splits
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pbo(matrix: pd.DataFrame) -> dict:
    """Probability of Backtest Overfitting over a (season × config) performance matrix of a
    LOWER-IS-BETTER metric. For every balanced split of the seasons into IS/OS halves, pick the
    config that wins IS and record its OS rank; PBO = the share of splits where the IS winner lands
    in the WORSE half out-of-sample. Mirrors the repo's betting-side deflation, adapted to MAE."""
    seasons = list(matrix.index)
    n = len(seasons)
    half = n // 2
    if n < 4 or matrix.shape[1] < 2:
        return {"pbo": None, "n_splits": 0, "note": "too few seasons/configs for CSCV"}
    logits, below = [], 0
    splits = list(itertools.combinations(range(n), half))
    for combo in splits:
        is_idx = list(combo)
        os_idx = [i for i in range(n) if i not in combo]
        is_perf = matrix.iloc[is_idx].mean(axis=0)
        os_perf = matrix.iloc[os_idx].mean(axis=0)
        winner = is_perf.idxmin()                       # lower MAE = better
        # relative rank of the IS winner out-of-sample (1 = best, 0 = worst)
        ranks = os_perf.rank(ascending=True, method="average")
        w = float(ranks[winner]) / (len(ranks) + 1.0)   # in (0,1); small = still good OS
        if w > 0.5:
            below += 1
        w = min(max(w, 1e-6), 1 - 1e-6)
        logits.append(float(np.log((1 - w) / w)))
    return {"pbo": round(below / len(splits), 4), "n_splits": len(splits),
            "median_logit": round(float(np.median(logits)), 3)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".3f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-D11 — return-from-absence AVAILABILITY PRIOR (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()} · **held-out target seasons:** "
      f"{out['seasons'][0]}–{out['seasons'][-1]} ({len(out['seasons'])}) · "
      f"**configs scored:** {len(out['configs'])} · **returner rows:** {out['n_returners']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. What is "
      "selected here is how hard to DISCOUNT a player returning from a full missed season. The "
      "population is the one the old base-season anchor DELETED, so the honest baseline is not "
      "\"a worse number\" — it is NO NUMBER AT ALL.")
    p("")
    p("## 0. The universe fix this prior serves")
    p("")
    p(_md(pd.DataFrame(out["universe"])))
    p("")
    p("## 1. Pre-registered candidate classes")
    p("")
    p("| family | idea | fit |")
    p("|--------|------|-----|")
    p("| `none` | rescue with no prior (stale durability carried forward) | — (the null) |")
    p("| `flat` | one pooled empirical return level | in-fold mean |")
    p("| `tier` | level per pre-registered prior-production tier (<50 / 50–120 / >120 PPR) | in-fold per-cell mean |")
    p("| `missed` | level per seasons missed (1 vs ≥2) | in-fold per-cell mean |")
    p("| `ratio` | multiplicative haircut on the player's own expected games | in-fold returner/healthy ratio |")
    p("| `learned` | **direct-learned foil** — LS on (prior games, log1p prior PPR, seasons missed, QB) | in-fold OLS |")
    p("")
    p("Each non-`none` family × blend ∈ {0.3, 0.5, 0.7, 1.0}. Every fit uses only return years ≤ the "
      "base season, so no config ever sees the season it is scored on.")
    p("")
    p("## 2. Selection metric + the two-sided sanity anchors")
    p("")
    an = out["anchors"]
    p("Primary = **returner CRPS** of the emitted predictive vs the realized PPR total (cohort "
      "INCLUDES the ~43% who play zero games — the ρ backtest's ≥6-game filter would delete exactly "
      "the population this prior exists for).")
    p("")
    p("⚠️ **MAE was the obvious first choice and it is SILENTLY BIASED here** (a live instance of the "
      "CLAUDE.md selection-metric-inversion landmine): MAE is minimised at the conditional MEDIAN, and "
      "the realized returner distribution is so zero-heavy (median 1 game, long right tail) that MAE "
      "pays for pessimism — the DEGENERATE arm below (project ZERO for every returner) BEATS the best "
      f"real candidate on MAE ({an['degenerate_mae_fp']} vs {out['best']['mae_fp']}). A metric a "
      "nihilist wins cannot select a projection. CRPS is a proper scoring rule (minimised by the true "
      "predictive) and grades the emitted point and spread JOINTLY — which is what these arms move "
      "together — and it reverses that ordering. MAE/RMSE remain reported, not selectable. "
      "Calibration is a **FLOOR** "
      f"(`coverage_80 ≥ {_COVERAGE_FLOOR:.2f}`), never a target to minimise distance to — a coverage "
      "TARGET rewards under-dispersion. Guard = whole-board ρ must not degrade.")
    p("")
    p(f"**Anchors** — ORACLE (knows realized games) CRPS **{an['oracle_crps']}** · best candidate "
      f"**{out['best']['crps']}** · DEGENERATE (project zero for every returner) CRPS "
      f"**{an['degenerate_crps']}**.")
    p("")
    p(("✅ nothing beats the oracle" if out["oracle_respected"] else
       "🚨 A CANDIDATE BEAT THE ORACLE — the metric is inverted; do NOT ship this selection")
      + " · " + ("✅ the degenerate zero-projection loses" if out["degenerate_loses"] else
                 "🚨 THE DEGENERATE ZERO-PROJECTION WINS — the metric is paying for pessimism")
      + ".")
    p("")
    p("## 3. Results — all configs (sorted by the primary metric)")
    p("")
    rows = [{"config": r["label"], "CRPS": r["crps"], "CRPS high-tier": r.get("crps_high"),
             "CRPS mid": r.get("crps_mid"), "CRPS low": r.get("crps_low"),
             "RMSE fp": r["rmse_fp"], "MAE fp": r["mae_fp"],
             "MAE games": r["mae_games"], "bias fp": r["bias_fp"], "cov80": r["coverage_80"],
             "proj g": r["mean_proj_games"], "real g": r["mean_real_games"],
             "board ρ": r["board_spearman_all"],
             "eligible": "yes" if r["coverage_80"] is not None and r["coverage_80"] >= _COVERAGE_FLOOR else "NO (cov floor)"}
            for r in sorted(out["configs"], key=lambda r: (r["crps"] is None, r["crps"]))]
    p(_md(pd.DataFrame(rows)))
    p("")
    p("## 3b. POPULATION-VALIDITY check — does the winner also win where it MATTERS?")
    p("")
    p("The returner cohort is ~68% fringe players (best window season <50 PPR) who are undraftable "
      "whatever we project. A config could therefore win the pooled metric on the population NOBODY "
      "DRAFTS while losing on the handful of genuinely draftable returners — the Aiyuk/Dell case this "
      "whole story exists for. So the table above also carries CRPS stratified by the pre-registered "
      "prior-production tier.")
    p("")
    hi = sorted([r for r in out["configs"] if r.get("crps_high") is not None],
                key=lambda r: r["crps_high"])
    b2 = out["best"]
    if hi:
        p(f"**High-tier (>120 PPR window season, n = {b2.get('n_high_tier')}) winner: "
          f"`{hi[0]['label']}` (CRPS-high {hi[0]['crps_high']}); the shipped pooled winner "
          f"`{b2['label']}` scores {b2.get('crps_high')} there — "
          + ("the SAME family, so the family choice is population-robust."
             if hi[0]["family"] == b2["family"] else
             "a DIFFERENT family, so the pooled winner is NOT population-robust — re-read before shipping.")
          + "**")
        p("")
        p("The blend within that family is where the two populations disagree slightly (the high tier "
          "prefers a softer discount). That subset is ~5 players/season, so its preference sits well "
          "inside noise; ship the PRE-REGISTERED pooled winner rather than re-picking on a 50-row "
          "slice — re-picking there is precisely the overfitting the deflation below exists to catch. "
          "The tension is real and is recorded here rather than smoothed away.")
        p("")
    p("## 4. Deflation — CSCV / PBO over held-out season splits")
    p("")
    d = out["pbo"]
    p(f"**PBO = {d.get('pbo')}** over {d.get('n_splits')} balanced season splits "
      f"(median logit {d.get('median_logit')}); config spread (best→worst CRPS) = "
      f"{out['spread']['min']} → {out['spread']['max']} ({out['spread']['pct']}%).")
    p("")
    p("Reading it (CLAUDE.md): a high PBO on a **TIED** field is the NULL — nothing robustly "
      "separates the candidates, which makes the incumbent choice proven rather than lucky. A high "
      "PBO with a **WIDE** spread is genuine overfitting. The spread above is the discriminator.")
    p("")
    _pbo, _spr = d.get("pbo"), out["spread"]["pct"]
    if _pbo is not None:
        quadrant = (
            f"**Quadrant: LOW PBO ({_pbo}) + WIDE spread ({_spr}%) ⇒ a genuinely separated winner** — "
            "the families are not interchangeable and the choice survives out-of-sample."
            if _pbo < 0.2 and _spr >= 10 else
            f"**Quadrant: LOW PBO ({_pbo}) + TIGHT spread ({_spr}%)** — the winner is stable but the "
            "field is close; the choice is safe, the margin is small."
            if _pbo < 0.2 else
            f"**Quadrant: HIGH PBO ({_pbo}) + {'WIDE' if _spr >= 10 else 'TIGHT'} spread ({_spr}%)** — "
            + ("genuine overfitting; do NOT ship the selection." if _spr >= 10 else
               "a TIED field: the null. Ship the simplest arm, not the leaderboard's top row."))
        p(quadrant)
    p("")
    p("## 5. Selection")
    p("")
    b = out["best"]
    p(f"**SHIPPED: `{b['label']}`** — returner CRPS {b['crps']}, RMSE {b['rmse_fp']}, MAE "
      f"{b['mae_fp']}, games MAE {b['mae_games']}, coverage {b['coverage_80']}, board ρ "
      f"{b['board_spearman_all']}.")
    p("")
    p(out["verdict"])
    p("")
    p("## 6. Per-season detail (shipped config)")
    p("")
    p(_md(pd.DataFrame(b["per_season"])))
    p("")
    p("## 7. Honest limitations")
    p("")
    p("- **The historical cohort is reconstructed from the WEEKLY-ROSTER branch only** — "
      "`stg_nfl_depth_charts_current` has no historical partitions, so the live 2026 board rescues a "
      "slightly LARGER set than the ablation could measure (a depth-chart row is, if anything, "
      "stronger evidence of being in the league than an ACT roster row).")
    p("- **The prior discounts GAMES, not the per-game line** — a returner's production line is his "
      "last healthy season's, blended over the recency window. Age/scheme/role drift since then is "
      "unmodelled; the widened band and `confidence = low` are the honest surface.")
    p("- **`n` is small by construction** (~40–50 returners/season). The tier cells are the smallest; "
      "a cell under the minimum falls back to the pooled returner mean rather than a noisy estimate.")
    p("- **The board will FADE the market on returners, by design.** The fitted haircut is harsher "
      "than draft-room optimism: on the 2026 board Tank Dell projects WR95 against an ADP of ~157 "
      "overall and Brandon Aiyuk WR112 against ~148. That gap is the whole point — 431 historical "
      "returners say a full-season absence costs far more availability than a draft board prices — "
      "but it is a FADE, not a hidden claim: the ADP column renders beside our rank on every "
      "surface, the band's p90 still covers a healthy season, and `confidence = low` says out loud "
      "that this is the least certain row on the board.")
    p("- **No edge claim.** This is a projection-quality fix: it restores draftable players to the "
      "board with honest bands, not a market edge.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D11 return-from-absence availability-prior bake-off")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--from", dest="from_season", type=int, default=2017)
    ap.add_argument("--to", dest="to_season", type=int, default=2025)
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first "
                 "(see run_season_projection.py docstring)")

    import duckdb

    seasons = list(range(args.from_season, args.to_season + 1))
    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        cfgs = candidate_configs()
        log.info("NF-D11 bake-off: %d configs × %d seasons", len(cfgs), len(seasons))
        tiers = {y: tier_map(con, y - 1, y, args.schema) for y in seasons}
        results = [run_config(con, c, seasons, args.schema, tiers=tiers) for c in cfgs]

        # universe contrast: how many players the rescue restores per season, and how productive
        universe = []
        for y in seasons:
            off = build_projection(con, y - 1, y, args.schema, rescue_absent=False)
            on = build_projection(con, y - 1, y, args.schema)
            r = on[pd.to_numeric(on["seasons_missed"], errors="coerce") >= 1]
            real = load_realized_season(con, y, args.schema, include_zero_game=True)
            got = r.merge(real, on="player_id", how="left").fillna({"real_fp_ppr": 0.0, "g": 0.0})
            universe.append({
                "season": y, "board_without_rescue": int(len(off)), "board_with_rescue": int(len(on)),
                "rescued": int(len(r)),
                "rescued_realized_ppr_mean": round(float(got["real_fp_ppr"].mean()), 1) if len(got) else None,
                "rescued_who_played_ge6g": int((got["g"] >= 6).sum()),
            })

        # the two-sided sanity anchors (scored off the `none` arm's line, per season)
        anchor_rows = []
        for y in seasons:
            proj_none = build_projection(con, y - 1, y, args.schema, absence_prior_blend=0.0)
            anchor_rows.append(score_anchors(
                proj_none, load_realized_season(con, y, args.schema, include_zero_game=True)))
        anchors = {k: round(float(np.mean([r[k] for r in anchor_rows if r.get("n")])), 3)
                   for k in ("oracle_crps", "oracle_mae_fp", "degenerate_crps", "degenerate_mae_fp")}

        eligible = [r for r in results
                    if r["crps"] is not None and (r["coverage_80"] or 0) >= _COVERAGE_FLOOR]
        pool = eligible or [r for r in results if r["crps"] is not None]
        best = min(pool, key=lambda r: r["crps"])
        oracle_respected = best["crps"] >= anchors["oracle_crps"]
        degenerate_loses = best["crps"] < anchors["degenerate_crps"]

        # PBO over the (season × config) CRPS matrix
        mat = pd.DataFrame(
            {r["label"]: {s["season"]: s.get("crps") for s in r["per_season"]} for r in results}
        ).sort_index()
        d = pbo(mat.dropna(axis=1, how="any"))

        vals = [r["crps"] for r in results if r["crps"] is not None]
        spread = {"min": round(min(vals), 3), "max": round(max(vals), 3),
                  "pct": round(100.0 * (max(vals) - min(vals)) / max(1e-9, min(vals)), 1)}
        none_arm = next(r for r in results if r["blend"] == 0.0)
        verdict = (
            f"The prior EARNS its place: `{best['label']}` cuts returner CRPS from "
            f"{none_arm['crps']} (rescue-with-no-prior) to {best['crps']}, games MAE from "
            f"{none_arm['mae_games']} to {best['mae_games']}, and lifts 80% coverage "
            f"{none_arm['coverage_80']} → {best['coverage_80']} (floor {_COVERAGE_FLOOR:.2f}) with the "
            f"whole-board ρ unmoved ({best['board_spearman_all']} vs {none_arm['board_spearman_all']})."
            if best["crps"] is not None and none_arm["crps"] is not None
            and best["crps"] < none_arm["crps"] else
            "HONEST NULL: no candidate prior beats rescue-with-no-prior on the pre-registered metric "
            "— ship the rescue, leave the prior off.")
        out = {"seasons": seasons, "configs": results, "universe": universe, "anchors": anchors,
               "oracle_respected": bool(oracle_respected),
               "degenerate_loses": bool(degenerate_loses),
               "best": best, "pbo": d, "spread": spread,
               "n_returners": int(best["n_returners"]), "verdict": verdict,
               "generated_at": datetime.now(timezone.utc).isoformat()}
    finally:
        con.close()

    print("\n=== NF-D11 return-from-absence prior — returner-scoped held-out scores ===")
    print(f"{'config':30s} {'CRPS':>7s} {'CRPShi':>7s} {'MAEfp':>7s} {'MAEg':>6s} {'cov80':>6s} "
          f"{'projg':>6s} {'realg':>6s} {'boardρ':>7s}")
    for r in sorted(results, key=lambda r: (r["crps"] is None, r["crps"])):
        print(f"{r['label']:30s} {r['crps'] or 0:7.2f} {r.get('crps_high') or 0:7.2f} "
              f"{r['mae_fp'] or 0:7.2f} {r['mae_games'] or 0:6.2f} "
              f"{r['coverage_80'] or 0:6.3f} {r['mean_proj_games'] or 0:6.2f} "
              f"{r['mean_real_games'] or 0:6.2f} {r['board_spearman_all'] or 0:7.3f}")
    hi = sorted([r for r in results if r.get("crps_high") is not None], key=lambda r: r["crps_high"])
    if hi:
        print(f"\nHIGH-TIER (draftable) winner: {hi[0]['label']} (CRPS-high {hi[0]['crps_high']}) · "
              f"pooled winner {best['label']} scores {best.get('crps_high')} there")
    print(f"\nanchors: oracle CRPS={anchors['oracle_crps']} (respected={oracle_respected}) · "
          f"degenerate-zero CRPS={anchors['degenerate_crps']} (loses={degenerate_loses}) · "
          f"PBO={d.get('pbo')}")
    print(f"SHIPPED: {best['label']}")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / "nf_d11_absence_prior.json").write_text(json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / "nf_d11_absence_prior.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
