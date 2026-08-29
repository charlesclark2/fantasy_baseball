"""NCAAF-P3.2 — the COPY-GOVERNANCE and FIXTURE-PROVENANCE suite for the college-football surface.

The browser suite (`frontend/e2e/specs/ncaaf-games*.spec.ts`) proves what a READER meets: the cards
render, the curve is drawn from the served quantiles, an absent market line says so. It cannot see
three things, and each of them is a way this surface could go wrong while every rendered assertion
stayed green:

  1. ⛔ A CLAIM COULD BE WRITTEN INTO A BRANCH NO SPEC OPENS. The E2E denylist runs over the
     rendered page in three data modes, which is the right instrument for the copy a reader
     actually meets — but a string on a fourth branch (a state the harness has no fixture for) is
     invisible to it. This suite screens the copy module's literals directly, so a sentence is
     screened whether or not anything renders it yet.

  2. ⛔ THE FIXTURES COULD DRIFT FROM THE SHIPPING BUILDERS. Two of the four are GENERATED, and a
     generated fixture that nobody re-derives is a hand-written one with extra steps (the NF-C0e
     lesson: a fixture derived from the code's own output cannot disconfirm it, and one that has
     stopped being derived cannot even do that). `build-ncaaf-degraded.py` is re-run here and its
     output compared byte-for-byte.

  3. ⛔ THE CAPTURED FIXTURES COULD STOP BEING PAYLOADS THE SERVER CAN SEND. A re-capture, or a
     hand edit, could produce a blob the Pydantic response model would reject — and then every E2E
     conclusion would be "given a payload no caller can receive, the page renders Y".

RED-PROVEN: `uv run python betting_ml/tests/ncaaf_p3_2_red_proof.py`.

Pure/offline (fast gate): reads committed source + fixtures, and re-runs a pure builder. No
DuckDB/S3/network.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.backend.models import ncaaf as contract
from betting_ml.governance import gates
from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"
_COPY_TS = _FRONTEND / "lib/ncaaf-copy.ts"
_CURVE_TS = _FRONTEND / "lib/ncaaf-curve.ts"
_DATA_TS = _FRONTEND / "lib/ncaaf.ts"
_COMPONENTS = sorted((_FRONTEND / "components/ncaaf").glob("*.tsx"))
_ROUTE = _FRONTEND / "app/ncaaf/games/page.tsx"

_FIXTURES = _FRONTEND / "e2e/fixtures/api"
_CAPTURED_MANIFEST = _FIXTURES / "ncaaf-manifest.json"
_CAPTURED_SLATE = _FIXTURES / "ncaaf-slate-2026-08-29.json"
_GENERATED = (
    _FIXTURES / "ncaaf-slate-2026-08-29-market.synthetic.json",
    _FIXTURES / "ncaaf-slate-degraded.synthetic.json",
)
_GENERATOR = _FRONTEND / "e2e/fixtures/build-ncaaf-degraded.py"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Extraction — deliberately crude, and CHECKED FOR NON-VACUITY before anything relies on it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _strip_comments(src: str) -> str:
    """Remove `//` and `/* */`, so a COMMENT can never satisfy a clause below.

    ⭐ INC-38's lesson, and it has bitten this repo more than once: a source-inspection guard that
    matches anywhere in the file passes on the explanatory comment a careful author wrote ABOVE the
    code, with the code itself deleted."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


#: A Tailwind class list is not prose. Every token is lower-case and at least one carries a
#: Tailwind separator (`-`, `:`, `/`, an arbitrary-value bracket) — a shape English sentences do not
#: have. Found by the guard's own first run, which read `-mx-1 flex gap-1.5 overflow-x-auto px-1
#: pb-1` as a six-word sentence and `gap-x-3` as a difference column.
_CLASS_TOKEN = re.compile(r"^[a-z0-9!\-:/\[\]%#.()_&>~*+]+$")


