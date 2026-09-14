"""handler.py — the NCAAB ingest entrypoint (Dagster op / CLI).

Registry-driven: it walks `sources.SOURCES`, fetches, and lands a content-timestamped Delta
season partition through `lake.py`. Paid feeds are `on_demand` and must be named explicitly,
so a routine run cannot burn Odds credits.

⭐ IT RETURNS A RECEIPT, AND THE RECEIPT RECORDS ATTEMPTS — not just successes. A run that
fetched nothing, a source that refused, and a source that landed 6,318 rows are three
different outcomes, and an artifact that only listed successes would render the first two
identically to "nothing to do" (the execution-witness discipline).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

from . import lake, sources as S

log = logging.getLogger(__name__)


@dataclass
class SourceResult:
    source: str
    season: int
    rows: int = 0
    wrote: bool = False
    uri: str = ""
    escalation: str | None = None
    error: str | None = None
    skipped_reason: str | None = None
    started_at: str = ""
    finished_at: str = ""


@dataclass
class Receipt:
    """The execution witness for one ingest run."""

    sport: str = lake.SPORT
    started_at: str = ""
    finished_at: str = ""
    requested_sources: list[str] = field(default_factory=list)
    seasons: list[int] = field(default_factory=list)
    results: list[SourceResult] = field(default_factory=list)
    credits_remaining: int | None = None

    @property
    def escalations(self) -> list[str]:
        return [r.escalation for r in self.results if r.escalation]

    @property
    def errors(self) -> list[str]:
        return [f"{r.source}[{r.season}]: {r.error}" for r in self.results if r.error]


def run_ingest(*, seasons: list[int] | None = None, source_names: list[str] | None = None,
               local_root: str | None = None, ctx: S.Ctx | None = None,
               today: date | None = None) -> Receipt:
    ctx = ctx or S.Ctx(odds_api_key=os.environ.get("ODDS_API_KEY"))
    seasons = seasons or [S.season_for(today)]
    names = source_names or S.DEFAULT_SOURCES

    # ⛔ ONE WRITER PER TABLE. `run_capture` owns the live odds tables through a read-merge-write
    # because they ACCUMULATE all season; every write on THIS path is a season-grained
    # `replaceWhere` OVERWRITE. So a run_ingest write to one of them does not merge badly — it
    # replaces the whole season with the single board it just fetched, silently and atomically.
    # REFUSING rather than routing: a quiet redirect would make `--sources odds_game_lines` do
    # something other than what it says, and the caller would never learn which writer ran.
    clobber = [n for n in names if n in S.CAPTURE_OWNED_SOURCES]
    if clobber:
        raise S.IngestRefusal(
            f"{clobber} is written by run_capture (read-merge-write), not by run_ingest. "
            "Every run_ingest write is a season replaceWhere OVERWRITE, so landing one here "
            "would replace the whole season's accumulated snapshots with a single board. "
            "Use `python -m ...ingest.odds_capture` (or the sports_ncaab_odds_capture_job) "
            "for live odds; `--sources odds_historical` is the paid backfill and writes its "
            "own separate table.")
    rec = Receipt(started_at=S.now_iso(), requested_sources=list(names), seasons=list(seasons))

    for name in names:
        spec = S.SOURCES.get(name)
        if spec is None:
            rec.results.append(SourceResult(source=name, season=-1,
                                            error=f"unknown source {name!r}; known: "
                                                  f"{sorted(S.SOURCES)}"))
            continue
        for season in seasons:
            r = SourceResult(source=name, season=season, started_at=S.now_iso())
            try:
                payload = spec.fetch(ctx, season)
                n = len(payload)
                r.rows = int(n)
                r.escalation = S.check_landing(spec, r.rows, when=today)
                if r.rows == 0:
                    # ⛔ Never overwrite a good partition with an empty one. An empty write is
                    # indistinguishable downstream from a genuine zero-game season, and Delta's
                    # replaceWhere would make the loss atomic and complete.
                    r.skipped_reason = "zero rows — refusing to overwrite the season partition"
                else:
                    if spec.typed:
                        r.rows = lake.write_dataframe(payload, source=spec.name, season=season,
                                                      local_root=local_root)
                    else:
                        r.rows = lake.write_records(payload, source=spec.name, season=season,
                                                    local_root=local_root)
                    r.wrote = True
                    r.uri = (lake.local_table_uri(local_root, spec.name) if local_root
                             else lake.table_uri(spec.name))
            except S.NotYetPublished as exc:
                # Expected before this season tips off; a real failure once it has. The
                # decision is the registry's, not this loop's.
                esc = S.classify_absence(spec, season, when=today)
                r.skipped_reason = f"not published yet: {exc}"
                r.escalation = esc
                if esc:
                    log.warning("ingest %s[%s] ABSENT in-season: %s", name, season, exc)
                else:
                    log.info("ingest %s[%s] not published yet (expected pre-season)",
                             name, season)
            except Exception as exc:  # noqa: BLE001 — recorded, then surfaced by the caller
                r.error = f"{type(exc).__name__}: {exc}"
                log.warning("ingest %s[%s] FAILED: %s", name, season, r.error)
            r.finished_at = S.now_iso()
            rec.results.append(r)

    rec.credits_remaining = ctx.credits_remaining
    rec.finished_at = S.now_iso()
    return rec


def receipt_to_dict(rec: Receipt) -> dict:
    d = asdict(rec)
    d["escalations"] = rec.escalations
    d["errors"] = rec.errors
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NCAAB lake ingest")
    ap.add_argument("--seasons", default="", help="e.g. 2027 or 2024-2027 (default: current)")
    ap.add_argument("--sources", default="", help=f"default: {','.join(S.DEFAULT_SOURCES)}")
    ap.add_argument("--local-root", default=None, help="write a LOCAL Delta tree instead of S3")
    ap.add_argument("--receipt", default=None, help="write the run receipt JSON here")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    seasons: list[int] = []
    if a.seasons:
        for part in a.seasons.split(","):
            if "-" in part:
                lo, hi = part.split("-")
                seasons += list(range(int(lo), int(hi) + 1))
            else:
                seasons.append(int(part))
    names = [s.strip() for s in a.sources.split(",") if s.strip()] or None

    rec = run_ingest(seasons=seasons or None, source_names=names, local_root=a.local_root)
    payload = receipt_to_dict(rec)
    if a.receipt:
        os.makedirs(os.path.dirname(a.receipt) or ".", exist_ok=True)
        with open(a.receipt, "w") as fh:
            json.dump(payload, fh, indent=2)

    for r in rec.results:
        state = ("wrote" if r.wrote else ("SKIP" if r.skipped_reason else "ERR "))
        print(f"  {state} {r.source:16s} season={r.season} rows={r.rows:>7} "
              f"{r.error or r.skipped_reason or ''}")
    for e in rec.escalations:
        print(f"  {e}")
    if rec.credits_remaining is not None:
        print(f"  odds credits remaining: {rec.credits_remaining:,}")
    # A failure must be visible in the EXIT CODE, not only in a receipt nobody opens.
    return 1 if (rec.errors or rec.escalations) else 0


if __name__ == "__main__":
    raise SystemExit(main())
