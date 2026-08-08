# NF-G0+D21 — shared model/publish governance, and NF-D16 at λ=0.5 routed through it

_generated 2026-08-05T01:45:46.930989+00:00_ · `best_alpha = 0`

> ✅ **RE-CONFIRMED BY NF-C3-REREAD (2026-08-08, `ablation_results/nf_c3_reread.md`) — this refusal
> STANDS on a correctly-measured gate.** After NF1.9-R exposed the veteran panel's `served_p10/p90`
> trap, this gate was re-read: its band is the ROOKIE band refit through the rookie model path
> (`shipped_rookie_cfg()` — never a `served_*` panel column; the recorded λ-sweep reproduces
> row-for-row), and under the corrected C3 structure (`coverage_λ ≥ min(0.80, coverage_λ=0)`, with
> λ=0 RB = 0.8041 ≥ 0.80) the clause reduces to the bare floor already applied here — λ=0.5 RB is
> still 0.7905, 2 covered rows short. CONSTRAINT_REFUSED, unchanged; NF-D21 stays CLOSED; the
> remedy remains NF-D22 / PM judgment — never more data, never a moved floor.

## Verdict: PUBLISH BLOCKED BY THE INTERVAL-FLOOR GATE

Phase A is complete and proven. Phase B was BUILT, STAMPED and ROUTED through the pipeline, and **the pipeline refused it** — the `interval_floors` gate fails because the rookie RB 80% coverage floor falls 2 covered rows short at λ = 0.5 (n = 148). Nothing is published; `SERVING_ENABLED` stays `False`, so the served board is the incumbent, byte-for-byte, and users see exactly the projection they had. λ was NOT moved and the floor was NOT moved — both are prohibited (see §4). ⭐ The first real artifact through the governance pipeline being REFUSED by a gate is a stronger validation of Phase A than a clean pass would have been.

## 0. PM DECISION — the answer to the refusal below

**CONSTRAINT_REFUSED** · decided 2026-08-05 · Charlie (operator/PM)

> Held at incumbent: the rookie-RB interval-floor breach is a coin-flip at n=148 (a perfectly calibrated band fails this floor 50% of the time), so the honest remedy is a power-derived floor for structurally-thin groups — carded independently — not moving λ or the floor. NF-D16's lift is deferred, not abandoned.

NF-D21 is **CLOSED, not parked** (`DISPOSITION_IS_NOT_PENDING = True`). The PM named the reason and it is load-bearing: a story left open pending a floor fix is exactly the pressure that would bias that floor toward clearing λ=0.5. ⛔ The rejected remedy — re-select the rookie band at the λ=0.5 centre (NF1.8-style §0.5 bake-off) — is a LAST RESORT only if `NF-D22` lands and a breach still stands; never a now-choice.

Follow-on `NF-D22` (a power-derived fallback floor for structurally-thin groups) is a SEPARATE, POST-LAUNCH story. ⛔ It must be derived from **n and a pre-stated false-reject target ONLY — zero reference to the 0.7905 measured in §4** — applied to ALL thin groups, with NF-D21 explicitly out of scope. Re-gating NF-D21 against whatever floor it produces is a downstream consequence, never that story's motivation.

## 1. The decision being recorded

- λ = **0.5**, `selection_status = PM_JUDGMENT`, `statistically_selected = False`
- source model **NF-D16**, decision story **NF-D21**, decided 2026-08-04
- recalibrated positions ['RB', 'TE', 'WR']; excluded ['QB']

λ = 0.5 is the MIDPOINT of the shrink family's declared interval — a number available before any result existed. It was not selected, ranked, or fitted. NF-D20's numbers are the evidence base for the decision, not a selection that produced it.

## 2. Board effects (the served NF1.5 board and the MVP-1 level board)

| board | players | rookies | best rookie rank λ=0 → λ=0.5 | who | placement constraint | QB max &#124;Δpoint&#124; | veteran max &#124;Δpoint&#124; |
|---|---|---|---|---|---|---|---|
| served (NF1.5 ordering) | 784 | 81 | 12 → 12 | Fernando Mendoza (QB) | INACTIVE (best rookie is a QB) | 0 | 0 |
| level (MVP-1) | 784 | 81 | 12 → 12 | Fernando Mendoza (QB) | INACTIVE (best rookie is a QB) | 0 | 0 |

Within-position rank movement on the served board — **FB 0/17**, **QB 0/105**, **RB 64/177**, **TE 75/169**, **WR 150/316**.

⚠️ Read the QB row correctly. QB projections move by **0.0** and QB's WITHIN-position order is untouched, but 78 QBs change OVERALL rank because lifted RB/TE/WR rookies pass them. That is arithmetic, not a policy breach — NF-D16 (g‴) records it as the reason a 'moves no ranks' claim is a WITHIN-position claim only.

## 3. Free preview (top-10 overall / top-3 per position)

- top-10 overall **unchanged** (order included)
- top-3 QB: unchanged
- top-3 RB: **changed** — ['BIJAN ROBINSON', 'CHRISTIAN MCCAFFREY', 'Jeremiyah Love']
- top-3 TE: unchanged
- top-3 WR: unchanged
- slice well-formed (exactly 10 / exactly 3): **True**

