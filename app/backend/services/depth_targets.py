"""NF-C7b — WHICH depth targets apply, and where they came from.

NF-C7 gave the draft optimizer a per-position depth target: how many of a position the user wants
to finish the draft holding. A position short of its target is a soft need, ranked below a real
open starter slot and above generic bench depth. It shipped stored in `localStorage`, keyed by
season + scoring-format name — which meant two different leagues on the same format silently shared
one setting, nothing synced across devices, and the Chrome extension could not read it at all.

This module owns the ONE question that arises once the setting has two homes: given an account-level
default and a per-league value, which applies?

⭐ ONE FUNCTION, DELIBERATELY. The web app and the extension both need this answer, and E9.61's
lesson is that two renderers of one field become two rule sets — there it was a player's name
upper-cased by two different passes, and a grep of the file that was wrong cleared the file that was
right. The resolution order is a rule, so it gets a single implementation per side and a SHARED
fixture (`betting_ml/tests/fixtures/nf_c7b_depth_target_precedence.json`) that both the Python and
the TypeScript tests consume. Neither side may state the precedence in its own words.

⭐ `resolve` ALSO RETURNS WHERE THE ANSWER CAME FROM, and that is a feature rather than a nicety.
"your league asks for 2 QBs" and "your account default asks for 2 QBs" produce an identical
recommendation, so a user who wants to change it cannot tell WHICH screen to go to. An invisible
override is a footgun; naming the source is what makes it adjustable.

⚠️ THE SOURCE IS NOT A PER-POSITION MERGE. A league that carries targets replaces the account
default WHOLE, rather than filling in only the positions it omits. A merge would make "my league
wants 6 RBs and nothing else" quietly inherit an account-level `TE: 3` the user never asked for on
that league, and there would be no screen on which the effective set is visible — the user would be
reading two screens and mentally unioning them. Whole replacement means one screen always shows the
truth.
"""

from __future__ import annotations

from app.backend.models.fantasy import sanitize_depth_targets

#: The three answers `resolve` can give, as a stable contract for the surfaces that display it.
SOURCE_LEAGUE = "league"
SOURCE_ACCOUNT = "account"
SOURCE_NONE = "none"


def resolve(
    league: dict | None = None,
    account: dict | None = None,
) -> tuple[dict[str, int], str]:
    """Return `(targets, source)` for one league.

    Precedence: an explicit per-league value wins; otherwise the account default; otherwise none.

    ⭐ `None` AND `{}` ARE DIFFERENT ON THE LEAGUE, and that distinction is the whole reason this is
    a function rather than an `or`. `None` means "never set for this league" and inherits; `{}`
    means "the user cleared this league's targets" and does NOT. Written as `league or account` —
    the obvious spelling — an empty dict is falsy, so clearing a league's targets would silently
    re-inherit the account default and the user would have no way to turn the feature off for one
    league. It would present as "my setting won't save" (the E8.6 silent-save class).

    ⚠️ An account default of `{}` is NOT distinguished, because there is nothing beneath it to
    inherit: cleared and never-set are genuinely the same state there, and inventing a difference
    the user cannot observe would be a shape a future reader gets wrong.
    """
    if league is not None:
        league_targets = sanitize_depth_targets(league)
        if league_targets:
            return league_targets, SOURCE_LEAGUE
        # An explicit-but-empty league value is a deliberate opt-out. It stops here.
        return {}, SOURCE_NONE

    account_targets = sanitize_depth_targets(account)
    if account_targets:
        return account_targets, SOURCE_ACCOUNT
    return {}, SOURCE_NONE


def resolve_for_record(record: dict | None, account: dict | None = None) -> tuple[dict[str, int], str]:
    """`resolve` for a stored league RECORD, which may not carry the key at all.

    A record saved before this field existed has no `depth_targets` key, which must read as "never
    set" (inherit), NOT as "cleared". `dict.get` returning `None` gives exactly that, but only
    because the absent key and a stored `None` are the same value — so this wrapper exists to make
    the equivalence explicit at the one call site that depends on it rather than leaving it implied.
    """
    raw = (record or {}).get("depth_targets")
    return resolve(raw, account)
