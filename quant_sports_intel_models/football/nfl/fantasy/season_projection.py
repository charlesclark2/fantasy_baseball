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
  • VETERANS — every player with a completed base-season (2025) NFL line, PLUS (NF-D11) the
    "injured-all-year" players whose base season is empty but whose 3-year window still holds real
    production and who are still on a projection-season roster — anchored on their MOST-RECENT
    PLAYED season and discounted by the RETURN-FROM-ABSENCE availability prior below. Projected from
    their realized per-game line, shrunk toward a conservative positional prior by sample size, and
    scaled by an EXPECTED-GAMES estimate built from depth-chart role + base-season durability. The
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

from quant_sports_intel_models.football.nfl.fantasy import xfp_source as _XFP  # NF-D7 TD regression

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

# ── NF-D2 slice 1: base-season USAGE-SHARE role signal → expected games (the within-tier ordering
#    lever, ablated 2026-07-25). Base-season snap share (`offense_pct`) is a validated volume/role
#    signal that separates entrenched starters ("volume-EARNERS") from rotational depth bodies — the
#    exact RB/WR ordering gap The Fantasy Footballers beat MVP-1 on. It predicts NEXT-season per-game
#    production far better than it predicts games (ρ≈0.66 vs ≈0.20 within position), but it enters the
#    model through expected-games because that is where a leakage-safe, non-double-counting role signal
#    belongs (production continuity is already carried by the recency-weighted per-game line). The
#    blend lifted held-out within-position ρ 2019–2025: RB +0.010, WR +0.009, TE +0.004, QB +0.000
#    (a smooth plateau over blend∈[0.3,0.6]) — see run_projection_ablation.py.
#
#    POSITION-SCOPED, by design (a hypothesis-driven scope, not open tuning):
#      • RB / WR — SNAP share is the clean volume signal → blend into expected games.
#      • TE       — snap share confounds blocking vs receiving TEs, so it does NOT lift TE ordering;
#                   TARGET share (the receiving-role signal) does → blend that instead.
#      • QB       — untouched; the starter/backup games question is already governed by depth rank,
#                   and a usage blend adds only noise (it regressed QB ρ in the ablation).
_USAGE_ROLE_BLEND = 0.4          # weight on the usage-implied games term (plateau peak; 0=off=MVP-1)
# usage share → an implied full-season games expectation. An 85%-snap RB is an entrenched every-down
# starter (~15 g); a 30%-snap committee body (~7 g). Calibrated to the realized share→games map, held
# deliberately gentle (the term is blended, never a hard override) and clamped to the [1,17] game range.
_SNAP_GAMES_INTERCEPT, _SNAP_GAMES_SLOPE = 3.0, 14.0    # RB/WR: 3 + 14·snap_share
_TGT_GAMES_INTERCEPT, _TGT_GAMES_SLOPE = 6.0, 55.0      # TE: 6 + 55·target_share (share ~0.05–0.20)

# ── NF-D2 slice 3: TEAM-CHANGE / DEPTH-JUMP opportunity (ablated + SHIPPED 2026-07-26). A player who
#    changes teams and steps into a new role has opportunity their STALE OLD-TEAM per-game line does
#    not reflect — the classic breakout (a career backup signed to lead a backfield) or bust (a starter
#    buried on a new depth chart). Diagnostic: among team-changers, `corr(depth-climb, next fp/g
#    change) = +0.26`; climbers gained +1.3 fp/g, non-climbers lost −1.5. FIX: for a MOVER (base-season
#    team ≠ projection-season team) at RB/WR/TE, rescale the per-game line toward the NEW team's
#    role-level volume (the positional median fp/g at the player's new depth rank). Held-out lift over
#    the slice-1 model (2020–2025): RB +0.005 · WR +0.003 · TE +0.004 · QB +0.000, and the MOVER
#    subpopulation's within-position ρ +0.024 — robust over blend∈[0.30,0.40]. QB is excluded (its
#    scoring is volume/rush-driven, not a clean role-median; a blend added noise). Leakage-safe: the
#    projection-season team + role are set preseason (the live board reads `stg_nfl_depth_charts_current`;
#    the backtest harness uses projection-season weeks 1–3). No-op when the mover columns are absent.
_MOVER_OPP_BLEND = 0.35        # weight on the new-role volume level for a mover (0 = off = pre-slice-3)
_MOVER_OPP_CAP = 1.6           # clamp the per-player mover rescale to [1/1.6, 1.6] (guard the tail)
_MOVER_OPP_POSITIONS = ("RB", "WR", "TE")

# ── NF-D2 slice 4: VEGAS TEAM ENVIRONMENT (ablated + SHIPPED 2026-07-26, LEAKAGE-SAFE via Week-1
#    lines). A QB's fantasy output scales with the team's offensive environment; the market prices that
#    forward. The valuable forward signal (season-long implied points) LEAKS in a backtest, but a team's
#    WEEK-1 game line is set BEFORE any of the season's games are played ⇒ leakage-safe, and it is a
#    decent proxy for the season environment (corr ≈0.65). Held-out QB ρ lift over the slice-1+3 model:
#    **+0.012** (2020–2025; the leaky season-long ceiling is +0.06, so Week-1 captures ~1/5). SCOPED
#    to QB — RB/WR/TE already carry team context through their own usage line; a QB has no such volume
#    anchor, so the environment is where its cross-team ordering signal lives. The tilt is a mild
#    z-scored multiplier on the passing/rushing line, clamped. `team_env` = the projection-season team's
#    Week-1 implied points; a no-op when that column is absent (unknown forward team / no line).
#    Blend/clamp are deliberately GENTLE (≤±10% per QB): a QB's own line already partly reflects his
#    offense, so a large tilt would DOUBLE-COUNT; ρ (rank) is magnitude-insensitive, so the gentle
#    setting keeps ~85% of the lift while staying face-valid on the board (no ±20% swings).
_ENV_TILT_BLEND = 0.06                    # QB environment tilt strength (0 = off); gentle by design
_ENV_TILT_LO, _ENV_TILT_HI = 0.92, 1.10  # clamp the per-QB environment multiplier to ±~10%
_ENV_TILT_POSITIONS = ("QB",)

# ── NF-D2 slice 5: INJURY / AVAILABILITY (ablated + SHIPPED 2026-07-26). A forward roster-status flag
#    of unavailability — reserve/IR (`RES`), physically-unable-to-perform (`PUP`), non-football-injury
#    (`NFI`), or suspension (`SUS`) — set PRESEASON is a strong, leakage-safe signal that the player
#    will miss games. Empirically (2015–2024, players productive the prior year) a Week-1 status of
#    RES → 3.7 games, PUP → 2.4, SUS → 6.9 vs ACT → 13.2. The base model over-projects such a player
#    off LAST year's healthy games; this caps expected games toward the empirical status level. THE
#    OPERATOR'S CASE (a player recovering from offseason surgery who misses the first few games) lands
#    exactly on PUP/NFI. ⚠️ The held-out within-position ρ lift is only +0.002 because the ρ eval
#    filters to players with ≥6 realized games — which EXCLUDES the very players this fixes (a
#    season-ending IR player plays 0 games) — so the measured number badly UNDER-states the value; it
#    is a CORRECTNESS fix (don't rank a shelved star as startable), not a ρ optimisation. Leakage-safe:
#    the flag is a preseason designation (the live board reads the freshest projection-season roster
#    snapshot; the backtest uses the season's Week-1 status). No-op when `proj_status` is absent.
_INJURY_STATUS_GAMES_CAP = {"RES": 4.0, "PUP": 4.0, "NFI": 4.0, "SUS": 7.0}  # empirical status→games
_INJURY_OVERRIDE_BLEND = 0.7   # weight on the status cap vs the base estimate (0 = off; 1 = hard cap)

