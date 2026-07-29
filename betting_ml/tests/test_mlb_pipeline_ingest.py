"""E7.11 — the MLB Pipeline ranking parser + its access discipline.

Two classes of thing are pinned here:

  * **The access rule, mechanically.** `/prospects/` is fetched only because robots permits it, and
    `data-graph.mlb.com` is never called because robots forbids it. Those are the story's hard
    constraint, so they are assertions, not comments — including a source-inspection test that the
    forbidden host appears nowhere in the fetching code.
  * **The parse contract.** The page ships a server-rendered Apollo cache; a moved/renamed key must
    RAISE, never return an empty ranking (an org that silently vanishes reads downstream as
    "Pipeline chose not to rank these players", which is a data claim we never made).

The fixture is a hand-cut miniature of the real 2026 page shape (verified live 2026-07-29), not a
1.6 MB capture — the structural facts it encodes are the ones that break.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from betting_ml.scripts.prospect_board.mlb_pipeline import (
    ORG_LIST_DEPTH_BY_ERA,
    ORG_NAME_TO_ABBREV,
    ORG_SLUG_TO_ABBREV,
    OVERALL_LIST_DEPTH_BY_ERA,
    PipelineParseError,
    extract_scouting_grades,
    list_slug,
    parse_rankings_page,
    robots_disallows,
    selection_slug,
)
from betting_ml.scripts.prospect_board.board_assembly import ORG_TO_LEAGUE

_INGEST = Path(__file__).resolve().parents[2] / "scripts" / "ingest_mlb_pipeline_to_s3.py"

# The real robots.txt shape (abridged, verbatim structure as fetched 2026-07-29).
MLB_ROBOTS = """
User-agent: *
Disallow: /test/
Disallow: /api/
Disallow: /mlb/
Disallow: /search
Sitemap: https://www.mlb.com/sitemaps/48-hr-news.xml.gz
"""
DATA_GRAPH_ROBOTS = "User-agent: *\nDisallow: /\n"


def _page(season: int, slug: str, entries: list[dict], entities: dict) -> str:
    """A miniature of the real page: an HTML-entity-escaped Apollo cache in an attribute."""
    payload = (f'"getPlayerRankingsFromSelection({{\\"limit\\":{len(entries)},'
               f'\\"slug\\":\\"{selection_slug(season, slug)}\\"}})":'
               + json.dumps(entries) + ","
               + ",".join(f'"{k}":{json.dumps(v)}' for k, v in entities.items()))
    body = '<div data-props="{&quot;payload&quot;:{' + payload.replace('"', "&quot;") + '}}"></div>'
    return "<html><body>" + body.replace("&quot;", '"') + "</body></html>"


@pytest.fixture
def sample_page() -> str:
    entries = [
        {"rank": 1, "playerEntity": {
            "player": {"__ref": "Person:815908"}, "position": "SS", "eta": "2026",
            "gradesHitting": None, "gradesPitching": None,
            "prospectBio": [
                {"contentTitle": "international",
                 "contentText": "<p><strong>Scouting grades: </strong>Hit: 45 | Power: 45 | "
                                "Run: 50 | Arm: 50 | Field: 50 | Overall: 45</p>"},
                {"contentTitle": "2026",
                 "contentText": "<p><strong>Scouting grades: </strong>Hit: 60 | Power: 60 | "
                                "Run: 60 | Arm: 60 | Field: 55 | Overall: 65</p>"},
            ]}},
        {"rank": 2, "playerEntity": {
            "player": {"__ref": "Person:700001"}, "position": "RHP", "eta": "2027",
            "prospectBio": []}},
    ]
    entities = {
        "Person:815908": {"id": 815908, "useName": "Jesús", "useLastName": "Made",
                          "birthDate": "2007-05-08", "currentAge": 19, "batSideCode": "S",
                          "pitchHandCode": "R", "draftYear": None,
                          "primaryPosition": {"abbreviation": "SS"},
                          "activeRoster": {"__ref": "Team:5015"}},
        "Person:700001": {"id": 700001, "useName": "Robby", "useLastName": "Snelling",
                          "birthDate": "2003-12-19", "currentAge": 22,
                          "activeRoster": {"__ref": "Team:146"}},
        # a minor-league affiliate: the org is its PARENT club
        "Team:5015": {"id": 5015, "name": "Biloxi Shuckers", "parentOrgId": 158,
                      "parentOrgName": "Milwaukee Brewers"},
        # an MLB club: parentOrgName is NULL and the club IS the org
        "Team:146": {"id": 146, "name": "Miami Marlins", "parentOrgId": None,
                     "parentOrgName": None},
    }
    return _page(2026, "top100", entries, entities)


class TestAccessDiscipline:
    def test_the_prospects_path_is_permitted(self):
        assert not robots_disallows(MLB_ROBOTS, list_slug(2026, "top100"))
        assert not robots_disallows(MLB_ROBOTS, list_slug(2026, "orioles"))

    def test_the_paths_mlb_forbids_are_recognised_as_forbidden(self):
        assert robots_disallows(MLB_ROBOTS, "/api/v1/prospects")
        assert robots_disallows(MLB_ROBOTS, "/mlb/anything")
        assert robots_disallows(MLB_ROBOTS, "/search?q=x")

    def test_the_graphql_host_is_disallowed_wholesale(self):
        assert robots_disallows(DATA_GRAPH_ROBOTS, "/graphql")
        assert robots_disallows(DATA_GRAPH_ROBOTS, "/anything/at/all")

    def test_the_ingest_never_references_the_forbidden_host(self):
        """The clean JSON API is robots-blocked; parsing HTML is the WHOLE reason this exists.

        A future session "simplifying" the parser into a data-graph request would be a compliance
        regression that no functional test would catch — so it is caught here, in the source.
        """
        source = _INGEST.read_text(encoding="utf-8")
        code_lines = [ln for ln in source.splitlines()
                      if "data-graph.mlb.com" in ln and "Disallow" not in ln
                      and not ln.strip().startswith(("#", "*", "•"))]
        assert not code_lines, f"data-graph.mlb.com referenced outside a comment: {code_lines}"

    def test_robots_ignores_an_empty_disallow(self):
        """`Disallow:` with no value means allow-everything, per the standard."""
        assert not robots_disallows("User-agent: *\nDisallow:\n", "/prospects/2026/top100/")

    def test_robots_only_applies_the_matching_agent_group(self):
        robots = "User-agent: Bytespider\nDisallow: /\n\nUser-agent: *\nDisallow: /api/\n"
        assert not robots_disallows(robots, "/prospects/2026/top100/")
        assert robots_disallows(robots, "/api/x")


class TestParseRankingsPage:
    def test_parses_rank_and_the_mlbam_id(self, sample_page):
        rows = parse_rankings_page(sample_page, season=2026, list_name="top100")
        assert [r["rank"] for r in rows] == [1, 2]
        # ⭐ the whole reason this source is ingestible — the MLBAM spine, with no name matching
        assert [r["mlbam_id"] for r in rows] == ["815908", "700001"]
        assert rows[0]["player_name"] == "Jesús Made"

    def test_org_current_comes_from_the_affiliates_parent_club(self, sample_page):
        rows = parse_rankings_page(sample_page, season=2026, list_name="top100")
        assert rows[0]["org_current"] == "MIL"

    def test_a_player_rostered_at_mlb_still_resolves_an_org(self, sample_page):
        """An MLB club has a NULL `parentOrgName` — without the fallback these came back org-less
        (3 of the real 2026 Top 100 did)."""
        rows = parse_rankings_page(sample_page, season=2026, list_name="top100")
        assert rows[1]["org_current"] == "MIA"

    def test_a_top100_entry_has_no_POINT_IN_TIME_org(self, sample_page):
        """⚠️ The roster-derived org is as of the FETCH, not the season — on the real 2015 page
        Kris Bryant comes back COL, and he was a Cub. A Top-100 entry carries no org of its own, so
        the unsuffixed (point-in-time) `org` must stay NULL rather than borrow a current one."""
        rows = parse_rankings_page(sample_page, season=2026, list_name="top100")
        assert all(r["org"] is None for r in rows)

    def test_an_org_list_takes_its_org_from_the_url_and_that_IS_point_in_time(self, sample_page):
        """The 2015 Orioles list IS the Orioles' 2015 top 30 — that org is as-of the season."""
        rows = parse_rankings_page(sample_page.replace("top100", "orioles"),
                                   season=2026, list_name="orioles")
        assert {r["org"] for r in rows} == {"BAL"}
        assert {r["list_type"] for r in rows} == {"org"}

    def test_grades_come_from_the_seasons_own_scouting_report(self, sample_page):
        """A prospect accumulates a bio per cycle and the old ones carry OLD grades."""
        rows = parse_rankings_page(sample_page, season=2026, list_name="top100")
        assert rows[0]["pipeline_grade_hit"] == 60.0        # the 2026 report, not the intl one
        assert rows[0]["pipeline_grade_overall"] == 65.0
        assert rows[0]["bio_season"] == 2026

    def test_a_player_without_a_bio_gets_no_grade_columns_not_zeros(self, sample_page):
        rows = parse_rankings_page(sample_page, season=2026, list_name="top100")
        assert not any(k.startswith("pipeline_grade_") for k in rows[1])

    def test_a_missing_selection_raises_rather_than_returning_empty(self, sample_page):
        with pytest.raises(PipelineParseError, match="no ranking payload"):
            parse_rankings_page(sample_page, season=2025, list_name="top100")

    def test_the_raise_points_away_from_the_forbidden_host(self, sample_page):
        with pytest.raises(PipelineParseError, match="robots-blocked"):
            parse_rankings_page(sample_page, season=2025, list_name="top100")

    def test_a_truncated_page_raises(self, sample_page):
        truncated = sample_page[:sample_page.find('"rank": 2')]
        with pytest.raises(PipelineParseError):
            parse_rankings_page(truncated, season=2026, list_name="top100")


