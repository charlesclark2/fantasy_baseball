"""NF-D8 — Contract / financial feature source. Pure/offline unit tests for the team crosswalk,
the nested per-year `cols` flatten, the as-of-preseason active-contract selection (leakage
safety), the team cap aggregates (O-line total, skill concentration), and the guaranteed-ratio /
log-investment math — all on SYNTHETIC contract frames, no network. Fast gate only."""
import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import contract_source as C


# ── team crosswalk ──────────────────────────────────────────────────────────────────────────────
def test_team_abbr_known_and_unknown():
    assert C.team_abbr("Bengals") == "CIN"
    assert C.team_abbr("Redskins") == "WAS"
    assert C.team_abbr("Washington") == "WAS"
    assert C.team_abbr("Commanders") == "WAS"
    assert C.team_abbr("Total") is None
    assert C.team_abbr("") is None
    assert C.team_abbr(None) is None
    assert C.team_abbr("Not A Team") is None


# ── flatten_contract_years ───────────────────────────────────────────────────────────────────────
def _contract(gsis_id="00-0000001", player="Test Player", position="QB", year_signed=2023,
             years=4.0, value=100.0, apy=25.0, guaranteed=60.0, otc_id=1, is_active=True,
             cols=None):
    if cols is None:
        cols = [
            {"year": "2023", "team": "Bengals", "cap_number": 10.0, "base_salary": 1.0,
             "guaranteed_salary": 10.0, "cap_percent": 0.05},
            {"year": "2024", "team": "Bengals", "cap_number": 20.0, "base_salary": 2.0,
             "guaranteed_salary": 5.0, "cap_percent": 0.09},
            {"year": "Total", "team": "Total", "cap_number": 30.0, "base_salary": 3.0,
             "guaranteed_salary": 15.0, "cap_percent": None},
        ]
    return {"gsis_id": gsis_id, "player": player, "position": position, "year_signed": year_signed,
            "years": years, "value": value, "apy": apy, "guaranteed": guaranteed, "otc_id": otc_id,
            "is_active": is_active, "cols": np.array(cols, dtype=object)}


def test_flatten_drops_total_row_and_keeps_year_rows():
    df = pd.DataFrame([_contract()])
    flat = C.flatten_contract_years(df)
    assert set(flat["year"]) == {2023, 2024}          # 'Total' row dropped
    assert set(flat["team_abbr"]) == {"CIN"}
    row2024 = flat[flat["year"] == 2024].iloc[0]
    assert row2024["cap_number"] == pytest.approx(20.0)
    assert row2024["gsis_id"] == "00-0000001"


def test_flatten_drops_garbage_year_and_out_of_range():
    bad_cols = [
        {"year": "201", "team": "Chargers", "cap_number": 0.5, "base_salary": 0.5,
         "guaranteed_salary": 0.0, "cap_percent": None},   # truncated-year artifact
        {"year": "0", "team": "Jets", "cap_number": 0.48, "base_salary": 0.48,
         "guaranteed_salary": None, "cap_percent": None},  # placeholder-year artifact
        {"year": "2024", "team": "Jets", "cap_number": 1.0, "base_salary": 1.0,
         "guaranteed_salary": 1.0, "cap_percent": 0.01},   # a real row
    ]
    df = pd.DataFrame([_contract(cols=bad_cols, year_signed=2024)])
    flat = C.flatten_contract_years(df)
    assert list(flat["year"]) == [2024]


def test_flatten_handles_none_cols_and_empty_input():
    df = pd.DataFrame([_contract(cols=None)]).assign(cols=[None])
    assert C.flatten_contract_years(df).empty
    assert C.flatten_contract_years(pd.DataFrame()).empty


# ── active_contract_rows (leakage safety) ────────────────────────────────────────────────────────
def test_active_contract_rows_excludes_future_signed_contracts():
    # a contract signed in 2025 must NOT be usable when projecting 2024 (would leak a future deal).
    flat = pd.DataFrame([
        {"gsis_id": "P1", "player": "A", "position": "QB", "year_signed": 2025, "years": 3.0,
         "value": 90.0, "apy": 30.0, "guaranteed": 60.0, "otc_id": 2, "is_active": True,
         "year": 2025, "team_abbr": "CIN", "cap_number": 15.0, "base_salary": 1.0,
         "guaranteed_salary": 10.0, "cap_percent": 0.05},
    ])
    assert C.active_contract_rows(flat, 2024).empty
    assert len(C.active_contract_rows(flat, 2025)) == 1


