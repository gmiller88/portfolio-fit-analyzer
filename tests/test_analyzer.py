import copy, pathlib, re
import pandas as pd
import pytest
from analyzer import metrics, verdict, memo, analysis
from analyzer.config import load_thresholds, ROOT

# ---------- tiny hand-built world ----------
def _tables():
    accts = pd.DataFrame({"account_id": ["A1", "A2", "A3", "A4"], "segment": ["smb", "smb", "enterprise", "smb"], "company_name": list("WXYZ")})
    rows = []
    def add(a, m, p, via, rev, units=None):
        rows.append({"account_id": a, "month": f"2025-{m:02d}", "m": 2025 * 12 + m, "product": p, "invoked_via": via, "revenue_usd": rev, "usage_units": units or rev, "gross_margin_usd": rev * 0.3})
    # A1: direct inference only, months 1..14 (retained at +12)
    for m in range(1, 15): add("A1", m, "inference", "direct_api", 100)
    # A2: direct inference months 1..4 then churn
    for m in range(1, 5): add("A2", m, "inference", "direct_api", 50)
    # A3: voice_api -> voice_ai_agents -> inference via voice
    for m in range(1, 15): add("A3", m, "voice_api", "direct_api", 10)
    for m in range(3, 15): add("A3", m, "voice_ai_agents", "direct_api", 60); add("A3", m, "inference", "voice_ai_agent", 300)
    # A4 exists but no inference
    add("A4", 1, "messaging", "webhook", 5)
    usage = pd.DataFrame(rows)
    opps = pd.DataFrame({"opp_id": [f"O{i}" for i in range(1, 7)], "outcome": ["won", "lost", "won", "lost", "open", "won"], "account_id": ["A1", None, "A3", None, None, "A2"]})
    sig = pd.DataFrame({"entry_product": ["inference"] * 4 + ["voice_api"], "activated": [True, True, True, False, True], "paid_90d": [True, False, True, False, False],
                        "products_at_90d": ["inference|voice_ai_agents", "inference", "inference", "", "voice_api"]})
    return {"accounts": accts, "usage_monthly": usage, "opportunities": opps, "signups": sig}

def test_standalone_usage_share_overall_and_segment():
    b = metrics.behavioral(_tables(), "inference")
    direct, voice = 14 * 100 + 4 * 50, 12 * 300
    assert b["standalone_usage_share"] == pytest.approx(direct / (direct + voice), abs=1e-3)
    assert b["by_segment"]["enterprise"]["standalone_usage_share"] == 0.0
    assert b["by_segment"]["smb"]["standalone_usage_share"] == 1.0
    assert b["adoption_share"] == 0.75 and b["n_accounts_using"] == 3

def test_account_classes_retention_and_margin():
    b = metrics.behavioral(_tables(), "inference")
    assert b["n_standalone_accounts"] == 2 and b["n_attached_accounts"] == 1
    assert b["retention_12m"]["standalone"] == {"rate": 0.5, "n": 2, "n_cohort": 2}   # A1 retained, A2 churned
    assert b["retention_12m"]["attached"]["n"] == 0                                    # voice cohort starts month 3, +12 is unobservable
    assert b["gross_margin_pct"]["standalone"] == pytest.approx(0.3)

def test_attach_sequence_and_median_delay():
    b = metrics.behavioral(_tables(), "inference")
    links = {(l["source"], l["target"]): l["count"] for l in b["attach_links"]}
    assert links[("0:voice_api", "1:voice_ai_agents")] == 1 and links[("1:voice_ai_agents", "2:inference (via Voice AI)")] == 1
    assert b["median_months_to_attach"]["voice_api"] == 2           # voice_api m1 -> inference m3

