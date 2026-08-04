"""Fast-gate tests for NF-C0b — the MANUAL league-settings editor (the customization FLOOR).

Three things have to hold for this story, and each is a section below.

1. HONEST COVERAGE IS MECHANICAL. A real league scores stats we do not project. The scorer treats a
   missing column as a zero term, so such a setting would be accepted and then silently score
   nothing. `resolve_scoring` must classify every term against the projection columns that ACTUALLY
   exist, and a term must never be able to reach "applied" without a column behind it.

2. THERE IS ONE SCHEMA, NOT TWO. The editor's TS mirror (`frontend/lib/league-config.ts`) and the
   backend's Pydantic models restate the Python contract. The whole point of the story is that a
   hand-entered league and an imported one produce the IDENTICAL object, so a second schema that
   quietly diverges is the one failure mode that would defeat it. These tests parse the TS source and
   compare it term-by-term against the Python catalog — the same guard-the-drift-prone-part approach
   `draft-optimizer.ts` already relies on.

3. THE CONFIG STILL ROUND-TRIPS. `captured_rules` is new on `LeagueConfig`; a config carrying it must
   survive `to_dict`/`from_dict` unchanged, and the engine must never read it.

Fast-gate discipline: pure imports (`fantasy_engine` + presets + the backend MODELS, which are plain
pydantic), no `pipeline`, no IO beyond reading the TS source as text.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

lc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.league_config")
settings = pytest.importorskip("quant_sports_intel_models.fantasy_engine.settings")
presets = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.league_presets")

REPO = Path(__file__).resolve().parents[2]
TS_CONFIG = REPO / "frontend" / "lib" / "league-config.ts"

APPLIED, DERIVED, CAPTURED = settings.APPLIED, settings.DERIVED, settings.CAPTURED


def _config(**overrides):
    base = dict(
        name="test league",
        sport="nfl",
        n_teams=12,
        scoring=lc.ScoringRules(per_stat=presets.default_custom_scoring()),
        roster=presets.default_custom_roster(),
        ppr="custom",
    )
    base.update(overrides)
    return lc.LeagueConfig(**base).validate()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. HONEST COVERAGE — applied / derived / captured, decided by the data
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestCoverageIsMechanical:
    def test_a_stat_with_no_projection_column_is_captured_not_applied(self):
        """The core honesty guarantee: a league scores it, we do not project it, and we SAY so.

        Without this the term scores 0 behind an 'applied' label — a number that looks like it
        honoured the user's league and does not.

        NF-C0e swapped this test's UNPROJECTED EXAMPLE, which is worth saying out loud: it used to
        use `def_forced_fumble`, and that term now has a real column (it cleared a held-out
        degenerate-baseline gate in 16/16 seasons), so it is legitimately APPLIED. The examples
        below are the terms NF-C0e tested and DELIBERATELY LEFT CAPTURED — `pat_missed` failed its
        gate (8/16 folds, +0.21%) and `st_player_td` has no per-player predictor at all, so the only
        arm constructible for it IS the degenerate. Using a still-unprojected example keeps this
        guard about the MECHANISM rather than about one term's status.
        """
        scoring = lc.ScoringRules(per_stat={"rec": 1.0, "pat_missed": -1.0, "st_player_td": 6.0})
        _, report = settings.resolve_scoring(scoring, presets.NFL_PROFILE)
        verdicts = {t.key: t.verdict for t in report.terms}
        assert verdicts["rec"] == APPLIED
        assert verdicts["pat_missed"] == CAPTURED
        assert verdicts["st_player_td"] == CAPTURED

    def test_a_column_missing_from_the_data_downgrades_to_captured(self):
        """Coverage reads the REAL columns, not the profile's intent.

        A projection that loses a column must degrade honestly rather than keep claiming the term is
        applied — the mechanical half of the guarantee (cf. the repo's 'a tier label enforced only by
        a docstring is not enforced at all').
        """
        scoring = lc.ScoringRules(per_stat={"rec": 1.0, "def_sacks": 1.0})
        available = frozenset({"proj_rec"})  # def_sacks' column absent from this frame
        _, report = settings.resolve_scoring(scoring, presets.NFL_PROFILE, available_columns=available)
        verdicts = {t.key: t.verdict for t in report.terms}
        assert verdicts["rec"] == APPLIED
        assert verdicts["def_sacks"] == CAPTURED

    def test_a_captured_term_contributes_nothing_to_the_score(self):
        """'Captured' has to mean it genuinely does not move the board."""
        pd = pytest.importorskip("pandas")
        sc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.scoring")

        row = {c: 0.0 for c in presets.NFL_PROFILE.stat_columns.values()}
        row["position"] = "WR"
        row["proj_rec"] = 100.0
        df = pd.DataFrame([row])

        with_capture = _config(
            scoring=lc.ScoringRules(per_stat={"rec": 1.0, "def_forced_fumble": 99.0})
        )
        resolved, _ = presets.resolve_config(with_capture)
        scored = sc.score_players(df, resolved, presets.NFL_PROFILE, with_interval=False)
        assert scored["league_points"].iloc[0] == pytest.approx(100.0)

    def test_identical_fg_sub_buckets_fold_exactly(self):
        """The common real-world case — most leagues pay the same for a 22- and a 35-yarder — must
        be EXACT, with the nominal attempt shares never entering the arithmetic."""
        scoring = lc.ScoringRules(
            per_stat={"fg_made_0_19": 3.0, "fg_made_20_29": 3.0, "fg_made_30_39": 3.0}
        )
        resolved, report = settings.resolve_scoring(
            scoring, presets.NFL_PROFILE, derived_buckets=presets.FG_DERIVED_BUCKETS
        )
        assert resolved.per_stat["fg_made_0_39"] == pytest.approx(3.0)
        assert all(t.exact for t in report.by_verdict(DERIVED))
        assert report.has_approximation is False

    def test_divergent_fg_sub_buckets_are_flagged_approximate(self):
        """When a league genuinely prices sub-buckets apart we combine them — and must SAY it is an
        approximation rather than implying a resolution the projection does not have."""
        scoring = lc.ScoringRules(
            per_stat={"fg_made_0_19": 3.0, "fg_made_20_29": 3.0, "fg_made_30_39": 4.0}
        )
        resolved, report = settings.resolve_scoring(
            scoring, presets.NFL_PROFILE, derived_buckets=presets.FG_DERIVED_BUCKETS
        )
        assert report.has_approximation is True
        # weighted by the declared shares: (3*.02 + 3*.30 + 4*.68) / 1.0
        assert resolved.per_stat["fg_made_0_39"] == pytest.approx(3.68)
        # and it must stay INSIDE the range it combines — never extrapolate past the user's values
        assert 3.0 <= resolved.per_stat["fg_made_0_39"] <= 4.0

    def test_points_allowed_tiers_are_applied_exactly(self):
        """A hand-entered D/ST tier table must be APPLIED, not approximated: the projection's nine
        expected-games columns make the tier table linear, so it is expressible exactly."""
        scoring = lc.ScoringRules(per_stat={f"dst_pa_g_{b}": 1.0 for b in
                                            ("0", "1_6", "7_13", "14_17", "18_20", "21_27",
                                             "28_34", "35_45", "46p")})
        _, report = settings.resolve_scoring(scoring, presets.NFL_PROFILE)
        assert {t.verdict for t in report.terms} == {APPLIED}

    def test_seven_tier_league_table_restates_exactly_over_nine_buckets(self):
        """The story's tier list (0/1-6/7-13/14-20/21-27/28-34/35+) is an exact union of our nine,
        which is why the editor can offer it without any approximation."""
        merge_groups = {t.merge_group for t in presets.SCORING_CATALOG if t.merge_group}
        assert merge_groups == {"pa_14_20", "pa_35p"}
        for group, expected in (("pa_14_20", {"dst_pa_g_14_17", "dst_pa_g_18_20"}),
                                ("pa_35p", {"dst_pa_g_35_45", "dst_pa_g_46p"})):
            assert {t.key for t in presets.SCORING_CATALOG if t.merge_group == group} == expected

    def test_every_catalog_term_is_classified(self):
        """No term may fall out of the report silently — a setting the user can type must always get
        a verdict (or be a deliberate zero)."""
        cfg = _config()
        _, report = presets.resolve_config(cfg)
        reported = {t.key for t in report.terms}
        zeroed = {t.key for t in presets.SCORING_CATALOG if t.default == 0.0}
        fine = {b.fine_key for b in presets.FG_DERIVED_BUCKETS}
        for term in presets.SCORING_CATALOG:
            if term.key in zeroed and term.key not in fine:
                continue
            assert term.key in reported, f"{term.key} got no coverage verdict"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ONE SCHEMA — the TS editor mirror may not drift from the Python catalog
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ts_source() -> str:
    assert TS_CONFIG.is_file(), f"missing {TS_CONFIG}"
    return TS_CONFIG.read_text()


def _ts_catalog() -> dict[str, float]:
    """Parse `SCORING_CATALOG` out of the TS source → {key: default}."""
    src = _ts_source()
    block = re.search(r"export const SCORING_CATALOG: StatTerm\[\] = \[(.*?)\n\]", src, re.S)
    assert block, "could not locate SCORING_CATALOG in league-config.ts"
    out: dict[str, float] = {}
    for entry in re.finditer(r"\{\s*key:\s*\"([a-z0-9_]+)\".*?default:\s*(-?[\d.]+)", block.group(1), re.S):
        out[entry.group(1)] = float(entry.group(2))
    return out


class TestTsMirrorMatchesPython:
    """The editor writes the shared contract, so its term list and defaults must BE the Python ones.

    Drift here is the failure the story exists to prevent: two settings schemas that look the same
    and score differently, so an imported config and a hand-entered one stop being interchangeable.
    """

    def test_catalog_keys_match(self):
        ts = _ts_catalog()
        py = {t.key: float(t.default) for t in presets.SCORING_CATALOG}
        assert set(ts) == set(py), (
            f"TS/Python catalog drift — only in TS: {sorted(set(ts) - set(py))}; "
            f"only in Python: {sorted(set(py) - set(ts))}"
        )

    def test_catalog_defaults_match(self):
        ts, py = _ts_catalog(), {t.key: float(t.default) for t in presets.SCORING_CATALOG}
        mismatched = {k: (py[k], ts[k]) for k in py if abs(py[k] - ts[k]) > 1e-9}
        assert not mismatched, f"default drift (python, ts): {mismatched}"

    def test_stat_field_map_covers_the_same_projected_keys(self):
        """`STAT_FIELD` is the TS analog of `NFL_PROFILE.stat_columns` — the map that decides which
        terms can be APPLIED. If it drifts, the browser and the Python engine disagree about what is
        projected, which is exactly a coverage lie."""
        src = _ts_source()
        block = re.search(r"export const STAT_FIELD: Record<string, string> = \{(.*?)\n\}", src, re.S)
        assert block, "could not locate STAT_FIELD in league-config.ts"
        ts_keys = set(re.findall(r"(\w+):\s*\"", block.group(1)))
        py_keys = set(presets.NFL_PROFILE.stat_columns)
        assert ts_keys == py_keys, (
            f"STAT_FIELD drift — only in TS: {sorted(ts_keys - py_keys)}; "
            f"only in Python: {sorted(py_keys - ts_keys)}"
        )

    def test_fg_derived_buckets_match(self):
        src = _ts_source()
        block = re.search(r"export const FG_DERIVED_BUCKETS: DerivedBucket\[\] = \[(.*?)\n\]", src, re.S)
        assert block, "could not locate FG_DERIVED_BUCKETS in league-config.ts"
        ts = {
            m.group(1): (m.group(2), float(m.group(3)))
            for m in re.finditer(
                r"fineKey:\s*\"(\w+)\",\s*projectedKey:\s*\"(\w+)\",\s*share:\s*([\d.]+)",
                block.group(1),
            )
        }
        py = {b.fine_key: (b.projected_key, float(b.share)) for b in presets.FG_DERIVED_BUCKETS}
        assert ts.keys() == py.keys(), f"FG fold drift: ts={sorted(ts)} py={sorted(py)}"
        for k, (proj, share) in py.items():
            assert ts[k][0] == proj, f"{k} folds onto {ts[k][0]} in TS but {proj} in Python"
            assert abs(ts[k][1] - share) < 1e-9, f"{k} share drift: ts={ts[k][1]} py={share}"

    def test_entitlement_group_list_matches_the_server(self):
        """The client gate is a MIRROR of the server rule, not a second policy.

        `frontend/lib/entitlements.ts::FANTASY_BETA_GROUPS` decides whether the nav item and
        page render; `cognito.FANTASY_BETA_GROUPS` decides whether the API answers. If they
        drift, the visible product and the enforced product disagree — either a user sees an
        editor that 403s on save, or (worse) the nav hides a surface the API would serve.
        """
        ts_src = (REPO / "frontend" / "lib" / "entitlements.ts").read_text()
        block = re.search(r"const FANTASY_BETA_GROUPS = \[(.*?)\] as const", ts_src, re.S)
        assert block, "could not locate FANTASY_BETA_GROUPS in entitlements.ts"
        ts_groups = set(re.findall(r"\"(\w+)\"", block.group(1)))

        cognito = pytest.importorskip("app.backend.services.cognito")
        assert ts_groups == set(cognito.FANTASY_BETA_GROUPS), (
            f"client/server entitlement drift — ts={sorted(ts_groups)} "
            f"server={sorted(cognito.FANTASY_BETA_GROUPS)}"
        )
        assert "subscriber" not in ts_groups

    def test_the_league_settings_nav_item_is_restricted(self):
        """The nav entry must carry `restrict: "fantasy_beta"`.

        Without it the item renders for every subscriber and links to a page that bounces them
        — a broken-looking nav rather than a staged rollout.
        """
        nav_src = (REPO / "frontend" / "lib" / "nav-model.ts").read_text()
        entry = re.search(
            r"\{\s*label:\s*\"My League Settings\".*?\}", nav_src, re.S
        )
        assert entry, "My League Settings nav item not found"
        assert 'restrict: "fantasy_beta"' in entry.group(0)

    def test_captured_rule_catalog_matches(self):
        src = _ts_source()
        block = re.search(r"export const CAPTURED_RULE_CATALOG.*?= \[(.*?)\n\]", src, re.S)
        assert block, "could not locate CAPTURED_RULE_CATALOG in league-config.ts"
        ts_keys = set(re.findall(r"key:\s*\"(\w+)\"", block.group(1)))
        py_keys = {k for k, _label, _help in presets.CAPTURED_RULE_CATALOG}
        assert ts_keys == py_keys


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. THE SHARED CONTRACT — round-trip + captured_rules are inert + IR/multi-flex are representable
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestSharedContract:
    def test_config_with_captured_rules_round_trips(self):
        cfg = _config(captured_rules={"median_scoring": True, "playoff_weeks": 3})
        assert lc.LeagueConfig.from_dict(json.loads(json.dumps(cfg.to_dict()))) == cfg

    def test_captured_rules_never_reach_the_scorer(self):
        """A captured rule is a record of the league, not an input. Two configs differing ONLY in
        `captured_rules` must score byte-identically — the structural guarantee that median scoring
        cannot leak into a projection."""
        pd = pytest.importorskip("pandas")
        sc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.scoring")
        row = {c: 0.0 for c in presets.NFL_PROFILE.stat_columns.values()}
        row["position"] = "WR"
        row["proj_rec"] = 80.0
        df = pd.DataFrame([row])

        plain = _config()
        with_rules = _config(captured_rules={"median_scoring": True})
        a = sc.score_players(df, plain, presets.NFL_PROFILE, with_interval=False)["league_points"]
        b = sc.score_players(df, with_rules, presets.NFL_PROFILE, with_interval=False)["league_points"]
        assert list(a) == list(b)

    def test_ir_slot_is_representable_and_adds_no_starter_demand(self):
        """IR needed no schema change — it is a bench slot. The load-bearing property is that it
        contributes NO starter demand, so it cannot move replacement level (an IR spot never starts)."""
        roster = presets.default_custom_roster()
        ir = [s for s in roster if s.name == "IR"]
        assert ir and ir[0].bench and ir[0].count == 3
        cfg = _config(roster=roster)
        without_ir = _config(roster=tuple(s for s in roster if s.name != "IR"))
        assert cfg.dedicated_demand() == without_ir.dedicated_demand()
        assert cfg.flex_slot_specs() == without_ir.flex_slot_specs()

    def test_bench_slot_may_have_no_eligible_positions(self):
        """'IR: any position' must be storable — validate() only requires STARTERS to declare one."""
        _config(roster=(lc.RosterSlot("QB", 1, ("QB",)), lc.RosterSlot("IR", 2, (), bench=True)))

    def test_multi_count_flex_is_representable(self):
        """The operator's screenshot has TWO W/R/T flex slots."""
        cfg = _config(roster=(
            lc.RosterSlot("QB", 1, ("QB",)),
            lc.RosterSlot("FLEX", 2, ("RB", "WR", "TE")),
        ))
        specs = cfg.flex_slot_specs()
        assert specs == [(frozenset({"RB", "WR", "TE"}), 2 * cfg.n_teams)]

    @pytest.mark.parametrize(
        "preset_name,rec_value", [("standard", 0.0), ("half_ppr", 0.5), ("full_ppr", 1.0)]
    )
    def test_starting_from_a_preset_reproduces_that_preset_exactly(self, preset_name, rec_value):
        """"Start from a preset, then edit" must actually START from the preset.

        The editor seeds from the CATALOG (which spells field goals in the league's six distance
        buckets) while the shipped presets spell them in the projection's three. If the fold did not
        land back on the preset's own weights, a user who picked "full PPR" and changed nothing would
        silently get a DIFFERENT board than the shipped full-PPR one — the subtlest possible way for
        the two paths to stop being interchangeable.
        """
        scoring = presets.default_custom_scoring()
        scoring["rec"] = rec_value
        editor_cfg = _config(scoring=lc.ScoringRules(per_stat=scoring))
        resolved, _ = presets.resolve_config(editor_cfg)

        preset = presets.get_preset(preset_name, 12)
        for key, expected in preset.scoring.per_stat.items():
            assert resolved.scoring.per_stat.get(key, 0.0) == pytest.approx(expected), (
                f"{preset_name}: editor-from-preset gives {key}="
                f"{resolved.scoring.per_stat.get(key)} but the preset says {expected}"
            )

    def test_a_config_with_no_starters_is_rejected(self):
        with pytest.raises(ValueError):
            lc.LeagueConfig(
                name="bench only", sport="nfl", n_teams=12,
                scoring=lc.ScoringRules(per_stat={"rec": 1.0}),
                roster=(lc.RosterSlot("BN", 5, ("WR",), bench=True),),
            ).validate()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. THE API MODELS — same accept/reject as LeagueConfig.validate(), and read is not gated by write
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestLeagueCrud:
    """A user must be able to CREATE, UPDATE and DELETE their own leagues — and only their own.

    Exercised against a minimal fake table rather than mocked at the function boundary, so the
    actual UpdateExpressions are executed: the store writes a SINGLE map entry (`SET #fl.#id`) so
    two tabs saving different leagues cannot clobber each other, and that only works if the parent
    map is created first. Mocking the table object would assert nothing about either.
    """

    @staticmethod
    def _fake_table():
        class FakeTable:
            def __init__(self):
                self.items: dict[str, dict] = {}

            def get_item(self, Key):  # noqa: N803
                item = self.items.get(Key["user_id"])
                return {"Item": item} if item is not None else {}

            def update_item(self, Key, UpdateExpression, ExpressionAttributeNames=None,  # noqa: N803
                            ExpressionAttributeValues=None, ConditionExpression=None):
                names = ExpressionAttributeNames or {}
                values = ExpressionAttributeValues or {}
                item = self.items.setdefault(Key["user_id"], {})
                expr = " ".join(UpdateExpression.split())

                if expr == "SET #fl = :empty":
                    if ConditionExpression and "fantasy_leagues" in item:
                        raise RuntimeError("ConditionalCheckFailedException")
                    item[names["#fl"]] = values[":empty"]
                elif expr == "SET #fl.#id = :cfg":
                    item.setdefault(names["#fl"], {})[names["#id"]] = values[":cfg"]
                elif expr == "REMOVE #fl.#id":
                    item.get(names["#fl"], {}).pop(names["#id"], None)
                else:  # a new expression shape must not pass silently
                    raise AssertionError(f"unhandled UpdateExpression: {expr}")

        return FakeTable()

    @pytest.fixture()
    def store(self, monkeypatch):
        dynamo = pytest.importorskip("app.backend.services.dynamo")
        table = self._fake_table()
        monkeypatch.setattr(dynamo, "_users_table", lambda: table)
        return dynamo

    @staticmethod
    def _cfg(name="My League", n_teams=12):
        cfg = _config(name=name, n_teams=n_teams).to_dict()
        return cfg

    def test_create_then_read_back(self, store):
        rec = store.put_fantasy_league("u1", None, self._cfg())
        assert rec["league_id"]
        assert rec["created_at"] and rec["updated_at"]

        listed = store.list_fantasy_leagues("u1")
        assert [item["league_id"] for item in listed] == [rec["league_id"]]
        assert listed[0]["name"] == "My League"

    def test_update_keeps_identity_and_created_at(self, store):
        created = store.put_fantasy_league("u1", None, self._cfg(name="Old"))
        updated = store.put_fantasy_league(
            "u1", created["league_id"], self._cfg(name="New", n_teams=10)
        )
        assert updated["league_id"] == created["league_id"]      # same league, not a duplicate
        assert updated["created_at"] == created["created_at"]    # origin never rewritten
        assert updated["name"] == "New" and updated["n_teams"] == 10
        assert len(store.list_fantasy_leagues("u1")) == 1        # updated in place

    def test_delete_removes_only_that_league(self, store):
        a = store.put_fantasy_league("u1", None, self._cfg(name="A"))
        b = store.put_fantasy_league("u1", None, self._cfg(name="B"))
        store.delete_fantasy_league("u1", a["league_id"])
        remaining = [item["league_id"] for item in store.list_fantasy_leagues("u1")]
        assert remaining == [b["league_id"]]

    def test_delete_of_an_unknown_league_raises_not_found(self, store):
        with pytest.raises(ValueError, match="not_found"):
            store.delete_fantasy_league("u1", "does-not-exist")

    def test_a_user_cannot_touch_another_users_league(self, store):
        """Leagues are keyed by the caller's own user_id (from the token), so cross-user access is
        structurally impossible rather than merely unauthorised — pinned so a future refactor to a
        shared key space would fail loudly."""
        mine = store.put_fantasy_league("u1", None, self._cfg(name="Mine"))
        store.put_fantasy_league("u2", None, self._cfg(name="Theirs"))

        assert store.get_fantasy_league("u2", mine["league_id"]) is None
        with pytest.raises(ValueError, match="not_found"):
            store.delete_fantasy_league("u2", mine["league_id"])
        assert len(store.list_fantasy_leagues("u1")) == 1  # untouched

    def test_saving_many_leagues_is_capped(self, store):
        for i in range(store.MAX_LEAGUES_PER_USER):
            store.put_fantasy_league("u1", None, self._cfg(name=f"L{i}"))
        with pytest.raises(ValueError, match="too_many_leagues"):
            store.put_fantasy_league("u1", None, self._cfg(name="one too many"))

    def test_a_malformed_stored_league_does_not_blank_the_collection(self, store):
        """E9.49 again, at the store layer: one bad row must cost only itself."""
        good = store.put_fantasy_league("u1", None, self._cfg(name="Good"))
        table = store._users_table()
        table.items["u1"]["fantasy_leagues"]["corrupt"] = "not-a-dict"

        listed = store.list_fantasy_leagues("u1")
        assert [item["league_id"] for item in listed] == [good["league_id"]]


class TestApiModels:
    @staticmethod
    def _payload(**overrides):
        cfg = _config().to_dict()
        cfg.update(overrides)
        return cfg

    def test_valid_config_saves(self):
        models = pytest.importorskip("app.backend.models.fantasy")
        saved = models.LeagueSave(**self._payload())
        assert saved.n_teams == 12
        assert any(s.name == "IR" and s.bench for s in saved.roster)

    def test_rejects_what_the_engine_rejects(self):
        """The API must not store a league the engine cannot rank."""
        models = pytest.importorskip("app.backend.models.fantasy")
        pydantic = pytest.importorskip("pydantic")
        bench_only = self._payload(
            roster=[{"name": "BN", "count": 5, "eligible": ["WR"], "bench": True}]
        )
        with pytest.raises(pydantic.ValidationError):
            models.LeagueSave(**bench_only)
        with pytest.raises(pydantic.ValidationError):
            models.LeagueSave(**self._payload(scoring={"per_stat": {}, "position_bonuses": {}}))
        with pytest.raises(pydantic.ValidationError):
            models.LeagueSave(**self._payload(n_teams=1))

    def test_response_model_inherits_no_write_validators(self):
        """E9.49: a rule tightened for SAVES must never make an already-stored league unreadable.

        The regression this pins is concrete — `Bet` subclassing `BetCreate` meant one legacy row
        500'd the entire bet log on read. A league config is long-lived user data we fully expect to
        extend, so the read model must stay validator-free.
        """
        models = pytest.importorskip("app.backend.models.fantasy")
        assert not issubclass(models.League, models.LeagueSave)

        # a stored league that would FAIL today's save rules must still READ
        legacy = self._payload(n_teams=64, scoring={"per_stat": {}, "position_bonuses": {}})
        legacy["league_id"] = "legacy-1"
        out = models.League(**legacy)
        assert out.league_id == "legacy-1"
        assert out.n_teams == 64
