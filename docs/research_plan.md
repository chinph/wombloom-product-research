# Wombloom Market Research: Data Collection Plan

## Context
I'm a data analyst building a portfolio around Wombloom, my pregnancy journal app on the iOS App Store. I want to collect public app reviews from competitor pregnancy and baby tracking apps, then analyze them (themes, sentiment, feature gaps) to guide product decisions. This plan covers **data collection only**. Analysis comes later.

## Scope
- Platforms: iOS App Store first, then Google Play.
- Countries: US and Canada.
- Category: pregnancy apps plus baby tracking apps (including postpartum and newborn tracking).
- Language: English (flag other languages, don't delete them).
- I have not chosen competitors yet. Part of this project is selecting them with a documented, repeatable method.

## Working rules
- Python 3.11+, managed with a virtual environment. I use VS Code.
- Be polite to every service: wait 1 to 2 seconds between requests, set a clear User-Agent, retry with backoff, and never hammer endpoints.
- Privacy: do NOT store reviewer names, user IDs or profile URLs. Drop them at ingestion.
- Keep raw responses untouched in `data/raw/`. Cleaning writes to `data/clean/` and SQLite, so everything is reproducible.
- Verify each endpoint or library actually works before building on it (these change without notice). If something is blocked or broken, stop and tell me instead of working around it with anything that looks like evasion.
- Explain choices briefly in code comments and the README. I want to be able to explain every step in an interview.
- Pause for my review at every step marked CHECKPOINT.

## Folder structure
```
wombloom-research/
  README.md
  PLAN.md
  requirements.txt
  data/
    raw/            # untouched API responses (JSON)
    clean/          # cleaned CSV/Parquet
    wombloom.db     # SQLite
  notebooks/
  src/
    discover_apps.py
    fetch_appstore_reviews.py
    fetch_googleplay_reviews.py
    clean_and_load.py
    quality_report.py
  docs/
    app_selection_log.md
    data_quality_report.md
```

## Steps

### Step 1: Setup
- Create the folder structure, a virtual environment and `requirements.txt` (requests, pandas, langdetect, google-play-scraper, tqdm).
- Initialize git with a sensible `.gitignore` (ignore `data/raw/` and the database; I decide later what to publish).
- Write a first README with the project goal and scope above.

### Step 2: App discovery (the selection method)
Goal: choose 8 to 10 apps using a documented method, not gut feeling.

1. Use Apple's iTunes Search API (country US, then CA) with these keywords: pregnancy tracker, pregnancy journal, pregnancy week by week, pregnancy app, baby bump, prenatal, baby tracker, newborn tracker, baby feeding sleep tracker, postpartum.
2. Merge and de-duplicate results by app ID. Capture: app ID, name, developer, category, price, rating count, average rating, last updated date, description.
3. Apply filters and record how many apps each filter removes:
   - Category is Health & Fitness, Medical, Lifestyle or Parenting-like
   - At least 1,000 ratings (enough reviews to analyze)
   - Updated within the last 12 months (still maintained)
   - Not a duplicate or regional clone of another app
4. Segment the survivors into:
   - **Direct competitors**: journal / memory-keeping pregnancy apps (closest to Wombloom)
   - **Category leaders**: the big pregnancy trackers
   - **Adjacent**: baby trackers that pregnant users move on to
5. Output `docs/app_selection_log.md` with the candidate table, filters applied, and a recommended shortlist of 8 to 10 apps balanced across the three groups, each with a one-line reason. Also list notable apps excluded and why.

**CHECKPOINT:** show me the shortlist. I confirm or swap apps before any review collection.

### Step 3: App Store reviews
- Use Apple's public customer-reviews RSS/JSON feed per app and country (US, CA), sorted by most recent, paginating as far as the feed allows.
- Save raw JSON per app, country and page under `data/raw/appstore/`.
- Extract: app ID, country, review ID, rating, title, text, date, app version. Drop author fields.
- Log per app how many reviews were retrieved and the date range covered. Note the limitation that the feed only returns recent reviews.

**CHECKPOINT:** show me the row counts and date coverage per app before continuing.

### Step 4: Google Play reviews
**SKIPPED (decision after Step 3):** the iOS sample (7,955 reviews across 10 apps) is enough for exploratory research, and Wombloom launches on iOS first. The scope is now iOS only. The `platform` column stays in the schema so Android can be added later. The original plan is kept below for reference.

- Use the `google-play-scraper` library for the matching Android apps (US, CA). Find package names by matching app name and developer; flag any I need to confirm manually.
- Cap at a sensible number per app (for example 1,000 to 2,000, newest first) and rate-limit.
- Same fields as Step 3 where available. Drop author fields. Note in the README that this library is unofficial.

### Step 5: Clean and load
- Combine both platforms into one schema: `reviews(platform, app_id, app_name, country, review_id, rating, title, text, review_date, app_version, language, is_duplicate)`.
- Steps: remove exact duplicates, standardize dates (UTC), detect language, flag empty or very short reviews, keep raw text intact.
- Load to SQLite in two tables: `apps` (selection metadata and segment) and `reviews`.
- Also export a clean CSV.

### Step 6: Data quality report
- Produce `docs/data_quality_report.md` with: reviews per app, platform and country; date coverage; rating distribution per app; share of non-English and very short reviews; duplicates removed; known limitations and biases (recent-only feeds, review self-selection, platform differences).
- Include a few simple charts (matplotlib) saved to `docs/`.

## Done when
- A shortlist of 8 to 10 apps with a documented selection method exists.
- Reviews from both platforms for US and CA are in SQLite with a clear schema.
- Every script can be re-run from the README instructions.
- The data quality report is written, with limitations stated honestly.

## Start now
Begin with Step 1 and Step 2. Stop at the first CHECKPOINT and show me the app shortlist.
