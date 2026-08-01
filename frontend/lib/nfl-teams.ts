// NFL team → ESPN CDN logo slug. The fantasy export already normalizes every `team` field to a
// modern abbreviation (see export_draft_board_json.py's team-alias table — LA→LAR, OAK→LV, etc.),
// so no name→abbreviation step is needed here (unlike frontend/lib/teams.ts's MLB helper, which
// starts from full team names). ESPN's CDN slug matches our abbreviation lowercased for every team
// except Washington.
const ESPN_LOGO_OVERRIDE: Record<string, string> = {
  WAS: "wsh",
}

export function nflTeamLogoUrl(abbrev: string | null | undefined): string | null {
  if (!abbrev) return null
  const slug = ESPN_LOGO_OVERRIDE[abbrev] ?? abbrev.toLowerCase()
  return `https://a.espncdn.com/i/teamlogos/nfl/500/${slug}.png`
}

/** Up to two initials for an avatar placeholder — used until a real per-player photo source is
 *  wired into the export (nflverse's roster crosswalk carries an espn_id/sleeper_id today, but it
 *  isn't threaded through projections.json yet, so there's no stable photo id to fetch by). */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("")
}
