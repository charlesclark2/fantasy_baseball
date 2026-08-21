# NF-D22 — a power-derived coverage floor for structurally-thin groups

**Generated:** 2026-08-21T01:52:13.618397+00:00 · **verdict: ✅ FLOOR INSTALLED — and NF-D16 at λ=0.5 now CLEARS the interval-floor gate**

> ⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · a projection-QUALITY gate. No market, edge, CLV or ROI claim is made or implied. Nothing in this run flips a serving switch: `rookie_publish_policy.SERVING_ENABLED` is untouched and stays `False`.

The power-derived floor is derived from design quantities alone (§1) and satisfies both halves of its validation (§2). Installing it, NF-D16's rookie recalibration at λ = 0.5 clears every per-group coverage floor and every one of the ten NF-G0 gates — under the previous hard point-estimate rule it did not (`pass_at_nominal_floor = False`). ⛔ **That is a CONSEQUENCE, not this story's motivation, and it publishes nothing.** NF-D21 stays CLOSED with disposition `CONSTRAINT_REFUSED`; a publish needs a NEW PM disposition recorded against the floor now in force, and `SERVING_ENABLED` is untouched at `False`.

## 1. The floor — derived from DESIGN QUANTITIES ONLY

Every number in this section is a function of a group's held-out row count, the nominal coverage the band was built for, and a **pre-registered false-reject target**. Nothing else reaches it: `coverage_power_floor.power_floor` takes no coverage argument, and a guard asserts its signature never gains one. **This whole table could have been published before any band was ever scored** — which is the property that makes it a floor rather than a number reverse-engineered from something that failed (E2.1-r).

**The target is not a new number.** NF1.8's pre-registered Tier-2 fallback level: `_TIER2_Z = 1.6448536269514722 = Φ⁻¹(0.95)`, i.e. a ONE-SIDED 95% test ⇒ a 0.05 false-reject target. Recorded in `run_rookie_perposition_ablation` before any of the results this floor is now read against existed. NF-D22 widens its SCOPE and makes it EXACT; it does not move the level.

|    n |   floor (NF-D22) |   covered rows required |   …at the nominal floor |   relaxation (rows) |   P(reject | truly nominal) |   …under the previous rule |   normal-approx floor (NF1.8 form) |   approx. rate error |   detectable shortfall | thin?   |
|-----:|-----------------:|------------------------:|------------------------:|--------------------:|----------------------------:|---------------------------:|-----------------------------------:|---------------------:|-----------------------:|:--------|
|   30 |           0.6667 |                      20 |                      24 |                   4 |                      0.0256 |                     0.3930 |                             0.6799 |               0.0111 |                 0.5735 | True    |
|   50 |           0.7000 |                      35 |                      40 |                   5 |                      0.0308 |                     0.4164 |                             0.7070 |               0.0107 |                 0.6320 | True    |
|   81 |           0.7284 |                      59 |                      65 |                   6 |                      0.0443 |                     0.4558 |                             0.7269 |              -0.0057 |                 0.6780 | True    |
|  100 |           0.7300 |                      73 |                      80 |                   7 |                      0.0342 |                     0.4405 |                             0.7342 |               0.0058 |                 0.6855 | True    |
|  148 |           0.7432 |                     110 |                     119 |                   9 |                      0.0369 |                     0.5000 |                             0.7459 |               0.0054 |                 0.7080 | True    |
|  200 |           0.7550 |                     151 |                     160 |                   9 |                      0.0494 |                     0.4578 |                             0.7535 |              -0.0006 |                 0.7255 | True    |
|  400 |           0.7675 |                     307 |                     320 |                  13 |                      0.0478 |                     0.4701 |                             0.7671 |              -0.0022 |                 0.7475 | True    |
| 1000 |           0.7790 |                     779 |                     800 |                  21 |                      0.0459 |                     0.4811 |                             0.7792 |               0.0039 |                 0.7670 | True    |
| 3000 |           0.7880 |                    2364 |                    2400 |                  36 |                      0.0486 |                     0.4891 |                             0.7880 |              -0.0014 |                 0.7810 | True    |
| 6000 |           0.7915 |                    4749 |                    4800 |                  51 |                      0.0488 |                     0.4923 |                             0.7915 |              -0.0012 |                 0.7865 | True    |

