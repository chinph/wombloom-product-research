"""Step 2: discover candidate apps with Apple's iTunes Search API and document the selection.

Method (repeatable): run every keyword in every country, save each raw response,
merge by app ID, apply filters in a fixed order while counting what each removes,
then segment the survivors with simple keyword rules.

Outputs:
  data/raw/itunes_search/<country>__<keyword>.json   untouched API responses
  data/clean/app_candidates.csv                      all merged candidates + flags
  docs/app_selection_log.md                          funnel, segments, shortlist table
Run from the project root:  python src/discover_apps.py
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "itunes_search"
CLEAN_DIR = ROOT / "data" / "clean"
DOCS_DIR = ROOT / "docs"

COUNTRIES = ["us", "ca"]
KEYWORDS = [
    "pregnancy tracker", "pregnancy journal", "pregnancy week by week",
    "pregnancy app", "baby bump", "prenatal", "baby tracker",
    "newborn tracker", "baby feeding sleep tracker", "postpartum",
]
SEARCH_LIMIT = 200  # the API maximum per request
# The Search API is documented at roughly 20 calls/minute, so 3 s between calls stays under it.
DELAY_SECONDS = 3
HEADERS = {"User-Agent": "WombloomResearch/0.1 (portfolio market research; contact nphchi223@gmail.com)"}

# Filter thresholds from PLAN.md
ALLOWED_GENRES = {"Health & Fitness", "Medical", "Lifestyle", "Education", "Social Networking"}
MIN_RATINGS = 1000
MAX_AGE_DAYS = 365

# Segmentation keyword rules (documented in the selection log)
PREGNANCY_RE = re.compile(r"pregnan|prenatal|expecting|trimester|baby bump|due date", re.I)
BABY_RE = re.compile(r"newborn|baby|infant|postpartum|toddler|nursing|breastfeed", re.I)
JOURNAL_RE = re.compile(r"journal|diary|memor|keepsake|scrapbook|milestone photo|bump photo", re.I)
TRACKER_RE = re.compile(r"feeding|sleep|diaper|nap|growth|track", re.I)
LEADER_MIN_RATINGS = 20_000
# Cycle / fertility trackers are a different product (out of scope) unless the name says pregnancy
CYCLE_RE = re.compile(r"period|cycle|ovulation|fertil|menstrua|flo|clue", re.I)


def search(session, keyword, country):
    """One Search API call with retry + exponential backoff. Raw JSON is saved untouched."""
    out = RAW_DIR / f"{country}__{keyword.replace(' ', '_')}.json"
    params = {"term": keyword, "country": country, "entity": "software", "limit": SEARCH_LIMIT}
    for attempt in range(4):
        try:
            resp = session.get("https://itunes.apple.com/search", params=params, timeout=30)
            if resp.status_code == 200:
                out.write_text(resp.text, encoding="utf-8")
                return resp.json()["results"]
            print(f"  HTTP {resp.status_code} for {country}/{keyword}, retry {attempt + 1}")
        except requests.RequestException as exc:
            print(f"  {exc!r} for {country}/{keyword}, retry {attempt + 1}")
        time.sleep(DELAY_SECONDS * 2 ** (attempt + 1))
    raise RuntimeError(f"Search failed for {country}/{keyword}; stopping instead of working around it.")


def collect():
    """Run all keyword x country searches and merge by app ID."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    apps, query_log = {}, []
    for country in COUNTRIES:
        for keyword in KEYWORDS:
            results = search(session, keyword, country)
            new = 0
            for r in results:
                app_id = r["trackId"]
                if app_id not in apps:
                    new += 1
                    apps[app_id] = {
                        "app_id": app_id,
                        "name": r.get("trackName"),
                        "developer": r.get("artistName"),
                        "category": r.get("primaryGenreName"),
                        "price": r.get("price"),
                        "rating_count_us": None,
                        "avg_rating_us": None,
                        "rating_count_ca": None,
                        "avg_rating_ca": None,
                        "last_updated": r.get("currentVersionReleaseDate"),
                        "bundle_id": r.get("bundleId"),
                        "description": r.get("description"),
                        "found_by": set(),
                    }
                a = apps[app_id]
                a[f"rating_count_{country}"] = r.get("userRatingCount")
                a[f"avg_rating_{country}"] = r.get("averageUserRating")
                a["found_by"].add(f"{country}:{keyword}")
            query_log.append((country, keyword, len(results), new))
            print(f"{country} | {keyword:<28} {len(results):>3} results, {new:>3} new")
            time.sleep(DELAY_SECONDS)
    df = pd.DataFrame(apps.values())
    df["found_by"] = df["found_by"].apply(lambda s: "; ".join(sorted(s)))
    return df, query_log


def normalize_name(name):
    """Name used to spot clones: lowercase letters/digits only, text after a dash or colon dropped."""
    base = re.split(r"\s[-:|–—]\s|:", name or "")[0]
    return re.sub(r"[^a-z0-9]", "", base.lower())


