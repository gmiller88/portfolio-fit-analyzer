"""Sales-call transcripts: Claude writes the prose from a structured brief; a template fallback works offline.
Briefs derive from ground truth only. Outcomes never appear in the text."""
import hashlib, json, os, random, re, zlib
from concurrent.futures import ThreadPoolExecutor
from . import names

MIN_W, MAX_W = 600, 1250
CRIT_TXT = {
    "price": "price (per-token, per-minute and overall cost)", "model_breadth": "breadth of model selection (needs to swap between several open models)",
    "latency": "latency (time to first token / round-trip time)", "compliance": "data residency and compliance (a DPA, data staying in-region)",
    "maturity": "how proven and mature the vendor is for production AI workloads", "single_vendor": "preference to consolidate with their existing cloud/AI vendor",
    "reliability": "reliability and uptime SLAs", "integration_effort": "integration effort and time to deploy", "support_quality": "support quality and escalation paths",
    "voice_quality": "voice quality and call completion", "cost_predictability": "cost predictability (no surprise bills)"}

def brief(o, scenario):
    r = random.Random(zlib.crc32((scenario + o["opp_id"]).encode()))
    used = {o["rep_name"]}
    title = r.choice(names.REP_TITLES)
    b1 = names.person(r, used); b2 = names.person(r, used) if r.random() < 0.5 else None
    roles = names.BUYER_ROLES.get(o["industry"], names.BUYER_ROLES["default"])
    b1r = r.choice(names.BUYER_ROLES["software"] if o["primary_interest"] in ("inference", "edge_compute") else roles)
    return {"opp_id": o["opp_id"], "date": o["call_date"].isoformat(), "call_type": r.choice(["Discovery call", "Discovery call", "Product demo"]),
            "company": o["prospect_name"], "industry": o["industry"], "segment": o["segment"], "region": o["region"],
            "rep": {"name": o["rep_name"], "title": title}, "buyer1": {"name": b1, "role": b1r}, "buyer2": {"name": b2, "role": r.choice(["Senior Engineer", "Procurement Manager", "Security Lead", "Operations Manager"])} if b2 else None,
            "primary_interest": o["primary_interest"], "use_case": o["use_case"],
            "inference_framing": o["inference_framing"], "inference_raised_by": o["inference_raised_by"],
            "edge_framing": o["edge_framing"], "edge_raised_by": o["edge_raised_by"],
            "competitors_inference": o["competitors_inference"], "competitors_edge": o["competitors_edge"], "competitors_voice": o["competitors_voice"],
            "decision_criteria": o["decision_criteria"], "depth": o["depth"], "vague_buyer": o["vague"], "facts": o["facts"]}

def header(b):
    p = [f"{b['rep']['name']} ({b['rep']['title']}, Telnyx)", f"{b['buyer1']['name']} ({b['buyer1']['role']}, {b['company']})"]
    if b["buyer2"]: p.append(f"{b['buyer2']['name']} ({b['buyer2']['role']}, {b['company']})")
    return (f"# Sales Call Transcript\n\n> SYNTHETIC DATA. Fictional company and people. Generated for prototype testing.\n\n"
            f"- **Opportunity:** {b['opp_id']}\n- **Date:** {b['date']}\n- **Call type:** {b['call_type']}\n- **Company:** {b['company']}\n"
            f"- **Participants:** {'; '.join(p)}\n\n---\n\n")

def label(b, who):
    if who == "R": return f"**{b['rep']['name']} ({b['rep']['title']}, Telnyx):**"
    if who == "B2" and b["buyer2"]: return f"**{b['buyer2']['name']} ({b['buyer2']['role']}, {b['company']}):**"
    return f"**{b['buyer1']['name']} ({b['buyer1']['role']}, {b['company']}):**"

