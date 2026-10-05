"""The detailed KPI report of one batch: every field measured, summarised across locations and written as
report.json with a segmentation overlay per field (see the analysis.kpis package docstring)."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from .catalogue import CROSS_DETECTOR_KPIS, HEADLINE, KPI_GROUPS, MICRON, SIGNED_KPIS
from .constants import MAX_BRIGHT_SHARE, PHASE_COLORS, PROFILE_BANDS, RIM_CLEAN, SEPARABILITY_LIMIT, TARGET_NM
from .cross_detector import cross_detector
from .measurements import measure_location
from .segmentation import segment
from .statistics import findings, histogram, summarise
from .views import bin_image, inventory, read_grey, view_confidence, view_score

logger = logging.getLogger(__name__)


def output_dir() -> Path:
    """analysis.kpis.OUT, read at call time so that reassigning it (scripts, tests) redirects the reports."""
    from .. import kpis

    return kpis.OUT


def save_overlay(img: np.ndarray, labels: np.ndarray, path: Path, width: int = 1400) -> None:
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


def analyse_batch(batch: str, rebuild_fields: bool = False) -> dict:
    """Measure every field of a batch and write its report.json and overlays (see the analysis.kpis package docstring)."""
    out_dir = output_dir() / f"batch_{batch}"
    fields = inventory(batch, rebuild_fields)
    locs = {fid: f["views"] for fid, f in fields.items()}
    locations, per_kpi, pore_ecd, bright_ecd, profiles = [], {}, [], [], {"pore": [], "bright": []}
    for i, (loc, views) in enumerate(sorted(locs.items()), 1):
        logger.info("[batch %s %d/%d] %s", batch, i, len(locs), loc)
        scored = []
        for v in views:
            img, px = read_grey(v["path"])
            rim, share = view_score(img, px)
            scored.append(
                {"view": v, "img": img, "px": px, "rim": rim, "share": share, "confidence": view_confidence(rim, share)}
            )
        # The BSE view carries the composition contrast; without one, show the InLens view but exclude it.
        rank = {"BSE": 0, "InLens": 1, "ETD": 2}
        scored.sort(key=lambda s: rank.get(s["view"]["detector"], 3))
        best = scored[0]
        view, img, px = best["view"], best["img"], best["px"]
        if view["detector"] != "BSE":
            confidence = "excluded"
        elif best["confidence"] == "clean":
            confidence = "clean"
        else:
            confidence = "usable"
        b = max(1, round(TARGET_NM / px)) if px else 2
        px_um = (px * b if px else TARGET_NM) / 1000
        work = bin_image(img, b)
        labels, quality = segment(work)
        kpis, extra = measure_location(labels, px_um)
        flags = []
        # Compare with the field's secondary-electron views, binned to the same analysis pixel size.
        others = {
            s["view"]["detector"]: bin_image(s["img"], max(1, round(TARGET_NM / s["px"])) if s["px"] else 2)
            for s in scored
            if s["view"]["detector"] in ("ETD", "InLens")
        }
        alignment = {}
        if view["detector"] == "BSE" and others:
            cross, alignment = cross_detector(work, labels, others)
            kpis.update(cross)
        kpis.update({k: None for k in CROSS_DETECTOR_KPIS if k not in kpis})
        missing = [d for d in ("ETD", "InLens") if d not in others]
        if view["detector"] == "BSE" and missing:
            flags.append(f"no {' or '.join(missing)} view, so the cross-detector comparison with it is not measured")
        included = confidence != "excluded"
        if confidence == "usable":
            flags.append(
                f"bright class has rough rims or a high share (perimeter/area {best['rim']:.2f} µm⁻¹, "
                f"{best['share'] * 100:.0f}% bright); binder or particle edges may add to it"
            )
        elif confidence == "excluded":
            flags.append(
                f"no BSE view in this field (shown: the {view['detector']} view); left out of batch statistics"
            )
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
        locations.append(
            {
                # Named after the field's assigned location so every view of it shares one name.
                "location_id": fields[loc]["field"]["location"],
                "field_id": loc,
                "location_recovered": fields[loc]["field"]["location_recovered"],
                "filename_codes": fields[loc]["field"]["filename_codes"],
                "match_confidence": fields[loc]["field"]["confidence"],
                "included": included,
                "confidence": confidence,
                "analysed_image": view["filename"],
                "analysed_detector": view["detector"],
                "analysed_filename_detector": view["filename_detector"],
                "pixel_size_um": px_um,
                "field_um": [round(labels.shape[1] * px_um, 1), round(labels.shape[0] * px_um, 1)],
                "views": [
                    {
                        "filename": s["view"]["filename"],
                        "detector": s["view"]["detector"],
                        "detector_confidence": s["view"]["detector_confidence"],
                        "filename_detector": s["view"]["filename_detector"],
                        "rim_score": s["rim"],
                        "bright_share": s["share"],
                        "analysed": s is best,
                    }
                    for s in scored
                ],
                "quality": quality,
                "flags": flags,
                "kpis": kpis,
                "cross_detector_shift_px": alignment,
                "profile_pore": extra["profile_pore"],
                "profile_bright": extra["profile_bright"],
                "overlay": overlay,
            }
        )
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
    groups = []
    for gid, title, description, items in KPI_GROUPS:
        kpis = []
        for kid, name, unit, scale, definition in items:
            pairs = per_kpi.get(kid, [])
            kpis.append(
                {
                    "id": kid,
                    "name": name,
                    "unit": unit,
                    "display_scale": scale,
                    "definition": definition,
                    **summarise([v for _, v in pairs], kid in SIGNED_KPIS),
                    "per_location": [{"location_id": l, "value": v} for l, v in pairs],
                }
            )
        groups.append({"id": gid, "title": title, "description": description, "kpis": kpis})

    def profile_summary(rows: list[list[float]]) -> dict[str, list[float]]:
        a = np.array(rows) if rows else np.zeros((0, PROFILE_BANDS))
        return {
            "mean": a.mean(0).tolist() if len(a) else [],
            "min": a.min(0).tolist() if len(a) else [],
            "max": a.max(0).tolist() if len(a) else [],
        }

    pore_all = np.concatenate(pore_ecd) if pore_ecd else np.array([])
    bright_all = np.concatenate(bright_ecd) if bright_ecd else np.array([])
    included = [l for l in locations if l["included"]]
    report = {
        "report_type": "batch-kpi-report",
        "report_version": 1,
        "batch_id": str(batch),
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
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
            "cross_detector": "The ETD and InLens views of each field are segmented the same way, aligned to "
            "the BSE view by phase correlation of gradient images, and compared pixel by pixel.",
            "statistics": "Each matched location is one replicate. Mean, sample SD, CV and a t-based 95% CI of "
            "the batch mean across locations.",
            "consistency_bands": "CV < 10% consistent · 10–25% moderate · > 25% variable. Signed KPIs "
            "report whether the 95% CI excludes zero instead.",
            "phase_colors": {"pore": "#2a78d6", "graphite": "#1baf7a", "bright": "#eb6834"},
        },
        "inventory": {
            "locations": len(locations),
            "locations_analysed": len(included),
            "confidence": {c: sum(l["confidence"] == c for l in locations) for c in ("clean", "usable", "excluded")},
            "images": sum(len(v) for v in locs.values()),
            "filename_detectors": {
                d: sum(v["filename_detector"] == d for vs in locs.values() for v in vs)
                for d in ("BSE", "ETD", "INLENS", "SE")
            },
            "identified_detectors": {
                d: sum(v["detector"] == d for vs in locs.values() for v in vs) for d in ("BSE", "InLens", "ETD")
            },
            "field_area_um2": float(sum(l["field_um"][0] * l["field_um"][1] for l in included)),
        },
        "headline": HEADLINE,
        "kpi_groups": groups,
        "distributions": {
            "bright_ecd": {"label": "Bright particle size (ECD)", "unit": MICRON, **histogram(bright_all, 0.25, 30)},
            "pore_ecd": {"label": "Pore size (ECD)", "unit": MICRON, **histogram(pore_all, 0.1, 30)},
        },
        "profiles": {
            "bands": PROFILE_BANDS,
            "axis": "image top to bottom",
            "porosity": profile_summary(profiles["pore"]),
            "bright_fraction": profile_summary(profiles["bright"]),
        },
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
    report["findings"] = findings(groups, locations)
    (out_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
