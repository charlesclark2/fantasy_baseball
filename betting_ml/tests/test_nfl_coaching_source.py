"""NF-D10 — OC / head-coach change source: the pure construct, offline.

Covers the three things that can silently be WRONG in this ingest:

  1. **The leakage-safe as-of** (the story's correctness crux) — a MID-SEASON change must be
     invisible to its own season's pre-season feature and visible to the next one. The rule has to
     be safe by DATING, not by discarding, so both halves are asserted.
  2. **The Wikipedia staff parse** — every miss found while probing 672 real pages is pinned here
     as a regression case: combined titles ('Assistant head coach/offensive coordinator'), an
     ASSISTANT coordinator that must NOT be read as the coordinator, an interim listed FIRST, a
     '(through week 8)' annotation that still describes the week-1 holder, prose bullets outside
     the `==Staff==` section, and a staff TEMPLATE whose `<noinclude>` docs carry headings.
  3. **The feature semantics** — `new_oc` NaN (not 0) when the predecessor is unknown, tenure
     counted off who FINISHED each prior season, and `oc_prior_pass_rate_delta` exactly 0.0 for a
     retained OC vs NaN for a first-time coordinator.

No network, no lake, no DuckDB — every helper under test is pure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import coaching_source as C
from quant_sports_intel_models.football.nfl.fantasy import nf1_2_model as M12


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Franchise naming (a relocation changes the ARTICLE TITLE — one name per team would 404 history)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("team,season,expected", [
    ("LAR", 2012, "St. Louis Rams"),
    ("LAR", 2016, "Los Angeles Rams"),
    ("LAC", 2016, "San Diego Chargers"),
    ("LAC", 2017, "Los Angeles Chargers"),
    ("LV", 2019, "Oakland Raiders"),
    ("LV", 2020, "Las Vegas Raiders"),
    ("WAS", 2019, "Washington Redskins"),
    ("WAS", 2020, "Washington Football Team"),
    ("WAS", 2022, "Washington Commanders"),
    ("KC", 2011, "Kansas City Chiefs"),
])
def test_franchise_name_is_era_aware(team, season, expected):
    assert C.franchise_name(team, season) == expected
    assert C.season_article_title(team, season) == f"{season} {expected} season"


def test_unknown_team_yields_no_title():
    assert C.franchise_name("XXX", 2020) is None
    assert C.season_article_title("XXX", 2020) is None


def test_all_32_teams_map_across_the_window():
    assert len(C.TEAMS) == 32
    for season in (2006, 2016, 2026):
        assert all(C.franchise_name(t, season) for t in C.TEAMS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The wikitext parse
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("raw,expected", [
    ("[[Scott Linehan]]", "Scott Linehan"),
    ("[[Ben Johnson (American football coach)|Ben Johnson]]", "Ben Johnson"),
    ("[[Greg Olson (American football)|Greg Olson]] (interim)", "Greg Olson"),
    ("Bob Smith<ref>{{cite web|url=x}}</ref>", "Bob Smith"),
    ("'''[[Dan Campbell]]'''", "Dan Campbell"),
    ("", ""),
])
def test_clean_coach_name(raw, expected):
    assert C.clean_coach_name(raw) == expected


_ARTICLE = """{{Infobox}}
==Offseason==
* January 4: [[Mike Sullivan (American football coach)|Mike Sullivan]] was the Giants'
offensive coordinator during the previous three seasons.
==Staff==
'''Head coaches'''
*Head coach – [[Andy Reid]]
*Assistant head coach/offensive coordinator – [[Marty Mornhinweg]]
'''Offensive coaches'''
*Assistant offensive coordinator – [[Nobody Atall]]
*Quarterbacks – [[Pat Shurmur]]
*Offensive quality control – [[Someone Else]]
==Schedule==
* the offensive coordinator was fired in week 12
"""


def test_prose_outside_the_staff_section_is_not_parsed_as_staff():
    """The bug this pins: `*` bullets in Offseason/Schedule prose also contain the role token, and
    matching them made a PROSE SENTENCE outrank the real coordinator on real articles."""
    rows = C.parse_staff_roles(_ARTICLE, C.ROLE_OC)
    assert [r["coach_name"] for r in rows] == ["Marty Mornhinweg"]
    assert rows[0]["is_season_opener"] is True


def test_combined_title_is_the_coordinator_but_an_assistant_coordinator_is_not():
    names = [r["coach_name"] for r in C.parse_staff_roles(_ARTICLE, C.ROLE_OC)]
    assert "Marty Mornhinweg" in names          # 'Assistant head coach/offensive coordinator'
    assert "Nobody Atall" not in names          # 'Assistant offensive coordinator'
    assert "Someone Else" not in names          # 'Offensive quality control'


def test_article_with_no_staff_section_yields_no_rows_rather_than_prose():
    text = "==Offseason==\n*Offensive coordinator talk in prose – [[Ghost Coach]]\n==Schedule==\nx"
    assert C.parse_staff_roles(text, C.ROLE_OC) == []


def test_interim_listed_first_still_leaves_a_season_opener():
    """Real 2018 BAL/CLE shape: the interim's combined title sorts ABOVE the plain coordinator
    line, which would otherwise leave the season with no week-1 holder at all."""
    text = ("==Staff==\n"
            "*Assistant head coach/interim offensive coordinator – [[Greg Roman]]\n"
            "*Offensive coordinator – [[Marty Mornhinweg]]\n")
    rows = C.parse_staff_roles(text, C.ROLE_OC)
    assert [(r["coach_name"], r["is_season_opener"]) for r in rows] == [
        ("Greg Roman", False), ("Marty Mornhinweg", True)]


def test_through_week_annotation_describes_the_week_one_holder():
    """Real 2016 MIN shape: '(through week 8)' is the man who STARTED the season, not a
    replacement — reading the bare '8' as a start week loses him."""
    text = ("==Staff==\n"
            "*Offensive Coordinator (through week 8) – [[Norv Turner]]\n"
            "*Offensive Coordinator (weeks 9-17)/tight ends – [[Pat Shurmur]]\n")
    rows = C.parse_staff_roles(text, C.ROLE_OC)
    assert rows[0]["coach_name"] == "Norv Turner" and rows[0]["is_season_opener"] is True
    assert rows[1]["is_season_opener"] is False


def test_staff_template_noinclude_headings_do_not_hide_the_body():
    """A staff TEMPLATE's transcluded body has no headings, but its `<noinclude>` documentation
    does — leaving them in made every template look like an article with no staff section and
    silently zeroed the CURRENT board year."""
    tmpl = ("{{Navbox}}\n;Head coaches\n*Head coach – [[Ben Johnson]]\n"
            ";Offensive coaches\n*Offensive coordinator – [[Press Taylor]]\n"
            "<noinclude>\n==Documentation==\nSee usage.\n</noinclude>")
    assert [r["coach_name"] for r in C.parse_staff_roles(tmpl, C.ROLE_OC)] == ["Press Taylor"]


def test_oc_stints_date_the_opener_at_the_asof_anchor_and_the_replacement_inside_the_season():
    text = ("==Staff==\n"
            "*Offensive coordinator – [[Alpha One]]\n"
            "*Interim offensive coordinator (weeks 10-17) – [[Beta Two]]\n")
    st = C.oc_stints_from_wikitext(text, "KC", 2019)
    assert list(st["coach_name"]) == ["Alpha One", "Beta Two"]
    assert st.iloc[0]["effective_date"] == str(C.asof_date(2019))
    assert st.iloc[0]["is_season_opener"]
    assert pd.Timestamp(st.iloc[1]["effective_date"]) > pd.Timestamp(C.asof_date(2019))
    assert not st.iloc[1]["is_season_opener"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Head-coach stints from the per-game schedule
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _games() -> pd.DataFrame:
    """CAR 2022: Matt Rhule opens, fired after week 5, Steve Wilks takes over from week 6."""
    rows = []
    for wk in range(1, 11):
        coach = "Matt Rhule" if wk <= 5 else "Steve Wilks"
        rows.append({"season": 2022, "week": wk, "gameday": f"2022-09-{10 + wk:02d}",
                     "game_type": "REG", "home_team": "CAR", "home_coach": coach,
                     "away_team": "ATL", "away_coach": "Arthur Smith"})
    rows.append({"season": 2022, "week": 20, "gameday": "2023-01-29", "game_type": "CON",
                 "home_team": "CAR", "home_coach": "Playoff Ghost",
                 "away_team": "ATL", "away_coach": "Arthur Smith"})
    return pd.DataFrame(rows)


def test_head_coach_stints_are_one_row_per_contiguous_run_with_exact_dates():
    st = C.head_coach_stints(_games())
    car = st[st["team"] == "CAR"].reset_index(drop=True)
    assert list(car["coach_name"]) == ["Matt Rhule", "Steve Wilks"]
    # the opener is anchored to the offseason as-of date (his hire was public before Week 1)…
    assert car.loc[0, "effective_date"] == str(C.asof_date(2022))
    assert bool(car.loc[0, "is_season_opener"])
    # …the successor carries the ACTUAL gameday of his first game
    assert car.loc[1, "effective_date"] == "2022-09-16"
    assert not bool(car.loc[1, "is_season_opener"])


def test_head_coach_stints_ignore_the_postseason():
    """Only REG games define a season's coaching regime — a playoff row must not open a stint."""
    st = C.head_coach_stints(_games())
    assert "Playoff Ghost" not in set(st["coach_name"])


