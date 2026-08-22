# NF-INJ1 — draft-projection injury awareness + scenario coherence: DIAGNOSIS

**Status:** investigation complete · two defects diagnosed and measured · guards shipped ·
model fix pre-registered for §0.5 (`nf_inj1_preregistration.md`). `best_alpha = 0` — no bet rides
on any of this; the exposure is the paid `/fantasy/nfl/projections-full` surface and the draft board.

**Measured against:** the live published `artifacts/draft_board_json/2026/projections.json`
(`generated_at` 2026-08-17T04:33Z, 868 players, `projection_source = nf1_5`), the two build frames
(`nfl_fantasy_season_projections_2026.parquet` = MVP-1, `nf1_5_season_projections_2026.parquet` =
served), the laptop `sports.duckdb`, and the live `nfl/raw/sleeper_injuries` S3 Delta. Read on
2026-08-20/21.

---

## 0. Headline

Two defects, and **they are the same defect seen twice**.

1. **Coherence.** The served board carries **9 players whose stat line is impossible at their own
   expected games** — Easton Stick at 153.4 pass attempts over 1.9 games (**80.7 per game**, against
   an all-time realized maximum of 45.4). All 9 are QB.
2. **Injury awareness.** The current-injury feed **is** consumed (the story's Q1 hypothesis is
   refuted), but the board was built on a **20-day-old** copy of it while the feed itself was 15h
   fresh. **18 currently-PUP/IR players project at their healthy rate**, three of them draftable.

The link: MVP-1's point is `per-game rate × expected games`, so it **embeds availability**. NF1.5
then permutes those points within each position as if they were pure quality — which redistributes
the availability discount from healthy players to unavailable ones, and leaves `proj_games` behind.
**8 of the 13 injury-capped board rows have their point scaled back UP by that step.**

---

## 1. Facet 1 — Q1 answered: the current-injury feed IS consumed

The story asked whether `season_projection.py` / `availability_mixture.py` consume
`sleeper_injuries_source` / `injury_log_source`, or only historical positional rates. Grepped every
consumer (INC-27), then verified by execution rather than by reading (NF-C0e: wired ≠ invoked).

| Component | Verdict | Evidence |
|---|---|---|
| `sleeper_injuries_source` → `stg_nfl_sleeper_injuries` | ✅ **WIRED AND INVOKED** | `run_season_projection.load_forward_roster_status` reads it (Sleeper preferred, nflverse `stg_nfl_weekly_rosters` fallback, `_coalesce_forward_status`) → `proj_status` → `season_projection.injury_availability_games` caps `proj_games` toward 4.0 games (RES/PUP/NFI) / 7.0 (SUS) at blend 0.7. **13 of 794 served rows carry a cap** and their games are visibly discounted (Kittle 7.3, not 16). |
| `injury_log_source` | ⛔ **display only, by design** | Sole consumer is `export_player_history_json.py` (the NF3.3 player-history overlay). Never reaches a projection. Its source `stg_nfl_injuries` (nflverse weekly report) **holds no 2026 rows at all** — latest season is 2025 — so there is no in-season injury-report channel for the 2026 board yet. |
| `availability_mixture.py` | ⛔ **not on this path** | It is **NF-W4 — the WEEKLY availability mixture, a recorded null (×4)**. Its only importers are research runners and the `fp_*` weekly-assembly family. The story's anchor is wrong for the season board: season availability lives in `season_projection.expected_games` + `blend_usage_into_games` + `injury_availability_games` + `absence_return_games`. |

⇒ **The gap is not "unwired". It is input staleness at the board build, plus a coarse cap.**

### 1.1 The staleness is between a healthy feed and the board — not in the feed

| Layer | State | Reading |
|---|---|---|
| S3 Delta `nfl/raw/sleeper_injuries` | **v6, 15.4h lag, SLA 36h → OK** | NF-INFRA1's fix is working; the box lands daily. |
| Board's copy (`stg_nfl_sleeper_injuries`, laptop DuckDB) | `max(ingested_at)` = **2026-07-26** | ~26 days stale as of this read. |
| Served payload stamp | `input_vintage.sleeper_status_as_of = 2026-07-26` beside `depth_chart_as_of = 2026-08-14` | **NF-FRESH2 P2 already made it VISIBLE. Nothing ACTED on it.** |

The staging model reads the Delta directly, so the only thing between the fresh feed and the board
is a `dbt run --select stg_nfl_sleeper_injuries` + a rebuild that nobody was required to do.