def test_active_contract_rows_keeps_most_recently_signed_on_overlap():
    # two contracts both have a 'year == 2024' row (an extension signed in 2024 superseding a
    # 2021 deal's now-void out-year) — the MOST RECENT signing must win.
    flat = pd.DataFrame([
        {"gsis_id": "P1", "player": "A", "position": "WR", "year_signed": 2021, "years": 4.0,
         "value": 40.0, "apy": 10.0, "guaranteed": 8.0, "otc_id": 1, "is_active": False,
         "year": 2024, "team_abbr": "CIN", "cap_number": 5.0, "base_salary": 1.0,
         "guaranteed_salary": 0.0, "cap_percent": 0.02},
        {"gsis_id": "P1", "player": "A", "position": "WR", "year_signed": 2024, "years": 3.0,
         "value": 60.0, "apy": 20.0, "guaranteed": 40.0, "otc_id": 2, "is_active": True,
         "year": 2024, "team_abbr": "CIN", "cap_number": 12.0, "base_salary": 2.0,
         "guaranteed_salary": 12.0, "cap_percent": 0.05},
    ])
    active = C.active_contract_rows(flat, 2024)
    assert len(active) == 1
    assert active.iloc[0]["otc_id"] == 2
    assert active.iloc[0]["cap_number"] == pytest.approx(12.0)


def test_active_contract_rows_drops_missing_gsis():
    flat = pd.DataFrame([
        {"gsis_id": None, "player": "A", "position": "RB", "year_signed": 2023, "years": 2.0,
         "value": 10.0, "apy": 5.0, "guaranteed": 2.0, "otc_id": 1, "is_active": True,
         "year": 2024, "team_abbr": "CIN", "cap_number": 3.0, "base_salary": 1.0,
         "guaranteed_salary": 0.0, "cap_percent": 0.01},
    ])
    assert C.active_contract_rows(flat, 2024).empty


# ── team_cap_aggregates ──────────────────────────────────────────────────────────────────────────
def _active_frame():
    rows = [
        # CIN: 2 OL, 2 skill (one dominant QB)
        {"team_abbr": "CIN", "position": "LT", "cap_number": 20.0},
        {"team_abbr": "CIN", "position": "C", "cap_number": 10.0},
        {"team_abbr": "CIN", "position": "QB", "cap_number": 50.0},
        {"team_abbr": "CIN", "position": "WR", "cap_number": 10.0},
        # DAL: 1 OL, 2 skill (evenly split)
        {"team_abbr": "DAL", "position": "LG", "cap_number": 15.0},
        {"team_abbr": "DAL", "position": "RB", "cap_number": 10.0},
        {"team_abbr": "DAL", "position": "TE", "cap_number": 10.0},
    ]
    return pd.DataFrame(rows)


def test_team_cap_aggregates_ol_and_concentration():
    agg = C.team_cap_aggregates(_active_frame())
    cin = agg[agg.team_abbr == "CIN"].iloc[0]
    dal = agg[agg.team_abbr == "DAL"].iloc[0]

    assert cin["team_total_cap"] == pytest.approx(90.0)
    assert cin["team_ol_cap_total"] == pytest.approx(30.0)
    assert cin["team_ol_cap_pct"] == pytest.approx(30.0 / 90.0)
    assert cin["team_skill_cap_total"] == pytest.approx(60.0)
    # CIN's skill cap is dominated by the QB (50/60) ⇒ HIGH concentration
    cin_hhi = (50 / 60) ** 2 + (10 / 60) ** 2
    assert cin["team_skill_cap_concentration"] == pytest.approx(cin_hhi)

    # DAL's skill cap is split evenly (10/10) ⇒ LOWER concentration than CIN
    dal_hhi = (10 / 20) ** 2 + (10 / 20) ** 2
    assert dal["team_skill_cap_concentration"] == pytest.approx(dal_hhi)
    assert dal["team_skill_cap_concentration"] < cin["team_skill_cap_concentration"]


