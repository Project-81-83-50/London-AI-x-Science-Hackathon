"""Scratch: screen the production-step markers and classify locations with them."""

import json
import warnings
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parents[1] / "out" / "classifier"  # batch_match/out/classifier
m2 = json.loads((OUT / "material2.json").read_text())
locs = [r["location"] for r in m2]
y = np.array([r["batch"] for r in m2], dtype=object)
keys = [k for k in m2[0] if k not in ("batch", "location")]
X = np.array([[r.get(k, np.nan) for k in keys] for r in m2], float)
batches = np.array(["Batch_1", "Batch_2", "Batch_3"], dtype=object)
session_b = {"rxax5ozo"} | {l for l, b in zip(locs, y) if b == "Batch_3" and l not in ("cfe5vt7s", "pl8uabbv")}


def auc(a, b):
    u = np.mean(a[:, None] > b[None, :]) + 0.5 * np.mean(a[:, None] == b[None, :])
    return max(u, 1 - u)


def robust_z(v, group):
    x = X[group][:, j]
    x = x[np.isfinite(x)]
    return (v - np.median(x)) / (1.4826 * np.median(np.abs(x - np.median(x))) + 1e-9)


print(
    f"{'marker':30s} {'Batch_1':>8s} {'Batch_2':>8s} {'Batch_3':>8s}  KW p   AUC 2-vs-rest 1v2  | follows batch in crossovers (rxax, cfe5, pl8u)"
)
rows = []
idx = {l: i for i, l in enumerate(locs)}
for j, k in enumerate(keys):
    v = X[:, j]
    g = [v[(y == b) & np.isfinite(v)] for b in batches]
    if any(len(x) < 3 for x in g):
        continue
    p = stats.kruskal(*g).pvalue
    a2 = auc(v[(y == "Batch_2") & np.isfinite(v)], v[(y != "Batch_2") & np.isfinite(v)])
    a12 = auc(g[0], g[1])
    sa = np.array([l not in session_b for l in locs])
    fb = [
        abs(robust_z(v[idx["rxax5ozo"]], (y == "Batch_3") & ~sa))
        - abs(robust_z(v[idx["rxax5ozo"]], (y == "Batch_2") & sa))
    ]
    for l in ("cfe5vt7s", "pl8uabbv"):
        fb.append(abs(robust_z(v[idx[l]], (y != "Batch_3") & sa)) - abs(robust_z(v[idx[l]], (y == "Batch_3") & ~sa)))
    rows.append((p, k, g, a2, a12, fb))
for p, k, g, a2, a12, fb in sorted(rows):
    print(
        f"{k:30s} "
        + " ".join(f"{np.median(x):8.4f}" for x in g)
        + f"  {p:5.3f}  {a2:5.2f}      {a12:4.2f}  | "
        + " ".join(f"{x:+5.1f}" for x in fb)
    )

# location-level classification (leave one location out)
hz = json.loads((OUT / "harmonized_features.json").read_text())["rows"]
hz_keys = sorted(k for k in hz[0] if k != "path" and not k.startswith("_"))
bse = {Path(r["path"]).stem.split("_")[1]: r for r in hz if Path(r["path"]).stem.endswith("_BSE")}
XH = np.array([[bse[l].get(k, np.nan) for k in hz_keys] for l in locs], float)


def lda():
    return make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))


def lr():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=5000, class_weight="balanced"))


def loo(Xm, make, labels=y, classes=batches):
    pred = []
    for i in range(len(locs)):
        tr = np.arange(len(locs)) != i
        mu = np.nanmean(Xm[tr], 0)
        m = make().fit(np.where(np.isfinite(Xm[tr]), Xm[tr], mu), labels[tr])
        pred.append(m.predict(np.where(np.isfinite(Xm[i : i + 1]), Xm[i : i + 1], mu))[0])
    return np.array(pred, dtype=object)


print()
for name, Xm in (
    ("production-step markers", X),
    ("harmonised BSE material features", XH),
    ("both", np.hstack([X, XH])),
):
    for mname, make in (("LDA", lda), ("logistic", lr)):
        pr = loo(Xm, make)
        pb = [np.sum((pr == b) & (y == b)) for b in batches]
        cross = " ".join(f"{l[:4]}->{pr[idx[l]][-1]}" for l in ("rxax5ozo", "cfe5vt7s", "pl8uabbv"))
        print(
            f"{name:34s} {mname:8s} locations {np.sum(pr == y):2d}/31  B1 {pb[0]}/7  B2 {pb[1]}/7  B3 {pb[2]}/17  "
            f"balanced {100 * np.mean([pb[0] / 7, pb[1] / 7, pb[2] / 17]):3.0f}%   crossovers: {cross}"
        )
