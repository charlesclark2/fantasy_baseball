"""NF-C0e — guards for turning CAPTURED scoring terms into APPLIED ones, where the signal is real.

Four things need pinning, and they are in descending order of how badly they bite:

1. **EVERY ADAPTER TARGET MUST BE A REAL CANONICAL KEY.** This is the guard for the outage NF-C0e
   found: `espn.py` mapped ESPN's yardage stat ids onto `pass_yd` / `rush_yd` / `rec_yd` /
   `fum_lost` — SLEEPER's platform keys — instead of the canonical `pass_yds` / `rush_yds` /
   `rec_yds` / `fumbles_lost`. Nothing errored, because NF-C0's contract is that an unrecognised
   key passes through verbatim and reports CAPTURED. So every ESPN-imported league scored ZERO for
   passing, rushing and receiving YARDAGE behind a panel that said so and nobody read. A key one
   character off is indistinguishable from a genuinely unprojected term — which is exactly why the
   check has to be MECHANICAL and cover every adapter at once.

2. **THE TIER COLUMNS MUST BE LINEAR IN EXPECTED GAMES.** The whole reason a league's yards-allowed
   table applies EXACTLY rather than approximately is that
   `sum_bucket tier_points x E[games in bucket]` is linear in the emitted columns. If the buckets
   stopped summing to the projected games, or the scorer stopped being linear in them, the table
   would silently become an approximation while still being reported APPLIED.

3. **A TERM THAT FAILED ITS HELD-OUT GATE MUST STAY CAPTURED.** The story's central discipline is
   that "project it so it's applied" is not automatically an improvement — a term projected with no
   skill still moves the board, on noise, while wearing the "applied" label. So the terms NF-C0e
   TESTED AND REJECTED (`pat_missed`, `fum`, `st_player_td`, `fumble_rec_td`) must have no
   projection column, and that has to be enforced rather than remembered.

4. **THE NET-vs-GROSS YARDS CONVENTION.** nflverse `total_yards` is GROSS; the platforms grade a
   D/ST on NET (sack yardage removed). Using the gross column overstates every defense by ~15
   yards/game and shifts the whole league about one tier rung — a silent, uniform mispricing.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

presets = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.league_presets")
KD = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.kdst_projection")
KS = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.kdst_source")
CT = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.captured_terms")

from quant_sports_intel_models.fantasy_engine import league_config as lc  # noqa: E402
from quant_sports_intel_models.fantasy_engine import settings as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# The terms NF-C0e tested against a held-out degenerate baseline and DELIBERATELY left captured.
# Keyed by the evidence, so a future session that wants to graduate one has to produce a better
# number rather than delete a line. See `ablation_results/nf_c0e_captured_terms.md`.
REJECTED_TERMS = {
    "pat_missed": "8/16 folds on MAE (+0.21%); the clause requires 11. 44% of kicker-seasons "
                  "record zero misses and make rate is unforecastable (rho=0.085), so the arm "
                  "reduces to volume x a league constant.",
    "fum": "MAE wins 7/7 but RMSE LOSES 7/7 — a systematic sign disagreement. 67% of players "
           "fumble zero times, so MAE is minimised by under-projecting (the NF-D11 inversion).",
    "st_player_td": "no per-player return-volume predictor exists, so the only constructible arm "
                    "IS the degenerate (measured gain exactly 0.000, by construction).",
    "fumble_rec_td": "same shape; realized mean 0.004 per player-season.",
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Every adapter target key is a REAL canonical key  (the ESPN-outage guard)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _canonical_keys() -> set[str]:
    return {t.key for t in presets.SCORING_CATALOG} | set(presets.NFL_PROFILE.stat_columns)


def _adapter_targets(module) -> set[str]:
    """Every canonical key an adapter's maps claim to write."""
    out: set[str] = set()
    for name in ("SCORING_KEY_MAP", "STAT_ID_MAP"):
        table = getattr(module, name, None)
        if isinstance(table, dict):
            for value in table.values():
                out.update(value if isinstance(value, tuple) else [value])
    bonus = getattr(module, "BONUS_KEY_MAP", None)
    if isinstance(bonus, dict):
        out.update(stat for _pos, stat in bonus.values())
    return {t for t in out if isinstance(t, str)}


