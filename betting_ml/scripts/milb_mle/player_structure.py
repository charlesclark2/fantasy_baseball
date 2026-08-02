"""player_structure.py — MLB Edge-E7.15 H3: the PLAYER is the unit, not the row.

THE MECHANISM (pure — no IO, no Snowflake, fast-gate-safe)
----------------------------------------------------------
`build_graduated_pairs` emits ONE ROW PER (player_id, level), and every one of a player's rows carries
the SAME MLB label (its own docstring calls that "a stated limitation"). So the training matrix is
PSEUDO-REPLICATED: 2,171 labelled batter rows come from 736 players, and 42% of those players supply
four rows each — 57% of the fitted weight comes from 42% of the people. The fit currently treats those
2,171 rows as 2,171 independent observations of the minor→MLB map. They are not.

⚠️ **THIS IS AN EFFICIENCY/WEIGHTING QUESTION, NOT A LEAKAGE BUG — and the distinction is load-bearing.**
The CV folds are MLB debut cohorts and `debut_cohort` is a per-PLAYER join, so all of a player's rows
share one fold: no player ever straddles the train/test boundary. Nothing here is leaking. What is at
stake is only whose line the coefficients are fitted to.

Three pre-registered ways to take the player seriously, deliberately spanning weak→strong:

  1. **DE-PSEUDO-REPLICATION (`dedup`)** — divide the observation weight by the player's row count so
     every PLAYER carries equal total weight. The mildest possible correction: it does not change the
     identifying variation at all, it only equalises influence. `dedup_sqrt` is its matched partner —
     the classic half-measure — because "1/n is an over-correction" is a real and separate hypothesis
     from "1/n is right", and a bake-off that carries only one of them cannot tell them apart.

  2. **A PLAYER RANDOM INTERCEPT (`player_re`)** — a penalized per-player intercept block. ⭐ NOTE this
     needs NO new projector class: `PartialPoolProjector`'s slice-5 `bucket_col`/`bucket_intercept`
     machinery IS a generic grouped random intercept, and reusing it means the arm round-trips through
     `clone_projector` correctly. Writing a subclass would have re-opened the documented E7.12-S5
     landmine (`clone_projector` is `isinstance`-dispatched and returns a PLAIN `PartialPoolProjector`,
     so a subclass's extra config would be silently dropped on every expanding-window refit and the arm
     would score as the foil under its own name — the same silent-inert-arm class as the H2 anchor).

  3. **TRAJECTORY (`traj`)** — the player's rate CHANGE from their previous level to this one. Two rows
     of the same final line mean different things if one player arrived improving and the other
     declining, and nothing in the incumbent's feature vector can express that.

⭐ **A PRE-REGISTERED DIRECTIONAL PRIOR ON THE RANDOM INTERCEPT — STATED BEFORE THE RUN.** Because the
label is CONSTANT within a player, a player intercept can absorb *all* between-player variation in y,
leaving the fixed effects identified only by WITHIN-player variation — i.e. it silently converts the
estimator into a within-player one, whose identifying variation is exactly the level-transition
variation H1 measured and found null. At predict time a held-out player has no column (its intercept is
0), so the prediction is made from fixed effects fitted on within-player contrasts alone, discarding
the between-player information the incumbent actually runs on. **We therefore expect P3/P4 to LOSE, and
we are running them as a DECOMPOSITION (how much of the incumbent's skill is between- vs within-player),
not as hopefuls.** A loss here is an informative measurement; a WIN would overturn the reading above.

🎏 **EVERY MECHANISM CARRIES ITS MATCHED FOIL** (NF-D15 g′), because each of the three has an obvious
"it worked for a boring reason" explanation and a rank alone cannot separate those:
  * `player_re` vs `re_shuffled` — the same block size and the same group-size distribution with the
    player labels permuted. If a RANDOM grouping does as well, the win is extra regularization, not
    "players". This is the sharpest test in the slice.
  * `traj_ladder` vs `traj_raw` — the H1 ladder makes the cross-level difference like-for-like (without
    it, `x_high − x_prev` confounds "the player improved" with "the level got harder"). If the RAW
    delta ties it, the ladder adds nothing HERE either. ⚠️ Note this is a genuinely different USE of
    the ladder than H1 scored (H1 rewrote the feature's level; H3 uses it to make a within-player
    difference comparable), so H1's null does not transfer automatically — it is re-tested, not assumed.
  * `dedup` vs `dedup_sqrt` — full vs half correction.

🕳️ **`pct_rows_moved` MUST BE MEASURED IN THE MECHANISM'S OWN UNITS (the H2 inert-anchor lesson, one
mechanism over).** H1/H2 both rewrote `minor_<metric>`, so "did the arm act" was a feature diff. H3's
weighting and random-effect arms move NO feature value — a feature-diff activity check would report 0%
for all of them and the `must_move` guard would block the entire slice for the wrong reason. So each
arm here reports the activity of the thing it actually changes: weight arms report the share of rows
whose normalised weight moved, the RE arm reports the share of rows whose player can pool at all
(≥2 rows) together with the fitted block width, and trajectory arms report non-null delta coverage.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.level_ladder import (
    ASC_LEVELS,
    LEVEL_RANK,
    LadderFit,
)

# Deterministic seeds — a permutation anchor whose seed drifts is not an anchor.
PLAYER_SHUFFLE_SEED = 20260802
TRAJ_SHUFFLE_SEED = 20260803

# A player needs at least this many rows before a random intercept can pool anything. A one-row player
# contributes an intercept that is exactly its own residual: no information is shared, so it is neither
# helped nor harmed — but it must NOT be counted as "the mechanism acted" in the coverage report.
MIN_POOLABLE_ROWS = 2

# Column names this module owns. One canonical name per quantity — the H2 defect was two names for one
# column (a mode-suffixed variant the consumer never looked for), which made an anchor silently inert.
W_DEDUP = "w_player_dedup"
W_DEDUP_SQRT = "w_player_dedup_sqrt"
W_IDENTITY = "w_player_identity"
PLAYER_SHUFFLED = "player_id_shuffled"
TRAJ_LADDER = "traj_delta_ladder"
TRAJ_RAW = "traj_delta_raw"
TRAJ_SHUFFLED = "traj_delta_shuffled"
TRAJ_PRESENT = "traj_delta_present"
TENURE_YEARS = "level_tenure_years"
TENURE_LEVELS = "player_n_levels"

PLAYER_MODES: tuple[str, ...] = ("off", "dedup", "dedup_sqrt", "identity")


@dataclass(frozen=True)
class PlayerSpec:
    """One pre-registered rung of the H3 ladder.

    Defaults are the INCUMBENT (no reweighting, no random intercept, no trajectory), so `PlayerSpec()`
    is a byte-exact no-op — the same discipline as `ContextSpec()`/`LadderSpec()`, and pinned by a test.
    """

    weight_mode: str = "off"        # off | dedup | dedup_sqrt | identity
    player_re: bool = False         # penalized per-player intercept block
    shuffle_players: bool = False   # MATCHED FOIL for player_re — permuted grouping, same block width
    trajectory: str | None = None   # None | "ladder" | "raw" | "shuffled"
    tenure: bool = False            # years-at-level + levels-played as extra fixed regressors

    def __post_init__(self):
        if self.weight_mode not in PLAYER_MODES:
            raise ValueError(f"weight_mode={self.weight_mode!r} not in {PLAYER_MODES}")
        if self.trajectory is not None and self.trajectory not in ("ladder", "raw", "shuffled"):
            raise ValueError(f"trajectory={self.trajectory!r} not in (None, ladder, raw, shuffled)")
        if self.shuffle_players and not self.player_re:
            raise ValueError("shuffle_players is the FOIL FOR player_re — set both or neither")

    @property
    def is_noop(self) -> bool:
        return (self.weight_mode in ("off", "identity") and not self.player_re
                and self.trajectory is None and not self.tenure)

    @property
    def label(self) -> str:
        if self.weight_mode == "off" and self.is_noop:
            return "baseline"
        bits = []
        if self.weight_mode not in ("off",):
            bits.append(f"w:{self.weight_mode}")
        if self.player_re:
            bits.append("re:player" + ("_shuffled" if self.shuffle_players else ""))
        if self.trajectory:
            bits.append(f"traj:{self.trajectory}")
        if self.tenure:
            bits.append("tenure")
        return "+".join(bits) or "baseline"


# ══════════════════════════════════════════════════════════════════════════════════════
# The census — ⭐ REPORTED BEFORE ANY SCORE (the E7.15 readiness lock-2 discipline)
# ══════════════════════════════════════════════════════════════════════════════════════


def player_structure_census(pairs: pd.DataFrame, labelled_only: bool = True) -> dict:
    """How pseudo-replicated is the training matrix, and how much of it can each mechanism touch?

    The premise of the whole slice is "the row is not the unit". If most players contributed one row,
    every H3 arm would be a near-no-op and a null would be about COVERAGE rather than about the
    mechanism — the H1 lock-2 distinction. Reporting this before a leaderboard exists is what keeps
    that reading available.
    """
    d = pairs
    if labelled_only and "has_mlb_label" in d.columns:
        d = d[d["has_mlb_label"].fillna(False).astype(bool)]
    n_rows = int(len(d))
    if not n_rows:
        return {"n_rows": 0, "n_players": 0}
    counts = d.groupby("player_id").size()
    poolable = counts[counts >= MIN_POOLABLE_ROWS].index
    in_pool = d["player_id"].isin(poolable)
    # the share of fitted weight carried by the most-replicated players
    top = counts.sort_values(ascending=False)
    n_top = max(1, int(round(0.42 * len(counts))))
    return {
        "n_rows": n_rows,
        "n_players": int(counts.size),
        "mean_rows_per_player": round(float(counts.mean()), 3),
        "rows_per_player_hist": {int(k): int(v) for k, v in counts.value_counts().sort_index().items()},
        "pct_rows_poolable": round(100.0 * float(in_pool.mean()), 2),
        "pct_players_poolable": round(100.0 * len(poolable) / counts.size, 2),
        "effective_n_is_players_not_rows": f"{counts.size} players vs {n_rows} rows "
                                           f"({n_rows / counts.size:.2f}x replication)",
        "pct_weight_from_top_42pct_players": round(
            100.0 * float(top.head(n_top).sum()) / float(counts.sum()), 2),
        "n_cohorts": int(d["debut_cohort"].nunique()) if "debut_cohort" in d.columns else 0,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# Weights
# ══════════════════════════════════════════════════════════════════════════════════════


def player_row_counts(pairs: pd.DataFrame) -> pd.Series:
    """Rows per player, aligned to `pairs`' index (NOT to the player index)."""
    return pairs.groupby("player_id")["player_id"].transform("size").astype(float)


