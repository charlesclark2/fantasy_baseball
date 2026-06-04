# run_differential — Production Bayesian Three-Layer Evaluation (sequential retrain)

- **OOS set:** 660 games (2026 fold; trained 2021–25 → genuine OOS).
- **Champion = faithful 369-feature no-sequential reproduction** (the documented production-champion spec). The deployed S3 `*_eb_enriched` binaries drifted from every record (needed ≥374 features vs. documented 369) and are unrecoverable; this nonseq retrain reproduces the documented contract AND is the clean ablation baseline.
- **Challenger present:** yes (sequential-enriched).

- **Layer 1 prior-predictive:** discretized-Normal(mu=0.042, sigma=4.482) → NLL **2.9334** (must beat).

| Metric | champion | challenger |
|---|---:|---:|
| L1 NLL (PMF) | 2.7757 | 2.7612 |
| L2 calib_80 | 0.768 | 0.776 |
| mean pred | -0.008 | -0.019 |

## Gates
### champion
| Gate | Result |
|---|:--:|
| L1 NLL < prior | ✅ |
| L2 calib_80 in [0.75,0.85] | ✅ |

### challenger
| Gate | Result |
|---|:--:|
| L1 NLL < prior | ✅ |
| L2 calib_80 in [0.75,0.85] | ✅ |

### head_to_head
| Gate | Result |
|---|:--:|
| challenger NLL < champion | ✅ |

