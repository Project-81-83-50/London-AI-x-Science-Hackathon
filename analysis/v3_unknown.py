"""Segment the unknown batch with the v3 SEM pipeline (sem_pipeline/) and measure it like the references.

v3's delivered U-Net weights are a release asset that is not in this repository, so the unknown images are
segmented with v3's LightGBM teacher, which sem_pipeline/run_cpu_pipeline.py trains on CPU from the pipeline's
committed labels (models/teacher_cpu.txt, BSE + InLens features). Each step is v3's own code, applied to images
outside its manifest: prepare() below (src.predict.prepare, repeated here because src.predict imports PyTorch for
the U-Net), src.features.detector_features (27 features per detector), the model, src.physics.constrain_siox
(BSE only) and src.teacher.clean; SiOx particles follow src.instances.

A location with only one usable image (for example a single upload) is segmented by a one-detector model
(BSE, InLens or ETD/SE) distilled from the teacher: trained on the teacher's confident pixels of the reference
locations, using that detector's features only. Each one-detector model is first fitted on v3's student
training split and scored against the teacher on the 6 held-out locations (pixel agreement, phase-fraction
differences), then refitted on all 31. Those scores travel with every result it produces.

So that the comparison is like for like, the 31 reference locations are measured from the teacher's own label
maps (v3 data/processed/<sid>/teacher_cpu_labels.npy) with the same measure() below, not from the U-Net numbers
shown in the reference reports. Detectors of the unknown views are identified from the pixels by analysis.fields
(data/processed/fields/batch_unknown.json must exist; analysis.classify --rebuild creates it).

    python -m analysis.v3_unknown     # writes data/processed/v3_unknown/measurements.json and overlays/
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import configure_cli_logging, paths

logger = logging.getLogger(__name__)

ROOT = paths.REPO_ROOT
SEM_PIPELINE_DIR = paths.SEM_PIPELINE_DIR
TEACHER = SEM_PIPELINE_DIR / "models" / "teacher_cpu.txt"
SPLIT = SEM_PIPELINE_DIR / "models" / "student_split.json"
RAW_UNKNOWN = paths.RAW_UNKNOWN_DIR
FIELDS = paths.FIELDS_DIR / "batch_unknown.json"
OUT = paths.V3_UNKNOWN_DIR
MODEL_DIR = OUT / "models"
# analysis.fields detector name -> v3 channel name. ETD and SE are v3's "SE2" channel.
V3_CHANNEL = {"BSE": "BSE", "InLens": "Inlens", "ETD": "SE2", "SE": "SE2"}
SINGLE_PRIORITY = ["BSE", "InLens", "ETD", "SE"]  # which view a single-view location is segmented from
MODEL_LABEL = {
    "pair": "v3 teacher (BSE + InLens)",
    "BSE": "one-detector model (BSE)",
    "Inlens": "one-detector model (InLens)",
    "SE2": "one-detector model (ETD / SE)",
}
CONFIDENT = int(0.9 * 255)  # teacher_cpu_maxp.npy stores the max class probability as uint8
PER_CLASS = 6000  # training pixels per class and location


def import_sem_pipeline() -> tuple:
    """Import the pipeline's own modules (its package is called src): (config, features, physics, preprocess,
    teacher). This tuple is passed around as `mods`."""
    if str(SEM_PIPELINE_DIR) not in sys.path:
        sys.path.insert(0, str(SEM_PIPELINE_DIR))
    from src import config, features, physics, preprocess, teacher

    return config, features, physics, preprocess, teacher


def prepare(paths: dict[str, Path], C, preprocess) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """v3 src/predict.prepare for any set of channels: half resolution, excluded border (and the Cu foil, found
    on BSE), 0.5-99.5% normalisation. paths: {v3 channel: path}."""
    raw = {d: preprocess.read_half(p) for d, p in paths.items()}
    h, w = next(iter(raw.values())).shape
    exclude = np.zeros((h, w), bool)
    b = C.BORDER_RAW_PX // C.DS
    exclude[:b], exclude[-b:], exclude[:, :b], exclude[:, -b:] = True, True, True, True
    if "BSE" in raw:
        exclude |= preprocess.cu_foil(raw["BSE"])
    chans = {}
    for d, a in raw.items():
        lo, hi = np.percentile(a[~exclude], [0.5, 99.5])
        chans[d] = ndi.median_filter(np.clip((a - lo) / (hi - lo), 0, 1), size=3).astype(np.float32)
    return chans, exclude


def channel_features(a: np.ndarray, det: str, F) -> np.ndarray:
    """v3's per-pixel features of one normalised channel (H x W x 27, float16)."""
    f = F.detector_features(a)
    f[2] = a - ndi.gaussian_filter(a, F.CONTEXT_SIGMA[det])
    return np.stack(f, -1).astype(np.float16)  # v3 stores features as float16


