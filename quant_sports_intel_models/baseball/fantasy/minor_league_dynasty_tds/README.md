# Minor League Dynasty Projection System
## Technical Design Specification Set

This package contains four Markdown documents.

1. **00_core_architecture.md**  
   Product boundary, shared posterior architecture, trust by level, V0–V4 roadmap, honest user outputs, infrastructure, and release criteria.

2. **01_data_provenance_and_v0_audit.md**  
   Feature-to-source matrix, explicit MiLB tracking limitations, source tiers, V0 audit schema, and the box-score + FanGraphs FV minimum viable set.

3. **02_model_validation_and_calibration.md**  
   Pre-registered bake-offs, translation-correlation gates, CRPS-primary selection, degenerate tripwires, purged/embargoed CV, null handling, layer calibration, and the permanent foil ladder.

4. **03_v4_mlb_debut_prior_integration.md**  
   Separately gated betting integration, shadow evaluation, held-out debut validation, distribution-widening requirements, graceful degradation, and serving release controls.

## Current Production Reconciliation

The design assumes:

- Single-A through Triple-A ingestion from the MLB Stats API.
- Box-score MLE components.
- FanGraphs FV as an admin-gated input.
- Existing learned ladder translations.
- Stolen-base attempt propensity as translated signal.
- Stolen-base success rate as a recorded null.
- S3 + Delta Lake + DuckDB.
- `best_alpha = 0`.

It does not assume comprehensive public MiLB Hawk-Eye data.
It explicitly treats ladder translations as selected on promotion and requires selection-bias diagnostics.
It prohibits retrospective use of current FanGraphs FV when contemporaneous snapshots do not exist.