The gate is that the preview is CORRECT, not that it is frozen: it is a slice of the served board, so a board change may legitimately change its membership.

## 4. Interval floors after the level shift — THE BLOCKING GATE

| λ | pooled cov | IS80 | QB cov (slack rows) | RB cov (slack rows) | TE cov (slack rows) | WR cov (slack rows) | verdict |
|---|---|---|---|---|---|---|---|
| 0.0 | 0.8354 | 183.407 | 0.8148 (1) | 0.8041 (0) | 0.9000 (10) | 0.8348 (7) | ✅ |
| 0.25 | 0.8336 | 183.911 | 0.8025 (0) | 0.8041 (0) | 0.9000 (10) | 0.8348 (7) | ✅ |
| 0.5 | 0.8300 | 184.534 | 0.8025 (0) | 0.7905 (-2) | 0.9000 (10) | 0.8348 (7) | 🚨 RB 0.7905<0.800 |
| 0.75 | 0.8354 | 184.119 | 0.8148 (1) | 0.8041 (0) | 0.9000 (10) | 0.8348 (7) | ✅ |
| 1.0 | 0.8391 | 184.048 | 0.8148 (1) | 0.8041 (0) | 0.9200 (12) | 0.8348 (7) | ✅ |

Rookie **RB** carries n = 148 held-out seasons and the 0.80 floor requires 119 covered rows. λ = 0.5 delivers 2 fewer. It is the only point on NF-D16's own grid that misses, and the miss is not monotone in λ.

⚠️ **The gate's own noise floor, measured:** a PERFECTLY-calibrated band fails this floor with probability **0.5** at n = 148. That is the design property NF1.8 recorded (and why it flagged rookie RB as the position a future class breaks first — it shipped with ZERO rows of slack). It does not license ignoring the breach; it is the context a PM needs to weigh one.

⛔ **Neither obvious remedy is admissible, and both are worth naming:**

1. **Move λ.** That is selecting the shrink on the CONSTRAINT'S OWN HEADROOM — NF1.8's explicit prohibition — and the nearest passing grid value is **0.75**, precisely the board-fitted frontier NF-D18/NF-D20 ruled un-publishable. The trap closes on itself.
2. **Move the floor.** E2.1-r's cardinal error. A floor that moves until something clears it is not a floor; `run_interval_revalidation` exits non-zero so a breach is a RE-SELECTION trigger, not a log line.

## 5. Governance gates (the ten NF-G0 requires)

| gate | status | detail |
|---|---|---|
| `model_stamp_consistency` | PASS | artifact stamp agrees with the registry on 6 lineage field(s) |
| `projection_source_consistency` | PASS | payload lineage agrees with the registry (model_version='nfl_fantasy_nf1_5_v1', projection_source='nf1_5') |
| `universe_count` | PASS | universe 784 → 784 (0.00% drift, within 2%) |
| `rookie_coverage` | PASS | 81 rookie(s), unchanged |
| `interval_floors` | FAIL | coverage floor BREACH — re-run that population's bake-off, do NOT move the floor. Breaches: ['rookies:RB 0.7905<0.800'] |
| `scoring_parity` | PASS | scored line reproduces the displayed point (max |Δ| 0 over 81 row(s)) |
| `track_record_copy_compatible` | PASS | copy carries no forbidden market/edge claim |
| `rollback_artifact_exists` | PASS | rollback artifact present at s3://credence-prod-s3-api-cache/fantasy/nfl/2026/ |
| `live_payload_matches_staged` | UNEVALUABLE | one side has no digest (pre-publish, or the live read failed) — cannot claim the live payload matches what was reviewed |
| `clients_agree_on_version` | UNEVALUABLE | neither client version could be read |

`ready_to_promote` = **False**. The two post-publish gates are UNEVALUABLE by design pre-publish (`POST_PUBLISH_GATE_NAMES`); every other gate must resolve, and UNEVALUABLE never counts as a pass.

Scoring parity: the recalibrated board's displayed point equals the score of its own stat line to **0** over 81 rookie rows. Reported beside it, and NOT a gate: the emitted point lands **0.0218** PPR from the raw affine target — the pre-existing 2-dp fumble rounding `project_rookies` has always had (NF-D16 measured 0.032 PPR from the same cause at λ=1).

## 6. Rollback — proven byte-for-byte

- artifact digests: incumbent `8b807b21a8f0…` → published `10bced358e99…` → after rollback `8b807b21a8f0…`
- **byte-for-byte restore: True**
- registry served version after rollback: `nfl_fantasy_nf1_5_v1`
- λ=0 folds to the identity affine per position ({'RB': [0.0, 1.0], 'TE': [0.0, 1.0], 'WR': [0.0, 1.0]}) ⇒ rookie-point max |Δ| vs the incumbent = **0**

## 7. Wiring proofs

- param_shrink_equals_output_blend[served (NF1.5 ordering)]: `2.84e-14`
- param_shrink_equals_output_blend[level (MVP-1)]: `2.84e-14`

