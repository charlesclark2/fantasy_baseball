# Application-session bootstrap prompt

**Last updated:** 2026-06-18 _(refresh on any material change)_

**What this is:** the standard primer pasted **FIRST in every fresh app-repo session**, immediately followed by **exactly one** `▶ Story prompt` (from `story_prompts.md` or `../fantasy/story_prompts.md`).

**Workflow (one fresh session per story):** we run app work **one story at a time, each in its own clean session** — *bootstrap + one story block → build → report → end the session.* Do **not** chain multiple stories through a single long-lived session (context drifts and stories bleed together). Pull the next card into a new session.

---

## Paste-first block

```
You are running ONE app story in the Credence app repo, in a FRESH session. After this primer I will paste
exactly one ▶ Story prompt. Do THAT story only — do not start, scope, or "while I'm here" any other story.

🚨 APP TARGET — three similar paths; TWO are live, ONE is dead:
- ✅ UI / anything user-facing → `frontend/` ONLY (Next.js on Vercel).
- ✅ API / backend → `app/backend/` (LIVE FastAPI; deployed to Lambda via infrastructure/lambda/deploy.sh,
  entrypoint app.backend.main). Edit this for backend work.
- ⛔ DEPRECATED legacy Streamlit UI → `app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`.
  NOT deployed, not the product. Do NOT edit and do NOT copy patterns from it.
- FOOTGUN: `app/` is half-alive — `app/backend/` is live, but the dead Streamlit UI sits right next to it,
  and Next.js has its own `frontend/app/` router dir. "The app's UI" is ALWAYS `frontend/`, never app/home.py.
- FIRST ACTIONS, before anything else:
    1. Read the repo-root `CLAUDE.md`.
    2. Run `cat frontend/package.json` and confirm Next.js ("next" in deps, "dev": "next dev").
- TRIPWIRE: if you are doing UI work and open `streamlit_app.py`, `st.set_page_config`, `app/home.py`, or
  `app/pages/*.py` → STOP, wrong place → go to `frontend/`.

ARCHITECTURE (implementation_guide.md §0.2):
- Frontend: Next.js on Vercel, in `frontend/`. UI lives in frontend/app, frontend/components, frontend/lib,
  frontend/hooks, frontend/data.
- Backend: AWS API Gateway + Lambda, FastAPI source in `app/backend/` (deploy via infrastructure/lambda/
  deploy.sh); serving-store writers in scripts/; dbt marts in dbt/.
- Serving read order: Railway PostgreSQL (primary) → S3 (fallback) → Snowflake (last resort, NEVER at request
  time). Precomputed picks/detail are reverse-ETL'd to PG via scripts/write_serving_store.py.
- DynamoDB holds only the bet log + users.

CONVENTIONS (§0.1):
- uv run python; dbtf (not dbt), always --select-scoped; Snowflake via MCP, fully-qualified, no USE, never on
  a request path.
- Hand any >1-minute script to the operator to run. DO NOT git commit or push — the operator does that.
- HONEST FRAMING (best_alpha = 0, non-negotiable): nothing user-facing may claim a win-rate/edge or frame
  "+EV"/"high conviction" as "place this bet." Every surface is transparency/confidence only; US betting is
  manual. Copy must reflect this.

DEFINITION OF DONE for an app story:
1. The change is in the right LIVE target — `frontend/` for UI, `app/backend/` for API — never the legacy
   Streamlit UI (`app/streamlit_app.py`, `app/home.py`, `app/pages/`, `app/utils/`).
2. It actually renders/works in the Next.js app (and/or the API responds correctly).
3. If the end user would notice the change: add an honest, factual entry to `frontend/data/changelog.json` as
   the final step (no edge claims). Weeks group MONDAY→MONDAY — set the entry's `week` to the MONDAY of the
   current week (not the literal ship date) and APPEND to that Monday's block if it already exists; only create
   a new block when this Monday has none. The legacy Streamlit app gets no changelog entry — it isn't shipped.
4. You do NOT git commit/push, deploy, or run >1-min jobs yourself. Instead, END with an OPERATOR HANDOFF (below).

⏭️ OPERATOR HANDOFF — REQUIRED FINAL OUTPUT (every app session ends with this):
   When your build is code-complete, STOP and present a single "⏭️ Operator handoff" checklist of everything
   *I* need to run to land/deploy it — exact, copy-pasteable, in run order. Omit a section only if it truly
   doesn't apply (say "none"). Do not bury these in prose; this block is the last thing you output.

   ```
   ⏭️ OPERATOR HANDOFF — <story id>
   1. 🔧 Backend/API (Lambda rebuild+deploy)?  — yes/no. If yes: what changed + the command:
        ./infrastructure/lambda/deploy.sh
   2. 🗄️ dbt models to run?  — list each with the exact scoped command, e.g.:
        dbtf run --select mart_clv_labeled_games
   3. ▶️ Scripts to run?  — exact commands incl. env + date/args (flag any >1 min), e.g.:
        uv run python betting_ml/scripts/predict_today.py --date <today>
   4. 🌱 Migrations / one-off infra (PG table, DynamoDB attr, SNS/SES, env vars, VAPID keys)?  — list each.
   5. 📦 git add (files to stage for deploy) — the exact command, listing ONLY the files this story changed:
        git add <path> <path> ...
        (I commit/push + deploy — you never do. List frontend/, app/backend/, dbt/, scripts/ paths as applicable.)
   6. 📝 Changelog — confirm the frontend/data/changelog.json entry (paste the line), or state "N/A — not user-facing."
   7. ✅ Verify-after-deploy — what I should check to confirm it worked (URL/endpoint/metric/expected output).
   ```

Acknowledge in one line that you are targeting `frontend/` (UI) / `app/backend/` (API) — NOT the legacy
Streamlit UI — have confirmed Next.js, and will end with the ⏭️ Operator handoff. Then I'll paste the one story.
```

---

## Notes
- This primer is **generic**; the per-story specifics (what to build, gates/AC) come from the story's own `▶ Story prompt`. Keep the two separate.
- App surfaces tagged **⏳ §0.3** are *not* run from here — their prompt is generated by the upstream model session as its final step, then run as a normal app session (bootstrap + that generated block).
- If a story is genuinely backend-only (no UI), the app-target guard still applies to any surface it touches; the serving/dedup logic lives in `scripts/`, the Lambda, or dbt — still never the Streamlit `app/`.
