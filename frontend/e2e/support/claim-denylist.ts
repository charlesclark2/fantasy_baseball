// NF-TR1 — the overclaim denylist, mirrored for the browser.
//
// ⚠️ THIS IS A MIRROR, NOT A SECOND SOURCE OF TRUTH. The authority is
// `export_track_record_json._CLAIM_DENYLIST`, and a mirror that can drift from its original is
// worse than no mirror — it would go on passing while the real list grew a term it never learned.
// `betting_ml/tests/test_nf_tr1_claim_copy.py::test_the_browser_denylist_mirror_matches_the_export`
// asserts SET EQUALITY between this array and the Python tuple, so adding a term in one place and
// not the other is a red build rather than a silent hole.
//
// WHY MIRROR IT AT ALL: the Python screening runs over what the EXPORTER generates. This one runs
// over what the BROWSER renders — which also includes every static string a component contributes
// (headings, table labels, CTA text, the empty states). Those never pass through `build_claim`, so
// no amount of export-side screening can see them, and they are exactly where a well-meaning copy
// edit would put "beat ADP".
export const CLAIM_DENYLIST: readonly string[] = [
  // the original NF3.2 set
  "we beat",
  "beat the market",
  "beat consensus",
  "every position",
  "all four",
  "our edge",
  "guaranteed",
  "more accurate",
  // the governance-gate set (betting_ml/governance/gates._DEFAULT_CLAIM_DENYLIST)
  "beats the market",
  "outperforms the market",
  "market-beating",
  "profitable",
  "edge over the market",
  // the plain-English overclaims NF-TR1's consumer lead could reach for
  "beats adp",
  "beat adp",
  "beats ecr",
  "beat ecr",
  "win your league",
  "wins your league",
  "sure thing",
  "can't miss",
  "risk-free",
  "always right",
  "never wrong",
]

/** Every denied phrase present in `text`, lowercased-substring, in the order they are listed. */
export function forbiddenPhrasesIn(text: string): string[] {
  const lowered = text.toLowerCase()
  return CLAIM_DENYLIST.filter((term) => lowered.includes(term))
}