def test_pipeline_rates_ignore_open_deals():
    flat = {f"O{i}": {"inference_framing": fr, "inference_raised_by": rb, "stated_reason": "price", "decision_criteria": ["price"], "competitors_inference": ["X"]}
            for i, (fr, rb) in enumerate([("standalone", "buyer"), ("standalone", "rep"), ("bundled_with_voice", "buyer"), ("standalone", "buyer"), ("standalone", "buyer"), ("not_mentioned", "n/a")], 1)}
    p = metrics.pipeline(flat, {}, _tables()["opportunities"], "inference")
    assert p["n_standalone"] == 4 and p["standalone_demand_share"] == pytest.approx(4 / 6, abs=1e-3)
    assert p["n_standalone_closed"] == 3                         # O5 is open
    assert p["standalone_win_rate"] == pytest.approx(1 / 3, abs=1e-3)   # O1 won, O2 lost, O4 lost
    assert p["buyer_initiated_share_standalone"] == 0.75
    assert p["loss_reasons_stated"] == {"price": 2} and p["competitors_standalone"] == {"X": 4}

def test_stated_vs_revealed():
    flat = {"O1": {"inference_framing": "standalone"}, "O3": {"inference_framing": "standalone"}, "O6": {"inference_framing": "bundled_with_voice"}}
    s = metrics.stated_vs_revealed(_tables(), "inference", flat)
    assert s["n_stated_standalone"] == 2 and s["n_gap"] == 1 and s["gap_share"] == 0.5   # O1->A1 direct, O3->A3 voice AI

def test_selfserve_voice_split():
    s = metrics.selfserve(_tables(), "inference")
    assert s["n_with_voice"] == 1 and s["paid_90d_rate_with_voice"] == 1.0
    assert s["n_no_voice"] == 3 and s["paid_90d_rate_no_voice"] == pytest.approx(1 / 3, abs=1e-3)

# ---------- verdict logic ----------
def _m(usage=0.1, n_acc=50, mention=20, demand=0.1, buyer=0.8, closed=10, win=0.5, nv=0.06, wv=0.07, nsig=100):
    return ({"n_accounts_using": n_acc, "standalone_usage_share": usage},
            {"n_mentioning": mention, "standalone_demand_share": demand, "buyer_initiated_share_standalone": buyer, "n_standalone_closed": closed, "standalone_win_rate": win},
            {"n_signups": nsig, "paid_90d_rate_no_voice": nv, "paid_90d_rate_with_voice": wv})

def cls(th=None, **kw): return verdict.classify(*_m(**kw), th or load_thresholds())

def test_four_quadrants():
    assert cls(usage=0.1, demand=0.1)["key"] == "component"
    assert cls(usage=0.1, demand=0.3)["key"] == "latent_standalone"
    assert cls(usage=0.6, demand=0.1)["key"] == "retention_led"
    assert cls(usage=0.6, demand=0.3)["key"] == "standalone_business"

def test_threshold_edges_are_inclusive():
    th = load_thresholds()
    assert cls(th, usage=0.30, demand=0.15, win=0.25, nv=0.06)["key"] == "standalone_business"      # exactly at every threshold passes
    assert cls(th, usage=0.2999, demand=0.15, win=0.25, nv=0.06)["key"] == "latent_standalone"
    assert cls(th, usage=0.30, demand=0.15, win=0.2499, nv=0.06)["key"] == "retention_led"

def test_insufficient_evidence_paths():
    assert cls(mention=7)["key"] == "insufficient" and cls(mention=8)["key"] != "insufficient"      # min_sample = 8
    assert cls(n_acc=7)["key"] == "insufficient"
    r = cls(demand=0.3, closed=7)                                                                   # demand real but win rate unjudgeable
    assert r["key"] == "insufficient" and "closed standalone deals" in r["pipeline"]["insufficient_reason"]
    assert cls(demand=0.3, closed=7, th={**load_thresholds(), "min_sample": 5})["key"] != "insufficient"

def test_buyer_initiated_gate_makes_pipeline_weak():
    assert cls(usage=0.1, demand=0.3, buyer=0.2)["key"] == "component"                              # demand is rep-driven

def test_selfserve_adjusts_behavior_threshold():
    base = load_thresholds()["behavior"]["standalone_usage_share_min"]
    strong = cls(nv=0.12); weak = cls(nv=0.02, wv=0.2); neutral = cls(nv=0.06, wv=0.07)
    assert strong["behavior"]["threshold_effective"] == pytest.approx(base - 0.05)
    assert weak["behavior"]["threshold_effective"] == pytest.approx(base + 0.05)
    assert neutral["behavior"]["threshold_effective"] == pytest.approx(base)
    assert cls(usage=0.27, nv=0.12)["behavior"]["status"] == "standalone" and cls(usage=0.27, nv=0.06)["behavior"]["status"] == "attached"
    assert cls(nv=0.12, nsig=5)["behavior"]["selfserve_adjustment"] == 0                           # too few signups: no adjustment

