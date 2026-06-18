# ⚠️ `app/` is HALF-ALIVE — check which part you're in

This directory mixes a **live backend** with a **dead UI**. Know which you're touching:

- ✅ **`app/backend/` = LIVE FastAPI API.** Edit it for backend/API work. Deployed to Lambda via `../infrastructure/lambda/deploy.sh` (entrypoint `app.backend.main`).
- ⛔ **Everything else here = DEPRECATED legacy Streamlit UI:** `app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`. **Not deployed, not the product. Do NOT edit** unless a task *explicitly* says "legacy Streamlit."

**If you were asked to do UI / user-facing work, you are in the WRONG place.** The live UI is the **Next.js app in `../frontend/`** (`cat ../frontend/package.json` → `"dev": "next dev"`). Go there.

A session edited the Streamlit UI here by mistake (2026-06-18) when it should have edited `../frontend/`. See the repo-root `CLAUDE.md` for the full rule.
