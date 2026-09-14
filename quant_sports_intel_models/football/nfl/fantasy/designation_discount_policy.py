"""designation_discount_policy.py — the ONE place the served WEEKLY-DESIGNATION discount is decided
(NF-INJ4b), the sibling of `injury_games_policy` (formal availability), `veteran_level_policy`
(veteran level) and `rookie_publish_policy` (rookie leg).

WHAT IS SERVED (when `SERVING_ENABLED`): NF-INJ4b's certified `desig_x_practice` arm, as a
per-designation REMAINING-SEASON RATE on `proj_games` — `Out ×0.8639`, `Doubtful ×0.9526`,
`Questionable ×0.9629`. The constants are PERSISTED in `served_artifacts/` and loaded at build time;
⛔ never re-fitted on a serving path (MH2.1 (b): serve the object that was validated), and never
typed here (NF-INJ4b §3b(3): the counterfactual's first magnitude table priced the REGISTERED arm
rather than the CERTIFIED WINNER — `out ×0.8682` against `×0.8639` — a transcription slip that
produced a plausible, wrong operator packet).

WHY THIS FORM — the record: `ablation_results/nf_inj4b_designation_duration.md` (NF-INJ4b: 9 of 9
registered gates under a matched-resolution anchor) and its parent `nf_inj4_designation_duration.md`
(NF-INJ4, `CONSTRAINT_REFUSED` — the same measurement under a registration whose `oracle_respected`
clause measured the ORACLE'S SAMPLE SIZE rather than an arm property).

⭐ **SCOPE, and it is a boundary rather than an omission.** Only the three DISCLOSED weekly
designations are priced. Two exclusions are deliberate:

  · `none_listed` (×0.9906) is the baseline hazard the arm reports for CONTEXT. Applying it would
    discount ~2,400 undesignated players — a board-wide LEVEL SHIFT, which is a different change
    from the one that was certified and the one the counterfactual priced (59 designated rows per
    board). It is in the artifact and is not served.
  · A MODELLED roster status (IR / PUP / NFI / SUS) never reaches this channel at all:
    `sleeper_injuries_source.disclosable_designation` withholds it at the SOURCE, because the formal
    channel already prices it. That is what makes the two channels disjoint at the feed, before any
    composition argument is needed.

⭐ **DISJOINTNESS IS COMPOSED, NOT STACKED.** Both this channel and the formal one are min-caps on
the same `proj_games` computed from the SAME pre-step baseline, so
`nf_inj4_designation_duration.compose_availability_caps` takes the single strongest and records one
owning channel. Applying them sequentially compounds two rate caps — 7.83 where the composed answer
is 9.06 on the registered both-channels row. The designation cap also stamps
`_formal_discount_applied`, because `reported_absence_games` skips a row on that flag: a designation
cap that did not set it would let a player carrying BOTH a news cap and a live designation take both
(the NEWS-1 rule, arriving through a channel that rule predates).

⭐ THE FLIP IS ONE READ OF `serving_enabled()`. `SERVING_ENABLED = False` ⇒ no production caller
passes `designation_games`, `new_games` is `formal_new` itself, and the board is BYTE-IDENTICAL to
the pre-NF-INJ4b path — the rollback is the same code path, not a second one.

🔒 **SERVING IS ON** as of NF-INJ4b-SHIP. ⚠️⚠️ **AND THE MERGE IS THE DEPLOY.** Unlike the API
Lambda (which needs an explicit `deploy.sh`), the season board is published by
`sports_nfl_board_publish_schedule` — a Dagster schedule that ships `default_status=RUNNING` and
runs `export_draft_board_json --publish` daily at 07:15 America/Los_Angeles from the box image,
which is built from `main` on merge. So there is NO gate between merging this and serving it; the
operator's ship decision IS the merge decision (the MH2.1 (c) promotion-mechanics landmine, on the
fantasy board). ⛔ If that decision is NO, this flag goes to False and NF-C9's copy reverts WITH it —
`betting_ml/tests/test_nf_inj4b_ship_wiring.py` refuses the two halves drifting apart.
"""
from __future__ import annotations

import json
from pathlib import Path

