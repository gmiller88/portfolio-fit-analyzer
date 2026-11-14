import pathlib
def load():
    """Load the repo .env, overriding a stale shell-exported key (same convention as digest/main.py)."""
    try: from dotenv import load_dotenv
    except ImportError: return
    for p in (pathlib.Path(__file__).resolve().parent.parent / ".env", pathlib.Path(__file__).resolve().parent.parent.parent / ".env"):
        if p.exists(): load_dotenv(p, override=True); return
