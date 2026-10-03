"""
Detailed KPI report for each reference battery batch (data/raw/batch_N).

Each batch is one battery type, imaged at several fields of view; every field has two to
three detector views. Filenames do not say which files show the same field (see
field_matching.py), so fields are matched from the images first and each field is one
replicate. The electrode cross-sections show three intensity classes on a
compositional-contrast view: black pores, dark-grey graphite flakes and a bright,
higher-Z phase (likely the silicon-containing additive). This script:

1. Analyses the BSE view of each field. Filename detector labels are wrong, so the detector
   of every view is identified from its pixels by field_matching.py (BSE / InLens / ETD).
   Fields without a BSE view are reported but left out of the batch statistics. A BSE view
   whose bright class has rough rims or a high loading is kept but flagged lower-confidence,
   since binder and particle edges can leak into the bright class.
2. Segments that view into pore / graphite / bright phase (3-class Otsu after removing
   smooth shading) and measures composition, pore network, bright-particle, graphite
   texture, interface and homogeneity KPIs.
3. Summarises every KPI across locations (mean, SD, CV, t-based 95% CI, range) and writes
   a frontend-ready report plus a segmentation overlay per field.

Outputs (Git-ignored, like the raw data):
  data/processed/batch_kpis/batch_N/report.json
  data/processed/batch_kpis/batch_N/overlays/<field>.jpg
  data/processed/batch_kpis/summary.json      headline KPIs of every batch side by side
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage, spatial, stats
from skimage import filters, measure

from field_matching import load_or_match

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "batch_kpis"

TARGET_NM = 50.0          # analysis pixel size; raw images are ~25 nm/px
# View selection: bright-class perimeter per area (1/um, at 100 nm/px) and bright area share.
# Thresholds sit in the gap between the two clusters seen across all reference views.
RIM_CLEAN, RIM_USABLE = 2.3, 2.6
MAX_BRIGHT_SHARE = 0.15
SEPARABILITY_LIMIT = 0.80
MIN_PORE_PX = 4           # 0.01 um^2 at 50 nm/px
MIN_BRIGHT_PX = 20        # 0.05 um^2: smaller bright specks are mostly edge noise
CRACK_ASPECT, CRACK_LENGTH_UM = 4.0, 5.0
PROFILE_BANDS = 16
PHASE_COLORS = {0: (42, 120, 214), 2: (235, 104, 52)}  # pore, bright phase; graphite stays grey


# ---------------------------------------------------------------- loading and view selection

def pixel_size_nm(tif):
    """Pixel size from the TIFF resolution tags (pixels per inch or per cm)."""
    page = tif.pages[0]
    xres, unit = page.tags.get("XResolution"), page.tags.get("ResolutionUnit")
    per_unit_nm = {2: 25.4e6, 3: 1e7}.get(int(unit.value) if unit else 2)
    if xres and per_unit_nm and xres.value[0]:
        px = per_unit_nm * xres.value[1] / xres.value[0]
        if px < 10_000:  # larger values are screen-dpi placeholders, not a calibration
            return px
    return None


def read_grey(path):
    """Grey image in [0, 1] and its raw pixel size. The RGB channels are copies, except for a
    two-pixel stripe on the right edge of some files, which is cropped."""
    with tifffile.TiffFile(path) as tif:
        arr = tif.asarray()
        px = pixel_size_nm(tif)
    if arr.ndim == 3:
        arr = arr[..., 1]
    full = float(np.iinfo(arr.dtype).max) if np.issubdtype(arr.dtype, np.integer) else 1.0
    return arr[:, :-2].astype(np.float32) / full, px


def bin_image(img, b):
    h, w = img.shape[0] // b * b, img.shape[1] // b * b
    return img[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))


def view_score(img, px_nm):
    """Quick 100 nm/px test segmentation: (bright-class perimeter per area in 1/um, bright area
    share). Compact bright particles score about 1.5-2.2; rim-lit edge views score higher."""
    b = max(1, round(100 / px_nm)) if px_nm else 4
    labels, _ = segment(bin_image(img, b))
    bright = labels == 2
    share = float(bright.mean())
    rim = boundary_density(bright, (px_nm * b if px_nm else 100) / 1000) / max(share, 1e-9)
    return rim, share


def view_confidence(rim, share):
    if share > MAX_BRIGHT_SHARE or rim > RIM_USABLE:
        return "excluded"
    return "clean" if rim <= RIM_CLEAN else "usable"


def inventory(batch, rebuild_fields=False):
    """Views grouped by the field they show (matched from pixels, not from filenames)."""
    manifest = load_or_match(batch, rebuild_fields)
    batch_dir = RAW / f"batch_{batch}"
    return {f["field_id"]: {"field": f, "views": [{"filename": v["filename"], "path": batch_dir / v["filename"],
                                                   "detector": v["detector"],
                                                   "detector_confidence": v["detector_confidence"],
                                                   "filename_detector": v["filename_detector"]}
                                                  for v in f["views"]]}
            for f in manifest["fields"]}


# ---------------------------------------------------------------- segmentation

def poly_surface(shape, ys, xs, values, degree=2):
    """Least-squares low-order surface through sampled grey values."""
    h, w = shape
    def terms(y, x):
        y, x = y / h - 0.5, x / w - 0.5
        return np.stack([y ** i * x ** j for i in range(degree + 1) for j in range(degree + 1 - i)], -1)
    coef, *_ = np.linalg.lstsq(terms(ys, xs), values, rcond=None)
    gy, gx = np.mgrid[0:h, 0:w]
    return (terms(gy.astype(np.float32), gx.astype(np.float32)) @ coef).astype(np.float32)


def segment(img):
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
    quality = {"shading": shading, "separability": float(between / max(sub.var(), 1e-12)),
               "clipped_black": float((img <= 0.002).mean()), "clipped_white": float((img >= 0.998).mean())}
    return labels, quality


# ---------------------------------------------------------------- KPI measurements

def chords(mask, axis):
    """Lengths (px) of uninterrupted runs of the phase along x (axis=1) or y (axis=0),
    excluding runs cut by the image border."""
    m = mask if axis == 1 else mask.T
    padded = np.pad(m, ((0, 0), (1, 1))).astype(np.int8)
    d = np.diff(padded, axis=1)
    _, starts = np.nonzero(d == 1)
    _, ends = np.nonzero(d == -1)
    keep = (starts > 0) & (ends < m.shape[1])
    return (ends - starts)[keep]


def boundary_density(mask, px_um):
    """Phase boundary length per area (um/um^2) from line intersections: L_A = (pi/2) P_L."""
    crossings = np.count_nonzero(mask[:, 1:] != mask[:, :-1]) + np.count_nonzero(mask[1:] != mask[:-1])
    line_um = (mask.shape[0] * (mask.shape[1] - 1) + mask.shape[1] * (mask.shape[0] - 1)) * px_um
    return float(np.pi / 2 * crossings / line_um)


def regions(mask, min_px):
    lab = measure.label(mask, connectivity=1)
    props = measure.regionprops_table(lab, properties=("area", "centroid", "axis_major_length",
                                                       "axis_minor_length"))
    keep = props["area"] >= min_px
    return {k: v[keep] for k, v in props.items()}


def clark_evans(ys, xs, shape):
    """Nearest-neighbour ratio with Donnelly's edge correction: < 1 clustered, ~1 random,
    > 1 evenly dispersed."""
    n = len(xs)
    if n < 10:
        return None
    nn = spatial.cKDTree(np.column_stack([ys, xs])).query(np.column_stack([ys, xs]), k=2)[0][:, 1]
    area, perimeter = shape[0] * shape[1], 2 * (shape[0] + shape[1])
    expected = 0.5 * np.sqrt(area / n) + (0.0514 + 0.041 / np.sqrt(n)) * perimeter / n
    return float(nn.mean() / expected)


def ecd_um(area_px, px_um):
    return 2 * np.sqrt(area_px / np.pi) * px_um


def weighted_median(values, weights):
    order = np.argsort(values)
    c = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(c, c[-1] / 2)])


def measure_location(labels, px_um):
    h, w = labels.shape
    field_um2 = h * w * px_um ** 2
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
    return kpis, {"profile_pore": profile_pore, "profile_bright": profile_bright,
                  "pore_ecd": p_ecd, "bright_ecd": b_ecd}


def save_overlay(img, labels, path, width=1400):
    """Grey image with pores tinted blue and the bright phase tinted orange."""
    scale = width / img.shape[1]
    size = (width, max(1, round(img.shape[0] * scale)))
    p1, p99 = np.percentile(img[::4, ::4], [0.5, 99.5])
    grey = np.clip((img - p1) / max(p99 - p1, 1e-6), 0, 1)
    rgb = np.repeat((grey * 255).astype(np.uint8)[..., None], 3, axis=2).astype(np.float32)
    for cls, colour in PHASE_COLORS.items():
        m = labels == cls
        rgb[m] = 0.45 * rgb[m] + 0.55 * np.array(colour, np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb.astype(np.uint8)).resize(size, Image.Resampling.LANCZOS).save(path, quality=85)


# ---------------------------------------------------------------- KPI catalogue

PERCENT, MICRON, RATIO, DENSITY, PER_UM = "%", "µm", "ratio", "per 100 µm²", "µm / µm²"
KPI_GROUPS = [
    ("composition", "Phase composition", "Area fractions of the segmented phases. In a "
     "cross-section, area fraction estimates volume fraction (Delesse principle).", [
        ("porosity", "Porosity", PERCENT, 100, "Area share of the black pore class."),
        ("graphite_fraction", "Graphite fraction", PERCENT, 100, "Area share of the dark-grey flake class."),
        ("bright_fraction", "Bright-phase fraction", PERCENT, 100,
         "Area share of the bright, higher-Z class (likely the Si-containing additive)."),
        ("bright_to_solid", "Bright phase share of solids", PERCENT, 100,
         "Bright phase / (graphite + bright phase): the additive loading of the active material."),
    ]),
    ("pores", "Pore network", "Connected regions of the pore class.", [
        ("pore_density", "Pore count density", DENSITY, 1, "Separate pore regions per 100 µm²."),
        ("pore_ecd_d50", "Median pore size", MICRON, 1,
         "Median equivalent circle diameter (ECD) of pore regions, by count."),
        ("pore_ecd_area_d50", "Area-weighted pore size", MICRON, 1,
         "ECD at which half of the pore area lies in larger pores."),
        ("largest_pore_share", "Largest pore network share", PERCENT, 100,
         "Share of pore area in the single largest connected pore region: a 2D connectivity proxy."),
        ("crack_share", "Crack-like pore share", PERCENT, 100,
         f"Share of pore area in elongated pores (aspect ≥ {CRACK_ASPECT:g}, length ≥ {CRACK_LENGTH_UM:g} µm)."),
    ]),
    ("bright", "Bright-phase particles", "Connected regions of the bright class.", [
        ("bright_density", "Bright particle density", DENSITY, 1, "Bright particles per 100 µm²."),
        ("bright_d50", "Bright particle D50", MICRON, 1,
         "Median ECD by count. Dominated by the many small particles near the 0.25 µm detection limit."),
        ("bright_area_d50", "Area-weighted bright particle size", MICRON, 1,
         "ECD at which half of the bright-phase area lies in larger particles."),
        ("bright_d90", "Bright particle D90", MICRON, 1, "90th percentile ECD by count."),
        ("bright_aspect", "Bright particle aspect ratio", RATIO, 1, "Median major / minor axis length."),
        ("bright_clustering", "Bright particle dispersion", RATIO, 1,
         "Clark–Evans nearest-neighbour ratio: below 1 clustered, about 1 random, above 1 evenly spread."),
    ]),
    ("graphite", "Graphite texture", "Mean intercept (chord) lengths through the graphite class.", [
        ("graphite_chord_x", "Graphite chord length, horizontal", MICRON, 1,
         "Mean length of uninterrupted graphite runs along image rows."),
        ("graphite_chord_y", "Graphite chord length, vertical", MICRON, 1,
         "Mean length of uninterrupted graphite runs along image columns."),
        ("graphite_orientation", "Flake orientation index", RATIO, 1,
         "Horizontal / vertical chord length: above 1 means flakes lie along the image width."),
    ]),
    ("interfaces", "Interfaces and transport", "Boundary densities and model transport estimates.", [
        ("pore_interface_density", "Pore–solid interface density", PER_UM, 1,
         "Pore boundary length per unit area (stereological estimate of specific surface)."),
        ("bright_interface_density", "Bright-phase interface density", PER_UM, 1,
         "Bright-phase boundary length per unit area."),
        ("bruggeman_tortuosity", "Tortuosity (Bruggeman estimate)", RATIO, 1,
         "Model value porosity^-0.5. Assumes spherical particles, so treat as a lower bound."),
        ("bruggeman_transport", "Effective transport factor (Bruggeman)", PERCENT, 100,
         "Model value porosity^1.5: electrolyte conductivity as a share of bulk."),
    ]),
    ("homogeneity", "Homogeneity within each image", "How evenly the pore class is spread "
     f"within each field of view, using {PROFILE_BANDS} bands.", [
        ("porosity_gradient", "Top-to-bottom porosity change", "pp", 100,
         "Porosity of the bottom third minus the top third of the image, in percentage points."),
        ("porosity_band_cv", "Vertical porosity variation", PERCENT, 100,
         "Coefficient of variation of porosity across horizontal bands."),
        ("porosity_inplane_cv", "Horizontal porosity variation", PERCENT, 100,
         "Coefficient of variation of porosity across vertical bands."),
    ]),
]
HEADLINE = ["porosity", "graphite_fraction", "bright_fraction", "bright_area_d50", "pore_ecd_area_d50",
            "graphite_orientation"]
KPI_INDEX = {k[0]: (g[0], *k[1:]) for g in KPI_GROUPS for k in g[3]}


SIGNED_KPIS = {"porosity_gradient"}  # can be negative: CV is meaningless, judge by the CI instead


def summarise(values, signed=False):
    v = np.array([x for x in values if x is not None and np.isfinite(x)], float)
    if not len(v):
        return {"n": 0}
    out = {"n": int(len(v)), "mean": float(v.mean()), "min": float(v.min()), "max": float(v.max()),
           "sd": None, "cv": None, "ci95": None, "consistency": "single location"}
    if len(v) > 1:
        sd = float(v.std(ddof=1))
        half = float(stats.t.ppf(0.975, len(v) - 1) * sd / np.sqrt(len(v)))
        ci = [out["mean"] - half, out["mean"] + half]
        if signed:
            out.update(sd=sd, ci95=ci, consistency="non-zero" if ci[0] > 0 or ci[1] < 0 else "includes zero")
            return out
        cv = sd / abs(out["mean"]) if out["mean"] else None
        out.update(sd=sd, cv=cv, ci95=ci,
                   consistency="consistent" if cv is not None and cv < 0.10 else
                   "moderate" if cv is not None and cv < 0.25 else "variable")
    return out


def histogram(values, lo, hi, n_bins=24):
    """Log-spaced histogram (share of particles per bin) for size distributions."""
    edges = np.geomspace(lo, hi, n_bins + 1)
    v = np.clip(values, lo, hi * 0.9999)
    counts = np.histogram(v, edges)[0]
    return {"edges": edges.tolist(), "counts": counts.tolist(),
            "shares": (counts / max(counts.sum(), 1)).tolist(), "total": int(counts.sum())}


def locations_phrase(n):
    return f"{n} location" + ("" if n == 1 else "s")


def findings(groups, locations, profiles):
    """Plain-language observations derived only from this batch's numbers."""
    k = {kpi["id"]: kpi for g in groups for kpi in g["kpis"]}
    notes = []
    def pct(x):
        return f"{x * 100:.1f}%"
    if k["porosity"]["n"]:
        notes.append(f"Average composition is {pct(k['porosity']['mean'])} pore, "
                     f"{pct(k['graphite_fraction']['mean'])} graphite and {pct(k['bright_fraction']['mean'])} "
                     f"bright phase across {k['porosity']['n']} locations.")
    if k["bright_area_d50"]["n"]:
        notes.append(f"Half of the bright-phase area sits in particles larger than "
                     f"{k['bright_area_d50']['mean']:.2f} µm; by count the median is "
                     f"{k['bright_d50']['mean']:.2f} µm and D90 is {k['bright_d90']['mean']:.2f} µm.")
    ori = k["graphite_orientation"]
    if ori["n"]:
        notes.append(f"Graphite runs are {ori['mean']:.2f}× longer horizontally than vertically: "
                     + ("flakes lie strongly along the image width." if ori["mean"] > 1.3 else
                        "flakes are mildly aligned with the image width." if ori["mean"] > 1.1 else
                        "flakes show little preferred orientation."))
    variable = [kpi["name"] for kpi in k.values() if kpi.get("consistency") == "variable"
                and KPI_INDEX[kpi["id"]][0] not in ("homogeneity",)]
    if variable:
        notes.append("Location-to-location spread exceeds 25% CV for: " + ", ".join(variable) + ".")
    g = k["porosity_gradient"]
    if g["n"] > 1 and g["ci95"] and (g["ci95"][0] > 0 or g["ci95"][1] < 0):
        notes.append(f"Porosity changes consistently from the top to the bottom of the images "
                     f"({g['mean'] * 100:+.1f} percentage points, 95% CI excludes zero).")
    excluded = [l["location_id"] for l in locations if not l["included"]]
    if excluded:
        notes.append(f"{locations_phrase(len(excluded))} had no BSE view and "
                     f"{'was' if len(excluded) == 1 else 'were'} left out: "
                     + ", ".join(excluded) + ".")
    usable = [l["location_id"] for l in locations if l["confidence"] == "usable"]
    if usable:
        notes.append(f"{locations_phrase(len(usable))} {'has' if len(usable) == 1 else 'have'} a BSE view whose "
                     "bright class may include binder or particle edges (lower confidence): "
                     + ", ".join(usable) + ".")
    mixed = sum(len(l["filename_codes"]) > 1 for l in locations)
    assigned = sum(not l["location_recovered"] for l in locations)
    if mixed or assigned:
        notes.append(f"Files were regrouped by image matching into {len(locations)} locations; {mixed} of them "
                     "combine files with different filename codes. Each location is named with one filename code; "
                     f"for {assigned} of them several codes fit equally well, so the name is assigned, not recovered.")
    views = [v for l in locations for v in l["views"]]
    # A filename "SE" counts as the chamber secondary-electron detector, i.e. ETD.
    wrong = sum(v["detector"].upper() != {"SE": "ETD"}.get(v["filename_detector"], v["filename_detector"])
                for v in views)
    if wrong:
        notes.append(f"Detectors were identified from the images: {wrong} of {len(views)} files carry a different "
                     "detector label in their filename.")
    if not (mixed or assigned or wrong):
        notes.append(f"All {len(views)} filenames agree with the images: each location's files show the same field, "
                     "and every filter label matches the detector identified from the image.")
    return notes


