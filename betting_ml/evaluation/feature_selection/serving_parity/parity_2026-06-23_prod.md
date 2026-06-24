# E12 Serving-Parity Report (2026-06-23) — tier `prod`

- Live `data_source`: **feature_store**, 15 game(s)
- Served tier: **prod** (`total_runs`=15, `run_differential`=15, `home_win`=21)

Per SERVED target: how the LIVE served matrix compares to the contract the
morning tier actually serves and to the training distribution.
`served-but-ALL-NULL` columns are imputed to a single training-median constant
for every game → zero discrimination. `parity_ok` fails only on a structural-absent
column or a STRONG-TIER column flattened/absent (the live-skill killers).

## total_runs — prod (contract 15)  ✅ PASS

- structurally served: **15/15**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/0**

## run_differential — prod (contract 15)  ✅ PASS

- structurally served: **15/15**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/2**

## home_win — prod (contract 21)  ✅ PASS

- structurally served: **21/21**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/2**