#: The story that certified the served arm, and its recorded parent refusal.
SOURCE_MODEL = "NF-INJ4b"
PREDECESSOR = "NF-INJ4"
DECISION_STORY = "NF-INJ4b-SHIP"
MODEL_VERSION = "nfl_fantasy_nf_inj4b_designation_duration_v1"
#: what the board stamps when serving is OFF — the pre-NF-INJ4b state, a discount of exactly zero.
INCUMBENT_MODEL_VERSION = "nfl_fantasy_designation_discount_none_v1"

#: The recorded dispositions. ⛔ Read, never re-labelled (E2.1-r).
DISPOSITION = "SHIP_CANDIDATE"                  # NF-INJ4b: 9/9 registered gates, deploy-held
PREDECESSOR_DISPOSITION = "CONSTRAINT_REFUSED"  # NF-INJ4: same measurement, anchor measured n

#: The served form + arm, READ from the decisive record by the artifact builder so they cannot drift.
ARM = "desig_x_practice"
SELECTION_STATUS = "STATISTICALLY_SELECTED"
STATISTICALLY_SELECTED = True

#: 🔒 THE FLIP. See the module docstring: with the board on a RUNNING publish schedule, merging this
#: at True is the deploy.
SERVING_ENABLED: bool = True

#: the persisted constants (committed, NOT gitignored — the fitting frame IS gitignored, so a
#: build-time fit would be the NF-INFRA1 deploy-ephemeral time bomb).
ARTIFACT_FILENAME = "nfl_fantasy_designation_duration_v1.json"
_ARTIFACT = Path(__file__).resolve().parent / "served_artifacts" / ARTIFACT_FILENAME


def serving_enabled() -> bool:
    """The ONE read. Every caller asks this rather than the constant, so the flip has one owner."""
    return bool(SERVING_ENABLED)


def load_constants() -> dict:
    """`{designation -> {expected_games_missed, rate_multiplier}}` for the SERVED designations only.

    ⛔ RAISES on an absent or incoherent artifact rather than degrading to "no discount". A silently
    empty discount is byte-indistinguishable from a correctly-applied one that happened to move
    nothing (NF-INJ4b §3b(2), where a label-case mismatch made the whole discount a no-op with no
    error and a join coverage reading a healthy 89)."""
    if not _ARTIFACT.exists():
        raise FileNotFoundError(
            f"the served designation-duration constants are absent at {_ARTIFACT}. ⛔ This is a "
            f"serving artifact, so its absence is a build failure, never a silent no-discount. "
            f"Rebuild it with run_nf_inj4b_ship_serving_artifact (it needs the gitignored frame).")
    payload = json.loads(_ARTIFACT.read_text())
    if payload.get("arm") != ARM:
        raise RuntimeError(
            f"the served artifact carries arm {payload.get('arm')!r} but this policy serves {ARM!r} "
            f"— the certified-winner transcription defect (NF-INJ4b §3b(3)) in its other direction.")
    served = payload["served_designations"]
    out = {d: payload["designations"][d] for d in served}
    missing = [d for d in served if d not in payload["designations"]]
    if missing:
        raise RuntimeError(f"the served artifact declares {missing} served but carries no constant "
                           f"for them — refusing rather than pricing them at 1.0.")
    return out


def stamp() -> dict:
    """What the board records about WHICH designation model produced its games figures."""
    on = serving_enabled()
    return {
        "designation_discount_model_version": MODEL_VERSION if on else INCUMBENT_MODEL_VERSION,
        "designation_discount_serving_enabled": on,
        "designation_discount_source_model": SOURCE_MODEL,
        "designation_discount_arm": ARM if on else None,
    }


def assert_coherent() -> None:
    """Refuse a flip that contradicts the record, AT IMPORT (the `injury_games_policy` shape).

    ⭐ A bare flag flip is exactly how a refused study gets served by accident, so the contradiction
    is refused here rather than caught in review."""
    if SERVING_ENABLED and DISPOSITION not in ("SHIP", "SHIP_CANDIDATE"):
        raise RuntimeError(
            f"designation_discount_policy: SERVING_ENABLED is True but {SOURCE_MODEL}'s recorded "
            f"disposition is {DISPOSITION!r}. A flip that contradicts the record is refused "
            f"(E2.1-r). Record a NEW disposition first.")
    if SERVING_ENABLED and PREDECESSOR_DISPOSITION == DISPOSITION:
        raise RuntimeError(
            "designation_discount_policy: the predecessor's refusal and this study's disposition "
            "cannot be the same string — one of them has been edited to match the other, which is "
            "how a refused study becomes a served one without a fresh registration.")


assert_coherent()
