"""E9.8-P2 — guards for the Lambda env flip helper (`infrastructure/lambda/set_lambda_env.py`).

The tool exists because `update-function-configuration --environment` REPLACES the whole
`Variables` map. Every test here is a way that replacement could still happen, or a way the
tool could report success without having changed anything.

⭐ EACH CLAUSE IS TESTED IN ISOLATION (NF-D17). The tool's safety is an AND of several
conditions, and a fixture that trips two of them proves neither: the guard stays green when
you delete the clause it names, because a second clause is already refusing the fixture. So
every test below satisfies every condition EXCEPT the one it is about. The RED proofs at the
bottom of this file demonstrate that mechanically, by deleting each clause from a copy of
the source and asserting the corresponding test goes red.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "infrastructure" / "lambda" / "set_lambda_env.py"

# The RED proof at the bottom of this file re-runs one test against a DELIBERATELY BROKEN
# copy of the tool. It points here rather than editing the real file, so a crashed proof can
# never leave a mutated source behind.
_LOADED = Path(os.environ.get("E98P2_TOOL_OVERRIDE") or _TOOL)


def _load():
    """Import the tool by path — `infrastructure/` is not an importable package."""
    spec = importlib.util.spec_from_file_location("_e98p2_set_lambda_env", _LOADED)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load()


# A realistic pre-change map: the shape actually on `credence-prod-lambda-api` (key names
# read live 2026-08-15), so a fixture cannot pass by being simpler than production.
#
# ⚠️ KEEP THE FAKE STRIPE KEYS SHORT AND OFF THE REAL FORMAT. GitHub push protection is on for
# this repo and matches Stripe's `sk_(live|test)_` prefix followed by a long alphanumeric run;
# a realistic-LOOKING fixture is rejected at `git push` with no way to tell it from a real leak
# (this file was blocked twice while being written). `looks_like_a_secret` keys on the PREFIX
# alone, so a short obviously-synthetic suffix tests exactly as much and pushes.
CURRENT = {
    "STRIPE_SECRET_KEY": "sk_test_FIXTUREabcdefghijklmnop",
    "STRIPE_PRICE_FOUNDING": "price_1TwwPBLQcIo7TYtcckL3Vr72",
    "STRIPE_PRICE_STANDARD": "price_1TwwPYLQcIo7TYtcH6StktUP",
    "STRIPE_WEBHOOK_SECRET": "whsec_FIXTUREnotarealsecret",
    "COGNITO_USER_POOL_ID": "us-east-1_gG9zMbwQt",
    "COGNITO_APP_CLIENT_ID": "1qh95e78bd7g6ipqcvdcpf7ou6",
    "APP_BASE_URL": "https://www.credencesports.com",
    "CACHE_BUCKET": "credence-prod-s3-api-cache",
    "SNOWFLAKE_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----",
    "ADMIN_EMAILS": "ctcb57@gmail.com",
    "TARGET_ENV": "prod",
}


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The preservation invariant — the wipe this tool exists to prevent
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheRestOfTheEnvironmentSurvives:
    def test_a_single_key_change_keeps_every_other_key_byte_identical(self):
        merged = mod.merge_environment(CURRENT, {"ENFORCE_SUBSCRIBER_MFA": "1"})
        assert set(merged) == set(CURRENT) | {"ENFORCE_SUBSCRIBER_MFA"}
        for key, value in CURRENT.items():
            assert merged[key] == value, f"{key} was not preserved"

    def test_the_whole_go_live_flip_is_one_update_that_loses_nothing(self):
        """The real Part-C call: key + both price ids + webhook secret + the MFA flag."""
        updates = {
            "STRIPE_SECRET_KEY": "sk_live_FIXTUREzzzzzzzzzz",
            "STRIPE_PRICE_FOUNDING": "price_LIVEfounding",
            "STRIPE_PRICE_STANDARD": "price_LIVEstandard",
            "STRIPE_WEBHOOK_SECRET": "whsec_liveZZZ",
            "ENFORCE_SUBSCRIBER_MFA": "1",
        }
        merged = mod.merge_environment(CURRENT, updates)
        assert merged["STRIPE_SECRET_KEY"].startswith("sk_live_")
        # Everything NOT named is untouched — this is the assertion that fails if someone
        # "simplifies" the tool back into a bare update-function-configuration.
        for key, value in CURRENT.items():
            if key not in updates:
                assert merged[key] == value, f"{key} was collateral damage"

    def test_a_key_can_only_leave_via_an_explicit_unset(self):
        merged = mod.merge_environment(CURRENT, {"TARGET_ENV": "prod"}, frozenset({"ADMIN_EMAILS"}))
        assert "ADMIN_EMAILS" not in merged
        assert set(CURRENT) - set(merged) == {"ADMIN_EMAILS"}


class TestTheMergeTripwireCatchesAFutureRefactor:
    """`merge_environment`'s `lost`/`changed` raises cannot be tripped through its public
    signature today — the body starts from `dict(current)`, so nothing is ever dropped. That
    makes them a TRIPWIRE for a later edit of the body, and a tripwire is only real if
    something proves it fires. Testing it therefore requires simulating the refactor: this
    loads a copy whose body has been changed to build the map from scratch (the natural
    "simplification" someone would make) and asserts the clause converts that silent wipe
    into a refusal.

    Without this, the clause is untested decoration — which is the failure mode this repo
    keeps finding (a guard nothing exercises, NF1.7 (a)).
    """

    def _load_with_base_dropped(self, tmp_path):
        src = _LOADED.read_text()
        fragment = "    merged = dict(current)\n"
        assert fragment in src, "the merge body changed — this tripwire test has rotted"
        broken = src.replace(fragment, "    merged = {}\n", 1)
        assert broken != src, "MUTATION DID NOT LAND"
        target = tmp_path / "refactored.py"
        target.write_text(broken)
        spec = importlib.util.spec_from_file_location("_e98p2_refactored", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_refactor_that_drops_the_base_map_raises_instead_of_returning_the_wipe(self, tmp_path):
        refactored = self._load_with_base_dropped(tmp_path)
        with pytest.raises(refactored.Abort, match="LOST"):
            refactored.merge_environment(CURRENT, {"ENFORCE_SUBSCRIBER_MFA": "1"})

    def test_the_unmutated_tool_still_merges_normally(self):
        """Two-sided: the tripwire must not be 'raise on everything'."""
        assert mod.merge_environment(CURRENT, {"ENFORCE_SUBSCRIBER_MFA": "1"})["CACHE_BUCKET"] == (
            CURRENT["CACHE_BUCKET"]
        )


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. An empty / failed read must never become a write
# ══════════════════════════════════════════════════════════════════════════════════════


class TestAnUnreadableCurrentEnvironmentAborts:
    """⭐ The single most dangerous input. `{}` merged with one update IS the wipe payload,
    and an empty read is indistinguishable from a permissions or networking failure — so it
    must be refused as a precondition, never treated as data (E9.26b)."""

    @pytest.mark.parametrize("payload", ["{}", "null", "[]"])
    def test_an_empty_read_refuses_instead_of_returning_a_wipe_payload(self, monkeypatch, payload):
        monkeypatch.setattr(mod, "_aws", lambda args, profile: payload)
        with pytest.raises(mod.Abort, match="EMPTY|non-dict"):
            mod.read_environment("fn", "us-east-1", None)

    def test_a_failed_aws_call_refuses(self, monkeypatch):
        def boom(args, profile):
            raise mod.Abort("AccessDeniedException")
        monkeypatch.setattr(mod, "_aws", boom)
        with pytest.raises(mod.Abort):
            mod.read_environment("fn", "us-east-1", None)

    def test_a_good_read_is_returned_intact(self, monkeypatch):
        """The two-sided half: the refusals above would also 'pass' if the function always
        raised. This proves the healthy path still works (NF1.7 (a))."""
        monkeypatch.setattr(mod, "_aws", lambda args, profile: json.dumps(CURRENT))
        assert mod.read_environment("fn", "us-east-1", None) == CURRENT


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. Secrets never reach argv, and never reach stdout
# ══════════════════════════════════════════════════════════════════════════════════════


class TestSecretsStayOffTheCommandLineAndOutOfTheOutput:
    @pytest.mark.parametrize(
        "value",
        [
            "sk_live_FIXTUREaaa",
            "sk_test_FIXTUREccc",
            "rk_live_restrictedkey",
            "whsec_liveSigningSecret",
            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        ],
    )
    def test_a_credential_shaped_value_on_the_command_line_is_refused(self, value):
        args = mod.build_parser().parse_args(["--set", f"STRIPE_SECRET_KEY={value}"])
        with pytest.raises(mod.Abort, match="shell history|--set-env"):
            mod.collect_updates(args, {}, "")

    def test_a_non_secret_flag_on_the_command_line_is_fine(self):
        """Two-sided: the refusal above must not be 'refuse everything'."""
        args = mod.build_parser().parse_args(["--set", "ENFORCE_SUBSCRIBER_MFA=1"])
        assert mod.collect_updates(args, {}, "") == {"ENFORCE_SUBSCRIBER_MFA": "1"}

    def test_set_env_reads_the_secret_without_it_touching_argv(self):
        args = mod.build_parser().parse_args(["--set-env", "STRIPE_SECRET_KEY"])
        got = mod.collect_updates(args, {"STRIPE_SECRET_KEY": "sk_live_FIXTUREReal"}, "")
        assert got == {"STRIPE_SECRET_KEY": "sk_live_FIXTUREReal"}

    def test_set_env_refuses_a_missing_or_empty_variable(self):
        """An unset var would otherwise write an EMPTY key, and an empty STRIPE_SECRET_KEY
        makes every billing call 503 'Billing is not configured' — a silent outage."""
        args = mod.build_parser().parse_args(["--set-env", "STRIPE_SECRET_KEY"])
        with pytest.raises(mod.Abort, match="no such variable"):
            mod.collect_updates(args, {}, "")
        with pytest.raises(mod.Abort, match="EMPTY"):
            mod.collect_updates(args, {"STRIPE_SECRET_KEY": ""}, "")

    def test_set_stdin_takes_one_line_and_refuses_nothing_or_several(self):
        args = mod.build_parser().parse_args(["--set-stdin", "STRIPE_WEBHOOK_SECRET"])
        assert mod.collect_updates(args, {}, "whsec_live\n") == {"STRIPE_WEBHOOK_SECRET": "whsec_live"}
        with pytest.raises(mod.Abort, match="nothing arrived"):
            mod.collect_updates(args, {}, "   \n")
        with pytest.raises(mod.Abort, match="ONE line"):
            mod.collect_updates(args, {}, "whsec_a\nwhsec_b\n")

    def test_no_diff_line_ever_prints_a_whole_secret(self):
        """The diff is what the operator screenshots or pastes into a handoff."""
        merged = mod.merge_environment(
            CURRENT,
            {"STRIPE_SECRET_KEY": "sk_live_FIXTUREbbb", "ENFORCE_SUBSCRIBER_MFA": "1"},
        )
        printed = "\n".join(mod.describe_diff(CURRENT, merged))
        assert "sk_live_FIXTUREbbb" not in printed
        assert CURRENT["STRIPE_SECRET_KEY"] not in printed
        assert CURRENT["SNOWFLAKE_PRIVATE_KEY"] not in printed
        # ...but the operationally load-bearing part IS shown: test vs live.
        assert "sk_test_" in printed and "sk_live_" in printed
        # And the non-secret flag is fully legible.
        assert "ENFORCE_SUBSCRIBER_MFA" in printed and "-> 1" in printed

    def test_the_mask_keeps_test_and_live_distinguishable(self):
        assert mod.mask("STRIPE_SECRET_KEY", "sk_live_abcdefghijk").startswith("sk_live_")
        assert mod.mask("STRIPE_SECRET_KEY", "sk_test_abcdefghijk").startswith("sk_test_")
        assert "abcdefghijk" not in mod.mask("STRIPE_SECRET_KEY", "sk_live_abcdefghijk")


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. Dry run by default; the backup is real and 0600
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheOperatorSeesTheChangeBeforeMakingIt:
    def test_apply_defaults_to_false(self):
        assert mod.build_parser().parse_args(["--set", "A=1"]).apply is False

    def test_a_dry_run_never_writes(self, monkeypatch, capsys):
        calls: list[list[str]] = []

        def fake_aws(args, profile):
            calls.append(args)
            assert "update-function-configuration" not in args, "DRY RUN WROTE TO AWS"
            return json.dumps(CURRENT)

        monkeypatch.setattr(mod, "_aws", fake_aws)
        rc = mod.main(["--set", "ENFORCE_SUBSCRIBER_MFA=1"])
        assert rc == 0
        assert any("update-function-configuration" in a for a in calls) is False
        assert "DRY RUN" in capsys.readouterr().out

    def test_nothing_to_do_is_refused_rather_than_silently_writing_the_map_back(self):
        args = mod.build_parser().parse_args([])
        with pytest.raises(mod.Abort, match="nothing to do"):
            mod.collect_updates(args, {}, "")

    def test_the_backup_is_created_0600_and_round_trips(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / ".secrets")
        path = mod.write_backup(CURRENT, "credence-prod-lambda-api")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f"backup is mode {oct(mode)} — it holds live credentials"
        assert json.loads(path.read_text()) == {"Variables": CURRENT}

    def test_the_backup_directory_is_gitignored(self):
        """A file of live credentials must be unreachable by a stray `git add`."""
        root = Path(__file__).resolve().parents[2]
        ignored = (root / ".gitignore").read_text().splitlines()
        assert any(line.strip() in (".secrets/", ".secrets") for line in ignored)


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. The write is verified — "the command succeeded" is not "the flag is live" (FU-1)
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheChangeIsVerifiedAfterTheWrite:
    def _driver(self, after_env, statuses=("Successful",)):
        """An `_aws` stand-in that serves CURRENT before the write and `after_env` after it."""
        state = {"written": False, "status": list(statuses)}

        def fake_aws(args, profile):
            if "update-function-configuration" in args:
                state["written"] = True
                return "{}"
            if "LastUpdateStatus" in args:
                return state["status"].pop(0) if len(state["status"]) > 1 else state["status"][0]
            return json.dumps(after_env if state["written"] else CURRENT)

        return fake_aws, state

    def test_a_landed_change_is_confirmed(self, monkeypatch, tmp_path, capsys):
        after = {**CURRENT, "ENFORCE_SUBSCRIBER_MFA": "1"}
        fake, state = self._driver(after)
        monkeypatch.setattr(mod, "_aws", fake)
        monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / ".secrets")
        assert mod.main(["--set", "ENFORCE_SUBSCRIBER_MFA=1", "--apply"]) == 0
        assert state["written"]
        assert "Verified" in capsys.readouterr().out

    def test_a_change_that_did_NOT_land_is_reported_as_a_failure(self, monkeypatch, tmp_path, capsys):
        """The whole point of the re-read: a silent no-op must not print success."""
        fake, _ = self._driver(dict(CURRENT))  # the flag never appears
        monkeypatch.setattr(mod, "_aws", fake)
        monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / ".secrets")
        assert mod.main(["--set", "ENFORCE_SUBSCRIBER_MFA=1", "--apply"]) == 2
        assert "verification FAILED" in capsys.readouterr().err

    def test_collateral_damage_after_the_write_is_reported(self, monkeypatch, tmp_path, capsys):
        """If anything DID wipe the map, the tool must say so rather than report success."""
        after = {"ENFORCE_SUBSCRIBER_MFA": "1"}  # the wipe
        fake, _ = self._driver(after)
        monkeypatch.setattr(mod, "_aws", fake)
        monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / ".secrets")
        assert mod.main(["--set", "ENFORCE_SUBSCRIBER_MFA=1", "--apply"]) == 2
        assert "INVESTIGATE" in capsys.readouterr().err

    def test_it_waits_for_the_async_update_before_reading_back(self, monkeypatch):
        """Reading before `LastUpdateStatus` settles returns the OLD env, so an
        un-waited verification confirms the PRE-change state and calls it success."""
        monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
        seen = ["InProgress", "InProgress", "Successful"]
        monkeypatch.setattr(mod, "_aws", lambda args, profile: seen.pop(0))
        assert mod.wait_for_update("fn", "us-east-1", None) == "Successful"
        assert not seen, "it stopped polling before the update settled"

    def test_a_failed_update_status_is_not_treated_as_success(self, monkeypatch):
        monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
        monkeypatch.setattr(mod, "_aws", lambda args, profile: "Failed")
        assert mod.wait_for_update("fn", "us-east-1", None) == "Failed"


# ══════════════════════════════════════════════════════════════════════════════════════
# 6. RED PROOFS — each clause deleted in isolation must turn its own test red
# ══════════════════════════════════════════════════════════════════════════════════════


_CLAUSES = {
    # (clause name) -> (source fragment to delete, the test that must go red)
    "empty_read_refusal": (
        '    if not isinstance(env, dict) or not env:\n'
        '        raise Abort(\n'
        '            "the current environment read back EMPTY or non-dict. Refusing to write — "\n'
        '            "merging onto an empty read is exactly the call that wipes the function. "\n'
        '            "Check credentials/permissions and re-run."\n'
        '        )\n',
        "TestAnUnreadableCurrentEnvironmentAborts",
    ),
    "argv_secret_refusal": (
        '        if looks_like_a_secret(value):\n'
        '            raise Abort(\n'
        '                f"--set {key}=… carries what looks like a live credential. It would be written "\n'
        '                f"to your shell history and be visible in `ps`. Use:\\n"\n'
        '                f"    read -rs {key} && export {key}\\n"\n'
        '                f"    uv run python infrastructure/lambda/set_lambda_env.py --set-env {key} --apply"\n'
        '            )\n',
        "TestSecretsStayOffTheCommandLineAndOutOfTheOutput::test_a_credential_shaped_value_on_the_command_line_is_refused",
    ),
    "preservation_invariant": (
        '    lost = [k for k in current if k not in merged and k not in unsets]\n'
        '    if lost:\n'
        '        raise Abort(f"refusing to write: these keys would be LOST: {sorted(lost)}")\n',
        "TestTheMergeTripwireCatchesAFutureRefactor::test_a_refactor_that_drops_the_base_map_raises_instead_of_returning_the_wipe",
    ),
    "post_write_collateral_check": (
        '        for key, value in current.items():\n'
        '            if key in updates or key in unsets:\n'
        '                continue\n'
        '            if after.get(key) != value:\n'
        '                problems.append(f"{key} changed unexpectedly — INVESTIGATE")\n',
        "TestTheChangeIsVerifiedAfterTheWrite::test_collateral_damage_after_the_write_is_reported",
    ),
    "post_write_landing_check": (
        '        for key, value in updates.items():\n'
        '            if after.get(key) != value:\n'
        '                problems.append(f"{key} did not land (reads back {mask(key, after.get(key))})")\n',
        "TestTheChangeIsVerifiedAfterTheWrite::test_a_change_that_did_NOT_land_is_reported_as_a_failure",
    ),
}


class TestTheReadinessGateNeverScoresAnUnevaluableCheckHealthy:
    """`scripts/check_stripe_golive_readiness.py` — the aggregation rule, not the AWS reads.

    NF1.7 (a): a check that could not RUN is not a check that PASSED. A readiness gate whose
    UNKNOWN counts as GO is the vacuous-anchor defect in its most consequential position —
    it would report GO on a go-live precisely when it could see nothing.
    """

    @staticmethod
    def _gate():
        spec = importlib.util.spec_from_file_location(
            "_e98p2_readiness",
            Path(__file__).resolve().parents[2] / "scripts" / "check_stripe_golive_readiness.py",
        )
        module = importlib.util.module_from_spec(spec)
        # Register BEFORE exec: `@dataclass` resolves its module via `sys.modules[__module__]`
        # while the class body runs, and an unregistered module makes that lookup return None.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_an_unevaluable_blocking_check_blocks(self, monkeypatch, capsys):
        gate = self._gate()
        monkeypatch.setattr(gate, "check_stripe_mode", lambda *a, **k: gate.Check("mode", gate.UNKNOWN, "AccessDenied"))
        for name in ("check_flag", "check_founding_counter", "check_mfa_lockout_risk",
                     "check_billing_alarm", "check_public_routes_and_degrade"):
            monkeypatch.setattr(gate, name, lambda *a, **k: gate.Check("ok", gate.GO, "fine"))
        monkeypatch.setattr(gate, "check_stripe_customer_links",
                            lambda *a, **k: gate.Check("links", gate.GO, "fine", blocking=False))
        assert gate.main([]) == 1
        assert "NO-GO" in capsys.readouterr().out

    def test_an_advisory_unknown_does_not_block(self, monkeypatch, capsys):
        """Two-sided: the rule above must not degenerate into 'anything non-GO blocks'."""
        gate = self._gate()
        for name in ("check_stripe_mode", "check_flag", "check_founding_counter",
                     "check_mfa_lockout_risk", "check_billing_alarm", "check_public_routes_and_degrade"):
            monkeypatch.setattr(gate, name, lambda *a, **k: gate.Check("ok", gate.GO, "fine"))
        monkeypatch.setattr(gate, "check_stripe_customer_links",
                            lambda *a, **k: gate.Check("links", gate.UNKNOWN, "?", blocking=False))
        assert gate.main([]) == 0
        assert "advisory" in capsys.readouterr().out

    def test_a_real_no_go_blocks(self, monkeypatch):
        gate = self._gate()
        monkeypatch.setattr(gate, "check_founding_counter",
                            lambda *a, **k: gate.Check("counter", gate.NO_GO, "slots_used=4"))
        for name in ("check_stripe_mode", "check_flag", "check_mfa_lockout_risk",
                     "check_billing_alarm", "check_public_routes_and_degrade"):
            monkeypatch.setattr(gate, name, lambda *a, **k: gate.Check("ok", gate.GO, "fine"))
        monkeypatch.setattr(gate, "check_stripe_customer_links",
                            lambda *a, **k: gate.Check("links", gate.GO, "fine", blocking=False))
        assert gate.main([]) == 1


class TestTheGoLivePriceContract:
    """The `$10 founding` promise, pinned against the fixture the E2E suite renders.

    The fixture is a verbatim capture of `GET /subscription/public-pricing` — the bytes a
    logged-out visitor's browser receives — so this asserts the PRODUCT PROMISE against the
    served payload rather than against a constant we wrote down. It is also the guard that
    fires if the operator re-captures after the flip onto a MIS-PROVISIONED live Price
    (wrong amount, wrong currency, a one-off instead of a subscription): the story's DoD is
    "$10-first-100", and a live Price of $1,000 or €10 or a non-recurring charge is a
    silently-wrong number on the page that takes real money.
    """

    @staticmethod
    def _fixture():
        path = (
            Path(__file__).resolve().parents[2]
            / "frontend" / "e2e" / "fixtures" / "api" / "subscription-public-pricing.json"
        )
        return json.loads(path.read_text())

    def test_the_founding_price_is_ten_dollars_a_month(self):
        f = self._fixture()
        assert f["unit_amount"] == 1000, f"the founding price is not $10.00 (got {f['unit_amount']} cents)"
        assert f["currency"] == "usd"
        assert f["interval"] == "month"
        assert f["interval_count"] == 1
        assert f["tier"] == "founding", "the fixture was captured while the STANDARD price was live"

    def test_the_public_payload_still_withholds_the_conversion_count(self):
        """E9.59: shipping `founding_cap` beside `remaining` would make `used` a subtraction
        away, i.e. leak the internal conversion count through the back door."""
        f = self._fixture()
        assert "founding_slots_used" not in f
        assert "founding_cap" not in f

    def test_seats_remaining_is_a_sane_clamped_count(self):
        remaining = self._fixture()["founding_slots_remaining"]
        assert isinstance(remaining, int) and 0 <= remaining <= 100, remaining


class TestTheRunbookCommandsAreActuallyPasteable:
    """`docs/e9_8_p2_stripe_golive.md` — the operator run-order.

    ⭐ A RUNBOOK COMMAND MUST NOT CONTAIN A CHARACTER THE SHELL WILL ACT ON. `<PLACEHOLDER>`
    reads as "fill this in" to a human and as INPUT REDIRECTION to bash/zsh, so pasting the
    literal line dies with `no such file or directory: PLACEHOLDER` before the command ever
    runs. That happened for real on 2026-08-16, mid-go-live, on the step that verifies the
    live price — the single most consequential read in the whole procedure.

    The repo's standing rule is that a handoff command is "FULL, copy-pasteable … no
    placeholders left unfilled". This makes it mechanical instead of a habit: a value the
    operator must supply is assigned to a shell VARIABLE on its own line, which is both
    paste-safe and reusable by later steps.

    Scoped to this runbook deliberately — it is the one this story owns, and a repo-wide
    sweep would fail on older docs for reasons no one is acting on today.
    """

    RUNBOOK = Path(__file__).resolve().parents[2] / "docs" / "e9_8_p2_stripe_golive.md"

    def _bash_blocks(self):
        import re
        blocks = re.findall(r"```bash\n(.*?)```", self.RUNBOOK.read_text(), re.S)
        assert blocks, "no bash blocks found — this guard would pass on nothing"
        return blocks

    def test_no_shell_hostile_placeholder_survives_in_a_command(self):
        import re
        offenders = []
        for block in self._bash_blocks():
            for line in block.splitlines():
                code = line.split("#", 1)[0]  # a placeholder inside a COMMENT is fine
                if re.search(r"<[A-Z_]{3,}>", code):
                    offenders.append(line.strip())
        assert not offenders, (
            "these runbook lines carry a <PLACEHOLDER> the shell reads as a redirect:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_price_verification_is_a_GET_not_a_POST(self):
        """`curl -d` defaults to POST, and `POST /v1/prices/{id}` is Stripe's UPDATE endpoint.
        A verification step must never be a write against a live billing object, so the
        retrieve has to carry `-G`."""
        for block in self._bash_blocks():
            for line in block.splitlines():
                if "api.stripe.com/v1/prices" in line and line.strip().startswith("curl"):
                    assert " -G " in line, f"price read is a POST (missing -G): {line.strip()}"

    def test_every_secret_exported_in_the_runbook_is_unset_at_the_end(self):
        """A live key left in the operator's shell outlives the step that needed it."""
        import re
        text = self.RUNBOOK.read_text()
        exported = set(re.findall(r"read -rs (\w+)\s+&&\s+export \1", text))
        assert exported, "no `read -rs … && export` found — this guard would pass on nothing"
        cleared = set()
        for line in text.splitlines():
            if line.strip().startswith("unset "):
                cleared.update(line.split("#", 1)[0].split()[1:])
        assert not (exported - cleared), f"never unset: {sorted(exported - cleared)}"