def predict_labels(booster, X: np.ndarray, bse: np.ndarray | None, exclude: np.ndarray, mods: tuple) -> np.ndarray:
    """Model probabilities -> v3's SiOx constraint (needs BSE) -> v3's clean-up."""
    _, _, physics, _, teacher = mods
    h, w, nf = X.shape
    flat = X.reshape(-1, nf)
    proba = np.empty((h * w, 4), np.float32)
    for i in range(0, h * w, 600_000):
        proba[i : i + 600_000] = booster.predict(np.asarray(flat[i : i + 600_000], dtype=np.float32))
    proba = proba.reshape(h, w, 4)
    if bse is not None:
        proba = physics.constrain_siox(proba, bse, exclude)
    return teacher.clean(proba.argmax(-1), exclude)


# ---------------------------------------------------------------- one-detector models


def _training_set(sids: list[str], det: str, mods: tuple, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Up to PER_CLASS confident teacher pixels per class and location: (features of channel `det`, labels)."""
    C = mods[0]
    X, y = [], []
    for sid in sids:
        lab = np.load(C.proc_dir(sid) / "teacher_cpu_labels.npy")
        maxp = np.load(C.proc_dir(sid) / "teacher_cpu_maxp.npy")
        feats = np.load(C.proc_dir(sid) / f"feat_{det}.npy", mmap_mode="r")
        ok = (lab != C.EXCLUDED) & (maxp >= CONFIDENT)
        flat_lab, flat_ok = lab.ravel(), ok.ravel()
        for k in range(4):
            cand = np.flatnonzero(flat_ok & (flat_lab == k))
            if len(cand):
                pick = rng.choice(cand, min(PER_CLASS, len(cand)), replace=False)
                X.append(np.asarray(feats.reshape(-1, feats.shape[-1])[pick], np.float32))
                y.append(np.full(len(pick), k))
    return np.concatenate(X), np.concatenate(y)


def _fit(X: np.ndarray, y: np.ndarray, teacher):
    """Train a LightGBM model with the teacher's own settings (uniform sample weights)."""
    return teacher.fit(X, y, np.ones(len(y), np.float32))


def train_single_detector_models(mods: tuple) -> dict:
    """Distil one model per detector from the teacher; score each on v3's held-out locations first."""
    C, _, _, _, teacher = mods
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    sids = [s for _, s in C.sample_ids()]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    scores = {}
    for det in ("BSE", "Inlens", "SE2"):
        rng = np.random.default_rng(0)
        model = _fit(*_training_set(split["train"], det, mods, rng), teacher)
        agree, diffs = [], {c: [] for c in C.CLASSES}
        for sid in split["held_out"]:
            ref = np.load(C.proc_dir(sid) / "teacher_cpu_labels.npy")
            ch = C.load_channels(sid, [det] + (["BSE"] if det != "BSE" else []))
            X = np.load(C.proc_dir(sid) / f"feat_{det}.npy")
            excl = C.load_exclude(sid)
            lab = predict_labels(model, X, ch["BSE"] if det == "BSE" else None, excl, mods)
            valid = (ref != C.EXCLUDED) & (lab != C.EXCLUDED)
            agree.append(float((lab[valid] == ref[valid]).mean()))
            for k, c in enumerate(C.CLASSES):
                diffs[c].append(100 * float((lab[valid] == k).mean() - (ref[valid] == k).mean()))
        scores[det] = {
            "held_out_locations": split["held_out"],
            "pixel_agreement_with_teacher": round(float(np.mean(agree)), 3),
            "fraction_difference_pp": {
                c: {"mean": round(float(np.mean(v)), 2), "max_abs": round(float(np.max(np.abs(v))), 2)}
                for c, v in diffs.items()
            },
        }
        logger.info(
            "one-detector model %s: held-out pixel agreement with the teacher %.3f; %s",
            det,
            scores[det]["pixel_agreement_with_teacher"],
            ", ".join(f"{c} {d['mean']:+.1f} pp" for c, d in scores[det]["fraction_difference_pp"].items()),
        )
        rng = np.random.default_rng(0)
        _fit(*_training_set(sids, det, mods, rng), teacher).save_model(str(MODEL_DIR / f"{det}.txt"))
    (MODEL_DIR / "validation.json").write_text(json.dumps(scores, indent=1), encoding="utf-8")
    return scores


def single_detector_models(mods: tuple) -> tuple[dict, dict]:
    """The one-detector boosters by v3 channel (trained on first use) and their validation scores."""
    import lightgbm as lgb

    if not (MODEL_DIR / "validation.json").is_file():
        logger.info("training the one-detector models (once, a few minutes) ...")
        train_single_detector_models(mods)
    scores = json.loads((MODEL_DIR / "validation.json").read_text(encoding="utf-8"))
    return {det: lgb.Booster(model_file=str(MODEL_DIR / f"{det}.txt")) for det in scores}, scores


# ---------------------------------------------------------------- measurement


def siox_particles(lab: np.ndarray, C) -> list[dict]:
    """SiOx instances exactly as v3 src/instances.py: fill holes, EDT, h-maxima (h = 3 px), watershed."""
    from skimage.measure import regionprops
    from skimage.morphology import h_maxima
    from skimage.segmentation import watershed

    excl = lab == C.EXCLUDED
    mask = ndi.binary_fill_holes(lab == C.SIOX)
    dist = ndi.distance_transform_edt(mask)
    markers, _ = ndi.label(h_maxima(dist, 3))
    inst = watershed(-dist, markers, mask=mask)
    near_excl = ndi.binary_dilation(excl, iterations=2)
    rows = []
    for p in regionprops(inst):
        area = p.area * C.PX_UM2
        if area < 0.1:
            continue
        rows.append(
            {
                "area_um2": area,
                "eq_diam_um": 2 * np.sqrt(area / np.pi),
                "aspect_ratio": p.major_axis_length / max(p.minor_axis_length, 1e-6),
                "centroid_y_um": p.centroid[0] * C.NM_PER_PX / 1000,
                "centroid_x_um": p.centroid[1] * C.NM_PER_PX / 1000,
                "touches_excluded": bool(near_excl[p.coords[:, 0], p.coords[:, 1]].any()),
            }
        )
    return rows


def measure(lab: np.ndarray, bse: np.ndarray | None, C) -> tuple[dict, list[dict]]:
    """The v3 report's segmentation metrics for one label map (0 pore, 1 graphite, 2 SiOx, 3 CBD, 255 excluded).
    bse may be None (no BSE view): the deep / open pore split, which is defined on BSE, is then not measured."""
    from scipy.spatial import cKDTree
    from skimage.filters import threshold_multiotsu

    valid = lab != C.EXCLUDED
    n = int(valid.sum())
    area = n * C.PX_UM2
    m = {f"{c}_pct": 100 * float((lab[valid] == k).sum()) / n for k, c in enumerate(C.CLASSES)}
    m["carbon_pct"] = m["graphite_pct"] + m["CBD_pct"]
    if bse is not None:
        # v3 src/metrics.py: deep pores are pore pixels in the dark BSE multi-Otsu class, open pores the rest.
        deep = (lab == C.PORE) & (bse < threshold_multiotsu(bse[valid], classes=3)[0])
        m["pore_deep_pct"] = 100 * float(deep.sum()) / n
        m["pore_open_pct"] = 100 * float(((lab == C.PORE) & ~deep).sum()) / n
    ps = siox_particles(lab, C)
    d = np.array([p["eq_diam_um"] for p in ps])
    a = np.array([p["area_um2"] for p in ps])
    m["siox_per_1000um2"] = 1000 * len(d) / area
    if len(d):
        m["siox_median_ecd_um"] = float(np.median(d))
        m["siox_p90_ecd_um"] = float(np.percentile(d, 90))
        order = np.argsort(d)
        m["siox_area_d50_um"] = float(d[order][np.searchsorted(np.cumsum(a[order]) / a.sum(), 0.5)])
        inside = [p["aspect_ratio"] for p in ps if not p["touches_excluded"]]
        m["siox_aspect_median"] = float(np.median(inside)) if inside else None
        xy = np.array([[p["centroid_x_um"], p["centroid_y_um"]] for p in ps])
        if len(xy) > 3:
            nn = cKDTree(xy).query(xy, k=2)[0][:, 1].mean()
            m["siox_clark_evans"] = float(nn / (0.5 / np.sqrt(len(xy) / area)))
        m["siox_top_share"] = float(100 * a[xy[:, 1] < lab.shape[0] * C.NM_PER_PX / 1000 / 2].sum() / a.sum())
    m["excluded_pct"] = 100 * float((~valid).mean())
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}, ps


