"""opportunity_allocation.py — NF-W5: opportunity allocation on the JOINT gate (pure).

THE STORY IN ONE PARAGRAPH. Both predecessor LEVEL channels are measured inert against the
injury-aware champion on the marginal per-player CRPS gate (NF-W3: environment, ceiling 2–3% of
champion CRPS; NF-W4: availability, ceiling 8–28% but the pregame-forecastable slice already
priced in). NF-W5 measures the one place the assembled projection can still gain — the
CORRELATION structure a shared team play budget creates (teammates share one play budget; shares
sum to 1; opportunity is a COMPOSITIONAL joint object) — which a marginal gate is structurally
blind to and which is the v3 doc's own justification for the NF-W8 simulator (§9/§9.1/§10.1A).
⭐ The story's deliverable is a DECISION: is the joint-allocation ceiling large enough to justify
NF-W8, yes or no.

THE SKLAR SPLIT. A joint predictive = per-player marginals ⊗ a copula. The marginals are PINNED
to the injury-aware champion (the NF-W2b/W2d certified per-position winners, refit per fold);
every construction in the field differs ONLY in the copula, so the dead marginal channel is
excluded BY CONSTRUCTION and a marginal-identity guard asserts it numerically every fold.

⭐ ORACLE-FIRST (the NF-W3/W4 transferable discipline, on the joint metric): per-form peeking
oracles (each parametrized copula form re-fit on the TEST fold's realized PITs; the empirical
form leave-one-out) are scored before any arm is judged. The CEILING = the best peeking form's
improvement over `independence` on the primary metric. A max over 5 peeking forms is upward-
biased by selection — the bias direction FAVORS a YES, so a NO under this estimator is
CONSERVATIVE (declared in advance).

THE PRE-REGISTERED DECISION RULE (narrative copy: ablation_results/nf_w5_preregistration.md):
`ceiling_stat_ok` = CI95 excludes zero ∧ fold clause (6/8) ∧ BH binding. Bands on
`ceiling_pct` = 100·ceiling/independence: <2% → NO (the §9 simulator premise fails at the
allocation channel); 2–5% → MARGINAL (PM decision); ≥5% → YES. Not stat_ok → NO regardless of
magnitude.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: this module promotes nothing and serves
nothing; serving is NF-W8 / NF-C6 Ph2.

Pure module — no lake IO. The runner is `run_nf_w5_opportunity_allocation.py`.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W5"
#: The joint selection metric — sample-based CRPS of the team-week TOTAL (roster-grain lineup
#: CRPS). Correlations move the distribution of a sum; marginals alone cannot.
PRIMARY_METRIC = "team_total_crps"
#: §12.7 dependence diagnostics — reported for mechanism attribution, NEVER select.
CO_METRICS: tuple[str, ...] = ("energy_score", "variogram_score")
ALL_METRICS: tuple[str, ...] = (PRIMARY_METRIC, *CO_METRICS)
VARIOGRAM_P = 0.5
#: Monte-Carlo draws per construction per team-week, under common random numbers.
N_SAMPLES = 512
_SEED = 20260811
#: A team-week with fewer than 2 modeled players carries no joint structure — excluded + COUNTED.
MIN_TEAM_K = 2
#: Role caps for the nonparametric empirical-copula arm (deeper players draw independently).
ROLE_CAPS: dict[str, int] = {"QB": 2, "RB": 4, "WR": 5, "TE": 3}
#: The marginal-identity tolerance: pooled per-player sample-CRPS spread across constructions
#: must sit inside MC noise (identical marginals by construction — §10.1A made structural).
MARGINAL_IDENTITY_TOL = 0.02
#: The NF-W8 decision bands on ceiling_pct (NO < 2.0 ≤ MARGINAL < 5.0 ≤ YES), calibrated against
#: the program's own precedents (NF-W3's 2–3% recorded as "cannot justify the chain alone";
#: NF-W4's 8–28% as the largest single error source).
CEILING_BANDS: tuple[float, float] = (2.0, 5.0)

TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE

#: Foils (never shippable; the best foil binds). `independence` is the incumbent — what the
#: marginally-assembled champion serves today. `constant_rho` is the climatology-of-dependence:
#: one pooled same-team correlation (the matched NON-learned foil, NF-D10 (g)).
FOILS: tuple[str, ...] = ("independence", "constant_rho")
#: 4 structurally different copula classes (§0.5): shared-latent factor (§9 z_g) · full
#: position-pair Gaussian (§10.1A empirical covariance; the only Gaussian form expressing
#: NEGATIVE within-position competition) · compositional Dirichlet allocation (§5) ·
#: nonparametric empirical copula by role cell.
REAL_ARMS: tuple[str, ...] = (
    "gauss_pos_factor", "gauss_pos_pairwise", "dirichlet_alloc", "empirical_role_resample",
)
#: Forms with fit parameters — each gets a peeking oracle (NF-D16 (g‴)). `independence` has no
#: parameters: its peeking version is itself (declared, not silently absent).
PARAMETRIZED_FORMS: tuple[str, ...] = (
    "constant_rho", "gauss_pos_factor", "gauss_pos_pairwise", "dirichlet_alloc",
    "empirical_role_resample",
)
#: Diagnostic anchors — EXCLUDED from the PBO matrix and the DSR trial field (MH2.1 (a)).
#: `comonotonic` = the maximal-dependence degenerate (must LOSE; `independence` is the
#: zero-dependence end, so the pair brackets the dependence axis two-sidedly — NF1.7 (c)).
#: `shuffled_teams` = the permutation anchor (pairwise form fit on team-shuffled train PITs).
BASE_ANCHORS: tuple[str, ...] = ("comonotonic", "shuffled_teams")

oracle_of = GE.oracle_of
matched_n_of = GE.matched_n_of


def anchors() -> tuple[str, ...]:
    return (*BASE_ANCHORS,
            *(oracle_of(f) for f in PARAMETRIZED_FORMS),
            *(matched_n_of(a) for a in REAL_ARMS))


def all_labels() -> tuple[str, ...]:
    return (*REAL_ARMS, *FOILS, *anchors())


def eligible_labels() -> list[str]:
    """The set the selection actually searched — real arms + foils (NF1.8: a deflation statistic
    over a field containing its own anchors measures the anchors)."""
    return [*REAL_ARMS, *FOILS]


#: ⭐ TWO pre-registered multiplicity families; own-family AND pooled computed, the STRICTER
#: binds (MH2 (a)).
FDR_FAMILIES: dict[str, tuple[str, ...]] = {
    "arm": ("joint_alloc_arm",),
    "ceiling": ("joint_alloc_ceiling",),
}

# Shared verdict / reporting helpers — IMPORTED, never re-typed (NF-W2d discipline).
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
flag_unsafe_field_shrink = GE.flag_unsafe_field_shrink
gate_sensitivity = GE.gate_sensitivity
hand_classify_refusal = GE.hand_classify_refusal


# ── PIT and marginal machinery (the 39-level grid identity) ─────────────────────────────────────
def randomized_pit(qmat: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Randomized PIT of realized outcomes under the 39-level quantile bank.

    For y inside a grid cell the PIT is uniform between the adjacent levels; across an atom (a
    run of equal quantiles, e.g. the zero atom) it is uniform over the atom's level span. Tails
    map to [0, 0.025] / [0.975, 1]. The same grid carries sampling (`x_from_uniforms`), so PIT
    and inverse-PIT are two reads of one object."""
    q = np.sort(np.asarray(qmat, dtype=float), axis=1)
    yv = np.asarray(y, dtype=float)[:, None]
    levels = WP.Q_LEVELS
    n_levels = len(levels)
    lo_ct = (q < yv).sum(axis=1)
    hi_ct = (q <= yv).sum(axis=1)
    lo = np.where(lo_ct == 0, 0.0, levels[np.clip(lo_ct - 1, 0, n_levels - 1)])
    hi = np.where(hi_ct >= n_levels, 1.0, levels[np.clip(hi_ct, 0, n_levels - 1)])
    u = lo + rng.random(len(yv)) * np.maximum(hi - lo, 0.0)
    return np.clip(u, 1e-6, 1 - 1e-6)


