"""NF-ROS1b — guards on the hurdle interval and the harness hook (registration §6, amendment 1).

Fast gate: pure `ros_interval` plus the parent harness driven on a synthetic frame (no lake, no
credentials). The §6 synthetic controls live here: the positive control must pass and the two
negative controls must fail, on a design fixed before either was run.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import ros_interval as RI
from quant_sports_intel_models.football.nfl.fantasy import ros_value as V

REPO = Path(__file__).resolve().parents[2]
FANT = REPO / "quant_sports_intel_models/football/nfl/fantasy"

# ── §6 synthetic controls: design fixed before running ────────────────────────────────────────────
CONTROL_N = 20000
CONTROL_SIGMA = 0.5


def _hurdle_truth(seed: int):
    rng = np.random.default_rng(seed)
    x1 = rng.standard_normal(CONTROL_N)
    x2 = rng.uniform(math.log(20), math.log(300), CONTROL_N)
    pi = 1.0 / (1.0 + np.exp(-(-1.0 + 1.2 * x1)))
    mu = np.exp(x2)
    eps = rng.lognormal(-CONTROL_SIGMA ** 2 / 2, CONTROL_SIGMA, CONTROL_N)
    y = np.where(rng.random(CONTROL_N) < pi, 0.0, mu * eps)
    k = rng.integers(1, 13, CONTROL_N)
    pos = np.array(["RB"] * CONTROL_N)
    return np.column_stack([x1, x2]), mu, y, k, pos


@pytest.fixture(scope="module")
def control_draws():
    return _hurdle_truth(V.SEED), _hurdle_truth(V.SEED + 1)


def _pit(y, q, seed=V.SEED):
    return V.max_decile_dev(V.randomized_pit(y, q, np.random.default_rng(seed)))


def test_hurdle_positive_control_reads_flat(control_draws):
    (Xa, mua, ya, ka, pa), (Xb, mub, yb, kb, pb) = control_draws
    model = RI.fit_pi(Xa, (ya <= 0).astype(int))
    table = RI.fit_ratio_table(pa, ka, mua, ya)
    q, _ = RI.apply_hurdle(table, pb, kb, mub, RI.predict_pi(model, Xb))
    assert _pit(yb, q) <= 0.02


def test_hurdle_negative_control_without_the_atom_fails(control_draws):
    (Xa, mua, ya, ka, pa), (Xb, mub, yb, kb, pb) = control_draws
    table = RI.fit_ratio_table(pa, ka, mua, ya)
    q, _ = RI.apply_hurdle(table, pb, kb, mub, np.zeros(len(yb)))
    assert _pit(yb, q) > V.PIT_MAX_DECILE_DEV


def test_hurdle_negative_control_parent_location_shift_fails(control_draws):
    (Xa, mua, ya, ka, pa), (Xb, mub, yb, kb, pb) = control_draws
    table = V.fit_residual_table(pa, ka, mua, ya)
    q, _ = V.apply_residual_table(table, pb, kb, mub)
    assert _pit(yb, q) > V.PIT_MAX_DECILE_DEV


# ── the family's structural clauses ───────────────────────────────────────────────────────────────
def _table_and_rows(seed=3, n=3000):
    rng = np.random.default_rng(seed)
    pos = rng.choice(["QB", "RB"], n)
    k = rng.integers(1, 13, n)
    pred = rng.uniform(1, 250, n)
    y = np.where(rng.random(n) < 0.2, 0.0, pred * rng.lognormal(0, 0.4, n))
    return RI.fit_ratio_table(pos, k, pred, y), pos, k, pred, rng.uniform(0, 0.6, n)


def test_scale_equivariance():
    table, pos, k, pred, pi = _table_and_rows()
    q1, _ = RI.apply_hurdle(table, pos, k, pred, pi)
    # scaling ŷ moves terciles — compare within ONE shared ratio vector, the family's own map
    rq = table["pos"]["RB"]
    a = RI.mixture_quantiles(pred, pi, rq)
    b = RI.mixture_quantiles(3.7 * pred, pi, rq)
    atom = V.LEVELS[None, :] <= pi[:, None]
    assert np.allclose(b[~atom], 3.7 * a[~atom], rtol=0, atol=1e-9)
    assert (b[atom] == 0).all() and (a[atom] == 0).all()
    assert q1.shape == (len(pred), len(V.LEVELS))


def test_mixture_is_monotone_and_the_atom_levels_are_exactly_zero():
    table, pos, k, pred, pi = _table_and_rows()
    rq = table["pos"]["QB"]
    raw = RI.mixture_quantiles(pred, pi, rq)          # before the floor-and-sort
    assert (np.diff(raw, axis=1) >= -1e-12).all()
    assert (raw[V.LEVELS[None, :] <= pi[:, None]] == 0).all()
    assert (raw[V.LEVELS[None, :] > pi[:, None]] > 0).all()


def test_a_zero_point_is_a_point_mass_at_zero():
    table, pos, k, pred, pi = _table_and_rows()
    pred = pred.copy()
    pred[:50] = 0.0
    q, _ = RI.apply_hurdle(table, pos, k, pred, pi)
    assert (q[:50] == 0).all()
    assert (q[50:, -1] > 0).all()


def test_a_certain_zero_is_all_zero_and_no_zero_is_all_positive():
    rq = np.linspace(0.2, 3.0, len(RI.FINE_LEVELS))
    q = RI.mixture_quantiles(np.array([100.0, 100.0]), np.array([1.0, 0.0]), rq)
    assert (q[0] == 0).all() and (q[1] > 0).all()


def test_ratio_fallback_is_counted_only_where_a_ratio_is_needed():
    rng = np.random.default_rng(4)
    n = 200                                            # far below 3 cells × 40 per k-bucket
    pos = np.array(["TE"] * n)
    k = rng.integers(1, 13, n)
    pred = rng.uniform(1, 100, n)
    y = pred * rng.lognormal(0, 0.3, n)
    table = RI.fit_ratio_table(pos, k, pred, y)
    pred2 = pred.copy()
    pred2[:20] = 0.0
    _, fb = RI.apply_hurdle(table, pos, k, pred2, np.full(n, 0.1))
    assert fb == n - 20


def test_an_all_zero_predictor_needs_no_ratio_table():
    pos = np.array(["K"] * 100)
    k = np.arange(100) % 12 + 1
    table = RI.fit_ratio_table(pos, k, np.zeros(100), np.ones(100))
    q, fb = RI.apply_hurdle(table, pos, k, np.zeros(100), np.full(100, 0.3))
    assert (q == 0).all() and fb == 0


def test_a_positive_prediction_without_a_table_refuses():
    with pytest.raises(V.RosError):
        RI.apply_hurdle({"edges": {}, "cell": {}, "kb": {}, "pos": {}}, ["WR"], [3], [10.0], [0.1])


def test_single_class_hurdle_falls_back_to_the_base_rate():
    m = RI.fit_pi(np.random.default_rng(0).normal(size=(30, 3)), np.zeros(30, dtype=int))
    assert m["single_class"] and (RI.predict_pi(m, np.zeros((4, 3))) == 0).all()


def test_zero_sd_feature_is_dropped_and_counted():
    rng = np.random.default_rng(1)
    X = np.column_stack([rng.normal(size=400), np.ones(400)])
    z = (X[:, 0] + rng.normal(size=400) > 0).astype(int)
    m = RI.fit_pi(X, z)
    assert m["dropped"] == 1 and len(m["coef"]) == 1


def test_the_hurdle_learns_the_direction_of_its_signal():
    rng = np.random.default_rng(2)
    x = rng.normal(size=(4000, 1))
    z = (rng.random(4000) < 1 / (1 + np.exp(-(2 * x[:, 0])))).astype(int)
    p = RI.predict_pi(RI.fit_pi(x, z), np.array([[-2.0], [2.0]]))
    assert p[0] < 0.2 < 0.8 < p[1]


# ── §3.2 miss_streak ──────────────────────────────────────────────────────────────────────────────
def _streak_frame():
    # team plays every week except week 4 (bye); the player misses weeks 5-7, returns at 8
    t = [1, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    played = {1, 2, 3, 8, 9, 10, 11, 12}
    n, c = [], 0
    for k in range(1, 13):
        c += k in played
        n.append(c)
    return pd.DataFrame({"season": 2021, "player_id": "P", "k": range(1, 13), "t": t, "n": n})


def test_miss_streak_counts_missed_team_games_and_skips_the_bye():
    s = RI.miss_streak(_streak_frame()).tolist()
    assert s == [0, 0, 0, 0, 1, 2, 3, 0, 0, 0, 0, 0]


def test_miss_streak_reads_no_week_after_k():
    f = _streak_frame()
    full = RI.miss_streak(f)
    for k in range(1, 13):
        part = RI.miss_streak(f[f["k"] <= k])
        assert part.iloc[-1] == full.iloc[k - 1]


def test_miss_streak_carries_a_missing_row():
    f = _streak_frame()
    s = RI.miss_streak(f.drop(index=5))                 # k = 6 unresolved
    # registered literally (§3.2): the previous AVAILABLE row stands in for k−1, so the gap is one
    # +1 step, not two — k = 7 reads 2. (The parent frame had 0 unresolved rows.)
    assert s.loc[6] == 2
    assert s.loc[7] == 0 and 5 not in s.index


def test_the_foil_carries_the_donors_streak():
    """perm_n and perm_miss_streak must come from the SAME donor. Each player's n and streak encode
    its own code, so a mismatched pair is visible whatever the permutation draws — and at least one
    player must actually receive someone else's history, or the check proves nothing."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1 as N
    rows = []
    for code in range(1, 7):
        for k in V.EVAL_WEEKS:
            r = {"season": 2021, "player_id": f"P{code}", "pos": "RB", "k": k, "n": code * k,
                 "miss_streak": float(code * 100 + k)}
            for p in V.PRESETS:
                r[f"xsum_{p}"] = float(k)
            rows.append(r)
    f = N.add_permuted(pd.DataFrame(rows))
    n_code = f["perm_n"] / f["k"]
    s_code = (f["perm_miss_streak"] - f["k"]) / 100
    assert np.array_equal(n_code.to_numpy(), s_code.to_numpy())
    own = f["player_id"].str[1:].astype(float)
    assert (n_code != own).any(), "the permutation is the identity — the check is vacuous"


