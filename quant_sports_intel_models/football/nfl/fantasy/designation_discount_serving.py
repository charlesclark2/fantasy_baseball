"""designation_discount_serving.py — build the `designation_games` callable the season board's
availability owner consumes (NF-INJ4b-SHIP).

⭐ **DISPATCH-ONLY BY DESIGN.** This module fits nothing and knows no constants. It reads the
persisted artifact through `designation_discount_policy`, reads the live designation map through the
board's OWN feed owner, and returns a callable. Everything that could drift from the certified arm
lives in the artifact; everything that could drift from the board's id join lives in the exporter.

⭐ **ONE OWNER FOR THE FEED, REUSED NOT RE-IMPLEMENTED.** The map comes from
`export_draft_board_json.weekly_designation_map`, which already encodes three things this module
must not get independently right: the three-state return (unreadable feed / nothing to disclose /
uninterpretable value), the withholding of MODELLED statuses at the SOURCE (so the formal channel
and this one are disjoint before any composition), and `_norm_player_id` — the normaliser that
exists because 275 of 2,501 live feed rows carry a LEADING SPACE in `player_id`, which silently cost
Josh Jacobs and DK Metcalf their disclosure on a published board. A second implementation here would
be a second chance to get that wrong (the E9.61 two-renderers rule, on a join key).

⚖️ **TIER — ALERT-loud-but-continue, and the reasoning is the boundary.** A designation-feed outage
must NOT fail the board build: the boards are the draft-critical output and a board without this
discount is exactly the board that served all of last season. But it must never be SILENT either —
NF-INJ4b §3b(2) is the case in point, where a label-case mismatch made the entire discount a no-op
with no error while an id-join coverage read a healthy 89. So an unreadable feed logs `[ALERT]` and
returns None (the caller then passes no channel, and the board is byte-identical to the
pre-NF-INJ4b path), while a feed that IS readable but carries a label we have no constant for
**RAISES** — because that is a broken contract, not an outage.

⛔ **THE ROW COUNT IS RECORDED, NOT INFERRED.** `row_log` carries how many rows the discount actually
MOVED, so "served with the discount" and "served without it" are distinguishable on the artifact
rather than from the policy stamp alone (NF-INJ3b-SHIP D6 / NF-C0e: a stamp says what a build was
CONFIGURED to do, never what it did).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import designation_discount_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import nf_inj4_designation_duration as DD

log = logging.getLogger("nfl.fantasy.designation_discount")

#: ⛔ "not supplied" and "supplied as unreadable" are DIFFERENT facts and a bare `None` default
#: conflates them — the caller that passes nothing wants a fetch, the caller that passes None
#: is telling us the feed came back unreadable. Collapsing the two would make an outage
#: indistinguishable from a normal build (NF-C9's absent-vs-null rule, on a parameter).
_UNSET = object()


def _multiplier_by_label() -> dict:
    """`{feed label -> published rate multiplier}` — the SERVED constants keyed as the feed labels.

    ⚠️ The feed emits TITLE-CASE display labels (`Questionable`) and the model's levels are
    lower-case (`questionable`). NF-INJ4b §3b(2): the counterfactual's first cut mapped one onto the
    other directly, every multiplier resolved to NaN, `.fillna(1.0)` applied nothing, and the result
    was a plausible zero. The crosswalk is built from the feed's OWN vocabulary here, and a label
    with no constant raises below rather than defaulting.

    ⭐ **THE PUBLISHED `rate_multiplier` IS SERVED, NOT ONE RE-DERIVED FROM `expected_games_missed`,
    and the difference is not academic.** Both figures are stored at the 4 decimals the operator
    packet publishes, so re-deriving `(17 − 2.3145)/17 = 0.863853` instead of using the published
    `0.8639` moves a 17-game projection by 8e-4 games. Numerically that is nothing; as a PROPERTY it
    is the difference between "the board does what the packet said" being exactly true and being
    approximately true, and a ship decision is made against the packet's numbers."""
    from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI

    consts = POLICY.load_constants()
    out = {}
    for label in SI.WEEKLY_DESIGNATIONS.values():
        level = str(label).strip().lower()
        if level in consts:
            out[str(label)] = float(consts[level]["rate_multiplier"])
    return out


