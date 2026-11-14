"""Where is the funnel weakest, and which GTM actions are likely to move it? Deterministic and transparent:
severity = relative shortfall against an explicit benchmark; action score = sum(severity x how directly the action addresses that weakness).
This is a prioritisation heuristic, not a forecast of impact."""
from .config import AREA_LABEL

pc = lambda x: f"{x * 100:.1f}%"

def weaknesses(area, m, verdict, th):
    b, p, s = m["behavioral"], m["pipeline"], m["selfserve"]
    ms = max(1, th["min_sample"]); A = AREA_LABEL[area]
    if verdict["key"] == "insufficient":
        why = verdict["behavior"]["insufficient_reason"] or verdict["pipeline"]["insufficient_reason"]
        return [{"id": "evidence", "stage": "evidence", "severity": 1.0, "tags": ["evidence"], "text": f"There is too little evidence to judge {A}: {why}."}]
    out = []
    def add(id, stage, sev, text, tags):
        if sev is not None and sev > 0.05: out.append({"id": id, "stage": stage, "severity": round(min(1.0, sev), 2), "tags": tags, "text": text})
    n_signups, idx = s["n_signups"], s["signup_volume_index"]
    if idx is not None and idx < 1:
        add("topfunnel", "top of funnel", 1 - idx, f"Top of the self-serve funnel is thin: {n_signups} signups, {idx:.1f}x the average entry product.", ["topfunnel"])
    if s["activation_rate"] is not None and s["baseline_activation_rate"] and s["activation_rate"] < s["baseline_activation_rate"]:
        add("activation", "activation", (s["baseline_activation_rate"] - s["activation_rate"]) / s["baseline_activation_rate"],
            f"Activation is {pc(s['activation_rate'])} against {pc(s['baseline_activation_rate'])} for all signups.", ["activation"])
    nv, wv, base = s["paid_90d_rate_no_voice"], s["paid_90d_rate_with_voice"], s["baseline_paid_90d_rate_all_signups"]
    if nv is not None and base and nv < base:
        add("conversion", "paid conversion", (base - nv) / base, f"Paid conversion within 90 days without voice is {pc(nv)} against {pc(base)} for all signups.", ["conversion"])
    if nv is not None and wv and wv > 1.5 * max(nv, 1e-9) and (base is None or nv < base):
        add("voice_dependence", "paid conversion", 0.9 * (1 - nv / wv), f"Signups pay mainly when paired with voice: {pc(wv)} with voice versus {pc(nv)} without.", ["voice_dependence", "conversion"])
    sh, thr = b["standalone_usage_share"], verdict["behavior"]["threshold_effective"]
    if sh is not None and sh < thr:
        add("usage_share", "usage", (thr - sh) / thr, f"Only {pc(sh)} of revenue is standalone usage against a {pc(thr)} threshold.", ["usage_share"])
    sa, att = b["retention_12m"]["standalone"], b["retention_12m"]["attached"]
    if sa["rate"] is not None and att["rate"] and sa["rate"] < att["rate"]:
        add("retention", "retention", (att["rate"] - sa["rate"]) / att["rate"] * min(1, sa["n"] / ms),
            f"12-month retention is {pc(sa['rate'])} for standalone accounts (n={sa['n']}) against {pc(att['rate'])} for Voice AI-attached.", ["retention"])
    dm, dthr = p["standalone_demand_share"], th["pipeline"]["standalone_demand_share_min"]
    if dm is not None and dm < dthr:
        add("demand", "pipeline demand", (dthr - dm) / dthr, f"Only {pc(dm)} of calls frame it as standalone against a {pc(dthr)} threshold.", ["demand"])
    bi, bthr = p["buyer_initiated_share_standalone"], th["pipeline"]["buyer_initiated_share_min"]
    if bi is not None and bi < bthr and p["n_standalone"]:
        add("buyer_led", "pipeline demand", (bthr - bi) / bthr, f"Only {pc(bi)} of standalone mentions were raised by the buyer; reps are creating most of the standalone conversation.", ["buyer_led", "demand"])
    w, bw = p["standalone_win_rate"], p["bundled_win_rate"]
    bench = bw if bw is not None else th["pipeline"]["standalone_win_rate_min"]
    if w is not None and w < bench and p["n_standalone_closed"]:
        add("win", "win rate", (bench - w) / bench * min(1, p["n_standalone_closed"] / ms), f"Standalone win rate is {pc(w)} on {p['n_standalone_closed']} closed deals against {pc(bw) if bw is not None else pc(bench)} when bundled.", ["win"])
    lost = p["n_standalone_lost"]
    if lost >= 3 and p["loss_concerns_voiced"]:
        top = list(p["loss_concerns_voiced"].items())[:2]; names = " and ".join(k.replace("_", " ") for k, _ in top)
        add("loss_concerns", "win rate", 0.5 * top[0][1] / lost, f"Lost standalone deals most often cite {names}.", [f"loss:{k}" for k, _ in top])
    out.sort(key=lambda x: -x["severity"])
    return out

