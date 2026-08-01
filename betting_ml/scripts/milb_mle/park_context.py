"""park_context.py — MLB Edge-E7.12 SLICE 1: minor-league PARK + LEVEL-RUN-ENVIRONMENT context, and
the small-sample (reliability) hardening of the E7.3/E7.3p Bayesian partial-pool.

WHAT THIS IS
------------
E7.3/E7.3p translate a raw MiLB rate line into an MLB-equivalent line with a Bayesian hierarchical
partial-pool. The pool learns a per-LEVEL intercept + slope and a per-LEAGUE intercept — but it sees the
player's rate **un-parked** and **un-seasoned**. Deep research (`research_milb_projection_2026-07-29.md`
Thread 1 #1) ranks that the single biggest remaining gap: minor-league park-factor dispersion is HUGE
(BA: AAA Iowa 132 vs AA Arkansas 67 — a 65-point spread, far wider than the component noise we model),
so an un-parked ISO carries systematic venue bias the pool currently absorbs as "skill."

This module is the **pure math** (no IO) so the fast gate exercises it directly; `build_park_context.py`
is the DuckDB/S3 assembly that produces the context parquet, and `run_e7_12_slice1.py` is the
pre-registered §0.5 ablation ladder that decides whether any of it ships.

⚠️ **A NULL ADD IS DROPPED, NOT SHIPPED.** Nothing here is wired into the E7.3 emission unless its arm
clears the deflated gate in the ladder. `best_alpha = 0` (a projection, never a market bet).

THE THREE MECHANISMS (each independently ablatable)
---------------------------------------------------
1. **PARK FACTOR (`pf_<metric>`)** — computed from OUR OWN free substrate (the E7.1 MiLB game logs carry
   `venue_id` / `team_side` / `game_pk` on every player-game), so no paywalled BA table and no
   pybaseball dependency. Classic Bill-James/Davenport form, per park-team T and metric m:

       PF_raw(T) = rate_m(all batter-rows in T's HOME games) / rate_m(all batter-rows in T's ROAD games)

   Both buckets contain T's own hitters, so team offensive quality largely cancels. Then:
     * **3-season trailing window** (`[S-2, S]`) — the memo is explicit that single-season MiLB PFs are
       noisy. Trailing (not centred) so the factor applied in season S never reads a future season.
     * **EB shrink toward 1.0 in LOG space** with a PA pseudo-count — a thin park is pulled to neutral,
       exactly the partial-pool posture one rung down.
     * **CLAMP** to a plausible band; a factor outside it is a broken bucket, not a bold park.

2. **LEVEL × SEASON RUN ENVIRONMENT (`env_<metric>`)** — the pool has a per-level intercept but no
   per-SEASON one, so league-wide drift (ball, level composition, pitch clock) rides in the residual.
   The adjustment re-expresses a player's rate against his LEVEL's pooled baseline:
   `rate × env_level / env_player`. Deliberately WITHIN level: the level difference is what the pool is
   supposed to learn; only the season mix is normalised away.

3. **RELIABILITY / SMALL-SAMPLE HARDENING (`reliability`)** — the story's explicit ask. A regression
   slope is a SINGLE number, so the incumbent pool cannot express "regress the 160-PA line harder than
   the 600-PA line," nor "regress ISO harder than K%." The cure is the textbook measurement-error
   (regression-dilution) shrink applied to the FEATURE, with a PER-COMPONENT stabilisation point:

       feat_rel = env + r·(feat − env),   r = PA / (PA + k_m)

   `k_m` = the PA at which split-half reliability ≈ 0.5 (Carleton / "Pizza Cutter" stabilisation points:
   K% ≈ 60 PA, BB% ≈ 120, ISO ≈ 160, wOBA ≈ 470) — i.e. **ISO is regressed ~2.7× harder than K% at equal
   PA**, which IS the measured translatability ordering (E7.3: K% corr 0.637 · BB% 0.491 · ISO 0.429)
   expressed as a prior rather than asserted.

🪤 ANCHORS — WHY THIS SLICE CANNOT FAKE A WIN (the CLAUDE.md two-sided-anchor rule)
-----------------------------------------------------------------------------------
Dividing a rate by a dispersed multiplier and shrinking it toward a mean BOTH reduce MAE against a
regressed target **whether or not the multiplier is a real park factor**. Three anchors are therefore
pre-registered as first-class arms, and a real arm that fails to beat them is a NULL, not a win:

  * **LEAVE-ONE-PLAYER-OUT is MANDATORY, not hygiene.** A player's own hot line inflates his home park's
    PF, so dividing by a self-inclusive PF shrinks *him specifically* toward the mean — manufacturing
    exactly the MAE reduction we are trying to measure. Every headline PF subtracts the player's own
    counting stats from BOTH buckets first (`park="exposure"`). `park="exposure_noloo"` is carried as a
    DIAGNOSTIC arm: if it beats the LOO arm, the "lift" is self-shrinkage, not parks.
  * **PLACEBO PARK (`park="placebo"`)** — the SAME PF values, permuted across players within a level
    (deterministic seed). Marginal distribution identical, player↔park correspondence destroyed. It MUST
    LOSE; if it ties, the mechanism is "divide by any dispersed number," not the venue.
  * **CONSTANT RELIABILITY (`constant_reliability=True`)** — everyone shrunk by the population-mean `r`.
    It MUST LOSE to the PA-varying arm, or the reliability "hardening" is just a global slope rescale the
    regression already had.

Plus a pre-registered DIRECTIONAL falsification: parks move BALLS IN PLAY. The park lift must be
concentrated in **ISO / wOBA** and be near-zero for **K% / BB%**. A lift that appears *uniformly* across
all four metrics is the shrinkage confound wearing a park costume.

⛔ CONSIDERED AND DEFERRED — the Davenport/James LEVEL-INTERCEPT ANCHOR (memo #1's third clause). The
   ~20%-off-AAA → ~60%-off-Low-A gradient is defined on overall RUN PRODUCTION, not on per-component
   rates (a "60% haircut" on K% is meaningless), and the partial pool estimates just 4 level effects from
   1,750 labelled rows — nowhere near the thin-cell regime where a fixed prior anchor beats estimation.
   Its natural form, a multiplicative per-level factor, is ALREADY in the E7.3 field as the
   `multiplicative` Davenport foil and LOST to the partial pool on every metric. Stated, not silently
   dropped.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.milb_mle import BATTER_METRICS

# The metrics a park factor is computed for. Same four as the batter MLE — each park factor is the ratio
# of that metric's rate in the park's home games to its rate in the park team's road games.
PF_METRICS: tuple[str, ...] = BATTER_METRICS

# 3 seasons, TRAILING and inclusive ([S-2, S]). The memo: single-season MiLB PFs are noisy; a centred
# window would let a factor applied in season S read season S+1 (not label leakage — the label is MLB
# production — but it is a time-ordering violation we get for free by staying trailing).
DEFAULT_PF_WINDOW = 3

# EB pseudo-count for the shrink toward a neutral park, in PLATE APPEARANCES. A park-window bucket with
# `n_eff` PA gets weight n_eff/(n_eff + PF_PSEUDO_PA) on its own raw factor. One AAA park-season is
# ~5,000 PA per side, so a full 3-season window sits around 0.88 weight and a one-off alternate site is
# pulled hard to neutral.
DEFAULT_PF_PSEUDO_PA = 2_000.0

# A factor outside this band is a broken bucket (an alternate site, a two-game "park", a division-by-tiny
# road sample), not a bold park. Clamped, and the clamp count is reported.
PF_CLAMP: tuple[float, float] = (0.60, 1.70)

# Split-half stabilisation points — the PA at which a rate's reliability ≈ 0.5 (Carleton / "Pizza Cutter";
# the same constants the public work on MLB rate stabilisation uses). These are what make the shrink
# PER-COMPONENT: at 160 PA, K% keeps r = 0.73 of its observed deviation while ISO keeps only r = 0.50.
STABILIZATION_PA: dict[str, float] = {
    "k_pct": 60.0,
    "bb_pct": 120.0,
    "iso": 160.0,
    "woba": 470.0,
    # pitcher-side siblings (E7.3p), per-TBF — carried so a follow-on pitcher slice reuses this home
    "hr_rate": 500.0,
    "gb_pct": 80.0,
    "xwoba_against": 470.0,
}

# Physically-sane bounds on an ADJUSTED minor rate. The adjustment is multiplicative, so a broken factor
# could push a rate out of its own support; clip rather than emit a rate no batter can have.
_RATE_BOUNDS: dict[str, tuple[float, float]] = {
    "woba": (0.050, 0.800),
    "k_pct": (0.0, 0.90),
    "bb_pct": (0.0, 0.60),
    "iso": (0.0, 0.80),
    "hr_rate": (0.0, 0.20),
    "gb_pct": (0.0, 1.0),
    "xwoba_against": (0.050, 0.800),
}

# The deterministic seed for the PLACEBO permutation. Fixed so the anchor is reproducible run-to-run —
# a placebo that moves between runs cannot be a gate.
PLACEBO_SEED = 20260731

PARK_MODES: tuple[str, ...] = ("off", "exposure", "halfweight", "exposure_noloo", "placebo")


# ══════════════════════════════════════════════════════════════════════════════════════
# Park-factor math
# ══════════════════════════════════════════════════════════════════════════════════════


def shrink_log_pf(
    pf_raw: np.ndarray | pd.Series,
    n_eff: np.ndarray | pd.Series,
    pseudo_pa: float = DEFAULT_PF_PSEUDO_PA,
    clamp: tuple[float, float] = PF_CLAMP,
) -> np.ndarray:
    """EB-shrink a raw park factor toward NEUTRAL (1.0) in log space, then clamp.

    `log_pf = w · log(pf_raw)` with `w = n_eff / (n_eff + pseudo_pa)`. Log space is the right home for a
    multiplicative factor: shrinking 1.30 and 0.77 (reciprocals) by the same weight keeps them
    reciprocal, which shrinking in linear space does not.

    `n_eff` is the BINDING side of the ratio — `min(home_pa, road_pa)` — because a factor built on 8,000
    home PA and 40 road PA is a 40-PA estimate, not an 8,000-PA one.
    """
    pf = pd.to_numeric(pd.Series(pf_raw), errors="coerce").to_numpy(float)
    n = pd.to_numeric(pd.Series(n_eff), errors="coerce").fillna(0.0).to_numpy(float)
    w = np.divide(n, n + float(pseudo_pa), out=np.zeros_like(n), where=(n + pseudo_pa) > 0)
    ok = np.isfinite(pf) & (pf > 0)
    log_pf = np.where(ok, np.log(np.where(ok, pf, 1.0)), 0.0)
    out = np.exp(w * log_pf)
    lo, hi = clamp
    return np.clip(out, lo, hi)


# ── The REDUCED bucket representation ──────────────────────────────────────────────────
# A park bucket only ever needs the numerator/denominator of each rate, not all 12 box columns — and
# carrying 8 numbers per side instead of 24 is what keeps the LEAVE-ONE-PLAYER-OUT table (one row per
# player × park × season, ~1M rows) a tractable pandas frame instead of a half-gigabyte one. The
# subtraction that makes LOO work is exact in this representation: a rate over "bucket minus player" is
# `(num_bucket − num_player) / (den_bucket − den_player)`.
REDUCED_FIELDS: tuple[str, ...] = ("pa", "ab", "so", "bb", "h", "tb", "woba_num", "woba_den")

# metric → (numerator field, denominator field). ONE table drives the SQL emitter, the pandas reducer
# and the rate computation, so the three can never drift apart.
_RATE_PARTS: dict[str, tuple[str, str]] = {
    "woba": ("woba_num", "woba_den"),
    "k_pct": ("so", "pa"),
    "bb_pct": ("bb", "pa"),
    "iso": ("_tb_minus_h", "ab"),
}


def woba_numerator_sql(c: str = "") -> str:
    """The wOBA numerator as a SQL sum-expression, GENERATED from `milb_mle._WOBA_W`.

    The park-factor buckets are summed in DuckDB (a 4.6M-row scan we are not pulling into pandas), so the
    wOBA weights necessarily appear in SQL. Emitting that SQL *from the Python constant* keeps the single
    formula home intact — the weights cannot drift between the park factor and the player's own rate.
    A test asserts this expression reproduces `compute_woba_from_counts` exactly.
    """
    from betting_ml.scripts.milb_mle.milb_mle import _WOBA_W

    w = _WOBA_W
    b1 = f"greatest(coalesce({c}bat_hits,0) - coalesce({c}bat_doubles,0) - coalesce({c}bat_triples,0) - coalesce({c}bat_home_runs,0), 0)"
    ubb = f"greatest(coalesce({c}bat_walks,0) - coalesce({c}bat_intentional_walks,0), 0)"
    return (
        f"{w['ubb']} * {ubb} + {w['hbp']} * coalesce({c}bat_hit_by_pitch,0) + {w['b1']} * {b1} "
        f"+ {w['b2']} * coalesce({c}bat_doubles,0) + {w['b3']} * coalesce({c}bat_triples,0) "
        f"+ {w['hr']} * coalesce({c}bat_home_runs,0)"
    )


def reduced_aggregate_sql(prefix: str, c: str = "") -> str:
    """`sum(...) as <prefix>_<field>` for every REDUCED_FIELD — the bucket aggregation, one place."""
    def s(expr: str, name: str) -> str:
        return f"sum({expr}) as {prefix}_{name}"

    return ",\n           ".join([
        s(f"coalesce({c}bat_plate_appearances,0)", "pa"),
        s(f"coalesce({c}bat_at_bats,0)", "ab"),
        s(f"coalesce({c}bat_strike_outs,0)", "so"),
        s(f"coalesce({c}bat_walks,0)", "bb"),
        s(f"coalesce({c}bat_hits,0)", "h"),
        s(f"coalesce({c}bat_total_bases,0)", "tb"),
        s(woba_numerator_sql(c), "woba_num"),
        s(f"coalesce({c}bat_at_bats,0) + greatest(coalesce({c}bat_walks,0) - coalesce({c}bat_intentional_walks,0),0) "
          f"+ coalesce({c}bat_sac_flies,0) + coalesce({c}bat_hit_by_pitch,0)", "woba_den"),
    ])


def reduced_from_counts(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """The pandas twin of `reduced_aggregate_sql` — full `bat_*` counts → the 8 reduced fields.

    Exists so the fast gate can prove the reduced representation reproduces
    `compute_rate_metrics_from_counts` exactly, without touching S3.
    """
    def c(name: str) -> np.ndarray:
        return pd.to_numeric(df.get(name), errors="coerce").fillna(0.0).to_numpy(float)

    from betting_ml.scripts.milb_mle.milb_mle import _WOBA_W

    ab, h = c("bat_at_bats"), c("bat_hits")
    dbl, tpl, hr = c("bat_doubles"), c("bat_triples"), c("bat_home_runs")
    bb, ibb, hbp, sf = c("bat_walks"), c("bat_intentional_walks"), c("bat_hit_by_pitch"), c("bat_sac_flies")
    b1, ubb = np.maximum(h - dbl - tpl - hr, 0.0), np.maximum(bb - ibb, 0.0)
    out = pd.DataFrame(index=df.index)
    out[f"{prefix}_pa"] = c("bat_plate_appearances")
    out[f"{prefix}_ab"] = ab
    out[f"{prefix}_so"] = c("bat_strike_outs")
    out[f"{prefix}_bb"] = bb
    out[f"{prefix}_h"] = h
    out[f"{prefix}_tb"] = c("bat_total_bases")
    out[f"{prefix}_woba_num"] = (_WOBA_W["ubb"] * ubb + _WOBA_W["hbp"] * hbp + _WOBA_W["b1"] * b1
                                 + _WOBA_W["b2"] * dbl + _WOBA_W["b3"] * tpl + _WOBA_W["hr"] * hr)
    out[f"{prefix}_woba_den"] = ab + ubb + sf + hbp
    return out


def rates_from_reduced(df: pd.DataFrame, prefix: str,
                       metrics: tuple[str, ...] = PF_METRICS) -> dict[str, np.ndarray]:
    """The four rates from a reduced bucket (`<prefix>_pa`, `<prefix>_so`, …). NaN where the denominator
    is non-positive — a bucket with no denominator has no rate, it does not have rate 0."""
    def f(name: str) -> np.ndarray:
        if name == "_tb_minus_h":
            return (pd.to_numeric(df[f"{prefix}_tb"], errors="coerce").fillna(0.0).to_numpy(float)
                    - pd.to_numeric(df[f"{prefix}_h"], errors="coerce").fillna(0.0).to_numpy(float))
        return pd.to_numeric(df[f"{prefix}_{name}"], errors="coerce").fillna(0.0).to_numpy(float)

    out: dict[str, np.ndarray] = {}
    for m in metrics:
        num_f, den_f = _RATE_PARTS[m]
        num, den = f(num_f), f(den_f)
        out[m] = np.divide(num, den, out=np.full_like(den, np.nan), where=den > 0)
    return out


def park_factors_from_buckets(
    buckets: pd.DataFrame,
    metrics: tuple[str, ...] = PF_METRICS,
    pseudo_pa: float = DEFAULT_PF_PSEUDO_PA,
    clamp: tuple[float, float] = PF_CLAMP,
    home_prefix: str = "h",
    road_prefix: str = "r",
) -> pd.DataFrame:
    """Raw → shrunk park factors from window-summed HOME and ROAD reduced buckets.

    `buckets` carries, per bucket key: the window-summed reduced aggregates over every batter-row in the
    park team's HOME games (`h_*`) and over every batter-row in its ROAD games (`r_*`). Attaches
    `pf_<metric>` (shrunk + clamped), the raw factor, and the effective sample the shrink used.
    """
    out = buckets.copy().reset_index(drop=True)
    if out.empty:
        for m in metrics:
            out[f"pf_{m}"] = pd.Series(dtype=float)
            out[f"pf_{m}_raw"] = pd.Series(dtype=float)
        out["pf_n_eff_pa"] = pd.Series(dtype=float)
        return out

    h_rates = rates_from_reduced(out, home_prefix, metrics)
    r_rates = rates_from_reduced(out, road_prefix, metrics)
    n_eff = np.minimum(
        pd.to_numeric(out[f"{home_prefix}_pa"], errors="coerce").fillna(0.0).to_numpy(float),
        pd.to_numeric(out[f"{road_prefix}_pa"], errors="coerce").fillna(0.0).to_numpy(float),
    )
    out["pf_n_eff_pa"] = n_eff
    for m in metrics:
        h, r = h_rates[m], r_rates[m]
        raw = np.divide(h, r, out=np.full_like(h, np.nan), where=np.isfinite(r) & (r > 0))
        out[f"pf_{m}_raw"] = raw
        out[f"pf_{m}"] = shrink_log_pf(raw, n_eff, pseudo_pa, clamp)
    return out


def exposure_weighted_pf(
    exposure: pd.DataFrame,
    metrics: tuple[str, ...] = PF_METRICS,
    pf_prefix: str = "pf_",
    weight_col: str = "pa",
    keys: tuple[str, ...] = ("player_id", "level"),
) -> pd.DataFrame:
    """Collapse a per-(player, park-season) exposure table to ONE factor per (player, level).

    ⭐ **This is the repo's advantage over the memo's prescription.** The research memo recommends the
    classic **half-weight** multiplier (`(1 + pf_home)/2`) because BA's published park-factor tables
    arrive without game logs, so "roughly half his games were at home" is the best you can do. We HAVE
    the game logs — `venue_id` is on every player-game — so we know EXACTLY how many PA each player took
    in each park and can weight by the real exposure instead of assuming it. The half-weight form is
    still carried as a pre-registered FOIL (`park="halfweight"`), because the memo's prescription
    beating our refinement would itself be a finding.

    The average is GEOMETRIC (mean of logs), which is the correct centre for a multiplicative factor.

    A park-season with NO usable factor contributes weight ZERO rather than a fabricated 1.0 — and the
    share of the player's PA that WAS covered is reported (`pf_<metric>_covered_pa_share`), so a
    thinly-covered player is visible instead of silently reading as "played in neutral parks."
    """
    out_cols = ([f"{pf_prefix}{m}_exposure" for m in metrics]
                + [f"{pf_prefix}{m}_covered_pa_share" for m in metrics] + ["pf_n_park_seasons"])
    if exposure.empty:
        return pd.DataFrame(columns=list(keys) + out_cols)

    df = exposure.copy()
    w = pd.to_numeric(df[weight_col], errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(float)
    df["_w"] = w
    agg: dict[str, str] = {"_w": "sum"}
    for m in metrics:
        pf = pd.to_numeric(df.get(f"{pf_prefix}{m}"), errors="coerce")
        ok = (pf.notna() & (pf > 0)).to_numpy(bool)
        wm = np.where(ok, w, 0.0)
        df[f"_wm_{m}"] = wm
        df[f"_wlg_{m}"] = wm * np.where(ok, np.log(pf.where(pf > 0, 1.0).to_numpy(float)), 0.0)
        agg[f"_wm_{m}"] = "sum"
        agg[f"_wlg_{m}"] = "sum"

    g = df.groupby(list(keys), dropna=False).agg(agg).reset_index()
    total_w = g["_w"].to_numpy(float)
    for m in metrics:
        den = g[f"_wm_{m}"].to_numpy(float)
        num = g[f"_wlg_{m}"].to_numpy(float)
        lg = np.divide(num, den, out=np.zeros_like(den), where=den > 0)
        g[f"{pf_prefix}{m}_exposure"] = np.where(den > 0, np.exp(lg), np.nan)
        g[f"{pf_prefix}{m}_covered_pa_share"] = np.divide(
            den, total_w, out=np.zeros_like(den), where=total_w > 0)
    counts = df.groupby(list(keys), dropna=False).size().rename("pf_n_park_seasons").reset_index()
    g = g.merge(counts, on=list(keys), how="left")
    return g[list(keys) + out_cols]


# ══════════════════════════════════════════════════════════════════════════════════════
# The context specification — one dataclass per rung of the pre-registered ablation ladder
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ContextSpec:
    """A pre-registered rung of the SLICE-1 ablation ladder.

    Every field defaults to the **E7.3 incumbent behaviour**, so `ContextSpec()` is a byte-exact no-op —
    that identity is what makes the ladder's baseline the real incumbent rather than a re-implementation
    of it, and it is pinned by a test.
    """

    park: str = "off"                       # off | exposure | halfweight | exposure_noloo | placebo
    level_env: bool = False                 # normalise the season mix to the level's pooled baseline
    reliability: float | None = None        # multiplier on STABILIZATION_PA (None = no shrink)
    constant_reliability: bool = False      # DEGENERATE FOIL: population-mean r, no PA variation
    weight_col: str | None = None           # observation weights for the partial-pool fit (e.g. mlb_pa)

    def __post_init__(self):
        if self.park not in PARK_MODES:
            raise ValueError(f"park={self.park!r} not in {PARK_MODES}")
        if self.reliability is not None and not (self.reliability > 0):
            raise ValueError("reliability multiplier must be > 0 (or None to disable)")
        if self.constant_reliability and self.reliability is None:
            raise ValueError("constant_reliability is a foil FOR the reliability shrink — set both")

    @property
    def is_noop(self) -> bool:
        return (self.park == "off" and not self.level_env
                and self.reliability is None and self.weight_col is None)

    @property
    def label(self) -> str:
        if self.is_noop:
            return "baseline"
        bits = []
        if self.park != "off":
            bits.append(f"park:{self.park}")
        if self.level_env:
            bits.append("levelenv")
        if self.reliability is not None:
            bits.append(f"rel:{'const' if self.constant_reliability else f'{self.reliability:g}k'}")
        if self.weight_col:
            bits.append(f"w:{self.weight_col}")
        return "+".join(bits)


def _park_column(spec: ContextSpec, metric: str) -> str | None:
    """Which context column carries the factor this rung divides by."""
    return {
        "off": None,
        "exposure": f"pf_{metric}_exposure",
        "halfweight": f"pf_{metric}_halfweight",
        "exposure_noloo": f"pf_{metric}_exposure_noloo",
        "placebo": f"pf_{metric}_exposure",     # permuted at apply time, deterministic seed
    }[spec.park]


def _permute_within_level(values: pd.Series, levels: pd.Series, seed: int = PLACEBO_SEED) -> pd.Series:
    """The PLACEBO: permute factors across players WITHIN a level, deterministically.

    Within-level (not global) so the placebo keeps each level's own factor distribution — otherwise a
    "placebo" that shuffles an AAA factor onto a Single-A player is testing level mixing, not parks.
    """
    rng = np.random.default_rng(seed)
    out = values.copy()
    for lvl, idx in values.groupby(levels, dropna=False).groups.items():  # noqa: B007
        idx = pd.Index(idx)
        if len(idx) < 2:
            continue
        out.loc[idx] = values.loc[idx].to_numpy()[rng.permutation(len(idx))]
    return out


def reliability_weight(pa: np.ndarray | pd.Series, k: float) -> np.ndarray:
    """`r = PA / (PA + k)` — the fraction of an observed deviation that is SIGNAL at this sample size.

    This is the whole of the small-sample hardening: `k` is per-component (K% 60 PA vs ISO 160 PA), so
    at equal PA a power line is regressed harder than a discipline line — the measured translatability
    ordering encoded as a prior instead of asserted.
    """
    p = pd.to_numeric(pd.Series(pa), errors="coerce").fillna(0.0).clip(lower=0.0).to_numpy(float)
    k = float(k)
    return np.divide(p, p + k, out=np.zeros_like(p), where=(p + k) > 0)


def apply_context(
    pairs: pd.DataFrame,
    context: pd.DataFrame | None,
    spec: ContextSpec,
    metric: str,
    keys: tuple[str, ...] = ("player_id", "level"),
) -> pd.DataFrame:
    """Rewrite `minor_<metric>` under one rung of the ladder. Returns a COPY; `pairs` is untouched.

    Order is park → season run-environment → reliability, and it is not arbitrary: the park factor is a
    property of WHERE the PA happened, the run environment of WHEN, and the reliability shrink of HOW
    MANY — so each later step operates on a cleaner estimate of the same quantity.

    🔒 **LEAKAGE POSTURE.** Every quantity here is derived from the MiLB side ONLY — park factors from
    other players' minor-league counting stats, run environments from level-season minor aggregates,
    stabilisation points from published literature. None of them touches an MLB label, so applying the
    transform globally (rather than refitting it inside each CV fold) cannot leak the target. That is
    why the ladder can pre-transform the pairs table and leave E7.3's fold machinery untouched.

    A row with NO context (an unmatched player, a park with no usable bucket) is a documented NO-OP —
    factor 1.0, env ratio 1.0 — never dropped and never fabricated. `context_coverage` reports it.
    """
    out = pairs.copy().reset_index(drop=True)
    mcol = f"minor_{metric}"
    if mcol not in out.columns:
        raise KeyError(f"pairs has no {mcol!r} column — wrong metric or a pre-E7.3 pairs artifact")
    rate = pd.to_numeric(out[mcol], errors="coerce")
    out[f"{mcol}_raw"] = rate

    if context is not None and not context.empty:
        cols = [c for c in context.columns if c not in keys]
        ctx = context.drop_duplicates(subset=list(keys))[list(keys) + cols]
        out = out.merge(ctx, on=list(keys), how="left", suffixes=("", "_ctx"))

    n = len(out)
    applied_park = np.ones(n)
    applied_env = np.ones(n)

    # ── 1. PARK ────────────────────────────────────────────────────────────────────────
    pcol = _park_column(spec, metric)
    if pcol is not None:
        if spec.park == "halfweight" and pcol not in out.columns:
            # the memo's prescription verbatim, derived from the player's PRIMARY home park:
            # (1 + PF_home)/2 — "a player takes about half his PA at home, and his road parks average
            # out to neutral." We only fall back to it because the builder stores `pf_<m>_home`; the
            # exposure arm above needs no such assumption because we HAVE the per-game venue.
            home = pd.to_numeric(out.get(f"pf_{metric}_home"), errors="coerce") \
                if f"pf_{metric}_home" in out.columns else pd.Series(np.nan, index=out.index)
            pf = (1.0 + home) / 2.0
        elif pcol in out.columns:
            pf = pd.to_numeric(out[pcol], errors="coerce")
        else:
            pf = pd.Series(np.nan, index=out.index)
        if spec.park == "placebo":
            pf = _permute_within_level(pf, out["level"])
        pf = pf.where(pf.notna() & (pf > 0), 1.0)
        applied_park = pf.to_numpy(float)
        rate = rate / applied_park

    # ── 2. LEVEL × SEASON RUN ENVIRONMENT ─────────────────────────────────────────────
    if spec.level_env:
        env_p = pd.to_numeric(out.get(f"env_{metric}"), errors="coerce")
        env_l = pd.to_numeric(out.get(f"env_level_{metric}"), errors="coerce")
        ratio = (env_l / env_p).where(env_p.notna() & (env_p > 0) & env_l.notna() & (env_l > 0), 1.0)
        applied_env = ratio.to_numpy(float)
        rate = rate * applied_env

    # ── 3. RELIABILITY (per-component small-sample shrink) ────────────────────────────
    applied_r = np.ones(n)
    if spec.reliability is not None:
        k = spec.reliability * STABILIZATION_PA.get(metric, 200.0)
        pa = pd.to_numeric(out.get("minor_pa"), errors="coerce").fillna(0.0)
        r = reliability_weight(pa, k)
        if spec.constant_reliability:
            # DEGENERATE FOIL — one r for everyone (the PA-weighted population mean). If this ties the
            # PA-varying arm, the "hardening" was a global slope rescale the regression already had.
            wsum = float(pa.sum())
            r_bar = float(np.average(r, weights=pa)) if wsum > 0 else float(np.mean(r))
            r = np.full(n, r_bar)
        # shrink toward the player's own LEVEL baseline (post-park, post-env, so the anchor lives in the
        # same adjusted space as the value being shrunk)
        anchor = pd.to_numeric(out.get(f"env_level_{metric}"), errors="coerce")
        if anchor.isna().all():
            anchor = pd.Series(np.full(n, float(rate.mean(skipna=True))), index=out.index)
        anchor = anchor.fillna(float(rate.mean(skipna=True)) if rate.notna().any() else 0.0)
        rate = anchor + r * (rate - anchor)
        applied_r = r

    lo, hi = _RATE_BOUNDS.get(metric, (-np.inf, np.inf))
    out[mcol] = rate.clip(lower=lo, upper=hi)
    out[f"{mcol}_park_factor"] = applied_park
    out[f"{mcol}_env_ratio"] = applied_env
    out[f"{mcol}_reliability"] = applied_r
    return out


def context_coverage(adjusted: pd.DataFrame, metric: str, spec: ContextSpec) -> dict:
    """How much of the population the rung actually TOUCHED — a context join that silently matches
    nothing produces a byte-identical no-op arm that reads as an honest null (the repo's silent-empty
    class, one rung down). Reported beside every arm's score."""
    mcol = f"minor_{metric}"
    pf = adjusted.get(f"{mcol}_park_factor")
    env = adjusted.get(f"{mcol}_env_ratio")
    n = len(adjusted)
    moved = np.zeros(n, dtype=bool)
    if pf is not None:
        moved |= (np.abs(pf.to_numpy(float) - 1.0) > 1e-9)
    if env is not None:
        moved |= (np.abs(env.to_numpy(float) - 1.0) > 1e-9)
    if spec.reliability is not None:
        moved |= (np.abs(adjusted[f"{mcol}_reliability"].to_numpy(float) - 1.0) > 1e-9)
    raw = pd.to_numeric(adjusted[f"{mcol}_raw"], errors="coerce")
    adj = pd.to_numeric(adjusted[mcol], errors="coerce")
    delta = (adj - raw).abs()
    return {
        "n_rows": int(n),
        "pct_rows_moved": round(100.0 * float(moved.mean()), 2) if n else 0.0,
        "mean_abs_delta": float(delta.mean(skipna=True)) if n else 0.0,
        "max_abs_delta": float(delta.max(skipna=True)) if n else 0.0,
        "pf_p05": float(np.nanpercentile(pf, 5)) if pf is not None and n else 1.0,
        "pf_p95": float(np.nanpercentile(pf, 95)) if pf is not None and n else 1.0,
    }
