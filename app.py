"""Portfolio Fit Analyzer (Streamlit UI). All analysis lives in the analyzer/ package; this file only renders."""
import copy, json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analyzer import analysis, data, extraction, gtm, memo, stability, validation
from analyzer.config import AREAS, AREA_LABEL, SCENARIOS, load_thresholds, scenario_description, PROMPT_VERSION
from analyzer.verdict import LABELS

st.set_page_config(page_title="Portfolio Fit Analyzer", page_icon="🧭", layout="wide")
BLUE, ORANGE, GREY, GREEN, RED = "#2563eb", "#ea580c", "#94a3b8", "#0f766e", "#b91c1c"
PAGES = ["Verdict", "Behavioral evidence", "Pipeline evidence", "Stated vs revealed", "Assumptions", "Data and validation", "Data explorer"]
QCOLOR = {"standalone_business": GREEN, "retention_led": "#a16207", "latent_standalone": "#7c3aed", "component": "#475569", "insufficient": RED}

# ---------------- thresholds in session state ----------------
DEFAULT = load_thresholds()
if "T" not in st.session_state: st.session_state["T"] = copy.deepcopy(DEFAULT)
T = st.session_state["T"]

@st.cache_data(show_spinner=False)
def run(scenario, th_json):
    return analysis.analyze(scenario, json.loads(th_json))

@st.cache_data(show_spinner=False)
def run_stability(scenario, th_json):
    th = json.loads(th_json); return stability.bootstrap(scenario, th, analysis.analyze(scenario, th)["areas"], B=300)

@st.cache_data(show_spinner=False)
def run_validation(scenario):
    return validation.validate(scenario, extraction.load_cached(scenario))

def pct(x, d=1): return "n/a" if x is None else f"{x * 100:.{d}f}%"

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown("### Portfolio Fit Analyzer")
    scenario = st.selectbox("Scenario", SCENARIOS, key="scenario", help="Switch between the two synthetic worlds.")
    page = st.radio("Page", PAGES, key="page")
    st.caption(scenario_description(scenario))
    if T != DEFAULT: st.info("Custom thresholds are active (see Assumptions).")

st.error("**Synthetic data: illustrative only.** Every company, call and number here is fictional and machine-generated.", icon="⚠️")
R = run(scenario, json.dumps(T))
D = run(scenario, json.dumps(DEFAULT))
tables = data.load(scenario)

def badge(key, label):
    st.markdown(f"<span style='background:{QCOLOR[key]};color:white;padding:4px 12px;border-radius:14px;font-weight:600'>{label}</span>", unsafe_allow_html=True)

def fig_cfg(fig, h=340):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", y=-0.2))
    return fig

