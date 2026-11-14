import copy, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = pathlib.Path(__file__).resolve().parent / "cache"
AREAS = ("inference", "edge_compute")
AREA_LABEL = {"inference": "AI Inference", "edge_compute": "Edge Compute"}
SCENARIOS = ("component", "latent_standalone")
PROMPT_VERSION = "v2"

def load_thresholds(overrides=None):
    t = yaml.safe_load((pathlib.Path(__file__).parent / "thresholds.yaml").read_text())
    if overrides:
        t = copy.deepcopy(t)
        for k, v in overrides.items():
            if isinstance(v, dict): t[k].update(v)
            else: t[k] = v
    return t

def scenario_dir(s): return DATA / s

def scenario_description(s):
    import re
    txt = (DATA / "README.md").read_text()
    m = re.search(rf"\| `{s}` \| (.*?) \|\n", txt)
    return m.group(1) if m else ""
