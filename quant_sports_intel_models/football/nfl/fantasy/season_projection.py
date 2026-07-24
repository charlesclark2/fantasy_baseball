"""season_projection.py — NF-FASTPATH pure model logic (the 2026 season raw-stat-line projection).

The **projection product** the draft tool ranks on. Every function here is PURE (numpy/pandas in,
DataFrame out, NO IO) so the whole model is unit-tested offline against the fast gate; the DuckDB
reads + S3 landing + validation report live in `run_season_projection.py`.

WHAT IT PRODUCES — a RAW STAT-LINE projection per draft-relevant player for the UPCOMING season,
NOT a single league's fantasy points. NF-C1 (the league-config/scoring engine) converts the raw line
into any league's points; the `proj_fp_*` columns here are a CONVENIENCE for ranking + validation
only (standard nflverse scoring), never the product contract.

⚖️ HONEST FRAME (roadmap §0): edge-independent — no PBO/DSR/CLV gate (that is the betting posture).
The gate is FACE-VALIDITY + COVERAGE + a holdout-season rank-correlation sanity check. Uncertainty is
surfaced (an 80% interval on the convenience PPR total), not hidden; NULL = unknown kept NULL.

TWO PLAYER POPULATIONS, one schema:
  • VETERANS — every player with a completed base-season (2025) NFL line. Projected from their
    realized per-game line, shrunk toward a conservative positional prior by sample size, and scaled
    by an EXPECTED-GAMES estimate built from depth-chart role + base-season durability. The
    expected-games step is the fix for the naïve `per_game × 17` failure that ranks small-sample
    backups (Malik Willis, Jake Browning) at the very top of `mart_projections_preseason`.
  • ROOKIES (skill positions QB/RB/WR/TE) — no NFL line yet, so anchored on a HISTORICAL
    draft-slot → rookie-year production curve (fit per position on prior classes), then nudged by the
    NCAAF-P1A residual (`projected_nfl_z` vs the slot-expected z — talent the draft board disagreed
    with). P1A's `sd` is PARAMETER uncertainty, so rookie intervals are widened deliberately.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MODEL_VERSION = "nfl_fantasy_fastpath_v1"

# ── Standard (nflverse-compatible) scoring. The CONVENIENCE ranking/validation metric only — the
#    product emits the raw line and NF-C1 rescores per league. std → half-PPR → PPR differ only in
#    the per-reception weight. ────────────────────────────────────────────────────────────────────
SCORING_STD = {
    "pass_yds": 0.04, "pass_td": 4.0, "pass_int": -2.0,
    "rush_yds": 0.1, "rush_td": 6.0,
    "rec_yds": 0.1, "rec_td": 6.0, "rec": 0.0,
    "fumbles_lost": -2.0, "two_pt": 2.0,
}
PPR_PER_RECEPTION = 1.0
HALF_PPR_PER_RECEPTION = 0.5

# The raw stat-line columns the product emits (the input contract for MVP-2 / NF-C1). Season totals.
RAW_STAT_COLS = [
    "proj_games",
    "proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
    "proj_rush_att", "proj_rush_yds", "proj_rush_td",
    "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td",
    "proj_fumbles_lost", "proj_two_pt",
]

# The per-game counting stats the veteran model shrinks (base name → (fct total col)). Each is a
# realized per-game rate = season total / games_played.
_VET_PERGAME_STATS = [
    "pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int",
    "rush_att", "rush_yds", "rush_td",
    "targets", "rec", "rec_yds", "rec_td",
]

# Shrinkage half-life K per stat family (games at which player-signal == prior). Volume/counting
# stats stabilise faster than the noisy rate stats folded into them, so a single modest K.
_SHRINK_K = 5.0

# Positions that carry an offensive fantasy line at all (kickers/defense excluded from this product).
SKILL_POSITIONS = ("QB", "RB", "WR", "TE", "FB")
ROOKIE_POSITIONS = ("QB", "RB", "WR", "TE")

# Minimum base-season games for a veteran to anchor a conservative positional prior (avoids the
# cup-of-coffee crowd diluting the prior toward zero).
_PRIOR_MIN_GAMES = 6


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring (pure) — from a raw stat line to convenience fantasy points
# ══════════════════════════════════════════════════════════════════════════════════════════════
def score_line(df: pd.DataFrame, prefix: str = "proj_") -> pd.DataFrame:
    """Add `<prefix>fp_std / _fp_half / _fp_ppr` computed from the raw stat columns. Pure; NULLs in
    a raw column propagate to 0 for that term (a missing passing line does not zero a WR)."""
    def g(name):
        col = df.get(prefix + name)
        if col is None:
            return pd.Series(0.0, index=df.index)
        return pd.to_numeric(col, errors="coerce").fillna(0.0)
    std = (
        SCORING_STD["pass_yds"] * g("pass_yds")
        + SCORING_STD["pass_td"] * g("pass_td")
        + SCORING_STD["pass_int"] * g("pass_int")
        + SCORING_STD["rush_yds"] * g("rush_yds")
        + SCORING_STD["rush_td"] * g("rush_td")
        + SCORING_STD["rec_yds"] * g("rec_yds")
        + SCORING_STD["rec_td"] * g("rec_td")
        + SCORING_STD["fumbles_lost"] * g("fumbles_lost")
        + SCORING_STD["two_pt"] * g("two_pt")
    )
    out = df.copy()
    out[prefix + "fp_std"] = std
    out[prefix + "fp_half"] = std + HALF_PPR_PER_RECEPTION * g("rec")
    out[prefix + "fp_ppr"] = std + PPR_PER_RECEPTION * g("rec")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Expected games — the playing-time / role model (the hard part; the backup-QB fix)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Role base games by (position family, depth-chart rank). A rank-1 QB is a bell-cow 17-game starter;
# a rank-2 QB is a clipboard backup (a handful of relief games); skill positions rotate more so a
# rank-2 RB/WR/TE still sees meaningful time.
def _role_base_games(position: str, rank: float) -> float:
    r = 99 if rank is None or not np.isfinite(rank) else int(rank)
    pos = (position or "").upper()
    if pos == "QB":
        return {1: 16.0, 2: 4.0}.get(r, 2.0)
    if pos in ("RB", "WR", "TE", "FB"):
        return {1: 15.5, 2: 11.0, 3: 7.0}.get(r, 4.0)
    return {1: 14.0, 2: 9.0}.get(r, 4.0)  # other offensive roles


def expected_games(
    games_played: pd.Series, depth_rank: pd.Series, position: pd.Series
) -> pd.Series:
    """A leakage-safe expected-games estimate = a 50/50 blend of the depth-chart ROLE base and the
    player's realized base-season durability, clamped to [1, 17].

    The role term demotes a small-sample backup (a rank-2 QB with 4 relief games projects to ~4
    games, not 17); the durability term keeps a proven 17-game workhorse near 17 and applies a mild
    injury-carryover haircut to a player who missed time. Where the depth rank is unknown, the role
    base falls back to a games-derived proxy so the estimate never silently defaults to full-time."""
    gp = pd.to_numeric(games_played, errors="coerce").fillna(0.0).clip(0, 17)
    rank = pd.to_numeric(depth_rank, errors="coerce")
    base = np.array([_role_base_games(p, r) for p, r in zip(position, rank)], dtype=float)
    # rank-unknown fallback: lean on realized games (a full base season ⇒ starter-ish)
    unknown = ~np.isfinite(rank.to_numpy())
    proxy = np.where(gp.to_numpy() >= 12, 14.0, np.where(gp.to_numpy() >= 6, 8.0, 3.0))
    base = np.where(unknown, proxy, base)
    est = 0.5 * base + 0.5 * gp.to_numpy()
    return pd.Series(np.clip(est, 1.0, 17.0), index=gp.index)


def _games_sd(depth_rank: pd.Series, position: pd.Series) -> pd.Series:
    """Std-dev of the games estimate (drives the interval): a proven rank-1 starter is fairly
    predictable, a rotational/backup role is far more volatile (promotion or benching)."""
    rank = pd.to_numeric(depth_rank, errors="coerce")
    sd = np.where(rank.to_numpy() == 1, 2.6, np.where(rank.to_numpy() == 2, 4.2, 4.8))
    return pd.Series(sd, index=depth_rank.index)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Conservative positional priors + shrinkage (per-game)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def positional_pergame_priors(base_season: pd.DataFrame) -> pd.DataFrame:
    """Per-position conservative per-game anchor for each counting stat = the MEDIAN over qualified
    (games ≥ `_PRIOR_MIN_GAMES`) base-season players. The median (not the mean) is robust to the
    stud tail, so shrinking a small-sample player toward it pulls to a plausible mid-roster level,
    never to a star's line. Returns one row per position with a `<stat>_prior` column each."""
    q = base_season[base_season["games_played"] >= _PRIOR_MIN_GAMES].copy()
    rows = []
    for pos, g in q.groupby("position"):
        row = {"position": pos}
        for s in _VET_PERGAME_STATS:
            pg = pd.to_numeric(g.get(s + "_pg"), errors="coerce")
            row[s + "_prior"] = float(pg[pg.notna()].median()) if pg.notna().any() else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def _shrink_pergame(player_pg: np.ndarray, games: np.ndarray, prior: np.ndarray, k: float) -> np.ndarray:
    """Empirical-Bayes shrinkage: w = g/(g+k). A 16-game line barely moves (w≈0.76); a 3-game line
    is pulled ~⅔ toward the conservative prior. Vectorised, NaN-safe (missing player value ⇒ prior)."""
    w = games / (games + k)
    pv = np.where(np.isfinite(player_pg), player_pg, prior)
    return w * pv + (1.0 - w) * prior


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Veteran projection
# ══════════════════════════════════════════════════════════════════════════════════════════════
def project_veterans(
    base_season: pd.DataFrame,
    priors: pd.DataFrame,
    projection_season: int,
) -> pd.DataFrame:
    """Project every base-season player's UPCOMING-season raw stat line.

    base_season: one row per (player_id) with `<stat>_pg` realized per-game counting stats,
      `games_played`, `depth_chart_position_rank`, `fp_ppr_sd` (game-to-game PPR sd), team, position.
    priors: `positional_pergame_priors(base_season)` output.
    Returns the RAW_STAT_COLS (season totals) + convenience fp + an 80% PPR interval, per player.
    """
    df = base_season.merge(priors, on="position", how="left")
    g = pd.to_numeric(df["games_played"], errors="coerce").fillna(0.0).to_numpy()

    eg = expected_games(df["games_played"], df["depth_chart_position_rank"], df["position"])
    df["proj_games"] = eg.to_numpy()

    # shrink each per-game counting stat, then scale by expected games → season total
    season = {}
    for s in _VET_PERGAME_STATS:
        pg = pd.to_numeric(df.get(s + "_pg"), errors="coerce").to_numpy()
        prior = pd.to_numeric(df.get(s + "_prior"), errors="coerce").fillna(0.0).to_numpy()
        reg_pg = _shrink_pergame(pg, g, prior, _SHRINK_K)
        season[s] = np.clip(reg_pg, 0.0, None) * df["proj_games"].to_numpy()

    df["proj_pass_att"] = season["pass_att"]
    df["proj_pass_cmp"] = np.minimum(season["pass_cmp"], season["pass_att"])
    df["proj_pass_yds"] = season["pass_yds"]
    df["proj_pass_td"] = season["pass_td"]
    df["proj_pass_int"] = season["pass_int"]
    df["proj_rush_att"] = season["rush_att"]
    df["proj_rush_yds"] = season["rush_yds"]
    df["proj_rush_td"] = season["rush_td"]
    df["proj_targets"] = season["targets"]
    df["proj_rec"] = np.minimum(season["rec"], season["targets"])
    df["proj_rec_yds"] = season["rec_yds"]
    df["proj_rec_td"] = season["rec_td"]

    # fumbles-lost: touches × a modest league per-touch rate (materially affects scoring; honestly a
    # small nuisance term). two-point conversions are rare/idiosyncratic → left NULL (unknown).
    touches = df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy() + df["proj_pass_att"].to_numpy() * 0.0
    df["proj_fumbles_lost"] = np.round(touches * 0.006, 2)
    df["proj_two_pt"] = np.nan

    df = score_line(df, prefix="proj_")

    # ── 80% interval on the convenience PPR total. Two independent sources of season variance:
    #    (a) game-to-game scoring variance accumulated over the played games (sd·√games), and
    #    (b) games-played uncertainty (per-game mean × games sd). Normal approx, floored at 0.
    fp_pg_sd = pd.to_numeric(df.get("fp_ppr_sd"), errors="coerce").fillna(0.0).to_numpy()
    fp_ppr = df["proj_fp_ppr"].to_numpy()
    eg_arr = np.clip(df["proj_games"].to_numpy(), 1e-6, None)
    fp_per_game = fp_ppr / eg_arr
    gsd = _games_sd(df["depth_chart_position_rank"], df["position"]).to_numpy()
    season_sd = np.sqrt((fp_pg_sd * np.sqrt(eg_arr)) ** 2 + (fp_per_game * gsd) ** 2)
    z80 = 1.2815515594
    df["fp_ppr_sd"] = np.round(season_sd, 2)
    df["fp_ppr_p10"] = np.round(np.clip(fp_ppr - z80 * season_sd, 0.0, None), 1)
    df["fp_ppr_p90"] = np.round(fp_ppr + z80 * season_sd, 1)
    df["uncertainty_type"] = "empirical"  # from realized game-to-game variance
    df["is_rookie"] = False
    df["draft_overall"] = np.nan
    df["source"] = "veteran"
    df["projection_season"] = int(projection_season)
    df["confidence"] = np.where(g >= 10, "high", np.where(g >= 5, "medium", "low"))
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Rookie projection — historical draft-slot production curve + the P1A residual nudge
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Temper a slot prediction toward the position's global rookie mean (survivor-bias + small-sample
# guard): pred = (1-w)·slot + w·mean. Keeps the slot ORDER but humbles the top.
_ROOKIE_SHRINK_TO_MEAN = 0.15
# Ceiling on a rookie projection = a high quantile of historical rookie fantasy seasons at the
# position, NOT the all-time max — projecting an incoming pick at the single best rookie year ever
# is not face-valid (and the power-law extrapolates catastrophically below the training slot range).
# A P93 ceiling lets a genuinely elite early pick reach a strong-rookie level (~an established RB2/
# WR2 season) without exceeding what rookies realistically achieve.
_ROOKIE_FP_CEILING_Q = 0.93