# ---------------------------------------------------------------- LLM
def llm_prompt(b):
    f = b["facts"]
    who = lambda w: b["rep"]["name"] if w == "rep" else b["buyer1"]["name"]
    lines = [f"Write the spoken dialogue of a realistic B2B sales call between a Telnyx sales rep and a prospect. {MIN_W}-1,100 words. This is for a synthetic dataset; all names are fictional.",
             "", "CALL FACTS",
             f"- Telnyx rep: {b['rep']['name']} ({b['rep']['title']}). Buyer: {b['buyer1']['name']} ({b['buyer1']['role']}), company {b['company']} ({b['industry']}, {b['segment']}, {b['region']})."]
    if b["buyer2"]: lines.append(f"- Also on the call: {b['buyer2']['name']} ({b['buyer2']['role']}).")
    lines += [f"- Call type: {b['call_type']}. Primary thing the buyer came to discuss: {b['primary_interest']}. Use case: {b['use_case'].replace('_', ' ')}.",
              f"- Buyer style: {'vague and non-committal, answers in generalities' if b['vague_buyer'] else 'clear and specific'}. Depth of any Inference/Edge discussion: {b['depth']} (passing = a brief aside; moderate = a few exchanges; deep = a substantial section)."]
    for area, name, fr, rb, comps in (("inference", "AI Inference (hosted LLM API)", b["inference_framing"], b["inference_raised_by"], b["competitors_inference"]),
                                      ("edge", "Edge Compute (run code/functions near users)", b["edge_framing"], b["edge_raised_by"], b["competitors_edge"])):
        if fr == "not_mentioned":
            lines.append(f"- {name}: NOT mentioned at all. Do not discuss {'inference, LLM hosting or token pricing' if area == 'inference' else 'edge compute or edge functions'} as a Telnyx product.")
            continue
        if fr == "standalone":
            fr_txt = ("discussed as a SEPARATE, independently purchasable workload that does not depend on Telnyx Voice AI agents "
                      "(the workload lives in the buyer's own application or pipeline and would be bought by itself via API)")
        else:
            fr_txt = "discussed ONLY as a component of a Telnyx Voice AI agent (needed to make the voice agent work; not wanted as its own product)"
        first = who("buyer" if rb == "buyer" else "rep")
        lines.append(f"- {name}: {fr_txt}. The FIRST person to bring it up must be {first} ({'the buyer, unprompted' if rb == 'buyer' else 'the rep, pushing it; the buyer did not ask'}).")
        if comps: lines.append(f"  Competitors the buyer is evaluating or using for this: {', '.join(comps)} (name them explicitly, exactly as written).")
    if b["competitors_voice"]: lines.append(f"- Voice/telephony vendors the buyer mentions currently using or evaluating: {', '.join(b['competitors_voice'])} (name them explicitly, exactly as written).")
    else: lines.append("- The buyer names no voice vendor competitors.")
    lines.append("- The buyer's decision criteria, each of which must come out naturally in the conversation as something they care about or worry about: " + "; ".join(CRIT_TXT[c] for c in b["decision_criteria"]) + ".")
    crit = b["decision_criteria"]; inf_on = b["inference_framing"] != "not_mentioned"; edge_on = b["edge_framing"] != "not_mentioned"
    spec = []
    if inf_on:
        spec.append(f"- A competitor's quoted price is about ${f['comp_price_per_m']} per million tokens; Telnyx's quote is about ${f['telnyx_price_per_m']} per million tokens. Models of interest: {f['models'][0]} and {f['models'][1]}. Volume about {f['volume_m_tokens']}M tokens/month.")
        if "latency" in crit: spec.append(f"- Time-to-first-token target {f['ttft_ms']} ms.")
    if edge_on and "latency" in crit: spec.append(f"- Edge p95 latency target {f['edge_p95_ms']} ms.")
    if "compliance" in crit: spec.append(f"- Data residency requirement: {f['residency']} (needs a DPA).")
    spec.append(f"- Scale: about {f['concurrency']} concurrent calls at peak; {f['agents']} voice agents planned.")
    lines += ["", "SPECIFICS TO WEAVE IN WHERE RELEVANT (use these exact numbers; they are fictional). Use ONLY these; do not add other numbers or concerns of these kinds"] + spec + [
              "", "RULES",
              "- Format: alternating speaker lines like `**Name (Role, Company):** text`, blank line between turns. No stage directions, no summary, no title, no preamble.",
              "- Realistic spoken language: hesitations, interruptions, half-answers, tangents about unrelated stuff (security review, porting numbers, timeline). Not every question gets a direct answer.",
              "- The buyer must not raise concerns beyond the decision criteria listed above (e.g. no latency worries, residency, price-per-token talk or vendor-maturity doubts unless listed). Small talk and logistics are fine.",
              "- Do NOT reveal or imply whether the deal is won or lost, and do not mention a decision, a contract signature, or that the buyer chose anyone. End with neutral next steps (e.g., send a proposal, schedule a technical session).",
              "- Never say the data is synthetic. Do not include the competitors or facts above that this brief does not list. Do not discuss Inference or Edge beyond what is specified above.",
              "- Output only the transcript dialogue."]
    return "\n".join(lines)

