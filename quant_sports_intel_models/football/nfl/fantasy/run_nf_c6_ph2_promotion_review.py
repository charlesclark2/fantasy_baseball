"""run_nf_c6_ph2_promotion_review.py — NF-G0's ten gates over the WEEKLY champion.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_c6_ph2_promotion_review

⭐ THIS IS THE REGISTRY'S FIRST REAL PROMOTION REVIEW. NF-D21's was gate-REFUSED (an interval-floor
breach that NF-D22 later showed was a coin-flip at n=148), so the pipeline has never yet carried a
release through to a served version. That means every gate here is live rather than ceremonial, and
the two things a first run must not do are (a) declare a gate passed that could not see its subject,
and (b) invent a baseline so a comparison gate has something to compare against.

⛔ THIS SCRIPT STAGES; IT DOES NOT PROMOTE. It writes a CHALLENGER entry and records a verdict. The
`promote()` call is an OPERATOR step taken on the recorded verdict — and under this story's
deploy-held posture a registry change ships with the box image ON MERGE TO MAIN (MH2.1: merging IS
the deploy), so nothing here may make that decision on the operator's behalf.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS PROMOTES, AND WHAT IT DELIBERATELY LEAVES A CHALLENGER
────────────────────────────────────────────────────────────────────────────────────────────────
Promote ONLY what this story SERVES. The registry currently holds three staged NFL-fantasy weekly
challengers, and each names its own blockers:

  · `nfl_fantasy_w2b_v1`  (weekly_projection, the injury-rate arm) — its notes block promotion until
    NF-C6 Phase 2 *and* a live in-season stamped injury forward-capture *and* pre-flip snapshots.
    This story satisfies the FIRST of three. It stays a CHALLENGER.
  · `nfl_fantasy_w6c_v1` / `w6d_v1` (weekly_stat_distribution — a DIFFERENT target) — their notes
    block promotion until the arbitrary-league re-scoring consumer exists, which is the DEFERRED
    gate-3 story. Nothing here reads them. They stay CHALLENGERS.

So this review covers exactly one thing: the NF-W1 base champion's points distribution, which is
what the weekly serving path actually serves.

────────────────────────────────────────────────────────────────────────────────────────────────
THREE GATES CANNOT SEE THEIR SUBJECT ON A FIRST PROMOTION, AND THEY ARE NAMED RATHER THAN WAIVED
────────────────────────────────────────────────────────────────────────────────────────────────
`all_passed(allow_unevaluable=...)` requires the caller to NAME any gate it will accept as
unresolved, precisely so one can never be waved through by accident. This run names none of them:
`ready_to_promote` is computed with the strict default, so a first review reports FALSE and says
exactly why. The reasons differ in kind and the record keeps them apart:

  · `live_payload_matches_staged` / `clients_agree_on_version` — POST-PUBLISH by construction
    (`gates.POST_PUBLISH_GATE_NAMES`). There is no live payload to read before publishing one.
  · `universe_count` — needs a PREVIOUS universe. Nothing weekly has ever served, so there is no
    baseline; supplying one would be inventing the comparison the gate exists to make.
  · `scoring_parity` — asks whether the displayed point equals what the scoring engine derives from
    the stat line. For the SEASON board that is a real question, because NF-D21 moves the point by
    rescaling the line. ⛔ FOR THE WEEKLY IT IS NOT: the points distribution and the component head
    are INDEPENDENT models fitted side by side, so the point is not derived from the line at all and
    a `max_abs_diff` of 0.0 would be a fabricated pass. It is left UNEVALUABLE and a genuine
    COHERENCE diagnostic is measured beside it instead — the NF-INJ1 question ("is this point
    consistent with this line?") rather than the season's parity question.

⚠️ AND ONE GATE SEES LESS THAN IT LOOKS. `model_stamp_consistency` reconciles six lineage fields, of
which the weekly family populates exactly ONE (`served_version`) — the others name a level model, an
ordering model and a rookie leg the weekly stack does not have. The gate is honest about an EMPTY
intersection but not about a THIN one, so this review reports the intersection size and runs a
supplementary reconciliation over the weekly's OWN lineage fields beside it. ⛔ Extending the shared
gate is deliberately NOT done here: it is a cross-vertical instrument and changing it means sweeping
every guard that pins its output (MH2.7), which is its own change, not a rider on this one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.backend.models import nfl_weekly as C  # noqa: E402
from betting_ml.governance import gates as G  # noqa: E402
from betting_ml.governance import registry as R  # noqa: E402
from betting_ml.utils import coverage_power_floor as CPF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_c6_ph2_review")

_FAN = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_ABLATION = _FAN / "ablation_results"
_STAGING = _FAN / "artifacts/weekly_serving"
_BAKEOFF = _ABLATION / "nf_w1_weekly_bakeoff.json"

MODEL_FAMILY = "nfl_fantasy"
TARGET = "weekly_projection"
PROJECTION_SOURCE = "nf_w1_weekly"

#: NF-W1's per-position held-out coverage of the central 80% band, and the row count each was
#: measured on. Read from the bake-off record rather than restated — a hand-copied number is a
#: second owner of a measurement (INC-38).
INTERVAL_NOMINAL = 0.80


def _bakeoff() -> dict:
    if not _BAKEOFF.is_file():
        raise SystemExit(f"NF-W1's record is missing at {_BAKEOFF} — it is this promotion's "
                         "validation report AND its rollback artifact; the review cannot run.")
    return json.loads(_BAKEOFF.read_text())


def interval_revalidation(bakeoff: dict) -> dict:
    """NF-W1's per-position coverage, re-read against the floor NOW IN FORCE.

    ⭐ NF-D22 REPLACED THE HARD POINT-ESTIMATE FLOOR, and this review must use the replacement or it
    would judge a certified band by a rule the programme has retired — one whose false-reject rate
    against a PERFECTLY calibrated band is 0.393–0.500 at every n. `power_floor` derives the bar
    from the group's own n and a pre-registered false-reject target, and takes no coverage argument,
    so it cannot be reverse-engineered from the value it is judging (E2.1-r-proof).

    ⚠️ THE GATE'S OWN POPULATION LOOP IS INACTIVE HERE, and that is reported rather than hidden:
    `interval_floors` scans `rookies`/`veterans`/`kdst`, and this family is per-POSITION. So the
    misses are computed HERE and handed over as the verdict, and `populations_read_by_the_gate` says
    the loop found nothing to read. A `pass` supplied without that disclosure would be the gate
    passing on the caller's say-so.
    """
    positions, misses = {}, []
    for pos, block in (bakeoff.get("positions") or {}).items():
        cov = ((block.get("selection") or {}).get("coverage")
               or block.get("coverage") or {})
        c = cov.get("winner_coverage_80")
        n = cov.get("n_rows")
        if c is None or not n:
            misses.append(f"{pos}:coverage-unreadable")
            continue
        floor = CPF.power_floor(int(n), nominal=INTERVAL_NOMINAL)
        ok = float(c) >= floor
        positions[pos] = {"coverage": round(float(c), 4), "n": int(n),
                          "power_floor": round(floor, 4), "pass": ok,
                          "margin_rows": int(round((float(c) - floor) * int(n)))}
        if not ok:
            misses.append(f"{pos}:{c:.4f}<{floor:.4f}")
    return {
        "pass": not misses and bool(positions),
        "misses": misses,
        "floor_rule": "NF-D22 power-derived exact one-sided Binomial acceptance bound",
        "nominal": INTERVAL_NOMINAL,
        "positions": positions,
        "populations_read_by_the_gate": [],
        "note": ("per-POSITION, so `interval_floors`' rookies/veterans/kdst loop reads nothing; the "
                 "misses handed to it are computed here against the NF-D22 floor and the "
                 "per-position detail is recorded so the verdict is checkable rather than asserted"),
    }


def _digest(blob: object) -> str:
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()


def _staged() -> tuple[dict, dict] | tuple[None, None]:
    """The newest staged (manifest, payload), or (None, None) when nothing has been built."""
    pointers = sorted(_STAGING.glob("*/current.json")) if _STAGING.exists() else []
    if not pointers:
        return None, None
    cur = json.loads(pointers[-1].read_text())
    week_dir = pointers[-1].parent / str(cur["week"])
    return (json.loads((week_dir / "manifest.json").read_text()),
            json.loads((week_dir / "players.json").read_text()))


def component_coherence(payload: dict | None) -> dict:
    """⭐ THE HONEST SUBSTITUTE FOR `scoring_parity` ON THIS FAMILY.

    The season gate asks "does the displayed point equal what the scorer derives from the line?" —
    a real question there because the rookie leg moves the point by rescaling the line. The weekly
    point and the weekly line come from two INDEPENDENT heads, so that question has no answer and a
    0.0 would be fabricated.

    What IS answerable, and is the NF-INJ1 question, is whether the two are COHERENT: PPR scored
    from the served component line versus the served point. They are not expected to agree exactly —
    they are different models — so this is a DIAGNOSTIC that is reported, never a gate. A large
    divergence would be a finding worth a story; a modest one is what two heads look like.
    """
    if not payload:
        return {"evaluable": False, "reason": "nothing staged"}
    diffs = []
    for r in payload.get("players") or []:
        if r.get("status") != "projected" or r.get("rec") is None:
            continue
        ppr = (0.04 * (r.get("passYds") or 0.0) + 4.0 * (r.get("passTd") or 0.0)
               - 2.0 * (r.get("passInt") or 0.0)
               + 0.1 * (r.get("rushYds") or 0.0) + 6.0 * (r.get("rushTd") or 0.0)
               + 1.0 * (r.get("rec") or 0.0) + 0.1 * (r.get("recYds") or 0.0)
               + 6.0 * (r.get("recTd") or 0.0))
        diffs.append(ppr - float(r["fpPpr"]))
    if not diffs:
        return {"evaluable": False, "reason": "no rows carried a component line"}
    import statistics

    a = sorted(abs(d) for d in diffs)
    return {
        "evaluable": True, "n": len(diffs),
        "mean_signed_diff": round(statistics.fmean(diffs), 4),
        "median_abs_diff": round(a[len(a) // 2], 4),
        "p95_abs_diff": round(a[int(0.95 * (len(a) - 1))], 4),
        "max_abs_diff": round(a[-1], 4),
        "interpretation": ("the points distribution and the component head are INDEPENDENT models; "
                           "this is a coherence diagnostic, never a parity gate"),
    }


def build_entry(manifest: dict | None, *, staged_digest: str | None) -> dict:
    """The CHALLENGER entry. Every field is one this family genuinely has."""
    lineage = (manifest or {}).get("lineage") or {}
    entry = {
        "served_version": WS.SERVED_VERSION,
        "base_model_version": WS.BASE_MODEL_VERSION,
        "point_model_version": WS.POINT_MODEL_VERSION,
        "interval_model_version": WS.INTERVAL_MODEL_VERSION,
        "component_head_status": "advisory_ungated",
        "projection_source": PROJECTION_SOURCE,
        "positions": list(C.PROJECTED_POSITIONS),
        "scoring_system_id": C.SCORING_SYSTEM_ID,
        "artifact_uri": "s3://credence-prod-s3-api-cache/fantasy/nfl/weekly/",
        # ⭐ THE ROLLBACK ARTIFACT IS NF-W1'S OWN RECORD, not a previous served version — nothing
        # weekly has ever served, so there is nothing to roll back TO. Naming the certified record
        # is what W2b and W6c already do, and it is honest: rolling this back means serving nothing
        # weekly, and the record is the spec that would be re-served if it ever were.
        "fallback_artifact_uri": f"repo:{_BAKEOFF.relative_to(_PROJECT_ROOT)}",
        "promotion_status": R.STAGED_STATUS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if staged_digest:
        entry["staged_digest"] = staged_digest
    if lineage.get("served_version"):
        entry["served_version"] = lineage["served_version"]
    return entry


def supplementary_lineage_check(entry: dict, manifest: dict | None) -> dict:
    """Reconcile the weekly's OWN lineage fields — the ones `model_stamp_consistency` cannot see.

    Reported BESIDE the shared gate, never folded into it: a caller that quietly widened a shared
    gate's field list would change the verdict for every other family that reads it."""
    if not manifest:
        return {"evaluable": False, "reason": "nothing staged to reconcile"}
    stamp = manifest.get("lineage") or {}
    fields = ("served_version", "base_model_version", "point_model_version",
              "interval_model_version")
    mismatches = [f"{f}: registry={entry.get(f)!r} artifact={stamp.get(f)!r}"
                  for f in fields
                  if entry.get(f) is not None and stamp.get(f) is not None
                  and str(entry[f]) != str(stamp[f])]
    checked = [f for f in fields if entry.get(f) is not None and stamp.get(f) is not None]
    return {"evaluable": bool(checked), "checked": checked, "mismatches": mismatches,
            "pass": bool(checked) and not mismatches}


