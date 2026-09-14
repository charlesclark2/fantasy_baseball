"""run_nf_inj4b_ship_serving_artifact.py — derive the SERVED designation-duration constants ONCE,
from the CERTIFIED winner, and persist them as a COMMITTED artifact.

⭐ **WHY A PERSISTED ARTIFACT RATHER THAN A BUILD-TIME FIT** — two independent reasons, both of
which this repo has already paid for:

  1. **MH2.1 (b): serve the object that was VALIDATED, never a re-derivation.** The certified arm is
     `desig_x_practice`, selected by NF-INJ4b under a matched-resolution anchor. A serving path that
     re-fitted it at build time would be free to drift from the object the gates scored.

  2. ⛔ **NF-INFRA1: the fitting frame is GITIGNORED.** `artifacts/.gitignore` carries `*.parquet`,
     so `nf_inj4_designation_frame_2025.parquet` is ABSENT from the `COPY . .` box image. A build-time
     fit would therefore die on the box — or, far worse, degrade quietly to whatever a bare `except`
     decided. A serving artifact under a gitignored path is the deploy-ephemeral time bomb NF-INFRA1
     names; this one is committed under `served_artifacts/`, beside NF-INJ3b's.

⭐ **THE CONSTANTS ARE READ OUT OF THE DECISIVE RUN, NEVER NAMED HERE.** `winner` comes from
`nf_inj4b_designation_duration.json`. That is not fastidiousness: NF-INJ4b's own §3b(3) records the
counterfactual's magnitude table pricing the REGISTERED arm rather than the CERTIFIED WINNER
(`out ×0.8682` against the certified `×0.8639`) — a transcription slip that produced a plausible,
wrong operator packet. Reading the winner is what makes that class unavailable.

⭐ **AND IT IS VERIFIED AGAINST THE OPERATOR'S COUNTERFACTUAL.** The written constants must
reproduce `nf_inj4b_counterfactual.json`'s published magnitude table EXACTLY, because that is the
table the operator's ship decision is being made against. A serving artifact that disagreed with the
packet would mean the operator approved one number and the board served another.

⚠️ **POSITION-INVARIANT, AND MEASURED RATHER THAN ASSUMED.** The live feed carries no practice
column, so every live row resolves at `practice = unknown` and backs off to the designation-only
parent; at that resolution the arm is position-invariant to 0.0e+00 across QB/RB/WR/TE. The check
runs here and REFUSES on a spread, so a future arm that is NOT position-invariant cannot be silently
flattened into per-designation constants.

⚠️ **`games_remaining = 17` IS THE CERTIFIED RESOLUTION, and it is a scope statement.** The
predictive is truncated to a row's own support, so `E[missed]` falls once fewer than ~12 games
remain (measured: 2.3145 at 17/16/12, 2.1032 at 8, 1.8483 at 4). The counterfactual priced the
full-remaining-season constant and the operator's decision is being made on it, so that is what
serves. ⛔ A per-row `games_remaining` refinement is a DIFFERENT, UNREGISTERED model — it is not
adopted here, and adopting it later is a fresh registration, not a config change.

RUN (LAPTOP — needs the gitignored fitting frame, so `--frame` normally points at the MAIN checkout):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_ship_serving_artifact \
        --frame <main>/quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_inj4_designation_frame_2025.parquet
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    nf_inj4_designation_duration as DD,
)

_HERE = pathlib.Path(__file__).resolve().parent
_ART = _HERE / "ablation_results"
_DECISIVE = _ART / "nf_inj4b_designation_duration.json"
_COUNTERFACTUAL = _ART / "nf_inj4b_counterfactual.json"
_SERVED_DIR = _HERE / "served_artifacts"
ARTIFACT_FILENAME = "nfl_fantasy_designation_duration_v1.json"

#: the designations the SERVED channel prices. ⛔ `none_listed` is DELIBERATELY EXCLUDED: it is the
#: baseline hazard the arm reports for context, and applying its ×0.9906 to every undesignated
#: player would be a BOARD-WIDE level shift on ~2,400 rows — a completely different change from the
#: one NF-INJ4b certified and the counterfactual priced (59 designated rows per board).
SERVED_DESIGNATIONS: tuple[str, ...] = ("out", "doubtful", "questionable")

#: the resolution the certified constants are read at — see the module docstring.
CERTIFIED_GAMES_REMAINING = int(DD.SUPPORT_MAX)


def derive(frame: pd.DataFrame, arm: str) -> dict:
    """`{designation -> {expected_games_missed, rate_multiplier}}` for the certified arm.

    Mirrors `run_nf_inj4b_counterfactual.magnitude_table` step for step — same probe, same
    truncation, same rounding — because the whole point is that the served object and the packet
    the operator reads are the same numbers."""
    rows = {}
    for desig in DD.DESIGNATION_LEVELS:
        per_pos = {}
        for pos in ("QB", "RB", "WR", "TE"):
            probe = pd.DataFrame([{"designation": desig, "position": pos,
                                   "practice_level": DD.PRACTICE_UNKNOWN,
                                   "games_remaining": CERTIFIED_GAMES_REMAINING, "spell": 0}])
            pmf = DD.truncate_to_support(DD.fit_predict(arm, frame, probe),
                                         probe["games_remaining"].to_numpy())
            per_pos[pos] = float(DD.expected_games_missed(pmf)[0])
        spread = max(per_pos.values()) - min(per_pos.values())
        if spread > 1e-12:
            raise SystemExit(
                f"⛔ the certified arm is NOT position-invariant for {desig!r} at "
                f"practice={DD.PRACTICE_UNKNOWN!r} (spread {spread:.3e} across {per_pos}). The "
                f"served artifact stores ONE constant per designation, which would silently flatten "
                f"a real per-position effect. Refusing — a position-varying arm needs a "
                f"position-keyed artifact and a fresh look at the serving contract.")
        missed = per_pos["RB"]
        rows[desig] = {"expected_games_missed": round(missed, 4),
                       "rate_multiplier": round((DD.SEASON_GAMES - missed) / DD.SEASON_GAMES, 4)}
    return rows


def _verify_against_counterfactual(rows: dict) -> dict:
    """⛔ The served constants MUST equal the ones in the operator's packet.

    An artifact that disagreed with the counterfactual would mean the operator approved one set of
    numbers and the board served another — the "declaration outran its production" class (NF-C0e)
    with the roles reversed, and entirely invisible once the packet is filed."""
    if not _COUNTERFACTUAL.exists():
        raise SystemExit(
            f"⛔ {_COUNTERFACTUAL.name} is absent — the served constants cannot be checked against "
            f"the operator's packet, and an unverifiable check is never a pass (NF1.7 (a)). Run the "
            f"counterfactual first (it is the operator's command).")
    cf = json.loads(_COUNTERFACTUAL.read_text())
    published = {r["designation"]: r for r in cf["magnitude_table"]["rows"]}
    if cf["magnitude_table"]["arm"] != json.loads(_DECISIVE.read_text())["winner"]:
        raise SystemExit(
            f"⛔ the counterfactual priced arm {cf['magnitude_table']['arm']!r} but the decisive run "
            f"certified {json.loads(_DECISIVE.read_text())['winner']!r}. This is exactly NF-INJ4b "
            f"§3b(3)'s registered-arm-vs-certified-winner defect; nothing downstream is trustworthy.")
    mismatches = []
    for desig, got in rows.items():
        want = published.get(desig)
        if want is None:
            mismatches.append(f"{desig}: absent from the counterfactual's table")
            continue
        for field in ("expected_games_missed", "rate_multiplier"):
            if abs(float(got[field]) - float(want[field])) > 1e-9:
                mismatches.append(f"{desig}.{field}: served {got[field]} vs packet {want[field]}")
    if mismatches:
        raise SystemExit("⛔ SERVED CONSTANTS DISAGREE WITH THE OPERATOR'S PACKET:\n  "
                         + "\n  ".join(mismatches))
    return {"checked_against": _COUNTERFACTUAL.name,
            "counterfactual_generated_at": cf["generated_at"],
            "designations_checked": sorted(rows), "max_abs_difference": 0.0, "reproduces": True}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-INJ4b-SHIP served-constant derivation")
    ap.add_argument("--frame", required=True,
                    help="the gitignored NF-INJ4 designation frame (normally in the MAIN checkout)")
    args = ap.parse_args(argv)

    decisive = json.loads(_DECISIVE.read_text())
    if not decisive.get("ship"):
        raise SystemExit(f"⛔ {_DECISIVE.name} does not record ship=True — refusing to build a "
                         f"serving artifact for an unshipped study (E2.1-r).")
    arm = decisive["winner"]
    frame = pd.read_parquet(args.frame)
    rows = derive(frame, arm)
    verification = _verify_against_counterfactual(rows)

    payload = {
        "model_version": "nfl_fantasy_nf_inj4b_designation_duration_v1",
        "contract_version": 1,
        "source_model": decisive["story"],
        "arm": arm,
        "verdict": decisive["verdict"],
        "preregistration": "ablation_results/nf_inj4b_preregistration.md",
        "decisive_record": "ablation_results/nf_inj4b_designation_duration.md",
        "served_designations": list(SERVED_DESIGNATIONS),
        "certified_games_remaining": CERTIFIED_GAMES_REMAINING,
        "season_games": float(DD.SEASON_GAMES),
        "practice_level": DD.PRACTICE_UNKNOWN,
        "designations": rows,
        "frame_rows": int(len(frame)),
        "fit_at": datetime.now(timezone.utc).isoformat(),
        "position_invariance": "verified to 0.0e+00 across QB/RB/WR/TE at practice=unknown",
        "notes": (
            "Derived by run_nf_inj4b_ship_serving_artifact from the CERTIFIED winner read out of "
            "the decisive run, on the frame NF-INJ4b scored. `none_listed` is reported for context "
            "and is NOT served — applying it would be a board-wide level shift, not this study. The "
            "constants reproduce the operator counterfactual's magnitude table exactly."),
    }
    _SERVED_DIR.mkdir(exist_ok=True)
    (_SERVED_DIR / ARTIFACT_FILENAME).write_text(json.dumps(payload, indent=1) + "\n")
    (_SERVED_DIR / ARTIFACT_FILENAME.replace(".json", ".verification.json")).write_text(
        json.dumps(verification, indent=1) + "\n")
    print(f"wrote {_SERVED_DIR / ARTIFACT_FILENAME}")
    for d, r in rows.items():
        mark = "SERVED " if d in SERVED_DESIGNATIONS else "context"
        print(f"  [{mark}] {d:14s} missed={r['expected_games_missed']:.4f} "
              f"mult=x{r['rate_multiplier']:.4f}")
    print(f"verified against {verification['checked_against']}: reproduces exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
