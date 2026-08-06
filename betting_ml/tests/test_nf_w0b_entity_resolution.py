"""NF-W0b — guards for the canonical cross-vendor entity-resolution service (v3 §12A).

Every guard here was RED-proven against deliberately-broken source before being trusted (the
repo's INC-38/INC-39 rule: a guard that cannot fail is worse than none).

⭐ ONE ISOLATING FIXTURE PER CLAUSE (the NF-D17 lesson). `monitors.evaluate` decides `fail_closed`
from an OR of five clauses, so a fixture that trips two of them proves neither: delete the clause
under test and the guard stays green because the other one still rejects. Each fail-closed test
below therefore satisfies EVERY OTHER clause and violates exactly one, so removing that clause
from the source is the only way to make the case pass — and each was verified to go red that way.

The suite is pure pandas — no lake, no network, no module-level global mutation — so it runs in
the fast gate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.entity import (
    CROSSWALK_COLUMNS,
    EntityResolutionFailClosed,
    ResolutionSpec,
    ResolutionThresholds,
    assert_no_silent_zero,
    attach_snaps_to_player_week,
    build_crosswalk,
    evaluate,
    jaro_winkler,
    normalize_name,
    position_group,
    qa_records,
    resolve,
    resolve_prop_players,
    resolve_snap_counts,
    skill_starter_mask,
)
from quant_sports_intel_models.football.nfl.entity.resolver import (
    METHOD_EXACT_NAME_TEAM_POS,
    METHOD_FUZZY_CONSTRAINED,
    METHOD_NAME_TEAM_RELAXED,
    METHOD_REVIEWED,
    METHOD_UNRESOLVED,
    METHOD_VENDOR_ID,
)

REPO = Path(__file__).resolve().parents[2]


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
def _targets(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["canonical_player_id", "player_name", "team", "position", "season", "week"]
    )


def _snaps(rows) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["pfr_player_id", "player", "position", "team", "season", "week",
                 "offense_snaps", "offense_pct", "special_teams_snaps", "special_teams_pct"],
    )


def _crosswalk(rows) -> pd.DataFrame:
    """(canonical_player_id, source_name, source_player_id) → a full §12A crosswalk row."""
    out = []
    for cid, source, sid in rows:
        out.append([cid, source, sid, None, None, None, None, None, None,
                    "stable_vendor_id", 1.0, "auto", "t"])
    return pd.DataFrame(out, columns=list(CROSSWALK_COLUMNS))


SPEC = ResolutionSpec(
    source_name="test.source",
    vendor_id_column="pfr_player_id",
    vendor_source_name="pfr",
    name_column="player",
    team_column="team",
    position_column="position",
    block_columns=("season", "week", "team"),
)


# ── names ────────────────────────────────────────────────────────────────────────────────────────
class TestNormalization:
    @pytest.mark.parametrize(
        "a,b,expected",
        [("MARTHA", "MARHTA", 0.961), ("DIXON", "DICKSONX", 0.813),
         ("DWAYNE", "DUANE", 0.840), ("JELLYFISH", "SMELLYFISH", 0.896)],
    )
    def test_jaro_winkler_matches_the_published_reference_values(self, a, b, expected):
        """Pin our own implementation against Winkler's published numbers.

        The threshold that governs the fuzzy rung is a NUMBER (0.95) calibrated against a measured
        control, so it is only meaningful if the similarity function producing it stays the same
        function. A drifted metric would silently re-tune every match decision in the service.
        """
        assert jaro_winkler(a, b) == pytest.approx(expected, abs=0.001)

    def test_normalization_folds_formatting_noise(self):
        assert normalize_name("T.J. Watt Jr.") == "tj watt"
        assert normalize_name("José Ramírez III") == "jose ramirez"
        assert normalize_name("Ka'imi Fairbairn") == "kaimi fairbairn"

    def test_normalization_deliberately_does_NOT_fold_a_nickname(self):
        """"Michael Woods II" and "Mike Woods" are the SAME player in the live lake — and must
        still normalize to DIFFERENT strings.

        Collapsing nicknames by rule would merge genuinely different players (there is no rule that
        maps mike→michael without also mapping other pairs wrongly). Nicknames are the fuzzy rung's
        and the reviewed crosswalk's job, where the damage is bounded and reviewable. If this ever
        starts passing as equal, the exact-name rungs have silently become fuzzy ones.
        """
        assert normalize_name("Michael Woods II") == "michael woods"
        assert normalize_name("Mike Woods") == "mike woods"
        assert normalize_name("Michael Woods II") != normalize_name("Mike Woods")
        # …and it is genuinely below the calibrated fuzzy bar, which is why it needs review.
        assert jaro_winkler("michael woods", "mike woods") < 0.95

    def test_position_group_reconciles_the_vendor_grain_mismatch(self):
        """snap_counts writes T/G/C/DE/FS; weekly_rosters writes OL/DL/DB. Without the fold, an
        exact position join fails on every lineman — not on a typo, on a whole population."""
        assert position_group("T") == position_group("G") == position_group("OL") == "OL"
        assert position_group("DE") == position_group("NT") == "DL"
        assert position_group("FS") == position_group("CB") == "DB"
        assert position_group("FB") == "RB"

    def test_an_unknown_position_label_maps_to_itself_not_to_a_bucket(self):
        """The safe direction: an unrecognised label constrains to exactly itself, so a new vendor
        label degrades to a weaker rung rather than merging two players in a wrong bucket."""
        assert position_group("XYZ") == "XYZ"


# ── the ladder ───────────────────────────────────────────────────────────────────────────────────
class TestMatchOrderLadder:
    def test_each_rung_resolves_its_own_case(self):
        targets = _targets([
            ("g1", "Jerry Jeudy", "CLE", "WR", 2024, 15),
            ("g2", "Zack Zombie", "CLE", "G", 2024, 15),
            ("g3", "Mike Woods", "CLE", "WR", 2024, 15),
        ])
        snaps = _snaps([
            ("pfrA", "Jerry Jeudy", "WR", "CLE", 2024, 15, 60, 0.95, 2, 0.05),
            (None, "Zack Zombie", "OL", "CLE", 2024, 15, 70, 1.00, 0, 0.0),
            (None, "Mike Wooods", "WR", "CLE", 2024, 15, 63, 1.00, 0, 0.0),
            (None, "Ghost Player", "WR", "CLE", 2024, 15, 10, 0.15, 0, 0.0),
        ])
        got = resolve(snaps, spec=SPEC, crosswalk=_crosswalk([("g1", "pfr", "pfrA")]),
                      targets=targets, target_name_column="player_name")
        methods = dict(zip(got["player"], got["match_method"]))
        assert methods["Jerry Jeudy"] == METHOD_VENDOR_ID          # tier 1
        assert methods["Zack Zombie"] == METHOD_EXACT_NAME_TEAM_POS  # tier 3 (G vs OL → both OL)
        assert methods["Mike Wooods"] == METHOD_FUZZY_CONSTRAINED    # tier 4b (a typo, ≥ 0.95)
        assert methods["Ghost Player"] == METHOD_UNRESOLVED          # tier 5

    def test_a_source_whose_team_lives_in_the_BLOCK_still_gets_an_exact_rung(self):
        """⭐ REGRESSION — found only by running the real props payload, because every unit fixture
        happened to supply a `team_column`.

        A source may carry its team constraint in the BLOCK rather than in its own columns (props
        are exactly that: an Odds-API outcome names no team, so the constraint arrives as
        `_event_team`). Joining tiers 3/4a on `_team` regardless compared the source's placeholder
        `""` against the target's real team, so those rungs could NEVER match and every EXACT-name
        prop fell through to the fuzzy rung — mislabelled `constrained_fuzzy`, scored into the
        low-confidence band, driving `low_confidence_rate` to 1.0 and failing the build closed on
        586,850 exact matches.

        Here the source declares no team/position column and blocks on `("season", "team")`; an
        exact name must resolve at tier 4a, NOT tier 4b.
        """
        spec = ResolutionSpec(
            source_name="block-carried-team", name_column="player", block_columns=("season", "team")
        )
        targets = _targets([("g1", "Exact Match", "CLE", "WR", 2024, 15)])
        snaps = _snaps([(None, "Exact Match", "WR", "CLE", 2024, 15, 30, 0.5, 0, 0.0)])
        got = resolve(snaps, spec=spec, targets=targets, target_name_column="player_name")
        assert got.loc[0, "canonical_player_id"] == "g1"
        assert got.loc[0, "match_method"] == METHOD_NAME_TEAM_RELAXED, (
            "an exact name match must not be reported as a fuzzy one"
        )
        assert got.loc[0, "match_confidence"] > 0.89, (
            "…and must not be scored into the low-confidence band"
        )

    def test_a_fuzzy_match_is_always_inside_the_low_confidence_band(self):
        """⭐ Otherwise `low_confidence_rate` is a monitor that CANNOT FIRE.

        The natural choice is to use the Jaro-Winkler score as the fuzzy match's confidence — but
        the rung only accepts scores ≥ 0.95, so every fuzzy confidence would land above the 0.89
        low-confidence bar and the monitor would report 0.0000 forever while looking healthy.
        Confidence belongs to the RUNG (an inexact match is the least trustworthy one however close
        the strings were); the raw similarity stays on `match_score`.
        """
        targets = _targets([("g1", "Mike Woods", "CLE", "WR", 2024, 15)])
        snaps = _snaps([(None, "Mike Wooods", "WR", "CLE", 2024, 15, 60, 0.9, 0, 0.0)])
        got = resolve(snaps, spec=SPEC, targets=targets, target_name_column="player_name")
        assert got.loc[0, "match_method"] == METHOD_FUZZY_CONSTRAINED
        assert got.loc[0, "match_score"] >= 0.95, "the rung only accepts a close match"
        assert got.loc[0, "match_confidence"] <= 0.89, (
            "a fuzzy match must count toward low_confidence_rate, or the monitor is unfirable"
        )

    def test_a_reviewed_row_outranks_the_vendor_id_when_they_disagree(self):
        """Tier 2 exists to CORRECT a vendor id, so it must win where the two disagree — otherwise
        a human decision is silently re-overridden by the feed it was recorded to fix."""
        snaps = _snaps([("pfrA", "Someone", "WR", "CLE", 2024, 15, 10, 0.2, 0, 0.0)])
        reviewed = _crosswalk([("g_reviewed", "pfr", "pfrA")])
        reviewed["match_method"] = METHOD_REVIEWED
        got = resolve(snaps, spec=SPEC, crosswalk=_crosswalk([("g_vendor", "pfr", "pfrA")]),
                      reviewed=reviewed, targets=_targets([]))
        assert got.loc[0, "canonical_player_id"] == "g_reviewed"
        assert got.loc[0, "match_method"] == METHOD_REVIEWED

    def test_a_weaker_rung_never_overwrites_a_stronger_one(self):
        """A row resolvable at BOTH tier 1 and tier 3 must keep tier 1's answer."""
        snaps = _snaps([("pfrA", "Jerry Jeudy", "WR", "CLE", 2024, 15, 60, 0.9, 0, 0.0)])
        targets = _targets([("g_name", "Jerry Jeudy", "CLE", "WR", 2024, 15)])
        got = resolve(snaps, spec=SPEC, crosswalk=_crosswalk([("g_vendor", "pfr", "pfrA")]),
                      targets=targets, target_name_column="player_name")
        assert got.loc[0, "canonical_player_id"] == "g_vendor"
        assert got.loc[0, "match_method"] == METHOD_VENDOR_ID

    def test_resolution_never_drops_or_fans_out_a_row(self):
        """The row-preservation contract is what makes `silent_drop_count` a measurable fact."""
        snaps = _snaps([(None, f"Nobody {i}", "WR", "CLE", 2024, 15, 1, 0.1, 0, 0.0)
                        for i in range(7)])
        got = resolve(snaps, spec=SPEC, targets=_targets([]))
        assert len(got) == 7
        assert got["canonical_player_id"].isna().all()


