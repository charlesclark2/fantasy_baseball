# NF Delivery Epic
## Credence Fantasy Football 2026 Launch, Weekly Retention, and Decision Systems

**Epic status:** Finalized from PM-settled decisions  
**Business objective:** Monetize the 2026 predraft product, protect paid data at the wire, and transition users into recurring weekly subscriptions  
**Standing constraints:** `best_alpha = 0`, honest analytics, market-aware ordering disclosed, platform-import red line enforced  
**Primary product hook:** Calibrated player distributions, league-specific scoring, and explicit uncertainty  
**Secondary proof point:** The served-style board modestly outperformed the captured ADP benchmark on pooled within-position rank correlation from 2019–2024; results vary by position and season, and the confidence interval includes zero  
**Primary modeling frontier:** Weekly fantasy projections and matchup-aware decision systems  
**Season-model posture:** Current season architecture stands; only narrowly authorized improvements proceed

---

# 1. Epic Outcome

At completion, Credence will have:

1. A secure paid 2026 predraft product whose gated rankings cannot be lifted from the wire by a non-subscriber.
2. A shared model-governance framework aligned with the existing baseball model registry and K-props governance pattern.
3. A published rookie recalibration at fixed `λ=0.5`, explicitly stamped as a PM judgment.
4. A weekly player-distribution model ready before the 2026 NFL regular season.
5. A matchup-aware lineup optimizer that maximizes weekly win probability.
6. Injury and availability infrastructure that refreshes projections and recommendations.
7. Roster-specific waiver recommendations.
8. A compliant ESPN sync decision with an exact GO or NO-GO recipe.
9. Trade utility, search, and eventual acceptance modeling.
10. A tiered entitlement structure supporting Free, Draft, Core, and Pro plans.

---

# 2. Product and Model Principles

## 2.1 Honest-Analytics Rule

Credence must distinguish:

- Calibration.
- Ranking quality.
- Uncertainty quality.
- Product utility.
- Historical benchmark comparison.
- Future user outcomes.

Credence must never claim:

- “Beats ADP/ECR.”
- “Guaranteed to win your league.”
- “Most accurate” without a tightly bounded methodology.
- A statistically selected rookie recalibration when the serving choice is PM judgment.

The claim denylist remains active.

## 2.2 Primary Product Hook

Lead with:

- League-specific scoring.
- Calibrated season and weekly distributions.
- 80% uncertainty intervals.
- Transparent model drivers.
- Matchup-aware decisions.
- Injury-responsive updates.

The ADP comparison is secondary and caveated.

## 2.3 Model-Tier Definitions

| Tier | Meaning |
|---|---|
| **T0 — Governance / Data Contract** | Registry, versioning, entitlements, serving controls, parity, and validation infrastructure |
| **T1 — Production Foundation Model** | Existing served season model and authorized narrow improvements |
| **T2 — Retention Model** | Weekly projections, availability, matchup optimization |
| **T3 — Recommendation Model** | Waiver, trade utility, trade search |
| **T4 — Learning / Proprietary Moat** | Trade acceptance, user behavior, outcome learning |

## 2.4 Delivery-Class Definitions

| Tag | Meaning |
|---|---|
| **LAUNCH-GATING** | Must complete before the paid launch or before gated data exposure expands |
| **DEADLINE-CRITICAL** | Must complete by the 2026 season-start window |
| **POST-LAUNCH** | May ship after launch without undermining paid access or core weekly retention |
| **PROBE-FIRST** | Begins as feasibility work; implementation requires explicit GO |
| **MODEL-GATED** | Depends on an upstream model or validation gate |
| **EXTERNAL-BLOCKED** | Depends on third-party approval or capability |

---

# 3. Final Sequence