def dedup_weights(pairs: pd.DataFrame, base_weight_col: str | None, power: float) -> pd.Series:
    """`base / n_rows(player)**power`, the observation weight a de-pseudo-replicated fit wants.

    ⚠️ **THE BASE MATTERS AND IT DIFFERS BY SIDE.** The shipped pitcher configs for `bb_pct`/`hr_rate`
    already carry `w:mlb_pa` (label-precision weighting). Replacing that with a bare `1/n` would change
    TWO things at once and the arm would be unattributable — so the dedup weight MULTIPLIES the arm's
    own foil weight rather than replacing it. On a side whose foil is unweighted the base is 1.0 and
    this reduces to the plain `1/n`. `_weights` normalises to mean 1 downstream, so only the RATIOS
    here matter.
    """
    n = player_row_counts(pairs)
    base = (pd.to_numeric(pairs[base_weight_col], errors="coerce")
            if base_weight_col and base_weight_col in pairs.columns
            else pd.Series(1.0, index=pairs.index))
    base = base.where(np.isfinite(base) & (base > 0))
    base = base.fillna(float(base.median()) if base.notna().any() else 1.0)
    return base / np.power(n.clip(lower=1.0), float(power))


# ══════════════════════════════════════════════════════════════════════════════════════
# Trajectory
# ══════════════════════════════════════════════════════════════════════════════════════


