"""
Scratch: the first classifier's tile texture features (brightness-independent), recomputed
for the method comparison. Image binned 2x (50 nm/px), 256 x 256 tiles (12.8 um):
radial power spectrum, edge statistics, local binary patterns, grey-level co-occurrence
texture (rank-quantised), 3-class fractions.
"""

import sys
from pathlib import Path

import numpy as np
from scipy import fft, ndimage
from skimage import feature, filters

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

from batch_classifier import ROOT, index, load_u8  # noqa: E402

OUT = PROJECT_DIR / "out" / "classifier" / "texture_features.npz"
BIN, TILE = 2, 256
EDGES = np.geomspace(1 / 128, 0.5, 9)
_R = np.hypot(fft.fftfreq(TILE)[:, None], fft.fftfreq(TILE)[None, :])
_BINS = np.digitize(_R, EDGES)
_HANN = np.outer(np.hanning(TILE), np.hanning(TILE))


def tile_features(t):
    z = (t - t.mean()) / (t.std() + 1e-6)
    p = np.abs(fft.fft2(z * _HANN)) ** 2
    spectrum = np.log([p[_BINS == k].mean() for k in range(1, len(EDGES))])
    spectrum -= spectrum.mean()
    g = filters.sobel(ndimage.gaussian_filter(z, 1.0))
    u8 = np.clip(t * 255, 0, 255).astype(np.uint8)
    lbp1 = np.bincount(feature.local_binary_pattern(u8, 8, 1, "uniform").astype(int).ravel(), minlength=10) / u8.size
    lbp4 = np.bincount(feature.local_binary_pattern(u8, 16, 4, "uniform").astype(int).ravel(), minlength=18) / u8.size
    q = np.searchsorted(np.quantile(t, np.linspace(0, 1, 17)[1:-1]), t).astype(np.uint8)
    glcm = feature.graycomatrix(q, [1, 4, 16], [0, np.pi / 2], levels=16, symmetric=True, normed=True)
    texture = np.concatenate(
        [feature.graycoprops(glcm, prop).mean(axis=1) for prop in ("contrast", "homogeneity", "correlation", "energy")]
    )
    sm = ndimage.gaussian_filter(t, 1.0)
    try:
        lab = np.digitize(sm, filters.threshold_multiotsu(sm, classes=3))
        phases = np.bincount(lab.ravel(), minlength=3) / lab.size
    except ValueError:
        phases = np.array([0.0, 1.0, 0.0])
    return np.concatenate([spectrum, [g.mean(), g.std(), np.percentile(g, 90)], lbp1, lbp4, texture, phases])


def main():
    rows = index(ROOT)
    X, image_of_tile = [], []
    for i, r in enumerate(rows):
        a = load_u8(r["path"]).astype(np.float32) / 255
        h, w = a.shape[0] // BIN * BIN, a.shape[1] // BIN * BIN
        a = a[:h, :w].reshape(h // BIN, BIN, w // BIN, BIN).mean(axis=(1, 3))
        ny, nx = a.shape[0] // TILE, a.shape[1] // TILE
        y0, x0 = (a.shape[0] - ny * TILE) // 2, (a.shape[1] - nx * TILE) // 2
        for yi in range(ny):
            for xi in range(nx):
                X.append(tile_features(a[y0 + yi * TILE : y0 + (yi + 1) * TILE, x0 + xi * TILE : x0 + (xi + 1) * TILE]))
                image_of_tile.append(i)
        print(f"  {i + 1}/{len(rows)} {r['batch']}/{r['path'].name}", flush=True)
    np.savez(OUT, X=np.array(X), image_of_tile=np.array(image_of_tile), paths=np.array([str(r["path"]) for r in rows]))


if __name__ == "__main__":
    main()
