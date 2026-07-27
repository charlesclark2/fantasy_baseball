"""player_xref.py — MLB Edge-E7.4: the prospect identity spine (`dim_player_xref`).

Builds ONE crosswalk + prospect dimension keyed on the **MLBAM id**, so a prospect's minor-league
record, his FanGraphs scouting grade, and (after a call-up) his MLB identity all reconcile to one
person. Pure DuckDB over the S3 Delta lake — SF-FREE. The NCAAF-P0.3 analog
(`quant_sports_intel_models/football/ncaaf/feeder/xref.py`) is the shape this mirrors: a tested
Python builder with hard anti-cartesian assertions + a per-hop match-rate report, not un-runnable
SQL.

🧬 THE DOMAIN SPINE (non-obvious — preserve it)
----------------------------------------------
**MLBAM `person.id` is ONE stable id for a player's WHOLE career, minors AND majors** → it is the
spine and everything hangs off it. **FanGraphs is the fragmenter**: a stable minor-league id
(`minorMasterId`, the `sa`-prefixed `fg_minor_id`) plus a SEPARATE numeric MLB id (`fg_mlb_id`,
assigned at debut). So a graduating prospect acquires a NEW FanGraphs id, and the xref must bridge
`fg_minor_id` → `fg_mlb_id` → MLBAM for his minor and major records to reconcile.

⭐ THE BRIDGE (verified on the REAL lake 2026-07-27 — see `ablation_results/e7_4_prospect_xref.md`)
--------------------------------------------------------------------------------------------------
THE BOARD carries **no MLBAM id at all** (the column exists and is 100% NULL). The prospect→MLBAM
bridge therefore routes through the E7.7 *leaderboard* feed, which carries BOTH ids:

    board.fg_minor_id ──▶ fg_leaderboards.fg_minor_id ──▶ fg_leaderboards.mlbam_id (xMLBAMID) ──▶ SPINE
                     (HOP 1: 99.3% current / 99.6–99.9% historical)   (HOP 2: 100% populated, numeric)

with a second, independent leg for graduates (and as the `fg_mlb_id` source the story asks for):

    board.fg_player_id (numeric ⇒ an MLB FG id) ──▶ fg_hitting_leaderboard_raw / fg_stuff_plus_raw
                                                    ($.playerid → $.xMLBAMID) ──▶ SPINE   (97.2%)

🚨 LANDMINES THIS BUILDER ENCODES (each cost real time to find — do not "simplify" them away)
---------------------------------------------------------------------------------------------
1. **`delta_scan` CANNOT read `baseball/milb/the_board`.** Its `mlbam_id` column is 100% NULL, so
   pyarrow inferred an arrow `null` type and the Delta schema records `"void"` — DuckDB's delta
   reader hard-errors `Unsupported Delta table type: 'void'`. The board is therefore read through
   `DeltaTable(...).to_pyarrow_dataset()` (`board_relation()` below). The ingest has since been
   pinned to write string columns as strings, but the ALREADY-WRITTEN partitions keep the void
   schema until a full re-backfill — so this reader stays regardless.
2. **NEVER read the board with a `read_parquet('…/**/*.parquet')` glob.** A glob has no Delta file
   list, so it unions TOMBSTONED files: the 2026-07-27 partition globs to 3,870 rows across three
   superseded ingest generations vs the ACID truth of 1,290 — and the stale generation extracted
   `fg_minor_id` DIFFERENTLY (numeric MLB ids for graduates), which silently drags the measured
   HOP-1 match rate from 99.3% down to 84.2%. Same class as the E11.20 phase-1.5 path-reader
   incident. `board_relation()` is the only sanctioned reader.
3. **A `read_parquet`-glob-derived match rate is not a match rate** — see (2). Every number in the
   report comes off the Delta-correct relation.
4. **No fuzzy name matching.** The deterministic legs resolve 99.3% of the current board; the 9
   unresolved are pre-pro signees/draftees with NO MLBAM record to match to, and the single
   name-equality hit against the MiLB logs was a FALSE POSITIVE (prospect "Michael Massey", DET vs
   MLB 2B Michael Massey, id 686681, Royals). No match beats a wrong match — unresolved rows are
   emitted honestly with `mlbam_match_method='unresolved'` and a NULL `mlbam_id`.

WHAT A ROW IS
-------------
One row per **`mlbam_id`** (the spine), plus one row per board prospect the deterministic legs
could NOT resolve (`mlbam_id` NULL, keyed on `fg_minor_id`). `xref_key` is the non-null identity
key either way, so the table has exactly one row per person and joins cleanly.

Every row carries the identity ids, the current-state dimension attributes (level / age / org /
position / birth date), the latest-board prospect attributes (FV / ETA / risk / ranks), presence
flags against each source, and the provenance stamp (`mlbam_match_method` /
`mlbam_match_confidence`) the AC requires — so a downstream model can weight by confidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("e7_4.xref")

XREF_TABLE = "dim_player_xref"
XREF_VERSION = "e7.4-v1"

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
LAKEHOUSE_RAW = f"{BUCKET}/baseball/lakehouse_raw"

# ── Dead-bridge tripwires ────────────────────────────────────────────────────────────────────
# A cross-source ID xref fails SILENTLY and CI-green when a vendor renames a field (the P1.2b
# `athleteId` incident: 7 matched rows where the real key matched 60,883). These floors turn that
# into a LOUD build failure. Set BELOW the measured rates with headroom for genuine drift, not at
# them — a floor that trips on normal week-to-week churn gets disabled, which defeats the point.
MIN_BOARD_TO_LEADERBOARD_RATE = 0.90   # measured 0.993 current / 0.996–0.999 historical
MIN_LEADERBOARD_MLBAM_POPULATION = 0.95  # measured 1.000
MIN_LEADERBOARD_MLBAM_NUMERIC = 0.99   # measured 1.000 — an MLBAM id is always all-digits
MIN_BOARD_RESOLUTION_RATE = 0.90       # measured 0.993 end-to-end on the current snapshot

# Provenance vocabulary (stamped on every row; `high` = a deterministic vendor-published id pair).
MATCH_FG_LEADERBOARD = "fg_leaderboard_xmlbamid"
MATCH_FG_MLB_GRADUATE = "fg_mlb_leaderboard_playerid"
MATCH_MILB_NATIVE = "milb_game_log_native"
MATCH_MLB_NATIVE = "statsapi_profile_native"
MATCH_UNRESOLVED = "unresolved"

_HIGH_CONFIDENCE = {
    MATCH_FG_LEADERBOARD,
    MATCH_FG_MLB_GRADUATE,
    MATCH_MILB_NATIVE,
    MATCH_MLB_NATIVE,
}


class XrefValidationError(RuntimeError):
    """A build invariant failed — a dead bridge, a cartesian join, or a duplicate identity key.

    HARD stop, never a silent wrong xref: an id crosswalk that quietly resolves 7 rows instead of
    60,883 is green everywhere downstream and poisons every model that joins through it.
    """


@dataclass
class XrefSources:
    """The FROM-expressions (or registered view names) for each input relation.

    Injectable so the SAME join SQL runs against the real S3 lake (the box runtime gate) and
    against local parquet fixtures in the fast gate — one copy of the joins, provable offline.
    """
    board: str
    leaderboards: str
    milb_game_logs: str
    mlb_player_profiles: str
    fg_mlb_hitting_raw: str
    fg_mlb_pitching_raw: str


@dataclass
class XrefResult:
    dim: Any                                            # pandas DataFrame — the dimension
    report: dict[str, Any] = field(default_factory=dict)


# ── Source resolvers ─────────────────────────────────────────────────────────────────────────

def s3_sources() -> XrefSources:
    """The real-lake FROM-expressions. NOTE `board` is a *view name* — it must be registered by
    `register_board(conn)` first (landmine 1: the board is unreadable by `delta_scan`)."""
    return XrefSources(
        board="board_src",
        leaderboards=f"delta_scan('{MILB}/fg_leaderboards')",
        milb_game_logs=f"delta_scan('{MILB}/player_game_logs')",
        mlb_player_profiles=(
            f"read_parquet('{LAKEHOUSE}/stg_statsapi_player_profiles/**/*.parquet',"
            " union_by_name=true)"
        ),
        fg_mlb_hitting_raw=(
            f"read_parquet('{LAKEHOUSE_RAW}/fg_hitting_leaderboard_raw/**/*.parquet',"
            " union_by_name=true)"
        ),
        fg_mlb_pitching_raw=(
            f"read_parquet('{LAKEHOUSE_RAW}/fg_stuff_plus_raw/**/*.parquet', union_by_name=true)"
        ),
    )


def register_board(conn, uri: str | None = None, view: str = "board_src") -> None:
    """Register THE BOARD as `view` using the Delta ACID file list.

    ⚠️ This is NOT interchangeable with `delta_scan` or a parquet glob — see landmines 1 and 2 at
    the top of this module. `to_pyarrow_dataset()` is the only reader that both tolerates the
    `void`-typed `mlbam_id` column AND honours the Delta tombstones.
    """
    from deltalake import DeltaTable

    try:
        from scripts.utils.delta_lake import storage_options
    except ImportError:  # pragma: no cover — lean-image layout
        from utils.delta_lake import storage_options

    dt = DeltaTable(uri or f"{MILB}/the_board", storage_options=storage_options())
    conn.register(view, dt.to_pyarrow_dataset())


# ── Building blocks ──────────────────────────────────────────────────────────────────────────
#
# Each is a self-contained CTE body so the per-hop match-rate report can be computed off the SAME
# relations the final dimension is built from (a report measured on a different read than the
# build is worthless — landmine 3).

def _board_latest_sql(src: XrefSources) -> str:
    """THE BOARD, deduped to ONE row per (season, fg_minor_id).

    Two independent dedupes, both load-bearing:
      • `as_of_date = max(as_of_date)` per season — snapshots accumulate by design (E7.8 as-of
        joins want the history; the DIMENSION wants only the newest view of each player).
      • `ingested_at_utc desc` within the partition — defensive against a same-day re-ingest
        landing more than one generation, so the dimension always reflects the newest extraction.
    """
    return f"""
    with b as (select * from {src.board} where fg_minor_id is not null),
         latest_asof as (select season, max(as_of_date) as as_of_date from b group by 1),
         picked as (
            select b.*, row_number() over (
                partition by b.season, b.fg_minor_id order by b.ingested_at_utc desc
            ) as rn
            from b join latest_asof using (season, as_of_date)
         )
    select * exclude (rn) from picked where rn = 1
    """


def _leaderboard_bridge_sql(src: XrefSources) -> str:
    """HOP 1+2 collapsed: `fg_minor_id` → the newest `mlbam_id` FanGraphs has published for him.

    Deliberately season-AGNOSTIC. A same-season join drops ~5% (a board prospect who did not
    record a stat line that year — injured, promoted early, or a DSL/complex assignment the
    leaderboard season filter misses); the id itself is career-stable, so the newest observation
    of the pair is the right one. Measured: 79–96% same-season vs 99.6–99.9% any-season.
    """
    return f"""
    select fg_minor_id,
           argmax(mlbam_id, coalesce(as_of_date, '') || '|' || cast(season as varchar)) as mlbam_id
    from {src.leaderboards}
    where fg_minor_id is not null and mlbam_id is not null
    group by 1
    """


def _fg_mlb_bridge_sql(src: XrefSources) -> str:
    """The graduate leg: the FanGraphs **MLB** id ↔ MLBAM pair, from the MLB feeds.

    Both MLB FanGraphs feeds store the vendor record verbatim in `raw_json`, carrying `$.playerid`
    (the numeric MLB FG id = `fg_mlb_id`) and `$.xMLBAMID`. Hitters come from the hitting
    leaderboard, pitchers from Stuff+; unioned because a player appears in exactly one.

    ⏱️ Restricted to the NEWEST `dt` snapshot per season. These feeds re-land the full leaderboard
    every capture day (~230k ~10KB JSON rows across all `dt` partitions), but an id PAIR is
    career-stable — every extra snapshot re-derives the identical pair at full JSON-decode cost.
    Taking one snapshot per season reads the same players from ~10× fewer rows. The cheap
    `(season, dt)` pre-pass touches only two columns; `raw_json` is decoded once per season.
    """
    def _latest_per_season(rel: str, alias: str) -> str:
        return f"""
        {alias} as (
            select raw_json from {rel}
            qualify dt = max(dt) over (partition by season)
        )"""

    return f"""
    with {_latest_per_season(src.fg_mlb_hitting_raw, 'h')},
         {_latest_per_season(src.fg_mlb_pitching_raw, 'p')},
         pairs as (
            select json_extract_string(raw_json, '$.playerid')  as fg_mlb_id,
                   json_extract_string(raw_json, '$.xMLBAMID')  as mlbam_id
            from h
            union all
            select json_extract_string(raw_json, '$.playerid')  as fg_mlb_id,
                   json_extract_string(raw_json, '$.xMLBAMID')  as mlbam_id
            from p
         )
    select fg_mlb_id, max(mlbam_id) as mlbam_id
    from pairs
    where fg_mlb_id is not null and mlbam_id is not null
    group by 1
    """


def _milb_player_state_sql(src: XrefSources, season_floor: int | None) -> str:
    """Per-MLBAM current MiLB state from the E7.1 game logs: newest level / org / name / bio.

    `argmax(..., official_date)` picks the most recent *game*, which is what "current level/org"
    means for a minor leaguer. `official_date` is an ISO VARCHAR (the W8a binary-timestamp cure) —
    string ordering is chronologically correct for ISO dates, so no cast is needed here, and none
    is done (INC-23: cast only where a date FUNCTION or a typed comparison is applied).
    """
    where = f"where season >= {int(season_floor)}" if season_floor else ""
    return f"""
    select cast(player_id as varchar)                          as mlbam_id,
           argmax(player_name, official_date)                  as milb_player_name,
           argmax(level_name, official_date)                   as milb_level,
           argmax(affiliate_org_name, official_date)           as milb_org,
           argmax(position_code, official_date)                as milb_position_code,
           max(birth_date)                                     as milb_birth_date,
           max(season)                                         as milb_last_season,
           min(season)                                         as milb_first_season,
           count(*)                                            as milb_game_logs
    from {src.milb_game_logs}
    {where}
    group by 1
    """


def _mlb_player_state_sql(src: XrefSources) -> str:
    """The existing MLB player master (`stg_statsapi_player_profiles`) — the join to the MLB
    player xref the AC requires. Already one row per `player_id` upstream; re-deduped anyway so a
    future upstream grain change can never multiply rows here."""
    return f"""
    select cast(player_id as varchar)      as mlbam_id,
           argmax(full_name, last_fetched_at)             as mlb_full_name,
           argmax(cast(birth_date as varchar), last_fetched_at) as mlb_birth_date,
           argmax(primary_position_code, last_fetched_at) as mlb_position_code,
           argmax(active, last_fetched_at)                as mlb_active
    from {src.mlb_player_profiles}
    where player_id is not null
    group by 1
    """


def _leaderboard_state_sql(src: XrefSources) -> str:
    """Per-MLBAM current FanGraphs-minors state — the coverage layer for players E7.1 does NOT
    ingest (E7.1 pulls sportIds 11–14 = AAA/AA/A+/A; the leaderboards also enumerate DSL and
    complex-league players, who are exactly the youngest prospects a dynasty board cares about).
    """
    return f"""
    select mlbam_id,
           argmax(fg_minor_id, cast(season as varchar) || '|' || coalesce(as_of_date, '')) as fg_minor_id,
           argmax(player_name, cast(season as varchar) || '|' || coalesce(as_of_date, ''))  as lb_player_name,
           argmax(level, cast(season as varchar) || '|' || coalesce(as_of_date, ''))        as lb_level,
           argmax(team, cast(season as varchar) || '|' || coalesce(as_of_date, ''))         as lb_team,
           argmax(age, cast(season as varchar) || '|' || coalesce(as_of_date, ''))          as lb_age,
           max(season)                                                                      as lb_last_season
    from {src.leaderboards}
    where mlbam_id is not null
    group by 1
    """


# ── The build ────────────────────────────────────────────────────────────────────────────────

def build_xref(conn, src: XrefSources, *, season_floor: int | None = None,
               enforce: bool = True) -> XrefResult:
    """Assemble `dim_player_xref` + the per-hop match-rate report.

    `enforce=False` skips the tripwire raises (report-only mode) but STILL computes every rate —
    used by `--dry-run` so an operator can see a degraded bridge before it fails a job.
    """
    conn.execute(f"create or replace temp view _board as {_board_latest_sql(src)}")
    conn.execute(f"create or replace temp view _lb_bridge as {_leaderboard_bridge_sql(src)}")
    conn.execute(f"create or replace temp view _fg_mlb as {_fg_mlb_bridge_sql(src)}")
    conn.execute(f"create or replace temp view _milb as {_milb_player_state_sql(src, season_floor)}")
    conn.execute(f"create or replace temp view _mlb as {_mlb_player_state_sql(src)}")
    conn.execute(f"create or replace temp view _lb_state as {_leaderboard_state_sql(src)}")

    _assert_unique(conn, "_lb_bridge", "fg_minor_id")
    _assert_unique(conn, "_fg_mlb", "fg_mlb_id")
    _assert_unique(conn, "_milb", "mlbam_id")
    _assert_unique(conn, "_mlb", "mlbam_id")
    _assert_unique(conn, "_lb_state", "mlbam_id")
    _assert_unique(conn, "_board", "season, fg_minor_id")

    report = _hop_report(conn, src)
    if enforce:
        _enforce_tripwires(report)

    # ── The board prospect layer, resolved to the spine ──────────────────────────────────────
    # `fg_mlb_id` = the board's `fg_player_id` ONLY when it is numeric. FanGraphs reuses that field
    # for the `sa`-prefixed minor id on un-graduated players, so an unconditional read would stamp
    # a minor id into the MLB-id column (a wrong id is worse than a null one).
    conn.execute("""
    create or replace temp view _prospect as
    select
        b.fg_minor_id,
        case when b.fg_player_id is not null and regexp_matches(b.fg_player_id, '^[0-9]+$')
             then b.fg_player_id end                                     as fg_mlb_id,
        coalesce(lbb.mlbam_id, g.mlbam_id)                               as mlbam_id,
        case when lbb.mlbam_id is not null then 'fg_leaderboard_xmlbamid'
             when g.mlbam_id  is not null then 'fg_mlb_leaderboard_playerid'
             else 'unresolved' end                                       as mlbam_match_method,
        b.player_name, b.org, b.position, b.level, b.age,
        b.fv, b.risk, b.eta, b.overall_rank, b.org_rank,
        b.fantasy_dynasty_rank, b.fantasy_redraft_rank,
        b.season      as board_season,
        b.as_of_date  as board_as_of_date,
        row_number() over (partition by b.fg_minor_id order by b.season desc) as rn
    from _board b
    left join _lb_bridge lbb on b.fg_minor_id = lbb.fg_minor_id
    left join _fg_mlb    g   on b.fg_player_id = g.fg_mlb_id
                             and regexp_matches(b.fg_player_id, '^[0-9]+$')
    """)
    conn.execute("create or replace temp view _prospect_latest as "
                 "select * exclude (rn) from _prospect where rn = 1")
    _assert_unique(conn, "_prospect_latest", "fg_minor_id")
    _assert_no_inflation(conn, "_board", "_prospect", "board → prospect resolution")

    # ── The universe: every identity any source knows about ──────────────────────────────────
    conn.execute("""
    create or replace temp view _spine as
    select mlbam_id from _milb
    union select mlbam_id from _mlb
    union select mlbam_id from _lb_state
    union select mlbam_id from _prospect_latest where mlbam_id is not null
    """)

    dim = conn.execute(f"""
    with resolved as (
        select
            s.mlbam_id                                                    as mlbam_id,
            coalesce(p.fg_minor_id, ls.fg_minor_id)                       as fg_minor_id,
            p.fg_mlb_id                                                   as fg_mlb_id,
            coalesce(m.mlb_full_name, mi.milb_player_name, ls.lb_player_name,
                     p.player_name)                                       as player_name,
            coalesce(m.mlb_birth_date, mi.milb_birth_date)                as birth_date,
            coalesce(m.mlb_position_code, mi.milb_position_code, p.position) as position_code,
            -- current level: an MLB profile outranks any minor-league observation; otherwise the
            -- newest MiLB game log, then the FanGraphs leaderboard (covers DSL/complex, which
            -- E7.1's sportIds 11–14 do not ingest), then the board's own level.
            case when m.mlbam_id is not null then 'MLB'
                 else coalesce(mi.milb_level, ls.lb_level, p.level) end   as current_level,
            coalesce(p.org, mi.milb_org, ls.lb_team)                      as org,
            coalesce(p.age, ls.lb_age)                                    as age,
            p.fv, p.risk, p.eta, p.overall_rank, p.org_rank,
            p.fantasy_dynasty_rank, p.fantasy_redraft_rank,
            p.board_season, p.board_as_of_date,
            (p.fg_minor_id is not null)                                   as is_on_prospect_board,
            (m.mlbam_id  is not null)                                     as in_mlb_player_master,
            (mi.mlbam_id is not null)                                     as in_milb_game_logs,
            (ls.mlbam_id is not null)                                     as in_fg_leaderboards,
            m.mlb_active                                                  as mlb_active,
            mi.milb_first_season, mi.milb_last_season, mi.milb_game_logs,
            ls.lb_last_season                                             as fg_last_season,
            case when p.mlbam_id is not null then p.mlbam_match_method
                 when m.mlbam_id  is not null then '{MATCH_MLB_NATIVE}'
                 when mi.mlbam_id is not null then '{MATCH_MILB_NATIVE}'
                 else '{MATCH_FG_LEADERBOARD}' end                        as mlbam_match_method
        from _spine s
        left join _milb            mi on s.mlbam_id = mi.mlbam_id
        left join _mlb             m  on s.mlbam_id = m.mlbam_id
        left join _lb_state        ls on s.mlbam_id = ls.mlbam_id
        left join _prospect_latest p  on s.mlbam_id = p.mlbam_id
    ),
    unresolved as (
        select
            cast(null as varchar) as mlbam_id, p.fg_minor_id, p.fg_mlb_id,
            p.player_name, cast(null as varchar) as birth_date, p.position as position_code,
            p.level as current_level, p.org, p.age,
            p.fv, p.risk, p.eta, p.overall_rank, p.org_rank,
            p.fantasy_dynasty_rank, p.fantasy_redraft_rank,
            p.board_season, p.board_as_of_date,
            true as is_on_prospect_board, false as in_mlb_player_master,
            false as in_milb_game_logs, false as in_fg_leaderboards,
            cast(null as boolean) as mlb_active,
            cast(null as bigint) as milb_first_season, cast(null as bigint) as milb_last_season,
            cast(null as bigint) as milb_game_logs, cast(null as bigint) as fg_last_season,
            '{MATCH_UNRESOLVED}' as mlbam_match_method
        from _prospect_latest p
        where p.mlbam_id is null
    ),
    combined as (select * from resolved union all select * from unresolved)
    select
        coalesce(mlbam_id, 'fg:' || fg_minor_id)  as xref_key,
        *,
        case when mlbam_match_method = '{MATCH_UNRESOLVED}' then 'none' else 'high' end
                                                  as mlbam_match_confidence,
        '{XREF_VERSION}'                          as xref_version
    from combined
    order by mlbam_id nulls last
    """).df()

    _assert_unique_frame(dim, "xref_key")
    report["dim_rows"] = int(len(dim))
    report["dim_resolved_rows"] = int(dim["mlbam_id"].notna().sum())
    report["dim_unresolved_rows"] = int(dim["mlbam_id"].isna().sum())
    report["dim_prospect_rows"] = int(dim["is_on_prospect_board"].sum())
    report["match_method_counts"] = {
        str(k): int(v) for k, v in dim["mlbam_match_method"].value_counts().items()
    }
    return XrefResult(dim=dim, report=report)


# ── Per-hop match-rate report (the AC deliverable) ───────────────────────────────────────────

def _hop_report(conn, src: XrefSources) -> dict[str, Any]:
    """Match-count EVERY candidate join key on the relations the build actually reads.

    This is the P1.2b discipline made mechanical: a plausible-but-wrong id key produces a
    green-everywhere near-empty result, and the ONLY way to catch it is to count matches on the
    real data. Rates are reported per hop AND per board season so a regression is attributable.
    """
    rep: dict[str, Any] = {"xref_version": XREF_VERSION}

    rep["board_seasons"] = conn.execute("""
        select season, max(as_of_date) as as_of_date, count(*) as board_ids
        from _board group by 1 order by 1
    """).df().to_dict("records")

    # HOP 1 — board.fg_minor_id → fg_leaderboards.fg_minor_id
    rep["hop1_board_to_leaderboard"] = conn.execute("""
        select b.season,
               count(*)                                              as board_ids,
               count(l.fg_minor_id)                                  as matched,
               round(count(l.fg_minor_id) * 1.0 / count(*), 4)       as rate
        from _board b left join _lb_bridge l on b.fg_minor_id = l.fg_minor_id
        group by 1 order by 1
    """).df().to_dict("records")

    # HOP 2 — the xMLBAMID key itself: populated? shaped like an MLBAM id? in the spine?
    rep["hop2_leaderboard_mlbam"] = conn.execute(f"""
        select count(*)                                                        as lb_rows,
               count(mlbam_id)                                                 as populated,
               round(count(mlbam_id) * 1.0 / nullif(count(*), 0), 4)           as population_rate,
               round(sum(case when regexp_matches(mlbam_id, '^[0-9]+$') then 1 else 0 end) * 1.0
                     / nullif(count(mlbam_id), 0), 4)                          as numeric_rate
        from {src.leaderboards}
    """).df().to_dict("records")[0]

    # HOP 2b — does that MLBAM id land in a spine source? A miss here is a COVERAGE statement
    # (E7.1 ingests sportIds 11–14 only, so DSL/complex players are absent by construction), NOT
    # a bad key — reported per level so the two can never be confused.
    rep["hop2b_mlbam_in_spine_by_level"] = conn.execute(f"""
        with l as (select distinct level, mlbam_id from {src.leaderboards} where mlbam_id is not null),
             s as (select mlbam_id from _milb union select mlbam_id from _mlb)
        select coalesce(l.level, '(null)')                        as level,
               count(*)                                           as lb_ids,
               count(s.mlbam_id)                                  as matched,
               round(count(s.mlbam_id) * 1.0 / count(*), 4)       as rate
        from l left join s on l.mlbam_id = s.mlbam_id
        group by 1 having count(*) >= 100 order by 2 desc
    """).df().to_dict("records")

    # The graduate leg, standalone.
    rep["hop3_board_fg_mlb_id_to_mlbam"] = conn.execute("""
        with b as (select distinct fg_player_id from _board
                   where fg_player_id is not null and regexp_matches(fg_player_id, '^[0-9]+$'))
        select count(*)                                            as numeric_board_ids,
               count(g.mlbam_id)                                   as matched,
               round(count(g.mlbam_id) * 1.0 / nullif(count(*), 0), 4) as rate
        from b left join _fg_mlb g on b.fg_player_id = g.fg_mlb_id
    """).df().to_dict("records")[0]

    # End-to-end, on the CURRENT board snapshot — the number E8.0 and E7.8 actually depend on.
    rep["chain_current_board"] = conn.execute("""
        with cur as (select * from _board where season = (select max(season) from _board)),
             r as (
                select cur.fg_minor_id,
                       l.mlbam_id                                   as via_lb,
                       case when l.mlbam_id is null then g.mlbam_id end as via_grad
                from cur
                left join _lb_bridge l on cur.fg_minor_id = l.fg_minor_id
                left join _fg_mlb    g on cur.fg_player_id = g.fg_mlb_id
                                       and regexp_matches(cur.fg_player_id, '^[0-9]+$')
             )
        select count(*)                                                     as board_ids,
               count(via_lb)                                                as via_leaderboard,
               count(via_grad)                                              as via_graduate_leg,
               count(coalesce(via_lb, via_grad))                            as resolved,
               round(count(coalesce(via_lb, via_grad)) * 1.0 / count(*), 4) as rate
        from r
    """).df().to_dict("records")[0]

    rep["unresolved_current_board"] = conn.execute("""
        with cur as (select * from _board where season = (select max(season) from _board))
        select cur.fg_minor_id, cur.player_name, cur.org, cur.level, cur.fv, cur.eta
        from cur
        left join _lb_bridge l on cur.fg_minor_id = l.fg_minor_id
        left join _fg_mlb    g on cur.fg_player_id = g.fg_mlb_id
                               and regexp_matches(cur.fg_player_id, '^[0-9]+$')
        where l.mlbam_id is null and g.mlbam_id is null
        order by cur.fv desc nulls last
    """).df().to_dict("records")
    return rep


def _enforce_tripwires(rep: dict[str, Any]) -> None:
    hop2 = rep["hop2_leaderboard_mlbam"]
    if (hop2["population_rate"] or 0) < MIN_LEADERBOARD_MLBAM_POPULATION:
        raise XrefValidationError(
            f"DEAD BRIDGE (hop 2): fg_leaderboards.mlbam_id populated on only "
            f"{hop2['population_rate']:.1%} of rows (floor {MIN_LEADERBOARD_MLBAM_POPULATION:.0%}). "
            f"FanGraphs likely renamed `xMLBAMID` — re-probe the live leaderboard "
            f"(`ingest_fangraphs_milb_leaderboards_to_s3.py --probe`) before trusting any join."
        )
    if (hop2["numeric_rate"] or 0) < MIN_LEADERBOARD_MLBAM_NUMERIC:
        raise XrefValidationError(
            f"DEAD BRIDGE (hop 2): only {hop2['numeric_rate']:.1%} of fg_leaderboards.mlbam_id "
            f"values are all-digits — an MLBAM id always is. The alias is resolving to the WRONG "
            f"field (the P1.2b class: a plausible-but-wrong key)."
        )

    chain = rep["chain_current_board"]
    hop1_current = next(
        (r for r in rep["hop1_board_to_leaderboard"]
         if r["season"] == max(x["season"] for x in rep["hop1_board_to_leaderboard"])), None
    )
    if hop1_current and (hop1_current["rate"] or 0) < MIN_BOARD_TO_LEADERBOARD_RATE:
        raise XrefValidationError(
            f"DEAD BRIDGE (hop 1): board→leaderboard matched only {hop1_current['rate']:.1%} of "
            f"{hop1_current['board_ids']} current-season board ids (floor "
            f"{MIN_BOARD_TO_LEADERBOARD_RATE:.0%}). Either `minorMasterId` changed shape or the "
            f"board was read with a parquet GLOB instead of the Delta relation (landmine 2 — a "
            f"glob unions tombstoned generations and drags this rate to ~84%)."
        )
    if (chain["rate"] or 0) < MIN_BOARD_RESOLUTION_RATE:
        raise XrefValidationError(
            f"DEAD BRIDGE (end-to-end): only {chain['rate']:.1%} of the current board resolves to "
            f"an MLBAM id (floor {MIN_BOARD_RESOLUTION_RATE:.0%}). E8.0's board join and E7.8's "
            f"prospect→realized-MLB link both route through this."
        )


# ── Invariants ───────────────────────────────────────────────────────────────────────────────

def _assert_unique(conn, relation: str, key: str) -> None:
    """A join key that is not unique silently MULTIPLIES rows downstream. Checked before use, not
    hoped for (the NCAAF-P0.3 anti-cartesian discipline)."""
    dupes = conn.execute(
        f"select count(*) from (select {key} from {relation} group by {key} having count(*) > 1)"
    ).fetchone()[0]
    if dupes:
        raise XrefValidationError(
            f"{relation} has {dupes} duplicate values of ({key}) — joining on it would inflate "
            f"the xref. Fix the dedupe upstream; never join through a non-unique key."
        )


def _assert_no_inflation(conn, before: str, after: str, label: str) -> None:
    n_before = conn.execute(f"select count(*) from {before}").fetchone()[0]
    n_after = conn.execute(f"select count(*) from {after}").fetchone()[0]
    if n_after > n_before:
        raise XrefValidationError(
            f"{label}: row count grew {n_before} → {n_after}. A join multiplied rows "
            f"(cartesian); the xref is not trustworthy."
        )


def _assert_unique_frame(df, key: str) -> None:
    dupes = int(df[key].duplicated().sum())
    if dupes:
        raise XrefValidationError(
            f"dim_player_xref has {dupes} duplicate {key} values — the dimension must be one row "
            f"per person."
        )


# ── Report rendering ─────────────────────────────────────────────────────────────────────────

def format_report(rep: dict[str, Any]) -> str:
    """The human-readable per-key match-rate block the AC asks for."""
    lines = ["", "──────── E7.4 XREF MATCH-RATE REPORT (measured on the REAL lake) ────────"]
    lines.append("HOP 1  board.fg_minor_id → fg_leaderboards.fg_minor_id")
    for r in rep["hop1_board_to_leaderboard"]:
        lines.append(f"    season {r['season']}:  {r['matched']:>6}/{r['board_ids']:<6} "
                     f"= {r['rate']:.1%}")
    h2 = rep["hop2_leaderboard_mlbam"]
    lines.append("HOP 2  fg_leaderboards.mlbam_id (xMLBAMID) → the MLBAM spine")
    lines.append(f"    populated: {h2['populated']:,}/{h2['lb_rows']:,} = "
                 f"{h2['population_rate']:.1%}   numeric-shaped: {h2['numeric_rate']:.1%}")
    lines.append("    in a spine source, by level (a miss = E7.1 level COVERAGE, not a bad key):")
    for r in rep["hop2b_mlbam_in_spine_by_level"]:
        lines.append(f"        {r['level']:<12} {r['matched']:>6}/{r['lb_ids']:<6} = {r['rate']:.1%}")
    h3 = rep["hop3_board_fg_mlb_id_to_mlbam"]
    lines.append("HOP 3  board.fg_player_id (numeric ⇒ fg_mlb_id) → MLB FanGraphs $.xMLBAMID")
    lines.append(f"    {h3['matched']}/{h3['numeric_board_ids']} = "
                 f"{(h3['rate'] or 0):.1%}   (the graduate leg)")
    c = rep["chain_current_board"]
    lines.append("CHAIN  current board snapshot → MLBAM  ⭐ the join E8.0 + E7.8 depend on")
    lines.append(f"    {c['resolved']}/{c['board_ids']} = {c['rate']:.1%}  "
                 f"(via leaderboard {c['via_leaderboard']}, via graduate leg {c['via_graduate_leg']})")
    unres = rep.get("unresolved_current_board", [])
    lines.append(f"    UNRESOLVED: {len(unres)} — emitted with mlbam_id NULL, "
                 f"mlbam_match_method='unresolved' (no fuzzy match: see landmine 4)")
    for r in unres[:10]:
        lines.append(f"        {r['player_name']:<26} {str(r['org']):<5} FV "
                     f"{r['fv']}  ETA {r['eta']}")
    if "dim_rows" in rep:
        lines.append(f"DIM    {rep['dim_rows']:,} rows  "
                     f"({rep['dim_resolved_rows']:,} resolved, "
                     f"{rep['dim_unresolved_rows']:,} unresolved, "
                     f"{rep['dim_prospect_rows']:,} on the prospect board)")
        lines.append(f"    provenance: {rep['match_method_counts']}")
    lines.append("─────────────────────────────────────────────────────────────────────────")
    return "\n".join(lines)
