"""E8.1 — the MLB dynasty prospect board's app surface: the exporter, the publish guard, and the
gated `/fantasy/mlb/prospects/*` read path.

Fast-gate: pure pandas + direct endpoint calls, no S3 / network (the router is exercised through
the same local-dir override `test_fantasy_entitlement.py` and `test_fantasy_public_router.py` use).

What this file exists to prove, in the order the failures would actually hurt:

  1. The board reaches the surface with its MEANING intact — a missing MLE line stays missing rather
     than becoming a zero, and the honest framing travels IN the payload.
  2. The paid board cannot be read without the fantasy gate, and it reads the `fantasy/mlb/` key
     space rather than silently sharing NFL's.
  3. `--publish` never silently no-ops, and a resolved bucket never publishes by itself.
  4. The payload cannot quietly outgrow AWS Lambda's 6 MB proxy-response cap.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest
from fastapi import HTTPException

from app.backend import dependencies as deps
from app.backend.routers import fantasy
from quant_sports_intel_models.baseball.fantasy import export_prospect_board_json as exporter


# ── a board frame shaped like the real one ────────────────────────────────────────────────────
#
# Row 2 is the case that matters most: a complex-league bat with NO MLE line at all. That is an
# EXPECTED state on this board (an identity with no minor-league PA yet), and it must survive to the
# client as an absence, never as a zero.
# Row 3 is an MLB-Pipeline-only player — carried with a NULL `season`, which is why the exporter
# derives the season with max() rather than any statistic a null can win.

def _board() -> pd.DataFrame:
    return pd.DataFrame({
        "board_rank": [1, 2, 3],
        "player_name": ["Real Bat", "Complex Kid", "Pipeline Arm"],
        "org": ["ATL", "SDP", "NYY"],
        "mlb_league": ["NL", "NL", "AL"],
        "position": ["SS", "OF", "RHP"],
        "player_type": ["batter", "batter", "pitcher"],
        "level": ["AA", "CPX", "A+"],
        "age": [21.4, 18.2, 22.0],
        "age_vs_level": [-1.8, 0.1, 0.4],
        "eta": [2027, 2030, 2028],
        "fv": [55.0, 40.0, None],
        "risk": ["High", "Extreme", None],
        "on_fangraphs_board": [True, True, False],
        "pipeline_overall_rank": [None, None, 63],
        "fv_pctile": [92.0, 30.0, None],
        "mle_score": [88.0, None, 61.0],
        "model_score": [86.0, 40.0, 61.0],
        "blend_score": [88.0, 33.0, 61.0],
        "disagreement": [17.5, None, -2.0],
        "disagreement_label": ["WE'RE HIGHER", "n/a (no MLE line)", "agree"],
        "speed_flag": ["SPEED — SB not in our MLE", "", ""],
        "in_majors": ["", "", ""],
        "mle_level": ["AA", None, None],
        "mle_pa": [430, None, None],
        "mle_k_pct": [0.221, None, None],
        "mle_k_pct_sd": [0.011, None, None],
        "mle_bb_pct": [0.094, None, None],
        "mle_iso": [0.168, None, None],
        "mle_p_gb_pct": [None, None, 0.512],
        "mle_p_k_pct": [None, None, 0.243],
        "comp_fp_median": [412.0, None, 130.0],
        "comp_names": ["Bo Bichette (0.04), Gleyber Torres (0.05)", None, "Some Arm (0.07)"],
        "comp_note": ["2 of 25 comps never reached MLB.", None, "14 of 25 never reached MLB."],
        "comp_quality": ["strong", "thin", "fair"],
        "comp_bust_rate": [0.08, None, 0.56],
        "comp_n_never_reached": [2, None, 14],
        "comp_rank_delta": [0, None, 3],
        "scouting_note": ["Advanced bat.", None, "Big fastball."],
        "mlbam_id": [111, 222, 333],
        "season": [2026.0, 2026.0, None],
        "as_of_date": ["2026-07-27", "2026-07-27", None],
    })


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The payload keeps the board's meaning
# ══════════════════════════════════════════════════════════════════════════════════════════════

class TestPayloadMeaning:
    def test_a_missing_projection_is_absent_not_zero(self):
        """🚨 THE ONE THAT MATTERS. A complex-league prospect has an identity and NO minor-league
        PA — that is expected, not a defect. Emitting 0 would render as *measured and terrible*,
        which is the opposite of what the blank means, and it would poison any client-side sort."""
        rows = exporter.build_players(_board())
        kid = next(r for r in rows if r["name"] == "Complex Kid")
        for key in ("mleK", "mleBb", "mleIso", "mleScore", "mlePa", "disagreement"):
            assert key not in kid, f"{key} was emitted for a player with no MLE line"
        # …and the row is still THERE. FV-only players stay on the board rather than being dropped.
        assert kid["rank"] == 2 and kid["league"] == "NL"

    def test_zero_is_preserved_where_it_is_a_real_measurement(self):
        """The inverse guard: `_clean` must not confuse "absent" with "zero". A genuine 0 (here a
        comp read that moved nobody) has to survive, or the omit-nulls rule has become a data
        filter."""
        rows = exporter.build_players(_board())
        bat = next(r for r in rows if r["name"] == "Real Bat")
        assert bat["compRankDelta"] == 0

    def test_the_al_nl_league_is_on_every_row(self):
        """Dynasty leagues are single-league, so `league` is a REQUIRED filter column — a row
        missing it silently vanishes from the only view the user actually drafts against."""
        rows = exporter.build_players(_board())
        assert {r["league"] for r in rows} == {"AL", "NL"}
        assert all("league" in r for r in rows)

    def test_a_board_missing_a_required_column_is_refused_not_published(self):
        board = _board().drop(columns=["mlb_league"])
        with pytest.raises(SystemExit, match="required by the app surface"):
            exporter.build_players(board)

    def test_the_season_comes_from_max_not_a_null_beating_statistic(self, tmp_path):
        """The ~165 MLB-Pipeline-only rows carry a NULL season (no board snapshot of their own).
        Any statistic a null can win would resolve the S3 key to nothing."""
        rep = exporter.export(_write_csv(tmp_path, _board()), tmp_path / "out")
        assert rep["season"] == 2026

    def test_pipeline_only_rows_are_carried_with_their_blanks_intact(self):
        """`onFgBoard: false` is the loudest disagreement two sources can produce, so the row is
        ADDED rather than dropped — and its FanGraphs columns are blank because there is no
        FanGraphs row, which the client can only say if the flag survives."""
        rows = exporter.build_players(_board())
        arm = next(r for r in rows if r["name"] == "Pipeline Arm")
        assert arm["onFgBoard"] is False
        assert "fv" not in arm and arm["pipelineOverallRank"] == 63


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The honest frame travels in the payload
# ══════════════════════════════════════════════════════════════════════════════════════════════

class TestHonestFrame:
    def test_the_framing_is_exported_not_left_to_the_frontend(self, tmp_path):
        """NF3's convention: the claim wording lives with the model that earned it, so it cannot
        drift out of sync with what was measured."""
        exporter.export(_write_csv(tmp_path, _board()), tmp_path / "out")
        manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
        framing = manifest["framing"]
        assert framing["byPosition"]["pitcher"] and framing["byPosition"]["batter"]
        assert framing["absences"] and framing["uncertainty"] and framing["comps"]

    def test_the_position_asymmetry_is_stated_in_both_directions(self):
        """E7.8's verdict IS the product: FV leads for arms (it complements), our line leads for
        bats (FV substitutes). A framing block that only carried one half would read as a blanket
        'trust the scouts' or a blanket 'trust us' — both of which the measurement contradicts."""
        assert "FV" in exporter.FRAMING["byPosition"]["pitcher"]
        assert exporter.FRAMING["byPosition"]["pitcher"].startswith("LEAD WITH FV")
        assert exporter.FRAMING["byPosition"]["batter"].startswith("LEAD WITH OUR LINE")

    def test_no_claim_to_beat_the_scouts_anywhere_in_the_framing(self):
        """`best_alpha = 0`. This surface never claims an edge, a win rate, or superiority over
        FanGraphs — checked over the WHOLE framing block, not just the headline.

        ⚠️ Matching on the BARE terms ("win-rate", "edge") would be inverted: the disclaimer itself
        contains them ("no edge or win-rate claim is made or implied"), so a bare-substring guard
        fails on correct copy and passes on copy that has merely dropped the disclaimer. Match the
        AFFIRMATIVE forms, and assert the disclaimer is present separately."""
        blob = json.dumps(exporter.FRAMING).lower()
        assert "does not claim to beat" in blob
        assert "no edge or win-rate claim" in blob
        for forbidden in ("beats fangraphs", "beat fangraphs by", "outperform", "our edge is",
                          "win rate of", "more accurate than fangraphs"):
            assert forbidden not in blob, f"framing carries a {forbidden!r} claim"

    def test_woba_is_absent_and_stays_absent(self):
        """wOBA is a MEASURED NULL for hitter translation (corr 0.22 — no better than knowing the
        player's level). It must never reappear as a column: shipping it would launder a null into
        a ranking. The absence is stated in the framing so a future surface knows it is deliberate."""
        assert not any(key.lower().startswith("mlewoba") for _, key, _ in exporter._COLUMNS)
        assert any("wOBA" in a for a in exporter.FRAMING["absences"])

    def test_the_stolen_base_blind_spot_is_stated(self):
        """SB is structurally invisible to every metric we translate, so a speed-first prospect is
        systematically under-served by our score. Saying so is the only honest option."""
        assert any("STOLEN BASES" in a for a in exporter.FRAMING["absences"])
        assert any(key == "speedFlag" for _, key, _ in exporter._COLUMNS)

    def test_a_missing_line_is_explained_by_its_two_real_causes(self):
        """🚨 THE COPY THAT WAS WRONG, now pinned (operator-reported, 2026-08-02).

        The original wording told a user a blank line meant the player had "no minor-league record
        to translate". True for complex/DSL, and FALSE for the case that actually got noticed:
        Josuar González (26 PA), Luis Hernández (33 PA), Dax Kilby (120 PA) and Trey Yesavage (a
        pitcher split across four levels) all have Single-A-or-higher records and sit blank because
        they are under E7.3's `min_minor_pa = 150` floor. Two causes ⇒ two strings, and the
        thin-sample one must NOT claim an absence of data."""
        no_line = exporter.FRAMING["noLine"]
        assert set(no_line) == {"complex", "thinSample"}
        assert "150" in no_line["thinSample"] or str(exporter.FRAMING["minSample"]) == "150"
        # the thin-sample case must say he HAS a record — the exact thing the old copy denied
        assert "has a professional record" in no_line["thinSample"]
        # …and the complex case must be about SCOPE, not sample size
        assert "Single-A through Triple-A" in no_line["complex"]

    def test_the_covered_levels_are_declared_so_the_ui_owns_no_threshold(self):
        """The UI picks WHICH no-line reason to show by testing the row's level against this list.
        Declaring it here keeps the level vocabulary and the 150 floor in one place — the exporter,
        beside the model that set them — rather than hard-coded in a component."""
        assert exporter.FRAMING["mleLevels"] == ["A", "A+", "AA", "AAA", "MLB"]
        assert "CPX" not in exporter.FRAMING["mleLevels"]
        assert "DSL" not in exporter.FRAMING["mleLevels"]
        assert exporter.FRAMING["minSample"] == 150

    def test_the_weak_metrics_are_marked_weak(self):
        """E7.3/E7.3p: batter K%/BB% (0.64/0.49) and pitcher GB% (0.55) are strong; ISO (0.43) and
        pitcher K%/BB% (~0.37) are weak-but-real. The UI demotes them off THIS map, so an inverted
        entry here would present a weak number as a confident one."""
        conf = exporter.FRAMING["metricConfidence"]
        assert conf["mleK"] == "strong" and conf["mleBb"] == "strong" and conf["mlePGb"] == "strong"
        assert conf["mleIso"] == "weak" and conf["mlePK"] == "weak" and conf["mlePBb"] == "weak"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The serving path — gated, and reading the MLB key space
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def staged_board(tmp_path, monkeypatch):
    out = tmp_path / "2026"
    out.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({"season": 2026, "players": 3}))
    (out / "board.json").write_text(json.dumps({"season": 2026, "players": [{"rank": 1}]}))
    monkeypatch.setenv("MLB_FANTASY_BOARD_DIR", str(tmp_path))
    return tmp_path


class TestServingPath:
    def test_the_endpoints_serve_the_staged_board(self, staged_board):
        assert fantasy.mlb_prospect_manifest(season=2026)["players"] == 3
        assert fantasy.mlb_prospect_board(season=2026)["players"] == [{"rank": 1}]

    def test_a_missing_season_404s_rather_than_serving_an_empty_board(self, staged_board):
        """An empty result must never be served as if it were a board (the E9.26b silent-zero
        shape) — a miss is a 404, which the client renders as an honest empty state."""
        for fn in (fantasy.mlb_prospect_manifest, fantasy.mlb_prospect_board):
            with pytest.raises(HTTPException) as exc:
                fn(season=2019)
            assert exc.value.status_code == 404

    def test_the_board_is_admin_only_while_in_development(self):
        """🔒 ADMIN ONLY (operator, 2026-08-02) — the STRICTEST gate in the codebase, and the
        assertion that matters most here.

        The router-level `require_fantasy_access` grants `subscriber` OR `admin` OR `fantasy_comp`,
        which is correct for the shipped NFL routes it is shared with and WRONG for an
        in-development surface: it would expose the board to every paying subscriber. Even
        `require_fantasy_beta_access` (`admin` + `fantasy_comp`) is too wide. So each MLB route must
        additionally depend on `get_admin_user` — checked PER ROUTE, because the router-level
        dependency cannot express a rule narrower than its other routes need."""
        by_path = {r.path: r for r in fantasy.router.routes}
        for path in ("/fantasy/mlb/prospects/board", "/fantasy/mlb/prospects/manifest"):
            assert path in by_path, f"{path} is not registered"
            route_deps = [d.call for d in by_path[path].dependant.dependencies]
            assert deps.get_admin_user in route_deps, (
                f"{path} is NOT admin-only — it would be readable by every paying subscriber"
            )
        # …and the router-level fantasy gate still applies underneath (defence in depth).
        assert deps.require_fantasy_access in [d.dependency for d in fantasy.router.dependencies]

    def test_the_nfl_routes_did_not_get_the_admin_gate_by_accident(self):
        """The inverse. `get_admin_user` was added PER ROUTE precisely so the shipped NFL board
        endpoints stay open to subscribers — pinning that keeps a future 'tidy-up' from hoisting it
        to the router and silently locking paying users out of a product they bought."""
        by_path = {r.path: r for r in fantasy.router.routes}
        for path in ("/fantasy/nfl/board", "/fantasy/nfl/projections", "/fantasy/nfl/manifest"):
            route_deps = [d.call for d in by_path[path].dependant.dependencies]
            assert deps.get_admin_user not in route_deps, f"{path} became admin-only"
        assert deps.get_admin_user not in [d.dependency for d in fantasy.router.dependencies]

    def test_the_reads_hit_the_mlb_key_space_not_nfl(self, monkeypatch):
        """A shared bucket makes a wrong prefix a data-mixing bug that still returns 200. Pin that
        `sport="mlb"` actually reaches `fantasy/mlb/...`."""
        seen: list[str] = []
        monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", None)
        monkeypatch.setenv("MLB_FANTASY_BOARD_DIR", "")
        monkeypatch.setattr(fantasy, "_CACHE_BUCKET", "bucket")

        class _S3:
            def get_object(self, Bucket, Key):  # noqa: N803 - boto3's own kwarg names
                seen.append(Key)
                raise KeyError("miss")

        monkeypatch.setattr(fantasy, "_s3", _S3())
        with pytest.raises(Exception):
            fantasy.mlb_prospect_board(season=2026)
        assert seen == ["fantasy/mlb/2026/board.json"]

    def test_the_sport_parameter_is_additive_and_defaults_to_nfl(self, tmp_path, monkeypatch):
        """`_load_json` is shared with `fantasy_public.py` and every NFL route. Adding `sport` must
        not change a single existing caller's behaviour (NF-C0: additive only)."""
        monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", None)
        monkeypatch.setattr(fantasy, "_CACHE_BUCKET", "bucket")
        seen: list[str] = []

        class _S3:
            def get_object(self, Bucket, Key):  # noqa: N803
                seen.append(Key)
                raise KeyError("miss")

        monkeypatch.setattr(fantasy, "_s3", _S3())
        with pytest.raises(Exception):
            fantasy._load_json("2026/manifest.json")
        assert seen == ["fantasy/nfl/2026/manifest.json"]

    def test_the_mlb_local_dir_does_not_hijack_the_nfl_one(self, tmp_path, monkeypatch):
        """Local backend dev reads a directory per sport. Sharing one would make an NFL board
        answer an MLB request (and vice versa) with a perfectly plausible 200."""
        (tmp_path / "2026").mkdir()
        (tmp_path / "2026" / "manifest.json").write_text(json.dumps({"iam": "nfl"}))
        monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
        monkeypatch.delenv("MLB_FANTASY_BOARD_DIR", raising=False)
        monkeypatch.setattr(fantasy, "_CACHE_BUCKET", None)
        with pytest.raises(HTTPException) as exc:
            fantasy.mlb_prospect_manifest(season=2026)
        # 503 (store not configured), NOT the NFL blob served as an MLB board.
        assert exc.value.status_code == 503


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The publish guard + the response-size ceiling
# ══════════════════════════════════════════════════════════════════════════════════════════════

class TestPublishGuard:
    def test_publish_with_no_bucket_raises_rather_than_silently_staging(self, tmp_path):
        """🚨 NF1.7 cost a real publish to exactly this: `--publish` degraded to a local-stage
        WARNING buried in the log, and the run looked successful while nothing reached users. An
        operator who explicitly asks for an outward-facing action must never get a silent no-op."""
        with pytest.raises(SystemExit, match="NO BUCKET resolved"):
            exporter._maybe_publish(tmp_path, None, 2026, publish=True)

    def test_a_resolved_bucket_alone_is_a_dry_run(self, tmp_path, monkeypatch):
        """NF-D12: `$CACHE_BUCKET` is set in the operator's normal env, so a bucket must not be
        enough to reach prod — a re-export session would publish on every run."""
        (tmp_path / "board.json").write_text("{}")
        called: list[str] = []
        monkeypatch.setattr("boto3.client", lambda *a, **k: called.append("s3"))
        exporter._maybe_publish(tmp_path, "credence-prod-s3-api-cache", 2026, publish=False)
        assert called == []

    def test_the_upload_targets_the_mlb_prefix(self):
        assert exporter.S3_PREFIX == "fantasy/mlb"


class TestResponseSizeCeiling:
    def test_a_board_past_the_bound_fails_the_export_not_the_surface(self):
        """AWS Lambda hard-caps a proxy response at 6 MB and this API has no gzip middleware, so an
        oversized board is a 502 on a PAID surface. Fail the export, where the cause is obvious."""
        with pytest.raises(SystemExit, match="SPLIT the payload"):
            exporter.check_response_size(exporter._SIZE_FAIL_BYTES + 1)

    def test_the_bound_sits_under_the_aws_cap(self):
        assert exporter._SIZE_WARN_BYTES < exporter._SIZE_FAIL_BYTES < 6 * 1024 * 1024

    def test_a_normal_board_passes(self, tmp_path):
        exporter.export(_write_csv(tmp_path, _board()), tmp_path / "out")  # must not raise


def _write_csv(tmp_path, board: pd.DataFrame):
    path = tmp_path / "board.csv"
    board.to_csv(path, index=False)
    return path


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The nav wiring
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# There is no JS test runner in this repo, so `tsc --noEmit` + `next build` are the frontend gate —
# and neither of them can see this class of bug: `nav-model.ts`'s own header says `key` values MUST
# match the `activeLink` prop each page passes, and a mismatch type-checks, builds, renders, and just
# silently stops highlighting the active tab. A source read is the available instrument.

_FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"


def _mlb_nav_block(strip_comments: bool = True) -> str:
    """Just the MLB sport entry of `SPORTS`, with `//` comment lines removed by default.

    ⚠️ BOTH halves of this are load-bearing, and both were caught by this test failing:
      * scoped from `sport: "mlb"` (not the top of the file) because the `NavItem` interface above
        the array names every `restrict` value in its own doc comment;
      * COMMENTS STRIPPED because the explanatory comment above the MLB items itself contains the
        literal `restrict: "admin"`, which inflated a count-based assertion from 2 to 3. That is the
        INC-38 "prose can satisfy a source guard" hazard facing the other way — a source-inspection
        test must match CODE, never the commentary about it.
    """
    nav = (_FRONTEND / "lib/nav-model.ts").read_text(encoding="utf-8")
    block = nav[nav.index('sport: "mlb"'):nav.index('sport: "nfl"')]
    if not strip_comments:
        return block
    return "\n".join(ln for ln in block.splitlines() if not ln.strip().startswith("//"))


class TestNavWiring:
    def test_the_mlb_fantasy_surface_is_declared(self):
        """E9.45's nav is sport-first with only the (sport × surface) combos that EXIST declared.
        E8.1 is the first MLB→Fantasy surface, so it has to be added there or the pages are
        unreachable from the nav even though they build and route fine."""
        mlb_block = _mlb_nav_block()
        assert 'surface: "fantasy"' in mlb_block, "MLB has no Fantasy surface in the nav model"
        assert "/fantasy/mlb/prospects" in mlb_block
        assert "/fantasy/mlb/disagreements" in mlb_block

    @pytest.mark.parametrize(
        "page,key",
        [("app/fantasy/mlb/prospects/page.tsx", "mlb-prospects"),
         ("app/fantasy/mlb/disagreements/page.tsx", "mlb-disagreements")],
    )
    def test_each_page_activelink_matches_its_nav_key(self, page, key):
        nav = (_FRONTEND / "lib/nav-model.ts").read_text(encoding="utf-8")
        src = (_FRONTEND / page).read_text(encoding="utf-8")
        assert f'key: "{key}"' in nav, f"{key} is not a nav key"
        assert f'activeLink="{key}"' in src, f"{page} does not pass activeLink={key}"

    def test_the_mlb_fantasy_items_are_admin_restricted(self):
        """🔒 The nav mirror of the server gate. `restrict: "admin"` — NOT `"fantasy_beta"`, which
        would also show the items to `fantasy_comp` accounts. Cosmetic (the API is the real gate),
        but a nav item pointing at a route that 403s is its own bug."""
        mlb_block = _mlb_nav_block()
        # ⚠️ Asserted as "EVERY item", not as a magic count. A hard-coded 2 made this fail for the
        # WRONG reason the moment E8.2 added a third (correctly restricted) item — a guard that
        # goes red on a compliant change trains people to edit the guard instead of the code.
        items = mlb_block.count('href: "/fantasy/mlb')
        assert items >= 2, "the MLB fantasy nav items disappeared — this assertion would be vacuous"
        assert mlb_block.count('restrict: "admin"') == items, (
            "every MLB fantasy nav item must be admin-restricted while the surface is in development"
        )
        assert 'restrict: "fantasy_beta"' not in mlb_block

    @pytest.mark.parametrize(
        "page", ["app/fantasy/mlb/prospects/page.tsx", "app/fantasy/mlb/disagreements/page.tsx"],
    )
    def test_each_page_uses_the_admin_guard_not_the_fantasy_guard(self, page):
        """The page-level mirror. `FantasyGuard` would let any subscriber render the surface and
        then watch every fetch 403 — a worse experience than not showing it at all."""
        src = (_FRONTEND / page).read_text(encoding="utf-8")
        assert "<AdminGuard>" in src
        assert "<FantasyGuard>" not in src

    def test_the_prospect_hooks_refuse_to_issue_the_request_for_a_non_admin(self):
        """The hooks must not merely hide the result — an unentitled caller should never ISSUE the
        gated request at all (the NF3.2 rule), and here the predicate has to be `isAdmin` rather
        than the fantasy one or every subscriber fires a request that 403s."""
        src = (_FRONTEND / "lib/fantasy-queries.ts").read_text(encoding="utf-8")
        mlb = src[src.index("E8.1 — MLB dynasty PROSPECT BOARD"):]
        # ⚠️ COMMENTS STRIPPED, for the same reason `_mlb_nav_block` strips them: E8.2's explanatory
        # comment contains the literal `enabled: isAdmin`, which inflated this count from 2 to 5
        # while every hook was in fact correct. A source-inspection guard must match CODE, never the
        # prose about it (INC-38). And asserted as "EVERY query", not a magic number, so a new gated
        # hook cannot fail this for the wrong reason.
        code = "\n".join(ln for ln in mlb.splitlines() if not ln.lstrip().startswith("//"))
        queries = code.count("useQuery<")
        assert queries >= 2, "no MLB queries found — this assertion would be vacuous"
        assert code.count("enabled: isAdmin") == queries, (
            "every MLB fantasy query hook must gate on isAdmin, so an unentitled caller never "
            "issues a request that would 403"
        )
        assert 'enabled: canAccess("fantasy", groups)' not in code

    def test_a_surface_whose_items_are_all_hidden_does_not_render(self):
        """🐛 The bug this pairs with: for an entitled NON-admin the MLB→Fantasy surface is not
        LOCKED (they do have fantasy) but every item is filtered away — which would draw a bare
        "FANTASY" heading with nothing under it. `visibleSurfaces` drops the whole group."""
        nav = (_FRONTEND / "components/nav.tsx").read_text(encoding="utf-8")
        assert "const visibleSurfaces" in nav
        assert nav.count("visibleSurfaces(sport).map") == 2, (
            "both the desktop and mobile sub-navs must filter empty surface groups"
        )
        assert "{sport.surfaces.map" not in nav

    def test_the_mlb_fantasy_items_are_not_marked_public(self):
        """🔒 `public: true` keeps a nav item visible when its surface is LOCKED — correct for NF3.2's
        genuinely-public track record, WRONG here: the current-season board is the paid product
        (E9.56). Marking it public would advertise a route that 403s."""
        assert "public: true" not in _mlb_nav_block()
