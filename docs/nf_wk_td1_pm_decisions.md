# NF-WK-TD1 — what the PM needs to decide

Written for the PM. Source of truth for the work itself: `plan_specs/nfl_fantasy/nf-wk-td1.yaml`
(closeout + six follow-ups) and `docs/nf_wk_td1_touchdown_components.md` (the measurements).
PR **#1137** → `dev`.

> ## ✅ RULED BY THE PM, 2026-09-16 — this document is now the RECORD of a settled decision,
> ## not an open question. The rulings live in the spec's `closeout.followUps`.
>
> **D1** lens hold does NOT lift; criterion restated — the substrate-carries-TDs criterion is MET,
> and the lens lifts when NF-INC-0916's corrected republish measures OK. **D2** gates the lens: yes;
> now an incident, `NF-INC-0916` (card ISopvUYR). **D3** operator: HOLD the merge — #1137 lands at
> INC-0916 node 4(ii). **D4** ungated posture accepted; the zero-clip re-measurement folds into
> INC-0916 node 3. **D5** triaged. **D6** spec stays `IN_PROGRESS`, held for INC-0916.
>
> ⚠️⚠️ **STATE CORRECTION on D3, measured after the ruling landed:** #1137 was **already merged to
> `dev`** (`7e0f1080`, 02:44:40Z). The intent is intact for a mechanical reason — the box image
> ships from `main` (`orchestration_cd.yml` fires on `push: branches: [main]`), Vercel production is
> `main`, the emission code is on `origin/dev` and **not** on `origin/main`, and no `dev→main` PR is
> open. **But the control has moved:** the hold is no longer "do not merge #1137", it is
> **"do not promote `dev`→`main` until NF-INC-0916 node 4"** — a routine promotion would ship the
> emission *and* a changelog entry that is not yet true, and the next scheduled weekly-serving fire
> would publish TD columns at uncorrected levels.

**Status: `IN_PROGRESS`, held for NF-INC-0916.** Code complete and CI-green. Node 3's acceptance
criterion — "record the before/after table" — is **not yet met**: the AFTER side needs one
~9-minute operator staging build. Nothing in this story publishes.

---

## The one-line summary

The weekly payload can now carry touchdowns, and the fix was plumbing rather than modelling.
**But the measurement done to justify it found something larger: the served weekly projection
is running at ~0.355 of the realized population mean, because the model trains on a whole week
of fabricated zeros.** The touchdown gap the lens was held for is real and now fixed; it is
smaller than the defect nobody had measured.

---

## D1 — Does the my-teams weekly lens hold lift? ⭐ the story's reason for existing

**The hold's stated criterion is met, literally.** The payload carries `passTd`/`passInt`/
`rushTd`/`recTd`; a league's touchdown rules flip CAPTURED → APPLIED automatically (verified
through the real `resolve_scoring`, two-sided); the scorer was already correct and is untouched.

**Two things complicate the decision, and both are new since the hold was placed.**

1. **The coherence hypothesis is refuted.** The registered expectation was that missing
   touchdowns explained most of the points-head-vs-component-line gap. Measured: the seven
   served terms were running *hot* by roughly the value of the four they omitted, so the
   payload's near-zero coherence was two offsetting errors. Emission removes one and exposes
   the other — the gap **widens** in seven of eight position/tier cells.
   *My read: this should not block the lens.* Coherence between two deliberately independent
   heads was never a serving criterion, the points figure a user sees is unchanged, and the
   component line is strictly more complete than before. But the hold's criterion was written
   before this was known, so it is worth restating rather than silently satisfying.

2. **The level defect (D2) is the bigger user-facing problem**, and it lands on exactly what
   the lens displays.

**Options.** (a) Lift now, on the literal criterion. (b) Lift after node 3's table lands.
(c) Hold the lens until D2 is fixed. (d) Lift, but scope the lens to ordering and suppress the
projected point total until D2 is fixed.

**My recommendation: (c), and merge this PR regardless.** Reasoning below under D2 — a start/sit
*ordering* largely survives the level defect, but the projected *number* does not, and the number
is the thing a user checks against every other site.

---

## D2 — Does the training-feed gap gate the lens (and what is it)? ⭐ the largest finding

**`stats_player_week` and `snap_counts` are absent from `ROLL_FORWARD_SOURCES` and referenced
nowhere in `pipeline/`.** The weekly model's two training feeds have no scheduled ingest at all.
Both are free, non-`on_demand` nflverse sources, so both are eligible for the roll-forward that
already runs weekly.

**Provable from the published manifest alone**, with no re-derivation: it records
`stats_as_of: "2025-W18"` beside `train_through: 2026 wk 1`. Those are both computed correctly,
and together they say the 2026 week-1 training rows carry **no stat line**, so `attach_labels`
fills `fantasy_points = 0.0` under the retained-zero convention. The model trains on a whole week
of fabricated zeros, and every player's "last week's points" feature is 0.0 on the week-2 slate.

**Measured effect, population-matched** (both sides are game-day-rostered QB/RB/WR/TE
player-weeks, so there is no selection confound):

| | mean PROJECTION | mean REALIZED | ratio |
|---|---:|---:|---:|
| QB | 1.345 | 6.549 | **0.205** |
| RB | 2.585 | 5.555 | 0.465 |
| WR | 2.057 | 5.743 | 0.358 |
| TE | 1.433 | 3.565 | 0.402 |
| **ALL** | **1.901** | **5.357** | **0.355** |