@pytest.mark.parametrize("adapter", ["espn", "sleeper", "yahoo"])
def test_every_adapter_target_is_a_real_canonical_key(adapter):
    """⭐ THE GUARD FOR THE BUG THIS STORY FOUND.

    An adapter that maps onto a key nothing projects does not fail loudly — it produces a config
    that stores the weight faithfully and scores NOTHING, reported as CAPTURED. That is the correct
    behaviour for a term we genuinely cannot project and a SILENT DISASTER for a typo, and the two
    are indistinguishable from inside the coverage machinery. Only a check against the catalog can
    tell them apart, so it belongs here rather than in any one adapter.
    """
    module = pytest.importorskip(f"app.backend.services.platform_import.{adapter}")
    unknown = sorted(_adapter_targets(module) - _canonical_keys())
    assert not unknown, (
        f"{adapter}.py maps onto {unknown}, which are not canonical catalog/profile keys. Such a "
        f"key has no projection column, so every league carrying that rule scores ZERO for it and "
        f"is told it was 'captured'. This is exactly how ESPN leagues lost all passing, rushing "
        f"and receiving yardage.")


def test_the_guard_would_actually_catch_the_bug_it_was_written_for():
    """RED-proof: a guard that cannot fail is worse than none (INC-38/INC-39).

    Rather than trusting that the parametrised test above is live, re-run its exact logic against
    the historical broken map and assert it REJECTS it.
    """
    broken = {"3": ("pass_yd",), "24": ("rush_yd",), "42": ("rec_yd",), "72": ("fum_lost",)}
    targets = {t for v in broken.values() for t in v}
    assert sorted(targets - _canonical_keys()) == ["fum_lost", "pass_yd", "rec_yd", "rush_yd"]


def test_espn_and_sleeper_agree_on_the_canonical_key_for_the_same_concept():
    """The bug was a DISAGREEMENT between adapters, so pin the agreement directly.

    Every adapter is a different vocabulary for one league model; two adapters resolving "passing
    yards" to different canonical keys means at least one of them is not resolving it at all.
    """
    espn = pytest.importorskip("app.backend.services.platform_import.espn")
    sleeper = pytest.importorskip("app.backend.services.platform_import.sleeper")
    for espn_id, sleeper_key in (("3", "pass_yd"), ("24", "rush_yd"),
                                 ("42", "rec_yd"), ("72", "fum_lost")):
        assert espn.SCORING_KEY_MAP[espn_id] == sleeper.SCORING_KEY_MAP[sleeper_key]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The yards-allowed tier family is LINEAR in expected games
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_ya_bucket_index_maps_every_boundary_to_the_right_rung():
    """Inclusive-lower-bound semantics pinned at each edge. An off-by-one here would pay the
    "under 100 yards" bonus (+5 to +6 in a real league) for a 100-yard game, or miss it entirely."""
    yards = [0, 99, 100, 199, 200, 299, 300, 349, 350, 399, 400, 449, 450, 499, 500, 549, 550, 900]
    want = ["0_99", "0_99", "100_199", "100_199", "200_299", "200_299", "300_349", "300_349",
            "350_399", "350_399", "400_449", "400_449", "450_499", "450_499", "500_549",
            "500_549", "550p", "550p"]
    assert [KD.YA_BUCKET_LABELS[i] for i in KD.ya_bucket_index(yards)] == want


