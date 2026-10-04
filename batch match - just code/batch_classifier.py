"""
Which batch is an SEM image from?  Answers Batch_1, Batch_2, Batch_3 - or "unsure".

1. KNOWN-LOCATION MATCHER. Every reference image is kept as an edge map (8x binned). A query
   (any view, or a crop) that shows a spot already in the reference set is found by
   cross-correlation and gets that location's batch (certain). Works across detectors.
2. TWO SIGNALS for a location never seen before, both from the image alone, one model per view:
     imaging fingerprint - noise per phase, noise correlation along / across the scan, contrast
                           ratios, sharpness, stripes, clipping, histogram comb (shrinkage LDA)
     texture             - local binary patterns, co-occurrence texture, power spectrum on
                           12.8 um tiles (logistic regression; image = mean over its tiles)
   Each is calibrated (temperature scaling) and the two probabilities are averaged.
3. MATERIAL RANGE RULE (BSE images). Pore / graphite / bright-phase percentages with GET4's 95%
   error bars: if they fall inside only Batch_1's or only Batch_2's range, that is the answer
   (unless the models point to Batch_3).
4. UNSURE. A model answer is only given at a confidence where answers on held-out locations
   were at least 90% right; below that the result is "unsure" (the leaning is shown).

--forced: always answer, with the model that is best at forced choice: Batch_3 or not
(fingerprint) -> material range rule -> Batch_1 vs Batch_2 specialist (fingerprint).
Held out: 74% of single images, 77% of locations; its confidence is not reliable, so the
default mode above is better whenever "unsure" is an acceptable answer.

The batches have the same measurable microstructure; the models mostly recognise how each batch
was imaged, which only carries over to new images from the same imaging sessions.

Accuracy is measured leave-one-LOCATION-out and nested: calibration and thresholds are chosen
without the tested location. Never test on training images - predict refuses them.

    python batch_classifier.py evaluate             # honest accuracy (about 5 minutes)
    python batch_classifier.py train                # fit on everything, save model + references
    python batch_classifier.py predict IMG.tif ...  # which batch? (view read from filename)
    python batch_classifier.py train --exclude ID   # fair spot check: leave location ID out, then predict it
    python batch_classifier.py predict --forced IMG.tif ...   # always answer (two-step model)
    python batch_classifier.py evaluate --forced              # its honest accuracy
"""

import argparse
import json
import pickle
import re
from pathlib import Path

import numpy as np
import tifffile
from scipy import fft, ndimage
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from skimage import feature, filters

import GET4

HERE = Path(__file__).parent
ROOT = HERE / "data" / "batches"
OUT = HERE / "out" / "classifier"
VIEW_OF = {"BSE": "BSE", "ETD": "SE", "SE": "SE", "INLENS": "InLens"}
VIEWS = ["BSE", "SE", "InLens"]
EDGE = 8                      # stitching artefact columns at left / right edges
MATCH_BIN = 8
MATCH_THRESHOLD = 15.0        # peak height in SDs; unrelated locations stayed <= 10.7 in testing
SELF_MATCH = 500.0            # an image matched against itself scores ~1000; crops of other views 30-250
TARGET_ACCURACY = 0.90        # model answers below this held-out accuracy become "unsure"
RANGE_Z = 2.0                 # material range rule uses GET4's 95% error bars
RANGE_BATCHES = ("Batch_1", "Batch_2")
MATERIAL_PX_NM = 25.0         # material percentages are measured at this pixel size
K_IMMERKAER = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
LAGS = [(0, 1), (0, 2), (0, 3), (1, 0), (2, 0), (1, 1)]


# ---------------------------------------------------------------- data

def parse_name(path):
    m = re.match(r"img_(\w+?)_(BSE|ETD|SE|Inlens)$", Path(path).stem, re.I)
    if not m:
        raise ValueError(f"cannot read location/view from {Path(path).name} (expected img_<id>_<view>.tif)")
    return m[1], VIEW_OF[m[2].upper()]


def index(root):
    rows = []
    for p in sorted(root.glob("*/*.tif")):
        loc, view = parse_name(p)
        rows.append({"path": p, "batch": p.parent.name, "location": loc, "view": view})
    return rows


