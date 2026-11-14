# Portfolio Fit Analyzer: synthetic datasets

> **SYNTHETIC DATA.** Every company, person, account, price, margin and call in this folder is fictional and machine-generated.
> Competitor vendors (Together AI, Cloudflare Workers, Twilio, ...) are real public names used only as vendors mentioned in
> fictional dialogue; any prices or claims attributed to them are invented. Unit prices and margins are illustrative, not Telnyx list prices.

Purpose: test whether Telnyx **AI Inference** and **Edge Compute** are viable standalone products or mostly components of **Voice AI**,
by combining behavioral (usage/billing), pipeline (sales calls and opportunities) and self-serve (signup) evidence.

## Design: generated from a hidden ground truth
Each scenario file (`scenarios/<name>.yaml`) sets explicit parameters. The generator allocates attributes by **exact quotas** (largest remainder),
so realized aggregates track the parameters closely, then writes transcripts from per-call briefs derived from `ground_truth/transcript_truth.csv`.
`ground_truth/` must **never be read by the analysis pipeline** except in a dedicated validation step.
Everything is seeded; regenerating from a scenario file reproduces the tables exactly (transcript prose is cached; see below).

## Scenarios
| Scenario | Story |
|---|---|
| `component` | Baseline. Inference and Edge are mostly pulled in by Voice AI agents. Standalone demand is low and mostly raised by reps, standalone deals often lose to specialist vendors, and self-serve Inference/Edge signups rarely convert to paid unless paired with voice. |
| `latent_standalone` | Real buyer-led standalone demand for Inference (Edge stays component-like). Telnyx loses many of the standalone Inference deals to specialist inference clouds on model breadth and price. Accounts that do buy standalone Inference retain and expand. |

## Layout (per scenario, `data/<scenario>/`)
`accounts.csv`, `usage_monthly.csv`, `opportunities.csv`, `signups.csv`, `transcripts/<opp_id>.md`, `sanity_report.md`,
`ground_truth/transcript_truth.csv`, `ground_truth/scenario_effective.json`.

## Data dictionary
**accounts.csv**: `account_id`; `company_name`; `segment` (self_serve|smb|mid_market|enterprise); `region` (NA|EMEA|LATAM|APAC|MEA); `industry`; `created_date`;
`acquisition_channel` (self_serve = converted from a paid signup, sales_led); `entry_product` (first product used).

**usage_monthly.csv**: `account_id`, `month` (YYYY-MM), `product`, `usage_units`, `unit`, `revenue_usd`, `gross_margin_usd`, `invoked_via`
(voice_ai_agent | direct_api | webhook | other). For `inference` and `edge_compute`, `voice_ai_agent` means pulled in by a Voice AI agent; any other value is
direct (standalone) use. One row per account, month, product and invoking path, so an account can have both. Products and areas:
communications (voice_api, sip_trunking, messaging, numbers, voice_ai_agents), AI inference (inference), Edge Compute (edge_compute),
developer infrastructure (cloud_storage, networking). Prices and margins live in `scenarios/_shared/products.yaml`; inference has the lowest margin (GPU cost).
Aggregate direct-vs-voice revenue for inference/edge is calibrated to `standalone_usage_share`.

**opportunities.csv**: `opp_id`; `account_id` (set only for won deals; blank for lost/open prospects who never became customers); `prospect_name`; `created_date`; `close_date` (blank if open);
`stage`; `outcome` (won|lost|open); `amount_usd`; `primary_product`; `products_discussed` (pipe list); `rep_name`; `segment`; `region`.

**signups.csv**: `signup_id`, `signup_date`, `entry_product`, `activated`, `paid_90d`, `products_at_90d` (pipe list), `converted_account_id` (paid signups map to self_serve accounts).

**transcripts/<opp_id>.md**: sales call (discovery or demo) with a header (date, call type, opp_id, participants) and speaker-labelled turns. No outcome appears in the text.
About 60% belong to won opportunities with a linked account, enabling the stated-versus-revealed comparison.

**ground_truth/transcript_truth.csv** (lists are pipe-separated): `opp_id, primary_interest, use_case, inference_framing (standalone|bundled_with_voice|not_mentioned),
inference_raised_by (buyer|rep|n/a), edge_framing, edge_raised_by, competitors_inference, competitors_edge, competitors_voice, decision_criteria, outcome,
primary_loss_reason (n/a unless lost), segment`.
Definitions: *standalone* = discussed as a separately purchased workload independent of Voice AI agents; *bundled_with_voice* = needed only as part of a voice agent;
*raised_by* = who first brings the product up; competitors are listed in the order they matter (first = main rival). Loss reasons: price, model_breadth, latency,
compliance, maturity, single_vendor (buyer prefers to keep the workload with an incumbent cloud/AI vendor).

**ground_truth/scenario_effective.json**: realized aggregates after sampling, at opportunity, transcript, behavioral and self-serve level.

## Regenerate
```bash
pip install -r requirements.txt
python -m generator --scenario component          # one scenario
python -m generator --all                         # every scenario in scenarios/
python -m generator --all --transcripts template  # offline, no API key (template fallback)
python -m generator --scenario component --regenerate-transcripts   # rewrite cached prose
```
Transcripts use the Anthropic SDK (`ANTHROPIC_API_KEY`, model from `CLAUDE_MODEL`, default `claude-sonnet-5-5`) and fall back to templates without a key.
Cached files record their source and a brief hash in `transcripts/.cache_index.json`; if ground truth changes, the generator refuses to reuse stale prose until you pass `--regenerate-transcripts`.
