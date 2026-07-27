"""Tests for betting_ml.utils.totals_serving (Story E2.7 — Distribution UX serving helper).

The helper turns the served per-side means + E2.3 dispersion params into the compact distribution
payload the totals pick detail renders. These tests pin the CONTRACT (shape, keys, monotonicity,
determinism, §6 no-raw-samples) — the app consumes this blob verbatim, so a shape regression here is
a silently-dropped field on the page (the E9.41 class)."""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.utils.totals_distribution import TotalsDistributionParams
from betting_ml.utils.totals_serving import (
    _nearest_half,
    build_totals_distribution_payload,
    distribution_is_plausible,
)

# The served E2.3 held-out per-side dispersions (totals_distribution_v1.json).
PARAMS = TotalsDistributionParams(
    dispersion_r=3.7311, dispersion_r_home=4.0645, dispersion_r_away=3.3977,
    rho=0.0, n_draws=10_000,
)


def _payload(mu_home=4.6, mu_away=4.3, line=8.5, **kw):
    return build_totals_distribution_payload(
        mu_home, mu_away, PARAMS, market_total_line=line,
        rng=np.random.default_rng(7), n_draws=4000, **kw,
    )


def test_top_level_shape_matches_served_contract():
    p = _payload()
    assert set(p) == {"version", "total", "run_diff", "team_totals", "alt_totals"}
    assert set(p["total"]) == {"mu", "quantiles", "pmf", "ci80", "market_line", "p_over"}
    assert set(p["run_diff"]) == {"mu", "quantiles", "pmf", "p_home"}
    assert set(p["team_totals"]) == {"home", "away"}
    assert set(p["team_totals"]["home"]) == {"line", "p_over", "mu", "ladder"}


def test_pmf_is_a_valid_unimodal_integer_mass_function():
    pmf = _payload()["total"]["pmf"]
    xs = [pt["x"] for pt in pmf]
    ps = [pt["p"] for pt in pmf]
    # integer support, contiguous and ascending (no sawtooth gaps)
    assert all(isinstance(pt["x"], int) for pt in pmf)
    assert xs == sorted(xs)
    assert xs == list(range(xs[0], xs[-1] + 1))
    # a probability mass: each in [0,1] and the trimmed support holds ~all the mass
    assert all(0.0 <= q <= 1.0 for q in ps)
    assert 0.9 <= sum(ps) <= 1.0001
    # unimodal-ish: a single interior peak (a count distribution is a smooth bell, not a sawtooth)
    peak = ps.index(max(ps))
    assert 0 < peak < len(ps) - 1
    # the peak sits near the projected mean (sum of the per-side means)
    assert abs(xs[peak] - _payload()["total"]["mu"]) <= 2.0


def test_pmf_peak_shifts_with_the_projection():
    lo_peak = max(_payload(mu_home=2.5, mu_away=2.5)["total"]["pmf"], key=lambda d: d["p"])["x"]
    hi_peak = max(_payload(mu_home=6.5, mu_away=6.5)["total"]["pmf"], key=lambda d: d["p"])["x"]
    assert lo_peak < hi_peak


def test_run_diff_pmf_spans_negative_and_positive():
    pmf = _payload(mu_home=4.6, mu_away=4.3)["run_diff"]["pmf"]
    xs = [pt["x"] for pt in pmf]
    assert min(xs) < 0 < max(xs)  # margins can be negative (away wins) or positive (home wins)


def test_quantile_grid_is_p05_to_p95_and_monotone():
    q = _payload()["total"]["quantiles"]
    keys = [f"p{int(round(l * 100)):02d}" for l in PARAMS.quantile_levels]
    assert list(q.keys()) == keys
    vals = [q[k] for k in keys]
    assert vals == sorted(vals)  # non-decreasing quantiles
    assert q["p05"] < q["p50"] < q["p95"]


def test_total_mu_equals_sum_of_per_side_means():
    assert _payload(mu_home=4.6, mu_away=4.3)["total"]["mu"] == pytest.approx(8.9, abs=1e-6)


def test_ci80_brackets_the_median_and_is_ordered():
    tot = _payload()["total"]
    lo, hi = tot["ci80"]
    assert lo < tot["quantiles"]["p50"] < hi
    # 80% interval ≈ [P10, P90]
    assert lo == pytest.approx(tot["quantiles"]["p10"], abs=0.5)
    assert hi == pytest.approx(tot["quantiles"]["p90"], abs=0.5)


def test_p_over_is_prob_and_falls_as_line_rises():
    # Higher totals line ⇒ lower P(over). A clean monotonicity sanity check on the served p_over.
    p_low = _payload(line=7.5)["total"]["p_over"]
    p_high = _payload(line=10.5)["total"]["p_over"]
    assert 0.0 <= p_high < p_low <= 1.0


def test_no_market_line_yields_null_p_over_but_still_ladders():
    p = build_totals_distribution_payload(
        4.6, 4.3, PARAMS, market_total_line=None, rng=np.random.default_rng(1), n_draws=2000,
    )
    assert p["total"]["market_line"] is None
    assert p["total"]["p_over"] is None
    # alt ladder still anchored (on nearest-half of μ_total) so the surface is never empty
    assert len(p["alt_totals"]) == 9
    assert all(0.0 <= a["p_over"] <= 1.0 for a in p["alt_totals"])