def test_driver_text_and_sensitivity():
    r = cls(usage=0.1, demand=0.3, win=0.21)
    t = [c for c in r["pipeline"]["checks"] if c["name"] == "standalone_win_rate"][0]
    assert "4.0 pts below the threshold" in t["text"] and t["sensitive"] and not t["passes"]

# ---------- memo number guard ----------
FACTS = {"a_pct": 20.0, "n": 11, "x": {"y": 5.5}, "s": "12-month window", "retention_window_months": 12}
def test_number_check_accepts_rounding_and_rejects_fabrication():
    assert memo.check_numbers("Share is 20.0% and 20% overall; 11 deals; 5.5 pts; 12-month", FACTS)[0]
    ok, bad = memo.check_numbers("Share is 21.0% across 11 deals", FACTS); assert not ok and bad == ["21.0%"]
    assert not memo.check_numbers("There were 19 deals", FACTS)[0]

# ---------- repo rules ----------
def test_only_validation_reads_ground_truth():
    offenders = [p.name for p in list((ROOT / "analyzer").glob("*.py")) + [ROOT / "app.py"] if "ground_truth" in p.read_text() and p.name != "validation.py"]
    assert offenders == []

# ---------- integration on the committed scenarios ----------
@pytest.fixture(scope="module")
def runs(): return {s: analysis.analyze(s) for s in ("component", "latent_standalone")}

def test_intended_scenario_verdicts(runs):
    assert runs["component"]["areas"]["inference"]["verdict"]["key"] == "component"
    assert runs["latent_standalone"]["areas"]["inference"]["verdict"]["key"] == "latent_standalone"
    assert runs["component"]["areas"]["edge_compute"]["verdict"]["key"] == "component"
    assert runs["latent_standalone"]["areas"]["edge_compute"]["verdict"]["key"] == "component"

def test_one_slider_flips_a_verdict():
    th = load_thresholds({"behavior": {"standalone_usage_share_min": 0.15}})
    assert analysis.analyze("latent_standalone", th)["areas"]["inference"]["verdict"]["key"] == "standalone_business"
    th = load_thresholds({"behavior": {"standalone_usage_share_min": 0.04}})        # component scenario: behavior flips, rep-led pipeline stays weak
    assert analysis.analyze("component", th)["areas"]["inference"]["verdict"]["key"] == "retention_led"
    th = load_thresholds({"pipeline": {"standalone_demand_share_min": 0.05}})       # demand alone is not enough: it is rep-raised
    assert analysis.analyze("component", th)["areas"]["inference"]["verdict"]["key"] == "component"

def test_cached_memos_pass_number_check(runs):
    for s, r in runs.items():
        for a, x in r["areas"].items():
            m = memo.get_memo(a, x, r["thresholds"])
            assert not m["flagged"], (s, a, m["unmatched_numbers"])
            assert m["source"].startswith("claude (cached)")


# ---------- weaknesses and GTM actions ----------
from analyzer import gtm, data

def _plan(**kw):
    ss = {"n_signups": 100, "signup_volume_index": 1.0, "activation_rate": 0.6, "baseline_activation_rate": 0.6, "paid_90d_rate_no_voice": 0.1, "paid_90d_rate_with_voice": 0.1, "baseline_paid_90d_rate_all_signups": 0.1}
    ss.update(kw.pop("ss", {}))
    b, p, _ = _m(**kw)
    b.update({"retention_12m": {"standalone": {"rate": 0.8, "n": 20}, "attached": {"rate": 0.8, "n": 20}}})
    p.update({"n_standalone": 10, "bundled_win_rate": 0.5, "loss_concerns_voiced": {}, "n_standalone_lost": 0})
    m = {"behavioral": b, "pipeline": p, "selfserve": ss}
    th = load_thresholds(); v = verdict.classify(b, p, ss, th)
    return gtm.plan("inference", m, v, th), v

