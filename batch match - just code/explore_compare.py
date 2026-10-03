"""
Scratch: every method under the same leave-one-location-out test, broken down by view and
by batch. Each method gives image-level log-probabilities; a location combines its views.
The ensemble is a pre-specified equal-weight average of the image-level log-probabilities.
"""

import json
import warnings
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import batch_classifier as B

warnings.filterwarnings("ignore")
OUT = Path(__file__).parent / "out" / "classifier"
rows = B.index(B.ROOT)
paths = [str(r["path"]) for r in rows]
batches = np.array(sorted({r["batch"] for r in rows}), dtype=object)
batch = np.array([r["batch"] for r in rows], dtype=object)
loc = np.array([r["location"] for r in rows])
view = np.array([r["view"] for r in rows])


def normalise(lp):
    return lp - np.log(np.exp(lp - lp.max(1, keepdims=True)).sum(1, keepdims=True)) - lp.max(1, keepdims=True)


def proba(model, X):
    p = np.full((len(X), len(batches)), 1e-6)
    p[:, np.searchsorted(batches, model.classes_)] = np.clip(model.predict_proba(X), 1e-6, 1)
    return np.log(p)


def image_level(X, make):
    """One feature vector per image; one model per view."""
    lp = np.zeros((len(rows), len(batches)))
    for l in np.unique(loc):
        for v in B.VIEWS:
            tr, te = (loc != l) & (view == v), (loc == l) & (view == v)
            if te.any():
                lp[te] = proba(make().fit(X[tr], batch[tr]), X[te])
    return normalise(lp)


def tile_level(X, image_of_tile, make):
    """Model trained on tiles; an image = mean tile log-probability."""
    lp = np.zeros((len(rows), len(batches)))
    tl, tv, tb = loc[image_of_tile], view[image_of_tile], batch[image_of_tile]
    for l in np.unique(loc):
        for v in B.VIEWS:
            tr = (tl != l) & (tv == v)
            te = np.nonzero((loc == l) & (view == v))[0]
            if len(te):
                m = make().fit(X[tr], tb[tr])
                for i in te:
                    lp[i] = proba(m, X[image_of_tile == i]).mean(0)
    return normalise(lp)


def load_tiles(name):
    d = np.load(OUT / name)
    assert list(d["paths"]) == paths
    return d["X"].astype(np.float32), d["image_of_tile"]


methods = {}
Xt, it = load_tiles("texture_features.npz")
methods["texture tiles (LBP, GLCM, spectrum)"] = tile_level(
    Xt, it, lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=5000)))
print("  texture done", flush=True)

Xf = B.build_features(rows)
means = np.nanmean(Xf, 0)
Xf = np.where(np.isfinite(Xf), Xf, means)
methods["imaging fingerprint (LDA)"] = image_level(Xf, B.make_model)
print("  fingerprint done", flush=True)

Xd, idt = load_tiles("deep_features.npz")
methods["ResNet-50 deep features"] = tile_level(
    Xd[:, 2048:], idt, lambda: make_pipeline(StandardScaler(), PCA(30), LogisticRegression(C=0.05, class_weight="balanced", max_iter=5000)))
print("  deep done", flush=True)

acf = json.loads((OUT / "noise_acf.json").read_text())
by_img = {}
for r in acf:
    by_img.setdefault((r["location"], r["view"]), []).append(r["acf"])
Xa = np.array([np.mean(by_img[(r["location"], r["view"])], axis=0) for r in rows])
methods["noise autocorrelation"] = image_level(
    Xa, lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, class_weight="balanced", max_iter=5000)))

core = ["texture tiles (LBP, GLCM, spectrum)", "imaging fingerprint (LDA)", "ResNet-50 deep features"]
methods["ENSEMBLE: texture + fingerprint + deep"] = normalise(np.mean([methods[k] for k in core], axis=0))
methods["ENSEMBLE: all four"] = normalise(np.mean(list(methods.values())[:4], axis=0))

# physical descriptors need all three views of a location: location level only
ds = {r["location"]: r for r in json.loads((OUT / "descriptors.json").read_text())}
locs = np.unique(loc)
true_loc = np.array([batch[loc == l][0] for l in locs])
keys = sorted(k for k in ds[locs[0]] if k not in ("batch", "location"))
Xp = np.array([[ds[l].get(k, np.nan) for k in keys] for l in locs], float)
Xp = np.where(np.isfinite(Xp), Xp, np.nanmean(Xp, 0))
pred_phys = np.array([make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))
                      .fit(Xp[np.arange(len(locs)) != i], true_loc[np.arange(len(locs)) != i]).predict(Xp[i:i + 1])[0]
                      for i in range(len(locs))])

results = {}
print(f"\n{'SINGLE IMAGE accuracy':40s} {'BSE':>5s} {'SE':>5s} {'InLens':>6s} | {'Batch_1':>7s} {'Batch_2':>7s} {'Batch_3':>7s} | {'all':>5s} {'bal.':>5s}")
for name, lp in methods.items():
    pred = batches[lp.argmax(1)]
    pv = [100 * np.mean(pred[view == v] == batch[view == v]) for v in B.VIEWS]
    pb = [100 * np.mean(pred[batch == b] == b) for b in batches]
    results[name] = {"views": pv, "batches": pb}
    print(f"{name:40s} " + " ".join(f"{x:4.0f}%" for x in pv[:2]) + f" {pv[2]:5.0f}% | "
          + " ".join(f"{x:6.0f}%" for x in pb) + f" | {100 * np.mean(pred == batch):4.0f}% {np.mean(pb):4.0f}%")

print(f"\n{'LOCATION accuracy (3 views combined)':40s} {'Batch_1':>7s} {'Batch_2':>7s} {'Batch_3':>7s} | {'all':>5s} {'bal.':>5s}")
for name, lp in list(methods.items()) + [("physical descriptors only", None)]:
    if lp is None:
        pl = pred_phys
    else:
        pl = np.array([batches[lp[loc == l].sum(0).argmax()] for l in locs])
    pb = [np.sum(pl[true_loc == b] == b) for b in batches]
    nb = [np.sum(true_loc == b) for b in batches]
    print(f"{name:40s} " + " ".join(f"{a:4d}/{n:<2d}" for a, n in zip(pb, nb))
          + f" | {100 * np.mean(pl == true_loc):4.0f}% {100 * np.mean([a / n for a, n in zip(pb, nb)]):4.0f}%")
np.savez(OUT / "compare_logprobs.npz", names=np.array(list(methods)), lp=np.stack(list(methods.values())))
