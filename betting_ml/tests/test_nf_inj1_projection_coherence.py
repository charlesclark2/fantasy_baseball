"""NF-INJ1 — the served (expected-games, stat-line) coherence guard + the injury-input freshness gate.

WHAT THESE DEFEND (measured on the live 2026 board, `ablation_results/nf_inj1_diagnosis.md`):
  * the served `projections.json` carried nine veteran QBs whose stat line is impossible at their own
    `g` (Easton Stick: 153.4 pass attempts over 1.9 games = 82.7/g against an all-time max of 45.4);
  * the board was built on a 20-day-old injury snapshot while the feed itself was 15h fresh, so 18
    currently-PUP/IR players projected at their healthy rate.

⭐ EVERY CLAUSE HAS ITS OWN ISOLATING FIXTURE (NF-D17): a fixture that trips two clauses proves
neither. The two vacuity clauses matter most here — `applicable=False` and `n_unevaluable` are the
two ways this check can report "0 violations" without having checked anything.

`red_proof_nf_inj1.py` breaks the source and proves each of these goes RED.
"""

import json

import pytest

from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as C


# ── fixtures: one shape per clause ───────────────────────────────────────────────────────────────
def _qb(name="Healthy QB", g=16.0, att=560.0, yds=4200.0, pid="x"):
    """A COHERENT starting QB: 35 att/g, 262 yd/g — comfortably inside the envelope."""
    return {"id": pid, "name": name, "pos": "QB", "g": g, "passAtt": att, "passYds": yds}


def _stick():
    """The measured live defect, verbatim off the 2026 board."""
    return {"id": "00-0035282", "name": "Easton Stick", "pos": "QB", "g": 1.9,
            "passAtt": 153.4, "passYds": 1045.6}


def _board_row():
    """A LEAGUE-BOARD row: `g` and `pts`, NO counting line. The envelope structurally cannot fire."""
    return {"id": "b", "name": "Board Row", "pos": "RB", "g": 14.0, "pts": 210.0}


# ── the envelope is a derived design quantity, not a tuned one ───────────────────────────────────
def test_envelope_is_the_documented_realized_maximum():
    """Pins the derived numbers. ⛔ E2.1-r: these come from 11,190 realized player-seasons and must
    never be widened to accommodate a board that failed them — a change here is a reviewable diff."""
    assert C.REALIZED_MAX_PER_GAME["QB"]["passAtt"] == pytest.approx(45.44)
    assert C.REALIZED_MAX_PER_GAME["QB"]["passYds"] == pytest.approx(371.20)
    assert C.REALIZED_MAX_PER_GAME["RB"]["rushAtt"] == pytest.approx(27.38)
    assert C.REALIZED_MAX_PER_GAME["WR"]["recYds"] == pytest.approx(122.75)
    assert set(C.REALIZED_MAX_PER_GAME) == {"QB", "RB", "WR", "TE"}
    assert C.ENVELOPE_PROVENANCE["seasons"] == "2006-2025"
    assert sum(C.ENVELOPE_PROVENANCE["n_player_seasons"].values()) == 11190


def test_a_real_starter_line_is_coherent():
    """The two-sided control: the guard must PASS the ordinary case, or it is just a tripwire."""
    assert C.row_violations(_qb()) == []
    assert C.coherence_summary([_qb()])["n_violating_players"] == 0


def test_the_measured_live_defect_is_caught():
    v = C.row_violations(_stick())
    stats = {x["stat"] for x in v}
    assert stats == {"passAtt", "passYds"}
    att = next(x for x in v if x["stat"] == "passAtt")
    assert att["implied_per_game"] == pytest.approx(80.74, abs=0.01)
    assert att["max_ever_per_game"] == pytest.approx(45.44)
    assert att["times_over"] > 1.7


def test_violation_needs_BOTH_a_big_line_and_a_small_g():
    """ISOLATING: the same season total over a full season is fine — it is the RATIO that is
    indicted, which is what lets this guard fire without first settling which half is wrong."""
    assert C.row_violations({**_stick(), "g": 16.0}) == []          # same line, real games → OK
    # …and a SMALLER line at the same tiny g still fires, so the clause is the ratio and not the
    # season total: 100 att / 1.9 g = 52.6/g, over the 45.44 max.
    assert C.row_violations({**_stick(), "passAtt": 100.0, "passYds": 600.0, "g": 1.9}) != []
    # the two-sided edge: 80 att / 1.9 g = 42.1/g is UNDER the max and must NOT fire
    assert [v for v in C.row_violations({**_stick(), "passAtt": 80.0, "passYds": 600.0, "g": 1.9})
            if v["stat"] == "passAtt"] == []


# ── vacuity clause 1: a blob with no stat line is NOT a clean board ──────────────────────────────
def test_a_board_blob_reports_NOT_APPLICABLE_rather_than_clean():
    s = C.coherence_summary([_board_row(), _board_row()])
    assert s["applicable"] is False
    assert s["n_violating_players"] == 0          # true, and MEANINGLESS on its own
    assert s["n_with_stat_line"] == 0
    assert "NOT APPLICABLE" in C.format_summary(s, "board")
    assert "NOT a clean board" in C.format_summary(s, "board")


def test_applicable_is_true_once_any_row_carries_a_stat_line():
    s = C.coherence_summary([_board_row(), _qb()])
    assert s["applicable"] is True


