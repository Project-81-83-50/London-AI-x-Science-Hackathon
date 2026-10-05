"""Imaging-condition checks across images: quality flags against a reference and the common pixel size."""

import argparse

import numpy as np

from .preprocessing import STRIPE_LIMIT

QUALITY_TOLERANCE = {  # metric: (relative or absolute, tolerance) vs the reference images
    "sharpness": ("rel", 0.25),
    "noise": ("rel", 0.30),
    "contrast": ("rel", 0.25),
    "anisotropy": ("rel", 0.15),
    "median": ("abs", 0.08),
    "separability": ("abs", 0.05),
    "stripes_curtaining": ("rel", 0.25),
    "stripes_scan_lines": ("rel", 0.25),
}
QUALITY_LIMITS = {  # absolute sanity limits: metric: (min, max)
    # black clipping mostly hits pores (darkest phase anyway); white clipping erases bright-phase detail
    "clipped_black": (None, 0.05),
    "clipped_white": (None, 0.01),
    "separability": (0.70, None),
    "shading": (None, 0.15),
    # stripes strong enough to need removal are flagged even when removal worked: it leaves residual error
    "stripes_curtaining": (None, STRIPE_LIMIT),
    "stripes_scan_lines": (None, STRIPE_LIMIT),
    "stripes_curtaining_after": (None, STRIPE_LIMIT),
    "stripes_scan_lines_after": (None, STRIPE_LIMIT),
}


def quality_flags(q: dict, ref: list[dict]) -> list[str]:
    """Imaging metrics outside absolute limits or outside the reference images' range.
    With >= 3 references the band is +-3 sd (never tighter than the tolerance), else the tolerance."""
    flags = []
    for key, (lo, hi) in QUALITY_LIMITS.items():
        v = q.get(key)
        if v is not None and lo is not None and v < lo:
            flags.append(f"{key} {v:.3f} below limit {lo}")
        if v is not None and hi is not None and v > hi:
            flags.append(f"{key} {v:.3f} above limit {hi}")
    for key, (kind, tol) in QUALITY_TOLERANCE.items():
        vals = np.array([r[key] for r in ref if key in r])
        if not len(vals) or key not in q:
            continue
        center = float(np.median(vals))
        dev = q[key] / center - 1 if kind == "rel" else q[key] - center
        band = tol
        if len(vals) >= 3:
            band = max(tol, 3 * vals.std(ddof=1) / (abs(center) if kind == "rel" else 1.0))
        if abs(dev) > band:
            shown = f"{100 * dev:+.0f}%" if kind == "rel" else f"{dev:+.3f}"
            flags.append(f"{key} {q[key]:.3f} vs reference {center:.3f} ({shown})")
    return flags


def resolve_target(metas: list[dict], args: argparse.Namespace, baseline: dict | None) -> tuple[float | None, str]:
    """One physical pixel size for the whole comparison. Returns (target_nm, note)."""
    pxs = [args.px_size or m["pixel_size_nm"] for m in metas]
    known = [p for p in pxs if p]
    if known and len(known) < len(pxs):
        raise ValueError("some images have no pixel size in their metadata: pass --px-size")
    if args.target_px:
        target, note = args.target_px, "set by --target-px"
    elif baseline and baseline.get("target_pixel_nm"):
        target, note = baseline["target_pixel_nm"], "taken from baseline"
    elif known:
        b = args.bin or 1
        target, note = max(known) * b, "coarsest image" + (f" x bin {b}" if b > 1 else "")
    else:
        return None, f"NO PIXEL SIZES: plain {args.bin or 2}x binning, scale consistency cannot be checked"
    if not known:
        raise ValueError("a target pixel size needs image pixel sizes: pass --px-size")
    if max(known) / min(known) > 1.05:
        note += f"; mixed magnifications ({min(known):.2f}-{max(known):.2f} nm/px) resampled to match"
    return target, note
