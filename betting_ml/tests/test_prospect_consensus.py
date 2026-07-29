"""E7.11 — the multi-source prospect-ranking consensus.

Two things in this story are easy to get wrong in a way that still LOOKS right in the output, and
both get an explicit oracle-style test here:

  1. **Partial coverage.** A source that publishes a Top 100 has said nothing about player #340.
     Imputing him at rank 101 fabricates an opinion. `test_partial_coverage_*`.
  2. **Disagreement as a raw gap.** Two imperfectly-correlated rankings regress toward each other
     at the extremes, so `source − consensus` flags the whole top of the board. E8.0 hit exactly
     this on its first real run. `TestResidualNotRawGap` asserts the broken metric IS broken on
     synthetic data and that the shipped one is not — the repo's selection-metric-hygiene rule
     (sanity-check a metric against what it mechanically must produce) applied to a display column.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.prospect_board.board_assembly import residual_vs_fit
from betting_ml.scripts.prospect_board.build_consensus_assembly import (
    HOW_TO_READ,
    build_sources,
    merge_pipeline_ranks,
)
from betting_ml.scripts.prospect_board.consensus import (
    DISAGREEMENT_THRESHOLD,
    MANUAL_CSV_COLUMNS,
    PAYWALLED_SOURCES,
    ConsensusError,
    RankSource,
    attach_consensus,
    build_consensus,
    coverage_table,
    format_consensus_report,
    normalize_name,
    resolve_manual_source,
)


def _sources(*names_and_cols, scope="overall"):
    return [RankSource(name=n, rank_col=c, scope=scope) for n, c in names_and_cols]


@pytest.fixture
def universe() -> pd.DataFrame:
    """12 players; source A ranks all 12, source B only the top 6 (the partial-coverage case)."""
    return pd.DataFrame({
        "mlbam_id": [f"{600000 + i}" for i in range(12)],
        "player_name": [f"Player {i}" for i in range(12)],
        "org": ["BAL"] * 6 + ["NYY"] * 6,
        "player_type": ["batter"] * 8 + ["pitcher"] * 4,
        "rank_a": list(range(1, 13)),
        "rank_b": [2, 1, 4, 3, 6, 5] + [np.nan] * 6,
        "model_score": [95, 80, 70, 60, 55, 50, 45, 40, 35, 30, 25, 20],
    })


class TestBuildConsensus:
    def test_mean_of_available_ranks_only(self, universe):
        out = build_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        # player 0: ranks 1 and 2 → 1.5;  player 6: only source A's rank 7 → 7.0
        assert out["consensus_rank_mean"].iloc[0] == pytest.approx(1.5)
        assert out["consensus_rank_mean"].iloc[6] == pytest.approx(7.0)

    def test_partial_coverage_is_never_imputed(self, universe):
        """An unranked player must not be scored as if the source ranked him last.

        If source B's absence were imputed at 7 (list length + 1), player 6's mean would become
        (7+7)/2 = 7 with n_sources = 2. The whole point is that it stays a ONE-source number.
        """
        out = build_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert out["consensus_n_sources"].iloc[6] == 1
        assert out["consensus_sources"].iloc[6] == "a"
        assert out["consensus_n_sources"].iloc[0] == 2

    def test_partial_coverage_does_not_penalise_the_unranked(self, universe):
        """Two players tied on source A must not be separated by B's non-opinion of one of them."""
        frame = universe.copy()
        frame.loc[6, "rank_a"] = 5.0     # same A rank as player 4, but B ranked only player 4
        out = build_consensus(frame, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert out["consensus_rank_mean"].iloc[6] == pytest.approx(5.0)

    def test_confidence_labels_flag_a_one_source_consensus(self, universe):
        out = build_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert out["consensus_confidence"].iloc[0] == "medium (2 sources)"
        assert out["consensus_confidence"].iloc[6] == "low (1 source)"

    def test_spread_measures_actual_disagreement(self, universe):
        out = build_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert out["consensus_rank_spread"].iloc[0] == pytest.approx(1.0)
        assert pd.isna(out["consensus_rank_spread"].iloc[6])   # one rank has no spread

    def test_org_scope_ranks_within_organization(self, universe):
        frame = universe.rename(columns={"rank_a": "org_rank_a"})
        out = build_consensus(frame, _sources(("a", "org_rank_a"), scope="org"),
                              scope="org", group_col="org", prefix="org_consensus")
        # each org's best player is org-consensus rank 1
        assert out["org_consensus_rank"].iloc[0] == 1
        assert out["org_consensus_rank"].iloc[6] == 1

    def test_overall_and_org_scopes_never_mix(self, universe):
        """An org rank must not enter the overall average — different measurements."""
        frame = universe.copy()
        sources = [RankSource("a", "rank_a", scope="overall"),
                   RankSource("b", "rank_b", scope="org")]
        out = build_consensus(frame, sources, scope="overall")
        assert (out["consensus_n_sources"] == 1).all()

    def test_bad_scope_is_rejected(self):
        with pytest.raises(ConsensusError, match="scope"):
            RankSource("a", "rank_a", scope="league")

    def test_missing_rank_column_raises(self, universe):
        with pytest.raises(ConsensusError, match="absent from the frame"):
            build_consensus(universe, _sources(("a", "rank_a"), ("z", "rank_missing")))

    def test_tier_is_assigned_in_overall_scope(self, universe):
        out = build_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert out["consensus_tier"].iloc[0] == "Tier 1 (top 10)"


class TestResidualNotRawGap:
    """The E8.0 regression-to-the-mean lesson, made mechanical.

    Construct two rankings that agree perfectly in expectation and differ only by symmetric noise.
    A correct disagreement metric must flag roughly as many players at the top as at the bottom.
    The raw gap does not — it flags the extremes, because a noisy ranking regresses.
    """

    @staticmethod
    def _two_noisy_rankings(n=400, seed=7):
        rng = np.random.default_rng(seed)
        truth = rng.normal(size=n)
        a = truth + rng.normal(scale=1.0, size=n)
        b = truth + rng.normal(scale=1.0, size=n)
        pct = lambda v: pd.Series(v).rank(pct=True) * 100.0   # noqa: E731
        return pct(a), pct(b)

    def _tail_bias(self, metric, seeds=range(20)):
        """Mean |bias| of a disagreement metric in the top and bottom deciles of the reference.

        Averaged over seeds because a single draw of 400 players puts ~40 in each tail, and the
        SE of a tail mean is a few points — a one-seed assertion would be a coin-flip test.
        """
        biases = []
        for seed in seeds:
            a, b = self._two_noisy_rankings(seed=seed)
            values = metric(a, b)
            biases += [abs(values[b >= 90].mean()), abs(values[b <= 10].mean())]
        return float(np.mean(biases))

    def test_the_raw_gap_is_a_broken_metric(self):
        """The oracle: on two rankings that agree in expectation, the gap must NOT be flat.

        It is systematically NEGATIVE where the reference ranks a player high and POSITIVE where it
        ranks him low — it re-encodes the reference rank. Asserting the broken metric IS broken is
        what makes the next assertion mean something.
        """
        a, b = self._two_noisy_rankings()
        gap = a - b
        assert gap[b >= 90].mean() < -5
        assert gap[b <= 10].mean() > 5
        assert self._tail_bias(lambda x, y: x - y) > 15

    def test_the_residual_removes_most_of_that_tail_bias(self):
        """Measured 2026-07-29: gap tail bias ≈ 20.6 pctile pts → residual ≈ 3.6 (−82%).

        Not asserted to be exactly zero, and the docstring of `residual_vs_fit` says why: the fit
        is LINEAR while two bounded rank-percentiles are related S-shaped, so a little curvature
        survives in the tails. What matters is that the survivor is far below
        DISAGREEMENT_THRESHOLD, i.e. it cannot by itself label a player a disagreement.
        """
        gap_bias = self._tail_bias(lambda x, y: x - y)
        resid_bias = self._tail_bias(residual_vs_fit)
        assert resid_bias < gap_bias / 3
        assert resid_bias < DISAGREEMENT_THRESHOLD / 2

    def test_the_residual_is_mean_zero_overall(self):
        a, b = self._two_noisy_rankings()
        assert abs(residual_vs_fit(a, b).mean()) < 1

    def test_the_residual_still_detects_a_real_disagreement(self):
        """De-biasing must not de-fang it: a genuinely differently-ranked player still shows."""
        a, b = self._two_noisy_rankings()
        a = a.copy()
        a.iloc[0] = 99.0
        b = b.copy()
        b.iloc[0] = 5.0
        resid = residual_vs_fit(a, b)
        assert resid.iloc[0] > DISAGREEMENT_THRESHOLD

    def test_too_few_points_falls_back_to_the_gap_without_raising(self):
        out = residual_vs_fit(pd.Series([50.0, 60.0]), pd.Series([40.0, 40.0]))
        assert out.tolist() == [10.0, 20.0]


class TestAttachConsensus:
    def test_attaches_both_scopes_and_the_ours_vs_consensus_column(self, universe):
        frame = universe.assign(org_rank_a=universe["rank_a"])
        sources = [RankSource("a", "rank_a", scope="overall"),
                   RankSource("b", "rank_b", scope="overall"),
                   RankSource("org_a", "org_rank_a", scope="org")]
        out, rep = attach_consensus(frame, sources)
        for col in ("consensus_rank", "org_consensus_rank", "mle_vs_consensus",
                    "vs_consensus_a", "vs_consensus_b", "mle_vs_consensus_label"):
            assert col in out.columns
        assert rep["universe_rows"] == len(frame)
        assert rep["overall_multi_source_players"] == 6

    def test_duplicate_source_names_are_rejected(self, universe):
        with pytest.raises(ConsensusError, match="duplicate source name"):
            attach_consensus(universe, [RankSource("a", "rank_a"), RankSource("a", "rank_b")])

    def test_no_sources_is_rejected(self, universe):
        with pytest.raises(ConsensusError, match="no ranking sources"):
            attach_consensus(universe, [])

    def test_a_lone_source_cannot_disagree_with_itself(self, universe):
        """Where only source A ranked a player, the consensus IS source A.

        Comparing them would measure nothing but the difference between two percentile
        denominators — which produced a lopsided 89-vs-35 split of spurious flags on the first
        real 1,451-player run. Those rows must be NULL, and say why.
        """
        out, _ = attach_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        lone = out["consensus_n_sources"] == 1
        assert lone.any()
        assert out.loc[lone, "vs_consensus_a"].isna().all()
        assert (out.loc[lone, "vs_consensus_a_label"] == "n/a (only one source ranked him)").all()
        assert out.loc[~lone, "vs_consensus_a"].notna().all()

    def test_the_two_scopes_are_fitted_separately_for_ours_vs_consensus(self, universe):
        """An overall percentile of 50 and an org percentile of 50 are different statements.

        Half the frame gets an overall consensus, half only an org one; the emitted
        `consensus_scope_used` must say which reference frame each row was judged in.
        """
        frame = universe.copy()
        frame["rank_a"] = [1, 2, 3, 4, 5, 6] + [np.nan] * 6      # overall: first 6 only
        frame["org_rank_x"] = list(range(1, 13))                  # org: everyone
        sources = [RankSource("a", "rank_a", scope="overall"),
                   RankSource("x", "org_rank_x", scope="org")]
        out, _ = attach_consensus(frame, sources)
        assert set(out["consensus_scope_used"].dropna()) == {"overall", "org"}
        assert (out["consensus_scope_used"].head(6) == "overall").all()
        assert (out["consensus_scope_used"].tail(6) == "org").all()

    def test_report_counts_disagreements_per_source(self, universe):
        out, rep = attach_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert set(rep["disagreement_counts"]) == {"a", "b"}
        assert rep["mle_vs_consensus"]["comparable"] > 0

    def test_report_renders(self, universe):
        _, rep = attach_consensus(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        text = format_consensus_report(rep)
        assert "best_alpha = 0" in text
        assert "PER-SOURCE COVERAGE" in text
        assert "RESIDUAL" in text

    def test_coverage_table_reports_depth_per_source(self, universe):
        cov = coverage_table(universe, _sources(("a", "rank_a"), ("b", "rank_b")))
        assert cov.loc[cov["source"] == "b", "players_ranked"].iloc[0] == 6
        assert cov.loc[cov["source"] == "b", "deepest_rank"].iloc[0] == 6


class TestManualSources:
    """The paywalled/robots-restricted path: hand-keyed files, deterministic legs only."""

    @staticmethod
    def _universe():
        return pd.DataFrame({
            "player_name": ["José Ramírez", "Mike Smith", "Mike Smith", "Ana Cruz"],
            "org": ["CLE", "BAL", "NYY", "SDP"],
            "mlbam_id": ["1", "2", "3", "4"],
        })

    def test_supplied_id_wins_and_is_labelled(self):
        manual = pd.DataFrame({"rank": [1], "player_name": ["whoever"], "mlbam_id": ["4"]})
        out, rep = resolve_manual_source(manual, self._universe(), source_name="ba")
        assert out["mlbam_id"].tolist() == ["4"]
        assert rep["by_method"] == {"id_supplied": 1}

    def test_name_plus_org_resolves_an_ambiguous_name(self):
        manual = pd.DataFrame({"rank": [1, 2], "player_name": ["Mike Smith", "Mike Smith"],
                               "org": ["BAL", "NYY"]})
        out, rep = resolve_manual_source(manual, self._universe(), source_name="ba")
        assert out["mlbam_id"].tolist() == ["2", "3"]
        assert rep["by_method"] == {"name_org_exact": 2}

    def test_accents_and_suffixes_normalize(self):
        manual = pd.DataFrame({"rank": [1], "player_name": ["Jose Ramirez Jr."]})
        out, _ = resolve_manual_source(manual, self._universe(), source_name="ba")
        assert out["mlbam_id"].tolist() == ["1"]

    def test_an_ambiguous_name_without_org_is_left_unresolved_never_guessed(self):
        """E7.4 landmine 4: no match beats a wrong match."""
        manual = pd.DataFrame({"rank": [1], "player_name": ["Mike Smith"]})
        out, rep = resolve_manual_source(manual, self._universe(), source_name="ba")
        assert out.empty
        assert rep["resolved"] == 0
        assert rep["unresolved_rows"][0]["player_name"] == "Mike Smith"

    def test_unmatched_rows_are_reported_not_dropped_silently(self):
        manual = pd.DataFrame({"rank": [1, 2], "player_name": ["Ana Cruz", "Nobody At All"]})
        out, rep = resolve_manual_source(manual, self._universe(), source_name="ba")
        assert rep["rows"] == 2 and rep["resolved"] == 1
        assert rep["resolved_rate"] == 0.5
        assert [r["player_name"] for r in rep["unresolved_rows"]] == ["Nobody At All"]

    def test_two_rows_resolving_to_the_same_player_raises(self):
        manual = pd.DataFrame({"rank": [1, 2], "player_name": ["Ana Cruz", "Ana Cruz"]})
        with pytest.raises(ConsensusError, match="DUPLICATE"):
            resolve_manual_source(manual, self._universe(), source_name="ba")

    def test_missing_required_columns_raise(self):
        with pytest.raises(ConsensusError, match="missing required column"):
            resolve_manual_source(pd.DataFrame({"player_name": ["x"]}), self._universe(),
                                  source_name="ba")

    def test_empty_file_raises(self):
        with pytest.raises(ConsensusError, match="EMPTY"):
            resolve_manual_source(pd.DataFrame(columns=MANUAL_CSV_COLUMNS), self._universe(),
                                  source_name="ba")

    def test_the_paywalled_registry_names_every_non_ingestible_source(self):
        """A source may only be here — the code path that would scrape one does not exist."""
        assert {"baseball_america", "keith_law", "espn_mcdaniel", "baseball_prospectus",
                "prospects_live"} <= set(PAYWALLED_SOURCES)
        for note in PAYWALLED_SOURCES.values():
            assert "never scraped" in note or "hand-keyed only" in note

    def test_normalize_name_is_exact_not_fuzzy(self):
        """Normalization removes conventions; it must not bridge genuinely different spellings."""
        assert normalize_name("Jose Ramirez") == normalize_name("José Ramírez Jr.")
        assert normalize_name("Michael Massey") != normalize_name("Mike Massey")


class TestPipelineUnion:
    """⭐ The union is the point: "ranked top-100 by one source, absent from the other's board
    entirely" is the loudest disagreement two sources can produce, and a naive merge drops it."""

    @staticmethod
    def _board():
        return pd.DataFrame({
            "mlbam_id": pd.Series(["1", "2"], dtype="string"),
            "player_name": ["On Board A", "On Board B"],
            "org": ["BAL", "NYY"],
            "position": ["SS", "RHP"],
            "player_type": ["batter", "pitcher"],
            "age": [19.0, 21.0],
            "eta": [2027, 2026],
            "fv": [55.0, 50.0],
            "org_rank": [1, 2],
        })

    @staticmethod
    def _pipeline():
        """Note the schema: `org` is point-in-time and exists only on an ORG-list row; a Top-100
        entry has no org of its own, so it carries only the roster-derived `org_current`."""
        return pd.DataFrame({
            "mlbam_id": ["1", "1", "3"],
            "list_type": ["top100", "org", "top100"],
            "rank": [7, 1, 12],
            "player_name": ["On Board A", "On Board A", "Pipeline Only"],
            "org": [None, "BAL", None],
            "org_current": ["BAL", "BAL", "SDP"],
            "position": ["SS", "SS", "OF"],
            "age_current": [19.0, 19.0, 18.0],
            "eta": [2027, 2027, 2029],
            "pipeline_grade_hit": [60.0, 60.0, 55.0],
        })

    def test_org_falls_back_to_the_roster_derived_one_for_a_top100_only_player(self):
        """A Pipeline-only player ranked ONLY on the Top 100 still needs an org, or he drops out of
        the AL/NL filter the whole draft board runs on."""
        out, _ = merge_pipeline_ranks(self._board(), self._pipeline())
        assert out.loc[out["mlbam_id"] == "3", "mlb_league"].iloc[0] == "NL"

    def test_both_pipeline_rank_kinds_land_in_their_own_columns(self):
        out, _ = merge_pipeline_ranks(self._board(), self._pipeline())
        row = out[out["mlbam_id"] == "1"].iloc[0]
        assert row["pipeline_overall_rank"] == 7
        assert row["pipeline_org_rank"] == 1

    def test_a_pipeline_only_player_is_added_not_dropped(self):
        out, rep = merge_pipeline_ranks(self._board(), self._pipeline())
        assert len(out) == 3
        extra = out[out["mlbam_id"] == "3"].iloc[0]
        assert not extra["on_fangraphs_board"]
        assert extra["player_name"] == "Pipeline Only"
        assert extra["mlb_league"] == "NL"           # derived from the org, so the AL/NL filter works
        assert pd.isna(extra["fv"])                  # blank = NOT ON THEIR BOARD, never "ungraded"
        assert rep["pipeline_only_players"] == 1

    def test_board_players_keep_on_fangraphs_board_true(self):
        out, _ = merge_pipeline_ranks(self._board().assign(on_fangraphs_board=True),
                                      self._pipeline())
        assert out.loc[out["mlbam_id"] == "1", "on_fangraphs_board"].iloc[0]

    def test_the_join_never_multiplies_rows(self):
        """A player appearing on two Pipeline lists must not become two board rows."""
        out, _ = merge_pipeline_ranks(self._board(), self._pipeline())
        assert not out["mlbam_id"].dropna().duplicated().any()

    def test_an_empty_pipeline_frame_is_refused(self):
        with pytest.raises(ValueError, match="EMPTY"):
            merge_pipeline_ranks(self._board(), self._pipeline().iloc[0:0])

    def test_sources_are_declared_from_the_frame_not_a_static_list(self):
        """A run without a Pipeline snapshot must report FEWER sources, not an all-NULL column."""
        board = self._board()
        assert {s.name for s in build_sources(board, [])} == {"fangraphs_org"}
        merged, _ = merge_pipeline_ranks(board, self._pipeline())
        assert {s.name for s in build_sources(merged, [])} == {
            "fangraphs_org", "pipeline_overall", "pipeline_org"}

    def test_a_manual_source_is_declared_and_labelled_manual(self):
        merged, _ = merge_pipeline_ranks(self._board(), self._pipeline())
        merged["rank_baseball_america"] = [3, np.nan, np.nan]
        sources = {s.name: s for s in build_sources(merged, ["baseball_america"])}
        assert sources["baseball_america"].access == "manual"
        assert "never scraped" in sources["baseball_america"].note

    def test_the_legend_states_the_honest_frame_and_the_access_rule(self):
        text = " ".join(f"{k} {v}" for k, v in HOW_TO_READ)
        assert "best_alpha = 0" in text
        assert "never scraped" in text
        assert "never imputed" in text
