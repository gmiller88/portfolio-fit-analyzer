"""Compare realized aggregates with scenario parameters; flag deviations over 10 percentage points."""
from .config import AREAS
TOL = 0.10

def report(cfg, eff):
    rows = []
    def add(metric, param, real, n=None, level=""):
        if real is None: rows.append((metric, param, None, n, level, "n/a")); return
        dev = real - param; small = level == "transcripts" and n is not None and n < 10
        rows.append((metric, param, real, n, level, ("info (n<10)" if small else "FLAG") if abs(dev) > TOL + 1e-9 else "ok"))
    for area in AREAS:
        p = cfg[area]; o = eff["opportunity_level"][area]; t = eff["transcript_level"][area]; b = eff["behavioral"][area]; s = eff["selfserve"][area]
        add(f"{area}: standalone_demand_share", p["standalone_demand_share"], o["standalone_demand_share"], o["n"], "opps")
        add(f"{area}: standalone_demand_share", p["standalone_demand_share"], t["standalone_demand_share"], t["n"], "transcripts")
        add(f"{area}: bundled_mention_share", p["bundled_mention_share"], o["bundled_mention_share"], o["n"], "opps")
        add(f"{area}: bundled_mention_share", p["bundled_mention_share"], t["bundled_mention_share"], t["n"], "transcripts")
        add(f"{area}: buyer_initiated_share (standalone)", p["buyer_initiated_share"], o["buyer_initiated_share"], o["n_standalone"], "opps")
        add(f"{area}: buyer_initiated_share (standalone)", p["buyer_initiated_share"], t["buyer_initiated_share"], t["n_standalone"], "transcripts")
        add(f"{area}: standalone_win_rate", p["standalone_win_rate"], o["standalone_win_rate"], o["n_standalone_closed"], "opps (closed)")
        add(f"{area}: bundled_win_rate", p["bundled_win_rate"], o["bundled_win_rate"], None, "opps (closed)")
        for k, w in p["loss_reason_weights"].items():
            tot = sum(p["loss_reason_weights"].values())
            add(f"{area}: loss_reason[{k}]", w / tot, o["loss_reason_shares"].get(k, 0.0) if o["n_standalone_lost"] else None, o["n_standalone_lost"], "standalone lost opps")
        tot = sum(p["competitor_weights"].values())
        for k, w in p["competitor_weights"].items():
            add(f"{area}: competitor[{k}]", w / tot, o["competitor_shares"].get(k, 0.0), o["n_competitor_mentions"], "opps (first-named)")
        add(f"{area}: standalone_usage_share (revenue)", p["standalone_usage_share"], b["standalone_usage_share"], None, "usage")
        add(f"{area}: standalone_retention_12m", p["standalone_retention_12m"], b["standalone_retention_12m"], b["n_cohort_eligible"], "direct cohort")
        add(f"{area}: selfserve_signup_share", p["selfserve_signup_share"], s["signup_share"], None, "signups")
        add(f"{area}: selfserve_paid_90d_rate", p["selfserve_paid_90d_rate"], s["paid_90d_rate_no_voice"], s["n_no_voice"], "signups (no voice)")
        add(f"{area}: selfserve_paid_90d_rate_with_voice", p["selfserve_paid_90d_rate_with_voice"], s["paid_90d_rate_with_voice"], s["n_with_voice"], "signups (voice)")
    sv = eff["behavioral"]["stated_vs_revealed"]
    add("stated_vs_revealed_gap", cfg["stated_vs_revealed_gap"], sv["revealed_voice_only_share"], sv["stated_standalone_won_accounts"], "won standalone-framed accts")
    add("won share of transcripts", cfg["won_share_of_transcripts"], eff["transcript_level"]["won_share"], eff["counts"]["transcripts"], "transcripts")
    flags = [r for r in rows if r[5] == "FLAG"]
    L = [f"# Sanity report: `{cfg['name']}`", "", "> SYNTHETIC DATA. Realized aggregates versus scenario parameters; deviations over 10 percentage points are flagged.", "",
         f"**Result: {'CLEAN' if not flags else str(len(flags)) + ' FLAG(S)'}** ({len(rows)} checks)", ""]
    chk = []
    for area in AREAS:
        m = eff["transcript_level"][area]["n_mentioning"]
        chk.append(f"- Transcripts mentioning {area}: **{m}** ({'ok' if m >= 12 else 'BELOW 12'})")
        sc = eff["behavioral"][area]["calibration_scale"]
        chk.append(f"- {area} calibration scale applied to direct usage: {sc} ({'ok' if 0.05 < sc < 40 else 'near cap, check'})")
    ln = eff["transcript_level"]["linked_to_account"]; nt = eff["counts"]["transcripts"]
    chk.append(f"- Transcripts linked to an account with usage history: **{ln}/{nt}** ({ln / nt:.0%})")
    chk.append(f"- Transcripts mentioning neither product: {eff['transcript_level']['not_mentioned_either_share']:.0%}")
    chk.append(f"- Never-won prospects (lost or open, no account): {eff['counts']['prospects_never_won']}")
    chk.append(f"- Realized standalone direct NRR, 12m: inference {eff['behavioral']['inference']['direct_nrr_12m']}, edge {eff['behavioral']['edge_compute']['direct_nrr_12m']}")
    L += chk + ["", "| Metric | Level | Param | Realized | Dev (pp) | n | Status |", "|---|---|---|---|---|---|---|"]
    for m, p, r, n, lv, st in rows:
        L.append(f"| {m} | {lv} | {p:.2f} | {'n/a' if r is None else f'{r:.2f}'} | {'n/a' if r is None else f'{(r - p) * 100:+.1f}'} | {n if n is not None else ''} | {st} |")
    return "\n".join(L) + "\n"