def _words(t): return len(re.findall(r"\S+", t))

def _clean(t):
    t = t.strip()
    t = re.sub(r"^```\w*\n|\n```$", "", t).strip()
    return t

def _check(b, text):
    miss = [c for c in b["competitors_inference"] + b["competitors_edge"] + b["competitors_voice"] if c.lower() not in text.lower()]
    w = _words(text); bad = []
    if w < MIN_W - 40 or w > MAX_W: bad.append(f"length {w} words (need {MIN_W}-1100)")
    if miss: bad.append("missing competitor names: " + ", ".join(miss))
    low = text.lower()
    if b["inference_framing"] == "not_mentioned" and re.search(r"per million tokens|tokens (a|per) month|inference api", low): bad.append("mentions inference although it must not be discussed")
    if b["edge_framing"] == "not_mentioned" and re.search(r"edge compute|edge function", low): bad.append("mentions edge compute although it must not be discussed")
    if "compliance" not in b["decision_criteria"] and re.search(r"residency|\bdpa\b", low): bad.append("raises data residency/DPA, which is not a listed criterion")
    if "latency" not in b["decision_criteria"] and re.search(r"time to first token|\bp95\b", low): bad.append("raises latency targets, which is not a listed criterion")
    if re.search(r"synthetic|closed[- ]won|closed[- ]lost|we lost|we won", text, re.I): bad.append("contains outcome/synthetic language")
    return bad

def llm_transcript(b, client, model):
    prompt = llm_prompt(b); extra = ""
    for attempt in range(3):
        msg = client.messages.create(model=model, max_tokens=4000, output_config={"effort": "low"},
                                     messages=[{"role": "user", "content": prompt + extra}])
        if msg.stop_reason == "refusal": raise RuntimeError("refusal")
        text = _clean("".join(x.text for x in msg.content if x.type == "text"))
        bad = _check(b, text)
        if not bad: return text
        extra = "\n\nYour previous draft had problems: " + "; ".join(bad) + ". Rewrite the full transcript fixing them."
    return text  # best effort; flagged by validator in sanity step

# ---------------------------------------------------------------- template fallback
def _fill(s, b, comp=""):
    f = b["facts"]
    return s.format(co=b["company"], ind=b["industry"].replace("_", " "), comp=comp, cp=f"{f['comp_price_per_m']:.2f}", tp=f"{f['telnyx_price_per_m']:.2f}", m1=f["models"][0], m2=f["models"][1],
                    ttft=f["ttft_ms"], p95=f["edge_p95_ms"], res=f["residency"], vol=f["volume_m_tokens"], conc=f["concurrency"], ag=f["agents"],
                    rep=b["rep"]["name"].split()[0], b1=b["buyer1"]["name"].split()[0], uc=b["use_case"].replace("_", " "), reg=b["region"])

