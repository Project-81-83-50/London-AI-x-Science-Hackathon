"""Choosing input images: detector and location codes from filenames, and folder expansion."""

import re
from pathlib import Path

from .constants import IMAGE_SUFFIXES

DETECTOR_TAGS = ("bse", "etd", "inlens", "se", "tld", "cbs")


def _detector_of(path: str | Path) -> str | None:
    """Detector named in the filename, e.g. img_0grcilhi_BSE.tif -> 'bse' (None if untagged)."""
    parts = re.split(r"[_\-. ]", Path(path).stem.lower())
    return next((t for t in DETECTOR_TAGS if t in parts), None)


def _location_of(path: str | Path) -> str | None:
    """Return the leading image code, which identifies a location in project filenames."""
    match = re.fullmatch(r"img_([^_]+)_[A-Za-z0-9-]+(?: \(\d+\))?", Path(path).stem, re.IGNORECASE)
    return match.group(1).casefold() if match else None


def collect_images(inputs: list[str], detector: str = "bse", require_detector: bool = False) -> list[Path]:
    """Images to treat as separate fields. In a folder, files tagged with another detector
    are skipped: BSE / ETD / InLens of one spot are one field, not three. Project mode can
    also require an explicit detector tag so unknown files are never treated as BSE."""
    paths, skipped = [], []
    for p in map(Path, inputs):
        if p.is_dir():
            for q in sorted(q for q in p.iterdir() if q.suffix.lower() in IMAGE_SUFFIXES):
                tag = _detector_of(q)
                exclude = (require_detector and tag is None) or (tag and detector != "all" and tag != detector)
                (skipped if exclude else paths).append(q)
        else:
            paths.append(p)
    if skipped:
        print(f"using {detector.upper()} images only; skipped: {', '.join(q.name for q in skipped)}")
    return paths