def test_head_coach_stints_normalise_legacy_team_codes():
    g = pd.DataFrame([{"season": 2015, "week": 1, "gameday": "2015-09-13", "game_type": "REG",
                       "home_team": "STL", "home_coach": "Jeff Fisher",
                       "away_team": "OAK", "away_coach": "Jack Del Rio"}])
    st = C.head_coach_stints(g)
    assert set(st["team"]) == {"LAR", "LV"}


def test_empty_games_gives_an_empty_typed_frame():
    out = C.head_coach_stints(pd.DataFrame())
    assert out.empty and "effective_date" in out.columns


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 🚨 THE LEAKAGE CRUX
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _stints() -> pd.DataFrame:
    """CAR: Rhule opens 2022 and is replaced mid-season by Wilks; Reich opens 2023."""
    return pd.DataFrame([
        {"season": 2021, "team": "CAR", "role": "HC", "coach_name": "Matt Rhule",
         "effective_date": "2021-03-15", "is_season_opener": True, "annotation": "", "source": "t"},
        {"season": 2022, "team": "CAR", "role": "HC", "coach_name": "Matt Rhule",
         "effective_date": "2022-03-15", "is_season_opener": True, "annotation": "", "source": "t"},
        {"season": 2022, "team": "CAR", "role": "HC", "coach_name": "Steve Wilks",
         "effective_date": "2022-10-16", "is_season_opener": False, "annotation": "from week 6",
         "source": "t"},
        {"season": 2023, "team": "CAR", "role": "HC", "coach_name": "Frank Reich",
         "effective_date": "2023-03-15", "is_season_opener": True, "annotation": "", "source": "t"},
    ])