# ── vacuity clause 2: an unreadable `g` is counted, not silently passed ──────────────────────────
def test_rows_without_usable_games_are_counted_unevaluable():
    """NF1.7 (a): a row the check could not read has not passed it."""
    rows = [{**_qb(), "g": None}, {**_qb(), "g": 0.0}, _qb()]
    s = C.coherence_summary(rows)
    assert s["n_unevaluable"] == 2
    assert s["n_in_scope"] == 3
    assert "UNEVALUABLE" in C.format_summary(s, "x")


def test_out_of_scope_positions_are_not_unevaluable():
    """K/DST carry no counting line by design — out of scope is different from unreadable."""
    s = C.coherence_summary([{"id": "k", "name": "K", "pos": "K", "g": 17.0}])
    assert s["n_in_scope"] == 0 and s["n_unevaluable"] == 0


# ── the injury-input freshness gate ──────────────────────────────────────────────────────────────
def test_fresh_injury_input_is_OK():
    r = C.assess_injury_input_freshness(
        {"sleeper_status_as_of": "2026-08-21T00:00:00+00:00"}, "2026-08-21T06:00:00+00:00")
    assert r["verdict"] == "OK" and r["lag_hours"] == pytest.approx(6.0)


def test_the_measured_live_staleness_is_STALE():
    r = C.assess_injury_input_freshness(
        {"sleeper_status_as_of": "2026-07-26T23:20:48+00:00"}, "2026-08-21T05:00:00+00:00")
    assert r["verdict"] == "STALE" and r["lag_hours"] > 600


def test_a_missing_stamp_is_UNKNOWN_never_OK():
    for vintage in (None, {}, {"sleeper_status_as_of": "not-a-date"}):
        assert C.assess_injury_input_freshness(vintage, "2026-08-21T05:00:00+00:00")["verdict"] \
            == "UNKNOWN"


def test_the_bar_is_derived_from_the_feeds_own_declared_SLA():
    """DERIVED, not chosen: 2x the feed's INC-41 `max_lag_hours`. Pinned against the registry so a
    change to one cannot silently desynchronise from the other."""
    from betting_ml.monitoring import sports_delta_freshness as SDF
    feed = SDF.by_name("nfl_sleeper_injuries")
    assert C.INJURY_INPUT_MAX_LAG_HOURS == pytest.approx(2.0 * feed.max_lag_hours)


# ── the exporter wrapper, driven through the REAL function on REAL staged bytes ──────────────────
def _stage(tmp_path, players, freshness_stamp="2026-08-21T00:00:00+00:00"):
    (tmp_path / "projections.json").write_text(json.dumps(
        {"season": 2026, "players": players,
         "freshness": {"input_vintage": {"sleeper_status_as_of": freshness_stamp}}}))
    return tmp_path


def test_exporter_guard_is_ALERT_tier_by_default(tmp_path, caplog):
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    d = _stage(tmp_path, [_qb(), _stick()])
    fr = json.loads((d / "projections.json").read_text())["freshness"]
    with caplog.at_level("INFO"):
        out = E.report_publish_coherence(d, 2026, fr, "2026-08-21T06:00:00+00:00", strict=False)
    assert out["violating_players"] == 1                      # did NOT raise
    assert "[METRIC] nf_inj1_coherence_violating_players=1" in caplog.text


def test_exporter_guard_refuses_under_strict(tmp_path):
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    d = _stage(tmp_path, [_qb(), _stick()])
    fr = json.loads((d / "projections.json").read_text())["freshness"]
    with pytest.raises(SystemExit) as ei:
        E.report_publish_coherence(d, 2026, fr, "2026-08-21T06:00:00+00:00", strict=True)
    assert "NF-INJ1 PUBLISH REFUSED" in str(ei.value)


def test_strict_passes_a_coherent_board_with_a_fresh_injury_input(tmp_path):
    """The two-sided control on the REFUSAL path: strict must not refuse a good board, or it is a
    switch nobody can ever turn on."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    d = _stage(tmp_path, [_qb(), _qb(name="Other", pid="y")])
    fr = json.loads((d / "projections.json").read_text())["freshness"]
    out = E.report_publish_coherence(d, 2026, fr, "2026-08-21T06:00:00+00:00", strict=True)
    assert out["violating_players"] == 0
    assert out["injury_input"]["verdict"] == "OK"


def test_strict_refuses_on_a_STALE_injury_input_even_when_every_line_is_coherent(tmp_path):
    """ISOLATING for the freshness clause: a perfectly coherent board still must not ship on a
    20-day-old injury snapshot — that was the live facet-1 defect and it moves no stat line."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    d = _stage(tmp_path, [_qb()], freshness_stamp="2026-07-26T23:20:48+00:00")
    fr = json.loads((d / "projections.json").read_text())["freshness"]
    with pytest.raises(SystemExit) as ei:
        E.report_publish_coherence(d, 2026, fr, "2026-08-21T05:00:00+00:00", strict=True)
    assert "STALE" in str(ei.value)


def test_strict_refuses_when_NO_staged_file_carries_a_stat_line(tmp_path):
    """ISOLATING for the applicability clause: a run that checked nothing must not report a pass."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    (tmp_path / "board_full_ppr_12.json").write_text(json.dumps([_board_row()]))
    with pytest.raises(SystemExit) as ei:
        E.report_publish_coherence(tmp_path, 2026,
                                   {"input_vintage": {"sleeper_status_as_of":
                                                      "2026-08-21T00:00:00+00:00"}},
                                   "2026-08-21T06:00:00+00:00", strict=True)
    assert "carrying a scorable stat line: 0" in str(ei.value)
