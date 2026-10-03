"""
Scratch: imaging-harmonised material features.

Every image is first brought to the same imaging conditions, so that nothing an imaging
session leaves behind (noise, contrast settings, focus) can be measured afterwards:

  1. contrast   - its 3 intensity classes are mapped piecewise-linearly to fixed grey levels
  2. noise      - white noise is added up to a common level per view (2x the noisiest
                  image's), so the added noise dominates every session's own noise
  3. resolution - binned 2x (50 nm/px) and blurred, so focus / beam differences vanish

Then only the material is measured: phase fractions, length-weighted chord-length
distributions, two-point correlation C(r), particle size and clustering, and texture.
"""

import json
import zlib
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage import feature, filters, measure

from batch_classifier import K_IMMERKAER, ROOT, index, load_u8

OUT = Path(__file__).parent / "out" / "classifier"
LEVELS = (0.2, 0.5, 0.85)
CUTS = (0.35, 0.675)
CHORD_EDGES = np.array([1, 2, 4, 8, 16, 32, 64, 128, 10 ** 6])
LAGS = (1, 2, 4, 8, 16, 32, 64)
PX_UM = 0.05


def class_medians(img):
    sm = ndimage.gaussian_filter(img, 2.0)
    lab = np.digitize(sm, filters.threshold_multiotsu(sm[::4, ::4], classes=3))
    med = []
    for k in range(3):
        core = ndimage.binary_erosion(lab == k, iterations=3)
        med.append(float(np.median(img[core])) if core.sum() > 500 else float(np.median(img[lab == k])))
    med[1] = max(med[1], med[0] + 1.0)
    med[2] = max(med[2], med[1] + 1.0)
    return med, lab


def map_levels(img, med):
    lo = LEVELS[0] + (img - med[0]) * (LEVELS[1] - LEVELS[0]) / (med[1] - med[0])
    hi = LEVELS[1] + (img - med[1]) * (LEVELS[2] - LEVELS[1]) / (med[2] - med[1])
    return np.where(img < med[1], lo, hi).astype(np.float32)


def noise_sigma(mapped, lab):
    core = ndimage.binary_erosion(lab == 1, iterations=4)
    r = ndimage.convolve(mapped, K_IMMERKAER)
    return float(np.sqrt(np.pi / 2) * np.abs(r[core]).mean() / 6)


def harmonise(u8, target, seed):
    img = u8.astype(np.float32)
    med, lab = class_medians(img)
    m = map_levels(img, med)
    s = noise_sigma(m, lab)
    rng = np.random.default_rng(seed)
    m = m + rng.normal(0, np.sqrt(max(target ** 2 - s ** 2, 0.0)), m.shape).astype(np.float32)
    h, w = m.shape[0] // 2 * 2, m.shape[1] // 2 * 2
    m = m[:h, :w].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    return ndimage.gaussian_filter(m, 1.0)