def designation_games_callable(season: int, *, designations=_UNSET,
                               row_log: dict | None = None):
    """The `frame -> np.ndarray` callable for `season_projection.apply_availability_chain`, or None.

    Returns **None** when serving is off or the feed is unreadable. None is the honest value: the
    availability owner then takes its no-designation branch, in which `new_games` is `formal_new`
    ITSELF, so the board is byte-identical to the pre-NF-INJ4b path BY CONSTRUCTION rather than by
    an argument about monotonicity.
    """
    if not POLICY.serving_enabled():
        log.info("NF-INJ4b: the weekly-designation discount is OFF (policy) — the board serves the "
                 "pre-NF-INJ4b games figures, a discount of exactly zero.")
        return None

    if designations is _UNSET:
        from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
        designations = EX.weekly_designation_map(season)

    if designations is None:
        log.warning("[ALERT] NF-INJ4b: the weekly game-status feed is UNREADABLE — the board will "
                    "serve NO designation discount this build. It is not wrong, it is the "
                    "pre-NF-INJ4b board; but it is NOT the board the discount was approved for, so "
                    "this line is the only thing that distinguishes them.")
        if row_log is not None:
            row_log["feed_readable"] = False
            row_log["rows_moved"] = 0
        return None

    # ⭐ BOTH SIDES OF THE JOIN GO THROUGH THE ONE NORMALISER. `weekly_designation_map` already
    #    normalises its keys, so in production this is a no-op — but which END is padded is a
    #    property of the FEED, not of our code, and it has changed under us before (275 of 2,501
    #    live rows carry a leading space). Normalising one end is half a fix (NF-C9).
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as _EX
    designations = {_EX._norm_player_id(k): v for k, v in designations.items()}

    mult_by_label = _multiplier_by_label()
    # ⛔ A label we cannot price RAISES. The alternative — price it at 1.0 — produces a discount
    #    that is silently absent for exactly the players it was most likely to matter for.
    unpriceable = sorted({str(v) for v in designations.values() if v is not None} - set(mult_by_label))
    if unpriceable:
        raise RuntimeError(
            f"the live designation feed carries label(s) {unpriceable} that the served artifact has "
            f"no constant for (served: {sorted(mult_by_label)}). ⛔ Refusing rather than defaulting to "
            f"no discount — a silent no-discount is indistinguishable from a correctly-applied one "
            f"that happened to move nothing (NF-INJ4b §3b(2)).")

    def _designation_games(frame: pd.DataFrame) -> np.ndarray:
        from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX

        current = frame["proj_games"].to_numpy(dtype=float)
        pid = frame["player_id"].map(EX._norm_player_id)
        label = pid.map(designations)
        out = current.astype(float).copy()
        moved = 0
        for i, lab in enumerate(label.to_numpy()):
            if lab is None or (isinstance(lab, float) and pd.isna(lab)):
                continue                      # nothing to disclose, or an uninterpretable value
            mult = mult_by_label.get(str(lab))
            if mult is None:
                continue                      # `(True, None)` — disclosed as unknown, never priced
            # routed through the REGISTERED rate form (one owner) at the PUBLISHED multiplier
            capped = DD.remaining_season_rate_cap(
                current[i], DD.SEASON_GAMES * (1.0 - mult))
            if np.isfinite(capped) and capped < current[i] - 1e-9:
                moved += 1
            out[i] = capped
        if row_log is not None:
            row_log["feed_readable"] = True
            row_log["designated_rows_on_frame"] = int(label.notna().sum())
            row_log["rows_moved"] = int(row_log.get("rows_moved", 0)) + moved
        log.info("NF-INJ4b: designation discount applied to %d of %d rows (%d carried a "
                 "designation)", moved, len(frame), int(label.notna().sum()))
        return out

    return _designation_games
