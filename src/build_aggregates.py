"""Build the aggregated files that the case-study notebook and the dashboard read.

Everything here is a count, a share or an average, plus the hand-picked quotes in data/registers/. No review
text or reviewer data is written, so data/aggregates/ can be published and the case study runs without the
local database.

Reads (local): data/wombloom.db, data/clean/, docs/app_selection_log.md
Writes:        data/aggregates/*.csv and data/registers/theme_label_sample_keys.csv
Run from the project root:  python src/build_aggregates.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import themes  # noqa: E402

DB = ROOT / "data" / "wombloom.db"
CLEAN = ROOT / "data" / "clean"
REGISTERS = ROOT / "data" / "registers"
OUT = ROOT / "data" / "aggregates"

RECENT_MONTHS = 24
MIN_RECENT = 30  # apps with fewer reviews in the recent window are left out of that window

# Features in Wombloom v1.0 that the theme list had no topic for. Simple keyword probes, not validated rules.
FEATURE_PROBES = {
    "Shopping list, registry or budget": r"shopping list|wish ?list|registry|budget",
    "Personalization (stickers, themes, cute design)": r"sticker|customi[sz]|personali[sz]|aesthetic|\bcute\b|\bthemes?\b|washi",
    "Appointments and calendar": r"appointment|calendar",
    "Growth or weight charts": r"growth chart|weight chart|percentile|growth (?:tracking|tracker)",
    "Reminders and notifications": r"reminders?|notifications?",
    "Ultrasound or scan logging": r"ultrasound|sonogram",
    "Other languages (including Vietnamese)": r"\blanguages?\b|translat|vietnam",
}


def read_reviews():
    with sqlite3.connect(DB) as con:
        reviews = pd.read_sql("select * from reviews", con)
        apps = pd.read_sql("select * from apps", con)
    reviews["review_date"] = pd.to_datetime(reviews["review_date"], utc=True)
    reviews["text_full"] = (reviews["title"].fillna("") + ". " + reviews["text"].fillna("")).str.strip()
    return reviews, apps


def windows(usable):
    cutoff = usable["review_date"].max() - pd.DateOffset(months=RECENT_MONTHS)
    recent = usable[usable["review_date"] >= cutoff].groupby("app_name").filter(lambda g: len(g) >= MIN_RECENT)
    return {"all": usable, "last_24m": recent}


def discovery_tables():
    """Funnel from the selection log, segment counts of the filtered candidates."""
    text = (ROOT / "docs" / "app_selection_log.md").read_text(encoding="utf-8")
    block = text.split("## 2. Filter funnel", 1)[1].split("\n## ", 1)[0]
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in block.splitlines() if line.startswith("|")]
    funnel = pd.DataFrame(rows[2:], columns=["step", "removed", "remaining"])
    funnel["removed"] = pd.to_numeric(funnel["removed"], errors="coerce")
    funnel["remaining"] = funnel["remaining"].astype(int)
    segments = (pd.read_csv(CLEAN / "app_candidates_filtered.csv")["segment"].value_counts()
                .rename_axis("segment").reset_index(name="apps"))
    return funnel, segments


def collection_tables(reviews, apps):
    coverage = pd.read_csv(CLEAN / "appstore_coverage.csv")
    usable_mask = (reviews["is_english"] == 1) & (reviews["is_short"] == 0)
    totals = reviews.groupby("app_id").agg(reviews_collected=("review_id", "size"))
    totals["usable"] = reviews[usable_mask].groupby("app_id").size()
    shortlist = apps.merge(totals, left_on="app_id", right_index=True)[
        ["app_id", "app_name", "segment", "developer", "category", "store_rating_count", "reviews_collected", "usable"]]

    by_year = (reviews.assign(year=reviews["review_date"].dt.year).groupby(["year", "segment"]).size()
               .reset_index(name="reviews"))
    quality = reviews.groupby(["segment", "app_name"]).apply(lambda g: pd.Series({
        "reviews": len(g),
        "usable": int(((g["is_english"] == 1) & (g["is_short"] == 0)).sum()),
        "english_but_short": int(((g["is_english"] == 1) & (g["is_short"] == 1)).sum()),
        "non_english_or_undetermined": int((g["is_english"] == 0).sum()),
    }), include_groups=False).reset_index()
    lang = reviews.groupby(["country", "language"]).size().reset_index(name="reviews")
    rating_mix = (reviews.groupby(["segment", "app_name", "rating"]).size()
                  .groupby(level=[0, 1]).transform(lambda s: s / s.sum() * 100).reset_index(name="pct"))
    return coverage, shortlist, by_year, quality, lang, rating_mix


def vader_tables(usable):
    analyzer = SentimentIntensityAnalyzer()
    score = usable["text_full"].map(lambda t: analyzer.polarity_scores(t)["compound"])
    vader = pd.cut(score, [-1.01, -0.05, 0.05, 1.01], labels=["negative", "neutral", "positive"])
    stars = pd.cut(usable["rating"], [0, 2, 3, 5], labels=["negative", "neutral", "positive"])
    agreement = (pd.crosstab(stars, vader, normalize="index") * 100).stack().reset_index(name="pct")
    agreement.columns = ["star_label", "vader_label", "pct"]
    by_star = score.groupby(usable["rating"]).agg(["mean", "median", "size"]).reset_index()
    return agreement, by_star


def theme_tables(usable, register):
    tiers = themes.reliability_tiers()
    label = {c: l for c, (l, _) in themes.THEMES.items()}
    order = list(themes.THEMES)
    rates, impact, baselines, actions, probes = [], [], [], [], []
    for window, d in windows(usable).items():
        d = d.reset_index(drop=True)
        t = pd.concat([d[["app_name", "segment", "rating", "text_full"]], themes.tag_reviews(d)], axis=1)
        base_rating, base_low = d["rating"].mean(), (d["rating"] <= 2).mean() * 100
        baselines.append({"window": window, "reviews": len(d), "apps": d["app_name"].nunique(),
                          "avg_rating": base_rating, "pct_low": base_low})

        sizes = t.groupby("app_name").size()
        app_segment = t.drop_duplicates("app_name").set_index("app_name")["segment"]
        per_app = t.groupby(["segment", "app_name"])[order].mean().mul(100).reset_index()
        long = per_app.melt(id_vars=["segment", "app_name"], var_name="theme", value_name="rate_pct")
        long["window"], long["reviews_in_app"] = window, long["app_name"].map(sizes)
        rates.append(long)

        for code in order:
            m = t[code] == 1
            impact.append({"window": window, "theme": code, "label": label[code], "tier": tiers[code],
                           "reviews": int(m.sum()), "pct_of_reviews": m.mean() * 100,
                           "avg_rating": t.loc[m, "rating"].mean(), "pct_low": (t.loc[m, "rating"] <= 2).mean() * 100})

        for _, a in register.dropna(subset=["topics"]).iterrows():
            codes = a["topics"].split("+")
            m = t[codes].max(axis=1) == 1
            app_share = m.groupby(t["app_name"]).mean()
            seg_share = app_share.groupby(app_segment).mean() * 100
            # Differentiation: how much more the journal-style (Direct) apps talk about it than the other segments do
            others = seg_share.reindex(["Category leader", "Adjacent"]).mean()
            actions.append({
                "window": window, "action_id": a["action_id"], "topics": a["topics"],
                "tier": "directional" if any(tiers[c] == "directional" for c in codes) else "reliable",  # weakest link
                "n_reviews": int(m.sum()), "reach_pct": app_share.mean() * 100,
                "avg_rating": t.loc[m, "rating"].mean(), "pct_low": (t.loc[m, "rating"] <= 2).mean() * 100,
                "baseline_rating": base_rating, "effort": a["effort_default"],
                "share_direct": seg_share.get("Direct"), "share_others": others,
                "direct_over_index": seg_share.get("Direct") / others if others else None,
            })

        for feature, pattern in FEATURE_PROBES.items():
            m = t["text_full"].str.contains(pattern, case=False, regex=True)
            probes.append({"window": window, "feature": feature, "reviews": int(m.sum()), "pct_of_reviews": m.mean() * 100,
                           "avg_rating": t.loc[m, "rating"].mean(), "pct_low": (t.loc[m, "rating"] <= 2).mean() * 100})

    dev, test = themes.evaluate("dev"), themes.evaluate("test")
    accuracy = dev.merge(test, on=["theme", "label"], suffixes=("_dev", "_test"))
    accuracy["tier"] = accuracy["theme"].map(tiers)
    return (pd.concat(rates), pd.DataFrame(impact), pd.DataFrame(actions), pd.DataFrame(baselines),
            pd.DataFrame(probes), accuracy)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reviews, apps = read_reviews()
    usable = reviews[(reviews["is_english"] == 1) & (reviews["is_short"] == 0)].reset_index(drop=True)
    register = pd.read_csv(REGISTERS / "actions_register.csv")

    funnel, segments = discovery_tables()
    coverage, shortlist, by_year, quality, lang, rating_mix = collection_tables(reviews, apps)
    agreement, by_star = vader_tables(usable)
    rates, impact, actions, baselines, probes, accuracy = theme_tables(usable, register)

    outputs = {
        "discovery_funnel": funnel, "discovery_segments": segments, "shortlist": shortlist, "coverage": coverage,
        "reviews_by_year": by_year, "text_quality_by_app": quality, "language_by_country": lang, "rating_mix": rating_mix,
        "vader_agreement": agreement, "vader_by_star": by_star, "theme_app_rates": rates, "theme_impact": impact,
        "action_evidence": actions, "baseline": baselines, "feature_probe": probes, "theme_accuracy": accuracy,
    }
    for name, df in outputs.items():
        df.to_csv(OUT / f"{name}.csv", index=False)

    # The labeled sample without its text: enough to find each review again by its store ID
    sample = pd.read_csv(CLEAN / "theme_label_sample.csv")
    sample[["sample_id", "split", "key", "app_name", "segment", "rating"]].to_csv(REGISTERS / "theme_label_sample_keys.csv", index=False)
    print(f"Wrote {len(outputs)} files to data/aggregates/ and the label sample keys to data/registers/")


if __name__ == "__main__":
    main()