def test_a_midseason_change_cannot_reach_its_own_seasons_preseason_feature():
    known = C.known_stints(_stints(), 2022)
    assert set(known["coach_name"]) == {"Matt Rhule"}
    assert "Steve Wilks" not in set(known["coach_name"])


def test_the_same_midseason_change_IS_visible_to_the_following_season():
    """The rule must be safe by DATING, not by discarding — a firing is legitimate history for the
    next projection."""
    known = C.known_stints(_stints(), 2023)
    assert "Steve Wilks" in set(known["coach_name"])


def test_a_stint_with_no_parseable_date_fails_closed():
    s = _stints()
    s.loc[len(s)] = {"season": 2022, "team": "CAR", "role": "OC", "coach_name": "No Date",
                     "effective_date": None, "is_season_opener": True, "annotation": "",
                     "source": "t"}
    assert "No Date" not in set(C.known_stints(s, 2030)["coach_name"])


def test_asof_anchor_sits_between_the_offseason_and_week_one():
    d = C.asof_date(2024)
    assert d.year == 2024 and (d.month, d.day) == (3, 15)
    # a January hire is known; a September in-season change is not
    assert pd.Timestamp("2024-01-20") < pd.Timestamp(d) < pd.Timestamp("2024-09-05")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The per-team feature build
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _regime_stints() -> pd.DataFrame:
    """KC keeps its OC three straight seasons; DEN hires 2023's KC-adjacent coordinator away from
    BUF in 2024 (so `oc_prev_team`/`oc_prev_season` resolve)."""
    rows = []
    for season, oc in ((2022, "Steady Sam"), (2023, "Steady Sam"), (2024, "Steady Sam")):
        rows.append({"season": season, "team": "KC", "role": "OC", "coach_name": oc,
                     "effective_date": str(C.asof_date(season)), "is_season_opener": True,
                     "annotation": "", "source": "wiki"})
        rows.append({"season": season, "team": "KC", "role": "HC", "coach_name": "Andy Reid",
                     "effective_date": str(C.asof_date(season)), "is_season_opener": True,
                     "annotation": "", "source": "sched"})
    for season, oc, hc in ((2022, "Ken Dorsey", "Sean McDermott"),
                           (2023, "Ken Dorsey", "Sean McDermott")):
        rows.append({"season": season, "team": "BUF", "role": "OC", "coach_name": oc,
                     "effective_date": str(C.asof_date(season)), "is_season_opener": True,
                     "annotation": "", "source": "wiki"})
        rows.append({"season": season, "team": "BUF", "role": "HC", "coach_name": hc,
                     "effective_date": str(C.asof_date(season)), "is_season_opener": True,
                     "annotation": "", "source": "sched"})
    rows += [
        {"season": 2023, "team": "DEN", "role": "OC", "coach_name": "Old Guy",
         "effective_date": str(C.asof_date(2023)), "is_season_opener": True, "annotation": "",
         "source": "wiki"},
        {"season": 2023, "team": "DEN", "role": "HC", "coach_name": "Sean Payton",
         "effective_date": str(C.asof_date(2023)), "is_season_opener": True, "annotation": "",
         "source": "sched"},
        {"season": 2024, "team": "DEN", "role": "OC", "coach_name": "Ken Dorsey",
         "effective_date": str(C.asof_date(2024)), "is_season_opener": True, "annotation": "",
         "source": "wiki"},
        {"season": 2024, "team": "DEN", "role": "HC", "coach_name": "Sean Payton",
         "effective_date": str(C.asof_date(2024)), "is_season_opener": True, "annotation": "",
         "source": "sched"},
    ]
    return pd.DataFrame(rows)