def chord_features(lab, k, axis, prefix):
    m = (lab == k) if axis == 1 else (lab == k).T
    d = np.diff(np.pad(m.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    runs = np.nonzero(d == -1)[1] - np.nonzero(d == 1)[1]
    if not len(runs):
        return {f"{prefix}_mean": 0.0, **{f"{prefix}_w{i}": 0.0 for i in range(len(CHORD_EDGES) - 1)}}
    w = np.histogram(runs, CHORD_EDGES, weights=runs)[0] / runs.sum()  # share of phase length in each chord-length bin
    return {f"{prefix}_mean": float(runs.mean() * PX_UM), **{f"{prefix}_w{i}": float(v) for i, v in enumerate(w)}}


def particle_features(mask, prefix):
    lab = measure.label(mask)
    area = np.bincount(lab.ravel())[1:]
    keep = np.nonzero(area >= 4)[0] + 1
    if len(keep) < 5:
        return {}
    area = area[keep - 1].astype(float)
    eqd = np.sqrt(4 * area / np.pi) * PX_UM
    cents = np.array(ndimage.center_of_mass(mask, lab, keep))
    nnd = cKDTree(cents).query(cents, k=2)[0][:, 1] * PX_UM
    density = len(keep) / (mask.size * PX_UM ** 2)
    order = np.argsort(eqd)
    cum = np.cumsum(area[order]) / area.sum()
    return {f"{prefix}_density": density,
            f"{prefix}_d10": float(np.percentile(eqd, 10)), f"{prefix}_d50": float(np.percentile(eqd, 50)),
            f"{prefix}_d90": float(np.percentile(eqd, 90)),
            f"{prefix}_d50_area": float(eqd[order][np.searchsorted(cum, 0.5)]),
            f"{prefix}_clark_evans": float(nnd.mean() / (0.5 / np.sqrt(density)))}


def material_features(H):
    lab = np.digitize(H, CUTS)
    f = {f"phi_{k}": float(np.mean(lab == k)) for k in range(3)}
    for k in range(3):
        phi = f[f"phi_{k}"]
        ind = (lab == k).astype(np.float32)
        for axis, ax in ((1, "x"), (0, "y")):
            f.update(chord_features(lab, k, axis, f"chord{k}{ax}"))
            for r in LAGS:
                a, b = (ind[:, :-r], ind[:, r:]) if axis == 1 else (ind[:-r], ind[r:])
                f[f"C{k}{ax}{r}"] = float(((a * b).mean() - phi ** 2) / max(phi * (1 - phi), 1e-9))
    f.update(particle_features(lab == 2, "bright"))
    f.update(particle_features(lab == 0, "pore"))
    t = 64
    ny, nx = lab.shape[0] // t, lab.shape[1] // t
    q = (lab[: ny * t, : nx * t] == 2).reshape(ny, t, nx, t).mean(axis=(1, 3))
    f["bright_quadrat_var"] = float(q.var() / max(f["phi_2"] * (1 - f["phi_2"]), 1e-9))
    u8 = (np.clip(H, 0, 1) * 255).astype(np.uint8)
    for P, R in ((8, 1), (16, 4)):
        h = np.bincount(feature.local_binary_pattern(u8, P, R, "uniform").astype(int).ravel(), minlength=P + 2) / u8.size
        f.update({f"lbp{P}_{i}": float(v) for i, v in enumerate(h)})
    q16 = np.clip((H * 16).astype(int), 0, 15).astype(np.uint8)
    glcm = feature.graycomatrix(q16, [1, 4, 16], [0, np.pi / 2], levels=16, symmetric=True, normed=True)
    for prop in ("contrast", "homogeneity", "correlation", "energy"):
        f.update({f"glcm_{prop}_{d}": float(v) for d, v in zip((1, 4, 16), feature.graycoprops(glcm, prop).mean(axis=1))})
    return f


def main():
    rows = index(ROOT)
    sig = []
    for r in rows:  # pass 1: own noise level of every image, in harmonised grey units
        img = load_u8(r["path"]).astype(np.float32)
        med, lab = class_medians(img)
        sig.append(noise_sigma(map_levels(img, med), lab))
    views = np.array([r["view"] for r in rows])
    target = {v: 2 * max(s for s, vv in zip(sig, views) if vv == v) for v in set(views)}
    print("own noise (harmonised units), per view min-max:",
          {v: f"{min(s for s, vv in zip(sig, views) if vv == v):.3f}-{max(s for s, vv in zip(sig, views) if vv == v):.3f}" for v in target},
          "-> target", {v: round(t, 3) for v, t in target.items()}, flush=True)
    table = []
    for i, r in enumerate(rows):  # pass 2: harmonise, then measure the material
        H = harmonise(load_u8(r["path"]), target[r["view"]], zlib.crc32(r["path"].name.encode()))
        f = material_features(H)
        lab = np.digitize(H, CUTS)
        f["_check_noise"] = noise_sigma(H, lab)
        f["_check_median_graphite"] = float(np.median(H[lab == 1]))
        table.append({"path": str(r["path"]), **f})
        print(f"  {i + 1}/{len(rows)} {r['batch']}/{r['path'].name}", flush=True)
    (OUT / "harmonized_features.json").write_text(json.dumps({"target": target, "rows": table}))


if __name__ == "__main__":
    main()