class TestAmbiguityIsNeverArbitrated:
    def test_a_duplicate_name_in_the_block_resolves_to_nothing(self):
        targets = _targets([
            ("gA", "Chris Smith", "CLE", "WR", 2024, 15),
            ("gB", "Chris Smith", "CLE", "TE", 2024, 15),
        ])
        snaps = _snaps([(None, "Chris Smith", "WR", "CLE", 2024, 15, 30, 0.5, 0, 0.0)])
        got = resolve(snaps, spec=SPEC, targets=targets, target_name_column="player_name")
        assert pd.isna(got.loc[0, "canonical_player_id"]), "a coin flip is not a resolution"

    def test_ambiguity_is_judged_over_the_SEASON_not_inside_the_block(self):
        """⭐ THE JONAH WILLIAMS CASE — the defect the blind-vendor-id control caught, isolated.

        The NFL carried two "Jonah Williams" in 2024–25. ARI's roster for a given week lists only
        ONE of them, so inside the block the name looks perfectly unique and a block-local
        uniqueness test happily matched it — at tier 3's 0.95 confidence, and wrong, on all 15 of
        that pair's rows. A block-local test cannot see a collision it does not contain.

        This fixture reproduces exactly that shape: the duplicate lives in a DIFFERENT team-week of
        the same season, so the block contains one candidate. Narrowing
        `ambiguity_scope_columns` to the block makes this case match — which is how the fix is
        RED-provable.
        """
        targets = _targets([
            ("gOL", "Jonah Williams", "ARI", "OL", 2025, 1),   # in-block: the only ARI candidate
            ("gDL", "Jonah Williams", "SEA", "DL", 2025, 1),   # the collision, elsewhere in-season
        ])
        snaps = _snaps([(None, "Jonah Williams", "T", "ARI", 2025, 1, 70, 1.0, 0, 0.0)])
        got = resolve(snaps, spec=SPEC, targets=targets, target_name_column="player_name")
        assert pd.isna(got.loc[0, "canonical_player_id"]), (
            "a name duplicated anywhere in the season must abstain — the block cannot see the twin"
        )

    def test_a_fuzzy_tie_resolves_to_nothing(self):
        targets = _targets([
            ("gA", "Jon Smithe", "CLE", "WR", 2024, 15),
            ("gB", "Jon Smythe", "CLE", "TE", 2024, 15),
        ])
        snaps = _snaps([(None, "Jon Smxthe", "WR", "CLE", 2024, 15, 30, 0.5, 0, 0.0)])
        got = resolve(snaps, spec=SPEC, targets=targets, target_name_column="player_name")
        assert pd.isna(got.loc[0, "canonical_player_id"])

    def test_a_candidate_below_the_threshold_is_not_matched(self):
        targets = _targets([("gA", "Completely Different", "CLE", "WR", 2024, 15)])
        snaps = _snaps([(None, "Nothing Alike", "WR", "CLE", 2024, 15, 30, 0.5, 0, 0.0)])
        got = resolve(snaps, spec=SPEC, targets=targets, target_name_column="player_name")
        assert pd.isna(got.loc[0, "canonical_player_id"])


