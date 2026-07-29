"""board_assembly.py — MLB Edge-E8.0: the LEAN prospect draft board, assembly logic.

Pure pandas / no IO, so every rule below is exercised by the fast gate. The runner
(`build_prospect_board.py`) does the S3 reads and the export; everything that decides *what a row
means* lives here.

WHAT THIS PRODUCES
------------------
One row per **current-board prospect** (FanGraphs THE BOARD, newest snapshot), carrying three
INDEPENDENT views of the same player plus the places they disagree:

  1. **The scouts** — FanGraphs FV / rank / ETA / tool grades (E7.7 `the_board`).
  2. **Us** — the E7.3 / E7.3p MiLB→MLB translated line (MLB-equivalent K% / BB% / ISO for bats,
     K% / BB% / GB% for arms) with its parameter uncertainty, joined through E7.4's
     `dim_player_xref`.
  3. **Prospect Savant** (optional) — THEIR MiLB-Statcast expected stats, always labelled as theirs.

🔒 HONEST FRAME (`best_alpha = 0`). Nothing here claims to beat FanGraphs. `blend_score` is a
DISPLAY heuristic for ordering a draft board, not a validated ranking, and every weight in it is
traceable to a measured number in an E7.x ablation (cited at the constant). The uncertainty columns
travel with the point estimates on purpose — a projection without its band invites exactly the
over-reading this frame exists to prevent.

⭐ THE POSITION ASYMMETRY IS THE PRODUCT (E7.8, 2026-07-27)
----------------------------------------------------------
E7.8 asked whether FV adds projection lift on realized dynasty-fantasy value OVER an
age-relative-to-level + level + pedigree null, and the answer split by position:

  * **PITCHERS — FV COMPLEMENTS us.** Our MiLB performance read adds ~+0.014 over the null, FV a
    further ~+0.031 ON TOP of it (`pitcher/unconditional` and `pitcher/debut` both clear PBO<0.2 +
    DSR≥0.95). Corroborated by E7.3 vs E7.3p: pitcher K% translates at OOS corr 0.366 vs 0.637 for
    bats — the statistical record leaves more unexplained on the mound, which is the room a
    scouting grade fills. ⇒ **lead with FV; our line is the secondary read.**
  * **HITTERS — FV SUBSTITUTES for us.** Our read adds ~+0.047, FV only ~+0.015 more, and no batter
    stage cleared the deflated gates. ⇒ **lead with our MLE + age-relative-to-level; FV is
    CONFIRMATION.**

So the honest claim is *"we know WHEN to trust the scouts"* — not "we use FV" and not "we ignore
it". `FV_WEIGHT_BY_TYPE` is that verdict, and only that verdict, in numbers.

⚠️ KNOWN GAP — SB IS INVISIBLE TO US. Every E7.3/E7.3p target is a per-PA/per-TBF rate; stolen
bases are not in the substrate (the same limitation E7.8 states for its fantasy target). A
speed-first prospect is therefore SYSTEMATICALLY under-served by `mle_score`. Rather than bury
that, `speed_flag` surfaces it from the scouts' own future-speed grade — the one place the board
knows something we structurally cannot.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

__all__ = [
    "BOARD_LEVEL_RANK",
    "FV_WEIGHT_BY_TYPE",
    "MLE_METRIC_WEIGHTS",
    "ORG_TO_LEAGUE",
    "ProspectBoardError",
    "assemble_board",
    "assign_league",
    "attach_scores",
    "board_column_order",
    "normalize_level",
    "parse_grade",
    "select_mle_row_per_player",
    "split_sheets",
]


class ProspectBoardError(RuntimeError):
    """A board invariant failed — an unmapped org, a duplicated identity, a dead join.

    HARD stop rather than a NULL column: the operator drafts in a SINGLE-LEAGUE dynasty league, so
    a player whose `mlb_league` silently came back NULL is a player who silently vanishes from the
    only view that matters on draft day.
    """


# ── 1. The AL/NL map ─────────────────────────────────────────────────────────────────────────
#
# Dynasty leagues are single-league, so `mlb_league` is a REQUIRED filter column, not a nicety.
# Keys are THE BOARD's own org abbreviations (verified against the 2026 snapshot: all 30 present,
# FanGraphs-style — SFG/WSN/CHW/KCR/SDP/TBR, and `ATH` for the Athletics post-relocation).
ORG_TO_LEAGUE: dict[str, str] = {
    # American League
    "BAL": "AL", "BOS": "AL", "NYY": "AL", "TBR": "AL", "TOR": "AL",
    "CHW": "AL", "CLE": "AL", "DET": "AL", "KCR": "AL", "MIN": "AL",
    "ATH": "AL", "HOU": "AL", "LAA": "AL", "SEA": "AL", "TEX": "AL",
    # National League
    "ATL": "NL", "MIA": "NL", "NYM": "NL", "PHI": "NL", "WSN": "NL",
    "CHC": "NL", "CIN": "NL", "MIL": "NL", "PIT": "NL", "STL": "NL",
    "ARI": "NL", "COL": "NL", "LAD": "NL", "SDP": "NL", "SFG": "NL",
}

# Aliases for the same 30 clubs under other abbreviation conventions (Prospect Savant uses MLBAM's
# `MLB_AbbName`, which differs from FanGraphs on six clubs). Mapped rather than fuzzy-matched.
ORG_ALIASES: dict[str, str] = {
    "SF": "SFG", "SD": "SDP", "TB": "TBR", "KC": "KCR", "WSH": "WSN", "WAS": "WSN",
    "CWS": "CHW", "CHA": "CHW", "CHN": "CHC", "OAK": "ATH", "AZ": "ARI",
    "LA": "LAD", "ANA": "LAA", "NYA": "NYY", "NYN": "NYM", "SLN": "STL",
}


def assign_league(org: Any) -> str | None:
    """`org` → 'AL' / 'NL'. Unknown/blank orgs return None; the caller decides how loud to be."""
    if org is None or (isinstance(org, float) and np.isnan(org)):
        return None
    key = str(org).strip().upper()
    if not key:
        return None
    key = ORG_ALIASES.get(key, key)
    return ORG_TO_LEAGUE.get(key)


# ── 2. Levels ────────────────────────────────────────────────────────────────────────────────
#
# One ordering for two vocabularies: THE BOARD says `A+`/`AA`, the E7.3 MLE tables say
# `High-A`/`Double-A` (E7.1's `level_name`). Both normalize here so "highest level reached" means
# the same thing on either side of the join.
BOARD_LEVEL_RANK: dict[str, int] = {
    "DSL": 1, "CPX": 2, "ROK": 2, "A": 3, "A+": 4, "AA": 5, "AAA": 6, "MLB": 7,
}

_LEVEL_SYNONYMS: dict[str, str] = {
    "SINGLE-A": "A", "LOW-A": "A", "CLASS A": "A", "A-BALL": "A",
    "HIGH-A": "A+", "CLASS A ADVANCED": "A+",
    "DOUBLE-A": "AA", "CLASS AA": "AA",
    "TRIPLE-A": "AAA", "CLASS AAA": "AAA",
    "ROOKIE": "CPX", "COMPLEX": "CPX", "ACL": "CPX", "FCL": "CPX",
    "MAJORS": "MLB", "MAJOR LEAGUE BASEBALL": "MLB",
}


def normalize_level(level: Any) -> str | None:
    """Any level spelling → the canonical board vocabulary (`A`, `A+`, `AA`, `AAA`, `MLB`, …)."""
    if level is None or (isinstance(level, float) and np.isnan(level)):
        return None
    key = str(level).strip().upper()
    if not key:
        return None
    key = _LEVEL_SYNONYMS.get(key, key)
    return key if key in BOARD_LEVEL_RANK else None


def level_rank(level: Any) -> int:
    """Sortable level height; 0 for unknown so an unmapped level never wins a `max()`."""
    norm = normalize_level(level)
    return BOARD_LEVEL_RANK.get(norm, 0) if norm else 0


# ── 3. Player type ───────────────────────────────────────────────────────────────────────────
#
# Classified from THE BOARD's scouting POSITION, not from which MLE table happened to match: a
# converted prospect can carry a stale line in the other table, and the scouts' position is what
# the operator drafts against.
PITCHER_POSITIONS = frozenset({"SP", "RP", "RHP", "LHP", "SIRP", "MIRP", "P"})
TWO_WAY_POSITIONS = frozenset({"TWP"})


def classify_player_type(position: Any) -> str:
    if position is None or (isinstance(position, float) and np.isnan(position)):
        return "batter"          # THE BOARD's positionless rows are overwhelmingly bats
    pos = str(position).strip().upper()
    if pos in TWO_WAY_POSITIONS:
        return "two_way"
    if pos in PITCHER_POSITIONS:
        return "pitcher"
    return "batter"


# ── 4. Scouting grades ───────────────────────────────────────────────────────────────────────

_GRADE_RE = re.compile(r"(\d+(?:\.\d+)?)")

# THE BOARD's `raw_json` grade fields → the board's column names. Present/future grades arrive as
# `"40 / 60"`; the FUTURE grade (the second) is the one a dynasty owner drafts.
BATTER_GRADE_FIELDS = {"Hit": "grade_hit", "Game": "grade_game_pwr", "Raw": "grade_raw_pwr",
                       "Spd": "grade_spd", "Fld": "grade_fld"}
PITCHER_GRADE_FIELDS = {"FB": "grade_fb", "SL": "grade_sl", "CB": "grade_cb", "CH": "grade_ch",
                        "CT": "grade_ct", "SPL": "grade_spl", "CMD": "grade_cmd"}


def parse_grade(value: Any, which: str = "future") -> float | None:
    """`"40 / 60"` → 60.0 (future) or 40.0 (present). A single number returns itself.

    Blank strings are the board's "no grade published" and must come back None, never 0 — a 0 grade
    would read as *scouted and terrible* and would poison any downstream mean.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    nums = _GRADE_RE.findall(str(value))
    if not nums:
        return None
    return float(nums[-1] if which == "future" and len(nums) > 1 else nums[0])


