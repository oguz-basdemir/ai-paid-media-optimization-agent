"""Portfolio dashboard: all analysis and workflow operations go through FastAPI."""

import json
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from paid_media.client import call
from paid_media.store import TRANSITIONS

st.set_page_config(page_title="Paid Media Lab", page_icon="◈", layout="wide")
st.markdown(
    """<style>
    .block-container {padding-top:4.5rem; max-width:1500px;}
    [data-testid="stMetric"] {background:#142035; border:1px solid #24364d; padding:18px; border-radius:12px;}
    [data-testid="stMetricLabel"] {color:#91a6c2; font-size:.85rem;}
    h1 {letter-spacing:-.045em;} h2 {letter-spacing:-.025em;}
    .eyebrow {color:#78e2bd; font-size:12px; letter-spacing:3px; font-weight:700; margin-bottom:12px;}
    .subtle {color:#a4b4cc; margin-bottom:24px;}
    .rail {border:1px solid #284355; border-radius:8px; padding:12px 18px; background:#102333;
           color:#a4dacd; font-size:13px; margin:12px 0 25px;}
    [data-testid="stSidebar"] {border-right:1px solid #24364d;}
</style>""",
    unsafe_allow_html=True,
)


def money(value):
    return f"${value:,.2f}" if value is not None else "N/A"


def pct(value):
    return f"{value:.2%}" if value is not None else "N/A"


def kpis(m):
    cols = st.columns(6)
    values = [
        ("Spend", f"${m['spend'] / 1000:,.1f}k" if m["spend"] >= 1000 else money(m["spend"])),
        ("Conversions", f"{m['conversions']:,.0f}"),
        ("CPA", money(m["cpa"])),
        ("ROAS", f"{m['roas']:.2f}×" if m["roas"] is not None else "N/A"),
        ("CTR", pct(m["ctr"])),
        ("CVR", pct(m["cvr"])),
    ]
    for col, (label, value) in zip(cols, values, strict=True):
        col.metric(label, value)


def campaign_table(campaigns):
    rows = [
        {
            "Campaign": c["campaign"],
            "Platform": c["platform"],
            "Health": c["health_score"],
            "Spend": c["metrics"]["spend"],
            "CPA": c["metrics"]["cpa"],
            "ROAS": c["metrics"]["roas"],
            "CVR": c["metrics"]["cvr"],
            "Issues": len(c["issues"]),
        }
        for c in campaigns
    ]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Health": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
            "Spend": st.column_config.NumberColumn(format="$%.2f"),
            "CPA": st.column_config.NumberColumn(format="$%.2f"),
            "CVR": st.column_config.NumberColumn(
                format="percent", help="Conversion rate, conversions / clicks"
            ),
        },
    )


def experiment_card(r):
    ex = r["experiment"]
    st.markdown(f"**Hypothesis** · {ex['hypothesis']}")
    st.write("**Test** · " + ex["test"])
    a, b = st.columns(2)
    a.write(f"**Primary KPI:** {ex['primary_kpi']}")
    b.write(f"**Secondary KPI:** {ex['secondary_kpi']}")
    st.success(ex["success_criteria"])
    st.caption(ex["design"] + " · " + ex["duration"])
    st.write("**Guardrails:** " + "; ".join(ex["guardrails"]))
    if ex["planning"]:
        p = ex["planning"]
        st.info(
            f"Planning estimate: {p['trials_per_arm']:,} {p['trial_unit']} per arm · "
            f"~{p['estimated_days']} days · 80% power · 5% alpha · 15% relative MDE"
        )
        st.caption(p["caveat"])
        if p["estimated_days"] > 90:
            st.warning(
                "This effect size is impractical at current traffic. Review the MDE, pool compatible traffic, "
                "or prioritize a different experiment before approval."
            )
    else:
        st.caption(
            "CPA/ROAS and diagnostic tests need a separate variance-aware or checklist design; no binomial power claim."
        )
    st.caption(ex["decision_rule"])


