# E8.7 — DSL / CPX ingest + the complex-level translation screen

**2026-08-03.** `best_alpha = 0` — nothing here rides a bet.
Pre-registration: [`e8_7_preregistration.md`](e8_7_preregistration.md), committed (89018b3) **before**
any statistic below was computed.

## Verdict in one line

**The complex rungs translate, and the screen PASSES the pre-registered bar.** DSL and CPX season
lines carry K% / BB% / ISO signal at **0.55–0.98× the incumbent rung's**, whether measured
rung-to-rung or **directly to MLB**. The pre-committed decision rule therefore fires: the sportId-16
game-log backfill is justified, and the MLE refit → SB bake-off → board rebuild should proceed.

⛔ **Nothing is on the board yet.** The refit needs game-log-grain data that does not exist until the
backfill runs (a ~3.2 h operator job). Until then the 156 prospects keep the FV-only fallback,
unchanged. **This is the honest state: the gate is answered, the model change is not yet made.**

## What shipped in this PR

1. **`scripts/ingest_milb_to_s3.py` ingests sportId 16** (DSL + ACL/FCL), with the rung derived
   **per team from the league ID**. Guarded, red-proven, live-smoked.
2. **`run_e8_7_complex_screen.py`** — the pre-registered gate, reproducible from the Stats API.
3. This write-up + the screen result JSON.

Not shipped: the MLE refit, the SB bake-off, the board rebuild — all blocked on the backfill.

## 1. Ingest — three ways the level mapping silently goes wrong

sportId 16 (`Rookie`) is one sportId spanning several rungs. Probed live 2026-08-03:

| league_id | name (2021+) | name (≤2020) | rung |
|---|---|---|---|
| 130 | Dominican Summer League | *same* | `DSL` |
| 134 | Venezuelan Summer League | *same* | `DSL` |
| 121 | Arizona **Complex** League | Arizona League | `CPX` |
| 124 | **Florida** Complex League | **Gulf Coast** League | `CPX` |
| 120 | *(collegiate summer since 2021)* | Appalachian League | `Rookie-Adv` |
| 128 | *(independent since 2021)* | Pioneer League | `Rookie-Adv` |

1. **Rung collapse** — the trap the story named. `BOARD_LEVEL_RANK` ranks DSL=1 and CPX=2
   *differently*; a flat `16: "Rookie"` merges them and corrupts the ladder.
2. ⭐ **The league NAME is not a durable key** — a refinement of the story spec, found by probing
   history rather than the current season. Both CPX leagues were **renamed in 2021**, so a
   name-keyed map silently drops *every pre-2021 CPX row* — i.e. most of the history a ladder fit
   needs. **Keyed on the league ID**, name only as a fallback.
3. ⭐ **The rung is per-TEAM, not per-GAME.** 2 of 10,364 probed sportId-16 games are cross-league,
   and the real strays include league 107 `College Baseball` and 126 `Northwest League`. Each side
   carries its own `home_level_name`/`away_level_name`; a player row inherits **its own side's**.
   An unrecognised league yields `None` — a NULL rung is skipped downstream, a *guessed* one
   silently corrupts a cell.

**Guards** (`test_ingest_milb.py`, +11 tests): each of the three failure modes was reproduced in
source and verified to go RED. Breaks 2 and 3 each fail **exactly one** test — the fixtures isolate
their own clause rather than tripping a shared condition (NF-D17).

Live smoke (no writes): 870 schedule rows for 2025-07 → `DSL 571 / CPX 299`; two real boxscores
flattened with distinct rungs, `SB`/`CS`/`PA` present, point-in-time ages 16.9–19.4 (DSL).

## 2. The screen — and three anchor defects it caught in its own instrument

The primitive is E7.15-H1's: the **within-player translation correlation** from a source-rung season
line to the same player's later destination-rung line. Population 2006–2025 (2020 absent — no MiLB
season), `MIN_TRANSITION_PA = 150` inherited from `level_ladder`, rates from the MLE's own
`compute_rate_metrics_from_counts`.

⭐ **Every one of the three fixes below was forced by a pre-registered anchor, not noticed by eye.**
This is the anchors doing exactly the job §0.5 gives them, and all three are the *same* class of
error — an invented constant standing in for a measured null.