def test_pi_features_are_the_registered_set_in_order():
    assert RI.PI_FEATURES == ("a0", "share_played", "no_games", "miss_streak", "log_g_rem",
                              "log_r0", "rookie", "kb_4_6", "kb_7_9", "kb_10_12")
    df = pd.DataFrame({"a0": [0.5], "n": [2.0], "t": [4.0], "k": [8], "miss_streak": [1.0],
                       "g_rem": [9.0], "r0_full_ppr": [12.0], "rookie": [True],
                       "perm_n": [0.0], "perm_miss_streak": [4.0]})
    X = RI.pi_features(df)
    assert X.tolist() == [[0.5, 0.5, 0.0, 1.0, math.log1p(9), math.log1p(12), 1.0, 0.0, 1.0, 0.0]]
    Xp = RI.pi_features(df, "perm_")
    assert Xp[0, 1] == 0.0 and Xp[0, 2] == 1.0 and Xp[0, 3] == 4.0


# ── §8 name-join classification ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("rid,auth,real,want", [
    ("G1", "G1", {"G1"}, "CORRECT"),
    ("G2", "G1", {"G1", "G2"}, "WRONG"),
    (None, "G1", {"G1"}, "MISSED"),
    (None, "G1", set(), "CORRECT_ABSENT"),
    ("G1", None, {"G1"}, "UNVERIFIABLE"),
])
def test_join_outcomes(rid, auth, real, want):
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    assert B.classify_join(rid, auth, real) == want


