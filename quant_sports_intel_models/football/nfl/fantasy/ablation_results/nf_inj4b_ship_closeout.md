# NF-INJ4b-SHIP — closeout: **WIRED AND MEASURED, awaiting the operator's ship decision**

`best_alpha = 0`. Nothing in this session published anything, and the session never ran `--publish`,
`deploy.sh`, or a box schedule change.

| record | what it is |
|---|---|
| `nf_inj4b_ship_operator_packet.md` | **the deliverable** — the decision, generated from the measured state |
| `nf_inj4b_ship_battery.{json,md}` | the level-adjacent measurement battery on the publish candidate |
| `nf_inj4b_ship_expected_effect.json` | the 60 designated players, pre-ship → post-ship games (the post-publish check joins to this) |
| `served_artifacts/nfl_fantasy_designation_duration_v1.json` | the served constants, derived from the certified winner |
| this file | the verdict, the findings, and what the operator does next |

---

## 1. The precondition, verified rather than assumed — **PASS**

All three clauses hold, and the third was checked against the artifact rather than the prose:

- the operator-run counterfactual exists (`generated_at 2026-09-13T21:29:44Z`);
- its **§3 no-op control PASSED** — 14 boards, 0 max rank move, baseline agreement 1.0000;
- it priced the **CERTIFIED winner**. `nf_inj4b_designation_duration.json` records
  `winner = desig_x_practice`, `ship = true`, 9/9 gates; the counterfactual reads that key rather
  than naming an arm, and the constants it published (`out ×0.8639 / doubtful ×0.9526 /
  questionable ×0.9629`) **re-derive exactly** from the certified arm on the frame. The registered-
  arm figure NF-INJ4b §3b(3) records as the near-miss (`×0.8682`) does not appear anywhere.

The run is genuinely **in scope**: season start 2026-09-09, as-of 2026-09-13, 0 designations refused,
59 designated rows per board, 549–640 ranks moved.

⚠️ **The W0a dependency is SATISFIED** — NF-CAP1's 2026-09-13 re-measurement found the injuries
capture healthy and capturing 2026 designation history (11 rows on 09-08, 167 on 09-11), picked up
with no operator action. NF-INJ4b §3e's "zero rows for 2026" is the **retired** finding.

---

## 2. What was wired

A production caller now passes `designation_games` into the season board's availability owner, so the
certified arm is reached from the build path for the first time. The absence guard became a
**presence** guard in the same commit (MH2.7).

Design decisions worth their own line, each closing a named failure mode:

- **The constants are PERSISTED, never re-fitted at build time.** MH2.1 (b) says serve the object
  that was validated; NF-INFRA1 makes it stronger than a preference — the fitting frame is
  gitignored, so it is absent from the `COPY . .` box image and a build-time fit could only die or
  degrade quietly.
- **They are read out of the decisive run and verified against the operator packet.** A serving
  artifact that disagreed with the packet would mean the operator approved one set of numbers and
  the board served another.
- **`none_listed` (×0.9906) is NOT served.** It is the arm's baseline hazard; applying it would
  discount ~2,400 undesignated players — a board-wide level shift, not the certified intervention.
- **The channel is season-gated**, so a historical fold rebuilt for the scorecard or the band panel
  can never be regraded against today's designations (the `market_freshness` hindsight boundary,
  on the availability channel).
- **A modelled roster status never reaches this channel at all** — `disclosable_designation`
  withholds IR/PUP/NFI/SUS at the SOURCE, so the formal and weekly channels are disjoint at the feed
  before any composition argument is needed; and the designation cap stamps
  `_formal_discount_applied` so the news channel stays disjoint too (the NEWS-1 rule).

---

## 3. ⭐ The findings

### 3a. ⭐⭐ The whole NF-C9 suite passed GREEN over a wired discount that made its copy false

52 clauses, all green, while `WEEKLY_DESIGNATION_NOT_MODELLED` — *"our projected-games figure does
not take this into account"* — was live on every board and no longer true.

The clause meant to prevent exactly this (`test_the_projection_path_never_reads_the_disclosure_channel`)
asserted three **token spellings** were absent from `season_projection.py`. The feed read lives in
`designation_discount_serving.py` and the production caller in `run_season_projection.py`, so none
of those tokens was ever going to appear in the file being scanned. **The guard was one module
boundary away from the thing it existed to protect.**

⭐ **The transferable half:** a guard keyed on a SPELLING tests where somebody happened to type a
name; a guard keyed on the WIRING tests whether the model is reached. Only the second survives a
refactor that moves the read one file over — which is the commonest thing that happens to a serving
path. Re-keyed (the NF-CAP1 re-key), and a new coherence clause now refuses the copy and the policy
disagreeing in **either** direction: policy-on/copy-denying is what this PR would have shipped,
policy-off/copy-claiming is what a **rollback** produces, and that one is more dangerous because the
one-line flag flip feels complete on its own.

### 3b. ⭐ The no-op control caught a rounding re-derivation — and nothing guarded it

The battery's first run FAILED its own control at worst `1.0e-01`, with **1,113 ranks moving across
the 14 boards under an EMPTY designation map**. Cause: the published board rounds `pts`, `repl` and
`vor` each to one decimal, so re-deriving `vor` as `pts − repl` reintroduces a rounding residue —
as *movement*, on rows nothing had touched. Fixed by applying the DELTA to the published value
(`repl` is invariant under a first-order read, so `Δvor == Δpts` exactly). Worst is now `0.000e+00`.