def apply_filters(df):
    """Apply filters in order; return the surviving frame and the funnel (step, removed, remaining)."""
    funnel = [("All unique apps found", None, len(df))]
    df = df.copy()
    df["rating_count"] = df[["rating_count_us", "rating_count_ca"]].max(axis=1).fillna(0)
    df["last_updated"] = pd.to_datetime(df["last_updated"], utc=True)
    text = (df["name"].fillna("") + " " + df["description"].fillna(""))

    steps = [
        ("Relevance: pregnancy or baby terms in name/description", text.str.contains(PREGNANCY_RE) | text.str.contains(BABY_RE)),
        (f"Category in {sorted(ALLOWED_GENRES)}", df["category"].isin(ALLOWED_GENRES)),
        ("Out of scope: cycle/fertility tracker without 'pregnan' in name", ~(df["name"].fillna("").str.contains(CYCLE_RE) & ~df["name"].fillna("").str.contains(r"pregnan", case=False))),
        (f"At least {MIN_RATINGS:,} ratings", df["rating_count"] >= MIN_RATINGS),
        (f"Updated within {MAX_AGE_DAYS} days", df["last_updated"] >= datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)),
    ]
    for label, mask in steps:
        before = len(df)
        df = df[mask.loc[df.index]]
        funnel.append((label, before - len(df), len(df)))

    # Clone filter: same normalized name -> keep the one with the most ratings
    before = len(df)
    df = df.assign(_key=df["name"].map(normalize_name)).sort_values("rating_count", ascending=False)
    dupes = df[df.duplicated("_key", keep="first")]
    df = df.drop_duplicates("_key", keep="first").drop(columns="_key")
    funnel.append(("Duplicate / regional clone (same normalized name)", before - len(df), len(df)))
    return df, funnel, dupes


def segment(row):
    """Direct competitor / Category leader / Adjacent, from simple keyword rules."""
    text = f"{row['name']} {row['description']}"
    journal_text = f"{row['name']} {(row['description'] or '')[:400]}"
    name_preg = bool(PREGNANCY_RE.search(row["name"] or ""))
    desc_head_preg = bool(PREGNANCY_RE.search((row["description"] or "")[:400]))
    pregnancy_focused = name_preg or desc_head_preg
    if pregnancy_focused and JOURNAL_RE.search(journal_text):
        return "Direct competitor"
    if name_preg and row["rating_count"] >= LEADER_MIN_RATINGS:
        return "Category leader"
    if not name_preg and BABY_RE.search(text) and TRACKER_RE.search(text):
        return "Adjacent"
    return "Pregnancy other"


def write_log(all_df, survivors, funnel, query_log, dropped_dupes):
    """Write docs/app_selection_log.md with the evidence the shortlist is chosen from."""
    DOCS_DIR.mkdir(exist_ok=True)
    log_path = DOCS_DIR / "app_selection_log.md"
    # Section 6 (shortlist) is written by hand after review; keep it across re-runs.
    kept_tail = ""
    if log_path.exists():
        old = log_path.read_text(encoding="utf-8")
        if "## 6. Recommended shortlist" in old and "_To be written" not in old:
            kept_tail = old[old.index("## 6. Recommended shortlist"):]
    lines = [
        "# App Selection Log", "",
        f"Generated {datetime.now().strftime('%Y-%m-%d')} by `src/discover_apps.py`.", "",
        "## 1. Queries run", "",
        "| Country | Keyword | Results | New apps added |", "|---|---|---|---|",
    ]
    lines += [f"| {c} | {k} | {n} | {new} |" for c, k, n, new in query_log]
    lines += ["", "## 2. Filter funnel", "", "| Step | Removed | Remaining |", "|---|---|---|"]
    lines += [f"| {s} | {'' if r is None else r} | {rem} |" for s, r, rem in funnel]
    lines += ["", "## 3. Surviving candidates by segment", ""]
    cols = ["segment", "name", "developer", "category", "rating_count", "avg_rating", "price", "app_id"]
    table = survivors.copy()
    table["avg_rating"] = table[["avg_rating_us", "avg_rating_ca"]].mean(axis=1).round(2)
    table["rating_count"] = table["rating_count"].astype(int)
    lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in table.sort_values(["segment", "rating_count"], ascending=[True, False]).iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    lines += ["", "## 4. Removed as duplicates/clones", ""]
    lines += [f"- {r['name']} ({r['developer']}, {int(r['rating_count']):,} ratings)" for _, r in dropped_dupes.iterrows()] or ["- none"]
    lines += [
        "", "## 5. Segmentation rules", "",
        "- **Direct competitor**: pregnancy-focused (name, or first 400 characters of description) AND mentions journal/diary/memories/keepsake/scrapbook in the name or first 400 characters of the description.",
        f"- **Category leader**: pregnancy in the app name AND at least {LEADER_MIN_RATINGS:,} ratings.",
        "- **Adjacent**: not pregnancy-named, mentions baby/newborn/postpartum AND feeding/sleep/diaper/growth/tracking.",
        "- **Pregnancy other**: pregnancy-focused apps that fit none of the above.",
        "",
    ]
    if not kept_tail:
        kept_tail = "## 6. Recommended shortlist\n\n_To be written after manual review of the table above._\n"
    log_path.write_text("\n".join(lines) + "\n" + kept_tail, encoding="utf-8")


def main():
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    all_df, query_log = collect()
    survivors, funnel, dropped = apply_filters(all_df)
    survivors["segment"] = survivors.apply(segment, axis=1)
    all_df.to_csv(CLEAN_DIR / "app_candidates_all.csv", index=False)
    survivors.drop(columns=["description"]).to_csv(CLEAN_DIR / "app_candidates_filtered.csv", index=False)
    write_log(all_df, survivors, funnel, query_log, dropped)
    print("\nFunnel:")
    for s, r, rem in funnel:
        print(f"  {s}: removed {r}, remaining {rem}")
    print(survivors["segment"].value_counts().to_string())


if __name__ == "__main__":
    main()