**(a) The reliability ceiling was uninformative.** A crude delta-method noise bound
(`p·(w_max − p)/n`) over-stated the noise so badly that wOBA reliability came out **negative at
every rung, including rungs the MLE already trusts** — not a finding, a broken estimator. Replaced
with the **exact multinomial variance**, which the season line's own counts fully determine. The
repaired ceilings are sensible and monotone in sample thickness:

| rung | mean PA | k_pct | bb_pct | iso | woba |
|---|---|---|---|---|---|
| DSL | 209 | 0.851 | 0.734 | 0.608 | 0.512 |
| CPX | 187 | 0.832 | 0.712 | 0.586 | 0.442 |
| Single-A | 330 | 0.871 | 0.782 | 0.671 | 0.554 |
| Triple-A | 332 | 0.876 | 0.766 | 0.714 | 0.582 |
| MLB | 414 | 0.884 | 0.772 | 0.693 | 0.546 |

⇒ a ~200-PA complex line is a **genuinely informative measurement** (K% reliability 0.83–0.85, only
~0.02 below a full-season A-ball line). The mechanism **can act** — this is not an `INACTIVE` story.

**(b) The permutation floor failed — twice, in opposite directions.** Scoring **one** permutation
draw against a fixed `|r| < 0.05` returned up to +0.183 and "failed". But a single draw's sd is
`~1/√n`, so that constant is ~1.7σ at n=3,509 and only ~0.57σ at n=130: **the gate's stringency was
a side-effect of n** — the MH2-H8 defect in a new costume — and it duly "failed" only at the small
`→MLB` rows while every large rung sat inside ±0.065. Replacing it with "the null mean must be
statistically zero (200 draws, ≤3 SE)" then failed **26 of 40 cells including the incumbent rungs**,
because at 200 draws SE ≈ 0.0013 and a null mean of +0.0116 is "significant" while sitting 24.5
null-sd below the observed 0.658. **A floor a known-good rung cannot pass is measuring the wrong
thing.**

⇒ **CURE: use the null for what it provides — a LOCATION and a SCALE.** Subtract the location
(`r_adj = r − perm_mean`), applied **identically to the incumbent benchmark** so the ratio stays a
matched comparison, and judge significance against the scale (`z`). The residual location is real
and explicable: shuffling within destination season cannot break the pairing inside a *singleton*
season group, and the `→MLB` transitions spread 130–193 players across 20 seasons.

⭐ **This correction was not cosmetic and it cuts against the headline.** `DSL→MLB` K% carries a
null location of **+0.144**; correcting it drops the ratio-to-incumbent from a flattering **0.96 to
0.58**. An uncorrected reading would have overstated the strongest claim in this document.

**(c) An era confound, found by the same floor.** Minor-league K% trends league-wide across
2006–2025, and shuffling within destination season preserves that season's mean. Rates are therefore
**centred on their own (rung, season) mean** — which is also exactly what the MLE's level factor
does. The raw uncentred statistic is computed and reported beside it (`metrics_raw_uncentred`);
**the conclusion is unchanged under either convention**, which is the point of reporting both
(NF1.8).

## 3. Results

Bias-corrected `r_adj`, player-clustered bootstrap CI, vs the matched incumbent. **PASS** = CI
excludes 0 **and** `r_adj ≥ 0.50 ×` the incumbent's `r_adj` **and** the null is characterised with
`z > 2`.

### Rung-to-rung (bar = 0.50 × `Single-A→High-A`)

| transition | n | k_pct | bb_pct | iso | woba |
|---|---|---|---|---|---|
| **DSL→CPX** | 1,151 | **0.647** (0.90×) | **0.416** (0.70×) | **0.423** (0.83×) | **0.239** (0.69×) |
| **DSL→Single-A** | 1,122 | **0.599** (0.83×) | **0.443** (0.74×) | **0.353** (0.69×) | 0.152 (0.43×) ❌ |
| **CPX→Single-A** | 1,376 | **0.671** (0.93×) | **0.504** (0.84×) | **0.426** (0.84×) | **0.237** (0.68×) |
| **CPX→High-A** | 929 | **0.591** (0.82×) | **0.467** (0.78×) | **0.429** (0.84×) | **0.261** (0.75×) |
| *A→A+ (incumbent)* | 3,509 | *0.719* | *0.599* | *0.509* | *0.349* |
| *A+→AA (incumbent)* | 3,369 | *0.651* (0.91×) | *0.578* (0.97×) | *0.493* (0.97×) | *0.278* (0.80×) |