def review(*, apply: bool = False) -> dict:
    bakeoff = _bakeoff()
    manifest, payload = _staged()
    staged_digest = _digest(payload) if payload else None
    entry = build_entry(manifest, staged_digest=staged_digest)

    reval = interval_revalidation(bakeoff)
    claims = [
        C.NflWeeklyHonestFraming().interval_note,
        C.NflWeeklyHonestFraming().ros_interval_note,
        C.ROS_INTERVAL_NOTE,
        *(a.get("detail", "") for a in (manifest or {}).get("absences") or []),
    ]
    # The NF-W1 claims constraint, enforced on exactly the copy this promotion would publish.
    C.assert_no_matchup_claim([(f"claim[{i}]", t) for i, t in enumerate(claims)],
                              where="the weekly promotion's published copy")

    n_players = (manifest or {}).get("n_players")
    n_rookies = (manifest or {}).get("n_rookies")

    results = G.run_gates(
        entry=entry,
        artifact_stamp=(manifest or {}).get("lineage"),
        payload_meta={"projection_source": (manifest or {}).get("projection_source")
                      or PROJECTION_SOURCE,
                      "model_version": None},
        n_staged=n_players,
        # ⛔ NO BASELINE IS INVENTED. Nothing weekly has ever served.
        n_previous=None,
        n_rookies=n_rookies,
        n_previous_rookies=None,
        revalidation=reval,
        # ⛔ NOT APPLICABLE on this family — see the module docstring. UNEVALUABLE, never a 0.0.
        scoring_max_abs_diff=None,
        scoring_n_compared=None,
        claim_texts=claims,
        rollback_exists=_BAKEOFF.is_file(),
        staged_digest=staged_digest,
        live_digest=None,      # post-publish
        backend_version=None,  # post-publish
        frontend_version=None,  # there is no weekly frontend yet — it is the NEXT story
    )
    summary = G.summarize(results)
    # ⛔ THE STRICT DEFAULT: nothing is named as an allowed unevaluable, so a first review reports
    # FALSE and the record says exactly which gates could not see their subject and why.
    ready = G.all_passed(results)

    out = {
        "story": "NF-C6-PH2",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_family": MODEL_FAMILY, "target": TARGET,
        "entry": entry,
        "ready_to_promote": ready,
        "gates": summary,
        "unresolvable_reasons": {
            "live_payload_matches_staged": "post-publish by construction (POST_PUBLISH_GATE_NAMES)",
            "clients_agree_on_version": ("post-publish, and one-sided even then — there is no "
                                         "weekly frontend yet; it is the next story"),
            "universe_count": ("no previous weekly universe exists; nothing weekly has ever served, "
                               "and inventing a baseline would fake the comparison"),
            "scoring_parity": ("not applicable: the weekly point and the weekly component line come "
                               "from INDEPENDENT heads, so the point is not derived from the line. "
                               "See `component_coherence` for the question that IS answerable"),
        },
        "interval_revalidation": reval,
        "supplementary_lineage_check": supplementary_lineage_check(entry, manifest),
        "component_coherence": component_coherence(payload),
        "staged": {"manifest_present": manifest is not None,
                   "season": (manifest or {}).get("season"),
                   "week": (manifest or {}).get("week"),
                   "n_players": n_players,
                   "staged_digest": staged_digest},
        "not_promoted_here": {
            "nfl_fantasy_w2b_v1": ("weekly injury-rate arm — its own notes require a LIVE stamped "
                                   "injury forward-capture and pre-flip snapshots beyond this "
                                   "story; stays CHALLENGER"),
            "nfl_fantasy_w6c_v1": ("per-stat distributions (a different target) — blocked on the "
                                   "DEFERRED re-scoring consumer; nothing here reads them; stays "
                                   "CHALLENGER"),
            "nfl_fantasy_w6d_v1": "as w6c; stays CHALLENGER",
        },
    }

    if apply:
        R.register(MODEL_FAMILY, TARGET, {
            **entry,
            "validation_report": _validation_report(bakeoff, reval),
            "notes": _notes(out),
        }, served_version=entry["served_version"])
        log.warning("staged CHALLENGER %s in the registry — ⛔ NOT promoted; `promote()` is an "
                    "operator step on this verdict", entry["served_version"])
    return out


