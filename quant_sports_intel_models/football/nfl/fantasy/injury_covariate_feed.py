"""injury_covariate_feed.py — build the covariate feed the certified injury-games hurdle needs,
INSIDE the board build (NF-INJ3b-SHIP, PM ruling D7).

⚠️ THE PREREQUISITE THE FLIP INHERITED. NF-INJ3b certified a GLM hurdle over
`onset_carryover, weeks_since_last_game, prior_games, log1p_prior_fp, is_qb`. `prior_games` aside,
**none of those exists anywhere in the board build** — they are derived from the warehouse by the
bake-off's own population builder. So `injury_games_serving.served_injury_games` REFUSES (loudly)
rather than falling back to the incumbent under the fitted arm's stamp, and until this module
existed a flip was impossible. This is that feed.

⭐ IT DERIVES NOTHING ITSELF. Every covariate comes from `nf_inj3_injury_games.derive_covariates`
— the definition the arm was FITTED on, extracted from `build_population` verbatim — over the
prior-season columns `run_nf_inj3_injury_games.load_prior_features` emits (the study's own SQL).
A feed that re-derived either half would serve a different model from the one that was certified
(NF-C0e), and the 1e-9 pin in `betting_ml/tests/test_nf_inj3b_ship_covariate_feed.py` is what makes
that a MEASUREMENT rather than a claim about this docstring.

🔒 THE LEAKAGE GATE, AND IT IS THE REASON THIS IS NOT UNCONDITIONAL. The SERVED artifact is fitted
on `train_seasons` = [2016, 2025] — it has seen every one of those seasons' realized outcomes. So
applying it to a board for a season inside that window (an NF3.2 track-record backtest board, or
one of the NF1.9 band-panel seasons) would be **leakage**: a past board scored by a model that read
the future. `feed_for_board` therefore refuses any projection season that is not strictly AFTER the
artifact's last training season, and the bound is READ OFF THE ARTIFACT — not a constant here, not
a season hardcoded anywhere. The refusal is RECORDED, never silent, and the board then keeps the
incumbent caps exactly as it does today.

⭐ THAT GATE IS ALSO WHAT KEEPS THE BAND AND LEVEL PANELS ON THE INCUMBENT'S HISTORY.
`build_veteran_panel_season` builds target seasons 2019…2025 — every one inside the training
window — so the panel the NF1.9 band and the NF-TR2b level constant are fitted on stays the
incumbent's, and neither correction can compound with this one. That is a consequence of the
leakage rule, not a second rule to keep in sync.
"""
from __future__ import annotations

import logging

import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG

log = logging.getLogger("nfl.fantasy.injury_covariate_feed")

#: the columns the feed emits — `player_id` plus exactly the design covariates the served hurdle
#: consumes, READ from the serving module so the two cannot drift.
FEED_COLUMNS: tuple[str, ...] = ("player_id", *IG.TIMING_FEATURES, *IG.BASE_FEATURES)


def leakage_bound(artifact: dict) -> int:
    """The last season the SERVED artifact was trained on — the bound `feed_for_board` refuses at.

    ⭐ Read off the artifact rather than declared here: a constant would silently go stale the first
    time the hurdle is re-fitted on a wider window, and it would go stale in the UNSAFE direction
    (a bound that is too low admits a leaked season)."""
    ts = artifact.get("train_seasons")
    if not isinstance(ts, (list, tuple)) or len(ts) != 2:
        raise ValueError(
            f"injury_covariate_feed: the served artifact declares no usable `train_seasons` "
            f"({ts!r}) — without it the leakage bound is unknowable and the feed must not be "
            f"built. An unverifiable bound is a failure, never a pass (NF1.7 (a)).")
    return int(ts[1])