# ── NF-D11: RETURN-FROM-ABSENCE AVAILABILITY PRIOR (the second half of the projection-UNIVERSE fix;
#    bake-off + ablation 2026-07-29 → `ablation_results/nf_d11_absence_prior.md`).
#    THE UNIVERSE HALF (in `run_season_projection.resolve_base_anchor`): a player who missed the
#    ENTIRE base season used to be DELETED from the board by the base-season inner-join anchor even
#    when the 3-year window held a WR1 season (Brandon Aiyuk, Tank Dell, Jonathon Brooks, MarShawn
#    Lloyd for 2026). He is now RESCUED — anchored on his MOST-RECENT PLAYED season for
#    role/durability/sd — but only when a PROJECTION-SEASON roster/depth-chart row proves he is still
#    in the league (that gate is what keeps the anchor's real purpose: retired/out-of-league players
#    stay out).
#    THE PRIOR HALF (here): a rescued player's durability is STALE — carrying his last healthy
#    season's games forward would rank a year-out star as a full-time starter. Empirically
#    (2016–2025, 431 historical returners: a player with 0 games in Y−1, production in Y−3..Y−2, and
#    a Week-1 roster row in Y) a returner plays a mean of **4.1 games** vs **10.4** for a
#    base-season-present player, and ~43% play ZERO. So expected games is capped toward the empirical
#    return level and the games-uncertainty band is widened to the empirical returner SD — an
#    availability DISCOUNT with an HONEST band, never a rosy point.
#    The level is fit IN-FOLD per candidate family (`fit_absence_return_prior`); the shipped
#    family/blend are the ablation winners. `_ABSENCE_FALLBACK_*` are the pooled empirical constants
#    used when no history is available (a degraded but still-conservative prior, not a no-op).
#    ⭐ SHIPPED = the `ratio` family at full weight — a MULTIPLICATIVE haircut on the player's OWN
#    expected games (the in-fold returner ÷ base-anchored mean-games ratio, ≈0.4), which beat every
#    absolute-level family AND the direct-learned foil on held-out returner CRPS over 2017–2025
#    (13.52 vs 18.36 rescue-with-no-prior; PBO 0.0 over 126 season splits; oracle respected,
#    degenerate-zero beaten). It wins because it PRESERVES the ordering among returners — a WR1
#    coming back still outranks a fringe returner — while cutting the level hard, where a flat level
#    flattens them into each other. See `ablation_results/nf_d11_absence_prior.md`.
_ABSENCE_TIER_EDGES = (50.0, 120.0)   # pre-registered prior-production tier edges (best window PPR)
_ABSENCE_FALLBACK_LEVEL = 4.1         # pooled 2016–2025 returner mean games
_ABSENCE_FALLBACK_SD = 5.4            # pooled 2016–2025 returner games SD
_ABSENCE_HEALTHY_MEAN_GAMES = 10.4    # pooled base-season-present mean games (the `ratio` denominator)
_ABSENCE_MIN_FIT_N = 20               # below this the fit falls back to the pooled constants
_ABSENCE_MIN_CELL_N = 15              # below this a cell falls back to the pooled returner mean
_ABSENCE_PRIOR_FAMILY = "ratio"       # ⬅ NF-D11 bake-off winner (21 configs, CRPS, PBO 0.0)
_ABSENCE_PRIOR_BLEND = 1.0            # ⬅ apply the in-fold-FITTED haircut in full (0 = off)

# ── NF-D2 #6 / NF-D3: ADP MARKET-CONSENSUS PRIOR (ablated 2026-07-26). Preseason ADP (Fantasy Football
#    Calculator real-draft consensus, snapshotted before Week 1 ⇒ leakage-safe) is the single strongest
#    forward ordering signal — it prices everything public the box-score line cannot see (offseason
#    moves, holdouts, camp buzz, coaching/scheme, rookie draft capital). Blended in, it lifts held-out
#    within-position ρ substantially; ADP-ALONE is a very strong NF-D3 benchmark.
#    ⚠️ SHIPPED OFF BY DESIGN (`_ADP_PRIOR_BLEND = 0.0`). This projection is a NON-MARKET product
#    (roadmap §0: "market-blind for non-market models"); its EDGE is precisely the DISAGREEMENTS with
#    consensus, so blanket-blending ADP into every player would just make the board a laggy
#    market-follower and destroy the disagreement value. ADP is therefore wired as (a) the NF-D3
#    BENCHMARK and (b) an OPTIONAL prior (turn on via `adp_prior_blend > 0`) whose ρ-lift-vs-independence
#    tradeoff `run_adp_ablation.py` quantifies. The blend is a within-position QUANTILE REMAP: it
#    reorders a position's players toward the blended (model, ADP) score while preserving that
#    position's exact projected-points multiset, so cross-position scale + the downstream raw-line
#    scoring stay intact. No-op when the `adp` column is absent or blend == 0.
_ADP_PRIOR_BLEND = 0.0

# ── NF-D7: EXPECTED-TD / TD REGRESSION (`xfp_source.py`). TDs are the biggest AND noisiest fantasy
#    driver: a season's realized rush/rec TD count is a high-variance draw around the TDs a player's
#    OPPORTUNITY implies (goal-line carries, end-zone/red-zone targets). NF-D7 assigns every carry and
#    target a league TD-conversion probability from its field-position bucket and sums to an EXPECTED-TD
#    rate; regressing the realized per-game TD rate toward that expected rate is a strictly better
#    forward predictor of next-year TDs (validated: rush forward ρ 0.618 xTD vs 0.578 actual; rec 50/50
#    blend beats either). This blends the base-season window-weighted `rush_td_pg`/`rec_td_pg` toward the
#    leakage-safe expected rate (`xrush_td_pg`/`xrec_td_pg`, joined onto the base season) BEFORE the
#    positional shrink, so a lucky/unlucky TD year does not anchor the projection. Passing TDs are left
#    alone (volume/scheme-driven, not field-position-noise like rush/rec finishing). No-op when the
#    xTD columns are absent or `xfp_td_blend == 0`; the SHIPPED value is set by the NF-D7 ablation.
_XFP_TD_BLEND = 0.0

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


def blend_usage_into_games(
    base_eg: pd.Series,
    position: pd.Series,
    snap_share: pd.Series | None,
    target_share: pd.Series | None,
    blend: float = _USAGE_ROLE_BLEND,
) -> pd.Series:
    """NF-D2 slice 1 — refine the role/durability expected-games estimate with a base-season
    USAGE-SHARE role signal, position-scoped (RB/WR ← snap share; TE ← target share; QB untouched).

    Leakage-safe: snap/target share are realized BASE-season quantities, known at projection time.
    Non-double-counting: this modifies only expected GAMES (playing-time), never the per-game line
    (which already carries production). Where a player's usage share is unknown (a base-season
    snap-count gap) the estimate falls through to the unchanged role/durability `base_eg`. Returns the
    blended games, clamped to [1, 17]. `blend=0` is a no-op ⇒ the exact MVP-1 baseline (ablation off).
    """
    eg = pd.to_numeric(base_eg, errors="coerce").to_numpy(dtype=float)
    if blend <= 0.0:
        return pd.Series(np.clip(eg, 1.0, 17.0), index=base_eg.index)
    pos = np.array([(p or "").upper() for p in position], dtype=object)
    snap = (pd.to_numeric(snap_share, errors="coerce").to_numpy(dtype=float)
            if snap_share is not None else np.full(len(eg), np.nan))
    tgt = (pd.to_numeric(target_share, errors="coerce").to_numpy(dtype=float)
           if target_share is not None else np.full(len(eg), np.nan))

    # RB/WR ← snap-share-implied games
    snap_games = np.clip(_SNAP_GAMES_INTERCEPT + _SNAP_GAMES_SLOPE * snap, 1.0, 17.0)
    use_snap = np.isfinite(snap) & np.isin(pos, ("RB", "WR", "FB"))
    eg = np.where(use_snap, (1.0 - blend) * eg + blend * snap_games, eg)
    # TE ← target-share-implied games (receiving role, not blocking snaps)
    tgt_games = np.clip(_TGT_GAMES_INTERCEPT + _TGT_GAMES_SLOPE * tgt, 1.0, 17.0)
    use_tgt = np.isfinite(tgt) & (pos == "TE")
    eg = np.where(use_tgt, (1.0 - blend) * eg + blend * tgt_games, eg)
    return pd.Series(np.clip(eg, 1.0, 17.0), index=base_eg.index)