def extract_board_json_fields(raw_json: Any) -> dict[str, Any]:
    """Pull the display fields THE BOARD publishes only inside `raw_json` (tool grades, handedness,
    the TLDR blurb). A malformed/absent blob yields empty values, never an exception — one bad row
    must not cost the operator his board on draft morning."""
    out: dict[str, Any] = {k: None for k in
                           list(BATTER_GRADE_FIELDS.values()) + list(PITCHER_GRADE_FIELDS.values())}
    out.update({"bats": None, "throws": None, "variance": None, "tldr": None, "summary": None})
    if not raw_json:
        return out
    try:
        blob = json.loads(raw_json) if isinstance(raw_json, str) else dict(raw_json)
    except (ValueError, TypeError):
        return out
    for src, dst in {**BATTER_GRADE_FIELDS, **PITCHER_GRADE_FIELDS}.items():
        out[dst] = parse_grade(blob.get(src))
    # `fSpd` is the board's numeric future-speed grade — the fallback when `Spd` is unparseable.
    if out["grade_spd"] is None:
        out["grade_spd"] = parse_grade(blob.get("fSpd"))
    out["bats"] = blob.get("Bats") or None
    out["throws"] = blob.get("Throws") or None
    out["variance"] = blob.get("Variance") or blob.get("cRisk") or None
    out["tldr"] = blob.get("TLDR") or None
    out["summary"] = blob.get("Ovr_Summary") or blob.get("Summary") or None
    return out


