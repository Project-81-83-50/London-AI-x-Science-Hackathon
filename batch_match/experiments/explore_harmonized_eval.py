"""Scratch: leave-one-location-out evaluation of the harmonised material features."""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

import batch_classifier as B  # noqa: E402

warnings.filterwarnings("ignore")
OUT = PROJECT_DIR / "out" / "classifier"
rows = B.index(B.ROOT)
data = json.loads((OUT / "harmonized_features.json").read_text())
by_path = {r["path"]: r for r in data["rows"]}
keys = sorted(k for k in data["rows"][0] if k != "path" and not k.startswith("_"))
X = np.array([[by_path[str(r["path"])].get(k, np.nan) for k in keys] for r in rows], float)
batches = np.array(["Batch_1", "Batch_2", "Batch_3"], dtype=object)
batch = np.array([r["batch"] for r in rows], dtype=object)
loc = np.array([r["location"] for r in rows])
view = np.array([r["view"] for r in rows])
locs = np.unique(loc)
true_loc = np.array([batch[loc == l][0] for l in locs])
CROSS = {
    "rxax5ozo": "Batch_2 imaged in a Batch_3 session",
    "cfe5vt7s": "Batch_3 imaged in a Batch_1/2 session",
    "pl8uabbv": "Batch_3 imaged in a Batch_1/2 session",
}
session_b = {"rxax5ozo"} | {l for l, t in zip(locs, true_loc) if t == "Batch_3" and l not in ("cfe5vt7s", "pl8uabbv")}

print("harmonisation check (should be the same for every batch):")
for name in ("_check_noise", "_check_median_graphite"):
    vals = {b: [by_path[str(r["path"])][name] for r in rows if r["batch"] == b] for b in batches}
    print(f"  {name[7:]:16s} " + "  ".join(f"{b}: {np.median(v):.4f}" for b, v in vals.items()))

MODELS = {
    "LDA": lambda: make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
    "logistic": lambda: make_pipeline(
        StandardScaler(), LogisticRegression(C=0.05, max_iter=5000, class_weight="balanced")
    ),
}


def run(make, y, classes, mask=None):
    mask = np.ones(len(rows), bool) if mask is None else mask
    lp = np.full((len(rows), len(classes)), np.nan)
    for l in np.unique(loc[mask]):
        for v in B.VIEWS:
            tr, te = mask & (loc != l) & (view == v), mask & (loc == l) & (view == v)
            if te.any():
                mu = np.nanmean(X[tr], 0)
                m = make().fit(np.where(np.isfinite(X[tr]), X[tr], mu), y[tr])
                p = np.clip(m.predict_proba(np.where(np.isfinite(X[te]), X[te], mu)), 1e-6, 1)
                lp[te] = np.log(p[:, np.searchsorted(m.classes_, classes)])
    return lp


results = {}
for mname, make in MODELS.items():
    lp = run(make, batch, batches)
    results[mname] = lp
    pi = batches[lp.argmax(1)]
    pl = np.array([batches[lp[loc == l].sum(0).argmax()] for l in locs])
    pb_img = [100 * np.mean(pi[batch == b] == b) for b in batches]
    pv = [100 * np.mean(pi[view == v] == batch[view == v]) for v in B.VIEWS]
    print(f"\nharmonised material features / {mname}")
    print(
        f"  single image {100 * np.mean(pi == batch):3.0f}% (balanced {np.mean(pb_img):3.0f}%)  per batch "
        + ", ".join(f"{b[-1]}: {x:.0f}%" for b, x in zip(batches, pb_img))
        + "  per view "
        + ", ".join(f"{v} {x:.0f}%" for v, x in zip(B.VIEWS, pv))
    )
    print(
        f"  locations {np.sum(pl == true_loc)}/31  per batch "
        + ", ".join(f"{b[-1]}: {np.sum((pl == true_loc) & (true_loc == b))}/{np.sum(true_loc == b)}" for b in batches)
        + f"  (balanced {100 * np.mean([np.mean(pl[true_loc == b] == b) for b in batches]):.0f}%)"
    )
    print(
        "  crossovers: "
        + "; ".join(
            f"{l} -> {pl[list(locs).index(l)]} ({'RIGHT' if pl[list(locs).index(l)] == true_loc[list(locs).index(l)] else 'wrong'})"
            for l in CROSS
        )
    )
    print("  wrong: " + " ".join(f"{l}({t[-1]}->{p[-1]})" for l, t, p in zip(locs, true_loc, pl) if t != p))

# can harmonised features still recognise the imaging session? (they should not)
sess = np.array(["S_B" if l in session_b else "S_A" for l in loc], dtype=object)
lp = run(MODELS["LDA"], sess, np.array(["S_A", "S_B"], dtype=object))
ps = np.array([["S_A", "S_B"][lp[loc == l].sum(0).argmax()] for l in locs])
ts = np.array(["S_B" if l in session_b else "S_A" for l in locs])
print(
    f"\nsession leak test: harmonised features predict the imaging session of {np.sum(ps == ts)}/31 locations "
    f"(always guessing the larger session: {max(np.sum(ts == 'S_A'), np.sum(ts == 'S_B'))}/31)"
)

# Batch_1 vs Batch_2 specialist
m12 = np.isin(batch, ["Batch_1", "Batch_2"])
for mname, make in MODELS.items():
    lp = run(make, batch, batches[:2], m12)
    l12 = np.unique(loc[m12])
    pl = np.array([batches[:2][np.nansum(lp[loc == l], 0).argmax()] for l in l12])
    t12 = np.array([batch[loc == l][0] for l in l12])
    pi = batches[:2][np.nanargmax(np.where(np.isnan(lp), -np.inf, lp), 1)]
    print(
        f"Batch_1 vs Batch_2 specialist / {mname}: images {100 * np.mean(pi[m12] == batch[m12]):.0f}%, "
        f"locations {np.sum(pl == t12)}/14 (B1 {np.sum((pl == t12) & (t12 == 'Batch_1'))}/7, B2 {np.sum((pl == t12) & (t12 == 'Batch_2'))}/7)"
    )
np.save(OUT / "harmonized_logprobs.npy", results["LDA"])
