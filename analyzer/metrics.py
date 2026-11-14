"""Deterministic metrics (no LLM). Pure functions over the scenario tables and the extractions."""
import statistics
from collections import Counter, defaultdict
import pandas as pd

ORDER = ["voice_api", "sip_trunking", "messaging", "numbers", "voice_ai_agents", "cloud_storage", "networking", "inference", "edge_compute"]
LOSS_KEYS = ["price", "model_breadth", "latency", "compliance", "maturity", "single_vendor"]

def _r(x, n=4): return None if x is None or (isinstance(x, float) and pd.isna(x)) else round(float(x), n)
def _div(a, b): return (a / b) if b else None

def _area_usage(usage, area):
    u = usage[usage["product"] == area].copy()
    u["path"] = u["invoked_via"].map(lambda v: "voice" if v == "voice_ai_agent" else "direct")
    return u

def behavioral(t, area):
    usage, accts = t["usage_monthly"], t["accounts"]
    u = _area_usage(usage, area)
    seg = accts.set_index("account_id")["segment"]
    rev = u.groupby("path")["revenue_usd"].sum(); units = u.groupby("path")["usage_units"].sum()
    gm = u.groupby("path")["gross_margin_usd"].sum()
    tot_rev, tot_units = rev.sum(), units.sum()
    u["segment"] = u["account_id"].map(seg)
    by_seg = {}
    for s, g in u.groupby("segment"):
        r = g.groupby("path")["revenue_usd"].sum(); by_seg[s] = {"standalone_usage_share": _r(_div(r.get("direct", 0), r.sum())), "revenue_usd": _r(r.sum(), 2), "n_accounts": int(g["account_id"].nunique())}
    voice_ai_users = set(usage[usage["product"] == "voice_ai_agents"]["account_id"])
    per = u.pivot_table(index="account_id", columns="path", values="revenue_usd", aggfunc="sum", fill_value=0)
    for c in ("direct", "voice"):
        if c not in per: per[c] = 0.0
    per["dshare"] = per["direct"] / (per["direct"] + per["voice"])
    per["uses_vai"] = per.index.isin(voice_ai_users)
    standalone = per[(per["dshare"] >= 0.5) & (~per["uses_vai"])]
    attached = per[(per["voice"] > 0) & ((per["dshare"] < 0.5) | per["uses_vai"])]
    mixed = per[(per["direct"] > 0) & (per["voice"] > 0)]
    last = usage["m"].max()
    ret, nrr = {}, {}
    for path in ("direct", "voice"):
        p = u[u["path"] == path]
        first = p.groupby("account_id")["m"].min()
        monthly = p.groupby(["account_id", "m"])["revenue_usd"].sum()
        elig = first[first + 12 <= last]
        retained = sum(monthly.get((a, f + 12), 0) > 0 for a, f in elig.items())
        base = sum(monthly.get((a, f + 1), 0) for a, f in elig.items()); end = sum(monthly.get((a, f + 12), 0) for a, f in elig.items())
        name = "standalone" if path == "direct" else "attached"
        ret[name] = {"rate": _r(_div(retained, len(elig))), "n": int(len(elig)), "n_cohort": int(len(first))}
        nrr[name] = {"nrr": _r(_div(end, base)), "n": int(len(elig))}
    # attach sequences
    first_month = usage.assign(label=usage.apply(lambda r: (area + (" (via Voice AI)" if r["invoked_via"] == "voice_ai_agent" else " (direct)")) if r["product"] == area else r["product"], axis=1)) \
        if False else None
    seqs, delay_by_entry, links = Counter(), defaultdict(list), Counter()
    uu = usage.copy()
    mask = uu["product"] == area
    uu["label"] = uu["product"]
    uu.loc[mask, "label"] = uu.loc[mask, "invoked_via"].map(lambda v: f"{area} (via Voice AI)" if v == "voice_ai_agent" else f"{area} (direct)")
    fm = uu.groupby(["account_id", "label"])["m"].min().reset_index()
    rank = lambda lab: ORDER.index(lab.split(" (")[0]) if lab.split(" (")[0] in ORDER else 99
    for a, g in fm.groupby("account_id"):
        if not g["label"].str.startswith(area).any(): continue
        items = sorted(zip(g["m"], g["label"].map(rank), g["label"]))
        seq = []
        for m, _, lab in items:
            seq.append((lab, m))
            if lab.startswith(area): break
        names = [s[0] for s in seq]
        if len(names) == 1: nodes = [f"0:{names[0]}"]
        elif len(names) == 2: nodes = [f"0:{names[0]}", f"2:{names[1]}"]
        else: nodes = [f"0:{names[0]}", f"1:{names[-2]}", f"2:{names[-1]}"]
        for s_, t_ in zip(nodes, nodes[1:]): links[(s_, t_)] += 1
        seqs[" > ".join(names)] += 1
        if len(seq) > 1: delay_by_entry[seq[0][0]].append(seq[-1][1] - seq[0][1])
    n_using = int(u["account_id"].nunique())
    return {"n_accounts_total": int(len(accts)), "n_accounts_using": n_using, "adoption_share": _r(n_using / len(accts)),
            "revenue_usd": _r(tot_rev, 2), "standalone_usage_share": _r(_div(rev.get("direct", 0), tot_rev)), "standalone_units_share": _r(_div(units.get("direct", 0), tot_units)),
            "by_segment": by_seg, "n_standalone_accounts": int(len(standalone)), "n_attached_accounts": int(len(attached)), "n_mixed_accounts": int(len(mixed)),
            "revenue_by_path": {"standalone": _r(rev.get("direct", 0), 2), "attached": _r(rev.get("voice", 0), 2)},
            "gross_margin_pct": {"standalone": _r(_div(gm.get("direct", 0), rev.get("direct", 0))), "attached": _r(_div(gm.get("voice", 0), rev.get("voice", 0)))},
            "retention_12m": ret, "nrr_12m": nrr,
            "attach_links": [{"source": s, "target": t_, "count": c} for (s, t_), c in links.items()],
            "top_sequences": seqs.most_common(8),
            "median_months_to_attach": {k: statistics.median(v) for k, v in delay_by_entry.items()},
            "median_months_to_attach_overall": statistics.median([x for v in delay_by_entry.values() for x in v]) if delay_by_entry else None}

