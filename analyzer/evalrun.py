import sys, json
from . import env; env.load()
from . import extraction, validation
from .config import SCENARIOS
def main():
    for s in SCENARIOS:
        ex = extraction.run(s, regenerate="--regenerate" in sys.argv)
        v = validation.validate(s, ex)
        print(s, "framing/raised-by acc:", round(v["framing_and_raised_by_accuracy"], 3), "grounded:", round(v["quote_grounding_rate"], 3))
        for f in v["fields"]: print("  ", f["field"], round(f["accuracy"], 2), f.get("mean_jaccard") and round(f["mean_jaccard"], 2), f"n={f['n']}")
main()