USE = {
 "llm_api_backend": "We're building an LLM-backed product for {co}, and the application layer calls a model API all day. We want to stop juggling providers.",
 "rag_pipeline": "Our team runs a retrieval pipeline over a few million documents and we need a dependable model API behind it.",
 "batch_document_processing": "We process large batches of documents overnight, classification and extraction, and token cost is the whole game for us.",
 "internal_copilot": "We've got an internal copilot for our staff, nothing customer facing yet, and we're shopping for where to host the models.",
 "low_latency_api_gateway": "We need to run small bits of logic close to our users, auth checks and request routing, before traffic hits our core services.",
 "edge_functions_routing": "We route and transform API traffic and want those functions to run at the edge instead of in one region.",
 "voice_ai_support_agent": "We want an AI voice agent that picks up our support line and handles the first-tier questions without a human.",
 "voice_ai_appointment_booking": "We want a voice agent that books and reschedules appointments so our front desk stops drowning in calls.",
 "voice_ai_outbound_qualification": "We're looking at outbound voice agents to qualify inbound leads within minutes of a form fill.",
 "voice_ai_ivr_replacement": "Our phone tree is miserable. We want a conversational agent in its place that routes properly.",
 "contact_center_modernization": "We're modernizing a contact center of about {ag} seats and the carrier side is the first thing we want to fix.",
 "sip_migration": "We have SIP trunks with a legacy carrier and we want to migrate them with no downtime.",
 "sms_notifications": "We send appointment and delivery notifications by text and we need better deliverability and clearer reporting.",
 "number_porting_migration": "We have a few hundred numbers spread over several providers and want them consolidated in one place.",
 "otp_verification": "We send one-time passcodes for login and the delivery rate to some regions is not good enough.",
 "ivr_replacement": "Our IVR is old and brittle and we want to replace it with something we can change ourselves."}

FILL = [
 ("What does your timeline look like?", "We'd like a pilot running inside about six weeks. Procurement is slow here, so anything we can do to get paperwork moving early helps."),
 ("How are you handling security review?", "Our security lead will want a SOC 2 report and a walkthrough of how credentials and call recordings are stored. I don't know the details yet; that's a separate thread."),
 ("Anything about the current setup that's been painful?", "Honestly support. When something breaks at night, we open a ticket and wait. And invoices are hard to reconcile, usage doesn't line up with what we see."),
 ("Who else is involved in the decision?", "It's me, our finance partner, and someone from engineering who'll own the integration. I'd say I'm the day-to-day contact but not the signer."),
 ("Can you tell me about expected volumes?", "Roughly {conc} concurrent calls at peak, much lower the rest of the day. We spike hard on Monday mornings, which is what usually breaks things."),
 ("How do you prefer to do a proof of concept?", "A sandbox with a handful of numbers and an API key would be ideal. We'd rather test with real traffic than a canned demo."),
 ("Are there regions you need coverage in?", "Mostly {reg}, with a small tail elsewhere. Number availability in a couple of countries is something we'd want confirmed in writing."),
 ("How do you want pricing structured?", "Predictable is the main thing. If there's a commit with overage that's fine, as long as we're not guessing at the bill each month."),
]

CRIT_LINE = {
 "price": ("Price is going to be a big factor. We'll line up your numbers against what we pay today, per minute and per unit.", "Understood. I'll put together a comparison on the same volumes so it's apples to apples."),
 "model_breadth": ("We swap models fairly often as new ones come out, so breadth of the model catalog matters to us. If I can't get what I need, it's a problem.", "Fair. I'll check the current list against {m1} and {m2} and send it over."),
 "latency": ("Latency is critical. For us it's time to first token under {ttft} milliseconds, otherwise the experience falls apart.", "We can test that against your target in the pilot. I'd rather measure than promise."),
 "compliance": ("Data residency is a hard requirement. Everything has to stay in {res}, and we'll need a data processing agreement before anything else.", "Okay. I'll bring in someone from our compliance team to walk through where processing happens."),
 "maturity": ("To be candid, I'm a little cautious about how proven you are for production AI at our scale. We can't afford to be someone's early adopter.", "That's a reasonable concern. I can share reference architectures and uptime history."),
 "single_vendor": ("We already run most things with one big cloud vendor, and there's a real preference internally to keep it all there for simplicity.", "I hear that. Where we tend to help is where a second vendor buys you something concrete, so let's find that."),
 "reliability": ("Uptime is non-negotiable. What does your SLA look like, and what happens when there's a regional issue?", "I'll send the SLA terms and the status history so you can judge for yourself."),
 "integration_effort": ("How much work is the integration? Our engineers are stretched, so I want to know what we'd be signing up for.", "For most teams it's a few days of API work. I'll get you a sample app to see what's involved."),
 "support_quality": ("Support responsiveness matters. Who do I call at two in the morning?", "You'd have a named engineer and a shared channel. Escalation paths are in the proposal."),
 "voice_quality": ("Call quality is something we get complaints about today. Jitter, one-way audio, that sort of thing.", "We can run test calls on your routes and share the MOS scores, so you can hear it before committing."),
 "cost_predictability": ("I'd like to avoid surprise bills. Our finance team hates variable spend with no ceiling.", "We can set spend limits and alerts, and there are committed-use options to cap the variance."),
}