class TestScoutingGrades:
    def test_parses_the_published_format(self):
        grades = extract_scouting_grades(
            "<p><strong>Scouting grades: </strong>Hit: 55 | Power: 60 | Run: 45 | Arm: 50 | "
            "Field: 55 | Overall: 60</p><p>He is good.</p>")
        assert grades == {"hit": 55.0, "power": 60.0, "run": 45.0, "arm": 50.0,
                          "field": 55.0, "overall": 60.0}

    def test_parses_a_pitcher_grade_line(self):
        grades = extract_scouting_grades(
            "Scouting grades: Fastball: 70 | Slider: 60 | Changeup: 50 | Control: 45 | Overall: 55")
        assert grades["fastball"] == 70.0 and grades["control"] == 45.0

    def test_a_value_outside_the_20_80_scale_is_dropped_not_carried(self):
        """A year or a jersey number caught by the pair regex is a parse artifact, not a grade."""
        grades = extract_scouting_grades("Scouting grades: Hit: 55 | Draft: 2024 | Power: 90")
        assert grades == {"hit": 55.0}

    def test_no_grades_yields_an_empty_dict_never_zeros(self):
        """A 0 grade reads as 'scouted and terrible' — the E8.0 Prospect-Savant landmine."""
        assert extract_scouting_grades("<p>A fine young player.</p>") == {}
        assert extract_scouting_grades(None) == {}