def test_thin_top_of_funnel_recommends_paid_demand_first():
    plan, _ = _plan(usage=0.5, demand=0.3, win=0.5, ss={"signup_volume_index": 0.4})
    assert plan["weaknesses"][0]["id"] == "topfunnel" and plan["actions"][0]["id"] == "paid_demand"

def test_poor_activation_recommends_onboarding_and_docs():
    plan, _ = _plan(usage=0.5, demand=0.3, win=0.5, ss={"activation_rate": 0.2})
    assert plan["weaknesses"][0]["id"] == "activation" and plan["actions"][0]["id"] == "onboarding"

SS_OK = {"n_signups": 100, "signup_volume_index": 1.0, "activation_rate": 0.6, "baseline_activation_rate": 0.6, "paid_90d_rate_no_voice": 0.1, "paid_90d_rate_with_voice": 0.1, "baseline_paid_90d_rate_all_signups": 0.1}

def test_price_losses_recommend_pricing_action():
    b, p, _ = _m(usage=0.5, demand=0.3, win=0.1)
    b["retention_12m"] = {"standalone": {"rate": 0.8, "n": 20}, "attached": {"rate": 0.8, "n": 20}}
    p.update({"n_standalone": 10, "bundled_win_rate": 0.5, "loss_concerns_voiced": {"price": 6, "latency": 2}, "n_standalone_lost": 8})
    th = load_thresholds(); m = {"behavioral": b, "pipeline": p, "selfserve": SS_OK}
    plan = gtm.plan("inference", m, verdict.classify(b, p, SS_OK, th), th)
    assert "loss_concerns" in [w["id"] for w in plan["weaknesses"]]
    ids = [a["id"] for a in plan["actions"]]
    assert ids[0] == "sales_enablement" and "pricing" in ids          # win rate far below bundled ranks sales enablement first; price losses bring in pricing

def test_weaknesses_cover_distinct_stages_and_actions_are_three():
    plan, _ = _plan(usage=0.05, demand=0.05, win=0.1, ss={"signup_volume_index": 0.5, "activation_rate": 0.3, "paid_90d_rate_no_voice": 0.02, "paid_90d_rate_with_voice": 0.2})
    assert len({w["stage"] for w in plan["weaknesses"]}) == 3 and len(plan["actions"]) == 3
    assert [a["score"] for a in plan["actions"]] == sorted((a["score"] for a in plan["actions"]), reverse=True)

def test_insufficient_evidence_yields_evidence_actions():
    plan, v = _plan(mention=3)
    assert v["key"] == "insufficient" and plan["weaknesses"][0]["id"] == "evidence" and plan["actions"][0]["id"] == "more_calls"

def test_cached_memos_follow_the_plan(runs):
    for s, r in runs.items():
        for a, x in r["areas"].items():
            m = memo.get_memo(a, x, r["thresholds"])
            assert m["actions_match_plan"] and len(m["actions"]) == 3 and len(m["weaknesses"]) >= 1

# ---------- data access ----------
def test_data_bundle_never_includes_the_answer_key():
    for s in ("component", "latent_standalone"):
        files = data.scenario_files(s)
        assert "accounts.csv" in files and sum(k.startswith("transcripts/") for k in files) == 50
        assert not any("truth" in k or "ground" in k or "effective" in k for k in files)

def test_region_na_is_not_read_as_missing():
    accts = data.load("component")["accounts"]
    assert accts["region"].isna().sum() == 0 and (accts["region"] == "NA").sum() > 0


# ---------- hardened memo guard ----------
FACTS2 = {"win_pct": 25.0, "thr_pct": 35.2, "n": 10, "gap": "5.0 pts below (20.0% vs 25.0%)", "retention_window_months": 12, "paid_window_days": 90}
def test_guard_rejects_percent_type_swaps():
    assert memo.check_numbers("Win rate is 25.0% on 10 deals", FACTS2)[0]
    ok, bad = memo.check_numbers("Win rate is 10% on 25 deals", FACTS2); assert not ok and "10%" in bad and "25" in bad   # 10 is a count, 25.0 a percent: both mis-typed
    assert not memo.check_numbers("That is 10.0% of calls", FACTS2)[0] and not memo.check_numbers("across 25 deals", FACTS2)[0]