def role_volume_prior(base_season: pd.DataFrame) -> dict:
    """NF-D2 slice 3 — the (position, depth-rank) → typical per-game fantasy VOLUME level, learned
    IN-FOLD from the base season: the median realized base-season PPR/game among qualified players at
    each (position, depth-rank bucket 1–4). This is the role level a team-changer's projection is
    pulled toward. Pure; leakage-safe (base-season only). Returns {(position, rank): fp_pg_median}.
    NF-D11: computed over BASE-ANCHORED rows only, so the rescued-player universe cannot move it."""
    b = base_anchored_rows(base_season).copy()
    scored = score_line(
        b.assign(**{"proj_" + s: pd.to_numeric(b.get(s + "_pg"), errors="coerce").fillna(0.0)
                    for s in _VET_PERGAME_STATS}), prefix="proj_")
    fp_pg = scored["proj_fp_ppr"].to_numpy()
    rk = pd.to_numeric(b.get("depth_chart_position_rank"), errors="coerce").clip(1, 4)
    gp = pd.to_numeric(b.get("games_played"), errors="coerce").fillna(0.0)
    q = pd.DataFrame({"position": b["position"].to_numpy(), "rk": rk.to_numpy(),
                      "fp_pg": fp_pg, "gp": gp.to_numpy()})
    q = q[(q["gp"] >= _PRIOR_MIN_GAMES) & q["rk"].notna()]
    return {(pos, int(r)): float(g["fp_pg"].median())
            for (pos, r), g in q.groupby(["position", "rk"])}


def mover_opportunity_scale(
    df: pd.DataFrame,
    rvp: dict,
    fp_per_game: np.ndarray,
    blend: float = _MOVER_OPP_BLEND,
    cap: float = _MOVER_OPP_CAP,
) -> np.ndarray:
    """NF-D2 slice 3 — the per-player multiplicative rescale for team-CHANGERS. For a mover (base_team
    ≠ proj_team) at an `_MOVER_OPP_POSITIONS` position with a known new depth rank, pull the projected
    per-game volume toward the new role's level `rvp[(pos, new_rank)]`; the scale is that blended
    per-game divided by the current per-game, clamped to [1/cap, cap]. Everyone else → 1.0 (no-op).

    Leakage-safe: base_team/proj_team/depth_chart_position_rank are all preseason-known. Returns an
    array of length len(df). A no-op (all 1.0) when the mover columns are absent or blend == 0."""
    n = len(df)
    if blend <= 0.0 or not rvp or "base_team" not in df.columns or "proj_team" not in df.columns:
        return np.ones(n)
    pos = np.array([(p or "").upper() for p in df["position"]], dtype=object)
    base_team = df["base_team"].astype("string")
    proj_team = df["proj_team"].astype("string")
    moved = (base_team != proj_team) & base_team.notna() & proj_team.notna()
    new_rank = pd.to_numeric(df.get("depth_chart_position_rank"), errors="coerce").to_numpy()
    role_level = np.array([
        rvp.get((pos[i], int(np.clip(new_rank[i], 1, 4))), np.nan) if np.isfinite(new_rank[i]) else np.nan
        for i in range(n)])
    fp_pg = np.asarray(fp_per_game, dtype=float)
    apply = (moved.to_numpy() & np.isin(pos, _MOVER_OPP_POSITIONS)
             & np.isfinite(role_level) & np.isfinite(new_rank) & (fp_pg > 1e-6))
    blended = np.where(apply, (1.0 - blend) * fp_pg + blend * role_level, fp_pg)
    scale = np.where(apply, np.clip(blended / np.where(fp_pg < 1e-6, 1e-6, fp_pg), 1.0 / cap, cap), 1.0)
    return scale


def injury_availability_games(df: pd.DataFrame, blend: float = _INJURY_OVERRIDE_BLEND) -> np.ndarray:
    """NF-D2 slice 5 — expected games adjusted for a forward roster-status unavailability flag. For a
    player whose projection-season status is in `_INJURY_STATUS_GAMES_CAP` (RES/PUP/NFI/SUS), blend the
    base expected-games estimate toward the empirical status-level games (a cap the base line can only
    move DOWN toward, never up). Everyone else is unchanged. Pure; leakage-safe (a preseason flag).
    Returns the adjusted `proj_games` array; a no-op (returns proj_games unchanged) when the
    `proj_status` column is absent or blend == 0."""
    eg = pd.to_numeric(df["proj_games"], errors="coerce").to_numpy(dtype=float)
    if blend <= 0.0 or "proj_status" not in df.columns:
        return eg
    st = df["proj_status"].astype("string")
    cap = st.map(_INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)   # NaN where not a flagged status
    flagged = np.isfinite(cap)
    return np.where(flagged, (1.0 - blend) * eg + blend * np.minimum(eg, cap), eg)


def absence_tier(prior_best_fp) -> np.ndarray:
    """NF-D11 — the PRE-REGISTERED prior-production tier of a returning player, off the best single
    season (convenience PPR total) in his 3-year window: `low` (<50), `mid` (50–120), `high` (>120).
    The edges are fixed a-priori (roughly: never-productive / rotational / fantasy-startable), NOT
    tuned — the tier LEVELS are what the in-fold fit learns. Unknown/NaN → `low` (conservative)."""
    fp = pd.to_numeric(pd.Series(prior_best_fp), errors="coerce").to_numpy(dtype=float)
    out = np.full(len(fp), "low", dtype=object)
    out[np.isfinite(fp) & (fp >= _ABSENCE_TIER_EDGES[0])] = "mid"
    out[np.isfinite(fp) & (fp >= _ABSENCE_TIER_EDGES[1])] = "high"
    return out


