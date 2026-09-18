"""NF-WK-RC1 addendum (PM 2026-09-17) — the realized artifact's publish-time CONTRACT, and the
cumulative SEASON-TO-DATE artifact published beside the weekly one.

⭐ THE ANCHOR IS THE STORED WEEK 1, NOT A HAND-WRITTEN FIXTURE. `fixtures/nf_wk_rc1_realized_2026_
wk1_stored.json.gz` is the served `realized/2026/1/players.json` (06:43:50Z), re-encoded columnar;
the first clause proves it re-expands to the served bytes. A fixture the author wrote would only
restate the author's idea of what a week looks like (NF-C0e) — this one is what actually shipped.

⭐ ONE ISOLATING MUTATION PER CLAUSE (NF-D17). Every negative case starts from the real week, changes
exactly one property, and recounts the manifest from the mutated rows — so the ONLY clause that can
fire is the one under test. A mutation that also tripped the recount check would pass for the
wrong reason.

⭐ THE SCOPE IS THE PM's AND NOTHING WIDER: non-null per listed column, the n_players / n_teams
floors, and the stored-artifact anchor. No type or range validation — deliberately.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
import re
from pathlib import Path

import botocore.exceptions
import pytest

from app.backend.models import nfl_recap
from betting_ml.tests import _realized_capture as _capture
from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW
from quant_sports_intel_models.football.nfl.fantasy import run_realized_week as RUN

_REPO = Path(__file__).resolve().parents[2]
_FIXTURE = Path(__file__).parent / "fixtures" / "nf_wk_rc1_realized_2026_wk1_stored.json.gz"
_JOB = _REPO / "pipeline/jobs/sports_nfl_weekly_serving_job.py"

#: The five columns that are all-zero on week 1 — true zeros (rare events across 16 games), measured
#: by NF-WVR1 ⑭ and confirmed here. The contract must PASS them.
_TRUE_ZERO_COLUMNS = ("def_safeties", "fg_made_0_19", "fg_made_60_",
                      "rushing_2pt_conversions", "special_teams_tds")

#: Lowest players-per-game observed on any REG week in the lake, 2018–2026 wk1 (2023 wk17), measured
#: 2026-09-16 over 142 weeks. The floor must sit below it or it false-fires on a real week.
_LOWEST_MEASURED_PLAYERS_PER_GAME = 63.25


def _stored() -> dict:
    return json.loads(gzip.decompress(_FIXTURE.read_bytes()))


def _week1() -> tuple[dict, list[dict]]:
    fx = _stored()
    players = [dict(zip(fx["columns"], r)) for r in fx["rows"]]
    return copy.deepcopy(fx["manifest"]), players


def _recount(manifest: dict, players: list[dict]) -> dict:
    """The manifest a correct `build` would have written for these rows — so a mutation of the rows
    trips only the clause it targets, never the manifest-vs-rows recount."""
    m = dict(manifest)
    m["n_players"] = len(players)
    m["n_teams"] = len({p["team"] for p in players if p.get("team")})
    m["realized_games"] = len({p["game_id"] for p in players if p.get("game_id")})
    return m


def _hashed(manifest: dict, players: list[dict]) -> dict:
    return {**manifest, "content_sha256": RW.content_hash(players)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — THE ANCHOR IS THE SERVED ARTIFACT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_fixture_re_expands_to_the_served_week_1_bytes():
    """⭐ Otherwise the 'stored artifact' anchor is just another hand-built fixture."""
    fx = _stored()
    body = json.dumps({"players": [dict(zip(fx["columns"], r)) for r in fx["rows"]],
                       "generated_at": fx["generated_at"]}, default=str).encode()
    assert hashlib.sha256(body).hexdigest() == fx["provenance"]["players_json_sha256"]
    assert fx["provenance"]["source"].endswith("fantasy/nfl/realized/2026/1/players.json")
    assert fx["manifest"]["n_players"] == len(fx["rows"]) == 1118


def test_the_stored_week_1_passes_the_contract():
    man, players = _week1()
    rep = RW.contract_report(man, players)
    assert rep["ok"], rep["violations"]
    assert rep["emptyColumns"] == []
    # Every REG week in the lake carries exactly one such vendor row — reported, never gated.
    assert rep["rowsWithoutPlayerId"] == 1


def test_true_zero_columns_pass_because_the_check_counts_values_not_nonzero_values():
    """⛔ A future reader must not 'fix' these: rare events, legitimately all-zero on week 1."""
    man, players = _week1()
    for c in _TRUE_ZERO_COLUMNS:
        assert c in man["columns"]
        assert all(p[c] == 0 for p in players), c
    assert RW.contract_report(man, players)["ok"]


def test_the_floors_are_derived_from_the_measured_population():
    man, _ = _week1()
    assert RW.TEAMS_PER_GAME == 2
    assert RW.MIN_PLAYERS_PER_GAME < _LOWEST_MEASURED_PLAYERS_PER_GAME
    assert man["n_players"] / man["realized_games"] > RW.MIN_PLAYERS_PER_GAME


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — EACH CLAUSE, ISOLATED
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _only(rep: dict, needle: str) -> None:
    assert not rep["ok"]
    assert len(rep["violations"]) == 1, rep["violations"]
    assert needle in rep["violations"][0], rep["violations"]


def test_a_listed_column_with_no_value_on_any_row_is_refused():
    man, players = _week1()
    for p in players:
        p["receiving_yards"] = None
    _only(RW.contract_report(man, players), "'receiving_yards'")


def test_a_nan_filled_column_is_not_a_populated_one():
    """⛔ The lake read goes through pandas: an unpopulated NUMERIC column arrives as NaN."""
    man, players = _week1()
    for p in players:
        p["passing_yards"] = math.nan
    _only(RW.contract_report(man, players), "'passing_yards'")


def test_a_listed_column_missing_from_the_rows_entirely_is_refused():
    man, players = _week1()
    for p in players:
        p.pop("targets")
    _only(RW.contract_report(man, players), "'targets'")


def test_a_game_missing_one_side_breaks_the_two_teams_per_game_identity():
    man, players = _week1()
    players = [p for p in players if p["team"] != "SEA"]
    rep = RW.contract_report(_recount(man, players), players)
    assert len(players) >= RW.MIN_PLAYERS_PER_GAME * 16  # the row floor alone would still pass
    _only(rep, "teams across 16 games")


def test_a_gross_row_loss_breaks_the_players_per_game_floor():
    man, players = _week1()
    kept, seen = [], {}
    for p in players:  # two rows per team per game: every team and game survives
        k = (p["game_id"], p["team"])
        if seen.get(k, 0) < 2:
            kept.append(p)
            seen[k] = seen.get(k, 0) + 1
    rep = RW.contract_report(_recount(man, kept), kept)
    _only(rep, "below the floor")


def test_a_manifest_that_disagrees_with_its_rows_is_refused():
    man, players = _week1()
    man["n_players"] += 1
    _only(RW.contract_report(man, players), "manifest n_players")


def test_a_manifest_listing_no_columns_is_refused():
    man, players = _week1()
    man["columns"] = []
    _only(RW.contract_report(man, players), "lists no columns")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — ENFORCED AT PUBLISH, BEFORE ANY S3 CALL
# ══════════════════════════════════════════════════════════════════════════════════════════════

class _FakeS3:
    """An in-memory bucket with the three calls the publisher and runner make."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []

    def get_object(self, Bucket, Key):  # noqa: N803
        self.calls.append(("get", Key))
        if Key not in self.objects:
            raise botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchKey"}}, "GetObject")

        class _Body:
            def __init__(self, b):
                self._b = b

            def read(self):
                return self._b
        return {"Body": _Body(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        self.calls.append(("put", Key))
        self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

    def get_paginator(self, _):
        outer = self

        class _P:
            def paginate(self, Bucket, Prefix):  # noqa: N803
                return [{"Contents": [{"Key": k} for k in sorted(outer.objects)
                                      if k.startswith(Prefix)]}]
        return _P()


def test_publish_refuses_a_violating_build_before_touching_s3():
    man, players = _week1()
    for p in players:
        p["rushing_yards"] = None
    s3 = _FakeS3()
    with pytest.raises(RW.RealizedContractError, match="rushing_yards"):
        RW.publish({"manifest": _hashed(man, players), "players": players},
                   s3=s3, bucket="b")
    assert s3.calls == []


def test_publish_accepts_the_stored_week_and_writes_both_keys():
    man, players = _week1()
    s3 = _FakeS3()
    out = RW.publish({"manifest": _hashed(man, players), "players": players}, s3=s3, bucket="b")
    assert out["action"] == "create"
    assert {k for op, k in s3.calls if op == "put"} == {
        "fantasy/nfl/realized/2026/1/players.json",
        "fantasy/nfl/realized/2026/1/manifest.json",
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4 — THE SEASON-TO-DATE ARTIFACT
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: ⭐ ONE OWNER, shared with `test_nf_wvr1_fact_columns.py` — ruling ① put BOTH suites' fixtures one
#: column behind the contract at once, and a copy of the adaptation in each file is a second owner of
#: one rule (the repo's INC-30/36/38 shape). Read `_realized_capture`'s docstrings before trusting
#: what a clause built on the adapted capture proves.
_columns_the_capture_predates = _capture.columns_the_capture_predates
_bring_up_to_contract = _capture.bring_up_to_contract


def _served_week(week: int, *, completeness: str = "final", hashed: bool = True):
    man, players = _week1()
    for p in players:
        p["week"] = week
        p["game_id"] = p["game_id"].replace("_01_", f"_{week:02d}_")
    man, players = _bring_up_to_contract(man, players)
    man = {**man, "week": week, "completeness": completeness}
    return (_hashed(man, players) if hashed else man), players


def test_the_authentic_capture_is_columns_behind_until_it_is_republished():
    """⭐ THE REAL OPERATIONAL CONSEQUENCE of widening the column contract, pinned on the UNTOUCHED
    capture rather than on an adapted one: a week published before a column existed cannot enter the
    season artifact, and it names itself rather than silently contributing short rows.

    This is the state every already-published 2026 week is in after NF-WK-ACC1 ruling ①, which is why
    the closeout lists a republish as an operator step. ⛔ If `_columns_the_capture_predates()` is
    empty the clause is INERT and says so — an assertion about a gap that no longer exists would be
    the vacuous pass, not a success.
    """
    missing = _columns_the_capture_predates()
    if not missing:
        pytest.skip("the committed capture already carries today's contract — nothing to exclude")
    man, players = _week1()
    man = {**man, "week": 1, "completeness": "final"}
    built = RW.build_season(2026, {1: (_hashed(man, players), players)})
    assert built["manifest"]["weeks"] == []
    [excluded] = built["manifest"]["excluded"]
    assert excluded["reason"] == "columns_behind"
    for column in missing:
        assert column in excluded["detail"], "the exclusion must NAME the columns it is behind on"


def test_the_season_artifact_is_the_concatenation_of_the_served_weeks():
    served = {1: _served_week(1), 2: _served_week(2)}
    built = RW.build_season(2026, served)
    man = built["manifest"]
    assert man["through_week"] == 2 and man["weeks"] == [1, 2] and man["excluded"] == []
    assert man["n_rows"] == len(built["rows"]) == 2 * 1118
    assert man["encoding"] == RW.SEASON_ENCODING
    assert RW.season_contract_report(built) == {"ok": True, "violations": []}
    # Re-expanding the columnar rows gives back each week's canonical rows, in week order.
    expanded = [dict(zip(built["columns"], r)) for r in built["rows"]]
    want = [{c: p.get(c) for c in built["columns"]}
            for w in (1, 2) for p in RW.canonical_rows(served[w][1])]
    assert expanded == want


def test_a_gap_ends_the_season_artifact_and_names_itself():
    """⛔ A season total that silently skipped a week reads as a quiet week for every player."""
    built = RW.build_season(2026, {1: _served_week(1), 3: _served_week(3)})
    man = built["manifest"]
    assert man["through_week"] == 1 and man["weeks"] == [1]
    assert man["excluded"] == [{"week": 3, "reason": "after_gap",
                                "detail": "week 2 has no served artifact"}]
    assert RW.season_defects(built) == man["excluded"]
    assert {r[built["columns"].index("week")] for r in built["rows"]} == {1}


def test_a_partial_week_is_a_routine_exclusion_but_what_follows_it_is_a_defect():
    served = {1: _served_week(1), 2: _served_week(2, completeness="partial"),
              3: _served_week(3)}
    built = RW.build_season(2026, served)
    assert built["manifest"]["through_week"] == 1
    assert [(e["week"], e["reason"]) for e in built["manifest"]["excluded"]] == [
        (2, "not_final"), (3, "after_gap")]
    assert [e["week"] for e in RW.season_defects(built)] == [3]


@pytest.mark.parametrize("mutate, reason", [
    (lambda m, p: ({**m, "content_sha256": None}, p), "unverifiable"),
    (lambda m, p: ({**m, "content_sha256": "0" * 64}, p), "hash_mismatch"),
    (lambda m, p: ({**m, "columns": m["columns"][1:]}, p), "columns_behind"),
])
def test_an_unusable_served_week_is_excluded_with_its_reason(mutate, reason):
    m, p = mutate(*_served_week(2))
    built = RW.build_season(2026, {1: _served_week(1), 2: (m, p)})
    assert built["manifest"]["through_week"] == 1
    assert built["manifest"]["excluded"][0]["reason"] == reason
    assert RW.season_defects(built)


def test_a_week_failing_the_contract_does_not_enter_the_season_total():
    m, p = _served_week(2)
    for row in p:
        row["receptions"] = None
    built = RW.build_season(2026, {1: _served_week(1), 2: (_hashed(m, p), p)})
    assert built["manifest"]["excluded"][0]["reason"] == "contract"


def test_no_qualifying_week_publishes_nothing():
    built = RW.build_season(2026, {1: _served_week(1, hashed=False)})
    assert built["manifest"]["through_week"] is None
    assert RW.season_publish_decision(built["manifest"], None)["action"] == "skip_empty"
    s3 = _FakeS3()
    RW.publish_season(built, s3=s3, bucket="b")
    assert not [c for c in s3.calls if c[0] == "put"]


def test_the_season_contract_catches_a_tampered_concatenation():
    built = RW.build_season(2026, {1: _served_week(1), 2: _served_week(2)})
    built["rows"].pop()
    rep = RW.season_contract_report(built)
    assert not rep["ok"]
    assert any("n_rows" in v for v in rep["violations"])
    s3 = _FakeS3()
    with pytest.raises(RW.RealizedContractError):
        RW.publish_season(built, s3=s3, bucket="b")
    assert s3.calls == []


def test_the_season_contract_catches_rows_from_a_week_the_manifest_does_not_list():
    built = RW.build_season(2026, {1: _served_week(1), 2: _served_week(2)})
    wk = built["columns"].index("week")
    for r in built["rows"]:
        if r[wk] == 2:
            r[wk] = 3
    assert any("carry weeks" in v for v in RW.season_contract_report(built)["violations"])


def _dec(through, fp="a", *, prior_through=None, prior_fp=None, published=True):
    man = {"through_week": through, "source_fingerprint": fp}
    prior = ({"through_week": prior_through, "source_fingerprint": prior_fp}
             if published else None)
    return RW.season_publish_decision(man, prior)


@pytest.mark.parametrize("args, kwargs, action, write, event", [
    ((None,), {"published": False}, "skip_empty", False, False),
    ((2,), {"published": False}, "create", True, False),
    ((2, "a"), {"prior_through": 2, "prior_fp": "a"}, "unchanged", False, False),
    ((3, "b"), {"prior_through": 2, "prior_fp": "a"}, "advance", True, False),
    ((2, "b"), {"prior_through": 2, "prior_fp": "a"}, "refresh", True, False),
    ((1, "b"), {"prior_through": 2, "prior_fp": "a"}, "refuse_regress", False, True),
])
def test_the_season_decision_table(args, kwargs, action, write, event):
    d = _dec(*args, **kwargs)
    assert (d["action"], d["servingWrite"], d["event"]) == (action, write, event)


def test_the_season_key_can_never_read_as_a_published_week():
    """⭐ Both week-listers count a week only under an all-digit directory; `season` is not one."""
    key = nfl_recap.realized_season_manifest_key(2026)
    assert key == "realized/2026/season/manifest.json"
    assert not key.split("/")[-2].isdigit()

    s3 = _FakeS3()
    for k in (f"fantasy/nfl/{nfl_recap.realized_manifest_key(2026, 1)}",
              f"fantasy/nfl/{key}",
              f"fantasy/nfl/{nfl_recap.realized_season_players_key(2026)}"):
        s3.objects[k] = b"{}"
    assert RUN._published_weeks(s3, "b", 2026) == {1}

    code = "\n".join(line for line in _JOB.read_text().splitlines()
                     if not line.lstrip().startswith("#"))
    assert re.search(r'parts\[-1\] == "manifest\.json" and parts\[-2\]\.isdigit\(\)', code), \
        "the freshness op's week-lister no longer requires an all-digit week directory"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5 — THE RUNNER'S SEASON STEP, END TO END OVER THE SERVED FILES
# ══════════════════════════════════════════════════════════════════════════════════════════════

class _Args:
    season = 2026
    s3_bucket = "b"


def _serve(s3: _FakeS3, week: int, **kw) -> None:
    man, players = _served_week(week, **kw)
    RW.publish({"manifest": man, "players": players}, s3=s3, bucket="b")


def test_the_runner_publishes_and_verifies_the_season_from_what_is_served():
    """⭐ Weeks go through the REAL weekly publish (JSON on the wire) and come back through the REAL
    loader — so the hash each week is verified against has survived the round trip."""
    s3 = _FakeS3()
    _serve(s3, 1)
    _serve(s3, 2)
    summary = {"errors": [], "events": []}
    report = RUN._season(_Args(), s3, False, summary)
    assert summary["errors"] == [], summary["errors"]
    assert (report["action"], report["through_week"], report["n_rows"]) == ("create", 2, 2236)

    body = json.loads(s3.objects["fantasy/nfl/realized/2026/season/players.json"])
    assert body["encoding"] == RW.SEASON_ENCODING and len(body["rows"]) == 2236

    again = RUN._season(_Args(), s3, False, {"errors": [], "events": []})
    assert again["action"] == "unchanged"


def test_the_runner_pages_when_a_served_week_cannot_enter_the_season_total():
    s3 = _FakeS3()
    _serve(s3, 1)
    _serve(s3, 3)
    summary = {"errors": [], "events": []}
    report = RUN._season(_Args(), s3, False, summary)
    assert report["through_week"] == 1
    assert [e["week"] for e in summary["errors"]] == ["season"]
    assert "after_gap" in summary["errors"][0]["error"]


def test_a_dry_run_reports_exclusions_without_paging():
    s3 = _FakeS3()
    _serve(s3, 1)
    _serve(s3, 3)
    summary = {"errors": [], "events": []}
    RUN._season(_Args(), s3, True, summary)
    assert summary["errors"] == []
    assert not [c for c in s3.calls if c[0] == "put" and "/season/" in c[1]]


def test_a_season_failure_is_recorded_rather_than_raised():
    class _Broken(_FakeS3):
        def get_paginator(self, _):
            raise RuntimeError("listing denied")

    summary = {"errors": [], "events": []}
    report = RUN._season(_Args(), _Broken(), False, summary)
    assert report["action"] == "error"
    assert summary["errors"] == [{"week": "season", "error": "RuntimeError: listing denied"}]


def test_the_op_labels_season_entries_rather_than_rendering_wkseason():
    code = _JOB.read_text()
    assert "wk{e['week']}" not in code
    assert re.search(r'"season-to-date" if entry\.get\("week"\) == "season"', code)