| Seq | Story | Delivery Class | Model Tier | Primary Dependency |
|---:|---|---|---|---|
| 1 | E9.56 + E9.8-P2 + E9.57 Entitlement Enforcement Triad | LAUNCH-GATING | T0 | Existing Stripe and fantasy API |
| 2 | NF-G0 Shared Model and Publish Governance | ✅ DONE 2026-08-04 | T0 | Existing baseball registry pattern |
| 3 | NF-D21 Rookie Recalibration Publish | ✅ CLOSED 2026-08-05 as CONSTRAINT_REFUSED — built, refused by its own interval-floor gate, PM ACCEPTED THE NULL. Nothing published; served board = incumbent; NOT launch-gating | T1 | NF-G0 staging/promotion path |
| 3b | NF-D22 Power-Derived Floor for Thin Interval Groups | ⏳ POST-LAUNCH, NOT launch-gating — the NF-D21 follow-on. ⛔ Nothing is blocked on it (NF-D21 is CLOSED, not parked, precisely so this floor cannot be biased toward clearing λ=0.5) | — | NF1.8's unspecified fallback-floor prescription |
| 4 | NF-TR1 Track-Record and Claim Hardening | LAUNCH-GATING — ✅ UNBLOCKED: it reads the INCUMBENT board (NF-D21 published nothing), so it no longer sequences after NF-D21 | T0 | Settled PM wording |
| 5 | NF-W0 Weekly Data and Label Audit | DEADLINE-CRITICAL | T2 | Lakehouse and weekly feature marts |
| 6 | NF-W1 Weekly Projection Champion | DEADLINE-CRITICAL | T2 | NF-W0 |
| 7 | NF-W2 Matchup-Aware Lineup Optimizer | DEADLINE-CRITICAL / MODEL-GATED | T2 | NF-W1 |
| 8 | NF-C6P2 Post-Draft Roster Report | DEADLINE-CRITICAL but SLIPPABLE | T2 | Season model; ideally NF-W1 |
| 9 | NF-I0 Injury NLP and Availability Architecture | POST-LAUNCH / DEADLINE-SENSITIVE | T2 | Source and evidence contracts |
| 10 | NF-C4 Waiver Recommender | POST-LAUNCH / MODEL-GATED | T3 | NF-W1 + NF-I0 |
| 11 | NF-C0-ESPN Compliant Sync Spike | PROBE-FIRST | T0 | Policy/security review |
| 12 | NF-C3 Trade Utility and Search V1 | POST-LAUNCH | T3 | Season/weekly utility model |
| 13 | NF-C3A Trade Acceptance Learning | POST-LAUNCH / DATA-GATED | T4 | Outcome labels from V1 |
| 14 | NF-P1 Playoff and Multi-League Planning | POST-LAUNCH | T3 | Weekly and ROS models |
| 15 | NF-X1 Commissioner / Creator Expansion | POST-LAUNCH | T0/T3 | Stable core product |

---

# 4. New Sequencing Conflict

## 4.1 Conflict

The settled roadmap creates a direct pre-season competition between:

### Launch-security path

- Server-side entitlement filtering.
- Stripe production activation.
- End-to-end entitlement verification.
- Shared registry and publish governance.
- Rookie recalibration publication.
- Track-record copy hardening.

### Recurring-revenue path

- Weekly data audit.
- Weekly model.
- Matchup-aware optimizer.

Both paths require completion before or near season start.

## 4.2 Risk

If the team executes strictly sequentially:

```text
entitlement
→ governance
→ rookie publish
→ track record
→ weekly model
→ optimizer
```

the weekly system may miss the season-start deadline.

If the team prioritizes weekly modeling first, paid 2026 values may be insufficiently protected or published under weak governance.

## 4.3 Resolution

Run two parallel workstreams.

### Workstream A — Launch Protection

```text
E9.56
E9.8-P2
E9.57
NF-G0
NF-D21
NF-TR1
```

### Workstream B — Weekly Critical Path

```text
NF-W0
NF-W1
NF-W2
```

These workstreams may share platform and QA resources, so PM capacity planning must explicitly reserve:

- One owner for entitlement/governance.
- One owner for weekly data/modeling.
- Shared QA windows.
- A fixed integration freeze before season start.

