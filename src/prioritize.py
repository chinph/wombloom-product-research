"""Prioritization model: score each action from the review evidence, then test how stable the ranking is.

Score = w_reach * Reach + w_impact * Impact + w_confidence * Confidence - w_effort * Effort, each part on 0 to 1.
  Reach       share of reviews that mention the action's topic(s), averaged per app, min-max scaled
  Impact      stars at stake: |average rating when the topic is mentioned - average rating of all reviews|, min-max scaled
              (a topic that drags ratings down and a topic that lifts them both matter)
  Confidence  1.0 for a reliable keyword rule; for a directional rule 0.6 / 0.4 / 0.2 when it has 250+ / 100-249 / under 100 mentions.
              An action that uses several topics takes its weakest topic.
  Effort      1 (small), 2 (medium) or 3 (large), an analyst estimate that the owner can replace; scaled to 0 to 1 and subtracted

The weights are assumptions, not facts, so rank_stability() redraws them at random and reports how often each action
stays near the top. Actions with no clean review topic are left out of the scoring.
"""
import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {"reach": 0.25, "impact": 0.35, "confidence": 0.25, "effort": 0.15}
COMPONENTS = ["reach", "impact", "confidence", "effort"]


def confidence(tier, n_reviews):
    """Confidence in the evidence for an action, from rule reliability and number of mentions."""
    if tier == "reliable":
        return 1.0
    if n_reviews >= 250:
        return 0.6
    if n_reviews >= 100:
        return 0.4
    return 0.2


def _minmax(s):
    span = s.max() - s.min()
    return (s - s.min()) / span if span else s * 0.0


def components(evidence, efforts=None):
    """One row per scored action with each component on a 0 to 1 scale. evidence has one row per action and window."""
    df = evidence.copy()
    df["impact_raw"] = (df["avg_rating"] - df["baseline_rating"]).abs()
    df["reach"] = _minmax(df["reach_pct"])
    df["impact"] = _minmax(df["impact_raw"])
    df["confidence"] = [confidence(t, n) for t, n in zip(df["tier"], df["n_reviews"])]
    effort = df["effort"] if efforts is None else df["action_id"].map(efforts).fillna(df["effort"])
    df["effort_used"] = effort
    df["effort"] = (effort - 1) / 2  # 1,2,3 -> 0, 0.5, 1
    return df


def score_actions(evidence, weights=None, efforts=None):
    """Scores and ranks the actions; rank 1 is the highest score."""
    w = pd.Series(weights or DEFAULT_WEIGHTS)
    w = w / w.sum()
    df = components(evidence, efforts)
    df["score"] = (w["reach"] * df["reach"] + w["impact"] * df["impact"] + w["confidence"] * df["confidence"]
                   - w["effort"] * df["effort"])
    df["rank"] = df["score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank")


def rank_stability(evidence, efforts=None, n_draws=5000, seed=0):
    """Redraw the four weights at random (uniform over all weight mixes) and report where each action ranks."""
    df = components(evidence, efforts).reset_index(drop=True)
    parts = np.column_stack([df["reach"], df["impact"], df["confidence"], -df["effort"]])
    weights = np.random.default_rng(seed).dirichlet(np.ones(4), size=n_draws)
    scores = weights @ parts.T  # draws x actions
    ranks = (-scores).argsort(axis=1).argsort(axis=1) + 1  # 1 = best, per draw
    out = pd.DataFrame({
        "action_id": df["action_id"],
        "median_rank": np.median(ranks, axis=0),
        "best_rank": np.percentile(ranks, 10, axis=0),
        "worst_rank": np.percentile(ranks, 90, axis=0),
        "pct_in_top3": (ranks <= 3).mean(axis=0) * 100,
        "pct_in_top5": (ranks <= 5).mean(axis=0) * 100,
    })
    return out.sort_values("median_rank")
