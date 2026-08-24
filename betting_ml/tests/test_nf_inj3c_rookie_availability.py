"""NF-INJ3c — the ROOKIE-PATH availability routing, and the boundaries it must not cross.

THE DEFECT. Both model-driven availability discounts — the formal RES/PUP/NFI/SUS status cap and
the NF-D11 return-from-absence prior — lived inside `project_veterans`. `project_rookies` ran
neither, so a rookie placed on IR was projected as though healthy by every path on the board.
Measured over the 2016–2025 builds: **50 of 60** flagged rookies projected ABOVE the incumbent cap's
own ceiling, against **0 of 496** veterans. The 53-man cutdown (2026-08-30) puts a wave of exactly
those rows on the board.

⚠️⚠️ WHAT THESE CLAUSES CAN AND CANNOT DO. Every clause here is a fixture or a source inspection,
and the defect this story closes was INVISIBLE to fixtures for the whole life of the mechanism — a
synthetic frame does not know which production function built it (NF-C0e: wired ≠ invoked). The
acceptance evidence is therefore MEASURED, by `run_nf_inj3c_rookie_availability.py`, on the real
boards / the real roster feed / the real rookie classes, and recorded in
`ablation_results/nf_inj3c_rookie_availability.json`. These clauses exist to stop the wiring
REGRESSING, not to establish that it works. Both are needed and neither substitutes for the other.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

_FANTASY = Path(__file__).resolve().parents[2] / "quant_sports_intel_models/football/nfl/fantasy"
_SRC = (_FANTASY / "season_projection.py").read_text()


def _chain_body() -> str:
    return _SRC.split("def apply_availability_chain(", 1)[1].split("\ndef ", 1)[0]


def _rookie_body() -> str:
    return _SRC.split("def project_rookies(", 1)[1].split("\ndef ", 1)[0]


def _veteran_body() -> str:
    return _SRC.split("def project_veterans(", 1)[1].split("\ndef ", 1)[0]


def _strip_comments(body: str) -> str:
    """⚠️ INC-38: a source-inspection clause a COMMENT can satisfy is not a clause. Every clause
    below that reads for a call reads COMMENT-STRIPPED source, because this module's comments name
    the very symbols and boundaries being asserted — the explanatory prose would satisfy a naive
    substring scan with the code deleted."""
    return "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))


def _frame(*, games, status=None, n=None, **extra) -> pd.DataFrame:
    """A projected frame with a physically coherent line, so a rescale is observable."""
    games = np.atleast_1d(np.asarray(games, dtype=float))
    n = n or len(games)
    df = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "player_name": [f"P{i}" for i in range(n)],
        "position": ["RB"] * n,
        "proj_games": games,
        "proj_pass_att": np.zeros(n), "proj_pass_cmp": np.zeros(n), "proj_pass_yds": np.zeros(n),
        "proj_pass_td": np.zeros(n), "proj_pass_int": np.zeros(n),
        "proj_rush_att": np.full(n, 200.0), "proj_rush_yds": np.full(n, 900.0),
        "proj_rush_td": np.full(n, 7.0),
        "proj_targets": np.full(n, 60.0), "proj_rec": np.full(n, 45.0),
        "proj_rec_yds": np.full(n, 380.0), "proj_rec_td": np.full(n, 2.0),
        "proj_fumbles_lost": np.full(n, 1.5), "proj_two_pt": np.zeros(n),
    })
    if status is not None:
        df["proj_status"] = list(np.atleast_1d(status))
    for k, v in extra.items():
        df[k] = v
    return SP.score_line(df, prefix="proj_")


# ══ AC-1 — THE FORMAL CAP REACHES ROOKIES, ON THE INCUMBENT CONSTANTS ════════════════════════════

@pytest.mark.parametrize("status", ["RES", "PUP", "NFI", "SUS"])
def test_a_flagged_rookie_is_capped_by_the_formal_status_path(status):
    """⭐⭐ THE DEFECT, through the REAL `project_rookies`. Before this story the answer was "not at
    all, for any status" — the function had no way to see a roster status and no formal step to run
    it through. Driven end to end (synthetic class + real curve fit + a roster-status frame) rather
    than by calling the chain directly, because "the chain caps correctly" and "the rookie frame
    reaches the chain" are different claims and only the second one was ever broken."""
    incoming, curve = _synthetic_rookie_class()
    status_frame = pd.DataFrame({"player_id": ["R0"], "proj_status": [status]})
    before = SP.project_rookies(incoming, curve, 2026).set_index("player_id")
    after = SP.project_rookies(incoming, curve, 2026,
                               roster_status=status_frame).set_index("player_id")
    cap = SP._INJURY_STATUS_GAMES_CAP[status]
    b = SP._INJURY_OVERRIDE_BLEND
    g0 = float(before.loc["R0", "proj_games"])
    assert g0 > cap, "the fixture's rookie already projects below the cap — nothing to observe"
    assert float(after.loc["R0", "proj_games"]) == pytest.approx((1 - b) * g0 + b * cap), (
        f"a rookie flagged {status} was not moved to the incumbent blend of his status level")
    assert bool(after.loc["R0", SP.FORMAL_APPLIED_COL]) is True
    # ⚠️ and NOBODY ELSE moves — the discount is a per-row statement, not a class-wide one.
    others = [i for i in before.index if i != "R0"]
    assert np.array_equal(before.loc[others, "proj_fp_ppr"].to_numpy(),
                          after.loc[others, "proj_fp_ppr"].to_numpy()), (
        "an unflagged rookie moved")


