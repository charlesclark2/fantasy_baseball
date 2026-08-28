"use client"

// NCAAF-P3.9 — the team mark in a game card's header.
//
// ⛔ DECORATIVE ONLY. The card's content is the win probability and the two curves; a logo adds
// recognition, never information. So it is `aria-hidden` (the team NAME is the accessible label,
// immediately beside it), it is sized well below the probability so the P3 brand directive's lead
// clause survives, and its box is FIXED — the fallback occupies the identical square, so whether
// the image loads or fails nothing below it moves.

import { useState } from "react"

/** ESPN's college-football team mark.
 *
 * ⭐ THE PAYLOAD'S `team_id` IS THE ESPN ID — this is the whole reason the rider is a frontend-only
 * change. Verified against the live CDN at build time for all sixteen 2026-08-29 opener teams
 * (2628, 153, 30, 23, 258, 152, 2449, 55, 2199, 16, 24, 62, 52, 166, 2439, 235): every one is a
 * 200 image/png. An unknown id answers 404, which is what drives the fallback below.
 *
 * ⚠️ `a.espncdn.com` is ALREADY in the CSP `img-src` allowlist (`next.config.mjs`) — it is what the
 * MLB game page and the home page's fantasy card render from. E9.46's lesson is why that is stated
 * rather than assumed: a CSP refusal has NO server-side signal and presents identically to "there
 * is no image for this team", so a new host would fail silently and product-wide. */
export function espnNcaafLogoUrl(teamId: number): string {
  return `https://a.espncdn.com/i/teamlogos/ncaa/500/${teamId}.png`
}

/**
 * ⭐ THE MISSING STATE IS A STATED FALLBACK, NEVER INITIALS (E9.46, bound by this story's spec).
 *
 * `player-page.tsx` and the home page's fantasy card both fall back to a player's INITIALS, and
 * E9.46 recorded what that cost: `static.www.nfl.com` was absent from the CSP `img-src` allowlist
 * for as long as it existed, and every blocked headshot in the product presented as "this player
 * has no photo" — a defect wearing the costume of ordinary missing data. Two-letter initials beside
 * a college team read exactly like a real team abbreviation ("NC", "TC"), so the same fallback here
 * would be worse still: it would read as DATA we published rather than as an image we failed to
 * load.
 *
 * So the fallback is a mark that could not be mistaken for team identity — a dashed square with a
 * muted glyph — and it carries its own testid so a spec can tell the two states apart. It says "no
 * mark", which is a fact about the image; initials would say something about the team.
 */
export function NcaafTeamLogo({
  teamId,
  teamName,
}: {
  teamId: number | null
  teamName: string
}) {
  const [failed, setFailed] = useState(false)

  // ⚠️ ONE SHARED SIZE STRING for both branches. Two copies is how the fallback drifts to a
  // different box and reintroduces the layout shift this component is written to avoid.
  const box = "h-5 w-5 shrink-0"

  if (teamId == null || failed) {
    return (
      <span
        data-testid="ncaaf-team-logo-fallback"
        data-team-logo="fallback"
        aria-hidden="true"
        title={`No team mark for ${teamName}`}
        className={
          `${box} inline-flex items-center justify-center rounded-[3px] border border-dashed ` +
          "border-[#3a3a3a] text-[9px] leading-none text-gray-600"
        }
      >
        {/* ⛔ NOT the team's initials — see the component header. A neutral glyph is unambiguous
            about what it is: an image we do not have. */}
        ?
      </span>
    )
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- ESPN serves a pre-sized asset per URL;
    // next/image would re-proxy it for no benefit and needs a remotePattern entry. The MLB game
    // page and `featured-fantasy-player.tsx` render the same host the same way.
    <img
      src={espnNcaafLogoUrl(teamId)}
      alt=""
      aria-hidden="true"
      data-testid="ncaaf-team-logo"
      data-team-id={teamId}
      // ⚠️ width/height are declared as ATTRIBUTES as well as classes so the box is reserved
      // before the bytes arrive — a logo that pops in and reflows the header would move the
      // probability, which is the one thing this rider may not do.
      width={20}
      height={20}
      loading="lazy"
      onError={() => setFailed(true)}
      className={`${box} object-contain`}
    />
  )
}