class TestNameOnlyIsNeverFuzzyJoinedAlone:
    """§12A: "Name-only props cannot be joined on fuzzy name alone." Enforced, not documented."""

    def test_a_spec_with_no_block_is_refused_the_name_tiers(self):
        spec = ResolutionSpec(source_name="s", name_column="player", block_columns=())
        assert spec.allow_name_tiers is False
        targets = _targets([("gA", "Exact Match", "CLE", "WR", 2024, 15)])
        snaps = _snaps([(None, "Exact Match", "WR", "CLE", 2024, 15, 30, 0.5, 0, 0.0)])
        got = resolve(snaps, spec=spec, targets=targets, target_name_column="player_name")
        assert pd.isna(got.loc[0, "canonical_player_id"]), (
            "an EXACT name match must still be refused when the source declares no constraint"
        )

    def test_a_PARTIAL_block_is_refused_just_like_an_absent_one(self):
        """A spec declaring (season, week, team) whose frames supply only `season` would run the
        fuzzy rung against every player in the league — a name-only global match reached by
        accident. Accepting the partial block is the regression this isolates."""
        spec = ResolutionSpec(
            source_name="s", name_column="player", team_column="team", position_column="position",
            block_columns=("season", "week", "team"),
        )
        targets = _targets([("gA", "Exact Match", "CLE", "WR", 2024, 15)]).drop(columns=["week"])
        snaps = _snaps([(None, "Exact Match", "WR", "CLE", 2024, 15, 30, 0.5, 0, 0.0)])
        got = resolve(snaps, spec=spec, targets=targets, target_name_column="player_name")
        assert pd.isna(got.loc[0, "canonical_player_id"])


