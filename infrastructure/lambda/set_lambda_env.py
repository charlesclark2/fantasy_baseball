#!/usr/bin/env python3
"""E9.8-P2 — the operator's tool for changing ONE Lambda environment variable safely.

⚠️ THE DEFECT THIS EXISTS TO MAKE IMPOSSIBLE. `aws lambda update-function-configuration
--environment` does not MERGE — it **REPLACES the whole `Variables` map**. Send it
`{"Variables": {"STRIPE_SECRET_KEY": "sk_live_..."}}` and the API Lambda loses
`COGNITO_USER_POOL_ID`, `CACHE_BUCKET`, `SNOWFLAKE_PRIVATE_KEY`, `ADMIN_EMAILS` and every
other setting in one call. The function keeps serving — it just answers wrong, from a
half-configured process, and `deploy.sh` will NOT restore it (it only ever calls
`update-function-code`; it never touches the environment). So the blast radius of one
forgotten read is the whole API, on the day real money starts moving through it.

The documented workaround was a hand-rolled read-modify-write heredoc, copied into
`infrastructure/aws_resources.md` in TWO places (the Vercel-token section and the
degrade-mode runbook). That is this repo's recurring "one logical thing, many owners"
shape (INC-30 crontab, INC-36 deploy lock, INC-38 per-caller flags): every copy is another
chance to paste the update without the read. This file is the single owner, and both doc
copies now point at it.

WHAT MAKES IT SAFE — each of these is a way the hand-rolled version silently fails:

  1. **READ-MODIFY-WRITE, and it REFUSES on a bad read.** If `get-function-configuration`
     errors, or returns an empty `Variables` map, the tool ABORTS without writing. A merge
     onto a failed read produces exactly the map that wipes the function, so the read is a
     precondition, not a step. (The E11.24 target-6 lesson, one service over: a destructive
     operation must verify its source is readable BEFORE it destroys the current state —
     a guard that is safe against failure A and unsafe against failure B has only
     relocated the outage.)

  2. **THE PRESERVATION INVARIANT IS ASSERTED, NOT ASSUMED.** Before the write, every
     pre-existing key must still be present with a byte-identical value unless it was
     named on the command line. A key can only leave via an explicit `--unset`. If the
     merged map fails that check the tool raises instead of writing.

  3. **IT VERIFIES AFTER THE WRITE.** The config update is ASYNCHRONOUS — the call returns
     `LastUpdateStatus=InProgress` and a `get-function-configuration` a second later still
     reports the OLD environment. The tool waits for `Successful`, re-reads, and asserts
     every intended key actually landed and no other key changed. Without this, "the
     command succeeded" and "the flag is live" are different claims, and only the second
     one matters (FU-1: a flag is not armed until it is proven in the thing that runs).

  4. **SECRETS NEVER REACH ARGV, AND NEVER REACH STDOUT.** `--set-env` / `--set-stdin`
     take the value from the environment or a pipe, so `sk_live_…` stays out of shell
     history and out of `ps`. Every value this tool prints is masked. A `--set K=V` whose
     value looks like a live credential is refused outright and told to use `--set-env`.

  5. **DRY RUN IS THE DEFAULT.** It prints the masked diff and runs every invariant, but
     writes nothing until `--apply`. On a go-live the operator gets to see the change
     before making it.

  6. **A BACKUP IS TAKEN BY DEFAULT.** The invariants stop the map being WIPED; they cannot
     stop a wrong VALUE being pasted. The backup is the rollback for that, and the tool
     prints the exact restore command. ⚠️ It contains the real secrets — it is written
     0600 into a gitignored directory and the tool tells the operator to delete it.

USAGE (all commands from the LAPTOP):

    # See what would change — writes nothing.
    uv run python infrastructure/lambda/set_lambda_env.py --set ENFORCE_SUBSCRIBER_MFA=1

    # Apply it.
    uv run python infrastructure/lambda/set_lambda_env.py --set ENFORCE_SUBSCRIBER_MFA=1 --apply

    # A secret: put it in the environment first so it never lands in shell history.
    #   read -rs STRIPE_SECRET_KEY && export STRIPE_SECRET_KEY
    uv run python infrastructure/lambda/set_lambda_env.py --set-env STRIPE_SECRET_KEY --apply

    # Or pipe it straight out of a password manager:
    op read 'op://private/stripe/live_secret_key' \
      | uv run python infrastructure/lambda/set_lambda_env.py --set-stdin STRIPE_SECRET_KEY --apply

Several `--set*` flags may be combined; they are applied as ONE update, which is what you
want for the go-live flip (the key, the price ids and the webhook secret must never be
live in the function separately from each other).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_FUNCTION = "credence-prod-lambda-api"
DEFAULT_REGION = "us-east-1"

# Where a backup goes. Gitignored (see .gitignore) so a file full of live credentials can
# never be committed by an unrelated `git add`.
BACKUP_DIR = Path(".secrets")

# Values that must never be typed on a command line: they would land in shell history and
# be visible in `ps` to every process on the machine for the duration of the call.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"^sk_(live|test)_"),      # Stripe secret key
    re.compile(r"^rk_(live|test)_"),      # Stripe restricted key
    re.compile(r"^whsec_"),               # Stripe webhook signing secret
    re.compile(r"-----BEGIN .*PRIVATE KEY"),
)

# Keys whose value is masked in output even when it does not match a pattern above.
_SECRET_KEY_HINTS = ("SECRET", "KEY", "TOKEN", "PASSWORD", "PRIVATE", "DSN", "URL")


class Abort(RuntimeError):
    """A refusal. Raised instead of writing whenever an invariant cannot be established."""


# ── masking ──────────────────────────────────────────────────────────────────────────────


def is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(hint in upper for hint in _SECRET_KEY_HINTS)


def mask(key: str, value: str) -> str:
    """A printable rendering that identifies a value without disclosing it.

    Secrets keep a short PREFIX because that is the operationally useful part — `sk_test_`
    vs `sk_live_` is exactly the distinction a go-live turns on — plus a length, so the
    operator can tell a truncated paste from a whole one.
    """
    if value is None:
        return "<absent>"
    if not is_secret_key(key) and not looks_like_a_secret(value):
        return value if len(value) <= 80 else value[:77] + "..."
    if len(value) <= 8:
        return f"<redacted len={len(value)}>"
    return f"{value[:8]}…<redacted len={len(value)}>"


def looks_like_a_secret(value: str) -> bool:
    return any(p.search(value) for p in _SECRET_VALUE_PATTERNS)


# ── AWS ──────────────────────────────────────────────────────────────────────────────────


def _aws(args: list[str], profile: str | None) -> str:
    cmd = ["aws", *args]
    if profile:
        cmd += ["--profile", profile]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Abort(
            f"aws {' '.join(args[:3])} failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc.stdout


def read_environment(function: str, region: str, profile: str | None) -> dict[str, str]:
    """The function's CURRENT `Environment.Variables`.

    ⛔ Raises rather than returning `{}` on an empty map. An empty read is the one input
    that turns this tool into the wipe it exists to prevent, and — the recurring lesson —
    an empty result is indistinguishable from a permissions or networking failure, so it
    must never be treated as data (E9.26b: a silent-empty is SUSPECT, never a value).
    """
    raw = _aws(
        [
            "lambda", "get-function-configuration",
            "--function-name", function,
            "--region", region,
            "--query", "Environment.Variables",
            "--output", "json",
        ],
        profile,
    )
    try:
        env = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Abort(f"could not parse the current environment as JSON: {exc}") from exc
    if not isinstance(env, dict) or not env:
        raise Abort(
            "the current environment read back EMPTY or non-dict. Refusing to write — "
            "merging onto an empty read is exactly the call that wipes the function. "
            "Check credentials/permissions and re-run."
        )
    return {str(k): str(v) for k, v in env.items()}


def wait_for_update(function: str, region: str, profile: str | None, timeout_s: int = 180) -> str:
    """Block until the async config update settles. Returns the terminal LastUpdateStatus.

    A config update returns `InProgress`; reading the environment before it settles reports
    the OLD values, so a verification that skipped this would confirm the pre-change state
    and call it a success.
    """
    deadline = time.time() + timeout_s
    status = "InProgress"
    while time.time() < deadline:
        raw = _aws(
            [
                "lambda", "get-function-configuration",
                "--function-name", function,
                "--region", region,
                "--query", "LastUpdateStatus",
                "--output", "text",
            ],
            profile,
        )
        status = raw.strip()
        if status != "InProgress":
            return status
        time.sleep(3)
    raise Abort(f"timed out after {timeout_s}s waiting for the update (last status: {status})")


# ── the merge, and the invariant that makes it safe ──────────────────────────────────────


def merge_environment(
    current: dict[str, str],
    updates: dict[str, str],
    unsets: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """`current` with `updates` applied and `unsets` removed — nothing else touched.

    ⭐ THE PRESERVATION INVARIANT IS CHECKED HERE, not left to the caller's care, so that a
    future caller cannot reintroduce the wipe by constructing the map itself. Every key of
    `current` must survive with a byte-identical value unless it was explicitly named. The
    function raises rather than returning a map that would lose one.
    """
    merged = dict(current)
    for key in unsets:
        merged.pop(key, None)
    merged.update(updates)

    named = set(updates) | set(unsets)
    lost = [k for k in current if k not in merged and k not in unsets]
    if lost:
        raise Abort(f"refusing to write: these keys would be LOST: {sorted(lost)}")
    changed = [k for k in current if k in merged and merged[k] != current[k] and k not in named]
    if changed:
        raise Abort(f"refusing to write: these keys would change unasked: {sorted(changed)}")
    return merged


def describe_diff(current: dict[str, str], merged: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for key in sorted(set(current) | set(merged)):
        before, after = current.get(key), merged.get(key)
        if before == after:
            continue
        if before is None:
            lines.append(f"  + {key}: <absent> -> {mask(key, after)}")
        elif after is None:
            lines.append(f"  - {key}: {mask(key, before)} -> <REMOVED>")
        else:
            lines.append(f"  ~ {key}: {mask(key, before)} -> {mask(key, after)}")
    return lines


# ── argument collection ──────────────────────────────────────────────────────────────────


def collect_updates(args: argparse.Namespace, environ: dict[str, str], stdin_text: str) -> dict[str, str]:
    """Assemble the KEY->VALUE updates from the three input channels.

    ⛔ A `--set K=V` carrying something that looks like a live credential is REFUSED. The
    refusal is the point: by the time the operator sees the error the value is already in
    their shell history, so the tool names the safe channel instead of quietly accepting it.
    """
    updates: dict[str, str] = {}

    for pair in args.set or []:
        if "=" not in pair:
            raise Abort(f"--set expects KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise Abort(f"--set expects a non-empty KEY, got {pair!r}")
        if looks_like_a_secret(value):
            raise Abort(
                f"--set {key}=… carries what looks like a live credential. It would be written "
                f"to your shell history and be visible in `ps`. Use:\n"
                f"    read -rs {key} && export {key}\n"
                f"    uv run python infrastructure/lambda/set_lambda_env.py --set-env {key} --apply"
            )
        updates[key] = value

    for key in args.set_env or []:
        if key not in environ:
            raise Abort(
                f"--set-env {key}: no such variable in this shell. Set it first:\n"
                f"    read -rs {key} && export {key}"
            )
        value = environ[key]
        if not value:
            raise Abort(f"--set-env {key}: the variable is set but EMPTY. Refusing.")
        updates[key] = value

    if args.set_stdin:
        value = stdin_text.strip()
        if not value:
            raise Abort(f"--set-stdin {args.set_stdin}: nothing arrived on stdin. Refusing.")
        if "\n" in value:
            raise Abort(f"--set-stdin {args.set_stdin}: expected ONE line, got several.")
        updates[args.set_stdin] = value

    if not updates and not args.unset:
        raise Abort("nothing to do — pass at least one of --set / --set-env / --set-stdin / --unset")
    return updates


def write_backup(current: dict[str, str], function: str) -> Path:
    """Persist the pre-change map 0600 so a wrong VALUE is one command from a rollback."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = BACKUP_DIR / f"lambda-env.{function}.{stamp}.json"
    # Create with 0600 from the start — writing then chmod'ing leaves a window in which the
    # file is world-readable, which for a file of live credentials is the whole risk.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"Variables": current}, fh, indent=2)
    return path