def show_overview(report, params, platform=None):
    kpis(report["overview"])
    st.write("")
    left, right = st.columns([1.65, 1])
    series = pd.DataFrame(call("GET", "/series", params={"platform": platform} if platform else {}))
    finish = pd.Timestamp(params["end"])
    series = series[
        (pd.to_datetime(series.date) > finish - pd.Timedelta(days=2 * params["window"]))
        & (pd.to_datetime(series.date) <= finish)
    ]
    with left:
        st.subheader("Spend across the decision window")
        chart = (
            alt.Chart(series)
            .mark_line(strokeWidth=2.5)
            .encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("spend:Q", title="Daily spend · USD"),
                color=alt.Color(
                    "platform:N", scale=alt.Scale(range=["#78e2bd", "#9d9aff", "#f4be78"]), title=None
                ),
                tooltip=["date:T", "platform:N", alt.Tooltip("spend:Q", format="$.2f"), "conversions:Q"],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, width="stretch")
    with right:
        st.subheader("Channel efficiency")
        channels = pd.DataFrame(report["platforms"])
        st.altair_chart(
            alt.Chart(channels)
            .mark_bar(cornerRadiusEnd=5, color="#78e2bd")
            .encode(
                y=alt.Y("platform:N", title=None),
                x=alt.X("cpa:Q", title="CPA · USD"),
                tooltip=[
                    "platform:N",
                    alt.Tooltip("cpa:Q", format="$.2f"),
                    alt.Tooltip("roas:Q", format=".2f"),
                ],
            )
            .properties(height=280),
            width="stretch",
        )
        st.caption("Compare against channel targets and lead quality, not CPA alone.")
    st.subheader("Campaigns at a glance")
    campaign_table(report["campaigns"])
    with st.expander("Full performance metrics and measurement notes"):
        st.dataframe(pd.DataFrame(report["platforms"]), hide_index=True, width="stretch")
        st.caption("MQL cost uses spend only on rows with CRM coverage. Unknown MQLs remain unknown.")
        st.caption(
            "Frequency is an impression-weighted proxy; unique reach is unavailable. Revenue is synthetic attributed value."
        )


def show_health(report):
    st.caption(
        "Explainable 0–100 planning score. Components: efficiency 35%, quality 20%, trend 20%, spend 10%, confidence 15%."
    )
    campaign_table(report["campaigns"])
    cid = st.selectbox(
        "Inspect campaign",
        [c["campaign_id"] for c in report["campaigns"]],
        format_func=lambda x: next(c["campaign"] for c in report["campaigns"] if c["campaign_id"] == x),
    )
    c = next(c for c in report["campaigns"] if c["campaign_id"] == cid)
    left, right = st.columns(2)
    with left:
        st.subheader(f"Health score · {c['health_score']}")
        components = pd.DataFrame(
            [{"Component": k.replace("_", " ").title(), "Score": v} for k, v in c["components"].items()]
        )
        st.altair_chart(
            alt.Chart(components)
            .mark_bar(color="#9d9aff")
            .encode(y=alt.Y("Component:N", title=None), x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 100])))
            .properties(height=220),
            width="stretch",
        )
        st.write("**Planning targets:**", c["targets"])
        if not c["quality_available"]:
            st.warning(
                "MQL coverage unavailable: quality receives a neutral 50/100; validate CRM data before acting."
            )
        if not c["complete_windows"]:
            st.warning(
                "Incomplete comparison windows: trend evidence is suppressed and confidence is discounted."
            )
    with right:
        st.subheader("Evidence and uncertainty")
        interval = c["cvr_interval_95"]
        st.write(f"Observed CVR 95% Wilson interval: {pct(interval[0])} – {pct(interval[1])}")
        st.caption(report["confidence_note"])
        for issue in c["issues"]:
            st.write(f"**{issue['severity']} · {issue['reason']}**")
            st.caption(f"Confidence: {issue['confidence']}")
            st.json(issue["evidence"], expanded=False)
        if not c["issues"]:
            st.success("No rule-based underperformance flags in this window.")