@pytest.mark.parametrize("clause", sorted(_CLAUSES))
def test_the_guard_goes_red_when_its_own_clause_is_deleted(clause, tmp_path, monkeypatch):
    """⭐ A guard that cannot fail is not a guard (NF1.7 (a) / INC-38 / NF-D17).

    Each clause is deleted ALONE — every other safeguard stays in place — so the test that
    goes red can only be reacting to the clause named. The mutation is applied IN-PROCESS
    and asserted to have LANDED first: a shell-quoting slip that silently no-ops the break
    would otherwise report "the guard caught it" while nothing was ever broken (#682).
    """
    fragment, test_id = _CLAUSES[clause]
    original = _TOOL.read_text()
    assert fragment in original, f"clause {clause!r} not found — the RED proof has rotted"
    broken = original.replace(fragment, "", 1)
    assert broken != original, "MUTATION DID NOT LAND"
    assert fragment not in broken

    target = tmp_path / "set_lambda_env.py"
    target.write_text(broken)

    import subprocess

    # Point the test module at the BROKEN copy via an env var the loader honours.
    env = {**os.environ, "E98P2_TOOL_OVERRIDE": str(target)}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{Path(__file__).name}::{test_id}", "-q", "-p", "no:randomly"],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0, (
        f"deleting the {clause!r} clause did NOT turn {test_id} red — that test is vacuous.\n"
        f"{proc.stdout[-2000:]}"
    )
