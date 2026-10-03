"""
Scratch: acquisition / sample-preparation fingerprint per image, at full resolution.

  noise level per phase (Immerkaer residual inside eroded phase interiors), relative
  to the image's phase contrast; noise correlation along / across the scan direction
  (detector bandwidth, line integration); edge sharpness and directionality (focus,
  astigmatism, drift); stripe strength (ion-milling curtaining); grey-level histogram
  comb (post-acquisition contrast stretching); phase contrast ratios.
"""

import json
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage, stats

import GET4
from batch_classifier import ROOT, index

OUT = Path(__file__).parent / "out" / "classifier"
K_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
LAGS = [(0, 1), (0, 2), (0, 3), (1, 0), (2, 0), (1, 1)]


def load_u8(path):
    a = tifffile.imread(path)
    return (a[..., 0] if a.ndim == 3 else a)[:, 8:-8]


def fingerprint(u8, labels, prefix):
    img = u8.astype(np.float32)
    d = {}
    interior = [ndimage.binary_erosion(labels == k, iterations=4) for k in range(3)]
    med = [np.median(img[m]) if m.sum() > 1000 else np.nan for m in interior]
    contrast = max(abs(med[1] - med[0]), 1.0)
    spread = max(np.percentile(img[::4, ::4], 99) - np.percentile(img[::4, ::4], 1), 1.0)
    d[f"{prefix}_contrast_over_spread"] = contrast / spread

    resid = ndimage.convolve(img, K_IMMERKAER)
    for k, name in enumerate(["pore", "graphite", "bright"]):
        m = interior[k]
        if m.sum() < 1000:
            continue
        sd = np.sqrt(np.pi / 2) * np.abs(resid[m]).mean() / 6
        d[f"{prefix}_noise_{name}"] = sd / spread
        d[f"{prefix}_noise_{name}_rel"] = sd / max(med[k], 1.0)  # ~ shot-noise SNR
    if f"{prefix}_noise_graphite" in d and f"{prefix}_noise_pore" in d:
        d[f"{prefix}_nlf_slope"] = d[f"{prefix}_noise_graphite"] / max(d[f"{prefix}_noise_pore"], 1e-6)

    # noise correlation in graphite interior: high-pass residual, normalised autocorrelation at small lags
    m = interior[1]
    hp = img - ndimage.uniform_filter(img, 7)
    base = (hp[m] ** 2).mean()
    for dy, dx in LAGS:
        mm = m[dy:, dx:] & m[: m.shape[0] - dy, : m.shape[1] - dx]
        a, b = hp[dy:, dx:][mm], hp[: hp.shape[0] - dy, : hp.shape[1] - dx][mm]
        d[f"{prefix}_ncorr_{dy}{dx}"] = float((a * b).mean() / base)

    # edges: sharpness and direction (focus / astigmatism / drift)
    sm = ndimage.gaussian_filter(img, 0.7)
    gx, gy = ndimage.sobel(sm, 1), ndimage.sobel(sm, 0)
    g = np.hypot(gx, gy)
    d[f"{prefix}_sharp"] = float(np.percentile(g[::2, ::2], 99) / spread)
    d[f"{prefix}_grad_aniso"] = float(np.sqrt((gx ** 2).mean() / max((gy ** 2).mean(), 1e-9)))
    q = GET4.stripe_index(img / 255.0)
    d[f"{prefix}_curtain"] = q["curtaining"]
    d[f"{prefix}_scanlines"] = q["scan_lines"]

    # histogram comb: empty grey levels inside the occupied range (contrast stretching after acquisition)
    h = np.bincount(u8.ravel(), minlength=256)
    lo, hi = np.searchsorted(np.cumsum(h) / h.sum(), [0.01, 0.99])
    d[f"{prefix}_empty_levels"] = float(np.mean(h[lo: hi + 1] == 0))
    d[f"{prefix}_clip_low"] = float(h[0] / h.sum())
    d[f"{prefix}_clip_high"] = float(h[255] / h.sum())
    # contrast ratios between phases
    if np.all(np.isfinite(med)):
        d[f"{prefix}_bright_ratio"] = (med[2] - med[0]) / contrast
    return d


def main():
    rows = index(ROOT)
    locs = {}
    for r in rows:
        locs.setdefault((r["batch"], r["location"]), {})[r["view"]] = r["path"]
    table = []
    for (batch, loc), views in sorted(locs.items()):
        bse = load_u8(views["BSE"])
        labels, _, _ = GET4.segment_bse(bse.astype(np.float32) / 255, smooth=2.0)
        d = {"batch": batch, "location": loc}
        for view, path in views.items():
            u8 = bse if view == "BSE" else load_u8(path)[: labels.shape[0], : labels.shape[1]]
            d.update(fingerprint(u8, labels, view))
        table.append(d)
        print(f"  {batch} {loc}", flush=True)
    (OUT / "fingerprint.json").write_text(json.dumps(table, indent=1, default=float))

    keys = [k for k in table[0] if k not in ("batch", "location")]
    batches = sorted({t["batch"] for t in table})

    def auc(a, b):
        u = np.mean(a[:, None] > b[None, :]) + 0.5 * np.mean(a[:, None] == b[None, :])
        return max(u, 1 - u)
    res = []
    for k in keys:
        vals = {b: np.array([t.get(k, np.nan) for t in table if t["batch"] == b], float) for b in batches}
        vals = {b: v[np.isfinite(v)] for b, v in vals.items()}
        if any(len(v) < 3 for v in vals.values()):
            continue
        res.append((stats.kruskal(*vals.values()).pvalue, k, vals))
    print(f"\n{'fingerprint':28s} " + " ".join(f"{b:>17s}" for b in batches) + "   KW p    AUC 1v2 1v3 2v3")
    for p, k, v in sorted(res, key=lambda x: x[0]):
        b1, b2, b3 = (v[b] for b in batches)
        print(f"{k:28s} " + " ".join(f"{np.median(x):9.4f}+-{stats.iqr(x) / 2:<6.4f}" for x in (b1, b2, b3))
              + f"  {p:7.5f}   {auc(b1, b2):.2f} {auc(b1, b3):.2f} {auc(b2, b3):.2f}")


if __name__ == "__main__":
    main()