def _ya_mix() -> KD.ConditionalBucketMix:
    rng = np.random.default_rng(11)
    rows, seasons = [], (2022, 2023, 2024)
    for i, team in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE")):
        for y in seasons:
            for w in range(1, 18):
                rows.append({"season": y, "team": team, "week": w,
                             "yards_against": float(max(0.0, 280.0 + 30.0 * i
                                                        + rng.normal(0.0, 60.0)))})
    games = pd.DataFrame(rows)
    ts = (games.groupby(["season", "team"], as_index=False)
          .agg(team_games=("yards_against", "size"), yards_against=("yards_against", "sum")))
    ts["yards_against_pg"] = ts.yards_against / ts.team_games
    return KD.fit_yards_allowed_mix(games, ts)


def test_ya_bucket_mass_is_a_distribution_over_the_projected_games():
    """The nine expected-games columns must sum to the games played — that IS the claim that makes
    a tier table exact. If they summed to less, every tier weight would be quietly diluted."""
    mix = _ya_mix()
    games = np.array([17.0, 17.0, 16.0])
    buckets = KD.expected_bucket_games([300.0, 340.0, 390.0], games, mix)
    assert buckets.shape == (3, 9)
    assert np.allclose(buckets.sum(axis=1), games)
    assert (buckets >= 0).all()


def test_a_league_tier_table_is_applied_EXACTLY_not_approximated():
    """⭐ THE PROPERTY THE WHOLE CONSTRUCTION EXISTS FOR.

    Scoring the projection through the real sport-agnostic scorer must reproduce
    `sum_bucket tier_points x expected_games` to floating-point equality. Anything less and the
    league's own table has become an approximation of itself while still reporting APPLIED.
    """
    from quant_sports_intel_models.fantasy_engine.scoring import score_players

    mix = _ya_mix()
    buckets = KD.expected_bucket_games([300.0, 355.0, 410.0], np.array([17.0, 17.0, 17.0]), mix)
    frame = pd.DataFrame({"player_id": ["DST-A", "DST-B", "DST-C"], "position": ["DST"] * 3})
    for j, col in enumerate(KD.YA_BUCKET_COLS):
        frame[col] = buckets[:, j]

    # the operator's real Sleeper ladder, +6 down to -6
    table = dict(zip(KD.YA_BUCKET_LABELS, (6.0, 4.0, 2.0, 1.0, 0.0, -2.0, -4.0, -6.0, -6.0)))
    config = presets.get_preset("full_ppr").with_overrides(
        scoring=lc.ScoringRules(per_stat={f"dst_ya_g_{b}": w for b, w in table.items()}))
    scored = score_players(frame, config, presets.NFL_PROFILE, with_interval=False)

    want = buckets @ np.array([table[b] for b in KD.YA_BUCKET_LABELS])
    got = pd.to_numeric(scored["league_points"], errors="coerce").to_numpy(float)
    assert np.allclose(got, want), f"{got} != {want}"


def test_a_better_defense_scores_higher_under_a_real_yards_tier_table():
    """Face validity, and the direction a sign error would invert."""
    mix = _ya_mix()
    buckets = KD.expected_bucket_games([280.0, 400.0], np.array([17.0, 17.0]), mix)
    weights = np.array([6.0, 4.0, 2.0, 1.0, 0.0, -2.0, -4.0, -6.0, -6.0])
    stingy, leaky = buckets @ weights
    assert stingy > leaky, (stingy, leaky)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Graduated terms are APPLIED; rejected terms STAY CAPTURED
# ══════════════════════════════════════════════════════════════════════════════════════════════
GRADUATED = (
    *(f"dst_ya_g_{b}" for b in KD.YA_BUCKET_LABELS),
    "def_forced_fumble", "two_pt", "pass_td_40p", "rush_td_40p", "rec_td_40p",
)


@pytest.mark.parametrize("key", GRADUATED)
def test_a_graduated_term_resolves_APPLIED(key):
    scoring = lc.ScoringRules(per_stat={key: 3.0})
    _, report = st.resolve_scoring(scoring, presets.NFL_PROFILE)
    verdicts = {t.key: t.verdict for t in report.terms}
    assert verdicts[key] == st.APPLIED