def unknown_locations() -> list[tuple[str, dict[str, Path], list[str]]]:
    """(location_id, {fields detector: path}, all views) per unknown field; detectors read from the pixels."""
    fields = json.loads(FIELDS.read_text(encoding="utf-8"))["fields"]
    out = []
    for f in fields:
        views = f["views"]
        code = next((v["filename_code"] for v in views if v.get("filename_code")), f["field_id"])
        found = {}
        for v in views:
            found.setdefault(v["detector"], RAW_UNKNOWN / v["filename"])
        out.append((code, found, [v["filename"] for v in views]))
    return out


def segment_location(found: dict[str, Path], teacher_model, singles: dict, mods: tuple) -> tuple:
    """BSE + InLens -> the teacher; otherwise the best single view -> its one-detector model.

    Returns (label map, BSE channel or None, grey channel for the overlay, model key, filenames used).
    """
    C, F = mods[0], mods[1]
    if "BSE" in found and "InLens" in found:
        chans, exclude = prepare({"BSE": found["BSE"], "Inlens": found["InLens"]}, C, mods[3])
        X = np.concatenate([channel_features(chans[d], d, F) for d in ("BSE", "Inlens")], -1)
        lab = predict_labels(teacher_model, X, chans["BSE"], exclude, mods)
        return lab, chans["BSE"], chans["BSE"], "pair", [found["BSE"].name, found["InLens"].name]
    det = next(d for d in SINGLE_PRIORITY if d in found)
    ch = V3_CHANNEL[det]
    chans, exclude = prepare({ch: found[det]}, C, mods[3])
    X = channel_features(chans[ch], ch, F)
    bse = chans["BSE"] if ch == "BSE" else None
    lab = predict_labels(singles[ch], X, bse, exclude, mods)
    return lab, bse, chans[ch], ch, [found[det].name]


