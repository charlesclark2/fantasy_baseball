"""fv_translation.py — MLB Edge-E7.8: does a FanGraphs prospect grade translate to MLB fantasy value?

THE QUESTION (and why it gates E8)
----------------------------------
Before the Dynasty board (E8) leans on FanGraphs' Future Value / rank as a HEADLINE signal, prove it
is signal and not marketing: **does The Board's as-of FV/rank add incremental projection lift over an
age-relative-to-level + level + pedigree null?** An honest answer either way is product-defensible —
and, since the operator's 2026-08-03 AL-only prospect draft picks current minor leaguers, it is a
direct DRAFT input: *trust FV more*, or *lean on our own MLE + age-relative-to-level*.

A CLEAN NULL IS A VALID, HIGH-VALUE ANSWER. The graduated-prospect cohort is small (a handful of board
seasons), so the deflation is NOISY by construction — the NF1.4 rookie small-N situation. Do not force
a survivor; read a TIED-FIELD high PBO as the null (the E2.1-r reading: high PBO + TIGHT config spread
= "nothing robustly separates", which is exactly what a trustworthy null looks like; high PBO + WIDE
spread = overfitting).

⚠️ THE TWO CONFOUNDS THAT MANUFACTURE A MIRAGE (both pre-registered and modelled, not hand-waved)
--------------------------------------------------------------------------------------------------
1. **SURVIVORSHIP.** You only observe an MLB line for prospects who REACHED MLB — and a highly-ranked
   prospect gets more runway, so a "graduates-only" fit credits FV for the org's own belief in him.
   The cure is structural, not a correction factor: the DYNASTY-FANTASY outcome is defined on the FULL
   board cohort, where a prospect who never reaches MLB scores **ZERO — a realized outcome, not
   missing data**. The study then reports THREE stages that separate the channels:
     * `debut`         — P(reach MLB with real playing time inside the window). The SELECTION model.
     * `conditional`   — fantasy value GIVEN a debut (graduates only). The survivorship-exposed stage;
                         reported precisely so the inflation is visible rather than baked in.
     * `unconditional` — fantasy value over the WHOLE cohort, zeros included. ⭐ The draft-relevant
                         stage: it is the product of the two channels and carries no survivorship
                         selection at all.
2. **LEVEL CONFOUND.** FV correlates with level and level correlates with proximity-to-MLB, so a naive
   fit credits FV for what level already told you. Level (one-hot) and **age-relative-to-level**
   (age minus the TRAIN-fold mean age at that level — computed in-fold, never peeking at the eval
   cohort) are in the NULL arm. FV must beat that null, not the raw population.

THE PRE-REGISTERED CONTRAST (this, not "the best config wins")
--------------------------------------------------------------
The headline test per (player_type, stage) is a FIXED PAIR — same learner, one feature block added:

        null + perf + FV      vs      null + perf          →  Δ per fold  →  one-sided paired p

with a second, secondary pair `null + FV` vs `null` (is FV informative AT ALL, before our own
performance read). Both are fixed in advance, so the headline number carries no selection bias. The
WIDER search (every feature set × FV transform × learner) is run too and reported with PBO / config
spread / DSR — that answers the different question "could a cherry-picked FV configuration look good
by chance?".

  * NULL arm (`null`)  — level one-hot, age, **age-relative-to-level**, pro experience, prior MLB
    exposure. ⚠️ **DEVIATION FROM THE STORY'S NULL, STATED HONESTLY:** the story pre-registered
    *draft round / bonus* as the pedigree term. **MLB draft round/bonus is NOT in the lake** (no
    StatsAPI draft ingest exists — a `/api/v1/draft/{year}` ingest is a real follow-up story). The
    substituted, genuinely-available pedigree proxies are `pro_experience_years` (seasons since the
    player's first professional game) and `level` reached for that experience — an organisation
    promotes its pedigree aggressively, so level-for-age-for-experience is the observable shadow of
    draft pedigree. The gap is named in the report; it makes the null WEAKER than intended, which
    biases the study TOWARD finding FV lift — so a NULL result is, if anything, conservative.
  * PERF arm (`perf`)  — our own read: the player's MiLB rate line **as of the board date**.
    ⚠️ We deliberately do NOT feed E7.3/E7.3p's `mle_projections`: their feature window is
    pre-DEBUT, not pre-BOARD, so a graduate's MLE embeds minor-league games played AFTER the board
    snapshot — a leak straight into the outcome window. The as-of raw line is the leakage-safe
    stand-in, and E7.3 showed the translation is essentially monotone in the minor rate, so it
    carries the same information the MLE would.
  * FV arm (`fv`)      — FV (linear or grade-bucket), risk, ETA lead (`eta − board season`).
  * RANK arm (`rank`)  — overall / org / FanGraphs-Dynasty rank, as `1/log2(1+rank)` scores plus an
    `is_ranked` flag (most of the board carries an org rank; only the top tier carries an overall rank,
    so "unranked" is a real state, never an imputed number).

CV — LEAVE-ONE-BOARD-COHORT-OUT, EXPANDING, PLAYER-PURGED
---------------------------------------------------------
Fold S trains on board cohorts strictly BEFORE S and scores cohort S. **Player purge is load-bearing:**
the same prospect appears on 3–5 consecutive boards and his outcome windows OVERLAP, so any player in
the eval cohort is dropped from the training fold — without it a "prediction" is partly a memory of the
same person's realised outcome.

⚠️ **What this CV does and does not claim** (stated in the report, not buried): the expanding-cohort
design is out-of-sample in the PLAYER and in the COHORT, but it is not strictly real-time — a model
tested on the 2021 board trains on 2018–2020 boards whose 3-season outcome windows had not fully closed
by mid-2021. With only ~5 usable board cohorts, the strictly-real-time variant leaves ≤2 folds, which
cannot support PBO at all. `strict_realtime=True` runs it anyway as a reported sensitivity when the
folds exist. This is the NF1.4 small-N posture: state the limit, report both, force nothing.

SELECTION-METRIC HYGIENE (CLAUDE.md §0.5)
-----------------------------------------
Every stage's metric is RANK-based (Spearman ρ within cohort; AUC for the binary debut stage) because
the consumer is a DRAFT BOARD — ordering is the product, not calibrated point values. Both metrics have
an exact oracle ceiling (ρ = 1, AUC = 1), so `oracle_is_the_scoring_floor()` asserts no candidate ever
exceeds the realized-outcome oracle. A candidate beating the oracle is mathematically impossible and is
the tell that the metric is inverted (the E2.1-r lesson).

HONEST FRAMING: `best_alpha = 0`. This is a projection-validation study, never a market claim.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

STUDY_VERSION = "e7.8-v1"

# ── Deflation gates (the program's standing bars) ────────────────────────────────────────────────
PBO_MAX = 0.20
DSR_MIN = 0.95
FDR_Q = 0.10

# The three evaluation stages (see the survivorship section of the module docstring).
STAGES = ("debut", "conditional", "unconditional")

# ── The fantasy outcome ──────────────────────────────────────────────────────────────────────────
# A points-league core, computed from the columns the Statcast-derived MLB marts actually expose at
# game grain. Weights are constants (not tuned — tuning the TARGET would be circular).
#
# BATTER:  1.3·(H − HR) + 4·HR + 1·BB − 0.5·K
#   `1.3` is the population mean TOTAL BASES per NON-HOME-RUN hit (≈ (63·1 + 20·2 + 2·3)/85 for the
#   league's 1B/2B/3B mix) — it recovers total bases IN EXPECTATION without needing the 2B/3B split,
#   which `mart_batter_rolling_stats` does not carry at game grain. ⚠️ R / RBI / SB are NOT in the
#   Statcast substrate: R and RBI are lineup-context terms that track playing time and production
#   (already both in the target), but **SB is a genuinely distinct speed skill this target cannot
#   see** — a stated limitation, and the reason a speed-first prospect is under-valued here.
# PITCHER: 3·IP + 1·K − 1·H − 1·BB − 3·HR,  with IP = (BF − H − BB)/3
#   Innings are reconstructed from batters faced minus baserunners (ignores HBP / double plays /
#   caught stealing — a small, non-differential approximation). W / SV / ER are unavailable; HR
#   carries the earned-run weight as the proxy. Stated in the report.
BAT_FP_WEIGHTS: dict[str, float] = {"hit_non_hr": 1.3, "hr": 4.0, "bb": 1.0, "k": -0.5}
PIT_FP_WEIGHTS: dict[str, float] = {"ip": 3.0, "k": 1.0, "hit": -1.0, "bb": -1.0, "hr": -3.0}

# A "debut" that counts: enough playing time that the prospect actually returned fantasy value.
MIN_DEBUT_PA = 100     # batters, over the whole outcome window
MIN_DEBUT_BF = 150     # pitchers (batters faced), over the whole outcome window

# The as-of MiLB line must be this thick before we read a rate off it (mirrors E7.3's floor).
MIN_MINOR_PA = 100

# ── Player-type classification ───────────────────────────────────────────────────────────────────
#
# 🚨 **FANGRAPHS CHANGED THIS VOCABULARY MID-PANEL** (found on the first real run, 2026-07-27).
# The 2018–2020 boards label arms `RHP` / `LHP`; from 2021 they use ROLE labels — `SP` (starter),
# `SIRP` (single-inning reliever), `MIRP` (multi-inning reliever). A regex written against the old
# vocabulary silently typed **666 relievers as BATTERS** (319 in 2021, 346 in 2022), where they were
# scored on the batter formula, recorded ~0 fantasy points and a 0.0 debut rate, and entered the two
# most recent eval folds as fake "never arrived" prospects — while the pitcher cohort for those same
# folds collapsed to an SP-only (non-random, higher-arrival) subset. That is a verdict-flipping
# contamination that no CV or deflation gate can see, because the LABELS are wrong before any model
# runs.
#
# The cure is not a longer regex. Classification now cascades to the OBJECTIVE evidence:
#   1. the position string, when every token is unambiguously one role;
#   2. otherwise the MiLB game logs — did he actually pitch more games than he batted? (this also
#      resolves the genuine two-way slash positions FanGraphs publishes: `SIRP/SS`, `1B/LHP`, `SS/RHP`);
#   3. otherwise a stated default, COUNTED in the coverage report.
# and a tripwire RAISES when a season's batters are full of pitcher-majority game logs, so the next
# vocabulary change is a loud build failure rather than a quiet mirage.
PITCHER_TOKENS = frozenset({
    "P", "RHP", "LHP", "SP", "RP",           # 2018–2020 vocabulary (+ generic)
    "SIRP", "MIRP", "RHSP", "LHSP", "RHRP", "LHRP",  # 2021+ ROLE vocabulary
})
BATTER_TOKENS = frozenset({
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH",
    "UTIL", "INF", "MIF", "CI", "MI", "IF", "4C",
})


def classify_position(pos: object) -> str | None:
    """`'pitcher'` / `'batter'` from a board position, or **None when the string cannot decide**.

    None is returned for a genuine two-way slash position (`SIRP/SS`) AND for any token this function
    does not recognise — both hand the decision to the game logs. Returning None rather than guessing
    is the whole point: an unrecognised token that silently defaulted to "batter" is exactly how the
    2021 vocabulary change slipped through.
    """
    if pos is None or (isinstance(pos, float) and np.isnan(pos)):
        return None
    tokens = [t.strip().upper() for t in str(pos).split("/") if t.strip()]
    if not tokens:
        return None
    if all(t in PITCHER_TOKENS for t in tokens):
        return "pitcher"
    if all(t in BATTER_TOKENS for t in tokens):
        return "batter"
    return None


def unknown_position_tokens(positions) -> set[str]:
    """Position tokens in NEITHER vocabulary — surfaced in the coverage report so a future FanGraphs
    relabel is visible on the run that introduces it, not three stories later."""
    out: set[str] = set()
    for pos in pd.Series(positions).dropna().unique():
        for t in str(pos).split("/"):
            t = t.strip().upper()
            if t and t not in PITCHER_TOKENS and t not in BATTER_TOKENS:
                out.add(t)
    return out


def resolve_player_type(position: object, pitcher_games: float, batter_games: float
                        ) -> tuple[str, str]:
    """The classification cascade. Returns `(player_type, source)` — the source is reported so a run
    where many rows fell through to the logs (or to the default) is visible."""
    label = classify_position(position)
    if label is not None:
        return label, "position"
    pg = float(pitcher_games or 0.0)
    bg = float(batter_games or 0.0)
    if pg > 0 or bg > 0:
        return ("pitcher" if pg > bg else "batter"), "milb_game_logs"
    return "batter", "default"


def is_pitcher_position(pos: object) -> bool:
    """Back-compat convenience: True only when the position string ITSELF says pitcher. Callers that
    need a decision for every row must use `resolve_player_type` — this one cannot see two-way or
    unrecognised labels."""
    return classify_position(pos) == "pitcher"


def batter_fantasy_points(hits, home_runs, walks, strikeouts,
                          weights: dict[str, float] | None = None) -> np.ndarray:
    """Points-league fantasy points from a batter's accumulated window counts (see BAT_FP_WEIGHTS)."""
    w = weights or BAT_FP_WEIGHTS
    h = _num(hits); hr = _num(home_runs); bb = _num(walks); k = _num(strikeouts)
    return (w["hit_non_hr"] * np.maximum(h - hr, 0.0) + w["hr"] * hr
            + w["bb"] * bb + w["k"] * k)