@pytest.mark.parametrize("key", sorted(REJECTED_TERMS))
def test_a_term_that_failed_its_heldout_gate_STAYS_CAPTURED(key):
    """⭐ The story's central discipline, made mechanical.

    "Project it so it's applied" is not automatically an improvement: a term projected with no
    skill still moves the board, on noise, while wearing the "applied" label — which is strictly
    worse than an honest "captured", because the user now believes we modelled it. Each of these
    was TESTED against a degenerate baseline on held-out data and lost. Graduating one later means
    producing a better number, not deleting a line here.
    """
    assert key not in presets.NFL_PROFILE.stat_columns, (
        f"{key} gained a projection column. NF-C0e rejected it: {REJECTED_TERMS[key]} If that has "
        f"genuinely changed, update `ablation_results/nf_c0e_captured_terms.md` with the new "
        f"held-out evidence in the SAME change.")
    scoring = lc.ScoringRules(per_stat={key: 2.0})
    _, report = st.resolve_scoring(scoring, presets.NFL_PROFILE)
    assert {t.key: t.verdict for t in report.terms}[key] == st.CAPTURED


def test_pat_missed_is_rejected_even_though_its_inputs_are_BOTH_projected():
    """The sharpest case: `pat_missed` is one subtraction from two columns we already emit.

    It is left captured anyway, which is the point — availability is not evidence. A term is
    graduated by BEATING A BASELINE, never by being cheap to compute.
    """
    assert "proj_pat_att" in presets.NFL_PROFILE.stat_columns.values()
    assert "proj_pat_made" in presets.NFL_PROFILE.stat_columns.values()
    assert "pat_missed" not in presets.NFL_PROFILE.stat_columns


def test_the_kdst_module_records_why_pat_missed_is_absent():
    """A rejection that lives only in a report is a rejection the next session silently reverses."""
    src = (REPO / "quant_sports_intel_models" / "football" / "nfl" / "fantasy"
           / "kdst_projection.py").read_text()
    assert "proj_pat_missed" in src and "8/16" in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The NET-vs-GROSS yards convention
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_yards_allowed_is_NET_of_sack_yardage_not_gross():
    """nflverse `total_yards` == passing + rushing, both GROSS. The fantasy platforms grade a D/ST
    on the official box score's TOTAL NET yards, which removes sack yardage.

    Measured: net gives 331.6 yards/g in 2023 against the NFL's published 331.1; gross gives 349.0.
    Using gross would overstate every defense by ~15 yards/game and move the whole league roughly
    one tier rung — uniform, silent, and invisible to any per-team check.
    """
    sql = KS._TEAM_GAME_YARDS_SQL
    assert "sack_yards_lost" in sql, "the net-yards correction is missing from the query"
    assert "total_yards" not in sql, (
        "`total_yards` is the GROSS column — using it would overstate every defense by ~15 "
        "yards/game and shift the league about one yards-allowed tier rung")
    # the correction is an ADD because `sack_yards_lost` is stored NEGATIVE
    assert re.search(r"pass_yds\s*\+\s*rush_yds\s*\+\s*sack_yds", sql), sql


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The per-player long-tail terms
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _history() -> pd.DataFrame:
    return pd.DataFrame({
        "season": [2022, 2022, 2023, 2023],
        "player_id": ["a", "b", "a", "b"],
        "two_pt": [1.0, 0.0, 2.0, 1.0],
        "pass_td_40p": [3.0, 0.0, 4.0, 0.0],
        "rush_td_40p": [0.0, 1.0, 0.0, 2.0],
        "pass_td": [30.0, 0.0, 34.0, 0.0],
        "rush_td": [1.0, 9.0, 2.0, 11.0],
        "rec_td": [0.0, 4.0, 0.0, 3.0],
    })


def test_rates_are_measured_in_fold_and_a_later_season_cannot_leak():
    """`fitted_through` is not decoration — a rate fitted on the projection season's own outcomes
    would flatter every downstream number and could not be reproduced at serve time."""
    early = CT.fit_captured_term_rates(_history(), base_season=2022)
    both = CT.fit_captured_term_rates(_history(), base_season=2023)
    assert early.n_seasons == 1 and both.n_seasons == 2
    assert early.long_td_share["pass"] == pytest.approx(3.0 / 30.0)
    assert both.long_td_share["pass"] == pytest.approx(7.0 / 64.0)
    assert early.long_td_share != both.long_td_share


