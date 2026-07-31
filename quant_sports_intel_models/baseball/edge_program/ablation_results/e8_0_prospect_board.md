# MLB Edge-E8.0(+E8.0b) — the LEAN prospect draft board (8/3 dynasty draft)

**Built:** 2026-07-29 · **E8.0b consensus fold:** 2026-07-31 · **board snapshot:** FanGraphs THE
BOARD season 2026 as-of **2026-07-27**, MLB Pipeline as-of **2026-07-29** · **code:**
`betting_ml/scripts/prospect_board/` · **exports:** `ablation_results/e8_0_artifacts/`
(gitignored — regenerate in ~10s, see below)

> 🔒 **`best_alpha = 0`.** This is *"FanGraphs consensus + our independent MLE-translated line +
> where they disagree"*. It is **not** a ranking that claims to beat FanGraphs, and no edge or
> win-rate claim is made or implied. The ordering heuristic and every weight in it are display
> devices traceable to a measured E7.x number; nothing here has been validated as a ranking.

---

## 0. What shipped

One row per current-board prospect, carrying **three independent reads** of the same player and the
places they disagree:

| view | source | what it contributes |
|---|---|---|
| **The scouts** | E7.7 `baseball/milb/the_board` | FV · overall/org rank · ETA · risk · future tool grades · TLDR |
| **Us** | E7.3 `mle_projections` + E7.3p `mle_projections_pitchers` | MLB-equivalent K% / BB% / ISO (bats), K% / BB% / GB% (arms), each with its parameter sd |
| **Prospect Savant** *(optional)* | `oriolebird.pythonanywhere.com` | THEIR MiLB-Statcast expected stats — xwOBA, EV, whiff/chase, xFIP, velo |

joined through **E7.4 `dim_player_xref`** (`fg_minor_id` → MLBAM), plus `mlb_league` (AL/NL) from a
static 30-team org map — the filter a single-league dynasty draft actually runs on.

**Deliverables:** `e8_0_prospect_board.csv` (the 8/3 minimum), `_AL.csv` / `_NL.csv`, and a 10-tab
`.xlsx` — *How to read this · All · AL · NL · Hitters · Pitchers · Minors only · By blend ·
Disagreements · Pipeline-only* (E8.0b). The **stretch in-app page was deliberately not built** — it
is E8.1, and the story scopes E8.0 export-first so the draft cannot be gated on a serving surface.

## 0b. E8.0b (2026-07-31) — MLB Pipeline folded in as a second source + a consensus

E8.0 shipped FanGraphs-only. **MLB Pipeline (E7.11) ranks 165 players FanGraphs' board omits
entirely** — those were draft-relevant blanks in the 8/3 export. `build_prospect_board.py` now folds
MLB Pipeline in by default (`fold_pipeline_into_e8_0_board`, `betting_ml/scripts/prospect_board/
build_consensus_assembly.py`), reusing E7.11's `merge_pipeline_ranks` + `consensus.attach_consensus`
— **not** a hand-rolled join, not a second rebuild of E7.11's math.

**Measured on the real lake (2026-07-31, board season 2026 / Pipeline as-of 2026-07-29):**

```
FanGraphs board                    : 1,286 prospects
+ MLB-Pipeline-only players added  :   165   ("Pipeline-only" tab)
= combined universe                : 1,451
overall consensus (≥2 sources)     :    62   (FanGraphs Top-100-ish ∩ Pipeline Top 100)
org consensus (≥2 sources)         :   735   (FanGraphs org rank ∩ Pipeline org Top 30)
```

**What changed on the export:**

* Per-source ranks side by side: `overall_rank`/`org_rank` (FanGraphs, unchanged) +
  `pipeline_overall_rank`/`pipeline_org_rank` (new).
* `consensus_rank` / `consensus_rank_mean` / `consensus_tier` / `consensus_n_sources` /
  `consensus_confidence` / `consensus_rank_spread` (overall scope) and the `org_consensus_*` siblings
  (org scope, ~10× the coverage). **Equal weight** — `consensus_rank_mean` is the plain mean of the
  ranks that exist for a player. E7.14 (the accuracy study that could justify a different weight) had
  not landed at build time; ship equal-weight and let a future session apply E7.14's verdict here if
  it clears the deflated gates.