def test_team_cap_aggregates_empty_and_no_skill_cap_is_nan_not_crash():
    assert C.team_cap_aggregates(pd.DataFrame(columns=["team_abbr", "position", "cap_number"])).empty
    only_ol = pd.DataFrame([{"team_abbr": "SEA", "position": "C", "cap_number": 5.0}])
    agg = C.team_cap_aggregates(only_ol)
    assert agg.iloc[0]["team_skill_cap_total"] == 0.0
    assert np.isnan(agg.iloc[0]["team_skill_cap_concentration"])


# ── guaranteed_ratio / log_investment_feature ────────────────────────────────────────────────────
def test_guaranteed_ratio_basic_and_zero_safe():
    r = C.guaranteed_ratio(np.array([50.0, 0.0, 30.0]), np.array([100.0, 0.0, 0.0]))
    assert r[0] == pytest.approx(0.5)
    assert np.isnan(r[1])   # 0 guaranteed / 0 value ⇒ NaN, not 0/0 crash
    assert np.isnan(r[2])   # nonzero guaranteed but 0 value ⇒ NaN, never a divide error


def test_log_investment_feature_scales_with_both_terms():
    base = C.log_investment_feature(np.array([10.0]), np.array([0.5]))[0]
    higher_salary = C.log_investment_feature(np.array([20.0]), np.array([0.5]))[0]
    higher_guarantee = C.log_investment_feature(np.array([10.0]), np.array([1.0]))[0]
    assert higher_salary > base
    assert higher_guarantee > base
    assert base == pytest.approx(np.log(10.0) * 0.5)
    # a 0/negative apy is floored, never -inf/NaN
    floored = C.log_investment_feature(np.array([0.0, -5.0]), np.array([0.5, 0.5]))
    assert np.all(np.isfinite(floored))


# ── end-to-end assembly (build_contract_features, no network — synthetic `contracts` passed in) ──
def test_build_contract_features_end_to_end_shape_and_merge():
    contracts = pd.DataFrame([
        _contract(gsis_id="00-1111111", player="Star QB", position="QB", year_signed=2023,
                 value=200.0, apy=50.0, guaranteed=150.0,
                 cols=[
                     {"year": "2023", "team": "Bengals", "cap_number": 10.0, "base_salary": 1.0,
                      "guaranteed_salary": 8.0, "cap_percent": 0.05},
                     {"year": "2024", "team": "Bengals", "cap_number": 40.0, "base_salary": 3.0,
                      "guaranteed_salary": 20.0, "cap_percent": 0.15},
                     {"year": "Total", "team": "Total", "cap_number": 50.0, "base_salary": 4.0,
                      "guaranteed_salary": 28.0, "cap_percent": None},
                 ]),
        _contract(gsis_id="00-2222222", player="Left Tackle", position="LT",
                 year_signed=2022, value=80.0, apy=20.0, guaranteed=40.0,
                 cols=[
                     {"year": "2024", "team": "Bengals", "cap_number": 15.0, "base_salary": 2.0,
                      "guaranteed_salary": 5.0, "cap_percent": 0.06},
                     {"year": "Total", "team": "Total", "cap_number": 15.0, "base_salary": 2.0,
                      "guaranteed_salary": 5.0, "cap_percent": None},
                 ]),
    ])
    player, team = C.build_contract_features(2024, contracts=contracts)
    assert set(player["player_id"]) == {"00-1111111", "00-2222222"}
    assert (player["season"] == 2024).all()
    qb = player[player.player_id == "00-1111111"].iloc[0]
    assert qb["cap_number"] == pytest.approx(40.0)
    # team aggregates merged onto the player row
    assert qb["team_total_cap"] == pytest.approx(55.0)   # 40 (QB) + 15 (LT) that season
    assert qb["team_ol_cap_total"] == pytest.approx(15.0)
    assert not team.empty and team.iloc[0]["season"] == 2024


def test_load_contract_features_computes_when_lake_absent():
    contracts = pd.DataFrame([_contract(gsis_id="00-3333333", year_signed=2024)])
    df = C.load_contract_features(2024, from_lake=False, contracts=contracts)
    assert list(df["player_id"]) == ["00-3333333"]
