# E8.7 — pre-registration: does a COMPLEX-level (DSL / CPX) line carry translatable signal?

**Written 2026-08-03, BEFORE any translation statistic was computed.** The ingest spec below was
probed live first (that is a factual API question, not a result); every *inferential* number in
this document is unmeasured at the time of writing.

`best_alpha = 0` — nothing here rides a bet. The consumer is the E8.0 prospect board.

---

## 0. The premise correction that scopes this story

E8.3 flagged 156 board prospects (10.8% of the board) with no MLE line. That was **not** an
identity/xref failure — `mlbam_id` is 100% resolved for all 156 (DSL 62/62, CPX 94/94). The gap is
that `scripts/ingest_milb_to_s3.py` pulls sportIds **11–14 only**, so complex-level games were
absent *by construction* and those players have no game logs of any kind.

So: E8.7 is an **ingest** story with a **model-feasibility gate** bolted on. The ingest is the easy
half and is unconditionally worth doing (the logs are useful whatever the gate says). The MLE
extension is the half that can legitimately come back NULL.

## 1. Ingest spec — VERIFIED LIVE 2026-08-03 (probe, not documentation)

| Fact | Measured value |
|---|---|
| sportId 16 name | `Rookie` |
| Live leagues | Dominican Summer **130**, Florida Complex **124**, Arizona Complex **121** |
| Historical leagues | Venezuelan Summer **134** (≤~2015), Appalachian **120**, Pioneer **128** (affiliated ≤2020) |
| Volume | ~430–440 games / 2 weeks in season; 870 schedule rows for 2025-07 alone |
| Field parity | boxscores carry identical `plateAppearances` / `stolenBases` / `caughtStealing` / `hits` / `doubles` → `BATTING_FIELDS` unchanged |
| sportId 17 | Winter Leagues — **NOT** the DSL. Deliberately not ingested. |

### Three ways the level mapping can silently go wrong (all guarded)

1. **Rung collapse.** `SPORT_LEVELS` is one-sportId-one-rung, but sportId 16 spans three rungs and
   `BOARD_LEVEL_RANK` ranks DSL=1 and CPX=2 *differently*. A flat `16: "Rookie"` corrupts the ladder.
2. ⭐ **The league NAME is not a durable key** — a refinement of the story spec, found by probing
   history. Both CPX leagues were **renamed in 2021**: 121 `Arizona League`→`Arizona Complex
   League`, 124 `Gulf Coast League`→`Florida Complex League`. A name-keyed map silently drops
   *every pre-2021 CPX row*, which is most of the history a ladder fit would need. **The level is
   therefore derived from the league ID**, name only as a fallback.
3. ⭐ **The rung is per-TEAM, not per-GAME.** 2 of 10,364 probed sportId-16 games are cross-league,
   and the stray opponents include league 107 `College Baseball` and league 126 `Northwest League`.
   Each side carries its own `home_level_name`/`away_level_name`; a player row inherits **its own
   side's**. An unrecognised league yields `None`, never a guess.

Rung assignment: `130,134 → DSL` · `121,124 → CPX` · `120,128 → Rookie-Adv` (history-only; a rung
*above* complex, kept distinct in the lakehouse rather than folded into CPX).

## 2. The gate — what would make a complex line usable

> **The question.** Does a DSL or CPX line carry measurable, *translatable* signal about how the
> same player performs at the next rung up — enough to justify putting a number on the board?

E7.15-H1 established the mechanism: a rung is estimated from **within-player minor→minor
transitions**, not from graduates-only labels. So the primitive statistic is the **within-player
translation correlation** between a player's rate at a source rung in season *t* and the same rate
at the destination rung in a later season.

