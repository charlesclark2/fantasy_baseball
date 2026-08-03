# Minor League Dynasty Projection System
## Appendix C — Separately Gated MLB-Debut Prior Integration

**Stage:** V4 only  
**Serving status by default:** Shadow  
**Principle:** A speculative prospect posterior may not corrupt a live served number.

## 1. Separation of Systems

Through V3:

```text
Dynasty product
    └── standalone posterior and career simulation
```

V4 adds a one-way, versioned adapter:

```text
approved dynasty posterior snapshot
        ↓
debut-prior adapter
        ↓
shadow betting-model run
        ↓
held-out evaluation
        ↓
release gate
```

No direct runtime dependency from the live model to the dynasty board is allowed.

---

## 2. Adapter Contract

The adapter publishes only approved MLB-level latent distributions.

### Hitter candidate fields

- K% distribution.
- BB% distribution.
- ISO/damage distribution.
- Platoon distribution only if validated.
- Playing-time uncertainty.
- Data trust and level.
- Posterior sample IDs.

### Pitcher candidate fields

- K% distribution.
- BB% distribution.
- HR/damage proxy.
- Starter/reliever probability.
- Workload distribution.
- Data trust and level.

Tracking-derived fields are absent unless separately sourced and validated.

---

## 3. Hard Requirement: Sparse Debuts Widen Uncertainty

A player with no MLB evidence must not inherit an artificially narrow MiLB posterior.

The served distribution must include:

\[
\sigma^2_{\text{served}}
=
\sigma^2_{\text{MiLB posterior}}
+
\sigma^2_{\text{level translation}}
+
\sigma^2_{\text{debut adaptation}}
+
\sigma^2_{\text{role}}
\]

Requirements:

- Lower-level origin produces greater inflation.
- Missing FV produces greater inflation.
- Unsupported component produces marginalization, not zero variance.
- A new MLB observation updates gradually.
- The prior cannot become more confident merely because component means agree.

---

## 4. Held-Out Debut Evaluation

Build cohorts of historical debuts using only information available before debut.

Evaluate:

- First 10 PA/BF.
- First 25 PA/BF.
- First 50 PA/BF.
- First 100 PA/BF.
- First 5 appearances/starts.
- Rest-of-season.

Mandatory comparison ladder:

1. League-average prior.
2. Fixed MLE.
3. FV/ranking prior.
4. Fixed MLE + FV.
5. Full prospect posterior.
6. MLB-only model as MLB data accumulates.
7. Blended prior/MLB posterior.

Metrics:

- Event log loss.
- CRPS.
- Brier score for relevant events.
- Calibration.
- Distribution width.
- Tail miss rate.
- Downstream H2H/total proper scores.

---

## 5. Release Gate

V4 can influence served output only when:

- Full posterior improves held-out proper score over fixed MLE + FV.
- Improvement survives multiple-testing adjustment.
- Calibration floors pass.
- Distribution widening requirement passes.
- No level cohort is materially harmed without an explicit fallback.
- Rollback and kill switch are tested.
- Shadow monitoring has run across a minimum sample.
- Product and model-risk owners approve.

If not:

```text
served_debut_prior = fixed_MLE_or_league_average
```

---

## 6. Graceful Degradation

Fallback hierarchy:

1. Validated full debut prior.
2. Fixed MLE + FV.
3. Fixed MLE.
4. Level/age prior.
5. League-average rookie prior.

Triggers:

- Missing posterior snapshot.
- Stale feature timestamp.
- Unsupported level.
- Failed identity match.
- Calibration alert.
- Vendor/FV unavailable.
- Model-version incompatibility.

The fallback selected must be logged with every served prediction.

---

## 7. Shadow and Canary Operation

### Shadow

- Generate predictions without serving them.
- Compare distributions and outcomes.
- Inspect cohort-specific harm.

### Canary

- Limited percentage or internal-only use.
- Automatic rollback on calibration or data-integrity breach.
- No user-visible performance claim.

---

## 8. Monitoring

Track:

- Prior-to-posterior weight as MLB evidence accrues.
- Calibration by debut level.
- CRPS by PA/BF horizon.
- Distribution width versus baseline.
- Missing-field rates.
- Fallback usage.
- Identity errors.
- Posterior staleness.
- Difference from fixed MLE.

---

## 9. No Automatic Recommendation Coupling

Even after V4 approval, the integration supplies probability distributions only.

It may support:

- H2H event distributions.
- Player-prop distributions.
- Team-run and game-total distributions.
- Scenario analysis.

It must not generate user-facing “edge,” “bet,” “lock,” or expected-profit claims.
