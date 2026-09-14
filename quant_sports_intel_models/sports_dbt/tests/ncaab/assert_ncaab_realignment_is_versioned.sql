-- A POSITIVE control on the SCD: realignment must actually PRODUCE versions.
--
-- ⚠️ The uniqueness test beside this one passes VACUOUSLY if the dimension collapses every
-- team to a single version — a dimension that versioned nothing would satisfy "one version per
-- season" perfectly while having silently lost the whole property it exists to provide. So
-- this asserts the other side: over a window containing the largest realignment in the sport's
-- history, many teams must carry multiple versions.
--
-- 🪤 THE FIRST CUT OF THIS TEST WAS MIS-SPECIFIED, and the way it failed is the lesson. It
-- asked for teams whose FIRST version starts at or after 2023 (`valid_from_season >= 2023`),
-- which is a question about teams that ENTERED the data late — 8 of them. The question it
-- meant to ask is which teams have more than one version whose validity REACHES 2023 or later,
-- i.e. who actually moved during the window — 80 of them, matching the 52+ movers measured
-- independently off the raw feed. A control that is mis-specified and FAILS is recoverable; a
-- control that is mis-specified and PASSES is the vacuous guard this file exists to prevent.
--
-- The floor is deliberately far below the measured 80, so ordinary source churn cannot trip it
-- while a dimension that stopped versioning fails immediately.
select
    'scd_versioning_is_inert' as failure,
    count(distinct team_id)   as movers
from {{ ref('dim_ncaab_team') }}
where n_versions > 1
  and valid_to_season >= 2023
having count(distinct team_id) < 25