def _synthetic_rookie_class():
    """A minimal incoming class + a curve fitted on synthetic history, kept local so this file owns
    its own fixture. The history's shape (`rookie_fp_ppr`, `games`, the raw stat columns) is what
    `fit_rookie_slot_curves` actually consumes."""
    rng = np.random.default_rng(0)
    rows = []
    for pos, base_yds, base_fp in [("RB", 900, 170), ("WR", 850, 150), ("TE", 450, 90)]:
        for _ in range(40):
            overall = int(rng.integers(1, 255))
            scale = max(0.05, (260 - overall) / 260.0)
            rows.append({
                "position_group": pos, "draft_overall": overall,
                "games": min(17, 6 + scale * 11),
                "rookie_fp_ppr": max(2.0, base_fp * scale * rng.uniform(0.6, 1.4)),
                "pass_att": 0.0, "pass_cmp": 0.0, "pass_yds": 0.0, "pass_td": 0.0, "pass_int": 0.0,
                "rush_att": 200 * scale if pos == "RB" else 0.0,
                "rush_yds": base_yds * scale if pos == "RB" else 0.0,
                "rush_td": 7 * scale if pos == "RB" else 0.0,
                "targets": 90 * scale, "rec": 60 * scale,
                "rec_yds": (base_yds if pos in ("WR", "TE") else 250) * scale,
                "rec_td": 5 * scale,
            })
    curve = SP.fit_rookie_slot_curves(pd.DataFrame(rows))
    incoming = pd.DataFrame([
        {"gsis_id": f"R{i}", "player_name": f"Rookie{i}", "position_group": "RB",
         "nfl_position": "RB", "draft_overall": ov, "projected_nfl_z": 0.5}
        for i, ov in enumerate([6, 24, 60])])
    return incoming, curve


def test_the_rookie_frame_routes_the_INCUMBENT_CONSTANTS_never_the_certified_veteran_hurdle():
    """⛔⛔ AC-1's BINDING BOUNDARY. NF-INJ3b certified `hurdle_transfer` on the VETERAN population
    and EXCLUDED rookies by registration (60 of them). Its covariates — `prior_games`,
    `log1p_prior_fp`, `weeks_since_last_game`, `onset_carryover` — are prior-NFL-career quantities a
    rookie does not have and cannot have. Routing the rookie frame through
    `injury_games_serving.served_injury_games` would serve a fitted object on a population it never
    scored, which is MH2.1's "serve the object that was VALIDATED" facing the population axis.

    So the rookie frame calls `injury_availability_games` DIRECTLY. If a future edit points it at
    the policy router, the flip would silently extend an uncertified model to 81 board rows, and
    nothing else in this repo would notice."""
    body = _strip_comments(_rookie_body())
    assert "injury_availability_games(" in body, (
        "project_rookies no longer calls the incumbent constants cap — either the routing is gone "
        "or it has been pointed at something else")
    assert "injury_games_serving" not in body and "served_injury_games" not in body, (
        "project_rookies reaches the NF-INJ3b policy router. That arm was certified on VETERANS "
        "with rookies EXCLUDED by registration, and its covariates are veteran-history quantities "
        "a rookie does not have — serving it here is an uncertified re-derivation (MH2.1)")


