# E5.3 — Name→ID join coverage (S3 K closing lines → E5.2 predictions)

_Bridge: `ref_players` name dimension → modelled pitcher_id, via `prop_edge.normalize_name` (accents / punctuation / Jr.–Sr. folded), restricted to the 26,062 modelled pitcher×date predictions._

| metric | value |
|---|---|
| player×date closing-line keys | 7,774 |
| **resolved to a prediction** | **7,351 (94.6%)** |
| book-line rows total | 66,124 |
| book-line rows resolved | 63,765 |
| resolved via full name | 7,073 |
| resolved via (last, initial) fallback | 278 |

_The (last, initial) fallback folds the feed's full legal names vs ref's common names ("Matthew Boyd"↔"Matt Boyd", "Joseph Ryan"↔"Joe Ryan"), resolved against the game-date window so collisions stay rare._

## Resolution status (player×date keys)

| status | n |
|---|---|
| resolved | 7,351 |
| unresolved_no_start_that_date | 302 |
| unresolved_name_not_modelled | 112 |
| unresolved_ambiguous_no_start_that_date | 6 |
| ambiguous_same_name_same_date | 3 |

## Top unresolved names (FLAGGED — not silently dropped)

_Most are relievers / non-modelled starters / one-off spellings; a high-count name here would signal a systematic bridge miss to fix._

| player_name | reason | n |
|---|---|---|
| Yoshinobu Yamamoto | unresolved_no_start_that_date | 9 |
| Walbert Urena | unresolved_name_not_modelled | 8 |
| Anthony Gonsolin | unresolved_name_not_modelled | 7 |
| Tatsuya Imai | unresolved_name_not_modelled | 7 |
| Carlos Rodon | unresolved_no_start_that_date | 6 |
| Noah Schultz | unresolved_name_not_modelled | 6 |
| Max Scherzer | unresolved_no_start_that_date | 6 |
| Kenneth Kelly | unresolved_name_not_modelled | 6 |
| Zac Gallen | unresolved_no_start_that_date | 6 |
| John Ober | unresolved_name_not_modelled | 5 |
| Andrew Painter | unresolved_name_not_modelled | 5 |
| Michael Lynn | unresolved_name_not_modelled | 5 |
| George Kirby | unresolved_no_start_that_date | 5 |
| Jacob Lugo | unresolved_name_not_modelled | 5 |
| Shane Bieber | unresolved_no_start_that_date | 4 |
| Tarik Skubal | unresolved_no_start_that_date | 4 |
| Trey Yesavage | unresolved_no_start_that_date | 4 |
| Jared Triolo | unresolved_name_not_modelled | 4 |
| Nathan Eovaldi | unresolved_no_start_that_date | 4 |
| Shohei Ohtani | unresolved_no_start_that_date | 4 |
| Brandon Pfaadt | unresolved_no_start_that_date | 4 |
| Jack Flaherty | unresolved_no_start_that_date | 4 |
| Todd Smyly | unresolved_name_not_modelled | 4 |
| Blake Snell | unresolved_no_start_that_date | 4 |
| Connor Prielipp | unresolved_name_not_modelled | 4 |
| Gerrit Cole | unresolved_no_start_that_date | 4 |
| Robert Miller | unresolved_name_not_modelled | 4 |
| Edward Lively | unresolved_name_not_modelled | 4 |
| Robert Anderson | unresolved_name_not_modelled | 4 |
| Osvaldo Bido | unresolved_no_start_that_date | 3 |
| Donald Zackary Greinke | unresolved_name_not_modelled | 3 |
| Douglas Ashcraft | unresolved_name_not_modelled | 3 |
| Miles Mikolas | unresolved_no_start_that_date | 3 |
| Gage Jump | unresolved_name_not_modelled | 3 |
| Dylan Cease | unresolved_no_start_that_date | 3 |
| Zack Wheeler | unresolved_no_start_that_date | 3 |
| Matthew Boyd | unresolved_no_start_that_date | 3 |
| Merrill Kelly | unresolved_no_start_that_date | 3 |
| Aaron Nola | unresolved_no_start_that_date | 3 |
| Walker Buehler | unresolved_no_start_that_date | 3 |

> Unresolved ≠ error: a closing line resolves only if the named pitcher is a starter we model AND has a prediction on that game_date. Relievers, openers, and DNPs legitimately have no K-distribution to compare. best_alpha = 0 — this is a comparison table, not a bet rec.