# ── the four monitors + fail-closed ──────────────────────────────────────────────────────────────
def _clean_resolved(n_matched: int = 10, n_unmatched: int = 0, confidence: float = 1.0):
    """A resolution result that satisfies EVERY fail-closed clause — the isolating baseline."""
    rows = []
    for i in range(n_matched):
        rows.append({"canonical_player_id": f"g{i}", "match_method": METHOD_VENDOR_ID,
                     "match_confidence": confidence, "match_score": 1.0, "source_degraded": False})
    for i in range(n_unmatched):
        rows.append({"canonical_player_id": pd.NA, "match_method": METHOD_UNRESOLVED,
                     "match_confidence": 0.0, "match_score": float("nan"), "source_degraded": True})
    cols = ["canonical_player_id", "match_method", "match_confidence", "match_score",
            "source_degraded"]
    df = pd.DataFrame(rows, columns=cols)
    df["canonical_player_id"] = df["canonical_player_id"].astype("string")
    return df


class TestMonitors:
    def test_a_clean_resolution_does_not_fail_closed(self):
        """The two-sided control: without this, every fail-closed test below could pass because the
        gate rejects EVERYTHING, which would make the whole class vacuous."""
        rep = evaluate(_clean_resolved(), source_name="s", n_input_rows=10)
        assert rep.fail_closed is False and rep.reasons == []
        assert rep.unmatched_rate == 0.0 and rep.silent_drop_count == 0

    def test_a_silent_drop_fails_closed_even_under_permissive_thresholds(self):
        """⭐ ISOLATING FIXTURE for the unconditional clause. Every rate bar is set wide open and
        every other clause is satisfied, so ONLY the silent-drop clause can fire. §12A:
        `silent_drop_count` must equal 0, and is deliberately not threshold-governed."""
        permissive = ResolutionThresholds(
            max_unmatched_rate=1.0, max_low_confidence_rate=1.0,
            max_high_value_unmatched=10**9, require_evaluated=False,
        )
        rep = evaluate(_clean_resolved(n_matched=9), source_name="s", n_input_rows=10,
                       thresholds=permissive)
        assert rep.silent_drop_count == 1
        assert rep.fail_closed is True
        assert any("silent_drop_count" in r for r in rep.reasons)
        assert len(rep.reasons) == 1, "another clause fired — the fixture is not isolating"

    def test_an_unevaluable_run_is_not_scored_healthy(self):
        """NF1.7 (a): a monitor that could not be computed is not a passing monitor. An empty
        source must report None, never 0.0 — otherwise "no rows" reads exactly like "all matched"."""
        rep = evaluate(_clean_resolved(n_matched=0), source_name="s", n_input_rows=0)
        assert rep.evaluated is False
        assert rep.unmatched_rate is None, "0.0 here would read as a perfect match rate"
        assert rep.fail_closed is True
        assert len(rep.reasons) == 1 and "unevaluable" in rep.reasons[0]

    def test_low_confidence_rate_is_None_when_nothing_matched(self):
        """Same vacuity trap one level in: with no matched population there is no rate to report,
        and 0.0 would read as "no low-confidence matches"."""
        rep = evaluate(_clean_resolved(n_matched=0, n_unmatched=5), source_name="s",
                       n_input_rows=5, thresholds=ResolutionThresholds(max_unmatched_rate=1.0))
        assert rep.low_confidence_rate is None

    def test_the_unmatched_rate_clause_fires_alone(self):
        rep = evaluate(_clean_resolved(n_matched=90, n_unmatched=10), source_name="s",
                       n_input_rows=100, thresholds=ResolutionThresholds(max_unmatched_rate=0.05))
        assert rep.unmatched_rate == pytest.approx(0.10)
        assert len(rep.reasons) == 1 and "unmatched_rate" in rep.reasons[0]

    def test_the_low_confidence_clause_fires_alone(self):
        rep = evaluate(_clean_resolved(n_matched=10, confidence=0.60), source_name="s",
                       n_input_rows=10,
                       thresholds=ResolutionThresholds(max_low_confidence_rate=0.05))
        assert rep.low_confidence_rate == pytest.approx(1.0)
        assert len(rep.reasons) == 1 and "low_confidence_rate" in rep.reasons[0]

    def test_the_high_value_clause_fires_alone_and_is_not_a_rate(self):
        """⭐ WHY THE COUNT IS SEPARATE FROM THE RATE. One unmatched starter among 999 clean rows is
        a 0.1% unmatched rate — under any sane bar — and a corrupted starter. The rate averages a
        100%-snap WR and a special-teamer into the same number; the count does not."""
        df = _clean_resolved(n_matched=999, n_unmatched=1)
        hv = pd.Series([False] * 999 + [True], index=df.index)
        rep = evaluate(df, source_name="s", n_input_rows=1000, high_value_mask=hv,
                       thresholds=ResolutionThresholds(max_high_value_unmatched=0))
        assert rep.unmatched_rate == pytest.approx(0.001)
        assert rep.high_value_unmatched_count == 1
        assert len(rep.reasons) == 1 and "high_value_unmatched_count" in rep.reasons[0]

    def test_qa_records_queue_the_unmatched_and_the_low_confidence(self):
        df = pd.concat([_clean_resolved(n_matched=2, n_unmatched=1),
                        _clean_resolved(n_matched=1, confidence=0.60)], ignore_index=True)
        qa = qa_records(df, source_name="s")
        assert set(qa["qa_reason"]) == {"unmatched", "low_confidence"}
        assert qa.iloc[0]["qa_reason"] == "unmatched", "worst-first: the queue's top is the work"


