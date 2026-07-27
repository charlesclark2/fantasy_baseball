---
name: feedback_no_github_actions
description: Split of duties — the data pipeline executes in Dagster; GitHub Actions is the live CI/CD (tests + deploy) path, NOT decommissioned
metadata:
  type: feedback
---

Two separate systems — do not conflate them:

**Data pipeline EXECUTION → Dagster (self-hosted OSS on EC2).** For any pipeline fix (env vars, new ops/steps, scheduling, ingestion, dbt orchestration), target the Dagster ops/jobs in `pipeline/` — not a GitHub Actions workflow. Diagnose pipeline failures with `scripts/ops/dagster_runs.py` and `scripts/ops/dagster_steplog.py`.

**CI/CD → GitHub Actions (LIVE — not decommissioned).** `.github/workflows/` IS the live continuous-integration + continuous-deploy path: `ci.yml` / `orchestration_ci.yml` run the test gates, `orchestration_cd.yml` auto-deploys `betting_ml` + the Lambda backend on push to `main`, and `dbt_build_ci.yml` / `daily_ingestion.yml` also reference `betting_ml`. Editing these IS the correct place for CI-gate / deploy changes.

**Why this note exists:** an earlier version of this memory claimed "GitHub Actions is decommissioned; all pipeline fixes go in Dagster" — that was half-right and actively misleading. The correct rule: don't try to fix a *pipeline data* problem by editing a GH Actions workflow (that's Dagster's job), and don't treat GH Actions as dead (it's the live CI/CD path). Corrected 2026-07-27 after the CI/CD story wired `betting_ml/**` into `orchestration_cd.yml`.
