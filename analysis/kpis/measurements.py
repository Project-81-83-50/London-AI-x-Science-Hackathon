"""The KPIs of one segmented location: composition, pore network, bright particles, graphite texture,
interfaces, transport estimates and homogeneity (see catalogue.KPI_GROUPS for their definitions)."""

import numpy as np
from scipy import spatial
from skimage import measure

from .constants import CRACK_ASPECT, CRACK_LENGTH_UM, MIN_BRIGHT_PX, MIN_PORE_PX, PROFILE_BANDS


def chords(mask: np.ndarray, axis: int) -> np.ndarray:
    """Lengths (px) of uninterrupted runs of the phase along x (axis=1) or y (axis=0),
    excluding runs cut by the image border."""
    m = mask if axis == 1 else mask.T
    padded = np.pad(m, ((0, 0), (1, 1))).astype(np.int8)
    d = np.diff(padded, axis=1)
    _, starts = np.nonzero(d == 1)
    _, ends = np.nonzero(d == -1)
    keep = (starts > 0) & (ends < m.shape[1])
    return (ends - starts)[keep]


def boundary_density(mask: np.ndarray, px_um: float) -> float:
    """Phase boundary length per area (um/um^2) from line intersections: L_A = (pi/2) P_L."""
    crossings = np.count_nonzero(mask[:, 1:] != mask[:, :-1]) + np.count_nonzero(mask[1:] != mask[:-1])
    line_um = (mask.shape[0] * (mask.shape[1] - 1) + mask.shape[1] * (mask.shape[0] - 1)) * px_um
    return float(np.pi / 2 * crossings / line_um)


def regions(mask: np.ndarray, min_px: int) -> dict[str, np.ndarray]:
    """Area, centroid and axis lengths of the 4-connected regions of at least `min_px` pixels."""
    lab = measure.label(mask, connectivity=1)
    props = measure.regionprops_table(lab, properties=("area", "centroid", "axis_major_length", "axis_minor_length"))
    keep = props["area"] >= min_px
    return {k: v[keep] for k, v in props.items()}


def clark_evans(ys: np.ndarray, xs: np.ndarray, shape: tuple[int, int]) -> float | None:
    """Nearest-neighbour ratio with Donnelly's edge correction: < 1 clustered, ~1 random,
    > 1 evenly dispersed."""
    n = len(xs)
    if n < 10:
        return None
    nn = spatial.cKDTree(np.column_stack([ys, xs])).query(np.column_stack([ys, xs]), k=2)[0][:, 1]
    area, perimeter = shape[0] * shape[1], 2 * (shape[0] + shape[1])
    expected = 0.5 * np.sqrt(area / n) + (0.0514 + 0.041 / np.sqrt(n)) * perimeter / n
    return float(nn.mean() / expected)


def ecd_um(area_px: np.ndarray, px_um: float) -> np.ndarray:
    """Equivalent circle diameter in µm of regions of `area_px` pixels."""
    return 2 * np.sqrt(area_px / np.pi) * px_um


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Value below which half of the total weight lies."""
    order = np.argsort(values)
    c = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(c, c[-1] / 2)])


def measure_location(labels: np.ndarray, px_um: float) -> tuple[dict[str, float | None], dict]:
    """Every BSE segmentation KPI of one location, plus its profiles and particle size lists.

    `labels` is a pore (0) / graphite (1) / bright (2) map at `px_um` µm per pixel.
    """
    h, w = labels.shape
    field_um2 = h * w * px_um**2
    pore, graphite, bright = labels == 0, labels == 1, labels == 2
    phi = {k: float(m.mean()) for k, m in (("pore", pore), ("graphite", graphite), ("bright", bright))}

    pr = regions(pore, MIN_PORE_PX)
    p_ecd = ecd_um(pr["area"], px_um)
    p_len = pr["axis_major_length"] * px_um
    p_aspect = pr["axis_major_length"] / np.maximum(pr["axis_minor_length"], 1)
    cracks = (p_aspect >= CRACK_ASPECT) & (p_len >= CRACK_LENGTH_UM)
    lab = measure.label(pore, connectivity=1)
    largest = np.bincount(lab.ravel())[1:].max() if lab.max() else 0

    br = regions(bright, MIN_BRIGHT_PX)
    b_ecd = ecd_um(br["area"], px_um)
    b_aspect = br["axis_major_length"] / np.maximum(br["axis_minor_length"], 1)
    gx, gy = chords(graphite, 1) * px_um, chords(graphite, 0) * px_um

    kpis = {
        "porosity": phi["pore"],
        "graphite_fraction": phi["graphite"],
        "bright_fraction": phi["bright"],
        "bright_to_solid": phi["bright"] / max(phi["graphite"] + phi["bright"], 1e-9),
        "pore_density": len(p_ecd) / field_um2 * 100,
        "pore_ecd_d50": float(np.median(p_ecd)) if len(p_ecd) else None,
        "pore_ecd_area_d50": weighted_median(p_ecd, pr["area"]) if len(p_ecd) else None,
        "largest_pore_share": float(largest / max(pore.sum(), 1)),
        "crack_share": float(pr["area"][cracks].sum() / max(pr["area"].sum(), 1)),
        "bright_density": len(b_ecd) / field_um2 * 100,
        "bright_d50": float(np.percentile(b_ecd, 50)) if len(b_ecd) else None,
        "bright_area_d50": weighted_median(b_ecd, br["area"]) if len(b_ecd) else None,
        "bright_d90": float(np.percentile(b_ecd, 90)) if len(b_ecd) else None,
        "bright_aspect": float(np.median(b_aspect)) if len(b_aspect) else None,
        "bright_clustering": clark_evans(br["centroid-0"], br["centroid-1"], labels.shape),
        "graphite_chord_x": float(gx.mean()) if len(gx) else None,
        "graphite_chord_y": float(gy.mean()) if len(gy) else None,
        "graphite_orientation": float(gx.mean() / gy.mean()) if len(gx) and len(gy) else None,
        "pore_interface_density": boundary_density(pore, px_um),
        "bright_interface_density": boundary_density(bright, px_um),
    }
    rows = np.array_split(np.arange(h), PROFILE_BANDS)
    cols = np.array_split(np.arange(w), PROFILE_BANDS)
    profile_pore = [float(pore[r].mean()) for r in rows]
    profile_bright = [float(bright[r].mean()) for r in rows]
    third = PROFILE_BANDS // 3
    kpis["porosity_gradient"] = float(np.mean(profile_pore[-third:]) - np.mean(profile_pore[:third]))
    kpis["porosity_band_cv"] = float(np.std(profile_pore) / max(np.mean(profile_pore), 1e-9))
    in_plane = [float(pore[:, c].mean()) for c in cols]
    kpis["porosity_inplane_cv"] = float(np.std(in_plane) / max(np.mean(in_plane), 1e-9))
    kpis["bruggeman_transport"] = phi["pore"] ** 1.5
    kpis["bruggeman_tortuosity"] = phi["pore"] ** -0.5 if phi["pore"] > 0 else None
    return kpis, {
        "profile_pore": profile_pore,
        "profile_bright": profile_bright,
        "pore_ecd": p_ecd,
        "bright_ecd": b_ecd,
    }