Same shape as the `(config_name, n_teams)` defect that made 1,715 of 1,716 rows "move" in NF-INJ4b's
own counterfactual — and the RED proof then found **no guard covered it**, so the control is now a
test too, with a fixture whose `vor` deliberately disagrees with `pts − repl` (a consistent fixture
would make the clause vacuous).

### 3c. ⚠️ The counterfactual's renderer prints PRESEASON prose over IN-SEASON data

Its numbers are right and its narrative contradicts them. §1 renders *"**-4 days before Week 1**"*
for a run four days AFTER kickoff and calls an in-season census *"the preseason shape"*; §5's third
bullet — *"Today's zero is the SCOPE RULE refusing every row"* — is emitted **unconditionally** and
is flatly false on a run that moved 549–640 ranks per board. The JSON is correct throughout
(`in_scope: true`, `designations_refused: 0`, `out_of_scope_rehearsal: null`).

⛔ Nothing was changed there: it is a decided story's artifact and re-running it is the operator's
command by rule. This packet therefore quotes the **JSON**, never that prose. Carded below, because
a reader who trusts the narrative over the table reaches the opposite conclusion about whether the
discount does anything.

### 3d. The post-publish check's first cut reported partial success against an unshipped board

Two of the 60 designated players have a discount smaller than the board's own one-decimal rounding,
so they are individually indistinguishable from undiscounted. Counting them as MOVED reported
`moved 2` against a board that had not shipped at all. They are now their own state — never a pass.

⭐ The check is **proven two-sided**: against today's pre-ship board it reports `moved 0 / UNMOVED 58
/ below the board's rounding 2` and exits 1. A green from it is therefore informative rather than
the only thing it can say (G100-D1).

### 3e. Two smaller ones, both found by driving the code rather than reading it

- **The published multiplier is served, not one re-derived from a 4dp `E[games missed]`.** Both are
  stored at the packet's four decimals, so re-deriving `(17 − 2.3145)/17 = 0.863853` instead of using
  `0.8639` moves a 17-game projection by 8e-4 games. Immaterial as a number; as a property it is the
  difference between "the board does what the packet said" being exactly true and approximately true.
- **`designations=None` meant two things.** "Not supplied, go and fetch" and "supplied, and the feed
  came back unreadable" were the same value, which would make an outage indistinguishable from a
  normal build. Separated with a sentinel.

### 3f. The capture-pinned rebuild is not reachable from a laptop, and the window is narrow

The D3 precondition was RUN and REFUSED. The served board carries `ecr_as_of 2026-09-10`; the main
checkout's FantasyPros cache is `9/01`, and FantasyPros serves **only the current snapshot**, so the
board's own ECR vintage is **unrecoverable** (NF-INJ2c). ⛔ Not chased.

⚠️ Two sub-findings for the next session that needs a pin:
- `assert_vintages_match` is pinned to **NF-INJ2c's** baseline directory, so its refusal quotes THAT
  manifest's vintages (`adp 2026-08-31 / ecr 2026-09-01`). Its verdict is still right for this
  checkout — the local caches match neither board — but the figures it prints describe a different
  capture, so the battery reports the comparison against its own capture beside it.
- the market caches are gitignored, so a fresh worktree has **none at all** and every vintage reads
  `None`. Capture the board AND its market inputs at study start, promptly after a publish.

### 3g. Population facts worth carrying

- **No rookie on the current board carries a weekly designation** — all 60 designated rows are
  veterans, so the rookie band is untouched by this change on today's feed. Not a guarantee; a
  measurement about this slate.
- 16 players carry a feed value we cannot interpret. They are disclosed as unknown and **priced at
  nothing** — never guessed at, never silently dropped.

---

## 4. ⛔ What this session did NOT do, and why

- **The capture-pinned REBUILD** — not reachable (3f). It is the operator's step, in an environment
  whose caches match, exactly where NF-INJ4b's closeout §5B put it. Every figure in the packet is
  FIRST-ORDER and says so: replacement levels are the published board's, and NF1.5's ordering
  permutation has not re-run (NF-INJ1 measured that step handing **+36.4%** of an availability
  discount back, so a rebuild's rank moves will differ — most plausibly they will be smaller).
- **The interval revalidation** — reported **STRUCTURALLY INACTIVE, not passed**. The channel is
  season-gated and NF1.9 scores historical panels, so it cannot reach a row the discount moved.
  NF-INJ4b §6 refused the preseason placement read for this reason; the reason it was right then is
  the reason this is right now. The adjacent question it is easy to conflate with is answered: the
  availability chain runs BEFORE the band attach, so a capped player's band is attached to his capped
  point — byte-identically how the formal cap has always been treated.
- **The publish** — the operator's by registration.

---

## 5. ⏭️ Operator

**The decision is in `nf_inj4b_ship_operator_packet.md`.** The one thing to read first:

⚠️⚠️ **MERGING THIS PR IS THE DEPLOY.** The board is published by `sports_nfl_board_publish_schedule`
— `default_status=RUNNING`, `export_draft_board_json --publish`, daily 07:15 America/Los_Angeles,
from the box image built from `main` on merge. There is **no** separate publish step to approve
later, which is why NF-C9's copy and the changelog line are in this PR rather than a follow-up. If
the answer is no, the PR does not merge — the wiring **is** the serve.

Post-publish, one command (LAPTOP, ~30 s), proven two-sided:

```
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_ship_battery \
    --verify-published
```
