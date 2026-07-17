"""xref.py  (NCAAF-P0.3 — the college↔NFL player-ID crosswalk builder)
=======================================================================
The spine of the NFL feeder (college production → NFL rookie projections; the MLB Edge-E7
MiLB→MLB analog). Builds the crosswalk that keys a CFBD college athlete to an NFL `gsis_id`,
so a later story (NCAAF-P1A) can attach college production to an NFL outcome.

⭐ THE KEY IS THE DRAFT SLOT, NOT AN ID (ncaaf_data_inventory.md §4 — the load-bearing P0.1
finding). There is NO shared player ID between CFBD and nflverse:
  • CFBD `collegeAthleteId` = an ESPN numeric (4431611)
  • nflverse `cfb_player_id` = a sports-reference SLUG (caleb-williams-3)
  • CFBD `nflAthleteId` ∩ nflverse `espn_id` = 0 of 257.
But the DRAFT SLOT `(year, overall pick)` is a clean deterministic key:
  CFBD /draft/picks (year, overall)  ⇄  nflverse draft_picks (season, pick)
resolving 99.7% of 2015–25 picks to a `gsis_id` (validated independently at 92–100% surname
agreement). Combine measurables attach nflverse-INTERNALLY on the `cfb_player_id` slug.

WHY DuckDB-over-Delta (a Python builder, not a dbt model):
  Mirrors MLB's `run_w1_lakehouse` — a DuckDB build over the S3 Delta lake, landing a
  versioned Delta MART. The same code runs against the real S3 lake (the box runtime gate)
  AND against local Delta fixtures (the offline fast-gate test) — one copy of the join SQL,
  provable without a warehouse. The fuzzy-UDFA residual + the anti-cartesian row-count
  assertions live far more safely here (tested, asserted) than in un-runnable dbt SQL.

  ⚠️ SQL joins are IMMUNE to the pandas NaN-to-NaN cartesian trap (P0.1 §1: coercing the
  slug with `to_numeric` → all-NaN → a bogus ~100% match). In SQL `NULL = NULL` is NULL, so
  null keys never match. We STILL drop null keys explicitly AND assert row counts after every
  join (a join must never MULTIPLY rows) so the guarantee is enforced, not assumed.

MATCH CONFIDENCE is source-stamped, leakage-safe:
  • deterministic_slot (high)  — the 99.7% spine; match_score = 1.0.
  • fuzzy_udfa (medium/low)    — undrafted players have NO draft slot ⇒ genuinely need a
    fuzzy `name + school + position` match to a CFBD roster row; match_score = Jaro-Winkler.
  NFL OUTCOME columns (`target_*`) are POST-draft — they are the P1A TARGET, NOT features;
  prefixed `target_` so a downstream feature build can't mistake them for inputs.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from .name_norm import norm_full_sql, norm_last_sql

log = logging.getLogger(__name__)

SPORT = "ncaaf"
XREF_TABLE = "xref_college_nfl_players"   # the Delta mart name (marts/ tier)
XREF_VERSION = "p0.3-v1"

# The draft-class window the slot spine covers with player-advanced college data behind it
# (ncaaf_data_inventory.md §2.7 floor = 2014; §4.2 validated 2015–2025). Draft class 2015+
# so a drafted player's final college seasons fall in the 2014+ advanced-data window.
DEFAULT_DRAFT_SEASONS = list(range(2015, 2026))

# A fuzzy UDFA match below this Jaro-Winkler on the normalised full name is not trustworthy
# even with a school + surname block — dropped rather than asserted (honest: no match beats a
# wrong match). Conservative default; the report surfaces the score distribution to re-tune.
UDFA_MIN_SCORE = 0.92


class XrefValidationError(RuntimeError):
    """Raised when a build invariant fails (cartesian inflation, duplicate NFL key, or the
    slot baseline collapsing) — a HARD stop, never a silent wrong xref (the P0.1 discipline)."""


@dataclass
class XrefResult:
    mart: Any                       # pandas DataFrame — the xref mart (one row / matched player)
    report: dict[str, Any] = field(default_factory=dict)


# ── lake resolvers (parity: S3 in prod, local Delta in the fast-gate test) ───────────────
def s3_lake(source: str, *, bucket: str | None = None, tier: str = "raw") -> str:
    """A `delta_scan('s3://…')` FROM-expression for a raw lake source (the box path)."""
    from ..ingest import s3io

    uri = s3io.table_uri(SPORT, source, bucket=bucket or s3io.DEFAULT_BUCKET, tier=tier)
    return f"delta_scan('{uri}')"


def local_lake(root: str) -> Callable[[str], str]:
    """A resolver over a LOCAL-FS Delta tree (the offline fixture / laptop dev path)."""
    from ..ingest import s3io

    def resolve(source: str, *, tier: str = "raw") -> str:
        return f"delta_scan('{s3io.local_table_uri(root, SPORT, source, tier=tier)}')"

    return resolve


def _connect_s3():
    """A DuckDB connection wired to read the S3 Delta lake via the credential chain (the
    AKID-safe path — no inline keys). Mirrors query_lake._connect."""
    import duckdb

    from ..ingest import s3io

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute("INSTALL delta; LOAD delta")
    con.execute(
        f"CREATE OR REPLACE SECRET sports_s3 "
        f"(TYPE S3, PROVIDER credential_chain, REGION '{s3io.DEFAULT_REGION}')"
    )
    return con


def _local_con():
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    return con


# ── SQL fragments ───────────────────────────────────────────────────────────────────────
def _j(expr_col: str, key: str) -> str:
    """json_extract_string(raw_json, '$.<key>') — the raw tier lands each record as a JSON
    string (s3io.records_to_arrow), flattened here (the MLB W3pre VARIANT→staging pattern)."""
    return f"json_extract_string({expr_col}, '$.{key}')"


def _num(key: str) -> str:
    """A NaN-safe numeric cast of a raw_json field to DOUBLE. nflverse floats land as NaN when
    missing (json.dumps writes `NaN`), and `try_cast('NaN' as double)` yields a NON-null NaN
    double — so a naive cast makes a `is not null` flag over-count (has_forty read 81.8% when
    only ~65.7% truly have a time). Collapse NaN → NULL so both the value and its presence flag
    are honest."""
    e = f"try_cast({_j('raw_json', key)} as double)"
    return f"case when isnan({e}) then null else {e} end"


def _season_list_sql(seasons) -> str:
    return ", ".join(str(int(s)) for s in seasons)


# ── stage builders (each registers a temp view/table on `con`) ───────────────────────────
def _stage_cfbd_picks(con, lake, seasons) -> None:
    """CFBD /draft/picks → the college side of the slot key, deduped 1-row-per-slot."""
    con.execute(f"""
        create or replace temp view _cfbd_picks as
        with base as (
            select
                try_cast({_j('raw_json','year')} as int)     as draft_year,
                try_cast({_j('raw_json','overall')} as int)  as overall_pick,
                try_cast({_j('raw_json','round')} as int)    as cfbd_round,
                try_cast({_j('raw_json','collegeAthleteId')} as bigint) as college_athlete_id,
                {_j('raw_json','name')}            as cfbd_name,
                {_j('raw_json','position')}        as cfbd_position,
                {_j('raw_json','collegeTeam')}     as cfbd_college_team,
                {_j('raw_json','collegeConference')} as cfbd_college_conf,
                {norm_last_sql(_j('raw_json','name'))} as cfbd_norm_last
            from {lake('cfbd_draft_picks')}
            where try_cast({_j('raw_json','year')} as int) in ({_season_list_sql(seasons)})
              and try_cast({_j('raw_json','overall')} as int) is not null
        )
        -- one row per draft slot (guards a rare supplemental/duplicate pick); prefer a row
        -- that actually carries a collegeAthleteId (the bridge back to college production).
        select * from base
        qualify row_number() over (
            partition by draft_year, overall_pick
            order by (college_athlete_id is null), cfbd_name
        ) = 1
    """)


def _stage_nfl_picks(con, lake, seasons) -> None:
    """nflverse draft_picks → the NFL side of the slot key + the P1A TARGET outcomes,
    deduped 1-row-per-slot. `pick` IS the overall pick (P0.1 §4.2, round 2 starts at 33)."""
    con.execute(f"""
        create or replace temp view _nfl_picks as
        with base as (
            select
                try_cast({_j('raw_json','season')} as int) as draft_year,
                try_cast({_j('raw_json','pick')} as int)   as overall_pick,
                try_cast({_j('raw_json','round')} as int)  as draft_round,
                {_j('raw_json','gsis_id')}         as gsis_id,
                {_j('raw_json','pfr_player_id')}   as pfr_player_id,
                {_j('raw_json','cfb_player_id')}   as cfb_player_id,
                {_j('raw_json','pfr_player_name')} as nfl_name,
                {_j('raw_json','position')}        as nfl_position,
                {_j('raw_json','college')}         as nfl_college,
                {norm_last_sql(_j('raw_json','pfr_player_name'))} as nfl_norm_last,
                -- the feeder TARGET (ncaaf_data_inventory.md §4.3) — POST-draft, leakage-unsafe
                -- as a feature; prefixed target_ so P1A can't feed it in.
                try_cast({_j('raw_json','car_av')} as double)          as target_car_av,
                try_cast({_j('raw_json','w_av')} as double)            as target_w_av,
                try_cast({_j('raw_json','dr_av')} as double)           as target_dr_av,
                try_cast({_j('raw_json','games')} as double)           as target_games,
                try_cast({_j('raw_json','seasons_started')} as double) as target_seasons_started,
                try_cast({_j('raw_json','probowls')} as double)        as target_probowls,
                try_cast({_j('raw_json','allpro')} as double)          as target_allpro,
                ({_j('raw_json','hof')} in ('true','True','1'))        as target_hof
            from {lake('nflverse_draft_picks')}
            where try_cast({_j('raw_json','season')} as int) in ({_season_list_sql(seasons)})
              and try_cast({_j('raw_json','pick')} as int) is not null
        )
        select * from base
        qualify row_number() over (
            partition by draft_year, overall_pick
            order by (gsis_id is null), nfl_name
        ) = 1
    """)


def _stage_combine(con, lake) -> None:
    """nflverse combine → measurables, deduped 1-row-per-`cfb_id` slug (the nflverse-internal
    attach key). Null slugs dropped (the NaN-to-NaN trap — the join must never multiply)."""
    con.execute(f"""
        create or replace temp view _combine as
        with base as (
            select
                {_j('raw_json','cfb_id')}   as cfb_id,
                {_num('forty')}             as forty,
                {_num('vertical')}          as vertical,
                {_num('bench')}             as bench,
                {_num('broad_jump')}        as broad_jump,
                {_num('cone')}              as cone,
                {_num('shuttle')}           as shuttle,
                {_j('raw_json','ht')}       as combine_ht,
                {_num('wt')}                as combine_wt
            from {lake('nflverse_combine')}
            where {_j('raw_json','cfb_id')} is not null
              and length({_j('raw_json','cfb_id')}) > 0
        )
        select * from base
        qualify row_number() over (partition by cfb_id order by (forty is null)) = 1
    """)


def _build_slot_xref(con) -> int:
    """The deterministic slot join → `_slot_xref` temp table (materialised so its row count
    is a stable assertion target). INNER join on the unique (year, overall) key, both sides
    already 1-row-per-slot ⇒ result is 1-row-per-matched-slot (no multiplication)."""
    con.execute("""
        create or replace temp table _slot_xref as
        select
            n.gsis_id,
            n.pfr_player_id,
            n.cfb_player_id,
            c.college_athlete_id,
            coalesce(n.nfl_name, c.cfbd_name)      as player_name,
            coalesce(n.nfl_position, c.cfbd_position) as position,
            coalesce(c.cfbd_college_team, n.nfl_college) as college,
            c.cfbd_college_conf                    as college_conference,
            n.draft_year,
            n.overall_pick                         as draft_overall,
            n.draft_round,
            'deterministic_slot'                   as match_method,
            'high'                                 as match_confidence,
            1.0                                    as match_score,
            (c.cfbd_norm_last = n.nfl_norm_last)   as surname_agree,
            false                                  as is_udfa,
            n.target_car_av, n.target_w_av, n.target_dr_av, n.target_games,
            n.target_seasons_started, n.target_probowls, n.target_allpro, n.target_hof
        from _nfl_picks n
        join _cfbd_picks c
          on n.draft_year = c.draft_year
         and n.overall_pick = c.overall_pick
    """)
    return con.execute("select count(*) from _slot_xref").fetchone()[0]


def _attach_combine(con) -> None:
    """LEFT-join combine measurables onto the slot xref via the cfb_player_id slug. LEFT so a
    slot match is never dropped for lacking a combine row; the null-key drop + the 1-per-slug
    dedup keep it a strict 1:1 attach (asserted by the caller)."""
    con.execute("""
        create or replace temp table _slot_xref_meas as
        select s.*,
               k.forty, k.vertical, k.bench, k.broad_jump, k.cone, k.shuttle,
               k.combine_ht, k.combine_wt,
               (k.cfb_id is not null)             as has_combine,
               (k.forty is not null)              as has_forty
        from _slot_xref s
        left join _combine k
          on s.cfb_player_id is not null
         and s.cfb_player_id = k.cfb_id
    """)


def _stage_udfa(con, lake, seasons, min_score: float) -> int:
    """The UDFA residual: undrafted NFL players have NO draft slot ⇒ a genuine fuzzy match of
    `name + school + position` to a CFBD roster row (the only way to recover a
    college_athlete_id for them). Blocked on (normalised surname + normalised school +
    position) to keep the candidate set tiny, ranked by Jaro-Winkler on the full name, best
    per gsis_id above `min_score`. Lower confidence, source-stamped `fuzzy_udfa`.

    Leakage-safe: name/school/position/entry_year are all pre-NFL facts. No `target_*` — an
    undrafted player has no draft_picks outcome row (that outcome would come from a different
    nflverse table; out of P0.3 scope), so UDFA target columns are NULL by construction.

    Returns the count of UDFA matches. Depends on `_slot_xref` (to exclude already-matched
    gsis_ids). If nflverse_players lacks college_name/draft_number (verify on first box run —
    P0.1 discipline), the block yields 0 and the slot spine still stands.
    """
    entry_lo = min(seasons)          # college rosters span a few years before the entry year
    # A player entering the NFL in year Y played college roughly [Y-6, Y-1]; bound the roster
    # scan so a huge multi-season roster join stays cheap (blocking already prunes hard).
    con.execute(f"""
        create or replace temp view _nfl_udfa as
        select
            {_j('raw_json','gsis_id')}      as gsis_id,
            {_j('raw_json','display_name')} as nfl_name,
            {_j('raw_json','position')}     as nfl_position,
            {_j('raw_json','college_name')} as nfl_college,
            try_cast({_j('raw_json','rookie_season')} as int) as rookie_season,
            {norm_full_sql(_j('raw_json','display_name'))} as nfl_norm_full,
            {norm_last_sql(_j('raw_json','display_name'))} as nfl_norm_last,
            {norm_full_sql(_j('raw_json','college_name'))} as nfl_norm_school
        from {lake('nflverse_players')}
        where {_j('raw_json','gsis_id')} is not null
          -- undrafted = no draft pick AND no draft round (nflverse leaves both null for a UDFA).
          -- ⚠️ real nflverse_players columns are draft_pick/draft_round/rookie_season — NOT the
          -- draft_number/entry_year the P0.1 notes implied (verified on the box 2026-07-17).
          and {_j('raw_json','draft_pick')} is null
          and {_j('raw_json','draft_round')} is null
          and {_j('raw_json','college_name')} is not null
          and try_cast({_j('raw_json','rookie_season')} as int) >= {int(entry_lo)}
          and {_j('raw_json','gsis_id')} not in (select gsis_id from _slot_xref where gsis_id is not null)
    """)
    con.execute(f"""
        create or replace temp view _roster as
        select
            try_cast({_j('raw_json','id')} as bigint) as college_athlete_id,
            trim(concat_ws(' ', {_j('raw_json','firstName')}, {_j('raw_json','lastName')})) as roster_name,
            {_j('raw_json','position')} as roster_position,
            {_j('raw_json','team')}     as roster_team,
            season                      as roster_season,
            {norm_full_sql("concat_ws(' ', " + _j('raw_json','firstName') + ", " + _j('raw_json','lastName') + ")")} as r_norm_full,
            {norm_last_sql("concat_ws(' ', " + _j('raw_json','firstName') + ", " + _j('raw_json','lastName') + ")")} as r_norm_last,
            {norm_full_sql(_j('raw_json','team'))} as r_norm_school
        from {lake('roster')}
        where try_cast({_j('raw_json','id')} as bigint) is not null
    """)
    # Block on (surname + school + position) → rank by Jaro-Winkler on the full name.
    con.execute(f"""
        create or replace temp table _udfa_xref as
        with cand as (
            select
                u.gsis_id, u.nfl_name, u.nfl_position, u.nfl_college, u.rookie_season,
                r.college_athlete_id, r.roster_team, r.roster_season,
                jaro_winkler_similarity(u.nfl_norm_full, r.r_norm_full) as score
            from _nfl_udfa u
            join _roster r
              on u.nfl_norm_last = r.r_norm_last
             and u.nfl_norm_school = r.r_norm_school
             and lower(u.nfl_position) = lower(r.roster_position)
        ),
        best as (
            select *
            from cand
            where score >= {float(min_score)}
            qualify row_number() over (partition by gsis_id order by score desc, roster_season desc) = 1
        )
        select
            gsis_id,
            cast(null as varchar)  as pfr_player_id,
            cast(null as varchar)  as cfb_player_id,
            college_athlete_id,
            nfl_name               as player_name,
            nfl_position           as position,
            roster_team            as college,
            cast(null as varchar)  as college_conference,
            cast(null as int)      as draft_year,     -- a UDFA has no draft slot (rookie_season ≠ draft year)
            cast(null as int)      as draft_overall,
            cast(null as int)      as draft_round,
            'fuzzy_udfa'           as match_method,
            case when score >= 0.97 then 'medium' else 'low' end as match_confidence,
            score                  as match_score,
            true                   as surname_agree,   -- surname is the block key ⇒ agrees by construction
            true                   as is_udfa,
            cast(null as double) as target_car_av, cast(null as double) as target_w_av,
            cast(null as double) as target_dr_av, cast(null as double) as target_games,
            cast(null as double) as target_seasons_started, cast(null as double) as target_probowls,
            cast(null as double) as target_allpro, cast(null as boolean) as target_hof,
            -- combine measurables: not attached on the UDFA path (no cfb_player_id slug)
            cast(null as double) as forty, cast(null as double) as vertical, cast(null as double) as bench,
            cast(null as double) as broad_jump, cast(null as double) as cone, cast(null as double) as shuttle,
            cast(null as varchar) as combine_ht, cast(null as double) as combine_wt,
            false as has_combine, false as has_forty
        from best
    """)
    return con.execute("select count(*) from _udfa_xref").fetchone()[0]


# ── the public builder ──────────────────────────────────────────────────────────────────
def build_xref(
    lake: Callable[[str], str],
    *,
    con=None,
    draft_seasons=None,
    include_udfa: bool = True,
    udfa_min_score: float = UDFA_MIN_SCORE,
    built_at: str | None = None,
) -> XrefResult:
    """Build the college↔NFL xref mart from the raw Delta lake.

    `lake(source)` → a DuckDB FROM-expression for a raw source (use `s3_lake` on the box or
    `local_lake(root)` offline). Returns an `XrefResult` (the mart DataFrame + a validation
    report). RAISES `XrefValidationError` on any anti-cartesian / duplicate-key / collapsed-
    baseline invariant so a wrong xref can never be silently returned.
    """
    seasons = sorted(int(s) for s in (draft_seasons or DEFAULT_DRAFT_SEASONS))
    if con is None:
        con = _local_con()
    report: dict[str, Any] = {"draft_seasons": seasons, "xref_version": XREF_VERSION}

    # ---- stage the sides + the deterministic slot join ----
    _stage_cfbd_picks(con, lake, seasons)
    _stage_nfl_picks(con, lake, seasons)
    _stage_combine(con, lake)

    n_cfbd = con.execute("select count(*) from _cfbd_picks").fetchone()[0]
    n_nfl = con.execute("select count(*) from _nfl_picks").fetchone()[0]
    n_slot = _build_slot_xref(con)

    # anti-cartesian: an inner join on a UNIQUE key both sides can never exceed either side.
    if n_slot > min(n_cfbd, n_nfl):
        raise XrefValidationError(
            f"slot join produced {n_slot} rows > min(cfbd={n_cfbd}, nfl={n_nfl}) — CARTESIAN "
            f"inflation (a dedup on (year, overall) failed). Refusing to emit a bogus xref."
        )
    dup_slot = con.execute(
        "select count(*) from (select gsis_id from _slot_xref where gsis_id is not null "
        "group by gsis_id having count(*) > 1)").fetchone()[0]
    if dup_slot:
        raise XrefValidationError(f"{dup_slot} gsis_id(s) appear >1× in the slot xref — key not 1:1.")

    # ---- attach combine (must be a strict 1:1 LEFT join — never multiply) ----
    _attach_combine(con)
    n_meas = con.execute("select count(*) from _slot_xref_meas").fetchone()[0]
    if n_meas != n_slot:
        raise XrefValidationError(
            f"combine attach changed the row count ({n_slot} → {n_meas}) — the cfb_id slug "
            f"join multiplied rows (the NaN-to-NaN trap in SQL dress). Dedup _combine on cfb_id."
        )

    # ---- the UDFA fuzzy residual ----
    n_udfa = 0
    if include_udfa:
        try:
            n_udfa = _stage_udfa(con, lake, seasons, udfa_min_score)
        except Exception as exc:  # noqa: BLE001 — UDFA is a residual; its failure never sinks the spine
            log.warning("ALERT UDFA fuzzy stage skipped (%s: %s) — slot spine unaffected",
                        type(exc).__name__, str(exc)[:160])
            report["udfa_error"] = f"{type(exc).__name__}: {exc}"

    stamp = built_at or _now_iso()
    union_udfa = "union all by name select * from _udfa_xref" if n_udfa else ""
    mart = con.execute(f"""
        select
            'ncaaf' as sport,
            x.*,
            '{XREF_VERSION}' as xref_version,
            '{stamp}'        as built_at
        from (
            select * from _slot_xref_meas
            {union_udfa}
        ) x
        order by is_udfa, draft_year, draft_overall, player_name
    """).df()

    # ---- final invariants over the emitted mart ----
    if mart["gsis_id"].notna().any():
        dup = mart.loc[mart["gsis_id"].notna(), "gsis_id"].duplicated().sum()
        if dup:
            raise XrefValidationError(f"{dup} duplicate gsis_id in the final xref — not 1-row-per-NFL-player.")

    # ---- the report (per-class slot baseline; the 99.7% reproduction) ----
    per_class = con.execute("""
        select c.draft_year as season,
               count(*)                               as cfbd_picks,
               count(s.gsis_id)                       as matched,
               round(100.0 * count(s.gsis_id) / count(*), 1) as match_pct
        from _cfbd_picks c
        left join _slot_xref s
          on c.draft_year = s.draft_year and c.college_athlete_id = s.college_athlete_id
        group by 1 order by 1
    """).df()
    slot_matched = int(per_class["matched"].sum())
    slot_total = int(per_class["cfbd_picks"].sum())
    report.update({
        "cfbd_picks_deduped": int(n_cfbd),
        "nfl_picks_deduped": int(n_nfl),
        "slot_matched": slot_matched,
        "slot_total": slot_total,
        "slot_match_pct": round(100.0 * slot_matched / slot_total, 2) if slot_total else 0.0,
        "combine_attached": int(con.execute(
            "select count(*) from _slot_xref_meas where has_combine").fetchone()[0]),
        "has_forty": int(con.execute(
            "select count(*) from _slot_xref_meas where has_forty").fetchone()[0]),
        "surname_agree_pct": round(100.0 * con.execute(
            "select avg(case when surname_agree then 1 else 0 end) from _slot_xref").fetchone()[0], 2)
            if n_slot else 0.0,
        "udfa_matched": int(n_udfa),
        "total_rows": int(len(mart)),
        "per_class": per_class.to_dict("records"),
    })
    log.info("xref built: %d slot + %d UDFA = %d rows; slot baseline %.2f%% (%d/%d), "
             "combine %d, surname-agree %.1f%%",
             n_slot, n_udfa, len(mart), report["slot_match_pct"], slot_matched, slot_total,
             report["combine_attached"], report["surname_agree_pct"])
    return XrefResult(mart=mart, report=report)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def write_xref_to_delta(
    result: XrefResult,
    *,
    bucket: str | None = None,
    local_root: str | None = None,
) -> int:
    """Land the xref mart as a versioned Delta table under the `marts/` tier
    (`ncaaf/marts/xref_college_nfl_players`). Season-partitionless (one logical crosswalk);
    written as a single `season=0` partition so it reuses the s3io Delta writer + its AKID-safe
    auth. Overwrites idempotently (the whole xref is rebuilt each run)."""
    from ..ingest import s3io

    df = result.mart
    n = s3io.write_dataframe(
        df.assign(season=0), sport=SPORT, source=XREF_TABLE, season=0,
        bucket=bucket or s3io.DEFAULT_BUCKET, local_root=local_root, tier="marts",
    )
    return n


def _cli() -> None:
    import argparse
    import json

    p = argparse.ArgumentParser(description="Build the NCAAF college↔NFL player-ID xref mart.")
    p.add_argument("--draft-seasons", help="comma list or A-B range (default 2015-2025)")
    p.add_argument("--local-root", help="read+write a LOCAL Delta tree instead of S3 (offline dev)")
    p.add_argument("--no-udfa", action="store_true", help="skip the fuzzy UDFA residual (slot spine only)")
    p.add_argument("--udfa-min-score", type=float, default=UDFA_MIN_SCORE)
    p.add_argument("--write", action="store_true", help="land the mart as Delta (else just report)")
    p.add_argument("--bucket")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seasons = _parse_seasons(args.draft_seasons) if args.draft_seasons else None
    if args.local_root:
        con = _local_con()
        lake = local_lake(args.local_root)
    else:
        con = _connect_s3()
        lake = lambda s: s3_lake(s, bucket=args.bucket)  # noqa: E731

    res = build_xref(lake, con=con, draft_seasons=seasons,
                     include_udfa=not args.no_udfa, udfa_min_score=args.udfa_min_score)
    report = {k: v for k, v in res.report.items() if k != "per_class"}
    print(json.dumps(report, indent=2, default=str))
    print("\nper-draft-class slot baseline:")
    for row in res.report["per_class"]:
        print(f"  {row['season']}: {row['matched']}/{row['cfbd_picks']} = {row['match_pct']}%")
    if args.write:
        n = write_xref_to_delta(res, bucket=args.bucket, local_root=args.local_root)
        print(f"\nwrote {n} rows → {SPORT}/marts/{XREF_TABLE}")


def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s) for s in spec.split(",")]


if __name__ == "__main__":
    _cli()