# ── 5. Picking ONE MLE line per player ───────────────────────────────────────────────────────

def select_mle_row_per_player(mle: pd.DataFrame, *, min_pa: float = 100.0,
                              key: str = "player_id") -> pd.DataFrame:
    """Collapse the per-(player, level) MLE table to ONE row per player.

    E7.3 emits a separate MLB-equivalent line for every level a player has a MiLB record at, and
    those lines are *career-at-level* aggregates (no season filter for un-graduated prospects — see
    `build_graduated_pairs`'s PROSPECTS note). For a draft board the right line is the HIGHEST level
    he has a real sample at: it is both the most recent and the least level-extrapolated.

    ⚠️ "Highest level" alone is the wrong rule — a prospect promoted to AAA three weeks ago has a
    20-PA AAA line and a 400-PA AA line, and the 20-PA line is noise wearing a higher level's
    clothes. So: **the highest level with `minor_pa ≥ min_pa`; if he clears that bar nowhere, the
    level where he has the most PA** (an honest "this is all we have" rather than a dropped player).
    `mle_pa` ships alongside so the sample is always visible next to the number.
    """
    if mle.empty:
        return mle.assign(mle_level=pd.Series(dtype="object"))
    df = mle.copy()
    df["_qualified"] = (df["minor_pa"].fillna(0) >= float(min_pa)).astype(int)
    # Level height only breaks ties AMONG qualified lines. Zeroed on the unqualified ones so that
    # when a player clears the bar nowhere the fallback is genuinely "most PA" — otherwise the
    # 25-PA promotion line would win the fallback too, which is the exact bug this rule exists for.
    df["_level_key"] = df["level"].map(level_rank) * df["_qualified"]
    # sort so the winner per player is the LAST row: qualified first, then level, then sample size
    df = df.sort_values([key, "_qualified", "_level_key", "minor_pa"],
                        ascending=[True, True, True, True], na_position="first")
    picked = df.groupby(key, as_index=False).tail(1).copy()
    picked = picked.rename(columns={"level": "mle_level", "minor_pa": "mle_pa"})
    return picked.drop(columns=["_level_key", "_qualified"])


# ── 6. Scoring ───────────────────────────────────────────────────────────────────────────────
#
# ⭐ EVERY WEIGHT BELOW IS A MEASURED NUMBER, NOT A TASTE CALL.
#
# Per-metric weights are PROPORTIONAL to that metric's measured out-of-sample translation
# correlation in its own bake-off, so a metric that translates poorly cannot quietly dominate the
# composite. Metrics that came back NO-SIGNAL are absent entirely — including them at a small
# weight would be laundering a null into a ranking.
#
#   batters (E7.3, `e7_3_milb_mle.md`):  k_pct 0.637 ✅ · bb_pct 0.491 ✅ · iso 0.429 🟡
#                                        woba 0.220 ❌ no-signal → EXCLUDED (never resurrect it)
#   pitchers (E7.3p, `e7_3p_milb_mle_pitchers.md`):
#                                        gb_pct 0.551 ✅ · bb_pct 0.367 🟡 · k_pct 0.366 🟡
#                                        hr_rate 0.094 (DSR 0.130) + xwoba_against 0.147 ❌ → EXCLUDED
#
# `higher_is_better` is the fantasy-value direction, which INVERTS between the two sides: a batter
# wants a LOW K%, a pitcher wants a HIGH one.
MLE_METRIC_WEIGHTS: dict[str, dict[str, tuple[float, bool]]] = {
    # metric column suffix -> (oos translation corr = the weight, higher_is_better)
    "batter": {"mle_k_pct": (0.637, False), "mle_bb_pct": (0.491, True), "mle_iso": (0.429, True)},
    "pitcher": {"mle_p_gb_pct": (0.551, True), "mle_p_bb_pct": (0.367, False),
                "mle_p_k_pct": (0.366, True)},
}

