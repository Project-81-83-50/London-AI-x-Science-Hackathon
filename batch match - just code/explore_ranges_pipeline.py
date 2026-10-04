"""
Scratch: the range rule inside the full three-batch pipeline, leave-one-location-out.

  1. Batch_3 or not?  fingerprint model (3 views combined), trained on the other 30 locations
  2. if not: Batch_1 vs Batch_2 by the material-percentage range rule (ranges from the other
     Batch_1 / Batch_2 locations)
  3. if the rule is unsure: Batch_1 vs Batch_2 fingerprint specialist
"""

import json
import warnings
from pathlib import Path

import numpy as np

import batch_classifier as B
from explore_ranges import PHASES, range_rule

warnings.filterwarnings("ignore")
OUT = Path(__file__).parent / "out" / "classifier"
table = json.loads((OUT / "get4_phases.json").read_text())
by_loc = {t["location"]: i for i, t in enumerate(table)}
rows = B.index(B.ROOT)
X = B.build_features(rows)
batch = np.array([r["batch"] for r in rows], dtype=object)
loc = np.array([r["location"] for r in rows])
view = np.array([r["view"] for r in rows])
locs = np.unique(loc)
truth = {l: batch[loc == l][0] for l in locs}


def fit(Xtr, ytr):
    mu = np.nanmean(Xtr, 0)
    return B.make_model().fit(np.where(np.isfinite(Xtr), Xtr, mu), ytr), mu


def location_logprob(l, labels, mask, classes):
    """Sum over the views of location l of per-view model log-probabilities (models trained without l)."""
    total = np.zeros(len(classes))
    for v in B.VIEWS:
        tr, te = mask & (loc != l) & (view == v), (loc == l) & (view == v)
        if te.any():
            m, mu = fit(X[tr], labels[tr])
            p = np.clip(m.predict_proba(np.where(np.isfinite(X[te]), X[te], mu)), 1e-6, 1)
            total += np.log(p[:, np.searchsorted(m.classes_, classes)]).sum(0)
    return total


is3 = np.where(batch == "Batch_3", "B3", "B12").astype(object)
results = {}
for z in (0, 1, 2):
    pred, how = {}, {}
    for l in locs:
        lp = location_logprob(l, is3, np.ones(len(rows), bool), np.array(["B12", "B3"], dtype=object))
        if lp[1] > lp[0]:
            pred[l], how[l] = "Batch_3", "step 1"
            continue
        train = [t for t in table if t["batch"] in ("Batch_1", "Batch_2") and t["location"] != l]
        p, _ = range_rule(table, by_loc[l], z, PHASES, train)
        if p:
            pred[l], how[l] = p, "range rule"
        else:
            lp2 = location_logprob(l, batch, batch != "Batch_3", np.array(["Batch_1", "Batch_2"], dtype=object))
            pred[l], how[l] = ("Batch_1", "Batch_2")[int(np.argmax(lp2))], "fingerprint fallback"
    right = {l: pred[l] == truth[l] for l in locs}
    per = {b: f"{sum(right[l] for l in locs if truth[l] == b)}/{sum(truth[l] == b for l in locs)}"
           for b in ("Batch_1", "Batch_2", "Batch_3")}
    by_how = {h: f"{sum(right[l] for l in locs if how[l] == h)}/{sum(how[l] == h for l in locs)}"
              for h in ("step 1", "range rule", "fingerprint fallback")}
    print(f"margin {z} SE: {sum(right.values())}/31 locations  per batch {per}   correct per route {by_how}")
    print("    wrong: " + " ".join(f"{l}({truth[l][-1]}->{pred[l][-1]}, {how[l]})" for l in locs if not right[l]))