def _translated_rate(pairs: pd.DataFrame, metric: str, fit: LadderFit | None) -> pd.Series:
    """Each row's minor rate expressed on the REFERENCE level's scale.

    With a ladder this is `a + b*x` for the row's own rung (the H1 `direct`-to-reference map); without
    one it is the raw rate, which is the `traj_raw` foil. Rows at the reference level are already on
    that scale under either reading.
    """
    rate = pd.to_numeric(pairs[f"minor_{metric}"], errors="coerce")
    if fit is None:
        return rate
    return pd.Series(fit.to_reference(pairs["level"], rate), index=pairs.index, dtype=float)


def trajectory_delta(pairs: pd.DataFrame, metric: str, fit: LadderFit | None) -> pd.DataFrame:
    """Per row: the change in (reference-scale) rate from the player's IMMEDIATELY PREVIOUS level.

    A player's LOWEST level row has no predecessor, so its delta is undefined — filled with 0.0 and
    flagged by `traj_delta_present`, the impute-flag pattern the GBM arm already uses. A structurally
    absent value is a documented no-op here, never a fabricated 0 masquerading as "no change".

    ⚠️ Order is by LEVEL RANK, not by season: the pairs row aggregates a player's whole stint at a
    level, so ranks are the only ordering the table supports. `build_transitions` enforces the same
    ordering for the same reason, and demotions are excluded there by a season check that has no
    analogue at this grain — so a rehab assignment can contribute a descending pair here. That is a
    stated limitation, and it is exactly what `traj_shuffled` controls for: if the ordering carried no
    real information, the shuffled foil would tie.
    """
    d = pairs[["player_id", "level"]].copy()
    d["rank"] = d["level"].map(LEVEL_RANK)
    d["ref_rate"] = _translated_rate(pairs, metric, fit)
    d = d.reset_index().rename(columns={"index": "_row"})
    d = d.sort_values(["player_id", "rank"], kind="mergesort")
    prev = d.groupby("player_id")["ref_rate"].shift(1)
    delta = d["ref_rate"] - prev
    out = pd.DataFrame({
        "_row": d["_row"].to_numpy(),
        "delta": delta.to_numpy(float),
    }).set_index("_row").reindex(pairs.index)
    present = out["delta"].notna()
    return pd.DataFrame({
        "delta": out["delta"].fillna(0.0).to_numpy(float),
        "present": present.to_numpy(float),
    }, index=pairs.index)