def test_a_wrong_join_is_never_correct():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    assert B.classify_join("G2", "G1", {"G1", "G2"}) == "WRONG"


def test_the_pick_key_is_refused_when_a_position_disagrees():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    syn = pd.DataFrame({"player_id": ["S1", "S2"], "player_name": ["Ann Able", "Bo Bee"],
                        "position": ["WR", "RB"], "draft_pick": [3, 7]})
    picks = pd.DataFrame({"season": [2026, 2026], "pick": [3, 7], "gsis_id": ["G3", "G7"],
                          "pfr_player_name": ["Ann Able", "Bo Bee"], "position": ["WR", "QB"]})
    rosters = pd.DataFrame({"season": [2026], "week": [1], "full_name": ["Ann Able"],
                            "position": ["WR"], "gsis_id": ["G3"]})
    auth, ver = B.authority(syn, picks, rosters)
    assert ver["pick_key_verified"] is False
    assert auth["S1"] == ("G3", "rosters_name (normalizer-dependent)")
    assert auth["S2"][0] is None


def test_the_pick_key_is_used_when_verified():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    syn = pd.DataFrame({"player_id": ["S1"], "player_name": ["Totally Different"],
                        "position": ["WR"], "draft_pick": [3]})
    picks = pd.DataFrame({"season": [2026], "pick": [3], "gsis_id": ["G3"],
                          "pfr_player_name": ["Ann Able"], "position": ["WR"]})
    rosters = pd.DataFrame({"season": [2026], "week": [1], "full_name": ["x"], "position": ["WR"],
                            "gsis_id": ["G9"]})
    auth, ver = B.authority(syn, picks, rosters)
    assert ver["pick_key_verified"] is True and auth["S1"] == ("G3", "draft_pick")


