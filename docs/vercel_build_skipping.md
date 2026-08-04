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

## ⚠️ What this does and does not fix

**It does NOT reduce the deployment count**, which is what `api-deployments-free-per-day` limits.

Vercel creates the deployment first, then runs the ignore command and marks the deployment
`Canceled`. The deployment still exists and still counts. Vercel's own
[Builds doc](https://vercel.com/docs/builds) says so explicitly, contrasting the two mechanisms:

> **Skipping unaffected projects**: Vercel automatically detects whether a project's files (or its
> dependencies) have changed and skips deploying projects that are unaffected. This feature reduces
> unnecessary builds and **doesn't occupy concurrent build slots**.
>
> **Ignored build step**: You can also write a script that cancels the build for a project if no
> relevant changes are detected. **This approach still counts toward your concurrent build limits**,
> but may be useful in certain scenarios.

So what this config actually buys:

- ✅ no `npm install` + `next build` on non-frontend commits — build minutes, and the Hobby
  concurrent-build slot frees almost immediately
- ✅ non-frontend pushes stop queueing behind each other
- ❌ **does not lower the deployments-per-day count** — a canceled deployment is still a deployment

### The lever that does cut the deployment count

`git.deploymentEnabled` in `vercel.json` prevents a deployment from being *created at all* for
matching branches ([Git Configuration](https://vercel.com/docs/project-configuration/git-configuration)).
It is branch-pattern based (minimatch), not path based, so it cannot express "only when `frontend/`
changed" — it can only stop whole branches from deploying. Example, if preview URLs for story
branches are judged not worth the quota:

```json
{ "git": { "deploymentEnabled": { "*": false, "dev": true, "main": true } } }
```

**This is deliberately NOT configured** — it removes per-PR preview URLs, which is a workflow
decision for the operator, not a session's to make. Same class as "upgrade to Pro": an operator
call.

## Verification

Two-sided verification of the **exit-code direction and cwd-robustness** was done locally against
real commits in this repo (table above) — that is the half most likely to be silently inverted.

**Live Vercel verification is still open** (this session had no Vercel dashboard, CLI, or connector
access). To close it, after this merges to `dev`:

1. Confirm Settings → General → **Root Directory** reads `frontend`. If it reads the repo root
   instead, move `frontend/vercel.json` to the repo root — Vercel only reads `vercel.json` from the
   Root Directory, so in that case this config is inert and nothing changes.
2. Push a **non-frontend** commit → that deployment should show **Canceled**, with the ignore-step
   log ending in something like `The Ignored Build Step exited with 0, deployment canceled`.
3. Push a **frontend** commit → it must **build and deploy normally**. Do not accept step 2 alone;
   a config that skips everything produces an identical-looking "Canceled" and is the exact failure
   mode described above.

Merging this PR is itself a frontend change (`frontend/vercel.json`), so it will run one build —
that is expected and is also a free instance of check 3.