# ================= 1. Verdict =================
if page == "Verdict":
    st.title("Standalone product or Voice AI component?")
    st.caption("Each area is placed in a quadrant from two axes: behavior (does usage show standalone adoption?) and pipeline (do buyers want it standalone, and does it win?). Self-serve adjusts the behavior threshold.")
    cols = st.columns(2)
    for col, a in zip(cols, AREAS):
        x = R["areas"][a]; v = x["verdict"]; m = x["metrics"]; b, p, s = m["behavioral"], m["pipeline"], m["selfserve"]
        with col, st.container(border=True):
            st.subheader(AREA_LABEL[a]); badge(v["key"], v["label"])
            if v["key"] == "insufficient": st.write("Not enough evidence: " + (v["behavior"]["insufficient_reason"] or v["pipeline"]["insufficient_reason"]))
            else: st.write(f"Behavior reads **{v['behavior']['status']}**; pipeline reads **{v['pipeline']['status']}**. " + (v["drivers"][0] if v["drivers"] else ""))
            k = st.columns(2) + st.columns(2)
            k[0].metric("Standalone usage share", pct(b["standalone_usage_share"]), help="Share of this product's revenue not invoked by Voice AI agents.")
            k[1].metric("Standalone demand", pct(p.get("standalone_demand_share")), help="Share of transcripts where the buyer framed it as standalone.")
            k[2].metric("Standalone win rate", pct(p.get("standalone_win_rate")), f"{p.get('n_standalone_closed', 0)} closed deals", delta_color="off")
            k[3].metric("Self-serve paid, no voice", pct(s["paid_90d_rate_no_voice"]), help="Paid within 90 days, signups with this entry product and no voice product.")
            with st.expander("Inputs vs thresholds (what pushes the verdict across a line)", expanded=True):
                for c in v["behavior"]["checks"] + v["pipeline"]["checks"]:
                    st.markdown(f"{'✅' if c['passes'] else '❌'} {c['text']}" + ("  ⚠️ *within 5 pts: sensitive*" if c["sensitive"] else ""))
                st.caption(v["behavior"]["selfserve_note"])
            with st.spinner("Resampling to test how stable this verdict is…"): stab = (run_stability(scenario, json.dumps(T)) or {}).get(a)
            if stab and v["key"] != "insufficient":
                keep, lo_hi = stab["share_keeping_point_verdict"], stab["usage_share_90pct_interval"]
                other = ", ".join(f"{LABELS[k].split(' (')[0]} {p * 100:.0f}%" for k, p in stab["distribution"].items() if k != v["key"] and p >= 0.03)
                (st.success if keep >= 0.9 else st.warning if keep >= 0.6 else st.error)(
                    f"**How stable is this verdict?** It held in {keep * 100:.0f}% of {stab['draws']} resamples of the transcripts and accounts" + (f"; otherwise: {other}." if other else ".")
                    + f" Standalone usage share 90% interval: {lo_hi[0] * 100:.0f}% to {lo_hi[1] * 100:.0f}%.", icon="🎲" if keep >= 0.9 else "⚠️")
            mm = memo.get_memo(a, x, R["thresholds"])
            st.markdown("**Memo** &nbsp; <span style='color:#64748b;font-size:0.8em'>" + mm["source"] + "</span>", unsafe_allow_html=True)
            st.markdown(f"*{mm['headline']}*"); st.markdown(mm["evidence"])
            st.markdown("**Top areas of weakness**")
            for i, w in enumerate(mm["weaknesses"], 1): st.markdown(f"{i}. {w}")
            st.markdown("**Top 3 GTM actions to try**")
            for i, ac in enumerate(mm["actions"], 1):
                st.markdown(f"{i}. **{ac['title']}**  \n{ac['rationale']}  \n*Watch:* {ac['metric_to_watch']}")
            st.caption("Weaknesses are ranked by shortfall against an explicit benchmark; actions by how directly they address those weaknesses. This is a prioritisation heuristic on synthetic data, not a forecast of impact."
                       + (" For a component verdict, read these as experiments to test whether a standalone path is worth unlocking, not as a case for funding a standalone category." if v["key"] == "component" else ""))
            if mm["flagged"]: st.warning(f"Memo flagged: numbers not found in metrics {mm['unmatched_numbers']}; recommendation matches verdict: {mm['recommendation_matches_verdict']}; actions match plan: {mm['actions_match_plan']}")
            else: st.caption("✔ Numbers checked against the metrics object (digits and spelled-out numbers; it cannot tell whether a correct number is attached to the right metric).")
    st.divider(); st.markdown("#### Where each area sits")
    fig = go.Figure()
    for a in AREAS:
        v = R["areas"][a]["verdict"]; m = R["areas"][a]["metrics"]
        fig.add_trace(go.Scatter(x=[m["behavioral"]["standalone_usage_share"] * 100], y=[(m["pipeline"].get("standalone_demand_share") or 0) * 100], mode="markers+text", text=[AREA_LABEL[a]],
                                 textposition="top left" if a == "inference" else "bottom right", marker=dict(size=18, color=QCOLOR[v["key"]]), name=AREA_LABEL[a]))
    fig.add_vline(x=R["areas"]["inference"]["verdict"]["behavior"]["threshold_effective"] * 100, line_dash="dash", line_color=GREY, annotation_text="behavior threshold (inference, after self-serve adj.)")
    fig.add_hline(y=T["pipeline"]["standalone_demand_share_min"] * 100, line_dash="dash", line_color=GREY, annotation_text="demand threshold")
    fig.update_xaxes(title="Standalone usage share of revenue (%)", range=[0, 100]); fig.update_yaxes(title="Standalone demand share of transcripts (%)", range=[0, 60])
    st.plotly_chart(fig_cfg(fig, 380), width="stretch")
    st.caption("Right of the vertical line = standalone adoption in usage. Above the horizontal line = buyers frame it as standalone (the win-rate and buyer-initiated tests then decide 'strong').")