# ── entrypoint ───────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="set_lambda_env.py",
        description="Change specific env vars on the API Lambda WITHOUT wiping the rest.",
    )
    p.add_argument("--function", default=DEFAULT_FUNCTION)
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--profile", default=None, help="AWS CLI profile (omit to use the default chain)")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="non-secret value; refused if it looks like a credential")
    p.add_argument("--set-env", action="append", metavar="KEY",
                   help="take KEY's value from this shell's environment (secrets)")
    p.add_argument("--set-stdin", metavar="KEY", help="read KEY's value as one line from stdin")
    p.add_argument("--unset", action="append", metavar="KEY", default=None,
                   help="remove KEY entirely — the ONLY way a key leaves the map")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.add_argument("--no-backup", action="store_true", help="skip the pre-change backup")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    unsets = frozenset(args.unset or ())

    try:
        stdin_text = sys.stdin.read() if args.set_stdin and not sys.stdin.isatty() else ""
        updates = collect_updates(args, dict(os.environ), stdin_text)

        print(f"Function : {args.function}  ({args.region})")
        print("Reading the CURRENT environment before changing anything...")
        current = read_environment(args.function, args.region, args.profile)
        print(f"  {len(current)} variables currently set.")

        merged = merge_environment(current, updates, unsets)

        diff = describe_diff(current, merged)
        print("\nChange:")
        print("\n".join(diff) if diff else "  (no change — the values are already what you asked for)")
        print(
            f"\nInvariant: {len(current)} vars in -> {len(merged)} out; "
            f"{len(set(current) - set(merged))} removed (explicitly requested: {len(unsets)})."
        )

        if not diff:
            print("\nNothing to write.")
            return 0

        if not args.apply:
            print("\nDRY RUN — nothing was written. Re-run with --apply to make this change.")
            return 0

        if not args.no_backup:
            backup = write_backup(current, args.function)
            print(f"\nBackup written: {backup} (mode 0600)")
            print("  ⚠️ It contains the REAL secrets. Restore with:")
            print(f"    aws lambda update-function-configuration --function-name {args.function} \\")
            print(f"      --region {args.region} --environment file://{backup}")
            print(f"  Delete it once the change is confirmed:  rm {backup}")

        payload = json.dumps({"Variables": merged})
        print("\nWriting...")
        _aws(
            [
                "lambda", "update-function-configuration",
                "--function-name", args.function,
                "--region", args.region,
                "--environment", payload,
                "--output", "json",
            ],
            args.profile,
        )

        print("Waiting for the update to settle (it is asynchronous)...")
        status = wait_for_update(args.function, args.region, args.profile)
        if status != "Successful":
            raise Abort(f"the update finished with LastUpdateStatus={status} — check the console")

        print("Re-reading to VERIFY the change actually landed...")
        after = read_environment(args.function, args.region, args.profile)
        problems: list[str] = []
        for key, value in updates.items():
            if after.get(key) != value:
                problems.append(f"{key} did not land (reads back {mask(key, after.get(key))})")
        for key in unsets:
            if key in after:
                problems.append(f"{key} was not removed")
        for key, value in current.items():
            if key in updates or key in unsets:
                continue
            if after.get(key) != value:
                problems.append(f"{key} changed unexpectedly — INVESTIGATE")
        if problems:
            raise Abort("post-write verification FAILED:\n  - " + "\n  - ".join(problems))

        print(f"  Verified: {len(after)} variables set; every intended key landed; nothing else moved.")
        print("\nDone.")
        return 0

    except Abort as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
