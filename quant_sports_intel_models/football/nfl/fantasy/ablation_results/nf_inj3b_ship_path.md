# NF-INJ3b — the LEVEL-ADJACENT gated ship path (preregistration §5)

_generated 2026-08-23T05:48:04.827495+00:00_ · `best_alpha = 0` · **DEPLOY-HELD**, served arm `incumbent`

## Verdict: **SHIP_PATH_INCOMPLETE — step (d) is unrun and BLOCKING**

NF-INJ3b cleared all nine registered gates. **A cleared §0.5 gate is not a deploy.** The arm changes `proj_games` and MVP-1's served point is `rate × games`, so the change is LEVEL-ADJACENT and must clear the whole-board machinery first. Two of the four steps run here and pass; one is carried; **one is unrun and BLOCKING** — and it is named rather than quietly omitted (NF1.7 (a): a check that did not run is not a pass).

| step | status | result |
|---|---|---|
| (a) whole-board cross-position placement read (published artifact) | RUN | **SANE** — {'band_integrity': 'PASS', 'within_position_order': 'PASS', 'rookie_placement_cap': 'PASS', 'position_survival': 'PASS'} |
| (b) `run_interval_revalidation` (every shipped 80% band vs its floor) | RUN | **ALL FLOORS MET** (exit 0) |
| (c) NF-TR2b superflex caveat | CARRIED | see below |
| (d) served-POINT impact, MEASURED | **NOT_RUN_BLOCKING** | ⛔ blocking |

## (a) Placement read — the PUBLISHED board, as a BASELINE

Read from `s3://credence-prod-s3-api-cache/fantasy/nfl/2026/` (`s3`), served level model `nfl_fantasy_nf_tr2b_veteran_level_v1`, board built 2026-08-22T20:36:26.627701+00:00. Configs read: 14; absent: none.

Verdict **SANE**, gates `{'band_integrity': 'PASS', 'within_position_order': 'PASS', 'rookie_placement_cap': 'PASS', 'position_survival': 'PASS'}`.

⚠️ ⚠️ this is a BASELINE on the board AS PUBLISHED — it establishes that the served board is placement-clean TODAY. It is NOT the counterfactual read: the decision-relevant comparison (published board vs a board rebuilt on the NF-INJ3b caps) is blocked on the same rebuild step (d) is blocked on.

## (b) Interval re-validation

**✅ ALL FLOORS MET** (exit 0). a floor breach is a RE-SELECTION trigger for that population, never a reason to move the floor (E2.1-r / NF1.8 §1)

| population | form | n | pooled coverage |
|---|---|---|---|
| rookies | qreg_sqrt | 553 | 0.83 |
| veterans | knn_norm | 8398 | 0.8897 |
| kdst | empirical_ratio_band | 795 | 0.8566 |

⛔ The decided NF1.9 artifact was byte-RESTORED after this run (`decided_artifact_restored: True`) — `--no-report` still rewrites its JSON, and a post-decision story never clobbers a decided story's record.

## (c) The NF-TR2b superflex caveat — CARRIED

NF-TR2b: the VOR 'shield' — NF-W8-0's finding that a per-group level shift CANCELS in VOR space because a group's own replacement level absorbs it — is **ADDITIVE-ONLY**, and it additionally assumes the group is not cross-pooled. Two published configs are SUPERFLEX (`superflex_10`, `superflex_12`), where QB IS cross-pooled with RB/WR/TE, so the shield does NOT hold there. A cap change moves `proj_games` for flagged veterans at every position, so the superflex configs must be read on their own placement rows, never inferred from the non-superflex ones.

## (d) ⛔ The served-POINT impact — UNRUN and BLOCKING

the served POINT is not recoverable from the games change: NF1.5 PERMUTES the within-position point multiset and rescales the stat line to the new point, so a games change alters the multiset the permutation re-assigns (NF-INJ1 measured that step handing +36.4% of an availability discount BACK). It requires a counterfactual board REBUILD on the NF-INJ3b caps, which additionally needs a SERVED artifact for the fitted hurdle that this deploy-held study deliberately does not create.

⛔ NO proportional estimate is published in its place. `pts × arm_games / incumbent_games` is exactly the assumption preregistration §5 (d) forbids, and publishing it would read as a measurement.

**Operator step:** rebuild the 2026 board with the NF-INJ3b caps, DRY-RUN (no --publish), and diff the staged board against the published one on `pts`, `proj_games`, overall rank and per-config placement.

## What this means for the decision

Every step that COULD run has run and passed (`executable_steps_pass: True`). The ship path is nevertheless **INCOMPLETE**, so nothing serves and `SERVED_ARM` stays `"incumbent"`. OPERATOR — ship/no-ship is not this harness's call, and it cannot be taken until (d) is measured.