def show_fatigue(report):
    st.info(
        "Likely fatigue requires frequency ≥3, ≥1,000 impressions per window, CTR down >15% and CPA up >15%."
    )
    f = pd.DataFrame(report["fatigue"])
    if f.empty:
        st.success("No creative satisfies all fatigue conditions for this window.")
        return
    st.dataframe(f, hide_index=True, width="stretch")
    st.altair_chart(
        alt.Chart(f)
        .mark_circle(size=280)
        .encode(
            x=alt.X("frequency:Q", title="Exposure frequency proxy"),
            y=alt.Y("ctr_change:Q", axis=alt.Axis(format="%"), title="CTR change vs prior window"),
            color="platform:N",
            tooltip=["creative:N", "frequency:Q", "ctr_change:Q", "cpa_change:Q"],
        )
        .properties(height=330),
        width="stretch",
    )
    st.caption(
        "Fatigue is a hypothesis. Audience changes, auction pressure and tracking shifts can produce similar signals."
    )


def show_recommendations(params):
    if st.button("Generate proposals for selected window", type="primary"):
        call("POST", "/recommendations/generate", params=params)
        st.success("Proposals saved. Existing decisions are preserved.")
    records = call("GET", "/recommendations")
    st.caption(
        "Saved proposals retain their original evidence window. Approvals record a decision; campaign changes remain manual."
    )
    selected_status = st.multiselect("Status filter", list(TRANSITIONS), default=list(TRANSITIONS))
    filtered = [r for r in records if r["status"] in selected_status]
    st.download_button(
        "Export review register", json.dumps(filtered, indent=2), "recommendations.json", "application/json"
    )
    if not filtered:
        st.info("No recommendations match this filter.")
        return
    counts = {status: sum(r["status"] == status for r in records) for status in TRANSITIONS}
    for col, (status, count) in zip(st.columns(5), counts.items(), strict=True):
        col.metric(status, count)
    rid = st.selectbox(
        "Review recommendation",
        [r["id"] for r in filtered],
        format_func=lambda x: next(
            f"{r['platform']} · {r['campaign_id']} · {r['action']} · {r['status']}"
            for r in filtered
            if r["id"] == x
        ),
    )
    r = next(r for r in filtered if r["id"] == rid)
    st.subheader(r["action"])
    st.write(r["reason"])
    st.caption(
        f"{r['campaign']} · {r['severity']} priority · {r['confidence']} confidence · "
        f"as of {r['as_of']} · {r['window_days']}-day window · version {r['version']}"
    )
    with st.expander("Evidence and proposed experiment", expanded=True):
        st.json(r["evidence"], expanded=False)
        experiment_card(r)
    allowed = sorted(TRANSITIONS[r["status"]])
    if allowed:
        next_status = st.selectbox("Next status", allowed)
        with st.form("review_form"):
            a, b = st.columns(2)
            reviewer = a.text_input("Reviewer", placeholder="Your name")
            notes = b.text_input(
                "Decision rationale", placeholder="Why approve, reject or advance this test?"
            )
            result = None
            if next_status == "Completed":
                st.write(f"**Record results · {r['experiment']['primary_kpi']}**")
                st.caption(
                    "Use fractions for rate KPIs, USD for CPA, multiples for ROAS. Outcome is a human assessment."
                )
                x, y = st.columns(2)
                baseline = x.number_input("Control KPI value", min_value=0.0, value=0.04, format="%.4f")
                variant = y.number_input("Variant KPI value", min_value=0.0, value=0.046, format="%.4f")
                control_n = x.number_input("Control sample size", min_value=1, value=1000)
                variant_n = y.number_input("Variant sample size", min_value=1, value=1000)
                start = x.date_input("Test start", value=date.fromisoformat(r["as_of"]))
                end = y.date_input("Test end", value=date.fromisoformat(r["as_of"]))
                outcome = x.selectbox("Outcome", ["Inconclusive", "Success", "Failure"])
                guardrails = y.checkbox("Guardrails passed", value=False)
                result_notes = st.text_area(
                    "Result interpretation",
                    placeholder="Include effect uncertainty, traffic quality and attribution lag.",
                )
                result = {
                    "primary_kpi": r["experiment"]["primary_kpi"],
                    "baseline_value": baseline,
                    "variant_value": variant,
                    "control_sample": control_n,
                    "variant_sample": variant_n,
                    "started_on": start.isoformat(),
                    "ended_on": end.isoformat(),
                    "outcome": outcome,
                    "guardrails_passed": guardrails,
                    "notes": result_notes,
                }
            submitted = st.form_submit_button("Record human decision", type="primary")
        if submitted:
            call(
                "PATCH",
                f"/recommendations/{rid}",
                json={
                    "status": next_status,
                    "reviewer": reviewer,
                    "notes": notes,
                    "expected_version": r["version"],
                    "result": result,
                },
            )
            st.rerun()
    if r["result"]:
        st.subheader("Recorded test result")
        st.json(r["result"])
    with st.expander("Approval history"):
        history = call("GET", f"/recommendations/{rid}/history")
        if history:
            st.dataframe(pd.DataFrame(history), hide_index=True, width="stretch")
        else:
            st.caption("Awaiting first human decision.")


