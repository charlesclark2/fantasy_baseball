# MLB Edge-E7.11 — multi-source prospect-ranking CONSENSUS (beyond FanGraphs)

**Built:** 2026-07-29 · **board:** FanGraphs THE BOARD season 2026 as-of **2026-07-27** ·
**new source:** MLB Pipeline season 2026, fetched **2026-07-29** ·
**code:** `betting_ml/scripts/prospect_board/{mlb_pipeline,consensus,build_consensus,build_consensus_assembly}.py`
+ `scripts/ingest_mlb_pipeline_to_s3.py` · **exports:** `ablation_results/e7_11_artifacts/`
(gitignored — regenerate in ~2 min)

> 🔒 **`best_alpha = 0`.** A consensus is a **DESCRIPTION**, not a claim. Nothing here asserts that
> the consensus beats any single source, that our line beats the consensus, or that a disagreement
> is an edge. No accuracy test against realized outcomes was run and none is implied. What a
> consensus buys is robustness to single-source idiosyncrasy; what a disagreement buys is a
> shortlist worth a second look.

---

## 0. What shipped

| piece | what it is |
|---|---|
| `scripts/ingest_mlb_pipeline_to_s3.py` | MLB Pipeline Top 100 + all 30 org Top 30s → `baseball/milb/mlb_pipeline_rankings` (S3 Delta, partitioned `(season, as_of_date)`) |
| `…/prospect_board/mlb_pipeline.py` | the page parser + the robots gate (pure, fast-gate tested) |
| `…/prospect_board/consensus.py` | rank aggregation, per-source coverage, residual disagreement, manual-source resolution |
| `…/prospect_board/build_consensus_assembly.py` | the board↔Pipeline union + the export shape/legend |
| `…/prospect_board/build_consensus.py` | the runner: lake reads → consensus board → CSV/xlsx/JSON |

**Exports:** `e7_11_consensus_board.csv` (+ `_AL` / `_NL`) and a 9-tab workbook — *How to read this ·
All · AL · NL · Consensus top 100 · Source disagreements · Us vs consensus · Pipeline-only ·
Coverage by source*.

## 1. Access discipline — what was probed, and what was refused

Every host was probed before a single row was read.

| source | verdict | evidence |
|---|---|---|
| **FanGraphs THE BOARD** | ✅ already ingested (E7.7) | — |
| **MLB Pipeline** (`www.mlb.com/prospects/…`) | ✅ **INGESTED** | `robots.txt` disallows `/api/`, `/mlb/`, `/web/`, `/search` — **not** `/prospects/`. Page read of an allowed path. |
| `data-graph.mlb.com/graphql` | ⛔ **NEVER CALLED** | `User-agent: * / Disallow: /`. This is the JSON API the page's own JS calls — and the reason the ingest parses HTML instead. |
| **Baseball America** | ⛔ **BLOCKED → manual** | **Cloudflare managed challenge on `/robots.txt` ITSELF** — an anonymous client cannot read the access policy, let alone the content. See §1a. |
| **Keith Law (The Athletic)** | ⛔ **EXPLICITLY PROHIBITED → manual** | `robots.txt` carries a prose NYT rights reservation banning automated scraping, **text/data mining, and "the development of any software, machine learning, artificial intelligence (AI), and/or large language models"**. See §1a. |
| **Prospects Live** | ⛔ **not ingested → manual** | `robots.txt`: `User-agent: ClaudeBot / Disallow: /`, plus `Content-Signal: ai-train=no, use=reference`. Its ranking routes also 404 anonymously (the lists are Ghost posts, partly Patreon). |
| **ESPN/McDaniel · Baseball Prospectus** | ⛔ paywalled → manual | never scraped; hand-key path only |

### 1a. Why Baseball America and Keith Law specifically cannot be ingested

The operator asked for the verdict on these two by name. They fail for **different** reasons, and
neither is "we didn't try".

