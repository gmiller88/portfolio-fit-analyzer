"""Loads scenario tables. Never touches the generator's answer-key folder (only validation.py may)."""
import functools, hashlib
import pandas as pd
from .config import scenario_dir, DATA, CACHE
DATA_README = DATA / "README.md"

def fingerprint(scenario):
    """Cheap version stamp of everything a scenario's results depend on (its tables, transcripts and the cached LLM outputs).
    Used in cache keys so that a data update can never be served from stale in-process caches."""
    root = scenario_dir(scenario); h = hashlib.sha1()
    files = [p for p in sorted(root.iterdir()) if p.is_file()] + sorted((root / "transcripts").glob("OPP-*.md"))
    for sub in ("extractions", "stability", "memos"): files += sorted((CACHE / sub).glob("*.json"))
    for p in files:
        s = p.stat(); h.update(f"{p.name}|{s.st_size}|{s.st_mtime_ns}\n".encode())
    return h.hexdigest()[:16]

def load(scenario):
    return _load(scenario, fingerprint(scenario))

@functools.lru_cache(maxsize=8)
def _load(scenario, _fp):
    d = scenario_dir(scenario)
    # keep_default_na=False: the region code "NA" is North America, not a missing value
    t = {n: pd.read_csv(d / f"{n}.csv", keep_default_na=False, na_values=[""]) for n in ("accounts", "usage_monthly", "opportunities", "signups")}
    t["usage_monthly"]["m"] = (t["usage_monthly"]["month"].str[:4].astype(int) * 12 + t["usage_monthly"]["month"].str[5:7].astype(int))
    for c in ("activated", "paid_90d"):
        t["signups"][c] = t["signups"][c].astype(str).str.lower().eq("true")
    t["signups"]["products_at_90d"] = t["signups"]["products_at_90d"].fillna("")
    return t

def transcripts(scenario):
    d = scenario_dir(scenario) / "transcripts"
    return {p.stem: p.read_text() for p in sorted(d.glob("OPP-*.md"))}


def scenario_files(scenario):
    """The shipped tables, sanity report and transcripts of a scenario as {relative path: bytes} (an allowlist, so the answer key can never leak in)."""
    root = scenario_dir(scenario)
    paths = [p for p in sorted(root.iterdir()) if p.is_file() and p.suffix in (".csv", ".md")] + sorted((root / "transcripts").glob("OPP-*.md"))
    return {str(p.relative_to(root)): p.read_bytes() for p in paths}