def _validation_report(bakeoff: dict, reval: dict) -> str:
    pos = bakeoff.get("positions") or {}
    per = "; ".join(
        f"{p} coverage {reval['positions'].get(p, {}).get('coverage')} vs floor "
        f"{reval['positions'].get(p, {}).get('power_floor')}"
        for p in sorted(reval["positions"])
    )
    return (
        "NF-W1 weekly bake-off, SHIP x4 positions (2026-08-07): `lgbm_hurdle` (P(zero) x "
        "conditional quantile bank) beats the honest degenerate foil by +1.1703 (QB) / +0.5651 (RB) "
        "/ +0.4734 (WR) / +0.3762 (TE) mean CRPS, 8/8 folds each against a clause requiring 6; "
        "PBO 0.0, DSR 0.9888-1.0, BH-FDR pass, every degenerate and the permutation anchor beaten. "
        f"Interval floors re-read against the NF-D22 power-derived floor: {per}. "
        "⚠️ The matchup foil LOST at all four positions and lost to the FLAT foil too — the weekly "
        "edge is usage/snap conditioning, and `nfl_weekly.assert_no_matchup_claim` enforces that in "
        "the served schema. Record: quant_sports_intel_models/football/nfl/fantasy/"
        "ablation_results/nf_w1_weekly_bakeoff.md."
    )


