"""ncaaf_game_predictor.py — NCAAF-P1.4 serving + P1.5-facing predictive interface.

WHAT THIS IS
------------
The callable wrapper around the P1.4 served joint distribution (`NcaafGameDistributionParams` +
the strength-prior mean). It turns a matchup into a posterior-predictive (margin, total) sample and
the three market probabilities — AND, critically, it exposes the interface a downstream
**season-simulation (P1.5: National-Championship / conference-title futures)** needs WITHOUT the
game model painting itself into a corner.

⭐ THE STRENGTH-DECOMPOSITION CONTRACT (the load-bearing bit for honest futures)
------------------------------------------------------------------------------
The posterior-predictive game width DECOMPOSES the per-game variance into two independent parts:

    σ_g²  =  σ₀²                      (irreducible game noise — a perfect strength model still
                                       can't predict a given Saturday)
          +  k²·(home_sd² + away_sd²) (the TEAM-STRENGTH POSTERIOR uncertainty, propagated)

A season sim draws each team's TRUE strength ONCE per simulated season (from its P1.2 posterior)
and reuses it across that team's whole schedule — that is what makes a futures number honest (a
team that is genuinely a coin-flip to be good must have its uncertainty correlated across all 12
games, not re-rolled and washed out each week). So the sim MUST NOT also add the k²·strength_var
term per game — that would DOUBLE-COUNT the strength uncertainty. Hence two modes:

  * `sample_matchup(..., fixed_strength=False)` — the FULL posterior-predictive for a STANDALONE
    game (both sources of uncertainty): σ_g = √(σ₀² + k²·strength_var). This is the serving path
    (a single game's honest distribution).
  * `sample_matchup(..., fixed_strength=True)` — GAME-NOISE ONLY: σ_g = σ₀. Use this INSIDE the
    season sim, AFTER you have drawn the teams' strengths for that simulated season (which is what
    supplies the μ). The strength uncertainty is already in the drawn μ; adding it again is the
    double-count.

WHERE THE STRENGTH POSTERIORS LIVE (P1.5 draws from here)
--------------------------------------------------------
The team strength POSTERIORS (mean + sd, not just a point) are the P1.2 mart
`ncaaf_team_strength_week` — per (season, team, as_of_week): `strength_margin` (mean),
`strength_margin_sd` (posterior sd), and the `strength_offense` / `strength_defense` split for the
total. The sim reads a team's pre-season (week-1) posterior, draws `strength ~ Normal(strength_margin,
strength_margin_sd)` once, maps the two drawn strengths → (μ_margin, μ_total) via the P1.4 mean
model, then calls `sample_matchup(..., fixed_strength=True)` per game. This module does NOT build the
sim (that's P1.5) — it provides the pieces so P1.5 is a thin Monte-Carlo on top, not a re-derivation.

HONEST FRAME: market-blind product value, `best_alpha = 0`. A wide early-season interval is the
CORRECT answer for a thin-sample matchup, not a weakness.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    NcaafGameDistributionParams,
    derive_markets,
    draw_joint,
    prob_over,
    sample_joint_normal,
    strength_posterior_sigma,
)

# The bivariate-Normal forms (gaussian / native / strength_posterior) all serve through the
# per-game σ path; student_t / count keep their own shape.
_NORMAL_FORMS = ("gaussian", "native", "strength_posterior")


_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
#: newest first — a post-P1.4 contract (NCAAF-P2.1 S1-serve) writes v2 beside the frozen v1.
SERVED_DISPERSION_CANDIDATES: tuple[str, ...] = (
    "ncaaf_game_distribution_v2.json", "ncaaf_game_distribution_v1.json")
SERVED_MEAN_FILENAME = "ncaaf_game_mean_v2.json"


def load_params(path: str | Path) -> NcaafGameDistributionParams:
    """Load a served `ncaaf_game_distribution_v*.json` written by the bake-off finalize stage."""
    return NcaafGameDistributionParams.from_dict(json.loads(Path(path).read_text()))


def resolve_served_dispersion(artifact_dir: str | Path = _ARTIFACT_DIR) -> Path:
    """The dispersion artifact that actually serves — v2 (a post-P1.4 contract) if present, else v1.

    ⭐ An explicit, ORDERED preference with the chosen path returned to the caller so it can be
    LOGGED. The prospect-board regression was a silent source-precedence pick; this one is
    auditable, and it prefers the NEWER schema rather than a name that a later build may stop
    writing.
    """
    d = Path(artifact_dir)
    for name in SERVED_DISPERSION_CANDIDATES:
        if (d / name).exists():
            return d / name
    raise FileNotFoundError(
        f"no served dispersion artifact in {d} (looked for {list(SERVED_DISPERSION_CANDIDATES)}) — "
        "run `bakeoff_ncaaf_game --stage finalize`.")


def load_served_pair(artifact_dir: str | Path = _ARTIFACT_DIR):
    """Load (dispersion, mean, dispersion_path) and REFUSE a mismatched pair.

    σ is calibrated on the OOS residuals of one (learner, contract) and μ is that config's refit;
    pairing a dispersion with a mean fitted on a DIFFERENT contract is exactly the E7.9 train/serve
    mismatch the S1 read-out flagged (a σ fitted on pace residuals served against a pace-free μ),
    so it raises rather than degrading quietly. A mean artifact that is simply ABSENT is the
    pre-S1-serve state and returns `None` — the caller must say so in its own output.
    """
    from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_mean import NcaafGameMeanParams

    disp_path = resolve_served_dispersion(artifact_dir)
    disp = load_params(disp_path)
    mean_path = Path(artifact_dir) / SERVED_MEAN_FILENAME
    if not mean_path.exists():
        return disp, None, disp_path
    mean = NcaafGameMeanParams.load(mean_path)
    if mean.contract != disp.contract or mean.learner != disp.learner:
        raise ValueError(
            f"served artifacts disagree: dispersion {disp_path.name} was fitted on "
            f"{disp.learner}/{disp.contract} but the mean artifact carries "
            f"{mean.learner}/{mean.contract}. Serving that pair is an E7.9 train/serve mismatch — "
            "re-run `--stage finalize` so both are written together.")
    return disp, mean, disp_path


def matchup_sigma(
    params: NcaafGameDistributionParams, strength_var: np.ndarray | float,
    *, fixed_strength: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-game predictive σ (margin, total) for a matchup under the served form.

    `strength_var` = home_strength_margin_sd² + away_strength_margin_sd² for the matchup (0 or a
    scalar is fine for a non-posterior form). `fixed_strength=True` returns the irreducible σ₀
    ALONE (the season-sim mode — the strength uncertainty is already in μ; see the module
    docstring's double-count warning)."""
    sv = np.atleast_1d(np.asarray(strength_var, dtype=float))
    if params.form == "strength_posterior":
        if fixed_strength:
            return (np.full_like(sv, params.sigma0_margin, dtype=float),
                    np.full_like(sv, params.sigma0_total, dtype=float))
        return (strength_posterior_sigma(params.sigma0_margin, params.k_margin, sv),
                strength_posterior_sigma(params.sigma0_total, params.k_total, sv))
    # homoscedastic forms: one served σ (fixed_strength is a no-op — there is no separable term)
    return (np.full_like(sv, params.sigma_margin, dtype=float),
            np.full_like(sv, params.sigma_total, dtype=float))


