"""Accounts, adoption sequences and monthly usage/billing."""
import datetime as dt, math
from .util import labels_by_quota, wchoice, month_str, month_start_date, date_to_idx
from . import names

SEG_HAZARD = {"self_serve": 0.030, "smb": 0.018, "mid_market": 0.009, "enterprise": 0.004}
SEG_GROWTH = {"self_serve": 0.010, "smb": 0.015, "mid_market": 0.020, "enterprise": 0.020}
VIA = {"voice_api": "direct_api", "sip_trunking": "other", "messaging": "webhook", "numbers": "other",
       "voice_ai_agents": "direct_api", "cloud_storage": "direct_api", "networking": "other"}
ORGANIC_ENTRY = {"voice_api": .35, "sip_trunking": .25, "messaging": .20, "numbers": .08, "cloud_storage": .07, "networking": .05}
AREA_PRODUCTS = ("inference", "edge_compute")

def build_accounts(cfg, rng, opps, signups, start, months, end):
    accts, used_co = [], set(n["prospect_name"] for n in opps)
    # --- won opportunities -> sales-led accounts
    won = [o for o in opps if o["outcome"] == "won"]
    pairs = [(o, area) for o in won for area, fkey in (("inference", "inference_framing"), ("edge_compute", "edge_framing")) if o[fkey] == "standalone"]
    g = cfg["stated_vs_revealed_gap"]
    for (o, area), lab in zip(pairs, labels_by_quota(rng, len(pairs), {"gap": g, "direct": 1 - g})):
        o["mode_" + area] = "voice" if lab == "gap" else "direct"
    for o in won:
        for area, fkey in (("inference", "inference_framing"), ("edge_compute", "edge_framing")):
            if o[fkey] == "bundled_with_voice": o["mode_" + area] = "voice"
    for o in won:
        a = {"company_name": o["prospect_name"], "segment": o["segment"], "region": o["region"], "industry": o["industry"],
             "created_date": o["close_date"], "channel": "sales_led", "opp": o,
             "inf_mode": o.get("mode_inference"), "edge_mode": o.get("mode_edge_compute"),
             "force_voice_ai": o["cls"] in ("inf_b", "edge_b") or o.get("mode_inference") == "voice" or o.get("mode_edge_compute") == "voice"
                                or o["primary_interest"] == "voice_ai_agents"}
        o["_acct"] = a; accts.append(a)
    # --- paid self-serve signups -> accounts
    for s in signups:
        if not s["paid_90d"]: continue
        e = s["entry_product"]
        a = {"signup": s, "segment": wchoice(rng, {"self_serve": .8, "smb": .2}), "region": wchoice(rng, {"NA": .45, "EMEA": .25, "APAC": .15, "LATAM": .1, "MEA": .05}),
             "industry": rng.choice(names.INDUSTRIES), "created_date": s["signup_date"] + dt.timedelta(days=rng.randint(10, 85)),
             "channel": "self_serve", "entry": e, "inf_mode": None, "edge_mode": None, "force_voice_ai": s["with_voice"]}
        if e in AREA_PRODUCTS:
            key = "inf_mode" if e == "inference" else "edge_mode"
            a[key] = "voice" if s["with_voice"] else "direct"
        s["_acct"] = a; accts.append(a)
    # --- organic sales-led remainder
    n_org = max(0, cfg["n_accounts"] - len(accts))
    org = []
    seg = labels_by_quota(rng, n_org, {"smb": .45, "mid_market": .35, "enterprise": .20})
    mode_inf = labels_by_quota(rng, n_org, {"direct": cfg["organic_standalone_share"]["inference"], "none": 1 - cfg["organic_standalone_share"]["inference"]})
    mode_edge = labels_by_quota(rng, n_org, {"direct": cfg["organic_standalone_share"]["edge_compute"], "none": 1 - cfg["organic_standalone_share"]["edge_compute"]})
    for i in range(n_org):
        ind = rng.choice(names.INDUSTRIES)
        if mode_inf[i] == "direct" and mode_edge[i] == "direct": mode_edge[i] = "none"
        early = rng.random() < 0.7
        created = start + dt.timedelta(days=rng.randint(0, 170) if early else rng.randint(0, (end - start).days - 60))
        a = {"company_name": names.company(rng, ind, used_co), "segment": seg[i], "region": wchoice(rng, {"NA": .5, "EMEA": .25, "APAC": .1, "LATAM": .08, "MEA": .07}),
             "industry": ind, "created_date": created, "channel": "sales_led", "inf_mode": "direct" if mode_inf[i] == "direct" else None,
             "edge_mode": "direct" if mode_edge[i] == "direct" else None, "force_voice_ai": False}
        a["entry"] = "inference" if a["inf_mode"] == "direct" else "edge_compute" if a["edge_mode"] == "direct" else wchoice(rng, ORGANIC_ENTRY)
        accts.append(a)
    for a in accts:
        a["c"] = max(0, min(months - 1, date_to_idx((start.year, start.month), a["created_date"])))
    accts.sort(key=lambda a: a["created_date"])
    for i, a in enumerate(accts, 1):
        a["account_id"] = f"A{i:04d}"
        if "signup" in a: a["signup"]["converted_account_id"] = a["account_id"]
        if "opp" in a: a["opp"]["account_id"] = a["account_id"]
        if "company_name" not in a: a["company_name"] = names.company(rng, a["industry"], used_co)
    return accts

