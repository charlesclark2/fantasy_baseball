"""wayback_injury_source.py — NF-W2c: PIT-clean 2025 injury designations from Wayback captures.

THE GAP THIS CLOSES: nflverse deleted the `date_modified` as-of stamp in 2025 and NF-W0a's own
forward-capture didn't exist before the 2025 season ended, so the injury family is structurally
unmeasurable there (the NF-W2/W2b shadow folds). ⭐ THE 2025 DESIGNATION VALUES EXIST in the
lake (6,068 rows) — what is missing is a PROVABLE per-row as-of instant. A Wayback Machine
snapshot supplies exactly that: the archive's capture instant is a third-party-attested moment
at which the page's content demonstrably existed. A designation parsed from a capture at T is
admissible for a player-week iff T lands STRICTLY BEFORE that player's own gameday 00:00 UTC —
the NF-W2 bound verbatim, with the Wayback instant in `date_modified`'s role.

STAMP ENCODING (verified two-sided against `assert_point_in_time`): `capture_timestamp` /
`feature_timestamp` / `ingestion_timestamp` = the Wayback instant; `source_timestamp` = a
DECLARED absence (the page publishes no per-row vendor as-of — never launder the archive's
instant into a vendor claim; the guard bounds on the capture/feature stamps and rejects a
post-projection capture).

SOURCES (assessed 2026-08-09; each capture decompresses to a full data-bearing page):
  · nfl.com/injuries — the OFFICIAL weekly report: per-player practice participation + game
    status, the page title declares its week. Sparse but covers December (23 captures).
  · espn.com/nfl/injuries — `window['__espnfitt__']` embedded JSON: per-athlete statusDesc
    (Out/Doubtful/Questionable) + the game date. Dense Sep–Nov (79 captures), dark in December.
  · cbssports.com/nfl/injuries — data-bearing (65 captures) but its parser is DEFERRED
    (carded); enumerate + fetch it so the crawl retains the raw bytes either way.

⚠️ SNAPSHOT BYTES ARE BYTES: archived bodies are frequently stored gzip'd, and decoding them
as text with errors="ignore" DESTROYS the gzip magic and yields a confident, empty parse — this
exact bug produced a false "all sources are dataless shells" verdict during this story's own
research. `snapshot_text` therefore takes bytes, gunzips on magic, and REFUSES a mangled
payload (guard-tested).

⛔ NO fillna(0): a parsed row carries None for an absent designation/practice status — absence
of evidence in a snapshot is never "healthy". Pure module — network lives in small fetch
helpers the runner drives; S3 landing lives in the runner (store.append_captures).
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger("nfl.fantasy.wayback_injury")

SEASON = 2025
CAPTURE_SOURCE = "wayback_injuries"

#: The enumerated capture families. CBS is fetched (raw bytes retained) but not yet parsed.
CDX_TARGETS: tuple[tuple[str, str], ...] = (
    ("nfl", "nfl.com/injuries*"),
    ("espn", "espn.com/nfl/injuries"),
    ("cbs", "cbssports.com/nfl/injuries*"),
)
#: The 2025 season's capture window (Aug 2025 – mid-Feb 2026 covers REG + playoffs).
CDX_FROM, CDX_TO = "20250801", "20260215"

_STATUS_MAP = {"out": "out", "doubtful": "doubtful", "questionable": "questionable"}
_PRACTICE_MAP = {
    "did not participate in practice": "dnp",
    "limited participation in practice": "limited",
    "full participation in practice": "full",
}


# ── Wayback plumbing (bytes-first; every response cached to disk for reproducibility) ───────────
def cdx_captures(url_pattern: str, cache_dir: Path, *, frm: str = CDX_FROM, to: str = CDX_TO,
                 name: str | None = None, retries: int = 4) -> list[dict]:
    """CDX enumeration for one URL pattern → [{timestamp, url}] (status-200 only, cached)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / f"cdx_{name or re.sub(r'[^A-Za-z0-9]+', '_', url_pattern)}.json"
    if f.exists():
        rows = json.loads(f.read_text())
    else:
        u = (f"https://web.archive.org/cdx/search/cdx?url={url_pattern}&from={frm}&to={to}"
             f"&output=json&filter=statuscode:200&limit=1000")
        rows = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(u, timeout=120) as r:
                    payload = json.load(r)
                rows = payload[1:] if payload else []
                f.write_text(json.dumps(rows))
                break
            except Exception as exc:  # noqa: BLE001 — retried, then raised loudly below
                err = exc
                time.sleep(10 * (attempt + 1))
        if rows is None:
            raise RuntimeError(f"CDX enumeration failed for {url_pattern}: {err}")
    return [{"timestamp": r[1], "url": r[2]} for r in rows]


def fetch_snapshot_bytes(timestamp: str, url: str, cache_dir: Path,
                         *, retries: int = 3, pause_s: float = 2.0) -> bytes:
    """One archived body, RAW BYTES, disk-cached. `id_` mode returns the original response."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = f"{timestamp}_{re.sub(r'[^A-Za-z0-9]+', '_', url)[:80]}"
    f = cache_dir / f"snap_{key}.bin"
    if f.exists():
        return f.read_bytes()
    u = f"https://web.archive.org/web/{timestamp}id_/{url}"
    req = urllib.request.Request(u, headers={"User-Agent": "credence-nf-w2c/0.1"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            f.write_bytes(raw)
            time.sleep(pause_s)  # be a polite archive citizen — the crawl is ~150 requests
            return raw
        except Exception as exc:  # noqa: BLE001
            err = exc
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"snapshot fetch failed for {timestamp} {url}: {err}")


def snapshot_text(raw: bytes) -> str:
    """Bytes → text, gunzipping on magic. REFUSES a decode-mangled gzip payload — the header
    `\\x1f\\x08` (gzip missing its second magic byte) is the fingerprint of bytes that went
    through a lossy text decode, and parsing them yields a confident empty result."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    elif raw[:1] == b"\x1f":
        raise ValueError(
            "payload starts with a mangled gzip header (\\x1f without \\x8b) — these bytes went "
            "through a lossy text decode; refetch as BYTES (the false-'dataless-shell' bug)")
    return raw.decode("utf-8", errors="replace")