def sample_matchup(
    params: NcaafGameDistributionParams,
    mu_margin: np.ndarray | float, mu_total: np.ndarray | float, strength_var: np.ndarray | float,
    rng: np.random.Generator, *, n_draws: int = 10_000, fixed_strength: bool = False,
) -> dict[str, np.ndarray]:
    """Sample the joint (margin, total) predictive for one or many matchups → the market arrays.

    `mu_margin`/`mu_total` = the P1.4 mean-model point predictions (home−away, home+away). Returns
    `derive_markets(...)`: {margin, total, home_win} sample arrays (n_games, n_draws). See
    `market_probabilities` for the read-off. `fixed_strength=True` is the season-sim mode.
    """
    mu_m = np.atleast_1d(np.asarray(mu_margin, dtype=float))
    mu_t = np.atleast_1d(np.asarray(mu_total, dtype=float))
    sv = np.broadcast_to(np.asarray(strength_var, dtype=float), mu_m.shape)
    if params.form in _NORMAL_FORMS:
        sm, st = matchup_sigma(params, sv, fixed_strength=fixed_strength)
        m_s, t_s = sample_joint_normal(mu_m, mu_t, sm, st, params.rho, rng, n_draws=n_draws)
    else:
        # student_t / count keep their served (homoscedastic) shape; fixed_strength is a no-op
        # here (no separable strength term), which the sim should note.
        m_s, t_s = draw_joint(params.form, mu_m, mu_t, params.dispersion(), rng, n_draws=n_draws)
    return derive_markets(m_s, t_s)


def market_probabilities(
    markets: dict[str, np.ndarray], *, home_spread: float | None = None, total_line: float | None = None,
) -> dict[str, float | None]:
    """The three market probabilities off a sampled matchup (per-game if the sample is 2-D).

    H2H  = P(margin > 0);  spread = P(home covers) = P(margin > −home_spread);  total =
    P(total > total_line). `home_spread` is the book's home number (favourite negative), so the
    home team covers when margin > −home_spread.
    """
    margin, total = markets["margin"], markets["total"]
    single = margin.ndim == 1 or (margin.ndim == 2 and margin.shape[0] == 1)
    m = margin.ravel() if single else margin
    t = total.ravel() if single else total

    def _p(sample, thr):
        return float((sample > thr).mean()) if single else (sample > thr).mean(axis=1)

    out: dict[str, float | None] = {"p_home_win": _p(m, 0.0)}
    out["p_home_cover"] = _p(m, -home_spread) if home_spread is not None else None
    out["p_over"] = _p(t, total_line) if total_line is not None else None
    return out