## 4.4 Slip Rule

If capacity compresses:

1. Entitlement enforcement cannot slip.
2. Weekly projections cannot slip beyond the season-start window.
3. Matchup optimizer may launch shortly after weekly projections if necessary.
4. Post-draft roster report slips before either entitlement or weekly projections.
5. Trade, waiver, and ESPN expansion do not consume deadline-critical capacity.

---

# 5. Story 1 — Entitlement Enforcement Triad

## Story ID

`E9.56 + E9.8-P2 + E9.57`

## Sequence

`1`

## Tags

`LAUNCH-GATING` · `T0` · `SECURITY` · `ANTI-SCRAPE`

## Objective

Ensure a non-subscriber cannot obtain the full 2026 projection board from any API payload, static asset, server response, cache, or frontend bundle.

## Settled Entitlements

### Free

```text
connected_leagues_max = 2
preview_active_leagues_max = 1
overall_values_visible = top 10
per_position_values_visible = top 3
player_detail_unlocks = 3
draft_optimizer_runs = 1
```

### Draft

```text
active_leagues_max = 5
full_predraft_board = true
full_draft_optimizer = true
live_draft_assistant = true
```

### Pro

```text
active_leagues_max >= 10
advanced_simulation = true
multi_league_dashboard = true
```

## Data-Layer Contract

For free/non-subscriber requests:

```json
{
  "playerId": "example",
  "locked": true,
  "rank": null,
  "tier": null,
  "projection": null,
  "p10": null,
  "p90": null,
  "projectedStats": null
}
```

Values are included only for:

- Top 10 overall.
- Top 3 within each position.
- Explicit player-detail unlocks.

## Prohibited Pattern

```text
full board sent
    ↓
frontend hides rows
```

This is a release-blocking defect.

## Acceptance Criteria

- Non-subscriber API response contains no hidden full-board values.
- Static JSON and public assets contain no gated 2026 values.
- Browser dev tools cannot recover gated values.
- Logged-out, free, Draft, and Pro fixtures pass.
- League-count limits are enforced server-side.
- Player unlock count is server-authoritative.
- Draft optimizer call limit is server-authoritative.
- Cache keys include entitlement tier.
- CDN/API caches cannot cross-serve paid data to free users.
- Stripe entitlement propagation passes end-to-end.
- Revoked/canceled subscriptions lose gated access.
- Tests prove top-10/top-3 behavior exactly.

## Trello Card

**Title:** `1 · E9.56/E9.8-P2/E9.57 — Enforce paid fantasy entitlements at the wire`

**Description:**

Implement the full entitlement triad. Free users receive only top-10 overall, top-3 per position, three player unlocks, and one optimizer run. Full 2026 values must never be sent to free users and hidden only in the UI.

**Checklist:**

- [ ] Server-side board filtering
- [ ] Locked marker schema
- [ ] Player unlock state
- [ ] Optimizer usage limit
- [ ] League-count enforcement
- [ ] Stripe production activation
- [ ] Cache partitioning by tier
- [ ] Logged-out/free/Draft/Pro test matrix
- [ ] Network-level anti-scrape verification
- [ ] Cancellation/revocation test
- [ ] PM live proof

---

# 6. Story 2 — Shared Model and Publish Governance

## Story ID

`NF-G0`

## Sequence

`2`

## Tags

`LAUNCH-GATING` · `T0` · `GOVERNANCE`

## Objective

Reuse the established baseball governance pattern rather than create a bespoke fantasy registry.

## Registry Shape

Extend the existing shared governance schema to support:

```yaml
model_family: nfl_fantasy
target: season_projection
served_version: nfl_fantasy_nf1_5_v1
level_model_version: nfl_fantasy_fastpath_v1
ordering_model_version: nfl_fantasy_nf1_5_v1
rookie_model_version: rookie_slot_curve_v1
rookie_selection_status: incumbent
interval_model_version:
  rookie: nf1_8
  veteran: nf1_9
  kdst: nf1_6
scoring_contract_version: nf_c0e
artifact_uri: ...
fallback_artifact_uri: ...
generated_at: ...
published_at: ...
validation_report: ...
promotion_status: served
```

