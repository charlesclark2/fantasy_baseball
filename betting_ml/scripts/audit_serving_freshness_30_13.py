"""
audit_serving_freshness_30_13.py — Story 30.13 Task 1: serving-path FRESHNESS map.

Distinct from the 30.12 COMPLETENESS map (null-rate in the offline-dense historical table). THIS audit
asks, for UPCOMING games (the serve surface): is each serving-path feature block STALE / ABSENT at serve
time, and WHY. For every block it reports:
  - feature-table build time      (information_schema.tables.LAST_ALTERED — when dbt/Python last wrote it)
  - latest source ingestion        (max(ingestion_ts) on the staging the block depends on)
  - staleness_lag                  (ingestion - build; POSITIVE ⇒ table built BEFORE the latest ingestion
                                     landed ⇒ the block has NOT absorbed the newest data = build-ordering stale)
  - upcoming-game null-rate         (today / +1d / +2d on feature_pregame_game_features)

…and classifies each block into the failure class that determines WHO fixes it:
  - build_ordering : NON-lineup block that's stale/null because the feature store rebuilt before the latest
                     ingestion. THIS is 30.13's target (build-ordering guarantee + serve-time gate).
  - point_in_time  : LINEUP-dependent block null for future games BY DESIGN (lineups aren't posted until
                     ~game day). NOT a bug — the serve-time gate must ABSTAIN (not alarm) on pre-lineup
                     serves; the real fix is the pre/post-lineup CONTRACT (Story 30.8). Reported for
                     completeness, NOT counted as a freshness defect.
  - fresh          : dense + built after the latest ingestion.

Verified headline (2026-06-15): the prod feature store (feature_pregame_game_features, built 15:34) was
already STALE vs stg_statsapi_probable_pitchers/lineups (ingested 16:00) — no build-ordering guarantee.
Non-lineup blocks were 0% null for today/+1 after the 30.6 watermark rebuild; lineup blocks 100% null at
+1/+2 (point_in_time, by design).

HAND-OFF: a handful of fast aggregate Snowflake queries (<1 min) but it IS a Snowflake script, so run it
yourself with real creds:

    uv run python betting_ml/scripts/audit_serving_freshness_30_13.py

Outputs:
    quant_sports_intel_models/baseball/ablation_results/serving_freshness_30_13.md
    quant_sports_intel_models/baseball/ablation_results/serving_freshness_30_13.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

_DB = "baseball_data"
_FEATURE_SCHEMA = "BETTING_FEATURES"
_FEATURE_TABLE = f"{_DB}.{_FEATURE_SCHEMA}.feature_pregame_game_features"
_OUT_MD = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/serving_freshness_30_13.md"
_OUT_CSV = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/serving_freshness_30_13.csv"

# Intraday-changing source stagings. A block is "stale" only vs the source it ACTUALLY
# depends on intraday. Overnight-sourced blocks (bullpen/team/pythag/elo) do NOT depend on
# these intraday polls — comparing them here is a FALSE POSITIVE (the 2026-06-15 bullpen 6.5h
# artifact). They refresh once/day in daily_ingestion_job + statcast_catchup_job.
_SOURCES = {
    "probable_pitchers": f"{_DB}.BETTING.stg_statsapi_probable_pitchers",
    "lineups":           f"{_DB}.BETTING.stg_statsapi_lineups",
}

# Serving-path blocks. `repr_cols` = representative serve columns (null-profiled on upcoming games);
# `build_table` = (schema, table) whose LAST_ALTERED is the block's build time;
# `intraday_source` = the intraday staging the block must be built AFTER (None ⇒ OVERNIGHT-sourced:
#     freshness = "built today", not vs an intraday poll — avoids the false-positive above);
# `lineup_dependent` = True ⇒ future-game nulls are point-in-time BY DESIGN (Story 30.8), not 30.13 defects.
_BLOCKS = [
    {"block": "starter_eb",        "repr_cols": ["home_starter_eb_xwoba_against", "away_starter_eb_xwoba_against"],
     "build_table": ("BETTING", "EB_STARTER_POSTERIORS"),       "intraday_source": "probable_pitchers", "lineup_dependent": False},
    {"block": "starter_sequential", "repr_cols": ["home_starter_eb_xwoba_against_sequential"],
     "build_table": ("BETTING", "EB_STARTER_POSTERIORS"),       "intraday_source": "probable_pitchers", "lineup_dependent": False},
    {"block": "bullpen_eb",        "repr_cols": ["home_bp_eb_xwoba", "away_bp_eb_xwoba"],
     "build_table": ("BETTING", "EB_BULLPEN_POSTERIORS"),       "intraday_source": None, "lineup_dependent": False},
    {"block": "team_sequential",   "repr_cols": ["home_team_sequential_woba"],
     "build_table": ("BETTING_FEATURES", "FEATURE_PREGAME_GAME_FEATURES_RAW"), "intraday_source": None, "lineup_dependent": False},
    {"block": "pythagorean",       "repr_cols": ["home_pythagorean_win_exp"],
     "build_table": ("BETTING_FEATURES", "FEATURE_PREGAME_GAME_FEATURES_RAW"), "intraday_source": None, "lineup_dependent": False},
    {"block": "elo",               "repr_cols": ["home_elo"],
     "build_table": ("BETTING_FEATURES", "FEATURE_PREGAME_GAME_FEATURES_RAW"), "intraday_source": None, "lineup_dependent": False},
    {"block": "batter_sequential", "repr_cols": ["home_avg_eb_woba_sequential"],
     "build_table": ("BETTING_FEATURES", "FEATURE_PREGAME_LINEUP_FEATURES"), "intraday_source": "lineups", "lineup_dependent": True},
    {"block": "lineup_archetype",  "repr_cols": ["home_lineup_archetype_avg_xwoba", "away_lineup_archetype_avg_xwoba"],
     "build_table": ("BETTING_FEATURES", "FEATURE_PREGAME_LINEUP_FEATURES"), "intraday_source": "lineups", "lineup_dependent": True},
    {"block": "lineup_statcast",   "repr_cols": ["home_lineup_avg_bat_speed"],
     "build_table": ("BETTING_FEATURES", "FEATURE_PREGAME_LINEUP_FEATURES"), "intraday_source": "lineups", "lineup_dependent": True},
]

_NULL_TOL = 5.0   # upcoming-game null-rate above this (for a NON-lineup block) = stale-at-serve


def _scalar(cur, sql: str):
    cur.execute(sql)
    r = cur.fetchone()
    return r[0] if r else None


def _ts_pair(cur, expr: str, frm: str, where: str = "") -> tuple:
    """Return (display_string, epoch_seconds) for a timestamp expression.

    Zone handling: `ingestion_ts` is TIMESTAMP_NTZ stored in SESSION-LOCAL wall clock
    (verified: max(ingestion_ts) tracks current_timestamp in the -07 session), while
    `last_altered` is TIMESTAMP_LTZ (absolute). Casting BOTH to `::timestamp_ntz`
    renders each in the session-local wall clock; `epoch_second` then treats both on
    the same as-if-UTC basis, so the constant offset cancels and the DIFFERENCE is the
    true lag (positive ⇒ ingested after build = stale)."""
    cur.execute(f"select to_varchar(({expr})::timestamp_ntz,'YYYY-MM-DD HH24:MI'), "
                f"date_part(epoch_second, ({expr})::timestamp_ntz) from {frm} {where}")
    r = cur.fetchone()
    if not r or r[0] is None:
        return (None, None)
    return (r[0], float(r[1]))


def _build_times(cur) -> dict:
    out = {}
    for schema, table in {(b["build_table"]) for b in _BLOCKS}:
        out[(schema, table)] = _ts_pair(cur, "last_altered", f"{_DB}.information_schema.tables",
                                        f"where table_schema='{schema}' and table_name='{table}'")
    return out


def _ingestion_times(cur) -> dict:
    return {k: _ts_pair(cur, "max(ingestion_ts)", v) for k, v in _SOURCES.items()}


def _upcoming_null_profile(cur) -> pd.DataFrame:
    """null-rate per repr col for today / +1 / +2 day buckets."""
    cols = sorted({c for b in _BLOCKS for c in b["repr_cols"]})
    exprs = ",\n  ".join(f"round(100*avg(iff({c} is null,1,0)),1) as {c}" for c in cols)
    sql = (f"select datediff('day', current_date(), game_date) as d, count(*) as games,\n  {exprs}\n"
           f"from {_FEATURE_TABLE} where game_date >= current_date() and game_date <= dateadd('day',2,current_date())\n"
           f"group by 1 order by 1")
    cur.execute(sql)
    names = [d[0].lower() for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=names)


def main() -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        builds = _build_times(cur)
        ingest = _ingestion_times(cur)
        prof = _upcoming_null_profile(cur)
        today_str = _scalar(cur, "select to_varchar(current_date(),'YYYY-MM-DD')")
    finally:
        conn.close()

    # null lookups by day-offset
    def null_for(cols, d):
        row = prof[prof["d"] == d]
        if row.empty:
            return None
        vals = [float(row.iloc[0][c]) for c in cols if c in prof.columns]
        return max(vals) if vals else None  # worst repr col = the block's serve null

    games_by_d = {int(r.d): int(r.games) for r in prof.itertuples()}

    rows = []
    for b in _BLOCKS:
        src = b["intraday_source"]
        bt_str, bt_epoch = builds.get(b["build_table"], (None, None))
        it_str, it_epoch = ingest.get(src, (None, None)) if src else ("(overnight)", None)
        lag_min = None
        if src and bt_epoch is not None and it_epoch is not None:
            lag_min = round((it_epoch - bt_epoch) / 60.0, 1)  # >0 ⇒ ingested AFTER build = stale
        built_today = bool(bt_str and today_str and bt_str.startswith(today_str))
        n_today, n1, n2 = null_for(b["repr_cols"], 0), null_for(b["repr_cols"], 1), null_for(b["repr_cols"], 2)

        # classification. Non-lineup blocks key on null_TODAY (today's slate is fully
        # announced; future-game nulls for non-lineup blocks = unannounced starters =
        # point-in-time, NOT a defect). lineup-dependent → point_in_time by design.
        if b["lineup_dependent"]:
            cls = "point_in_time"          # null-for-future BY DESIGN → Story 30.8
        elif n_today is not None and n_today > _NULL_TOL:
            cls = "stale_now"              # actively ABSENT at serve for today → severe 30.13 defect
        elif src is None:
            # OVERNIGHT-sourced: fresh iff rebuilt today (morning job / statcast-catchup);
            # NOT compared to intraday polls (that was the bullpen false-positive).
            cls = "fresh" if built_today else "stale_overnight"
        elif lag_min is not None and lag_min > 0:
            cls = "unguaranteed"           # present now, but store built BEFORE latest intraday
                                           # ingestion = build-ordering EXPOSURE (30.13 closes this)
        else:
            cls = "fresh"

        rows.append({
            "block": b["block"], "class": cls, "lineup_dependent": b["lineup_dependent"],
            "build_table": ".".join(b["build_table"]),
            "build_last_altered": bt_str, "built_today": built_today,
            "intraday_source": src or "(overnight)", "source_latest_ingestion": it_str,
            "staleness_lag_min": lag_min,
            "null_today": n_today, "null_plus1": n1, "null_plus2": n2,
        })
    out = pd.DataFrame(rows)
    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(_OUT_CSV, index=False)

    # ── report ──
    stale_now = out[out["class"] == "stale_now"]
    stale_on = out[out["class"] == "stale_overnight"]
    unguar = out[out["class"] == "unguaranteed"]
    pit = out[out["class"] == "point_in_time"]
    fresh = out[out["class"] == "fresh"]
    intraday_lag = out[out["intraday_source"] != "(overnight)"]["staleness_lag_min"].dropna()
    hdr_lag = f"{intraday_lag.max():.0f} min" if len(intraday_lag) else "n/a"

    def _tbl(sub):
        if sub.empty:
            return "_(none)_\n"
        h = ("| block | class | build (LAST_ALTERED) | intraday source | latest ingestion | lag(min) | null today/+1/+2 |\n"
             "|---|---|---|---|---|---|---|\n")
        return h + "".join(
            f"| `{r.block}` | {r['class']} | {r.build_last_altered} | {r.intraday_source} | {r.source_latest_ingestion} | "
            f"{r.staleness_lag_min} | {r.null_today}/{r.null_plus1}/{r.null_plus2} |\n"
            for _, r in sub.iterrows())

    md = (
        f"# Story 30.13 — Serving-path freshness map (Task 1)\n\n"
        f"Upcoming games audited: today={games_by_d.get(0,0)}, +1={games_by_d.get(1,0)}, +2={games_by_d.get(2,0)}. "
        f"A block is judged vs the source it ACTUALLY depends on intraday: `probable_pitchers` (starter blocks) / "
        f"`lineups` (lineup blocks) / `(overnight)` (bullpen/team/pythag/elo — refreshed once/day, NOT vs intraday "
        f"polls). `staleness_lag_min` >0 ⇒ built before the latest intraday ingestion. Worst intraday lag: **{hdr_lag}**.\n\n"
        f"**Classes** (who owns the fix):\n"
        f"- **stale_now** ({len(stale_now)}) — block ABSENT at serve for TODAY's slate. Severe; 30.13's acute target.\n"
        f"- **stale_overnight** ({len(stale_on)}) — OVERNIGHT-sourced block NOT rebuilt today (morning job / "
        f"statcast-catchup didn't run or failed). 30.13 build-ordering target.\n"
        f"- **unguaranteed** ({len(unguar)}) — intraday block present now BUT built before the latest intraday ingestion "
        f"(positive lag). Build-ordering EXPOSURE: a starter/lineup change between build and serve ships stale. The "
        f"every-10-min lineup_monitor self-heals within a cycle; the serve-time gate (Task 4) removes the residual.\n"
        f"- **point_in_time** ({len(pit)}) — LINEUP-dependent block null for future games BY DESIGN (lineups post "
        f"~game day). NOT a 30.13 defect; the gate must ABSTAIN on pre-lineup serves → Story 30.8 pre/post contract.\n"
        f"- **fresh** ({len(fresh)}).\n\n"
        f"## 🔴 stale_now (acute — absent at serve today)\n\n" + _tbl(stale_now) +
        f"\n## 🟠 stale_overnight (overnight compute didn't refresh today)\n\n" + _tbl(stale_on) +
        f"\n## 🟡 unguaranteed (intraday build-ordering exposure)\n\n" + _tbl(unguar) +
        f"\n## point_in_time (by design → Story 30.8; reported, not a defect)\n\n" + _tbl(pit) +
        f"\n## 🟢 fresh\n\n" + _tbl(fresh) +
        f"\n**Note:** EB posterior tables (`eb_starter_posteriors`, `eb_bullpen_posteriors`) carry NO build-timestamp "
        f"column — freshness is inferred from `LAST_ALTERED` only. Adding a `computed_at` to the EB computes would let "
        f"the serve-time gate assert per-row freshness directly (recommend in the 30.13 Task-4 gate).\n"
    )
    _OUT_MD.write_text(md)

    print(out.to_string(index=False))
    print(f"\nWrote {_OUT_MD}\n      {_OUT_CSV}")
    print(f"\nstale_now: {len(stale_now)}  stale_overnight: {len(stale_on)}  unguaranteed: {len(unguar)}  "
          f"point_in_time: {len(pit)}  fresh: {len(fresh)}  worst_intraday_lag={hdr_lag}")


if __name__ == "__main__":
    main()