* `vs_consensus_<source>` (+`_label`): each source's RESIDUAL disagreement vs the consensus — never
  the raw gap (E8.0's own regression-to-the-mean defect, §3a below) — computed **only** where
  `consensus_n_sources ≥ 2` (a source cannot disagree with a consensus it alone constitutes; E7.11's
  own first-run defect, restated in `sport_data_platform.md`).
* `mle_vs_consensus` (+`_label`): the differentiated view, extended — how much higher OUR line scores
  a player than is usual for a player the (FanGraphs + Pipeline) consensus places there, fitted within
  player type via the shared `board_assembly.residual_vs_fit`.
* `on_fangraphs_board`: `False` for the 165 unioned-in rows. Their `fv`, `model_score`, `mle_score`,
  `blend_score`, `disagreement` all stay **blank — never a fabricated MLE or a fabricated FV pctile**;
  they were never scored by the E8.0 pass (no FanGraphs row to score against, and `merge_pipeline_ranks`
  does not join an MLE line for them). `in_majors` / `speed_flag` / `disagreement_label` are filled
  to the same sentinel the FanGraphs-board rows use (`""` / `""` / `"n/a (no MLE line)"`) rather than
  a bare NaN, so the export doesn't mix conventions depending on which source a row came from.
* **`board_rank` / default sort is UNCHANGED for every original FanGraphs-board row** — the re-sort
  keeps `fv` → `model_score` → `blend_score` first, and all three are NaN for a Pipeline-only row, so
  none of the 165 new rows can outrank an existing one (`na_position='last'` sinks them regardless of
  direction). They break ties among themselves on `pipeline_overall_rank` and are separately visible
  (and Pipeline-rank-sorted) on the **Pipeline-only** tab.
* **AL/NL hard-error preserved** for the new rows too — an MLB-Pipeline-only player from an org with
  no AL/NL mapping raises `ProspectBoardError`, same as the pre-existing FanGraphs-side rule.

Reused, not rebuilt: `board_assembly.split_sheets` gained the `Pipeline-only` tab conditionally (only
when `on_fangraphs_board` is present — a plain FanGraphs-only board is byte-for-byte unaffected), and
`e8_0_column_order_with_consensus` relocates the new columns out of the auto-appended tail into a
readable block beside the FanGraphs "scouts" columns without ever dropping one.

## 1. Join match rates (measured, on the real lake)

```
current board snapshot     : 1,286 prospects
→ resolved to an MLBAM id  : 1,277 (99.3%)   [E7.4 dim_player_xref; NO fuzzy leg]
→ with OUR MLE line        : 1,023 (79.5%)   [bats 467 / arms 556]
→ with Prospect Savant     : 1,006          [their expected stats, ps_* columns]
unmapped orgs              : none (all 30 mapped to AL/NL)
```

> ⚠️ **E7.4's headline "4,263/4,279 current board prospects, 1,812 with an MLE" is an ALL-SEASONS
> count**, not the current snapshot — `dim_player_xref`'s nine board seasons sum to exactly 4,279.
> The current 2026 board is **1,286** players. Both numbers are right; they count different things.

The 99.3% reproduces E7.4's measured chain rate exactly — the expected result when the board is
read through the sanctioned reader, and the tell that it was not read through a tombstoning glob.

**The 20.5% without an MLE line is EXPECTED, not a defect.** Complex-league (CPX), DSL and
just-drafted prospects have an identity but no MiLB-PA projection: E7.1 ingests sportIds 11–14
(AAA/AA/A+/A) only. Coverage by level, from the built board:

| level | bats w/ MLE | arms w/ MLE |
|---|---|---|
| AAA / AA / A+ | 79/80 · 118/119 · 104/105 | 120/123 · 134/139 · 114/130 |
| A | 76/103 | 53/88 |
| **CPX / DSL** | **0/56 · 0/59** | **0/37 · 0/3** |

Those rows stay on the board **FV-only** rather than being dropped, and no fuzzy name leg was added
(E7.4 found name equality produces false positives — a DET prospect matching a KC 2B).

### ⭐ A free third-party audit of the E7.4 bridge

Prospect Savant publishes **both** `MinorMasterId` (= our `fg_minor_id`) and `MLBAMId`. We join on
`fg_minor_id` **alone**, so their MLBAM id is an independently-sourced second answer to "who is
this?":

> **1,006 / 1,006 = 100.00% agreement** with the MLBAM id E7.4 derived through the FanGraphs
> leaderboards.

That is not a restatement of the bridge — it is a different vendor's crosswalk agreeing with ours on
every comparable player. It is now computed on every run and printed in the join report.

## 2. How the board is ordered — and why it is ordered that way

### The position asymmetry (E7.8) is the product

E7.8 asked whether FV adds projection lift on realized dynasty-fantasy value over an
age-relative-to-level + level + pedigree null. The answer split by position, so the board does too:

* **Pitchers — FV COMPLEMENTS us** (our read +0.014, FV a further +0.031 on top; `pitcher/debut`
  and `pitcher/unconditional` both clear PBO<0.2 + DSR≥0.95) ⇒ **FV leads** (`blend_score` = 70% FV).
* **Hitters — FV SUBSTITUTES for us** (our read +0.047, FV only +0.015 more; no batter stage cleared
  the deflated gates) ⇒ **our MLE + age-rel-to-level leads, FV confirms** (35% FV).

Corroborated independently by E7.3 vs E7.3p: batter K% translates at OOS corr **0.637** vs pitcher
K% **0.366** on the same harness — the statistical record leaves more unexplained on the mound,
which is exactly the room a scouting grade fills. **The honest claim is "we know WHEN to trust the
scouts," not "we use FV" and not "we ignore it."**

### Metric weights are measured, not chosen

`mle_score` weights each metric **proportionally to its own measured out-of-sample translation
correlation**, and metrics that came back no-signal are absent entirely rather than carried at a
small weight:

| side | in the score (weight = OOS corr) | excluded, and why |
|---|---|---|
| batters | k_pct **0.637** ✅ · bb_pct **0.491** ✅ · iso **0.429** 🟡 | **wOBA 0.220 ❌ no-signal** — never resurrected |
| pitchers | gb_pct **0.551** ✅ · bb_pct **0.367** 🟡 · k_pct **0.366** 🟡 | hr_rate (0.094, DSR 0.130) · xwoba_against (0.147 ❌) |

K%'s direction **inverts** between the two sides (a bat wants it low, an arm wants it high) — pinned
by a test, because getting it backwards would invert half the board and still look plausible.

## 3. Two things the first real run got wrong (both fixed, both now guarded)

**(a) `disagreement` as a raw gap was a broken metric.** `model_score − fv_pctile` labelled **10 of
the top 12** players "SCOUTS HIGHER" — including one our own line scored in the 95th percentile.
That is not disagreement, it is *regression to the mean*: two rankings correlated below 1.0 pull
toward each other at the extremes, so the raw gap is a re-encoding of FV rank. It now reports the
**residual** after removing the fitted FV↔our-score relationship (fit within player type), so a flag
means "unusual for a player with this grade". Post-fix the column is centred (mean 0.02, sd 13.3)
and the labels are symmetric (139 scouts-higher / 129 we're-higher / 755 agree). Same class as the
repo's selection-metric-hygiene rule: check what the metric must *mechanically* produce before
trusting what it says.

**(b) Prospect Savant encodes "not tracked at this level" as the number `0`.** Batted-ball and
velocity tracking is **Triple-A only** (the coverage wall E7.2 hit), and below it the payload writes
`xwoba = 0.0`, `ev = 0.0`, `velo = 0.0` rather than omitting them. Shipped verbatim, a 0.000
expected-wOBA-against renders on a draft board as a *perfect* pitcher. The tracking-gated group is
now nulled together, keyed on `ev`. The plate-discipline rates (whiff / chase / K / BB / GB) and
xFIP **are** real at every level and are kept — that is why 1,006 players have `ps_whiff_pct` while
only 404 have `ps_xwoba`. `bat_speed` is not mapped at all: it is 0.0 for every player at every
level, AAA included.

## 4. Stated limitations

* **SB is invisible to us.** Every E7.3/E7.3p target is a per-PA/per-TBF rate; stolen bases are not
  in the substrate (the same gap E7.8 states for its fantasy target). Speed-first prospects are
  systematically under-served by `mle_score`, so the board flags them from the scouts' own
  future-speed grade (`speed_flag`, 60+). If the league scores SB, say so out loud at the table.
* **The MLE line is a career-at-level aggregate**, not a 2026-only line — for un-graduated prospects
  E7.3 aggregates all games at a level. `mle_level` + `mle_pa` ship beside every projection so the
  sample is always visible; the board prefers the highest level with ≥100 PA and falls back to the
  largest sample rather than projecting a player off a 25-PA promotion line.
* **Uncertainty is PARAMETER uncertainty**, and E7.3 states it is too tight to read as a calibrated
  interval. It ranks confidence correctly; it does not price it.
* **Scores are within player type.** A hitter's 90 and a pitcher's 90 each mean "elite among his own
  kind", not "equally valuable" — cross-type ordering carries no positional-value claim.
* **231 of the 1,286 board players are listed at MLB.** Flagged `in_majors`, with a *Minors only*
  tab (1,055 players), since most minor-league dynasty drafts do not make them draftable.
* **Prospect Savant is an unofficial hobbyist endpoint**, opt-in, cached, display-only. It has no
  as-of history, so it can never be an E7.8 backtest feature.

## 5. Reproduce

```bash
# LAPTOP — the full board: FanGraphs + MLB Pipeline consensus + our MLE + Prospect Savant (~10s)
AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
    betting_ml.scripts.prospect_board.build_prospect_board --prospect-savant

# CSV only, no optional dependency
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    betting_ml.scripts.prospect_board.build_prospect_board
```

`--ps-probe` re-probes the Prospect Savant route shape; `--min-mle-pa` moves the sample floor;
`--allow-unmapped-orgs` downgrades the unmapped-org HALT to a warning (not advised — a NULL
`mlb_league` silently removes players from the only sheet the operator drafts off);
`--skip-pipeline-consensus` is an **E8.0b emergency escape hatch** back to the plain FanGraphs-only
board (not advised — the whole point of this story is that it stays off for 8/3);
`--pipeline-season` / `--pipeline-from-dir` mirror E7.11's own flags for the MLB Pipeline snapshot.

## 6. Follow-ons (out of scope here, on purpose)

* **E8.1** — productize this board into an in-app Fantasy Baseball section.
* **E8.2** — import a CBS Sports Fantasy Baseball league's rosters → an "available in the
  minor-league draft" filter.

Both carry serving-path and external-auth unknowns that must not gate the 8/3 draft.