def test_retained_staff_reads_as_no_change_full_continuity_and_growing_tenure():
    f = C.build_team_coach_features(_regime_stints(), 2024)
    kc = f[f["team"] == "KC"].iloc[0]
    assert kc["new_oc"] == 0.0 and kc["new_hc"] == 0.0
    assert kc["coach_continuity"] == 1.0
    assert kc["oc_tenure_years"] == 2.0          # 2022 + 2023 held before the 2024 projection
    assert pd.isna(kc["oc_prev_team"])


def test_a_new_oc_carries_his_previous_job_and_partial_continuity():
    f = C.build_team_coach_features(_regime_stints(), 2024)
    den = f[f["team"] == "DEN"].iloc[0]
    assert den["new_oc"] == 1.0 and den["new_hc"] == 0.0
    assert den["coach_continuity"] == 0.5
    assert den["oc_tenure_years"] == 0.0
    assert den["oc_prev_team"] == "BUF" and den["oc_prev_season"] == 2023.0


def test_an_unknown_predecessor_gives_NaN_not_a_silent_zero():
    """A Wikipedia parse gap in season Y−1 must not be read as 'no coordinator change'."""
    s = _regime_stints()
    s = s[~((s["team"] == "KC") & (s["role"] == "OC") & (s["season"] == 2023))]
    f = C.build_team_coach_features(s, 2024)
    kc = f[f["team"] == "KC"].iloc[0]
    assert pd.isna(kc["new_oc"])
    assert pd.isna(kc["coach_continuity"])