# ================= 2. Behavioral =================
elif page == "Behavioral evidence":
    st.title("Behavioral evidence")
    st.caption("From billing and usage: how is each product actually invoked, and who stays?")
    tabs = st.tabs([AREA_LABEL[a] for a in AREAS])
    for tab, a in zip(tabs, AREAS):
        b = R["areas"][a]["metrics"]["behavioral"]; s = R["areas"][a]["metrics"]["selfserve"]
        with tab:
            k = st.columns(5)
            k[0].metric("Accounts using", b["n_accounts_using"], f"{pct(b['adoption_share'])} of accounts", delta_color="off")
            k[1].metric("Standalone usage share", pct(b["standalone_usage_share"]), help="Revenue not invoked via Voice AI agents. Units share is identical for a single-unit product.")
            k[2].metric("Standalone accounts", b["n_standalone_accounts"], help="Mostly direct usage and no Voice AI agents product.")
            k[3].metric("Voice AI-attached accounts", b["n_attached_accounts"]); k[4].metric("Mixed accounts", b["n_mixed_accounts"], help="Use both paths.")
            c1, c2 = st.columns(2)
            seg = pd.DataFrame([{"segment": sg, "standalone share": v["standalone_usage_share"] * 100, "accounts": v["n_accounts"]} for sg, v in b["by_segment"].items()])
            f = go.Figure(go.Bar(x=seg["segment"], y=seg["standalone share"], marker_color=BLUE, text=[f"{y:.0f}% (n={n})" for y, n in zip(seg["standalone share"], seg["accounts"])], textposition="outside"))
            f.update_yaxes(title="% of revenue", range=[0, 100]); f.update_layout(title="Standalone usage share by segment")
            c1.plotly_chart(fig_cfg(f), width="stretch")
            comp = pd.DataFrame({"Cohort": ["Standalone", "Voice AI"], "Revenue": [f"${b['revenue_by_path']['standalone']:,.0f}", f"${b['revenue_by_path']['attached']:,.0f}"],
                                 "GM": [pct(b["gross_margin_pct"]["standalone"]), pct(b["gross_margin_pct"]["attached"])],
                                 "12-mo ret.": [f"{pct(b['retention_12m']['standalone']['rate'])} (n={b['retention_12m']['standalone']['n']})", f"{pct(b['retention_12m']['attached']['rate'])} (n={b['retention_12m']['attached']['n']})"],
                                 "NRR": [pct(b["nrr_12m"]["standalone"]["nrr"], 0), pct(b["nrr_12m"]["attached"]["nrr"], 0)]})
            c2.markdown("**Standalone vs attached cohorts**"); c2.dataframe(comp, hide_index=True, width="stretch")
            c2.caption("Retention: share of accounts still billing 12 months after first use of that path (only accounts old enough to observe). NRR: revenue at month 12 over month 1.")
            # sankey
            links = b["attach_links"]
            if links:
                nodes = sorted({l["source"] for l in links} | {l["target"] for l in links}, key=lambda n: (n[0], n))
                idx = {n: i for i, n in enumerate(nodes)}
                col = lambda n: BLUE if "(direct)" in n else ORANGE if "via Voice AI" in n else GREY
                sk = go.Figure(go.Sankey(node=dict(label=[n[2:] for n in nodes], color=[col(n) for n in nodes], pad=14),
                                         link=dict(source=[idx[l["source"]] for l in links], target=[idx[l["target"]] for l in links], value=[l["count"] for l in links])))
                sk.update_layout(title=f"Attach flow into {AREA_LABEL[a]}: entry product → (previous product) → {a}")
                st.plotly_chart(fig_cfg(sk, 420), width="stretch")
                med = b["median_months_to_attach"]
                st.caption(f"Median months from entry product to {a}: " + (", ".join(f"{k} {v:g}" for k, v in sorted(med.items())) or "n/a") + f" (overall {b['median_months_to_attach_overall']}).")
            st.markdown("**Self-serve evidence** (developers signing up with this as their entry product)")
            ss = pd.DataFrame([{"Signups": s["n_signups"], "Activated": pct(s["activation_rate"]), "Paid in 90 days (all)": pct(s["paid_90d_rate"]),
                                f"Paid, no voice (n={s['n_no_voice']})": pct(s["paid_90d_rate_no_voice"]), f"Paid, with voice (n={s['n_with_voice']})": pct(s["paid_90d_rate_with_voice"]),
                                "Baseline (all signups)": pct(s["baseline_paid_90d_rate_all_signups"])}])
            st.dataframe(ss, hide_index=True, width="stretch")
            st.caption(R["areas"][a]["verdict"]["behavior"]["selfserve_note"])

