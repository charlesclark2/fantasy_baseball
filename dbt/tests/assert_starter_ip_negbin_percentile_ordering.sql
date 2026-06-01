-- Asserts NegBin percentile ordering: p80_outs > ip_mu > p20_outs for every
-- row where starter_ip signals are available. A violation indicates a corrupted
-- dispersion parameter or clipping artifact from inference.
select
    game_pk,
    side,
    starter_ip_mu_v1,
    starter_ip_p80_outs_v1,
    starter_ip_p20_outs_v1
from {{ ref('feature_pregame_sub_model_signals') }}
where starter_ip_mu_v1_available = true
  and not (
        starter_ip_p80_outs_v1 > starter_ip_mu_v1
    and starter_ip_mu_v1       > starter_ip_p20_outs_v1
  )