def test_a_team_with_no_parsed_oc_still_gets_a_row_with_its_head_coach():
    s = _regime_stints()
    s = s[~((s["team"] == "DEN") & (s["role"] == "OC"))]
    f = C.build_team_coach_features(s, 2024)
    den = f[f["team"] == "DEN"]
    assert len(den) == 1 and den.iloc[0]["hc_name"] == "Sean Payton"
    assert pd.isna(den.iloc[0]["oc_name"])


def test_coverage_report_counts_only_computable_flags():
    st = _regime_stints()
    rep = C.coverage_report(st, C.build_team_coach_features(st, 2024), 2024)
    assert rep["season"] == 2024
    assert rep["hc_coverage"] == 1.0
    assert rep["new_oc_computable"] >= 2


def test_an_all_nan_season_still_lands_a_STRING_previous_team_column():
    """🧨 The Delta landmine, pinned: a season where NO team has a resolvable previous OC job
    leaves `oc_prev_team` all-NaN → float64 → the Delta column is CREATED as Float64 and the next
    season's real team codes die with `Cannot cast string 'CLE' to Float64`. The writer-side pin
    must survive an entirely empty column."""
    s = _regime_stints()
    f = C.pin_feature_dtypes(C.build_team_coach_features(s, 2023))  # 2023 has no cross-team hire
    assert f["oc_prev_team"].isna().all()
    assert str(f["oc_prev_team"].dtype) == "string"
    assert str(f["oc_prev_season"].dtype) == "float64"
    assert str(f["season"].dtype) == "int64"
    # and a season that DOES carry codes pins to the same dtype, so the partitions agree
    g = C.pin_feature_dtypes(C.build_team_coach_features(s, 2024))
    assert g["oc_prev_team"].dtype == f["oc_prev_team"].dtype


def test_stint_dtypes_are_pinned_for_the_audit_table_too():
    st = C.pin_stint_dtypes(_regime_stints())
    assert str(st["annotation"].dtype) == "string"   # empty on every opener-only season
    assert st["is_season_opener"].dtype == bool
    assert str(st["season"].dtype) == "int64"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The model-side attach (H-COACH) — nf1_2_model.attach_coach
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"player_id": "p1", "position": "WR", "base_season": 2023, "projection_season": 2024,
         "proj_team": "DEN", "base_team": "DEN"},
        {"player_id": "p2", "position": "RB", "base_season": 2023, "projection_season": 2024,
         "proj_team": "KC", "base_team": "KC"},
        {"player_id": "p3", "position": "TE", "base_season": 2023, "projection_season": 2024,
         "proj_team": "LA", "base_team": "KC"},   # legacy code — must normalise to LAR
    ])


def _team_rates() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": 2023, "team": "DEN", "off_pass_rate": 0.55, "off_plays_per_game": 62.0},
        {"season": 2023, "team": "BUF", "off_pass_rate": 0.65, "off_plays_per_game": 65.0},
        {"season": 2023, "team": "KC", "off_pass_rate": 0.60, "off_plays_per_game": 64.0},
        {"season": 2023, "team": "LAR", "off_pass_rate": 0.58, "off_plays_per_game": 63.0},
    ])


