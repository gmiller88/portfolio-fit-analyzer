"""Glue: scenario -> metrics + verdicts for both areas."""
from . import data, extraction, metrics, verdict
from .config import AREAS, AREA_LABEL, load_thresholds

def analyze(scenario, thresholds=None, extractions=None):
    th = thresholds or load_thresholds()
    t = data.load(scenario)
    ext = extractions if extractions is not None else extraction.load_cached(scenario)
    flat = {k: extraction.flat(v) for k, v in ext.items()}
    out = {"scenario": scenario, "thresholds": th, "areas": {}}
    for a in AREAS:
        m = {"behavioral": metrics.behavioral(t, a), "pipeline": metrics.pipeline(flat, ext, t["opportunities"], a),
             "selfserve": metrics.selfserve(t, a), "stated_vs_revealed": metrics.stated_vs_revealed(t, a, flat)}
        v = verdict.classify(m["behavioral"], m["pipeline"], m["selfserve"], th)
        out["areas"][a] = {"label": AREA_LABEL[a], "metrics": m, "verdict": v}
    return out
