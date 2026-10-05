"""Shared helpers: batch IDs, their raw-image folders, and reading generated JSON outputs."""

import json
from pathlib import Path

from fastapi import HTTPException

from .paths import IMAGE_NAME_PATTERN, RAW_DATA_DIR, UNKNOWN_BATCH


def is_image_batch(batch_id: str) -> bool:
    """Reference batches are numeric; the unknown set uses the ID "unknown"."""
    return batch_id.isdigit() or batch_id == UNKNOWN_BATCH


def get_batch_image_directory(batch_id: str) -> Path:
    """Return a valid local raw-image directory for a reference batch number or the unknown set."""
    if not is_image_batch(batch_id):
        raise HTTPException(404, f"Unknown image batch {batch_id}")
    directory = RAW_DATA_DIR / (UNKNOWN_BATCH if batch_id == UNKNOWN_BATCH else f"batch_{batch_id}")
    if not directory.is_dir():
        raise HTTPException(404, f"Image directory for batch {batch_id} was not found")
    return directory


def find_batch_image(batch_id: str, image_name: str) -> Path:
    """Resolve an image name only when it matches an indexed file in its batch."""
    directory = get_batch_image_directory(batch_id)
    for path in directory.iterdir():
        if path.is_file() and path.name == image_name and IMAGE_NAME_PATTERN.fullmatch(path.name):
            return path
    raise HTTPException(404, f"Unknown image {image_name} in batch {batch_id}")


def read_kpi_json(path: Path, missing: str) -> dict:
    """Read an analysis.kpis / analysis.classify output, mapping absent or corrupt files to HTTP errors."""
    if not path.is_file():
        raise HTTPException(
            404,
            f"{missing}; run python -m analysis.kpis (or python -m analysis.classify "
            "for the unknown set) to generate it",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise HTTPException(500, f"{path.name} is invalid JSON") from error
