"""NCAAF-P1.2W — did the weekly P1.2 strength re-fit actually WORK, or did it merely RUN?

THE DEFECT THIS EXISTS FOR, measured twice.

P1.2 reads its covariates from the sports dbt MARTS (`ncaaf_team_roster_continuity`,
`ncaaf_team_coaching_change`), not from the lake. So `run_team_strength` pointed at STALE marts
reproduces the pre-season cold start, writes a full set of per-season Delta commits, exits 0, and
looks exactly like a successful re-fit. It did precisely that on 2026-08-17: the Delta log showed
the writes and every covariate component in the output was 0. The NCAAF-PS report records the SQL
that separated the two readings — `0 / 0 / 138` is a cold start, `136 / 136 / 138` is a real fit.

⭐ AND A SECOND READING IS NEEDED, BECAUSE THE COVARIATE CHECK ALONE IS SATISFIED BY DOING NOTHING.
Measured on the served table 2026-09-13: season 2026 carries 138 teams with `roster_flux` 136 and
`coaching` 136 — i.e. the covariate discriminator PASSES on an artifact whose newest commit is
2026-08-18 and which holds `as_of_week = 1` and nothing else, three played weeks later. A check
that passes on the frozen artifact cannot certify a refresh. So this module reads THREE things and
each answers a question the other two structurally cannot:

  1. THE VINTAGE ADVANCED — the Delta version/commit captured BEFORE the fit must be strictly older
     than the one read AFTER it, in the same run. This is what catches "the fit crashed / wrote
     nothing / wrote somewhere else", and it needs no persisted state because both readings are
     taken inside one run. ⛔ It is a CONTENT read from inside `_delta_log`, never an object mtime
     or an `aws s3 ls` LastModified (INC-41: an mtime is refreshed by any server-side rewrite that
     changes no data, and `aws s3 ls` prints SHELL-LOCAL time).
  2. THE COVARIATES ARE PRESENT — the 2026-08-17 cold start, caught by its own fingerprint.
  3. THE WEEK INDEX ADVANCED — `max(as_of_week) > 1` **when the marts hold completed games for the
     season**. This is the reading that would have caught the story's actual gap, and its guard is
     the condition: in August, before a snap is played, `as_of_week = 1` is the only correct answer,
     so the check declares itself INACTIVE rather than passing (NF1.7(a) / NF-D20 — an inactive
     check is uninformative, never a pass, and the count of rows it could have acted on is
     reported beside the verdict).

TIERING — this module DECIDES, it never pages and never raises. `pipeline/jobs/…` does the paging
and the raising, so the policy stays import-safe for the fast gate (E11.23: nothing here imports
`pipeline`, and the IO import is lazy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: The NCAAF season months, as a `active_months` window: August → January (bowls + the CFP run
#: into mid-January). The SAME set every other in-season NCAAF cron carries (`8-12,1`), which is
#: why it is written once here and read by the freshness contract rather than re-typed.
SEASON_MONTHS: tuple[int, ...] = (8, 9, 10, 11, 12, 1)

#: The covariate GROUPS whose presence separates a real fit from the cold start.
#:
#: ⛔ `carryover` and `talent` are deliberately NOT here, and both exclusions are measurements
#: rather than taste. `carryover` is last season's posterior carried forward — it is populated in
#: the cold start too (136/138 on the frozen 2026 artifact), so it cannot discriminate. `talent`
#: is 0 for all 138 teams because CFBD has not published 2026 talent at all (verified live by
#: NCAAF-RF1: `/talent?year=2026` returns HTTP 200 with zero rows while 2024/2025 return 134
#: each) — requiring it would fail every honest 2026 fit. `unknown` is a residual bucket.
DISCRIMINATING_COVARIATES: tuple[str, ...] = ("roster_flux", "coaching")

#: Column prefix `run_team_strength` emits one per covariate group.
COVARIATE_COLUMN_PREFIX = "covariate_component_"


@dataclass(frozen=True)
class RefitState:
    """One reading of the ratings artifact — the vintage plus the content that proves a real fit.

    `error` is set when the lake could not be read at all; every numeric field is then None and
    `classify_refit` reports UNREADABLE rather than inventing a verdict (NF1.7(a)).
    """

    season: int
    version: int | None = None
    commit: datetime | None = None          # tz-aware UTC, from inside `_delta_log`
    teams: int | None = None
    covariate_nonzero: dict[str, int] = field(default_factory=dict)
    max_as_of_week: int | None = None
    error: str | None = None

    @property
    def readable(self) -> bool:
        return self.error is None and self.version is not None


def classify_refit(before: RefitState, after: RefitState, *,
                   completed_games: int | None) -> dict:
    """PURE — the verdict for one re-fit attempt, from the before/after readings.

    `completed_games` is the number of completed team-game rows the MARTS held for the season when
    the fit ran; it is what makes reading 3 active or inactive. `None` means the marts count could
    not be taken, which makes reading 3 UNEVALUABLE — reported as such, never as a pass.

    Verdicts: `REFIT_LANDED` · `UNREADABLE` · `VINTAGE_DID_NOT_ADVANCE` · `COLD_START` ·
    `WEEK_DID_NOT_ADVANCE`. Every non-OK verdict is CRITICAL: each one means the ratings the
    product serves are not the ratings this run was supposed to produce.
    """
    metrics = _metrics(before, after, completed_games)

    if not after.readable:
        return _verdict("UNREADABLE", "CRITICAL", metrics,
                        f"the ratings artifact could not be read AFTER the fit "
                        f"({after.error or 'no Delta version'}). The fit may or may not have "
                        f"landed — an unreadable check is not a passed check, so this run fails "
                        f"rather than reporting a refresh it cannot see.")

    if before.readable and not _advanced(before, after):
        return _verdict("VINTAGE_DID_NOT_ADVANCE", "CRITICAL", metrics,
                        f"the ratings artifact did NOT advance across this run: version "
                        f"{before.version} → {after.version}, commit {_iso(before.commit)} → "
                        f"{_iso(after.commit)}. The fit exited without writing the lake, so the "
                        f"product is still serving the previous vintage. This is a CONTENT read "
                        f"from inside _delta_log, not an object mtime.")

    zero = [g for g in DISCRIMINATING_COVARIATES if not after.covariate_nonzero.get(g)]
    if zero and after.teams:
        return _verdict("COLD_START", "CRITICAL", metrics,
                        f"the fit landed but reproduced the PRE-SEASON COLD START for season "
                        f"{after.season}: {', '.join(zero)} is zero on all {after.teams} teams. "
                        f"P1.2 reads its covariates from the sports dbt MARTS, so this is the "
                        f"stale-marts signature (measured once, 2026-08-17). The ratings now "
                        f"served are COMPRESSED toward the mean; rebuild the marts from the fresh "
                        f"lake and re-fit.")

    if completed_games is None:
        return _verdict("REFIT_LANDED", None, metrics,
                        f"{_landed(after)} ⚠️ the week-index check was UNEVALUABLE — the completed"
                        f"-game count could not be read from the marts, so it is reported "
                        f"unverified rather than passed.")

    if completed_games > 0 and (after.max_as_of_week or 0) <= 1:
        return _verdict("WEEK_DID_NOT_ADVANCE", "CRITICAL", metrics,
                        f"the marts hold {completed_games} completed team-game row(s) for season "
                        f"{after.season}, but the fit emitted no as-of week past 1 "
                        f"(max_as_of_week={after.max_as_of_week}). The posterior has not absorbed "
                        f"a single played week — exactly the frozen-prior state this schedule "
                        f"exists to end.")

    if completed_games == 0:
        return _verdict("REFIT_LANDED", None, metrics,
                        f"{_landed(after)} ℹ️ the week-index check is INACTIVE: the marts hold no "
                        f"completed games for season {after.season} yet, so as_of_week=1 is the "
                        f"only correct answer and this reading could not have failed. Inactive, "
                        f"not passed.")

    return _verdict("REFIT_LANDED", None, metrics,
                    f"{_landed(after)} The week index reached {after.max_as_of_week} over "
                    f"{completed_games} completed team-game row(s).")


def is_problem(verdict: dict) -> bool:
    """True when the verdict means the run must fail — anything but a landed re-fit."""
    return verdict.get("verdict") != "REFIT_LANDED"


def _advanced(before: RefitState, after: RefitState) -> bool:
    """Strictly newer content. VERSION is the authority (delta's monotone commit counter); the
    commit timestamp is carried for legibility and is NOT used as a tiebreak — two commits can
    share a millisecond, and a clock is not a sequence."""
    if after.version is None:
        return False
    if before.version is None:
        return True          # nothing to compare against; the presence of a version is the news
    return after.version > before.version


def _landed(after: RefitState) -> str:
    counts = ", ".join(f"{g}={after.covariate_nonzero.get(g, 0)}"
                       for g in DISCRIMINATING_COVARIATES)
    return (f"the re-fit LANDED: season {after.season}, {after.teams} teams, Delta v{after.version} "
            f"at {_iso(after.commit)}, covariates {counts}.")


def _metrics(before: RefitState, after: RefitState, completed_games: int | None) -> dict:
    return {
        "season": after.season,
        "before_version": before.version,
        "after_version": after.version,
        "before_commit": _iso(before.commit),
        "after_commit": _iso(after.commit),
        "teams": after.teams,
        "max_as_of_week": after.max_as_of_week,
        "completed_games": completed_games,
        **{f"covariate_nonzero_{g}": after.covariate_nonzero.get(g, 0)
           for g in DISCRIMINATING_COVARIATES},
    }


def _verdict(name: str, severity: str | None, metrics: dict, detail: str) -> dict:
    return {"verdict": name, "severity": severity, "detail": detail, "metrics": metrics}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


# ── The readers (IO — imported lazily so this module stays fast-gate safe) ───────────────────
def read_refit_state(season: int, *, bucket: str | None = None,
                     local_root: str | None = None) -> RefitState:
    """Read the ratings artifact's vintage AND the content that proves a real fit. NEVER raises —
    an unreadable lake becomes a `RefitState` carrying the error, which `classify_refit` turns into
    UNREADABLE/CRITICAL.

    ⭐ THE VINTAGE COMES FROM `sports_delta_freshness`, NOT FROM A SECOND PARSER HERE. delta-rs has
    shipped the commit `timestamp` as both epoch-milliseconds and a datetime; a second reader is
    how the two owners drift (the `ncaaf_ratings_vintage` module makes the same delegation and
    names the same reason).
    """
    from betting_ml.monitoring import sports_delta_freshness as SDF

    contract = ratings_contract()
    reading = SDF.read_contract(contract, bucket=bucket, local_root=local_root)
    if not reading.readable:
        return RefitState(season=season, error=reading.error or "no commit timestamp")

    try:
        counts, teams, max_week = _read_season_content(season, bucket=bucket,
                                                       local_root=local_root)
    except Exception as exc:  # noqa: BLE001 — surfaced as UNREADABLE, never swallowed
        return RefitState(season=season, version=reading.version, commit=reading.last_commit,
                          error=f"{type(exc).__name__}: {exc}")
    return RefitState(season=season, version=reading.version, commit=reading.last_commit,
                      teams=teams, covariate_nonzero=counts, max_as_of_week=max_week)


def _read_season_content(season: int, *, bucket: str | None = None,
                         local_root: str | None = None):
    """`(covariate nonzero counts, team count, max as_of_week)` for `season`.

    Column-projected on purpose: the table is every team-week of every season since the seed, and
    this reader runs inside a serving-adjacent job. Only the six columns the verdict reads are
    pulled.
    """
    import os

    from deltalake import DeltaTable

    from quant_sports_intel_models.football.ncaaf.ingest import s3io

    contract = ratings_contract()
    if local_root:
        uri = s3io.local_table_uri(local_root, contract.sport, contract.source, tier=contract.tier)
        opts = None
    else:
        uri = s3io.table_uri(contract.sport, contract.source,
                             bucket=bucket or s3io.DEFAULT_BUCKET, tier=contract.tier)
        opts = s3io.storage_options(os.environ.get("SPORTS_LAKE_REGION", s3io.DEFAULT_REGION))

    columns = ["season", "team_id", "as_of_week"] + [
        f"{COVARIATE_COLUMN_PREFIX}{g}" for g in DISCRIMINATING_COVARIATES]
    frame = DeltaTable(uri, storage_options=opts).to_pyarrow_table(columns=columns).to_pandas()
    rows = frame[frame["season"] == season]
    if rows.empty:
        return {g: 0 for g in DISCRIMINATING_COVARIATES}, 0, None

    counts = {
        g: int((rows[f"{COVARIATE_COLUMN_PREFIX}{g}"].fillna(0) != 0).sum())
        for g in DISCRIMINATING_COVARIATES
    }
    return counts, int(rows["team_id"].nunique()), int(rows["as_of_week"].max())


def read_completed_games(season: int, duckdb_path: str, schema: str = "main_ncaaf_marts") -> int | None:
    """Completed team-game rows the MARTS hold for `season` — the activity count for reading 3.

    Returns None (never 0) when the marts cannot be read: an ABSENT count must classify as
    UNEVALUABLE, not as "no completed games", because the latter would silently DISABLE the
    week-index check on exactly the runs where something is already wrong.
    """
    try:
        import duckdb

        conn = duckdb.connect(duckdb_path, read_only=True)
        try:
            row = conn.execute(
                f"select count(*) from {schema}.fact_ncaaf_team_game "  # noqa: S608 — fixed schema
                f"where season = ? and is_completed", [season]).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else None
    except Exception:  # noqa: BLE001 — UNEVALUABLE, reported by the caller, never a silent 0
        return None


def ratings_contract():
    """The ratings artifact's freshness contract, from the ONE registry that owns it."""
    from betting_ml.monitoring import sports_delta_freshness as SDF

    return SDF.by_name("ncaaf_team_strength_week")
