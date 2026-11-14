import argparse, os, sys
from .config import list_scenarios

def _load_env():
    # A stale ANTHROPIC_API_KEY exported in the shell shadows the valid one in .env, so .env wins (as in digest/main.py).
    try:
        from dotenv import load_dotenv, find_dotenv
    except ImportError:
        return
    path = find_dotenv(usecwd=True) or find_dotenv(str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent / ".env"))
    if path: load_dotenv(path, override=True)

def main():
    _load_env()
    ap = argparse.ArgumentParser(prog="python -m generator", description="Generate SYNTHETIC Portfolio Fit Analyzer data.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scenario"); g.add_argument("--all", action="store_true")
    ap.add_argument("--transcripts", choices=["auto", "llm", "template"], default="auto",
                    help="auto = Claude if ANTHROPIC_API_KEY is set, else template fallback")
    ap.add_argument("--regenerate-transcripts", action="store_true", help="overwrite cached transcripts")
    a = ap.parse_args()
    from . import pipeline
    for s in (list_scenarios() if a.all else [a.scenario]):
        if s.startswith("_"): continue
        print(f"== {s}", flush=True)
        eff = pipeline.generate(s, a.transcripts, a.regenerate_transcripts)
        print("   counts:", eff["counts"])
    from . import readme; readme.write()

main()