@dataclass
class AbsenceReturnPrior:
    """NF-D11 — the fitted RETURN-FROM-ABSENCE availability prior: for a player who missed an ENTIRE
    season and is back on a projection-season roster, the empirical expected-GAMES level his
    stale-durability estimate is capped toward, plus the empirical games SD that widens his band.

    `family` is the candidate class (the §0.5 bake-off arms — see `fit_absence_return_prior`):
      • `flat`   — one pooled level for every returner.
      • `tier`   — a level per PRE-REGISTERED prior-production tier (low/mid/high).
      • `missed` — a level per number of consecutive seasons missed (1 vs ≥2).
      • `ratio`  — a multiplicative haircut on the player's OWN stale durability estimate
                   (returner mean games ÷ base-anchored mean games), not an absolute level.
      • `learned`— the DIRECT-LEARNED FOIL: a least-squares fit of realized return-year games on
                   (prior-season games, log1p prior best PPR, seasons missed, QB flag).
    Every parameter is fit IN-FOLD (target seasons ≤ the base season) — never on the season being
    projected. `sd` is the realized games SD in the same cell (an honest, empirical band width)."""

    family: str
    levels: dict = field(default_factory=dict)      # cell key → expected games
    sds: dict = field(default_factory=dict)         # cell key → realized games SD
    coefs: dict = field(default_factory=dict)       # `learned` family only
    n_fit: int = 0
    fallback_level: float = _ABSENCE_FALLBACK_LEVEL
    fallback_sd: float = _ABSENCE_FALLBACK_SD

    # ── cell keys ───────────────────────────────────────────────────────────────────────────
    def _cells(self, df: pd.DataFrame) -> np.ndarray:
        if self.family == "tier":
            return absence_tier(df.get("prior_best_fp"))
        if self.family == "missed":
            sm = pd.to_numeric(df.get("seasons_missed"), errors="coerce").fillna(1).to_numpy()
            return np.where(sm >= 2, "2plus", "1")
        return np.full(len(df), "all", dtype=object)

    def level(self, df: pd.DataFrame) -> np.ndarray:
        """The per-row expected-games LEVEL (NaN where the prior has nothing to say)."""
        n = len(df)
        if self.family == "ratio":
            eg = pd.to_numeric(df.get("proj_games"), errors="coerce").to_numpy(dtype=float)
            return eg * float(self.levels.get("ratio", 1.0))
        if self.family == "learned":
            return self._learned_level(df)
        cells = self._cells(df)
        return np.array([float(self.levels.get(c, self.fallback_level)) for c in cells])

    def sd(self, df: pd.DataFrame) -> np.ndarray:
        """The per-row realized games SD for the returner's cell (drives the honest wide band)."""
        if self.family in ("ratio", "learned"):
            return np.full(len(df), float(self.sds.get("all", self.fallback_sd)))
        cells = self._cells(df)
        return np.array([float(self.sds.get(c, self.fallback_sd)) for c in cells])

    def _learned_level(self, df: pd.DataFrame) -> np.ndarray:
        x = _absence_design_matrix(df)
        if not self.coefs or x is None:
            return np.full(len(df), float(self.fallback_level))
        beta = np.array([self.coefs.get(k, 0.0) for k in _ABSENCE_LEARNED_FEATURES], dtype=float)
        return np.clip(x @ beta + float(self.coefs.get("intercept", 0.0)), 0.0, 17.0)


_ABSENCE_LEARNED_FEATURES = ("prior_games", "log_prior_fp", "seasons_missed", "is_qb")


def _absence_design_matrix(df: pd.DataFrame) -> np.ndarray | None:
    """The `learned` foil's feature matrix — all four columns are preseason-known (a realized prior
    season + the roster gap), so the fit stays leakage-safe."""
    if len(df) == 0:
        return None
    def _num(col: str, default: float) -> np.ndarray:
        s = df[col] if col in df.columns else pd.Series([default] * len(df), index=df.index)
        return pd.to_numeric(s, errors="coerce").fillna(default).to_numpy(dtype=float)
    pg = _num("prior_games", 0.0) if "prior_games" in df.columns else _num("games_played", 0.0)
    fp = np.clip(_num("prior_best_fp", 0.0), 0.0, None)
    sm = _num("seasons_missed", 1.0)
    pos = df["position"] if "position" in df.columns else pd.Series([""] * len(df), index=df.index)
    qb = np.array([1.0 if str(p).upper() == "QB" else 0.0 for p in pos])
    return np.column_stack([pg, np.log1p(fp), sm, qb])


def fit_absence_return_prior(history: pd.DataFrame, family: str = "tier") -> AbsenceReturnPrior:
    """NF-D11 §0.5 — fit ONE candidate family of the return-from-absence prior on the historical
    returner population. Pure.

    `history`: one row per (target season, historical returner) with `realized_games` (what he
    actually played in the return year) plus the preseason-known predictors `prior_best_fp`,
    `prior_games`, `seasons_missed`, `position`, and (for `ratio`) `healthy_mean_games`. The caller
    passes ONLY target seasons ≤ the base season, so every fit is in-fold.

    An empty/short history returns the module fallback level (the pooled empirical constant), so the
    prior degrades to a conservative constant rather than to a no-op."""
    fam = family if family in ("flat", "tier", "missed", "ratio", "learned") else "flat"
    p = AbsenceReturnPrior(family=fam, n_fit=int(len(history)))
    if history is None or len(history) < _ABSENCE_MIN_FIT_N:
        return p
    h = history.copy()
    g = pd.to_numeric(h["realized_games"], errors="coerce")
    h = h[g.notna()].assign(realized_games=g[g.notna()].to_numpy())
    if len(h) < _ABSENCE_MIN_FIT_N:
        return p
    p.sds["all"] = float(h["realized_games"].std(ddof=1) or _ABSENCE_FALLBACK_SD)

    if fam == "ratio":
        healthy = pd.to_numeric(h.get("healthy_mean_games"), errors="coerce").mean()
        denom = float(healthy) if np.isfinite(healthy) and healthy > 0 else _ABSENCE_HEALTHY_MEAN_GAMES
        p.levels["ratio"] = float(np.clip(h["realized_games"].mean() / denom, 0.05, 1.0))
        return p
    if fam == "learned":
        x = _absence_design_matrix(h)
        y = h["realized_games"].to_numpy(dtype=float)
        xd = np.column_stack([x, np.ones(len(x))])
        beta, *_ = np.linalg.lstsq(xd, y, rcond=None)
        p.coefs = {**dict(zip(_ABSENCE_LEARNED_FEATURES, beta[:-1].tolist())), "intercept": float(beta[-1])}
        return p

    if fam == "tier":
        h = h.assign(_cell=absence_tier(h.get("prior_best_fp")))
    elif fam == "missed":
        sm = pd.to_numeric(h.get("seasons_missed"), errors="coerce").fillna(1).to_numpy()
        h = h.assign(_cell=np.where(sm >= 2, "2plus", "1"))
    else:
        h = h.assign(_cell="all")
    pooled = float(h["realized_games"].mean())
    for cell, grp in h.groupby("_cell"):
        # a thin cell falls back to the POOLED returner mean, never to a 1-player estimate
        p.levels[cell] = float(grp["realized_games"].mean()) if len(grp) >= _ABSENCE_MIN_CELL_N else pooled
        p.sds[cell] = float(grp["realized_games"].std(ddof=1)) if len(grp) >= _ABSENCE_MIN_CELL_N \
            else p.sds["all"]
    p.fallback_level = pooled
    return p


def absence_return_games(df: pd.DataFrame, prior: AbsenceReturnPrior | None,
                         blend: float = _ABSENCE_PRIOR_BLEND) -> np.ndarray:
    """NF-D11 — expected games for a player RETURNING from a full missed season. For a row with
    `seasons_missed >= 1` (a base-season-absent player rescued by the most-recent-played anchor),
    blend the stale-durability expected-games estimate toward the empirical return level — a CAP the
    estimate can only move DOWN toward, never up (`min(eg, level)`), exactly like the NF-D2 slice-5
    status cap it composes with. Everyone else is unchanged.

    Pure; leakage-safe (the prior is fit on target seasons ≤ the base season, and `seasons_missed`
    is a realized roster/production gap). Returns the adjusted `proj_games`; a no-op when the
    `seasons_missed` column is absent, `prior` is None, or `blend == 0`."""
    eg = pd.to_numeric(df["proj_games"], errors="coerce").to_numpy(dtype=float)
    if blend <= 0.0 or prior is None or "seasons_missed" not in df.columns:
        return eg
    sm = pd.to_numeric(df["seasons_missed"], errors="coerce").fillna(0.0).to_numpy()
    returning = sm >= 1
    if not returning.any():
        return eg
    lvl = np.asarray(prior.level(df), dtype=float)
    ok = returning & np.isfinite(lvl)
    return np.where(ok, (1.0 - blend) * eg + blend * np.minimum(eg, lvl), eg)


