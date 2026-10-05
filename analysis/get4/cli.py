"""Command line of GET4 (`python -m analysis.get4 --help`): one image set, --project mode over data/raw/, and
--compare of two lots."""

import argparse
import json
import re
from pathlib import Path

from .comparison import compare_lots, parse_tolerances
from .constants import IMAGE_SUFFIXES, INTENSITY_CLASSES, PHASES
from .inputs import DETECTOR_TAGS, _detector_of, _location_of, collect_images
from .pipeline import analyse_paths
from .reporting import print_comparison

# data/raw/ of the repository (analysis/get4/cli.py -> parents[2] is the repository root); read by --project
RAW_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw"


def build_parser() -> argparse.ArgumentParser:
    """The argument parser of `main`."""
    parser = argparse.ArgumentParser(description="Area / regularity / between-image uncertainty of phase fractions.")
    parser.add_argument("inputs", nargs="*", help="images or folders of one detector: different locations, same batch")
    parser.add_argument(
        "--project", action="store_true", help="analyse all recognized detector files, separately by batch and filter"
    )
    parser.add_argument(
        "--batch",
        action="append",
        default=None,
        metavar="FOLDER",
        help="with --project, analyse only this data/raw folder (e.g. batch_1 or unknown); "
        "repeatable; default: every batch_N folder",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="with --project, list location codes, filters, and images without processing",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="use 2x coarser sampling by default and skip per-image plots; full analysis remains available without this flag",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("LOT_A_JSON", "LOT_B_JSON"),
        default=None,
        help="compare two batch_uncertainty.json files (A = baseline / approved lot)",
    )
    parser.add_argument(
        "--tol", default=None, help='absolute tolerances on phi per phase, e.g. "pore=0.02,bright phase=0.01"'
    )
    parser.add_argument(
        "--tol-rel",
        type=float,
        default=0.10,
        help="tolerance as a fraction of lot A's phi, for phases without --tol (default 0.10)",
    )
    parser.add_argument(
        "--bin",
        type=int,
        default=None,
        help="target pixel = coarsest image pixel x bin (default 1); without pixel sizes, plain binning (default 2)",
    )
    parser.add_argument(
        "--target-px", type=float, default=None, help="analyse at this pixel size, nm (overrides baseline)"
    )
    parser.add_argument("--px-size", type=float, default=None, help="override pixel size of the ORIGINAL images, nm")
    parser.add_argument(
        "--tilt-deg",
        type=float,
        default=None,
        help="stage tilt of a FIB cross-section if the microscope did not tilt-correct (e.g. 52)",
    )
    parser.add_argument("--crop-bottom", type=int, default=None, help="override databar rows to crop")
    parser.add_argument("--page", type=int, default=0, help="page of a multi-page TIF")
    parser.add_argument("--max-lag", type=int, default=None, help="max correlation lag in analysed px")
    parser.add_argument("--no-flatten", action="store_true", help="skip shading flattening")
    parser.add_argument("--no-destripe", action="store_true", help="skip curtaining / scan-line removal")
    parser.add_argument(
        "--baseline",
        default=None,
        help="batch JSON from a baseline run: its scale, imaging conditions and tau2 are the reference",
    )
    parser.add_argument(
        "--detector",
        default="BSE",
        help="in folders, only use images whose filename names this detector (BSE, ETD, Inlens, or 'all')",
    )
    parser.add_argument("--out", default="out", help="output folder (default: out)")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run GET4 on the command line (`argv` defaults to sys.argv[1:])."""
    parser = build_parser()
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.compare:
        if args.project or args.inputs or args.list_only:
            parser.error("--compare cannot be combined with --project, --list-only, or image inputs")
        tol_abs = parse_tolerances(args.tol)
        try:
            result = compare_lots(*args.compare, tol_abs, args.tol_rel)
        except ValueError as e:
            parser.error(str(e))
        names = [Path(f).parent.name or Path(f).stem for f in args.compare]
        tol_note = ", ".join(f"{k} +-{v}" for k, v in tol_abs.items())
        tol_note = (
            tol_note + "; " if tol_note else ""
        ) + f"others +-{100 * args.tol_rel:.0f}% of lot A (set real limits from the material spec with --tol)"
        print_comparison(result, names[0], names[1], tol_note)
        (out / "comparison.json").write_text(json.dumps(result, indent=2))
        return

    if args.project:
        if args.inputs:
            parser.error("--project cannot be combined with image inputs")
        if args.baseline:
            parser.error("--baseline is not supported with --project; analyse a batch separately to use one")
        raw_root = RAW_ROOT
        if args.batch:
            batches = [raw_root / name for name in args.batch]
            missing = [path.name for path in batches if not path.is_dir() or path.parent != raw_root]
            if missing:
                parser.error(f"no such folder under {raw_root}: {', '.join(missing)}")
        else:
            batches = (
                sorted(
                    path
                    for path in raw_root.iterdir()
                    if path.is_dir() and re.fullmatch(r"batch_\d+", path.name.lower())
                )
                if raw_root.is_dir()
                else []
            )
        if not batches:
            parser.error(f"no data/raw/batch_N folders found under {raw_root}")
        for batch_dir in batches:
            grouped = {tag: [] for tag in DETECTOR_TAGS}
            locations = {}
            location_views = {}
            image_paths = sorted(
                path for path in batch_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
            for path in image_paths:
                detector = _detector_of(path)
                location = _location_of(path)
                if detector is None or location is None:
                    parser.error(f"cannot determine location and supported detector from filename: {path.name}")
                grouped[detector].append(path)
                locations[path.name] = location
                location_views.setdefault(location, []).append({"detector": detector.upper(), "image": path.name})
            if not image_paths:
                parser.error(f"no supported images found in {batch_dir}")
            for detector in DETECTOR_TAGS:
                paths = grouped[detector]
                if not paths:
                    continue
                args.detector = detector.upper()
                class_names = PHASES if detector == "bse" else INTENSITY_CLASSES
                print(f"\n=== project analysis: {batch_dir.name} / {args.detector} ({len(paths)} images) ===")
                if args.list_only:
                    for path in paths:
                        print(f"  {locations[path.name]} :: {args.detector} :: {path.name}")
                    continue
                analyse_paths(
                    paths,
                    args,
                    out / batch_dir.name / args.detector,
                    parser,
                    class_names=class_names,
                    locations=locations,
                    batch_id=batch_dir.name,
                )
            if not args.list_only:
                manifest = {
                    "batch": batch_dir.name,
                    "location_code_source": "filename component after 'img_' and before the detector suffix",
                    "locations": [
                        {"location_id": location, "views": sorted(views, key=lambda view: view["detector"])}
                        for location, views in sorted(location_views.items())
                    ],
                }
                (out / batch_dir.name / "location_manifest.json").write_text(json.dumps(manifest, indent=2))
        return
    if args.list_only:
        parser.error("--list-only requires --project")

    paths = collect_images(args.inputs, args.detector.lower())
    if not paths:
        parser.error(f"no images found (in folders, only files tagged {args.detector} or untagged are used)")
    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    if baseline and "phases" not in baseline and "intensity_classes" not in baseline:
        # Older batch JSON stored phase estimates at top level.
        baseline = {"phases": baseline}
    analyse_paths(paths, args, out, parser, baseline)