def test_the_boundary_is_written_where_a_future_editor_will_read_it():
    """A boundary that lives only in a closeout is a boundary nobody enforces. AC-1 requires it in
    the code."""
    body = _rookie_body()
    assert "NF-INJ3b" in body and "MH2.1" in body, (
        "the rookie frame does not record WHY it may not use the certified veteran hurdle — the "
        "next editor sees a constants call beside a certified model and 'upgrades' it")


# ══ AC-2 — NF-D11 IS NOT-APPLICABLE-BY-CONSTRUCTION ══════════════════════════════════════════════

def test_the_rookie_frame_passes_NO_absence_prior():
    """⛔ AC-2, ruled on MECHANISM before any measurement. NF-D11 fires on `seasons_missed >= 1` —
    a player who missed an ENTIRE prior NFL season while carrying production in Y−3..Y−2 — and its
    design matrix is `(prior_games, log_prior_fp, seasons_missed, is_qb)`, three of whose four terms
    are prior-NFL-career quantities. A rookie has no prior NFL season, so `seasons_missed` is not
    merely missing but UNDEFINED, and the fit population (431 historical returners) contains no row
    like him. Forcing it would transfer the FEATURE where only the FINDING transfers."""
    body = _strip_comments(_rookie_body())
    assert "absence_prior=None" in body, (
        "project_rookies passes an absence prior — NF-D11 conditions on a prior-NFL-season absence "
        "a rookie cannot have; the ruling is NOT-APPLICABLE-BY-CONSTRUCTION, not 'apply it anyway'")
    assert "absence_prior_blend=0.0" in body


def test_the_ruling_names_the_mechanism_not_just_the_conclusion():
    """A recorded null whose REASON is absent cannot be re-read later. AC-2 asks for the reasoning."""
    body = _rookie_body()
    assert "NOT-APPLICABLE-BY-CONSTRUCTION" in body, "the ruling's verdict is not recorded"
    assert "A rookie has no prior NFL season" in body, (
        "the NF-D11 ruling does not say WHY the mechanism cannot act — a future reader cannot tell "
        "'we measured it and it did nothing' from 'it cannot act here', and only the second one "
        "means a re-test would be pointless")
    assert "seasons_missed" in body, "the ruling does not name the quantity the prior turns on"


def test_the_chain_self_gates_on_seasons_missed_so_the_ruling_holds_at_both_ends():
    """Belt and braces: even if a caller passed a prior by mistake, a frame with no `seasons_missed`
    column is left COMPLETELY alone. The ruling is enforced by the caller AND by the callee.

    ⚠️ ASSERTED ON THE WHOLE FRAME, NOT ON `proj_games` — and that is what makes the clause bite.
    `absence_return_games` gates on the same column and would return the games unchanged anyway, so
    a games-only assertion passes with the chain's own gate DELETED (measured: it did). The gate is
    load-bearing for a different reason: it also skips the RESCALE, and a rescale is not a no-op
    even at scale 1.0 — it recomputes `proj_fumbles_lost` from touches and re-scores, so a frame
    whose fumble term did not exactly equal `round(touches*0.006, 2)` would silently move."""
    prior = SP.AbsenceReturnPrior(family="ratio", levels={"ratio": 0.4},
                                  sds={"all": 5.4}, n_fit=100)
    df = _frame(games=[12.0])
    df["proj_fumbles_lost"] = 1.5   # deliberately NOT the value a rescale would recompute
    df = SP.score_line(df, prefix="proj_")
    got = SP.apply_availability_chain(df.copy(), absence_prior=prior, absence_prior_blend=1.0)
    assert got["proj_games"].iloc[0] == pytest.approx(12.0), (
        "the chain applied the NF-D11 prior to a frame that carries no `seasons_missed` at all")
    for col in ("proj_fumbles_lost", "proj_fp_ppr", *SP.AVAILABILITY_LINE_COLS):
        assert got[col].iloc[0] == df[col].iloc[0], (
            f"{col} moved on a frame the NF-D11 prior cannot act on — the chain ran a rescale it "
            f"should have skipped")


# ══ ONE OWNER — the "one logical thing, many owners" cure ════════════════════════════════════════