# How much of the headline ordering the SCOUTS get, by position — the E7.8 verdict, in numbers.
# Pitchers: FV COMPLEMENTS our line (it adds +0.031 on top of our +0.014, gates cleared) ⇒ it leads.
# Hitters:  FV SUBSTITUTES for our line (+0.015 on top of our +0.047, no stage cleared) ⇒ it confirms.
FV_WEIGHT_BY_TYPE: dict[str, float] = {"batter": 0.35, "pitcher": 0.70, "two_way": 0.50}

# Within our own view, how much is the translated line vs age-relative-to-level. Age-rel-to-level is
# part of E7.8's NULL — it is the single most reliable prospect signal there is, and it costs nothing
# to carry, so it gets a real (minority) share rather than being left to the eye.
AGE_WEIGHT_IN_MODEL_SCORE = 0.25

# Future-speed grade at or above this is a "the MLE cannot see this" flag (see the module docstring:
# SB is absent from every E7.3/E7.3p target). 60 = plus on the 20–80 scouting scale.
SPEED_FLAG_GRADE = 60.0

# |disagreement| in percentile points before we call it a disagreement rather than noise. A board
# percentile is a rank statistic on ~1,300 players; anything under ~15 points is jitter.
DISAGREEMENT_THRESHOLD = 15.0


def _disagreement_residual(model_score: pd.Series, fv_pctile: pd.Series) -> pd.Series:
    """Our score MINUS what our score usually is at that FV — not the raw gap between them.

    🚨 THE RAW GAP IS A BROKEN METRIC, and it looks fine until you read the output. Two rankings
    that correlate at anything below 1.0 regress toward each other at the extremes, so
    `model_score − fv_pctile` labels essentially the ENTIRE top of the board 'SCOUTS HIGHER' and
    the entire bottom 'WE'RE HIGHER' — it is a re-encoding of FV rank, not a disagreement. (Caught
    on the first real 1,286-player run: 10 of the top 12 were flagged, including players our own
    line scored in the 95th percentile.)

    Removing the fitted linear relationship first makes the residual mean-zero at every FV, so a
    flag means *"unusual for a player with this grade"* — which is the thing that is actually worth
    a second look on draft day. Same class as the repo's selection-metric hygiene rule: sanity-check
    the metric against what it mechanically must produce before trusting what it says.
    """
    ok = model_score.notna() & fv_pctile.notna()
    if int(ok.sum()) < 3 or fv_pctile[ok].nunique() < 2:
        return (model_score - fv_pctile).round(1)      # too few points to fit — the raw gap is all
    slope, intercept = np.polyfit(fv_pctile[ok].astype(float), model_score[ok].astype(float), 1)
    expected = intercept + slope * fv_pctile
    return (model_score - expected).round(1)