def load_u8(path):
    a = tifffile.imread(path)
    g = a[..., 0] if a.ndim == 3 else a
    if g.dtype != np.uint8:
        g = np.clip(g.astype(np.float32) / g.max() * 255, 0, 255).astype(np.uint8)
    return g[:, EDGE:-EDGE] if g.shape[1] > 4 * EDGE else g


# ---------------------------------------------------------------- 1. known-location matcher

def edge_map(u8, binning=MATCH_BIN):
    g = u8.astype(np.float32)
    h, w = g.shape[0] // binning * binning, g.shape[1] // binning * binning
    g = g[:h, :w].reshape(h // binning, binning, w // binning, binning).mean(axis=(1, 3))
    g = ndimage.gaussian_gradient_magnitude(g, 1.0)
    g -= ndimage.gaussian_filter(g, 10)
    return ((g - g.mean()) / (g.std() + 1e-6)).astype(np.float32)


def match_score(query, ref):
    H, W = ref.shape[0] + query.shape[0], ref.shape[1] + query.shape[1]
    x = fft.rfft2(ref, s=(H, W), workers=-1) * np.conj(fft.rfft2(query, s=(H, W), workers=-1))
    c = fft.irfft2(x / (np.abs(x) + 1e-6 * np.abs(x).mean()), s=(H, W), workers=-1)
    return float((c.max() - c.mean()) / c.std())


def find_known_location(u8, references):
    """(score, batch, location) of the best-matching reference image."""
    q = edge_map(u8)
    return max((match_score(q, r["edges"]), r["batch"], r["location"]) for r in references)


# ---------------------------------------------------------------- 2a. imaging fingerprint

def fingerprint(u8):
    img = u8.astype(np.float32)
    sm = ndimage.gaussian_filter(img, 2.0)
    labels = np.digitize(sm, filters.threshold_multiotsu(sm[::4, ::4], classes=3))
    interior = [ndimage.binary_erosion(labels == k, iterations=4) for k in range(3)]
    med = [float(np.median(img[m])) if m.sum() > 1000 else np.nan for m in interior]
    contrast = max(abs(med[1] - med[0]), 1.0) if np.isfinite(med[0] + med[1]) else 1.0
    p1, p99 = np.percentile(img[::4, ::4], [1, 99])
    spread = max(p99 - p1, 1.0)
    f = {f"fraction_{k}": float(np.mean(labels == k)) for k in range(3)}
    f["contrast_over_spread"] = contrast / spread
    f["bright_ratio"] = (med[2] - med[0]) / contrast
    resid = ndimage.convolve(img, K_IMMERKAER)
    for k, m in enumerate(interior):
        ok = m.sum() > 1000
        f[f"sd_{k}"] = float(np.std(img[m]) / contrast) if ok else np.nan
        sd = np.sqrt(np.pi / 2) * np.abs(resid[m]).mean() / 6 if ok else np.nan
        f[f"noise_{k}"] = sd / spread
        f[f"noise_rel_{k}"] = sd / max(med[k], 1.0) if ok else np.nan
    f["nlf_slope"] = f["noise_1"] / max(f["noise_0"], 1e-6)

    m = interior[1]
    hp = img - ndimage.uniform_filter(img, 7)
    base = (hp[m] ** 2).mean()
    for dy, dx in LAGS:
        mm = m[dy:, dx:] & m[: m.shape[0] - dy, : m.shape[1] - dx]
        f[f"ncorr_{dy}{dx}"] = float((hp[dy:, dx:][mm] * hp[: hp.shape[0] - dy, : hp.shape[1] - dx][mm]).mean() / base)

    g07 = ndimage.gaussian_filter(img, 0.7)
    gx, gy = ndimage.sobel(g07, 1), ndimage.sobel(g07, 0)
    f["sharpness"] = float(np.percentile(np.hypot(gx, gy)[::2, ::2], 99) / spread)
    f["grad_anisotropy"] = float(np.sqrt((gx ** 2).mean() / max((gy ** 2).mean(), 1e-9)))
    s = GET4.stripe_index(img / 255.0)
    f["curtaining"], f["scan_lines"] = s["curtaining"], s["scan_lines"]

    h = np.bincount(u8.ravel(), minlength=256)
    lo, hi = np.searchsorted(np.cumsum(h) / h.sum(), [0.01, 0.99])
    f["empty_levels"] = float(np.mean(h[lo: hi + 1] == 0))
    f["clip_low"], f["clip_high"] = float(h[0] / h.sum()), float(h[255] / h.sum())
    return f


FEATURES = None  # fixed order, set on first use


def vector(f):
    global FEATURES
    FEATURES = FEATURES or sorted(f)
    return np.array([f.get(k, np.nan) for k in FEATURES], float)


def build_features(rows, cache=OUT / "fingerprints.json"):
    known = json.loads(cache.read_text()) if cache.exists() else {}
    for i, r in enumerate(rows):
        key = str(r["path"])
        if key not in known:
            known[key] = fingerprint(load_u8(r["path"]))
            print(f"  fingerprint {i + 1}/{len(rows)} {r['batch']}/{r['path'].name}", flush=True)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(known))
    return np.array([vector(known[str(r["path"])]) for r in rows])


