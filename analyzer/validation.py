"""The ONLY module allowed to read ground_truth/. Scores extractions against the hidden truth, per field."""
import pandas as pd
from .config import scenario_dir
from .extraction import flat, quote_grounded
from .data import transcripts

def _set(v): return {x.strip().lower() for x in (v.split("|") if isinstance(v, str) else v) if x and x.strip()}

def validate(scenario, extractions):
    truth = pd.read_csv(scenario_dir(scenario) / "ground_truth" / "transcript_truth.csv", keep_default_na=False)
    tx = transcripts(scenario); rows = []
    for _, t in truth.iterrows():
        ex = extractions.get(t["opp_id"])
        if not ex: continue
        f = flat(ex); r = {"opp_id": t["opp_id"]}
        for k in ("primary_interest", "use_case", "inference_framing", "inference_raised_by", "edge_framing", "edge_raised_by"):
            r[k] = (f[k] == t[k], f[k], t[k], ex[k]["confidence"])
        for k in ("competitors_inference", "competitors_edge", "competitors_voice", "decision_criteria"):
            a, b = _set(f[k]), _set(t[k]); r[k] = (a == b, "|".join(sorted(a)), "|".join(sorted(b)), ex[k]["confidence"])
            r[k + "_jaccard"] = len(a & b) / len(a | b) if (a | b) else 1.0
        if t["outcome"] == "lost": r["stated_reason"] = (f["stated_reason"] == t["primary_loss_reason"], f["stated_reason"], t["primary_loss_reason"], ex["stated_reason"]["confidence"])
        r["grounded"] = all(quote_grounded(ex[k]["quote"], tx[t["opp_id"]]) for k in ex)
        rows.append(r)
    fields = ["primary_interest", "use_case", "inference_framing", "inference_raised_by", "edge_framing", "edge_raised_by",
              "competitors_inference", "competitors_edge", "competitors_voice", "decision_criteria", "stated_reason"]
    summ = []
    for k in fields:
        vals = [r[k] for r in rows if k in r]
        if not vals: continue
        d = {"field": k, "n": len(vals), "accuracy": sum(v[0] for v in vals) / len(vals), "metric": "exact match" if k != "stated_reason" else "exact match (lost deals only)"}
        if k + "_jaccard" in rows[0]: d["mean_jaccard"] = sum(r[k + "_jaccard"] for r in rows) / len(rows)
        for c in ("high", "medium", "low"):
            cv = [v for v in vals if v[3] == c]; d[f"n_{c}"] = len(cv); d[f"acc_{c}"] = sum(v[0] for v in cv) / len(cv) if cv else None
        summ.append(d)
    framing = [r[k][0] for r in rows for k in ("inference_framing", "inference_raised_by", "edge_framing", "edge_raised_by")]
    return {"scenario": scenario, "n_transcripts": len(rows), "fields": summ, "framing_and_raised_by_accuracy": sum(framing) / len(framing) if framing else None,
            "quote_grounding_rate": sum(r["grounded"] for r in rows) / len(rows) if rows else None,
            "errors": [{"opp_id": r["opp_id"], "field": k, "extracted": r[k][1], "truth": r[k][2]} for r in rows for k in fields if k in r and not r[k][0]]}