def plan_products(a, rng, cfg, months):
    c = a["c"]; P = {}
    def add(p, s, kind="base"):
        if s <= months - 1 and p not in P: P[p] = {"start": max(c, s), "kind": kind, "end": None}
    opp = a.get("opp")
    entry = a.get("entry")
    if opp:
        pi = opp["primary_interest"]
        entry = pi if pi in ORGANIC_ENTRY or pi == "voice_ai_agents" else "voice_api"
        if a["inf_mode"] == "direct" and opp["inference_raised_by"] == "buyer": entry = "inference"
        if a["edge_mode"] == "direct" and opp["edge_raised_by"] == "buyer": entry = "edge_compute"
    a["entry"] = entry
    # base products
    if entry in ("inference", "edge_compute"):
        pass
    elif entry == "voice_ai_agents":
        add("voice_api", c); add("voice_ai_agents", c)
    else:
        add(entry, c)
        if entry in ("voice_api", "sip_trunking", "messaging") and rng.random() < 0.55: add("numbers", c + rng.randint(0, 1))
        if entry == "numbers" and rng.random() < 0.5: add("voice_api", c + rng.randint(1, 3))
        if entry == "sip_trunking" and rng.random() < 0.3: add("voice_api", c + rng.randint(2, 6))
        if entry in ("cloud_storage", "networking") and rng.random() < 0.25: add("voice_api", c + rng.randint(2, 8))
    voice_base = [p for p in ("voice_api", "sip_trunking") if p in P]
    vai = P.get("voice_ai_agents", {}).get("start")
    if vai is None and (a["force_voice_ai"] or (voice_base and rng.random() < cfg["voice_ai_attach_rate"])):
        if a["force_voice_ai"]:
            if not voice_base: add("voice_api", c); 
            vai = c + rng.randint(0, 2)
        else:
            vai = max(c, P[voice_base[0]]["start"]) + rng.randint(2, 7)
        if vai <= months - 1: add("voice_ai_agents", vai)
        else: vai = None
    # pulled / direct inference + edge
    for prod, mode, pull_rate, mixed in (("inference", a["inf_mode"], cfg["inference_pull_rate"], cfg["mixed_direct_rate"]["inference"]),
                                          ("edge_compute", a["edge_mode"], cfg["edge_pull_rate"], cfg["mixed_direct_rate"]["edge_compute"])):
        if mode == "direct":
            s = c if a["channel"] == "self_serve" or a["entry"] == prod else c + rng.randint(0, 2)
            add(prod + "|direct", s, "direct")
        elif vai is not None and (mode == "voice" or (mode is None and rng.random() < pull_rate)):
            add(prod + "|voice", vai + rng.choice([0, 0, 0, 1, 2]) if a["channel"] != "self_serve" or a["entry"] not in AREA_PRODUCTS else vai, "voice")
        if vai is not None and mode is None and rng.random() < mixed:
            add(prod + "|direct", vai + rng.randint(1, 5), "direct")
    if rng.random() < (0.45 if vai is not None else 0.22): add("cloud_storage", c + rng.randint(1, 8))
    if rng.random() < 0.15: add("networking", c + rng.randint(1, 10))
    if not P: add("voice_api", c)
    a["P"] = P
    a["churn"] = None
    for m in range(c + 1, months):
        if rng.random() < SEG_HAZARD[a["segment"]]:
            a["churn"] = m; break

