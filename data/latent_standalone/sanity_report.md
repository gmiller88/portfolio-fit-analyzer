# Sanity report: `latent_standalone`

> SYNTHETIC DATA. Realized aggregates versus scenario parameters; deviations over 10 percentage points are flagged.

**Result: CLEAN** (47 checks)

- Transcripts mentioning inference: **22** (ok)
- inference calibration scale applied to direct usage: 0.0447 (near cap, check)
- Transcripts mentioning edge_compute: **16** (ok)
- edge_compute calibration scale applied to direct usage: 0.2065 (ok)
- Transcripts linked to an account with usage history: **30/50** (60%)
- Transcripts mentioning neither product: 24%
- Never-won prospects (lost or open, no account): 40
- Realized standalone direct NRR, 12m: inference 2.047, edge 0.316

| Metric | Level | Param | Realized | Dev (pp) | n | Status |
|---|---|---|---|---|---|---|
| inference: standalone_demand_share | opps | 0.25 | 0.25 | +0.0 | 80 | ok |
| inference: standalone_demand_share | transcripts | 0.25 | 0.22 | -3.0 | 50 | ok |
| inference: bundled_mention_share | opps | 0.20 | 0.20 | +0.0 | 80 | ok |
| inference: bundled_mention_share | transcripts | 0.20 | 0.22 | +2.0 | 50 | ok |
| inference: buyer_initiated_share (standalone) | opps | 0.75 | 0.75 | +0.0 | 20 | ok |
| inference: buyer_initiated_share (standalone) | transcripts | 0.75 | 0.82 | +6.8 | 11 | ok |
| inference: standalone_win_rate | opps (closed) | 0.35 | 0.33 | -1.7 | 18 | ok |
| inference: bundled_win_rate | opps (closed) | 0.70 | 0.67 | -3.3 |  | ok |
| inference: loss_reason[price] | standalone lost opps | 0.30 | 0.33 | +3.3 | 12 | ok |
| inference: loss_reason[model_breadth] | standalone lost opps | 0.40 | 0.42 | +1.7 | 12 | ok |
| inference: loss_reason[latency] | standalone lost opps | 0.10 | 0.08 | -1.7 | 12 | ok |
| inference: loss_reason[compliance] | standalone lost opps | 0.10 | 0.08 | -1.7 | 12 | ok |
| inference: loss_reason[maturity] | standalone lost opps | 0.10 | 0.08 | -1.7 | 12 | ok |
| inference: loss_reason[single_vendor] | standalone lost opps | 0.00 | 0.00 | +0.0 | 12 | ok |
| inference: competitor[Together AI] | opps (first-named) | 0.35 | 0.36 | +1.1 | 36 | ok |
| inference: competitor[Fireworks] | opps (first-named) | 0.30 | 0.31 | +0.6 | 36 | ok |
| inference: competitor[Baseten] | opps (first-named) | 0.15 | 0.14 | -1.1 | 36 | ok |
| inference: competitor[OpenAI direct] | opps (first-named) | 0.20 | 0.19 | -0.6 | 36 | ok |
| inference: standalone_usage_share (revenue) | usage | 0.20 | 0.20 | +0.0 |  | ok |
| inference: standalone_retention_12m | direct cohort | 0.80 | 0.81 | +0.6 | 31 | ok |
| inference: selfserve_signup_share | signups | 0.14 | 0.14 | +0.0 |  | ok |
| inference: selfserve_paid_90d_rate | signups (no voice) | 0.12 | 0.12 | +0.2 | 147 | ok |
| inference: selfserve_paid_90d_rate_with_voice | signups (voice) | 0.24 | 0.24 | -0.2 | 63 | ok |
| edge_compute: standalone_demand_share | opps | 0.10 | 0.10 | +0.0 | 80 | ok |
| edge_compute: standalone_demand_share | transcripts | 0.10 | 0.06 | -4.0 | 50 | ok |
| edge_compute: bundled_mention_share | opps | 0.24 | 0.24 | -0.3 | 80 | ok |
| edge_compute: bundled_mention_share | transcripts | 0.24 | 0.26 | +2.0 | 50 | ok |
| edge_compute: buyer_initiated_share (standalone) | opps | 0.40 | 0.38 | -2.5 | 8 | ok |
| edge_compute: buyer_initiated_share (standalone) | transcripts | 0.40 | 0.33 | -6.7 | 3 | ok |
| edge_compute: standalone_win_rate | opps (closed) | 0.15 | 0.14 | -0.7 | 7 | ok |
| edge_compute: bundled_win_rate | opps (closed) | 0.70 | 0.72 | +2.2 |  | ok |
| edge_compute: loss_reason[price] | standalone lost opps | 0.34 | 0.33 | -0.7 | 6 | ok |
| edge_compute: loss_reason[model_breadth] | standalone lost opps | 0.00 | 0.00 | +0.0 | 6 | ok |
| edge_compute: loss_reason[latency] | standalone lost opps | 0.33 | 0.33 | +0.3 | 6 | ok |
| edge_compute: loss_reason[compliance] | standalone lost opps | 0.00 | 0.00 | +0.0 | 6 | ok |
| edge_compute: loss_reason[maturity] | standalone lost opps | 0.33 | 0.33 | +0.3 | 6 | ok |
| edge_compute: loss_reason[single_vendor] | standalone lost opps | 0.00 | 0.00 | +0.0 | 6 | ok |
| edge_compute: competitor[Cloudflare Workers] | opps (first-named) | 0.50 | 0.52 | +1.8 | 27 | ok |
| edge_compute: competitor[Fastly] | opps (first-named) | 0.20 | 0.19 | -1.5 | 27 | ok |
| edge_compute: competitor[AWS Lambda] | opps (first-named) | 0.30 | 0.30 | -0.4 | 27 | ok |
| edge_compute: standalone_usage_share (revenue) | usage | 0.12 | 0.12 | +0.0 |  | ok |
| edge_compute: standalone_retention_12m | direct cohort | 0.40 | 0.40 | +0.0 | 5 | ok |
| edge_compute: selfserve_signup_share | signups | 0.08 | 0.08 | +0.0 |  | ok |
| edge_compute: selfserve_paid_90d_rate | signups (no voice) | 0.02 | 0.02 | +0.4 | 84 | ok |
| edge_compute: selfserve_paid_90d_rate_with_voice | signups (voice) | 0.20 | 0.19 | -0.6 | 36 | ok |
| stated_vs_revealed_gap | won standalone-framed accts | 0.25 | 0.29 | +3.6 | 7 | ok |
| won share of transcripts | transcripts | 0.60 | 0.60 | +0.0 | 50 | ok |
