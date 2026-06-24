# E12 Serving-Parity Report (2026-06-23) — tier `pre_lineup`

- Live `data_source`: **feature_store**, 15 game(s)
- Served tier: **pre_lineup** (`total_runs`=16, `run_differential`=126, `home_win`=38)

Per SERVED target: how the LIVE served matrix compares to the contract the
morning tier actually serves and to the training distribution.
`served-but-ALL-NULL` columns are imputed to a single training-median constant
for every game → zero discrimination. `parity_ok` fails only on a structural-absent
column or a STRONG-TIER column flattened/absent (the live-skill killers).

## total_runs — pre_lineup (contract 16)  ✅ PASS

- structurally served: **16/16**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/0**

## run_differential — pre_lineup (contract 126)  ✅ PASS

- structurally served: **126/126**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/9**

## home_win — pre_lineup (contract 38)  ✅ PASS

- structurally served: **38/38**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/4**
