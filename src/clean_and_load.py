"""Step 5: clean the extracted reviews and load them into SQLite.

Reads data/clean/appstore_reviews.csv (author fields were already dropped in Step 3) and the shortlist metadata.
Writes data/clean/reviews_clean.csv and data/wombloom.db with two tables:
  apps     one row per shortlisted app (selection metadata and segment)
  reviews  one row per review, with language and quality flags

Nothing is deleted except exact duplicates: language and length problems are flagged, and the original text
is kept untouched, so later analysis can decide what to exclude.
Run from the project root:  python src/clean_and_load.py
"""
import sqlite3
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data" / "clean"
DB_PATH = ROOT / "data" / "wombloom.db"

SHORT_REVIEW_WORDS = 5   # fewer words than this = "very short" (little signal for theme analysis)
MIN_LANGDETECT_CHARS = 20  # language detection is unreliable on very short text

DetectorFactory.seed = 0  # langdetect is randomized by default; a fixed seed makes results repeatable


def detect_language(text):
    """ISO language code, or 'und' (undetermined) when the text is too short or has no letters."""
    if len(text) < MIN_LANGDETECT_CHARS:
        return "und"
    try:
        return detect(text)
    except LangDetectException:
        return "und"


def clean_reviews():
    df = pd.read_csv(CLEAN_DIR / "appstore_reviews.csv", parse_dates=["review_date"])
    rows_in = len(df)

    df["platform"] = "ios"
    # Title and text can be missing; use empty strings so length and language checks work.
    df["title"] = df["title"].fillna("")
    df["text"] = df["text"].fillna("")

    # Exact duplicates: same review ID, or identical content for the same app, country, date and rating.
    # Both are flagged first so the count can be reported, then the flagged rows are dropped.
    dup_id = df.duplicated(["platform", "app_id", "country", "review_id"], keep="first")
    dup_content = df.duplicated(["app_id", "country", "rating", "title", "text", "review_date"], keep="first")
    df["is_duplicate"] = dup_id | dup_content
    removed = int(df["is_duplicate"].sum())
    df = df[~df["is_duplicate"]].copy()

    df["word_count"] = df["text"].str.split().str.len()
    df["is_short"] = df["word_count"] < SHORT_REVIEW_WORDS
    df["is_empty"] = df["text"].str.strip() == ""
    df["language"] = df["text"].map(detect_language)
    df["is_english"] = df["language"] == "en"
    df["review_date"] = df["review_date"].dt.tz_convert("UTC")

    columns = ["platform", "app_id", "app_name", "segment", "country", "review_id", "rating", "title", "text",
               "review_date", "app_version", "language", "is_english", "word_count", "is_short", "is_empty",
               "is_duplicate"]
    return df[columns], rows_in, removed


def build_apps_table():
    """Shortlist metadata joined with the discovery data (category, developer, rating counts)."""
    cand = pd.read_csv(CLEAN_DIR / "app_candidates_all.csv")
    cand["rating_count"] = cand[["rating_count_us", "rating_count_ca"]].max(axis=1)
    cand = cand[["app_id", "developer", "category", "price", "rating_count", "last_updated"]]
    cand = cand.rename(columns={"rating_count": "store_rating_count"})
    shortlist = pd.read_csv(CLEAN_DIR / "appstore_coverage.csv")[["app_id", "app_name", "segment"]].drop_duplicates()
    return shortlist.merge(cand, on="app_id", how="left")


def load_sqlite(apps, reviews):
    with sqlite3.connect(DB_PATH) as con:
        apps.to_sql("apps", con, if_exists="replace", index=False)
        out = reviews.copy()
        out["review_date"] = out["review_date"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # UTC ISO 8601 text
        for flag in ["is_english", "is_short", "is_empty", "is_duplicate"]:
            out[flag] = out[flag].astype(int)
        out.to_sql("reviews", con, if_exists="replace", index=False)
        con.execute("CREATE INDEX idx_reviews_app ON reviews(app_id, country)")
        con.execute("CREATE INDEX idx_reviews_date ON reviews(review_date)")


def main():
    reviews, rows_in, removed = clean_reviews()
    apps = build_apps_table()
    reviews.to_csv(CLEAN_DIR / "reviews_clean.csv", index=False)
    load_sqlite(apps, reviews)

    print(f"Rows in: {rows_in:,}  duplicates removed: {removed}  rows out: {len(reviews):,}")
    print(f"Apps table: {len(apps)} rows")
    print("\nLanguage (top 6):")
    print(reviews["language"].value_counts().head(6).to_string())
    print(f"\nEnglish: {reviews['is_english'].mean():.1%}  short (<{SHORT_REVIEW_WORDS} words): {reviews['is_short'].mean():.1%}"
          f"  empty text: {int(reviews['is_empty'].sum())}")


if __name__ == "__main__":
    main()
