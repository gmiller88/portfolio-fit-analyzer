"""How stable is each verdict? Bootstrap the transcripts and the account base and count how often each verdict comes out.
Self-serve evidence is held fixed. Deterministic (fixed seed)."""
import hashlib, json, random
from collections import Counter
import pandas as pd
from . import data, extraction, metrics, verdict
from .config import AREAS, CACHE

def _key(scenario, th, flat, B, seed):
    return hashlib.sha256(json.dumps({"s": scenario, "t": th, "e": flat, "B": B, "seed": seed}, sort_keys=True, default=str).encode()).hexdigest()[:24]

def bootstrap(scenario, th, base, B=300, seed=7, write=False):
    """Cached on disk for the committed default thresholds; computed live otherwise (about 2 s per 100 draws)."""
    flat = {k: extraction.flat(v) for k, v in extraction.load_cached(scenario).items()}
    if not flat: return None
    path = CACHE / "stability" / f"{_key(scenario, th, flat, B, seed)}.json"
    if path.exists(): return json.loads(path.read_text())
    out = _compute(scenario, th, base, flat, B, seed)
    if write: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(out, indent=1))
    return out

def _compute(scenario, th, base, flat, B, seed):
    t = data.load(scenario)
    rng = random.Random(seed)
    recs = {r["opp_id"]: r for r in t["opportunities"].to_dict("records")}
    u = t["usage_monthly"]; acct_ids = list(t["accounts"]["account_id"])
    pre = {}
    for a in AREAS:
        x = u[u["product"] == a].copy(); x["direct"] = (x["invoked_via"] != "voice_ai_agent") * x["revenue_usd"]
        pre[a] = x.groupby("account_id")[["revenue_usd", "direct"]].sum()
    keys = list(flat); counts = {a: Counter() for a in AREAS}; shares = {a: [] for a in AREAS}
    for _ in range(B):
        f2, rows = {}, []
        for i in range(len(keys)):
            k = rng.choice(keys); nid = f"{k}#{i}"; f2[nid] = flat[k]
            rows.append({**recs[k], "opp_id": nid})
        o2 = pd.DataFrame(rows); acc_draw = [rng.choice(acct_ids) for _ in acct_ids]
        for a in AREAS:
            p = metrics.pipeline(f2, {}, o2, a)
            g = pre[a].reindex(acc_draw).dropna()
            if not len(g) or g["revenue_usd"].sum() <= 0: continue
            beh = dict(base[a]["metrics"]["behavioral"]); beh["standalone_usage_share"] = g["direct"].sum() / g["revenue_usd"].sum(); beh["n_accounts_using"] = len(g)
            counts[a][verdict.classify(beh, p, base[a]["metrics"]["selfserve"], th)["key"]] += 1; shares[a].append(beh["standalone_usage_share"])
    out = {}
    for a in AREAS:
        tot = sum(counts[a].values()) or 1; s = sorted(shares[a]); point = base[a]["verdict"]["key"]
        out[a] = {"draws": tot, "point_verdict": point, "share_keeping_point_verdict": round(counts[a][point] / tot, 3),
                  "distribution": {k: round(v / tot, 3) for k, v in counts[a].most_common()},
                  "usage_share_90pct_interval": [round(s[int(0.05 * len(s))], 3), round(s[min(len(s) - 1, int(0.95 * len(s)))], 3)] if s else None}
    return out