def _inf_block(b, rng):
    fr, rb, d = b["inference_framing"], b["inference_raised_by"], b["depth"]
    comps = b["competitors_inference"]; c1 = comps[0] if comps else ""; c2 = comps[1] if len(comps) > 1 else None
    both = f" and {c2}" if c2 else ""
    T = []
    if fr == "standalone" and rb == "buyer":
        T += [("B", "Separate from anything with voice, we have a bigger need on the AI side. We call hosted language models from our own application, and that has nothing to do with phone calls. We want an inference API we can buy on its own."),
              ("R", "That's something we offer, a standalone inference API. What models are you running today, and roughly what volume?"),
              ("B", "Mostly {m1}, sometimes {m2}. Around {vol} million tokens a month right now and it's growing.")]
        if d != "passing":
            T += [("R", "And who are you using today?"),
                  ("B", f"We're on {c1}{both}. {c1} quoted us about ${{cp}} per million tokens for {{m1}}. What would it cost with you?"),
                  ("R", "For that model we'd be around ${tp} per million tokens at your volume, and we can talk about commit discounts."),
                  ("B", "It's close, but it's not just price. I want to be able to switch models without rewriting things.")]
        if d == "deep":
            T += [("B2", "From the engineering side, we'd want an OpenAI-compatible endpoint, streaming, and a clear rate limit story. We would not be running this through a voice agent. It's a plain API workload."),
                  ("R", "Understood, it's a direct API integration. No voice involved, billed on tokens.")]
    elif fr == "standalone":
        T += [("R", "One more thing before we wrap up the telephony piece. We also sell inference as its own API, separate from voice agents. Do you have any language model workloads outside this project?"),
              ("B", "Not really a priority right now." if d != "deep" else "A little. We use {c1} for a couple of internal tools, but it isn't something I'm shopping for.")]
        if d != "passing":
            T += [("R", "It could be a good fit as a standalone service. Pricing is per million tokens, about ${tp} for {m1}, and you'd call it over API without any of the voice stack."),
                  ("B", "Maybe down the road. {c1} charges about ${cp} per million for {m1} and it works fine. I'd have to see a reason to move.")]
        if d == "deep":
            T += [("R", "I can send a model list and a price sheet for the standalone API in case it becomes relevant."), ("B", "Sure, send it. Just don't expect me to get to it soon.")]
    elif fr == "bundled_with_voice" and rb == "buyer":
        T += [("B", "For the voice agent, the language model is the piece I'm worried about. Can it run on your platform so the agent isn't making a hop out to another vendor?"),
              ("R", "Yes. When you build the agent on Telnyx, the inference is co-located with the voice pipeline, so you don't make that extra call. Which models do you have in mind?"),
              ("B", "{m1} probably. We need time to first token under {ttft} milliseconds or the conversation feels slow.")]
        if d != "passing":
            T += [("B", f"We looked at {c1}{both} for the model side, but then it's another vendor and another round trip on every turn."),
                  ("R", "That latency is the argument for keeping it in the same place. And you'd only pay for the inference as part of the agent, no separate integration.")]
        if d == "deep":
            T += [("B2", "How does it handle tool calls mid-conversation? If the agent has to look up an appointment, that all has to happen inside the turn."),
                  ("R", "The agent platform manages that loop for you, the model, the tool call, and the speech, in one pipeline.")]
    elif fr == "bundled_with_voice":
        T += [("R", "When you build the agent on our platform, the language model inference runs alongside the voice pipeline, so you don't wire up a separate AI vendor."),
              ("B", "Okay, that's easier than I expected. What models can the agent use?")]
        if d != "passing":
            T += [("R", "{m1} and {m2} among others. You pick per agent."),
                  ("B", f"We'd been thinking about {c1}{both} for the model, but if it's included with the agent we'd rather not manage another contract.")]
        if d == "deep":
            T += [("B", "And what about speed? {ttft} milliseconds to first token is where it needs to be."), ("R", "We'll measure that on your agent configuration in the pilot.")]
    return [(w, _fill(t.replace("{c1}", c1), b)) for w, t in T]