class TestOrgMaps:
    def test_all_thirty_org_slugs_are_present_and_map_to_a_known_league(self):
        assert len(ORG_SLUG_TO_ABBREV) == 30
        assert len(set(ORG_SLUG_TO_ABBREV.values())) == 30
        # Every org must be AL/NL-mappable — `mlb_league` is the filter a single-league dynasty
        # draft runs on, so an unmapped org silently drops those players from the only view used.
        assert set(ORG_SLUG_TO_ABBREV.values()) == set(ORG_TO_LEAGUE)

    def test_the_club_name_map_covers_the_same_thirty_orgs(self):
        assert set(ORG_NAME_TO_ABBREV.values()) == set(ORG_SLUG_TO_ABBREV.values())

    def test_slug_and_selection_key_shapes(self):
        assert list_slug(2026, "orioles") == "/prospects/2026/orioles/"
        assert selection_slug(2026, "top100") == "sel-pr-2026-top100"


class TestHistoricalSnapshots:
    """The archived seasons — and the two ways a historical page leaks the future into a
    point-in-time row. Both were measured live (2026-07-29), not assumed."""

    @staticmethod
    def _historical_page(season: int) -> str:
        """A 2015-shaped page: the ranking is archived, but the bio list runs PAST the season and
        the Person entity is a LIVE record (Buxton comes back at his 2026 age, on his 2026 club)."""
        entries = [{"rank": 1, "playerEntity": {
            "player": {"__ref": "Person:621439"}, "position": "OF", "eta": None,
            "prospectBio": [
                {"contentTitle": "2014", "contentText": "Scouting grades: Hit: 60 | Power: 50"},
                {"contentTitle": str(season),
                 "contentText": "Scouting grades: Hit: 70 | Power: 55 | Run: 80"},
                {"contentTitle": str(season + 1),
                 "contentText": "Scouting grades: Hit: 40 | Power: 45"},   # ⛔ written LATER
                {"contentTitle": str(season + 3),
                 "contentText": "Scouting grades: Hit: 30 | Power: 40"},   # ⛔ written MUCH later
            ]}}]
        entities = {
            "Person:621439": {"id": 621439, "useName": "Byron", "useLastName": "Buxton",
                              "birthDate": "1993-12-18", "currentAge": 32,   # he was 21 in 2015
                              "activeRoster": {"__ref": "Team:142"}},
            "Team:142": {"id": 142, "name": "Minnesota Twins", "parentOrgId": None,
                         "parentOrgName": None},
        }
        return _page(season, "top100", entries, entities)

    def test_grades_never_come_from_a_report_written_after_the_season(self):
        """🚨 The 2015 page carries 2016/2017/2018 writeups for 65 of its 100 players. Grading a
        2015 snapshot off a 2018 report is three years of hindsight in a point-in-time row."""
        rows = parse_rankings_page(self._historical_page(2015), season=2015, list_name="top100")
        assert rows[0]["bio_season"] == 2015
        assert rows[0]["pipeline_grade_hit"] == 70.0        # the 2015 report
        assert rows[0]["pipeline_grade_run"] == 80.0

    def test_falls_back_to_the_newest_report_not_after_the_season(self):
        """No report for the season itself ⇒ the most recent EARLIER one, never a later one."""
        page = self._historical_page(2015).replace('"contentTitle": "2015"', '"contentTitle": "x"')
        rows = parse_rankings_page(page, season=2015, list_name="top100")
        assert rows[0]["bio_season"] == 2014
        assert rows[0]["pipeline_grade_hit"] == 60.0

    def test_an_undated_report_is_used_only_as_a_last_resort_and_says_so(self):
        entries = [{"rank": 1, "playerEntity": {
            "player": {"__ref": "Person:1"}, "position": "SS", "eta": None,
            "prospectBio": [{"contentTitle": "international",
                             "contentText": "Scouting grades: Hit: 50"}]}}]
        page = _page(2015, "top100", entries, {"Person:1": {"id": 1, "useName": "A",
                                                            "useLastName": "B"}})
        rows = parse_rankings_page(page, season=2015, list_name="top100")
        assert rows[0]["bio_season"] is None       # undated ⇒ NOT era-matched, and visibly so
        assert rows[0]["pipeline_grade_hit"] == 50.0

    def test_live_person_fields_are_suffixed_current_so_the_leak_is_visible(self):
        """`age_current` 32 on a 2015 board is correct-as-labelled and wrong-as-a-feature."""
        rows = parse_rankings_page(self._historical_page(2015), season=2015, list_name="top100")
        assert rows[0]["age_current"] == 32.0
        assert rows[0]["org_current"] == "MIN"
        assert "age" not in rows[0] and "affiliate_team" not in rows[0]

    def test_birth_date_is_unsuffixed_because_it_does_not_change(self):
        """Age as of the season is derivable from `birth_date` + the snapshot — which is the
        leakage-free way to get it."""
        rows = parse_rankings_page(self._historical_page(2015), season=2015, list_name="top100")
        assert rows[0]["birth_date"] == "1993-12-18"


