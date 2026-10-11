"""Run the reference-batch report generators in one command.

Runs, as subprocesses from the repository root: analysis.kpis for every populated ReferenceBatches/Batch_N (else
data/raw/batch_N) folder, analysis.get4 --project (with --fast unless --full-resolution) into data/processed/get4,
and analysis.v3_report.

    python -m analysis.reports [--full-resolution]
"""

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

from . import configure_cli_logging, paths

logger = logging.getLogger(__name__)

ROOT = paths.REPO_ROOT
RAW = paths.RAW_DIR
GET4_OUT = paths.GET4_DIR
IMAGE_SUFFIXES = {".tif", ".tiff", ".png"}


def reference_batches() -> list[tuple[int, Path]]:
    """Return populated batch folders in numeric order. A present ReferenceBatches/Batch_N folder takes precedence
    over data/raw/batch_N (as in analysis.fields.batch_dir), unless RAW was overridden."""
    roots = [RAW] + ([paths.REFERENCE_BATCHES_DIR] if RAW == paths.RAW_DIR else [])
    found = {}
    for root in roots:  # later roots replace earlier ones
        if root.is_dir():
            for path in root.iterdir():
                match = re.fullmatch(r"batch_(\d+)", path.name, re.IGNORECASE)
                if path.is_dir() and match:
                    found[int(match.group(1))] = path
    return sorted(
        (number, path)
        for number, path in found.items()
        if any(image.is_file() and image.suffix.lower() in IMAGE_SUFFIXES for image in path.iterdir())
    )


def run(command: list[str], description: str) -> None:
    """Run one generator from the repository root; a failure stops the whole run."""
    logger.info("\n=== %s ===", description)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the reference-batch reports used by the local app.")
    parser.add_argument(
        "--full-resolution",
        action="store_true",
        help="run GET4 without fast sampling or diagnostic-plot skipping",
    )
    args = parser.parse_args()
    configure_cli_logging()

    batches = reference_batches()
    if not batches:
        parser.error(
            f"no images found directly inside ReferenceBatches/Batch_N or data/raw/batch_N folders under {ROOT}"
        )

    batch_ids = [str(number) for number, _ in batches]
    logger.info("Generating reports for batches: %s", ", ".join(batch_ids))

    run(
        [sys.executable, "-m", "analysis.kpis", "--batches", *batch_ids],
        "KPI reports and overlays",
    )

    get4_command = [
        sys.executable,
        "-m",
        "analysis.get4",
        "--project",
        "--out",
        str(GET4_OUT),
    ]
    if not args.full_resolution:
        get4_command.append("--fast")
    run(get4_command, "GET4 uncertainty and analysis reports")

    run(
        [sys.executable, "-m", "analysis.v3_report"],
        "General and Detailed reports",
    )

    logger.info("\nAll reference-batch reports generated successfully.")


if __name__ == "__main__":
    main()