# The raw stat totals allocated from the projected fantasy total via the positional composition.
_ROOKIE_RAW_STATS = [
    "pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int",
    "rush_att", "rush_yds", "rush_td",
    "targets", "rec", "rec_yds", "rec_td",
]


@dataclass
class RookieSlotCurve:
    """The rookie model, fit per position from prior classes. COMPOSITE-FIRST: a single draft-slot →
    rookie-year FANTASY-POINT power-law (bounded, clipped to the historical positional max), then the
    total is allocated to a raw stat line via the position's typical stat-per-point COMPOSITION. This
    is the fix for the per-stat-independent blow-up — predicting each raw stat at its own positional
    near-max for an early pick and summing yields a superhuman composite (a 2,400-rush-yd rookie); a
    bounded fp target × a real composition stays internally consistent and physically plausible."""
    fp_a: dict = field(default_factory=dict)      # position -> log-log intercept for rookie_fp
    fp_b: dict = field(default_factory=dict)      # position -> log-log slope for rookie_fp
    fp_mean: dict = field(default_factory=dict)   # position -> global rookie fp mean
    fp_ceiling: dict = field(default_factory=dict)  # position -> P93 rookie fp (hard clip)
    ratios: dict = field(default_factory=dict)    # (position, stat) -> median stat_total / fp
    games_by_pos_slot: dict = field(default_factory=dict)  # (position, slot_bucket) -> mean games
    fp_cv_by_pos: dict = field(default_factory=dict)       # position -> fp coefficient of variation

    def predict_fp(self, position: str, overall: float) -> float:
        if position not in self.fp_mean:
            return 0.0
        b = self.fp_b.get(position)
        if b is None or b >= 0 or not np.isfinite(b):
            slot = self.fp_mean[position]
        else:
            slot = np.exp(self.fp_a[position]) * (max(1.0, overall) ** b) - 1.0
        slot = max(0.0, float(slot))
        val = (1.0 - _ROOKIE_SHRINK_TO_MEAN) * slot + _ROOKIE_SHRINK_TO_MEAN * self.fp_mean[position]
        return float(np.clip(val, 0.0, self.fp_ceiling.get(position, val)))


