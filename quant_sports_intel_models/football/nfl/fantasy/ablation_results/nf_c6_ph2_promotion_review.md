# NF-C6-PH2 — NF-G0 promotion review: the WEEKLY champion

**Generated:** 2026-09-05T18:39:52+00:00 · **family:** `nfl_fantasy` · **target:** `weekly_projection` · **version:** `nfl_fantasy_weekly_v1`

> ⚖️ Edge-independent projection product — `best_alpha = 0`. No CLV/ROI/win-rate claim rides on any number here.

## Verdict

**`ready_to_promote = False`** — 6 passed, 0 failed, 4 unevaluable of 10.

⛔ **Nothing was named in `all_passed(allow_unevaluable=…)`.** The strict default produced this
verdict, so no gate was waved through. A first promotion legitimately cannot resolve every gate, and
the reasons differ in kind:

- **`live_payload_matches_staged`** — post-publish by construction (POST_PUBLISH_GATE_NAMES)
- **`clients_agree_on_version`** — post-publish, and one-sided even then — there is no weekly frontend yet; it is the next story
- **`universe_count`** — no previous weekly universe exists; nothing weekly has ever served, and inventing a baseline would fake the comparison
- **`scoring_parity`** — not applicable: the weekly point and the weekly component line come from INDEPENDENT heads, so the point is not derived from the line. See `component_coherence` for the question that IS answerable

## The ten gates

| gate | status | detail |
|---|---|---|
| model_stamp_consistency | PASS | artifact stamp agrees with the registry on 1 lineage field(s) |
| projection_source_consistency | PASS | payload lineage agrees with the registry (model_version=None, projection_source='nf_w1_weekly') |
| universe_count | UNEVALUABLE | universe counts unavailable on one or both sides |
| rookie_coverage | PASS | 95 rookie(s), unchanged |
| interval_floors | PASS | all per-group coverage floors met after the change (floor rule: NF-D22 power-derived exact one-sided Binomial acceptance bound) |
| scoring_parity | UNEVALUABLE | no scoring-parity measurement supplied |
| track_record_copy_compatible | PASS | copy carries no forbidden market/edge claim |
| rollback_artifact_exists | PASS | rollback artifact present at repo:quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_w1_weekly_bakeoff.json |
| live_payload_matches_staged | UNEVALUABLE | one side has no digest (pre-publish, or the live read failed) — cannot claim the live payload matches what was reviewed |
| clients_agree_on_version | UNEVALUABLE | neither client version could be read |

### Supplementary lineage reconciliation (beyond the shared gate)

`model_stamp_consistency` reconciles six lineage fields, of which this family populates exactly one
(`served_version`) — the others name a level model, an ordering model and a rookie leg the weekly
stack does not have. The gate refuses an EMPTY intersection but not a THIN one, so the weekly's own
fields are reconciled here instead. ⛔ The shared gate is deliberately NOT extended: it is a
cross-vertical instrument, and changing it means sweeping every guard that pins its output (MH2.7).

```json
{
  "evaluable": true,
  "checked": [
    "served_version",
    "base_model_version",
    "point_model_version",
    "interval_model_version"
  ],
  "mismatches": [],
  "pass": true
}
```

## Interval floors, re-read against the floor NOW IN FORCE

NF-D22 replaced the hard point-estimate floor at nominal — whose false-reject rate against a
*perfectly calibrated* band is 0.393–0.500 at every n — with the exact one-sided Binomial acceptance
bound at a pre-registered false-reject target. `power_floor` takes no coverage argument, so it
cannot be reverse-engineered from the value it judges.

| position | coverage(80) | power floor | n | margin (rows) | |
|---|---|---|---|---|---|
| QB | 0.8173 | 0.7911 | 5485 | +144 | ✅ |
| RB | 0.8494 | 0.7929 | 8591 | +485 | ✅ |
| TE | 0.8827 | 0.7924 | 7649 | +691 | ✅ |
| WR | 0.8523 | 0.7942 | 12827 | +745 | ✅ |

⚠️ `interval_floors`' own population loop scans `rookies`/`veterans`/`kdst` and this family is
per-POSITION, so it read **0** populations. The misses handed
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
{
  "evaluable": true,
  "n": 503,
  "mean_signed_diff": -0.7709,
  "median_abs_diff": 0.6016,
  "p95_abs_diff": 3.7101,
  "max_abs_diff": 7.9164,
  "interpretation": "the points distribution and the component head are INDEPENDENT models; this is a coherence diagnostic, never a parity gate"
}
```

## Promoted here: nothing. Staged: one.

- **`nfl_fantasy_w2b_v1`** — weekly injury-rate arm — its own notes require a LIVE stamped injury forward-capture and pre-flip snapshots beyond this story; stays CHALLENGER
- **`nfl_fantasy_w6c_v1`** — per-stat distributions (a different target) — blocked on the DEFERRED re-scoring consumer; nothing here reads them; stays CHALLENGER
- **`nfl_fantasy_w6d_v1`** — as w6c; stays CHALLENGER

Promotion is not a rubber stamp for the whole shelf: a staged cell with no consumer stays a
challenger. This review covers exactly what the weekly serving path serves.

## Staged artifact

```json
{
  "manifest_present": true,
  "season": 2026,
  "week": 1,
  "n_players": 503,
  "staged_digest": "48954c1bfc0c18791cb4d9cae35eef78a9dc41933fad94701e4eceb6befb0c23"
}
```