def _edge_block(b, rng):
    fr, rb, d = b["edge_framing"], b["edge_raised_by"], b["depth"]
    comps = b["competitors_edge"]; c1 = comps[0] if comps else ""; c2 = comps[1] if len(comps) > 1 else None
    both = f" and {c2}" if c2 else ""
    T = []
    if fr == "standalone" and rb == "buyer":
        T += [("B", "We also have a need that has nothing to do with voice. We want to run small compute functions at the edge, near our users, for request routing and auth. It'd be its own service."),
              ("R", "That's our Edge Compute product, and you can run it independently. What are you running that on today?"),
              ("B", f"Mostly {c1}{both}. We need p95 under {{p95}} milliseconds.")]
        if d != "passing": T += [("R", "We can test against that target from your user regions."), ("B", f"{c1} is solid, to be honest. What would make us switch is price or placement, not a feature checklist.")]
        if d == "deep": T += [("B2", "We'd deploy from our CI pipeline, so a CLI and good logs matter. No dependency on any telephony product for this.")]
    elif fr == "standalone":
        T += [("R", "Also worth knowing: we have an Edge Compute product you can use on its own, separate from the voice side. Do you run any edge functions?"),
              ("B", f"We have a few on {c1}, but it's not what I came to talk about.")]
        if d != "passing": T += [("R", "No pressure. It runs your code close to users with low latency and bills by vCPU hour."), ("B", "Maybe later. Not a priority.")]
    elif fr == "bundled_with_voice" and rb == "buyer":
        T += [("B", "Could the tools our voice agent calls run on your edge compute, right next to the agent? That would cut a hop."), ("R", "Yes, you can deploy those functions on Edge Compute so they sit next to the agent runtime.")]
        if d != "passing": T += [("B", f"We were considering {c1}{both} for those, but keeping it in one place is attractive. Latency to the agent matters, ideally under {{p95}} ms.")]
    else:
        T += [("R", "If your agent needs to call your own functions, you can host them on our Edge Compute right beside the agent so the round trip stays short."), ("B", "Oh, that's handy. We'd probably use that for the lookups.")]
        if d != "passing": T += [("B", f"We'd otherwise put them on {c1}{both}, so I'd want to compare.")]
    return [(w, _fill(t, b)) for w, t in T]

def template_transcript(b):
    rng = random.Random(zlib.crc32(b["opp_id"].encode()) ^ 0x5EED)
    T = []
    T += [("R", _fill("Thanks for making time, {b1}. I'm {rep} with Telnyx. I'd like to spend the first part understanding what {co} is trying to do, and then show what's relevant. Does that work?", b)),
          ("B", _fill("Sure. We're a {ind} company, and I'm the one who's been asked to figure this out. " + USE.get(b["use_case"], "We have a communications project.") + " I have another meeting in forty minutes, though.", b)),
          ("R", "Understood. Tell me about what you're running today.")]
    vc = b["competitors_voice"]
    if vc:
        T += [("B", f"We're on {vc[0]} right now" + (f", and we've also had a look at {vc[1]}" if len(vc) > 1 else "") + ". It's okay, but support is slow and the pricing keeps creeping up."), ("R", "That's a common story. What would you change first if you could?")]
    else:
        T += [("B", "A mix of things, honestly. A legacy carrier and some scripts someone wrote years ago. Nobody wants to touch it."), ("R", "Got it. So reliability and ownership are part of this.")]
    T += [("B", "Mostly support and cost, and nobody owns it. And we're being asked to add AI to it, which is why I'm talking to you rather than just renewing.")]
    if b["vague_buyer"]: T += [("R", "What does success look like in six months?"), ("B", "Hard to say. Something better than what we have. We're still figuring out what we need, so I'm mostly here to learn.")]
    else: T += [("R", "What does success look like in six months?"), ("B", "Pilot in production on one line of business, measurable drop in handle time, and a cost per interaction we can defend to finance.")]
    if b["inference_framing"] != "not_mentioned": T += _inf_block(b, rng)
    if b["edge_framing"] != "not_mentioned": T += _edge_block(b, rng)
    crits = [c for c in b["decision_criteria"]]; rng.shuffle(crits)
    for c in crits:
        q, a = CRIT_LINE[c]; T += [("B", _fill(q, b)), ("R", _fill(a, b))]
    fill = FILL[:]; rng.shuffle(fill)
    def text(): return " ".join(t for _, t in T)
    for q, a in fill:
        if _words(text()) >= 700: break
        T += [("R", q), ("B2" if b["buyer2"] and rng.random() < .4 else "B", _fill(a, b))]
    for area_key, phrase in (("competitors_inference", "On the model side we've also talked to {c}."), ("competitors_edge", "For the edge piece we've also looked at {c}."), ("competitors_voice", "We've also had a conversation with {c} on the telephony side.")):
        for c in b[area_key]:
            if c.lower() not in text().lower(): T += [("B", phrase.format(c=c))]
    T += [("R", "Let me suggest next steps. I'll send a written summary of what we covered with pricing, and set up a technical session with one of our engineers. Does next week work?"),
          ("B", "That works. Send it over and I'll loop in my colleagues."), ("R", "Will do. Thanks again, {b1}.".replace("{b1}", b["buyer1"]["name"].split()[0])), ("B", "Thanks, talk soon.")]
    return "\n\n".join(f"{label(b, w)} {t}" for w, t in T)