def absence_games_sd(base_sd: np.ndarray, df: pd.DataFrame,
                     prior: AbsenceReturnPrior | None) -> np.ndarray:
    """NF-D11 — widen the games-uncertainty term for a returner to the EMPIRICAL games SD of the
    historical returner population (≈5 games — ~40% of returners play ZERO). Take the MAX of the
    role-based SD and the empirical one so the band can only get WIDER, never narrower: a
    return-from-injury projection must carry honest uncertainty, never a rosy point."""
    sd = np.asarray(base_sd, dtype=float)
    if prior is None or "seasons_missed" not in df.columns:
        return sd
    sm = pd.to_numeric(df["seasons_missed"], errors="coerce").fillna(0.0).to_numpy()
    ret = sm >= 1
    if not ret.any():
        return sd
    return np.where(ret, np.maximum(sd, np.asarray(prior.sd(df), dtype=float)), sd)


def environment_tilt_scale(df: pd.DataFrame, blend: float = _ENV_TILT_BLEND,
                           positions: tuple = _ENV_TILT_POSITIONS) -> np.ndarray:
    """NF-D2 slice 4 / NF-D4 — the per-position multiplicative environment tilt from the projection-
    season team's forward Vegas environment (`df['team_env']` — Week-1 implied points in the slice-4
    ship, or the NF-D4 preseason WIN TOTAL). A z-score WITHIN each tilted position's field →
    `exp(blend·z)`, clamped to [_ENV_TILT_LO, _ENV_TILT_HI]; rows outside `positions` and rows without a
    team_env → 1.0 (no-op). The tilt is UNIT-INVARIANT (it z-scores team_env), so swapping the env
    source only changes the ordering, not the mechanism. Leakage-safe (a Week-1 line / preseason win
    total is set before any of the season's games). No-op when `team_env` is absent or blend == 0.
    `positions` defaults to the shipped QB-only scope; NF-D4 ablates extending it to skill positions."""
    n = len(df)
    if blend <= 0.0 or "team_env" not in df.columns:
        return np.ones(n)
    env = pd.to_numeric(df["team_env"], errors="coerce").to_numpy()
    pos = np.array([(p or "").upper() for p in df["position"]], dtype=object)
    # NF-D11: standardise on the BASE-ANCHORED field only. The z-score's mean/sd are population
    # statistics, so admitting the rescued returners would otherwise shift every incumbent QB's tilt
    # by a hair (measured: 36/716 adjacent rank swaps) — a universe change must not silently move a
    # player it has nothing to do with. The tilt is still APPLIED to every row, returners included.
    if "seasons_missed" in df.columns:
        stat_ok = pd.to_numeric(df["seasons_missed"], errors="coerce").fillna(0.0).to_numpy() < 1
    else:
        stat_ok = np.ones(n, dtype=bool)
    scale = np.ones(n)
    for p in positions:
        idx = np.where(pos == p)[0]
        ev = env[idx]
        mk = np.isfinite(ev)
        if mk.sum() < 10:                       # too thin to standardise reliably ⇒ skip
            continue
        ref = mk & stat_ok[idx]
        if ref.sum() < 10:                      # thin base-anchored field ⇒ standardise on all
            ref = mk
        z = np.zeros(len(idx))
        z[mk] = (ev[mk] - np.nanmean(ev[ref])) / (np.nanstd(ev[ref]) or 1.0)
        scale[idx] = np.clip(np.exp(blend * z), _ENV_TILT_LO, _ENV_TILT_HI)
    return scale


def _zscore(x: np.ndarray) -> np.ndarray:
    """Finite-safe z-score. Non-finite entries stay NaN; a zero/undefined std yields all-zeros."""
    x = np.asarray(x, dtype=float)
    m = np.isfinite(x)
    z = np.full(len(x), np.nan)
    if m.sum() >= 2 and np.nanstd(x[m]) > 0:
        z[m] = (x[m] - np.nanmean(x[m])) / np.nanstd(x[m])
    elif m.sum() >= 1:
        z[m] = 0.0
    return z


def blend_adp_prior(
    df: pd.DataFrame,
    blend: float = _ADP_PRIOR_BLEND,
    adp_col: str = "adp",
    fp_col: str = "proj_fp_ppr",
    positions: tuple = SKILL_POSITIONS,
) -> np.ndarray:
    """NF-D2 #6 / NF-D3 — reorder each position's projections toward the ADP market consensus,
    PRESERVING the position's exact projected-points multiset (a within-position quantile remap).

    Blended score per player = (1-blend)·z(model fp) + blend·(−z(adp))  (lower ADP = better ⇒ +score).
    Within each position the players are re-ordered by that blended score and assigned that position's
    projected-points values in descending order — so the position keeps its exact point scale (cross-
    position comparability + the downstream raw-line rescore are untouched) while the ORDER moves toward
    the blend. A player with no ADP keeps the model score (falls through in place). Pure; leakage-safe
    (preseason ADP). Returns an adjusted `fp_col` array.

    `blend = 0` ⇒ EXACT no-op (returns `fp_col` unchanged) = the market-blind product / the ablation
    'model-only' arm. `blend = 1` ⇒ pure-ADP order over the position's points = the NF-D3 benchmark.
    No-op (returns `fp_col` unchanged) when `adp_col` is absent from `df`.
    """
    fp = pd.to_numeric(df[fp_col], errors="coerce").to_numpy(dtype=float)
    if blend <= 0.0 or adp_col not in df.columns:
        return fp
    adp = pd.to_numeric(df[adp_col], errors="coerce").to_numpy(dtype=float)
    pos = np.array([(p or "").upper() for p in df["position"]], dtype=object)
    out = fp.copy()
    for p in positions:
        idx = np.where(pos == p)[0]
        if len(idx) < 2:
            continue
        zf = _zscore(fp[idx])
        za = -_zscore(adp[idx])                       # lower ADP ⇒ higher score
        za = np.where(np.isfinite(za), za, zf)        # no ADP ⇒ keep the model score
        score = (1.0 - blend) * zf + blend * za
        score = np.where(np.isfinite(score), score, zf)
        # rank players by blended score (best first) and hand them this position's point values,
        # sorted descending — a monotone quantile remap that preserves the point multiset exactly.
        order = np.argsort(-score, kind="stable")
        sorted_points = np.sort(fp[idx])[::-1]
        remap = np.empty(len(idx), dtype=float)
        remap[order] = sorted_points
        out[idx] = remap
    return out


def _games_sd(depth_rank: pd.Series, position: pd.Series) -> pd.Series:
    """Std-dev of the games estimate (drives the interval): a proven rank-1 starter is fairly
    predictable, a rotational/backup role is far more volatile (promotion or benching)."""
    rank = pd.to_numeric(depth_rank, errors="coerce")
    sd = np.where(rank.to_numpy() == 1, 2.6, np.where(rank.to_numpy() == 2, 4.2, 4.8))
    return pd.Series(sd, index=depth_rank.index)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Conservative positional priors + shrinkage (per-game)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def base_anchored_rows(base_season: pd.DataFrame) -> pd.DataFrame:
    """NF-D11 — the subset of the projection universe anchored on the ACTUAL base season (i.e.
    excluding the most-recent-played fallback rows the NF-D11 rescue admits). Every IN-FOLD prior
    that describes "what a base season looks like" (the positional per-game prior, the role→volume
    prior) is computed over this subset, so admitting rescued players CANNOT perturb any incumbent
    player's projection — the rescue is strictly ADDITIVE. A frame without the `base_anchor` column
    (an older caller / a unit-test fixture) is returned unchanged."""
    if "base_anchor" not in base_season.columns:
        return base_season
    return base_season[base_season["base_anchor"].astype("string") == "base_season"]


