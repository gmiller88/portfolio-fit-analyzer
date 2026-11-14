"""Opportunities, signups and account plans, all generated from quotas on a scenario file."""
import datetime as dt, math, random
from .util import apportion, labels_by_quota, wchoice, month_str
from . import names

CLASSES = ["inf_sa", "inf_b", "edge_sa", "edge_b", "none"]
LOSS_KEYS = ["price", "model_breadth", "latency", "compliance", "maturity", "single_vendor"]
EXTRA_CRITERIA = ["reliability", "integration_effort", "support_quality", "voice_quality", "cost_predictability"]
USE_CASES = {
    "inf_sa_buyer": ["llm_api_backend", "rag_pipeline", "batch_document_processing", "internal_copilot"],
    "edge_sa_buyer": ["low_latency_api_gateway", "edge_functions_routing"],
    "bundled": ["voice_ai_support_agent", "voice_ai_appointment_booking", "voice_ai_outbound_qualification", "voice_ai_ivr_replacement"],
    "none": ["contact_center_modernization", "sip_migration", "sms_notifications", "number_porting_migration", "otp_verification", "ivr_replacement"],
}
NONE_INTEREST = {"voice_api": .3, "sip_trunking": .25, "messaging": .2, "numbers": .1, "voice_ai_agents": .15}
NONE_USECASE_BY_INTEREST = {"voice_api": ["contact_center_modernization", "ivr_replacement"], "sip_trunking": ["sip_migration", "contact_center_modernization"],
                            "messaging": ["sms_notifications", "otp_verification"], "numbers": ["number_porting_migration"], "voice_ai_agents": ["voice_ai_support_agent", "voice_ai_ivr_replacement"]}

def _largest(rng, items):  # shuffle helper
    items = list(items); rng.shuffle(items); return items

