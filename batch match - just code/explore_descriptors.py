"""
Scratch: physically meaningful per-location descriptors, to find what separates the batches.

BSE is segmented (GET4 pipeline: shading flattened, 3 phases). Because the three views of
a location are pixel-registered, the BSE phase map is also used to read the SE and InLens
signal of each phase (a per-phase "detector spectrum").
"""

import json
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage, stats
from skimage import measure, morphology

import GET4
from batch_classifier import ROOT, index

BIN = 2
OUT = Path(__file__).parent / "out" / "classifier"


def grey(path):
    a = tifffile.imread(path)
    a = (a[..., 0] if a.ndim == 3 else a).astype(np.float32) / 255
    a = a[:, 8:-8]  # stitching edge columns
    h, w = a.shape[0] // BIN * BIN, a.shape[1] // BIN * BIN
    return a[:h, :w].reshape(h // BIN, BIN, w // BIN, BIN).mean(axis=(1, 3))


def chord_lengths(mask, axis):
    """Mean length of runs of True along an axis (stereology: mean chord length)."""
    m = mask if axis == 1 else mask.T
    d = np.diff(np.pad(m.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    starts, ends = np.nonzero(d == 1), np.nonzero(d == -1)
    runs = ends[1] - starts[1]
    return runs


def particle_stats(mask, prefix, min_area=20):
    lab = measure.label(morphology.binary_opening(mask, morphology.disk(1)))
    props = [p for p in measure.regionprops(lab) if p.area >= min_area]
    if not props:
        return {}
    area = np.array([p.area for p in props], float)
    eqd = np.sqrt(4 * area / np.pi) * BIN * 0.025  # um
    ecc = np.array([p.eccentricity for p in props])
    sol = np.array([p.solidity for p in props])
    orient = np.array([p.orientation for p in props])
    w = area / area.sum()
    return {f"{prefix}_density": len(props) / mask.size * 1e6,
            f"{prefix}_d50": float(np.median(eqd)),
            f"{prefix}_d90": float(np.percentile(eqd, 90)),
            f"{prefix}_dvol": float((w * eqd).sum()),  # area-weighted size
            f"{prefix}_ecc": float((w * ecc).sum()),
            f"{prefix}_solidity": float((w * sol).sum()),
            f"{prefix}_horiz": float((w * np.abs(np.cos(orient))).sum())}


def location_descriptors(views):
    bse = grey(views["BSE"])
    flat, _ = GET4.flatten_shading(bse)
    labels, thr, sm = GET4.segment_bse(flat)
    d = {}
    fr = np.bincount(labels.ravel(), minlength=3) / labels.size
    d.update({"phi_pore": fr[0], "phi_graphite": fr[1], "phi_bright": fr[2]})
    # BSE contrast physics: grey level of each phase relative to pore and graphite (gain/offset cancel)
    med = [np.median(flat[labels == k]) for k in range(3)]
    d["bse_bright_ratio"] = (med[2] - med[0]) / (med[1] - med[0])
    d["bse_bright_sd"] = float(np.std(flat[labels == 2]) / (med[1] - med[0]))
    d["bse_graphite_sd"] = float(np.std(flat[labels == 1]) / (med[1] - med[0]))
    for k, name in enumerate(["pore", "graphite", "bright"]):
        for axis, ax in ((1, "x"), (0, "y")):
            runs = chord_lengths(labels == k, axis)
            d[f"chord_{name}_{ax}"] = float(runs.mean()) * BIN * 0.025 if len(runs) else 0.0
    d.update(particle_stats(labels == 2, "bright"))
    d.update(particle_stats(labels == 0, "pore", min_area=10))
    # cross-detector signature of each BSE phase
    core = [ndimage.binary_erosion(labels == k, iterations=2) for k in range(3)]
    for view in ("SE", "InLens"):
        if view not in views:
            continue
        g = grey(views[view])[: labels.shape[0], : labels.shape[1]]
        m = [np.median(g[c]) if c.any() else np.nan for c in core]
        spread = np.percentile(g, 99) - np.percentile(g, 1)
        d[f"{view}_bright_vs_graphite"] = (m[2] - m[1]) / spread
        d[f"{view}_pore_vs_graphite"] = (m[0] - m[1]) / spread
        d[f"{view}_graphite_sd"] = float(np.std(g[core[1]]) / spread)
        # edges: SE/InLens edge brightness at graphite boundaries (topography / charging)
        edge = (labels == 1) & ~ndimage.binary_erosion(labels == 1, iterations=1)
        d[f"{view}_edge_vs_graphite"] = (np.median(g[edge]) - m[1]) / spread
    return d


def main():
    rows = index(ROOT)
    locs = {}
    for r in rows:
        locs.setdefault((r["batch"], r["location"]), {})[r["view"]] = r["path"]
    table = []
    for (batch, loc), views in sorted(locs.items()):
        d = location_descriptors(views)
        d.update(batch=batch, location=loc)
        table.append(d)
        print(f"  {batch} {loc}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "descriptors.json").write_text(json.dumps(table, indent=1, default=float))

    keys = [k for k in table[0] if k not in ("batch", "location")]
    batches = sorted({t["batch"] for t in table})
    print(f"\n{'descriptor':28s} " + " ".join(f"{b:>16s}" for b in batches) + "   KW p    AUC 1v2  AUC 1v3  AUC 2v3")
    res = []
    for k in keys:
        vals = {b: np.array([t.get(k, np.nan) for t in table if t["batch"] == b], float) for b in batches}
        vals = {b: v[np.isfinite(v)] for b, v in vals.items()}
        if any(len(v) < 3 for v in vals.values()):
            continue
        p = stats.kruskal(*vals.values()).pvalue

        def auc(a, b):
            return max(np.mean(a[:, None] > b[None, :]) + 0.5 * np.mean(a[:, None] == b[None, :]),
                       1 - np.mean(a[:, None] > b[None, :]) - 0.5 * np.mean(a[:, None] == b[None, :]))
        res.append((p, k, vals, auc(vals[batches[0]], vals[batches[1]]), auc(vals[batches[0]], vals[batches[2]]),
                    auc(vals[batches[1]], vals[batches[2]])))
    for p, k, vals, a12, a13, a23 in sorted(res, key=lambda x: x[0]):
        print(f"{k:28s} " + " ".join(f"{np.median(v):8.3f}+-{stats.iqr(v) / 2:<6.3f}" for v in vals.values())
              + f"  {p:6.4f}   {a12:.2f}     {a13:.2f}     {a23:.2f}")


if __name__ == "__main__":
    main()
