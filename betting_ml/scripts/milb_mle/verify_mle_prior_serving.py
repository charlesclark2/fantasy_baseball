"""verify_mle_prior_serving.py — E7.5b post-land SERVING verification for the MiLB MLE rookie prior.

WHY THIS EXISTS
---------------
CI mocks all IO, so it cannot see the failure mode that actually matters here: the prior parquet lands
correctly on S3, the offline gate was clean — and the SERVED path still reads nothing. This repo has
paid for that class repeatedly (INC-31's silently-100%-NULL feature block, the E9.26b swallowed read,
the E9.52 predicate that matched zero rows without raising). `milb_mle_prior` is joined into
`eb_batter_posteriors_raw` by a LEFT JOIN, so a dead join degrades SILENTLY to the generic prior: no
error, no HALT, no coverage alarm — just a served rookie prior that quietly stopped being the MLE.

So the check is not "did the file upload" (an `s3 ls` answers that, and would be the ⚠️ mtime trap
anyway — `aws s3 ls` prints LOCAL time). It is "does the join produce rows, and are the downstream
served columns populated". Read the CONTENT, never the mtime.

    AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.verify_mle_prior_serving

Exit 0 = the served path is intact. Exit 1 = a check failed (details on stdout). SF-FREE — pure
DuckDB over the S3 lakehouse.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# The metric columns eb_batter_posteriors_raw reads off the served parquet.
_PRIOR_COLS = ("mle_k_pct", "mle_bb_pct", "mle_iso")
_TABLES = ("milb_mle_prior", "eb_batter_posteriors_raw")


def classify_reach(hits: dict[str, int], n_cold: int, threshold: float = 0.90) -> tuple[str, list[str]]:
    """Classify the cold-start identity result into VERIFIED / PENDING_REBUILD / DEGRADED.

    ⚠️ WHY THIS IS NOT JUST A THRESHOLD (found the first time this script was run for real, 2026-08-01).
    Right after `--s3` lands a NEW prior, the served `eb_batter_posteriors_raw` still holds posteriors
    built against the OLD one, so the identity legitimately misses until the next W8a rebuild. A bare
    threshold reports that as "the join is degraded", which is the WRONG CAUSE and would send an operator
    hunting a join bug during the one window where a miss is expected.

    The discriminator is free and exact: `eb_batter_posteriors_raw` fetches all six prior columns through
    ONE LEFT JOIN on batter_id, so the join either matched a batter or it did not — it cannot match for
    one metric and miss for another. ⇒ if ANY metric hits on the same cold-start rows, the join is ALIVE
    by construction, and a metric that misses is a STALE downstream build, not a dead join. Only when
    EVERY metric misses is a dead join actually on the table.

    Both non-VERIFIED states are still failures (each needs an operator action) — they just name a
    different action. Returns (state, messages)."""
    if n_cold == 0:
        return "UNEVALUABLE", []
    missing = [m for m, h in hits.items() if h / n_cold < threshold]
    if not missing:
        return "VERIFIED", []
    if len(missing) == len(hits):
        return "DEGRADED", [
            f"{m}: only {hits[m]}/{n_cold} cold-start batters WITH an MLE prior serve the MLE value — "
            "EVERY metric misses, so the milb_mle_prior join is dead and those rookies are silently "
            "getting the ZiPS/generic prior instead" for m in missing]
    live = [m for m in hits if m not in missing]
    return "PENDING_REBUILD", [
        f"{m}: {hits[m]}/{n_cold} cold-start batters serve the MLE value, but {', '.join(live)} "
        f"hit ≥{threshold:.0%} on the SAME rows through the SAME join ⇒ the join is ALIVE and this is a "
        "STALE eb_batter_posteriors_raw, not a join defect. Run the W8a rebuild, then re-run this check."
        for m in missing]


def _connect():
    import duckdb

    from scripts.utils.delta_lakehouse import register_lakehouse_views
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("CREATE OR REPLACE SECRET s3_cred (TYPE S3, PROVIDER credential_chain, "
                 "REGION 'us-east-2')")
    register_lakehouse_views(conn, _TABLES)
    return conn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.5b — verify the served MiLB MLE rookie prior")
    p.add_argument("--season", type=int, default=None,
                   help="season to check the served join on (default: the newest in the EB table)")
    args = p.parse_args(argv)

    conn = _connect()
    failures: list[str] = []

    # ── 1. the landed prior itself ───────────────────────────────────────────────────
    cols = {r[0] for r in conn.execute("describe milb_mle_prior").fetchall()}
    n, *nonnull = conn.execute(
        "select count(*), " + ", ".join(f"count({c})" for c in _PRIOR_COLS) + " from milb_mle_prior"
    ).fetchone()
    print(f"[prior]  rows={n}  " + "  ".join(f"{c}={v}" for c, v in zip(_PRIOR_COLS, nonnull)))
    if n == 0:
        failures.append("milb_mle_prior is EMPTY — the served build will fall back to the generic prior")
    for c, v in zip(_PRIOR_COLS, nonnull):
        if v == 0:
            failures.append(f"milb_mle_prior.{c} is 100% NULL — that metric's MLE prior is dead")

    # E7.5b per-metric provenance. Absent on a pre-E7.5b parquet — reported, never a failure.
    src_cols = sorted(c for c in cols if c.endswith("_source"))
    if src_cols:
        for c in src_cols:
            mix = conn.execute(f"select {c}, count(*) from milb_mle_prior group by 1 order by 2 desc"
                               ).fetchall()
            print(f"[prov]   {c}: " + ", ".join(f"{k}={v}" for k, v in mix))
    else:
        print("[prov]   no <metric>_source columns — this parquet predates E7.5b")

    # ── 2. does the SERVED posterior actually carry the MLE? (the INC-31 silent class) ──
    # `eb_batter_posteriors_raw` does NOT expose the joined mle_* columns — they live inside its CTEs —
    # so "is the join alive" cannot be read off the served table directly. The precise instrument is the
    # model's own PA=0 identity: at pa=0 the SQL is `coalesce(mle_<m>, proj_<m>, generic)`, so a
    # cold-start batter WITH an MLE prior must serve eb_<m> == round(mle_<m>, 4). If the join were dead
    # he would silently serve the ZiPS/generic value instead — same shape, no error, wrong number. That
    # identity is a far stronger check than a non-null count, which a fully-degraded build also passes.
    season = args.season or conn.execute(
        "select max(season) from eb_batter_posteriors_raw").fetchone()[0]
    rows, eb_k, eb_bb, eb_iso = conn.execute(f"""
        select count(*), count(eb_k_pct), count(eb_bb_pct), count(eb_iso)
        from eb_batter_posteriors_raw where season = {int(season)}
    """).fetchone()
    print(f"[served] season={season} rows={rows} | non-null eb_k_pct={eb_k} eb_bb_pct={eb_bb} "
          f"eb_iso={eb_iso}")
    if rows == 0:
        failures.append(f"eb_batter_posteriors_raw has NO rows for season {season}")
    for label, v in (("eb_k_pct", eb_k), ("eb_bb_pct", eb_bb), ("eb_iso", eb_iso)):
        if rows and v == 0:
            failures.append(f"{label} is 100% NULL on season {season} — the served posterior "
                            "collapsed (the INC-31 class)")

    cold = conn.execute(f"""
        with cold as (
            select e.batter_id, e.eb_k_pct, e.eb_bb_pct, e.eb_iso,
                   m.mle_k_pct, m.mle_bb_pct, m.mle_iso
            from eb_batter_posteriors_raw e
            join milb_mle_prior m on m.batter_id::varchar = e.batter_id::varchar
            where e.season = {int(season)} and e.pa_weight = 0
        )
        select count(*),
               count(*) filter (where abs(eb_k_pct  - round(mle_k_pct,  4)) <= 5e-5),
               count(*) filter (where abs(eb_bb_pct - round(mle_bb_pct, 4)) <= 5e-5),
               count(*) filter (where abs(eb_iso    - round(mle_iso,    4)) <= 5e-5)
        from cold
    """).fetchone()
    n_cold, hit_k, hit_bb, hit_iso = cold
    print(f"[reach]  cold-start rows (pa_weight=0) WITH an MLE prior: {n_cold} | serving the MLE "
          f"value: k={hit_k} bb={hit_bb} iso={hit_iso}")
    state, messages = classify_reach(
        {"eb_k_pct": hit_k, "eb_bb_pct": hit_bb, "eb_iso": hit_iso}, n_cold)
    if state == "UNEVALUABLE":
        # NF1.7 (a): an unevaluable check is never scored as a passed one.
        print("[reach]  ⚠️ no cold-start rows to test on this season — the identity check is "
              "UNEVALUABLE, which is not the same as passed. Re-run on a season with rookie call-ups.")
    failures.extend(messages)

    print()
    if failures:
        banner = ("⏳ SERVED PRIOR NOT YET PROPAGATED — the landed parquet is fine, the downstream "
                  "table is stale" if state == "PENDING_REBUILD" else "❌ SERVING VERIFICATION FAILED")
        print(banner)
        for f in failures:
            print(f"   • {f}")
        return 1
    print("✅ served MiLB MLE rookie prior verified — the join is alive and the posteriors populate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