# (id, title, what it is, {tag: how directly it addresses that weakness 0-1})
ACTIONS = [
    ("paid_demand", "Paid and content demand campaigns that feed self-serve signups", "Developer-targeted paid, content and community campaigns to widen the top of the self-serve funnel.", {"topfunnel": 1.0, "demand": 0.4, "usage_share": 0.3}),
    ("onboarding", "Improve self-serve onboarding and documentation", "Quickstarts, sample apps and a sandbox that reach a first successful call or request in minutes, plus lifecycle nudges after signup.", {"activation": 1.0, "conversion": 0.9, "voice_dependence": 0.5}),
    ("voice_pairing", "Package it with Voice AI", "A starter bundle and in-product prompts that add it to a voice agent, capturing the conversion that already happens when it is paired with voice.", {"voice_dependence": 0.8, "conversion": 0.4}),
    ("pricing", "Standalone pricing and packaging", "Free tier or starter credits, price matching on the most-used models, and commit discounts to lower the barrier to a first paid month.", {"conversion": 0.7, "loss:price": 1.0, "topfunnel": 0.2}),
    ("competitive", "Competitive positioning and a product-gap plan", "Battlecards and benchmarks against the named specialists, plus a prioritised gap list for product.", {"loss:model_breadth": 1.0, "loss:maturity": 0.8, "loss:latency": 0.6, "win": 0.7}),
    ("buyer_led", "Buyer-led demand generation for non-voice workloads", "Solution plays, comparison pages and developer content aimed at buyers who need it on its own.", {"demand": 1.0, "buyer_led": 1.0, "topfunnel": 0.4}),
    ("sales_enablement", "Sales enablement for standalone deals", "Non-voice discovery guides, a solutions-engineer overlay and structured proofs of concept for standalone evaluations.", {"win": 1.0, "buyer_led": 0.6, "loss:maturity": 0.4}),
    ("customer_success", "Customer success and expansion motion", "Usage alerts, health scoring and commit upsell for accounts that use it directly.", {"retention": 1.0, "usage_share": 0.3}),
    ("compliance", "Data-residency and compliance packaging", "Regional processing options, a DPA template and a trust centre so compliance stops blocking evaluations.", {"loss:compliance": 1.0}),
]
EVIDENCE_ACTIONS = [
    {"id": "more_calls", "title": "Run more discovery calls that probe non-voice workloads", "why": "More calls are needed before the pipeline axis can be judged.", "watch": "Calls discussing the product", "addresses": ["evidence"]},
    {"id": "instrument", "title": "Instrument usage so direct and Voice AI-invoked use are separable", "why": "The behavior axis needs enough accounts with clean invoking-path data.", "watch": "Accounts using the product", "addresses": ["evidence"]},
    {"id": "selfserve_test", "title": "Run a small self-serve test cohort", "why": "Signup, activation and paid conversion are the cheapest evidence to gather.", "watch": "Signups with this entry product", "addresses": ["evidence"]},
]
WATCH = {"paid_demand": "Self-serve signups for this entry product", "onboarding": "Activation rate and paid conversion without voice", "voice_pairing": "Paid conversion when paired with voice",
         "pricing": "Paid conversion without voice", "competitive": "Standalone win rate", "buyer_led": "Standalone demand share of calls", "sales_enablement": "Standalone win rate",
         "customer_success": "12-month standalone retention", "compliance": "Standalone win rate"}
LEAD_METRIC = {"topfunnel": "Self-serve signups", "activation": "Activation rate", "conversion": "Paid conversion within 90 days (no voice)", "voice_dependence": "Paid conversion without voice",
               "usage_share": "Standalone usage share", "retention": "12-month standalone retention", "demand": "Standalone demand share", "buyer_led": "Buyer-initiated share",
               "win": "Standalone win rate", "loss_concerns": "Standalone win rate"}

def actions(weak, top_n=3):
    if weak and weak[0]["id"] == "evidence": return [dict(a) for a in EVIDENCE_ACTIONS[:top_n]]
    scored = []
    for aid, title, what, addr in ACTIONS:
        hit = [(w, max([addr[t] for t in w["tags"] if t in addr] or [0])) for w in weak]
        hit = [(w, k) for w, k in hit if k > 0]
        if not hit: continue
        score = sum(w["severity"] * k for w, k in hit)
        hit.sort(key=lambda x: -x[0]["severity"] * x[1])
        scored.append({"id": aid, "title": title, "what": what, "score": round(score, 2), "addresses": [w["id"] for w, _ in hit],
                       "why": " ".join(w["text"] for w, _ in hit[:2]), "watch": WATCH.get(aid, LEAD_METRIC.get(hit[0][0]["id"], hit[0][0]["stage"]))})
    scored.sort(key=lambda a: -a["score"])
    return scored[:top_n]

def plan(area, m, verdict, th):
    w = weaknesses(area, m, verdict, th)
    top, seen = [], set()
    for x in w:                       # show the worst weakness of each distinct funnel stage first
        if x["stage"] not in seen: top.append(x); seen.add(x["stage"])
    top += [x for x in w if x not in top]
    return {"weaknesses": top[:3], "actions": actions(w), "n_weaknesses": len(w)}