# ---------------------------------------------------------------- orchestration
def write_all(out, tr_opps, cfg, mode, regenerate):
    tdir = out / "transcripts"; tdir.mkdir(parents=True, exist_ok=True)
    idx_path = tdir / ".cache_index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {}
    key = os.environ.get("ANTHROPIC_API_KEY")
    use_llm = mode == "llm" or (mode == "auto" and bool(key))
    if mode == "llm" and not key: raise SystemExit("ANTHROPIC_API_KEY not set; use --transcripts template")
    briefs = {o["opp_id"]: brief(o, cfg["name"]) for o in tr_opps}
    todo, stale = [], []
    for oid, b in briefs.items():
        h = hashlib.sha256(json.dumps(b, sort_keys=True, default=str).encode()).hexdigest()[:16]
        b["_hash"] = h
        p = tdir / f"{oid}.md"
        if p.exists() and not regenerate:
            if idx.get(oid, {}).get("hash") != h: stale.append(oid)
            continue
        todo.append(oid)
    if stale:
        raise SystemExit(f"{len(stale)} cached transcripts are stale relative to the ground truth ({stale[:3]}...). Re-run with --regenerate-transcripts.")
    # drop transcripts that no longer belong to this scenario
    for p in tdir.glob("OPP-*.md"):
        if p.stem not in briefs: p.unlink(); idx.pop(p.stem, None)
    if todo:
        client = model = None
        if use_llm:
            import anthropic
            client = anthropic.Anthropic(); model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
            try: client.messages.create(model=model, max_tokens=8, messages=[{"role": "user", "content": "ping"}])
            except anthropic.AuthenticationError:
                msg = "ANTHROPIC_API_KEY was rejected (401)."
                if mode == "llm": raise SystemExit(msg + " Fix the key or use --transcripts template.")
                print(f"   WARNING: {msg} Using the template fallback.", flush=True); use_llm = False
        def make(oid):
            b = briefs[oid]
            src = "template"
            if use_llm:
                try: body = llm_transcript(b, client, model); src = "llm:" + model
                except Exception as e: print(f"   {oid}: LLM failed ({type(e).__name__}); template fallback", flush=True); body = template_transcript(b)
            else: body = template_transcript(b)
            (tdir / f"{oid}.md").write_text(header(b) + body + "\n")
            return oid, {"hash": b["_hash"], "source": src}
        with ThreadPoolExecutor(6 if use_llm else 1) as ex:
            for oid, rec in ex.map(make, todo): idx[oid] = rec
        print(f"   wrote {len(todo)} transcripts ({'Claude' if use_llm else 'template'})", flush=True)
    idx_path.write_text(json.dumps(idx, indent=1, sort_keys=True))
