# Vercel build skipping — `frontend/vercel.json` `ignoreCommand`

**Added 2026-08-04.** Config lives in [`frontend/vercel.json`](../frontend/vercel.json).

## Why

The worktree-per-session + PR-per-story workflow generates a lot of Vercel activity: every push to
every story branch creates a preview deployment, plus the `dev` build and the `dev → main`
production build. Almost none of those touch `frontend/` — they are pipeline, dbt, model, or docs
work — yet each one used to run a full `next build`. On the free (Hobby) tier that was flooding
`api-deployments-free-per-day` (100 deployments / 86,400s) and burning the single Hobby concurrent
build slot.

The Ignored Build Step path-filters on `frontend/`, so only a commit that actually changes the
Next.js app runs a build.

> **Plan update (2026-08-04): the account is now on Pro.** That removes the quota problem outright —
> deployments/day 100 → **6000**, per-hour 100 → **450**, concurrent builds 1 → **up to 500**. This
> config is therefore no longer a *quota* lever; it is a **cost** lever. Pro bills Build CPU Minutes
> (from $0.0035/CPU-minute against the monthly credit), so every skipped `npm install` + `next build`
> on a pipeline/dbt/model commit is money not spent. Worth keeping — it is a recurring saving rather
> than a one-off ceiling.

## Why Vercel's native "Skip deployments" toggle does NOT cover this repo

Settings → General → Root Directory has a toggle: *"Skip deployments when there are no changes to the
root directory or its dependencies."* It is **Enabled**, and it does **nothing here** — this is why
the deploy flood happened despite the toggle looking like it should have prevented it.

Vercel's [monorepo requirements](https://vercel.com/docs/monorepos) for that feature:

> The monorepo must be using npm, yarn, pnpm, or Bun workspaces, following JavaScript ecosystem
> conventions. Packages in the workspace must be included in the workspace definition (`workspaces`
> key in `package.json` for npm and yarn or `pnpm-workspace.yaml` for pnpm).
>
> - **Changes that are not a part of the workspace definition will be considered global changes and
>   deploy all applications in the repository.**

This repo has **no root `package.json` at all** — it is a Python repo with a single Next.js
subdirectory, so there is no workspace definition and nothing to detect a dependency graph from.
Every commit is therefore "not part of the workspace definition" → treated as a **global change** →
deploys. The toggle is structurally inert here.

Vercel's own next sentence names the remedy, which is exactly what this repo does:

> If your project does not meet these requirements, you can use the Ignored Build Step.

**Leave the toggle Enabled.** It is a no-op for this repo, and its failure mode errs toward
*deploying*, never toward skipping — so it can never cause a missed deploy. It would start working on
its own if the repo ever grew a real JS workspace. Likewise leave *"Include files outside the root
directory in the Build Step"* Enabled; it does not affect skip detection.

## What is configured

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "ignoreCommand": "cd \"$(git rev-parse --show-toplevel)\" && git diff --quiet HEAD^ HEAD -- frontend/"
}
```

`ignoreCommand` in `vercel.json` **overrides** the dashboard's Settings → Git → Ignored Build Step,
so this is version-controlled and reviewable in the PR rather than being a dashboard setting nobody
can see in the repo (this repo's recurring *documented-but-never-set* failure class — cf.
`W7B_LAKEHOUSE_S3` in `CLAUDE.md`).

### 🚨 Exit semantics are inverted from intuition, and are load-bearing

Per Vercel's docs: **exit `0` → the build is IGNORED (deployment shows `Canceled`); exit `1` or
greater → the build PROCEEDS.**

| Situation | `git diff --quiet` exit | Vercel does |
|---|---|---|
| `frontend/` unchanged in this commit | `0` | **skips** ✅ |
| `frontend/` changed in this commit | `1` | **builds** ✅ |
| `HEAD^` missing (initial commit / shallow clone edge) | `128` | **builds** — fails safe ✅ |

The fail-safe direction is the correct one: an unexpected git error builds rather than silently
freezing deploys.

### 🪤 Why the command is anchored with `git rev-parse --show-toplevel`

**The Ignored Build Step runs with cwd set to the project's Root Directory, not the repo root.**
This project's Vercel Root Directory is `frontend` (the repo has no top-level `package.json`;
`frontend/` is the only Next.js app). So the obvious-looking command is silently catastrophic:

```sh
# ⛔ DO NOT USE — run from cwd=frontend/, the pathspec resolves to frontend/frontend/,
#    which matches nothing, so git reports "no diff" and exits 0 for EVERY commit.
git diff --quiet HEAD^ HEAD frontend/
```

Measured in this repo against a real frontend commit (`93fb2498`) and a real non-frontend commit
(`385b2d6c`):

```
cwd=frontend/, naive command:
  frontend CHANGED   -> exit 0   # ⛔ SKIPS a real frontend change
  frontend UNCHANGED -> exit 0
