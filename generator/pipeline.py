import csv, datetime as dt, json, random, shutil
from collections import Counter, defaultdict
from .config import ROOT, load_scenario, load_products, AREAS
from .util import month_str
from . import world, usage, transcripts, sanity

DATA = ROOT / "data"

def _write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in fields})

def _share(n, d): return round(n / d, 4) if d else None

def generate(name, mode="auto", regenerate=False):
    cfg = load_scenario(name); prods = load_products()
    ys, ms = cfg["start_month"].split("-"); start_t = (int(ys), int(ms)); months = cfg["months"]
    start = dt.date(*start_t, 1)
    ey, em = divmod(start_t[0] * 12 + start_t[1] - 1 + months, 12); end = dt.date(ey, em + 1, 1) - dt.timedelta(days=1)
    rng = random.Random(cfg["seed"]); urng = random.Random(cfg["seed"] + 1)
    out = DATA / name; gt = out / "ground_truth"; gt.mkdir(parents=True, exist_ok=True)

    opps = world.build_opportunities(cfg, rng, start, end)
    tr_opps = world.select_transcripts(cfg, rng, opps)
    signups = world.build_signups(cfg, rng, start, end)
    accts = usage.build_accounts(cfg, urng, opps, signups, start, months, end)
    for a in accts: usage.plan_products(a, urng, cfg, months)
    cohorts = usage.apply_retention(accts, cfg, urng, months)
    rows, scales = usage.generate_usage(accts, cfg, urng, prods, start_t, months)

    # ---- tables
    _write_csv(out / "accounts.csv", [{"account_id": a["account_id"], "company_name": a["company_name"], "segment": a["segment"], "region": a["region"],
              "industry": a["industry"], "created_date": a["created_date"].isoformat(), "acquisition_channel": a["channel"], "entry_product": a["entry"]} for a in accts],
              ["account_id", "company_name", "segment", "region", "industry", "created_date", "acquisition_channel", "entry_product"])
    _write_csv(out / "usage_monthly.csv", rows, ["account_id", "month", "product", "usage_units", "unit", "revenue_usd", "gross_margin_usd", "invoked_via"])
    _write_csv(out / "opportunities.csv", [{**o, "created_date": o["created_date"].isoformat(), "close_date": o["close_date"].isoformat() if o["close_date"] else "",
              "account_id": o.get("account_id", "")} for o in opps],
              ["opp_id", "account_id", "prospect_name", "created_date", "close_date", "stage", "outcome", "amount_usd", "primary_product", "products_discussed", "rep_name", "segment", "region"])
    _write_csv(out / "signups.csv", [{**s, "signup_date": s["signup_date"].isoformat(), "activated": str(s["activated"]).lower(), "paid_90d": str(s["paid_90d"]).lower(),
              "converted_account_id": s.get("converted_account_id", "")} for s in signups],
              ["signup_id", "signup_date", "entry_product", "activated", "paid_90d", "products_at_90d", "converted_account_id"])
    L = lambda v: "|".join(v)
    truth = [{"opp_id": o["opp_id"], "primary_interest": o["primary_interest"], "use_case": o["use_case"], "inference_framing": o["inference_framing"],
              "inference_raised_by": o["inference_raised_by"], "edge_framing": o["edge_framing"], "edge_raised_by": o["edge_raised_by"],
              "competitors_inference": L(o["competitors_inference"]), "competitors_edge": L(o["competitors_edge"]), "competitors_voice": L(o["competitors_voice"]),
              "decision_criteria": L(o["decision_criteria"]), "outcome": o["outcome"], "primary_loss_reason": o.get("loss_reason", "") if o["outcome"] == "lost" else "n/a",
              "segment": o["segment"]} for o in tr_opps]
    _write_csv(gt / "transcript_truth.csv", truth, list(truth[0]))

    # ---- transcripts
    transcripts.write_all(out, tr_opps, cfg, mode, regenerate)

    eff = effective(cfg, opps, tr_opps, signups, accts, rows, cohorts, scales, months, start_t)
    (gt / "scenario_effective.json").write_text(json.dumps(eff, indent=2, default=str))
    (out / "sanity_report.md").write_text(sanity.report(cfg, eff))
    return eff