def _permute_within_level(values: pd.Series, levels: pd.Series, seed: int) -> pd.Series:
    """Permute across players WITHIN a level, deterministically — the placebo shape slice 1 established
    (a global shuffle would test level mixing rather than the quantity itself)."""
    rng = np.random.default_rng(seed)
    out = values.copy()
    for _lvl, idx in values.groupby(levels, dropna=False).groups.items():
        idx = pd.Index(idx)
        if len(idx) < 2:
            continue
        out.loc[idx] = values.loc[idx].to_numpy()[rng.permutation(len(idx))]
    return out


def shuffled_player_ids(pairs: pd.DataFrame, seed: int = PLAYER_SHUFFLE_SEED,
                        within: pd.Series | None = None) -> pd.Series:
    """⭐ THE MATCHED FOIL FOR THE RANDOM INTERCEPT: a permutation of the row→player assignment that
    PRESERVES the group-size multiset exactly.

    We permute the ROWS across the existing player labels rather than relabelling players, so the
    multiset of group sizes is identical by construction (the same 125 singletons, 96 pairs, 206
    triples, 309 quads) — the shuffled block then has the same width and the same shrinkage geometry as
    the real one, and the ONLY thing that differs is whether the grouping is the truth.

    🪤 **`within` IS NOT OPTIONAL POLISH — A GLOBAL PERMUTATION SILENTLY UNMATCHES THE FOIL ON THE
    POPULATION THAT IS ACTUALLY FITTED.** The pairs table is ~5× the labelled rows (it carries the
    un-promoted prospects), so a permutation over ALL rows scatters the labelled subset's ids across the
    whole ~9,800-player pool: measured, the labelled block went to **1,614 near-singleton groups against
    the true 661**, i.e. a foil 2.4× wider with almost no pooling. Its 4% loss would then have been
    partly "a badly-conditioned wide block", not "the grouping is wrong" — and the pre-registration's
    claim of identical width would have been false while the report looked healthy. Permuting WITHIN the
    stratum that will later be conditioned on (`has_mlb_label`) restores the guarantee.

    ⭐ The general rule this is an instance of: **permute within every stratum you will later condition
    on** — a foil matched on the full frame is not matched on a subset of it (NF1.7 (b), same family AND
    same resolution). Note it was the COVERAGE-DENOMINATOR fix that exposed this: while coverage was
    measured over all rows, the true and shuffled blocks both reported 9,804 and looked matched.
    """
    rng = np.random.default_rng(seed)
    ids = pairs["player_id"].to_numpy()
    out = ids.copy()
    if within is None:
        out = ids[rng.permutation(len(ids))]
    else:
        strata = pd.Series(np.asarray(within), index=pairs.index)
        for _key, idx in strata.groupby(strata, dropna=False).groups.items():
            pos = pairs.index.get_indexer(pd.Index(idx))
            if len(pos) > 1:
                out[pos] = ids[pos][rng.permutation(len(pos))]
    return pd.Series(out, index=pairs.index, name=PLAYER_SHUFFLED)