# ── reproduction comparison ───────────────────────────────────────────────────────────────────────
def test_max_abs_diff_sees_numbers_structure_and_ignores_meta():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    a = {"meta": {"commit": "x"}, "result": {"v": [1.0, 2.0], "s": "a"}}
    assert B.max_abs_diff(a, {"meta": {"commit": "y"}, "result": {"v": [1.0, 2.0], "s": "a"}}) == (0.0, [])
    d, bad = B.max_abs_diff(a, {"meta": {}, "result": {"v": [1.0, 2.5], "s": "a"}})
    assert d == 0.5 and not bad
    _, bad = B.max_abs_diff(a, {"meta": {}, "result": {"v": [1.0], "s": "b", "extra": 1}})
    assert len(bad) == 3


# ── hygiene ───────────────────────────────────────────────────────────────────────────────────────
def test_ros_interval_never_imports_pipeline_or_does_io():
    tree = ast.parse((FANT / "ros_interval.py").read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods, "the scan found no imports at all — it is not reading the module"
    assert not mods & {"pipeline", "boto3", "deltalake", "duckdb", "requests"}


def test_the_successor_never_writes_the_parents_record():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    stems = {B.STEM, B.REPRO_STEM, B.NAME_JOIN_STEM}
    assert B.PARENT_STEM not in stems
    assert all(s.startswith("nf_ros1b_") for s in stems)


def test_the_reference_arm_is_labelled_and_outside_the_field():
    assert "not a trial" in RI.REFERENCE_LABEL and "not in V" in RI.REFERENCE_LABEL
    assert RI.REFERENCE_KEY not in V.ARMS + V.DEGENERATES + (V.INCUMBENT, V.MATCHED_FOIL)


# ── the harness hook, end to end on a synthetic frame ────────────────────────────────────────────
def _synthetic_frame(seed=11, players=70):
    rng = np.random.default_rng(seed)
    rows = []
    for s in (2019, 2020, 2021):
        for P in V.POSITIONS:
            for i in range(players):
                pid = f"{P}{s}_{i}"
                r0 = rng.uniform(3, 20)
                a0 = rng.uniform(0.3, 1.0)
                hurt = rng.random() < 0.25
                played = np.array([(not hurt or w < 4) and rng.random() < 0.9 for w in range(1, 18)])
                pts = np.where(played, np.maximum(rng.normal(r0, r0 / 2, 17), 0), 0.0)
                for k in V.EVAL_WEEKS:
                    r = {"season": s, "player_id": pid, "rid": pid, "k": k, "pos": P,
                         "rookie": bool(i % 5 == 0), "t": float(k), "g_rem": float(17 - k),
                         "g_season": 17.0, "n": int(played[:k].sum()),
                         "last3_n": int(min(3, played[:k].sum())), "a0": a0}
                    for p in V.PRESETS:
                        r[f"r0_{p}"] = r0
                        r[f"board_{p}"] = r0 * 17 * a0
                        r[f"xsum_{p}"] = float(pts[:k].sum())
                        r[f"last3_sum_{p}"] = float(pts[:k][played[:k]][-3:].sum())
                        r[f"y_{p}"] = float(pts[k:].sum())
                    rows.append(r)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def synthetic():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1 as N
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    f = B.prepare_frame(_synthetic_frame())
    return N, B, f


def test_the_hook_is_inert_when_no_interval_is_passed(synthetic):
    N, _, f = synthetic
    base = f.drop(columns=["miss_streak", "perm_miss_streak"])
    a = N.score_fold(base, 2021, presets=(V.GATE_PRESET,))
    b = N.score_fold(f, 2021, presets=(V.GATE_PRESET,), interval=None)
    assert "reference" not in b
    for name, (pa, qa) in a["pred"][V.GATE_PRESET].items():
        pb, qb = b["pred"][V.GATE_PRESET][name]
        assert np.array_equal(pa, pb) and np.array_equal(qa, qb), name


def test_the_hurdle_replaces_every_predictors_interval_but_not_its_point(synthetic):
    N, _, f = synthetic
    a = N.score_fold(f, 2021, presets=(V.GATE_PRESET,))
    b = N.score_fold(f, 2021, presets=(V.GATE_PRESET,), interval=RI.HurdleInterval())
    names = set(a["pred"][V.GATE_PRESET])
    assert names == set(b["pred"][V.GATE_PRESET]) and len(names) > 10
    for name in names:
        pa, qa = a["pred"][V.GATE_PRESET][name]
        pb, qb = b["pred"][V.GATE_PRESET][name]
        assert np.array_equal(pa, pb), name
        if name != "nihilist_zero":
            assert not np.array_equal(qa, qb), name
    # the reference is the parent's construction on the arm's own point
    for arm in V.ARMS:
        pr, qr = b["reference"][arm]
        assert np.array_equal(pr, a["pred"][V.GATE_PRESET][arm][0])
        assert np.array_equal(qr, a["pred"][V.GATE_PRESET][arm][1])


def test_the_foil_reads_the_permuted_hurdle(synthetic):
    N, _, f = synthetic
    iv = RI.HurdleInterval()
    N.score_fold(f, 2021, presets=(V.GATE_PRESET,), interval=iv)
    real = iv.by_fold[(2021, V.GATE_PRESET, "")]
    perm = iv.by_fold[(2021, V.GATE_PRESET, "perm_")]
    assert real.shape == perm.shape and not np.allclose(real, perm)


def _atom_levels_used(q, point):
    """Per row, how many grid levels are exactly 0 — for a positive point that is exactly the
    count of levels ≤ π, because every ratio quantile is > 0."""
    m = point > 0
    return m, (q[m] == 0).sum(axis=1)


def test_every_predictor_reads_its_own_hurdle_probability(synthetic):
    """The foil's predictive must use the PERMUTED π and everyone else the real π — checked on the
    quantiles actually produced, not on what `prepare` stored (the first cut only checked the latter,
    which stays green if the foil is handed the wrong π)."""
    N, _, f = synthetic
    iv = RI.HurdleInterval()
    b = N.score_fold(f, 2021, presets=(V.GATE_PRESET,), interval=iv)
    real = iv.by_fold[(2021, V.GATE_PRESET, "")]
    perm = iv.by_fold[(2021, V.GATE_PRESET, "perm_")]
    want_real = (V.LEVELS[None, :] <= real[:, None]).sum(axis=1)
    want_perm = (V.LEVELS[None, :] <= perm[:, None]).sum(axis=1)
    for name, (point, q) in b["pred"][V.GATE_PRESET].items():
        if name in ("nihilist_zero",):
            continue
        m, got = _atom_levels_used(q, point)
        want = (want_perm if name == V.MATCHED_FOIL else want_real)[m]
        assert np.array_equal(got, want), name
    assert not np.array_equal(want_real, want_perm)


def test_the_hurdle_event_is_y_at_or_below_zero(synthetic):
    N, _, f = synthetic
    iv = RI.HurdleInterval()
    train = f[f["season"] < 2021]
    iv.prepare(train, f[f["season"] == 2021].reset_index(drop=True), V.GATE_PRESET, 2021)
    for P in V.POSITIONS:
        want = float((train.loc[train["pos"] == P, f"y_{V.GATE_PRESET}"] <= 0).mean())
        assert want > 0
        assert iv.diag[(2021, V.GATE_PRESET, "real", P)]["train_zero_rate"] == pytest.approx(want)


def test_the_registered_constants():
    assert len(RI.FINE_LEVELS) == 199
    assert RI.FINE_LEVELS[0] == 0.005 and RI.FINE_LEVELS[-1] == 0.995
    assert RI.LOGIT_C == 1.0 and RI.LOGIT_MAX_ITER == 2000


def test_the_companion_diagnostic_reads_mean_pi_on_the_top_tercile():
    point = np.array([1.0, 2.0, 3.0, 10.0, 11.0, 12.0])
    pos = np.array(["RB"] * 6)
    pi = np.array([0.9, 0.9, 0.9, 0.06, 0.10, 0.20])
    y = np.array([0.0, 0.0, 0.0, 0.0, 5.0, 7.0])
    d = RI.atom_calibration_top_tercile(pi, y, point, pos)["RB"]
    top = point > np.quantile(point, 2 / 3)
    assert d["top_tercile_rows"] == int(top.sum())
    assert d["mean_predicted_p_zero"] == pytest.approx(pi[top].mean())
    assert d["realized_zero_share"] == pytest.approx((y[top] <= 0).mean())
    assert d["difference"] == pytest.approx(pi[top].mean() - (y[top] <= 0).mean())


def test_the_companion_diagnostic_is_labelled_and_outside_every_verdict():
    assert RI.COMPANION_LABEL.startswith("POST-SMOKE COMPANION DIAGNOSTIC")
    assert "gates nothing" in RI.COMPANION_LABEL
    src = (FANT / "run_nf_ros1.py").read_text()
    assert "companion" not in src.lower(), "the diagnostic must never reach the verdict harness"


def test_the_full_evaluate_runs_and_writes_a_labelled_report(synthetic, tmp_path, monkeypatch):
    N, B, f = synthetic
    monkeypatch.setattr(N, "RESULTS", tmp_path)
    result = B.run(f, (2020, 2021), RI.INTERVAL_NAME)
    assert set(result["positions"]) == set(V.POSITIONS)
    for d in result["positions"].values():
        assert set(d["clauses"]) >= {"C7_coverage_floor", "C9_pit_flat"}
    h = result["hurdle"]
    assert set(h["mechanism_check"]) == {"hurdle", "location_shift_reference"}
    meta = {"generated_at": "t", "commit": "c", "interval": RI.INTERVAL_NAME}
    jp, mp = B.write_report(result, {"x": 1}, smoke=True, meta=meta, stem="probe")
    assert jp.parent == tmp_path
    text = mp.read_text()
    assert RI.REFERENCE_LABEL in text and "Mechanism check" in text
    assert RI.COMPANION_LABEL in text and "not a calibration reading" in text
    assert "top_tercile_atom_calibration" in h["post_smoke_companion_diagnostic"]
    payload = json.loads(jp.read_text())
    assert RI.REFERENCE_KEY in payload["result"]["hurdle"]
    assert "interval" not in payload["result"]


def test_the_rb_rookie_read_uses_only_rb_rookies_and_the_registered_bar(synthetic):
    N, B, f = synthetic
    result = B.run(f, (2020, 2021), RI.INTERVAL_NAME)
    res = B.rb_rookie_read(result)
    tests = pd.concat([x["test"] for x in result["_folds_obj"]])
    assert res["rb_rookie"]["rows"] == int(((tests["pos"] == "RB") & tests["rookie"]).sum())
    assert res["rb_veteran_context_only"]["rows"] == int(((tests["pos"] == "RB") & ~tests["rookie"]).sum())
    assert res["bar"] == V.PIT_MAX_DECILE_DEV == 0.05
    dev = res["rb_rookie"]["pit_max_decile_dev"]
    assert res["decision"] == ("STRATUM_CHECK_PASSES" if dev <= 0.05 else "STOP_TO_PM")


def test_the_rb_rookie_decision_rule_has_both_branches():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    assert B.rb_rookie_decision(0.05) == "STRATUM_CHECK_PASSES"
    assert B.rb_rookie_decision(0.0501) == "STOP_TO_PM"
    assert B.rb_rookie_decision(None) == "UNEVALUABLE"


# ══ amendment 5 — the per-player spread (descriptive; gates nothing) ═══════════════════════════


def test_the_spread_finds_a_concentrated_excess_and_names_its_contributors():
    """A top decile carried by TWO player-seasons must read as concentrated, not as a broad tilt —
    that distinction is the whole reason the PM asked for the spread."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    import numpy as np

    # 10 player-seasons × 10 rows. Two of them live entirely in the top decile; the rest are
    # spread uniformly below it.
    keys = np.repeat([f"2021|p{i}" for i in range(10)], 10)
    u = np.concatenate([np.full(20, 0.95),                      # p0, p1 — entirely top-decile
                        np.tile(np.linspace(0.01, 0.89, 10), 8)])
    s = B.pit_spread(u, keys)

    assert s["top_decile_rows"] == 20
    assert s["top_decile_player_seasons"] == 2
    assert s["player_seasons_entirely_in_top_decile"] == 2
    assert s["top_decile_share_from_10_largest_contributors"] == 1.0
    assert s["player_seasons_above_half"] == 2


def test_the_clustered_reading_is_the_conservative_one():
    """⭐ THE INVERSION THIS GUARD EXISTS FOR. The two z columns differ ONLY in the effective n, so
    swapping them would report a clustered deviation as MORE significant than an independent one —
    i.e. it would overstate exactly the evidence the PM's disposition rests on. Fewer effective
    observations must always mean a smaller |z|."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    import numpy as np

    keys = np.repeat([f"2021|p{i}" for i in range(12)], 12)
    rng = np.random.default_rng(7)
    u = np.clip(rng.beta(2.0, 1.2, size=keys.size), 0, 1 - 1e-12)   # a deliberately skewed draw
    s = B.pit_spread(u, keys)

    moved = [i for i in range(10) if abs(s["decile_z_rows_independent"][i]) > 1e-9]
    assert moved, "the fixture produced a flat histogram — the comparison would be vacuous"
    for i in moved:
        assert abs(s["decile_z_fully_clustered"][i]) < abs(s["decile_z_rows_independent"][i])


def test_the_spread_never_returns_a_verdict():
    """Amendment 5 declares no threshold: the PM reads the spread. A verdict key appearing here
    would be a bar invented after the stop fired (E2.1-r)."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    import numpy as np

    s = B.pit_spread(np.linspace(0.01, 0.99, 60), np.repeat(["a", "b", "c", "d", "e"], 12))
    for k, val in s.items():
        assert "decision" not in k and "verdict" not in k and "pass" not in k
        assert not isinstance(val, str), f"{k} carries prose, and prose is where a verdict hides"


def test_a_rerun_after_the_result_is_known_must_prove_it_moved_nothing(tmp_path):
    """The re-run that computes the spread happens AFTER its own number is public. It has to show
    it did not move it — and a FIRST run must report `None`, never a vacuous 'reproduced'."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1b as B
    import json

    now = {"rb_rookie": {"pit_max_decile_dev": 0.081, "coverage80": 0.7637},
           "decision": "STOP_TO_PM"}
    jp = tmp_path / "prior.json"

    assert B.reproduction_of_prior(now, jp) is None          # nothing on disk to reproduce

    jp.write_text(json.dumps({"result": now}))
    assert B.reproduction_of_prior(now, jp)["identical"] is True

    moved = {**now, "rb_rookie": {**now["rb_rookie"], "pit_max_decile_dev": 0.0812}}
    assert B.reproduction_of_prior(moved, jp)["identical"] is False

    flipped = {**now, "decision": "STRATUM_CHECK_PASSES"}
    assert B.reproduction_of_prior(flipped, jp)["identical"] is False

    jp.write_text("{ not json")
    assert B.reproduction_of_prior(now, jp)["identical"] is None   # unverified, never "the same"