Transitions tested: `DSL → CPX`, `DSL → A`, `CPX → A`, `CPX → A+`.
Metrics: `k_pct`, `bb_pct`, `iso`, `woba` (the board's line).

### 2.1 Two-sided anchors — registered in advance, both must behave

Per §0.5 / NF1.7(a)-(d): an anchor that fails to compute is **not** a pass, and a one-sided anchor
set is gameable. Both of these are computed every run and reported whatever they say.

- **CEILING — same-rung split-half reliability.** A player's odd-game vs even-game line *at the same
  rung, same season*. No cross-rung translation can exceed the source line's own measurement
  reliability. ⭐ If DSL reliability is itself ~0 at complex-league sample sizes, the mechanism
  **cannot act** — that is an `INACTIVE`/reliability finding (NF1.9), a scope result, not a power
  one, and no number of seasons fixes it.
- **FLOOR — permutation null.** Destination lines shuffled within (rung, season). Must return
  |r| < 0.05. Proves the pairing machinery is not manufacturing correlation. A non-zero floor
  invalidates the whole read.

### 2.2 Incumbent benchmark

The same statistic on rungs the MLE **already** trusts (`A → A+`, `A+ → AA`), computed by the
identical code path on the identical instrument. This is the matched comparison that turns a bare
correlation into an interpretable one (NF-D10: read the *paired* quantity, not a rank).

### 2.3 PASS criterion — fixed now

A metric's complex rung **PASSES** iff **all** of:

1. the permutation floor returns |r| < 0.05 (instrument is honest); **and**
2. the split-half reliability ceiling is computable and > 0 (mechanism can act); **and**
3. the translation correlation is **positive** with a **player-clustered bootstrap 95% CI excluding
   zero**; **and**
4. it is **≥ 0.50 ×** the incumbent adjacent-rung (`A → A+`) correlation for the *same metric* on
   the *same instrument*.

Clause 4 is the pre-registered practically-meaningful effect: a rung that carries less than half the
translation of the rung directly above it does not deserve a board number, however statistically
detectable it is. Stating it now is what makes a miss a *trustworthy* null rather than a shrug.

**FAIL ⇒ the board keeps the FV-only fallback + `speed_flag` for those players, unchanged.** A
recorded null with the mechanism named is the deliverable in that branch. It is a real possible
outcome and is not a failed story.

### 2.4 How a miss will be classified

Via `betting_ml/utils/cv_power.classify_null` and the MH2 seven-state taxonomy, plus NF-D18's
eighth state. The states this story can plausibly land in, and what each implies:

| State | Meaning here | Remedy |
|---|---|---|
| `INACTIVE` | reliability ceiling ≈ 0 — a ~200-PA complex line is not a measurement of anything stable | different population/metric; **more seasons do nothing** |
| `GENUINE_ABSENCE` | translation correlation ≤ 0 on average | **no** re-test trigger |
| `POWER_LIMITED` | positive but CI includes 0 | state the shortfall **in players/seasons**, and say whether it is reachable now |
| `TRUSTWORTHY_DEAD` | MDE ≤ the 0.50× bar and nothing showed | closed |

⚠️ Per MH2 (g″)/NF-D18: a shortfall gets a re-test trigger **only** if more data can actually change
it. A reliability-ceiling failure must **not** be published as "needs N more seasons."

## 3. Cost discipline — why the gate is measured before the backfill

A full sportId-16 backfill (2005–2026) is ~3,000 games/season × 22 seasons at the polite fetch delay
≈ **several hours** — an operator run, and one worth paying for only if the answer can be yes.

The gate above is therefore first measured on the Stats API's **season-aggregate** endpoint
(`/stats?stats=season&group=hitting&sportId=…`) — one call per (season, group, level) instead of one
per game. This is a **screen, not a substitute**: it returns the same counting stats aggregated to
the season-level line the translation statistic actually consumes, so it answers the feasibility
question directly, but it carries no park/opponent/age context and cannot itself fit the MLE.

**Pre-committed decision rule:**
- Screen **PASSES** on ≥1 metric → the full game-log backfill is justified → refit the ladder with
  the new rungs, re-run the SB bake-off, rebuild the board.
- Screen **FAILS on every metric** → record the null; ingest still ships (the logs have standalone
  value and the daily incremental now covers complex ball); **no** board change; FV-only fallback
  stands.

⚠️ The screen may **only** move the decision in the direction of *more* work or *no* work. It may
not be used to select a metric after the fact and then report that metric's number as the headline
(that is the E2.1-r inversion). Every metric's screen result is reported.

## 4. Scope explicitly OUT

- No `--publish` of any board from this branch (8/3 draft-day coordination — the live board is
  tonight's draft board; any E8.7 re-export is a POST-draft, post-merge operator step).
- No change to `BOARD_LEVEL_RANK`'s existing spacing.
- sportId 17 (Winter Leagues) is not ingested.