**The band names the mechanism.** Every one of the top ten projections carries `fpP10 = 0.00`
against a plausible `fpP90` (McCaffrey 0.00 / 10.45 / 27.17). An elite back's 10th percentile is
not zero. The ceilings are roughly right, so the conditional-on-playing half of the hurdle is
intact — **what is inflated is the zero atom**, which is precisely what a training week of
all-zeros does to a hurdle's `P(zero)` classifier.

**What this does and does not break.** Within-position *ordering* is probably largely preserved
(the model still names McCaffrey, Bijan, Gibbs, JSN, McBride as its top players — the right
players at the wrong level). The *displayed number* is not: a lens showing "4.2 projected points"
where every other site shows ~14 is immediately and visibly wrong, and cross-position comparisons
are distorted on top of that, because QB is depressed roughly twice as hard as the others
(0.205 vs 0.358–0.465).

**Question for the PM:** does this gate the lens, and does it become its own spec now? ⚠️ The fix
*looks* like adding two strings to a list. Before treating it that way, the repo's own rule
applies: verify the source actually advances, and check what a season-scoped partition overwrite
does to in-season weekly data. A scheduled writer over a source that does not advance is a
green-forever false green (the `stg_ref_players` lesson).

---

## D3 — Merging alone puts touchdowns on the wire. Is that intended?

There is **no gate between merge and serve**. `sports_nfl_weekly_serving_job` runs the publish
command daily, so the next scheduled fire after this merges will publish a payload carrying the
touchdown line, and the public weekly page will render four new columns for paid users (it filters
per field on `!= null`, so it picks them up with no frontend change).

A changelog entry is included on that basis. If the PM wants the emission staged behind the lens
decision instead, the lever is merge timing — not a code change.

**Question:** merge now and let it publish, or hold the merge until D1/D2 are settled?

---

## D4 — Four ungated numbers become five-to-eleven. Confirm the posture.

The component head is stamped `component_head_status: "advisory_ungated"` and this story does not
change that. The four new components inherit exactly the certification the seven served ones have,
which is none. Relevant context: NF-W6 *closed* four TD cells after measuring a distribution's
improvement ceiling over this same head's TD mean at 0.07–0.38%, so the head's TD means are near
their measured ceiling for those cells — a point in favour, not against.

**Recorded, not fixed:** `fit_component_head` clips predictions at zero, a structural upward bias
on a zero-heavy target. On one test week the head over-projected QB `passing_tds` 1.40× and TE
`receiving_tds` 3.41× against realized (n=78 / n=113 against realized means of 0.44 / 0.03 — the
single-week ratios are noisy and are **not** a bias measurement on their own). It interacts with
D2, because a depressed feature level changes what the clip does.

**Question:** accept the posture as-is (my recommendation), or does the PM want a measurement over
a full season before these numbers are paid-visible?

---

## D5 — Which follow-ups become specs?

| # | Finding | My view |
|---|---|---|
| 1 | The training-feed ingest gap (D2) | **Its own spec, high priority.** Larger than this story. |
| 2 | Entrypoint sibling sweep (card GyD9hoeD) — **premise corrected**: `main()` has two executing callers, both stopping at the `--publish` refusal, so the *success path* is the real gap | Re-scope the existing card against the corrected premise; a true executing smoke needs a synthetic lake |
| 3 | Component head clips at zero (D4) | Fold into a future head measurement; not urgent alone |
| 4 | Fixture re-capture — due (first publish happened), but **blocked on the rebuild**, and the published week has `n_bye: 0` so four synthetic rows cannot be captured | Checklist item on whichever story does the rebuild; a guard already fails if the bye row is dropped |
| 5 | NF-C6-PH2's `−0.7709` is a different, locally-staged artifact under the *opposite* sign convention from the published blob's `+0.0609` | Note on the C6-PH2 record; it entered this story's spec as though it described the published payload |
| 6 | Two sign conventions for the same quantity live in one program | One-line doc fix, low priority |

---

## D6 — Status flip

Node 3's acceptance criterion is not met until the operator's build lands. I left the spec
`IN_PROGRESS` per the NF-WK-FE1 / NF-C6-PH2 precedent (the PM flips status with a dated
annotation; a worker session does not).

**Question:** flip to `DONE` on the merge and treat node 3's after-side as an operator item — as
FE1 and C6-PH2 both did for their calendar-bound publishes — or keep it open until the table
exists?

---

## What is already settled and needs no ruling

- **The fork.** (A) EMISSION, on evidence: `fit_component_head` unchanged emits seven components
  without the labels and eleven with them, and the seven already-served components are
  **bit-identical** either way (`0.000e+00`). No new learner, feature set, hyperparameter or form.
- **The blast radius.** The attach lives in the serving path, not `engineer_features`, because
  `build_matrix_w6` calls `build_matrix` then `EM.attach_td_labels`, which raises if the column is
  already present — changing the shared matrix would break the NF-W6/W6b/W6b-C/W6c/W6d line. Every
  research harness is byte-identical.
- **Both artifacts stay readable.** The already-published pre-TD payload is driven through the
  payload contract, the per-row contract and the free reducer as a guard. The refusal lives in the
  builder, never on the contract (NF-C0).
- **Verification.** 26 guards, 12/12 RED-proven attributably; owning shard `core` 6,725 passed /
  0 failed; publish entrypoint smoke green.
- **No rescaling.** The coherence residual is reported as it falls (MH2.2).
