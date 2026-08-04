"""Guards for `resolve_board` — the export's board-source choice (2026-08-03).

🚨 WHY. `resolve_board` used to take the FIRST candidate that existed on disk (`BOARD_WITH_COMPS`
then `BOARD_PLAIN`), a fixed preference with no regard for age. `build_prospect_board.py` writes
`BOARD_PLAIN`, and since E8.1 it carries the E7.13 comps NATIVELY — so `BOARD_WITH_COMPS` is the
LEGACY second-export path, and any checkout that ever ran it keeps a stale CSV forever that every
later publish silently preferred.

Live consequence: a rebuild carrying 43 trade-corrected orgs was written to disk and then IGNORED;
prod got a TWO-DAY-OLD board and moved backwards an hour after a good publish. Nothing in the
ordinary output said so — a healthy build report, then a plausible player count from a different
file. It reproduced only on a checkout holding the legacy artifact, so a fresh worktree passes by
accident, which is how it shipped.
"""
from __future__ import annotations

import importlib
import os

import pytest

MOD = "quant_sports_intel_models.baseball.fantasy.export_prospect_board_json"

_COMPS_HEADER = "player_name,org,comp_score,comp_names\n"
_PLAIN_HEADER = "player_name,org\n"


@pytest.fixture()
def exp(tmp_path, monkeypatch):
    """The module with both candidate paths redirected into a tmp dir."""
    mod = importlib.import_module(MOD)
    comps = tmp_path / "e7_13_prospect_board_comps.csv"
    plain = tmp_path / "e8_0_prospect_board.csv"
    monkeypatch.setattr(mod, "BOARD_WITH_COMPS", comps)
    monkeypatch.setattr(mod, "BOARD_PLAIN", plain)
    return mod, comps, plain


def _write(path, header, *, mtime):
    path.write_text(header + "Someone,BOS\n")
    os.utime(path, (mtime, mtime))


def test_a_fresh_plain_board_beats_a_stale_comps_board():
    """⭐ THE REGRESSION ITSELF. Both carry comps; the newer one must win.

    Pre-fix this returned the stale comps board and published an Aug-2 file over a fresh build.
    """
    mod = importlib.import_module(MOD)
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        comps, plain = d / "comps.csv", d / "plain.csv"
        _write(comps, _COMPS_HEADER, mtime=1_000_000)      # older
        _write(plain, _COMPS_HEADER, mtime=2_000_000)      # newer, also has comps
        orig = (mod.BOARD_WITH_COMPS, mod.BOARD_PLAIN)
        mod.BOARD_WITH_COMPS, mod.BOARD_PLAIN = comps, plain
        try:
            assert mod.resolve_board(None) == plain, \
                "a stale comps board must not outrank a freshly built one"
        finally:
            mod.BOARD_WITH_COMPS, mod.BOARD_PLAIN = orig


def test_a_fresh_comps_board_still_wins_when_it_is_newest(exp):
    """The legacy path is not banned — when it IS the freshest, it is the right answer."""
    mod, comps, plain = exp
    _write(plain, _COMPS_HEADER, mtime=1_000_000)
    _write(comps, _COMPS_HEADER, mtime=2_000_000)
    assert mod.resolve_board(None) == comps


def test_comps_beat_freshness_because_a_pre_comp_board_is_a_real_downgrade(exp, caplog):
    """A NEWER board WITHOUT comps must NOT be chosen — that is the pre-comp ordering E8.1 exists
    to prevent — but the situation must be announced, not silent."""
    mod, comps, plain = exp
    _write(comps, _COMPS_HEADER, mtime=1_000_000)          # older, has comps
    _write(plain, _PLAIN_HEADER, mtime=2_000_000)          # newer, NO comps
    with caplog.at_level("WARNING"):
        assert mod.resolve_board(None) == comps
    assert any("NEWER" in r.message for r in caplog.records), \
        "publishing the older board while a newer one exists must be stated, never silent"


def test_only_one_candidate_present_is_used(exp):
    mod, comps, plain = exp
    _write(plain, _COMPS_HEADER, mtime=1_000_000)
    assert mod.resolve_board(None) == plain


def test_an_explicit_board_always_wins(exp, tmp_path):
    """The operator's `--board` escape hatch must never be second-guessed."""
    mod, comps, plain = exp
    _write(comps, _COMPS_HEADER, mtime=9_000_000)
    chosen = tmp_path / "hand_picked.csv"
    _write(chosen, _COMPS_HEADER, mtime=1)
    assert mod.resolve_board(str(chosen)) == chosen


def test_no_candidate_present_refuses_with_the_build_command(exp):
    mod, _, _ = exp
    with pytest.raises(SystemExit, match="build_prospect_board"):
        mod.resolve_board(None)


def test_has_comps_reads_the_header_only(exp):
    """These CSVs are ~2 MB; the check must not load them."""
    mod, comps, plain = exp
    _write(comps, _COMPS_HEADER, mtime=1)
    _write(plain, _PLAIN_HEADER, mtime=1)
    assert mod._has_comps(comps) is True
    assert mod._has_comps(plain) is False
