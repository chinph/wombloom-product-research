"""Loading and charts for the case-study notebook.

Everything reads from data/aggregates/ and data/registers/, so the case study runs on a fresh clone without the
review database. Each chart answers one question; its bold headline states the finding, and the grey line under it
says what is plotted.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import prioritize

SEGMENTS = ["Direct", "Category leader", "Adjacent"]
SEGMENT_NAMES = {"Direct": "Journal apps", "Category leader": "Pregnancy leaders", "Adjacent": "Baby trackers"}
SEGMENT_COLORS = {"Direct": "#2a9d8f", "Category leader": "#8d6cab", "Adjacent": "#e9a23b"}
TIER_COLORS = {"reliable": "#2a6f97", "directional": "#c0504d"}
STATUS_COLORS = {"Shipped": "#7a9e7e", "Partial": "#e9c46a", "Missing": "#c0504d", "Not applicable yet": "#c9ced6"}
COUNTRY_COLORS = {"us": "#2a6f97", "ca": "#e9a23b"}
GREY, DARK = "#8a94a0", "#2b2f36"
SHORT = {"A1": "No ads", "A2": "Transparent pricing", "A3": "Never lose entries", "A4": "Careful updates",
         "B1": "Pregnancy-week journaling", "B2": "Partner and family sharing", "B3": "No account needed",
         "B4": "Inclusive by default", "B5": "Honest keepsakes", "C1": "iOS widgets and Watch", "C2": "Support and refunds",
         "C3": "Editable due date", "D1": "No forced AI", "D2": "No data selling", "D3": "Not an article app"}
FIGURES = None


def load(root):
    """All the data the case study uses, as a dict of DataFrames."""
    global FIGURES
    root = Path(root)
    FIGURES = root / "docs" / "figures"
    data = {p.stem: pd.read_csv(p) for p in (root / "data" / "aggregates").glob("*.csv")}
    for name in ["actions_register", "evidence_quotes"]:
        data[name] = pd.read_csv(root / "data" / "registers" / f"{name}.csv")
    data["promo_log"] = pd.read_csv(root / "data" / "measurement" / "promo_post_log.csv")
    return data


def style():
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 160, "font.size": 10, "axes.titlesize": 10, "axes.labelsize": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#c9ced6", "axes.labelcolor": DARK,
        "xtick.color": DARK, "ytick.color": DARK, "legend.frameon": False, "axes.titlelocation": "left",
    })
    pd.set_option("display.max_colwidth", 90)


def show(df, precision=1):
    """A table without the index column, numbers rounded, for clean rendering on GitHub."""
    return df.style.hide(axis="index").format(precision=precision, thousands=",")


def _finish(fig, headline, subtitle, name):
    h = fig.get_figheight()  # place the titles a fixed distance (in inches) from the top, whatever the figure height
    fig.text(0.01, 1 - 0.12 / h, headline, ha="left", va="top", fontsize=13, fontweight="bold", color=DARK)
    fig.text(0.01, 1 - 0.42 / h, subtitle, ha="left", va="top", fontsize=10, color=GREY)
    fig.tight_layout(rect=[0, 0, 1, 1 - 0.7 / h])
    if FIGURES is not None:
        FIGURES.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGURES / f"{name}.png", bbox_inches="tight", facecolor="white")
    plt.show()


def _seg(s):
    return s.map(SEGMENT_NAMES)


# ---------------------------------------------------------------- 1. Choosing competitors
FUNNEL_STEPS = ["Found by 20 keyword searches (US + CA)", "Mentions pregnancy or babies", "Health, medical, lifestyle, education or social",
                "Not a period or fertility tracker", "At least 1,000 ratings", "Updated in the last 12 months", "Not a duplicate or clone"]


def funnel(d):
    f = d["discovery_funnel"].copy()
    f["label"] = FUNNEL_STEPS
    f = pd.concat([f, pd.DataFrame({"label": ["Shortlisted by hand, balanced across 3 groups"], "remaining": [10], "removed": [np.nan]})])
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(f))
    colors = [GREY] * (len(f) - 1) + ["#2a6f97"]
    ax.barh(y, f["remaining"], color=colors, height=0.65)
    for yi, (rem, cut) in enumerate(zip(f["remaining"], f["removed"])):
        note = f"{rem:,}" + (f"   (-{int(cut):,})" if pd.notna(cut) and cut > 0 else "")
        ax.text(rem + 15, yi, note, va="center", fontsize=9, color=DARK)
    ax.set_yticks(y, f["label"])
    ax.invert_yaxis()
    ax.set_xlim(0, 1750)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    _finish(fig, "1,464 apps in, 10 out: the 1,000-rating bar did most of the cutting",
            "Apps remaining after each filter, in the order applied", "01_discovery_funnel")


def shortlist_table(d):
    s = d["shortlist"].copy()
    s["group"] = _seg(s["segment"])
    s["order"] = s["segment"].map({k: i for i, k in enumerate(SEGMENTS)})
    s = s.sort_values(["order", "store_rating_count"], ascending=[True, False])
    out = s[["group", "app_name", "developer", "store_rating_count", "reviews_collected", "usable"]].rename(columns={
        "group": "Group", "app_name": "App", "developer": "Developer", "store_rating_count": "Store ratings",
        "reviews_collected": "Reviews collected", "usable": "Usable for text analysis"})
    out["Store ratings"] = out["Store ratings"].map("{:,.0f}".format)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- 2. The data and how far to trust it
def coverage(d):
    c = d["coverage"].copy()
    c["first_date"], c["last_date"] = pd.to_datetime(c["first_date"]), pd.to_datetime(c["last_date"])
    c["order"] = c["segment"].map({k: i for i, k in enumerate(SEGMENTS)})
    apps = c.sort_values(["order", "app_name"])["app_name"].drop_duplicates().tolist()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1, 1.3]}, sharey=True)
    y = np.arange(len(apps))
    for i, (ctry, off) in enumerate([("us", -0.18), ("ca", 0.18)]):
        sub = c[c["country"] == ctry].set_index("app_name").reindex(apps)
        a1.barh(y + off, sub["reviews"], height=0.34, color=COUNTRY_COLORS[ctry], label=ctry.upper())
        a2.hlines(y + off, sub["first_date"], sub["last_date"], color=COUNTRY_COLORS[ctry], linewidth=5)
    a1.axvline(500, color=GREY, linestyle="--", linewidth=1)
    a1.text(500, -0.6, "feed limit (500)", color=GREY, fontsize=8, ha="right", va="bottom")
    a1.set_yticks(y, apps)
    a1.invert_yaxis()
    a1.set_xlabel("Reviews collected")
    a1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
    a2.set_xlabel("Period the collected reviews cover")
    _finish(fig, "Same 500-review cap, very different time spans",
            "Left: reviews per app and country. Right: from the oldest to the newest review collected", "02_coverage")


def recency(d):
    y = d["reviews_by_year"].pivot(index="year", columns="segment", values="reviews").fillna(0)[SEGMENTS]
    fig, ax = plt.subplots(figsize=(10, 4))
    bottom = np.zeros(len(y))
    for seg in SEGMENTS:
        ax.bar(y.index.astype(str), y[seg], bottom=bottom, color=SEGMENT_COLORS[seg], label=SEGMENT_NAMES[seg], width=0.7)
        bottom += y[seg].to_numpy()
    ax.text(len(y) - 1, bottom[-1] + 30, "Jan-Oct", ha="center", fontsize=8, color=GREY)
    ax.set_ylabel("Reviews")
    ax.legend(loc="upper left")
    _finish(fig, "The sample leans recent: 2026, a partial year, has the most reviews",
            "All 7,955 collected reviews, by the year they were written", "03_recency")


def quality_table(d):
    q = d["text_quality_by_app"].copy()
    q["Group"] = _seg(q["segment"])
    q["% usable"] = (q["usable"] / q["reviews"] * 100).round(1)
    q["order"] = q["segment"].map({k: i for i, k in enumerate(SEGMENTS)})
    q = q.sort_values(["order", "% usable"])
    return q[["Group", "app_name", "reviews", "usable", "english_but_short", "non_english_or_undetermined", "% usable"]].rename(
        columns={"app_name": "App", "reviews": "Reviews", "usable": "Usable", "english_but_short": "Under 5 words",
                 "non_english_or_undetermined": "Not English or undetermined"}).reset_index(drop=True)


# ---------------------------------------------------------------- 3. Measuring what reviews are about
def vader_vs_stars(d):
    a = d["vader_agreement"].pivot(index="star_label", columns="vader_label", values="pct").loc[["negative", "neutral", "positive"]]
    groups = {"negative": "1-2 stars", "neutral": "3 stars", "positive": "4-5 stars"}
    colors = {"negative": "#c0504d", "neutral": "#c9ced6", "positive": "#7a9e7e"}
    fig, ax = plt.subplots(figsize=(9, 3.6))
    left = np.zeros(3)
    for lab in ["negative", "neutral", "positive"]:
        ax.barh([groups[i] for i in a.index], a[lab], left=left, color=colors[lab], label=f"VADER says {lab}", height=0.6)
        for yi, (l, v) in enumerate(zip(left, a[lab])):
            if v > 6:
                ax.text(l + v / 2, yi, f"{v:.0f}%", ha="center", va="center", fontsize=9, color="white" if lab != "neutral" else DARK)
        left += a[lab].to_numpy()
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of reviews in the star group")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.25))
    _finish(fig, "VADER recognises happy reviews but misses most complaints",
            "How a standard sentiment tool labels reviews, by the star rating the reviewer gave", "04_vader_vs_stars")


def rule_accuracy(d):
    a = d["theme_accuracy"].copy().sort_values(["f1_test", "f1_dev"], na_position="first")
    fig, ax = plt.subplots(figsize=(9, 6.2))
    y = np.arange(len(a))
    for yi, (_, r) in enumerate(a.iterrows()):
        if pd.notna(r["f1_test"]):
            ax.plot([r["f1_dev"], r["f1_test"]], [yi, yi], color="#d5dae0", linewidth=2, zorder=1)
    ax.scatter(a["f1_dev"], y, facecolors="white", edgecolors=GREY, s=45, zorder=2, label="Tuning set (100 reviews)")
    ax.scatter(a["f1_test"], y, c=a["tier"].map(TIER_COLORS), s=55, zorder=3, label="Held-out test (50 reviews)")
    for yi, (_, r) in enumerate(a.iterrows()):
        if pd.isna(r["f1_test"]):
            ax.text(1.02, yi, "no test examples", va="center", fontsize=8, color=GREY)
    ax.axvline(0.75, color=GREY, linestyle="--", linewidth=1)
    ax.set_yticks(y, [f"{l} ({int(n)})" for l, n in zip(a["label"], a["hand_labeled_test"])])
    ax.set_xlim(0, 1.25)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_xlabel("F1 score (dashed line = 0.75 bar). Blue = reliable, red = directional. Brackets: real examples in the test set")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
    _finish(fig, "7 of 19 topic rules held up on reviews they were not tuned on",
            "Keyword-rule accuracy against hand labels, tuning set vs held-out test set", "05_rule_accuracy")


# ---------------------------------------------------------------- 4. What reviewers complain about and value
def topic_impact(d, window="all"):
    imp = d["theme_impact"][d["theme_impact"]["window"] == window].copy()
    base = d["baseline"].set_index("window").loc[window, "avg_rating"]
    imp["gap"] = imp["avg_rating"] - base
    imp = imp.sort_values("gap")
    fig, ax = plt.subplots(figsize=(10, 6.2))
    y = np.arange(len(imp))
    ax.barh(y, imp["gap"], color=imp["tier"].map(TIER_COLORS), height=0.65)
    for yi, (g, n) in enumerate(zip(imp["gap"], imp["reviews"])):
        ax.text(g + (0.03 if g >= 0 else -0.03), yi, f"n={n:,}", va="center", ha="left" if g >= 0 else "right", fontsize=8, color=GREY)
    ax.axvline(0, color=DARK, linewidth=0.8)
    ax.set_yticks(y, imp["label"])
    ax.set_xlim(-2.3, 0.7)
    ax.set_xlabel(f"Average stars when the topic is mentioned, minus the {base:.2f} average of all reviews")
    _finish(fig, "Ads, updates and bugs cost the most stars; journaling and articles earn a little",
            "Stars gained or lost when a review mentions a topic. Blue = reliable rule, red = directional (a lead, not a measurement)",
            "06_topic_impact")


def segment_heatmap(d, window="all"):
    r = d["theme_app_rates"][d["theme_app_rates"]["window"] == window]
    seg = r.groupby(["theme", "segment"])["rate_pct"].mean().unstack()[SEGMENTS]  # each app counts once
    imp = d["theme_impact"][d["theme_impact"]["window"] == "all"].set_index("theme")
    order = imp.sort_values("pct_low", ascending=False).index
    seg = seg.loc[order]
    scaled = seg.div(seg.max(axis=1), axis=0)  # colour shows which segment talks about the topic most
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    ax.imshow(scaled.to_numpy(), cmap="Blues", aspect="auto", vmin=0, vmax=1.15)
    for i in range(seg.shape[0]):
        for j in range(seg.shape[1]):
            v = seg.iat[i, j]
            ax.text(j, i, f"{v:.1f}%", ha="center", va="center", fontsize=9, color="white" if scaled.iat[i, j] > 0.7 else DARK)
    ax.set_xticks(range(3), [SEGMENT_NAMES[s] for s in SEGMENTS])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(order)), [imp.loc[t, "label"] + ("*" if imp.loc[t, "tier"] == "directional" else "") for t in order])
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    _finish(fig, "Journal apps own memories; baby trackers carry the ads and pricing complaints",
            "% of each group's reviews mentioning a topic (average of its apps). Darkest cell = the group that mentions it most. * = directional rule",
            "07_segment_heatmap")


# ---------------------------------------------------------------- 5. From findings to priorities
def scored(d, window="all", weights=None):
    ev = d["action_evidence"][d["action_evidence"]["window"] == window]
    s = prioritize.score_actions(ev, weights)
    stab = prioritize.rank_stability(ev)
    reg = d["actions_register"][["action_id", "priority", "strength", "v1_status", "narrative_order"]]
    return s.merge(stab, on="action_id").merge(reg, on="action_id")


def priority_stability(d):
    s = scored(d).sort_values("median_rank")
    fig, ax = plt.subplots(figsize=(10, 5.2))
    y = np.arange(len(s))
    ax.hlines(y, s["best_rank"], s["worst_rank"], color="#d5dae0", linewidth=7)
    ax.scatter(s["rank"], y, c=s["tier"].map(TIER_COLORS), s=60, zorder=3)
    for yi, p in enumerate(s["pct_in_top3"]):
        ax.text(14.2, yi, f"{p:.0f}%", va="center", fontsize=9, color=DARK)
    ax.text(14.2, -1.1, "in top 3", fontsize=8, color=GREY)
    ax.set_yticks(y, [f"{SHORT[a]} ({a})" for a in s["action_id"]])
    ax.invert_yaxis()
    ax.set_xlim(0.5, 15.5)
    ax.set_xticks(range(1, 14))
    ax.set_xlabel("Rank (1 = do first). Dot = rank with my default weights; bar = 10th-90th percentile over 5,000 random weightings")
    _finish(fig, "Pricing, updates and ads stay on top whatever the weights",
            "Priority score per action, stress-tested by redrawing the weights at random. Blue = reliable evidence, red = directional",
            "08_priority_stability")


def two_lenses(d):
    s = scored(d)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(s["score"], s["direct_over_index"], s=90, c=s["tier"].map(TIER_COLORS), zorder=3)
    nudge = {"B4": (7, 8), "B2": (7, -13), "A3": (-8, 9), "B3": (7, -13)}  # keep neighbouring labels apart
    for _, r in s.iterrows():
        dx, dy = nudge.get(r["action_id"], (7, 4))
        ax.annotate(SHORT[r["action_id"]], (r["score"], r["direct_over_index"]), textcoords="offset points",
                    xytext=(dx, dy), ha="right" if dx < 0 else "left", fontsize=9)
    ax.set_yscale("log")
    ticks = [0.25, 0.5, 1, 2, 4, 8]
    ax.set_yticks(ticks, [f"{t:g}x" for t in ticks])
    ax.minorticks_off()
    ax.axhline(2, color=GREY, linestyle="--", linewidth=1)
    ax.axvline(s["score"].median(), color=GREY, linestyle=":", linewidth=1)
    ax.text(0.01, 0.97, "Strategic bets: low stars at stake,\njournal apps talk about it a lot", transform=ax.transAxes, va="top", fontsize=9, color=GREY)
    ax.text(0.99, 0.04, "Hygiene: costly to get wrong,\nevery segment complains", transform=ax.transAxes, ha="right", fontsize=9, color=GREY)
    ax.set_xlabel("Priority score (stars at stake, reach and confidence, minus effort)")
    ax.set_ylabel("Journal apps' share / other groups' share (log)")
    _finish(fig, "The score misses differentiation: journaling ranks low but is the clearest opening",
            "Each action on two lenses. Above the dashed line, journal apps mention the topic at least twice as often as the others",
            "09_two_lenses")


def actions_table(d):
    s = scored(d)[["action_id", "rank", "pct_in_top3", "direct_over_index"]]
    reg = d["actions_register"].merge(s, on="action_id", how="left")
    reg["Action"] = reg["action_id"].map(SHORT)
    reg["Model rank"] = reg["rank"].map(lambda v: "" if pd.isna(v) else f"{int(v)}")
    reg["Journal-app index"] = reg["direct_over_index"].map(lambda v: "" if pd.isna(v) else f"{v:.1f}x")
    return reg[["action_id", "Action", "priority", "strength", "Model rank", "Journal-app index", "v1_status"]].rename(columns={
        "action_id": "ID", "priority": "Priority", "strength": "Evidence", "v1_status": "Wombloom v1.0"})


# ---------------------------------------------------------------- 6. Checking my own plan
def plan_vs_reality(d):
    reg = d["actions_register"]
    order = ["P0", "P1", "P2", "Avoid"]
    t = pd.crosstab(reg["priority"], reg["v1_status"]).reindex(index=order, columns=list(STATUS_COLORS), fill_value=0)
    fig, ax = plt.subplots(figsize=(10, 3.3))
    left = np.zeros(len(t))
    for status in t.columns:
        ax.barh(t.index, t[status], left=left, color=STATUS_COLORS[status], label=status, height=0.6)
        for yi, (l, v) in enumerate(zip(left, t[status])):
            if v:
                ax.text(l + v / 2, yi, str(v), ha="center", va="center", fontsize=9, color=DARK)
        left += t[status].to_numpy()
    ax.invert_yaxis()
    ax.set_xlabel("Number of actions")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.3))
    _finish(fig, "v1.0 already covers trust and privacy; the gap that matters is data safety",
            "The 15 actions from the research against what Wombloom v1.0 contains, by priority", "10_plan_vs_reality")


def feature_probe_table(d):
    p = d["feature_probe"][d["feature_probe"]["window"] == "all"].sort_values("pct_of_reviews", ascending=False)
    return p[["feature", "reviews", "pct_of_reviews", "avg_rating", "pct_low"]].round(1).rename(columns={
        "feature": "Feature in v1.0", "reviews": "Reviews mentioning", "pct_of_reviews": "% of reviews",
        "avg_rating": "Avg stars", "pct_low": "% 1-2 star"}).reset_index(drop=True)


def margin_of_error_table():
    n = np.array([30, 50, 100, 200, 400])
    return pd.DataFrame({"Sample size": n, "95% margin of error (+/- points)": (1.96 * np.sqrt(0.25 / n) * 100).round(1)})