class TestFallBackAndFlagNeverZeroes:
    def test_a_degraded_row_carrying_a_value_is_rejected(self):
        """⭐ THE MECHANICAL GUARD against the defect this whole story exists to remove: an
        unresolved identity rendered as a real number."""
        bad = pd.DataFrame({"source_degraded": [True], "offense_pct": [0.0]})
        with pytest.raises(EntityResolutionFailClosed, match="silently zeroed"):
            assert_no_silent_zero(bad, value_columns=["offense_pct"])

    def test_a_degraded_row_carrying_NULL_is_accepted(self):
        """The two-sided half: the guard must ACCEPT the correct shape, or it is just a blanket
        rejection that proves nothing about which shape it enforces."""
        ok = pd.DataFrame({"source_degraded": [True], "offense_pct": [None]})
        assert_no_silent_zero(ok, value_columns=["offense_pct"])  # must not raise

    def test_a_resolved_row_may_carry_a_genuine_zero(self):
        """A resolved player who truly played 0 snaps keeps his 0.0 — the guard must not confuse
        "observed zero" with "fabricated zero", which is the entire distinction."""
        ok = pd.DataFrame({"source_degraded": [False], "offense_pct": [0.0]})
        assert_no_silent_zero(ok, value_columns=["offense_pct"])  # must not raise