def positional_pergame_priors(base_season: pd.DataFrame) -> pd.DataFrame:
    """Per-position conservative per-game anchor for each counting stat = the MEDIAN over qualified
    (games ≥ `_PRIOR_MIN_GAMES`) base-season players. The median (not the mean) is robust to the
    stud tail, so shrinking a small-sample player toward it pulls to a plausible mid-roster level,
    never to a star's line. Returns one row per position with a `<stat>_prior` column each."""
    base_season = base_anchored_rows(base_season)
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
    usage_role_blend: float = _USAGE_ROLE_BLEND,
    role_vol_prior: dict | None = None,
    mover_opportunity_blend: float = _MOVER_OPP_BLEND,
    env_tilt_blend: float = _ENV_TILT_BLEND,
    env_tilt_positions: tuple = _ENV_TILT_POSITIONS,
    injury_override_blend: float = _INJURY_OVERRIDE_BLEND,
    xfp_td_blend: float = _XFP_TD_BLEND,
    absence_prior: "AbsenceReturnPrior | None" = None,
    absence_prior_blend: float = _ABSENCE_PRIOR_BLEND,
) -> pd.DataFrame:
    """Project every base-season player's UPCOMING-season raw stat line.

    base_season: one row per (player_id) with `<stat>_pg` realized per-game counting stats,
      `games_played`, `depth_chart_position_rank`, `fp_ppr_sd` (game-to-game PPR sd), team, position,
      and (NF-D2 slice 1) base-season `snap_share` / `target_share` usage-role signals (optional —
      absent columns fall through to the MVP-1 role/durability expected-games estimate). NF-D2 slice 3
      additionally reads `base_team` + `proj_team` (base-season vs projection-season team) — a mover is
      rescaled toward the new role's volume; absent columns make the mover step a no-op.
    priors: `positional_pergame_priors(base_season)` output.
    usage_role_blend: weight on the usage-share role signal in expected games (0 = MVP-1 baseline,
      the ablation "off" arm). Position-scoped inside `blend_usage_into_games`.
    role_vol_prior: `role_volume_prior(base_season)` output (NF-D2 slice 3). None ⇒ the mover step is
      skipped (the pre-slice-3 baseline / the ablation "off" arm).
    mover_opportunity_blend: weight on the new-role volume level for a team-changer (0 = off).
    absence_prior / absence_prior_blend: NF-D11 — the fitted return-from-absence availability prior
      applied to rows the base-anchor fallback rescued (`seasons_missed >= 1`). None / 0 = the
      rescue-with-no-prior arm (a player carries his stale durability forward).
    Returns the RAW_STAT_COLS (season totals) + convenience fp + an 80% PPR interval, per player.
    """
    df = base_season.merge(priors, on="position", how="left")
    g = pd.to_numeric(df["games_played"], errors="coerce").fillna(0.0).to_numpy()

    eg = expected_games(df["games_played"], df["depth_chart_position_rank"], df["position"])
    # NF-D2 slice 1: refine expected games with the base-season usage-share role signal (snap share
    # for RB/WR, target share for TE). No-op when the columns are absent or usage_role_blend == 0.
    eg = blend_usage_into_games(
        eg, df["position"], df.get("snap_share"), df.get("target_share"), blend=usage_role_blend
    )
    df["proj_games"] = eg.to_numpy()

    # ── NF-D7: TD REGRESSION. Regress the base-season window-weighted rush/rec TD-per-game toward the
    #    opportunity-based EXPECTED per-game rate BEFORE the positional shrink, so a lucky/unlucky TD
    #    year does not anchor the projection (the noisiest fantasy driver, de-noised by opportunity).
    #    No-op when the xTD columns are absent (join miss / cache not built) or xfp_td_blend == 0.
    if xfp_td_blend > 0:
        if "xrush_td_pg" in df.columns:
            df["rush_td_pg"] = _XFP.regress_td_rate(
                pd.to_numeric(df.get("rush_td_pg"), errors="coerce").to_numpy(),
                pd.to_numeric(df.get("xrush_td_pg"), errors="coerce").to_numpy(), xfp_td_blend)
        if "xrec_td_pg" in df.columns:
            df["rec_td_pg"] = _XFP.regress_td_rate(
                pd.to_numeric(df.get("rec_td_pg"), errors="coerce").to_numpy(),
                pd.to_numeric(df.get("xrec_td_pg"), errors="coerce").to_numpy(), xfp_td_blend)

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

    # ── NF-D2 slice 3: team-change / depth-jump opportunity. For a MOVER (base_team ≠ proj_team) at
    #    RB/WR/TE, rescale the whole per-game line toward the NEW role's volume level (the stale
    #    old-team line under/over-states a role change). Scoring is linear in the stats, so one scalar
    #    per player keeps the line internally consistent; re-clamp cmp≤att, rec≤targets, then re-score.
    #    No-op when role_vol_prior is None or the base_team/proj_team columns are absent.
    if role_vol_prior and mover_opportunity_blend > 0:
        fp_pg_now = df["proj_fp_ppr"].to_numpy() / np.clip(df["proj_games"].to_numpy(), 1e-6, None)
        mscale = mover_opportunity_scale(df, role_vol_prior, fp_pg_now,
                                         blend=mover_opportunity_blend, cap=_MOVER_OPP_CAP)
        for col in ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
                    "proj_rush_att", "proj_rush_yds", "proj_rush_td",
                    "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td"):
            df[col] = df[col].to_numpy() * mscale
        df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])
        df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
        df["proj_fumbles_lost"] = np.round(
            (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)
        df = score_line(df, prefix="proj_")

    # ── NF-D2 slice 4 / NF-D4: Vegas team ENVIRONMENT tilt from the projection-season team's forward
    #    Vegas environment (`team_env` = Week-1 implied points in the slice-4 ship, or the NF-D4
    #    preseason WIN TOTAL). Disjoint from the mover step (QB vs RB/WR/TE) so order is irrelevant when
    #    QB-scoped. NF-D4: the scaled column set now includes the receiving line so `env_tilt_positions`
    #    can be widened past QB — a QB's receiving line is ~0, so including it is a no-op for the shipped
    #    QB-only scope. `proj_pass_int` stays UNSCALED by design (a better environment lifts production,
    #    not interceptions). No-op when the team_env column is absent or env_tilt_blend == 0.
    if env_tilt_blend > 0 and "team_env" in df.columns:
        escale = environment_tilt_scale(df, blend=env_tilt_blend, positions=env_tilt_positions)
        for col in ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td",
                    "proj_rush_att", "proj_rush_yds", "proj_rush_td",
                    "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td"):
            df[col] = df[col].to_numpy() * escale
        df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])
        df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
        df["proj_fumbles_lost"] = np.round(
            (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)
        df = score_line(df, prefix="proj_")

    # ── NF-D2 slice 5: INJURY / AVAILABILITY. Cap expected games for a player flagged unavailable
    #    (RES/PUP/NFI/SUS) in the projection-season roster, and rescale the whole season line by the
    #    games ratio. Applied LAST so it caps whatever the prior steps produced. No-op when the
    #    proj_status column is absent or injury_override_blend == 0.
    if injury_override_blend > 0 and "proj_status" in df.columns:
        new_games = injury_availability_games(df, blend=injury_override_blend)
        old_games = df["proj_games"].to_numpy()
        iscale = np.where(old_games > 1e-6, new_games / np.clip(old_games, 1e-6, None), 1.0)
        for col in ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
                    "proj_rush_att", "proj_rush_yds", "proj_rush_td",
                    "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td"):
            df[col] = df[col].to_numpy() * iscale
        df["proj_games"] = new_games
        df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])
        df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
        df["proj_fumbles_lost"] = np.round(
            (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)
        df = score_line(df, prefix="proj_")

    # ── NF-D11: RETURN-FROM-ABSENCE availability prior. A player rescued by the most-recent-played
    #    anchor (`seasons_missed >= 1`) carries STALE durability, so cap expected games toward the
    #    empirical return level and rescale the season line by the games ratio. Applied AFTER the
    #    slice-5 status cap so the two COMPOSE (both are min-caps ⇒ monotone; a returner who is ALSO
    #    flagged RES/PUP takes the harsher of the two, never a rebound). No-op when the prior is
    #    absent, blend == 0, or no row is a returner.
    if absence_prior_blend > 0 and absence_prior is not None and "seasons_missed" in df.columns:
        new_games = absence_return_games(df, absence_prior, blend=absence_prior_blend)
        old_games = df["proj_games"].to_numpy()
        ascale = np.where(old_games > 1e-6, new_games / np.clip(old_games, 1e-6, None), 1.0)
        for col in ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
                    "proj_rush_att", "proj_rush_yds", "proj_rush_td",
                    "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td"):
            df[col] = df[col].to_numpy() * ascale
        df["proj_games"] = new_games
        df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])
        df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
        df["proj_fumbles_lost"] = np.round(
            (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)
        df = score_line(df, prefix="proj_")

    # ── 80% interval on the convenience PPR total. Two independent sources of season variance:
    #    (a) game-to-game scoring variance accumulated over the played games (sd·√games), and
    #    (b) games-played uncertainty (per-game mean × games sd). Normal approx, floored at 0.
    fp_pg_sd = pd.to_numeric(df.get("fp_ppr_sd"), errors="coerce").fillna(0.0).to_numpy()
    fp_ppr = df["proj_fp_ppr"].to_numpy()
    eg_arr = np.clip(df["proj_games"].to_numpy(), 1e-6, None)
    fp_per_game = fp_ppr / eg_arr
    gsd = _games_sd(df["depth_chart_position_rank"], df["position"]).to_numpy()
    # NF-D11: a returner's games uncertainty is the EMPIRICAL returner SD (~5 games — 43% of them
    # play zero), never the tidy role-based one. Widen-only, so the band is honest by construction.
    gsd = absence_games_sd(gsd, df, absence_prior if absence_prior_blend > 0 else None)
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
    # NF-D11: a rescued returner is projected off a STALE season — never claim high confidence for
    # him, whatever his last healthy year's game count was.
    if "seasons_missed" in df.columns:
        ret = pd.to_numeric(df["seasons_missed"], errors="coerce").fillna(0.0).to_numpy() >= 1
        df["confidence"] = np.where(ret, "low", df["confidence"])
        df["source"] = np.where(ret, "veteran_returning", df["source"])
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
    # NF1.4: the CALIBRATED 80% rookie band. (position, prediction-tercile) -> (p10, p90) in fp,
    # read off the realized outcomes of the FULL drafted population; empty ⇒ the legacy cv band.
    fp_bands: dict = field(default_factory=dict)
    fp_band_cuts: dict = field(default_factory=dict)       # position -> (tercile cut 1, cut 2)

    def band(self, position: str, pred: float) -> tuple[float, float] | None:
        """The calibrated 80% interval for one rookie, or None when no band was fitted (the caller
        then falls back to the legacy `fp × cv` width). Always brackets the point projection — a
        band that excluded its own point estimate would be incoherent."""
        cuts = self.fp_band_cuts.get(position)
        if cuts is None:
            return None
        c1, c2 = cuts
        b = 0 if pred <= c1 else (1 if pred <= c2 else 2)
        lohi = self.fp_bands.get((position, b))
        if lohi is None:
            return None
        lo, hi = lohi
        return (max(0.0, min(lo, pred)), max(hi, pred))

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


def fit_rookie_slot_curves(hist: pd.DataFrame, band_hist: pd.DataFrame | None = None) -> RookieSlotCurve:
    """Fit the composite rookie model from prior classes.

    hist: one row per historical drafted rookie (skill positions) with `position_group`,
      `draft_overall`, `games`, `rookie_fp_ppr`, and the rookie-year raw stat TOTALS
      (`_ROOKIE_RAW_STATS` cols) — the training base for the fp curve + the stat composition.

    band_hist (NF1.4): the SAME history over the FULL DRAFTED POPULATION — every drafted skill
      rookie including the ~15% (35% at QB) who never played a snap, carried as a real `rookie_fp_ppr
      = 0`. Used ONLY to calibrate the 80% interval; the point curve is unchanged. See
      `_fit_rookie_bands` for why the interval needs the un-filtered population and the curve does
      not. Omit it and the projection falls back to the legacy `fp × cv` width."""
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
    if band_hist is not None and not band_hist.empty:
        _fit_rookie_bands(curve, band_hist)
    return curve


# The nominal rookie interval. 80% central ⇒ the 10th/90th percentiles of the realized outcome.
_ROOKIE_BAND_Q = (0.10, 0.90)
_ROOKIE_BAND_MIN_N = 15


def _fit_rookie_bands(curve: RookieSlotCurve, band_hist: pd.DataFrame) -> None:
    """NF1.4 — calibrate the rookie 80% band EMPIRICALLY, from what drafted rookies actually did.

    ⚠️ THE DEFECT THIS FIXES (measured over draft classes 2019–2025, walk-forward): MVP-1's rookie
    band is `fp ± 1.2816·fp·cv`, with the cv estimated on the SURVIVOR-filtered fit sample. Its
    realized coverage of the nominal 80% is **0.678 overall and 0.444 at QB** — the band is not an
    80% interval, it is a decoration, and its own report said "recalibrate before pricing." A
    multiplicative width also collapses to nothing as the projection approaches zero, so the late-
    round rookies who most often surprise get the narrowest band.

    THE CURE: within a position, bucket the curve's predictions into terciles and take the empirical
    q10/q90 of the REALIZED rookie seasons in each bucket. Two properties the cv band lacked —
      • the population is the FULL drafted class, zero-game rookies included, so the p10 tells the
        truth that a late pick's most likely outcome is ~nothing;
      • the width is read off outcomes rather than asserted, so coverage is a measurable claim
        (`0.834` overall / `0.827` at QB with this band).
    The POINT projection is untouched: this is an interval-calibration fix, not a model change.
    """
    lo_q, hi_q = _ROOKIE_BAND_Q
    pos = band_hist["position_group"].astype(str)
    overall = pd.to_numeric(band_hist["draft_overall"], errors="coerce")
    real = pd.to_numeric(band_hist.get("rookie_fp_ppr"), errors="coerce")
    for p in pos.unique():
        m = (pos == p) & overall.notna() & real.notna()
        if int(m.sum()) < _ROOKIE_BAND_MIN_N or p not in curve.fp_mean:
            continue
        pred = np.array([curve.predict_fp(p, o) for o in overall[m]], dtype=float)
        y = real[m].to_numpy(dtype=float)
        c1, c2 = float(np.quantile(pred, 1 / 3)), float(np.quantile(pred, 2 / 3))
        curve.fp_band_cuts[p] = (c1, c2)
        for b, sel in enumerate((pred <= c1, (pred > c1) & (pred <= c2), pred > c2)):
            if int(sel.sum()) >= max(5, _ROOKIE_BAND_MIN_N // 3):
                curve.fp_bands[(p, b)] = (float(np.quantile(y[sel], lo_q)),
                                          float(np.quantile(y[sel], hi_q)))


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

    # ── the 80% rookie interval ────────────────────────────────────────────────────────────────
    # NF1.4: prefer the CALIBRATED band (empirical q10/q90 of what drafted rookies in this
    # prediction tercile actually scored — realized coverage 0.834 vs the nominal 0.80). The legacy
    # `fp × cv` parameter-uncertainty width is the fallback for a curve fitted without `band_hist`;
    # it covers only 0.678 (0.444 at QB), so it is a decoration rather than an 80% interval and is
    # kept solely so an un-migrated caller still gets *a* band. See `_fit_rookie_bands`.
    fp = df["proj_fp_ppr"].to_numpy()
    cv = np.array([curve.fp_cv_by_pos.get(p, 0.7) for p in pos_group])
    z80 = 1.2815515594
    calibrated = [curve.band(pos_group[i], float(fp[i])) for i in range(len(df))]
    have_band = any(b is not None for b in calibrated)
    lo = np.array([b[0] if b else max(0.0, fp[i] - z80 * fp[i] * cv[i])
                   for i, b in enumerate(calibrated)])
    hi = np.array([b[1] if b else fp[i] + z80 * fp[i] * cv[i] for i, b in enumerate(calibrated)])
    df["fp_ppr_sd"] = np.round((hi - lo) / (2 * z80), 2)   # the band's implied 1-sd equivalent
    # Round the bounds OUTWARD (p10 down, p90 up). `band()` guarantees lo ≤ point ≤ hi, but
    # nearest-rounding can push a bound past a point projection it exactly equals and emit a
    # displayed interval that excludes its own point estimate.
    df["fp_ppr_p10"] = np.floor(np.clip(lo, 0.0, None) * 10.0) / 10.0
    df["fp_ppr_p90"] = np.ceil(hi * 10.0) / 10.0
    df["uncertainty_type"] = "calibrated" if have_band else "parameter"
    df["is_rookie"] = True
    df["source"] = "rookie"
    df["projection_season"] = int(projection_season)
    df["confidence"] = "low"  # rookies are inherently high-variance
    df["fp_ppr_l5"] = np.nan
    return df


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF1.4 — the rookie FACE-VALIDITY gate on an emitted board
# ══════════════════════════════════════════════════════════════════════════════════════════════
# How far down the board a rookie may sit before the placement is worth flagging. Anchored on what
# actually happens: over draft classes 2019–2025 the #1-overall rookie QB was projected QB11–QB15
# and finished QB8–QB25 (mean rank ≈ QB19.5), so a rookie inside the overall top 10 is the
# placement that has never been earned.
_FACE_VALIDITY_TOP_N = 10


def rookie_board_face_validity(board: pd.DataFrame, rookie_history: pd.DataFrame,
                               *, fp_col: str = "proj_fp_ppr", top_n: int = _FACE_VALIDITY_TOP_N,
                               quantile: float = 0.90, min_classes: int = 3) -> dict:
    """Flag rookie OVER-PLACEMENT on an emitted (veterans + rookies) board — the NF1.4 gate.

    Two checks, both anchored on realized history rather than an arbitrary threshold:
      1. **placement** — the #1 overall board slot is a veteran, and no rookie sits inside the
         overall top `top_n`. This is the symptom MVP-3 dogfooding raised ("a rookie QB floated to
         #1 overall"); on the 2019–2025 boards MVP-1 put a rookie in the overall top 12 twice, both
         #1-overall QBs (Trevor Lawrence → finished QB23; Cam Ward → QB22).
      2. **level** — per position, the TOP projected rookie is compared against the Q`quantile` of
         the per-class BEST realized rookie at that position over prior classes. In words: "does
         this board project someone above what the best rookie in a strong class actually does?"

    ⚠️ THE REFERENCE CLASS IS THE WHOLE GAME HERE, and getting it wrong makes the gate useless.
    The first cut of this check compared the top projected rookie against the Q90 of ALL drafted
    rookies — but the best rookie at a position IS, by construction, near the top of that
    distribution, so the bar was one almost every board clears: measured over 2019–2025 the
    **REALIZED** top rookie exceeded it in **25 of 28** cohort-positions, and the gate fired on
    7/7 cohorts. A check that always fires carries no information. Against the corrected
    top-of-class reference the incumbent breaches **0/28** while reality breaches **9/28** — the
    gate is a genuine tripwire, and its silence is itself another reading of NF1.4's central
    finding that the rookie prior runs COLD.

    `rookie_history` needs `position_group`, `rookie_fp_ppr` and `draft_year` (the per-class max
    needs the class). A position with fewer than `min_classes` prior classes is skipped rather than
    judged on a reference too thin to mean anything. ADVISORY, not a HALT: this is a projection
    product and a genuinely exceptional class should be able to trip it — it exists so the board is
    checked rather than assumed. Returns every measurement plus `pass`.
    """
    out: dict = {"pass": True, "n_rookies": 0, "placement": {}, "level": {}}
    if board is None or board.empty or fp_col not in board.columns:
        return {**out, "note": "empty board"}

    ranked = board.sort_values(fp_col, ascending=False).reset_index(drop=True)
    is_rk = (ranked["is_rookie"].fillna(False).astype(bool) if "is_rookie" in ranked
             else pd.Series(False, index=ranked.index))
    out["n_rookies"] = int(is_rk.sum())
    top = ranked[is_rk].head(1)
    out["placement"] = {
        "top1_is_rookie": bool(is_rk.iloc[0]),
        f"n_rookies_in_top{top_n}": int(is_rk.head(top_n).sum()),
        "best_rookie_overall_rank": int(ranked[is_rk].index[0]) + 1 if len(top) else None,
        "best_rookie": None if top.empty else str(top.iloc[0].get("player_name")),
    }

    pos_col = "position" if "position" in ranked.columns else "position_group"
    caps, over = {}, []
    if "draft_year" in rookie_history.columns:
        for p, h in rookie_history.groupby(rookie_history["position_group"].astype(str)):
            per_class_best = (h.assign(_fp=pd.to_numeric(h["rookie_fp_ppr"], errors="coerce"))
                              .groupby("draft_year")["_fp"].max().dropna())
            if len(per_class_best) < min_classes:
                continue
            cap = float(np.quantile(per_class_best.to_numpy(), quantile))
            caps[p] = round(cap, 1)
            proj = pd.to_numeric(ranked[is_rk & (ranked[pos_col].astype(str) == p)][fp_col],
                                 errors="coerce")
            if len(proj) and float(proj.max()) > cap:
                over.append({"position": p, "max_projected": round(float(proj.max()), 1),
                             "top_of_class_cap": round(cap, 1),
                             "n_reference_classes": int(len(per_class_best))})
    out["level"] = {"top_of_class_caps": caps, "positions_over_cap": over,
                    "reference": f"Q{int(quantile * 100)} of the per-class BEST realized rookie"}
    out["pass"] = (not out["placement"]["top1_is_rookie"]
                   and out["placement"][f"n_rookies_in_top{top_n}"] == 0
                   and not over)
    return out