def effective(cfg, opps, tr, signups, accts, rows, cohorts, scales, months, start_t):
    e = {"scenario": cfg["name"], "seed": cfg["seed"], "SYNTHETIC": True,
         "counts": {"accounts": len(accts), "usage_rows": len(rows), "opportunities": len(opps), "transcripts": len(tr), "signups": len(signups),
                    "prospects_never_won": sum(o["outcome"] != "won" for o in opps)},
         "opportunity_level": {}, "transcript_level": {}, "behavioral": {}, "selfserve": {}}
    fk = {"inference": ("inference_framing", "inference_raised_by", "competitors_inference", "inf_sa", "inf_b"),
          "edge_compute": ("edge_framing", "edge_raised_by", "competitors_edge", "edge_sa", "edge_b")}
    for area, (fr, rb, cp, csa, cb) in fk.items():
        for level, pool in (("opportunity_level", opps), ("transcript_level", tr)):
            n = len(pool); sa = [o for o in pool if o[fr] == "standalone"]; b = [o for o in pool if o[fr] == "bundled_with_voice"]
            sa_c = [o for o in sa if o["outcome"] != "open"]; b_c = [o for o in b if o["outcome"] != "open"]
            lost = [o for o in sa if o["outcome"] == "lost"]
            comp = Counter(o[cp][0] for o in pool if o[cp])
            d = {"n": n, "standalone_demand_share": _share(len(sa), n), "bundled_mention_share": _share(len(b), n), "n_mentioning": len(sa) + len(b),
                 "buyer_initiated_share": _share(sum(o[rb] == "buyer" for o in sa), len(sa)), "n_standalone": len(sa),
                 "standalone_win_rate": _share(sum(o["outcome"] == "won" for o in sa_c), len(sa_c)), "n_standalone_closed": len(sa_c),
                 "bundled_win_rate": _share(sum(o["outcome"] == "won" for o in b_c), len(b_c)),
                 "loss_reason_shares": {k: _share(c, len(lost)) for k, c in Counter(o["loss_reason"] for o in lost).items()}, "n_standalone_lost": len(lost),
                 "competitor_shares": {k: _share(c, sum(comp.values())) for k, c in comp.items()}, "n_competitor_mentions": sum(comp.values())}
            e[level][area] = d
    e["transcript_level"]["won_share"] = _share(sum(o["outcome"] == "won" for o in tr), len(tr))
    e["transcript_level"]["not_mentioned_either_share"] = _share(sum(o["cls"] == "none" for o in tr), len(tr))
    e["transcript_level"]["linked_to_account"] = sum(bool(o.get("account_id")) for o in tr)
    # behavioral
    rev = defaultdict(float)
    for r in rows: rev[(r["product"], r["invoked_via"] == "voice_ai_agent")] += r["revenue_usd"]
    drev = defaultdict(float)
    for r in rows:
        if r["product"] in AREAS and r["invoked_via"] != "voice_ai_agent": drev[(r["account_id"], r["month"])] += r["revenue_usd"] if r["product"] else 0
    for area in AREAS:
        v, s = rev[(area, True)], rev[(area, False)]
        co = [c for c in cohorts[area] if c["eligible"]]
        e["behavioral"][area] = {"standalone_usage_share": _share(s, s + v), "total_revenue_usd": round(s + v, 2), "calibration_scale": scales[area],
            "standalone_retention_12m": _share(sum(c["retained"] for c in co), len(co)), "n_cohort_eligible": len(co), "n_direct_accounts": len(cohorts[area])}
    gm = defaultdict(float); rv = defaultdict(float)
    for r in rows: gm[r["product"]] += r["gross_margin_usd"]; rv[r["product"]] += r["revenue_usd"]
    e["behavioral"]["gross_margin_pct_by_product"] = {p: round(gm[p] / rv[p], 3) for p in rv}
    # direct-cohort NRR (eligible): revenue at +12 vs +1, direct rows of the area product
    per = defaultdict(float)
    for r in rows:
        if r["invoked_via"] != "voice_ai_agent" and r["product"] in AREAS: per[(r["product"], r["account_id"], r["month"])] += r["revenue_usd"]
    for area in AREAS:
        a1 = a12 = 0.0
        for c in cohorts[area]:
            if not c["eligible"]: continue
            a1 += per.get((area, c["account_id"], month_str(start_t, c["start"] + 1)), 0); a12 += per.get((area, c["account_id"], month_str(start_t, c["start"] + 12)), 0)
        e["behavioral"][area]["direct_nrr_12m"] = round(a12 / a1, 3) if a1 else None
    # stated vs revealed
    by = defaultdict(lambda: defaultdict(float))
    for r in rows: by[r["account_id"]][(r["product"], r["invoked_via"] == "voice_ai_agent")] += r["revenue_usd"]
    n = gap = 0; detail = Counter()
    for o in opps:
        if o["outcome"] != "won": continue
        for area, fr in (("inference", "inference_framing"), ("edge_compute", "edge_framing")):
            if o[fr] != "standalone": continue
            d, v = by[o["account_id"]].get((area, False), 0), by[o["account_id"]].get((area, True), 0)
            rv_ = "direct" if d > 0 else "voice_only" if v > 0 else "none"; detail[rv_] += 1; n += 1; gap += rv_ == "voice_only"
    e["behavioral"]["stated_vs_revealed"] = {"stated_standalone_won_accounts": n, "revealed_voice_only_share": _share(gap, n), "detail": dict(detail)}
    # self-serve
    for area in AREAS:
        g = [s for s in signups if s["entry_product"] == area]
        wv = [s for s in g if "voice_ai_agents" in s["products_at_90d"].split("|")]; nv = [s for s in g if s not in wv]
        e["selfserve"][area] = {"signup_share": _share(len(g), len(signups)), "paid_90d_rate_no_voice": _share(sum(s["paid_90d"] for s in nv), len(nv)),
                                "paid_90d_rate_with_voice": _share(sum(s["paid_90d"] for s in wv), len(wv)), "n_no_voice": len(nv), "n_with_voice": len(wv)}
    ent = Counter(a["entry"] for a in accts); e["counts"]["accounts_by_entry_product"] = dict(ent)
    e["counts"]["accounts_by_channel"] = dict(Counter(a["channel"] for a in accts))
    return e