# ── the snap bridge (the NF-W1-critical leg) ─────────────────────────────────────────────────────
class TestSnapBridge:
    def test_an_unresolved_identity_becomes_NULL_and_a_real_zero_survives(self):
        """⭐ THE HEADLINE INVARIANT, both directions in one case.

        `zero_guy` is resolved and genuinely played 0 snaps → he keeps 0.0, tier 'observed'.
        `ghost` cannot be resolved → NULL, never 0.0. Before NF-W0b both rendered as 0.0 and were
        indistinguishable, which is how a 100%-snap starter was served a 0.00 snap share.
        """
        targets = _targets([("g_zero", "Zero Guy", "CLE", "WR", 2024, 15)])
        snaps = _snaps([
            ("pfrZ", "Zero Guy", "WR", "CLE", 2024, 15, 0, 0.0, 0, 0.0),
            (None, "Ghost Player", "WR", "CLE", 2024, 15, 40, 0.9, 0, 0.0),
        ])
        resolved, _ = resolve_snap_counts(
            snaps, targets=targets, crosswalk=_crosswalk([("g_zero", "pfr", "pfrZ")])
        )
        pw = pd.DataFrame({"canonical_player_id": ["g_zero", "g_absent"],
                           "season": [2024, 2024], "week": [15, 15]})
        out = attach_snaps_to_player_week(pw, resolved).set_index("canonical_player_id")

        assert out.loc["g_zero", "snap_source_tier"] == "observed"
        assert out.loc["g_zero", "offense_pct"] == 0.0, "a genuine zero must survive"
        assert out.loc["g_absent", "snap_source_tier"] == "no_snap_row"
        assert pd.isna(out.loc["g_absent", "offense_pct"]), "an unknown must be NULL, never 0.0"

    def test_the_snap_feed_is_never_silently_dropped(self):
        """The other direction: an unattributable snap OBSERVATION stays in the frame and is
        counted, rather than being inner-joined out of existence."""
        snaps = _snaps([(None, f"Ghost {i}", "WR", "CLE", 2024, 15, 40, 0.9, 0, 0.0)
                        for i in range(4)])
        resolved, rep = resolve_snap_counts(snaps, targets=_targets([]))
        assert len(resolved) == 4 and rep.silent_drop_count == 0
        assert rep.n_output_rows == rep.n_input_rows

    def test_attaching_snaps_cannot_fan_the_spine_out(self):
        """A mid-week team change puts two snap rows on one player-week; the spine must stay 1:1
        or every downstream per-player aggregate double-counts."""
        targets = _targets([("g1", "Two Teams", "CLE", "WR", 2024, 15)])
        snaps = _snaps([
            ("pfr1", "Two Teams", "WR", "CLE", 2024, 15, 20, 0.4, 0, 0.0),
            ("pfr1", "Two Teams", "WR", "PIT", 2024, 15, 10, 0.2, 0, 0.0),
        ])
        resolved, _ = resolve_snap_counts(
            snaps, targets=targets, crosswalk=_crosswalk([("g1", "pfr", "pfr1")])
        )
        pw = pd.DataFrame({"canonical_player_id": ["g1"], "season": [2024], "week": [15]})
        out = attach_snaps_to_player_week(pw, resolved)
        assert len(out) == 1
        assert out.loc[0, "offense_snaps"] == 30, "snaps sum across the two teams"

    def test_the_high_value_mask_is_not_vacuous(self):
        """A mask that is all-False would score `high_value_unmatched_count` 0 on any input — the
        NF1.7 (a) shape, where a monitor reads healthy because it examined nothing."""
        snaps = _snaps([
            (None, "Starter", "WR", "CLE", 2024, 15, 60, 0.95, 0, 0.0),
            (None, "Rotational", "WR", "CLE", 2024, 15, 5, 0.05, 0, 0.0),
            (None, "Long Snapper", "LS", "CLE", 2024, 15, 0, 0.0, 3, 0.1),
        ])
        mask = skill_starter_mask(snaps)
        assert mask.tolist() == [True, False, False]


# ── props: the name-only leg ─────────────────────────────────────────────────────────────────────
def _props(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["player_name", "season", "home_team", "away_team",
                                       "market", "bookmaker"])


