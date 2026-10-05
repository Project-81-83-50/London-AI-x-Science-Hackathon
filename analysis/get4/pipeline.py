"""End-to-end analysis: one image (`analyse_image`) and one detector-specific image set (`analyse_paths`),
which writes the per-image JSON files, batch_uncertainty.json, analysis_report.json and the batch figure."""

import argparse
import json
from pathlib import Path

import numpy as np

from .constants import FFT_TILE, FULL_FFT_MAX_PX, INTENSITY_CLASSES, PHASES, Z95
from .imaging import quality_flags, resolve_target
from .inputs import _location_of
from .loading import load_image, read_meta
from .plotting import plot_batch_report, plot_image_report
from .pooling import analyse_batch
from .preprocessing import destripe, flatten_shading, image_quality, stripe_index
from .reporting import print_batch_summary, print_image_summary, print_quality_report
from .segmentation import local_segmentation_fractions, segment_intensity_classes, segmentation_sensitivity
from .spatial import analyse_phase


def analyse_image(
    path: str | Path, meta: dict, target_nm: float | None, args: argparse.Namespace, class_names: dict | None = None
) -> dict:
    """Load, check, preprocess and segment one image, then analyse every class (prints a summary)."""
    class_names = class_names or (PHASES if args.detector.upper() == "BSE" else INTENSITY_CLASSES)
    px = args.px_size or meta["pixel_size_nm"]
    plain_bin = args.bin or 2
    img, info = load_image(path, meta, args.page, args.crop_bottom, px, target_nm, plain_bin, args.tilt_deg)
    unit, unit_len = ("nm", target_nm) if target_nm else ("px", float(plain_bin))

    quality = image_quality(img)
    preprocessing = []
    if not args.no_flatten:
        img, amp = flatten_shading(img)
        quality["shading"] = amp / quality["contrast"]
        preprocessing.append(f"shading flattened (was {100 * quality['shading']:.0f}% of contrast)")
    applied = []
    if not args.no_destripe:
        img, applied = destripe(img, quality)
        preprocessing += [f"removed {a}" for a in applied]
    after = stripe_index(img) if applied else {}
    quality["stripes_curtaining_after"] = after.get("curtaining", quality["stripes_curtaining"])
    quality["stripes_scan_lines_after"] = after.get("scan_lines", quality["stripes_scan_lines"])

    labels, thresholds, sm = segment_intensity_classes(img)
    seg_lo, seg_hi, seg_variants = segmentation_sensitivity(sm, thresholds)
    phi_local, n_refit, n_tiles = local_segmentation_fractions(sm, thresholds, labels)

    h, w = labels.shape
    tile = None if h * w <= FULL_FFT_MAX_PX else FFT_TILE
    max_lag = min(h, w) // 2 if tile is None else FFT_TILE // 2
    if args.max_lag:
        max_lag = min(max_lag, args.max_lag)
    sizes = np.unique(np.geomspace(4, min(h, w) // 2, 16).astype(int))

    result = {
        "image": Path(path).name,
        "detector": args.detector.upper(),
        **meta,
        **info,
        "pixel_size_nm_used": px,
        "target_pixel_nm": target_nm,
        "unit": unit,
        "thresholds": thresholds.tolist(),
        "quality": quality,
        "preprocessing": preprocessing,
        "local_threshold_tiles": [n_refit, n_tiles],
        "max_autocorrelation_lag_px": max_lag,
        "phases": {},
    }
    for k, name in class_names.items():
        r = analyse_phase(labels == k, max_lag, tile, sizes, unit_len)
        r["threshold_range"] = [float(seg_lo[k]), float(seg_hi[k])]
        r["phi_local_threshold"] = float(phi_local[k])
        r["shading_shift"] = float(phi_local[k] - r["phi"])
        r["systematic_range"] = [float(min(seg_lo[k], phi_local[k])), float(max(seg_hi[k], phi_local[k]))]
        # the same segmentation variants in every image/lot, so lot comparisons can cancel common-mode bias:
        # 4 threshold nudges (-/-, -/+, +/-, +/+) and local thresholds
        r["variant_shifts"] = [float(v - r["phi"]) for v in list(seg_variants[:, k]) + [phi_local[k]]]
        result["phases"][name] = r

    print_image_summary(result)
    result["class_names"] = class_names
    if not args.fast:
        plot_image_report(labels, result, unit_len, Path(args.out) / f"{Path(path).stem}_uncertainty.png")
    return result


def analyse_paths(
    paths: list[Path],
    args: argparse.Namespace,
    out: Path,
    parser: argparse.ArgumentParser,
    baseline: dict | None = None,
    class_names: dict | None = None,
    locations: dict[str, str] | None = None,
    batch_id: str | None = None,
) -> dict:
    """Run the existing per-image and batch analysis for one detector-specific image set."""
    class_names = class_names or (PHASES if args.detector.upper() == "BSE" else INTENSITY_CLASSES)
    measurement_key = "phases" if args.detector.upper() == "BSE" else "intensity_classes"
    if baseline and measurement_key not in baseline:
        parser.error(f"baseline does not contain {args.detector.upper()} {measurement_key}")
    out.mkdir(parents=True, exist_ok=True)
    args.out = str(out)

    if args.fast and args.bin is None and args.target_px is None and baseline is None:
        args.bin = 2

    metas = [read_meta(path, args.page) for path in paths]
    try:
        target_nm, target_note = resolve_target(metas, args, baseline)
    except ValueError as e:
        parser.error(str(e))
    print(f"scale: {f'{target_nm:.2f} nm/px' if target_nm else 'pixels'} ({target_note})")

    results = [analyse_image(path, meta, target_nm, args, class_names) for path, meta in zip(paths, metas, strict=True)]

    ref_images = (baseline or {}).get("images")
    for i, r in enumerate(results):
        location_id = locations.get(r["image"]) if locations is not None else _location_of(r["image"])
        if location_id is not None:
            r["location_id"] = location_id
        ref = (
            [b["quality"] for b in ref_images]
            if ref_images
            else [o["quality"] for j, o in enumerate(results) if j != i]
        )
        flags = quality_flags(r["quality"], ref if (ref_images or len(ref) >= 2) else [])
        if r["upsampled"]:
            flags.append("image is coarser than the analysis scale (upsampled): fine features may be lost")
        flags += [
            f"{name} resolution-limited (features < 5 px)"
            for name, ph in r["phases"].items()
            if ph["resolution_limited"]
        ]
        r["imaging_flags"] = flags
        image_report = dict(r)
        image_report[measurement_key] = image_report.pop("phases")
        (out / f"{Path(r['image']).stem}_uncertainty.json").write_text(json.dumps(image_report, indent=2))
    reference = (
        "baseline images"
        if ref_images
        else (
            "the rest of this batch" if len(results) >= 3 else "absolute limits only (need >= 3 images or --baseline)"
        )
    )
    print_quality_report(results, reference)

    tau2_prior = None
    if baseline:
        tau2_prior = {
            name: b["tau2"] for name, b in baseline[measurement_key].items() if "estimated" in b["tau2_source"]
        }
    batch = analyse_batch(results, tau2_prior, class_names)
    print_batch_summary(batch)
    fraction_label = "phase fraction" if args.detector.upper() == "BSE" else "intensity-class fraction"
    plot_batch_report(batch, out / "batch_uncertainty.png", fraction_label)
    detector_name = args.detector.upper()
    is_bse = detector_name == "BSE"
    measurement_names = class_names
    kpis = []
    for name, measurement in batch.items():
        lo, hi = measurement["ci95"]
        candidate_name = (
            f"Candidate {name} fraction (provisional)"
            if is_bse
            else f"{name} fraction ({detector_name} intensity class)"
        )
        kpis.append(
            {
                "id": name,
                "name": candidate_name,
                "value": measurement["phi"],
                "unit": "fraction (0-1)",
                "ci_low": lo,
                "ci_high": hi,
                "status": "provisional",
                "locations_measured": measurement["n_images"],
                "between_location_sd": (None if "NOT ESTIMABLE" in measurement["tau2_source"] else measurement["tau"]),
                "measurement_kind": "candidate_material_kpi" if is_bse else "detector_intensity_metric",
                "evidence_note": (
                    "Threshold-defined class; validate the segmentation against labelled images "
                    "before interpreting as a material phase."
                    if is_bse
                    else "Detector intensity class only; not a validated material property."
                ),
            }
        )

    summary = {
        "detector": detector_name,
        "segmentation_interpretation": (
            "provisional BSE intensity classes; verify against ground truth before interpreting as phases"
            if args.detector.upper() == "BSE"
            else "low/mid/high detector-intensity classes only; not validated material phases"
        ),
        "target_pixel_nm": target_nm,
        "scale_note": target_note,
        "images": [
            {
                "image": r["image"],
                "location_id": r.get("location_id"),
                "quality": r["quality"],
                "imaging_flags": r["imaging_flags"],
                "fraction_estimates": {
                    name: {
                        "fraction": phase["phi"],
                        "uncertainty_95": [
                            max(0.0, phase["phi"] - Z95 * phase["se_image"]),
                            min(1.0, phase["phi"] + Z95 * phase["se_image"]),
                        ],
                    }
                    for name, phase in r["phases"].items()
                },
            }
            for r in results
        ],
        measurement_key: batch,
    }
    summary.update(
        {
            "report_type": "battery-image-analysis",
            "report_version": 1,
            "analysis_settings": {
                "mode": "fast" if args.fast else "full",
                "target_pixel_nm": target_nm,
                "scale_note": target_note,
                "per_image_plots_generated": not args.fast,
            },
            "batch_id": batch_id,
            "report_title": f"{batch_id or 'Image set'} / {detector_name} analysis",
            "report_summary": (
                f"Descriptive image-derived measurements from {len(results)} {detector_name} "
                f"images across {len({r.get('location_id', r['image']) for r in results})} locations."
            ),
            "comparison": {
                "performed": False,
                "reference_batch": None,
                "reason": "Each reference batch represents a different battery; no cross-batch baseline is assumed.",
            },
            "decision": {
                "status": "not_assessed",
                "reason": "No approved KPI limits or acceptance criteria were supplied.",
            },
            "kpis": kpis if is_bse else [],
            "image_metrics": [] if is_bse else kpis,
            "quality_findings": [
                {"image": image["image"], "location_id": image.get("location_id"), "flags": image["imaging_flags"]}
                for image in summary["images"]
                if image["imaging_flags"]
            ],
            "measurement_groups": list(measurement_names.values()),
        }
    )
    (out / "batch_uncertainty.json").write_text(json.dumps(summary, indent=2))
    (out / "analysis_report.json").write_text(json.dumps(summary, indent=2))
    return summary