def _pctile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Percentile (0–100) among the NON-NULL values, NULLs preserved.

    Rank-based on purpose: the MLE metrics are on wildly different scales (ISO ~0.09 vs K% ~0.22)
    and a z-score composite would hand the widest-tailed metric the ranking. Percentiles also make
    `disagreement` (ours minus theirs) a directly readable "how many places apart are they".
    """
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index, dtype="float64")
    ranked = series.rank(pct=True, na_option="keep")
    if not higher_is_better:
        ranked = 1.0 - ranked
    return (ranked * 100.0).astype("float64")


def _weighted_score(df: pd.DataFrame, spec: dict[str, tuple[float, bool]]) -> pd.DataFrame:
    """Weighted mean of the available metric percentiles, RENORMALIZED over what is present.

    A player missing ISO must not be scored as if his ISO were terrible — he is scored on the
    metrics he has, and `mle_coverage` reports how much of the intended weight that was, so a
    thin-coverage score is visible as thin rather than passing as complete.
    """
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for col, (weight, higher) in spec.items():
        if col not in df.columns:
            continue
        pct = _pctile(df[col], higher_is_better=higher)
        present = pct.notna()
        num = num.add(pct.fillna(0.0) * weight * present, fill_value=0.0)
        den = den.add(weight * present, fill_value=0.0)
    total_weight = sum(w for w, _ in spec.values()) or 1.0
    score = np.where(den > 0, num / den.replace(0, np.nan), np.nan)
    return pd.DataFrame({"score": score, "coverage": (den / total_weight).round(3)}, index=df.index)


def attach_scores(board: pd.DataFrame) -> pd.DataFrame:
    """Add the percentile views + the display blend. Scores are computed WITHIN player type.

    Batters and pitchers are ranked against their own kind because the two composites are built
    from different metrics with different translation strengths — a cross-type percentile would be
    comparing a GB% rank to an ISO rank and calling the result an ordering.
    """
    df = board.copy()
    for col in ("mle_score", "mle_coverage", "age_score", "fv_pctile", "model_score",
                "blend_score", "disagreement"):
        df[col] = np.nan

    # age relative to level: how much younger than the board's typical player AT HIS LEVEL. The
    # median is taken over the whole board (both types) at that level — level age curves are a
    # property of the level, not of the position.
    level_median_age = df.groupby(df["level"].map(normalize_level))["age"].transform("median")
    df["age_vs_level"] = (df["age"] - level_median_age).round(2)

    for ptype, spec in MLE_METRIC_WEIGHTS.items():
        mask = df["player_type"] == ptype
        if ptype == "batter":                       # two-way players ride the batter board
            mask = mask | (df["player_type"] == "two_way")
        if not mask.any():
            continue
        sub = df.loc[mask]
        scored = _weighted_score(sub, spec)
        df.loc[mask, "mle_score"] = scored["score"].round(1)
        df.loc[mask, "mle_coverage"] = scored["coverage"]
        df.loc[mask, "age_score"] = _pctile(sub["age_vs_level"], higher_is_better=False).round(1)
        df.loc[mask, "fv_pctile"] = _pctile(sub["fv"], higher_is_better=True).round(1)

    # OUR view = the translated line + age-relative-to-level (E7.8's null term). Where we have no
    # MLE line at all, our view degrades to age-rel-to-level rather than going blank — a 19-year-old
    # in High-A is a real read even with no projection attached.
    model = (df["mle_score"] * (1 - AGE_WEIGHT_IN_MODEL_SCORE)
             + df["age_score"] * AGE_WEIGHT_IN_MODEL_SCORE)
    df["model_score"] = model.where(df["mle_score"].notna() & df["age_score"].notna(),
                                    df["mle_score"].fillna(df["age_score"])).round(1)

    fv_w = df["player_type"].map(FV_WEIGHT_BY_TYPE).fillna(0.5)
    blend = fv_w * df["fv_pctile"] + (1 - fv_w) * df["model_score"]
    # Either side missing ⇒ fall back to the side we have, so a player is never ranked last merely
    # for being un-projected (the FV-only rows the story requires we keep, not drop).
    df["blend_score"] = blend.where(df["fv_pctile"].notna() & df["model_score"].notna(),
                                    df["fv_pctile"].fillna(df["model_score"])).round(1)

    # Disagreement is specifically OUR TRANSLATED LINE vs the grade, and it is a RESIDUAL (see
    # `_disagreement_residual` — the raw gap is a broken metric). Fitted within player type: the
    # FV↔our-score relationship is genuinely different for bats and arms (that asymmetry is E7.8's
    # whole finding), so one pooled fit would smear the two together. A player with no MLE at all
    # still gets a `model_score` (it degrades to age-rel-to-level, so he stays rankable) — but
    # calling that a disagreement with the scouts would be reading a projection we never made.
    df["disagreement"] = np.nan
    for ptype in df["player_type"].dropna().unique():
        mask = (df["player_type"] == ptype) & df["mle_score"].notna()
        if not mask.any():
            continue
        df.loc[mask, "disagreement"] = _disagreement_residual(
            df.loc[mask, "model_score"], df.loc[mask, "fv_pctile"])
    df["disagreement_label"] = np.select(
        [df["disagreement"] >= DISAGREEMENT_THRESHOLD,
         df["disagreement"] <= -DISAGREEMENT_THRESHOLD],
        ["WE'RE HIGHER", "SCOUTS HIGHER"],
        default="agree",
    )
    df.loc[df["disagreement"].isna(), "disagreement_label"] = "n/a (no MLE line)"

    # 231 of the 1,286 current-board prospects are listed AT MLB — graduated but still carrying a
    # prospect grade. Most minor-league dynasty drafts do not make those players draftable, so the
    # board says so explicitly rather than leaving the operator to infer it from the level column.
    df["in_majors"] = np.where(df["level"].map(normalize_level) == "MLB", "MLB — check eligibility",
                               "")

    df["speed_flag"] = np.where(
        df["grade_spd"].fillna(0) >= SPEED_FLAG_GRADE,
        "SPEED — SB not in our MLE", "")
    return df


# ── 7. Assembly ──────────────────────────────────────────────────────────────────────────────

def assemble_board(board: pd.DataFrame, xref: pd.DataFrame, mle_bat: pd.DataFrame,
                   mle_pit: pd.DataFrame, savant: pd.DataFrame | None = None, *,
                   min_pa: float = 100.0, strict_league: bool = True) -> tuple[pd.DataFrame, dict]:
    """Join the three views into the board + return the match-rate report the AC requires.

    `board` is the CURRENT BOARD snapshot (already deduped by the caller via
    `player_xref.register_board` — see that module's landmines 1–2: this table has exactly one valid
    reader, and a parquet glob fabricates the match rate). `xref` is E7.4's `dim_player_xref`,
    used ONLY as the `fg_minor_id → mlbam_id` bridge; the two-hop it encapsulates is not re-derived.

    ⚠️ A missing MLE is EXPECTED, not a defect: complex/DSL/just-drafted prospects have an identity
    but no MiLB-PA projection. Those rows stay on the board FV-only. Residual unmatched identities
    stay too — no fuzzy name leg (E7.4 found name equality yields false positives).
    """
    rep: dict[str, Any] = {}
    b = board.copy()
    rep["board_rows"] = int(len(b))
    if b["fg_minor_id"].duplicated().any():
        raise ProspectBoardError(
            f"the board snapshot has {int(b['fg_minor_id'].duplicated().sum())} duplicate "
            "fg_minor_id values — it was not deduped to one snapshot. Every downstream count "
            "would be inflated (the tombstoned-glob failure mode, E7.4 landmine 2)."
        )

    # ── identity bridge (E7.4) ───────────────────────────────────────────────────────────────
    bridge = (xref.loc[xref["fg_minor_id"].notna() & xref["mlbam_id"].notna(),
                       ["fg_minor_id", "mlbam_id"]]
              .drop_duplicates(subset=["fg_minor_id"]))
    b = b.merge(bridge, on="fg_minor_id", how="left", suffixes=("", "_xref"))
    if "mlbam_id_xref" in b.columns:      # THE BOARD ships an all-NULL mlbam_id column of its own
        b["mlbam_id"] = b["mlbam_id_xref"]
        b = b.drop(columns=["mlbam_id_xref"])
    rep["matched_mlbam"] = int(b["mlbam_id"].notna().sum())
    rep["matched_mlbam_rate"] = round(rep["matched_mlbam"] / max(len(b), 1), 4)

    # ── board display attributes ─────────────────────────────────────────────────────────────
    extracted = pd.DataFrame(
        [extract_board_json_fields(v) for v in b.get("raw_json", pd.Series([None] * len(b)))],
        index=b.index)
    b = pd.concat([b.drop(columns=[c for c in extracted.columns if c in b.columns]), extracted],
                  axis=1)
    b["scouting_note"] = [_scouting_note(t, s) for t, s in
                          zip(b.get("tldr", pd.Series([None] * len(b))),
                              b.get("summary", pd.Series([None] * len(b))))]
    b["player_type"] = b["position"].map(classify_player_type)
    b["mlb_league"] = b["org"].map(assign_league)

    unknown = sorted({str(o) for o in b.loc[b["mlb_league"].isna(), "org"].dropna().unique()})
    rep["unmapped_orgs"] = unknown
    if unknown and strict_league:
        raise ProspectBoardError(
            f"org(s) {unknown} have no AL/NL mapping. `mlb_league` is a REQUIRED filter for a "
            "single-league dynasty draft — an unmapped org silently drops those players from the "
            "only view the operator uses. Add them to ORG_TO_LEAGUE (or ORG_ALIASES) and re-run."
        )

    # ── our MLE line ─────────────────────────────────────────────────────────────────────────
    bat = select_mle_row_per_player(mle_bat, min_pa=min_pa)
    bat_cols = {"mle_level": "mle_level", "mle_pa": "mle_pa"}
    for m in ("k_pct", "bb_pct", "iso"):
        bat_cols[f"mle_{m}"] = f"mle_{m}"
        bat_cols[f"mle_{m}_sd"] = f"mle_{m}_sd"
    bat = bat[[c for c in ["player_id", *bat_cols] if c in bat.columns]]

    pit = select_mle_row_per_player(mle_pit, min_pa=min_pa)
    pit_rename = {"mle_level": "mle_p_level", "mle_pa": "mle_p_tbf"}
    for m in ("k_pct", "bb_pct", "gb_pct"):
        pit_rename[f"mle_{m}"] = f"mle_p_{m}"
        pit_rename[f"mle_{m}_sd"] = f"mle_p_{m}_sd"
    pit = (pit[[c for c in ["player_id", *pit_rename] if c in pit.columns]]
           .rename(columns=pit_rename))

    b = b.merge(bat, left_on="mlbam_id", right_on="player_id", how="left") \
         .drop(columns=["player_id"], errors="ignore")
    b = b.merge(pit, left_on="mlbam_id", right_on="player_id", how="left") \
         .drop(columns=["player_id"], errors="ignore")

    is_bat = b["player_type"].isin(("batter", "two_way"))
    rep["with_batter_mle"] = int((is_bat & b.get("mle_k_pct", pd.Series(np.nan, index=b.index))
                                  .notna()).sum())
    rep["with_pitcher_mle"] = int(((~is_bat) & b.get("mle_p_k_pct", pd.Series(np.nan, index=b.index))
                                   .notna()).sum())
    rep["with_any_mle"] = rep["with_batter_mle"] + rep["with_pitcher_mle"]
    rep["with_any_mle_rate"] = round(rep["with_any_mle"] / max(len(b), 1), 4)

    # ── Prospect Savant (THEIR numbers, always labelled) ─────────────────────────────────────
    if savant is not None and not savant.empty:
        sav = savant.drop_duplicates(subset=["fg_minor_id"])
        keep = ["fg_minor_id"] + [c for c in sav.columns if c.startswith("ps_")]
        b = b.merge(sav[keep], on="fg_minor_id", how="left")
        rep["with_prospect_savant"] = int(b["ps_level"].notna().sum()) if "ps_level" in b else 0
        # ⭐ A FREE, INDEPENDENT AUDIT OF THE E7.4 BRIDGE. Prospect Savant publishes BOTH ids, and
        # we joined on `fg_minor_id` alone — so their MLBAM id and the one our xref derived through
        # FanGraphs' leaderboards are two independently-sourced answers to "who is this?". Any
        # mismatch is a wrong identity that every other check on this board would pass over.
        if "ps_mlbam_id" in b.columns:
            both = b[b["ps_mlbam_id"].notna() & b["mlbam_id"].notna()]
            agree = int((both["ps_mlbam_id"].astype(str) == both["mlbam_id"].astype(str)).sum())
            rep["savant_id_crosscheck"] = {
                "comparable": int(len(both)), "agree": agree,
                "rate": round(agree / max(len(both), 1), 4),
                "disagreeing_players": both.loc[
                    both["ps_mlbam_id"].astype(str) != both["mlbam_id"].astype(str),
                    ["player_name", "fg_minor_id", "mlbam_id", "ps_mlbam_id"]
                ].to_dict("records")[:20],
            }
    else:
        rep["with_prospect_savant"] = 0

    b = attach_scores(b)
    # Default ordering, per the AC: the scouts' FV first, our line as the tiebreak.
    b = b.sort_values(["fv", "model_score", "blend_score"],
                      ascending=[False, False, False], na_position="last").reset_index(drop=True)
    b.insert(0, "board_rank", np.arange(1, len(b) + 1))
    return b[board_column_order(b)], rep


# Source columns that have already been unpacked into real columns, or that are plumbing. Dropped
# from the EXPORT only. `raw_json` alone is ~5 KB of vendor blob per player — carrying it made the
# CSV 7 MB and pushed the readable columns off the right-hand edge of a spreadsheet.
EXPORT_DROP_COLUMNS = frozenset({
    "raw_json", "board_slug", "ingested_at_utc", "fv_raw", "fg_player_id", "ps_player_type",
    "summary",
})

# THE BOARD's full scouting report averages ~1,400 characters — 1.7 MB across the board, and a row
# height that makes a spreadsheet unreadable. The one-line TLDR is published for only a fraction of
# players, so the export carries a SHORT note: the TLDR when there is one, otherwise the opening of
# the report. The full text stays on FanGraphs, where it reads properly.
SCOUTING_NOTE_CHARS = 320


def _scouting_note(tldr: Any, summary: Any) -> str | None:
    for text in (tldr, summary):
        if text is None or (isinstance(text, float) and np.isnan(text)):
            continue
        s = str(text).strip()
        if not s:
            continue
        return s if len(s) <= SCOUTING_NOTE_CHARS else s[:SCOUTING_NOTE_CHARS].rsplit(" ", 1)[0] + "…"
    return None


def board_column_order(df: pd.DataFrame) -> list[str]:
    """Column order for the export: WHO first, then the three views side by side, then the blurb.

    Deliberately readable-left-to-right on draft day — identity, the scouts, us, the disagreement,
    then the detail. Any column not named here is appended (so a new field is never silently lost).
    """
    order = [
        # who
        "board_rank", "player_name", "org", "mlb_league", "position", "player_type", "level",
        "age", "age_vs_level", "eta", "bats", "throws",
        # the scouts (FanGraphs)
        "fv", "risk", "variance", "overall_rank", "org_rank",
        "fantasy_dynasty_rank", "fantasy_redraft_rank",
        # the three scores + where they disagree
        "fv_pctile", "mle_score", "age_score", "model_score", "blend_score",
        "disagreement", "disagreement_label", "speed_flag", "in_majors",
        # our line — batters
        "mle_level", "mle_pa", "mle_k_pct", "mle_k_pct_sd", "mle_bb_pct", "mle_bb_pct_sd",
        "mle_iso", "mle_iso_sd",
        # our line — pitchers
        "mle_p_level", "mle_p_tbf", "mle_p_k_pct", "mle_p_k_pct_sd", "mle_p_bb_pct",
        "mle_p_bb_pct_sd", "mle_p_gb_pct", "mle_p_gb_pct_sd", "mle_coverage",
        # Prospect Savant (THEIR expected stats)
        "ps_level", "ps_pa", "ps_xwoba", "ps_xwoba_pctile", "ps_ev",
        "ps_barrel_pct", "ps_hardhit_pct", "ps_chase_pct", "ps_whiff_pct", "ps_k_pct",
        "ps_bb_pct", "ps_gb_pct", "ps_velo", "ps_xfip",
        # scouting grades
        "grade_hit", "grade_game_pwr", "grade_raw_pwr", "grade_spd", "grade_fld",
        "grade_fb", "grade_sl", "grade_cb", "grade_ch", "grade_ct", "grade_spl", "grade_cmd",
        # ids + provenance + the blurb
        "mlbam_id", "fg_minor_id", "board_season", "board_as_of_date", "scouting_note", "tldr",
    ]
    present = [c for c in order if c in df.columns]
    return present + [c for c in df.columns
                      if c not in present and c not in EXPORT_DROP_COLUMNS]


def split_sheets(board: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The export's tabs. AL/NL are first-class because the operator's league is single-league.

    `Disagreements` is the differentiated view — the players where our translated line and the
    scouts' grade rank differently — sorted by the size of the gap in both directions.
    """
    sheets: dict[str, pd.DataFrame] = {"All": board}
    for lg in ("AL", "NL"):
        sheets[lg] = board[board["mlb_league"] == lg].reset_index(drop=True)
    sheets["Hitters"] = board[board["player_type"].isin(("batter", "two_way"))].reset_index(drop=True)
    sheets["Pitchers"] = board[board["player_type"] == "pitcher"].reset_index(drop=True)
    if "in_majors" in board.columns:
        # The likely draft pool: prospect grades minus the players already in the majors.
        sheets["Minors only"] = board[board["in_majors"] == ""].reset_index(drop=True)
    if "blend_score" in board.columns:
        sheets["By blend"] = board.sort_values("blend_score", ascending=False,
                                               na_position="last").reset_index(drop=True)
    disagree = board[board["disagreement"].abs() >= DISAGREEMENT_THRESHOLD]
    sheets["Disagreements"] = disagree.sort_values(
        "disagreement", ascending=False, na_position="last").reset_index(drop=True)
    return sheets