class TestPropsIdentity:
    def test_a_prop_resolves_when_its_event_supplies_the_team_constraint(self):
        targets = _targets([("gQB", "Joe Passer", "CLE", "QB", 2024, 1)])
        props = _props([("Joe Passer", 2024, "CLE", "PIT", "player_pass_yds", "bovada")])
        out, rep = resolve_prop_players(props, targets=targets)
        assert out.loc[0, "canonical_player_id"] == "gQB"
        assert rep.silent_drop_count == 0

    def test_a_prop_with_no_resolvable_event_is_refused_the_name_tiers(self):
        """⭐ §12A's hard rule, isolated: the SAME player name that resolves above must NOT resolve
        once the event teams are gone. That is the difference between the rule being enforced and
        it being a comment — the name alone is never enough."""
        targets = _targets([("gQB", "Joe Passer", "CLE", "QB", 2024, 1)])
        props = _props([("Joe Passer", 2024, None, None, "player_pass_yds", "bovada")])
        out, _ = resolve_prop_players(props, targets=targets)
        assert pd.isna(out.loc[0, "canonical_player_id"])
        assert bool(out.loc[0, "source_degraded"]) is True

    def test_a_name_matching_a_player_on_each_side_resolves_to_nothing(self):
        """Two "Josh Allen"s, one per team in the same game — the §12A duplicate-name case at its
        most dangerous, because both candidates are inside the constraint.

        ⚠️ HONEST NOTE ON WHAT THIS PROVES. Two independent clauses enforce this outcome: the
        resolver's season-scope ambiguity abstain, and `resolve_prop_players`' two-sided collapse
        (`n_ids == 1`). RED-proving showed that disabling EITHER alone leaves the test green,
        because the other still refuses — so this is a BEHAVIOUR guard over a redundantly-defended
        property, not an isolating guard for one clause (`test_both_ambiguity_defences_are_load_
        bearing` proves it goes red when both are removed). The redundancy is deliberate: the
        two-sided check is the backstop if a future spec narrows the ambiguity scope.
        """
        targets = _targets([
            ("gA", "Josh Allen", "CLE", "QB", 2024, 1),
            ("gB", "Josh Allen", "PIT", "LB", 2024, 1),
        ])
        props = _props([("Josh Allen", 2024, "CLE", "PIT", "player_pass_yds", "bovada")])
        out, _ = resolve_prop_players(props, targets=targets)
        assert pd.isna(out.loc[0, "canonical_player_id"])

    def test_the_two_sided_collapse_is_subsumed_by_the_season_scope_rule(self):
        """⚠️ A RECORDED NEGATIVE RESULT, not a guard — written because trying to RED-prove the
        two-sided collapse proved it UNREACHABLE, and a future reader deserves to know that rather
        than assume it was tested.

        For the two event sides to disagree, the SAME normalized prop name must map to two
        different canonical players — which is precisely the definition of season-scope ambiguity,
        so the resolver abstains first and the collapse never decides a row. No fixture can
        isolate it (I tried: "A.J. Brown" vs "AJ Brown" normalize to one key, so the season rule
        still fires).

        The collapse is KEPT as a backstop for a future spec that narrows `ambiguity_scope_columns`
        — but it is explicitly unproven, and this test pins the subsumption so that if the scope
        ever narrows, the assertion below still describes real behaviour and the collapse becomes
        genuinely testable.
        """
        targets = _targets([
            ("gCLE", "A.J. Brown", "CLE", "WR", 2024, 1),
            ("gPIT", "AJ Brown", "PIT", "WR", 2024, 1),
        ])
        props = _props([("A.J. Brown", 2024, "CLE", "PIT", "player_reception_yds", "bovada")])
        out, _ = resolve_prop_players(props, targets=targets)
        assert pd.isna(out.loc[0, "canonical_player_id"])
        # the resolver refused before the collapse was consulted — that is the subsumption
        assert out.loc[0, "match_method"] == METHOD_UNRESOLVED

    def test_props_are_row_preserving(self):
        targets = _targets([("gQB", "Joe Passer", "CLE", "QB", 2024, 1)])
        props = _props([("Nobody At All", 2024, "CLE", "PIT", "player_pass_yds", "bovada")] * 3)
        out, rep = resolve_prop_players(props, targets=targets)
        assert len(out) == 3 and rep.silent_drop_count == 0


# ── the crosswalk artifact ───────────────────────────────────────────────────────────────────────
class TestCrosswalk:
    def test_the_field_contract_matches_the_architecture_doc(self):
        """§12A lists these thirteen fields by name. Pinned so a field cannot be quietly dropped
        from the artifact a downstream reviewer depends on."""
        assert CROSSWALK_COLUMNS == (
            "canonical_player_id", "source_name", "source_player_id", "source_player_name",
            "normalized_name", "team_id", "position", "effective_start_timestamp",
            "effective_end_timestamp", "match_method", "match_confidence", "review_status",
            "last_verified_timestamp",
        )

    def test_it_unpivots_the_vendor_ids_the_lake_already_carries(self):
        rosters = pd.DataFrame([{
            "gsis_id": "g1", "full_name": "Jerry Jeudy", "team": "CLE", "position": "WR",
            "season": 2024, "week": 1, "espn_id": "4241463", "pfr_id": "JeudJe00",
            "sleeper_id": "6803",
        }])
        cw = build_crosswalk(rosters, last_verified_timestamp="2026-08-05T00:00:00+00:00")
        assert set(cw["source_name"]) == {"espn", "pfr", "sleeper"}
        assert (cw["canonical_player_id"] == "g1").all()
        assert list(cw.columns) == list(CROSSWALK_COLUMNS)

    def test_a_placeholder_vendor_id_is_blanked_not_treated_as_real(self):
        """A numeric vendor column renders a missing id as '0'/'0.0'/'nan'. Treating those as real
        would merge EVERY id-less player of that vendor into one canonical player — the single most
        destructive thing a crosswalk can do."""
        rosters = pd.DataFrame([
            {"gsis_id": "g1", "full_name": "A", "team": "CLE", "position": "WR",
             "season": 2024, "week": 1, "espn_id": "0"},
            {"gsis_id": "g2", "full_name": "B", "team": "CLE", "position": "WR",
             "season": 2024, "week": 1, "espn_id": "nan"},
        ])
        cw = build_crosswalk(rosters, last_verified_timestamp="t")
        assert cw.empty, "'0' and 'nan' are absence, not identity"

    def test_a_float_rendered_vendor_id_keeps_its_integer_form(self):
        """`espn_id` arrives as a float across some seasons (the N0.2 type-drift), so '4241463.0'
        and '4241463' must be the SAME key or tier 1 misses every affected row."""
        rosters = pd.DataFrame([{
            "gsis_id": "g1", "full_name": "A", "team": "CLE", "position": "WR",
            "season": 2024, "week": 1, "espn_id": "4241463.0",
        }])
        cw = build_crosswalk(rosters, last_verified_timestamp="t")
        assert cw.loc[0, "source_player_id"] == "4241463"