def test_an_unfittable_rate_set_RAISES_instead_of_falling_back_to_the_constants():
    """NF1.7 (a): an anchor that silently fails makes every check resting on it vacuously true.

    Returning the pinned offline constants here would make every rate LOOK measured when none of
    them were, and nothing downstream could tell the difference.
    """
    with pytest.raises(ValueError, match="refusing to fit"):
        CT.fit_captured_term_rates(pd.DataFrame())
    with pytest.raises(ValueError, match="refusing to fit"):
        CT.fit_captured_term_rates(_history(), base_season=1990)


def test_long_td_bonus_is_proportional_to_the_projected_touchdowns():
    """The honest claim: the bonus is applied in proportion to the touchdowns we project. It is NOT
    a claim to know who scores LONG ones — the share is a measured league constant, deliberately."""
    rates = CT.fit_captured_term_rates(_history(), base_season=2023)
    proj = pd.DataFrame({"player_id": ["x", "y"], "position": ["QB", "RB"],
                         "proj_pass_td": [30.0, 0.0], "proj_rush_td": [2.0, 12.0],
                         "proj_rec_td": [0.0, 3.0]})
    out = CT.project_captured_terms(proj, rates)
    assert out["proj_pass_td_40p"].tolist() == pytest.approx(
        [30.0 * rates.long_td_share["pass"], 0.0])
    assert out["proj_rush_td_40p"].tolist() == pytest.approx(
        [2.0 * rates.long_td_share["rush"], 12.0 * rates.long_td_share["rush"]])
    # a receiving TD's length IS its passing play's, so it takes the PASS share, not a third one
    assert out["proj_rec_td_40p"].tolist() == pytest.approx(
        [0.0, 3.0 * rates.long_td_share["pass"]])


def test_two_pt_is_overwritten_never_left_as_the_NaN_mvp1_declares():
    """MVP-1 declares `proj_two_pt` and sets it to NaN — a column that exists carrying no value.

    Downstream that was already honest (the exporter drops an all-null field, so `two_pt` reported
    CAPTURED), but it is a trap: a consumer reading the frame directly sees a real column name and
    scores `weight x NaN`. Graduating the term has to close that too.
    """
    proj = pd.DataFrame({"player_id": ["x"], "position": ["QB"], "proj_two_pt": [np.nan],
                         "proj_pass_td": [30.0], "proj_rush_td": [2.0], "proj_rec_td": [0.0]})
    out = CT.project_captured_terms(proj, CT.fit_captured_term_rates(_history()))
    assert out["proj_two_pt"].notna().all()
    assert out["proj_two_pt"].iloc[0] > 0


def test_a_missing_volume_column_yields_NO_bonus_column_rather_than_zeros():
    """A zeroed bonus column would be APPLIED-and-wrong ("this player scores no long touchdowns");
    an ABSENT one is correctly reported CAPTURED. The difference is the whole coverage contract."""
    proj = pd.DataFrame({"player_id": ["x"], "position": ["RB"], "proj_rush_td": [10.0]})
    out = CT.project_captured_terms(proj, CT.fit_captured_term_rates(_history()))
    assert "proj_rush_td_40p" in out.columns
    assert "proj_pass_td_40p" not in out.columns


