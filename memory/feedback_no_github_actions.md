---
name: feedback_no_github_actions
description: Pipeline runs entirely in Dagster+ — GitHub Actions workflows are decommissioned and must not be edited or referenced as the live pipeline
metadata:
  type: feedback
---

Never suggest editing GitHub Actions workflows as a fix for pipeline issues. The pipeline runs entirely in Dagster+ (hybrid agent). GitHub Actions workflows still exist in the repo but are decommissioned and not the live execution path.

**Why:** Migration to Dagster+ (Epic 0.5) is complete. GH Actions is no longer the live pipeline and user has had to correct this multiple times.

**How to apply:** For any pipeline fix (env vars, new steps, scheduling), target the Dagster ops/jobs in `pipeline/` — not `.github/workflows/`. When diagnosing pipeline failures, use `scripts/ops/dagster_runs.py` and `scripts/ops/dagster_steplog.py`.