def test_both_projection_frames_reach_the_SAME_availability_step():
    """⭐ The repo's most-repeated defect class (INC-30 crontab, INC-36 deploy lock, INC-38 the
    per-caller flag): one logical thing with two implementations drifts, and the drift is silent.
    Copy-pasting the caps into `project_rookies` would have closed the gap and re-opened it on the
    next edit to either copy."""
    for name, body in (("project_veterans", _veteran_body()), ("project_rookies", _rookie_body())):
        assert "apply_availability_chain(" in _strip_comments(body), (
            f"{name} does not call the shared availability step — the two populations are back on "
            f"separate copies of the caps")


def test_the_games_rescale_has_exactly_one_owner():
    """The availability rescale used to be typed out four times (three veteran steps + one rookie).
    A stat column added to one copy and forgotten in another is the whole failure mode.

    ⚠️ KEYED ON `df["proj_games"] = `, NOT on the column list. The mover-opportunity and
    environment-tilt steps also rescale the line inside `project_veterans` and are deliberately NOT
    part of this owner: they are LEVEL steps, they never touch games, and the env one scales a
    DIFFERENT column set on purpose (`proj_pass_int` is excluded — a better environment lifts
    production, not interceptions). Writing the clause against the column list conflated them; the
    property that actually belongs to this story is "only the chain assigns `proj_games`"."""
    # ⚠️ Each frame legitimately ESTABLISHES `proj_games` once (from `expected_games` / the slot
    #    curve). What it may not do is RE-assign it, which is what a second rescale looks like.
    for name, body, allowed in (("project_veterans", _veteran_body(), 1),
                                ("project_rookies", _rookie_body(), 0)):
        found = [ln.strip() for ln in _strip_comments(body).splitlines()
                 if re.search(r'df\["proj_games"\]\s*=', ln)]
        assert len(found) <= allowed, (
            f"{name} assigns proj_games {len(found)} time(s), at most {allowed} of which is the "
            f"establishing one ({found}) — the availability rescale is back to having two owners, "
            f"which is how the two populations drifted apart in the first place")
    owner = _SRC.split("def rescale_line_to_games(", 1)[1].split("\ndef ", 1)[0]
    assert re.search(r'df\["proj_games"\]\s*=', owner), (
        "`rescale_line_to_games` no longer assigns proj_games — the owner is now nobody")
    assert "rescale_line_to_games(" in _strip_comments(_chain_body()), (
        "the shared chain no longer calls the rescale owner")
    assert set(SP.AVAILABILITY_LINE_COLS) < set(SP.RAW_STAT_COLS), (
        "the rescaled columns are not a subset of the emitted raw stat line")


def test_the_scored_line_moves_with_games_and_the_fumble_rounding_is_the_only_gap():
    """⭐ A games discount that left the points alone would show a healthy fantasy total beside a
    shelved player's game count — the NF-INJ1 coherence class.

    ⚠️ THE VOLUME COLUMNS SCALE EXACTLY; THE SCORED POINT DOES NOT, and the difference is a
    MEASUREMENT rather than a tolerance picked to make a test pass. `proj_fumbles_lost` is
    recomputed from touches and ROUNDED to 2dp on both sides at −2/fumble, so
    `fp_after − s·fp_before = −2(ε_after − s·ε_before)` with each |ε| ≤ 0.005 ⇒ **|Δfp| ≤ 0.02
    points for any s ∈ [0,1]**, derived. Asserting the fp RATIO at 1e-6 instead reported a
    coherence failure on 9 of 10 real seasons."""
    df = _frame(games=[14.0], status=["RES"])
    before = df.copy()
    after = SP.apply_availability_chain(
        df.copy(), formal_games=lambda f: SP.injury_availability_games(f))
    s = after["proj_games"].iloc[0] / before["proj_games"].iloc[0]
    assert s < 1.0, "the fixture does not exercise a cap at all"
    for col in SP.AVAILABILITY_LINE_COLS:
        assert after[col].iloc[0] == pytest.approx(before[col].iloc[0] * s, rel=1e-12, abs=1e-9), (
            f"{col} did not follow the games discount exactly")
    dev = abs(after["proj_fp_ppr"].iloc[0] - before["proj_fp_ppr"].iloc[0] * s)
    assert dev <= 0.02 + 1e-9, (
        f"the scored point moved by {dev:.4f} more than the derived fumble-rounding bound of 0.02 "
        f"— the gap is no longer explained by rounding")


# ══ THE REFACTOR IS BYTE-IDENTICAL FOR VETERANS ══════════════════════════════════════════════════

def _reference_three_blocks(df, *, formal_games, absence_prior, absence_prior_blend,
                            reported_absence_rows, reported_absence_log):
    """The PRE-NF-INJ3c veteran implementation, transcribed verbatim from the three inline blocks
    `project_veterans` used to carry. ⚠️ This is deliberately a SECOND implementation and would
    normally be the defect (the NF-C0e "a self-validating check that owns its own copy of the
    scored logic"). Here it is the point: the claim under test is "the extraction changed nothing",
    and that claim can only be checked against what the code USED to be."""
    _COLS = ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
             "proj_rush_att", "proj_rush_yds", "proj_rush_td",
             "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td")

    def _rescale(df, new_games):
        old_games = df["proj_games"].to_numpy()
        sc = np.where(old_games > 1e-6, new_games / np.clip(old_games, 1e-6, None), 1.0)
        for col in _COLS:
            df[col] = df[col].to_numpy() * sc
        df["proj_games"] = new_games
        df["proj_pass_cmp"] = np.minimum(df["proj_pass_cmp"], df["proj_pass_att"])
        df["proj_rec"] = np.minimum(df["proj_rec"], df["proj_targets"])
        df["proj_fumbles_lost"] = np.round(
            (df["proj_rush_att"].to_numpy() + df["proj_rec"].to_numpy()) * 0.006, 2)
        return SP.score_line(df, prefix="proj_")

    if formal_games is not None:
        new_games = formal_games(df)
        old_games = df["proj_games"].to_numpy()
        df[SP.FORMAL_APPLIED_COL] = new_games < old_games - 1e-9
        df = _rescale(df, new_games)
    if absence_prior_blend > 0 and absence_prior is not None and "seasons_missed" in df.columns:
        df = _rescale(df, SP.absence_return_games(df, absence_prior, blend=absence_prior_blend))
    if reported_absence_rows:
        new_games, dec = SP.reported_absence_games(df, reported_absence_rows)
        if reported_absence_log is not None:
            reported_absence_log.extend(dec)
        df = _rescale(df, new_games)
        applied = [d for d in dec if d.get("applied")]
        if applied:
            for c in SP.REPORTED_ABSENCE_COLS:
                if c not in df.columns:
                    df[c] = np.nan
            by_id = {r.player_id: r for r in reported_absence_rows}
            for d in applied:
                row = by_id[d["player_id"]]
                i = df.index[d["row_index"]]
                df.loc[i, "reported_absence_source_url"] = row.source_url
                df.loc[i, "reported_absence_entered_at"] = row.entered_at.isoformat()
                df.loc[i, "reported_absence_games_missed"] = float(row.expected_games_missed)
    return df


def _override_row(pid="p2", miss=6):
    from quant_sports_intel_models.football.nfl.fantasy import reported_absence_overrides as RAO
    import datetime as _dt
    return RAO.OverrideRow(
        player_id=pid, player_name="P2", expected_games_missed=miss,
        source_url="https://example.test/report", entered_by="fixture",
        entered_at=_dt.date(2026, 8, 20),
        review_by=_dt.date(2026, 12, 31), note="fixture")