def test_attach_coach_joins_the_FORWARD_team_and_prices_the_scheme_shock():
    coach = C.build_team_coach_features(_regime_stints(), 2024)
    out = M12.attach_coach(_frame(), coach, _team_rates())
    den = out[out["player_id"] == "p1"].iloc[0]
    # DEN's new OC ran BUF's 0.65-pass-rate offence; DEN's own base rate was 0.55 → +0.10 shock
    assert den["new_oc"] == 1.0
    assert den["oc_prior_pass_rate_delta"] == pytest.approx(0.10, abs=1e-9)


def test_a_retained_oc_scores_exactly_zero_shock_not_NaN():
    coach = C.build_team_coach_features(_regime_stints(), 2024)
    out = M12.attach_coach(_frame(), coach, _team_rates())
    kc = out[out["player_id"] == "p2"].iloc[0]
    assert kc["new_oc"] == 0.0
    assert kc["oc_prior_pass_rate_delta"] == 0.0


def test_a_mover_carries_his_NEW_teams_regime_under_a_legacy_team_code():
    """p3's base team is KC but he projects to the Rams, keyed 'LA' upstream and 'LAR' in the
    coach table — the crosswalk landmine every source-boundary join in this repo hits."""
    coach = pd.DataFrame([{"season": 2024, "team": "LAR", "new_oc": 1.0, "oc_tenure_years": 0.0,
                           "new_hc": 0.0, "coach_continuity": 0.5, "oc_prev_team": np.nan,
                           "oc_prev_season": np.nan}])
    out = M12.attach_coach(_frame(), coach, _team_rates())
    p3 = out[out["player_id"] == "p3"].iloc[0]
    assert p3["new_oc"] == 1.0 and p3["coach_continuity"] == 0.5
    # a new OC with no prior coordinator season is an honest unknown, never a fabricated 0
    assert pd.isna(p3["oc_prior_pass_rate_delta"])


def test_attach_coach_with_no_source_leaves_every_column_NaN_and_never_raises():
    out = M12.attach_coach(_frame(), pd.DataFrame(), _team_rates())
    for col in M12.REFINEMENT_FAMILIES["coach"]:
        assert col in out.columns and out[col].isna().all()
    assert len(out) == 3


def test_add_refinement_features_includes_the_coach_family():
    inputs = M12.RefinementInputs(team_rates=_team_rates(),
                                  coach=C.build_team_coach_features(_regime_stints(), 2024))
    out = M12.add_refinement_features(_frame().assign(mvp1_fp=10.0, target_share=0.1,
                                                      carry_share=0.0), inputs)
    assert out.loc[out["player_id"] == "p1", "new_oc"].iloc[0] == 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Registry wiring — the family must actually REACH the model, in both harnesses
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_coach_family_is_registered_for_every_skill_position():
    assert "coach" in M12.REFINEMENT_FAMILIES
    assert set(M12.FAMILY_POSITIONS["coach"]) == {"QB", "RB", "WR", "TE"}
    for pos in ("QB", "RB", "WR", "TE"):
        assert set(M12.REFINEMENT_FAMILIES["coach"]) <= set(M12.POSITION_FEATURES[pos])
    assert "coach" in M12.FEATURE_GROUPS


def test_nf1_5_bundles_carry_the_pre_registered_coach_hypotheses():
    from quant_sports_intel_models.football.nfl.fantasy import nf1_5_model as M15

    assert M15.BLIND_BUNDLES["base_system_coach"] == ("xfp", "system", "coach")
    assert "coach" in M15.BLIND_BUNDLES["env_coach"]
    assert "coach" in M15.BLIND_BUNDLES["kitchen_sink"]
    # the direct-test bundle must genuinely differ from its foil, else the sweep tests nothing
    for pos in ("QB", "RB", "WR", "TE"):
        assert set(M15.bundle_features("base_system_coach", pos)) > set(
            M15.bundle_features("base_xfp", pos))
