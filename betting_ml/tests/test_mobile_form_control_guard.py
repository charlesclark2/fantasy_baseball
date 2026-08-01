"""Guards for the two mobile form-control defect classes fixed 2026-08-01.

Both classes were live in production, both are invisible to every other gate (CI mocks IO, and
neither is a type error), and both are the kind of thing a new component reintroduces by writing
the *obvious* spelling. So they are pinned here by source inspection rather than left to review.

CLASS 1 — iOS FOCUS AUTO-ZOOM. Safari zooms the page whenever a focused ``<input>``/``<select>``/
``<textarea>`` has a font-size under 16px, and the zoom re-lays-out the viewport *underneath* an
already-opening native ``<select>`` picker — so the picker anchors to pre-zoom coordinates and
lands somewhere unrelated. That was the user-visible "the dropdown pops up in a weird spot" bug on
every NFL fantasy page. Radix ``SelectTrigger`` renders a ``<button>``, which does NOT auto-zoom,
so it is deliberately out of scope here.

CLASS 2 — PER-KEYSTROKE ``Number()`` COERCION on a controlled numeric field. ``Number("") === 0``,
so clearing a field to retype it snapped the value to 0 and the next digit read as "01". Where the
handler also clamped (``Math.max(1, ...)``), it was worse than cosmetic: clearing a min-1 Kelly-cap
field snapped it to 1, so typing "5" silently left the user on 15% — a plausible number nobody
typed, feeding stake sizing. ``<select>`` is exempt: its value is always one of its own options,
never "" or a partial token, so ``Number()`` on a select is safe.

These parse TSX with a brace/quote-aware scanner rather than a naive regex, because a JSX attribute
value can contain an arrow function whose ``=>`` ends a lazy ``[^>]*?>`` match early — a real bug
that made an earlier sweep silently under-report.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
UI_DIRS = ("components", "app")

# Raw intrinsic controls that iOS auto-zooms. Radix primitives render <button> and are excluded.
ZOOMABLE_TAGS = ("select", "input", "textarea")
# A control with no text content of its own cannot be zoomed into by a font-size rule.
EXEMPT_INPUT_TYPES = ('type="checkbox"', 'type="radio"', 'type="range"', 'type="file"')

SMALL_TEXT = re.compile(r"(?<![\w:-])text-(xs|sm)\b")


def _strip_comments(src: str) -> str:
    """Blank out // and /* */ comments, respecting quotes and template literals.

    Necessary because the fixed source now *documents* the defect — several files contain the
    literal text "raw <select>" in a comment explaining why they no longer use one. A scanner that
    does not strip comments would read those as real elements, which would make the
    no-native-select assertion below fail on the very code that satisfies it.
    """
    out = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if quote:
            if c == "\\":
                out.append(src[i : i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
            out.append(c)
        elif c in "\"'`":
            quote = c
            out.append(c)
        elif c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        elif c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(" " * (j - i))  # preserve offsets so line numbers stay right
            i = j
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _tsx_files() -> list[Path]:
    files: list[Path] = []
    for d in UI_DIRS:
        root = FRONTEND / d
        if root.is_dir():
            files.extend(sorted(root.rglob("*.tsx")))
    return files


def _opening_tag(src: str, start: int) -> str:
    """Return the full opening tag beginning at ``start``, brace- and quote-aware.

    A naive scan to the first ``>`` truncates at the arrow of an inline handler
    (``onChange={(e) => ...}``), which silently hides attributes that follow it.
    """
    i, depth, quote = start, 0, None
    while i < len(src):
        c = src[i]
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            break
        i += 1
    return src[start:i]


def _class_attr(tag: str) -> str:
    m = re.search(r'className="([^"]*)"', tag)
    return m.group(1) if m else ""


def _iter_raw_controls():
    """Yield (path, line, tagname, opening_tag) for every raw zoomable control."""
    for path in _tsx_files():
        src = _strip_comments(path.read_text())
        for m in re.finditer(rf"<({'|'.join(ZOOMABLE_TAGS)})\b", src):
            tag = _opening_tag(src, m.start())
            if any(t in tag for t in EXEMPT_INPUT_TYPES):
                continue
            yield path, src[: m.start()].count("\n") + 1, m.group(1), tag


class TestIosAutoZoom:
    def test_scanner_finds_controls_at_all(self):
        """Non-vacuity: a silently-empty scan would make every assertion below pass."""
        found = list(_iter_raw_controls())
        assert len(found) > 10, f"scanner found only {len(found)} raw controls — it is broken"

    def test_no_raw_control_is_under_16px_on_mobile(self):
        """A raw control may use text-xs/text-sm only behind a breakpoint, with a >=16px base."""
        offenders = []
        for path, line, tag, el in _iter_raw_controls():
            cls = _class_attr(el)
            if SMALL_TEXT.search(cls) and "text-base" not in cls:
                rel = path.relative_to(FRONTEND)
                offenders.append(f"{rel}:{line} <{tag}> className={cls!r}")
        assert not offenders, (
            "Raw form control(s) render under 16px on mobile — iOS will auto-zoom on focus and "
            "misplace any native <select> picker. Use `text-base sm:text-sm` (16px on phones, "
            "unchanged on desktop):\n  " + "\n  ".join(offenders)
        )

    @pytest.mark.parametrize("component", ["input.tsx", "textarea.tsx"])
    def test_shared_primitive_pins_mobile_size_after_className(self, component):
        """The shadcn primitives must re-assert a >=16px mobile size AFTER the caller's className.

        `cn()` is tailwind-merge, so a call site passing `text-sm` REPLACES the primitive's safe
        `text-base` base — 25 call sites did exactly that. The trailing `max-sm:text-base` is a
        different merge group, so it survives, and Tailwind emits variant utilities after
        unprefixed ones so it wins the cascade below 640px.
        """
        src = (FRONTEND / "components" / "ui" / component).read_text()
        assert src.count("max-sm:text-base") == 1, (
            f"{component}: expected exactly one mobile-size guard, found "
            f"{src.count('max-sm:text-base')} — a duplicate makes the ordering check ambiguous"
        )

        # Order must be checked INSIDE the cn() argument list. Checking the raw file offsets is
        # wrong: `className,` also appears in the component's own destructuring signature
        # (`function Input({ className, type, ...props })`), which sits above everything and makes
        # a naive index comparison pass no matter where the guard actually is.
        call = re.search(r"className=\{cn\((.*?)\n\s*\)\}", src, re.S)
        assert call, f"{component}: could not locate the className={{cn(...)}} call"
        args = call.group(1)

        guard_at = args.index("'max-sm:text-base'")
        passthrough = re.search(r"^\s*className,\s*$", args, re.M)
        assert passthrough, f"{component}: cn() no longer forwards the caller's className"
        assert passthrough.start() < guard_at, (
            f"{component}: `max-sm:text-base` must come AFTER the caller's `className` in cn(). "
            "cn() is tailwind-merge — placed before, a call-site `text-sm` wins and the guard is "
            "INERT while still appearing present."
        )


class TestNoNativeSelect:
    """No raw ``<select>``: on iOS its popup anchors to the top-left of the page, not the control.

    This is CLASS 3, and it is the one the first two fixes did NOT solve. With a 16px font, an
    un-nested label, a correct ``width=device-width`` viewport and no transform/scroll-container
    ancestor, the native popup was STILL misplaced. What identified it was that the defect tracked
    the implementation rather than the page: every surface using a raw ``<select>`` reproduced it,
    and every surface already using Radix (Bet Log, Parlay, the prop dialogs) did not — same device,
    same session. Radix renders a ``<button>`` trigger plus a portalled, JS-positioned menu, so it
    never depends on WebKit anchoring a native popup.
    """

    def test_no_raw_select_element(self):
        offenders = []
        for path, line, tag, _el in _iter_raw_controls():
            if tag == "select":
                offenders.append(f"{path.relative_to(FRONTEND)}:{line}")
        assert not offenders, (
            "Raw <select> found. Its native popup mis-anchors on iOS regardless of font-size or "
            "label nesting. Use `Picker` (components/ui/picker.tsx), which wraps Radix:\n  "
            + "\n  ".join(offenders)
        )

    def test_comment_stripping_does_not_hide_a_real_select(self):
        """The stripper must remove only comments — a real element must still be seen.

        Without this, `test_no_raw_select_element` could pass by silently blanking real code.
        """
        sample = (
            'const a = "not // a comment"\n'
            "// <select id='commented'>\n"
            "/* <select id='blockCommented'> */\n"
            "<select id='real' className='text-sm'>\n"
        )
        stripped = _strip_comments(sample)
        assert "commented" not in stripped, "line comment survived stripping"
        assert "blockCommented" not in stripped, "block comment survived stripping"
        assert "real" in stripped, "a REAL element was stripped — the guard would be vacuous"
        assert "not // a comment" in stripped, "a // inside a string literal must be preserved"


class TestNumericInputCoercion:
    """No controlled numeric <input> may coerce with Number() on every keystroke."""

    def test_no_per_keystroke_number_coercion_on_an_input(self):
        offenders = []
        for path, line, tag, el in _iter_raw_controls():
            if tag != "input":
                continue  # <select> is exempt: its value is always a valid option
            if "Number(e.target.value)" in el or "parseFloat(e.target.value)" in el:
                rel = path.relative_to(FRONTEND)
                offenders.append(f"{rel}:{line}")
        assert not offenders, (
            "Controlled numeric <input>(s) coerce with Number() per keystroke. `Number('') === 0`, "
            "so clearing the field to retype snaps it to 0 and the next digit reads as '01'; with a "
            "clamp it lands the user on a wrong value entirely. Use "
            "`components/ui/numeric-input.tsx` instead:\n  " + "\n  ".join(offenders)
        )

    def test_numeric_input_holds_a_string_draft_and_rejects_out_of_range(self):
        """The shared component's whole reason to exist — pin the mechanism, not just its presence."""
        src = (FRONTEND / "components" / "ui" / "numeric-input.tsx").read_text()
        assert "useState<string | null>(null)" in src, "must hold the raw STRING while focused"
        assert 'type="text"' in src, 'must be type="text" — type="number" re-normalises leading zeros'
        assert "inputMode=" in src, "must still raise the numeric keypad on mobile"
        assert "onBlur" in src, "must drop an abandoned partial draft on blur"
        # min/max must REJECT (return) rather than clamp — clamping is what produced the wrong value.
        assert re.search(r"if \(min != null && n < min\) return", src), "min must reject, not clamp"
        assert re.search(r"if \(max != null && n > max\) return", src), "max must reject, not clamp"