def level_tenure(pairs: pd.DataFrame) -> pd.DataFrame:
    """Years the player spent AT this level, and how many levels they logged.

    Repeating a level is a scouting-legible negative signal that the aggregated box line erases: two
    identical Double-A lines mean different things if one took one season and the other took three.
    `last_minor_season - first_minor_season` is already on every row (E7.12-S2 added it for the
    censoring model), so this costs no new build.
    """
    first = pd.to_numeric(pairs.get("first_minor_season"), errors="coerce")
    last = pd.to_numeric(pairs.get("last_minor_season"), errors="coerce")
    years = (last - first).fillna(0.0).clip(lower=0.0)
    n_levels = pairs.groupby("player_id")["level"].transform("nunique").astype(float)
    return pd.DataFrame({TENURE_YEARS: years.to_numpy(float),
                         TENURE_LEVELS: n_levels.to_numpy(float)}, index=pairs.index)


# ══════════════════════════════════════════════════════════════════════════════════════
# Apply
# ══════════════════════════════════════════════════════════════════════════════════════


def apply_player_structure(pairs: pd.DataFrame, spec: PlayerSpec, metric: str, *,
                           base_weight_col: str | None = None,
                           ladder: LadderFit | None = None,
                           fitted_mask: pd.Series | None = None) -> pd.DataFrame:
    """Attach every column this spec's arm needs. Returns a COPY; `pairs` is untouched.

    Nothing here rewrites `minor_<metric>` — that is the whole point of H3 versus H1/H2. The arm's
    effect enters through the FIT (observation weights, a penalized block, extra regressors), which is
    why the coverage report below cannot be a feature diff.

    🔒 LEAKAGE POSTURE. Row counts, level tenure and the player grouping are MiLB-side facts. The
    trajectory delta uses the H1 ladder, which is fitted on within-player MINOR transitions and touches
    no MLB label (H1 established that and measured a calendar-purged sensitivity arm against it), so
    applying it globally cannot leak the target.
    """
    out = pairs.copy().reset_index(drop=True)
    out[W_IDENTITY] = dedup_weights(out, base_weight_col, power=0.0)
    if spec.weight_mode == "dedup":
        out[W_DEDUP] = dedup_weights(out, base_weight_col, power=1.0)
    elif spec.weight_mode == "dedup_sqrt":
        out[W_DEDUP_SQRT] = dedup_weights(out, base_weight_col, power=0.5)

    if spec.player_re:
        # Permute WITHIN the exact stratum the fit conditions on, so the shuffled block's group-size
        # multiset matches the true one on the population actually fitted. `fitted_mask` is the
        # metric-specific `has_target` (a further restriction of `has_mlb_label` — a row missing THIS
        # metric's rate is dropped), and using the coarser label flag instead left the foil 712 blocks
        # against the true 661. Caller passes it; the label flag is the fallback.
        strata = fitted_mask
        if strata is None and "has_mlb_label" in out.columns:
            strata = out["has_mlb_label"].fillna(False).astype(bool)
        out[PLAYER_SHUFFLED] = shuffled_player_ids(out, within=strata)

    if spec.trajectory:
        use_ladder = ladder if spec.trajectory in ("ladder", "shuffled") else None
        traj = trajectory_delta(out, metric, use_ladder)
        delta = traj["delta"]
        if spec.trajectory == "shuffled":
            delta = _permute_within_level(delta, out["level"], TRAJ_SHUFFLE_SEED)
        col = {"ladder": TRAJ_LADDER, "raw": TRAJ_RAW, "shuffled": TRAJ_SHUFFLED}[spec.trajectory]
        out[col] = delta.to_numpy(float)
        out[TRAJ_PRESENT] = traj["present"].to_numpy(float)

    if spec.tenure:
        for c, v in level_tenure(out).items():
            out[c] = v
    return out


