"""Step 7: theme codebook and keyword tagging for review text.

A theme is a TOPIC a review discusses, not a verdict: the star rating says whether the review is a
complaint or praise, so complaint pairs (ads, pricing, usability, community, sharing) are one topic here.
Each theme is a list of regular expressions run on the lowercased title + text. A review can match many themes.

The rules were written from the codebook in the notebook (section 14), tuned on the 100 'dev' reviews of the
hand-labeled sample, and scored once on the 50 held-out 'test' reviews. See evaluate() and the notebook.
Run from the project root to print the scores:  python src/themes.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data" / "clean"            # local only: the labeled sample includes review text
REGISTERS = ROOT / "data" / "registers"         # published: the hand labels themselves

# code -> (label, [regex, ...]).  Patterns are matched case-insensitively.
THEMES = {
    "ADS": ("Ads", [
        r"\bads?\b", r"\badverts?\b", r"advertis", r"\bsponsored\b",
    ]),
    "PRICE": ("Pricing and subscription", [
        r"subscri", r"paywall", r"pay wall", r"premium", r"\bpa(y|id|ying)\b", r"\bcharg", r"refund", r"renew",
        r"free trial", r"\bscam", r"expensive", r"overpriced", r"pricey", r"\bpric(e|ed|ing)\b", r"\bcosts?\b",
        r"\bmoney\b", r"per year", r"\bannual", r"\$\d", r"upgrad", r"\bfees?\b", r"\bfree\b",
    ]),
    "UPDATE": ("Updates and redesigns", [
        r"\bupdated\b", r"\bupdating\b",
        r"\b(the|this|an|another|after|since|until|following) update\b",
        r"\b(new|newest|latest|recent|last|bad|terrible|horrible|awful|major|subsequent|constant) updates?\b",
        r"new (version|layout|look|design|interface|ui|format)", r"latest version", r"old(er)? version", r"redesign",
        r"previous (version|design|layout|look|formatting)", r"used to (be|love|work)", r"constantly changing",
        r"stop changing", r"interface change", r"since the (latest|last|new|recent)",
    ]),
    "BUGS": ("Bugs, crashes and slowness", [
        r"crash", r"freez", r"froze", r"glitch", r"\bbugs?\b", r"\bbuggy\b", r"\blag(s|gy|ging)?\b", r"\bslow\b",
        r"not working", r"stopped working", r"doesn'?t work", r"won'?t (load|open|work)", r"wouldn'?t (load|open|work)",
        r"can'?t open", r"cannot open", r"(black|white|loading) screen", r"\berrors?\b", r"technical", r"\bbroke(n)?\b",
        r"malfunction", r"unusable", r"(doesn'?t|does not|not) load", r"keeps? (closing|quitting)",
    ]),
    "DATA": ("Data loss and sync", [
        r"lost (all|my|everything|data)", r"\bgone\b", r"erased", r"disappear", r"\bsync", r"(not|can'?t|cannot|won'?t|don'?t|doesn'?t|didn'?t) sav(e|ing)",
        r"data loss", r"deleted (my|all)", r"back ?up", r"\brestore\b",
    ]),
    "ACCOUNT": ("Account and login", [
        r"log(ged|ging)? ?(in|out)\b", r"login", r"logout", r"sign(ed|ing)? ?(in|up|out)\b", r"signup", r"\baccount",
        r"password", r"verification", r"age requirement",
    ]),
    "ACCURACY": ("Accuracy of information", [
        r"inaccura", r"incorrect", r"not (very )?accurate", r"isn'?t accurate", r"\bwrong (date|week|size|info|information|time)",
        r"\b(way|totally|completely|wildly|week or so|week) off\b", r"due date", r"miscalculat", r"not (right|correct)",
    ]),
    "INCLUSION": ("Inclusivity and tone", [
        r"inclusiv", r"heterosexual", r"\bstraight\b", r"\bcis\b", r"same[- ]sex", r"\blgbt", r"queer", r"\bgay\b",
        r"lesbian", r"\bivf\b", r"surrogat", r"intended parent", r"discriminat", r"sexist", r"\bbias(ed)?\b",
        r"twin[- ]friendly", r"for twins", r"premie", r"premature", r"\bteen", r"age requirement", r"weight gain", r"gain(ing)? (too much )?weight",
        r"single (mom|mother|parent)", r"adopt", r"father'?s? experience",
    ]),
    "COMMUNITY": ("Community", [
        r"communit", r"forums?", r"\bboards?\b", r"\bgroups?\b", r"other (moms|mothers|parents|mamas|women)", r"toxic",
        r"bully", r"catty", r"cattiness", r"shaming", r"hostile", r"drama", r"discussion", r"mature women", r"not alone",
    ]),
    "PRIVACY": ("Privacy and data use", [
        r"privacy", r"\bsold\b", r"sell (my|your)", r"selling", r"personal (info|information|data)", r"data mining",
        r"\bmined\b", r"\bcamera\b", r"consent",
    ]),
    "AI": ("AI features", [
        r"\bai\b", r"artificial intelligence", r"chatgpt",
    ]),
    "SUPPORT": ("Customer support", [
        r"customer (service|support)", r"\bsupport (team|staff)", r"no (response|reply)", r"never (replied|responded|heard)",
        r"contact(ed)? (them|us|support)", r"reach(ed)? out", r"help ?desk", r"refused",
    ]),
    "SHARING": ("Sharing with partner and family", [
        r"\bshar(e|ed|es|ing)\b", r"partner", r"spouse", r"\bdad\b", r"daddy", r"grandma",
        r"grandmother", r"grandparent", r"grandchild", r"caregiver", r"nanny", r"both of us", r"same app",
        r"co-?parent", r"family members", r"take turns",
    ]),
    "INFO": ("Information and articles", [
        r"informative", r"information", r"\binfo\b", r"articles?", r"\blearn", r"educat", r"week[- ]by[- ]week", r"\bweekly\b",
        r"daily (fact|tip|update)", r"fun facts?", r"\bfacts\b", r"\btips\b", r"knowledge", r"resources?", r"guidance",
        r"descriptions?", r"tell me all about", r"development",
    ]),
    "TRACKING": ("Tracking and logging", [
        r"\btrack(s|er|ing|ed)?\b", r"\blogs?\b(?!\s*(in|out))", r"\blogging\b", r"\blogged\b(?!\s*(in|out))", r"schedule", r"pattern", r"trend",
        r"sweet ?spot", r"wake window", r"\bstats?\b", r"timer", r"\bcharts?\b", r"graph", r"\breports?\b", r"diaper",
        r"feeding", r"\bnaps?\b", r"\bsleep", r"summar(y|ies)", r"(feeding|nap|diaper|sleep) reminders?",
    ]),
    "MEMORIES": ("Memories and journaling", [
        r"memor(y|ies)", r"journal", r"diary", r"scrap ?book", r"baby book", r"keepsake", r"photo ?book", r"prompts?",
        r"look(ing)? back", r"\bbond", r"\bcapture\b", r"\bjourney\b",
    ]),
    "VISUALS": ("Visuals and baby size", [
        r"\b3d\b", r"baby size", r"size of", r"how big", r"fruit", r"raspberry", r"pineapple", r"ultrasound", r"animation",
    ]),
    "USABILITY": ("Ease of use and design", [
        r"\beasy\b", r"\beasier\b", r"\beasiest\b", r"\bsimple\b", r"intuitive", r"user[- ]friendly", r"navigat", r"clutter",
        r"confus", r"complicated", r"hard to (use|find|see|read|navigate)", r"difficult", r"messy", r"\blayout", r"\bui\b",
        r"\bux\b", r"interface", r"\bdesign", r"pop[- ]?ups?", r"too (much|busy|many)", r"\bbusy\b", r"bulky", r"tedious",
        r"convenient", r"\bscroll",
    ]),
    "REQUEST": ("Feature requests", [
        r"\bi wish (i could|they|you|there|it|the)\b", r"would (love|like)\b", r"would be (nice|helpful)", r"it would be great if",
        r"\bplease (add|make|bring)", r"\bneeds? (widget|timer|support|an? option|more|the ability|a way)", r"can we (get|have)",
        r"\bmissing\b", r"\blacks?\b", r"no way to", r"could use", r"should (add|have|be able)", r"an option", r"option to",
        r"manually (change|edit|add)",
    ]),
}

_COMPILED = {code: [re.compile(p, re.I) for p in pats] for code, (_, pats) in THEMES.items()}

# Hand labels were written as 21 valence-aware codes; complaint/praise pairs fold into the merged topics above.
LABEL_MAP = {
    "N1": "ADS", "N2": "PRICE", "P6": "PRICE", "N3": "UPDATE", "N4": "BUGS", "N5": "DATA", "N6": "ACCOUNT",
    "N7": "ACCURACY", "N8": "INCLUSION", "N9": "COMMUNITY", "P5": "COMMUNITY", "N10": "PRIVACY", "N11": "USABILITY",
    "P2": "USABILITY", "N12": "SUPPORT", "N13": "SHARING", "P7": "SHARING", "R1": "REQUEST", "P1": "INFO",
    "P3": "TRACKING", "P4": "MEMORIES", "P8": "VISUALS", "AI": "AI",
}
# Reviews #76, #99, #127 and #138 discuss AI features (added after labeling, from reading the text, before any rule scoring).
EXTRA_LABELS = {76: ["AI"], 99: ["AI"], 127: ["AI"], 138: ["AI"],
                # Label correction found while reviewing dev mistakes: the partner receives the questions too.
                38: ["N13"]}

# These four topics were hand-labeled only where praised (the P codes had no complaint twin), so they are
# scored on 4-5 star reviews, where the labels are complete.
PRAISE_ONLY = {"TRACKING", "INFO", "MEMORIES", "VISUALS"}


def tag_text(text):
    """Set of theme codes whose rules match the text."""
    return {code for code, pats in _COMPILED.items() if any(p.search(text) for p in pats)}


def tag_reviews(df, text_col="text_full"):
    """0/1 column per theme for every review in df."""
    tags = df[text_col].fillna("").map(tag_text)
    return pd.DataFrame({code: tags.map(lambda s, c=code: int(c in s)) for code in THEMES}, index=df.index)


def load_hand_labels():
    """Hand-labeled sample as a frame with one 0/1 column per theme, plus split (dev/test)."""
    sample = pd.read_csv(CLEAN_DIR / "theme_label_sample.csv")
    labels = {}
    for line in (REGISTERS / "theme_hand_labels.txt").read_text(encoding="utf-8").splitlines():
        sid, _, codes = line.partition(":")
        labels[int(sid)] = {LABEL_MAP[c] for c in codes.split()}
    for sid, codes in EXTRA_LABELS.items():
        labels[sid] |= {LABEL_MAP[c] for c in codes}
    truth = pd.DataFrame({code: sample["sample_id"].map(lambda i, c=code: int(c in labels[i])) for code in THEMES})
    return pd.concat([sample, truth.add_prefix("true_")], axis=1)


def evaluate(split=None):
    """Precision, recall and F1 per theme against the hand labels, optionally for one split ('dev' or 'test')."""
    data = load_hand_labels()
    if split:
        data = data[data["split"] == split]
    pred = tag_reviews(data)
    rows = []
    for code, (label, _) in THEMES.items():
        rows_used = data["rating"] >= 4 if code in PRAISE_ONLY else data["rating"] > 0
        t, p = data.loc[rows_used, f"true_{code}"].astype(bool), pred.loc[rows_used, code].astype(bool)
        tp, fp, fn = int((t & p).sum()), int((~t & p).sum()), int((t & ~p).sum())
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if tp else (0.0 if tp + fp + fn else float("nan"))
        rows.append({"theme": code, "label": label, "hand_labeled": int(t.sum()), "rule_tagged": int(p.sum()),
                     "true_pos": tp, "false_pos": fp, "false_neg": fn, "precision": prec, "recall": rec, "f1": f1})
    return pd.DataFrame(rows)


def reliability_tiers(min_test_positives=3, min_f1=0.75):
    """'reliable' if the held-out test split has enough real examples and a good F1, otherwise 'directional'."""
    test = evaluate("test")
    ok = (test["hand_labeled"] >= min_test_positives) & (test["f1"] >= min_f1)
    return pd.Series(np.where(ok, "reliable", "directional"), index=test["theme"])


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for split in ("dev", "test"):
        print(f"\n{split.upper()}")
        print(evaluate(split).round(2).to_string(index=False))
