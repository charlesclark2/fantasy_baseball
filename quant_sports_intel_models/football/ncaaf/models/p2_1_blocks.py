"""p2_1_blocks.py — NCAAF-P2.1: the pre-registered hypothesis BLOCKS.

Each registered hypothesis (`ncaaf_p2_1_preregistration.md` §2) is one BLOCK: a set of columns
added to the P1.4 reference contract, everything else held byte-identical. This module is the pure,
unit-testable definition of those blocks — the registry a guard test pins so a block cannot silently
change after pre-registration.

TWO KINDS OF BLOCK
------------------
* **RAW** — columns that exist verbatim on the assembled frame (all of them leakage-safe by
  construction: strictly-prior season-to-date, or a pre-game schedule/venue fact).
* **IN-FOLD** — columns that must be FIT on the fold's TRAIN rows and only then applied to eval
  (the empirical-Bayes per-team HFA, and every z-scored MatchupGap). A block that fits anything on
  eval rows is leakage; the in-fold builders take `(tr, ev)` and return `(tr_cols, ev_cols)`.

⛔ The reference contract itself is NEVER modified by a block — an arm is `reference ∪ block`, which
is what makes the paired read (NF-D10) valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# The doc §6.2 compact matchup set — MatchupGap_k = Z(Off_k) − Z(DefAllowed_k)
# ---------------------------------------------------------------------------
# Each entry: (gap name, offence column stem, defence-allowed column stem, source).
# `source` records WHERE the pair came from, because the pre-registration (V6) found that only 4 of
# the doc's 9 interactions exist in the P1.3 matrix; the other 5 are built by the P2.1 plays rollup.
MATCHUP_PAIRS: tuple[tuple[str, str, str, str], ...] = (
    ("rush_line",     "off_line_yards",       "def_line_yards",       "matrix"),   # doc: rush-off vs rush-def
    ("rush_stuff",    "off_stuff_rate",       "def_stuff_rate",       "matrix"),   # doc: rush-off vs rush-def
    ("explosive",     "off_explosiveness",    "def_explosiveness",    "matrix"),   # doc: explosiveness gen-vs-allowed
    ("success",       "off_success_rate",     "def_success_rate",     "matrix"),
    ("clean_ppa",     "off_clean_ppa",        "def_clean_ppa",        "matrix"),
    ("pass",          "st_off_pass_ppa",      "st_def_pass_ppa",      "plays"),    # doc: pass-off vs pass-def
    ("std_down",      "st_off_sd_ppa",        "st_def_sd_ppa",        "plays"),    # doc: standard downs
    ("pass_down",     "st_off_pd_ppa",        "st_def_pd_ppa",        "plays"),    # doc: passing downs
    ("redzone",       "st_off_rz_ppa",        "st_def_rz_ppa",        "plays"),    # doc: finishing drives vs RZ-D
    ("havoc",         "st_havoc_allowed",     "st_havoc_made",        "plays"),    # doc: havoc
    ("pressure",      "st_sack_rate_allowed", "st_sack_rate_made",    "plays"),    # doc: pressure susc. vs gen.
)

# doc §6.2 items expressible WITHOUT an off/def gap (they are team-style levels, not gaps)
_STYLE_COLS: tuple[str, ...] = (
    "seconds_per_play", "off_plays_per_game",          # doc: pace
    "rushing_yards_per_game", "passing_yards_per_game",  # doc: run/pass stylistic conflict
)


# ---------------------------------------------------------------------------
# The pace composites — ONE implementation, two callers (P2.1's battery assemble and P1.4's
# serving assemble). ⭐ NCAAF-P2.1-S1-serve: the served representation is `pace_axis` =
# {pace_sum, pace_diff}, so the SERVING derivation must be byte-identical to the one the S1
# certification scored — two renderers of one field would be two rule sets (the E9.61 lesson).
# ---------------------------------------------------------------------------

#: the per-side level the composites are built from (the `possession_seconds / off_plays` ratio,
#: `feature_ncaaf_pregame_matrix.sql` L220/L312 — S1-V4 verified the identity holds exactly).
PACE_SIDE_COL = "seconds_per_play"

#: the two GAME-level composites. `pace_sum` is the TOTAL axis (slow+slow ⇒ fewer possessions);
#: `pace_diff` is the margin axis (S1 §3 measured it at the edge of the tie band).
PACE_COMPOSITE_COLS: tuple[str, ...] = ("pace_sum", "pace_diff")


def derive_pace_composites(df: pd.DataFrame) -> pd.DataFrame:
    """Add `pace_sum` / `pace_diff` to `df` IN PLACE-of-a-copy and return it.

    NULL propagates: if either side's `seconds_per_play` is NULL (every week-1 row — the team-week
    rollup's honest empty row) BOTH composites are NULL, which is what makes the served pace term
    inert pre-season (S1-V6/V7).
    """
    out = df.copy()
    missing = [f"{s}_{PACE_SIDE_COL}" for s in ("home", "away") if f"{s}_{PACE_SIDE_COL}" not in out.columns]
    if missing:
        raise KeyError(f"cannot derive the pace composites — absent column(s) {missing}. A missing "
                       "pace source must RAISE, never silently produce a pace-free frame (NF1.7 a).")
    spp = [pd.to_numeric(out[f"{s}_{PACE_SIDE_COL}"], errors="coerce") for s in ("home", "away")]
    out["pace_sum"] = spp[0] + spp[1]      # the TOTAL axis: slow+slow ⇒ fewer possessions
    out["pace_diff"] = spp[0] - spp[1]
    return out


def _z(train: pd.Series, target: pd.Series) -> np.ndarray:
    """z-score `target` using TRAIN-only mean/sd (leakage-safe). A zero-variance train column maps
    to zeros rather than infinities."""
    t = pd.to_numeric(train, errors="coerce")
    mu, sd = float(t.mean()), float(t.std(ddof=0))
    v = pd.to_numeric(target, errors="coerce").to_numpy(float)
    if not np.isfinite(mu):
        return np.zeros(len(v))
    if not np.isfinite(sd) or sd <= 1e-12:
        return np.nan_to_num(v - mu)
    return np.nan_to_num((v - mu) / sd)


# ---------------------------------------------------------------------------
# IN-FOLD builders
# ---------------------------------------------------------------------------

def matchup_gap_infold(tr: pd.DataFrame, ev: pd.DataFrame, pairs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MatchupGap_k for both sides plus their difference, z-scored on TRAIN only.

        home_gap_k = Z(home_off_k) − Z(away_def_k)
        away_gap_k = Z(away_off_k) − Z(home_def_k)
        gap_diff_k = home_gap_k − away_gap_k        ← the game-level matchup term

    Both sides' offence columns share ONE z-fit (they are the same quantity measured on two teams),
    likewise the defence columns — otherwise home and away would sit on different scales and the
    difference would be meaningless.
    """
    a, b = pd.DataFrame(index=tr.index), pd.DataFrame(index=ev.index)
    for name, off_stem, def_stem, _src in pairs:
        ho, ao = f"home_{off_stem}", f"away_{off_stem}"
        hd, ad = f"home_{def_stem}", f"away_{def_stem}"
        if not all(c in tr.columns for c in (ho, ao, hd, ad)):
            continue
        off_train = pd.concat([tr[ho], tr[ao]], ignore_index=True)
        def_train = pd.concat([tr[hd], tr[ad]], ignore_index=True)
        for frame, src in ((a, tr), (b, ev)):
            h_gap = _z(off_train, src[ho]) - _z(def_train, src[ad])
            a_gap = _z(off_train, src[ao]) - _z(def_train, src[hd])
            frame[f"mg_{name}_home"] = h_gap
            frame[f"mg_{name}_away"] = a_gap
            frame[f"mg_{name}_diff"] = h_gap - a_gap
    return a, b


