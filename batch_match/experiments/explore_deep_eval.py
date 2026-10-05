"""Scratch: leave-one-location-out accuracy of the ResNet-50 tile features."""

import sys
import warnings
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

from batch_classifier import ROOT, VIEWS, index  # noqa: E402

warnings.filterwarnings("ignore")
d = np.load(PROJECT_DIR / "out" / "classifier" / "deep_features.npz")
X, image_of_tile = d["X"].astype(np.float32), d["image_of_tile"]
rows = index(ROOT)
assert [str(r["path"]) for r in rows] == list(d["paths"])
batch = np.array([r["batch"] for r in rows])
loc = np.array([r["location"] for r in rows])
view = np.array([r["view"] for r in rows])
batches = np.unique(batch)
BLOCKS = {"stage3 mean": slice(0, 1024), "stage3 mean+sd": slice(0, 2048), "final pool": slice(2048, 4096)}


def report(name, image_lp):
    pred = batches[image_lp.argmax(1)]
    per_view = " ".join(f"{v} {100 * np.mean(pred[view == v] == batch[view == v]):.0f}%" for v in VIEWS)
    locs = np.unique(loc)
    lp_loc = {l: image_lp[loc == l].sum(0) for l in locs}
    pl = np.array([batches[lp_loc[l].argmax()] for l in locs])
    tl = np.array([batch[loc == l][0] for l in locs])
    bal = np.mean([np.mean(pl[tl == b] == b) for b in batches])
    wrong = " ".join(f"{l}({t[-1]}->{p[-1]})" for l, t, p in zip(locs, tl, pl) if t != p)
    print(
        f"{name:34s} image {100 * np.mean(pred == batch):5.1f}% [{per_view}]  location {100 * np.mean(pl == tl):5.1f}% "
        f"(bal {100 * bal:5.1f}%)  wrong: {wrong}"
    )


for bname, cols in BLOCKS.items():
    img_feat = np.array([X[image_of_tile == i, cols].mean(0) for i in range(len(rows))])
    # (a) image-level: one vector per image, PCA + logistic, per view
    lp = np.zeros((len(rows), len(batches)))
    for l in np.unique(loc):
        for v in VIEWS:
            tr, te = (loc != l) & (view == v), (loc == l) & (view == v)
            if not te.any():
                continue
            m = make_pipeline(
                StandardScaler(), PCA(10), LogisticRegression(C=1.0, max_iter=5000, class_weight="balanced")
            )
            m.fit(img_feat[tr], batch[tr])
            lp[te] = np.log(np.clip(m.predict_proba(img_feat[te]), 1e-6, 1))
    report(f"{bname} / image-level PCA+LR", lp)
    # (b) tile-level: logistic on tiles, image = mean tile log-probability
    lp = np.zeros((len(rows), len(batches)))
    tile_loc, tile_view, tile_batch = loc[image_of_tile], view[image_of_tile], batch[image_of_tile]
    for l in np.unique(loc):
        for v in VIEWS:
            tr = (tile_loc != l) & (tile_view == v)
            te_imgs = np.nonzero((loc == l) & (view == v))[0]
            if not len(te_imgs):
                continue
            m = make_pipeline(
                StandardScaler(), PCA(30), LogisticRegression(C=0.05, max_iter=5000, class_weight="balanced")
            )
            m.fit(X[tr, cols], tile_batch[tr])
            for i in te_imgs:
                lp[i] = np.log(np.clip(m.predict_proba(X[image_of_tile == i, cols]), 1e-6, 1)).mean(0)
    report(f"{bname} / tile-level PCA+LR", lp)