## Promotion Flow

```text
build
→ validate
→ stage
→ PM/operator review
→ promote
→ publish
→ live readback
```

## Required Gates

- Model stamp consistency.
- Projection-source consistency.
- Universe count.
- Rookie coverage.
- Interval floors.
- Scoring parity.
- Track-record copy compatibility.
- Rollback artifact exists.
- Live payload matches staged artifact.
- Frontend and backend consume the same version.

## Acceptance Criteria

- Fantasy and baseball model families share one governance shape.
- Registry supports composite model lineage.
- Build and publish are separate operations.
- Publish defaults to no-op/dry-run.
- Rollback is one documented operator action.
- Live readback verifies version and rookie policy.
- Registry is the named authority for model status.
- Existing artifact stamps remain embedded for reconciliation.

## Trello Card

**Title:** `2 · NF-G0 — Put NFL fantasy on the shared model-governance path`

**Description:**

Extend the established baseball model-registry and K-props governance pattern to NFL fantasy. Separate build, stage, promote, publish, and live verification.

---

# 7. Story 3 — Publish Rookie Recalibration

## Story ID

`NF-D21`

## Sequence

`3`

## Tags

`LAUNCH-GATING` · `T1` · `PM-JUDGMENT`

## Objective

Publish NF-D16 at fixed board-blind `λ=0.5`.

## Required Artifact Stamp

```json
{
  "selection_status": "PM_JUDGMENT",
  "shrink_lambda": 0.5,
  "statistically_selected": false,
  "source_model": "NF-D16",
  "decision_story": "NF-D21"
}
```

## Scope

- Apply to RB/WR/TE rookies.
- QB remains unchanged.
- No claim that `λ=0.5` was selected in-fold.
- No reuse of NF-D20 as a selection result.
- Preserve prior artifact for rollback.

## Required Validation

- Rookie interval revalidation.
- Position-level 80% floors.
- Rookie RB floor.
- Rookie placement check.
- Custom league scoring parity.
- Overall board sanity.
- Artifact diff.
- Live rollback proof.

## Acceptance Criteria

- Fixed shrink is applied exactly once.
- Artifact carries PM-judgment stamp.
- All interval floors pass.
- Placement rule passes.
- Free-preview top-10/top-3 remains correct.
- Live readback proves served version.
- Rollback restores previous rookie points byte-for-byte.

## Trello Card

**Title:** `3 · NF-D21 — Publish half-shrunk rookie recalibration with PM-judgment stamp`

---

# 8. Story 4 — Track-Record and Claim Hardening

## Story ID

`NF-TR1`

## Sequence

`4`

## Tags

`LAUNCH-GATING` · `T0` · `COPY-GOVERNANCE`

## Primary Hook

Lead with:

- Calibrated point levels.
- 80% uncertainty.
- League-specific scoring.
- Transparent model inputs.

## Secondary Claim

Approved language:

> Credence’s served-style board modestly outperformed the captured ADP benchmark on pooled within-position rank correlation from 2019–2024. Results vary by position and season, and the confidence interval includes zero.

## Required Disclosures

- RB is a wash.
- ECR, ESPN, and Sleeper comparisons are separately reported.
- Served ordering uses market consensus.
- ADP comparison is not a guarantee.
- Confidence interval is visible.
- Frozen-board methodology is explained.

## Acceptance Criteria

- `_CLAIM_DENYLIST` remains active.
- No “beats ADP/ECR.”
- Calibration appears before benchmark comparison.
- Track record names the benchmark and metric.
- Player count and seasons are visible.
- Position-level table is available.
- Copy matches served architecture.

## Consumer Readability (operator 2026-08-07 — Charlie)