def test_guard_rejects_spelled_out_and_fractional_numbers():
    for bad in ("about thirty percent of deals", "roughly a quarter are won", "win rate is half of bundled", "doubled versus last time", "fifty deals"):
        assert not memo.check_numbers(bad, FACTS2)[0], bad
    assert memo.check_numbers("A twelve-month window and a ninety-day paid window; the top three actions", FACTS2)[0]


# ---------- CLI ----------
import json, subprocess, sys
def _cli(*args): return subprocess.run([sys.executable, "-m", "analyzer", *args], cwd=ROOT, capture_output=True, text=True)

def test_cli_rejects_unknown_or_bad_thresholds():
    for bad in ("pipeline.bogus=1", "nosuch.key=1", "min_sample=abc", "min_sample", "pipeline=1"):
        r = _cli("verdict", "--scenario", "component", "--set", bad)
        assert r.returncode == 2 and "Traceback" not in r.stderr, bad

def test_cli_override_changes_verdict_and_is_strict_json():
    r = _cli("verdict", "--scenario", "latent_standalone", "--area", "inference", "--no-metrics", "--set", "behavior.standalone_usage_share_min=0.15")
    assert r.returncode == 0
    out = json.loads(r.stdout, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    assert out["areas"]["inference"]["verdict"]["key"] == "standalone_business" and out["thresholds"]["behavior"]["standalone_usage_share_min"] == 0.15


# ---------- stability ----------
from analyzer import stability
def test_bootstrap_is_deterministic_and_reflects_fragility():
    th = load_thresholds(); r = analysis.analyze("latent_standalone", th)["areas"]
    a = stability.bootstrap("latent_standalone", th, r, B=60); b = stability.bootstrap("latent_standalone", th, r, B=60)
    assert a == b                                                       # fixed seed
    inf = a["inference"]; assert abs(sum(inf["distribution"].values()) - 1) < 0.01
    assert inf["point_verdict"] == "latent_standalone" and inf["share_keeping_point_verdict"] < 0.9   # the headline call is fragile
    lo, hi = inf["usage_share_90pct_interval"]; assert lo < r["inference"]["metrics"]["behavioral"]["standalone_usage_share"] < hi
    c = stability.bootstrap("component", th, analysis.analyze("component", th)["areas"], B=60)
    assert c["inference"]["share_keeping_point_verdict"] > 0.9          # the component call is robust


# ---------- validation scoring ----------
from analyzer import validation, extraction
def test_competitor_alias_and_multipart_quotes():
    assert validation._set("OpenAI direct|Together AI") == validation._set(["openai", "Together AI"])
    tx = "**Sam (VP, Co):** We need data to stay in Canada. Honestly latency matters. We swap models often."
    assert extraction.quote_grounded("We need data to stay in Canada. | We swap models often.", tx)
    assert extraction.quote_grounded("data to stay in Canada ... We swap models often", tx)
    assert not extraction.quote_grounded("We need data to stay in Germany. | We swap models often.", tx)   # a fabricated part still fails


# ---------- the app itself must compile and render (AppTest alone reports 0 exceptions on a SyntaxError) ----------
import py_compile
PAGES_ALL = ["Verdict", "Behavioral evidence", "Pipeline evidence", "Stated vs revealed", "Assumptions", "Data and validation", "Data explorer"]

def test_app_and_package_compile():
    for p in [ROOT / "app.py", *(ROOT / "analyzer").glob("*.py"), *(ROOT / "generator").glob("*.py")]:
        py_compile.compile(str(p), doraise=True)

@pytest.mark.parametrize("scenario", ["component", "latent_standalone"])
@pytest.mark.parametrize("page", PAGES_ALL)
def test_every_page_renders(scenario, page):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["scenario"] = scenario; at.session_state["page"] = page; at.run()
    assert not at.exception
    assert len(at.title) == 1 and any("Synthetic data" in e.value for e in at.error), f"{scenario}/{page} did not render (title/banner missing)"
