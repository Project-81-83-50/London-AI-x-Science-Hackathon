"""Three-class intensity segmentation and its systematic sensitivity (threshold nudges, local thresholds)."""

import numpy as np
from scipy import ndimage
from skimage import filters, transform

from .constants import PHASES


def segment_intensity_classes(img: np.ndarray, smooth: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split a detector image into three intensity classes; material meaning is unvalidated."""
    sm = ndimage.gaussian_filter(img, smooth)
    thresholds = filters.threshold_multiotsu(sm[::4, ::4], classes=3)
    return np.digitize(sm, thresholds), thresholds, sm


def segmentation_sensitivity(
    sm: np.ndarray, thresholds: np.ndarray, frac: float = 0.02
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Phase-fraction range when each threshold moves by +-frac of the grey-level range."""
    lo, hi = np.percentile(sm[::4, ::4], [1, 99])
    d = frac * (hi - lo)
    fractions = []
    for s0 in (-d, d):
        for s1 in (-d, d):
            labels = np.digitize(sm, thresholds + np.array([s0, s1]))
            fractions.append(np.bincount(labels.ravel(), minlength=len(PHASES)) / labels.size)
    fractions = np.array(fractions)
    return fractions.min(axis=0), fractions.max(axis=0), fractions


def local_segmentation_fractions(
    sm: np.ndarray,
    global_t: np.ndarray,
    labels: np.ndarray,
    tile: int | None = None,
    max_shift: float = 0.15,
    min_class: float = 0.02,
) -> tuple[np.ndarray, int, int]:
    """Phase fractions with thresholds that follow the local grey level of each phase.

    On a rough or unevenly lit surface a phase's grey level drifts across the image. Per
    tile we measure how far each phase's mean grey level sits from its global mean and
    move each threshold by the average drift of the two phases it separates (a
    proportion-independent measure, unlike re-running Otsu per tile). The phi difference
    between local and global thresholds is the roughness/shading part of the
    segmentation error. A phase only counts in a tile if it covers >= 2% of it, and a
    shift is only applied if it stays within 15% of the grey range."""
    h, w = sm.shape
    tile = tile or int(np.clip(min(h, w) // 4, 128, 512))
    lo, hi = np.percentile(sm[::4, ::4], [1, 99])
    ny, nx = max(1, round(h / tile)), max(1, round(w / tile))
    ys, xs = np.linspace(0, h, ny + 1).astype(int), np.linspace(0, w, nx + 1).astype(int)
    global_t = np.asarray(global_t, np.float32)
    lab_s, sm_s = labels[::2, ::2], sm[::2, ::2]
    global_means = np.array([sm_s[lab_s == k].mean() if (lab_s == k).any() else np.nan for k in range(len(PHASES))])
    grid = np.tile(global_t, (ny, nx, 1))
    refit = 0
    for i in range(ny):
        for j in range(nx):
            block = (slice(ys[i], ys[i + 1]), slice(xs[j], xs[j + 1]))
            lb, vb = labels[block][::2, ::2].ravel(), sm[block][::2, ::2].ravel()
            frac = np.bincount(lb, minlength=len(PHASES)) / lb.size
            drift = np.array(
                [vb[lb == k].mean() - global_means[k] if frac[k] >= min_class else np.nan for k in range(len(PHASES))]
            )
            moved = False
            for t in range(len(global_t)):
                shift = np.nanmean(drift[t : t + 2]) if not np.all(np.isnan(drift[t : t + 2])) else np.nan
                if np.isfinite(shift) and abs(shift) <= max_shift * (hi - lo):
                    grid[i, j, t] = global_t[t] + shift
                    moved = True
            refit += moved
    local = np.zeros(sm.shape, np.uint8)
    for k in range(grid.shape[-1]):
        tmap = transform.resize(grid[..., k], (h, w), order=1, preserve_range=True, anti_aliasing=False)
        local += sm >= tmap.astype(np.float32)
    return np.bincount(local.ravel(), minlength=len(PHASES)) / local.size, refit, ny * nx