# ---------------------------------------------------------------- 2b. texture

TEX_BIN, TEX_TILE = 2, 256
_TEX_EDGES = np.geomspace(1 / 128, 0.5, 9)
_TEX_BINS = np.digitize(np.hypot(fft.fftfreq(TEX_TILE)[:, None], fft.fftfreq(TEX_TILE)[None, :]), _TEX_EDGES)
_HANN = np.outer(np.hanning(TEX_TILE), np.hanning(TEX_TILE))


def texture_tile(t):
    z = (t - t.mean()) / (t.std() + 1e-6)
    p = np.abs(fft.fft2(z * _HANN)) ** 2
    spectrum = np.log([p[_TEX_BINS == k].mean() for k in range(1, len(_TEX_EDGES))])
    spectrum -= spectrum.mean()
    g = filters.sobel(ndimage.gaussian_filter(z, 1.0))
    u8 = np.clip(t * 255, 0, 255).astype(np.uint8)
    lbp1 = np.bincount(feature.local_binary_pattern(u8, 8, 1, "uniform").astype(int).ravel(), minlength=10) / u8.size
    lbp4 = np.bincount(feature.local_binary_pattern(u8, 16, 4, "uniform").astype(int).ravel(), minlength=18) / u8.size
    q = np.searchsorted(np.quantile(t, np.linspace(0, 1, 17)[1:-1]), t).astype(np.uint8)
    glcm = feature.graycomatrix(q, [1, 4, 16], [0, np.pi / 2], levels=16, symmetric=True, normed=True)
    co = np.concatenate([feature.graycoprops(glcm, prop).mean(axis=1)
                         for prop in ("contrast", "homogeneity", "correlation", "energy")])
    sm = ndimage.gaussian_filter(t, 1.0)
    try:
        lab = np.digitize(sm, filters.threshold_multiotsu(sm, classes=3))
        phases = np.bincount(lab.ravel(), minlength=3) / lab.size
    except ValueError:  # flat tile
        phases = np.array([0.0, 1.0, 0.0])
    return np.concatenate([spectrum, [g.mean(), g.std(), np.percentile(g, 90)], lbp1, lbp4, co, phases])


def texture_tiles(u8):
    a = u8.astype(np.float32) / 255
    h, w = a.shape[0] // TEX_BIN * TEX_BIN, a.shape[1] // TEX_BIN * TEX_BIN
    a = a[:h, :w].reshape(h // TEX_BIN, TEX_BIN, w // TEX_BIN, TEX_BIN).mean(axis=(1, 3))
    ny, nx = a.shape[0] // TEX_TILE, a.shape[1] // TEX_TILE
    y0, x0 = (a.shape[0] - ny * TEX_TILE) // 2, (a.shape[1] - nx * TEX_TILE) // 2
    return np.array([texture_tile(a[y0 + i * TEX_TILE: y0 + (i + 1) * TEX_TILE, x0 + j * TEX_TILE: x0 + (j + 1) * TEX_TILE])
                     for i in range(ny) for j in range(nx)])


def build_texture(rows, cache=OUT / "texture_features.npz"):
    """Tile texture features of every image (cached per image) -> (tiles x features, image index of each tile)."""
    known = {}
    if cache.exists():
        d = np.load(cache)
        for i, p in enumerate(d["paths"]):
            known[str(p)] = d["X"][d["image_of_tile"] == i]
    new = False
    for i, r in enumerate(rows):
        if str(r["path"]) not in known:
            known[str(r["path"])] = texture_tiles(load_u8(r["path"])).astype(np.float32)
            new = True
            print(f"  texture {i + 1}/{len(rows)} {r['batch']}/{r['path'].name}", flush=True)
    if new:
        keys = sorted(known)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, X=np.vstack([known[k] for k in keys]), paths=np.array(keys),
                 image_of_tile=np.concatenate([np.full(len(known[k]), j) for j, k in enumerate(keys)]))
    tiles = [known[str(r["path"])] for r in rows]
    return np.vstack(tiles).astype(np.float32), np.concatenate([np.full(len(t), i) for i, t in enumerate(tiles)])