def _notes(out: dict) -> str:
    return (
        "STAGED CHALLENGER (NF-C6-PH2) — the weekly serving path now EXISTS, which is the blocker "
        "every staged weekly entry named first. ⛔ NOT PROMOTED HERE: this run stages and records a "
        "verdict; `promote()` is an operator step, and under this story's deploy-held posture a "
        "registry change ships with the box image ON MERGE TO MAIN (MH2.1 — merging IS the deploy). "
        f"ready_to_promote={out['ready_to_promote']} at stage time, with "
        f"{out['gates']['unevaluable']} gate(s) unable to see their subject: "
        + "; ".join(f"{k} ({v})" for k, v in out["unresolvable_reasons"].items())
        + ". ⭐ NONE of them is named in `all_passed(allow_unevaluable=...)`, so none was waved "
        "through — the strict default is what produced this verdict. The component head is served "
        "PAID and stamped `advisory_ungated`: `weekly_projection.fit_component_head` calls it "
        "\"advisory raw lines beside the gated points distribution (never themselves gated in this "
        "slice)\", and a value's certification status is part of what it means. Edge-independent "
        "(best_alpha = 0)."
    )


def write_report(out: dict, path: Path) -> None:
    g = out["gates"]
    rows = "\n".join(
        f"| {r['gate']} | {r['status']} | {r['detail'][:150]} |" for r in g["gates"]
    )
    iv = out["interval_revalidation"]
    ivrows = "\n".join(
        f"| {p} | {b['coverage']} | {b['power_floor']} | {b['n']} | {b['margin_rows']:+d} | "
        f"{'✅' if b['pass'] else '❌'} |"
        for p, b in sorted(iv["positions"].items())
    )
    cc = out["component_coherence"]
    md = f"""# NF-C6-PH2 — NF-G0 promotion review: the WEEKLY champion

**Generated:** {out['generated_at']} · **family:** `{out['model_family']}` · **target:** `{out['target']}` · **version:** `{out['entry']['served_version']}`

> ⚖️ Edge-independent projection product — `best_alpha = 0`. No CLV/ROI/win-rate claim rides on any number here.

## Verdict

**`ready_to_promote = {out['ready_to_promote']}`** — {g['passed']} passed, {g['failed']} failed, {g['unevaluable']} unevaluable of {g['n']}.

⛔ **Nothing was named in `all_passed(allow_unevaluable=…)`.** The strict default produced this
verdict, so no gate was waved through. A first promotion legitimately cannot resolve every gate, and
the reasons differ in kind:

{chr(10).join(f'- **`{k}`** — {v}' for k, v in out['unresolvable_reasons'].items())}

## The ten gates

| gate | status | detail |
|---|---|---|
{rows}

### Supplementary lineage reconciliation (beyond the shared gate)

`model_stamp_consistency` reconciles six lineage fields, of which this family populates exactly one
(`served_version`) — the others name a level model, an ordering model and a rookie leg the weekly
stack does not have. The gate refuses an EMPTY intersection but not a THIN one, so the weekly's own
fields are reconciled here instead. ⛔ The shared gate is deliberately NOT extended: it is a
cross-vertical instrument, and changing it means sweeping every guard that pins its output (MH2.7).

```json
{json.dumps(out['supplementary_lineage_check'], indent=2)}
```

## Interval floors, re-read against the floor NOW IN FORCE

NF-D22 replaced the hard point-estimate floor at nominal — whose false-reject rate against a
*perfectly calibrated* band is 0.393–0.500 at every n — with the exact one-sided Binomial acceptance
bound at a pre-registered false-reject target. `power_floor` takes no coverage argument, so it
cannot be reverse-engineered from the value it judges.

| position | coverage(80) | power floor | n | margin (rows) | |
|---|---|---|---|---|---|
{ivrows}

⚠️ `interval_floors`' own population loop scans `rookies`/`veterans`/`kdst` and this family is
per-POSITION, so it read **{len(iv['populations_read_by_the_gate'])}** populations. The misses handed
to it are computed above and the per-position detail is recorded, so the verdict is checkable rather
than taken on the caller's word.

## `scoring_parity` is not applicable — and what was measured instead

The season gate asks whether the displayed point equals what the scorer derives from the stat line.
That is a real question there because NF-D21 moves the rookie point by rescaling the line. ⛔ On the
weekly family the points distribution and the component head are INDEPENDENT models fitted side by
side, so the point is not derived from the line at all and a `max_abs_diff` of 0.0 would be a
fabricated pass. The gate is left UNEVALUABLE and the answerable question — NF-INJ1's coherence
question — is measured beside it:

```json
{json.dumps(cc, indent=2)}
```

## Promoted here: nothing. Staged: one.

{chr(10).join(f'- **`{k}`** — {v}' for k, v in out['not_promoted_here'].items())}

Promotion is not a rubber stamp for the whole shelf: a staged cell with no consumer stays a
challenger. This review covers exactly what the weekly serving path serves.

## Staged artifact

```json
{json.dumps(out['staged'], indent=2)}
```
"""
    path.write_text(md)
    path.with_suffix(".json").write_text(json.dumps(out, indent=2, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-G0 promotion review for the weekly champion")
    ap.add_argument("--apply", action="store_true",
                    help="write the CHALLENGER entry to the registry (still never promotes)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = review(apply=args.apply)
    _ABLATION.mkdir(parents=True, exist_ok=True)
    write_report(out, _ABLATION / "nf_c6_ph2_promotion_review.md")
    g = out["gates"]
    log.info("verdict: ready_to_promote=%s (%d passed / %d failed / %d unevaluable of %d)",
             out["ready_to_promote"], g["passed"], g["failed"], g["unevaluable"], g["n"])
    for r in g["gates"]:
        log.info("  %-32s %s — %s", r["gate"], r["status"], r["detail"][:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