def x_from_uniforms(q_sorted: np.ndarray, u_col: np.ndarray) -> np.ndarray:
    """Inverse CDF on the 39-level grid, tails clamped at q025/q975 — IDENTICALLY for every
    construction, so paired comparisons are unaffected by the clamp."""
    return np.interp(u_col, WP.Q_LEVELS, q_sorted)


def pit_frame(df: pd.DataFrame, qmat: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    """The copula-fitting substrate: one row per player-week with its randomized PIT, its normal
    score, and the champion predictive mean (the role-rank key)."""
    from scipy.stats import norm
    u = randomized_pit(qmat, df["fantasy_points"].to_numpy(dtype=float), rng)
    return pd.DataFrame({
        "team": df["team"].astype(str).to_numpy(),
        "gw": df["gw"].to_numpy(dtype=int),
        "position": df["position"].astype(str).to_numpy(),
        "u": u,
        "z": norm.ppf(u),
        "champ_mean": np.sort(np.asarray(qmat, dtype=float), axis=1).mean(axis=1),
    })


# ── The joint object: team-week groups (row-conservation asserted, exclusions counted) ──────────
def build_team_weeks(test: pd.DataFrame, min_k: int = MIN_TEAM_K) -> tuple[list[dict], dict]:
    posn = pd.Series(np.arange(len(test)), index=test.index)
    groups: list[dict] = []
    excl = {"n_groups_excluded": 0, "n_rows_excluded": 0}
    for (team, gw), sub in test.groupby(["team", "gw"], sort=True):
        rows = posn.loc[sub.index].to_numpy()
        if len(rows) < min_k:
            excl["n_groups_excluded"] += 1
            excl["n_rows_excluded"] += int(len(rows))
            continue
        groups.append({"team": str(team), "gw": int(gw), "rows": rows,
                       "positions": sub["position"].astype(str).to_numpy()})
    kept = int(sum(len(g["rows"]) for g in groups))
    if kept + excl["n_rows_excluded"] != len(test):
        raise ValueError(
            f"team-week grouping lost rows: {kept} scored + {excl['n_rows_excluded']} excluded "
            f"!= {len(test)} test rows — a joint gate scored on a silently different population "
            f"is not a comparison (NF-W3 row-conservation rule)"
        )
    excl.update({"n_groups": len(groups), "n_rows_scored": kept, "n_rows_total": int(len(test))})
    return groups, excl


# ── Pair-correlation moments (MoM over normal scores; cluster = team-week) ──────────────────────
def pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


_POS_CODE: dict[str, int] = {p: i for i, p in enumerate(WP.POSITIONS)}


def fit_pair_correlations(pf: pd.DataFrame) -> dict:
    """Pooled same-team pairwise moments E[z_i z_j] by position pair (within-position pairs
    included). PITs are marginally ~U(0,1) by construction, so the mean product IS the MoM
    Gaussian-copula correlation. Cluster statistics (per team-week) are kept for the report."""
    n_pos = len(WP.POSITIONS)
    n_cells = n_pos * n_pos
    sums = np.zeros(n_cells)
    counts = np.zeros(n_cells, dtype=int)
    group_sums: dict[int, list[float]] = {i: [] for i in range(n_cells)}
    group_ns: dict[int, list[int]] = {i: [] for i in range(n_cells)}
    code_all = pf["position"].map(_POS_CODE)
    if code_all.isna().any():
        raise ValueError(f"unknown positions in the PIT frame: "
                         f"{sorted(pf.loc[code_all.isna(), 'position'].unique())}")
    work = pf.assign(_pc=code_all.astype(int))
    for (_, _), sub in work.groupby(["team", "gw"], sort=False):
        k = len(sub)
        if k < 2:
            continue
        z = sub["z"].to_numpy(dtype=float)
        code = sub["_pc"].to_numpy()
        iu, ju = np.triu_indices(k, 1)
        prods = z[iu] * z[ju]
        a = np.minimum(code[iu], code[ju])
        b = np.maximum(code[iu], code[ju])
        pid = a * n_pos + b
        s = np.bincount(pid, weights=prods, minlength=n_cells)
        n = np.bincount(pid, minlength=n_cells)
        sums += s
        counts += n
        for i in np.nonzero(n)[0]:
            group_sums[i].append(float(s[i]))
            group_ns[i].append(int(n[i]))
    out: dict[tuple[str, str], dict] = {}
    for i in range(n_cells):
        if not counts[i]:
            continue
        key = pair_key(WP.POSITIONS[i // n_pos], WP.POSITIONS[i % n_pos])
        r = float(np.clip(sums[i] / counts[i], -0.9, 0.9))
        gs = np.asarray(group_sums[i])
        gn = np.asarray(group_ns[i], dtype=float)
        se = float(np.sqrt(np.sum((gs - r * gn) ** 2)) / counts[i])
        out[key] = {"r": r, "n_pairs": int(counts[i]), "n_groups": int(len(gs)),
                    "cluster_se": se}
    return out


def fit_constant_rho(paircorr: dict) -> float:
    """The climatology-of-dependence foil: ONE pooled same-team correlation. Clipped to [0, 0.9]
    — an equicorrelation matrix with negative rho is non-PSD at roster K (declared; the pairwise
    arm is the form that carries negative values)."""
    tot = sum(d["r"] * d["n_pairs"] for d in paircorr.values())
    n = sum(d["n_pairs"] for d in paircorr.values())
    return float(np.clip(tot / n, 0.0, 0.9)) if n else 0.0


def fit_factor_loadings(paircorr: dict) -> dict[str, float]:
    """One-factor loadings per position: minimize Σ n_ab·(r_ab − λ_a λ_b)² (same-position pairs
    contribute r_aa ≈ λ_a²). Bounded [0, 0.95] — a factor model cannot express negative
    within-position competition (declared; that is WHY the field carries multiple classes)."""
    from scipy.optimize import least_squares
    positions = list(WP.POSITIONS)
    keys = [k for k in paircorr if k[0] in positions and k[1] in positions]
    if not keys:
        return {p: 0.0 for p in positions}

    def resid(lam: np.ndarray) -> list[float]:
        lam_of = dict(zip(positions, lam))
        return [float(np.sqrt(paircorr[k]["n_pairs"]))
                * (paircorr[k]["r"] - lam_of[k[0]] * lam_of[k[1]]) for k in keys]

    res = least_squares(resid, x0=np.full(len(positions), 0.2),
                        bounds=(0.0, 0.95), max_nfev=200)
    return {p: float(v) for p, v in zip(positions, res.x)}


def nearest_psd_corr(R: np.ndarray, floor: float = 1e-4) -> np.ndarray:
    w, V = np.linalg.eigh((R + R.T) / 2.0)
    w = np.clip(w, floor, None)
    A = (V * w) @ V.T
    d = np.sqrt(np.diag(A))
    A = A / np.outer(d, d)
    return (A + A.T) / 2.0


def build_team_corr(pos_vec: np.ndarray, paircorr: dict) -> np.ndarray:
    K = len(pos_vec)
    R = np.eye(K)
    for i in range(K):
        for j in range(i + 1, K):
            R[i, j] = R[j, i] = paircorr.get(pair_key(pos_vec[i], pos_vec[j]), {"r": 0.0})["r"]
    return nearest_psd_corr(R)


def shuffle_teams_within_week(pf: pd.DataFrame, seed: int = _SEED) -> pd.DataFrame:
    """The permutation substrate: team labels permuted ACROSS players within a global week —
    destroys real same-team structure, keeps every marginal and the week composition."""
    rng = np.random.default_rng(seed)
    out = pf.copy()
    team = out["team"].to_numpy(dtype=object).copy()
    keys = out["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(out)), index=keys).groupby(level=0):
        posn = idx.to_numpy()
        if len(posn) > 1:
            team[posn] = team[rng.permutation(posn)]
    out["team"] = team
    return out


def matched_n_pit(pf_train: pd.DataFrame, n_rows: int) -> pd.DataFrame:
    """The most recent slice of the TRAIN PIT frame with about as many rows as the test block —
    the NF1.9 (f) capacity control, cut at global-week boundaries so team-weeks stay intact."""
    gws = np.sort(pf_train["gw"].unique())[::-1]
    take: list[int] = []
    total = 0
    for g in gws:
        take.append(int(g))
        total += int((pf_train["gw"] == g).sum())
        if total >= max(n_rows, 50):
            break
    return pf_train[pf_train["gw"].isin(take)].copy()


# ── Role cells (the nonparametric arm's alignment key) ──────────────────────────────────────────
def role_cells(positions: np.ndarray, champ_means: np.ndarray) -> list[str | None]:
    """(position, within-team rank by champion predictive mean), capped by ROLE_CAPS; a player
    past the cap has no cell (draws independently). Ties break by array order (deterministic)."""
    cells: list[str | None] = [None] * len(positions)
    for pos in set(positions.tolist()):
        idx = [i for i, p in enumerate(positions) if p == pos]
        order = sorted(idx, key=lambda i: (-float(champ_means[i]), i))
        for rank, i in enumerate(order, start=1):
            if rank <= ROLE_CAPS.get(pos, 0):
                cells[i] = f"{pos}{rank}"
    return cells


def fit_empirical_bank(pf: pd.DataFrame) -> dict:
    """The empirical copula bank: one realized PIT vector per donor team-week, keyed by role
    cell, PER-CELL RANK-NORMALIZED (so every cell's donor values are exactly uniform and the
    marginal-identity property holds)."""
    donors: list[tuple[str, int]] = []
    cell_vals: dict[str, list[tuple[int, float]]] = {}
    for (team, gw), sub in pf.groupby(["team", "gw"], sort=True):
        d_idx = len(donors)
        donors.append((str(team), int(gw)))
        cells = role_cells(sub["position"].to_numpy(dtype=object),
                           sub["champ_mean"].to_numpy(dtype=float))
        for cell, u in zip(cells, sub["u"].to_numpy(dtype=float)):
            if cell is not None:
                cell_vals.setdefault(cell, []).append((d_idx, float(u)))
    n_donors = len(donors)
    bank: dict[str, np.ndarray] = {}
    for cell, pairs in cell_vals.items():
        arr = np.full(n_donors, np.nan)
        vals = np.asarray([v for _, v in pairs])
        ranks = vals.argsort().argsort().astype(float)
        normed = (ranks + 0.5) / len(vals)
        for (d_idx, _), nv in zip(pairs, normed):
            arr[d_idx] = nv
        bank[cell] = arr
    return {"donors": donors, "bank": bank, "n_donors": n_donors}


# ── The compositional class (§5): volume shock × Dirichlet share allocation ─────────────────────
DIRICHLET_C_GRID: tuple[float, ...] = (4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0)
DIRICHLET_SV_GRID: tuple[float, ...] = (0.0, 0.05, 0.1, 0.2, 0.35, 0.5)
DIRICHLET_FIT_STRUCTURES = 60
DIRICHLET_FIT_SAMPLES = 256
DIRICHLET_WEIGHT_FLOOR = 0.1


def _dirichlet_uniforms(weights: np.ndarray, c: float, sv: float, zg: np.ndarray,
                        rng: np.random.Generator) -> np.ndarray:
    """Copula draw: shares ~ Dirichlet(c·w), opportunity o = exp(sv·z_g)·share, then a per-player
    rank transform across samples (an exact uniform permutation — marginals preserved by
    construction; dependence = compositional competition + the shared volume shock)."""
    S = len(zg)
    alpha = np.maximum(c * weights, 1e-3)
    shares = rng.dirichlet(alpha, size=S)
    o = np.exp(sv * zg)[:, None] * shares
    ranks = o.argsort(axis=0).argsort(axis=0).astype(float)
    return (ranks + 0.5) / S


def dirichlet_moments(weights_list: list[np.ndarray], pos_list: list[np.ndarray],
                      c: float, sv: float, rng: np.random.Generator,
                      n_samples: int = DIRICHLET_FIT_SAMPLES) -> tuple[float, float]:
    """Model-implied (within-position, cross-position) mean normal-score products over a set of
    real team structures — the MoM instrument for the (c, sv) fit."""
    from scipy.stats import norm
    sw = sx = nw = nx = 0.0
    for w, pos in zip(weights_list, pos_list):
        zg = rng.standard_normal(n_samples)
        u = _dirichlet_uniforms(w, c, sv, zg, rng)
        z = norm.ppf(np.clip(u, 1e-6, 1 - 1e-6))
        k = len(w)
        iu, ju = np.triu_indices(k, 1)
        prods = (z[:, iu] * z[:, ju]).mean(axis=0)
        same = pos[iu] == pos[ju]
        sw += float(prods[same].sum())
        nw += int(same.sum())
        sx += float(prods[~same].sum())
        nx += int((~same).sum())
    return (sw / nw if nw else 0.0, sx / nx if nx else 0.0)


def fit_dirichlet_params(pf: pd.DataFrame, paircorr: dict, seed: int = _SEED) -> dict:
    """MoM grid fit of (concentration c, volume sd sv) matching the pooled within- and
    cross-position moments. Deterministic (fixed grid, fixed seed, fixed structure subsample)."""
    same = [d for k, d in paircorr.items() if k[0] == k[1]]
    diff = [d for k, d in paircorr.items() if k[0] != k[1]]
    t_w = (sum(d["r"] * d["n_pairs"] for d in same) / sum(d["n_pairs"] for d in same)) if same else 0.0
    t_x = (sum(d["r"] * d["n_pairs"] for d in diff) / sum(d["n_pairs"] for d in diff)) if diff else 0.0

    weights_list: list[np.ndarray] = []
    pos_list: list[np.ndarray] = []
    for (_, _), sub in pf.groupby(["team", "gw"], sort=True):
        if len(sub) < MIN_TEAM_K:
            continue
        weights_list.append(team_weights(sub["champ_mean"].to_numpy(dtype=float)))
        pos_list.append(sub["position"].to_numpy(dtype=object))
        if len(weights_list) >= DIRICHLET_FIT_STRUCTURES:
            break

    best = {"c": DIRICHLET_C_GRID[0], "sv": DIRICHLET_SV_GRID[0], "obj": np.inf,
            "target_within": float(t_w), "target_cross": float(t_x)}
    for c in DIRICHLET_C_GRID:
        for sv in DIRICHLET_SV_GRID:
            rng = np.random.default_rng(np.random.SeedSequence([seed, int(c * 10), int(sv * 100)]))
            m_w, m_x = dirichlet_moments(weights_list, pos_list, c, sv, rng)
            obj = (m_w - t_w) ** 2 + (m_x - t_x) ** 2
            if obj < best["obj"]:
                best.update({"c": float(c), "sv": float(sv), "obj": float(obj),
                             "implied_within": float(m_w), "implied_cross": float(m_x)})
    return best


def team_weights(champ_means: np.ndarray) -> np.ndarray:
    w = np.maximum(np.asarray(champ_means, dtype=float), DIRICHLET_WEIGHT_FLOOR)
    return w / w.sum()


# ── Sampling: one CRN base per team-week, every construction transforms the SAME draws ──────────
def group_seed(fold_label: str, team: str, gw: int) -> np.random.SeedSequence:
    h = zlib.crc32(f"{fold_label}|{team}|{gw}".encode())
    return np.random.SeedSequence([_SEED, h])


def group_base(fold_label: str, team: str, gw: int, k: int,
               n_samples: int = N_SAMPLES) -> dict:
    """The common-random-number base: Z (S×K) player normals, zg (S) the shared latent, du (S)
    donor picks, plus per-mechanism child streams for the non-Gaussian classes."""
    rng = np.random.default_rng(group_seed(fold_label, team, gw))
    return {
        "Z": rng.standard_normal((n_samples, k)),
        "zg": rng.standard_normal(n_samples),
        "du": rng.random(n_samples),
        "dirichlet_rng": np.random.default_rng(group_seed(fold_label, team, gw).spawn(1)[0]),
    }


def sample_uniforms(label: str, params, group: dict, base: dict,
                    champ_means: np.ndarray) -> np.ndarray:
    """U (S×K) for one construction. Every Gaussian-shaped form transforms the SAME base normals
    (CRN); the compositional and empirical classes use their own child streams but share zg/du."""
    from scipy.stats import norm
    Z, zg = base["Z"], base["zg"]
    pos = group["positions"]
    if label == "independence":
        return norm.cdf(Z)
    if label == "comonotonic":
        return np.repeat(norm.cdf(zg)[:, None], Z.shape[1], axis=1)
    if "constant_rho" in label:
        # the exact equicorrelated Gaussian copula, expressed on the CRN base (√ρ·zg + √(1−ρ)·Z)
        rho = float(params)
        z = np.sqrt(rho) * zg[:, None] + np.sqrt(1.0 - rho) * Z
        return norm.cdf(z)
    if "gauss_pos_factor" in label:
        lam = np.asarray([params.get(p, 0.0) for p in pos], dtype=float)
        z = lam[None, :] * zg[:, None] + np.sqrt(1.0 - lam ** 2)[None, :] * Z
        return norm.cdf(z)
    if "gauss_pos_pairwise" in label or "shuffled_teams" in label:
        L = np.linalg.cholesky(build_team_corr(pos, params))
        return norm.cdf(Z @ L.T)
    if "dirichlet_alloc" in label:
        return _dirichlet_uniforms(team_weights(champ_means), params["c"], params["sv"],
                                   zg, base["dirichlet_rng"])
    if "empirical_role_resample" in label:
        return _empirical_uniforms(params, group, base, champ_means)
    raise ValueError(f"unknown construction label: {label}")


def _empirical_uniforms(params: dict, group: dict, base: dict,
                        champ_means: np.ndarray) -> np.ndarray:
    from scipy.stats import norm
    Z, du = base["Z"], base["du"]
    n_samples, k = Z.shape
    self_key = (group["team"], group["gw"])
    donor_ok = [i for i, key in enumerate(params["donors"]) if key != self_key]
    U = norm.cdf(Z)
    if not donor_ok:
        return U
    donor_idx = np.asarray(donor_ok)[np.minimum((du * len(donor_ok)).astype(int),
                                                len(donor_ok) - 1)]
    cells = role_cells(group["positions"], champ_means)
    for i, cell in enumerate(cells):
        if cell is None or cell not in params["bank"]:
            continue
        vals = params["bank"][cell][donor_idx]
        U[:, i] = np.where(np.isfinite(vals), vals, U[:, i])
    return U


def assert_finite_samples(X: np.ndarray, label: str) -> None:
    """The reducer refuses a non-finite predictive — a NaN sample matrix is scored on a silently
    different population by any nan-aware mean (NF-W3's rule, applied to the sample ensemble)."""
    bad = int((~np.isfinite(np.asarray(X, dtype=float))).sum())
    if bad:
        raise ValueError(
            f"construction `{label}` emitted {bad} non-finite sample cells of {np.size(X)} — "
            f"refusing to score a partially-failed ensemble"
        )


# ── Joint scores (sample-based; unit-tested against brute force) ────────────────────────────────
def crps_sample(samples: np.ndarray, y: float) -> float:
    """Sample CRPS: E|X−y| − ½E|X−X'|, cross-term exact over all ordered pairs via the sorted
    identity (O(S log S))."""
    x = np.sort(np.asarray(samples, dtype=float))
    n = len(x)
    term1 = float(np.mean(np.abs(x - y)))
    i = np.arange(n)
    mean_pair = 2.0 * float(np.sum(x * (2 * i - n + 1))) / (n * n)
    return term1 - 0.5 * mean_pair


def energy_score(X: np.ndarray, y: np.ndarray) -> float:
    """Energy score with the half-pairing cross-term estimator (CRN keeps paired deltas tight)."""
    S = X.shape[0]
    h = S // 2
    term1 = float(np.mean(np.linalg.norm(X - y[None, :], axis=1)))
    term2 = float(np.mean(np.linalg.norm(X[:h] - X[h:2 * h], axis=1)))
    return term1 - 0.5 * term2


def variogram_score(X: np.ndarray, y: np.ndarray, p: float = VARIOGRAM_P) -> float:
    dy = np.abs(y[:, None] - y[None, :]) ** p
    dx = np.mean(np.abs(X[:, :, None] - X[:, None, :]) ** p, axis=0)
    iu = np.triu_indices(len(y), 1)
    return float(np.sum((dy[iu] - dx[iu]) ** 2))


def score_group(X: np.ndarray, y: np.ndarray) -> dict:
    T = X.sum(axis=1)
    t_star = float(y.sum())
    q10, q90 = np.quantile(T, [0.10, 0.90])
    return {
        "team_total_crps": crps_sample(T, t_star),
        "energy_score": energy_score(X, y),
        "variogram_score": variogram_score(X, y),
        "total_inside_80": bool(q10 <= t_star <= q90),
        "marginal_crps_sum": float(sum(crps_sample(X[:, j], float(y[j]))
                                       for j in range(X.shape[1]))),
        "k": int(X.shape[1]),
    }


def assert_marginal_identity(marginal_crps: dict[str, float], fold_label: str,
                             tol: float = MARGINAL_IDENTITY_TOL) -> float:
    """⭐ The Sklar guard: every construction shares byte-identical marginal banks, so pooled
    per-player sample CRPS must agree within MC tolerance. A spread beyond it means a
    construction leaked into the marginals — the comparison would mix the dead LEVEL channel
    back in (§10.1A's marginal non-degradation clause, made structural)."""
    vals = np.asarray(list(marginal_crps.values()), dtype=float)
    spread = float((vals.max() - vals.min()) / max(float(vals.mean()), 1e-9))
    if spread > tol:
        worst = {k: round(v, 5) for k, v in marginal_crps.items()}
        raise ValueError(
            f"marginal-identity violated on fold {fold_label}: pooled per-player CRPS spread "
            f"{spread:.4f} > {tol} across constructions {worst} — a copula construction has "
            f"leaked into the marginals and the joint comparison is no longer marginal-pinned"
        )
    return spread


# ── The NF-W8 decision (the story's deliverable; derived, three-way inputs, fails closed) ───────
def decide_nf_w8(ceiling: dict) -> dict:
    """The pre-registered decision rule. Not stat_ok → NO regardless of magnitude; the bands are
    CEILING_BANDS on ceiling_pct. Derived at report time from the stored ceiling selection."""
    lo = ceiling["ci95"][0]
    stat_ok = bool(lo is not None and np.isfinite(lo) and lo > 0
                   and ceiling["fold_clause"]["passes"] and ceiling["fdr_binding"])
    pct = ceiling.get("ceiling_pct")
    if not stat_ok:
        answer = "NO"
        reason = ("the ceiling is not statistically demonstrable at this design "
                  f"(CI95 {ceiling['ci95']}, fold wins {ceiling['fold_wins']}, "
                  f"BH binding {ceiling['fdr_binding']}) — and an upward-biased estimator that "
                  "still cannot demonstrate a ceiling is a conservative NO")
    elif pct is None or not np.isfinite(pct):
        answer = "NO"
        reason = "ceiling_pct unevaluable — failing closed (NF1.7 (a))"
    elif pct < CEILING_BANDS[0]:
        answer = "NO"
        reason = (f"ceiling {pct:.2f}% of independence {PRIMARY_METRIC} is below the "
                  f"{CEILING_BANDS[0]}% band — the §9 simulator premise fails at the allocation "
                  f"channel; revise before committing NF-W8")
    elif pct < CEILING_BANDS[1]:
        answer = "MARGINAL"
        reason = (f"ceiling {pct:.2f}% sits in the {CEILING_BANDS[0]}–{CEILING_BANDS[1]}% band — "
                  f"a PM decision; both readings reported")
    else:
        answer = "YES"
        reason = (f"ceiling {pct:.2f}% ≥ {CEILING_BANDS[1]}% — NF-W8 is justified on the "
                  f"allocation channel")
    return {"answer": answer, "stat_ok": stat_ok, "bands": list(CEILING_BANDS),
            "ceiling_pct": pct, "reason": reason}


# ── The arm gate (names mirror GE's check sets so the shared refusal classifier is reusable) ────
def compose_gate_joint(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["comonotonic_loses"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_shuffled"]
                                    and sel["anchors"]["shuffled_lift_not_significant"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}