def pitcher_fantasy_points(batters_faced, hits_allowed, walks, strikeouts, home_runs_allowed,
                           weights: dict[str, float] | None = None) -> np.ndarray:
    """Points-league fantasy points from a pitcher's accumulated window counts (see PIT_FP_WEIGHTS).

    Innings are reconstructed as (BF − H − BB)/3 and floored at 0 — a bullpen cameo with more
    baserunners than outs must not score NEGATIVE innings."""
    w = weights or PIT_FP_WEIGHTS
    bf = _num(batters_faced); h = _num(hits_allowed); bb = _num(walks)
    k = _num(strikeouts); hr = _num(home_runs_allowed)
    ip = np.maximum(bf - h - bb, 0.0) / 3.0
    return w["ip"] * ip + w["k"] * k + w["hit"] * h + w["bb"] * bb + w["hr"] * hr


def _num(v) -> np.ndarray:
    return pd.to_numeric(pd.Series(v).reset_index(drop=True), errors="coerce").fillna(0.0).to_numpy(float)


def attach_outcome(cohort: pd.DataFrame, *, weights_bat: dict[str, float] | None = None,
                   weights_pit: dict[str, float] | None = None,
                   min_debut_pa: int = MIN_DEBUT_PA,
                   min_debut_bf: int = MIN_DEBUT_BF) -> pd.DataFrame:
    """Attach `fantasy_points`, `debuted`, and `exposure` to an assembled cohort frame.

    A row that never reached MLB inside its window scores **0 fantasy points — a realized outcome for a
    dynasty owner, not missing data**. That is what dissolves the survivorship confound at the
    `unconditional` stage. `debuted` additionally requires real playing time (a 4-PA September cameo is
    not fantasy value); the un-debuted and the cameo alike keep their honest 0.
    """
    out = cohort.copy().reset_index(drop=True)
    is_pit = out["player_type"].astype(str).eq("pitcher").to_numpy()

    def col(name: str) -> pd.Series:
        """A missing counting column means ZERO of that event, not a zero-length array — a batter-only
        fixture carries no pitcher columns and must still score."""
        v = out.get(name)
        return pd.Series(0.0, index=out.index) if v is None else v

    fp_bat = batter_fantasy_points(col("mlb_hits"), col("mlb_home_runs"),
                                   col("mlb_walks"), col("mlb_strikeouts"), weights_bat)
    fp_pit = pitcher_fantasy_points(col("mlb_batters_faced"), col("mlb_hits_allowed"),
                                    col("mlb_walks_allowed"), col("mlb_strikeouts_pitched"),
                                    col("mlb_home_runs_allowed"), weights_pit)
    out["fantasy_points"] = np.where(is_pit, fp_pit, fp_bat)

    pa = _num(col("mlb_pa"))
    bf = _num(col("mlb_batters_faced"))
    out["exposure"] = np.where(is_pit, bf, pa)
    out["debuted"] = np.where(is_pit, bf >= min_debut_bf, pa >= min_debut_pa)
    # a sub-threshold cameo returns its real (small) points; a non-appearance is a hard 0
    out.loc[~out["debuted"], "fantasy_points"] = np.where(
        out.loc[~out["debuted"], "exposure"].to_numpy(float) > 0,
        out.loc[~out["debuted"], "fantasy_points"].to_numpy(float), 0.0)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Feature blocks + the design builder (every statistic fitted on TRAIN only — leakage-safe)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

