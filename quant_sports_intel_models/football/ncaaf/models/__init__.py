"""NCAAF model layer (Phase 1).

`hierarchical` is sport-agnostic linear-algebra (a penalized Gaussian / mixed-effects
solver); `team_strength` is the NCAAF-P1.2 team-strength estimator built on it;
`run_team_strength` is the CLI that reads the P1.1 marts and emits the posterior.
"""