### Direct to MLB — the estimand itself (bar = 0.50 × `Single-A→MLB`)

An `mle_<metric>` board number *is* a projected MLB rate, so this is the quantity, not a proxy.

| transition | n | k_pct | bb_pct | iso | woba |
|---|---|---|---|---|---|
| **DSL→MLB** | 130 | **0.289** (0.58×) | **0.234** (0.55×) | **0.336** (0.88×) | 0.046 (0.25×) ❌ |
| **CPX→MLB** | 193 | **0.475** (0.96×) | **0.327** (0.76×) | **0.374** (0.98×) | 0.087 (0.47×) ❌ |
| *A→MLB (incumbent)* | 749 | *0.495* | *0.429* | *0.384* | *0.184* |
| *AAA→MLB (incumbent)* | 1,102 | *0.555* (1.12×) | *0.527* (1.23×) | *0.440* (1.15×) | *0.186* (1.01×) |

**Screen verdict:** DSL→CPX, CPX→A, CPX→A+ pass **4/4**; DSL→A, DSL→MLB, CPX→MLB pass **3/4**.
Every complex rung clears on **K%, BB% and ISO**.

**wOBA is the consistent exception** and should be read as a real limit, not noise: it fails outright
at DSL→A (0.43×), DSL→MLB (0.25×) and CPX→MLB (0.47×), and is the weakest metric even where it
passes. wOBA is a composite dominated by power and BABIP — the least stable components of a teenage
complex-league line (its reliability at CPX is 0.442, the lowest cell in the table). ⇒ **the refit
should carry K% / BB% / ISO for complex-level players and withhold wOBA**, rather than shipping all
four because three passed.

### What the screen does NOT establish

- It is **season-aggregate**, so it carries no park / opponent / age context and **cannot replace the
  E7.3 fit**. Per the pre-registration it may only move the decision toward more work or none.
- The `→MLB` pairs are **graduates only** (E7.12-S2 survivorship). That is the *same* selection the
  incumbent `A→MLB` row carries, so the comparison is matched — but neither number is a population
  estimate for un-promoted players.
- `n = 130 / 193` on the `→MLB` rows is thin; those CIs are wide and the wOBA cells there are
  underpowered as well as small.

## 4. Deviations from the pre-registration (disclosed, not retro-fitted)

The pre-registration is left **as written**; these are the deviations forced by the anchors:

1. The floor criterion changed from `|r_perm| < 0.05` (one draw) to the location/scale reading in
   §2(b). **Reason: the registered constant was itself defective** — it could not be passed by the
   incumbent rungs under either the original or the first repaired form.
2. The reliability estimator changed from a delta-method bound to the exact multinomial variance
   (§2(a)), because the registered one returned negative reliabilities.
3. Rates are (rung, season)-centred (§2(c)); the uncentred convention is reported alongside and does
   not change the verdict.
4. `DSL→MLB` / `CPX→MLB` / `Triple-A→MLB` were **added** to the registered transition list to
   measure the estimand directly. This is an addition, not a substitution — every registered
   transition is still reported.

None of these changed a FAIL into a PASS on the headline metrics: under the *original* uncorrected
statistic the complex rungs passed even more comfortably (§2(b)) — the corrections made the claim
**smaller**, not larger.

## 5. What happens next (blocked on the backfill)

| step | owner | note |
|---|---|---|
| sportId-16 game-log backfill | **operator, laptop, ~3.2 h** | resumable, idempotent per (season, sport_id, month) |
| MLE ladder refit with DSL/CPX rungs | next session | must be a registered **arm** beside the incumbent, not a replacement — `LEVEL_ORDER` is left untouched by this PR |
| SB bake-off (E8.3) re-run | next session | complex lines carry `SB`/`CS`; verified present in the smoke |
| board rebuild + `--publish` | operator, **post-draft, post-merge** | ⛔ not from this branch |

⚠️ The refit must **not** simply extend `LEVEL_ORDER` in place: that would silently change the
incumbent model for every existing consumer. It is deliberately left unmodified here.
