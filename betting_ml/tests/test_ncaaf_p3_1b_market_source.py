"""test_ncaaf_p3_1b_market_source.py — NCAAF-P3.1b: WHICH market line, from WHEN, and never a
line we cannot prove is pre-kickoff.

P0.6c has captured TWO snapshots per NCAAF kickoff since 2026-08-01 — a ~24h-prior T-1 line and a
K−5min close — and `payloads._market()` read only the `close_*` columns and hardcoded
`MARKET_SOURCE_CLOSE`. So the one snapshot that is genuinely a PRE-kickoff line, i.e. the honest
comparator for a pre-kickoff projection, was stored (and paid for) and never served.

WHAT THESE GUARDS DEFEND, and why each is a property rather than a preference:

  1. **PREFERENCE + LABEL.** T-1 is preferred and the served block SAYS which line it is
     (`source`) and when it was taken (`as_of`). Two lines a day apart under one unlabelled number
     is the mislabelling class this repo keeps paying for (INC-41's two unequal numbers under one
     word), and it is not hypothetical here: the kind-blind staging leg takes the LATEST
     pre-commence snapshot, so a kickoff with a T-1 and no close yet was ALREADY serving T-1 values
     under a `close` label.
  2. **THE LEAKAGE GUARD, FAIL-CLOSED.** Every attached line must be PROVABLY strictly pre-kickoff.
     Not because the capture buffer is suspect — the staging SQL filters `_snapshot_ts <
     commence_time` already — but because that join matches Odds-API team names to CFBD names by
     PREFIX, and a prefix collision attaches ANOTHER game's line, whose instant has no relationship
     to this kickoff. A line we cannot prove is pre-game is refused: a check that did not run is
     not a pass (NF1.7 (a)).
  3. **ADDITIVE ONLY (NF-C0), DECLARED (E9.41).** The API Lambda ships only via `deploy.sh` while
     the frontend auto-deploys, so both skew directions are live at every deploy; a removed or
     renamed key is a blank screen with a 200 and no error anywhere.
  4. **NO CLIENT CHANGE.** The P3.2 panel must render a T-1-sourced line as it renders a close one.
     Proven two ways rather than by eye: the panel reads no `source` at all, and two payloads
     differing ONLY in source are byte-identical in every field the panel reads.

⛔ `best_alpha = 0` throughout. A market line is context beside the model's number, never a pick,
and nothing here computes or asserts a vs-market performance reading (VAL1's null stands).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd
import pytest

from app.backend.models import ncaaf as contract
from quant_sports_intel_models.football.ncaaf.serving import payloads

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "frontend/components/ncaaf/market-comparison.tsx"

#: A kickoff, its T-1 line (~24h before) and its close (~5min before) — the real relative vintages.
KICKOFF = "2026-08-29T23:30:00.000Z"
T1_TS = "2026-08-28T23:30:00.000Z"
CLOSE_TS = "2026-08-29T23:25:00.000Z"

T1_LINE = {"t1_home_spread": -6.5, "t1_total": 55.5,
           "t1_home_ml_american": -240.0, "t1_home_ml_prob": 0.7058823529411765,
           "t1_snapshot_ts": T1_TS}
CLOSE_LINE = {"close_home_spread": -8.0, "close_total": 57.5,
              "close_home_ml_american": -320.0, "close_home_ml_prob": 0.7619047619047619,
              "close_snapshot_ts": CLOSE_TS}

#: Every field `NcaafMarketLine` declared BEFORE this story. NF-C0's additive rule is checked
#: against this list, not against "whatever the model has today" (which would be a tautology).
PRE_P3_1B_FIELDS = frozenset({
    "status", "reason", "source", "snapshot_ts", "home_spread", "total",
    "home_moneyline_american", "home_moneyline_implied_probability",
})


def _snapshot_row(commence: str | None = KICKOFF) -> dict:
    """A minimal persisted snapshot row — enough to build a payload, nothing model-specific."""
    row = {
        "game_id": 401752677, "season": 2026, "commence_time": commence,
        "snapshot_ts": "2026-08-27T12:00:00.000Z", "snapshot_kind": "pre_kickoff",
        "season_type": "regular", "cfbd_week": 1,
        "home_team_id": 194, "home_team": "Ohio State", "home_conference": "Big Ten",
        "away_team_id": 2050, "away_team": "Texas", "away_conference": "SEC",
        "p_home_win": 0.71, "mu_margin": 6.9, "sigma_margin": 15.8,
        "mu_total": 54.2, "sigma_total": 12.4,
        "model_version": "ncaaf_game_v2", "model_form": "student_t",
    }
    for i, level in enumerate(payloads.QUANTILE_LEVELS):
        row[payloads._q_col("margin", level)] = 6.9 + (i - 3) * 9.0
        row[payloads._q_col("total", level)] = 54.2 + (i - 3) * 8.0
    return row


def _market(row: dict | None, *, commence: str | None = KICKOFF, read_failed: bool = False) -> dict:
    return payloads._market(row, read_failed=read_failed, commence_time=commence, game_id=1)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Preference, and saying which line it is
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_t1_line_is_preferred_over_the_close_and_says_so():
    """The surface serves a PRE-KICKOFF projection, so the comparator is the market's PRE-kickoff
    line. The close is the fallback, not the preference — it is the better-informed number, which
    is precisely why quoting it beside a day-old projection flatters neither honestly."""
    block = _market({**T1_LINE, **CLOSE_LINE})
    assert block["status"] == "available"
    assert block["source"] == payloads.MARKET_SOURCE_T1
    assert block["home_spread"] == T1_LINE["t1_home_spread"], "the CLOSE values were served"
    assert block["total"] == T1_LINE["t1_total"]
    assert block["home_moneyline_american"] == T1_LINE["t1_home_ml_american"]
    assert block["snapshot_ts"] == T1_TS and block["as_of"] == T1_TS


def test_the_close_is_served_when_no_t1_snapshot_was_captured():
    """The fallback, and the state every pre-P3.1b payload was in."""
    block = _market(dict(CLOSE_LINE))
    assert block["status"] == "available"
    assert block["source"] == payloads.MARKET_SOURCE_CLOSE
    assert block["home_spread"] == CLOSE_LINE["close_home_spread"]
    assert block["as_of"] == CLOSE_TS


def test_a_t1_only_kickoff_is_no_longer_labelled_a_close():
    """⭐ THE MISLABEL THIS STORY FIXES, and it predates the story.

    `build_clv_staging`'s kind-blind leg takes the LATEST pre-commence snapshot per event. For a
    kickoff whose T-1 has been captured and whose close has NOT — the pre-kickoff case this whole
    story exists for — that leg picks the T-1 row up and files it under `close_*`. Preferring the
    explicitly-kinded columns makes the label match the line."""
    both_legs_see_the_t1_row = {**T1_LINE,
                                "close_home_spread": T1_LINE["t1_home_spread"],
                                "close_total": T1_LINE["t1_total"],
                                "close_home_ml_american": T1_LINE["t1_home_ml_american"],
                                "close_home_ml_prob": T1_LINE["t1_home_ml_prob"],
                                "close_snapshot_ts": T1_TS}
    block = _market(both_legs_see_the_t1_row)
    assert block["source"] == payloads.MARKET_SOURCE_T1, (
        "a T-1 snapshot is still being served under a `close` label — the number is right and the "
        "word beside it is wrong, which is the harder defect to notice")


def test_as_of_always_equals_the_served_lines_own_snapshot_instant():
    """`as_of` is the reader-facing name for the instant, and it must never drift from the line it
    labels — an `as_of` copied from the other candidate would be a correct-looking lie."""
    for row, expected in ((dict(T1_LINE), T1_TS), (dict(CLOSE_LINE), CLOSE_TS),
                          ({**T1_LINE, **CLOSE_LINE}, T1_TS)):
        block = _market(row)
        assert block["as_of"] == block["snapshot_ts"] == expected


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The leakage guard — fail-closed, both directions RED-proven by ncaaf_p3_1b_red_proof.py
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_snapshot_at_or_after_kickoff_attaches_nothing_and_names_the_refusal():
    """Never a post-kickoff line labelled as a pre-game price. `<` is strict: a snapshot exactly AT
    kickoff is refused too, because equality proves nothing about which came first."""
    after = {**T1_LINE, "t1_snapshot_ts": "2026-08-30T02:00:00.000Z"}
    at = {**T1_LINE, "t1_snapshot_ts": KICKOFF}
    for row in (after, at):
        block = _market(row)
        assert block["status"] == "unavailable"
        assert block["reason"] == payloads.MARKET_REASON_NOT_PRE_KICKOFF
        assert block["home_spread"] is None and block["total"] is None, (
            "a refused row attached its numbers anyway")
        assert block["source"] is None and block["as_of"] is None


def test_the_refusal_is_logged_loudly_not_swallowed_into_a_blank():
    """A silent refusal is indistinguishable from 'nobody priced this game' — and one of those is a
    defect in our own odds join (a prefix collision attaching the WRONG game's line)."""
    logger = logging.getLogger("ncaaf.serving.payloads")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logger.addHandler(handler)
    try:
        _market({**T1_LINE, "t1_snapshot_ts": "2026-08-30T02:00:00.000Z"})
    finally:
        logger.removeHandler(handler)
    assert records, "the refusal produced no log record at all"
    assert any(r.levelno >= logging.WARNING and "REFUSED" in r.getMessage() for r in records)


@pytest.mark.parametrize("commence", [None, "", "not-a-timestamp", float("nan")],
                         ids=["none", "empty", "garbage", "nan"])
def test_a_kickoff_we_cannot_read_refuses_the_line_rather_than_attaching_it(commence):
    """FAIL CLOSED. With no readable kickoff the guard cannot RUN, and a check that did not run is
    not a pass (NF1.7 (a)) — the alternative is serving a line of unknown vintage as a pre-game
    price, which is the one thing this surface must never do."""
    block = _market({**T1_LINE, **CLOSE_LINE}, commence=commence)
    assert block["status"] == "unavailable"
    assert block["reason"] == payloads.MARKET_REASON_INSTANT_UNPROVABLE
    assert block["home_spread"] is None


@pytest.mark.parametrize("snapshot_ts", [None, "", "not-a-timestamp"],
                         ids=["none", "empty", "garbage"])
def test_a_snapshot_instant_we_cannot_read_refuses_the_line_too(snapshot_ts):
    """The other half of the pair — the guard needs BOTH instants, and neither may be guessed."""
    block = _market({**T1_LINE, "t1_snapshot_ts": snapshot_ts})
    assert block["status"] == "unavailable"
    assert block["reason"] == payloads.MARKET_REASON_INSTANT_UNPROVABLE


def test_a_refused_t1_does_not_veto_a_valid_close():
    """A refused candidate is refused; it is not a verdict on the OTHER candidate.

    ⚠️ The direction matters and the obvious test is VACUOUS: with T-1 preferred, a bad CLOSE is
    never even examined, so "a bad close does not veto the T-1" is true by the ordering alone and
    would pass with the fall-through deleted. The observable property is the other way round — a
    mis-joined T-1 must not blank a perfectly good close."""
    block = _market({**T1_LINE, "t1_snapshot_ts": "2026-08-30T02:00:00.000Z", **CLOSE_LINE})
    assert block["status"] == "available", "one refused candidate blanked the whole block"
    assert block["source"] == payloads.MARKET_SOURCE_CLOSE
    assert block["home_spread"] == CLOSE_LINE["close_home_spread"]
    assert block["as_of"] == CLOSE_TS


def test_the_refusal_reason_is_distinguishable_from_never_having_been_priced():
    """Three causes of a null market line, three machine-readable values (NF-C6b). A refusal is a
    DEFECT in our join; an absent capture is the honest pre-opener state. Rendering them alike
    costs an investigation every time the first one happens."""
    reasons = {
        _market(None)["reason"],
        _market(None, read_failed=True)["reason"],
        _market({**T1_LINE, "t1_snapshot_ts": "2026-08-30T02:00:00.000Z"})["reason"],
        _market({**T1_LINE, **CLOSE_LINE}, commence=None)["reason"],
    }
    assert len(reasons) == 4, f"two causes render identically: {reasons}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The absent state, unchanged
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_absent_stays_absent_with_the_same_reasons_it_always_had():
    assert _market(None)["reason"] == payloads.MARKET_REASON_NO_CAPTURE
    assert _market(None, read_failed=True)["reason"] == payloads.MARKET_REASON_READ_FAILED


def test_a_staging_row_carrying_no_numbers_is_absent_rather_than_an_available_blank():
    """A row can reach us with a timestamp and no consensus price (no book quoted the market).
    `status="available"` with every number null is a blank cell wearing an availability badge —
    exactly the render `status`/`reason` exist to prevent."""
    block = _market({"close_snapshot_ts": CLOSE_TS, "close_home_spread": None,
                     "close_total": None, "close_home_ml_american": None,
                     "close_home_ml_prob": None})
    assert block["status"] == "unavailable"
    assert block["reason"] == payloads.MARKET_REASON_NO_CAPTURE


def test_nan_columns_from_an_outer_merge_read_as_absent_not_as_zero():
    """`build_clv_staging(with_t1=True)` OUTER-merges the two legs, so the missing leg's columns
    arrive as NaN on a pandas record — never as a fabricated 0.0 line."""
    frame = pd.DataFrame([{**CLOSE_LINE, "t1_home_spread": float("nan"),
                           "t1_total": float("nan"), "t1_home_ml_american": float("nan"),
                           "t1_home_ml_prob": float("nan"), "t1_snapshot_ts": None}])
    block = _market(frame.to_dict("records")[0])
    assert block["source"] == payloads.MARKET_SOURCE_CLOSE
    assert block["home_spread"] == CLOSE_LINE["close_home_spread"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The contract — additive, declared, on the wire
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_market_block_is_additive_over_what_the_deployed_client_already_reads():
    """NF-C0: the API Lambda deploys ONLY via `deploy.sh` while `frontend/` auto-deploys, so a
    removed or renamed key is a 200 with a blank screen and no error anywhere."""
    declared = set(contract.NcaafMarketLine.model_fields)
    missing = PRE_P3_1B_FIELDS - declared
    assert not missing, f"NCAAF-P3.1b removed {sorted(missing)} — additive means ADD ONLY"
    assert "as_of" in declared, "`as_of` is not declared, so Pydantic will strip it (E9.41)"


def test_every_declared_field_is_on_the_wire_in_both_states():
    """Nothing is serialised with `exclude_none`: a declared field is always present, `null` when
    we have no value (ABSENT vs NULL — `app/backend/models/ncaaf.py`)."""
    declared = set(contract.NcaafMarketLine.model_fields)
    for row in (None, dict(T1_LINE), dict(CLOSE_LINE), {**T1_LINE, **CLOSE_LINE}):
        block = payloads.build_game_payload(_snapshot_row(), market_row=row)["market"]
        assert set(block) == declared, f"served keys drift from the contract: {set(block) ^ declared}"


def test_the_new_field_and_source_names_still_carry_no_edge_claim():
    """`best_alpha = 0`. A field or source that READ as a pick would assert something VAL1's null
    forbids, and the guard walking the model tree is the thing that has to keep being true."""
    contract.assert_no_edge_claim_in_schema()
    for source in (payloads.MARKET_SOURCE_T1, payloads.MARKET_SOURCE_CLOSE):
        assert not any(tok in source.lower() for tok in contract.FORBIDDEN_PAYLOAD_TOKENS)


def test_the_game_payload_passes_the_kickoff_into_the_guard():
    """The guard is a property of the (line, game) PAIR. A builder that could not see the kickoff
    could not run it — so the wiring is the guard, and it is asserted rather than assumed."""
    good = payloads.build_game_payload(_snapshot_row(), market_row={**T1_LINE, **CLOSE_LINE})
    assert good["market"]["status"] == "available"
    assert good["market"]["source"] == payloads.MARKET_SOURCE_T1
    no_kickoff = payloads.build_game_payload(_snapshot_row(commence=None),
                                             market_row={**T1_LINE, **CLOSE_LINE})
    assert no_kickoff["market"]["status"] == "unavailable", (
        "build_game_payload attached a line without proving it precedes the kickoff")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The staging read — ONE join, and the T-1 leg cannot leak into a training contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_t1_leg_is_the_same_join_filtered_by_snapshot_kind():
    """E9.61: two renderers of one rule are two rule sets. The T-1 read is `build_clv_staging`'s own
    SQL with a kind filter and a column prefix, not a second copy free to drift."""
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bake
    close_sql = bake._clv_sql("O", "G", 2020, kind=None, prefix="close_")
    t1_sql = bake._clv_sql("O", "G", 2020, kind=bake._SNAPSHOT_KIND_T1, prefix="t1_")
    assert "_snapshot_kind" not in close_sql, (
        "the DEFAULT leg grew a kind filter — that changes the mart P1.4 was decided on")
    assert bake._SNAPSHOT_KIND_T1 in t1_sql and "t1_home_spread" in t1_sql
    # Same skeleton, asserted EXACTLY: remove the two knobs (the kind filter, the column prefix)
    # and the T-1 query must be byte-identical to the one P1.4 was decided on. A looser
    # whitespace-normalised comparison would let a real fork hide in a reformat.
    kind_filter = re.search(r"\n\s+and coalesce.*?= 't_minus_1'", t1_sql, re.S)
    assert kind_filter, "the T-1 leg carries no kind filter, so it is reading BOTH kinds"
    assert t1_sql.replace(kind_filter.group(0), "").replace("t1_", "close_") == close_sql, (
        "the two legs have forked into different joins — a second rule set free to drift from the "
        "one the model was validated against (E9.61)")


def test_the_snapshot_kind_string_matches_the_ingest_module_that_writes_it():
    """A serving read that filtered on a kind nothing writes returns silently EMPTY — a null that
    looks exactly like 'nobody priced this kickoff'."""
    from quant_sports_intel_models.football.ncaaf.ingest import odds_recurring_capture as cap
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bake
    assert bake._SNAPSHOT_KIND_T1 == cap.SNAPSHOT_KIND_T1
    assert bake._SNAPSHOT_KIND_CLOSE == cap.SNAPSHOT_KIND_CLOSE


def test_the_t1_columns_are_opt_in_so_they_can_never_become_a_model_feature():
    """⛔ `feature_columns` excludes ids, labels and `_CLOSE_COLS` BY NAME. A numeric
    `t1_home_spread` in the default frame matches none of those, so it would sail into every
    training contract — and `assert_market_blind` would (correctly) HALT the bake-off. Default-off
    is what keeps this serving story from being able to move a recorded P1.4/P2.1 result."""
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as bake
    import inspect
    signature = inspect.signature(bake.build_clv_staging)
    assert signature.parameters["with_t1"].default is False
    t1_ish = [c for c in bake._CLOSE_COLS if c.startswith("t1_")]
    assert not t1_ish, "a t1_ column was added to _CLOSE_COLS — say why, it changes the matrix"
    # And the guard the exclusion-by-name relies on: a t1_ column IS model-eligible today.
    frame = pd.DataFrame([{"t1_home_spread": -6.5, "label_x": 1.0, "game_id": 1}])
    assert "t1_home_spread" in bake.feature_columns(frame), (
        "this test's premise is stale — re-read why with_t1 must stay opt-in")


def test_the_serving_writer_is_the_caller_that_opts_in():
    """The serving read is the one caller that wants both kinds; the modelling callers must not."""
    src = Path(_REPO / "scripts/write_ncaaf_serving_store.py").read_text()
    assert "build_clv_staging(min_year=int(season), with_t1=True)" in src
    for modelling in ("quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_game.py",
                      "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_p2_1.py"):
        body = Path(_REPO / modelling).read_text()
        assert "with_t1=True" not in body, (
            f"{modelling} opted into the T-1 columns — that changes the training matrix")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The client renders a T-1 line with NO change (spec AC3), proven mechanically
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _strip_comments(src: str) -> str:
    """INC-38: a source scan that matches inside a COMMENT passes on the prose above deleted code."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


def test_the_market_panel_branches_on_status_not_on_which_snapshot_it_is():
    """AC3, as a MECHANICAL claim rather than an eyeball: a panel that branched on `source` would
    need a client change for the T-1 value, and this story's lane forbids one."""
    src = _strip_comments(_PANEL.read_text())
    assert "market.status" in src and "market.home_spread" in src, (
        "the scan is vacuous — it is not reading the panel it thinks it is")
    assert "market.source" not in src and ".as_of" not in src, (
        "the panel reads `source`/`as_of`, so a T-1-sourced line does NOT render without a client "
        "change — STOP and flag it to the PM rather than editing the P3.9 lane")


def test_two_payloads_differing_only_in_source_are_identical_where_the_client_reads():
    """The other half of the same claim, from the DATA side: whatever the panel reads, it reads the
    same bytes for a T-1 line as for a close one."""
    read_by_panel = ("status", "reason", "home_spread", "total",
                     "home_moneyline_implied_probability")
    same_numbers = {"t1_home_spread": CLOSE_LINE["close_home_spread"],
                    "t1_total": CLOSE_LINE["close_total"],
                    "t1_home_ml_american": CLOSE_LINE["close_home_ml_american"],
                    "t1_home_ml_prob": CLOSE_LINE["close_home_ml_prob"],
                    "t1_snapshot_ts": T1_TS}
    as_t1 = _market(same_numbers)
    as_close = _market(dict(CLOSE_LINE))
    assert as_t1["source"] != as_close["source"], "the two arms are not actually different sources"
    assert {k: as_t1[k] for k in read_by_panel} == {k: as_close[k] for k in read_by_panel}


def test_the_absent_reason_copy_falls_back_rather_than_rendering_a_blank():
    """The two NEW reasons have no entry in `MARKET_REASON_COPY`, and that is fine ONLY because the
    panel falls back to a sentence. Without the fallback a refused line would render as empty
    space — the stated-absence rule broken by a new value nobody added copy for."""
    copy_ts = _strip_comments((_REPO / "frontend/lib/ncaaf-copy.ts").read_text())
    assert "MARKET_REASON_FALLBACK" in copy_ts
    panel = _strip_comments(_PANEL.read_text())
    # ⚠️ NOT a bare identifier scan: `MARKET_REASON_FALLBACK` also appears on the IMPORT line, so
    # a grep for the name stays green with every USE deleted (the wired-≠-invoked class). Match the
    # fallback OPERATOR beside it.
    assert re.search(r"\|\|\s*MARKET_REASON_FALLBACK", panel), (
        "the panel indexes MARKET_REASON_COPY with no fallback — a reason it has no copy for would "
        "render as a blank")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The run log answers "did the T-1 leg actually fire?" (the P3.1 positive-control lesson)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_writer_counts_market_lines_per_source_not_just_in_total():
    """A run log saying "12 lines attached" cannot answer the only question this story's runtime
    gate asks — WHICH kind attached. Per key shape, per the P3.1 lesson."""
    import scripts.write_ncaaf_serving_store as writer
    slates = {"2026-08-29": {"games": [
        {"market": _market({**T1_LINE, **CLOSE_LINE})},
        {"market": _market(dict(CLOSE_LINE))},
        {"market": _market(None)},
        {"market": _market({**T1_LINE, "t1_snapshot_ts": "2026-08-30T02:00:00.000Z"})},
    ]}}
    assert writer._count_by(slates, "source") == {
        payloads.MARKET_SOURCE_CLOSE: 1, payloads.MARKET_SOURCE_T1: 1}
    assert writer._count_by(slates, "reason") == {
        payloads.MARKET_REASON_NOT_PRE_KICKOFF: 1, payloads.MARKET_REASON_NO_CAPTURE: 1}


def test_a_real_write_run_reports_which_line_it_attached(monkeypatch, tmp_path):
    """The counter is WIRED, not merely defined — a helper nothing calls is the NF-C0e class, and
    the whole point of these counts is that the operator's runtime gate can read them off the run
    log without opening a blob."""
    import scripts.write_ncaaf_serving_store as writer
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    row = _snapshot_row()
    monkeypatch.setattr(writer, "read_snapshots",
                        lambda season, source, *, local_root=None:
                        pd.DataFrame([row]) if source == gps.SNAPSHOT_SOURCE else pd.DataFrame())
    monkeypatch.setattr(writer, "read_market_lines",
                        lambda season: ({row["game_id"]: {**T1_LINE, **CLOSE_LINE}}, False))
    result = writer.write_serving_store(2026, dry_run=True, out_dir=str(tmp_path))
    assert result["market_lines_attached"] == 1
    assert result["market_lines_by_source"] == {payloads.MARKET_SOURCE_T1: 1}, (
        "the run log cannot answer WHICH line attached, which is the only question this story's "
        "runtime gate asks")
    assert result["market_reasons"] == {}


def test_the_generated_e2e_fixtures_still_clear_the_real_leakage_guard():
    """The market fixture is built by the SHIPPING `_market()`, so if the guard refused those rows
    the fixture would silently become an all-unavailable slate and the panel's available branch
    would stop being covered at all."""
    blob = json.loads(
        (_REPO / "frontend/e2e/fixtures/api/ncaaf-slate-2026-08-29-market.synthetic.json").read_text())
    available = [g["market"] for g in blob["games"] if g["market"]["status"] == "available"]
    assert len(available) == 3, f"the market-available branch lost its coverage ({len(available)})"
    for block in available:
        assert block["as_of"] == block["snapshot_ts"] is not None
        assert block["source"] in (payloads.MARKET_SOURCE_CLOSE, payloads.MARKET_SOURCE_T1)