def pipeline(ext_flat, ext_full, opps, area):
    fk, rk = ("inference_framing", "inference_raised_by") if area == "inference" else ("edge_framing", "edge_raised_by")
    ck = "competitors_inference" if area == "inference" else "competitors_edge"
    o = opps.set_index("opp_id")
    rows = [{"opp_id": oid, "framing": f[fk], "raised": f[rk], "outcome": o.loc[oid, "outcome"] if oid in o.index else None, "account_id": o.loc[oid, "account_id"] if oid in o.index else None,
             "reason": f["stated_reason"], "criteria": f["decision_criteria"], "comps": f[ck]} for oid, f in ext_flat.items()]
    d = pd.DataFrame(rows)
    n = len(d)
    if not n:
        keys = ("standalone_demand_share", "bundled_share", "buyer_initiated_share_standalone", "buyer_initiated_share_all_mentions", "rep_raised_share_standalone", "standalone_win_rate", "bundled_win_rate")
        return {"n_transcripts": 0, "n_mentioning": 0, "n_standalone": 0, "n_bundled": 0, "n_standalone_closed": 0, "n_bundled_closed": 0, "n_standalone_lost": 0,
                "loss_reasons_stated": {}, "loss_concerns_voiced": {}, "competitors_standalone": {}, "table": [], **{k: None for k in keys}}
    sa, bd = d[d.framing == "standalone"], d[d.framing == "bundled_with_voice"]
    sa_c, bd_c = sa[sa.outcome.isin(["won", "lost"])], bd[bd.outcome.isin(["won", "lost"])]
    lost = sa[sa.outcome == "lost"]
    mention = d[d.framing != "not_mentioned"]
    reasons = Counter(r for r in lost.reason if r != "none_stated")
    crit = Counter(c for cs in lost.criteria for c in cs if c in LOSS_KEYS)
    comps = Counter(c for cs in sa.comps for c in cs)
    return {"n_transcripts": n, "n_mentioning": int(len(mention)), "n_standalone": int(len(sa)), "n_bundled": int(len(bd)),
            "standalone_demand_share": _r(len(sa) / n), "bundled_share": _r(len(bd) / n),
            "buyer_initiated_share_standalone": _r(_div((sa.raised == "buyer").sum(), len(sa))),
            "buyer_initiated_share_all_mentions": _r(_div((mention.raised == "buyer").sum(), len(mention))),
            "rep_raised_share_standalone": _r(_div((sa.raised == "rep").sum(), len(sa))),
            "n_standalone_closed": int(len(sa_c)), "standalone_win_rate": _r(_div((sa_c.outcome == "won").sum(), len(sa_c))),
            "n_bundled_closed": int(len(bd_c)), "bundled_win_rate": _r(_div((bd_c.outcome == "won").sum(), len(bd_c))),
            "n_standalone_lost": int(len(lost)), "loss_reasons_stated": dict(reasons.most_common()), "loss_concerns_voiced": dict(crit.most_common()),
            "competitors_standalone": dict(comps.most_common()),
            "table": d.drop(columns=["criteria", "comps"]).to_dict("records")}

