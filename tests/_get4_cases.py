"""One set of GET4 function calls, run against each GET4 entry point (analysis.get4 and its shims in
batch_match/ and sem_pipeline/src/).

The same inputs go through every entry point, so the outputs can be pinned by golden files per entry point
and compared across them (batch_match/get4.py and sem_pipeline/src/get4.py were separate copies before they
became thin shims over analysis.get4).
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np


def get4_args(out: Path, **overrides) -> SimpleNamespace:
    """The argparse namespace GET4's analyse_image expects, with the CLI defaults plus --fast."""
    args = {
        "px_size": None,
        "bin": 2,
        "page": 0,
        "crop_bottom": None,
        "tilt_deg": None,
        "no_flatten": False,
        "no_destripe": False,
        "max_lag": None,
        "detector": "BSE",
        "fast": True,
        "out": str(out),
        "target_px": None,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


def segment(g4):
    """The 3-class segmentation function of a GET4 copy (batch_match calls it segment_bse)."""
    return getattr(g4, "segment_intensity_classes", None) or g4.segment_bse


def preprocessing_outputs(g4, img: np.ndarray, striped: np.ndarray) -> dict:
    """Imaging quality, stripe index, shading flattening, destriping, segmentation and its sensitivity."""
    out = {}
    q = g4.image_quality(img)
    out["image_quality"] = q
    out["noise_sigma"] = g4.noise_sigma(img)
    out["stripe_index"] = g4.stripe_index(img)
    out["stripe_index_striped"] = g4.stripe_index(striped)
    out["stripe_index_small"] = g4.stripe_index(img[:100, :100])
    out["separability"] = g4.separability(img[::4, ::4], np.array([0.3, 0.65]))

    flat, amp = g4.flatten_shading(img)
    out["flatten_shading"] = {"image": flat, "amplitude": amp}
    out["flatten_shading_degree1"] = dict(zip(("image", "amplitude"), g4.flatten_shading(img, degree=1), strict=True))

    same, applied = g4.destripe(img, q)
    out["destripe_clean"] = {"unchanged": bool(same is img), "applied": applied}
    qs = g4.image_quality(striped)
    out["image_quality_striped"] = qs
    destriped, applied = g4.destripe(striped, qs)
    out["destripe_striped"] = {"image": destriped, "applied": applied, "after": g4.stripe_index(destriped)}

    labels, thresholds, sm = segment(g4)(flat)
    out["segment"] = {"labels": labels, "thresholds": thresholds, "smoothed": sm}
    out["segment_smooth2"] = dict(zip(("labels", "thresholds", "smoothed"), segment(g4)(flat, 2.0), strict=True))
    lo, hi, variants = g4.segmentation_sensitivity(sm, thresholds)
    out["segmentation_sensitivity"] = {"lo": lo, "hi": hi, "variants": variants}
    out["local_segmentation_fractions"] = g4.local_segmentation_fractions(sm, thresholds, labels)
    out["local_segmentation_fractions_tile64"] = g4.local_segmentation_fractions(sm, thresholds, labels, tile=64)
    return out


def phase_outputs(g4, img: np.ndarray) -> dict:
    """analyse_phase on every class of the segmented image (whole-image FFT and tiled), plus its parts."""
    flat, _ = g4.flatten_shading(img)
    labels, _, _ = segment(g4)(flat)
    h, w = labels.shape
    max_lag = min(h, w) // 2
    sizes = np.unique(np.geomspace(4, min(h, w) // 2, 16).astype(int))
    out = {name: g4.analyse_phase(labels == k, max_lag, None, sizes, 50.0) for k, name in g4.PHASES.items()}
    out["graphite_tiled"] = g4.analyse_phase(labels == 1, 48, 128, sizes, 1.0)
    out["empty_phase"] = g4.analyse_phase(np.zeros((h, w), bool), max_lag, None, sizes, 1.0)
    cov, phi = g4.normalised_covariance(labels == 0, 32)
    out["normalised_covariance"] = {"cov": cov, "phi": phi}
    out["integral_range"] = g4.integral_range(cov, 32)
    out["integral_range_capped"] = g4.integral_range(cov, 32, corr_len=2.0)
    out["correlation_length"] = [g4.correlation_length(cov, 32, "x"), g4.correlation_length(cov, 32, "y")]
    out["predicted_se"] = g4.predicted_se(cov, 32, phi, 100, 80)
    out["tile_scaling"] = g4.tile_scaling(labels == 0, [8, 16, 32, 64, 200])
    out["info_bits"] = [g4.info_bits(0.01), g4.info_bits(0.0)]
    return out


RANDOM_EFFECTS_CASES = {
    "one_image": ([0.3], [1e-4], [0.0], None),
    "one_image_prior": ([0.3], [1e-4], [0.0], 2e-4),
    "two_images_prior": ([0.30, 0.31], [1e-4, 2e-4], [0.0, 1e-5], 5e-4),
    "two_images_no_prior": ([0.30, 0.36], [1e-4, 2e-4], [0.0, 1e-5], None),
    "four_images": ([0.28, 0.31, 0.35, 0.30], [1e-4, 2e-4, 1.5e-4, 1e-4], [0.0, 1e-5, 0.0, 3e-5], None),
    "homogeneous": ([0.30, 0.30, 0.30], [1e-4, 1e-4, 1e-4], [0.0, 0.0, 0.0], None),
}


def pooling_outputs(g4) -> dict:
    """random_effects / next_measurement on fixed inputs, plus the small helpers."""
    out = {"random_effects": {}, "next_measurement": {}}
    for name, (phis, va, vi, prior) in RANDOM_EFFECTS_CASES.items():
        out["random_effects"][name] = g4.random_effects(phis, va, vi, prior)
        out["next_measurement"][name] = g4.next_measurement(va, vi, out["random_effects"][name]["tau2"])
    out["parse_tolerances"] = [g4.parse_tolerances("pore=0.02, bright phase=0.01"), g4.parse_tolerances(None)]
    out["how_sure"] = [g4.how_sure(p) for p in ([0.99, 0.995], [0.6, 0.97], [0.01, 0.4], [0.2, 0.8])]
    out["detector_of"] = [
        g4._detector_of(p)
        for p in ("img_0grcilhi_BSE.tif", "img_x_Inlens (2).tif", "img_y_ETD.tif", "scan-se-01.png", "plain.tif")
    ]
    return out


def file_outputs(g4, tiff: Path, plain: Path) -> dict:
    """read_meta / load_image on TIFF files: resampling to a target pixel size, plain binning, crop and tilt."""
    out = {}
    meta = g4.read_meta(tiff)
    out["read_meta"] = meta
    out["read_meta_plain"] = g4.read_meta(plain)
    px = meta["pixel_size_nm"]
    cases = {
        "target_50nm": {"px_nm": px, "target_nm": 50.0, "bin_factor": 1},
        "target_60nm": {"px_nm": px, "target_nm": 60.0, "bin_factor": 1},
        "upsample_20nm": {"px_nm": px, "target_nm": 20.0, "bin_factor": 1},
        "plain_bin2": {"bin_factor": 2},
        "crop_tilt": {"crop_bottom": 32, "px_nm": px, "target_nm": 50.0, "tilt_deg": 52.0},
    }
    for name, kwargs in cases.items():
        img, info = g4.load_image(tiff, meta, **kwargs)
        out[f"load_image_{name}"] = {"image": img, "info": info}
    img, info = g4.load_image(plain, g4.read_meta(plain), bin_factor=3)
    out["load_image_plain_bin3"] = {"image": img, "info": info}
    return out


def material_outputs(g4, tiff: Path) -> dict:
    """The GET4 calls of batch_classifier.material_percentages, step by step, at 25 nm/px."""
    meta = g4.read_meta(tiff)
    px = meta["pixel_size_nm"]
    img, _ = g4.load_image(tiff, meta, px_nm=px, target_nm=25.0 if px else None, bin_factor=1)
    quality = g4.image_quality(img)
    img, _ = g4.flatten_shading(img)
    img, _ = g4.destripe(img, quality)
    labels, _, _ = segment(g4)(img)
    h, w = labels.shape
    tile = None if h * w <= g4.FULL_FFT_MAX_PX else g4.FFT_TILE
    max_lag = min(h, w) // 2 if tile is None else g4.FFT_TILE // 2
    sizes = np.unique(np.geomspace(4, min(h, w) // 2, 16).astype(int))
    return {name: g4.analyse_phase(labels == k, max_lag, tile, sizes, 1.0) for k, name in g4.PHASES.items()}


def analyse_image_results(g4, paths: list[Path], out: Path, args_factory) -> list[dict]:
    """analyse_image on each path at the batch's common target pixel size (as the CLI chooses it)."""
    args = args_factory(out)
    metas = [g4.read_meta(p) for p in paths]
    target, _ = g4.resolve_target(metas, args, None)
    return [g4.analyse_image(p, m, target, args) for p, m in zip(paths, metas, strict=True)]
