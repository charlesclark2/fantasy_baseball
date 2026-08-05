"""NF-W0a — the NFL point-in-time (PIT) immutable capture store + fail-closed leakage guards.

Two halves, deliberately separable (the story's 🚦 sequencing rule — the 2026-09-10 opener puts
the clock on the CAPTURE, not on the framework):

  1. FORWARD CAPTURE (time-critical, ships first) — `weather_capture` / `market_capture` /
     `injury_capture` / `schema_snapshot`. Each writes RAW, IMMUTABLY, stamped with the §13
     timestamp keys. A week not captured is a week PERMANENTLY absent from the training frame:
     the Open-Meteo archive returns OBSERVATIONS, never the forecast that stood on a historical
     Tuesday, and only CLOSING lines exist in the odds history.
  2. THE STORE + GUARD (built around the accruing data) — `timestamps` (the key contract),
     `store` (append-only immutable Delta + write-once raw payloads), `leakage_guard` (the
     fail-closed §13 rejection set, RED-proven case by case).

Everything here is DuckDB/S3-native and Snowflake-FREE.
"""