⭐ **NON-NEGOTIABLE PRODUCT CONSTRAINT: the audience is the AVERAGE fantasy player — keep it LOW-TECH.** Analyst jargon ("pooled within-position rank correlation", "confidence interval includes zero") in the *headline* limits who will use the product. This REFINES the "use the exact wording verbatim" instruction above — the exact sentence is never DELETED, only RELOCATED below a plain lead.

⇒ **TWO-LAYER COPY, both honest:**

1. **CONSUMER LEAD (what a casual user reads first) — plain, everyday English.** Lead with the value ("honest projected points with a range, tuned to your league's scoring"), and state the track record in plain terms WITHOUT overclaiming. Example register (illustrative, not final — the session writes it, the operator approves): *"Over 2019–2024 our board did a little better than where the crowd was drafting — but the edge is small and not a sure thing, and at some spots (like running back) it's basically even."*

2. **PRECISE LAYER (preserved — a "How we measured this" expandable / methodology / fine print).** The EXACT approved sentence + the named benchmark, metric, player count, seasons, and the visible CI live HERE for rigor and claims-integrity.

⛔ **GUARDRAILS UNCHANGED — plain ≠ overclaimed:** the consumer lead must NOT STRENGTHEN the claim. It must still carry the hedge in everyday words (small edge · not guaranteed · varies by position/season · RB a wash), and it must PASS `_CLAIM_DENYLIST`. Translating "the confidence interval includes zero" into "it could just be luck — we're not promising it" is REQUIRED, not optional; dropping the hedge to sound punchier is the exact failure this story exists to prevent. The denylist test (AC #1) applies to the PLAIN-ENGLISH lead too, not only the precise layer.

## Trello Card

**Title:** `4 · NF-TR1 — Make calibration the lead and narrow the ADP claim`

---

# 9. Story 5 — Weekly Data and Label Audit

## Story ID

`NF-W0`

## Sequence

`5`

## Tags

`DEADLINE-CRITICAL` · `T2` · `DATA-AUDIT`

## Objective

Prove that a leak-clean, point-in-time weekly training and serving frame exists before fitting a weekly model.

## Required Audit Areas

- Player-week spine.
- Played/inactive/bye labels.
- Snap, route, target, carry, and red-zone timing.
- Depth-chart timestamp.
- Injury-report timestamp.
- Team and opponent state.
- Weather timestamp.
- Vegas context policy.
- Roster changes.
- Team changes.
- Player identity bridges.
- Scoring settings.
- Stat correction/versioning.
- Week and season boundaries.

## Output

```text
weekly_training_frame_status
weekly_serving_frame_status
point_in_time_safe
train_serve_parity
known_missingness
allowed_feature_contract
deferred_feature_contract
```

## Acceptance Criteria

- Every feature has an as-of timestamp rule.
- No current-week outcome enters prediction.
- Inactive and zero-opportunity outcomes are retained.
- Train/serve parity is tested.
- Weekly labels are versioned.
- Coverage by year/position is reported.
- Model fitting remains blocked until audit passes.

## Trello Card

**Title:** `5 · NF-W0 — Certify the weekly point-in-time training and serving frame`

---

# 10. Story 6 — Weekly Projection Champion

## Story ID

`NF-W1`

## Sequence

`6`

## Tags

`DEADLINE-CRITICAL` · `T2` · `MODEL`

## Objective

Produce weekly player stat and fantasy-point distributions.

## Architecture

```text
season prior
    + recent role
    + snap/route/carry/target state
    + opponent
    + team game environment
    + injury/availability
    + depth chart
    + weather
        ↓
participation distribution
        ↓
opportunity distribution
        ↓
efficiency distribution
        ↓
touchdown distribution
        ↓
joint stat simulation
        ↓
league scoring
```

## Permanent Foils

- Season projection divided by expected games.
- Flat weekly tilt.
- Consensus/ECR benchmark if available point-in-time.
- Position mean.
- Current scoped weekly baseline.

## Required Candidates

1. Parsimonious generalized linear/hierarchical model.
2. Gradient-boosted distributional candidate.
3. Bayesian or empirical-Bayes opportunity model.
4. Position-specific champion.
5. Stacked candidate only from OOF predictions.

## Validation

- Rolling-origin weekly CV.
- Season outer holdouts.
- CRPS primary.
- Interval score.
- P10/P90 coverage.
- PIT.
- MAE secondary.
- Position floors.
- Projection-day segments.
- Injury-status segments.
- Rookie/veteran.
- High/low role certainty.

## Acceptance Criteria

- Beats the flat weekly foil on CRPS.
- Meets interval floors.
- No material season-holdout regression.
- Survives deflation appropriate to candidate count.
- Serves raw stats and fantasy distributions.
- Supports league-specific scoring.
- Includes model version and data timestamp.

## Trello Card

**Title:** `6 · NF-W1 — Ship the weekly player-distribution champion before season start`

---

# 11. Story 7 — Matchup-Aware Lineup Optimizer

## Story ID

`NF-W2`

## Sequence

`7`

## Tags

`DEADLINE-CRITICAL` · `MODEL-GATED` · `T2`

## Dependency

`NF-W1`

## Objective

Maximize:

\[
P(S_{\text{user}}>S_{\text{opponent}})
\]

rather than expected points.

## Architecture

```text
weekly marginal distributions
    + teammate correlation
    + same-game correlation
    + opponent roster
    + players already completed
    + injury uncertainty
    + lineup constraints
    + late-swap rules
        ↓
legal lineup generation
        ↓
joint matchup simulation
        ↓
win probability per lineup
        ↓
recommended lineup
```

## Required Outputs

```text
matchup_state
baseline_win_probability
recommended_win_probability
recommended_lineup
alternative_lineups
mean
floor
ceiling
correlation_effect
late_swap_plan
decision_confidence
```

## Guardrail

No mechanical:

```text
favorite → safe
underdog → boom
```

The recommendation must come from simulated win probability.

## Validation

- Win-probability calibration.
- Regret versus optimal hindsight lineup.
- Comparison with max-mean lineup.
- Favorite/underdog strata.
- Late-swap scenarios.
- Correlation ablations.
- User override and outcome tracking.

## Trello Card

**Title:** `7 · NF-W2 — Optimize weekly lineups for matchup win probability`

---

# 12. Story 8 — Post-Draft Roster Report

## Story ID

`NF-C6P2`

## Sequence

`8`

## Tags

`DEADLINE-CRITICAL` · `SLIPPABLE` · `T2`

## Slip Policy

This story slips behind `NF-W1` and `NF-W2` if the pre-season window compresses.

## Architecture

```text
league settings
    + drafted roster
    + season distributions
    + weekly distributions if available
    + replacement pool
    + bye weeks
        ↓
roster simulation
        ↓
strength / weakness / fragility
        ↓
recommended next actions
```

## Outputs

- Team projection.
- Position strengths.
- Bench quality.
- Bye conflicts.
- Injury concentration.
- Waiver archetypes.
- Trade archetypes.
- First-week lineup.
- Season upgrade prompt.

## Trello Card

**Title:** `8 · NF-C6P2 — Convert completed drafts into season subscriptions`

---

# 13. Story 9 — Injury NLP and Availability

## Story ID

`NF-I0`

## Sequence

`9`

## Tags

`POST-LAUNCH` · `DEADLINE-SENSITIVE` · `T2`

## Architecture

```text
official report
    + team statement
    + trusted reporter
    + practice status
    + transaction
        ↓
NLP extraction
        ↓
entity resolution
        ↓
evidence classification
        ↓
availability posterior
        ↓
workload posterior
        ↓
opportunity reallocation
```

## Guardrail

The NLP layer extracts evidence.

It does not directly assign uncalibrated participation probabilities.

## Acceptance Criteria

- Source is stored.
- Timestamp is stored.
- Evidence confidence is stored.
- Conflicting reports remain visible.
- Availability model is calibrated.
- Projection refresh is versioned.
- Recommendation changes are explainable.

## Trello Card

**Title:** `9 · NF-I0 — Turn injury evidence into calibrated availability updates`

---

# 14. Story 10 — Waiver Recommender

## Story ID

`NF-C4`

## Sequence

`10`

## Tags

`POST-LAUNCH` · `MODEL-GATED` · `T3`

## Architecture

```text
league free agents
    + user roster
    + weekly projection
    + rest-of-season projection
    + position scarcity
    + schedule
    + FAAB budget
        ↓
add/drop simulation
        ↓
roster utility change
        ↓
claim and bid recommendation
```

## Outputs

- Add priority.
- Drop candidate.
- Suggested FAAB.
- Week value.
- ROS value.
- Playoff value.
- Confidence.
- Alternatives.

## Trello Card

**Title:** `10 · NF-C4 — Recommend roster-specific waiver adds and FAAB bids`

---

# 15. Story 11 — ESPN Compliant Sync Spike

## Story ID

`NF-C0-ESPN`

## Sequence

`11`

## Tags

`PROBE-FIRST` · `T0` · `SECURITY` · `POLICY`

## Red Line

Never:

- Capture.
- Store.
- Replay.

a password-equivalent ESPN session cookie.

Encrypting the cookie in KMS does not make it compliant with the settled product red line.

## Probe Order

1. Browser extension normalizing data client-side.
2. Official OAuth or public-read path.
3. User-mediated re-authentication.
4. Improved paste/import flow.
5. Other compliant user-agent-assisted mechanisms.

## Required Memo

```text
GO
or
NO_GO
```

The memo must include:

- Exact mechanism.
- Data flow.
- Credentials observed.
- Credentials stored.
- Robots/ToS review.
- User consent.
- Mobile limitations.
- Operational reliability.
- Security threat model.
- Maintenance burden.

## Acceptance Criteria

- Compliant mechanisms are exhaustively tested.
- No password-equivalent cookie reaches the server.
- Robots and ToS are honored.
- GO includes an exact implementation recipe.
- NO-GO documents attempted paths and why each failed.

## Trello Card

**Title:** `11 · NF-C0-ESPN — Exhaust compliant ESPN sync paths and issue GO/NO-GO`

---

# 16. Story 12 — Trade Utility and Search V1

## Story ID

`NF-C3`

## Sequence

`12`

## Tags

`POST-LAUNCH` · `T3`

## Architecture

```text
user roster utility
    + recipient roster utility
    + replacement value
    + weekly/ROS projections
    + scarcity
    + schedule
        ↓
candidate trade generation
        ↓
both-side utility scoring
        ↓
realistic offer ranking
```

## Objective

\[
TradeScore(T)
=
PriorAcceptance(T)
\times
E[\Delta U_{user}(T)]
\]

subject to a recipient-harm bound.

## Outputs

- Best Value.
- Most Realistic.
- Win-Win.
- Counter option.

## Trello Card

**Title:** `12 · NF-C3 — Generate beneficial and plausible fantasy trades`

---

# 17. Story 13 — Trade Acceptance Learning

## Story ID

`NF-C3A`

## Sequence

`13`

## Tags

`POST-LAUNCH` · `DATA-GATED` · `T4`

## Target

```text
accepted
rejected
countered
expired_or_ignored
not_submitted
```

## Architecture

```text
recipient utility
    + roster need
    + perceived player value
    + offer complexity
    + league behavior
    + manager history
        ↓
hierarchical outcome model
```

## Gate

Do not promote beyond heuristic prior until enough labeled outcomes exist.

## Trello Card

**Title:** `13 · NF-C3A — Learn trade acceptance from proprietary outcomes`

---

# 18. Story 14 — Playoff and Multi-League Planning

## Story ID

`NF-P1`

## Sequence

`14`

## Tags

`POST-LAUNCH` · `T3`

## Scope

- Rest-of-season rankings.
- Playoff-week schedule.
- Multi-week lineup planning.
- Bench stash value.
- Multi-league exposure.
- Contender/rebuilder modes.

## Trello Card

**Title:** `14 · NF-P1 — Add playoff planning and multi-league strategy`

---

# 19. Story 15 — Commissioner and Creator Expansion

## Story ID

`NF-X1`

## Sequence

`15`

## Tags

`POST-LAUNCH` · `T0/T3`

## Scope

- Expanded league count.
- Shareable reports.
- Exportable rankings.
- League-wide analysis.
- Creator/community embeds.

## Trello Card

**Title:** `15 · NF-X1 — Launch commissioner and creator expansion tier`

---

# 20. Trello Board Structure

## Lists

### 1. Settled / Ready

- Story 1 — Entitlement Triad
- Story 2 — Shared Governance
- Story 3 — Rookie Recalibration
- Story 4 — Track Record
- Story 5 — Weekly Audit

### 2. Deadline-Critical In Progress

- Story 6 — Weekly Model
- Story 7 — Matchup Optimizer
- Story 8 — Post-Draft Report

### 3. Post-Launch Ready

- Story 9 — Injury NLP
- Story 10 — Waivers
- Story 11 — ESPN Spike

### 4. Model/Data Gated

- Story 12 — Trade Utility/Search
- Story 13 — Acceptance Learning

### 5. Expansion

- Story 14 — Playoffs/Multi-League
- Story 15 — Commissioner/Creator

### 6. Blocked / External

- Yahoo approval.
- Any ESPN mechanism pending policy review.
- Acceptance learning pending labels.

### 7. Done / Live-Proven

Cards move here only after:

- Production artifact readback.
- Entitlement verification.
- Acceptance criteria.
- PM live proof.

---

# 21. Critical Path

## Launch Protection

```text
Story 1
→ Story 2
→ Story 3
→ Story 4
```

## Weekly Revenue

```text
Story 5
→ Story 6
→ Story 7
```

## Retention Expansion

```text
Story 6
→ Story 9
→ Story 10
```

## Trade Moat

```text
Story 6
→ Story 12
→ Story 13
```

---

# 22. Release Gates

## Paid Predraft Expansion Gate

Must pass:

- Story 1.
- Story 2.
- Story 3.
- Story 4.
- Stripe production verification.
- Non-subscriber wire inspection.
- Rollback artifact verification.

## Weekly Launch Gate

Must pass:

- Story 5.
- Story 6.
- Weekly interval floors.
- League scoring parity.
- Production freshness.
- Weekly model version stamp.

## Matchup Optimizer Gate

Must pass:

- Weekly model live.
- Joint/correlation contract validated.
- Win-probability simulation calibrated.
- Legal lineup constraints verified.
- Late-swap behavior tested.

## Injury-Driven Recommendation Gate

Must pass:

- Source/evidence provenance.
- Entity resolution.
- Availability calibration.
- Opportunity reallocation validation.
- User-visible explanation.

---

# 23. Definition of Done

A story is not done when code merges.

It is done when:

1. Artifact is built.
2. Validation passes.
3. Registry is updated.
4. Artifact is staged.
5. PM/operator promotes.
6. Artifact is published.
7. Production is read back.
8. Entitlement behavior is verified.
9. Rollback is verified.
10. User-facing copy matches the artifact.

---

# Final PM Note

The settled decisions produce a coherent roadmap, but they create one meaningful execution risk:

> Launch governance and weekly modeling now compete for the same limited pre-season window.

The final epic resolves this by running two parallel critical paths and explicitly allowing the post-draft roster report to slip before either paid-data protection or the weekly projection engine.

The non-negotiable outcomes are:

1. Paid 2026 values are protected at the data layer.
2. The weekly projection model is ready for the season-start window.
3. The matchup optimizer follows as quickly as the weekly distribution and correlation contracts allow.
4. No platform-sync shortcut violates the ESPN credential red line.
5. No public claim exceeds the actual evidence.
