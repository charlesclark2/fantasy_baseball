# Credence — repo guide for Claude Code sessions

## 🚨 WHICH APP TO EDIT — READ FIRST

Three things share confusingly similar paths. Two are live; one is dead.

- ✅ **UI / anything user-facing → `frontend/` ONLY** — the **Next.js** app (Vercel, auto-deploys on push to main).
- ✅ **API / backend → `app/backend/`** — the **live FastAPI** service (deployed to Lambda via `infrastructure/lambda/deploy.sh`; `app.backend.main` is the entrypoint). This is live — edit it for backend work.
- ⛔ **DEPRECATED legacy Streamlit UI → `app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`** — **not deployed, not the product. Do NOT edit** unless a task *explicitly* names "legacy Streamlit."

**Footgun (this is what bit a session on 2026-06-18):** the dead Streamlit UI files sit at the **top of `app/`, right next to the live `app/backend/`**, and Next.js has its *own* router dir at `frontend/app/`. So `app/` is **half-alive**: `app/backend/` = keep; everything else in `app/` = legacy UI = don't touch. "The app's UI" is **always `frontend/`**, never `app/home.py` / `app/pages/`.

**First action in any app/UI session:** run `cat frontend/package.json` and confirm Next.js (`"next"` in deps, `"dev": "next dev"`). If you're doing **UI** work and find yourself in `streamlit_app.py`, `st.set_page_config`, `app/home.py`, or `app/pages/*.py`, **STOP — wrong place → go to `frontend/`.**

## App quick map
- UI (Next.js): `frontend/app/**`, `frontend/components/**`, `frontend/lib/**`, `frontend/hooks/**`, `frontend/data/**`
- Backend API (live FastAPI): `app/backend/**` (`main.py`, `routers/`, `models/`, `services/`); deploy via `infrastructure/lambda/deploy.sh`
- Serving-store writers: `scripts/` (e.g. `write_serving_store.py`); dbt marts in `dbt/`
- Serving store read order: Railway PostgreSQL (primary) → S3 (fallback) → Snowflake (last resort, never at request time)
- ⛔ Legacy Streamlit (do not edit): `app/streamlit_app.py`, `app/home.py`, `app/pages/**`, `app/utils/**`
- **Changelog:** any user-facing change adds an entry to `frontend/data/changelog.json` as its final step. (Streamlit gets none — it isn't shipped.)

## Where the plans live
- Model + application roadmap (single source of truth): `quant_sports_intel_models/baseball/edge_program/build_roadmap.md`
- Story specs: `quant_sports_intel_models/baseball/edge_program/edge_program_implementation_guide.md` (§0.2 = app architecture + the app-target rule)
- Per-story run prompts: `quant_sports_intel_models/baseball/edge_program/story_prompts.md`

## Conventions (see guide §0.1)
`dbtf` (not `dbt`); Snowflake via MCP, fully-qualified, no `USE`, never on a request path; `uv run python`; hand >1-min scripts to the operator; **do not `git commit`/`push`**; market-blind for non-market models; honest framing for anything user-facing (no win-rate / edge claims — `best_alpha = 0`).
