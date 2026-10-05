"""Pore (0) / graphite (1) / bright phase (2) segmentation of a grey SEM view: smooth shading fitted to the
graphite phase is removed, then 3-class Otsu thresholds and a 3x3 median clean-up."""

import numpy as np
from scipy import ndimage
from skimage import filters


def poly_surface(shape: tuple[int, int], ys, xs, values, degree: int = 2) -> np.ndarray:
    """Least-squares low-order surface through sampled grey values."""
    h, w = shape

    def terms(y, x):
        y, x = y / h - 0.5, x / w - 0.5
        return np.stack([y**i * x**j for i in range(degree + 1) for j in range(degree + 1 - i)], -1)

    coef, *_ = np.linalg.lstsq(terms(ys, xs), values, rcond=None)
    gy, gx = np.mgrid[0:h, 0:w]
    return (terms(gy.astype(np.float32), gx.astype(np.float32)) @ coef).astype(np.float32)


def segment(img: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    """Pore (0) / graphite (1) / bright (2). Smooth shading is fitted to the graphite (majority)
    phase only and removed, so a real composition gradient is not flattened away."""
    sm = ndimage.gaussian_filter(img, 1.0)
    t = filters.threshold_multiotsu(sm[::4, ::4], classes=3)
    labels = np.digitize(sm, t)
    ys, xs = np.nonzero(labels[::8, ::8] == 1)
    surface = poly_surface(sm.shape, ys * 8.0, xs * 8.0, sm[::8, ::8][ys, xs])
    p1, p99 = np.percentile(sm[::4, ::4], [1, 99])
    shading = float(np.ptp(surface) / max(p99 - p1, 1e-6))
    sm = sm - (surface - np.median(surface))
    t = filters.threshold_multiotsu(sm[::4, ::4], classes=3)
    labels = ndimage.median_filter(np.digitize(sm, t).astype(np.uint8), size=3)
    sub = sm[::4, ::4]
    cls = np.digitize(sub, t)
    between = sum((cls == k).mean() * (sub[cls == k].mean() - sub.mean()) ** 2 for k in range(3) if (cls == k).any())
    quality = {
        "shading": shading,
        "separability": float(between / max(sub.var(), 1e-12)),
        "clipped_black": float((img <= 0.002).mean()),
        "clipped_white": float((img >= 0.998).mean()),
    }
    return labels, quality