def _slot_bucket(overall: float) -> str:
    if overall <= 15:
        return "01-15"
    if overall <= 40:
        return "16-40"
    if overall <= 100:
        return "41-100"
    return "101+"


def fit_rookie_slot_curves(hist: pd.DataFrame) -> RookieSlotCurve:
    """Fit the composite rookie model from prior classes.

    hist: one row per historical drafted rookie (skill positions) with `position_group`,
      `draft_overall`, `games`, `rookie_fp_ppr`, and the rookie-year raw stat TOTALS
      (`_ROOKIE_RAW_STATS` cols) — the training base for the fp curve + the stat composition."""
    curve = RookieSlotCurve()
    for pos, g in hist.groupby("position_group"):
        overall = pd.to_numeric(g["draft_overall"], errors="coerce")
        fp = pd.to_numeric(g.get("rookie_fp_ppr"), errors="coerce")
        ok = overall.notna() & (overall > 0) & fp.notna()
        if ok.sum() < 8:
            continue
        logo = np.log(overall[ok].to_numpy())
        fpv = np.log(np.clip(fp[ok].to_numpy(), 0, None) + 1.0)
        curve.fp_mean[pos] = float(np.clip(fp[ok].mean(), 0, None))
        curve.fp_ceiling[pos] = float(np.clip(np.quantile(fp[ok].to_numpy(), _ROOKIE_FP_CEILING_Q), 0, None))
        if np.ptp(logo) > 0:
            slope, intercept = np.polyfit(logo, fpv, 1)
            curve.fp_a[pos] = float(intercept)
            curve.fp_b[pos] = float(slope)
        # stat composition — the median raw-stat total PER fantasy point among producing rookies
        prod = g[fp > 20]
        for stat in _ROOKIE_RAW_STATS:
            y = pd.to_numeric(prod.get(stat), errors="coerce")
            f = pd.to_numeric(prod.get("rookie_fp_ppr"), errors="coerce")
            r = (y / f).replace([np.inf, -np.inf], np.nan).dropna()
            curve.ratios[(pos, stat)] = float(r.median()) if len(r) else 0.0
        # games mean by slot bucket (rookie playing-time prior)
        for bucket, gb in g.assign(_bkt=overall.map(lambda o: _slot_bucket(o) if pd.notna(o) else "101+")).groupby("_bkt"):
            gm = pd.to_numeric(gb.get("games"), errors="coerce")
            if gm.notna().any():
                curve.games_by_pos_slot[(pos, bucket)] = float(gm.mean())
        # fp dispersion (coefficient of variation) → interval width
        fpp = fp[fp.notna() & (fp > 5)]
        if len(fpp) >= 8 and fpp.mean() > 0:
            curve.fp_cv_by_pos[pos] = float(np.clip(fpp.std() / fpp.mean(), 0.35, 1.2))
    return curve