def format_report(rep: dict, extra: Iterable[str] = ()) -> str:
    """The join match-rate block the AC requires — printed AND written beside the export."""
    lines = ["", "──────── E8.0 PROSPECT BOARD — JOIN MATCH-RATE REPORT ────────",
             f"  current board snapshot     : {rep.get('board_rows', 0):,} prospects",
             f"  → resolved to an MLBAM id  : {rep.get('matched_mlbam', 0):,} "
             f"({rep.get('matched_mlbam_rate', 0):.1%})   [E7.4 dim_player_xref; no fuzzy leg]",
             f"  → with OUR MLE line        : {rep.get('with_any_mle', 0):,} "
             f"({rep.get('with_any_mle_rate', 0):.1%})   "
             f"[bats {rep.get('with_batter_mle', 0):,} / arms {rep.get('with_pitcher_mle', 0):,}]",
             f"  → with Prospect Savant     : {rep.get('with_prospect_savant', 0):,}   "
             "[THEIR expected stats, labelled ps_*]",
             "",
             "  ⚠️ A missing MLE is EXPECTED, not a defect — complex/DSL/just-drafted prospects",
             "     have an identity but no MiLB-PA projection. Those rows stay on the board FV-only;",
             "     nothing is silently dropped.",
             ]
    cross = rep.get("savant_id_crosscheck")
    if cross and cross.get("comparable"):
        lines += ["",
                  f"  ⭐ IDENTITY CROSS-CHECK — Prospect Savant's own MLBAM id vs the one E7.4's",
                  f"     xref derived independently: {cross['agree']:,}/{cross['comparable']:,} "
                  f"agree ({cross['rate']:.2%}). We joined on fg_minor_id ALONE, so this is a",
                  "     third-party audit of the bridge, not a restatement of it."]
        for bad in cross.get("disagreeing_players", []):
            lines.append(f"     ⛔ MISMATCH {bad['player_name']}: ours={bad['mlbam_id']} "
                         f"theirs={bad['ps_mlbam_id']}")
    if rep.get("unmapped_orgs"):
        lines.append(f"  ⛔ UNMAPPED ORGS: {rep['unmapped_orgs']}")
    lines += list(extra)
    lines.append("──────────────────────────────────────────────────────────────")
    return "\n".join(lines)