def show_experiments():
    records = call("GET", "/recommendations")
    st.caption(
        "One experiment per issue. Prioritize related hypotheses and avoid overlapping changes on the same audience."
    )
    for r in records:
        with st.expander(
            f"{r['campaign_id']} · {r['experiment']['primary_kpi']} · {r['action']} [{r['status']}]"
        ):
            st.caption(f"Evidence window ends {r['as_of']} · {r['window_days']} days")
            experiment_card(r)


def show_creative():
    st.caption("Draft variants from a mock brief. Offline templates work without an API key.")
    with st.form("creative_brief"):
        a, b = st.columns(2)
        audience = a.text_input("Audience", "Revenue operations leaders")
        product = b.text_input("Product", "Revenue analytics software")
        tone = a.selectbox("Brand tone", ["Professional", "Friendly", "Bold", "Playful"])
        goal = b.text_input("Campaign goal", "Book a demo")
        use_ai = st.checkbox("Use optional AI provider for this synthetic brief", value=False)
        st.caption(
            "AI use requires ENABLE_AI=true on the API server. Only the entered brief is sent to the configured provider."
        )
        submit = st.form_submit_button("Generate creative variants", type="primary")
    if submit:
        st.session_state.creative = call(
            "POST",
            "/creative/draft",
            json={
                "audience": audience,
                "product": product,
                "brand_tone": tone,
                "campaign_goal": goal,
                "use_ai": use_ai,
            },
        )
    if "creative" in st.session_state:
        draft = st.session_state.creative
        st.caption(draft["source"] + " · human review required")
        for col, key in zip(st.columns(2), ["headlines", "primary_text"], strict=True):
            with col:
                st.subheader(key.replace("_", " ").title())
                for value in draft[key]:
                    st.write("• " + value)
        for col, key in zip(st.columns(2), ["ctas", "angles"], strict=True):
            with col:
                st.subheader(key.title())
                for value in draft[key]:
                    st.write("• " + value)
        st.download_button(
            "Export drafts", json.dumps(draft, indent=2), "creative-drafts.json", "application/json"
        )


def show_landing(report):
    st.caption("Mock metadata only. Alignment scores are transparent keyword and CTA heuristics.")
    for p in report["landing_pages"]:
        with st.expander(f"{p['campaign_id']} · Alignment {p['alignment_score']}/100 · {p['landing_page']}"):
            left, right = st.columns(2)
            left.write("**Ad promise:** " + p["ad_message"])
            left.write("**Keywords:** " + ", ".join(p["keywords"]))
            right.write("**Page headline:** " + p["headline"])
            right.write("**Proposition:** " + p["proposition"])
            right.write("**CTA:** " + p["cta"])
            st.write(p["reason"])