def project_rookies(
    rookies: pd.DataFrame,
    curve: RookieSlotCurve,
    projection_season: int,
    residual_lambda: float = 0.12,
) -> pd.DataFrame:
    """Project the incoming rookie class (skill positions) from the slot curve, nudged by the P1A
    residual (talent the draft board under/over-rated) and widened for rookie uncertainty.

    rookies: P1A rows for the incoming class — `gsis_id, player_name, position_group, nfl_position,
      draft_overall, projected_nfl_z`. Only QB/RB/WR/TE with a real draft slot are projected.
    """
    r = rookies.copy()
    r = r[r["position_group"].isin(ROOKIE_POSITIONS)]
    r = r[pd.to_numeric(r["draft_overall"], errors="coerce").notna()].reset_index(drop=True)
    if r.empty:
        return r

    overall = pd.to_numeric(r["draft_overall"], errors="coerce").to_numpy()

    # ── P1A residual: within (position, class), how far the player's translated talent z sits above
    #    the slot-EXPECTED z. Regress projected_nfl_z ~ log(overall) inside the class per position;
    #    the residual is the disagreement the draft board did not price. Scaled + clipped to a mild
    #    multiplicative production nudge (never a wild swing off a parameter-uncertainty z).
    nudge = np.ones(len(r))
    z = pd.to_numeric(r["projected_nfl_z"], errors="coerce").to_numpy()
    logo = np.log(np.clip(overall, 1, None))
    for pos in r["position_group"].unique():
        idx = np.where((r["position_group"] == pos).to_numpy())[0]
        if len(idx) < 6:
            continue
        zi, li = z[idx], logo[idx]
        m = np.isfinite(zi) & np.isfinite(li)
        if m.sum() < 6:
            continue
        if np.ptp(li[m]) == 0:
            # every player in the group shares a slot ⇒ no slope; the slot-expected z is the mean z
            resid = zi - np.nanmean(zi[m])
        else:
            slope, intercept = np.polyfit(li[m], zi[m], 1)
            resid = zi - (intercept + slope * logo[idx])
        rs = np.nanstd(resid[np.isfinite(resid)])
        if rs and np.isfinite(rs):
            nudge[idx] = np.clip(np.exp(residual_lambda * np.nan_to_num(resid / rs)), 0.75, 1.35)

    out = {
        "player_id": r["gsis_id"].to_numpy(),
        "player_name": r["player_name"].to_numpy(),
        "position": r["nfl_position"].fillna(r["position_group"]).to_numpy(),
        "team_id": np.nan,
        "draft_overall": overall,
    }
    pos_group = r["position_group"].to_numpy()
    # 1) a bounded rookie FANTASY-POINT target per player (slot curve × the P1A residual nudge),
    #    re-clipped so the nudge can never carry it past the historical positional ceiling.
    fp_target = np.array([curve.predict_fp(pos_group[i], overall[i]) for i in range(len(r))]) * nudge
    fp_cap = np.array([curve.fp_ceiling.get(pos_group[i], 0.0) for i in range(len(r))])
    fp_target = np.clip(fp_target, 0.0, np.where(fp_cap > 0, fp_cap, fp_target))
    # 2) allocate the target to a raw stat line via the position's median stat-per-point composition
    stat_to_col = {
        "pass_att": "proj_pass_att", "pass_cmp": "proj_pass_cmp", "pass_yds": "proj_pass_yds",
        "pass_td": "proj_pass_td", "pass_int": "proj_pass_int",
        "rush_att": "proj_rush_att", "rush_yds": "proj_rush_yds", "rush_td": "proj_rush_td",
        "targets": "proj_targets", "rec": "proj_rec", "rec_yds": "proj_rec_yds", "rec_td": "proj_rec_td",
    }
    for stat, col in stat_to_col.items():
        ratio = np.array([curve.ratios.get((pos_group[i], stat), 0.0) for i in range(len(r))])
        out[col] = np.clip(ratio * fp_target, 0.0, None)
    # expected games from the slot-bucket historical mean
    games = np.array([
        curve.games_by_pos_slot.get((pos_group[i], _slot_bucket(overall[i])),
                                    curve.games_by_pos_slot.get((pos_group[i], "101+"), 6.0))
        for i in range(len(r))
    ])
    out["proj_games"] = np.clip(games, 1.0, 17.0)

    df = pd.DataFrame(out)
    df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])
    df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
    # 3) rescale the whole line so its SCORED PPR equals the bounded fp target exactly — median
    #    composition ratios do not reproduce the mean scoring, so an un-rescaled line can drift ABOVE
    #    the positional ceiling. Scoring is linear in the stats, so one scalar per player restores
    #    internal consistency (scored line == target ≤ ceiling) and physical plausibility.
    scored = score_line(df, prefix="proj_")["proj_fp_ppr"].to_numpy()
    k = np.where(scored > 1e-6, fp_target / scored, 1.0)
    for col in stat_to_col.values():
        df[col] = np.clip(df[col].to_numpy() * k, 0.0, None)
    touches = df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()
    df["proj_fumbles_lost"] = np.round(touches * 0.006, 2)
    df["proj_two_pt"] = np.nan
    df = score_line(df, prefix="proj_")

    # wide rookie interval from the per-position fp coefficient of variation (parameter uncertainty)
    cv = np.array([curve.fp_cv_by_pos.get(p, 0.7) for p in pos_group])
    fp = df["proj_fp_ppr"].to_numpy()
    sd = fp * cv
    z80 = 1.2815515594
    df["fp_ppr_sd"] = np.round(sd, 2)
    df["fp_ppr_p10"] = np.round(np.clip(fp - z80 * sd, 0.0, None), 1)
    df["fp_ppr_p90"] = np.round(fp + z80 * sd, 1)
    df["uncertainty_type"] = "parameter"  # slot-curve + P1A parameter uncertainty, recalibrate downstream
    df["is_rookie"] = True
    df["source"] = "rookie"
    df["projection_season"] = int(projection_season)
    df["confidence"] = "low"  # rookies are inherently high-variance
    df["fp_ppr_l5"] = np.nan
    return df