def test_run_diff_p_home_reflects_stronger_home_offense():
    p_home_edge = _payload(mu_home=5.5, mu_away=3.5)["run_diff"]["p_home"]
    p_away_edge = _payload(mu_home=3.5, mu_away=5.5)["run_diff"]["p_home"]
    assert p_home_edge > 0.5 > p_away_edge
    assert _payload(mu_home=5.5, mu_away=3.5)["run_diff"]["mu"] == pytest.approx(2.0, abs=1e-6)


def test_alt_ladder_is_monotone_decreasing_in_line():
    alt = _payload()["alt_totals"]
    lines = [a["line"] for a in alt]
    assert lines == sorted(lines)                       # ascending lines
    p = [a["p_over"] for a in alt]
    assert all(p[i] >= p[i + 1] for i in range(len(p) - 1))  # P(over) non-increasing


def test_team_total_ladder_monotone_and_line_defaults_to_nearest_half_of_mu():
    tt = _payload(mu_home=4.6, mu_away=4.3, home_team_line=None, away_team_line=None)["team_totals"]
    assert tt["home"]["line"] == _nearest_half(4.6) == 4.5
    assert tt["away"]["line"] == _nearest_half(4.3) == 4.5
    for side in ("home", "away"):
        pov = [pt["p_over"] for pt in tt[side]["ladder"]]
        assert all(pov[i] >= pov[i + 1] for i in range(len(pov) - 1))


def test_provided_team_lines_are_used_verbatim():
    tt = _payload(home_team_line=5.0, away_team_line=3.5)["team_totals"]
    assert tt["home"]["line"] == 5.0
    assert tt["away"]["line"] == 3.5


def test_deterministic_for_a_fixed_seed():
    a = build_totals_distribution_payload(4.6, 4.3, PARAMS, market_total_line=8.5,
                                          rng=np.random.default_rng(42), n_draws=3000)
    b = build_totals_distribution_payload(4.6, 4.3, PARAMS, market_total_line=8.5,
                                          rng=np.random.default_rng(42), n_draws=3000)
    assert a == b


def test_payload_is_compact_and_json_safe():
    """§6: params + quantile grid + p_over ladders only — never raw samples. And every value is a
    JSON-native scalar (no numpy types) so json.dumps into the DynamoDB blob can't choke."""
    import json

    p = _payload()
    s = json.dumps(p)  # raises TypeError if any numpy scalar leaked in
    assert len(s) < 4000  # a few hundred floats, well under the 400 KB DynamoDB item cap
    # spot-check: no raw sample arrays anywhere
    assert "samples" not in s

    def _all_native(obj):
        if isinstance(obj, dict):
            return all(_all_native(v) for v in obj.values())
        if isinstance(obj, list):
            return all(_all_native(v) for v in obj)
        return obj is None or isinstance(obj, (str, int, float, bool))

    assert _all_native(p)


def test_plausibility_guard_flags_implausibly_low_side_mu():
    # A full-game team total of 1.29 runs (the 824734 case) is implausible → suppress.
    assert distribution_is_plausible(4.5, 4.3) is True
    assert distribution_is_plausible(1.29, 4.31) is False   # home side μ below the floor
    assert distribution_is_plausible(4.31, 1.29) is False   # symmetric


def test_plausibility_guard_flags_sharp_divergence_from_champion():
    # Both sides sane, but the convolved total (9.0) disagrees with the champion by > 4 runs.
    assert distribution_is_plausible(4.5, 4.5, champion_total=9.2) is True   # gap 0.2 — fine
    assert distribution_is_plausible(4.5, 4.5, champion_total=11.0) is True  # gap 2.0 — within tolerance
    assert distribution_is_plausible(4.5, 4.5, champion_total=14.0) is False  # gap 5.0 — contradictory
    # No champion to compare against ⇒ the divergence rule is skipped.
    assert distribution_is_plausible(4.5, 4.5, champion_total=None) is True


def test_higher_dispersion_widens_the_interval():
    """The E2.3 held-out r (wider) must produce a wider CI than the under-dispersed train-fit r —
    the whole point of serving the calibrated dispersion, not the artifact's."""
    wide = build_totals_distribution_payload(
        4.6, 4.3, PARAMS, market_total_line=8.5, rng=np.random.default_rng(3), n_draws=6000)
    tight_params = TotalsDistributionParams(dispersion_r=20.0, dispersion_r_home=20.0,
                                            dispersion_r_away=20.0)
    tight = build_totals_distribution_payload(
        4.6, 4.3, tight_params, market_total_line=8.5, rng=np.random.default_rng(3), n_draws=6000)
    wide_w = wide["total"]["ci80"][1] - wide["total"]["ci80"][0]
    tight_w = tight["total"]["ci80"][1] - tight["total"]["ci80"][0]
    assert wide_w > tight_w
