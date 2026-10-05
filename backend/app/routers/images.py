"""Raw microscopy images: grouped listing, cached JPEG previews and TIFF downloads (frontend: Images tab)."""

import json
import logging
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from PIL import Image

from ..batches import find_batch_image, get_batch_image_directory
from ..paths import FIELD_DATA_DIR, IMAGE_NAME_PATTERN, PREVIEW_CACHE_DIR

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/batches/{batch_id}/images")
def list_batch_images(batch_id: str) -> list[dict[str, Any]]:
    """List local TIFF views grouped by the field of view they show.

    Filename codes do not identify fields, so when analysis.fields has produced a manifest
    covering exactly these files, its image-matched fields are used. Otherwise the views fall
    back to filename-code groups, marked with grouping "filename" so the UI can warn."""
    directory = get_batch_image_directory(batch_id)
    files = {}
    for path in sorted(directory.iterdir()):
        match = IMAGE_NAME_PATTERN.fullmatch(path.name)
        if path.is_file() and match:
            files[path.name] = match
    manifest_path = FIELD_DATA_DIR / f"batch_{batch_id}.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            listed = {view["filename"] for field in manifest["fields"] for view in field["views"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Ignoring unreadable field manifest %s; grouping by filename", manifest_path, exc_info=True)
            listed = None
        if listed == set(files):
            return [
                {
                    "specimen_id": field.get("location", field["field_id"]),
                    "field_id": field["field_id"],
                    "location_recovered": field.get("location_recovered"),
                    "location_alternatives": field.get("location_alternatives", []),
                    "grouping": "matched",
                    "match_confidence": field["confidence"],
                    "filename_codes": field["filename_codes"],
                    # "filter" stays the filename label (other code keys on it); "detector" is the
                    # detector identified from the image itself.
                    "images": [
                        {
                            "filter": files[view["filename"]].group("filter"),
                            "filename": view["filename"],
                            "detector": view.get("detector"),
                            "display_name": view.get("display_name"),
                            "label_matches_image": view.get("label_matches_image"),
                            "detector_confidence": view.get("detector_confidence"),
                        }
                        for view in sorted(
                            field["views"],
                            key=lambda v: {"BSE": 0, "InLens": 1, "ETD": 2}.get(v.get("detector"), 3),
                        )
                    ],
                }
                for field in sorted(manifest["fields"], key=lambda f: f.get("location", f["field_id"]))
            ]
    groups: dict[str, list[dict[str, str]]] = {}
    for name, match in files.items():
        groups.setdefault(match.group("specimen"), []).append({"filter": match.group("filter"), "filename": name})
    return [
        {"specimen_id": specimen_id, "grouping": "filename", "images": images}
        for specimen_id, images in sorted(groups.items())
    ]


@router.get("/batches/{batch_id}/images/{image_name}")
def get_batch_image(
    batch_id: str,
    image_name: str,
    download: bool = Query(default=False),
) -> FileResponse:
    """Serve a browser-friendly JPEG preview or the original TIFF download."""
    path = find_batch_image(batch_id, image_name)
    if download:
        return FileResponse(path, media_type="image/tiff", filename=path.name)

    # Decoding a full TIFF takes ~0.7 s, so each preview is built once and cached on disk. The cache key
    # includes the file's size and modification time, so a replaced or edited TIFF gets a fresh preview.
    stat = path.stat()
    cache_dir = PREVIEW_CACHE_DIR / f"batch_{batch_id}"
    cached = cache_dir / f"{path.stem}_{stat.st_size}_{stat.st_mtime_ns}.jpg"
    if not cached.is_file():
        try:
            with Image.open(path) as image:
                image.thumbnail((1800, 1200), Image.Resampling.LANCZOS)
                preview = image.convert("RGB")
                output = BytesIO()
                preview.save(output, format="JPEG", quality=88, optimize=True)
        except OSError as error:
            logger.warning("Could not decode %s for a preview: %s", path, error)
            raise HTTPException(500, f"Could not decode image {image_name}") from error
        cache_dir.mkdir(parents=True, exist_ok=True)
        for stale in cache_dir.glob(f"{path.stem}_*.jpg"):
            stale.unlink(missing_ok=True)
        temporary = cached.with_suffix(".tmp")
        temporary.write_bytes(output.getvalue())
        temporary.replace(cached)

    return FileResponse(
        cached,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )
