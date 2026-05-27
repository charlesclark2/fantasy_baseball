# Epic 2: Building the Factory Before Building the Products

## What Epic 2 Was About

Epics 3 through 8 are each building a specialized prediction model: one for run environment, one for offensive quality, one for starting pitcher suppression, one for bullpen state, and so on. These are called **sub-models** — targeted models that each answer one specific question about a game.

Before any of those models could be built, we needed shared infrastructure: a standard place to store their outputs, a registry to track which versions exist and which are currently in use, a framework for evaluating them, and a set of data readiness checks to ensure each model has the inputs it needs.

That's what Epic 2 was. Think of it like building a factory before building the products. The factory — the tooling, storage, quality control, and standards — had to come first so that every subsequent product was built the same way.

---

## The Four Core Infrastructure Pieces

### 1. Output Storage Table

Sub-models are only useful if their outputs can be stored and retrieved reliably. We built a single long-format storage table (`mart_sub_model_signals`) where every sub-model writes its predictions.

Each row in this table represents one **signal** for one game:

- Which game it's for
- Which team side (home or away)
- What the signal is called (e.g., `run_env_signal`)
- The signal's value and an uncertainty estimate
- Which model version computed it and when
- A hash of the input features that went into it (for auditing)

The table is also built with **SCD-2 time-tracking** (Slowly Changing Dimension Type 2) — meaning every time a signal is recomputed with new inputs, the old version is closed out with a timestamp rather than overwritten. This allows us to ask: "what did this signal look like at prediction time?" even months after the fact.

For downstream consumption, a separate wide-format view flattens all active signals for each game into a single row — making it easy for the main models and dashboards to join in sub-model outputs with a single lookup.

### 2. Sub-Model Registry

Just as the main production models have a registry (`model_registry.yaml`) tracking which version is live and what its performance metrics were, we created a parallel `sub_model_registry.yaml` for sub-models.

Each entry in the registry records:
- What the model predicts and over what time window it was trained
- The CV (cross-validation) performance score and the promotion threshold it had to clear
- Which feature tables it depends on
- What signals it writes to the storage table
- Its current status: **pending → challenger → champion → deprecated**

The registry enforces a one-champion-per-domain rule: promoting a new version automatically deprecates the previous one.

### 3. Evaluation Harness

Every sub-model needs to be tested before it can be promoted. We built a standalone evaluation script (`evaluate_sub_model.py`) that can be run against any registered sub-model to produce:

- Walk-forward temporal cross-validation metrics (MAE, Pearson correlation, etc.)
- Calibration analysis — does the model's confidence match how often it's right?
- Season-by-season stability — does the model perform consistently year over year?
- Head-to-head comparison mode — when a new version exists, compare it directly against the current champion on identical data

The harness was explicitly designed to be **isolated from the main production models**. It tests sub-models on their own terms — not "does adding this signal to the totals model improve it?" but "does this signal accurately predict what it claims to predict?"

### 4. Write Pattern Convention

Every sub-model that writes to the signal storage table uses the same merge pattern: a temporary staging table receives the new values as raw text, which is then typed and merged into the permanent table. This convention was established to avoid a specific technical failure mode that had caused problems in earlier work.

---

## Data Readiness Work (Per Sub-Model)

Before each upcoming sub-model epic could begin, we verified that the data it needs actually exists and is clean. These checks surfaced several things worth noting:

**Run environment model (Epic 3):** Weather data is only available from 2021 onward — there's no feasible way to backfill earlier seasons. The training window for the run environment model is therefore 2021+.

**Offensive quality model (Epic 4):** Player projection data (ZiPS) was not yet joined into the lineup feature table. We extended that table to include projected strikeout rate, walk rate, isolated power, and wRC+ for each lineup slot, with a prior-season fallback for players who don't yet have a current-season projection. We also added a metric for lineup depth (how strong are the bottom three batters?) and a lineup entropy score (how evenly is talent distributed across the lineup?).

**Starter suppression model (Epic 5):** The data was essentially already there. The pitching game log table already had xwOBA-against (our primary target) for 99.998% of starter appearances going back to 2015. The only meaningful adjustment was excluding a projected FIP metric that turned out to be 100% null in every season — a data ingestion issue in the underlying data source.

**Matchup model (Epic 8):** Bat tracking data (bat speed, swing length) was already wired in from an earlier phase but was missing one derived metric (the standard deviation of bat speeds across a lineup). We added that. We also wrote formal documentation of the player archetype clusters — the statistical groupings of batter and pitcher types — that the matchup model will use.

---

## What Epic 2 Means Going Forward

Epic 2 delivered the shared plumbing that every sub-model epic depends on. The result:

- **Any sub-model can now be built, stored, evaluated, and promoted** using a consistent, well-tested framework
- **Signal outputs are auditable and time-tracked** — every historical state is preserved
- **Feature data is confirmed ready** for the four sub-models scheduled in Epics 3–6
- **The evaluation harness is independent** — sub-model quality is measured on its own merits, not by how it affects the existing production models

Story 2.8 (building a supervised training target for the bullpen model) was intentionally deferred. The bullpen model's first version will use a rules-based approach that doesn't require a new training target — so building that target is only necessary if the rules-based version proves insufficient.

---

*Epic 2 completed 2026-05-19 (Stories 2.1–2.7, 2.9 complete; Story 2.8 deferred pending Epic 6 evaluation).*
