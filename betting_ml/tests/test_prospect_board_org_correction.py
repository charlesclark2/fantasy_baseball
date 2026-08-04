"""Guards for `apply_roster_org_correction` — the roster-org coalesce (2026-08-03).

WHY THIS EXISTS. FanGraphs THE BOARD's `org` is editorial and does NOT move for a trade (measured:
47 board rows changed level/rank across 07-27 → 08-03, ZERO changed org, straight through a
deadline). `org` drives `mlb_league`, which is THE filter a single-league dynasty draft runs on, so
a stale org silently puts a player on the wrong AL/NL sheet — on 8/3 that was 22 players, 9 of them
INVISIBLE on the sheet they belonged to (incl. River Ryan, FV 55, overall #18).

⚠️ EACH TEST ISOLATES ONE RULE BRANCH. The correction is a multi-clause rule (slug moved / roster
moved / both agree / both conflict), and a fixture that trips two clauses at once proves neither
(the NF-D17 lesson: a guard on an `and`-composed rule is vacuous unless its fixture satisfies every
OTHER clause). Every fixture here differs from the baseline in exactly ONE way.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.prospect_board.board_assembly import ProspectBoardError
from betting_ml.scripts.prospect_board.build_consensus_assembly import apply_roster_org_correction


def _row(name, org, slug=None, roster=None, *, on_board=True, org_rank=None):
    return {
        "player_name": name, "org": org, "mlb_league": "AL" if org in ("BOS", "BAL", "TBR") else "NL",
        "pipeline_org_slug": slug, "pipeline_org_roster": roster,
        "on_fangraphs_board": on_board, "org_rank": org_rank,
    }


def _apply(rows, **kw):
    return apply_roster_org_correction(pd.DataFrame(rows), **kw)


def test_both_signals_moved_and_agree_corrects_the_org():
    """The dominant real case (35 of 43 on 8/3): list AND roster both say the new org."""
    out, rep = _apply([_row("Anthony Eyanson", "BOS", slug="BAL", roster="BAL")])
    assert out.loc[0, "org"] == "BAL"
    assert out.loc[0, "org_prior"] == "BOS"
    assert out.loc[0, "org_source"] == "mlb_pipeline"
    assert rep["org_corrected"] == 1


def test_slug_moved_alone_corrects_the_org():
    """Tyler Uberstine 8/3: on the BRAVES list, roster still Worcester (BOS). The LIST caught up.

    Isolating clause: roster AGREES with the baseline, so only the slug clause can flip this.
    """
    out, _ = _apply([_row("Tyler Uberstine", "BOS", slug="ATL", roster="BOS")])
    assert out.loc[0, "org"] == "ATL", "a slug-only move must still correct the org"


def test_roster_moved_alone_corrects_the_org():
    """Juan Brito 8/3: still on the GUARDIANS list, roster says Cincinnati. The ROSTER caught up.

    Isolating clause: slug AGREES with the baseline, so only the roster clause can flip this.
    ⭐ This is the case a `pipeline_org` (slug-first coalesce) read misses entirely — 6 players on
    8/3 — which is the whole reason both signals are carried separately.
    """
    out, _ = _apply([_row("Juan Brito", "CLE", slug="CLE", roster="CIN")])
    assert out.loc[0, "org"] == "CIN", "a roster-only move must still correct the org"


def test_a_conflict_refuses_to_guess_and_is_reported():
    """Both signals moved to DIFFERENT orgs — unresolvable. Keep the baseline, surface it.

    Did not occur on 8/3 (0 of 726), but picking one arbitrarily would move a player into a league
    he may not be in, which is exactly the failure this function exists to prevent.
    """
    out, rep = _apply([_row("Ambiguous Guy", "BOS", slug="ATL", roster="NYM")])
    assert out.loc[0, "org"] == "BOS", "a conflict must NOT be silently resolved"
    assert out.loc[0, "org_source"] == "conflict"
    assert rep["org_conflicts"] == 1
    assert rep["conflicts"][0]["slug_org"] == "ATL"
    assert rep["conflicts"][0]["roster_org"] == "NYM"
    assert rep["org_corrected"] == 0, "a conflict is not a correction"


def test_no_move_leaves_everything_alone():
    out, rep = _apply([_row("Stay Put", "BOS", slug="BOS", roster="BOS", org_rank=4)])
    assert out.loc[0, "org"] == "BOS"
    assert out.loc[0, "org_source"] == "fangraphs"
    assert pd.isna(out.loc[0, "org_prior"])
    assert out.loc[0, "org_rank"] == 4, "an unmoved player keeps his org rank"
    assert rep["org_corrected"] == 0


def test_missing_pipeline_signals_are_uninformative_not_a_move():
    """A player Pipeline does not rank (~387 on the board) must be left untouched, never blanked."""
    out, rep = _apply([_row("Unranked Guy", "BOS", slug=None, roster=None, org_rank=7)])
    assert out.loc[0, "org"] == "BOS"
    assert out.loc[0, "org_source"] == "fangraphs"
    assert out.loc[0, "org_rank"] == 7
    assert rep["org_corrected"] == 0


def test_the_league_is_recomputed_so_the_draft_sheet_actually_changes():
    """The POINT of the correction: River Ryan LAD(NL) → DET(AL) must land on the AL sheet."""
    out, rep = _apply([_row("River Ryan", "LAD", slug="DET", roster="DET")])
    assert out.loc[0, "mlb_league"] == "AL", "mlb_league must follow the corrected org"
    assert rep["league_changed"] == 1


def test_org_rank_is_nulled_for_a_moved_player_and_preserved_beside_it():
    """FanGraphs' org rank is a rank WITHIN THE PRIOR ORG — carrying it onto the new org would
    assert a standing FanGraphs never published."""
    out, _ = _apply([_row("Anthony Eyanson", "BOS", slug="BAL", roster="BAL", org_rank=3)])
    assert np.isnan(out.loc[0, "org_rank"]), "a prior-org rank must not survive onto the new org"
    assert out.loc[0, "org_rank_prior_org"] == 3, "but it must not be lost either"


def test_a_pipeline_only_row_is_not_touched():
    """A Pipeline-only player already carries Pipeline's org; re-deriving would be a no-op at best."""
    out, rep = _apply([_row("Pipeline Only", "NYM", slug="NYM", roster="NYM", on_board=False)])
    assert out.loc[0, "org"] == "NYM"
    assert rep["board_players_checked"] == 0


def test_an_unmapped_corrected_org_hard_errors_rather_than_dropping_the_player():
    """An org with no AL/NL mapping silently vanishes from the only sheet the operator drafts off —
    the same rule `assemble_board` already enforces for the FanGraphs side."""
    with pytest.raises(ProspectBoardError, match="no AL/NL mapping"):
        _apply([_row("Bad Org", "BOS", slug="ZZZ", roster="ZZZ")])


def test_strict_league_false_downgrades_the_hard_error():
    out, _ = _apply([_row("Bad Org", "BOS", slug="ZZZ", roster="ZZZ")], strict_league=False)
    assert out.loc[0, "org"] == "ZZZ"
    assert pd.isna(out.loc[0, "mlb_league"])


def test_case_and_whitespace_do_not_fabricate_a_move():
    """A casing/whitespace difference is not a trade — it must not null an org rank."""
    out, rep = _apply([_row("Case Guy", "BOS", slug=" bos ", roster="Bos", org_rank=5)])
    assert rep["org_corrected"] == 0
    assert out.loc[0, "org_rank"] == 5