def build_opportunities(cfg, rng, start, end):
    n = cfg["n_opportunities"]
    inf, edge = cfg["inference"], cfg["edge_compute"]
    w = {"inf_sa": inf["standalone_demand_share"], "inf_b": inf["bundled_mention_share"],
         "edge_sa": edge["standalone_demand_share"], "edge_b": edge["bundled_mention_share"]}
    w["none"] = max(0.0, 1 - sum(w.values()))
    cls = labels_by_quota(rng, n, w)
    opps = [{"cls": c} for c in cls]
    by = {c: [o for o in opps if o["cls"] == c] for c in CLASSES}

    # raised_by (quota within class)
    for c, area in (("inf_sa", inf), ("edge_sa", edge), ("inf_b", None), ("edge_b", None)):
        grp = by[c]
        share = area["buyer_initiated_share"] if area else cfg["bundled_buyer_initiated_share"]
        for o, r in zip(grp, labels_by_quota(rng, len(grp), {"buyer": share, "rep": 1 - share})):
            o["raised_by"] = r
    # outcome (quota within class), open spread via error diffusion
    rates = {"inf_sa": inf["standalone_win_rate"], "inf_b": inf["bundled_win_rate"], "edge_sa": edge["standalone_win_rate"],
             "edge_b": edge["bundled_win_rate"], "none": cfg["base_win_rate"]}
    carry = 0.0
    for c in CLASSES:
        grp = by[c]
        x = cfg["open_share"] * len(grp) + carry
        n_open = int(round(x)); carry = x - n_open
        n_open = min(n_open, len(grp))
        closed = len(grp) - n_open
        wins = int(round(rates[c] * closed))
        lab = ["open"] * n_open + ["won"] * wins + ["lost"] * (closed - wins)
        rng.shuffle(lab)
        for o, l in zip(grp, lab):
            o["outcome"] = l
    # loss reasons: standalone classes use area weights; others default weights (quota inside each group)
    for key, wts in (("inf_sa", inf["loss_reason_weights"]), ("edge_sa", edge["loss_reason_weights"])):
        lost = [o for o in by[key] if o["outcome"] == "lost"]
        for o, r in zip(lost, labels_by_quota(rng, len(lost), wts)):
            o["loss_reason"] = r
    rest = [o for o in opps if o["outcome"] == "lost" and "loss_reason" not in o]
    for o, r in zip(rest, labels_by_quota(rng, len(rest), cfg["default_loss_reason_weights"])):
        o["loss_reason"] = r

    for area, key, pre in (("inference", "competitors_inference", "inf"), ("edge_compute", "competitors_edge", "edge")):
        grp = [o for o in opps if o["cls"].startswith(pre)]
        for o in opps: o[key] = []
        for o, comp in zip(grp, labels_by_quota(rng, len(grp), cfg[area]["competitor_weights"])): o[key] = [comp]
    used_co, used_people = set(), set()
    reps = [names.person(rng, used_people) for _ in range(6)]
    for i, o in enumerate(opps):
        c = o["cls"]
        o["inference_framing"] = "standalone" if c == "inf_sa" else "bundled_with_voice" if c == "inf_b" else "not_mentioned"
        o["edge_framing"] = "standalone" if c == "edge_sa" else "bundled_with_voice" if c == "edge_b" else "not_mentioned"
        o["inference_raised_by"] = o["raised_by"] if c.startswith("inf") else "n/a"
        o["edge_raised_by"] = o["raised_by"] if c.startswith("edge") else "n/a"
        if c in ("inf_sa", "edge_sa") and o["raised_by"] == "buyer":
            o["primary_interest"] = "inference" if c == "inf_sa" else "edge_compute"
            o["use_case"] = rng.choice(USE_CASES["inf_sa_buyer" if c == "inf_sa" else "edge_sa_buyer"])
        elif c in ("inf_sa", "edge_sa"):  # rep pushes it; buyer came for something else
            o["primary_interest"] = rng.choice(["voice_api", "sip_trunking", "voice_ai_agents"])
            o["use_case"] = rng.choice(NONE_USECASE_BY_INTEREST[o["primary_interest"]])
        elif c in ("inf_b", "edge_b"):
            o["primary_interest"] = "voice_ai_agents"; o["use_case"] = rng.choice(USE_CASES["bundled"])
        else:
            o["primary_interest"] = wchoice(rng, NONE_INTEREST); o["use_case"] = rng.choice(NONE_USECASE_BY_INTEREST[o["primary_interest"]])
        o["industry"] = rng.choice(names.INDUSTRIES)
        o["prospect_name"] = names.company(rng, o["industry"], used_co)
        o["segment"] = wchoice(rng, {"smb": .30, "mid_market": .42, "enterprise": .28})
        o["region"] = wchoice(rng, {"NA": .5, "EMEA": .25, "APAC": .1, "LATAM": .08, "MEA": .07})
        o["rep_name"] = rng.choice(reps)
        o["depth"] = wchoice(rng, {"deep": .35, "moderate": .40, "passing": .25})
        o["vague"] = rng.random() < 0.3
        # competitors
        for area, key in (("inference", "competitors_inference"), ("edge_compute", "competitors_edge")):
            if o[key] and rng.random() < 0.4:
                rest = {k: v for k, v in cfg[area]["competitor_weights"].items() if k != o[key][0] and v > 0}
                if rest: o[key].append(wchoice(rng, rest))
        o["competitors_voice"] = _pick_comps(rng, cfg["voice_competitors"], p_none=0.35, max_n=2)
        o["decision_criteria"] = _criteria(rng, o)
        o["facts"] = _facts(rng, o)
    _dates(opps, rng, start, end, cfg)
    for i, o in enumerate(_largest(rng, opps)):
        pass
    opps.sort(key=lambda o: o["created_date"])
    for i, o in enumerate(opps, 1):
        o["opp_id"] = f"OPP-{i:04d}"
        o["amount_usd"] = int(round(rng.lognormvariate({"smb": 9.4, "mid_market": 10.9, "enterprise": 12.3}[o["segment"]], 0.45), -2))
        disc = ["voice_api"] if o["primary_interest"] != "voice_api" and o["cls"] == "none" else []
        prod = [o["primary_interest"]] + disc
        if o["inference_framing"] != "not_mentioned": prod.append("inference")
        if o["edge_framing"] != "not_mentioned": prod.append("edge_compute")
        o["products_discussed"] = "|".join(dict.fromkeys(prod))
        o["primary_product"] = o["primary_interest"]
        o["stage"] = {"won": "closed_won", "lost": "closed_lost"}.get(o["outcome"]) or rng.choice(["discovery", "evaluation", "proposal", "negotiation"])
    return opps

def _pick_comps(rng, weights, p_none=0.0, max_n=2):
    if p_none and rng.random() < p_none: return []
    first = wchoice(rng, weights); out = [first]
    if max_n > 1 and rng.random() < 0.4:
        rest = {k: v for k, v in weights.items() if k != first}
        if rest: out.append(wchoice(rng, rest))
    return out

def _criteria(rng, o):
    c = set()
    if o["outcome"] == "lost": c.add(o["loss_reason"])
    pool = list(LOSS_KEYS) + EXTRA_CRITERIA
    if o["inference_framing"] == "not_mentioned": pool = [p for p in pool if p != "model_breadth"]
    if o["cls"] == "none": pool = [p for p in pool if p not in ("model_breadth", "latency")] 
    while len(c) < rng.choice([2, 3, 3, 4]):
        c.add(rng.choice(pool))
    return sorted(c)

