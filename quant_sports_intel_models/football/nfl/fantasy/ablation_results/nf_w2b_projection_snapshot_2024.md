# NF-W2b — pre/post-flip projection snapshot

**Generated:** 2026-08-09T04:29:25+00:00 · **folds:** 2024H1, 2024H2 · **rows:** 8577 · per-row record: `quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w2b_projection_snapshot_2024.parquet` (gitignored)

Pre-flip = the NF-W1 champion spec; post-flip = the NF-W2b validated winners (artifact-pinned). Positive `mean_crps_delta` = the post-flip model is better.

|    |   n_rows |   mean_crps_pre |   mean_crps_post |   mean_crps_delta |   mean_abs_delta_q50 |   share_moved_gt_1ppr |   share_moved_gt_3ppr |   listed_rows |   listed_mean_abs_delta_q50 |
|:---|---------:|----------------:|-----------------:|------------------:|---------------------:|----------------------:|----------------------:|--------------:|----------------------------:|
| QB |     1361 |          2.6339 |           2.503  |            0.1309 |               0.5584 |                0.1609 |                0.0331 |           184 |                      1.9474 |
| RB |     2102 |          2.551  |           2.3947 |            0.1562 |               0.6385 |                0.1499 |                0.0366 |           371 |                      1.8949 |
| WR |     3185 |          2.7165 |           2.5974 |            0.1192 |               0.6723 |                0.1881 |                0.0396 |           698 |                      1.5836 |
| TE |     1929 |          1.8003 |           1.7279 |            0.0723 |               0.3886 |                0.1146 |                0.0166 |           352 |                      0.8907 |

```json
{
  "generated_at": "2026-08-09T04:29:25+00:00",
  "story": "NF-W2b flip tracking",
  "season": 2024,
  "half": null,
  "folds": [
    "2024H1",
    "2024H2"
  ],
  "n_rows": 8577,
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
  "parquet": "quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_w2b_projection_snapshot_2024.parquet",
  "positions": {
    "QB": {
      "n_rows": 1361,
      "mean_crps_pre": 2.6339,
      "mean_crps_post": 2.503,
      "mean_crps_delta": 0.1309,
      "mean_abs_delta_q50": 0.5584,
      "share_moved_gt_1ppr": 0.1609,
      "share_moved_gt_3ppr": 0.0331,
      "listed_rows": 184,
      "listed_mean_abs_delta_q50": 1.9474
    },
    "RB": {
      "n_rows": 2102,
      "mean_crps_pre": 2.551,
      "mean_crps_post": 2.3947,
      "mean_crps_delta": 0.1562,
      "mean_abs_delta_q50": 0.6385,
      "share_moved_gt_1ppr": 0.1499,
      "share_moved_gt_3ppr": 0.0366,
      "listed_rows": 371,
      "listed_mean_abs_delta_q50": 1.8949
    },
    "WR": {
      "n_rows": 3185,
      "mean_crps_pre": 2.7165,
      "mean_crps_post": 2.5974,
      "mean_crps_delta": 0.1192,
      "mean_abs_delta_q50": 0.6723,
      "share_moved_gt_1ppr": 0.1881,
      "share_moved_gt_3ppr": 0.0396,
      "listed_rows": 698,
      "listed_mean_abs_delta_q50": 1.5836
    },
    "TE": {
      "n_rows": 1929,
      "mean_crps_pre": 1.8003,
      "mean_crps_post": 1.7279,
      "mean_crps_delta": 0.0723,
      "mean_abs_delta_q50": 0.3886,
      "share_moved_gt_1ppr": 0.1146,
      "share_moved_gt_3ppr": 0.0166,
      "listed_rows": 352,
      "listed_mean_abs_delta_q50": 0.8907
    }
  }
}
```