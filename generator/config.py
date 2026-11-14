import pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCEN = ROOT / "scenarios"
AREAS = ("inference", "edge_compute")

def load_products():
    return yaml.safe_load((SCEN / "_shared" / "products.yaml").read_text())

def load_scenario(name):
    cfg = yaml.safe_load((SCEN / "_shared" / "defaults.yaml").read_text())
    scn = yaml.safe_load((SCEN / f"{name}.yaml").read_text())
    cfg.update({k: v for k, v in scn.items()})
    cfg["name"] = name
    return cfg

def list_scenarios():
    return sorted(p.stem for p in SCEN.glob("*.yaml"))
