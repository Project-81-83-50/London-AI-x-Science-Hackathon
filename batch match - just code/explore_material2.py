"""
Scratch: production-step markers, per location, from all three registered views.

All images are harmonised first (explore_harmonized: same contrast levels, same noise,
same resolution), so imaging-session settings cannot leak into these measurements.
BSE says WHAT each pixel is; SE / InLens (same pixels) show surface detail.

  carbon-binder domain  extended mid-grey regions between pore and graphite level (BSE)
  pore filling          SE / InLens signal from inside BSE-dark pores (material deeper in pores)
  graphite cracks       thin dark lines inside graphite (BSE), thin bright lines (InLens)
  bright particles      internal texture (dense vs porous), contact with pores
  mixing patchiness     how unevenly the bright phase is spread at 6.4 and 12.8 um scales
"""

import json
import zlib
from pathlib import Path

import numpy as np
from scipy import ndimage

import explore_harmonized as E
from batch_classifier import ROOT, index, load_u8

OUT = Path(__file__).parent / "out" / "classifier"


def H_of(path, target):
    return E.harmonise(load_u8(path), target, zlib.crc32(Path(path).name.encode()))


def local_stats(H, s):
    mu = ndimage.gaussian_filter(H, s)
    sd = np.sqrt(np.maximum(ndimage.gaussian_filter(H * H, s) - mu * mu, 0))
    return mu, sd


def features(views, target):
    Hb = H_of(views["BSE"], target["BSE"])
    lab = np.digitize(Hb, E.CUTS)
    mu, sd = local_stats(Hb, 1.5)
    f = {}
    graphite_core = ndimage.binary_erosion(lab == 1, iterations=3)
    sd_ref = float(np.median(sd[graphite_core]))

    # carbon-binder domain: extended regions between pore and graphite grey level (thin edge bands removed)
    mid = (mu > 0.27) & (mu < 0.42)
    cbd = ndimage.binary_opening(mid, structure=np.ones((5, 5)))
    dark = (mu <= 0.27)
    f["cbd_fraction"] = float(cbd.mean())
    f["cbd_share_of_pore_space"] = float(cbd.sum() / max(cbd.sum() + dark.sum(), 1))
    f["cbd_texture"] = float(np.median(sd[cbd]) / sd_ref) if cbd.any() else np.nan

    # graphite cracks: thin dark lines inside graphite (black top-hat)
    th = ndimage.grey_closing(Hb, size=(5, 5)) - Hb
    gi = ndimage.binary_erosion(lab == 1, iterations=4)
    f["graphite_crack_density"] = float(np.mean(th[gi] > 0.1))
    f["graphite_crack_strength"] = float(np.percentile(th[gi], 99))

    # bright particles: internal texture and what they touch
    bi = ndimage.binary_erosion(lab == 2, iterations=2)
    _, sd1 = local_stats(Hb, 1.0)
    if bi.sum() > 200:
        f["bright_internal_texture"] = float(np.median(sd1[bi]) / max(np.median(sd1[graphite_core]), 1e-6))
        f["bright_porous_share"] = float(np.mean(sd1[bi] > 2 * np.median(sd1[graphite_core])))
    edge = (lab == 2) & ~ndimage.binary_erosion(lab == 2)
    ring = ndimage.binary_dilation(lab == 2, iterations=2) & (lab != 2)
    f["bright_contact_pore"] = float(np.mean(lab[ring] == 0)) if ring.any() else np.nan
    f["bright_perimeter_per_area"] = float(edge.sum() / max((lab == 2).sum(), 1))

    # mixing patchiness of the bright phase at two scales (variance relative to a random binary field)
    phi = max(float(np.mean(lab == 2)), 1e-6)
    for t in (128, 256):
        ny, nx = lab.shape[0] // t, lab.shape[1] // t
        q = (lab[: ny * t, : nx * t] == 2).reshape(ny, t, nx, t).mean(axis=(1, 3))
        f[f"bright_patchiness_{t * 50 // 1000}um"] = float(q.std() / phi)

    # cross-view: what SE / InLens see inside BSE-defined pores and graphite
    pore_core = ndimage.binary_erosion(lab == 0, iterations=2)
    for v in ("SE", "InLens"):
        if v not in views:
            continue
        Hv = H_of(views[v], target[v])[: Hb.shape[0], : Hb.shape[1]]
        g_level = np.median(Hv[graphite_core])
        f[f"{v}_signal_in_pores"] = float(np.median(Hv[pore_core]) - g_level) if pore_core.any() else np.nan
        f[f"{v}_signal_in_cbd"] = float(np.median(Hv[cbd]) - g_level) if cbd.any() else np.nan
        f[f"{v}_signal_on_bright"] = float(np.median(Hv[bi]) - g_level) if bi.any() else np.nan
        wt = Hv - ndimage.grey_opening(Hv, size=(5, 5))
        f[f"{v}_graphite_bright_lines"] = float(np.mean(wt[gi] > 0.1))
    return f


def main():
    data = json.loads((OUT / "harmonized_features.json").read_text())
    target = data["target"]
    rows = index(ROOT)
    locs = {}
    for r in rows:
        locs.setdefault((r["batch"], r["location"]), {})[r["view"]] = r["path"]
    table = []
    for (b, l), views in sorted(locs.items()):
        table.append({"batch": b, "location": l, **features(views, target)})
        print(f"  {b} {l}", flush=True)
    (OUT / "material2.json").write_text(json.dumps(table, indent=1))


if __name__ == "__main__":
    main()