def main() -> None:
    argparse.ArgumentParser(description="Segment and measure the unknown batch with the v3 SEM pipeline.").parse_args()
    configure_cli_logging()
    if not TEACHER.is_file():
        sys.exit(f"{TEACHER} not found: run python run_cpu_pipeline.py in sem_pipeline first (~1 h, CPU)")
    import lightgbm as lgb

    mods = import_sem_pipeline()
    C = mods[0]
    teacher_model = lgb.Booster(model_file=str(TEACHER))
    singles, single_scores = single_detector_models(mods)
    (OUT / "overlays").mkdir(parents=True, exist_ok=True)

    reference = []
    for batch, sid in C.sample_ids():
        lab = np.load(C.proc_dir(sid) / "teacher_cpu_labels.npy")
        metrics, particles = measure(lab, C.load_channels(sid, ["BSE"])["BSE"], C)
        height = json.loads((C.proc_dir(sid) / "meta.json").read_text(encoding="utf-8"))["shape"][0] * C.DS
        reference.append(
            {
                "sample_id": sid,
                "batch": batch,
                "session": f"h{height}",
                "metrics": metrics,
                "siox_diameters_um": [round(p["eq_diam_um"], 3) for p in particles],
                "siox_areas_um2": [round(p["area_um2"], 4) for p in particles],
            }
        )
    logger.info("measured %d reference locations from the teacher's label maps", len(reference))

    unknown, skipped = [], []
    for code, found, views in unknown_locations():
        if not any(d in found for d in SINGLE_PRIORITY):
            skipped.append({"location_id": code, "views": views, "reason": "no view with a recognised detector"})
            continue
        lab, bse, grey, model, used = segment_location(found, teacher_model, singles, mods)
        metrics, particles = measure(lab, bse, C)
        Image.fromarray(C.overlay_rgb(grey, lab, alpha=0.45)).save(OUT / "overlays" / f"{code}.jpg", quality=88)
        with Image.open(RAW_UNKNOWN / used[0]) as im:
            height = im.size[1]
        unknown.append(
            {
                "sample_id": code,
                "batch": "unknown",
                "session": f"h{height}",
                "views": views,
                "segmented_from": used,
                "model": model,
                "model_label": MODEL_LABEL[model],
                "model_validation": single_scores.get(model),
                "metrics": metrics,
                "siox_diameters_um": [round(p["eq_diam_um"], 3) for p in particles],
                "siox_areas_um2": [round(p["area_um2"], 4) for p in particles],
            }
        )
        logger.info(
            "%s (%s): pore %.1f%%, carbon %.1f%%, SiOx %.1f%%",
            code,
            MODEL_LABEL[model],
            metrics["pore_pct"],
            metrics["carbon_pct"],
            metrics["SiOx_pct"],
        )

    out = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": "sem_pipeline v3 LightGBM teacher (CPU rebuild, models/teacher_cpu.txt); one-detector "
        "models distilled from it for locations with a single usable image",
        "single_detector_validation": single_scores,
        "reference": reference,
        "unknown": unknown,
        "skipped": skipped,
    }
    (OUT / "measurements.json").write_text(json.dumps(out), encoding="utf-8")
    logger.info("wrote %s (%d unknown locations, %d skipped)", OUT / "measurements.json", len(unknown), len(skipped))


if __name__ == "__main__":
    main()
