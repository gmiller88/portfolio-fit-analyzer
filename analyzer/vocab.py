"""Taxonomies handed to the extractor as its strict schema."""
PRODUCTS = ["voice_api", "sip_trunking", "messaging", "numbers", "voice_ai_agents", "inference", "edge_compute", "other"]
FRAMING = ["standalone", "bundled_with_voice", "not_mentioned"]
RAISED = ["buyer", "rep", "n/a"]
CRITERIA = {
    "price": "cost: per-minute, per-token or total price",
    "model_breadth": "range of models available / ability to switch models",
    "latency": "response speed: time to first token, round-trip or p95 latency",
    "compliance": "data residency, DPA, regulatory compliance",
    "maturity": "how proven / production-ready the vendor is",
    "single_vendor": "preference to consolidate with an incumbent cloud or AI vendor",
    "reliability": "uptime, SLAs, resilience",
    "integration_effort": "engineering effort / time to integrate",
    "support_quality": "support responsiveness and escalation",
    "voice_quality": "call audio quality, jitter, call completion",
    "cost_predictability": "predictable bills, spend caps, no surprises",
}
STATED_REASON = ["price", "model_breadth", "latency", "compliance", "maturity", "single_vendor", "none_stated"]
USE_CASES = {
    "llm_api_backend": "buyer's own application calls an LLM API (not telephony)",
    "rag_pipeline": "retrieval pipeline needing a model API",
    "batch_document_processing": "large offline document classification/extraction",
    "internal_copilot": "internal staff copilot",
    "low_latency_api_gateway": "auth/routing logic at the edge in front of services",
    "edge_functions_routing": "routing/transforming API traffic at the edge",
    "voice_ai_support_agent": "voice agent answering customer support calls",
    "voice_ai_appointment_booking": "voice agent booking/rescheduling appointments",
    "voice_ai_outbound_qualification": "outbound voice agent qualifying leads",
    "voice_ai_ivr_replacement": "conversational agent replacing a phone tree",
    "contact_center_modernization": "modernizing contact center telephony",
    "sip_migration": "migrating SIP trunks from a legacy carrier",
    "sms_notifications": "transactional SMS notifications",
    "number_porting_migration": "porting/consolidating phone numbers",
    "otp_verification": "one-time passcode delivery",
    "ivr_replacement": "replacing a legacy IVR with something configurable",
    "other": "none of the above",
}
