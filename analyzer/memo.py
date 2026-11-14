"""Verdict memo: Claude writes it from a metrics object only; every number is then checked against that object."""
import hashlib, json, os, re
from . import extraction, gtm
from .config import CACHE, PROMPT_VERSION, AREA_LABEL
from .verdict import LABELS

MEMO_PROMPT_VERSION = "m2"
TOOL = "record_memo"
RECS = ["double_down_standalone", "invest_as_voice_ai_component", "diagnose_further", "insufficient_evidence"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["recommendation", "headline", "evidence", "weaknesses", "actions"],
          "properties": {"recommendation": {"type": "string", "enum": RECS},
                         "headline": {"type": "string", "description": "One sentence, under 25 words."},
                         "evidence": {"type": "string", "description": "60-110 words: what the behavioral, pipeline and self-serve evidence shows and what would change the call. No next steps here."},
                         "weaknesses": {"type": "array", "items": {"type": "string", "description": "One sentence naming a funnel weakness with its numbers."}},
                         "actions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "rationale", "metric_to_watch"],
                                     "properties": {"title": {"type": "string"}, "rationale": {"type": "string", "description": "One or two sentences: which weakness it targets and why it should help."},
                                                    "metric_to_watch": {"type": "string", "description": "The metric to track, with its current value from FACTS."}}}}}}
SYSTEM = """You write short investment-planning memos for a VP of Product Marketing at Telnyx. The decision: is this product (AI Inference or Edge Compute) a viable standalone product worth investing in as its own category, or mainly a component of Voice AI?
You are given a FACTS object computed by deterministic code, including facts.gtm: the three highest-severity funnel weaknesses and the three highest-leverage GTM actions, already ranked. Rules:
- The recommendation MUST equal facts.verdict.recommendation (do not second-guess the quadrant).
- "weaknesses": exactly the weaknesses in facts.gtm.weaknesses, in the same order, each as one clear sentence. Do not add, drop or reorder them.
- "actions": exactly the actions in facts.gtm.actions, in the same order, using their titles. For each, explain which weakness it targets and why it should help, and give the metric to watch with its current value. Do not invent other actions.
- Cite ONLY numbers that appear in FACTS, written the way FACTS gives them (percent values are already in percent; counts are counts). Never compute new numbers (no sums, ratios, differences, targets or forecasts) unless that number is itself in FACTS. Do not write any other numerals: no years, no dates, no list numbers. Do not promise outcomes.
- You may mention a 12-month retention window and a 90-day paid window using the facts retention_window_months and paid_window_days.
- Flag small samples and sensitive thresholds honestly, using facts.sensitive and the sample sizes. The data is synthetic; do not present conclusions as real market facts.
- Call the tool record_memo exactly once."""

def build_facts(area, am, th):
    m, v = am["metrics"], am["verdict"]
    plan = gtm.plan(area, m, v, th)
    b, p, s, sv = m["behavioral"], m["pipeline"], m["selfserve"], m["stated_vs_revealed"]
    pc = lambda x: None if x is None else round(x * 100, 1)
    f = {"area": AREA_LABEL[area],
         "verdict": {"quadrant": v["label"], "recommendation": v["recommendation"]},
         "behavioral": {"accounts_using": b["n_accounts_using"], "adoption_pct": pc(b["adoption_share"]), "standalone_usage_share_pct": pc(b["standalone_usage_share"]),
                        "standalone_threshold_effective_pct": pc(v["behavior"]["threshold_effective"]), "standalone_accounts": b["n_standalone_accounts"], "attached_accounts": b["n_attached_accounts"],
                        "retention_12m_standalone_pct": pc(b["retention_12m"]["standalone"]["rate"]), "retention_12m_standalone_n": b["retention_12m"]["standalone"]["n"],
                        "retention_12m_attached_pct": pc(b["retention_12m"]["attached"]["rate"]), "retention_12m_attached_n": b["retention_12m"]["attached"]["n"],
                        "gross_margin_standalone_pct": pc(b["gross_margin_pct"]["standalone"]), "gross_margin_attached_pct": pc(b["gross_margin_pct"]["attached"]),
                        "median_months_to_attach": b["median_months_to_attach_overall"]},
         "pipeline": {"transcripts": p["n_transcripts"], "mentioning": p["n_mentioning"], "standalone_framed": p["n_standalone"], "standalone_demand_share_pct": pc(p["standalone_demand_share"]),
                      "buyer_initiated_share_of_standalone_pct": pc(p["buyer_initiated_share_standalone"]), "standalone_closed_deals": p["n_standalone_closed"],
                      "standalone_win_rate_pct": pc(p["standalone_win_rate"]), "bundled_win_rate_pct": pc(p["bundled_win_rate"]),
                      "top_loss_concerns": list(p["loss_concerns_voiced"])[:3], "top_competitors": list(p["competitors_standalone"])[:3]},
         "selfserve": {"signups": s["n_signups"], "paid_90d_rate_without_voice_pct": pc(s["paid_90d_rate_no_voice"]), "paid_90d_rate_with_voice_pct": pc(s["paid_90d_rate_with_voice"])},
         "stated_vs_revealed": {"won_accounts_stated_standalone": sv["n_stated_standalone"], "mostly_voice_ai_share_pct": pc(sv["gap_share"])},
         "thresholds": {"min_sample": th["min_sample"], "behavior_standalone_usage_share_min_pct": pc(th["behavior"]["standalone_usage_share_min"]),
                        "standalone_demand_share_min_pct": pc(th["pipeline"]["standalone_demand_share_min"]), "buyer_initiated_share_min_pct": pc(th["pipeline"]["buyer_initiated_share_min"]),
                        "standalone_win_rate_min_pct": pc(th["pipeline"]["standalone_win_rate_min"])},
         "checks": [c["text"] for c in v["behavior"]["checks"] + v["pipeline"]["checks"]], "sensitive": v["sensitive"], "selfserve_note": v["behavior"]["selfserve_note"],
         "insufficient_reason": v["behavior"]["insufficient_reason"] or v["pipeline"]["insufficient_reason"],
         "gtm": {"weaknesses": [w["text"] for w in plan["weaknesses"]],
                 "actions": [{"title": a["title"], "what": a.get("what", ""), "targets": a["why"], "metric_to_watch": a["watch"]} for a in plan["actions"]]},
         "retention_window_months": 12, "paid_window_days": 90}
    return f

