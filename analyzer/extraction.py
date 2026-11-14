"""Transcript -> structured fields via Claude tool use. Every field carries a supporting quote and a confidence.
All LLM outputs are cached on disk keyed by sha256(input text, model, prompt version, schema)."""
import hashlib, json, os, re
from concurrent.futures import ThreadPoolExecutor
from . import vocab
from .config import CACHE, PROMPT_VERSION
from .data import transcripts

CONF = ["high", "medium", "low"]
TOOL_NAME = "record_extraction"

def _field(value_schema, desc):
    return {"type": "object", "description": desc, "additionalProperties": False, "required": ["value", "quote", "confidence"],
            "properties": {"value": value_schema,
                           "quote": {"type": "string", "description": "Verbatim text copied from the transcript that supports the value; empty string only when value is not_mentioned / empty."},
                           "confidence": {"type": "string", "enum": CONF}}}

def _enum(vals): return {"type": "string", "enum": vals}
def _list(vals=None): return {"type": "array", "items": _enum(vals) if vals else {"type": "string"}}

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["primary_interest", "use_case", "inference_framing", "inference_raised_by", "edge_framing", "edge_raised_by",
                       "competitors_inference", "competitors_edge", "competitors_voice", "decision_criteria", "stated_reason"],
          "properties": {
              "primary_interest": _field(_enum(vocab.PRODUCTS), "The Telnyx product the buyer came to discuss (what the call is mainly about)."),
              "use_case": _field(_enum(list(vocab.USE_CASES)), "Buyer's main use case. " + "; ".join(f"{k}: {v}" for k, v in vocab.USE_CASES.items())),
              "inference_framing": _field(_enum(vocab.FRAMING), "How AI Inference (hosted LLM API) is framed, per the definitions in the instructions."),
              "inference_raised_by": _field(_enum(vocab.RAISED), "Who first brought up inference / the LLM API: buyer or rep. n/a if not mentioned."),
              "edge_framing": _field(_enum(vocab.FRAMING), "How Edge Compute (running code/functions near users) is framed."),
              "edge_raised_by": _field(_enum(vocab.RAISED), "Who first brought up Edge Compute. n/a if not mentioned."),
              "competitors_inference": _field(_list(), "Vendors named as alternatives or incumbents for the inference/LLM piece. Empty list if none."),
              "competitors_edge": _field(_list(), "Vendors named as alternatives or incumbents for edge compute. Empty list if none."),
              "competitors_voice": _field(_list(), "Vendors named for voice / telephony / voice-agent platforms (carriers, CPaaS, voice-agent startups). Empty list if none."),
              "decision_criteria": _field(_list(list(vocab.CRITERIA)), "Every criterion the buyer states they care about or are worried about. " + "; ".join(f"{k}: {v}" for k, v in vocab.CRITERIA.items())),
              "stated_reason": _field(_enum(vocab.STATED_REASON), "The single most decisive concern or blocker the buyer voices that could lead them to choose another vendor; none_stated if none is voiced."),
          }}