### 1.2 What that costs on the live board (measured against the full coalesced status, any source)

Live feed: **29 flagged** (21 RES + 8 PUP). Board's copy: **14**.

* **18 currently-flagged players are on the served board with NO cap applied**, incl.
  **Alec Pierce (WR, PUP) 15.2 g / 134.5 PPR**, **Jayden Higgins (WR, RES) 12.9 g / 114.4 PPR**,
  **Ricky Pearsall (WR, RES) 9.5 g / 108.4 PPR** — 3 draftable (≥100 PPR).
* **5 players are still being discounted who have since cleared** (McIntosh, Tim Patrick, Terrell
  Jennings, Fidone, Dippre).

This is exactly the story's premise — "expected_games too high on exactly the players a drafter
needs it right on" — but the cause is a refresh gap, not a missing mechanism.

### 1.3 Two further limits, recorded but not defects

* **The mapped vocabulary is deliberately narrow**: only the long-absence set (PUP / IR→RES / NFI /
  SUS). Weekly game-report tags (Questionable/Doubtful/Out) are left unmapped on purpose — NF-D2
  slice 5 found that channel weak/confounded. Reasonable for a *season* board; re-open only with a
  bake-off.
* **The cap is a hardcoded constant**, `{RES: 4.0, PUP: 4.0, NFI: 4.0, SUS: 7.0}` at blend 0.7,
  described in-code as "empirical" but not fitted in-fold and not re-validated since NF-D2. A PUP
  designation in March and one in late August are the same 4.0 games. → §0.5 candidate.

---

## 2. Facet 2 — the coherence mechanism, and it is NOT a scenario mixture

The story hypothesised that `expected_games` and the counting stats "come from different branches of
MVP-1's scenario mixture". **Refuted.** MVP-1 has no such decoupling:

```
season[s] = shrunk_per_game_rate[s] * proj_games          # coherent BY CONSTRUCTION
```

and every downstream availability step (`mover`, `env_tilt`, `injury_availability_games`,
`absence_return_games`) rescales the *whole* line by `new_games / old_games` and re-scores. Measured:
**MVP-1 has 1 violating row on 767** — and that one is a rookie from a different path (§2.2).

### 2.1 The actual mechanism: an ordering step that moves the line but not the games

`run_nf1_5.build_season_projection` injects `_reorder` as MVP-1's `veteran_postprocess`. That calls
`nf1_model.apply_learned_ordering` → **`apply_learned_level`**, which rescales:

```python
_RAW_SCALE_COLS = ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td", "proj_pass_int",
                   "proj_rush_att", "proj_rush_yds", "proj_rush_td",
                   "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td")
```

**`proj_games` is not in that tuple.** The ordering hands each player a *different* player's point
level from the position's own multiset and rescales his line by up to the 3.5 clamp to reach it,
while his expected games stay exactly where MVP-1 left them.

Easton Stick, measured end-to-end:

| | expected games | pass att | att/game | PPR |
|---|---|---|---|---|
| MVP-1 | 1.86 | 57.7 | **31.1** ✅ | 26.7 |
| NF1.5 (served) | 1.86 | 153.4 | **82.7** ⛔ | 71.1 |

`nf1_scale = 2.88`. The games never moved.

### 2.2 Blast radius

Against a **derived** envelope — the maximum per-game rate any real NFL player-season posted
2006–2025 (11,190 player-seasons; QB pass att 45.44, pass yds 371.20, RB carries 27.38, WR rec yds
122.75). It is a **max**, so a breach is impossibility, not improbability, and cannot false-alarm.

| Frame | Violating players |
|---|---|
| MVP-1 | **1 / 767** (0.13%) — Fernando Mendoza, a **rookie** |
| NF1.5 (served) | **9 / 777** (1.16%) — **all QB** (8.5% of QB; **0** at RB/WR/TE) |

The 9: Case Keenum (85.0 att/g), Bailey Zappe (81.1), Easton Stick (80.7), Sam Howell (75.7), Sam
Ehlinger (74.8), Will Levis (61.9), Aidan O'Connell (60.3), Brandon Allen (48.5), Fernando Mendoza
(49.6). Concentrated at low availability: **12.7% of rows with `g < 3`** violate, vs 0–0.5% elsewhere.

**Two distinct producers, and they need separate fixes:**

