"""CLI: python -m analyzer verdict --scenario component   (JSON on stdout; agent-friendly)"""
import argparse, json, sys
from . import env; env.load()
from .config import SCENARIOS, AREAS, load_thresholds

def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m analyzer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verdict", help="verdicts + metrics as JSON"); v.add_argument("--scenario", required=True, choices=SCENARIOS); v.add_argument("--area", choices=AREAS)
    v.add_argument("--memo", action="store_true", help="include the (cached) memo"); v.add_argument("--set", action="append", default=[], metavar="a.b=0.3", help="override a threshold, e.g. pipeline.standalone_win_rate_min=0.4")
    v.add_argument("--no-metrics", action="store_true")
    e = sub.add_parser("extract", help="run transcript extraction (uses cache; calls Claude only on misses)"); e.add_argument("--scenario", required=True, choices=SCENARIOS); e.add_argument("--regenerate", action="store_true")
    va = sub.add_parser("validate", help="score extractions against ground truth"); va.add_argument("--scenario", required=True, choices=SCENARIOS)
    m = sub.add_parser("memo", help="generate memos with Claude for the default thresholds"); m.add_argument("--scenario", required=True, choices=SCENARIOS)
    a = ap.parse_args(argv)
    from . import analysis, extraction, memo, validation
    if a.cmd == "extract":
        ex = extraction.run(a.scenario, regenerate=a.regenerate); print(json.dumps({"scenario": a.scenario, "extracted": len(ex), "model": extraction.model_name()})); return
    if a.cmd == "validate":
        r = validation.validate(a.scenario, extraction.load_cached(a.scenario)); r.pop("errors", None); print(json.dumps(r, indent=1)); return
    th = load_thresholds()
    for s in getattr(a, "set", []):
        k, val = s.split("="); sec, _, name = k.partition(".")
        if name: th[sec][name] = float(val)
        else: th[sec] = float(val)
    res = analysis.analyze(a.scenario, th)
    if a.cmd == "memo":
        for ar in AREAS:
            mm = memo.get_memo(ar, res["areas"][ar], th, allow_llm=True); print(ar, mm["source"], "flagged" if mm["flagged"] else "ok", mm["unmatched_numbers"])
        return
    out = {"scenario": a.scenario, "thresholds": th, "areas": {}}
    for ar, x in res["areas"].items():
        if a.area and ar != a.area: continue
        o = {"label": x["label"], "verdict": x["verdict"]}
        if not a.no_metrics: o["metrics"] = {k: ({kk: vv for kk, vv in v_.items() if kk != "table"} if isinstance(v_, dict) else v_) for k, v_ in x["metrics"].items()}
        if a.memo: o["memo"] = {k: v_ for k, v_ in memo.get_memo(ar, x, th).items() if k != "facts"}
        out["areas"][ar] = o
    print(json.dumps(out, indent=1, default=str))

if __name__ == "__main__": main()
