"""Imaging-quality metrics and preprocessing: shading flattening and curtaining / scan-line removal."""

import numpy as np
from scipy import fft, ndimage
from skimage import filters

from .constants import FULL_FFT_MAX_PX

STRIPE_LIMIT = 3.0  # stripe index above which we destripe / flag
F0 = 1 / 64  # cycles/px: structure coarser than 64 px is never touched by destriping


def _central_crop(img: np.ndarray, size: int = 2048) -> np.ndarray:
    """Central size x size crop (or the whole image if it is smaller)."""
    h, w = img.shape
    ch, cw = min(h, size), min(w, size)
    return img[(h - ch) // 2 : (h - ch) // 2 + ch, (w - cw) // 2 : (w - cw) // 2 + cw]


def separability(values: np.ndarray, thresholds: np.ndarray) -> float:
    """Otsu's eta: between-class / total grey-level variance (1 = phases perfectly separated)."""
    v = values.ravel()
    lab = np.digitize(v, thresholds)
    mu = v.mean()
    between = sum((lab == k).mean() * (v[lab == k].mean() - mu) ** 2 for k in np.unique(lab))
    return float(between / max(v.var(), 1e-12))


def stripe_index(img: np.ndarray, step: float = 0.5) -> dict[str, float]:
    """Straight-streak artefacts: FIB curtaining (any angle) and raster scan lines (horizontal).

    Straight streaks put their power in a narrow wedge of the Fourier spectrum, at right
    angles to the streaks. Index = power in a +-1 deg wedge / power 6-12 deg either side,
    over wavelengths 4-32 px; ~1 for a clean image. Particle shape anisotropy gives broad
    bumps, not narrow wedges, so it barely registers. Angle 0 = vertical streaks."""
    c = _central_crop(img)
    if min(c.shape) < 128:
        return {"curtaining": 1.0, "curtaining_angle": 0.0, "scan_lines": 1.0}
    c = (c - c.mean()) * np.outer(np.hanning(c.shape[0]), np.hanning(c.shape[1]))
    p = np.abs(fft.fftshift(fft.fft2(c))) ** 2
    fy = (np.arange(c.shape[0]) - c.shape[0] // 2) / c.shape[0]
    fx = (np.arange(c.shape[1]) - c.shape[1] // 2) / c.shape[1]
    fyy, fxx = np.meshgrid(fy, fx, indexing="ij")
    band = (np.hypot(fyy, fxx) > 1 / 32) & (np.hypot(fyy, fxx) < 1 / 4)
    ang = np.degrees(np.arctan2(fyy[band], fxx[band])) % 180
    bins = (ang / step).astype(int)
    n_bins = int(180 / step)
    order = np.argsort(bins)
    edges = np.searchsorted(bins[order], np.arange(n_bins + 1))
    pv = p[band][order]
    med = np.array(
        [np.median(pv[edges[i] : edges[i + 1]]) if edges[i + 1] > edges[i] else np.nan for i in range(n_bins)]
    )

    def wedge(a, lo, hi):
        d = np.abs((np.arange(n_bins) * step - a + 90) % 180 - 90)
        return np.nanmean(med[(d >= lo) & (d <= hi)])

    ratios = np.array([wedge(a, 0, 1) / wedge(a, 6, 12) for a in np.arange(n_bins) * step])
    angles = np.arange(n_bins) * step
    curtain = np.abs((angles - 90 + 90) % 180 - 90) > 3  # scan lines live at exactly 90 deg
    i = int(np.nanargmax(np.where(curtain, ratios, -np.inf)))
    signed = (angles[i] + 90) % 180 - 90
    return {
        "curtaining": float(ratios[i]),
        "curtaining_angle": float(signed),
        "scan_lines": float(ratios[int(90 / step)]),
    }


def noise_sigma(img: np.ndarray) -> float:
    """Immerkaer (1996) fast noise estimate: a Laplacian-difference kernel cancels smooth
    structure, leaving mostly pixel noise."""
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    r = ndimage.convolve(img, k)[1:-1, 1:-1]
    return float(np.sqrt(np.pi / 2) * np.abs(r).mean() / 6)


def image_quality(img: np.ndarray) -> dict[str, float]:
    """Imaging metrics on the resampled image (so they compare across magnifications)."""
    sub = img[::2, ::2]
    p1, p50, p99 = np.percentile(sub, [1, 50, 99])
    contrast = float(max(p99 - p1, 1e-6))
    sm = ndimage.gaussian_filter(img, 1.0)
    gx, gy = ndimage.sobel(sm, axis=1), ndimage.sobel(sm, axis=0)
    thresholds = filters.threshold_multiotsu(sm[::4, ::4], classes=3)
    q = {
        "median": float(p50),
        "contrast": contrast,
        "clipped_black": float(np.mean(sub <= 0.002)),
        "clipped_white": float(np.mean(sub >= 0.998)),
        "sharpness": float(np.percentile(np.hypot(gx, gy)[::2, ::2], 99) / contrast),
        "anisotropy": float(np.sqrt(np.mean(gx**2) / max(np.mean(gy**2), 1e-12))),
        "noise": noise_sigma(_central_crop(img, 1024)) / contrast,
        "separability": separability(sm[::4, ::4], thresholds),
    }
    q.update({f"stripes_{k}": v for k, v in stripe_index(img).items()})
    return q


def _poly_terms(y, x, degree: int) -> list:
    """Monomials y^i x^j with i + j <= degree."""
    return [y**i * x**j for i in range(degree + 1) for j in range(degree + 1 - i)]


def flatten_shading(img: np.ndarray, degree: int = 2, rows: int = 256, iterations: int = 2) -> tuple[np.ndarray, float]:
    """Remove smooth shading (charging, detector geometry, uneven tilt) as a gain AND an
    offset map. A low-order surface is fitted to the grey level of each of the two most
    abundant phases; since each phase should look the same everywhere, the two surfaces
    fix gain g(x) and offset o(x) with I = g * I_true + o. Fitting phase grey LEVELS (not
    the overall image) means real composition gradients are not flattened away.
    Returns (corrected image, shading amplitude in grey levels)."""
    h, w = img.shape
    s = max(1, h // rows)
    small = ndimage.uniform_filter(img, s)[::s, ::s] if s > 1 else img.copy()
    y = (np.arange(h, dtype=np.float32) / h)[:, None]
    x = (np.arange(w, dtype=np.float32) / w)[None, :]
    gain, offset = np.ones((h, w), np.float32), np.zeros((h, w), np.float32)
    corrected = small
    for _ in range(iterations):
        lab = np.digitize(corrected, filters.threshold_multiotsu(corrected, classes=3))
        counts = np.bincount(lab.ravel(), minlength=3)
        a_cls, b_cls = np.argsort(counts)[::-1][:2]
        surfaces, levels = [], []
        for cls in (a_cls, b_cls):
            yy, xx = np.nonzero(lab == cls)
            if len(yy) < 100:
                return img, 0.0
            design = np.stack(_poly_terms(yy * s / h, xx * s / w, degree), axis=1)
            coef, *_ = np.linalg.lstsq(design, small[yy, xx], rcond=None)
            surfaces.append(coef)
            levels.append(float(np.median(small[yy, xx])))
        if abs(levels[0] - levels[1]) < 1e-3:
            return img, 0.0
        sa = sum(np.float32(c) * t for c, t in zip(surfaces[0], _poly_terms(y, x, degree), strict=True))
        sb = sum(np.float32(c) * t for c, t in zip(surfaces[1], _poly_terms(y, x, degree), strict=True))
        gain = np.broadcast_to(np.clip((sa - sb) / (levels[0] - levels[1]), 0.5, 2.0), (h, w))
        offset = np.broadcast_to(sa - gain * levels[0], (h, w))
        # re-label on the corrected small image for the next iteration
        g_small, o_small = (
            gain[::s, ::s][: small.shape[0], : small.shape[1]],
            offset[::s, ::s][: small.shape[0], : small.shape[1]],
        )
        corrected = (small - o_small) / g_small
    out = ((img - offset) / gain).astype(np.float32)
    # grey-level drift of a phase across the image (5-95% range: polynomial corners overshoot)
    amp = float(max(np.subtract(*np.percentile(np.broadcast_to(srf, (h, w))[::s, ::s], [95, 5])) for srf in (sa, sb)))
    return out, amp


def destripe(img: np.ndarray, q: dict, width: float = 1.5) -> tuple[np.ndarray, list[str]]:
    """Notch the detected stripe lines out of the Fourier spectrum, keeping |f| < F0 intact."""
    applied = []
    lines = []
    if q["stripes_curtaining"] > STRIPE_LIMIT:
        lines.append((q["stripes_curtaining_angle"], f"curtaining ({q['stripes_curtaining_angle']:+.0f} deg)"))
    if q["stripes_scan_lines"] > STRIPE_LIMIT:
        lines.append((90.0, "horizontal scan lines"))
    if not lines or img.size > FULL_FFT_MAX_PX:
        return img, applied
    h, w = img.shape
    f = fft.rfft2(img, workers=-1)
    fy = fft.fftfreq(h).astype(np.float32)[:, None]
    fx = fft.rfftfreq(w).astype(np.float32)[None, :]
    # the notch is ~1.5 frequency bins wide, so it can go almost down to zero frequency
    # without touching real structure; only the lowest few bins (image-scale shading) are kept
    low = np.hypot(fy, fx) < 4 / min(h, w)
    mask = np.ones(f.shape, np.float32)
    for angle, label in lines:
        a = np.radians(angle)  # the streaks' power lies on the line through 0 at this angle
        d = np.abs(fy * np.cos(a) - fx * np.sin(a))
        mask *= np.where(low, 1.0, 1 - np.exp(-0.5 * (d * min(h, w) / width) ** 2))
        applied.append(label)
    return fft.irfft2(f * mask, s=img.shape, workers=-1).astype(np.float32), applied