def selfserve(t, area, base_paid=None):
    s = t["signups"]; g = s[s.entry_product == area]
    wv = g[g.products_at_90d.str.split("|").map(lambda p: "voice_ai_agents" in p)]; nv = g[~g.index.isin(wv.index)]
    rate = lambda x: _r(_div(x.paid_90d.sum(), len(x)))
    return {"n_signups": int(len(g)), "signup_share": _r(len(g) / len(s)), "activation_rate": _r(_div(g.activated.sum(), len(g))), "paid_90d_rate": rate(g),
            "paid_90d_rate_no_voice": rate(nv), "n_no_voice": int(len(nv)), "paid_90d_rate_with_voice": rate(wv), "n_with_voice": int(len(wv)),
            "baseline_paid_90d_rate_all_signups": rate(s)}

def stated_vs_revealed(t, area, ext_flat):
    fk = "inference_framing" if area == "inference" else "edge_framing"
    usage, accts, opps = t["usage_monthly"], t["accounts"].set_index("account_id"), t["opportunities"]
    u = _area_usage(usage, area); rev = u.groupby(["account_id", "path"])["revenue_usd"].sum().unstack(fill_value=0)
    rows = []
    for _, o in opps[(opps.outcome == "won") & opps.account_id.notna()].iterrows():
        f = ext_flat.get(o.opp_id)
        if not f: continue
        r = rev.loc[o.account_id] if o.account_id in rev.index else None
        d, v = (float(r.get("direct", 0)), float(r.get("voice", 0))) if r is not None else (0.0, 0.0)
        revealed = "none" if d + v == 0 else ("mostly_direct" if d >= v else "mostly_voice_ai")
        rows.append({"opp_id": o.opp_id, "account_id": o.account_id, "company": accts.loc[o.account_id, "company_name"], "stated": f[fk],
                     "revealed": revealed, "direct_rev": round(d, 2), "voice_rev": round(v, 2)})
    df = pd.DataFrame(rows)
    sa = df[df.stated == "standalone"] if len(df) else df
    out = {"n_won_linked": int(len(df)), "n_stated_standalone": int(len(sa)),
           "gap_share": _r(_div((sa.revealed == "mostly_voice_ai").sum(), len(sa))) if len(sa) else None,
           "n_gap": int((sa.revealed == "mostly_voice_ai").sum()) if len(sa) else 0,
           "n_direct": int((sa.revealed == "mostly_direct").sum()) if len(sa) else 0, "n_none": int((sa.revealed == "none").sum()) if len(sa) else 0,
           "matrix": {s: dict(Counter(df[df.stated == s].revealed)) for s in df.stated.unique()} if len(df) else {}, "table": rows}
    return out
