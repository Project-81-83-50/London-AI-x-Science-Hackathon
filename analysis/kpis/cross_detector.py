"""Cross-detector KPIs: the BSE segmentation compared pixel by pixel with the same field's ETD and InLens views."""

import numpy as np
from scipy import ndimage
from skimage import registration

from .segmentation import segment


def _gradient(img: np.ndarray) -> np.ndarray:
    """Smoothed gradient magnitude, used to align views of different detector contrast."""
    g = ndimage.gaussian_filter(img, 1.5)
    return np.hypot(ndimage.sobel(g, 0), ndimage.sobel(g, 1))


def _overlap(a: np.ndarray, b: np.ndarray, shift) -> tuple[np.ndarray, np.ndarray]:
    """a and b cropped to their common area, b displaced by `shift` (dy, dx) relative to a."""
    dy, dx = (int(round(s)) for s in shift)
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:h, :w], b[:h, :w]
    ya, yb = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
    xa, xb = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
    return a[ya, xa], b[yb, xb]


def cross_detector(
    bse_img: np.ndarray, bse_labels: np.ndarray, views: dict[str, np.ndarray]
) -> tuple[dict[str, float | None], dict[str, list[int]]]:
    """Compare the BSE segmentation pixel by pixel with the same field's ETD and InLens segmentations.

    Each secondary-electron view is segmented like the BSE view (same 3 intensity classes) and aligned to it
    by phase correlation of the gradient images. The detectors see different contrast: ETD keeps pores black,
    InLens fills shallow pores in and lights up particle rims. Where they agree or disagree with BSE is
    a property of the material's surface and pores, which BSE alone does not show.

    `views` maps "ETD" / "InLens" to grey images binned to the BSE image's pixel size. Returns the
    cross-detector KPIs and the (dy, dx) alignment shift of each view.
    """
    kpis, alignment = {}, {}
    for detector, img in views.items():
        labels, _ = segment(img)
        h, w = min(bse_img.shape[0], img.shape[0]), min(bse_img.shape[1], img.shape[1])
        shift = registration.phase_cross_correlation(
            _gradient(bse_img[:h, :w]), _gradient(img[:h, :w]), normalization=None
        )[0]
        alignment[detector] = [int(round(s)) for s in shift]
        lb, lo = _overlap(bse_labels, labels, shift)
        pore, bright = lb == 0, lb == 2
        if detector == "ETD":
            dark = lo == 0
            kpis["pore_agreement_etd"] = float(2 * (pore & dark).sum() / max(pore.sum() + dark.sum(), 1))
            kpis["porosity_confirmed_etd"] = float((pore & dark).mean())
            kpis["porosity_bse_minus_etd"] = float(pore.mean() - dark.mean())
            kpis["etd_dark_solid"] = float((dark & ~pore).mean())
        elif detector == "InLens":
            lit = lo == 2
            kpis["bright_lit_inlens"] = float(lit[bright].mean()) if bright.any() else None
            kpis["pores_filled_inlens"] = float((lo[pore] != 0).mean()) if pore.any() else None
            kpis["inlens_lit_outside_bright"] = float((lit & ~bright).mean())
    return kpis, alignment
