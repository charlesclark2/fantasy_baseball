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
    band_model: "VeteranBandModel | None" = None,
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
    band_model: NF1.9 — the fitted PER-PLAYER veteran 80% band (`fit_veteran_band_model`). None ⇒ the
      pre-NF1.9 NORMAL APPROXIMATION, whose measured coverage of its own nominal 80% is only ~0.55.
      A row the model cannot speak to falls back to that normal band, labelled honestly.
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
    z80 = _Z80_SEASON
    df["fp_ppr_sd"] = np.round(season_sd, 2)
    # ⚠️ THE UNROUNDED SEASON SD, retained OUTSIDE the emitted schema (`OUTPUT_COLS` carries only the
    #    2-dp display column). NF1.9 needs it: the band model is fed the unrounded `season_sd` at serve
    #    time, so a historical panel that stored the ROUNDED one would fit the band on a systematically
    #    different feature than it is served with — and it would make the served-band reproduction proof
    #    disagree by exactly one rounding step, which is how this was caught.
    df["fp_ppr_sd_raw"] = season_sd

    # ── the 80% veteran interval. TWO TIERS, best first (NF1.9):
    #  1. `band_model` — a PER-PLAYER CONDITIONAL-QUANTILE band, selected on a PROPER interval score
    #     with a PER-POSITION coverage FLOOR (`run_veteran_interval_ablation.py`).
    #  2. the NORMAL APPROXIMATION below — `point ± 1.2816·season_sd`. Kept as the honest fallback for
    #     a row the fit cannot speak to, and labelled `empirical` so the tier is never overstated.
    #     ⚠️ Its MEASURED coverage of its own nominal 80% is ~0.55 (held-out target seasons 2013–2025),
    #     missing on BOTH tails: a symmetric normal cannot fit a right-skewed season total, and a
    #     game-to-game sd measured on the games a player DID play cannot price the availability/role
    #     risk that is the dominant veteran uncertainty. It is a fallback, not a band.
    lo = np.clip(fp_ppr - z80 * season_sd, 0.0, None)
    hi = fp_ppr + z80 * season_sd
    tier = np.full(len(df), "empirical", dtype=object)
    if band_model is not None:
        frame = veteran_band_inputs(
            df["position"], fp_ppr, season_sd, proj_games=df["proj_games"],
            base_games=df.get("games_played"), snap_share=df.get("snap_share"),
            seasons_missed=df.get("seasons_missed"))
        b_lo, b_hi = band_model.band_many(frame)
        use = np.isfinite(b_lo) & np.isfinite(b_hi) & (b_hi >= b_lo)
        lo = np.where(use, b_lo, lo)
        hi = np.where(use, b_hi, hi)
        tier = np.where(use, "calibrated_per_player", tier).astype(object)
    # Round the bounds OUTWARD (p10 down, p90 up). Both tiers guarantee lo ≤ point ≤ hi, but
    # nearest-rounding can push a bound past a point projection it exactly equals and emit a displayed
    # interval that excludes its own point estimate (the same fix `project_rookies` carries).
    # ⚠️ …and the min/max clamps are load-bearing: `floor(x*10)/10` is NOT always ≤ x, because `x*10`
    # can round UP to an integer in float64 (`3.6999999999999997*10 == 37.0`), so the "outward" rounding
    # would land ~1e-15 INSIDE the bound and re-emit exactly the incoherence it exists to prevent.
    lo = np.clip(lo, 0.0, None)
    df["fp_ppr_p10"] = np.minimum(np.floor(lo * 10.0) / 10.0, lo)
    df["fp_ppr_p90"] = np.maximum(np.ceil(hi * 10.0) / 10.0, hi)
    df["uncertainty_type"] = tier
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
    # NF1.7: the PER-PLAYER 80% band that SUPERSEDES the tercile buckets above (which are retained
    # as the fallback + as the bake-off's degenerate-ceiling anchor). None ⇒ no per-player fit.
    band_model: "RookieBandModel | None" = None

    def band(self, position: str, pred: float) -> tuple[float, float] | None:
        """The CLASS-LEVEL (tercile-bucket) 80% interval for one rookie, or None when no band was
        fitted (the caller then falls back to the legacy `fp × cv` width). Always brackets the point
        projection — a band that excluded its own point estimate would be incoherent.

        ⚠️ NF1.7 SUPERSEDED this as the served band: it quantises to ~3 intervals per position, so
        every rookie in a bucket carries a byte-identical range while their point projections span an
        order of magnitude. It is kept because it is the pre-NF1.7 incumbent (the bake-off's
        degenerate-ceiling anchor) and the fallback when the per-player fit has too little history.
        Prefer `band_model.band_many(...)`."""
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


def fit_rookie_slot_curves(hist: pd.DataFrame, band_hist: pd.DataFrame | None = None,
                           *, band_form: str | None = None, band_k: int | None = None,
                           band_resid_sd_gain: float | None = None,
                           band_qreg_alpha: float | None = None,
                           band_qreg_per_pos: bool | None = None,
                           band_cqr_mode: str | None = None,
                           band_cqr_scale: str | None = None,
                           band_cqr_k: int | None = None,
                           per_player_band: bool = True) -> RookieSlotCurve:
    """Fit the composite rookie model from prior classes.

    hist: one row per historical drafted rookie (skill positions) with `position_group`,
      `draft_overall`, `games`, `rookie_fp_ppr`, and the rookie-year raw stat TOTALS
      (`_ROOKIE_RAW_STATS` cols) — the training base for the fp curve + the stat composition.

    band_hist (NF1.4): the SAME history over the FULL DRAFTED POPULATION — every drafted skill
      rookie including the ~15% (35% at QB) who never played a snap, carried as a real `rookie_fp_ppr
      = 0`. Used ONLY to calibrate the 80% interval; the point curve is unchanged. See
      `_fit_rookie_bands` for why the interval needs the un-filtered population and the curve does
      not. Omit it and the projection falls back to the legacy `fp × cv` width.

    NF1.7: when `band_hist` is supplied, a PER-PLAYER band model (`fit_rookie_band_model`) is fitted
      on top of it and becomes the served band; the NF1.4 tercile buckets stay as the fallback. The
      `band_*` overrides exist for the bake-off harness — production leaves them at the module
      defaults (the selected form). `per_player_band=False` reproduces the NF1.4 incumbent exactly,
      which is what the bake-off's degenerate-ceiling anchor needs."""
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
        if per_player_band:
            # NF1.7 — the served band. Conditioned on the SAME served point projection the board
            # displays (`rookie_point_projection`), so the interval is centred on the number the user
            # sees rather than on a bucket it was averaged into.
            curve.band_model = fit_rookie_band_model(
                band_hist, rookie_point_projection(band_hist, curve),
                form=_ROOKIE_BAND_FORM if band_form is None else band_form,
                k=_ROOKIE_BAND_K if band_k is None else band_k,
                resid_sd_gain=(_ROOKIE_BAND_RESID_SD_GAIN if band_resid_sd_gain is None
                               else band_resid_sd_gain),
                qreg_alpha=(_ROOKIE_BAND_QREG_ALPHA if band_qreg_alpha is None
                            else band_qreg_alpha),
                qreg_per_pos=(_ROOKIE_BAND_QREG_PER_POS if band_qreg_per_pos is None
                              else band_qreg_per_pos),
                cqr_mode=_ROOKIE_BAND_CQR_MODE if band_cqr_mode is None else band_cqr_mode,
                cqr_scale=_ROOKIE_BAND_CQR_SCALE if band_cqr_scale is None else band_cqr_scale,
                cqr_k=_ROOKIE_BAND_CQR_K if band_cqr_k is None else band_cqr_k)
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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF1.7 — the PER-PLAYER rookie 80% band (bake-off: run_rookie_interval_ablation.py)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ THE DEFECT (NF3 surfacing, 2026-07-29): NF1.4's band above is CLASS-LEVEL. Every rookie in a
#    (position, prediction-tercile) bucket carries a byte-identical interval, so on the 2026 board 81
#    rookies shared **12** distinct bands (3 per position) against 647 distinct bands for 703
#    veterans. Every top-bucket rookie QB carried 26.5–277.0 while their point projections spanned
#    25.1→268.3 — a 268-point projection sat in the top 3% of "its own" interval and a 25-point rookie
#    at the bottom of the SAME one. The band carried ~zero per-player information.
#
# ⚠️ AND WHY IT HAPPENED — the §0.5 selection-metric landmine in the wild. NF1.4 tuned this band on
#    COVERAGE (0.678 → 0.834) and a POSITION-CONSTANT band can hit nominal coverage while carrying NO
#    information at all: coverage is a property of the population, not of the player. So NF1.7 selects
#    on a PROPER interval score (the Winkler/pinball interval score — sharpness penalised for
#    miscoverage) with coverage kept strictly as a FLOOR, exactly the E2.1-r rule ("a coverage figure
#    is a FLOOR, never a target to minimise distance to") applied to intervals.
#
# ⭐ AND THE HONEST DIRECTION IS *WIDER*, NOT MERELY DIFFERENTIATED. A rookie has no NFL sample, so
#    his honest band is generally wider than a comparable veteran's. Sharpness must therefore never be
#    bought by under-covering — which is precisely what the coverage FLOOR and the bake-off's
#    ZERO-WIDTH degenerate anchor (a band of width 0 is maximally "sharp" and must LOSE) exist to
#    prevent. The point projection is UNCHANGED: NF1.4 proved the rookie point is ~unbiased.
_ROOKIE_BAND_FORMS = ("ratio_q", "ratio_q_floor", "knn_pos", "knn_norm", "qreg", "qreg_sqrt")
_ROOKIE_BAND_MIN_TRAIN = 40      # below this a position/pool fit is refused → tercile fallback

# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF1.8 — the PER-POSITION coverage floor (bake-off: run_rookie_perposition_ablation.py)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ WHAT NF1.7 LEFT ON THE TABLE. Its coverage floor was pre-registered POOLED, and pooled coverage
#    duly rose 0.791 → 0.808 — but it REDISTRIBUTED rather than improved uniformly: QB 0.739 (below
#    nominal in BOTH arms), RB 0.836 → 0.777, TE 0.878, WR 0.822. Pooled coverage is a population
#    property one position can pay for on another's behalf, which is the same class of blind spot as
#    NF1.4's "coverage cannot select an interval" — one level up. So NF1.8 re-selects under a
#    PER-POSITION floor, still SELECTING on the interval score (coverage stays a FLOOR, never a target).
#
# ⭐ TWO MECHANISMS ARE ADDED TO THE BALLOT, because re-filtering NF1.7's leaderboard under a new
#    constraint would make the QB fix INCIDENTAL rather than designed:
#      • `qreg_per_pos` — fit the quantile regression SEPARATELY per position. NF1.7's position dummy
#        shifts only the INTERCEPT, so every position was forced to share one slope on log(point) and
#        one on the P1A sd. QB is precisely the position whose slope should differ (~35% of drafted
#        rookie QBs never take a snap).
#      • `cqr_mode` — CONFORMALIZED quantile regression (Romano/Patterson/Candès 2019) with a
#        MONDRIAN (group-conditional) calibration per position. This is the textbook instrument for a
#        per-GROUP coverage floor: the fitted band is inflated by the (1−α) empirical quantile of the
#        calibration conformity scores WITHIN the position, which is what carries the finite-sample
#        group-conditional guarantee. `cqr_mode="pool"` is its pre-registered FOIL — the identical
#        machinery calibrated POOLED — so the report can separate "conformal helped" from
#        "per-position conditioning helped".
_ROOKIE_BAND_CQR_MODES = ("", "pos", "pool")
_ROOKIE_BAND_CQR_SCALES = ("add", "width")
_ROOKIE_BAND_CQR_K = 4           # cross-conformal folds (uses every training row for both jobs)
# Below this many calibration rows a GROUP cannot carry its own conformal quantile and falls back to
# the pooled one — recorded in `RookieBandModel.cqr_pooled_groups`, never silent. At α=0.20 the
# finite-sample guarantee needs only n ≥ 4, but a 4-row quantile is noise; 20 is the honest floor.
_ROOKIE_BAND_CQR_MIN_CALIB = 20
_CQR_POOL_KEY = "__POOL__"       # the pooled conformal quantile, and every thin group's fallback
_CQR_MIN_WIDTH = 1.0             # floor on the width a `"width"`-scaled inflation multiplies
# ⬇ THE SHIPPED SELECTION (44 configs, held-out draft classes 2019–2025, PBO 0.029 / spread 27% =
#    LOW-PBO + WIDE-spread ⇒ a genuinely separated winner). See
#    `ablation_results/nf1_7_rookie_intervals.md`. Held-out interval score 181.16 vs the class-level
#    incumbent's 202.14 (−10.4%) at coverage 0.808 (floor 0.80); distinct-band fraction 0.184 → 0.989
#    and the point projections in the extreme 5% tail of their own band 30/553 → **0**.
#    ⭐ THE WINNING BAND IS *WIDER* THAN THE ONE IT REPLACES (127.7 vs 124.4 PPR mean, ≈2× a veteran's)
#    — the win came from putting the width where it belongs per player, not from shrinking it. Which is
#    the point: sharpness was the SELECTION metric, honesty the CONSTRAINT.
#    ⚠️ SUPERSEDED BY NF1.8 (2026-07-29) — the constants below are NF1.8's, not NF1.7's. NF1.7's
#    `qreg` won under a POOLED floor but covers QB at only 0.741 and RB at 0.777, so it is INELIGIBLE
#    under NF1.8's per-position floor. See `ablation_results/nf1_8_rookie_perposition_floor.md`.
_ROOKIE_BAND_FORM = "qreg_sqrt"      # NF1.8: `qreg` on √y — the heavy-right-tailed target's linear scale
_ROOKIE_BAND_K = 80                  # neighbourhood arms only; unused by the shipped parametric arm
_ROOKIE_BAND_QREG_ALPHA = 0.01       # a whisper of L1 — it beat the unregularised fit on every metric
# The P1A parameter-uncertainty WIDENER is left OFF — and this is the shipped value of a genuine TIE,
# not a clear win. `sdgain` 0.1/0.2 land within 0.2% of the winner on the primary metric while covering
# 0.841/0.850 against its 0.808, so there is a real temptation to re-pick on that headroom. We do not:
# coverage was pre-registered as an eligibility FLOOR, and "prefer more headroom" is monotone in
# WIDENING — the `max_width` degenerate wins it outright — so re-picking a tie on it is the E2.1-r
# inversion facing the other way. `projected_nfl_z_sd` still enters the shipped band as a REGRESSION
# FEATURE; what is switched off is only the extra multiplicative widening on top. See §4b of the report.
_ROOKIE_BAND_RESID_SD_GAIN = 0.0
# ⬇ NF1.8 — THE PER-POSITION-FLOOR RE-SELECTION. Shipped: `qreg_sqrt+cqr[pos,add] · sdgain 0` (80
#    configs × 7 held-out draft classes, 553 rookie-seasons). See
#    `ablation_results/nf1_8_rookie_perposition_floor.md`.
#      · every position clears the NOMINAL 0.80 floor (Tier 1; the documented Tier-2 QB relaxation was
#        NOT needed): QB 0.741 → 0.815, RB 0.777 → 0.804, TE 0.870 → 0.900, WR 0.826 → 0.835;
#      · the floor costs +1.3% of interval score (180.99 → 183.41) and is still 9.1% better than the
#        NF1.4 class-level incumbent (201.76) at a distinct-band fraction of 0.89 vs 0.18;
#      · the rookie POINT projection is byte-identical (asserted in the harness, max drift 0.0).
#    ⭐ THE MONDRIAN (PER-POSITION) CALIBRATION IS WHAT EARNS IT, and the pre-registered POOLED foil is
#    the proof: pooled calibration is a numerical NO-OP on this base (183.451 → 183.451, QB 0.778 →
#    0.778) because the base band's aggregate out-of-fold coverage is already ≈ nominal. Only reading
#    the conformity scores WITHIN a position makes the QB shortfall visible.
#    ⚠️ `qreg_per_pos` (a separate quantile REGRESSION per position) was the other pre-registered
#    per-position mechanism and it LOST — it made QB worse (0.716), because separate slopes overfit at
#    QB's in-fold n. Per-position CALIBRATION works where per-position FITTING does not.
_ROOKIE_BAND_QREG_PER_POS = False
_ROOKIE_BAND_CQR_MODE = "pos"
_ROOKIE_BAND_CQR_SCALE = "add"


