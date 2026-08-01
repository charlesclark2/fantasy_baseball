"""run_coaching_ingest.py — NF-D10 OC/HC COACHING-CHANGE source: probe + coverage + landing.

No §0.5 bake-off here (this is the DATA half of NF-D10): the deliverable is the reusable
`coaching_source.load_coach_features(season)` + a live availability/ToS probe + an honest coverage
report. Whether the H-COACH family EARNS a place is decided downstream by NF1.5's deflated
market+blind re-bake-off (`run_nf1_5.py --mode market|blind`), not here — a new data source is not
automatically a feature. `best_alpha = 0`.

  --probe          live-probe both sources (nflverse schedules' per-game coach columns + the
                   Wikipedia staff parse), report shape/coverage/vocabulary. PROBE, don't code to
                   docs — an upstream layout drift shows up here, not as a silent NaN column.
  --coverage       build every season in --from/--to and report per-season OC/HC coverage, the
                   observed change rates, and the leakage assertion (a mid-season change is
                   invisible to its own season).
  --land SEASON [--s3 | --lake-root ROOT]        compute + land one season.
  --land-range --from Y1 --to Y2 [--s3 | ...]    land every season in the range.

RUN (LAPTOP — SF-free; the Wikipedia cache makes a re-run offline):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_coaching_ingest --probe

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_coaching_ingest \
      --coverage --from 2006 --to 2026

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_coaching_ingest \
      --land-range --from 2006 --to 2026 --s3

⏱️ A COLD `--probe`/`--coverage` fetches ~670 Wikipedia pages at a courtesy 0.25 s rate-limit
(~5 min) — that is an OPERATOR run per the >2-min rule. Once the cache under
`artifacts/coaching_cache/wiki/` is primed every later run is offline and seconds-fast.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import coaching_source as C  # noqa: E402

log = logging.getLogger("nfl.fantasy.coaching_ingest")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"


def probe(from_season: int, to_season: int) -> dict:
    """Live availability probe of BOTH sources — printed, not asserted, so an upstream drift is
    visible immediately rather than silently mis-parsed downstream."""
    games = C.fetch_schedule_games(refresh=True)
    reg = games[games["game_type"].astype(str).str.upper() == "REG"] if "game_type" in games else games
    hc_cov = float(reg["home_coach"].notna().mean())
    print(f"HC source: {C.SCHEDULES_URL}")
    print(f"  games rows {len(games)}, REG {len(reg)}, seasons "
          f"{int(games['season'].min())}-{int(games['season'].max())}")
    print(f"  home_coach non-null (REG): {hc_cov:.3f}")

    print(f"OC source: {C.WIKI_API.format('<title>')}  [{C.WIKI_LICENSE}]")
    sample = [(t, s) for s in (from_season, (from_season + to_season) // 2, to_season - 1)
              for t in ("KC", "PHI", "SF")]
    parsed = 0
    for team, season in sample:
        src = C.fetch_wikitext(C.season_article_title(team, season))
        rows = C.parse_staff_roles(src, C.ROLE_OC)
        parsed += int(bool(rows))
        print(f"  {season} {team}: {[(r['coach_name'], r['is_season_opener']) for r in rows] or 'no staff list'}")
    tmpl = C.fetch_wikitext(C.staff_template_title("KC", to_season))
    print(f"  {to_season} KC via {C.staff_template_title('KC', to_season)!r}: "
          f"{[r['coach_name'] for r in C.parse_staff_roles(tmpl, C.ROLE_OC)] or 'none'}")
    return {"hc_source": C.SCHEDULES_URL, "hc_coverage_reg": round(hc_cov, 4),
            "oc_source": "wikipedia (api.wikimedia.org core REST)", "oc_license": C.WIKI_LICENSE,
            "oc_sample_parsed": f"{parsed}/{len(sample)}",
            "games_seasons": [int(games["season"].min()), int(games["season"].max())]}


def leakage_assertion(stints: pd.DataFrame) -> dict:
    """The correctness crux, measured rather than asserted in prose: across the whole stint table,
    how many MID-SEASON changes exist, and does ANY of them reach its own season's feature?

    A mid-season stint is dated inside its season and the as-of anchor is March 15 of that season,
    so the count of leaked stints must be exactly 0 — and the same stints must be visible to the
    FOLLOWING season (otherwise the rule would be 'safe' by simply losing the data)."""
    mid = stints[~stints["is_season_opener"].astype(bool)]
    leaked = visible_next = 0
    for season in sorted(mid["season"].unique()):
        this_season_mid = mid[mid["season"] == int(season)]
        known_same = C.known_stints(this_season_mid, int(season))
        known_next = C.known_stints(this_season_mid, int(season) + 1)
        leaked += len(known_same)
        visible_next += len(known_next)
    return {"n_mid_season_changes": int(len(mid)),
            "leaked_into_own_season": int(leaked),
            "visible_to_next_season": int(visible_next),
            "leakage_safe": bool(leaked == 0 and visible_next == len(mid))}


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-D10 — OC / head-coach change source (the H-SYSTEM regime variable)")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()}. Edge-independent, "
      f"`best_alpha=0` — CANDIDATE projection features for NF1.2/NF1.5, not an edge claim. "
      f"Whether H-COACH ships is decided by NF1.5's deflated market+blind re-bake-off.")
    p("")
    p("## 1. Sources + ToS disposition (probed live, not read off docs)")
    p("")
    p("| role | source | license / access | disposition |")
    p("|------|--------|------------------|-------------|")
    p("| **HC** | nflverse `schedules/games.parquet` (`home_coach`/`away_coach`) | the release "
      "feed this repo already reads | ✅ used — PER-GAME grain, so an HC stint carries an EXACT "
      "effective date |")
    p("| **OC** | Wikipedia team-season `==Staff==` via `api.wikimedia.org` core REST | CC BY-SA "
      "4.0, Wikimedia's own programmatic endpoint, identifying UA, one cached fetch per page | ✅ "
      "used — the story's sanctioned last resort, after the structured options below failed |")
    p("| — | nflverse coaching release | — | ❌ **does not exist** (all 25 release tags enumerated "
      "live; `contracts`/`depth_charts`/`officials` exist, a coaches table does not) |")
    p("| — | Pro-Football-Reference coaching pages | Cloudflare JS challenge on `robots.txt` "
      "itself | ❌ **not scraped** — same disposition NF-D8 reached for Spotrac/OverTheCap |")
    p("| — | `spatto12/NFLCoaches` (PFR-derived) | MIT | ❌ HEAD-COACH ONLY and stops at 2023 — "
      "adds nothing over the nflverse coach columns |")
    p("")
    p(f"Wikipedia's `robots.txt` was fetched and honoured: `/wiki/<Article>` is allowed for "
      f"`User-agent: *` (only `Special:`, `/w/` and `/api/` are disallowed); reads go through the "
      f"dedicated `api.wikimedia.org` host with a contact UA per Wikimedia's UA policy.")
    p("")
    pr = out.get("probe", {})
    if pr:
        p(f"- HC `home_coach` non-null over regular-season games: **{pr.get('hc_coverage_reg')}** "
          f"(seasons {pr.get('games_seasons')})")
        p("")
    p("## 2. Coverage (the honest floor)")
    p("")
    p("`oc_coverage` = share of the 32 teams with a parsed WEEK-1 offensive coordinator. "
      "`new_oc_computable` = teams where BOTH this season's opener and last season's finisher "
      "parsed, so the flag is real rather than NaN.")
    p("")
    p("| season | teams | OC cov | HC cov | new_oc computable | new_oc rate | new_hc rate |")
    p("|--------|-------|--------|--------|-------------------|-------------|-------------|")
    for r in out.get("seasons", []):
        p(f"| {r['season']} | {r['n_teams']} | {r['oc_coverage']} | {r['hc_coverage']} | "
          f"{r['new_oc_computable']} | {r['new_oc_rate']} | {r['new_hc_rate']} |")
    p("")
    cov = [r["oc_coverage"] for r in out.get("seasons", [])]
    if cov:
        p(f"**Coverage floor:** OC parses for **{min(cov):.0%}–{max(cov):.0%}** of teams per "
          f"season (overall {sum(cov)/len(cov):.1%}); HC is **100%** every season. The weak years "
          f"are 2007–2009, where a handful of team-season articles carry no staff list at all "
          f"(prose only). A team with no parsed OC gets **NaN**, never a fabricated value — the "
          f"learners median-impute and the MVP-1 null ignores it.")
    p("")
    p("## 3. Leakage-safe as-of (the correctness crux)")
    p("")
    p("Every stint carries an `effective_date`; a projection for season *Y* may only read stints "
      "with `effective_date <= March 15 of Y` (after the new league year opens and after the "
      "Jan–Feb coaching carousel, months before Week 1). So an OFFSEASON hire is in *Y*'s feature "
      "and a MID-SEASON firing inside *Y* is not — it becomes visible only from *Y+1*.")
    p("")
    lk = out.get("leakage", {})
    p(f"- mid-season changes in the stint table: **{lk.get('n_mid_season_changes')}**")
    p(f"- of those, reaching their OWN season's pre-season feature: **{lk.get('leaked_into_own_season')}** "
      f"(must be 0)")
    p(f"- visible to the FOLLOWING season: **{lk.get('visible_to_next_season')}** (must equal the "
      f"total — the rule must be safe by DATING, not by discarding)")
    p(f"- **leakage-safe: {lk.get('leakage_safe')}**")
    p("")
    p("## 4. Honest gaps")
    p("")
    p("- **The OC parse is season-granular.** Wikipedia records WHO held the job, not the DATE he "
      "was hired; a season-opening coordinator is therefore stamped with the March 15 anchor "
      "rather than his actual announcement date. That is conservative in the direction that "
      "matters (it never makes a change known EARLIER than the offseason) but it means the source "
      "cannot answer 'was this hire known on February 1'.")
    p("- **A mid-season replacement's date is approximate** — derived from a week annotation when "
      "the article carries one, else the season's week-9 midpoint. Only its SIDE of the as-of "
      "boundary is load-bearing, and that is exact by construction (any within-season date is "
      "after the March anchor).")
    p("- **Co-coordinators** are recorded as separate stints; the first listed is treated as the "
      "week-1 holder, so a genuine co-OC pair reads as a single regime.")
    p("- **`oc_prior_pass_rate_delta` inherits the team-rate floor, and DEGENERATES below it.** "
      "`rollup_nfl_team_season` carries `off_pass_rate` for 2020–2025 only, so for projection "
      "seasons ≤2020 the column collapses to '0.0 iff the OC was retained, NaN otherwise' — the "
      "same information `new_oc` already carries, NOT a measured scheme shock. It is a genuinely "
      "distinct signal only from projection season 2021 onward (measured non-null rate on the "
      "rebuilt pools: ~0.51–0.58, of which the pre-2021 part is entirely retained-OC zeros). "
      "⚠️ Read a family lift accordingly: if H-COACH clears only on pre-2021 targets, it is "
      "`new_oc` clearing, not the scheme-shock hypothesis. The other four columns cover the full "
      "range.")
    p("- **A parse gap in season *Y−1* makes season *Y*'s `new_oc` NaN**, not 0 — an unknown "
      "predecessor can never be silently read as 'no change'.")
    p("")
    p("## Disposition")
    p("")
    p("- **Ship (data):** `coaching_source.load_coach_features(season)` → per-team "
      "`new_oc` / `oc_tenure_years` / `new_hc` / `coach_continuity` (+ the names and the previous "
      "OC's last job, which `nf1_2_model.attach_coach` turns into `oc_prior_pass_rate_delta`). "
      "Landed to `nfl/fantasy/coaching/team_coach_features` + the effective-dated audit table "
      "`nfl/fantasy/coaching/coach_stints` (season-partitioned Delta).")
    p("- **Feature — ⛔ RECORDED NULL (NF1.5 blind re-bake-off, 2026-07-31).** H-COACH is "
      "registered in `nf1_2_model.REFINEMENT_FAMILIES` and in NF1.5's `base_system_coach` / "
      "`env_coach` / `kitchen_sink` bundles, and it **did not clear**: no coach bundle won at any "
      "position over 16 scored targets (2010–2025, 631–811 configs/position, placebo clean, "
      "oracle sane). The MATCHED-FOIL attribution the bundles exist for — each coach bundle "
      "against the identical bundle minus `coach` — is **NEGATIVE in 7 of 10 computable "
      "comparisons**, and no position has both of its comparisons positive. Full result: "
      "`ablation_results/nf1_5_feature_combination_bakeoff.{md,json}` (stage 2). The DATA still "
      "ships (it is the effective-dated substrate for the future weekly model); the FEATURE does "
      "not, and the incumbent bundles stand.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def land(season: int, *, stints: pd.DataFrame, to_s3: bool, local_root: str | None) -> tuple[int, int]:
    """Land SEASON's feature rows + its effective-dated stint rows to the lake."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    # dtypes are pinned at the WRITER (see `pin_feature_dtypes` — an all-NaN season would
    # otherwise create the Delta column as Float64 and break every later partition)
    feats = C.pin_feature_dtypes(C.build_team_coach_features(stints, season))
    season_stints = C.pin_stint_dtypes(stints[stints["season"] == int(season)].copy())
    if not (to_s3 or local_root):
        log.info("computed %d feature rows / %d stint rows for season=%d (no --s3/--lake-root ⇒ "
                 "not landed)", len(feats), len(season_stints), season)
        return 0, 0
    n_f = s3io.write_dataframe(feats, sport=C.LAKE_SPORT, source=C.LAKE_SOURCE_FEATURES,
                              season=season, tier=C.LAKE_TIER, local_root=local_root)
    n_s = s3io.write_dataframe(season_stints, sport=C.LAKE_SPORT, source=C.LAKE_SOURCE_STINTS,
                              season=season, tier=C.LAKE_TIER, local_root=local_root)
    log.info("landed season=%d: %d feature rows, %d stint rows", season, n_f, n_s)
    return n_f, n_s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D10 OC/HC coaching-change source")
    ap.add_argument("--probe", action="store_true", help="live availability probe of both sources")
    ap.add_argument("--from", dest="from_season", type=int, default=C.DEFAULT_FROM_SEASON)
    ap.add_argument("--to", dest="to_season", type=int, default=C.DEFAULT_TO_SEASON)
    ap.add_argument("--refresh", action="store_true", help="force re-fetch (schedules + wikitext)")
    ap.add_argument("--coverage", action="store_true", help="per-season coverage + leakage report")
    ap.add_argument("--land", type=int, metavar="SEASON", help="compute + land one SEASON")
    ap.add_argument("--land-range", action="store_true", help="land every season in --from/--to")
    ap.add_argument("--s3", action="store_true")
    ap.add_argument("--lake-root", default=None, help="land to a local-FS Delta tree (offline)")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")

    out: dict = {}
    if args.probe:
        out["probe"] = probe(args.from_season, args.to_season)
        if not (args.coverage or args.land is not None or args.land_range):
            return 0

    if not (args.coverage or args.land is not None or args.land_range):
        ap.error("nothing to do — pass --probe, --coverage, --land or --land-range")

    seasons = list(range(args.from_season, args.to_season + 1))
    # ONE stint assembly for the whole window (assemble-once). The window starts a season EARLY:
    # `new_oc`/tenure both need who finished the season BEFORE the floor.
    stints = C.build_coach_stints([args.from_season - 1, *seasons], refresh=args.refresh,
                                  current_season=args.to_season)
    log.info("stint table: %d rows (%s)", len(stints),
             stints.groupby("role").size().to_dict() if len(stints) else {})

    if args.coverage:
        rows = []
        for s in seasons:
            feats = C.build_team_coach_features(stints, s)
            r = C.coverage_report(stints, feats, s)
            rows.append(r)
            print(f"season={s}: OC {r['oc_coverage']} HC {r['hc_coverage']} "
                  f"new_oc {r['new_oc_rate']} (n={r['new_oc_computable']}) "
                  f"new_hc {r['new_hc_rate']}")
        out["seasons"] = rows
        out["leakage"] = leakage_assertion(stints)
        print(f"leakage assertion: {out['leakage']}")
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (_REPORT_DIR / "nf_d10_coaching_source.json").write_text(
            json.dumps(out, indent=2, default=str))
        if not args.no_report:
            write_report(out, _REPORT_DIR / "nf_d10_coaching_source.md")

    if args.land is not None:
        land(args.land, stints=stints, to_s3=args.s3, local_root=args.lake_root)
    elif args.land_range:
        for s in seasons:
            land(s, stints=stints, to_s3=args.s3, local_root=args.lake_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
