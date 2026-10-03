"""
Group each batch's images into the fields of view they actually show.

The filename code (img_<code>_<detector>) does not identify the imaged field: views of one
field carry different codes, and files sharing a code often show different fields. The
detector suffix is unreliable too (one field can have three files all labelled BSE).
So fields are recovered from the pixels instead:

1. Each image is reduced to an edge map (gradient magnitude at ~200 nm/px). Edges sit at the
   same particle and pore boundaries whatever the detector contrast, so two views of one
   field line up even when one is compositional (BSE-like) and the other rim-lit (InLens/SE).
2. Every pair in a batch is phase-correlated. Unrelated images peak near 0.02; views of the
   same field peak at 0.06-0.5.
3. Pairs are merged strongest first (single linkage) while the score clears MATCH_SCORE
   and a field holds at most MAX_VIEWS views.

4. Each view's real detector is identified from its pixels (the filename suffix is ignored):
   - BSE: the only grainy view. Backscatter signal is weak, so its pixel noise relative to
     contrast is about 0.06-0.09, against at most 0.045 for the secondary-electron views.
   - ETD vs InLens: both are secondary-electron views. With the field's views pixel-aligned,
     the BSE phase map shows where the pores are. In the ETD view pores stay black (contrast
     below about -4 graphite IQRs); in the InLens view pores fill in (about -3 to 0) and
     particle rims glow. This orientation is calibrated on the corrected reference filenames,
     where it agrees with every ETD / InLens label. Without a BSE view, each SE view's own
     phase map is used. Files labelled "SE" are counted with the ETD class.
5. Each field gets one location name, so every view in a group shares it: the filename codes
   are assigned one-to-one to fields (optimal assignment). A code must have as many files as
   the field has views, codes already carried by the field's files are preferred, and ties go
   to the code of the field's BSE file. When the filenames are correct, every field's files
   share one code and the name is simply recovered; otherwise it is marked as assigned.
   Each view's label is its filename (img_ and extension dropped) when that agrees with the
   field's location and the identified detector, and location_detector otherwise.

Output: data/processed/fields/batch_N.json, used by batch_kpis.py and the image API.
Run directly to (re)build the manifests: python field_matching.py [--batches 1 2 3]
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import tifffile
from scipy import fft, ndimage
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "fields"
NAME = re.compile(r"^img_(?P<code>[^_]+)_(?P<detector>BSE|ETD|Inlens|SE)(?: \(\d+\))?\.tiff?$", re.I)

MATCH_SCORE = 0.045   # unrelated pairs score ~0.02; the weakest true matches seen score ~0.06
MAX_VIEWS = 3         # the acquisition gives every field at most three detector views
BIN = 8               # ~200 nm/px from 25 nm/px raw pixels
CROP = (200, 860)     # common crop (rows, cols) so every image has the same FFT size
STRONG, MODERATE = 0.15, 0.06
BSE_NOISE = 0.055     # relative pixel noise; BSE views 0.06-0.09, SE views <= 0.045
PORE_SPLIT = -4.0     # pore contrast (graphite IQRs): ETD <= -4.7, InLens >= -2.9 in the reference batches


def edge_map(path):
    """Windowed, standardised gradient magnitude of a downsampled grey image."""
    arr = tifffile.imread(path)
    if arr.ndim == 3:
        arr = arr[..., 1]
    arr = arr[:, :-2].astype(np.float32)
    h, w = arr.shape[0] // BIN * BIN, arr.shape[1] // BIN * BIN
    a = arr[:h, :w].reshape(h // BIN, BIN, w // BIN, BIN).mean(axis=(1, 3))[: CROP[0], : CROP[1]]
    a = ndimage.gaussian_filter(a, 1.0)
    g = np.hypot(ndimage.sobel(a, 0), ndimage.sobel(a, 1))
    g = (g - g.mean()) / (g.std() + 1e-9)
    return g * np.hanning(g.shape[0])[:, None] * np.hanning(g.shape[1])[None, :]


def read_grey(path, b=1):
    arr = tifffile.imread(path)
    if arr.ndim == 3:
        arr = arr[..., 1]
    a = arr[:, :-2].astype(np.float32) / (np.iinfo(arr.dtype).max if np.issubdtype(arr.dtype, np.integer) else 1.0)
    if b > 1:
        h, w = a.shape[0] // b * b, a.shape[1] // b * b
        a = a[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))
    return a


def relative_noise(img):
    """Immerkaer pixel-noise estimate on a central crop, relative to the 1-99% grey range."""
    h, w = img.shape
    c = img[h // 2 - 400: h // 2 + 400, w // 2 - 1000: w // 2 + 1000]
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    sigma = np.sqrt(np.pi / 2) * np.abs(ndimage.convolve(c, k)[1:-1, 1:-1]).mean() / 6
    lo, hi = np.percentile(img[::8, ::8], [1, 99])
    return float(sigma / max(hi - lo, 1e-6))


def phase_map(img):
    """Quick 3-class Otsu map (0 pore, 1 graphite, 2 bright) used only as a mask."""
    from skimage import filters
    sm = ndimage.gaussian_filter(img, 1.0)
    return np.digitize(sm, filters.threshold_multiotsu(sm[::4, ::4], classes=3))


def phase_contrast(img, labels):
    """Pore and bright-phase level relative to graphite, in graphite inter-quartile ranges."""
    h, w = min(img.shape[0], labels.shape[0]), min(img.shape[1], labels.shape[1])
    img, labels = img[:h, :w], labels[:h, :w]
    graphite = img[ndimage.binary_erosion(labels == 1, iterations=3)]
    mid = np.median(graphite)
    iqr = np.percentile(graphite, 75) - np.percentile(graphite, 25) + 1e-6
    level = lambda m: float((np.median(img[m]) - mid) / iqr) if m.any() else 0.0
    return {"pore": level(ndimage.binary_erosion(labels == 0)),
            "bright": level(ndimage.binary_erosion(labels == 2, iterations=2))}


def identify_detectors(paths):
    """Detector class per view of one field: 'BSE', 'InLens' or 'ETD', with evidence."""
    noise = [relative_noise(read_grey(p)) for p in paths]
    images = [read_grey(p, 4) for p in paths]
    bse = int(np.argmax(noise)) if max(noise) >= BSE_NOISE else None
    others = [i for i in range(len(paths)) if i != bse]
    masks = [phase_map(images[bse])] if bse is not None else [phase_map(images[i]) for i in others]
    contrast = {i: {k: float(np.mean([phase_contrast(images[i], m)[k] for m in masks])) for k in ("pore", "bright")}
                for i in others}
    result = [None] * len(paths)
    if bse is not None:
        second = max((noise[i] for i in others), default=0.0)
        result[bse] = {"detector": "BSE", "confidence": "high" if noise[bse] >= 1.3 * max(second, BSE_NOISE) else "moderate"}
    if len(others) == 2:
        a, b = sorted(others, key=lambda i: contrast[i]["pore"])
        gap = contrast[b]["pore"] - contrast[a]["pore"]
        sided = contrast[a]["pore"] <= PORE_SPLIT < contrast[b]["pore"]
        conf = "high" if sided and gap >= 2 else "moderate" if gap >= 1 else "low"
        result[a] = {"detector": "ETD", "confidence": conf}     # darker pores
        result[b] = {"detector": "InLens", "confidence": conf}
    for i in others:
        if result[i] is None:  # a lone SE view: judge it against the fixed split
            margin = abs(contrast[i]["pore"] - PORE_SPLIT)
            result[i] = {"detector": "ETD" if contrast[i]["pore"] <= PORE_SPLIT else "InLens",
                         "confidence": "moderate" if margin >= 1.5 else "low"}
    for i in range(len(paths)):
        result[i]["evidence"] = {"relative_noise": round(noise[i], 4),
                                 **({k: round(v, 2) for k, v in (("pore_contrast", contrast[i]["pore"]),
                                                                ("bright_contrast", contrast[i]["bright"]))}
                                    if i in contrast else {})}
    return result


def assign_locations(fields):
    """One filename code per field, used once each. Adds location, location_recovered and
    location_alternatives (other codes that would fit the field equally well)."""
    counts = {}
    for f in fields:
        for v in f["views"]:
            counts[v["filename_code"]] = counts.get(v["filename_code"], 0) + 1
    codes = sorted(counts)

    def score(f, code, tiebreak=True):
        overlap = sum(v["filename_code"] == code for v in f["views"])
        bse = any(v["filename_code"] == code and v["detector"] == "BSE" for v in f["views"])
        return 100 * (counts[code] == len(f["views"])) + 10 * overlap + (bse if tiebreak else 0)

    base = np.array([[score(f, c, False) for c in codes] for f in fields], float)
    full = np.array([[score(f, c) for c in codes] for f in fields], float)
    rows, cols = linear_sum_assignment(-full)
    best = base[rows, cols].sum()
    for i, j in zip(rows, cols):
        alternatives = []
        for k in range(len(codes)):
            if k == j:
                continue
            forced = base.copy()
            forced[i, :] = -1e6
            forced[i, k] = base[i, k]
            r2, c2 = linear_sum_assignment(-forced)
            if forced[r2, c2].sum() >= best:  # an equally good assignment gives this field another code
                alternatives.append(codes[k])
        f = fields[i]
        f["location"] = codes[j]
        f["location_recovered"] = not alternatives
        f["location_alternatives"] = alternatives
        for v in f["views"]:
            label = {"SE": "ETD", "INLENS": "INLENS"}.get(v["filename_detector"], v["filename_detector"])
            v["label_matches_image"] = v["filename_code"] == codes[j] and label == v["detector"].upper()
            v["display_name"] = (re.sub(r"^img_|\.tiff?$", "", v["filename"], flags=re.I)
                                 if v["label_matches_image"] else f"{codes[j]}_{v['detector']}")


def phase_correlation(fa, fb):
    """Peak of the normalised cross-power spectrum, and the (dy, dx) shift of b relative to a."""
    cross = fa * np.conj(fb)
    corr = np.real(fft.ifft2(cross / (np.abs(cross) + 1e-9)))
    dy, dx = np.unravel_index(corr.argmax(), corr.shape)
    h, w = corr.shape
    return float(corr.max()), [int(dy - h if dy > h // 2 else dy) * BIN, int(dx - w if dx > w // 2 else dx) * BIN]


def group_fields(scores):
    """Strongest-first merging with a size cap. Returns a list of index lists."""
    n = len(scores)
    field = list(range(n))
    members = {i: [i] for i in range(n)}
    pairs = sorted(((scores[i, j], i, j) for i in range(n) for j in range(i + 1, n)), reverse=True)
    for s, i, j in pairs:
        if s < MATCH_SCORE:
            break
        a, b = field[i], field[j]
        if a == b or len(members[a]) + len(members[b]) > MAX_VIEWS:
            continue
        for k in members[b]:
            field[k] = a
        members[a] += members.pop(b)
    return sorted((sorted(m) for m in members.values()), key=lambda m: m[0])


def match_batch(batch):
    files = sorted(p for p in (RAW / f"batch_{batch}").iterdir() if NAME.match(p.name))
    spectra = [fft.fft2(edge_map(p)) for p in files]
    n = len(files)
    scores, shifts = np.zeros((n, n)), {}
    for i in range(n):
        for j in range(i + 1, n):
            scores[i, j], shifts[i, j] = phase_correlation(spectra[i], spectra[j])
            scores[j, i] = scores[i, j]
    groups = group_fields(scores)
    in_field = {i: g for g in groups for i in g}
    fields = []
    for number, idx in enumerate(groups, 1):
        links = [scores[i, j] for a, i in enumerate(idx) for j in idx[a + 1:]]
        # Weakest view-to-field link: each view's best score to another member of its field.
        support = min((max(scores[i, j] for j in idx if j != i) for i in idx), default=0.0)
        outside = max((scores[i, j] for i in idx for j in range(n) if j not in idx), default=0.0)
        anchor = idx[0]
        detectors = identify_detectors([files[i] for i in idx])
        fields.append({
            "field_id": f"F{number:02d}",
            "views": [{"filename": files[i].name,
                       "filename_code": NAME.match(files[i].name)["code"],
                       "filename_detector": NAME.match(files[i].name)["detector"].upper(),
                       "detector": det["detector"], "detector_confidence": det["confidence"],
                       "detector_evidence": det["evidence"],
                       # idx is sorted, so the anchor (first view) always has the lower index.
                       "offset_px": [0, 0] if i == anchor else shifts[anchor, i]}
                      for i, det in zip(idx, detectors)],
            "detectors": sorted(det["detector"] for det in detectors),
            "filename_codes": sorted({NAME.match(files[i].name)["code"] for i in idx}),
            "match_score_min": float(support) if len(idx) > 1 else None,
            "pair_scores": [round(float(s), 3) for s in links],
            "best_outside_score": float(outside),
            "confidence": ("single view" if len(idx) == 1 else
                           "strong" if support >= STRONG else
                           "moderate" if support >= MODERATE else "weak"),
        })
    assign_locations(fields)
    unrelated = np.array([scores[i, j] for i in range(n) for j in range(i + 1, n) if in_field[i] is not in_field[j]])
    manifest = {
        "batch_id": str(batch), "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Phase correlation of edge maps (~200 nm/px); strongest-first merging, "
                  f"score ≥ {MATCH_SCORE}, at most {MAX_VIEWS} views per field.",
        "note": "Filename codes and detector suffixes do not identify fields or detectors; both are "
                "recovered from the images.",
        "detector_method": f"BSE: relative pixel noise ≥ {BSE_NOISE}. ETD vs InLens: pore contrast against "
                           f"the field's BSE phase map, ETD ≤ {PORE_SPLIT} < InLens.",
        "unrelated_pair_scores": {"median": float(np.median(unrelated)), "max": float(unrelated.max())},
        "fields": fields,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"batch_{batch}.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def load_or_match(batch, rebuild=False):
    """Cached manifest unless it is missing, older than the newest raw image, or rebuild is set."""
    path = OUT / f"batch_{batch}.json"
    raw = [p for p in (RAW / f"batch_{batch}").iterdir() if NAME.match(p.name)]
    if not rebuild and path.is_file() and path.stat().st_mtime >= max(p.stat().st_mtime for p in raw):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if ({v["filename"] for f in manifest["fields"] for v in f["views"]} == {p.name for p in raw}
                and all("location" in f for f in manifest["fields"])):
            return manifest
    return match_batch(batch)


def main():
    ap = argparse.ArgumentParser(description="Group batch images into the fields they show.")
    ap.add_argument("--batches", nargs="+", default=["1", "2", "3"])
    args = ap.parse_args()
    for batch in args.batches:
        m = match_batch(batch)
        sizes = [len(f["views"]) for f in m["fields"]]
        print(f"batch {batch}: {len(sizes)} fields (views per field {sorted(sizes, reverse=True)}); "
              f"unrelated pairs max {m['unrelated_pair_scores']['max']:.3f}")
        for f in m["fields"]:
            print(f"  {f['field_id']} {f['location']} ({'recovered' if f['location_recovered'] else 'assigned'}) "
                  + ", ".join(f"{v['filename_code']}_{v['filename_detector']} -> {v['detector']} "
                              f"({v['detector_confidence']})" for v in f["views"]))


if __name__ == "__main__":
    main()