def wayback_ts_to_utc(ts: str) -> str:
    """A CDX timestamp (YYYYMMDDhhmmss, UTC by Wayback convention) → ISO-8601 UTC."""
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc).isoformat()


# ── Parsers (fixtures in the guard tests are REAL trimmed payloads — NF-C0e) ────────────────────
_NFL_TITLE_RE = re.compile(r"Week\s+(\d+)\s+of\s+the\s+(\d{4})", re.I)
_NFL_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_NFL_PLAYER_RE = re.compile(r'href="/players/([^/"]+)/"[^>]*>\s*([^<]+?)\s*</a>', re.S)
_NFL_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def parse_nfl_report(text: str) -> tuple[int | None, int | None, list[dict]]:
    """The official nfl.com report → (declared_week, declared_season, rows).

    Row cells (observed layout): player-link · position · injury · practice participation ·
    game status. Absent practice/status cells parse to None — ⛔ never a semantic zero."""
    m = _NFL_TITLE_RE.search(text)
    week, season = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    rows: list[dict] = []
    for tr in _NFL_TR_RE.findall(text):
        pm = _NFL_PLAYER_RE.search(tr)
        if not pm:
            continue
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in _NFL_TD_RE.findall(tr)]
        if len(cells) < 5:
            continue
        practice = _PRACTICE_MAP.get(cells[3].strip().lower()) if cells[3].strip() else None
        status = _STATUS_MAP.get(cells[4].strip().lower()) if cells[4].strip() else None
        rows.append({
            "player_slug": pm.group(1), "player_name": pm.group(2).strip(),
            "position": cells[1].strip().upper() or None,
            "injury": cells[2].strip() or None,
            "practice_status": practice, "report_status": status,
        })
    return week, season, rows


_ESPN_STATE_RE = re.compile(r"window\['__espnfitt__'\]\s*=\s*(\{.*?\});?\s*</script>", re.S)


def parse_espn(text: str) -> list[dict]:
    """espn.com/nfl/injuries → rows from the embedded `__espnfitt__` JSON.

    A recursive walk collects every athlete-bearing injury entry (robust to layout drift
    across the season's captures). ONLY the weekly designations (Out/Doubtful/Questionable)
    are kept — ESPN mixes in roster designations (IR etc.), which are NOT the weekly report
    channel this family models."""
    m = _ESPN_STATE_RE.search(text)
    if not m:
        return []
    state = json.loads(m.group(1))
    rows: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            ath = node.get("athlete")
            desc = node.get("statusDesc")
            if isinstance(ath, dict) and isinstance(desc, str):
                status = _STATUS_MAP.get(desc.strip().lower())
                if status is not None:
                    rows.append({
                        "player_name": (ath.get("name") or "").strip(),
                        "position": (ath.get("position") or "").strip().upper() or None,
                        "report_status": status,
                        "practice_status": None,   # ESPN does not publish the practice line
                        "game_date_hint": (node.get("date") or "").strip() or None,
                    })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(state)
    return [r for r in rows if r["player_name"]]


def resolve_game_date_hint(hint: str | None, capture_ts_iso: str) -> str | None:
    """ESPN's 'Oct 12' → an ISO date, year resolved from the capture instant (a Jan game in a
    season that started the prior Sep belongs to capture-year when the capture is already in
    Jan/Feb, else capture-year+1)."""
    if not hint:
        return None
    cap = datetime.fromisoformat(capture_ts_iso)
    try:
        d = datetime.strptime(hint, "%b %d")
    except ValueError:
        return None
    year = cap.year
    if d.month < 6 and cap.month >= 6:      # a Jan/Feb game seen from Sep–Dec
        year += 1
    return d.replace(year=year).date().isoformat()


# ── Normalization to capture-stamped rows ───────────────────────────────────────────────────────
def stamped_rows_from_capture(source: str, timestamp: str, text: str) -> pd.DataFrame:
    """One snapshot → a frame of capture-stamped designation rows (no week/gsis resolution yet;
    the builder attributes weeks against the schedule and crosswalks names → gsis)."""
    ts_iso = wayback_ts_to_utc(timestamp)
    if source == "nfl":
        week, season, rows = parse_nfl_report(text)
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["declared_week"] = week
        df["declared_season"] = season
        df["game_date_hint"] = None
    elif source == "espn":
        df = pd.DataFrame(parse_espn(text))
        if df.empty:
            return df
        df["declared_week"] = None
        df["declared_season"] = None
        df["game_date_hint"] = df["game_date_hint"].map(
            lambda h: resolve_game_date_hint(h, ts_iso))
        df["player_slug"] = None
        df["injury"] = None
    else:
        raise ValueError(f"no parser for source {source!r} (cbs is enumerated but deferred)")
    df["capture_ts"] = ts_iso
    df["capture_wayback"] = timestamp
    df["source"] = source
    return df
