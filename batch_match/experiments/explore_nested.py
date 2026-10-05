"""
Scratch: nested leave-one-location-out, so that CHOOSING the best feature set / model is
part of what gets tested. For each held-out location, every candidate is scored by an inner
leave-one-out on the other 30 locations only; the inner winner then predicts the held-out one.
"""

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
m2 = json.loads((OUT / "material2.json").read_text())
locs = [r["location"] for r in m2]
y = np.array([r["batch"] for r in m2], dtype=object)
batches = np.array(["Batch_1", "Batch_2", "Batch_3"], dtype=object)
mk = [k for k in m2[0] if k not in ("batch", "location")]
XM = np.array([[r.get(k, np.nan) for k in mk] for r in m2], float)
hz = json.loads((OUT / "harmonized_features.json").read_text())["rows"]
hk = sorted(k for k in hz[0] if k != "path" and not k.startswith("_"))
bse = {Path(r["path"]).stem.split("_")[1]: r for r in hz if Path(r["path"]).stem.endswith("_BSE")}
XH = np.array([[bse[l].get(k, np.nan) for k in hk] for l in locs], float)
rows = B.index(B.ROOT)
XF_img = B.build_features(rows)
XF = np.array(
    [
        np.concatenate(
            [XF_img[[i for i, r in enumerate(rows) if r["location"] == l and r["view"] == v][0]] for v in B.VIEWS]
        )
        for l in locs
    ]
)


def lda():
    return make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))


def lr():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=5000, class_weight="balanced"))


CANDIDATES = {
    "production markers / LDA": (XM, lda),
    "production markers / logistic": (XM, lr),
    "harmonised material / LDA": (XH, lda),
    "harmonised material / logistic": (XH, lr),
    "markers + harmonised / LDA": (np.hstack([XM, XH]), lda),
    "markers + harmonised / logistic": (np.hstack([XM, XH]), lr),
    "imaging fingerprint (3 views) / LDA": (XF, lda),
    "markers + harmonised + fingerprint / LDA": (np.hstack([XM, XH, XF]), lda),
}


def fit_predict(X, make, tr, te):
    mu = np.nanmean(X[tr], 0)

    def fill(A):
        return np.where(np.isfinite(A), A, mu)

    return make().fit(fill(X[tr]), y[tr]).predict(fill(X[te]))


def balanced(pred, true):
    return np.mean([np.mean(pred[true == b] == b) for b in batches if np.any(true == b)])


n = len(locs)
plain = {
    name: np.array([fit_predict(X, make, np.arange(n) != i, [i])[0] for i in range(n)], dtype=object)
    for name, (X, make) in CANDIDATES.items()
}
print("plain leave-one-out (picking the best of these afterwards is optimistic):")
for name, p in plain.items():
    print(
        f"  {name:42s} {np.sum(p == y):2d}/31  B1 {np.sum((p == y) & (y == 'Batch_1'))}/7  B2 {np.sum((p == y) & (y == 'Batch_2'))}/7"
        f"  B3 {np.sum((p == y) & (y == 'Batch_3'))}/17  balanced {100 * balanced(p, y):3.0f}%"
    )

outer, chosen = [], []
for i in range(n):
    inner_idx = [j for j in range(n) if j != i]
    scores = {}
    for name, (X, make) in CANDIDATES.items():
        p = np.array(
            [fit_predict(X, make, np.array([k for k in inner_idx if k != j]), [j])[0] for j in inner_idx], dtype=object
        )
        scores[name] = balanced(p, y[inner_idx])
    best = max(scores, key=scores.get)
    chosen.append(best)
    X, make = CANDIDATES[best]
    outer.append(fit_predict(X, make, np.array(inner_idx), [i])[0])
    print(f"  outer {i + 1:2d}/31 {locs[i]} ({y[i]}): inner winner {best} -> {outer[-1]}", flush=True)
outer = np.array(outer, dtype=object)
print(
    f"\nNESTED (honest, includes choosing the method): {np.sum(outer == y)}/31  "
    + "  ".join(f"{b[-1]}: {np.sum((outer == y) & (y == b))}/{np.sum(y == b)}" for b in batches)
    + f"  balanced {100 * balanced(outer, y):.0f}%"
)
print("methods chosen:", {c: chosen.count(c) for c in set(chosen)})