def test_the_degenerate_baseline_is_reusable_and_refuses_an_empty_history():
    """The thing every graduation had to beat is exposed as a function, not buried in a script, so
    next season's re-run measures against the SAME baseline rather than a re-derived one."""
    hist = pd.DataFrame({"position": ["QB", "QB", "RB"], "two_pt": [2.0, 0.0, 4.0]})
    got = CT.degenerate_baseline(hist, ["QB", "RB", "TE"], "two_pt")
    assert got.tolist() == pytest.approx([1.0, 4.0, 2.0])   # TE unseen -> the overall mean
    with pytest.raises(ValueError):
        CT.degenerate_baseline(pd.DataFrame(), ["QB"], "two_pt")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The projection emits the family only when it was actually fitted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_an_unfitted_yards_family_emits_NO_columns_rather_than_zeros():
    """⭐ The honest-degradation rule, at the family level.

    `resolve_scoring` decides coverage against the columns the frame REALLY has. A model with no
    yards mix that emitted nine zero columns would report the league's tier table APPLIED and score
    it as "this defense allows no yardage at all" — a fabricated number wearing an applied label.
    Emitting nothing makes the same situation report CAPTURED, which is the truth.
    """
    universe = pd.DataFrame({"team": ["AAA", "BBB"], "scheduled_games": [17.0, 17.0]})
    team_def = pd.DataFrame({"season": [2024, 2024], "team": ["AAA", "BBB"], "games": [17.0, 17.0],
                             "def_sacks": [40.0, 30.0], "def_int": [12.0, 8.0],
                             "def_fumble_rec": [9.0, 7.0], "def_td": [2.0, 1.0],
                             "st_td": [1.0, 0.0], "def_safety": [0.0, 1.0],
                             "def_blocked_kick": [1.0, 0.0], "def_forced_fumble": [14.0, 10.0]})
    team_pts = pd.DataFrame({"season": [2024, 2024], "team": ["AAA", "BBB"],
                             "team_games": [17.0, 17.0], "points_against": [300.0, 400.0],
                             "points_for": [400.0, 300.0], "points_against_pg": [17.6, 23.5],
                             "points_for_pg": [23.5, 17.6]})
    sos = pd.DataFrame({"team": ["AAA", "BBB"], "sos_off_z": [0.0, 0.0], "sos_off_pg": [22.0, 22.0]})

    pa_games = pd.DataFrame([{"season": 2024, "team": t, "week": w,
                              "points_against": float(17 + (w % 11) * 2)}
                             for t in ("AAA", "BBB") for w in range(1, 18)])
    model = KD.DstModel(components={c: KD.LinearShrink(0.0, 1.0, 1.0, 50) for c in KD.DST_COMPONENTS},
                        pa_league_mean=20.0, pa_intercept=20.0)
    model.pa_mix = KD.fit_points_allowed_mix(pa_games, team_pts)
    assert model.ya_mix is None

    out = KD.project_dst(universe, team_def, team_pts, model, sos, 2025)
    for col in KD.YA_BUCKET_COLS:
        assert col not in out.columns, f"{col} was emitted by a model that never fitted the family"
    # and the POINTS family, which WAS fitted, is still there — the skip must be surgical
    for col in KD.PA_BUCKET_COLS:
        assert col in out.columns


def test_a_component_absent_from_the_loaded_history_is_skipped_not_zero_filled():
    """The same rule one level down. A zero-filled component would be fitted, projected and scored
    as APPLIED against data that was never loaded."""
    seasons = (2022, 2023, 2024)
    rows = [{"season": y, "team": t, "games": 17.0, "def_sacks": 30.0 + 5 * i,
             "def_int": 10.0, "def_fumble_rec": 8.0, "def_td": 1.0, "st_td": 1.0,
             "def_safety": 0.0, "def_blocked_kick": 1.0}          # NO def_forced_fumble
            for i, t in enumerate(("AAA", "BBB", "CCC")) for y in seasons]
    team_def = pd.DataFrame(rows)
    team_pts = pd.DataFrame([{"season": y, "team": t, "team_games": 17.0,
                              "points_against": 340.0, "points_for": 350.0,
                              "points_against_pg": 20.0, "points_for_pg": 20.6}
                             for t in ("AAA", "BBB", "CCC") for y in seasons])
    panel = KD.build_dst_training_panel(team_def, team_pts, None, [2023, 2024])
    assert "real_def_forced_fumble" not in panel.columns
    assert "real_def_sacks" in panel.columns