def _looks_like_class_names(text: str) -> bool:
    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    if not tokens:
        return False
    return all(_CLASS_TOKEN.match(t) for t in tokens) and any(
        c in t for t in tokens for c in "-:/["
    )


#: JSX text, CONSERVATIVELY. `>…<` also matches a run of CODE between an arrow function's `>` and a
#: comparison's `<` — the guard's first run read a whole `useMemo`/`const` block as a 34-word
#: sentence that way. A rendered text node is one line and carries no operator characters.
#:
#: ⚠️ CONSERVATIVE IS THE RIGHT DIRECTION HERE, and the reason is that this is the BELT, not the
#: braces: the authoritative screen over rendered JSX is `ncaaf-games.spec.ts`'s denylist pass over
#: `document.body.innerText` in three data modes, which sees every text node the browser produced
#: however it was written. What this half adds is coverage of prose that is NOT yet rendered by any
#: fixture — which is overwhelmingly string literals, and those are matched exactly.
_JSX_CODE_CHARS = set("=;(){}[]<>|&`$")


def _is_jsx_text(text: str) -> bool:
    if not text or "\n" in text:
        return False
    return not (set(text) & _JSX_CODE_CHARS)


def _prose(src: str) -> list[str]:
    """Every human-readable run in a TS/TSX source: string literals, template literals, JSX text.

    JSX TEXT IS THE HALF THAT MATTERS MOST and the half a string-literal scan misses entirely —
    `<p>we beat the market</p>` contains no string literal at all."""
    s = _strip_comments(src)
    out = re.findall(r'"((?:[^"\\]|\\.)*)"', s)
    # ⚠️ A template literal carrying `${…}` is CODE with a bit of punctuation in it (an SVG path
    # builder, a testid suffix), not a sentence — the guard's first run read an SVG `d`-attribute
    # builder as a seven-word sentence. Its literal HALVES still reach the denylist above as
    # ordinary string literals, so nothing user-facing escapes by living inside one.
    out += [t for t in re.findall(r"`([^`]*)`", s) if "${" not in t]
    out += [m for m in (t.strip() for t in re.findall(r">([^<>{}]+)<", s)) if _is_jsx_text(m)]
    return [t for t in out if t.strip() and not _looks_like_class_names(t)]


ALL_SOURCES = [_COPY_TS, _CURVE_TS, _DATA_TS, _ROUTE, *_COMPONENTS]


def test_the_source_registry_is_not_empty_and_names_real_files():
    """Every clause below iterates this list. An empty or stale list would make all of them pass on
    nothing — the NF1.7 (a) vacuous-anchor shape, in its cheapest form."""
    assert len(_COMPONENTS) >= 5, f"only {len(_COMPONENTS)} NCAAF component(s) found"
    for p in ALL_SOURCES:
        assert p.exists(), f"{p} does not exist"


def test_the_prose_scan_actually_finds_prose():
    """The extractor's own non-vacuity check. A scan that silently returned nothing would make the
    screening clauses vacuously true."""
    literals = _prose(_COPY_TS.read_text())
    assert len(literals) >= 20, f"only {len(literals)} run(s) extracted from the copy module"
    assert any("market" in s.lower() for s in literals), "the market framing was not extracted"
    # And on a COMPONENT, where the JSX-text half is what is being exercised.
    card = _prose((_FRONTEND / "components/ncaaf/game-card.tsx").read_text())
    assert any("Neutral site" in s for s in card), "JSX text was not extracted from a component"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The denylist — over the copy module AND every component
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_every_ncaaf_frontend_string_passes_the_claim_denylist():
    """⛔ `best_alpha = 0`. VAL1 came back ALL_BUCKETS_NULL — ATS 0.496 against the close,
    indistinguishable from the placebo — and the pooled CLV null stands, so there is no measured
    advantage over a market price and a sentence implying one asserts something the program has
    MEASURED to be absent.

    Screened with `export_track_record_json._CLAIM_DENYLIST` rather than a list of this story's own,
    because that tuple is the repo's SUPERSET (the governance gates' set plus the plain-English
    overclaims) and a second list here would be free to lag it."""
    for path in ALL_SOURCES:
        for s in _prose(path.read_text()):
            hits = [t for t in ex._CLAIM_DENYLIST if t in s.lower()]
            assert not hits, f"{path.name} makes a forbidden claim {hits}: {s!r}"