# ---------------------------------------------------------------- batch report

def analyse_batch(batch, rebuild_fields=False):
    out_dir = OUT / f"batch_{batch}"
    fields = inventory(batch, rebuild_fields)
    locs = {fid: f["views"] for fid, f in fields.items()}
    locations, per_kpi, pore_ecd, bright_ecd, profiles = [], {}, [], [], {"pore": [], "bright": []}
    for i, (loc, views) in enumerate(sorted(locs.items()), 1):
        print(f"[batch {batch} {i}/{len(locs)}] {loc}", flush=True)
        scored = []
        for v in views:
            img, px = read_grey(v["path"])
            rim, share = view_score(img, px)
            scored.append({"view": v, "img": img, "px": px, "rim": rim, "share": share,
                           "confidence": view_confidence(rim, share)})
        # The BSE view carries the composition contrast; without one, show the InLens view but exclude it.
        rank = {"BSE": 0, "InLens": 1, "ETD": 2}
        scored.sort(key=lambda s: rank.get(s["view"]["detector"], 3))
        best = scored[0]
        view, img, px = best["view"], best["img"], best["px"]
        if view["detector"] != "BSE":
            confidence = "excluded"
        else:
            confidence = "clean" if best["confidence"] == "clean" else "usable"
        b = max(1, round(TARGET_NM / px)) if px else 2
        px_um = (px * b if px else TARGET_NM) / 1000
        work = bin_image(img, b)
        labels, quality = segment(work)
        kpis, extra = measure_location(labels, px_um)
        flags = []
        included = confidence != "excluded"
        if confidence == "usable":
            flags.append(f"bright class has rough rims or a high share (perimeter/area {best['rim']:.2f} µm⁻¹, "
                         f"{best['share'] * 100:.0f}% bright); binder or particle edges may add to it")
        elif confidence == "excluded":
            flags.append(f"no BSE view in this field (shown: the {view['detector']} view); "
                         "left out of batch statistics")
        if quality["clipped_white"] > 0.01:
            flags.append(f"{quality['clipped_white'] * 100:.1f}% of pixels saturated white")
        if quality["clipped_black"] > 0.05:
            flags.append(f"{quality['clipped_black'] * 100:.1f}% of pixels clipped black")
        if quality["shading"] > 0.25:
            flags.append(f"strong shading removed ({quality['shading']:.2f} of grey range)")
        if quality["separability"] < SEPARABILITY_LIMIT:
            flags.append(f"weak phase separation (separability {quality['separability']:.2f})")
        if not px:
            flags.append("no pixel calibration; 50 nm/px assumed")
        overlay = f"overlays/{fields[loc]['field']['location']}.jpg"
        save_overlay(work, labels, out_dir / overlay)
        locations.append({
            # Named after the field's assigned location so every view of it shares one name.
            "location_id": fields[loc]["field"]["location"], "field_id": loc,
            "location_recovered": fields[loc]["field"]["location_recovered"],
            "filename_codes": fields[loc]["field"]["filename_codes"],
            "match_confidence": fields[loc]["field"]["confidence"],
            "included": included, "confidence": confidence, "analysed_image": view["filename"],
            "analysed_detector": view["detector"], "analysed_filename_detector": view["filename_detector"],
            "pixel_size_um": px_um,
            "field_um": [round(labels.shape[1] * px_um, 1), round(labels.shape[0] * px_um, 1)],
            "views": [{"filename": s["view"]["filename"], "detector": s["view"]["detector"],
                       "detector_confidence": s["view"]["detector_confidence"],
                       "filename_detector": s["view"]["filename_detector"],
                       "rim_score": s["rim"], "bright_share": s["share"],
                       "analysed": s is best} for s in scored],
            "quality": quality, "flags": flags, "kpis": kpis,
            "profile_pore": extra["profile_pore"], "profile_bright": extra["profile_bright"],
            "overlay": overlay,
        })
        if included:
            for key, value in kpis.items():
                per_kpi.setdefault(key, []).append((fields[loc]["field"]["location"], value))
            pore_ecd.append(extra["pore_ecd"])
            bright_ecd.append(extra["bright_ecd"])
            profiles["pore"].append(extra["profile_pore"])
            profiles["bright"].append(extra["profile_bright"])

    locations.sort(key=lambda l: l["location_id"])
    for key in per_kpi:
        per_kpi[key].sort()
    locations.sort(key=lambda l: l["location_id"])
    for key in per_kpi:
        per_kpi[key].sort()
    groups = []
    for gid, title, description, items in KPI_GROUPS:
        kpis = []
        for kid, name, unit, scale, definition in items:
            pairs = per_kpi.get(kid, [])
            kpis.append({"id": kid, "name": name, "unit": unit, "display_scale": scale,
                         "definition": definition, **summarise([v for _, v in pairs], kid in SIGNED_KPIS),
                         "per_location": [{"location_id": l, "value": v} for l, v in pairs]})
        groups.append({"id": gid, "title": title, "description": description, "kpis": kpis})

    def profile_summary(rows):
        a = np.array(rows) if rows else np.zeros((0, PROFILE_BANDS))
        return {"mean": a.mean(0).tolist() if len(a) else [], "min": a.min(0).tolist() if len(a) else [],
                "max": a.max(0).tolist() if len(a) else []}

    pore_all = np.concatenate(pore_ecd) if pore_ecd else np.array([])
    bright_all = np.concatenate(bright_ecd) if bright_ecd else np.array([])
    included = [l for l in locations if l["included"]]
    report = {
        "report_type": "batch-kpi-report", "report_version": 1, "batch_id": str(batch),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": {
            "analysis_pixel_um": TARGET_NM / 1000,
            "view_selection": "Filename detector labels are wrong, so each view's detector is identified "
                              "from its pixels (BSE: grainy backscatter noise; ETD: pores black; InLens: pores "
                              "filled in and rims lit) and the field's BSE view is analysed. Fields "
                              "without one are excluded. BSE views whose bright class has rough rims "
                              f"(perimeter/area > {RIM_CLEAN} µm⁻¹) or a share above {MAX_BRIGHT_SHARE:.0%} "
                              "are kept but flagged lower-confidence.",
            "segmentation": "Gaussian smoothing (1 px), shading surface fitted to the graphite class, "
                            "3-class Otsu thresholds, 3×3 median clean-up.",
            "statistics": "Each matched location is one replicate. Mean, sample SD, CV and a t-based 95% CI of "
                          "the batch mean across locations.",
            "consistency_bands": "CV < 10% consistent · 10–25% moderate · > 25% variable. Signed KPIs "
                                 "report whether the 95% CI excludes zero instead.",
            "phase_colors": {"pore": "#2a78d6", "graphite": "#1baf7a", "bright": "#eb6834"},
        },
        "inventory": {
            "locations": len(locations), "locations_analysed": len(included),
            "confidence": {c: sum(l["confidence"] == c for l in locations) for c in ("clean", "usable", "excluded")},
            "images": sum(len(v) for v in locs.values()),
            "filename_detectors": {d: sum(v["filename_detector"] == d for vs in locs.values() for v in vs)
                                   for d in ("BSE", "ETD", "INLENS", "SE")},
            "identified_detectors": {d: sum(v["detector"] == d for vs in locs.values() for v in vs)
                                     for d in ("BSE", "InLens", "ETD")},
            "field_area_um2": float(sum(l["field_um"][0] * l["field_um"][1] for l in included)),
        },
        "headline": HEADLINE,
        "kpi_groups": groups,
        "distributions": {
            "bright_ecd": {"label": "Bright particle size (ECD)", "unit": MICRON,
                           **histogram(bright_all, 0.25, 30)},
            "pore_ecd": {"label": "Pore size (ECD)", "unit": MICRON, **histogram(pore_all, 0.1, 30)},
        },
        "profiles": {"bands": PROFILE_BANDS, "axis": "image top to bottom",
                     "porosity": profile_summary(profiles["pore"]),
                     "bright_fraction": profile_summary(profiles["bright"])},
        "locations": locations,
        "caveats": [
            "Phases are intensity classes. They have not been validated against labelled images or "
            "chemical mapping (EDS); in particular, carbon-black/binder domains may fall in either the "
            "pore or the graphite class.",
            "Each image is a 2D section. Connectivity and tortuosity values are proxies, not 3D measurements.",
            f"Features smaller than about {5 * TARGET_NM / 1000:.2f} µm (5 px) are under-resolved at the "
            "analysis pixel size.",
            "No acceptance limits are defined, so no pass/fail verdict is given.",
        ],
    }
    report["findings"] = findings(groups, locations, report["profiles"])
    (out_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description="Detailed KPI report per reference battery batch.")
    ap.add_argument("--batches", nargs="+", default=["1", "2", "3"])
    ap.add_argument("--rebuild-fields", action="store_true",
                    help="re-match fields even if the cached field manifest is up to date")
    args = ap.parse_args()
    # Merge into the existing summary so rerunning one batch keeps the others' headline KPIs.
    summary_path = OUT / "summary.json"
    previous = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    summary = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "batches": [b for b in previous.get("batches", []) if b["batch_id"] not in args.batches]}
    for batch in args.batches:
        report = analyse_batch(batch, args.rebuild_fields)
        kpis = {k["id"]: k for g in report["kpi_groups"] for k in g["kpis"]}
        summary["batches"].append({
            "batch_id": report["batch_id"], "locations_analysed": report["inventory"]["locations_analysed"],
            "kpis": [{key: kpis[h][key] for key in ("id", "name", "unit", "display_scale", "mean", "sd",
                                                     "ci95", "n", "consistency") if key in kpis[h]}
                     for h in HEADLINE]})
    summary["batches"].sort(key=lambda b: int(b["batch_id"]))
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"wrote reports to {OUT}")


if __name__ == "__main__":
    main()
