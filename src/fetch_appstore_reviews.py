"""Step 3: collect App Store reviews for the confirmed shortlist from Apple's public customer-reviews feed.

Two stages, so extraction can be re-run offline without touching the network:
  1. fetch    saves each feed page untouched to data/raw/appstore/<app_id>_<country>_p<page>.json
  2. extract  reads those files and writes data/clean/appstore_reviews.csv (author fields are never read)
              plus data/clean/appstore_coverage.csv (reviews and date range per app and country)

The feed returns at most 10 pages x 50 reviews per app and country, newest first, so only
recent reviews are available. Existing raw pages are skipped, so a run can be resumed.
Run from the project root:  python src/fetch_appstore_reviews.py [--refresh]
"""
import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "appstore"
CLEAN_DIR = ROOT / "data" / "clean"

# Confirmed shortlist (docs/app_selection_log.md, section 6)
SHORTLIST = {
    1541460870: ("Cubtale: Pregnancy & Baby", "Direct"),
    1332312787: ("Qeepsake: Family Photo Album", "Direct"),
    995864179: ("280days: Pregnancy Diary App", "Direct"),
    289560144: ("Pregnancy Tracker App - WTE", "Category leader"),
    505864483: ("Pregnancy + | Tracker App", "Category leader"),
    568940747: ("The Bump: Pregnancy & Baby App", "Category leader"),
    882398397: ("Nurture Pregnancy Week by Week", "Category leader"),
    779656557: ("Baby Tracker - Newborn Log", "Adjacent"),
    1169136078: ("Huckleberry: Baby Tracker", "Adjacent"),
    1077177456: ("Glow Baby Tracker & Growth App", "Adjacent"),
}
COUNTRIES = ["us", "ca"]
MAX_PAGES = 10  # the feed's own limit
DELAY_SECONDS = 1.5
EMPTY_PAGE_CHECKS = 3  # total attempts before an empty page counts as the end of the feed
EMPTY_PAGE_WAIT = 5
HEADERS = {"User-Agent": "WombloomResearch/0.1 (portfolio market research; contact nphchi223@gmail.com)"}
URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"


def raw_path(app_id, country, page):
    return RAW_DIR / f"{app_id}_{country}_p{page}.json"


def get_page(session, app_id, country, page):
    """Fetch one page with retry + exponential backoff. Returns parsed JSON, or None if the page does not exist."""
    url = URL.format(country=country, page=page, app_id=app_id)
    for attempt in range(4):
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            print(f"    {exc!r}, retry {attempt + 1}")
            time.sleep(DELAY_SECONDS * 2 ** (attempt + 1))
            continue
        if resp.status_code == 200:
            raw_path(app_id, country, page).write_text(resp.text, encoding="utf-8")  # untouched
            return resp.json()
        if resp.status_code in (400, 404):
            return None  # past the last page
        print(f"    HTTP {resp.status_code}, retry {attempt + 1}")
        time.sleep(DELAY_SECONDS * 2 ** (attempt + 1))
    raise RuntimeError(f"Feed failed for app {app_id} {country} page {page}; stopping instead of working around it.")


def reviews_in(feed_json):
    """Entries that are reviews. Feed entries without a rating (app metadata) are skipped; one entry may be a dict."""
    entries = feed_json.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    return [e for e in entries if "im:rating" in e]


def fetch(refresh=False):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    for app_id, (name, _) in SHORTLIST.items():
        for country in COUNTRIES:
            fetched = 0
            for page in range(1, MAX_PAGES + 1):
                path = raw_path(app_id, country, page)
                data, n = None, 0
                # An empty page is only trusted as "end of feed" after re-checking: the feed sometimes
                # returns an empty page transiently (seen for app 289560144, US, page 1).
                for check in range(EMPTY_PAGE_CHECKS):
                    if check == 0 and path.exists() and not refresh:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    else:
                        if check > 0:
                            time.sleep(EMPTY_PAGE_WAIT)
                        data = get_page(session, app_id, country, page)
                        time.sleep(DELAY_SECONDS)
                    n = len(reviews_in(data)) if data is not None else 0
                    if n > 0:
                        break
                fetched += n
                if n == 0:
                    break
            print(f"{name:<36} {country}  {fetched:>4} reviews")


def extract():
    """Build the review table from the raw pages. Only the listed fields are read, so author data is dropped here."""
    rows = []
    for path in sorted(RAW_DIR.glob("*.json")):
        app_id, country, _ = path.stem.split("_")
        data = json.loads(path.read_text(encoding="utf-8"))
        for e in reviews_in(data):
            rows.append({
                "app_id": int(app_id),
                "app_name": SHORTLIST[int(app_id)][0],
                "segment": SHORTLIST[int(app_id)][1],
                "country": country,
                "review_id": e["id"]["label"],
                "rating": int(e["im:rating"]["label"]),
                "title": e["title"]["label"],
                "text": e["content"]["label"],
                "review_date": e["updated"]["label"],
                "app_version": e["im:version"]["label"],
            })
    df = pd.DataFrame(rows)
    df["review_date"] = pd.to_datetime(df["review_date"], utc=True)
    # Same review can appear on two pages if new reviews arrive mid-run; keep the first.
    df = df.drop_duplicates(["app_id", "country", "review_id"])
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEAN_DIR / "appstore_reviews.csv", index=False)

    coverage = (df.groupby(["app_id", "app_name", "segment", "country"])
                  .agg(reviews=("review_id", "size"),
                       first_date=("review_date", "min"),
                       last_date=("review_date", "max"),
                       avg_rating=("rating", "mean"))
                  .reset_index())
    coverage["days_covered"] = (coverage["last_date"] - coverage["first_date"]).dt.days
    coverage.to_csv(CLEAN_DIR / "appstore_coverage.csv", index=False)
    return df, coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-download pages that already exist")
    args = parser.parse_args()
    fetch(refresh=args.refresh)
    df, coverage = extract()
    print(f"\n{len(df):,} reviews written to data/clean/appstore_reviews.csv")
    print(coverage.assign(first_date=coverage["first_date"].dt.date, last_date=coverage["last_date"].dt.date)
                  .drop(columns="app_id").round(2).to_string(index=False))


if __name__ == "__main__":
    main()