def weight_column_for(spec: PlayerSpec, base_weight_col: str | None) -> str | None:
    """Which column the projector's `weight_col` should point at for this spec.

    ⚠️ A spec whose weight_mode is `off` must inherit the arm's OWN foil weight, not None — otherwise
    the pitcher arms would silently DROP the shipped `w:mlb_pa` and every H3 arm on that side would be
    testing two changes at once.
    """
    return {
        "off": base_weight_col,
        "identity": W_IDENTITY,
        "dedup": W_DEDUP,
        "dedup_sqrt": W_DEDUP_SQRT,
    }[spec.weight_mode]


def extra_cols_for(spec: PlayerSpec) -> tuple[str, ...]:
    """The extra UNPENALIZED fixed regressors this spec adds.

    Trajectory and tenure are structural covariates, not deviations to be shrunk toward zero — the same
    argument E7.12-S2 made for the Heckman inverse-Mills ratio, and the reason they go in `extra_cols`
    rather than a penalized block.
    """
    cols: list[str] = []
    if spec.trajectory:
        cols.append({"ladder": TRAJ_LADDER, "raw": TRAJ_RAW, "shuffled": TRAJ_SHUFFLED}[spec.trajectory])
        cols.append(TRAJ_PRESENT)
    if spec.tenure:
        cols += [TENURE_YEARS, TENURE_LEVELS]
    return tuple(cols)


def bucket_col_for(spec: PlayerSpec) -> str | None:
    """The categorical the penalized random intercept groups on (None when the arm has no RE)."""
    if not spec.player_re:
        return None
    return PLAYER_SHUFFLED if spec.shuffle_players else "player_id"


