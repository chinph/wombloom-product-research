# Wombloom research dashboard

**Live:** https://wombloom-analysis-research.streamlit.app/

An interactive companion to the case study: the feature gap matrix, the priority model with adjustable weights and
effort, the evidence and quotes behind each action, and the plan compared with what Wombloom v1.0 contains.

It reads only `data/aggregates/` and `data/registers/` (counts, shares, averages and a short list of public quotes).
No review table, reviewer name or ID is published.

## Run it locally
From the repository root:

```
pip install -r requirements.txt
streamlit run dashboard/app.py
```

## Deploy it free on Streamlit Community Cloud
1. Push this repository to GitHub (public).
2. Sign in at https://share.streamlit.io with GitHub and choose **Create app**.
3. Pick the repository and branch, and set the main file path to `dashboard/app.py`.
4. Deploy. Streamlit installs `dashboard/requirements.txt` and gives you a public link.

Deploy from the repository root: the app imports `src/prioritize.py` and reads `data/aggregates/`.

## Refresh the data
`python src/build_aggregates.py` rebuilds `data/aggregates/` from the local database (not published).