def test_the_extraction_reproduces_the_old_three_blocks_BIT_FOR_BIT():
    """⭐⭐ THE REFACTOR'S OWN GATE. This story is a rookie fix; a veteran row must not move by a
    single float. The frame below exercises ALL THREE steps at once — a formally-flagged row, a
    returner, and a row carrying an operator override — because a chain is exactly where an
    ordering change hides.

    ⚠️ NON-VACUITY IS ASSERTED FIRST: if the fixture did not actually move any games, the equality
    would hold trivially and this clause would pass on nothing (NF1.7 (a))."""
    prior = SP.AbsenceReturnPrior(family="ratio", levels={"ratio": 0.4},
                                  sds={"all": 5.4}, n_fit=100)
    base = _frame(games=[14.0, 13.0, 12.5, 11.0],
                  status=["RES", None, None, "SUS"],
                  seasons_missed=[0, 1, 0, 0],
                  prior_best_fp=[100.0, 140.0, 30.0, 80.0])
    # ⭐ TWO overrides, and the second one MUST be REFUSED: `p0` is the RES-flagged row, so the
    #    formal step moved him and PM ruling 2b's disjointness ignores his override. A fixture with
    #    only an APPLIED row cannot tell "stamp what was applied" from "stamp the whole file" — the
    #    two implementations agree on it, and the clause would pass on nothing.
    rows = [_override_row("p2", 6), _override_row("p0", 4)]

    def _formal(f):
        return SP.injury_availability_games(f)

    log_a, log_b = [], []
    got = SP.apply_availability_chain(
        base.copy(), formal_games=_formal, absence_prior=prior, absence_prior_blend=1.0,
        reported_absence_rows=rows, reported_absence_log=log_a)
    want = _reference_three_blocks(
        base.copy(), formal_games=_formal, absence_prior=prior, absence_prior_blend=1.0,
        reported_absence_rows=rows, reported_absence_log=log_b)

    moved = np.abs(got["proj_games"].to_numpy() - base["proj_games"].to_numpy()) > 1e-9
    assert moved.sum() >= 3, (
        f"the fixture exercises only {int(moved.sum())} of the three steps — an equality proved on "
        f"a frame nothing moved is proved on nothing")
    for col in sorted(set(want.columns) & set(got.columns)):
        a, b = got[col], want[col]
        if pd.api.types.is_numeric_dtype(b):
            assert np.array_equal(a.to_numpy(), b.to_numpy(), equal_nan=True), (
                f"{col} differs between the extracted chain and the pre-refactor implementation")
        else:
            assert a.astype(str).tolist() == b.astype(str).tolist(), f"{col} differs"
    assert log_a == log_b, "the decision log differs between the two implementations"
    refused = [d for d in log_a if not d.get("applied")]
    assert refused, (
        "the fixture produced no REFUSED override — the provenance clause then cannot distinguish "
        "'stamp what was applied' from 'stamp every row in the file'")
    assert pd.isna(got.loc[0, "reported_absence_source_url"]), (
        "a row whose override was REFUSED by the disjointness rule was stamped with provenance")
    assert sorted(got.columns) == sorted(want.columns), "the emitted column set changed"


def test_a_frame_with_no_roster_status_is_untouched_by_the_formal_step():
    """The pre-NF-INJ3c behaviour for a caller with no roster feed — byte-identical, and the honest
    state rather than a silently-assumed-healthy one."""
    df = _frame(games=[9.0])
    out = SP.apply_availability_chain(df.copy(), formal_games=None)
    assert out["proj_games"].iloc[0] == 9.0
    assert SP.FORMAL_APPLIED_COL not in out.columns, (
        "a frame that ran no formal step carries a formal-discount flag — an absent column is the "
        "truthful reading (`reported_absence_games` treats absent as False)")


# ══ THE CALLER WIRING — declared is not invoked ══════════════════════════════════════════════════

def test_build_projection_hands_the_rookie_frame_its_roster_status():
    """⭐ NF-C0e: the routing exists and is never invoked is the same defect wearing a hat. Without
    `roster_status` the rookie frame carries no `proj_status` and the formal step is structurally
    unreachable — which is precisely the state this story found."""
    run = (_FANTASY / "run_season_projection.py").read_text()
    call = run.split("rks = (project_rookies(", 1)[1].split("\n           if not incoming.empty", 1)[0]
    assert "roster_status=" in call, (
        "build_projection does not pass the forward roster status to project_rookies — the rookie "
        "frame has no proj_status and the formal cap can never fire")
    body = _strip_comments(run.split("def build_projection(", 1)[1].split("\ndef ", 1)[0])
    assert body.index("_rk_status = load_forward_roster_status(") < body.index("rks = (project_rookies("), (
        "the roster status is loaded AFTER the rookie frame is built — it can then only feed the "
        "detector, which is exactly the pre-NF-INJ3c arrangement")


def test_the_rookie_status_join_normalises_BOTH_ends():
    """NF-C9 shipped a join that normalised one side and trusted the other; a padded feed id then
    read as "this player is not on the board" rather than as a join failure, and it cost Josh Jacobs
    and DK Metcalf a live board. This join drives a CAP now, so a silent miss is a healthy-looking
    projection for a shelved player."""
    body = _strip_comments(_rookie_body())
    assert body.count("normalize_player_id") >= 2, (
        "the rookie roster-status join does not normalise both ends of the key")