# ---------------------------------------------------------------- 3. material percentages (GET4)

def material_percentages(path):
    """Pore / graphite / bright-phase fraction and its sampling SE, measured exactly as GET4 does."""
    meta = GET4.read_meta(path)
    px = meta["pixel_size_nm"]
    img, _ = GET4.load_image(path, meta, px_nm=px, target_nm=MATERIAL_PX_NM if px else None, bin_factor=1)
    quality = GET4.image_quality(img)
    img, _ = GET4.flatten_shading(img)
    img, _ = GET4.destripe(img, quality)
    labels, _, _ = GET4.segment_bse(img)
    h, w = labels.shape
    tile = None if h * w <= GET4.FULL_FFT_MAX_PX else GET4.FFT_TILE
    max_lag = min(h, w) // 2 if tile is None else GET4.FFT_TILE // 2
    sizes = np.unique(np.geomspace(4, min(h, w) // 2, 16).astype(int))
    out = {}
    for k, name in GET4.PHASES.items():
        r = GET4.analyse_phase(labels == k, max_lag, tile, sizes, 1.0)
        out[name] = [r["phi"], r["se_image"]]
    return out


def build_materials(rows, cache=OUT / "material_percentages.json"):
    """Per location (its BSE image): {phase: [fraction, SE]}. Reuses GET4 reports in out/get4 if present."""
    known = json.loads(cache.read_text()) if cache.exists() else {}
    for r in rows:
        key = str(r["path"])
        if r["view"] != "BSE" or key in known:
            continue
        report = HERE / "out" / "get4" / r["batch"] / f"{r['path'].stem}_uncertainty.json"
        if report.exists():
            known[key] = {k: [v["phi"], v["se_image"]] for k, v in json.loads(report.read_text())["phases"].items()}
        else:
            print(f"  material percentages (GET4) {r['batch']}/{r['path'].name}", flush=True)
            known[key] = material_percentages(r["path"])
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known))
    return {r["location"]: known[str(r["path"])] for r in rows if r["view"] == "BSE"}


def material_ranges(materials, batch_of, locations):
    return {b: {name: (min(materials[l][name][0] for l in locations if batch_of[l] == b),
                       max(materials[l][name][0] for l in locations if batch_of[l] == b))
                for name in GET4.PHASES.values()}
            for b in RANGE_BATCHES}


def exclusive_phases(m, ranges):
    """{phase: batch} for every phase whose value (+- RANGE_Z SE) lies inside only one batch's range."""
    out = {}
    for name, (phi, se) in m.items():
        lo, hi = phi - RANGE_Z * se, phi + RANGE_Z * se
        inside = [b for b, r in ranges.items() if hi >= r[name][0] and lo <= r[name][1]]
        if len(inside) == 1:
            out[name] = inside[0]
    return out


def range_vote(m, ranges):
    votes = set(exclusive_phases(m, ranges).values())
    return votes.pop() if len(votes) == 1 else None


# ---------------------------------------------------------------- models, calibration, decisions

def make_model():
    return make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"))


def make_texture_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=5000))


def fill_nan(X, means):
    return np.where(np.isfinite(X), X, means)


def fit_view(X, y):
    means = np.nanmean(X, axis=0)
    return make_model().fit(fill_nan(X, means), y), means


def log_proba(model, means, X, batches):
    p = np.full((len(X), len(batches)), 1e-6)
    p[:, np.searchsorted(batches, model.classes_)] = np.clip(model.predict_proba(fill_nan(X, means)), 1e-6, 1)
    lp = np.log(p)
    return lp - np.log(np.exp(lp).sum(axis=1, keepdims=True))