def test_the_copy_module_passes_the_governance_gate():
    result = gates.track_record_copy_compatible(_prose(_COPY_TS.read_text()))
    assert result.status == gates.PASS, result.detail


def test_the_copy_module_carries_no_measured_figure():
    """⛔ E9.56b/NF-D3: a number typed into a component cannot be reconciled against the measurement
    it came from and drifts silently the first time the model is re-scored. Every figure on this
    surface — the probability, the interval bounds, the band's own levels, the market line — is
    read off the payload."""
    for s in _prose(_COPY_TS.read_text()):
        assert not re.search(r"\d\.\d{2,}", s), f"the copy module hardcodes a measured figure: {s!r}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Structural properties the browser cannot see
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_served_disclosure_is_never_duplicated_in_the_frontend():
    """⭐ The disclosure is SERVED and rendered verbatim from the payload.

    `app/backend/models/ncaaf.py::DISCLOSURE` is pinned verbatim by a backend guard, so a reword
    there is a reviewed change. A second copy in the frontend would be free to drift from it — and
    the drifting copy is the one a reader would actually see, because a component prefers its own
    constant over a payload field it does not know it has."""
    needle = contract.DISCLOSURE[:60]
    for path in ALL_SOURCES:
        assert needle not in path.read_text(), (
            f"{path.name} carries a LOCAL copy of the served disclosure. Render "
            f"`framing.disclosure` from the payload instead."
        )


def test_the_prose_lives_in_the_copy_module_not_in_the_components():
    """A component that writes its own sentence writes a sentence no screening owns.

    ⚠️ THE THRESHOLD IS A JUDGEMENT AND IS STATED AS ONE: short runs ("Neutral site", "at",
    "market", "Team TBD") are labels and belong where they are rendered; anything sentence-length is
    prose and belongs in `lib/ncaaf-copy.ts`, where clause 1 above and the E2E denylist both see it.
    Six words is where a label stops being a label."""
    for path in _COMPONENTS + [_ROUTE]:
        for s in _prose(path.read_text()):
            words = [w for w in re.split(r"\s+", s.strip()) if w]
            assert len(words) < 6, (
                f"{path.name} writes its own prose ({len(words)} words): {s!r}\n"
                f"Move it to frontend/lib/ncaaf-copy.ts so the denylist screens it."
            )


def _identifier_words(src: str) -> set[str]:
    """Every identifier in the CODE, split on camelCase / snake / kebab boundaries.

    ⚠️ STRING LITERALS AND JSX TEXT ARE REMOVED FIRST, and that is not a tidy-up: without it the
    scan reads the words of a user-facing SENTENCE as identifiers. The guard's first run proved it
    — "Pick another kickoff day above." refused the copy module for declaring a `pick`, and a
    Tailwind `gap-x-3` refused the comparison panel for naming a difference. Both are prose and
    styling, and both are screened by their OWN clauses above; identifiers are a separate question
    and need a separate substrate."""
    src = re.sub(r'"(?:[^"\\]|\\.)*"', " ", _strip_comments(src))
    src = re.sub(r"`[^`]*`", " ", src)
    src = re.sub(r">[^<>{}]+<", "><", src)
    # ⭐ The contract's OWN exemption, honoured rather than re-litigated: `best_alpha` NAMES the
    # absence of a claim, which is why `app/backend/models/ncaaf.py` exempts it from the identical
    # screen one layer up. A client that mirrors the served field has to be able to spell it.
    exempt = {f.lower() for f in contract.FORBIDDEN_TOKEN_EXEMPT_FIELDS}
    exempt |= {f.replace("_", "").lower() for f in contract.FORBIDDEN_TOKEN_EXEMPT_FIELDS}
    words: set[str] = set()
    for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", src):
        if ident.lower() in exempt:
            continue
        parts = re.split(r"[_\-]|(?<=[a-z0-9])(?=[A-Z])", ident)
        words.update(p.lower() for p in parts if p)
    return words


