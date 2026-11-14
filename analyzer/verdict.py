"""Quadrant verdict with explicit, editable thresholds. Pure functions."""
LABELS = {"standalone_business": "Standalone business", "retention_led": "Retention-led standalone (fix GTM before investing)",
          "latent_standalone": "Latent standalone (diagnose losses)", "component": "Component of Voice AI", "insufficient": "Insufficient evidence"}
RECOMMEND = {"standalone_business": "double_down_standalone", "component": "invest_as_voice_ai_component", "latent_standalone": "diagnose_further",
             "retention_led": "diagnose_further", "insufficient": "insufficient_evidence"}

def _check(name, label, value, thr, fmt="pct", near=0.05):
    if value is None: return {"name": name, "label": label, "value": None, "threshold": thr, "passes": None, "gap_pp": None, "sensitive": False, "text": f"{label}: no data"}
    gap = value - thr
    pc = lambda x: f"{x * 100:.1f}%"
    txt = f"{label} is {abs(gap) * 100:.1f} pts {'above' if gap >= 0 else 'below'} the threshold ({pc(value)} vs {pc(thr)})"
    return {"name": name, "label": label, "value": value, "threshold": thr, "passes": gap >= 0, "gap_pp": round(gap * 100, 2), "sensitive": abs(gap) <= near, "text": txt}

def selfserve_adjustment(ss, th):
    c = th["selfserve"]
    if ss["n_signups"] < c["min_signups"] or ss["paid_90d_rate_no_voice"] is None:
        return 0.0, "Self-serve evidence too thin to adjust (fewer than the minimum signups)."
    nv, wv = ss["paid_90d_rate_no_voice"], ss["paid_90d_rate_with_voice"] or 0.0
    if nv >= c["strong_paid_rate_no_voice"]:
        return -c["adjust_pp"], f"Self-serve signups convert to paid without voice at {nv * 100:.1f}%, so the standalone-adoption threshold is lowered by {c['adjust_pp'] * 100:.0f} pts."
    if nv < c["weak_paid_rate_no_voice"] and wv >= c["weak_voice_multiple"] * max(nv, 1e-9):
        return c["adjust_pp"], f"Self-serve signups convert mainly when paired with voice ({wv * 100:.1f}% with vs {nv * 100:.1f}% without), so the threshold is raised by {c['adjust_pp'] * 100:.0f} pts."
    return 0.0, "Self-serve evidence is neutral; no threshold adjustment."

def classify(behavior, pipe, ss, th):
    ms, near = th["min_sample"], th["near_threshold_pp"]
    b, p = th["behavior"], th["pipeline"]
    # behavior axis
    adj, adj_text = selfserve_adjustment(ss, th)
    thr_eff = b["standalone_usage_share_min"] + adj
    b_checks, b_status, b_reason = [], None, None
    if behavior["n_accounts_using"] < b["min_accounts_using"]:
        b_status, b_reason = "insufficient", f"only {behavior['n_accounts_using']} accounts use it (minimum {b['min_accounts_using']})"
    else:
        c = _check("standalone_usage_share", "Standalone usage share (revenue)", behavior["standalone_usage_share"], thr_eff, near=near)
        b_checks.append(c); b_status = "standalone" if c["passes"] else "attached"
    # pipeline axis
    p_checks, p_status, p_reason = [], None, None
    if pipe["n_mentioning"] < ms:
        p_status, p_reason = "insufficient", f"only {pipe['n_mentioning']} transcripts discuss it (minimum {ms})"
    else:
        d = _check("standalone_demand_share", "Standalone demand share", pipe["standalone_demand_share"], p["standalone_demand_share_min"], near=near)
        p_checks.append(d)
        if not d["passes"]: p_status = "weak"
        else:
            bi = _check("buyer_initiated_share", "Buyer-initiated share of standalone mentions", pipe["buyer_initiated_share_standalone"], p["buyer_initiated_share_min"], near=near)
            p_checks.append(bi)
            if not bi["passes"]: p_status = "weak"
            elif pipe["n_standalone_closed"] < ms:
                p_status, p_reason = "insufficient", f"only {pipe['n_standalone_closed']} closed standalone deals (minimum {ms}) to judge win rate"
            else:
                w = _check("standalone_win_rate", "Standalone win rate", pipe["standalone_win_rate"], p["standalone_win_rate_min"], near=near)
                p_checks.append(w); p_status = "strong" if w["passes"] else "weak"
    if "insufficient" in (b_status, p_status):
        key = "insufficient"
    else:
        key = {("standalone", "strong"): "standalone_business", ("standalone", "weak"): "retention_led", ("attached", "strong"): "latent_standalone", ("attached", "weak"): "component"}[(b_status, p_status)]
    sensitive = [c for c in b_checks + p_checks if c["sensitive"]]
    return {"key": key, "label": LABELS[key], "recommendation": RECOMMEND[key],
            "behavior": {"status": b_status, "threshold_base": b["standalone_usage_share_min"], "selfserve_adjustment": adj, "threshold_effective": round(thr_eff, 4), "selfserve_note": adj_text, "checks": b_checks, "insufficient_reason": b_reason},
            "pipeline": {"status": p_status, "checks": p_checks, "insufficient_reason": p_reason},
            "drivers": [c["text"] for c in b_checks + p_checks], "sensitive": [c["text"] for c in sensitive]}