def p1a_residual_nudge(position_group, overall, z, residual_lambda: float = 0.12) -> np.ndarray:
    """The NCAAF-P1A residual nudge — a mild multiplicative production tilt from the talent the draft
    board did not price. WITHIN (position, class): regress `projected_nfl_z` on log(draft slot); the
    residual (standardised by its own spread) becomes `exp(λ·resid/sd)`, clipped to [0.75, 1.35].

    Factored out of `project_rookies` (NF1.7) so the BAND fit can condition on the very same served
    point projection the board displays — a band conditioned on a *different* point than the one it is
    pasted onto is the class-level defect in another guise. A within-class quantity, so it is identical
    whether the class is train or test and cannot leak across a walk-forward fold.

    Returns all-ones for a group too thin (<6 usable rows) to estimate a slot slope."""
    pos = np.asarray(position_group, dtype=object)
    overall = pd.to_numeric(pd.Series(overall), errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(pd.Series(z), errors="coerce").to_numpy(dtype=float) if z is not None \
        else np.full(len(pos), np.nan)
    nudge = np.ones(len(pos))
    logo = np.log(np.clip(overall, 1, None))
    for p in pd.unique(pos):
        idx = np.where(pos == p)[0]
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
            resid = zi - (intercept + slope * li)
        rs = np.nanstd(resid[np.isfinite(resid)])
        if rs and np.isfinite(rs):
            nudge[idx] = np.clip(np.exp(residual_lambda * np.nan_to_num(resid / rs)), 0.75, 1.35)
    return nudge


def _knn_interval(train_x: np.ndarray, train_y: np.ndarray, q: np.ndarray, k: int,
                  lo_q: float, hi_q: float) -> tuple[np.ndarray, np.ndarray]:
    """The q`lo_q`/q`hi_q` of the realized outcomes of the `k` training rookies NEAREST `q` in
    PREDICTION space — a local (per-player) reading of the incumbent's tercile bucket. `k` is the
    resolution knob: k = n/3 reproduces the incumbent, small k is a per-player band with a noisy
    quantile. It is selected in the bake-off, not chosen."""
    kk = int(np.clip(k, 5, len(train_x)))
    lo = np.empty(len(q), dtype=float)
    hi = np.empty(len(q), dtype=float)
    for i, x in enumerate(q):
        idx = np.argpartition(np.abs(train_x - x), kk - 1)[:kk]
        yy = train_y[idx]
        lo[i] = float(np.quantile(yy, lo_q))
        hi[i] = float(np.quantile(yy, hi_q))
    return lo, hi


@dataclass
class RookieBandModel:
    """NF1.7 — the fitted PER-PLAYER rookie 80% band. One of the pre-registered forms below, all fit
    IN-FOLD on prior draft classes' REALIZED rookie seasons (the FULL drafted population, zero-game
    rookies carried as a real 0 — NF1.4's population fix, which this inherits).

    `form` — the candidate class (`run_rookie_interval_ablation.py` is the §0.5 gate):
      • `ratio_q`       — per-position empirical quantiles of the RATIO realized/predicted, applied
                          multiplicatively to the player's own point. Per-player and continuous, but
                          its width COLLAPSES to zero as the point approaches zero — the exact flaw
                          NF1.4 documented in the pre-NF1.4 `fp × cv` band.
      • `ratio_q_floor` — `ratio_q` plus an ADDITIVE upside floor (the q90 of realized outcomes in the
                          position's bottom prediction decile), so a near-zero projection still
                          carries the honest "a late pick sometimes hits" upside.
      • `knn_pos`       — the q10/q90 of the realized outcomes of the `k` nearest training rookies in
                          the POSITION's own prediction space. Non-parametric; k is the resolution.
      • `knn_norm`      — the same, but in POSITION-NORMALISED prediction space POOLED across
                          positions, then rescaled by the position level. The resolution fix: a single
                          position carries only ~40–90 training rookies, so a per-position k-NN is
                          barely finer than terciles; pooling buys ~4× the neighbours at the cost of
                          assuming the SHAPE of the conditional distribution is position-invariant
                          once scaled (which is why `knn_pos` is pre-registered beside it).
      • `qreg`          — THE DIRECT-LEARNED FOIL: linear quantile regression (pinball loss, τ =
                          0.10/0.90) of the realized rookie season on the story's named uncertainty
                          drivers — log point projection, log draft slot, the P1A residual sd, and
                          position. Learns the conditional quantiles directly instead of reading them
                          off a neighbourhood.
      • `qreg_sqrt`     — `qreg` on √y, inverted. Quantiles are invariant under a monotone transform,
                          so this is still a valid quantile estimate; it changes only WHERE linearity
                          in the features is assumed to hold (the rookie outcome is heavy-right-tailed,
                          so the √ scale is the more plausible linear scale).
    `resid_sd_gain` optionally widens any form by the player's OWN P1A parameter uncertainty
    (`projected_nfl_z_sd`, z-scored in-fold) — the per-player uncertainty driver that no
    outcome-neighbourhood can see. 0 = off.

    NF1.8 adds two knobs on the parametric arms, both aimed at a PER-POSITION coverage floor:
      • `qreg_per_pos` — fit the quantile pair SEPARATELY per position (a position dummy shifts only
                         the intercept, so NF1.7 forced every position to share one slope).
      • `cqr_mode`     — conformalize the fitted band. `"pos"` = MONDRIAN / group-conditional (the
                         conformity quantile is taken WITHIN the position — the instrument that
                         actually carries a per-group coverage guarantee); `"pool"` = the pooled foil.
                         `cqr_scale` is `"add"` (a points-scale inflation) or `"width"` (an inflation
                         PROPORTIONAL to the band's own width — the scale-aware variant, appropriate
                         for a heavy-right-tailed target whose spread grows with the level).
      ⚠️ The conformal adjustment is a per-GROUP SCALAR by construction, so it cannot buy sharpness by
        narrowing selected players; it may be NEGATIVE when the base band over-covers on calibration
        (that is CQR working as designed, not a back door — it moves every member of the group
        together), which is why the `resid_sd_gain` widen-only clamp is a SEPARATE guard.
    """

    form: str = _ROOKIE_BAND_FORM
    k: int = _ROOKIE_BAND_K
    resid_sd_gain: float = _ROOKIE_BAND_RESID_SD_GAIN
    qreg_alpha: float = _ROOKIE_BAND_QREG_ALPHA
    qreg_per_pos: bool = False
    cqr_mode: str = ""
    cqr_scale: str = "add"
    cqr_k: int = _ROOKIE_BAND_CQR_K
    # NF-D14 — the AVAILABILITY driver (`avail_risk_z`, a per-player availability-risk z from
    # `rookie_availability.AvailabilityPrior`). BOTH default OFF, so a model constructed without them
    # is byte-identical to the NF1.8 band that ships today (`test_the_availability_channel_is_inert_by_default`).
    avail_feature: bool = False      # enter the driver as a QUANTILE-REGRESSION feature
    avail_gain: float = 0.0          # ...and/or as a strictly WIDEN-ONLY multiplicative widener
    avail_ref: tuple = (0.0, 1.0)    # in-fold (mean, sd) of the driver
    n_fit: int = 0
    lo_q: float = 0.10
    hi_q: float = 0.90
    scale: dict = field(default_factory=dict)        # position -> normalising prediction level
    pos_pred: dict = field(default_factory=dict)     # position -> training predictions
    pos_real: dict = field(default_factory=dict)     # position -> realized rookie fp (aligned)
    pool_pred: np.ndarray | None = None              # pooled, position-normalised predictions
    pool_real: np.ndarray | None = None              # pooled, position-normalised realized
    ratio_lo: dict = field(default_factory=dict)     # position -> q10 of realized/predicted
    ratio_hi: dict = field(default_factory=dict)     # position -> q90 of realized/predicted
    floor_hi: dict = field(default_factory=dict)     # position -> additive upside floor
    qreg_lo: dict = field(default_factory=dict)      # feature -> coef (+ 'intercept')
    qreg_hi: dict = field(default_factory=dict)
    qreg_positions: tuple = ()
    resid_sd_ref: tuple = (0.0, 1.0)                 # in-fold (mean, sd) of projected_nfl_z_sd
    # NF1.8 — the per-position quantile pair and the (group-conditional) conformal adjustment
    qreg_lo_pos: dict = field(default_factory=dict)   # position -> {feature: coef}
    qreg_hi_pos: dict = field(default_factory=dict)
    conformal: dict = field(default_factory=dict)     # position -> adjustment (+ _CQR_POOL_KEY)
    cqr_pooled_groups: tuple = ()                     # groups too thin for their OWN quantile
    cqr_n_calib: dict = field(default_factory=dict)   # position -> calibration rows behind it

    # ── prediction ──────────────────────────────────────────────────────────────────────────
    def band_many(self, position, pred, overall=None, resid_sd=None, avail=None
                  ) -> tuple[np.ndarray, np.ndarray]:
        """Per-player (lo, hi) arrays. NaN for a row the fit cannot speak to (an unseen position, or
        a form whose required parameters were never fitted) — the caller then falls back to the
        class-level tercile band, so a thin fit degrades rather than emitting a fabricated interval.

        Two invariants enforced on every form: the band is NON-NEGATIVE (a fantasy season cannot be
        negative) and it BRACKETS the point projection (a displayed interval that excludes its own
        point estimate is incoherent — the very symptom NF3 surfaced)."""
        pos = np.array([str(p or "").upper() for p in np.asarray(position, dtype=object)],
                       dtype=object)
        pred = np.asarray(pd.to_numeric(pd.Series(pred), errors="coerce").to_numpy(), dtype=float)
        n = len(pred)
        lo = np.full(n, np.nan)
        hi = np.full(n, np.nan)
        ov = (pd.to_numeric(pd.Series(overall), errors="coerce").to_numpy(dtype=float)
              if overall is not None else np.full(n, np.nan))
        rsd = (pd.to_numeric(pd.Series(resid_sd), errors="coerce").to_numpy(dtype=float)
               if resid_sd is not None else np.full(n, np.nan))
        av = (pd.to_numeric(pd.Series(avail), errors="coerce").to_numpy(dtype=float)
              if avail is not None else np.full(n, np.nan))

        if self.form in ("ratio_q", "ratio_q_floor"):
            for p in np.unique(pos):
                if p not in self.ratio_lo:
                    continue
                idx = np.where(pos == p)[0]
                lo[idx] = self.ratio_lo[p] * pred[idx]
                hi[idx] = self.ratio_hi[p] * pred[idx]
                if self.form == "ratio_q_floor":
                    hi[idx] = hi[idx] + float(self.floor_hi.get(p, 0.0))
        elif self.form == "knn_pos":
            for p in np.unique(pos):
                tx, ty = self.pos_pred.get(p), self.pos_real.get(p)
                if tx is None or len(tx) < _ROOKIE_BAND_MIN_TRAIN:
                    continue
                idx = np.where(pos == p)[0]
                lo[idx], hi[idx] = _knn_interval(tx, ty, pred[idx], self.k, self.lo_q, self.hi_q)
        elif self.form == "knn_norm":
            if self.pool_pred is not None and len(self.pool_pred) >= _ROOKIE_BAND_MIN_TRAIN:
                for p in np.unique(pos):
                    s = float(self.scale.get(p, 0.0))
                    if s <= 0:
                        continue
                    idx = np.where(pos == p)[0]
                    l, h = _knn_interval(self.pool_pred, self.pool_real, pred[idx] / s,
                                         self.k, self.lo_q, self.hi_q)
                    lo[idx], hi[idx] = l * s, h * s
        elif self.form in ("qreg", "qreg_sqrt"):
            if self.qreg_per_pos:
                # NF1.8 — a SEPARATE quantile pair per position (no dummies in the design). A position
                # with no fit stays NaN and falls back, exactly as a thin pooled fit does.
                for p in np.unique(pos):
                    clo, chi = self.qreg_lo_pos.get(p), self.qreg_hi_pos.get(p)
                    if not clo or not chi:
                        continue
                    idx = np.where(pos == p)[0]
                    x = self._design(pos[idx], pred[idx], ov[idx], rsd[idx], av[idx],
                                     with_positions=False)
                    lo[idx] = self._apply_qreg(clo, x)
                    hi[idx] = self._apply_qreg(chi, x)
            elif self.qreg_lo and self.qreg_hi:
                x = self._design(pos, pred, ov, rsd, av)
                lo = self._apply_qreg(self.qreg_lo, x)
                hi = self._apply_qreg(self.qreg_hi, x)
            if self.form == "qreg_sqrt":
                lo = np.clip(lo, 0.0, None) ** 2
                hi = np.clip(hi, 0.0, None) ** 2

        # ⭐ NF1.8 — the CONFORMAL adjustment, BEFORE the P1A widener so the conformity scores the
        #    calibration folds measured describe the same band shape this inflates. A per-GROUP scalar
        #    (`cqr_mode="pos"` reads the position's own quantile, `"pool"` one shared quantile), so it
        #    moves every member of a group together and cannot narrow a chosen player. `"width"` makes
        #    the inflation proportional to the band's own width, i.e. a per-group MULTIPLIER on the
        #    width rather than a points-scale constant.
        if self.cqr_mode and self.conformal:
            qp = float(self.conformal.get(_CQR_POOL_KEY, 0.0))
            adj = (np.array([float(self.conformal.get(p, qp)) for p in pos], dtype=float)
                   if self.cqr_mode == "pos" else np.full(n, qp))
            if self.cqr_scale == "width":
                w = np.maximum(hi - lo, _CQR_MIN_WIDTH)
                lo, hi = lo - adj * w, hi + adj * w
            else:
                lo, hi = lo - adj, hi + adj

        # ⭐ the per-player uncertainty driver an outcome-neighbourhood cannot see: widen by the
        #    player's OWN P1A parameter uncertainty.
        #    STRICTLY WIDEN-ONLY (`max(z, 0)`), by design: a player whose translation is unusually
        #    UNCERTAIN gets a wider band, but an unusually CONFIDENT translation buys NOTHING. A
        #    two-sided tilt would let this knob SHARPEN half the field off a parameter-uncertainty z,
        #    i.e. buy sharpness on the selection metric by narrowing bands — the exact trade the
        #    coverage floor exists to forbid. (Measured: the two-sided version cost coverage
        #    0.808 → 0.773.) Guard: `test_the_widener_is_widen_only`.
        if self.resid_sd_gain > 0:
            m0, s0 = self.resid_sd_ref
            zsd = np.where(np.isfinite(rsd), (rsd - m0) / (s0 or 1.0), 0.0)
            grow = np.exp(self.resid_sd_gain * np.clip(zsd, 0.0, 2.0))
            mid = 0.5 * (lo + hi)
            half = 0.5 * (hi - lo) * grow
            lo, hi = mid - half, mid + half

        # ⭐ NF-D14 — the AVAILABILITY widener. Same widen-only contract as the P1A one above, and for
        #    the same reason (NF1.7 lesson (d)): a two-sided `exp(gain·z)` would SHARPEN the half of the
        #    field whose availability is unusually certain, i.e. buy the selection metric by narrowing
        #    bands, which is precisely the trade a coverage floor exists to forbid. `clip(z, 0, 2)` makes
        #    it monotone by construction — a rookie whose PLAYING TIME is unusually uncertain gets a
        #    wider band; an unusually certain one buys NOTHING.
        if self.avail_gain > 0:
            a0, as0 = self.avail_ref
            za = np.where(np.isfinite(av), (av - a0) / (as0 or 1.0), 0.0)
            grow = np.exp(self.avail_gain * np.clip(za, 0.0, 2.0))
            mid = 0.5 * (lo + hi)
            half = 0.5 * (hi - lo) * grow
            lo, hi = mid - half, mid + half

        lo = np.clip(np.minimum(lo, pred), 0.0, None)
        hi = np.maximum(hi, pred)
        return lo, hi

    # ── the quantile-regression design (shared by fit + predict, so they cannot drift) ──────
    def _design(self, pos: np.ndarray, pred: np.ndarray, overall: np.ndarray,
                resid_sd: np.ndarray, avail: np.ndarray | None = None,
                with_positions: bool = True) -> pd.DataFrame:
        """`with_positions=False` drops the position dummies — the NF1.8 per-position fit, where the
        position is the GROUPING rather than a feature (a dummy shifts only the intercept).

        NF-D14's `avail_z` column is added ONLY when `avail_feature` is set, so the default design is
        byte-identical to NF1.8's and the shipped band cannot move by accident."""
        m0, s0 = self.resid_sd_ref
        x = pd.DataFrame({
            "log_pred": np.log1p(np.clip(pred, 0.0, None)),
            "log_overall": np.log(np.clip(np.nan_to_num(overall, nan=200.0), 1.0, None)),
            "z_sd": np.where(np.isfinite(resid_sd), (resid_sd - m0) / (s0 or 1.0), 0.0),
        })
        if self.avail_feature:
            a0, as0 = self.avail_ref
            a = (np.full(len(x), np.nan) if avail is None
                 else np.asarray(avail, dtype=float))
            x["avail_z"] = np.where(np.isfinite(a), (a - a0) / (as0 or 1.0), 0.0)
        if with_positions:
            for p in self.qreg_positions[1:]:      # first position is the reference level
                x[f"pos_{p}"] = (pos == p).astype(float)
        return x

    @staticmethod
    def _apply_qreg(coefs: dict, x: pd.DataFrame) -> np.ndarray:
        beta = np.array([float(coefs.get(c, 0.0)) for c in x.columns], dtype=float)
        return x.to_numpy(dtype=float) @ beta + float(coefs.get("intercept", 0.0))


def rookie_point_projection(hist: pd.DataFrame, curve: RookieSlotCurve,
                            residual_lambda: float = 0.12,
                            class_col: str = "draft_year") -> np.ndarray:
    """The SERVED rookie point projection for an arbitrary frame of drafted rookies, by RUNNING THE
    SERVED PATH — `project_rookies` itself, one draft class at a time — and reading `proj_fp_ppr` back.

    NF1.7 needs this so the BAND is fitted on the SAME conditioning variable it is later pasted onto.
    A band conditioned on a different point than the board displays is the class-level defect wearing
    a new hat: it would be centred on a quantity nobody sees.

    ⚠️ IT DELEGATES RATHER THAN RE-DERIVING, and that is not fastidiousness — the first cut recomputed
    `slot curve × nudge, clipped to the ceiling` and was WRONG BY UP TO 3.3 PPR, because the served
    point is that target MINUS the fumbles-lost term (`project_rookies` rescales the stat line to hit
    the target, then recomputes fumbles from the rescaled touches and re-scores). The harness's
    point-invariance assertion caught it. Any future change to the rookie line therefore flows here
    for free. Per class, because the P1A residual nudge is a WITHIN-class quantity — grouping by
    `class_col` is what keeps it from leaking across a walk-forward fold.

    Rows `project_rookies` declines to project (a non-skill position, a missing draft slot) come back
    as NaN, and `fit_rookie_band_model` drops them."""
    pos = hist["position_group"].astype(str).str.upper()
    frame = hist.copy()
    frame["position_group"] = pos.to_numpy()
    if "nfl_position" not in frame.columns:
        frame["nfl_position"] = pos.to_numpy()
    if "player_name" not in frame.columns:
        frame["player_name"] = ""
    if "projected_nfl_z" not in frame.columns:
        frame["projected_nfl_z"] = np.nan
    # A SYNTHETIC row key, always — `project_rookies` drops and re-indexes rows, so the results have to
    # be mapped back by id, and neither a caller's real `gsis_id` (which a unit-test fixture may not
    # carry at all) nor its uniqueness can be assumed. We only need to re-join our own rows.
    ids = np.arange(len(frame)).astype(str)
    frame["gsis_id"] = ids
    cls = (frame[class_col].to_numpy() if class_col in frame.columns
           else np.zeros(len(frame), dtype=int))
    out = np.full(len(frame), np.nan)
    for c in pd.unique(cls):
        idx = np.where(cls == c)[0]
        got = project_rookies(frame.iloc[idx], curve, int(c) if pd.notna(c) else 0,
                              residual_lambda=residual_lambda)
        if got.empty:
            continue
        m = dict(zip(got["player_id"].astype(str),
                     pd.to_numeric(got["proj_fp_ppr"], errors="coerce")))
        out[idx] = [m.get(i, np.nan) for i in ids[idx]]
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Shared band kernels — used by BOTH the rookie (NF1.7/1.8) and veteran (NF1.9) band models
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Factored out (NF1.9) rather than copied, because these two are where a re-implementation would go
# wrong SILENTLY: a pinball fit with the wrong regularisation convention, or a conformal quantile at
# the ASYMPTOTIC level instead of the finite-sample one, both produce a plausible band that quietly
# fails to carry the guarantee it claims. One definition, two consumers, one test.
def _pinball_fit(x: pd.DataFrame, target: np.ndarray, q: float, alpha: float) -> dict:
    """Linear quantile regression at τ=`q` (pinball loss, L1 penalty `alpha`) → {feature: coef} +
    'intercept'. Raises ImportError when sklearn is absent; every caller degrades from that."""
    from sklearn.linear_model import QuantileRegressor
    r = QuantileRegressor(quantile=float(q), alpha=float(alpha), solver="highs")
    r.fit(x.to_numpy(dtype=float), target)
    return {**dict(zip(x.columns, r.coef_.tolist())), "intercept": float(r.intercept_)}


def _conformity_quantile(vals, alpha: float) -> float:
    """The ⌈(1−α)(n+1)⌉/n empirical quantile of a set of conformity scores — the FINITE-SAMPLE
    split-conformal level. ⚠️ Not `np.quantile(v, 1−α)`: the (n+1)/n inflation is exactly what turns
    the coverage statement into a guarantee at the group's own sample size rather than an asymptotic
    hope, and at the group sizes a per-position floor lives at, the difference is material."""
    v = np.asarray(vals, dtype=float)
    nn = len(v)
    if nn == 0:
        return 0.0
    lvl = min(1.0, float(np.ceil((1.0 - alpha) * (nn + 1.0)) / nn))
    return float(np.quantile(v, lvl))


def _interval_score(lo, hi, y, alpha: float = 0.20) -> np.ndarray:
    """The Winkler / Gneiting-Raftery interval score for a central (1−α) interval (LOWER is better).

    The SERVED-side copy of the bake-off's primary metric, needed because one veteran arm
    (`normal_scaled`) fits its own dispersion multiplier by minimising it in-fold. Pinned to the
    harness definition by `test_interval_score_definitions_agree`."""
    lo, hi, y = (np.asarray(a, dtype=float) for a in (lo, hi, y))
    return (hi - lo) + (2.0 / alpha) * (np.clip(lo - y, 0, None) + np.clip(y - hi, 0, None))


def _fit_qreg_into(m: RookieBandModel, pos: np.ndarray, y: np.ndarray, pred: np.ndarray,
                   ov: np.ndarray, rsd: np.ndarray, av: np.ndarray | None = None) -> None:
    """Fit `m`'s quantile pair in place — POOLED with position dummies, or (NF1.8) a SEPARATE pair per
    position when `m.qreg_per_pos`. Factored out of `fit_rookie_band_model` because the NF1.8
    cross-conformal calibration has to re-fit the very same arm on each fold's complement, and a
    re-implementation there could silently calibrate a band shape that is not the one served."""
    try:
        import sklearn.linear_model  # noqa: F401  (the kernel imports it; fail soft here)
    except ImportError:                                    # pragma: no cover - sklearn is a dep
        return
    target = np.sqrt(np.clip(y, 0.0, None)) if m.form == "qreg_sqrt" else y

    def _fit(x: pd.DataFrame, t: np.ndarray, q: float) -> dict:
        return _pinball_fit(x, t, q, m.qreg_alpha)

    avv = np.full(len(pos), np.nan) if av is None else np.asarray(av, dtype=float)
    if m.qreg_per_pos:
        for p in np.unique(pos):
            sel = pos == p
            if sel.sum() < _ROOKIE_BAND_MIN_TRAIN:
                continue                                   # → NaN → the class-level fallback
            x = m._design(pos[sel], pred[sel], ov[sel], rsd[sel], avv[sel], with_positions=False)
            m.qreg_lo_pos[p] = _fit(x, target[sel], m.lo_q)
            m.qreg_hi_pos[p] = _fit(x, target[sel], m.hi_q)
        return
    x = m._design(pos, pred, ov, rsd, avv)
    m.qreg_lo.update(_fit(x, target, m.lo_q))
    m.qreg_hi.update(_fit(x, target, m.hi_q))


def _fit_conformal_into(m: RookieBandModel, pos: np.ndarray, y: np.ndarray, pred: np.ndarray,
                        ov: np.ndarray, rsd: np.ndarray, av: np.ndarray | None = None) -> None:
    """NF1.8 — CROSS-CONFORMAL calibration of `m`'s fitted band (Vovk cross-conformal / CQR).

    THE POINT: a per-POSITION coverage floor needs an instrument that delivers coverage PER GROUP, and
    conformalized quantile regression with a MONDRIAN (per-group) calibration is that instrument. For
    each of `cqr_k` deterministic folds the arm is re-fit on the complement and scored on the held
    fold, giving every training row an out-of-fold conformity score

        E_i = max(lo(x_i) − y_i,  y_i − hi(x_i))        ('add')
        E_i = that, divided by the row's own band width  ('width')

    The adjustment for a group is the ⌈(1−α)(n+1)⌉/n empirical quantile of that group's E — the finite-
    sample split-conformal level, which is what makes the coverage claim a guarantee at the group's own
    sample size rather than an asymptotic hope.

    ⚠️ CROSS-conformal, not a single split, and that is not a refinement: a per-position calibration
    split of ~80 QB training rows would leave ~30 rows to fit on and ~20 to calibrate with, so BOTH
    halves would be too thin. Cross-conformal spends every row on both jobs.

    ⚠️ A GROUP TOO THIN FOR ITS OWN QUANTILE FALLS BACK TO THE POOLED ONE AND IS RECORDED
    (`cqr_pooled_groups`) — a silently-pooled group would be a per-position claim the fit never made.
    That is the NF1.7 lesson-(1) shape: an anchor/estimate that quietly fails to fit makes its own
    check vacuous."""
    if m.form not in ("qreg", "qreg_sqrt"):
        return
    n = len(y)
    avv = np.full(n, np.nan) if av is None else np.asarray(av, dtype=float)
    alpha = 1.0 - (m.hi_q - m.lo_q)
    # a DETERMINISTIC fold assignment (no RNG — a seeded split would make the fitted band depend on the
    # draw): order within position by the conditioning variable, then deal the rows round-robin, so
    # every fold gets a balanced spread of every position and prediction level.
    order = np.lexsort((pred, pos))
    fold = np.empty(n, dtype=int)
    fold[order] = np.arange(n) % max(2, int(m.cqr_k))
    scores: list[tuple[str, float]] = []
    for f in range(max(2, int(m.cqr_k))):
        trn, cal = fold != f, fold == f
        if trn.sum() < _ROOKIE_BAND_MIN_TRAIN or cal.sum() < 3:
            continue
        # ⚠️ the sub-model must carry the availability settings too — a calibration fitted on a
        # DIFFERENT band shape than the one it inflates would silently calibrate the wrong object.
        sub = RookieBandModel(form=m.form, qreg_alpha=m.qreg_alpha, qreg_per_pos=m.qreg_per_pos,
                              lo_q=m.lo_q, hi_q=m.hi_q, resid_sd_ref=m.resid_sd_ref,
                              qreg_positions=m.qreg_positions, n_fit=int(trn.sum()),
                              avail_feature=m.avail_feature, avail_ref=m.avail_ref)
        _fit_qreg_into(sub, pos[trn], y[trn], pred[trn], ov[trn], rsd[trn], avv[trn])
        lo, hi = sub.band_many(pos[cal], pred[cal], overall=ov[cal], resid_sd=rsd[cal],
                               avail=avv[cal])
        good = np.isfinite(lo) & np.isfinite(hi)
        if not good.any():
            continue
        e = np.maximum(lo[good] - y[cal][good], y[cal][good] - hi[good])
        if m.cqr_scale == "width":
            e = e / np.maximum(hi[good] - lo[good], _CQR_MIN_WIDTH)
        scores.extend(zip(pos[cal][good].tolist(), e.tolist()))
    if not scores:
        return

    def _q(vals: list[float]) -> float:
        return _conformity_quantile(vals, alpha)

    by_group: dict[str, list[float]] = {}
    for p, e in scores:
        by_group.setdefault(p, []).append(e)
    m.conformal[_CQR_POOL_KEY] = _q([e for _, e in scores])
    thin: list[str] = []
    for p, vals in by_group.items():
        m.cqr_n_calib[p] = len(vals)
        if len(vals) >= _ROOKIE_BAND_CQR_MIN_CALIB:
            m.conformal[p] = _q(vals)
        else:
            thin.append(p)
    m.cqr_pooled_groups = tuple(sorted(thin))


def fit_rookie_band_model(
    band_hist: pd.DataFrame,
    preds,
    *,
    form: str = _ROOKIE_BAND_FORM,
    k: int = _ROOKIE_BAND_K,
    resid_sd_gain: float = _ROOKIE_BAND_RESID_SD_GAIN,
    qreg_alpha: float = _ROOKIE_BAND_QREG_ALPHA,
    qreg_per_pos: bool = False,
    cqr_mode: str = "",
    cqr_scale: str = "add",
    cqr_k: int = _ROOKIE_BAND_CQR_K,
    band_q: tuple[float, float] = _ROOKIE_BAND_Q,
    avail_feature: bool = False,
    avail_gain: float = 0.0,
) -> RookieBandModel | None:
    """NF1.7 §0.5 — fit ONE pre-registered per-player band form on the historical drafted population.

    `band_hist` is the FULL drafted rookie population (one row per historical drafted skill rookie,
    zero-game rookies carried as a real `rookie_fp_ppr = 0`) and `preds` is the SERVED point
    projection for each of those rows — i.e. the band is conditioned on exactly the quantity it will
    be pasted onto. Optional columns `draft_overall` and `projected_nfl_z_sd` feed the parametric arm
    and the P1A-uncertainty widening.

    Pure. Returns None when the history is too thin to fit anything (the caller then keeps the
    class-level tercile band) — a thin fit must degrade to the incumbent, never to a fabricated
    per-player interval."""
    if band_hist is None or band_hist.empty or form not in _ROOKIE_BAND_FORMS:
        return None
    if cqr_mode not in _ROOKIE_BAND_CQR_MODES or cqr_scale not in _ROOKIE_BAND_CQR_SCALES:
        raise ValueError(f"unknown conformal setting: cqr_mode={cqr_mode!r} cqr_scale={cqr_scale!r}")
    lo_q, hi_q = band_q
    pos = band_hist["position_group"].astype(str).str.upper().to_numpy()
    y = pd.to_numeric(band_hist.get("rookie_fp_ppr"), errors="coerce").to_numpy(dtype=float)
    pred = pd.to_numeric(pd.Series(preds), errors="coerce").to_numpy(dtype=float)
    if len(pred) != len(y):
        raise ValueError("preds must be aligned to band_hist (one point projection per row)")
    ok = np.isfinite(y) & np.isfinite(pred)
    if ok.sum() < _ROOKIE_BAND_MIN_TRAIN:
        return None
    pos, y, pred = pos[ok], y[ok], pred[ok]
    ov = pd.to_numeric(band_hist.get("draft_overall"), errors="coerce").to_numpy(dtype=float)[ok]
    rsd_col = band_hist.get("projected_nfl_z_sd")
    rsd = (pd.to_numeric(rsd_col, errors="coerce").to_numpy(dtype=float)[ok]
           if rsd_col is not None else np.full(len(y), np.nan))
    # NF-D14 — the availability driver rides on the frame exactly as `projected_nfl_z_sd` does, so
    # production plumbing is "add the column", not "thread another argument through the board build".
    av_col = band_hist.get("avail_risk_z")
    av = (pd.to_numeric(av_col, errors="coerce").to_numpy(dtype=float)[ok]
          if av_col is not None else np.full(len(y), np.nan))

    m = RookieBandModel(form=form, k=int(k), resid_sd_gain=float(resid_sd_gain),
                        qreg_alpha=float(qreg_alpha), qreg_per_pos=bool(qreg_per_pos),
                        cqr_mode=str(cqr_mode), cqr_scale=str(cqr_scale), cqr_k=int(cqr_k),
                        n_fit=int(len(y)), lo_q=lo_q, hi_q=hi_q,
                        avail_feature=bool(avail_feature), avail_gain=float(avail_gain))
    if np.isfinite(rsd).sum() >= _ROOKIE_BAND_MIN_TRAIN:
        m.resid_sd_ref = (float(np.nanmean(rsd)), float(np.nanstd(rsd)) or 1.0)
    if np.isfinite(av).sum() >= _ROOKIE_BAND_MIN_TRAIN:
        m.avail_ref = (float(np.nanmean(av)), float(np.nanstd(av)) or 1.0)

    for p in np.unique(pos):
        sel = pos == p
        if sel.sum() < _ROOKIE_BAND_MIN_TRAIN:
            continue
        m.pos_pred[p] = pred[sel]
        m.pos_real[p] = y[sel]
        # the position's normalising level = the MEAN realized rookie season at the position. The
        # mean (not the max) keeps the normalisation robust to one freak class-best rookie.
        lvl = float(np.mean(y[sel]))
        m.scale[p] = lvl if lvl > 1e-6 else float(np.mean(pred[sel]) or 1.0)
        pr = pred[sel]
        ratio = np.where(pr > 1e-6, y[sel] / np.where(pr > 1e-6, pr, 1.0), np.nan)
        ratio = ratio[np.isfinite(ratio)]
        if len(ratio) >= _ROOKIE_BAND_MIN_TRAIN:
            m.ratio_lo[p] = float(np.quantile(ratio, lo_q))
            m.ratio_hi[p] = float(np.quantile(ratio, hi_q))
            # the additive upside floor: what the BOTTOM prediction decile of this position actually
            # achieves at its q90. A multiplicative band cannot express it (it collapses at pred→0),
            # and it is exactly the late-pick surprise the pre-NF1.4 band priced at ~nothing.
            cut = float(np.quantile(pr, 0.10))
            bottom = y[sel][pr <= cut]
            m.floor_hi[p] = float(np.quantile(bottom, hi_q)) if len(bottom) >= 5 else 0.0

    if m.scale:
        keep = np.array([p in m.scale for p in pos])
        s = np.array([m.scale.get(p, 1.0) for p in pos])[keep]
        m.pool_pred = pred[keep] / s
        m.pool_real = y[keep] / s

    if form in ("qreg", "qreg_sqrt"):
        m.qreg_positions = tuple(sorted(np.unique(pos).tolist()))
        _fit_qreg_into(m, pos, y, pred, ov, rsd, av)
        if not (m.qreg_lo or m.qreg_lo_pos):
            return None                                        # sklearn absent, or every group thin
        if cqr_mode:
            _fit_conformal_into(m, pos, y, pred, ov, rsd, av)
    return m


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF1.9 — the PER-PLAYER VETERAN 80% band (bake-off: run_veteran_interval_ablation.py)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⚠️ THE DEFECT (measured 2026-07-29, held-out target seasons 2013–2025). The whole NF1.4→1.7→1.8 arc
#    validated intervals for the ~81 ROOKIES on the board. The ~700 VETERANS — 90% of it — carried
#    `point ± 1.2816·season_sd`, a NORMAL APPROXIMATION off game-to-game scoring variance plus a
#    games-played term (`uncertainty_type="empirical"`), and NO coverage number for it existed in any
#    ablation report. Measured, its realized coverage of the nominal 80% is **~0.55**, and it misses on
#    BOTH tails at once (~25% of veteran-seasons land BELOW p10, ~19% ABOVE p90). It is not an 80%
#    interval; like the pre-NF1.4 rookie band, it is a decoration.
#
# ⭐ WHY A NORMAL APPROXIMATION HAD TO FAIL HERE, and why the fix is not "widen it":
#      • the season total is RIGHT-SKEWED (a career year is unbounded; a floor sits at 0), so a
#        symmetric band cannot fit both tails at once;
#      • the dominant veteran risk is NOT game-to-game scoring noise, it is AVAILABILITY AND ROLE — a
#        player who loses his job or tears an ACL scores a fraction of his projection, and no
#        game-to-game sd measured on the games he DID play can see that. `season_sd` is a
#        within-season-conditional-on-playing quantity being asked to price an out-of-season event.
#    Hence the pre-registered candidates are CONDITIONAL-QUANTILE estimators of the realized season on
#    the served point, not variance rescalings of it — with the variance rescalings kept as the honest
#    nulls (`normal_scaled`, `normal_cov`) so "we needed a new shape, not a bigger sigma" is a measured
#    claim rather than an assertion.
#
# ⚖️ WHAT IS SELECTED — the WIDTH AND SHAPE of the veteran 80% interval, and NOTHING ELSE. The POINT
#    projection is held identical across every arm and asserted (`< 1e-9`, not byte-equality — a
#    polyfit/DuckDB ordering ULP is not a model change).
_VET_BAND_FORMS = ("normal", "normal_scaled", "normal_cov", "ratio_q", "ratio_q_floor",
                   "knn_pos", "knn_norm", "qreg", "qreg_sqrt")
_VET_BAND_Q = (0.10, 0.90)
# A veteran fold carries THOUSANDS of rows (vs a rookie class's ~80), so these floors are about
# refusing a degenerate fit, not about scarcity. A form whose fit is refused emits NaN and the caller
# falls back to the served normal band — recorded as a fallback, never silently.
_VET_BAND_MIN_TRAIN = 200
_VET_BAND_MIN_POS_TRAIN = 100
_VET_BAND_CQR_K = 4              # cross-conformal folds (every training row used for both jobs)
_VET_BAND_CQR_MIN_CALIB = 50     # below this a GROUP falls back to the pooled quantile, and is recorded
_VET_BAND_CQR_MODES = ("", "pos", "pool")
_VET_BAND_CQR_SCALES = ("add", "width")
# The dispersion-multiplier grid for the two variance-rescaling nulls. Spans "sharpen a little" to
# "3× the served sigma" so the nulls are given every chance — the finding must not be an artifact of a
# grid that could not reach the answer.
_VET_SD_SCALE_GRID = tuple(np.round(np.arange(0.6, 3.01, 0.05), 2).tolist())
# ⬇ THE SHIPPED SELECTION — `knn_norm k300 · sdgain 0`, from 75 configs × 13 held-out target seasons
#   (8,401 veteran-seasons). See `ablation_results/nf1_9_veteran_perposition_floor.md`.
#     · held-out interval score **205.96 → 160.89 (−21.9%)** against the served normal approximation;
#     · pooled coverage **0.545 → 0.890** (floor 0.80), and every CONSTRAINED position clears the
#       nominal floor with room: QB 0.682 → 0.858, RB 0.549 → 0.887, TE 0.536 → 0.888, WR 0.511 → 0.907
#       (Tier 1; the documented Tier-2 relaxation was NOT needed). FB stays unconstrained (n < 400).
#     · the two-sided tail split goes 0.272/0.183 → 0.025/0.085 (below p10 / above p90);
#     · deflation: PBO(eligible) 0.0 over 1,716 balanced season splits, Bailey degradation 0.21%,
#       contender spread 1.43% against a 28.0% whole-field spread ⇒ a genuinely separated winner;
#     · the veteran POINT projection is unchanged (asserted `< 1e-9`, not byte-equality).
#   ⚠️ `knn_pos` (no position-invariance assumption) is only 0.7% behind and inside the tie band, so the
#   position-invariant-shape assumption `knn_norm` makes is NOT load-bearing — it buys resolution, and
#   the two arms agree. ⚠️ The PARAMETRIC foil (`qreg*`) lost by ~2–10%: a single linear conditional q10
#   cannot express a target that is genuinely 0 for the bottom eight projection deciles and clearly
#   POSITIVE in the top one. A neighbourhood quantile handles that point mass natively.
#   `_VET_BAND_PER_PLAYER = False` reverts the board to the pre-NF1.9 normal approximation.
_VET_BAND_PER_PLAYER = True
_VET_BAND_FORM = "knn_norm"
_VET_BAND_K = 300
_VET_BAND_QREG_ALPHA = 0.01      # parametric arms only; unused by the shipped neighbourhood arm
_VET_BAND_QREG_PER_POS = False
# ⚠️ The conformal layer is OFF, and not by preference — on this population it is a MATHEMATICAL no-op.
# ~29% of conformity scores are EXACTLY 0 (a zero-outcome row whose lower bound floored at 0 scores
# exactly 0), so the (1−α) conformity quantile is pinned at 0 and a Mondrian adjustment has nothing it
# can move. All four CQR arms scored byte-identically to their base. It is also inapplicable to a
# neighbourhood form. Recorded because "we tried the NF1.8 winner's mechanism and it could not act here"
# is a finding, not an omission.
_VET_BAND_CQR_MODE = ""
_VET_BAND_CQR_SCALE = "add"
_VET_BAND_SD_GAIN = 0.0

# The band's design features. Every one is a BASE-SEASON (or projection-season roster) quantity, so
# nothing here can leak the outcome being predicted.
_VET_BAND_FEATURES = ("log_pred", "log_sd", "games", "base_games", "snap", "returner")


def veteran_band_inputs(position, point, season_sd, proj_games=None, base_games=None,
                        snap_share=None, seasons_missed=None) -> pd.DataFrame:
    """THE VETERAN BAND'S INPUT CONTRACT, assembled in ONE place.

    ⚠️ This exists so the FIT (over a historical walk-forward panel) and the SERVED EMIT (inside
    `project_veterans`) cannot drift apart. NF1.7 learned the same lesson from the other side: its
    first cut re-derived the rookie point instead of delegating to the served path and was wrong by up
    to 3.3 PPR. A band conditioned on a quantity the board never shows is the class-level defect in a
    new disguise, and a band FIT on features assembled differently from the ones it is later scored
    with is the same bug one level down.

    Missing optional columns fall through to honest neutral values (a player with no snap-share row
    contributes 0 to that feature, a player with no `seasons_missed` is not a returner) rather than
    refusing the row — the served board must always emit SOME band."""
    n = len(pd.Series(point))

    def _num(v, fill):
        if v is None:
            return np.full(n, float(fill))
        return pd.to_numeric(pd.Series(v).reset_index(drop=True),
                             errors="coerce").fillna(float(fill)).to_numpy(dtype=float)

    return pd.DataFrame({
        "position": np.array([str(p or "").upper()
                              for p in pd.Series(position).reset_index(drop=True)], dtype=object),
        "point": _num(point, 0.0),
        "season_sd": _num(season_sd, 0.0),
        "proj_games": _num(proj_games, 0.0),
        "base_games": _num(base_games, 0.0),
        "snap_share": _num(snap_share, 0.0),
        "seasons_missed": _num(seasons_missed, 0.0),
    })


@dataclass
class VeteranBandModel:
    """NF1.9 — the fitted PER-PLAYER veteran 80% band. One of the pre-registered forms below, all fit
    IN-FOLD on the realized outcomes of PRIOR target seasons (the FULL projected veteran population,
    players who ended up playing ZERO games carried as a real 0 — the population fix NF1.4 made for
    rookies, applied here for the first time).

    `form` — the candidate class (`run_veteran_interval_ablation.py` is the §0.5 gate):
      • `normal`        — the INCUMBENT: `point ± 1.2816·season_sd`, the served pre-NF1.9 band.
      • `normal_scaled` — the incumbent with a per-position dispersion MULTIPLIER fitted in-fold by
                          minimising the INTERVAL SCORE. The honest "just widen sigma" null, fitted on
                          the same proper score the selection uses so it is a fair null and not a
                          straw man.
      • `normal_cov`    — the same multiplier fitted instead to MATCH nominal coverage in-fold. The
                          NAIVE fix, and pre-registered specifically so the report can show what
                          fitting a band to a coverage TARGET costs on a proper score (E2.1-r, live).
      • `ratio_q`       — per-position empirical quantiles of the RATIO realized/predicted, applied
                          multiplicatively to the player's own point. Per-player and skew-aware, but
                          its width COLLAPSES as the point approaches zero.
      • `ratio_q_floor` — `ratio_q` + an ADDITIVE upside floor (the q90 of realized outcomes in the
                          position's bottom prediction decile), so a deep-bench projection still
                          carries the honest "a backup sometimes starts 12 games" upside.
      • `knn_pos`       — q10/q90 of the realized outcomes of the `k` nearest training veteran-seasons
                          in the POSITION's own prediction space. Non-parametric; `k` is the resolution.
      • `knn_norm`      — the same in POSITION-NORMALISED prediction space, pooled across positions.
      • `qreg`          — THE DIRECT-LEARNED FOIL: linear quantile regression (pinball, τ=0.10/0.90)
                          of the realized season on the named uncertainty drivers — log point, log
                          season sd, expected games, base-season games, snap share, returner flag,
                          position.
      • `qreg_sqrt`     — `qreg` on √y, inverted. Quantiles are invariant under a monotone transform,
                          so this remains a valid quantile estimate; it moves only WHERE linearity is
                          assumed (a right-skewed season total is more plausibly linear on √).

    `cqr_mode` conformalizes a fitted parametric band: `"pos"` = MONDRIAN / group-conditional (the
    conformity quantile read WITHIN the position — the instrument that actually carries a per-GROUP
    coverage guarantee, and what won NF1.8), `"pool"` = the pre-registered POOLED foil that separates
    "conformal helped" from "PER-POSITION conditioning helped". `cqr_scale` is `"add"` (points-scale)
    or `"width"` (proportional to the band's own width).

    `sd_gain` widens by the player's OWN small-sample PARAMETER uncertainty (`1/√base_games`,
    z-scored in-fold) — the per-player driver no outcome-neighbourhood can see, since a rate measured
    on 4 played games is far less certain than one measured on 17. ⚠️ STRICTLY WIDEN-ONLY
    (`max(z, 0)`), the NF1.7 anchor-guard-4 lesson: a two-sided version would let this knob SHARPEN
    half the field off a non-outcome signal, i.e. buy interval score by narrowing bands, which is the
    exact trade the coverage floor exists to forbid."""

    form: str = _VET_BAND_FORM
    k: int = _VET_BAND_K
    sd_gain: float = _VET_BAND_SD_GAIN
    qreg_alpha: float = _VET_BAND_QREG_ALPHA
    qreg_per_pos: bool = False
    cqr_mode: str = ""
    cqr_scale: str = "add"
    cqr_k: int = _VET_BAND_CQR_K
    n_fit: int = 0
    lo_q: float = 0.10
    hi_q: float = 0.90
    positions: tuple = ()
    scale: dict = field(default_factory=dict)          # position -> normalising prediction level
    pos_pred: dict = field(default_factory=dict)
    pos_real: dict = field(default_factory=dict)
    pool_pred: np.ndarray | None = None
    pool_real: np.ndarray | None = None
    ratio_lo: dict = field(default_factory=dict)
    ratio_hi: dict = field(default_factory=dict)
    floor_hi: dict = field(default_factory=dict)
    sd_scale: dict = field(default_factory=dict)       # position -> dispersion multiplier
    qreg_lo: dict = field(default_factory=dict)
    qreg_hi: dict = field(default_factory=dict)
    qreg_lo_pos: dict = field(default_factory=dict)
    qreg_hi_pos: dict = field(default_factory=dict)
    # ⭐ BOTH conformal scalings are stored from ONE cross-conformal pass (the `"width"` score is the
    #   `"add"` score divided by the row's own band width, so a second pass would re-fit the identical
    #   models to learn nothing new). `cqr_mode`/`cqr_scale` then select at band time, which is what
    #   makes the four CQR arms cost one fit rather than four.
    conformal: dict = field(default_factory=dict)      # scale -> {group|_CQR_POOL_KEY: adjustment}
    cqr_pooled_groups: tuple = ()
    cqr_n_calib: dict = field(default_factory=dict)
    param_unc_ref: tuple = (0.0, 1.0)                  # in-fold (mean, sd) of 1/√base_games

    # ── prediction ──────────────────────────────────────────────────────────────────────────
    def band_many(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Per-player (lo, hi) over a `veteran_band_inputs` frame. NaN for a row the fit cannot speak
        to (an unseen position, a form whose parameters were never fitted) — the caller then falls
        back to the served normal band, so a thin fit DEGRADES rather than fabricating an interval.

        Two invariants on every form: the band is NON-NEGATIVE (a fantasy season cannot be negative)
        and it BRACKETS the point projection (a displayed interval that excludes its own point
        estimate is incoherent)."""
        pos = np.asarray(frame["position"].to_numpy(), dtype=object)
        pred = frame["point"].to_numpy(dtype=float)
        sd = frame["season_sd"].to_numpy(dtype=float)
        n = len(pred)
        lo = np.full(n, np.nan)
        hi = np.full(n, np.nan)
        z = _Z80_SEASON

        if self.form == "normal":
            lo, hi = pred - z * sd, pred + z * sd
        elif self.form in ("normal_scaled", "normal_cov"):
            mult = np.array([float(self.sd_scale.get(p, np.nan)) for p in pos], dtype=float)
            lo, hi = pred - z * mult * sd, pred + z * mult * sd
        elif self.form in ("ratio_q", "ratio_q_floor"):
            for p in np.unique(pos):
                if p not in self.ratio_lo:
                    continue
                idx = np.where(pos == p)[0]
                lo[idx] = self.ratio_lo[p] * pred[idx]
                hi[idx] = self.ratio_hi[p] * pred[idx]
                if self.form == "ratio_q_floor":
                    hi[idx] = hi[idx] + float(self.floor_hi.get(p, 0.0))
        elif self.form == "knn_pos":
            for p in np.unique(pos):
                tx, ty = self.pos_pred.get(p), self.pos_real.get(p)
                if tx is None or len(tx) < _VET_BAND_MIN_POS_TRAIN:
                    continue
                idx = np.where(pos == p)[0]
                lo[idx], hi[idx] = _knn_interval(tx, ty, pred[idx], self.k, self.lo_q, self.hi_q)
        elif self.form == "knn_norm":
            if self.pool_pred is not None and len(self.pool_pred) >= _VET_BAND_MIN_TRAIN:
                for p in np.unique(pos):
                    s = float(self.scale.get(p, 0.0))
                    if s <= 0:
                        continue
                    idx = np.where(pos == p)[0]
                    l, h = _knn_interval(self.pool_pred, self.pool_real, pred[idx] / s,
                                         self.k, self.lo_q, self.hi_q)
                    lo[idx], hi[idx] = l * s, h * s
        elif self.form in ("qreg", "qreg_sqrt"):
            if self.qreg_per_pos:
                for p in np.unique(pos):
                    clo, chi = self.qreg_lo_pos.get(p), self.qreg_hi_pos.get(p)
                    if not clo or not chi:
                        continue
                    idx = np.where(pos == p)[0]
                    x = self._design(frame.iloc[idx], with_positions=False)
                    lo[idx] = _apply_linear(clo, x)
                    hi[idx] = _apply_linear(chi, x)
            elif self.qreg_lo and self.qreg_hi:
                x = self._design(frame)
                lo = _apply_linear(self.qreg_lo, x)
                hi = _apply_linear(self.qreg_hi, x)
            if self.form == "qreg_sqrt":
                lo = np.clip(lo, 0.0, None) ** 2
                hi = np.clip(hi, 0.0, None) ** 2

        # ⭐ the CONFORMAL adjustment, BEFORE the widener so the conformity scores the calibration
        #   folds measured describe the same band shape this inflates. A per-GROUP SCALAR, so it moves
        #   every member of a group together and can never narrow a chosen player.
        table = self.conformal.get(self.cqr_scale) if self.cqr_mode else None
        if table:
            qp = float(table.get(_CQR_POOL_KEY, 0.0))
            adj = (np.array([float(table.get(p, qp)) for p in pos], dtype=float)
                   if self.cqr_mode == "pos" else np.full(n, qp))
            if self.cqr_scale == "width":
                w = np.maximum(hi - lo, _CQR_MIN_WIDTH)
                lo, hi = lo - adj * w, hi + adj * w
            else:
                lo, hi = lo - adj, hi + adj

        # ⭐ WIDEN-ONLY by the player's own small-sample parameter uncertainty (see the class docstring).
        if self.sd_gain > 0:
            m0, s0 = self.param_unc_ref
            pu = _vet_param_uncertainty(frame)
            zsd = np.where(np.isfinite(pu), (pu - m0) / (s0 or 1.0), 0.0)
            grow = np.exp(self.sd_gain * np.clip(zsd, 0.0, 2.0))
            mid = 0.5 * (lo + hi)
            half = 0.5 * (hi - lo) * grow
            lo, hi = mid - half, mid + half

        lo = np.clip(np.minimum(lo, pred), 0.0, None)
        hi = np.maximum(hi, pred)
        return lo, hi

    # ── the design matrix (shared by fit + predict, so they cannot drift) ────────────────────
    def _design(self, frame: pd.DataFrame, with_positions: bool = True) -> pd.DataFrame:
        """`with_positions=False` drops the dummies — the per-position fit, where the position is the
        GROUPING rather than a feature (a dummy shifts only the intercept)."""
        x = pd.DataFrame({
            "log_pred": np.log1p(np.clip(frame["point"].to_numpy(dtype=float), 0.0, None)),
            "log_sd": np.log1p(np.clip(frame["season_sd"].to_numpy(dtype=float), 0.0, None)),
            "games": frame["proj_games"].to_numpy(dtype=float) / 17.0,
            "base_games": frame["base_games"].to_numpy(dtype=float) / 17.0,
            "snap": np.clip(frame["snap_share"].to_numpy(dtype=float), 0.0, 1.0),
            "returner": (frame["seasons_missed"].to_numpy(dtype=float) >= 1).astype(float),
        })
        if with_positions:
            pos = np.asarray(frame["position"].to_numpy(), dtype=object)
            for p in self.positions[1:]:           # first position is the reference level
                x[f"pos_{p}"] = (pos == p).astype(float)
        return x


_Z80_SEASON = 1.2815515594


def _apply_linear(coefs: dict, x: pd.DataFrame) -> np.ndarray:
    beta = np.array([float(coefs.get(c, 0.0)) for c in x.columns], dtype=float)
    return x.to_numpy(dtype=float) @ beta + float(coefs.get("intercept", 0.0))


def _vet_param_uncertainty(frame: pd.DataFrame) -> np.ndarray:
    """`1/√base_games` — the per-player PARAMETER uncertainty of the base-season per-game rate the
    whole projection is built on. A rate from 4 played games is far less certain than one from 17, and
    no neighbourhood of OUTCOMES can see that; it is the veteran analogue of the rookie band's P1A
    parameter sd."""
    g = np.clip(frame["base_games"].to_numpy(dtype=float), 1.0, None)
    return 1.0 / np.sqrt(g)


def _fit_vet_qreg_into(m: VeteranBandModel, frame: pd.DataFrame, y: np.ndarray) -> None:
    """Fit `m`'s quantile pair in place — POOLED with position dummies, or a SEPARATE pair per
    position when `m.qreg_per_pos`. Factored out because the cross-conformal calibration has to re-fit
    the very same arm on each fold's complement, and a re-implementation there could silently
    calibrate a band shape that is not the one served."""
    try:
        import sklearn.linear_model  # noqa: F401
    except ImportError:                                    # pragma: no cover - sklearn is a dep
        return
    target = np.sqrt(np.clip(y, 0.0, None)) if m.form == "qreg_sqrt" else y
    pos = np.asarray(frame["position"].to_numpy(), dtype=object)
    if m.qreg_per_pos:
        for p in np.unique(pos):
            sel = pos == p
            if sel.sum() < _VET_BAND_MIN_POS_TRAIN:
                continue                                   # → NaN → the normal-band fallback
            x = m._design(frame.loc[sel], with_positions=False)
            m.qreg_lo_pos[p] = _pinball_fit(x, target[sel], m.lo_q, m.qreg_alpha)
            m.qreg_hi_pos[p] = _pinball_fit(x, target[sel], m.hi_q, m.qreg_alpha)
        return
    x = m._design(frame)
    m.qreg_lo.update(_pinball_fit(x, target, m.lo_q, m.qreg_alpha))
    m.qreg_hi.update(_pinball_fit(x, target, m.hi_q, m.qreg_alpha))


def _fit_vet_conformal_into(m: VeteranBandModel, frame: pd.DataFrame, y: np.ndarray) -> None:
    """CROSS-CONFORMAL calibration of `m`'s fitted band (Vovk cross-conformal / CQR), computing BOTH
    scalings and BOTH aggregations in one pass.

    For each of `cqr_k` deterministic folds the arm is re-fit on the complement and scored on the held
    fold, giving every training row an out-of-fold conformity score

        E_i = max(lo(x_i) − y_i,  y_i − hi(x_i))                     ('add')
        E_i / max(width_i, 1)                                        ('width')

    A group's adjustment is the ⌈(1−α)(n+1)⌉/n quantile of that group's E — the finite-sample
    split-conformal level, which is what makes the per-group coverage claim a guarantee at the GROUP's
    own sample size rather than an asymptotic hope.

    ⚠️ CROSS-conformal, not a single split: a per-position calibration split would have to divide each
    position's rows between fitting and calibrating, leaving both halves thinner than either job wants.
    Cross-conformal spends every row on both.

    ⚠️ A GROUP TOO THIN FOR ITS OWN QUANTILE FALLS BACK TO THE POOLED ONE AND IS RECORDED
    (`cqr_pooled_groups`) — a silently-pooled group would be a per-position claim the fit never made,
    which is the NF1.7 lesson-(1) shape (an estimate that quietly fails to fit makes its own check
    vacuous)."""
    if m.form not in ("qreg", "qreg_sqrt"):
        return
    n = len(y)
    alpha = 1.0 - (m.hi_q - m.lo_q)
    pos = np.asarray(frame["position"].to_numpy(), dtype=object)
    pred = frame["point"].to_numpy(dtype=float)
    # a DETERMINISTIC fold assignment (no RNG — a seeded split would make the fitted band depend on the
    # draw): order within position by the conditioning variable, then deal round-robin, so every fold
    # gets a balanced spread of every position and prediction level.
    order = np.lexsort((pred, pos))
    fold = np.empty(n, dtype=int)
    fold[order] = np.arange(n) % max(2, int(m.cqr_k))
    scores: dict[str, list[tuple[str, float]]] = {"add": [], "width": []}
    for f in range(max(2, int(m.cqr_k))):
        trn, cal = fold != f, fold == f
        if trn.sum() < _VET_BAND_MIN_TRAIN or cal.sum() < 3:
            continue
        sub = VeteranBandModel(form=m.form, k=m.k, qreg_alpha=m.qreg_alpha,
                              qreg_per_pos=m.qreg_per_pos, lo_q=m.lo_q, hi_q=m.hi_q,
                              positions=m.positions, param_unc_ref=m.param_unc_ref,
                              n_fit=int(trn.sum()))
        _fit_vet_qreg_into(sub, frame.loc[trn], y[trn])
        lo, hi = sub.band_many(frame.loc[cal])
        good = np.isfinite(lo) & np.isfinite(hi)
        if not good.any():
            continue
        yc = y[cal][good]
        e = np.maximum(lo[good] - yc, yc - hi[good])
        w = np.maximum(hi[good] - lo[good], _CQR_MIN_WIDTH)
        gp = pos[cal][good].tolist()
        scores["add"].extend(zip(gp, e.tolist()))
        scores["width"].extend(zip(gp, (e / w).tolist()))
    if not scores["add"]:
        return
    thin: set = set()
    for sc, rows in scores.items():
        by_group: dict[str, list[float]] = {}
        for p, e in rows:
            by_group.setdefault(p, []).append(e)
        table = {_CQR_POOL_KEY: _conformity_quantile([e for _, e in rows], alpha)}
        for p, vals in by_group.items():
            m.cqr_n_calib[p] = len(vals)
            if len(vals) >= _VET_BAND_CQR_MIN_CALIB:
                table[p] = _conformity_quantile(vals, alpha)
            else:
                thin.add(p)
        m.conformal[sc] = table
    m.cqr_pooled_groups = tuple(sorted(thin))


def _fit_sd_multiplier(y: np.ndarray, pred: np.ndarray, sd: np.ndarray, mode: str,
                       lo_q: float, hi_q: float) -> float:
    """The per-position dispersion multiplier for the two variance-rescaling NULLS.

    `mode="score"` (`normal_scaled`) minimises the in-fold INTERVAL SCORE — a PROPER score, so this
    null is fitted on the same criterion the selection uses and cannot be dismissed as a straw man.
    `mode="coverage"` (`normal_cov`) instead picks the multiplier whose in-fold coverage is closest to
    nominal. That is pre-registered precisely BECAUSE it is the naive fix: E2.1-r says a coverage
    figure is a FLOOR and never a target, and the two arms side by side put a number on what fitting a
    band to a coverage target costs."""
    alpha = 1.0 - (hi_q - lo_q)
    best, best_v = 1.0, np.inf
    for mult in _VET_SD_SCALE_GRID:
        lo = np.clip(pred - _Z80_SEASON * mult * sd, 0.0, None)
        hi = pred + _Z80_SEASON * mult * sd
        if mode == "coverage":
            v = abs(float(np.mean((y >= lo) & (y <= hi))) - (hi_q - lo_q))
        else:
            v = float(np.mean(_interval_score(lo, hi, y, alpha)))
        if v < best_v:
            best, best_v = float(mult), v
    return best


def fit_veteran_band_model(
    panel: pd.DataFrame,
    *,
    form: str = _VET_BAND_FORM,
    k: int = _VET_BAND_K,
    sd_gain: float = _VET_BAND_SD_GAIN,
    qreg_alpha: float = _VET_BAND_QREG_ALPHA,
    qreg_per_pos: bool = False,
    cqr_mode: str = "",
    cqr_scale: str = "add",
    cqr_k: int = _VET_BAND_CQR_K,
    band_q: tuple[float, float] = _VET_BAND_Q,
    real_col: str = "real_fp_ppr",
) -> VeteranBandModel | None:
    """NF1.9 §0.5 — fit ONE pre-registered per-player veteran band form on a historical walk-forward
    panel.

    `panel` is one row per (prior target season × projected veteran): the `veteran_band_inputs`
    contract columns PLUS `real_col`, the realized season total — with players who ended up playing
    ZERO games carried as a real 0. That population choice is the whole ballgame: filtering to players
    who actually played (the ≥6-game filter every OTHER veteran backtest in this program uses, and
    correctly, for a RANK read) would grade the interval only on the cases where availability risk did
    not materialise, which is exactly the risk the band exists to price.

    Pure. Returns None when the panel is too thin to fit anything, so the caller keeps the served
    normal band."""
    if panel is None or panel.empty or form not in _VET_BAND_FORMS:
        return None
    if cqr_mode not in _VET_BAND_CQR_MODES or cqr_scale not in _VET_BAND_CQR_SCALES:
        raise ValueError(f"unknown conformal setting: cqr_mode={cqr_mode!r} cqr_scale={cqr_scale!r}")
    lo_q, hi_q = band_q
    frame = veteran_band_inputs(
        panel["position"], panel["point"] if "point" in panel else panel["proj_fp_ppr"],
        panel["season_sd"] if "season_sd" in panel else panel["fp_ppr_sd"],
        proj_games=panel.get("proj_games"), base_games=panel.get("base_games"),
        snap_share=panel.get("snap_share"), seasons_missed=panel.get("seasons_missed"))
    y = pd.to_numeric(pd.Series(panel[real_col]).reset_index(drop=True),
                      errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(y) & np.isfinite(frame["point"].to_numpy(dtype=float))
    if int(ok.sum()) < _VET_BAND_MIN_TRAIN:
        return None
    frame, y = frame.loc[ok].reset_index(drop=True), y[ok]
    pos = np.asarray(frame["position"].to_numpy(), dtype=object)
    pred = frame["point"].to_numpy(dtype=float)
    sd = frame["season_sd"].to_numpy(dtype=float)

    m = VeteranBandModel(form=form, k=int(k), sd_gain=float(sd_gain), qreg_alpha=float(qreg_alpha),
                         qreg_per_pos=bool(qreg_per_pos), cqr_mode=str(cqr_mode),
                         cqr_scale=str(cqr_scale), cqr_k=int(cqr_k), n_fit=int(len(y)),
                         lo_q=lo_q, hi_q=hi_q,
                         positions=tuple(sorted(np.unique(pos).tolist())))
    pu = _vet_param_uncertainty(frame)
    m.param_unc_ref = (float(np.nanmean(pu)), float(np.nanstd(pu)) or 1.0)

    for p in np.unique(pos):
        sel = pos == p
        if sel.sum() < _VET_BAND_MIN_POS_TRAIN:
            continue
        m.pos_pred[p] = pred[sel]
        m.pos_real[p] = y[sel]
        lvl = float(np.mean(y[sel]))
        m.scale[p] = lvl if lvl > 1e-6 else float(np.mean(pred[sel]) or 1.0)
        pr = pred[sel]
        ratio = np.where(pr > 1e-6, y[sel] / np.where(pr > 1e-6, pr, 1.0), np.nan)
        ratio = ratio[np.isfinite(ratio)]
        if len(ratio) >= _VET_BAND_MIN_POS_TRAIN:
            m.ratio_lo[p] = float(np.quantile(ratio, lo_q))
            m.ratio_hi[p] = float(np.quantile(ratio, hi_q))
            cut = float(np.quantile(pr, 0.10))
            bottom = y[sel][pr <= cut]
            m.floor_hi[p] = float(np.quantile(bottom, hi_q)) if len(bottom) >= 10 else 0.0
        if form in ("normal_scaled", "normal_cov"):
            m.sd_scale[p] = _fit_sd_multiplier(
                y[sel], pr, sd[sel], "coverage" if form == "normal_cov" else "score", lo_q, hi_q)

    if m.scale:
        keep = np.array([p in m.scale for p in pos])
        s = np.array([m.scale.get(p, 1.0) for p in pos])[keep]
        m.pool_pred = pred[keep] / s
        m.pool_real = y[keep] / s

    if form in ("qreg", "qreg_sqrt"):
        _fit_vet_qreg_into(m, frame, y)
        if not (m.qreg_lo or m.qreg_lo_pos):
            return None                                    # sklearn absent, or every group thin
        if cqr_mode:
            _fit_vet_conformal_into(m, frame, y)
    return m


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
    #    the slot-EXPECTED z — the disagreement the draft board did not price, as a mild clipped
    #    multiplicative nudge. NF1.7 factored the computation into `p1a_residual_nudge` so the band
    #    fit conditions on the identical served point projection (same code, no drift).
    nudge = p1a_residual_nudge(r["position_group"].to_numpy(), overall,
                               r.get("projected_nfl_z"), residual_lambda)

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
    # THREE TIERS, best first (each is the honest fallback for the one above):
    #  1. NF1.7 `band_model` — a PER-PLAYER band, width driven by the player's own point projection
    #     (+ draft slot / P1A sd, per the selected form). Selected on a PROPER interval score with
    #     coverage as a FLOOR (`run_rookie_interval_ablation.py`).
    #  2. NF1.4 `curve.band()` — the CLASS-LEVEL tercile bucket. Nominally calibrated (0.834 coverage)
    #     but carries ~zero per-player information: 81 rookies shared 12 bands on the 2026 board.
    #  3. the legacy `fp × cv` parameter width — covers only 0.678 (0.444 at QB); a decoration, kept
    #     solely so an un-migrated caller (no `band_hist`) still gets *a* band, honestly labelled.
    fp = df["proj_fp_ppr"].to_numpy()
    cv = np.array([curve.fp_cv_by_pos.get(p, 0.7) for p in pos_group])
    z80 = 1.2815515594
    calibrated = [curve.band(pos_group[i], float(fp[i])) for i in range(len(df))]
    lo = np.array([b[0] if b else max(0.0, fp[i] - z80 * fp[i] * cv[i])
                   for i, b in enumerate(calibrated)])
    hi = np.array([b[1] if b else fp[i] + z80 * fp[i] * cv[i] for i, b in enumerate(calibrated)])
    tier = np.where([b is not None for b in calibrated], "calibrated", "parameter").astype(object)
    if curve.band_model is not None:
        p_lo, p_hi = curve.band_model.band_many(
            pos_group, fp, overall=overall, resid_sd=r.get("projected_nfl_z_sd"))
        use = np.isfinite(p_lo) & np.isfinite(p_hi) & (p_hi >= p_lo)
        lo = np.where(use, p_lo, lo)
        hi = np.where(use, p_hi, hi)
        tier = np.where(use, "calibrated_per_player", tier)
    df["fp_ppr_sd"] = np.round((hi - lo) / (2 * z80), 2)   # the band's implied 1-sd equivalent
    # Round the bounds OUTWARD (p10 down, p90 up). Every tier guarantees lo ≤ point ≤ hi, but
    # nearest-rounding can push a bound past a point projection it exactly equals and emit a
    # displayed interval that excludes its own point estimate.
    # ⚠️ The min/max clamps are load-bearing — see the same note in `project_veterans`: `floor(x*10)/10`
    # is not always ≤ x in float64, so "outward" without the clamp is only nearly-always outward.
    lo = np.clip(lo, 0.0, None)
    df["fp_ppr_p10"] = np.minimum(np.floor(lo * 10.0) / 10.0, lo)
    df["fp_ppr_p90"] = np.maximum(np.ceil(hi * 10.0) / 10.0, hi)
    df["uncertainty_type"] = tier
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
