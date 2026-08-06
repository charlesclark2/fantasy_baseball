# NF-W0b — canonical cross-vendor entity resolution (v3 §12A)

**Story:** NF-W0b (V0-infra). **Scope (as reconciled by NF-W0):** apply the §12A framework — the
match-order ladder, the four monitors, fall-back-and-flag, fail-closed thresholds — to the **two**
joins the lake does not already resolve: `snap_counts` (the NF-W1-critical one) and name-only Odds
API prop identities. ⛔ NOT a from-scratch canonical-id build; the lake already carries espn /
sportradar / pff / pfr / yahoo / sleeper / esb / smart ids. `best_alpha` N/A — no modelling, no
serving change. Branch `nf-w0b-entity-resolution`.

**Service:** `quant_sports_intel_models/football/nfl/entity/` (pure pandas, fast-gate testable;
`run_entity_resolution.py` is the DuckDB/S3 lake driver). **Guards:**
`betting_ml/tests/test_nf_w0b_entity_resolution.py` (47) +
`sports_dbt/tests/nfl/assert_nfl_snap_bridge_has_no_silent_zero.sql`.

---

## 1. ⭐ TOP — the defect, measured on the live lake

NF-W0c flagged that `fct_player_week`'s snap join "coalesces a `pfr_id` miss to `offense_pct=0.0`".
Measured here, it is worse than a coverage gap and it has a name:

| | measured (2022–2025) |
|---|---|
| `weekly_rosters.pfr_id` NULL share | **25–53%** per season |
| snap rows with no per-season bridge | **19–46%** per season |
| distinct 2024 snap players bridged by `pfr_id` | 1,449 of 2,192 (**66%**) |

**Why a fabricated zero is worse than a NULL, and the reason this blocks NF-W1.** A snap share is a
rate in [0, 1] where **0.0 is a legal observation** — "dressed, played no offensive snaps". So the
zero manufactured by a join miss is *indistinguishable from a real one*: no error, no NULL, nothing
for a coverage gate to see, and a model trains on it as fact.

The live case, and it is not a corner: **Michael Woods II played 100% of Cleveland's offensive snaps
in week 15 of 2024, and the fact serves him a 0.00 snap share** (also 0.88 in wk 14, 0.86 in wk 17).
`snap_counts` writes "Michael Woods II"; that season's roster row writes **"Mike Woods"** with a NULL
`pfr_id`. A nickname, not a suffix — normalization cannot fold it, and it should not try to.

The same root cause hits the second consumer in the opposite, equally invisible way:
`run_nf_w0_audit.load_sources` INNER-joined snaps to the bridge, **silently dropping 19–46% of snap
rows per season** — the frame simply had fewer rows and every coverage number still read healthy.
That is the §12A `silent_drop_count` surface, which must equal 0.

## 2. What actually fixes it — and it is not a cleverer name match

| lever | unresolved snap rows |
|---|---|
| per-season `pfr_id` bridge (the incumbent) | 19–46% |
| \+ exact name + team + position **group** | 11.6–28.8% |
| \+ name + team, position relaxed | 0.5–1.5% |
| ⭐ \+ **vendor map keyed on the id ALONE** (not season+id) | **0.68–1.24%**, and `high_value_unmatched_count` **0** |

**A `pfr_id` is a stable property of a PLAYER; its presence in one season's roster row is not.**
Keying the crosswalk on the id alone recovers Woods at **tier 1** off another season's row. That one
widening — not the fuzzy rung — is what rescues the high-value cohort. Both consumers keyed on
(season, id), which is why both missed it.

A second, structural finding: **the position vocabularies differ in GRAIN, not spelling.**
`snap_counts` writes T/G/C/NT/DE/FS (19 labels), `weekly_rosters` writes OL/DL/DB (11). An exact
`position = position` join does not fail on a typo, it fails on *every offensive lineman* — hence
`position_group`.

## 3. Production monitors (2022–2025, full ladder)

| season | unmatched_rate | low_confidence_rate | high_value_unmatched | **silent_drop** | fuzzy matches | fail_closed |
|---|---|---|---|---|---|---|
| 2022 | 0.0124 | 0.000499 | 0 | **0** | 13 | no |
| 2023 | 0.0088 | 0.000532 | 0 | **0** | 14 | no |
| 2024 | 0.0101 | 0.000228 | 0 | **0** | 6 | no |
| 2025 | 0.0068 | 0.0 | 0 | **0** | 0 | no |

