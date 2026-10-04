"""
Scratch: which method best separates Batch_1 from Batch_2? (binary specialists)

Only the 14 Batch_1 / Batch_2 locations are used; each is predicted by a model trained on
the other 13. Chance = 50%. "top-3 features" picks the 3 features with the best
Batch_1-vs-Batch_2 separation INSIDE each fold (on the 13 training locations only), so the
selection cannot see the location being tested.
"""

import json
import warnings
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import batch_classifier as B

warnings.filterwarnings("ignore")
OUT = Path(__file__).parent / "out" / "classifier"
rows = B.index(B.ROOT)
batch = np.array([r["batch"] for r in rows], dtype=object)
loc = np.array([r["location"] for r in rows])
view = np.array([r["view"] for r in rows])
keep = np.isin(batch, ["Batch_1", "Batch_2"])
locs = np.unique(loc[keep])
true_loc = np.array([batch[loc == l][0] for l in locs])
CLASSES = np.array(["Batch_1", "Batch_2"], dtype=object)


def lp_of(model, X):
    p = np.clip(model.predict_proba(X), 1e-6, 1)
    return np.log(p[:, np.searchsorted(model.classes_, CLASSES)])


def image_level(X, make):
    lp = np.full((len(rows), 2), np.nan)
    for l in locs:
        for v in B.VIEWS:
            tr, te = keep & (loc != l) & (view == v), keep & (loc == l) & (view == v)
            if te.any():
                mu = np.nanmean(X[tr], 0)
                lp[te] = lp_of(make().fit(np.where(np.isfinite(X[tr]), X[tr], mu), batch[tr]),
                               np.where(np.isfinite(X[te]), X[te], mu))
    return lp


def tile_level(X, image_of_tile, make):
    lp = np.full((len(rows), 2), np.nan)
    tl, tv, tb = loc[image_of_tile], view[image_of_tile], batch[image_of_tile]
    tk = keep[image_of_tile]
    for l in locs:
        for v in B.VIEWS:
            tr = tk & (tl != l) & (tv == v)
            te = np.nonzero(keep & (loc == l) & (view == v))[0]
            if len(te):
                m = make().fit(X[tr], tb[tr])
                for i in te:
                    lp[i] = lp_of(m, X[image_of_tile == i]).mean(0)
    return lp


def tiles(name):
    d = np.load(OUT / name)
    return d["X"].astype(np.float32), d["image_of_tile"]


logistic = lambda C: (lambda: make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000)))
lda = lambda: make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))

methods = {}
Xt, it = tiles("texture_features.npz")
methods["texture tiles"] = tile_level(Xt, it, logistic(0.1))
methods["imaging fingerprint"] = image_level(B.build_features(rows), lda)
Xd, idt = tiles("deep_features.npz")
methods["ResNet-50 deep features"] = tile_level(
    Xd[:, 2048:], idt, lambda: make_pipeline(StandardScaler(), PCA(20), LogisticRegression(C=0.05, max_iter=5000)))
acf = json.loads((OUT / "noise_acf.json").read_text())
by = {}
for r in acf:
    by.setdefault((r["location"], r["view"]), []).append(r["acf"])
methods["noise autocorrelation"] = image_level(np.array([np.mean(by[(r["location"], r["view"])], 0) for r in rows]), logistic(0.3))
methods["average of the four"] = np.mean([methods[k] for k in list(methods)], axis=0)

# location-level feature tables (cross-view): exploratory fingerprint + physical descriptors
fp = {r["location"]: r for r in json.loads((OUT / "fingerprint.json").read_text())}
ds = {r["location"]: r for r in json.loads((OUT / "descriptors.json").read_text())}
table = {l: {**ds[l], **fp[l]} for l in locs}
keys = sorted({k for t in table.values() for k in t if k not in ("batch", "location")})
XL = np.array([[table[l].get(k, np.nan) for k in keys] for l in locs], float)
desc_cols = [i for i, k in enumerate(keys) if k in ds[locs[0]] and k not in ("batch", "location")]


def location_level(X, make, top_k=None):
    pred = []
    for i in range(len(locs)):
        tr = np.arange(len(locs)) != i
        mu = np.nanmean(X[tr], 0)
        Xtr, Xte = np.where(np.isfinite(X[tr]), X[tr], mu), np.where(np.isfinite(X[i:i + 1]), X[i:i + 1], mu)
        cols = np.arange(X.shape[1])
        if top_k:
            a, b = Xtr[true_loc[tr] == "Batch_1"], Xtr[true_loc[tr] == "Batch_2"]
            auc = np.array([abs(np.mean(a[:, j][:, None] > b[:, j][None, :]) - 0.5) for j in range(X.shape[1])])
            cols = np.argsort(-auc)[:top_k]
        pred.append(make().fit(Xtr[:, cols], true_loc[tr]).predict(Xte[:, cols])[0])
    return np.array(pred)


def p_value(k, n):
    return stats.binomtest(int(k), n, 0.5, alternative="greater").pvalue


print(f"{'Batch_1 vs Batch_2 specialist':38s} {'images':>7s}  {'B1 img':>6s} {'B2 img':>6s} | {'locations':>9s}  {'B1':>4s} {'B2':>4s}  p vs chance")
for name, lp in methods.items():
    pred_img = CLASSES[np.nanargmax(np.where(np.isnan(lp), -np.inf, lp), 1)]
    ok = keep & (pred_img == batch)
    pl = np.array([CLASSES[np.nansum(lp[loc == l], 0).argmax()] for l in locs])
    k = np.sum(pl == true_loc)
    print(f"{name:38s} {100 * ok.sum() / keep.sum():6.0f}%  {100 * np.mean(pred_img[batch == 'Batch_1'] == 'Batch_1'):5.0f}% "
          f"{100 * np.mean(pred_img[batch == 'Batch_2'] == 'Batch_2'):5.0f}% | {k:5d}/14  "
          f"{np.sum((pl == true_loc) & (true_loc == 'Batch_1')):2d}/7 {np.sum((pl == true_loc) & (true_loc == 'Batch_2')):2d}/7   {p_value(k, 14):.3f}")
for name, X, make, k_ in [("physical descriptors (all)", XL[:, desc_cols], lda, None),
                          ("all location features (all)", XL, lda, None),
                          ("top-3 features, chosen inside each fold", XL, lda, 3),
                          ("top-5 features, chosen inside each fold", XL, lda, 5)]:
    pl = location_level(X, make, k_)
    k = np.sum(pl == true_loc)
    print(f"{name:38s} {'-':>7s}  {'':6s} {'':6s} | {k:5d}/14  {np.sum((pl == true_loc) & (true_loc == 'Batch_1')):2d}/7 "
          f"{np.sum((pl == true_loc) & (true_loc == 'Batch_2')):2d}/7   {p_value(k, 14):.3f}")