# ================= 3. Pipeline =================
elif page == "Pipeline evidence":
    st.title("Pipeline evidence")
    st.caption("From new-business sales calls: Claude extracts framing, who raised it, competitors and concerns (with supporting quotes); outcomes come from the opportunity table.")
    ext = extraction.load_cached(scenario)
    if not ext: st.error("No cached extractions for this scenario."); st.stop()
    tabs = st.tabs([AREA_LABEL[a] for a in AREAS])
    for tab, a in zip(tabs, AREAS):
        p = R["areas"][a]["metrics"]["pipeline"]
        with tab:
            k = st.columns(5)
            k[0].metric("Calls discussing it", f"{p['n_mentioning']} of {p['n_transcripts']}")
            k[1].metric("Standalone demand", pct(p["standalone_demand_share"]), f"{p['n_standalone']} calls", delta_color="off")
            k[2].metric("Raised by buyer (standalone)", pct(p["buyer_initiated_share_standalone"]), help="The rest were raised by the rep: a framing bias to keep in mind.")
            k[3].metric("Standalone win rate", pct(p["standalone_win_rate"]), f"n={p['n_standalone_closed']} closed", delta_color="off")
            k[4].metric("Bundled win rate", pct(p["bundled_win_rate"]), f"n={p['n_bundled_closed']} closed", delta_color="off")
            c1, c2, c3 = st.columns(3)
            f = go.Figure(go.Bar(x=["Standalone", "Bundled with voice"], y=[(p["standalone_win_rate"] or 0) * 100, (p["bundled_win_rate"] or 0) * 100], marker_color=[BLUE, ORANGE],
                                 text=[pct(p["standalone_win_rate"], 0), pct(p["bundled_win_rate"], 0)], textposition="outside")); f.update_yaxes(range=[0, 100], title="% won"); f.update_layout(title="Win rate (closed deals)")
            c1.plotly_chart(fig_cfg(f), width="stretch")
            lr = p["loss_concerns_voiced"]; lr2 = p["loss_reasons_stated"]
            if lr:
                f = go.Figure([go.Bar(y=list(lr), x=list(lr.values()), orientation="h", marker_color=BLUE, name="Concerns voiced"), go.Bar(y=list(lr2), x=list(lr2.values()), orientation="h", marker_color=ORANGE, name="Single biggest")])
                f.update_layout(title=f"Standalone deals lost (n={p['n_standalone_lost']})", barmode="group", yaxis=dict(autorange="reversed")); c2.plotly_chart(fig_cfg(f), width="stretch")
            else: c2.info("No lost standalone deals.")
            cp = p["competitors_standalone"]
            if cp:
                f = go.Figure(go.Bar(y=list(cp), x=list(cp.values()), orientation="h", marker_color=GREY)); f.update_layout(title="Competitors named on standalone calls", yaxis=dict(autorange="reversed")); c3.plotly_chart(fig_cfg(f), width="stretch")
            else: c3.info("No competitors named on standalone calls.")
            st.markdown("##### Drill into a call")
            fk = "inference_framing" if a == "inference" else "edge_framing"
            rows = [r for r in p["table"] if r["framing"] != "not_mentioned"]
            if not rows: st.info("No calls discuss this product."); continue
            labels = {r["opp_id"]: f"{r['opp_id']} · {r['framing']} · raised by {r['raised']} · {r['outcome']}" for r in rows}
            oid = st.selectbox("Call", list(labels), format_func=labels.get, key=f"call_{a}_{scenario}")
            e = ext[oid]; tx = data.transcripts(scenario)[oid]
            show = [("primary_interest", "Primary interest"), ("use_case", "Use case"), (fk, "Framing"), ("inference_raised_by" if a == "inference" else "edge_raised_by", "Raised by"),
                    ("competitors_inference" if a == "inference" else "competitors_edge", "Competitors (this area)"), ("competitors_voice", "Competitors (voice)"), ("decision_criteria", "Decision criteria"), ("stated_reason", "Single biggest concern")]
            for key, name in show:
                v = e[key]; val = ", ".join(v["value"]) if isinstance(v["value"], list) else v["value"]
                ok = extraction.quote_grounded(v["quote"], tx)
                st.markdown(f"**{name}:** `{val or '—'}` &nbsp; <span style='color:#64748b'>confidence: {v['confidence']}</span>" + ("" if ok else " ⚠️ *quote not found verbatim*"), unsafe_allow_html=True)
                if v["quote"]: st.markdown(f"> {v['quote']}")
            with st.expander("Full transcript"): st.markdown(tx)

