const TEAM_ABBREV: Record<string, string> = {
  "Arizona Diamondbacks": "AZ",
  "Atlanta Braves": "ATL",
  "Baltimore Orioles": "BAL",
  "Boston Red Sox": "BOS",
  "Chicago Cubs": "CHC",
  "Chicago White Sox": "CWS",
  "Cincinnati Reds": "CIN",
  "Cleveland Guardians": "CLE",
  "Colorado Rockies": "COL",
  "Detroit Tigers": "DET",
  "Houston Astros": "HOU",
  "Kansas City Royals": "KC",
  "Los Angeles Angels": "LAA",
  "Los Angeles Dodgers": "LAD",
  "Miami Marlins": "MIA",
  "Milwaukee Brewers": "MIL",
  "Minnesota Twins": "MIN",
  "New York Mets": "NYM",
  "New York Yankees": "NYY",
  "Athletics": "ATH",
  "Oakland Athletics": "ATH",
  "Philadelphia Phillies": "PHI",
  "Pittsburgh Pirates": "PIT",
  "San Diego Padres": "SD",
  "San Francisco Giants": "SF",
  "Seattle Mariners": "SEA",
  "St. Louis Cardinals": "STL",
  "Tampa Bay Rays": "TB",
  "Texas Rangers": "TEX",
  "Toronto Blue Jays": "TOR",
  "Washington Nationals": "WSH",
}

export function normalizeTeam(name: string): string {
  return TEAM_ABBREV[name] ?? name
}

export function normalizeMatchup(matchup: string): string {
  const parts = matchup.split(" @ ")
  if (parts.length !== 2) return matchup
  return `${normalizeTeam(parts[0])} @ ${normalizeTeam(parts[1])}`
}

// Maps our internal abbreviations → ESPN CDN logo paths (where they differ)
const ESPN_CDN_OVERRIDE: Record<string, string> = {
  "AZ":  "ari",
  "CWS": "chw",
  "ATH": "oak",
}

export function espnLogoPath(teamNameOrAbbrev: string): string {
  const abbrev = normalizeTeam(teamNameOrAbbrev)
  return ESPN_CDN_OVERRIDE[abbrev] ?? abbrev.toLowerCase()
}