⭐ **The rule being replaced rejects a perfectly-calibrated band 0.393–0.500 of the time — at EVERY size.** That is the defect: not that the floor is strict, but that its refusals carry almost no information while still reading as evidence. Under the new rule the worst observed false-reject rate across the same range is **0.0494**, against a target of 0.05.

⭐ **No thin-group list exists, and that is deliberate.** The floor self-attenuates, converging to nominal as the group grows (`True`: at the largest reference size it sits within 1pp of nominal), so nothing has to decide where to stop applying it. ⚠️ Attenuation is an **envelope, not pointwise monotonicity** — the requirement is an integer count, so discreteness makes the floor locally jagged; what is stable is `(nominal − floor)·√n`, measured here at 0.64–0.73 across three orders of magnitude. Asserting monotonicity would have been a claim the arithmetic does not support. Under the pre-registered target every size this program has is 'thin' by the only knob-free criterion available — the calibrated floor sits more than one covered row below the nominal one (`True`) — so 'uniformly to all thin groups' and 'uniformly to every constrained group' are the same set. A boundary would have been a degree of freedom someone chose; there is none.

⚠️ **`approx. rate error`** is why the exact Binomial form gates rather than NF1.8's normal approximation `nominal − 1.645·SE`: a positive value means that approximation rejects a truly-nominal band MORE often than the rate it advertises. NF-D22 keeps NF1.8's LEVEL and fixes its FORM.

### 1b. The same rule on the VETERAN population — the 'uniformly' half

Veteran per-position n is ~20× the rookie equivalent, so the calibrated floor sits within ~1pp of nominal there. The rule is identical; its EFFECT scales with 1/√n, which is why no thin-group boundary had to be drawn.

|    n |   floor |   relaxation (rows) |   relaxation (pp) |   P(reject | truly nominal) |
|-----:|--------:|--------------------:|------------------:|----------------------------:|
|  400 |  0.7675 |                  13 |            3.2500 |                      0.0478 |
| 1000 |  0.7790 |                  21 |            2.1000 |                      0.0459 |
| 2000 |  0.7850 |                  30 |            1.5000 |                      0.0451 |
| 4000 |  0.7895 |                  42 |            1.0500 |                      0.0472 |
| 6000 |  0.7915 |                  51 |            0.8500 |                      0.0488 |

## 2. The two-sided validation

⭐ **A one-sided check would be vacuous, and it is the obvious way to get this wrong.** 'A correct band passes' is satisfied perfectly by a floor of 0.0; 'a broken band fails' is satisfied perfectly by a floor of 1.0. Only both together say anything — and the second half is what stops this story from being a floor-removal wearing a floor's badge. Both are exact Binomial computations, so neither rests on a simulation seed.

