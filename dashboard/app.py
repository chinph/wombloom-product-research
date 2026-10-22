"""Wombloom market research dashboard.

Reads only the aggregated files in data/aggregates/ (built by src/build_aggregates.py), the registers in
data/registers/ and the scoring model in src/prioritize.py. No review table or reviewer data is included.
Run from the project root:  streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "aggregates"
REGISTERS = ROOT / "data" / "registers"
sys.path.insert(0, str(ROOT / "src"))
import prioritize  # noqa: E402

SEGMENT_ORDER = ["Direct", "Category leader", "Adjacent"]
TIER_COLORS = alt.Scale(domain=["reliable", "directional"], range=["#2a6f97", "#c0504d"])
STATUS_COLORS = alt.Scale(domain=["Shipped", "Partial", "Missing", "Not applicable yet"],
                          range=["#7a9e7e", "#e9c46a", "#c0504d", "#c9ced6"])
WINDOW_LABELS = {"all": "All reviews", "last_24m": "Last 24 months"}

st.set_page_config(page_title="Wombloom market research", layout="wide")


@st.cache_data
def load(name, folder=DATA):
    return pd.read_csv(folder / name)


@st.cache_data
def stability(window, efforts_items):
    ev = load("action_evidence.csv")
    return prioritize.rank_stability(ev[ev["window"] == window], dict(efforts_items), n_draws=3000)


rates, impact, evidence = load("theme_app_rates.csv"), load("theme_impact.csv"), load("action_evidence.csv")
baseline, accuracy, probe = load("baseline.csv"), load("theme_accuracy.csv"), load("feature_probe.csv")
register, quotes = load("actions_register.csv", REGISTERS), load("evidence_quotes.csv", REGISTERS)
tier_of = impact[impact["window"] == "all"].set_index("theme")["tier"]
theme_label = impact[impact["window"] == "all"].set_index("theme")["label"]
theme_order = list(theme_label)

st.title("Wombloom market research")
st.caption("What 7,024 usable App Store reviews of 10 pregnancy and baby apps say about what to build. "
           "Aggregated numbers and a few public quotes only. Analysis of record: the project notebook.")

window = st.sidebar.radio("Time window", list(WINDOW_LABELS), format_func=WINDOW_LABELS.get,
                          help="Last 24 months leaves out apps with fewer than 30 reviews in that period.")
base = baseline[baseline["window"] == window].iloc[0]
st.sidebar.markdown(f"**{int(base['reviews']):,} reviews in this view**  \nAverage rating {base['avg_rating']:.2f}  \n"
                    f"{base['pct_low']:.1f}% are 1-2 stars")
st.sidebar.markdown("Blue means the keyword rule that finds the topic was reliable on held-out tests. "
                    "Red means directional: a lead to check, not a measurement.")

tabs = st.tabs(["Summary", "Feature gap matrix", "Prioritization", "Evidence", "Plan vs reality", "Method"])

# ---------------------------------------------------------------- Summary
with tabs[0]:
    ev = evidence[evidence["window"] == window]
    default_scored = prioritize.score_actions(ev).merge(register[["action_id", "action", "priority"]], on="action_id")
    stab_default = stability(window, tuple(sorted(register.set_index("action_id")["effort_default"].items())))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Usable reviews", f"{int(base['reviews']):,}")
    c2.metric("Average rating", f"{base['avg_rating']:.2f}")
    c3.metric("1-2 star reviews", f"{base['pct_low']:.1f}%")
    c4.metric("Apps studied", "10" if window == "all" else str(rates[rates['window'] == window]['app_name'].nunique()))

    st.subheader("What to do first")
    top = default_scored.head(5).merge(stab_default[["action_id", "pct_in_top5"]], on="action_id")
    for _, r in top.iterrows():
        st.markdown(f"**{r['action']}**  \n{r['tier'].capitalize()} evidence, {int(r['n_reviews']):,} mentions, "
                    f"{r['avg_rating']:.1f} stars when mentioned. In the top 5 in {r['pct_in_top5']:.0f}% of random weightings.")
    st.info("The model measures how many stars an app loses by failing at a topic. It cannot see whether a topic is a chance to stand out. "
            "Journaling is the biggest opening (journal-style apps talk about it about 9 times as much as other segments), "
            "but it rests on two apps, so treat it as a strategic bet to test, not a measured requirement.")
    st.subheader("Caveats")
    st.markdown("- iOS only, US and Canada only, English reviews only. Reviewers lean toward strong opinions.\n"
                "- The newest 500 reviews per app and country, so time windows differ by app.\n"
                "- The labels used to test the keyword rules were made by AI, not a person.\n"
                "- The research has no data on Vietnamese-speaking users, although the app is bilingual.")

# ---------------------------------------------------------------- Feature gap matrix
with tabs[1]:
    st.subheader("Which topics do reviewers of each app talk about?")
    left, right = st.columns([2, 1])
    segs = left.multiselect("Segments", SEGMENT_ORDER, default=SEGMENT_ORDER)
    only_reliable = right.checkbox("Reliable topics only", value=False)
    d = rates[(rates["window"] == window) & rates["segment"].isin(segs)].copy()
    d["tier"] = d["theme"].map(tier_of)
    if only_reliable:
        d = d[d["tier"] == "reliable"]
    d["topic"] = d["theme"].map(theme_label) + d["tier"].map({"directional": "*", "reliable": ""})
    topic_order = [theme_label[t] + ("*" if tier_of[t] == "directional" else "") for t in theme_order if t in set(d["theme"])]
    app_order = (d.assign(seg_rank=d["segment"].map({s: i for i, s in enumerate(SEGMENT_ORDER)}))
                 .sort_values(["seg_rank", "app_name"])["app_name"].drop_duplicates().tolist())
    if d.empty:
        st.warning("No apps in this selection for the chosen window.")
    else:
        chart_base = alt.Chart(d).encode(
            x=alt.X("topic:N", sort=topic_order, axis=alt.Axis(labelAngle=-40, title=None)),
            y=alt.Y("app_name:N", sort=app_order, title=None))
        heat = chart_base.mark_rect().encode(
            color=alt.Color("rate_pct:Q", scale=alt.Scale(scheme="blues", domainMin=0), title="% of reviews"),
            tooltip=["app_name", "segment", "topic", alt.Tooltip("rate_pct:Q", format=".1f", title="% of reviews"),
                     alt.Tooltip("reviews_in_app:Q", title="reviews in app")])
        txt = chart_base.mark_text(fontSize=10).encode(
            text=alt.Text("rate_pct:Q", format=".0f"),
            color=alt.condition(alt.datum.rate_pct > d["rate_pct"].max() * 0.55, alt.value("white"), alt.value("black")))
        st.altair_chart((heat + txt).properties(height=max(200, 34 * len(app_order))), width="stretch")
        st.caption("Each cell is the share of that app's usable reviews that mention the topic. * = directional topic.")

    st.subheader("How much each topic hurts or helps")
    imp = impact[impact["window"] == window][["label", "tier", "reviews", "pct_of_reviews", "avg_rating", "pct_low"]]
    imp = imp.rename(columns={"label": "Topic", "tier": "Rule", "reviews": "Reviews", "pct_of_reviews": "% of reviews",
                              "avg_rating": "Average stars", "pct_low": "% 1-2 star"})
    st.dataframe(imp.sort_values("% 1-2 star", ascending=False), hide_index=True, width="stretch",
                 column_config={"% of reviews": st.column_config.NumberColumn(format="%.1f"),
                                "Average stars": st.column_config.NumberColumn(format="%.2f"),
                                "% 1-2 star": st.column_config.NumberColumn(format="%.1f")})
    scatter = alt.Chart(impact[impact["window"] == window]).mark_circle(size=110).encode(
        x=alt.X("pct_of_reviews:Q", title="% of reviews mentioning the topic"),
        y=alt.Y("avg_rating:Q", title="Average stars when mentioned", scale=alt.Scale(zero=False)),
        color=alt.Color("tier:N", scale=TIER_COLORS, title="Rule"), tooltip=["label", "reviews", "avg_rating", "pct_low"])
    labels = alt.Chart(impact[impact["window"] == window]).mark_text(align="left", dx=8, fontSize=10).encode(
        x="pct_of_reviews:Q", y="avg_rating:Q", text="label:N")
    st.altair_chart((scatter + labels).properties(height=380), width="stretch")

# ---------------------------------------------------------------- Prioritization
with tabs[2]:
    st.subheader("Change the assumptions and watch the ranking move")
    st.markdown("Score = Reach + Impact + Confidence - Effort, each on a 0 to 1 scale. The weights and the effort estimates are "
                "assumptions, so change them. Two actions with no clean review topic are left out.")
    wc = st.columns(4)
    w = {"reach": wc[0].slider("Reach", 0, 100, 25, help="Share of reviews that mention the topic"),
         "impact": wc[1].slider("Impact", 0, 100, 35, help="Stars at stake: distance from the average rating"),
         "confidence": wc[2].slider("Confidence", 0, 100, 25, help="How reliable the evidence is"),
         "effort": wc[3].slider("Effort penalty", 0, 100, 15, help="Cost to build")}
    if sum(w.values()) == 0:
        st.warning("All weights are zero, so the default weights are used instead.")
        w = prioritize.DEFAULT_WEIGHTS
    scored_ids = evidence[evidence["window"] == window]["action_id"].tolist()
    effort_df = register[register["action_id"].isin(scored_ids)][["action_id", "action", "effort_default"]].rename(
        columns={"effort_default": "effort"})
    with st.expander("Effort estimates (1 = small, 2 = medium, 3 = large). These are estimates, edit them."):
        edited = st.data_editor(effort_df, hide_index=True, disabled=["action_id", "action"], key="efforts",
                                column_config={"effort": st.column_config.NumberColumn(min_value=1, max_value=3, step=1)})
    efforts = dict(zip(edited["action_id"], edited["effort"]))
    ev = evidence[evidence["window"] == window]
    scored = prioritize.score_actions(ev, w, efforts).merge(register[["action_id", "action", "priority", "v1_status"]], on="action_id")
    stab = stability(window, tuple(sorted(efforts.items()))).rename(columns={"median_rank": "median_rank_random"})
    scored = scored.merge(stab[["action_id", "pct_in_top3", "pct_in_top5", "best_rank", "worst_rank", "median_rank_random"]], on="action_id")

    bars = alt.Chart(scored).mark_bar().encode(
        y=alt.Y("label:N", sort=alt.EncodingSortField("score", order="descending"), title=None),
        x=alt.X("score:Q", title="Score"), color=alt.Color("tier:N", scale=TIER_COLORS, title="Evidence"),
        tooltip=["action", "rank", alt.Tooltip("score:Q", format=".2f"), "n_reviews", "tier"]
    ).transform_calculate(label="datum.action_id + '  ' + slice(datum.action, 0, 48)")
    st.altair_chart(bars.properties(height=380), width="stretch")
    st.dataframe(scored[["rank", "action_id", "action", "priority", "score", "reach", "impact", "confidence", "effort_used", "tier", "n_reviews", "v1_status"]],
                 hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.2f") for c in ["score", "reach", "impact", "confidence"]})

    st.subheader("How stable is each rank?")
    st.markdown("Redraws the four weights at random 3,000 times (your sliders do not change this) and shows where each action lands. "
                "A short bar near the top is a robust priority.")
    rng = alt.Chart(scored).encode(y=alt.Y("label:N", sort=alt.EncodingSortField("median_rank_random", order="ascending"), title=None)).transform_calculate(
        label="datum.action_id + '  ' + slice(datum.action, 0, 48)")
    st.altair_chart((rng.mark_rule(size=6, color="#9aa5b1").encode(x=alt.X("best_rank:Q", title="Rank (1 = best; bar = 10th to 90th percentile, dot = median)", scale=alt.Scale(reverse=True)), x2="worst_rank:Q")
                     + rng.mark_circle(size=80, color="#2a6f97").encode(x=alt.X("median_rank_random:Q", scale=alt.Scale(reverse=True)))).properties(height=380),
                    width="stretch")

    st.subheader("A second lens: differentiation")
    st.markdown("The score cannot see whether a topic is a chance to stand out. This compares how much the journal-style apps "
                "(Direct) talk about a topic with the other two segments. Above the dashed line they over-index 2 times.")
    lens = scored.copy()
    pts = alt.Chart(lens).mark_circle(size=130).encode(
        x=alt.X("score:Q", title="Score (stars at stake)"),
        y=alt.Y("direct_over_index:Q", title="Journal-app share / other-segment share (log)", scale=alt.Scale(type="log")),
        color=alt.Color("tier:N", scale=TIER_COLORS, title="Evidence"), tooltip=["action", alt.Tooltip("direct_over_index:Q", format=".1f"), "tier"])
    lbl = alt.Chart(lens).mark_text(align="left", dx=9, fontSize=11).encode(x="score:Q", y="direct_over_index:Q", text="action_id:N")
    line = alt.Chart(pd.DataFrame({"y": [2]})).mark_rule(strokeDash=[4, 4], color="grey").encode(y="y:Q")
    st.altair_chart((pts + lbl + line).properties(height=380), width="stretch")

# ---------------------------------------------------------------- Evidence
with tabs[3]:
    st.subheader("Check the evidence behind an action")
    reg = register.copy()
    reg["label"] = reg["action_id"] + "  " + reg["action"]
    pick = st.selectbox("Action", reg["label"])
    a = reg[reg["label"] == pick].iloc[0]
    st.markdown(f"**Priority {a['priority']}** | Evidence strength: **{a['strength']}** | Effort estimate: {a['effort_default']} ({a['effort_note']})")
    ev_row = evidence[(evidence["window"] == window) & (evidence["action_id"] == a["action_id"])]
    if ev_row.empty:
        st.markdown("No clean review topic, so this action is not scored. See the quotes and the notes below.")
    else:
        r = ev_row.iloc[0]
        m = st.columns(5)
        m[0].metric("Mentions", f"{int(r['n_reviews']):,}")
        m[1].metric("Share of reviews", f"{r['reach_pct']:.1f}%")
        m[2].metric("Average stars", f"{r['avg_rating']:.2f}", f"{r['avg_rating'] - r['baseline_rating']:+.2f} vs all", delta_color="off")
        m[3].metric("1-2 star", f"{r['pct_low']:.0f}%")
        m[4].metric("Journal-app index", f"{r['direct_over_index']:.1f}x")
        st.caption(f"Topic rule(s): {a['topics']} ({r['tier']}). Journal-app index = share in the Direct apps divided by the share in the other segments.")
    q = quotes[quotes["action_id"] == a["action_id"]]
    st.markdown("**What reviewers said**" if not q.empty else "*No quotes selected for this action.*")
    for _, row in q.iterrows():
        st.markdown(f"> “{row['quote']}”  \n> {row['app']}, {int(row['stars'])} star{'s' if row['stars'] != 1 else ''}")
    st.markdown(f"**In Wombloom v1.0:** {a['v1_status']}. {a['v1_evidence']}")
    st.markdown(f"**How I would measure it:** {a['measurement_idea']}")

# ---------------------------------------------------------------- Plan vs reality
with tabs[4]:
    st.subheader("Evidence-led plan against what Wombloom v1.0 contains")
    st.markdown("The feature plan came from the owner's own needs as an expectant parent, before this research. This is a retrospective "
                "check of that plan against the evidence, not a claim that the research shaped the build.")
    statuses = st.multiselect("Show", ["Shipped", "Partial", "Missing", "Not applicable yet"], default=["Shipped", "Partial", "Missing", "Not applicable yet"])
    shown = register[register["v1_status"].isin(statuses)]
    counts = register.groupby(["priority", "v1_status"]).size().reset_index(name="actions")
    st.altair_chart(alt.Chart(counts).mark_bar().encode(
        y=alt.Y("priority:N", sort=["P0", "P1", "P2", "Avoid"], title=None), x=alt.X("actions:Q", title="Actions"),
        color=alt.Color("v1_status:N", scale=STATUS_COLORS, title="v1.0")).properties(height=200), width="stretch")
    st.dataframe(shown[["action_id", "priority", "action", "strength", "v1_status", "v1_evidence"]].rename(
        columns={"v1_status": "v1.0", "v1_evidence": "What the files show"}), hide_index=True, width="stretch")
    st.subheader("Features in v1.0 that the research did not cover")
    p = probe[probe["window"] == window].sort_values("pct_of_reviews", ascending=False)
    st.dataframe(p[["feature", "reviews", "pct_of_reviews", "avg_rating", "pct_low"]].rename(
        columns={"feature": "Feature", "reviews": "Reviews mentioning", "pct_of_reviews": "% of reviews", "avg_rating": "Average stars",
                 "pct_low": "% 1-2 star"}), hide_index=True, width="stretch",
        column_config={"% of reviews": st.column_config.NumberColumn(format="%.1f"), "Average stars": st.column_config.NumberColumn(format="%.1f"),
                       "% 1-2 star": st.column_config.NumberColumn(format="%.0f")})
    st.caption("Rough keyword counts in reviews of other apps, not validated rules.")

# ---------------------------------------------------------------- Method
with tabs[5]:
    st.subheader("How the topics were found, and how far to trust them")
    tp, fp, fn = (accuracy[c].sum() for c in ["true_pos_test", "false_pos_test", "false_neg_test"])
    rel = accuracy[accuracy["tier"] == "reliable"]
    c = st.columns(3)
    c[0].metric("Reliable topics", f"{len(rel)} of {len(accuracy)}")
    c[1].metric("Average test F1 (reliable)", f"{rel['f1_test'].mean():.2f}")
    c[2].metric("Pooled test precision / recall", f"{tp / (tp + fp):.2f} / {tp / (tp + fn):.2f}")
    st.markdown("Topics are found with keyword rules, tuned on 100 hand-labeled reviews and scored once on 50 held-out ones. "
                "A topic is reliable if the test set has at least 3 real examples and an F1 of at least 0.75.")
    st.dataframe(accuracy[["label", "tier", "hand_labeled_dev", "f1_dev", "hand_labeled_test", "precision_test", "recall_test", "f1_test"]]
                 .rename(columns={"label": "Topic", "tier": "Rule", "hand_labeled_dev": "Labeled (tuning)", "f1_dev": "F1 (tuning)",
                                  "hand_labeled_test": "Labeled (test)", "precision_test": "Precision (test)", "recall_test": "Recall (test)",
                                  "f1_test": "F1 (test)"}),
                 hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(format="%.2f") for k in ["F1 (tuning)", "Precision (test)", "Recall (test)", "F1 (test)"]})
    st.subheader("How AI was used")
    st.markdown("- **The analyst owns the question, the method and every decision.** The research plan (scope, competitor selection, data rules and "
                "review checkpoints) was written by the analyst, who also chose what to build and what to trust.\n"
                "- **AI is an accelerator.** It saved time writing and running the scripts and assembling first drafts, and did a first-pass labeling "
                "of 150 reviews used only to test the rules.\n"
                "- **Verification:** a held-out test, a coverage check at each checkpoint and a stress test of the ranking caught a silent data gap, "
                "a weak sentiment tool and over-optimistic accuracy. See the notebook, section 20.\n"
                "- **Limit:** the 150 validation labels were made by the AI, not by a person, so accuracy means agreement with the AI's own labels.")
    st.subheader("Limits")
    st.markdown("- iOS only; US and Canada; English; newest 500 reviews per app and country.\n"
                "- The journal-app evidence rests mostly on one app (Qeepsake).\n"
                "- Weights and effort scores are assumptions. The rank-stability chart shows which conclusions survive them.\n"
                "- Reviews describe other apps' users, not Wombloom's, and cannot prove demand for a new feature.")