BLOCK_NULL = "null"
BLOCK_PERF = "perf"
BLOCK_FV = "fv"
BLOCK_RANK = "rank"

# The as-of MiLB rate columns each player type reads (assembled pre-board — see build_fv_cohort.py).
PERF_COLS = {
    "batter": ("minor_woba", "minor_k_pct", "minor_bb_pct", "minor_iso"),
    "pitcher": ("minor_k_pct", "minor_bb_pct", "minor_hr_rate", "minor_gb_pct"),
}

# FV grade buckets for the `bucket` transform — the 20-80 scouting scale is ORDINAL with heaps at the
# published grades, so "is this a 55 or a 45" may matter more than the linear distance.
FV_BUCKETS = (0, 40, 45, 50, 55, 60, 100)


@dataclass(frozen=True)
class FeatureSet:
    """One pre-registered feature configuration. `blocks` is the arm; `fv_transform` is the FV-shape
    axis the story asks us to count toward deflation."""

    name: str
    blocks: tuple[str, ...]
    fv_transform: str = "linear"   # "linear" | "bucket"

    @property
    def has_fv(self) -> bool:
        return BLOCK_FV in self.blocks or BLOCK_RANK in self.blocks

    @property
    def is_fangraphs_free(self) -> bool:
        return not self.has_fv