def show_budget(params):
    st.warning("Decision-support simulation - not financial forecasting.")
    fraction = st.slider("Maximum donor redistribution", 0, 30, 10, format="%d%%") / 100
    sim = call("GET", "/budget-simulation", params={**params, "shift_fraction": fraction})
    rows = pd.DataFrame(sim["rows"])
    a, b, c = st.columns(3)
    a.metric("Historical spend", money(rows.historical_spend.sum()))
    b.metric("Scenario spend", money(rows.simulated_spend.sum()))
    c.metric("Reallocated", money(rows.budget_delta.clip(lower=0).sum()))
    st.dataframe(rows, hide_index=True, width="stretch")
    st.altair_chart(
        alt.Chart(
            rows.melt(
                id_vars=["campaign_id"],
                value_vars=["historical_spend", "simulated_spend"],
                var_name="Scenario",
                value_name="Spend",
            )
        )
        .mark_bar()
        .encode(
            x="campaign_id:N",
            y="Spend:Q",
            xOffset="Scenario:N",
            color=alt.Color("Scenario:N", scale=alt.Scale(range=["#516b90", "#78e2bd"])),
            tooltip=["campaign_id:N", "Scenario:N", "Spend:Q"],
        )
        .properties(height=320),
        width="stretch",
    )
    for assumption in sim["assumptions"]:
        st.caption("• " + assumption)
    st.download_button("Export simulation", rows.to_csv(index=False), "budget-simulation.csv", "text/csv")


def main():
    metadata = call("GET", "/metadata")
    with st.sidebar:
        st.markdown("### ◈ PAID MEDIA LAB")
        st.caption("OPTIMIZATION & EXPERIMENTATION")
        section = st.radio(
            "Workspace",
            [
                "Cross-Channel Overview",
                "Google Ads",
                "Meta",
                "LinkedIn",
                "Campaign Health",
                "Creative Fatigue",
                "Experiments",
                "Recommendations",
                "Creative Studio",
                "Landing-Page Analysis",
                "Budget Simulator",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("ANALYSIS SCOPE")
        finish = st.date_input(
            "Window ends",
            value=date.fromisoformat(metadata["max_date"]),
            min_value=date.fromisoformat(metadata["min_date"]),
            max_value=date.fromisoformat(metadata["max_date"]),
        )
        window = st.selectbox(
            "Comparison window", [7, 14, 28], index=1, format_func=lambda x: f"{x} days vs prior {x} days"
        )
        st.caption(f"{metadata['rows']:,} synthetic daily creative rows · USD")
        st.markdown("**Human control, always.**")
        st.caption("No ad accounts connected. No campaign or budget execution capability.")
    st.markdown(
        '<div class="eyebrow">AI PAID MEDIA OPTIMIZATION & EXPERIMENTATION AGENT</div>',
        unsafe_allow_html=True,
    )
    st.title(section)
    subtitles = {
        "Cross-Channel Overview": "From channel signals to evidence-led decisions.",
        "Recommendations": "Review the evidence. Approve the test. Keep control.",
        "Experiments": "Turn performance signals into falsifiable hypotheses.",
        "Budget Simulator": "Explore constrained allocation scenarios before making a decision.",
    }
    st.markdown(
        f'<div class="subtle">{subtitles.get(section, "Understand the signal. Design the next experiment.")}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="rail">SYNTHETIC DATA ONLY &nbsp; / &nbsp; HUMAN APPROVAL REQUIRED &nbsp; / &nbsp; NO CAMPAIGN EXECUTION</div>',
        unsafe_allow_html=True,
    )
    params = {"end": finish.isoformat(), "window": window}
    platform = {"Google Ads": "Google Ads", "Meta": "Meta Ads", "LinkedIn": "LinkedIn Ads"}.get(section)
    report = call("GET", "/analysis", params={**params, **({"platform": platform} if platform else {})})
    if section in {"Cross-Channel Overview", "Google Ads", "Meta", "LinkedIn"}:
        show_overview(report, params, platform)
    elif section == "Campaign Health":
        show_health(report)
    elif section == "Creative Fatigue":
        show_fatigue(report)
    elif section == "Recommendations":
        show_recommendations(params)
    elif section == "Experiments":
        show_experiments()
    elif section == "Creative Studio":
        show_creative()
    elif section == "Landing-Page Analysis":
        show_landing(report)
    else:
        show_budget(params)
    st.divider()
    st.caption(
        "PAID MEDIA LAB · Synthetic demonstration · Thresholds are planning assumptions, not universal benchmarks."
    )


try:
    main()
except RuntimeError as exc:
    st.error(str(exc))
    st.info("Run the API and dashboard using the README quickstart or docker compose up --build.")