# ================= 4. Stated vs revealed =================
elif page == "Stated vs revealed":
    st.title("Stated vs revealed")
    st.caption("For won deals linked to an account: what the buyer said on the call (extracted) versus how the account actually used the product afterwards.")
    tabs = st.tabs([AREA_LABEL[a] for a in AREAS])
    for tab, a in zip(tabs, AREAS):
        sv = R["areas"][a]["metrics"]["stated_vs_revealed"]
        with tab:
            k = st.columns(4)
            k[0].metric("Won deals linked to accounts", sv["n_won_linked"]); k[1].metric("Said standalone", sv["n_stated_standalone"])
            k[2].metric("…but mostly via Voice AI", pct(sv["gap_share"]), f"{sv['n_gap']} accounts", delta_color="off"); k[3].metric("…and used directly", sv["n_direct"])
            if sv["n_stated_standalone"] < T["min_sample"]: st.warning(f"Only {sv['n_stated_standalone']} accounts said standalone (minimum sample {T['min_sample']}): treat the share as anecdotal.")
            df = pd.DataFrame(sv["table"])
            if df.empty: st.info("No linked won deals."); continue
            order = {"standalone": 0, "bundled_with_voice": 1, "not_mentioned": 2}
            df = df.sort_values(by=["stated", "revealed"], key=lambda c: c.map(order) if c.name == "stated" else c)
            st.dataframe(df.rename(columns={"direct_rev": "direct revenue (USD)", "voice_rev": "via Voice AI (USD)"}), hide_index=True, width="stretch")
            ex_df = df[df.stated == "standalone"]
            if len(ex_df):
                pick = st.selectbox("Example account", list(ex_df.account_id), format_func=lambda x: f"{x} · {ex_df.set_index('account_id').loc[x, 'company']} · {ex_df.set_index('account_id').loc[x, 'revealed']}", key=f"ex_{a}_{scenario}")
                u = tables["usage_monthly"]; u = u[(u.account_id == pick) & (u["product"] == a)].copy()
                if u.empty: st.info("This account has no usage of the product.")
                else:
                    u["path"] = u.invoked_via.map(lambda v: "Via Voice AI" if v == "voice_ai_agent" else "Direct")
                    g = u.pivot_table(index="month", columns="path", values="revenue_usd", aggfunc="sum", fill_value=0).reset_index()
                    f = go.Figure([go.Bar(x=g["month"], y=g[c], name=c, marker_color=BLUE if c == "Direct" else ORANGE) for c in g.columns if c != "month"]); f.update_layout(barmode="stack", title=f"{pick}: monthly {a} revenue by invoking path")
                    st.plotly_chart(fig_cfg(f), width="stretch")
            st.caption("Revealed = whichever path carries more of the account's revenue for this product. 'none' = the account never used it.")