def feature_sets() -> list[FeatureSet]:
    """The pre-registered feature-set grid. Every entry counts toward PBO/DSR (deflation is what makes
    a search this wide safe). Ordered so the two PRIMARY-contrast pairs sit adjacent."""
    sets = [
        FeatureSet("null", (BLOCK_NULL,)),
        FeatureSet("null+perf", (BLOCK_NULL, BLOCK_PERF)),
        FeatureSet("fv_only", (BLOCK_FV,)),
        FeatureSet("null+fv", (BLOCK_NULL, BLOCK_FV)),
        FeatureSet("null+perf+fv", (BLOCK_NULL, BLOCK_PERF, BLOCK_FV)),
        FeatureSet("null+rank", (BLOCK_NULL, BLOCK_RANK)),
        FeatureSet("null+perf+rank", (BLOCK_NULL, BLOCK_PERF, BLOCK_RANK)),
        FeatureSet("null+perf+fv+rank", (BLOCK_NULL, BLOCK_PERF, BLOCK_FV, BLOCK_RANK)),
    ]
    # the FV-transform axis: every FV-carrying set is also tried as grade BUCKETS
    bucket = [FeatureSet(f"{fs.name}#bucket", fs.blocks, "bucket")
              for fs in sets if BLOCK_FV in fs.blocks]
    return sets + bucket


# The two FIXED contrasts (declared here, never chosen after seeing results).
PRIMARY_CONTRAST = ("null+perf+fv", "null+perf")
SECONDARY_CONTRAST = ("null+fv", "null")


def _numeric_col(df: pd.DataFrame, col: str) -> pd.Series:
    """A numeric column as a Series, or an all-NaN Series when the frame does not carry it.

    A per-type feature is legitimately absent for the other type (a bat has no `minor_gb_pct`), so an
    absent column is imputed exactly like an absent VALUE — never a scalar that blows up downstream.
    """
    v = df.get(col)
    if v is None:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(v, errors="coerce")


class Designer:
    """Builds the model matrix. Every imputation constant, category level and the age-by-level mean is
    learned on the TRAIN fold and applied verbatim to the eval fold (the level-confound control must
    not peek at the cohort being scored)."""

    def __init__(self, fs: FeatureSet, player_type: str):
        self.fs = fs
        self.player_type = player_type

    def fit(self, train: pd.DataFrame) -> "Designer":
        self.levels_ = sorted(str(v) for v in train["level"].dropna().unique())
        self.risks_ = sorted(str(v) for v in train.get("risk", pd.Series(dtype=object)).dropna().unique())
        # age-relative-to-level: the TRAIN mean age at each level (the level confound control)
        age = pd.to_numeric(train.get("age"), errors="coerce")
        self.age_by_level_ = age.groupby(train["level"].astype(str)).mean().to_dict()
        self.age_global_ = float(age.mean()) if age.notna().any() else 0.0
        self.medians_ = {}
        for c in self._numeric_cols():
            v = _numeric_col(train, c)
            self.medians_[c] = float(v.median()) if v.notna().any() else 0.0
        return self

    def _numeric_cols(self) -> list[str]:
        cols: list[str] = []
        if BLOCK_NULL in self.fs.blocks:
            cols += ["age", "pro_experience_years", "pre_board_mlb_exposure"]
        if BLOCK_PERF in self.fs.blocks:
            cols += list(PERF_COLS[self.player_type]) + ["minor_pa"]
        if BLOCK_FV in self.fs.blocks:
            cols += ["fv", "eta"]
        if BLOCK_RANK in self.fs.blocks:
            cols += ["overall_rank", "org_rank", "fantasy_dynasty_rank"]
        return cols

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        cols: list[np.ndarray] = []
        names: list[str] = []
        n = len(df)

        def add(name: str, v: np.ndarray) -> None:
            cols.append(np.asarray(v, float).reshape(n)); names.append(name)

        def imputed(c: str) -> np.ndarray:
            v = _numeric_col(df, c).to_numpy(float)
            return np.where(np.isfinite(v), v, self.medians_.get(c, 0.0))

        if BLOCK_NULL in self.fs.blocks:
            age = imputed("age")
            add("age", age)
            lvl = df["level"].astype(str)
            lvl_mean = lvl.map(self.age_by_level_).fillna(self.age_global_).to_numpy(float)
            add("age_rel_level", age - lvl_mean)                 # ⭐ the level-confound control
            add("pro_experience_years", imputed("pro_experience_years"))
            add("log_pre_board_mlb_exposure",
                np.log1p(np.maximum(imputed("pre_board_mlb_exposure"), 0.0)))
            for lv in self.levels_:
                add(f"level__{lv}", (lvl == lv).to_numpy(float))

        if BLOCK_PERF in self.fs.blocks:
            has_line = pd.to_numeric(df.get("minor_pa"), errors="coerce").fillna(0.0).to_numpy(float)
            add("log_minor_pa", np.log1p(np.maximum(has_line, 0.0)))
            add("minor_line_missing", (has_line < MIN_MINOR_PA).astype(float))
            for c in PERF_COLS[self.player_type]:
                add(c, imputed(c))

        if BLOCK_FV in self.fs.blocks:
            fv = imputed("fv")
            if self.fs.fv_transform == "bucket":
                for lo, hi in zip(FV_BUCKETS[:-1], FV_BUCKETS[1:]):
                    add(f"fv__{lo}_{hi}", ((fv > lo) & (fv <= hi)).astype(float))
            else:
                add("fv", fv)
            eta = imputed("eta")
            season = pd.to_numeric(df.get("board_season"), errors="coerce").fillna(0.0).to_numpy(float)
            add("eta_lead", np.where(eta > 0, eta - season, 0.0))
            risk = df.get("risk", pd.Series([None] * n, index=df.index)).astype(str)
            for r in self.risks_:
                add(f"risk__{r}", (risk == r).to_numpy(float))

        if BLOCK_RANK in self.fs.blocks:
            for c, tag in (("overall_rank", "ovr"), ("org_rank", "org"),
                           ("fantasy_dynasty_rank", "dyn")):
                v = pd.to_numeric(df.get(c), errors="coerce").to_numpy(float)
                ranked = np.isfinite(v) & (v > 0)
                # 1/log2(1+rank): steep at the top of the board, flat in the tail — the shape a draft
                # actually experiences. Unranked is a STATE (score 0 + flag), never an imputed rank.
                add(f"{tag}_rank_score", np.where(ranked, 1.0 / np.log2(1.0 + np.maximum(v, 1.0)), 0.0))
                add(f"is_{tag}_ranked", ranked.astype(float))

        self.feature_names_ = names
        return np.column_stack(cols) if cols else np.zeros((n, 1))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Learners
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Learner:
    name: str
    kind: str                    # "linear" | "gbm"
    params: tuple = ()