def test_no_ncaaf_frontend_identifier_names_a_pick_or_an_edge():
    """The frontend half of `assert_no_edge_claim_in_schema`.

    That guard REFUSES to declare a served field whose NAME reads as a pick, an edge, a stake or a
    win-rate. It polices the wire; this polices what the client builds out of it — a field can be
    introduced at either end, and a client-side `edgeVsMarket` would be exactly the quantity the
    contract deliberately does not carry.

    ⚠️ WHOLE WORDS, split on camelCase, NOT substrings. `DayPicker` splits to `day` + `picker`, and
    `picker` is not `pick`; a substring scan would refuse the day selector this surface is required
    to have."""
    tokens = {t for t in contract.FORBIDDEN_PAYLOAD_TOKENS if "_" not in t}
    for path in ALL_SOURCES:
        offending = tokens & _identifier_words(path.read_text())
        assert not offending, (
            f"{path.name} declares an identifier named {sorted(offending)}, which reads as a "
            f"pick/edge/stake claim. This vertical serves a market-blind projection (best_alpha=0)."
        )


def test_the_market_panel_names_no_difference_between_the_two_columns():
    """⛔ THE CONTRACT DECLARES NO DIFFERENCE FIELD ON PURPOSE.

    `NcaafMarketLine`'s own docstring: "Model −7, market −3.5 is a fact a reader can see; 'model
    beats market by 3.5' is the claim VAL1's null forbids, and a signed difference column is one
    rename away from being read as exactly that."

    This is a NAMING guard and says so: it cannot see arithmetic, and the browser suite carries the
    structural half (the comparison grid has exactly three columns). What it catches is the
    realistic drift — a `delta`/`diff`/`gap`/`beat` appearing on the panel — which is what a
    well-meaning copy or feature edit would actually introduce."""
    panel = _FRONTEND / "components/ncaaf/market-comparison.tsx"
    words = _identifier_words(panel.read_text())
    for banned in ("delta", "diff", "difference", "gap", "beat", "beats", "advantage", "vs"):
        assert banned not in words, (
            f"market-comparison.tsx names a `{banned}` — the served contract declares no difference "
            f"field, and a signed gap is the claim VAL1's null forbids."
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Fixture provenance
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _split_fields_added_since_capture(validated, blob, path=""):
    """Recursively strip keys the CONTRACT declares and the CAPTURE predates.

    Returns `(stripped_validated, added_paths)`. Nothing the fixture CARRIES is touched, so the
    caller can still demand exact equality on every captured key — the only thing tolerated is a
    field declared after the bytes were captured.
    """
    added: list[str] = []
    if isinstance(validated, dict) and isinstance(blob, dict):
        out = {}
        for key, value in validated.items():
            here = f"{path}.{key}" if path else key
            if key not in blob:
                added.append(here)
                continue
            sub, sub_added = _split_fields_added_since_capture(value, blob[key], here)
            out[key], _ = sub, added.extend(sub_added)
        return out, added
    if isinstance(validated, list) and isinstance(blob, list) and len(validated) == len(blob):
        out_list = []
        for i, (value, other) in enumerate(zip(validated, blob)):
            sub, sub_added = _split_fields_added_since_capture(value, other, f"{path}[{i}]")
            out_list.append(sub)
            added.extend(sub_added)
        return out_list, added
    return validated, added


@pytest.mark.parametrize(
    "path,model",
    [(_CAPTURED_MANIFEST, contract.NcaafManifest), (_CAPTURED_SLATE, contract.NcaafSlate)],
    ids=["manifest", "slate"],
)
def test_the_captured_fixtures_are_payloads_the_server_could_actually_send(path, model):
    """Otherwise every E2E conclusion is "given a payload no caller can receive, the page renders Y".

    ⚠️ RE-ANCHORED by NCAAF-P3.1b, which declared `market.as_of` — an ADDITIVE field (NF-C0), so
    the deployed server now sends one key these captured bytes predate. The property that matters
    is unchanged and still exactly asserted: nothing the fixture carries may be REJECTED or altered
    by the response model. A field the CAPTURE predates is tolerated ONLY when it validates to
    `null`, i.e. it cannot be carrying content the fixture is silently missing — and the test NAMES
    the fields it tolerated, so a stale capture stays visible rather than becoming invisible.
    (Closing it properly is a re-capture through `capture-fixtures.mjs` AFTER the Lambda deploy —
    the fixture cannot lead the wire.)
    """
    blob = json.loads(path.read_text())
    validated = model.model_validate(blob).model_dump()
    stripped, added = _split_fields_added_since_capture(validated, blob)
    assert stripped == blob, f"{path.name} does not round-trip the response model unchanged"
    for dotted in added:
        node = validated
        for part in re.findall(r"[^.\[\]]+", dotted):
            node = node[int(part)] if part.isdigit() else node[part]
        assert node is None, (
            f"{path.name} predates the declared field {dotted!r} AND that field validates to "
            f"{node!r}, not null — the capture is missing real content, not merely a new key. "
            "Re-capture the fixture rather than tolerating this."
        )


def test_the_captured_slate_still_holds_the_state_the_specs_reason_from():
    """The specs' conclusions rest on properties of the CAPTURE, and a re-capture can move them.

    ⚠️ These are not assertions about the model — they are assertions that the fixture is still the
    kind of payload the surface was designed against. If one fails after a re-capture, the fixture
    has changed CHARACTER (a market line landed; a day was published for 'today') and the specs
    that reason from it need re-reading, not silencing."""
    slate = json.loads(_CAPTURED_SLATE.read_text())
    manifest = json.loads(_CAPTURED_MANIFEST.read_text())
    assert slate["games"], "the captured slate is empty"
    # The market-absent branch is the one nearly every reader meets (P3.1 closeout item 2).
    assert all(g["market"]["status"] == "unavailable" for g in slate["games"])
    # A full quantile ladder — what makes `data-curve-source="quantiles"` the expected state.
    assert all(len(g["margin"]["quantiles"]) >= 3 for g in slate["games"])
    assert all(g["margin"]["interval_lo"] is not None for g in slate["games"])
    # 'Today' has no slate — the case that makes `defaultGameDay` more than `current_game_day`.
    assert manifest["current_game_day"] not in [d["game_day"] for d in manifest["game_days"]]


def test_the_generated_fixtures_are_the_shipping_builders_own_output():
    """Re-run the generator and demand byte-identical output.

    ⭐ This is what keeps "generated" from decaying into "hand-written". Both fixtures leave through
    `payloads._market()` / `payloads.build_game_payload()`, which validate against the Pydantic
    contract on the way out — so a contract change that the fixtures no longer satisfy fails HERE,
    where it is one command to fix, rather than in a browser assertion that says nothing about
    why."""
    before = {p: p.read_bytes() for p in _GENERATED}
    result = subprocess.run(
        [sys.executable, str(_GENERATOR)], capture_output=True, text=True, cwd=str(_REPO)
    )
    assert result.returncode == 0, f"the generator failed:\n{result.stdout}\n{result.stderr}"
    for p in _GENERATED:
        assert p.read_bytes() == before[p], (
            f"{p.name} is not the generator's current output — re-run "
            f"`uv run python {_GENERATOR.relative_to(_REPO)}` and commit the result."
        )