def season_is_admissible(artifact: dict, projection_season: int) -> tuple[bool, str]:
    """`(admissible, reason)` — may the SERVED artifact be applied to this projection season?

    Strictly after the last training season. Equality is REFUSED: a board for season Y built from a
    model that saw season Y's outcomes is the leak, not a boundary case."""
    bound = leakage_bound(artifact)
    if int(projection_season) > bound:
        return True, (f"projection season {int(projection_season)} is after the served artifact's "
                      f"last training season ({bound})")
    return False, (
        f"REFUSED: the served injury-games artifact was fitted on seasons {artifact['train_seasons']}, "
        f"so applying it to a {int(projection_season)} board would score that board with a model "
        f"that has already seen its outcomes. The board keeps the INCUMBENT caps.")


def build_feed(con, roster: pd.DataFrame, projection_season: int, *,
               schema: str | None = None) -> tuple[pd.DataFrame, dict]:
    """The covariate feed for one projection season, one row per player of `roster`.

    `roster` supplies `player_id` and `position` — the board's OWN universe and the board's OWN
    position, which is what `build_population` used, so `is_qb` means the same thing on both sides.

    ⛔ Neither the SQL nor the arithmetic lives here: the prior-season columns come from the study
    runner's `load_prior_features` and the covariates from `IG.derive_covariates`."""
    # LAZY: the study runner imports `season_projection`, and this module is imported from
    # `run_season_projection` — a module-scope import would be a cycle.
    from quant_sports_intel_models.football.nfl.fantasy import (
        run_nf_inj3_injury_games as R3,
    )

    need = ("player_id", "position")
    missing = [c for c in need if c not in roster.columns]
    if missing:
        raise ValueError(f"injury_covariate_feed.build_feed: roster frame is missing {missing}")
    base = roster[list(need)].drop_duplicates("player_id").copy()
    base["player_id"] = base["player_id"].astype(str)
    prior = R3.load_prior_features(con, int(projection_season))
    prior["player_id"] = prior["player_id"].astype(str)
    merged = base.merge(prior, on="player_id", how="left")
    feed = IG.derive_covariates(merged)[list(FEED_COLUMNS)]
    prov = {
        "projection_season": int(projection_season),
        "rows": int(len(feed)),
        "matched_prior_season": int(prior["player_id"].isin(base["player_id"]).sum()),
        "covariates": list(FEED_COLUMNS[1:]),
        "derivation": "nf_inj3_injury_games.derive_covariates (the study's own definition)",
        "prior_features": "run_nf_inj3_injury_games.load_prior_features (the study's own SQL)",
        "schema": schema,
    }
    return feed, prov


def feed_for_board(con, roster: pd.DataFrame, projection_season: int, *,
                   schema: str | None = None,
                   artifact: dict | None = None) -> tuple[pd.DataFrame | None, dict]:
    """The feed the SERVED board should use, or `None` with a RECORDED reason.

    Returns `None` — and the board then keeps the incumbent caps — when the policy is OFF (the
    rollback state, where nothing reads the covariates at all) or when the leakage gate refuses the
    season. ⛔ It never returns `None` because something went wrong: a broken artifact, an
    unreadable warehouse or a malformed roster RAISES, because a build that quietly loses its feed
    while the policy is ON is the exact failure the D6 publish guard exists to catch, and failing
    here is strictly better than being caught there."""
    if not POLICY.serving_enabled():
        return None, {"supplied": False, "reason": "injury_games_policy.SERVING_ENABLED is False — "
                                                   "the board keeps the incumbent caps",
                      "projection_season": int(projection_season)}
    from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as IGS

    art = artifact if artifact is not None else IGS.load_artifact()
    ok, reason = season_is_admissible(art, projection_season)
    if not ok:
        return None, {"supplied": False, "reason": reason,
                      "projection_season": int(projection_season),
                      "train_seasons": list(art.get("train_seasons") or ())}
    feed, prov = build_feed(con, roster, projection_season, schema=schema)
    return feed, {"supplied": True, "reason": reason, **prov,
                  "train_seasons": list(art.get("train_seasons") or ()),
                  "artifact_fit_at": art.get("fit_at")}