def player_coverage(applied: pd.DataFrame, spec: PlayerSpec,
                    base_weight_col: str | None, fitted_mask: pd.Series | None = None) -> dict:
    """⭐ DID THE MECHANISM ACT — MEASURED IN THE MECHANISM'S OWN UNITS, OVER THE FITTED POPULATION.

    ⚠️ **THE DENOMINATOR IS THE LABELLED ROWS, NOT THE WHOLE PAIRS TABLE** — and getting that wrong
    understates every arm toward the inert threshold. The pairs table is ~5× labelled rows (it carries
    the un-promoted prospects the MLE exists to project), but H3's mechanisms act on the FIT, which sees
    labelled rows only. Measured over everything, the random-intercept arm reported 81.2% moved and
    9,804 blocks against the 94.2% / 736 the fit actually gets — a mechanism scored on a population it
    never touches. Feature-transform coverage (H1/H2) legitimately spans prospects because the transform
    really does rewrite their features; a fit-side mechanism does not.

    The H2 defect was an anchor that ran, moved nothing, and reported `violated=False` on an empty
    comparison. `h_harness.evaluate_anchors` now BLOCKS a `must_move` anchor that moved ≤1% of rows —
    but H3's arms change the FIT, not the feature, so a feature diff would report 0% for every one of
    them and block the slice for the wrong reason. `pct_rows_moved` here is therefore the share of rows
    the arm's OWN mechanism touched:

      * weight arms — rows whose mean-normalised weight differs from the foil's
      * random-intercept arms — rows whose player can pool at all (≥2 rows), which is also the only
        honest denominator for "the block did something"
      * trajectory arms — rows carrying a non-imputed delta
    """
    if fitted_mask is not None:
        applied = applied.loc[np.asarray(fitted_mask, dtype=bool)].reset_index(drop=True)
    n = len(applied)
    if not n:
        return {"n_rows": 0, "pct_rows_moved": 0.0}

    def _norm(col: str | None) -> np.ndarray:
        if not col or col not in applied.columns:
            return np.ones(n)
        w = pd.to_numeric(applied[col], errors="coerce").to_numpy(float)
        w = np.where(np.isfinite(w) & (w > 0), w, np.nan)
        med = float(np.nanmedian(w)) if np.isfinite(w).any() else 1.0
        w = np.nan_to_num(w, nan=med if med > 0 else 1.0)
        mean = float(np.mean(w))
        return w / mean if mean > 0 else np.ones(n)

    moved = np.zeros(n, dtype=bool)
    detail: dict = {}

    arm_w = weight_column_for(spec, base_weight_col)
    if spec.weight_mode not in ("off",):
        d = np.abs(_norm(arm_w) - _norm(base_weight_col))
        moved |= d > 1e-9
        detail["weight_ratio_p05"] = float(np.percentile(_norm(arm_w), 5))
        detail["weight_ratio_p95"] = float(np.percentile(_norm(arm_w), 95))

    if spec.player_re:
        grp = applied[bucket_col_for(spec)]
        sizes = applied.groupby(grp)[grp.name].transform("size").to_numpy(float)
        moved |= sizes >= MIN_POOLABLE_ROWS
        detail["n_player_blocks"] = int(pd.Series(grp).nunique())
        detail["pct_rows_poolable"] = round(100.0 * float((sizes >= MIN_POOLABLE_ROWS).mean()), 2)

    if spec.trajectory:
        present = pd.to_numeric(applied[TRAJ_PRESENT], errors="coerce").fillna(0.0).to_numpy(float)
        moved |= present > 0
        col = {"ladder": TRAJ_LADDER, "raw": TRAJ_RAW, "shuffled": TRAJ_SHUFFLED}[spec.trajectory]
        vals = pd.to_numeric(applied[col], errors="coerce").to_numpy(float)
        detail["traj_p05"] = float(np.nanpercentile(vals, 5))
        detail["traj_p95"] = float(np.nanpercentile(vals, 95))

    if spec.tenure:
        yrs = pd.to_numeric(applied[TENURE_YEARS], errors="coerce").fillna(0.0).to_numpy(float)
        moved |= yrs > 0
        detail["pct_repeated_a_level"] = round(100.0 * float((yrs > 0).mean()), 2)

    detail.update({"n_rows": int(n), "pct_rows_moved": round(100.0 * float(moved.mean()), 2)})
    return detail