def apply_retention(accts, cfg, rng, months):
    """Quota-assign 12-month retention for direct-usage cohorts; returns cohort records."""
    out = {}
    for prod in AREA_PRODUCTS:
        key = prod + "|direct"
        coh = [(a, a["P"][key]) for a in accts if key in a["P"]]
        elig = [(a, p) for a, p in coh if p["start"] + 12 <= months - 1]
        inel = [(a, p) for a, p in coh if p["start"] + 12 > months - 1]
        target = cfg[prod]["standalone_retention_12m"]
        lab = labels_by_quota(rng, len(elig), {"ret": target, "churn": 1 - target})
        recs = []
        for (a, p), l in zip(elig, lab): p["retained"] = l == "ret"; recs.append((a, p, True))
        for a, p in inel: p["retained"] = rng.random() < target; recs.append((a, p, False))
        for a, p, e in recs:
            if p["retained"]:
                p["g"] = rng.gauss(cfg["direct_growth_retained_monthly"], 0.015)
                a["churn"] = None
            else:
                p["end"] = min(months - 1, p["start"] + rng.randint(3, 11)); p["g"] = rng.gauss(-0.03, 0.015)
        out[prod] = [{"account_id": a["account_id"], "start": p["start"], "eligible": e, "retained": p["retained"]} for a, p, e in recs]
    return out

def generate_usage(accts, cfg, rng, prods, start, months):
    rows = []
    pull = prods["voice_pull_units_per_agent_minute"]
    for a in accts:
        seg = a["segment"]; scale = prods["segment_scale"][seg]
        fac = rng.lognormvariate(0, 0.45)
        via_edge = rng.choice(["direct_api", "direct_api", "webhook"])
        last = (a["churn"] - 1) if a["churn"] else months - 1
        series = {}
        order = sorted(a["P"], key=lambda k: (k.endswith("|voice"), k))
        va_units = {}
        for key in order:
            p = a["P"][key]; prod, _, mode = key.partition("|")
            info = prods["products"][prod]
            s = p["start"]; e = min(last, p["end"] if p["end"] is not None else months - 1)
            if s > e: continue
            g = p.get("g", rng.gauss(SEG_GROWTH[seg], 0.012) if rng.random() > 0.15 else rng.gauss(-0.025, 0.01))
            base = info["base_monthly_units"] * scale * fac * rng.lognormvariate(0, 0.35)
            pf = rng.uniform(0.8, 1.25)
            for t in range(s, e + 1):
                k = t - s
                ramp = (0.35, 0.7)[k] if k < 2 else 1.0
                noise = rng.lognormvariate(0, 0.10)
                if mode == "voice":
                    vu = va_units.get(t)
                    if not vu: continue
                    u = vu * pull[prod] * pf * noise
                    via = "voice_ai_agent"
                else:
                    u = base * ((1 + g) ** k) * ramp * noise
                    via = (via_edge if prod == "edge_compute" else "direct_api") if mode == "direct" else VIA[prod]
                    if prod == "voice_ai_agents": va_units[t] = u
                if u <= 0: continue
                rows.append({"account_id": a["account_id"], "month": month_str(start, t) , "product": prod, "usage_units": u, "unit": info["unit"],
                             "invoked_via": via, "_gm": info["gross_margin"], "_price": info["unit_price"]})
    # calibrate direct share of revenue for inference / edge to the scenario target
    scales = {}
    for prod in AREA_PRODUCTS:
        V = sum(r["usage_units"] * r["_price"] for r in rows if r["product"] == prod and r["invoked_via"] == "voice_ai_agent")
        D = sum(r["usage_units"] * r["_price"] for r in rows if r["product"] == prod and r["invoked_via"] != "voice_ai_agent")
        t = cfg[prod]["standalone_usage_share"]
        s = 1.0
        if V > 0 and D > 0: s = max(0.02, min(80.0, t * V / ((1 - t) * D)))
        scales[prod] = round(s, 4)
        for r in rows:
            if r["product"] == prod and r["invoked_via"] != "voice_ai_agent": r["usage_units"] *= s
    for r in rows:
        rev = r["usage_units"] * r["_price"]
        r["usage_units"] = round(r["usage_units"], 3); r["revenue_usd"] = round(rev, 2)
        r["gross_margin_usd"] = round(rev * r["_gm"] * rng.uniform(0.97, 1.03), 2)
        del r["_gm"], r["_price"]
    rows.sort(key=lambda r: (r["account_id"], r["month"], r["product"], r["invoked_via"]))
    return rows, scales
