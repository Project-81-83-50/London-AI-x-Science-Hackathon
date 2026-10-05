"""
Scratch: is "trust the most confident method" a good way to combine methods?

Uses the leave-one-location-out image probabilities saved by explore_compare.py.
  1. calibration: for each method, average confidence vs actual accuracy
  2. strategies: average all methods / pick the most confident method, raw and calibrated
     (temperature scaling, fitted for each held-out location on the OTHER 30 locations only)
  3. selective prediction: accuracy when only the most confident X% of images are answered
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

import batch_classifier as B  # noqa: E402

OUT = PROJECT_DIR / "out" / "classifier"
d = np.load(OUT / "compare_logprobs.npz")
names, LP = list(d["names"]), d["lp"]
base = [i for i, n in enumerate(names) if not n.startswith("ENSEMBLE")]
rows = B.index(B.ROOT)
batches = np.array(sorted({r["batch"] for r in rows}), dtype=object)
batch = np.array([r["batch"] for r in rows], dtype=object)
loc = np.array([r["location"] for r in rows])
y = np.searchsorted(batches, batch)
TEMPS = np.geomspace(0.3, 300, 60)


def softmax(lp):
    e = np.exp(lp - lp.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def best_temperature(lp, yy):
    nll = [-np.log(softmax(lp / t)[np.arange(len(yy)), yy] + 1e-12).mean() for t in TEMPS]
    return TEMPS[int(np.argmin(nll))]


def calibrated(m):
    """Temperature-scaled probabilities; each location's temperature is fitted on the other locations."""
    out = np.zeros_like(LP[m])
    for l in np.unique(loc):
        t = best_temperature(LP[m][loc != l], y[loc != l])
        out[loc == l] = softmax(LP[m][loc == l] / t)
    return out


print("1. CALIBRATION: does a method's confidence match how often it is right?")
P_raw = {m: softmax(LP[m]) for m in base}
P_cal = {m: calibrated(m) for m in base}
for m in base:
    for label, P in (("raw", P_raw[m]), ("calibrated", P_cal[m])):
        conf, right = P.max(1), P.argmax(1) == y
        hi = conf >= 0.9
        print(
            f"  {names[m]:38s} {label:10s} avg confidence {100 * conf.mean():4.0f}%, actually right {100 * right.mean():4.0f}%;"
            f"  when it says >=90%: right {100 * right[hi].mean() if hi.any() else float('nan'):4.0f}% of {hi.sum()} images"
        )


def report(label, P):
    pred = P.argmax(1)
    pb = [100 * np.mean(pred[y == k] == k) for k in range(len(batches))]
    print(
        f"  {label:52s} {100 * np.mean(pred == y):4.0f}%  (balanced {np.mean(pb):4.0f}%;  "
        + ", ".join(f"{b} {p:.0f}%" for b, p in zip(batches, pb))
        + ")"
    )
    return P


print("\n2. STRATEGIES (single image, unseen locations)")
for m in base:
    report(f"single method: {names[m]}", P_raw[m])
report("average of all methods (raw)", softmax(np.mean([LP[m] for m in base], 0)))
report("average of all methods (calibrated)", np.mean([P_cal[m] for m in base], 0))


def most_confident(Ps):
    stack = np.stack([Ps[m] for m in base])  # methods x images x batches
    pick = stack.max(2).argmax(0)  # most confident method per image
    chosen = stack[pick, np.arange(stack.shape[1])]
    counts = np.bincount(pick, minlength=len(base))
    return chosen, counts


for label, Ps in (("raw", P_raw), ("calibrated", P_cal)):
    chosen, counts = most_confident(Ps)
    report(f"pick the most confident method ({label})", chosen)
    print("      chosen: " + ", ".join(f"{names[m].split(' (')[0]} {c}x" for m, c in zip(base, counts)))

print("\n3. SELECTIVE PREDICTION: answer only the most confident images (calibrated average)")
P = np.mean([P_cal[m] for m in base], 0)
conf, right = P.max(1), P.argmax(1) == y
order = np.argsort(-conf)
for cover in (1.0, 0.75, 0.5, 0.33, 0.2):
    k = max(1, int(round(cover * len(order))))
    sel = order[:k]
    per_b = ", ".join(f"{b} {np.sum(y[sel] == i)}" for i, b in enumerate(batches))
    print(
        f"  answer {100 * cover:3.0f}% of images ({k:2d}): {100 * right[sel].mean():4.0f}% correct"
        f"  [confidence >= {100 * conf[sel].min():.0f}%; answered per batch: {per_b}]"
    )