Rung mix (2025): 21,572 tier-1 · 4,859 tier-3 · 1 tier-4a · 180 unresolved. The 1,012-row residual
across all four seasons is **entirely OL/DL/LS** — positions whose snap share no fantasy projection
reads — and every row is in `nf_w0b_entity_qa_queue.csv`, flagged, never zeroed.
Artifacts: `nf_w0b_entity_report.json` · `nf_w0b_entity_monitors.csv` ·
`nf_w0b_vendor_id_coverage.csv` · `nf_w0b_fuzzy_threshold_calibration.csv`.

## 4. ⭐ The fuzzy threshold was calibrated, and the measurement overturned the obvious answer

A fuzzy rung is trivially easy to tune the wrong way: lower the threshold, watch `unmatched_rate`
fall, declare victory. But that rate is a **yield**, and yield is silent about whether the new
matches are *right* — a join that confidently merges the wrong players scores a BETTER
unmatched_rate than one that honestly abstains. So the threshold comes from a **blind-vendor-id
control** (`--calibrate`): take the 43,013 snap rows tier 1 already resolves (a known, independent
answer), **hide the vendor id**, force them through the name rungs, and compare.

| threshold | 0.80 | 0.84 | 0.86 | 0.88 | 0.90 | 0.92 | **0.95** |
|---|---|---|---|---|---|---|---|
| fuzzy matches | 559 | 500 | 420 | 263 | 201 | 132 | 64 |
| **wrong merges** | 65 | 64 | 42 | **34** | 16 | 16 | **0** |

Every value below 0.95 buys yield with errors ⇒ **0.95**. The consequence is deliberate and worth
stating plainly: the nickname that motivated the story scores **0.8913** and is therefore *not*
auto-matched by the fuzzy rung. Nicknames belong in the reviewed crosswalk (tier 2) or manual
review (tier 5) — a threshold loose enough to catch that one makes 34 wrong merges.

### 4a. The control caught a real defect in tier 3 — twice, at two different scopes

**Attempt 1 — uniqueness per (name, team, position-group).** The NFL carried **two "Jonah
Williams"** in 2024–25 (an OT and an edge). The OL cell held exactly one candidate, so tier 3
matched it at 0.95 confidence and got it **wrong on all 15 rows**. Position cannot arbitrate a
duplicate name, because the vendors disagree on position grain — the very reason `position_group`
exists.

**Attempt 2 — uniqueness inside the block.** Still wrong, and this is the subtle part: ARI's roster
that week lists only ONE Jonah Williams, so *within the block the name looks perfectly unique*. The
other one is elsewhere in the league. **A block-local uniqueness test cannot see a collision it does
not contain, so it certifies exactly the case it needs to catch.**

**Fix:** ambiguity is judged over the **season** — the population the true player could have come
from. If a normalized name maps to more than one canonical player anywhere in the season, every name
rung abstains and the row goes to review. Measured at 0.95: wrong merges **15 → 0** for 489 extra
abstentions (1.1% of the control). The trade is the right way round — an abstention is visible,
queued, and fixable with one reviewed row; a wrong merge is invisible and misattributes one player's
snaps to another.

## 5. What shipped

- **Service** — `entity/`: `names` (shared normalizer + position groups + a pinned Jaro-Winkler),
  `crosswalk` (the 13 §12A fields, built from the vendor ids the lake already carries; 74,800 rows),
  `resolver` (the 5-rung ladder), `monitors` (the four monitors + fail-closed + the QA queue),
  `snap_bridge`, `props_identity`, `run_entity_resolution` (`--report` / `--calibrate` / `--strict`).
- **`fct_player_week`** — cross-season `pfr_bridge` (abstaining on an id claimed by two players);
  the four `coalesce(sc.*, 0)` removed; new **`snap_source_tier`** (`observed` / `no_snap_row` /
  `bye`) so a *real* 0.0 stays tellable from an unknown.
