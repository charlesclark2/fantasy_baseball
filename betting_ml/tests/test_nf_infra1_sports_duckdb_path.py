"""NF-INFRA1 — ONE authoritative sports-DuckDB path, on a volume that survives a deploy.

WHAT THESE PIN, and why each clause is separate (NF-D17): a guard on an `and`-composed rule is
vacuous unless its fixture satisfies every OTHER clause, so each invariant here gets its own test
and its own failure mode. Every clause was RED-proven against deliberately-broken source before
being trusted.

THE DEFECT (NF-FRESH1, 2026-08-15). `SPORTS_DUCKDB_PATH` was unset on the box and four owners each
supplied their own default — the Sleeper ingest op, the dbt-build op (`/tmp/sports_ncaaf.duckdb`),
the two game-day schedules (`/tmp/sports_ncaaf.duckdb` AND a `/tmp/sports_nfl.duckdb` that nothing
ever wrote), and `profiles.yml`. Nothing agreed, so the NFL game-day gate read a file that never
existed (permanently fail-open) and the Sleeper op died at `duckdb.connect` in 114ms behind a bare
`except`, producing 19 consecutive green runs over a 19-day-old Delta commit. Both halves matter:
the file also had nowhere durable to live (`*.duckdb` is gitignored ⇒ absent from the `COPY . .`
image, `/tmp` is wiped by every deploy, `/app` is replaced by the image).

Fast-gate safe (E11.23): nothing here imports `pipeline` — the owners are read as SOURCE.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from betting_ml.utils import sports_duckdb as SD

_REPO = Path(__file__).resolve().parents[2]
_COMPOSE = _REPO / "services/dagster/aws/docker-compose.yml"
_ENV_REQUIRED = _REPO / "services/dagster/aws/env.required"
_ENV_EXAMPLE = _REPO / "services/dagster/aws/.env.example"
_PROFILES = _REPO / "quant_sports_intel_models/sports_dbt/profiles.yml"
_RESOLVER = _REPO / "betting_ml/utils/sports_duckdb.py"

# The trees an owner could plausibly live in. Scanned exhaustively rather than listed by name —
# INC-38's lesson is that a per-owner fix fails exactly where the owner registry is incomplete.
_SCAN_ROOTS = ("pipeline", "betting_ml", "scripts", "quant_sports_intel_models")


# ── source helpers ──────────────────────────────────────────────────────────────────────────
def _code_strings(path: Path) -> list[str]:
    """Every string CONSTANT in `path` that is not a docstring.

    Docstrings and `#` comments are excluded deliberately: this repo documents its landmines in
    prose (this very file names `/tmp/sports_ncaaf.duckdb` three times), and a guard that prose can
    satisfy — or trip — is not a guard (INC-38).
    """
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def _python_files() -> list[Path]:
    out: list[Path] = []
    for root in _SCAN_ROOTS:
        for path in (_REPO / root).rglob("*.py"):
            # Tests legitimately name the env var (this file does); they are not owners.
            if "betting_ml/tests/" in path.as_posix() or "/tests/" in path.as_posix():
                continue
            out.append(path)
    return out


def _files_naming_the_env_var() -> set[Path]:
    """Every non-test Python file that reads/writes `SPORTS_DUCKDB_PATH` in CODE (not prose)."""
    hits = set()
    for path in _python_files():
        try:
            if SD.ENV_VAR in _code_strings(path):
                hits.add(path)
        except SyntaxError:  # pragma: no cover — a genuinely broken file is not this test's job
            continue
    return hits


# ── 1. the resolver's own behaviour ─────────────────────────────────────────────────────────
def test_an_unset_env_var_falls_back_to_the_repo_default(monkeypatch):
    monkeypatch.delenv(SD.ENV_VAR, raising=False)
    assert SD.sports_duckdb_path() == SD.REPO_DEFAULT


def test_a_present_but_EMPTY_env_var_is_treated_as_unset(monkeypatch):
    """An empty value SHADOWS a code default (`os.environ.get(k, d)` returns `""`), which would
    point DuckDB at `""` — the exact trap `env.required` documents for CACHE_BUCKET."""
    monkeypatch.setenv(SD.ENV_VAR, "   ")
    assert SD.sports_duckdb_path() == SD.REPO_DEFAULT


def test_the_env_var_wins_when_set(monkeypatch):
    monkeypatch.setenv(SD.ENV_VAR, "/somewhere/else.duckdb")
    assert SD.sports_duckdb_path() == "/somewhere/else.duckdb"


def test_a_relative_path_anchors_on_app_dir_not_the_process_cwd(monkeypatch):
    """A Dagster op and the subprocess it spawns run with DIFFERENT cwds (`_run_sports_dbt` uses
    `cwd=SPORTS_DBT_DIR`), so a relative value must be resolved ONCE, by the op."""
    monkeypatch.setenv(SD.ENV_VAR, "rel/sports.duckdb")
    monkeypatch.setenv("APP_DIR", "/app")
    assert SD.resolve_sports_duckdb() == Path("/app/rel/sports.duckdb")


def test_the_subprocess_env_carries_an_ABSOLUTE_path(monkeypatch):
    monkeypatch.setenv(SD.ENV_VAR, "rel/sports.duckdb")
    monkeypatch.setenv("APP_DIR", "/app")
    assert SD.sports_duckdb_env()[SD.ENV_VAR] == "/app/rel/sports.duckdb"


# ── 2. the box path is on a volume that survives a deploy ───────────────────────────────────
def test_the_box_path_lives_inside_the_mounted_volume_dir():
    assert SD.BOX_DUCKDB_PATH.startswith(SD.BOX_VOLUME_DIR + "/")


def test_the_box_path_is_not_deploy_ephemeral():
    """`/tmp` is wiped by every deploy and `/app` is REPLACED by the image — the two locations the
    pre-NF-INFRA1 owners actually used."""
    assert not SD.BOX_DUCKDB_PATH.startswith("/tmp/")
    assert not SD.BOX_DUCKDB_PATH.startswith("/app/")


def test_compose_declares_the_named_volume():
    compose = _COMPOSE.read_text()
    top_level = compose.split("\nvolumes:\n")[-1]
    assert "\n  sports_duckdb:" in top_level, (
        "docker-compose.yml must declare a top-level named volume `sports_duckdb` — a bind/anonymous "
        "mount would not survive `docker compose up -d`")


def test_compose_mounts_the_volume_on_codeloc_at_the_resolver_s_directory():
    """The mount point and `BOX_VOLUME_DIR` are ONE fact in two files; drift between them puts the
    database back somewhere the image replaces."""
    compose = _COMPOSE.read_text()
    codeloc = compose.split("dagster-codeloc:", 1)[1].split("\n  dagster-daemon:", 1)[0]
    assert f"- sports_duckdb:{SD.BOX_VOLUME_DIR}" in codeloc, (
        f"dagster-codeloc must mount sports_duckdb at {SD.BOX_VOLUME_DIR} "
        "(it is BOTH the run worker and the code server where schedule evaluation reads the gate)")


# ── 3. the deploy-time gate + the operator-facing template ──────────────────────────────────
def test_env_required_gates_the_deploy_on_the_path_being_set():
    keys = {line.strip() for line in _ENV_REQUIRED.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")}
    assert SD.ENV_VAR in keys, (
        "SPORTS_DUCKDB_PATH must be in env.required: an UNSET var is the defect itself (every owner "
        "falls back to its own default), and deploy.sh is the only thing that can refuse it")


def test_the_env_template_documents_the_exact_box_value():
    assert f"{SD.ENV_VAR}={SD.BOX_DUCKDB_PATH}" in _ENV_EXAMPLE.read_text(), (
        "CI's env-parity check asserts every env.required key is documented in .env.example, and an "
        "operator copying a WRONG value re-creates the divergence this story removed")


def test_profiles_yml_reads_the_shared_env_var_on_every_path():
    """dbt is the one owner that cannot import the resolver, so it must at least read the same var."""
    paths = [ln for ln in _PROFILES.read_text().splitlines() if ln.strip().startswith("path:")]
    assert paths, "profiles.yml has no `path:` entries — the scan is stale"
    for line in paths:
        assert f"env_var('{SD.ENV_VAR}'" in line, f"profiles.yml path does not read {SD.ENV_VAR}: {line}"


# ── 4. no owner may hold its own path ───────────────────────────────────────────────────────
def test_the_env_var_scan_is_not_vacuous():
    """A walk that matched nothing would make every clause below pass on nothing (NF1.7(a))."""
    files = _python_files()
    assert len(files) > 200, f"the source walk only found {len(files)} files — the roots are wrong"
    assert _RESOLVER in files


def test_only_the_resolver_names_the_env_var_in_code():
    """The single-owner invariant, derived rather than declared: any NEW consumer that reaches for
    `os.environ[...]` directly instead of `sports_duckdb_path()` fails here the day it ships."""
    owners = _files_naming_the_env_var()
    assert owners == {_RESOLVER}, (
        "SPORTS_DUCKDB_PATH must be read through betting_ml/utils/sports_duckdb.py only; found it "
        f"named in: {sorted(p.relative_to(_REPO).as_posix() for p in owners - {_RESOLVER})}")


def test_no_pipeline_owner_hardcodes_a_deploy_ephemeral_duckdb_path():
    """`/tmp/sports_ncaaf.duckdb` and `/tmp/sports_nfl.duckdb` were the two literals that made the
    build and the gate read different files, one of which nothing ever wrote."""
    offenders = []
    for path in _python_files():
        if not path.as_posix().startswith((_REPO / "pipeline").as_posix(),):
            continue
        for value in _code_strings(path):
            if value.startswith("/tmp/") and value.endswith(".duckdb"):
                offenders.append(f"{path.relative_to(_REPO)}: {value}")
    assert not offenders, (
        "a Dagster op/schedule must not hardcode a /tmp DuckDB path — /tmp is wiped by every "
        f"deploy (INC-25 shape): {offenders}")


@pytest.mark.parametrize("owner", [
    "pipeline/jobs/sports_dbt_job.py",
    "pipeline/jobs/sports_nfl_sleeper_injuries_job.py",
    "pipeline/jobs/sports_nfl_board_publish_job.py",
    "pipeline/schedules/sports_dbt_schedules.py",
])
def test_each_known_owner_imports_the_shared_resolver(owner):
    """The four owners NF-FRESH1 found disagreeing. Named explicitly (as well as covered by the
    derived scan above) so a regression names the file it broke."""
    src = (_REPO / owner).read_text()
    assert "from betting_ml.utils.sports_duckdb import" in src, (
        f"{owner} must resolve the sports DuckDB through the shared helper")


def test_both_game_day_gates_read_the_same_database_the_build_writes():
    """The NFL gate used to read `/tmp/sports_nfl.duckdb` while the build wrote
    `/tmp/sports_ncaaf.duckdb`, so it was permanently FAIL-OPEN — visible only as a gate that never
    skipped, never as an error."""
    src = (_REPO / "pipeline/schedules/sports_dbt_schedules.py").read_text()
    assert src.count("duckdb_path=_gate_duckdb()") == 2, (
        "both sports game-day gates must resolve their DuckDB through the shared helper")