# ── source guards on the two consumers (prose must not be able to satisfy them) ──────────────────
def _strip_sql_comments(sql: str) -> str:
    """Comments explain the fix; only CODE may satisfy the guard (INC-38)."""
    return "\n".join(line.split("--")[0] for line in sql.splitlines())


def _strip_py_comments(src: str) -> str:
    return "\n".join(line.split("#")[0] for line in src.splitlines())


class TestConsumersCannotReintroduceTheSilentZero:
    def test_fct_player_week_does_not_coalesce_a_snap_value_to_zero(self):
        """The exact regression: `coalesce(sc.offense_pct, 0.0)` turned an unresolved identity into
        an observed zero. Comments are stripped first, so the explanatory note above the fix cannot
        make this pass with the defect restored."""
        sql = _strip_sql_comments(
            (REPO / "quant_sports_intel_models/sports_dbt/models/nfl/marts/fct_player_week.sql")
            .read_text()
        )
        for col in ("offense_pct", "offense_snaps", "special_teams_pct", "special_teams_snaps"):
            assert not re.search(rf"coalesce\s*\(\s*sc\.{col}\s*,\s*0", sql, re.I), (
                f"{col} is coalesced to 0 again — an unresolved identity would read as an "
                "observed zero (v3 §12A)"
            )

    def test_fct_player_week_labels_the_kind_of_absence(self):
        sql = _strip_sql_comments(
            (REPO / "quant_sports_intel_models/sports_dbt/models/nfl/marts/fct_player_week.sql")
            .read_text()
        )
        assert "snap_source_tier" in sql
        assert "'observed'" in sql, "without an observed tier the two kinds of zero merge again"

    def test_the_snap_bridge_is_keyed_on_the_id_alone_not_on_season_plus_id(self):
        """A per-SEASON pfr bridge leaves the high-value cohort unresolved (`pfr_id` is 25–53% NULL
        in any given season). Keying on the id alone is what recovers it at tier 1."""
        sql = _strip_sql_comments(
            (REPO / "quant_sports_intel_models/sports_dbt/models/nfl/marts/fct_player_week.sql")
            .read_text()
        )
        assert "pfr_bridge" in sql
        assert re.search(r"having\s+count\s*\(\s*distinct\s+player_id\s*\)\s*=\s*1", sql, re.I), (
            "the bridge must abstain on an id claimed by two players rather than pick one"
        )

    def test_sat_snap_counts_weekly_has_no_second_copy_of_the_bridge(self):
        """Two copies of a bridge drift apart, and the satellite's copy is where the silent zero
        would come back unnoticed. It reads the resolved columns off the fact instead."""
        sql = _strip_sql_comments(
            (REPO / "quant_sports_intel_models/sports_dbt/models/nfl/marts/sat_snap_counts_weekly.sql")
            .read_text()
        )
        assert not re.search(r"coalesce\s*\([^)]*offense_pct[^)]*,\s*0", sql, re.I)
        assert "fct_player_week" in sql
        assert "stg_nfl_snap_counts" not in sql, "the satellite must not re-derive the bridge"

    def test_the_nf_w0_audit_resolves_snaps_through_the_entity_service(self):
        """The audit used to INNER-join snaps to a per-season bridge, silently dropping 19–46% of
        snap rows per season. It must now go through the ladder, which is row-preserving."""
        src = _strip_py_comments(
            (REPO / "quant_sports_intel_models/football/nfl/fantasy/run_nf_w0_audit.py").read_text()
        )
        # ⚠️ Assert a CALL, not a mention. `"resolve_snap_counts" in src` is satisfied by the
        # IMPORT line alone, so it stays green when the call is swapped for something else — the
        # same vacuity as matching a name in a comment. (Found by RED-proving this very guard.)
        assert re.search(r"=\s*resolve_snap_counts\s*\(", src), (
            "the audit must RESOLVE snaps through the ladder, not merely import it"
        )
        assert not re.search(r"join\s*\(\s*select\s+distinct\s+season,\s*pfr_id", src, re.I), (
            "the per-season INNER-join bridge is back — it drops unresolved snap rows silently"
        )