|         n |   floor |   P(pass | truly nominal) |   target P(pass) |   P(pass | true cov 0.800) |   P(pass | true cov 0.775) |   P(pass | true cov 0.750) |   P(pass | true cov 0.725) |   P(pass | true cov 0.700) |   P(pass | true cov 0.650) |   P(pass | true cov 0.600) |
|----------:|--------:|--------------------------:|-----------------:|---------------------------:|---------------------------:|---------------------------:|---------------------------:|---------------------------:|---------------------------:|---------------------------:|
|   30.0000 |  0.6667 |                    0.9744 |           0.9500 |                     0.9744 |                     0.9440 |                     0.8943 |                     0.8226 |                     0.7304 |                     0.5078 |                     0.2915 |
|   50.0000 |  0.7000 |                    0.9692 |           0.9500 |                     0.9692 |                     0.9212 |                     0.8369 |                     0.7157 |                     0.5692 |                     0.2801 |                     0.0955 |
|   81.0000 |  0.7284 |                    0.9557 |           0.9500 |                     0.9557 |                     0.8712 |                     0.7228 |                     0.5298 |                     0.3362 |                     0.0846 |                     0.0111 |
|  100.0000 |  0.7300 |                    0.9658 |           0.9500 |                     0.9658 |                     0.8829 |                     0.7224 |                     0.5067 |                     0.2964 |                     0.0558 |                     0.0046 |
|  148.0000 |  0.7432 |                    0.9631 |           0.9500 |                     0.9631 |                     0.8469 |                     0.6176 |                     0.3471 |                     0.1446 |                     0.0097 |                     0.0002 |
|  200.0000 |  0.7550 |                    0.9506 |           0.9500 |                     0.9506 |                     0.7789 |                     0.4729 |                     0.1927 |                     0.0506 |                     0.0009 |                     0.0000 |
|  400.0000 |  0.7675 |                    0.9522 |           0.9500 |                     0.9522 |                     0.6657 |                     0.2277 |                     0.0307 |                     0.0016 |                     0.0000 |                     0.0000 |
| 1000.0000 |  0.7790 |                    0.9541 |           0.9500 |                     0.9541 |                     0.3980 |                     0.0177 |                     0.0001 |                     0.0000 |                     0.0000 |                     0.0000 |
| 3000.0000 |  0.7880 |                    0.9514 |           0.9500 |                     0.9514 |                     0.0454 |                     0.0000 |                     0.0000 |                     0.0000 |                     0.0000 |                     0.0000 |
| 6000.0000 |  0.7915 |                    0.9512 |           0.9500 |                     0.9512 |                     0.0011 |                     0.0000 |                     0.0000 |                     0.0000 |                     0.0000 |                     0.0000 |

**Verdict: ✅ BOTH HALVES HOLD AT EVERY REFERENCE SIZE** — a truly-nominal band clears at or above the pre-registered rate, and a materially-short band still fails. Exact Binomial throughout — both halves are closed-form, so neither rests on a simulation seed. `detectable_shortfall` is the floor's RESOLUTION: a ✅ means 'not shown to be broken at this n', never 'shown to be right' (NF1.7 (a)).

## 3. The consequence — NF-D16's λ sweep under the floor in force

⚠️ **READ THIS SECTION AFTER §1 AND §2, WHICH IS THE ORDER IT WAS COMPUTED IN.** The floor above exists independently of everything below; this section reports what installing it implies for a band that was already scored. Reversing that order is exactly the E2.1-r inversion this story is most exposed to.

