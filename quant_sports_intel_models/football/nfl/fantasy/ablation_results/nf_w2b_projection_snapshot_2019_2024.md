# NF-W2b — pre/post-flip projection snapshot

**Generated:** 2026-08-09T04:57:24+00:00 · **folds:** 2019H1, 2019H2, 2020H1, 2020H2, 2021H1, 2021H2, 2022H1, 2022H2, 2023H1, 2023H2, 2024H1, 2024H2 · **rows:** 51092 · per-row record: `quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w2b_projection_snapshot_2019_2024.parquet` (gitignored)

Pre-flip = the NF-W1 champion spec; post-flip = the NF-W2b validated winners (artifact-pinned). Positive `mean_crps_delta` = the post-flip model is better.

|    |   n_rows |   mean_crps_pre |   mean_crps_post |   mean_crps_delta |   mean_abs_delta_q50 |   share_moved_gt_1ppr |   share_moved_gt_3ppr |   listed_rows |   listed_mean_abs_delta_q50 |
|:---|---------:|----------------:|-----------------:|------------------:|---------------------:|----------------------:|----------------------:|--------------:|----------------------------:|
| QB |     8111 |          2.5914 |           2.4747 |            0.1167 |               0.635  |                0.1764 |                0.0361 |          1055 |                      2.0383 |
| RB |    13102 |          2.6233 |           2.481  |            0.1423 |               0.6867 |                0.1857 |                0.0374 |          2448 |                      1.7631 |
| WR |    18873 |          2.8042 |           2.6733 |            0.1309 |               0.7247 |                0.2211 |                0.0418 |          4141 |                      1.6221 |
| TE |    11006 |          1.855  |           1.7947 |            0.0603 |               0.4395 |                0.1407 |                0.0174 |          1961 |                      0.9555 |

```json
{
  "generated_at": "2026-08-09T04:57:24+00:00",
  "story": "NF-W2b flip tracking",
  "season": 2024,
  "half": null,
  "folds": [
    "2019H1",
    "2019H2",
    "2020H1",
    "2020H2",
    "2021H1",
    "2021H2",
    "2022H1",
    "2022H2",
    "2023H1",
    "2023H2",
    "2024H1",
    "2024H2"
  ],
  "n_rows": 51092,
  "pre_flip_spec": {
    "QB": "base_noRate",
    "RB": "base_noRate",
    "WR": "base_noRate",
    "TE": "base_noRate"
  },
  "post_flip_spec": {
    "QB": "inj_zero_leg",
    "RB": "inj_both",
    "WR": "inj_both",
    "TE": "inj_zero_leg"
  },
  "parquet": "quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w2b_projection_snapshot_2019_2024.parquet",
  "positions": {
    "QB": {
      "n_rows": 8111,
      "mean_crps_pre": 2.5914,
      "mean_crps_post": 2.4747,
      "mean_crps_delta": 0.1167,
      "mean_abs_delta_q50": 0.635,
      "share_moved_gt_1ppr": 0.1764,
      "share_moved_gt_3ppr": 0.0361,
      "listed_rows": 1055,
      "listed_mean_abs_delta_q50": 2.0383
    },
    "RB": {
      "n_rows": 13102,
      "mean_crps_pre": 2.6233,
      "mean_crps_post": 2.481,
      "mean_crps_delta": 0.1423,
      "mean_abs_delta_q50": 0.6867,
      "share_moved_gt_1ppr": 0.1857,
      "share_moved_gt_3ppr": 0.0374,
      "listed_rows": 2448,
      "listed_mean_abs_delta_q50": 1.7631
    },
    "WR": {
      "n_rows": 18873,
      "mean_crps_pre": 2.8042,
      "mean_crps_post": 2.6733,
      "mean_crps_delta": 0.1309,
      "mean_abs_delta_q50": 0.7247,
      "share_moved_gt_1ppr": 0.2211,
      "share_moved_gt_3ppr": 0.0418,
      "listed_rows": 4141,
      "listed_mean_abs_delta_q50": 1.6221
    },
    "TE": {
      "n_rows": 11006,
      "mean_crps_pre": 1.855,
      "mean_crps_post": 1.7947,
      "mean_crps_delta": 0.0603,
      "mean_abs_delta_q50": 0.4395,
      "share_moved_gt_1ppr": 0.1407,
      "share_moved_gt_3ppr": 0.0174,
      "listed_rows": 1961,
      "listed_mean_abs_delta_q50": 0.9555
    }
  }
}
```