class TestSeasonBackfillArgs:
    """The historical backfill's dating contract — imported from the ingest, which needs no IO."""

    @staticmethod
    def _mod():
        import importlib.util
        spec = importlib.util.spec_from_file_location("_e711_ingest", _INGEST)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_season_spec_parsing(self):
        parse = self._mod().parse_seasons
        assert parse("2015") == [2015]
        assert parse("2019,2021") == [2019, 2021]
        assert parse("2012-2015") == [2012, 2013, 2014, 2015]

    def test_a_past_season_is_never_stamped_with_todays_date(self):
        """🚨 Stamping a 2015 board as 2026-07-29 places a decade-old opinion AFTER every outcome
        it is meant to predict — it would silently invert any accuracy study built on it."""
        resolve = self._mod().resolve_as_of_date
        as_of, guessed = resolve(None, 2015, 2026, "2026-07-29")
        assert as_of == "2015-02-01" and guessed is True

    def test_the_current_season_uses_today(self):
        resolve = self._mod().resolve_as_of_date
        as_of, guessed = resolve(None, 2026, 2026, "2026-07-29")
        assert as_of == "2026-07-29" and guessed is False

    def test_an_explicit_as_of_always_wins(self):
        resolve = self._mod().resolve_as_of_date
        assert resolve("2015-01-20", 2015, 2026, "2026-07-29") == ("2015-01-20", False)

    def test_the_probed_history_bounds_are_recorded(self):
        """Probed live: 2008 → empty; 2010/2011 → Top 50; 2012+ → Top 100. A study must not read
        'absent from the 2010 list' as 'outside the top 100' — that list only went to 50."""
        module = self._mod()
        assert module.EARLIEST_SEASON == 2010
        assert module.TOP50_SEASONS == frozenset({2010, 2011})


