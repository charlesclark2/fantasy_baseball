# E12 Serving-Parity Report (2026-06-22) — tier `prod`

- Live `data_source`: **feature_store**, 12 game(s)
- Served tier: **prod** (`total_runs`=113, `run_differential`=169, `home_win`=211)

Per SERVED target: how the LIVE served matrix compares to the contract the
morning tier actually serves and to the training distribution.
`served-but-ALL-NULL` columns are imputed to a single training-median constant
for every game → zero discrimination. `parity_ok` fails only on a structural-absent
column or a STRONG-TIER column flattened/absent (the live-skill killers).

## total_runs — prod (contract 113)  ✅ PASS

- structurally served: **113/113**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/2**

## run_differential — prod (contract 169)  ✅ PASS

- structurally served: **169/169**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/12**

## home_win — prod (contract 211)  ✅ PASS

- structurally served: **211/211**  (absent→0.0-fill: 0)
- served-but-ALL-NULL→constant-impute: **0**  (**0%** of the matrix flattened to a constant live)
- column ORDER parity: OK (all present, reindex preserves contract order)
- STRONG-TIER served null/absent: **0/15**