⛔ **The sweep is DIAGNOSIS, not a menu** (NF-D21's words, unchanged). λ is fixed by PM judgment; re-picking it because a neighbour has more headroom would be selecting on the constraint's own headroom, which NF1.8 prohibits outright.

|      λ |   pooled cov |     IS80 |   cov QB |   cov RB |   cov TE |   cov WR |   slack QB (rows) |   slack RB (rows) |   slack TE (rows) |   slack WR (rows) | verdict (NF-D22)   | verdict (previous rule)   |
|-------:|-------------:|---------:|---------:|---------:|---------:|---------:|------------------:|------------------:|------------------:|------------------:|:-------------------|:--------------------------|
| 0.0000 |       0.8354 | 183.4070 |   0.8148 |   0.8041 |   0.9000 |   0.8348 |                 7 |                 9 |                17 |                18 | ✅ met             | ✅ met                    |
| 0.2500 |       0.8336 | 183.9110 |   0.8025 |   0.8041 |   0.9000 |   0.8348 |                 6 |                 9 |                17 |                18 | ✅ met             | ✅ met                    |
| 0.5000 |       0.8300 | 184.5340 |   0.8025 |   0.7905 |   0.9000 |   0.8348 |                 6 |                 7 |                17 |                18 | ✅ met             | 🚨 breach                 |
| 0.7500 |       0.8354 | 184.1190 |   0.8148 |   0.8041 |   0.9000 |   0.8348 |                 7 |                 9 |                17 |                18 | ✅ met             | ✅ met                    |
| 1.0000 |       0.8391 | 184.0480 |   0.8148 |   0.8041 |   0.9200 |   0.8348 |                 7 |                 9 |                19 |                18 | ✅ met             | ✅ met                    |

Slack under the PREVIOUS rule, for comparison:

|      λ |   slack QB @nominal (rows) |   slack RB @nominal (rows) |   slack TE @nominal (rows) |   slack WR @nominal (rows) | misses (previous rule)   |
|-------:|---------------------------:|---------------------------:|---------------------------:|---------------------------:|:-------------------------|
| 0.0000 |                          1 |                          0 |                         10 |                          7 | —                        |
| 0.2500 |                          0 |                          0 |                         10 |                          7 | —                        |
| 0.5000 |                          0 |                         -2 |                         10 |                          7 | RB 0.7905<0.800          |
| 0.7500 |                          1 |                          0 |                         10 |                          7 | —                        |
| 1.0000 |                          1 |                          0 |                         12 |                          7 | —                        |

## 4. NF-D16 at λ = 0.5 routed through the ten NF-G0 gates

| gate                          | status      | detail                                                                                                                  |
|:------------------------------|:------------|:------------------------------------------------------------------------------------------------------------------------|
| model_stamp_consistency       | PASS        | artifact stamp agrees with the registry on 6 lineage field(s)                                                           |
| projection_source_consistency | PASS        | payload lineage agrees with the registry (model_version='nfl_fantasy_nf1_5_v1', projection_source='nf1_5')              |
| universe_count                | PASS        | universe 794 → 794 (0.00% drift, within 2%)                                                                             |
| rookie_coverage               | PASS        | 81 rookie(s), unchanged                                                                                                 |
| interval_floors               | PASS        | all per-group coverage floors met after the change (floor rule: nf_d22_exact_binomial_power_floor_v1)                   |
| scoring_parity                | PASS        | scored line reproduces the displayed point (max |Δ| 0 over 81 row(s))                                                   |
| track_record_copy_compatible  | PASS        | copy carries no forbidden market/edge claim                                                                             |
| rollback_artifact_exists      | PASS        | rollback artifact present at s3://credence-prod-s3-api-cache/fantasy/nfl/2026/                                          |
| live_payload_matches_staged   | UNEVALUABLE | one side has no digest (pre-publish, or the live read failed) — cannot claim the live payload matches what was reviewed |
| clients_agree_on_version      | UNEVALUABLE | neither client version could be read                                                                                    |

`ready_to_promote`: **True**

## 5. What this does NOT do

- ⛔ **It does not publish, and it does not flip a serving switch.** `rookie_publish_policy.SERVING_ENABLED` is `False` and this run does not touch it. NF-D21 is a **CLOSED** story with disposition `CONSTRAINT_REFUSED` and `DISPOSITION_IS_NOT_PENDING = True`; a publish requires a NEW PM disposition recorded against the floor now in force. That re-decision is the PM's, and `rookie_publish_policy.assert_coherent()` refuses the incoherent in-between state (serving while the disposition still reads a refusal) at import.
- ⛔ **It does not touch the §0.5 SELECTION floor.** `position_floors` still gates bake-off eligibility at the hard nominal level, and NF1.8's guards are unedited and green. Relaxing eligibility inside searches that are already recorded would re-decide them post hoc.
- ⛔ **It does not correct for multiplicity**, deliberately: a Bonferroni split would make every individual floor LOOSER, which is the one adjustment a reader should most distrust from this story. The family false-reject rate is reported beside each population's floors as an honest caveat, and the per-group pre-registered target binds (NF1.8: report both conventions, let the pre-registered one bind).
- ⛔ **It does not make a floor pass mean 'the band is right'.** `detectable_shortfall` is the floor's resolution, published with every verdict: at n = 148 the floor detects a true coverage of ~0.71 or worse at 80% power and cannot resolve anything finer. A ✅ means 'not shown to be broken at this n'.

## 6. A breach under this rule

Still a **RE-SELECTION TRIGGER**, and the floor still may not move (E2.1-r; NF1.8 §1). ⭐ That prohibition binds HARDER now, not less: the false-reject target is NF1.8's own pre-registered level rather than a knob, and a breach under a calibrated rule is genuine evidence instead of a coin toss. `run_interval_revalidation` still exits non-zero on a breach.