```

That is a total, silent deploy freeze — the failure is invisible because a canceled deployment
looks exactly like a correctly-skipped one. Git does not error on a non-matching `diff` pathspec;
it just reports nothing. The `cd "$(git rev-parse --show-toplevel)"` prefix makes the pathspec
repo-root-relative, so the command is correct from either cwd:

```
cwd=repo root:  CHANGED -> 1 (build) | UNCHANGED -> 0 (skip)   ✅
cwd=frontend/:  CHANGED -> 1 (build) | UNCHANGED -> 0 (skip)   ✅
```

### 🪟 `HEAD^ HEAD` is a single-commit window

The diff looks at **one commit**, not the whole branch. Two consequences worth knowing before you
report a bug:

- **Merge commits are correct.** `git diff HEAD^ HEAD` on a merge compares against the *first
  parent* — the branch as it was before the merge — so a `dev` or `main` merge commit sees the
  entire PR's diff. This is the case that matters for production.
- **Branch previews are per-push.** On a story branch whose frontend change landed in commit 1, a
  later backend-only push will skip, so the preview URL stops updating. That is benign — the
  preview built from commit 1 still exists, and the eventual merge diffs correctly — but it looks
  like "my preview didn't update." Push a frontend-touching commit (or redeploy without *Use
  project's Ignore Build Step*) if you need a fresh preview.

This is the pattern Vercel's own docs use; a base-branch diff would be more precise but is fragile
against the `--depth=10` shallow clone.

### 🔑 A REDEPLOY after an ENV VAR change will be SKIPPED — uncheck the box

**This is the trap most likely to bite, because it looks like the env var simply didn't work.**

Changing a Vercel environment variable does not change git. So a plain **Redeploy** re-runs
`git diff HEAD^ HEAD -- frontend/` against *the same commit* — and if that commit was a non-frontend
one (which, on `main`, it usually is now), the ignore step exits `0`, the redeploy is **skipped**,
and the new env var **never takes effect**. No error; the site just keeps serving the old build.

This project sets a lot of these in the Vercel dashboard — `NEXT_PUBLIC_API_URL`, the Cognito pool
and app-client ids, `NEXT_PUBLIC_ADMIN_EMAILS`, PostHog, Sentry — so this will come up.

**The fix is built into Vercel.** On the deployment's **Redeploy** dialog, untick **"Use project's
Ignore Build Step."** Per Vercel's [monorepo doc](https://vercel.com/docs/monorepos):

> If you have created a script to ignore the build step, you can skip the script when redeploying or
> promoting your app to production. This can be done through the dashboard when you click on the
> **Redeploy** button, and unchecking the **Use project's Ignore Build Step** checkbox.

Same applies to promoting a deployment to production, and to any other "rebuild without a code
change" reason (rotating a secret, clearing build cache, picking up a changed Vercel project
setting). Rule of thumb: **if you want a build and the commit did not touch `frontend/`, untick the
box** — or push a real frontend commit.

## ⚠️ What this does and does not fix

**It does NOT reduce the deployment count.** Vercel creates the deployment first, then runs the
ignore command and marks it `Canceled`. The deployment still exists and still counts. Vercel's
[monorepo doc](https://vercel.com/docs/monorepos) states it outright:

> Canceled builds initiated using the Ignored Build Step **count towards your deployment and
> concurrent build limits** and so skipping unaffected projects may be a better option for monorepos
> with many projects.

(…and "skipping unaffected projects" is unavailable here — see the workspace-requirements section
above.)

So what this config buys:

- ✅ no `npm install` + `next build` on non-frontend commits — **build CPU minutes**, which is
  billable on Pro
- ✅ the concurrent-build slot frees almost immediately, so non-frontend pushes stop queueing
- ❌ **does not lower the deployments-per-day count** — a canceled deployment is still a deployment

**On Pro this is fine.** The limit that motivated the story (`api-deployments-free-per-day`, 100/day)
no longer applies: Pro is 6000/day, 450/hour, 500 concurrent. The remaining benefit is cost, not
quota.

### `git.deploymentEnabled` — considered, and now moot

`git.deploymentEnabled` in `vercel.json` prevents a deployment from being *created at all* for
matching branches ([Git Configuration](https://vercel.com/docs/project-configuration/git-configuration)).
It is branch-pattern based (minimatch), not path based, so it cannot express "only when `frontend/`
changed" — it can only stop whole branches deploying:

```json
{ "git": { "deploymentEnabled": { "*": false, "dev": true, "main": true } } }
```

It was the only lever that would have cut the deployment *count* on Hobby, and was deliberately left
unset because it removes per-PR preview URLs — a workflow call for the operator. **With the Pro
upgrade it is unnecessary**: the quota ceiling is gone, so there is no reason to trade away preview
URLs. Recorded here only so a future session does not re-derive it.

## Verification

Two-sided verification of the **exit-code direction and cwd-robustness** was done locally against
real commits in this repo (table above) — that is the half most likely to be silently inverted.

1. ✅ **Root Directory confirmed `frontend`** (dashboard, 2026-08-04) — so Vercel does read
   `frontend/vercel.json`. Had it read the repo root, the file would have been inert and the config
   would have done nothing.
2. ⏳ **A non-frontend commit must show `Canceled`**, with the ignore-step log ending in something
   like `The Ignored Build Step exited with 0, deployment canceled`.
3. ⏳ **A frontend commit must build and deploy normally.** Do not accept check 2 alone — a config
   that skips *everything* produces an identical-looking `Canceled`, which is the exact failure mode
   described above. The PR #580 merge commit (`85cd01bc`, which changed `frontend/vercel.json`) is a
   free instance of this check.

Note that `frontend/vercel.json` reached `dev` before `main`, so production kept building
unfiltered until the following `dev → main` merge.
