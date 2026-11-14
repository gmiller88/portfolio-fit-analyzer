"""Loads scenario tables. Never touches the generator's answer-key folder (only validation.py may)."""
import functools
import pandas as pd
from .config import scenario_dir

@functools.lru_cache(maxsize=8)
def load(scenario):
    d = scenario_dir(scenario)
    t = {n: pd.read_csv(d / f"{n}.csv") for n in ("accounts", "usage_monthly", "opportunities", "signups")}
    t["usage_monthly"]["m"] = (t["usage_monthly"]["month"].str[:4].astype(int) * 12 + t["usage_monthly"]["month"].str[5:7].astype(int))
    for c in ("activated", "paid_90d"):
        t["signups"][c] = t["signups"][c].astype(str).str.lower().eq("true")
    t["signups"]["products_at_90d"] = t["signups"]["products_at_90d"].fillna("")
    return t

def transcripts(scenario):
    d = scenario_dir(scenario) / "transcripts"
    return {p.stem: p.read_text() for p in sorted(d.glob("OPP-*.md"))}