class TestBackfillRealities:
    """Facts measured on the FULL 2010–2026 backfill (14,455 rows). Each cost a spot check."""

    def test_a_digit_string_that_is_not_a_year_is_treated_as_undated(self):
        """The live feed contains a `contentTitle` of "201" — digits, so `.isdigit()` accepts it,
        `int()` yields the year 201, and it sorts BELOW every real season. That makes it win the
        "newest bio not after the season" fallback whenever nothing else qualifies, and reports
        `bio_season = 201` into a study. One row in the 2016 backfill did exactly this."""
        entries = [{"rank": 1, "playerEntity": {
            "player": {"__ref": "Person:1"}, "position": "SS", "eta": None,
            "prospectBio": [{"contentTitle": "201",
                             "contentText": "Scouting grades: Hit: 55"}]}}]
        page = _page(2016, "top100", entries,
                     {"Person:1": {"id": 1, "useName": "A", "useLastName": "B"}})
        rows = parse_rankings_page(page, season=2016, list_name="top100")
        assert rows[0]["bio_season"] is None       # undated, not "the year 201"
        assert rows[0]["pipeline_grade_hit"] == 55.0   # the grades are still used, just undated

    def test_a_real_year_still_beats_an_undated_title(self):
        entries = [{"rank": 1, "playerEntity": {
            "player": {"__ref": "Person:1"}, "position": "SS", "eta": None,
            "prospectBio": [{"contentTitle": "201", "contentText": "Scouting grades: Hit: 20"},
                            {"contentTitle": "2016", "contentText": "Scouting grades: Hit: 55"}]}}]
        page = _page(2016, "top100", entries,
                     {"Person:1": {"id": 1, "useName": "A", "useLastName": "B"}})
        rows = parse_rankings_page(page, season=2016, list_name="top100")
        assert rows[0]["bio_season"] == 2016 and rows[0]["pipeline_grade_hit"] == 55.0

    def test_the_published_list_depth_eras_are_recorded(self):
        """🚨 MLB Pipeline's ORG lists were Top 10 (2011), Top 20 (2012-2014), Top 30 (2015+), and
        its overall list Top 50 (2010-2011) before Top 100. A study that treats an org rank of 15 as
        the same statement in 2013 and 2023 is comparing different things, and "absent from the 2013
        list" means outside the top 20, not the top 30."""
        assert ORG_LIST_DEPTH_BY_ERA == {"2011": 10, "2012-2014": 20, "2015+": 30}
        assert OVERALL_LIST_DEPTH_BY_ERA == {"2010-2011": 50, "2012+": 100}