@pytest.mark.parametrize("pid", ["  00-0039918", "00-0039918  ", "00-0039918"])
def test_a_padded_roster_id_still_reaches_the_rookie_it_names(pid):
    """The behavioural half of the clause above."""
    from quant_sports_intel_models.football.nfl.fantasy import reported_absence_overrides as RAO
    assert RAO.normalize_player_id(pid) == "00-0039918"


# ══ THE METER — the live instrument this story is measured by ════════════════════════════════════

def test_the_detector_reads_zero_once_a_flagged_rookie_is_actually_discounted():
    """The NF-INJ-NEWS-1 meter is this story's acceptance instrument. A rookie whose formal cap
    fired must stop being counted; one whose cap did NOT fire must still be counted, or the meter
    would go quiet for the wrong reason."""
    from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as R
    discounted = pd.DataFrame({
        "player_id": ["r1"], "player_name": ["RookieOnIR"], "position": ["WR"],
        "proj_status": ["RES"], "proj_games": [4.6], "is_rookie": [True],
        SP.FORMAL_APPLIED_COL: [True]})
    assert R._warn_formal_tag_without_discount(discounted) == 0
    not_discounted = discounted.assign(**{SP.FORMAL_APPLIED_COL: [False], "proj_games": [13.6]})
    assert R._warn_formal_tag_without_discount(not_discounted) == 1, (
        "the meter stopped counting a rookie who received NO discount — it would then read 0 on "
        "exactly the board state this story exists to make visible")


# ══ THE MEASURED EVIDENCE IS RECORDED, AND ITS ACTIVITY IS STATED ════════════════════════════════

_ART = _FANTASY / "ablation_results/nf_inj3c_rookie_availability.json"


def test_the_measured_verification_is_committed_and_every_leg_passed():
    """⭐ These fixtures cannot establish that the fix works on the real board; the runner can, and
    its output is the acceptance evidence. Pinned here so a later edit cannot quietly drop it."""
    import json
    rep = json.loads(_ART.read_text())
    assert rep["leg1_reproduction"]["reproduces"], (
        "the reproduction pin no longer reproduces NF-INJ3's recorded 50/60 — the with-fix leg is "
        "then measured against an unknown population")
    assert rep["leg2_with_fix_same_rows"]["passes"]
    assert rep["leg3_wiring_end_to_end"]["passes"]
    assert rep["leg4_meter_rookie_half"]["passes"]
    assert rep["leg2_with_fix_same_rows"]["unflagged_rows_moved"] == 0, (
        "a row carrying no formal tag moved — this story may only touch flagged rookies")


def test_the_recorded_evidence_states_that_the_LIVE_class_is_INACTIVE():
    """⭐⭐ NF-D20, and the single most misreadable number in this story. **Not one 2026 rookie
    carries a formal tag today** — the 53-man cutdown that creates the population is 2026-08-30 —
    so every 2026-only reading here passes WITHOUT TESTING ANYTHING, and the live meter reads 0
    both with and without the fix. A packet that quoted "meter = 0 on the live board" as evidence
    the routing works would be quoting an inactive gate as a pass.

    The recorded artifact must therefore say which seasons were ACTIVE, and 2026 must not be among
    them while that remains true."""
    import json
    rep = json.loads(_ART.read_text())
    leg3 = rep["leg3_wiring_end_to_end"]
    assert leg3["n_active_seasons"] >= 5, (
        "the wiring leg was verified on too few seasons carrying a flagged rookie — a leg with no "
        "active season passes on nothing")
    per = {d["season"]: d for d in leg3["per_season"]}
    assert 2026 in per, "the live class was not read at all"
    assert per[2026]["flagged"] == 0 or per[2026]["active"], (
        "inconsistent activity record for the live class")
    if per[2026]["flagged"] == 0:
        assert per[2026]["active"] is False, (
            "a season with no flagged rookie is recorded as ACTIVE — an inactive gate reported as "
            "a pass is the failure mode this clause exists for")
    assert rep["leg4_meter_rookie_half"]["n_informative_seasons"] >= 5, (
        "the meter leg keyed on seasons whose PRE-fix reading was already 0 — a meter that was "
        "always 0 cannot show that anything was fixed")