- **`sat_snap_counts_weekly`** — reads the resolved columns off the fact; the duplicate bridge is
  gone (two copies drift, and the satellite's copy is where the zero would return unnoticed).
- **`run_nf_w0_audit`** — the INNER join replaced by the ladder: **19.22% → 0.84%** unresolved,
  `silent_drop=0`, and the residual announced ALERT-tier rather than skipped quietly. Its own gates
  still hold (parity PASS, canary DETECTED).
- **Fail-closed policy** — `silent_drop_count > 0` fails closed *unconditionally* and has no
  threshold knob (a configurable "0" is a 0 someone eventually configures to 1). An **unevaluable**
  run reports `None`, never 0.0, and fails closed under `require_evaluated` (NF1.7 (a)).
  `max_high_value_unmatched` defaults to *report, do not gate* — a hard 0 would fire every week a
  practice-squad elevation out-runs the roster feed, which is a real condition, not a defect.

## 6. Name-only props: the rule is mechanical, not documentary

§12A: "name-only props cannot be joined on fuzzy name alone." An Odds-API outcome carries a player
name and nothing else. The constraint comes from the **event** — a prop belongs to a game, a game has
two teams, so a candidate must be on one of them (~106 players, not ~2,000). A prop whose event teams
cannot be resolved gets an **empty block**, and `ResolutionSpec.allow_name_tiers` is then False, so
the ladder refuses tiers 3–4 outright. A guard proves the same *exact* name that resolves with an
event fails to resolve without one. A **partial** block is refused identically — a spec declaring
(season, week, team) whose frames supply only `season` would fuzzy-match against the whole league,
i.e. reach the forbidden global match by accident rather than by choice.

## 6a. ⭐ The props leg, run against the REAL payload (2023–24, added 2026-08-06)

Leg 2 was unit-tested but had never touched real data. Running it over the live
`odds_nfl_props_historical` (570 events → **601,933 outcome rows**) found three things no fixture
could — the "second real payload" rule, again earning its keep.

**(a) It did not finish.** The per-row path ran >10 minutes without completing: the fuzzy rung is
O(rows × candidates). But identity depends only on `(season, event teams, name)`, and 601,933 rows
carry just **28,158 distinct identity tuples** (21×) — a prop feed repeats the same player across
every market, book and side. `resolve_prop_players` now resolves distinct identities and broadcasts
back (exact, not an approximation — the same key is the same question), with a row-count assertion
so a fan-out can't slip through. **>10 min → 19.5 s.**

**(b) Every exact match was mislabelled as a fuzzy one — and it failed the build closed.** A source
may carry its team constraint in the BLOCK rather than in its own columns; props are exactly that.
Tiers 3/4a joined on `_team` regardless, comparing the source's placeholder `""` against the
target's real team, so those rungs could never fire and **586,850 EXACT-name matches fell through to
the fuzzy rung**, were scored into the low-confidence band, and drove `low_confidence_rate` to
**1.0**. Every unit fixture happened to supply a team column, so none of them could expose it. Fixed
(join only on attributes the source actually supplies) + regression test, RED-proven.

**(c) The result, and it fails closed — correctly.**

| monitor | value |
|---|---|
| rows in / out | 601,933 / 601,933 (**silent_drop 0**) |
| by method | 584,756 exact (tier 4a) · 2,094 fuzzy · 15,083 unresolved |
| `unmatched_rate` | **0.0251** — exceeds the 0.02 bar ⇒ **fail_closed** |
| `low_confidence_rate` | 0.0036 (was 1.0 before the (b) fix) |
| `high_value_unmatched_count` | 1,008 (target-book rows) |

The 15,083 unresolved decompose cleanly:

| | rows | what it is |
|---|---|---|
| duplicate-name abstention | **8,875 (59%)** | **CORRECT** — two Josh Allens, two Lamar Jacksons, two Michael Thomases, two DJ Turners. The season-scope rule refusing to guess. |
| name on no roster that season | 5,815 (39%) | non-player outcomes (`"No Touchdown"`), vendor disambiguation strings (`"Michael (Saints) Thomas"`), and nickname variants (`"Chig Okonkwo"` vs `"Chigoziem Okonkwo"`, `"Gabriel Davis"` vs `"Gabe Davis"`) |
| on a roster, not on the event teams | 393 (2.6%) | mid-season moves / practice-squad churn |

⛔ **The threshold was NOT retuned to make this pass.** 0.02 was pre-registered from the SNAP leg's
baseline (0.68–1.24%); props genuinely sit above it, and relaxing a bar because it caught something
is the E2.1-r inversion. **The props leg therefore needs its own pre-registered threshold, derived
from the characterisation above rather than reverse-engineered from this run** — a deliberate
follow-up, not a silent edit here. Note that 59% of the residual is the ladder working as designed,
so the right props bar is almost certainly not 2%.

## 7. Honest limits

- **The served board does not change — MEASURED, not reasoned (§9).** `run_season_projection`
  aggregates snap share as `avg(offense_pct) filter (where … > 0)`, so fabricated zeros were
  excluded there anyway. Re-computing that exact aggregation both ways over 2020–2025 gives
  **0 changed player-seasons of 20,518, max |Δ| = 0.0** (consistent with NF-W0c finding the served
  numeric path clean). The corruption was in the **NF-W1 training frame** and in any future reader
  of raw `offense_pct` — precisely why this story gates NF-W1 rather than the live board.
- **The two-sided prop collapse is unreachable** under the current ambiguity scope and is labelled as
  such in the source rather than left looking tested — RED-proving it is what established this.
- **`low_confidence_rate` nearly didn't work, and the fix is worth carrying forward.** The natural
  implementation makes the fuzzy match's confidence *be* its Jaro-Winkler score — but the rung only
  accepts scores ≥ 0.95, so every fuzzy confidence would land **above** the 0.89 low-confidence bar
  and the monitor would report `0.0000` forever while looking perfectly healthy: a monitor that
  cannot fire, dressed as a clean number (the NF1.7 (a) shape, reached through the metric's
  *definition* rather than its population). **Confidence is a property of the RUNG, not of the
  string similarity** — an inexact match is the least trustworthy rung however close the strings
  were — so a fuzzy match maps into [0.60, 0.89] and the raw similarity stays on `match_score`. It
  now reports real numbers (2022 0.000499 → 2025 0.0, the last because 2025 genuinely has zero
  fuzzy matches, not because the monitor is blind).
- **The cross-era depth-chart comparability check remains SPUN OFF** (RB ranks run 1–3 in 2024 vs
  1–6+ in 2025), as the story directs. Untouched here.

## 8. Guard discipline

All 47 Python guards were **RED-proven** against deliberately-broken source (15 breaks: restore the
coalesce, drop the tier label, drop the bridge's ambiguity `having`, re-derive the satellite bridge,
bypass the resolver in the audit, narrow the ambiguity scope, accept a partial block, allow name
tiers with no block, make `silent_drop` threshold-governed, score an empty run 0.0, let a degraded
row keep its value, zero-fill the unknown, treat `'0'`/`'nan'` as a real vendor id, …). Two findings
from that pass, both fixed:

1. **A guard asserting `"resolve_snap_counts" in src` was satisfied by the IMPORT line** — it stayed
   green with the call swapped out. Now it matches an actual call site. Same vacuity class as a name
   matched inside a comment (which is why the SQL/Python guards strip comments first).
2. **`qa_records` sorted the review queue alphabetically**, putting `low_confidence` above
   `unmatched` — burying the rows with no answer under the rows with a weak one. Now sorted by
   severity.

`test_a_clean_resolution_does_not_fail_closed` is the two-sided control: without it, every
fail-closed test could pass because the gate rejects everything. Each fail-closed test satisfies
every *other* clause and violates exactly one, so removing that clause is the only way to make it
pass (the NF-D17 and-composed-guard rule).

## 9. dbt build verification (run on the branch, 2026-08-06)

`dbt build --select +fct_player_week +sat_snap_counts_weekly` → **40/40 PASS in 22s**, incl.
`assert_nfl_snap_bridge_has_no_silent_zero`. Then the three downstream marts
(`+mart_player_season +mart_opportunity_player_week +mart_efficiency_player_week`) → **60/60 PASS**.

⚠️ **A green test is not evidence until the data is checked** — the biconditional could pass
vacuously on a table where every row sits in one tier. It does not:

| check | result |
|---|---|
| tier distribution (all three present) | `observed` 81,542 · `no_snap_row` 830,078 · `bye` 197,617 |
| ⭐ **Michael Woods II, CLE 2024 wk 13–17** | **0.77 / 0.88 / 1.00 / 0.68 / 0.86** — was 0.00 |
| genuine observed zeros retained | **8,725** (a real 0.0 survives) |
| biconditional, both directions, 1.1M rows | `value_on_non_observed` 0 · `null_on_observed` 0 |

**The semantic change is concentrated where snap data never existed.** 830k rows move from a
fabricated `0.0` to NULL, but `snap_counts` only starts in 2012, so the bulk is pre-2012
player-weeks where NULL is unambiguously the truthful value. The modern skill-position population
affected is tiny — **2025: 14 rows, 2024: 26, 2023: 64** — and `mart_player_season`'s snap averages
now correctly exclude those unknowns instead of averaging a fake zero in.

⚠️ **Correction to the original handoff:** the command shipped in the PR selected only the two
changed models, which fails on a fresh DuckDB (`Catalog Error: team_week_calendar does not exist`)
because the upstream chain is not built. The correct selector is `+fct_player_week
+sat_snap_counts_weekly` (10 models).