SYSTEM = """You extract structured fields from a B2B sales-call transcript between a Telnyx rep and a prospect. Telnyx sells communications APIs (voice, SIP, messaging, numbers), Voice AI agents, AI Inference (hosted LLM API) and Edge Compute (functions run close to users).
Call the record_extraction tool exactly once. Rules:
- Use only what the transcript says. If evidence is absent, use not_mentioned / n/a / empty list / none_stated. Never guess. Every non-empty value needs a verbatim supporting quote copied from the transcript (a short span, at most two sentences).
- Speaker labels show who is the Telnyx rep (label ends with ', Telnyx') and who is the buyer (everyone else).
- FRAMING of inference or edge:
  * standalone = discussed as a separately purchasable workload that does NOT depend on Telnyx Voice AI agents: it lives in the buyer's own application or pipeline and would be bought by itself via API. This holds even if the buyer is lukewarm or declines, and even if only the rep describes it as a standalone service the buyer could buy without the voice stack.
  * bundled_with_voice = discussed only as part of a Telnyx Voice AI agent (the model or functions needed to make the voice agent work, co-located with it).
  * not_mentioned = the product is not discussed as a Telnyx offering. A buyer merely using some LLM or edge vendor elsewhere does not count unless Telnyx's offering is discussed.
  Where a call mixes both for the same product, pick the framing of the main discussion.
- RAISED_BY = who FIRST brings up that product in the call (earliest turn that raises it), the buyer or the rep. If the rep's agenda or a question introduces it before the buyer does, it is rep. If the buyer raises it unprompted, it is buyer.
- Competitors: only vendors explicitly named in the transcript, spelled as written; assign each to the area it is discussed for (inference/LLM, edge, or voice/telephony). Do not include Telnyx.
- Decision criteria: include a criterion only when the buyer presents it as something that would influence their choice: a stated priority, requirement, worry, or a point of comparison with another vendor. Do NOT include procedural or logistical mentions: noting that a security review or questionnaire will happen, asking how pricing is structured or for a quote, discussing timeline, who is on the buying committee, or sandbox/POC logistics. In particular: compliance means a stated requirement about data residency, a DPA, or regulation (a routine "security team will review it" is not compliance); price means cost is a concern or compared against alternatives (merely asking for pricing is not); integration_effort means worry about engineering effort or time to integrate; cost_predictability means worry about unpredictable bills. Use only the allowed values.
- stated_reason: the one criterion among price, model_breadth, latency, compliance, maturity, single_vendor that the buyer treats as the biggest obstacle or deciding factor for choosing Telnyx. Other criteria (reliability, support, etc.) are not allowed here: if the strongest concern is not one of the six, pick the strongest of the six that the buyer voices, or none_stated.
"""

def _key(text, model):
    blob = json.dumps({"t": text, "m": model, "p": PROMPT_VERSION, "s": SCHEMA, "sys": SYSTEM}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]

def _path(key): return CACHE / "extractions" / f"{key}.json"
def model_name(): return os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

def cached(text, model=None):
    p = _path(_key(text, model or model_name()))
    return json.loads(p.read_text()) if p.exists() else None

def extract_one(text, client, model, retries=2):
    last = None
    for _ in range(retries + 1):
        msg = client.messages.create(model=model, max_tokens=4000, system=SYSTEM, output_config={"effort": "medium"},
            tools=[{"name": TOOL_NAME, "description": "Record the structured extraction for this transcript.", "input_schema": SCHEMA, "strict": True}],
            tool_choice={"type": "auto"}, messages=[{"role": "user", "content": f"Extract the fields from this transcript. Call {TOOL_NAME}.\n\n<transcript>\n{text}\n</transcript>"}])
        for b in msg.content:
            if b.type == "tool_use" and b.name == TOOL_NAME: return b.input
        last = msg.stop_reason
    raise RuntimeError(f"no tool call (stop_reason={last})")

def run(scenario, regenerate=False, workers=6, only=None):
    """Extract every transcript of a scenario, using the cache where possible. Returns {opp_id: extraction}."""
    tr = transcripts(scenario); model = model_name(); out, todo = {}, []
    for oid, text in tr.items():
        if only and oid not in only: continue
        c = None if regenerate else cached(text, model)
        if c: out[oid] = c["extraction"]
        else: todo.append(oid)
    if todo:
        if not os.environ.get("ANTHROPIC_API_KEY"): raise RuntimeError(f"{len(todo)} transcripts are not cached and ANTHROPIC_API_KEY is not set")
        import anthropic
        client = anthropic.Anthropic()
        def job(oid):
            ex = extract_one(tr[oid], client, model)
            p = _path(_key(tr[oid], model)); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"opp_id": oid, "scenario": scenario, "model": model, "prompt_version": PROMPT_VERSION, "extraction": ex}, indent=1))
            return oid, ex
        with ThreadPoolExecutor(workers) as pool:
            for oid, ex in pool.map(job, todo): out[oid] = ex
    return out

def load_cached(scenario):
    """Cache-only load (no API). Missing transcripts are simply absent."""
    model = model_name(); out = {}
    for oid, text in transcripts(scenario).items():
        c = cached(text, model)
        if c: out[oid] = c["extraction"]
    return out

def flat(ex):
    return {k: v["value"] for k, v in ex.items()}

_norm = lambda s: re.sub(r"[^a-z0-9$%.' ]+", " ", s.lower().replace("’", "'").replace("**", "")).split()
def quote_grounded(quote, text):
    if not quote: return True
    q, t = " ".join(_norm(quote)), " ".join(_norm(text))
    return q in t