def tile_log_proba(model, X_tiles, batches):
    p = np.full((len(X_tiles), len(batches)), 1e-6)
    p[:, np.searchsorted(batches, model.classes_)] = np.clip(model.predict_proba(X_tiles), 1e-6, 1)
    lp = np.log(p).mean(axis=0)
    return lp - lp.max() - np.log(np.exp(lp - lp.max()).sum())


def softmax(lp):
    e = np.exp(lp - lp.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


TEMPS = np.geomspace(0.3, 300, 60)


def fit_temperature(lp, y):
    nll = [-np.log(softmax(lp / t)[np.arange(len(y)), y] + 1e-12).mean() for t in TEMPS]
    return float(TEMPS[int(np.argmin(nll))])


def combine(lf, lt, cal):
    return 0.5 * (softmax(lf / cal["T_fingerprint"]) + softmax(lt / cal["T_texture"]))


def location_proba(ps):
    return softmax(np.sum(np.log(np.clip(ps, 1e-9, 1)), axis=0))


def choose_threshold(conf, right, min_answers):
    """Lowest confidence from which every higher threshold still gives >= TARGET_ACCURACY right."""
    grid = np.round(np.arange(0.34, 1.0, 0.01), 2)
    ok = [right[conf >= t].mean() >= TARGET_ACCURACY if np.sum(conf >= t) >= min_answers else True for t in grid]
    for i, t in enumerate(grid):
        if all(ok[i:]) and np.sum(conf >= t) >= min_answers:
            return float(t)
    return 1.01  # never confident enough: always unsure


def decide(p, threshold, vote, batches):
    """(answer, how). A material range vote wins unless the models point to Batch_3."""
    names = list(batches)
    if vote and ("Batch_3" not in names or p[names.index("Batch_3")] < 0.5):
        return vote, "material"
    k = int(np.argmax(p))
    return (batches[k], "model") if p[k] >= threshold else ("unsure", "model")


class Data:
    def __init__(self, rows, Xf, Xt, owner, materials):
        self.rows, self.Xf, self.Xt, self.owner, self.materials = rows, Xf, Xt, owner, materials
        self.batch = np.array([r["batch"] for r in rows], dtype=object)
        self.loc = np.array([r["location"] for r in rows])
        self.view = np.array([r["view"] for r in rows])
        self.batches = np.array(sorted(set(self.batch)), dtype=object)
        self.batch_of = dict(zip(self.loc, self.batch))


def fit_models(D, train):
    models = {}
    for v in VIEWS:
        tr = train & (D.view == v)
        tiles = np.isin(D.owner, np.nonzero(tr)[0])
        models[v] = (fit_view(D.Xf[tr], D.batch[tr]),
                     make_texture_model().fit(D.Xt[tiles], D.batch[D.owner[tiles]]))
    return models


def raw_scores(D, models, i):
    (fp, means), tx = models[D.view[i]]
    return log_proba(fp, means, D.Xf[i:i + 1], D.batches)[0], tile_log_proba(tx, D.Xt[D.owner == i], D.batches)


def held_out_scores(D, train, locations):
    """Scores of every image of each location, from models fitted on `train` minus that location."""
    out = {}
    for l in locations:
        models = fit_models(D, train & (D.loc != l))
        for i in np.nonzero(D.loc == l)[0]:
            out[i] = raw_scores(D, models, i)
    return out


def calibrate(D, scores):
    """Temperatures and answer thresholds from held-out scores {image index: (fingerprint, texture)}."""
    idx = np.array(sorted(scores))
    y = np.searchsorted(D.batches, D.batch[idx])
    lf, lt = np.array([scores[i][0] for i in idx]), np.array([scores[i][1] for i in idx])
    cal = {"T_fingerprint": fit_temperature(lf, y), "T_texture": fit_temperature(lt, y)}
    p = np.array([combine(a, b, cal) for a, b in zip(lf, lt)])
    cal["threshold_image"] = choose_threshold(p.max(1), p.argmax(1) == y, min_answers=5)
    locs = sorted(set(D.loc[idx]))
    pl = np.array([location_proba(p[D.loc[idx] == l]) for l in locs])
    yl = np.searchsorted(D.batches, np.array([D.batch_of[l] for l in locs], dtype=object))
    cal["threshold_location"] = choose_threshold(pl.max(1), pl.argmax(1) == yl, min_answers=3)
    return cal


def evaluate(D):
    locs = sorted(set(D.loc))
    img_rec, loc_rec = [], []
    for n, l in enumerate(locs):
        train = D.loc != l
        cal = calibrate(D, held_out_scores(D, train, [m for m in locs if m != l]))  # never sees location l
        models = fit_models(D, train)
        ranges = material_ranges(D.materials, D.batch_of,
                                 [m for m in locs if m != l and D.batch_of[m] in RANGE_BATCHES])
        vote = range_vote(D.materials[l], ranges) if l in D.materials else None
        ps = []
        for i in np.nonzero(D.loc == l)[0]:
            p = combine(*raw_scores(D, models, i), cal)
            ps.append(p)
            ans, how = decide(p, cal["threshold_image"], vote if D.view[i] == "BSE" else None, D.batches)
            img_rec.append({"truth": D.batch[i], "answer": ans, "how": how, "item": D.rows[i]["path"].name,
                            "confidence": float(p.max()), "leaning": D.batches[p.argmax()]})
        p = location_proba(np.array(ps))
        ans, how = decide(p, cal["threshold_location"], vote, D.batches)
        loc_rec.append({"truth": D.batch_of[l], "answer": ans, "how": how, "item": l,
                        "confidence": float(p.max()), "leaning": D.batches[p.argmax()]})
        print(f"  {n + 1}/{len(locs)} {l} ({D.batch_of[l]}): {ans}{' (material)' if how == 'material' else ''}"
              f"   [thresholds: image {cal['threshold_image']:.2f}, location {cal['threshold_location']:.2f}]", flush=True)
    result = {"single_images": summarise(img_rec, D.batches, "SINGLE IMAGES"),
              "locations": summarise(loc_rec, D.batches, "LOCATIONS (all views combined)")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evaluation.json").write_text(json.dumps(result, indent=2, default=str))


def summarise(rec, batches, title):
    truth = np.array([r["truth"] for r in rec], dtype=object)
    ans = np.array([r["answer"] for r in rec], dtype=object)
    lean = np.array([r["leaning"] for r in rec], dtype=object)
    answered = ans != "unsure"
    right = answered & (ans == truth)
    print(f"\n{title}: answered {answered.sum()}/{len(rec)} ({100 * answered.mean():.0f}%), "
          f"correct among answered {right.sum()}/{answered.sum()} ({100 * right.sum() / max(answered.sum(), 1):.0f}%)"
          f";  if forced to always answer: {100 * np.mean(lean == truth):.0f}%")
    per = {}
    for b in batches:
        m = truth == b
        per[b] = {"n": int(m.sum()), "answered": int((answered & m).sum()), "right": int((right & m).sum()),
                  "wrong": int((answered & m & ~right).sum()), "unsure": int((~answered & m).sum())}
        print(f"  {b}: {per[b]['right']} right, {per[b]['wrong']} wrong, {per[b]['unsure']} unsure  (of {per[b]['n']})")
    wrong = [f"{r['item']} ({r['truth']} -> {r['answer']}, {r['how']}"
             + (f", {100 * r['confidence']:.0f}%)" if np.isfinite(r["confidence"]) else ")")
             for r in rec if r["answer"] not in ("unsure", r["truth"])]
    print("  wrong answers: " + ("; ".join(wrong) if wrong else "none"))
    return {"answered": int(answered.sum()), "n": len(rec), "right": int(right.sum()), "per_batch": per, "wrong": wrong}


# ---------------------------------------------------------------- forced mode: two-step model

STEP1 = np.array(["B12", "B3"], dtype=object)
STEP2 = np.array(RANGE_BATCHES, dtype=object)


def fit_two_step(D, train):
    """Per view: a Batch_3-or-not model and a Batch_1-vs-Batch_2 specialist (imaging fingerprint)."""
    is3 = np.where(D.batch == "Batch_3", "B3", "B12").astype(object)
    models = {}
    for v in VIEWS:
        tr = train & (D.view == v)
        t12 = tr & np.isin(D.batch, RANGE_BATCHES)
        models[v] = (fit_view(D.Xf[tr], is3[tr]), fit_view(D.Xf[t12], D.batch[t12]))
    return models


def two_step_scores(models, view, x):
    (m1, mu1), (m2, mu2) = models[view]
    return log_proba(m1, mu1, x[None], STEP1)[0], log_proba(m2, mu2, x[None], STEP2)[0]


def forced_answer(l1, l2, vote):
    """Batch_3 if step 1 says so; otherwise the material range rule if it fires; otherwise the specialist."""
    if l1[1] >= l1[0]:
        return "Batch_3", "step 1: Batch_3 or not"
    if vote:
        return vote, "material range rule"
    return STEP2[int(np.argmax(l2))], "Batch_1 vs Batch_2 specialist"


def evaluate_forced(D):
    """Leave-one-location-out accuracy of the forced (always answer) two-step model."""
    locs = sorted(set(D.loc))
    img_rec, loc_rec = [], []
    for l in locs:
        models = fit_two_step(D, D.loc != l)
        ranges = material_ranges(D.materials, D.batch_of,
                                 [m for m in locs if m != l and D.batch_of[m] in RANGE_BATCHES])
        vote = range_vote(D.materials[l], ranges) if l in D.materials else None
        s = {i: two_step_scores(models, D.view[i], D.Xf[i]) for i in np.nonzero(D.loc == l)[0]}
        for i, (l1, l2) in s.items():
            ans, how = forced_answer(l1, l2, vote if D.view[i] == "BSE" else None)
            img_rec.append({"truth": D.batch[i], "answer": ans, "how": how, "item": D.rows[i]["path"].name,
                            "confidence": float("nan"), "leaning": ans})
        ans, how = forced_answer(sum(x[0] for x in s.values()), sum(x[1] for x in s.values()), vote)
        loc_rec.append({"truth": D.batch_of[l], "answer": ans, "how": how, "item": l,
                        "confidence": float("nan"), "leaning": ans})
    print("\nForced mode (always answers), leave-one-location-out:")
    result = {"single_images": summarise(img_rec, D.batches, "SINGLE IMAGES"),
              "locations": summarise(loc_rec, D.batches, "LOCATIONS (all views combined)")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evaluation_forced.json").write_text(json.dumps(result, indent=2, default=str))


def train(D):
    locs = sorted(set(D.loc))
    everything = np.ones(len(D.rows), bool)
    cal = calibrate(D, held_out_scores(D, everything, locs))  # thresholds from held-out predictions only
    references = [{"batch": r["batch"], "location": r["location"], "view": r["view"],
                   "edges": edge_map(load_u8(r["path"])).astype(np.float16)} for r in D.rows]
    bundle = {"models": fit_models(D, everything), "two_step": fit_two_step(D, everything),
              "calibration": cal, "features": FEATURES,
              "batches": list(D.batches), "references": references,
              "ranges": material_ranges(D.materials, D.batch_of, [l for l in locs if D.batch_of[l] in RANGE_BATCHES]),
              "training_images": {r["path"].name: r["batch"] for r in D.rows}}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "batch_model.pkl", "wb") as fh:
        pickle.dump(bundle, fh)
    print(f"saved {OUT / 'batch_model.pkl'} ({len(locs)} locations, {len(D.rows)} images); answer thresholds: "
          f"image {cal['threshold_image']:.2f}, location {cal['threshold_location']:.2f}")


# ---------------------------------------------------------------- predict

def describe(name, view, ans, how, p, batches, threshold, m=None, ranges=None):
    if how == "material":
        why = []
        for k, b in exclusive_phases(m, ranges).items():
            o = next(x for x in ranges if x != b)
            why.append(f"{k} {100 * m[k][0]:.1f}% +- {200 * m[k][1]:.1f} overlaps only {b}'s range "
                       f"({100 * ranges[b][k][0]:.1f}-{100 * ranges[b][k][1]:.1f}%), "
                       f"not {o}'s ({100 * ranges[o][k][0]:.1f}-{100 * ranges[o][k][1]:.1f}%)")
        return f"{name} ({view}): {ans}  - material: " + "; ".join(why)
    lean = batches[int(np.argmax(p))]
    if ans == "unsure":
        return (f"{name} ({view}): unsure  - leaning {lean} ({100 * p.max():.0f}%), below the "
                f"{100 * threshold:.0f}% at which answers were {100 * TARGET_ACCURACY:.0f}%+ right")
    return f"{name} ({view}): {ans}  - confidence {100 * p.max():.0f}%"


def predict(paths, forced=False):
    global FEATURES
    with open(OUT / "batch_model.pkl", "rb") as fh:
        bundle = pickle.load(fh)
    FEATURES = bundle["features"]
    batches = np.array(bundle["batches"], dtype=object)
    cal, ranges, training = bundle["calibration"], bundle["ranges"], bundle["training_images"]
    refs = [dict(r, edges=r["edges"].astype(np.float32)) for r in bundle["references"]]
    groups = {}
    for path in paths:
        name = Path(path).name
        loc, view = parse_name(path)
        refuse = "part of the training data" if name in training else None
        u8 = None
        if not refuse:
            u8 = load_u8(path)
            score, mbatch, mloc = find_known_location(u8, refs)
            if score >= SELF_MATCH:
                refuse = f"identical to a training image of location {mloc}"
        if refuse:
            print(f"{name}: {refuse} - not predicted; a model tested on its own training images gives a meaningless result")
            continue
        g = groups.setdefault(loc, {"ps": [], "l1": 0.0, "l2": 0.0, "vote": None, "known": None, "m": None, "n": 0})
        g["n"] += 1
        if score >= MATCH_THRESHOLD:
            print(f"{name} ({view}): {mbatch}  - known location {mloc} (match {score:.0f} SD), certain")
            g["known"] = mbatch
            continue
        x = vector(fingerprint(u8))
        vote, m = None, None
        if view == "BSE":
            print(f"  measuring material percentages of {name} with GET4 (about a minute)...", flush=True)
            m = material_percentages(path)
            vote = range_vote(m, ranges)
            g["vote"], g["m"] = vote, m
        if forced:
            l1, l2 = two_step_scores(bundle["two_step"], view, x)
            g["l1"], g["l2"] = g["l1"] + l1, g["l2"] + l2
            ans, how = forced_answer(l1, l2, vote)
            print(f"{name} ({view}): {ans}  - forced answer ({how})")
            continue
        (fp, means), tx = bundle["models"][view]
        p = combine(log_proba(fp, means, x[None], batches)[0], tile_log_proba(tx, texture_tiles(u8), batches), cal)
        ans, how = decide(p, cal["threshold_image"], vote, batches)
        print(describe(name, view, ans, how, p, batches, cal["threshold_image"], m, ranges))
        g["ps"].append(p)
    for loc, g in groups.items():
        if g["n"] < 2:
            continue
        if g["known"]:
            print(f"  location {loc}: {g['known']}  - known location, certain")
            continue
        if forced:
            ans, how = forced_answer(g["l1"], g["l2"], g["vote"])
            print(f"  location {loc} ({g['n']} views): {ans}  - forced answer ({how})")
            continue
        p = location_proba(np.array(g["ps"]))
        ans, how = decide(p, cal["threshold_location"], g["vote"], batches)
        print("  " + describe(f"location {loc}", f"{len(g['ps'])} views", ans, how, p, batches,
                              cal["threshold_location"], g["m"], ranges))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["evaluate", "train", "predict"])
    p.add_argument("images", nargs="*")
    p.add_argument("--exclude", nargs="*", default=[], metavar="LOCATION",
                   help="train: leave these location ids out, so their images can be predicted as a fair test")
    p.add_argument("--forced", action="store_true",
                   help="evaluate / predict: always answer, with the two-step model (best forced-choice accuracy)")
    args = p.parse_args()
    if args.command == "predict":
        predict(args.images, args.forced)
        return
    rows = [r for r in index(ROOT) if not (args.command == "train" and r["location"] in args.exclude)]
    print(f"{len(rows)} images, {len({r['location'] for r in rows})} locations")
    D = Data(rows, build_features(rows), *build_texture(rows), build_materials(rows))
    if args.command == "train":
        train(D)
    else:
        evaluate_forced(D) if args.forced else evaluate(D)


if __name__ == "__main__":
    main()