def _nums(obj, out):
    if isinstance(obj, bool) or obj is None: return
    if isinstance(obj, (int, float)): out.append(float(obj))
    elif isinstance(obj, dict):
        for x in obj.values(): _nums(x, out)
    elif isinstance(obj, (list, tuple)):
        for x in obj: _nums(x, out)
    elif isinstance(obj, str):
        for t in re.findall(r"\d+(?:\.\d+)?", obj): out.append(float(t))

def memo_text(res):
    return " ".join([res["headline"], res["evidence"], *res["weaknesses"], *[f"{a['title']} {a['rationale']} {a['metric_to_watch']}" for a in res["actions"]]])

def check_numbers(text, facts):
    """Every numeric token in the memo must equal a number in facts (to the precision written). Returns (ok, unmatched)."""
    allowed = []; _nums(facts, allowed)
    bad = []
    for tok in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text):
        v = float(tok); dec = len(tok.split(".")[1]) if "." in tok else 0
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if not any(abs(v - a) <= tol for a in allowed): bad.append(tok)
    return (not bad), bad

def _key(facts, model):
    return hashlib.sha256(json.dumps({"f": facts, "m": model, "p": MEMO_PROMPT_VERSION, "sys": SYSTEM, "schema": SCHEMA}, sort_keys=True).encode()).hexdigest()[:24]

def template_memo(facts):
    v, b, p, s = facts["verdict"], facts["behavioral"], facts["pipeline"], facts["selfserve"]
    a = facts["area"]
    if v["recommendation"] == "insufficient_evidence":
        ev = f"There is not enough evidence to classify {a}: {facts['insufficient_reason']}."
    else:
        ev = (f"{a} is classified as {v['quadrant']}. Behavior: {b['standalone_usage_share_pct']}% of its revenue is standalone against an effective threshold of {b['standalone_threshold_effective_pct']}% "
              f"({b['accounts_using']} accounts use it). Pipeline: {p['standalone_demand_share_pct']}% of the {p['transcripts']} transcripts frame it as standalone"
              + (f", and the standalone win rate is {p['standalone_win_rate_pct']}% on {p['standalone_closed_deals']} closed deals" if p["standalone_win_rate_pct"] is not None else "")
              + f". Self-serve: {s['paid_90d_rate_without_voice_pct']}% of signups pay within 90 days without voice versus {s['paid_90d_rate_with_voice_pct']}% with voice.")
        if facts["sensitive"]: ev += " Sensitive inputs: " + "; ".join(facts["sensitive"]) + "."
    return {"recommendation": v["recommendation"], "headline": f"{a}: {v['quadrant']}.", "evidence": ev, "weaknesses": list(facts["gtm"]["weaknesses"]),
            "actions": [{"title": x["title"], "rationale": f"Targets: {x['targets']}" if x["targets"] else x.get("what", ""), "metric_to_watch": x["metric_to_watch"]} for x in facts["gtm"]["actions"]]}

def get_memo(area, am, th, allow_llm=False):
    facts = build_facts(area, am, th); model = extraction.model_name(); key = _key(facts, model)
    path = CACHE / "memos" / f"{key}.json"; src = None; res = None
    if path.exists(): res, src = json.loads(path.read_text())["memo"], "claude (cached)"
    elif allow_llm and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        c = anthropic.Anthropic()
        for _ in range(3):
            msg = c.messages.create(model=model, max_tokens=2000, system=SYSTEM, output_config={"effort": "medium"},
                tools=[{"name": TOOL, "description": "Record the memo.", "input_schema": SCHEMA, "strict": True}], tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": f"FACTS:\n{json.dumps(facts, indent=1)}\n\nWrite the memo and call {TOOL}."}])
            tu = next((b for b in msg.content if b.type == "tool_use" and b.name == TOOL), None)
            if tu is None: continue
            res = tu.input
            if check_numbers(memo_text(res), facts)[0] and res["recommendation"] == facts["verdict"]["recommendation"]: break
        if res:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"area": area, "model": model, "prompt_version": MEMO_PROMPT_VERSION, "facts": facts, "memo": res}, indent=1)); src = "claude (generated)"
    if res is None: res, src = template_memo(facts), "template (no cached Claude memo for these metrics/thresholds)"
    ok, bad = check_numbers(memo_text(res), facts)
    rec_ok = res["recommendation"] == facts["verdict"]["recommendation"]
    struct_ok = ([a["title"] for a in res["actions"]] == [a["title"] for a in facts["gtm"]["actions"]] and len(res["weaknesses"]) == len(facts["gtm"]["weaknesses"]))
    return {**res, "source": src, "numbers_ok": ok, "unmatched_numbers": bad, "recommendation_matches_verdict": rec_ok, "actions_match_plan": struct_ok,
            "flagged": not (ok and rec_ok and struct_ok), "facts": facts}