# ================= 5. Assumptions =================
elif page == "Assumptions":
    st.title("Assumptions")
    st.caption("Every threshold the verdicts use. Move a slider and every page recomputes. Defaults live in analyzer/thresholds.yaml.")
    def S(label, path, lo, hi, step, help=None):
        sec, _, name = path.partition("."); cur = T[sec][name] if name else T[sec]
        wkey = f"w{st.session_state.get('nonce', 0)}_{path}"
        def cb():
            val = st.session_state[wkey]
            if name: T[sec][name] = val
            else: T[sec] = val
        return st.slider(label, lo, hi, float(cur) if not isinstance(cur, int) else int(cur), step, key=wkey, on_change=cb, help=help)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Behavior axis")
        S("Standalone usage share needed for 'standalone adoption'", "behavior.standalone_usage_share_min", 0.0, 1.0, 0.01, "Share of revenue not invoked by Voice AI.")
        S("Minimum accounts using the product", "behavior.min_accounts_using", 1, 50, 1)
        st.markdown("##### Self-serve adjustment")
        S("Adjustment size", "selfserve.adjust_pp", 0.0, 0.2, 0.01, "Added to / subtracted from the behavior threshold.")
        S("'Strong' paid rate without voice (lowers threshold)", "selfserve.strong_paid_rate_no_voice", 0.0, 0.5, 0.01)
        S("'Weak' paid rate without voice (raises threshold if voice converts better)", "selfserve.weak_paid_rate_no_voice", 0.0, 0.5, 0.01)
        S("Voice-conversion multiple that counts as voice-dependent", "selfserve.weak_voice_multiple", 1.0, 5.0, 0.1)
    with c2:
        st.markdown("##### Pipeline axis")
        S("Standalone demand share needed", "pipeline.standalone_demand_share_min", 0.0, 0.6, 0.01, "Share of transcripts where the buyer framed it standalone.")
        S("Buyer-initiated share of standalone mentions", "pipeline.buyer_initiated_share_min", 0.0, 1.0, 0.01)
        S("Standalone win rate needed", "pipeline.standalone_win_rate_min", 0.0, 1.0, 0.01)
        st.markdown("##### Evidence floor")
        S("Minimum relevant opportunities", "min_sample", 1, 30, 1, "Below this, the tool says 'insufficient evidence' instead of a quadrant.")
        S("Sensitivity band (flag inputs within this of a line)", "near_threshold_pp", 0.0, 0.2, 0.01)
    if st.button("Reset to defaults"):
        st.session_state["T"] = copy.deepcopy(DEFAULT)
        st.session_state["nonce"] = st.session_state.get("nonce", 0) + 1   # fresh widget keys so sliders rebuild at the defaults
        st.rerun()
    st.markdown("#### Verdicts under these assumptions")
    rows = []
    for a in AREAS:
        v, d = R["areas"][a]["verdict"], D["areas"][a]["verdict"]
        rows.append({"Area": AREA_LABEL[a], "Verdict now": v["label"], "Default verdict": d["label"], "Changed": "◀ changed" if v["key"] != d["key"] else "",
                     "Behavior": f"{v['behavior']['status']} (threshold {pct(v['behavior']['threshold_effective'])})", "Pipeline": v["pipeline"]["status"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.markdown("""**How the verdict is built**
- *Behavior axis:* standalone if the share of the product's revenue not invoked by Voice AI is at or above the threshold. **Self-serve adjusts that threshold**: if signups with this entry product pay within 90 days without voice at or above the 'strong' rate, the threshold drops by the adjustment size (independent developer pull); if the no-voice paid rate is below the 'weak' rate *and* signups with voice convert at least the multiple better, it rises by the adjustment size (conversion depends on voice). Otherwise no change, and no change when there are too few signups.
- *Pipeline axis:* strong only if standalone demand share, buyer-initiated share and standalone win rate all clear their thresholds; otherwise weak.
- *Evidence floor:* fewer than the minimum relevant opportunities (or too few closed standalone deals to judge a win rate, or too few accounts) gives 'insufficient evidence'.
- Quadrants: standalone adoption + strong pipeline = Standalone business; standalone adoption + weak pipeline = Retention-led standalone; attached + strong pipeline = Latent standalone; attached + weak pipeline = Component of Voice AI.""")

# ================= 6. Data and validation =================
elif page == "Data and validation":
    st.title("Data and validation")
    st.markdown(f"**Scenario `{scenario}`**: {scenario_description(scenario)}")
    cnt = st.columns(5)
    cnt[0].metric("Accounts", len(tables["accounts"])); cnt[1].metric("Usage rows", f"{len(tables['usage_monthly']):,}"); cnt[2].metric("Opportunities", len(tables["opportunities"]))
    cnt[3].metric("Transcripts", len(data.transcripts(scenario))); cnt[4].metric("Signups", f"{len(tables['signups']):,}")
    st.markdown("#### Did the extractions get it right?")
    st.caption(f"Claude's transcript extractions are scored against the hidden answer key the generator wrote. Only the validation module reads that key (it also serves the answer-key download on Data explorer). Model: `{extraction.model_name()}`, prompt version `{PROMPT_VERSION}`.")
    vres = run_validation(scenario)
    if not vres["n_transcripts"]: st.error("No cached extractions to validate.")
    else:
        h = st.columns(3)
        acc = vres["framing_and_raised_by_accuracy"]
        h[0].metric("Framing + raised-by accuracy", pct(acc), help="Target: at least 85%."); h[1].metric("Transcripts scored", vres["n_transcripts"]); h[2].metric("Quotes found verbatim", pct(vres["quote_grounding_rate"]))
        fv = pd.DataFrame([{"Field": f["field"], "Metric": f["metric"], "n": f["n"], "Accuracy": round(f["accuracy"] * 100, 1), "Mean Jaccard": "–" if f.get("mean_jaccard") is None else f"{f['mean_jaccard']:.2f}",
                            "Acc. when high conf. %": "–" if f["acc_high"] is None else f"{f['acc_high'] * 100:.1f}", "n high": f["n_high"]} for f in vres["fields"]])
        st.dataframe(fv, hide_index=True, width="stretch", column_config={"Accuracy": st.column_config.ProgressColumn("Accuracy %", min_value=0, max_value=100, format="%.1f")})
        st.caption("Competitor names are matched case-insensitively and "OpenAI direct" counts as "OpenAI". Decision criteria are scored as an exact set match (harsh) and by Jaccard overlap. 'Single biggest concern' is only scored on lost deals, and transcripts voice several concerns, so it is the weakest field: treat loss-reason shares as directional.")
        with st.expander(f"Misses ({len(vres['errors'])})"): st.dataframe(pd.DataFrame(vres["errors"]), hide_index=True, width="stretch")
    try: hist = json.load(open(__import__("analyzer.config", fromlist=["CACHE"]).CACHE / "prompt_history.json"))
    except Exception: hist = {}
    if hist:
        st.markdown("#### Prompt history")
        for ver, h in hist.items():
            r = h["results"]; st.markdown(f"- **{ver}**: {h['change']} Framing + raised-by: " + ", ".join(f"{s} {pct(x['framing_and_raised_by_accuracy'])}" for s, x in r.items()) + "; criteria exact: " + ", ".join(f"{s} {pct(x['fields']['decision_criteria'])}" for s, x in r.items()))
    st.markdown("#### Data sources")
    st.markdown("- **Behavioral:** `usage_monthly.csv`, `accounts.csv`: monthly usage and billing by product, with an `invoked_via` field separating Voice AI-driven from direct use.\n- **Pipeline:** `transcripts/*.md` and `opportunities.csv`: new-business calls and deal outcomes.\n- **Self-serve:** `signups.csv`: developer signups by entry product, activation and paid-in-90-days.\n- All synthetic, generated by `generator/` from a scenario file. See the README for limitations.")


# ================= 7. Data explorer =================
else:
    import io, zipfile
    st.title("Data explorer")
    st.markdown("Everything the verdicts rest on, for both synthetic worlds: browse it here or download it. All of it is fictional and generated from the scenario files in `scenarios/` by the generator in `generator/`.")
    @st.cache_data(show_spinner=False)
    def bundle(s, with_key):
        files = dict(data.scenario_files(s))
        if with_key: files.update(validation.answer_files(s))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, b in files.items(): z.writestr(f"{s}/{name}", b)
        return buf.getvalue()
    @st.cache_data(show_spinner=False)
    def ext_json(s): return json.dumps({k: v for k, v in extraction.load_cached(s).items()}, indent=1).encode()
    st.markdown(f"#### Scenario `{scenario}`")
    c = st.columns(3)
    c[0].download_button("Download full scenario (zip: tables, transcripts)", bundle(scenario, False), f"{scenario}_synthetic_data.zip", "application/zip", width="stretch")
    c[1].download_button("…plus the hidden answer key", bundle(scenario, True), f"{scenario}_with_answer_key.zip", "application/zip", width="stretch",
                         help="The answer key is what the extraction validation scores against (the generator's true values).")
    c[2].download_button("Claude's extractions (JSON, with quotes)", ext_json(scenario), f"{scenario}_extractions.json", "application/json", width="stretch")
    st.caption("The other scenario is one switch away in the sidebar. Table descriptions are in the data dictionary below.")
    names = {"accounts": "Accounts", "usage_monthly": "Monthly usage and billing", "opportunities": "Opportunities", "signups": "Self-serve signups"}
    tabs = st.tabs(list(names.values()) + ["Transcripts", "Data dictionary"])
    for tab, (key, label) in zip(tabs, names.items()):
        with tab:
            df = tables[key].drop(columns=["m"], errors="ignore")
            st.caption(f"{len(df):,} rows × {len(df.columns)} columns")
            st.dataframe(df, hide_index=True, width="stretch", height=420)
            st.download_button(f"Download {key}.csv", df.to_csv(index=False).encode(), f"{scenario}_{key}.csv", "text/csv", key=f"dl_{key}_{scenario}")
    with tabs[4]:
        trs = data.transcripts(scenario)
        oid = st.selectbox("Transcript", list(trs), key=f"tx_{scenario}")
        st.download_button("Download this transcript (.md)", trs[oid].encode(), f"{scenario}_{oid}.md", "text/markdown", key=f"dltx_{scenario}")
        st.markdown(trs[oid])
    with tabs[5]:
        st.markdown((data.DATA_README).read_text() if hasattr(data, "DATA_README") else "")