def strength_interaction_infold(tr: pd.DataFrame, ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """H2 — the off-vs-def INTERACTION the additive ridge structurally cannot express.

    Pre-registration V2: `home_strength_offense/defense` and their away twins ARE already in
    `strength_only` as LINEAR terms, so the spec's "the spread runs on net strength" premise is
    false. What is genuinely absent is the product term — a strong offence facing a weak defence is
    worth more than the sum of the two levels.
    """
    a, b = pd.DataFrame(index=tr.index), pd.DataFrame(index=ev.index)
    off_train = pd.concat([tr["home_strength_offense"], tr["away_strength_offense"]], ignore_index=True)
    def_train = pd.concat([tr["home_strength_defense"], tr["away_strength_defense"]], ignore_index=True)
    for frame, src in ((a, tr), (b, ev)):
        zho, zao = _z(off_train, src["home_strength_offense"]), _z(off_train, src["away_strength_offense"])
        zhd, zad = _z(def_train, src["home_strength_defense"]), _z(def_train, src["away_strength_defense"])
        frame["si_home_off_x_away_def"] = zho * zad
        frame["si_away_off_x_home_def"] = zao * zhd
        frame["si_interaction_diff"] = zho * zad - zao * zhd
    return a, b


# H1b: the shrinkage constant for the empirical-Bayes per-team HFA. `k` is the number of home games
# at which a team's own home-margin evidence is weighted equally with the global mean; 20 ≈ 2.5
# seasons of home games, a deliberately conservative pooling for a 137-team league whose median team
# has 58 home games in the window.
EB_HFA_K: float = 20.0


def eb_team_hfa_infold(tr: pd.DataFrame, ev: pd.DataFrame, *, k: float = EB_HFA_K,
                       shrink_to_global: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """H1b — a partial-pooled per-home-team home-field advantage, fit on TRAIN rows only.

        raw_t   = mean(home margin − strength_margin_diff)  over team t's NON-neutral home games
        hfa_t   = (n_t · raw_t + k · global) / (n_t + k)              (empirical-Bayes shrinkage)

    The residual `home margin − strength_margin_diff` is the part of the margin the P1.2 rating
    difference does NOT explain — i.e. the home bump. A team with few home games is pulled to the
    global bump; a team with many keeps its own.

    ⭐ `shrink_to_global=True` is the pre-registered MATCHED LEVEL-ONLY FOIL (`hfa_global`, NF-D15
    g′): the byte-identical construction with the shrinkage taken to ∞, so EVERY team receives the
    same global bump. If H1b does not beat this foil, the effect is a global level (already H1a's
    territory) and the per-TEAM claim is refuted rather than assumed.
    """
    if "label_home_margin" not in tr.columns:
        raise ValueError("eb_team_hfa_infold needs label_home_margin on the TRAIN frame")
    home_only = tr[~tr["is_neutral_site"].fillna(False).astype(bool)]
    resid = (pd.to_numeric(home_only["label_home_margin"], errors="coerce")
             - pd.to_numeric(home_only["strength_margin_diff"], errors="coerce"))
    ok = resid.notna()
    if int(ok.sum()) < 100:
        raise ValueError(f"eb_team_hfa_infold: only {int(ok.sum())} usable train rows — anchor "
                         "cannot be fit, and an unfittable anchor must RAISE, never pass (NF1.7 a)")
    glob = float(resid[ok].mean())
    grp = resid[ok].groupby(home_only.loc[ok, "home_team"])
    n_t, raw_t = grp.count(), grp.mean()
    if shrink_to_global:
        hfa = pd.Series(glob, index=raw_t.index)
    else:
        hfa = (n_t * raw_t + k * glob) / (n_t + k)

    a, b = pd.DataFrame(index=tr.index), pd.DataFrame(index=ev.index)
    for frame, src in ((a, tr), (b, ev)):
        v = src["home_team"].map(hfa).astype(float).fillna(glob).to_numpy()
        # a neutral-site game gets NO home bump — the whole point of the hypothesis
        v = np.where(src["is_neutral_site"].fillna(False).astype(bool).to_numpy(), 0.0, v)
        frame["eb_team_hfa"] = v
    return a, b


def turnover_shrunk_infold(tr: pd.DataFrame, ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """H11 — turnover luck regresses. Emits the raw season-to-date turnover MARGIN differential and
    the sample-shrunk version `margin · n/(n+k)`; the PAIR is the hypothesis (if the shrunk term
    carries the signal and the raw does not, turnover luck genuinely regresses)."""
    a, b = pd.DataFrame(index=tr.index), pd.DataFrame(index=ev.index)
    k = 6.0
    for frame, src in ((a, tr), (b, ev)):
        def marg(side: str) -> np.ndarray:
            take = pd.to_numeric(src.get(f"{side}_st_takeaway_rate"), errors="coerce")
            give = pd.to_numeric(src.get(f"{side}_st_giveaway_rate"), errors="coerce")
            return np.nan_to_num((take - give).to_numpy(float))
        raw = marg("home") - marg("away")
        n = pd.to_numeric(src.get("home_st_n_prior_games"), errors="coerce").fillna(0.0).to_numpy(float)
        frame["to_margin_diff"] = raw
        frame["to_margin_diff_shrunk"] = raw * (n / (n + k))
    return a, b


def preseason_weight_infold(tr: pd.DataFrame, ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """H16 — the LIGHT preseason-prior weight foil: let the strength signal's weight vary with how
    much in-season evidence the two teams have. (The deep cold-start state-space init is P2.6.)"""
    a, b = pd.DataFrame(index=tr.index), pd.DataFrame(index=ev.index)
    for frame, src in ((a, tr), (b, ev)):
        gp = (pd.to_numeric(src["home_games_played"], errors="coerce").fillna(0.0)
              + pd.to_numeric(src["away_games_played"], errors="coerce").fillna(0.0)) / 2.0
        smd = pd.to_numeric(src["strength_margin_diff"], errors="coerce").fillna(0.0).to_numpy(float)
        w = 1.0 / (1.0 + gp.to_numpy(float))
        frame["pw_games_played_avg"] = gp.to_numpy(float)
        frame["pw_early_weight"] = w
        frame["pw_strength_x_early"] = smd * w
    return a, b


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Block:
    """One pre-registered hypothesis block. `raw` columns come off the assembled frame verbatim;
    `infold` is an optional (tr, ev) -> (tr_extra, ev_extra) builder."""
    arm: str
    hypothesis: str
    tier: int
    title: str
    raw: tuple[str, ...] = ()
    infold: Callable[..., tuple[pd.DataFrame, pd.DataFrame]] | None = None
    infold_kwargs: dict = field(default_factory=dict)


def _sides(*stems: str) -> tuple[str, ...]:
    return tuple(f"{side}_{s}" for s in stems for side in ("home", "away"))


HFA_VENUE_COLS: tuple[str, ...] = (
    "is_neutral_site", "game_venue_elevation_m", "game_venue_is_dome", "game_venue_is_grass",
    "away_travel_km", "away_altitude_change_m",
)

BLOCKS: tuple[Block, ...] = (
    # ── Tier 1 ────────────────────────────────────────────────────────────
    Block("hfa_venue", "H1a", 1, "team/venue HFA — venue & travel context", raw=HFA_VENUE_COLS),
    Block("hfa_team_eb", "H1b", 1, "team/venue HFA — EB-shrunk per-home-team HFA",
          raw=("is_neutral_site",), infold=eb_team_hfa_infold),
    Block("hfa_full", "H1c", 1, "team/venue HFA — venue context + per-team EB",
          raw=HFA_VENUE_COLS, infold=eb_team_hfa_infold),
    Block("matchup_interaction", "H2", 1, "matchup-aware spread — off×def interaction",
          infold=strength_interaction_infold),
    Block("matchup_unit", "H2b", 1, "unit-level matchup — the doc §6.2 compact set",
          raw=_sides(*_STYLE_COLS),
          infold=lambda tr, ev: matchup_gap_infold(tr, ev, MATCHUP_PAIRS)),
    # ── Tier 2 ────────────────────────────────────────────────────────────
    Block("rest", "H3", 2, "rest / bye differential",
          raw=("home_rest_days", "away_rest_days", "rest_days_diff",
               "home_off_bye", "away_off_bye", "off_bye_diff")),
    Block("lookahead_letdown", "H4", 2, "lookahead / letdown",
          raw=("home_next_opp_strength", "away_next_opp_strength",
               "home_prev_opp_strength", "away_prev_opp_strength",
               "lookahead_gap_diff", "letdown_gap_diff")),
    Block("rivalry", "H5", 2, "rivalry variance (PROXY — no rivalry list exists)",
          raw=("rivalry_prior_meetings", "is_rivalry_proxy", "rivalry_late_season")),
    Block("bowl", "H6", 2, "bowl regime",
          raw=("is_postseason_flag", "postseason_x_strength", "postseason_x_abs_strength")),
    # ── Tier 3 ────────────────────────────────────────────────────────────
    Block("qb_regime", "H7", 3, "QB-availability regime (LIGHT flag; the layer is P2.7)",
          raw=_sides("qb_starter_changed_recent", "qb_starts_prior",
                     "qb_distinct_starters_prior", "qb_trailing_qbr", "qb_trailing_ypa")),
    Block("recency", "H8", 3, "recency-weighted strength (trend residual)",
          raw=("home_recent_form", "away_recent_form", "recent_form_diff")),
    # ── Tier 4 ────────────────────────────────────────────────────────────
    Block("pace", "H9", 4, "pace / tempo",
          raw=_sides("seconds_per_play", "off_plays_per_game", "possession_seconds_per_game")
              + ("pace_sum", "pace_diff")),
    # H10 weather: NOT REGISTERED — no weather exists in the NCAAF lake (pre-registration V5).
    # ── Tier 5 ────────────────────────────────────────────────────────────
    Block("turnover_luck", "H11", 5, "turnover-luck regression", infold=turnover_shrunk_infold),
    Block("garbage_clean", "H12", 5, "garbage-time-excluded vs raw efficiency (matched pair)",
          raw=_sides("off_clean_ppa", "def_clean_ppa", "off_clean_success_rate",
                     "def_clean_success_rate", "off_ppa", "def_ppa",
                     "off_success_rate", "def_success_rate")),
    Block("special_teams", "H13", 5, "special-teams component",
          raw=_sides("st_fg_pct", "st_fg_rate", "st_fg_dist", "st_punt_gross",
                     "st_punt_ret_allowed", "st_td_for_rate", "st_td_against_rate",
                     "st_block_for_rate", "st_block_against_rate")),
    Block("preseason_weight", "H16", 5, "preseason-prior weight (LIGHT foil; deep version is P2.6)",
          infold=preseason_weight_infold),
)

#: the pre-registered REAL-arm field size — the number `classify_null(declared_field_size=…)` gets.
DECLARED_FIELD_SIZE: int = len(BLOCKS)

BLOCK_BY_ARM: dict[str, Block] = {b.arm: b for b in BLOCKS}


def block_columns(block: Block, tr: pd.DataFrame, ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Materialise one block for a fold. Returns (train extra, eval extra, column names)."""
    frames_tr, frames_ev, names = [], [], []
    raw = [c for c in block.raw if c in tr.columns]
    missing = [c for c in block.raw if c not in tr.columns]
    if missing:
        raise KeyError(f"block {block.arm!r} declares columns absent from the assembled frame: "
                       f"{missing} — a block whose columns are missing must RAISE, never silently "
                       "score a smaller feature set (NF1.7 a)")
    if raw:
        frames_tr.append(tr[raw]); frames_ev.append(ev[raw]); names += raw
    if block.infold is not None:
        a, b = block.infold(tr, ev, **block.infold_kwargs)
        frames_tr.append(a); frames_ev.append(b); names += list(a.columns)
    if not names:
        raise ValueError(f"block {block.arm!r} produced NO columns")
    return (pd.concat(frames_tr, axis=1), pd.concat(frames_ev, axis=1), names)