def _facts(rng, o):
    return {"comp_price_per_m": round(rng.uniform(0.35, 0.95), 2), "telnyx_price_per_m": round(rng.uniform(0.55, 1.15), 2),
            "models": rng.sample(["Llama 3.3 70B", "Qwen 2.5 72B", "Mistral Large", "DeepSeek V3", "Llama 3.1 8B", "a fine-tuned Llama variant", "Mixtral 8x22B"], 2),
            "ttft_ms": rng.choice([250, 300, 400, 500, 600]), "edge_p95_ms": rng.choice([30, 50, 80, 120]),
            "residency": rng.choice(["EU", "UK", "India", "Germany", "Canada", "Australia"]), "volume_m_tokens": rng.choice([200, 500, 900, 1500, 4000]),
            "concurrency": rng.choice([40, 120, 300, 800]), "agents": rng.choice([3, 8, 15, 40])}

def _dates(opps, rng, start, end, cfg):
    span = (end - start).days
    for o in opps:
        if o["outcome"] == "won":
            created = start + dt.timedelta(days=rng.randint(0, span - 170))
        elif o["outcome"] == "lost":
            created = start + dt.timedelta(days=rng.randint(0, span - 70))
        else:
            created = end - dt.timedelta(days=rng.randint(7, 55))
        o["created_date"] = created
        o["close_date"] = None if o["outcome"] == "open" else created + dt.timedelta(days=rng.randint(20, 80))
        o["call_date"] = created + dt.timedelta(days=rng.randint(5, 18))

def select_transcripts(cfg, rng, opps):
    nt = cfg["n_transcripts"]
    n_won = min(round(cfg["won_share_of_transcripts"] * nt), sum(o["outcome"] == "won" for o in opps))
    won = [o for o in opps if o["outcome"] == "won"]; non = [o for o in opps if o["outcome"] != "won"]
    def spread(pool, k):
        pool = _largest(rng, pool); pool.sort(key=lambda o: (o["cls"], o["raised_by"] if "raised_by" in o else "", o["outcome"]))
        if k >= len(pool): return pool
        return [pool[int((i + 0.5) * len(pool) / k)] for i in range(k)]
    chosen = spread(won, n_won) + spread(non, nt - n_won)
    ids = {id(o) for o in chosen}
    for o in opps: o["has_transcript"] = id(o) in ids
    return [o for o in opps if o["has_transcript"]]

def build_signups(cfg, rng, start, end):
    n = cfg["n_signups"]; inf, edge = cfg["inference"], cfg["edge_compute"]
    rest = 1 - inf["selfserve_signup_share"] - edge["selfserve_signup_share"]
    other = {"voice_api": .30, "sip_trunking": .08, "messaging": .18, "numbers": .10, "voice_ai_agents": .14, "cloud_storage": .12, "networking": .08}
    tot = sum(other.values())
    w = {"inference": inf["selfserve_signup_share"], "edge_compute": edge["selfserve_signup_share"], **{k: rest * v / tot for k, v in other.items()}}
    entries = labels_by_quota(rng, n, w)
    sig = [{"entry_product": e} for e in entries]
    span = (end - start).days - 100
    for s in sig: s["signup_date"] = start + dt.timedelta(days=rng.randint(0, span))
    groups = {}
    for s in sig:
        e = s["entry_product"]
        if e in ("inference", "edge_compute"): groups.setdefault((e, None), []).append(s)
        else: groups.setdefault((e, "other"), []).append(s)
    for (e, kind), grp in list(groups.items()):
        if kind is None:
            area = cfg[e]
            wv = labels_by_quota(rng, len(grp), {"voice": cfg["selfserve_with_voice_share"], "novoice": 1 - cfg["selfserve_with_voice_share"]})
            for s, v in zip(grp, wv): s["with_voice"] = v == "voice"
            for flag, rate, act in ((True, area["selfserve_paid_90d_rate_with_voice"], 1.0), (False, area["selfserve_paid_90d_rate"], 0.45)):
                sub = [s for s in grp if s["with_voice"] == flag]
                _assign_paid(rng, sub, rate, act)
        else:
            for s in grp: s["with_voice"] = False
            _assign_paid(rng, grp, cfg["default_selfserve_paid_90d_rate"], 0.5)
    rng.shuffle(sig); sig.sort(key=lambda s: s["signup_date"])
    for i, s in enumerate(sig, 1):
        s["signup_id"] = f"SU-{i:05d}"
        prods = []
        if s["activated"]:
            prods = [s["entry_product"]]
            if s["with_voice"]: prods += ["voice_api", "voice_ai_agents"]
            elif s["paid_90d"]: prods += rng.sample(["cloud_storage", "networking", "messaging", "numbers"], rng.choice([0, 1, 1]))
            elif rng.random() < 0.15: prods += [rng.choice(["cloud_storage", "numbers", "messaging"])]
        s["products_at_90d"] = "|".join(dict.fromkeys(prods))
    return sig

def _assign_paid(rng, sub, rate, act_rate):
    k = len(sub); paid = int(round(rate * k)); act = max(paid, int(round(act_rate * k)))
    idx = list(range(k)); rng.shuffle(idx)
    for r, i in enumerate(idx):
        sub[i]["paid_90d"] = r < paid; sub[i]["activated"] = r < act