* **8 veteran QBs** — the NF1.5 ordering step above.
* **1 rookie (Mendoza)** — a *different* defect in `season_projection.rookie_projection`: the rookie
  line is allocated to hit an `fp_target` via median stat-per-point ratios and then rescaled so the
  scored line equals that target, while `proj_games` comes independently from the slot-bucket
  historical mean. **The two are never reconciled** — the same class (a point-level assignment that
  moves the line and not the games), a different code path.

**Why QB-only?** Two reasons, both structural rather than lucky: QB has a hard, narrow physical
per-game anchor (attempts/game), and QB has by far the widest availability spread on a roster
(a starter at 17 games beside a QB3 at ~1). A 2–3× line rescale on a 1-game backup is visible; the
same rescale on a 14-game WR is not.

### 2.3 The decoupling is board-wide, even where it is not yet *impossible*

Measured **within the served frame only** (`nf1_scale` is the ordering step's own per-row rescale,
recorded in-run — no cross-vintage comparison; an earlier cut comparing the two parquet files was
discarded because they are 7 days apart and MVP-1's predates NF-TR2b entirely, the NF-D10 lesson):

| expected games | n | median `nf1_scale` | % upgraded |
|---|---|---|---|
| [0, 2) | 22 | **1.906** | 91% |
| [2, 4) | 94 | 1.092 | 73% |
| [4, 6) | 118 | 1.039 | 58% |
| [9, 12) | 136 | 1.000 | 49% |
| [15, 18) | 63 | 0.958 | 17% |

**Spearman ρ(expected games, `nf1_scale`) = −0.187, p = 6.6e-07, n = 697**, and it is significant at
every position: QB −0.299, RB −0.252, TE −0.236, WR −0.126. ⭐ **SUPERSEDED BY §7.2** — a
matched-vintage rebuild put the true figure at **−0.213 (p = 1.4e-08)**, by both routes. The clamp saturators sit at low `g`
(4 of 7 have `g < 3`).

⇒ **The ordering step systematically transfers point level from high-availability players to
low-availability ones.** QB is where it crosses into the physically impossible; at RB/WR/TE it is
the same transfer, just still inside the envelope.

### 2.4 Why — and an honest alternative reading

The learner is **not** availability-blind: `expected_games` and `injury_cap_ratio` are both in
`nf1_model.FEATURES`. But neither reaches the published top-6 importance at any position, while
`pergame_fp` dominates (**21.3% at QB**, 14.0% pooled). So the ordering is driven by per-game *pace*,
and pace is exactly the axis on which a shelved backup with one good stale season looks strong.

**The alternative reading, stated because it is genuinely live:** maybe the learner is *right* that
Stick's 26.7-PPR MVP-1 projection is too low, and the real error is that `g = 1.86` is too pessimistic.
Under that reading the point is fine and the *games* are wrong.

**This does not need settling to act, and that is the useful part.** Under *either* reading the
served pair is impossible — 82.7 attempts per game is not a defensible number in any world. So the
guard can ship now on the ratio alone, and *which half moves* is precisely the §0.5 question.

---

## 3. Where the two facets meet

`injury_availability_games` discounts a flagged player's games **and** his line coherently. Then the
ordering step scales his line back up and leaves the games discounted. Of the 13 injury-capped rows
on the served board, **8 have `nf1_scale > 1`**:

| player | status | `proj_games` | `nf1_scale` |
|---|---|---|---|
| Kenny McIntosh | PUP | 2.82 | **2.14** |
| Isaac Guerendo | PUP | 5.19 | **1.73** |
| Julian Hill | RES | 5.40 | **1.63** |
| Tip Reiman | PUP | 5.00 | **1.61** |
| Thomas Fidone II | PUP | 4.51 | **1.58** |
| George Kittle | PUP | 7.32 | **1.29** |
| Zach Charbonnet | PUP | 6.90 | **1.12** |

So the answer to "does a currently-injured player project down?" is: **his games do; his points
partly do not.** That is one defect, not two — the availability discount lives in a quantity the
ordering step is free to permute.

---

## 4. What shipped in this story (no model change — nothing here moves a projection)

1. **`projection_coherence.py`** — a pure module: the derived envelope + its provenance,
   `row_violations` / `coherence_summary` / `format_summary`, and
   `assess_injury_input_freshness` (bar = **2× the feed's own declared INC-41 SLA**, pinned against
   `sports_delta_freshness` so the two cannot drift apart).
2. **`export_draft_board_json.report_publish_coherence`** — a publish-time check beside NF-K1's,
   reading the **staged bytes**. **ALERT-tier by default**, `--strict-coherence` refuses. The count
   is written onto `manifest.json` so it is visible on the served payload, not only in a run log
   (E11.30). It reports **NOT APPLICABLE** rather than "clean" for the league-board blobs, which
   carry no counting line and on which the envelope structurally cannot fire (NF1.7 (a) / NF-D20).
3. **17 tests + an 8-break RED proof** (`red_proof_nf_inj1.py`), 8/8 red, each clause with its own
   isolating fixture (NF-D17).

**⚠️ The ALERT-vs-HALT default is a PM decision and is deliberately not mine.** NF-K1 refuses because
a missing position is unusable and the remedy takes minutes. Here the remedy is a §0.5 model change;
refusing would freeze every publish through draft season over 9 backup QBs on an otherwise sound
868-player board. `--strict-coherence` flips it with no code change.

---

## 5. Scoped fix plan

### 5a. Immediate, no model change — **operator, today**
Refresh the injury input and rebuild. This alone corrects all 23 misprojected players (18 uncapped +
5 wrongly capped) including three draftable WRs, during draft season. Commands in the handoff.

### 5b. The coherence fix — **§0.5, pre-registered** (`nf_inj1_preregistration.md`) → **FUNDED as NF-INJ2** (§8.2)
Level-adjacent ⇒ triggers the whole-board placement read (`run_nf_tr2b_placement_read`) **and** the
interval revalidation (`run_interval_revalidation`) per NF-D16/D21, and — because it changes a
served *point* — the NF-TR2b multiplicative-correction caveat that the VOR "shield" is additive-only
and does **not** hold under the two superflex configs.

Candidate arms (declared forward, ≥3 + a matched foil + degenerates):
* `incumbent` — today's season-point multiset permutation.
* `rate_permute` — permute the per-game **rate** multiset, then multiply by each player's **own**
  `proj_games`. Coherent by construction; availability becomes un-permutable. *The principled arm.*
* `stratified` — permute within availability strata, so a level is only exchanged between players of
  comparable `g`.
* `feasibility_clamp` — bound `nf1_scale` by the envelope. Minimal, but treats the symptom.
* Anchors: an oracle floor, a `no_reorder` degenerate, and a matched foil isolating the games channel.

### 5c. The rookie path (§2.2) — separate, smaller → **low priority, no standalone story** (§8.3)
`rookie_projection` reconciles `fp_target` and the slot-bucket games not at all. Fixable in the same
family but on its own registration; 1 row today, and it is the only MVP-1-side violation.

### 5d. The injury cap itself (§1.3) — §0.5 candidate → **scheduled as NF-INJ3, AFTER NF-INJ2** (§8.3)
`{RES: 4, PUP: 4, NFI: 4, SUS: 7}` is unfitted and status-only. A fitted current-status →
expected-games prior (with recency of the designation as a covariate) is the honest successor.
**Keep it separable from 5b** — a level change and an availability change must not be bundled, or
neither is attributable (NF-W7d).

---

## 6. Reusable lessons

* **A within-group permutation of a quantity that EMBEDS a second dimension redistributes that
  dimension.** MVP-1's point is `rate × games`; permuting it as if it were pure quality moved the
  availability discount between players. Before permuting/remapping a composite quantity, ask what
  else is inside it.
* **A rescale-to-target that enumerates its columns will silently omit the one that is not
  production.** `_RAW_SCALE_COLS` is correct about every stat and wrong about the pair; the omission
  is invisible to a schema, a scorer, and every test in the repo.
* **When two served quantities are each defensible and their RATIO is not, guard the ratio.** It
  indicts the pair without first settling which half is wrong — so a guard can ship ahead of the
  model change instead of waiting on it.
* **A guard's "0 violations" needs an applicability flag.** The league-board blobs carry no stat
  line, so the check cannot fire there; reporting that as clean would have been a textbook vacuous
  pass on 13 of the 14 published files.
* **Making staleness visible is not the same as acting on it.** NF-FRESH2 stamped
  `sleeper_status_as_of` onto the served payload and it was *correct the whole time* — the board
  still shipped 20 days stale, because nothing read the stamp back.
* **Two artifacts of different vintages are not an A/B.** The first cut of §2.3 compared the MVP-1
  and NF1.5 parquets (7 days apart, one predating NF-TR2b) and read the TR2b constant as a finding.
  The vintage-free instrument — `nf1_scale`, recorded in-run — was already on the row (NF-D10).


---

## 7. POST-PUBLISH VERIFICATION (2026-08-21, operator ran the §5a chain and published)

The operator ran steps (a)–(f). `generated_at` 2026-08-21T05:23:33Z; `sleeper_status_as_of`
**2026-08-20T13:30:16Z**; `[METRIC] nf_inj1_injury_input_freshness=OK lag_hours=15.9`. ⭐ Both
projection frames were rebuilt in the **same run**, which finally makes the MVP-1 ↔ NF1.5 A/B
matched-vintage (`proj_games` identical to 3.55e-15) — the comparison §2.3 could not make.

### 7.1 Facet 1 — FIXED, verified on the published artifact ✅

All 9 spot-checked newly-flagged players moved **down**; the full flagged cohort is 23 rows.

| player | status | expected games | PPR |
|---|---|---|---|
| Alec Pierce | PUP | 15.16 → **7.30** | 134.5 → 118.3 |
| Jayden Higgins | RES | 12.86 → **6.70** | 114.4 → 106.8 |
| Ricky Pearsall | RES | 9.50 → **5.60** | 108.4 → **45.0** |
| Luke Musgrave | PUP | 12.30 → **6.50** | 39.6 → 27.7 |
| Tyrell Shavers | PUP | 9.71 → **5.70** | 38.0 → 18.6 |

### 7.2 …and the same run measured §3 directly, on live data

Note the ratios above: **Pierce's expected games HALVED while his points fell 12%.** With both frames
at matched vintage this decomposes exactly. On the 23-row injury-capped cohort, MVP-1 applies the cap
to games *and* line, and the ordering step then hands the point back:

* **median NF1.5 ÷ MVP-1 point = 1.292; 18 of 23 scaled UP** (Higgins ×2.32, Pierce ×1.67, Guerendo ×1.81)
* **aggregate 563 → 769 PPR = +36.4% of the availability discount given back**, on precisely the
  cohort the discount exists for.

Matched-vintage whole-board gradient (this **supersedes** §2.3's −0.187): median point ratio **1.942**
at `g < 2` → **0.955** at `g ≥ 15`; **ρ(games, point ratio) = −0.213, p = 1.4e-08, n = 697** — and
ρ(games, `nf1_scale`) is **−0.213** to three decimals, i.e. the vintage-free instrument was measuring
exactly the right quantity. Veterans with `g < 6`: +14.8% aggregate (§2.3's contaminated cut said
+18.1%).

### 7.3 Two numbers moved — one is nothing, one is undecomposable

**Violations 9 → 10.** The new row is **Spencer Rattler** (QB, `g` 6.50, 359.8 att = 55.4/g, scale
2.10). He is **not** injury-flagged, so this is not the refresh. The market also refreshed in the same
run (ADP 08-16 → 08-20, ECR 08-15 → 08-21) and the pre-refresh frame was overwritten, so ⛔ **this is
not attributable** — recorded as observed, not explained.

**⚠️ Clamp saturation 19 → 31 — my first read of this was WRONG and is corrected here.** It is
**entirely the LOW end**: high-end saturation (`≥3.4999`, the direction that manufactures an
impossible stat line) is **7 → 7, unchanged**; the low end (`≤0.3001`, downgrades the line cannot
reach) went **12 → 24**, median `g` 10.32 — i.e. healthy players marked down hard, not injured ones
inflated. **The injury refresh did not aggravate the coherence defect.** Same caveat as Rattler: two
inputs changed at once, so the low-end doubling is observed, not attributed.

### 7.4 Stick-class rows are NOT coherent — as designed

`Easton Stick` is byte-identical (153.4 att / 1.86 g / 80.7 per game) and the board published with the
ALERT firing on 10 rows. That is the intended outcome of this story, not a miss: the AC's
"Stick-class players are coherent" is gated on the §0.5 model change in
`nf_inj1_preregistration.md`, which is the half that is *not* shipped here.

**What §7.2 changes for that study:** it replaces an inferred mechanism with a measured effect size.
The pre-registered `rate_permute` arm now has a concrete target — restore the 36.4% give-back on the
injury-capped cohort without losing held-out ordering ρ — and a matched-vintage baseline to be scored
against.


---

## 8. PM DECISIONS (2026-08-21) — recorded; NF-INJ1 closes here

All three items in §5 were put to the PM. The decisions, and the trigger conditions that go with
them, are recorded here so a later reader does not have to reconstruct them.

### 8.1 Decision 1 — the coherence guard stays at **ALERT** ✅

**DECIDED: Option A.** The guard measures and pages; it does not block. The rationale is the coupling,
which is the part that is easy to miss: **HALT would have blocked the 2026-08-21 republish** — the one
that corrected 23 injured players including three draftable WRs (§7.1). Blocking publishes blocks
**injury refreshes too**, so HALT trades a cosmetic defect on undraftable backup QBs for a real one on
draftable players. `--strict-coherence` exists and is deliberately left OFF.

**⏰ Option C is the documented fallback, and this is its TRIGGER — recorded so it is not forgotten:**

> **Suppress the stat line on violating rows only** (points and expected games still render; the
> impossible counting stats do not) **IF EITHER**
> **(a)** NF-INJ2 is not funded, **OR**
> **(b)** NF-INJ2 runs and does not clear its gates.

C is **not** needed today: the affected rows are undraftable backups, there are **no paying
subscribers yet**, and the funded fix removes those rows anyway.

**⚠️ AND A SECOND TRIGGER, which is time-based rather than outcome-based — revisit C *immediately* if
paying subscribers arrive before NF-INJ2 lands.** An impossible number on a paid surface is a
credibility cost for an honest-analytics product even on a backup, and that cost does not depend on
whether anyone drafts the player.

### 8.2 Decision 2 — the §0.5 fix is **FUNDED**, as its own story ✅

**DECIDED: fund it, and run it as NF-INJ2 — a separate follow-on story off the existing
pre-registration, NOT an extension of this diagnosis session.**

The PM's framing, recorded because it is the correct reading of the evidence and sharper than the
"impossible stat line" headline: **the give-back un-discounts injured players.** It hands back +36.4%
of the availability cut on 18 of 23 flagged players and it hits DRAFTABLE ones (Pierce ×1.67, Kittle
×1.29, Higgins ×2.32) in the exact draft-season window where it matters most. **That is the founding
injury priority running backwards** — an injured player must project down, and today he partly
projects back up. The rate-permutation reformulation removes the give-back and the 10 impossible rows
in one principled change.

Confirmed as pre-registered, with three readings the PM ratified explicitly:
* **a TIE on the selecting metric still ships** — coherence is a correctness constraint the incumbent
  *violates*, so this is **not** the E2.1-r inversion; it is the pricing-vs-discrimination family rule
  that a tie ships when the incumbent fails a hard constraint;
* a placement/interval refusal is recorded **`CONSTRAINT_REFUSED`** with **no "more data" re-test
  trigger** (NF-D18);
* it moves served point levels ⇒ the whole-board placement read **and** interval revalidation
  (NF-D16/D21) both gate it.

⚠️ **Verify against the CURRENT board vintage** — the board is republished by hand and moved twice
during NF-INJ1 alone; a study scored against a stale frame measures a board nobody is served (§7.2's
own lesson, and the CLV-class trap).

### 8.3 Decision 3 — 3b is **NF-INJ3, scheduled AFTER NF-INJ2**; 3a is low priority ✅

**DECIDED as recommended.**

**NF-INJ3 (§5d — the hardcoded `{RES: 4.0, PUP: 4.0, NFI: 4.0, SUS: 7.0}` caps).** The more
consequential of the two: it governs the expected games of all 23 flagged players, the constants are
unfitted and unrevalidated, and they ignore **when** the designation happened — a March PUP and a
late-August PUP both collapse to 4.0, which is clearly wrong. Own §0.5 story; make the caps
designation-timing-aware, ideally fitted rather than hardcoded.

⛔ **Do NOT bundle it with NF-INJ2.** NF-INJ3 changes the same quantity (availability / expected
games) that NF-INJ2 is trying to stop mis-handling, and mixing a level change with an availability
change makes neither attributable (NF-W7e's measured non-additivity).

**3a (the rookie path, §5c — 1 row today).** Low priority, no standalone story: fold it into the next
rookie-path touch.

### 8.4 NF-INJ1 status

**CLOSED** as the diagnosis + the ALERT-tier guard (PRs #991 / #993, both merged to `dev`).
`best_alpha = 0` throughout. Carried forward: **NF-INJ2** (the funded fix) and **NF-INJ3** (the caps),
both as separate stories in `nfl_fantasy_story_prompts.md`.
