# Portfolio Fit Analyzer

> **SYNTHETIC DATA.** Every company, call, account and number is fictional and machine-generated (see `data/README.md`). Nothing here is a real Telnyx or market fact. The tool is a prototype for a PMM leadership exercise.

## What it is
A decision tool that answers one question for **AI Inference** and **Edge Compute**:

> Is each one a viable **standalone product** worth investing in as its own category, or mainly a **component of Voice AI**, worth investing in only as far as it makes Voice AI better?

It combines three evidence sources into a verdict per area, for the VP PMM and GTM leadership during quarterly investment planning:
1. **Behavioral:** usage and billing by account (`usage_monthly.csv`, `accounts.csv`), including whether Inference/Edge was invoked by a Voice AI agent or directly.
2. **Pipeline:** new-business sales transcripts and opportunities.
3. **Self-serve:** developer signups by entry product.

Two synthetic worlds ship with it: **`component`** (Inference and Edge are pulled in by Voice AI) and **`latent_standalone`** (real buyer-led standalone demand for Inference that Telnyx mostly fails to capture). Switching between them moves the Inference verdict from **Component of Voice AI** to **Latent standalone (diagnose losses)**; Edge stays a component in both.

## Run it
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py            # no API key needed: all LLM outputs are cached and committed
.venv/bin/python -m pytest -q tests       # 17 unit and integration tests
```
Agent/CLI access (JSON on stdout):
```bash
.venv/bin/python -m analyzer verdict --scenario latent_standalone --area inference --memo
.venv/bin/python -m analyzer verdict --scenario component --set pipeline.standalone_win_rate_min=0.4
.venv/bin/python -m analyzer validate --scenario component      # extraction accuracy vs the hidden answer key
.venv/bin/python -m analyzer extract --scenario component       # re-extract (Claude is only called on cache misses)
```
Layout: `analyzer/` is a pure-function package (metrics, verdict, extraction, validation, memo, CLI); `app.py` only renders; `analyzer/thresholds.yaml` holds every threshold; `analyzer/cache/` holds the committed LLM outputs; `data/` and `generator/` are from Prompt 1.

## How AI is used
All three uses are Claude through the Anthropic Python SDK (key from `ANTHROPIC_API_KEY`, model from `CLAUDE_MODEL`, default **`claude-sonnet-5-5`**; a `.env` at the repo root overrides a stale shell key). Outputs are cached on disk keyed by sha256 of input, model, prompt version and schema, and **committed for both scenarios**, so the demo runs instantly without a key. If you set a different `CLAUDE_MODEL`, the cache will miss; unset it to use the committed outputs.
1. **Transcript extraction (100 transcripts).** One tool whose input schema is the extraction schema (strict tool use, not free-text parsing). Fields: primary interest, use case, inference framing and who raised it, the same two for Edge, competitors per area, decision criteria, and the single biggest stated concern. Each field carries a **verbatim supporting quote** and a **confidence**; absent evidence returns `not_mentioned`. The app checks that every quote actually appears in the transcript.
2. **Validation against ground truth.** `analyzer/validation.py` is the only code that reads the generator's answer key (a test enforces this). Results below and on the app's *Data and validation* page.
3. **Verdict memo.** Claude writes a short memo per area from a FACTS object computed by code; it may cite only numbers in that object. A programmatic check confirms every number in the memo matches the facts (and that the recommendation equals the verdict), and flags the memo if not. Memos are cached for the default thresholds; when you move a slider the app falls back to a deterministic template memo and labels it as such.

Everything else (metrics, quadrants, thresholds) is deterministic code, not an LLM.

## Verdict logic
Two axes, thresholds in `analyzer/thresholds.yaml`, all exposed as sliders on the *Assumptions* page (verdicts recompute live):

| | Pipeline: real standalone demand, and it wins | Pipeline: little demand, rep-driven, or loses |
|---|---|---|
| **Behavior: standalone adoption** | Standalone business | Retention-led standalone (fix GTM before investing) |
| **Behavior: Voice AI-attached** | Latent standalone (diagnose losses) | Component of Voice AI |

- **Behavior axis:** standalone if the share of the product's revenue *not* invoked by Voice AI is at or above 30%.
- **Self-serve adjusts the behavior threshold** (documented precisely): if signups with this entry product pay within 90 days *without* voice at or above 8%, the threshold drops 5 points (independent developer pull). If the no-voice paid rate is below 4% *and* signups paired with voice convert at least 2x better, it rises 5 points (conversion depends on voice). Otherwise no change; no change either with fewer than 30 signups.
- **Pipeline axis:** strong only if all of: standalone demand share of transcripts at least 15%; at least 50% of standalone mentions raised by the buyer; standalone win rate at least 25%. The buyer-raised test guards against rep framing bias.
- **Evidence floor (default 8):** fewer than 8 transcripts discussing the product, fewer than 8 accounts using it, or fewer than 8 closed standalone deals when a win rate is needed yields **"Insufficient evidence"** instead of a quadrant.
- Every check is shown with its gap ("Standalone win rate is 4.0 pts below the threshold"), and inputs within 5 points of a line are flagged as sensitive.

## Results (committed scenarios)
| Scenario | AI Inference | Edge Compute |
|---|---|---|
| `component` | Component of Voice AI | Component of Voice AI |
| `latent_standalone` | **Latent standalone (diagnose losses)** | Component of Voice AI |

For `latent_standalone` Inference: 22% of calls frame it standalone, 73% of those raised by the buyer, standalone win rate 40% (bundled 67%), self-serve pays without voice at 12%, yet standalone is only 20% of revenue (threshold 25% after the self-serve adjustment): demand is real and Telnyx loses much of it, mainly on model breadth and price. Moving the behavior slider to 15% flips it to *Standalone business*; moving the minimum-sample slider to 30 flips both areas to *Insufficient evidence* (both checked in the app and in tests).

## Extraction validation (claim we verified)
Scored against the hidden answer key (exact match unless noted; 50 transcripts per scenario):

| Field | component | latent_standalone |
|---|---|---|
| **Inference framing** | 100% | 98% |
| **Inference raised by** | 98% | 96% |
| **Edge framing** | 100% | 100% |
| **Edge raised by** | 100% | 98% |
| **Framing + raised-by combined (target 85%)** | **99.5%** | **98.0%** |
| Primary interest / use case | 90% / 86% | 98% / 98% |
| Competitors: inference / edge / voice | 86% / 100% / 100% | 92% / 100% / 100% |
| Decision criteria (exact set; mean Jaccard) | 50% (0.85) | 48% (0.83) |
| Single biggest concern (lost deals only) | 69% | 35% |
| Quotes found verbatim in the transcript | 100% | 96% |

**Prompt iterations** (`analyzer/cache/prompt_history.json`): *v1* (initial) already cleared the 85% target on framing and raised-by (100% / 97.5%), so those were left alone. v1's decision-criteria exact-match was 12% / 8%: the extractor labelled routine logistics ("we'd need a security review", asking how pricing works) as criteria (recall was near perfect; precision was the problem). *v2* tightened that definition: criteria exact match rose to 50% / 48% (Jaccard about 0.85). One honest correction: my first scoring run showed 68% on raised-by, which was a bug in the validator (pandas read the truth value `n/a` as missing), fixed before any prompt change.

## Known limitations
- **Synthetic data, by design.** The verdicts demonstrate the method on worlds built to have a known answer; they say nothing about real Telnyx customers. Extraction was validated against transcripts written by an LLM from a brief, which is easier than real calls (cleaner speech, explicit statements). Real-world accuracy will be lower.
- **Small samples.** 50 transcripts per scenario; 5-11 standalone-framed calls, 3-10 closed standalone deals, 4 won accounts in the stated-vs-revealed test. Win rates and retention carry wide error bars; the app shows *n* beside them and flags inputs near a threshold. Several verdicts sit within 5 points of a threshold (flagged "sensitive").
- **"Single biggest concern" is weak** (35-69%): transcripts voice several concerns at once, so the loss-reason mix is directional. The pipeline page shows both the single concern and all concerns voiced.
- **Self-serve developers never appear in transcripts.** The pipeline axis sees sales-led buyers only; self-serve evidence enters only through the behavior-threshold adjustment and the signup table.
- **Rep framing bias.** Reps raise standalone offerings the buyer did not ask for; that is why "buyer-initiated share" is a gate and is reported separately.
- **12-month retention** is observable only for accounts that started at least 12 months before the end of an 18-month window, so cohorts are small. Mixed accounts (both paths) appear in both cohorts.
- The behavior axis uses revenue share; retention, NRR and margin are shown as supporting evidence and do not move the quadrant.

## Deploy a public link (no API key needed)
Streamlit Community Cloud: push the repo, create an app with main file `portfolio_fit_analyzer/app.py` (dependencies come from `portfolio_fit_analyzer/requirements.txt`; theme from `.streamlit/config.toml`). Everything the app needs is committed: `data/`, `analyzer/cache/`, thresholds. Do not set `CLAUDE_MODEL`, and do not add `ANTHROPIC_API_KEY`: the app reads only the cache. `analyzer/cache/` must be deployed with the code.