def learners(stage: str) -> list[Learner]:
    """The pre-registered learner set. Deliberately small — the study's question is about a FEATURE
    BLOCK, and every extra learner inflates the trial count the DSR has to deflate."""
    return [
        Learner("linear", "linear"),
        Learner("gbm@200-2-0.05", "gbm", (200, 2, 0.05)),
        Learner("gbm@400-3-0.03", "gbm", (400, 3, 0.03)),
    ]


def _fit_predict(learner: Learner, X: np.ndarray, y: np.ndarray, Xt: np.ndarray,
                 *, binary: bool) -> np.ndarray:
    """Fit on (X, y) and score Xt. Returns a SCORE (higher = more predicted value/probability); the
    evaluation is rank-based, so the score's scale never matters."""
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.preprocessing import StandardScaler

    if len(np.unique(y)) < 2:                       # a degenerate fold cannot be fit
        return np.zeros(len(Xt))
    if learner.kind == "linear":
        sc = StandardScaler().fit(X)
        Xs, Xts = sc.transform(X), sc.transform(Xt)
        if binary:
            m = LogisticRegression(max_iter=2000, C=1.0).fit(Xs, y)
            return m.predict_proba(Xts)[:, 1]
        return Ridge(alpha=1.0).fit(Xs, y).predict(Xts)
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    n, d, lr = learner.params
    common = dict(n_estimators=n, max_depth=d, learning_rate=lr, random_state=0)
    if binary:
        return GradientBoostingClassifier(**common).fit(X, y).predict_proba(Xt)[:, 1]
    return GradientBoostingRegressor(**common).fit(X, y).predict(Xt)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Rank metrics (+ the oracle floor)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def spearman(pred, y) -> float | None:
    """Tie-aware Spearman ρ. Returns None when either side is degenerate (a cohort where every
    prospect scored 0 carries no ordering to learn — honest None, never a fabricated 0)."""
    a = pd.to_numeric(pd.Series(pred).reset_index(drop=True), errors="coerce")
    b = pd.to_numeric(pd.Series(y).reset_index(drop=True), errors="coerce")
    ok = a.notna() & b.notna()
    if ok.sum() < 5:
        return None
    ra, rb = a[ok].rank(), b[ok].rank()
    if ra.std(ddof=0) == 0 or rb.std(ddof=0) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def auc(pred, y) -> float | None:
    """Mann-Whitney AUC (tie-corrected). None when a fold has only one class."""
    a = pd.to_numeric(pd.Series(pred).reset_index(drop=True), errors="coerce")
    b = pd.Series(y).reset_index(drop=True).astype(float)
    ok = a.notna() & b.notna()
    a, b = a[ok], b[ok]
    n1, n0 = float((b > 0.5).sum()), float((b <= 0.5).sum())
    if n1 < 2 or n0 < 2:
        return None
    r = a.rank()
    return float((r[b > 0.5].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def stage_metric(stage: str):
    return auc if stage == "debut" else spearman


def oracle_is_the_scoring_floor(scores: dict[str, float | None], oracle: float | None,
                                tol: float = 1e-9) -> bool:
    """⭐ E2.1-r SELECTION-METRIC HYGIENE. Score a target-seeing oracle and assert nothing beats it.
    A candidate scoring ABOVE the oracle is mathematically impossible for a rank metric — it is the
    tell that the metric is INVERTED, which is exactly how a pre-registered metric silently ranks an
    under-dispersed candidate first."""
    if oracle is None:
        return True
    return all(v is None or v <= oracle + tol for v in scores.values())


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# CV folds — leave-one-board-cohort-out, expanding, PLAYER-PURGED
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class Fold:
    cohort: int
    train_idx: np.ndarray
    test_idx: np.ndarray
    n_purged: int


def cohort_folds(df: pd.DataFrame, *, horizon: int = 3, strict_realtime: bool = False) -> list[Fold]:
    """Expanding-window folds over board cohorts with a PLAYER PURGE.

    The purge is not optional hygiene: a prospect sits on 3–5 consecutive boards and those rows share
    ONE overlapping outcome window, so leaving him in the training fold turns a "projection" into a
    recollection of the same person's realized MLB line.

    `strict_realtime=True` additionally restricts training to cohorts whose full outcome window had
    CLOSED by the test cohort's board date (`train_cohort + horizon <= test_cohort`) — the only
    variant a model could genuinely have been fit on in real time. With ~5 board cohorts it usually
    leaves too few folds to support PBO; it is run as a reported sensitivity, never as the primary.
    """
    cohorts = sorted(int(c) for c in df["board_season"].dropna().unique())
    key = df["player_key"].astype(str)
    folds: list[Fold] = []
    for c in cohorts:
        prior = [p for p in cohorts if p < c and (not strict_realtime or p + horizon <= c)]
        if not prior:
            continue
        test_mask = df["board_season"].astype("Int64").eq(c).fillna(False).to_numpy()
        test_players = set(key[test_mask])
        train_mask = (df["board_season"].isin(prior).to_numpy()
                      & ~key.isin(test_players).to_numpy())     # ⭐ the player purge
        n_purged = int((df["board_season"].isin(prior).to_numpy() & key.isin(test_players).to_numpy()).sum())
        if train_mask.sum() < 30 or test_mask.sum() < 10:
            continue
        folds.append(Fold(cohort=c, train_idx=np.flatnonzero(train_mask),
                          test_idx=np.flatnonzero(test_mask), n_purged=n_purged))
    return folds


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The bake-off, per (player_type, stage)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

@dataclass
class StageResult:
    player_type: str
    stage: str
    leaderboard: pd.DataFrame                 # per-config mean OOS metric
    per_fold: pd.DataFrame                    # config × fold matrix of the OOS metric
    fold_cohorts: list[int]
    n_train_rows: int
    n_test_rows: int
    # rows dropped from training because the same prospect is being evaluated — the leakage guard's
    # real cost, reported so a thin training fold is visible rather than inferred
    n_purged_rows: int
    oracle_ok: bool
    oracle_score: float | None
    pbo: float | None = None
    config_spread: float | None = None      # spread across the CONTENDERS (top quartile)
    full_spread: float | None = None        # min→max across every config, reported for transparency
    dsr: float | None = None
    contrasts: dict = field(default_factory=dict)     # the FIXED pre-registered pairs
    notes: list[str] = field(default_factory=list)


def _stage_frame(df: pd.DataFrame, stage: str) -> pd.DataFrame:
    """The row population + target for a stage.

      debut         — the FULL cohort, y = reached MLB with real playing time (the SELECTION channel)
      conditional   — DEBUTS ONLY, y = fantasy points (the survivorship-exposed channel, reported so
                      the inflation is visible rather than silently baked into a headline)
      unconditional — the FULL cohort, y = fantasy points with a hard 0 for a prospect who never made
                      it ⭐ the draft-relevant stage; no survivorship selection at all
    """
    if stage == "debut":
        out = df.copy()
        out["_y"] = out["debuted"].astype(float)
    elif stage == "conditional":
        out = df[df["debuted"].astype(bool)].copy()
        out["_y"] = pd.to_numeric(out["fantasy_points"], errors="coerce")
    elif stage == "unconditional":
        out = df.copy()
        out["_y"] = pd.to_numeric(out["fantasy_points"], errors="coerce").fillna(0.0)
    else:
        raise ValueError(f"unknown stage {stage!r}")
    return out.reset_index(drop=True)


def config_name(fs: FeatureSet, lr: Learner) -> str:
    return f"{fs.name}@{lr.name}"


def run_stage(cohort: pd.DataFrame, *, player_type: str, stage: str, horizon: int = 3,
              strict_realtime: bool = False,
              learner_set: list[Learner] | None = None) -> StageResult:
    """Run every (feature set × learner) config for one (player_type, stage) under the purged
    expanding-cohort CV, then attach the deflation numbers and the FIXED contrasts.

    `learner_set` narrows the pre-registered learner grid — used by the fast-gate tests and the
    `--fast` smoke so a full GBM sweep is not paid for twice. A narrowed set also narrows the DSR's
    trial count, which is correct: the deflation must reflect the search ACTUALLY run.
    """
    from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv

    df = cohort[cohort["player_type"].astype(str) == player_type]
    data = _stage_frame(df, stage)
    folds = cohort_folds(data, horizon=horizon, strict_realtime=strict_realtime)
    notes: list[str] = []
    if len(folds) < 2:
        raise ValueError(
            f"[{player_type}/{stage}] only {len(folds)} evaluable board cohort(s) — the study needs "
            f"≥2. With a {horizon}-season outcome window a cohort is evaluable only when a strictly "
            f"prior cohort exists AND its window has closed; widen the board backfill or shorten "
            f"--horizon."
        )

    sets = feature_sets()
    lrns = list(learner_set) if learner_set else learners(stage)
    configs = [(fs, lr) for fs in sets for lr in lrns]
    names = [config_name(fs, lr) for fs, lr in configs]
    metric = stage_metric(stage)
    binary = stage == "debut"

    mat = np.full((len(folds), len(configs)), np.nan)
    for fi, fold in enumerate(folds):
        train = data.iloc[fold.train_idx]
        test = data.iloc[fold.test_idx]
        y_tr = train["_y"].to_numpy(float)
        y_te = test["_y"].to_numpy(float)
        for ci, (fs, lr) in enumerate(configs):
            try:
                dz = Designer(fs, player_type).fit(train)
                X, Xt = dz.transform(train), dz.transform(test)
                pred = _fit_predict(lr, X, y_tr, Xt, binary=binary)
                v = metric(pred, y_te)
            except Exception as e:                      # a degenerate fold must not kill the sweep
                notes.append(f"fold {fold.cohort} config {names[ci]}: {type(e).__name__}: {e}")
                v = None
            mat[fi, ci] = np.nan if v is None else v

    per_fold = pd.DataFrame(mat.T, index=names, columns=[f.cohort for f in folds])
    mean_score = np.nanmean(mat, axis=0)
    leaderboard = (pd.DataFrame({
        "config": names,
        "feature_set": [fs.name for fs, _ in configs],
        "learner": [lr.name for _, lr in configs],
        "uses_fangraphs": [fs.has_fv for fs, _ in configs],
        "oos_metric": mean_score,
    }).sort_values("oos_metric", ascending=False).reset_index(drop=True))

    # ── ORACLE FLOOR: the realized outcome itself scores the ceiling (ρ = 1 / AUC = 1) ─────────────
    oracle = metric(data["_y"], data["_y"])
    oracle_ok = oracle_is_the_scoring_floor(
        {n: (None if not np.isfinite(v) else float(v)) for n, v in zip(names, mean_score)}, oracle)
    if not oracle_ok:
        notes.append("ORACLE-FLOOR VIOLATION — a candidate scored above a target-seeing oracle; the "
                     "selection metric is inverted (E2.1-r).")

    res = StageResult(
        player_type=player_type, stage=stage, leaderboard=leaderboard, per_fold=per_fold,
        fold_cohorts=[f.cohort for f in folds],
        n_train_rows=int(sum(len(f.train_idx) for f in folds)),
        n_test_rows=int(sum(len(f.test_idx) for f in folds)),
        n_purged_rows=int(sum(f.n_purged for f in folds)),
        oracle_ok=oracle_ok, oracle_score=oracle, notes=notes,
    )

    # ── Deflation over the WHOLE search ────────────────────────────────────────────────────────────
    finite = [i for i in range(len(configs)) if np.isfinite(mat[:, i]).all()]
    if len(finite) >= 2 and len(folds) >= 4:
        res.pbo = float(pbo_cscv(mat[:, finite], higher_is_better=True,
                                 n_splits=min(len(folds), 8)).pbo)
    else:
        notes.append(f"PBO not computable: {len(folds)} folds × {len(finite)} complete configs "
                     f"(CSCV needs ≥4 folds and ≥2 configs) — small-N, stated not hidden.")
    res.config_spread, res.full_spread = contender_spread(mean_score)

    # ── The FIXED pre-registered contrasts ─────────────────────────────────────────────────────────
    for tag, (fv_set, base_set) in (("primary", PRIMARY_CONTRAST), ("secondary", SECONDARY_CONTRAST)):
        res.contrasts[tag] = _contrast(per_fold, fv_set, base_set, lrns, n_trials=len(configs),
                                       deflated_sharpe=deflated_sharpe)
    prim = res.contrasts.get("primary", {}).get("linear", {})
    res.dsr = prim.get("dsr")
    return res


def contender_spread(mean_score: np.ndarray) -> tuple[float | None, float | None]:
    """The PBO discriminator (E2.1-r), measured on the CONTENDERS rather than the whole grid.

    A min→max spread over every config is dominated by the deliberately-crippled reference arms —
    `fv_only` carries no level or age at all and will always trail — so it says nothing about whether
    the configs that could actually win are TIED. The tie-vs-overfit read therefore uses the spread
    across the top QUARTILE (min 3 configs); the full range is returned alongside it for transparency.
    """
    ms = np.asarray(mean_score, float)
    ms = ms[np.isfinite(ms)]
    if len(ms) < 2:
        return None, None
    k = max(3, int(np.ceil(len(ms) / 4)))
    top = np.sort(ms)[-k:]
    return float(top.max() - top.min()), float(ms.max() - ms.min())


def _contrast(per_fold: pd.DataFrame, fv_set: str, base_set: str, lrns: list[Learner],
              *, n_trials: int, deflated_sharpe) -> dict:
    """One FIXED pair (FV arm − no-FV arm), evaluated per learner. Returns per-fold deltas, the mean
    lift, a one-sided paired p-value for H1: lift > 0, and the winner-arm DSR deflated by the FULL
    trial count (the search the study ran, not just this pair)."""
    out: dict = {}
    for lr in lrns:
        a, b = f"{fv_set}@{lr.name}", f"{base_set}@{lr.name}"
        if a not in per_fold.index or b not in per_fold.index:
            continue
        d = (per_fold.loc[a] - per_fold.loc[b]).to_numpy(float)
        d = d[np.isfinite(d)]
        entry: dict = {
            "fv_arm": a, "base_arm": b,
            "per_fold_delta": [round(float(x), 4) for x in d],
            "mean_lift": float(np.mean(d)) if len(d) else None,
            "n_folds": int(len(d)),
            "p_value": onesided_paired_pvalue(d),
            "dsr": None,
        }
        if len(d) >= 3 and np.std(d, ddof=1) > 0:
            try:
                entry["dsr"] = float(deflated_sharpe(d, n_trials=n_trials).dsr)
            except Exception:  # noqa: BLE001 — a degenerate series is an honest None
                entry["dsr"] = None
        out[lr.name] = entry
    return out


def onesided_paired_pvalue(deltas) -> float | None:
    """One-sided paired t-test p-value for H1: mean(delta) > 0 — the per-(type, stage) evidence fed to
    BH-FDR. None when too thin (<3 folds) to say anything (small-N honesty, not a 1.0 stand-in)."""
    from scipy.stats import t as student_t

    d = np.asarray(deltas, float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return None
    sd = float(d.std(ddof=1))
    if sd < 1e-12:
        return 0.0 if d.mean() > 0 else 1.0
    tstat = float(d.mean()) / (sd / np.sqrt(len(d)))
    return float(1.0 - student_t.cdf(tstat, len(d) - 1))


def bh_fdr(pvals: dict[str, float | None], q: float = FDR_Q) -> dict[str, bool]:
    """Benjamini-Hochberg at level `q` across the study family (player_type × stage). An unscorable
    (None) p-value can never pass — a test we could not run is not a test we won."""
    items = sorted(((k, p) for k, p in pvals.items() if p is not None), key=lambda kv: kv[1])
    out = {k: False for k in pvals}
    if not items:
        return out
    m = len(items)
    cutoff = 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= q * i / m:
            cutoff = i
    for i, (k, _) in enumerate(items, start=1):
        out[k] = i <= cutoff
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The verdict
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def stage_verdict(res: StageResult, *, fdr_pass: bool, learner: str = "linear",
                  pbo_max: float = PBO_MAX, dsr_min: float = DSR_MIN) -> dict:
    """Does FV/rank add DEFLATED, confound-controlled lift at this (player_type, stage)?

    Requires ALL of: the fixed primary contrast is positive out-of-sample, its one-sided p survives
    BH-FDR across the family, the DSR clears the bar, and the search-wide PBO clears the bar.

    ⭐ THE TIED-FIELD READ (E2.1-r) is applied here rather than left to the reader: a HIGH PBO over a
    TIGHT config spread is the NULL ("nothing robustly separates"), not evidence of overfitting; a
    high PBO over a WIDE spread IS overfitting. The spread is the discriminator, so it is reported
    next to the PBO in every verdict.
    """
    c = res.contrasts.get("primary", {}).get(learner, {})
    lift = c.get("mean_lift")
    checks = {
        "lift_positive": bool(lift is not None and lift > 0),
        "fdr_ok": bool(fdr_pass),
        "dsr_ok": bool(c.get("dsr") is not None and c["dsr"] >= dsr_min),
        "pbo_ok": bool(res.pbo is not None and res.pbo < pbo_max),
        "oracle_ok": bool(res.oracle_ok),
    }
    adds_lift = all(checks.values())
    if res.pbo is None:
        pbo_read = "not computable (too few board cohorts) — small-N, stated"
    elif res.pbo < pbo_max:
        pbo_read = "clears the bar"
    elif (res.config_spread or 0.0) < 0.05:
        pbo_read = ("TIED FIELD → read as the NULL, not as overfitting (E2.1-r): the CONTENDERS are "
                    f"within {res.config_spread:.3f} of each other, so 'which one wins' is noise")
    else:
        pbo_read = (f"high PBO over a WIDE contender spread ({res.config_spread:.3f}) → genuine "
                    f"overfitting risk, not a tie")
    return {
        "player_type": res.player_type, "stage": res.stage, "learner": learner,
        "adds_lift": adds_lift, "mean_lift": lift, "p_value": c.get("p_value"),
        "dsr": c.get("dsr"), "pbo": res.pbo, "config_spread": res.config_spread,
        "full_spread": res.full_spread, "pbo_read": pbo_read, **checks,
    }


def block_decomposition(leaderboard: pd.DataFrame) -> dict:
    """How much does OUR OWN performance read add over the null, and how much does FV add ON TOP?

    Both are read off the SAME leaderboard the verdict came from, taking each feature set's best
    learner. This is the mechanism question the headline contrast cannot answer: a positive contrast
    says "FV adds something", but not whether it adds something our own MLE already knew.
    """
    best = {}
    for fs in ("null", "null+perf", "null+perf+fv"):
        vals = leaderboard.loc[leaderboard["feature_set"] == fs, "oos_metric"]
        vals = vals[np.isfinite(vals)]
        best[fs] = float(vals.max()) if len(vals) else float("nan")
    return {
        **best,
        "perf_adds": best["null+perf"] - best["null"],
        "fv_adds_over_perf": best["null+perf+fv"] - best["null+perf"],
    }


def mechanism_rows(results: dict) -> list[dict]:
    """The decomposition table, one row per (player_type, stage)."""
    rows = []
    for (ptype, stage), res in results.items():
        d = block_decomposition(res.leaderboard)
        rows.append({"player_type": ptype, "stage": stage,
                     "null": d["null"], "null+perf": d["null+perf"],
                     "perf_adds": d["perf_adds"], "fv_adds_over_perf": d["fv_adds_over_perf"]})
    return rows


def mechanism_read(rows: list[dict]) -> dict[str, str]:
    """Per player type: are FV and our own MLE SUBSTITUTES or COMPLEMENTS?

    Computed, never asserted — a future re-run must be able to overturn this sentence. If our
    performance read adds MORE than FV does on top of it, the two are substitutes (the MLE already
    carries the scouting signal); if FV adds more, they are complements (FV carries information the
    statistical record does not).
    """
    out: dict[str, str] = {}
    for ptype in sorted({r["player_type"] for r in rows}):
        mine = [r for r in rows if r["player_type"] == ptype]
        perf = float(np.nanmean([r["perf_adds"] for r in mine]))
        fv = float(np.nanmean([r["fv_adds_over_perf"] for r in mine]))
        if fv > perf:
            out[ptype] = (f"COMPLEMENTS — our MiLB performance read adds {perf:+.4f} on average while "
                          f"FV adds a further {fv:+.4f} ON TOP of it, so the scouting grade carries "
                          f"information the statistical record does not.")
        else:
            out[ptype] = (f"SUBSTITUTES — our MiLB performance read adds {perf:+.4f} on average and FV "
                          f"only a further {fv:+.4f} on top, so the MLE already captures most of what "
                          f"the grade would tell us.")
    return out


def draft_takeaway(verdicts: list[dict]) -> str:
    """The one line the 2026-08-03 prospect draft actually consumes. A clean null is a REAL answer
    here — it says lean on our MLE + age-relative-to-level and do not pay up for FV hype."""
    unc = [v for v in verdicts if v["stage"] == "unconditional"]
    debut = [v for v in verdicts if v["stage"] == "debut"]
    types = sorted({v["player_type"] for v in verdicts})
    wins_unc = [v["player_type"] for v in unc if v["adds_lift"]]
    wins_debut = [v["player_type"] for v in debut if v["adds_lift"]]
    # a type that did NOT clear the gates needs an instruction too — silence there reads as
    # "the finding applies to everyone", which is the misuse this study exists to prevent.
    rest = [t for t in types if t not in wins_unc]
    rest_note = ("" if not rest else
                 f" For {', '.join(rest)}, FV did NOT clear the deflated gates — lean on our MLE + "
                 f"age-relative-to-level there and treat the grade as confirmation, not evidence.")
    if wins_unc:
        return (f"TRUST FV FOR {', '.join(t.upper() for t in wins_unc)} — it adds deflated, "
                "confound-controlled lift on realized dynasty-fantasy value. Use FV/rank as a "
                "headline ordering input for those, alongside (not instead of) our MLE + "
                f"age-relative-to-level.{rest_note}")
    if wins_debut:
        return ("PARTIAL — FV does NOT survive on realized fantasy VALUE, but it does predict WHO "
                f"REACHES the majors ({', '.join(wins_debut)}). Draft read: use FV as a proximity / "
                "risk-of-never-arriving signal, not as a production forecast; rank inside the "
                "'will arrive' group with our MLE + age-relative-to-level.")
    return ("CLEAN NULL — FV/rank adds no deflated lift over age-relative-to-level + level + "
            "pedigree once the survivorship and level confounds are controlled. Draft read: LEAN ON "
            "OUR MLE + AGE-RELATIVE-TO-LEVEL and do not pay up for FV hype; on the E8 board FV is a "
            "DISPLAY attribute (what the market believes), never a headline projection claim.")
