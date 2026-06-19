# E12 Serving-Parity Report (2026-06-19) — tier `pre_lineup`

- Live `data_source`: **intraday_assembly**, 14 game(s)
- Served tier: **pre_lineup** (`total_runs`=89, `run_differential`=126, `home_win`=156)

Per SERVED target: how the LIVE served matrix compares to the contract the
morning tier actually serves and to the training distribution.
`served-but-ALL-NULL` columns are imputed to a single training-median constant
for every game → zero discrimination. `parity_ok` fails only on a structural-absent
column or a STRONG-TIER column flattened/absent (the live-skill killers).

## total_runs — pre_lineup (contract 89)  ✅ PASS

- structurally served: **89/89**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/1**

## run_differential — pre_lineup (contract 126)  ✅ PASS

- structurally served: **126/126**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **1**  (**1%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/9**

<details><summary>served-but-all-null columns (live null / train null)</summary>

  - `series_game_number` — train null 0.00%

</details>

## home_win — pre_lineup (contract 156)  ✅ PASS

- structurally served: **156/156**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **1**  (**1%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/11**

<details><summary>served-but-all-null columns (live null / train null)</summary>

  - `series_game_number` — train null 0.00%

</details>

---

## Champion-shadow (why morning routes to pre-lineup)

What the **champion** contract would have imputed on the SAME morning matrix —
the gap the Story 33.0 tier-split sidesteps by serving the pre-lineup model.

- **total_runs** champion (113): 16 all-null→const (14%), strong-tier degraded 1/2
- **run_differential** champion (169): 41 all-null→const (24%), strong-tier degraded 3/12
- **home_win** champion (211): 52 all-null→const (25%), strong-tier degraded 4/15