**Baseball America — a technical wall we must not climb.** `https://www.baseballamerica.com/robots.txt`
does not return a robots file at all; it returns a **Cloudflare managed-challenge interstitial**
(`cf_chl_opt`, "Enable JavaScript and cookies to continue"). So an anonymous client cannot even
read BA's stated crawl policy. This repo *does* run a challenge solver (Byparr, INC-26) for the
FanGraphs ingest — and that is exactly why the distinction matters: **using it here would be
deliberately defeating an access control in order to take paywalled subscription content.** The
FanGraphs board is free-to-view and CSV-exportable; BA's rankings are the product its subscribers
pay for. Same tool, categorically different act. **Verdict: refuse.** Note the actual research
value at BA is its **~30-park minor-league park factors** (Thread-1 #1), not its rankings — and
those are hand-keyable once a year, or computable ourselves from free game logs.

**Keith Law / The Athletic — an explicit written prohibition.** `theathletic.com/robots.txt` opens
with an NYT rights reservation, in prose, before any directive:

> *"Use of any device, tool, or process designed to data mine or scrape the content using automated
> means is prohibited without prior written permission… Prohibited uses include but are not limited
> to: (1) text and data mining activities under Art. 4 of the EU Directive…; (2) the development of
> any software, machine learning, artificial intelligence (AI), and/or large language models
> (LLMs); (3) creating or providing archived or cached data sets containing our content to others;
> and/or (4) any commercial purposes."*

That covers this use case four separate ways — it is a reservation of rights, not merely a crawl
directive, and it names AI/ML development and commercial use explicitly. **Verdict: refuse.** No
crawl-delay, no partial-quote carve-out, no "just the numbers" reading gets around it.

**What this costs us, honestly:** the overall-scope consensus stays 2 sources deep (62 players with
≥2 ranks). A hand-keyed BA or Law Top 100 would roughly double that and is fully supported —
`--manual baseball_america=…` resolved a 40-row test file at 100% via the deterministic
name+org leg. That is a ~20-minute annual typing job for someone with a subscription, and it is the
only compliant path.

The robots rule is **mechanical, not a comment**: `assert_robots_allows()` re-reads
`https://www.mlb.com/robots.txt` on every run and raises if `/prospects/` ever becomes disallowed,
and `test_mlb_pipeline_ingest.py::test_the_ingest_never_references_the_forbidden_host` inspects the
ingest's source so a future "simplification" into a data-graph request fails CI.

The paywalled/robots-restricted sources enter only through `build_consensus.py --manual
<name>=<file.csv>` — a file a human with legitimate access hand-keyed. `--write-manual-template`
emits the schema plus `manual_source_ACCESS.md` naming each source and why it is manual.

## 2. ⭐ Why MLB Pipeline was cheap to add: it publishes the MLBAM id

Each ranked entry in the page's embedded cache references `Person:<id>`, and that `<id>` **is** the
MLBAM `person.id` — the spine `dim_player_xref` is keyed on. So the second opinion joins to our
board with **zero name matching**, which is exactly the leg E7.4 refused to build (its single
name-equality attempt produced a false positive). Measured on the real pull: **1,000 rows, 900
distinct players, 100.0% carrying an MLBAM id.**

Tool grades came as a bonus: MLB Pipeline's `gradesHitting`/`gradesPitching` fields are NULL on
every row, but the 20-80 grades are published inside the scouting-report prose
(`Scouting grades: Hit: 55 | Power: 60 | …`). Parsed best-effort into `pipeline_grade_*` on
**994/1,000** rows — a second, independent grade set for E7.12's tool-grade→component priors. A
prose parse is a weaker contract than a field, so a miss is a `None`, never a `0`.

## 3. Coverage (measured, on the real lake)

```
universe (FanGraphs board ∪ Pipeline-ranked)  : 1,451 players
  on the FanGraphs board                      : 1,286
  MLB Pipeline players                        :   900  (735 matched to the board = 81.7%)
  ⭐ Pipeline-only (NOT on FanGraphs' board)   :   165

PER-SOURCE COVERAGE
  source                 access    scope    ranked   of universe   depth
  FanGraphs (overall)    ingested  overall     123         8.5%    1–123
  FanGraphs (org)        ingested  org       1,286        88.6%    1–63
  MLB Pipeline (Top 100) ingested  overall     100         6.9%    1–100
  MLB Pipeline (org 30)  ingested  org         900        62.0%    1–30

CONSENSUS DEPTH (players by number of sources ranking them)
  overall scope : {0: 1290, 1: 99, 2: 62}    → 62 players have a genuine 2-source consensus
  org scope     : {1: 716, 2: 735}           → 735 players have a genuine 2-source consensus
```

The **org scope is where the consensus actually has breadth** (735 players vs 62). That is the
scope a 1,451-player dynasty board is drafted from, and it is why both scopes exist.

## 4. ⭐ The finding: two respected sources agree far less than they look like they do

Where **both** sources rank a player:

| scope | n | Spearman ρ (FanGraphs vs MLB Pipeline) | median \|rank difference\| |
|---|---:|---:|---:|
| overall (Top-100-style) | 62 | **0.592** | — |
| within-organization | 735 | **0.655** | **6 places** (of 30) |

Plus **165 players MLB Pipeline ranks that FanGraphs' board does not carry at all** — the loudest
disagreement two sources can produce, and one a naive inner join would have deleted silently.

This is the whole case for the story, stated as a number rather than an intuition: **ρ ≈ 0.6 means
a single-source board inherits a large amount of that source's idiosyncrasy.** It is *not* a claim
that averaging them is more accurate — that was not tested.

The largest 2-source overall disagreements on the 2026 snapshot (illustrative, not a
recommendation):

| player | org | FanGraphs overall | MLB Pipeline Top 100 | spread |
|---|---|---:|---:|---:|
| Ethan Holliday | COL | 120 | 17 | 103 |
| Travis Sykora | WSN | 121 | 32 | 89 |
| Robby Snelling | MIA | 123 | 34 | 89 |
| River Ryan | LAD | 18 | 69 | 51 |

## 5. The four modelling decisions that are load-bearing

**(a) Partial coverage is averaged over, never imputed.** A source that publishes a Top 100 has said
*nothing* about player #340 — it has not ranked him 101st. `consensus_rank_mean` is the mean of the
ranks that exist, and `consensus_n_sources` travels beside it. Imputing "unranked ⇒ list length + 1"
would fabricate an opinion and would systematically punish players in organizations a source covers
less. Pinned by `test_partial_coverage_is_never_imputed`.

**(b) A 1-source "consensus" is labelled as one.** Averaging one number returns that number. Every
row carries `consensus_n_sources` + `consensus_confidence` (`low (1 source)` / `medium (2)` /
`high (3+)`), and `consensus_rank_spread` is **NULL** rather than `0.0` for a lone source — `max −
min` over one value is 0, which renders as *"every source agrees exactly"*, the precise opposite of
what one opinion means. (Caught by a test, not by reading the output.)

**(c) Disagreement is a RESIDUAL, not a gap.** `source_rank − consensus_rank` flags the entire top
of the board because imperfectly-correlated rankings regress toward each other at the extremes —
E8.0 hit exactly this on its first real run (10 of its top 12 flagged). Every comparison column here
goes through the shared `board_assembly.residual_vs_fit`. Quantified on synthetic rankings that
agree in expectation: **raw-gap tail bias ≈ 20.6 percentile points → residual ≈ 3.6 (−82%)**, well
under the 15-point flag threshold. The residual is *not* claimed to be exactly unbiased — the fit is
linear while two bounded rank-percentiles are S-shaped related, so a little tail curvature survives.
Stated in the docstring and pinned by `TestResidualNotRawGap`, which asserts both that the broken
metric IS broken and that the shipped one is 3× better.

**(d) A source cannot disagree with a consensus it alone constitutes.** The first real run reported
a lopsided 89-vs-35 split of "FanGraphs org lower/higher" flags. The cause was not the ranking — it
was that 1-source rows were being compared against themselves through two different percentile
denominators. Restricting the residual to `n_sources ≥ 2` made the counts near-symmetric
(64/63 and 100/130), which is what two sources disagreeing at random looks like.

## 6. Our MLE line vs the CONSENSUS — the differentiated view

`mle_vs_consensus` is the residual of our E7.3/E7.3p translated line (E8.0's `model_score`) on the
consensus percentile, fitted **within player type × consensus scope**. The scope split matters: an
overall percentile of 50 means *"≈65th best prospect alive"* while an org percentile of 50 means
*"middle of one club's top 30"*, so pooling them would fit against an x whose meaning changes
mid-column. `consensus_scope_used` says which frame each row was judged in.

```
comparable 1,276    we're higher 194    consensus higher 207
```

Near-symmetric, as it must be for a mean-zero residual. Read it as a conversation starter: a large
positive means our translated MiLB line likes a player more than is usual for someone the scouts
place there — which is worth a look, and is not an edge claim.

## 7. 🕰️ Historical rankings — 2010–2026 ingested, and the two traps in them

The operator asked for history so MLB Pipeline's rankings can actually be *assessed*, not just
consumed. `/prospects/<year>/<list>/` serves archived lists and **the ranks are genuinely
point-in-time** — verified against what MLB published:

| season | #1 | #2 | #3 |
|---|---|---|---|
| 2015 | Byron Buxton | Kris Bryant | Carlos Correa |
| 2019 | Vladimir Guerrero Jr. | Fernando Tatís Jr. | Eloy Jiménez |
| 2023 | Gunnar Henderson | Corbin Carroll | Francisco Álvarez |

**Depth probed live:** 2008 and earlier → empty selection. **2010–2011 → Top 50.** 2012+ → Top 100.
Org Top 30s exist for the historical seasons too (`sel-pr-2015-orioles` resolves). So **17 seasons**
of MLBAM-keyed rankings, 100% id-populated on every season checked.

⚠️ **A study must not read "absent from the 2010 list" as "outside the top 100" — that list only
went to 50.** The ingest warns on those two seasons, and `EARLIEST_SEASON` / `TOP50_SEASONS` are
pinned constants.

### 7a. Two leakage traps, both found by inspection and both closed

**(i) The page's `Person` and `Team` entities are LIVE records, not archived ones.** On the 2015
page **Byron Buxton returns `currentAge` 32** (he was 21) and **Kris Bryant returns COL** (he was a
Cub). Using either as an as-of feature is straightforward leakage — and it would have been very easy
to miss, because the *rank* beside them is correctly historical. **Cure:** every such field is
suffixed **`_current`** (`org_current`, `age_current`, `affiliate_team_current`), so the mistake is
visible at the call site. The unsuffixed `org` is populated only from an **org list's URL**, which
genuinely is as-of that season; a Top-100 entry has no org of its own and gets NULL rather than a
borrowed current one. `birth_date` stays unsuffixed because it doesn't change — **age as of the
season is derivable from `birth_date` + the snapshot, which is the leakage-free way to get it.**

**(ii) The bio list runs PAST the season.** The 2015 page carries 2016/2017/2018 scouting reports
for 65 of its 100 players; my first implementation took the *newest* bio, which would have graded
the 2015 board off a 2018 report. **Cure:** `_select_bio` takes the report titled `season`, else the
newest **not after** it — never a later one — and stamps **`bio_season`** as the receipt. Measured
after the fix: **100/100 era-matched on 2015, 2019 and 2023; zero future bios on any season**, and
the coverage report warns loudly if a `bio_season > season` ever appears.

**(iii) As-of dating.** A past season stamps `as_of=<season>-02-01` (the preseason publication
window), never today. Stamping a 2015 board `2026-07-29` would place a decade-old opinion *after*
every outcome it is meant to predict and silently invert any study built on it — the same contract
E7.7 enforces for FanGraphs. `--as-of` overrides when the true publication date is known.

### 7c. Post-backfill spot check (operator ran the full ingest 2026-07-29)

All 17 seasons landed: **14,455 rows**, `as_of_date` correct on every one (historical = `<season>-02-01`,
current = the run date), **100.0% MLBAM id on every season**, and — the receipt that matters —
**ZERO rows graded off a report written after their snapshot season**, across the whole backfill.

Four anomalies were chased down; three are genuine upstream facts, one was our defect:

| observation | verdict |
|---|---|
| 2011 `dbacks`, 2014 `bluejays` absent | **upstream.** MLB declares `limit:30` and serves an **empty array** for those two org-seasons. Correctly recorded as "not published" rather than failing the backfill or writing zeros. |
| 2020 / 2021 Top 100 has **99** entries | **upstream.** Ranks 1–99, no gaps, no duplicates — MLB's list is genuinely 99 deep those years, not truncated by us. |
| 🚨 **org-list depth changes by era** | **upstream, and the most consequential finding here** — see below. |
| `bio_season = 201` on one 2016 row | **our defect, fixed.** See below. |

**🚨 ORG-LIST DEPTH IS NOT CONSTANT — a study must normalize for it.** Measured:

| era | org list depth |
|---|---|
| 2011 | Top **10** |
| 2012–2014 | Top **20** |
| 2015–2026 | Top **30** |

This matters more than the already-noted Top-50 overall lists, because the **org scope is where the
coverage breadth is** (735 of the 1,451 current-board players have a 2-source org consensus vs 62
overall). An org rank of 15 is mid-pack in 2023 and *did not exist* in 2013; "absent from the 2013
org list" means outside that club's top **20**, not top 30. Recorded as `ORG_LIST_DEPTH_BY_ERA` /
`OVERALL_LIST_DEPTH_BY_ERA`, warned on by the ingest for any pre-2015 season, and surfaced in the
coverage report as the **observed** `published depth` — which is authoritative, since the constants
are a summary, not a substitute for reading `max(rank)` per (season, list).

**The one real defect: `.isdigit()` is not "is a year".** The live feed contains a `contentTitle`
of `"201"`. It is digits, so it parsed as the year 201 — which sorts *below* every real season and
therefore quietly wins the "newest bio not after the season" fallback whenever nothing else
qualifies, reporting `bio_season = 201` into a study. It hit **1 row of 14,455** and could never
cause leakage (201 is in the past, not the future), but it is nonsense in the output. Fixed by
constraining a parsed title to `MIN_BIO_YEAR`–`MAX_BIO_YEAR`; an out-of-range title is now treated
as **undated** (`bio_season` NULL), which is the honest answer. The row's grades are still used —
only their dating claim was withdrawn. ⏭️ The stored row keeps `201` until the next re-ingest of
2016; it is cosmetic and needs no re-backfill.

### 7b. What the accuracy study still needs (NOT run here)

The substrate is now there, but **"are MLB Pipeline's rankings any good?" is an E7.8-shaped
question, not a coverage report**, and answering it credibly needs what E7.8 needed: a realized
outcome (accumulated fantasy points over the N seasons after each snapshot, with a prospect who
never arrives scoring **zero** — that is what dissolves survivorship), leave-one-cohort-out CV with
a **player purge** (a prospect appears on 3–5 consecutive boards sharing one outcome window), and
PBO/DSR/FDR deflation over every config tried.

The good news is that harness already exists and was built for exactly this question about
FanGraphs FV: `betting_ml/scripts/fv_translation/` (`build_fv_cohort.py` + `run_fv_translation.py`).
Pointing it at `mlb_pipeline_rankings` instead of `the_board` is a bounded follow-on, and it would
answer something genuinely new — **E7.8 measured FV; nobody has measured Pipeline, and a
head-to-head between two sources on the same cohort with the same gates is a stronger test than
either alone.** ⚠️ It also inherits E7.8's binding constraint: ~5–17 cohorts is enough to rule out a
large effect, not a small one. I did not run it, and this report makes **no accuracy claim** —
`best_alpha = 0` stands.

## 8. What was NOT done

* **No accuracy test.** Whether the consensus (or our divergence from it) predicts anything is a
  separate, E7.8-shaped question requiring realized outcomes and deflated gates. The *substrate* for
  it now exists (§7) and the harness already exists (`betting_ml/scripts/fv_translation/`), but the
  study was not run. Not attempted, not claimed. `best_alpha = 0`.
* **No third ingested source.** Prospects Live was probed and refused on its own robots (§1). The
  manual path exists and is documented, but no paywalled source was hand-keyed in this session —
  that is the operator's call, and the code works with zero, one, or many of them.
* **No serving surface.** This writes files. E8.1 owns the in-app board.
* **The Delta table is not yet written.** The verification run used `--pipeline-from-dir` over the
  ingest's cached HTML; the S3 write is in the operator handoff.

## 9. Regenerating

```bash
# LAPTOP — 1. ingest MLB Pipeline, current season (31 polite page fetches, ~1 min)
AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py --season 2026

# LAPTOP — 1b. HISTORY for the accuracy study. Top-100 only (~17 pages, ~30 s):
AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py \
    --seasons 2010-2025 --lists top100
#      …or the full history incl. org lists (17 x 31 pages, ~15 min — operator-run):
AWS_DEFAULT_REGION=us-east-2 uv run python scripts/ingest_mlb_pipeline_to_s3.py --seasons 2010-2025

# LAPTOP — 2. build the consensus board (~2 min; S3 reads over the xref + MLE tables)
AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
    betting_ml.scripts.prospect_board.build_consensus

# optional: add hand-keyed paywalled second opinions
uv run python -m betting_ml.scripts.prospect_board.build_consensus --write-manual-template
AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
    betting_ml.scripts.prospect_board.build_consensus \
    --manual baseball_america=~/ba_top100.csv --manual keith_law=~/law_top100.csv
```

The ingest is a **hand-run job, not a daily op** — rankings move on a weekly-ish cadence, so it is
deliberately not wired into any Dagster schedule.
