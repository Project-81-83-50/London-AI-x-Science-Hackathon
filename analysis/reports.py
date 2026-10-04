"""Run the reference-batch report generators in one command."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
GET4_OUT = ROOT / "data" / "processed" / "get4"
IMAGE_SUFFIXES = {".tif", ".tiff", ".png"}


def reference_batches():
    """Return populated batch_N folders in numeric order."""
    batches = []
    if RAW.is_dir():
        for path in RAW.iterdir():
            match = re.fullmatch(r"batch_(\d+)", path.name, re.IGNORECASE)
            if path.is_dir() and match and any(
                image.is_file() and image.suffix.lower() in IMAGE_SUFFIXES
                for image in path.iterdir()
            ):
                batches.append((int(match.group(1)), path))
    return sorted(batches)


def run(command, description):
    print(f"\n=== {description} ===", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Generate the reference-batch reports used by the local app."
    )
    parser.add_argument(
        "--full-resolution",
        action="store_true",
        help="run GET4 without fast sampling or diagnostic-plot skipping",
    )
    args = parser.parse_args()

    batches = reference_batches()
    if not batches:
        parser.error(f"no images found directly inside data/raw/batch_N folders under {RAW}")

    batch_ids = [str(number) for number, _ in batches]
    print(f"Generating reports for batches: {', '.join(batch_ids)}")

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

    print("\nAll reference-batch reports generated successfully.")


if __name__ == "__main__":
    main()
